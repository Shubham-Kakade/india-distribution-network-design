"""Scenario building blocks on the tiny network in conftest.py."""

import pytest

from src.config import with_overrides
from src.model import Solution, build_and_solve
from src.scenarios import (
    Run,
    grown_demand,
    open_sets,
    rent_switching_points,
    s5_disruption,
    with_rents,
)


def fake_run(scenario_id: str, open_dcs: tuple[str, ...], feasible: bool = True) -> Run:
    cost = object() if feasible else None  # only "is the scenario feasible" is read
    sol = Solution("x", None, None, None, 0.0, open_dcs, None, None, cost, None)
    return Run(scenario_id, scenario_id[:2], "q", {}, sol)


def test_with_rents_scales_only_the_named_sites(tiny):
    out = with_rents(tiny, {"D2": 1.5})
    rents = out.dcs.set_index("dc_id")["rent_inr_sqft_month"]
    assert rents.to_dict() == {"D1": 20.0, "D2": 45.0, "D3": 25.0}
    assert tiny.dcs["rent_inr_sqft_month"].tolist() == [20.0, 30.0, 25.0]  # input untouched


def test_regional_growth_follows_the_state_lists(params, tiny):
    # Z1, Z2 are Maharashtra (Rest), Z3 is Gujarat (Rest) unless Gujarat is put in the East
    east = with_overrides(params, {"scenarios.demand_growth.regions.East": ["Gujarat"]})
    grown, ratio = grown_demand(tiny, east, "regional_skew")
    skew = params["scenarios"]["demand_growth"]["regional_skew"]
    expected = [
        30_000 * (1 + skew["Rest"]),
        60_000 * (1 + skew["Rest"]),
        90_000 * (1 + skew["East"]),
    ]
    assert grown.zones["demand_t_yr"].tolist() == pytest.approx(expected)
    assert ratio == pytest.approx(sum(expected) / 180_000)
    uniform, _ = grown_demand(tiny, params, "uniform")
    assert uniform.zones["demand_t_yr"].sum() == pytest.approx(
        180_000 * (1 + params["scenarios"]["demand_growth"]["uniform"])
    )


def test_open_sets_keep_feasible_runs_in_order():
    runs = [
        fake_run("S4_x", ("A", "B")),
        fake_run("S3_bad", (), feasible=False),
        fake_run("S1", ("A",)),
    ]
    assert open_sets(runs) == {"S4_x": ("A", "B"), "S1": ("A",)}


def test_operational_outage_keeps_the_open_set_and_charges_freight_for_the_months(params, tiny):
    rec_sol = build_and_solve(params, tiny, k=2)
    rec = Run("REC", "S3", "q", {}, rec_sol)
    s5a, s5b = s5_disruption(params, tiny, rec)
    closed = s5a.extra["closed_dc"]
    assert closed in rec_sol.open_dcs
    assert set(s5a.solution.open_dcs) == set(rec_sol.open_dcs) - {closed}
    freight = lambda s: s.cost.primary_inr + s.cost.secondary_inr  # noqa: E731
    months = params["scenarios"]["disruption_months"]
    assert s5a.extra["outage_cost_cr"] == pytest.approx(
        (freight(s5a.solution) - freight(rec_sol)) * months / 12 / params["meta"]["crore"]
    )
    assert closed not in s5b.solution.open_dcs


def test_switching_rent_is_above_todays_rent_or_beyond_the_search(params, tiny):
    rec = Run("REC", "S3", "q", {}, build_and_solve(params, tiny, k=2))
    headroom = rent_switching_points(params, tiny, rec).set_index("dc_id")
    assert set(headroom.index) == set(rec.solution.open_dcs)
    found = headroom["switch_rent"].dropna()
    assert (found > headroom.loc[found.index, "rent"]).all()
