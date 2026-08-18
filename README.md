# OPCOM Dashboard

Aplicație Python pentru descărcarea și vizualizarea prețurilor din Piața pentru Ziua Următoare (PZU), publicate de OPCOM.

## Funcționalități

- descarcă rapoartele zilnice pentru rezoluții de 15, 30 și 60 de minute;
- combină toate rapoartele anului într-un singur CSV;
- filtrează datele după perioadă și rezoluție;
- afișează prețul mediu zilnic pentru perioade de mai multe zile;
- afișează prețurile pe intervale pentru o singură zi;
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

Rezultatul este salvat în `opcom_2026_full.csv`.

Pentru anumite rezoluții:

```bash
python3 opcom_scrapper.py 2026 --resolution 15 60
```

Pentru anul curent, argumentul pentru an poate fi omis:

```bash
python3 opcom_scrapper.py
```

## Pornirea dashboardului

```bash
streamlit run streamlit_app.py
```

Aplicația este disponibilă implicit la [http://localhost:8501](http://localhost:8501).

Fișierele CSV generate sunt ignorate de Git. Ele pot fi regenerate oricând prin rularea scraperului.
