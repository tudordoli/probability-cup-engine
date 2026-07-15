from src.markets.market_mapper import MarketMappingResult
from src.nlp.question_parser import parse_question
from src.nlp.team_matcher import TeamMatcher
from run import compute_confidence_score


def matcher() -> TeamMatcher:
    return TeamMatcher("data/team_aliases.csv")


def test_confidence_score_high_for_direct_supported_market() -> None:
    parsed = parse_question(
        "Will England win the match?",
        "Panama vs England",
        matcher(),
    )
    mapped = MarketMappingResult(
        status="READY",
        reason="",
        source_market_used="match_winner",
        market_probability=0.62,
        matched_rows=[
            {"selection": "England"},
            {"selection": "Panama"},
            {"selection": "Draw"},
        ],
    )
    score, label = compute_confidence_score(parsed, mapped, 0.60, 0.61)
    assert score is not None
    assert score >= 75
    assert label == "HIGH"


def test_confidence_score_missing_market_is_none() -> None:
    parsed = parse_question(
        "Will Harry Kane have at least 1 shot on target?",
        "Panama vs England",
        matcher(),
    )
    mapped = MarketMappingResult(
        status="SKIPPED",
        reason="no matching betting market found",
        source_market_used=None,
        market_probability=None,
        matched_rows=[],
    )
    score, label = compute_confidence_score(parsed, mapped, None, None)
    assert score is None
    assert label == ""
