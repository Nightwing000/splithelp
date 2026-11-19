from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from knowledge_base import ALL_KNOWLEDGE, KnowledgeItem


STOP_WORDS = {
    "a", "an", "and", "are", "for", "from", "how", "in", "is",
    "of", "on", "or", "the", "this", "to", "what", "who",
}

SYNONYMS = {
    "account": "user",
    "accounts": "user",
    "amounts": "amount",
    "belong": "member",
    "belongs": "member",
    "covered": "pay",
    "contributed": "pay",
    "contribution": "pay",
    "contributions": "pay",
    "owed": "owe",
    "owes": "owe",
    "owing": "owe",
    "paid": "pay",
    "payer": "pay",
    "payers": "pay",
    "payments": "payment",
    "people": "user",
    "person": "user",
    "participants": "member",
    "spent": "pay",
    "users": "user",
}


@dataclass(frozen=True)
class RetrievalMatch:
    item: KnowledgeItem
    score: int
    matched_keywords: frozenset[str]


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9_]+", text.lower()))
    return {SYNONYMS.get(token, token) for token in tokens - STOP_WORDS}


def _score(question: str, item: KnowledgeItem) -> RetrievalMatch:
    question_tokens = _tokenize(question)
    keyword_tokens = _tokenize(" ".join(item["keywords"]))
    content_tokens = _tokenize(item["content"])
    keyword_matches = question_tokens & keyword_tokens
    content_matches = question_tokens & content_tokens
    return RetrievalMatch(
        item=item,
        score=(3 * len(keyword_matches)) + len(content_matches),
        matched_keywords=frozenset(keyword_matches),
    )


def retrieve_scored(
    question: str,
    items: Sequence[KnowledgeItem] = ALL_KNOWLEDGE,
    top_k: int = 5,
    kind: str | None = None,
) -> list[RetrievalMatch]:
    if top_k < 0:
        raise ValueError("top_k must be non-negative")

    scored_items = [
        (index, _score(question, item))
        for index, item in enumerate(items)
        if kind is None or item["kind"] == kind
    ]
    matching_items = [
        (index, match)
        for index, match in scored_items
        if match.score > 0
    ]
    matching_items.sort(key=lambda result: (-result[1].score, result[0]))

    return [match for _, match in matching_items[:top_k]]


def retrieve(
    question: str,
    items: Sequence[KnowledgeItem] = ALL_KNOWLEDGE,
    top_k: int = 5,
    kind: str | None = None,
) -> list[KnowledgeItem]:
    return [
        match.item
        for match in retrieve_scored(question, items, top_k, kind)
    ]


def retrieve_context(
    question: str,
    items: Sequence[KnowledgeItem] = ALL_KNOWLEDGE,
    schema_limit: int | None = None,
    rule_limit: int = 4,
    example_limit: int = 2,
) -> list[KnowledgeItem]:
    """Retrieve prompt context for a question.

    schema_limit=None (the default) includes every schema item. The schema
    is six tables, and a ranked cut kept dropping tables a balance query
    needs (Expenses, ExpensePayments, GroupMembers), so the model answered
    CANNOT_ANSWER under the "use only tables in the context" rule. Rules and
    examples stay ranked and budgeted.
    """
    limits = {
        "schema": schema_limit,
        "rule": rule_limit,
        "example": example_limit,
    }
    if any(limit is not None and limit < 0 for limit in limits.values()):
        raise ValueError("context limits must be non-negative")

    context = []
    for kind, limit in limits.items():
        if limit is None:
            context.extend(item for item in items if item["kind"] == kind)
        else:
            context.extend(retrieve(question, items, top_k=limit, kind=kind))
    return context


def retrieve_context_scored(
    question: str,
    items: Sequence[KnowledgeItem] = ALL_KNOWLEDGE,
    schema_limit: int = 3,
    rule_limit: int = 4,
    example_limit: int = 2,
) -> list[RetrievalMatch]:
    limits = {
        "schema": schema_limit,
        "rule": rule_limit,
        "example": example_limit,
    }
    if any(limit < 0 for limit in limits.values()):
        raise ValueError("context limits must be non-negative")

    matches = []
    for kind, limit in limits.items():
        matches.extend(
            retrieve_scored(question, items, top_k=limit, kind=kind)
        )
    return matches
