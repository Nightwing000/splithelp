from pathlib import Path
import sys
import types

from nl_to_sql import SCHEMA_PATH, _extract_sql, ask, build_prompt


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
    assert "Active users have deleted_at IS NULL." in prompt
    assert "Question: List active users." in prompt


def test_extract_sql_removes_sql_code_fence():
    text = "```sql\nSELECT id FROM Users;\n```"

    assert _extract_sql(text) == "SELECT id FROM Users;"


def test_extract_sql_strips_surrounding_whitespace_without_code_fence():
    text = "\n  SELECT id FROM Users;\n"

    assert _extract_sql(text) == "SELECT id FROM Users;"


def test_generate_sql_returns_clean_sql(monkeypatch):
    """Test generate_sql without making a real Gemini API request."""

    class FakeResponse:
        text = "```sql\nSELECT id, name FROM Users;\n```"

    class FakeModel:
        def generate_content(self, prompt):
            assert "Show me the users" in prompt
            return FakeResponse()

    fake_genai = types.ModuleType("google.generativeai")

    def configure(api_key):
        assert api_key == "fake-test-key"

    def generative_model(model_name):
        assert model_name == "gemini-flash-latest"
        return FakeModel()

    fake_genai.configure = configure
    fake_genai.GenerativeModel = generative_model

    fake_google = types.ModuleType("google")
    fake_google.generativeai = fake_genai

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda: None

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")

    from nl_to_sql import generate_sql

    result = generate_sql("Show me the users")

    assert result == "SELECT id, name FROM Users;"
    assert "```" not in result


def test_ask_returns_rows_as_dictionaries(monkeypatch):
    class FakeCursor:
        description = [("id",), ("name",)]

        def execute(self, sql):
            assert sql == "SELECT id, name FROM Users;"

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


def test_ask_returns_none_for_statement_without_result_rows(monkeypatch):
    class FakeCursor:
        description = None

        def execute(self, _sql):
            pass

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

    assert ask(FakePool(), "Create something") is None