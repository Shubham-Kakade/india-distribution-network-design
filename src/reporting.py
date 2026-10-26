"""Scenario outputs (spec §9, §12): JSON records, the summary CSV, charts, maps and the report.

Reads the results of scenarios.run_all; computes no cost of its own (every figure comes from
evaluate_network via the solutions).
"""

import hashlib
import json
import logging
from typing import TYPE_CHECKING

import pandas as pd

from src import viz
from src.baseline import as_is_network
from src.config import ASSUMPTIONS_PATH
from src.costs import to_crore
from src.data_prep import OUTPUTS_DIR, NetworkData
from src.model import COMPONENTS, Solution

if TYPE_CHECKING:  # only for type hints: scenarios.py imports this module
    from src.scenarios import Run

logger = logging.getLogger(__name__)

SCENARIO_DIR = OUTPUTS_DIR / "scenarios"
CHART_DIR = OUTPUTS_DIR / "charts"


def run_record(run: "Run", params: dict, assumptions_sha256: str) -> dict:
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


def summary_row(run: "Run", params: dict, recommended_total_inr: float) -> dict:
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
    frontier = results["frontier_table"][["radius_km", "alpha", "total_inr"]]
    frontier = frontier.assign(total=to_crore(frontier["total_inr"], params))
    rec = results["recommended"]
    radius_km, alpha = results["target"]
    knee = (radius_km, alpha, to_crore(rec.solution.cost.total_inr, params))
    viz.save_chart(
        viz.plot_service_frontier(frontier[["radius_km", "alpha", "total"]], knee),
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
    radius_km = results["target"][0]
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
