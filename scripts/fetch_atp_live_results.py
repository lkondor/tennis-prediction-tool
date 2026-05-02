import json
import re
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen


TOURNAMENT_CONTEXT_PATH = Path("data/live/tournament_context.json")
OUTPUT_DIR = Path("data/raw/imports_live")


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
                "Mozilla/5.0 (compatible; tennis-madrid-tool/1.0; "
                "+https://github.com/)"
            )
        },
    )

    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def is_doubles_name(name):
    n = norm_name(name)
    return any(marker in n for marker in ["/", " & ", " + ", " and "])


def parse_score_sets(score_text):
    """
    Parser leggero. Non calcola aces/breaks.
    Serve solo per winner/score live results.
    """
    score_text = str(score_text or "").strip()
    return score_text


def extract_matches_from_text(text, context):
    """
    Parser euristico su testo ATP results.
    ATP cambia spesso markup, quindi qui estraiamo match completati
    tramite frase: 'X wins the match ...'
    """

    matches = []

    winner_patterns = list(
        re.finditer(
            r"Game Set and Match\s+(.+?)\.\s+(.+?)\s+wins the match\s+([0-9].+?)(?=Game Set and Match|$)",
            text,
            flags=re.I,
        )
    )

    for idx, m in enumerate(winner_patterns):
        winner_a = norm_name(m.group(1))
        winner_b = norm_name(m.group(2))
        score = parse_score_sets(m.group(3))

        winner = winner_b or winner_a

        # Prendi finestra testo prima della frase per cercare i due player.
        start = max(0, m.start() - 500)
        window = text[start:m.start()]

        # euristica: cerca nomi candidati prima dello score.
        # Rimuove rumore comune.
        window = re.sub(r"Image:\s*Player-Photo-[a-z0-9]+", " ", window, flags=re.I)
        window = re.sub(r"\bUmp:\b.*", " ", window, flags=re.I)
        window = re.sub(r"\s+", " ", window).strip()

        # Candidati: parole con iniziali maiuscole prima di numeri score.
        candidates = re.findall(
            r"\b[A-Z][a-zA-ZÀ-ÿ'\-]+(?:\s+[A-Z][a-zA-ZÀ-ÿ'\-]+){1,3}\b",
            window,
        )

        blacklist = {
            "Round",
            "Quarterfinals",
            "Semifinals",
            "Final",
            "Manolo Santana",
            "Arantxa Sanchez",
            "Stadium",
            "Court",
            "Game Set",
        }

        clean_candidates = []
        for c in candidates:
            c_norm = norm_name(c)
            if any(b.lower() in c_norm for b in blacklist):
                continue
            if c_norm not in clean_candidates:
                clean_candidates.append(c_norm)

        if winner not in clean_candidates:
            clean_candidates.append(winner)

        # L'avversario è l'ultimo candidato diverso dal winner.
        opponents = [c for c in clean_candidates if c != winner]

        if not opponents:
            continue

        opponent = opponents[-1]

        if is_doubles_name(winner) or is_doubles_name(opponent):
            continue

        match = {
            "date": "",
            "season": int(context.get("season", datetime.utcnow().year)),
            "tour": "atp",
            "tournament": context.get("tournament"),
            "tournament_slug": context.get("slug"),
            "surface": context.get("surface"),
            "round": "",
            "court": "",
            "player1": winner,
            "player2": opponent,
            "winner": winner,
            "score": score,
            "aces_p1": 0,
            "aces_p2": 0,
            "breaks_p1": 0,
            "breaks_p2": 0,
            "service_games_p1": 0,
            "service_games_p2": 0,
            "return_games_p1": 0,
            "return_games_p2": 0,
            "source": "atp_results_html",
            "imported_at": datetime.utcnow().isoformat(),
        }

        matches.append(match)

    return matches


def fetch_atp_live_results():
    context = load_json(TOURNAMENT_CONTEXT_PATH, {})
    slug = str(context.get("slug", "")).lower().strip()

    if slug not in ATP_RESULTS_URLS:
        print(f"No ATP results URL configured for slug: {slug}")
        return

    url = ATP_RESULTS_URLS[slug]
    html = fetch_html(url)
    text = clean_text(html)

    matches = extract_matches_from_text(text, context)

    output_path = OUTPUT_DIR / f"atp_live_{slug}_{context.get('season')}.json"
    save_json(output_path, matches)

    print(f"Fetched ATP results from: {url}")
    print(f"Parsed matches: {len(matches)}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    fetch_atp_live_results()
