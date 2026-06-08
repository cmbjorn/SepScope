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

from .nozzle_geometry import NOZZLE_OD

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


def saddle_height(
    Di_mm: float,
    t_shell_nom_mm: float,
    nozzles: list[dict],
    basis: str = BASIS_CLEAR_NOZZLES,
    custom_height_mm: float | None = None,
    ground_clearance_mm: float = 100.0,
) -> dict:
    """
    Compute the saddle stand height and overall mounting height for a basis.

    Returns a dict with the geometry breakdown, the governing constraint, the
    bottom-nozzle clearance requirement, and any layout warnings.
    """
    R = Di_mm / 2.0
    Do = Di_mm + 2.0 * t_shell_nom_mm
    t_base = _baseplate_thickness(Di_mm)
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

    return {
        "basis": basis,
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
    }
