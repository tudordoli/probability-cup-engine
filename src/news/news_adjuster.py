from __future__ import annotations

from src.utils.helpers import clamp


def adjust_for_news(
    base_probability: float,
    parsed_question: dict | object,
    news_notes: dict | None = None,
) -> tuple[float, float]:
    if not news_notes:
        return base_probability, 0.0
    match_name = (
        getattr(parsed_question, "match_name", None)
        if not isinstance(parsed_question, dict)
        else parsed_question.get("match_name")
    )
    adjustment = float(news_notes.get(match_name, 0.0)) if match_name else 0.0
    adjustment = clamp(adjustment, -0.05, 0.05)
    adjusted = clamp(base_probability + adjustment, 0.01, 0.99)
    return adjusted, adjustment
