from datetime import date
from decimal import Decimal

import pytest

from bot_commands import (
    NOT_AUTHORIZED_MESSAGE,
    AddCommand,
    CommandError,
    SettleCommand,
    SplitHelpService,
    parse_add,
    parse_amount,
    parse_settle,
    parse_telegram_users,
)
from repositories.user_repository import User

GROUP_ID = 1
ISHAN = User(id=1, name="Ishan", email="ishan@example.com", created_at=None, deleted_at=None)
ALEX = User(id=2, name="Alex", email="alex@example.com", created_at=None, deleted_at=None)
PRIYA = User(id=3, name="Priya", email="priya@example.com", created_at=None, deleted_at=None)
OUTSIDER = User(id=9, name="Sam", email="sam@example.com", created_at=None, deleted_at=None)

# Telegram user id -> app user id. 999 is a stranger.
TELEGRAM_USERS = {111: ISHAN.id, 222: ALEX.id, 999_000: OUTSIDER.id}


# --- parsing -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [("900", Decimal("900")), ("33.34", Decimal("33.34")), ("0.01", Decimal("0.01"))],
)
def test_parse_amount_accepts_positive_cents(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", ["abc", "", "0", "-5", "10.005", "NaN", "Infinity", "1,250"])
def test_parse_amount_rejects_invalid(text):
    with pytest.raises(CommandError):
        parse_amount(text)


def test_parse_add_with_names():
    command = parse_add(["900", "Dinner", "at", "Thalassa", "@alex", "@Priya"])

    assert command == AddCommand(Decimal("900"), "Dinner at Thalassa", ["alex", "priya"])


def test_parse_add_without_names_means_whole_group():
    assert parse_add(["90", "Fuel"]) == AddCommand(Decimal("90"), "Fuel", [])


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["900"],  # no description
        ["@alex", "900", "Dinner"],  # amount must come first
        ["900", "Dinner", "@alex", "@ALEX"],  # same person twice
        ["900", "Dinner", "@"],  # empty name
    ],
)
def test_parse_add_rejects_bad_input(args):
    with pytest.raises(CommandError):
        parse_add(args)


@pytest.mark.parametrize("args", [["@alex", "400"], ["alex", "400"], ["@Alex", "400.00"]])
def test_parse_settle(args):
    assert parse_settle(args) == SettleCommand("alex", Decimal("400"))


@pytest.mark.parametrize("args", [[], ["@alex"], ["@alex", "400", "extra"], ["@alex", "lots"]])
def test_parse_settle_rejects_bad_input(args):
    with pytest.raises(CommandError):
        parse_settle(args)


def test_parse_telegram_users():
    assert parse_telegram_users("111:1, 222:2") == {111: 1, 222: 2}
    assert parse_telegram_users("") == {}


def test_parse_telegram_users_rejects_malformed_config():
    # A config mistake must fail at startup, not quietly lock everyone out.
    with pytest.raises(ValueError):
        parse_telegram_users("111-1")


# --- service fakes -------------------------------------------------------------


class FakeUsers:
    def get_by_id(self, user_id):
        return {u.id: u for u in (ISHAN, ALEX, PRIYA, OUTSIDER)}.get(user_id)


class FakeGroups:
    def list_members(self, group_id):
        assert group_id == GROUP_ID
        return [PRIYA, ISHAN, ALEX]  # deliberately unsorted


class FakeExpenses:
    def __init__(self, balances=None):
        self.created = []
        self.balances = balances or {}

    def create_expense(self, group_id, description, payments, splits, spent_on=None, merchant=None):
        assert group_id == GROUP_ID
        self.created.append((description, payments, splits))
        self.details = {"spent_on": spent_on, "merchant": merchant}

    def get_group_balances(self, group_id):
        return self.balances


def make_service(expenses=None, answer_question=None):
    return SplitHelpService(
        users=FakeUsers(),
        groups=FakeGroups(),
        expenses=expenses or FakeExpenses(),
        group_id=GROUP_ID,
        telegram_users=TELEGRAM_USERS,
        answer_question=answer_question or (lambda question: "answer"),
    )


# --- authorization -------------------------------------------------------------


@pytest.mark.parametrize("telegram_id", [999, 999_000])
def test_strangers_and_non_members_are_refused_everywhere(telegram_id):
    # 999 is unmapped; 999_000 maps to a real user who is not in the group.
    expenses = FakeExpenses()
    asked = []
    service = make_service(expenses, answer_question=asked.append)

    assert service.add_expense(telegram_id, ["90", "Fuel"]) == NOT_AUTHORIZED_MESSAGE
    assert service.settle(telegram_id, ["@alex", "10"]) == NOT_AUTHORIZED_MESSAGE
    assert service.balances(telegram_id) == NOT_AUTHORIZED_MESSAGE
    assert service.ask(telegram_id, "Who owes money?") == NOT_AUTHORIZED_MESSAGE
    assert expenses.created == []
    assert asked == []


# --- /add -----------------------------------------------------------------------


def test_add_splits_equally_across_whole_group_paid_by_sender():
    expenses = FakeExpenses()

    reply = make_service(expenses).add_expense(111, ["100", "Taxi"])

    description, payments, splits = expenses.created[0]
    assert description == "Taxi"
    assert [(p.user_id, p.amount) for p in payments] == [(ISHAN.id, Decimal("100"))]
    assert {s.user_id: s.amount_owed for s in splits} == {
        1: Decimal("33.34"),
        2: Decimal("33.33"),
        3: Decimal("33.33"),
    }
    assert all(s.split_type == "equal" for s in splits)
    assert sum(s.amount_owed for s in splits) == Decimal("100")
    assert "Taxi" in reply and "100.00" in reply


def test_add_splits_only_between_named_people_case_insensitively():
    expenses = FakeExpenses()

    make_service(expenses).add_expense(111, ["900", "Dinner", "@ALEX", "@priya"])

    _, payments, splits = expenses.created[0]
    assert payments[0].user_id == ISHAN.id  # the sender paid, but did not eat
    assert {s.user_id: s.amount_owed for s in splits} == {
        ALEX.id: Decimal("450.00"),
        PRIYA.id: Decimal("450.00"),
    }


def test_add_with_unknown_name_creates_nothing():
    expenses = FakeExpenses()

    reply = make_service(expenses).add_expense(111, ["900", "Dinner", "@bob"])

    assert "bob" in reply.lower()
    assert expenses.created == []


def test_add_with_bad_input_returns_usage_and_creates_nothing():
    expenses = FakeExpenses()

    reply = make_service(expenses).add_expense(111, ["lots", "Dinner"])

    assert "/add" in reply
    assert expenses.created == []


# --- /settle ----------------------------------------------------------------------


def test_settle_records_payment_that_moves_both_balances():
    expenses = FakeExpenses()

    reply = make_service(expenses).settle(222, ["@ishan", "400"])

    description, payments, splits = expenses.created[0]
    assert "Settlement" in description
    # Alex (payer) gains +400, Ishan (recipient) gets -400: Alex's debt and
    # Ishan's credit both shrink, and payments == splits for the trigger.
    assert [(p.user_id, p.amount) for p in payments] == [(ALEX.id, Decimal("400"))]
    assert [(s.user_id, s.split_type, s.amount_owed) for s in splits] == [
        (ISHAN.id, "exact", Decimal("400"))
    ]
    assert "Alex" in reply and "Ishan" in reply and "400.00" in reply


def test_cannot_settle_with_yourself():
    expenses = FakeExpenses()

    reply = make_service(expenses).settle(222, ["@alex", "400"])

    assert expenses.created == []
    assert "yourself" in reply.lower()


# --- /balances --------------------------------------------------------------------


def test_balances_are_described_in_words_with_suggested_payments():
    expenses = FakeExpenses(
        balances={1: Decimal("1766.66"), 2: Decimal("-433.33"), 3: Decimal("-1333.33")}
    )

    reply = make_service(expenses).balances(111)

    assert "Ishan is owed ₹1766.66" in reply
    assert "Alex owes ₹433.33" in reply
    assert "Priya owes ₹1333.33" in reply
    assert "Priya pays Ishan ₹1333.33" in reply
    assert "Alex pays Ishan ₹433.33" in reply
    assert "-" not in reply


def test_members_without_expenses_are_settled_up():
    reply = make_service(FakeExpenses(balances={})).balances(111)

    assert "Ishan is settled up" in reply
    assert "Nothing to settle" in reply


# --- free-text questions -----------------------------------------------------------


def test_questions_carry_the_askers_name_for_i_and_me():
    asked = []
    service = make_service(answer_question=lambda q: asked.append(q) or "You owe 433.33.")

    reply = service.ask(222, "How much do I owe?")

    assert reply == "You owe 433.33."
    assert "How much do I owe?" in asked[0]
    assert "Alex" in asked[0]


def test_identity_note_pulls_users_schema_into_retrieval():
    # Live test: "How much do I owe?" came back CANNOT_ANSWER because the
    # Users table never reached the SQL prompt, so the model couldn't
    # filter by the asker's name.
    from retrieval import retrieve_context

    asked = []
    make_service(answer_question=lambda q: asked.append(q) or "ok").ask(
        222, "How much do I owe in the Goa Trip group?"
    )

    assert "users" in [item["id"] for item in retrieve_context(asked[0])]



# --- sponsored parts, dates, merchants, currency ------------------------------


def test_parse_add_with_sponsored_part_date_and_merchant():
    command = parse_add(
        ["4000", "Fireworks", "+Ishan:1080", "on:2026-11-08", "at:Cracker_Bazaar"]
    )

    assert command == AddCommand(
        Decimal("4000"),
        "Fireworks",
        [],
        extras={"ishan": Decimal("1080")},
        spent_on=date(2026, 11, 8),
        merchant="Cracker Bazaar",
    )


def test_parse_add_defaults_have_no_extras_date_or_merchant():
    command = parse_add(["90", "Fuel"])

    assert command.extras == {}
    assert command.spent_on is None
    assert command.merchant is None


@pytest.mark.parametrize(
    "args",
    [
        ["4000", "Fireworks", "+ishan"],  # no amount
        ["4000", "Fireworks", "+ishan:lots"],  # bad amount
        ["4000", "Fireworks", "+:100"],  # no name
        ["4000", "Fireworks", "+ishan:100", "+ishan:200"],  # same sponsor twice
        ["1000", "Fireworks", "+ishan:1080"],  # sponsored part exceeds the bill
        ["4000", "Fireworks", "on:2026-13-40"],  # not a date
        ["4000", "Fireworks", "on:2026-11-08", "on:2026-11-09"],  # two dates
        ["4000", "Fireworks", "at:"],  # empty merchant
    ],
)
def test_parse_add_rejects_bad_extras_dates_and_merchants(args):
    with pytest.raises(CommandError):
        parse_add(args)


def test_add_sponsored_part_goes_only_to_sponsor_rest_split_equally():
    # The Diwali Crackers bill, in a 3-person group: Ishan sponsors 1080 of
    # sky shots alone; the remaining 2920 is split equally.
    expenses = FakeExpenses()

    reply = make_service(expenses).add_expense(
        111, ["4000", "Fireworks", "+ishan:1080", "on:2026-11-08", "at:Cracker_Bazaar"]
    )

    _, payments, splits = expenses.created[0]
    assert [(p.user_id, p.amount) for p in payments] == [(ISHAN.id, Decimal("4000"))]
    assert {s.user_id: s.amount_owed for s in splits} == {
        ISHAN.id: Decimal("2053.34"),  # 1080 + 973.34
        ALEX.id: Decimal("973.33"),
        PRIYA.id: Decimal("973.33"),
    }
    # Mixed rule: amount_owed stores the resolved amount, typed 'exact'.
    assert all(s.split_type == "exact" for s in splits)
    assert sum(s.amount_owed for s in splits) == Decimal("4000")
    assert expenses.details == {"spent_on": date(2026, 11, 8), "merchant": "Cracker Bazaar"}
    assert "₹4000.00" in reply
    assert "Cracker Bazaar" in reply


def test_add_fully_sponsored_bill_has_no_equal_part():
    expenses = FakeExpenses()

    make_service(expenses).add_expense(111, ["1080", "Sky", "shots", "+ishan:1080"])

    _, _, splits = expenses.created[0]
    assert [(s.user_id, s.amount_owed) for s in splits] == [(ISHAN.id, Decimal("1080"))]


def test_sponsor_can_be_outside_the_named_sharers():
    expenses = FakeExpenses()

    make_service(expenses).add_expense(111, ["300", "Snacks", "@alex", "@priya", "+ishan:100"])

    _, _, splits = expenses.created[0]
    assert {s.user_id: s.amount_owed for s in splits} == {
        ISHAN.id: Decimal("100"),
        ALEX.id: Decimal("100.00"),
        PRIYA.id: Decimal("100.00"),
    }


def test_add_with_unknown_sponsor_creates_nothing():
    expenses = FakeExpenses()

    reply = make_service(expenses).add_expense(111, ["4000", "Fireworks", "+bob:1080"])

    assert "bob" in reply.lower()
    assert expenses.created == []


def test_plain_add_still_uses_equal_split_type():
    expenses = FakeExpenses()

    make_service(expenses).add_expense(111, ["90", "Fuel"])

    _, _, splits = expenses.created[0]
    assert all(s.split_type == "equal" for s in splits)
    assert expenses.details == {"spent_on": None, "merchant": None}


def test_settle_reply_shows_currency():
    reply = make_service().settle(222, ["@ishan", "400"])

    assert "₹400.00" in reply
