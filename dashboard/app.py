import streamlit as st

from services.data_service import get_upcoming_matches
from services.model_service import run_prediction

from components.match_selector import render_match_selector
from components.prediction_view import render_prediction
from components.breakdown_view import render_breakdown
from components.filters import render_filters


def main():
    st.set_page_config(layout="wide")

    matches = get_upcoming_matches()

    if not matches:
        st.error("Nessuna partita trovata.")
        return

    render_filters()

    selected_match = render_match_selector(matches)

    result, context = run_prediction(selected_match)

    render_prediction(
        result,
        selected_match.player1,
        selected_match.player2
    )

    render_breakdown(context)


if __name__ == "__main__":
    main()
