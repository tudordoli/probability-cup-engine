from __future__ import annotations

from dataclasses import dataclass

from src.utils.helpers import load_csv, normalize_text


@dataclass
class TeamMatcher:
    alias_path: str

    def __post_init__(self) -> None:
        self.alias_to_team = self._load_aliases()

    def _load_aliases(self) -> dict[str, str]:
        alias_rows = load_csv(self.alias_path)
        mapping = {normalize_text(row["alias"]): row["canonical"] for row in alias_rows if row.get("alias")}
        for canonical in list(mapping.values()):
            mapping.setdefault(normalize_text(canonical), canonical)
        return mapping

    def canonicalize(self, name: str | None) -> str | None:
        if not name:
            return None
        return self.alias_to_team.get(normalize_text(name), name)

    def split_match_name(self, match_name: str | None) -> tuple[str | None, str | None]:
        if not match_name or " vs " not in match_name:
            return None, None
        home, away = match_name.split(" vs ", 1)
        return self.canonicalize(home.strip()), self.canonicalize(away.strip())

