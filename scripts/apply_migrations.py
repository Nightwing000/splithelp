"""Apply migrations/*.sql in filename order.

init/01_schema.sql only runs when the Docker volume is first created, so an
existing database needs these to pick up later schema changes. Every
migration is written to be idempotent, so rerunning is safe.

Usage: python scripts/apply_migrations.py
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def apply_migrations(pool) -> list[str]:
    applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        with pool.connection() as conn:
            conn.execute(path.read_text(encoding="utf-8"))
        applied.append(path.name)
    return applied


def main() -> None:
    from dotenv import load_dotenv
    from psycopg_pool import ConnectionPool

    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
    conninfo = (
        f"host={os.environ.get('POSTGRES_HOST', '127.0.0.1')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')} dbname=expense_splitter "
        f"user={os.environ.get('POSTGRES_ADMIN_USER', 'splitter_user')} "
        f"password={os.environ.get('POSTGRES_ADMIN_PASSWORD', 'devpassword')}"
    )
    with ConnectionPool(conninfo, open=True) as pool:
        for name in apply_migrations(pool):
            print(f"Applied {name}")


if __name__ == "__main__":
    main()
