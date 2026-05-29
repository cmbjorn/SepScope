"""
Cylindrical shell thickness per EN 13445-3 cl. 7.3 and ASME VIII-1 UG-27.
All dimensions in mm, pressures in barg (→ MPa internally).
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field


@dataclass
class ShellThicknessResult:
    Di: float
    P_MPa: float
    fd_MPa: float
    z: float
    code: str
    t_calc_mm: float
    t_nom_mm: float
    CA_mm: float
    clause: str
    formula: str
    warnings: list[str] = field(default_factory=list)


def shell_thickness(
    Di: float,
    P_barg: float,
    fd_MPa: float,
    z: float = 1.0,
    CA_mm: float = 3.0,
    code: str = "EN",
) -> ShellThicknessResult:
    """
    Minimum cylindrical shell wall thickness.

    Parameters
    ----------
    Di      : inside diameter (mm)
    P_barg  : design pressure (barg)
    fd_MPa  : allowable design stress (MPa)
    z       : weld joint efficiency factor (1.0 = full RT)
    CA_mm   : corrosion allowance (mm)
    code    : "EN" or "ASME"
    """
    P = P_barg * 0.1   # bar → MPa
    warnings: list[str] = []

    if code == "ASME":
        # UG-27(c)(1): t = P*R / (S*E - 0.6*P), R = Di/2
        R = Di / 2
        t = P * R / (fd_MPa * z - 0.6 * P)
        clause  = "ASME VIII-1 UG-27(c)(1)"
        formula = (f"t = P·R / (S·E − 0.6·P) = "
                   f"{P:.4f}·{R:.1f} / ({fd_MPa:.2f}·{z:.2f} − 0.6·{P:.4f})")
    else:
        # EN 13445-3 cl. 7.3.1: e = P*Di / (2*fd*z - P)
        t = P * Di / (2 * fd_MPa * z - P)
        clause  = "EN 13445-3 cl. 7.3.1"
        formula = (f"e = P·Di / (2·fd·z − P) = "
                   f"{P:.4f}·{Di:.1f} / (2·{fd_MPa:.2f}·{z:.2f} − {P:.4f})")

    if t <= 0:
        warnings.append("Calculated thickness is non-positive. Check inputs.")
    if P >= fd_MPa * z:
        warnings.append("P ≥ fd·z — thin-wall formula is at its limit.")

    t_nom = math.ceil((t + CA_mm) * 2) / 2

    return ShellThicknessResult(
        Di=Di, P_MPa=P, fd_MPa=fd_MPa, z=z, code=code,
        t_calc_mm=round(t, 3), t_nom_mm=t_nom,
        CA_mm=CA_mm, clause=clause, formula=formula, warnings=warnings,
    )
