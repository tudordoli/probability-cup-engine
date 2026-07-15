from src.models.goals_model import estimate_goals_probability
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


def test_team_to_score_uses_expected_goals_split() -> None:
    parsed = parse_question(
        "Will Panama score at least 1 goal?",
        "Panama vs England",
        matcher(),
    )
    probability = estimate_goals_probability(parsed, 0.45, sample_match_rows())
    assert probability is not None
    assert 0.15 < probability < 0.75


def test_total_goals_over_uses_poisson_tail() -> None:
    parsed = parse_question(
        "Will the match have 3 or more total goals?",
        "Panama vs England",
        matcher(),
    )
    probability = estimate_goals_probability(parsed, 0.55, sample_match_rows())
    assert probability is not None
    assert 0.35 < probability < 0.75
