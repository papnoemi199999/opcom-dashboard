# OPCOM Dashboard

Aplicație Python pentru descărcarea și vizualizarea prețurilor din Piața pentru Ziua Următoare (PZU), publicate de OPCOM.

## Funcționalități

- descarcă rapoartele zilnice pentru rezoluții de 15, 30 și 60 de minute;
- combină toate rapoartele anului într-un singur CSV;
- filtrează datele după perioadă și rezoluție;
- afișează toate prețurile pe intervale pentru perioade de maximum 7 zile și
  mediile zilnice pentru perioade mai lungi;
- permite exportul datelor filtrate.

## Instalare

Este recomandat Python 3.10 sau mai nou.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Pe Windows, activarea mediului virtual se face cu:

```powershell
.venv\Scripts\activate
```

## Descărcarea datelor

Pentru toate rezoluțiile din anul 2026:

```bash
python3 opcom_scrapper.py 2026
```

Rezultatul este salvat în `data/opcom_2026_full.csv`.

Pentru anumite rezoluții:

```bash
python3 opcom_scrapper.py 2026 --resolution 15 60
```

Pentru anul curent, argumentul pentru an poate fi omis:

```bash
python3 opcom_scrapper.py
```

Dacă fișierul anual există deja, scraperul păstrează datele existente și
descarcă numai zilele noi, inclusiv datele publicate pentru ziua următoare. Pe
31 decembrie, rularea fără argument creează și fișierul anului următor pentru
datele din 1 ianuarie.

## Pornirea dashboardului

```bash
streamlit run streamlit_app.py
```

Aplicația este disponibilă implicit la [http://localhost:8501](http://localhost:8501).

## Structura proiectului

- `streamlit_app.py` — punctul de intrare al aplicației;
- `app/` — încărcarea datelor și componentele interfeței;
- `data/` — fișierele CSV anuale generate de scraper.

Fișierele CSV pot fi actualizate oricând prin rularea scraperului.

Pentru zilele de livrare anterioare datei de 1 octombrie 2025, PZU a avut
granularitate orară. Scraperul salvează pentru acea perioadă numai rapoartele
PT60M; nu etichetează artificial datele orare drept PT15M sau PT30M.

## Actualizarea automată a datelor

Workflow-ul GitHub Actions din `.github/workflows/update-opcom.yml` rulează
scraperul zilnic la ora 15:00 în fusul orar `Europe/Bucharest`, inclusiv după
schimbarea orei de vară/iarnă. Workflow-ul poate fi pornit și manual din pagina
**Actions** a repository-ului.

Dacă toate rapoartele sunt descărcate corect, workflow-ul face commit numai când
fișierul `data/opcom_<an>_full.csv` s-a modificat. Dacă un raport nu poate fi
descărcat sau validat, scraperul păstrează fișierul existent, iar rularea eșuează
în loc să publice un CSV incomplet.
