from __future__ import annotations

from src.nlp.question_parser import ParsedQuestion


def estimate_corners_probability(parsed: ParsedQuestion, market_probability: float | None) -> float | None:
    if market_probability is None:
        return None
    if parsed.market_type in {"total_corners", "team_corners"}:
        return min(0.95, max(0.05, market_probability * 0.97 + 0.015))
    return None

