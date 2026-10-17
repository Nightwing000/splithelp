from rag_evaluation import evaluate_retrieval


def test_retrieval_evaluation_cases_have_expected_context():
    reports = evaluate_retrieval()

    assert reports
    assert all(report["passed"] for report in reports)
