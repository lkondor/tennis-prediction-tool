import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from backfill.elo import SurfaceElo
from backfill.atp_backfill import build_atp_player_backfill
from backfill.wta_backfill import aggregate_wta_players_from_matches
from backfill.aggregate_players import build_three_year_rates
from backfill.weather import fetch_madrid_weather_forecast
from backfill.results_scraper import scrape_results_history


OUT_DIR = Path("data/live")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def compute_clay_elo(results_history):
    elo = SurfaceElo(base_rating=1500, k=24)

    clay_results = [
        r for r in results_history
        if r.get("surface", "").lower() == "clay"
    ]

    clay_results.sort(key=lambda x: x["date"])

    for r in clay_results:
        elo.update(r["winner"], r["loser"])

    return elo.export()


def merge_players(atp_players, wta_players, elo_map):
    merged = {}

    for name, rec in atp_players.items():
        merged[name] = build_three_year_rates(rec)

    for name, rec in wta_players.items():
        merged[name] = build_three_year_rates(rec)

    for name, rating in elo_map.items():
        merged.setdefault(name, {})
        merged[name]["elo_clay"] = round(rating, 1)

    return merged


def ensure_matches_file():
    matches_path = OUT_DIR / "matches.json"
    if matches_path.exists():
        return

    sample = [
        {
            "player1": "Jannik Sinner",
            "player2": "Daniil Medvedev",
            "court": "Manolo Santana Stadium",
            "date": datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat(),
            "tour": "ATP"
        }
    ]
    with open(matches_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)


def main():
    ensure_matches_file()

    results_history = scrape_results_history()
    elo_map = compute_clay_elo(results_history)

    atp_players = build_atp_player_backfill()
    wta_players = aggregate_wta_players_from_matches()
    players = merge_players(atp_players, wta_players, elo_map)

    weather = fetch_madrid_weather_forecast()

    with open(OUT_DIR / "players.json", "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

    with open(OUT_DIR / "weather.json", "w", encoding="utf-8") as f:
        json.dump(weather, f, ensure_ascii=False, indent=2)

    with open(OUT_DIR / "meta.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(ZoneInfo("Europe/Madrid")).isoformat(),
            "match_source": "live/update pipeline",
            "players_backfill_updated_at": datetime.now(ZoneInfo("Europe/Madrid")).isoformat()
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
