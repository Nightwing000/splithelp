from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import psycopg


@dataclass
class ExpensePayment:
    user_id: int
    amount: Decimal
    id: int | None = None
    expense_id: int | None = None


@dataclass
class ExpenseSplit:
    user_id: int
    split_type: str
    amount_owed: Decimal
    id: int | None = None
    expense_id: int | None = None


@dataclass
class Expense:
    id: int
    group_id: int
    description: str
    created_at: datetime
    spent_on: date | None = None
    merchant: str | None = None
    payments: list[ExpensePayment] = field(default_factory=list)
    splits: list[ExpenseSplit] = field(default_factory=list)


class UnbalancedExpenseError(Exception):
    pass


class ExpenseNotFoundError(Exception):
    pass


class ExpenseRepository:
    def __init__(self, pool):
        self.pool = pool

    def create_expense(
        self,
        group_id: int,
        description: str,
        payments: list[ExpensePayment],
        splits: list[ExpenseSplit],
        spent_on: date | None = None,
        merchant: str | None = None,
    ) -> Expense:
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    # COALESCE keeps the column default (today) when no
                    # date is given, instead of inserting NULL.
                    cur.execute(
                        "INSERT INTO Expenses (group_id, description, spent_on, merchant) "
                        "VALUES (%s, %s, COALESCE(%s, CURRENT_DATE), %s) "
                        "RETURNING id, group_id, description, created_at, spent_on, merchant;",
                        (group_id, description, spent_on, merchant),
                    )
                    row = cur.fetchone()
                    expense = Expense(
                        id=row[0],
                        group_id=row[1],
                        description=row[2],
                        created_at=row[3],
                        spent_on=row[4],
                        merchant=row[5],
                    )

                    for payment in payments:
                        cur.execute(
                            """
                            INSERT INTO ExpensePayments (expense_id, user_id, amount)
                            VALUES (%s, %s, %s);
                            """,
                            (expense.id, payment.user_id, payment.amount),
                        )
                        expense.payments.append(payment)

                    for split in splits:
                        cur.execute(
                            """
                            INSERT INTO ExpenseSplits (expense_id, user_id, split_type, amount_owed)
                            VALUES (%s, %s, %s, %s);
                            """,
                            (expense.id, split.user_id, split.split_type, split.amount_owed),
                        )
                        expense.splits.append(split)

            return expense
        except psycopg.errors.RaiseException as e:
            raise UnbalancedExpenseError(
                f"Expense {expense.id} is unbalanced"
            ) from e

    def get_expense(self, expense_id: int) -> Expense | None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, group_id, description, created_at, spent_on, merchant
                    FROM Expenses
                    WHERE id = %s;
                    """,
                    (expense_id,),
                )

                row = cur.fetchone()

                if row is None:
                    return None

                expense = Expense(
                    id=row[0],
                    group_id=row[1],
                    description=row[2],
                    created_at=row[3],
                    spent_on=row[4],
                    merchant=row[5],
                )

                cur.execute(
                    """
                    SELECT id, expense_id, user_id, amount
                    FROM ExpensePayments
                    WHERE expense_id = %s;
                    """,
                    (expense_id,),
                )

                payment_rows = cur.fetchall()

                payments = [
                    ExpensePayment(
                        id=row[0],
                        expense_id=row[1],
                        user_id=row[2],
                        amount=row[3],
                    )
                    for row in payment_rows
                ]

                cur.execute(
                    """
                    SELECT id, expense_id, user_id, split_type, amount_owed
                    FROM ExpenseSplits
                    WHERE expense_id = %s;
                    """,
                    (expense_id,),
                )

                split_rows = cur.fetchall()

                splits = [
                    ExpenseSplit(
                        id=row[0],
                        expense_id=row[1],
                        user_id=row[2],
                        split_type=row[3],
                        amount_owed=row[4],
                    )
                    for row in split_rows
                ]

                expense.payments = payments
                expense.splits = splits

                return expense

    def list_expenses_for_group(self, group_id: int) -> list[Expense]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, group_id, description, created_at, spent_on, merchant
                    FROM Expenses
                    WHERE group_id = %s
                    ORDER BY created_at DESC;
                    """,
                    (group_id,),
                )

                rows = cur.fetchall()

                expenses = [
                    Expense(
                        id=row[0],
                        group_id=row[1],
                        description=row[2],
                        created_at=row[3],
                        spent_on=row[4],
                        merchant=row[5],
                    )
                    for row in rows
                ]

                return expenses

    def delete_expense(self, expense_id: int) -> None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM Expenses
                    WHERE id = %s;
                    """,
                    (expense_id,),
                )

                if cur.rowcount == 0:
                    raise ExpenseNotFoundError(
                        f"Expense {expense_id} not found"
                    )

    def get_group_balances(self, group_id: int) -> dict[int, Decimal]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COALESCE(payments.user_id, splits.user_id) AS user_id,
                        COALESCE(payments.total_paid, 0)
                        - COALESCE(splits.total_owed, 0) AS net_balance
                    FROM (
                        SELECT
                            ep.user_id,
                            SUM(ep.amount) AS total_paid
                        FROM ExpensePayments ep
                        JOIN Expenses e ON e.id = ep.expense_id
                        WHERE e.group_id = %s
                        GROUP BY ep.user_id
                    ) payments

                    FULL OUTER JOIN (
                        SELECT
                            es.user_id,
                            SUM(es.amount_owed) AS total_owed
                        FROM ExpenseSplits es
                        JOIN Expenses e ON e.id = es.expense_id
                        WHERE e.group_id = %s
                        GROUP BY es.user_id
                    ) splits ON splits.user_id = payments.user_id;
                    """,
                    (group_id, group_id),
                )

                rows = cur.fetchall()

                return {user_id: net_balance for user_id, net_balance in rows}
