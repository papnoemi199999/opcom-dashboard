import argparse
import csv
import io
import time
from datetime import date, timedelta
from pathlib import Path

import requests


BASE_URL = "https://www.opcom.ro/rapoarte-pzu-raportPIP-export-csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": (
        "https://www.opcom.ro/"
        "grafice-ip-raportPIP-si-volumTranzactionat/ro"
    ),
}


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


def parse_opcom_csv(content, resolution):
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

        for source_row in table[header_index + 1 :]:
            if len(source_row) <= max(interval_index, price_index):
                continue

            interval = source_row[interval_index].strip()
            price = source_row[price_index].strip()
            if not interval.isdigit() or not price:
                continue

            row_resolution = f"PT{resolution}M"
            if resolution_index is not None and len(source_row) > resolution_index:
                row_resolution = source_row[resolution_index].strip() or row_resolution

            rows.append(
                {
                    "Interval": interval,
                    "Pret mediu [lei/MWh]": price,
                    "Rezolutie": row_resolution,
                }
            )

        if rows:
            return rows

    raise ValueError(f"Raportul PT{resolution}M nu contine un tabel valid.")


def download_day(session, report_date, resolution=60):
    """Descarca si parseaza raportul OPCOM pentru o singura zi."""
    url = (
        f"{BASE_URL}/{report_date:%d/%m/%Y}/ro"
        f"?resolution={resolution}"
    )
    response = session.get(url, timeout=30)
    response.raise_for_status()

    # OPCOM trimite un CSV UTF-8; utf-8-sig elimina si un eventual BOM.
    content = response.content.decode("utf-8-sig")
    return parse_opcom_csv(content, resolution)


def download_year(year, resolutions=(15, 30, 60), delay=0.2):
    """
    Descarca rapoartele zilnice pentru rezolutiile cerute intr-un singur CSV.

    In mod implicit sunt descarcate rezolutiile de 15, 30 si 60 de minute.
    """
    output_filename = f"opcom_{year}_full.csv"
    temporary_filename = f"opcom_{year}_full.tmp.csv"
    fieldnames = ["Data", "Interval", "Pret mediu [lei/MWh]", "Rezolutie"]
    downloaded_reports = 0
    skipped_reports = 0
    resolutions = tuple(dict.fromkeys(resolutions))

    with requests.Session() as session, open(
        temporary_filename, "w", newline="", encoding="utf-8-sig"
    ) as output_file:
        session.headers.update(HEADERS)
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()

        for report_date in iter_dates(year):
            for resolution in resolutions:
                try:
                    rows = download_day(session, report_date, resolution)
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

    # Fisierul vechi ramane disponibil pentru dashboard pana cand noul fisier
    # este complet, apoi este inlocuit printr-o singura operatie.
    Path(temporary_filename).replace(output_filename)

    print(
        f"\nFisier creat: {output_filename} "
        f"({downloaded_reports} rapoarte descarcate, "
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
        choices=(15, 30, 60),
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
