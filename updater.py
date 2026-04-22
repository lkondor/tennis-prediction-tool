import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import requests
from bs4 import BeautifulSoup


OUT_DIR = Path("data/live")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_madrid_order_of_play():
    url = "https://mutuamadridopen.com/en/order-of-play/"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    text = soup.get_text("\n", strip=True)
    lines = [x.strip() for x in text.splitlines() if x.strip()]

    # parser semplice da migliorare sul markup reale della pagina
    current_court = None
    current_date = None
    matches = []

    court_names = {
        "Manolo Santana Stadium",
        "Arantxa Sanchez Stadium",
        "Stadium 3",
        "Court 3",
        "Court 4",
        "Court 5",
        "Court 6",
        "Court 7",
        "Court 8",
    }

    for i, line in enumerate(lines):
        if line in ["Today", "Tomorrow"]:
            current_date = line
            continue

        if line in court_names:
            current_court = line
            continue

        if " vs " in line and current_court and current_date:
            left, right = line.split(" vs ", 1)
            matches.append({
                "player1": left.strip(),
                "player2": right.strip(),
                "court": current_court,
                "date": current_date,
                "tour": "ATP/WTA"
            })

    return matches


def fetch_atp_madrid_schedule_fallback():
    url = "https://www.atptour.com/en/news/madrid-2026-schedule"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [x.strip() for x in text.splitlines() if x.strip()]

    matches = []
    current_court = None

    courts = [
        "Manolo Santana Stadium - start 11 a.m.",
        "Arantxa Sanchez Stadium - start 11 a.m.",
        "Stadium 3 - start 11 a.m.",
        "Court 4 - start 11 a.m.",
    ]

    for line in lines:
        if line in courts:
            current_court = line.split(" - ")[0]
            continue

        if " vs " in line and current_court:
            cleaned = line.replace("ATP - ", "").replace("WTA - ", "")
            left, right = cleaned.split(" vs ", 1)
            matches.append({
                "player1": left.strip(),
                "player2": right.strip(),
                "court": current_court,
                "date": "Today",
                "tour": "ATP/WTA"
            })

    return matches


def build_players_dataset():
    # seed iniziale; qui va collegato il backfill vero ATP/WTA
    return {
        "jannik sinner": {
            "elo_clay": 2120,
            "ace_rate_clay_3y": 7.3,
            "ace_allowed_clay_3y": 5.4,
            "break_rate_clay_3y": 2.4,
            "break_allowed_clay_3y": 1.8
        },
        "carlos alcaraz": {
            "elo_clay": 2160,
            "ace_rate_clay_3y": 5.9,
            "ace_allowed_clay_3y": 4.8,
            "break_rate_clay_3y": 2.9,
            "break_allowed_clay_3y": 1.6
        }
    }


def main():
    try:
        matches = fetch_madrid_order_of_play()
        source = "Mutua Madrid Open"
        if not matches:
            matches = fetch_atp_madrid_schedule_fallback()
            source = "ATP Madrid schedule fallback"
    except Exception:
        matches = []
        source = "failed"

    players = build_players_dataset()

    with open(OUT_DIR / "matches.json", "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)

    with open(OUT_DIR / "players.json", "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

    with open(OUT_DIR / "meta.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(ZoneInfo("Europe/Madrid")).isoformat(),
            "match_source": source
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
