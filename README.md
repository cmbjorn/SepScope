# SepScope

SepScope is a Streamlit-based screening tool for horizontal two-phase separators, aimed at
process engineers working at inquiry and FEED stage. Given vessel geometry, operating
conditions, and fluid properties, it performs API 12J separator sizing, EN 13445-3 or
ASME VIII Div.1 mechanical design, full nozzle schedule with reinforcement checks, inlet
device sizing, liquid level analysis, and weight estimation. Results are delivered as a
downloadable HTML datasheet (structured to API 12J Annex E, print to PDF) and a Word
(.docx) design report. SepScope is a screening-level tool — it is **not** a certified
pressure vessel calculation.

## Features

- API 12J separator sizing: L/D optimisation, gas velocity (K factor), hold-up/surge
  times, and NLL fraction
- Turndown analysis with re-entrainment bound (1.15 × K_max)
- K_sb service derating guidance per API 12J Table 2-2 / GPSA
- Shell and head thickness design to EN 13445-3 or ASME VIII Div.1
- Full nozzle schedule with area-replacement reinforcement checks and schedule upgrade
  recommendations
- Inlet device sizing: half-pipe diverter and slotted/perforated cylinder (API 12J §5.3)
- Endcap nozzle analysis with face-on SVG drawings and alternative head comparison
- LDV (Liquid Design Volume) with two-segment pass/fail
- Internal mechanical loads from LDV startup surge
- Weight estimate (dry / operating / hydro test) with component breakdown
- Liquid levels (LZLL → LZHH) with accurate volumes including head geometry
- Gas and liquid outlet nozzle ρv² checks (API RP 14E)
- Instrument nozzle auto-population
- HTML datasheet (print to PDF) and Word (.docx) design report

## Prerequisites

- Python 3.11 or later
- pip packages listed in `requirements.txt`:
  `streamlit`, `plotly`, `pandas`, `numpy`, `python-docx`, `openpyxl`

## Installation and running

```bash
git clone <repo>
cd VesselCalc
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Project structure

```
VesselCalc/
├── app.py              Streamlit UI and main calculation orchestration
├── report.py           HTML datasheet generator (API 12J Annex E structure)
├── word_report.py      Word (.docx) design report generator
├── engines/            Calculation modules:
│   ├── vessel_design         Shell and head thickness (EN 13445-3 / ASME VIII Div.1)
│   ├── separator_process     API 12J sizing, K factor, hold-up/surge, LDV
│   ├── nozzle_geometry       Nozzle OD/wall tables, schedule lookup
│   ├── nozzle_reinforcement  Area-replacement checks, schedule upgrade logic
│   ├── inlet_device          Half-pipe diverter and cylinder sizing (API 12J §5.3)
│   ├── vessel_volume         Vessel volume by segment including head geometry
│   └── weight                Dry / operating / hydro-test weight estimation
└── standards/          DN sizes, EN PN ratings, ASME Class pressure ratings
```

## Disclaimer

SepScope is a screening-level tool intended for inquiry and FEED scoping only. It is not a
certified pressure vessel calculation and does not replace detailed engineering. All results
must be verified by a qualified engineer before use in design, procurement, or construction.
