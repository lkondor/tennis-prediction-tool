def weighted_mean(values, weights):
    s_w = sum(weights)
    if s_w == 0:
        return 0
    return sum(v * w for v, w in zip(values, weights)) / s_w


def build_three_year_rates(player_record):
    stats = player_record.get("stats_by_year_clay", {})
    years = ["2023", "2024", "2025", "2026"]
    weights = [0.15, 0.25, 0.35, 0.25]

    ace_rates = []
    break_rates = []

    for y in years:
        rec = stats.get(y, {})
        aces = rec.get("aces", 0) or 0
        sgp = rec.get("service_games_played", 0) or 0
        breaks = rec.get("breaks_made", 0) or 0
        rgp = rec.get("return_games_played", 0) or 0

        ace_rates.append(aces / sgp if sgp else 0)
        break_rates.append(breaks / rgp if rgp else 0)

    player_record["ace_rate_clay_3y"] = round(weighted_mean(ace_rates, weights), 4)
    player_record["break_rate_clay_3y"] = round(weighted_mean(break_rates, weights), 4)

    madrid_matches = player_record.get("madrid_matches", 0) or 0
    if madrid_matches:
        player_record["madrid_ace_rate"] = round(player_record.get("madrid_aces", 0) / madrid_matches, 4)
        player_record["madrid_break_rate"] = round(player_record.get("madrid_breaks", 0) / madrid_matches, 4)
    else:
        player_record["madrid_ace_rate"] = 0
        player_record["madrid_break_rate"] = 0

    return player_record
