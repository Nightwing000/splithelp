"""Keep the validator's column policy in sync with init/01_schema.sql.

ALLOWED_COLUMNS is a hand-written security policy, not a copy of the schema:
every schema column must be deliberately allowed or excluded, so a new
column (say Users.password_hash) can never become queryable by accident or
be silently rejected without anyone noticing.
"""
from pathlib import Path

from schema_drift import find_schema_drift, parse_schema_columns
from sql_validation import ALLOWED_COLUMNS, ALLOWED_TABLES, EXCLUDED_COLUMNS

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "init" / "01_schema.sql"


# --- parse_schema_columns -------------------------------------------------


def test_parses_real_schema():
    # Written out from init/01_schema.sql by hand, independently of
    # ALLOWED_COLUMNS, so this checks the parser rather than the policy.
    assert parse_schema_columns(SCHEMA_PATH.read_text(encoding="utf-8")) == {
        "users": {"id", "name", "email", "created_at", "deleted_at"},
        "groups": {"id", "name", "created_by", "created_at"},
        "groupmembers": {"group_id", "user_id", "joined_at"},
        "expenses": {"id", "group_id", "description", "created_at"},
        "expensepayments": {"id", "expense_id", "user_id", "amount"},
        "expensesplits": {"id", "expense_id", "user_id", "split_type", "amount_owed"},
    }


def test_ignores_table_constraints():
    schema = """
    CREATE TABLE Things (
        id BIGSERIAL PRIMARY KEY,
        owner_id BIGINT NOT NULL,
        PRIMARY KEY (id, owner_id),
        UNIQUE (owner_id),
        FOREIGN KEY (owner_id) REFERENCES Users(id) ON DELETE RESTRICT,
        CHECK (owner_id > 0)
    );
    """

    assert parse_schema_columns(schema) == {"things": {"id", "owner_id"}}


def test_ignores_functions_and_triggers():
    schema = """
    CREATE TABLE Things (id BIGINT);

    CREATE OR REPLACE FUNCTION check_things()
    RETURNS TRIGGER AS $$
    BEGIN
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE CONSTRAINT TRIGGER check_things_trigger
    AFTER INSERT ON Things
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION check_things();
    """

    assert parse_schema_columns(schema) == {"things": {"id"}}


def test_lowercases_unquoted_identifiers():
    # Postgres folds unquoted names to lowercase, and ALLOWED_COLUMNS
    # is keyed the same way.
    schema = "CREATE TABLE GroupMembers (Group_ID BIGINT, JoinedAt TIMESTAMP);"

    assert parse_schema_columns(schema) == {"groupmembers": {"group_id", "joinedat"}}


# --- find_schema_drift ----------------------------------------------------
# These prove the checker actually fires; a drift check that can never fail
# would make the real-schema test below meaningless.

SCHEMA = {"users": {"id", "name", "email"}}


def test_no_drift_when_policy_covers_schema():
    allowed = {"users": {"id", "name"}}
    excluded = {"users": {"email"}}

    assert find_schema_drift(SCHEMA, allowed, excluded) == []


def test_new_schema_column_must_be_allowed_or_excluded():
    allowed = {"users": {"id", "name", "email"}}
    schema = {"users": {"id", "name", "email", "password_hash"}}

    problems = find_schema_drift(schema, allowed, {})

    assert len(problems) == 1
    assert "users.password_hash" in problems[0]


def test_allowed_column_missing_from_schema():
    # e.g. a column was renamed in the schema but not in the policy.
    allowed = {"users": {"id", "name", "email", "nickname"}}

    problems = find_schema_drift(SCHEMA, allowed, {})

    assert len(problems) == 1
    assert "users.nickname" in problems[0]


def test_column_both_allowed_and_excluded():
    allowed = {"users": {"id", "name", "email"}}
    excluded = {"users": {"email"}}

    problems = find_schema_drift(SCHEMA, allowed, excluded)

    assert len(problems) == 1
    assert "users.email" in problems[0]


def test_schema_table_missing_from_policy():
    schema = {"users": {"id"}, "receipts": {"id", "image_url"}}
    allowed = {"users": {"id"}}

    problems = find_schema_drift(schema, allowed, {})

    assert len(problems) == 1
    assert "receipts" in problems[0]


def test_policy_table_missing_from_schema():
    allowed = {"users": {"id", "name", "email"}, "ghosts": {"id"}}

    problems = find_schema_drift(SCHEMA, allowed, {})

    assert len(problems) == 1
    assert "ghosts" in problems[0]


def test_reports_every_problem_not_just_the_first():
    schema = {"users": {"id", "password_hash"}, "receipts": {"id"}}
    allowed = {"users": {"id", "nickname"}}

    problems = find_schema_drift(schema, allowed, {})

    assert len(problems) == 3


# --- the real check ---------------------------------------------------------


def test_validator_policy_matches_real_schema():
    schema = parse_schema_columns(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert find_schema_drift(schema, ALLOWED_COLUMNS, EXCLUDED_COLUMNS) == []


def test_allowed_tables_match_allowed_columns():
    assert ALLOWED_TABLES == set(ALLOWED_COLUMNS)
