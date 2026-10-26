"""Deterministic answers from tool results, and the offline library (spec §10).

describe() turns one tool result into plain sentences. It writes the live agent's templated
fallback (when a reply fails the grounding check twice) and every offline answer, so both are
grounded by construction. The offline library pre-computes 20 common questions with the same
tools; offline answers need no network and no solver.

Build the library from the project root: python -m src.agent_offline
"""

import json
import logging
import re
from dataclasses import dataclass

from src.data_prep import OUTPUTS_DIR

logger = logging.getLogger(__name__)

LIBRARY_PATH = OUTPUTS_DIR / "agent_library.json"
TOP_ROWS = 5  # tornado rows and largest sites shown in a templated answer


# --- Deterministic answers ------------------------------------------------------------------


def site_list(sites: list[dict]) -> str:
    return ", ".join(f"{s['name']} ({s['dc_id']})" for s in sites)


def network_line(r: dict) -> str:
    """One sentence on a network summary: DCs, cost, change against recommended, service."""
    if "cost_cr_per_yr" not in r:
        return f"{r['scenario_id']}: {r['status']}; no feasible network for these inputs."
    vs = r["vs_recommended"]
    is_recommended = r["scenario_id"] == vs["recommended_id"]
    overrides = ", ".join(f"{k} = {v:g}" for k, v in r.get("overrides", {}).items())
    text = (
        f"{r['scenario_id']}{f' ({overrides})' if overrides else ''}: {r['n_dcs']} DCs at INR "
        f"{r['cost_cr_per_yr']['total']:.1f} Cr a year"
        + (
            ""
            if is_recommended
            else f" ({vs['delta_total_cr']:+.1f} Cr against {vs['recommended_id']})"
        )
        + f", {100 * r['next_day_share_frac']:.1f}% of demand next-day."
    )
    changes = []
    if vs["added"]:
        changes.append(f"opens {', '.join(vs['added'])}")
    if vs["dropped"]:
        changes.append(f"closes {', '.join(vs['dropped'])}")
    if not is_recommended:
        text += (
            f" Against the recommended network it {' and '.join(changes)}."
            if changes
            else " It keeps the recommended sites."
        )
    return text


def describe_disruption(r: dict) -> str:
    site = r["closed_site"]
    if r["mode"] == "operational":
        o = r["outage"]
        moved = ", ".join(f"{j} ({n})" for j, n in o["reassigned_zones_by_site"].items())
        return (
            f"{r['scenario_id']}: with {site['name']} ({site['dc_id']}) shut for "
            f"{o['months']:g} month(s), the other {r['n_dcs']} sites absorb its zones "
            f"(zones moved to {moved}). Extra freight runs at INR "
            f"{o['freight_change_cr_per_yr']:.1f} Cr a year, so the outage costs about INR "
            f"{o['outage_cost_cr']:.1f} Cr, a floor: {o['not_costed']} are not costed. "
            f"Next-day coverage falls from {100 * o['next_day_share_before_frac']:.1f}% to "
            f"{100 * o['next_day_share_during_frac']:.1f}%, and "
            f"{o['zones_losing_next_day_count']} zones "
            f"({100 * o['demand_losing_next_day_frac']:.1f}% of demand) lose next-day delivery."
        )
    penalty = r["permanent_loss"]["penalty_cr_per_yr"]
    if penalty is None:
        return network_line(r)
    return (
        f"{network_line(r)} Losing {site['name']} ({site['dc_id']}) for good therefore costs INR "
        f"{abs(penalty):.1f} Cr a year {'more' if penalty >= 0 else 'less'} than the "
        "recommended network, once the network is re-optimised without it."
    )


def describe_explain(r: dict) -> str:
    if "cost_cr_per_yr" not in r:
        return network_line(r)
    c = r["cost_cr_per_yr"]
    parts = ", ".join(
        f"{k} {c[k]:.1f}"
        for k in ("primary", "secondary", "space", "handling", "inventory", "fixed")
    )
    largest = sorted(r["sites"], key=lambda s: -s["throughput_t_yr"])[:TOP_ROWS]
    sites = "; ".join(
        f"{s['name']} ({s['dc_id']}) {s['throughput_t_yr']:,.0f} t/yr, "
        f"{100 * s['share_of_volume_frac']:.1f}% of volume"
        for s in largest
    )
    return (
        f"{network_line(r)} Sites: {site_list(r['sites'])}. Cost by component (INR Cr a year): "
        f"{parts}; {100 * r['share_of_revenue_frac']:.1f}% of revenue. Busiest sites: {sites}."
    )


def describe_compare(r: dict) -> str:
    lines = []
    for s in r["scenarios"]:
        if "cost_cr_per_yr" in s:
            lines.append(
                f"- {s['scenario_id']} ({s['question']}): {s['n_dcs']} DCs, INR "
                f"{s['cost_cr_per_yr']['total']:.1f} Cr a year "
                f"({s['delta_total_vs_recommended_cr']:+.1f} against {r['recommended_id']}), "
                f"{100 * s['next_day_share_frac']:.1f}% next-day."
            )
        else:
            lines.append(f"- {s['scenario_id']}: {s['status']}.")
    return "\n".join(lines)


def describe_ranking(r: dict) -> str:
    lines = [
        f"{r['source_id']}: each uncertain assumption moved to both ends of its range, with the "
        f"network re-optimised (base {r['recommended_id']}: INR {r['base_total_cr']:.1f} Cr, "
        f"{r['base_n_dcs']} DCs, saving INR {r['base_saving_vs_as_is_cr']:.1f} Cr against "
        f"today). Widest cost swings:"
    ]
    for row in r["rows"][:TOP_ROWS]:
        dcs = (
            f"{row['low_n_dcs']} DCs at both ends"
            if row["low_n_dcs"] == row["high_n_dcs"]
            else f"{row['low_n_dcs']} to {row['high_n_dcs']} DCs"
        )
        lines.append(
            f"- {row['range_label']}: total INR {row['low_total_cr']:.1f} to "
            f"{row['high_total_cr']:.1f} Cr, {dcs}, "
            f"saving INR {row['low_saving_vs_as_is_cr']:.1f} to "
            f"{row['high_saving_vs_as_is_cr']:.1f} Cr."
        )
    return "\n".join(lines)


def describe_source(r: dict) -> str:
    return "; ".join(f"{k}: {v}" for k, v in r.items())


def describe_parameters(r: dict) -> str:
    return "\n".join(
        f"- {p['key']}: {p['value']} (range {p['range']}, {p['confidence']} confidence)"
        for p in r["parameters"]
    )


DESCRIBERS = {
    "simulate_disruption": describe_disruption,
    "explain_network": describe_explain,
    "compare_scenarios": describe_compare,
    "rank_assumptions": describe_ranking,
    "get_assumption_source": describe_source,
    "list_parameters": describe_parameters,
    "run_scenario": network_line,
}


def describe(tool: str, result: dict) -> str:
    """Plain-language summary of one tool result; every number is formatted from the result."""
    if "error" in result:
        return f"Refused: {result['error']}"
    return DESCRIBERS[tool](result)


# --- The offline library --------------------------------------------------------------------

SITE_ALIASES = {  # library sites: display name, then the words that name them
    "BLR_HSR": ("Hosur", "hosur", "bengaluru", "bangalore"),
    "NCR_FRN": ("NCR", "ncr", "delhi", "farrukhnagar", "gurgaon", "gurugram"),
    "MUM_BHW": ("Mumbai", "mumbai", "bhiwandi", "bombay"),
}
PERMANENT = r"permanent|for good|lost|lose|never reopen|close for ever"
OUTAGE = r"month|week|shut|outage|down|closed|disrupt|fire|flood|strike"


@dataclass(frozen=True)
class Intent:
    """One library entry: the patterns that must all match, the site it needs, and its calls."""

    intent_id: str
    example: str
    required: tuple[str, ...]
    calls: tuple[tuple[str, dict], ...]
    site: str | None = None


def library_intents(recommended_id: str) -> list[Intent]:
    """The 20 pre-computed questions, most specific first (the first full match wins)."""
    rec = recommended_id
    intents = []
    for dc, (name, *_) in SITE_ALIASES.items():
        intents += [
            Intent(
                f"loss_{dc}",
                f"And if we lost {name} permanently?",
                (PERMANENT,),
                (("simulate_disruption", {"dc_id": dc, "mode": "strategic"}),),
                dc,
            ),
            Intent(
                f"outage_{dc}",
                f"What if {name} shuts for a month?",
                (OUTAGE,),
                (("simulate_disruption", {"dc_id": dc, "mode": "operational", "months": 1}),),
                dc,
            ),
        ]
    compare = "compare_scenarios"
    intents += [
        Intent(
            "diesel_40",
            "What if diesel rises 40%?",
            (r"diesel|fuel", r"\b40\b"),
            (("run_scenario", {"name": "diesel_40", "overrides": {"diesel_shock_frac": 0.4}}),),
        ),
        Intent(
            "diesel_20",
            "Diesel just went up 20%. Should we change anything?",
            (r"diesel|fuel",),
            (("run_scenario", {"name": "diesel_20", "overrides": {"diesel_shock_frac": 0.2}}),),
        ),
        Intent(
            "service_90_95",
            "What would 90% or 95% next-day cost?",
            (r"\b9[05]\b",),
            ((compare, {"ids": [rec, "S3_400km_85", "S3_400km_90", "S3_400km_95"]}),),
        ),
        Intent(
            "service_85",
            "What would it cost to reach 85% next-day?",
            (r"upgrade|\b85\b|faster|better service|higher service|more next.?day",),
            ((compare, {"ids": [rec, "S3_400km_85", f"{rec}_staged"]}),),
        ),
        Intent(
            "growth",
            "What if demand grows 30%?",
            (r"grow|growth|expan|more demand|volume",),
            ((compare, {"ids": [rec, "S4_uniform", "S4_regional_skew"]}),),
        ),
        Intent(
            "rent",
            "What if rents rise 20%?",
            (r"rent|real estate|lease|warehouse cost",),
            ((compare, {"ids": [rec, "S7_rent_minus_20", "S7_rent_plus_20"]}),),
        ),
        Intent(
            "no_puducherry",
            "What if we close the Puducherry plant?",
            (r"puducherry|pondicherry",),
            ((compare, {"ids": [rec, "S8_no_puducherry"]}),),
        ),
        Intent(
            "east_plant",
            "What if we add a plant in the East?",
            (r"plant|factory", r"east|kolkata|howrah|new|add|another"),
            ((compare, {"ids": [rec, "S8_add_east"]}),),
        ),
        Intent(
            "assumptions",
            "Which of our assumptions should I worry about most?",
            (r"assumption|sensitiv|uncertain|tornado|worry|risk",),
            (("rank_assumptions", {}),),
        ),
        Intent(
            "cog",
            "Why not just use centre of gravity?",
            (r"cent(re|er) of gravity|\bcog\b",),
            ((compare, {"ids": ["S2_k09", "COG_k09"]}),),
        ),
        Intent(
            "dc_count",
            "How many DCs should we run?",
            (r"how many|number of (dc|site|warehouse)",),
            ((compare, {"ids": ["S2_k04", "S2_k06", "S2_k08", "S2_k09", "S2_k10", "S2_k12"]}),),
        ),
        Intent(
            "cheapest",
            "What is the cheapest possible network?",
            (r"cheapest|lowest cost|minimum cost|cost only",),
            ((compare, {"ids": ["S1", rec]}),),
        ),
        Intent(
            "as_is",
            "What does today's network cost, and what do we save?",
            (r"today|current|as.?is|existing|saving|save",),
            ((compare, {"ids": ["S0", rec]}),),
        ),
        Intent(
            "recommended",
            "What's our recommended network and what does it cost?",
            (r"recommend|proposed|our network|which sites|where",),
            (("explain_network", {"scenario_id": rec}),),
        ),
    ]
    return intents


def mentioned_site(question: str) -> str | None:
    """The library site a question names, if any ("Hosur" -> BLR_HSR)."""
    q = question.lower()
    for dc, (_, *aliases) in SITE_ALIASES.items():
        if dc.lower() in q or any(re.search(rf"\b{a}\b", q) for a in aliases):
            return dc
    return None


def match_intent(question: str, intents: list[Intent], last_site: str | None) -> Intent | None:
    """First intent whose patterns all match; a site intent also needs its site named in the
    question or, for follow-ups like "and if we lost it?", in the previous question."""
    site = mentioned_site(question) or last_site
    for intent in intents:
        if intent.site is not None and intent.site != site:
            continue
        if all(re.search(p, question, re.IGNORECASE) for p in intent.required):
            return intent
    return None


def build_library(toolbox) -> dict:
    """Run every library call through the tools and keep the results plus agent-made records."""
    entries = []
    for intent in library_intents(toolbox.recommended_id):
        results = [[name, toolbox.call(name, args)] for name, args in intent.calls]
        entries.append(
            {
                "intent_id": intent.intent_id,
                "example": intent.example,
                "calls": [list(c) for c in intent.calls],
                "results": results,
            }
        )
        logger.info("Library entry %s built", intent.intent_id)
    return {
        "recommended_id": toolbox.recommended_id,
        "assumptions_sha256": toolbox.assumptions_sha256,
        "entries": entries,
        "records": toolbox.records,  # agent-made networks, so offline answers can be mapped
    }


def main() -> None:
    from src.agent_tools import ToolBox
    from src.config import load_params
    from src.data_prep import load_network_data

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    library = build_library(ToolBox(load_params(), load_network_data()))
    LIBRARY_PATH.write_text(json.dumps(library, indent=1))
    logger.info("Wrote %d entries to %s", len(library["entries"]), LIBRARY_PATH)


if __name__ == "__main__":
    main()
