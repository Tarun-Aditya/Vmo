"""make seed -> python /scripts/seed.py [YYYY-MM-DD] [--extractor heuristic|llm|auto]"""

import argparse
from datetime import date

from app import seed

ap = argparse.ArgumentParser()
ap.add_argument("seed_date", nargs="?", help="override 'today' (default: today)")
ap.add_argument("--extractor", default="auto", choices=["auto", "llm", "heuristic"])
a = ap.parse_args()
seed.run(
    date.fromisoformat(a.seed_date) if a.seed_date else None,
    a.extractor,
    "auto" if a.extractor == "auto" else a.extractor,
)
