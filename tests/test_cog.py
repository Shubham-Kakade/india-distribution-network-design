import pytest

from src.cog import centre_of_gravity, k_centres_of_gravity


def test_symmetric_points_give_the_centre():
    lat, lon = centre_of_gravity([20.0, 20.0, 21.0, 19.0], [78.0, 80.0, 79.0, 79.0], [1, 1, 1, 1])
    assert lat == pytest.approx(20.0, abs=0.01)
    assert lon == pytest.approx(79.0, abs=0.01)


def test_dominant_weight_pulls_the_centre_onto_its_point():
    # Geometric median: a point carrying at least half the weight is the optimum
    lat, lon = centre_of_gravity([19.0, 28.6, 13.0], [72.9, 77.2, 80.3], [10, 1, 1])
    assert lat == pytest.approx(19.0, abs=0.01)
    assert lon == pytest.approx(72.9, abs=0.01)


def test_k_centres_find_two_separated_clusters():
    # Two tight groups around (20, 75) and (28, 85); the heavier group seeds the first centre
    lat = [19.9, 20.1, 20.0, 27.9, 28.1, 28.0]
    lon = [75.0, 75.0, 75.1, 85.0, 85.0, 84.9]
    centres, labels = k_centres_of_gravity(lat, lon, [5, 5, 5, 1, 1, 1], k=2)
    assert labels.tolist() == [0, 0, 0, 1, 1, 1]
    assert centres[0] == pytest.approx([20.0, 75.0], abs=0.1)
    assert centres[1] == pytest.approx([28.0, 85.0], abs=0.1)


def test_one_centre_equals_the_single_centre_of_gravity():
    lat, lon, w = [19.0, 28.6, 13.0, 22.6], [72.9, 77.2, 80.3, 88.4], [4, 3, 2, 1]
    centres, labels = k_centres_of_gravity(lat, lon, w, k=1)
    assert (labels == 0).all()
    assert tuple(centres[0]) == pytest.approx(centre_of_gravity(lat, lon, w))
