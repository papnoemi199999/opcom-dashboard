from dataclasses import dataclass
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from app.data_service import (
    PRICE_COLUMN,
    latest_day_data,
    minutes_for_resolution,
    prepare_display_data,
)


@dataclass(frozen=True)
class FilterSelection:
    dataframe: pd.DataFrame
    start_date: date
    end_date: date
    resolution: str
    intervals: list[int]
    minutes_per_interval: int


def render_header():
    st.title("Dashboard prețuri PZU RO")
    st.caption(
        "Analiză și filtrare pentru rapoartele Pieței pentru Ziua Următoare"
    )


def render_file_uploader():
    return st.sidebar.file_uploader(
        "Încarcă alt CSV OPCOM",
        type="csv",
        help="Fișierul încărcat are prioritate față de fișierele locale.",
    )


def render_invalid_rows_warning(dataframe):
    invalid_by_resolution = dataframe.attrs.get("invalid_by_resolution", {})
    if not invalid_by_resolution:
        return

    invalid_details = ", ".join(
        f"{resolution}: {count:,}"
        for resolution, count in invalid_by_resolution.items()
    )
    st.warning(
        "Unele rânduri invalide au fost ignorate "
        f"({invalid_details}). Regenerează fișierul cu scraperul actualizat."
    )


def format_resolution_label(value):
    return value.replace("PT", "").replace("M", " minute")


def render_latest_day_chart(dataframe):
    day_dataframe = latest_day_data(dataframe)
    latest_date = day_dataframe["Data"].max()
    available_resolutions = sorted(
        day_dataframe["Rezolutie"].unique().tolist()
    )
    preferred_resolution = next(
        (
            resolution
            for resolution in ("PT15M", "PT60M", "PT30M")
            if resolution in available_resolutions
        ),
        available_resolutions[0],
    )

    title_column, resolution_column = st.columns(
        [4, 1],
        vertical_alignment="bottom",
    )
    title_column.subheader("Ultima zi din baza de date")
    title_column.caption(latest_date.strftime("%d.%m.%Y"))
    selected_resolution = resolution_column.selectbox(
        "Rezoluție",
        options=available_resolutions,
        format_func=format_resolution_label,
        index=available_resolutions.index(preferred_resolution),
        key="latest_day_resolution",
    )

    resolution_data = day_dataframe[
        day_dataframe["Rezolutie"] == selected_resolution
    ]
    minutes_per_interval = minutes_for_resolution(selected_resolution)
    displayed_data, _ = prepare_display_data(
        resolution_data,
        minutes_per_interval,
    )

    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric(
        "Preț mediu",
        f"{format_number(displayed_data[PRICE_COLUMN].mean())} lei/MWh",
    )
    metric_2.metric(
        "Preț minim",
        f"{format_number(displayed_data[PRICE_COLUMN].min())} lei/MWh",
    )
    metric_3.metric(
        "Preț maxim",
        f"{format_number(displayed_data[PRICE_COLUMN].max())} lei/MWh",
    )

    chart = px.line(
        displayed_data,
        x="Ora",
        y=PRICE_COLUMN,
        markers=True,
        labels={PRICE_COLUMN: "Preț [lei/MWh]", "Ora": "Ora"},
    )
    chart.update_layout(hovermode="x unified")
    st.plotly_chart(
        chart,
        use_container_width=True,
        key="latest_day_chart",
    )


def set_interval_selection(state_key, intervals):
    st.session_state[state_key] = intervals.copy()


def interval_selection_label(selected_count, total_count):
    if selected_count == total_count:
        return f"Intervale: toate ({total_count})"
    if selected_count == 0:
        return "Intervale: niciunul"
    return f"Intervale: {selected_count}/{total_count}"


def render_chart_filters(dataframe):
    (
        year_column,
        period_column,
        resolution_column,
        interval_column,
    ) = st.columns(
        [1, 2, 1.2, 1.6],
        gap="small",
        vertical_alignment="bottom",
    )

    available_years = sorted(dataframe["Data"].dt.year.unique().tolist())
    year_options = ["Toți anii", *available_years]
    selected_year = year_column.selectbox(
        "An",
        options=year_options,
        index=len(year_options) - 1,
    )

    if selected_year == "Toți anii":
        year_dataframe = dataframe
    else:
        year_dataframe = dataframe[dataframe["Data"].dt.year == selected_year]

    minimum_date = year_dataframe["Data"].min().date()
    maximum_date = year_dataframe["Data"].max().date()
    selected_dates = period_column.date_input(
        "Perioada",
        value=(minimum_date, maximum_date),
        min_value=minimum_date,
        max_value=maximum_date,
        key=f"perioada_{selected_year}",
    )

    available_resolutions = sorted(
        year_dataframe["Rezolutie"].unique().tolist()
    )
    selected_resolution = resolution_column.selectbox(
        "Rezoluție",
        options=available_resolutions,
        format_func=format_resolution_label,
        index=(
            available_resolutions.index("PT60M")
            if "PT60M" in available_resolutions
            else 0
        ),
        key="main_chart_resolution",
    )

    minutes_per_interval = minutes_for_resolution(selected_resolution)
    maximum_interval = 24 * 60 // minutes_per_interval
    interval_options = list(range(1, maximum_interval + 1))
    interval_state_key = f"intervale_{selected_resolution}"
    if interval_state_key not in st.session_state:
        st.session_state[interval_state_key] = interval_options.copy()

    selected_count = len(st.session_state[interval_state_key])
    popover_label = interval_selection_label(
        selected_count,
        maximum_interval,
    )
    with interval_column.popover(
        popover_label,
        use_container_width=True,
    ):
        st.caption(
            f"{maximum_interval} intervale pe zi · "
            f"câte {minutes_per_interval} minute"
        )
        select_all_column, deselect_all_column = st.columns(2)
        select_all_column.button(
            "Selectează tot",
            key=f"selecteaza_tot_{selected_resolution}",
            on_click=set_interval_selection,
            args=(interval_state_key, interval_options),
            use_container_width=True,
        )
        deselect_all_column.button(
            "Deselectează tot",
            key=f"deselecteaza_tot_{selected_resolution}",
            on_click=set_interval_selection,
            args=(interval_state_key, []),
            use_container_width=True,
        )
        selected_intervals = st.multiselect(
            "Intervale selectate",
            options=interval_options,
            format_func=lambda interval: f"I{interval}",
            key=interval_state_key,
            help="Selectează unul sau mai multe intervale din listă.",
        )

    start_date, end_date = normalize_date_range(selected_dates)
    return FilterSelection(
        dataframe=year_dataframe,
        start_date=start_date,
        end_date=end_date,
        resolution=selected_resolution,
        intervals=selected_intervals,
        minutes_per_interval=minutes_per_interval,
    )


def normalize_date_range(selected_dates):
    if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
        return selected_dates
    if isinstance(selected_dates, (tuple, list)):
        return selected_dates[0], selected_dates[0]
    return selected_dates, selected_dates


def format_number(value, decimals=2):
    return f"{value:,.{decimals}f}".replace(",", " ")


def render_dashboard(displayed_data, single_day, source_name):
    shows_intervals = "Interval" in displayed_data.columns
    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric(
        "Preț mediu",
        f"{format_number(displayed_data[PRICE_COLUMN].mean())} lei/MWh",
    )
    metric_2.metric(
        "Preț minim",
        f"{format_number(displayed_data[PRICE_COLUMN].min())} lei/MWh",
    )
    metric_3.metric(
        "Preț maxim",
        f"{format_number(displayed_data[PRICE_COLUMN].max())} lei/MWh",
    )
    metric_4.metric(
        "Intervale" if shows_intervals else "Zile",
        format_number(len(displayed_data), decimals=0),
    )

    if single_day:
        selected_day = displayed_data["Data"].iloc[0].strftime("%d.%m.%Y")
        st.subheader(f"Prețul pe intervale pentru {selected_day}")
        chart = px.line(
            displayed_data,
            x="Ora",
            y=PRICE_COLUMN,
            markers=True,
            labels={PRICE_COLUMN: "Preț [lei/MWh]", "Ora": "Ora"},
        )
    elif shows_intervals:
        st.subheader("Prețul pe intervale în perioada selectată")
        chart = px.line(
            displayed_data,
            x="Data și ora",
            y=PRICE_COLUMN,
            render_mode="webgl",
            labels={PRICE_COLUMN: "Preț [lei/MWh]"},
        )
    else:
        st.subheader("Prețul mediu pe zi")
        st.caption(
            "Pentru perioade mai lungi de 7 zile, graficul afișează "
            "mediile zilnice. Selectează maximum 7 zile pentru toate "
            "intervalele."
        )
        chart = px.line(
            displayed_data,
            x="Data",
            y=PRICE_COLUMN,
            markers=True,
            labels={PRICE_COLUMN: "Preț mediu [lei/MWh]"},
        )

    chart.update_layout(hovermode="x unified")
    st.plotly_chart(chart, use_container_width=True)
    render_data_table(displayed_data)
    st.caption(
        f"Sursă: {source_name} · "
        f"{len(displayed_data):,} valori afișate"
    )


def render_data_table(displayed_data):
    with st.expander("Vezi datele din grafic"):
        table_data = displayed_data.copy()
        table_data["Data"] = table_data["Data"].dt.strftime("%Y-%m-%d")
        if "Interval" in table_data.columns:
            table_data = table_data[
                ["Data", "Interval", "Interval orar", PRICE_COLUMN]
            ]
        else:
            table_data = table_data[["Data", PRICE_COLUMN]]
        st.dataframe(
            table_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                PRICE_COLUMN: st.column_config.NumberColumn(
                    format="%.2f lei/MWh"
                ),
            },
        )

        csv_data = table_data.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Descarcă datele filtrate",
            data=csv_data,
            file_name="opcom_filtrat.csv",
            mime="text/csv",
        )
