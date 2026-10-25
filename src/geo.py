"""Road-distance proxy (spec §5): haversine x circuity, North-East routes via Siliguri."""

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in km between points given in degrees; numpy-broadcastable."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def road_distance_km(a: pd.DataFrame, b: pd.DataFrame, params: dict) -> np.ndarray:
    """Road km from every row of `a` to every row of `b`, shape (len(a), len(b)) (spec §5).

    d = circuity x hav(a, b), except when exactly one endpoint is in a North-East state:
    d = circuity x (hav(a, Siliguri) + hav(Siliguri, b)).
    Both frames need columns lat, lon and state.
    """
    distance = params["distance"]
    waypoint = distance["northeast_waypoint"]
    a_lat, a_lon = a["lat"].to_numpy()[:, None], a["lon"].to_numpy()[:, None]
    b_lat, b_lon = b["lat"].to_numpy()[None, :], b["lon"].to_numpy()[None, :]

    direct_gc_km = haversine_km(a_lat, a_lon, b_lat, b_lon)
    via_siliguri_gc_km = haversine_km(
        a_lat, a_lon, waypoint["lat"], waypoint["lon"]
    ) + haversine_km(waypoint["lat"], waypoint["lon"], b_lat, b_lon)
    # Siliguri corridor: the only road link between the North-East and the rest of India
    a_is_ne = a["state"].isin(waypoint["applies_to_states"]).to_numpy()[:, None]
    b_is_ne = b["state"].isin(waypoint["applies_to_states"]).to_numpy()[None, :]
    gc_km = np.where(a_is_ne != b_is_ne, via_siliguri_gc_km, direct_gc_km)
    return distance["circuity_factor"]["value"] * gc_km
