"""The Telegram layer only routes messages to SplitHelpService and replies."""
import asyncio
from types import SimpleNamespace

from telegram.ext import CommandHandler, MessageHandler

from bot import ERROR_MESSAGE, build_application
from bot_commands import HELP_TEXT


class FakeService:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def _record(self, name, *args):
        self.calls.append((name, *args))
        if self.fail:
            raise RuntimeError("database exploded")
        return f"{name} reply"

    def add_expense(self, telegram_id, args):
        return self._record("add", telegram_id, args)

    def settle(self, telegram_id, args):
        return self._record("settle", telegram_id, args)

    def balances(self, telegram_id):
        return self._record("balances", telegram_id)

    def ask(self, telegram_id, question):
        return self._record("ask", telegram_id, question)


def _handlers(app):
    return [handler for group in app.handlers.values() for handler in group]


def _command_callback(app, command):
    for handler in _handlers(app):
        if isinstance(handler, CommandHandler) and command in handler.commands:
            return handler.callback
    raise AssertionError(f"no handler for /{command}")


def _text_callback(app):
    for handler in _handlers(app):
        if isinstance(handler, MessageHandler):
            return handler.callback
    raise AssertionError("no free-text handler")


def _invoke(callback, telegram_id=111, args=None, text=""):
    replies = []

    async def reply_text(message):
        replies.append(message)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=telegram_id),
        effective_message=SimpleNamespace(text=text, reply_text=reply_text),
    )
    context = SimpleNamespace(args=args)
    # Not asyncio.run(): on Python 3.9 it unsets the default event loop when
    # done, and the next Application.builder().build() then fails.
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(callback(update, context))
    finally:
        loop.close()
    return replies


def test_all_commands_are_registered():
    app = build_application("123456:TEST-TOKEN", FakeService())

    commands = set()
    for handler in _handlers(app):
        if isinstance(handler, CommandHandler):
            commands |= handler.commands

    assert commands == {"start", "help", "add", "settle", "balances"}


def test_help_replies_with_usage():
    app = build_application("123456:TEST-TOKEN", FakeService())

    assert _invoke(_command_callback(app, "help")) == [HELP_TEXT]


def test_add_passes_sender_and_arguments():
    service = FakeService()
    app = build_application("123456:TEST-TOKEN", service)

    replies = _invoke(_command_callback(app, "add"), telegram_id=222, args=["900", "Dinner"])

    assert service.calls == [("add", 222, ["900", "Dinner"])]
    assert replies == ["add reply"]


def test_settle_and_balances_are_routed():
    service = FakeService()
    app = build_application("123456:TEST-TOKEN", service)

    _invoke(_command_callback(app, "settle"), args=["@ishan", "400"])
    _invoke(_command_callback(app, "balances"))

    assert service.calls == [("settle", 111, ["@ishan", "400"]), ("balances", 111)]


def test_missing_args_are_passed_as_empty_list():
    service = FakeService()
    app = build_application("123456:TEST-TOKEN", service)

    _invoke(_command_callback(app, "add"), args=None)

    assert service.calls == [("add", 111, [])]


def test_free_text_goes_to_ask():
    service = FakeService()
    app = build_application("123456:TEST-TOKEN", service)

    replies = _invoke(_text_callback(app), text="Who owes money?")

    assert service.calls == [("ask", 111, "Who owes money?")]
    assert replies == ["ask reply"]


def test_unexpected_errors_reply_politely_and_are_logged(caplog):
    app = build_application("123456:TEST-TOKEN", FakeService(fail=True))

    replies = _invoke(_command_callback(app, "add"), args=["900", "Dinner"])

    assert replies == [ERROR_MESSAGE]
    assert "database exploded" in caplog.text
