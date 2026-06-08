"""Quick checks for the saddle height engine. Run: python test_saddle.py"""
from engines import saddle_height

NZ = [
    {"tag": "LO", "service": "Liquid outlet", "loc": "Shell — bottom", "dn": 250},
    {"tag": "D1", "service": "Drain", "loc": "Shell — bottom", "dn": 50},
    {"tag": "GO", "service": "Gas outlet", "loc": "Shell — top", "dn": 150},
]

WT = {"m_dry_kg": 5732, "m_operating_kg": 12624, "m_hydrotest_kg": 25208}


def test_zick_reaction_is_half_hydrotest_weight():
    r = saddle_height(1800, 12.5, NZ, "Clear bottom nozzles", weight_result=WT, saddle_w_mm=300)
    z = r["zick"]
    assert abs(z["Q_per_saddle_N"] - WT["m_hydrotest_kg"] * 9.81 / 2.0) < 1.0
    assert abs(z["W_hydrotest_N"] - WT["m_hydrotest_kg"] * 9.81) < 1.0


def test_baseplate_thickens_with_load_and_low_bearing():
    light = saddle_height(1800, 12.5, NZ, "Minimum (structural)",
                          weight_result={"m_hydrotest_kg": 10000}, saddle_w_mm=300)
    heavy = saddle_height(1800, 12.5, NZ, "Minimum (structural)",
                          weight_result={"m_hydrotest_kg": 60000}, saddle_w_mm=300)
    assert heavy["t_base_mm"] > light["t_base_mm"]            # plate scales with load


def test_soft_foundation_fails_bearing_and_warns():
    r = saddle_height(1800, 12.5, NZ, "Clear bottom nozzles",
                      weight_result=WT, saddle_w_mm=300, bearing_pressure_MPa=0.2)
    assert r["zick"]["bearing_ok"] is False
    assert any("bearing" in w.lower() for w in r["warnings"])


def test_zick_firms_baseplate_vs_rule_of_thumb():
    rule = saddle_height(1800, 12.5, NZ, "Minimum (structural)")            # no weight
    zick = saddle_height(1800, 12.5, NZ, "Minimum (structural)", weight_result=WT, saddle_w_mm=300)
    assert rule["zick"] is None
    assert zick["zick"] is not None
    # load-derived baseplate is firmer (thicker) than the 0.007·Di rule
    assert zick["t_base_mm"] >= rule["t_base_mm"]


def test_overall_height_decomposition():
    r = saddle_height(1800, 12.5, NZ, "Clear bottom nozzles")
    assert abs(r["overall_height_mm"] - (r["Do_mm"] + r["h_stand_mm"] + r["t_base_mm"])) < 1e-6
    assert r["Do_mm"] == 1800 + 2 * 12.5


def test_minimum_is_lower_and_warns_with_bottom_nozzles():
    clear = saddle_height(1800, 12.5, NZ, "Clear bottom nozzles")
    minimum = saddle_height(1800, 12.5, NZ, "Minimum (structural)")
    assert minimum["h_stand_mm"] < clear["h_stand_mm"]            # minimising works
    assert minimum["overall_height_mm"] < clear["overall_height_mm"]
    assert minimum["warnings"]                                    # relocate warning


def test_clear_governed_by_bottom_nozzle():
    r = saddle_height(1800, 12.5, NZ, "Clear bottom nozzles")
    assert r["governing"] == "Bottom-nozzle clearance"
    assert r["h_clear_mm"] > 0 and not r["warnings"]


def test_no_bottom_nozzles_uses_structural():
    top_only = [{"tag": "GO", "loc": "Shell — top", "dn": 150}]
    r = saddle_height(1800, 12.5, top_only, "Clear bottom nozzles")
    assert r["h_clear_mm"] == 0.0
    assert r["governing"] == "Structural minimum"


def test_custom_below_required_warns():
    r = saddle_height(1800, 12.5, NZ, "Custom", custom_height_mm=120.0)
    assert r["h_stand_mm"] == 120.0
    assert any("structural" in w.lower() for w in r["warnings"])
    assert any("clearance" in w.lower() for w in r["warnings"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} checks passed.")
