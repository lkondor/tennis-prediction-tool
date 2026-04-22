import requests
from bs4 import BeautifulSoup


def get_atp_top_players(limit=150):
    url = "https://www.atptour.com/en/rankings/singles"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")

    players = []

    rows = soup.select("table tbody tr")
    for row in rows[:limit]:
        name = row.select_one(".player-cell").get_text(strip=True)
        players.append(name)

    return players


def get_wta_top_players(limit=150):
    url = "https://www.wtatennis.com/rankings/singles"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")

    players = []

    rows = soup.select("table tbody tr")
    for row in rows[:limit]:
        name = row.select_one(".player-cell").get_text(strip=True)
        players.append(name)

    return players
