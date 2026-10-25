import pytest

from src.cog import centre_of_gravity


def test_symmetric_points_give_the_centre():
    lat, lon = centre_of_gravity([20.0, 20.0, 21.0, 19.0], [78.0, 80.0, 79.0, 79.0], [1, 1, 1, 1])
    assert lat == pytest.approx(20.0, abs=0.01)
    assert lon == pytest.approx(79.0, abs=0.01)


def test_dominant_weight_pulls_the_centre_onto_its_point():
    # Geometric median: a point carrying at least half the weight is the optimum
    lat, lon = centre_of_gravity([19.0, 28.6, 13.0], [72.9, 77.2, 80.3], [10, 1, 1])
    assert lat == pytest.approx(19.0, abs=0.01)
    assert lon == pytest.approx(72.9, abs=0.01)
