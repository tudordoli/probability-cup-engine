from __future__ import annotations

from src.utils.helpers import clamp


def combine_probabilities(
    market_prob: float | None,
    model_prob: float | None,
    news_adjusted_prob: float | None,
    market_weight: float = 0.80,
    model_weight: float = 0.15,
    news_weight: float = 0.05,
) -> tuple[int | None, str]:
    """
    Returns an integer 1-99 probability plus a status reason.
    SportsPredict expects integer percentages on submission.
    """
    if market_prob is None:
        return None, "missing market anchor"

    if news_adjusted_prob is None:
        news_adjusted_prob = market_prob

    if model_prob is None:
        final = 0.95 * market_prob + 0.05 * news_adjusted_prob
    else:
        final = (
            market_weight * market_prob
            + model_weight * model_prob
            + news_weight * news_adjusted_prob
        )

    final = clamp(final, 0.01, 0.99)
    return int(round(final * 100)), ""

