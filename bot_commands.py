"""Chat commands for SplitHelp, independent of any chat platform.

Money is only ever written by these deterministic commands (/add, /settle).
Free-text questions go to the LLM pipeline, which is read-only, so no model
output can create or change a financial record.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable

from netting import simplify_debts
from repositories.expense_repository import ExpensePayment, ExpenseSplit
from repositories.user_repository import User
from response_formatting import describe_balance, format_value
from splitting import CENTS, allocate_equal

NOT_AUTHORIZED_MESSAGE = (
    "Sorry, you're not set up to use this bot. Ask the group admin to add you."
)
ADD_USAGE = (
    "Usage: /add <amount> <description> [@name ...]\n"
    "Example: /add 900 Dinner @alex @priya\n"
    "With no names, the whole group splits it equally."
)
SETTLE_USAGE = "Usage: /settle @name <amount>\nExample: /settle @ishan 400"
HELP_TEXT = (
    "SplitHelp tracks shared expenses for your group.\n\n"
    f"{ADD_USAGE}\n\n"
    f"{SETTLE_USAGE}\n"
    "Records that you paid that person back.\n\n"
    "/balances: who owes whom, with suggested payments.\n\n"
    "Or just ask a question, e.g. \"How much did I spend on food?\""
)


class CommandError(ValueError):
    """Invalid user input; the message is safe to show to the user."""


@dataclass(frozen=True)
class AddCommand:
    amount: Decimal
    description: str
    names: list[str]


@dataclass(frozen=True)
class SettleCommand:
    name: str
    amount: Decimal


def parse_amount(text: str) -> Decimal:
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise CommandError(f"'{text}' is not a valid amount.") from None
    # NaN and Infinity parse as Decimals but are not money.
    if not amount.is_finite() or amount <= 0:
        raise CommandError("The amount must be a positive number.")
    if amount != amount.quantize(CENTS):
        raise CommandError("The amount can have at most two decimal places.")
    return amount


def _parse_name(token: str) -> str:
    name = token.removeprefix("@").strip().lower()
    if not name:
        raise CommandError("A name can't be empty.")
    return name


def parse_add(args: list[str]) -> AddCommand:
    if len(args) < 2:
        raise CommandError(ADD_USAGE)
    amount = parse_amount(args[0])
    words = [token for token in args[1:] if not token.startswith("@")]
    names = [_parse_name(token) for token in args[1:] if token.startswith("@")]
    if not words:
        raise CommandError(ADD_USAGE)
    if len(names) != len(set(names)):
        raise CommandError("Each person can only be listed once.")
    return AddCommand(amount, " ".join(words), names)


def parse_settle(args: list[str]) -> SettleCommand:
    if len(args) != 2:
        raise CommandError(SETTLE_USAGE)
    return SettleCommand(_parse_name(args[0]), parse_amount(args[1]))


def parse_telegram_users(value: str) -> dict[int, int]:
    """Parse "telegram_id:user_id,..." from config.

    This mapping is both the identity source ("I" in a question) and the
    allowlist: Telegram users not listed here can't use the bot.
    """
    mapping = {}
    for entry in filter(None, (part.strip() for part in value.split(","))):
        telegram_id, separator, user_id = entry.partition(":")
        if not separator:
            raise ValueError(f"Bad TELEGRAM_USERS entry {entry!r}; expected telegram_id:user_id")
        mapping[int(telegram_id)] = int(user_id)
    return mapping


def _with_usage(exc: CommandError, usage: str) -> str:
    message = str(exc)
    return message if message == usage else f"{message}\n\n{usage}"


class SplitHelpService:
    def __init__(
        self,
        users,
        groups,
        expenses,
        group_id: int,
        telegram_users: dict[int, int],
        answer_question: Callable[[str], str],
    ):
        self.users = users
        self.groups = groups
        self.expenses = expenses
        self.group_id = group_id
        self.telegram_users = telegram_users
        self.answer_question = answer_question

    def _sender_and_members(self, telegram_id: int) -> tuple[User | None, list[User]]:
        user_id = self.telegram_users.get(telegram_id)
        if user_id is None:
            return None, []
        members = self.groups.list_members(self.group_id)
        sender = next((member for member in members if member.id == user_id), None)
        return sender, members

    @staticmethod
    def _find_member(members: list[User], name: str) -> User:
        matches = [member for member in members if member.name.lower() == name]
        if not matches:
            raise CommandError(f"No one in the group is called '{name}'.")
        if len(matches) > 1:
            raise CommandError(f"More than one member is called '{name}'.")
        return matches[0]

    def add_expense(self, telegram_id: int, args: list[str]) -> str:
        sender, members = self._sender_and_members(telegram_id)
        if sender is None:
            return NOT_AUTHORIZED_MESSAGE
        try:
            command = parse_add(args)
            sharers = (
                [self._find_member(members, name) for name in command.names]
                if command.names
                else members
            )
        except CommandError as exc:
            return _with_usage(exc, ADD_USAGE)

        shares = allocate_equal(command.amount, [member.id for member in sharers])
        self.expenses.create_expense(
            self.group_id,
            command.description,
            [ExpensePayment(sender.id, command.amount)],
            [ExpenseSplit(user_id, "equal", share) for user_id, share in shares.items()],
        )
        names = {member.id: member.name for member in sharers}
        breakdown = ", ".join(
            f"{names[user_id]} {format_value(share)}" for user_id, share in shares.items()
        )
        return (
            f"Added {command.description}: {format_value(command.amount)} "
            f"paid by {sender.name}. Shares: {breakdown}."
        )

    def settle(self, telegram_id: int, args: list[str]) -> str:
        sender, members = self._sender_and_members(telegram_id)
        if sender is None:
            return NOT_AUTHORIZED_MESSAGE
        try:
            command = parse_settle(args)
            recipient = self._find_member(members, command.name)
        except CommandError as exc:
            return _with_usage(exc, SETTLE_USAGE)
        if recipient.id == sender.id:
            return "You can't settle up with yourself."

        # Stored as an expense the sender paid and the recipient "owes":
        # sender's balance rises by the amount, recipient's falls by it, and
        # payments == splits, so the balance trigger accepts it unchanged.
        self.expenses.create_expense(
            self.group_id,
            f"Settlement: {sender.name} paid {recipient.name}",
            [ExpensePayment(sender.id, command.amount)],
            [ExpenseSplit(recipient.id, "exact", command.amount)],
        )
        return f"Recorded: {sender.name} paid {recipient.name} {format_value(command.amount)}."

    def balances(self, telegram_id: int) -> str:
        sender, members = self._sender_and_members(telegram_id)
        if sender is None:
            return NOT_AUTHORIZED_MESSAGE

        balances = self.expenses.get_group_balances(self.group_id)
        names = {member.id: member.name for member in members}
        lines = [
            f"{member.name} {describe_balance(balances.get(member.id, Decimal('0')))}"
            for member in sorted(members, key=lambda member: member.name.lower())
        ]
        payments = simplify_debts(balances)
        if payments:
            lines.append("\nSuggested payments:")
            lines.extend(
                f"{names.get(p.payer_id, p.payer_id)} pays "
                f"{names.get(p.payee_id, p.payee_id)} {format_value(p.amount)}"
                for p in payments
            )
        else:
            lines.append("\nNothing to settle.")
        return "\n".join(lines)

    def ask(self, telegram_id: int, question: str) -> str:
        sender, _ = self._sender_and_members(telegram_id)
        if sender is None:
            return NOT_AUTHORIZED_MESSAGE
        # Lets the SQL model resolve "I"/"me"/"my" to a real user. "user" and
        # "name" are deliberate: they are keywords of the users schema item,
        # so retrieval puts the Users table in the prompt.
        return self.answer_question(
            f'{question}\n(Asked by the user named {sender.name}; '
            f'"I", "me" and "my" mean the user named {sender.name}.)'
        )
