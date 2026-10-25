import dataclasses

import pytest

from src.baseline import as_is_network, solve_as_is
from src.config import with_overrides
from src.costs import evaluate_network

DEPOTS = [
    # Same metro group as candidates D1 and D3; nearer to D1
    {"id": "AS_A", "name": "Depot A", "lat": 19.06, "lon": 73.06, "state": "Maharashtra",
     "metro_group": "A", "states": ["Maharashtra"]},
    # No candidate in metro group Q: default rent
    {"id": "AS_Q", "name": "Depot Q", "lat": 22.2, "lon": 72.6, "state": "Rajasthan",
     "metro_group": "Q", "states": ["Rajasthan"]},
]  # fmt: skip


@pytest.fixture
def depot_params(params) -> dict:
    return with_overrides(params, {"as_is_depots.list": DEPOTS})


def test_grade_b_rent_from_nearest_same_metro_candidate_else_default(depot_params, tiny):
    as_is, _ = as_is_network(depot_params, tiny)
    rent = as_is.dcs.set_index("dc_id")["rent_inr_sqft_month"]
    discount = depot_params["warehousing"]["grade_b_rent_discount"]["value"]
    assert rent["AS_A"] == pytest.approx(20.0 * (1 - discount))  # D1's rent, not D3's
    assert rent["AS_Q"] == depot_params["as_is_depots"]["default_rent"]["value"]


def test_zones_go_to_their_state_depot_else_the_nearest(depot_params, tiny):
    _, assignment = as_is_network(depot_params, tiny)
    assert assignment["Z1"] == "AS_A"
    assert assignment["Z2"] == "AS_A"
    assert assignment["Z3"] == "AS_Q"  # Gujarat has no depot; AS_Q is the nearer one


def test_as_is_is_costed_by_the_same_evaluator(depot_params, tiny):
    sol = solve_as_is(depot_params, tiny)
    as_is, assignment = as_is_network(depot_params, tiny)
    assert sol.open_dcs == ("AS_A", "AS_Q")
    assert sol.assignment.sort_index().equals(assignment.sort_index())
    direct = evaluate_network(sol.open_dcs, assignment, sol.flows, depot_params, as_is)
    assert dataclasses.asdict(direct) == pytest.approx(dataclasses.asdict(sol.cost))
