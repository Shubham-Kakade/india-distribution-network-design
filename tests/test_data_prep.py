"""Spec §4.2 defect handling on the real raw files (small, so these stay in the fast suite)."""

import pandas as pd
import pytest

from src.config import load_params
from src.data_prep import (
    TELANGANA_DISTRICTS,
    calibration_table,
    clean_cities,
    clean_districts,
    clean_states,
    distance_table,
    read_raw,
)
from src.demand import build_demand_points, build_zones


@pytest.fixture(scope="module")
def params() -> dict:
    return load_params()


@pytest.fixture(scope="module")
def cleaned(params) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cities = clean_cities(
        read_raw("final_cities.csv"), read_raw("manual_fixes/city_coords_patch.csv"), params
    )
    districts = clean_districts(read_raw("final_districts.csv"), params)
    states = clean_states(
        read_raw("final_states.csv"), read_raw("manual_fixes/state_population_patch.csv"), params
    )
    return cities, districts, states


def test_no_zero_coordinates_remain(cleaned):
    cities, districts, _ = cleaned
    assert (cities[["lat", "lon"]] != 0).all().all()
    assert (districts[["lat", "lon"]] != 0).all().all()


def test_hyderabad_is_one_telangana_city_at_override_population(cleaned):
    cities, _, _ = cleaned
    ghmc = cities[cities["city"] == "GHMC"]
    assert len(ghmc) == 1
    assert ghmc["state"].item() == "Telangana"
    assert ghmc["population"].item() == 6_809_970


def test_telangana_districts_no_longer_in_andhra_pradesh(cleaned):
    cities, _, _ = cleaned
    ap = cities[cities["state"] == "Andhra Pradesh"]
    assert not ap["district"].isin(TELANGANA_DISTRICTS).any()


def test_duplicate_cities_collapsed(cleaned):
    cities, _, _ = cleaned
    assert not cities.duplicated(["state", "city"]).any()
    assert cities.loc[cities["city"] == "Bally", "population"].item() == 113_377 + 293_373


def test_state_names_match_states_file_and_islands_excluded(cleaned, params):
    cities, districts, states = cleaned
    assert set(cities["state"]) <= set(states["state"])
    assert set(districts["state"]) == set(states["state"])
    excluded = set(params["demand"]["excluded_states"]["value"])
    assert not excluded & set(states["state"])


def test_jammu_kashmir_population_fixed_and_ladakh_merged(cleaned):
    _, districts, states = cleaned
    pop = states.set_index("state")["population"]
    assert pop["Jammu and Kashmir"] == 12_541_302
    assert "Ladakh" not in pop.index
    assert {"Leh", "Kargil"} <= set(
        districts.loc[districts["state"] == "Jammu and Kashmir", "district"]
    )


def test_national_population_within_tolerance(cleaned, params):
    _, _, states = cleaned
    checks = params["checks"]
    raw = read_raw("final_states.csv")
    excluded_pop = raw.loc[
        raw["state"].isin(params["demand"]["excluded_states"]["value"]), "population"
    ].sum()
    reference = checks["census_2011_population"]["value"] - excluded_pop
    assert states["population"].sum() == pytest.approx(
        reference, rel=checks["population_tolerance_frac"]["value"]
    )


def test_full_india_zones_conserve_demand_and_respect_share_cap(cleaned, params):
    zones = build_zones(build_demand_points(*cleaned, params), params)
    volume_t_yr = params["company"]["annual_volume_tonnes"]["value"]
    assert zones["demand_t_yr"].sum() == pytest.approx(volume_t_yr, rel=1e-6)
    assert zones["population"].sum() == pytest.approx(cleaned[2]["population"].sum())
    assert (zones["demand_t_yr"] / volume_t_yr).max() <= params["checks"]["max_zone_share_frac"][
        "value"
    ]
    assert zones["zone_id"].is_unique


def test_calibration_pairs_pass(cleaned, params):
    table = calibration_table(cleaned[0], params)
    assert len(table) == len(params["checks"]["calibration_pairs"]["value"])


def test_distance_table_is_long_and_aligned(params):
    a = pd.DataFrame(
        {"zone_id": ["Z1", "Z2"], "lat": [19.0, 28.6], "lon": [72.9, 77.2], "state": "X"}
    )
    b = pd.DataFrame(
        {
            "dc_id": ["D1", "D2", "D3"],
            "lat": [19.0, 13.0, 22.6],
            "lon": [72.9, 80.3, 88.4],
            "state": "X",
        }
    )
    table = distance_table(a, "zone_id", b, "dc_id", params)
    assert len(table) == 6
    same_point = table[(table["zone_id"] == "Z1") & (table["dc_id"] == "D1")]["dist_km"].item()
    assert same_point == pytest.approx(0.0)
