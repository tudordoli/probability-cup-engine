from src.models.monte_carlo import simulate_question_probability
from src.nlp.question_parser import parse_question
from src.nlp.team_matcher import TeamMatcher


def matcher() -> TeamMatcher:
    return TeamMatcher("data/team_aliases.csv")


def sample_match_rows() -> list[dict]:
    return [
        {"match_name": "Panama vs England", "market_type": "match_winner", "selection": "Panama", "period": "full_match", "decimal_odds": 6.20},
        {"match_name": "Panama vs England", "market_type": "match_winner", "selection": "England", "period": "full_match", "decimal_odds": 1.55},
        {"match_name": "Panama vs England", "market_type": "match_winner", "selection": "Draw", "period": "full_match", "decimal_odds": 4.20},
        {"match_name": "Panama vs England", "market_type": "total_goals_over", "selection": "Over", "line": 2.5, "period": "full_match", "decimal_odds": 1.80},
        {"match_name": "Panama vs England", "market_type": "total_goals_under", "selection": "Under", "line": 2.5, "period": "full_match", "decimal_odds": 2.00},
    ]


def test_monte_carlo_total_goals_probability() -> None:
    parsed = parse_question(
        "Will the match have 3 or more total goals?",
        "Panama vs England",
        matcher(),
    )
    result = simulate_question_probability(parsed, sample_match_rows(), simulations=2000, seed=11)
    assert result.supported is True
    assert result.estimated_probability is not None
    assert 0.30 < result.estimated_probability < 0.75


def test_monte_carlo_rejects_unsupported_market() -> None:
    parsed = parse_question(
        "Will Bruno Fernandes have at least 1 shot on target?",
        "Portugal vs Spain",
        matcher(),
    )
    result = simulate_question_probability(parsed, sample_match_rows(), simulations=1000, seed=11)
    assert result.supported is False
    assert result.estimated_probability is None
