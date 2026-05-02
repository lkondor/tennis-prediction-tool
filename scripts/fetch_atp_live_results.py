import json
import re
import time
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError


TOURNAMENT_CONTEXT_PATH = Path("data/live/tournament_context.json")
OUTPUT_DIR = Path("data/raw/imports_live")

MAX_MATCH_STATS_PER_RUN = 8
REQUEST_SLEEP_SECONDS = 8


ATP_RESULTS_URLS = {
    "madrid": "https://www.atptour.com/en/scores/current/atp-masters-1000-madrid/1536/results",
    "rome": "https://www.atptour.com/en/scores/current/rome/0416/results",
}


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


def norm_name(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s*\([^)]*\)", "", value)
    return value.strip()


def clean_text(html):
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_html(url):
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )

    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def is_doubles_name(name):
    n = norm_name(name)
    return any(marker in n for marker in ["/", " & ", " + ", " and "])


def extract_match_ids(html):
    """
    Estrae link Stats Centre:
    /en/scores/stats-centre/archive/2026/1536/ms016
    /en/scores/stats-centre/live/2026/1536/ms016
    """
    raw_matches = re.findall(
        r"/en/scores/stats-centre/(archive|live)/(\d{4})/(\d+)/([a-z0-9]+)",
        html,
        flags=re.I,
    )

    seen = set()
    result = []

    for mode, year, tournament_id, match_id in raw_matches:
        key = (mode.lower(), year, tournament_id, match_id.lower())

        if key in seen:
            continue

        seen.add(key)

        result.append(
            {
                "mode": mode.lower(),
                "year": year,
                "tournament_id": tournament_id,
                "match_id": match_id.lower(),
            }
        )

    return result


def fetch_match_stats_html(mode, year, tournament_id, match_id):
    url = (
        f"https://www.atptour.com/en/scores/stats-centre/"
        f"{mode}/{year}/{tournament_id}/{match_id}"
    )
    return fetch_html(url), url


def extract_embedded_json_objects(html):
    """
    ATP spesso inserisce dati in JSON/props dentro HTML.
    Qui non assumiamo una struttura unica: cerchiamo pattern testuali.
    """
    return html


def extract_player_names_from_stats(html):
    """
    Prova a estrarre i nomi player dalla pagina Stats Centre.
    Fallback conservativo.
    """
    text = clean_text(html)

    # Pattern frequenti in Stats Centre: nomi vicino a Player Stats.
    candidates = re.findall(
        r"\b[A-Z][a-zA-ZÀ-ÿ'\-]+(?:\s+[A-Z][a-zA-ZÀ-ÿ'\-]+){1,3}\b",
        text,
    )

    blacklist_terms = [
        "Stats Centre",
        "ATP Tour",
        "Infosys ATP",
        "Match Stats",
        "Player Stats",
        "Service Stats",
        "Return Stats",
        "Break Points",
        "Total Points",
        "Official Tennis",
        "Game Set",
        "Manolo Santana",
        "Arantxa Sanchez",
    ]

    clean = []

    for c in candidates:
        c_norm = norm_name(c)

        if any(term.lower() in c_norm for term in blacklist_terms):
            continue

        if len(c_norm) < 4:
            continue

        if c_norm not in clean:
            clean.append(c_norm)

    # euristica: i primi due nomi validi sono spesso i giocatori
    if len(clean) >= 2:
        return clean[0], clean[1]

    return "", ""


def extract_score_from_stats(html):
    text = clean_text(html)

    score_match = re.search(
        r"\b(\d-\d(?:\s+\d-\d|\s+\d-\d\(\d+\)|\s+\d-\d\(\d+\))*)\b",
        text,
    )

    if score_match:
        return score_match.group(1)

    return ""


def extract_stat_pair_from_html(html, label):
    """
    Cerca coppie numeriche vicino alla label.
    Funziona sia con HTML testuale sia con JSON embedded.
    """
    label_escaped = re.escape(label)

    patterns = [
        rf"{label_escaped}[^0-9]{{0,300}}(\d+)[^0-9]{{1,120}}(\d+)",
        rf'"{label_escaped}"[^0-9]{{0,300}}(\d+)[^0-9]{{1,120}}(\d+)',
        rf"{label_escaped}.*?value[^0-9]*(\d+).*?value[^0-9]*(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, html, flags=re.I | re.S)

        if match:
            return int(match.group(1)), int(match.group(2))

    return 0, 0


def extract_percentage_pair_from_html(html, label):
    label_escaped = re.escape(label)

    pattern = rf"{label_escaped}[^0-9]{{0,300}}(\d+)%[^0-9]{{1,120}}(\d+)%"
    match = re.search(pattern, html, flags=re.I | re.S)

    if match:
        return int(match.group(1)), int(match.group(2))

    return 0, 0


def parse_break_points_converted(html):
    """
    Possibili formati:
    - Break Points Converted 3/8 1/4
    - Break Points Converted 38% 25%
    Restituisce break convertiti, cioè breaks.
    """
    text = clean_text(html)

    m = re.search(
        r"Break Points Converted[^0-9]{0,100}(\d+)\s*/\s*(\d+)[^0-9]{1,80}(\d+)\s*/\s*(\d+)",
        text,
        flags=re.I,
    )

    if m:
        return int(m.group(1)), int(m.group(3))

    return extract_stat_pair_from_html(html, "Break Points Converted")


def parse_service_games(html):
    return extract_stat_pair_from_html(html, "Service Games Played")


def parse_match_stats(html):
    aces_p1, aces_p2 = extract_stat_pair_from_html(html, "Aces")
    breaks_p1, breaks_p2 = parse_break_points_converted(html)
    service_games_p1, service_games_p2 = parse_service_games(html)

    if service_games_p1 == 0 and service_games_p2 == 0:
        # fallback: prova label alternativa
        service_games_p1, service_games_p2 = extract_stat_pair_from_html(
            html,
            "Service Games",
        )

    return_games_p1 = service_games_p2
    return_games_p2 = service_games_p1

    first_serve_pct_p1, first_serve_pct_p2 = extract_percentage_pair_from_html(
        html,
        "1st Serve",
    )

    return {
        "aces_p1": aces_p1,
        "aces_p2": aces_p2,
        "breaks_p1": breaks_p1,
        "breaks_p2": breaks_p2,
        "service_games_p1": service_games_p1,
        "service_games_p2": service_games_p2,
        "return_games_p1": return_games_p1,
        "return_games_p2": return_games_p2,
        "first_serve_pct_p1": first_serve_pct_p1,
        "first_serve_pct_p2": first_serve_pct_p2,
    }


def make_match_record(match_ref, stats_html, stats_url, context):
    player1, player2 = extract_player_names_from_stats(stats_html)

    if is_doubles_name(player1) or is_doubles_name(player2):
        return None

    stats = parse_match_stats(stats_html)
    score = extract_score_from_stats(stats_html)

    # Se non abbiamo player names, salviamo comunque record diagnostico ma non utile al model.
    if not player1 or not player2:
        return {
            "date": "",
            "season": int(match_ref.get("year", context.get("season", datetime.utcnow().year))),
            "tour": "atp",
            "tournament": context.get("tournament"),
            "tournament_slug": context.get("slug"),
            "surface": context.get("surface"),
            "round": "",
            "court": "",
            "player1": "",
            "player2": "",
            "winner": "",
            "score": score,
            **stats,
            "stats_url": stats_url,
            "match_id": match_ref.get("match_id"),
            "tournament_id": match_ref.get("tournament_id"),
            "source": "atp_stats_centre",
            "parse_status": "missing_players",
            "imported_at": datetime.utcnow().isoformat(),
        }

    return {
        "date": "",
        "season": int(match_ref.get("year", context.get("season", datetime.utcnow().year))),
        "tour": "atp",
        "tournament": context.get("tournament"),
        "tournament_slug": context.get("slug"),
        "surface": context.get("surface"),
        "round": "",
        "court": "",
        "player1": player1,
        "player2": player2,
        "winner": "",
        "score": score,
        **stats,
        "stats_url": stats_url,
        "match_id": match_ref.get("match_id"),
        "tournament_id": match_ref.get("tournament_id"),
        "source": "atp_stats_centre",
        "parse_status": "ok",
        "imported_at": datetime.utcnow().isoformat(),
    }


def fetch_atp_live_results():
    context = load_json(TOURNAMENT_CONTEXT_PATH, {})
    slug = str(context.get("slug", "")).lower().strip()

    if slug not in ATP_RESULTS_URLS:
        print(f"No ATP results URL configured for slug: {slug}")
        return

    url = ATP_RESULTS_URLS[slug]
    html = fetch_html(url)

    match_refs = extract_match_ids(html)

    print(f"Fetched ATP results from: {url}")
    print(f"Found stats-centre match ids: {len(match_refs)}")

    records = []

    for i, match_ref in enumerate(match_refs[:MAX_MATCH_STATS_PER_RUN], start=1):
        try:
            stats_html, stats_url = fetch_match_stats_html(
                match_ref["mode"],
                match_ref["year"],
                match_ref["tournament_id"],
                match_ref["match_id"],
            )

            record = make_match_record(match_ref, stats_html, stats_url, context)

            if record:
                records.append(record)

            print(
                f"[{i}/{min(len(match_refs), MAX_MATCH_STATS_PER_RUN)}] "
                f"{match_ref['match_id']} -> "
                f"{record.get('parse_status') if record else 'skipped'}"
            )

            time.sleep(REQUEST_SLEEP_SECONDS)

        except HTTPError as e:
            print(f"HTTP error {e.code} on {match_ref}")

            if e.code == 403:
                print("ATP returned 403. Stopping this run to avoid further blocking.")
                break

        except Exception as e:
            print(f"Error fetching stats for {match_ref}: {e}")

    
    output_path = OUTPUT_DIR / f"atp_live_{slug}_{context.get('season')}.json"
    save_json(output_path, records)

    ok_count = sum(1 for r in records if r.get("parse_status") == "ok")
    missing_players = sum(1 for r in records if r.get("parse_status") == "missing_players")

    print(f"Parsed records: {len(records)}")
    print(f"OK records: {ok_count}")
    print(f"Missing player records: {missing_players}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    fetch_atp_live_results()
