import re
from pathlib import Path

import pandas as pd
import streamlit as st


PRICE_COLUMN = "Pret mediu [lei/MWh]"
REQUIRED_COLUMNS = {"Interval", PRICE_COLUMN, "Rezolutie"}
RESOLUTION_MINUTES = {
    "PT15M": 15,
    "PT30M": 30,
    "PT60M": 60,
}
DETAILED_VIEW_MAX_DAYS = 7


@st.cache_data(show_spinner=False)
def load_csv(source, filename, cache_version):
    """Citeste, valideaza si normalizeaza un fisier CSV OPCOM."""
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


def local_csv_files(base_directory):
    """Gaseste si ordoneaza toate fisierele locale opcom_*.csv."""
    files = list(Path(base_directory).glob("opcom_*.csv"))
    return sorted(
        files,
        key=lambda path: (
            0 if path.stem.endswith("_full") else 1,
            len(re.findall(r"\d+", path.stem)),
            path.name,
        ),
    )


def load_available_data(uploaded_file, base_directory):
    """Incarca fisierul trimis sau combina toate fisierele locale."""
    if uploaded_file is not None:
        source_name = uploaded_file.name
        cache_version = len(uploaded_file.getvalue())
        return (
            load_csv(uploaded_file, source_name, cache_version),
            source_name,
        )

    files = local_csv_files(base_directory)
    if not files:
        raise FileNotFoundError("Nu exista fisiere locale opcom_*.csv.")

    local_dataframes = []
    invalid_by_resolution = {}
    for path in files:
        file_stats = path.stat()
        cache_version = (file_stats.st_mtime_ns, file_stats.st_size)
        file_dataframe = load_csv(path, path.name, cache_version)
        local_dataframes.append(file_dataframe)
        for resolution, count in file_dataframe.attrs.get(
            "invalid_by_resolution", {}
        ).items():
            invalid_by_resolution[resolution] = (
                invalid_by_resolution.get(resolution, 0) + count
            )

    dataframe = pd.concat(local_dataframes, ignore_index=True)
    dataframe = (
        dataframe.drop_duplicates(subset=["Data", "Interval", "Rezolutie"])
        .sort_values(["Data", "Interval", "Rezolutie"])
        .reset_index(drop=True)
    )
    dataframe.attrs["invalid_by_resolution"] = invalid_by_resolution
    return dataframe, f"{len(files)} fișiere locale"


def minutes_for_resolution(resolution):
    """Intoarce durata in minute pentru o rezolutie OPCOM."""
    if resolution in RESOLUTION_MINUTES:
        return RESOLUTION_MINUTES[resolution]

    resolution_match = re.fullmatch(r"PT(\d+)M", resolution)
    return int(resolution_match.group(1)) if resolution_match else 60


def filter_data(
    dataframe,
    start_date,
    end_date,
    resolution,
    selected_intervals,
):
    """Aplica filtrele de perioada, rezolutie si interval."""
    return dataframe[
        dataframe["Data"].dt.date.between(start_date, end_date)
        & (dataframe["Rezolutie"] == resolution)
        & dataframe["Interval"].isin(selected_intervals)
    ]


def latest_day_data(dataframe):
    """Intoarce toate randurile pentru cea mai recenta zi disponibila."""
    latest_date = dataframe["Data"].max().date()
    return dataframe[dataframe["Data"].dt.date == latest_date]


def interval_start_time(interval, minutes_per_interval):
    """Formateaza ora de inceput a unui interval ca HH:MM."""
    total_minutes = (interval - 1) * minutes_per_interval
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def prepare_display_data(period_data, minutes_per_interval):
    """Pastreaza intervalele pe maximum 7 zile, altfel agrega zilnic."""
    day_count = period_data["Data"].dt.date.nunique()
    single_day = day_count == 1
    if day_count > DETAILED_VIEW_MAX_DAYS:
        displayed_data = period_data.groupby("Data", as_index=False)[
            PRICE_COLUMN
        ].mean()
        return displayed_data, single_day

    displayed_data = period_data[["Data", "Interval", PRICE_COLUMN]].copy()
    interval_offsets = pd.to_timedelta(
        (displayed_data["Interval"] - 1) * minutes_per_interval,
        unit="m",
    )
    displayed_data["Data și ora"] = (
        displayed_data["Data"].dt.normalize() + interval_offsets
    )
    displayed_data["Ora"] = displayed_data["Interval"].map(
        lambda interval: interval_start_time(interval, minutes_per_interval)
    )
    displayed_data["Interval orar"] = displayed_data["Interval"].map(
        lambda interval: (
            f"{interval_start_time(interval, minutes_per_interval)}–"
            f"{interval_start_time(interval + 1, minutes_per_interval)}"
        )
    )
    return displayed_data, single_day
