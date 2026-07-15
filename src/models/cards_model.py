from __future__ import annotations

from src.nlp.question_parser import ParsedQuestion


def estimate_cards_probability(parsed: ParsedQuestion, market_probability: float | None) -> float | None:
    if market_probability is None:
        return None
    if parsed.market_type in {"cards", "penalty_or_red_card"}:
        return min(0.90, max(0.05, market_probability * 0.96 + 0.02))
    return None

