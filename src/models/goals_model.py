from __future__ import annotations

import math

from src.nlp.question_parser import ParsedQuestion
from src.utils.helpers import clamp, normalize_text


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def _poisson_cdf(k: int, lam: float) -> float:
    return sum(_poisson_pmf(i, lam) for i in range(k + 1))


def _fair_probability_from_rows(rows: list[dict]) -> dict[str, float]:
    priced_rows = [row for row in rows if row.get("decimal_odds")]
    raw_probs: list[tuple[str, float]] = []
    for row in priced_rows:
        raw_probs.append((str(row.get("selection", "")), 1.0 / float(row["decimal_odds"])))

    total = sum(prob for _, prob in raw_probs)
    if total <= 0:
        return {}
    return {selection: prob / total for selection, prob in raw_probs}


def _get_match_winner_probs(match_rows: list[dict]) -> dict[str, float]:
    winner_rows = [
        row
        for row in match_rows
        if normalize_text(row.get("market_type")) == "match_winner"
    ]
    return _fair_probability_from_rows(winner_rows)


def _find_total_goals_row(parsed: ParsedQuestion, match_rows: list[dict]) -> dict | None:
    expected_line = None
    if parsed.threshold is not None:
        if parsed.comparator == "at_least":
            expected_line = parsed.threshold - 0.5
        elif parsed.comparator == "at_most":
            expected_line = parsed.threshold + 0.5
        else:
            expected_line = parsed.threshold

    candidate_rows = [
        row
        for row in match_rows
        if normalize_text(row.get("market_type")) in {"total_goals_over", "total_goals_under"}
        and normalize_text(row.get("period")) in {normalize_text(parsed.period), "full match", "regulation"}
    ]
    if expected_line is None:
        return candidate_rows[0] if candidate_rows else None

    for row in candidate_rows:
        line = row.get("line")
        if line is not None and abs(float(line) - float(expected_line)) < 0.26:
            return row
    return None


def _infer_total_lambda(over_probability: float, goal_line: float) -> float:
    target_tail = clamp(over_probability, 0.02, 0.98)
    cutoff = max(int(math.floor(goal_line)), 0)
    low, high = 0.05, 6.0

    for _ in range(40):
        mid = (low + high) / 2
        tail_probability = 1 - _poisson_cdf(cutoff, mid)
        if tail_probability < target_tail:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _derive_expected_goals(
    parsed: ParsedQuestion,
    match_rows: list[dict],
) -> tuple[float | None, float | None, float | None]:
    total_row = _find_total_goals_row(parsed, match_rows)
    if not total_row or total_row.get("line") is None or not total_row.get("decimal_odds"):
        return None, None, None

    market_type = normalize_text(total_row.get("market_type"))
    market_prob = 1.0 / float(total_row["decimal_odds"])
    if market_type == "total_goals_under":
        market_prob = 1 - market_prob

    total_lambda = _infer_total_lambda(market_prob, float(total_row["line"]))

    winner_probs = _get_match_winner_probs(match_rows)
    home_team = parsed.home_team or ""
    away_team = parsed.away_team or ""
    home_prob = winner_probs.get(home_team, 0.45)
    away_prob = winner_probs.get(away_team, 0.35)
    non_draw_total = home_prob + away_prob
    if non_draw_total <= 0:
        home_share = 0.5
    else:
        home_share = clamp(home_prob / non_draw_total, 0.25, 0.75)

    home_lambda = total_lambda * home_share
    away_lambda = total_lambda - home_lambda
    return total_lambda, home_lambda, away_lambda


def estimate_goals_probability(
    parsed: ParsedQuestion,
    market_probability: float | None,
    match_rows: list[dict] | None = None,
) -> float | None:
    """Use a small Poisson-based secondary model derived from same-match odds."""
    if market_probability is None:
        return None

    match_rows = match_rows or []
    total_lambda, home_lambda, away_lambda = _derive_expected_goals(parsed, match_rows)

    if parsed.market_type == "team_score_at_least_1":
        if parsed.target_team == parsed.home_team and home_lambda is not None:
            return 1 - math.exp(-home_lambda)
        if parsed.target_team == parsed.away_team and away_lambda is not None:
            return 1 - math.exp(-away_lambda)
        return 1 - math.exp(-1.1)

    if parsed.market_type == "total_goals_over" and parsed.threshold and total_lambda is not None:
        cutoff = max(int(parsed.threshold) - 1, 0)
        return 1 - _poisson_cdf(cutoff, total_lambda)

    if parsed.market_type == "total_goals_under" and parsed.threshold is not None and total_lambda is not None:
        cutoff = int(parsed.threshold)
        return _poisson_cdf(cutoff, total_lambda)

    if parsed.market_type == "first_team_to_score" and home_lambda is not None and away_lambda is not None:
        total = home_lambda + away_lambda
        if total <= 0:
            return None
        no_goal_probability = math.exp(-total)
        if parsed.target_team == parsed.home_team:
            return (home_lambda / total) * (1 - no_goal_probability)
        if parsed.target_team == parsed.away_team:
            return (away_lambda / total) * (1 - no_goal_probability)

    if parsed.market_type == "player_goal":
        return min(0.75, market_probability * 0.95 + 0.02)

    return None
