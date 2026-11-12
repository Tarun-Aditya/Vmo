"""Compare clauses to the standard template + playbook. Used for (a) executed-contract deviation
tracking and (b) the draft redline. Claude judges each *changed* clause; without an API key a
deterministic engine does it (word diff + playbook keyword rules)."""

from __future__ import annotations

import difflib
import re
from concurrent.futures import ThreadPoolExecutor

from app import llm
from app.config import settings
from app.docgen.library import (
    CLAUSES,
    OPTIONAL,
    STD,
    TEMPLATES,
    VARIANTS,
    clause_text,
    standard_text,
)

SEV_ORDER = ["low", "medium", "high", "critical"]


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip())


def word_diff(old: str, new: str) -> list[list[str]]:
    """[[op, text], ...] with op in eq|del|ins - drives the redline view."""
    a, b = old.split(), new.split()
    if difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio() < 0.55:
        # mostly rewritten: show whole-clause replacement instead of confetti
        return ([["del", old]] if old else []) + [["ins", new]]
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append(["eq", " ".join(a[i1:i2])])
        else:
            if i2 > i1:
                ops.append(["del", " ".join(a[i1:i2])])
            if j2 > j1:
                ops.append(["ins", " ".join(b[j1:j2])])
    return ops


def _summarise(ctype: str, std: str, found: str) -> str:
    changes = []
    for op, txt in word_diff(std, found):
        if op == "del":
            changes.append(f'removes "{txt[:80]}"')
        elif op == "ins":
            changes.append(f'adds "{txt[:80]}"')
    return f"{CLAUSES[ctype].heading}: " + "; ".join(changes[:3]) + "."


def heuristic_compare(ctype: str, std: str, found: str, doc: str = "Agreement") -> dict:
    """Offline rules engine. Known risky wordings (the pattern library) get a curated summary and
    severity; anything else falls back to a word diff with playbook-based severity. This is NOT a
    substitute for the Claude path: it only recognises patterns it has been given."""
    m = re.search(r"at least (\d+) days", found)
    ctx = {"notice_period_days": m.group(1) if m else "60"}
    for v in VARIANTS.get(ctype, {}).values():
        if norm(clause_text(ctype, doc, ctx, v.name)) == norm(found):
            return dict(
                is_deviation=True,
                deviation=f"{v.summary}.",
                severity=v.severity,
                suggested_text=std,
            )
    c = CLAUSES[ctype]
    low = found.lower()
    sev = {"critical": "high"}.get(c.severity_if_missing, c.severity_if_missing)
    if ctype == "termination_for_cause" or ctype == "non_solicit":
        sev = "low"
    if "unlimited" in low or "any country" in low:
        sev = "critical"
    elif ctype == "data_protection" and "considers appropriate" in low:
        sev = "critical"
    else:
        # numeric-only change that matches the playbook fallback is acceptable (low)
        nums = {t for op, t in word_diff(std, found) if op == "ins"}
        fb = c.fallback.lower()
        if (
            nums
            and all(re.fullmatch(r"[\d.%]+", n.strip(".,")) or n.strip(".,") in fb for n in nums)
            and any(n.strip(".,") in fb for n in nums)
        ):
            sev = "low"
    return dict(
        is_deviation=True, deviation=_summarise(ctype, std, found), severity=sev, suggested_text=std
    )


def _llm_tool() -> dict:
    return {
        "name": "report_comparison",
        "description": "Report the comparison result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "is_deviation": {"type": "boolean"},
                "deviation": {"type": "string"},
                "severity": {"type": "string", "enum": SEV_ORDER},
                "suggested_text": {"type": "string"},
            },
            "required": ["is_deviation", "deviation", "severity", "suggested_text"],
        },
    }


def llm_compare(ctype: str, doc: str, std: str, found: str) -> dict:
    c = CLAUSES[ctype]
    user = (
        f"Clause type: {c.heading}\n\nSTANDARD:\n{std}\n\nPLAYBOOK POSITION:\n{c.playbook}\n\n"
        f"FALLBACK:\n{c.fallback.format(**{**STD, 'doc': doc}) or '(none)'}\n\n"
        f"DRAFT:\n{found}"
    )
    return llm.call_tool(
        "redline",
        settings.model_redline,
        llm.prompt("redline_clause"),
        user,
        _llm_tool(),
        max_tokens=1000,
    )


def compare_document(clauses: list[dict], template_type: str, mode: str = "auto") -> list[dict]:
    """Align a document's clauses to its template and return deviation items.

    Item: {clause_type, heading, status[changed|missing], draft_text, standard_text,
           standard_position, deviation, severity, suggested_text, diff, page}
    """
    tdef = TEMPLATES[template_type]
    doc = tdef["doc"]
    by = {c["clause_type"]: c for c in clauses}
    use_llm = mode == "llm" or (mode == "auto" and llm.available())
    jobs, items = [], []
    for ct in tdef["clauses"]:
        c = CLAUSES[ct]
        if c.variable or ct in OPTIONAL:
            continue
        std = standard_text(ct, doc)
        found = by.get(ct)
        if not found:
            items.append(
                dict(
                    clause_type=ct,
                    heading=c.heading,
                    status="missing",
                    draft_text="",
                    standard_text=std,
                    standard_position=c.playbook,
                    deviation=f"The {c.heading} clause is missing.",
                    severity=c.severity_if_missing,
                    suggested_text=std,
                    diff=[["ins", std]],
                    page=None,
                )
            )
        elif norm(found["text"]) != norm(std):
            jobs.append((ct, std, found))

    def run(job):
        ct, std, found = job
        if use_llm and llm.available():
            try:
                return ct, std, found, llm_compare(ct, doc, std, found["text"])
            except Exception as e:      # limit reached / network: fall back to the pattern library for this clause
                llm.note_failure(e)
        return ct, std, found, heuristic_compare(ct, std, found["text"], doc)

    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(run, jobs)) if use_llm else [run(j) for j in jobs]
    for ct, std, found, r in results:
        if not r["is_deviation"]:
            continue
        sug = r["suggested_text"] or std
        items.append(
            dict(
                clause_type=ct,
                heading=CLAUSES[ct].heading,
                status="changed",
                draft_text=found["text"],
                standard_text=std,
                standard_position=CLAUSES[ct].playbook,
                deviation=r["deviation"],
                severity=r["severity"],
                suggested_text=sug,
                diff=word_diff(found["text"], sug),
                page=found["page"],
            )
        )
    items.sort(key=lambda i: -SEV_ORDER.index(i["severity"]))
    return items


def compare_custom(clauses: list[dict], kcc_cfg: list[dict], doc_type: str) -> list[dict]:
    """Redline items for clauses an admin added to the library (they have no template page): missing -> insert the standard wording,
    present but worded very differently -> flag it with the standard wording as the suggestion."""
    import difflib

    by = {c["clause_type"]: c for c in clauses}
    items = []
    for k in kcc_cfg:
        std = (k.get("standard_text") or "").strip()
        if k.get("builtin") or not k.get("enabled", True) or not std or (k.get("applies_to") and doc_type not in k["applies_to"]):
            continue
        found = by.get(k["key"])
        base = dict(clause_type=k["key"], heading=k["name"], standard_text=std, standard_position=k.get("playbook_position") or "", suggested_text=std)
        if not found:
            items.append({**base, "status": "missing", "draft_text": "", "deviation": f"The {k['name']} clause is missing.",
                          "severity": k.get("severity_if_missing") or "medium", "diff": [["ins", std]], "page": None})
        elif difflib.SequenceMatcher(None, norm(found["text"]), norm(std)).ratio() < 0.5:
            items.append({**base, "status": "changed", "draft_text": found["text"], "deviation": f"{k['name']} is worded differently from the standard position.",
                          "severity": "medium", "diff": word_diff(found["text"], std), "page": found["page"]})
    return items
