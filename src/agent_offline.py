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
# Every answer has the same six labelled parts (D-049): a direct headline, what changes in the
# network, why (the cost drivers and their mechanism), what it means for the client, the
# assumptions and limits, and the source scenario ids. Every number is formatted from the tool
# result, so the answers pass the grounding check by construction.

STRUCTURE = (
    "Headline",
    "What happens in the network",
    "Why",
    "What it means for the client",
    "Assumptions and limits",
    "Source",
)
COMPONENT_LABELS = {
    "primary": "primary (plant-to-DC) freight",
    "secondary": "secondary (last-mile) freight",
    "space": "warehouse space",
    "handling": "handling",
    "inventory": "inventory carrying cost",
    "fixed": "fixed site cost",
}
MECHANISM = {  # (component, rises) -> why it moves; true whatever the cause (volume, sites, rates)
    ("primary", True): "more tonne-km on inbound lanes from the plants",
    ("primary", False): "fewer tonne-km on inbound lanes from the plants",
    ("secondary", True): "more tonne-km on last-mile lanes, e.g. zones served from further away",
    ("secondary", False): "fewer tonne-km on last-mile lanes, as DCs sit closer to demand",
    ("space", True): "more or dearer warehouse space",
    ("space", False): "less or cheaper warehouse space",
    ("handling", True): "more tonnes handled",
    ("handling", False): "fewer tonnes handled",
    ("inventory", True): "more stock to hold: more volume, or stock split across more sites",
    ("inventory", False): "less stock to hold: stock pooled in fewer sites",
    ("fixed", True): "more sites to run",
    ("fixed", False): "fewer sites to run",
}
PARAMETER_NAMES = {  # plain names for the S9 tornado parameters (last part of the YAML key)
    "annual_volume_tonnes": "annual volume",
    "circuity_factor": "road circuity",
    "primary_ftl_inr_per_tkm": "primary freight rate",
    "secondary_inr_per_tkm": "secondary freight rate",
    "fixed_cost_per_dc_cr_per_yr": "fixed cost per DC",
    "safety_stock_days_single_dc": "safety-stock days",
    "residual_share_target": "rest-of-state demand share",
    "cycle_stock_days": "cycle-stock days",
    "storage_density_t_per_sqft": "storage density",
    "handling_inr_per_tonne": "handling rate",
    "opex_inr_per_sqft_month": "warehouse opex",
    "metro_uplift": "metro demand uplift",
    "elasticity": "demand elasticity",
    "diesel_share_of_freight_cost": "diesel share of freight cost",
}
DIESEL_MECHANISM = "dearer diesel raises the rate per tonne-km on the same lanes"
GENERIC_LIMITS = (
    "Hypothetical client; Census-based demand, straight-line distance x circuity, some analyst "
    "rents."
)  # static texts carry no digits: every number in an answer must come from a tool result
MAX_LISTED_CHANGES = 3  # a comparison row lists site ids only when few sites change
TOP_DESTINATIONS = 3  # destination DCs named for re-assigned zones
TOP_ZONES = 4  # zone names quoted for lost next-day service


def cr(x_cr: float) -> str:
    return f"INR {abs(x_cr):.1f} Cr"


def pct(frac: float) -> str:
    return f"{100 * frac:.1f}%"


def short_name(name: str) -> str:
    """'Bengaluru - Hosur (Attibele-Bommasandra)' -> 'Bengaluru - Hosur'."""
    return name.split(" (")[0]


def site_list(sites: list[dict]) -> str:
    return ", ".join(f"{short_name(s['name'])} ({s['dc_id']})" for s in sites)


def result_ids(result: dict) -> list[str]:
    """Scenario ids a tool result reports, in first-seen order."""
    ids = [result[k] for k in ("scenario_id", "source_id") if k in result]
    ids += [row["scenario_id"] for row in result.get("scenarios", [])]
    return list(dict.fromkeys(ids))


def answer(parts: tuple[str, str, str, str, str], result: dict) -> str:
    """The six labelled parts as Markdown; the source is the result's scenario ids."""
    source = ", ".join(result_ids(result)) or "data/assumptions.yaml"
    return "\n\n".join(
        f"**{label}:** {text}" for label, text in zip(STRUCTURE, (*parts, source), strict=True)
    )


def service_clause(new_frac: float, recommended_frac: float) -> str:
    """'with next-day service at 85.1% against 80.1%', or 'unchanged at 80.1%' when equal."""
    if pct(new_frac) == pct(recommended_frac):
        return f"with next-day service unchanged at {pct(new_frac)}"
    return f"with next-day service at {pct(new_frac)} against {pct(recommended_frac)}"


SCENARIO_NAMES = {  # recorded scenarios as a reader would name them (no ids in headlines)
    "S0": "Today's network",
    "S1": "The cheapest possible network",
    "S4_uniform": "The network with uniform demand growth",
    "S4_regional_skew": "The network with faster growth in the East and Centre",
    "S7_rent_plus_20": "The network with higher rents everywhere",
    "S7_rent_minus_20": "The network with lower rents everywhere",
    "S8_no_puducherry": "The network without the Puducherry plant",
    "S8_add_east": "The network with an eastern plant",
}


def subject_name(row: dict, recommended_id: str) -> str:
    """A scenario as a reader would name it, so headlines never start with a scenario id."""
    sid = row["scenario_id"]
    name = SCENARIO_NAMES.get(sid, "This scenario's network")
    if sid == recommended_id:
        name = "The recommended network"
    elif sid.startswith("S2_k"):
        name = f"The best {row['n_dcs']}-warehouse network"
    elif sid.endswith("_staged"):
        name = "The staged network"
    elif sid.startswith("S3_") and "next_day_share_frac" in row:
        name = f"The network built for {pct(row['next_day_share_frac'])} next-day service"
    elif sid.startswith("COG_"):
        name = "The centre-of-gravity network"
    return name


def cost_versus(r: dict, subject: str) -> str:
    """Headline clause: cost and service against the recommended network."""
    vs = r["vs_recommended"]
    delta = vs["delta_total_cr"]
    return (
        f"{subject} costs {cr(delta)} a year {'more' if delta >= 0 else 'less'} than the "
        f"recommended network ({cr(r['cost_cr_per_yr']['total'])} against "
        f"{cr(vs['recommended_total_cr'])}), "
        f"{service_clause(r['next_day_share_frac'], vs['recommended_next_day_share_frac'])}."
    )


def parameter_name(key: str) -> str:
    leaf = key.split(".")[-1]
    return PARAMETER_NAMES.get(leaf, leaf.replace("_", " "))


def drivers_text(drivers: list[dict], freight_mechanism: str | None = None) -> str:
    """The cost components that move most, each with its mechanism. freight_mechanism replaces
    the distance-based reason for freight (a diesel shock changes the rate, not the lanes)."""
    if not drivers:
        return "No cost component moves against the recommended network."

    def move(d: dict) -> str:
        text = f"{COMPONENT_LABELS[d['component']]} {d['delta_cr']:+.1f} Cr"
        if freight_mechanism and d["component"] in ("primary", "secondary"):
            return text  # the shared reason is stated once, below
        return f"{text} ({MECHANISM[(d['component'], d['delta_cr'] > 0)]})"

    moves = [move(d) for d in drivers]
    if freight_mechanism:
        return f"The biggest cost moves, because {freight_mechanism}: " + "; ".join(moves) + "."
    return "The biggest cost moves: " + "; ".join(moves) + "."


def sites_text(vs: dict) -> str:
    changes = []
    if vs["added_sites"]:
        changes.append(f"opens {site_list(vs['added_sites'])}")
    if vs["dropped_sites"]:
        changes.append(f"closes {site_list(vs['dropped_sites'])}")
    return ("It " + " and ".join(changes) + ".") if changes else "It keeps the recommended sites."


def zones_text(zones: dict | None) -> str:
    if zones is None:
        return "It uses a different set of sites, so zones are not compared one by one."
    if not zones["moved_count"]:
        return "No zone changes DC."
    top = sorted(zones["moved_to"].items(), key=lambda kv: -kv[1])[:TOP_DESTINATIONS]
    text = (
        f"{zones['moved_count']} zones ({pct(zones['moved_demand_frac'])} of demand) change DC, "
        f"mostly to {', '.join(f'{j} ({n})' for j, n in top)}."
    )
    if zones["losing_next_day_count"]:
        text += (
            f" {zones['losing_next_day_count']} zones "
            f"({pct(zones['losing_next_day_demand_frac'])} of demand) lose next-day service."
        )
    if zones["gaining_next_day_count"]:
        text += (
            f" {zones['gaining_next_day_count']} zones "
            f"({pct(zones['gaining_next_day_demand_frac'])} of demand) gain it."
        )
    return text


def describe_network(
    r: dict, meaning: str | None = None, limits: str | None = None, subject: str | None = None
) -> str:
    """A re-optimised network (run_scenario) against the recommended one."""
    if "cost_cr_per_yr" not in r:
        return answer(
            (
                f"No feasible network meets these inputs ({r['status']}).",
                "Nothing changes: the model found no network that meets the service target.",
                "The service constraint cannot be met with the candidate sites.",
                meaning or "Relax the service target or widen the candidate list.",
                limits or GENERIC_LIMITS,
            ),
            r,
        )
    vs = r["vs_recommended"]
    overrides = ", ".join(f"{k} = {v:g}" for k, v in r.get("overrides", {}).items())
    shock = r.get("overrides", {}).get("diesel_shock_frac")
    if subject is None and shock:
        subject = f"With diesel prices up {pct(shock)}, the network"
    elif subject is None:
        subject = f"With {overrides}, the network" if overrides else "This scenario's network"
    why = drivers_text(vs["cost_drivers"])
    if "diesel" in r:
        d = r["diesel"]
        why = (
            f"Diesel is {pct(d['diesel_share_of_freight_cost_frac'])} of freight cost, so both "
            f"freight rates rise by a factor of {d['freight_multiplier']:.2f}. "
            + drivers_text(vs["cost_drivers"], DIESEL_MECHANISM)
        )
    changed = bool(vs["added"] or vs["dropped"])
    default_meaning = (
        "The network holds: this is a budget risk to manage through contracts, such as "
        "diesel-linked freight rates, not a reason to move sites."
        if not changed
        else "The core network holds, but the swing site changes: confirm the swing location "
        "before committing to it."
    )
    return answer(
        (
            cost_versus(r, subject),
            f"{sites_text(vs)} {zones_text(vs['zones'])}",
            why,
            meaning or default_meaning,
            limits
            or "Re-optimised at the recommended service target with only these inputs "
            "changed; everything else as in data/assumptions.yaml.",
        ),
        r,
    )


def describe_disruption(r: dict, meaning: str | None = None, limits: str | None = None) -> str:
    site = r["closed_site"]
    named = f"{short_name(site['name'])} ({site['dc_id']})"
    if r["mode"] == "strategic":
        return describe_network(
            r,
            meaning
            or "A permanent loss is manageable because a credible substitute exists; secure "
            "lease continuity (break clauses, a landlord with alternative stock) more than a "
            "lower rent.",
            limits
            or "Re-optimised without the site at the same next-day target. " + GENERIC_LIMITS,
            subject=f"Without {named}, the re-optimised network",
        )
    o = r["outage"]
    deltas = r["vs_recommended"]["delta_by_component_cr"]
    moved = ", ".join(f"{j} ({n})" for j, n in o["reassigned_zones_by_site"].items())
    lost = o["zones_losing_next_day"][:TOP_ZONES]
    return answer(
        (
            f"Shutting {named} for {o['months']:g} {'month' if o['months'] == 1 else 'months'} "
            "costs about "
            f"{cr(o['outage_cost_cr'])} in extra freight, and next-day coverage falls from "
            f"{pct(o['next_day_share_before_frac'])} to {pct(o['next_day_share_during_frac'])} "
            "while it is shut.",
            f"The other {r['n_dcs']} sites stay open and absorb its zones: {moved}. "
            f"{o['zones_losing_next_day_count']} zones ({pct(o['demand_losing_next_day_frac'])} "
            f"of demand) lose next-day delivery, including {', '.join(lost)}.",
            f"Freight runs {cr(o['freight_change_cr_per_yr'])} a year higher while it is shut: "
            f"{COMPONENT_LABELS['secondary']} {deltas['secondary']:+.1f} Cr "
            f"({MECHANISM[('secondary', deltas['secondary'] > 0)]}) and "
            f"{COMPONENT_LABELS['primary']} {deltas['primary']:+.1f} Cr. Rent, fixed cost and "
            "stock at the closed site keep running, so only the freight is charged.",
            meaning
            or "This is a service risk more than a cost risk: it argues for a documented "
            "contingency, such as a cross-dock or third-party overflow deal near the site, rather "
            "than a spare DC.",
            limits
            or f"The outage counts extra freight only; {o['not_costed']} are not costed, so the "
            "cost is a floor.",
        ),
        r,
    )


def describe_explain(r: dict, meaning: str | None = None, limits: str | None = None) -> str:
    if "cost_cr_per_yr" not in r:
        return describe_network(r, meaning, limits)
    c, share = r["cost_cr_per_yr"], r["cost_share_frac"]
    vs = r["vs_recommended"]
    busiest = sorted(r["sites"], key=lambda s: -s["throughput_t_yr"])[:2]
    is_rec = r["scenario_id"] == vs["recommended_id"]
    headline = (
        f"{'The recommended network' if is_rec else 'This network'} runs {r['n_dcs']} DCs at "
        f"{cr(c['total'])} a year "
        f"({pct(r['share_of_revenue_frac'])} of revenue) and reaches "
        f"{pct(r['next_day_share_frac'])} of demand next-day."
    )
    if not is_rec:
        headline += " " + cost_versus(r, "It")
    return answer(
        (
            headline,
            f"Sites: {site_list(r['sites'])}. The busiest are "
            + "; ".join(
                f"{short_name(s['name'])} ({pct(s['share_of_volume_frac'])} of volume)"
                for s in busiest
            )
            + ".",
            f"Freight is most of the cost: primary {c['primary']:.1f} Cr "
            f"({pct(share['primary'])}) and secondary {c['secondary']:.1f} Cr "
            f"({pct(share['secondary'])}), set by how far DCs sit from plants and from demand. "
            f"Inventory ({c['inventory']:.1f} Cr) and fixed site cost ({c['fixed']:.1f} Cr) "
            "grow with every extra site.",
            meaning
            or "Commit first to the sites that stay open in every stress test, and confirm the "
            "swing site with real-estate diligence.",
            limits or GENERIC_LIMITS,
        ),
        r,
    )


def row_line(s: dict, recommended_id: str) -> str:
    if "cost_cr_per_yr" not in s:
        return f"- {s['scenario_id']}: {s['status']}."
    line = (
        f"- {s['scenario_id']}: {s['n_dcs']} DCs, {s['cost_cr_per_yr']['total']:.1f} Cr, "
        f"{pct(s['next_day_share_frac'])} next-day"
    )
    if s["scenario_id"] == recommended_id:
        return line + " (recommended)."
    changes = []
    if len(s["added_sites"]) + len(s["dropped_sites"]) > MAX_LISTED_CHANGES:
        changes.append("other sites")
    else:
        if s["added_sites"]:
            changes.append("opens " + ", ".join(x["dc_id"] for x in s["added_sites"]))
        if s["dropped_sites"]:
            changes.append("closes " + ", ".join(x["dc_id"] for x in s["dropped_sites"]))
    zones = s["zones"]
    if zones and zones["losing_next_day_count"]:
        changes.append(f"{zones['losing_next_day_count']} zones lose next-day")
    if zones and zones["gaining_next_day_count"]:
        changes.append(f"{zones['gaining_next_day_count']} gain it")
    return line + (f"; {'; '.join(changes)}." if changes else "; same sites.")


def describe_compare(r: dict, meaning: str | None = None, limits: str | None = None) -> str:
    rec_id = r["recommended_id"]
    rows = r["scenarios"]
    subject = next((s for s in rows if s["scenario_id"] != rec_id and "cost_cr_per_yr" in s), None)
    if subject is None:
        subject = rows[0]
    name = subject_name(subject, rec_id)
    if "cost_cr_per_yr" in subject:
        delta = subject["delta_total_vs_recommended_cr"]
        service = service_clause(
            subject["next_day_share_frac"], subject["recommended_next_day_share_frac"]
        )
        headline = (
            f"{name} costs INR {subject['cost_cr_per_yr']['total']:.1f} Cr a year, {cr(delta)} "
            f"{'more' if delta >= 0 else 'less'} than the recommended network, {service}."
        )
        why = f"For {name[0].lower()}{name[1:]}: " + drivers_text(subject["cost_drivers"])
    else:
        headline = f"{name}: {subject['status']}."
        why = "No feasible network to compare."
    return answer(
        (
            headline,
            "\n" + "\n".join(row_line(s, rec_id) for s in rows),
            why,
            meaning
            or "Use the comparison to price the trade-off between cost and service before "
            "choosing.",
            limits or GENERIC_LIMITS,
        ),
        r,
    )


def describe_ranking(r: dict, meaning: str | None = None, limits: str | None = None) -> str:
    rows = r["rows"]
    top = rows[0]
    reshaping = [row for row in rows if row["low_n_dcs"] != row["high_n_dcs"]]
    saving = max(
        rows, key=lambda row: abs(row["high_saving_vs_as_is_cr"] - row["low_saving_vs_as_is_cr"])
    )
    swings = "; ".join(
        f"{parameter_name(row['parameter'])} {row['low_total_cr']:.1f} to "
        f"{row['high_total_cr']:.1f} Cr"
        for row in rows[:TOP_DESTINATIONS]
    )
    network = (
        "Only "
        + " and ".join(
            f"{parameter_name(row['parameter'])} ({row['low_n_dcs']} to {row['high_n_dcs']} DCs)"
            for row in reshaping
        )
        + f" {'changes' if len(reshaping) == 1 else 'change'} the DC count; every other "
        f"assumption keeps the {r['base_n_dcs']} DCs."
        if reshaping
        else f"No assumption changes the DC count from {r['base_n_dcs']}."
    )
    return answer(
        (
            f"{parameter_name(top['parameter']).capitalize()} moves total cost most "
            f"({top['low_total_cr']:.1f} to {top['high_total_cr']:.1f} Cr), but "
            f"{parameter_name(saving['parameter'])} decides the business "
            f"case: the saving against today ranges from {saving['low_saving_vs_as_is_cr']:.1f} "
            f"to {saving['high_saving_vs_as_is_cr']:.1f} Cr.",
            network,
            f"Widest cost swings, each re-optimised at both ends of its range: {swings}. "
            f"Base: {r['base_total_cr']:.1f} Cr, saving {r['base_saving_vs_as_is_cr']:.1f} Cr "
            "against today.",
            meaning
            or "Firm up the assumptions that change the network or the saving first, with "
            "client data.",
            limits
            or "One low- or medium-confidence assumption at a time across its range; rents are "
            "tested separately.",
        ),
        r,
    )


def describe_source(r: dict, meaning: str | None = None, limits: str | None = None) -> str:
    return answer(
        (
            f"{r['key']} is {r.get('value')} {r.get('unit', '')}".rstrip() + ".",
            "No network change: this is a model input.",
            f"Source: {r.get('source', 'not recorded')}".strip(),
            meaning or f"Confidence: {r.get('confidence', 'not rated')}.",
            limits or f"Range tested: {r.get('range')}.",
        ),
        r,
    )


def describe_parameters(r: dict, meaning: str | None = None, limits: str | None = None) -> str:
    keys = ", ".join(p["key"] for p in r["parameters"])
    return answer(
        (
            "These are the inputs a what-if run may change.",
            "No network change: this lists inputs only.",
            f"Editable inputs: {keys}.",
            meaning or "Ask for a run with any of them, e.g. a diesel shock or a service target.",
            limits or "An override may go at most twice the range width beyond its range.",
        ),
        r,
    )


def describe_refusal(r: dict) -> str:
    return answer(
        (
            "That input is refused, so no model run was made.",
            "Nothing changes in the network.",
            r["error"],
            "Choose a value inside the accepted range and ask again.",
            "Accepted ranges come from data/assumptions.yaml.",
        ),
        r,
    )


DESCRIBERS = {
    "simulate_disruption": describe_disruption,
    "explain_network": describe_explain,
    "compare_scenarios": describe_compare,
    "rank_assumptions": describe_ranking,
    "get_assumption_source": describe_source,
    "list_parameters": describe_parameters,
    "run_scenario": describe_network,
}


def describe(tool: str, result: dict, meaning: str | None = None, limits: str | None = None) -> str:
    """A six-part answer from one tool result; every number is formatted from the result.

    meaning and limits replace the tool's generic client implication and limits line (the
    offline library passes the ones written for each question).
    """
    if "error" in result:
        return describe_refusal(result)
    return DESCRIBERS[tool](result, meaning, limits)


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
    meaning: str | None = None  # the client implication, from docs/scenario_insights.md
    limits: str | None = None  # None: the tool's generic limits line
    action: str | None = None  # plain answer: the one recommendation (D-053)
    caveat: str | None = None  # plain answer: the main limitation, in plain words


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
            ((compare, {"ids": [rec, "S3_400km_90", "S3_400km_95", "S3_400km_85"]}),),
            meaning="Each step costs more than the last, and above the first upgrade the network "
            "re-shapes rather than grows (NCR gives way to Jaipur and Rajpura), so treat the "
            "highest targets as a separate network decision, not a further stage.",
            action="Treat the highest next-day targets as a separate decision: the network would "
            "have to be redrawn, not just extended.",
            caveat="Costs are modelled; the next-day reach uses estimated road distances.",
        ),
        Intent(
            "service_85",
            "What would it cost to reach 85% next-day?",
            (r"upgrade|\b85\b|faster|better service|higher service|more next.?day",),
            ((compare, {"ids": [rec, "S3_400km_85", f"{rec}_staged"]}),),
            meaning="This is the first upgrade to offer. Building Nagpur instead of Indore now "
            "(the staged run) costs a little more today but makes the upgrade purely additive.",
            action="Offer this as the first service upgrade, and build Nagpur instead of Indore "
            "now so the upgrade only adds warehouses later.",
            caveat="Costs are modelled; the next-day reach uses estimated road distances.",
        ),
        Intent(
            "growth",
            "What if demand grows 30%?",
            (r"grow|growth|expan|more demand|volume",),
            ((compare, {"ids": [rec, "S4_uniform", "S4_regional_skew"]}),),
            meaning="Growth needs no extra site: cost per tonne falls with scale, and only the "
            "central site swings from Indore to Nagpur, because more volume makes freight weigh "
            "more than rent.",
            limits="The skewed run grows the East and Centre faster; zone shares use base demand.",
            action="No extra warehouse is needed for this growth; watch the central-India "
            "location, which shifts from Indore to Nagpur.",
            caveat="Growth is spread by state; customer shares use today's demand.",
        ),
        Intent(
            "rent",
            "What if rents rise 20%?",
            (r"rent|real estate|lease|warehouse cost",),
            ((compare, {"ids": [rec, "S7_rent_plus_20", "S7_rent_minus_20"]}),),
            meaning="Rent is a small share of cost and no site changes, so location drives the "
            "choice; a rent survey matters only for the central-India swing site.",
            limits="Every candidate rent moves together; one site at a time is the S7 "
            "switching-rent analysis.",
            action="Location matters more than rent: survey rents only for the central-India "
            "warehouse.",
            caveat="All rents move together; one warehouse at a time is tested separately.",
        ),
        Intent(
            "no_puducherry",
            "What if we close the Puducherry plant?",
            (r"puducherry|pondicherry",),
            ((compare, {"ids": [rec, "S8_no_puducherry"]}),),
            meaning="Sourcing drives cost far more than site choice: the core DCs survive, but "
            "the plant footprint is worth modelling jointly with the network.",
            limits="Plant shares are renormalised analyst assumptions (docs/DECISIONS.md).",
            action="Plan factory and warehouse decisions together: where goods are made changes "
            "cost more than where they are stored.",
            caveat="The factory volumes are assumptions.",
        ),
        Intent(
            "east_plant",
            "What if we add a plant in the East?",
            (r"plant|factory", r"east|kolkata|howrah|new|add|another"),
            ((compare, {"ids": [rec, "S8_add_east"]}),),
            meaning="An eastern plant cuts inbound freight sharply and moves the swing sites; "
            "plant allocation should be decided jointly with the network.",
            limits="The plant location and share are analyst assumptions (docs/DECISIONS.md).",
            action="Plan factory and warehouse decisions together: an eastern factory cuts "
            "trucking from the factories sharply.",
            caveat="The factory location and volume are assumptions.",
        ),
        Intent(
            "assumptions",
            "Which of our assumptions should I worry about most?",
            (r"assumption|sensitiv|uncertain|tornado|worry|risk",),
            (("rank_assumptions", {}),),
            meaning="Calibrate circuity with real road distances first, and replace fixed cost "
            "per DC with the client's own overhead data: they decide the DC count and the size "
            "of the business case.",
            action="Check distances on real road routes first, and replace the assumed running "
            "cost per warehouse with your own figures.",
            caveat="One estimate changed at a time; rents are tested separately.",
        ),
        Intent(
            "cog",
            "Why not just use centre of gravity?",
            (r"cent(re|er) of gravity|\bcog\b",),
            ((compare, {"ids": ["S2_k09", "COG_k09"]}),),
            meaning="Centre of gravity is a useful first sketch, but it ignores plant "
            "locations, rents and inventory pooling, so the optimised network earns its cost.",
            action="Use the optimised network: the simple centre-of-gravity layout ignores "
            "factories, rents and stock.",
            caveat="Both networks are costed the same way.",
        ),
        Intent(
            "dc_count",
            "How many DCs should we run?",
            (r"how many|number of (dc|site|warehouse)",),
            ((compare, {"ids": ["S2_k04", "S2_k06", "S2_k08", "S2_k09", "S2_k10", "S2_k12"]}),),
            meaning="Cost alone cannot pick the DC count because the curve is flat across the "
            "middle range; the next-day promise picks it.",
            limits="These runs have no service target.",
            action="Choose the number of warehouses by the next-day promise, not by cost alone: "
            "cost barely moves across the middle range.",
            caveat="These runs have no next-day target.",
        ),
        Intent(
            "cheapest",
            "What is the cheapest possible network?",
            (r"cheapest|lowest cost|minimum cost|cost only",),
            ((compare, {"ids": ["S1", rec]}),),
            meaning="The cheapest network saves cost by giving up next-day service for much of "
            "the market; the recommendation pays a small premium for it.",
            action="Pay the small premium for next-day delivery: the cheapest network leaves much "
            "of the market on slower delivery.",
            caveat="Costs are modelled for a hypothetical client.",
        ),
        Intent(
            "as_is",
            "What does today's network cost, and what do we save?",
            (r"today|current|as.?is|existing|saving|save",),
            ((compare, {"ids": ["S0", rec]}),),
            meaning="Consolidation is a like-for-like saving at today's service level: fewer, "
            "larger DCs save fixed cost, inbound freight and inventory, and give up some "
            "last-mile freight.",
            limits="Today's network is illustrative (pre-GST state depots, Grade B rents), not "
            "client data.",
            action="Move to the recommended network: it saves money at about today's service "
            "level.",
            caveat="Today's network is illustrative, not real client data.",
        ),
        Intent(
            "recommended",
            "What's our recommended network and what does it cost?",
            (r"recommend|proposed|our network|which sites|where",),
            (("explain_network", {"scenario_id": rec}),),
            meaning="Commit first to the sites that stay open in every stress test; confirm the "
            "central-India site (Indore or Nagpur) with real-estate diligence.",
            action="Commit first to the warehouses that stay open in every test, and confirm the "
            "central-India location (Indore or Nagpur) with a property search.",
            caveat="Hypothetical client; road distances and some rents are estimates.",
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


WORKED_EXAMPLE_INTENTS = ("outage_BLR_HSR", "diesel_20")  # one outage, one diesel shock


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
        # agent-made networks, so offline answers can be mapped; sorted and without solver
        # wall-clock times, so a rebuild is byte-identical with or without the result cache
        "records": {
            sid: without_solve_times(toolbox.records[sid]) for sid in sorted(toolbox.records)
        },
    }


def without_solve_times(record: dict) -> dict:
    solve = record["solve"] | {"solve_time_s": None}
    solve["passes"] = [p | {"solve_time_s": None} for p in solve.get("passes", [])]
    return record | {"solve": solve}


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
