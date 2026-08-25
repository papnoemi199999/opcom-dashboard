import argparse
import csv
import io
import re
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


BASE_URL = "https://www.opcom.ro/rapoarte-pzu-raportPIP-export-csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": (
        "https://www.opcom.ro/"
        "grafice-ip-raportPIP-si-volumTranzactionat/ro"
    ),
}
SUPPORTED_RESOLUTIONS = (15, 30, 60)
MARKET_TIMEZONE = ZoneInfo("Europe/Bucharest")
QUARTER_HOURLY_START_DATE = date(2025, 10, 1)
DATA_DIRECTORY = Path(__file__).parent / "data"


class ResolutionMismatchError(ValueError):
    """Raportul primit are alta rezolutie decat cea solicitata."""


def expected_interval_count(report_date, resolution):
    """Calculeaza numarul de intervale, inclusiv pentru zilele de 23/25 ore."""
    start = datetime.combine(
        report_date,
        datetime_time.min,
        tzinfo=MARKET_TIMEZONE,
    )
    end = datetime.combine(
        report_date + timedelta(days=1),
        datetime_time.min,
        tzinfo=MARKET_TIMEZONE,
    )
    day_minutes = int(
        (
            end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
        ).total_seconds()
        // 60
    )
    return day_minutes // resolution


def available_resolutions(report_date):
    """Returneaza granularitatile PZU disponibile pentru ziua de livrare."""
    if report_date < QUARTER_HOURLY_START_DATE:
        return (60,)
    return SUPPORTED_RESOLUTIONS


def iter_dates(year):
    """Returneaza zilele disponibile din anul cerut."""
    today = date.today()

    if year > today.year:
        raise ValueError("Nu se pot descarca rapoarte pentru un an viitor.")

    current_date = date(year, 1, 1)
    end_date = min(date(year, 12, 31), today)

    while current_date <= end_date:
        yield current_date
        current_date += timedelta(days=1)


def parse_opcom_csv(content, requested_resolution, report_date):
    """
    Extrage tabelul cu intervale din formatele CSV returnate de OPCOM.

    Raportul PT15M contine un rezumat inaintea tabelului si are alt nume
    pentru coloana de pret fata de rapoartele PT30M si PT60M.
    """
    table = list(csv.reader(io.StringIO(content)))
    price_columns = (
        "Pret mediu [lei/MWh]",
        "Pret de Inchidere a Pietei [lei/MWh]",
    )

    for header_index, header in enumerate(table):
        if "Interval" not in header:
            continue

        price_column = next(
            (column for column in price_columns if column in header),
            None,
        )
        if price_column is None:
            continue

        interval_index = header.index("Interval")
        price_index = header.index(price_column)
        resolution_index = (
            header.index("Rezolutie") if "Rezolutie" in header else None
        )
        rows = []
        declared_resolutions = set()

        for source_row in table[header_index + 1 :]:
            if len(source_row) <= max(interval_index, price_index):
                continue

            interval = source_row[interval_index].strip()
            price = source_row[price_index].strip()
            if not interval.isdigit() or not price:
                continue

            if resolution_index is not None and len(source_row) > resolution_index:
                declared_resolution = source_row[resolution_index].strip()
                if declared_resolution:
                    declared_resolutions.add(declared_resolution)

            rows.append(
                {
                    "Interval": interval,
                    "Pret mediu [lei/MWh]": price,
                }
            )

        if rows:
            intervals = [int(row["Interval"]) for row in rows]
            if intervals != list(range(1, len(rows) + 1)):
                raise ValueError(
                    "Raportul contine intervale lipsa, duplicate sau neordonate."
                )

            if declared_resolutions:
                if len(declared_resolutions) != 1:
                    values = ", ".join(sorted(declared_resolutions))
                    raise ValueError(
                        f"Raportul contine rezolutii diferite: {values}."
                    )

                declared_resolution = declared_resolutions.pop()
                match = re.fullmatch(r"PT(15|30|60)M", declared_resolution)
                if match is None:
                    raise ValueError(
                        f"Rezolutie OPCOM necunoscuta: {declared_resolution}."
                    )
                actual_resolution = int(match.group(1))
            else:
                matching_resolutions = [
                    resolution
                    for resolution in SUPPORTED_RESOLUTIONS
                    if len(rows)
                    == expected_interval_count(report_date, resolution)
                ]
                if len(matching_resolutions) != 1:
                    raise ValueError(
                        "Rezolutia raportului nu poate fi determinata din "
                        f"cele {len(rows)} intervale."
                    )
                actual_resolution = matching_resolutions[0]

            expected_count = expected_interval_count(
                report_date,
                actual_resolution,
            )
            if len(rows) != expected_count:
                raise ValueError(
                    f"Raport PT{actual_resolution}M incomplet: "
                    f"{len(rows)} din {expected_count} intervale."
                )

            if actual_resolution != requested_resolution:
                raise ResolutionMismatchError(
                    f"s-a cerut PT{requested_resolution}M, dar OPCOM a "
                    f"returnat PT{actual_resolution}M"
                )

            for row in rows:
                row["Rezolutie"] = f"PT{actual_resolution}M"
            return rows

    raise ValueError(
        f"Raportul PT{requested_resolution}M nu contine un tabel valid."
    )


def download_day(session, report_date, resolution=60):
    """Descarca si parseaza raportul OPCOM pentru o singura zi."""
    url = f"{BASE_URL}/{report_date:%d/%m/%Y}/ro"
    response = session.get(
        url,
        params={"resolution": resolution},
        timeout=30,
    )
    response.raise_for_status()

    # OPCOM trimite un CSV UTF-8; utf-8-sig elimina si un eventual BOM.
    content = response.content.decode("utf-8-sig")
    return parse_opcom_csv(content, resolution, report_date)


def download_year(year, resolutions=(15, 30, 60), delay=0.2):
    """
    Descarca rapoartele zilnice pentru rezolutiile cerute intr-un singur CSV.

    In mod implicit sunt descarcate rezolutiile de 15, 30 si 60 de minute.
    """
    DATA_DIRECTORY.mkdir(exist_ok=True)
    output_filename = DATA_DIRECTORY / f"opcom_{year}_full.csv"
    temporary_filename = DATA_DIRECTORY / f"opcom_{year}_full.tmp.csv"
    fieldnames = ["Data", "Interval", "Pret mediu [lei/MWh]", "Rezolutie"]
    downloaded_reports = 0
    unavailable_reports = 0
    skipped_reports = 0
    resolutions = tuple(dict.fromkeys(resolutions))
    invalid_resolutions = set(resolutions).difference(SUPPORTED_RESOLUTIONS)
    if invalid_resolutions:
        values = ", ".join(str(value) for value in sorted(invalid_resolutions))
        raise ValueError(f"Rezolutii nesuportate: {values}")

    with requests.Session() as session, open(
        temporary_filename, "w", newline="", encoding="utf-8-sig"
    ) as output_file:
        session.headers.update(HEADERS)
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()

        for report_date in iter_dates(year):
            for resolution in resolutions:
                if resolution not in available_resolutions(report_date):
                    unavailable_reports += 1
                    print(
                        f"[INDISPONIBIL] {report_date:%d/%m/%Y} "
                        f"PT{resolution}M: PZU a avut granularitate orara"
                    )
                    continue

                try:
                    rows = download_day(session, report_date, resolution)
                except ResolutionMismatchError as error:
                    skipped_reports += 1
                    print(
                        f"[EROARE] {report_date:%d/%m/%Y} "
                        f"PT{resolution}M: {error}"
                    )
                except (requests.RequestException, UnicodeError, ValueError) as error:
                    skipped_reports += 1
                    print(
                        f"[EROARE] {report_date:%d/%m/%Y} "
                        f"PT{resolution}M: {error}"
                    )
                else:
                    for row in rows:
                        writer.writerow(
                            {
                                "Data": report_date.isoformat(),
                                "Interval": row.get("Interval", ""),
                                "Pret mediu [lei/MWh]": row.get(
                                    "Pret mediu [lei/MWh]", ""
                                ),
                                "Rezolutie": row.get(
                                    "Rezolutie", f"PT{resolution}M"
                                ),
                            }
                        )

                    downloaded_reports += 1
                    print(
                        f"[OK] {report_date:%d/%m/%Y} "
                        f"PT{resolution}M: {len(rows)} randuri"
                    )

                time.sleep(delay)

    if skipped_reports:
        temporary_filename.unlink(missing_ok=True)
        raise RuntimeError(
            f"Descarcarea a esuat pentru {skipped_reports} rapoarte. "
            "Fisierul existent nu a fost inlocuit."
        )

    # Fisierul vechi ramane disponibil pentru dashboard pana cand noul fisier
    # este complet, apoi este inlocuit printr-o singura operatie.
    temporary_filename.replace(output_filename)

    print(
        f"\nFisier creat: {output_filename} "
        f"({downloaded_reports} rapoarte descarcate, "
        f"{unavailable_reports} rezolutii indisponibile, "
        f"{skipped_reports} rapoarte omise)"
    )
    return output_filename


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Descarca rapoartele zilnice OPCOM intr-un singur CSV."
    )
    parser.add_argument(
        "year",
        type=int,
        nargs="?",
        default=date.today().year,
        help="anul descarcat (implicit: anul curent)",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        choices=SUPPORTED_RESOLUTIONS,
        nargs="+",
        default=[15, 30, 60],
        help=(
            "una sau mai multe rezolutii in minute "
            "(implicit: 15 30 60)"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    download_year(args.year, args.resolution)
