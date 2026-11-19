import sqlglot
from sqlglot import exp


def parse_schema_columns(schema_sql: str) -> dict[str, set[str]]:
    """Return the columns declared by CREATE TABLE statements in *schema_sql*."""
    schema: dict[str, set[str]] = {}

    for stmt in sqlglot.parse(schema_sql, read="postgres"):
        if not isinstance(stmt, exp.Create) or stmt.args.get("kind") != "TABLE":
            continue

        table = stmt.this.this
        table_name = table.name.lower()
        schema[table_name] = {
            column.name.lower()
            for column in stmt.this.expressions
            if isinstance(column, exp.ColumnDef)
        }

    return schema


def find_schema_drift(
    schema: dict[str, set[str]],
    allowed: dict[str, set[str]],
    excluded: dict[str, set[str]],
) -> list[str]:
    """Find differences between a parsed schema and the column policy."""
    problems: list[str] = []

    for table in sorted(schema.keys() - allowed.keys()):
        problems.append(f"table {table} is in the schema but not in ALLOWED_COLUMNS")

    for table in sorted(allowed.keys() - schema.keys()):
        problems.append(f"table {table} is in ALLOWED_COLUMNS but not in the schema")

    for table in sorted(schema.keys() & allowed.keys()):
        schema_columns = schema[table]
        allowed_columns = allowed[table]
        excluded_columns = excluded.get(table, set())

        for column in sorted(allowed_columns - schema_columns):
            problems.append(f"{table}.{column} is allowed but not in the schema")
        for column in sorted(schema_columns - allowed_columns - excluded_columns):
            problems.append(f"{table}.{column} is neither allowed nor excluded")
        for column in sorted(allowed_columns & excluded_columns):
            problems.append(f"{table}.{column} is both allowed and excluded")

    return problems
