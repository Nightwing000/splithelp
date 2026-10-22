from __future__ import annotations

import re

import sqlglot
from sqlglot import exp


class SQLValidationError(ValueError):
    """Raised when generated SQL violates the read-only query policy."""


ALLOWED_TABLES = {
    "users",
    "groups",
    "groupmembers",
    "expenses",
    "expensepayments",
    "expensesplits",
}

# Phase 6 follow-up: replace this schema-level placeholder with the exact
# columns allowed for each table, then validate every exp.Column node.
ALLOWED_COLUMNS = {
    "users": set(),
    "groups": set(),
    "groupmembers": set(),
    "expenses": set(),
    "expensepayments": set(),
    "expensesplits": set(),
}

# Phase 6 follow-up: replace this blocklist with an explicit allowlist of
# aggregate, conditional, and date functions used by supported questions.
BLOCKED_FUNCTIONS = {
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "lo_import",
    "lo_export",
    "dblink",
}
ALLOWED_FUNCTIONS = set()

# Phase 6 follow-up: use these names when creating a restricted PostgreSQL
# role for NL-to-SQL connections. Do not reuse the write-capable app role.
READ_ONLY_ROLE_NAME = "splitter_readonly"
READ_ONLY_ROLE_PASSWORD = "<set outside source control>"


def validate_read_only_sql(sql: str) -> str:
    """Validate and return one safe, read-only PostgreSQL statement.

    Parse ``sql`` with SQLGlot and enforce the application's read-only policy.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise SQLValidationError("SQL query cannot be empty.")

    normalized_sql = sql.strip()
    normalized_sql = re.sub(
        r"^```(?:sql)?\s*|\s*```$",
        "",
        normalized_sql,
        flags=re.IGNORECASE,
    ).strip()

    if normalized_sql.upper().rstrip(";").strip() == "CANNOT_ANSWER":
        raise SQLValidationError(
            "The model could not answer this question using the available data."
        )

    try:
        statements = sqlglot.parse(normalized_sql, read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise SQLValidationError("Invalid PostgreSQL SQL syntax.") from exc

    statements = [stmt for stmt in statements if stmt is not None]

    if len(statements) != 1:
        raise SQLValidationError("Exactly one SQL statement is required.")

    statement = statements[0]
    cte_names = {
        cte.alias_or_name.lower()
        for cte in statement.find_all(exp.CTE)
    }

    # Permit SELECT and WITH ... SELECT. SQLGlot represents a CTE query
    # as a query expression, with its CTEs attached to that expression.
    if not isinstance(statement, exp.Query):
        raise SQLValidationError("Only SELECT queries are allowed.")

    # Inspect the full AST, including nested queries and CTEs.
    for node in statement.walk():
        # Reject write operations, DDL, administrative statements,
        # and other command-like operations anywhere in the AST.
        if isinstance(
            node,
            (
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Merge,
                exp.Create,
                exp.Drop,
                exp.Alter,
                exp.Command,
            ),
        ):
            raise SQLValidationError(
                "Write, DDL, and administrative operations are not allowed."
            )

        # SELECT INTO can create a table.
        if isinstance(node, exp.Into):
            raise SQLValidationError("SELECT INTO is not allowed.")

        # Locking clauses can acquire locks and are unnecessary here.
        if isinstance(node, exp.Lock):
            raise SQLValidationError("Locking clauses are not allowed.")

        # Enforce the approved table list using parsed table nodes.
        if isinstance(node, exp.Table):
            table_name = node.name.lower()

            if table_name in cte_names:
                continue

            # Disallow schema-qualified references for this initial policy.
            if node.db or node.catalog:
                raise SQLValidationError(
                    "Schema-qualified table references are not allowed."
                )

            if table_name not in ALLOWED_TABLES:
                raise SQLValidationError(
                    f"Table '{node.name}' is not approved."
                )

        # Block explicitly dangerous function calls.
        if isinstance(node, exp.Anonymous):
            function_name = node.name.lower()

            if function_name in BLOCKED_FUNCTIONS:
                raise SQLValidationError(
                    f"Function '{function_name}' is not allowed."
                )

    return statement.sql(dialect="postgres")
