"""Add the five realistic hotel contracts (data/realistic_hotel/docs) to a running hotel demo: they are copied into the inbox (uploads/intake, as the Intake screen does) with
their category and property, and the pipeline reads them as it reads any uploaded contract (Claude when available, else the offline rules).

From backend/ with the hotel environment:  python ../scripts/load_realistic_hotel.py
They are not part of `seed --hotel` (the demo's walkthrough and Ask evals count the seeded portfolio); a re-seed removes them again."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import pipeline
from app.db import SessionLocal

SRC = Path(__file__).resolve().parents[1] / "data" / "realistic_hotel"
OWNER = "Andrea Whitfield"      # the procurement signatory in the documents

with SessionLocal() as s:
    dest = pipeline.inbox_path(s) / "uploads" / "intake"      # the Intake screen's folder, so its reset removes them too
dest.mkdir(parents=True, exist_ok=True)
files = []
for d in json.loads((SRC / "sources.json").read_text()):
    f = dest / d["file"]
    shutil.copy2(SRC / "docs" / d["file"], f)
    meta = {"category": d["category"], "owner": OWNER, "origin": "upload"}
    if d.get("property"):
        meta["property"] = d["property"]
    f.with_suffix(".meta.json").write_text(json.dumps(meta))
    files.append(f)
r = pipeline.run_pipeline("manual", only=files, force=True)
print(json.dumps({k: r.get(k) for k in ("status", "scanned", "new_docs", "updated", "failed", "seconds")}))
