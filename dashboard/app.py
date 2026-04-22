import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st
from dashboard.services.data_service import get_upcoming_matches
from dashboard.services.model_service import run_prediction
from dashboard.components.match_selector import render_match_selector
from dashboard.components.filters import render_filters
from dashboard.components.prediction_view import render_prediction
from dashboard.components.breakdown_view import render_breakdown

def main():
    st.set_page_config(page_title="Madrid Tennis Predictor", layout="wide")
    st.sidebar.title("Madrid Tennis Predictor")
    render_filters()
   matches = get_upcoming_matches()
    if not matches:
        st.warning("Nessun match disponibile.")
        return
    selected = render_match_selector(matches)
    result, context = run_prediction(selected, matches)
    render_prediction(result, selected.player1, selected.player2)
    render_breakdown(context)

if __name__ == "__main__":
    main()
