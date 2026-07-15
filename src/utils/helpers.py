from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Iterable

import yaml


def _as_path(path: str | Path) -> Path:
    return path if isinstance(path, Path) else Path(path)


def load_env_file(path: str | Path) -> None:
    """Load simple KEY=VALUE pairs from a .env-style file if present."""
    path = _as_path(path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_yaml(path: str | Path) -> dict[str, Any]:
    path = _as_path(path)
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_json(path: str | Path) -> Any:
    path = _as_path(path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_csv(path: str | Path) -> list[dict[str, str]]:
    path = _as_path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    path = _as_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str | Path, payload: Any) -> None:
    path = _as_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def chunked(values: Iterable[Any], size: int) -> Iterable[list[Any]]:
    chunk: list[Any] = []
    for value in values:
        chunk.append(value)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.lower().replace("-", " ").split())


def utc_timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
