import numpy as np
import pandas as pd
import pytest

from src.config import load_params
from src.geo import haversine_km, road_distance_km

MUMBAI = {"lat": 19.076, "lon": 72.877, "state": "Maharashtra"}
DELHI = {"lat": 28.651, "lon": 77.231, "state": "Delhi"}
KOLKATA = {"lat": 22.57, "lon": 88.36, "state": "West Bengal"}
GUWAHATI = {"lat": 26.15, "lon": 91.73, "state": "Assam"}
SHILLONG = {"lat": 25.57, "lon": 91.88, "state": "Meghalaya"}


@pytest.fixture(scope="module")
def params() -> dict:
    return load_params()


def points(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def test_haversine_mumbai_delhi_in_spec_band():
    # spec §11: 1,140-1,170 km great-circle
    assert 1140 <= haversine_km(MUMBAI["lat"], MUMBAI["lon"], DELHI["lat"], DELHI["lon"]) <= 1170


def test_haversine_is_zero_for_same_point_and_symmetric():
    assert haversine_km(10.0, 70.0, 10.0, 70.0) == pytest.approx(0.0)
    there = haversine_km(MUMBAI["lat"], MUMBAI["lon"], DELHI["lat"], DELHI["lon"])
    back = haversine_km(DELHI["lat"], DELHI["lon"], MUMBAI["lat"], MUMBAI["lon"])
    assert there == pytest.approx(back)


def test_mainland_pair_is_circuity_times_great_circle(params):
    circuity = params["distance"]["circuity_factor"]["value"]
    road_km = road_distance_km(points(MUMBAI), points(DELHI), params)[0, 0]
    gc_km = haversine_km(MUMBAI["lat"], MUMBAI["lon"], DELHI["lat"], DELHI["lon"])
    assert road_km == pytest.approx(circuity * gc_km)


def test_northeast_waypoint_applies_only_when_exactly_one_end_is_northeast(params):
    circuity = params["distance"]["circuity_factor"]["value"]
    wp = params["distance"]["northeast_waypoint"]
    road_km = road_distance_km(points(KOLKATA, GUWAHATI), points(GUWAHATI, SHILLONG), params)

    via = haversine_km(KOLKATA["lat"], KOLKATA["lon"], wp["lat"], wp["lon"]) + haversine_km(
        wp["lat"], wp["lon"], GUWAHATI["lat"], GUWAHATI["lon"]
    )
    assert road_km[0, 0] == pytest.approx(circuity * via)  # mainland -> NE: via Siliguri
    direct = haversine_km(GUWAHATI["lat"], GUWAHATI["lon"], SHILLONG["lat"], SHILLONG["lon"])
    assert road_km[1, 1] == pytest.approx(circuity * direct)  # NE -> NE: direct
    assert road_km[1, 0] == pytest.approx(0.0)  # same point


def test_kolkata_guwahati_close_to_road_reference(params):
    # spec §5: about 1,030 km by road; the direct great-circle proxy gives about 680
    road_km = road_distance_km(points(KOLKATA), points(GUWAHATI), params)[0, 0]
    assert road_km == pytest.approx(1030, rel=0.15)


def test_matrix_shape_and_symmetry(params):
    a = points(MUMBAI, DELHI, KOLKATA)
    b = points(GUWAHATI, SHILLONG)
    ab = road_distance_km(a, b, params)
    assert ab.shape == (3, 2)
    np.testing.assert_allclose(ab, road_distance_km(b, a, params).T)
