"""Scenarios S0-S9, R and the k-COG comparison (spec §9): every result in the study, from raw data.

Run from the project root: python -m src.scenarios
It rebuilds data/processed from data/raw (src.data_prep), solves every scenario in dependency
order, then hands the results to reporting.py, which writes outputs/scenarios/<id>.json,
outputs/scenario_summary.csv, the spec §12 charts and the network maps.
Every cost comes from costs.evaluate_network through model.build_and_solve.
"""

import dataclasses
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from itertools import repeat

import numpy as np
import pandas as pd

from src import data_prep, reporting
from src.baseline import solve_as_is
from src.config import entries_with_range, load_params, with_overrides
from src.costs import to_crore
from src.data_prep import (
    NetworkData,
    build_network_data,
    clean_raw,
    load_network_data,
    plant_table,
)
from src.demand import build_demand_points, build_zones
from src.model import Solution, build_and_solve, dc_capacity_t_yr
from src.robustness import (
    cog_network,
    comparable_service_alpha,
    knee_alpha,
    site_robustness,
    upgrade_options,
)

logger = logging.getLogger(__name__)

RADIUS_KEY = "service.next_day_radius_km.value"
ALPHA_KEY = "service.min_share_within_radius.value"
TORNADO_CONFIDENCE = ("low", "medium")


@dataclass(frozen=True)
class Run:
    """One solved scenario (spec §9): what was changed, the solution, and scenario findings."""

    scenario_id: str
    group: str
    question: str
    inputs: dict  # parameter overrides and data changes, as recorded in the JSON
    solution: Solution
    extra: dict = field(default_factory=dict)


# --- Building blocks ------------------------------------------------------------------------


def at_service(params: dict, radius_km: float, alpha: float) -> dict:
    """Params with the next-day service target set to radius_km / alpha (spec §7 constraint 6)."""
    return with_overrides(params, {RADIUS_KEY: radius_km, ALPHA_KEY: alpha})


def with_rents(data: NetworkData, multiplier: dict[str, float]) -> NetworkData:
    """Candidate rents scaled per dc_id (sites not named keep their rent)."""
    factor = data.dcs["dc_id"].map(multiplier).fillna(1.0)
    dcs = data.dcs.assign(rent_inr_sqft_month=data.dcs["rent_inr_sqft_month"] * factor)
    return dataclasses.replace(data, dcs=dcs)


def assigned_km(solution: Solution, data: NetworkData) -> pd.Series:
    """Road km from each zone to the DC serving it, indexed by zone_id."""
    km = data.zone_dc_km.loc[solution.assignment.index]
    cols = km.columns.get_indexer(solution.assignment)
    return pd.Series(km.to_numpy()[np.arange(len(km)), cols], index=km.index)


def throughput_t_yr(solution: Solution, data: NetworkData) -> pd.Series:
    """Annual tonnes through each open DC."""
    demand = data.zones.set_index("zone_id")["demand_t_yr"]
    return demand.groupby(solution.assignment).sum()


def site_changes(solution: Solution, reference: Solution) -> dict[str, list[str]]:
    """Sites opened and closed relative to a reference network."""
    return {
        "added": sorted(set(solution.open_dcs) - set(reference.open_dcs)),
        "dropped": sorted(set(reference.open_dcs) - set(solution.open_dcs)),
    }


# --- Scenarios ------------------------------------------------------------------------------


def s0_as_is(params: dict, data: NetworkData) -> Run:
    """S0: today's 15 state depots (spec §8)."""
    return Run(
        "S0",
        "S0",
        "What does today cost?",
        {"network": "15 state C&F depots in Grade B space (spec §8)"},
        solve_as_is(params, data),
    )


def s1_cost_only(params: dict, data: NetworkData) -> Run:
    """S1: cheapest network with no service target."""
    return Run(
        "S1",
        "S1",
        "What is the cheapest possible network?",
        {ALPHA_KEY: 0.0},
        build_and_solve(with_overrides(params, {ALPHA_KEY: 0.0}), data),
    )


def s2_dc_count(params: dict, data: NetworkData) -> list[Run]:
    """S2: k = 1..12 DCs, no service target (spec §3 table)."""
    unconstrained = with_overrides(params, {ALPHA_KEY: 0.0})
    return [
        Run(
            f"S2_k{k:02d}",
            "S2",
            "How many DCs?",
            {"k": k, ALPHA_KEY: 0.0},
            build_and_solve(unconstrained, data, k=k),
        )
        for k in params["scenarios"]["dc_count_sweep"]
    ]


def s3_service_frontier(params: dict, data: NetworkData) -> list[Run]:
    """S3: cheapest network for every radius x service-share target; infeasible cells kept."""
    runs = []
    for radius_km in params["service"]["next_day_radius_km"]["sensitivities"]:
        for alpha in params["scenarios"]["service_frontier_alphas"]:
            sol = build_and_solve(at_service(params, radius_km, alpha), data)
            runs.append(
                Run(
                    f"S3_{radius_km}km_{round(100 * alpha)}",
                    "S3",
                    "What does service cost?",
                    {RADIUS_KEY: radius_km, ALPHA_KEY: alpha},
                    sol,
                )
            )
    return runs


def grown_demand(data: NetworkData, params: dict, variant: str) -> tuple[NetworkData, float]:
    """Zone demand after uniform or region-skewed growth (spec §9 S4), and the volume ratio."""
    growth = params["scenarios"]["demand_growth"]
    zones = data.zones
    if variant == "uniform":
        growth_frac = pd.Series(growth["uniform"], index=zones.index)
    else:
        region = {state: r for r, states in growth["regions"].items() for state in states}
        growth_frac = zones["state"].map(region).fillna("Rest").map(growth["regional_skew"])
    grown = zones.assign(demand_t_yr=zones["demand_t_yr"] * (1 + growth_frac))
    ratio = grown["demand_t_yr"].sum() / zones["demand_t_yr"].sum()
    return dataclasses.replace(data, zones=grown), ratio


def s4_growth(params: dict, data: NetworkData, recommended: Run) -> list[Run]:
    """S4: demand +30% uniform, and a variant growing faster in the East and Centre."""
    runs = []
    capacity_t_yr = dc_capacity_t_yr(params)
    for variant in ("uniform", "regional_skew"):
        grown, ratio = grown_demand(data, params, variant)
        # Revenue grows with volume at the same realisation, so the % of revenue stays comparable
        revenue_key = "company.annual_revenue_cr.value"
        p = with_overrides(
            params, {revenue_key: params["company"]["annual_revenue_cr"]["value"] * ratio}
        )
        sol = build_and_solve(p, grown)
        extra = {
            "volume_ratio": ratio,
            "max_dc_utilisation_frac": throughput_t_yr(sol, grown).max() / capacity_t_yr,
            **site_changes(sol, recommended.solution),
        }
        runs.append(
            Run(
                f"S4_{variant}",
                "S4",
                "Does growth change the answer?",
                {"demand_growth": variant, revenue_key: "scaled with volume"},
                sol,
                extra,
            )
        )
    return runs


def s5_disruption(params: dict, data: NetworkData, recommended: Run) -> list[Run]:
    """S5a (operational outage) and S5b (permanent loss) of the busiest recommended DC (spec §9)."""
    busiest = throughput_t_yr(recommended.solution, data).idxmax()
    months = params["scenarios"]["disruption_months"]
    return [
        operational_outage(params, data, recommended, busiest, months, "S5a"),
        permanent_loss(params, data, recommended, busiest, "S5b"),
    ]


def operational_outage(
    params: dict, data: NetworkData, recommended: Run, dc: str, months: float, scenario_id: str
) -> Run:
    """A recommended DC shut for some months while the rest of the network carries on (S5a).

    Keeps the open set, re-assigns the closed site's zones with the capacity surge allowed and
    no service target, and charges only the change in freight for the outage months: rent, fixed
    cost and stock stay in place for a short outage (D-029).
    """
    rec = recommended.solution
    cfg = params["scenarios"]
    max_size_key = "warehousing.max_dc_size_sqft.value"
    surge = with_overrides(
        params,
        {
            ALPHA_KEY: 0.0,
            max_size_key: params["warehousing"]["max_dc_size_sqft"]["value"]
            * (1 + cfg["disruption_capacity_surge"]["value"]),
        },
    )
    remaining = [j for j in rec.open_dcs if j != dc]
    outage = build_and_solve(
        surge, data, k=len(remaining), forced_open=remaining, forced_closed=[dc]
    )
    radius_km = params["service"]["next_day_radius_km"]["value"]
    before_km, after_km = assigned_km(rec, data), assigned_km(outage, data)
    losing = before_km.index[(before_km <= radius_km) & (after_km[before_km.index] > radius_km)]
    zones = data.zones.set_index("zone_id")
    freight_change_inr = (outage.cost.primary_inr + outage.cost.secondary_inr) - (
        rec.cost.primary_inr + rec.cost.secondary_inr
    )
    return Run(
        scenario_id,
        "S5",
        "What if a site goes down for a month?",
        {
            "closed_dc": dc,
            "open_set": "fixed",
            "capacity_surge": cfg["disruption_capacity_surge"]["value"],
            "months": months,
            ALPHA_KEY: 0.0,
        },
        outage,
        {
            "closed_dc": dc,
            "freight_change_cr_per_yr": to_crore(freight_change_inr, params),
            "outage_cost_cr": to_crore(freight_change_inr * months / 12, params),
            "next_day_share_before": rec.cost.next_day_share_frac,
            "next_day_share_during": outage.cost.next_day_share_frac,
            "zones_losing_next_day": zones.loc[losing, "anchor_name"].tolist(),
            "demand_losing_next_day_t_yr": float(zones.loc[losing, "demand_t_yr"].sum()),
        },
    )


def permanent_loss(
    params: dict, data: NetworkData, recommended: Run, dc: str, scenario_id: str
) -> Run:
    """A recommended DC lost for good: re-optimise without it at the same service target (S5b)."""
    rec = recommended.solution
    lost = build_and_solve(params, data, forced_closed=[dc])
    return Run(
        scenario_id,
        "S5",
        "What if we lose the site permanently?",
        {"excluded_dc": dc},
        lost,
        {
            "excluded_dc": dc,
            "penalty_cr_per_yr": to_crore(lost.cost.total_inr - rec.cost.total_inr, params)
            if lost.cost
            else None,
            **(site_changes(lost, rec) if lost.cost else {}),
        },
    )


def diesel_overrides(params: dict, shock: float) -> tuple[float, dict[str, float]]:
    """Freight multiplier and rate overrides for a diesel price shock (spec §9 S6, D-032c).

    Both freight rates x (1 + diesel share of freight cost x shock).
    """
    multiplier = 1 + params["transport"]["diesel_share_of_freight_cost"]["value"] * shock
    overrides = {
        f"transport.{rate}.value": params["transport"][rate]["value"] * multiplier
        for rate in ("primary_ftl_inr_per_tkm", "secondary_inr_per_tkm")
    }
    return multiplier, overrides


def s6_fuel(params: dict, data: NetworkData, recommended: Run) -> list[Run]:
    """S6: diesel shocks; freight x (1 + diesel share x shock) on both legs (spec §9)."""
    runs = []
    for shock in params["scenarios"]["diesel_shock"]:
        multiplier, overrides = diesel_overrides(params, shock)
        sol = build_and_solve(with_overrides(params, overrides), data)
        runs.append(
            Run(
                f"S6_diesel_{round(100 * shock)}",
                "S6",
                "Fuel shock?",
                {"diesel_shock": shock, "freight_multiplier": multiplier, **overrides},
                sol,
                {"freight_multiplier": multiplier, **site_changes(sol, recommended.solution)},
            )
        )
    return runs


def s7_rent_shocks(params: dict, data: NetworkData, recommended: Run) -> list[Run]:
    """S7: every candidate rent +/-20% at once."""
    runs = []
    for shock in params["scenarios"]["rent_shock"]:
        shocked = with_rents(data, dict.fromkeys(data.dcs["dc_id"], 1 + shock))
        sol = build_and_solve(params, shocked)
        runs.append(
            Run(
                f"S7_rent_{'plus' if shock > 0 else 'minus'}_{round(100 * abs(shock))}",
                "S7",
                "Real-estate sensitivity?",
                {"all_rents_multiplier": 1 + shock},
                sol,
                site_changes(sol, recommended.solution),
            )
        )
    return runs


def switching_rent(params: dict, data: NetworkData, dc: str) -> float:
    """S7: the rent at which one site drops out of the re-optimised network.

    Bisection on that site's rent alone, between today's rent and max_multiplier x today's, to
    within tolerance_inr_sqft_month. NaN means the site stays open even at the upper bound.
    Assumes a site, once dropped, stays dropped at higher rents (checked only at the bounds).
    """
    cfg = params["scenarios"]["rent_switch_search"]
    rent = data.dcs.set_index("dc_id").loc[dc, "rent_inr_sqft_month"]

    def stays_open(multiplier: float) -> bool:
        return dc in build_and_solve(params, with_rents(data, {dc: multiplier})).open_dcs

    low, high = 1.0, cfg["max_multiplier"]
    if stays_open(high):
        return np.nan
    while (high - low) * rent > cfg["tolerance_inr_sqft_month"]:
        mid = (low + high) / 2
        low, high = (mid, high) if stays_open(mid) else (low, mid)
    return high * rent


def rent_switching_points(params: dict, data: NetworkData, recommended: Run) -> pd.DataFrame:
    """S7: switching rent for every recommended site (spec §9).

    The site searches are independent, so they run in parallel processes (D-037); each solve
    stays single-threaded and results come back in site order, so the output is unchanged.
    """
    dcs = list(recommended.solution.open_dcs)
    rents = data.dcs.set_index("dc_id")["rent_inr_sqft_month"]
    # spawn, not fork: safe in a threaded parent, and what Windows does anyway
    with ProcessPoolExecutor(mp_context=multiprocessing.get_context("spawn")) as pool:
        switch = list(pool.map(switching_rent, repeat(params), repeat(data), dcs))
    rows = []
    for dc, switch_rent in zip(dcs, switch, strict=True):
        logger.info("S7 switching rent %s: today %.1f, drops out at %s", dc, rents[dc], switch_rent)
        rows.append({"dc_id": dc, "rent": rents[dc], "switch_rent": switch_rent})
    headroom = pd.DataFrame(rows)
    return headroom.assign(headroom_frac=headroom["switch_rent"] / headroom["rent"] - 1)


def s8_plants(params: dict, data: NetworkData, recommended: Run) -> list[Run]:
    """S8: plant footprint variants (remove Puducherry; add an eastern plant), spec §9."""
    runs = []
    for variant, plants in params["scenarios"]["plant_footprints"].items():
        if variant == "note":
            continue
        varied = build_network_data(data.zones, data.dcs, plant_table(plants), params)
        sol = build_and_solve(params, varied)
        runs.append(
            Run(
                f"S8_{variant}",
                "S8",
                "Does plant footprint drive the answer?",
                {"plants": plants},
                sol,
                site_changes(sol, recommended.solution),
            )
        )
    return runs


def rebuild_data(
    params: dict, data: NetworkData, cleaned: tuple, changed_keys: list[str]
) -> NetworkData:
    """Network data under overridden params: a demand or volume key rebuilds zone demand from the
    cleaned raw data (spec §4.3), and the distances are rebuilt with the params' circuity (§5).

    cleaned is the output of data_prep.clean_raw. The zone set must not change, because every
    scenario is compared zone by zone with the recommended network.
    """
    zones = data.zones
    if any(k.startswith("demand.") or k.startswith("company.annual_volume") for k in changed_keys):
        zones = build_zones(build_demand_points(*cleaned, params), params)
        if not zones["zone_id"].equals(data.zones["zone_id"]):
            raise ValueError(f"Overrides {changed_keys} changed the zone set; it must stay fixed")
    return build_network_data(zones, data.dcs, data.plants, params)


def s9_tornado(params: dict, data: NetworkData) -> tuple[list[Run], pd.DataFrame]:
    """S9: re-optimise with each low/medium-confidence parameter at each end of its range.

    Demand parameters rebuild zone demand from the cleaned raw data; circuity rebuilds the
    distances. Each end also re-costs the as-is network, so the saving's sensitivity shows.
    """
    cleaned = clean_raw(params)
    runs, rows = [], []
    for key, entry in entries_with_range(params):
        if entry.get("confidence") not in TORNADO_CONFIDENCE:
            continue
        ends = {}
        for end, value in zip(("low", "high"), entry["range"], strict=True):
            p = with_overrides(params, {f"{key}.value": value})
            varied = rebuild_data(p, data, cleaned, [key])
            sol, as_is = build_and_solve(p, varied), solve_as_is(p, varied)
            saving_cr = to_crore(as_is.cost.total_inr - sol.cost.total_inr, params)
            ends[end] = (sol, saving_cr)
            runs.append(
                Run(
                    f"S9_{key.split('.')[-1]}_{end}",
                    "S9",
                    "Which assumptions matter?",
                    {f"{key}.value": value},
                    sol,
                    {
                        "parameter": key,
                        "value": value,
                        "confidence": entry["confidence"],
                        "as_is_total_cr": to_crore(as_is.cost.total_inr, params),
                        "saving_vs_as_is_cr": saving_cr,
                    },
                )
            )
        rows.append(
            {
                "parameter": key,
                "label": f"{key.split('.')[-1]} [{entry['range'][0]} to {entry['range'][1]}]",
                **{
                    f"{end}_total": to_crore(s.cost.total_inr, params)
                    for end, (s, _) in ends.items()
                },
                **{f"{end}_saving": saving for end, (_, saving) in ends.items()},
                **{f"{end}_dcs": len(s.open_dcs) for end, (s, _) in ends.items()},
            }
        )
    tornado = pd.DataFrame(rows)
    swing = (tornado["high_total"] - tornado["low_total"]).abs()
    return runs, tornado.assign(swing_cr=swing).sort_values("swing_cr", ascending=False)


def cog_networks(params: dict, data: NetworkData, sweep: list[Run]) -> list[Run]:
    """k-centre-of-gravity networks against the MILP at each k of the S2 sweep (§16; D-033)."""
    milp_total = {run.inputs["k"]: run.solution.cost.total_inr for run in sweep}
    runs = []
    for k in params["scenarios"]["dc_count_sweep"]:
        sol, centres = cog_network(params, data, k)
        runs.append(
            Run(
                f"COG_k{k:02d}",
                "COG",
                "Why not just use centre of gravity?",
                {"k": k, "method": "k-centre-of-gravity, snapped to candidates"},
                sol,
                {
                    "centres_lat_lon": centres.round(3).tolist(),
                    "milp_total_cr": to_crore(milp_total[k], params),
                    "premium_vs_milp_frac": sol.cost.total_inr / milp_total[k] - 1,
                },
            )
        )
    return runs


def s3_staging(
    params: dict, data: NetworkData, recommended: Run, upgrades: pd.DataFrame
) -> list[Run]:
    """Can the recommended network grow into the first upgrade option without closing a site?

    If the next upgrade drops some recommended sites, re-solve the recommended target with
    those sites closed: the extra cost is what building toward the upgrade costs today, and
    "nested_in_next" says whether the upgrade then only adds sites (supervisor request, D-028).
    """
    if upgrades.empty or not upgrades["dropped"].iloc[0]:
        return []
    upgrade = upgrades.iloc[0]
    sol = build_and_solve(params, data, forced_closed=upgrade["dropped"])
    nested = sol.cost is not None and set(sol.open_dcs) <= set(upgrade["sites"])
    return [
        Run(
            f"{recommended.scenario_id}_staged",
            "S3",
            "Can the recommended network stage into the next upgrade?",
            {"forced_closed": upgrade["dropped"], "toward": upgrade["scenario_id"]},
            sol,
            {
                "toward": upgrade["scenario_id"],
                "penalty_cr_per_yr": to_crore(
                    sol.cost.total_inr - recommended.solution.cost.total_inr, params
                )
                if sol.cost
                else None,
                "nested_in_next": nested,
                **(site_changes(sol, recommended.solution) if sol.cost else {}),
            },
        )
    ]


def open_sets(runs: list[Run]) -> dict[str, tuple[str, ...]]:
    """Open sites of each feasible run, by scenario id (the input R classifies on)."""
    return {r.scenario_id: r.solution.open_dcs for r in runs if r.solution.cost is not None}


def frontier_table(frontier: list[Run]) -> pd.DataFrame:
    """S3 as a table: one row per radius x target, total NaN where infeasible."""
    return pd.DataFrame(
        [
            {
                "scenario_id": r.scenario_id,
                "radius_km": r.inputs[RADIUS_KEY],
                "alpha": r.inputs[ALPHA_KEY],
                "total_inr": r.solution.cost.total_inr if r.solution.cost else np.nan,
                "open_dcs": r.solution.open_dcs,
            }
            for r in frontier
        ]
    )


# --- Orchestration --------------------------------------------------------------------------


def run_all(params: dict, data: NetworkData) -> dict:
    """Solve every scenario in dependency order. The recommended network is the cheapest S3
    network at the service level comparable to today's; S4-S9 and R stress-test it at that
    target, and every higher S3 target is priced as an upgrade option (D-028)."""
    as_is = s0_as_is(params, data)
    cost_only = s1_cost_only(params, data)
    sweep = s2_dc_count(params, data)
    frontier = s3_service_frontier(params, data)
    radius_km = params["service"]["next_day_radius_km"]["value"]
    table = frontier_table(frontier)
    curve = table[table["radius_km"] == radius_km]
    alpha = comparable_service_alpha(
        sorted(curve["alpha"]), as_is.solution.cost.next_day_share_frac
    )
    knee = knee_alpha(curve.rename(columns={"total_inr": "total"}))
    recommended = next(
        r for r in frontier if r.inputs[RADIUS_KEY] == radius_km and r.inputs[ALPHA_KEY] == alpha
    )
    logger.info(
        "Recommended: cheapest network at %.0f%% within %s km (today %.1f%%); Kneedle knee %.0f%%",
        100 * alpha,
        radius_km,
        100 * as_is.solution.cost.next_day_share_frac,
        100 * knee,
    )
    target = at_service(params, radius_km, alpha)
    upgrades = upgrade_options(curve, alpha)
    staging = s3_staging(target, data, recommended, upgrades)
    stress = [
        *s4_growth(target, data, recommended),
        *s5_disruption(target, data, recommended),
        *s6_fuel(target, data, recommended),
        *s7_rent_shocks(target, data, recommended),
        *s8_plants(target, data, recommended),
    ]
    headroom = rent_switching_points(target, data, recommended)
    tornado_runs, tornado = s9_tornado(target, data)
    cog = cog_networks(params, data, sweep)
    # S5 forces the busiest site out by design, so it is shown but does not classify (D-030)
    robustness = site_robustness(
        open_sets([recommended, *(r for r in stress if r.group != "S5")]),
        open_sets([cost_only, *frontier, *(r for r in stress if r.scenario_id == "S5b")]),
    )
    runs = [as_is, cost_only, *sweep, *frontier, *staging, *stress, *tornado_runs, *cog]
    return {
        "runs": runs,
        "as_is": as_is,
        "sweep": sweep,
        "frontier": frontier,
        "frontier_table": table,
        "recommended": recommended,
        "target": (radius_km, alpha),
        "knee_alpha": knee,
        "upgrades": upgrades,
        "staging": staging,
        "headroom": headroom,
        "tornado": tornado,
        "cog": cog,
        "robustness": robustness,
    }


def main() -> None:
    start = time.perf_counter()
    data_prep.main()  # raw -> processed, demand map and Checkpoint A report
    params = load_params()
    data = load_network_data()
    results = run_all(params, data)
    reporting.write_outputs(results, params, data)
    reporting.print_report(results, params, time.perf_counter() - start)


if __name__ == "__main__":
    main()
