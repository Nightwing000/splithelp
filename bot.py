"""Telegram front end for SplitHelp.

Run with: python bot.py
Needs TELEGRAM_BOT_TOKEN, TELEGRAM_USERS and SPLITHELP_GROUP_ID in .env
(see README). All logic lives in bot_commands.SplitHelpService; this module
only routes Telegram messages to it.
"""
from __future__ import annotations

import asyncio
import logging
import os

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot_commands import HELP_TEXT, SplitHelpService, parse_telegram_users

logger = logging.getLogger(__name__)

ERROR_MESSAGE = "Something went wrong on my side. Please try again in a moment."


async def _reply_with(update, function, *args) -> None:
    # The service does blocking database and Gemini calls; running them in a
    # thread keeps the bot responsive to other users meanwhile.
    try:
        reply = await asyncio.to_thread(function, *args)
    except Exception:
        logger.exception("Command failed for Telegram user %s", update.effective_user.id)
        reply = ERROR_MESSAGE
    await update.effective_message.reply_text(reply)


def build_application(token: str, service: SplitHelpService) -> Application:
    async def help_command(update, context):
        await update.effective_message.reply_text(HELP_TEXT)

    async def add_command(update, context):
        await _reply_with(update, service.add_expense, update.effective_user.id, context.args or [])

    async def settle_command(update, context):
        await _reply_with(update, service.settle, update.effective_user.id, context.args or [])

    async def balances_command(update, context):
        await _reply_with(update, service.balances, update.effective_user.id)

    async def question(update, context):
        await _reply_with(update, service.ask, update.effective_user.id, update.effective_message.text)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("settle", settle_command))
    app.add_handler(CommandHandler("balances", balances_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, question))
    return app


def _write_pool():
    from psycopg_pool import ConnectionPool

    # /add and /settle write money records, so they use the app role; the
    # LLM question path below gets the separate read-only pool.
    conninfo = (
        f"host={os.environ.get('POSTGRES_HOST', '127.0.0.1')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')} dbname=expense_splitter "
        f"user={os.environ.get('POSTGRES_ADMIN_USER', 'splitter_user')} "
        f"password={os.environ.get('POSTGRES_ADMIN_PASSWORD', 'devpassword')}"
    )
    return ConnectionPool(conninfo, open=True)


def main() -> None:
    from dotenv import load_dotenv

    from nl_to_sql import ENV_PATH, get_read_only_pool
    from repositories.expense_repository import ExpenseRepository
    from repositories.group_repository import GroupRepository
    from repositories.user_repository import UserRepository
    from response_formatting import answer

    load_dotenv(dotenv_path=ENV_PATH)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs every Telegram poll, and the URL contains the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    write_pool = _write_pool()
    read_only_pool = get_read_only_pool()
    service = SplitHelpService(
        users=UserRepository(write_pool),
        groups=GroupRepository(write_pool),
        expenses=ExpenseRepository(write_pool),
        group_id=int(os.environ["SPLITHELP_GROUP_ID"]),
        telegram_users=parse_telegram_users(os.environ.get("TELEGRAM_USERS", "")),
        answer_question=lambda question: answer(read_only_pool, question),
    )
    build_application(os.environ["TELEGRAM_BOT_TOKEN"], service).run_polling()


if __name__ == "__main__":
    main()
