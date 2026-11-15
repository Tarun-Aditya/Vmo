"""Read REAL hotel-world contracts (public records: a hotel management agreement, housekeeping at hotels, linen and laundry, elevator maintenance, pest control,
hotel lodging and shared-technology agreements) and score what the engine reads against labels made by reading each document.

The documents are not in the repository (they belong to the public bodies that published them): `sh scripts/fetch_real_hotel.sh` downloads them into data/real_hotel/docs.
Labels: data/real_hotel/labels.json  {file: {field: value}}; a field that is absent from a document's labels was not labelled and is not scored.

Usage (from backend/):  python ../evals/real_hotel_eval.py [--dump out.json]
       REAL_SET=realistic_hotel python ../evals/real_hotel_eval.py   (five fictional contracts written to read like real ones: data/realistic_hotel)
  LLM_PROVIDER=offline for the rules alone; unset for Claude (subscription CLI or API key)."""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / os.environ.get("REAL_SET", "real_hotel")      # REAL_SET=realistic_hotel: the realistic fictional set in the repository
MANIFEST = json.loads((ROOT / "sources.json").read_text())
# the buyer in each document is a public body; the other party is the supplier
os.environ["CUSTOMER_NAMES"] = ",".join(sorted({m for d in MANIFEST for m in d["customer_markers"]}))

from app import docstruct, extraction, kcc, llm, meta_rules, pipeline
from app.parsing import parse_document

FIELDS = ["vendor", "governing_law", "effective_date", "expiry_date", "auto_renew", "notice_period_days", "termination_for_convenience", "payment_terms_days", "liability_cap_multiple",
          "annual_value", "total_value", "processes_personal_data"]


def same(field: str, got, want) -> bool:
    if want is None:
        return got in (None, "", False) if field in ("auto_renew",) else got in (None, "")
    if got in (None, ""):
        return False
    if field == "vendor":
        n = lambda s: re.sub(r"[^a-z0-9]+", " ", re.sub(r"\b(inc|llc|corp|corporation|company|co|ltd|lp|l p)\b\.?", "", str(s).lower())).strip()
        return n(want) in n(got) or n(got) in n(want)
    if field == "governing_law":
        return str(want).lower() in str(got).lower()
    kind = pipeline.EDITABLE.get(field)
    try:
        if kind in ("num", "int"):
            return abs(float(got) - float(want)) <= 0.01 * max(abs(float(want)), 1)
        if kind == "bool":
            return pipeline.coerce_input(field, got) == pipeline.coerce_input(field, want)
        if kind == "date":
            return str(got)[:10] == str(want)[:10]
    except (ValueError, TypeError):
        return False
    return str(got).strip().lower() == str(want).strip().lower()


def read(path: Path, doc_type: str) -> dict:
    md = docstruct.load_document(path)
    with pipeline.SessionLocal() as s:
        cfg_kcc = kcc.load_kcc(s)
    header, clauses = parse_document(md, lambda h, t: kcc.classify(h, t, cfg_kcc))
    out, mode = extraction.extract(md, header, clauses, doc_type)
    got = {f: (out.get(f) or {}).get("value") for f in FIELDS if f != "vendor"}
    got["vendor"] = meta_rules.choose_vendor(meta_rules.find_vendor(md, header, {}), (out.get("supplier_name") or {}).get("value"), md)
    got["_mode"], got["_clauses"], got["_chars"] = mode, len(clauses), len(md)
    return got


def main() -> int:
    labels = json.loads((ROOT / "labels.json").read_text()) if (ROOT / "labels.json").exists() else {}
    dump = sys.argv[sys.argv.index("--dump") + 1] if "--dump" in sys.argv else None
    per_field: dict[str, list[int]] = {f: [0, 0] for f in FIELDS}
    rows, miss = {}, []
    for d in MANIFEST:
        f = ROOT / "docs" / d["file"]
        if not f.exists():
            print(f"  skip {d['file']}: not downloaded (sh scripts/fetch_real_hotel.sh)")
            continue
        try:
            got = read(f, d.get("type", "MSA"))
        except Exception as e:  # a document the engine cannot open counts against it
            got = {"_error": f"{type(e).__name__}: {e}"}
        rows[d["file"]] = got
        for field, want in (labels.get(d["file"]) or {}).items():
            if field not in per_field:
                continue
            ok = same(field, got.get(field), want)
            per_field[field][0] += ok
            per_field[field][1] += 1
            if not ok:
                miss.append((d["file"], field, got.get(field), want))
    if dump:
        Path(dump).write_text(json.dumps(rows, indent=1, default=str))
    print(f"engine: {'Claude (' + llm.provider() + ')' if llm.available() else 'offline rules'}   documents read: {len(rows)}   could not be opened: {sum(1 for r in rows.values() if '_error' in r)}")
    for field, (ok, n) in per_field.items():
        if n:
            print(f"  {field:28s} {ok:2d}/{n:2d}  {100 * ok / n:5.1f}%")
    for m in miss:
        print("  MISS", m)
    ok, n = sum(v[0] for v in per_field.values()), sum(v[1] for v in per_field.values())
    print(f"OVERALL {ok}/{n} = {100 * ok / max(n, 1):.1f}% of labelled fields")
    return 0


if __name__ == "__main__":
    sys.exit(main())
