import json
from pathlib import Path


PLAYER_PATH = Path("data/live/players.json")


def load_players():
    if not PLAYER_PATH.exists():
        return {}
    with open(PLAYER_PATH) as f:
        return json.load(f)


def win_prob(elo_a, elo_b):
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


def run_prediction(match):
    players = load_players()

    a = players.get(match.player1.lower(), {})
    b = players.get(match.player2.lower(), {})

    elo_a = a.get("elo_clay", 1800)
    elo_b = b.get("elo_clay", 1800)

    serve_a = a.get("ace_rate_clay", 6)
    serve_b = b.get("ace_rate_clay", 6)

    break_a = a.get("break_rate_clay", 2)
    break_b = b.get("break_rate_clay", 2)

    p_a = win_prob(elo_a, elo_b)
    match_length = 1.1 + (1 - abs(p_a - 0.5)) * 0.5

    court_factor = 1.08 if "court 4" in match.court.lower() else 1.0

    aces_a = round(serve_a * court_factor * match_length, 1)
    aces_b = round(serve_b * court_factor * match_length, 1)

    breaks_a = round(break_a * (1.2 - court_factor / 10), 1)
    breaks_b = round(break_b * (1.2 - court_factor / 10), 1)

    return {
        "playerA": {"aces": aces_a, "breaks": breaks_a},
        "playerB": {"aces": aces_b, "breaks": breaks_b},
        "totals": {
            "aces": round(aces_a + aces_b, 1),
            "breaks": round(breaks_a + breaks_b, 1)
        }
    }, {
        "elo_a": elo_a,
        "elo_b": elo_b,
        "match_length": match_length,
        "court_factor": court_factor
    }
