"""Record what the engine produces for the demo sample documents, for replay in Demo mode (see app/recorded.py).

From backend/, with the hotel environment and Demo mode OFF so Claude reads the documents (if Claude is not reachable the offline engine's results are
recorded and labelled so):  python ../scripts/record_demo.py
It (re)reads the sample folder into the inbox (uploads/samples), keeps the terms extracted from each document, asks every question of
data/realistic_hotel/demo_questions.json about its documents, and writes data/realistic_hotel/recorded.json. Commit that file: the demo then shows these
results in Demo mode, fast and identical every time, without Claude or internet."""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import text  # noqa: E402

from app import ask, llm, pipeline, recorded  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.routes_admin import SAMPLE_DIR, SAMPLES, _sample_folder  # noqa: E402

LABEL = {"llm": "Claude", "heuristic": "offline rules", "heuristic-fallback": "offline rules (Claude unavailable)"}


def main() -> int:
    engine = llm.PROVIDER_LABEL.get(llm.provider(), "Claude") if llm.available() else "offline rules"
    if not llm.available():
        print("Claude is not available (Demo mode on, no API key or Claude login): recording the offline engine's results. Turn Demo mode off and configure "
              "Claude, then run this again to record Claude's.")
    recorded.start_capture()
    with SessionLocal() as s:
        d = pipeline.inbox_path(s) / SAMPLE_DIR
    d.mkdir(parents=True, exist_ok=True)
    files = []
    for x in _sample_folder():
        f = d / x["file"]                                   # the originals only (the duplicate copy has nothing of its own to record)
        if x.get("duplicate"):
            continue
        shutil.copy2(SAMPLES / "docs" / x["file"], f)
        f.with_suffix(".meta.json").write_text(json.dumps({"category": x.get("category"), "owner": "Andrea Whitfield", "origin": "upload",
                                                           **({"property": x["property"]} if x.get("property") else {})}))
        files.append(f)
    print(f"reading {len(files)} documents with {engine} ...")
    r = pipeline.run_pipeline("record", only=files, force=True)
    if r.get("status") == "busy":
        print("another pipeline run is in progress; try again in a moment")
        return 1
    docs = {h: {**v, "engine": LABEL.get(v["engine"], v["engine"])} for h, v in recorded.captured().items()}
    fp = {x["file"]: hashlib.sha256((SAMPLES / "docs" / x["file"]).read_bytes()).hexdigest() for x in _sample_folder() if not x.get("duplicate")}
    qs = json.loads((SAMPLES / "demo_questions.json").read_text())
    answers = {}
    with SessionLocal() as s:
        by_hash = {r_[1]: r_[0] for r_ in s.execute(text("SELECT id, content_hash FROM contracts WHERE content_hash = ANY(:h)"), {"h": list(fp.values())})}
        for q in qs["questions"]:
            names = qs["groups"][q["documents"]] if isinstance(q["documents"], str) else q["documents"]
            hashes = [fp[n] for n in names]
            ids = [by_hash[h] for h in hashes if h in by_hash]
            if len(ids) != len(hashes):
                print(f"  skip {q['question']!r}: not every document was read")
                continue
            res = ask.answer(q["question"], scope=ids)
            res.pop("elapsed_ms", None)
            answers[recorded.key(q["question"], hashes)] = {"question": q["question"], "documents": names,
                                                             "engine": "Claude" if res.get("source") in ("llm", "claude-subscription") else "offline engine",
                                                             "response": recorded.to_portable(s, res, ids)}
            print(f"  {q['question']} ({len(ids)} documents): {res.get('answer', '')[:70]}")
    out = {"about": "Recorded by scripts/record_demo.py; replayed in Demo mode for the sample documents (app/recorded.py).", "engine": engine,
           "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "documents": docs, "answers": answers}
    recorded.PATH.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote {recorded.PATH}: {len(docs)} documents, {len(answers)} answers, engine {engine}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
