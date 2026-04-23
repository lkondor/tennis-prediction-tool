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


def safe_write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def compute_clay_elo(results_history):
    elo = SurfaceElo(base_rating=1500, k=24)

    clay_results = [
        r for r in results_history
        if r.get("surface", "").lower() == "clay"
        and r.get("winner")
        and r.get("loser")
    ]

    clay_results.sort(key=lambda x: x.get("date", ""))

    for r in clay_results:
        elo.update(r["winner"], r["loser"])

    elo_map = elo.export()

    # fallback realistico se non ci sono ancora abbastanza risultati storici
    if not elo_map:
        return {
            "jannik sinner": 2100.0,
            "carlos alcaraz": 2200.0,
            "daniil medvedev": 2050.0,
            "alexander zverev": 2000.0,
            "iga swiatek": 2150.0,
            "aryna sabalenka": 2100.0,
        }

    return elo_map


def merge_players(atp_players, wta_players, elo_map):
    merged = {}

    for name, rec in atp_players.items():
        base = build_three_year_rates(rec)
        merged[name.lower().strip()] = base

    for name, rec in wta_players.items():
        base = build_three_year_rates(rec)
        merged[name.lower().strip()] = base

    for name, rating in elo_map.items():
        clean_name = name.lower().strip()
        merged.setdefault(clean_name, {})
        merged[clean_name]["elo_clay"] = round(rating, 1)

    # fallback di sicurezza per campi usati dal modello
    for name, rec in merged.items():
        rec.setdefault("elo_clay", 1800.0)
        rec.setdefault("ace_rate_clay_3y", 0.25)
        rec.setdefault("break_rate_clay_3y", 0.20)

        # se non presenti, li deriviamo dai tassi base
        rec.setdefault("ace_allowed_clay_3y", round(rec["ace_rate_clay_3y"] * 0.9, 4))
        rec.setdefault("break_allowed_clay_3y", round(rec["break_rate_clay_3y"] * 0.8, 4))

        rec.setdefault("madrid_ace_rate", 0.0)
        rec.setdefault("madrid_break_rate", 0.0)

    return merged


def update_matches():
    madrid_today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()

    # placeholder coerente finché non colleghiamo lo scraper reale order-of-play
    matches = [
        {
            "player1": "Jannik Sinner",
            "player2": "Daniil Medvedev",
            "court": "Manolo Santana Stadium",
            "date": madrid_today,
            "tour": "ATP"
        },
        {
            "player1": "Carlos Alcaraz",
            "player2": "Alexander Zverev",
            "court": "Court 4",
            "date": madrid_today,
            "tour": "ATP"
        },
        {
            "player1": "Iga Swiatek",
            "player2": "Aryna Sabalenka",
            "court": "Arantxa Sanchez Stadium",
            "date": madrid_today,
            "tour": "WTA"
        }
    ]

    safe_write_json(OUT_DIR / "matches.json", matches)
    return matches


def main():
    now_madrid = datetime.now(ZoneInfo("Europe/Madrid")).isoformat()

    # 1) Partite del giorno
    matches = update_matches()

    # 2) Storico risultati per Elo
    try:
        results_history = scrape_results_history()
        if not isinstance(results_history, list):
            results_history = []
    except Exception:
        results_history = []

    elo_map = compute_clay_elo(results_history)

    # 3) Backfill ATP/WTA
    try:
        atp_players = build_atp_player_backfill()
        if not isinstance(atp_players, dict):
            atp_players = {}
    except Exception:
        atp_players = {}

    try:
        wta_players = aggregate_wta_players_from_matches()
        if not isinstance(wta_players, dict):
            wta_players = {}
    except Exception:
        wta_players = {}

    players = merge_players(atp_players, wta_players, elo_map)

    # 4) Meteo Madrid
    try:
        weather = fetch_madrid_weather_forecast()
        if not isinstance(weather, dict):
            weather = {}
    except Exception:
        weather = {}

    # 5) Scrittura file finali
    safe_write_json(OUT_DIR / "players.json", players)
    safe_write_json(OUT_DIR / "weather.json", weather)
    safe_write_json(OUT_DIR / "meta.json", {
        "updated_at": now_madrid,
        "match_source": "daily updater placeholder",
        "players_backfill_updated_at": now_madrid,
        "results_count": len(results_history),
        "matches_count": len(matches),
        "players_count": len(players)
    })


if __name__ == "__main__":
    main()
