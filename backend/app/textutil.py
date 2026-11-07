"""Text normalisation shared by the offline extractors: number words, '(30)' duplicates, money, many date formats."""
from __future__ import annotations

import re
from datetime import date

UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
         "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_WORD = r"(?:%s)" % "|".join(sorted(UNITS, key=len, reverse=True))
NUM_PHRASE = re.compile(rf"\b({_WORD})(?:[- ](one|two|three|four|five|six|seven|eight|nine))?\b", re.I)
PAREN_DUP = re.compile(rf"\b(?:{_WORD}(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|hundred)\s*\(\s*(\d+(?:\.\d+)?)\s*\)", re.I)
UNIT_AFTER = r"(?=\s*(?:days?|months?|years?|hours?|business days|weeks?|times|percent|%))"
MONTHS = {m: i for i, m in enumerate("january february march april may june july august september october november december".split(), 1)}
MONTH_RE = "(" + "|".join(list(MONTHS) + [m[:3] for m in MONTHS]) + ")"
DATE_PATTERNS = [
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH_RE}\.?,?\s+(\d{{4}})\b", re.I), "dmy"),
    (re.compile(rf"\b{MONTH_RE}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I), "mdy"),
    (re.compile(rf"\b(\d{{1,2}})\s*(?:[a-z]\s*[a-z])?\s+day\s+of\s+{MONTH_RE}\.?,?\s+(\d{{4}})\b", re.I), "dmy"),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "us"),
]


def normalize(text: str) -> str:
    """'forty-five (45) days' -> '45 days'; 'thirty days' -> '30 days'; keeps everything else."""
    t = PAREN_DUP.sub(lambda m: m.group(1), text)

    def words(m: re.Match) -> str:
        v = UNITS[m.group(1).lower()] + (UNITS[m.group(2).lower()] if m.group(2) else 0)
        return str(v)

    t = re.sub(rf"\b({_WORD})(?:[- ](one|two|three|four|five|six|seven|eight|nine))?\b{UNIT_AFTER}", words, t, flags=re.I)
    t = re.sub(r"\bUS\$|\bUSD\s*\$?|\$\s*(?=\d)", "USD ", t)
    t = re.sub(r"\bUSD\s+USD\b", "USD", t)
    return re.sub(r"[ \t]{2,}", " ", t)


def to_date(m: re.Match, kind: str) -> date | None:
    g = m.groups()
    try:
        if kind == "dmy":
            return date(int(g[2]), MONTHS[_mon(g[1])], int(g[0]))
        if kind == "mdy":
            return date(int(g[2]), MONTHS[_mon(g[0])], int(g[1]))
        if kind == "iso":
            return date(int(g[0]), int(g[1]), int(g[2]))
        if kind == "us":
            return date(int(g[2]), int(g[0]), int(g[1]))
    except (ValueError, KeyError):
        return None
    return None


def _mon(s: str) -> str:
    s = s.lower().rstrip(".")
    return next(k for k in MONTHS if k.startswith(s[:3]))


def find_dates(text: str) -> list[tuple[int, date]]:
    out = []
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            d = to_date(m, kind)
            if d:
                out.append((m.start(), d))
    return sorted(out)


def first_date(text: str) -> date | None:
    ds = find_dates(text)
    return ds[0][1] if ds else None


def money(text: str) -> float | None:
    m = re.search(r"USD\s*([\d,]+(?:\.\d+)?)\s*(million|m\b|thousand|k\b)?", text, re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    mult = (m.group(2) or "").lower()
    return v * (1e6 if mult.startswith("m") else 1e3 if mult.startswith(("t", "k")) else 1)
