"""
Mechanical loads on separator internals — LDV startup surge scenario.

Governing load case: the LDV inventory (seg_a + seg_b) floods into the vessel in
t_flood seconds (default 30 s), split equally across n_inlets. This represents
the startup slug / surge event. Both the inlet device impact force and the baffle
differential pressure are calculated from this same scenario using pure liquid density.

Engineering basis (first principles):
  Inlet device : momentum flux  F = ρ_liq × v² × A_nozzle
  Baffle ΔP    : perforated plate  ΔP = (1/Cd²) × (ρ_liq/2) × v_hole²   Cd = 0.61
  Plate t      : clamped circular plate under uniform pressure  t = R × √(3q / 4f_d)
  Weld sizing  : τ_allow = 0.4 × f_y  (EN 1993-1-8 / AWS D1.1)

Safety factors applied:
  SF = 3.0 for inlet device  (impulsive / dynamic amplification, repeated slugs)
  SF = 2.0 for baffle        (quasi-static, sustained 30 s, measurement uncertainty)

No standard prescribes this method for separator internals. API 12J requires
"adequate support" prescriptively; ASME UG-22(j) / EN 13445-3 require fluid
impact loads to be considered but give no calculation method.
"""
from __future__ import annotations
import math as _m

_CD = 0.61       # sharp-edged hole discharge coefficient
_SF_INLET  = 3.0 # dynamic safety factor — inlet device
_SF_BAFFLE = 2.0 # quasi-static safety factor — baffle
_API12J_T_MIN_MM = 6.0   # API 12J minimum baffle plate thickness


def _nozzle_bore(dn: int, pn: int, code_key: str) -> tuple[float, float, float]:
    """Return (OD_mm, ID_mm, A_m2) for the given nozzle DN and PN."""
    from engines.nozzle_geometry import (
        NOZZLE_OD, NOZZLE_WALL_T, NOZZLE_WALL_SCH, recommended_schedule,
    )
    OD  = NOZZLE_OD.get(dn, dn * 1.05)
    rec = recommended_schedule(pn, code_key)
    t   = float(NOZZLE_WALL_SCH[rec].get(dn, NOZZLE_WALL_T.get(dn, 8.0)))
    ID  = max(OD - 2.0 * t, 1.0)
    A   = _m.pi * (ID * 1e-3) ** 2 / 4.0
    return OD, ID, A


def internal_loads(
    Di_mm: float,
    rho_liq: float,           # kg/m³
    rho_gas: float,           # kg/m³ — for reference gas ΔP only
    n_inlets: int,
    nozzle_dn: int,
    nozzle_pn: int,
    code_key: str,
    baffle_open_pct: float,   # % open area of baffle
    U_act_ms: float,          # superficial gas velocity (from sep_res) — reference only
    seg_a_m3: float,          # LDV segment A volume (VB → LZLL)
    seg_b_m3: float,          # LDV segment B volume (LZLL → LALL)
    fd_MPa: float,            # vessel material allowable stress at design T
    fy_MPa: float,            # vessel material yield strength at 20 °C (Rp0.2)
    t_flood_s: float = 30.0,  # LDV flood time (s) — default 30 s per design basis
) -> dict:
    """
    Calculate mechanical loads on the inlet device and baffle plate.

    Both loads use the LDV startup surge: V_ldv = seg_a + seg_b floods in t_flood s.

    Returns a dict with all intermediate and final values.
    """
    n  = max(n_inlets, 1)
    tf = max(t_flood_s, 1.0)

    # ── LDV surge flow rate per inlet ────────────────────────────────────────
    V_ldv_m3            = seg_a_m3 + seg_b_m3
    Q_ldv_per_inlet_m3s = V_ldv_m3 / tf / n

    # ── Nozzle bore ──────────────────────────────────────────────────────────
    nz_od_mm, nz_id_mm, A_nozzle_m2 = _nozzle_bore(nozzle_dn, nozzle_pn, code_key)

    # ── Inlet device: momentum flux F = ρ_liq × v_ldv² × A ──────────────────
    v_ldv_ms    = Q_ldv_per_inlet_m3s / max(A_nozzle_m2, 1e-9)
    F_impact_N  = rho_liq * v_ldv_ms ** 2 * A_nozzle_m2
    F_inlet_design_N = _SF_INLET * F_impact_N

    # ── Baffle geometry ──────────────────────────────────────────────────────
    phi         = max(baffle_open_pct / 100.0, 1e-3)
    A_baffle_m2 = _m.pi * (Di_mm * 1e-3) ** 2 / 4.0
    R_m         = Di_mm * 1e-3 / 2.0

    # ── Baffle: LDV surge ΔP — liquid through perforations ──────────────────
    v_hole_ldv_ms = Q_ldv_per_inlet_m3s / max(A_baffle_m2 * phi, 1e-9)
    dP_surge_Pa   = (1.0 / _CD ** 2) * (rho_liq / 2.0) * v_hole_ldv_ms ** 2
    F_baffle_surge_N = dP_surge_Pa * A_baffle_m2

    # ── Baffle: gas operating ΔP (reference — governs in no liquid scenario) ─
    v_hole_gas_ms  = U_act_ms / max(phi, 1e-9)
    dP_gas_op_Pa   = (1.0 / _CD ** 2) * (rho_gas / 2.0) * v_hole_gas_ms ** 2
    F_baffle_gas_N = dP_gas_op_Pa * A_baffle_m2

    # ── Governing baffle design force ────────────────────────────────────────
    F_baffle_design_N = _SF_BAFFLE * F_baffle_surge_N

    # ── Baffle plate thickness: clamped circular plate ───────────────────────
    f_d_Pa     = fd_MPa * 1e6
    q_design   = F_baffle_design_N / max(A_baffle_m2, 1e-9)   # uniform design pressure [Pa]
    t_min_mm   = R_m * _m.sqrt(max(3.0 * q_design / (4.0 * f_d_Pa), 0.0)) * 1000.0
    t_design_mm = max(t_min_mm, _API12J_T_MIN_MM)

    # ── Baffle fillet weld: τ_allow = 0.4 × f_y (EN 1993-1-8 / AWS D1.1) ───
    L_weld_m      = _m.pi * Di_mm * 1e-3
    f_y_Pa        = fy_MPa * 1e6
    tau_allow_Pa  = 0.4 * f_y_Pa
    a_weld_req_mm = F_baffle_design_N / max(L_weld_m * tau_allow_Pa, 1e-9) * 1000.0
    a_weld_design_mm = max(a_weld_req_mm, 3.0)   # 3 mm practical minimum

    return {
        # LDV surge scenario
        "V_ldv_m3":              V_ldv_m3,
        "Q_ldv_per_inlet_m3s":   Q_ldv_per_inlet_m3s,
        "t_flood_s":             t_flood_s,
        "n_inlets":              n,
        # Nozzle
        "nozzle_dn":             nozzle_dn,
        "nz_od_mm":              nz_od_mm,
        "nz_id_mm":              nz_id_mm,
        "A_nozzle_m2":           A_nozzle_m2,
        # Inlet device
        "v_ldv_ms":              v_ldv_ms,
        "F_impact_N":            F_impact_N,
        "SF_inlet":              _SF_INLET,
        "F_inlet_design_N":      F_inlet_design_N,
        # Baffle
        "phi":                   phi,
        "A_baffle_m2":           A_baffle_m2,
        "v_hole_ldv_ms":         v_hole_ldv_ms,
        "dP_surge_Pa":           dP_surge_Pa,
        "F_baffle_surge_N":      F_baffle_surge_N,
        "v_hole_gas_ms":         v_hole_gas_ms,
        "dP_gas_op_Pa":          dP_gas_op_Pa,
        "F_baffle_gas_N":        F_baffle_gas_N,
        "SF_baffle":             _SF_BAFFLE,
        "F_baffle_design_N":     F_baffle_design_N,
        # Plate sizing
        "q_design_Pa":           q_design,
        "t_baffle_min_mm":       t_min_mm,
        "t_baffle_design_mm":    t_design_mm,
        # Weld sizing
        "L_weld_m":              L_weld_m,
        "tau_allow_Pa":          tau_allow_Pa,
        "a_weld_req_mm":         a_weld_req_mm,
        "a_weld_design_mm":      a_weld_design_mm,
        "fd_MPa":                fd_MPa,
        "fy_MPa":                fy_MPa,
    }
