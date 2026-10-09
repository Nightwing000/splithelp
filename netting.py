from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Transaction:
    payer_id: int
    payee_id: int
    amount: Decimal


def simplify_debts(balances: dict[int, Decimal]) -> list[Transaction]:
    """
    balances: {user_id: net}, where net = total_paid - total_owed.
    Positive net means owed money; negative means owes money.
    """

    creditors = [
        [user_id, net]
        for user_id, net in balances.items()
        if net > 0
    ]

    debtors = [
        [user_id, net]
        for user_id, net in balances.items()
        if net < 0
    ]

    transactions: list[Transaction] = []

    while creditors and debtors:

        # Largest creditor first
        creditors.sort(key=lambda x: x[1], reverse=True)

        # Most negative debtor first
        debtors.sort(key=lambda x: x[1])

        creditor_id, creditor_amount = creditors[0]
        debtor_id, debtor_amount = debtors[0]

        # Debtor amount is negative, so take its absolute value
        transfer = min(creditor_amount, abs(debtor_amount))

        transactions.append(
            Transaction(
                payer_id=debtor_id,
                payee_id=creditor_id,
                amount=transfer,
            )
        )

        # Update remaining balances
        creditors[0][1] -= transfer
        debtors[0][1] += transfer

        # Remove anyone who has been completely settled
        if creditors[0][1] == 0:
            creditors.pop(0)

        if debtors[0][1] == 0:
            debtors.pop(0)

    return transactions
