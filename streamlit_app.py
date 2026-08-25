from pathlib import Path

import streamlit as st

from app.dashboard_ui import (
    render_dashboard,
    render_file_uploader,
    render_header,
    render_invalid_rows_warning,
    render_chart_filters,
    render_comparison_chart,
    render_latest_day_chart,
)
from app.data_service import (
    filter_data,
    load_available_data,
    prepare_display_data,
)


st.set_page_config(
    page_title="Dashboard prețuri PZU RO",
    page_icon="⚡",
    layout="wide",
)

render_header()
uploaded_file = render_file_uploader()

try:
    dataframe, source_name = load_available_data(
        uploaded_file,
        Path(__file__).parent / "data",
    )
except FileNotFoundError:
    st.info(
        "Nu am găsit niciun fișier `opcom_*.csv`. "
        "Rulează scraperul sau încarcă manual un CSV."
    )
    st.stop()
except Exception as error:
    if uploaded_file is not None:
        st.error(f"Fișierul nu a putut fi citit: {error}")
    else:
        st.error(f"Fișierele locale nu au putut fi citite: {error}")
    st.stop()

if dataframe.empty:
    st.warning("Fișierul nu conține rânduri valide.")
    st.stop()

render_invalid_rows_warning(dataframe)
render_latest_day_chart(dataframe)
st.divider()
render_comparison_chart(dataframe)
st.divider()
filters = render_chart_filters(dataframe)

if not filters.intervals:
    st.info(
        "Nu este selectat niciun interval. "
        "Selectează cel puțin unul pentru a afișa graficul."
    )
else:
    period_data = filter_data(
        filters.dataframe,
        filters.start_date,
        filters.end_date,
        filters.resolution,
        filters.intervals,
    )
    if period_data.empty:
        st.warning("Niciun rând nu corespunde filtrelor selectate.")
    else:
        displayed_data, single_day = prepare_display_data(
            period_data,
            filters.minutes_per_interval,
        )
        render_dashboard(displayed_data, single_day, source_name)
