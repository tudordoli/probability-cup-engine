from __future__ import annotations


def decimal_odds_to_probability(decimal_odds: float) -> float:
    if decimal_odds <= 1:
        raise ValueError("Decimal odds must be greater than 1.")
    return 1.0 / decimal_odds


def american_odds_to_probability(american_odds: int) -> float:
    if american_odds == 0:
        raise ValueError("American odds cannot be zero.")
    if american_odds > 0:
        return 100.0 / (american_odds + 100.0)
    return abs(american_odds) / (abs(american_odds) + 100.0)


def remove_vig_two_way(prob_a: float, prob_b: float) -> tuple[float, float]:
    total = prob_a + prob_b
    if total <= 0:
        raise ValueError("Two-way probabilities must sum to a positive value.")
    return prob_a / total, prob_b / total


def remove_vig_three_way(prob_home: float, prob_draw: float, prob_away: float) -> tuple[float, float, float]:
    total = prob_home + prob_draw + prob_away
    if total <= 0:
        raise ValueError("Three-way probabilities must sum to a positive value.")
    return prob_home / total, prob_draw / total, prob_away / total

