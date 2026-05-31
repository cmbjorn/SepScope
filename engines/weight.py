"""
Vessel weight estimation — dry, operating and hydrotest.

Dry weight components:
  Shell        : cylindrical shell wall (exact thin-shell formula)
  Heads (×2)   : surface area × t_head (per head type)
  Nozzles      : pipe stub (300 mm projection) + weld-neck flange per nozzle
  Saddles (×2) : plate-area estimate from Di and saddle width
  Internals    : baffles, mesh pad, inlet devices, vortex breaker
  Misc (+5 %)  : welds, paint, clips, reinforcement pads

Operating weight : dry + liquid inventory at NLL (full vessel including heads)
Hydrotest weight : dry + water fill to 100 % vessel capacity

All lengths / diameters in mm.  Masses in kg.
"""
from __future__ import annotations
import math as _m

# ── Weld-neck flange mass lookup (kg) ────────────────────────────────────────
# One flange per nozzle (vessel-side only).  Approximate values based on
# ASME B16.5 / EN 1092-1 carbon-steel weld-neck flanges.
# Format: {dn: {pn_class: mass_kg}}
_FLANGE_KG: dict[int, dict[int, float]] = {
     15: {10: 0.3,  16: 0.4,  25: 0.5,  40: 0.6,   63: 0.8,  100: 1.2},
     20: {10: 0.4,  16: 0.5,  25: 0.6,  40: 0.8,   63: 1.0,  100: 1.5},
     25: {10: 0.5,  16: 0.6,  25: 0.8,  40: 1.0,   63: 1.3,  100: 2.0},
     32: {10: 0.7,  16: 0.8,  25: 1.0,  40: 1.3,   63: 1.7,  100: 2.5},
     40: {10: 0.9,  16: 1.0,  25: 1.3,  40: 1.6,   63: 2.1,  100: 3.2},
     50: {10: 1.2,  16: 1.5,  25: 1.8,  40: 2.3,   63: 3.0,  100: 4.5},
     65: {10: 1.8,  16: 2.2,  25: 2.7,  40: 3.4,   63: 4.5,  100: 6.5},
     80: {10: 2.4,  16: 3.0,  25: 3.7,  40: 4.7,   63: 6.0,  100: 9.0},
    100: {10: 3.8,  16: 4.8,  25: 6.0,  40: 7.5,   63: 9.5,  100: 14.0},
    125: {10: 5.5,  16: 7.0,  25: 8.5,  40: 11.0,  63: 14.0, 100: 20.0},
    150: {10: 7.5,  16: 9.5,  25: 12.0, 40: 15.0,  63: 19.0, 100: 28.0},
    200: {10: 13.0, 16: 16.0, 25: 20.0, 40: 26.0,  63: 33.0, 100: 48.0},
    250: {10: 20.0, 16: 25.0, 25: 32.0, 40: 41.0,  63: 52.0, 100: 75.0},
    300: {10: 30.0, 16: 38.0, 25: 48.0, 40: 62.0,  63: 80.0, 100: 115.0},
    350: {10: 42.0, 16: 53.0, 25: 67.0, 40: 87.0,  63: 110.0,100: 160.0},
    400: {10: 56.0, 16: 72.0, 25: 90.0, 40: 117.0, 63: 148.0,100: 215.0},
    450: {10: 74.0, 16: 95.0, 25: 120.0,40: 156.0, 63: 195.0,100: 285.0},
    500: {10: 95.0, 16: 122.0,25: 155.0,40: 200.0, 63: 252.0,100: 365.0},
    600: {10: 145.0,16: 185.0,25: 235.0,40: 305.0, 63: 385.0,100: 560.0},
    700: {10: 210.0,16: 270.0,25: 340.0,40: 440.0, 63: 555.0,100: 810.0},
    800: {10: 290.0,16: 370.0,25: 470.0,40: 605.0, 63: 760.0,100: 1110.0},
}

_NOZZLE_STUB_MM = 300.0   # standard projection: face of flange to vessel OD
_MISC_FACTOR    = 0.05    # 5 % allowance: welds, paint, clips, reinf. pads

# Approximate PN-class conversion (just need a nearby key for lookup)
def _pn_key(pn: int) -> int:
    for k in (10, 16, 25, 40, 63, 100):
        if pn <= k:
            return k
    return 100


def _head_surface_area_mm2(
    Di_mm: float,
    head_type_str: str,
    crown_ratio: float = 1.0,
    knuckle_ratio: float = 0.10,
    alpha_deg_cone: float = 30.0,
    ellipse_ratio: float = 2.0,
) -> float:
    """
    Approximate outer surface area of one head (inner face, mm²).
    Used with t_head to estimate head metal volume.
    """
    R = Di_mm / 2.0

    if head_type_str in ("Hemispherical",):
        return 2.0 * _m.pi * R ** 2

    elif head_type_str in ("Ellipsoidal 2:1",):
        a = R  # equatorial semi-axis
        c = R / ellipse_ratio  # polar semi-axis (e.g. Di/4 for 2:1)
        e = _m.sqrt(max(1.0 - (c / a) ** 2, 0.0))
        if e < 1e-6:  # sphere limit
            return 2.0 * _m.pi * a ** 2
        # Oblate spheroid one-cap surface area = half of total
        S_total = 2.0 * _m.pi * a ** 2 * (1.0 + (1.0 - e ** 2) / e * _m.atanh(e))
        return S_total / 2.0

    elif head_type_str in (
        "Torispherical (dished)",           # legacy label (report.py)
        "Torispherical (Klöpper / dished)", # current app.py label
        "Flanged & Dished (ASME F&D)",      # legacy label (report.py)
        "Flanged & Dished — ASME F&D",      # current app.py label
    ):
        R_c = crown_ratio * Di_mm
        r_k = knuckle_ratio * Di_mm
        x_kc = R - r_k                       # radial position of knuckle centre
        dist = max(R_c - r_k, 1e-9)          # crown-centre to knuckle-centre distance
        # Crown spherical cap: correct half-angle uses (R_c − r_k) as denominator
        sin_phi = min(x_kc / dist, 1.0)
        cos_phi = _m.sqrt(max(0.0, 1.0 - sin_phi ** 2))
        S_crown = 2.0 * _m.pi * R_c ** 2 * (1.0 - cos_phi)
        # Knuckle arc angle — not always 90°; depends on actual crown/knuckle radii
        inner     = max(0.0, dist ** 2 - x_kc ** 2)
        z_cj      = _m.sqrt(inner) * r_k / dist          # axial depth of junction
        r_cj_off  = x_kc * r_k / dist                    # r_cj − x_kc (radial offset)
        theta_max = _m.atan2(z_cj, r_cj_off)             # actual knuckle arc angle
        arc       = r_k * theta_max
        centroid_r = (x_kc + r_k * _m.sin(theta_max) / theta_max
                      if theta_max > 1e-9 else x_kc + r_k)
        S_knuckle = 2.0 * _m.pi * centroid_r * arc
        return S_crown + S_knuckle

    elif head_type_str in ("Conical",):
        alpha_rad = _m.radians(alpha_deg_cone)
        h = R / max(_m.tan(alpha_rad), 1e-6)
        slant = _m.sqrt(R ** 2 + h ** 2)
        return _m.pi * R * slant

    else:  # Flat
        return _m.pi * R ** 2


def _nozzle_stub_mass_kg(od_mm: float, t_mm: float, rho: float) -> float:
    """Carbon-steel pipe stub mass for _NOZZLE_STUB_MM projection."""
    Di_nz = od_mm - 2.0 * t_mm
    V = _m.pi / 4.0 * (od_mm ** 2 - Di_nz ** 2) * _NOZZLE_STUB_MM * 1e-9  # m³
    return V * rho


def _flange_mass_kg(dn: int, pn: int) -> float:
    """Look up one weld-neck flange mass.  Interpolates between tabulated DNs."""
    pn_k = _pn_key(pn)
    # find nearest DN ≤ and > requested
    dns = sorted(_FLANGE_KG.keys())
    if dn <= dns[0]:
        return _FLANGE_KG[dns[0]].get(pn_k, 0.5)
    if dn >= dns[-1]:
        return _FLANGE_KG[dns[-1]].get(pn_k, 1000.0)
    for i, d in enumerate(dns[:-1]):
        if d <= dn <= dns[i + 1]:
            m0 = _FLANGE_KG[d].get(pn_k, 0.0)
            m1 = _FLANGE_KG[dns[i + 1]].get(pn_k, 0.0)
            f = (dn - d) / (dns[i + 1] - d)
            return m0 + f * (m1 - m0)
    return 0.0


def vessel_weights(
    Di_mm: float,
    L_shell_mm: float,
    t_shell_mm: float,
    t_head_mm: float,
    head_type_str: str,
    rho_mat_kgm3: float,
    nozzle_list: list[dict],    # each: {dn, pn, service}
    code_key: str,
    has_baffles: bool,
    t_baffle_mm: float,         # plate thickness (from int_loads or default 8 mm)
    baffle_open_pct: float,
    has_meshpad: bool,
    has_inlet_dev: bool,
    n_inlets: int,
    has_vortex_brk: bool,
    saddle_w_mm: float,
    V_nll_m3: float,            # liquid volume at NLL (full vessel incl. heads)
    V_total_m3: float,          # total vessel volume (full vessel incl. heads)
    rho_liq_kgm3: float,
    crown_ratio: float = 1.0,
    knuckle_ratio: float = 0.10,
    alpha_deg_cone: float = 30.0,
    ellipse_ratio: float = 2.0,
) -> dict:
    """
    Estimate dry, operating, and hydrotest weights.
    Returns a dict with all component masses and totals.
    """
    from engines.nozzle_geometry import NOZZLE_OD, NOZZLE_WALL_T, NOZZLE_WALL_SCH, recommended_schedule

    # ── Shell ────────────────────────────────────────────────────────────────
    V_shell_m3 = _m.pi * (Di_mm + t_shell_mm) * t_shell_mm * L_shell_mm * 1e-9
    m_shell = V_shell_m3 * rho_mat_kgm3

    # ── Heads (two) ──────────────────────────────────────────────────────────
    S_head_mm2 = _head_surface_area_mm2(
        Di_mm, head_type_str, crown_ratio, knuckle_ratio, alpha_deg_cone, ellipse_ratio,
    )
    V_head_m3 = S_head_mm2 * t_head_mm * 1e-9
    m_head_each = V_head_m3 * rho_mat_kgm3
    m_heads = 2.0 * m_head_each

    # ── Nozzles ───────────────────────────────────────────────────────────────
    m_nozzles = 0.0
    nozzle_detail: list[dict] = []
    for nz in nozzle_list:
        dn  = int(nz.get("dn", 100))
        pn  = int(nz.get("pn", 25))
        tag = nz.get("tag", "?")
        svc = nz.get("service", "")
        OD  = NOZZLE_OD.get(dn, dn * 1.05)
        rec = recommended_schedule(pn, code_key)
        t_w = float(NOZZLE_WALL_SCH[rec].get(dn, NOZZLE_WALL_T.get(dn, 8.0)))
        m_stub   = _nozzle_stub_mass_kg(OD, t_w, rho_mat_kgm3)
        m_flange = _flange_mass_kg(dn, pn)
        m_nz     = m_stub + m_flange
        m_nozzles += m_nz
        nozzle_detail.append({"tag": tag, "service": svc, "dn": dn, "pn": pn,
                               "m_stub_kg": m_stub, "m_flange_kg": m_flange,
                               "m_total_kg": m_nz})

    # ── Saddles (two, carbon steel assumed) ──────────────────────────────────
    # Estimate from base plate + webs/ribs using Di and saddle width.
    # Base plate: ~Di × saddle_w × 16 mm thick (approx.)
    # Web + gussets: approx 1.4× base plate mass (typical fabrication ratio)
    rho_cs = 7850.0  # carbon steel for saddles (always CS)
    t_base_mm = max(12.0, Di_mm * 0.007)   # thickness scales with Di
    A_base_mm2 = Di_mm * saddle_w_mm * 0.9  # effective base area
    m_saddle_base = A_base_mm2 * t_base_mm * 1e-9 * rho_cs
    m_saddle_each = m_saddle_base * 1.5     # web + ribs + base plate
    m_saddles = 2.0 * m_saddle_each

    # ── Internals ─────────────────────────────────────────────────────────────
    A_vessel_m2 = _m.pi / 4.0 * (Di_mm * 1e-3) ** 2   # cross-section area

    m_baffles = 0.0
    if has_baffles:
        phi = baffle_open_pct / 100.0
        V_baffle_m3 = A_vessel_m2 * (1.0 - phi) * t_baffle_mm * 1e-3
        m_baffles = 2.0 * V_baffle_m3 * rho_mat_kgm3

    m_meshpad = 0.0
    if has_meshpad:
        # Typical knitted wire mesh: ~48 kg/m³ bulk density, 100–150 mm thick
        m_meshpad = A_vessel_m2 * 0.125 * 48.0   # 125 mm thick, 48 kg/m³

    m_inlet_dev = 0.0
    if has_inlet_dev:
        # Half-pipe: OD ≈ inlet nozzle OD, length ≈ Di, wall 8 mm, half circumference
        # Estimate: ~15 kg per DN200 inlet device, scales with Di
        m_inlet_dev = n_inlets * max(10.0, Di_mm * 0.008)

    m_vortex_brk = 0.0
    if has_vortex_brk:
        m_vortex_brk = 8.0  # flat cross-plate, ~8 kg typical

    m_internals = m_baffles + m_meshpad + m_inlet_dev + m_vortex_brk

    # ── Structural subtotal and misc allowance ───────────────────────────────
    m_structural = m_shell + m_heads + m_nozzles + m_saddles + m_internals
    m_misc = m_structural * _MISC_FACTOR

    # ── Dry weight ────────────────────────────────────────────────────────────
    m_dry = m_structural + m_misc

    # ── Operating weight ──────────────────────────────────────────────────────
    m_liquid_op = V_nll_m3 * rho_liq_kgm3
    m_operating = m_dry + m_liquid_op

    # ── Hydrotest weight ──────────────────────────────────────────────────────
    m_water_ht = V_total_m3 * 1000.0   # ρ_water = 1000 kg/m³
    m_hydrotest = m_dry + m_water_ht

    return {
        # Components
        "m_shell_kg":       m_shell,
        "m_head_each_kg":   m_head_each,
        "m_heads_kg":       m_heads,
        "m_nozzles_kg":     m_nozzles,
        "m_saddle_each_kg": m_saddle_each,
        "m_saddles_kg":     m_saddles,
        "m_baffles_kg":     m_baffles,
        "m_meshpad_kg":     m_meshpad,
        "m_inlet_dev_kg":   m_inlet_dev,
        "m_vortex_brk_kg":  m_vortex_brk,
        "m_internals_kg":   m_internals,
        "m_misc_kg":        m_misc,
        "m_structural_kg":  m_structural,
        # Totals
        "m_dry_kg":         m_dry,
        "m_liquid_op_kg":   m_liquid_op,
        "m_operating_kg":   m_operating,
        "m_water_ht_kg":    m_water_ht,
        "m_hydrotest_kg":   m_hydrotest,
        # Volume reference
        "V_nll_m3":         V_nll_m3,
        "V_total_m3":       V_total_m3,
        "rho_liq_kgm3":     rho_liq_kgm3,
        # Nozzle detail list
        "nozzle_detail":    nozzle_detail,
        # Misc factor
        "misc_factor":      _MISC_FACTOR,
    }
