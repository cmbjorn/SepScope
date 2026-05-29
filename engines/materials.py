"""
Pressure vessel material allowable stress tables.

Sources:
    ASME BPVC Section II Part D (2021) — Table 1A (ferrous), Table 1B (non-ferrous)
    EN 13445-3:2021 Annex B  — fd = min(Rp0.2/1.5, Rm/2.4) at temperature
    All stress values in MPa, temperatures in °C.
"""
from __future__ import annotations
import math

# ── Material database ────────────────────────────────────────────────────────
# Each entry:
#   "name"        : display name
#   "code"        : "ASME" | "EN" | "BOTH"
#   "spec"        : material specification string
#   "group"       : EN 13445 material group (for weld joint coefficient table)
#   "Rm"          : tensile strength at 20 °C (MPa)
#   "Rp02"        : 0.2% proof stress at 20 °C (MPa)
#   "rho"         : density (kg/m³)
#   "E_GPa"       : Young's modulus at 20 °C (GPa)
#   "allowable"   : list of (T_max_C, S_MPa) for ASME, or computed from EN formula
#   "Rm_T"        : list of (T_C, Rm_MPa) for EN temperature de-rating
#   "Rp02_T"      : list of (T_C, Rp02_MPa) for EN temperature de-rating

MATERIALS: dict[str, dict] = {
    # ── Carbon steel ─────────────────────────────────────────────────────────
    "SA-516-70": {
        "name": "SA-516 Gr.70  (Carbon steel pressure vessel plate)",
        "code": "ASME",
        "spec": "SA-516-70",
        "group": "1.1",
        "Rm": 485, "Rp02": 260, "rho": 7850, "E_GPa": 200,
        # ASME II-D Table 1A, Group B (SA-516-70)
        "allowable": [
            (-29, 138), (40, 138), (50, 138), (100, 138), (150, 138),
            (200, 138), (250, 131), (300, 124), (350, 117), (400, 110),
            (450, 102), (454, 101),
        ],
    },
    "SA-516-60": {
        "name": "SA-516 Gr.60  (Carbon steel pressure vessel plate)",
        "code": "ASME",
        "spec": "SA-516-60",
        "group": "1.1",
        "Rm": 415, "Rp02": 220, "rho": 7850, "E_GPa": 200,
        "allowable": [
            (-29, 118), (40, 118), (100, 118), (150, 118), (200, 118),
            (250, 112), (300, 107), (350, 101), (400, 95), (454, 88),
        ],
    },
    "P265GH": {
        "name": "P265GH  (EN 10028-2 carbon steel for pressure purposes)",
        "code": "EN",
        "spec": "P265GH",
        "group": "1.1",
        "Rm": 410, "Rp02": 265, "rho": 7850, "E_GPa": 200,
        "Rm_T":   [(20, 410), (100, 390), (150, 380), (200, 370), (250, 355),
                   (300, 340), (350, 325), (400, 310), (425, 295)],
        "Rp02_T": [(20, 265), (100, 240), (150, 225), (200, 215), (250, 205),
                   (300, 195), (350, 185), (400, 175), (425, 165)],
    },
    "P295GH": {
        "name": "P295GH  (EN 10028-2 carbon steel, higher strength)",
        "code": "EN",
        "spec": "P295GH",
        "group": "1.1",
        "Rm": 460, "Rp02": 295, "rho": 7850, "E_GPa": 200,
        "Rm_T":   [(20, 460), (100, 440), (150, 430), (200, 415), (250, 400),
                   (300, 385), (350, 370), (400, 355), (450, 335)],
        "Rp02_T": [(20, 295), (100, 270), (150, 255), (200, 240), (250, 230),
                   (300, 220), (350, 210), (400, 200), (450, 185)],
    },
    # ── Austenitic stainless steel ───────────────────────────────────────────
    "SA-240-316L": {
        "name": "SA-240 Type 316L  (Austenitic SS plate)",
        "code": "ASME",
        "spec": "SA-240-316L",
        "group": "8.1",
        "Rm": 485, "Rp02": 170, "rho": 8000, "E_GPa": 195,
        "allowable": [
            (-196, 115), (40, 115), (100, 110), (150, 106), (200, 101),
            (250, 96),  (300, 92),  (350, 89),  (400, 86),  (450, 84),
            (500, 82),  (550, 80),
        ],
    },
    "SA-240-304L": {
        "name": "SA-240 Type 304L  (Austenitic SS plate)",
        "code": "ASME",
        "spec": "SA-240-304L",
        "group": "8.1",
        "Rm": 485, "Rp02": 170, "rho": 8000, "E_GPa": 195,
        "allowable": [
            (-196, 115), (40, 115), (100, 108), (150, 103), (200, 98),
            (250, 93),  (300, 89),  (350, 86),  (400, 83),  (450, 81),
            (500, 80),
        ],
    },
    "X2CrNiMo17-12-2": {
        "name": "X2CrNiMo17-12-2 (1.4404 / 316L)  (EN 10028-7 austenitic SS)",
        "code": "EN",
        "spec": "X2CrNiMo17-12-2",
        "group": "8.1",
        "Rm": 485, "Rp02": 200, "rho": 8000, "E_GPa": 195,
        "Rm_T":   [(20, 485), (100, 465), (150, 450), (200, 440), (250, 430),
                   (300, 425), (350, 420), (400, 415), (450, 410), (500, 405)],
        "Rp02_T": [(20, 200), (100, 165), (150, 148), (200, 136), (250, 128),
                   (300, 123), (350, 119), (400, 116), (450, 113), (500, 111)],
    },
    "X2CrNi18-9": {
        "name": "X2CrNi18-9 (1.4307 / 304L)  (EN 10028-7 austenitic SS)",
        "code": "EN",
        "spec": "X2CrNi18-9",
        "group": "8.1",
        "Rm": 485, "Rp02": 195, "rho": 8000, "E_GPa": 195,
        "Rm_T":   [(20, 485), (100, 465), (150, 452), (200, 440), (250, 430),
                   (300, 420), (350, 415), (400, 410), (450, 408), (500, 405)],
        "Rp02_T": [(20, 195), (100, 160), (150, 143), (200, 130), (250, 122),
                   (300, 118), (350, 114), (400, 112), (450, 110), (500, 108)],
    },
    # ── Duplex stainless steel ───────────────────────────────────────────────
    "SA-240-2205": {
        "name": "SA-240 UNS S31803 / S32205  (Duplex 2205 plate)",
        "code": "ASME",
        "spec": "SA-240-S31803",
        "group": "10H",
        "Rm": 620, "Rp02": 450, "rho": 7800, "E_GPa": 200,
        "allowable": [
            (-46, 172), (40, 172), (100, 161), (150, 155), (200, 148),
            (250, 141), (300, 134), (315, 131),
        ],
    },
    "X2CrNiMoN22-5-3": {
        "name": "X2CrNiMoN22-5-3 (1.4462 / 2205)  (EN 10028-7 duplex SS)",
        "code": "EN",
        "spec": "X2CrNiMoN22-5-3",
        "group": "10H",
        "Rm": 620, "Rp02": 450, "rho": 7800, "E_GPa": 200,
        "Rm_T":   [(20, 620), (50, 610), (100, 590), (150, 570),
                   (200, 555), (250, 540), (300, 520), (315, 510)],
        "Rp02_T": [(20, 450), (50, 435), (100, 415), (150, 400),
                   (200, 390), (250, 380), (300, 370), (315, 365)],
    },
}


def _interp(table: list[tuple[float, float]], T: float) -> float:
    """Linear interpolation on a (T, value) table; clamps at limits."""
    if T <= table[0][0]:
        return table[0][1]
    if T >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        t0, v0 = table[i]
        t1, v1 = table[i + 1]
        if t0 <= T <= t1:
            return v0 + (v1 - v0) * (T - t0) / (t1 - t0)
    return table[-1][1]


def allowable_stress(mat_key: str, T_C: float, code: str) -> dict:
    """
    Return the allowable stress for a material at design temperature.

    Parameters
    ----------
    mat_key : key in MATERIALS dict
    T_C     : design temperature (°C)
    code    : "ASME" or "EN"

    Returns
    -------
    dict with keys:
        fd_MPa   : allowable design stress (MPa)
        basis    : short description of how fd was derived
        warnings : list of warning strings
    """
    mat = MATERIALS[mat_key]
    warnings = []

    if code == "ASME":
        tbl = mat.get("allowable")
        if tbl is None:
            # Fall back to EN formula if no ASME table
            code = "EN"
        else:
            fd = _interp(tbl, T_C)
            if T_C > tbl[-1][0]:
                warnings.append(
                    f"Temperature {T_C:.0f} °C exceeds tabulated range "
                    f"({tbl[-1][0]:.0f} °C). Value extrapolated — verify.")
            return {"fd_MPa": fd, "basis": f"ASME II-D Table 1A interpolated at {T_C:.0f} °C",
                    "warnings": warnings}

    # EN 13445-3 Annex B: fd = min(Rp0.2_T / 1.5,  Rm_T / 2.4)
    Rm_T   = mat.get("Rm_T",   [(20, mat["Rm"])])
    Rp02_T = mat.get("Rp02_T", [(20, mat["Rp02"])])
    Rm  = _interp(Rm_T, T_C)
    Rp  = _interp(Rp02_T, T_C)
    fd  = min(Rp / 1.5, Rm / 2.4)
    if T_C > Rm_T[-1][0]:
        warnings.append(
            f"Temperature {T_C:.0f} °C exceeds tabulated range "
            f"({Rm_T[-1][0]:.0f} °C). Value extrapolated — verify.")
    basis = (f"EN 13445 fd = min(Rp0.2/1.5, Rm/2.4) = "
             f"min({Rp:.1f}/1.5, {Rm:.1f}/2.4) = min({Rp/1.5:.1f}, {Rm/2.4:.1f}) "
             f"= {fd:.1f} MPa  at {T_C:.0f} °C")
    return {"fd_MPa": round(fd, 2), "basis": basis, "warnings": warnings}
