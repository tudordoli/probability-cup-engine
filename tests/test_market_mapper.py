from src.markets.market_mapper import map_question_to_market
from src.nlp.question_parser import parse_question
from src.nlp.team_matcher import TeamMatcher
from src.utils.helpers import load_csv


def test_map_match_winner_market() -> None:
    matcher = TeamMatcher("data/team_aliases.csv")
    parsed = parse_question("Will England win the match?", "Panama vs England", matcher)
    odds_rows = load_csv("data/manual_odds.csv")
    mapped = map_question_to_market(parsed, [
        {
            "match_name": row["match_name"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "market_type": row["market_type"],
            "selection": row["selection"],
            "line": float(row["line"]) if row["line"] else None,
            "period": row["period"],
            "decimal_odds": float(row["decimal_odds"]) if row["decimal_odds"] else None,
            "american_odds": None,
            "bookmaker": row["bookmaker"],
        }
        for row in odds_rows
        if row["match_name"] == "Panama vs England"
    ])
    assert mapped.status == "READY"
    assert mapped.market_probability is not None


def test_skip_when_no_market_exists() -> None:
    matcher = TeamMatcher("data/team_aliases.csv")
    parsed = parse_question("At halftime, will Panama be winning?", "Panama vs England", matcher)
    mapped = map_question_to_market(parsed, [])
    assert mapped.status == "SKIPPED"
    assert mapped.reason == "no matching betting market found"

