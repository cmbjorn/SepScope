"""
Piping and flange standards for VesselCalc.

Sources:
  EN 1092-1:2018  Flanges PN designation (pressures in barg at 20 °C)
  ASME B16.5-2017 Flanges Class designation
  ASME B36.10M   Pipe OD and wall schedules
  ISO 4200        Plain end steel tubes

All dimensions in mm, pressures in barg.
"""
from __future__ import annotations

# EN 1092-1 PN ratings (barg at 20 °C / ambient)
# Used for nozzle flange class selection
EN_PN_RATINGS: list[int] = [2.5, 6, 10, 16, 25, 40, 63, 100, 160, 250, 320, 400]

# ASME B16.5 pressure classes (psi) and approximate max pressure in barg at 20 °C, Group 1.1
ASME_CLASS_PRESSURE_20C: dict[str, float] = {
    "150": 19.6,
    "300": 51.1,
    "600": 102.1,
    "900": 153.2,
    "1500": 255.3,
    "2500": 425.5,
}

# Nozzle pipe OD (mm) by DN — ISO 4200 / ASME B36.10M
# Used by nozzle_geometry.py (also kept here for UI lookups)
NOZZLE_OD: dict[int, float] = {
    15: 21.3,  20: 26.9,  25: 33.7,  32: 42.4,  40: 48.3,
    50: 60.3,  65: 76.1,  80: 88.9, 100: 114.3, 125: 139.7,
    150: 168.3, 200: 219.1, 250: 273.1, 300: 323.9,
    350: 355.6, 400: 406.4, 450: 457.0, 500: 508.0,
    600: 609.6, 700: 711.0, 800: 812.8,
}

# Nozzle wall thickness by DN — schedule 40 / standard wall (mm)
NOZZLE_WALL_SCH40: dict[int, float] = {
    15: 2.8,  20: 2.9,  25: 3.4,  32: 3.6,  40: 3.7,
    50: 3.9,  65: 5.2,  80: 5.5, 100: 6.0, 125: 6.6,
    150: 7.1, 200: 8.2, 250: 9.3, 300: 9.5,
    350: 9.5, 400: 9.5, 450: 9.5, 500: 9.5,
    600: 9.5, 700: 11.1, 800: 12.7,
}

# Schedule 80 / extra-heavy wall (mm)
NOZZLE_WALL_SCH80: dict[int, float] = {
    15: 3.7,  20: 3.9,  25: 4.5,  32: 4.9,  40: 5.1,
    50: 5.5,  65: 7.0,  80: 7.6, 100: 8.6, 125: 9.5,
    150: 11.0, 200: 12.7, 250: 15.1, 300: 17.4,
    350: 19.0, 400: 21.4, 450: 23.8, 500: 25.4,
    600: 28.6, 700: 31.8, 800: 34.9,
}

# Available DN sizes (nominal diameters) for the UI
DN_SIZES: list[int] = sorted(NOZZLE_OD.keys())

# Flange facing dimensions (mm) — raised-face OD and bolt-circle by DN/PN16
# Approximate per EN 1092-1 PN16 for reference; not used in calculations.
FLANGE_PN16_OD: dict[int, float] = {
    50: 165, 65: 185, 80: 200, 100: 220, 125: 250,
    150: 285, 200: 340, 250: 400, 300: 455, 350: 520,
    400: 580, 500: 715, 600: 840,
}


def max_pn_for_temperature(pn: float, T_C: float, material_group: str = "1.1") -> float:
    """
    Derate EN 1092-1 PN flange pressure limit for temperature.
    Simplified: linear derating above 50 °C based on EN 1092-1 Annex B (Group 1.1 carbon steel).
    Returns allowable pressure in barg.
    """
    # PN at 20 °C is the rated value.
    # Approximate derating factors for Group 1.1 (carbon steel):
    _derate = {
        50: 1.00, 100: 0.96, 150: 0.92, 200: 0.85,
        250: 0.79, 300: 0.72, 350: 0.65, 400: 0.55,
    }
    if T_C <= 50:
        return pn
    temps = sorted(_derate.keys())
    if T_C >= temps[-1]:
        factor = _derate[temps[-1]]
    else:
        for i in range(len(temps) - 1):
            t0, t1 = temps[i], temps[i + 1]
            if t0 <= T_C <= t1:
                f0, f1 = _derate[t0], _derate[t1]
                factor = f0 + (f1 - f0) * (T_C - t0) / (t1 - t0)
                break
        else:
            factor = _derate[temps[0]]
    return round(pn * factor, 1)
