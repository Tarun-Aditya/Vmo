"""Score the extraction engine on REAL contracts: CUAD v1 (510 commercial contracts from SEC filings with expert clause labels, CC BY 4.0, https://zenodo.org/records/4595826).
Download and unzip CUAD_v1.zip, then: python evals/cuad_eval.py /path/to/CUAD_v1 [--n 150] [--seed 1] [--pdf]
Run with LLM_PROVIDER=offline (rules) or unset (Claude fills gaps). CUAD labels are NOT VMO-shaped (distribution, licence, sponsorship ... agreements), so this measures robustness on
real, messy text: clause detection (precision / recall), governing law, effective date, termination for convenience, liability cap.
Reported honestly: where the engine abstains (None) it counts as a miss for recall and not as a false positive."""
import csv
import random
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from app import docstruct, extraction, kcc, pipeline
from app.db import SessionLocal
from app.parsing import parse_document
from app.textutil import find_dates

# our key clause <- CUAD label columns (any 'Yes' means the clause is present)
PRESENCE = {"termination_for_convenience": ["Termination For Convenience"], "liability_cap": ["Cap On Liability", "Uncapped Liability"], "audit_rights": ["Audit Rights"], "assignment": ["Anti-Assignment"],
            "insurance": ["Insurance"], "ip_ownership": ["Ip Ownership Assignment", "Joint Ip Ownership"], "non_solicit": ["No-Solicit Of Customers", "No-Solicit Of Employees"]}                                                 # (warranties is left out: CUAD labels only a stated warranty DURATION, our clause is any warranty)


def parse_cuad_date(s: str):
    s = (s or "").strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d if d.year <= date.today().year + 30 else date(d.year - 100, d.month, d.day)
        except ValueError:
            pass
    d = find_dates(s)
    return d[0][1] if d else None


def main() -> int:
    root = Path(sys.argv[1])
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 150
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 1
    use_pdf = "--pdf" in sys.argv
    split = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else "all"      # train (70%) | test (30%, never tuned on) | all; fixed by a hash of the file name
    dump = sys.argv[sys.argv.index("--dump") + 1] if "--dump" in sys.argv else None
    import hashlib
    import json
    if split != "all":
        rows0 = list(csv.DictReader(open(root / "master_clauses.csv", encoding="utf-8-sig")))
        keep = {r["Filename"] for r in rows0 if (int(hashlib.md5(r["Filename"].encode()).hexdigest(), 16) % 10 < 7) == (split == "train")}
    else:
        keep = None
    miss: list[dict] = []
    rows = list(csv.DictReader(open(root / "master_clauses.csv", encoding="utf-8-sig")))
    random.Random(seed).shuffle(rows)
    if keep is not None:
        rows = [r for r in rows if r["Filename"] in keep]
    with SessionLocal() as s:
        cfg = pipeline.load_config(s)
    classify = lambda h, t: kcc.classify(h, t, cfg["kcc"])  # noqa: E731
    pres = {k: [0, 0, 0, 0] for k in PRESENCE}                      # tp fp fn tn
    fld = defaultdict(lambda: [0, 0])                                 # field -> [right, total]
    tfc = [0, 0, 0, 0]
    done, errors = 0, 0
    for r in rows:
        if done >= n:
            break
        name = r["Filename"]
        f = (next((root / "full_contract_pdf").rglob(Path(name).stem + ".*"), None) if use_pdf else root / "full_contract_txt" / (Path(name).stem + ".txt"))
        if f is None or not f.exists():
            continue
        try:
            md = docstruct.load_document(f)
            header, clauses = parse_document(md, classify)
            if "--no-text-detect" not in sys.argv:
                clauses += kcc.detect_in_text(clauses, md, {c["clause_type"] for c in clauses}, {k["key"] for k in cfg["kcc"] if k.get("enabled", True)})
            out, _ = extraction.extract(md, header, clauses, "MSA")
        except Exception as e:                                        # a real contract must never crash the pipeline: count it
            errors += 1
            print("  ERROR", name[:60], type(e).__name__, str(e)[:80])
            continue
        done += 1
        types = {c["clause_type"] for c in clauses}
        for key, cols in PRESENCE.items():
            want = any(r.get(c + "-Answer", "").strip().lower() == "yes" or (r.get(c) or "").strip() not in ("", "[]") and c != "Uncapped Liability" and r.get(c + "-Answer") is None for c in cols)
            want = any((r.get(c + "-Answer") or "").strip().lower() == "yes" for c in cols)
            got = key in types
            i = (0 if got else 2) if want else (1 if got else 3)
            pres[key][i] += 1
            if dump and i in (1, 2):
                miss.append({"file": name, "kind": "presence", "clause": key, "error": "FP" if i == 1 else "FN", "label": " | ".join((r.get(c) or "")[:300] for c in cols), "ours": next((c["text"][:300] for c in clauses if c["clause_type"] == key), "")})
        v = lambda k: (out.get(k) or {}).get("value")  # noqa: E731
        gl = (r.get("Governing Law-Answer") or "").strip()
        if gl:
            fld["governing_law"][1] += 1
            fld["governing_law"][0] += bool(v("governing_law")) and (gl.lower().split(",")[0] in str(v("governing_law")).lower() or str(v("governing_law")).lower() in gl.lower())
        ed = parse_cuad_date(r.get("Effective Date-Answer") or "") or parse_cuad_date(r.get("Agreement Date-Answer") or "")
        if ed:
            fld["effective_date"][1] += 1
            fld["effective_date"][0] += str(v("effective_date"))[:10] == ed.isoformat()
        if dump:
            if gl and not (v("governing_law") and gl.lower().split(",")[0] in str(v("governing_law")).lower()):
                miss.append({"file": name, "kind": "field", "clause": "governing_law", "error": "FN", "label": gl, "ours": str(v("governing_law"))})
            if ed and str(v("effective_date"))[:10] != ed.isoformat():
                miss.append({"file": name, "kind": "field", "clause": "effective_date", "error": "FN", "label": ed.isoformat(), "ours": str(v("effective_date")), "head": md[:300]})
        want_t = (r.get("Termination For Convenience-Answer") or "").strip().lower() == "yes"
        got_t = v("termination_for_convenience") is True
        tfc[(0 if got_t else 2) if want_t else (1 if got_t else 3)] += 1
        capped = (r.get("Cap On Liability-Answer") or "").strip().lower() == "yes"
        unc = (r.get("Uncapped Liability-Answer") or "").strip().lower() == "yes"
        if capped or unc:
            fld["liability_stated"][1] += 1
            fld["liability_stated"][0] += (v("liability_cap_multiple") is not None) or bool(v("liability_cap_text")) or "liability_cap" in types
    print(f"contracts scored: {done} (errors: {errors}) from {'PDF' if use_pdf else 'text'}\n")
    print(f"{'clause presence':30s} {'precision':>9s} {'recall':>7s} {'F1':>6s}   tp/fp/fn")
    for k, (tp, fp, fn, tn) in pres.items():
        p, rc = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
        print(f"  {k:28s} {p:9.2f} {rc:7.2f} {2 * p * rc / max(p + rc, 1e-9):6.2f}   {tp}/{fp}/{fn}")
    tp, fp, fn, tn = tfc
    print(f"\n  termination_for_convenience=True  precision {tp / max(tp + fp, 1):.2f}  recall {tp / max(tp + fn, 1):.2f}  (tp/fp/fn {tp}/{fp}/{fn})")
    for k, (a, b) in fld.items():
        print(f"  {k:28s} {a}/{b} = {100 * a / max(b, 1):.1f}%")
    if dump:
        Path(dump).write_text(json.dumps(miss))
    print(f"\nOVERALL crashes: {errors}/{done + errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
