"""Two-layer demand model and demand zones (spec §4.3).

Inputs are the cleaned tables from data_prep: cities (state, city, population, lat, lon),
valid districts (state, district, population, lat, lon) and states (state, population).
"""

import logging

import numpy as np
import pandas as pd

from src.geo import road_distance_km

logger = logging.getLogger(__name__)

POINT_COLUMNS = ["name", "state", "lat", "lon", "layer", "population", "demand_t_yr"]
ZONE_COLUMNS = [
    "zone_id",
    "anchor_name",
    "state",
    "lat",
    "lon",
    "population",
    "city_demand_t_yr",
    "rest_demand_t_yr",
    "demand_t_yr",
]


def consumption_index(states: pd.Series, layer: str, params: dict) -> pd.Series:
    """Per-capita consumption index of each state for one layer (spec §4.3).

    index = (state MPCE / All-India MPCE) ^ elasticity, with urban MPCE for the "city" layer
    and rural MPCE for the "rest" layer. States without an HCES figure get All-India (index 1).
    """
    cfg = params["demand"]["state_consumption_index"]
    column = {"rest": 0, "city": 1}[layer]  # YAML pairs are [rural, urban]
    mpce = {state: pair[column] for state, pair in cfg["mpce_inr_month"].items()}
    all_india = mpce["All-India"]
    return (states.map(mpce).fillna(all_india) / all_india) ** cfg["elasticity"]["value"]


def city_layer_multiplier(
    city_weight: float, rest_weight: float, rest_share_target_frac: float
) -> float:
    """Multiplier m on city-layer consumption that gives the rest-of-state layer its target share.

    rest / (rest + m x city) = target  =>  m = rest x (1 - target) / (target x city)  (spec §4.3)
    """
    return rest_weight * (1 - rest_share_target_frac) / (rest_share_target_frac * city_weight)


def build_demand_points(
    cities: pd.DataFrame, districts: pd.DataFrame, states: pd.DataFrame, params: dict
) -> pd.DataFrame:
    """City points plus rest-of-state district fragments, each with annual demand (spec §4.3).

    Rest-of-state population = state population - city population, spread over the state's
    valid district centroids in proportion to district population. Each layer's population is
    weighted by its consumption index (and the metro uplift for the 8 metros); the city layer is
    then scaled so the rest-of-state layer delivers residual_share_target of national demand, and
    the total is scaled to company.annual_volume_tonnes.
    """
    demand = params["demand"]
    metros = demand["metro_uplift"]["applies_to"]
    missing_metros = sorted(set(metros) - set(cities["city"]))
    if missing_metros:
        raise ValueError(f"demand.metro_uplift.applies_to not in city table: {missing_metros}")

    metro_uplift = np.where(cities["city"].isin(metros), demand["metro_uplift"]["value"], 1.0)
    city = cities.assign(
        name=cities["city"],
        layer="city",
        weight=cities["population"]
        * consumption_index(cities["state"], "city", params)
        * metro_uplift,
    )

    state_pop = states.set_index("state")["population"]
    rest_pop = state_pop - city.groupby("state")["population"].sum().reindex(
        state_pop.index, fill_value=0
    )
    if (rest_pop < 0).any():
        raise ValueError(
            f"City population exceeds state population: {rest_pop[rest_pop < 0].to_dict()}"
        )
    district_share_frac = districts["population"] / districts.groupby("state")[
        "population"
    ].transform("sum")
    rest = districts.assign(
        name=districts["district"],
        layer="rest",
        population=district_share_frac * districts["state"].map(rest_pop),
    )
    rest = rest.assign(
        weight=rest["population"]
        * consumption_index(rest["state"], "rest", params)
        * demand["per_capita_index_rest"]["value"]
    )
    # A state with rest-of-state population but no valid district would lose it here
    assert np.isclose(city["population"].sum() + rest["population"].sum(), state_pop.sum())

    multiplier = city_layer_multiplier(
        city["weight"].sum(), rest["weight"].sum(), demand["residual_share_target"]["value"]
    )
    logger.info("City-layer per-capita multiplier solved at %.3f (spec §4.3)", multiplier)
    points = pd.concat([city.assign(weight=city["weight"] * multiplier), rest], ignore_index=True)

    volume_t_yr = params["company"]["annual_volume_tonnes"]["value"]
    points = points.assign(demand_t_yr=points["weight"] / points["weight"].sum() * volume_t_yr)
    return points[POINT_COLUMNS]


def build_zones(points: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Aggregate demand points into zones around anchor cities (spec §4.3).

    Anchors are the n most populous cities, plus one for each state that has none and either
    exceeds the population threshold (§4.3) or has no city of 1 lakh or more (§4.2: Goa,
    Arunachal Pradesh, DNH & DD). The extra anchor is the state's largest city, else its most
    populous district centroid.
    Every point joins the nearest anchor in its own state, or the nearest anchor overall when its
    state has none. A zone sits at its anchor, where the distributor would be.
    """
    demand = params["demand"]
    cities = points[points["layer"] == "city"].sort_values(
        ["population", "name"], ascending=[False, True]
    )
    anchors = cities.head(demand["n_demand_zones"]["value"])

    state_pop = points.groupby("state")["population"].sum()
    needs_zone = (
        state_pop > demand["min_one_zone_per_state_pop_above"]["value"]
    ) | ~state_pop.index.isin(cities["state"])
    unanchored = state_pop[needs_zone].index.difference(anchors["state"])
    # "city" sorts before "rest", so a state's largest city wins over its largest district
    extra = (
        points[points["state"].isin(unanchored)]
        .sort_values(["layer", "population", "name"], ascending=[True, False, True])
        .groupby("state")
        .head(1)
    )
    for row in extra.itertuples():  # small table
        logger.info("Extra zone anchor for %s: %s (%s layer)", row.state, row.name, row.layer)

    anchors = pd.concat([anchors, extra]).sort_values(
        ["population", "name"], ascending=[False, True]
    )
    anchors = anchors.assign(zone_id=[f"Z{i:03d}" for i in range(1, len(anchors) + 1)])

    dist_km = road_distance_km(points, anchors, params)
    same_state = points["state"].to_numpy()[:, None] == anchors["state"].to_numpy()[None, :]
    has_anchor = same_state.any(axis=1)
    fallback_states = sorted(points.loc[~has_anchor, "state"].unique())
    if fallback_states:
        logger.info("States without an anchor join the nearest zone overall: %s", fallback_states)
    dist_km = np.where(same_state | ~has_anchor[:, None], dist_km, np.inf)
    points = points.assign(
        zone_id=anchors["zone_id"].to_numpy()[dist_km.argmin(axis=1)],
        city_demand_t_yr=points["demand_t_yr"].where(points["layer"] == "city", 0.0),
        rest_demand_t_yr=points["demand_t_yr"].where(points["layer"] == "rest", 0.0),
    )

    totals = points.groupby("zone_id")[
        ["population", "city_demand_t_yr", "rest_demand_t_yr", "demand_t_yr"]
    ].sum()
    zones = anchors[["zone_id", "name", "state", "lat", "lon"]].rename(
        columns={"name": "anchor_name"}
    )
    zones = zones.merge(totals, left_on="zone_id", right_index=True, validate="one_to_one")
    assert len(zones) == len(anchors), "an anchor attracted no demand, not even its own"
    assert np.isclose(zones["demand_t_yr"].sum(), points["demand_t_yr"].sum())
    return zones[ZONE_COLUMNS].sort_values("zone_id").reset_index(drop=True)
