from __future__ import annotations

import random
from dataclasses import dataclass

from src.models.goals_model import _derive_expected_goals
from src.nlp.question_parser import ParsedQuestion


@dataclass
class MonteCarloResult:
    simulations: int
    home_lambda: float
    away_lambda: float
    estimated_probability: float | None
    supported: bool
    reason: str


def _poisson_sample(lam: float, rng: random.Random) -> int:
    """Knuth Poisson sampler. Fine here because football lambdas are small."""
    if lam <= 0:
        return 0

    threshold = pow(2.718281828459045, -lam)
    product = 1.0
    count = 0
    while product > threshold:
        count += 1
        product *= rng.random()
    return count - 1


def infer_match_lambdas(
    parsed: ParsedQuestion,
    match_rows: list[dict],
) -> tuple[float | None, float | None]:
    """Infer home and away expected goals from same-match odds rows."""
    _, home_lambda, away_lambda = _derive_expected_goals(parsed, match_rows)
    return home_lambda, away_lambda


def simulate_question_probability(
    parsed: ParsedQuestion,
    match_rows: list[dict],
    simulations: int = 5000,
    seed: int = 7,
) -> MonteCarloResult:
    """
    Optional Monte Carlo estimator for scoreline-driven question types.

    Useful for:
    - match_winner
    - total_goals_over / total_goals_under
    - team_score_at_least_1
    - first_team_to_score
    - halftime_tied
    """
    home_lambda, away_lambda = infer_match_lambdas(parsed, match_rows)
    if home_lambda is None or away_lambda is None:
        return MonteCarloResult(
            simulations=simulations,
            home_lambda=0.0,
            away_lambda=0.0,
            estimated_probability=None,
            supported=False,
            reason="could not infer expected goals from match odds",
        )

    if parsed.market_type not in {
        "match_winner",
        "total_goals_over",
        "total_goals_under",
        "team_score_at_least_1",
        "first_team_to_score",
        "halftime_tied",
    }:
        return MonteCarloResult(
            simulations=simulations,
            home_lambda=home_lambda,
            away_lambda=away_lambda,
            estimated_probability=None,
            supported=False,
            reason="market type not supported by monte carlo module",
        )

    rng = random.Random(seed)
    hits = 0

    for _ in range(simulations):
        home_goals = _poisson_sample(home_lambda, rng)
        away_goals = _poisson_sample(away_lambda, rng)

        if parsed.market_type == "match_winner":
            if parsed.target_team == parsed.home_team and home_goals > away_goals:
                hits += 1
            elif parsed.target_team == parsed.away_team and away_goals > home_goals:
                hits += 1

        elif parsed.market_type == "total_goals_over" and parsed.threshold is not None:
            if home_goals + away_goals >= int(parsed.threshold):
                hits += 1

        elif parsed.market_type == "total_goals_under" and parsed.threshold is not None:
            if home_goals + away_goals <= int(parsed.threshold):
                hits += 1

        elif parsed.market_type == "team_score_at_least_1":
            if parsed.target_team == parsed.home_team and home_goals >= 1:
                hits += 1
            elif parsed.target_team == parsed.away_team and away_goals >= 1:
                hits += 1

        elif parsed.market_type == "first_team_to_score":
            # Approximate first scorer by comparing first-arrival times.
            if home_goals == 0 and away_goals == 0:
                continue
            home_first = rng.expovariate(home_lambda) if home_lambda > 0 else float("inf")
            away_first = rng.expovariate(away_lambda) if away_lambda > 0 else float("inf")
            if parsed.target_team == parsed.home_team and home_first < away_first:
                hits += 1
            elif parsed.target_team == parsed.away_team and away_first < home_first:
                hits += 1

        elif parsed.market_type == "halftime_tied":
            half_home = _poisson_sample(home_lambda / 2.0, rng)
            half_away = _poisson_sample(away_lambda / 2.0, rng)
            if half_home == half_away:
                hits += 1

    return MonteCarloResult(
        simulations=simulations,
        home_lambda=home_lambda,
        away_lambda=away_lambda,
        estimated_probability=hits / simulations,
        supported=True,
        reason="",
    )
