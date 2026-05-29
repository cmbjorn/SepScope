"""
Nozzle placement geometry on pressure vessel endcaps — horizontal vessel convention.

Input reference
---------------
d_from_top_mm : vertical distance from the vessel TOP inner wall to the nozzle
                centreline.
                0 mm   = nozzle centreline at the same height as the inside top
                         of the cylindrical shell (at the tangent line between
                         shell and head, outermost position, generally not
                         buildable).
                Di/2   = nozzle centreline on the vessel horizontal axis.
                Di     = nozzle centreline at the inside bottom.

This measurement is independent of head type.  The geometry engine converts it
to the radial distance from the vessel axis (r) and, from the head surface
equation, to the axial depth of the nozzle on the curved head face.

Proximity to the vessel wall — engineering implications
-------------------------------------------------------
As the nozzle moves toward the vessel wall (r → Di/2):

1. The nozzle OD circle eventually overlaps the cylindrical shell → infeasible.
2. For torispherical heads the nozzle enters the knuckle transition zone before
   reaching the shell wall.  Standard area-replacement rules (cl. 9 / UG-37)
   are not valid in the knuckle — specialist analysis required.
3. As the nozzle edge approaches the head–cylinder circumferential seam weld,
   EN 13445-3 cl. 5.6 / ASME VIII-1 UW-11 require a minimum clearance
   (typically max(3t, 25 mm)) between adjacent weld toes.
4. Very close to the junction, a three-way stress interaction (nozzle + head +
   cylinder) arises that is outside the scope of standard code formulas.
5. The reinforcement limit zone may spill into the cylindrical shell; the shell
   thickness must also satisfy UG-45 / cl. 9.4 limits.

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
    Di: float                   # vessel inner diameter (mm)
    d_from_top_mm: float        # vertical distance from vessel top inner wall (mm) — INPUT
    dn_mm: int                  # nozzle DN (nominal, mm)
    nozzle_OD_mm: float
    nozzle_t_mm: float

    # Computed position
    r_from_axis_mm: float       # radial distance from vessel axis (mm)
    y_nozzle_mm: float          # signed vertical position: + above axis, − below axis (mm)
    z_on_head_mm: float         # axial depth of nozzle on head surface from tangent (mm)
    head_depth_mm: float        # total head depth — tangent to pole (mm)

    # Zone and validity
    zone: str                   # "crown" | "knuckle" | "cone" | "flat" | "outside_head"
    geom_ok: bool
    code_ok: bool | None

    # Clearances
    nozzle_OR_mm: float = 0.0
    edge_to_shell_mm: float = 0.0        # nozzle OD edge → cylindrical shell wall (mm)
    edge_to_knuckle_mm: float | None = None  # nozzle OD edge → crown–knuckle boundary (mm)
    r_crown_end_mm: float | None = None   # radial offset at crown–knuckle junction (mm)
    z_crown_end_mm: float | None = None   # axial depth of crown–knuckle junction (mm)
    d_at_crown_end_mm: float | None = None  # d_from_top value at crown–knuckle junction

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    geometry: HeadGeometry | None = None


def _tori_geometry(Di: float, R_c: float, r_k: float) -> dict:
    """
    Pre-compute torispherical key points.

    Convention: Z = axial distance from the tangent plane (head–shell junction),
    positive toward the pole.  r = radial distance from the vessel axis.

    Returns:
        h_head   : head depth (tangent to pole, mm)
        r_cj     : radial distance of crown–knuckle junction from axis (mm)
        z_cj     : axial depth of crown–knuckle junction from tangent (mm)
        Z_sc     : axial position of crown sphere centre (mm, can be negative)
    """
    R = Di / 2
    x_kc = R - r_k                               # knuckle centre radial offset
    # Tangency condition: dist(crown_ctr, knuckle_ctr) = R_c - r_k
    # Crown sphere centre on axis at Z = Z_sc_old from POLE; in new convention:
    # h_head = depth of tangent from pole (old z_kc) computed from:
    #   x_kc² + (h_head - R_c)² = (R_c - r_k)²  [where old z_kc = h_head]
    inner = max(0.0, (R_c - r_k) ** 2 - x_kc ** 2)
    h_head_old_zsc = R_c - math.sqrt(inner)   # = z_kc in old depth-from-pole convention
    h_head = h_head_old_zsc                   # same numerical value, now "depth from tangent"

    Z_sc = h_head - R_c   # axial position of sphere centre (negative for std Klöpper)

    # Crown–knuckle junction via internal tangency point projection
    dist = R_c - r_k
    # Direction from crown centre (Z=Z_sc, r=0) to knuckle centre (Z=0, r=x_kc):
    dZ = 0 - Z_sc    # = -Z_sc = R_c - h_head
    dr = x_kc - 0
    # Junction = crown_centre + R_c × unit(to knuckle centre)
    r_cj = 0 + R_c * dr / dist
    z_cj = Z_sc + R_c * dZ / dist

    return {
        "h_head": h_head,
        "r_cj": r_cj,
        "z_cj": z_cj,
        "Z_sc": Z_sc,
    }


def _z_on_head(head_type: HeadType, Di: float, r: float,
               R_c: float, r_k: float, b: float, alpha_deg: float,
               tg: dict | None = None) -> float:
    """
    Axial depth of the head surface at radial distance r from the axis.
    Returned value: Z from the tangent plane (0 = tangent, h_head = pole).
    Returns 0.0 if r > Di/2 (outside head).
    """
    R = Di / 2
    if r > R:
        return 0.0

    if head_type == HeadType.HEMISPHERICAL:
        return math.sqrt(max(0.0, R ** 2 - r ** 2))

    elif head_type == HeadType.ELLIPSOIDAL:
        h_head = b
        return h_head * math.sqrt(max(0.0, 1 - (r / R) ** 2))

    elif head_type == HeadType.TORISPHERICAL:
        if tg is None:
            tg = _tori_geometry(Di, R_c, r_k)
        r_cj = tg["r_cj"]
        Z_sc = tg["Z_sc"]
        x_kc = R - r_k

        if r <= r_cj:
            # Crown sphere
            return Z_sc + math.sqrt(max(0.0, R_c ** 2 - r ** 2))
        else:
            # Knuckle torus (generating circle at Z=0, r=x_kc, radius r_k)
            return math.sqrt(max(0.0, r_k ** 2 - (r - x_kc) ** 2))

    elif head_type == HeadType.CONICAL:
        alpha_rad = math.radians(alpha_deg)
        h_head = R / math.tan(alpha_rad)
        # On a cone: r / tan(α) = Z → r = Z*tan(α) → Z = r / tan(α)
        return (R - r) / math.tan(alpha_rad)   # depth from tangent at radial r

    else:  # FLAT
        return 0.0


def nozzle_on_head(
    head_type: HeadType,
    Di: float,
    d_from_top_mm: float,
    dn_mm: int,
    crown_ratio: float = 1.0,
    knuckle_ratio: float = 0.1,
    alpha_deg_cone: float = 30.0,
    ellipse_ratio: float = 2.0,
    nozzle_OD_mm: float | None = None,
    nozzle_t_mm: float | None = None,
    t_head_nom_mm: float = 20.0,   # for weld-clearance check
) -> NozzlePlacementResult:
    """
    Evaluate nozzle placement on a pressure vessel endcap.

    Parameters
    ----------
    d_from_top_mm   : vertical distance from the vessel top inner wall to the
                      nozzle centreline (mm).  0 = top of vessel inner wall,
                      Di/2 = vessel axis, Di = bottom.
    dn_mm           : nozzle nominal diameter (DN, integer mm)
    t_head_nom_mm   : nominal head thickness (mm) — used for weld clearance check
    All other parameters: head geometry (same as head_geometry())
    """
    if nozzle_OD_mm is None:
        nozzle_OD_mm = NOZZLE_OD.get(dn_mm, dn_mm * 1.05)
    if nozzle_t_mm is None:
        nozzle_t_mm = NOZZLE_WALL_T.get(dn_mm, 6.0)

    nozzle_OR = nozzle_OD_mm / 2.0
    R = Di / 2.0

    R_c = crown_ratio * Di
    r_k = knuckle_ratio * Di
    b = Di / (2 * ellipse_ratio)   # ellipsoidal semi-minor axis

    geom = head_geometry(head_type, Di, crown_ratio, knuckle_ratio, alpha_deg_cone, ellipse_ratio)
    warnings: list[str] = []
    errors: list[str] = []

    # ── Radial distance and vertical position ─────────────────────────────────
    if d_from_top_mm < 0:
        errors.append("d_from_top cannot be negative.")
        d_from_top_mm = 0.0
    elif d_from_top_mm > Di:
        errors.append(f"d_from_top {d_from_top_mm:.0f} mm > Di {Di:.0f} mm.")
        d_from_top_mm = Di

    y_nozzle = R - d_from_top_mm          # + above axis, − below axis
    r = abs(y_nozzle)                     # radial distance from axis

    # ── Head-type specific geometry ───────────────────────────────────────────
    tg: dict | None = None
    h_head: float = 0.0
    zone: str = "crown"
    r_crown_end: float | None = None
    z_crown_end: float | None = None
    d_at_crown_end: float | None = None
    edge_to_knuckle: float | None = None

    if head_type == HeadType.HEMISPHERICAL:
        h_head = R
        if r > R:
            errors.append(
                f"Radial offset r = {r:.0f} mm > vessel radius R = {R:.0f} mm. "
                "Nozzle is outside the vessel — check d_from_top.")
            zone = "outside_head"
        else:
            zone = "crown"
        r_crown_end = R   # head extends to r = R at the tangent
        z_crown_end = 0.0

    elif head_type == HeadType.ELLIPSOIDAL:
        h_head = b
        if r > R:
            errors.append(f"r = {r:.0f} mm > R = {R:.0f} mm.")
            zone = "outside_head"
        else:
            zone = "crown"
        r_crown_end = R
        z_crown_end = 0.0

    elif head_type == HeadType.TORISPHERICAL:
        tg = _tori_geometry(Di, R_c, r_k)
        h_head = tg["h_head"]
        r_cj = tg["r_cj"]
        z_cj = tg["z_cj"]

        if r_k < 0.06 * Di:
            warnings.append(f"Knuckle radius r_k = {r_k:.0f} mm < 0.06·Di. Code minimum is 0.06·Di.")

        r_crown_end = r_cj
        z_crown_end = z_cj
        d_at_crown_end = R - r_cj   # d_from_top value at the crown–knuckle boundary

        if r > R:
            errors.append(f"r = {r:.0f} mm > R = {R:.0f} mm.")
            zone = "outside_head"
        elif r <= r_cj:
            zone = "crown"
        else:
            zone = "knuckle"
            warnings.append(
                f"Nozzle centre is in the knuckle transition zone "
                f"(r = {r:.0f} mm > r_crown = {r_cj:.0f} mm). "
                "EN 13445-3 cl. 9 and ASME UG-36 require nozzles on torispherical "
                "heads to lie entirely within the spherical crown zone. "
                f"Move the nozzle so d_from_top ≤ {d_at_crown_end:.0f} mm "
                f"(or ≥ {Di - d_at_crown_end:.0f} mm for bottom half).")

        # Radial clearance from nozzle OD edge to crown–knuckle boundary
        if zone != "outside_head":
            edge_to_knuckle = r_cj - (r + nozzle_OR)
            if zone == "crown" and edge_to_knuckle < 0:
                warnings.append(
                    f"Nozzle OD edge extends {-edge_to_knuckle:.0f} mm into the "
                    f"knuckle zone (nozzle edge at r = {r + nozzle_OR:.0f} mm, "
                    f"knuckle starts at r = {r_cj:.0f} mm). "
                    "Reduce nozzle size or move toward the axis.")
                zone = "knuckle"

    elif head_type == HeadType.CONICAL:
        alpha_rad = math.radians(alpha_deg_cone)
        h_head = R / math.tan(alpha_rad)
        if r > R:
            errors.append(f"r = {r:.0f} mm > R = {R:.0f} mm.")
            zone = "outside_head"
        else:
            zone = "cone"
            if r < 0.1 * R:   # nozzle very close to the apex
                warnings.append(
                    "Nozzle is close to the cone apex. "
                    "Reinforcement near the apex requires specialist analysis.")

    else:  # FLAT
        h_head = 0.0
        zone = "flat"
        if r > R:
            errors.append(f"Nozzle at r = {r:.0f} mm > vessel R = {R:.0f} mm.")

    # ── Axial depth on head surface ───────────────────────────────────────────
    z_nozzle = _z_on_head(head_type, Di, r, R_c, r_k, b, alpha_deg_cone, tg)

    # ── Common geometric checks ───────────────────────────────────────────────
    edge_to_shell = R - (r + nozzle_OR)

    if zone != "outside_head":
        if nozzle_OD_mm >= Di:
            errors.append(
                f"Nozzle OD ({nozzle_OD_mm:.0f} mm) ≥ vessel Di ({Di:.0f} mm).")
        elif edge_to_shell < 0:
            errors.append(
                f"Nozzle OD extends {-edge_to_shell:.0f} mm beyond the vessel "
                f"inner wall. Nozzle at r = {r:.0f} mm with OR = {nozzle_OR:.0f} mm "
                f"gives edge at r = {r + nozzle_OR:.0f} mm > R = {R:.0f} mm. "
                "Move nozzle toward vessel axis (increase d_from_top toward Di/2) "
                "or use a smaller DN.")
        else:
            # Proximity-to-junction warning
            # Minimum weld clearance: max(3 × t_head, 25 mm)
            min_clearance = max(3.0 * t_head_nom_mm, 25.0)
            if edge_to_shell < min_clearance:
                warnings.append(
                    f"Nozzle OD edge is only {edge_to_shell:.0f} mm from the vessel "
                    f"inner wall (recommended minimum clearance to avoid weld "
                    f"interference: {min_clearance:.0f} mm = max(3×t_head, 25 mm)). "
                    "Complex 3-way stress state at the nozzle/head/shell junction — "
                    "special analysis may be required.")
            if d_from_top_mm < nozzle_OR or d_from_top_mm > (Di - nozzle_OR):
                errors.append(
                    f"Nozzle centreline is only {min(d_from_top_mm, Di - d_from_top_mm):.0f} mm "
                    f"from the vessel wall (nozzle OR = {nozzle_OR:.0f} mm). "
                    "Nozzle must be further from the vessel wall.")

    geom_ok = len(errors) == 0

    # Code-zone compliance
    if geom_ok:
        if head_type in (HeadType.HEMISPHERICAL, HeadType.ELLIPSOIDAL):
            code_ok = zone == "crown"
        elif head_type == HeadType.TORISPHERICAL:
            code_ok = (zone == "crown") and (edge_to_knuckle is not None) and (edge_to_knuckle >= 0)
        elif head_type == HeadType.CONICAL:
            code_ok = zone == "cone"
        elif head_type == HeadType.FLAT:
            code_ok = r + nozzle_OR <= R
        else:
            code_ok = None
    else:
        code_ok = False

    return NozzlePlacementResult(
        head_type=head_type,
        Di=Di,
        d_from_top_mm=d_from_top_mm,
        dn_mm=dn_mm,
        nozzle_OD_mm=nozzle_OD_mm,
        nozzle_t_mm=nozzle_t_mm,
        r_from_axis_mm=round(r, 1),
        y_nozzle_mm=round(y_nozzle, 1),
        z_on_head_mm=round(z_nozzle, 1),
        head_depth_mm=round(h_head, 1),
        zone=zone,
        geom_ok=geom_ok,
        code_ok=code_ok,
        nozzle_OR_mm=round(nozzle_OR, 1),
        edge_to_shell_mm=round(edge_to_shell, 1),
        edge_to_knuckle_mm=round(edge_to_knuckle, 1) if edge_to_knuckle is not None else None,
        r_crown_end_mm=round(r_crown_end, 1) if r_crown_end is not None else None,
        z_crown_end_mm=round(z_crown_end, 1) if z_crown_end is not None else None,
        d_at_crown_end_mm=round(d_at_crown_end, 1) if d_at_crown_end is not None else None,
        warnings=warnings,
        errors=errors,
        geometry=geom,
    )
