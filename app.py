"""
VesselCalc — Pressure vessel design screener.

Calculates shell/head thickness and evaluates nozzle placement on endcaps
per EN 13445-3:2021 and ASME VIII Div.1.
"""
import math
import streamlit as st
import plotly.graph_objects as go

import engines
from engines import (
    MATERIALS, allowable_stress,
    HeadType, head_geometry, head_thickness,
    shell_thickness, nozzle_on_head, reinforcement_check,
)
from engines.nozzle_geometry import NOZZLE_OD, NOZZLE_WALL_T, _tori_geometry
from standards import DN_SIZES, EN_PN_RATINGS, ASME_CLASS_PRESSURE_20C, max_pn_for_temperature

st.set_page_config(
    page_title="VesselCalc",
    page_icon="🔩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────── HEAD PROFILE GEOMETRY ────────────────────────────────

def _head_surface_points(
    head_type: HeadType, Di: float, R_c: float, r_k: float,
    alpha_deg: float, b: float, N: int = 120,
) -> tuple[list[float], list[float]]:
    """
    Return (x_list, y_list) for the inner head surface, half cross-section.
    x : radial distance from axis (0 at centre, R at shell wall)
    y : height above tangent line (0 = tangent, positive = into head, negative = cylinder)
    """
    R = Di / 2
    xs: list[float] = []
    ys: list[float] = []

    if head_type == HeadType.HEMISPHERICAL:
        # Sphere of radius R, centre at y=0 (tangent).
        for i in range(N + 1):
            angle = math.pi / 2 * i / N  # 0 at equator (tangent), π/2 at pole
            xs.append(R * math.cos(angle))
            ys.append(R * math.sin(angle))

    elif head_type == HeadType.ELLIPSOIDAL:
        # (x/R)² + (y/b)² = 1 for y ≥ 0
        for i in range(N + 1):
            angle = math.pi / 2 * i / N
            xs.append(R * math.cos(angle))
            ys.append(b * math.sin(angle))

    elif head_type == HeadType.TORISPHERICAL:
        tg = _tori_geometry(Di, R_c, r_k)
        z_kc = tg["z_kc"]
        x_cj = tg["x_cj"]
        z_cj = tg["z_cj"]
        h_head = z_kc   # y at pole (tangent is y=0)

        # Crown arc: from pole (x=0, y=h_head) down to junction (x=x_cj, y=y_cj)
        y_cj = h_head - z_cj
        # Crown sphere centre in (x, y): (0, y_sc) where y_sc = h_head - R_c
        y_sc = h_head - R_c
        N1 = max(1, int(N * z_cj / max(z_kc, 0.01)))
        for i in range(N1 + 1):
            frac = i / N1
            angle = math.acos(1 - frac * z_cj / R_c)  # angle from top of crown sphere
            x_val = R_c * math.sin(angle)
            y_val = y_sc + R_c * math.cos(angle)
            xs.append(x_val)
            ys.append(y_val)

        # Knuckle arc: from junction (x_cj, y_cj) to tangent (R, 0)
        # Knuckle centre in (x, y): (Di/2 - r_k, 0)
        x_kc = Di / 2 - r_k
        # Angle at junction:
        theta_cj = math.atan2(y_cj, x_cj - x_kc)      # angle from knuckle centre
        theta_tan = math.atan2(0 - 0, Di / 2 - x_kc)   # = 0 (tangent at same y as centre)
        N2 = N - N1
        for i in range(1, N2 + 1):
            frac = i / N2
            theta = theta_cj + frac * (theta_tan - theta_cj)
            x_val = x_kc + r_k * math.cos(theta)
            y_val = 0 + r_k * math.sin(theta)
            xs.append(x_val)
            ys.append(y_val)

    elif head_type == HeadType.CONICAL:
        alpha_rad = math.radians(alpha_deg)
        h_head = R / math.tan(alpha_rad)
        for i in range(N + 1):
            frac = i / N
            x_val = frac * R
            y_val = h_head * (1 - frac)
            xs.append(x_val)
            ys.append(y_val)

    else:  # FLAT
        xs = [0.0, R]
        ys = [0.0, 0.0]

    return xs, ys


def _vessel_figure(
    head_type: HeadType,
    Di: float,
    R_c: float, r_k: float, alpha_deg: float, b: float,
    t_head_nom: float,
    t_shell_nom: float,
    nres,
    cyl_len_show: float = 350.0,
) -> go.Figure:
    """Build the half-section vessel cross-section plot."""
    R = Di / 2
    xs, ys = _head_surface_points(head_type, Di, R_c, r_k, alpha_deg, b)
    h_head = max(ys) if ys else 0.0

    fig = go.Figure()

    # ── Fill zones for torispherical ──────────────────────────────────────────
    if head_type == HeadType.TORISPHERICAL and nres is not None:
        tg = _tori_geometry(Di, R_c, r_k)
        z_kc = tg["z_kc"]
        z_cj = tg["z_cj"]
        x_cj = tg["x_cj"]
        y_cj = h_head - z_cj

        # Crown zone fill (both halves)
        crown_x, crown_y = [], []
        N_fill = 60
        N1 = max(1, int(N_fill * z_cj / max(z_kc, 0.01)))
        y_sc = h_head - R_c
        for i in range(N1 + 1):
            ang = math.acos(1 - i / N1 * z_cj / R_c)
            crown_x.append(R_c * math.sin(ang))
            crown_y.append(y_sc + R_c * math.cos(ang))
        # Close: back along axis
        crown_fill_x = crown_x + [0, 0]
        crown_fill_y = crown_y + [y_cj, h_head]

        fig.add_trace(go.Scatter(
            x=crown_fill_x + [-x for x in reversed(crown_fill_x)] + [crown_fill_x[0]],
            y=crown_fill_y + list(reversed(crown_fill_y)) + [crown_fill_y[0]],
            fill="toself", fillcolor="rgba(34,197,94,0.10)",
            line=dict(color="rgba(34,197,94,0)", width=0),
            name="Crown zone", hoverinfo="skip", legendgroup="zones",
        ))
        # Crown boundary dashed line
        fig.add_trace(go.Scatter(
            x=[x_cj, -x_cj], y=[y_cj, y_cj],
            mode="lines", line=dict(color="rgba(34,197,94,0.7)", width=1.5, dash="dash"),
            showlegend=False, hoverinfo="skip",
        ))

    # ── Shell inner wall ───────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=[R, R], y=[0, -cyl_len_show],
        mode="lines", line=dict(color="#2563eb", width=2.5),
        name="Shell inner wall", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[-R, -R], y=[0, -cyl_len_show],
        mode="lines", line=dict(color="#2563eb", width=2.5),
        showlegend=False, hoverinfo="skip",
    ))

    # ── Head inner surface ─────────────────────────────────────────────────────
    head_trace_x = xs + [-x for x in reversed(xs)]
    head_trace_y = ys + list(reversed(ys))
    fig.add_trace(go.Scatter(
        x=head_trace_x, y=head_trace_y,
        mode="lines", line=dict(color="#2563eb", width=2.5),
        name="Head inner surface", hoverinfo="skip",
    ))

    # Outer wall (approximate offset by wall thickness)
    if t_head_nom > 0 and t_shell_nom > 0:
        fig.add_trace(go.Scatter(
            x=[R + t_shell_nom, R + t_shell_nom], y=[0, -cyl_len_show],
            mode="lines", line=dict(color="#93c5fd", width=1.5, dash="dot"),
            name="Shell outer wall", hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=[-(R + t_shell_nom), -(R + t_shell_nom)], y=[0, -cyl_len_show],
            mode="lines", line=dict(color="#93c5fd", width=1.5, dash="dot"),
            showlegend=False, hoverinfo="skip",
        ))

    # Tangent line annotation
    fig.add_hline(y=0, line=dict(color="#94a3b8", dash="dot", width=1))

    # ── Nozzle ────────────────────────────────────────────────────────────────
    if nres is not None:
        nx = nres.x_from_axis_mm
        ny = h_head - nres.d_top_mm
        nOR = nres.nozzle_OR_mm

        if nres.geom_ok:
            if nres.code_ok:
                nc = "#16a34a"
                nfill = "rgba(22,163,74,0.20)"
            else:
                nc = "#d97706"
                nfill = "rgba(217,119,6,0.20)"
        else:
            nc = "#dc2626"
            nfill = "rgba(220,38,38,0.18)"

        theta_list = [i / 30 * 2 * math.pi for i in range(31)]
        for sign in (1, -1):
            noz_x = [sign * nx + nOR * math.cos(t) for t in theta_list]
            noz_y = [ny + nOR * math.sin(t) for t in theta_list]
            fig.add_trace(go.Scatter(
                x=noz_x, y=noz_y,
                fill="toself", fillcolor=nfill,
                line=dict(color=nc, width=2),
                name=f"DN{nres.dn_mm}" if sign == 1 else None,
                showlegend=(sign == 1),
                hovertemplate=(
                    f"DN{nres.dn_mm} nozzle<br>"
                    f"x = {nx:.0f} mm from axis<br>"
                    f"d_top = {nres.d_top_mm:.0f} mm<br>"
                    f"Zone: {nres.zone}"
                    "<extra></extra>"
                ) if sign == 1 else None,
            ))
        # Centre crosshair
        fig.add_trace(go.Scatter(
            x=[nx], y=[ny], mode="markers",
            marker=dict(color=nc, size=7, symbol="cross-thin", line=dict(width=2, color=nc)),
            showlegend=False,
            hovertemplate=f"x={nx:.0f} mm, y={ny:.0f} mm<extra></extra>",
        ))

        # d_top dimension arrow
        if nres.d_top_mm > 10:
            ax = -(R + 60)
            fig.add_shape(type="line", x0=ax, x1=ax, y0=h_head, y1=ny,
                          line=dict(color="#64748b", width=1.5))
            fig.add_annotation(
                x=ax, y=(h_head + ny) / 2,
                text=f" {nres.d_top_mm:.0f} mm", showarrow=False,
                xanchor="left", font=dict(size=11, color="#475569"),
            )
            # Tick marks
            for y_t in (h_head, ny):
                fig.add_shape(type="line", x0=ax - 8, x1=ax + 8, y0=y_t, y1=y_t,
                              line=dict(color="#64748b", width=1.5))

        # Inner diameter annotation (at bottom of shown cylinder)
        fig.add_annotation(
            x=0, y=-cyl_len_show + 20,
            text=f"Di = {Di:.0f} mm",
            showarrow=False, font=dict(size=11, color="#475569"),
        )

    # Pole label
    fig.add_annotation(
        x=0, y=h_head if h_head > 0 else 5,
        text="Pole", showarrow=False, yanchor="bottom",
        font=dict(size=10, color="#64748b"),
    )

    fig.update_layout(
        height=580,
        margin=dict(l=10, r=10, t=10, b=30),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=True,
        legend=dict(orientation="h", x=0.0, y=-0.06, bgcolor="rgba(255,255,255,0.8)"),
        xaxis=dict(
            title="Radial distance from axis (mm)",
            zeroline=True, zerolinecolor="#e2e8f0", zerolinewidth=1.5,
            gridcolor="#f8fafc", range=[-(R + 160), R + 160],
            tickformat=",d",
        ),
        yaxis=dict(
            title="Height (mm) — 0 = tangent line",
            gridcolor="#f8fafc",
            scaleanchor="x", scaleratio=1,
        ),
    )
    return fig


# ─────────────────────── RESULT BADGE ─────────────────────────────────────────

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


# ─────────────────────── MAIN APP ─────────────────────────────────────────────

def main():
    st.title("VesselCalc — Pressure Vessel Screener")

    # ── Sidebar inputs ─────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Vessel parameters")

        code = st.radio("Design code", ["EN 13445-3", "ASME VIII Div.1"],
                        horizontal=True, key="code")
        code_key = "EN" if code.startswith("EN") else "ASME"

        Di = st.number_input("Inner diameter Di (mm)", min_value=100.0, max_value=10000.0,
                              value=1800.0, step=50.0, key="Di")
        P_barg = st.number_input("Design pressure (barg)", min_value=0.1, max_value=500.0,
                                 value=20.0, step=0.5, key="P_barg")
        T_C = st.number_input("Design temperature (°C)", min_value=-200.0, max_value=500.0,
                              value=100.0, step=5.0, key="T_C")

        # Filter materials by code
        mat_options = {k: v["name"] for k, v in MATERIALS.items()
                       if v["code"] in (code_key, "BOTH")}
        if not mat_options:
            mat_options = {k: v["name"] for k, v in MATERIALS.items()}
        mat_key = st.selectbox("Material", options=list(mat_options.keys()),
                               format_func=lambda k: MATERIALS[k]["name"][:55],
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
            HeadType.TORISPHERICAL:  "Torispherical (dished / Klöpper)",
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
                    help="Standard Klöpper: 1.0 (R_c = Di). Korbbogen: 0.8.")
                knuckle_ratio = st.number_input(
                    "Knuckle radius ratio r_k/Di", min_value=0.06, max_value=0.3,
                    value=0.1, step=0.01, key="knuckle_ratio",
                    help="Minimum per EN/ASME: 0.06.")
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
        st.header("Nozzle")

        dn_mm = st.selectbox("Nozzle DN", options=DN_SIZES,
                             index=DN_SIZES.index(250), key="dn_mm")
        nozzle_OD_mm = NOZZLE_OD.get(dn_mm, dn_mm)
        nozzle_t_mm_default = NOZZLE_WALL_T.get(dn_mm, 8.0)

        if code_key == "EN":
            pn_options = [p for p in EN_PN_RATINGS if p >= 1]
            pn_sel = st.selectbox("Flange PN rating", options=pn_options,
                                  index=pn_options.index(20) if 20 in pn_options else 0,
                                  key="pn_sel")
        else:
            class_options = list(ASME_CLASS_PRESSURE_20C.keys())
            pn_sel = st.selectbox("Flange Class", options=class_options,
                                  index=1, key="pn_sel")

        d_top_mm = st.number_input(
            "Distance from vessel top / pole (mm)",
            min_value=0.0, max_value=float(Di),
            value=200.0, step=10.0, key="d_top",
            help="Vertical distance from the pole (topmost point of the endcap) "
                 "to the nozzle centreline.",
        )

        nozzle_t_override = st.number_input(
            "Nozzle wall thickness (mm)",
            min_value=1.0, max_value=100.0,
            value=float(nozzle_t_mm_default),
            step=0.5, key="nozzle_t",
            help="Default: Sch 40 / standard wall for this DN.",
        )

    # ── Compute ────────────────────────────────────────────────────────────────

    # Allowable stress
    stress = allowable_stress(mat_key, T_C, code_key)
    fd = stress["fd_MPa"]

    # Shell thickness
    shell_res = shell_thickness(Di, P_barg, fd, z=z_weld, CA_mm=CA_mm, code=code_key)

    # Head thickness
    head_res = head_thickness(
        head_type, Di, P_barg, fd, z=z_weld, CA_mm=CA_mm, code=code_key,
        crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
        alpha_deg=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
    )

    # Nozzle placement
    R_c = crown_ratio * Di
    r_k = knuckle_ratio * Di
    b = Di / (2 * ellipse_ratio)

    nozzle_res = nozzle_on_head(
        head_type, Di, d_top_mm, dn_mm,
        crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
        alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
        nozzle_OD_mm=nozzle_OD_mm, nozzle_t_mm=nozzle_t_override,
    )

    # Reinforcement
    reinf_res = reinforcement_check(
        Di=Di, P_barg=P_barg, fd_MPa=fd,
        nozzle_OD_mm=nozzle_OD_mm, nozzle_t_mm=nozzle_t_override,
        t_head_req_mm=head_res.t_calc_mm,
        t_head_nom_mm=head_res.t_nom_mm,
        CA_mm=CA_mm, code=code_key, z=z_weld,
    )

    # Flange pressure check
    if code_key == "EN":
        pn_at_T = max_pn_for_temperature(float(pn_sel), T_C)
        flange_ok = P_barg <= pn_at_T
    else:
        class_p20 = ASME_CLASS_PRESSURE_20C.get(str(pn_sel), 999.0)
        pn_at_T = class_p20  # simplified (no temp derating for ASME in this screener)
        flange_ok = P_barg <= pn_at_T

    # ── Main layout ────────────────────────────────────────────────────────────
    col_fig, col_results = st.columns([1.1, 1.0], gap="medium")

    with col_fig:
        st.subheader("Cross-section diagram")
        fig = _vessel_figure(
            head_type, Di, R_c, r_k, alpha_deg_cone, b,
            t_head_nom=head_res.t_nom_mm,
            t_shell_nom=shell_res.t_nom_mm,
            nres=nozzle_res,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Quick status summary
        st.markdown("**Placement summary**")
        all_ok = nozzle_res.geom_ok and nozzle_res.code_ok and reinf_res.adequate and flange_ok
        badges = (
            _badge("Geometry", nozzle_res.geom_ok) + " " +
            _badge("Code zone", nozzle_res.code_ok) + " " +
            _badge("Reinforcement", reinf_res.adequate) + " " +
            _badge("Flange PN/Class", flange_ok)
        )
        st.markdown(badges, unsafe_allow_html=True)

        # Errors and warnings consolidated
        all_msgs = (
            [("error", e) for e in nozzle_res.errors + reinf_res.warnings] +
            [("warning", w) for w in nozzle_res.warnings + head_res.warnings + shell_res.warnings]
        )
        for kind, msg in all_msgs:
            if kind == "error":
                st.error(msg, icon="🚫")
            else:
                st.warning(msg, icon="⚠️")

    with col_results:
        # ── Material and allowable stress ──────────────────────────────────────
        with st.expander("**Material & allowable stress**", expanded=True):
            st.markdown(f"**{MATERIALS[mat_key]['name']}**")
            st.caption(stress["basis"])
            st.metric("Allowable stress fd", f"{fd:.1f} MPa")

        # ── Shell thickness ────────────────────────────────────────────────────
        with st.expander("**Shell thickness**", expanded=True):
            sc1, sc2 = st.columns(2)
            sc1.metric("Calculated t", f"{shell_res.t_calc_mm:.2f} mm")
            sc2.metric("Nominal (rounded up)", f"{shell_res.t_nom_mm:.1f} mm")
            st.caption(f"{shell_res.clause}  —  {shell_res.formula}")

        # ── Head thickness ─────────────────────────────────────────────────────
        with st.expander("**Head thickness**", expanded=True):
            hc1, hc2, hc3 = st.columns(3)
            hc1.metric("Calculated e", f"{head_res.t_calc_mm:.2f} mm")
            hc2.metric("Nominal (rounded up)", f"{head_res.t_nom_mm:.1f} mm")
            hc3.metric("Head depth", f"{nozzle_res.head_depth_mm:.1f} mm")
            st.caption(f"{head_res.clause}  —  {head_res.formula}")

        # ── Nozzle geometry ────────────────────────────────────────────────────
        with st.expander("**Nozzle placement geometry**", expanded=True):
            ng_rows = {
                "Nozzle DN / OD": f"DN{dn_mm}  /  {nozzle_OD_mm:.1f} mm OD",
                "Nozzle wall": f"{nozzle_t_override:.1f} mm (ID = {nozzle_OD_mm - 2*nozzle_t_override:.1f} mm)",
                "Radial offset from axis": f"{nozzle_res.x_from_axis_mm:.1f} mm",
                "Polar angle": f"{nozzle_res.alpha_deg:.1f}°",
                "Zone": nozzle_res.zone.capitalize(),
                "Edge to shell wall": f"{nozzle_res.edge_to_shell_mm:.1f} mm",
            }
            if head_type == HeadType.TORISPHERICAL:
                ng_rows["Crown zone ends at"] = (
                    f"d_top = {nozzle_res.d_crown_end_mm:.1f} mm  "
                    f"(x = {nozzle_res.x_crown_end_mm:.1f} mm)")
                ng_rows["Edge to knuckle"] = (
                    f"{nozzle_res.edge_to_knuckle_mm:.1f} mm"
                    if nozzle_res.edge_to_knuckle_mm is not None else "—")

            for k, v in ng_rows.items():
                c1, c2 = st.columns([1.4, 1.6])
                c1.markdown(f"*{k}*")
                c2.markdown(f"**{v}**")

        # ── Reinforcement ──────────────────────────────────────────────────────
        with st.expander("**Nozzle reinforcement**", expanded=True):
            rc1, rc2 = st.columns(2)
            rc1.metric("Area required", f"{reinf_res.A_required_mm2:,.0f} mm²")
            rc1.metric("Area in shell", f"{reinf_res.A_shell_mm2:,.0f} mm²")
            rc1.metric("Area in nozzle", f"{reinf_res.A_nozzle_mm2:,.0f} mm²")
            if reinf_res.pad_required:
                rc1.metric("Area in pad", f"{reinf_res.A_pad_mm2:,.0f} mm²")
            rc2.metric("Total available", f"{reinf_res.A_total_mm2:,.0f} mm²")
            delta_v = reinf_res.A_total_mm2 - reinf_res.A_required_mm2
            rc2.metric(
                "Surplus / Deficit",
                f"{abs(delta_v):,.0f} mm²",
                delta=f"{'surplus' if delta_v >= 0 else 'deficit'} {delta_v:+,.0f} mm²",
                delta_color="normal" if delta_v >= 0 else "inverse",
            )
            if reinf_res.pad_required:
                pad_label = (f"Pad required — width ≥ {reinf_res.pad_width_mm:.0f} mm each side, "
                             f"thickness {reinf_res.pad_thickness_mm:.0f} mm")
                if delta_v >= 0:
                    st.success(pad_label)
                else:
                    st.error(f"Reinforcement insufficient even with computed pad. {pad_label}")
            else:
                st.success("No pad required — shell/nozzle wall excess is sufficient.")
            st.caption(reinf_res.clause)

        # ── Flange rating ──────────────────────────────────────────────────────
        with st.expander("**Flange pressure rating**", expanded=False):
            if code_key == "EN":
                st.markdown(
                    f"PN{pn_sel} rated at **{pn_at_T:.1f} barg** at {T_C:.0f} °C  "
                    f"(Group 1.1 carbon steel per EN 1092-1 Annex B derating)")
            else:
                st.markdown(
                    f"Class {pn_sel} rated at **{pn_at_T:.1f} barg** at ambient "
                    f"(ASME B16.5 Group 1.1 — no temp derating applied in this screener)")
            if flange_ok:
                st.success(f"✓ Design pressure {P_barg:.1f} barg ≤ flange rating {pn_at_T:.1f} barg")
            else:
                st.error(
                    f"✗ Design pressure {P_barg:.1f} barg > flange rating {pn_at_T:.1f} barg at {T_C:.0f} °C. "
                    "Select a higher PN/Class.")

        # ── Alternative head comparison ────────────────────────────────────────
        with st.expander("**Try other head types at this d_top**", expanded=False):
            st.caption(
                f"Can DN{dn_mm} at d_top = {d_top_mm:.0f} mm fit on other head types?")
            compare_heads = [h for h in HeadType if h != head_type]
            rows = []
            for h in compare_heads:
                try:
                    r_alt = nozzle_on_head(
                        h, Di, d_top_mm, dn_mm,
                        crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
                        alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
                        nozzle_OD_mm=nozzle_OD_mm, nozzle_t_mm=nozzle_t_override,
                    )
                    rows.append({
                        "Head type": head_label_map[h],
                        "Head depth (mm)": f"{r_alt.head_depth_mm:.0f}",
                        "x from axis (mm)": f"{r_alt.x_from_axis_mm:.0f}",
                        "Zone": r_alt.zone,
                        "Geom OK": "✓" if r_alt.geom_ok else "✗",
                        "Code OK": "✓" if r_alt.code_ok else ("?" if r_alt.code_ok is None else "✗"),
                        "Edge to wall (mm)": f"{r_alt.edge_to_shell_mm:.0f}",
                    })
                except Exception:
                    pass
            if rows:
                import pandas as pd
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
