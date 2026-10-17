from __future__ import annotations

import re
from collections.abc import Sequence

from knowledge_base import ALL_KNOWLEDGE, KnowledgeItem


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def _score(question: str, item: KnowledgeItem) -> int:
    question_tokens = _tokenize(question)
    keyword_tokens = _tokenize(" ".join(item["keywords"]))
    return len(question_tokens & keyword_tokens)


def retrieve(
    question: str,
    items: Sequence[KnowledgeItem] = ALL_KNOWLEDGE,
    top_k: int = 5,
    kind: str | None = None,
) -> list[KnowledgeItem]:
    if top_k < 0:
        raise ValueError("top_k must be non-negative")

    scored_items = [
        (index, item, _score(question, item))
        for index, item in enumerate(items)
        if kind is None or item["kind"] == kind
    ]
    matching_items = [
        (index, item, score)
        for index, item, score in scored_items
        if score > 0
    ]
    matching_items.sort(key=lambda result: (-result[2], result[0]))

    return [item for _, item, _ in matching_items[:top_k]]


def retrieve_context(
    question: str,
    items: Sequence[KnowledgeItem] = ALL_KNOWLEDGE,
    schema_limit: int = 2,
    rule_limit: int = 3,
    example_limit: int = 2,
) -> list[KnowledgeItem]:
    limits = {
        "schema": schema_limit,
        "rule": rule_limit,
        "example": example_limit,
    }
    if any(limit < 0 for limit in limits.values()):
        raise ValueError("context limits must be non-negative")

    context = []
    for kind, limit in limits.items():
        context.extend(retrieve(question, items, top_k=limit, kind=kind))
    return context
