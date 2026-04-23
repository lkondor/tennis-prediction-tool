import io
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

from backfill.elo import SurfaceElo
from backfill.atp_backfill import build_atp_player_backfill
from backfill.wta_backfill import aggregate_wta_players_from_matches
from backfill.aggregate_players import build_three_year_rates
from backfill.weather import fetch_madrid_weather_forecast
from backfill.results_scraper import scrape_results_history


OUT_DIR = Path("data/live")
OUT_DIR.mkdir(parents=True, exist_ok=True)


COURT_NAMES = {
    "MANOLO SANTANA STADIUM",
    "ARANTXA SANCHEZ STADIUM",
    "STADIUM 3",
    "COURT 3",
    "COURT 4",
    "COURT 5",
    "COURT 6",
    "COURT 7",
    "COURT 8",
}


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
        merged[name.lower().strip()] = build_three_year_rates(rec)

    for name, rec in wta_players.items():
        merged[name.lower().strip()] = build_three_year_rates(rec)

    for name, rating in elo_map.items():
        clean_name = name.lower().strip()
        merged.setdefault(clean_name, {})
        merged[clean_name]["elo_clay"] = round(rating, 1)

    for _, rec in merged.items():
        rec.setdefault("elo_clay", 1800.0)
        rec.setdefault("ace_rate_clay_3y", 0.25)
        rec.setdefault("break_rate_clay_3y", 0.20)
        rec.setdefault("ace_allowed_clay_3y", round(rec["ace_rate_clay_3y"] * 0.9, 4))
        rec.setdefault("break_allowed_clay_3y", round(rec["break_rate_clay_3y"] * 0.8, 4))
        rec.setdefault("madrid_ace_rate", 0.0)
        rec.setdefault("madrid_break_rate", 0.0)

    return merged


def _candidate_dates():
    madrid_today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    return [
        madrid_today,
        madrid_today + timedelta(days=1),
    ]


def _normalize_line(line: str) -> str:
    line = line.replace("\xa0", " ").strip()
    line = re.sub(r"\[[^\]]+\]", "", line)
    line = re.sub(r"\([A-Z]{2,3}\)", "", line)
    line = re.sub(r"\s+", " ", line).strip(" -–•")
    return line.strip()


def _looks_like_name(line: str) -> bool:
    if not line:
        return False

    if " vs " in line.lower():
        return False

    banned = {
        "ORDER", "PLAY", "MADRID", "OPEN", "COURT", "STADIUM",
        "FOLLOWED", "STARTING", "NOT", "BEFORE", "SINGLES", "DOUBLES",
        "TODAY", "TOMORROW", "ROUND", "DAY", "DEFEATS", "WTA", "ATP",
        "STARTS", "AT", "H2H"
    }

    words = line.replace(".", " ").split()
    if len(words) < 2 or len(words) > 5:
        return False

    if any(w.upper() in banned for w in words):
        return False

    # ammetti iniziali tipo "I." e seed già rimossi
    letters = [c for c in line if c.isalpha()]
    if len(letters) < 3:
        return False

    return True


def _parse_matches_from_lines(lines, date_str):
    matches = []
    current_court = None
    buffer_names = []

    for raw in lines:
        line = _normalize_line(raw)
        if not line:
            continue

        upper = line.upper()

        if upper in COURT_NAMES:
            current_court = line.title()
            buffer_names = []
            continue

        if _looks_like_name(line):
            buffer_names.append(line.title())
            if len(buffer_names) == 2 and current_court:
                p1, p2 = buffer_names
                if p1 != p2:
                    matches.append({
                        "player1": p1,
                        "player2": p2,
                        "court": current_court,
                        "date": date_str,
                        "tour": "ATP/WTA"
                    })
                buffer_names = []
        else:
            buffer_names = []

    deduped = []
    seen = set()
    for m in matches:
        key = (m["player1"].lower(), m["player2"].lower(), m["court"].lower(), m["date"])
        rev = (m["player2"].lower(), m["player1"].lower(), m["court"].lower(), m["date"])
        if key not in seen and rev not in seen:
            seen.add(key)
            deduped.append(m)

    return deduped


def fetch_matches_from_atp_daily_schedule(target_date):
    if BeautifulSoup is None:
        return []

    url = "https://www.atptour.com/en/scores/current/madrid/1536/daily-schedule"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text("\n", strip=True)
        raw_lines = [x.strip() for x in text.splitlines() if x.strip()]

        # normalizza
        lines = [_normalize_line(x) for x in raw_lines if _normalize_line(x)]

        target_label = target_date.strftime("%a, %-d %B, %Y")
        target_label_alt = target_date.strftime("%a, %d %B, %Y")

        matches = []
        current_court = None
        in_target_day = False
        i = 0

        while i < len(lines):
            line = lines[i]
            upper = line.upper()

            # attiva parsing solo quando siamo nella giornata giusta
            if target_label.lower() in line.lower() or target_label_alt.lower() in line.lower():
                in_target_day = True
                i += 1
                continue

            # se arriva un altro giorno, fermati
            if in_target_day and re.match(r"^[A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]+, \d{4}", line):
                break

            if not in_target_day:
                i += 1
                continue

            # campi
            if upper.startswith("MANOLO SANTANA STADIUM"):
                current_court = "Manolo Santana Stadium"
                i += 1
                continue
            if upper.startswith("ARANTXA SANCHEZ STADIUM"):
                current_court = "Arantxa Sanchez Stadium"
                i += 1
                continue
            if upper.startswith("STADIUM 3"):
                current_court = "Stadium 3"
                i += 1
                continue
            if upper.startswith("COURT 3"):
                current_court = "Court 3"
                i += 1
                continue
            if upper.startswith("COURT 4"):
                current_court = "Court 4"
                i += 1
                continue
            if upper.startswith("COURT 5"):
                current_court = "Court 5"
                i += 1
                continue
            if upper.startswith("COURT 6"):
                current_court = "Court 6"
                i += 1
                continue
            if upper.startswith("COURT 7"):
                current_court = "Court 7"
                i += 1
                continue
            if upper.startswith("COURT 8"):
                current_court = "Court 8"
                i += 1
                continue

            # match futuri: nome / Vs / nome
            if current_court and i + 2 < len(lines):
                p1 = lines[i]
                mid = lines[i + 1]
                p2 = lines[i + 2]

                if (
                    _looks_like_name(p1)
                    and mid.upper() == "VS"
                    and _looks_like_name(p2)
                ):
                    matches.append({
                        "player1": p1.title(),
                        "player2": p2.title(),
                        "court": current_court,
                        "date": target_date.isoformat(),
                        "tour": "ATP/WTA"
                    })
                    i += 3
                    continue

            i += 1

        # deduplica
        deduped = []
        seen = set()
        for m in matches:
            key = (
                m["player1"].lower(),
                m["player2"].lower(),
                m["court"].lower(),
                m["date"]
            )
            rev = (
                m["player2"].lower(),
                m["player1"].lower(),
                m["court"].lower(),
                m["date"]
            )
            if key not in seen and rev not in seen:
                seen.add(key)
                deduped.append(m)

        return deduped

    except Exception:
        return []


def fetch_matches_from_madrid_pdf(target_date):
    if PdfReader is None:
        return []

    pdf_url = (
        f"https://mutuamadridopen.com/wp-content/uploads/"
        f"{target_date.year}/{target_date.month:02d}/OP-{target_date.year}-{target_date.month:02d}-{target_date.day:02d}.pdf"
    )

    try:
        r = requests.get(pdf_url, timeout=20)
        if r.status_code != 200:
            return []

        content_type = r.headers.get("content-type", "").lower()
        if "pdf" not in content_type:
            return []

        reader = PdfReader(io.BytesIO(r.content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        return _parse_matches_from_lines(lines, target_date.isoformat())
    except Exception:
        return []


def update_matches():
    all_matches = []
    source_used = "fallback"

    for target_date in _candidate_dates():
        matches = fetch_matches_from_atp_daily_schedule(target_date)
        if matches:
            all_matches.extend(matches)
            source_used = "ATP daily schedule"

    if not all_matches:
        for target_date in _candidate_dates():
            matches = fetch_matches_from_madrid_pdf(target_date)
            if matches:
                all_matches.extend(matches)
                source_used = "Madrid official PDF"

    if not all_matches:
        madrid_today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
        all_matches = [
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
        source_used = "fallback demo"

    safe_write_json(OUT_DIR / "matches.json", all_matches)
    return all_matches, source_used


def main():
    now_madrid = datetime.now(ZoneInfo("Europe/Madrid")).isoformat()

    matches, match_source = update_matches()

    try:
        results_history = scrape_results_history()
        if not isinstance(results_history, list):
            results_history = []
    except Exception:
        results_history = []

    elo_map = compute_clay_elo(results_history)

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

    try:
        weather = fetch_madrid_weather_forecast()
        if not isinstance(weather, dict):
            weather = {}
    except Exception:
        weather = {}

    safe_write_json(OUT_DIR / "players.json", players)
    safe_write_json(OUT_DIR / "weather.json", weather)
    safe_write_json(OUT_DIR / "meta.json", {
        "updated_at": now_madrid,
        "match_source": match_source,
        "players_backfill_updated_at": now_madrid,
        "results_count": len(results_history),
        "matches_count": len(matches),
        "players_count": len(players)
    })


if __name__ == "__main__":
    main()
