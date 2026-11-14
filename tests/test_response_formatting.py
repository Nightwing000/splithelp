from datetime import date, datetime
from decimal import Decimal

import psycopg
import pytest

from nl_to_sql import LLMUnavailableError
from response_formatting import (
    CANNOT_ANSWER_MESSAGE,
    LLM_UNAVAILABLE_MESSAGE,
    MAX_ROWS_FOR_LLM,
    NO_RESULTS_MESSAGE,
    REJECTED_QUERY_MESSAGE,
    TIMEOUT_MESSAGE,
    _format_value,
    answer,
    format_answer,
    format_error,
)
from sql_validation import CannotAnswerError, SQLValidationError, validate_read_only_sql


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1250"), "1250.00"),
        (Decimal("12.5"), "12.50"),
        (Decimal("416.6666666667"), "416.67"),
        # Half rounds away from zero, matching Postgres ROUND().
        (Decimal("0.125"), "0.13"),
        (Decimal("-0.125"), "-0.13"),
        (datetime(2026, 11, 3, 14, 5, 33), "2026-11-03 14:05"),
        (date(2026, 11, 3), "2026-11-03"),
        (None, "none"),
        (3, "3"),
        ("Ishan", "Ishan"),
    ],
)
def test_format_value(value, expected):
    assert _format_value(value) == expected


@pytest.mark.parametrize("rows", [[], None])
def test_format_answer_reports_no_results(rows):
    assert format_answer("Who owes money?", rows) == NO_RESULTS_MESSAGE


def test_format_answer_formats_single_value():
    rows = [{"total_paid": Decimal("1250")}]

    assert format_answer("How much has Ishan paid?", rows) == "total_paid: 1250.00"


BALANCE_ROWS = [
    {"name": "Ishan", "net_balance": Decimal("1250")},
    {"name": "Alex", "net_balance": Decimal("-1250")},
]


def _fake_llm(monkeypatch, reply):
    prompts = []

    def generate_text(prompt):
        prompts.append(prompt)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr("response_formatting.generate_text", generate_text)
    return prompts


def test_format_answer_phrases_multi_row_results(monkeypatch):
    prompts = _fake_llm(monkeypatch, "Ishan is owed 1,250.00 and Alex owes 1250.00 in group 1.")

    answer = format_answer("Who owes money in group 1?", BALANCE_ROWS)

    assert answer == "Ishan is owed 1,250.00 and Alex owes 1250.00 in group 1."
    assert "name: Ishan, net_balance: 1250.00" in prompts[0]
    assert "Who owes money in group 1?" in prompts[0]


def test_format_answer_rejects_invented_numbers(monkeypatch):
    # 2500.00 is a sum the model computed; it appears nowhere in the rows.
    _fake_llm(monkeypatch, "In total 2500.00 changed hands.")

    answer = format_answer("Who owes money?", BALANCE_ROWS)

    assert answer == (
        "name: Ishan, net_balance: 1250.00\n"
        "name: Alex, net_balance: -1250.00"
    )


def test_format_answer_falls_back_when_llm_fails(monkeypatch):
    _fake_llm(monkeypatch, RuntimeError("quota exhausted"))

    answer = format_answer("Who owes money?", BALANCE_ROWS)

    assert answer.startswith("name: Ishan, net_balance: 1250.00")


def test_format_answer_falls_back_on_empty_llm_reply(monkeypatch):
    _fake_llm(monkeypatch, "   ")

    assert format_answer("Who owes money?", BALANCE_ROWS).startswith("name: Ishan")


def test_format_answer_skips_llm_for_large_results(monkeypatch):
    prompts = _fake_llm(monkeypatch, "unused")
    rows = [{"id": i, "name": f"user{i}"} for i in range(MAX_ROWS_FOR_LLM + 1)]

    answer = format_answer("List users", rows)

    assert prompts == []
    assert len(answer.splitlines()) == MAX_ROWS_FOR_LLM + 1


def test_format_error_for_cannot_answer():
    with pytest.raises(CannotAnswerError) as exc_info:
        validate_read_only_sql("CANNOT_ANSWER")

    assert format_error(exc_info.value) == CANNOT_ANSWER_MESSAGE


def test_format_error_hides_policy_details_but_logs_them(caplog):
    with pytest.raises(SQLValidationError) as exc_info:
        validate_read_only_sql("SELECT pg_sleep(5);")

    message = format_error(exc_info.value)

    assert message == REJECTED_QUERY_MESSAGE
    assert "PG_SLEEP" not in message
    assert "PG_SLEEP" in caplog.text


def _fake_ask(monkeypatch, result):
    def ask(_pool, _question):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("response_formatting.ask", ask)


def test_answer_formats_rows(monkeypatch):
    _fake_ask(monkeypatch, [{"total_paid": Decimal("1250")}])

    assert answer(object(), "How much has Ishan paid?") == "total_paid: 1250.00"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (SQLValidationError("Function 'PG_SLEEP' is not approved."), REJECTED_QUERY_MESSAGE),
        (CannotAnswerError("could not answer"), CANNOT_ANSWER_MESSAGE),
        (psycopg.errors.QueryCanceled("canceling statement due to statement timeout"), TIMEOUT_MESSAGE),
        (LLMUnavailableError("Gemini request failed"), LLM_UNAVAILABLE_MESSAGE),
    ],
)
def test_answer_turns_failures_into_user_messages(monkeypatch, error, expected):
    _fake_ask(monkeypatch, error)

    assert answer(object(), "Who owes money?") == expected


def test_answer_does_not_hide_unexpected_errors(monkeypatch):
    _fake_ask(monkeypatch, KeyError("GEMINI_API_KEY"))

    with pytest.raises(KeyError):
        answer(object(), "Who owes money?")
