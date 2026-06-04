"""
Inlet device sizing — API 12J §5.3 criteria.

Three device types:
  Half-pipe diverter          — API 12J §5.3.1
  Slotted/perforated cylinder — API 12J §5.3.2
  Vane distributor            — vendor-sized; no formula

Criteria applied
----------------
1. Device opening area ≥ 2 × inlet nozzle bore area  (API 12J §5.3)
2. ρv² at device face ≤ service limit                (API 12J / GPSA)
   Non-foaming / clean           8 000 Pa
   Slightly foaming or dirty     4 000 Pa
   Moderately foaming            4 000 Pa
   Severely foaming              2 400 Pa
3. Half-pipe OD ≥ 1.5 × nozzle OD                   (API 12J §5.3.1)
4. Cylinder OD ≥ 1.5 × nozzle OD                    (API 12J §5.3.2)

All dimensions in mm, areas in m², velocities in m/s, pressures in Pa.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field


# ρv² service limits (Pa) keyed by service condition label
RV2_LIMITS: dict[str, float] = {
    "Non-foaming / clean":       8_000.0,
    "Slightly foaming or dirty": 4_000.0,
    "Moderately foaming":        4_000.0,
    "Severely foaming":          2_400.0,
}

# Standard pipe ODs (mm) — ISO 4200 / ASME B36.10M, ascending
_PIPE_ODS: list[float] = [
    21.3, 26.9, 33.7, 42.4, 48.3, 60.3, 76.1, 88.9, 114.3, 139.7,
    168.3, 219.1, 273.1, 323.9, 355.6, 406.4, 457.0, 508.0,
    609.6, 711.0, 812.8, 914.0, 1016.0,
]


def _next_pipe_od(min_od_mm: float) -> float:
    """Return the smallest standard pipe OD ≥ min_od_mm."""
    for od in _PIPE_ODS:
        if od >= min_od_mm:
            return od
    return math.ceil(min_od_mm / 50) * 50.0  # fallback: round up to 50 mm


def _ceil50(mm: float) -> float:
    """Round up to next 50 mm."""
    return math.ceil(mm / 50.0) * 50.0


@dataclass
class InletDeviceSizing:
    device_type: str               # "Half-pipe diverter" | "Slotted/perforated cylinder" | "Vane distributor"
    svc_condition: str
    rv2_limit_Pa: float            # service ρv² limit at device face

    # Nozzle reference
    nozzle_OD_mm: float
    nozzle_ID_mm: float
    A_nozzle_m2: float             # bore area of inlet nozzle
    v_nozzle_ms: float             # mixture velocity in nozzle bore
    rv2_nozzle_Pa: float           # ρv² in nozzle bore

    # Device dimensions
    D_device_mm: float             # half-pipe or cylinder OD
    L_device_mm: float             # device length

    # Opening area
    A_opening_m2: float            # half-pipe face OR total slot area
    area_ratio: float              # A_opening / A_nozzle  (should be ≥ 2)
    area_api_ok: bool              # area_ratio ≥ 2

    # Velocity at device opening
    v_face_ms: float
    rv2_face_Pa: float
    rv2_face_ok: bool              # rv2_face ≤ rv2_limit

    # Perforated cylinder extras (None for half-pipe / vane)
    A_slot_mm2: float | None = None
    n_holes_dn25: int | None = None   # indicative hole count using DN25 holes

    adequate: bool = False
    notes: list[str] = field(default_factory=list)


def size_inlet_device(
    device_type: str,
    Q_mix_m3h_per_inlet: float,   # total volumetric flow (gas+liq) per inlet nozzle
    rho_mix_kgm3: float,
    nozzle_OD_mm: float,
    nozzle_ID_mm: float,
    svc_condition: str = "Non-foaming / clean",
) -> InletDeviceSizing | None:
    """
    Size one inlet device.  Returns None for "None" or "Vane distributor".
    """
    if device_type in ("None", "Vane distributor (vendor-sized)"):
        return None

    Q_m3s = Q_mix_m3h_per_inlet / 3600.0
    A_nozzle = math.pi * (nozzle_ID_mm * 1e-3) ** 2 / 4.0
    v_nozzle = Q_m3s / max(A_nozzle, 1e-9)
    rv2_nozzle = rho_mix_kgm3 * v_nozzle ** 2

    rv2_limit = RV2_LIMITS.get(svc_condition, 8_000.0)
    v_face_max = math.sqrt(rv2_limit / max(rho_mix_kgm3, 0.001))
    A_min_rv2  = Q_m3s / max(v_face_max, 1e-9)
    A_min_api  = 2.0 * A_nozzle                       # API 12J §5.3 minimum

    if device_type == "Half-pipe diverter":
        # ── OD ────────────────────────────────────────────────────────────────
        D_hp = _next_pipe_od(1.5 * nozzle_OD_mm)

        # ── Length: from ρv² criterion, API 2× area rule, and practical min ──
        # Face area = D_hp × L_hp  (rectangular projected face)
        L_from_rv2  = A_min_rv2 / (D_hp * 1e-3)
        L_from_api  = A_min_api / (D_hp * 1e-3)
        L_from_prac = 2.0 * nozzle_OD_mm * 1e-3       # ≥ 2 × nozzle OD
        L_hp = _ceil50(max(L_from_rv2, L_from_api, L_from_prac) * 1000.0)

        A_face = (D_hp * 1e-3) * (L_hp * 1e-3)
        v_face = Q_m3s / max(A_face, 1e-9)
        rv2_face = rho_mix_kgm3 * v_face ** 2

        area_ratio = A_face / max(A_nozzle, 1e-9)
        area_ok    = area_ratio >= 2.0
        rv2_ok     = rv2_face <= rv2_limit

        notes: list[str] = []
        if not area_ok:
            notes.append(f"Face area {A_face*1e4:.0f} cm² < 2 × nozzle area {A_nozzle*1e4:.0f} cm² — increase L or OD.")
        if not rv2_ok:
            notes.append(f"ρv²_face {rv2_face:.0f} Pa exceeds {rv2_limit:.0f} Pa limit.")

        return InletDeviceSizing(
            device_type=device_type,
            svc_condition=svc_condition,
            rv2_limit_Pa=rv2_limit,
            nozzle_OD_mm=nozzle_OD_mm,
            nozzle_ID_mm=nozzle_ID_mm,
            A_nozzle_m2=A_nozzle,
            v_nozzle_ms=v_nozzle,
            rv2_nozzle_Pa=rv2_nozzle,
            D_device_mm=D_hp,
            L_device_mm=L_hp,
            A_opening_m2=A_face,
            area_ratio=area_ratio,
            area_api_ok=area_ok,
            v_face_ms=v_face,
            rv2_face_Pa=rv2_face,
            rv2_face_ok=rv2_ok,
            adequate=(area_ok and rv2_ok),
            notes=notes,
        )

    elif device_type == "Slotted/perforated cylinder":
        # ── Cylinder OD ───────────────────────────────────────────────────────
        D_cyl = _next_pipe_od(1.5 * nozzle_OD_mm)

        # ── Length: ≥ 4 × nozzle OD, round up ────────────────────────────────
        L_cyl = _ceil50(max(4.0 * nozzle_OD_mm, 300.0))

        # ── Total slot area ───────────────────────────────────────────────────
        A_slot = max(A_min_rv2, A_min_api)
        A_slot_mm2 = math.ceil(A_slot * 1e6 / 100.0) * 100.0   # round to 100 mm²

        # Indicative hole count (DN25 = 25 mm diameter holes, ~491 mm² each)
        hole_area_mm2 = math.pi * (25 / 2) ** 2
        n_holes = math.ceil(A_slot_mm2 / hole_area_mm2)

        A_slot_actual = A_slot_mm2 * 1e-6
        v_slot = Q_m3s / max(A_slot_actual, 1e-9)
        rv2_slot = rho_mix_kgm3 * v_slot ** 2

        area_ratio = A_slot_actual / max(A_nozzle, 1e-9)
        area_ok    = area_ratio >= 2.0
        rv2_ok     = rv2_slot <= rv2_limit

        notes_c: list[str] = []
        if not area_ok:
            notes_c.append(f"Slot area {A_slot_mm2:.0f} mm² < 2 × nozzle area — increase hole count.")
        if not rv2_ok:
            notes_c.append(f"ρv²_slot {rv2_slot:.0f} Pa exceeds {rv2_limit:.0f} Pa limit.")

        return InletDeviceSizing(
            device_type=device_type,
            svc_condition=svc_condition,
            rv2_limit_Pa=rv2_limit,
            nozzle_OD_mm=nozzle_OD_mm,
            nozzle_ID_mm=nozzle_ID_mm,
            A_nozzle_m2=A_nozzle,
            v_nozzle_ms=v_nozzle,
            rv2_nozzle_Pa=rv2_nozzle,
            D_device_mm=D_cyl,
            L_device_mm=L_cyl,
            A_opening_m2=A_slot_actual,
            area_ratio=area_ratio,
            area_api_ok=area_ok,
            A_slot_mm2=A_slot_mm2,
            n_holes_dn25=n_holes,
            v_face_ms=v_slot,
            rv2_face_Pa=rv2_slot,
            rv2_face_ok=rv2_ok,
            adequate=(area_ok and rv2_ok),
            notes=notes_c,
        )

    return None
