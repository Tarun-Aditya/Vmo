"""Configurable libraries: clause identification, value extraction and the checklist engine."""
from app import kcc

K = kcc.default_kcc()
M = kcc.default_metrics()
R = {r["key"]: r for r in kcc.default_rules()}


def clause(ctype, text, page=1, cid=None):
    return {"id": cid, "clause_type": ctype, "heading": ctype, "text": text, "page": page}


def test_defaults_cover_the_clause_library():
    assert len(K) == 39 and sum(k["in_matrix"] for k in K) == 23 and len(M) == 16 and len(R) == 34
    assert all(k["heading_aliases"] for k in K)


def test_classify_by_heading_alias_then_keywords():
    assert kcc.classify("Fees and Payment", "anything", K) == "payment"          # alias
    assert kcc.classify("Limitation of Liability", "x", K) == "liability_cap"      # exact heading
    assert kcc.classify("Our caps", "Each party's aggregate liability shall not exceed 2 times fees", K) == "liability_cap"  # keywords
    assert kcc.classify("Miscellaneous", "Nothing relevant here.", K) == "other"


def test_a_custom_clause_is_identified_by_its_keywords():
    mfc = dict(key="mfc", name="Most Favoured Customer", keywords=["most favou?red customer", "price parity"], heading_aliases=["MFC"], sort_order=99)
    assert kcc.classify("Pricing protection", "The Supplier grants Most Favoured Customer pricing.", K + [mfc]) == "mfc"
    assert kcc.classify("MFC", "x", K + [mfc]) == "mfc"


def test_extract_metrics_converts_units_and_picks_the_right_clause():
    cl = [clause("security", "notify within 7 days of becoming aware", cid=1), clause("breach_notification", "within 48 hours", cid=2),
          clause("payment", "pay within 45 days", cid=3), clause("insurance", "at least USD 5,000,000 per claim", cid=4),
          clause("governing_law", "governed by the laws of New York. The courts", cid=5)]
    v = {x["metric_key"]: x for x in kcc.extract_metrics(cl, M)}
    assert v["incident_notice_hours"]["value_num"] == 168 and v["breach_notice_hours"]["value_num"] == 48   # days -> hours
    assert v["payment_terms_days"]["value_num"] == 45 and v["insurance_cover_usd"]["value_num"] == 5_000_000
    assert v["governing_law_text"]["value_text"] == "New York" and v["insurance_cover_usd"]["clause_id"] == 4


def run(rules, doc_type, clauses, status="draft", executed=False):
    vals = kcc.extract_metrics(clauses, M)
    return {r["rule_key"]: r for r in kcc.evaluate_rules(doc_type, status, clauses, vals, M, [R[k] for k in rules], executed)}


def test_threshold_rules_pass_fail_and_na():
    res = run(["payment_terms_min", "payment_terms_target", "warranty_min"], "MSA", [clause("payment", "pay within 30 days")])
    assert res["payment_terms_min"]["status"] == "pass" and res["payment_terms_target"]["status"] == "fail"
    assert res["payment_terms_target"]["actual"] == "30 days" and res["payment_terms_target"]["expected"] == "≥ 45 days"
    assert res["warranty_min"]["status"] == "na"                                  # no warranty value in the document
    assert run(["payment_terms_min"], "NDA", [clause("payment", "pay within 5 days")]) == {}   # rule does not apply to NDAs


def test_required_forbidden_and_text_rules():
    cl = [clause("liability_cap", "Each party's liability under this Agreement is unlimited.", page=4)]
    res = run(["liability_cap_required", "no_unlimited_liability", "indemnity_required"], "MSA", cl)
    assert res["liability_cap_required"]["status"] == "pass" and res["indemnity_required"]["status"] == "fail"
    assert res["no_unlimited_liability"]["status"] == "fail" and res["no_unlimited_liability"]["page"] == 4
    assert res["no_unlimited_liability"]["severity"] == "critical"


def test_stage_rules_and_signature():
    assert "executed" not in run(["executed"], "MSA", [clause("execution", "pending")], status="draft")       # post-sign only
    assert run(["executed"], "MSA", [clause("execution", "x")], status="active", executed=True)["executed"]["status"] == "pass"
    assert run(["executed"], "MSA", [clause("execution", "x")], status="active", executed=False)["executed"]["status"] == "fail"
