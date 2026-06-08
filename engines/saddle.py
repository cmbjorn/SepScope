"""
Saddle stand height and overall mounting height for a horizontal vessel.

Neither EN 13445 nor ASME VIII Div.1 prescribes a saddle *height* — both govern
the saddle wrap/contact angle (≥ 120°, EN 13445-3 §16.8 / Zick method) and the
shell stresses, not how high the vessel sits. The height is a layout quantity:

    overall height = D_o + saddle stand height + baseplate thickness

where the *minimum* stand height is the larger of a structural minimum and the
clearance needed for any bottom nozzles (liquid outlet / drain on the shell
bottom) plus a ground clearance under the feet. This module computes that height
for a chosen basis so the user can see — and minimise — the mounting height.

All dimensions in mm.
"""
from __future__ import annotations
import math

from .nozzle_geometry import NOZZLE_OD

_G = 9.81                  # m/s²
_FY_SADDLE_MPA = 235.0     # saddle steel yield (S235, carbon steel — saddles are always CS)
_SIGMA_ALLOW_BASE = 0.66 * _FY_SADDLE_MPA   # baseplate bending allowable (≈ 155 MPa)
SADDLE_WRAP_ANGLES = [120, 150, 168]        # EN 13445-3 §16.8 / Zick contact angles

# Mounting options (first is the default).
MOUNTING_FOUNDATION = "Concrete foundation (baseplate)"
MOUNTING_SKID       = "Skid-mounted (no baseplate)"
SADDLE_MOUNTINGS    = [MOUNTING_FOUNDATION, MOUNTING_SKID]

# Basis options (the first is the safe default).
BASIS_CLEAR_NOZZLES = "Clear bottom nozzles"
BASIS_MINIMUM       = "Minimum (structural)"
BASIS_PROPORTIONAL  = "Proportional (0.25 × R)"
BASIS_CUSTOM        = "Custom"
SADDLE_HEIGHT_BASES = [BASIS_CLEAR_NOZZLES, BASIS_MINIMUM, BASIS_PROPORTIONAL, BASIS_CUSTOM]

CODE_NOTE = (
    "Saddle height is not prescribed by EN 13445 or ASME VIII — both govern the "
    "saddle wrap angle (≥ 120°, EN 13445-3 §16.8 / Zick) and shell stresses, not "
    "the mounting height. Height here is a layout estimate; confirm against piping, "
    "foundation and Zick saddle design."
)


def _baseplate_thickness(Di_mm: float) -> float:
    """Baseplate thickness — same scaling as the weight engine (max(12, 0.007·Di))."""
    return max(12.0, Di_mm * 0.007)


def _bottom_nozzle_projection(dn: int) -> float:
    """How far a bottom nozzle (stub + flange) hangs below the shell, mm."""
    od = NOZZLE_OD.get(dn, dn * 1.05)
    stub = max(150.0, 0.8 * od)        # stub length to the flange face
    flange_t = max(20.0, 0.05 * od)    # weld-neck flange thickness
    return stub + flange_t


def zick_saddle_design(
    Di_mm: float,
    saddle_w_mm: float,
    weight_result: dict,
    wrap_angle_deg: float = 120.0,
    bearing_pressure_MPa: float = 3.5,
    has_baseplate: bool = True,
) -> dict:
    """
    Firm up the saddle from the saddle reaction load (Zick basis).

    Two symmetric saddles carry the (heaviest) hydrotest weight; the reaction Q
    per saddle is always computed. When `has_baseplate` (concrete foundation) the
    baseplate is sized from the allowable bearing pressure and its thickness +
    a load-spread stand minimum firm the height. When skid-mounted (no baseplate)
    the saddle bolts to the skid steelwork: no baseplate is added to the height
    and there is no foundation-bearing check — the reaction Q sizes the skid
    beams (structural-steel design, out of scope).

    Returns reaction loads and, for a foundation, the baseplate dimensions and
    bearing check; `t_base_mm` is 0 for a skid.
    """
    R = Di_mm / 2.0
    theta = math.radians(wrap_angle_deg)

    m_hydro = float(weight_result.get("m_hydrotest_kg", 0.0))
    m_oper = float(weight_result.get("m_operating_kg", 0.0))
    W_hydro_N = m_hydro * _G
    W_oper_N = m_oper * _G
    Q_N = W_hydro_N / 2.0                       # reaction per saddle (hydrotest governs)
    c_contact = Di_mm * math.sin(theta / 2.0)  # saddle contact chord (transverse)

    warnings: list[str] = []

    if not has_baseplate:
        # Skid-mounted: no baseplate, no foundation bearing. Saddle bolts to skid.
        result = {
            "has_baseplate": False,
            "wrap_angle_deg": wrap_angle_deg,
            "W_operating_N": W_oper_N,
            "W_hydrotest_N": W_hydro_N,
            "Q_per_saddle_N": Q_N,
            "c_contact_mm": c_contact,
            "B_mm": None, "L_bp_mm": None,
            "p_act_MPa": None, "p_allow_MPa": None, "bearing_ok": None,
            "t_base_mm": 0.0,
            "h_struct_mm": max(150.0, 0.10 * R),
            "warnings": warnings,
            "note": ("Skid-mounted: the saddle bolts to the skid steelwork — no "
                     "baseplate and no foundation bearing. The saddle reaction "
                     "below sizes the skid beams (structural-steel design, out of "
                     "scope). Two symmetric saddles, hydrotest load governing."),
        }
        return result

    L_bp = max(saddle_w_mm, 50.0)              # baseplate length along the vessel axis
    p_allow = max(bearing_pressure_MPa, 1e-6)  # MPa = N/mm²
    A_req = Q_N / p_allow                       # required bearing area, mm²
    B_req = A_req / L_bp                         # bearing-driven width, mm
    B_max = Di_mm                               # practical limit: ≤ vessel diameter
    # Width is the largest of the bearing demand and the contact chord, but capped
    # at a practical maximum — if the cap binds, the foundation is inadequate.
    B = max(min(B_req, B_max), c_contact, 150.0)
    p_act = Q_N / (B * L_bp)                     # actual bearing pressure, MPa
    bearing_ok = p_act <= p_allow * 1.001

    # Baseplate thickness from cantilever bending of the overhang under p_act.
    c_over = max((B - c_contact) / 2.0, 0.25 * B)
    t_bp = math.sqrt(3.0 * p_act * c_over ** 2 / _SIGMA_ALLOW_BASE)
    t_bp = max(12.0, math.ceil(t_bp))

    # Firmed structural-minimum stand: load-spread floor (web ≥ overhang).
    h_struct = max(150.0, 0.10 * R, c_over)

    if not bearing_ok:
        warnings.append(
            f"Foundation bearing {p_act:.2f} MPa exceeds the allowable "
            f"{p_allow:.2f} MPa — enlarge the baseplate or the footing.")

    return {
        "has_baseplate": True,
        "wrap_angle_deg": wrap_angle_deg,
        "W_operating_N": W_oper_N,
        "W_hydrotest_N": W_hydro_N,
        "Q_per_saddle_N": Q_N,
        "c_contact_mm": c_contact,
        "B_mm": B,
        "L_bp_mm": L_bp,
        "p_act_MPa": p_act,
        "p_allow_MPa": p_allow,
        "bearing_ok": bearing_ok,
        "t_base_mm": t_bp,
        "h_struct_mm": h_struct,
        "warnings": warnings,
        "note": ("Reaction-based foundation firming (Zick basis): two symmetric "
                 "saddles, hydrotest load governing. Full Zick shell-stress "
                 "analysis (EN 13445-3 §16.8) recommended for detailed design."),
    }


def saddle_height(
    Di_mm: float,
    t_shell_nom_mm: float,
    nozzles: list[dict],
    basis: str = BASIS_CLEAR_NOZZLES,
    custom_height_mm: float | None = None,
    ground_clearance_mm: float = 100.0,
    weight_result: dict | None = None,
    saddle_w_mm: float = 250.0,
    wrap_angle_deg: float = 120.0,
    bearing_pressure_MPa: float = 3.5,
    has_baseplate: bool = True,
) -> dict:
    """
    Compute the saddle stand height and overall mounting height for a basis.

    When `weight_result` is supplied, the baseplate thickness and the structural-
    minimum stand are firmed up from the Zick saddle reaction (see
    `zick_saddle_design`); otherwise rule-of-thumb values are used. `has_baseplate`
    selects the mounting: a concrete foundation (baseplate adds to the height and
    a bearing check applies) or a skid (no baseplate, no foundation bearing).

    Returns a dict with the geometry breakdown, the governing constraint, the
    bottom-nozzle clearance requirement, any layout warnings, the mounting, and
    (when weight is given) a `zick` sub-dict.
    """
    R = Di_mm / 2.0
    Do = Di_mm + 2.0 * t_shell_nom_mm

    zick = None
    if weight_result is not None:
        zick = zick_saddle_design(Di_mm, saddle_w_mm, weight_result,
                                  wrap_angle_deg, bearing_pressure_MPa, has_baseplate)
        t_base = zick["t_base_mm"]          # load-derived baseplate (0 for skid)
        h_struct = zick["h_struct_mm"]      # load-spread stand minimum (firmed)
    else:
        t_base = _baseplate_thickness(Di_mm) if has_baseplate else 0.0
        h_struct = max(150.0, 0.10 * R)

    # Bottom nozzles (liquid outlet / drain) hang below the shell and set the
    # clearance the saddle must provide to keep their flanges above the feet.
    bottom = []
    for nz in nozzles or []:
        if nz.get("loc") == "Shell — bottom":
            dn = nz.get("dn", 50)
            proj = _bottom_nozzle_projection(dn)
            bottom.append({"tag": nz.get("tag", "?"), "dn": dn, "proj_mm": proj,
                           "service": nz.get("service", "")})
    max_proj = max((b["proj_mm"] for b in bottom), default=0.0)
    h_clear = (max_proj + ground_clearance_mm) if bottom else 0.0

    warnings: list[str] = []

    if basis == BASIS_MINIMUM:
        h_stand = h_struct
        governing = "Structural minimum"
        if bottom:
            tags = ", ".join(b["tag"] for b in bottom)
            warnings.append(
                f"Minimum height ignores bottom nozzle clearance — relocate {tags} "
                f"to the head/side, or the flange(s) will sit only "
                f"{h_stand - h_clear:.0f} mm below grade (needs ≥ {h_clear:.0f} mm).")
    elif basis == BASIS_PROPORTIONAL:
        h_stand = max(h_struct, 0.25 * R)
        governing = "Proportional (0.25 × R)"
        if bottom and h_stand < h_clear:
            warnings.append(
                f"Proportional height {h_stand:.0f} mm is below the bottom-nozzle "
                f"clearance ({h_clear:.0f} mm) — flanges would not clear grade.")
    elif basis == BASIS_CUSTOM:
        h_stand = float(custom_height_mm or 0.0)
        governing = "Custom (user-specified)"
        if h_stand < h_struct:
            warnings.append(
                f"Custom height {h_stand:.0f} mm is below the structural minimum "
                f"({h_struct:.0f} mm).")
        if bottom and h_stand < h_clear:
            warnings.append(
                f"Custom height {h_stand:.0f} mm is below the bottom-nozzle "
                f"clearance ({h_clear:.0f} mm) — flanges would not clear grade.")
    else:  # BASIS_CLEAR_NOZZLES (default)
        h_stand = max(h_struct, h_clear)
        governing = ("Bottom-nozzle clearance" if h_clear >= h_struct
                     else "Structural minimum")

    overall = Do + h_stand + t_base

    if zick is not None:
        warnings = warnings + zick["warnings"]

    return {
        "basis": basis,
        "mounting": MOUNTING_FOUNDATION if has_baseplate else MOUNTING_SKID,
        "has_baseplate": has_baseplate,
        "Di_mm": Di_mm,
        "Do_mm": Do,
        "t_base_mm": t_base,
        "h_struct_mm": h_struct,
        "h_clear_mm": h_clear,
        "h_stand_mm": h_stand,
        "overall_height_mm": overall,
        "ground_clearance_mm": ground_clearance_mm,
        "governing": governing,
        "bottom_nozzles": bottom,
        "warnings": warnings,
        "code_note": CODE_NOTE,
        "zick": zick,
    }
