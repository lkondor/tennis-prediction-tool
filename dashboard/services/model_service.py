import json
import math
import random
from pathlib import Path


PLAYERS_PATH = Path("data/live/players.json")
WEATHER_PATH = Path("data/live/weather.json")
ALIASES_PATH = Path("data/live/player_aliases.json")
ATP_STATS_PATH = Path("data/live/atp_enriched_stats.json")
TOURNAMENT_CONTEXT_PATH = Path("data/live/tournament_context.json")


ATP_SERVE_BASELINE = 270.0
ATP_RETURN_BASELINE = 170.0
ATP_PRESSURE_BASELINE = 190.0

ATP_SERVE_SCALE = 35.0
ATP_RETURN_SCALE = 30.0
ATP_PRESSURE_SCALE = 30.0

MAX_ACE_BOOST = 0.18
MAX_BREAK_BOOST = 0.16
MAX_PRESSURE_BREAK_BOOST = 0.04
MAX_CONFIDENCE_BOOST_PER_PLAYER = 0.04

MAX_ATP_ELO_BOOST = 35

def load_json(path, default=None):
    if default is None:
        default = {}

    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_players():
    return load_json(PLAYERS_PATH, {})


def load_weather():
    return load_json(WEATHER_PATH, {})


def load_aliases():
    return load_json(ALIASES_PATH, {})


def load_atp_enriched_stats():
    data = load_json(ATP_STATS_PATH, {})
    return {
        "atp": data.get("atp", {}),
        "wta": data.get("wta", {}),
    }

def load_tournament_context():
    default_context = {
        "tournament": "Madrid Open",
        "slug": "madrid",
        "season": 2026,
        "surface": "clay",
        "tour": "combined",
        "location": "Madrid",
        "altitude_m": 667,
        "ace_environment_factor": 1.15,
        "break_environment_factor": 1.00,
    }

    if not TOURNAMENT_CONTEXT_PATH.exists():
        return default_context

    try:
        with open(TOURNAMENT_CONTEXT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {**default_context, **data}
    except Exception:
        return default_context

def norm_name(name):
    return str(name).lower().strip()


def detect_tour(player_name, players):
    p = players.get(player_name, {})

    # Se hai campo gender/source → usa quello
    if "tour" in p:
        return p["tour"]

    # fallback euristico
    name = player_name.lower()

    wta_names = [
        "swiatek",
        "sabalenka",
        "rybakina",
        "gauff",
        "pegula",
        "zheng",
        "jabeur",
    ]

    if any(n in name for n in wta_names):
        return "wta"

    return "atp"


def is_doubles_player_name(name):
    n = norm_name(name)

    doubles_markers = [
        "/",
        " & ",
        " and ",
        " + ",
    ]

    return any(marker in n for marker in doubles_markers)


def is_doubles_match(match):
    return (
        is_doubles_player_name(getattr(match, "player1", ""))
        or is_doubles_player_name(getattr(match, "player2", ""))
    )


def bounded_rating_delta(value, baseline, scale, max_abs=1.0):
    if value is None:
        return 0.0

    try:
        z = (float(value) - baseline) / scale
    except Exception:
        return 0.0

    return max(-max_abs, min(max_abs, z))


def quality_score(player):
    q = player.get("data_quality", "fallback")

    if q == "official_override":
        return 1.00
    if q == "historical_match_stats":
        return 0.80
    if q == "synthetic":
        return 0.55
    if q == "unresolved":
        return 0.25

    return 0.40

def atp_elo_boost_from_adjustment(atp_adjustment):
    """
    Converte i rating ATP/WTA enriched in piccolo boost ELO.
    Serve + return + pressure incidono sulla win probability,
    ma con cap massimo per evitare overfitting.
    """

    if not atp_adjustment.get("has_atp"):
        return 0

    serve_delta = atp_adjustment.get("serve_delta", 0.0)
    return_delta = atp_adjustment.get("return_delta", 0.0)
    pressure_delta = atp_adjustment.get("pressure_delta", 0.0)

    raw_boost = (
        serve_delta * 10
        + return_delta * 15
        + pressure_delta * 10
    )

    return round(
        max(-MAX_ATP_ELO_BOOST, min(MAX_ATP_ELO_BOOST, raw_boost))
    )


def apply_atp_rating_adjustments(
    player_name,
    ace_rate,
    break_rate,
    atp_stats,
    players,
    season=2026,
    surface="clay",
):
    """
    Usa ATP/WTA enriched stats solo se il player è presente.

    serve_rating    -> ace_rate
    return_rating   -> break_rate
    pressure_rating -> break_rate leggero + confidence
    """

    tour = detect_tour(player_name, players)
    tour_stats = atp_stats.get(tour, {})
    
    key = norm_name(player_name)
    
    if key not in tour_stats:
        return {
            "ace_rate": ace_rate,
            "break_rate": break_rate,
            "has_atp": False,
            "serve_rating": None,
            "return_rating": None,
            "pressure_rating": None,
            "serve_delta": 0.0,
            "return_delta": 0.0,
            "pressure_delta": 0.0,
            "confidence_boost": 0.0,
        }

    p = tour_stats[key]
    suffix = f"{season}_{surface.lower()}"

    serve_rating = p.get(f"serve_rating_{suffix}")
    return_rating = p.get(f"return_rating_{suffix}")
    pressure_rating = p.get(f"pressure_rating_{suffix}")

    serve_delta = bounded_rating_delta(
        serve_rating,
        ATP_SERVE_BASELINE,
        ATP_SERVE_SCALE,
    )

    return_delta = bounded_rating_delta(
        return_rating,
        ATP_RETURN_BASELINE,
        ATP_RETURN_SCALE,
    )

    pressure_delta = bounded_rating_delta(
        pressure_rating,
        ATP_PRESSURE_BASELINE,
        ATP_PRESSURE_SCALE,
    )

    ace_boost = serve_delta * MAX_ACE_BOOST

    break_boost = (
        return_delta * MAX_BREAK_BOOST
        + pressure_delta * MAX_PRESSURE_BREAK_BOOST
    )

    ace_boost = max(-MAX_ACE_BOOST, min(MAX_ACE_BOOST, ace_boost))
    break_boost = max(-MAX_BREAK_BOOST, min(MAX_BREAK_BOOST, break_boost))

    confidence_boost = max(
        0.0,
        min(
            MAX_CONFIDENCE_BOOST_PER_PLAYER,
            pressure_delta * MAX_CONFIDENCE_BOOST_PER_PLAYER,
        ),
    )

    return {
        "ace_rate": max(0.0, ace_rate * (1.0 + ace_boost)),
        "break_rate": max(0.0, break_rate * (1.0 + break_boost)),
        "has_atp": True,
        "serve_rating": serve_rating,
        "return_rating": return_rating,
        "pressure_rating": pressure_rating,
        "serve_delta": round(serve_delta, 3),
        "return_delta": round(return_delta, 3),
        "pressure_delta": round(pressure_delta, 3),
        "confidence_boost": confidence_boost,
    }


def resolve_player_key(display_name, players):
    aliases = load_aliases()
    name = norm_name(display_name)

    if name in aliases and aliases[name] in players:
        return aliases[name]

    manual_aliases = {
        "q. zheng": "qinwen zheng",
        "s. kenin": "sofia kenin",
        "j. sinner": "jannik sinner",
        "c. alcaraz": "carlos alcaraz",
        "a. zverev": "alexander zverev",
        "d. medvedev": "daniil medvedev",
        "h. hurkacz": "hubert hurkacz",
        "l. musetti": "lorenzo musetti",
        "b. shelton": "ben shelton",
        "i. swiatek": "iga swiatek",
        "a. sabalenka": "aryna sabalenka",
        "e. rybakina": "elena rybakina",
    }

    if name in manual_aliases and manual_aliases[name] in players:
        return manual_aliases[name]

    cleaned = name.replace(".", "").strip()
    parts = cleaned.split()

    if len(parts) >= 2 and len(parts[0]) == 1:
        initial = parts[0][0]
        surname = " ".join(parts[1:])

        for key in players.keys():
            key_parts = key.split()

            if len(key_parts) < 2:
                continue

            key_initial = key_parts[0][0]
            key_surname = " ".join(key_parts[1:])

            if key_initial == initial and key_surname == surname:
                return key

            if key_initial == initial and key.endswith(surname):
                return key

    if name in players:
        return name

    return name


def win_prob(elo_a, elo_b):
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


def court_factor(court):
    c = str(court).lower()

    if "court 4" in c:
        return 1.08
    if "manolo" in c:
        return 1.02
    if "arantxa" in c:
        return 1.01

    return 1.0


def ace_weather_factor(avg_temp, wind_kmh):
    factor = 1.0

    if avg_temp is not None:
        factor *= 1 + ((avg_temp - 20) * 0.01)

    if wind_kmh is not None:
        factor *= max(0.8, 1 - wind_kmh * 0.01)

    return round(factor, 3)


def break_weather_factor(avg_temp, wind_kmh):
    factor = 1.0

    if avg_temp is not None and avg_temp < 18:
        factor *= 1.03

    if wind_kmh is not None:
        factor *= 1 + min(0.12, wind_kmh * 0.005)

    return round(factor, 3)


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))

    if na == 0 or nb == 0:
        return 0.0

    return dot / (na * nb)


def safe_num(value, default=0.0):
    return value if value is not None else default


def build_feature_vector(player_data):
    return [
        safe_num(player_data.get("elo_clay"), 1800) / 2500.0,
        safe_num(player_data.get("ace_rate_clay_3y"), 0),
        safe_num(player_data.get("ace_allowed_clay_3y"), 0),
        safe_num(player_data.get("break_rate_clay_3y"), 0),
        safe_num(player_data.get("break_allowed_clay_3y"), 0),
        safe_num(player_data.get("madrid_ace_rate"), 0),
        safe_num(player_data.get("madrid_break_rate"), 0),
    ]


def find_similar_players(player_name, all_players, top_n=5):
    if player_name not in all_players:
        return []

    target_vec = build_feature_vector(all_players[player_name])
    scores = []

    for other_name, other_data in all_players.items():
        if other_name == player_name:
            continue

        other_vec = build_feature_vector(other_data)
        sim = cosine_similarity(target_vec, other_vec)
        scores.append((other_name, sim))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_n]


def adjusted_elo(player):
    elo = player.get("elo_clay") if player.get("elo_clay") is not None else 1800

    if player.get("data_quality") == "official_override":
        return elo + 50

    if player.get("data_quality") == "synthetic":
        return elo - 30

    return elo


def safe_stat(player, field, default):
    value = player.get(field)
    return value if value is not None else default


def weighted_stat(value, player):
    if player.get("data_quality") == "official_override":
        return value * 1.15

    if player.get("data_quality") == "synthetic":
        return value * 0.90

    return value


def monte_carlo_values(mean, simulations=1000):
    values = []

    for _ in range(simulations):
        value = random.gauss(mean, max(mean * 0.25, 0.8))
        values.append(max(0, value))

    values.sort()
    return values


def summarize_distribution(values):
    return {
        "mean": round(sum(values) / len(values), 2),
        "p10": round(values[int(0.10 * len(values))], 2),
        "p50": round(values[int(0.50 * len(values))], 2),
        "p90": round(values[int(0.90 * len(values))], 2),
    }


def blend_stats(player):
    """
    Combina:
    - surface stats (base)
    - tournament history
    - current tournament
    """

    surface_weight = 0.55
    tournament_weight = 0.25

    current_matches = player.get("current_tournament_matches", 0)
    current_weight = min(0.25, current_matches * 0.08)

    # normalizza pesi
    total = surface_weight + tournament_weight + current_weight
    surface_weight /= total
    tournament_weight /= total
    current_weight /= total

    def w(field_surface, field_tourn, field_current):
        return (
            (player.get(field_surface, 0) * surface_weight)
            + (player.get(field_tourn, 0) * tournament_weight)
            + (player.get(field_current, 0) * current_weight)
        )

    return {
        "ace_rate": w(
            "ace_rate_surface_3y",
            "tournament_ace_rate_3ed",
            "current_tournament_ace_rate",
        ),
        "ace_allowed": w(
            "ace_allowed_surface_3y",
            "tournament_ace_allowed_3ed",
            "current_tournament_ace_allowed",
        ),
        "break_rate": w(
            "break_rate_surface_3y",
            "tournament_break_rate_3ed",
            "current_tournament_break_rate",
        ),
        "break_allowed": w(
            "break_allowed_surface_3y",
            "tournament_break_allowed_3ed",
            "current_tournament_break_allowed",
        ),
    }

def apply_context_adjustments(player, base_value, stat_type, court, avg_temp, wind_kmh):
    adj = base_value

    court_key = str(court).lower().strip()
    court_adj = player.get("court_adjustments", {}).get(court_key)

    if court_adj and court_adj.get("matches", 0) >= 1:
        adj = (adj * 0.85) + (court_adj.get(stat_type, adj) * 0.15)

    weather_adj = player.get("weather_adjustments", {})

    if avg_temp is not None and avg_temp >= 26 and "hot" in weather_adj:
        adj = (adj * 0.9) + (weather_adj["hot"].get(stat_type, adj) * 0.1)

    if avg_temp is not None and avg_temp <= 18 and "cool" in weather_adj:
        adj = (adj * 0.9) + (weather_adj["cool"].get(stat_type, adj) * 0.1)

    if wind_kmh is not None and wind_kmh >= 15 and "windy" in weather_adj:
        adj = (adj * 0.9) + (weather_adj["windy"].get(stat_type, adj) * 0.1)

    return max(0.0, adj)


def run_prediction(match):
    if is_doubles_match(match):
        return {
            "playerA": {"aces": 0, "breaks": 0},
            "playerB": {"aces": 0, "breaks": 0},
            "totals": {"aces": 0, "breaks": 0},
        }, {
            "skipped": True,
            "skip_reason": "doubles_match",
            "matched_player_a": str(getattr(match, "player1", "")),
            "matched_player_b": str(getattr(match, "player2", "")),
        }

    players = load_players()
    weather = load_weather()
    atp_stats = load_atp_enriched_stats()
    tournament_context = load_tournament_context()
    
    season = int(tournament_context.get("season", 2026))
    surface = str(tournament_context.get("surface", "clay")).lower()
    ace_environment_factor = float(tournament_context.get("ace_environment_factor", 1.0))
    break_environment_factor = float(tournament_context.get("break_environment_factor", 1.0))

    a_name = resolve_player_key(match.player1, players)
    b_name = resolve_player_key(match.player2, players)

    a = players.get(a_name, {})
    b = players.get(b_name, {})

    day_weather = weather.get(match.date, {})
    avg_temp = day_weather.get("avg_temp")
    wind_kmh = day_weather.get("wind_kmh")

    elo_a = adjusted_elo(a)
    elo_b = adjusted_elo(b)

    blend_a = blend_stats(a)
    blend_b = blend_stats(b)

    ace_rate_a_raw = blend_a["ace_rate"]
    ace_rate_b_raw = blend_b["ace_rate"]

    ace_allowed_a = blend_a["ace_allowed"]
    ace_allowed_b = blend_b["ace_allowed"]

    break_rate_a_raw = blend_a["break_rate"]
    break_rate_b_raw = blend_b["break_rate"]

    break_allowed_a = blend_a["break_allowed"]
    break_allowed_b = blend_b["break_allowed"]

    atp_a = apply_atp_rating_adjustments(
        player_name=a_name,
        ace_rate=ace_rate_a_raw,
        break_rate=break_rate_a_raw,
        atp_stats=atp_stats,
        players=players,
        season=season,
        surface=surface,
    )

    atp_b = apply_atp_rating_adjustments(
        player_name=b_name,
        ace_rate=ace_rate_b_raw,
        break_rate=break_rate_b_raw,
        atp_stats=atp_stats,
        players=players,
        season=season,
        surface=surface,
    )

    ace_rate_a = apply_context_adjustments(
        player=a,
        base_value=atp_a["ace_rate"],
        stat_type="ace_rate",
        court=match.court,
        avg_temp=avg_temp,
        wind_kmh=wind_kmh,
    )

    ace_rate_b = apply_context_adjustments(
        player=b,
        base_value=atp_b["ace_rate"],
        stat_type="ace_rate",
        court=match.court,
        avg_temp=avg_temp,
        wind_kmh=wind_kmh,
    )

    break_rate_a = apply_context_adjustments(
        player=a,
        base_value=atp_a["break_rate"],
        stat_type="break_rate",
        court=match.court,
        avg_temp=avg_temp,
        wind_kmh=wind_kmh,
    )

    break_rate_b = apply_context_adjustments(
        player=b,
        base_value=atp_b["break_rate"],
        stat_type="break_rate",
        court=match.court,
        avg_temp=avg_temp,
        wind_kmh=wind_kmh,
    )

    ace_allowed_a = apply_context_adjustments(
        player=a,
        base_value=ace_allowed_a,
        stat_type="ace_allowed",
        court=match.court,
        avg_temp=avg_temp,
        wind_kmh=wind_kmh,
    )

    ace_allowed_b = apply_context_adjustments(
        player=b,
        base_value=ace_allowed_b,
        stat_type="ace_allowed",
        court=match.court,
        avg_temp=avg_temp,
        wind_kmh=wind_kmh,
    )

    break_allowed_a = apply_context_adjustments(
        player=a,
        base_value=break_allowed_a,
        stat_type="break_allowed",
        court=match.court,
        avg_temp=avg_temp,
        wind_kmh=wind_kmh,
    )

    break_allowed_b = apply_context_adjustments(
        player=b,
        base_value=break_allowed_b,
        stat_type="break_allowed",
        court=match.court,
        avg_temp=avg_temp,
        wind_kmh=wind_kmh,
    )

    atp_elo_boost_a = atp_elo_boost_from_adjustment(atp_a)
    atp_elo_boost_b = atp_elo_boost_from_adjustment(atp_b)

    elo_a_model = elo_a + atp_elo_boost_a
    elo_b_model = elo_b + atp_elo_boost_b

    p_a = win_prob(elo_a_model, elo_b_model)
    p_b = 1 - p_a
    model_edge = abs(p_a - 0.5) * 2

    c_factor = court_factor(match.court)

    # Legacy tournament factor.
    # Lo teniamo per ora, ma nel prossimo step lo renderemo dinamico via tournament_context.json.
    madrid_factor = ace_environment_factor

    match_length = 1.08 + (1 - abs(p_a - 0.5)) * 0.5

    ace_wf = ace_weather_factor(avg_temp, wind_kmh)
    break_wf = break_weather_factor(avg_temp, wind_kmh)

    sim_a = find_similar_players(a_name, players, top_n=3)
    sim_b = find_similar_players(b_name, players, top_n=3)

    sim_boost_a = 1.0 + (0.01 * len(sim_a))
    sim_boost_b = 1.0 + (0.01 * len(sim_b))

    aces_a = round(
        ((ace_rate_a + ace_allowed_b) / 2)
        * 20
        * c_factor
        * madrid_factor
        * match_length
        * ace_wf
        * sim_boost_a,
        1,
    )

    aces_b = round(
        ((ace_rate_b + ace_allowed_a) / 2)
        * 20
        * c_factor
        * madrid_factor
        * match_length
        * ace_wf
        * sim_boost_b,
        1,
    )

    breaks_a = round(
        ((break_rate_a + break_allowed_b) / 2)
        * 10
        * (1.12 - (c_factor - 1) * 0.5)
        * break_wf
        * break_environment_factor,
        1,
    )

    breaks_b = round(
        ((break_rate_b + break_allowed_a) / 2)
        * 10
        * (1.12 - (c_factor - 1) * 0.5)
        * break_wf
        * break_environment_factor,
        1,
    )

    mc_aces_a_values = monte_carlo_values(aces_a)
    mc_aces_b_values = monte_carlo_values(aces_b)
    mc_breaks_a_values = monte_carlo_values(breaks_a)
    mc_breaks_b_values = monte_carlo_values(breaks_b)

    mc_total_aces_values = [
        a_val + b_val
        for a_val, b_val in zip(mc_aces_a_values, mc_aces_b_values)
    ]

    mc_total_breaks_values = [
        a_val + b_val
        for a_val, b_val in zip(mc_breaks_a_values, mc_breaks_b_values)
    ]

    mc_aces_a = summarize_distribution(mc_aces_a_values)
    mc_aces_b = summarize_distribution(mc_aces_b_values)
    mc_breaks_a = summarize_distribution(mc_breaks_a_values)
    mc_breaks_b = summarize_distribution(mc_breaks_b_values)

    mc_total_aces = summarize_distribution(mc_total_aces_values)
    mc_total_breaks = summarize_distribution(mc_total_breaks_values)

    stat_diff = (
        abs(ace_rate_a - ace_rate_b)
        + abs(break_rate_a - break_rate_b)
    ) / 2

    stat_consistency = min(stat_diff * 2, 1.0)

    data_confidence = (quality_score(a) + quality_score(b)) / 2
    weather_confidence = 1.0 if avg_temp is not None and wind_kmh is not None else 0.6
    court_confidence = 1.0 if match.court else 0.7

    atp_confidence_boost = (
        atp_a["confidence_boost"]
        + atp_b["confidence_boost"]
    )

    confidence_score = round(
        min(
            1.0,
            (data_confidence * 0.45)
            + (model_edge * 0.30)
            + (stat_consistency * 0.15)
            + (weather_confidence * 0.10)
            + atp_confidence_boost,
        ),
        3,
    )

    if confidence_score >= 0.75:
        confidence_label = "Alta"
    elif confidence_score >= 0.55:
        confidence_label = "Media"
    else:
        confidence_label = "Bassa"

    ace_edge = abs(aces_a - aces_b) / max(aces_a + aces_b, 1)
    break_edge = abs(breaks_a - breaks_b) / max(breaks_a + breaks_b, 1)
    win_edge = abs(p_a - p_b)

    value_score = round(
        (confidence_score * 0.45)
        + (win_edge * 0.25)
        + (ace_edge * 0.15)
        + (break_edge * 0.15),
        3,
    )

    if value_score >= 0.70:
        value_label = "Forte"
    elif value_score >= 0.50:
        value_label = "Interessante"
    else:
        value_label = "Basso"

    result = {
        "playerA": {
            "aces": aces_a,
            "breaks": breaks_a,
        },
        "playerB": {
            "aces": aces_b,
            "breaks": breaks_b,
        },
        "totals": {
            "aces": round(aces_a + aces_b, 1),
            "breaks": round(breaks_a + breaks_b, 1),
        },
    }

    context = {
        "skipped": False,

        "matched_player_a": a_name,
        "matched_player_b": b_name,

        "data_quality_a": a.get("data_quality", "fallback"),
        "data_quality_b": b.get("data_quality", "fallback"),
        "stats_source_a": a.get("data_quality", "fallback"),
        "stats_source_b": b.get("data_quality", "fallback"),

        "atp_stats_a": atp_a["has_atp"],
        "atp_stats_b": atp_b["has_atp"],

        "atp_serve_rating_a": atp_a["serve_rating"],
        "atp_serve_rating_b": atp_b["serve_rating"],
        "atp_return_rating_a": atp_a["return_rating"],
        "atp_return_rating_b": atp_b["return_rating"],
        "atp_pressure_rating_a": atp_a["pressure_rating"],
        "atp_pressure_rating_b": atp_b["pressure_rating"],

        "atp_serve_delta_a": atp_a["serve_delta"],
        "atp_serve_delta_b": atp_b["serve_delta"],
        "atp_return_delta_a": atp_a["return_delta"],
        "atp_return_delta_b": atp_b["return_delta"],
        "atp_pressure_delta_a": atp_a["pressure_delta"],
        "atp_pressure_delta_b": atp_b["pressure_delta"],
        "atp_confidence_boost": round(atp_confidence_boost, 3),

        "elo_a": elo_a,
        "elo_b": elo_b,
        "atp_elo_boost_a": atp_elo_boost_a,
        "atp_elo_boost_b": atp_elo_boost_b,
        "elo_a_model": elo_a_model,
        "elo_b_model": elo_b_model,
        "win_prob_a": round(p_a, 3),
        "win_prob_b": round(p_b, 3),

        "ace_rate_a_raw": round(ace_rate_a_raw, 4),
        "ace_rate_b_raw": round(ace_rate_b_raw, 4),
        "break_rate_a_raw": round(break_rate_a_raw, 4),
        "break_rate_b_raw": round(break_rate_b_raw, 4),

        "ace_rate_a_used": round(ace_rate_a, 4),
        "ace_rate_b_used": round(ace_rate_b, 4),
        "break_rate_a_used": round(break_rate_a, 4),
        "break_rate_b_used": round(break_rate_b, 4),

        "ace_allowed_a_used": round(ace_allowed_a, 4),
        "ace_allowed_b_used": round(ace_allowed_b, 4),
        "break_allowed_a_used": round(break_allowed_a, 4),
        "break_allowed_b_used": round(break_allowed_b, 4),

        "current_tournament_matches_a": a.get("current_tournament_matches", 0),
        "current_tournament_matches_b": b.get("current_tournament_matches", 0),

        "court_factor": c_factor,
        "tournament": tournament_context.get("tournament"),
        "tournament_slug": tournament_context.get("slug"),
        "surface": surface,
        "season": season,
        "ace_environment_factor": ace_environment_factor,
        "break_environment_factor": break_environment_factor,
        "madrid_factor": madrid_factor,
        "match_length": round(match_length, 2),
        "avg_temp": avg_temp,
        "wind_kmh": wind_kmh,
        "ace_weather_factor": ace_wf,
        "break_weather_factor": break_wf,

        "confidence_score": confidence_score,
        "confidence_label": confidence_label,
        "data_confidence": round(data_confidence, 3),
        "weather_confidence": weather_confidence,
        "court_confidence": court_confidence,
        "model_edge": round(model_edge, 3),
        "stat_consistency": round(stat_consistency, 3),

        "ace_edge": round(ace_edge, 3),
        "break_edge": round(break_edge, 3),
        "win_edge": round(win_edge, 3),
        "value_score": value_score,
        "value_label": value_label,

        "mc_aces_a": mc_aces_a,
        "mc_aces_b": mc_aces_b,
        "mc_breaks_a": mc_breaks_a,
        "mc_breaks_b": mc_breaks_b,
        "mc_total_aces": mc_total_aces,
        "mc_total_breaks": mc_total_breaks,
        "mc_total_aces_values": mc_total_aces_values,
        "mc_total_breaks_values": mc_total_breaks_values,
    }

    return result, context
