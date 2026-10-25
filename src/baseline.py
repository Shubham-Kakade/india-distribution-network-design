"""As-is network (spec §8): 15 pre-GST state C&F depots in Grade B space, on the same cost engine.

Hypothetical and illustrative: it is the baseline the savings are measured against, not client data.
"""

import logging

import numpy as np
import pandas as pd

from src.config import with_overrides
from src.data_prep import CANDIDATE_COLUMNS, NetworkData, build_network_data
from src.geo import haversine_km
from src.model import Solution, build_and_solve

logger = logging.getLogger(__name__)


def as_is_network(params: dict, data: NetworkData) -> tuple[NetworkData, pd.Series]:
    """The depot network and its state-based zone assignment (spec §8).

    Rent: the nearest candidate cluster in the depot's metro group, less the Grade B discount;
    as_is_depots.default_rent where the metro has no candidate. Each zone goes to the depot
    listing its state; zones in unlisted states go to the nearest depot.
    """
    cfg = params["as_is_depots"]
    depots = pd.DataFrame(cfg["list"]).rename(columns={"id": "dc_id"})
    candidates = data.dcs

    cluster_km = haversine_km(
        depots["lat"].to_numpy()[:, None],
        depots["lon"].to_numpy()[:, None],
        candidates["lat"].to_numpy()[None, :],
        candidates["lon"].to_numpy()[None, :],
    )
    same_metro = depots["metro_group"].to_numpy()[:, None] == candidates["metro_group"].to_numpy()
    cluster_km = np.where(same_metro, cluster_km, np.inf)
    nearest_rent = candidates["rent_inr_sqft_month"].to_numpy()[cluster_km.argmin(axis=1)]
    discount = params["warehousing"]["grade_b_rent_discount"]["value"]
    depots = depots.assign(
        rent_inr_sqft_month=np.where(
            same_metro.any(axis=1), nearest_rent * (1 - discount), cfg["default_rent"]["value"]
        )
    )
    no_cluster = depots.loc[~same_metro.any(axis=1), "dc_id"].tolist()
    if no_cluster:
        logger.info(
            "As-is depots with no candidate cluster in their metro, default rent: %s", no_cluster
        )
    depots = depots[CANDIDATE_COLUMNS]

    as_is = build_network_data(data.zones, depots, data.plants, params)
    zones, zone_dc_km = as_is.zones, as_is.zone_dc_km

    state_depot = {state: d["id"] for d in cfg["list"] for state in d["states"]}
    assignment = pd.Series(zones["state"].map(state_depot).to_numpy(), index=zones["zone_id"])
    unlisted = assignment.isna()
    if unlisted.any():
        logger.info(
            "As-is: states with no depot go to the nearest one: %s",
            sorted(zones.loc[unlisted.to_numpy(), "state"].unique()),
        )
        assignment[unlisted] = zone_dc_km[unlisted].idxmin(axis=1)
    return as_is, assignment.rename("dc_id")


def solve_as_is(params: dict, data: NetworkData) -> Solution:
    """Cost the as-is network: depots and assignment fixed, plant flows optimised (spec §8).

    The flows come from the same MILP with every depot forced open and every zone pinned, so the
    as-is network meets the same evaluator, capacity and plant limits as the optimised ones.
    """
    as_is_data, assignment = as_is_network(params, data)
    # Evaluated, not constrained: today's network is not held to the new service target
    unconstrained = with_overrides(params, {"service.min_share_within_radius.value": 0.0})
    depot_ids = as_is_data.dcs["dc_id"].tolist()
    return build_and_solve(
        unconstrained,
        as_is_data,
        k=len(depot_ids),
        forced_open=depot_ids,
        fixed_assignment=assignment,
    )
