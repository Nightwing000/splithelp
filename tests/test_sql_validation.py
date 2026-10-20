import pytest

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
    with pytest.raises(SQLValidationError, match="not allowed"):
        validate_read_only_sql("SELECT pg_read_file('/etc/passwd');")


def test_validate_rejects_select_into():
    with pytest.raises(SQLValidationError, match="SELECT INTO"):
        validate_read_only_sql("SELECT id INTO new_users FROM Users;")
