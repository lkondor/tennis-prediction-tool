import streamlit as st

def render_breakdown(context):
    st.subheader("Model Breakdown")

    st.json({
        "Surface Factor": context.get("surface_factor", 1),
        "Madrid Factor": context.get("madrid_factor", 1),
        "Court Factor": context.get("court_factor", 1),
        "Match Length": context.get("match_length", 1),
        "Elo A": context.get("elo_a", "-"),
        "Elo B": context.get("elo_b", "-"),
        "Win Prob A": context.get("win_prob_a", "-"),
        "Win Prob B": context.get("win_prob_b", "-"),
    })
