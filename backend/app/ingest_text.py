"""Turn an uploaded file (.docx, .md, .txt, .json, .csv, .html) into plain text / Markdown, stdlib only."""
from __future__ import annotations

import html as _html
import io
import re
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SUPPORTED_UPLOADS = (".md", ".txt", ".json", ".csv", ".docx", ".html", ".htm")


def _docx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    out: list[str] = []
    for p in root.iter(f"{W}p"):
        style = p.find(f"{W}pPr/{W}pStyle")
        st = (style.get(f"{W}val") if style is not None else "") or ""
        txt = "".join(t.text or "" for t in p.iter(f"{W}t")).strip()
        if not txt:
            out.append("")
        elif st.lower().startswith("title"):
            out.append(f"# {txt}")
        elif st.lower().startswith("heading"):
            out.append(f"## {txt}")
        else:
            out.append(txt)
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(x for x in out)).strip() + "\n"


def _html_to_md(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    raw = re.sub(r"(?is)<h1[^>]*>(.*?)</h1>", r"\n# \1\n", raw)
    raw = re.sub(r"(?is)<h[2-6][^>]*>(.*?)</h[2-6]>", r"\n## \1\n", raw)
    raw = re.sub(r"(?i)</(p|div|li|tr)>|<br\s*/?>", "\n", raw)
    return re.sub(r"\n{3,}", "\n\n", _html.unescape(re.sub(r"<[^>]+>", "", raw))).strip() + "\n"


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".docx"):
        try:
            return _docx(data)
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
            raise ValueError(f"could not read the Word file: {e}") from e
    if name.endswith((".html", ".htm")):
        return _html_to_md(data.decode("utf-8", "replace"))
    if name.endswith((".md", ".txt", ".json", ".csv")) or "." not in name:
        return data.decode("utf-8", "replace")
    raise ValueError(f"unsupported file type; use one of {', '.join(SUPPORTED_UPLOADS)} (PDF/OCR is a later version)")
