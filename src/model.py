"""Two-echelon capacitated facility-location MILP (spec §7), solved by CBC through PuLP.

The objective is a linear proxy of costs.evaluate_network; every solution is re-costed by the
evaluator, and that exact figure is the one reported.

Run from the project root: python -m src.model   (Checkpoint B report)
"""

import dataclasses
import logging
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pulp

from src.config import load_params, with_overrides
from src.costs import (
    DAYS_PER_YEAR,
    CostBreakdown,
    carrying_cost_inr_per_t_yr,
    cycle_stock_t,
    evaluate_network,
    safety_stock_t,
    space_cost_inr_sqft_yr,
    stock_area_sqft,
    to_crore,
)
from src.data_prep import NetworkData, load_network_data

logger = logging.getLogger(__name__)

MIN_FLOW_T_YR = 1e-6  # flows below this are solver noise
COMPONENTS = ["primary", "secondary", "space", "handling", "inventory", "fixed"]


@dataclass(frozen=True)
class Solution:
    """Outcome of one solve. A non-optimal status is data, not an error (spec §7)."""

    status: str  # PuLP solution status, e.g. "Optimal Solution Found", "No Solution Exists"
    objective_inr: float | None  # MILP proxy objective
    best_bound_inr: float | None
    gap_frac: float | None
    solve_time_s: float
    open_dcs: tuple[str, ...]
    assignment: pd.Series | None  # dc_id per zone_id
    flows: pd.DataFrame | None  # plant_id, dc_id, flow_t_yr
    cost: CostBreakdown | None  # exact cost from evaluate_network
    proxy_gap_frac: float | None  # (objective + constant terms) / evaluator total - 1
    passes: tuple[dict, ...] = ()  # free runs: one summary per proxy pass (D-034)


def dc_capacity_t_yr(params: dict) -> float:
    """Annual throughput a maximum-size DC can hold stock for (spec §7 constraint 3).

    Cap = max_size x utilisation x density x 365 / (cycle_days + ss_days_1)
    """
    wh = params["warehousing"]
    stock_days = wh["cycle_stock_days"]["value"] + wh["safety_stock_days_single_dc"]["value"]
    return (
        wh["max_dc_size_sqft"]["value"]
        * wh["space_utilisation"]["value"]
        * wh["storage_density_t_per_sqft"]["value"]
        * DAYS_PER_YEAR
        / stock_days
    )


def build_problem(
    params: dict,
    data: NetworkData,
    k: int | None,
    k_ref: int,
    forced_open: Sequence[str],
    forced_closed: Sequence[str],
    fixed_assignment: pd.Series | None,
) -> tuple[pulp.LpProblem, dict, dict, dict]:
    """The spec §7 MILP and its y (open), x (zone -> DC) and f (plant -> DC) variables.

    k_ref is the DC count the safety-stock proxy is sized for (spec §7, D-022, D-034).
    """
    zones = data.zones.set_index("zone_id")
    demand_t_yr = zones["demand_t_yr"]
    total_t_yr = demand_t_yr.sum()
    dcs = data.dcs.set_index("dc_id")
    unknown = sorted((set(forced_open) | set(forced_closed)) - set(dcs.index))
    if unknown:
        raise ValueError(f"forced_open/forced_closed name unknown DCs: {unknown}")
    plants = data.plants.set_index("plant_id")
    zone_dc_km = data.zone_dc_km.loc[zones.index, dcs.index]
    plant_dc_km = data.plant_dc_km.loc[plants.index, dcs.index]
    zone_dc_pairs = [(z, j) for z in zones.index for j in dcs.index]
    plant_dc_pairs = [(p, j) for p in plants.index for j in dcs.index]

    prob = pulp.LpProblem("india_dc_network", pulp.LpMinimize)
    y = pulp.LpVariable.dicts("open", dcs.index, cat=pulp.LpBinary)
    x = pulp.LpVariable.dicts("serve", zone_dc_pairs, cat=pulp.LpBinary)
    f = pulp.LpVariable.dicts("flow_t", plant_dc_pairs, lowBound=0)

    # Objective (spec §7): per-DC fixed + safety-stock proxy, per-tonne secondary + handling +
    # cycle-stock space, primary freight
    wh, transport = params["warehousing"], params["transport"]
    space_inr_sqft_yr = space_cost_inr_sqft_yr(dcs["rent_inr_sqft_month"], params)
    # Safety stock of an average DC when demand splits over k_ref DCs; the proxy charges its
    # carrying cost and, at each site's rent, its space (D-022: space was missing in §7 v2)
    ss_ref_t = safety_stock_t(total_t_yr / k_ref, total_t_yr, params)
    per_dc_inr = (
        wh["fixed_cost_per_dc_cr_per_yr"]["value"] * params["meta"]["crore"]
        + carrying_cost_inr_per_t_yr(params) * ss_ref_t
        + stock_area_sqft(ss_ref_t, params) * space_inr_sqft_yr
    )
    floor_km = params["demand"]["intra_zone_min_distance_km"]["value"]
    per_t_inr = (
        transport["secondary_inr_per_tkm"]["value"] * np.maximum(zone_dc_km, floor_km)
        + wh["handling_inr_per_tonne"]["value"]
        + stock_area_sqft(cycle_stock_t(1.0, params), params) * space_inr_sqft_yr  # s_j
    )
    primary_rate = transport["primary_ftl_inr_per_tkm"]["value"]
    prob += (
        pulp.lpSum(per_dc_inr[j] * y[j] for j in dcs.index)
        + pulp.lpSum(demand_t_yr[z] * per_t_inr.loc[z, j] * x[z, j] for z, j in zone_dc_pairs)
        + pulp.lpSum(primary_rate * plant_dc_km.loc[p, j] * f[p, j] for p, j in plant_dc_pairs)
    )

    capacity_t_yr = dc_capacity_t_yr(params)
    headroom = params["plants"]["capacity_headroom"]["value"]
    for z in zones.index:
        prob += pulp.lpSum(x[z, j] for j in dcs.index) == 1  # spec §7 (1): single sourcing
    for z, j in zone_dc_pairs:
        prob += x[z, j] <= y[j]  # spec §7 (2)
    for j in dcs.index:
        throughput = pulp.lpSum(demand_t_yr[z] * x[z, j] for z in zones.index)
        prob += throughput <= capacity_t_yr * y[j]  # spec §7 (3): capacity
        prob += pulp.lpSum(f[p, j] for p in plants.index) == throughput  # spec §7 (4): balance
    for p in plants.index:
        # spec §7 (5): plant capacity = share x national demand x headroom
        prob += pulp.lpSum(f[p, j] for j in dcs.index) <= (
            plants.loc[p, "share_frac"] * total_t_yr * headroom
        )
    # spec §7 (6): service, on unfloored road km (D-016)
    service = params["service"]
    within = zone_dc_km <= service["next_day_radius_km"]["value"]
    prob += pulp.lpSum(demand_t_yr[z] * x[z, j] for z, j in zone_dc_pairs if within.loc[z, j]) >= (
        service["min_share_within_radius"]["value"] * total_t_yr
    )
    for group in sorted(dcs["metro_group"].unique()):
        members = dcs.index[dcs["metro_group"] == group]
        prob += pulp.lpSum(y[j] for j in members) <= 1  # spec §7 (7): one site per metro
    # spec §7 (8): optional DC count, forced opens and closures, fixed assignment
    if k is not None:
        prob += pulp.lpSum(y.values()) == k
    for j in forced_open:
        prob += y[j] == 1
    for j in forced_closed:
        prob += y[j] == 0
    if fixed_assignment is not None:
        for z, j in fixed_assignment.items():
            prob += x[z, j] == 1
    return prob, y, x, f


def solve_once(
    params: dict,
    data: NetworkData,
    k: int | None,
    k_ref: int,
    forced_open: Sequence[str],
    forced_closed: Sequence[str],
    fixed_assignment: pd.Series | None,
) -> Solution:
    """One CBC solve of the spec §7 MILP with the proxy sized for k_ref DCs, then the exact cost
    of its solution from evaluate_network."""
    prob, y, x, f = build_problem(
        params, data, k, k_ref, forced_open, forced_closed, fixed_assignment
    )
    cfg = params["solver"]
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "cbc.log"
        prob.solve(
            pulp.PULP_CBC_CMD(
                msg=cfg["log"],
                gapRel=cfg["mip_gap"],
                timeLimit=cfg["time_limit_s"],
                threads=cfg["threads"],
                logPath=str(log_path),
            )
        )
        cbc_log = log_path.read_text()
    status = pulp.LpSolution[prob.sol_status]
    if prob.sol_status not in (pulp.LpSolutionOptimal, pulp.LpSolutionIntegerFeasible):
        logger.info("Solve k=%s k_ref=%s: %s in %.1f s", k, k_ref, status, prob.solutionTime)
        return Solution(status, None, None, None, prob.solutionTime, (), None, None, None, None)

    objective_inr = pulp.value(prob.objective)
    # CBC prints a lower bound only when it stops short of proving optimality
    bound = re.search(r"Lower bound:\s+(\S+)", cbc_log)
    best_bound_inr = float(bound.group(1)) if bound else objective_inr
    gap_frac = (objective_inr - best_bound_inr) / objective_inr
    open_dcs = tuple(j for j in data.dcs["dc_id"] if y[j].value() > 0.5)
    assignment = pd.Series(
        {z: j for (z, j), var in x.items() if var.value() > 0.5}, name="dc_id"
    ).rename_axis("zone_id")
    flows = pd.DataFrame(
        [(p, j, var.value()) for (p, j), var in f.items() if var.value() > MIN_FLOW_T_YR],
        columns=["plant_id", "dc_id", "flow_t_yr"],
    )
    cost = evaluate_network(open_dcs, assignment, flows, params, data)

    # The MILP drops the cycle-stock carrying cost, which is the same for every network; add it
    # back so the proxy can be compared with the exact total (spec §7 proxy fidelity check)
    total_t_yr = data.zones["demand_t_yr"].sum()
    constant_inr = carrying_cost_inr_per_t_yr(params) * cycle_stock_t(total_t_yr, params)
    proxy_gap_frac = (objective_inr + constant_inr) / cost.total_inr - 1
    # D-027: the 3% limit binds where k_ref = k (sweep runs); free runs report the gap only
    tolerance = params["checks"]["proxy_gap_tolerance_frac"]["value"]
    if k is not None and abs(proxy_gap_frac) > tolerance:
        logger.warning(
            "Solve k=%s: MILP proxy differs from evaluator by %+.1f%%", k, 100 * proxy_gap_frac
        )
    logger.info(
        "Solve k=%s k_ref=%s: %s, %d DCs, INR %.1f Cr, gap %.2f%%, %.1f s",
        k,
        k_ref,
        status,
        len(open_dcs),
        to_crore(cost.total_inr, params),
        100 * gap_frac,
        prob.solutionTime,
    )
    return Solution(
        status=status,
        objective_inr=objective_inr,
        best_bound_inr=best_bound_inr,
        gap_frac=gap_frac,
        solve_time_s=prob.solutionTime,
        open_dcs=open_dcs,
        assignment=assignment,
        flows=flows,
        cost=cost,
        proxy_gap_frac=proxy_gap_frac,
    )


def pass_summary(solution: Solution, k_ref: int) -> dict:
    """What one proxy pass found, for the scenario record (D-034)."""
    return {
        "k_ref": k_ref,
        "status": solution.status,
        "n_dcs": len(solution.open_dcs),
        "open_dcs": list(solution.open_dcs),
        "total_inr": solution.cost.total_inr if solution.cost else None,
        "proxy_gap_frac": solution.proxy_gap_frac,
        "solve_time_s": solution.solve_time_s,
    }


def build_and_solve(
    params: dict,
    data: NetworkData,
    k: int | None = None,
    forced_open: Sequence[str] = (),
    forced_closed: Sequence[str] = (),
    fixed_assignment: pd.Series | None = None,
) -> Solution:
    """Solve the spec §7 MILP with CBC; every reported cost is the exact evaluate_network figure.

    k fixes the number of open DCs and sizes the safety-stock proxy for it. A free run (k None)
    is two-pass (D-034): the proxy is first sized for ss_proxy_k_ref_free_runs DCs, then re-sized
    for the k* DCs that pass opened, and the solution with the lower EXACT cost is kept (ties
    keep the first), so a mis-sized proxy cannot choose a costlier network. Both passes are
    recorded in Solution.passes. fixed_assignment pins each zone (indexed by zone_id) to a DC.
    """
    if k is not None:
        return solve_once(params, data, k, k, forced_open, forced_closed, fixed_assignment)
    k_ref = params["solver"]["ss_proxy_k_ref_free_runs"]["value"]
    first = solve_once(params, data, None, k_ref, forced_open, forced_closed, fixed_assignment)
    passes = [pass_summary(first, k_ref)]
    best = first
    # The proxy changes only the objective, so an infeasible first pass stays infeasible
    if first.cost is not None and len(first.open_dcs) != k_ref:
        k_star = len(first.open_dcs)
        second = solve_once(
            params, data, None, k_star, forced_open, forced_closed, fixed_assignment
        )
        passes.append(pass_summary(second, k_star))
        if second.cost is not None and second.cost.total_inr < first.cost.total_inr:
            best = second
    total_time_s = sum(p["solve_time_s"] for p in passes)
    return dataclasses.replace(best, solve_time_s=total_time_s, passes=tuple(passes))


def breakdown_cr(cost: CostBreakdown, params: dict) -> list[float]:
    """Components in spec §3 column order, then the total, in INR Cr."""
    parts = [getattr(cost, f"{c}_inr") for c in COMPONENTS] + [cost.total_inr]
    return [to_crore(v, params) for v in parts]


def print_checkpoint_b_report(
    base: Solution, sweep: dict[int, Solution], as_is: Solution, params: dict
) -> None:
    """Print the spec §3 tables next to the supervisor prototype, with solve statistics."""
    checks = params["checks"]
    prototype = checks["prototype_k_sweep"]["value"]
    tolerance = checks["prototype_tolerance_frac"]["value"]
    header = f"  {'DCs':<7}" + "".join(f"{c.title():>10}" for c in COMPONENTS)
    header += f"{'Total':>9}{'<=400km':>9}{'d Total':>9}"
    lines = [
        "",
        "=" * 100,
        "CHECKPOINT B REPORT (spec §3, §13). INR Cr per year; evaluator figures",
        "=" * 100,
        "Cost by number of DCs, no service constraint (proto = supervisor prototype, spec §3):",
        header,
    ]
    for k, sol in sweep.items():
        cr = breakdown_cr(sol.cost, params)
        row = f"  {k:<7}" + "".join(f"{v:>10.1f}" for v in cr[:-1])
        row += f"{cr[-1]:>9.1f}{sol.cost.next_day_share_frac:>9.0%}"
        if k in prototype:
            ref = prototype[k]
            diff_frac = cr[-1] / ref[6] - 1
            flag = "" if abs(diff_frac) <= tolerance else "  <-- above tolerance"
            lines.append(f"{row}{diff_frac:>+9.1%}{flag}")
            lines.append(
                f"  {'proto':<7}"
                + "".join(f"{v:>10.1f}" for v in ref[:6])
                + f"{ref[6]:>9.1f}{ref[7]:>9.0%}"
            )
        else:
            lines.append(row)

    base_dcs, base_total = checks["prototype_base_case"]["value"]
    as_is_total, as_is_share = checks["prototype_as_is"]["value"]
    base_cr, as_is_cr = breakdown_cr(base.cost, params), breakdown_cr(as_is.cost, params)
    lines += [
        "",
        f"Base case (400 km / 80%): {base.cost.n_dcs} DCs, INR {base_cr[-1]:.1f} Cr "
        f"({base.cost.share_of_revenue_frac:.2%} of revenue), next-day "
        f"{base.cost.next_day_share_frac:.1%}, two-day {base.cost.two_day_share_frac:.1%}; "
        f"proto {base_dcs} DCs, {base_total} Cr ({base_cr[-1] / base_total - 1:+.1%})",
        f"  Sites: {', '.join(base.open_dcs)}",
        "  Components: "
        + ", ".join(f"{c} {v:.1f}" for c, v in zip(COMPONENTS, base_cr, strict=False)),
        f"As-is (15 state depots, Grade B): INR {as_is_cr[-1]:.1f} Cr, next-day "
        f"{as_is.cost.next_day_share_frac:.1%}; proto {as_is_total} Cr, {as_is_share:.0%} "
        f"({as_is_cr[-1] / as_is_total - 1:+.1%})",
        "  Components: "
        + ", ".join(f"{c} {v:.1f}" for c, v in zip(COMPONENTS, as_is_cr, strict=False)),
        f"Saving, base case vs as-is: INR {as_is_cr[-1] - base_cr[-1]:.1f} Cr per year "
        f"({1 - base_cr[-1] / as_is_cr[-1]:.1%})",
        "",
        "Solve statistics (proxy gap = MILP objective plus constant terms vs evaluator, limit "
        f"{checks['proxy_gap_tolerance_frac']['value']:.0%}):",
        f"  {'run':<10}{'status':<26}{'DCs':>4}{'objective':>11}{'bound':>9}{'MIP gap':>9}"
        f"{'proxy gap':>11}{'time s':>8}",
    ]
    runs = {"base": base, **{f"k={k}": sol for k, sol in sweep.items()}, "as-is": as_is}
    lines += [
        f"  {name:<10}{sol.status:<26}{len(sol.open_dcs):>4}"
        f"{to_crore(sol.objective_inr, params):>11.1f}{to_crore(sol.best_bound_inr, params):>9.1f}"
        f"{sol.gap_frac:>9.2%}{sol.proxy_gap_frac:>+11.1%}{sol.solve_time_s:>8.1f}"
        for name, sol in runs.items()
    ]
    lines.append("=" * 100)
    print("\n".join(lines))  # noqa: T201


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from src.baseline import solve_as_is  # baseline imports this module, so import it late

    params = load_params()
    data = load_network_data()
    base = build_and_solve(params, data)
    unconstrained = with_overrides(params, {"service.min_share_within_radius.value": 0.0})
    sweep = {
        k: build_and_solve(unconstrained, data, k=k) for k in params["scenarios"]["dc_count_sweep"]
    }
    print_checkpoint_b_report(base, sweep, solve_as_is(params, data), params)


if __name__ == "__main__":
    main()
