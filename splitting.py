from decimal import Decimal

CENTS = Decimal("0.01")


def allocate_equal(total: Decimal, user_ids: list[int]) -> dict[int, Decimal]:
    """Split ``total`` equally, giving leftover cents to the lowest user ids.

    Shares always sum exactly to ``total``, so the expense passes the
    database balance trigger. 100.00 / 3 gives 33.34, 33.33, 33.33.
    """
    # A float would fail later with a confusing AttributeError, and
    # int(0.29 * 100) == 28 silently loses a cent.
    if not isinstance(total, Decimal):
        raise TypeError("total must be a Decimal")
    if not user_ids:
        raise ValueError("user_ids must not be empty")
    if len(user_ids) != len(set(user_ids)):
        raise ValueError("user_ids must not contain duplicates")
    if total <= 0:
        raise ValueError("total must be greater than zero")
    if total != total.quantize(CENTS):
        raise ValueError("total must have at most two decimal places")

    # Whole cents make the leftover an exact integer, not a rounding guess.
    cents = int(total * 100)
    base, leftover = divmod(cents, len(user_ids))

    # Sorted so the same expense always stores the same shares,
    # whatever order the ids arrive in.
    return {
        user_id: (Decimal(base + (index < leftover)) / 100).quantize(CENTS)
        for index, user_id in enumerate(sorted(user_ids))
    }
