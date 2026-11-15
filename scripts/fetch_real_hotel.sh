#!/bin/sh
# Download the real, public-record hotel-world contracts listed in data/real_hotel/sources.json into data/real_hotel/docs (not committed: they belong to the
# public bodies that published them). A link that has moved is reported and skipped; the eval scores whatever was fetched.
set -u
cd "$(dirname "$0")/.." || exit 1
mkdir -p data/real_hotel/docs
python3 - <<'PY'
import json, subprocess, pathlib
root = pathlib.Path("data/real_hotel")
for d in json.loads((root / "sources.json").read_text()):
    out = root / "docs" / d["file"]
    if out.exists() and out.stat().st_size > 2000:
        print("have   ", d["file"]); continue
    subprocess.run(["curl", "-s", "-L", "-m", "90", "-A", "Mozilla/5.0 (contract-research)", "-o", str(out), d["url"]])
    ok = out.exists() and out.read_bytes()[:4] == b"%PDF"
    print("fetched" if ok else "FAILED ", d["file"])
    if not ok and out.exists():
        out.unlink()
PY
