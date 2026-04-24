import json
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


OUT_DIR = Path("data/live")
RESULTS_PATH = OUT_DIR / "results_history.json"
DEBUG_PATH = OUT_DIR / "results_scraper_debug.json"
ALIASES_PATH = OUT_DIR / "player_aliases.json"

ATP_MADRID_RESULTS_URL = "https://www.atptour.com/en/scores/current/madrid/1536/results"

MADRID_TZ = ZoneInfo("Europe/Madrid")


def safe_write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def safe_load_json(path: Path, default):
    try:
        if not path.exists():
            return default
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return default
        return json.loads(text)
    except Exception:
        return default


def safe_get(url: str):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; MadridPredictor/1.0; +https://github.com)"
        )
    }
    return requests.get(url, timeout=25, headers=headers)


def normalize_name(name):
    return str(name).replace("\xa0", " ").strip().lower()


def load_aliases():
    return safe_load_json(ALIASES_PATH, {})


def canonical_name(name, aliases):
    key = normalize_name(name)
    return normalize_name(aliases.get(key, key))


def clean_line(line: str):
    line = line.replace("\xa0", " ").strip()
    line = re.sub(r"\([^)]*\)", "", line)
    line = re.sub(r"\[[^\]]+\]", "", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip(" -–•")


def result_key(row):
    return (
        row.get("date", ""),
        normalize_name(row.get("tour", "")),
        normalize_name(row.get("tournament", "")),
        normalize_name(row.get("player1", "")),
        normalize_name(row.get("player2", "")),
    )


def dedupe_results(rows):
    output = []
    seen = set()

    for row in rows:
        key = result_key(row)
        reverse_key = (
            row.get("date", ""),
            normalize_name(row.get("tour", "")),
            normalize_name(row.get("tournament", "")),
            normalize_name(row.get("player2", "")),
            normalize_name(row.get("player1", "")),
        )

        if key in seen or reverse_key in seen:
            continue

        seen.add(key)
        output.append(row)

    output.sort(key=lambda x: x.get("date", ""))
    return output


def load_existing_results():
    rows = safe_load_json(RESULTS_PATH, [])
    return rows if isinstance(rows, list) else []


def parse_atp_current_madrid_results():
    debug = {
        "source": "ATP Madrid Results",
        "url": ATP_MADRID_RESULTS_URL,
        "http_status": None,
        "parsed_results_count": 0,
        "status": "not_started",
        "error": None,
    }

    try:
        response = safe_get(ATP_MADRID_RESULTS_URL)
        debug["http_status"] = response.status_code

        if response.status_code != 200:
            debug["status"] = "http_error"
            return [], debug

        soup = BeautifulSoup(response.text, "html.parser")

        debug["html_diagnostics"] = {
            "day_table_rows": len(soup.select(".day-table tbody tr")),
            "table_rows": len(soup.select("table tr")),
            "match_rows": len(soup.select("[class*='match']")),
            "score_rows": len(soup.select("[class*='score']")),
            "player_name_nodes": len(soup.select("[class*='player']")),
            "sample_classes": sorted(
                list({
                    c
                    for tag in soup.find_all(True)
                    for c in (tag.get("class") or [])
                })
            )[:100],
        }
        
        aliases = load_aliases()
        results = []

        today = datetime.now(MADRID_TZ).date().isoformat()

        matches = soup.select(".day-table tbody tr")

        for row in matches:
            players = row.select(".day-table-name")

            if len(players) < 2:
                continue

            p1 = players[0].get_text(strip=True)
            p2 = players[1].get_text(strip=True)

            winner = canonical_name(p1, aliases).title()
            loser = canonical_name(p2, aliases).title()

            results.append({
                "date": today,
                "tour": "ATP",
                "tournament": "Madrid",
                "surface": "Clay",
                "player1": winner,
                "player2": loser,
                "winner": winner,
                "loser": loser,
                "aces_p1": 0,
                "aces_p2": 0,
                "service_games_p1": 0,
                "service_games_p2": 0,
                "breaks_p1": 0,
                "breaks_p2": 0,
                "return_games_p1": 0,
                "return_games_p2": 0,
                "data_source": "ATP HTML",
                "stats_quality": "result_only"
            })

        results = dedupe_results(results)

        debug["parsed_results_count"] = len(results)
        debug["status"] = "ok" if results else "no_results"

        return results, debug

    except Exception as exc:
        debug["status"] = "exception"
        debug["error"] = str(exc)
        return [], debug


def refresh_results_history():
    """
    Funzione principale incrementale:
    - carica storico esistente
    - scarica nuovi risultati disponibili
    - unisce senza duplicati
    - riscrive results_history.json
    - scrive debug
    """

    existing = load_existing_results()
    atp_new, atp_debug = [], {"status": "disabled_html_parser"}

    merged = dedupe_results(existing + atp_new)

    safe_write_json(RESULTS_PATH, merged)

    debug = {
        "updated_at": datetime.now(MADRID_TZ).isoformat(),
        "existing_count": len(existing),
        "new_atp_count": len(atp_new),
        "final_count": len(merged),
        "atp": atp_debug,
    }

    safe_write_json(DEBUG_PATH, debug)

    return {
        "existing_count": len(existing),
        "new_atp_count": len(atp_new),
        "final_count": len(merged),
    }


def scrape_results_history():
    """
    Compatibilità con il resto del progetto.
    Aggiorna results_history.json e restituisce lo storico finale.
    """
    refresh_results_history()
    return load_existing_results()
