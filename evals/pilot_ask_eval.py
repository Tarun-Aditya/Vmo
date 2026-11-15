"""Ask assistant over the pilot corpus (or the hotel corpus: QUESTIONS=questions_hotel.yaml LABELS=labels_hotel.json), scored against the spec labels. Run in either engine: LLM_PROVIDER=offline | (unset = Claude)."""
import sys
from pathlib import Path

import pilot_gt
import yaml

sys.modules["ground_truth"] = pilot_gt          # ask_eval.check() reads expectations from `ground_truth`
import ask_eval  # noqa: E402

from app import ask  # noqa: E402


def main() -> int:
    import os

    qs = yaml.safe_load((Path(__file__).parent / os.environ.get("QUESTIONS", "questions_pilot.yaml")).read_text())      # QUESTIONS=questions_hotel.yaml LABELS=labels_hotel.json
    ok = 0
    for q in qs:
        try:
            res = ask.answer(q["question"], demo_mode=False)
            good, detail = ask_eval.check(q, res)
        except Exception as e:
            res, good, detail = {"source": "error"}, False, f"{type(e).__name__}: {e}"
        ok += good
        print(f"{'PASS' if good else 'FAIL'} [{res['source']:8s}] {q['id']:16s} {'' if good else detail}")
    print(f"{ok}/{len(qs)} correct")
    return 0 if ok == len(qs) else 1


if __name__ == "__main__":
    sys.exit(main())
