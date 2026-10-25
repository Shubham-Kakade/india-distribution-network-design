"""Demand centre of gravity (spec §11): the point minimising demand-weighted distance."""

import numpy as np

from src.geo import haversine_km

WEISZFELD_TOLERANCE_KM = 0.01
WEISZFELD_MAX_ITERATIONS = 1000
MIN_DISTANCE_KM = 1e-6  # stops a demand point sitting on the estimate from dividing by zero


def centre_of_gravity(lat, lon, weight) -> tuple[float, float]:
    """Weighted geometric median of points in degrees, by Weiszfeld iteration (spec §11).

    Start at the weighted mean, then repeat x <- sum(w_i x_i / d_i) / sum(w_i / d_i), with d_i the
    great-circle km from point i to the current estimate, until a step moves under the tolerance.
    shortcut: the update averages degrees as if they were planar; on the 158 zones this lands
    about 15 km from the exact spherical optimum (0.01% more weighted tonne-km). Use a projected
    CRS if a site decision ever rests on it.
    """
    lat, lon, weight = np.asarray(lat), np.asarray(lon), np.asarray(weight)
    est_lat, est_lon = np.average(lat, weights=weight), np.average(lon, weights=weight)
    for _ in range(WEISZFELD_MAX_ITERATIONS):
        step_weight = weight / np.maximum(haversine_km(lat, lon, est_lat, est_lon), MIN_DISTANCE_KM)
        new_lat = np.average(lat, weights=step_weight)
        new_lon = np.average(lon, weights=step_weight)
        moved_km = haversine_km(est_lat, est_lon, new_lat, new_lon)
        est_lat, est_lon = new_lat, new_lon
        if moved_km < WEISZFELD_TOLERANCE_KM:
            break
    return float(est_lat), float(est_lon)
