"""Smoke tests: every chart and map renders from small inputs and carries the footnote."""

import numpy as np
import pandas as pd

from src import viz
from src.config import with_overrides
from src.model import build_and_solve

COMPONENTS = ["primary", "secondary", "space", "handling", "inventory", "fixed"]


def test_every_chart_saves_with_its_footnote(tmp_path):
    k = [1, 2, 3]
    sweep = pd.DataFrame({c: [10.0, 8.0, 9.0] for c in COMPONENTS}, index=k)
    sweep["total"] = sweep.sum(axis=1)
    frontier = pd.DataFrame(
        {
            "radius_km": [300, 300, 400, 400],
            "alpha": [0.8, 0.9, 0.8, 0.9],
            "total": [60, np.nan, 50, 55],
        }
    )
    tornado = pd.DataFrame(
        {
            "label": ["a", "b"],
            "low_total": [48, 49],
            "high_total": [53, 51],
            "low_saving": [5, 6],
            "high_saving": [7, 6],
            "low_dcs": [3, 3],
            "high_dcs": [4, 3],
        }
    )
    figures = {
        "cost_curve": viz.plot_cost_curve(sweep, pd.Series([62.0, 50.0, 56.0], index=k)),
        "frontier": viz.plot_service_frontier(frontier, (400, 0.8, 50.0), (400, 0.9, 55.0)),
        "waterfall": viz.plot_waterfall(
            dict.fromkeys(COMPONENTS, 10.0), dict.fromkeys(COMPONENTS, 9.0)
        ),
        "tornado": viz.plot_tornado(tornado, 50.0, 6.0),
        "robustness": viz.plot_site_robustness(
            pd.DataFrame({"S1": [1, 0], "S2": [1, 1]}, index=["A", "B"]), 1
        ),
        "headroom": viz.plot_rent_headroom(
            pd.DataFrame(
                {"dc_id": ["A", "B"], "rent": [20.0, 18.0], "switch_rent": [30.0, np.nan]}
            ),
            3.0,
        ),
    }
    for name, fig in figures.items():
        viz.save_chart(fig, tmp_path / f"{name}.png", "note", "disclaimer")
        assert (tmp_path / f"{name}.png").stat().st_size > 0
        footnote = fig.texts[-1].get_text()
        assert "note" in footnote and "Hypothetical client" in footnote and "disclaimer" in footnote


def test_network_map_highlights_zones_beyond_the_radius(params, tiny, tmp_path):
    no_target = with_overrides(params, {"service.min_share_within_radius.value": 0.0})
    sol = build_and_solve(no_target, tiny, k=1, forced_open=["D1"])
    fmap = viz.plot_network_map(tiny, sol, 400, 320, "title", "disclaimer")
    fmap.save(tmp_path / "map.html")
    html = (tmp_path / "map.html").read_text()
    assert html.count(viz.SERIES[1]) >= 1  # Z3 is 600 km from D1, so it is highlighted
