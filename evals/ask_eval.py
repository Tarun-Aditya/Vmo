"""Run the 15 demo questions through the Ask assistant and score against ground truth."""

import sys
from pathlib import Path

import yaml

import ground_truth as gt
from app import ask

PASS_MARK = 15


def sql_outputs(calls):
    return [c["output"] for c in calls if c["name"] == "run_sql" and "rows" in c["output"]]


def values(calls, column):
    """Values of `column` from the first run_sql result that has it."""
    for out in sql_outputs(calls):
        if column in out["columns"]:
            i = out["columns"].index(column)
            return [r[i] for r in out["rows"]], out
    return None


def best_set(calls, column, want):
    """The set the answer gave. Claude names columns freely, so: the named column when present, otherwise the column of
    any result whose values overlap the expected set most (what matters is the content, not the alias)."""
    v = values(calls, column)
    if v:
        return set(v[0])
    best, score = set(), -1.0
    for out in sql_outputs(calls):
        for i in range(len(out["columns"])):
            col = {r[i] for r in out["rows"] if isinstance(r[i], str)}
            if col:
                j = len(col & want) / len(col | want)
                if j > score:
                    best, score = col, j
    return best


def check(q, res):
    spec, calls = q["check"], res["tool_calls"]
    if spec["kind"] == "all":
        results = [check({**q, "check": sub}, res) for sub in spec["checks"]]
        return all(r[0] for r in results), " | ".join(r[1] for r in results if not r[0])
    want = getattr(gt, spec["expected"])()
    cited = {c["title"] for c in res["citations"]}
    kind = spec["kind"]
    if kind == "set":
        got = best_set(calls, spec["column"], want)
        return got == want, f"got {sorted(got)} want {sorted(want)}"
    if kind == "number":
        nums = [float(x) for o in sql_outputs(calls) for r in o["rows"] for x in r if isinstance(x, (int, float)) and not isinstance(x, bool)]
        ok = any(abs(n - float(want)) <= 0.01 * max(float(want), 1) for n in nums)
        return ok, f"want {want}, numbers returned {sorted(set(nums))[:12]}"
    if kind == "rowcount":
        got = [len(o["rows"]) for o in sql_outputs(calls)]
        return want in got, f"got {got} rows want {want}"
    if kind == "dict":
        want = {k: v for k, v in want.items() if v}
        seen = []
        for o in sql_outputs(calls):
            for ki, kc in enumerate(o["columns"]):
                for vi, vc in enumerate(o["columns"]):
                    if ki == vi:
                        continue
                    try:
                        got = {r[ki]: float(r[vi] or 0) for r in o["rows"] if isinstance(r[ki], str)}
                    except (TypeError, ValueError):
                        continue
                    got = {k: v for k, v in got.items() if v}
                    seen.append(got)
                    if got.keys() == want.keys() and all(abs(got[k] - want[k]) <= 0.01 * want[k] for k in want):
                        return True, ""
        return False, f"want {want}; closest {max(seen, key=lambda g: len(g.keys() & want.keys()), default={})}"
    if kind == "cited":
        top = {
            h["title"]
            for c in calls
            if c["name"] == "search_clauses"
            for h in c["output"]["hits"][:2]
        }
        return want <= top, f"top-2 cited {sorted(top)} want {sorted(want)}"
    if kind == "set_and_cited":
        got = best_set(calls, spec["column"], want)
        return (
            got == want and want <= cited,
            f"sql {sorted(got)} cited {sorted(cited)} want {sorted(want)}",
        )
    return False, "unknown check"


def main() -> int:
    qs = yaml.safe_load((Path(__file__).parent / "questions.yaml").read_text())
    ok = 0
    for q in qs:
        try:
            res = ask.answer(q["question"], demo_mode=False)
            good, detail = check(q, res)
        except Exception as e:
            res, good, detail = {"source": "error"}, False, f"{type(e).__name__}: {e}"
        ok += good
        print(
            f"{'PASS' if good else 'FAIL'} [{res['source']:8s}] {q['id']:22s} {'' if good else detail}"
        )
    print(f"{ok}/{len(qs)} correct")
    return 0 if ok == len(qs) else 1


if __name__ == "__main__":
    sys.exit(main())
