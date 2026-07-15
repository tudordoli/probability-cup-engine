from __future__ import annotations

from src.nlp.question_parser import ParsedQuestion


def estimate_shots_probability(parsed: ParsedQuestion, market_probability: float | None) -> float | None:
    if market_probability is None:
        return None
    if parsed.market_type in {"player_shot_on_target", "team_shots_on_target"}:
        return min(0.95, max(0.05, market_probability * 0.98 + 0.01))
    return None

