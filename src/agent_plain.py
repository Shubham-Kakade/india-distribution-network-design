"""Plain-English answers for a business manager: the default answer in the app (D-053).

Four short parts, in this order, then one small italic line:
- In short: the answer and its one or two key numbers;
- What changes: what happens to warehouses and customers;
- Why it costs more (or less): the main reason, in one or two plain sentences;
- What to do: one clear recommendation;
- *Limits: the main limitation. Source: the scenario ids.*

At most about 120 words and five numbers, rounded for reading (80.1% -> about 80%). Plain words
only: warehouse, market area, trucking from factories to warehouses, delivery trucking, share of
customers who get next-day delivery, cost of holding stock, running cost per warehouse; places
are named by city. Every number is formatted from the tool result, so the answer passes the
grounding check (rounding is allowed). The detailed six-part answer stays in agent_offline.py.
"""

from src.agent_offline import result_ids, subject_name
from src.agent_tools import cost_drivers

PLAIN_STRUCTURE = ("In short", "What changes", "Why it costs", "What to do")
MAX_LISTED_WAREHOUSES = 3  # name the warehouses that open or close only when few change
MARKET_NAMES = 3  # market areas named in an outage answer
HALF_PERCENT_FRAC = 0.005  # below this a share would read "about 0%"

PLAIN_REASON = {  # (cost component, rises) -> the reason in plain words
    ("primary", True): "trucking from the factories to the warehouses costs more",
    ("primary", False): "trucking from the factories to the warehouses costs less",
    ("secondary", True): "delivery trucks drive further to reach customers",
    ("secondary", False): "delivery trucks drive shorter distances to customers",
    ("space", True): "warehouse space costs more",
    ("space", False): "warehouse space costs less",
    ("handling", True): "more goods are handled",
    ("handling", False): "fewer goods are handled",
    ("inventory", True): "more stock has to be held",
    ("inventory", False): "less stock has to be held",
    ("fixed", True): "there are more warehouses to run",
    ("fixed", False): "there are fewer warehouses to run",
}
PLAIN_PARAMETER_NAMES = {  # S9 tornado inputs in plain words (last part of the YAML key)
    "annual_volume_tonnes": "sales volume",
    "circuity_factor": "road distances",
    "primary_ftl_inr_per_tkm": "the factory-to-warehouse trucking rate",
    "secondary_inr_per_tkm": "the delivery trucking rate",
    "fixed_cost_per_dc_cr_per_yr": "the running cost per warehouse",
    "safety_stock_days_single_dc": "safety stock",
    "residual_share_target": "demand outside the big cities",
    "cycle_stock_days": "regular stock",
    "storage_density_t_per_sqft": "how densely goods are stored",
    "handling_inr_per_tonne": "handling cost",
    "opex_inr_per_sqft_month": "warehouse running costs",
    "metro_uplift": "big-city demand",
    "elasticity": "demand by state",
    "diesel_share_of_freight_cost": "the diesel share of trucking cost",
}


def money(x_cr: float) -> str:
    """'about INR 244 Cr' above 100 Cr, else one decimal: 'about INR 2.9 Cr'."""
    x = abs(x_cr)
    return f"about INR {x:.0f} Cr" if x >= 100 else f"about INR {x:.1f} Cr"


def share(frac: float) -> str:
    return f"about {100 * frac:.0f}%"


def city(site_name: str) -> str:
    """'Bengaluru - Hosur (Attibele-Bommasandra)' -> 'Bengaluru'."""
    return site_name.split(" - ")[0]


def warehouse(site_name: str) -> str:
    """'Bengaluru - Hosur (Attibele-Bommasandra)' -> 'the Bengaluru warehouse (Hosur)'."""
    town, _, locality = site_name.partition(" - ")
    locality = locality.split(" (")[0].split(" / ")[0]
    return f"the {town} warehouse ({locality})" if locality else f"the {town} warehouse"


def customers(frac: float) -> str:
    """'About 17% of customers', or 'Almost no customers' when the share rounds to 0%."""
    return (
        f"{share(frac).capitalize()} of customers"
        if frac >= HALF_PERCENT_FRAC
        else "Almost no customers"
    )


def listing(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def delivery(new_frac: float, recommended_frac: float) -> str:
    if share(new_frac) == share(recommended_frac):
        return f"next-day delivery still reaches {share(new_frac)} of customers"
    return (
        f"next-day delivery reaches {share(new_frac)} of customers instead of "
        f"{share(recommended_frac)}"
    )


def reasons(drivers: list[dict], delta_cr: float) -> str:
    """The main reasons, the ones pushing cost the same way as the total first."""
    main = [d for d in drivers if (d["delta_cr"] >= 0) == (delta_cr >= 0)][:2]
    offset = [d for d in drivers if (d["delta_cr"] >= 0) != (delta_cr >= 0)][:1]
    if not main:
        return "The cost hardly moves."
    text = "Mainly because " + " and ".join(
        PLAIN_REASON[(d["component"], d["delta_cr"] > 0)] for d in main
    )
    if offset:
        d = offset[0]
        text += (
            f"; this is partly offset because {PLAIN_REASON[(d['component'], d['delta_cr'] > 0)]}"
        )
    return text + "."


def changes(added: list[dict], dropped: list[dict], zones: dict | None) -> str:
    """What happens to warehouses and customers."""
    if len(added) + len(dropped) > MAX_LISTED_WAREHOUSES:
        text = "The network uses a different set of warehouses."
    elif added or dropped:
        moves = []
        if added:
            moves.append("opens " + listing([warehouse(s["name"]) for s in added]))
        if dropped:
            moves.append("closes " + listing([warehouse(s["name"]) for s in dropped]))
        text = "It " + " and ".join(moves) + "."
    else:
        text = "No warehouse opens or closes."
    if zones is None:
        return text
    if zones["losing_next_day_count"]:
        return f"{text} {customers(zones['losing_next_day_demand_frac'])} lose next-day delivery."
    if zones["moved_count"]:
        return f"{text} {customers(zones['moved_demand_frac'])} switch to a different warehouse."
    return text + " No customer changes warehouse."


def plain_answer(parts: tuple[str, str, str, str], why_label: str, caveat: str, r: dict) -> str:
    source = ", ".join(result_ids(r)) or "data/assumptions.yaml"
    in_short, what_changes, why, what_to_do = parts
    return "\n\n".join(
        (
            f"**In short:** {in_short}",
            f"**What changes:** {what_changes}",
            f"**{why_label}:** {why}",
            f"**What to do:** {what_to_do}",
            f"*Limits: {caveat} Source: {source}*",
        )
    )


def why_label(delta_cr: float) -> str:
    return "Why it costs more" if delta_cr >= 0 else "Why it costs less"


def plain_network(
    r: dict, action: str | None, caveat: str | None, subject: str | None = None
) -> str:
    """A re-optimised network (run_scenario, or a site lost for good) in plain words."""
    if "cost_cr_per_yr" not in r:
        return plain_answer(
            (
                "No network can meet these settings.",
                "Nothing changes.",
                "The next-day target cannot be met with the available warehouse locations.",
                action or "Relax the next-day target or add warehouse locations.",
            ),
            "Why it costs more",
            caveat or "Hypothetical client.",
            r,
        )
    vs = r["vs_recommended"]
    delta = vs["delta_total_cr"]
    shock = r.get("overrides", {}).get("diesel_shock_frac")
    if subject is None:
        subject = f"A {100 * shock:.0f}% rise in diesel prices" if shock else "This change"
    why = reasons(vs["cost_drivers"], delta)
    if "diesel" in r:
        why = (
            f"Diesel is {share(r['diesel']['diesel_share_of_freight_cost_frac'])} of trucking "
            "cost, so every truck journey costs more on the same routes."
        )
    moved = bool(vs["added"] or vs["dropped"])
    default_action = (
        "Keep the network; protect the budget with fuel-linked trucking contracts."
        if shock and not moved
        else "Keep the core warehouses, and check the location that changes before committing."
        if moved
        else "Keep the network and keep an eye on this input."
    )
    return plain_answer(
        (
            f"{subject} {'adds' if delta >= 0 else 'saves'} {money(delta)} a year, and "
            f"{delivery(r['next_day_share_frac'], vs['recommended_next_day_share_frac'])}.",
            changes(vs["added_sites"], vs["dropped_sites"], vs["zones"]),
            why,
            action or default_action,
        ),
        why_label(delta),
        caveat or "Only this input changes; everything else is as assumed.",
        r,
    )


def plain_disruption(r: dict, action: str | None, caveat: str | None) -> str:
    closed = r["closed_site"]["name"]
    if r["mode"] == "strategic":
        return plain_network(
            r,
            action
            or "Agree strong lease terms (break clauses, a landlord with other buildings) "
            "rather than chasing the lowest rent.",
            caveat or "Assumes the network is redesigned to keep the same next-day target.",
            subject=f"Losing {warehouse(closed)} for good",
        )
    o = r["outage"]
    names = {s["dc_id"]: s["name"] for s in r["sites"]}
    receivers = sorted(o["reassigned_zones_by_site"].items(), key=lambda kv: -kv[1])[:2]
    months = o["months"]
    period = "a month" if months == 1 else f"{months:g} months"
    return plain_answer(
        (
            f"If {warehouse(closed)} shuts for {period}, extra trucking costs "
            f"{money(o['outage_cost_cr'])} and next-day delivery falls from "
            f"{share(o['next_day_share_before_frac'])} to "
            f"{share(o['next_day_share_during_frac'])} of customers.",
            "Other warehouses take over its market areas, mainly "
            + listing([warehouse(names[j]) for j, _ in receivers])
            + f". {customers(o['demand_losing_next_day_frac'])} lose "
            f"next-day delivery, in places such as "
            f"{listing(o['zones_losing_next_day'][:MARKET_NAMES])}.",
            "These customers are now served from warehouses further away, so delivery trucks "
            "drive longer distances.",
            action
            or f"Plan a back-up near {city(closed)}, such as a temporary cross-dock or "
            "overflow space, rather than building a spare warehouse.",
        ),
        "Why it costs more",
        caveat or "Counts extra trucking only, not lost sales.",
        r,
    )


def plain_explain(r: dict, action: str | None, caveat: str | None) -> str:
    if "cost_cr_per_yr" not in r:
        return plain_network(r, action, caveat)
    is_rec = r["scenario_id"] == r["vs_recommended"]["recommended_id"]
    busiest = sorted(r["sites"], key=lambda s: -s["throughput_t_yr"])[:2]
    return plain_answer(
        (
            f"{'The recommended network' if is_rec else 'This network'} uses {r['n_dcs']} "
            f"warehouses, costs {money(r['cost_cr_per_yr']['total'])} a year "
            f"({share(r['share_of_revenue_frac'])} of revenue) and gives "
            f"{share(r['next_day_share_frac'])} of customers next-day delivery.",
            "Warehouses in " + listing([city(s["name"]) for s in r["sites"]]) + ". The busiest "
            f"serve {listing([city(s['name']) for s in busiest])}.",
            "Trucking is the biggest cost. More warehouses shorten delivery trips but add "
            "running and stock-holding cost; this set balances the two and meets the next-day "
            "target.",
            action
            or "Commit first to the warehouses that stay open in every test, and confirm the "
            "location that varies with a property search.",
        ),
        "Why it costs this much",
        caveat or "Hypothetical client; road distances and some rents are estimates.",
        r,
    )


def is_target_network(row: dict) -> bool:
    """A network re-optimised for a higher next-day target (S3), not the staged variant."""
    return row["scenario_id"].startswith("S3_") and not row["scenario_id"].endswith("_staged")


def plain_sweep(r: dict, action: str | None, caveat: str | None) -> str:
    """Several warehouse counts side by side (S2): the cost and delivery ranges."""
    rows = sorted(r["scenarios"], key=lambda s: s["n_dcs"])
    low, high = rows[0], rows[-1]
    return plain_answer(
        (
            f"Between {low['n_dcs']} and {high['n_dcs']} warehouses, total cost runs from "
            f"{money(low['cost_cr_per_yr']['total'])} to "
            f"{money(high['cost_cr_per_yr']['total'])} a year, while "
            f"next-day delivery rises from {share(low['next_day_share_frac'])} to "
            f"{share(high['next_day_share_frac'])} of customers.",
            "Each extra warehouse puts stock closer to more customers, so more of them get "
            "next-day delivery.",
            "Fewer warehouses save running and stock-holding cost; more warehouses shorten "
            "delivery trips. The two nearly balance, so the total moves little.",
            action or "Choose the number of warehouses by the delivery promise you want to make.",
        ),
        "Why it costs more or less",
        caveat or "Costs are modelled for a hypothetical client.",
        r,
    )


def plain_pair(base: dict, alt: dict, r: dict, action: str | None, caveat: str | None) -> str:
    """Two networks side by side, neither of them the recommended one (for example the
    centre-of-gravity layout against the optimised network with the same warehouse count)."""
    rec_id = r["recommended_id"]
    alt_cr, base_cr = alt["cost_cr_per_yr"], base["cost_cr_per_yr"]
    delta = alt_cr["total"] - base_cr["total"]
    same_sites = set(alt["open_dcs"]) == set(base["open_dcs"])
    return plain_answer(
        (
            f"{subject_name(alt, rec_id)} costs {money(alt_cr['total'])} a year, against "
            f"{money(base_cr['total'])} for {subject_name(base, rec_id).lower()}, and next-day "
            f"delivery reaches {share(alt['next_day_share_frac'])} of customers against "
            f"{share(base['next_day_share_frac'])}.",
            "Both use the same warehouse locations."
            if same_sites
            else "The two networks use different warehouse locations.",
            reasons(cost_drivers(alt_cr, base_cr), delta),
            action or "Weigh the cost difference against the delivery difference before choosing.",
        ),
        why_label(delta),
        caveat or "Costs are modelled for a hypothetical client.",
        r,
    )


def plain_compare(r: dict, action: str | None, caveat: str | None) -> str:
    rec_id = r["recommended_id"]
    rows = r["scenarios"]
    feasible = [s for s in rows if s["scenario_id"] != rec_id and "cost_cr_per_yr" in s]
    if not feasible:
        return plain_answer(
            (
                "None of these options gives a workable network.",
                "Nothing changes.",
                "The next-day target cannot be met.",
                action or "Relax the target or add warehouse locations.",
            ),
            "Why it costs more",
            caveat or "Hypothetical client.",
            r,
        )
    if len(rows) > MAX_LISTED_WAREHOUSES and all(s["scenario_id"].startswith("S2_k") for s in rows):
        return plain_sweep(r, action, caveat)
    if len(rows) == len(feasible) == 2:  # a pair without the recommended network
        return plain_pair(feasible[0], feasible[1], r, action, caveat)
    subject = feasible[0]
    delta = subject["delta_total_vs_recommended_cr"]
    more_less = "more" if delta >= 0 else "less"
    rec_row = next((s for s in rows if s["scenario_id"] == rec_id), None)
    count = (
        f"It runs {subject['n_dcs']} warehouses instead of {rec_row['n_dcs']}."
        if rec_row and rec_row["n_dcs"] != subject["n_dcs"]
        else ""
    )
    if is_target_network(subject):
        in_short = (
            f"Raising next-day delivery to {share(subject['next_day_share_frac'])} of customers "
            f"costs {money(delta)} a year {more_less} than the recommended network"
        )
        higher = next((s for s in feasible[1:] if is_target_network(s)), None)
        if higher:
            in_short += (
                f"; {share(higher['next_day_share_frac'])} costs "
                f"{money(higher['delta_total_vs_recommended_cr'])} more"
            )
        in_short += "."
        what_changes = count or "Customers are served from more, closer warehouses."
    else:
        service = delivery(
            subject["next_day_share_frac"], subject["recommended_next_day_share_frac"]
        )
        in_short = (
            f"{subject_name(subject, rec_id)} costs {money(delta)} a year {more_less} than the "
            f"recommended network, and {service}."
        )
        moves = changes(subject["added_sites"], subject["dropped_sites"], subject["zones"])
        if count:
            moves = moves.replace("The network uses a different set of warehouses.", count)
            moves = moves if count in moves else f"{count} {moves}"
        what_changes = moves
    return plain_answer(
        (
            in_short,
            what_changes,
            reasons(subject["cost_drivers"], delta),
            action or "Weigh the cost difference against the delivery difference before choosing.",
        ),
        why_label(delta),
        caveat or "Costs are modelled for a hypothetical client.",
        r,
    )


def plain_ranking(r: dict, action: str | None, caveat: str | None) -> str:
    rows = r["rows"]

    def name(row: dict) -> str:
        leaf = row["parameter"].split(".")[-1]
        return PLAIN_PARAMETER_NAMES.get(leaf, leaf.replace("_", " "))

    saving = max(
        rows, key=lambda row: abs(row["high_saving_vs_as_is_cr"] - row["low_saving_vs_as_is_cr"])
    )
    reshaping = [row for row in rows if row["low_n_dcs"] != row["high_n_dcs"]]
    lows = [min(row["low_n_dcs"], row["high_n_dcs"]) for row in reshaping]
    highs = [max(row["low_n_dcs"], row["high_n_dcs"]) for row in reshaping]
    low_s, high_s = sorted((saving["low_saving_vs_as_is_cr"], saving["high_saving_vs_as_is_cr"]))
    return plain_answer(
        (
            f"{name(rows[0]).capitalize()} moves total cost the most, but {name(saving)} decides "
            f"how big the saving is: from {money(low_s)} to {money(high_s)} a year.",
            (
                f"Only {listing([name(row) for row in reshaping])} change the best number of "
                f"warehouses: between {min(lows)} and {max(highs)}."
            )
            if reshaping
            else "No estimate changes how many warehouses are best.",
            "These inputs are estimates; the model was re-run at both ends of each range to see "
            "how much the answer moves.",
            action or "Replace the estimates that move the answer most with your own data first.",
        ),
        "Why it costs more or less",
        caveat or "One estimate changed at a time; rents are tested separately.",
        r,
    )


def plain_source(r: dict, action: str | None, caveat: str | None) -> str:
    return plain_answer(
        (
            f"This input is set at {r.get('value')} {r.get('unit', '')}".rstrip() + ".",
            "Nothing changes in the network: this is an input.",
            f"It comes from: {r.get('source', 'not recorded')}".strip(),
            action or "Replace it with your own figure if you have one.",
        ),
        "Why it costs this much",
        caveat or f"Confidence in this input: {r.get('confidence', 'not rated')}.",
        r,
    )


def plain_parameters(r: dict, action: str | None, caveat: str | None) -> str:
    return plain_answer(
        (
            "These are the inputs a what-if question can change.",
            "Nothing changes in the network: this is a list.",
            "Each input is an estimate with a tested range.",
            action or "Ask, for example, what a rise in diesel prices would do.",
        ),
        "Why it costs this much",
        caveat or "Changes far outside the tested ranges are refused.",
        r,
    )


def plain_refusal(r: dict) -> str:
    return plain_answer(
        (
            "That change is outside the range the model accepts, so it was not run.",
            "Nothing changes.",
            r["error"],
            "Ask again with a value inside the accepted range.",
        ),
        "Why it costs this much",
        "Accepted ranges come from the assumptions file.",
        r,
    )


PLAIN_WRITERS = {
    "simulate_disruption": plain_disruption,
    "explain_network": plain_explain,
    "compare_scenarios": plain_compare,
    "rank_assumptions": plain_ranking,
    "get_assumption_source": plain_source,
    "list_parameters": plain_parameters,
    "run_scenario": plain_network,
}


def plain(tool: str, result: dict, action: str | None = None, caveat: str | None = None) -> str:
    """The plain-English answer to one tool result (D-053); action and caveat replace the
    generic recommendation and limitation (the offline library passes its own)."""
    if "error" in result:
        return plain_refusal(result)
    return PLAIN_WRITERS[tool](result, action, caveat)
