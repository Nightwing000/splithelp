"""Prove at the database level that splitter_readonly cannot write.

These run against the Docker Compose Postgres and skip when it is not
reachable or POSTGRES_READONLY_PASSWORD is unset (e.g. in CI).
"""
import os

import psycopg
import pytest
from dotenv import load_dotenv

from nl_to_sql import DATABASE_NAME, ENV_PATH, READ_ONLY_DB_USER


# Module scope: if Postgres is down, wait out connect_timeout once, not per test.
@pytest.fixture(scope="module")
def readonly_connection():
    load_dotenv(dotenv_path=ENV_PATH)
    password = os.environ.get("POSTGRES_READONLY_PASSWORD")
    if not password:
        pytest.skip("POSTGRES_READONLY_PASSWORD is not set")

    try:
        conn = psycopg.connect(
            host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
            dbname=DATABASE_NAME,
            user=READ_ONLY_DB_USER,
            password=password,
            # Without this, a stopped container hangs for about two minutes.
            connect_timeout=3,
        )
    except psycopg.OperationalError:
        pytest.skip("Docker PostgreSQL is not reachable")

    with conn:
        yield conn


@pytest.fixture
def readonly_cursor(readonly_connection):
    with readonly_connection.cursor() as cur:
        yield cur
    # A rejected statement aborts the transaction; rolling back also
    # discards anything a test managed to do.
    readonly_connection.rollback()


def test_read_only_role_can_select(readonly_cursor):
    readonly_cursor.execute("SELECT COUNT(*) FROM Users")

    assert readonly_cursor.fetchone()[0] >= 0


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO Users (name, email) VALUES ('probe', 'probe@example.com')",
        "UPDATE Users SET name = 'probe'",
        "DELETE FROM Users",
        "CREATE TABLE public.read_only_probe (id integer)",
        "DROP TABLE Users",
    ],
)
def test_read_only_role_cannot_write(readonly_cursor, sql):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        readonly_cursor.execute(sql)


def test_read_only_role_has_statement_timeout(readonly_cursor):
    readonly_cursor.execute("SHOW statement_timeout")

    assert readonly_cursor.fetchone()[0] == "5s"
