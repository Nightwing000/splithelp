from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import psycopg


@dataclass
class ExpensePayment:
    user_id: int
    amount: float
    id: int | None = None
    expense_id: int | None = None


@dataclass
class ExpenseSplit:
    user_id: int
    split_type: str
    amount_owed: float
    id: int | None = None
    expense_id: int | None = None


@dataclass
class Expense:
    id: int
    group_id: int
    description: str
    created_at: datetime
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
    ) -> Expense:
        # This is the one method in the whole repository layer where the
        # transaction boundary is load-bearing, not just good practice.
        # The DB trigger only checks sum(payments) == sum(splits) for a
        # given expense_id, and it's deferred to COMMIT. That means:
        #
        #   - all three inserts (Expenses, then N ExpensePayments, then N
        #     ExpenseSplits) need to happen inside ONE `with self.pool
        #     .connection()` block, sharing one cursor or at least one
        #     connection, so they commit or roll back together.
        #   - if you open a fresh `with self.pool.connection()` per insert
        #     instead of one for the whole method, each one commits on its
        #     own exit -- the trigger would fire (and could reject) after
        #     the Expenses insert alone, before payments/splits even exist.
        #
        # Questions to work through before you write the SQL:
        #   - You need the new expense's id before you can insert payments
        #     or splits (they have expense_id FKs). What's giving you that
        #     id -- RETURNING on the first insert, like in UserRepository?
        #   - Inserting N payments and N splits means N+N execute() calls
        #     (or can you do a multi-row INSERT? look at psycopg's
        #     executemany / execute_values-style options if you want that).
        #   - If total_paid != total_owed, the trigger raises inside
        #     Postgres. What actually happens to your Python code at that
        #     point -- does execute() raise an exception you can catch? If
        #     you wanted to turn that into your own UnbalancedExpenseError
        #     instead of leaking a raw psycopg error, where would that
        #     try/except need to sit relative to the `with` block? (Careful:
        #     the trigger is DEFERRED -- it doesn't fire on the individual
        #     execute() calls at all. It fires when the transaction tries
        #     to commit. So which statement in your code is actually the
        #     one that could raise it?)
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO Expenses (group_id, description) VALUES (%s, %s) "
                        "RETURNING id, group_id, description, created_at;",
                        (group_id, description),
                    )
                    row = cur.fetchone()
                    expense = Expense(
                        id=row[0],
                        group_id=row[1],
                        description=row[2],
                        created_at=row[3],
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

                # 1. Get the expense itself
                cur.execute(
                    """
                    SELECT id, group_id, description, created_at
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
                )

                # 2. Get all payments for this expense
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

                # 3. Get all splits for this expense
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

                # 4. Put everything together
                expense.payments = payments
                expense.splits = splits

                return expense

    def list_expenses_for_group(self, group_id: int) -> list[Expense]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, group_id, description, created_at
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
