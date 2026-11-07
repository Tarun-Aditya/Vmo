"""Score the extraction engine on REAL contracts you have labels for.
Labels come from people correcting extractions (Admin -> Extraction quality, or /api/quality/labels): {source_path: {field: correct value}}.
Each labelled document is re-read from the inbox with the engine as it is now (corrections are NOT applied), so you can change rules or the model and see the effect.
Usage: python evals/real_eval.py [labels.json]   (LLM_PROVIDER=offline for rules only; unset for Claude)"""
import json
import re
import sys
from pathlib import Path

from sqlalchemy import text

from app import docstruct, extraction, kcc, pipeline
from app.db import SessionLocal
from app.parsing import parse_document


def same(field: str, got, want) -> bool:
    if want in (None, "") and got in (None, ""):
        return True
    if got in (None, "") or want in (None, ""):
        return False
    kind = pipeline.EDITABLE.get(field)
    try:
        if kind in ("num", "int"):
            return abs(float(str(got).replace(",", "")) - float(str(want).replace(",", ""))) <= 0.01 * max(abs(float(str(want).replace(",", ""))), 1)
        if kind == "bool":
            return pipeline.coerce_input(field, got) == pipeline.coerce_input(field, want)
        if kind == "date":
            return str(got)[:10] == str(want)[:10]
    except (ValueError, TypeError):
        return False
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()  # noqa: E731
    return norm(got) == norm(want)


def main() -> int:
    labels = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else None
    with SessionLocal() as s:
        if labels is None:
            labels = {}
            for r in s.execute(text("SELECT source_path, field, corrected_value FROM field_corrections")):
                labels.setdefault(r[0], {})[r[1]] = r[2]
        root = pipeline.inbox_path(s)
        types = {r[0]: r[1] for r in s.execute(text("SELECT source_path, type FROM contracts"))}
    if not labels:
        print("no labels: correct some extractions first")
        return 1
    ok = tot = 0
    bad = []
    for path, want in labels.items():
        f = root / path
        if not f.exists():
            print(f"  skip {path}: file not found")
            continue
        md = docstruct.load_document(f)
        header, clauses = parse_document(md, lambda h, t: kcc.classify(h, t, []))
        out, mode = extraction.extract(md, header, clauses, types.get(path, "MSA"))
        for field, v in want.items():
            tot += 1
            good = same(field, (out.get(field) or {}).get("value"), v)
            ok += good
            if not good:
                bad.append((path, field, (out.get(field) or {}).get("value"), v))
    for b in bad[:30]:
        print("  MISS", b)
    print(f"OVERALL {ok}/{tot} = {100 * ok / max(tot, 1):.1f}% over {len(labels)} labelled documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
