from pathlib import Path
import sys
import types

import httpx
import pytest

from nl_to_sql import (
    ENV_PATH,
    SCHEMA_PATH,
    LLMUnavailableError,
    REQUEST_TIMEOUT_MS,
    _extract_sql,
    ask,
    build_prompt,
    run_query,
)
from retrieval import retrieve_context
from sql_validation import SQLValidationError


def test_build_prompt_includes_schema_and_question():
    question = "Who paid the most in each group?"

    prompt = build_prompt(question)

    assert question in prompt
    assert Path(SCHEMA_PATH).read_text(encoding="utf-8") in prompt


def test_build_prompt_does_not_depend_on_current_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    prompt = build_prompt("List all active users")

    assert "List all active users" in prompt
    assert "CREATE TABLE Users" in prompt


def test_build_prompt_falls_back_to_full_schema_for_empty_context():
    prompt = build_prompt("An unfamiliar question", [])

    assert "Schema:" in prompt
    assert "CREATE TABLE Users" in prompt


def test_build_prompt_includes_retrieved_context():
    context = [
        {
            "id": "users",
            "kind": "schema",
            "content": "Users stores application user records.",
            "keywords": ["users"],
        },
        {
            "id": "active_users",
            "kind": "rule",
            "content": "Active users have deleted_at IS NULL.",
            "keywords": ["active"],
        },
        {
            "id": "list_active_users",
            "kind": "example",
            "content": "Question: List active users.\nSQL: SELECT ...",
            "keywords": ["active", "users"],
        },
    ]

    prompt = build_prompt("List active users", context)

    assert "Relevant schema:" in prompt
    assert "[users]" in prompt
    assert "Relevant business rules:" in prompt
    assert "Relevant SQL examples:" in prompt
    assert "exactly one read-only PostgreSQL statement" in prompt
    assert "CANNOT_ANSWER" in prompt
    assert "Treat literal values in examples as placeholders" in prompt
    # The phrasing prompt reads amount_owed as a per-expense share, so a
    # computed debt aliased amount_owed was once answered as "nothing found".
    assert "Never alias a computed value with the name of an existing schema column" in prompt
    # Live test: without these, the lite model answered CANNOT_ANSWER 9/9 times
    # for owe/owed questions once all six tables were in the context.
    assert "filter on Groups.name and Users.name" in prompt
    assert "questions are about net balances" in prompt
    assert "Active users have deleted_at IS NULL." in prompt
    assert "Question: List active users." in prompt


def test_retrieved_prompt_respects_per_kind_budgets():
    context = retrieve_context(
        "Who owes money in group 1?",
        schema_limit=1,
        rule_limit=2,
        example_limit=1,
    )
    prompt = build_prompt("Who owes money in group 1?", context)

    assert sum(item["kind"] == "rule" for item in context) == 2
    assert sum(item["kind"] == "schema" for item in context) == 1
    assert sum(item["kind"] == "example" for item in context) == 1
    assert all(prompt.count(f"[{item['id']}]") == 1 for item in context)


def test_extract_sql_removes_sql_code_fence():
    text = "```sql\nSELECT id FROM Users;\n```"

    assert _extract_sql(text) == "SELECT id FROM Users;"


def test_extract_sql_strips_surrounding_whitespace_without_code_fence():
    text = "\n  SELECT id FROM Users;\n"

    assert _extract_sql(text) == "SELECT id FROM Users;"


class FakeAPIError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class FakeClientError(FakeAPIError):
    pass


class FakeServerError(FakeAPIError):
    pass


def _install_fake_genai(monkeypatch, generate_content):
    """Stand in for google.genai so tests never spend Gemini quota."""

    class FakeModels:
        def generate_content(self, *, model, contents):
            return generate_content(model, contents)

    class FakeClient:
        def __init__(self, *, api_key, http_options):
            assert api_key == "fake-test-key"
            assert http_options == {"timeout": REQUEST_TIMEOUT_MS}
            self.models = FakeModels()

    fake_errors = types.ModuleType("google.genai.errors")
    fake_errors.APIError = FakeAPIError
    fake_errors.ClientError = FakeClientError

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_genai.errors = fake_errors

    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai

    fake_dotenv = types.ModuleType("dotenv")

    def load_dotenv(*, dotenv_path):
        assert dotenv_path == ENV_PATH

    fake_dotenv.load_dotenv = load_dotenv
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.errors", fake_errors)
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
    # A developer's .env may override the models (and other tests load the
    # real .env), so start every fake-Gemini test from the defaults.
    monkeypatch.delenv("GEMINI_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)


class FakeResponse:
    def __init__(self, text):
        self.text = text


def test_generate_sql_returns_clean_sql(monkeypatch):
    def generate_content(model, contents):
        assert model == "gemini-flash-latest"
        assert "Show me the users" in contents
        return FakeResponse("```sql\nSELECT id, name FROM Users;\n```")

    _install_fake_genai(monkeypatch, generate_content)
    from nl_to_sql import generate_sql

    result = generate_sql("Show me the users")

    assert result == "SELECT id, name FROM Users;"
    assert "```" not in result


def test_generate_sql_falls_back_when_primary_is_rate_limited(monkeypatch):
    calls = []

    def generate_content(model, contents):
        calls.append(model)
        if model == "gemini-flash-latest":
            raise FakeClientError(429)
        return FakeResponse("SELECT id FROM Users;")

    _install_fake_genai(monkeypatch, generate_content)
    from nl_to_sql import generate_sql

    assert generate_sql("Show me the users") == "SELECT id FROM Users;"
    assert calls == ["gemini-flash-latest", "gemini-flash-lite-latest"]


def test_generate_sql_falls_back_when_primary_is_overloaded(monkeypatch):
    calls = []

    def generate_content(model, contents):
        calls.append(model)
        if model == "gemini-flash-latest":
            raise FakeServerError(503)
        return FakeResponse("SELECT id FROM Users;")

    _install_fake_genai(monkeypatch, generate_content)
    from nl_to_sql import generate_sql

    assert generate_sql("Show me the users") == "SELECT id FROM Users;"
    assert calls == ["gemini-flash-latest", "gemini-flash-lite-latest"]


def test_generate_sql_falls_back_when_primary_times_out(monkeypatch):
    calls = []

    def generate_content(model, contents):
        calls.append(model)
        if model == "gemini-flash-latest":
            raise httpx.ReadTimeout("timed out")
        return FakeResponse("SELECT id FROM Users;")

    _install_fake_genai(monkeypatch, generate_content)
    from nl_to_sql import generate_sql

    assert generate_sql("Show me the users") == "SELECT id FROM Users;"
    assert calls == ["gemini-flash-latest", "gemini-flash-lite-latest"]


def test_generate_sql_raises_when_offline(monkeypatch):
    def generate_content(model, contents):
        raise httpx.ConnectError("no network")

    _install_fake_genai(monkeypatch, generate_content)
    from nl_to_sql import generate_sql

    with pytest.raises(LLMUnavailableError):
        generate_sql("Show me the users")


def test_generate_sql_does_not_retry_other_client_errors(monkeypatch):
    calls = []

    def generate_content(model, contents):
        calls.append(model)
        raise FakeClientError(403)

    _install_fake_genai(monkeypatch, generate_content)
    from nl_to_sql import generate_sql

    with pytest.raises(LLMUnavailableError) as exc_info:
        generate_sql("Show me the users")
    assert calls == ["gemini-flash-latest"]
    assert isinstance(exc_info.value.__cause__, FakeClientError)


def test_generate_sql_raises_when_fallback_is_also_rate_limited(monkeypatch):
    calls = []

    def generate_content(model, contents):
        calls.append(model)
        raise FakeClientError(429)

    _install_fake_genai(monkeypatch, generate_content)
    from nl_to_sql import generate_sql

    with pytest.raises(LLMUnavailableError):
        generate_sql("Show me the users")
    assert calls == ["gemini-flash-latest", "gemini-flash-lite-latest"]


def test_ask_returns_rows_as_dictionaries(monkeypatch):
    class FakeCursor:
        description = [("id",), ("name",)]

        def execute(self, sql):
            assert sql == "SELECT id, name FROM Users"

        def fetchall(self):
            return [(1, "Ishan"), (2, "Alex")]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakeConnection:
        def __init__(self):
            self.cursor_instance = FakeCursor()

        def cursor(self):
            return self.cursor_instance

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakePool:
        def __init__(self):
            self.connection_instance = FakeConnection()

        def connection(self):
            return self.connection_instance

    monkeypatch.setattr(
        "nl_to_sql.generate_sql",
        lambda _question: "SELECT id, name FROM Users;",
    )

    result = ask(FakePool(), "Show me all users")

    assert result == [
        {"id": 1, "name": "Ishan"},
        {"id": 2, "name": "Alex"},
    ]

    # run_query exposes the validated SQL too, for grounding the phrasing.
    query = run_query(FakePool(), "Show me all users")

    assert query.sql == "SELECT id, name FROM Users"
    assert query.rows == result


def test_ask_rejects_write_statement_before_database_execution(monkeypatch):
    class FakeCursor:
        description = None

        def execute(self, _sql):
            raise AssertionError("invalid SQL must not reach the database")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakePool:
        def connection(self):
            return FakeConnection()

    monkeypatch.setattr(
        "nl_to_sql.generate_sql",
        lambda _question: "CREATE TABLE temporary_table (id integer);",
    )

    with pytest.raises(SQLValidationError, match="Only SELECT"):
        ask(FakePool(), "Create something")


def test_ask_rejects_cannot_answer_before_database_execution(monkeypatch):
    class FakePool:
        def connection(self):
            raise AssertionError("database must not be opened")

    monkeypatch.setattr(
        "nl_to_sql.generate_sql",
        lambda _question: "CANNOT_ANSWER",
    )

    with pytest.raises(SQLValidationError, match="could not answer"):
        ask(FakePool(), "Ask something unsupported")

def test_model_names_can_be_overridden_from_environment(monkeypatch):
    calls = []

    def generate_content(model, contents):
        calls.append(model)
        if model == "custom-primary":
            raise FakeServerError(503)
        return FakeResponse("SELECT id FROM Users;")

    _install_fake_genai(monkeypatch, generate_content)
    monkeypatch.setenv("GEMINI_PRIMARY_MODEL", "custom-primary")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "custom-fallback")
    from nl_to_sql import generate_sql

    assert generate_sql("Show me the users") == "SELECT id FROM Users;"
    assert calls == ["custom-primary", "custom-fallback"]


def test_blank_model_override_falls_back_to_default(monkeypatch):
    calls = []

    def generate_content(model, contents):
        calls.append(model)
        return FakeResponse("SELECT id FROM Users;")

    _install_fake_genai(monkeypatch, generate_content)
    # "GEMINI_PRIMARY_MODEL=" in .env loads as an empty string.
    monkeypatch.setenv("GEMINI_PRIMARY_MODEL", "")
    from nl_to_sql import generate_sql

    generate_sql("Show me the users")

    assert calls == ["gemini-flash-latest"]
