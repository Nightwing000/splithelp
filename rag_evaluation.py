from __future__ import annotations

from dataclasses import dataclass

from retrieval import retrieve_context_scored


@dataclass(frozen=True)
class RetrievalCase:
    question: str
    expected_ids: frozenset[str]


EVALUATION_CASES = [
    RetrievalCase(
        question="List all active users",
        expected_ids=frozenset({"users", "active_users", "list_active_users"}),
    ),
    RetrievalCase(
        question="Who belongs to group 1?",
        expected_ids=frozenset({"groups", "group_members", "list_group_members"}),
    ),
    RetrievalCase(
        question="How much did each person pay in group 1?",
        expected_ids=frozenset(
            {"expense_payments", "expenses", "group_payment_totals"}
        ),
    ),
    RetrievalCase(
        question="Who owes money in group 1?",
        expected_ids=frozenset(
            {
                "expense_splits",
                "net_balance_calculation",
                "negative_balance",
                "group_scoped_balances",
                "group_net_balances",
            }
        ),
    ),
    RetrievalCase(
        question="What is the weather today?",
        expected_ids=frozenset(),
    ),
]


def evaluate_retrieval() -> list[dict[str, object]]:
    reports = []
    for case in EVALUATION_CASES:
        matches = retrieve_context_scored(case.question)
        retrieved_ids = {match.item["id"] for match in matches}
        reports.append(
            {
                "question": case.question,
                "retrieved_ids": retrieved_ids,
                "scores": {
                    match.item["id"]: match.score for match in matches
                },
                "matched_keywords": {
                    match.item["id"]: sorted(match.matched_keywords)
                    for match in matches
                },
                "missing_ids": case.expected_ids - retrieved_ids,
                "unexpected_ids": retrieved_ids - case.expected_ids,
                "passed": case.expected_ids <= retrieved_ids,
            }
        )
    return reports
