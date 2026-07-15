from src.markets.odds_to_probability import (
    american_odds_to_probability,
    decimal_odds_to_probability,
    remove_vig_three_way,
    remove_vig_two_way,
)


def test_decimal_odds_to_probability() -> None:
    assert round(decimal_odds_to_probability(2.0), 4) == 0.5


def test_american_odds_to_probability() -> None:
    assert round(american_odds_to_probability(-150), 4) == 0.6
    assert round(american_odds_to_probability(200), 4) == 0.3333


def test_remove_vig_two_way() -> None:
    fair_a, fair_b = remove_vig_two_way(0.55, 0.50)
    assert round(fair_a + fair_b, 8) == 1.0
    assert fair_a > fair_b


def test_remove_vig_three_way() -> None:
    home, draw, away = remove_vig_three_way(0.50, 0.30, 0.40)
    assert round(home + draw + away, 8) == 1.0

