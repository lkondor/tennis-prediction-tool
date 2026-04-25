import json
import math
from pathlib import Path


PLAYERS_PATH = Path("data/live/players.json")
WEATHER_PATH = Path("data/live/weather.json")
ALIASES_PATH = Path("data/live/player_aliases.json")


def load_players():
    if not PLAYERS_PATH.exists():
        return {}

    with open(PLAYERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_weather():
    if not WEATHER_PATH.exists():
        return {}

    with open(WEATHER_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_aliases():
    if not ALIASES_PATH.exists():
        return {}

    with open(ALIASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_player_key(display_name, players):
    aliases = load_aliases()
    name = str(display_name).lower().strip()

    if name in aliases and aliases[name] in players:
        return aliases[name]
    
    ALIASES = {
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
        "e. rybakina": "elena rybakina"
    }

    if name in ALIASES and ALIASES[name] in players:
        return ALIASES[name]

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


def run_prediction(match):
    players = load_players()
    weather = load_weather()

    a_name = resolve_player_key(match.player1, players)
    b_name = resolve_player_key(match.player2, players)

    a = players.get(a_name, {})
    b = players.get(b_name, {})

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

    elo_a = adjusted_elo(a)
    elo_b = adjusted_elo(b)

    ace_rate_a = weighted_stat(safe_stat(a, "ace_rate_clay_3y", 0.25), a)
    ace_rate_b = weighted_stat(safe_stat(b, "ace_rate_clay_3y", 0.25), b)

    ace_allowed_a = weighted_stat(safe_stat(a, "ace_allowed_clay_3y", 0.23), a)
    ace_allowed_b = weighted_stat(safe_stat(b, "ace_allowed_clay_3y", 0.23), b)

    break_rate_a = weighted_stat(safe_stat(a, "break_rate_clay_3y", 0.20), a)
    break_rate_b = weighted_stat(safe_stat(b, "break_rate_clay_3y", 0.20), b)

    break_allowed_a = weighted_stat(safe_stat(a, "break_allowed_clay_3y", 0.18), a)
    break_allowed_b = weighted_stat(safe_stat(b, "break_allowed_clay_3y", 0.18), b)

    p_a = win_prob(elo_a, elo_b)
    p_b = 1 - p_a

    c_factor = court_factor(match.court)
    madrid_factor = 1.15
    match_length = 1.08 + (1 - abs(p_a - 0.5)) * 0.5

    day_weather = weather.get(match.date, {})
    avg_temp = day_weather.get("avg_temp")
    wind_kmh = day_weather.get("wind_kmh")

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
        1
    )

    aces_b = round(
        ((ace_rate_b + ace_allowed_a) / 2)
        * 20
        * c_factor
        * madrid_factor
        * match_length
        * ace_wf
        * sim_boost_b,
        1
    )

    breaks_a = round(
        ((break_rate_a + break_allowed_b) / 2)
        * 10
        * (1.12 - (c_factor - 1) * 0.5)
        * break_wf,
        1
    )

    breaks_b = round(
        ((break_rate_b + break_allowed_a) / 2)
        * 10
        * (1.12 - (c_factor - 1) * 0.5)
        * break_wf,
        1
    )

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

    data_confidence = (quality_score(a) + quality_score(b)) / 2
    weather_confidence = 1.0 if avg_temp is not None and wind_kmh is not None else 0.6
    court_confidence = 1.0 if match.court else 0.7

    confidence_score = round(
        (data_confidence * 0.65)
        + (weather_confidence * 0.20)
        + (court_confidence * 0.15),
        3
    )

    if confidence_score >= 0.80:
        confidence_label = "Alta"
    elif confidence_score >= 0.60:
        confidence_label = "Media"
    else:
        confidence_label = "Bassa"

    result = {
        "playerA": {
            "aces": aces_a,
            "breaks": breaks_a
        },
        "playerB": {
            "aces": aces_b,
            "breaks": breaks_b
        },
        "totals": {
            "aces": round(aces_a + aces_b, 1),
            "breaks": round(breaks_a + breaks_b, 1)
        }
    }

    context = {
        "matched_player_a": a_name,
        "matched_player_b": b_name,
        "data_quality_a": a.get("data_quality", "fallback"),
        "data_quality_b": b.get("data_quality", "fallback"),
        "stats_source_a": a.get("data_quality", "fallback"),
        "stats_source_b": b.get("data_quality", "fallback"),
        "elo_a": elo_a,
        "elo_b": elo_b,
        "win_prob_a": round(p_a, 3),
        "win_prob_b": round(p_b, 3),
        "ace_rate_a_used": round(ace_rate_a, 4),
        "ace_rate_b_used": round(ace_rate_b, 4),
        "break_rate_a_used": round(break_rate_a, 4),
        "break_rate_b_used": round(break_rate_b, 4),
        "court_factor": c_factor,
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
    }

    return result, context
