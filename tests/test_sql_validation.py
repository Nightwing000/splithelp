import pytest

from knowledge_base import SQL_EXAMPLES
from sql_validation import SQLValidationError, validate_read_only_sql


def test_validate_accepts_select_from_allowed_table():
    sql = validate_read_only_sql("SELECT id, name FROM Users;")

    assert sql == "SELECT id, name FROM Users"


def test_validate_accepts_read_only_cte():
    sql = validate_read_only_sql(
        """
        WITH totals AS (
            SELECT user_id, SUM(amount) AS total
            FROM ExpensePayments
            GROUP BY user_id
        )
        SELECT * FROM totals;
        """
    )

    assert "WITH totals AS" in sql
    assert "ExpensePayments" in sql


@pytest.mark.parametrize("value", ["", "   ", None, 123])
def test_validate_rejects_empty_or_non_string_sql(value):
    with pytest.raises(SQLValidationError, match="cannot be empty"):
        validate_read_only_sql(value)


def test_validate_rejects_cannot_answer():
    with pytest.raises(SQLValidationError, match="could not answer"):
        validate_read_only_sql("```CANNOT_ANSWER```")


def test_validate_rejects_multiple_statements():
    with pytest.raises(SQLValidationError, match="Exactly one"):
        validate_read_only_sql("SELECT id FROM Users; SELECT name FROM Users;")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO Users (name, email) VALUES ('A', 'a@example.com');",
        "UPDATE Users SET name = 'Changed';",
        "DELETE FROM Users;",
        "DROP TABLE Users;",
        "ALTER TABLE Users ADD COLUMN secret TEXT;",
    ],
)
def test_validate_rejects_writes_and_ddl(sql):
    with pytest.raises(SQLValidationError):
        validate_read_only_sql(sql)


def test_validate_rejects_unknown_table():
    with pytest.raises(SQLValidationError, match="not approved"):
        validate_read_only_sql("SELECT * FROM SecretTable;")


def test_validate_rejects_schema_qualified_table():
    with pytest.raises(SQLValidationError, match="Schema-qualified"):
        validate_read_only_sql("SELECT * FROM public.Users;")


def test_validate_rejects_dangerous_function():
    with pytest.raises(SQLValidationError, match="not approved"):
        validate_read_only_sql("SELECT pg_read_file('/etc/passwd');")


def test_validate_rejects_select_into():
    with pytest.raises(SQLValidationError, match="SELECT INTO"):
        validate_read_only_sql("SELECT id INTO new_users FROM Users;")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_sleep(100000);",
        "SELECT version();",
        "SELECT generate_series(1, 1000000000);",
        "SELECT current_setting('data_directory');",
        "SELECT id FROM Users WHERE id = 1 OR COALESCE(id, 0) = pg_sleep(5);",
    ],
)
def test_validate_rejects_functions_outside_allowlist(sql):
    with pytest.raises(SQLValidationError, match="not approved"):
        validate_read_only_sql(sql)


def test_validate_accepts_and_or_conditions():
    sql = "SELECT id FROM Expenses WHERE group_id = 1 AND (id = 2 OR id = 3);"

    assert validate_read_only_sql(sql).startswith("SELECT id FROM Expenses")


def test_validate_accepts_allowed_aggregates_and_case():
    validate_read_only_sql(
        "SELECT COUNT(*), CASE WHEN SUM(amount) > 0 THEN 1 ELSE 0 END "
        "FROM ExpensePayments;"
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT password FROM Users;",
        "SELECT u.password FROM Users u;",
        'SELECT "Name" FROM Users;',
        "SELECT bogus FROM (SELECT SUM(amount) AS total FROM ExpensePayments) t;",
        "SELECT u.id FROM Users u WHERE EXISTS "
        "(SELECT 1 FROM ExpenseSplits s WHERE s.user_id = u.id AND s.secret = 1);",
        "SELECT name FROM Users JOIN Groups ON Groups.id = Users.id;",
    ],
)
def test_validate_rejects_unknown_or_ambiguous_columns(sql):
    with pytest.raises(SQLValidationError, match="unknown or ambiguous column"):
        validate_read_only_sql(sql)


def test_validate_returns_original_sql_not_qualified_rewrite():
    assert validate_read_only_sql("SELECT COUNT(*) FROM Users;") == (
        "SELECT COUNT(*) FROM Users"
    )


@pytest.mark.parametrize(
    "example", SQL_EXAMPLES, ids=[item["id"] for item in SQL_EXAMPLES]
)
def test_trusted_examples_pass_validation(example):
    validate_read_only_sql(example["content"].split("SQL:\n", 1)[1])


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM Users WHERE NOT EXISTS "
        "(SELECT 1 FROM GroupMembers gm WHERE gm.user_id = Users.id);",
        "SELECT amount::numeric FROM ExpensePayments;",
        "SELECT LOWER(name) FROM Users;",
        "SELECT ABS(amount_owed) FROM ExpenseSplits;",
        "SELECT DATE_TRUNC('month', created_at) FROM Expenses;",
        "SELECT EXTRACT(MONTH FROM created_at) FROM Expenses;",
        "SELECT id FROM Expenses WHERE created_at > NOW() - INTERVAL '7 days';",
    ],
)
def test_validate_accepts_common_safe_constructs(sql):
    validate_read_only_sql(sql)
