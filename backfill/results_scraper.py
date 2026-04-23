import requests
from bs4 import BeautifulSoup


def scrape_atp_madrid_results():
    url = "https://www.atptour.com/en/scores/current/madrid/1536/results"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text("\n", strip=True)
        lines = [x.strip() for x in text.splitlines() if x.strip()]

        results = []
        for i in range(len(lines) - 1):
            if " def. " in lines[i]:
                left, right = lines[i].split(" def. ", 1)
                results.append({
                    "date": "2026-04-22",
                    "tour": "ATP",
                    "tournament": "Madrid",
                    "surface": "Clay",
                    "winner": left.title(),
                    "loser": right.title(),
                })
        return results
    except Exception:
        return []


def scrape_results_history():
    return scrape_atp_madrid_results()
