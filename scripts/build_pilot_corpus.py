"""One-off: have Claude write each pilot contract from its spec (backend/app/docgen/pilot_spec.py) into corpus/pilot/<key>.md.
Needs a Claude provider (subscription CLI or API key). Re-run with --only key1,key2 or --force to rewrite. Facts are validated programmatically."""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import llm  # noqa: E402
from app.config import settings  # noqa: E402
from app.docgen import pilot  # noqa: E402
from app.docgen.pilot_spec import DOCS  # noqa: E402


def write(spec: dict, force: bool) -> str:
    out = pilot.CORPUS_DIR / f"{spec['key']}.md"
    if out.exists() and not force:
        return f"{spec['key']}: exists"
    system, user = pilot.prompt(spec)
    problems: list[str] = []
    for attempt in range(3):
        extra = "" if not problems else "\n\nYOUR PREVIOUS ATTEMPT HAD THESE PROBLEMS, FIX THEM: " + "; ".join(problems)
        md = llm.complete("corpus", settings.model_extract, system, user + extra)
        md = md.removeprefix("```markdown").removeprefix("```").removesuffix("```").strip()
        problems = pilot.validate(spec, md)
        if not problems:
            break
    pilot.CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(md + "\n")
    return f"{spec['key']}: {len(md.split())} words" + (f"  (UNRESOLVED: {problems})" if problems else "")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default="pilot", help="pilot (IT services) or hotel")
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    pilot.use_pack(a.pack)
    specs = [d for d in pilot.DOCS if not a.only or d["key"] in a.only.split(",")]
    print("provider:", llm.provider())
    with ThreadPoolExecutor(a.workers) as ex:
        for line in ex.map(lambda s: write(s, a.force), specs):
            print(line, flush=True)
