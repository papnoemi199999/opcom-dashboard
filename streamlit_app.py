import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


PRICE_COLUMN = "Pret mediu [lei/MWh]"
REQUIRED_COLUMNS = {"Interval", PRICE_COLUMN, "Rezolutie"}
RESOLUTION_MINUTES = {
    "PT15M": 15,
    "PT30M": 30,
    "PT60M": 60,
}


st.set_page_config(
    page_title="Dashboard prețuri PZU RO",
    page_icon="⚡",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def load_csv(source, filename, cache_version):
    """
    Citeste un fisier CSV OPCOM si pregateste datele pentru dashboard.

    Verifica existenta coloanelor obligatorii, extrage data din numele
    fisierului atunci cand este necesar si converteste valorile in tipurile
    potrivite pentru filtrare si reprezentare grafica.

    cache_version se schimba atunci cand fisierul este regenerat, astfel incat
    Streamlit sa nu afiseze date vechi din cache.
    """
    data = pd.read_csv(source, encoding="utf-8-sig")
    data.columns = data.columns.str.strip()

    missing_columns = REQUIRED_COLUMNS.difference(data.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Lipsesc coloanele obligatorii: {missing}")

    if "Data" not in data.columns:
        match = re.search(r"(\d{4})_(\d{2})_(\d{2})", filename)
        if not match:
            raise ValueError(
                "CSV-ul nu are coloana Data, iar data nu poate fi extrasa "
                "din numele fisierului."
            )
        year, month, day = match.groups()
        data.insert(0, "Data", f"{year}-{month}-{day}")

    data["Data"] = pd.to_datetime(data["Data"], errors="coerce")
    data["Interval"] = pd.to_numeric(data["Interval"], errors="coerce")
    data[PRICE_COLUMN] = pd.to_numeric(
        data[PRICE_COLUMN].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )
    data["Rezolutie"] = data["Rezolutie"].astype(str).str.strip()

    invalid_rows = data[["Data", "Interval", PRICE_COLUMN]].isna().any(axis=1)
    invalid_by_resolution = (
        data.loc[invalid_rows, "Rezolutie"].value_counts().to_dict()
    )
    data = data.dropna(subset=["Data", "Interval", PRICE_COLUMN])
    data["Interval"] = data["Interval"].astype(int)
    data = data.sort_values(["Data", "Interval"]).reset_index(drop=True)
    data.attrs["invalid_by_resolution"] = invalid_by_resolution
    return data


def local_csv_files():
    """
    Gaseste toate fisierele locale care respecta modelul opcom_*.csv.

    Fisierele sunt ordonate astfel incat CSV-ul anual agregat sa fie selectat
    implicit inaintea fisierelor care contin date pentru o singura zi.
    """
    files = list(Path(__file__).parent.glob("opcom_*.csv"))
    return sorted(
        files,
        key=lambda path: (
            0 if path.stem.endswith("_full") else 1,
            len(re.findall(r"\d+", path.stem)),
            path.name,
        ),
    )


def format_number(value, decimals=2):
    """
    Formateaza un numar pentru afisare, cu spatiu ca separator de mii.

    Parametrul decimals stabileste numarul de zecimale afisate.
    """
    return f"{value:,.{decimals}f}".replace(",", " ")


def interval_start_time(interval, minutes_per_interval):
    """Formateaza ora de inceput a unui interval ca HH:MM."""
    total_minutes = (interval - 1) * minutes_per_interval
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


st.title("Dashboard prețuri PZU RO")
st.caption("Analiză și filtrare pentru rapoartele Pieței pentru Ziua Următoare")

files = local_csv_files()
uploaded_file = st.sidebar.file_uploader(
    "Încarcă alt CSV OPCOM",
    type="csv",
    help="Fișierul încărcat are prioritate față de fișierele locale.",
)

if uploaded_file is not None:
    source = uploaded_file
    source_name = uploaded_file.name
    cache_version = len(uploaded_file.getvalue())
elif files:
    selected_path = st.sidebar.selectbox(
        "Fișier local",
        options=files,
        format_func=lambda path: path.name,
    )
    source = selected_path
    source_name = selected_path.name
    file_stats = selected_path.stat()
    cache_version = (file_stats.st_mtime_ns, file_stats.st_size)
else:
    st.info(
        "Nu am găsit niciun fișier `opcom_*.csv`. "
        "Rulează scraperul sau încarcă un CSV din bara laterală."
    )
    st.stop()

try:
    dataframe = load_csv(source, source_name, cache_version)
except Exception as error:
    st.error(f"Fișierul nu a putut fi citit: {error}")
    st.stop()

if dataframe.empty:
    st.warning("Fișierul nu conține rânduri valide.")
    st.stop()

invalid_by_resolution = dataframe.attrs.get("invalid_by_resolution", {})
if invalid_by_resolution:
    invalid_details = ", ".join(
        f"{resolution}: {count:,}"
        for resolution, count in invalid_by_resolution.items()
    )
    st.warning(
        "Unele rânduri invalide au fost ignorate "
        f"({invalid_details}). Regenerează fișierul cu scraperul actualizat."
    )

st.sidebar.header("Filtre")

minimum_date = dataframe["Data"].min().date()
maximum_date = dataframe["Data"].max().date()
selected_dates = st.sidebar.date_input(
    "Perioada",
    value=(minimum_date, maximum_date),
    min_value=minimum_date,
    max_value=maximum_date,
)

available_resolutions = sorted(dataframe["Rezolutie"].unique().tolist())
selected_resolution = st.sidebar.selectbox(
    "Rezoluție",
    options=available_resolutions,
    format_func=lambda value: value.replace("PT", "").replace("M", " minute"),
    index=(
        available_resolutions.index("PT60M")
        if "PT60M" in available_resolutions
        else 0
    ),
)

minutes_per_interval = RESOLUTION_MINUTES.get(selected_resolution)
if minutes_per_interval is None:
    resolution_match = re.fullmatch(r"PT(\d+)M", selected_resolution)
    minutes_per_interval = (
        int(resolution_match.group(1)) if resolution_match else 60
    )

minimum_interval = 1
maximum_interval = 24 * 60 // minutes_per_interval
interval_options = list(range(minimum_interval, maximum_interval + 1))
interval_state_key = f"intervale_{selected_resolution}"
if interval_state_key not in st.session_state:
    st.session_state[interval_state_key] = interval_options.copy()

select_all_column, deselect_all_column = st.sidebar.columns(2)
if select_all_column.button(
    "Selectează tot",
    key=f"selecteaza_tot_{selected_resolution}",
    use_container_width=True,
):
    st.session_state[interval_state_key] = interval_options.copy()
if deselect_all_column.button(
    "Deselectează tot",
    key=f"deselecteaza_tot_{selected_resolution}",
    use_container_width=True,
):
    st.session_state[interval_state_key] = []

selected_intervals = st.sidebar.multiselect(
    "Interval",
    options=interval_options,
    format_func=lambda interval: f"I{interval}",
    key=interval_state_key,
    help="Selectează unul sau mai multe intervale din listă.",
)
st.sidebar.caption(
    f"{maximum_interval} intervale pe zi · "
    f"câte {minutes_per_interval} minute"
)

if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
elif isinstance(selected_dates, (tuple, list)):
    start_date = end_date = selected_dates[0]
else:
    start_date = end_date = selected_dates

if not selected_intervals:
    st.info(
        "Nu este selectat niciun interval. "
        "Selectează cel puțin unul pentru a afișa graficul."
    )
    st.stop()

period_data = dataframe[
    dataframe["Data"].dt.date.between(start_date, end_date)
    & (dataframe["Rezolutie"] == selected_resolution)
    & dataframe["Interval"].isin(selected_intervals)
]

if period_data.empty:
    st.warning("Niciun rând nu corespunde filtrelor selectate.")
    st.stop()

# Pentru o singura zi pastram valorile orare. Pentru o perioada mai lunga
# calculam o singura valoare medie pentru fiecare zi.
single_day = period_data["Data"].dt.date.nunique() == 1

if single_day:
    displayed_data = period_data[["Data", "Interval", PRICE_COLUMN]].copy()
    displayed_data["Ora"] = displayed_data["Interval"].map(
        lambda interval: interval_start_time(interval, minutes_per_interval)
    )
    displayed_data["Interval orar"] = displayed_data["Interval"].map(
        lambda interval: (
            f"{interval_start_time(interval, minutes_per_interval)}–"
            f"{interval_start_time(interval + 1, minutes_per_interval)}"
        )
    )
else:
    displayed_data = period_data.groupby("Data", as_index=False)[
        PRICE_COLUMN
    ].mean()

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
    "Intervale" if single_day else "Zile",
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
else:
    st.subheader("Prețul mediu pe zi")
    chart = px.line(
        displayed_data,
        x="Data",
        y=PRICE_COLUMN,
        markers=True,
        labels={PRICE_COLUMN: "Preț mediu [lei/MWh]"},
    )

chart.update_layout(hovermode="x unified")
st.plotly_chart(chart, use_container_width=True)

with st.expander("Vezi datele din grafic"):
    table_data = displayed_data.copy()
    table_data["Data"] = table_data["Data"].dt.strftime("%Y-%m-%d")
    if single_day:
        table_data = table_data[
            ["Data", "Interval", "Interval orar", PRICE_COLUMN]
        ]
    st.dataframe(
        table_data,
        use_container_width=True,
        hide_index=True,
        column_config={
            PRICE_COLUMN: st.column_config.NumberColumn(format="%.2f lei/MWh"),
        },
    )

    csv_data = table_data.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Descarcă datele filtrate",
        data=csv_data,
        file_name="opcom_filtrat.csv",
        mime="text/csv",
    )

st.caption(
    f"Sursă: {source_name} · "
    f"{len(displayed_data):,} valori afișate"
)
