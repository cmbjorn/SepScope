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
/* ── Sub-section title ── */
.sub-sec {
    background: #2d5f8a; color: #fff;
    font-weight: bold; font-size: 9pt;
    padding: 2px 8px; margin: 7px 0 0;
    letter-spacing: 0.02em;
}
/* ── Side-by-side head drawings ── */
.head-pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 8px;
}
.head-wrap {
    border: 1px solid #b0b8c4;
    background: #fff;
    text-align: center;
    padding: 3px;
}
/* ── Per-nozzle endcap detail blocks ── */
.nz-block {
    border: 1px solid #dce4ef;
    border-radius: 3px;
    margin: 7px 0;
    page-break-inside: avoid;
}
.nz-block-hdr {
    background: #f4f6fa;
    border-bottom: 1px solid #dce4ef;
    font-weight: bold;
    font-size: 9pt;
    color: #1e3a5f;
    padding: 3px 8px;
}
/* ── Implication boxes ── */
.impl-err  { background:#fee2e2; border-left:3px solid #dc2626; padding:4px 8px; margin:3px 0; font-size:8.5pt; }
.impl-warn { background:#fef3c7; border-left:3px solid #d97706; padding:4px 8px; margin:3px 0; font-size:8.5pt; }
.impl-info { background:#eff6ff; border-left:3px solid #2563eb; padding:4px 8px; margin:3px 0; font-size:8.5pt; }
/* ── Compact metric row ── */
.metrics { display:flex; gap:12px; flex-wrap:wrap; padding:5px 8px; }
.metric  { font-size:8.5pt; }
.metric b { color:#1e3a5f; }
/* ── Print ── */
@media print {
    @page { size: A4 portrait; margin: 12mm 14mm 14mm; }
    body { margin: 0; }
    .no-print { display: none; }
    .sec, .nz-block { page-break-inside: avoid; }
    .pb { page-break-before: always; }
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

# ── Endcap face-on SVG ───────────────────────────────────────────────────────

def _endcap_face_svg(
    head_type,
    Di: float,
    R_c: float,
    r_k: float,
    b: float,
    t_head_nom: float,
    nozzle_data: list,   # list of (nz_dict, nres)
    title: str = "",
    size: int = 320,
) -> str:
    """
    SVG of one endcap viewed face-on (looking axially inward).
    Zones filled, weld-exclusion ring shown, each endcap nozzle drawn
    as a circle at its vertical position (all on x = 0 centre plane).
    """
    from engines.head_geometry import HeadType, _FD_CROWN_RATIO, _FD_KNUCKLE_RATIO
    from engines.nozzle_geometry import _tori_geometry as _tg

    R   = Di / 2.0
    sc  = (size / 2 * 0.80) / R     # mm → px; R maps to 80 % of half-canvas
    cx  = cy = size / 2.0
    min_weld = max(3.0 * t_head_nom, 25.0)

    def _px(mm):  return mm * sc

    def _circ(r_mm, fill, stroke="none", sw=1.5, dash=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{_px(r_mm):.2f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def _annulus(ro_mm, ri_mm, fill):
        ro, ri = _px(ro_mm), _px(ri_mm)
        d = (f"M{cx+ro:.2f},{cy:.2f} A{ro:.2f},{ro:.2f} 0 1 0 {cx-ro:.2f},{cy:.2f} "
             f"A{ro:.2f},{ro:.2f} 0 1 0 {cx+ro:.2f},{cy:.2f} "
             f"M{cx+ri:.2f},{cy:.2f} A{ri:.2f},{ri:.2f} 0 1 1 {cx-ri:.2f},{cy:.2f} "
             f"A{ri:.2f},{ri:.2f} 0 1 1 {cx+ri:.2f},{cy:.2f}")
        return f'<path d="{d}" fill="{fill}" fill-rule="evenodd"/>'

    def _txt(x, y, s, anchor="middle", size_pt=8, color="#64748b", bold=False):
        fw = "bold" if bold else "normal"
        return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
                f'font-size="{size_pt}" font-weight="{fw}" fill="{color}" '
                f'font-family="Arial,sans-serif">{_e(s)}</text>')

    h_total = size + (18 if title else 0)
    yoff    = 18 if title else 0

    p: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{h_total}" '
        f'style="background:white;overflow:visible;">'
    ]
    if title:
        p.append(_txt(size / 2, 13, title, size_pt=9.5, color="#1e3a5f", bold=True))

    p.append(f'<g transform="translate(0,{yoff})">')

    # Normalise F&D
    _ht, _Rc, _rk = head_type, R_c, r_k
    if _ht == HeadType.FLANGED_DISHED:
        _ht, _Rc, _rk = HeadType.TORISPHERICAL, _FD_CROWN_RATIO * Di, _FD_KNUCKLE_RATIO * Di

    # ── Zone fills ────────────────────────────────────────────────────────────
    if _ht == HeadType.TORISPHERICAL:
        tg    = _tg(Di, _Rc, _rk)
        r_cj  = tg["r_cj"]
        p.append(_circ(R,    "rgba(245,158,11,0.22)"))
        p.append(_circ(r_cj, "rgba(34,197,94,0.28)"))
        p.append(_circ(r_cj, "none", "#16a34a", 1.5, "5,3"))
        p.append(_txt(cx, cy + 4, "Crown", color="#15803d"))
        kx = cx + _px((r_cj + R) * 0.52)
        p.append(_txt(kx, cy - _px((r_cj + R) * 0.18), "Knuckle", size_pt=7.5, color="#b45309"))
        p.append(_txt(cx + _px(r_cj) + 3, cy - 4,
                      f"r_cj = {r_cj:.0f} mm", anchor="start", size_pt=7, color="#15803d"))

    elif _ht == HeadType.ELLIPSOIDAL:
        _k    = max(Di / (2.0 * b), 1.001)
        r_rev = R / math.sqrt(_k * _k - 1.0)
        p.append(_circ(R,     "rgba(245,158,11,0.22)"))
        p.append(_circ(r_rev, "rgba(34,197,94,0.28)"))
        p.append(_circ(r_rev, "none", "#16a34a", 1.5, "5,3"))
        p.append(_txt(cx, cy + 4, "Tensile zone", color="#15803d"))
        p.append(_txt(cx + _px(r_rev) + 3, cy - 4,
                      f"r_rev = {r_rev:.0f} mm", anchor="start", size_pt=7, color="#15803d"))

    elif _ht == HeadType.HEMISPHERICAL:
        p.append(_circ(R, "rgba(34,197,94,0.22)"))
        p.append(_txt(cx, cy + 4, "Full face — no knuckle", color="#15803d", size_pt=7.5))

    else:
        p.append(_circ(R, "rgba(34,197,94,0.18)"))
        p.append(_txt(cx, cy + 4, "Full face usable", color="#15803d", size_pt=7.5))

    # ── Weld-exclusion ring ───────────────────────────────────────────────────
    r_excl = R - min_weld
    if r_excl > 5:
        p.append(_annulus(R, r_excl, "rgba(220,38,38,0.10)"))
        p.append(_circ(r_excl, "none", "#dc2626", 0.9, "4,2"))
        # label
        ang = math.radians(42)
        lx  = cx + _px(r_excl + min_weld * 0.5) * math.cos(ang)
        ly  = cy - _px(r_excl + min_weld * 0.5) * math.sin(ang)
        p.append(_txt(lx, ly, f"Weld excl. ≥{min_weld:.0f}", size_pt=6.5, color="#dc2626"))

    # ── Inner wall ────────────────────────────────────────────────────────────
    p.append(_circ(R, "none", "#1d4ed8", 2.5))
    p.append(_txt(cx, cy - _px(R) + 9, f"Di = {Di:.0f} mm", size_pt=7.5, color="#475569"))

    # ── Axis cross ────────────────────────────────────────────────────────────
    dc = _px(R) * 0.055
    p.append(f'<line x1="{cx-dc:.1f}" y1="{cy:.1f}" x2="{cx+dc:.1f}" y2="{cy:.1f}" '
             f'stroke="#94a3b8" stroke-width="0.8"/>')
    p.append(f'<line x1="{cx:.1f}" y1="{cy-dc:.1f}" x2="{cx:.1f}" y2="{cy+dc:.1f}" '
             f'stroke="#94a3b8" stroke-width="0.8"/>')

    # ── Nozzles ───────────────────────────────────────────────────────────────
    _NSTROKE = {"ok": "#16a34a", "warn": "#d97706", "fail": "#dc2626"}
    _NFILL   = {
        "ok":   "rgba(34,197,94,0.20)",
        "warn": "rgba(245,158,11,0.22)",
        "fail": "rgba(220,38,38,0.20)",
    }
    for nz, nres in nozzle_data:
        if not nres.geom_ok or nres.code_ok is False:  ck = "fail"
        elif nres.zone == "knuckle" or nres.code_ok is None: ck = "warn"
        else: ck = "ok"
        nc, nf = _NSTROKE[ck], _NFILL[ck]

        ny_px  = cy - nres.y_nozzle_mm * sc   # SVG y inverted
        nOR_px = _px(nres.nozzle_OR_mm)
        bOR_px = _px(max(nres.nozzle_OD_mm - 2 * nres.nozzle_t_mm, 1.0) / 2.0)

        p.append(f'<circle cx="{cx:.1f}" cy="{ny_px:.1f}" r="{nOR_px:.2f}" '
                 f'fill="{nf}" stroke="{nc}" stroke-width="2"/>')
        p.append(f'<circle cx="{cx:.1f}" cy="{ny_px:.1f}" r="{bOR_px:.2f}" '
                 f'fill="none" stroke="{nc}" stroke-width="0.9" stroke-dasharray="3,2"/>')
        # tag label — place above OD circle
        lbl_y = ny_px - nOR_px - 3
        p.append(f'<text x="{cx:.1f}" y="{lbl_y:.1f}" text-anchor="middle" '
                 f'font-size="8.5" font-weight="bold" fill="{nc}" '
                 f'font-family="Arial,sans-serif">{_e(nz["tag"])}</text>')

    p.append('</g>')

    # ── Bottom legend ─────────────────────────────────────────────────────────
    items = [
        ("rgba(34,197,94,0.5)",    "Crown / full-face (std. analysis)"),
        ("rgba(245,158,11,0.5)",   "Knuckle / compressive zone"),
        ("rgba(220,38,38,0.15)",   "Weld-exclusion ring"),
    ]
    lx0 = 4
    ly0 = h_total - 3 - len(items) * 11
    for col, lbl in items:
        p.append(f'<rect x="{lx0}" y="{ly0-7:.1f}" width="9" height="8" '
                 f'fill="{col}" rx="1"/>')
        p.append(f'<text x="{lx0+13}" y="{ly0:.1f}" font-size="7" fill="#64748b" '
                 f'font-family="Arial,sans-serif">{_e(lbl)}</text>')
        ly0 += 11

    p.append('</svg>')
    return '\n'.join(p)


# ── Endcap nozzle analysis section ───────────────────────────────────────────

_ENDCAP_ALT_HEADS = [
    ("Hemispherical",             "Hemispherical",                  {}),
    ("Ellipsoidal 2:1",           "Ellipsoidal 2:1",                {"ellipse_ratio": 2.0}),
    ("Tori — Klöpper (r=0.10Di)","Torispherical (dished)",          {"crown_ratio": 1.0, "knuckle_ratio": 0.10}),
    ("F&D ASME (r=0.06Di)",      "Flanged & Dished (ASME F&D)",    {}),
    ("Conical 30°",               "Conical",                        {"alpha_deg_cone": 30.0}),
    ("Flat",                      "Flat (unstayed)",                {}),
]


def _endcap_analysis_html(
    nozzle_results: list,
    Di: float,
    head_type,
    crown_ratio: float,
    knuckle_ratio: float,
    alpha_deg_cone: float,
    ellipse_ratio: float,
    t_head_nom: float,
    code_key: str,
    h_head: float = 0.0,
    lzhh_mm: float = 0.0,
) -> str:
    """
    Full endcap analysis section: face-on SVG drawings, summary table,
    and per-nozzle detail with alternative head type comparison.
    Returns an HTML string (one complete <div class="sec"> block).
    """
    from engines.head_geometry import HeadType, _FD_CROWN_RATIO, _FD_KNUCKLE_RATIO
    from engines.nozzle_geometry import nozzle_on_head, NOZZLE_OD, NOZZLE_WALL_T

    code = "EN 13445-3" if code_key == "EN" else "ASME VIII Div.1"
    R    = Di / 2.0
    min_weld = max(3.0 * t_head_nom, 25.0)

    R_c = crown_ratio * Di
    r_k = knuckle_ratio * Di
    b   = Di / (2.0 * ellipse_ratio)

    # Filter to endcap nozzles only (loc = "Left head" or "Right head")
    head_nz = [(nz, nres, rres) for nz, nres, rres, *_ in nozzle_results
               if nres is not None and nz.get("loc") in ("Left head", "Right head")]
    if not head_nz:
        return ""

    left_nz  = [(nz, nres) for nz, nres, _ in head_nz if nz["loc"] == "Left head"]
    right_nz = [(nz, nres) for nz, nres, _ in head_nz if nz["loc"] == "Right head"]

    html: list[str] = ['<div class="sec pb">',
                       '<div class="sec-title">G.1 — Endcap Nozzle Analysis</div>']

    # ── Face-on drawings ──────────────────────────────────────────────────────
    if left_nz or right_nz:
        html.append('<div class="head-pair">')
        for side_data, side_title in ((left_nz, "Left head — face-on view"),
                                      (right_nz, "Right head — face-on view")):
            svg_str = _endcap_face_svg(
                head_type, Di, R_c, r_k, b, t_head_nom,
                side_data, title=side_title, size=320,
            )
            html.append(f'<div class="head-wrap">{svg_str}</div>')
        html.append('</div>')

    # ── Summary table ─────────────────────────────────────────────────────────
    html.append(
        '<p style="font-size:8pt;color:#555;margin:3px 0 4px">'
        'All nozzles on the vertical centre plane of the head (horizontal x = 0). '
        f'Weld clearance minimum = max(3×t_head, 25 mm) = {min_weld:.0f} mm. '
        'Zone: Crown = standard analysis valid; Knuckle = specialist analysis required.'
        '</p>'
    )
    sum_hdrs = ["Tag", "Side", "DN (OD mm)", "From top", "r / R",
                "Zone", "Edge → wall", "Edge → bnd", "Depth / Head depth",
                "Geom", "Code", "Reinf"]
    sum_rows = []
    for nz, nres, rres in head_nz:
        r = nres.r_from_axis_mm
        e2w_ok  = nres.edge_to_shell_mm >= min_weld
        e2k_str = (f"{nres.edge_to_knuckle_mm:.0f} mm"
                   if nres.edge_to_knuckle_mm is not None else "—")
        geom_s  = '<span class="ok">✓</span>' if nres.geom_ok else '<span class="fail">✗</span>'
        code_s  = ('<span class="ok">✓</span>'  if nres.code_ok is True else
                   '<span class="warn">?</span>' if nres.code_ok is None else
                   '<span class="fail">✗</span>')
        reinf_s = ('<span class="ok">✓</span>'  if (rres and rres.adequate is True) else
                   '<span class="warn">?</span>' if (rres and rres.adequate is None) else
                   '<span class="fail">✗</span>')
        e2w_cls = "" if e2w_ok else ' style="color:#dc2626;font-weight:bold"'
        depth_s = f"{nres.z_on_head_mm:.0f} / {nres.head_depth_mm:.0f} mm"
        sum_rows.append([
            f"<b>{nz['tag']}</b>", nz["loc"],
            f"DN{nz['dn']} ({nres.nozzle_OD_mm:.1f})",
            f"{nres.d_from_top_mm:.0f} mm",
            f"{r/R:.2f}",
            nres.zone.replace("_", " ").capitalize(),
            f'<span{e2w_cls}>{nres.edge_to_shell_mm:.0f} mm</span>',
            e2k_str, depth_s, geom_s, code_s, reinf_s,
        ])
    html.append(_dt(sum_hdrs, sum_rows))

    # ── Per-nozzle detail ─────────────────────────────────────────────────────
    for nz, nres, rres in head_nz:
        r    = nres.r_from_axis_mm
        nOR  = nres.nozzle_OR_mm
        bore = max(nres.nozzle_OD_mm - 2 * nres.nozzle_t_mm, 1.0)
        bore_ratio = bore / Di

        html.append('<div class="nz-block">')
        html.append(f'<div class="nz-block-hdr">'
                    f'{_e(nz["tag"])} — {_e(nz["service"])} &nbsp;|&nbsp; '
                    f'DN{nz["dn"]} &nbsp;|&nbsp; {_e(nz["loc"])}'
                    f'</div>')
        html.append('<div style="padding:5px 8px">')

        # Key metrics bar
        html.append('<div class="metrics">')
        metrics = [
            ("r / R", f"{r/R:.3f}"),
            ("Nozzle edge / R", f"{(r+nOR)/R:.3f}"),
            ("Edge → shell wall", f"{nres.edge_to_shell_mm:.0f} mm"
             + (" ✓" if nres.edge_to_shell_mm >= min_weld else f" ✗ < {min_weld:.0f} mm")),
            ("Zone", nres.zone.replace("_", " ").capitalize()),
            ("Axial depth", f"{nres.z_on_head_mm:.0f} / {nres.head_depth_mm:.0f} mm"),
            ("Bore / Di", f"{bore_ratio:.1%}"),
        ]
        if nres.edge_to_knuckle_mm is not None:
            metrics.append(("Edge → crown bnd",
                            f"{nres.edge_to_knuckle_mm:.0f} mm"
                            + (" ✓" if nres.edge_to_knuckle_mm >= 0 else " ✗")))
        for k, v in metrics:
            html.append(f'<span class="metric"><b>{_e(k)}:</b> {_e(v)}</span>')
        html.append('</div>')

        # Reinforcement summary
        if rres is not None:
            surplus = rres.A_total_mm2 - rres.A_required_mm2
            cls = "ok" if surplus >= 0 else "fail"
            html.append(
                f'<p style="font-size:8.5pt;margin:3px 0">'
                f'Reinforcement: A_req = {rres.A_required_mm2:,.0f} mm²  '
                f'A_avail = {rres.A_total_mm2:,.0f} mm²  '
                f'<span class="{cls}">{"surplus" if surplus>=0 else "deficit"} '
                f'{abs(surplus):,.0f} mm²</span>'
                f'</p>'
            )

        # Inlet positioning (inlet nozzles only)
        if nz.get("service") == "Inlet" and lzhh_mm > 0:
            _nz_IR_h   = (nres.nozzle_OD_mm - 2.0 * nres.nozzle_t_mm) / 2.0
            _nz_bot_h  = (Di - nres.d_from_top_mm) - _nz_IR_h
            _top_clr_h = nres.edge_to_shell_mm          # OD top → vessel crown ID
            _lzhh_clr  = _nz_bot_h - lzhh_mm            # LZHH → inlet device bottom
            _MIN_CLR   = 150.0
            html.append('<div class="sub-sec" style="margin-top:5px">Inlet positioning</div>')
            html.append('<div class="metrics">')
            _top_flag = " ✓" if _top_clr_h >= min_weld else f" ✗ &lt; {min_weld:.0f} mm"
            html.append(f'<span class="metric"><b>Nozzle OD top → vessel crown ID:</b> '
                        f'{_top_clr_h:.0f} mm{_top_flag}</span>')
            _lzhh_cls  = "ok"   if _lzhh_clr >= _MIN_CLR else "fail"
            _lzhh_flag = (" ✓ ≥ 150 mm"          if _lzhh_clr >= _MIN_CLR else
                          " ✗ submerged at LZHH"  if _lzhh_clr < 0 else
                          f" ⚠ only {_lzhh_clr:.0f} mm — min 150 mm")
            html.append(f'<span class="metric"><b>LZHH → inlet device bottom:</b> '
                        f'<span class="{_lzhh_cls}">{_lzhh_clr:.0f} mm{_lzhh_flag}</span></span>')
            html.append(f'<span class="metric"><b>Inlet bore bottom from vessel bottom:</b> '
                        f'{_nz_bot_h:.0f} mm</span>')
            html.append('</div>')
            if _lzhh_clr < 0:
                html.append(
                    f'<div class="impl-err">🚫 Inlet device submerged at LZHH by '
                    f'{-_lzhh_clr:.0f} mm — raise inlet nozzle or lower LZHH.</div>')
            elif _lzhh_clr < _MIN_CLR:
                html.append(
                    f'<div class="impl-warn">⚠ Only {_lzhh_clr:.0f} mm clearance from LZHH to '
                    f'inlet device bottom — minimum 150 mm recommended. Inlet device may be '
                    f'intermittently submerged at high-high level, causing backflow and poor '
                    f'distribution.</div>')

        # Engineering implications
        impl: list[tuple[str, str]] = []

        if nres.edge_to_shell_mm < 0:
            impl.append(("err",
                f"OD overlaps shell wall by {-nres.edge_to_shell_mm:.0f} mm — "
                "not buildable. Move toward axis or use smaller DN."))
        elif nres.edge_to_shell_mm < min_weld:
            impl.append(("warn",
                f"Weld clearance {nres.edge_to_shell_mm:.0f} mm &lt; min {min_weld:.0f} mm "
                f"(max(3·t_head, 25 mm), {code} cl. {'5.6' if code_key=='EN' else 'UW-11'}). "
                "Adjacent weld-heat zones overlap — PWHT and NDT compromised. "
                "Move toward axis, use hemispherical head, or obtain fabrication deviation."))

        if nres.zone == "knuckle":
            if head_type in (HeadType.TORISPHERICAL, HeadType.FLANGED_DISHED):
                impl.append(("err",
                    f"Nozzle centre in knuckle zone — standard area-replacement "
                    f"({code} {'cl.9 / UG-37' if code_key=='EN' else 'UG-37'}) is NOT valid. "
                    "Move to crown zone, use hemispherical head, or commission FEA."))
            elif head_type == HeadType.ELLIPSOIDAL:
                impl.append(("warn",
                    "Nozzle in compressive-hoop zone — standard area-replacement is "
                    "non-conservative. Detailed analysis or FEA required."))

        elif nres.edge_to_knuckle_mm is not None and nres.edge_to_knuckle_mm < 0:
            impl.append(("warn",
                f"OD edge encroaches on crown/knuckle boundary by "
                f"{-nres.edge_to_knuckle_mm:.0f} mm — reinforcement limit zone "
                "partially in non-standard region; A_available overstated."))

        if 0 < nres.edge_to_shell_mm < 0.5 * (Di * 0.10):
            impl.append(("warn",
                "3-way stress interaction (nozzle + head/shell discontinuity + hoop) "
                "at this proximity — outside standard code formulas even if weld "
                "clearance is met. Full 3D FEA required."))

        if bore_ratio > 0.5:
            impl.append(("err",
                f"Bore/Di = {bore_ratio:.0%} &gt; 50 % — pressure-area method or FEA "
                "mandatory; reinforcing insert likely needed."))
        elif bore_ratio > 1/3:
            impl.append(("warn",
                f"Bore/Di = {bore_ratio:.0%} &gt; 33 % — enhanced reinforcement check "
                "required; confirm limit zone stays within crown."))

        # Existing nres warnings / errors (avoid duplicates)
        existing_msgs = {m[:40] for _, m in impl}
        for w in nres.warnings + nres.errors:
            if w[:40] not in existing_msgs:
                impl.append(("warn" if w in nres.warnings else "err", w))

        if impl:
            html.append('<div style="margin-top:4px">')
            for lvl, msg in impl:
                cls = "impl-err" if lvl == "err" else "impl-warn" if lvl == "warn" else "impl-info"
                icon = "🚫" if lvl == "err" else "⚠" if lvl == "warn" else "ℹ"
                html.append(f'<div class="{cls}">{icon} {msg}</div>')
            html.append('</div>')
        else:
            html.append('<div class="impl-info">ℹ No edge-proximity issues detected for this nozzle.</div>')

        # Alternative head type comparison table
        html.append('<div class="sub-sec" style="margin-top:6px">Alternative head type comparison</div>')
        alt_hdrs = ["Head type", "Zone", "Code", "Edge → wall", "Edge → bnd",
                    "Crown limit", "Head depth", "Notes"]
        alt_rows = []
        for label, ht_label, override_kw in _ENDCAP_ALT_HEADS:
            kw = dict(
                crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
                alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
                nozzle_OD_mm=nres.nozzle_OD_mm, nozzle_t_mm=nres.nozzle_t_mm,
                t_head_nom_mm=t_head_nom,
            )
            kw.update(override_kw)
            # Resolve head type enum from label
            from engines.head_geometry import HeadType as _HT
            _ht_map = {
                "Hemispherical": _HT.HEMISPHERICAL,
                "Ellipsoidal 2:1": _HT.ELLIPSOIDAL,
                "Torispherical (dished)": _HT.TORISPHERICAL,
                "Flanged & Dished (ASME F&D)": _HT.FLANGED_DISHED,
                "Conical": _HT.CONICAL,
                "Flat (unstayed)": _HT.FLAT,
            }
            ht_enum = _ht_map[ht_label]
            try:
                ar = nozzle_on_head(ht_enum, Di, nres.d_from_top_mm, nz["dn"], **kw)
            except Exception:
                continue

            is_cur = ht_enum == head_type
            cur_mark = "▶ " if is_cur else ""
            zone_s = ar.zone.replace("_", " ").capitalize()
            code_s  = ("✓ OK"  if ar.code_ok is True else
                       "? Check" if ar.code_ok is None else "✗ FAIL")
            e2w_s   = f"{ar.edge_to_shell_mm:.0f} mm"
            e2k_s   = (f"{ar.edge_to_knuckle_mm:.0f} mm"
                       if ar.edge_to_knuckle_mm is not None else "—")
            clim_s  = (f"≤{ar.d_at_crown_end_mm:.0f} mm from top"
                       if ar.d_at_crown_end_mm is not None else "—")
            depth_s = f"{ar.head_depth_mm:.0f} mm"
            # Short note
            notes_map = {
                "Hemispherical":            "No knuckle — full face",
                "Ellipsoidal 2:1":          "Reversal at r≈0.58R",
                "Tori — Klöpper (r=0.10Di)":"r_cj ≈ 0.80R",
                "F&D ASME (r=0.06Di)":      "r_cj ≈ 0.86R (larger crown)",
                "Conical 30°":              "No knuckle; apex check needed",
                "Flat":                     "No curvature; thick plate",
            }
            note_s = notes_map.get(label, "")

            alt_rows.append([
                f"{cur_mark}{_e(label)}", zone_s, code_s,
                e2w_s, e2k_s, clim_s, depth_s, note_s,
            ])
        html.append(_dt(alt_hdrs, alt_rows))
        html.append(
            '<p style="font-size:7.5pt;color:#64748b;margin:2px 0">'
            "▶ = currently selected head type &nbsp;·&nbsp; "
            "Alternative heads use standard default geometry &nbsp;·&nbsp; "
            "? = detailed analysis required"
            '</p>'
        )

        html.append('</div></div>')   # close padding div + nz-block

    html.append('</div>')  # close .sec
    return '\n'.join(html)


# ── SVG Sketch ────────────────────────────────────────────────────────────────

def _sketch_svg(
    Di: float, L_shell: float, h_head: float,
    nozzle_results: list,
    levels_mm: dict,
    nll_mm: float,
    saddle_a_mm: float = 0.0,
) -> str:
    from engines.nozzle_geometry import NOZZLE_OD, NOZZLE_WALL_T

    # Canvas: fix width at 860px, height proportional to vessel
    SVG_W = 860
    # Visible range in vessel coords (x: -margin to L+h+margin, y: -margin to Di+margin)
    MX = max(h_head * 1.5, 400.0)  # x margin — enough for large nozzle flanges
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

    # ── Vessel outline — single closed path, equal scale guaranteed ───────
    # Coordinate convention: px/py both use the same factor sc (mm→SVG px),
    # so 1 mm = sc px in both axes; no distortion possible.
    #
    # Path goes: top-left-tangent → top-wall → right-head-arc → bottom-wall
    #            → left-head-arc → close (Z)
    #
    # SVG arc orientation (y-axis points DOWN):
    #   Left  head: from (tl, top) to (tl, bottom) — large-arc=0, sweep=1 → bows LEFT
    #   Right head: from (tr, top) to (tr, bottom) — large-arc=0, sweep=0 → bows RIGHT
    tl  = px(0)             # left  tangent x (SVG)
    tr  = px(L_shell)       # right tangent x (SVG)
    vtop = py(Di)           # vessel top    y (SVG, small value)
    vbot = py(0)            # vessel bottom y (SVG, large value)
    rx   = h_head * sc      # head horizontal semi-axis (SVG px)
    ry   = (Di / 2) * sc    # head vertical   semi-axis (SVG px)

    if h_head > 0:
        # SVG arc notes (y axis points DOWN):
        # Going top→bottom at same x, sweep=1 (CW) bows outward to the RIGHT.
        # Going bottom→top at same x, sweep=1 (CW) bows outward to the LEFT.
        # Both heads therefore use sweep=1.
        vessel_d = (
            f"M {tl:.2f} {vtop:.2f} "                               # top-left tangent
            f"L {tr:.2f} {vtop:.2f} "                               # top wall →
            f"A {rx:.2f} {ry:.2f} 0 0 1 {tr:.2f} {vbot:.2f} "     # right head (CW → bows right)
            f"L {tl:.2f} {vbot:.2f} "                               # bottom wall ←
            f"A {rx:.2f} {ry:.2f} 0 0 1 {tl:.2f} {vtop:.2f} "     # left  head (CW → bows left)
            f"Z"
        )
    else:
        vessel_d = (
            f"M {tl:.2f} {vtop:.2f} L {tr:.2f} {vtop:.2f} "
            f"L {tr:.2f} {vbot:.2f} L {tl:.2f} {vbot:.2f} Z"
        )

    # White fill behind everything, then liquid, then outline on top
    out.append(f'<path d="{vessel_d}" fill="#f8faff" stroke="none"/>')

    # ── Liquid fill clipped to vessel outline ─────────────────────────────
    liq_h = max(0.0, min(Di, nll_mm))
    if liq_h > 0:
        clip_id = "vc"
        out.append(f'<defs><clipPath id="{clip_id}"><path d="{vessel_d}"/></clipPath></defs>')
        liq_y = py(liq_h)  # top of liquid in SVG coords
        out.append(
            f'<rect x="{px(-h_head):.1f}" y="{liq_y:.1f}" '
            f'width="{(L_shell + 2*h_head)*sc:.1f}" height="{(vbot-liq_y):.1f}" '
            f'fill="rgba(147,197,253,0.35)" clip-path="url(#{clip_id})"/>'
        )

    # ── Vessel outline on top ─────────────────────────────────────────────
    out.append(f'<path d="{vessel_d}" fill="none" stroke="#1e3a5f" stroke-width="2"/>')

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

    def _light(h6):
        r,g,b = int(h6[1:3],16),int(h6[3:5],16),int(h6[5:7],16)
        return f"#{int(r*.12+255*.88):02x}{int(g*.12+255*.88):02x}{int(b*.12+255*.88):02x}"

    def _mid(h6):
        r,g,b = int(h6[1:3],16),int(h6[3:5],16),int(h6[5:7],16)
        return f"#{int(r*.38+255*.62):02x}{int(g*.38+255*.62):02x}{int(b*.38+255*.62):02x}"

    for nz, nres, rres, _fok, _pat in nozzle_results:
        dn  = nz["dn"]
        loc = nz["loc"]
        svc = nz.get("service", "")
        nc  = _svc_colors.get(svc, "#475569")
        fl  = _light(nc)
        ff  = _mid(nc)

        OD     = NOZZLE_OD.get(dn, dn * 1.05)
        BV     = OD / 2 * 0.68   # visual bore radius (68 % of pipe radius)

        stub     = max(OD * 1.4, 45.0)
        flange_r = OD * 0.62
        flange_t = max(OD * 0.08, 7.0)
        pipe_h   = stub - flange_t

        if loc == "Left head" and nres is not None:
            ny   = Di - nres.d_from_top_mm
            nz_x = -nres.z_on_head_mm
            rect(nz_x - pipe_h, ny - OD/2, pipe_h, OD, fill=fl, stroke=nc, sw=1.2)
            rect(nz_x - pipe_h, ny - BV, pipe_h, BV*2, fill="white", stroke="none", sw=0)
            rect(nz_x - stub, ny - flange_r, flange_t, flange_r*2, fill=ff, stroke=nc, sw=1.5)
            text(nz_x - stub - 3, ny + 2, nz["tag"],
                 anchor="end", size=7, color=nc, bold=True)

        elif loc == "Right head" and nres is not None:
            ny   = Di - nres.d_from_top_mm
            nz_x = L_shell + nres.z_on_head_mm
            rect(nz_x, ny - OD/2, pipe_h, OD, fill=fl, stroke=nc, sw=1.2)
            rect(nz_x, ny - BV, pipe_h, BV*2, fill="white", stroke="none", sw=0)
            rect(nz_x + pipe_h, ny - flange_r, flange_t, flange_r*2, fill=ff, stroke=nc, sw=1.5)
            text(nz_x + stub + 3, ny + 2, nz["tag"],
                 anchor="start", size=7, color=nc, bold=True)

        elif loc == "Shell — top":
            nx = nz.get("axial_mm", L_shell / 2)
            rect(nx - OD/2, Di, OD, pipe_h, fill=fl, stroke=nc, sw=1.2)
            rect(nx - BV, Di, BV*2, pipe_h, fill="white", stroke="none", sw=0)
            rect(nx - flange_r, Di + pipe_h, flange_r*2, flange_t, fill=ff, stroke=nc, sw=1.5)
            text(nx, Di + stub + 10, nz["tag"],
                 anchor="middle", size=7, color=nc, bold=True)

        elif loc == "Shell — bottom":
            nx = nz.get("axial_mm", L_shell / 2)
            rect(nx - OD/2, -pipe_h, OD, pipe_h, fill=fl, stroke=nc, sw=1.2)
            rect(nx - BV, -pipe_h, BV*2, pipe_h, fill="white", stroke="none", sw=0)
            rect(nx - flange_r, -(pipe_h + flange_t), flange_r*2, flange_t, fill=ff, stroke=nc, sw=1.5)
            text(nx, -(stub + 10), nz["tag"],
                 anchor="middle", size=7, color=nc, bold=True)

        else:  # Shell — side: end-on view → flange ring + pipe ring
            nx       = nz.get("axial_mm", L_shell / 2)
            ny_s     = Di / 2
            fl_r_ss  = OD * 0.62
            bore_vis = OD / 2 * 0.68
            # Flange outer ring
            out.append(f'<circle cx="{px(nx):.1f}" cy="{py(ny_s):.1f}" '
                       f'r="{fl_r_ss*sc:.1f}" fill="none" stroke="{nc}" stroke-width="1.5"/>')
            # Pipe OD disk
            circle(nx, ny_s, OD/2,    fill=fl,      stroke=nc,  sw=1.2)
            # Bore disk (hollow centre)
            circle(nx, ny_s, bore_vis, fill="white",  stroke="none",  sw=0)
            text(nx, ny_s + fl_r_ss + 10, nz["tag"],
                 anchor="middle", size=6.5, color=nc, bold=True)

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
    P_op_barg: float | None = None,
    T_op_C: float | None = None,
    t_holdup_req_min: float = 3.0,
    t_surge_req_min: float = 3.0,
    include_surge_check: bool = True,
    ldv_result: dict | None = None,
    int_loads_result: dict | None = None,
    weight_result: dict | None = None,
    Z_gas: float = 1.0,
    lining_spec: dict | None = None,
    # Head geometry — needed for endcap drawings and analysis
    head_type=None,          # HeadType enum (None → skip endcap analysis)
    crown_ratio: float = 1.0,
    knuckle_ratio: float = 0.10,
    alpha_deg_cone: float = 30.0,
    ellipse_ratio: float = 2.0,
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

    # ── DISCLAIMER BANNER — always shown; wording scales with issued_for ────────
    # SepScope is a scoping tool for inquiry/FEED and is never a certified
    # design deliverable. The banner stays on all issue statuses.
    if issued_for == "Construction":
        banner = (
            '<div class="inquiry-banner" style="background:#fee2e2;border-color:#dc2626;color:#7f1d1d">'
            '🚫  THIS DOCUMENT IS ISSUED FOR CONSTRUCTION USE — '
            'IT IS GENERATED BY A SCREENING TOOL AND IS NOT A CERTIFIED DESIGN CALCULATION.  '
            'INDEPENDENT ENGINEERING REVIEW IS MANDATORY BEFORE FABRICATION.  🚫'
            '</div>'
        )
    elif issued_for in ("Approval",):
        banner = (
            '<div class="inquiry-banner">'
            '⚠  THIS DOCUMENT IS ISSUED FOR APPROVAL — SCREENING-LEVEL ONLY.  '
            'ALL RESULTS MUST BE VERIFIED BY A QUALIFIED ENGINEER BEFORE APPROVAL.  ⚠'
            '</div>'
        )
    else:
        banner = (
            '<div class="inquiry-banner">'
            f'⚠  ISSUED FOR {_e(issued_for.upper())} — SCREENING-LEVEL ONLY.  '
            'NOT FOR CONSTRUCTION.  ⚠'
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
        ("Operating pressure",
         f"{P_op_barg:.2f}  barg" if P_op_barg is not None else "—"),
        ("Operating temperature",
         f"{T_op_C:.0f}  °C" if T_op_C is not None else "—"),
        ("Design pressure",         f"{P_barg:.2f}  barg"),
        ("Design temperature",      f"{T_C:.0f}  °C"),
        ("Hydrostatic test pressure", f"{hydro_P:.2f}  barg  ({hydro_factor:.2f} × DP, {code_full})"),
        ("Corrosion allowance",     "See mechanical design section"),
        ("Fluid service",           "Two-phase gas / liquid — non-fouling"),
    ))

    # ── B  PROCESS FLUIDS ─────────────────────────────────────────────────────
    rho_g  = gas_props.rho_kgm3
    rho_l  = liq_props.rho_kgm3
    mu_g   = gas_props.mu_Pas * 1e6   # μPa·s
    mu_l   = liq_props.mu_Pas * 1e3   # mPa·s
    rho_mix = (rho_g * Q_gas_m3h + rho_l * Q_liq_m3h) / max(Q_gas_m3h + Q_liq_m3h, 1e-9)

    # Compact fluid property panels
    gas_kv = _kv(
        ("Fluid",                  gas_fluid),
        ("Mol. weight",            f"{gas_props.MW:.2f}  g/mol"),
        ("Compressibility Z",      f"{Z_gas:.3f}"),
        ("Density at op. cond.",   f"{rho_g:.3f}  kg/m³"),
        ("Dynamic viscosity",      f"{mu_g:.1f}  μPa·s"),
    )
    liq_kv = _kv(
        ("Fluid",                  liq_fluid),
        ("Density at op. cond.",   f"{rho_l:.0f}  kg/m³"),
        ("Dynamic viscosity",      f"{mu_l:.3f}  mPa·s"),
    )

    # ── Per-nozzle stream table ────────────────────────────────────────────
    def _bore(nz_dict):
        dn  = nz_dict["dn"]
        OD  = NOZZLE_OD.get(dn, dn * 1.05)
        rec = recommended_schedule(nz_dict.get("pn", 25), code_key)
        t   = float(NOZZLE_WALL_SCH[rec].get(dn, NOZZLE_WALL_T.get(dn, 8.0)))
        ID  = max(OD - 2 * t, 1.0)
        return ID, _m.pi * (ID * 1e-3) ** 2 / 4.0

    def _td(val, rs=1, bold=False, bg=""):
        rs_attr = f' rowspan="{rs}"' if rs > 1 else ""
        st_attr = []
        if bold:   st_attr.append("font-weight:bold")
        if bg:     st_attr.append(f"background:{bg}")
        st_str = f' style="{";".join(st_attr)}"' if st_attr else ""
        v = str(val)
        v = v if v.startswith("<") else _e(v)
        return f"<td{rs_attr}{st_str}>{v}</td>"

    _COLS = ["Tag", "DN", "Service", "Component", "Fluid",
             "Vol. flow  (m³/h)", "Mass flow  (kg/h)",
             "Density  (kg/m³)", "Viscosity",
             "Nozzle vel.  (m/s)", "ρv²  (Pa)"]
    th_row = "".join(f"<th>{_e(c)}</th>" for c in _COLS)

    inlet_nzs   = [(nz,*r) for nz,*r in nozzle_results if nz.get("service") == "Inlet"]
    gas_out_nzs = [(nz,*r) for nz,*r in nozzle_results if nz.get("service") == "Gas outlet"]
    liq_out_nzs = [(nz,*r) for nz,*r in nozzle_results if nz.get("service") == "Liquid outlet"]

    tbody = ""

    # ── Inlet nozzles: 3 rows each (gas / liquid / mixture) ───────────────
    for (nz, *_) in inlet_nzs:
        dn = nz["dn"]
        ID, A = _bore(nz)
        Qg = Q_gas_m3h / n_inlets
        Ql = Q_liq_m3h / n_inlets
        Qm = Qg + Ql
        v_m  = (Qm / 3600.0) / max(A, 1e-9)
        rv2  = rho_mix * v_m ** 2
        rv2_ok = rv2 <= 2400.0
        rv2_s = (f'<span style="color:{"#166534" if rv2_ok else "#dc2626"};font-weight:bold">'
                 f'{rv2:,.0f} {"✓" if rv2_ok else "✗"}</span>')

        # Row 1 — gas component
        tbody += ("<tr>"
            + _td(f"<b>{nz['tag']}</b>", rs=3)
            + _td(f"DN{dn}",             rs=3)
            + _td(nz["service"],         rs=3)
            + _td("Gas phase")
            + _td(gas_fluid)
            + _td(f"{Qg:,.1f}")
            + _td(f"{Qg*rho_g:,.0f}")
            + _td(f"{rho_g:.3f}")
            + _td(f"{mu_g:.1f} μPa·s")
            + _td("—") + _td("—")
            + "</tr>")
        # Row 2 — liquid component
        tbody += ("<tr>"
            + _td("Liquid phase")
            + _td(liq_fluid)
            + _td(f"{Ql:,.2f}")
            + _td(f"{Ql*rho_l:,.0f}")
            + _td(f"{rho_l:.0f}")
            + _td(f"{mu_l:.3f} mPa·s")
            + _td("—") + _td("—")
            + "</tr>")
        # Row 3 — mixture total (highlighted)
        tbody += (f'<tr style="background:#eef2ff">'
            + _td("<b>Mixture</b>")
            + _td("—")
            + _td(f"<b>{Qm:,.1f}</b>")
            + _td(f"<b>{Qg*rho_g+Ql*rho_l:,.0f}</b>")
            + _td(f"{rho_mix:.1f}")
            + _td("—")
            + _td(f"<b>{v_m:.2f}</b>")
            + _td(rv2_s)
            + "</tr>")

    # ── Gas outlet ────────────────────────────────────────────────────────
    for (nz, *_) in gas_out_nzs:
        ID, A = _bore(nz)
        v_go = (Q_gas_m3h / 3600.0) / max(A, 1e-9)
        tbody += ("<tr>"
            + _td(f"<b>{nz['tag']}</b>")
            + _td(f"DN{nz['dn']}")
            + _td(nz["service"])
            + _td("Gas  (separated)")
            + _td(gas_fluid)
            + _td(f"{Q_gas_m3h:,.1f}")
            + _td(f"{Q_gas_m3h*rho_g:,.0f}")
            + _td(f"{rho_g:.3f}")
            + _td(f"{mu_g:.1f} μPa·s")
            + _td(f"{v_go:.2f}")
            + _td("—")
            + "</tr>")

    # ── Liquid outlet ─────────────────────────────────────────────────────
    for (nz, *_) in liq_out_nzs:
        ID, A = _bore(nz)
        v_lo = (Q_liq_m3h / 3600.0) / max(A, 1e-9)
        tbody += ("<tr>"
            + _td(f"<b>{nz['tag']}</b>")
            + _td(f"DN{nz['dn']}")
            + _td(nz["service"])
            + _td("Liquid  (separated)")
            + _td(liq_fluid)
            + _td(f"{Q_liq_m3h:,.2f}")
            + _td(f"{Q_liq_m3h*rho_l:,.0f}")
            + _td(f"{rho_l:.0f}")
            + _td(f"{mu_l:.3f} mPa·s")
            + _td(f"{v_lo:.2f}")
            + _td("—")
            + "</tr>")

    if not tbody:
        tbody = f'<tr><td colspan="{len(_COLS)}" style="color:#888">No inlet / outlet nozzles configured.</td></tr>'

    stream_table = (
        f'<table class="dt" style="font-size:9pt">'
        f'<thead><tr>{th_row}</tr></thead>'
        f'<tbody>{tbody}</tbody>'
        f'</table>'
        f'<div style="font-size:8pt;color:#555;padding:2px 6px;margin-top:2px">'
        f'All flows at actual operating conditions.  '
        f'Inlet flow split equally between {n_inlets} nozzle{"s" if n_inlets>1 else ""}.  '
        f'ρv² limit: 2 400 Pa (API RP 14E, non-erosive service).  '
        f'Bore ID based on nominal schedule for the selected rating.'
        f'</div>'
    )

    panels_b = (
        f'<div class="two-panel" style="margin-bottom:6px">'
        f'{_panel("Gas Phase Properties", gas_kv)}'
        f'{_panel("Liquid Phase Properties", liq_kv)}'
        f'</div>'
        + stream_table
    )
    sec_b = _sec("B", "Process Fluids & Nozzle Streams", panels_b)

    # ── C  MECHANICAL DESIGN ──────────────────────────────────────────────────
    from engines import MATERIALS
    mat      = MATERIALS.get(mat_key, {})
    mat_name = mat.get("name", mat_key)
    CA_mm    = getattr(shell_res, "CA_mm", 3.0)
    z_weld   = getattr(shell_res, "z",     1.0)
    z_label  = ("1.0  (full radiography)" if z_weld >= 1.0
                else f"{z_weld:.2f}  (partial radiography)")

    if weight_result is not None:
        wt = weight_result
        _w_sfx = "  (est. ±20 %, see D.2)"
        _w_empty = f"{wt['m_dry_kg']:,.0f}  kg  ({wt['m_dry_kg']/1000:.2f} t){_w_sfx}"
        _w_op    = f"{wt['m_operating_kg']:,.0f}  kg  ({wt['m_operating_kg']/1000:.2f} t){_w_sfx}"
        _w_ht    = f"{wt['m_hydrotest_kg']:,.0f}  kg  ({wt['m_hydrotest_kg']/1000:.2f} t){_w_sfx}"
    else:
        _w_empty = _w_op = _w_ht = "TBD (vendor)"

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
        ("Corrosion allowance  CA",      f"{CA_mm:.1f}  mm"),
        ("Weld joint efficiency  z",     z_label),
        ("Support type",                 "Saddle supports — 2 off"),
        ("Saddle position from tangent", f"{saddle_a_mm:.0f}  mm" if saddle_a_mm > 0 else "TBD"),
        ("Saddle width",                 f"{saddle_w_mm:.0f}  mm"),
        ("Weight — empty",               _w_empty),
        ("Weight — operating",           _w_op),
        ("Weight — hydro test",          _w_ht),
    ))

    # Lining / surface treatment section (C.1 when specified)
    if lining_spec:
        ls = lining_spec
        lining_rows: list[tuple[str, str]] = []
        if ls.get("has_clad"):
            lining_rows.append(("Internal cladding / weld overlay", ls["clad_material"]))
            lining_rows.append(("Cladding thickness", f"{ls['clad_t_mm']:.1f}  mm  (min., after forming)"))
            lining_rows.append(("Cladding does not contribute to", "pressure-bearing wall thickness"))
            if ls.get("clad_note"):
                lining_rows.append(("Cladding note", ls["clad_note"]))
        if ls.get("has_enp"):
            lining_rows.append(("Internal surface plating", ls["enp_type"]))
            lining_rows.append(("Plating thickness", f"{ls['enp_t_um']:.0f}  µm  (min.)"))
            lining_rows.append(("Plating does not contribute to", "pressure-bearing wall thickness"))
            if ls.get("enp_note"):
                lining_rows.append(("Plating note", ls["enp_note"]))
        if ls.get("free_text"):
            lining_rows.append(("Material / treatment notes", ls["free_text"]))
        if lining_rows:
            sec_c += _sec("C.1", "Internal Lining / Surface Treatment", _kv(*lining_rows))

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
    _surge_limit = (f"≥ {t_surge_req_min:.1f}  min  (required)"
                    if include_surge_check else "Informational — check not required")
    sizing_rows += [
        _row("Liquid hold-up time at NLL",
             f"{sep_res.t_holdup_s/60:.1f}  min",
             f"≥ {t_holdup_req_min:.1f}  min  (required)",
             sep_res.holdup_ok),
        _row("Surge time  NLL → LAHH",
             f"{sep_res.t_surge_s/60:.1f}  min",
             _surge_limit,
             sep_res.surge_ok if include_surge_check else None),
        _row("NLL fill fraction  (NLL / Di)  [target ~50 %]",
             f"{sep_res.nll_frac*100:.0f}  %",
             "40 – 60 %",
             0.35 <= sep_res.nll_frac <= 0.65),
    ]
    # LDV rows
    if ldv_result is not None:
        ldv = ldv_result
        _has_target = ldv.get("target_m3") is not None
        sizing_rows += [
            _row("LDV — Segment A (VB → LZLL)",
                 f"{ldv['seg_a_m3']*1000:.1f}  L  ({ldv['seg_a_m3']:.4f} m³)",
                 f"VB = {ldv['eff_vb_mm']:.0f} mm  →  LZLL = {ldv['lzll_mm']:.0f} mm",
                 ldv.get("seg_a_ok") if _has_target else None),
            _row("LDV — Segment B (LZLL → LALL)",
                 f"{ldv['seg_b_m3']*1000:.1f}  L  ({ldv['seg_b_m3']:.4f} m³)",
                 f"LZLL = {ldv['lzll_mm']:.0f} mm  →  LALL = {ldv['lall_mm']:.0f} mm",
                 ldv.get("seg_b_ok") if _has_target else None),
        ]
        if ldv.get("target_m3") is not None:
            tgt_L    = ldv["target_m3"] * 1000
            req_a_L  = (ldv.get("ldv_required_a_m3") or ldv.get("ldv_required_m3") or 0.0) * 1000
            req_b_L  = (ldv.get("ldv_required_b_m3") or ldv.get("ldv_required_m3") or 0.0) * 1000
            sizing_rows += [
                _row("LDV Target  (before SF)  — downstream equipment volume",
                     f"{tgt_L:.1f}  L  (input)",
                     "User-specified required LDV",
                     None),
                _row(f"Seg A Required  (Target × SF {ldv['sf']:.2f})",
                     f"{req_a_L:.1f}  L",
                     "Requirement for Segment A check",
                     None),
                _row(f"Seg B Required  (Target × SF {ldv.get('sf_b', ldv['sf']):.2f})",
                     f"{req_b_L:.1f}  L",
                     "Requirement for Segment B check",
                     None),
            ]
    if inlet_nzs:
        _nz0 = inlet_nzs[0][0]
        _, _A0 = _bore(_nz0)
        _Qm0  = (Q_gas_m3h + Q_liq_m3h) / n_inlets / 3600.0
        _vm0  = _Qm0 / max(_A0, 1e-9)
        _rv2  = rho_mix * _vm0 ** 2
        sizing_rows.append(_row(
            f"Inlet nozzle momentum  ρv²  (DN{_nz0['dn']})  [API RP 14E]",
            f"{_rv2:,.0f}  Pa",
            "≤ 2 400  Pa",
            _rv2 <= 2400.0,
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

    sec_d = _sec("D", "Separator Sizing  (API 12J screening)",
                 _dt(["Criterion", "Actual", "Limit", "Status"], sizing_rows))

    # ── D.1  INTERNALS MECHANICAL LOADS ──────────────────────────────────────
    sec_d1 = ""
    if int_loads_result is not None:
        il = int_loads_result
        _inlet_kv = _kv(
            ("Scenario",
             f"LDV surge: {il['V_ldv_m3']*1000:.1f} L in {il['t_flood_s']:.0f} s  "
             f"→  {il['Q_ldv_per_inlet_m3s']*1000:.2f} L/s per inlet"),
            ("Nozzle",
             f"DN{il['nozzle_dn']}  ·  ID {il['nz_id_mm']:.0f} mm  "
             f"·  A = {il['A_nozzle_m2']*1e4:.1f} cm²"),
            ("Surge velocity",      f"{il['v_ldv_ms']:.2f}  m/s"),
            ("Impact force",        f"{il['F_impact_N']:,.0f}  N  (unfactored)"),
            (f"Design force  (SF {il['SF_inlet']:.0f})",
             f"<b>{il['F_inlet_design_N']:,.0f}  N</b>"),
            ("Basis",
             "F = ρ_liq × v² × A_nozzle  (momentum flux, first principles)  "
             "—  API RP 14E provides ρv²; force = ρv² × A is the direct extension."),
        )
        _baffle_kv = _kv(
            ("Scenario",
             f"Same LDV surge, liquid through baffle holes  "
             f"(φ = {il['phi']*100:.0f} %, Cd = 0.61)"),
            ("Hole velocity",       f"{il['v_hole_ldv_ms']:.3f}  m/s"),
            ("Surge ΔP",            f"{il['dP_surge_Pa']:,.0f}  Pa"),
            ("Surge force",         f"{il['F_baffle_surge_N']:,.0f}  N  (unfactored)"),
            (f"Design force  (SF {il['SF_baffle']:.0f})",
             f"<b>{il['F_baffle_design_N']:,.0f}  N</b>"),
            ("Gas ΔP (operating, ref.)",
             f"{il['dP_gas_op_Pa']:.1f}  Pa"),
            ("Min. plate thickness",
             f"<b>{il['t_baffle_design_mm']:.1f}  mm</b>  "
             f"(calc. {il['t_baffle_min_mm']:.1f} mm; API 12J min 6 mm)"),
            ("Fillet weld throat",
             f"<b>{il['a_weld_design_mm']:.1f}  mm</b>  "
             f"(calc. {il['a_weld_req_mm']:.1f} mm; min 3 mm)  "
             f"·  perimeter {il['L_weld_m']*1000:.0f} mm"),
            ("Material f_d / f_y",
             f"{il['fd_MPa']:.0f} MPa  /  {il['fy_MPa']:.0f} MPa  "
             f"·  τ_allow = 0.4 × f_y = {il['tau_allow_Pa']/1e6:.0f} MPa  "
             "(EN 1993-1-8 / AWS D1.1)"),
        )
        _note = (
            '<p style="font-size:0.82em;color:#64748b;margin-top:6px">'
            'Basis: LDV startup surge (t_flood = '
            f'{il["t_flood_s"]:.0f} s), pure liquid density. '
            'Inlet device: momentum flux. Baffle: perforated-plate ΔP. '
            'Plate: clamped circular plate. Weld: τ = 0.4·f_y. '
            'No standard prescribes this method — verify per project structural code.</p>'
        )
        sec_d1 = _sec(
            "D.1",
            "Internals — Mechanical Loads  (LDV Startup Surge)",
            f'<div style="display:flex;gap:16px;flex-wrap:wrap">'
            f'{_panel("Inlet Device (per inlet)", _inlet_kv)}'
            f'{_panel("Baffle Plate (per baffle, full circumferential weld)", _baffle_kv)}'
            f'</div>'
            f'{_note}',
        )

    # ── D.2  WEIGHT ESTIMATE ─────────────────────────────────────────────────
    sec_d2 = ""
    if weight_result is not None:
        wt = weight_result
        _total = max(wt["m_dry_kg"], 1.0)
        def _wpct(m):
            return f"{m / _total * 100:.1f} %"
        _wt_summary = _kv(
            ("Dry weight",       f"<b>{wt['m_dry_kg']:,.0f}  kg  ({wt['m_dry_kg']/1000:.2f} t)</b>"),
            ("Operating weight", f"<b>{wt['m_operating_kg']:,.0f}  kg  ({wt['m_operating_kg']/1000:.2f} t)</b>"),
            ("Hydrotest weight", f"<b>{wt['m_hydrotest_kg']:,.0f}  kg  ({wt['m_hydrotest_kg']/1000:.2f} t)</b>"),
        )
        _wt_breakdown = _dt(
            ["Component", "Mass (kg)", "% of dry"],
            [
                ["Shell",            f"{wt['m_shell_kg']:,.0f}",    _wpct(wt['m_shell_kg'])],
                [f"Heads × 2",       f"{wt['m_heads_kg']:,.0f}",    _wpct(wt['m_heads_kg'])],
                [f"Nozzles ({len(wt['nozzle_detail'])})",
                                     f"{wt['m_nozzles_kg']:,.0f}",  _wpct(wt['m_nozzles_kg'])],
                ["Saddles × 2",      f"{wt['m_saddles_kg']:,.0f}",  _wpct(wt['m_saddles_kg'])],
                ["Internals",        f"{wt['m_internals_kg']:,.0f}",_wpct(wt['m_internals_kg'])],
                [f"Misc (+{wt['misc_factor']*100:.0f} %)",
                                     f"{wt['m_misc_kg']:,.0f}",     f"{wt['misc_factor']*100:.0f} %"],
                ["<b>Dry total</b>", f"<b>{wt['m_dry_kg']:,.0f}</b>", "<b>100 %</b>"],
            ],
        )
        _wt_note = (
            '<p style="font-size:0.82em;color:#64748b;margin-top:6px">'
            "Estimate ±15–20 %. Shell and heads use nominal wall thickness. "
            "Nozzles = pipe stub (300 mm) + one weld-neck flange each. "
            "Saddles = plate-area estimate. Misc +5 % covers welds, paint, clips.</p>"
        )
        sec_d2 = _sec(
            "D.2", "Weight Estimate",
            f'<div style="display:flex;gap:16px;flex-wrap:wrap">'
            f'{_panel("Summary", _wt_summary)}'
            f'{_panel("Dry Weight Breakdown", _wt_breakdown)}'
            f'</div>'
            f'{_wt_note}',
        )

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

    # Full vessel volume (incl. heads) for % calculation
    V_total = sep_res.V_total_vessel_m3 if sep_res.V_total_vessel_m3 > 0 else 1.0

    # Compute full vessel volumes (cylinder + both endcaps) at each level
    from engines.vessel_volume import vessel_volumes as _vessel_volumes
    from engines.separator_process import _cyl_vol_mm3
    _lvl_tags = [t for t in _order if t in levels_mm]
    if head_type is not None and _lvl_tags:
        _vr = _vessel_volumes(
            head_type, Di, L_shell,
            {t: levels_mm[t] for t in _lvl_tags},
            crown_ratio=crown_ratio, knuckle_ratio=knuckle_ratio,
            alpha_deg_cone=alpha_deg_cone, ellipse_ratio=ellipse_ratio,
            include_heads=True,
        )
        _lvols = {r["tag"]: r["vol_m3"] for r in _vr["levels"]}
    else:
        _lvols = {}

    level_rows = []
    for tag in _order:
        if tag not in levels_mm:
            continue
        h = max(0.0, min(Di, levels_mm[tag]))
        vol = _lvols.get(tag, _cyl_vol_mm3(Di, L_shell, h) * 1e-9)
        vol_pct = vol / max(V_total, 1e-9) * 100
        level_rows.append([
            f"<b>{tag}</b>",
            _desc.get(tag, ""),
            f"{h:.0f}",
            f"{h/Di*100:.0f} %",
            f"{vol:.3f}",
            f"{vol*1000:.0f}",
        ])

    sec_e = _sec("E", "Liquid Levels",
                 _dt(
                     ["Tag", "Description", "Height from bottom  (mm)",
                      "% Di", "Volume  (m³)", "Volume  (L)"],
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

        geom_ok  = nres.geom_ok   if nres else True
        code_ok  = nres.code_ok   if nres else True    # None = needs check
        reinf_ok = rres.adequate  if rres else True
        all_ok   = geom_ok and (code_ok is not False) and fok and (reinf_ok is not False)
        # Downgrade to None (amber) if code zone needs a detailed check
        ok_flag  = None if (all_ok and code_ok is None) else all_ok
        status_s = _status(ok_flag)

        note_parts = []
        if nres is not None:
            note_parts.append(f"Zone: {nres.zone.replace('_', ' ')}")
            if nz.get("loc") in ("Left head", "Right head"):
                nz_IR_g  = (OD - 2*t) / 2.0
                nz_bot_g = (Di - nres.d_from_top_mm) - nz_IR_g
                top_clr_g  = nres.edge_to_shell_mm           # OD top → crown ID
                lzhh_clr_g = nz_bot_g - lzhh_mm              # LZHH → inlet device bottom
                note_parts.append(f"OD top→crown: {top_clr_g:.0f} mm")
                if nz.get("service") == "Inlet":
                    _flag_g = ("✓" if lzhh_clr_g >= 150
                               else ("✗ sub." if lzhh_clr_g < 0 else "⚠ &lt;150mm"))
                    note_parts.append(f"LZHH→inlet bot: {lzhh_clr_g:.0f} mm {_flag_g}")
        notes = "  |  ".join(note_parts)

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
            status_s + (f"  <span style='font-size:8pt;color:#555'>{_e(notes)}</span>" if notes else ""),
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

    # ── G.1  Endcap nozzle analysis ───────────────────────────────────────────
    sec_g1 = ""
    if head_type is not None:
        sec_g1 = _endcap_analysis_html(
            nozzle_results=nozzle_results,
            Di=Di,
            head_type=head_type,
            crown_ratio=crown_ratio,
            knuckle_ratio=knuckle_ratio,
            alpha_deg_cone=alpha_deg_cone,
            ellipse_ratio=ellipse_ratio,
            t_head_nom=head_res.t_nom_mm,
            code_key=code_key,
            h_head=h_head,
            lzhh_mm=lzhh_mm,
        )

    # ── FOOTER ────────────────────────────────────────────────────────────────
    footer = (
        f'<div class="footer">'
        f'Generated by <b>SepScope</b> — Separator scoping for inquiry and FEED · '
        f'{_e(today)} · Rev A · Issued for {_e(issued_for)}<br>'
        f'<b>Screening-level only — not a certified design calculation. '
        f'Independent engineering verification required before use in design or procurement.</b>'
        f'</div>'
    )

    body = (
        header_html + banner + sketch_html
        + sec_a + sec_b + sec_c + sec_d + sec_d1 + sec_d2
        + sec_e + sec_f + sec_g + sec_g1 + sec_h
        + footer
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SepScope — {_e(vessel_tag)}</title>
<style>{_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""
