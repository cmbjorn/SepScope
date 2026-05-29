"""
Nozzle placement geometry on pressure vessel endcaps.

Given a vertical offset from the vessel pole (top of endcap) and a nozzle
nominal diameter, determines the radial offset, angular position, zone
classification, and geometric feasibility.

Torispherical head geometry notes
-----------------------------------
The crown sphere has radius R_c, with centre on the vessel axis at depth R_c
below the pole.  The knuckle torus has minor radius r_k; its generating
circle (cross-section) has centre at (Di/2 − r_k, z_kc).  The depth of the
knuckle centre is found from the internal-tangency condition:

    z_kc = R_c − sqrt((R_c − r_k)² − (Di/2 − r_k)²)

The head–cylinder tangent line is at depth z_kc (where the knuckle circle
touches the cylindrical shell).

The crown–knuckle junction is the single tangent point between the crown
sphere and the knuckle circle, found by projecting from the crown sphere
centre through the knuckle centre:

    x_cj = R_c × (Di/2 − r_k) / (R_c − r_k)
    z_cj = R_c × (z_kc − r_k) / (R_c − r_k)

A nozzle with centre at depth d_top is in the CROWN zone when d_top ≤ z_cj,
and in the KNUCKLE zone when z_cj < d_top ≤ z_kc.

Codes:  EN 13445-3:2021 cl. 9  /  ASME VIII Div.1 UG-36–45
All dimensions in mm.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from .head_geometry import HeadType, HeadGeometry, head_geometry


# Nozzle pipe OD (mm) by DN — ISO 4200 / ASME B36.10M outside diameters
NOZZLE_OD: dict[int, float] = {
    15: 21.3,  20: 26.9,  25: 33.7,  32: 42.4,  40: 48.3,
    50: 60.3,  65: 76.1,  80: 88.9, 100: 114.3, 125: 139.7,
    150: 168.3, 200: 219.1, 250: 273.1, 300: 323.9,
    350: 355.6, 400: 406.4, 450: 457.0, 500: 508.0,
    600: 609.6, 700: 711.0, 800: 812.8,
}

# Nozzle minimum wall thickness (mm) by DN — approximate Sch 40 / standard wall
NOZZLE_WALL_T: dict[int, float] = {
    15: 2.8,  20: 2.8,  25: 3.4,  32: 3.6,  40: 3.7,
    50: 3.9,  65: 5.2,  80: 5.5, 100: 6.0, 125: 6.6,
    150: 7.1, 200: 8.2, 250: 9.3, 300: 9.5,
    350: 9.5, 400: 9.5, 450: 9.5, 500: 9.5,
    600: 9.5, 700: 11.1, 800: 12.7,
}


@dataclass
class NozzlePlacementResult:
    """Geometric feasibility and zone classification for one nozzle."""
    head_type: HeadType
    Di: float               # vessel inner diameter (mm)
    d_top_mm: float         # vertical distance from pole (mm) — input
    dn_mm: int              # nozzle DN (nominal, mm)
    nozzle_OD_mm: float     # nozzle outer diameter (mm)
    nozzle_t_mm: float      # nozzle wall thickness (mm)

    # Computed position
    x_from_axis_mm: float   # radial offset of nozzle centre from vessel axis (mm)
    alpha_deg: float        # polar angle from vessel axis (°); 0 = pole, 90 = equator
    head_depth_mm: float    # total head depth — pole to tangent line (mm)

    # Zone and validity
    zone: str               # "crown" | "knuckle" | "cone" | "flat" | "outside_head"
    geom_ok: bool           # True = nozzle fits geometrically on the head
    code_ok: bool | None    # True = zone is acceptable per EN/ASME code rules

    # Distances for reference
    nozzle_OR_mm: float = 0.0
    edge_to_shell_mm: float = 0.0           # nozzle OD edge → cylindrical shell wall (mm)
    edge_to_knuckle_mm: float | None = None # nozzle OD edge → crown–knuckle boundary (mm)
    d_crown_end_mm: float | None = None     # depth of crown–knuckle junction (mm)
    x_crown_end_mm: float | None = None     # radial offset at crown–knuckle junction (mm)
    h_head_for_plot: float = 0.0            # head depth used by the cross-section plot (mm)

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    geometry: HeadGeometry | None = None


def _tori_geometry(Di: float, R_c: float, r_k: float) -> dict:
    """
    Pre-compute all torispherical key points (in depth-from-pole convention).
    Returns a dict with:
        z_kc   : depth of knuckle centre from pole (= head depth, tangent line depth)
        x_cj   : radial offset at crown–knuckle junction
        z_cj   : depth of crown–knuckle junction from pole
    """
    x_kc = Di / 2 - r_k
    inner = max(0.0, (R_c - r_k) ** 2 - x_kc ** 2)
    z_kc = R_c - math.sqrt(inner)          # head depth = z_kc (tangent at z=z_kc)
    dist = R_c - r_k                       # distance between sphere and knuckle centres
    # Junction is on the line from crown centre (0, R_c) toward knuckle centre (x_kc, z_kc)
    x_cj = R_c * x_kc / dist              # x-component
    z_cj = R_c + R_c * (z_kc - R_c) / dist  # z-component = R_c * (z_kc - r_k) / dist
    return {"z_kc": z_kc, "x_cj": x_cj, "z_cj": z_cj}


def nozzle_on_head(
    head_type: HeadType,
    Di: float,
    d_top_mm: float,
    dn_mm: int,
    crown_ratio: float = 1.0,
    knuckle_ratio: float = 0.1,
    alpha_deg_cone: float = 30.0,
    ellipse_ratio: float = 2.0,
    nozzle_OD_mm: float | None = None,
    nozzle_t_mm: float | None = None,
) -> NozzlePlacementResult:
    """
    Evaluate nozzle placement on a pressure vessel endcap.

    Parameters
    ----------
    head_type       : endcap type (HeadType enum)
    Di              : vessel inner diameter (mm)
    d_top_mm        : vertical distance from pole to nozzle centre (mm).
                      For flat heads: radial distance from plate centre.
    dn_mm           : nozzle nominal diameter (DN, integer mm)
    crown_ratio     : R_c / Di for torispherical crown sphere (default 1.0)
    knuckle_ratio   : r_k / Di for torispherical knuckle (default 0.1)
    alpha_deg_cone  : half-apex angle for conical heads (degrees)
    ellipse_ratio   : Di / (2h), 2.0 = standard 2:1 ellipse
    nozzle_OD_mm    : override nozzle OD; if None, looked up from NOZZLE_OD table
    nozzle_t_mm     : override nozzle wall; if None, looked up from NOZZLE_WALL_T
    """
    if nozzle_OD_mm is None:
        nozzle_OD_mm = NOZZLE_OD.get(dn_mm, dn_mm * 1.05)
    if nozzle_t_mm is None:
        nozzle_t_mm = NOZZLE_WALL_T.get(dn_mm, 6.0)

    nozzle_OR = nozzle_OD_mm / 2.0
    R = Di / 2.0  # vessel inner radius

    geom = head_geometry(head_type, Di, crown_ratio, knuckle_ratio, alpha_deg_cone, ellipse_ratio)
    warnings: list[str] = []
    errors: list[str] = []

    x: float = 0.0
    alpha: float = 0.0
    h_head: float = 0.0
    zone: str = "crown"
    d_crown_end: float | None = None
    x_crown_end: float | None = None
    edge_to_knuckle: float | None = None

    # ── Per-head-type geometry (depth from pole convention) ───────────────────

    if head_type == HeadType.HEMISPHERICAL:
        # Sphere of radius R, centre at depth R from pole.
        # Surface: x² + (z − R)² = R²  →  x = sqrt(2Rz − z²)
        R_s = R
        h_head = R_s
        if d_top_mm > h_head:
            errors.append(
                f"d_top {d_top_mm:.0f} mm exceeds head depth {h_head:.0f} mm — "
                "nozzle is on the cylindrical shell, not the endcap.")
            x, alpha, zone = R, 90.0, "outside_head"
        else:
            x = math.sqrt(max(0.0, 2 * R_s * d_top_mm - d_top_mm ** 2))
            alpha = math.degrees(math.acos(max(-1.0, min(1.0, 1 - d_top_mm / R_s))))
            zone = "crown"
        d_crown_end = h_head

    elif head_type == HeadType.ELLIPSOIDAL:
        # Semi-minor axis b = Di/(2·ellipse_ratio) = head height from tangent to pole.
        # Ellipse: (x/a)² + ((b−z)/b)² = 1  →  x = a·sqrt(1 − ((b−z)/b)²)
        b = Di / (2 * ellipse_ratio)
        a = R
        h_head = b
        if d_top_mm > h_head:
            errors.append(
                f"d_top {d_top_mm:.0f} mm exceeds head depth {h_head:.0f} mm — "
                "nozzle is on the cylindrical shell, not the endcap.")
            x, alpha, zone = R, 90.0, "outside_head"
        else:
            # z measured from pole (same as d_top); tangent is at z = b
            frac = (b - d_top_mm) / b   # 1.0 at pole, 0.0 at tangent
            x = a * math.sqrt(max(0.0, 1 - frac ** 2))
            alpha = math.degrees(math.acos(max(-1.0, min(1.0, frac))))
            zone = "crown"
        d_crown_end = h_head

    elif head_type == HeadType.TORISPHERICAL:
        R_c = crown_ratio * Di
        r_k = knuckle_ratio * Di

        if r_k < 0.06 * Di:
            warnings.append(f"Knuckle radius r_k = {r_k:.0f} mm < 0.06·Di. Code minimum is 0.06·Di.")

        tg = _tori_geometry(Di, R_c, r_k)
        z_kc = tg["z_kc"]
        x_cj = tg["x_cj"]
        z_cj = tg["z_cj"]
        h_head = z_kc   # head depth = depth at which knuckle meets cylinder

        d_crown_end = z_cj
        x_crown_end = x_cj

        if d_top_mm > h_head:
            errors.append(
                f"d_top {d_top_mm:.0f} mm exceeds head depth {h_head:.0f} mm — "
                "nozzle is on the cylindrical shell, not the endcap.")
            x, alpha, zone = R, 90.0, "outside_head"
        elif d_top_mm <= z_cj:
            # Crown (spherical) zone
            x = math.sqrt(max(0.0, 2 * R_c * d_top_mm - d_top_mm ** 2))
            cos_a = max(-1.0, min(1.0, 1 - d_top_mm / R_c))
            alpha = math.degrees(math.acos(cos_a))
            zone = "crown"
        else:
            # Knuckle zone
            dz = d_top_mm - z_kc   # ≤ 0 (knuckle arcs from z_kc upward toward pole)
            x_kc = Di / 2 - r_k
            x = x_kc + math.sqrt(max(0.0, r_k ** 2 - dz ** 2))
            alpha = math.degrees(math.atan2(x, max(0.0001, R_c - d_top_mm)))
            zone = "knuckle"
            warnings.append(
                "Nozzle centre is in the knuckle transition zone. "
                "EN 13445-3 cl. 9 and ASME UG-36 require nozzles on torispherical "
                "heads to lie entirely within the spherical crown zone. "
                "Move the nozzle closer to the pole.")

        # Clearance from nozzle OD edge to the crown–knuckle boundary (radial)
        if zone != "outside_head":
            edge_to_knuckle = x_cj - (x + nozzle_OR)
            if zone == "crown" and edge_to_knuckle < 0:
                warnings.append(
                    f"Nozzle OD edge extends {-edge_to_knuckle:.0f} mm into the "
                    f"knuckle zone (nozzle edge at x = {x + nozzle_OR:.0f} mm, "
                    f"junction at x = {x_cj:.0f} mm). "
                    "Reduce nozzle size or move closer to the pole.")
                zone = "knuckle"

    elif head_type == HeadType.CONICAL:
        alpha_rad = math.radians(alpha_deg_cone)
        h_head = R / math.tan(alpha_rad)   # full cone height apex→base

        if d_top_mm < 0:
            errors.append("d_top cannot be negative.")
            x, alpha, zone = 0.0, 0.0, "outside_head"
        elif d_top_mm > h_head:
            errors.append(
                f"d_top {d_top_mm:.0f} mm exceeds cone height {h_head:.0f} mm.")
            x, alpha, zone = R, alpha_deg_cone, "outside_head"
        else:
            x = d_top_mm * math.tan(alpha_rad)
            alpha = alpha_deg_cone
            zone = "cone"
            if d_top_mm < max(50.0, nozzle_OD_mm):
                warnings.append(
                    f"Nozzle is very close to the cone apex (d_top = {d_top_mm:.0f} mm). "
                    "Reinforcement near the apex requires specialist analysis.")

    else:  # FLAT
        # Interpret d_top_mm as radial distance from plate centre.
        h_head = 0.0
        x = d_top_mm
        alpha = 90.0
        zone = "flat"

    # ── Common geometric feasibility checks ───────────────────────────────────

    edge_to_shell = R - (x + nozzle_OR)

    if zone != "outside_head":
        if nozzle_OD_mm >= Di:
            errors.append(
                f"Nozzle OD ({nozzle_OD_mm:.0f} mm) ≥ vessel Di ({Di:.0f} mm). Not feasible.")
        elif edge_to_shell < 0:
            errors.append(
                f"Nozzle OD edge extends {-edge_to_shell:.0f} mm beyond the vessel inner "
                f"wall (nozzle at x = {x:.0f} mm, OR = {nozzle_OR:.0f} mm, R = {R:.0f} mm). "
                "Move the nozzle closer to the pole or use a smaller DN.")
        elif edge_to_shell < 0.5 * nozzle_OR:
            warnings.append(
                f"Small clearance from nozzle OD edge to vessel wall: {edge_to_shell:.0f} mm.")

    geom_ok = len(errors) == 0

    # Code-zone compliance (geometric placement only; reinforcement is separate)
    if geom_ok:
        if head_type in (HeadType.HEMISPHERICAL, HeadType.ELLIPSOIDAL):
            code_ok = zone == "crown"
        elif head_type == HeadType.TORISPHERICAL:
            code_ok = (zone == "crown") and (edge_to_knuckle is not None) and (edge_to_knuckle >= 0)
        elif head_type == HeadType.CONICAL:
            code_ok = zone == "cone"
        elif head_type == HeadType.FLAT:
            code_ok = (x + nozzle_OR) <= R
        else:
            code_ok = None
    else:
        code_ok = False

    return NozzlePlacementResult(
        head_type=head_type,
        Di=Di,
        d_top_mm=d_top_mm,
        dn_mm=dn_mm,
        nozzle_OD_mm=nozzle_OD_mm,
        nozzle_t_mm=nozzle_t_mm,
        x_from_axis_mm=round(x, 1),
        alpha_deg=round(alpha, 2),
        head_depth_mm=round(h_head, 1),
        zone=zone,
        geom_ok=geom_ok,
        code_ok=code_ok,
        nozzle_OR_mm=round(nozzle_OR, 1),
        edge_to_shell_mm=round(edge_to_shell, 1),
        edge_to_knuckle_mm=round(edge_to_knuckle, 1) if edge_to_knuckle is not None else None,
        d_crown_end_mm=round(d_crown_end, 1) if d_crown_end is not None else None,
        x_crown_end_mm=round(x_crown_end, 1) if x_crown_end is not None else None,
        h_head_for_plot=round(h_head, 1),
        warnings=warnings,
        errors=errors,
        geometry=geom,
    )
