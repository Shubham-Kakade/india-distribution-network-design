"""Model invariants (spec §11) on the tiny network in conftest.py; full India runs are slow."""

import dataclasses

import pandas as pd
import pytest

from src import model
from src.config import with_overrides
from src.costs import evaluate_network
from src.model import Solution, build_and_solve, dc_capacity_t_yr

OPTIMAL = "Optimal Solution Found"


def no_service_target(params: dict) -> dict:
    return with_overrides(params, {"service.min_share_within_radius.value": 0.0})


def test_every_zone_assigned_once_and_only_to_an_open_dc(params, tiny):
    sol = build_and_solve(params, tiny, k=2)
    assert sol.status == OPTIMAL
    assert sorted(sol.assignment.index) == ["Z1", "Z2", "Z3"]
    assert sol.assignment.index.is_unique
    assert set(sol.assignment) <= set(sol.open_dcs)


def test_flow_balance_at_every_dc_and_plant_capacity(params, tiny):
    sol = build_and_solve(params, tiny, k=2)
    demand = tiny.zones.set_index("zone_id")["demand_t_yr"]
    throughput = demand.groupby(sol.assignment).sum()
    inflow = sol.flows.groupby("dc_id")["flow_t_yr"].sum()
    pd.testing.assert_series_equal(
        inflow.sort_index(), throughput.sort_index(), check_names=False, rtol=1e-6
    )
    headroom = params["plants"]["capacity_headroom"]["value"]
    share = tiny.plants.set_index("plant_id")["share_frac"]
    out = sol.flows.groupby("plant_id")["flow_t_yr"].sum()
    assert (out <= share[out.index] * demand.sum() * headroom + 1e-6).all()


def test_evaluator_same_for_milp_solution_and_rebuilt_assignment(params, tiny):
    sol = build_and_solve(params, tiny, k=2)
    # The same assignment typed out again, in a different order and as plain Python data
    rebuilt = pd.Series(dict(reversed(list(sol.assignment.items()))))
    flows = pd.DataFrame(sol.flows.to_dict("records"))
    again = evaluate_network(list(reversed(sol.open_dcs)), rebuilt, flows, params, tiny)
    assert dataclasses.asdict(again) == pytest.approx(dataclasses.asdict(sol.cost))


def test_service_target_is_met_or_reported_infeasible(params, tiny):
    # One DC: D2 is the best single site and reaches 83% next-day, so 80% is met ...
    sol = build_and_solve(params, tiny, k=1)
    assert sol.open_dcs == ("D2",)
    assert sol.cost.next_day_share_frac >= params["service"]["min_share_within_radius"]["value"]
    # ... and no single DC reaches 90%: infeasibility is a finding, returned as data (spec §7)
    strict = with_overrides(params, {"service.min_share_within_radius.value": 0.90})
    assert build_and_solve(strict, tiny, k=1).status == "No Solution Exists"


def test_dc_count_and_forced_closure_respected(params, tiny):
    sol = build_and_solve(no_service_target(params), tiny, k=2, forced_closed=["D1"])
    assert len(sol.open_dcs) == 2
    assert "D1" not in sol.open_dcs


def test_one_site_per_metro_group_makes_both_a_sites_infeasible(params, tiny):
    # D1 and D3 share metro group A (spec §7 constraint 7): infeasibility is data, not an error
    sol = build_and_solve(params, tiny, forced_open=["D1", "D3"])
    assert sol.status == "No Solution Exists"
    assert sol.cost is None


def test_fixed_assignment_is_respected(params, tiny):
    pinned = pd.Series({"Z1": "D3", "Z2": "D3", "Z3": "D2"})
    sol = build_and_solve(no_service_target(params), tiny, fixed_assignment=pinned)
    pd.testing.assert_series_equal(
        sol.assignment.sort_index(), pinned.sort_index(), check_names=False
    )


def test_unknown_forced_dc_is_rejected(params, tiny):
    with pytest.raises(ValueError, match="unknown DCs"):
        build_and_solve(params, tiny, forced_open=["NOPE"])


def test_dc_capacity_formula(params):
    wh = params["warehousing"]
    expected = (
        wh["max_dc_size_sqft"]["value"]
        * wh["space_utilisation"]["value"]
        * wh["storage_density_t_per_sqft"]["value"]
        * 365
        / (wh["cycle_stock_days"]["value"] + wh["safety_stock_days_single_dc"]["value"])
    )
    assert dc_capacity_t_yr(params) == pytest.approx(expected)


@pytest.mark.slow
def test_full_india_one_dc_costs_more_than_four(params):
    from src.data_prep import load_network_data

    data = load_network_data()
    one = build_and_solve(no_service_target(params), data, k=1)
    four = build_and_solve(no_service_target(params), data, k=4)
    assert one.cost.total_inr > four.cost.total_inr


@pytest.mark.slow
def test_full_india_base_case_optimal_within_gap_and_proxy_tolerance(params):
    from src.data_prep import load_network_data

    sol = build_and_solve(params, load_network_data())
    assert sol.status == OPTIMAL
    assert sol.gap_frac <= params["solver"]["mip_gap"]
    assert sol.cost.next_day_share_frac >= params["service"]["min_share_within_radius"]["value"]


def test_free_solve_keeps_the_cheaper_exact_pass_and_records_both(params, tiny):
    # D-034: k_ref = 6 first, then re-sized for the DCs opened; the lower exact cost wins
    sol = build_and_solve(params, tiny)
    assert 1 <= len(sol.passes) <= 2
    assert sol.passes[0]["k_ref"] == params["solver"]["ss_proxy_k_ref_free_runs"]["value"]
    if len(sol.passes) == 2:
        assert sol.passes[1]["k_ref"] == sol.passes[0]["n_dcs"]
    assert sol.cost.total_inr == pytest.approx(min(p["total_inr"] for p in sol.passes))
    assert sol.solve_time_s == pytest.approx(sum(p["solve_time_s"] for p in sol.passes))


@pytest.mark.parametrize(
    ("first_total", "second_total", "kept_k_ref"), [(100.0, 90.0, 3), (90.0, 100.0, 6)]
)
def test_two_pass_rule_keeps_the_lower_exact_cost(
    params, tiny, monkeypatch, first_total, second_total, kept_k_ref
):
    def fake_solve_once(params, data, k, k_ref, *rest):
        total = first_total if k_ref == 6 else second_total
        cost = type("Cost", (), {"total_inr": total})()
        return Solution("ok", 1.0, 1.0, 0.0, 1.0, ("D1", "D2", "D3"), None, None, cost, 0.0)

    monkeypatch.setattr(model, "solve_once", fake_solve_once)
    sol = model.build_and_solve(params, tiny)
    assert [p["k_ref"] for p in sol.passes] == [6, 3]  # pass 2 sized for the 3 DCs opened
    assert sol.cost.total_inr == min(first_total, second_total)
    assert sol.passes[[6, 3].index(kept_k_ref)]["total_inr"] == sol.cost.total_inr


def test_fixed_k_solve_is_single_pass(params, tiny):
    assert build_and_solve(params, tiny, k=2).passes == ()
