from src.api.odds_client import OddsClient, OddsClientConfig


def build_client() -> OddsClient:
    return OddsClient(
        OddsClientConfig(
            provider="manual",
            api_key=None,
            base_url=None,
            sport_key="soccer_fifa_world_cup",
            regions="eu",
            markets="h2h,totals",
            odds_format="decimal",
            bookmaker="manual",
            manual_odds_path="data/manual_odds.csv",
            team_aliases_path="data/team_aliases.csv",
        )
    )


def test_manual_odds_validation_passes() -> None:
    client = build_client()
    assert client.validate_manual_odds() == []


def test_manual_odds_loads_rows() -> None:
    client = build_client()
    rows = client.get_manual_odds()
    assert rows
    assert any(row["market_type"] == "player_goal" for row in rows)
