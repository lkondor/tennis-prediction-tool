import csv
import json
import subprocess
from pathlib import Path
from datetime import datetime


IMPORT_DIR = Path("data/raw/imports")
OUTPUT_PATH = Path("data/raw/historical_matches.json")
BUILD_STATS_SCRIPT = Path("scripts/build_player_stats.py")


SUPPORTED_EXTENSIONS = {".csv"}


COLUMN_ALIASES = {
    "date": ["date", "tourney_date", "match_date"],
    "season": ["season", "year"],
    "tour": ["tour", "circuit"],
    "tournament": ["tournament", "tourney_name", "event_name"],
    "tournament_slug": ["tournament_slug", "slug", "event_slug"],
    "surface": ["surface"],
    "round": ["round", "round_name"],
    "court": ["court", "court_name"],

    "player1": ["player1", "player_1", "winner_name", "winner"],
    "player2": ["player2", "player_2", "loser_name", "loser"],
    "winner": ["winner", "winner_name"],

    "aces_p1": ["aces_p1", "p1_aces", "w_ace", "winner_aces"],
    "aces_p2": ["aces_p2", "p2_aces", "l_ace", "loser_aces"],

    "breaks_p1": ["breaks_p1", "p1_breaks", "w_breaks", "winner_breaks"],
    "breaks_p2": ["breaks_p2", "p2_breaks", "l_breaks", "loser_breaks"],

    "service_games_p1": [
        "service_games_p1",
        "p1_service_games",
        "w_service_games",
        "winner_service_games",
        "w_sv_gms",
    ],
    "service_games_p2": [
        "service_games_p2",
        "p2_service_games",
        "l_service_games",
        "loser_service_games",
        "l_sv_gms",
    ],

    "return_games_p1": [
        "return_games_p1",
        "p1_return_games",
        "w_return_games",
        "winner_return_games",
    ],
    "return_games_p2": [
        "return_games_p2",
        "p2_return_games",
        "l_return_games",
        "loser_return_games",
    ],

    "draw_type": ["draw_type", "draw", "event_type", "category"],
}


def norm_text(value):
    return str(value or "").strip()


def norm_name(value):
    return norm_text(value).lower()


def slugify(value):
    text = norm_name(value)
    replacements = {
        " ": "-",
        "_": "-",
        ".": "",
        ",": "",
        "'": "",
        "’": "",
        "(": "",
        ")": "",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    while "--" in text:
        text = text.replace("--", "-")

    return text.strip("-")


def read_json(path, default):
    if not path.exists():
        return default

    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return default
        return json.loads(text)
    except Exception:
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_first(row, aliases, default=None):
    for col in aliases:
        if col in row and norm_text(row.get(col)) != "":
            return row.get(col)

    return default


def get_field(row, field, default=None):
    return get_first(row, COLUMN_ALIASES.get(field, [field]), default)


def to_int(value, default=0):
    try:
        if value is None or norm_text(value) == "":
            return default
        return int(float(value))
    except Exception:
        return default


def normalize_date(value):
    raw = norm_text(value)

    if not raw:
        return ""

    # formato Jeff Sackmann: 20240425
    if raw.isdigit() and len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

    # formato già ISO
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]

    # fallback
    return raw


def infer_season(row, date):
    season = get_field(row, "season")

    if season:
        return to_int(season, None)

    if date and len(date) >= 4:
        return to_int(date[:4], None)

    return None


def infer_tour_from_file(path):
    name = path.name.lower()

    if "wta" in name:
        return "wta"

    if "atp" in name:
        return "atp"

    return ""


def is_doubles_name(name):
    n = norm_name(name)

    doubles_markers = [
        "/",
        " & ",
        " + ",
        " and ",
    ]

    return any(marker in n for marker in doubles_markers)


def is_doubles_row(row):
    draw_type = norm_name(get_field(row, "draw_type", ""))

    if "double" in draw_type:
        return True

    if "mixed" in draw_type:
        return True

    p1 = get_field(row, "player1", "")
    p2 = get_field(row, "player2", "")

    if is_doubles_name(p1) or is_doubles_name(p2):
        return True

    return False


def infer_return_games(service_games_opp):
    return service_games_opp


def normalize_match(row, source_path):
    if is_doubles_row(row):
        return None

    date = normalize_date(get_field(row, "date", ""))
    season = infer_season(row, date)

    player1 = norm_name(get_field(row, "player1", ""))
    player2 = norm_name(get_field(row, "player2", ""))
    winner = norm_name(get_field(row, "winner", player1))

    if not player1 or not player2:
        return None

    if is_doubles_name(player1) or is_doubles_name(player2):
        return None

    tour = norm_name(get_field(row, "tour", "")) or infer_tour_from_file(source_path)

    tournament = norm_text(get_field(row, "tournament", ""))
    tournament_slug = norm_name(get_field(row, "tournament_slug", ""))

    if not tournament_slug:
        tournament_slug = slugify(tournament)

    surface = norm_name(get_field(row, "surface", ""))
    round_name = norm_text(get_field(row, "round", ""))
    court = norm_text(get_field(row, "court", ""))

    aces_p1 = to_int(get_field(row, "aces_p1", 0))
    aces_p2 = to_int(get_field(row, "aces_p2", 0))

    breaks_p1 = to_int(get_field(row, "breaks_p1", 0))
    breaks_p2 = to_int(get_field(row, "breaks_p2", 0))

    service_games_p1 = to_int(get_field(row, "service_games_p1", 0))
    service_games_p2 = to_int(get_field(row, "service_games_p2", 0))

    return_games_p1 = to_int(get_field(row, "return_games_p1", 0))
    return_games_p2 = to_int(get_field(row, "return_games_p2", 0))

    if return_games_p1 == 0 and service_games_p2 > 0:
        return_games_p1 = infer_return_games(service_games_p2)

    if return_games_p2 == 0 and service_games_p1 > 0:
        return_games_p2 = infer_return_games(service_games_p1)

    return {
        "date": date,
        "season": season,
        "tour": tour,
        "tournament": tournament,
        "tournament_slug": tournament_slug,
        "surface": surface,
        "round": round_name,
        "court": court,

        "player1": player1,
        "player2": player2,
        "winner": winner,

        "aces_p1": aces_p1,
        "aces_p2": aces_p2,
        "breaks_p1": breaks_p1,
        "breaks_p2": breaks_p2,

        "service_games_p1": service_games_p1,
        "service_games_p2": service_games_p2,
        "return_games_p1": return_games_p1,
        "return_games_p2": return_games_p2,

        "source_file": source_path.name,
        "imported_at": datetime.utcnow().isoformat(),
    }


def make_match_id(match):
    return "|".join(
        [
            str(match.get("date", "")),
            str(match.get("tour", "")),
            str(match.get("tournament_slug", "")),
            str(match.get("player1", "")),
            str(match.get("player2", "")),
            str(match.get("round", "")),
        ]
    )


def read_csv_matches(path):
    matches = []

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            match = normalize_match(row, path)

            if match:
                matches.append(match)

    return matches


def import_historical_matches():
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)

    existing = read_json(OUTPUT_PATH, [])
    existing_by_id = {
        make_match_id(m): m
        for m in existing
    }

    imported = []
    skipped_files = []

    for path in sorted(IMPORT_DIR.iterdir()):
        print(f"Reading file: {path}")

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            skipped_files.append(path.name)
            continue

        file_matches = read_csv_matches(path)
        print(f"Parsed {len(file_matches)} matches from {path.name}")

        imported.extend(file_matches)

    
    added = 0
    updated = 0

    for match in imported:
        match_id = make_match_id(match)

        if match_id in existing_by_id:
            existing_by_id[match_id] = match
            updated += 1
        else:
            existing_by_id[match_id] = match
            added += 1

    output = sorted(
        existing_by_id.values(),
        key=lambda x: (
            str(x.get("date", "")),
            str(x.get("tour", "")),
            str(x.get("tournament_slug", "")),
            str(x.get("player1", "")),
        ),
    )

    write_json(OUTPUT_PATH, output)

    print(f"CSV files read: {len(imported)} matches parsed")
    print(f"Added: {added}")
    print(f"Updated: {updated}")
    print(f"Total historical matches: {len(output)}")
    print(f"Output: {OUTPUT_PATH}")

    if skipped_files:
        print(f"Skipped unsupported files: {', '.join(skipped_files)}")

    if BUILD_STATS_SCRIPT.exists():
        print("Running build_player_stats.py...")
        subprocess.run(
            ["python", str(BUILD_STATS_SCRIPT)],
            check=False,
        )


if __name__ == "__main__":
    import_historical_matches()
