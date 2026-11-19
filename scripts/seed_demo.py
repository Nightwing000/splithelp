"""Seed a small demo group ("Goa Trip") for trying the bot and NL questions.

Safe to rerun: if the demo group already exists, nothing is written.
Prints the group id to put in SPLITHELP_GROUP_ID.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from repositories.expense_repository import ExpensePayment, ExpenseRepository, ExpenseSplit  # noqa: E402
from repositories.group_repository import GroupRepository  # noqa: E402
from repositories.user_repository import UserRepository  # noqa: E402
from splitting import allocate_equal  # noqa: E402

GROUP_NAME = "Goa Trip"
PEOPLE = [("Ishan", "ishan@example.com"), ("Alex", "alex@example.com"), ("Priya", "priya@example.com")]


def _conninfo() -> str:
    return (
        f"host={os.environ.get('POSTGRES_HOST', '127.0.0.1')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')} dbname=expense_splitter "
        f"user={os.environ.get('POSTGRES_ADMIN_USER', 'splitter_user')} "
        f"password={os.environ.get('POSTGRES_ADMIN_PASSWORD', 'devpassword')}"
    )


def main() -> None:
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
    with ConnectionPool(_conninfo(), open=True) as pool:
        users = UserRepository(pool)
        groups = GroupRepository(pool)
        expenses = ExpenseRepository(pool)

        people = [users.get_by_email(email) or users.create(name, email) for name, email in PEOPLE]
        ishan, alex, priya = people

        existing = next(
            (group for group in groups.list_groups_for_user(ishan.id) if group.name == GROUP_NAME),
            None,
        )
        if existing:
            print(f"Demo group already exists. SPLITHELP_GROUP_ID={existing.id}")
            return

        group = groups.create(GROUP_NAME, ishan.id)  # also adds Ishan as a member
        for person in (alex, priya):
            groups.add_member(group.id, person.id)

        everyone = [person.id for person in people]
        for description, payer, total in (
            ("Hotel", ishan, Decimal("3000.00")),
            ("Dinner", alex, Decimal("900.00")),
            ("Taxi", ishan, Decimal("100.00")),
        ):
            shares = allocate_equal(total, everyone)
            expenses.create_expense(
                group.id,
                description,
                [ExpensePayment(payer.id, total)],
                [ExpenseSplit(user_id, "equal", share) for user_id, share in shares.items()],
            )

        print(f"Seeded '{GROUP_NAME}'. SPLITHELP_GROUP_ID={group.id}")
        print("User ids for TELEGRAM_USERS:", {person.name: person.id for person in people})


if __name__ == "__main__":
    main()
