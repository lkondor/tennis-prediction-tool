from collections import defaultdict


class SurfaceElo:
    def __init__(self, base_rating=1500, k=24):
        self.base_rating = base_rating
        self.k = k
        self.ratings = defaultdict(lambda: self.base_rating)

    def get(self, player_name: str) -> float:
        return self.ratings[player_name.lower().strip()]

    def expected(self, a: str, b: str) -> float:
        ra = self.get(a)
        rb = self.get(b)
        return 1 / (1 + 10 ** ((rb - ra) / 400))

    def update(self, winner: str, loser: str):
        ew = self.expected(winner, loser)
        el = 1 - ew

        rw = self.get(winner)
        rl = self.get(loser)

        self.ratings[winner.lower().strip()] = rw + self.k * (1 - ew)
        self.ratings[loser.lower().strip()] = rl + self.k * (0 - el)

    def export(self):
        return dict(self.ratings)
