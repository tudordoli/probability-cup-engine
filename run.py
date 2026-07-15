from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.odds_client import OddsClient, OddsClientConfig
from src.api.sportspredict_client import SportsPredictClient, SportsPredictConfig
from src.markets.market_mapper import map_question_to_market
from src.models.cards_model import estimate_cards_probability
from src.models.corners_model import estimate_corners_probability
from src.models.ensemble import combine_probabilities
from src.models.goals_model import estimate_goals_probability
from src.models.monte_carlo import simulate_question_probability
from src.models.shots_model import estimate_shots_probability
from src.news.news_adjuster import adjust_for_news
from src.nlp.question_parser import ParsedQuestion, parse_question
from src.nlp.team_matcher import TeamMatcher
from src.output.report_writer import render_terminal_table, write_prediction_report
from src.output.submission_writer import (
    build_submission_payload,
    write_submission_preview,
)
from src.utils.helpers import (
    chunked,
    clamp,
    load_env_file,
    load_json,
    load_yaml,
    write_json,
    write_csv,
    utc_timestamp_slug,
)
from src.utils.logger import get_logger

LOGGER = get_logger("run")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Forecast SportsPredict Probability Cup markets."
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Actually submit predictions to SportsPredict.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode.")
    parser.add_argument(
        "--questions-file",
        type=str,
        help="Optional local JSON file with sample questions.",
    )
    parser.add_argument(
        "--manual-odds", type=str, help="Optional path to manual odds CSV."
    )
    parser.add_argument(
        "--use-api-odds",
        action="store_true",
        help="Use The Odds API instead of the manual CSV.",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Evaluate settled SportsPredict results and write an evaluation summary.",
    )
    return parser.parse_args()


def load_project_config() -> dict[str, Any]:
    load_env_file(PROJECT_ROOT / ".env")
    return load_yaml(PROJECT_ROOT / "config.yaml")


def _flatten_questions_file(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and "questions" in payload[0]:
            markets = []
            counter = 1
            for match_block in payload:
                match_name = match_block.get("match")
                for question in match_block.get("questions", []):
                    markets.append(
                        {
                            "id": f"sample-{counter}",
                            "question": question,
                            "lobby_id": "sample-lobby",
                            "match": {"name": match_name},
                        }
                    )
                    counter += 1
            return markets
        return payload
    raise ValueError("Questions file must contain a JSON list.")


def load_markets(
    args: argparse.Namespace, client: SportsPredictClient | None
) -> list[dict[str, Any]]:
    if args.questions_file:
        return _flatten_questions_file(load_json(Path(args.questions_file)))
    if client is None:
        raise ValueError(
            "SportsPredict client is required when no local questions file is supplied."
        )
    return client.get_open_questions()


def choose_model_probability(
    parsed: ParsedQuestion,
    market_probability: float | None,
    match_rows: list[dict[str, Any]],
) -> float | None:
    model_probability = estimate_goals_probability(
        parsed,
        market_probability,
        match_rows,
    )
    if model_probability is not None:
        return model_probability
    for estimator in (
        estimate_shots_probability,
        estimate_corners_probability,
        estimate_cards_probability,
    ):
        model_probability = estimator(parsed, market_probability)
        if model_probability is not None:
            return model_probability
    return None


def build_row(
    market: dict[str, Any], parsed: ParsedQuestion, mapped: dict[str, Any] | Any
) -> dict[str, Any]:
    market_name = (market.get("match") or {}).get("name") or parsed.match_name or ""
    return {
        "question_id": market.get("id"),
        "lobby_id": market.get("lobby_id"),
        "match": market_name,
        "raw_question": market.get("question", parsed.raw_question),
        "parsed_market_type": parsed.market_type,
        "market_probability": mapped.market_probability,
        "model_probability": None,
        "monte_carlo_probability": None,
        "model_vs_mc_gap": None,
        "news_adjustment": 0.0,
        "final_probability": None,
        "confidence_score": None,
        "confidence_label": "",
        "coverage_detail": "",
        "status": mapped.status,
        "reason": mapped.reason,
        "source_market_used": mapped.source_market_used,
    }


def _has_complete_market_context(parsed: ParsedQuestion, matched_rows: list[dict[str, Any]]) -> bool:
    if parsed.market_type == "match_winner":
        selections = {str(row.get("selection", "")) for row in matched_rows}
        return len(selections) >= 3
    if parsed.market_type in {"total_goals_over", "total_goals_under"}:
        selections = {str(row.get("selection", "")).lower() for row in matched_rows}
        return {"over", "under"}.issubset(selections)
    if parsed.market_type in {"team_score_at_least_1", "first_team_to_score", "team_advance"}:
        return len(matched_rows) >= 1
    return len(matched_rows) >= 1


def compute_confidence_score(
    parsed: ParsedQuestion,
    mapped: Any,
    model_probability: float | None,
    monte_carlo_probability: float | None,
) -> tuple[int | None, str]:
    if mapped.status != "READY" or mapped.market_probability is None:
        return None, ""

    score = 40
    score += 20

    if mapped.source_market_used == parsed.market_type:
        score += 15
    elif mapped.source_market_used in {"team total goals over 0.5", "anytime goalscorer"}:
        score += 2
        score -= 6

    matched_count = len(mapped.matched_rows or [])
    if matched_count >= 3:
        score += 10
    elif matched_count >= 2:
        score += 8
    elif matched_count == 1:
        score += 4

    if model_probability is not None:
        difference = abs(model_probability - mapped.market_probability)
        if difference <= 0.05:
            score += 10
        elif difference <= 0.12:
            score += 6
        else:
            score -= 4

    if monte_carlo_probability is not None and model_probability is not None:
        mc_difference = abs(model_probability - monte_carlo_probability)
        if mc_difference <= 0.05:
            score += 6
        elif mc_difference <= 0.12:
            score += 2
        else:
            score -= 8

    if _has_complete_market_context(parsed, mapped.matched_rows or []):
        score += 6
    else:
        score -= 8

    if parsed.market_type in {"match_winner", "total_goals_over", "total_goals_under"}:
        score += 5

    score = int(round(clamp(score, 5, 95)))
    if score >= 75:
        return score, "HIGH"
    if score >= 55:
        return score, "MEDIUM"
    return score, "LOW"


def build_run_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total_questions": len(rows),
        "ready": 0,
        "unsupported": 0,
        "no_market_found": 0,
        "other_skipped": 0,
    }
    for row in rows:
        if row["status"] == "READY":
            summary["ready"] += 1
        elif row["reason"] == "unsupported question type":
            summary["unsupported"] += 1
        elif row["reason"] == "no matching betting market found":
            summary["no_market_found"] += 1
        else:
            summary["other_skipped"] += 1
    return summary


def build_coverage_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "by_status": {},
        "by_reason": {},
        "by_market_type": {},
        "direct_matches": 0,
        "proxy_matches": 0,
    }
    for row in rows:
        status = str(row.get("status", ""))
        reason = str(row.get("reason", ""))
        market_type = str(row.get("parsed_market_type", "None"))
        diagnostics["by_status"][status] = diagnostics["by_status"].get(status, 0) + 1
        diagnostics["by_reason"][reason] = diagnostics["by_reason"].get(reason, 0) + 1
        diagnostics["by_market_type"][market_type] = diagnostics["by_market_type"].get(market_type, 0) + 1
        if row.get("source_market_used") == row.get("parsed_market_type") and row.get("status") == "READY":
            diagnostics["direct_matches"] += 1
        elif row.get("status") == "READY":
            diagnostics["proxy_matches"] += 1
    return diagnostics


def print_coverage_diagnostics(diagnostics: dict[str, Any]) -> None:
    print(
        "Coverage: "
        f"direct_matches={diagnostics['direct_matches']}, "
        f"proxy_matches={diagnostics['proxy_matches']}, "
        f"ready={diagnostics['by_status'].get('READY', 0)}, "
        f"skipped={diagnostics['by_status'].get('SKIPPED', 0)}"
    )


def write_history_artifacts(
    report_path: Path,
    submission_path: Path,
    rows: list[dict[str, Any]],
    submission_payload: list[dict[str, Any]],
    summary: dict[str, Any],
    diagnostics: dict[str, Any],
    history_dir: Path,
) -> None:
    stamp = utc_timestamp_slug()
    history_dir.mkdir(parents=True, exist_ok=True)
    write_csv(history_dir / f"{stamp}_predictions.csv", rows)
    write_json(history_dir / f"{stamp}_submission.json", submission_payload)
    write_json(
        history_dir / f"{stamp}_summary.json",
        {
            "latest_report_path": str(report_path),
            "latest_submission_path": str(submission_path),
            "summary": summary,
            "coverage_diagnostics": diagnostics,
        },
    )


def evaluate_results(
    client: SportsPredictClient,
    team_matcher: TeamMatcher,
    history_dir: Path,
) -> int:
    results = client.get_results()
    if not results:
        print("No settled SportsPredict results found yet.")
        return 0

    rows: list[dict[str, Any]] = []
    brier_values: list[float] = []
    by_market_type: dict[str, list[float]] = {}
    for result in results:
        parsed = parse_question(result.get("question", ""), None, team_matcher)
        market_type = parsed.market_type or "unknown"
        brier = result.get("brier_score")
        if brier is None:
            continue
        brier_value = float(brier)
        brier_values.append(brier_value)
        by_market_type.setdefault(market_type, []).append(brier_value)
        rows.append(
            {
                "question": result.get("question", ""),
                "market_type": market_type,
                "probability_submitted": result.get("probability_submitted"),
                "brier_score": brier_value,
                "created_date": result.get("created_date", ""),
            }
        )

    avg_brier = sum(brier_values) / len(brier_values) if brier_values else None
    market_summary = {
        market_type: {
            "count": len(scores),
            "avg_brier_score": round(sum(scores) / len(scores), 4),
        }
        for market_type, scores in sorted(by_market_type.items())
    }
    evaluation_payload = {
        "settled_predictions": len(rows),
        "avg_brier_score": round(avg_brier, 4) if avg_brier is not None else None,
        "market_type_summary": market_summary,
    }

    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_timestamp_slug()
    write_csv(history_dir / f"{stamp}_evaluation_rows.csv", rows)
    write_json(history_dir / f"{stamp}_evaluation_summary.json", evaluation_payload)

    print("Evaluation Summary")
    print(f"Settled predictions: {evaluation_payload['settled_predictions']}")
    print(f"Average Brier score: {evaluation_payload['avg_brier_score']}")
    print("By market type:")
    for market_type, stats in market_summary.items():
        print(f"- {market_type}: count={stats['count']}, avg_brier={stats['avg_brier_score']}")
    return 0


def main() -> int:
    args = parse_args()
    config = load_project_config()
    dry_run = not args.submit or args.dry_run

    odds_path = args.manual_odds or config["odds"]["manual_odds_path"]
    team_matcher = TeamMatcher(str(PROJECT_ROOT / config["odds"]["team_aliases_path"]))
    odds_client = OddsClient(
        OddsClientConfig(
            provider=(
                "the_odds_api" if args.use_api_odds else config["odds"]["provider"]
            ),
            api_key=(
                None
                if not (api_key := __import__("os").environ.get("ODDS_API_KEY"))
                else api_key
            ),
            base_url=__import__("os").environ.get("ODDS_API_BASE_URL")
            or config["odds"]["base_url"],
            sport_key=config["odds"]["sport_key"],
            regions=config["odds"]["regions"],
            markets=config["odds"]["markets"],
            odds_format=config["odds"]["odds_format"],
            bookmaker=__import__("os").environ.get(
                "DEFAULT_BOOKMAKER", config["odds"]["bookmaker"]
            ),
            manual_odds_path=str(PROJECT_ROOT / odds_path),
            team_aliases_path=str(PROJECT_ROOT / config["odds"]["team_aliases_path"]),
        )
    )
    validation_errors = odds_client.validate_manual_odds()
    if validation_errors:
        raise ValueError(
            "Manual odds CSV validation failed:\n- " + "\n- ".join(validation_errors)
        )

    odds_rows = odds_client.get_all_odds(use_api=args.use_api_odds)

    sp_api_key = __import__("os").environ.get("SPORTSPREDICT_API_KEY", "")
    sp_base_url = __import__("os").environ.get(
        "SPORTSPREDICT_BASE_URL", config["sportspredict"]["base_url"]
    )
    client = None
    if sp_api_key:
        client = SportsPredictClient(
            SportsPredictConfig(
                api_key=sp_api_key,
                base_url=sp_base_url,
                probability_event_title=config["sportspredict"][
                    "probability_event_title"
                ],
            )
        )

    history_dir = PROJECT_ROOT / config["output"]["history_dir"]
    if args.evaluate:
        if client is None:
            raise ValueError("SPORTSPREDICT_API_KEY is required when using --evaluate.")
        return evaluate_results(client, team_matcher, history_dir)

    markets = load_markets(args, client)
    LOGGER.info("Processing %s questions", len(markets))

    rows: list[dict[str, Any]] = []
    for market in markets:
        match_name = (market.get("match") or {}).get("name") or market.get("match")
        parsed = parse_question(market["question"], match_name, team_matcher)
        home_team, away_team = team_matcher.split_match_name(match_name)
        canonical_match_name = (
            f"{home_team} vs {away_team}" if home_team and away_team else match_name or ""
        )
        match_rows = [
            row
            for row in odds_rows
            if row.get("match_name") == canonical_match_name
        ]
        mapped = map_question_to_market(
            parsed,
            odds_client.find_rows(
                odds_rows, match_name or "", parsed.market_type or "", parsed.period
            ),
        )
        row = build_row(market, parsed, mapped)

        if row["status"] == "READY" and row["market_probability"] is not None:
            model_probability = choose_model_probability(
                parsed,
                row["market_probability"],
                match_rows,
            )
            monte_carlo_result = simulate_question_probability(
                parsed,
                match_rows,
            )
            news_adjusted_probability, news_adjustment = adjust_for_news(
                row["market_probability"], parsed, news_notes=None
            )
            final_probability, reason = combine_probabilities(
                row["market_probability"],
                model_probability,
                news_adjusted_probability,
                market_weight=config["models"]["market_weight"],
                model_weight=config["models"]["model_weight"],
                news_weight=config["models"]["news_weight"],
            )
            row["model_probability"] = model_probability
            row["monte_carlo_probability"] = monte_carlo_result.estimated_probability
            if (
                model_probability is not None
                and monte_carlo_result.estimated_probability is not None
            ):
                row["model_vs_mc_gap"] = abs(
                    model_probability - monte_carlo_result.estimated_probability
                )
            row["news_adjustment"] = news_adjustment
            row["final_probability"] = final_probability
            confidence_score, confidence_label = compute_confidence_score(
                parsed,
                mapped,
                model_probability,
                monte_carlo_result.estimated_probability,
            )
            row["confidence_score"] = confidence_score
            row["confidence_label"] = confidence_label
            row["coverage_detail"] = (
                "direct"
                if row["source_market_used"] == row["parsed_market_type"]
                else "proxy"
            )
            row["status"] = "READY" if final_probability is not None else "SKIPPED"
            row["reason"] = reason

        rows.append(row)

    report_path = (
        PROJECT_ROOT
        / config["output"]["report_dir"]
        / config["output"]["report_filename"]
    )
    submission_path = (
        PROJECT_ROOT
        / config["output"]["report_dir"]
        / config["output"]["submission_filename"]
    )
    write_prediction_report(rows, report_path)
    print(render_terminal_table(rows))
    summary = build_run_summary(rows)
    diagnostics = build_coverage_diagnostics(rows)
    print(
        "\nSummary: "
        f"{summary['ready']} ready, "
        f"{summary['unsupported']} unsupported, "
        f"{summary['no_market_found']} missing market, "
        f"{summary['other_skipped']} other skipped, "
        f"{summary['total_questions']} total"
    )
    print_coverage_diagnostics(diagnostics)

    submission_payload = build_submission_payload(rows)
    write_submission_preview(submission_payload, submission_path)
    write_history_artifacts(
        report_path,
        submission_path,
        rows,
        submission_payload,
        summary,
        diagnostics,
        history_dir,
    )

    if dry_run:
        LOGGER.info("Dry-run mode active. No predictions submitted.")
        return 0

    if client is None:
        raise ValueError("SPORTSPREDICT_API_KEY is required when using --submit.")

    for chunk in chunked(submission_payload, 50):
        result = client.submit_predictions_batch(chunk)
        LOGGER.info(
            "Submitted batch: %s/%s succeeded",
            result.get("succeeded"),
            result.get("total"),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
