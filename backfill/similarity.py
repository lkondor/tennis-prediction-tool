import math


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def build_feature_vector(player_data: dict):
    return [
        player_data.get("elo_clay", 1800) / 2500.0,
        player_data.get("ace_rate_clay_3y", 0),
        player_data.get("ace_allowed_clay_3y", 0),
        player_data.get("break_rate_clay_3y", 0),
        player_data.get("break_allowed_clay_3y", 0),
        player_data.get("madrid_ace_rate", 0),
        player_data.get("madrid_break_rate", 0),
    ]


def find_similar_players(player_name: str, all_players: dict, top_n: int = 5):
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
