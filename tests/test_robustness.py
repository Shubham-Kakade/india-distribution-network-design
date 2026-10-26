import numpy as np
import pandas as pd

from src.robustness import knee_alpha, site_robustness


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
