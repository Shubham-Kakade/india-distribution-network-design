"""Scenarios S0-S9, R and the k-COG comparison (spec §9): every result in the study, from raw data.

Run from the project root: python -m src.scenarios
It rebuilds data/processed from data/raw (src.data_prep), solves every scenario, and writes
outputs/scenarios/<id>.json, outputs/scenario_summary.csv, the spec §12 charts and network maps.
Every cost comes from costs.evaluate_network through model.build_and_solve.
"""

import dataclasses
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import data_prep, viz
from src.baseline import as_is_network, solve_as_is
from src.cog import k_centres_of_gravity
from src.config import ASSUMPTIONS_PATH, entries_with_range, load_params, with_overrides
from src.costs import to_crore
from src.data_prep import (
    OUTPUTS_DIR,
    NetworkData,
    build_network_data,
    clean_raw,
    load_network_data,
    plant_table,
)
from src.demand import build_demand_points, build_zones
from src.geo import haversine_km
from src.model import COMPONENTS, Solution, build_and_solve, dc_capacity_t_yr

logger = logging.getLogger(__name__)

SCENARIO_DIR = OUTPUTS_DIR / "scenarios"
CHART_DIR = OUTPUTS_DIR / "charts"
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


def knee_alpha(curve: pd.DataFrame) -> float:
    """Knee of one radius's cost-vs-service curve (spec §9 S3; D-028).

    With both axes scaled to 0-1 between the first and last feasible points, the knee is the
    point furthest below the straight line joining them: past it, each further point of service
    costs more than the average point before it (the "Kneedle" rule).
    curve: columns alpha, total (NaN when infeasible).
    """
    feasible = curve.dropna(subset=["total"]).sort_values("alpha")
    x = (feasible["alpha"] - feasible["alpha"].min()) / np.ptp(feasible["alpha"])
    y = (feasible["total"] - feasible["total"].min()) / np.ptp(feasible["total"])
    return float(feasible["alpha"].iloc[int(np.argmax(x - y))])


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
    """S5a (operational outage) and S5b (permanent loss) of the busiest recommended DC (spec §9).

    S5a keeps the open set, re-assigns the closed site's zones with 20% capacity surge allowed and
    no service target, and charges only the change in freight for the outage months: rent, fixed
    cost and stock stay in place for a one-month outage (D-029). S5b re-optimises without the site.
    """
    rec = recommended.solution
    busiest = throughput_t_yr(rec, data).idxmax()
    cfg = params["scenarios"]
    months = cfg["disruption_months"]
    max_size_key = "warehousing.max_dc_size_sqft.value"
    surge = with_overrides(
        params,
        {
            ALPHA_KEY: 0.0,
            max_size_key: params["warehousing"]["max_dc_size_sqft"]["value"]
            * (1 + cfg["disruption_capacity_surge"]["value"]),
        },
    )
    remaining = [j for j in rec.open_dcs if j != busiest]
    outage = build_and_solve(
        surge, data, k=len(remaining), forced_open=remaining, forced_closed=[busiest]
    )
    radius_km = params["service"]["next_day_radius_km"]["value"]
    before_km, after_km = assigned_km(rec, data), assigned_km(outage, data)
    losing = before_km.index[(before_km <= radius_km) & (after_km[before_km.index] > radius_km)]
    zones = data.zones.set_index("zone_id")
    freight_change_inr = (outage.cost.primary_inr + outage.cost.secondary_inr) - (
        rec.cost.primary_inr + rec.cost.secondary_inr
    )
    s5a = Run(
        "S5a",
        "S5",
        "What if a site goes down for a month?",
        {
            "closed_dc": busiest,
            "open_set": "fixed",
            "capacity_surge": cfg["disruption_capacity_surge"]["value"],
            "months": months,
            ALPHA_KEY: 0.0,
        },
        outage,
        {
            "closed_dc": busiest,
            "freight_change_cr_per_yr": to_crore(freight_change_inr, params),
            "outage_cost_cr": to_crore(freight_change_inr * months / 12, params),
            "next_day_share_before": rec.cost.next_day_share_frac,
            "next_day_share_during": outage.cost.next_day_share_frac,
            "zones_losing_next_day": zones.loc[losing, "anchor_name"].tolist(),
            "demand_losing_next_day_t_yr": float(zones.loc[losing, "demand_t_yr"].sum()),
        },
    )
    lost = build_and_solve(params, data, forced_closed=[busiest])
    s5b = Run(
        "S5b",
        "S5",
        "What if we lose the site permanently?",
        {"excluded_dc": busiest},
        lost,
        {
            "excluded_dc": busiest,
            "penalty_cr_per_yr": to_crore(lost.cost.total_inr - rec.cost.total_inr, params)
            if lost.cost
            else None,
            **(site_changes(lost, rec) if lost.cost else {}),
        },
    )
    return [s5a, s5b]


def s6_fuel(params: dict, data: NetworkData, recommended: Run) -> list[Run]:
    """S6: diesel shocks; freight x (1 + diesel share x shock) on both legs (spec §9)."""
    runs = []
    share = params["transport"]["diesel_share_of_freight_cost"]["value"]
    for shock in params["scenarios"]["diesel_shock"]:
        multiplier = 1 + share * shock
        overrides = {
            f"transport.{rate}.value": params["transport"][rate]["value"] * multiplier
            for rate in ("primary_ftl_inr_per_tkm", "secondary_inr_per_tkm")
        }
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


def rent_switching_points(params: dict, data: NetworkData, recommended: Run) -> pd.DataFrame:
    """S7: the rent at which each recommended site drops out of the re-optimised network.

    Bisection on that site's rent alone, between today's rent and max_multiplier x today's, to
    within tolerance_inr_sqft_month. NaN means the site stays open even at the upper bound.
    Assumes a site, once dropped, stays dropped at higher rents (checked only at the bounds).
    """
    cfg = params["scenarios"]["rent_switch_search"]
    rents = data.dcs.set_index("dc_id")["rent_inr_sqft_month"]
    rows = []
    for dc in recommended.solution.open_dcs:

        def stays_open(multiplier: float, dc: str = dc) -> bool:
            return dc in build_and_solve(params, with_rents(data, {dc: multiplier})).open_dcs

        low, high = 1.0, cfg["max_multiplier"]
        if stays_open(high):
            switch_rent = np.nan
        else:
            while (high - low) * rents[dc] > cfg["tolerance_inr_sqft_month"]:
                mid = (low + high) / 2
                low, high = (mid, high) if stays_open(mid) else (low, mid)
            switch_rent = high * rents[dc]
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
            zones = data.zones
            if key.startswith("demand.") or key == "company.annual_volume_tonnes":
                zones = build_zones(build_demand_points(*cleaned, p), p)
                if not zones["zone_id"].equals(data.zones["zone_id"]):
                    raise ValueError(
                        f"{key}={value} changed the zone set; tornado assumes it fixed"
                    )
            varied = build_network_data(zones, data.dcs, data.plants, p)
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
    """k-centre-of-gravity networks costed on the same engine, against the MILP at each k (§16).

    Each centre snaps to the nearest candidate whose metro group is still free (heaviest
    cluster first); every zone goes to its nearest chosen site; plant flows come from the MILP
    with that network pinned.
    """
    zones, dcs = data.zones, data.dcs
    unconstrained = with_overrides(params, {ALPHA_KEY: 0.0})
    milp_total = {run.inputs["k"]: run.solution.cost.total_inr for run in sweep}
    runs = []
    for k in params["scenarios"]["dc_count_sweep"]:
        centres, labels = k_centres_of_gravity(zones["lat"], zones["lon"], zones["demand_t_yr"], k)
        cluster_t = zones["demand_t_yr"].groupby(labels).sum().sort_values(ascending=False)
        chosen, groups = [], set()
        for c in cluster_t.index:
            km = haversine_km(centres[c, 0], centres[c, 1], dcs["lat"], dcs["lon"])
            for i in np.argsort(km.to_numpy(), kind="stable"):
                if dcs["metro_group"].iloc[i] not in groups:
                    chosen.append(dcs["dc_id"].iloc[i])
                    groups.add(dcs["metro_group"].iloc[i])
                    break
        nearest = data.zone_dc_km[chosen].idxmin(axis=1)
        sol = build_and_solve(
            unconstrained, data, k=k, forced_open=chosen, fixed_assignment=nearest
        )
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


def site_robustness(recommended: Run, context: list[Run], stress: list[Run]) -> dict:
    """R: open/closed matrix for every site, and no-regret core vs swing sites (spec §9).

    The core is open in the recommended network and in every stress scenario at its service
    target (S4, S6, S7, S8); swing sites are open in some of them. Context columns (S1, S3, S5b)
    are shown but do not classify: S1 and S3 ask for other service levels, and S5b removes a
    site by design (D-030).
    """
    feasible = [r for r in [recommended, *stress, *context] if r.solution.cost is not None]
    columns = list(dict.fromkeys(r.scenario_id for r in feasible))
    sites = sorted({j for r in feasible for j in r.solution.open_dcs})
    matrix = pd.DataFrame(
        {r.scenario_id: [int(j in r.solution.open_dcs) for j in sites] for r in feasible},
        index=pd.Index(sites, name="dc_id"),
    )[columns]
    stress_ids = [recommended.scenario_id] + [r.scenario_id for r in stress if r.solution.cost]
    share = matrix[stress_ids].mean(axis=1)
    return {
        "matrix": matrix,
        "core": sorted(share.index[share == 1]),
        "swing": sorted(share.index[(share > 0) & (share < 1)]),
        "stress_scenarios": stress_ids,
    }


# --- Outputs --------------------------------------------------------------------------------


def run_record(run: Run, params: dict, assumptions_sha256: str) -> dict:
    """The JSON record of one scenario: inputs, solve statistics, network and cost (spec §9)."""
    sol, cost = run.solution, run.solution.cost
    record = {
        "scenario_id": run.scenario_id,
        "group": run.group,
        "question": run.question,
        "inputs": run.inputs,
        "assumptions_sha256": assumptions_sha256,
        "status": sol.status,
        "solve": {
            "objective_cr": to_crore(sol.objective_inr, params) if sol.objective_inr else None,
            "best_bound_cr": to_crore(sol.best_bound_inr, params) if sol.best_bound_inr else None,
            "mip_gap_frac": sol.gap_frac,
            "proxy_gap_frac": sol.proxy_gap_frac,
            "solve_time_s": sol.solve_time_s,
        },
        "open_dcs": list(sol.open_dcs),
        "extra": run.extra,
    }
    if cost is not None:
        record["cost_cr"] = {
            **{c: to_crore(getattr(cost, f"{c}_inr"), params) for c in COMPONENTS},
            "total": to_crore(cost.total_inr, params),
        }
        record["service"] = {
            "next_day_share_frac": cost.next_day_share_frac,
            "two_day_share_frac": cost.two_day_share_frac,
        }
        record["share_of_revenue_frac"] = cost.share_of_revenue_frac
        record["assignment"] = sol.assignment.to_dict()
        record["flows_t_yr"] = sol.flows.to_dict("records")
    return record


def summary_row(run: Run, params: dict, recommended_total_inr: float) -> dict:
    """One row of outputs/scenario_summary.csv; costs blank when the scenario is infeasible."""
    sol, cost = run.solution, run.solution.cost
    row = {
        "scenario_id": run.scenario_id,
        "group": run.group,
        "question": run.question,
        "status": sol.status,
        "n_dcs": len(sol.open_dcs),
        "open_dcs": " ".join(sol.open_dcs),
    }
    if cost is not None:
        row |= {f"{c}_cr": to_crore(getattr(cost, f"{c}_inr"), params) for c in COMPONENTS}
        row |= {
            "total_cr": to_crore(cost.total_inr, params),
            "delta_vs_recommended_cr": to_crore(cost.total_inr - recommended_total_inr, params),
            "next_day_share_frac": cost.next_day_share_frac,
            "two_day_share_frac": cost.two_day_share_frac,
            "share_of_revenue_frac": cost.share_of_revenue_frac,
        }
    row |= {"mip_gap_frac": sol.gap_frac, "proxy_gap_frac": sol.proxy_gap_frac}
    return row | {"solve_time_s": sol.solve_time_s}


def write_outputs(results: dict, params: dict, data: NetworkData) -> None:
    """Scenario JSON files, the summary CSV, the §12 charts and the network maps."""
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    for stale in SCENARIO_DIR.glob("*.json"):
        stale.unlink()
    sha = hashlib.sha256(ASSUMPTIONS_PATH.read_bytes()).hexdigest()
    runs, rec = results["runs"], results["recommended"]
    for run in runs:
        record = run_record(run, params, sha)
        (SCENARIO_DIR / f"{run.scenario_id}.json").write_text(
            json.dumps(record, indent=1, default=float)
        )
    robustness = results["robustness"]
    (SCENARIO_DIR / "R.json").write_text(
        json.dumps(
            {
                "scenario_id": "R",
                "question": "Which sites are no-regret?",
                "core": robustness["core"],
                "swing": robustness["swing"],
                "stress_scenarios": robustness["stress_scenarios"],
                "open_matrix": robustness["matrix"].to_dict(),
            },
            indent=1,
        )
    )
    (SCENARIO_DIR / "S7_switching_rents.json").write_text(
        results["headroom"].to_json(orient="records", indent=1)
    )
    (SCENARIO_DIR / "S9_tornado.json").write_text(
        results["tornado"].to_json(orient="records", indent=1)
    )
    summary = pd.DataFrame([summary_row(r, params, rec.solution.cost.total_inr) for r in runs])
    summary.to_csv(OUTPUTS_DIR / "scenario_summary.csv", index=False, float_format="%.6g")
    logger.info("Wrote %d scenario JSON files and outputs/scenario_summary.csv", len(runs))
    write_charts(results, params)
    write_network_maps(results, params, data)


def breakdown_cr(solution: Solution, params: dict) -> dict[str, float]:
    return {c: to_crore(getattr(solution.cost, f"{c}_inr"), params) for c in COMPONENTS}


def write_charts(results: dict, params: dict) -> None:
    """The six spec §12 charts."""
    disclaimer = params["meta"]["disclaimer"].strip()
    sweep_cr = pd.DataFrame(
        {
            r.inputs["k"]: {
                **breakdown_cr(r.solution, params),
                "total": to_crore(r.solution.cost.total_inr, params),
            }
            for r in results["sweep"]
        }
    ).T
    cog_cr = pd.Series(
        {r.inputs["k"]: to_crore(r.solution.cost.total_inr, params) for r in results["cog"]}
    )
    viz.save_chart(
        viz.plot_cost_curve(sweep_cr, cog_cr),
        CHART_DIR / "cost_curve.png",
        "S2: cheapest network for each fixed DC count, no service target; dashed: "
        "k-centre-of-gravity network costed on the same engine.",
        disclaimer,
    )
    frontier = pd.DataFrame(
        [
            {
                "radius_km": r.inputs[RADIUS_KEY],
                "alpha": r.inputs[ALPHA_KEY],
                "total": to_crore(r.solution.cost.total_inr, params) if r.solution.cost else np.nan,
            }
            for r in results["frontier"]
        ]
    )
    rec = results["recommended"]
    knee = (
        rec.inputs[RADIUS_KEY],
        rec.inputs[ALPHA_KEY],
        to_crore(rec.solution.cost.total_inr, params),
    )
    viz.save_chart(
        viz.plot_service_frontier(frontier, knee),
        CHART_DIR / "service_frontier.png",
        "S3: free DC count; service = share of demand whose DC is within the radius by road "
        "(haversine x 1.25).",
        disclaimer,
    )
    viz.save_chart(
        viz.plot_waterfall(
            breakdown_cr(results["as_is"].solution, params), breakdown_cr(rec.solution, params)
        ),
        CHART_DIR / "as_is_vs_recommended.png",
        f"As-is: 15 state depots, Grade B rents (illustrative baseline, spec §8). Recommended: "
        f"{rec.scenario_id}.",
        disclaimer,
    )
    viz.save_chart(
        viz.plot_tornado(
            results["tornado"],
            to_crore(rec.solution.cost.total_inr, params),
            to_crore(
                results["as_is"].solution.cost.total_inr - rec.solution.cost.total_inr, params
            ),
        ),
        CHART_DIR / "tornado.png",
        "S9: each low/medium-confidence parameter at its range ends (data/assumptions.yaml); "
        "network re-optimised, as-is re-costed.",
        disclaimer,
    )
    viz.save_chart(
        viz.plot_site_robustness(
            results["robustness"]["matrix"], len(results["robustness"]["stress_scenarios"])
        ),
        CHART_DIR / "site_robustness.png",
        f"No-regret core (open in {results['recommended'].scenario_id} and every S4-S8 stress "
        f"scenario): {', '.join(results['robustness']['core'])}.",
        disclaimer,
    )
    viz.save_chart(
        viz.plot_rent_headroom(
            results["headroom"], params["scenarios"]["rent_switch_search"]["max_multiplier"]
        ),
        CHART_DIR / "rent_headroom.png",
        "S7: one site's rent raised at a time, network re-optimised; bisection to INR 0.25.",
        disclaimer,
    )
    logger.info("Wrote 6 charts to outputs/charts/")


def write_network_maps(results: dict, params: dict, data: NetworkData) -> None:
    """outputs/network_<scenario>.html for the as-is, cost-only, recommended and S5 networks."""
    disclaimer = params["meta"]["disclaimer"].strip()
    radius_km = results["recommended"].inputs[RADIUS_KEY]
    ring_gc_km = radius_km / params["distance"]["circuity_factor"]["value"]
    by_id = {r.scenario_id: r for r in results["runs"]}
    as_is_data, _ = as_is_network(params, data)
    maps = [("S0", as_is_data), ("S1", data), (results["recommended"].scenario_id, data)]
    maps += [("S5a", data), ("S5b", data)]
    for scenario_id, network in maps:
        run = by_id[scenario_id]
        cost = run.solution.cost
        title = (
            f"{scenario_id}: {run.question} {len(run.solution.open_dcs)} DCs, "
            f"INR {to_crore(cost.total_inr, params):.1f} Cr/yr, "
            f"{cost.next_day_share_frac:.0%} of demand within {radius_km} km"
        )
        viz.plot_network_map(network, run.solution, radius_km, ring_gc_km, title, disclaimer).save(
            OUTPUTS_DIR / f"network_{scenario_id}.html"
        )
    logger.info("Wrote %d network maps", len(maps))


# --- Orchestration --------------------------------------------------------------------------


def run_all(params: dict, data: NetworkData) -> dict:
    """Solve every scenario in dependency order: S3's knee fixes the recommended network, which
    S4-S9 and R stress-test at its service target."""
    as_is = s0_as_is(params, data)
    cost_only = s1_cost_only(params, data)
    sweep = s2_dc_count(params, data)
    frontier = s3_service_frontier(params, data)
    radius_km = params["service"]["next_day_radius_km"]["value"]
    curve = pd.DataFrame(
        [
            {
                "alpha": r.inputs[ALPHA_KEY],
                "total": r.solution.cost.total_inr if r.solution.cost else np.nan,
            }
            for r in frontier
            if r.inputs[RADIUS_KEY] == radius_km
        ]
    )
    alpha = knee_alpha(curve)
    recommended = next(
        r for r in frontier if r.inputs[RADIUS_KEY] == radius_km and r.inputs[ALPHA_KEY] == alpha
    )
    logger.info("Recommended network: knee of the %s km frontier at %.0f%%", radius_km, 100 * alpha)
    target = at_service(params, radius_km, alpha)
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
    # S5 forces the busiest site out by design, so it is shown but does not classify
    robustness = site_robustness(
        recommended,
        [cost_only, *frontier, *(r for r in stress if r.group == "S5" and r.scenario_id != "S5a")],
        [r for r in stress if r.group != "S5"],
    )
    runs = [as_is, cost_only, *sweep, *frontier, *stress, *tornado_runs, *cog]
    return {
        "runs": runs,
        "as_is": as_is,
        "sweep": sweep,
        "frontier": frontier,
        "recommended": recommended,
        "headroom": headroom,
        "tornado": tornado,
        "cog": cog,
        "robustness": robustness,
    }


def print_report(results: dict, params: dict, elapsed_s: float) -> None:
    """Print the Checkpoint C summary: headline results and every infeasible combination."""
    rec, as_is = results["recommended"], results["as_is"]
    cr = lambda x_inr: to_crore(x_inr, params)  # noqa: E731
    infeasible = [r.scenario_id for r in results["runs"] if r.solution.cost is None]
    by_id = {r.scenario_id: r for r in results["runs"]}
    lines = [
        "",
        "=" * 96,
        f"CHECKPOINT C REPORT (spec §9, §12, §13): {len(results['runs'])} runs, {elapsed_s:.0f} s",
        "=" * 96,
        f"Recommended ({rec.scenario_id}, knee of the frontier): {len(rec.solution.open_dcs)} DCs, "
        f"INR {cr(rec.solution.cost.total_inr):.1f} Cr, "
        f"next-day {rec.solution.cost.next_day_share_frac:.1%}",
        f"  Sites: {', '.join(rec.solution.open_dcs)}",
        f"  Saving vs as-is (S0, INR {cr(as_is.solution.cost.total_inr):.1f} Cr): "
        f"INR {cr(as_is.solution.cost.total_inr - rec.solution.cost.total_inr):.1f} Cr per year",
        f"  No-regret core: {', '.join(results['robustness']['core'])}",
        f"  Swing sites: {', '.join(results['robustness']['swing'])}",
        f"Infeasible combinations: {', '.join(infeasible) or 'none'}",
        "",
        f"  {'scenario':<26}{'status':<24}{'DCs':>4}{'total Cr':>10}{'d rec':>8}"
        f"{'next-day':>10}  notes",
    ]
    for run in results["runs"]:
        if run.group in ("S9", "COG", "S2"):
            continue  # summarised below
        cost = run.solution.cost
        if cost is None:
            lines.append(f"  {run.scenario_id:<26}{run.solution.status:<24}")
            continue
        notes = {k: v for k, v in run.extra.items() if k in ("added", "dropped") and v}
        lines.append(
            f"  {run.scenario_id:<26}{run.solution.status:<24}{len(run.solution.open_dcs):>4}"
            f"{cr(cost.total_inr):>10.1f}{cr(cost.total_inr - rec.solution.cost.total_inr):>+8.1f}"
            f"{cost.next_day_share_frac:>10.1%}  {notes or ''}"
        )
    s5a = by_id["S5a"].extra
    lines += [
        "",
        f"S5a outage of {s5a['closed_dc']}: freight "
        f"+INR {s5a['freight_change_cr_per_yr']:.1f} Cr/yr "
        f"(INR {s5a['outage_cost_cr']:.2f} Cr for the outage); next-day "
        f"{s5a['next_day_share_before']:.1%} -> {s5a['next_day_share_during']:.1%}; "
        f"{len(s5a['zones_losing_next_day'])} zones lose next-day",
        "",
        "S7 rent headroom (INR/sq ft/month; blank = stays open at the search bound):",
        results["headroom"].round(2).to_string(index=False),
        "",
        "S9 tornado (INR Cr; widest swing first):",
        results["tornado"][
            ["label", "low_total", "high_total", "low_dcs", "high_dcs", "low_saving", "high_saving"]
        ]
        .round(1)
        .to_string(index=False),
        "",
        "k-COG vs MILP at the same k (premium of the COG network):",
        "  "
        + ", ".join(
            f"k={r.inputs['k']}: {r.extra['premium_vs_milp_frac']:+.1%}" for r in results["cog"]
        ),
        "=" * 96,
    ]
    print("\n".join(lines))  # noqa: T201


def main() -> None:
    start = time.perf_counter()
    data_prep.main()  # raw -> processed, demand map and Checkpoint A report
    params = load_params()
    data = load_network_data()
    results = run_all(params, data)
    write_outputs(results, params, data)
    print_report(results, params, time.perf_counter() - start)


if __name__ == "__main__":
    main()
