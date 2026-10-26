import numpy as np
import pandas as pd
import pytest

from src.robustness import comparable_service_alpha, knee_alpha, site_robustness, upgrade_options


def test_knee_is_the_point_furthest_below_the_chord():
    # Flat to 80%, then steep: the knee is 80%. Infeasible cells are ignored.
    curve = pd.DataFrame(
        {"alpha": [0.70, 0.75, 0.80, 0.85, 0.90, 0.95], "total": [100, 101, 102, 110, 125, np.nan]}
    )
    assert knee_alpha(curve) == 0.80


def test_robustness_core_and_swing_come_from_classifying_runs_only():
    classify = {"S3_rec": ("A", "B", "C"), "S4_x": ("A", "B", "C"), "S6_x": ("A", "B", "D")}
    context = {"S1": ("A",), "S3_rec": ("A", "B", "C")}  # a repeat column is shown once
    r = site_robustness(classify, context)
    assert r["core"] == ["A", "B"]  # open in the recommended network and every stress run
    assert r["swing"] == ["C", "D"]
    assert list(r["matrix"].columns) == ["S3_rec", "S4_x", "S6_x", "S1"]
    assert r["stress_scenarios"] == ["S3_rec", "S4_x", "S6_x"]


def test_recommended_target_is_the_highest_one_today_already_meets():
    alphas = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
    assert comparable_service_alpha(alphas, 0.814) == 0.80  # as-is 81.4% next-day
    assert comparable_service_alpha(alphas, 0.85) == 0.85  # meeting a target exactly counts
    with pytest.raises(ValueError, match="No frontier target"):
        comparable_service_alpha(alphas, 0.60)


def test_upgrade_options_price_each_higher_target_against_the_recommended_network():
    curve = pd.DataFrame(
        {
            "scenario_id": ["a75", "a80", "a85", "a90"],
            "alpha": [0.75, 0.80, 0.85, 0.90],
            "total_inr": [95.0, 100.0, 104.0, np.nan],  # 90% infeasible: no option
            "open_dcs": [("A",), ("A", "B"), ("A", "B", "C", "D"), ()],
        }
    )
    options = upgrade_options(curve, 0.80)
    assert options["scenario_id"].tolist() == ["a85"]
    row = options.iloc[0]
    assert (row["extra_dcs"], row["extra_cost_inr"], row["extra_points"]) == (
        2,
        4.0,
        pytest.approx(5),
    )
    assert (row["added"], row["dropped"]) == (["C", "D"], [])
