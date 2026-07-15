from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from src.utils.logger import get_logger


@dataclass
class SportsPredictConfig:
    api_key: str
    base_url: str
    probability_event_title: str = "Probability Cup"
    timeout_seconds: int = 20


class SportsPredictClient:
    """Thin REST client for the documented SportsPredict Probability Cup API."""

    def __init__(self, config: SportsPredictConfig) -> None:
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        response = self.session.request(method, url, timeout=self.config.timeout_seconds, **kwargs)
        if not response.ok:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise requests.HTTPError(f"{method} {url} failed: {response.status_code} - {detail}")
        if not response.content:
            return None
        return response.json()

    def get_events(self) -> list[dict[str, Any]]:
        return self._request("GET", "/events")

    def get_probability_event(self) -> dict[str, Any]:
        events = self.get_events()
        for event in events:
            if event.get("title") == self.config.probability_event_title:
                return event
        for event in events:
            if self.config.probability_event_title.lower() in str(event.get("title", "")).lower():
                return event
        raise ValueError(f"Could not find event titled '{self.config.probability_event_title}'.")

    def get_lobbies(self, event_id: str) -> list[dict[str, Any]]:
        return self._request("GET", "/lobbies", params={"event_id": event_id})

    def ensure_lobby_joined(self, lobby_id: str) -> None:
        try:
            self._request("POST", f"/lobbies/{lobby_id}/join")
            self.logger.info("Joined lobby %s", lobby_id)
        except requests.HTTPError as error:
            if "409" in str(error):
                self.logger.info("Lobby %s already joined", lobby_id)
                return
            raise

    def get_matches(self, event_id: str, lobby_id: str | None = None) -> list[dict[str, Any]]:
        params = {"event_id": event_id}
        if lobby_id:
            params["lobby_id"] = lobby_id
        return self._request("GET", "/matches", params=params)

    def get_markets(self, lobby_id: str, match_id: str | None = None) -> list[dict[str, Any]]:
        params = {"lobby_id": lobby_id}
        if match_id:
            params["match_id"] = match_id
        return self._request("GET", "/markets", params=params)

    def get_open_questions(self) -> list[dict[str, Any]]:
        event = self.get_probability_event()
        lobbies = self.get_lobbies(event["id"])
        if not lobbies:
            raise ValueError("No lobbies returned for the Probability Cup event.")

        lobby = lobbies[0]
        if not lobby.get("joined", False):
            self.ensure_lobby_joined(lobby["id"])

        matches = self.get_matches(event["id"], lobby["id"])
        markets: list[dict[str, Any]] = []
        for match in matches:
            markets.extend(self.get_markets(lobby["id"], match["id"]))

        self.logger.info("Fetched %s open markets across %s matches", len(markets), len(matches))
        return markets

    def submit_prediction(self, market_id: str, lobby_id: str, probability: int) -> dict[str, Any]:
        payload = {"market_id": market_id, "lobby_id": lobby_id, "probability": probability}
        return self._request("POST", "/predictions", json=payload)

    def submit_predictions_batch(self, predictions: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {"predictions": predictions}
        return self._request("POST", "/predictions/batch", json=payload)

    def get_predictions(self, lobby_id: str | None = None) -> list[dict[str, Any]]:
        params = {"lobby_id": lobby_id} if lobby_id else None
        return self._request("GET", "/predictions", params=params)

    def get_results(self, lobby_id: str | None = None) -> list[dict[str, Any]]:
        params = {"lobby_id": lobby_id} if lobby_id else None
        return self._request("GET", "/results", params=params)

    def dry_run_submit(self, market_id: str, probability: int) -> dict[str, Any]:
        self.logger.info("Dry run only: would submit %s%% to market %s", probability, market_id)
        return {"market_id": market_id, "probability": probability, "submitted": False, "mode": "dry-run"}
