import json
from pathlib import Path
from collections import defaultdict


OUT_DIR = Path("data/live")

RESULTS_HISTORY_PATH = OUT_DIR / "results_history.json"
ATP_INDEX_PATH = OUT_DIR / "atp_players_index.json"
WTA_INDEX_PATH = OUT_DIR / "wta_players_index.json"
ALIASES_PATH = OUT_DIR / "player_aliases.json"
OVERRIDES_PATH = OUT_DIR / "player_stat_overrides.json"


DEFAULT_PLAYER = {
    "elo_clay": 1800.0,
    "ace_rate_clay_3y": 0.25,
    "ace_allowed_clay_3y": 0.23,
    "break_rate_clay_3y": 0.20,
    "break_allowed_clay_3y": 0.18,
    "madrid_ace_rate": 0.0,
    "madrid_break_rate": 0.0,
    "data_quality": "fallback"
}


def safe_load_json(path, default):
    try:
        if not path.exists():
            return default
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return default
        return json.loads(text)
    except Exception:
        return default


def normalize_name(name):
    return str(name).lower().strip()


def load_results_history():
    return safe_load_json(RESULTS_HISTORY_PATH, [])


def load_player_indices():
    atp = safe_load_json(ATP_INDEX_PATH, [])
    wta = safe_load_json(WTA_INDEX_PATH, [])

    players = {}

    for item in atp:
        name = normalize_name(item.get("name", ""))
        if name:
            players[name] = {
                "tour": "ATP",
                "rank": item.get("rank")
            }

    for item in wta:
        name = normalize_name(item.get("name", ""))
        if name:
            players[name] = {
                "tour": "WTA",
                "rank": item.get("rank")
            }

    return players


def load_aliases():
    return safe_load_json(ALIASES_PATH, {})


def canonical_name(name, aliases=None):
    aliases = aliases or {}
    key = normalize_name(name)
    return normalize_name(aliases.get(key, key))


def compute_surface_elo(results, surface="Clay", base=1500.0, k=24.0):
    ratings = defaultdict(lambda: base)

    filtered = [
        r for r in results
        if str(r.get("surface", "")).lower() == surface.lower()
        and r.get("winner")
        and r.get("loser")
        and r.get("date")
    ]

    filtered.sort(key=lambda x: x["date"])

    for r in filtered:
        winner = normalize_name(r["winner"])
        loser = normalize_name(r["loser"])

        rw = ratings[winner]
        rl = ratings[loser]

        ew = 1 / (1 + 10 ** ((rl - rw) / 400))
        el = 1 - ew

        ratings[winner] = rw + k * (1 - ew)
        ratings[loser] = rl + k * (0 - el)

    return dict(ratings)


def aggregate_player_stats(results):
    """
    Expected fields in results_history.json:
    date, surface, tournament, winner, loser,
    player1, player2,
    aces_p1, aces_p2,
    service_games_p1, service_games_p2,
    breaks_p1, breaks_p2,
    return_games_p1, return_games_p2
    """

    year_weights = {
        "2023": 0.15,
        "2024": 0.25,
        "2025": 0.35,
        "2026": 0.25,
    }

    buckets = defaultdict(lambda: defaultdict(lambda: {
        "aces_for": 0,
        "aces_against": 0,
        "service_games": 0,
        "return_games": 0,
        "breaks_for": 0,
        "breaks_against": 0,
        "madrid_aces": 0,
        "madrid_breaks": 0,
        "madrid_matches": 0,
        "matches": 0,
    }))

    for r in results:
        if str(r.get("surface", "")).lower() != "clay":
            continue

        year = str(r.get("date", ""))[:4]
        if year not in year_weights:
            continue

        p1 = normalize_name(r.get("player1") or r.get("winner"))
        p2 = normalize_name(r.get("player2") or r.get("loser"))

        if not p1 or not p2:
            continue

        aces_p1 = float(r.get("aces_p1", 0) or 0)
        aces_p2 = float(r.get("aces_p2", 0) or 0)

        sg_p1 = float(r.get("service_games_p1", 0) or 0)
        sg_p2 = float(r.get("service_games_p2", 0) or 0)

        breaks_p1 = float(r.get("breaks_p1", 0) or 0)
        breaks_p2 = float(r.get("breaks_p2", 0) or 0)

        rg_p1 = float(r.get("return_games_p1", sg_p2) or sg_p2 or 0)
        rg_p2 = float(r.get("return_games_p2", sg_p1) or sg_p1 or 0)

        tournament = str(r.get("tournament", "")).lower()

        # p1
        b1 = buckets[p1][year]
        b1["aces_for"] += aces_p1
        b1["aces_against"] += aces_p2
        b1["service_games"] += sg_p1
        b1["return_games"] += rg_p1
        b1["breaks_for"] += breaks_p1
        b1["breaks_against"] += breaks_p2
        b1["matches"] += 1

        if tournament == "madrid":
            b1["madrid_aces"] += aces_p1
            b1["madrid_breaks"] += breaks_p1
            b1["madrid_matches"] += 1

        # p2
        b2 = buckets[p2][year]
        b2["aces_for"] += aces_p2
        b2["aces_against"] += aces_p1
        b2["service_games"] += sg_p2
        b2["return_games"] += rg_p2
        b2["breaks_for"] += breaks_p2
        b2["breaks_against"] += breaks_p1
        b2["matches"] += 1

        if tournament == "madrid":
            b2["madrid_aces"] += aces_p2
            b2["madrid_breaks"] += breaks_p2
            b2["madrid_matches"] += 1

    output = {}

    for player, years in buckets.items():
        ace_rates = []
        ace_allowed_rates = []
        break_rates = []
        break_allowed_rates = []
        weights = []

        madrid_aces = 0
        madrid_breaks = 0
        madrid_matches = 0
        total_matches = 0

        for year, weight in year_weights.items():
            y = years.get(year)
            if not y:
                continue

            sg = y["service_games"]
            rg = y["return_games"]

            ace_rates.append(y["aces_for"] / sg if sg else 0)
            ace_allowed_rates.append(y["aces_against"] / rg if rg else 0)
            break_rates.append(y["breaks_for"] / rg if rg else 0)
            break_allowed_rates.append(y["breaks_against"] / sg if sg else 0)
            weights.append(weight)

            madrid_aces += y["madrid_aces"]
            madrid_breaks += y["madrid_breaks"]
            madrid_matches += y["madrid_matches"]
            total_matches += y["matches"]

        if not weights:
            continue

        total_weight = sum(weights)

        def weighted(values):
            return sum(v * w for v, w in zip(values, weights)) / total_weight

        output[player] = {
            "ace_rate_clay_3y": round(weighted(ace_rates), 4),
            "ace_allowed_clay_3y": round(weighted(ace_allowed_rates), 4),
            "break_rate_clay_3y": round(weighted(break_rates), 4),
            "break_allowed_clay_3y": round(weighted(break_allowed_rates), 4),
            "madrid_ace_rate": round(madrid_aces / madrid_matches, 4) if madrid_matches else 0.0,
            "madrid_break_rate": round(madrid_breaks / madrid_matches, 4) if madrid_matches else 0.0,
            "matches_in_backfill": total_matches,
            "data_quality": "historical_match_stats"
        }

    return output


def load_stat_overrides():
    return safe_load_json(OVERRIDES_PATH, {})


def build_players_database():
    aliases = load_aliases()
    indexed_players = load_player_indices()
    results = load_results_history()

    elo_map = compute_surface_elo(results, surface="Clay")
    stats_map = aggregate_player_stats(results)

    all_names = set(indexed_players.keys()) | set(elo_map.keys()) | set(stats_map.keys())

    players = {}

    for raw_name in sorted(all_names):
        name = canonical_name(raw_name, aliases)

        base = dict(DEFAULT_PLAYER)

        if raw_name in indexed_players:
            base.update(indexed_players[raw_name])

        if raw_name in stats_map:
            base.update(stats_map[raw_name])

        if raw_name in elo_map:
            base["elo_clay"] = round(elo_map[raw_name], 1)

        players[name] = base

    overrides = load_stat_overrides()

    for raw_name, override in overrides.items():
        name = canonical_name(raw_name, aliases)

        players.setdefault(name, dict(DEFAULT_PLAYER))
        players[name].update(override)
        players[name]["data_quality"] = "official_override"
    
    return players
