"""
Two-phase horizontal separator process sizing.

All inputs in SI-consistent units unless noted (mm for geometry, m³/h for flows).
No Streamlit dependency — pure calculation functions only.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _cyl_vol_mm3(Di_mm: float, L_mm: float, h_mm: float) -> float:
    """Volume of a horizontal cylinder filled to height h (all in mm, result in mm³)."""
    R = Di_mm / 2.0
    h = max(0.0, min(Di_mm, h_mm))
    cos_arg = max(-1.0, min(1.0, (R - h) / R))
    return L_mm * (R**2 * math.acos(cos_arg) - (R - h) * math.sqrt(max(0.0, 2*R*h - h**2)))


def _cyl_area_m2(Di_mm: float, h_mm: float) -> float:
    """Cross-sectional area of liquid in a horizontal cylinder at fill height h (m²)."""
    R = Di_mm / 2.0
    h = max(0.0, min(Di_mm, h_mm))
    cos_arg = max(-1.0, min(1.0, (R - h) / R))
    area_mm2 = R**2 * math.acos(cos_arg) - (R - h) * math.sqrt(max(0.0, 2*R*h - h**2))
    return area_mm2 * 1e-6  # mm² → m²


# ── Drag-corrected cut-size calculations ─────────────────────────────────────
#
# The horizontal-settler criterion (API 12J / GPSA) requires that a
# droplet/bubble reaches the gas-liquid interface before the horizontal flow
# carries it to the outlet:
#
#   v_t_required = Q_flow × H_settle / (A_cross × L_eff)
#
# We then invert v_t → d using the appropriate drag regime:
#   Stokes      (Re ≤ 0.1):  v_t = d² Δρ g / (18 μ_c)
#   Intermediate (0.1–1000): Schiller-Naumann:
#                             C_D = 24/Re × (1 + 0.15 Re^0.687)
#                             solved iteratively from the Stokes seed
#   Newton       (Re > 1000): C_D ≈ 0.44
#                             v_t = d × √(4 Δρ g / (3 × 0.44 × ρ_c))
#
# Re is based on the continuous-phase properties.

_g = 9.81  # m/s²


def _d_from_vt(v_t_req: float, delta_rho: float,
               mu_c: float, rho_c: float) -> float:
    """
    Return particle/bubble diameter (m) whose terminal velocity equals v_t_req.

    Uses Stokes as a starting estimate, then applies Schiller-Naumann drag
    correction iteratively until converged or the Newton regime is detected.
    Returns 0 for degenerate inputs.
    """
    if v_t_req <= 0 or delta_rho <= 0 or mu_c <= 0 or rho_c <= 0:
        return 0.0

    # Stokes seed
    d = math.sqrt(18.0 * mu_c * v_t_req / (delta_rho * _g))

    for _ in range(20):
        Re = rho_c * v_t_req * d / mu_c
        if Re <= 0.1:
            break  # Stokes is valid
        if Re > 1000:
            # Newton regime: C_D = 0.44
            d = v_t_req / math.sqrt(4.0 * delta_rho * _g / (3.0 * 0.44 * rho_c))
            break
        # Schiller-Naumann: f = drag factor relative to Stokes
        f = 1.0 + 0.15 * Re ** 0.687
        d_new = math.sqrt(18.0 * mu_c * f * v_t_req / (delta_rho * _g))
        if abs(d_new - d) < d * 1e-4:
            d = d_new
            break
        d = d_new

    return max(0.0, d)


def cut_size_gas_um(
    mu_gas_Pas: float,
    Q_gas_m3h: float,
    A_gas_m2: float,
    h_gas_m: float,
    rho_liq_kgm3: float,
    rho_gas_kgm3: float,
    L_eff_m: float,
) -> float:
    """
    Minimum liquid-droplet diameter (μm) that settles from the gas phase.

    The required settling velocity (horizontal settler):
        v_t = v_gas × H_gas / L_eff   where  v_gas = Q_gas / A_gas

    Drag regime is determined automatically (Stokes → Schiller-Naumann → Newton).
    Continuous phase for Re: gas (ρ_gas, μ_gas).
    Returns 0 for degenerate inputs.
    """
    delta_rho = max(0.0, rho_liq_kgm3 - rho_gas_kgm3)
    if delta_rho <= 0 or A_gas_m2 <= 0 or L_eff_m <= 0:
        return 0.0
    v_gas   = (Q_gas_m3h / 3600.0) / A_gas_m2
    v_t_req = v_gas * h_gas_m / max(L_eff_m, 1e-9)
    return _d_from_vt(v_t_req, delta_rho, mu_gas_Pas, rho_gas_kgm3) * 1e6


def cut_size_liq_um(
    mu_liq_Pas: float,
    Q_liq_m3h: float,
    A_liq_m2: float,
    h_liq_m: float,
    rho_liq_kgm3: float,
    rho_gas_kgm3: float,
    L_eff_m: float,
) -> float:
    """
    Minimum gas-bubble diameter (μm) that rises clear of the liquid phase.

    The required rise velocity (horizontal settler):
        v_t = v_liq × H_liq / L_eff   where  v_liq = Q_liq / A_liq

    Drag regime determined automatically; continuous phase is liquid.
    For n symmetric inlets v_liq and L_eff scale equally → result is
    independent of inlet count.
    Returns 0 for degenerate inputs.
    """
    delta_rho = max(0.0, rho_liq_kgm3 - rho_gas_kgm3)
    if delta_rho <= 0 or A_liq_m2 <= 0 or L_eff_m <= 0:
        return 0.0
    v_liq   = (Q_liq_m3h / 3600.0) / A_liq_m2
    v_t_req = v_liq * h_liq_m / max(L_eff_m, 1e-9)
    return _d_from_vt(v_t_req, delta_rho, mu_liq_Pas, rho_liq_kgm3) * 1e6


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class SeparatorProcessResult:
    # ── Gas side ──────────────────────────────────────────────────────────────
    A_gas_m2: float
    U_act_ms: float        # superficial gas velocity per inlet zone (Q_gas/n_inlets / A_gas)
    U_max_ms: float
    gas_velocity_ok: bool
    t_gas_s: float
    V_gas_eff_m3: float
    Q_gas_per_inlet_m3h: float   # gas flow per inlet nozzle (= Q_gas / n_inlets)

    # ── Liquid side (effective zone, between baffles) ─────────────────────────
    V_liq_eff_m3: float
    V_surge_eff_m3: float
    t_holdup_s: float
    t_surge_s: float
    holdup_ok: bool
    surge_ok: bool

    # ── Cut sizes (Stokes) ────────────────────────────────────────────────────
    d_cut_gas_um: float    # liquid droplet carryover — minimum size separated
    d_cut_liq_um: float    # gas bubble carryunder — minimum size separated

    # ── Full-vessel liquid inventory (incl. heads) ────────────────────────────
    V_total_at_nll_m3: float
    V_total_at_lahh_m3: float
    V_total_vessel_m3: float

    # ── Geometry & slenderness ────────────────────────────────────────────────
    L_eff_mm: float
    nll_mm: float
    lahh_mm: float
    gas_space_height_mm: float
    LD_ratio: float          # L_shell / Di  — API 12J recommends 3–5
    LD_eff: float            # L_eff / Di    — effective separation zone
    nll_frac: float          # NLL / Di      — fill fraction at NLL (target ~0.5)

    # ── Inlet count (informational) ───────────────────────────────────────────
    n_inlets: int = 1


# ── Main calculation ──────────────────────────────────────────────────────────

def separator_check(
    Di_mm: float,
    L_shell_mm: float,
    nll_mm: float,
    lahh_mm: float,
    L_baffle_mm: float,
    Q_gas_m3h: float,
    Q_liq_m3h: float,
    rho_gas_kgm3: float,
    rho_liq_kgm3: float,
    K_sb: float,
    t_holdup_req_min: float,
    t_surge_req_min: float,
    mu_gas_Pas: float = 1.8e-5,
    mu_liq_Pas: float = 1.0e-3,
    n_inlets: int = 1,
    V_total_at_nll_m3: float = 0.0,
    V_total_at_lahh_m3: float = 0.0,
    V_total_vessel_m3: float = 0.0,
) -> SeparatorProcessResult:
    """
    Screen a horizontal two-phase separator.

    Effective separation zone = cylindrical shell between the inlet baffles.
    Head volumes excluded from hold-up/surge; reported separately for inventory.
    Flow rates are actual volumetric rates at operating conditions (m³/h).

    Cut sizes use the Stokes horizontal-settler formula and are independent of
    the number of symmetric inlets (n_inlets cancels in the formula).
    """
    R = Di_mm / 2.0
    L_eff_mm = max(0.0, L_shell_mm - 2.0 * L_baffle_mm)
    L_eff_m  = L_eff_mm * 1e-3

    Q_gas_m3s = Q_gas_m3h / 3600.0
    Q_liq_m3s = Q_liq_m3h / 3600.0

    # Cross-sections at NLL
    A_total_m2 = math.pi * (R * 1e-3) ** 2
    A_liq_m2   = _cyl_area_m2(Di_mm, nll_mm)
    A_gas_m2   = max(1e-9, A_total_m2 - A_liq_m2)

    # Souders-Brown — velocity check uses the LOCAL gas velocity in each inlet zone.
    # With n symmetric inlets the vessel splits into n parallel zones; each zone
    # carries Q_gas/n through the full cross-section A_gas.
    # The gas outlet and mesh pad see the full Q_gas, but the body velocity that
    # drives entrainment is Q_gas/n_inlets / A_gas.
    n_in      = max(n_inlets, 1)
    Q_gas_per_inlet_m3h = Q_gas_m3h / n_in
    Q_gas_per_inlet_m3s = Q_gas_m3s / n_in
    delta_rho = max(0.0, rho_liq_kgm3 - rho_gas_kgm3)
    U_max_ms  = K_sb * math.sqrt(delta_rho / max(rho_gas_kgm3, 0.001))
    U_act_ms  = Q_gas_per_inlet_m3s / A_gas_m2 if A_gas_m2 > 0 else float("inf")
    gas_ok    = U_act_ms <= U_max_ms

    # Effective zone volumes
    V_liq_eff_m3   = _cyl_vol_mm3(Di_mm, L_eff_mm, nll_mm)  * 1e-9
    V_lahh_eff_m3  = _cyl_vol_mm3(Di_mm, L_eff_mm, lahh_mm) * 1e-9
    V_surge_eff_m3 = max(0.0, V_lahh_eff_m3 - V_liq_eff_m3)
    V_full_cyl_m3  = math.pi * (R * 1e-3) ** 2 * L_eff_m
    V_gas_eff_m3   = max(0.0, V_full_cyl_m3 - V_liq_eff_m3)

    # Residence times
    t_holdup_s = V_liq_eff_m3   / max(Q_liq_m3s, 1e-12)
    t_surge_s  = V_surge_eff_m3 / max(Q_liq_m3s, 1e-12)
    t_gas_s    = V_gas_eff_m3   / max(Q_gas_m3s, 1e-12)

    holdup_ok = t_holdup_s >= t_holdup_req_min * 60.0
    surge_ok  = t_surge_s  >= t_surge_req_min  * 60.0

    # Cut sizes (Stokes)
    h_gas_m = max(0.0, Di_mm - nll_mm) * 1e-3
    h_liq_m = max(0.0, nll_mm)         * 1e-3

    d_cut_gas = cut_size_gas_um(
        mu_gas_Pas, Q_gas_m3h, A_gas_m2,
        h_gas_m, rho_liq_kgm3, rho_gas_kgm3, L_eff_m,
    )
    d_cut_liq = cut_size_liq_um(
        mu_liq_Pas, Q_liq_m3h, A_liq_m2,
        h_liq_m, rho_liq_kgm3, rho_gas_kgm3, L_eff_m,
    )

    return SeparatorProcessResult(
        A_gas_m2           = A_gas_m2,
        U_act_ms           = U_act_ms,
        U_max_ms           = U_max_ms,
        gas_velocity_ok    = gas_ok,
        t_gas_s            = t_gas_s,
        V_gas_eff_m3       = V_gas_eff_m3,
        Q_gas_per_inlet_m3h = Q_gas_per_inlet_m3h,
        V_liq_eff_m3       = V_liq_eff_m3,
        V_surge_eff_m3     = V_surge_eff_m3,
        t_holdup_s         = t_holdup_s,
        t_surge_s          = t_surge_s,
        holdup_ok          = holdup_ok,
        surge_ok           = surge_ok,
        d_cut_gas_um       = d_cut_gas,
        d_cut_liq_um       = d_cut_liq,
        V_total_at_nll_m3  = V_total_at_nll_m3,
        V_total_at_lahh_m3 = V_total_at_lahh_m3,
        V_total_vessel_m3  = V_total_vessel_m3,
        L_eff_mm           = L_eff_mm,
        nll_mm             = nll_mm,
        lahh_mm            = lahh_mm,
        gas_space_height_mm = Di_mm - nll_mm,
        LD_ratio           = L_shell_mm / max(Di_mm, 1.0),
        LD_eff             = L_eff_mm   / max(Di_mm, 1.0),
        nll_frac           = nll_mm     / max(Di_mm, 1.0),
        n_inlets           = n_inlets,
    )
