"""Expense date/merchant columns, against the Docker database.

Skips when PostgreSQL is not reachable (e.g. in CI). Creates its own users
and group with unique emails, so it never touches demo data.
"""
import os
import uuid
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from dotenv import load_dotenv

from nl_to_sql import ENV_PATH


@pytest.fixture(scope="module")
def pool():
    from psycopg_pool import ConnectionPool

    load_dotenv(dotenv_path=ENV_PATH)
    conninfo = (
        f"host={os.environ.get('POSTGRES_HOST', '127.0.0.1')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')} dbname=expense_splitter "
        f"user={os.environ.get('POSTGRES_ADMIN_USER', 'splitter_user')} "
        f"password={os.environ.get('POSTGRES_ADMIN_PASSWORD', 'devpassword')} "
        "connect_timeout=3"
    )
    try:
        psycopg.connect(conninfo).close()
    except psycopg.OperationalError:
        pytest.skip("Docker PostgreSQL is not reachable")

    from scripts.apply_migrations import apply_migrations

    with ConnectionPool(conninfo, open=True) as pool:
        apply_migrations(pool)
        yield pool


@pytest.fixture(scope="module")
def group_and_users(pool):
    from repositories.group_repository import GroupRepository
    from repositories.user_repository import UserRepository

    tag = uuid.uuid4().hex[:8]
    users = UserRepository(pool)
    payer = users.create("Test Payer", f"payer-{tag}@test.invalid")
    sharer = users.create("Test Sharer", f"sharer-{tag}@test.invalid")
    groups = GroupRepository(pool)
    group = groups.create(f"Test group {tag}", payer.id)
    groups.add_member(group.id, sharer.id)
    return group, payer, sharer


def _expense(pool, group_and_users, **details):
    from repositories.expense_repository import ExpensePayment, ExpenseRepository, ExpenseSplit

    group, payer, sharer = group_and_users
    repo = ExpenseRepository(pool)
    created = repo.create_expense(
        group.id,
        "Fireworks",
        [ExpensePayment(payer.id, Decimal("100.00"))],
        [
            ExpenseSplit(payer.id, "exact", Decimal("60.00")),
            ExpenseSplit(sharer.id, "exact", Decimal("40.00")),
        ],
        **details,
    )
    return repo, created


def test_spent_on_and_merchant_round_trip(pool, group_and_users):
    repo, created = _expense(
        pool, group_and_users, spent_on=date(2026, 11, 8), merchant="Cracker Bazaar"
    )

    loaded = repo.get_expense(created.id)

    assert loaded.spent_on == date(2026, 11, 8)
    assert loaded.merchant == "Cracker Bazaar"
    assert created.spent_on == date(2026, 11, 8)


def test_spent_on_defaults_to_today_and_merchant_to_none(pool, group_and_users):
    repo, created = _expense(pool, group_and_users)

    loaded = repo.get_expense(created.id)

    with pool.connection() as conn:
        today = conn.execute("SELECT CURRENT_DATE").fetchone()[0]
    assert loaded.spent_on == today
    assert loaded.merchant is None


def test_list_expenses_includes_details(pool, group_and_users):
    repo, created = _expense(pool, group_and_users, merchant="Corner Shop")
    group, _, _ = group_and_users

    listed = {expense.id: expense for expense in repo.list_expenses_for_group(group.id)}

    assert listed[created.id].merchant == "Corner Shop"


def test_migrations_are_idempotent(pool):
    from scripts.apply_migrations import apply_migrations

    apply_migrations(pool)
    apply_migrations(pool)

    with pool.connection() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'expenses'"
            )
        }
    assert {"spent_on", "merchant"} <= columns


def test_read_only_role_can_select_new_columns(pool):
    # GRANT SELECT ON a table covers columns added later, but prove it.
    load_dotenv(dotenv_path=ENV_PATH)
    password = os.environ.get("POSTGRES_READONLY_PASSWORD")
    if not password:
        pytest.skip("POSTGRES_READONLY_PASSWORD is not set")
    with psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname="expense_splitter",
        user="splitter_readonly",
        password=password,
        connect_timeout=3,
    ) as conn:
        conn.execute("SELECT spent_on, merchant FROM Expenses LIMIT 1")
