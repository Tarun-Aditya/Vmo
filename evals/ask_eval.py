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


def check(q, res):
    spec, calls = q["check"], res["tool_calls"]
    if spec["kind"] == "all":
        results = [check({**q, "check": sub}, res) for sub in spec["checks"]]
        return all(r[0] for r in results), " | ".join(r[1] for r in results if not r[0])
    want = getattr(gt, spec["expected"])()
    cited = {c["title"] for c in res["citations"]}
    kind = spec["kind"]
    if kind == "set":
        v = values(calls, spec["column"])
        got = set(v[0]) if v else None
        return got == want, f"got {sorted(got or [])} want {sorted(want)}"
    if kind == "number":
        v = values(calls, spec["column"])
        got = v[0][0] if v else None
        return (
            got is not None and abs(float(got) - float(want)) <= 0.01 * float(want),
            f"got {got} want {want}",
        )
    if kind == "dict":
        sql = next(
            o
            for o in sql_outputs(calls)
            if spec["key"] in o["columns"] and spec["value"] in o["columns"]
        )
        ki, vi = sql["columns"].index(spec["key"]), sql["columns"].index(spec["value"])
        got = {r[ki]: float(r[vi] or 0) for r in sql["rows"]}
        want = {k: v for k, v in want.items() if v}
        got = {k: v for k, v in got.items() if v}
        ok = got.keys() == want.keys() and all(
            abs(got[k] - want[k]) <= 0.01 * want[k] for k in want
        )
        return ok, f"got {got} want {want}"
    if kind == "cited":
        top = {
            h["title"]
            for c in calls
            if c["name"] == "search_clauses"
            for h in c["output"]["hits"][:2]
        }
        return want <= top, f"top-2 cited {sorted(top)} want {sorted(want)}"
    if kind == "set_and_cited":
        v = values(calls, spec["column"])
        got = set(v[0]) if v else set()
        return (
            got == want and want <= cited,
            f"sql {sorted(got)} cited {sorted(cited)} want {sorted(want)}",
        )
    return False, "unknown check"


def main() -> int:
    qs = yaml.safe_load((Path(__file__).parent / "questions.yaml").read_text())
    ok = 0
    for q in qs:
        res = ask.answer(q["question"], demo_mode=False)
        good, detail = check(q, res)
        ok += good
        print(
            f"{'PASS' if good else 'FAIL'} [{res['source']:8s}] {q['id']:22s} {'' if good else detail}"
        )
    print(f"{ok}/{len(qs)} correct")
    return 0 if ok == len(qs) else 1


if __name__ == "__main__":
    sys.exit(main())
