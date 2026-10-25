import dataclasses

import numpy as np
import pandas as pd
import pytest

from src.config import with_overrides
from src.costs import (
    DAYS_PER_YEAR,
    evaluate_network,
    safety_stock_t,
)


def one_dc_network() -> tuple[list[str], pd.Series, pd.DataFrame]:
    assignment = pd.Series({"Z1": "D1", "Z2": "D1", "Z3": "D1"})
    flows = pd.DataFrame({"plant_id": ["P1"], "dc_id": ["D1"], "flow_t_yr": [180_000.0]})
    return ["D1"], assignment, flows


def test_breakdown_matches_hand_calculation(params, tiny):
    cost = evaluate_network(*one_dc_network(), params, tiny)
    wh, tr = params["warehousing"], params["transport"]
    crore = params["meta"]["crore"]

    # spec §6, by hand: Z1 is 10 km away, so the 25 km floor applies to its cost
    assert cost.secondary_inr == pytest.approx(
        tr["secondary_inr_per_tkm"]["value"] * (30_000 * 25 + 60_000 * 300 + 90_000 * 600)
    )
    assert cost.primary_inr == pytest.approx(tr["primary_ftl_inr_per_tkm"]["value"] * 180_000 * 100)
    assert cost.handling_inr == pytest.approx(wh["handling_inr_per_tonne"]["value"] * 180_000)
    stock_t = (
        (wh["cycle_stock_days"]["value"] + wh["safety_stock_days_single_dc"]["value"])
        / DAYS_PER_YEAR
        * 180_000
    )  # one DC: SS_1 = (ss_days / 365) x D_total
    value_inr_per_t = 200 * 0.60 * 1000  # realisation x COGS share x kg per tonne
    assert value_inr_per_t == pytest.approx(
        params["company"]["avg_realisation_inr_per_kg"]["value"]
        * params["company"]["cogs_share_of_realisation"]["value"]
        * 1000
    )
    assert cost.inventory_inr == pytest.approx(
        wh["inventory_carrying_rate"]["value"] * value_inr_per_t * stock_t
    )
    area_sqft = (
        stock_t / wh["storage_density_t_per_sqft"]["value"] / wh["space_utilisation"]["value"]
    )
    assert area_sqft > wh["min_dc_size_sqft"]["value"]
    assert cost.space_inr == pytest.approx(
        area_sqft * (20 + wh["opex_inr_per_sqft_month"]["value"]) * 12
    )
    assert cost.fixed_inr == pytest.approx(wh["fixed_cost_per_dc_cr_per_yr"]["value"] * crore)
    assert cost.total_inr == pytest.approx(
        cost.primary_inr
        + cost.secondary_inr
        + cost.handling_inr
        + cost.space_inr
        + cost.inventory_inr
        + cost.fixed_inr
    )
    assert cost.next_day_share_frac == pytest.approx(90_000 / 180_000)  # Z1, Z2 within 400 km
    assert cost.two_day_share_frac == pytest.approx(1.0)


def test_floor_applies_to_cost_but_not_to_service(params, tiny):
    # Radius 20 km: Z1 (10 km) is next-day although its cost is charged at 25 km (D-016)
    tight = with_overrides(params, {"service.next_day_radius_km.value": 20})
    cost = evaluate_network(*one_dc_network(), tight, tiny)
    assert cost.next_day_share_frac == pytest.approx(30_000 / 180_000)


def test_small_dc_is_charged_the_minimum_size(params, tiny):
    small = dataclasses.replace(tiny, zones=tiny.zones.assign(demand_t_yr=[1.0, 2.0, 3.0]))
    open_dcs, assignment, flows = one_dc_network()
    cost = evaluate_network(open_dcs, assignment, flows.assign(flow_t_yr=6.0), params, small)
    wh = params["warehousing"]
    assert cost.space_inr == pytest.approx(
        wh["min_dc_size_sqft"]["value"] * (20 + wh["opex_inr_per_sqft_month"]["value"]) * 12
    )


def test_square_root_law_total_safety_stock_rises_with_dc_count(params):
    one_dc = safety_stock_t(1000.0, 1000.0, params)
    two_dcs = safety_stock_t(np.array([500.0, 500.0]), 1000.0, params).sum()
    assert two_dcs == pytest.approx(np.sqrt(2) * one_dc)


def test_rejects_assignment_to_closed_dc(params, tiny):
    _, assignment, flows = one_dc_network()
    with pytest.raises(ValueError, match="closed DCs"):
        evaluate_network(["D2"], assignment, flows.assign(dc_id="D2"), params, tiny)


def test_rejects_unbalanced_flows(params, tiny):
    open_dcs, assignment, flows = one_dc_network()
    with pytest.raises(ValueError, match="do not balance"):
        evaluate_network(open_dcs, assignment, flows.assign(flow_t_yr=150_000.0), params, tiny)
