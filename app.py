"""
VesselCalc — Pressure vessel design screener (horizontal vessel).

Evaluates nozzle placement on endcaps per EN 13445-3:2021 and ASME VIII Div.1.
"""
import math
import streamlit as st
import plotly.graph_objects as go

from engines import (
    MATERIALS, allowable_stress,
    HeadType, head_geometry, head_thickness,
    shell_thickness, nozzle_on_head, reinforcement_check,
    separator_check,
    gas_properties, liquid_properties, FluidProps, GAS_FLUIDS, LIQ_FLUIDS,
)
from engines.nozzle_geometry import (
    NOZZLE_OD, NOZZLE_WALL_T, _tori_geometry,
    NOZZLE_WALL_SCH, recommended_schedule,
)
from engines.head_geometry import _FD_CROWN_RATIO, _FD_KNUCKLE_RATIO
from engines.vessel_volume import vessel_volumes
from standards import DN_SIZES, EN_PN_RATINGS, ASME_CLASS_PRESSURE_20C, max_pn_for_temperature

# Level tag visual styles: (line-colour, dash-style, line-width)
_LEVEL_STYLE: dict[str, tuple[str, str, float]] = {
    "LZLL": ("#4b5563", "dot",   1.5),
    "LALL": ("#dc2626", "dash",  1.5),
    "LAL":  ("#f97316", "dash",  1.5),
    "NLL":  ("#2563eb", "solid", 2.2),
    "LAH":  ("#f97316", "dash",  1.5),
    "LAHH": ("#dc2626", "dash",  1.5),
    "LZHH": ("#4b5563", "dot",   1.5),
}

_NOZZLE_SERVICES = [
    "Inlet", "Gas outlet", "Liquid outlet",
    "Drain", "Vent", "Purge",
    "PSV", "Pressure transmitter", "Pressure indicator", "Pressure trip",
    "Level transmitter", "Level trip", "Level gauge",
    "Temperature transmitter",
    "Manway", "Spare",
]

_NOZZLE_LOCS = [
    "Left head", "Right head",
    "Shell — top", "Shell — bottom", "Shell — side",
]

def _loc_y(loc: str, R: float) -> float:
    """Signed y-coordinate (from vessel axis) for a shell nozzle location."""
    if loc == "Shell — top":    return  R
    if loc == "Shell — bottom": return -R
    return 0.0

def _default_nozzles(Di: float, L_shell: float) -> list[dict]:
    """
    Typical horizontal two-phase separator nozzle list.
    Inlets high on endcaps (20% from top). Process outlets at shell centre.
    Instruments spaced to avoid OD overlaps.
    """
    pn = 25
    L  = L_shell
    D  = Di
    c  = L / 2
    return [
        # ── Process inlets — high on endcaps (20 % from top) ─────────────────
        {"tag": "N1",  "service": "Inlet",                "loc": "Left head",      "dn": 250, "pn": pn, "d_from_top": D * 0.20, "axial_mm": c},
        {"tag": "N2",  "service": "Inlet",                "loc": "Right head",     "dn": 250, "pn": pn, "d_from_top": D * 0.20, "axial_mm": c},
        # ── Process outlets — centre of shell ─────────────────────────────────
        {"tag": "GO",  "service": "Gas outlet",           "loc": "Shell — top",    "dn": 100, "pn": pn, "d_from_top": D / 2,    "axial_mm": c},
        {"tag": "LO",  "service": "Liquid outlet",        "loc": "Shell — bottom", "dn": 200, "pn": pn, "d_from_top": D / 2,    "axial_mm": c},
        # ── Access / safety ───────────────────────────────────────────────────
        {"tag": "MH",  "service": "Manway",               "loc": "Shell — top",    "dn": 600, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.20},
        {"tag": "PSV", "service": "PSV",                  "loc": "Shell — top",    "dn": 100, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.82},
        # ── Drain & vent ──────────────────────────────────────────────────────
        {"tag": "D1",  "service": "Drain",                "loc": "Shell — bottom", "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.08},
        {"tag": "V1",  "service": "Vent",                 "loc": "Shell — top",    "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.04},
        {"tag": "PG",  "service": "Purge",                "loc": "Shell — top",    "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.93},
        # ── Pressure instruments — sides, spread left & right ─────────────────
        {"tag": "PT1", "service": "Pressure transmitter", "loc": "Shell — side",   "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.13},
        {"tag": "PSH", "service": "Pressure trip",        "loc": "Shell — side",   "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.30},
        {"tag": "PI1", "service": "Pressure indicator",   "loc": "Shell — side",   "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.80},
        # ── Level instruments — centred on vessel, both sides ─────────────────
        {"tag": "LT1", "service": "Level transmitter",    "loc": "Shell — side",   "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.42},
        {"tag": "LGA", "service": "Level gauge",          "loc": "Shell — side",   "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.47},
        {"tag": "LGB", "service": "Level gauge",          "loc": "Shell — side",   "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.53},
        {"tag": "LSH", "service": "Level trip",           "loc": "Shell — side",   "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.58},
        # ── Temperature — bottom, in liquid ───────────────────────────────────
        {"tag": "TT1", "service": "Temperature transmitter", "loc": "Shell — bottom", "dn": 50, "pn": pn, "d_from_top": D / 2,  "axial_mm": L * 0.38},
        # ── Spare ─────────────────────────────────────────────────────────────
        {"tag": "SP1", "service": "Spare",                "loc": "Shell — top",    "dn":  50, "pn": pn, "d_from_top": D / 2,    "axial_mm": L * 0.97},
    ]

st.set_page_config(
    page_title="VesselCalc",
    page_icon="🔩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────── HEAD PROFILE GEOMETRY ───────────────────────────────

def _head_surface_points(
    head_type: HeadType, Di: float, R_c: float, r_k: float,
    alpha_deg: float, b: float, N: int = 120,
) -> tuple[list[float], list[float]]:
    """
    Upper-half head inner surface for a horizontal side-view diagram.

    Returns (z_list, y_list):
      z : 0 at tangent line; negative = into head toward pole
      y : 0 = vessel axis; R = top inner wall
    Profile goes from pole (z=−h_head, y=0) to tangent (z=0, y=R).
    """
    R = Di / 2
    zs: list[float] = []
    ys: list[float] = []

    # F&D is torispherical with fixed ratios — normalise before drawing
    if head_type == HeadType.FLANGED_DISHED:
        head_type   = HeadType.TORISPHERICAL
        R_c = _FD_CROWN_RATIO   * Di
        r_k = _FD_KNUCKLE_RATIO * Di

    if head_type == HeadType.HEMISPHERICAL:
        for i in range(N + 1):
            ang = math.pi / 2 * i / N   # 0 at pole, π/2 at tangent
            y = R * math.sin(ang)
            z_actual = R * math.cos(ang)
            zs.append(-z_actual)
            ys.append(y)

    elif head_type == HeadType.ELLIPSOIDAL:
        for i in range(N + 1):
            ang = math.pi / 2 * i / N
            y = R * math.sin(ang)
            z_actual = b * math.cos(ang)
            zs.append(-z_actual)
            ys.append(y)

    elif head_type == HeadType.TORISPHERICAL:
        tg = _tori_geometry(Di, R_c, r_k)
        h_head = tg["h_head"]
        r_cj = tg["r_cj"]
        z_cj = tg["z_cj"]
        Z_sc = tg["Z_sc"]
        x_kc = R - r_k

        # Crown arc: pole → junction
        angle_junc = math.asin(min(1.0, r_cj / R_c))
        N1 = max(2, int(N * z_cj / max(h_head, 1e-6)))
        for i in range(N1 + 1):
            ang = angle_junc * i / N1
            y = R_c * math.sin(ang)
            z_actual = Z_sc + R_c * math.cos(ang)
            zs.append(-z_actual)
            ys.append(y)

        # Knuckle arc: junction → tangent
        N2 = N - N1
        theta_junc = math.atan2(z_cj, r_cj - x_kc)
        for i in range(1, N2 + 1):
            frac = i / N2
            theta = theta_junc * (1.0 - frac)
            y = x_kc + r_k * math.cos(theta)
            z_actual = r_k * math.sin(theta)
            zs.append(-z_actual)
            ys.append(y)

    elif head_type == HeadType.CONICAL:
        alpha_rad = math.radians(alpha_deg)
        h_head = R / math.tan(alpha_rad)
        for i in range(N + 1):
            frac = i / N
            y = R * frac
            z_actual = h_head * (1.0 - frac)
            zs.append(-z_actual)
            ys.append(y)

    else:  # FLAT
        zs = [0.0, 0.0]
        ys = [0.0, R]

    return zs, ys


def _vessel_figure(
    head_type: HeadType,
    Di: float,
    R_c: float, r_k: float, alpha_deg: float, b: float,
    t_head_nom: float,
    t_shell_nom: float,
    nozzle_results: list,        # list of (nozzle_dict, nres|None, rres)
    L_shell: float,
    levels_mm: dict[str, float] | None = None,
    L_baffle_mm: float = 0.0,
    saddle_a_mm: float = 0.0,
    saddle_w_mm: float = 250.0,
    # internals
    has_baffles: bool = True,
    baffle_open_pct: float = 20.0,
    has_inlet_dev: bool = True,
    has_meshpad: bool = True,
    nll_mm: float = 0.0,        # needed to position mesh pad (from vessel axis: nll - R)
    has_vortex_brk: bool = True,
    nozzle_checks: dict | None = None,
) -> go.Figure:
    """Horizontal side-view: both heads + full cylinder shell.

    Internals such as inlet devices, mesh pads, and vortex breakers are not
    rendered in the figure. Only baffle plates are shown in the sketch.
    """
    R = Di / 2
    # F&D is drawn identically to torispherical with its fixed ratios
    if head_type == HeadType.FLANGED_DISHED:
        head_type = HeadType.TORISPHERICAL
        R_c = _FD_CROWN_RATIO   * Di
        r_k = _FD_KNUCKLE_RATIO * Di

    zs_upper, ys_upper = _head_surface_points(head_type, Di, R_c, r_k, alpha_deg, b)
    h_head = max((abs(z) for z in zs_upper), default=0.0)

    # Weld clearance minimum (for exclusion zone overlay)
    min_weld_clr = max(3.0 * t_head_nom, 25.0) if t_head_nom > 0 else 25.0
    r_weld_boundary = R - min_weld_clr   # nozzle OD edge must stay inside this radius

    fig = go.Figure()

    # ── Zone fills — both heads (right head = mirror: x_right = L_shell − x_left) ─
    def _mirror(xs: list) -> list:
        return [L_shell - x for x in xs]

    if head_type == HeadType.TORISPHERICAL:
        tg = _tori_geometry(Di, R_c, r_k)
        r_cj = tg["r_cj"]
        z_cj = tg["z_cj"]
        Z_sc = tg["Z_sc"]
        x_kc = R - r_k
        angle_junc = math.asin(min(1.0, r_cj / R_c))
        theta_junc = math.atan2(z_cj, r_cj - x_kc)
        N_z = 80
        N1 = max(2, int(N_z * z_cj / max(h_head, 1e-6)))
        N2 = N_z - N1

        cz = [-(Z_sc + R_c * math.cos(angle_junc * i / N1)) for i in range(N1 + 1)]
        cy = [R_c * math.sin(angle_junc * i / N1)            for i in range(N1 + 1)]
        kz, ky = [], []
        for i in range(N2 + 1):
            th = theta_junc * (1.0 - i / N2)
            kz.append(-(r_k * math.sin(th)))
            ky.append(x_kc + r_k * math.cos(th))

        crown_xs = cz + list(reversed(cz))
        crown_ys = cy + [-y for y in reversed(cy)]
        knuck_xs = kz + list(reversed(kz))
        knuck_ys = ky + [-y for y in reversed(ky)]

        for mirror in (False, True):
            mx = _mirror if mirror else (lambda v: v)
            fig.add_trace(go.Scatter(
                x=mx(crown_xs), y=crown_ys,
                fill="toself", fillcolor="rgba(34,197,94,0.22)",
                line=dict(color="rgba(0,0,0,0)", width=0),
                name="Crown — nozzle permitted" if not mirror else None,
                showlegend=not mirror, hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=mx(knuck_xs), y=knuck_ys,
                fill="toself", fillcolor="rgba(245,158,11,0.25)",
                line=dict(color="rgba(0,0,0,0)", width=0),
                name="Knuckle — non-standard placement" if not mirror else None,
                showlegend=not mirror, hoverinfo="skip",
            ))
            bx = -z_cj if not mirror else L_shell + z_cj
            fig.add_shape(type="line", x0=bx, x1=bx, y0=-r_cj, y1=r_cj,
                          line=dict(color="#16a34a", width=1.8, dash="dash"))
            mid_c = -(h_head + z_cj) / 2 if not mirror else L_shell + (h_head + z_cj) / 2
            mid_k = -z_cj / 2            if not mirror else L_shell + z_cj / 2
            fig.add_annotation(x=mid_c, y=0, text="Crown",
                               showarrow=False, font=dict(size=10, color="#15803d"),
                               bgcolor="rgba(255,255,255,0.55)", borderpad=2)
            for sy in ((r_cj + R) / 2, -(r_cj + R) / 2):
                fig.add_annotation(x=mid_k, y=sy, text="Knuckle",
                                   showarrow=False, font=dict(size=9, color="#b45309"),
                                   bgcolor="rgba(255,255,255,0.55)", borderpad=2)

    elif head_type == HeadType.ELLIPSOIDAL:
        _k = max(Di / (2.0 * b), 1.001)
        r_rev = R / math.sqrt(_k * _k - 1.0)
        z_rev = b * math.sqrt(max(0.0, 1.0 - (r_rev / R) ** 2))
        N_e = 80
        t_rev = math.asin(min(1.0, r_rev / R))

        def _ellipse_arc(t0, t1, n):
            pts_z, pts_y = [], []
            for i in range(n + 1):
                t = t0 + (t1 - t0) * i / n
                pts_y.append(R * math.sin(t))
                pts_z.append(-b * math.cos(t))
            return pts_z, pts_y

        n1 = max(2, int(N_e * t_rev / (math.pi / 2)))
        n2 = max(2, N_e - n1)
        cz, cy = _ellipse_arc(0, t_rev, n1)
        pz, py = _ellipse_arc(t_rev, math.pi / 2, n2)

        crown_xs = cz + list(reversed(cz))
        crown_ys = cy + [-y for y in reversed(cy)]
        peri_xs  = pz + list(reversed(pz))
        peri_ys  = py + [-y for y in reversed(py)]

        for mirror in (False, True):
            mx = _mirror if mirror else (lambda v: v)
            fig.add_trace(go.Scatter(
                x=mx(crown_xs), y=crown_ys,
                fill="toself", fillcolor="rgba(34,197,94,0.22)",
                line=dict(color="rgba(0,0,0,0)", width=0),
                name="Crown equiv. — nozzle permitted" if not mirror else None,
                showlegend=not mirror, hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=mx(peri_xs), y=peri_ys,
                fill="toself", fillcolor="rgba(245,158,11,0.25)",
                line=dict(color="rgba(0,0,0,0)", width=0),
                name="Compressive-stress zone — detailed check needed" if not mirror else None,
                showlegend=not mirror, hoverinfo="skip",
            ))
            bx = -z_rev if not mirror else L_shell + z_rev
            fig.add_shape(type="line", x0=bx, x1=bx, y0=-r_rev, y1=r_rev,
                          line=dict(color="#16a34a", width=1.8, dash="dash"))
            mid_c = -(b + z_rev) / 2 if not mirror else L_shell + (b + z_rev) / 2
            mid_p = -z_rev / 2        if not mirror else L_shell + z_rev / 2
            fig.add_annotation(x=mid_c, y=0, text="Crown",
                               showarrow=False, font=dict(size=10, color="#15803d"),
                               bgcolor="rgba(255,255,255,0.55)", borderpad=2)
            for sy in ((r_rev + R) / 2, -(r_rev + R) / 2):
                fig.add_annotation(x=mid_p, y=sy, text="Compressive",
                                   showarrow=False, font=dict(size=9, color="#b45309"),
                                   bgcolor="rgba(255,255,255,0.55)", borderpad=2)

    elif head_type != HeadType.FLAT:
        full_xs = zs_upper + list(reversed(zs_upper))
        full_ys = ys_upper + [-y for y in reversed(ys_upper)]
        for mirror in (False, True):
            mx = _mirror if mirror else (lambda v: v)
            fig.add_trace(go.Scatter(
                x=mx(full_xs), y=full_ys,
                fill="toself", fillcolor="rgba(34,197,94,0.18)",
                line=dict(color="rgba(0,0,0,0)", width=0),
                name="Full head — nozzle permitted" if not mirror else None,
                showlegend=not mirror, hoverinfo="skip",
            ))

    # ── Weld exclusion zone — both heads ─────────────────────────────────────
    if h_head > 0 and r_weld_boundary > 0:
        excl_reach = min(L_shell * 0.25, L_shell)
        for sign in (1, -1):
            # Left head side
            fig.add_shape(type="line",
                          x0=-h_head, x1=excl_reach,
                          y0=sign * r_weld_boundary, y1=sign * r_weld_boundary,
                          line=dict(color="rgba(220,38,38,0.55)", width=1.2, dash="dot"))
            # Right head side (mirrored)
            fig.add_shape(type="line",
                          x0=L_shell + h_head, x1=L_shell - excl_reach,
                          y0=sign * r_weld_boundary, y1=sign * r_weld_boundary,
                          line=dict(color="rgba(220,38,38,0.55)", width=1.2, dash="dot"))
        fig.add_annotation(
            x=-h_head * 0.5, y=r_weld_boundary + 12,
            text=f"Weld excl. ≥ {min_weld_clr:.0f} mm",
            showarrow=False, xanchor="center", yanchor="bottom",
            font=dict(size=8, color="#dc2626"),
            bgcolor="rgba(255,255,255,0.6)", borderpad=2,
        )
        fig.add_annotation(
            x=L_shell + h_head * 0.5, y=r_weld_boundary + 12,
            text=f"Weld excl. ≥ {min_weld_clr:.0f} mm",
            showarrow=False, xanchor="center", yanchor="bottom",
            font=dict(size=8, color="#dc2626"),
            bgcolor="rgba(255,255,255,0.6)", borderpad=2,
        )

    # ── Cylinder inner walls ──────────────────────────────────────────────────
    for sign in (1, -1):
        fig.add_trace(go.Scatter(
            x=[0.0, L_shell], y=[sign * R, sign * R],
            mode="lines", line=dict(color="#2563eb", width=2.5),
            name="Shell inner wall" if sign == 1 else None,
            showlegend=(sign == 1), hoverinfo="skip",
        ))

    # ── Left head inner surface (full cross-section) ─────────────────────────
    full_z = zs_upper + list(reversed(zs_upper))
    full_y = ys_upper + [-y for y in reversed(ys_upper)]
    fig.add_trace(go.Scatter(
        x=full_z, y=full_y,
        mode="lines", line=dict(color="#2563eb", width=2.5),
        name="Head inner surface", hoverinfo="skip",
    ))

    # ── Right head inner surface (mirror of left) ─────────────────────────────
    zs_right = [L_shell - z for z in zs_upper]
    fig.add_trace(go.Scatter(
        x=zs_right + list(reversed(zs_right)),
        y=full_y,
        mode="lines", line=dict(color="#2563eb", width=2.5),
        showlegend=False, hoverinfo="skip",
    ))

    # ── Outer walls (approximate) ─────────────────────────────────────────────
    if t_shell_nom > 0:
        for sign in (1, -1):
            fig.add_trace(go.Scatter(
                x=[0.0, L_shell],
                y=[sign * (R + t_shell_nom), sign * (R + t_shell_nom)],
                mode="lines",
                line=dict(color="#93c5fd", width=1.5, dash="dot"),
                name="Shell outer wall" if sign == 1 else None,
                showlegend=(sign == 1), hoverinfo="skip",
            ))

    # ── Tangent lines and centreline ─────────────────────────────────────────
    fig.add_vline(x=0,       line=dict(color="#94a3b8", dash="dot", width=1))
    fig.add_vline(x=L_shell, line=dict(color="#94a3b8", dash="dot", width=1))
    fig.add_hline(y=0,       line=dict(color="#e2e8f0", width=1, dash="dot"))

    # ── Nozzles ───────────────────────────────────────────────────────────────
    # Convention:
    #   Head nozzles       → rectangular stub projecting axially outward
    #   Shell top/bottom   → rectangular stub projecting radially (engineering elevation style)
    #   Shell side         → concentric circles at centreline (end-on view, they project ⊥ to page)
    theta_pts = [i / 30 * 2 * math.pi for i in range(31)]

    # Pre-compute max nozzle protrusion above/below vessel for dynamic y_lim (set later).
    _y_nz_top = R    # highest point of any nozzle or label above vessel axis
    _y_nz_bot = -R   # lowest point

    def _nozzle_w(nOR_mm: float) -> float:
        """Display half-width for a nozzle stub — capped so large nozzles stay legible."""
        return min(nOR_mm, Di * 0.045)

    for nz_cfg, nres, rres in nozzle_results:
        loc = nz_cfg["loc"]
        dn  = nz_cfg["dn"]
        nOR = NOZZLE_OD.get(dn, dn * 1.05) / 2.0

        # ── Status colour ─────────────────────────────────────────────────────
        geom_ok  = nres.geom_ok if nres else True
        code_ok  = nres.code_ok if nres else None
        reinf_ok = rres.adequate if rres else True
        # External checks mapping may override the visual severity for a nozzle
        sev = None
        if nozzle_checks and nz_cfg.get("tag") in nozzle_checks:
            sev = nozzle_checks.get(nz_cfg.get("tag"))
        if sev == "error":
            nc, nfill = "#dc2626", "rgba(220,38,38,0.22)"
        elif sev == "warning":
            nc, nfill = "#d97706", "rgba(217,119,6,0.22)"
        else:
            if not geom_ok or reinf_ok is False:
                nc, nfill = "#dc2626", "rgba(220,38,38,0.22)"
            elif code_ok is False or reinf_ok is None:
                nc, nfill = "#d97706", "rgba(217,119,6,0.22)"
            else:
                nc, nfill = "#16a34a", "rgba(22,163,74,0.22)"

        hover = (
            f"<b>{nz_cfg['tag']}</b> — {nz_cfg['service']}<br>"
            f"DN{dn}  |  {loc}"
        )

        if loc in ("Left head", "Right head") and nres is not None:
            # ── Head nozzle: rectangular stub projecting axially outward ──────
            nx   = -nres.z_on_head_mm if loc == "Left head" else L_shell + nres.z_on_head_mm
            ny   = nres.y_nozzle_mm
            hw   = _nozzle_w(nres.nozzle_OR_mm)    # half-width (capped)
            sign = -1.0 if loc == "Left head" else 1.0
            stub = max(hw * 2.0, 50.0)
            x_tip = nx + sign * stub
            hover += (
                f"<br>From top: {nres.d_from_top_mm:.0f} mm"
                f"<br>Zone: {nres.zone}"
            )
            # Nozzle body (rectangle)
            bx0, bx1 = min(nx, x_tip), max(nx, x_tip)
            fig.add_trace(go.Scatter(
                x=[bx0, bx1, bx1, bx0, bx0],
                y=[ny - hw, ny - hw, ny + hw, ny + hw, ny - hw],
                fill="toself", fillcolor="rgba(255,255,255,0.95)",
                line=dict(color=nc, width=2.8),
                showlegend=False, hovertemplate=hover + "<extra></extra>",
            ))
            # Flange face (bold line at tip)
            fig.add_shape(type="line", x0=x_tip, x1=x_tip,
                          y0=ny - hw - 6, y1=ny + hw + 6,
                          line=dict(color=nc, width=4))
            # Nozzle opening marker
            fig.add_trace(go.Scatter(
                x=[x_tip], y=[ny], mode="markers",
                marker=dict(size=min(11.0, hw * 1.9), color="white",
                            line=dict(color=nc, width=2.4)),
                showlegend=False, hoverinfo="skip",
            ))
            # Pulsing halo for problem nozzles (warning -> orange, error -> red)
            if sev in ("warning", "error"):
                pulse_col = "#d97706" if sev == "warning" else "#dc2626"
                fig.add_trace(go.Scatter(
                    x=[x_tip], y=[ny], mode="markers",
                    marker=dict(size=min(40.0, hw * 6.0), color=pulse_col, opacity=0.0),
                    showlegend=False, hoverinfo="skip",
                ))
            # Tag label outside
            fig.add_annotation(
                x=x_tip + sign * 12, y=ny,
                text=f"<b>{nz_cfg['tag']}</b>",
                showarrow=False,
                xanchor="left" if sign > 0 else "right", yanchor="middle",
                font=dict(size=9, color=nc),
                bgcolor="rgba(255,255,255,0.75)", borderpad=1,
            )

        elif loc in ("Shell — top", "Shell — bottom"):
            # ── Shell top/bottom: rectangular stub (elevation view) ───────────
            nx     = nz_cfg["axial_mm"]
            sign   = 1.0 if loc == "Shell — top" else -1.0
            y_wall = sign * R
            hw     = _nozzle_w(nOR)
            stub   = max(hw * 2.0, 45.0)
            y_tip  = y_wall + sign * stub
            # Nozzle body (rectangle, drawn as Scatter so it renders above zone fills)
            fig.add_trace(go.Scatter(
                x=[nx - hw, nx + hw, nx + hw, nx - hw, nx - hw],
                y=[y_wall, y_wall, y_tip, y_tip, y_wall],
                fill="toself", fillcolor="rgba(255,255,255,0.95)",
                line=dict(color=nc, width=2.8),
                showlegend=False, hovertemplate=hover + "<extra></extra>",
            ))
            # Flange face (bold horizontal line at tip)
            fig.add_shape(type="line",
                          x0=nx - hw - 6, x1=nx + hw + 6,
                          y0=y_tip, y1=y_tip,
                          line=dict(color=nc, width=4))
            # Nozzle opening marker
            fig.add_trace(go.Scatter(
                x=[nx], y=[y_tip], mode="markers",
                marker=dict(size=min(11.0, hw * 1.9), color="white",
                            line=dict(color=nc, width=2.4)),
                showlegend=False, hoverinfo="skip",
            ))
            # Pulsing halo for problem nozzles (warning -> orange, error -> red)
            if sev in ("warning", "error"):
                pulse_col = "#d97706" if sev == "warning" else "#dc2626"
                fig.add_trace(go.Scatter(
                    x=[nx], y=[y_tip], mode="markers",
                    marker=dict(size=min(40.0, hw * 6.0), color=pulse_col, opacity=0.0),
                    showlegend=False, hoverinfo="skip",
                ))
            # Tag label
            fig.add_annotation(
                x=nx, y=y_tip + sign * 12,
                text=f"<b>{nz_cfg['tag']}</b>",
                showarrow=False, xanchor="center",
                yanchor="bottom" if sign > 0 else "top",
                font=dict(size=9, color=nc),
                bgcolor="rgba(255,255,255,0.75)", borderpad=1,
            )
            # Track actual nozzle + label extents for y-axis limits.
            # Top nozzles extend upward (sign=+1); bottom nozzles downward (sign=−1).
            if sign > 0:
                _y_nz_top = max(_y_nz_top, y_tip + 22)   # +22 for tag label
            else:
                _y_nz_bot = min(_y_nz_bot, y_tip - 22)   # −22 for tag label

        else:
            # ── Shell side: concentric circles at y=0 (end-on in elevation) ──
            # Side nozzles project perpendicular to the page; in side view they
            # appear as circles centred on the vessel horizontal axis.
            nx    = nz_cfg["axial_mm"]
            cr    = min(nOR * 0.65, 20.0)
            bore_r = cr * 0.55
            fig.add_trace(go.Scatter(
                x=[nx + cr * math.cos(t) for t in theta_pts],
                y=[cr * math.sin(t) for t in theta_pts],
                fill="toself", fillcolor="rgba(255,255,255,0.95)",
                line=dict(color=nc, width=3.0), showlegend=False,
                hovertemplate=hover + "<extra></extra>",
            ))
            fig.add_trace(go.Scatter(
                x=[nx + bore_r * math.cos(t) for t in theta_pts],
                y=[bore_r * math.sin(t) for t in theta_pts],
                fill="toself", fillcolor="rgba(255,255,255,0.95)",
                line=dict(color=nc, width=2.2, dash="dot"), showlegend=False,
                hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=[nx], y=[0], mode="markers",
                marker=dict(size=4, color=nc),
                showlegend=False, hoverinfo="skip",
            ))
            # Pulsing halo for side nozzles
            if sev in ("warning", "error"):
                pulse_col = "#d97706" if sev == "warning" else "#dc2626"
                fig.add_trace(go.Scatter(
                    x=[nx], y=[0], mode="markers",
                    marker=dict(size=min(40.0, cr * 6.0), color=pulse_col, opacity=0.0),
                    showlegend=False, hoverinfo="skip",
                ))
            fig.add_annotation(
                x=nx, y=cr + 10,
                text=f"<b>{nz_cfg['tag']}</b>",
                showarrow=False, xanchor="center", yanchor="bottom",
                font=dict(size=9, color=nc),
                bgcolor="rgba(255,255,255,0.75)", borderpad=1,
            )

    # ── Baffle plates (distribution plate with distributed holes) ────────────
    _bclr  = "#7c3aed" if has_baffles else "#c4b5fd"
    _blabel = f"Baffle ({baffle_open_pct:.0f}% open)" if has_baffles else "Baffle (disabled)"
    if L_baffle_mm > 0:
        for bx in (L_baffle_mm, L_shell - L_baffle_mm):
            if 0 < bx < L_shell:
                # Full-height plate line
                fig.add_shape(type="line", x0=bx, x1=bx, y0=-R, y1=R,
                              line=dict(color=_bclr,
                                        width=2.5 if has_baffles else 1.0,
                                        dash="solid" if has_baffles else "dot"))
                if has_baffles:
                    # Distributed holes: small horizontal gaps evenly spaced
                    n_holes = max(5, int(R * 2 / 60))
                    for k in range(n_holes):
                        hy = -R + (2 * R) * (k + 0.5) / n_holes
                        fig.add_shape(type="line",
                                      x0=bx - 7, x1=bx + 7, y0=hy, y1=hy,
                                      line=dict(color=_bclr, width=1.2))
        for bx in (L_baffle_mm, L_shell - L_baffle_mm):
            if 0 < bx < L_shell:
                fig.add_annotation(x=bx, y=R + 20, text=_blabel,
                                   showarrow=False, xanchor="center", yanchor="bottom",
                                   font=dict(size=9, color=_bclr))

    # Inlet device, mesh pad, and vortex-breaker visuals are intentionally omitted
    # from the drawing. Baffle plates remain visible because they are part of the
    # vessel internals layout that is useful for the sketch.

    # Di label inside cylinder
    fig.add_annotation(
        x=L_shell * 0.5, y=0,
        text=f"Di = {Di:.0f} mm",
        showarrow=False, font=dict(size=11, color="#475569"),
    )

    # ── Liquid level lines ────────────────────────────────────────────────────
    if levels_mm:
        R = Di / 2
        x_line_l = -h_head
        x_line_r = L_shell + h_head
        x_label  = L_shell + h_head + 10
        # Sort so labels don't overlap if levels are close
        sorted_lvls = sorted(levels_mm.items(), key=lambda kv: kv[1])
        prev_label_y: float | None = None
        for tag, h in sorted_lvls:
            h = max(0.0, min(Di, h))
            y_line = h - R
            colour, dash, width = _LEVEL_STYLE.get(tag, ("#64748b", "dash", 1.5))
            fig.add_shape(
                type="line", x0=x_line_l, x1=x_line_r, y0=y_line, y1=y_line,
                line=dict(color=colour, width=width, dash=dash),
            )
            # Nudge label up if it would collide with the previous one
            label_y = y_line
            if prev_label_y is not None and abs(label_y - prev_label_y) < 22:
                label_y = prev_label_y + 22
            fig.add_annotation(
                x=x_label, y=label_y,
                text=f"<b>{tag}</b>",
                showarrow=False, xanchor="left",
                font=dict(size=9, color=colour),
                bgcolor="rgba(255,255,255,0.75)", borderpad=1,
            )
            prev_label_y = label_y

    # ── Pole labels ───────────────────────────────────────────────────────────
    fig.add_annotation(
        x=-(h_head + 2) if h_head > 0 else -5, y=0,
        text="Pole", showarrow=False, xanchor="right",
        font=dict(size=10, color="#64748b"),
    )
    fig.add_annotation(
        x=L_shell + h_head + 2 if h_head > 0 else L_shell + 5, y=0,
        text="Pole", showarrow=False, xanchor="left",
        font=dict(size=10, color="#64748b"),
    )

    # ── Overall length dimension (pole-to-pole) ───────────────────────────────
    total_len = L_shell + 2 * h_head
    x_left  = -h_head
    x_right = L_shell + h_head
    y_dim   = -(R + max(t_shell_nom, 15) + 45)   # below the bottom outer wall
    tick_h  = 18
    dim_colour = "#475569"
    # Horizontal dimension line
    fig.add_shape(type="line", x0=x_left, x1=x_right, y0=y_dim, y1=y_dim,
                  line=dict(color=dim_colour, width=1.5))
    # End ticks
    for x_tick in (x_left, x_right):
        fig.add_shape(type="line", x0=x_tick, x1=x_tick,
                      y0=y_dim - tick_h / 2, y1=y_dim + tick_h / 2,
                      line=dict(color=dim_colour, width=1.5))
    # Label
    fig.add_annotation(
        x=(x_left + x_right) / 2, y=y_dim - 14,
        text=f"<b>{total_len:,.0f} mm</b> pole-to-pole",
        showarrow=False, xanchor="center", yanchor="top",
        font=dict(size=11, color=dim_colour),
        bgcolor="rgba(255,255,255,0.8)", borderpad=2,
    )

    # ── Saddle supports ───────────────────────────────────────────────────────
    saddle_h = max(150.0, R * 0.25)          # visual height of saddle body
    saddle_base_extra = max(30.0, saddle_w_mm * 0.15)  # base plate overhang each side
    saddle_base_h = max(20.0, saddle_h * 0.12)
    y_saddle_top = -(R + max(t_shell_nom, 0))
    y_saddle_bot = y_saddle_top - saddle_h
    y_base_bot   = y_saddle_bot - saddle_base_h

    if saddle_a_mm > 0:
        for sx in (saddle_a_mm, L_shell - saddle_a_mm):
            hw = saddle_w_mm / 2
            # Saddle body
            fig.add_shape(type="rect",
                          x0=sx - hw, x1=sx + hw,
                          y0=y_saddle_bot, y1=y_saddle_top,
                          fillcolor="rgba(148,163,184,0.45)",
                          line=dict(color="#64748b", width=1.5))
            # Base plate
            fig.add_shape(type="rect",
                          x0=sx - hw - saddle_base_extra, x1=sx + hw + saddle_base_extra,
                          y0=y_base_bot, y1=y_saddle_bot,
                          fillcolor="rgba(100,116,139,0.55)",
                          line=dict(color="#64748b", width=1.5))
        # Saddle position dimension (distance from tangent)
        for sx in (saddle_a_mm, L_shell - saddle_a_mm):
            tang = 0 if sx < L_shell / 2 else L_shell
            fig.add_shape(type="line",
                          x0=tang, x1=sx, y0=y_base_bot - 12, y1=y_base_bot - 12,
                          line=dict(color="#94a3b8", width=1, dash="dot"))
            fig.add_annotation(
                x=(tang + sx) / 2, y=y_base_bot - 24,
                text=f"{saddle_a_mm:.0f} mm",
                showarrow=False, xanchor="center", yanchor="top",
                font=dict(size=9, color="#64748b"),
            )

    saddle_depth = (saddle_h + saddle_base_h + 40) if saddle_a_mm > 0 else 0
    x_min = -(h_head + 80)
    x_max = L_shell + h_head + 80
    # Y-axis: tight range — only what's needed to show vessel + nozzle stubs + labels.
    # _y_nz_top / _y_nz_bot hold the extreme y-coordinates of all shell nozzle stubs.
    _top_clearance = max(t_shell_nom, 15) + 40
    _bot_clearance = max(t_shell_nom, 15) + max(40, saddle_depth)
    y_lim     = max(R + _top_clearance, _y_nz_top + 25)
    y_lim_bot = max(R + _bot_clearance, abs(_y_nz_bot) + 25)

    # Build simple two-frame animation to 'flash' problem nozzles (pulse traces)
    pulse_indices: list[int] = []
    for i, tr in enumerate(fig.data):
        # identify our pulse traces by the presence of a marker with opacity == 0
        if hasattr(tr, 'marker') and getattr(tr.marker, 'opacity', None) == 0:
            # ensure it's one of the larger halo traces (size > 20)
            size = getattr(tr.marker, 'size', 0) or 0
            if size and size > 12:
                pulse_indices.append(i)

    if pulse_indices:
        frame_on = go.Frame(data=[go.Scatter(marker=dict(opacity=0.75)) for _ in pulse_indices],
                            traces=pulse_indices, name="on")
        frame_off = go.Frame(data=[go.Scatter(marker=dict(opacity=0.0)) for _ in pulse_indices],
                             traces=pulse_indices, name="off")
        fig.frames = [frame_on, frame_off]
        # Add a small play control for the animation; autoplay when the figure first appears
        fig.update_layout(updatemenus=[dict(type="buttons", showactive=False,
                                            x=0.01, y=-0.14, xanchor="left",
                                            buttons=[dict(label="Play",
                                                          method="animate",
                                                          args=[["on", "off"],
                                                                {"frame": {"duration": 700, "redraw": False},
                                                                 "fromcurrent": True, "transition": {"duration": 0}}])])])

    # Chart height for a 1:1-scale drawing.
    # With scaleanchor="x" Plotly shrinks the plot area so the data-unit size
    # is equal on both axes.  The required plot-area height is:
    #   h_plot ≈ effective_plot_width × (y_span / x_span)
    # Tuned for the typical Di=1.8 m / L=4 m vessel at ~1250 px effective
    # plot-area width (full-width Streamlit widget minus Plotly internal margins).
    # Longer vessels naturally produce shorter charts — the scale stays correct.
    _x_span   = x_max - x_min
    _y_span   = y_lim + y_lim_bot
    _plot_w   = 1250                              # effective plot-area width (px)
    _plot_h   = _plot_w * _y_span / _x_span      # required height at 1:1 scale
    _chart_h  = max(380, min(720, int(_plot_h) + 130))  # add margin/legend space

    fig.update_layout(
        height=_chart_h,
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=True,
        legend=dict(
            orientation="h", x=0.5, y=-0.12,
            xanchor="center", yanchor="top",
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#e2e8f0", borderwidth=1,
            font=dict(size=9),
        ),
        xaxis=dict(
            title="Axial position (mm) — 0 = left tangent, L = right tangent",
            range=[x_min, x_max],
            zeroline=False, gridcolor="#f8fafc", tickformat=",d",
            constrain="domain",
        ),
        yaxis=dict(
            title="Vertical position (mm) — 0 = vessel axis",
            range=[-y_lim_bot, y_lim],
            scaleanchor="x", scaleratio=1,
            gridcolor="#f8fafc",
        ),
    )
    return fig


# ──────────────────────── NOZZLE PLACEMENT CHECKS ───────────────────────────

import math as _math
from dataclasses import dataclass as _dc
from typing import List as _List

_LOC_ANGLE: dict[str, float] = {
    "Shell — top":    0.0,
    "Shell — side":   _math.pi / 2,
    "Shell — bottom": _math.pi,
}

@_dc
class _NozzleCheck:
    level:    str   # "error" | "warning" | "info"
    tags:     list
    code_ref: str
    headline: str   # concise technical statement
    detail:   str   # fuller technical explanation
    impact:   str   # plain-English "so what / what to do"


def _nozzle_placement_checks(
    nozzle_results: list,
    Di: float, L_shell: float,
    t_shell_mm: float, t_head_mm: float,
    saddle_a_mm: float, saddle_w_mm: float,
    code_key: str,
) -> _List[_NozzleCheck]:
    """
    Run code-based and practical placement checks across all nozzles.
    Returns a list of _NozzleCheck items ordered by severity (errors first).
    """
    checks: list[_NozzleCheck] = []
    R = Di / 2.0
    code = "EN 13445-3" if code_key == "EN" else "ASME VIII Div.1"

    # ── Build nozzle geometry list ─────────────────────────────────────────────
    nozzles_geo = []
    for nz, nres, rres, *_ in nozzle_results:
        dn  = nz["dn"]
        OD  = NOZZLE_OD.get(dn, dn * 1.05)
        OR  = OD / 2.0
        pn  = nz.get("pn", 25)
        rec = recommended_schedule(pn, code_key)
        t   = float(NOZZLE_WALL_SCH[rec].get(dn, NOZZLE_WALL_T.get(dn, 8.0)))
        bore = max(OD - 2 * t, 1.0)
        nozzles_geo.append({
            "tag": nz["tag"], "svc": nz["service"], "loc": nz["loc"],
            "OD": OD, "OR": OR, "bore": bore, "t_nz": t,
            "axial": nz.get("axial_mm", L_shell / 2),
            "d_from_top": nz.get("d_from_top", Di / 2),
            "nres": nres, "rres": rres,
        })

    min_shell_clr = max(3.0 * t_shell_mm, 25.0)   # min weld clearance on shell
    min_head_clr  = max(3.0 * t_head_mm,  25.0)   # min weld clearance on head

    # ── Shell nozzles only ────────────────────────────────────────────────────
    shell_nz = [g for g in nozzles_geo if g["loc"] in _LOC_ANGLE]

    # A — Shell nozzle edge too close to tangent (head-to-shell weld)
    for g in shell_nz:
        edge_L = g["axial"] - g["OR"]
        edge_R = L_shell - (g["axial"] + g["OR"])
        min_dist = min(edge_L, edge_R)
        if min_dist < 0:
            checks.append(_NozzleCheck(
                level="error", tags=[g["tag"]],
                code_ref=f"{code} cl.{'9.2' if code_key=='EN' else 'UG-36(d)'}",
                headline=f"{g['tag']} OD overlaps the tangent / head-shell weld seam.",
                detail=f"Nozzle OD edge is {-min_dist:.0f} mm past the tangent line. "
                       f"The head-shell circumferential weld must be at least {min_shell_clr:.0f} mm from any nozzle edge.",
                impact="This nozzle physically cannot be placed here — it would intersect the head-shell weld. "
                       "Move the nozzle inward or reduce the nozzle size.",
            ))
        elif min_dist < min_shell_clr:
            checks.append(_NozzleCheck(
                level="warning", tags=[g["tag"]],
                code_ref=f"{code} cl.{'9.2' if code_key=='EN' else 'UG-36(d)'}",
                headline=f"{g['tag']} is {min_dist:.0f} mm from tangent weld; min {min_shell_clr:.0f} mm required.",
                detail=f"The head-shell circumferential weld requires a clearance of max(3t_shell, 25 mm) = {min_shell_clr:.0f} mm. "
                       f"Current edge clearance is only {min_dist:.0f} mm.",
                impact="Nozzle too close to a seam weld. Either move it inward, use a thinner wall (if pressure permits), "
                       "or get fabricator approval for a local PWHT / WPS exception. Adds cost and documentation effort.",
            ))

    # B — Shell nozzle near saddle support
    # A standard saddle wraps approximately ±60° from the 6 o'clock position
    # (120° contact angle total).  Only "Shell — bottom" nozzles are inside
    # that contact zone and need this check.
    # "Shell — side" nozzles sit at 90° from the bottom — outside the contact
    # zone for any saddle with ≤ 180° wrap.  "Shell — top" nozzles are on the
    # diametrically opposite side and can never interact with the saddle.
    if saddle_a_mm > 0:
        bottom_nz = [g for g in shell_nz if g["loc"] == "Shell — bottom"]
        for g in bottom_nz:
            for sx in (saddle_a_mm, L_shell - saddle_a_mm):
                gap = abs(g["axial"] - sx) - (g["OR"] + saddle_w_mm / 2.0)
                if gap < 0:
                    checks.append(_NozzleCheck(
                        level="error", tags=[g["tag"]],
                        code_ref="Zick / EN 13445-3 cl.16",
                        headline=f"{g['tag']} OD overlaps saddle at {sx:.0f} mm — nozzle is inside the saddle contact zone.",
                        detail=f"Nozzle OD edge extends {-gap:.0f} mm into the saddle bearing area. "
                               "A nozzle inside the saddle contact zone creates a stress concentration "
                               "that is outside the scope of standard Zick analysis.",
                        impact="Relocate the nozzle axially or reposition the saddle. "
                               "Cannot be resolved by analysis alone — fabrication is not feasible as drawn.",
                    ))
                elif gap < min_shell_clr:
                    checks.append(_NozzleCheck(
                        level="warning", tags=[g["tag"]],
                        code_ref="Zick / EN 13445-3 cl.16",
                        headline=f"{g['tag']} is {gap:.0f} mm from saddle edge (min {min_shell_clr:.0f} mm recommended).",
                        detail="The bottom nozzle is close to the saddle horn. Combined saddle bending and "
                               "pressure stress at this location requires a Zick or FEA check.",
                        impact="Detailed local stress analysis required (1–3 weeks). "
                               "If stress is too high, move the nozzle or add a reinforcing ring.",
                    ))

    # C — Large opening ratio (bore / Di)
    for g in nozzles_geo:
        ratio = g["bore"] / Di
        if ratio > 0.5:
            checks.append(_NozzleCheck(
                level="error", tags=[g["tag"]],
                code_ref=f"{'EN 13445-3 cl.9.7' if code_key=='EN' else 'ASME UG-36(b)(1) + Div.1 App.1-7'}",
                headline=f"{g['tag']} bore/Di = {ratio:.0%} — exceeds 50 %. Pressure-area or FEA mandatory.",
                detail=f"Opening diameter {g['bore']:.0f} mm > Di/2 = {Di/2:.0f} mm. Standard area-replacement method (UG-37 / cl.9.4) "
                       "is not valid. Pressure-area method or full FEA required.",
                impact="Very large opening — significant cost and schedule impact. Expect 4–8 weeks additional analysis, "
                       "specialist review, and potentially a reinforcing insert or junction piece. "
                       "Reconsider if a standard nozzle size can meet the process requirement.",
            ))
        elif ratio > 1 / 3:
            checks.append(_NozzleCheck(
                level="warning", tags=[g["tag"]],
                code_ref=f"{'EN 13445-3 cl.9.5/9.7' if code_key=='EN' else 'ASME UG-36(b)(1)'}",
                headline=f"{g['tag']} bore/Di = {ratio:.0%} — exceeds 1/3. Enhanced reinforcement check required.",
                detail=f"Opening diameter {g['bore']:.0f} mm > Di/3 = {Di/3:.0f} mm. "
                       "Area-replacement method may still apply but code requires additional checks; "
                       "pressure-area method is recommended.",
                impact="Larger-than-normal nozzle requires detailed engineering. Reinforcing pad will likely be large. "
                       "Budget 1–2 extra weeks for analysis. FEA may be needed if pad geometry is impractical.",
            ))

    # D — Shell nozzle-to-nozzle axial proximity (same circumferential position)
    same_loc_groups: dict[str, list] = {}
    for g in shell_nz:
        same_loc_groups.setdefault(g["loc"], []).append(g)

    for loc, group in same_loc_groups.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                center_dist = abs(a["axial"] - b["axial"])
                edge_dist = center_dist - (a["OR"] + b["OR"])
                rz_overlap = center_dist - (a["bore"] / 2 + b["bore"] / 2 + 2 * t_shell_mm)
                if edge_dist < 0:
                    checks.append(_NozzleCheck(
                        level="error", tags=[a["tag"], b["tag"]],
                        code_ref=f"{'EN 13445-3 cl.9.5' if code_key=='EN' else 'ASME UG-42'}",
                        headline=f"{a['tag']} and {b['tag']} ODs overlap — physically impossible on same generator.",
                        detail=f"Axial centre-to-centre = {center_dist:.0f} mm; OD sum = {a['OD']+b['OD']:.0f} mm. "
                               "The nozzle bodies physically intersect.",
                        impact="These two nozzles cannot coexist at their current positions. "
                               "Move one nozzle axially or choose a smaller DN.",
                    ))
                elif rz_overlap < 0:
                    checks.append(_NozzleCheck(
                        level="warning", tags=[a["tag"], b["tag"]],
                        code_ref=f"{'EN 13445-3 cl.9.5' if code_key=='EN' else 'ASME UG-42'}",
                        headline=f"{a['tag']} and {b['tag']} reinforcement zones overlap — combined check required.",
                        detail=f"Centre-to-centre {center_dist:.0f} mm < bore sum + 2t ({a['bore']/2+b['bore']/2+2*t_shell_mm:.0f} mm). "
                               "Reinforcement zones interact; a combined area-replacement analysis is required.",
                        impact="Two nozzles sharing their reinforcement zone need a more complex calculation. "
                               "Budget 1–2 weeks additional analysis. If combined area is insufficient, "
                               "a larger pad or local thickening will be needed — adds cost.",
                    ))
                elif edge_dist < min_shell_clr:
                    checks.append(_NozzleCheck(
                        level="info", tags=[a["tag"], b["tag"]],
                        code_ref="Fabrication practice",
                        headline=f"{a['tag']} and {b['tag']} are {edge_dist:.0f} mm apart (edge-to-edge); min {min_shell_clr:.0f} mm recommended.",
                        detail="Tight spacing between adjacent nozzles on the same generator line makes "
                               "weld access and NDT difficult.",
                        impact="Confirm with fabricator that welding and inspection access is achievable. "
                               "May require special procedures or weld sequence planning (+1 week).",
                    ))

    # E — Cross-circumferential proximity (different loc, same axial zone)
    for i in range(len(shell_nz)):
        for j in range(i + 1, len(shell_nz)):
            a, b = shell_nz[i], shell_nz[j]
            if a["loc"] == b["loc"]:
                continue   # handled in D
            axial_gap = abs(a["axial"] - b["axial"]) - (a["OR"] + b["OR"])
            if axial_gap >= 0:
                continue   # not in same cluster
            # They're in the same axial cluster — check arc distance
            theta_a = _LOC_ANGLE[a["loc"]]
            theta_b = _LOC_ANGLE[b["loc"]]
            delta   = abs(theta_a - theta_b)
            delta   = min(delta, 2 * _math.pi - delta)
            arc_edge = R * delta - (a["OR"] + b["OR"])
            if arc_edge < 0:
                checks.append(_NozzleCheck(
                    level="error", tags=[a["tag"], b["tag"]],
                    code_ref="Fabrication / code geometry",
                    headline=f"{a['tag']} and {b['tag']} ODs overlap circumferentially in the same axial cluster.",
                    detail=f"Arc edge-to-edge = {arc_edge:.0f} mm (negative = overlap). "
                           "Nozzles at different clock positions in the same axial zone physically interfere.",
                    impact="Relocate one nozzle axially or reduce DN. No weld access possible in current arrangement.",
                ))
            elif arc_edge < min_shell_clr:
                checks.append(_NozzleCheck(
                    level="warning", tags=[a["tag"], b["tag"]],
                    code_ref="Fabrication practice",
                    headline=f"{a['tag']} and {b['tag']} arc clearance = {arc_edge:.0f} mm; min {min_shell_clr:.0f} mm recommended.",
                    detail="Nozzles at different circumferential positions within the same axial zone have tight arc spacing.",
                    impact="Difficult weld access between these nozzles. Fabricator may require manual welding procedures.",
                ))

    # F — Head nozzle-to-head nozzle proximity (same head)
    for side in ("Left head", "Right head"):
        head_grp = [g for g in nozzles_geo if g["loc"] == side and g["nres"] is not None]
        for i in range(len(head_grp)):
            for j in range(i + 1, len(head_grp)):
                a, b = head_grp[i], head_grp[j]
                # Approximate distance in the head plane via r_from_axis difference
                # (not exact for off-axis nozzles, but a useful screener)
                r_a = a["nres"].r_from_axis_mm
                r_b = b["nres"].r_from_axis_mm
                y_a = a["nres"].y_nozzle_mm
                y_b = b["nres"].y_nozzle_mm
                center_dist = abs(y_a - y_b)   # vertical distance between centres (simplified)
                edge_dist = center_dist - (a["OR"] + b["OR"])
                if edge_dist < 0:
                    checks.append(_NozzleCheck(
                        level="error", tags=[a["tag"], b["tag"]],
                        code_ref=f"{'EN 13445-3 cl.9.5' if code_key=='EN' else 'ASME UG-42'}",
                        headline=f"{a['tag']} and {b['tag']} on {side}: ODs overlap (edge dist ≈ {edge_dist:.0f} mm).",
                        detail="Head nozzle bodies intersect based on their vertical offset. Combined detailed check required.",
                        impact="These nozzles cannot be placed as specified. Move one nozzle or reduce DN.",
                    ))
                elif edge_dist < min_head_clr:
                    checks.append(_NozzleCheck(
                        level="warning", tags=[a["tag"], b["tag"]],
                        code_ref=f"{'EN 13445-3 cl.9.5' if code_key=='EN' else 'ASME UG-36(c)'}",
                        headline=f"{a['tag']} and {b['tag']} on {side}: edge spacing ≈ {edge_dist:.0f} mm < {min_head_clr:.0f} mm.",
                        detail="Close nozzle spacing on the head reduces weld access and may cause reinforcement zone overlap.",
                        impact="Confirm combined reinforcement is adequate. Fabrication will require careful weld sequencing.",
                    ))

    # G — Manway clear opening check
    for g in nozzles_geo:
        if g["svc"] == "Manway" and g["bore"] < 400:
            checks.append(_NozzleCheck(
                level="warning", tags=[g["tag"]],
                code_ref="EN 13445-5 / OSHA 1910.146 / typical practice",
                headline=f"Manway {g['tag']} clear opening ≈ {g['bore']:.0f} mm — below 400 mm industry minimum.",
                detail="Most codes and standards require a minimum 400–500 mm clear opening for personnel access "
                       "and confined-space compliance. Current bore is insufficient.",
                impact="Regulatory non-compliance risk. Workers cannot safely enter or exit vessel. "
                       "Increase to at least DN450 (bore ≥ 400 mm). This is a safety-critical change.",
            ))

    # H — Bottom nozzles: longitudinal seam advisory
    # This is a standard fabrication coordination note, not a defect.
    # The seam position is always specified on the fabrication drawing (MDS / material
    # specification) and is routinely placed away from nozzles — no relocation of the
    # nozzle is normally needed; only the seam placement note on the drawing.
    bottom_nz = [g for g in shell_nz if g["loc"] == "Shell — bottom"]
    if bottom_nz:
        tags = [g["tag"] for g in bottom_nz]
        checks.append(_NozzleCheck(
            level="info", tags=tags,
            code_ref="Fabrication practice / code weld exclusion",
            headline=f"Bottom nozzle(s) {', '.join(tags)}: specify longitudinal seam away from nozzle(s) on fabrication drawing.",
            detail=f"Rolled-plate shells have one longitudinal (long seam) weld that must be ≥ max(3·t_shell, 25 mm) "
                   f"= {min_shell_clr:.0f} mm clear of any nozzle OD edge. "
                   "This is normal practice for vessels with bottom nozzles — the seam position is simply called out on "
                   "the MDS / fabrication drawing. The fabricator rotates the plate so the seam lands at, for example, "
                   "the 3 o'clock or 9 o'clock position. No nozzle relocation is required.",
            impact="Add a note to the fabrication drawing: "
                   "'Longitudinal seam shall be positioned min. "
                   f"{min_shell_clr:.0f} mm clear of all nozzle OD edges at the bottom of the vessel.' "
                   "This is a routine instruction with no cost or schedule impact.",
        ))

    # I — Multi-course girth weld advisory (general)
    if L_shell > 3000:
        checks.append(_NozzleCheck(
            level="info", tags=[],
            code_ref="Fabrication practice",
            headline="Shell length > 3 m: girth (circumferential) welds likely between shell courses.",
            detail=f"At L_shell = {L_shell:.0f} mm, the shell will require ≥2 plate courses with girth welds. "
                   f"All nozzles must clear each girth weld by ≥ {min_shell_clr:.0f} mm (edge-to-edge). "
                   "Exact girth weld positions depend on plate sizes selected by the fabricator.",
            impact="Request the fabricator's plate layout drawing before finalising nozzle positions. "
                   "A single girth weld conflict can require a nozzle move late in the drawing review cycle.",
        ))

    # Sort: errors first, then warnings, then info
    order = {"error": 0, "warning": 1, "info": 2}
    checks.sort(key=lambda c: order.get(c.level, 3))
    return checks


# ──────────────────────── ENDCAP NOZZLE ANALYSIS ─────────────────────────────

# All head types with standard defaults used in alternative-head comparison.
_ENDCAP_ALT_HEADS: list[tuple] = [
    # (HeadType, display label, override kwargs for nozzle_on_head)
    (HeadType.HEMISPHERICAL,  "Hemispherical",              {}),
    (HeadType.ELLIPSOIDAL,    "Ellipsoidal 2:1",            {"ellipse_ratio": 2.0}),
    (HeadType.TORISPHERICAL,  "Tori — Klöpper (r=0.10Di)", {"crown_ratio": 1.0, "knuckle_ratio": 0.10}),
    (HeadType.FLANGED_DISHED, "F&D — ASME (r=0.06Di)",     {}),
    (HeadType.CONICAL,        "Conical 30°",                {"alpha_deg_cone": 30.0}),
    (HeadType.FLAT,           "Flat",                       {}),
]

_ENDCAP_HEAD_NOTES: dict[str, str] = {
    "Hemispherical":              "No knuckle — entire head face is usable; depth = R (Di/2); most expensive to form.",
    "Ellipsoidal 2:1":            "Stress reversal at r ≈ 0.577·R; compressive hoop beyond → detailed check or FEA.",
    "Tori — Klöpper (r=0.10Di)": "Crown to r_cj ≈ 0.80·R; knuckle zone beyond → standard rules invalid.",
    "F&D — ASME (r=0.06Di)":     "Shallower knuckle → larger crown zone (r_cj ≈ 0.86·R); shallower head.",
    "Conical 30°":                "No distinct knuckle; full face is 'cone' zone; apex & junction need separate checks.",
    "Flat":                       "No curvature benefit; requires thick plate; suitable for low pressure / small Di only.",
}


def _hex_alpha(hex_color: str, alpha: float = 0.25) -> str:
    """Convert #rrggbb hex to rgba(r,g,b,alpha) string."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _nozzle_zone_color(nres) -> str:
    """Traffic-light colour for a nozzle result."""
    if not nres.geom_ok:          return "#dc2626"
    if nres.code_ok is False:     return "#dc2626"
    if nres.zone == "knuckle":    return "#d97706"
    if nres.code_ok is None:      return "#d97706"
    return "#16a34a"


def _endcap_face_figure(
    head_type: HeadType, Di: float,
    R_c: float, r_k: float, b: float,
    t_head_nom: float,
    nozzle_data: list,   # list of (nz_dict, nres)
    title: str = "",
) -> go.Figure:
    """
    Face-on view of one endcap (looking axially inward).
    Shows crown/knuckle zone fills, weld-exclusion ring, and each nozzle OD circle.
    All nozzles are placed on the vertical centre axis of the head (x = 0),
    at the signed vertical position y = R − d_from_top.
    """
    R = Di / 2.0
    min_weld_clr = max(3.0 * t_head_nom, 25.0)

    N = 200
    theta_pts = [i / N * 2 * math.pi for i in range(N + 1)]
    ux = [math.cos(t) for t in theta_pts]
    uy = [math.sin(t) for t in theta_pts]

    fig = go.Figure()

    # Normalise F&D → torispherical for zone drawing
    _ht, _Rc, _rk = head_type, R_c, r_k
    if _ht == HeadType.FLANGED_DISHED:
        _ht = HeadType.TORISPHERICAL
        _Rc = _FD_CROWN_RATIO * Di
        _rk = _FD_KNUCKLE_RATIO * Di

    # ── Head zone fills ───────────────────────────────────────────────────────
    if _ht == HeadType.TORISPHERICAL:
        tg = _tori_geometry(Di, _Rc, _rk)
        r_cj = tg["r_cj"]
        # Crown zone (filled inner circle)
        fig.add_trace(go.Scatter(
            x=[r_cj * u for u in ux], y=[r_cj * u for u in uy],
            fill="toself", fillcolor="rgba(34,197,94,0.20)",
            line=dict(color="rgba(0,0,0,0)"),
            name=f"Crown zone — standard analysis OK (r ≤ {r_cj:.0f} mm)",
            hoverinfo="skip",
        ))
        # Knuckle zone (annulus)
        fig.add_trace(go.Scatter(
            x=[R * u for u in ux] + [r_cj * u for u in reversed(ux)],
            y=[R * u for u in uy] + [r_cj * u for u in reversed(uy)],
            fill="toself", fillcolor="rgba(245,158,11,0.22)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Knuckle zone — specialist analysis required",
            hoverinfo="skip",
        ))
        # Crown/knuckle boundary circle
        fig.add_trace(go.Scatter(
            x=[r_cj * u for u in ux], y=[r_cj * u for u in uy],
            mode="lines", line=dict(color="#16a34a", width=1.8, dash="dash"),
            name=f"Crown/knuckle boundary  r = {r_cj:.0f} mm",
            hoverinfo="skip",
        ))

    elif _ht == HeadType.ELLIPSOIDAL:
        _k = max(Di / (2.0 * b), 1.001)
        r_rev = R / math.sqrt(_k * _k - 1.0)
        fig.add_trace(go.Scatter(
            x=[r_rev * u for u in ux], y=[r_rev * u for u in uy],
            fill="toself", fillcolor="rgba(34,197,94,0.20)",
            line=dict(color="rgba(0,0,0,0)"),
            name=f"Tensile hoop zone — standard analysis OK (r ≤ {r_rev:.0f} mm)",
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=[R * u for u in ux] + [r_rev * u for u in reversed(ux)],
            y=[R * u for u in uy] + [r_rev * u for u in reversed(uy)],
            fill="toself", fillcolor="rgba(245,158,11,0.22)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Compressive hoop zone — detailed analysis needed",
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=[r_rev * u for u in ux], y=[r_rev * u for u in uy],
            mode="lines", line=dict(color="#16a34a", width=1.8, dash="dash"),
            name=f"Hoop-stress reversal  r = {r_rev:.0f} mm",
            hoverinfo="skip",
        ))

    else:
        # Hemispherical, Conical, Flat — full face is usable zone
        fig.add_trace(go.Scatter(
            x=[R * u for u in ux], y=[R * u for u in uy],
            fill="toself", fillcolor="rgba(34,197,94,0.18)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Full head face — code analysis applicable throughout",
            hoverinfo="skip",
        ))

    # ── Weld-exclusion ring ───────────────────────────────────────────────────
    r_excl = R - min_weld_clr
    if r_excl > 10:
        fig.add_trace(go.Scatter(
            x=[R * u for u in ux] + [r_excl * u for u in reversed(ux)],
            y=[R * u for u in uy] + [r_excl * u for u in reversed(uy)],
            fill="toself", fillcolor="rgba(220,38,38,0.10)",
            line=dict(color="rgba(0,0,0,0)"),
            name=f"Weld-exclusion ring ≥ {min_weld_clr:.0f} mm from head-shell seam",
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=[r_excl * u for u in ux], y=[r_excl * u for u in uy],
            mode="lines", line=dict(color="#dc2626", width=1.2, dash="dot"),
            showlegend=False, hoverinfo="skip",
        ))

    # ── Vessel inner wall circle ──────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=[R * u for u in ux], y=[R * u for u in uy],
        mode="lines", line=dict(color="#1d4ed8", width=2.5),
        name=f"Head inner wall  Di = {Di:.0f} mm",
        hoverinfo="skip",
    ))

    # ── Axis cross ────────────────────────────────────────────────────────────
    d = R * 0.05
    for xs, ys in [([-d, d], [0, 0]), ([0, 0], [-d, d])]:
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                                 line=dict(color="#94a3b8", width=1.2),
                                 showlegend=False, hoverinfo="skip"))

    # ── Nozzle circles ────────────────────────────────────────────────────────
    N_nz = 120
    nz_theta = [i / N_nz * 2 * math.pi for i in range(N_nz + 1)]

    for nz_dict, nres in nozzle_data:
        nc  = _nozzle_zone_color(nres)
        ny  = nres.y_nozzle_mm
        nOR = nres.nozzle_OR_mm
        bore = max(nres.nozzle_OD_mm - 2 * nres.nozzle_t_mm, 1.0)
        bOR  = bore / 2.0
        code_str = "OK" if nres.code_ok is True else ("?" if nres.code_ok is None else "FAIL")
        hover = (
            f"<b>{nz_dict['tag']}</b> — {nz_dict['service']}<br>"
            f"DN{nz_dict['dn']}  OD {nres.nozzle_OD_mm:.1f} mm<br>"
            f"Vertical: {ny:+.0f} mm from axis<br>"
            f"Radial: r = {nres.r_from_axis_mm:.0f} mm  (r/R = {nres.r_from_axis_mm / R:.2f})<br>"
            f"Zone: {nres.zone.replace('_', ' ')}  ·  Code: {code_str}<br>"
            f"Edge → shell wall: {nres.edge_to_shell_mm:.0f} mm"
        )
        if nres.edge_to_knuckle_mm is not None:
            hover += f"<br>Edge → crown boundary: {nres.edge_to_knuckle_mm:.0f} mm"

        # OD circle (filled)
        fig.add_trace(go.Scatter(
            x=[nOR * math.cos(t) for t in nz_theta],
            y=[ny + nOR * math.sin(t) for t in nz_theta],
            fill="toself", fillcolor=_hex_alpha(nc, 0.22),
            line=dict(color=nc, width=2.5), mode="lines",
            showlegend=False,
            hovertemplate=hover + "<extra></extra>",
        ))
        # Bore ID circle (dashed)
        fig.add_trace(go.Scatter(
            x=[bOR * math.cos(t) for t in nz_theta],
            y=[ny + bOR * math.sin(t) for t in nz_theta],
            mode="lines", line=dict(color=nc, width=1.0, dash="dot"),
            showlegend=False, hoverinfo="skip",
        ))
        # Tag annotation
        fig.add_annotation(
            x=0, y=ny + nOR + R * 0.03,
            text=f"<b>{nz_dict['tag']}</b>",
            showarrow=False, xanchor="center", yanchor="bottom",
            font=dict(size=9, color=nc),
            bgcolor="rgba(255,255,255,0.88)", borderpad=2,
        )

    # ── Layout ────────────────────────────────────────────────────────────────
    lim = R * 1.22
    fig.update_layout(
        height=430,
        margin=dict(l=5, r=5, t=36 if title else 12, b=5),
        plot_bgcolor="white", paper_bgcolor="white",
        title=dict(text=f"<b>{title}</b>",
                   font=dict(size=11, color="#334155"), x=0.5) if title else {},
        showlegend=True,
        legend=dict(
            orientation="h", x=0.5, y=-0.04,
            xanchor="center", yanchor="top",
            font=dict(size=8), bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#e2e8f0", borderwidth=1,
        ),
        xaxis=dict(range=[-lim, lim], scaleanchor="y", scaleratio=1,
                   zeroline=False, showgrid=False, showticklabels=False),
        yaxis=dict(range=[-lim, lim], zeroline=False, showgrid=False, showticklabels=False),
    )
    return fig


def _compare_nozzle_on_all_heads(
    Di: float, dn_mm: int, d_from_top_mm: float,
    nozzle_OD_mm: float, nozzle_t_mm: float, t_head_nom_mm: float,
    crown_ratio: float = 1.0, knuckle_ratio: float = 0.10,
    alpha_deg_cone: float = 30.0, ellipse_ratio: float = 2.0,
) -> list[dict]:
    """Evaluate one nozzle placement against every alternative head type."""
    rows: list[dict] = []
    base_kw = dict(
        crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
        alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
        nozzle_OD_mm=nozzle_OD_mm, nozzle_t_mm=nozzle_t_mm,
        t_head_nom_mm=t_head_nom_mm,
    )
    for ht, label, override_kw in _ENDCAP_ALT_HEADS:
        kw = {**base_kw, **override_kw}
        res = nozzle_on_head(ht, Di, d_from_top_mm, dn_mm, **kw)
        rows.append({"head_type": ht, "label": label, "res": res})
    return rows


def _endcap_edge_implications(
    nres,
    Di: float, t_head_nom_mm: float,
    code_key: str,
) -> list[dict]:
    """
    Return a list of {level, text} dicts describing engineering implications
    of a nozzle's proximity to the endcap edge and zone boundaries.
    Levels: "error" | "warning" | "info".
    """
    issues: list[dict] = []
    R = Di / 2.0
    r = nres.r_from_axis_mm
    nOR = nres.nozzle_OR_mm
    OD = nres.nozzle_OD_mm
    bore_ID = max(OD - 2.0 * nres.nozzle_t_mm, 1.0)
    edge_r = r + nOR
    edge_to_shell = nres.edge_to_shell_mm
    min_weld_clr = max(3.0 * t_head_nom_mm, 25.0)
    code = "EN 13445-3" if code_key == "EN" else "ASME VIII Div.1"
    cl_zone = "cl. 9 / UG-36" if code_key == "EN" else "UG-36 / UG-37"

    # 1 — OD physically overlaps shell wall (fatal)
    if not nres.geom_ok and edge_to_shell < 0:
        issues.append(dict(level="error", text=(
            f"**Nozzle OD overlaps the cylindrical shell** by {-edge_to_shell:.0f} mm — this geometry cannot be "
            f"built as drawn. The nozzle must be moved toward the vessel axis (increase d_from_top toward Di/2) "
            f"or a smaller DN must be used."
        )))
        return issues

    # 2 — Weld clearance to head-shell circumferential seam
    if 0 <= edge_to_shell < min_weld_clr:
        level = "warning"
        issues.append(dict(level=level, text=(
            f"**Weld clearance shortfall** — nozzle OD edge is only **{edge_to_shell:.0f} mm** from the "
            f"vessel inner wall, below the minimum **{min_weld_clr:.0f} mm** (= max(3·t_head, 25 mm) "
            f"per {code} cl. {'5.6 / UW-9' if code_key == 'EN' else 'UW-11'}).  \n"
            f"**Why it matters:** The head-to-shell circumferential weld toe must not overlap the nozzle "
            f"OD weld toe. Overlapping weld heat-affected zones create an uncontrolled metallurgical "
            f"condition that increases cracking risk and prevents valid PWHT. Inspection access is also "
            f"compromised.  \n"
            f"**Resolution:** (a) Move nozzle toward axis by ≥ {min_weld_clr - edge_to_shell:.0f} mm; "
            f"(b) switch to a **hemispherical head** (the head-shell weld moves to the apex, far from any "
            f"nozzle — this is the most common fix for large nozzles on small vessels); "
            f"(c) obtain a documented fabrication deviation agreed with the notified body (+4–8 weeks)."
        )))

    # 3 — Three-way stress near junction (even if weld clearance is technically met)
    if 0 < edge_to_shell < 0.5 * (Di * 0.10):
        issues.append(dict(level="warning", text=(
            f"**Three-way stress concentration near the head-shell junction** — nozzle OD edge is only "
            f"**{edge_to_shell:.0f} mm** from the vessel inner wall.  \n"
            f"**Engineering explanation:** At this proximity the stress fields from the nozzle opening, "
            f"the head/cylinder discontinuity bending, and the cylindrical shell hoop stress interact "
            f"simultaneously. This 3-way combination is outside the scope of area-replacement "
            f"formulas ({code} {cl_zone}), even when weld clearance is met.  \n"
            f"**Resolution:** Full 3D FEA with mesh refinement at the junction. Add at least 4–8 weeks to "
            f"the design schedule. Alternatively, move the nozzle significantly toward the axis or use a "
            f"hemispherical head so the nozzle sits well clear of the tangent weld."
        )))

    # 4 — Nozzle centre in the knuckle (torispherical / ellipsoidal)
    if nres.zone == "knuckle":
        if nres.head_type in (HeadType.TORISPHERICAL, HeadType.FLANGED_DISHED):
            issues.append(dict(level="error", text=(
                f"**Nozzle centre in the knuckle transition zone** — standard area-replacement "
                f"({code} {cl_zone}) is **not valid** in the knuckle.  \n"
                f"**Engineering explanation:** The knuckle is a torus transition whose stress field "
                f"combines membrane and bending components from both the spherical crown and the "
                f"cylindrical shell. Adding a nozzle opening there creates a 3-way stress concentration "
                f"(nozzle + knuckle bending + shell discontinuity) that no standard code formula covers.  \n"
                f"**Resolution options:**  \n"
                f"- Move nozzle toward the axis: d_from_top ≤ {nres.d_at_crown_end_mm:.0f} mm "
                f"(for upper half) or ≥ {Di - nres.d_at_crown_end_mm:.0f} mm (for lower half).  \n"
                f"- Switch to a **hemispherical head** — no knuckle, entire face is valid.  \n"
                f"- Switch to **F&D (ASME)** — shallower knuckle gives a larger crown zone.  \n"
                f"- Commission FEA per {code} cl. {'18 / Annex B' if code_key == 'EN' else 'Appendix 46'} "
                f"(typically 3–6 weeks with independent review)."
            )))
        elif nres.head_type == HeadType.ELLIPSOIDAL:
            issues.append(dict(level="warning", text=(
                f"**Nozzle in the compressive-stress zone of the ellipsoidal head** (r = {r:.0f} mm, "
                f"r/R = {r / R:.2f} > reversal boundary).  \n"
                f"**Engineering explanation:** Beyond the hoop-stress reversal radius the circumferential "
                f"membrane stress is compressive. Standard area-replacement assumes tensile hoop stress; "
                f"in the compressive zone the formula is non-conservative. The nozzle also influences local "
                f"buckling resistance of the compressive zone.  \n"
                f"**Resolution:** Move nozzle toward the axis (d_from_top ≤ {nres.d_at_crown_end_mm:.0f} mm) "
                f"or commission a detailed analysis / FEA."
            )))

    # 5 — Nozzle centre in crown zone but OD edge encroaches on boundary
    elif nres.edge_to_knuckle_mm is not None and nres.edge_to_knuckle_mm < 0:
        zone_name = ("knuckle" if nres.head_type in (HeadType.TORISPHERICAL, HeadType.FLANGED_DISHED)
                     else "compressive-stress zone")
        issues.append(dict(level="warning", text=(
            f"**Nozzle OD edge encroaches on the {zone_name}** by {-nres.edge_to_knuckle_mm:.0f} mm — "
            f"the nozzle centre is within the crown zone, but the outer OD circle crosses the boundary.  \n"
            f"**Implication:** The reinforcement limit zone (which extends 2.5·t_head beyond the bore edge) "
            f"will partially overlap the {zone_name}, where that material cannot be credited as valid "
            f"reinforcement under standard rules. The effective A_available is overstated. A corrected "
            f"calculation limiting the limit zone to the crown boundary is required."
        )))

    # 6 — Reinforcement limit zone extends into knuckle
    if nres.head_type in (HeadType.TORISPHERICAL, HeadType.FLANGED_DISHED, HeadType.ELLIPSOIDAL):
        rz_reach = min(2.5 * t_head_nom_mm, bore_ID / 2.0 + 2.5 * t_head_nom_mm)
        rz_outer = r + OD / 2.0 + rz_reach
        if nres.r_crown_end_mm is not None and rz_outer > nres.r_crown_end_mm:
            overflow = rz_outer - nres.r_crown_end_mm
            zone_name2 = ("knuckle" if nres.head_type != HeadType.ELLIPSOIDAL
                          else "compressive-stress zone")
            issues.append(dict(level="info", text=(
                f"**Reinforcement limit zone overflows the crown boundary by ≈ {overflow:.0f} mm** — "
                f"the code search window (≈ {rz_reach:.0f} mm beyond the bore edge) extends into the "
                f"{zone_name2}, where material cannot be credited as valid reinforcement.  \n"
                f"Recalculate A_available using a truncated limit zone that stops at the crown boundary "
                f"r_cj = {nres.r_crown_end_mm:.0f} mm."
            )))

    # 7 — Large opening (bore / Di)
    ratio = bore_ID / Di
    if ratio > 0.5:
        issues.append(dict(level="error", text=(
            f"**Large opening: bore/Di = {ratio:.0%} > 50 %** — standard area-replacement is invalid. "
            f"Pressure-area method or FEA is mandatory "
            f"({'EN 13445-3 cl. 9.7' if code_key == 'EN' else 'ASME App 1-7 / Div.2'}). "
            f"Reinforcing insert or integral forging likely required. Add 4–8 weeks for specialist analysis."
        )))
    elif ratio > 1 / 3:
        issues.append(dict(level="warning", text=(
            f"**Large opening: bore/Di = {ratio:.0%} > 33 %** — enhanced reinforcement check required "
            f"({'EN 13445-3 cl. 9.5/9.7' if code_key == 'EN' else 'ASME UG-36(b)(1)'}). "
            f"Confirm the reinforcement limit zone does not overflow into the knuckle or off the head."
        )))

    # 8 — Nozzle on a steeply curved surface (axial depth > 50 % of head depth)
    if nres.head_depth_mm > 0 and nres.z_on_head_mm > 0.5 * nres.head_depth_mm:
        issues.append(dict(level="info", text=(
            f"**Nozzle sits at {nres.z_on_head_mm:.0f} mm axial depth "
            f"({nres.z_on_head_mm / nres.head_depth_mm * 100:.0f} % of head depth "
            f"{nres.head_depth_mm:.0f} mm)** — the weld is on a steeply curved surface.  \n"
            f"Pre-weld inspection and compound-curvature awareness are required. NDT probe angles "
            f"must be adjusted for the local curvature. Confirm this with the fabricator's weld engineer."
        )))

    return issues


def _render_head_comparison_table(
    comp_rows: list[dict], current_head_type: HeadType,
) -> None:
    """Render the alternative-head comparison as a dataframe."""
    import pandas as pd
    table: list[dict] = []
    for row in comp_rows:
        res = row["res"]
        is_cur = row["head_type"] == current_head_type
        cur_mark = "▶ " if is_cur else "  "

        zone_map = {
            "crown":        "✓ Crown",
            "knuckle":      "⚠ Knuckle",
            "cone":         "✓ Cone",
            "flat":         "✓ Flat",
            "outside_head": "✗ Outside",
        }
        zone_sym = zone_map.get(res.zone, res.zone)
        geom_sym = "✓" if res.geom_ok else "✗"
        code_sym = ("✓" if res.code_ok is True
                    else ("?" if res.code_ok is None else "✗"))
        e2s  = f"{res.edge_to_shell_mm:.0f} mm"
        e2k  = (f"{res.edge_to_knuckle_mm:.0f} mm"
                if res.edge_to_knuckle_mm is not None else "—")
        depth = f"{res.head_depth_mm:.0f} mm"
        crown_lim = (f"≤ {res.d_at_crown_end_mm:.0f} mm from top"
                     if res.d_at_crown_end_mm is not None else "—")
        note = _ENDCAP_HEAD_NOTES.get(row["label"], "")

        table.append({
            "Head type":         cur_mark + row["label"],
            "Zone":              zone_sym,
            "Geom":              geom_sym,
            "Code":              code_sym,
            "Edge→wall":         e2s,
            "Edge→boundary":     e2k,
            "Crown zone limit":  crown_lim,
            "Head depth":        depth,
            "Notes":             note,
        })
    df = pd.DataFrame(table)
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption(
        "▶ = currently selected head type  ·  Alternative heads use standard default geometry.  ·  "
        "⚠ Knuckle = centre in knuckle zone (standard rules invalid).  ·  "
        "? = code compliance uncertain (detailed analysis required)."
    )


# ──────────────────────── RESULT BADGE ───────────────────────────────────────

def _badge(label: str, ok: bool | None, detail: str = "") -> str:
    if ok is True:
        colour, icon = "#16a34a", "✓"
    elif ok is False:
        colour, icon = "#dc2626", "✗"
    else:
        colour, icon = "#d97706", "?"
    style = (f"display:inline-block;padding:4px 10px;border-radius:6px;"
             f"background:{colour}18;color:{colour};border:1px solid {colour}44;"
             f"font-weight:600;font-size:0.87em;")
    tip = f' title="{detail}"' if detail else ""
    return f'<span style="{style}"{tip}>{icon} {label}</span>'


# ──────────────────────── MAIN APP ───────────────────────────────────────────

def main():
    st.title("VesselCalc — Pressure Vessel Screener")

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        project_name = st.text_input("Project name", value="", key="project_name",
                                     placeholder="e.g. Offshore Platform Alpha")
        vessel_tag   = st.text_input("Equipment tag", value="V-1001", key="vessel_tag")
        issued_for   = st.selectbox(
            "Issued for", ["Inquiry", "HAZOP review", "Approval", "Construction"],
            key="issued_for",
        )

        _rb1, _rb2 = st.columns(2)
        _gen_btn      = _rb1.button("Datasheet", type="secondary",
                                     key="gen_report_btn", use_container_width=True)
        _gen_word_btn = _rb2.button("Report", type="secondary",
                                     key="gen_word_btn", use_container_width=True)

        if "report_html" in st.session_state:
            st.download_button(
                "📥 Download HTML (print to PDF)",
                data=st.session_state["report_html"],
                file_name=st.session_state.get("report_fname", "datasheet.html"),
                mime="text/html",
                key="dl_report",
                use_container_width=True,
            )
        if "report_docx" in st.session_state:
            st.download_button(
                "📥 Download Word (.docx)",
                data=st.session_state["report_docx"],
                file_name=st.session_state.get("report_docx_fname", "design_report.docx"),
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="dl_word",
                use_container_width=True,
            )
        st.divider()

        st.header("Vessel parameters")

        code = st.radio("Design code", ["EN 13445-3", "ASME VIII Div.1"],
                        horizontal=True, key="code")
        code_key = "EN" if code.startswith("EN") else "ASME"

        Di = st.number_input("Inner diameter Di (mm)", min_value=100.0, max_value=10000.0,
                             value=1800.0, step=50.0, key="Di")
        L_shell = st.number_input("Shell length T-T (mm)", min_value=100.0, max_value=50000.0,
                                  value=6000.0, step=100.0, key="L_shell",
                                  help="Tangent-to-tangent cylinder length (excludes head depths).")
        P_op_barg = st.number_input("Operating pressure (barg)", min_value=0.0, max_value=500.0,
                                    value=18.0, step=0.5, key="P_op_barg")
        T_op_C = st.number_input("Operating temperature (°C)", min_value=-200.0, max_value=500.0,
                                  value=90.0, step=5.0, key="T_op_C")
        P_barg = st.number_input("Design pressure (barg)", min_value=0.1, max_value=500.0,
                                 value=20.0, step=0.5, key="P_barg")
        T_C = st.number_input("Design temperature (°C)", min_value=-200.0, max_value=500.0,
                              value=100.0, step=5.0, key="T_C")

        mat_options = {k: v["name"] for k, v in MATERIALS.items()
                       if v["code"] in (code_key, "BOTH")}
        if not mat_options:
            mat_options = {k: v["name"] for k, v in MATERIALS.items()}
        mat_key = st.selectbox("Material", options=list(mat_options.keys()),
                               format_func=lambda k: MATERIALS[k].get("short", MATERIALS[k]["name"][:55]),
                               key="material")

        CA_mm = st.number_input("Corrosion allowance CA (mm)", min_value=0.0,
                                max_value=20.0, value=3.0, step=0.5, key="CA")
        z_weld = st.slider("Weld joint efficiency z", min_value=0.7, max_value=1.0,
                           value=1.0, step=0.05, key="z_weld")

        st.divider()
        st.header("Endcap (head)")

        head_label_map = {
            HeadType.HEMISPHERICAL:  "Hemispherical",
            HeadType.ELLIPSOIDAL:    "Ellipsoidal 2:1",
            HeadType.TORISPHERICAL:  "Torispherical (Klöpper / dished)",
            HeadType.FLANGED_DISHED: "Flanged & Dished — ASME F&D",
            HeadType.CONICAL:        "Conical",
            HeadType.FLAT:           "Flat (unstayed)",
        }
        head_type = st.selectbox(
            "Head type",
            options=list(head_label_map.keys()),
            format_func=lambda h: head_label_map[h],
            key="head_type",
        )

        crown_ratio, knuckle_ratio, alpha_deg_cone, ellipse_ratio = 1.0, 0.1, 30.0, 2.0
        with st.expander("Head geometry (advanced)", expanded=False):
            if head_type == HeadType.TORISPHERICAL:
                crown_ratio = st.number_input(
                    "Crown radius ratio R_c/Di", min_value=0.5, max_value=1.5,
                    value=1.0, step=0.05, key="crown_ratio",
                    help="Standard Klöpper: 1.0 (R_c = Di).  Korbbogen: 0.8.")
                knuckle_ratio = st.number_input(
                    "Knuckle radius ratio r_k/Di", min_value=0.06, max_value=0.3,
                    value=0.1, step=0.01, key="knuckle_ratio",
                    help="Minimum per EN/ASME: 0.06.")
            elif head_type == HeadType.FLANGED_DISHED:
                crown_ratio   = 1.0
                knuckle_ratio = 0.06
                st.info(
                    "**Fixed geometry per ASME UG-32(e):**  "
                    "Crown R_c = Di · Knuckle r_k = 0.06·Di (code minimum).  "
                    "Shallower than Klöpper (r_k = 0.10·Di); larger crown zone."
                )
            elif head_type == HeadType.CONICAL:
                alpha_deg_cone = st.number_input(
                    "Half-apex angle α (°)", min_value=5.0, max_value=75.0,
                    value=30.0, step=1.0, key="alpha_deg")
            elif head_type == HeadType.ELLIPSOIDAL:
                ellipse_ratio = st.number_input(
                    "Ellipse ratio Di/(2h)", min_value=1.0, max_value=4.0,
                    value=2.0, step=0.1, key="ellipse_ratio",
                    help="2.0 = standard 2:1 semi-ellipsoidal.")

        st.divider()
        st.header("Saddle supports")

        # Rescale saddle position proportionally when L_shell changes
        _prev_L = st.session_state.get("_saddle_prev_L_shell")
        if _prev_L is None:
            # First render — seed the key from the formula
            st.session_state["saddle_a"] = float(round(L_shell * 0.2 / 50) * 50)
        elif _prev_L != L_shell and _prev_L > 0:
            cur = st.session_state.get("saddle_a", L_shell * 0.2)
            scaled = cur * (L_shell / _prev_L)
            # clamp to valid range and snap to nearest 50 mm step
            scaled = float(round(min(scaled, L_shell / 2) / 50) * 50)
            st.session_state["saddle_a"] = scaled
        st.session_state["_saddle_prev_L_shell"] = L_shell

        saddle_a_mm = st.number_input(
            "Saddle position — from tangent (mm)",
            min_value=0.0, max_value=float(L_shell / 2),
            value=float(round(L_shell * 0.2 / 50) * 50),   # used only if key absent
            step=50.0, key="saddle_a",
            help="Distance from each tangent line to the saddle centreline. "
                 "Rule of thumb: ~0.2 × shell length.",
        )
        saddle_w_mm = st.number_input(
            "Saddle width (mm)",
            min_value=50.0, max_value=2000.0,
            value=max(200.0, float(round(Di * 0.12 / 50) * 50)),
            step=50.0, key="saddle_w",
            help="Contact width of saddle against vessel.",
        )

        # ── Nozzle session-state init (UI is in the main area, below the drawing) ─
        if "nozzles" not in st.session_state:
            st.session_state["nozzles"] = _default_nozzles(Di, L_shell)

        pn_options     = [p for p in EN_PN_RATINGS if p >= 1] if code_key == "EN" else list(ASME_CLASS_PRESSURE_20C.keys())
        pn_label       = "PN" if code_key == "EN" else "Class"
        pn_default     = 25 if code_key == "EN" else pn_options[1]
        pn_default_idx = pn_options.index(pn_default) if pn_default in pn_options else 0

        st.divider()
        st.header("Volume levels")

        include_heads = st.checkbox("Include endcap volumes", value=True, key="incl_heads")

        _lvl_unit_col, _ = st.columns([1, 2])
        level_unit = _lvl_unit_col.radio(
            "Level input unit", ["% Di", "mm"],
            horizontal=True, key="level_unit",
            label_visibility="collapsed",
        )
        if level_unit == "% Di":
            st.caption("Set each level as % of inner diameter (0 % = bottom, 100 % = top)")
        else:
            st.caption(f"Set each level in mm from vessel bottom (0 mm = bottom, {Di:.0f} mm = top)")

        _LEVEL_DEFAULTS_PCT = {
            "LZLL": 5, "LALL": 10, "LAL": 20, "NLL": 50,
            "LAH": 75, "LAHH": 85, "LZHH": 95,
        }

        # When the unit toggle changes, convert existing values into the new unit's keys
        # so the user's work is preserved rather than reset to defaults.
        _prev_unit = st.session_state.get("_level_unit_prev")
        if _prev_unit is not None and _prev_unit != level_unit:
            for _tag in _LEVEL_DEFAULTS_PCT:
                if level_unit == "mm" and f"lvl_pct_{_tag}" in st.session_state:
                    st.session_state[f"lvl_mm_{_tag}"] = round(
                        st.session_state[f"lvl_pct_{_tag}"] / 100.0 * Di, 1)
                elif level_unit == "% Di" and f"lvl_mm_{_tag}" in st.session_state:
                    st.session_state[f"lvl_pct_{_tag}"] = round(
                        min(100.0, st.session_state[f"lvl_mm_{_tag}"] / Di * 100.0), 2)
        st.session_state["_level_unit_prev"] = level_unit

        levels_mm_vol: dict[str, float] = {}
        for tag, default_pct in _LEVEL_DEFAULTS_PCT.items():
            colour = _LEVEL_STYLE[tag][0]
            c1, c2 = st.columns([1, 2])
            c1.markdown(
                f'<span style="color:{colour};font-weight:700">{tag}</span>',
                unsafe_allow_html=True,
            )
            if level_unit == "% Di":
                pct = c2.number_input(
                    "% Di", min_value=0.0, max_value=100.0,
                    value=float(default_pct), step=1.0,
                    key=f"lvl_pct_{tag}", label_visibility="collapsed",
                )
                levels_mm_vol[tag] = pct / 100.0 * Di
            else:
                default_mm = default_pct / 100.0 * Di
                mm_val = c2.number_input(
                    "mm", min_value=0.0, max_value=float(Di),
                    value=round(default_mm, 1), step=10.0,
                    key=f"lvl_mm_{tag}", label_visibility="collapsed",
                )
                levels_mm_vol[tag] = mm_val

        st.divider()
        st.header("Separator process")
        st.caption(f"Operating conditions from vessel parameters: **{P_barg:.1f} barg, {T_C:.0f} °C**")

        L_baffle_mm = st.number_input(
            "Baffle setback from tangent (mm)", min_value=0.0, max_value=float(L_shell / 2),
            value=400.0, step=50.0, key="L_baffle",
            help="Axial distance from each tangent line to the inlet baffle. "
                 "Effective separation length = shell length − 2 × this value.",
        )

        # ── Gas phase ─────────────────────────────────────────────────────────
        st.markdown("**Gas phase**")
        gas_fluid = st.selectbox("Gas fluid", GAS_FLUIDS, key="gas_fluid",
                                  label_visibility="collapsed")
        if gas_fluid == "Custom":
            gc1, gc2, gc3 = st.columns(3)
            MW_gas_custom = gc1.number_input("MW (g/mol)", min_value=1.0, max_value=500.0,
                                              value=28.0, step=1.0, key="gas_MW_custom")
            mu_gas_custom = gc2.number_input("μ (μPa·s)", min_value=0.1, max_value=500.0,
                                              value=18.0, step=0.5, key="gas_mu_custom")
            Z_gas = gc3.number_input("Z", min_value=0.1, max_value=2.0,
                                      value=1.0, step=0.05, key="gas_Z_custom")
            gas_props = gas_properties("Custom", T_C, P_barg,
                                       MW_custom=MW_gas_custom,
                                       mu_custom_uPas=mu_gas_custom, Z=Z_gas)
        else:
            Z_gas = st.number_input("Compressibility Z", min_value=0.1, max_value=2.0,
                                     value=1.0, step=0.05, key="gas_Z")
            gas_props = gas_properties(gas_fluid, T_C, P_barg, Z=Z_gas)
        st.caption(f"ρ = **{gas_props.rho_kgm3:.3f} kg/m³**  ·  "
                   f"μ = **{gas_props.mu_Pas*1e6:.1f} μPa·s**  ·  "
                   f"MW = {gas_props.MW:.2f} g/mol")

        _gas_unit = st.radio("Gas flow unit", ["m³/h (actual)", "kg/h"],
                              horizontal=True, key="gas_flow_unit",
                              label_visibility="collapsed")
        if _gas_unit == "kg/h":
            Q_gas_kgh = st.number_input("Gas flow rate (kg/h)", min_value=0.001,
                                         max_value=1e9, value=1000.0, step=10.0, key="Q_gas_kgh")
            Q_gas_m3h = Q_gas_kgh / max(gas_props.rho_kgm3, 1e-6)
            st.caption(f"= **{Q_gas_m3h:,.1f} m³/h** actual at {P_barg:.1f} barg, {T_C:.0f} °C")
        else:
            Q_gas_m3h = st.number_input("Gas flow rate (m³/h, actual)", min_value=0.001,
                                         max_value=1e7, value=1000.0, step=10.0, key="Q_gas")
            st.caption(f"= **{Q_gas_m3h * gas_props.rho_kgm3:,.0f} kg/h**")

        # ── Liquid phase ──────────────────────────────────────────────────────
        st.markdown("**Liquid phase**")
        liq_fluid = st.selectbox("Liquid fluid", LIQ_FLUIDS, key="liq_fluid",
                                  label_visibility="collapsed")
        if liq_fluid == "Glycol (EG)":
            eg_conc = st.number_input("EG concentration (wt%)", min_value=0.0, max_value=100.0,
                                       value=30.0, step=5.0, key="eg_conc")
            liq_props = liquid_properties("Glycol (EG)", T_C, eg_conc_pct=eg_conc)
        elif liq_fluid == "Custom":
            lc1, lc2 = st.columns(2)
            rho_liq_custom = lc1.number_input("ρ (kg/m³)", min_value=100.0, max_value=3000.0,
                                               value=1000.0, step=10.0, key="liq_rho_custom")
            mu_liq_custom  = lc2.number_input("μ (mPa·s)", min_value=0.01, max_value=10000.0,
                                               value=1.0, step=0.1, key="liq_mu_custom")
            liq_props = liquid_properties("Custom", T_C,
                                          rho_custom=rho_liq_custom,
                                          mu_custom_mPas=mu_liq_custom)
        else:
            liq_props = liquid_properties(liq_fluid, T_C)
        st.caption(f"ρ = **{liq_props.rho_kgm3:.0f} kg/m³**  ·  "
                   f"μ = **{liq_props.mu_Pas*1e3:.3f} mPa·s**")
        Q_liq_m3h = st.number_input("Liquid flow rate (m³/h)", min_value=0.001,
                                     max_value=1e6, value=10.0, step=1.0, key="Q_liq")

        # convenience aliases kept for separator_check call below
        rho_gas = gas_props.rho_kgm3
        rho_liq = liq_props.rho_kgm3

        # ── Internals ─────────────────────────────────────────────────────────
        st.markdown("**Internals**")

        def _yn(label, key, default="Yes"):
            return st.radio(label, ["Yes", "No"], index=0 if default == "Yes" else 1,
                            horizontal=True, key=key) == "Yes"

        has_baffles       = _yn("Baffle plates",               "has_baffles")
        baffle_open_pct   = 20.0
        if has_baffles:
            baffle_open_pct = st.number_input(
                "Baffle opening area (%)", min_value=5.0, max_value=60.0,
                value=20.0, step=5.0, key="baffle_open_pct",
                help="Fraction of baffle plate that is open (holes/slots). "
                     "Typical: 15–25 %.",
            )

        has_inlet_dev = _yn("Inlet device (half-pipe)", "has_inlet_dev")

        has_meshpad = _yn("Mesh pad demister", "has_meshpad")
        K_pad = 0.10
        if has_meshpad:
            K_pad = st.number_input(
                "Mesh pad K factor (m/s)", min_value=0.03, max_value=0.25,
                value=0.10, step=0.01, key="K_pad",
                help="Souders-Brown K for mesh pad. Typical 0.07–0.12 m/s "
                     "(use lower end for high-pressure or foaming service).",
            )

        has_vortex_brk = _yn("Vortex breaker (liquid outlet)", "has_vortex")

        # ── Separator settings ────────────────────────────────────────────────
        st.markdown("**Separator settings**")
        if not has_meshpad:
            K_sb = st.number_input(
                "Souders-Brown K (open vessel, m/s)", min_value=0.01, max_value=0.5,
                value=0.06, step=0.01, key="K_sb",
                help="Typical: 0.04–0.07 without demister.",
            )
        else:
            K_sb = K_pad   # mesh pad K overrides
            st.caption(f"Gas velocity check uses mesh pad K = {K_pad:.2f} m/s")
        t_holdup_req = st.number_input(
            "Required hold-up time (min)", min_value=0.5, max_value=60.0,
            value=3.0, step=0.5, key="t_holdup_req",
            help="Liquid volume at NLL ÷ liquid flow rate. Ensures enough liquid inventory "
                 "for stable level control. Typical: 1–3 min for well-instrumented separators.",
        )

        # Surge check — optional
        include_surge_check = st.radio(
            "Surge volume check", ["Required", "Not required"],
            horizontal=True, key="include_surge",
            help="Surge volume = time to fill from NLL to LAHH at full liquid flow rate. "
                 "Disable when level control is fast-acting or surge buffering is provided elsewhere.",
        ) == "Required"
        t_surge_req = 3.0   # default when not required
        if include_surge_check:
            t_surge_req = st.number_input(
                "Required surge time (min)", min_value=0.5, max_value=60.0,
                value=3.0, step=0.5, key="t_surge_req",
                help="Time to fill from NLL to LAHH at full liquid flow rate. "
                     "Represents the operator/control-system response window. Typical: 2–5 min.",
            )

        st.divider()
        st.markdown("**LDV — Liquid Design Volume**")
        st.caption(
            "Minimum liquid inventory required to fill downstream equipment that are "
            "partially empty during operation or startup. "
            "LDV = (VB → LZLL) × SF  +  (LALL → LAL)."
        )
        include_ldv = _yn("Calculate LDV", "include_ldv")
        vb_offset_mm = 0.0
        ldv_sf = 1.5
        ldv_target_m3: float | None = None   # None = not set
        if include_ldv:
            vb_offset_mm = st.number_input(
                "Minimum VB level — vessel bottom + (mm)",
                min_value=0.0, max_value=float(Di * 0.25), value=0.0, step=25.0,
                key="vb_offset_mm",
                help="Raise the effective vessel bottom for LDV. Use to account for pump "
                     "suction deadband, instrument dead zone, or settled solids. "
                     "0 = use actual vessel bottom.",
            )
            ldv_sf = st.number_input(
                "Safety factor — VB → LZLL zone",
                min_value=1.0, max_value=3.0, value=1.5, step=0.05,
                key="ldv_sf",
                help="The VB→LZLL volume is multiplied by this factor before adding to the LDV. "
                     "Accounts for instrument uncertainty, cavitation margin, and measurement deadband. "
                     "Typical: 1.25–2.0.",
            )
            if _yn("Set specific LDV target", "ldv_set_target", default="No"):
                _ldv_target_L = st.number_input(
                    "Required LDV — before safety factor (L)",
                    min_value=0.0, max_value=100000.0, value=500.0, step=10.0,
                    key="ldv_target_L",
                    help="Volume of downstream equipment that must be filled "
                         "(before any safety factor). The safety factor is applied "
                         "separately to give the conservative requirement.",
                )
                ldv_target_m3 = _ldv_target_L / 1000.0

    # ── Sync nozzle widget values into session_state["nozzles"] ────────────────
    # The nozzle editor renders BELOW the chart, so we must pull the latest
    # widget values into the nozzle dicts BEFORE running any computation.
    for _i, _nz in enumerate(st.session_state.get("nozzles", [])):
        for _field, _skey in [
            ("tag",     f"nz_{_i}_tag"),
            ("service", f"nz_{_i}_svc"),
            ("loc",     f"nz_{_i}_loc"),
            ("dn",      f"nz_{_i}_dn"),
            ("pn",      f"nz_{_i}_pn"),
        ]:
            if _skey in st.session_state:
                _nz[_field] = st.session_state[_skey]
        if f"nz_{_i}_pos" in st.session_state:
            _pos = st.session_state[f"nz_{_i}_pos"]
            if _nz.get("loc") in ("Left head", "Right head"):
                _nz["d_from_top"] = _pos
            else:
                _nz["axial_mm"] = _pos

    # ── Compute ───────────────────────────────────────────────────────────────
    stress   = allowable_stress(mat_key, T_C, code_key)
    fd       = stress["fd_MPa"]

    shell_res = shell_thickness(Di, P_barg, fd, z=z_weld, CA_mm=CA_mm, code=code_key)

    head_res = head_thickness(
        head_type, Di, P_barg, fd, z=z_weld, CA_mm=CA_mm, code=code_key,
        crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
        alpha_deg=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
    )

    R_c = crown_ratio * Di
    r_k = knuckle_ratio * Di
    b   = Di / (2 * ellipse_ratio)

    # ── Nozzle results loop ───────────────────────────────────────────────────
    nozzle_results: list[tuple] = []
    for nz in st.session_state.get("nozzles", []):
        nz_OD = NOZZLE_OD.get(nz["dn"], nz["dn"] * 1.05)
        nz_pn = nz.get("pn", 25)
        rec   = recommended_schedule(nz_pn, code_key)
        nz_t  = float(NOZZLE_WALL_SCH[rec].get(nz["dn"], NOZZLE_WALL_T.get(nz["dn"], 8.0)))

        if nz["loc"] in ("Left head", "Right head"):
            nres = nozzle_on_head(
                head_type, Di, nz["d_from_top"], nz["dn"],
                crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
                alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
                nozzle_OD_mm=nz_OD, nozzle_t_mm=nz_t,
                t_head_nom_mm=head_res.t_nom_mm,
            )
            rres = reinforcement_check(
                Di=Di, P_barg=P_barg, fd_MPa=fd,
                nozzle_OD_mm=nz_OD, nozzle_t_mm=nz_t,
                t_head_req_mm=head_res.t_calc_mm,
                t_head_nom_mm=head_res.t_nom_mm,
                CA_mm=CA_mm, code=code_key, z=z_weld,
                space_to_wall_mm=nres.edge_to_shell_mm,
                space_to_knuckle_mm=nres.edge_to_knuckle_mm,
            )
        else:  # shell nozzle — no zone check, use shell wall thickness
            nres = None
            rres = reinforcement_check(
                Di=Di, P_barg=P_barg, fd_MPa=fd,
                nozzle_OD_mm=nz_OD, nozzle_t_mm=nz_t,
                t_head_req_mm=shell_res.t_calc_mm,
                t_head_nom_mm=shell_res.t_nom_mm,
                CA_mm=CA_mm, code=code_key, z=z_weld,
                space_to_wall_mm=None, space_to_knuckle_mm=None,
            )

        # Per-nozzle flange check
        pn_v = nz.get("pn", 25)
        if code_key == "EN":
            pn_at_T_nz = max_pn_for_temperature(float(pn_v), T_C)
            flange_ok_nz = P_barg <= pn_at_T_nz
        else:
            pn_at_T_nz = ASME_CLASS_PRESSURE_20C.get(str(pn_v), 999.0)
            flange_ok_nz = P_barg <= pn_at_T_nz

        nozzle_results.append((nz, nres, rres, flange_ok_nz, pn_at_T_nz))

    # Compute placement checks and build a severity map for nozzle visuals
    placement_checks = _nozzle_placement_checks(
        nozzle_results, Di, L_shell,
        t_shell_mm=shell_res.t_nom_mm, t_head_mm=head_res.t_nom_mm,
        saddle_a_mm=saddle_a_mm, saddle_w_mm=saddle_w_mm,
        code_key=code_key,
    )
    severity_map: dict[str, str] = {}
    for ch in placement_checks:
        for tag in ch.tags:
            # preserve error over warning if multiple checks apply
            if severity_map.get(tag) == "error":
                continue
            if ch.level == "error":
                severity_map[tag] = "error"
            elif ch.level == "warning":
                severity_map.setdefault(tag, "warning")

    # ── Vessel drawing (full width) ───────────────────────────────────────────
    fig = _vessel_figure(
        head_type, Di, R_c, r_k, alpha_deg_cone, b,
        t_head_nom=head_res.t_nom_mm,
        t_shell_nom=shell_res.t_nom_mm,
        nozzle_results=[(nz, nr, rr) for nz, nr, rr, _f, _p in nozzle_results],
        L_shell=L_shell,
        levels_mm=levels_mm_vol,
        L_baffle_mm=L_baffle_mm,
        saddle_a_mm=saddle_a_mm,
        saddle_w_mm=saddle_w_mm,
        has_baffles=has_baffles,
        baffle_open_pct=baffle_open_pct,
        has_inlet_dev=has_inlet_dev,
        has_meshpad=has_meshpad,
        nll_mm=levels_mm_vol.get("NLL", Di * 0.5),
        has_vortex_brk=has_vortex_brk,
        nozzle_checks=severity_map,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    _ud1, *_ = st.columns([1, 6])
    if _ud1.button("🔄 Update drawing", help="Click after editing the nozzle table below to refresh the sketch"):
        st.rerun()

    # ── Inline nozzle editor — directly below the drawing ────────────────────
    nozzles: list[dict] = st.session_state["nozzles"]
    _nz_remove: int | None = None

    # Column header
    _hcols = st.columns([0.45, 1.3, 1.35, 0.6, 0.55, 1.1, 0.32])
    for _hc, _hl in zip(_hcols, ["Tag", "Service", "Location", "DN", pn_label, "Position", ""]):
        _hc.caption(_hl)

    for i, nz in enumerate(nozzles):
        c1, c2, c3, c4, c5, c6, c7 = st.columns([0.45, 1.3, 1.35, 0.6, 0.55, 1.1, 0.32])
        nz["tag"] = c1.text_input("Tag", value=nz["tag"], key=f"nz_{i}_tag",
                                   label_visibility="collapsed", placeholder="Tag")
        nz["service"] = c2.selectbox("Service", _NOZZLE_SERVICES,
                                      index=_NOZZLE_SERVICES.index(nz["service"]) if nz["service"] in _NOZZLE_SERVICES else 0,
                                      key=f"nz_{i}_svc", label_visibility="collapsed")
        nz["loc"] = c3.selectbox("Location", _NOZZLE_LOCS,
                                  index=_NOZZLE_LOCS.index(nz["loc"]) if nz["loc"] in _NOZZLE_LOCS else 0,
                                  key=f"nz_{i}_loc", label_visibility="collapsed")
        nz["dn"] = c4.selectbox("DN", DN_SIZES,
                                 index=DN_SIZES.index(nz["dn"]) if nz["dn"] in DN_SIZES else 0,
                                 key=f"nz_{i}_dn", label_visibility="collapsed")
        _cur_pn     = nz.get("pn", pn_default)
        _cur_pn_idx = pn_options.index(_cur_pn) if _cur_pn in pn_options else pn_default_idx
        nz["pn"] = c5.selectbox(pn_label, pn_options, index=_cur_pn_idx,
                                 key=f"nz_{i}_pn", label_visibility="collapsed")
        if nz["loc"] in ("Left head", "Right head"):
            nz["d_from_top"] = c6.number_input(
                "d_from_top", min_value=0.0, max_value=float(Di),
                value=float(min(nz.get("d_from_top", Di / 2), Di)),
                step=10.0, key=f"nz_{i}_pos", label_visibility="collapsed",
                help="mm from top inner wall  (0 = top, Di/2 = axis, Di = bottom)",
            )
        else:
            nz["axial_mm"] = c6.number_input(
                "axial_mm", min_value=0.0, max_value=float(L_shell),
                value=float(min(nz.get("axial_mm", L_shell / 2), L_shell)),
                step=50.0, key=f"nz_{i}_pos", label_visibility="collapsed",
                help="mm from left tangent line",
            )
        if c7.button("×", key=f"nz_{i}_del", help="Remove"):
            _nz_remove = i

    if _nz_remove is not None:
        st.session_state["nozzles"].pop(_nz_remove)
        st.rerun()

    _ab1, _ab2, *_ = st.columns([0.9, 1.0, 5])
    if _ab1.button("＋ Add nozzle"):
        st.session_state["nozzles"].append({
            "tag": f"N{len(nozzles)+1}", "service": "Spare",
            "loc": "Shell — top", "dn": 50, "pn": pn_default,
            "d_from_top": Di / 2, "axial_mm": L_shell / 2,
        })
        st.rerun()
    if _ab2.button("Reset to default"):
        st.session_state["nozzles"] = _default_nozzles(Di, L_shell)
        st.rerun()

    # ── Nozzle placement checks ───────────────────────────────────────────────
    placement_checks = _nozzle_placement_checks(
        nozzle_results, Di, L_shell,
        t_shell_mm=shell_res.t_nom_mm,
        t_head_mm=head_res.t_nom_mm,
        saddle_a_mm=saddle_a_mm,
        saddle_w_mm=saddle_w_mm,
        code_key=code_key,
    )

    n_err  = sum(1 for c in placement_checks if c.level == "error")
    n_warn = sum(1 for c in placement_checks if c.level == "warning")
    n_info = sum(1 for c in placement_checks if c.level == "info")

    if placement_checks:
        summary_parts = []
        if n_err:  summary_parts.append(f"**{n_err} error{'s' if n_err>1 else ''}**")
        if n_warn: summary_parts.append(f"**{n_warn} warning{'s' if n_warn>1 else ''}**")
        if n_info: summary_parts.append(f"{n_info} advisory note{'s' if n_info>1 else ''}")
        with st.expander(
            f"⚠ Nozzle placement checks — {', '.join(summary_parts)}",
            expanded=(n_err + n_warn) > 0,
        ):
            for chk in placement_checks:
                tag_str  = f"**[{', '.join(chk.tags)}]** " if chk.tags else ""
                code_str = f"*{chk.code_ref}*" if chk.code_ref else ""
                body = (
                    f"{tag_str}{chk.headline}  \n"
                    f"{code_str}  \n"
                    f"{chk.detail}  \n"
                    f"💡 *{chk.impact}*"
                )
                if chk.level == "error":
                    st.error(body, icon="🚫")
                elif chk.level == "warning":
                    st.warning(body, icon="⚠️")
                else:
                    st.info(body, icon="ℹ️")
    else:
        st.success("✓ No nozzle placement issues detected.", icon="✅")

    st.divider()

    # ── Aggregate status badges ───────────────────────────────────────────────
    any_geom_fail  = any(nr is not None and not nr.geom_ok  for _, nr, _, _, _ in nozzle_results)
    any_code_fail  = any(nr is not None and nr.code_ok is False for _, nr, _, _, _ in nozzle_results)
    any_reinf_fail = any(rr is not None and rr.adequate is False for _, _, rr, _, _ in nozzle_results)
    any_flange_fail = any(not f for _, _, _, f, _ in nozzle_results)
    badges = (
        _badge("Geometry",      not any_geom_fail) + " " +
        _badge("Code zone",     None if any_code_fail is None else not any_code_fail) + " " +
        _badge("Reinforcement", not any_reinf_fail) + " " +
        _badge("Flange",        not any_flange_fail)
    )
    st.markdown(badges, unsafe_allow_html=True)

    # Messages from vessel checks (head/shell warnings)
    for msg in head_res.warnings + shell_res.warnings:
        st.warning(msg, icon="⚠️")
    # Nozzle-specific messages shown in per-nozzle expanders below

    import pandas as pd

    # ── Vessel calculation results ────────────────────────────────────────────
    r1c1, r1c2, r1c3 = st.columns(3)
    with r1c1:
        with st.expander("**Material & allowable stress**", expanded=False):
            mat = MATERIALS[mat_key]
            st.markdown(f"**{mat.get('short', mat['name'])}**")
            st.caption(mat['name'])
            st.caption(stress["basis"])
            st.metric("Allowable stress fd", f"{fd:.1f} MPa")
    with r1c2:
        with st.expander("**Shell thickness**", expanded=False):
            c1, c2 = st.columns(2)
            c1.metric("Calculated t", f"{shell_res.t_calc_mm:.2f} mm")
            c2.metric("Nominal (rounded up)", f"{shell_res.t_nom_mm:.1f} mm")
            st.caption(f"{shell_res.clause}  —  {shell_res.formula}")
    with r1c3:
        with st.expander("**Head thickness**", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("Calculated e", f"{head_res.t_calc_mm:.2f} mm")
            c2.metric("Nominal (rounded up)", f"{head_res.t_nom_mm:.1f} mm")
            # head depth from first head nozzle result if available
            _hd = next((nr.head_depth_mm for _, nr, _, _, _ in nozzle_results if nr), None)
            if _hd is not None:
                c3.metric("Head depth", f"{_hd:.1f} mm")
            st.caption(f"{head_res.clause}  —  {head_res.formula}")

    # ── Nozzle schedule ───────────────────────────────────────────────────────
    with st.expander("**Nozzle schedule**", expanded=True):
        lzhh_mm = levels_mm_vol.get("LZHH", 0.0)
        sched_rows = []
        for nz, nres, rres, flange_ok_nz, pn_at_T_nz in nozzle_results:
            nz_OD = NOZZLE_OD.get(nz["dn"], nz["dn"] * 1.05)
            rec   = recommended_schedule(nz.get("pn", 25), code_key)
            nz_t  = float(NOZZLE_WALL_SCH[rec].get(nz["dn"], NOZZLE_WALL_T.get(nz["dn"], 8.0)))
            geom_s  = ("✓" if (nres is None or nres.geom_ok) else "✗")
            code_s  = ("✓" if (nres is None or nres.code_ok is True) else ("?" if nres.code_ok is None else "✗"))
            reinf_s = ("✓" if (rres is None or rres.adequate) else "✗")
            flng_s  = "✓" if flange_ok_nz else "✗"

            # Bottom of nozzle bore to LZHH (for inlet nozzles on heads)
            lzhh_str = ""
            if nres is not None:
                nz_IR = (nz_OD - 2.0 * nz_t) / 2.0
                nz_bot = (Di - nres.d_from_top_mm) - nz_IR
                dist = lzhh_mm - nz_bot
                lzhh_str = f"{dist:+.0f} mm ({'sub.' if dist > 0 else 'clear'})"

            sched_rows.append({
                "Tag":      nz["tag"],
                "Service":  nz["service"],
                "Location": nz["loc"],
                "DN":       f"DN{nz['dn']}",
                f"{pn_label}": str(nz.get("pn", "")),
                "Geom":     geom_s,
                "Reinf":    reinf_s,
                "Flange":   flng_s,
                "Inlet→LZHH": lzhh_str,
            })
        st.dataframe(pd.DataFrame(sched_rows), hide_index=True, use_container_width=True)

    # ── Per-nozzle detail expanders ───────────────────────────────────────────
    nz_cols = st.columns(2)
    for idx, (nz, nres, rres, flange_ok_nz, pn_at_T_nz) in enumerate(nozzle_results):
        with nz_cols[idx % 2]:
            label = f"**{nz['tag']} — {nz['service']}** ({nz['loc']}, DN{nz['dn']})"
            with st.expander(label, expanded=False):
                nz_OD = NOZZLE_OD.get(nz["dn"], nz["dn"] * 1.05)
                rec   = recommended_schedule(nz.get("pn", 25), code_key)
                nz_t  = float(NOZZLE_WALL_SCH[rec].get(nz["dn"], NOZZLE_WALL_T.get(nz["dn"], 8.0)))

                for msg in (nres.errors + nres.warnings if nres else []) + (rres.warnings if rres else []):
                    st.warning(msg, icon="⚠️")

                if nres is not None:  # head nozzle — full geometry detail
                    R_loc = Di / 2
                    rows_ng = {
                        "OD / wall":    f"{nz_OD:.1f} mm OD  /  {nz_t:.1f} mm wall  (ID = {nz_OD - 2*nz_t:.1f} mm)",
                        "From top":     f"{nres.d_from_top_mm:.0f} mm",
                        "y from axis":  f"{nres.y_nozzle_mm:+.1f} mm",
                        "Axial depth":  f"{nres.z_on_head_mm:.1f} mm from tangent",
                        "Zone":         nres.zone.replace("_", " ").capitalize(),
                        "Edge to wall": f"{nres.edge_to_shell_mm:.1f} mm",
                    }
                    if head_type == HeadType.TORISPHERICAL:
                        if nres.d_at_crown_end_mm is not None:
                            rows_ng["Crown boundary"] = f"d = {nres.d_at_crown_end_mm:.0f} mm from top"
                        if nres.edge_to_knuckle_mm is not None:
                            rows_ng["Edge to knuckle"] = f"{nres.edge_to_knuckle_mm:.1f} mm"
                    nz_IR = (nz_OD - 2.0 * nz_t) / 2.0
                    nz_bot = (Di - nres.d_from_top_mm) - nz_IR
                    dist = lzhh_mm - nz_bot
                    rows_ng["Inlet bottom → LZHH"] = f"{dist:+.0f} mm ({'submerged at LZHH' if dist > 0 else 'clear at LZHH'})"
                    for k, v in rows_ng.items():
                        ca, cb = st.columns([1.4, 1.6])
                        ca.markdown(f"*{k}*"); cb.markdown(f"**{v}**")
                    st.caption(f"Schedule {rec}  ·  PN/Class {nz.get('pn', '')}")
                else:  # shell nozzle — just reinforcement
                    st.caption(f"{nz['loc']}  ·  axial {nz.get('axial_mm', 0):.0f} mm from left tangent")
                    st.caption(f"Schedule {rec}  ·  OD {nz_OD:.1f} mm / wall {nz_t:.1f} mm")

                if rres is not None:
                    delta_v = rres.A_total_mm2 - rres.A_required_mm2
                    rc1, rc2 = st.columns(2)
                    rc1.metric("A required",  f"{rres.A_required_mm2:,.0f} mm²")
                    rc1.metric("A available", f"{rres.A_total_mm2:,.0f} mm²")
                    surplus_label = "surplus" if delta_v >= 0 else "deficit"
                    rc2.metric("Surplus/deficit", f"{abs(delta_v):,.0f} mm²",
                               delta=f"{surplus_label} {delta_v:+,.0f} mm²",
                               delta_color="normal" if delta_v >= 0 else "inverse")
                    pn_label_str = f"PN{nz.get('pn','')} rated {pn_at_T_nz:.1f} barg at {T_C:.0f} °C"
                    if flange_ok_nz:
                        st.success(f"Flange OK  ·  {pn_label_str}")
                    else:
                        st.error(f"Flange FAIL  ·  {pn_label_str} < {P_barg:.1f} barg design")

    # ── Endcap nozzle analysis ────────────────────────────────────────────────
    _endcap_nz = [(nz, nres) for nz, nres, *_ in nozzle_results if nres is not None]
    if _endcap_nz:
        st.divider()
        with st.expander(
            "**Endcap nozzle analysis — edge proximity, zone evaluation & alternative head types**",
            expanded=True,
        ):
            st.markdown(
                "Detailed evaluation of nozzle placement on the endcaps. "
                "For each endcap nozzle the section shows: **(1)** a face-on view of the head "
                "with zone boundaries and nozzle OD circles; **(2)** engineering implications of "
                "nozzle proximity to the edge of the head (weld clearance, knuckle zone, 3-way "
                "stress); **(3)** how the same nozzle would behave on alternative head types."
            )

            # ── Face-on views (left and right head, side by side) ─────────────
            _left_nz  = [(nz, nres) for nz, nres in _endcap_nz if nz["loc"] == "Left head"]
            _right_nz = [(nz, nres) for nz, nres in _endcap_nz if nz["loc"] == "Right head"]

            if _left_nz or _right_nz:
                _fc1, _fc2 = st.columns(2)
                if _left_nz:
                    _fc1.plotly_chart(
                        _endcap_face_figure(
                            head_type, Di, R_c, r_k, b, head_res.t_nom_mm,
                            _left_nz, "Left head — face-on view (looking inward)",
                        ),
                        use_container_width=True, config={"displayModeBar": False},
                    )
                if _right_nz:
                    _fc2.plotly_chart(
                        _endcap_face_figure(
                            head_type, Di, R_c, r_k, b, head_res.t_nom_mm,
                            _right_nz, "Right head — face-on view (looking inward)",
                        ),
                        use_container_width=True, config={"displayModeBar": False},
                    )

            st.markdown(
                "> **Reading the face-on view:** Green fill = crown zone (standard analysis valid); "
                "amber fill = knuckle / compressive-stress zone (specialist analysis required); "
                "red ring = weld-exclusion zone (nozzle OD edge must stay inside). "
                "Nozzles shown with OD circle (solid) and bore ID circle (dashed). "
                "All nozzles are on the head's vertical centre plane (x = 0); "
                "their vertical position reflects d_from_top."
            )

            st.divider()

            # ── Per-nozzle detailed analysis ──────────────────────────────────
            for nz, nres in _endcap_nz:
                R_loc = Di / 2.0
                r_loc = nres.r_from_axis_mm
                nOR   = nres.nozzle_OR_mm
                min_weld_clr_h = max(3.0 * head_res.t_nom_mm, 25.0)
                nc    = _nozzle_zone_color(nres)

                st.markdown(
                    f"### {nz['tag']} — {nz['service']}  "
                    f"<span style='font-size:0.85em;color:#64748b'>DN{nz['dn']}  ·  {nz['loc']}</span>",
                    unsafe_allow_html=True,
                )

                # Key position metrics
                _m1, _m2, _m3, _m4, _m5 = st.columns(5)
                _m1.metric("r / R", f"{r_loc / R_loc:.3f}",
                           help="Radial offset from vessel axis ÷ vessel radius. "
                                "0 = on axis, 1.0 = at shell wall (not buildable).")
                _m2.metric("Nozzle edge / R", f"{(r_loc + nOR) / R_loc:.3f}",
                           help="Outer OD edge radius ÷ vessel radius. "
                                "Values approaching 1.0 indicate the OD is close to the shell wall.")
                _m3.metric(
                    "Edge → shell wall",
                    f"{nres.edge_to_shell_mm:.0f} mm",
                    delta=("OK" if nres.edge_to_shell_mm >= min_weld_clr_h
                           else f"< min {min_weld_clr_h:.0f} mm"),
                    delta_color=("normal" if nres.edge_to_shell_mm >= min_weld_clr_h
                                 else "inverse"),
                    help=f"Clear distance from the nozzle OD edge to the vessel inner wall. "
                         f"Minimum: max(3·t_head, 25 mm) = {min_weld_clr_h:.0f} mm.",
                )
                zone_display = nres.zone.replace("_", " ").capitalize()
                _m4.metric("Zone", zone_display,
                           help="Head zone where the nozzle centre sits. "
                                "Crown = standard analysis valid; knuckle = specialist analysis required.")
                _m5.metric("Head depth", f"{nres.head_depth_mm:.0f} mm",
                           help="Axial depth of this head type (tangent to pole).")

                if nres.edge_to_knuckle_mm is not None:
                    _ek_col, _ = st.columns([1, 3])
                    e2k = nres.edge_to_knuckle_mm
                    _ek_col.metric(
                        "Edge → crown boundary",
                        f"{e2k:.0f} mm",
                        delta=("Clear" if e2k >= 0 else f"Penetrates by {-e2k:.0f} mm"),
                        delta_color="normal" if e2k >= 0 else "inverse",
                        help="Distance from the nozzle OD edge to the crown/knuckle boundary. "
                             "Negative = the outer edge of the nozzle OD circle is inside the knuckle zone.",
                    )

                # Axial depth on head and nozzle r/R ratio visual indicator
                if nres.head_depth_mm > 0:
                    depth_frac = nres.z_on_head_mm / nres.head_depth_mm
                    _bar_pct = min(100, int(depth_frac * 100))
                    _bar_col = "#16a34a" if _bar_pct < 50 else "#d97706" if _bar_pct < 75 else "#dc2626"
                    st.markdown(
                        f"<div style='margin:4px 0 8px 0'>"
                        f"<span style='font-size:0.82em;color:#64748b'>"
                        f"Axial depth on head surface: <b>{nres.z_on_head_mm:.0f} mm</b> "
                        f"from tangent ({_bar_pct} % of head depth)</span><br>"
                        f"<div style='background:#f1f5f9;border-radius:4px;height:8px;width:100%;margin-top:3px'>"
                        f"<div style='background:{_bar_col};border-radius:4px;height:8px;"
                        f"width:{_bar_pct}%'></div></div></div>",
                        unsafe_allow_html=True,
                    )

                # ── Engineering implications ──────────────────────────────────
                implications = _endcap_edge_implications(
                    nres, Di, head_res.t_nom_mm, code_key,
                )
                if implications:
                    st.markdown("**Engineering implications**")
                    for issue in implications:
                        if issue["level"] == "error":
                            st.error(issue["text"], icon="🚫")
                        elif issue["level"] == "warning":
                            st.warning(issue["text"], icon="⚠️")
                        else:
                            st.info(issue["text"], icon="ℹ️")
                else:
                    st.success(
                        f"No edge-proximity issues detected for {nz['tag']}. "
                        "Nozzle is well within the crown zone with adequate weld clearance.",
                        icon="✅",
                    )

                # ── Alternative head type comparison ──────────────────────────
                st.markdown("**Alternative head type comparison**")
                _comp = _compare_nozzle_on_all_heads(
                    Di=Di, dn_mm=nz["dn"],
                    d_from_top_mm=nres.d_from_top_mm,
                    nozzle_OD_mm=nres.nozzle_OD_mm,
                    nozzle_t_mm=nres.nozzle_t_mm,
                    t_head_nom_mm=head_res.t_nom_mm,
                    crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
                    alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
                )
                _render_head_comparison_table(_comp, head_type)

                # Summary insight
                _ok_heads = [r["label"] for r in _comp
                             if r["res"].geom_ok and r["res"].code_ok is True]
                _warn_heads = [r["label"] for r in _comp
                               if r["res"].geom_ok and r["res"].code_ok is None]
                _fail_heads = [r["label"] for r in _comp
                               if not r["res"].geom_ok or r["res"].code_ok is False]
                if _ok_heads:
                    st.success(
                        f"**{nz['tag']} is code-compliant on:** {', '.join(_ok_heads)}.",
                        icon="✅",
                    )
                if _warn_heads:
                    st.warning(
                        f"**Detailed analysis required on:** {', '.join(_warn_heads)}.",
                        icon="⚠️",
                    )
                if _fail_heads:
                    st.error(
                        f"**Not compliant / not buildable on:** {', '.join(_fail_heads)}.",
                        icon="🚫",
                    )

                st.divider()

    # ── Separator sizing check ────────────────────────────────────────────────
    vol_res = vessel_volumes(
        head_type, Di, L_shell, levels_mm_vol,
        crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
        alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
        include_heads=True,
    )

    nll_vol  = next((r["vol_m3"] for r in vol_res["levels"] if r["tag"] == "NLL"),  0.0)
    lahh_vol = next((r["vol_m3"] for r in vol_res["levels"] if r["tag"] == "LAHH"), 0.0)
    nll_mm_v   = levels_mm_vol.get("NLL",  Di * 0.50)
    lahh_mm_v  = levels_mm_vol.get("LAHH", Di * 0.85)

    # ── LDV — Liquid Design Volume ────────────────────────────────────────────
    # LDV = minimum liquid inventory required to fill downstream equipment.
    # Segment A: vessel bottom (+ offset) to LZLL, scaled by safety factor.
    # Segment B: LALL to LAL (low-alarm response buffer).
    # Volumes use full vessel including endcaps (vessel_volumes with include_heads=True).
    _ldv_result: dict | None = None
    if include_ldv:
        _lzll_h = levels_mm_vol.get("LZLL", Di * 0.05)
        _lall_h = levels_mm_vol.get("LALL", Di * 0.10)
        _lal_h  = levels_mm_vol.get("LAL",  Di * 0.20)
        _nll_h  = levels_mm_vol.get("NLL",  Di * 0.50)
        _eff_vb = max(0.0, min(vb_offset_mm, _lzll_h - 1.0))  # clamp below LZLL

        _ldv_levels_calc = {
            "LDV_VB":   _eff_vb,
            "LDV_LZLL": _lzll_h,
            "LDV_LALL": _lall_h,
            "LDV_LAL":  _lal_h,
            "LDV_NLL":  _nll_h,
        }
        _ldv_vol = vessel_volumes(
            head_type, Di, L_shell, _ldv_levels_calc,
            crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
            alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
            include_heads=True,
        )
        _vmap = {r["tag"]: r["vol_m3"] for r in _ldv_vol["levels"]}

        _seg_a_raw = max(0.0, _vmap.get("LDV_LZLL", 0.0) - _vmap.get("LDV_VB",   0.0))
        _seg_a     = _seg_a_raw * ldv_sf
        _seg_b     = max(0.0, _vmap.get("LDV_LAL",  0.0) - _vmap.get("LDV_LALL", 0.0))
        _ldv_total = _seg_a + _seg_b                        # Seg A (×SF) + Seg B
        _ldv_raw   = _seg_a_raw + _seg_b                    # same, before SF
        _ldv_nll_inv = max(0.0, _vmap.get("LDV_NLL", 0.0) - _vmap.get("LDV_VB",  0.0))
        _ldv_ok    = _ldv_nll_inv >= _ldv_total

        # Target comparison (when a specific LDV volume is provided)
        _tgt_ok: bool | None = None
        _tgt_sf_ok: bool | None = None
        if ldv_target_m3 is not None and ldv_target_m3 > 0:
            _tgt_ok    = _ldv_raw    >= ldv_target_m3           # levels provide enough raw volume
            _tgt_sf_ok = _ldv_nll_inv >= ldv_target_m3 * ldv_sf  # NLL inventory covers target × SF

        _ldv_result = {
            "eff_vb_mm":    _eff_vb,
            "lzll_mm":      _lzll_h,
            "lall_mm":      _lall_h,
            "lal_mm":       _lal_h,
            "nll_mm":       _nll_h,
            "seg_a_raw_m3": _seg_a_raw,
            "seg_a_m3":     _seg_a,
            "seg_b_m3":     _seg_b,
            "ldv_raw_m3":   _ldv_raw,
            "ldv_total_m3": _ldv_total,
            "nll_inv_m3":   _ldv_nll_inv,
            "sf":           ldv_sf,
            "ok":           _ldv_ok,
            "target_m3":    ldv_target_m3,   # None if not set
            "target_ok":    _tgt_ok,         # levels raw volume ≥ target
            "target_sf_ok": _tgt_sf_ok,      # NLL inventory ≥ target × SF
        }

    # Count inlet nozzles for n_inlets parameter
    n_inlets = max(1, sum(1 for nz in st.session_state.get("nozzles", [])
                          if nz.get("service") == "Inlet"))

    sep_res = separator_check(
        Di_mm=Di, L_shell_mm=L_shell,
        nll_mm=nll_mm_v, lahh_mm=lahh_mm_v,
        L_baffle_mm=L_baffle_mm,
        Q_gas_m3h=Q_gas_m3h, Q_liq_m3h=Q_liq_m3h,
        rho_gas_kgm3=rho_gas, rho_liq_kgm3=rho_liq,
        K_sb=K_sb,
        t_holdup_req_min=t_holdup_req,
        t_surge_req_min=t_surge_req,
        mu_gas_Pas=gas_props.mu_Pas,
        mu_liq_Pas=liq_props.mu_Pas,
        n_inlets=n_inlets,
        V_total_at_nll_m3=nll_vol,
        V_total_at_lahh_m3=lahh_vol,
        V_total_vessel_m3=vol_res["total_m3"],
    )

    # ── Process streams summary ───────────────────────────────────────────────
    with st.expander("**Process streams**", expanded=True):
        ps1, ps2 = st.columns(2)

        def _prop_row(label, val):
            return f"**{label}:** {val}"

        ps1.markdown(f"**Gas phase — {gas_fluid}**")
        ps1.caption(
            f"MW = {gas_props.MW:.2f} g/mol  ·  "
            f"ρ = {gas_props.rho_kgm3:.3f} kg/m³  ·  "
            f"μ = {gas_props.mu_Pas*1e6:.1f} μPa·s  ·  Z = {Z_gas:.2f}"
        )
        ps1.metric("Gas flow", f"{Q_gas_m3h:,.0f} m³/h",
                   f"{Q_gas_m3h * gas_props.rho_kgm3:.0f} kg/h")

        ps2.markdown(f"**Liquid phase — {liq_fluid}**")
        ps2.caption(
            f"ρ = {liq_props.rho_kgm3:.0f} kg/m³  ·  "
            f"μ = {liq_props.mu_Pas*1e3:.3f} mPa·s"
        )
        ps2.metric("Liquid flow", f"{Q_liq_m3h:,.1f} m³/h",
                   f"{Q_liq_m3h * liq_props.rho_kgm3:.0f} kg/h")

        st.divider()

        # Nozzle stream assignment table
        inlet_nozzles  = [nz["tag"] for nz in st.session_state.get("nozzles", [])
                          if nz.get("service") == "Inlet"]
        gas_out_nozzles = [nz["tag"] for nz in st.session_state.get("nozzles", [])
                           if nz.get("service") == "Gas outlet"]
        liq_out_nozzles = [nz["tag"] for nz in st.session_state.get("nozzles", [])
                           if nz.get("service") == "Liquid outlet"]
        q_per_inlet = Q_gas_m3h / max(n_inlets, 1), Q_liq_m3h / max(n_inlets, 1)

        stream_rows = []
        for nz in st.session_state.get("nozzles", []):
            svc = nz.get("service", "")
            if svc == "Inlet":
                stream_rows.append({
                    "Tag": nz["tag"], "Service": svc,
                    "Gas (m³/h)": f"{q_per_inlet[0]:,.0f}",
                    "Liquid (m³/h)": f"{q_per_inlet[1]:,.1f}",
                    "ρ_gas (kg/m³)": f"{gas_props.rho_kgm3:.2f}",
                    "ρ_liq (kg/m³)": f"{liq_props.rho_kgm3:.0f}",
                })
            elif svc == "Gas outlet":
                stream_rows.append({
                    "Tag": nz["tag"], "Service": svc,
                    "Gas (m³/h)": f"{Q_gas_m3h:,.0f}", "Liquid (m³/h)": "—",
                    "ρ_gas (kg/m³)": f"{gas_props.rho_kgm3:.2f}", "ρ_liq (kg/m³)": "—",
                })
            elif svc == "Liquid outlet":
                stream_rows.append({
                    "Tag": nz["tag"], "Service": svc,
                    "Gas (m³/h)": "—", "Liquid (m³/h)": f"{Q_liq_m3h:,.1f}",
                    "ρ_gas (kg/m³)": "—", "ρ_liq (kg/m³)": f"{liq_props.rho_kgm3:.0f}",
                })
        if stream_rows:
            st.dataframe(pd.DataFrame(stream_rows), hide_index=True, use_container_width=True)
        if n_inlets > 1:
            st.caption(
                f"{n_inlets} inlet nozzles — two-phase flow split equally: "
                f"{q_per_inlet[0]:,.0f} m³/h gas + {q_per_inlet[1]:,.1f} m³/h liquid per inlet. "
                f"Gas outlet and liquid outlet each handle the full combined flow."
            )

    with st.expander("**Separator sizing (API 12J screening)**", expanded=True):
        import math as _math
        sc1, sc2, sc3 = st.columns(3)

        # ── Col 1: Gas capacity (Souders-Brown + mesh pad) ────────────────────
        sc1.markdown("**Gas capacity**")
        gas_ratio = sep_res.U_act_ms / max(sep_res.U_max_ms, 1e-9)
        sc1.metric(
            f"Gas velocity — body"
            + (f" (per zone, {n_inlets} inlets)" if n_inlets > 1 else ""),
            f"{sep_res.U_act_ms:.3f} m/s",
            delta=f"{'OK' if sep_res.gas_velocity_ok else 'EXCEEDS MAX'} — {gas_ratio*100:.0f} % of max",
            delta_color="normal" if sep_res.gas_velocity_ok else "inverse",
        )
        sc1.caption(
            f"Max = K × √(Δρ/ρ_g) = {sep_res.U_max_ms:.3f} m/s  "
            f"(K = {K_sb:.2f} m/s, {'mesh pad' if has_meshpad else 'open vessel'})"
        )

        if has_meshpad:
            # Mesh pad sees full Q_gas (both zones converge at the outlet)
            delta_rho_mp = max(0.0, rho_liq - rho_gas)
            U_pad_max   = K_pad * _math.sqrt(delta_rho_mp / max(rho_gas, 0.001))
            A_pad_req   = (Q_gas_m3h / 3600.0) / max(U_pad_max, 1e-9)
            A_pad_avail = sep_res.A_gas_m2
            pad_load    = A_pad_req / max(A_pad_avail, 1e-9) * 100
            pad_ok      = A_pad_req <= A_pad_avail
            sc1.metric("Mesh pad load (full Q_gas)", f"{pad_load:.0f} %",
                       delta="OK" if pad_ok else "UNDERSIZED",
                       delta_color="normal" if pad_ok else "inverse")
            sc1.caption(
                f"Pad area req. {A_pad_req:.3f} m²  /  avail. {A_pad_avail:.3f} m²  "
                f"·  K_pad = {K_pad:.2f} m/s"
            )

        sc1.markdown("**Droplet / bubble cut sizes**")
        sc1.metric("Liquid droplet cut size (gas phase)",
                   f"{sep_res.d_cut_gas_um:.0f} μm",
                   help="Smallest droplet that settles from gas before the outlet — drag-corrected Stokes")
        sc1.metric("Gas bubble cut size (liquid phase)",
                   f"{sep_res.d_cut_liq_um:.0f} μm",
                   help="Smallest bubble that rises clear of liquid before the outlet — drag-corrected Stokes")
        sc1.caption(
            f"Gas space H = {sep_res.gas_space_height_mm:.0f} mm  "
            f"·  A_gas = {sep_res.A_gas_m2:.3f} m²"
            + (f"  ·  per-zone flow = {sep_res.Q_gas_per_inlet_m3h:,.0f} m³/h gas" if n_inlets > 1 else "")
        )

        # ── Col 2: Liquid capacity (hold-up + optional surge) ────────────────
        sc2.markdown("**Liquid capacity**")
        sc2.metric("Hold-up time at NLL",
                   f"{sep_res.t_holdup_s/60:.1f} min",
                   delta=f"req. {t_holdup_req:.1f} min — {'OK' if sep_res.holdup_ok else 'SHORT'}",
                   delta_color="normal" if sep_res.holdup_ok else "inverse")
        if include_surge_check:
            sc2.metric("Surge time (NLL → LAHH)",
                       f"{sep_res.t_surge_s/60:.1f} min",
                       delta=f"req. {t_surge_req:.1f} min — {'OK' if sep_res.surge_ok else 'SHORT'}",
                       delta_color="normal" if sep_res.surge_ok else "inverse")
        else:
            sc2.caption(
                f"Surge time (NLL → LAHH): **{sep_res.t_surge_s/60:.1f} min** "
                f"(informational — check not required)"
            )
        sc2.metric("Liquid vol. at NLL (eff. zone)",
                   f"{sep_res.V_liq_eff_m3:.3f} m³",
                   f"Surge Δvol = {sep_res.V_surge_eff_m3:.3f} m³")
        sc2.caption(
            f"NLL = {sep_res.nll_mm:.0f} mm  ({sep_res.nll_frac*100:.0f} % of Di)  "
            f"·  Eff. L = {sep_res.L_eff_mm:.0f} mm"
            + (f"  ·  path per inlet = {sep_res.L_eff_mm/n_inlets:.0f} mm" if n_inlets > 1 else "")
        )

        # ── Col 3: Geometry checks + inlet momentum + inventory ───────────────
        sc3.markdown("**Geometry & inlet checks**")

        # Slenderness ratio (API 12J: 3–5 for horizontal separators)
        ld = sep_res.LD_ratio
        ld_ok = 3.0 <= ld <= 5.0
        sc3.metric("Slenderness L/D  (shell T–T / Di)",
                   f"{ld:.2f}",
                   delta="OK (3–5)" if ld_ok else ("TOO SHORT" if ld < 3 else "VERY LONG"),
                   delta_color="normal" if ld_ok else "inverse")

        # Inlet nozzle ρv² — API RP 14E / GPSA limit 2 400 Pa (non-erosive service)
        _RHO_V2_LIMIT = 2400.0  # Pa
        inlet_nozzles = [
            nz for nz, _, _, _, _ in nozzle_results
            if nz.get("service") == "Inlet"
        ]
        if inlet_nozzles:
            _Q_mix_per_m3s = (Q_gas_m3h + Q_liq_m3h) / n_inlets / 3600.0
            _rho_mix = (rho_gas * Q_gas_m3h + rho_liq * Q_liq_m3h) / max(Q_gas_m3h + Q_liq_m3h, 1e-9)
            # Use first inlet nozzle for representative size
            _nz0 = inlet_nozzles[0]
            _OD  = NOZZLE_OD.get(_nz0["dn"], _nz0["dn"] * 1.05)
            _rec = recommended_schedule(_nz0.get("pn", 25), code_key)
            _t   = float(NOZZLE_WALL_SCH[_rec].get(_nz0["dn"], NOZZLE_WALL_T.get(_nz0["dn"], 8.0)))
            _ID  = max(_OD - 2 * _t, 1.0)
            _A_nz = _math.pi * (_ID * 1e-3) ** 2 / 4.0
            _v_in = _Q_mix_per_m3s / max(_A_nz, 1e-9)
            _rho_v2 = _rho_mix * _v_in ** 2
            _rv2_ok = _rho_v2 <= _RHO_V2_LIMIT
            sc3.metric(f"Inlet nozzle ρv² (DN{_nz0['dn']})",
                       f"{_rho_v2:,.0f} Pa",
                       delta=f"{'OK' if _rv2_ok else 'EXCEEDS 2 400 Pa'} — limit {_RHO_V2_LIMIT:.0f} Pa",
                       delta_color="normal" if _rv2_ok else "inverse")
            sc3.caption(
                f"v_in = {_v_in:.2f} m/s  ·  ρ_mix = {_rho_mix:.1f} kg/m³  "
                f"·  bore ID = {_ID:.0f} mm  (API RP 14E)"
            )

        sc3.markdown("**Liquid inventory (incl. heads)**")
        inv_rows = [
            {"Level": "NLL",  "h (mm)": f"{nll_mm_v:.0f}",
             "Vol (m³)": f"{nll_vol:.3f}", "Vol (L)": f"{nll_vol*1000:.0f}"},
            {"Level": "LAHH", "h (mm)": f"{lahh_mm_v:.0f}",
             "Vol (m³)": f"{lahh_vol:.3f}", "Vol (L)": f"{lahh_vol*1000:.0f}"},
            {"Level": "Full", "h (mm)": f"{Di:.0f}",
             "Vol (m³)": f"{vol_res['total_m3']:.3f}",
             "Vol (L)": f"{vol_res['total_m3']*1000:.0f}"},
        ]
        sc3.dataframe(pd.DataFrame(inv_rows), hide_index=True, use_container_width=True)

        # ── LDV — Liquid Design Volume ────────────────────────────────────────
        if _ldv_result is not None:
            ldv = _ldv_result
            st.divider()
            st.markdown("**LDV — Liquid Design Volume**")
            st.caption(
                "Minimum liquid inventory required to fill downstream equipment that are "
                "partially empty during operation or startup. "
                "Volumes include full vessel geometry (cylinder + both endcaps)."
            )

            _lc1, _lc2, _lc3, _lc4 = st.columns(4)
            _lc1.metric(
                "Seg A — VB → LZLL (raw)",
                f"{ldv['seg_a_raw_m3'] * 1000:.1f} L  ({ldv['seg_a_raw_m3']:.4f} m³)",
                help=f"Volume from effective VB ({ldv['eff_vb_mm']:.0f} mm above vessel bottom) "
                     f"to LZLL ({ldv['lzll_mm']:.0f} mm). "
                     f"Before safety factor.",
            )
            _lc2.metric(
                f"Seg A × SF {ldv['sf']:.2f}",
                f"{ldv['seg_a_m3'] * 1000:.1f} L  ({ldv['seg_a_m3']:.4f} m³)",
                delta=f"SF adds {(ldv['seg_a_m3'] - ldv['seg_a_raw_m3']) * 1000:.1f} L",
                delta_color="off",
                help=f"Segment A after safety factor {ldv['sf']:.2f}× — accounts for "
                     "instrument deadband, pump cavitation margin, and measurement uncertainty.",
            )
            _lc3.metric(
                "Seg B — LALL → LAL",
                f"{ldv['seg_b_m3'] * 1000:.1f} L  ({ldv['seg_b_m3']:.4f} m³)",
                help=f"Volume from LALL ({ldv['lall_mm']:.0f} mm) to LAL ({ldv['lal_mm']:.0f} mm). "
                     "Low-alarm response buffer — liquid consumed between alarm and low-level action.",
            )
            _lc4.metric(
                "LDV Total",
                f"{ldv['ldv_total_m3'] * 1000:.1f} L  ({ldv['ldv_total_m3']:.4f} m³)",
                delta=("OK — NLL inventory sufficient" if ldv["ok"]
                       else "INSUFFICIENT — NLL inventory below LDV"),
                delta_color="normal" if ldv["ok"] else "inverse",
                help="Seg A (×SF) + Seg B. Must be ≤ available liquid inventory at NLL.",
            )

            # Breakdown table
            _ldv_rows = [
                {
                    "Segment": "A — VB → LZLL",
                    "From": f"{ldv['eff_vb_mm']:.0f} mm"
                            + (f"  (VB + {ldv['eff_vb_mm']:.0f} mm)" if ldv["eff_vb_mm"] > 0 else "  (vessel bottom)"),
                    "To": f"{ldv['lzll_mm']:.0f} mm  (LZLL)",
                    "Raw volume": f"{ldv['seg_a_raw_m3']*1000:.1f} L",
                    "× SF": f"{ldv['sf']:.2f}",
                    "Effective volume": f"{ldv['seg_a_m3']*1000:.1f} L",
                },
                {
                    "Segment": "B — LALL → LAL",
                    "From": f"{ldv['lall_mm']:.0f} mm  (LALL)",
                    "To": f"{ldv['lal_mm']:.0f} mm  (LAL)",
                    "Raw volume": f"{ldv['seg_b_m3']*1000:.1f} L",
                    "× SF": "1.00",
                    "Effective volume": f"{ldv['seg_b_m3']*1000:.1f} L",
                },
                {
                    "Segment": "LDV TOTAL",
                    "From": "—", "To": "—",
                    "Raw volume": "—",
                    "× SF": "—",
                    "Effective volume": f"**{ldv['ldv_total_m3']*1000:.1f} L**",
                },
            ]
            st.dataframe(pd.DataFrame(_ldv_rows), hide_index=True, use_container_width=True)

            # ── Specific target comparison (when set) ────────────────────────
            if ldv.get("target_m3") is not None:
                tgt_L    = ldv["target_m3"] * 1000
                tgt_sf_L = ldv["target_m3"] * ldv["sf"] * 1000
                raw_L    = ldv["ldv_raw_m3"] * 1000
                inv_L    = ldv["nll_inv_m3"] * 1000
                st.markdown("**Target LDV comparison**")
                _tc1, _tc2 = st.columns(2)
                _delta1 = raw_L - tgt_L
                _tc1.metric(
                    "Level volumes (before SF) vs target",
                    f"{raw_L:.1f} L",
                    delta=f"{'surplus' if _delta1 >= 0 else 'shortfall'} {_delta1:+.1f} L vs target {tgt_L:.1f} L",
                    delta_color="normal" if ldv["target_ok"] else "inverse",
                    help="Volume defined by level setpoints (Seg A raw + Seg B) compared "
                         "to the required LDV before safety factor. "
                         "Shows whether the level setpoints alone cover the downstream volume.",
                )
                _delta2 = inv_L - tgt_sf_L
                _tc2.metric(
                    f"NLL inventory vs target × SF {ldv['sf']:.2f}",
                    f"{inv_L:.1f} L",
                    delta=f"{'surplus' if _delta2 >= 0 else 'shortfall'} {_delta2:+.1f} L vs {tgt_sf_L:.1f} L",
                    delta_color="normal" if ldv["target_sf_ok"] else "inverse",
                    help=f"Available liquid at NLL (from VB to NLL) compared to "
                         f"target × SF = {tgt_L:.1f} × {ldv['sf']:.2f} = {tgt_sf_L:.1f} L. "
                         "This is the conservative requirement the vessel must meet.",
                )
                if ldv["target_ok"] and ldv["target_sf_ok"]:
                    st.success(
                        f"Target LDV **{tgt_L:.1f} L** covered — "
                        f"level volumes: {raw_L:.1f} L (raw), NLL inventory: {inv_L:.1f} L ≥ {tgt_sf_L:.1f} L (×SF).",
                        icon="✅",
                    )
                else:
                    _msgs = []
                    if not ldv["target_ok"]:
                        _msgs.append(
                            f"level volumes {raw_L:.1f} L < target {tgt_L:.1f} L — "
                            "adjust LZLL/LALL/LAL setpoints to widen the LDV zone"
                        )
                    if not ldv["target_sf_ok"]:
                        _msgs.append(
                            f"NLL inventory {inv_L:.1f} L < {tgt_sf_L:.1f} L (target × SF) — "
                            "increase vessel size or raise NLL"
                        )
                    st.error("Target LDV not met: " + "; ".join(_msgs) + ".", icon="🚫")

            # ── Inventory check (level-based LDV vs NLL) ──────────────────────
            _inv_surplus = ldv["nll_inv_m3"] - ldv["ldv_total_m3"]
            if ldv["ok"]:
                st.success(
                    f"NLL inventory check passed — "
                    f"**{ldv['nll_inv_m3']*1000:.1f} L** ≥ LDV (×SF) **{ldv['ldv_total_m3']*1000:.1f} L** "
                    f"(surplus: **{_inv_surplus*1000:.1f} L**).",
                    icon="✅",
                )
            else:
                st.error(
                    f"NLL inventory check failed — "
                    f"**{ldv['nll_inv_m3']*1000:.1f} L** < LDV (×SF) **{ldv['ldv_total_m3']*1000:.1f} L** "
                    f"(shortfall: **{-_inv_surplus*1000:.1f} L**). "
                    "Increase vessel size, raise NLL, lower LZLL, or reduce downstream equipment empty volume.",
                    icon="🚫",
                )
            st.caption(
                f"Available NLL inventory (VB+{ldv['eff_vb_mm']:.0f} mm → NLL {ldv['nll_mm']:.0f} mm, "
                f"full vessel incl. endcaps): **{ldv['nll_inv_m3']*1000:.1f} L**"
            )

    # ── Volume table ──────────────────────────────────────────────────────────
    vol_res_disp = vessel_volumes(
        head_type, Di, L_shell, levels_mm_vol,
        crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
        alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
        include_heads=include_heads,
    )
    with st.expander("**Volume calculator**", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total vessel", f"{vol_res_disp['total_m3']:.3f} m³", f"{vol_res_disp['total_L']:.0f} L")
        c2.metric("Cylinder only", f"{vol_res_disp['shell_m3']:.3f} m³", f"{vol_res_disp['shell_L']:.0f} L")
        c3.metric("Both heads", f"{vol_res_disp['heads_m3']:.3f} m³", f"{vol_res_disp['heads_L']:.0f} L")
        heads_pct = (vol_res_disp['heads_m3'] / vol_res_disp['total_m3'] * 100 if vol_res_disp['total_m3'] > 0 else 0)
        c4.metric("Heads share", f"{heads_pct:.1f} %", "incl. in total" if include_heads else "excluded")

        st.divider()
        rows_vol = []
        for row in vol_res_disp["levels"]:
            tag = row["tag"]
            colour, _, _ = _LEVEL_STYLE.get(tag, ("#64748b", "dash", 1.5))
            rows_vol.append({
                "Level":               f'<span style="color:{colour};font-weight:700">{tag}</span>',
                "Height (mm)":         f"{row['h_mm']:.0f}",
                "% Di":                f"{row['h_pct']:.1f}",
                "Vol to level (m³)":   f"{row['vol_m3']:.3f}",
                "Vol to level (L)":    f"{row['vol_L']:.0f}",
                "% vessel":            f"{row['vol_pct']:.1f}",
                "Between levels (m³)": f"{row['btw_m3']:.3f}",
                "Between levels (L)":  f"{row['btw_L']:.0f}",
            })
        table_html = pd.DataFrame(rows_vol).to_html(index=False, escape=False, classes="vol-table", border=0)
        st.markdown(
            "<style>.vol-table{width:100%;border-collapse:collapse;font-size:0.88em}"
            ".vol-table th{background:#f1f5f9;padding:6px 10px;text-align:left;border-bottom:2px solid #e2e8f0}"
            ".vol-table td{padding:5px 10px;border-bottom:1px solid #f1f5f9}"
            ".vol-table tr:hover td{background:#f8fafc}</style>",
            unsafe_allow_html=True,
        )
        st.markdown(table_html, unsafe_allow_html=True)
        st.caption(
            f"Shell L = {L_shell:.0f} mm T-T  ·  "
            + ("Endcap volumes included" if include_heads else "Cylinder only — endcaps excluded")
        )

    # ── Report generation (triggered from sidebar button) ─────────────────────
    if _gen_btn:
        import report as _report
        from datetime import date as _date
        _zs_up, _ = _head_surface_points(head_type, Di, R_c, r_k, alpha_deg_cone, b)
        _h_head   = max((abs(z) for z in _zs_up), default=0.0)
        st.session_state["report_html"] = _report.generate_datasheet_html(
            project_name=project_name,
            vessel_tag=vessel_tag,
            issued_for=issued_for,
            Di=Di, L_shell=L_shell, h_head=_h_head,
            P_barg=P_barg, T_C=T_C,
            mat_key=mat_key, head_type_label=head_label_map[head_type],
            code_key=code_key, fd_MPa=fd,
            shell_res=shell_res, head_res=head_res,
            nozzle_results=nozzle_results,
            levels_mm=levels_mm_vol,
            sep_res=sep_res,
            gas_props=gas_props, liq_props=liq_props,
            Q_gas_m3h=Q_gas_m3h, Q_liq_m3h=Q_liq_m3h,
            gas_fluid=gas_fluid, liq_fluid=liq_fluid,
            placement_checks=placement_checks,
            head_warnings=head_res.warnings,
            shell_warnings=shell_res.warnings,
            saddle_a_mm=saddle_a_mm, saddle_w_mm=saddle_w_mm,
            has_meshpad=has_meshpad, has_baffles=has_baffles,
            has_inlet_dev=has_inlet_dev, has_vortex_brk=has_vortex_brk,
            L_baffle_mm=L_baffle_mm, baffle_open_pct=baffle_open_pct,
            K_sb=K_sb, n_inlets=n_inlets,
            P_op_barg=P_op_barg, T_op_C=T_op_C,
            t_holdup_req_min=t_holdup_req,
            t_surge_req_min=t_surge_req,
            include_surge_check=include_surge_check,
            ldv_result=_ldv_result,
            Z_gas=Z_gas,
        ).encode("utf-8")
        st.session_state["report_fname"] = (
            f"datasheet_{vessel_tag.replace(' ','_')}_{_date.today().isoformat()}.html"
        )
        st.rerun()

    if _gen_word_btn:
        import word_report as _word_report
        from datetime import date as _date
        _zs_up, _ = _head_surface_points(head_type, Di, R_c, r_k, alpha_deg_cone, b)
        _h_head   = max((abs(z) for z in _zs_up), default=0.0)
        st.session_state["report_docx"] = _word_report.generate_word_report(
            project_name=project_name,
            vessel_tag=vessel_tag,
            issued_for=issued_for,
            Di=Di, L_shell=L_shell, h_head=_h_head,
            P_barg=P_barg, T_C=T_C,
            mat_key=mat_key, head_type_label=head_label_map[head_type],
            code_key=code_key, fd_MPa=fd,
            shell_res=shell_res, head_res=head_res,
            nozzle_results=nozzle_results,
            levels_mm=levels_mm_vol,
            sep_res=sep_res,
            gas_props=gas_props, liq_props=liq_props,
            Q_gas_m3h=Q_gas_m3h, Q_liq_m3h=Q_liq_m3h,
            gas_fluid=gas_fluid, liq_fluid=liq_fluid,
            placement_checks=placement_checks,
            head_warnings=head_res.warnings,
            shell_warnings=shell_res.warnings,
            saddle_a_mm=saddle_a_mm, saddle_w_mm=saddle_w_mm,
            has_meshpad=has_meshpad, has_baffles=has_baffles,
            has_inlet_dev=has_inlet_dev, has_vortex_brk=has_vortex_brk,
            L_baffle_mm=L_baffle_mm, baffle_open_pct=baffle_open_pct,
            K_sb=K_sb, n_inlets=n_inlets,
            P_op_barg=P_op_barg, T_op_C=T_op_C,
            t_holdup_req_min=t_holdup_req,
            t_surge_req_min=t_surge_req,
            include_surge_check=include_surge_check,
            ldv_result=_ldv_result,
            Z_gas=Z_gas,
        )
        st.session_state["report_docx_fname"] = (
            f"design_report_{vessel_tag.replace(' ','_')}_{_date.today().isoformat()}.docx"
        )
        st.rerun()


if __name__ == "__main__":
    main()
