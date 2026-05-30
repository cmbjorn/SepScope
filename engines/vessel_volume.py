"""
Horizontal vessel partial-fill volume calculator.

Integrates circular-segment areas along the head axis (trapezoidal rule)
to compute fill volumes for any supported endcap type at an arbitrary
liquid level. Results are in mm³, m³, and litres.
"""
from __future__ import annotations
import math
from .head_geometry import HeadType, _FD_CROWN_RATIO, _FD_KNUCKLE_RATIO
from .nozzle_geometry import _tori_geometry


def _seg_area(R: float, h: float) -> float:
    """Area of a circular segment of radius R filled to height h from bottom."""
    if h <= 0.0:
        return 0.0
    if h >= 2.0 * R:
        return math.pi * R * R
    rh = R - h
    return R * R * math.acos(rh / R) - rh * math.sqrt(max(0.0, 2.0 * R * h - h * h))


def _head_r_profile(
    head_type: HeadType,
    Di: float,
    R_c: float,
    r_k: float,
    alpha_deg: float,
    b: float,
    N: int = 400,
) -> tuple[list[float], list[float]]:
    """
    Inner cross-section radius r at each axial position z along the head.
    z = 0 at tangent line, z decreases toward the pole.
    Returns (z_list, r_list).
    """
    R = Di / 2.0

    if head_type == HeadType.FLAT:
        return [0.0, 0.0], [R, R]   # zero-depth; volume comes from cylinder only

    if head_type == HeadType.FLANGED_DISHED:
        head_type = HeadType.TORISPHERICAL
        R_c = _FD_CROWN_RATIO * Di
        r_k = _FD_KNUCKLE_RATIO * Di

    if head_type == HeadType.HEMISPHERICAL:
        zs = [-R * i / N for i in range(N + 1)]
        rs = [math.sqrt(max(0.0, R * R - z * z)) for z in zs]
        return zs, rs

    if head_type == HeadType.ELLIPSOIDAL:
        zs = [-b * i / N for i in range(N + 1)]
        rs = [R * math.sqrt(max(0.0, 1.0 - (z / b) ** 2)) for z in zs]
        return zs, rs

    if head_type == HeadType.TORISPHERICAL:
        tg = _tori_geometry(Di, R_c, r_k)
        h_head   = tg["h_head"]
        r_cj     = tg["r_cj"]
        z_cj     = tg["z_cj"]
        Z_sc     = tg["Z_sc"]
        x_kc     = R - r_k
        angle_j  = math.asin(min(1.0, r_cj / R_c))
        N1 = max(2, int(N * z_cj / max(h_head, 1e-9)))
        N2 = N - N1
        zs: list[float] = []
        rs: list[float] = []
        for i in range(N1 + 1):
            ang = angle_j * i / N1
            zs.append(-(Z_sc + R_c * math.cos(ang)))
            rs.append(R_c * math.sin(ang))
        theta_j = math.atan2(z_cj, r_cj - x_kc)
        for i in range(1, N2 + 1):
            theta = theta_j * (1.0 - i / N2)
            zs.append(-(r_k * math.sin(theta)))
            rs.append(x_kc + r_k * math.cos(theta))
        return zs, rs

    if head_type == HeadType.CONICAL:
        alpha_rad = math.radians(alpha_deg)
        h_head = R / math.tan(alpha_rad)
        zs = [-h_head * i / N for i in range(N + 1)]
        rs = [R * (1.0 - i / N) for i in range(N + 1)]
        return zs, rs

    return [0.0, 0.0], [R, R]


def _head_fill_vol(
    head_type: HeadType,
    Di: float,
    h_fill: float,
    R_c_ratio: float,
    r_k_ratio: float,
    alpha_deg: float,
    b: float,
    N: int = 400,
) -> float:
    """
    Partial-fill volume of ONE endcap at liquid height h_fill (0 ≤ h_fill ≤ Di).

    At axial position z the cross-section is a circle of radius r(z) centred on
    the vessel axis. The local fill height in that circle is h_fill - R + r(z),
    where R = Di/2 (the vessel inner radius). Integrates with the trapezoidal rule.
    """
    if head_type == HeadType.FLAT:
        return 0.0

    R = Di / 2.0
    zs, rs = _head_r_profile(
        head_type, Di,
        R_c_ratio * Di, r_k_ratio * Di,
        alpha_deg, b, N=N,
    )

    vol = 0.0
    for i in range(1, len(zs)):
        dz = abs(zs[i] - zs[i - 1])
        r0, r1 = rs[i - 1], rs[i]
        A0 = _seg_area(r0, h_fill - R + r0)
        A1 = _seg_area(r1, h_fill - R + r1)
        vol += 0.5 * (A0 + A1) * dz
    return vol


def vessel_volumes(
    head_type: HeadType,
    Di: float,
    L_shell: float,
    levels_mm: dict[str, float],
    crown_ratio: float = 1.0,
    knuckle_ratio: float = 0.1,
    alpha_deg_cone: float = 30.0,
    ellipse_ratio: float = 2.0,
    include_heads: bool = True,
) -> dict:
    """
    Compute fill volumes at each level for a horizontal cylindrical vessel.

    Parameters
    ----------
    Di          : inner diameter (mm)
    L_shell     : cylinder length tangent-to-tangent (mm)
    levels_mm   : {tag: height_from_bottom_inner_wall_mm}
    include_heads : if True, add both endcap volumes

    Returns
    -------
    dict with keys:
        total_m3, total_L               — full vessel
        shell_m3, shell_L               — cylinder only
        heads_m3, heads_L               — both heads combined
        levels                          — list of per-level dicts (sorted low→high)
    """
    R = Di / 2.0
    b = Di / (2.0 * ellipse_ratio)

    V_cyl_full  = _seg_area(R, Di) * L_shell
    V_head_full = 2.0 * _head_fill_vol(
        head_type, Di, Di,
        crown_ratio, knuckle_ratio, alpha_deg_cone, b,
    )
    V_total = V_cyl_full + (V_head_full if include_heads else 0.0)

    rows = []
    prev_vol = 0.0
    for tag, h in sorted(levels_mm.items(), key=lambda kv: kv[1]):
        h = max(0.0, min(Di, h))
        V_cyl  = _seg_area(R, h) * L_shell
        V_head = 2.0 * _head_fill_vol(
            head_type, Di, h,
            crown_ratio, knuckle_ratio, alpha_deg_cone, b,
        )
        vol = V_cyl + (V_head if include_heads else 0.0)
        rows.append({
            "tag":      tag,
            "h_mm":     h,
            "h_pct":    h / Di * 100.0,
            "vol_m3":   vol * 1e-9,
            "vol_L":    vol * 1e-6,
            "vol_pct":  vol / V_total * 100.0 if V_total > 0 else 0.0,
            "btw_m3":   (vol - prev_vol) * 1e-9,
            "btw_L":    (vol - prev_vol) * 1e-6,
        })
        prev_vol = vol

    return {
        "total_m3":  V_total * 1e-9,
        "total_L":   V_total * 1e-6,
        "shell_m3":  V_cyl_full * 1e-9,
        "shell_L":   V_cyl_full * 1e-6,
        "heads_m3":  V_head_full * 1e-9,
        "heads_L":   V_head_full * 1e-6,
        "levels":    rows,
    }
