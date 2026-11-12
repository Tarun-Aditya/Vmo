"""Real documents in, structured Markdown out. PDF (pdftotext), Word (.docx via pandoc, or a built-in reader), HTML, Markdown and plain text
all become the internal form: '# Title', '## Heading' per clause, '<!-- page: n -->' markers. Headings of documents that carry no
Markdown / Word styles are recovered by rules (ARTICLE n, Section n, '3. Heading', ALL CAPS, short title lines)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from app import ingest_text

SUPPORTED_EXT = {".md", ".txt", ".docx", ".pdf", ".html", ".htm"}
ROMAN = r"[IVXLC]+"
H_ARTICLE = re.compile(rf"^\s*(?:ARTICLE|Article)\s+({ROMAN}|\d+)\s*[.:\-–—]?\s*(.*)$")
H_SECTION = re.compile(r"^\s*(?:SECTION|Section)\s+(\d+)\s*[.:\-–—]?\s*(.*)$")
H_NUM = re.compile(r"^\s*(\d{1,2})\.\s+([A-Z][A-Za-z0-9 ,&/'()\-–]{2,70})\s*$")
H_SCHEDULE = re.compile(r"^\s*(?:SCHEDULE|Schedule|APPENDIX|Appendix|EXHIBIT|Exhibit|ORDER FORM|Order Form|ANNEX|Annex)\b[\s\dA-Z.:\-–—]*(.{0,70})$")
SENTENCE_END = re.compile(r"[.;:,]\s*$")


def _page_split(text: str) -> list[str]:
    return text.split("\f")


def pdf_to_text(path: Path) -> str:
    if not shutil.which("pdftotext"):
        raise ValueError("PDF support needs poppler's pdftotext on the machine running the API")
    r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise ValueError(f"could not read the PDF: {r.stderr.strip()[:200]}")
    pages = [p for p in _page_split(r.stdout)]
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    if not "".join(pages).strip():
        return ocr_pdf(path)
    return "\n".join(f"<!-- page: {i} -->\n{merge_layout_tables(p)}" for i, p in enumerate(pages, 1))


_GAP = re.compile(r"\s{2,}")


def _segments(line: str) -> list[tuple[int, str]]:
    """(start offset, text) of each run of words separated by two or more spaces."""
    out, pos = [], len(line) - len(line.lstrip())
    for part in _GAP.split(line.strip()):
        pos = line.find(part, pos)
        out.append((pos, part))
        pos += len(part)
    return out


def merge_layout_tables(page: str) -> str:
    """pdftotext -layout prints a table as aligned columns and wraps a long cell over several lines, so reading line by line mixes the columns
    ('Planned-  27 November 2025  Schedule approved in / maintenance  writing by the'). A block of lines with three or more aligned columns is
    rebuilt as one pipe-separated line per table row, each wrapped cell joined back together. Two-column layouts (signature blocks) are left alone."""
    lines = page.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and lines[j].strip():
            j += 1
        block = lines[i:j]
        segs = [_segments(ln) for ln in block]
        wide = [sg for sg in segs if len(sg) >= 3]
        ncol = max((len(sg) for sg in wide), default=0)
        anchors = [sg for sg in wide if len(sg) == ncol]
        cols = [min(sg[k][0] for sg in anchors) for k in range(ncol)] if anchors else []
        aligned = len(anchors) >= 2 and all(abs(sg[k][0] - cols[k]) <= 2 for sg in anchors for k in range(ncol))
        if not aligned:
            out.extend(block)
        else:
            first = next(k for k, sg in enumerate(segs) if len(sg) == ncol)
            head = max((k for k in range(first) if len(segs[k]) == 1 and segs[k][0][0] < cols[1] - 2), default=-1) + 1
            out.extend(block[:head])              # a paragraph or heading directly above the table stays as it is
            rows: list[list[str]] = []
            for sg in segs[head:]:
                cells = [""] * ncol
                for off, txt in sg:
                    k = max((c for c in range(ncol) if cols[c] <= off + 2), default=0)
                    cells[k] = (cells[k] + " " + txt).strip()
                if rows and not cells[0] and len(sg) < ncol:       # a continuation line of the row above
                    for k in range(ncol):
                        if cells[k]:
                            rows[-1][k] = (rows[-1][k] + cells[k]) if re.search(r"[a-z]-$", rows[-1][k]) else (rows[-1][k] + " " + cells[k]).strip()
                elif rows and not rows[-1][0] and not any(len(x) == ncol for x in segs[head:head + len(rows)]):
                    rows[-1] = [(a + " " + b).strip() for a, b in zip(rows[-1], cells)]      # a header that started on the line above
                else:
                    rows.append(cells)
            out.extend("| " + " | ".join(r) + " |" for r in rows)
        out.extend(lines[j:j + 1])
        i = j + 1
    return "\n".join(out)


def ocr_pdf(path: Path) -> str:
    """Scanned PDF (no text layer): OCR with tesseract when it is installed."""
    if not (shutil.which("tesseract") and shutil.which("pdftoppm")):
        raise ValueError("this PDF has no text layer (a scan). OCR needs tesseract + pdftoppm installed on the API machine")
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", "200", "-png", str(path), f"{td}/p"], check=True, timeout=300)
        out = []
        for i, img in enumerate(sorted(Path(td).glob("p*.png")), 1):
            r = subprocess.run(["tesseract", str(img), "-", "--psm", "4"], capture_output=True, text=True, timeout=300)
            out.append(f"<!-- page: {i} -->\n{r.stdout}")
    return "\n".join(out)


def docx_to_text(path: Path) -> str:
    if shutil.which("pandoc"):
        r = subprocess.run(["pandoc", str(path), "-t", "markdown", "--wrap=none", "-f", "docx"], capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    return ingest_text.extract_text(path.name, path.read_bytes())


def _clean_heading(h: str) -> str:
    h = re.sub(r"\*+|_{2,}|`", "", h).strip(" -–—:.")
    return re.sub(r"\s+", " ", h)


def looks_structured(text: str) -> bool:
    return len(re.findall(r"^##\s+\S", text, re.M)) >= 4


def structure_text(text: str) -> str:
    """Add '# Title' and '## Heading' lines to unstructured text (PDF / plain / Word without heading styles)."""
    lines = text.replace("\r", "").split("\n")
    out: list[str] = []
    title_done = False
    i = 0
    n = len(lines)

    def next_nonblank(j: int) -> tuple[int, str]:
        while j < n and not lines[j].strip():
            j += 1
        return j, (lines[j].strip() if j < n else "")

    while i < n:
        raw = lines[i]
        line = raw.strip()
        if re.match(r"^<!--\s*page:\s*\d+\s*-->$", line):
            out.append(line)
            i += 1
            continue
        if not line:
            out.append("")
            i += 1
            continue
        if line.startswith("# "):
            out.append(line)
            title_done = True
            i += 1
            continue
        if line.startswith("## "):
            out.append(line)
            i += 1
            continue
        if not title_done:
            if len(line) < 120 and not SENTENCE_END.search(line):
                out.append(f"# {_clean_heading(line)}")
                title_done = True
                i += 1
                continue
            title_done = True
        m = H_ARTICLE.match(line) or H_SECTION.match(line)
        if m:
            rest = m.group(2).strip()
            if not rest:
                j, nxt = next_nonblank(i + 1)
                if nxt and len(nxt) < 70 and not SENTENCE_END.search(nxt):
                    rest, i = nxt, j
            label = re.match(r"^\s*(\w+\s+(?:\w+))", line)
            out.append(f"## {_clean_heading(rest) or _clean_heading(label.group(1) if label else line)}")
            i += 1
            continue
        m = H_NUM.match(line)
        if m and len(line.split()) <= 9 and not SENTENCE_END.search(line):
            out.append(f"## {m.group(1)}. {_clean_heading(m.group(2))}")
            i += 1
            continue
        if H_SCHEDULE.match(line) and len(line) < 80 and not SENTENCE_END.search(line):
            out.append(f"## {_clean_heading(line)}")
            i += 1
            continue
        letters = re.sub(r"[^A-Za-z]", "", line)
        pv = lines[i - 1].strip() if i else ""
        continuation = len(pv) > 40 and not SENTENCE_END.search(pv) and not pv.startswith(("#", "<!--"))      # a wrapped line of an ALL-CAPS paragraph is not a heading
        if 3 <= len(letters) and not continuation and line.upper() == line and len(line) <= 70 and not SENTENCE_END.search(line) and not re.search(r"\d{4}", line) and len(line.split()) <= 9:
            out.append(f"## {_clean_heading(line.title())}")
            i += 1
            continue
        prev_blank = i == 0 or not lines[i - 1].strip() or bool(re.match(r"^<!--", lines[i - 1].strip()))
        nxt_idx, nxt = next_nonblank(i + 1)
        if (prev_blank and 1 <= len(line.split()) <= 8 and line[0].isupper() and not SENTENCE_END.search(line) and not re.search(r"\d{4}", line) and nxt and len(nxt) > 40
                and not re.match(r"^(by|name|title|date|signed|for and on behalf)\b", line, re.I) and not line.startswith(("|", "-", "*", "(", "["))):
            out.append(f"## {_clean_heading(line)}")
            i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


INLINE_BOLD = re.compile(r"^(\d{1,2})\.\s+\*\*([^*]{3,80}?)\.?\*\*\.?\s*(.*)$")
INLINE_PLAIN = re.compile(r"^(\d{1,2})\.\s+([A-Z][A-Za-z ,&/'\-]{2,60}?)\.\s+([A-Z].{30,})$")


def split_inline_headings(text: str) -> str:
    """Short-form agreements put the heading inside the paragraph ('13. **Termination for Convenience.** Customer may...' or
    '3. Fees. The Customer shall...'): make each of them a '## 13. Termination for Convenience' clause."""
    out = []
    for ln in text.split("\n"):
        m = INLINE_BOLD.match(ln) or INLINE_PLAIN.match(ln)
        if m and len(m.group(2).split()) <= 8:
            out.append(f"## {m.group(1)}. {m.group(2).strip()}")
            if m.group(3).strip():
                out.append(m.group(3).strip())
        else:
            out.append(ln)
    return "\n".join(out)


def load_document(path: Path) -> str:
    """The text of a file as internal Markdown. Raises ValueError with a clear message when it cannot be read."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        text = pdf_to_text(path)
    elif ext == ".docx":
        text = docx_to_text(path)
    elif ext in (".html", ".htm"):
        text = ingest_text.extract_text(path.name, path.read_bytes())
    elif ext in (".md", ".txt"):
        text = path.read_text(errors="replace")
    else:
        raise ValueError(f"unsupported file type {ext}")
    text = re.sub(r"\\\n", "\n", text)                      # pandoc hard line breaks
    text = re.sub(r"^\s*\\([\[\]*_])", r"\1", text, flags=re.M)
    text = split_inline_headings(text)
    has_title = bool(re.search(r"^# \S", text, re.M))
    has_clauses = bool(re.search(r"^##\s+\S", text, re.M))
    if not (has_title and has_clauses):          # already structured (Markdown, Word heading styles): leave alone
        text = structure_text(text)
    return text
