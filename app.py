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
)
from engines.nozzle_geometry import NOZZLE_OD, NOZZLE_WALL_T, _tori_geometry
from standards import DN_SIZES, EN_PN_RATINGS, ASME_CLASS_PRESSURE_20C, max_pn_for_temperature

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
    nres,
    cyl_len_show: float = 400.0,
) -> go.Figure:
    """Horizontal side-view cross-section: head on left, cylinder on right."""
    R = Di / 2
    zs_upper, ys_upper = _head_surface_points(head_type, Di, R_c, r_k, alpha_deg, b)
    h_head = max((abs(z) for z in zs_upper), default=0.0)

    fig = go.Figure()

    # ── Torispherical crown zone fill ─────────────────────────────────────────
    if head_type == HeadType.TORISPHERICAL:
        tg = _tori_geometry(Di, R_c, r_k)
        r_cj = tg["r_cj"]
        z_cj = tg["z_cj"]
        Z_sc = tg["Z_sc"]

        angle_junc = math.asin(min(1.0, r_cj / R_c))
        N_cr = 60
        crown_z = [-(Z_sc + R_c * math.cos(angle_junc * i / N_cr)) for i in range(N_cr + 1)]
        crown_y = [R_c * math.sin(angle_junc * i / N_cr) for i in range(N_cr + 1)]

        # Polygon: upper arc forward + lower arc backward (vertical close at junction)
        fill_z = crown_z + list(reversed(crown_z))
        fill_y = crown_y + [-y for y in reversed(crown_y)]
        fig.add_trace(go.Scatter(
            x=fill_z, y=fill_y,
            fill="toself", fillcolor="rgba(34,197,94,0.10)",
            line=dict(color="rgba(0,0,0,0)", width=0),
            name="Crown zone", hoverinfo="skip",
        ))
        fig.add_shape(
            type="line", x0=-z_cj, x1=-z_cj, y0=-r_cj, y1=r_cj,
            line=dict(color="rgba(34,197,94,0.7)", width=1.5, dash="dash"),
        )

    # ── Cylinder inner walls ──────────────────────────────────────────────────
    for sign in (1, -1):
        fig.add_trace(go.Scatter(
            x=[0.0, cyl_len_show], y=[sign * R, sign * R],
            mode="lines", line=dict(color="#2563eb", width=2.5),
            name="Shell inner wall" if sign == 1 else None,
            showlegend=(sign == 1), hoverinfo="skip",
        ))

    # ── Head inner surface (full cross-section) ───────────────────────────────
    full_z = zs_upper + list(reversed(zs_upper))
    full_y = ys_upper + [-y for y in reversed(ys_upper)]
    fig.add_trace(go.Scatter(
        x=full_z, y=full_y,
        mode="lines", line=dict(color="#2563eb", width=2.5),
        name="Head inner surface", hoverinfo="skip",
    ))

    # ── Outer walls (approximate) ─────────────────────────────────────────────
    if t_shell_nom > 0:
        for sign in (1, -1):
            fig.add_trace(go.Scatter(
                x=[0.0, cyl_len_show],
                y=[sign * (R + t_shell_nom), sign * (R + t_shell_nom)],
                mode="lines",
                line=dict(color="#93c5fd", width=1.5, dash="dot"),
                name="Shell outer wall" if sign == 1 else None,
                showlegend=(sign == 1), hoverinfo="skip",
            ))

    # ── Tangent line and centreline ───────────────────────────────────────────
    fig.add_vline(x=0, line=dict(color="#94a3b8", dash="dot", width=1))
    fig.add_hline(y=0, line=dict(color="#e2e8f0", width=1, dash="dot"))

    # ── Nozzle ────────────────────────────────────────────────────────────────
    if nres is not None:
        nz = -nres.z_on_head_mm
        ny = nres.y_nozzle_mm
        nOR = nres.nozzle_OR_mm

        if not nres.geom_ok:
            nc, nfill = "#dc2626", "rgba(220,38,38,0.18)"
        elif nres.code_ok is False:
            nc, nfill = "#d97706", "rgba(217,119,6,0.20)"
        else:
            nc, nfill = "#16a34a", "rgba(22,163,74,0.20)"

        theta_pts = [i / 30 * 2 * math.pi for i in range(31)]
        fig.add_trace(go.Scatter(
            x=[nz + nOR * math.cos(t) for t in theta_pts],
            y=[ny + nOR * math.sin(t) for t in theta_pts],
            fill="toself", fillcolor=nfill,
            line=dict(color=nc, width=2),
            name=f"DN{nres.dn_mm}",
            hovertemplate=(
                f"DN{nres.dn_mm}<br>"
                f"Height from top: {nres.d_from_top_mm:.0f} mm<br>"
                f"y from axis: {nres.y_nozzle_mm:.0f} mm<br>"
                f"Axial depth: {nres.z_on_head_mm:.0f} mm from tangent<br>"
                f"Zone: {nres.zone}"
                "<extra></extra>"
            ),
        ))
        fig.add_trace(go.Scatter(
            x=[nz], y=[ny], mode="markers",
            marker=dict(color=nc, size=7, symbol="cross-thin",
                        line=dict(width=2, color=nc)),
            showlegend=False, hoverinfo="skip",
        ))

        # d_from_top dimension annotation — vertical arrow left of head
        if nres.d_from_top_mm > 5 and abs(ny - R) > 5:
            z_ann = -(h_head + 70)
            fig.add_shape(type="line", x0=z_ann, x1=z_ann, y0=R, y1=ny,
                          line=dict(color="#64748b", width=1.5))
            for y_tick in (R, ny):
                fig.add_shape(type="line",
                              x0=z_ann - 8, x1=z_ann + 8, y0=y_tick, y1=y_tick,
                              line=dict(color="#64748b", width=1.5))
            fig.add_annotation(
                x=z_ann - 14, y=(R + ny) / 2,
                text=f"{nres.d_from_top_mm:.0f} mm",
                showarrow=False, xanchor="right",
                font=dict(size=11, color="#475569"),
            )

        # Di label inside cylinder
        fig.add_annotation(
            x=cyl_len_show * 0.55, y=0,
            text=f"Di = {Di:.0f} mm",
            showarrow=False, font=dict(size=11, color="#475569"),
        )

    # ── Pole label ────────────────────────────────────────────────────────────
    fig.add_annotation(
        x=-(h_head + 2) if h_head > 0 else -5, y=0,
        text="Pole", showarrow=False, xanchor="right",
        font=dict(size=10, color="#64748b"),
    )

    x_min = -(h_head + 180)
    x_max = cyl_len_show + 60
    y_lim = R + max(t_shell_nom, 30) + 60

    fig.update_layout(
        height=500,
        margin=dict(l=10, r=10, t=10, b=30),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=True,
        legend=dict(orientation="h", x=0.0, y=-0.09,
                    bgcolor="rgba(255,255,255,0.8)"),
        xaxis=dict(
            title="Axial position (mm) — 0 = tangent line",
            range=[x_min, x_max],
            zeroline=False, gridcolor="#f8fafc", tickformat=",d",
        ),
        yaxis=dict(
            title="Vertical position (mm) — 0 = vessel axis",
            range=[-y_lim, y_lim],
            gridcolor="#f8fafc",
        ),
    )
    return fig


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
            HeadType.HEMISPHERICAL: "Hemispherical",
            HeadType.ELLIPSOIDAL:   "Ellipsoidal 2:1",
            HeadType.TORISPHERICAL: "Torispherical (Klöpper / dished)",
            HeadType.CONICAL:       "Conical",
            HeadType.FLAT:          "Flat (unstayed)",
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
        nozzle_OD_mm = NOZZLE_OD.get(dn_mm, dn_mm * 1.05)
        nozzle_t_default = NOZZLE_WALL_T.get(dn_mm, 8.0)

        if code_key == "EN":
            pn_options = [p for p in EN_PN_RATINGS if p >= 1]
            pn_sel = st.selectbox("Flange PN rating", options=pn_options,
                                  index=pn_options.index(25) if 25 in pn_options else 0,
                                  key="pn_sel")
        else:
            class_options = list(ASME_CLASS_PRESSURE_20C.keys())
            pn_sel = st.selectbox("Flange Class", options=class_options,
                                  index=1, key="pn_sel")

        d_from_top_mm = st.number_input(
            "Distance from vessel top inner wall (mm)",
            min_value=0.0, max_value=float(Di),
            value=min(float(Di) / 2, float(Di)),
            step=10.0, key="d_from_top",
            help=(
                "Vertical distance from the top inner wall to the nozzle centreline.\n"
                "0 mm = at the vessel top wall  |  "
                f"{Di/2:.0f} mm = on the axis  |  "
                f"{Di:.0f} mm = at the vessel bottom wall"
            ),
        )

        nozzle_t_override = st.number_input(
            "Nozzle wall thickness (mm)",
            min_value=1.0, max_value=100.0,
            value=float(nozzle_t_default),
            step=0.5, key="nozzle_t",
            help="Default: Sch 40 / standard wall for this DN.",
        )

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

    nozzle_res = nozzle_on_head(
        head_type, Di, d_from_top_mm, dn_mm,
        crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
        alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
        nozzle_OD_mm=nozzle_OD_mm, nozzle_t_mm=nozzle_t_override,
        t_head_nom_mm=head_res.t_nom_mm,
    )

    reinf_res = reinforcement_check(
        Di=Di, P_barg=P_barg, fd_MPa=fd,
        nozzle_OD_mm=nozzle_OD_mm, nozzle_t_mm=nozzle_t_override,
        t_head_req_mm=head_res.t_calc_mm,
        t_head_nom_mm=head_res.t_nom_mm,
        CA_mm=CA_mm, code=code_key, z=z_weld,
    )

    if code_key == "EN":
        pn_at_T  = max_pn_for_temperature(float(pn_sel), T_C)
        flange_ok = P_barg <= pn_at_T
    else:
        pn_at_T  = ASME_CLASS_PRESSURE_20C.get(str(pn_sel), 999.0)
        flange_ok = P_barg <= pn_at_T

    # ── Layout ────────────────────────────────────────────────────────────────
    col_fig, col_res = st.columns([1.1, 1.0], gap="medium")

    with col_fig:
        st.subheader("Cross-section diagram")
        fig = _vessel_figure(
            head_type, Di, R_c, r_k, alpha_deg_cone, b,
            t_head_nom=head_res.t_nom_mm,
            t_shell_nom=shell_res.t_nom_mm,
            nres=nozzle_res,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("**Placement summary**")
        badges = (
            _badge("Geometry",     nozzle_res.geom_ok) + " " +
            _badge("Code zone",    nozzle_res.code_ok) + " " +
            _badge("Reinforcement", reinf_res.adequate) + " " +
            _badge("Flange",       flange_ok)
        )
        st.markdown(badges, unsafe_allow_html=True)

        all_msgs = (
            [("error",   e) for e in nozzle_res.errors   + reinf_res.warnings] +
            [("warning", w) for w in nozzle_res.warnings + head_res.warnings + shell_res.warnings]
        )
        for kind, msg in all_msgs:
            if kind == "error":
                st.error(msg, icon="🚫")
            else:
                st.warning(msg, icon="⚠️")

    with col_res:
        with st.expander("**Material & allowable stress**", expanded=True):
            st.markdown(f"**{MATERIALS[mat_key]['name']}**")
            st.caption(stress["basis"])
            st.metric("Allowable stress fd", f"{fd:.1f} MPa")

        with st.expander("**Shell thickness**", expanded=True):
            c1, c2 = st.columns(2)
            c1.metric("Calculated t", f"{shell_res.t_calc_mm:.2f} mm")
            c2.metric("Nominal (rounded up)", f"{shell_res.t_nom_mm:.1f} mm")
            st.caption(f"{shell_res.clause}  —  {shell_res.formula}")

        with st.expander("**Head thickness**", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("Calculated e", f"{head_res.t_calc_mm:.2f} mm")
            c2.metric("Nominal (rounded up)", f"{head_res.t_nom_mm:.1f} mm")
            c3.metric("Head depth", f"{nozzle_res.head_depth_mm:.1f} mm")
            st.caption(f"{head_res.clause}  —  {head_res.formula}")

        with st.expander("**Nozzle placement geometry**", expanded=True):
            R = Di / 2
            ng_rows: dict[str, str] = {
                "Nozzle DN / OD":
                    f"DN{dn_mm}  /  {nozzle_OD_mm:.1f} mm OD",
                "Nozzle wall":
                    f"{nozzle_t_override:.1f} mm  "
                    f"(ID = {nozzle_OD_mm - 2*nozzle_t_override:.1f} mm)",
                "From top inner wall":
                    f"{nozzle_res.d_from_top_mm:.0f} mm  "
                    f"({'top' if nozzle_res.d_from_top_mm < 1 else 'bottom' if nozzle_res.d_from_top_mm > Di-1 else 'axis' if abs(nozzle_res.d_from_top_mm - R) < 1 else ''})",
                "y from vessel axis":
                    f"{nozzle_res.y_nozzle_mm:+.1f} mm  "
                    f"({'above' if nozzle_res.y_nozzle_mm > 0 else 'below' if nozzle_res.y_nozzle_mm < 0 else 'on'} axis)",
                "Axial depth on head":
                    f"{nozzle_res.z_on_head_mm:.1f} mm from tangent",
                "Radial offset from axis":
                    f"{nozzle_res.r_from_axis_mm:.1f} mm",
                "Zone":
                    nozzle_res.zone.replace("_", " ").capitalize(),
                "Edge to shell wall":
                    f"{nozzle_res.edge_to_shell_mm:.1f} mm",
            }
            if head_type == HeadType.TORISPHERICAL:
                if nozzle_res.d_at_crown_end_mm is not None:
                    ng_rows["Crown zone boundary"] = (
                        f"d = {nozzle_res.d_at_crown_end_mm:.0f} mm from top  "
                        f"(r = {nozzle_res.r_crown_end_mm:.0f} mm from axis)"
                    )
                if nozzle_res.edge_to_knuckle_mm is not None:
                    ng_rows["Edge to knuckle"] = f"{nozzle_res.edge_to_knuckle_mm:.1f} mm"

            for k, v in ng_rows.items():
                c1, c2 = st.columns([1.5, 1.5])
                c1.markdown(f"*{k}*")
                c2.markdown(f"**{v}**")

        with st.expander("**Nozzle reinforcement**", expanded=True):
            rc1, rc2 = st.columns(2)
            rc1.metric("Area required",   f"{reinf_res.A_required_mm2:,.0f} mm²")
            rc1.metric("Area in shell",   f"{reinf_res.A_shell_mm2:,.0f} mm²")
            rc1.metric("Area in nozzle",  f"{reinf_res.A_nozzle_mm2:,.0f} mm²")
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
                pad_txt = (
                    f"Pad required — width ≥ {reinf_res.pad_width_mm:.0f} mm each side, "
                    f"thickness {reinf_res.pad_thickness_mm:.0f} mm"
                )
                if delta_v >= 0:
                    st.success(pad_txt)
                else:
                    st.error(f"Reinforcement insufficient even with pad. {pad_txt}")
            else:
                st.success("No pad required — shell/nozzle wall excess is sufficient.")
            st.caption(reinf_res.clause)

        with st.expander("**Flange pressure rating**", expanded=False):
            if code_key == "EN":
                st.markdown(
                    f"PN{pn_sel} rated at **{pn_at_T:.1f} barg** at {T_C:.0f} °C "
                    f"(Group 1.1 carbon steel, EN 1092-1 Annex B)")
            else:
                st.markdown(
                    f"Class {pn_sel} rated at **{pn_at_T:.1f} barg** at ambient "
                    f"(ASME B16.5 Group 1.1)")
            if flange_ok:
                st.success(f"✓ {P_barg:.1f} barg ≤ {pn_at_T:.1f} barg")
            else:
                st.error(
                    f"✗ Design pressure {P_barg:.1f} barg > flange rating "
                    f"{pn_at_T:.1f} barg at {T_C:.0f} °C — select a higher PN/Class.")

        with st.expander("**Try other head types at this position**", expanded=False):
            st.caption(
                f"Can DN{dn_mm} at {d_from_top_mm:.0f} mm from top fit on other head types?")
            rows = []
            for h in HeadType:
                if h == head_type:
                    continue
                try:
                    r_alt = nozzle_on_head(
                        h, Di, d_from_top_mm, dn_mm,
                        crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
                        alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
                        nozzle_OD_mm=nozzle_OD_mm, nozzle_t_mm=nozzle_t_override,
                    )
                    rows.append({
                        "Head type":       head_label_map[h],
                        "Head depth (mm)": f"{r_alt.head_depth_mm:.0f}",
                        "r from axis (mm)": f"{r_alt.r_from_axis_mm:.0f}",
                        "Zone":            r_alt.zone,
                        "Geom OK":         "✓" if r_alt.geom_ok else "✗",
                        "Code OK":         "✓" if r_alt.code_ok else ("?" if r_alt.code_ok is None else "✗"),
                        "Edge to wall (mm)": f"{r_alt.edge_to_shell_mm:.0f}",
                    })
                except Exception:
                    pass
            if rows:
                import pandas as pd
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
