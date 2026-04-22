import json
from datetime import date

# MOCK iniziale → poi sostituiamo con scraping reale

matches = [
    {"player1": "Sinner", "player2": "Medvedev", "court": "Center", "date": str(date.today())},
    {"player1": "Alcaraz", "player2": "Zverev", "court": "Court 4", "date": str(date.today())},
]

players = {
    "sinner": {"elo_clay": 2100, "ace_rate_clay": 7.5, "break_rate_clay": 2.3},
    "medvedev": {"elo_clay": 2000, "ace_rate_clay": 8.5, "break_rate_clay": 1.8},
    "alcaraz": {"elo_clay": 2150, "ace_rate_clay": 6.2, "break_rate_clay": 2.7},
    "zverev": {"elo_clay": 2050, "ace_rate_clay": 9.0, "break_rate_clay": 1.9},
}

with open("data/live/matches.json", "w") as f:
    json.dump(matches, f)

with open("data/live/players.json", "w") as f:
    json.dump(players, f)
