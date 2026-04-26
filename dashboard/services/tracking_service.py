import json
from pathlib import Path
from datetime import datetime


TRACKING_PATH = Path("data/live/bet_tracking.json")


def load_tracking():
    if not TRACKING_PATH.exists():
        return []

    try:
        text = TRACKING_PATH.read_text(encoding="utf-8").strip()
        if not text:
            return []
        return json.loads(text)
    except Exception:
        return []


def save_tracking(rows):
    TRACKING_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRACKING_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def make_pick_id(date, match, market, line):
    return f"{date}|{match}|{market}|{line}"


def add_picks(date, portfolio_rows):
    existing = load_tracking()
    existing_ids = {r.get("pick_id") for r in existing}

    new_rows = []

    for p in portfolio_rows:
        pick_id = make_pick_id(
            date=date,
            match=p["Match"],
            market=p["Market"],
            line=p["Line"]
        )

        if pick_id in existing_ids:
            continue

        new_rows.append({
            "pick_id": pick_id,
            "created_at": datetime.utcnow().isoformat(),
            "date": date,
            "match": p["Match"],
            "court": p["Court"],
            "market": p["Market"],
            "line": p["Line"],
            "model_prob": p["Model Prob"],
            "edge": p["Edge"],
            "confidence": p["Confidence"],
            "confidence_score": p["Confidence score"],
            "status": "PENDING",
            "result": None,
            "notes": ""
        })

    combined = existing + new_rows
    save_tracking(combined)

    return len(new_rows)


def update_pick_status(pick_id, status, result=None, notes=""):
    rows = load_tracking()

    for r in rows:
        if r.get("pick_id") == pick_id:
            r["status"] = status
            r["result"] = result
            r["notes"] = notes
            r["updated_at"] = datetime.utcnow().isoformat()

    save_tracking(rows)


def tracking_summary(rows):
    settled = [r for r in rows if r.get("status") in ["WIN", "LOSS", "PUSH"]]
    wins = sum(1 for r in settled if r.get("status") == "WIN")
    losses = sum(1 for r in settled if r.get("status") == "LOSS")
    pushes = sum(1 for r in settled if r.get("status") == "PUSH")

    total = len(settled)
    win_rate = wins / total if total else 0

    return {
        "total_picks": len(rows),
        "settled": total,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate": win_rate
    }
