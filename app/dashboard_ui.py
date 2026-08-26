from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from app.data_service import (
    PRICE_COLUMN,
    latest_day_data,
    minutes_for_resolution,
    prepare_comparison_series,
    prepare_display_data,
)


ROMANIAN_MONTHS = [
    "Ianuarie",
    "Februarie",
    "Martie",
    "Aprilie",
    "Mai",
    "Iunie",
    "Iulie",
    "August",
    "Septembrie",
    "Octombrie",
    "Noiembrie",
    "Decembrie",
]


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


def render_sidebar_notes():
    with st.sidebar.expander("Despre aplicație"):
        st.markdown(
            """
            Dashboardul permite explorarea prețurilor din **Piața pentru Ziua
            Următoare (PZU)** prin trei grafice:

            - **Ultima zi** - evoluția prețului în cea mai recentă zi disponibilă;
            - **Comparație** - suprapunerea mai multor luni sau perioade;
            - **Graficul principal** - analiza unei perioade și a unor intervale
              selectate.

            Datele provin din rapoartele PZU publicate pe **opcom.ro**.
            """
        )

    with st.sidebar.expander("Trecerea la intervale de 15 minute"):
        st.markdown(
            """
            Începând cu **1 octombrie 2025**, PZU a trecut de la intervale orare
            la intervale de **15 minute**, oferind de regulă 96 de intervale de
            tranzacționare. În zilele cu schimbarea orei sunt 92 sau 100 de
            intervale.

            Pentru perioadele anterioare acestei date sunt disponibile datele
            orare, cu 24 de intervale pe zi. De aceea, anumite rezoluții nu au date
            pentru toate perioadele selectabile.
            """
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
    render_data_table(displayed_data, download_key="latest_day_download")


def set_interval_selection(state_key, intervals):
    st.session_state[state_key] = intervals.copy()


def interval_selection_label(selected_count, total_count):
    if selected_count == total_count:
        return f"Intervale: toate ({total_count})"
    if selected_count == 0:
        return "Intervale: niciunul"
    return f"Intervale: {selected_count}/{total_count}"


def available_interval_options(
    dataframe,
    resolution,
    start_date,
    end_date,
):
    """Returneaza intervalele existente in perioada si rezolutia selectate."""
    return sorted(
        dataframe.loc[
            (dataframe["Rezolutie"] == resolution)
            & dataframe["Data"].dt.date.between(start_date, end_date),
            "Interval",
        ]
        .unique()
        .tolist()
    )


def render_interval_selector(
    container,
    resolution,
    state_key,
    interval_options,
    label="Intervale",
):
    minutes_per_interval = minutes_for_resolution(resolution)
    options_state_key = f"{state_key}_available_options"
    previous_options = st.session_state.get(options_state_key)
    if state_key not in st.session_state or previous_options is None:
        st.session_state[state_key] = interval_options.copy()
    elif st.session_state[state_key] == previous_options:
        st.session_state[state_key] = interval_options.copy()
    else:
        st.session_state[state_key] = [
            interval
            for interval in st.session_state[state_key]
            if interval in interval_options
        ]
    st.session_state[options_state_key] = interval_options.copy()

    selected_count = len(st.session_state[state_key])
    total_count = len(interval_options)
    popover_label = interval_selection_label(
        selected_count,
        total_count,
    )
    with container.popover(popover_label, use_container_width=True):
        st.caption(
            f"{total_count} intervale disponibile · "
            f"câte {minutes_per_interval} minute"
        )
        select_all_column, deselect_all_column = st.columns(2)
        select_all_column.button(
            "Selectează tot",
            key=f"selecteaza_tot_{state_key}",
            on_click=set_interval_selection,
            args=(state_key, interval_options),
            use_container_width=True,
        )
        deselect_all_column.button(
            "Deselectează tot",
            key=f"deselecteaza_tot_{state_key}",
            on_click=set_interval_selection,
            args=(state_key, []),
            use_container_width=True,
        )
        return st.multiselect(
            label,
            options=interval_options,
            format_func=lambda interval: f"I{interval}",
            key=state_key,
            help="Selectează unul sau mai multe intervale din listă.",
        )


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
    start_date, end_date = normalize_date_range(selected_dates)

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
    interval_options = available_interval_options(
        year_dataframe,
        selected_resolution,
        start_date,
        end_date,
    )
    interval_state_key = f"intervale_{selected_resolution}"
    selected_intervals = render_interval_selector(
        interval_column,
        selected_resolution,
        interval_state_key,
        interval_options,
        label="Intervale selectate",
    )

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


def comparison_interval_text(intervals, maximum_interval):
    if not intervals:
        return "niciun interval"
    if len(intervals) == maximum_interval:
        return "toate intervalele"
    if len(intervals) <= 3:
        return ", ".join(f"I{interval}" for interval in intervals)
    return f"{len(intervals)} intervale"


def unique_series_label(label, used_labels):
    occurrence = used_labels.get(label, 0) + 1
    used_labels[label] = occurrence
    return label if occurrence == 1 else f"{label} ({occurrence})"


def default_comparison_period(dataframe, series_index):
    minimum_date = dataframe["Data"].min().date()
    maximum_date = dataframe["Data"].max().date()
    preferred_year = 2025 + series_index
    preferred_start = date(preferred_year, 1, 1)
    preferred_end = date(preferred_year, 1, 31)
    if minimum_date <= preferred_start <= maximum_date:
        return preferred_start, min(preferred_end, maximum_date)

    if series_index == 0:
        start_date = minimum_date
        return start_date, min(start_date + timedelta(days=30), maximum_date)

    end_date = maximum_date
    return max(minimum_date, end_date - timedelta(days=30)), end_date


def render_comparison_chart(dataframe):
    st.subheader("Comparație")
    st.caption(
        "Compară mediile zilnice ale mai multor luni sau perioade pe aceeași "
        "axă. Fiecare serie poate folosi propriile intervale orare."
    )

    mode_column, resolution_column, count_column = st.columns(
        [2.2, 1, 1],
        vertical_alignment="bottom",
    )
    comparison_mode = mode_column.radio(
        "Mod de comparație",
        options=["Pe lună", "Pe date libere"],
        horizontal=True,
        key="comparison_mode",
    )
    available_resolutions = sorted(dataframe["Rezolutie"].unique().tolist())
    selected_resolution = resolution_column.selectbox(
        "Rezoluție",
        options=available_resolutions,
        format_func=format_resolution_label,
        index=(
            available_resolutions.index("PT60M")
            if "PT60M" in available_resolutions
            else 0
        ),
        key="comparison_resolution",
    )
    series_count = count_column.selectbox(
        "Număr de serii",
        options=[2, 3, 4],
        key="comparison_series_count",
    )

    available_years = sorted(dataframe["Data"].dt.year.unique().tolist())
    series_columns = st.columns(series_count, gap="medium")
    series_settings = []

    for series_index, series_column in enumerate(series_columns):
        series_column.markdown(f"**Seria {series_index + 1}**")
        if comparison_mode == "Pe lună":
            preferred_year = 2025 + series_index
            default_year = (
                preferred_year
                if preferred_year in available_years
                else available_years[min(series_index, len(available_years) - 1)]
            )
            selected_year = series_column.selectbox(
                "An",
                options=available_years,
                index=available_years.index(default_year),
                key=f"comparison_month_year_{series_index}",
            )
            selected_month = series_column.selectbox(
                "Lună",
                options=list(range(1, 13)),
                format_func=lambda month: ROMANIAN_MONTHS[month - 1],
                key=f"comparison_month_{series_index}",
            )
            start_date = date(selected_year, selected_month, 1)
            end_date = date(
                selected_year,
                selected_month,
                monthrange(selected_year, selected_month)[1],
            )
            base_label = f"{ROMANIAN_MONTHS[selected_month - 1]} {selected_year}"
            alignment = "day_of_month"
        else:
            minimum_date = dataframe["Data"].min().date()
            maximum_date = dataframe["Data"].max().date()
            default_period = default_comparison_period(
                dataframe,
                series_index,
            )
            selected_dates = series_column.date_input(
                "Perioada",
                value=default_period,
                min_value=minimum_date,
                max_value=maximum_date,
                key=f"comparison_free_dates_{series_index}",
            )
            start_date, end_date = normalize_date_range(selected_dates)
            base_label = (
                f"{start_date.strftime('%d.%m.%Y')}–"
                f"{end_date.strftime('%d.%m.%Y')}"
            )
            alignment = "period_day"

        interval_state_key = (
            f"comparison_intervals_{series_index}_{selected_resolution}"
        )
        interval_options = available_interval_options(
            dataframe,
            selected_resolution,
            start_date,
            end_date,
        )
        selected_intervals = render_interval_selector(
            series_column,
            selected_resolution,
            interval_state_key,
            interval_options,
        )
        interval_text = comparison_interval_text(
            selected_intervals,
            len(interval_options),
        )
        series_settings.append(
            (
                start_date,
                end_date,
                selected_intervals,
                alignment,
                f"{base_label} · {interval_text}",
            )
        )

    comparison_series = []
    used_labels = {}
    missing_series = []
    for start_date, end_date, intervals, alignment, base_label in series_settings:
        if not intervals:
            missing_series.append(f"{base_label}: niciun interval selectat")
            continue

        label = unique_series_label(base_label, used_labels)
        series_data = prepare_comparison_series(
            dataframe=dataframe,
            resolution=selected_resolution,
            start_date=start_date,
            end_date=end_date,
            selected_intervals=intervals,
            alignment=alignment,
            label=label,
        )
        if series_data.empty:
            missing_series.append(f"{label}: nu există date")
        else:
            comparison_series.append(series_data)

    if missing_series:
        st.warning("Serii neafișate — " + "; ".join(missing_series) + ".")
    if not comparison_series:
        st.info("Selectează intervale și perioade care conțin date.")
        return

    comparison_data = pd.concat(comparison_series, ignore_index=True)
    x_axis_title = (
        "Ziua lunii"
        if comparison_mode == "Pe lună"
        else "Poziția zilei în perioadă"
    )
    chart = px.line(
        comparison_data,
        x="Pozitie",
        y=PRICE_COLUMN,
        color="Serie",
        markers=True,
        hover_data={"Data": "|%d.%m.%Y", "Pozitie": True},
        labels={
            "Pozitie": x_axis_title,
            PRICE_COLUMN: "Preț mediu [lei/MWh]",
            "Serie": "Serie",
        },
    )
    chart.update_layout(hovermode="x unified", legend_title_text="Serie")
    if comparison_mode == "Pe lună":
        chart.update_xaxes(range=[1, 31], dtick=1)
    else:
        chart.update_xaxes(rangemode="tozero")
    st.plotly_chart(
        chart,
        use_container_width=True,
        key="comparison_chart",
    )

    with st.expander("Vezi datele comparației"):
        table_data = comparison_data.copy()
        table_data["Data"] = table_data["Data"].dt.strftime("%Y-%m-%d")
        st.dataframe(
            table_data[["Serie", "Pozitie", "Data", PRICE_COLUMN]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Pozitie": st.column_config.NumberColumn(
                    x_axis_title,
                    format="%d",
                ),
                PRICE_COLUMN: st.column_config.NumberColumn(
                    format="%.2f lei/MWh"
                ),
            },
        )


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
    render_data_table(displayed_data, download_key="filtered_data_download")
    st.caption(
        f"Sursă: {source_name} · "
        f"{len(displayed_data):,} valori afișate"
    )


def render_data_table(displayed_data, download_key):
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
            key=download_key,
        )
