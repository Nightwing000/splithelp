from __future__ import annotations

import os
import re
from pathlib import Path
from collections.abc import Sequence

from psycopg_pool import ConnectionPool

from knowledge_base import KnowledgeItem
from retrieval import retrieve_context
from sql_validation import validate_read_only_sql

SCHEMA_PATH = Path(__file__).resolve().parent / "init" / "01_schema.sql"
ENV_PATH = Path(__file__).resolve().parent / ".env"
READ_ONLY_DB_USER = "splitter_readonly"
DATABASE_NAME = "expense_splitter"
PROMPT_INSTRUCTIONS = """You are a PostgreSQL expert generating SQL for an expense-splitting application.
Return exactly one read-only PostgreSQL statement and nothing else.
Use only tables, columns, and relationships present in the supplied context.
Do not invent schema elements.
Treat literal values in examples as placeholders and use values from the user's question.
If the question cannot be answered from the supplied context, return exactly CANNOT_ANSWER."""


def _load_schema() -> str:
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return f.read()


def _format_retrieved_context(items: Sequence[KnowledgeItem]) -> str:
    sections = []
    headings = {
        "schema": "Relevant schema",
        "rule": "Relevant business rules",
        "example": "Relevant SQL examples",
    }
    for kind, heading in headings.items():
        matching_items = [item for item in items if item["kind"] == kind]
        if matching_items:
            entries = [
                f"[{item['id']}]\n{item['content']}"
                for item in matching_items
            ]
            sections.append(f"{heading}:\n" + "\n\n".join(entries))
    return "\n\n".join(sections)


def build_prompt(
    question: str,
    context: Sequence[KnowledgeItem] | None = None,
) -> str:
    if not context:
        context_text = _load_schema()
        context_heading = "Schema"
    else:
        context_text = _format_retrieved_context(context)
        context_heading = "Relevant retrieved context"

    return f"""{PROMPT_INSTRUCTIONS}

{context_heading}:
{context_text}

Question: {question}

SQL:"""


def _extract_sql(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(sql)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def generate_sql(question: str) -> str:
    from google import genai
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ENV_PATH)
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    context = retrieve_context(question)
    prompt = build_prompt(question, context)
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt,
    )
    return _extract_sql(response.text)


def get_read_only_pool() -> ConnectionPool:
    """Build the pool `ask()` should actually be called with.

    Connects as splitter_readonly, never the write-capable repository role --
    repository writes must keep using their own separately injected pool.
    """
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ENV_PATH)
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    password = os.environ["POSTGRES_READONLY_PASSWORD"]
    conninfo = (
        f"host={host} port={port} dbname={DATABASE_NAME} "
        f"user={READ_ONLY_DB_USER} password={password}"
    )
    return ConnectionPool(conninfo, open=True)


def ask(pool, question: str) -> list[dict] | None:
    sql = validate_read_only_sql(generate_sql(question))
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                return None
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return [dict(zip(columns, row)) for row in rows]
