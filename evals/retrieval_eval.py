"""Clause-search quality: for plain-English questions about a clause, is a clause of the expected type among the top 3 hits? Run on a seeded database; compare embedding providers
with EMBEDDING_PROVIDER=hash | fastembed (re-seed between runs: clause vectors are computed at seed time).  Usage: python evals/retrieval_eval.py"""
import sys

from app import ask, embeddings
from app.db import SessionLocal  # noqa: F401

CASES = [
    ("who is allowed to end the contract early without giving a reason", "termination_for_convenience"),
    ("can we walk away from the agreement with a month's notice", "termination_for_convenience"),
    ("what is the most the supplier could owe us if something goes wrong", "liability_cap"),
    ("is the vendor's liability limited to a multiple of fees", "liability_cap"),
    ("who owns the work the supplier creates for us", "ip_ownership"),
    ("which law applies and where are disputes heard", "governing_law"),
    ("what happens to our data when the contract ends", "data_return"),
    ("must the supplier keep our information secret and for how long", "confidentiality"),
    ("can the other side transfer the contract to someone else", "assignment"),
    ("do we have the right to inspect the supplier's records", "audit_rights"),
    ("what insurance must the supplier carry", "insurance"),
    ("how quickly must a security incident be reported", "security"),
    ("how many days do we have to pay an invoice", "payment"),
    ("does the contract renew by itself and how do we stop it", "renewal"),
    ("what service level and credits apply if the system is down", "sla"),
    ("can the supplier use subcontractors to process our personal data", "subprocessors"),
    ("what warranties does the supplier give", "warranties"),
    ("how are changes to the scope agreed", "change_control"),
    ("when can either party terminate because of a breach", "termination_for_cause"),
    ("how long does the agreement last", "term"),
]


def main() -> int:
    ok = 0
    print("provider:", embeddings.provider())
    for q, want in CASES:
        res = ask.execute_tool("search_clauses", {"query": q, "top_k": 3})
        got = [h["clause_type"] for h in res.get("hits", [])]
        good = want in got
        ok += good
        print(f"{'PASS' if good else 'FAIL'} {want:28s} {q[:58]:58s} -> {got}")
    print(f"OVERALL {ok}/{len(CASES)} = {100 * ok / len(CASES):.0f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
