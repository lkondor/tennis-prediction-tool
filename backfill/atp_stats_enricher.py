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
    base_url = "https://www.atptour.com/en/-/www/StatsLeaderboard/TopFive"

    test_cases = [
        {
            "name": "2026_clay",
            "url": f"{base_url}/2026/Clay?v=1"
        },
        {
            "name": "2025_clay",
            "url": f"{base_url}/2025/Clay?v=1"
        },
        {
            "name": "2024_clay",
            "url": f"{base_url}/2024/Clay?v=1"
        },
        {
            "name": "52weeks_clay",
            "url": f"{base_url}/52%20Weeks/Clay?v=1"
        },
        {
            "name": "2026_all_surfaces",
            "url": f"{base_url}/2026/All%20Surfaces?v=1"
        }
    ]

    output = []

    for case in test_cases:
        debug = {
            "name": case["name"],
            "url": case["url"],
            "http_status": None,
            "content_type": None,
            "looks_like_json": False,
            "json_keys": [],
            "text_sample": None,
            "status": "not_started",
            "error": None,
        }

        try:
            response = requests.get(
                case["url"],
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; MadridPredictor/1.0; +https://github.com)"
                    ),
                    "Accept": "application/json, text/plain, */*",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://www.atptour.com/en/stats/leaderboard",
                },
                timeout=25
            )

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
                debug["status"] = (
                    "ok_non_json"
                    if response.status_code == 200
                    else "http_error"
                )

        except Exception as exc:
            debug["status"] = "exception"
            debug["error"] = str(exc)

        output.append(debug)

    return output


def parse_leaderboard_tests(leaderboard_tests):
    players = {}

    def upsert_player(item, stat_type, year, surface):
        name = str(item.get("PlayerName", "")).lower().strip()

        if not name:
            return

        stat_rating = item.get("Stat", {}).get("StatRating")

        try:
            stat_rating = float(stat_rating)
        except Exception:
            stat_rating = None

        players.setdefault(name, {
            "player_id": item.get("PlayerId"),
            "country": item.get("PlayerCountryCode"),
            "sources": []
        })

        players[name][f"{stat_type}_rating_{year}_{surface}"] = stat_rating
        players[name]["sources"].append(f"ATP leaderboard {stat_type} {year} {surface}")

    for test in leaderboard_tests:
        if not test.get("looks_like_json"):
            continue

        try:
            response = requests.get(
                test["url"],
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json, text/plain, */*",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://www.atptour.com/en/stats/leaderboard",
                },
                timeout=25
            )
            payload = response.json()
        except Exception:
            continue

        name = test.get("name", "")
        parts = name.split("_")

        year = parts[0] if parts else "unknown"
        surface = parts[1] if len(parts) > 1 else "unknown"

        for item in payload.get("LeaderboardTopFiveServe", []):
            upsert_player(item, "serve", year, surface)

        for item in payload.get("LeaderboardTopFiveReturn", []):
            upsert_player(item, "return", year, surface)

        for item in payload.get("LeaderboardTopFivePressure", []):
            upsert_player(item, "pressure", year, surface)

    return players



def inspect_js_assets(page_url):
    debug = {
        "page_url": page_url,
        "js_files_count": 0,
        "matches": [],
        "error": None,
    }

    try:
        response = safe_get(page_url)
        soup = BeautifulSoup(response.text, "html.parser")

        js_urls = []

        for script in soup.find_all("script"):
            src = script.get("src")
            if not src:
                continue

            if src.startswith("/"):
                src = "https://www.atptour.com" + src

            if "atptour" in src or src.startswith("https://www.atptour.com"):
                js_urls.append(src)

        debug["js_files_count"] = len(js_urls)

        keywords = [
            "StatsLeaderboard",
            "TopFive",
            "IndividualGameStats",
            "gateway",
            "Leaderboard",
            "tdi",
            "Aces",
            "BreakPoints",
            "ReturnGames",
            "ServiceGames",
            "api/v2/gateway",
            "graphql",
            "query",
            "mutation",
            "operationName",
            "StatsLeaderboard",
            "IndividualGameStats",
            "TopFive",
            "statsLeaderboardApiUrl",
        ]

        for js_url in js_urls[:30]:
            try:
                js_response = safe_get(js_url)
                text = js_response.text

                hits = [
                    kw for kw in keywords
                    if kw.lower() in text.lower()
                ]

                if hits:
                    snippets = {}
                
                    for kw in hits:
                        lower_text = text.lower()
                        lower_kw = kw.lower()
                        idx = lower_text.find(lower_kw)
                
                        if idx != -1:
                            start = max(0, idx - 800)
                            end = min(len(text), idx + 1200)
                            snippets[kw] = text[start:end]
                
                    debug["matches"].append({
                        "js_url": js_url,
                        "hits": hits,
                        "snippets": snippets
                    })

            except Exception as exc:
                debug["matches"].append({
                    "js_url": js_url,
                    "error": str(exc)
                })

        return debug

    except Exception as exc:
        debug["error"] = str(exc)
        return debug


def test_atp_gateway():
    url = "https://app.atptour.com/api/v2/gateway"

    payload = {
        "operationName": None,
        "variables": {},
        "query": """
        query {
          __typename
        }
        """
    }

    debug = {
        "url": url,
        "http_status": None,
        "response_sample": None,
        "status": "not_started",
        "error": None,
    }

    try:
        r = requests.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
                "Origin": "https://www.atptour.com",
                "Referer": "https://www.atptour.com/",
            },
            timeout=25
        )

        debug["http_status"] = r.status_code
        debug["response_sample"] = r.text[:2000]
        debug["status"] = "ok"

    except Exception as e:
        debug["status"] = "exception"
        debug["error"] = str(e)

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
    parsed_players = parse_leaderboard_tests(leaderboard_test)
    gateway_test = test_atp_gateway()
    js_asset_debug = {
        "leaderboard": inspect_js_assets("https://www.atptour.com/en/stats/leaderboard"),
        "individual_game_stats": inspect_js_assets("https://www.atptour.com/en/stats/individual-game-stats"),
        "tdi_leaderboard": inspect_js_assets("https://www.atptour.com/en/stats/tdi-leaderboard"),
    }

    debug = {
        "updated_at": datetime.now(MADRID_TZ).isoformat(),
        "gateway_url": ATP_GATEWAY_URL,
        "leaderboard_test": leaderboard_test,
        "gateway_test": gateway_test,
        "js_asset_debug": js_asset_debug,
        "pages": pages,
    }

    safe_write_json(DEBUG_PATH, debug)

    output = {
        "updated_at": datetime.now(MADRID_TZ).isoformat(),
        "status": "ok",
        "source": "ATP StatsLeaderboard TopFive",
        "players": parsed_players
    }

    safe_write_json(OUTPUT_PATH, output)

    return {
        "status": "ok",
        "pages_checked": len(pages),
        "players_enriched": len(parsed_players),
    }
