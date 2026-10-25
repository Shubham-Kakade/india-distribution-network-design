import pandas as pd
import pytest

from src.config import load_params, with_overrides
from src.demand import (
    build_demand_points,
    build_zones,
    city_layer_multiplier,
    consumption_index,
)


@pytest.fixture(scope="module")
def params() -> dict:
    # One-zone run on a tiny fixture: the metro uplift must name a fixture city
    return with_overrides(
        load_params(),
        {"demand.n_demand_zones.value": 1, "demand.metro_uplift.applies_to": ["Kochi"]},
    )


@pytest.fixture(scope="module")
def tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cities = pd.DataFrame(
        {
            "state": ["Kerala", "Kerala", "Puducherry"],
            "city": ["Kochi", "Kozhikode", "Puducherry"],
            "population": [300_000, 150_000, 200_000],
            "lat": [10.0, 11.25, 11.9],
            "lon": [76.3, 75.8, 79.8],
        }
    )
    districts = pd.DataFrame(
        {
            "state": ["Kerala", "Kerala", "Goa", "Goa", "Puducherry"],
            # Kerala's second district sits beside Goa's anchor to test the same-state rule
            "district": ["Ernakulam", "Far North", "North Goa", "South Goa", "Karaikal"],
            "population": [600_000, 400_000, 200_000, 100_000, 50_000],
            "lat": [10.1, 15.4, 15.48, 15.27, 11.0],
            "lon": [76.4, 73.9, 73.82, 73.95, 79.9],
        }
    )
    states = pd.DataFrame(
        {"state": ["Kerala", "Goa", "Puducherry"], "population": [1_200_000, 400_000, 300_000]}
    )
    return cities, districts, states


@pytest.fixture(scope="module")
def points(tables, params) -> pd.DataFrame:
    return build_demand_points(*tables, params)


def test_consumption_index_uses_layer_mpce_and_all_india_default(params):
    mpce = params["demand"]["state_consumption_index"]["mpce_inr_month"]
    states = pd.Series(["Kerala", "Goa"])  # Goa has no HCES figure
    rest = consumption_index(states, "rest", params)
    city = consumption_index(states, "city", params)
    assert rest[0] == pytest.approx(mpce["Kerala"][0] / mpce["All-India"][0])
    assert city[0] == pytest.approx(mpce["Kerala"][1] / mpce["All-India"][1])
    assert rest[1] == pytest.approx(1.0)


def test_city_layer_multiplier_hits_rest_share_target():
    m = city_layer_multiplier(city_weight=40.0, rest_weight=60.0, rest_share_target_frac=0.55)
    assert 60.0 / (60.0 + m * 40.0) == pytest.approx(0.55)


def test_demand_points_conserve_population_by_state(points, tables):
    _, _, states = tables
    by_state = points.groupby("state")["population"].sum()
    expected = states.set_index("state")["population"]
    pd.testing.assert_series_equal(
        by_state.sort_index(), expected.sort_index().astype(float), check_names=False
    )


def test_demand_points_sum_to_volume_with_target_rest_share(points, params):
    volume_t_yr = params["company"]["annual_volume_tonnes"]["value"]
    assert points["demand_t_yr"].sum() == pytest.approx(volume_t_yr, rel=1e-6)
    rest_t_yr = points.loc[points["layer"] == "rest", "demand_t_yr"].sum()
    assert rest_t_yr / volume_t_yr == pytest.approx(
        params["demand"]["residual_share_target"]["value"]
    )


def test_zones_conserve_demand_and_population(points, params):
    zones = build_zones(points, params)
    volume_t_yr = params["company"]["annual_volume_tonnes"]["value"]
    assert zones["demand_t_yr"].sum() == pytest.approx(volume_t_yr, rel=1e-6)
    assert (zones["city_demand_t_yr"] + zones["rest_demand_t_yr"]).to_numpy() == pytest.approx(
        zones["demand_t_yr"].to_numpy()
    )
    assert zones["population"].sum() == pytest.approx(points["population"].sum())


def test_zone_anchors_and_assignment_rules(points, params):
    zones = build_zones(points, params).set_index("anchor_name")
    # Top-1 city, plus Goa (no city of 1 lakh: its largest district); Puducherry is below the
    # 1 mn threshold and has a city, so it gets no zone of its own
    assert sorted(zones.index) == ["Kochi", "North Goa"]
    # Same-state rule: Kerala's district next to North Goa still joins the Kochi zone
    assert zones.loc["Kochi", "population"] == pytest.approx(1_200_000 + 300_000)
    assert zones.loc["North Goa", "population"] == pytest.approx(400_000)
