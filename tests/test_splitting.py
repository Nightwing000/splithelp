from decimal import Decimal

import pytest

from splitting import allocate_equal


def test_leftover_cent_goes_to_lowest_user_id():
    assert allocate_equal(Decimal("100.00"), [1, 2, 3]) == {
        1: Decimal("33.34"),
        2: Decimal("33.33"),
        3: Decimal("33.33"),
    }


def test_input_order_does_not_change_shares():
    assert allocate_equal(Decimal("100.00"), [3, 1, 2]) == allocate_equal(
        Decimal("100.00"), [1, 2, 3]
    )


def test_even_split_has_no_leftover():
    assert allocate_equal(Decimal("90.00"), [1, 2, 3]) == {
        1: Decimal("30.00"),
        2: Decimal("30.00"),
        3: Decimal("30.00"),
    }


def test_single_cent_split_three_ways():
    # 0.00 shares are allowed: ExpenseSplits checks amount_owed >= 0.
    assert allocate_equal(Decimal("0.01"), [1, 2, 3]) == {
        1: Decimal("0.01"),
        2: Decimal("0.00"),
        3: Decimal("0.00"),
    }


def test_shares_always_have_two_decimal_places():
    shares = allocate_equal(Decimal("99"), [1, 2, 3])

    assert all(str(share) == "33.00" for share in shares.values())


def test_single_user_gets_whole_total():
    assert allocate_equal(Decimal("12.34"), [7]) == {7: Decimal("12.34")}


@pytest.mark.parametrize(
    "total",
    ["0.01", "0.02", "1.00", "10.00", "99.99", "100.00", "123.45", "1000.01"],
)
@pytest.mark.parametrize("group_size", [1, 2, 3, 4, 6, 7, 11])
def test_shares_always_sum_to_total(total, group_size):
    # The database trigger rejects any expense where this does not hold.
    total = Decimal(total)
    shares = allocate_equal(total, list(range(1, group_size + 1)))

    assert sum(shares.values()) == total
    assert max(shares.values()) - min(shares.values()) <= Decimal("0.01")


def test_rejects_float_total():
    with pytest.raises(TypeError, match="Decimal"):
        allocate_equal(100.0, [1, 2, 3])


@pytest.mark.parametrize(
    ("total", "user_ids", "message"),
    [
        (Decimal("10.00"), [], "empty"),
        (Decimal("10.00"), [1, 1, 2], "duplicates"),
        (Decimal("0.00"), [1, 2], "greater than zero"),
        (Decimal("-5.00"), [1, 2], "greater than zero"),
        (Decimal("10.005"), [1, 2], "two decimal places"),
    ],
)
def test_rejects_invalid_input(total, user_ids, message):
    with pytest.raises(ValueError, match=message):
        allocate_equal(total, user_ids)
