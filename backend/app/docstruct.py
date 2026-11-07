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
    return "\n".join(f"<!-- page: {i} -->\n{p}" for i, p in enumerate(pages, 1))


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
        if 3 <= len(letters) and line.upper() == line and len(line) <= 70 and not SENTENCE_END.search(line) and not re.search(r"\d{4}", line) and len(line.split()) <= 9:
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
    has_title = bool(re.search(r"^# \S", text, re.M))
    has_clauses = bool(re.search(r"^##\s+\S", text, re.M))
    if not (has_title and has_clauses):          # already structured (Markdown, Word heading styles): leave alone
        text = structure_text(text)
    return text
