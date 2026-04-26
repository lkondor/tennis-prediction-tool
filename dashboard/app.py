import streamlit as st
from streamlit_autorefresh import st_autorefresh

from services.data_service import (
    load_all_matches,
    get_available_dates,
    get_matches_by_date,
    load_meta
)
from services.model_service import run_prediction
from services.tracking_service import (
    load_tracking,
    add_picks,
    update_pick_status,
    tracking_summary
)
from components.match_selector import render_match_selector
from components.prediction_view import render_prediction
from components.breakdown_view import render_breakdown
from components.filters import render_filters


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

    # ---- DATE SELECTION ----
    dates = get_available_dates(all_matches)
    selected_date = st.selectbox("Seleziona data", dates)

    matches = get_matches_by_date(selected_date)

    if not matches:
        st.warning("Nessuna partita trovata per la data selezionata.")
        return

    # ---- SIDEBAR SETTINGS (DEVONO STARE PRIMA DI TOP PICKS) ----
    st.sidebar.subheader("Soglie operative")

    min_value_score = st.sidebar.slider(
        "Min Value Score",
        min_value=0.0,
        max_value=1.0,
        value=0.50,
        step=0.05
    )

    min_confidence_score = st.sidebar.slider(
        "Min Confidence Score",
        min_value=0.0,
        max_value=1.0,
        value=0.55,
        step=0.05
    )

    st.sidebar.subheader("Portfolio")

    min_portfolio_edge = st.sidebar.slider(
        "Min Portfolio Edge",
        min_value=0.0,
        max_value=0.30,
        value=0.03,
        step=0.01
    )

    min_portfolio_confidence = st.sidebar.slider(
        "Min Portfolio Confidence",
        min_value=0.0,
        max_value=1.0,
        value=0.55,
        step=0.05
    )

    
    # ---- MATCH RANKING ----
    st.subheader("Ranking match del giorno")

    rows = []
    for m in matches:
        pred, ctx = run_prediction(m)
        ace_values = ctx.get("mc_total_aces_values", [])
        break_values = ctx.get("mc_total_breaks_values", [])

        ace_line_default = float(pred["totals"]["aces"])
        break_line_default = float(pred["totals"]["breaks"])

        ace_over_prob = (
            sum(1 for v in ace_values if v > ace_line_default) / len(ace_values)
            if ace_values else 0
        )

        break_over_prob = (
            sum(1 for v in break_values if v > break_line_default) / len(break_values)
            if break_values else 0
        )

        # Default market 1.85 / 1.85 = mercato no-vig vicino al 50%
        market_prob = 0.50

        ace_edge = ace_over_prob - market_prob
        break_edge = break_over_prob - market_prob

        rows.append({
            "Match": f"{m.player1} vs {m.player2}",
            "Court": m.court,
            "Ace totali": pred["totals"]["aces"],
            "Break totali": pred["totals"]["breaks"],
            "Over Ace Prob": round(ace_over_prob, 3),
            "Over Break Prob": round(break_over_prob, 3),
            "Ace Edge": round(ace_edge, 3),
            "Break Edge": round(break_edge, 3),
            "Confidence": ctx.get("confidence_label"),
            "Confidence score": ctx.get("confidence_score"),
            "Value": ctx.get("value_label"),
            "Value score": ctx.get("value_score"),
        })


    
    rows = sorted(rows, key=lambda x: x["Value score"] or 0, reverse=True)

    st.dataframe(rows, use_container_width=True)

    # ---- PORTFOLIO VIEW ----
    st.subheader("Portfolio View")

    portfolio_rows = []

    for r in rows:
        if (
            (r.get("Ace Edge") or 0) >= min_portfolio_edge
            and (r.get("Confidence score") or 0) >= min_portfolio_confidence
        ):
            
            portfolio_rows.append({
                "Market": "Over Ace",
                "Match": r["Match"],
                "Court": r["Court"],
                "Line": r["Ace totali"],
                "Model Prob": r["Over Ace Prob"],
                "Edge": r["Ace Edge"],
                "Confidence": r["Confidence"],
                "Confidence score": r["Confidence score"],
            })

        if (
            (r.get("Break Edge") or 0) >= min_portfolio_edge
            and (r.get("Confidence score") or 0) >= min_portfolio_confidence
        ):
        
            portfolio_rows.append({
                "Market": "Over Break",
                "Match": r["Match"],
                "Court": r["Court"],
                "Line": r["Break totali"],
                "Model Prob": r["Over Break Prob"],
                "Edge": r["Break Edge"],
                "Confidence": r["Confidence"],
                "Confidence score": r["Confidence score"],
            })

    portfolio_rows = sorted(
        portfolio_rows,
        key=lambda x: (x["Edge"], x["Confidence score"] or 0),
        reverse=True
    )

    if portfolio_rows:
        st.dataframe(portfolio_rows, use_container_width=True)
    else:
        st.info("Nessun possibile value rilevato con le soglie portfolio attuali.")

    if portfolio_rows:
        if st.button("Salva Portfolio nel Tracking"):
            added = add_picks(selected_date, portfolio_rows)
            st.success(f"{added} nuove pick salvate nel tracking.")


    # ---- TRACKING PICKS ----
    st.subheader("Tracking Picks")

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
            list(pick_options.keys())
        )

        selected_pick_id = pick_options[selected_pick_label]

        new_status = st.selectbox(
            "Nuovo status",
            ["PENDING", "WIN", "LOSS", "PUSH"]
        )

        notes = st.text_input("Note", "")

        if st.button("Aggiorna pick"):
            update_pick_status(
                selected_pick_id,
                new_status,
                result=new_status,
                notes=notes
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
    selected_match = render_match_selector(matches)

    result, context = run_prediction(selected_match)

    st.metric(
        "Confidence",
        context.get("confidence_label", "-"),
        f"{context.get('confidence_score', '-')}"
    )

    st.metric(
        "Value",
        context.get("value_label", "-"),
        f"{context.get('value_score', '-')}"
    )

    render_prediction(result, selected_match.player1, selected_match.player2)
    
    st.subheader("Monte Carlo Range")

    col1, col2 = st.columns(2)

    with col1:
        st.write("Ace totali")
        st.json(context.get("mc_total_aces", {}))

    with col2:
        st.write("Break totali")
        st.json(context.get("mc_total_breaks", {}))


    st.subheader("Over/Under Simulator")

    ou_col1, ou_col2 = st.columns(2)

    with ou_col1:
        ace_line = st.number_input(
            "Linea Ace Totali",
            min_value=0.0,
            value=float(result["totals"]["aces"]),
            step=0.5
        )

        ace_over_odds = st.number_input(
            "Quota Over Ace",
            min_value=1.01,
            value=1.85,
            step=0.01
        )

        ace_under_odds = st.number_input(
            "Quota Under Ace",
            min_value=1.01,
            value=1.85,
            step=0.01
        )

    with ou_col2:
        break_line = st.number_input(
            "Linea Break Totali",
            min_value=0.0,
            value=float(result["totals"]["breaks"]),
            step=0.5
        )

        break_over_odds = st.number_input(
            "Quota Over Break",
            min_value=1.01,
            value=1.85,
            step=0.01
        )

        break_under_odds = st.number_input(
            "Quota Under Break",
            min_value=1.01,
            value=1.85,
            step=0.01
        )

    ace_values = context.get("mc_total_aces_values", [])
    break_values = context.get("mc_total_breaks_values", [])

    ace_over_prob = (
        sum(1 for v in ace_values if v > ace_line) / len(ace_values)
        if ace_values else 0
    )

    break_over_prob = (
        sum(1 for v in break_values if v > break_line) / len(break_values)
        if break_values else 0
    )

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

    ace_market_over_prob, ace_market_under_prob, ace_overround = no_vig_prob(
        ace_over_odds,
        ace_under_odds
    )

    break_market_over_prob, break_market_under_prob, break_overround = no_vig_prob(
        break_over_odds,
        break_under_odds
    )

    ace_edge = ace_over_prob - ace_market_over_prob
    break_edge = break_over_prob - break_market_over_prob

    def classify_value(edge, confidence):
        if edge >= 0.07 and confidence >= 0.60:
            return "FORTE"
        elif edge >= 0.03 and confidence >= 0.55:
            return "OK"
        else:
            return "NO BET"

    ace_value_label = classify_value(
        ace_edge,
        context.get("confidence_score", 0)
    )

    break_value_label = classify_value(
        break_edge,
        context.get("confidence_score", 0)
    )

    prob_col1, prob_col2 = st.columns(2)

    with prob_col1:
        st.metric("Probabilità Over Ace", f"{ace_over_prob:.1%}")

    with prob_col2:
        st.metric("Probabilità Over Break", f"{break_over_prob:.1%}")

    edge_col1, edge_col2 = st.columns(2)

    with edge_col1:
        st.metric(
            "Edge Over Ace",
            f"{ace_edge:.1%}",
            f"Market no-vig: {ace_market_over_prob:.1%}"
        )
        st.caption(f"Overround Ace market: {ace_overround:.1%}")

    with edge_col2:
        st.metric(
            "Edge Over Break",
            f"{break_edge:.1%}",
            f"Market no-vig: {break_market_over_prob:.1%}"
        )
        st.caption(f"Overround Break market: {break_overround:.1%}")

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

    render_breakdown(context)

if __name__ == "__main__":
    main()
