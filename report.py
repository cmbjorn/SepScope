"""
Vessel datasheet report generator — produces a self-contained HTML file
suitable for printing to PDF and sharing with a vessel fabricator.

The report follows a typical equipment datasheet structure:
  1. Title / identification block
  2. Vessel sketch (SVG, not interactive)
  3. Process data
  4. Mechanical design data
  5. Nozzle schedule
  6. Separator sizing results
  7. Engineering findings / warnings
"""
from __future__ import annotations
import math
import html as _html
from datetime import date

# ── CSS ──────────────────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; }
body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 10pt;
    color: #111;
    margin: 18mm 14mm;
}
h1 { font-size: 14pt; margin: 0 0 2px 0; }
h2 { font-size: 11pt; margin: 0; }
.ds-header {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: start;
    border: 2px solid #222;
    padding: 8px 10px;
    margin-bottom: 8px;
}
.ds-header-right { text-align: right; font-size: 9pt; color: #555; }
.rev-block { font-size: 8pt; border: 1px solid #ccc; padding: 3px 6px; margin-top: 4px; }
.section {
    margin-bottom: 8px;
}
.section-title {
    background: #1e3a5f;
    color: #fff;
    font-weight: bold;
    padding: 3px 8px;
    font-size: 10pt;
    margin-bottom: 0;
}
table {
    border-collapse: collapse;
    width: 100%;
    font-size: 9.5pt;
}
th, td {
    border: 1px solid #b0b8c4;
    padding: 3px 7px;
    vertical-align: top;
}
th {
    background: #dce4ef;
    font-weight: bold;
    text-align: left;
}
td.num { text-align: right; font-family: 'Courier New', monospace; }
tr:nth-child(even) td { background: #f7f9fc; }
.two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 8px;
}
.three-col {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
    margin-bottom: 8px;
}
.finding {
    padding: 4px 8px;
    margin: 3px 0;
    border-radius: 2px;
    font-size: 9pt;
}
.finding-error   { background: #fee2e2; border-left: 4px solid #dc2626; }
.finding-warning { background: #fef9c3; border-left: 4px solid #d97706; }
.finding-info    { background: #eff6ff; border-left: 4px solid #3b82f6; }
.finding-ok      { background: #f0fdf4; border-left: 4px solid #16a34a; color: #166534; }
.sketch-wrap {
    border: 1px solid #ccc;
    background: #fff;
    text-align: center;
    padding: 4px;
    margin-bottom: 8px;
}
@media print {
    body { margin: 10mm; }
    .no-print { display: none; }
}
"""

# ── Sketch SVG ────────────────────────────────────────────────────────────────

def _vessel_sketch_svg(
    Di: float,
    L_shell: float,
    h_head: float,
    t_shell: float,
    nozzle_results: list,   # (nz, nres, rres, flange_ok, pn_at_T)
    levels_mm: dict,
    nll_mm: float,
    saddle_a_mm: float = 0.0,
    saddle_w_mm: float = 250.0,
) -> str:
    """Return an SVG string with a simplified side-view vessel sketch."""
    R = Di / 2.0

    # Drawing coordinate system: x=axial (mm from left tangent), y=from vessel bottom (mm)
    # Vessel body spans x: [-h_head, L_shell+h_head], y: [0, Di]
    # We add margins around that.
    mg_x = max(h_head * 1.5, 80.0)
    mg_y = max(R * 0.6, 60.0)

    real_w = L_shell + 2 * h_head + 2 * mg_x
    real_h = Di + 2 * mg_y

    svg_w = 860
    svg_h = max(220, int(svg_w * real_h / real_w))

    scale = svg_w / real_w
    ox = mg_x + h_head         # x-origin in real coords → 0 at left tangent
    oy_top = mg_y + Di         # y in SVG = oy_top - y_real (y increases downward in SVG)

    def px(x_real):
        return (x_real + ox) * scale

    def py(y_real):  # y_real = 0 at vessel bottom
        return (oy_top - y_real) * scale

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" '
        f'style="background:#fff; font-family:Arial,sans-serif;">'
    ]

    def line(x1, y1, x2, y2, color="#222", width=1.5, dash=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        lines.append(
            f'<line x1="{px(x1):.1f}" y1="{py(y1):.1f}" '
            f'x2="{px(x2):.1f}" y2="{py(y2):.1f}" '
            f'stroke="{color}" stroke-width="{width}"{d}/>'
        )

    def rect(x, y, w, h, fill="none", stroke="#222", sw=1.5):
        lines.append(
            f'<rect x="{px(x):.1f}" y="{py(y+h):.1f}" '
            f'width="{w*scale:.1f}" height="{h*scale:.1f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def circle(cx, cy, r, fill="#eee", stroke="#222", sw=1.2):
        lines.append(
            f'<circle cx="{px(cx):.1f}" cy="{py(cy):.1f}" r="{r*scale:.1f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def text(x, y, s, anchor="middle", size=9, color="#333", bold=False):
        fw = "bold" if bold else "normal"
        lines.append(
            f'<text x="{px(x):.1f}" y="{py(y):.1f}" '
            f'text-anchor="{anchor}" dominant-baseline="auto" '
            f'font-size="{size}" font-weight="{fw}" fill="{color}">'
            f'{_html.escape(str(s))}</text>'
        )

    # ── Liquid fill at NLL ────────────────────────────────────────────────────
    liq_h = max(0.0, min(Di, nll_mm))
    rect(0.0, 0.0, L_shell, liq_h,
         fill="rgba(147,197,253,0.35)", stroke="none", sw=0)
    # NLL line
    if 0 < liq_h < Di:
        line(0, liq_h, L_shell, liq_h, color="#2563eb", width=1.5, dash="6,3")

    # ── Shell body ───────────────────────────────────────────────────────────
    rect(0.0, 0.0, L_shell, Di, fill="none", stroke="#1e40af", sw=2.0)

    # ── Endcaps (simplified as rectangles for now) ───────────────────────────
    if h_head > 0:
        # Left head
        rect(-h_head, 0.0, h_head, Di, fill="none", stroke="#1e40af", sw=1.5)
        # Right head
        rect(L_shell, 0.0, h_head, Di, fill="none", stroke="#1e40af", sw=1.5)

    # ── Centreline ───────────────────────────────────────────────────────────
    line(-h_head - 20, R, L_shell + h_head + 20, R,
         color="#94a3b8", width=0.8, dash="4,4")

    # ── Tangent lines ─────────────────────────────────────────────────────────
    for tx in (0.0, L_shell):
        line(tx, -mg_y * 0.2, tx, Di + mg_y * 0.2,
             color="#94a3b8", width=0.8, dash="4,4")

    # ── Saddle supports ───────────────────────────────────────────────────────
    if saddle_a_mm > 0:
        for sx in (saddle_a_mm, L_shell - saddle_a_mm):
            sw2 = saddle_w_mm / 2.0
            saddle_h_real = R * 0.22
            rect(sx - sw2, -saddle_h_real, saddle_w_mm, saddle_h_real,
                 fill="#e2e8f0", stroke="#64748b", sw=1.2)

    # ── Nozzles ───────────────────────────────────────────────────────────────
    from engines.nozzle_geometry import NOZZLE_OD
    for nz, nres, rres, _fok, _pat in nozzle_results:
        dn  = nz["dn"]
        loc = nz["loc"]
        nOR = NOZZLE_OD.get(dn, dn * 1.05) / 2.0
        disp_r = min(nOR, R * 0.22)
        tag = nz["tag"]

        geom_ok = nres.geom_ok if nres else True
        code_ok = nres.code_ok if nres else None
        reinf_ok = rres.adequate if rres else True
        if not geom_ok or reinf_ok is False:
            nc = "#dc2626"
        elif code_ok is False or reinf_ok is None:
            nc = "#d97706"
        else:
            nc = "#1e40af"

        stub = max(disp_r * 1.4, 18.0)

        if loc == "Left head" and nres is not None:
            # Nozzle on left head
            ny_real = Di - nres.d_from_top_mm   # from bottom
            line(-h_head - stub, ny_real, -h_head, ny_real, color=nc, width=1.5)
            circle(-h_head - stub, ny_real, disp_r, fill="#dbeafe", stroke=nc, sw=1.5)
            text(-h_head - stub - disp_r - 4, ny_real + 2, tag,
                 anchor="end", size=8, color=nc, bold=True)

        elif loc == "Right head" and nres is not None:
            ny_real = Di - nres.d_from_top_mm
            line(L_shell + h_head, ny_real, L_shell + h_head + stub, ny_real, color=nc, width=1.5)
            circle(L_shell + h_head + stub, ny_real, disp_r, fill="#dbeafe", stroke=nc, sw=1.5)
            text(L_shell + h_head + stub + disp_r + 4, ny_real + 2, tag,
                 anchor="start", size=8, color=nc, bold=True)

        elif loc == "Shell — top":
            nx_real = nz["axial_mm"]
            line(nx_real, Di, nx_real, Di + stub, color=nc, width=1.5)
            circle(nx_real, Di + stub, disp_r, fill="#dbeafe", stroke=nc, sw=1.5)
            text(nx_real, Di + stub + disp_r + 10, tag,
                 anchor="middle", size=8, color=nc, bold=True)

        elif loc == "Shell — bottom":
            nx_real = nz["axial_mm"]
            line(nx_real, 0, nx_real, -stub, color=nc, width=1.5)
            circle(nx_real, -stub, disp_r, fill="#dbeafe", stroke=nc, sw=1.5)
            text(nx_real, -stub - disp_r - 4, tag,
                 anchor="middle", size=8, color=nc, bold=True)

        elif loc == "Shell — side":
            nx_real = nz["axial_mm"]
            circle(nx_real, Di, disp_r * 0.7, fill="#dbeafe", stroke=nc, sw=1.2)
            text(nx_real, Di + disp_r * 0.7 + 10, tag,
                 anchor="middle", size=7, color=nc)

    # ── Level line labels ─────────────────────────────────────────────────────
    _level_colours = {
        "LZLL": "#4b5563", "LALL": "#dc2626", "LAL": "#f97316",
        "NLL":  "#2563eb", "LAH":  "#f97316", "LAHH": "#dc2626", "LZHH": "#4b5563",
    }
    for tag, h_mm in levels_mm.items():
        lc = _level_colours.get(tag, "#64748b")
        if tag == "NLL":
            continue  # already drawn above
        if 0 < h_mm < Di:
            line(0, h_mm, L_shell, h_mm, color=lc, width=0.8, dash="4,3")
        text(L_shell + h_head + 6, h_mm + 2, tag, anchor="start", size=7, color=lc)

    text(L_shell + h_head + 6, liq_h + 2, "NLL", anchor="start", size=7,
         color="#2563eb", bold=True)

    # ── Dimension annotations ─────────────────────────────────────────────────
    y_dim = -mg_y * 0.6   # below vessel
    dim_y = y_dim
    line(-h_head, dim_y, L_shell + h_head, dim_y, color="#475569", width=1.0)
    for xt in (-h_head, L_shell + h_head):
        line(xt, dim_y - 5, xt, dim_y + 5, color="#475569", width=1.0)
    total_len = L_shell + 2 * h_head
    text((L_shell) / 2, dim_y - 8,
         f"T–T = {L_shell:,.0f} mm   P–P = {total_len:,.0f} mm",
         anchor="middle", size=8, color="#475569")
    # Di arrow on right side
    x_arrow = L_shell + h_head + mg_x * 0.55
    line(x_arrow, 0, x_arrow, Di, color="#475569", width=1.0)
    for yt in (0, Di):
        line(x_arrow - 5, yt, x_arrow + 5, yt, color="#475569", width=1.0)
    text(x_arrow + 8, Di / 2, f"Di={Di:.0f}", anchor="start", size=8, color="#475569")

    lines.append("</svg>")
    return "\n".join(lines)


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _h(s: str) -> str:
    return _html.escape(str(s))


def _section(title: str, content: str) -> str:
    return (
        f'<div class="section">'
        f'<div class="section-title">{_h(title)}</div>'
        f'{content}'
        f'</div>'
    )


def _table(headers: list[str], rows: list[list], num_cols: set | None = None) -> str:
    num_cols = num_cols or set()
    ths = "".join(f"<th>{_h(h)}</th>" for h in headers)
    trs = []
    for row in rows:
        cells = []
        for i, v in enumerate(row):
            cls = ' class="num"' if i in num_cols else ""
            cells.append(f"<td{cls}>{_h(v) if not str(v).startswith('<') else v}</td>")
        trs.append("<tr>" + "".join(cells) + "</tr>")
    return f'<table><thead><tr>{ths}</tr></thead><tbody>{"".join(trs)}</tbody></table>'


def _kv_table(pairs: list[tuple]) -> str:
    rows = "".join(
        f'<tr><td style="font-weight:bold;color:#1e3a5f;width:45%">{_h(k)}</td>'
        f'<td>{_h(v)}</td></tr>'
        for k, v in pairs
    )
    return f'<table style="width:100%">{rows}</table>'


# ── Main report function ──────────────────────────────────────────────────────

def generate_datasheet_html(
    vessel_tag: str,
    Di: float,
    L_shell: float,
    h_head: float,
    P_barg: float,
    T_C: float,
    mat_key: str,
    head_type_label: str,
    code_key: str,
    fd_MPa: float,
    shell_res,
    head_res,
    nozzle_results: list,    # (nz, nres, rres, flange_ok, pn_at_T)
    levels_mm: dict,
    sep_res,
    gas_props,
    liq_props,
    Q_gas_m3h: float,
    Q_liq_m3h: float,
    gas_fluid: str,
    liq_fluid: str,
    placement_checks: list,
    head_warnings: list,
    shell_warnings: list,
    saddle_a_mm: float,
    saddle_w_mm: float,
    has_meshpad: bool,
    has_baffles: bool,
    has_inlet_dev: bool,
    has_vortex_brk: bool,
    L_baffle_mm: float,
    baffle_open_pct: float,
    K_sb: float,
    include_heads: bool = True,
) -> str:
    from engines.nozzle_geometry import NOZZLE_OD, NOZZLE_WALL_T, NOZZLE_WALL_SCH, recommended_schedule
    from standards import EN_PN_RATINGS, ASME_CLASS_PRESSURE_20C

    today = date.today().strftime("%Y-%m-%d")
    nll_mm = levels_mm.get("NLL", Di * 0.5)
    R = Di / 2.0
    total_len = L_shell + 2 * h_head

    pn_label = "PN" if code_key == "EN" else "Class"

    # ── Sketch ────────────────────────────────────────────────────────────────
    sketch_svg = _vessel_sketch_svg(
        Di, L_shell, h_head, shell_res.t_nom_mm,
        nozzle_results, levels_mm, nll_mm,
        saddle_a_mm, saddle_w_mm,
    )

    # ── 1. Title block ────────────────────────────────────────────────────────
    title_html = f"""
<div class="ds-header">
  <div>
    <h1>Vessel Equipment Datasheet</h1>
    <h2>Horizontal Two-Phase Separator</h2>
    <div style="margin-top:6px; font-size:11pt">
      <b>Equipment Tag:</b> {_h(vessel_tag)}&nbsp;&nbsp;
      <b>Service:</b> {_h(gas_fluid)} / {_h(liq_fluid)} separation&nbsp;&nbsp;
      <b>Design Code:</b> {"EN 13445-3:2021" if code_key == "EN" else "ASME VIII Div.1"}
    </div>
  </div>
  <div class="ds-header-right">
    <div>Rev. A &nbsp;|&nbsp; {_h(today)}</div>
    <div class="rev-block">Prepared by VesselCalc<br>For quotation purposes only</div>
  </div>
</div>"""

    # ── 2. Process data ───────────────────────────────────────────────────────
    proc_gas = _kv_table([
        ("Fluid", gas_fluid),
        ("Phase", "Gas / vapour"),
        ("Mol. weight (g/mol)", f"{gas_props.MW:.2f}" if gas_props.MW else "—"),
        ("Density at op. cond. (kg/m³)", f"{gas_props.rho_kgm3:.3f}"),
        ("Viscosity (μPa·s)", f"{gas_props.mu_Pas*1e6:.1f}"),
        ("Flow rate (m³/h actual)", f"{Q_gas_m3h:,.1f}"),
        ("Flow rate (kg/h)", f"{Q_gas_m3h * gas_props.rho_kgm3:,.0f}"),
    ])
    proc_liq = _kv_table([
        ("Fluid", liq_fluid),
        ("Phase", "Liquid"),
        ("Density at op. cond. (kg/m³)", f"{liq_props.rho_kgm3:.0f}"),
        ("Viscosity (mPa·s)", f"{liq_props.mu_Pas*1e3:.3f}"),
        ("Flow rate (m³/h)", f"{Q_liq_m3h:,.1f}"),
        ("Flow rate (kg/h)", f"{Q_liq_m3h * liq_props.rho_kgm3:,.0f}"),
    ])
    cond_data = _kv_table([
        ("Design pressure (barg)", f"{P_barg:.1f}"),
        ("Design temperature (°C)", f"{T_C:.0f}"),
        ("Operating pressure", "See design conditions"),
        ("Test pressure (barg)", f"{P_barg * 1.43:.1f}   (hydro, 1.43 × design)"),
    ])

    proc_html = f"""
<div class="three-col">
  <div>
    <div class="section-title" style="margin-bottom:4px">Gas Phase</div>
    {proc_gas}
  </div>
  <div>
    <div class="section-title" style="margin-bottom:4px">Liquid Phase</div>
    {proc_liq}
  </div>
  <div>
    <div class="section-title" style="margin-bottom:4px">Design Conditions</div>
    {cond_data}
  </div>
</div>"""

    # ── 3. Mechanical data ────────────────────────────────────────────────────
    mech_vessel = _kv_table([
        ("Internal diameter Di (mm)", f"{Di:,.0f}"),
        ("Shell length T–T (mm)", f"{L_shell:,.0f}"),
        ("Overall length P–P (mm)", f"{total_len:,.0f}"),
        ("Head type", head_type_label),
        ("Head depth h (mm)", f"{h_head:.0f}"),
        ("Shell wall thickness (mm)",
         f"{shell_res.t_nom_mm:.1f}  (calc. {shell_res.t_calc_mm:.2f} mm)"),
        ("Head wall thickness (mm)",
         f"{head_res.t_nom_mm:.1f}  (calc. {head_res.t_calc_mm:.2f} mm)"),
        ("Shell material", mat_key),
        ("Allowable stress fd (MPa)", f"{fd_MPa:.1f}"),
        ("Weld joint factor z", "1.0"),
        ("Corrosion allowance (mm)", "see input"),
    ])
    mech_supports = _kv_table([
        ("Support type", "Saddle supports (2 off)"),
        ("Saddle position from tangent (mm)",
         f"{saddle_a_mm:.0f}" if saddle_a_mm > 0 else "TBD"),
        ("Saddle width (mm)", f"{saddle_w_mm:.0f}"),
        ("Design code",
         "EN 13445-3:2021 cl.16  /  Zick analysis" if code_key == "EN"
         else "ASME VIII Div.1  /  Zick analysis"),
        ("Orientation", "Horizontal"),
    ])
    mech_intern = _kv_table([
        ("Inlet device", "Half-pipe distributor" if has_inlet_dev else "None"),
        ("Inlet baffles",
         f"Distribution plate, {baffle_open_pct:.0f}% open, at {L_baffle_mm:.0f} mm from each tangent"
         if has_baffles else "None"),
        ("Gas demister", f"Mesh pad demister  K={K_sb:.2f} m/s" if has_meshpad else "None"),
        ("Liquid outlet", "Vortex breaker" if has_vortex_brk else "No vortex breaker"),
    ])
    mech_html = f"""
<div class="two-col">
  <div>
    <div class="section-title" style="margin-bottom:4px">Vessel Dimensions & Design</div>
    {mech_vessel}
  </div>
  <div>
    <div class="section-title" style="margin-bottom:4px">Supports</div>
    {mech_supports}
    <div style="margin-top:8px">
    <div class="section-title" style="margin-bottom:4px">Internals</div>
    {mech_intern}
    </div>
  </div>
</div>"""

    # ── 4. Nozzle schedule ────────────────────────────────────────────────────
    nz_headers = ["Tag", "Service", "Location", "DN", pn_label, "OD (mm)",
                  "Wall (mm)", "Sched.", "Geom", "Reinf", "Flange", "Notes"]
    nz_rows = []
    lzhh_mm = levels_mm.get("LZHH", 0.0)
    for nz, nres, rres, fok, pat in nozzle_results:
        dn = nz["dn"]
        nz_OD = NOZZLE_OD.get(dn, dn * 1.05)
        rec = recommended_schedule(nz.get("pn", 25), code_key)
        nz_t = float(NOZZLE_WALL_SCH[rec].get(dn, NOZZLE_WALL_T.get(dn, 8.0)))
        geom_s = "✓" if (nres is None or nres.geom_ok) else "✗"
        reinf_s = "✓" if (rres is None or rres.adequate) else "✗"
        flng_s = "✓" if fok else "✗"

        notes = ""
        if nres is not None and nz.get("service") == "Inlet":
            nz_IR = (nz_OD - 2.0 * nz_t) / 2.0
            nz_bot = (Di - nres.d_from_top_mm) - nz_IR
            dist = lzhh_mm - nz_bot
            notes = f"Bottom of bore {dist:+.0f} mm to LZHH"
        elif nres is not None:
            notes = f"Zone: {nres.zone}"

        nz_rows.append([
            nz["tag"], nz["service"], nz["loc"], f"DN{dn}",
            str(nz.get("pn", "")),
            f"{nz_OD:.1f}", f"{nz_t:.1f}", rec,
            geom_s, reinf_s, flng_s, notes,
        ])

    nozzle_table = _table(nz_headers, nz_rows, num_cols={5, 6})

    # ── 5. Separator sizing ───────────────────────────────────────────────────
    sep_pairs = [
        ("Gas space area at NLL (m²)",         f"{sep_res.A_gas_m2:.4f}"),
        ("Actual gas velocity (m/s)",           f"{sep_res.U_act_ms:.4f}"),
        (f"Max gas velocity {'(mesh pad)' if has_meshpad else '(open)'} (m/s)",
                                                f"{sep_res.U_max_ms:.4f}"),
        ("Gas velocity status",
         "✓ OK" if sep_res.gas_velocity_ok else "✗ EXCEEDS LIMIT"),
        ("Gas residence time (min)",            f"{sep_res.t_gas_s/60:.2f}"),
        ("Liquid hold-up time (min)",           f"{sep_res.t_holdup_s/60:.2f}"),
        ("Hold-up status",
         "✓ OK" if sep_res.holdup_ok else "✗ BELOW REQUIRED"),
        ("Surge time (min)",                    f"{sep_res.t_surge_s/60:.2f}"),
        ("Surge status",
         "✓ OK" if sep_res.surge_ok else "✗ BELOW REQUIRED"),
        ("Effective separation length (mm)",    f"{sep_res.L_eff_mm:.0f}"),
        ("NLL height from bottom (mm)",         f"{sep_res.nll_mm:.0f}"),
        ("Gas space height at NLL (mm)",        f"{sep_res.gas_space_height_mm:.0f}"),
        ("Droplet cut size — gas phase (μm)",   f"{sep_res.d_cut_gas_um:.0f}"),
        ("Bubble cut size — liquid phase (μm)", f"{sep_res.d_cut_liq_um:.0f}"),
        ("Liquid vol. at NLL — eff. zone (m³)", f"{sep_res.V_liq_eff_m3:.3f}"),
        ("Surge vol. NLL→LAHH — eff. zone (m³)", f"{sep_res.V_surge_eff_m3:.3f}"),
    ]
    sep_table = _kv_table(sep_pairs)

    # ── 6. Findings ───────────────────────────────────────────────────────────
    findings_html = ""
    all_findings: list[tuple] = []
    for w in head_warnings + shell_warnings:
        all_findings.append(("warning", "", w, ""))
    for chk in placement_checks:
        tags = f"[{', '.join(chk.tags)}] " if chk.tags else ""
        all_findings.append((chk.level, tags, chk.headline, chk.detail))

    if not all_findings:
        findings_html = '<div class="finding finding-ok">✓ No engineering issues detected.</div>'
    else:
        for level, tags, headline, detail in all_findings:
            cls = {
                "error": "finding-error",
                "warning": "finding-warning",
                "info": "finding-info",
            }.get(level, "finding-warning")
            icon = {"error": "🚫", "warning": "⚠️", "info": "ℹ️"}.get(level, "⚠️")
            det = f"<br><span style='color:#555'>{_h(detail)}</span>" if detail else ""
            findings_html += (
                f'<div class="finding {cls}">'
                f'{icon} <b>{_h(tags)}{_h(headline)}</b>{det}'
                f'</div>\n'
            )

    # ── Assemble ──────────────────────────────────────────────────────────────
    body = f"""
{title_html}

<div class="sketch-wrap">
{sketch_svg}
<div style="font-size:8pt;color:#555;margin-top:2px">
  Schematic only — not to scale. Nozzle positions shown are axial centrelines.
</div>
</div>

{_section("PROCESS DATA", proc_html)}
{_section("MECHANICAL DESIGN", mech_html)}
{_section("NOZZLE SCHEDULE", nozzle_table)}
{_section("SEPARATOR SIZING (screening-level)", sep_table)}
{_section("ENGINEERING FINDINGS / NOTES", findings_html)}

<div style="margin-top:16px;border-top:1px solid #ccc;padding-top:6px;
            font-size:8pt;color:#555;text-align:center">
Generated by <b>VesselCalc</b> on {_h(today)}.
This document is for design screening only and does not constitute a formal engineering
calculation or fabrication document. All dimensions and ratings must be verified by a
qualified engineer prior to fabrication.
</div>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vessel Datasheet — {_h(vessel_tag)}</title>
<style>{_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""
