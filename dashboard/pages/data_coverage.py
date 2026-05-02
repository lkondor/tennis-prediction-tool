import json
from pathlib import Path
from collections import Counter, defaultdict

import streamlit as st


HISTORICAL_MATCHES_PATH = Path("data/raw/historical_matches.json")
CURRENT_RESULTS_PATH = Path("data/live/current_tournament_results.json")
PLAYERS_PATH = Path("data/live/players.json")
TOURNAMENT_CONTEXT_PATH = Path("data/live/tournament_context.json")


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


def has_complete_basic_stats(match):
    required = [
        "aces_p1",
        "aces_p2",
        "breaks_p1",
        "breaks_p2",
        "service_games_p1",
        "service_games_p2",
        "return_games_p1",
        "return_games_p2",
    ]

    return all(match.get(k) not in [None, ""] for k in required)


def main():
    st.set_page_config(layout="wide")
    st.title("Data Coverage")

    historical = load_json(HISTORICAL_MATCHES_PATH, [])
    current = load_json(CURRENT_RESULTS_PATH, [])
    players = load_json(PLAYERS_PATH, {})
    context = load_json(TOURNAMENT_CONTEXT_PATH, {})

    st.subheader("Tournament Context")
    st.json(context)

    st.subheader("Database Summary")

    total_matches = len(historical)
    total_current = len(current)
    total_players = len(players)

    stats_complete = sum(1 for m in historical if has_complete_basic_stats(m))
    stats_coverage = stats_complete / total_matches if total_matches else 0

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Historical matches", total_matches)
    c2.metric("Current tournament results", total_current)
    c3.metric("Players", total_players)
    c4.metric("Stats coverage", f"{stats_coverage:.1%}")

    st.subheader("Coverage by Year")

    by_year = Counter(str(m.get("season", "unknown")) for m in historical)

    year_rows = [
        {"Season": season, "Matches": count}
        for season, count in sorted(by_year.items())
    ]

    st.dataframe(year_rows, use_container_width=True)

    st.subheader("Coverage by Tour")

    by_tour = Counter(str(m.get("tour", "unknown")).lower() for m in historical)

    tour_rows = [
        {"Tour": tour, "Matches": count}
        for tour, count in sorted(by_tour.items())
    ]

    st.dataframe(tour_rows, use_container_width=True)

    st.subheader("Coverage by Surface")

    by_surface = Counter(str(m.get("surface", "unknown")).lower() for m in historical)

    surface_rows = [
        {"Surface": surface, "Matches": count}
        for surface, count in sorted(by_surface.items())
    ]

    st.dataframe(surface_rows, use_container_width=True)

    st.subheader("Top Tournaments by Match Count")

    by_tournament = Counter(
        str(m.get("tournament_slug") or m.get("tournament") or "unknown")
        for m in historical
    )

    tournament_rows = [
        {"Tournament": tournament, "Matches": count}
        for tournament, count in by_tournament.most_common(30)
    ]

    st.dataframe(tournament_rows, use_container_width=True)

    st.subheader("Stats Completeness by Season")

    season_totals = defaultdict(int)
    season_complete = defaultdict(int)

    for m in historical:
        season = str(m.get("season", "unknown"))
        season_totals[season] += 1

        if has_complete_basic_stats(m):
            season_complete[season] += 1

    completeness_rows = []

    for season in sorted(season_totals.keys()):
        total = season_totals[season]
        complete = season_complete[season]

        completeness_rows.append(
            {
                "Season": season,
                "Matches": total,
                "Complete Stats": complete,
                "Coverage": round(complete / total, 3) if total else 0,
            }
        )

    st.dataframe(completeness_rows, use_container_width=True)

    st.subheader("Player Data Quality")

    quality_counts = Counter(
        str(p.get("data_quality", "unknown"))
        for p in players.values()
    )

    quality_rows = [
        {"Data Quality": quality, "Players": count}
        for quality, count in quality_counts.most_common()
    ]

    st.dataframe(quality_rows, use_container_width=True)

    st.subheader("Players with Most Reliable Data")

    player_rows = []

    for name, p in players.items():
        player_rows.append(
            {
                "Player": name,
                "Tour": p.get("tour"),
                "Surface": p.get("surface"),
                "Data Quality": p.get("data_quality"),
                "Surface Matches Proxy": p.get("current_tournament_matches", 0),
                "Ace Rate Surface": p.get("ace_rate_surface_3y"),
                "Break Rate Surface": p.get("break_rate_surface_3y"),
                "Recent Form 10": p.get("recent_form_10"),
                "Surface Form 20": p.get("surface_form_20"),
            }
        )

    player_rows = sorted(
        player_rows,
        key=lambda x: (
            str(x.get("Data Quality") or ""),
            x.get("Recent Form 10") or 0,
        ),
        reverse=True,
    )

    st.dataframe(player_rows[:100], use_container_width=True)

    st.subheader("Current Tournament Live Results")

    if current:
        st.dataframe(current, use_container_width=True)
    else:
        st.info("Nessun risultato live/current tournament ancora disponibile.")


if __name__ == "__main__":
    main()
