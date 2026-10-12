
from decimal import Decimal

from netting import Transaction, simplify_debts


def test_already_settled_group():
    balances = {
        1: Decimal("0"),
        2: Decimal("0"),
        3: Decimal("0"),
    }

    result = simplify_debts(balances)

    assert result == []


def test_two_person_settle():
    balances = {
        1: Decimal("50"),
        2: Decimal("-50"),
    }

    result = simplify_debts(balances)

    assert result == [
        Transaction(
            payer_id=2,
            payee_id=1,
            amount=Decimal("50"),
        )
    ]


def test_four_person_worked_example():
    balances = {
        1: Decimal("40"),   # A
        2: Decimal("10"),   # B
        3: Decimal("-30"),  # C
        4: Decimal("-20"),  # D
    }

    result = simplify_debts(balances)

    assert result == [
        Transaction(3, 1, Decimal("30")),
        Transaction(4, 1, Decimal("10")),
        Transaction(4, 2, Decimal("10")),
    ]


def test_exact_tie_zeroes_both_sides_same_step():
    balances = {
        1: Decimal("15"),
        2: Decimal("-15"),
    }

    result = simplify_debts(balances)

    assert result == [
        Transaction(
            payer_id=2,
            payee_id=1,
            amount=Decimal("15"),
        )
    ]

