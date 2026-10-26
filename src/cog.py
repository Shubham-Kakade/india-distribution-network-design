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


def k_centres_of_gravity(lat, lon, weight, k: int) -> tuple[np.ndarray, np.ndarray]:
    """k demand-weighted centres of gravity, the classic heuristic the MILP is compared with.

    Alternates two steps until no point changes cluster: assign each point to its nearest
    centre (great-circle), then move each centre to its cluster's Weiszfeld centre of gravity.
    The start is a deterministic k-means++ seeding: the heaviest point, then repeatedly the point
    with the largest weight x distance to the seeds so far, which spreads the centres out
    (spec §11, D-018).
    Returns the centres as a (k, 2) array of [lat, lon] and the cluster label of every point.
    """
    lat, lon, weight = np.asarray(lat), np.asarray(lon), np.asarray(weight)
    seeds = [int(np.argmax(weight))]
    for _ in range(1, k):
        nearest_seed_km = haversine_km(
            lat[:, None], lon[:, None], lat[seeds][None, :], lon[seeds][None, :]
        ).min(axis=1)
        seeds.append(int(np.argmax(weight * nearest_seed_km)))
    centres = np.column_stack([lat[seeds], lon[seeds]])
    labels = np.full(len(lat), -1)
    for _ in range(WEISZFELD_MAX_ITERATIONS):
        dist_km = haversine_km(lat[:, None], lon[:, None], centres[None, :, 0], centres[None, :, 1])
        new_labels = dist_km.argmin(axis=1)
        if (new_labels == labels).all():
            break
        labels = new_labels
        for c in range(k):
            members = labels == c
            if members.any():  # an emptied cluster keeps its last centre
                centres[c] = centre_of_gravity(lat[members], lon[members], weight[members])
    return centres, labels
