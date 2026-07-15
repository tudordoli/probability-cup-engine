from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils.helpers import write_csv


def _format_percent(value: float | int | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value}%"
    return f"{value * 100:.1f}%"


def write_prediction_report(rows: list[dict[str, Any]], destination: Path) -> None:
    write_csv(destination, rows)


def render_terminal_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No prediction rows generated."

    headers = [
        "question_id",
        "match",
        "parsed_market_type",
        "market_probability",
        "model_probability",
        "monte_carlo_probability",
        "model_vs_mc_gap",
        "final_probability",
        "confidence_score",
        "confidence_label",
        "status",
        "reason",
    ]
    display_rows: list[list[str]] = []
    for row in rows:
        display_rows.append(
            [
                str(row.get("question_id", "")),
                str(row.get("match", "")),
                str(row.get("parsed_market_type", "")),
                _format_percent(row.get("market_probability")),
                _format_percent(row.get("model_probability")),
                _format_percent(row.get("monte_carlo_probability")),
                _format_percent(row.get("model_vs_mc_gap")),
                _format_percent(row.get("final_probability")),
                str(row.get("confidence_score", "")),
                str(row.get("confidence_label", "")),
                str(row.get("status", "")),
                str(row.get("reason", "")),
            ]
        )

    widths = [len(header) for header in headers]
    for display in display_rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, display)]

    def format_row(values: list[str]) -> str:
        return " | ".join(value.ljust(width) for value, width in zip(values, widths))

    divider = "-+-".join("-" * width for width in widths)
    lines = [format_row(headers), divider]
    lines.extend(format_row(row) for row in display_rows)
    return "\n".join(lines)
