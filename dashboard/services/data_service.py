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


def load_all_matches():
    if not MATCHES_PATH.exists():
        return []

    with open(MATCHES_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    return [
        Match(
            player1=m["player1"],
            player2=m["player2"],
            court=m["court"],
            date=m["date"],
            tour=m.get("tour", "")
        )
        for m in raw
    ]


def get_available_dates(matches):
    return sorted({m.date for m in matches})


def get_matches_by_date(selected_date):
    return [m for m in load_all_matches() if m.date == selected_date]


def load_meta():
    if not META_PATH.exists():
        return {}
    with open(META_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
