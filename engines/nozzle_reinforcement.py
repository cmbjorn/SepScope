"""
Nozzle opening reinforcement check — area replacement method.

Verifies that the material removed by the nozzle bore is compensated by
excess material in the shell/head wall, nozzle wall, and optional pad.

Codes implemented:
  ASME VIII Div.1  UG-36 to UG-42 (2021 edition)
  EN 13445-3:2021  Clause 9.4 (opening in shells and heads)

All dimensions in mm, pressures in MPa, stresses in MPa.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field


@dataclass
class ReinforcementResult:
    """Full area-replacement accounting for one nozzle opening."""
    # Inputs (echo)
    code: str               # "ASME" or "EN"
    d_bore_mm: float        # corroded bore of nozzle (mm)
    t_head_req_mm: float    # required head/shell thickness (mm)
    t_head_nom_mm: float    # actual (nominal) head/shell thickness (mm)
    t_nozzle_mm: float      # nozzle wall thickness (mm)
    t_nozzle_req_mm: float  # required nozzle wall (pressure only) (mm)
    CA_mm: float            # corrosion allowance (mm)

    # Areas (mm²)
    A_required_mm2: float   # area that must be replaced
    A_shell_mm2: float      # area available in shell/head wall (excess)
    A_nozzle_mm2: float     # area available in nozzle wall (excess, within limit zone)
    A_pad_mm2: float        # area available in pad (zero if no pad)
    A_total_mm2: float      # sum of available areas
    A_deficit_mm2: float    # A_required − A_total  (positive → reinforcement needed)

    # Pad sizing (filled when pad is required)
    pad_required: bool
    pad_width_mm: float | None = None     # half-width of pad (radial extent, each side)
    pad_thickness_mm: float | None = None # pad thickness used (= t_head_nom typically)

    # Code references
    clause: str = ""
    formula_notes: str = ""

    adequate: bool = False  # True if A_total ≥ A_required
    warnings: list[str] = field(default_factory=list)


def reinforcement_check(
    Di: float,
    P_barg: float,
    fd_MPa: float,
    nozzle_OD_mm: float,
    nozzle_t_mm: float,
    t_head_req_mm: float,
    t_head_nom_mm: float,
    CA_mm: float = 3.0,
    code: str = "EN",
    z: float = 1.0,
    pad_thickness_mm: float | None = None,
    nozzle_h_above_mm: float | None = None,  # nozzle projection above OD surface (outward)
    nozzle_h_below_mm: float | None = None,  # nozzle projection below ID surface (inward)
    space_to_wall_mm: float | None = None,    # clearance from nozzle OD edge to vessel wall
    space_to_knuckle_mm: float | None = None, # clearance from nozzle OD edge to knuckle zone
) -> ReinforcementResult:
    """
    Area-replacement reinforcement check for a radial nozzle on a curved head.

    Parameters
    ----------
    Di              : vessel inner diameter (mm)
    P_barg          : design pressure (barg)
    fd_MPa          : allowable design stress of shell/head material (MPa)
    nozzle_OD_mm    : nozzle outer diameter (mm)
    nozzle_t_mm     : nozzle wall thickness as supplied (mm)
    t_head_req_mm   : required minimum head thickness (mm) — from head_thickness()
    t_head_nom_mm   : nominal (actual) head thickness selected (mm)
    CA_mm           : corrosion allowance (mm)
    code            : "ASME" or "EN"
    z               : weld joint efficiency (default 1.0)
    pad_thickness_mm: pad thickness to try; if None, uses t_head_nom
    nozzle_h_above_mm: outward projection of nozzle above head OD surface (mm).
                       If None, assumed = 2.5 × t_head_nom (common minimum).
    nozzle_h_below_mm: inward projection below head ID surface (mm); 0 for flush.
    """
    P = P_barg * 0.1   # bar → MPa
    warnings: list[str] = []

    # Corroded nozzle bore
    d_bore = nozzle_OD_mm - 2 * (nozzle_t_mm - CA_mm)
    if d_bore <= 0:
        d_bore = nozzle_OD_mm - 2 * nozzle_t_mm   # fall back (no CA on nozzle)
        warnings.append("Corrosion-corrected nozzle bore is non-positive; CA not applied to nozzle.")

    # Required nozzle wall (pressure in nozzle bore, ASME UG-45 / EN cl.9)
    # Use simple cylinder formula for the nozzle tube itself
    d_nozzle_ID = nozzle_OD_mm - 2 * nozzle_t_mm
    r_n = d_nozzle_ID / 2
    if code == "ASME":
        t_nr = P * r_n / (fd_MPa * z - 0.6 * P) if (fd_MPa * z - 0.6 * P) > 0 else 0.0
        clause = "ASME VIII-1 UG-37 / UG-41"
    else:
        t_nr = P * d_nozzle_ID / (2 * fd_MPa * z - P) if (2 * fd_MPa * z - P) > 0 else 0.0
        clause = "EN 13445-3 cl. 9.4"

    t_nozzle_corroded = nozzle_t_mm - CA_mm
    t_head_corroded_nom = t_head_nom_mm - CA_mm

    # ── Required area ─────────────────────────────────────────────────────────
    #  Both ASME UG-37 and EN cl. 9.4 use: A_req = d_bore × e_req (for F=1)
    A_required = d_bore * t_head_req_mm

    # ── Area in shell/head (excess wall beyond required) ─────────────────────
    # A_1 = (t_head_corroded_nom − t_head_req) × d_bore
    A_shell = max(0.0, (t_head_corroded_nom - t_head_req_mm) * d_bore)

    # ── Area in nozzle wall (within the limit zone h_1) ──────────────────────
    # Limit height in the nozzle: smaller of 2.5·t_head or 2.5·t_nozzle (ASME UG-37)
    # EN cl.9.4: l_b = min(1.5·sqrt(d_bore·t_nozzle), actual outward projection)
    if nozzle_h_above_mm is None:
        nozzle_h_above_mm = 2.5 * t_head_corroded_nom

    if code == "ASME":
        h1 = min(2.5 * t_head_corroded_nom,
                 2.5 * t_nozzle_corroded,
                 nozzle_h_above_mm)
        # ASME: also include inward projection
        h2 = min(nozzle_h_below_mm if nozzle_h_below_mm else 0.0,
                 2.5 * t_nozzle_corroded)
        A_nozzle = 2 * max(0.0, t_nozzle_corroded - t_nr) * (h1 + h2)
    else:
        # EN cl.9.4.3: l_b = min(1.5·sqrt(d_bore·t_nozzle_corroded), outward proj)
        l_b = min(1.5 * math.sqrt(max(0.0, d_bore * t_nozzle_corroded)),
                  nozzle_h_above_mm)
        A_nozzle = 2 * max(0.0, t_nozzle_corroded - t_nr) * l_b

    # ── Area in pad ───────────────────────────────────────────────────────────
    # Attempt with pad_thickness = t_head_nom if not specified; compute required width.
    if pad_thickness_mm is None:
        pad_thickness_mm = t_head_nom_mm

    # First check without any pad
    A_total_no_pad = A_shell + A_nozzle
    A_deficit_no_pad = A_required - A_total_no_pad

    # Determine if a pad is needed and size it
    if A_deficit_no_pad <= 0:
        A_pad = 0.0
        pad_required = False
        pad_width = None
        pad_used_t = None
    else:
        pad_required = True
        # Required pad half-width (each side of bore, in the plane of the head)
        # Limit: pad must not extend beyond 2×t_head from nozzle OD
        # A_pad = 2 × pad_width × pad_thickness
        # ASME: pad OD ≤ nozzle_OD + 2×t_head_nom (limit zone)
        # EN: pad effective width ≤ 0.5·Di (conservative)
        pad_width_needed = A_deficit_no_pad / (2 * pad_thickness_mm)
        # Clamp to sensible maximum
        pad_width_max = min(d_bore, 0.5 * Di - d_bore / 2 - nozzle_OD_mm / 2)
        if pad_width_needed > pad_width_max:
            warnings.append(
                f"Required pad width ({pad_width_needed:.0f} mm each side) exceeds "
                f"practical maximum ({pad_width_max:.0f} mm). Consider thicker head, "
                "larger nozzle wall, or material upgrade.")
            pad_width = pad_width_max
        else:
            pad_width = pad_width_needed
        pad_used_t = pad_thickness_mm
        A_pad = 2 * pad_width * pad_used_t

    A_total = A_shell + A_nozzle + A_pad
    A_deficit = A_required - A_total
    adequate = A_deficit <= 0

    # ── Pad physical feasibility ──────────────────────────────────────────────
    # A computed pad width only helps if the pad physically fits on the head.
    if pad_required and pad_width is not None:
        # Check 1: pad outer edge vs vessel wall
        if space_to_wall_mm is not None and pad_width > space_to_wall_mm:
            warnings.append(
                f"Pad cannot fit: required half-width {pad_width:.0f} mm "
                f"exceeds available space to vessel wall {space_to_wall_mm:.0f} mm. "
                "The pad would collide with the head–shell circumferential seam weld. "
                "Options: increase head/nozzle wall thickness, move nozzle toward axis, "
                "use a smaller DN, or use an insert plate with specialist analysis.")
            adequate = False

        # Check 2: pad outer edge vs knuckle zone (torispherical heads)
        if space_to_knuckle_mm is not None:
            if space_to_knuckle_mm < 0:
                # Nozzle OD edge already overlaps the knuckle zone —
                # the area-replacement method is entirely invalid here.
                warnings.append(
                    f"Nozzle OD extends {-space_to_knuckle_mm:.0f} mm into the knuckle "
                    "transition zone. The area-replacement method (EN cl. 9 / ASME UG-37) "
                    "is not valid in the knuckle and cannot be applied. "
                    "Use a smaller nozzle, move the nozzle toward the vessel axis, "
                    "or use FEA / specialist analysis.")
                adequate = False
            elif pad_width > space_to_knuckle_mm:
                overlap = pad_width - space_to_knuckle_mm
                warnings.append(
                    f"Pad outer edge extends {overlap:.0f} mm into the knuckle transition "
                    "zone. The area-replacement method (EN cl. 9 / ASME UG-37) is not valid "
                    "in the knuckle — the pad area credit cannot be claimed there. "
                    "FEA or specialist analysis required.")
                adequate = False

    # Warnings
    if t_head_corroded_nom <= t_head_req_mm:
        warnings.append(
            "Nominal head thickness equals or is less than required — "
            "no shell area contribution to reinforcement.")
    if t_nozzle_corroded <= t_nr:
        warnings.append(
            "Nozzle wall thickness is minimal — no nozzle area contribution.")

    formula_notes = (
        f"A_req = d_bore × e_req = {d_bore:.1f} × {t_head_req_mm:.2f} = {A_required:.0f} mm²\n"
        f"A_shell = (t_nom_c − e_req) × d_bore = "
        f"({t_head_corroded_nom:.2f} − {t_head_req_mm:.2f}) × {d_bore:.1f} = {A_shell:.0f} mm²\n"
        f"A_nozzle = {A_nozzle:.0f} mm²\n"
        f"A_pad = {A_pad:.0f} mm²  (pad width = "
        f"{pad_width:.0f} mm × 2, t_pad = {pad_used_t:.0f} mm)"
        if pad_required else
        f"A_req = d_bore × e_req = {d_bore:.1f} × {t_head_req_mm:.2f} = {A_required:.0f} mm²\n"
        f"A_shell = {A_shell:.0f} mm²   A_nozzle = {A_nozzle:.0f} mm²   (no pad required)"
    )

    return ReinforcementResult(
        code=code,
        d_bore_mm=round(d_bore, 1),
        t_head_req_mm=round(t_head_req_mm, 3),
        t_head_nom_mm=t_head_nom_mm,
        t_nozzle_mm=nozzle_t_mm,
        t_nozzle_req_mm=round(t_nr, 3),
        CA_mm=CA_mm,
        A_required_mm2=round(A_required, 0),
        A_shell_mm2=round(A_shell, 0),
        A_nozzle_mm2=round(A_nozzle, 0),
        A_pad_mm2=round(A_pad, 0),
        A_total_mm2=round(A_total, 0),
        A_deficit_mm2=round(A_deficit, 0),
        pad_required=pad_required,
        pad_width_mm=round(pad_width, 0) if pad_width is not None else None,
        pad_thickness_mm=round(pad_used_t, 0) if pad_used_t is not None else None,
        clause=clause,
        formula_notes=formula_notes,
        adequate=adequate,
        warnings=warnings,
    )


# Schedule order — lightest to heaviest
_SCHEDULE_ORDER = ["Sch 10S", "Sch 40", "Sch 80", "Sch 160", "XXH"]


def suggest_schedule_upgrade(
    Di: float,
    P_barg: float,
    fd_MPa: float,
    nozzle_OD_mm: float,
    current_schedule: str,
    nozzle_dn: int,
    t_req_mm: float,
    t_nom_mm: float,
    CA_mm: float = 3.0,
    code: str = "EN",
    z: float = 1.0,
    space_to_wall_mm: float | None = None,
    space_to_knuckle_mm: float | None = None,
) -> str | None:
    """
    When reinforcement fails for the current schedule, find the lightest
    heavier schedule that makes it adequate without a pad.

    Returns:
      None                  — already adequate (no action needed)
      "Sch 80"  (or other) — upgrade to this schedule, no pad needed
      "Pad required"        — no schedule upgrade fixes it; pad needed
    """
    from engines.nozzle_geometry import NOZZLE_WALL_SCH, NOZZLE_WALL_T

    current_t = float(NOZZLE_WALL_SCH.get(current_schedule, {}).get(
        nozzle_dn, NOZZLE_WALL_T.get(nozzle_dn, 8.0)))

    # Check whether current schedule is already adequate
    rres = reinforcement_check(
        Di=Di, P_barg=P_barg, fd_MPa=fd_MPa,
        nozzle_OD_mm=nozzle_OD_mm, nozzle_t_mm=current_t,
        t_head_req_mm=t_req_mm, t_head_nom_mm=t_nom_mm,
        CA_mm=CA_mm, code=code, z=z,
        space_to_wall_mm=space_to_wall_mm,
        space_to_knuckle_mm=space_to_knuckle_mm,
    )
    if rres.adequate:
        return None

    # Try each heavier schedule
    try:
        start = _SCHEDULE_ORDER.index(current_schedule) + 1
    except ValueError:
        start = 1

    for sched in _SCHEDULE_ORDER[start:]:
        t_try = float(NOZZLE_WALL_SCH.get(sched, {}).get(
            nozzle_dn, NOZZLE_WALL_T.get(nozzle_dn, 8.0)))
        if t_try <= current_t:
            continue  # schedule exists but no thicker wall for this DN
        r = reinforcement_check(
            Di=Di, P_barg=P_barg, fd_MPa=fd_MPa,
            nozzle_OD_mm=nozzle_OD_mm, nozzle_t_mm=t_try,
            t_head_req_mm=t_req_mm, t_head_nom_mm=t_nom_mm,
            CA_mm=CA_mm, code=code, z=z,
            space_to_wall_mm=space_to_wall_mm,
            space_to_knuckle_mm=space_to_knuckle_mm,
        )
        if r.adequate:
            return sched

    return "Pad required"
