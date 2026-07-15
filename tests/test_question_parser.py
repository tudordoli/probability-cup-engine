from src.nlp.question_parser import parse_question
from src.nlp.team_matcher import TeamMatcher


def matcher() -> TeamMatcher:
    return TeamMatcher("data/team_aliases.csv")


def test_parse_player_shot_on_target() -> None:
    parsed = parse_question(
        "Will Harry Kane have at least 1 shot on target?",
        "Panama vs England",
        matcher(),
    )
    assert parsed.market_type == "player_shot_on_target"
    assert parsed.player_name == "Harry Kane"
    assert parsed.period == "full_match"


def test_parse_total_goals_over() -> None:
    parsed = parse_question(
        "Will the match have 3 or more total goals?",
        "Panama vs England",
        matcher(),
    )
    assert parsed.market_type == "total_goals_over"
    assert parsed.threshold == 3


def test_parse_unsupported_question() -> None:
    parsed = parse_question(
        "Will both teams score AND the match have 3 or more total goals?",
        "DR Congo vs Uzbekistan",
        matcher(),
    )
    assert parsed.status == "SKIPPED"
    assert parsed.reason == "unsupported question type"


def test_parse_match_winner_in_regulation() -> None:
    parsed = parse_question(
        "Will Argentina win in regulation (90 minutes + stoppage time)?",
        "ARG vs EGY",
        matcher(),
    )
    assert parsed.market_type == "match_winner"
    assert parsed.period == "regulation"
