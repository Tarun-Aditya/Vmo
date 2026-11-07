"""Word export. A draft becomes a clean .docx (pandoc). A redline becomes a .docx with real tracked changes (w:ins / w:del, author ContractIQ)
that Word shows with Accept / Reject, so the reviewed text can go back to the vendor in the format lawyers use."""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
AUTHOR = "ContractIQ"


def md_to_docx(md: str) -> bytes:
    if not shutil.which("pandoc"):
        raise RuntimeError("Word export needs pandoc on the machine running the API")
    md = re.sub(r"<!--.*?-->", "", md)
    with tempfile.TemporaryDirectory() as td:
        src, out = Path(td) / "a.md", Path(td) / "a.docx"
        src.write_text(md)
        r = subprocess.run(["pandoc", str(src), "-f", "markdown", "-o", str(out)], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"pandoc failed: {r.stderr[:200]}")
        return out.read_bytes()


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def _run(text: str, kind: str, rid: list[int], when: str) -> str:
    t = f'<w:t xml:space="preserve">{escape(text)}</w:t>'
    if kind == "del":
        rid[0] += 1
        return f'<w:del w:id="{rid[0]}" w:author="{AUTHOR}" w:date="{when}"><w:r><w:delText xml:space="preserve">{escape(text)}</w:delText></w:r></w:del>'
    if kind == "ins":
        rid[0] += 1
        return f'<w:ins w:id="{rid[0]}" w:author="{AUTHOR}" w:date="{when}"><w:r>{t}</w:r></w:ins>'
    return f"<w:r>{t}</w:r>"


def _para_text(p: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))


def _unescape(s: str) -> str:
    return s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")


def redline_docx(md: str, items: list[dict], decisions: dict[str, str] | None = None) -> tuple[bytes, dict]:
    """Tracked changes for every deviation: undecided and accepted changes are marked (accepted ones shown as already-inserted wording
    without a deletion), rejected ones are left out. Returns (docx bytes, {changes, inserted_clauses})."""
    decisions = decisions or {}
    base = md_to_docx(md)
    zin = zipfile.ZipFile(io.BytesIO(base))
    doc = zin.read("word/document.xml").decode("utf8")
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rid = [100]
    paras = list(re.finditer(r"<w:p>.*?</w:p>|<w:p [^>]*>.*?</w:p>", doc, re.S))
    texts = [_norm(_unescape(_para_text(m.group(0)))) for m in paras]
    out_doc, last, stats = [], 0, {"changes": 0, "inserted_clauses": 0}
    used: set[int] = set()
    repl: dict[int, str] = {}
    appended: list[str] = []
    for it in items:
        d = decisions.get(it["clause_type"])
        if d == "rejected":
            continue
        if it["status"] == "changed" and it.get("draft_text"):
            want = _norm(it["draft_text"])
            idx = next((i for i, t in enumerate(texts) if i not in used and want and want in t), None)
            if idx is None:
                continue
            used.add(idx)
            t = texts[idx]
            pre, post = t.split(want, 1)[0], t.split(want, 1)[1]
            body = _run(it["suggested_text"], "ins", rid, when) if d == "accepted" else "".join(_run(x[1], x[0], rid, when) if x[0] in ("del", "ins") else _run(x[1], "eq", rid, when) for x in _spaced(it["diff"]))
            repl[idx] = "<w:p>" + (_run(pre + " ", "eq", rid, when) if pre else "") + body + (_run(" " + post, "eq", rid, when) if post else "") + "</w:p>"
            stats["changes"] += 1
        elif it["status"] == "missing" and it.get("suggested_text"):
            h, b = escape(it["heading"] + " (new clause)"), it["suggested_text"]
            appended.append(f'<w:p><w:pPr><w:pStyle w:val="Heading2"/><w:rPr><w:ins w:id="{rid[0] + 1}" w:author="{AUTHOR}" w:date="{when}"/></w:rPr></w:pPr>{_run(h, "ins", rid, when)}</w:p>'
                            f'<w:p><w:pPr><w:rPr><w:ins w:id="{rid[0] + 2}" w:author="{AUTHOR}" w:date="{when}"/></w:rPr></w:pPr>{_run(b, "ins", rid, when)}</w:p>')
            rid[0] += 2
            stats["inserted_clauses"] += 1
    for i, m in enumerate(paras):
        out_doc.append(doc[last:m.start()])
        out_doc.append(repl.get(i, m.group(0)))
        last = m.end()
    out_doc.append(doc[last:])
    new = "".join(out_doc)
    if appended:
        new = new.replace("<w:sectPr", "".join(appended) + "<w:sectPr", 1) if "<w:sectPr" in new else new.replace("</w:body>", "".join(appended) + "</w:body>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            zout.writestr(name, new.encode("utf8") if name == "word/document.xml" else zin.read(name))
    return buf.getvalue(), stats


def _spaced(diff: list) -> list:
    """Word-level diff ops with a space between neighbouring segments."""
    out = []
    for i, (op, t) in enumerate(diff):
        out.append((op, t + (" " if i < len(diff) - 1 else "")))
    return out


def count_tracked(docx: bytes) -> dict:
    x = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode("utf8")
    return {"ins": len(re.findall(r"<w:ins ", x)), "del": len(re.findall(r"<w:del ", x))}
