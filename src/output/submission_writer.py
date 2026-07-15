from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils.helpers import write_json


def build_submission_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = []
    for row in rows:
        if row.get("status") != "READY" or row.get("final_probability") is None:
            continue
        payload.append(
            {
                "market_id": row["question_id"],
                "lobby_id": row["lobby_id"],
                "probability": row["final_probability"],
            }
        )
    return payload


def write_submission_preview(payload: list[dict[str, Any]], destination: Path) -> None:
    write_json(destination, payload)

