# SepScope

Screening-level scoping tool for horizontal two-phase separators, built for inquiry and FEED studies.

> **Not a certified design tool.** Results are suitable for scoping and preliminary engineering only.

## Features

- Shell and head thickness sizing (EN 13445 / ASME VIII Div. 1)
- Separator performance check (Souders–Brown gas capacity, liquid retention time)
- Internal loads: demister, inlet baffle, weir
- Nozzle sizing and reinforcement checks
- Level instrumentation layout (LZLL → LZHH)
- Vessel weight estimates (shell, heads, internals, liquid, tare)
- PDF and Word report generation
- Interactive vessel sketch with nozzle positions and dimension lines

## Stack

- [Streamlit](https://streamlit.io) — UI
- [Plotly](https://plotly.com/python/) — vessel sketch
- [python-docx](https://python-docx.readthedocs.io) — Word report export

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment

Deploy on [Streamlit Community Cloud](https://streamlit.io/cloud) by pointing it at `app.py` on the `main` branch.

## Disclaimer

SepScope is a **screening and scoping tool** intended for use during inquiry and FEED phases only. Results have not been verified against any certified design methodology and must not be used as the basis for detailed engineering, procurement, fabrication, or construction. All outputs must be independently reviewed and validated by a qualified engineer before any engineering decisions are made. The authors accept no liability for any loss or damage arising from use of this software.

## License

MIT — see [LICENSE](LICENSE).
