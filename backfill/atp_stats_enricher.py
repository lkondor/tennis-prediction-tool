import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


OUT_DIR = Path("data/live")
DEBUG_PATH = OUT_DIR / "atp_stats_enricher_debug.json"
OUTPUT_PATH = OUT_DIR / "atp_enriched_stats.json"

MADRID_TZ = ZoneInfo("Europe/Madrid")

ATP_GATEWAY_URL = "https://app.atptour.com/api/v2/gateway"
ATP_STATS_LEADERBOARD_TOP_FIVE_URL = (
    "https://www.atptour.com/en/-/www/StatsLeaderboard/TopFive"
)

ATP_STATS_URLS = {
    "stats_home": "https://www.atptour.com/en/stats/stats-home",
    "individual_game_stats": "https://www.atptour.com/en/stats/individual-game-stats",
    "leaderboard": "https://www.atptour.com/en/stats/leaderboard",
    "tdi_leaderboard": "https://www.atptour.com/en/stats/tdi-leaderboard",
}


KEYWORDS = [
    "Aces",
    "1st Serve",
    "1st Serve Points Won",
    "2nd Serve Points Won",
    "Service Games Won",
    "Break Points Saved",
    "Break Points Converted",
    "Return Games Won",
    "Serve Quality",
    "Return Quality",
    "Shot Quality",
]


def safe_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def safe_get(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; MadridPredictor/1.0; +https://github.com)"
        ),
        "Accept": "application/json,text/html,*/*",
    }
    return requests.get(url, headers=headers, timeout=25)


def clean_line(line):
    return " ".join(str(line).replace("\xa0", " ").split()).strip()


def fetch_stats_leaderboard_top_five():
    debug = {
        "url": ATP_STATS_LEADERBOARD_TOP_FIVE_URL,
        "http_status": None,
        "content_type": None,
        "looks_like_json": False,
        "json_keys": [],
        "text_sample": None,
        "status": "not_started",
        "error": None,
    }

    try:
        response = safe_get(ATP_STATS_LEADERBOARD_TOP_FIVE_URL)
        debug["http_status"] = response.status_code
        debug["content_type"] = response.headers.get("content-type", "")
        debug["text_sample"] = response.text[:3000]

        try:
            payload = response.json()
            debug["looks_like_json"] = True

            if isinstance(payload, dict):
                debug["json_keys"] = list(payload.keys())[:50]
            elif isinstance(payload, list):
                debug["json_keys"] = ["list", f"length={len(payload)}"]

            debug["status"] = "ok_json"
        except Exception:
            debug["status"] = "ok_non_json" if response.status_code == 200 else "http_error"

        return debug

    except Exception as exc:
        debug["status"] = "exception"
        debug["error"] = str(exc)
        return debug


def inspect_page(name, url):
    debug = {
        "name": name,
        "url": url,
        "http_status": None,
        "line_count": 0,
        "sample_lines": [],
        "keyword_hits": {},
        "sample_classes": [],
        "endpoint_candidates": [],
        "status": "not_started",
        "error": None,
    }

    try:
        response = safe_get(url)
        debug["http_status"] = response.status_code

        if response.status_code != 200:
            debug["status"] = "http_error"
            return debug

        soup = BeautifulSoup(response.text, "html.parser")

        endpoint_candidates = []

        for tag in soup.find_all(True):
            for attr_name, attr_value in tag.attrs.items():
                if isinstance(attr_value, list):
                    attr_value = " ".join(str(x) for x in attr_value)

                attr_value = str(attr_value)

                if (
                    "api" in attr_value.lower()
                    or "endpoint" in attr_value.lower()
                    or "stats" in attr_value.lower()
                    or "leaderboard" in attr_value.lower()
                    or "match" in attr_value.lower()
                    or "gateway" in attr_value.lower()
                ):
                    endpoint_candidates.append({
                        "tag": tag.name,
                        "attr": attr_name,
                        "value": attr_value[:500]
                    })

        debug["endpoint_candidates"] = endpoint_candidates[:150]

        text = soup.get_text("\n", strip=True)

        lines = [
            clean_line(x)
            for x in text.splitlines()
            if clean_line(x)
        ]

        debug["line_count"] = len(lines)
        debug["sample_lines"] = lines[:150]

        for kw in KEYWORDS:
            debug["keyword_hits"][kw] = sum(
                1 for line in lines
                if kw.lower() in line.lower()
            )

        debug["sample_classes"] = sorted(
            list({
                c
                for tag in soup.find_all(True)
                for c in (tag.get("class") or [])
            })
        )[:200]

        debug["status"] = "ok"

        return debug

    except Exception as exc:
        debug["status"] = "exception"
        debug["error"] = str(exc)
        return debug


def update_atp_enriched_stats():
    pages = []

    for name, url in ATP_STATS_URLS.items():
        pages.append(inspect_page(name, url))

    leaderboard_test = fetch_stats_leaderboard_top_five()

    debug = {
        "updated_at": datetime.now(MADRID_TZ).isoformat(),
        "gateway_url": ATP_GATEWAY_URL,
        "leaderboard_test": leaderboard_test,
        "pages": pages,
    }

    safe_write_json(DEBUG_PATH, debug)

    output = {
        "updated_at": datetime.now(MADRID_TZ).isoformat(),
        "status": "debug_only",
        "gateway_url": ATP_GATEWAY_URL,
        "players": {}
    }

    safe_write_json(OUTPUT_PATH, output)

    return {
        "status": "debug_only",
        "pages_checked": len(pages),
    }
