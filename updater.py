import io
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

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
from backfill.results_scraper import refresh_results_history
from backfill.player_database import build_players_database
from backfill.player_database import load_aliases, canonical_name
from backfill.historical_builder import expand_history
aliases = load_aliases()

OUT_DIR = Path("data/live")
OUT_DIR.mkdir(parents=True, exist_ok=True)

MADRID_TZ = ZoneInfo("Europe/Madrid")

ATP_DAILY_SCHEDULE_URL = (
    "https://www.atptour.com/en/scores/current/madrid/1536/daily-schedule"
)

COURTS = [
    "Manolo Santana Stadium",
    "Arantxa Sanchez Stadium",
    "Stadium 3",
    "Court 3",
    "Court 4",
    "Court 5",
    "Court 6",
    "Court 7",
    "Court 8",
]


# ============================================================
# Generic helpers
# ============================================================

def now_madrid():
    return datetime.now(MADRID_TZ)


def safe_write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def safe_get(url: str, timeout: int = 25):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; MadridPredictor/1.0; "
            "+https://github.com)"
        )
    }
    return requests.get(url, timeout=timeout, headers=headers)


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ").strip()
    value = re.sub(r"\([^)]*\)", "", value)      # remove seeds / Q / WC / country
    value = re.sub(r"\[[^\]]+\]", "", value)     # remove bracket markers
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -–•")


def looks_like_player_name(value: str) -> bool:
    if not value:
        return False

    lower = value.lower()

    blocked_fragments = [
        "order of play",
        "mutua madrid open",
        "singles",
        "doubles",
        "starts at",
        "followed by",
        "not before",
        "defeats",
        "walkover",
        "retired",
        "court",
        "stadium",
        "schedule",
        "results",
        "tickets",
        "news",
        "ranking",
        "draw",
        "h2h",
        "vs",
    ]

    if any(x in lower for x in blocked_fragments):
        return False

    words = value.replace(".", " ").split()

    if len(words) < 2 or len(words) > 5:
        return False

    letters = [c for c in value if c.isalpha()]
    if len(letters) < 3:
        return False

    return True


def normalize_court(line: str):
    upper = line.upper()

    for court in COURTS:
        if upper.startswith(court.upper()):
            return court

    return None


def fallback_matches():
    today = now_madrid().date().isoformat()

    return [
        {
            "player1": "Jannik Sinner",
            "player2": "Daniil Medvedev",
            "court": "Manolo Santana Stadium",
            "date": today,
            "tour": "ATP",
        },
        {
            "player1": "Carlos Alcaraz",
            "player2": "Alexander Zverev",
            "court": "Court 4",
            "date": today,
            "tour": "ATP",
        },
        {
            "player1": "Iga Swiatek",
            "player2": "Aryna Sabalenka",
            "court": "Arantxa Sanchez Stadium",
            "date": today,
            "tour": "WTA",
        },
    ]


# ============================================================
# Date helpers
# ============================================================

def candidate_dates():
    today = now_madrid().date()

    return [
        today,
        today + timedelta(days=1),
    ]


def parse_atp_date_line(line: str):
    """
    Expected examples:
    Thu, 23 April, 2026
    Thu, 23 April, 2026 (Day 4)
    """
    line = line.split("(")[0].strip()

    for fmt in ("%a, %d %B, %Y", "%a, %-d %B, %Y"):
        try:
            return datetime.strptime(line, fmt).date().isoformat()
        except Exception:
            continue

    return None


def is_atp_date_line(line: str):
    return bool(
        re.match(
            r"^[A-Z][a-z]{2},\s+\d{1,2}\s+[A-Z][a-z]+,\s+\d{4}",
            line,
        )
    )


# ============================================================
# Match parsing
# ============================================================

def dedupe_matches(matches):
    output = []
    seen = set()

    for m in matches:
        key = (
            m["player1"].lower(),
            m["player2"].lower(),
            m["court"].lower(),
            m["date"],
        )

        reverse = (
            m["player2"].lower(),
            m["player1"].lower(),
            m["court"].lower(),
            m["date"],
        )

        if key in seen or reverse in seen:
            continue

        seen.add(key)
        output.append(m)

    return output


def parse_matches_from_lines(lines, default_date=None):
    matches = []
    current_date = default_date
    current_court = None

    def is_initial(value):
        return bool(re.match(r"^[A-Z]\.$", value.strip()))

    def combine_name(idx):
        """
        Gestisce nomi ATP/WTA spezzati:
        J.
        Sinner

        oppure:
        A.
        de Minaur
        """
        if idx + 1 >= len(lines):
            return None, idx

        first = clean_text(lines[idx])
        second = clean_text(lines[idx + 1])

        if is_initial(first) and looks_like_player_name(f"{first} {second}"):
            return f"{first} {second}", idx + 2

        candidate = clean_text(lines[idx])
        if looks_like_player_name(candidate):
            return candidate, idx + 1

        return None, idx

    i = 0

    while i < len(lines):
        line = clean_text(lines[i])

        if not line:
            i += 1
            continue

        parsed_date = parse_atp_date_line(line)
        if parsed_date:
            current_date = parsed_date
            current_court = None
            i += 1
            continue

        court = normalize_court(line)
        if court:
            current_court = court
            i += 1
            continue

        if not current_date or not current_court:
            i += 1
            continue

        p1, next_i = combine_name(i)
        if not p1:
            i += 1
            continue

        if next_i >= len(lines) or clean_text(lines[next_i]).upper() != "VS":
            i += 1
            continue

        p2, final_i = combine_name(next_i + 1)
        if not p2:
            i += 1
            continue

        matches.append(
            {
                "player1": p1.title(),
                "player2": p2.title(),
                "court": current_court,
                "date": current_date,
                "tour": "ATP/WTA",
            }
        )

        i = final_i

    return dedupe_matches(matches)

# ============================================================
# Source 1: ATP Daily Schedule
# ============================================================

def fetch_atp_daily_schedule_matches():
    debug = {
        "status": "not_started",
        "url": ATP_DAILY_SCHEDULE_URL,
        "http_status": None,
        "line_count": 0,
        "sample_lines": [],
        "matches_count": 0,
        "error": None,
    }

    try:
        response = safe_get(ATP_DAILY_SCHEDULE_URL)
        debug["http_status"] = response.status_code

        if response.status_code != 200:
            debug["status"] = "http_error"
            return [], debug

        soup = BeautifulSoup(response.text, "html.parser")
        raw_text = soup.get_text("\n", strip=True)

        lines = [
            clean_text(x)
            for x in raw_text.splitlines()
            if clean_text(x)
        ]

        debug["line_count"] = len(lines)
        debug["sample_lines"] = lines[:120]

        matches = parse_matches_from_lines(lines)

        debug["matches_count"] = len(matches)
        debug["status"] = "ok" if matches else "no_matches"

        return matches, debug

    except Exception as exc:
        debug["status"] = "exception"
        debug["error"] = str(exc)
        return [], debug


# ============================================================
# Source 2: Madrid Official PDF
# ============================================================

def madrid_pdf_url(target_date):
    return (
        "https://mutuamadridopen.com/wp-content/uploads/"
        f"{target_date.year}/{target_date.month:02d}/"
        f"OP-{target_date.year}-{target_date.month:02d}-{target_date.day:02d}.pdf"
    )


def fetch_madrid_pdf_matches_for_date(target_date):
    url = madrid_pdf_url(target_date)

    debug = {
        "status": "not_started",
        "url": url,
        "date": target_date.isoformat(),
        "http_status": None,
        "content_type": None,
        "line_count": 0,
        "sample_lines": [],
        "matches_count": 0,
        "error": None,
    }

    if PdfReader is None:
        debug["status"] = "pypdf_missing"
        return [], debug

    try:
        response = safe_get(url)
        debug["http_status"] = response.status_code
        debug["content_type"] = response.headers.get("content-type", "")

        if response.status_code != 200:
            debug["status"] = "http_error"
            return [], debug

        if "pdf" not in debug["content_type"].lower():
            debug["status"] = "not_pdf"
            return [], debug

        reader = PdfReader(io.BytesIO(response.content))

        text = "\n".join(
            (page.extract_text() or "")
            for page in reader.pages
        )

        lines = [
            clean_text(x)
            for x in text.splitlines()
            if clean_text(x)
        ]

        debug["line_count"] = len(lines)
        debug["sample_lines"] = lines[:120]

        matches = parse_matches_from_lines(
            lines,
            default_date=target_date.isoformat(),
        )

        debug["matches_count"] = len(matches)
        debug["status"] = "ok" if matches else "no_matches"

        return matches, debug

    except Exception as exc:
        debug["status"] = "exception"
        debug["error"] = str(exc)
        return [], debug


def fetch_madrid_pdf_matches():
    all_matches = []
    debug_items = []

    for d in candidate_dates():
        matches, debug = fetch_madrid_pdf_matches_for_date(d)
        debug_items.append(debug)
        all_matches.extend(matches)

    return dedupe_matches(all_matches), debug_items


# ============================================================
# Match update orchestration
# ============================================================

def update_matches():
    debug = {
        "updated_at": now_madrid().isoformat(),
        "used_source": None,
        "atp": None,
        "pdf": None,
        "final_matches_count": 0,
    }

    # 1. ATP primary source
    atp_matches, atp_debug = fetch_atp_daily_schedule_matches()
    debug["atp"] = atp_debug

    if atp_matches:
        debug["used_source"] = "ATP daily schedule"
        debug["final_matches_count"] = len(atp_matches)

        safe_write_json(OUT_DIR / "matches.json", atp_matches)
        safe_write_json(OUT_DIR / "match_source_debug.json", debug)

        return atp_matches, "ATP daily schedule"

    # 2. Madrid PDF fallback
    pdf_matches, pdf_debug = fetch_madrid_pdf_matches()
    debug["pdf"] = pdf_debug

    if pdf_matches:
        debug["used_source"] = "Madrid official PDF"
        debug["final_matches_count"] = len(pdf_matches)

        safe_write_json(OUT_DIR / "matches.json", pdf_matches)
        safe_write_json(OUT_DIR / "match_source_debug.json", debug)

        return pdf_matches, "Madrid official PDF"

    # 3. Demo fallback
    demo = fallback_matches()

    debug["used_source"] = "fallback demo"
    debug["final_matches_count"] = len(demo)

    safe_write_json(OUT_DIR / "matches.json", demo)
    safe_write_json(OUT_DIR / "match_source_debug.json", debug)

    return demo, "fallback demo"


# ============================================================
# Player / Elo / Weather update
# ============================================================

def compute_clay_elo(results_history):
    elo = SurfaceElo(base_rating=1500, k=24)

    clay_results = [
        r for r in results_history
        if r.get("surface", "").lower() == "clay"
        and r.get("winner")
        and r.get("loser")
    ]

    clay_results.sort(key=lambda x: x.get("date", ""))

    for result in clay_results:
        elo.update(result["winner"], result["loser"])

    elo_map = elo.export()

    if elo_map:
        return elo_map

    return {
        "jannik sinner": 2100.0,
        "carlos alcaraz": 2200.0,
        "daniil medvedev": 2050.0,
        "alexander zverev": 2000.0,
        "iga swiatek": 2150.0,
        "aryna sabalenka": 2100.0,
    }


def merge_players(atp_players, wta_players, elo_map):
    merged = {}

    for name, record in atp_players.items():
        merged[name.lower().strip()] = build_three_year_rates(record)

    for name, record in wta_players.items():
        merged[name.lower().strip()] = build_three_year_rates(record)

    for name, rating in elo_map.items():
        key = name.lower().strip()
        merged.setdefault(key, {})
        merged[key]["elo_clay"] = round(rating, 1)

    for record in merged.values():
        record.setdefault("elo_clay", 1800.0)
        record.setdefault("ace_rate_clay_3y", 0.25)
        record.setdefault("break_rate_clay_3y", 0.20)
        record.setdefault(
            "ace_allowed_clay_3y",
            round(record["ace_rate_clay_3y"] * 0.9, 4),
        )
        record.setdefault(
            "break_allowed_clay_3y",
            round(record["break_rate_clay_3y"] * 0.8, 4),
        )
        record.setdefault("madrid_ace_rate", 0.0)
        record.setdefault("madrid_break_rate", 0.0)

    return merged


def update_players(matches):
    players = build_players_database()

    unresolved_players = []

    for m in matches:
        for player_name in [m.get("player1"), m.get("player2")]:
            if not player_name:
                continue

            key = canonical_name(player_name, aliases)

            if key not in players:
                players[key] = {
                    "elo_clay": None,
                    "ace_rate_clay_3y": None,
                    "ace_allowed_clay_3y": None,
                    "break_rate_clay_3y": None,
                    "break_allowed_clay_3y": None,
                    "madrid_ace_rate": None,
                    "madrid_break_rate": None,
                    "data_quality": "unresolved"
                }
                unresolved_players.append(key)

    safe_write_json(
        OUT_DIR / "unresolved_players.json",
        sorted(set(unresolved_players))
    )

    safe_write_json(OUT_DIR / "players.json", players)

    historical_count = sum(
        1 for p in players.values()
        if p.get("data_quality") == "historical_match_stats"
    )

    unresolved_count = sum(
        1 for p in players.values()
        if p.get("data_quality") == "unresolved"
    )

    return {
        "results_count": 0,
        "players_count": len(players),
        "historical_players_count": historical_count,
        "unresolved_players_count": unresolved_count,
    }


def update_weather():
    try:
        weather = fetch_madrid_weather_forecast()
        if not isinstance(weather, dict):
            weather = {}
    except Exception:
        weather = {}

    safe_write_json(OUT_DIR / "weather.json", weather)

    return {
        "weather_days_count": len(weather),
    }


# ============================================================
# Main
# ============================================================

def main():
    timestamp = now_madrid().isoformat()

    matches, match_source = update_matches()
    expand_history()
    results_info = {
        "final_count": len(json.loads((OUT_DIR / "results_history.json").read_text(encoding="utf-8"))),
        "new_atp_count": 0
    }
    player_info = update_players(matches)
    weather_info = update_weather()

    meta = {
        "updated_at": timestamp,
        "match_source": match_source,
        "matches_count": len(matches),
        "players_backfill_updated_at": timestamp,
        "results_count": player_info["results_count"],
        "players_count": player_info["players_count"],
        "historical_players_count": player_info["historical_players_count"],
        "unresolved_players_count": player_info["unresolved_players_count"],
        "weather_days_count": weather_info["weather_days_count"],
    }

    safe_write_json(OUT_DIR / "meta.json", meta)


if __name__ == "__main__":
    main()
