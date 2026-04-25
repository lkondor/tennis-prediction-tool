import streamlit as st


def render_breakdown(context):
    st.subheader("Model Breakdown")

    st.json({
        "matched_player_a": context.get("matched_player_a"),
        "matched_player_b": context.get("matched_player_b"),
        "data_quality_a": context.get("data_quality_a"),
        "data_quality_b": context.get("data_quality_b"),
        "stats_source_a": context.get("stats_source_a"),
        "stats_source_b": context.get("stats_source_b"),
        "elo_a": context.get("elo_a"),
        "elo_b": context.get("elo_b"),
        "win_prob_a": context.get("win_prob_a"),
        "win_prob_b": context.get("win_prob_b"),
        "ace_rate_a_used": context.get("ace_rate_a_used"),
        "ace_rate_b_used": context.get("ace_rate_b_used"),
        "break_rate_a_used": context.get("break_rate_a_used"),
        "break_rate_b_used": context.get("break_rate_b_used"),
        "court_factor": context.get("court_factor"),
        "madrid_factor": context.get("madrid_factor"),
        "match_length": context.get("match_length"),
        "avg_temp": context.get("avg_temp"),
        "wind_kmh": context.get("wind_kmh"),
        "ace_weather_factor": context.get("ace_weather_factor"),
        "break_weather_factor": context.get("break_weather_factor"),
        "confidence_score": context.get("confidence_score"),
        "confidence_label": context.get("confidence_label"),
        "data_confidence": context.get("data_confidence"),
        "weather_confidence": context.get("weather_confidence"),
        "court_confidence": context.get("court_confidence"),
        "model_edge": context.get("model_edge"),
        "stat_consistency": context.get("stat_consistency"),
    })
