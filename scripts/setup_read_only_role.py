from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
ROLE_NAME = "splitter_readonly"
DATABASE_NAME = "expense_splitter"
TABLES = (
    "users",
    "groups",
    "groupmembers",
    "expenses",
    "expensepayments",
    "expensesplits",
)


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is required in {ENV_PATH}. "
            "Do not commit that value."
        )
    return value


def _connection_string() -> str:
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    admin_user = os.environ.get("POSTGRES_ADMIN_USER", "splitter_user")
    admin_password = os.environ.get(
        "POSTGRES_ADMIN_PASSWORD", "devpassword"
    )
    return (
        f"host={host} port={port} dbname={DATABASE_NAME} "
        f"user={admin_user} password={admin_password}"
    )


def _role_exists(cur) -> bool:
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
        (ROLE_NAME,),
    )
    return cur.fetchone()[0]


def _create_or_update_role(cur, password: str) -> None:
    role_identifier = sql.Identifier(ROLE_NAME)
    password_literal = sql.Literal(password)

    if _role_exists(cur):
        cur.execute(
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                role_identifier,
                password_literal,
            )
        )
    else:
        cur.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                role_identifier,
                password_literal,
            )
        )


def _configure_privileges(cur) -> None:
    role = sql.Identifier(ROLE_NAME)
    database = sql.Identifier(DATABASE_NAME)
    table_list = sql.SQL(", ").join(
        sql.Identifier("public", table_name) for table_name in TABLES
    )

    statements = (
        sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(database, role),
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role),
        sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(role),
        sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role),
        sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(
            role
        ),
        sql.SQL("GRANT SELECT ON {} TO {}").format(table_list, role),
        sql.SQL(
            "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}"
        ).format(role),
        sql.SQL(
            "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {}"
        ).format(role),
    )

    for statement in statements:
        cur.execute(statement)


def configure_role() -> None:
    load_dotenv(dotenv_path=ENV_PATH)
    readonly_password = _required_environment("POSTGRES_READONLY_PASSWORD")

    with psycopg.connect(_connection_string()) as conn:
        with conn.cursor() as cur:
            _create_or_update_role(cur, readonly_password)
            _configure_privileges(cur)

    print(f"Configured read-only role: {ROLE_NAME}")


def verify_role() -> None:
    load_dotenv(dotenv_path=ENV_PATH)
    readonly_password = _required_environment("POSTGRES_READONLY_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    connection_string = (
        f"host={host} port={port} dbname={DATABASE_NAME} "
        f"user={ROLE_NAME} password={readonly_password}"
    )

    with psycopg.connect(connection_string) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)

            try:
                cur.execute("CREATE TABLE public.read_only_probe (id integer)")
            except psycopg.errors.InsufficientPrivilege:
                conn.rollback()
            else:
                raise RuntimeError(
                    "Read-only verification failed: DDL was allowed."
                )

            try:
                cur.execute("INSERT INTO public.users (name, email) "
                            "VALUES ('probe', 'probe@example.com')")
            except psycopg.errors.InsufficientPrivilege:
                conn.rollback()
            else:
                raise RuntimeError(
                    "Read-only verification failed: INSERT was allowed."
                )

    print(f"Verified read-only role: {ROLE_NAME}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configure or verify the NL-to-SQL PostgreSQL role."
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify SELECT succeeds and writes are rejected.",
    )
    args = parser.parse_args()

    if args.verify:
        verify_role()
    else:
        configure_role()


if __name__ == "__main__":
    main()
