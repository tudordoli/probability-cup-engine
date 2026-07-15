from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.markets.odds_to_probability import (
    american_odds_to_probability,
    decimal_odds_to_probability,
    remove_vig_three_way,
    remove_vig_two_way,
)
from src.nlp.question_parser import ParsedQuestion
from src.utils.helpers import normalize_text


@dataclass
class MarketMappingResult:
    status: str
    reason: str
    source_market_used: str | None
    market_probability: float | None
    matched_rows: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _row_probability(row: dict[str, Any]) -> float | None:
    if row.get("decimal_odds"):
        return decimal_odds_to_probability(float(row["decimal_odds"]))
    if row.get("american_odds") is not None:
        return american_odds_to_probability(int(row["american_odds"]))
    return None


def _fair_probability(rows: list[dict[str, Any]], selection: str | None = None) -> float | None:
    if not rows:
        return None
    selected_rows = rows
    if selection:
        selected_rows = [row for row in rows if normalize_text(row.get("selection")) == normalize_text(selection)]
    if not selected_rows:
        return None

    target_row = selected_rows[0]
    target_prob = _row_probability(target_row)
    if target_prob is None:
        return None

    opposite_rows = [row for row in rows if row is not target_row]
    if len(rows) >= 3:
        priced_rows = rows[:3]
        probs = [_row_probability(row) for row in priced_rows]
        if all(prob is not None for prob in probs):
            fair_probs = remove_vig_three_way(probs[0], probs[1], probs[2])
            for row, fair_prob in zip(priced_rows, fair_probs):
                if row is target_row:
                    return fair_prob
    if opposite_rows:
        opposite_prob = _row_probability(opposite_rows[0])
        if opposite_prob is not None:
            fair, _ = remove_vig_two_way(target_prob, opposite_prob)
            return fair
    return target_prob


def _expected_line(parsed: ParsedQuestion) -> float | None:
    if parsed.threshold is None:
        return None
    if parsed.comparator == "at_least":
        return parsed.threshold - 0.5
    if parsed.comparator == "at_most":
        return parsed.threshold + 0.5
    return parsed.threshold


def _line_matches(parsed: ParsedQuestion, row: dict[str, Any]) -> bool:
    expected_line = _expected_line(parsed)
    line = row.get("line")
    if expected_line is None or line is None:
        return True
    return abs(float(line) - float(expected_line)) < 0.26


def map_question_to_market(parsed: ParsedQuestion, odds_rows: list[dict[str, Any]]) -> MarketMappingResult:
    if parsed.status == "SKIPPED" or not parsed.market_type:
        return MarketMappingResult("SKIPPED", parsed.reason or "unsupported question type", None, None, [])

    candidate_rows = [
        row
        for row in odds_rows
        if normalize_text(row.get("market_type")) == normalize_text(parsed.market_type)
        and normalize_text(row.get("period")) == normalize_text(parsed.period)
        and _line_matches(parsed, row)
    ]

    selection: str | None = None
    if parsed.market_type in {"match_winner", "team_advance", "first_team_to_score", "team_score_at_least_1", "team_shots_on_target", "team_corners", "halftime_team_leading"}:
        selection = parsed.target_team
    elif parsed.market_type in {"player_goal", "player_shot_on_target"}:
        selection = parsed.player_name
    elif parsed.market_type == "total_goals_over":
        selection = "over"
    elif parsed.market_type == "total_goals_under":
        selection = "under"

    if selection:
        scoped_rows = [row for row in candidate_rows if normalize_text(row.get("selection")) == normalize_text(selection)]
        if scoped_rows:
            candidate_rows = scoped_rows + [
                row
                for row in odds_rows
                if normalize_text(row.get("market_type")) == normalize_text(parsed.market_type)
                and normalize_text(row.get("period")) == normalize_text(parsed.period)
                and _line_matches(parsed, row)
                and normalize_text(row.get("selection")) != normalize_text(selection)
            ]

    probability = _fair_probability(candidate_rows, selection)
    if probability is None:
        return MarketMappingResult("SKIPPED", "no matching betting market found", None, None, candidate_rows)

    source = parsed.market_type
    if parsed.market_type == "team_score_at_least_1":
        source = "team total goals over 0.5"
    elif parsed.market_type == "player_goal":
        source = "anytime goalscorer"

    return MarketMappingResult("READY", "", source, probability, candidate_rows)
