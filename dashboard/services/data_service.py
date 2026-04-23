import json
from dataclasses import dataclass
from pathlib import Path


MATCHES_PATH = Path("data/live/matches.json")
META_PATH = Path("data/live/meta.json")


@dataclass
class Match:
    player1: str
    player2: str
    court: str
    date: str
    tour: str


def _safe_load_json(path: Path, default):
    try:
        if not path.exists():
            return default

        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return default

        return json.loads(text)
    except Exception:
        return default


def load_all_matches():
    raw = _safe_load_json(MATCHES_PATH, [])

    matches = []
    for m in raw:
        try:
            matches.append(
                Match(
                    player1=m["player1"],
                    player2=m["player2"],
                    court=m["court"],
                    date=m["date"],
                    tour=m.get("tour", "")
                )
            )
        except Exception:
            continue

    return matches


def get_available_dates(matches):
    return sorted({m.date for m in matches})


def get_matches_by_date(selected_date):
    return [m for m in load_all_matches() if m.date == selected_date]


def load_meta():
    return _safe_load_json(META_PATH, {})
