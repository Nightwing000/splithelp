import pytest

from retrieval import retrieve, retrieve_context


def test_retrieve_returns_payment_context_for_paid_question():
    result = retrieve("How much did each payer pay in a group?", top_k=5)
    result_ids = [item["id"] for item in result]

    assert "expense_payments" in result_ids
    assert "group_payment_totals" in result_ids


def test_retrieve_returns_member_example_for_membership_question():
    result = retrieve("Who belongs to this group?", top_k=5)
    result_ids = [item["id"] for item in result]

    assert "list_group_members" in result_ids


def test_retrieve_returns_balance_example_for_settlement_question():
    result = retrieve("Show the net balance for each person", top_k=5)
    result_ids = [item["id"] for item in result]

    assert "group_net_balances" in result_ids


def test_retrieve_returns_balance_rules_for_owing_question():
    result = retrieve("Who owes money in the group?", top_k=5)
    result_ids = [item["id"] for item in result]

    assert "net_balance_calculation" in result_ids
    assert "negative_balance" in result_ids
    assert "group_scoped_balances" in result_ids


def test_retrieve_excludes_items_with_no_matching_keywords():
    result = retrieve("What is the weather today?")

    assert result == []


def test_retrieve_respects_top_k_and_preserves_tie_order():
    items = [
        {
            "id": "first",
            "kind": "schema",
            "content": "First item",
            "keywords": ["shared"],
        },
        {
            "id": "second",
            "kind": "rule",
            "content": "Second item",
            "keywords": ["shared"],
        },
    ]

    result = retrieve("shared", items=items, top_k=1)

    assert [item["id"] for item in result] == ["first"]


def test_retrieve_rejects_negative_top_k():
    with pytest.raises(ValueError, match="top_k"):
        retrieve("users", top_k=-1)


def test_retrieve_can_filter_by_kind():
    result = retrieve("How much did each payer pay?", kind="example")

    assert result
    assert all(item["kind"] == "example" for item in result)


def test_retrieve_context_preserves_each_kind_budget():
    result = retrieve_context(
        "Who owes money in the group?",
        schema_limit=1,
        rule_limit=2,
        example_limit=1,
    )

    counts = {
        kind: sum(item["kind"] == kind for item in result)
        for kind in ("schema", "rule", "example")
    }

    assert counts == {"schema": 1, "rule": 2, "example": 1}


def test_retrieve_context_rejects_negative_limits():
    with pytest.raises(ValueError, match="limits"):
        retrieve_context("users", schema_limit=-1)
