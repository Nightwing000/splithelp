from __future__ import annotations

import os
import re

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

SCHEMA_PATH = "init/01_schema.sql"


def _load_schema() -> str:
    with open(SCHEMA_PATH, "r") as f:
        return f.read()


def build_prompt(question: str) -> str:
    schema = _load_schema()
    return f"""You are a PostgreSQL expert. Given the schema below, write a single SQL query that answers the user's question.
Return ONLY the SQL query. No explanation, no markdown code fences.

Schema:
{schema}

Question: {question}

SQL:"""


def _extract_sql(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(sql)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def generate_sql(question: str) -> str:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-flash-latest")
    response = model.generate_content(build_prompt(question))
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
