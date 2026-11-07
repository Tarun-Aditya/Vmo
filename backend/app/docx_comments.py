"""Word margin comments: write a document's comment threads into a .docx (so Word / Google Docs show them), and read the comments of a returned .docx back as threads.
Each thread is attached to the paragraph that contains its anchor text; replies are separate comments on the same range; resolved threads are prefixed [Resolved]."""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace(" ", " ")).strip().lower()


def _unescape(s: str) -> str:
    return s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")


def _ptext(p: str) -> str:
    return _unescape("".join(re.findall(r"<w:(?:t|delText)[^>]*>([^<]*)</w:(?:t|delText)>", p)))


def add_comments(docx: bytes, threads: list[dict]) -> tuple[bytes, int]:
    """Returns (docx with comments, number of comment entries written)."""
    threads = [t for t in threads if t.get("comments")]
    if not threads:
        return docx, 0
    zin = zipfile.ZipFile(io.BytesIO(docx))
    doc = zin.read("word/document.xml").decode("utf8")
    paras = list(re.finditer(r"<w:p>.*?</w:p>|<w:p [^>]*>.*?</w:p>", doc, re.S))
    texts = [_norm(_ptext(m.group(0))) for m in paras]
    entries: list[str] = []
    marks: dict[int, list[int]] = {}
    cid = 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for t in threads:
        q = _norm(t.get("anchor_text") or "")
        idx = next((i for i, x in enumerate(texts) if q and q[:80] in x), 0 if paras else None)
        if idx is None:
            continue
        for c in t["comments"]:
            body = ("[Resolved] " if t["status"] == "resolved" else "") + c["body"]
            ps = "".join(f'<w:p><w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>' for line in body.split("\n") if line.strip()) or "<w:p/>"
            initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", c["author"])[:2]).upper() or "C"
            entries.append(f'<w:comment w:id="{cid}" w:author="{escape(c["author"])}" w:date="{now}" w:initials="{initials}">{ps}</w:comment>')
            marks.setdefault(idx, []).append(cid)
            cid += 1
    out, last = [], 0
    for i, m in enumerate(paras):
        out.append(doc[last:m.start()])
        p = m.group(0)
        if i in marks:
            starts = "".join(f'<w:commentRangeStart w:id="{c}"/>' for c in marks[i])
            ends = "".join(f'<w:commentRangeEnd w:id="{c}"/><w:r><w:commentReference w:id="{c}"/></w:r>' for c in marks[i])
            p = re.sub(r"(<w:p(?: [^>]*)?>)(<w:pPr>.*?</w:pPr>)?", lambda mm: mm.group(1) + (mm.group(2) or "") + starts, p, count=1, flags=re.S)
            p = p[:-len("</w:p>")] + ends + "</w:p>"
        out.append(p)
        last = m.end()
    out.append(doc[last:])
    new_doc = "".join(out)
    comments = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:comments xmlns:w="{W_NS}">{"".join(entries)}</w:comments>'
    ct = zin.read("[Content_Types].xml").decode("utf8")
    if "comments+xml" not in ct:
        ct = ct.replace("</Types>", '<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/></Types>')
    rels = zin.read("word/_rels/document.xml.rels").decode("utf8")
    if "relationships/comments" not in rels:
        rels = rels.replace("</Relationships>", '<Relationship Id="rIdCmt1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            if name in ("word/comments.xml",):
                continue
            data = {"word/document.xml": new_doc, "[Content_Types].xml": ct, "word/_rels/document.xml.rels": rels}.get(name)
            zout.writestr(name, data.encode("utf8") if data is not None else zin.read(name))
        zout.writestr("word/comments.xml", comments.encode("utf8"))
    return buf.getvalue(), len(entries)


def read_comments(docx: bytes) -> list[dict]:
    """[{author, body, anchor_text, date}] for every comment in a .docx; the anchor is the text of the paragraph the comment range sits in."""
    z = zipfile.ZipFile(io.BytesIO(docx))
    if "word/comments.xml" not in z.namelist():
        return []
    cx = z.read("word/comments.xml").decode("utf8")
    doc = z.read("word/document.xml").decode("utf8")
    anchors: dict[str, str] = {}
    for m in re.finditer(r"<w:p>.*?</w:p>|<w:p [^>]*>.*?</w:p>", doc, re.S):
        for cid in re.findall(r'<w:commentRangeStart w:id="(\d+)"', m.group(0)):
            anchors[cid] = _ptext(m.group(0)).strip()
    out = []
    for m in re.finditer(r'<w:comment ([^>]*)>(.*?)</w:comment>', cx, re.S):
        a = dict(re.findall(r'w:(\w+)="([^"]*)"', m.group(1)))
        body = "\n".join(_ptext(p) for p in re.findall(r"<w:p[ >].*?</w:p>|<w:p/>", m.group(2), re.S)).strip()
        out.append(dict(author=_unescape(a.get("author", "Word user")), body=body, anchor_text=anchors.get(a.get("id", ""), "")[:300], date=a.get("date")))
    return out
