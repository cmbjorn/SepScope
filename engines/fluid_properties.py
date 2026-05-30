"""
Fluid property lookup tables for separator process screening.

Uses ideal gas law for gas density; tabulated data for viscosity (gas)
and density + viscosity (liquid). No heavy third-party packages required.
All property functions accept operating P (barg) and T (°C) directly.
"""
from __future__ import annotations
import math
from dataclasses import dataclass


# ── Internal interpolation helper ────────────────────────────────────────────

def _interp1(xs: list[float], ys: list[float], x: float) -> float:
    """Linear interpolation; clamps to boundary values outside range."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return ys[-1]


def _interp2(xs: list[float], ys: list[float],
             table: list[list[float]], x: float, y: float) -> float:
    """
    Bilinear interpolation on a regular grid.
    xs  — outer axis (e.g. concentration %)
    ys  — inner axis (e.g. temperature °C)
    table[i][j] — value at (xs[i], ys[j])
    """
    # clamp
    x = max(xs[0], min(xs[-1], x))
    y = max(ys[0], min(ys[-1], y))

    # bracket x
    ix = 0
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            ix = i
            break
    tx = (x - xs[ix]) / (xs[ix + 1] - xs[ix]) if xs[ix + 1] != xs[ix] else 0.0

    def row_interp(row_idx: int) -> float:
        return _interp1(ys, table[row_idx], y)

    v0 = row_interp(ix)
    v1 = row_interp(ix + 1)
    return v0 + tx * (v1 - v0)


# ── Gas tables ────────────────────────────────────────────────────────────────

_GAS_T_REF = [0.0, 25.0, 50.0, 100.0, 150.0, 200.0, 300.0, 400.0]  # °C

# Dynamic viscosity (μPa·s) at 1 atm — pressure has negligible effect below ~100 bar
_GAS_MU_TABLE: dict[str, list[float]] = {
    "H2":  [8.35,  8.93,  9.52, 10.53, 11.44, 12.26, 13.65, 14.82],
    "N2":  [16.6,  17.8,  19.0, 21.2,  23.1,  24.9,  28.1,  31.0],
    "Air": [17.1,  18.4,  19.6, 21.9,  24.1,  26.0,  29.6,  32.7],
    "O2":  [19.2,  20.6,  22.0, 24.5,  26.9,  29.1,  33.2,  36.9],
}

_GAS_MW: dict[str, float] = {
    "H2":  2.016,
    "N2":  28.014,
    "Air": 28.97,
    "O2":  31.999,
}

GAS_FLUIDS = ["H2", "N2", "Air", "O2", "Custom"]


# ── Liquid tables ─────────────────────────────────────────────────────────────

_LIQ_T_REF = [0.0, 20.0, 40.0, 60.0, 80.0, 100.0, 120.0, 150.0]  # °C

_WATER_RHO = [999.8, 998.2, 992.2, 983.2, 971.8, 958.4, 943.4, 916.8]  # kg/m³
_WATER_MU  = [1.793, 1.002, 0.653, 0.467, 0.355, 0.282, 0.232, 0.182]  # mPa·s

# KOH 30 wt% aqueous (extrapolate flat outside range)
_KOH30_T   = [20.0,  40.0,  60.0,  80.0, 100.0]
_KOH30_RHO = [1288., 1275., 1260., 1244., 1225.]
_KOH30_MU  = [3.50,  2.20,  1.50,  1.10,  0.85]

# Ethylene glycol aqueous — bilinear table
# Outer axis: EG concentration (wt%)
# Inner axis: temperature (°C)
_EG_CONC  = [0.,   20.,   30.,   40.,   50.,   60.,   70.,  100.]  # wt%
_EG_T_REF = [0.,   20.,   40.,   60.,   80.]  # °C

# Density (kg/m³)
_EG_RHO: list[list[float]] = [
    # 0 °C   20 °C   40 °C   60 °C   80 °C
    [999.8, 998.2, 992.2, 983.2, 971.8],   # 0 %
    [1030., 1028., 1022., 1013., 1001.],    # 20 %
    [1047., 1044., 1037., 1027., 1014.],    # 30 %
    [1063., 1059., 1051., 1040., 1027.],    # 40 %
    [1079., 1073., 1064., 1052., 1038.],    # 50 %
    [1094., 1087., 1077., 1064., 1049.],    # 60 %
    [1109., 1100., 1089., 1075., 1059.],    # 70 %
    [1130., 1113., 1097., 1080., 1062.],    # 100 %
]

# Dynamic viscosity (mPa·s)
_EG_MU: list[list[float]] = [
    # 0 °C   20 °C   40 °C   60 °C   80 °C
    [1.793, 1.002, 0.653, 0.467, 0.355],   # 0 %
    [3.40,  1.90,  1.17,  0.80,  0.58],    # 20 %
    [5.30,  3.00,  1.79,  1.19,  0.85],    # 30 %
    [8.60,  4.95,  2.85,  1.84,  1.26],    # 40 %
    [15.2,  8.70,  4.75,  2.95,  1.95],    # 50 %
    [30.5,  16.8,  8.65,  5.08,  3.20],    # 60 %
    [70.0,  37.5,  17.8,  9.50,  5.65],    # 70 %
    [340.,  21.0 * 5, 21.0 * 2, 21.0, 10.0],  # 100 % EG (approx)
]

LIQ_FLUIDS = ["Water", "KOH 30wt%", "Glycol (EG)", "Custom"]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class FluidProps:
    label: str          # human-readable summary
    rho_kgm3: float
    mu_Pas: float       # dynamic viscosity in Pa·s
    MW: float | None    # molar mass g/mol — gas only, None for liquids


# ── Public API ────────────────────────────────────────────────────────────────

def ideal_gas_density(P_barg: float, T_C: float, MW: float,
                      Z: float = 1.0) -> float:
    """Gas density (kg/m³) from ideal gas law at operating P and T."""
    P_abs = (P_barg + 1.01325) * 1e5   # Pa
    T_K   = T_C + 273.15
    R_gas = 8314.46                     # J/(kmol·K)
    return (MW * P_abs) / (Z * R_gas * T_K)


def gas_properties(
    fluid: str,
    T_C: float,
    P_barg: float,
    MW_custom: float = 28.0,
    mu_custom_uPas: float = 18.0,
    Z: float = 1.0,
) -> FluidProps:
    """
    Return density and viscosity for a gas at operating conditions.
    fluid: one of "H2", "N2", "Air", "Custom"
    """
    if fluid == "Custom":
        MW  = MW_custom
        mu_uPas = mu_custom_uPas
    else:
        MW  = _GAS_MW.get(fluid, 28.0)
        mu_uPas = _interp1(_GAS_T_REF, _GAS_MU_TABLE[fluid], T_C)

    rho = ideal_gas_density(P_barg, T_C, MW, Z)
    label = f"{fluid}  ρ={rho:.2f} kg/m³  μ={mu_uPas:.1f} μPa·s  MW={MW:.1f}"
    return FluidProps(label=label, rho_kgm3=rho,
                      mu_Pas=mu_uPas * 1e-6, MW=MW)


def liquid_properties(
    fluid: str,
    T_C: float,
    eg_conc_pct: float = 30.0,
    rho_custom: float = 1000.0,
    mu_custom_mPas: float = 1.0,
) -> FluidProps:
    """
    Return density and viscosity for a liquid at operating temperature.
    fluid: one of "Water", "KOH 30wt%", "Glycol (EG)", "Custom"
    eg_conc_pct: ethylene glycol concentration in wt% (only used for Glycol)
    """
    if fluid == "Water":
        rho = _interp1(_LIQ_T_REF, _WATER_RHO, T_C)
        mu_mPas = _interp1(_LIQ_T_REF, _WATER_MU, T_C)
        label = f"Water  ρ={rho:.0f} kg/m³  μ={mu_mPas:.3f} mPa·s"

    elif fluid == "KOH 30wt%":
        rho = _interp1(_KOH30_T, _KOH30_RHO, T_C)
        mu_mPas = _interp1(_KOH30_T, _KOH30_MU, T_C)
        label = f"KOH 30wt%  ρ={rho:.0f} kg/m³  μ={mu_mPas:.3f} mPa·s"

    elif fluid == "Glycol (EG)":
        rho = _interp2(_EG_CONC, _EG_T_REF, _EG_RHO, eg_conc_pct, T_C)
        mu_mPas = _interp2(_EG_CONC, _EG_T_REF, _EG_MU, eg_conc_pct, T_C)
        label = f"EG {eg_conc_pct:.0f}wt%  ρ={rho:.0f} kg/m³  μ={mu_mPas:.3f} mPa·s"

    else:  # Custom
        rho = rho_custom
        mu_mPas = mu_custom_mPas
        label = f"Custom  ρ={rho:.0f} kg/m³  μ={mu_mPas:.3f} mPa·s"

    return FluidProps(label=label, rho_kgm3=rho,
                      mu_Pas=mu_mPas * 1e-3, MW=None)
