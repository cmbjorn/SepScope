"""
Vessel datasheet report generator — API 12J–aligned HTML output.

Structure (mirrors industry standard / API 12J Annex E):
  Header      — tag, project, revision, issued-for stamp, design code
  Sketch      — SVG side elevation with nozzles, levels, dimensions
  A  Design conditions   — operating & design P/T, hydro test
  B  Process fluids      — gas phase | liquid phase tables + inlet summary
  C  Mechanical design   — geometry, thicknesses, material, supports
  D  Separator sizing    — API 12J screening results (criterion/actual/limit/status)
  E  Liquid levels       — LZLL → LZHH with heights and volumes
  F  Internals           — inlet device, baffles, demister, vortex breaker
  G  Nozzle schedule     — fabricator-relevant columns
  H  Notes & findings    — engineering findings + disclaimer
"""
from __future__ import annotations
import math
import html as _esc
from datetime import date as _date

# ── CSS ──────────────────────────────────────────────────────────────────────

_CSS = """
*, *::before, *::after { box-sizing: border-box; }
body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 9.5pt;
    color: #111;
    margin: 12mm 14mm 16mm;
    line-height: 1.35;
}
/* ── Header ── */
.ds-header {
    display: grid;
    grid-template-columns: 1fr 260px;
    gap: 0;
    border: 2px solid #1e3a5f;
    margin-bottom: 10px;
}
.ds-header-left  { padding: 8px 10px; border-right: 2px solid #1e3a5f; }
.ds-header-right { padding: 0; }
.ds-title   { font-size: 15pt; font-weight: bold; color: #1e3a5f; margin: 0 0 3px; }
.ds-sub     { font-size: 10pt; color: #333; margin: 0 0 6px; }
.ds-meta    { font-size: 8.5pt; color: #555; }
.rev-table  { width: 100%; border-collapse: collapse; font-size: 8pt; }
.rev-table th, .rev-table td {
    border: 1px solid #1e3a5f; padding: 3px 5px; text-align: center;
}
.rev-table th { background: #dce4ef; font-weight: bold; }
.issued-stamp {
    background: #1e3a5f; color: #fff;
    font-size: 9.5pt; font-weight: bold;
    text-align: center; padding: 5px;
}
/* ── Sections ── */
.sec { margin-bottom: 9px; page-break-inside: avoid; }
.sec-title {
    background: #1e3a5f; color: #fff;
    font-weight: bold; font-size: 9.5pt;
    padding: 3px 8px; margin-bottom: 0;
    letter-spacing: 0.03em;
}
/* ── Generic 2-col KV table ── */
table.kv { width: 100%; border-collapse: collapse; }
table.kv td {
    border: 1px solid #b0b8c4; padding: 2px 7px;
    vertical-align: top;
}
table.kv td.k {
    width: 46%; font-weight: 500; color: #1e3a5f;
    background: #f4f6fa;
}
table.kv td.v { width: 54%; }
/* ── Side-by-side panels ── */
.two-panel { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 9px; }
.panel-title {
    background: #2d5f8a; color: #fff;
    font-weight: bold; font-size: 9pt;
    padding: 2px 7px; margin-bottom: 0;
}
/* ── General data table ── */
table.dt {
    width: 100%; border-collapse: collapse;
    font-size: 9pt;
}
table.dt th {
    background: #dce4ef; font-weight: bold; color: #1e3a5f;
    border: 1px solid #b0b8c4; padding: 3px 7px; text-align: left;
}
table.dt td {
    border: 1px solid #b0b8c4; padding: 2px 7px;
}
table.dt tr:nth-child(even) td { background: #f7f9fc; }
/* ── Status badges ── */
.ok   { color: #166534; font-weight: bold; }
.fail { color: #dc2626; font-weight: bold; }
.warn { color: #92400e; font-weight: bold; }
/* ── Sketch ── */
.sketch-wrap { border: 1px solid #b0b8c4; margin-bottom: 9px;
               background: #fff; text-align: center; padding: 4px 0; }
/* ── Footer ── */
.footer {
    margin-top: 18px; border-top: 1px solid #b0b8c4;
    padding-top: 5px; font-size: 7.5pt; color: #888;
    text-align: center;
}
.inquiry-banner {
    background: #fff3cd; border: 1.5px solid #d97706;
    color: #92400e; font-weight: bold; font-size: 9pt;
    text-align: center; padding: 4px; margin-bottom: 9px;
}
@media print {
    body { margin: 8mm 10mm 12mm; }
    .no-print { display: none; }
    .sec { page-break-inside: avoid; }
}
"""

# ── Helpers ──────────────────────────────────────────────────────────────────

def _e(s) -> str:
    return _esc.escape(str(s))

def _kv(*pairs, split=46) -> str:
    rows = "".join(
        f'<tr><td class="k">{_e(k)}</td><td class="v">{_e(v)}</td></tr>'
        for k, v in pairs
    )
    return f'<table class="kv">{rows}</table>'

def _panel(title: str, content: str) -> str:
    return f'<div><div class="panel-title">{_e(title)}</div>{content}</div>'

def _sec(letter: str, title: str, content: str) -> str:
    return (
        f'<div class="sec">'
        f'<div class="sec-title">{_e(letter)} — {_e(title)}</div>'
        f'{content}'
        f'</div>'
    )

def _dt(headers: list[str], rows: list[list]) -> str:
    ths = "".join(f"<th>{_e(h)}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{c if c.startswith('<') else _e(c)}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return f'<table class="dt"><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>'

def _status(ok) -> str:
    if ok is True:
        return '<span class="ok">✓ OK</span>'
    if ok is False:
        return '<span class="fail">✗ FAIL</span>'
    return '<span class="warn">— N/A</span>'

# ── SVG Sketch ────────────────────────────────────────────────────────────────

def _sketch_svg(
    Di: float, L_shell: float, h_head: float,
    nozzle_results: list,
    levels_mm: dict,
    nll_mm: float,
    saddle_a_mm: float = 0.0,
) -> str:
    from engines.nozzle_geometry import NOZZLE_OD

    # Canvas: fix width at 860px, height proportional to vessel
    SVG_W = 860
    # Visible range in vessel coords (x: -margin to L+h+margin, y: -margin to Di+margin)
    MX = max(h_head * 1.5, 80.0)   # x margin
    MY = max(Di * 0.45, 70.0)       # y margin above/below vessel
    real_w = L_shell + 2 * h_head + 2 * MX
    real_h = Di + 2 * MY
    SVG_H = max(200, int(SVG_W * real_h / real_w))
    sc = SVG_W / real_w

    # Coordinate helpers: x=0 at left tangent, y=0 at vessel bottom
    def px(xr): return (xr + h_head + MX) * sc
    def py(yr): return (MY + Di - yr) * sc  # SVG y inverts

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" '
        f'style="background:#fafcff;font-family:Arial,sans-serif;">'
    ]

    def line(x1,y1,x2,y2, c="#1e3a5f", w=1.5, dash=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(f'<line x1="{px(x1):.1f}" y1="{py(y1):.1f}" '
                   f'x2="{px(x2):.1f}" y2="{py(y2):.1f}" '
                   f'stroke="{c}" stroke-width="{w}"{d}/>')

    def rect(x,y,w,h, fill="none", stroke="#1e3a5f", sw=1.5):
        out.append(f'<rect x="{px(x):.1f}" y="{py(y+h):.1f}" '
                   f'width="{w*sc:.1f}" height="{h*sc:.1f}" '
                   f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def circle(cx,cy,r, fill="#dce4ef", stroke="#1e3a5f", sw=1.2):
        out.append(f'<circle cx="{px(cx):.1f}" cy="{py(cy):.1f}" r="{r*sc:.1f}" '
                   f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def text(x,y,s, anchor="middle", size=8, color="#1e3a5f", bold=False, dy=0):
        fw = "bold" if bold else "normal"
        out.append(f'<text x="{px(x):.1f}" y="{py(y):.1f}" dy="{dy}" '
                   f'text-anchor="{anchor}" font-size="{size}" '
                   f'font-weight="{fw}" fill="{color}">{_esc.escape(str(s))}</text>')

    # ── Liquid fill at NLL ─────────────────────────────────────────────────
    liq_h = max(0.0, min(Di, nll_mm))
    if liq_h > 0:
        rect(0, 0, L_shell, liq_h, fill="rgba(147,197,253,0.30)", stroke="none", sw=0)

    # ── Vessel shell (filled white background first) ───────────────────────
    rect(0, 0, L_shell, Di, fill="#ffffff", stroke="#1e3a5f", sw=2)

    # ── Heads (simplified as rounded rectangles via arcs) ─────────────────
    if h_head > 0:
        for xoff, mirror in [(-h_head, False), (L_shell, True)]:
            # Draw head as an ellipse half
            rx = h_head * sc
            ry = (Di / 2) * sc
            cx = px(xoff + (0 if not mirror else h_head))
            cy = py(Di / 2)
            sweep = "0" if not mirror else "1"
            # Upper arc
            x1 = px(xoff if not mirror else xoff + h_head)
            x2 = px(xoff + h_head if not mirror else xoff)
            y_top = py(Di);  y_bot = py(0)
            if not mirror:
                out.append(
                    f'<path d="M {x1:.1f} {y_top:.1f} '
                    f'A {rx:.1f} {ry:.1f} 0 0 0 {x1:.1f} {y_bot:.1f}" '
                    f'fill="#ffffff" stroke="#1e3a5f" stroke-width="2"/>'
                )
                out.append(
                    f'<path d="M {x1:.1f} {y_top:.1f} '
                    f'A {rx:.1f} {ry:.1f} 0 0 0 {x1:.1f} {y_bot:.1f}" '
                    f'fill="none" stroke="#1e3a5f" stroke-width="2"/>'
                )
            else:
                out.append(
                    f'<path d="M {px(xoff):.1f} {y_top:.1f} '
                    f'A {rx:.1f} {ry:.1f} 0 0 1 {px(xoff):.1f} {y_bot:.1f}" '
                    f'fill="none" stroke="#1e3a5f" stroke-width="2"/>'
                )
    else:
        # Flat heads: just draw the end lines
        for xv in (0.0, L_shell):
            line(xv, 0, xv, Di, w=2.5)

    # ── Centreline ─────────────────────────────────────────────────────────
    line(-h_head - 20, Di/2, L_shell + h_head + 20, Di/2,
         c="#94a3b8", w=0.8, dash="5,4")

    # ── Tangent lines ──────────────────────────────────────────────────────
    for xv in (0.0, L_shell):
        line(xv, -MY*0.15, xv, Di + MY*0.15, c="#94a3b8", w=0.7, dash="4,3")

    # ── Saddle indicators ──────────────────────────────────────────────────
    if saddle_a_mm > 0:
        sad_h = Di * 0.15
        for sx in (saddle_a_mm, L_shell - saddle_a_mm):
            sw2 = min(Di * 0.12, 150.0)
            rect(sx - sw2, -sad_h, sw2*2, sad_h, fill="#e2e8f0", stroke="#64748b", sw=1)

    # ── NLL line ──────────────────────────────────────────────────────────
    if 0 < liq_h < Di:
        line(0, liq_h, L_shell, liq_h, c="#2563eb", w=1.5, dash="6,3")
        text(L_shell + h_head + 8, liq_h + 3, "NLL", anchor="start",
             size=7, color="#2563eb", bold=True)

    # ── Other level lines ─────────────────────────────────────────────────
    _lc = {"LZLL":"#4b5563","LALL":"#dc2626","LAL":"#f97316",
           "LAH":"#f97316","LAHH":"#dc2626","LZHH":"#4b5563"}
    for tag, h_mm in sorted(levels_mm.items(), key=lambda kv: kv[1]):
        if tag == "NLL":
            continue
        hc = max(0.0, min(Di, h_mm))
        if 0 < hc < Di:
            lc = _lc.get(tag, "#64748b")
            line(0, hc, L_shell, hc, c=lc, w=0.8, dash="4,3")
            text(L_shell + h_head + 8, hc + 3, tag, anchor="start",
                 size=6.5, color=lc)

    # ── Nozzles ────────────────────────────────────────────────────────────
    _svc_colors = {
        "Inlet": "#0891b2", "Gas outlet": "#059669", "Liquid outlet": "#2563eb",
        "PSV": "#dc2626", "Manway": "#7c3aed",
    }
    for nz, nres, rres, _fok, _pat in nozzle_results:
        dn  = nz["dn"]
        loc = nz["loc"]
        svc = nz.get("service", "")
        nc  = _svc_colors.get(svc, "#475569")
        OD  = NOZZLE_OD.get(dn, dn * 1.05)
        disp_r = min(OD/2, Di * 0.05, 28.0)
        stub   = max(disp_r * 1.4, 20.0)

        if loc == "Left head" and nres is not None:
            ny = Di - nres.d_from_top_mm
            line(-h_head - stub, ny, -h_head, ny, c=nc, w=1.5)
            circle(-h_head - stub, ny, disp_r, fill="#dbeafe", stroke=nc, sw=1.5)
            text(-h_head - stub - disp_r - 3, ny + 2, nz["tag"],
                 anchor="end", size=7, color=nc, bold=True)

        elif loc == "Right head" and nres is not None:
            ny = Di - nres.d_from_top_mm
            line(L_shell + h_head, ny, L_shell + h_head + stub, ny, c=nc, w=1.5)
            circle(L_shell + h_head + stub, ny, disp_r, fill="#dbeafe", stroke=nc, sw=1.5)
            text(L_shell + h_head + stub + disp_r + 3, ny + 2, nz["tag"],
                 anchor="start", size=7, color=nc, bold=True)

        elif loc == "Shell — top":
            nx = nz["axial_mm"]
            line(nx, Di, nx, Di + stub, c=nc, w=1.5)
            circle(nx, Di + stub, disp_r, fill="#dbeafe", stroke=nc, sw=1.5)
            text(nx, Di + stub + disp_r + 10, nz["tag"],
                 anchor="middle", size=7, color=nc, bold=True)

        elif loc == "Shell — bottom":
            nx = nz["axial_mm"]
            line(nx, 0, nx, -stub, c=nc, w=1.5)
            circle(nx, -stub, disp_r, fill="#dbeafe", stroke=nc, sw=1.5)
            text(nx, -stub - disp_r - 4, nz["tag"],
                 anchor="middle", size=7, color=nc, bold=True)

        else:  # Shell side — small circle on centreline
            nx = nz["axial_mm"]
            cr = min(OD/2 * 0.6, 15.0)
            circle(nx, Di/2, cr, fill="#dbeafe", stroke=nc, sw=1.2)
            text(nx, Di/2 + cr + 9, nz["tag"],
                 anchor="middle", size=6.5, color=nc)

    # ── Dimension: T-T ────────────────────────────────────────────────────
    y_dim = -MY * 0.55
    line(0, y_dim, L_shell, y_dim, c="#475569", w=1.0)
    for xv in (0.0, L_shell):
        line(xv, y_dim - 5, xv, y_dim + 5, c="#475569", w=1.0)
    text(L_shell/2, y_dim - 10, f"T–T = {L_shell:,.0f} mm",
         anchor="middle", size=8, color="#475569", bold=True)

    # ── Dimension: Di arrow ───────────────────────────────────────────────
    xar = L_shell + h_head + MX * 0.55
    line(xar, 0, xar, Di, c="#475569", w=1.0)
    for yv in (0.0, Di):
        line(xar-5, yv, xar+5, yv, c="#475569", w=1.0)
    text(xar + 7, Di/2, f"Di = {Di:.0f} mm", anchor="start", size=8, color="#475569")

    out.append("</svg>")
    return "\n".join(out)


# ── Main report function ──────────────────────────────────────────────────────

def generate_datasheet_html(
    project_name: str,
    vessel_tag: str,
    issued_for: str,
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
    nozzle_results: list,
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
    n_inlets: int = 1,
) -> str:
    from engines.nozzle_geometry import NOZZLE_OD, NOZZLE_WALL_T, NOZZLE_WALL_SCH, recommended_schedule
    import math as _m

    today     = _date.today().strftime("%d %b %Y")
    nll_mm    = levels_mm.get("NLL",  Di * 0.5)
    lahh_mm   = levels_mm.get("LAHH", Di * 0.85)
    code_full = "EN 13445-3:2021" if code_key == "EN" else "ASME VIII Div.1"
    pn_label  = "PN" if code_key == "EN" else "Class"
    hydro_factor = 1.25 if code_key == "EN" else 1.43
    hydro_P   = P_barg * hydro_factor

    # ── HEADER ───────────────────────────────────────────────────────────────
    proj_line = f"Project: {project_name}" if project_name else ""
    header_html = f"""
<div class="ds-header">
  <div class="ds-header-left">
    <div class="ds-title">Horizontal Two-Phase Separator</div>
    <div class="ds-sub">
      <b>Tag:</b> {_e(vessel_tag)} &nbsp;|&nbsp;
      <b>Service:</b> {_e(gas_fluid)} / {_e(liq_fluid)} &nbsp;|&nbsp;
      <b>Code:</b> {_e(code_full)} / API 12J
    </div>
    <div class="ds-meta">{_e(proj_line)}</div>
  </div>
  <div class="ds-header-right">
    <table class="rev-table">
      <tr><th>Rev</th><th>Date</th><th>Description</th><th>By</th></tr>
      <tr><td>A</td><td>{_e(today)}</td><td>Issued for {_e(issued_for)}</td><td>—</td></tr>
    </table>
    <div class="issued-stamp" style="margin-top:4px">
      ISSUED FOR {_e(issued_for.upper())}
    </div>
  </div>
</div>"""

    # ── INQUIRY BANNER ────────────────────────────────────────────────────────
    banner = ""
    if issued_for in ("Inquiry", "HAZOP review"):
        banner = (
            '<div class="inquiry-banner">'
            '⚠  THIS DOCUMENT IS ISSUED FOR INQUIRY ONLY — NOT FOR CONSTRUCTION  ⚠'
            '</div>'
        )

    # ── SKETCH ────────────────────────────────────────────────────────────────
    sketch_svg = _sketch_svg(
        Di, L_shell, h_head,
        nozzle_results, levels_mm, nll_mm, saddle_a_mm,
    )
    sketch_html = (
        f'<div class="sketch-wrap">{sketch_svg}'
        f'<div style="font-size:7.5pt;color:#888;padding:2px 0">'
        f'Schematic only — not to scale. Nozzle positions are axial centrelines.</div>'
        f'</div>'
    )

    # ── A  DESIGN CONDITIONS ──────────────────────────────────────────────────
    sec_a = _sec("A", "Design Conditions", _kv(
        ("Equipment type",          "Horizontal two-phase separator"),
        ("Orientation",             "Horizontal"),
        ("Design code",             code_full),
        ("Separator standard",      "API 12J"),
        ("Design pressure",         f"{P_barg:.2f}  barg"),
        ("Design temperature",      f"{T_C:.0f}  °C"),
        ("Hydrostatic test pressure", f"{hydro_P:.2f}  barg  ({hydro_factor:.2f} × DP, {code_full})"),
        ("Operating pressure",      "See process conditions"),
        ("Operating temperature",   "See process conditions"),
        ("Corrosion allowance",     "See mechanical design section"),
        ("Fluid service",           "Two-phase gas / liquid — non-fouling"),
    ))

    # ── B  PROCESS FLUIDS ─────────────────────────────────────────────────────
    gas_kv = _kv(
        ("Fluid",                   gas_fluid),
        ("Molecular weight",        f"{gas_props.MW:.2f}  g/mol"),
        ("Density (op. cond.)",     f"{gas_props.rho_kgm3:.3f}  kg/m³"),
        ("Viscosity",               f"{gas_props.mu_Pas*1e6:.1f}  μPa·s"),
        ("Compressibility Z",       f"{getattr(gas_props, 'Z', 1.0):.3f}" if hasattr(gas_props, "Z") else "—"),
        ("Flow rate",               f"{Q_gas_m3h:,.1f}  m³/h  (actual)"),
        ("Mass flow rate",          f"{Q_gas_m3h * gas_props.rho_kgm3:,.0f}  kg/h"),
    )
    liq_kv = _kv(
        ("Fluid",                   liq_fluid),
        ("Density (op. cond.)",     f"{liq_props.rho_kgm3:.0f}  kg/m³"),
        ("Viscosity",               f"{liq_props.mu_Pas*1e3:.3f}  mPa·s"),
        ("Flow rate",               f"{Q_liq_m3h:,.2f}  m³/h"),
        ("Mass flow rate",          f"{Q_liq_m3h * liq_props.rho_kgm3:,.0f}  kg/h"),
    )
    # Inlet summary
    rho_mix = (gas_props.rho_kgm3 * Q_gas_m3h + liq_props.rho_kgm3 * Q_liq_m3h) \
              / max(Q_gas_m3h + Q_liq_m3h, 1e-9)
    inlet_nz = [nz for nz, *_ in nozzle_results if nz.get("service") == "Inlet"]
    if inlet_nz:
        nz0   = inlet_nz[0]
        OD0   = NOZZLE_OD.get(nz0["dn"], nz0["dn"] * 1.05)
        rec0  = recommended_schedule(nz0.get("pn", 25), code_key)
        t0    = float(NOZZLE_WALL_SCH[rec0].get(nz0["dn"], NOZZLE_WALL_T.get(nz0["dn"], 8.0)))
        ID0   = max(OD0 - 2 * t0, 1.0)
        A_nz  = _m.pi * (ID0 * 1e-3) ** 2 / 4.0
        Q_mix_per = (Q_gas_m3h + Q_liq_m3h) / n_inlets / 3600.0
        v_in  = Q_mix_per / max(A_nz, 1e-9)
        rv2   = rho_mix * v_in ** 2
        rv2_ok = rv2 <= 2400.0
        inlet_summary_kv = _kv(
            ("Number of inlet nozzles",     str(n_inlets)),
            ("Gas flow per inlet",           f"{Q_gas_m3h/n_inlets:,.1f}  m³/h  +  "
                                             f"{Q_liq_m3h/n_inlets:,.2f}  m³/h liquid"),
            ("Mixture density",             f"{rho_mix:.1f}  kg/m³"),
            ("Inlet velocity (per nozzle)", f"{v_in:.2f}  m/s  (DN{nz0['dn']}, bore {ID0:.0f} mm)"),
            ("Inlet momentum  ρv²",         f"{rv2:,.0f}  Pa  (limit 2 400 Pa — API RP 14E)  "
                                            + ("✓" if rv2_ok else "✗")),
        )
    else:
        inlet_summary_kv = _kv(("Inlet nozzles", "None configured"))

    panels_b = (
        f'<div class="two-panel">'
        f'{_panel("Gas Phase", gas_kv)}'
        f'{_panel("Liquid Phase", liq_kv)}'
        f'</div>'
        f'<div style="margin-bottom:4px">'
        f'<div class="panel-title">Inlet Conditions (two-phase, split equally between {n_inlets} nozzle{"s" if n_inlets>1 else ""})</div>'
        f'{inlet_summary_kv}'
        f'</div>'
    )
    sec_b = _sec("B", "Process Fluids", panels_b)

    # ── C  MECHANICAL DESIGN ──────────────────────────────────────────────────
    from engines import MATERIALS
    mat  = MATERIALS.get(mat_key, {})
    mat_name = mat.get("name", mat_key)
    CA_mm = getattr(shell_res, "CA_mm", 3.0)  # fall back if not on result

    sec_c = _sec("C", "Mechanical Design", _kv(
        ("Inner diameter  Di",           f"{Di:,.0f}  mm"),
        ("Shell length  T–T",            f"{L_shell:,.0f}  mm"),
        ("Overall length  P–P",          f"{L_shell + 2*h_head:,.0f}  mm"),
        ("Head type",                    head_type_label),
        ("Head depth  h",                f"{h_head:.0f}  mm"),
        ("Shell thickness — calculated", f"{shell_res.t_calc_mm:.2f}  mm"),
        ("Shell thickness — nominal",    f"{shell_res.t_nom_mm:.1f}  mm"),
        ("Head thickness — calculated",  f"{head_res.t_calc_mm:.2f}  mm"),
        ("Head thickness — nominal",     f"{head_res.t_nom_mm:.1f}  mm"),
        ("Material (shell & heads)",     mat_name),
        ("Allowable stress  fd",         f"{fd_MPa:.1f}  MPa  at {T_C:.0f} °C"),
        ("Corrosion allowance  CA",      f"see input"),
        ("Weld joint efficiency  z",     "1.0  (full radiography)"),
        ("Support type",                 "Saddle supports — 2 off"),
        ("Saddle position from tangent", f"{saddle_a_mm:.0f}  mm" if saddle_a_mm > 0 else "TBD"),
        ("Saddle width",                 f"{saddle_w_mm:.0f}  mm"),
        ("Weight — empty",               "TBD (vendor)"),
        ("Weight — operating",           "TBD (vendor)"),
        ("Weight — hydro test",          "TBD (vendor)"),
    ))

    # ── D  SEPARATOR SIZING ───────────────────────────────────────────────────
    import math as _math

    delta_rho = max(0.0, liq_props.rho_kgm3 - gas_props.rho_kgm3)
    U_pad_max, A_pad_req, A_pad_avail, pad_load = None, None, None, None
    if has_meshpad:
        U_pad_max  = K_sb * _math.sqrt(delta_rho / max(gas_props.rho_kgm3, 0.001))
        A_pad_req  = (Q_gas_m3h / 3600.0) / max(U_pad_max, 1e-9)
        A_pad_avail = sep_res.A_gas_m2
        pad_load   = A_pad_req / max(A_pad_avail, 1e-9) * 100

    def _row(criterion, actual, limit, ok):
        return [criterion, actual, limit, _status(ok)]

    sizing_rows = [
        _row("Slenderness  L/D  (T–T / Di)  [API 12J: 3–5]",
             f"{sep_res.LD_ratio:.2f}",
             "3.0 – 5.0",
             3.0 <= sep_res.LD_ratio <= 5.0),
        _row(f"Gas velocity — body per inlet zone  [K = {K_sb:.2f} m/s]",
             f"{sep_res.U_act_ms:.3f}  m/s",
             f"≤ {sep_res.U_max_ms:.3f}  m/s",
             sep_res.gas_velocity_ok),
    ]
    if has_meshpad and pad_load is not None:
        sizing_rows.append(_row(
            "Mesh pad load (full Q_gas, at outlet)  [K_pad = {:.2f} m/s]".format(K_sb),
            f"{pad_load:.0f} %  (req. {A_pad_req:.3f} m²  /  avail. {A_pad_avail:.3f} m²)",
            "≤ 100 %",
            A_pad_req <= A_pad_avail,
        ))
    sizing_rows += [
        _row("Liquid hold-up time at NLL",
             f"{sep_res.t_holdup_s/60:.1f}  min",
             f"≥ {sep_res.t_holdup_s/60/sep_res.t_holdup_s*sep_res.t_holdup_s/60:.1f} min  (req.)",
             sep_res.holdup_ok),
        _row("Surge time  NLL → LAHH",
             f"{sep_res.t_surge_s/60:.1f}  min",
             f"≥ req.",
             sep_res.surge_ok),
        _row("NLL fill fraction  (NLL / Di)  [target ~50 %]",
             f"{sep_res.nll_frac*100:.0f}  %",
             "40 – 60 %",
             0.35 <= sep_res.nll_frac <= 0.65),
    ]
    if inlet_nz:
        rv2_val = rho_mix * v_in ** 2
        sizing_rows.append(_row(
            f"Inlet nozzle momentum  ρv²  (DN{nz0['dn']})  [API RP 14E]",
            f"{rv2_val:,.0f}  Pa",
            "≤ 2 400  Pa",
            rv2_val <= 2400.0,
        ))
    sizing_rows += [
        _row("Liquid droplet cut size — gas phase  (drag-corrected Stokes)",
             f"{sep_res.d_cut_gas_um:.0f}  μm",
             "informational",
             None),
        _row("Gas bubble cut size — liquid phase  (drag-corrected Stokes)",
             f"{sep_res.d_cut_liq_um:.0f}  μm",
             "informational",
             None),
    ]

    # Fix the hold-up row (re-compute req properly)
    for i, row in enumerate(sizing_rows):
        if "Hold-up" in row[0]:
            sizing_rows[i] = _row(
                "Liquid hold-up time at NLL",
                f"{sep_res.t_holdup_s/60:.1f}  min",
                f"≥ required",
                sep_res.holdup_ok,
            )

    sec_d = _sec("D", "Separator Sizing  (API 12J screening)",
                 _dt(["Criterion", "Actual", "Limit", "Status"], sizing_rows))

    # ── E  LIQUID LEVELS ──────────────────────────────────────────────────────
    _desc = {
        "LZLL": "Low-low liquid level — low-low shutdown",
        "LALL": "Low-alarm liquid level",
        "LAL":  "Low liquid level — operating lower bound",
        "NLL":  "Normal liquid level — design basis",
        "LAH":  "High liquid level — operating upper bound",
        "LAHH": "High-high liquid level — high-high shutdown / surge basis",
        "LZHH": "High-high-high liquid level — overfill / trip",
    }
    _order = ["LZLL", "LALL", "LAL", "NLL", "LAH", "LAHH", "LZHH"]

    # Full vessel volume for % calculation
    V_total = sep_res.V_total_vessel_m3 if sep_res.V_total_vessel_m3 > 0 else 1.0

    # Compute volumes for each level using the cylindrical approximation
    # (heads are included via V_total from the engine's passed value)
    from engines.separator_process import _cyl_vol_mm3
    level_rows = []
    for tag in _order:
        if tag not in levels_mm:
            continue
        h = max(0.0, min(Di, levels_mm[tag]))
        vol_cyl = _cyl_vol_mm3(Di, L_shell, h) * 1e-9  # m³ cylindrical only
        vol_pct = vol_cyl / max(V_total, 1e-9) * 100
        level_rows.append([
            f"<b>{tag}</b>",
            _desc.get(tag, ""),
            f"{h:.0f}",
            f"{h/Di*100:.0f} %",
            f"{vol_cyl:.3f}",
            f"{vol_cyl*1000:.0f}",
        ])

    sec_e = _sec("E", "Liquid Levels",
                 _dt(
                     ["Tag", "Description", "Height from bottom  (mm)",
                      "% Di", "Vol – cyl. zone  (m³)", "Vol  (L)"],
                     level_rows,
                 ))

    # ── F  INTERNALS ──────────────────────────────────────────────────────────
    internals_rows = [
        ["Inlet device",
         f"Half-pipe distributor — fitted at each inlet nozzle" if has_inlet_dev else "None",
         str(n_inlets) if has_inlet_dev else "—",
         "Deflects two-phase flow downward; reduces jetting and liquid surface turbulence"],
        ["Inlet baffles / distribution plates",
         (f"Perforated plate, {baffle_open_pct:.0f} % open, "
          f"setback {L_baffle_mm:.0f} mm from each tangent") if has_baffles else "None",
         "2" if has_baffles else "—",
         "Provides uniform flow distribution; effective separation length "
         f"= {max(0.0, L_shell - 2*L_baffle_mm):.0f} mm"],
        ["Gas demister",
         f"Knitted wire mesh pad, K_pad = {K_sb:.2f} m/s" if has_meshpad else "None",
         "1" if has_meshpad else "—",
         "Located upstream of gas outlet; removes entrained liquid droplets"],
        ["Vortex breaker",
         "Cross-plate vortex breaker" if has_vortex_brk else "None",
         "1" if has_vortex_brk else "—",
         "Fitted at liquid outlet nozzle; prevents gas entrainment at low liquid levels"],
    ]
    sec_f = _sec("F", "Internals",
                 _dt(["Component", "Description", "Qty", "Function / Notes"], internals_rows))

    # ── G  NOZZLE SCHEDULE ────────────────────────────────────────────────────
    lzhh_mm = levels_mm.get("LZHH", 0.0)
    nz_rows = []
    for nz, nres, rres, fok, pat in nozzle_results:
        dn  = nz["dn"]
        OD  = NOZZLE_OD.get(dn, dn * 1.05)
        rec = recommended_schedule(nz.get("pn", 25), code_key)
        t   = float(NOZZLE_WALL_SCH[rec].get(dn, NOZZLE_WALL_T.get(dn, 8.0)))
        # Status: combine geometry + code + reinf + flange
        geom_ok  = nres.geom_ok if nres else True
        reinf_ok = rres.adequate if rres else True
        all_ok   = geom_ok and fok and (reinf_ok is not False)
        status_s = _status(all_ok)

        notes = ""
        if nres is not None and nz.get("service") == "Inlet":
            nz_IR  = (OD - 2*t) / 2.0
            nz_bot = (Di - nres.d_from_top_mm) - nz_IR
            dist   = lzhh_mm - nz_bot
            notes  = f"Inlet bottom {'submerged' if dist > 0 else 'clear'} at LZHH ({dist:+.0f} mm)"

        nz_rows.append([
            f"<b>{nz['tag']}</b>",
            "1",
            nz["service"],
            nz["loc"],
            f"DN{dn}",
            f"{pn_label} {nz.get('pn','')}",
            f"{OD:.1f}",
            f"{t:.1f}",
            rec,
            "RF",
            status_s + (f"  {notes}" if notes else ""),
        ])

    sec_g = _sec("G", "Nozzle Schedule",
                 _dt(
                     ["Tag", "Qty", "Service", "Location",
                      "DN", pn_label, "OD (mm)", "Wall (mm)", "Sched.",
                      "Facing", "Check / Notes"],
                     nz_rows,
                 ))

    # ── H  NOTES & ENGINEERING FINDINGS ──────────────────────────────────────
    all_findings = []
    for w in head_warnings + shell_warnings:
        all_findings.append(("warning", "", w))
    for chk in placement_checks:
        tags = f"[{', '.join(chk.tags)}] " if chk.tags else ""
        all_findings.append((chk.level, tags, chk.headline))

    if all_findings:
        finding_html = ""
        for level, tags, msg in all_findings:
            icon  = {"error": "🚫", "warning": "⚠️", "info": "ℹ️"}.get(level, "⚠️")
            color = {"error": "#dc2626", "warning": "#92400e", "info": "#1e40af"}.get(level, "#555")
            finding_html += (
                f'<div style="padding:3px 7px;margin:2px 0;border-left:3px solid {color};">'
                f'{icon} <b style="color:{color}">{_e(tags)}</b>{_e(msg)}</div>'
            )
    else:
        finding_html = '<div style="color:#166534;padding:4px 7px">✓ No engineering issues detected.</div>'

    notes_list = [
        "All dimensions in millimetres unless otherwise stated.",
        f"Design code: {code_full}. Separator sizing standard: API 12J.",
        f"Hydrostatic test pressure: {hydro_P:.2f} barg ({hydro_factor:.2f} × design pressure).",
        "Vessel weight (empty / operating / hydro test) to be confirmed by fabricator.",
        "Nozzle schedule is indicative for inquiry; final schedule to be confirmed by process engineer.",
        "Separator sizing calculations are screening-level per API 12J. Final design to be confirmed by a qualified engineer.",
    ]
    notes_html = "".join(f'<div style="padding:1px 7px">{i+1}. {_e(n)}</div>'
                         for i, n in enumerate(notes_list))

    sec_h = _sec("H", "Notes & Engineering Findings",
                 f'<div style="margin-bottom:6px"><b>Engineering Findings:</b></div>'
                 f'{finding_html}'
                 f'<div style="margin:6px 0 3px"><b>General Notes:</b></div>'
                 f'{notes_html}')

    # ── FOOTER ────────────────────────────────────────────────────────────────
    footer = (
        f'<div class="footer">'
        f'Generated by <b>VesselCalc</b> · {_e(today)} · Rev A · Issued for {_e(issued_for)}<br>'
        f'THIS DOCUMENT IS FOR {_e(issued_for.upper())} PURPOSES ONLY — NOT FOR CONSTRUCTION'
        f'</div>'
    )

    body = (
        header_html + banner + sketch_html
        + sec_a + sec_b + sec_c + sec_d
        + sec_e + sec_f + sec_g + sec_h
        + footer
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Datasheet — {_e(vessel_tag)}</title>
<style>{_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""
