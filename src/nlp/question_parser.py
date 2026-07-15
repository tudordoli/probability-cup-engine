from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from src.nlp.team_matcher import TeamMatcher
from src.utils.helpers import normalize_text


@dataclass
class ParsedQuestion:
    home_team: str | None
    away_team: str | None
    player_name: str | None
    target_team: str | None
    market_type: str | None
    threshold: float | None
    period: str
    raw_question: str
    match_name: str | None
    comparator: str | None = None
    status: str = "PARSED"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SUPPORTED_TYPES = {
    "match_winner",
    "team_advance",
    "total_goals_over",
    "total_goals_under",
    "team_score_at_least_1",
    "first_team_to_score",
    "player_goal",
    "player_shot_on_target",
    "team_shots_on_target",
    "total_corners",
    "team_corners",
    "cards",
    "penalty_or_red_card",
    "halftime_tied",
    "halftime_team_leading",
}


def _extract_period(question: str) -> str:
    normalized = normalize_text(question)
    if "first half" in normalized or "at halftime" in normalized:
        return "first_half"
    if "second half" in normalized:
        return "second_half"
    if "extra time" in normalized:
        return "extra_time"
    if "regulation" in normalized or "90 minutes" in normalized:
        return "regulation"
    return "full_match"


def _extract_threshold(question: str) -> tuple[float | None, str | None]:
    lowered = normalize_text(question)
    match = re.search(r"(\d+(?:\.\d+)?)\s+or\s+more", lowered)
    if match:
        return float(match.group(1)), "at_least"
    match = re.search(r"(\d+(?:\.\d+)?)\s+or\s+fewer", lowered)
    if match:
        return float(match.group(1)), "at_most"
    match = re.search(r"at least\s+(\d+(?:\.\d+)?)", lowered)
    if match:
        return float(match.group(1)), "at_least"
    match = re.search(r"(\d+(?:\.\d+)?)\s+or\s+less", lowered)
    if match:
        return float(match.group(1)), "at_most"
    return None, None


def _extract_player_name(question: str) -> str | None:
    patterns = [
        r"will\s+(.+?)\s+have at least",
        r"will\s+(.+?)\s+score a goal",
        r"will\s+(.+?)\s+score or assist",
    ]
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            player = re.sub(r"\s*\([^)]*\)", "", match.group(1)).strip()
            return player
    return None


def _find_target_team(question: str, teams: list[str]) -> str | None:
    normalized = normalize_text(question)
    for team in teams:
        if team and normalize_text(team) in normalized:
            return team
    return None


def parse_question(question: str, match_name: str | None, team_matcher: TeamMatcher) -> ParsedQuestion:
    home_team, away_team = team_matcher.split_match_name(match_name)
    teams = [team for team in (home_team, away_team) if team]
    normalized = normalize_text(question)
    threshold, comparator = _extract_threshold(question)
    period = _extract_period(question)
    player_name = _extract_player_name(question)
    target_team = _find_target_team(question, teams)
    market_type: str | None = None

    unsupported_markers = [
        "both teams score",
        "score or assist",
        "both teams have at least",
        "same number of goals",
        "substitute score",
        "more shots on target than",
        "more fouls than",
        "caught offside",
        "more cards than",
        "more goals than",
        "go to extra time",
        "first card of the match",
        "substitutions",
        "saves",
    ]

    if any(marker in normalized for marker in unsupported_markers):
        market_type = None

    elif "score or assist" in normalized:
        market_type = None
    elif "advance" in normalized or "to the quarterfinals" in normalized:
        market_type = "team_advance"
    elif (
        "win the match" in normalized
        or "win in regulation" in normalized
        or re.search(r"will .+ win the match", normalized)
    ):
        market_type = "match_winner"
    elif "score the first goal" in normalized:
        market_type = "first_team_to_score"
    elif "score at least 1 goal" in normalized or "score in the second half" in normalized:
        market_type = "team_score_at_least_1"
        if threshold is None:
            threshold = 1.0
            comparator = "at_least"
    elif "score a goal" in normalized:
        market_type = "player_goal"
    elif "shot on target" in normalized and player_name:
        market_type = "player_shot_on_target"
    elif "shots on target" in normalized and target_team:
        market_type = "team_shots_on_target"
    elif "corner" in normalized and target_team:
        market_type = "team_corners"
    elif "corner" in normalized:
        market_type = "total_corners"
    elif "cards" in normalized:
        market_type = "cards"
    elif "penalty kick" in normalized or "red card" in normalized:
        market_type = "penalty_or_red_card"
    elif ("at halftime" in normalized and "tied" in normalized) or "be tied at halftime" in normalized:
        market_type = "halftime_tied"
    elif "at halftime" in normalized and "winning" in normalized:
        market_type = "halftime_team_leading"
    elif "total goals" in normalized:
        if comparator == "at_most":
            market_type = "total_goals_under"
        else:
            market_type = "total_goals_over"

    parsed = ParsedQuestion(
        home_team=home_team,
        away_team=away_team,
        player_name=player_name,
        target_team=target_team,
        market_type=market_type,
        threshold=threshold,
        period=period,
        raw_question=question,
        match_name=match_name,
        comparator=comparator,
    )

    if parsed.market_type not in SUPPORTED_TYPES:
        parsed.status = "SKIPPED"
        parsed.reason = "unsupported question type"
    return parsed
