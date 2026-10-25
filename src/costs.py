"""The single cost engine (spec §6). Every reported cost comes from evaluate_network.

The MILP in model.py optimises a linear proxy built from the per-unit helpers below, so the
proxy and the evaluator cannot drift apart. Costs are INR per year; crore only at reporting.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data_prep import NetworkData

logger = logging.getLogger(__name__)

DAYS_PER_YEAR = 365
MONTHS_PER_YEAR = 12
KG_PER_TONNE = 1000


@dataclass(frozen=True)
class CostBreakdown:
    """Annual cost of one network by component (spec §6), with its service level."""

    primary_inr: float
    secondary_inr: float
    handling_inr: float
    space_inr: float
    inventory_inr: float
    fixed_inr: float
    n_dcs: int
    next_day_share_frac: float  # demand within service.next_day_radius_km of its DC
    two_day_share_frac: float  # demand within service.two_day_radius_km
    revenue_inr: float

    @property
    def total_inr(self) -> float:
        return (
            self.primary_inr
            + self.secondary_inr
            + self.handling_inr
            + self.space_inr
            + self.inventory_inr
            + self.fixed_inr
        )

    @property
    def share_of_revenue_frac(self) -> float:
        return self.total_inr / self.revenue_inr


def to_crore(x_inr: float, params: dict) -> float:
    """INR to INR crore, for reports and charts only."""
    return x_inr / params["meta"]["crore"]


def cycle_stock_t(dc_demand_t_yr, params: dict):
    """Average cycle stock held at a DC (spec §6): CS_j = (cycle_days / 365) x D_j."""
    return params["warehousing"]["cycle_stock_days"]["value"] / DAYS_PER_YEAR * dc_demand_t_yr


def safety_stock_t(dc_demand_t_yr, national_demand_t_yr: float, params: dict):
    """Safety stock at a DC under the square-root law (spec §6).

    SS_j = (ss_days_1 / 365) x D_total x sqrt(D_j / D_total), so total SS rises with DC count.
    """
    ss_days = params["warehousing"]["safety_stock_days_single_dc"]["value"]
    return (
        ss_days
        / DAYS_PER_YEAR
        * national_demand_t_yr
        * np.sqrt(np.asarray(dc_demand_t_yr) / national_demand_t_yr)
    )


def stock_area_sqft(stock_t, params: dict):
    """Gross area that holds a given stock (spec §6): stock / density / utilisation, unclipped."""
    wh = params["warehousing"]
    return stock_t / wh["storage_density_t_per_sqft"]["value"] / wh["space_utilisation"]["value"]


def space_cost_inr_sqft_yr(rent_inr_sqft_month, params: dict):
    """Annual cost of one sq ft (spec §6): (rent_j + opex) x 12."""
    opex = params["warehousing"]["opex_inr_per_sqft_month"]["value"]
    return (rent_inr_sqft_month + opex) * MONTHS_PER_YEAR


def carrying_cost_inr_per_t_yr(params: dict) -> float:
    """Annual cost of holding one tonne (spec §6): i x v, v = realisation x COGS share x 1,000."""
    company = params["company"]
    value_inr_per_t = (
        company["avg_realisation_inr_per_kg"]["value"]
        * company["cogs_share_of_realisation"]["value"]
        * KG_PER_TONNE
    )
    return params["warehousing"]["inventory_carrying_rate"]["value"] * value_inr_per_t


def evaluate_network(
    open_dcs: Sequence[str],
    assignment: pd.Series,
    flows: pd.DataFrame,
    params: dict,
    data: NetworkData,
) -> CostBreakdown:
    """Exact annual cost and service of a network (spec §6).

    Args:
        open_dcs: dc_ids of the open sites.
        assignment: dc_id serving each zone, indexed by zone_id (single sourcing).
        flows: plant_id, dc_id, flow_t_yr rows for the primary leg.
    """
    open_dcs = list(open_dcs)
    zones = data.zones.set_index("zone_id")
    demand_t_yr = zones["demand_t_yr"]
    if set(assignment.index) != set(zones.index):
        raise ValueError("assignment must name exactly one DC for every zone")
    if not assignment.isin(open_dcs).all():
        raise ValueError(f"zones assigned to closed DCs: {sorted(set(assignment) - set(open_dcs))}")
    total_t_yr = demand_t_yr.sum()
    dc_t_yr = demand_t_yr.groupby(assignment).sum().reindex(open_dcs, fill_value=0.0)
    inflow_t_yr = flows.groupby("dc_id")["flow_t_yr"].sum().reindex(open_dcs, fill_value=0.0)
    if not np.allclose(inflow_t_yr, dc_t_yr, rtol=1e-6, atol=1e-3):
        raise ValueError("plant flows do not balance DC throughput (spec §7 constraint 4)")

    transport = params["transport"]
    zone_dc_km = data.zone_dc_km.loc[demand_t_yr.index]
    assigned_km = zone_dc_km.to_numpy()[
        np.arange(len(zone_dc_km)), zone_dc_km.columns.get_indexer(assignment[demand_t_yr.index])
    ]
    # Floor for cost only: a DC inside a zone still drives to the distributor (D-016)
    floor_km = params["demand"]["intra_zone_min_distance_km"]["value"]
    secondary_inr = (
        transport["secondary_inr_per_tkm"]["value"]
        * (demand_t_yr.to_numpy() * np.maximum(assigned_km, floor_km)).sum()
    )
    flow_km = data.plant_dc_km.to_numpy()[
        data.plant_dc_km.index.get_indexer(flows["plant_id"]),
        data.plant_dc_km.columns.get_indexer(flows["dc_id"]),
    ]
    primary_inr = (
        transport["primary_ftl_inr_per_tkm"]["value"] * (flows["flow_t_yr"] * flow_km).sum()
    )

    wh = params["warehousing"]
    stock_t = cycle_stock_t(dc_t_yr, params) + safety_stock_t(dc_t_yr, total_t_yr, params)
    area_sqft = stock_area_sqft(stock_t, params)
    over_max = area_sqft > wh["max_dc_size_sqft"]["value"]
    if over_max.any():
        logger.warning("DCs above max size, space capped: %s", list(area_sqft[over_max].index))
    area_sqft = area_sqft.clip(wh["min_dc_size_sqft"]["value"], wh["max_dc_size_sqft"]["value"])
    rent = data.dcs.set_index("dc_id").loc[open_dcs, "rent_inr_sqft_month"]
    space_inr = (area_sqft * space_cost_inr_sqft_yr(rent, params)).sum()

    service = params["service"]
    breakdown = CostBreakdown(
        primary_inr=primary_inr,
        secondary_inr=secondary_inr,
        handling_inr=wh["handling_inr_per_tonne"]["value"] * total_t_yr,
        space_inr=space_inr,
        inventory_inr=carrying_cost_inr_per_t_yr(params) * stock_t.sum(),
        fixed_inr=wh["fixed_cost_per_dc_cr_per_yr"]["value"]
        * params["meta"]["crore"]
        * len(open_dcs),
        n_dcs=len(open_dcs),
        next_day_share_frac=demand_t_yr[assigned_km <= service["next_day_radius_km"]["value"]].sum()
        / total_t_yr,
        two_day_share_frac=demand_t_yr[assigned_km <= service["two_day_radius_km"]["value"]].sum()
        / total_t_yr,
        revenue_inr=params["company"]["annual_revenue_cr"]["value"] * params["meta"]["crore"],
    )
    low, high = params["checks"]["logistics_cost_share_band"]["value"]
    if not low <= breakdown.share_of_revenue_frac <= high:
        logger.warning(
            "Logistics cost %.2f%% of revenue is outside the %.1f-%.1f%% band (spec §6)",
            100 * breakdown.share_of_revenue_frac,
            100 * low,
            100 * high,
        )
    return breakdown
