from run import build_coverage_diagnostics


def test_build_coverage_diagnostics_counts_direct_and_proxy() -> None:
    rows = [
        {
            "status": "READY",
            "reason": "",
            "parsed_market_type": "match_winner",
            "source_market_used": "match_winner",
        },
        {
            "status": "READY",
            "reason": "",
            "parsed_market_type": "team_score_at_least_1",
            "source_market_used": "team total goals over 0.5",
        },
        {
            "status": "SKIPPED",
            "reason": "unsupported question type",
            "parsed_market_type": None,
            "source_market_used": None,
        },
    ]
    diagnostics = build_coverage_diagnostics(rows)
    assert diagnostics["direct_matches"] == 1
    assert diagnostics["proxy_matches"] == 1
    assert diagnostics["by_status"]["READY"] == 2
    assert diagnostics["by_reason"]["unsupported question type"] == 1
