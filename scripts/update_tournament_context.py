import json
from pathlib import Path
from datetime import datetime


TOURNAMENT_CONTEXT_PATH = Path("data/live/tournament_context.json")


TOURNAMENTS = {
    "madrid": {
        "tournament": "Madrid Open",
        "slug": "madrid",
        "surface": "clay",
        "tour": "combined",
        "location": "Madrid",
        "altitude_m": 667,
        "ace_environment_factor": 1.15,
        "break_environment_factor": 1.00,
    },
    "rome": {
        "tournament": "Italian Open",
        "slug": "rome",
        "surface": "clay",
        "tour": "combined",
        "location": "Rome",
        "altitude_m": 21,
        "ace_environment_factor": 1.03,
        "break_environment_factor": 1.05,
    },
    "roland-garros": {
        "tournament": "Roland Garros",
        "slug": "roland-garros",
        "surface": "clay",
        "tour": "combined",
        "location": "Paris",
        "altitude_m": 35,
        "ace_environment_factor": 1.00,
        "break_environment_factor": 1.06,
    },
    "wimbledon": {
        "tournament": "Wimbledon",
        "slug": "wimbledon",
        "surface": "grass",
        "tour": "combined",
        "location": "London",
        "altitude_m": 11,
        "ace_environment_factor": 1.12,
        "break_environment_factor": 0.92,
    },
    "us-open": {
        "tournament": "US Open",
        "slug": "us-open",
        "surface": "hard",
        "tour": "combined",
        "location": "New York",
        "altitude_m": 10,
        "ace_environment_factor": 1.08,
        "break_environment_factor": 0.96,
    },
}


TOURNAMENT_CALENDAR_2026 = [
    ("madrid", "2026-04-20", "2026-05-03"),
    ("rome", "2026-05-04", "2026-05-17"),
    ("roland-garros", "2026-05-24", "2026-06-07"),
    ("wimbledon", "2026-06-29", "2026-07-12"),
    ("us-open", "2026-08-24", "2026-09-13"),
]


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def detect_active_tournament(today=None):
    if today is None:
        today = datetime.utcnow().date()

    for slug, start, end in TOURNAMENT_CALENDAR_2026:
        if parse_date(start) <= today <= parse_date(end):
            return slug

    # fallback: ultimo torneo configurato più vicino nel futuro/passato
    return "madrid"


def build_context(slug):
    base = TOURNAMENTS[slug]
    season = 2026

    return {
        **base,
        "season": season,
        "lookback_tournament_editions": [season - 3, season - 2, season - 1],
        "current_edition": season,
        "updated_at": datetime.utcnow().isoformat(),
    }


def update_tournament_context():
    slug = detect_active_tournament()
    context = build_context(slug)

    save_json(TOURNAMENT_CONTEXT_PATH, context)

    print(f"Updated tournament context: {context['tournament']}")
    print(f"Output: {TOURNAMENT_CONTEXT_PATH}")


if __name__ == "__main__":
    update_tournament_context()
