from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from src.nlp.team_matcher import TeamMatcher
from src.utils.helpers import load_csv, normalize_text
from src.utils.logger import get_logger


@dataclass
class OddsClientConfig:
    provider: str
    api_key: str | None
    base_url: str | None
    sport_key: str
    regions: str
    markets: str
    odds_format: str
    bookmaker: str
    manual_odds_path: str
    team_aliases_path: str


class OddsClient:
    """CSV-first odds loader with optional The Odds API support."""

    REQUIRED_COLUMNS = {
        "match_name",
        "home_team",
        "away_team",
        "market_type",
        "selection",
        "line",
        "period",
        "decimal_odds",
        "american_odds",
        "bookmaker",
    }

    def __init__(self, config: OddsClientConfig) -> None:
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        self.session = requests.Session()
        self.team_matcher = TeamMatcher(config.team_aliases_path)

    def _match_name(self, home_team: str | None, away_team: str | None) -> str:
        if home_team and away_team:
            return f"{home_team} vs {away_team}"
        return ""

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        home_team = self.team_matcher.canonicalize(row.get("home_team") or "")
        away_team = self.team_matcher.canonicalize(row.get("away_team") or "")
        selection = row.get("selection") or ""
        return {
            "match_name": row.get("match_name") or row.get("match") or self._match_name(home_team, away_team),
            "home_team": home_team or "",
            "away_team": away_team or "",
            "market_type": row.get("market_type") or "",
            "selection": self.team_matcher.canonicalize(selection) or selection,
            "line": float(row["line"]) if row.get("line") not in (None, "", "null") else None,
            "period": row.get("period") or "full_match",
            "decimal_odds": float(row["decimal_odds"]) if row.get("decimal_odds") else None,
            "american_odds": int(row["american_odds"]) if row.get("american_odds") else None,
            "bookmaker": row.get("bookmaker") or self.config.bookmaker,
        }

    def validate_manual_odds(self) -> list[str]:
        rows = load_csv(self.config.manual_odds_path)
        errors: list[str] = []
        if not rows:
            errors.append("manual odds CSV is empty")
            return errors

        first_row_columns = set(rows[0].keys())
        missing_columns = self.REQUIRED_COLUMNS - first_row_columns
        if missing_columns:
            errors.append(f"missing columns: {', '.join(sorted(missing_columns))}")
            return errors

        for index, row in enumerate(rows, start=2):
            if not row.get("match_name"):
                errors.append(f"row {index}: match_name is required")
            if not row.get("market_type"):
                errors.append(f"row {index}: market_type is required")
            if not row.get("selection"):
                errors.append(f"row {index}: selection is required")
            if not row.get("period"):
                errors.append(f"row {index}: period is required")
            if not row.get("decimal_odds") and not row.get("american_odds"):
                errors.append(f"row {index}: provide decimal_odds or american_odds")
        return errors

    def get_manual_odds(self) -> list[dict[str, Any]]:
        rows = load_csv(self.config.manual_odds_path)
        normalized = [self._normalize_row(row) for row in rows]
        self.logger.info("Loaded %s manual odds rows from CSV", len(normalized))
        return normalized

    def _normalize_the_odds_api_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        home_team = self.team_matcher.canonicalize(event.get("home_team"))
        away_team = self.team_matcher.canonicalize(event.get("away_team"))
        match_name = self._match_name(home_team, away_team)

        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market.get("key") == "h2h":
                    for outcome in market.get("outcomes", []):
                        rows.append(
                            self._normalize_row(
                                {
                                    "match_name": match_name,
                                    "home_team": home_team,
                                    "away_team": away_team,
                                    "market_type": "match_winner",
                                    "selection": outcome.get("name"),
                                    "line": None,
                                    "period": "regulation",
                                    "decimal_odds": outcome.get("price"),
                                    "bookmaker": bookmaker.get("key"),
                                }
                            )
                        )
                elif market.get("key") == "totals":
                    for outcome in market.get("outcomes", []):
                        market_type = "total_goals_over" if normalize_text(outcome.get("name")) == "over" else "total_goals_under"
                        rows.append(
                            self._normalize_row(
                                {
                                    "match_name": match_name,
                                    "home_team": home_team,
                                    "away_team": away_team,
                                    "market_type": market_type,
                                    "selection": outcome.get("name"),
                                    "line": outcome.get("point"),
                                    "period": "regulation",
                                    "decimal_odds": outcome.get("price"),
                                    "bookmaker": bookmaker.get("key"),
                                }
                            )
                        )
        return rows

    def get_api_odds(self) -> list[dict[str, Any]]:
        if not self.config.api_key or not self.config.base_url:
            return []

        url = f"{self.config.base_url.rstrip('/')}/sports/{self.config.sport_key}/odds/"
        params = {
            "apiKey": self.config.api_key,
            "regions": self.config.regions,
            "markets": self.config.markets,
            "oddsFormat": self.config.odds_format,
        }
        if self.config.bookmaker:
            params["bookmakers"] = self.config.bookmaker

        response = self.session.get(url, params=params, timeout=20)
        response.raise_for_status()

        payload = response.json()
        normalized: list[dict[str, Any]] = []
        for event in payload if isinstance(payload, list) else []:
            normalized.extend(self._normalize_the_odds_api_event(event))

        self.logger.info("Loaded %s odds rows from The Odds API", len(normalized))
        return normalized

    def get_all_odds(self, use_api: bool = False) -> list[dict[str, Any]]:
        if use_api or self.config.provider == "the_odds_api":
            api_rows = self.get_api_odds()
            if api_rows:
                return api_rows
            self.logger.warning("API odds unavailable, falling back to manual CSV.")
        return self.get_manual_odds()

    def find_rows(
        self,
        rows: list[dict[str, Any]],
        match_name: str,
        market_type: str,
        period: str,
    ) -> list[dict[str, Any]]:
        home_team, away_team = self.team_matcher.split_match_name(match_name)
        canonical_match_name = self._match_name(home_team, away_team) if home_team and away_team else match_name
        match_key = normalize_text(canonical_match_name)
        market_key = normalize_text(market_type)
        period_key = normalize_text(period)
        allowed_periods = {period_key}
        if period_key in {"full match", "regulation"}:
            allowed_periods.update({"full match", "regulation"})

        return [
            row
            for row in rows
            if normalize_text(row.get("match_name")) == match_key
            and normalize_text(row.get("market_type")) == market_key
            and normalize_text(row.get("period")) in allowed_periods
        ]
