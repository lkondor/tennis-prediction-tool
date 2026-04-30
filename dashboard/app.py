import streamlit as st
from streamlit_autorefresh import st_autorefresh

from services.data_service import (
    load_all_matches,
    get_available_dates,
    get_matches_by_date,
    load_meta,
)
from services.model_service import run_prediction
from services.tracking_service import (
    load_tracking,
    add_picks,
    update_pick_status,
    tracking_summary,
    auto_settle_picks,
)
from components.match_selector import render_match_selector
from components.prediction_view import render_prediction
from components.breakdown_view import render_breakdown
from components.filters import render_filters


def no_vig_prob(over_odds, under_odds):
    raw_over = 1 / over_odds
    raw_under = 1 / under_odds
    total = raw_over + raw_under

    if total == 0:
        return 0, 0, 0

    market_over = raw_over / total
    market_under = raw_under / total
    overround = total - 1

    return market_over, market_under, overround


def line_sensitivity(values, center_line, step=0.5, n=7):
    lines = [center_line + (i - n // 2) * step for i in range(n)]
    results = []

    for line in lines:
        prob = sum(1 for v in values if v > line) / len(values) if values else 0

        results.append(
            {
                "Line": round(line, 2),
                "Over Prob": round(prob, 3),
                "Fair Odds": round(1 / prob, 2) if prob > 0 else None,
                "EV @1.85": round((prob * 1.85) - 1, 3),
            }
        )

    return results


def find_fair_line(sensitivity):
    if not sensitivity:
        return None

    closest = min(
        sensitivity,
        key=lambda x: abs(x["Over Prob"] - 0.5),
    )

    return closest["Line"]


def best_over_bet(values, odds, confidence, min_ev=0.03, min_confidence=0.55):
    if not values:
        return {
            "label": "NO BET",
            "line": None,
            "prob": 0,
            "ev": 0,
            "fair_odds": None,
        }

    candidate_lines = [
        round(min(values) + i * 0.5, 2)
        for i in range(int((max(values) - min(values)) / 0.5) + 1)
    ]

    candidates = []

    for line in candidate_lines:
        prob = sum(1 for v in values if v > line) / len(values)
        ev = (prob * odds) - 1
        fair_odds = round(1 / prob, 2) if prob > 0 else None

        candidates.append(
            {
                "line": line,
                "prob": prob,
                "ev": ev,
                "fair_odds": fair_odds,
            }
        )

    best = max(candidates, key=lambda x: x["ev"])

    if best["ev"] >= min_ev and confidence >= min_confidence:
        label = "BET"
    else:
        label = "NO BET"

    return {
        "label": label,
        "line": best["line"],
        "prob": round(best["prob"], 3),
        "ev": round(best["ev"], 3),
        "fair_odds": best["fair_odds"],
    }


def classify_value(edge, confidence):
    if edge >= 0.07 and confidence >= 0.60:
        return "FORTE"
    if edge >= 0.03 and confidence >= 0.55:
        return "OK"
    return "NO BET"


def main():
    st.set_page_config(layout="wide")
    st_autorefresh(interval=15 * 60 * 1000, key="data_refresh")

    st.title("Madrid Open Predictor")

    meta = load_meta()
    all_matches = load_all_matches()

    if not all_matches:
        st.error("Nessun dato disponibile.")
        return

    st.caption(
        f"Fonte calendario: {meta.get('match_source', 'n/d')} | "
        f"Aggiornato: {meta.get('updated_at', 'n/d')}"
    )

    dates = get_available_dates(all_matches)
    selected_date = st.selectbox("Seleziona data", dates)

    matches = get_matches_by_date(selected_date)

    if not matches:
        st.warning("Nessuna partita trovata per la data selezionata.")
        return

    # ---- SIDEBAR SETTINGS ----
    st.sidebar.subheader("Soglie operative")

    min_value_score = st.sidebar.slider(
        "Min Value Score",
        min_value=0.0,
        max_value=1.0,
        value=0.50,
        step=0.05,
    )

    min_confidence_score = st.sidebar.slider(
        "Min Confidence Score",
        min_value=0.0,
        max_value=1.0,
        value=0.55,
        step=0.05,
    )

    st.sidebar.subheader("Portfolio")

    min_portfolio_ev = st.sidebar.slider(
        "Min Portfolio EV",
        min_value=0.0,
        max_value=0.30,
        value=0.03,
        step=0.01,
    )

    min_portfolio_confidence = st.sidebar.slider(
        "Min Portfolio Confidence",
        min_value=0.0,
        max_value=1.0,
        value=0.55,
        step=0.05,
    )

    # ---- MATCH RANKING ----
    st.subheader("Ranking match del giorno")

    rows = []
    skipped_matches = 0

    for m in matches:
        pred, ctx = run_prediction(m)

        if ctx.get("skipped"):
            skipped_matches += 1
            continue

        ace_values = ctx.get("mc_total_aces_values", [])
        break_values = ctx.get("mc_total_breaks_values", [])

        ace_line_default = float(pred["totals"]["aces"])
        break_line_default = float(pred["totals"]["breaks"])

        ace_over_prob = (
            sum(1 for v in ace_values if v > ace_line_default) / len(ace_values)
            if ace_values
            else 0
        )

        break_over_prob = (
            sum(1 for v in break_values if v > break_line_default) / len(break_values)
            if break_values
            else 0
        )

        market_prob = 0.50

        ace_edge = ace_over_prob - market_prob
        break_edge = break_over_prob - market_prob

        rows.append(
            {
                "Match": f"{m.player1} vs {m.player2}",
                "Court": m.court,
                "Ace totali": pred["totals"]["aces"],
                "Break totali": pred["totals"]["breaks"],
                "Over Ace Prob": round(ace_over_prob, 3),
                "Over Break Prob": round(break_over_prob, 3),
                "Ace Edge": round(ace_edge, 3),
                "Break Edge": round(break_edge, 3),
                "EV Ace": round((ace_over_prob * 1.85) - 1, 3),
                "EV Break": round((break_over_prob * 1.85) - 1, 3),
                "Confidence": ctx.get("confidence_label"),
                "Confidence score": ctx.get("confidence_score"),
                "Value": ctx.get("value_label"),
                "Value score": ctx.get("value_score"),
                "ATP/WTA A": "✅" if ctx.get("atp_stats_a") else "",
                "ATP/WTA B": "✅" if ctx.get("atp_stats_b") else "",
                "ATP ELO A": ctx.get("atp_elo_boost_a", 0),
                "ATP ELO B": ctx.get("atp_elo_boost_b", 0),
            }
        )

    rows = sorted(rows, key=lambda x: x["Value score"] or 0, reverse=True)

    if skipped_matches > 0:
        st.caption(f"{skipped_matches} match di doppio esclusi dal modello.")

    st.dataframe(rows, use_container_width=True)

    enriched_rows = [
        r for r in rows
        if r.get("ATP/WTA A") == "✅" or r.get("ATP/WTA B") == "✅"
    ]

    if enriched_rows:
        st.caption(f"{len(enriched_rows)} match con ATP/WTA enriched stats attive.")

    # ---- PORTFOLIO VIEW ----
    st.subheader("Portfolio View")

    portfolio_rows = []

    for r in rows:
        if (
            (r.get("EV Ace") or 0) >= min_portfolio_ev
            and (r.get("Confidence score") or 0) >= min_portfolio_confidence
        ):
            portfolio_rows.append(
                {
                    "Market": "Over Ace",
                    "Match": r["Match"],
                    "Court": r["Court"],
                    "Line": r["Ace totali"],
                    "Model Prob": r["Over Ace Prob"],
                    "Edge": r["Ace Edge"],
                    "EV": r["EV Ace"],
                    "Confidence": r["Confidence"],
                    "Confidence score": r["Confidence score"],
                }
            )

        if (
            (r.get("EV Break") or 0) >= min_portfolio_ev
            and (r.get("Confidence score") or 0) >= min_portfolio_confidence
        ):
            portfolio_rows.append(
                {
                    "Market": "Over Break",
                    "Match": r["Match"],
                    "Court": r["Court"],
                    "Line": r["Break totali"],
                    "Model Prob": r["Over Break Prob"],
                    "Edge": r["Break Edge"],
                    "EV": r["EV Break"],
                    "Confidence": r["Confidence"],
                    "Confidence score": r["Confidence score"],
                }
            )

    portfolio_rows = sorted(
        portfolio_rows,
        key=lambda x: (x["EV"], x["Confidence score"] or 0),
        reverse=True,
    )

    if portfolio_rows:
        st.dataframe(portfolio_rows, use_container_width=True)

        added = add_picks(selected_date, portfolio_rows)

        if added > 0:
            st.success(f"{added} nuove pick salvate automaticamente nel tracking.")
        else:
            st.caption("Portfolio già salvato nel tracking.")
    else:
        st.info("Nessun possibile value rilevato con le soglie portfolio attuali.")

    # ---- TRACKING PICKS ----
    st.subheader("Tracking Picks")

    updated_picks = auto_settle_picks()

    if updated_picks > 0:
        st.success(f"{updated_picks} pick aggiornate automaticamente con risultati reali.")

    tracking_rows = load_tracking()
    summary = tracking_summary(tracking_rows)

    tcol1, tcol2, tcol3, tcol4 = st.columns(4)

    tcol1.metric("Pick totali", summary["total_picks"])
    tcol2.metric("Settled", summary["settled"])
    tcol3.metric("Win rate", f"{summary['win_rate']:.1%}")
    tcol4.metric("W-L-P", f"{summary['wins']}-{summary['losses']}-{summary['pushes']}")

    if tracking_rows:
        st.dataframe(tracking_rows, use_container_width=True)

        pick_options = {
            f"{r['date']} | {r['match']} | {r['market']} | {r['line']} | {r['status']}": r["pick_id"]
            for r in tracking_rows
        }

        selected_pick_label = st.selectbox(
            "Seleziona pick da aggiornare",
            list(pick_options.keys()),
        )

        selected_pick_id = pick_options[selected_pick_label]

        new_status = st.selectbox(
            "Nuovo status",
            ["PENDING", "WIN", "LOSS", "PUSH"],
        )

        notes = st.text_input("Note", "")

        if st.button("Aggiorna pick"):
            update_pick_status(
                selected_pick_id,
                new_status,
                result=new_status,
                notes=notes,
            )
            st.success("Pick aggiornata. La pagina si aggiornerà automaticamente.")
    else:
        st.info("Nessuna pick salvata nel tracking.")

    # ---- TOP PICKS ----
    top_picks = [
        r for r in rows
        if (r.get("Value score") or 0) >= min_value_score
        and (r.get("Confidence score") or 0) >= min_confidence_score
    ]

    st.subheader("Top Picks")

    if not top_picks:
        st.info("Nessun match supera le soglie operative attuali.")
    else:
        for pick in top_picks[:5]:
            st.success(
                f"{pick['Match']} | "
                f"Value: {pick['Value']} ({pick['Value score']}) | "
                f"Confidence: {pick['Confidence']} ({pick['Confidence score']}) | "
                f"Ace totali: {pick['Ace totali']} | "
                f"Break totali: {pick['Break totali']}"
            )

    # ---- MATCH DETAIL ----
    render_filters()

    singles_matches = []

    for m in matches:
        _, ctx = run_prediction(m)

        if not ctx.get("skipped"):
            singles_matches.append(m)

    if not singles_matches:
        st.warning("Nessun match di singolare disponibile per la data selezionata.")
        return

    selected_match = render_match_selector(singles_matches)
    result, context = run_prediction(selected_match)

    st.metric(
        "Confidence",
        context.get("confidence_label", "-"),
        f"{context.get('confidence_score', '-')}",
    )

    st.metric(
        "Value",
        context.get("value_label", "-"),
        f"{context.get('value_score', '-')}",
    )

    render_prediction(result, selected_match.player1, selected_match.player2)

    if context.get("atp_stats_a") or context.get("atp_stats_b"):
        st.subheader("ATP/WTA enriched stats")

        c1, c2 = st.columns(2)

        with c1:
            st.markdown(f"**{context.get('matched_player_a')}**")
            st.write(
                {
                    "has_stats": context.get("atp_stats_a"),
                    "serve_rating": context.get("atp_serve_rating_a"),
                    "return_rating": context.get("atp_return_rating_a"),
                    "pressure_rating": context.get("atp_pressure_rating_a"),
                    "elo_boost": context.get("atp_elo_boost_a"),
                }
            )

        with c2:
            st.markdown(f"**{context.get('matched_player_b')}**")
            st.write(
                {
                    "has_stats": context.get("atp_stats_b"),
                    "serve_rating": context.get("atp_serve_rating_b"),
                    "return_rating": context.get("atp_return_rating_b"),
                    "pressure_rating": context.get("atp_pressure_rating_b"),
                    "elo_boost": context.get("atp_elo_boost_b"),
                }
            )

    st.subheader("Monte Carlo Range")

    col1, col2 = st.columns(2)

    with col1:
        st.write("Ace totali")
        st.json(context.get("mc_total_aces", {}))

    with col2:
        st.write("Break totali")
        st.json(context.get("mc_total_breaks", {}))

    # ---- OVER/UNDER SIMULATOR ----
    st.subheader("Over/Under Simulator")

    ou_col1, ou_col2 = st.columns(2)

    with ou_col1:
        ace_line = st.number_input(
            "Linea Ace Totali",
            min_value=0.0,
            value=float(result["totals"]["aces"]),
            step=0.5,
        )

        ace_over_odds = st.number_input(
            "Quota Over Ace",
            min_value=1.01,
            value=1.85,
            step=0.01,
        )

        ace_under_odds = st.number_input(
            "Quota Under Ace",
            min_value=1.01,
            value=1.85,
            step=0.01,
        )

    with ou_col2:
        break_line = st.number_input(
            "Linea Break Totali",
            min_value=0.0,
            value=float(result["totals"]["breaks"]),
            step=0.5,
        )

        break_over_odds = st.number_input(
            "Quota Over Break",
            min_value=1.01,
            value=1.85,
            step=0.01,
        )

        break_under_odds = st.number_input(
            "Quota Under Break",
            min_value=1.01,
            value=1.85,
            step=0.01,
        )

    ace_values = context.get("mc_total_aces_values", [])
    break_values = context.get("mc_total_breaks_values", [])

    ace_over_prob = (
        sum(1 for v in ace_values if v > ace_line) / len(ace_values)
        if ace_values
        else 0
    )

    break_over_prob = (
        sum(1 for v in break_values if v > break_line) / len(break_values)
        if break_values
        else 0
    )

    ace_market_over_prob, ace_market_under_prob, ace_overround = no_vig_prob(
        ace_over_odds,
        ace_under_odds,
    )

    break_market_over_prob, break_market_under_prob, break_overround = no_vig_prob(
        break_over_odds,
        break_under_odds,
    )

    ace_edge = ace_over_prob - ace_market_over_prob
    break_edge = break_over_prob - break_market_over_prob

    ace_ev = (ace_over_prob * ace_over_odds) - 1
    break_ev = (break_over_prob * break_over_odds) - 1

    ace_value_label = classify_value(
        ace_edge,
        context.get("confidence_score", 0),
    )

    break_value_label = classify_value(
        break_edge,
        context.get("confidence_score", 0),
    )

    prob_col1, prob_col2 = st.columns(2)

    with prob_col1:
        st.metric("Probabilità Over Ace", f"{ace_over_prob:.1%}")
        st.metric("EV Over Ace", f"{ace_ev:.1%}")

    with prob_col2:
        st.metric("Probabilità Over Break", f"{break_over_prob:.1%}")
        st.metric("EV Over Break", f"{break_ev:.1%}")

    edge_col1, edge_col2 = st.columns(2)

    with edge_col1:
        st.metric(
            "Edge Over Ace",
            f"{ace_edge:.1%}",
            f"Market no-vig: {ace_market_over_prob:.1%}",
        )
        st.caption(f"Overround Ace market: {ace_overround:.1%}")

    with edge_col2:
        st.metric(
            "Edge Over Break",
            f"{break_edge:.1%}",
            f"Market no-vig: {break_market_over_prob:.1%}",
        )
        st.caption(f"Overround Break market: {break_overround:.1%}")

    
    st.subheader("Best Bet Suggestion")

    bb_col1, bb_col2 = st.columns(2)

    with bb_col1:
        if best_ace_bet["label"] == "BET":
            st.success(
                f"Over Ace {best_ace_bet['line']} @ {ace_over_odds:.2f} | "
                f"Prob {best_ace_bet['prob']:.1%} | "
                f"EV {best_ace_bet['ev']:.1%} | "
                f"Fair odds {best_ace_bet['fair_odds']}"
            )
        else:
            st.info("Ace: NO BET")

    with bb_col2:
        if best_break_bet["label"] == "BET":
            st.success(
                f"Over Break {best_break_bet['line']} @ {break_over_odds:.2f} | "
                f"Prob {best_break_bet['prob']:.1%} | "
                f"EV {best_break_bet['ev']:.1%} | "
                f"Fair odds {best_break_bet['fair_odds']}"
            )
        else:
            st.info("Break: NO BET")    
    
    
    value_col1, value_col2 = st.columns(2)

    with value_col1:
        if ace_value_label == "FORTE":
            st.success(f"Ace Bet: {ace_value_label}")
        elif ace_value_label == "OK":
            st.warning(f"Ace Bet: {ace_value_label}")
        else:
            st.error(f"Ace Bet: {ace_value_label}")

    with value_col2:
        if break_value_label == "FORTE":
            st.success(f"Break Bet: {break_value_label}")
        elif break_value_label == "OK":
            st.warning(f"Break Bet: {break_value_label}")
        else:
            st.error(f"Break Bet: {break_value_label}")

    # ---- LINE SENSITIVITY ----
    st.subheader("Line Sensitivity")

    ace_sensitivity = line_sensitivity(ace_values, ace_line)
    break_sensitivity = line_sensitivity(break_values, break_line)

    fair_ace_line = find_fair_line(ace_sensitivity)
    fair_break_line = find_fair_line(break_sensitivity)

    fair_col1, fair_col2 = st.columns(2)

    with fair_col1:
        st.metric("Fair Line Ace", fair_ace_line)

    with fair_col2:
        st.metric("Fair Line Break", fair_break_line)

    sens_col1, sens_col2 = st.columns(2)

    with sens_col1:
        st.write("Ace curve")
        st.dataframe(ace_sensitivity, use_container_width=True)

    with sens_col2:
        st.write("Break curve")
        st.dataframe(break_sensitivity, use_container_width=True)

    render_breakdown(context)


if __name__ == "__main__":
    main()
