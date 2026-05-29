"""
Pressure vessel head (endcap) geometry and thickness calculations.

Covers:
  - Hemispherical
  - Ellipsoidal (2:1 standard; custom a/b ratio)
  - Torispherical (dished) — standard Klöpper and custom r/D
  - Conical (including toriconical)
  - Flat (unstayed)

Design codes:
  EN 13445-3:2021  Clauses 7.4–7.7, 7.8
  ASME VIII Div.1  UG-32, UG-33

All dimensions in mm, pressures in MPa (bar × 0.1), stresses in MPa.
"""
from __future__ import annotations
import math
from enum import Enum
from dataclasses import dataclass, field


class HeadType(str, Enum):
    HEMISPHERICAL  = "Hemispherical"
    ELLIPSOIDAL    = "Ellipsoidal 2:1"
    TORISPHERICAL  = "Torispherical (dished)"
    CONICAL        = "Conical"
    FLAT           = "Flat (unstayed)"


@dataclass
class HeadGeometry:
    """Resolved geometric parameters for one head."""
    head_type: HeadType
    Di: float          # inner diameter of cylinder (mm)
    # Spherical / crown zone
    Ri: float          # inner radius of crown sphere (mm)  — equals Di/2 for hemi
    # Knuckle (torispherical only, else None)
    r_knuckle: float | None = None   # knuckle radius (mm)
    # Ellipsoidal
    h_ellipse: float | None = None   # semi-minor axis (mm) = Di/4 for 2:1
    # Conical
    alpha_deg: float | None = None   # half-apex angle (°)
    # Flat
    # (no extra geometry needed)

    # Derived zones
    def _tori_knuckle_depth(self) -> float:
        """
        Depth from pole to the knuckle centre (= depth to the head–cylinder tangent
        line, i.e. where the knuckle circle is tangent to the cylindrical shell).
        For torispherical only; result is only meaningful when self.r_knuckle is set.
        """
        r_k = self.r_knuckle
        R_c = self.Ri
        x_kc = self.Di / 2 - r_k
        # Tangency condition: dist(crown_centre, knuckle_centre) = R_c - r_k
        # Crown centre is on axis at depth R_c from pole.
        # sqrt(x_kc² + (z_kc − R_c)²) = R_c − r_k  →  solve for z_kc
        inner = (R_c - r_k) ** 2 - x_kc ** 2
        return R_c - math.sqrt(max(0.0, inner))   # z_kc (depth from pole)

    @property
    def crown_limit_mm(self) -> float | None:
        """
        Depth from the pole (vertical, mm) to the crown–knuckle junction.
        A nozzle centre at depth d_top ≤ crown_limit_mm is in the spherical crown zone.
        Returns None for head types that have no distinct knuckle.
        """
        if self.head_type == HeadType.TORISPHERICAL and self.r_knuckle is not None:
            R_c = self.Ri
            r_k = self.r_knuckle
            z_kc = self._tori_knuckle_depth()
            # Junction = crown_centre + R_c × unit(crown_centre → knuckle_centre)
            # crown_centre = (0, R_c) [depth-from-pole coords]
            # knuckle_centre = (Di/2 - r_k, z_kc)
            x_kc = self.Di / 2 - r_k
            dist = R_c - r_k   # distance between centres (tangency condition)
            # z-component of unit vector (downward positive):
            dz = z_kc - R_c
            z_cj = R_c + R_c * dz / dist   # depth of junction from pole
            return round(z_cj, 2)
        return None

    @property
    def knuckle_inner_radius_mm(self) -> float | None:
        """
        Radial distance (from vessel axis) to the crown–knuckle junction (mm).
        This is the x-coordinate of the junction point, i.e. the outermost radial
        extent of the purely spherical crown zone.
        """
        if self.r_knuckle is None:
            return None
        R_c = self.Ri
        r_k = self.r_knuckle
        z_kc = self._tori_knuckle_depth()
        x_kc = self.Di / 2 - r_k
        dist = R_c - r_k
        dx = x_kc - 0   # x-component of direction from crown centre to knuckle centre
        x_cj = 0 + R_c * dx / dist
        return round(x_cj, 2)

    def inside_crown_zone(self, d_top_mm: float) -> bool | None:
        """
        True  → nozzle centre is in the spherical crown zone
        False → in the knuckle or transition zone
        None  → head type has no distinct knuckle (question not applicable)

        d_top_mm : vertical distance from the pole (top of vessel) to nozzle centre.
        """
        lim = self.crown_limit_mm
        if lim is None:
            return None
        return d_top_mm <= lim


@dataclass
class HeadThicknessResult:
    head_type: HeadType
    Di: float
    P_MPa: float
    fd_MPa: float
    z: float                   # weld joint efficiency factor
    code: str
    t_calc_mm: float           # calculated minimum thickness (mm)
    t_nom_mm: float | None     # nominal thickness selected (≥ t_calc + CA)
    CA_mm: float               # corrosion allowance
    formula: str               # formula description
    clause: str                # code clause reference
    warnings: list[str] = field(default_factory=list)
    geometry: HeadGeometry | None = None


def head_geometry(
    head_type: HeadType,
    Di: float,
    crown_ratio: float = 1.0,     # Ri/Di for torispherical (0.8 typical; 0.5 for hemi)
    knuckle_ratio: float = 0.1,   # r/Di for torispherical (0.06 minimum per EN/ASME)
    alpha_deg: float = 30.0,      # half-apex for conical
    ellipse_ratio: float = 2.0,   # Di / (2*h) — 2.0 = standard 2:1
) -> HeadGeometry:
    """
    Build the HeadGeometry for any supported head type.

    For HEMISPHERICAL: Ri = Di/2
    For ELLIPSOIDAL:   Ri = Di²/(4h), h = Di/(2*ellipse_ratio)
    For TORISPHERICAL: Ri = crown_ratio * Di,  r = knuckle_ratio * Di
    For CONICAL:       alpha_deg defines the half-apex angle
    """
    if head_type == HeadType.HEMISPHERICAL:
        return HeadGeometry(head_type=head_type, Di=Di, Ri=Di / 2)

    elif head_type == HeadType.ELLIPSOIDAL:
        h = Di / (2 * ellipse_ratio)   # semi-minor axis
        # Equivalent crown sphere radius for a 2:1 ellipse
        # From the approximation used in ASME / EN: R_eq = Di²/(4h)
        Ri_eq = Di ** 2 / (4 * h)
        return HeadGeometry(head_type=head_type, Di=Di, Ri=Ri_eq, h_ellipse=h)

    elif head_type == HeadType.TORISPHERICAL:
        r_k = knuckle_ratio * Di
        R_c = crown_ratio   * Di
        return HeadGeometry(head_type=head_type, Di=Di, Ri=R_c, r_knuckle=r_k)

    elif head_type == HeadType.CONICAL:
        return HeadGeometry(head_type=head_type, Di=Di, Ri=float("inf"), alpha_deg=alpha_deg)

    else:  # FLAT
        return HeadGeometry(head_type=head_type, Di=Di, Ri=float("inf"))


def head_thickness(
    head_type: HeadType,
    Di: float,
    P_barg: float,
    fd_MPa: float,
    z: float = 1.0,
    CA_mm: float = 3.0,
    code: str = "EN",
    crown_ratio: float = 1.0,
    knuckle_ratio: float = 0.1,
    alpha_deg: float = 30.0,
    ellipse_ratio: float = 2.0,
    C_flat: float = 0.45,        # flat end coefficient (EN cl.10 / ASME UG-34)
) -> HeadThicknessResult:
    """
    Calculate minimum required head thickness.

    Parameters
    ----------
    P_barg          : design pressure (barg)
    fd_MPa          : allowable design stress (MPa)
    z               : weld joint efficiency (1.0 for full RT, 0.85 partial, etc.)
    CA_mm           : corrosion allowance (mm)
    code            : "EN" or "ASME"
    crown_ratio     : Ri/Di for torispherical crown (default 1.0 → Ri = Di)
    knuckle_ratio   : r/Di for torispherical knuckle (default 0.1 → r = 0.1Di)
    alpha_deg       : half-apex angle for conical (degrees)
    ellipse_ratio   : Di/(2h), 2.0 = standard 2:1 ellipse
    C_flat          : flat end coefficient

    Returns
    -------
    HeadThicknessResult
    """
    P = P_barg * 0.1          # bar → MPa
    geom = head_geometry(head_type, Di, crown_ratio, knuckle_ratio,
                         alpha_deg, ellipse_ratio)
    warnings: list[str] = []

    if head_type == HeadType.HEMISPHERICAL:
        # EN 13445-3 cl. 7.4 / ASME UG-32(f)
        # t = P * Di / (4 * fd * z - P)   (inside radius form)
        if code == "ASME":
            # ASME UG-32(f): t = P*R/(2*S*E - 0.2*P), R = Di/2
            R = Di / 2
            t = P * R / (2 * fd_MPa * z - 0.2 * P)
            clause = "ASME VIII-1 UG-32(f)"
        else:
            t = P * Di / (4 * fd_MPa * z - P)
            clause = "EN 13445-3 cl. 7.4"
        formula = f"t = P·Di / (4·fd·z − P) = {P:.3f}·{Di:.1f} / (4·{fd_MPa:.2f}·{z:.2f} − {P:.3f})"

    elif head_type == HeadType.ELLIPSOIDAL:
        # Equivalent sphere method: treat as torispherical with R = K*Di
        # K factor for 2:1 ellipse = 0.9 (ASME), or direct formula (EN cl.7.6)
        if code == "ASME":
            # UG-32(d): t = P*D/(2*S*E - 0.2*P) × K, K=1.0 for 2:1
            # For 2:1 standard: same as cylinder formula with K=1
            K = _asme_ellipsoidal_K(ellipse_ratio)
            t = P * Di * K / (2 * fd_MPa * z - 0.2 * P)
            clause = "ASME VIII-1 UG-32(d)"
            formula = f"t = P·Di·K / (2·S·E − 0.2·P), K={K:.4f}"
        else:
            # EN 13445-3 cl. 7.6: e = P*Di / (2*fd*z - 0.5*P) × beta
            # beta = 1/(2*sqrt(1 - (1-1/r^2)*(Di/2/Di*2)^2)) approximation
            # Simplified: use equivalent sphere R = K*Di
            h = Di / (2 * ellipse_ratio)
            # EN cl.7.6 exact formula: e_s = P*Di/(2*fd*z - P/2) * (1 - Di/4h*(1 - Di/4h))
            # Practical: use K = Di/(4h) for the correction
            K_en = Di / (4 * h)     # = ellipse_ratio / 2; for 2:1, K=1.0
            t = P * Di / (2 * fd_MPa * z - 0.5 * P) * K_en
            clause = "EN 13445-3 cl. 7.6"
            formula = f"t = P·Di·K / (2·fd·z − 0.5·P), K={K_en:.4f} (h={h:.1f} mm)"

    elif head_type == HeadType.TORISPHERICAL:
        r_k = knuckle_ratio * Di
        R_c = crown_ratio   * Di
        if r_k < 0.06 * Di:
            warnings.append(f"Knuckle radius r={r_k:.1f} mm < 0.06·Di={0.06*Di:.1f} mm. "
                            "Code minimum is 0.06·Di.")
        if R_c > Di:
            warnings.append(f"Crown radius R={R_c:.1f} mm > Di={Di:.1f} mm. "
                            "Not typical; verify.")
        if code == "ASME":
            # UG-32(e): t = 0.885*P*L / (S*E - 0.1*P),  L = crown radius
            t = 0.885 * P * R_c / (fd_MPa * z - 0.1 * P)
            clause = "ASME VIII-1 UG-32(e)"
            formula = (f"t = 0.885·P·L / (S·E − 0.1·P) = "
                       f"0.885·{P:.3f}·{R_c:.1f} / ({fd_MPa:.2f}·{z:.2f} − 0.1·{P:.3f})")
        else:
            # EN 13445-3 cl. 7.5.3: e = P*R/(2*fd*z - 0.5*P) with buckling check
            t = P * R_c / (2 * fd_MPa * z - 0.5 * P)
            clause = "EN 13445-3 cl. 7.5.3"
            formula = (f"t = P·R / (2·fd·z − 0.5·P) = "
                       f"{P:.3f}·{R_c:.1f} / (2·{fd_MPa:.2f}·{z:.2f} − 0.5·{P:.3f})")
        # Buckling / shape check: thickness must be ≥ 0.001*Di for typical r/R
        t_min_shape = 0.001 * Di
        if t < t_min_shape:
            warnings.append(f"Calculated t={t:.2f} mm < 0.001·Di={t_min_shape:.2f} mm. "
                            "Check for elastic buckling of crown zone.")

    elif head_type == HeadType.CONICAL:
        alpha = math.radians(alpha_deg)
        if code == "ASME":
            # UG-32(g): t = P*D / (2*cos(α)*(S*E - 0.6*P)), D = large end Di
            t = P * Di / (2 * math.cos(alpha) * (fd_MPa * z - 0.6 * P))
            clause = "ASME VIII-1 UG-32(g)"
        else:
            # EN 13445-3 cl. 7.6: e = P*Di / (2*fd*z*cos(α) - P)
            t = P * Di / (2 * fd_MPa * z * math.cos(alpha) - P)
            clause = "EN 13445-3 cl. 7.7"
        if alpha_deg > 60:
            warnings.append(f"Half-apex angle {alpha_deg}° > 60° — standard cone formula "
                            "may not apply. Check reinforcement at cone-to-shell junction.")
        formula = (f"t = P·Di / (2·cos(α)·(fd·z − 0.6·P)), α={alpha_deg}° = "
                   f"{P:.3f}·{Di:.1f} / (2·{math.cos(alpha):.4f}·({fd_MPa:.2f}·{z:.2f}))")

    else:  # FLAT
        # EN 13445-3 cl. 10 / ASME UG-34
        # e = C * Di * sqrt(P / fd)
        t = C_flat * Di * math.sqrt(P / fd_MPa)
        clause = "EN 13445-3 cl. 10 / ASME UG-34"
        formula = f"t = C·Di·√(P/fd) = {C_flat:.3f}·{Di:.1f}·√({P:.3f}/{fd_MPa:.2f})"

    t_nom = math.ceil((t + CA_mm) * 2) / 2  # round up to next 0.5 mm
    if fd_MPa <= 0:
        warnings.append("Allowable stress is zero or negative — check inputs.")
    if P >= 2 * fd_MPa * z:
        warnings.append("Design pressure ≥ 2·fd·z — shell formula is invalid. "
                        "Reduce pressure or increase material grade.")

    return HeadThicknessResult(
        head_type=head_type, Di=Di, P_MPa=P, fd_MPa=fd_MPa, z=z,
        code=code, t_calc_mm=round(t, 3), t_nom_mm=t_nom,
        CA_mm=CA_mm, formula=formula, clause=clause,
        warnings=warnings, geometry=geom,
    )


def _asme_ellipsoidal_K(ratio: float) -> float:
    """
    K factor for ASME UG-32(d) ellipsoidal head.
    ratio = Di / (2*h) — 2.0 for standard 2:1.
    K = (2 + ratio²) / 6
    """
    return (2 + ratio ** 2) / 6
