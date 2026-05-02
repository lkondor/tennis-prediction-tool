import json
from pathlib import Path
from datetime import datetime


TOURNAMENT_CONTEXT_PATH = Path("data/live/tournament_context.json")
HISTORICAL_MATCHES_PATH = Path("data/raw/historical_matches.json")
CURRENT_RESULTS_PATH = Path("data/live/current_tournament_results.json")


def load_json(path, default):
    if not path.exists():
        return default

    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return default
        return json.loads(text)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def norm(value):
    return str(value or "").lower().strip()


def make_match_id(match):
    return "|".join(
        [
            str(match.get("date", "")),
            str(match.get("tour", "")),
            str(match.get("tournament_slug", "")),
            str(match.get("player1", "")),
            str(match.get("player2", "")),
            str(match.get("round", "")),
        ]
    )


def is_same_tour(match_tour, context_tour):
    match_tour = norm(match_tour)
    context_tour = norm(context_tour)

    if context_tour == "combined":
        return match_tour in ["atp", "wta", "combined", ""]
    return match_tour == context_tour


def update_current_tournament_results():
    context = load_json(TOURNAMENT_CONTEXT_PATH, {})
    historical_matches = load_json(HISTORICAL_MATCHES_PATH, [])
    existing_live = load_json(CURRENT_RESULTS_PATH, [])

    slug = norm(context.get("slug"))
    season = int(context.get("season", datetime.utcnow().year))
    tour = norm(context.get("tour", "combined"))

    existing_by_id = {
        make_match_id(m): m
        for m in existing_live
    }

    imported_live = []

    for match in historical_matches:
        if norm(match.get("tournament_slug")) != slug:
            continue

        if int(match.get("season") or 0) != season:
            continue

        if not is_same_tour(match.get("tour"), tour):
            continue

        match_id = make_match_id(match)

        live_match = {
            **match,
            "source": "historical_current_season",
            "updated_at": datetime.utcnow().isoformat(),
        }

        existing_by_id[match_id] = live_match
        imported_live.append(live_match)

    output = sorted(
        existing_by_id.values(),
        key=lambda x: (
            str(x.get("date", "")),
            str(x.get("tour", "")),
            str(x.get("round", "")),
            str(x.get("player1", "")),
        ),
    )

    save_json(CURRENT_RESULTS_PATH, output)

    print(f"Tournament: {context.get('tournament')} ({slug})")
    print(f"Season: {season}")
    print(f"Live results imported from historical: {len(imported_live)}")
    print(f"Total current tournament results: {len(output)}")
    print(f"Output: {CURRENT_RESULTS_PATH}")


if __name__ == "__main__":
    update_current_tournament_results()
