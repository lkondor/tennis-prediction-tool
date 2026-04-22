import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ATP_PLAYERS_PATH = Path("data/live/atp_players_index.json")


def load_atp_player_index():
    if not ATP_PLAYERS_PATH.exists():
        return []
    with open(ATP_PLAYERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_stat_value(text: str, label: str):
    pattern = rf"{re.escape(label)}\s+([0-9]+(?:\.[0-9]+)?%?)"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.group(1) if m else None


def _to_num(value):
    if value is None:
        return None
    value = value.replace("%", "").replace(",", "").strip()
    try:
        return float(value)
    except Exception:
        return None


def fetch_atp_player_stats(player_slug: str, player_id: str, year: int, surface: str = "Clay"):
    url = f"https://www.atptour.com/en/players/{player_slug}/{player_id}/player-stats?surface={surface}&year={year}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    return {
        "aces": _to_num(_extract_stat_value(text, "Aces")),
        "service_games_played": _to_num(_extract_stat_value(text, "Service Games Played")),
        "service_games_won_pct": _to_num(_extract_stat_value(text, "Service Games Won")),
        "total_service_points_won_pct": _to_num(_extract_stat_value(text, "Total Service Points Won")),
        "first_serve_pct": _to_num(_extract_stat_value(text, "1st Serve")),
        "first_serve_points_won_pct": _to_num(_extract_stat_value(text, "1st Serve Points Won")),
        "second_serve_points_won_pct": _to_num(_extract_stat_value(text, "2nd Serve Points Won")),
        "break_points_saved_pct": _to_num(_extract_stat_value(text, "Break Points Saved")),
        "break_points_faced": _to_num(_extract_stat_value(text, "Break Points Faced")),
        "return_games_won_pct": _to_num(_extract_stat_value(text, "Return Games Won")),
    }


def build_atp_player_backfill():
    players = load_atp_player_index()
    output = {}

    for p in players:
        name = p["name"].lower().strip()
        slug = p["slug"]
        pid = p["id"]

        yearly = {}
        for year in [2023, 2024, 2025, 2026]:
            try:
                yearly[str(year)] = fetch_atp_player_stats(slug, pid, year, "Clay")
            except Exception:
                yearly[str(year)] = {}

        output[name] = {
            "tour": "ATP",
            "stats_by_year_clay": yearly
        }

    return output
