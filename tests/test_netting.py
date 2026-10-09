from decimal import Decimal

from netting import Transaction, simplify_debts


def test_already_settled_group():
    # TODO: balances where everyone nets to 0 -- what should come back?
    pass


def test_two_person_settle():
    # TODO: one creditor, one debtor, amounts match exactly.
    # Assert the exact Transaction(s) returned, not just the length.
    pass


def test_four_person_worked_example():
    # TODO: the A:+40, B:+10, C:-30, D:-20 example from earlier.
    # Assert the exact sequence: C->A 30, D->A 10, D->B 10.
    pass


def test_exact_tie_zeroes_both_sides_same_step():
    # TODO: a creditor and debtor with equal magnitude, e.g. +15 / -15,
    # so the transfer amount zeroes both out in the same loop iteration.
    # This is the "two separate `if`s, not `elif`" branch in simplify_debts --
    # make sure both actually get dropped, not just one.
    pass
