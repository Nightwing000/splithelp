from __future__ import annotations

import os
import re
from pathlib import Path
from collections.abc import Sequence

from knowledge_base import KnowledgeItem
from retrieval import retrieve

SCHEMA_PATH = Path(__file__).resolve().parent / "init" / "01_schema.sql"


def _load_schema() -> str:
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return f.read()


def _format_retrieved_context(items: Sequence[KnowledgeItem]) -> str:
    sections = []
    for item in items:
        sections.append(f"[{item['kind']}: {item['id']}]\n{item['content']}")
    return "\n\n".join(sections)


def build_prompt(
    question: str,
    context: Sequence[KnowledgeItem] | None = None,
) -> str:
    if context is None:
        context_text = _load_schema()
        context_heading = "Schema"
    else:
        context_text = _format_retrieved_context(context)
        context_heading = "Relevant retrieved context"

    return f"""You are a PostgreSQL expert. Given the database context below, write a single SQL query that answers the user's question.
Return ONLY the SQL query. No explanation, no markdown code fences.

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
    import google.generativeai as genai
    from dotenv import load_dotenv

    load_dotenv()
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-flash-latest")
    context = retrieve(question)
    prompt = build_prompt(question, context) if context else build_prompt(question)
    response = model.generate_content(prompt)
    return _extract_sql(response.text)


def ask(pool, question: str) -> list[dict] | None:
    sql = generate_sql(question)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                return None
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return [dict(zip(columns, row)) for row in rows]
