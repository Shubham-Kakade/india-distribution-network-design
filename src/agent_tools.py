"""Agent tools (spec §10): the JSON schemas the LLM sees and the implementations behind them.

The tools compute no cost of their own. New networks come from model.build_and_solve (two-pass
free solves, D-034) and the S5 functions in scenarios.py; recorded scenarios are read from the
JSON records that reporting.run_record writes. Every tool returns plain JSON-ready dicts, and a
ValueError carries a message the agent can show the user (a bad argument is a refusal, not a
crash).
"""

import hashlib
import json
import logging
import re
from functools import cached_property

import pandas as pd

from src.baseline import as_is_network
from src.config import ASSUMPTIONS_PATH, entries_with_range, with_overrides
from src.data_prep import OUTPUTS_DIR, NetworkData, clean_raw
from src.model import COMPONENTS, build_and_solve
from src.reporting import SCENARIO_DIR, run_record
from src.scenarios import (
    Run,
    diesel_overrides,
    operational_outage,
    permanent_loss,
    rebuild_data,
)

logger = logging.getLogger(__name__)

CACHE_DIR = OUTPUTS_DIR / "scenario_cache"  # git-ignored (spec §11)
MAX_RANGE_WIDTHS = 2  # spec §10: refuse overrides more than 2x the range width outside the range
MAX_OUTAGE_MONTHS = 12  # an outage is charged months/12 of a year's extra freight (D-029)
DIESEL_KEY = "diesel_shock_frac"
REBUILD_PREFIXES = ("demand.", "company.annual_volume", "distance.")
TOP_COST_DRIVERS = 3  # cost components listed as "what moved" against the recommended network
MIN_DRIVER_CR = 0.05  # smaller moves show as 0.0 Cr, so they are not drivers
# Plain English for zone anchors that are municipal-body abbreviations or official compound
# names. The only place these names are mapped; zone_ids and the data keep the official names.
ZONE_DISPLAY_NAMES = {
    "BBMP": "Bengaluru",
    "DMC": "Delhi",
    "GHMC": "Hyderabad",
    "GVMC": "Visakhapatnam",
    "Greater Mumbai": "Mumbai",
    "Haora": "Howrah",
    "Ahmadabad": "Ahmedabad",
    "Nanded Waghala": "Nanded",
    "Sangli Miraj Kupwad": "Sangli",
    "Bhiwandi Nizampur": "Bhiwandi",
}


def rounded(value: object) -> object:
    """Round floats in a tool result to 4 dp: short for the LLM, and fine enough that a figure
    rounded again to 1 dp in a reply cannot drift (no double rounding)."""
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [rounded(v) for v in value]
    return value


def editable_parameters(params: dict) -> dict[str, dict]:
    """Every parameter the agent may override, keyed by dotted path without ".value".

    The ranged entries of assumptions.yaml, plus the service target (range = the radii and
    targets swept in S3) and the S6 diesel shock (range = the shocks in assumptions.yaml).
    """
    editable = {
        key: {
            "value": entry["value"],
            "range": list(entry["range"]),
            "unit": entry.get("unit", ""),
            "confidence": entry.get("confidence", ""),
        }
        for key, entry in entries_with_range(params)
    }
    service = params["service"]
    for key, sweep in (
        ("service.next_day_radius_km", service["next_day_radius_km"]["sensitivities"]),
        ("service.min_share_within_radius", params["scenarios"]["service_frontier_alphas"]),
    ):
        entry = service[key.split(".")[1]]
        editable[key] = {
            "value": entry["value"],
            "range": [min(sweep), max(sweep)],
            "unit": entry["unit"],
            "confidence": entry["confidence"],
        }
    shocks = params["scenarios"]["diesel_shock"]
    editable[DIESEL_KEY] = {
        "value": 0.0,
        "range": [min(shocks), max(shocks)],
        "unit": "fraction rise in the diesel price; both freight rates x (1 + diesel share x "
        "shock), as in S6",
        "confidence": "scenario input",
    }
    return editable


def accepted_bounds(entry: dict) -> tuple[float, float]:
    """Values an override may take: the range widened by 2x its width each side (spec §10).

    A non-negative range stays non-negative and a fraction stays at most 1.
    """
    low, high = entry["range"]
    width = high - low
    floor, ceiling = low - MAX_RANGE_WIDTHS * width, high + MAX_RANGE_WIDTHS * width
    if low >= 0:
        floor = max(floor, 0.0)
    if "fraction" in entry["unit"]:
        ceiling = min(ceiling, 1.0)
    return floor, ceiling


def overrides_from_items(items: list) -> dict:
    """The run_scenario tool argument, a list of {"key", "value"} items (D-055), as the
    {key: value} dict that validate_overrides checks."""
    if not isinstance(items, list) or not all(
        isinstance(i, dict) and set(i) == {"key", "value"} for i in items
    ):
        raise ValueError('overrides must be a list of {"key": parameter, "value": number}')
    overrides = {str(i["key"]): i["value"] for i in items}
    if len(overrides) < len(items):
        raise ValueError("overrides name the same parameter twice")
    return overrides


def validate_overrides(params: dict, overrides: dict) -> dict[str, float]:
    """Check overrides against assumptions.yaml before any solve (spec §10 guardrail).

    Returns {dotted key: float}; raises ValueError naming the key and the accepted range.
    """
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be an object of {parameter: number}")
    editable = editable_parameters(params)
    clean = {}
    for raw_key, value in overrides.items():
        key = str(raw_key).removesuffix(".value")
        if key not in editable:
            raise ValueError(f"'{key}' is not an editable parameter; call list_parameters")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{key}: {value!r} is not a number")
        floor, ceiling = accepted_bounds(editable[key])
        if not floor <= value <= ceiling:
            low, high = editable[key]["range"]
            raise ValueError(
                f"{key} = {value:g} is refused: the assumptions range is [{low:g}, {high:g}] and "
                f"an override may go at most {MAX_RANGE_WIDTHS}x the range width beyond it, "
                f"so the accepted values are [{floor:g}, {ceiling:g}]"
            )
        clean[key] = float(value)
    return clean


def apply_overrides(params: dict, overrides: dict[str, float]) -> dict:
    """Params with validated overrides applied; a diesel shock scales both freight rates (S6)."""
    plain = {f"{k}.value": v for k, v in overrides.items() if k != DIESEL_KEY}
    out = with_overrides(params, plain)
    if overrides.get(DIESEL_KEY):
        out = with_overrides(out, diesel_overrides(out, overrides[DIESEL_KEY])[1])
    return out


def cache_key(tool: str, arguments: dict, assumptions_sha256: str) -> str:
    """sha256 of the tool name, its validated arguments and the assumptions file (spec §10)."""
    payload = json.dumps(
        {"tool": tool, "args": arguments, "yaml": assumptions_sha256}, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def display_name(anchor_name: str) -> str:
    """A zone's name as a reader knows it: 'BBMP' -> 'Bengaluru'."""
    return ZONE_DISPLAY_NAMES.get(anchor_name, anchor_name)


def cost_drivers(cost_cr: dict, recommended_cr: dict) -> list[dict]:
    """The cost components that move most against the recommended network, largest first."""
    deltas = [{"component": c, "delta_cr": cost_cr[c] - recommended_cr[c]} for c in COMPONENTS]
    deltas = [d for d in deltas if abs(d["delta_cr"]) >= MIN_DRIVER_CR]
    deltas.sort(key=lambda d: -abs(d["delta_cr"]))
    return deltas[:TOP_COST_DRIVERS]


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_parameters",
            "description": "List the parameters that run_scenario can override, with current "
            "value, assumptions range, accepted override range, unit and confidence.",
            # No "parameters": Gemini rejects an object schema with empty properties (D-055)
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_scenario",
            "description": "Re-optimise the network with parameter overrides at the recommended "
            "service target, and compare it with the recommended network. Example overrides: "
            '[{"key": "diesel_shock_frac", "value": 0.2}] for diesel +20%, '
            '[{"key": "service.min_share_within_radius", "value": 0.85}] for 85% next-day, '
            '[{"key": "warehousing.fixed_cost_per_dc_cr_per_yr", "value": 4.0}].',
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Short label, e.g. diesel_20"},
                    "overrides": {  # a list, not a free-form object, for Gemini (D-055)
                        "type": "array",
                        "description": "Parameters to change, one item each",
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {
                                    "type": "string",
                                    "description": "Parameter key from list_parameters",
                                },
                                "value": {"type": "number"},
                            },
                            "required": ["key", "value"],
                        },
                    },
                },
                "required": ["name", "overrides"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_disruption",
            "description": "Close one recommended DC. mode 'operational': shut for some months, "
            "the other sites absorb its zones (cost of the outage, service lost). mode "
            "'strategic': lost for good, the network is re-optimised without it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dc_id": {"type": "string", "description": "Site id or name, e.g. BLR_HSR"},
                    "months": {"type": "number", "description": "Outage length (operational)"},
                    "mode": {"type": "string", "enum": ["operational", "strategic"]},
                },
                "required": ["dc_id", "mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_scenarios",
            "description": "Side-by-side cost, service and sites for 2 to 6 scenario ids.",
            "parameters": {
                "type": "object",
                "properties": {"ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_network",
            "description": "Structured facts on one scenario's network: each site's zones, "
            "throughput, share of volume and next-day share, plus the cost breakdown.",
            "parameters": {
                "type": "object",
                "properties": {"scenario_id": {"type": "string"}},
                "required": ["scenario_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_assumption_source",
            "description": "Value, unit, range, source and confidence of one assumption "
            "(a parameter key from list_parameters, or a candidate site id for its rent).",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rank_assumptions",
            "description": "The S9 tornado: which uncertain assumptions move total cost, the DC "
            "count and the saving against today's network most (D-040).",
            # No "parameters", as for list_parameters (D-055)
        },
    },
]
TOOL_NAMES = [t["function"]["name"] for t in TOOL_SCHEMAS]


class ToolBox:
    """The agent's tools over one parameter set and one network (spec §10).

    Holds what every call shares: params, the network data, the recorded scenarios and the
    result cache (in memory, and as JSON files in cache_dir keyed by a hash of the arguments).
    """

    def __init__(
        self,
        params: dict,
        data: NetworkData,
        scenario_dir=SCENARIO_DIR,
        cache_dir=CACHE_DIR,
    ) -> None:
        self.params, self.data = params, data
        self.scenario_dir, self.cache_dir = scenario_dir, cache_dir
        self.assumptions_sha256 = hashlib.sha256(ASSUMPTIONS_PATH.read_bytes()).hexdigest()
        self.records: dict[str, dict] = {}  # agent-made scenarios by id
        if cache_dir.exists():
            for path in sorted(cache_dir.glob("*.json")):
                record = json.loads(path.read_text())
                if record.get("assumptions_sha256") == self.assumptions_sha256:
                    self.records[record["scenario_id"]] = record
        upgrades = json.loads((scenario_dir / "S3_upgrade_options.json").read_text())
        self.recommended_id = upgrades["recommended"]["scenario_id"]

    # --- dispatch -------------------------------------------------------------------------

    def call(self, name: str, arguments: dict) -> dict:
        """Run one tool by name. Bad arguments raise ValueError with a user-facing message."""
        if name not in TOOL_NAMES:
            raise ValueError(f"Unknown tool '{name}'; tools are {TOOL_NAMES}")
        try:
            return rounded(getattr(self, name)(**arguments))
        except TypeError as err:  # wrong or missing argument names from the model
            raise ValueError(f"{name}: bad arguments {sorted(arguments)} ({err})") from err

    # --- records ---------------------------------------------------------------------------

    def record(self, scenario_id: str) -> dict:
        """The JSON record of a recorded (outputs/scenarios) or agent-made scenario."""
        if scenario_id in self.records:
            return self.records[scenario_id]
        path = self.scenario_dir / f"{scenario_id}.json"
        if not re.fullmatch(r"[A-Za-z0-9_]+", scenario_id) or not path.exists():
            raise ValueError(f"Unknown scenario_id '{scenario_id}'")
        record = json.loads(path.read_text())
        if "open_dcs" not in record:
            raise ValueError(f"'{scenario_id}' is a table, not a network scenario")
        return record

    @cached_property
    def recommended_record(self) -> dict:
        return self.record(self.recommended_id)

    @cached_property
    def recommended_run(self) -> Run:
        """The recommended network as a solved Run (S5 needs its assignment and flows)."""
        sol = build_and_solve(self.params, self.data)  # base params = the recommended target
        expected = self.recommended_record["cost_cr"]["total"]
        actual = sol.cost.total_inr / self.params["meta"]["crore"]
        if abs(actual - expected) > 1e-6 * expected:
            raise ValueError(f"Re-solved recommended network costs {actual} Cr, record {expected}")
        return Run(self.recommended_id, "S3", "Recommended network", {}, sol)

    @cached_property
    def cleaned_raw(self) -> tuple:
        return clean_raw(self.params)

    def cached_run(self, tool: str, arguments: dict, make_run) -> dict:
        """The record for (tool, arguments): from the cache if seen, else solved and stored."""
        key = cache_key(tool, arguments, self.assumptions_sha256)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            record = json.loads(path.read_text())
        else:
            record = run_record(make_run(), self.params, self.assumptions_sha256)
            record = json.loads(json.dumps(record, default=float))
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, indent=1))
        self.records[record["scenario_id"]] = record
        return record

    @cached_property
    def as_is_data(self) -> NetworkData:
        """Network data with today's depots as the sites, for the S0 record (spec §8)."""
        return as_is_network(self.params, self.data)[0]

    def data_for(self, dc_ids: list[str]) -> NetworkData:
        """The network data whose sites include dc_ids: the candidates, or today's depots."""
        return self.data if set(dc_ids) <= set(self.data.dcs["dc_id"]) else self.as_is_data

    def site_names(self, dc_ids: list[str]) -> list[dict]:
        names = self.data_for(dc_ids).dcs.set_index("dc_id")["name"]
        return [{"dc_id": j, "name": names[j]} for j in dc_ids]

    def resolve_site(self, text: str) -> str:
        """A candidate dc_id from an id or a name fragment ("Hosur" -> BLR_HSR)."""
        dcs = self.data.dcs
        if text.upper() in set(dcs["dc_id"]):
            return text.upper()
        hits = dcs[dcs["name"].str.contains(text, case=False, regex=False)]
        if len(hits) != 1:
            raise ValueError(f"'{text}' does not name exactly one candidate site")
        return hits["dc_id"].iloc[0]

    def summary(self, record: dict) -> dict:
        """A record cut down for the LLM, with deltas against the recommended network."""
        out = {
            "scenario_id": record["scenario_id"],
            "question": record["question"],
            "status": record["status"],
            "n_dcs": len(record["open_dcs"]),
            "sites": self.site_names(record["open_dcs"]),
        }
        if record["group"] == "AG":  # agent-made: echo the overrides so they can be quoted
            out["overrides"] = record["inputs"]
        if "cost_cr" not in record:
            return out | {"note": "No feasible network for these inputs."}
        rec = self.recommended_record
        out |= {
            "cost_cr_per_yr": record["cost_cr"],
            "next_day_share_frac": record["service"]["next_day_share_frac"],
            "two_day_share_frac": record["service"]["two_day_share_frac"],
            "share_of_revenue_frac": record["share_of_revenue_frac"],
            "vs_recommended": {
                "recommended_id": self.recommended_id,
                "recommended_total_cr": rec["cost_cr"]["total"],
                "delta_total_cr": record["cost_cr"]["total"] - rec["cost_cr"]["total"],
                "delta_total_frac": record["cost_cr"]["total"] / rec["cost_cr"]["total"] - 1,
                "delta_by_component_cr": {
                    c: record["cost_cr"][c] - rec["cost_cr"][c] for c in COMPONENTS
                },
                "next_day_change_pts": 100
                * (
                    record["service"]["next_day_share_frac"] - rec["service"]["next_day_share_frac"]
                ),
                "recommended_next_day_share_frac": rec["service"]["next_day_share_frac"],
                "added": sorted(set(record["open_dcs"]) - set(rec["open_dcs"])),
                "dropped": sorted(set(rec["open_dcs"]) - set(record["open_dcs"])),
                "cost_drivers": cost_drivers(record["cost_cr"], rec["cost_cr"]),
                "zones": self.zone_changes(record),
            },
        }
        vs = out["vs_recommended"]
        vs["added_sites"] = self.site_names(vs["added"])
        vs["dropped_sites"] = self.site_names(vs["dropped"])
        return out

    def km_to_dc(self, assignment: pd.Series, data: NetworkData) -> pd.Series:
        """Road km from each zone to the DC serving it, indexed like assignment."""
        km = data.zone_dc_km.loc[assignment.index]
        cols = km.columns.get_indexer(assignment)
        return pd.Series(km.to_numpy()[range(len(km)), cols], index=assignment.index)

    def zone_changes(self, record: dict) -> dict | None:
        """Zones that change DC against the recommended network, where they go, and the zones
        and demand that lose or gain next-day service (on base demand and distances).

        None when the scenario's sites are not candidate sites (today's depots, S0), because
        the two networks then share no sites to compare zone by zone.
        """
        if not set(record["open_dcs"]) <= set(self.data.dcs["dc_id"]):
            return None
        before = pd.Series(self.recommended_record["assignment"])
        after = pd.Series(record["assignment"])[before.index]
        demand = self.data.zones.set_index("zone_id")["demand_t_yr"].loc[before.index]
        moved = after != before
        before_in = self.km_to_dc(before, self.data) <= self.radius_km
        after_in = self.km_to_dc(after, self.data) <= self.radius_km
        losing, gaining = before_in & ~after_in, ~before_in & after_in
        total_t = demand.sum()
        return {
            "moved_count": int(moved.sum()),
            "moved_demand_frac": float(demand[moved].sum() / total_t),
            "moved_to": after[moved].value_counts().sort_index().to_dict(),
            "losing_next_day_count": int(losing.sum()),
            "losing_next_day_demand_frac": float(demand[losing].sum() / total_t),
            "gaining_next_day_count": int(gaining.sum()),
            "gaining_next_day_demand_frac": float(demand[gaining].sum() / total_t),
        }

    # --- the tools (spec §10) --------------------------------------------------------------

    def list_parameters(self) -> dict:
        """Editable parameters with current value, range, accepted range and confidence."""
        return {
            "parameters": [
                {"key": k, **e, "accepted_range": list(accepted_bounds(e))}
                for k, e in editable_parameters(self.params).items()
            ]
        }

    def run_scenario(self, name: str, overrides: list) -> dict:
        """Re-optimise with validated overrides (two-pass free solve, D-034) at the base target.
        overrides is the tool's list of {"key", "value"} items (D-055)."""
        clean = validate_overrides(self.params, overrides_from_items(overrides))
        slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:24] or "run"

        def make_run() -> Run:
            p = apply_overrides(self.params, clean)
            data = self.data
            if any(k.startswith(REBUILD_PREFIXES) for k in clean):
                data = rebuild_data(p, self.data, self.cleaned_raw, list(clean))
            key = cache_key("run_scenario", clean, self.assumptions_sha256)
            return Run(
                f"AG_{slug}_{key[:6]}", "AG", f"What if: {name}", clean, build_and_solve(p, data)
            )

        out = self.summary(self.cached_run("run_scenario", clean, make_run))
        if clean.get(DIESEL_KEY):  # the S6 mechanics, so the answer can explain the cost rise
            out["diesel"] = {
                "diesel_share_of_freight_cost_frac": self.params["transport"][
                    "diesel_share_of_freight_cost"
                ]["value"],
                "freight_multiplier": diesel_overrides(self.params, clean[DIESEL_KEY])[0],
            }
        return out

    def simulate_disruption(self, dc_id: str, mode: str, months: float = 1) -> dict:
        """A recommended DC shut for some months (S5a logic) or lost for good (S5b logic)."""
        dc = self.resolve_site(dc_id)
        rec_open = self.recommended_record["open_dcs"]
        if dc not in rec_open:
            raise ValueError(f"{dc} is not open in the recommended network {rec_open}")
        if mode == "operational":
            if isinstance(months, bool) or not 0 < months <= MAX_OUTAGE_MONTHS:
                raise ValueError(f"months must be in (0, {MAX_OUTAGE_MONTHS}]; got {months!r}")
            args = {"dc_id": dc, "mode": mode, "months": float(months)}
            sid = f"AG_outage_{dc}_{months:g}m"
            record = self.cached_run(
                "simulate_disruption",
                args,
                lambda: operational_outage(
                    self.params, self.data, self.recommended_run, dc, months, sid
                ),
            )
        elif mode == "strategic":
            args = {"dc_id": dc, "mode": mode}
            record = self.cached_run(
                "simulate_disruption",
                args,
                lambda: permanent_loss(
                    self.params, self.data, self.recommended_run, dc, f"AG_loss_{dc}"
                ),
            )
        else:
            raise ValueError(f"mode must be 'operational' or 'strategic'; got {mode!r}")
        out = self.summary(record) | {"closed_site": self.site_names([dc])[0], "mode": mode}
        extra = record["extra"]
        if mode == "operational":
            before = pd.Series(self.recommended_record["assignment"])
            after = pd.Series(record["assignment"])[before.index]
            moved = after[before == dc]
            total_t = self.data.zones["demand_t_yr"].sum()
            out["outage"] = {
                "months": months,
                "outage_cost_cr": extra["outage_cost_cr"],
                "freight_change_cr_per_yr": extra["freight_change_cr_per_yr"],
                "next_day_share_before_frac": extra["next_day_share_before"],
                "next_day_share_during_frac": extra["next_day_share_during"],
                "zones_losing_next_day_count": len(extra["zones_losing_next_day"]),
                "zones_losing_next_day": [display_name(z) for z in extra["zones_losing_next_day"]],
                "demand_losing_next_day_t_yr": extra["demand_losing_next_day_t_yr"],
                "demand_losing_next_day_frac": extra["demand_losing_next_day_t_yr"] / total_t,
                "reassigned_zones_by_site": moved.value_counts().sort_index().to_dict(),
                "not_costed": "lost sales and stock stranded in the closed DC",
            }
        else:
            out["permanent_loss"] = {"penalty_cr_per_yr": extra["penalty_cr_per_yr"]}
        return out

    def compare_scenarios(self, ids: list[str]) -> dict:
        """Side-by-side table of 2 to 6 scenarios."""
        if not isinstance(ids, list) or not 2 <= len(ids) <= 6:
            raise ValueError("ids must be a list of 2 to 6 scenario ids")
        rows = []
        for sid in ids:
            s = self.summary(self.record(sid))
            rows.append(
                {
                    "scenario_id": sid,
                    "question": s["question"],
                    "status": s["status"],
                    "n_dcs": s["n_dcs"],
                    "open_dcs": [site["dc_id"] for site in s["sites"]],
                    **(
                        {
                            "cost_cr_per_yr": s["cost_cr_per_yr"],
                            "next_day_share_frac": s["next_day_share_frac"],
                            "delta_total_vs_recommended_cr": s["vs_recommended"]["delta_total_cr"],
                            "recommended_next_day_share_frac": s["vs_recommended"][
                                "recommended_next_day_share_frac"
                            ],
                            "added_sites": s["vs_recommended"]["added_sites"],
                            "dropped_sites": s["vs_recommended"]["dropped_sites"],
                            "cost_drivers": s["vs_recommended"]["cost_drivers"],
                            "zones": s["vs_recommended"]["zones"],
                        }
                        if "cost_cr_per_yr" in s
                        else {}
                    ),
                }
            )
        return {"recommended_id": self.recommended_id, "scenarios": rows}

    def explain_network(self, scenario_id: str) -> dict:
        """Each site's zones, throughput, share of volume and next-day share (spec §10).

        Throughput comes from the record's plant flows (flow balance, spec §7). Per-site
        next-day shares use the base distances and zone demand; the network total in
        next_day_share_frac is the evaluator's figure for the scenario itself.
        """
        record = self.record(scenario_id)
        out = self.summary(record)
        if "cost_cr" not in record:
            return out
        throughput = pd.DataFrame(record["flows_t_yr"]).groupby("dc_id")["flow_t_yr"].sum()
        assignment = pd.Series(record["assignment"])
        data = self.data_for(record["open_dcs"])
        zones = data.zones.set_index("zone_id").loc[assignment.index]
        within = zones["demand_t_yr"].where(self.km_to_dc(assignment, data) <= self.radius_km, 0.0)
        sites = []
        for site in out["sites"]:
            j = site["dc_id"]
            served = zones[assignment == j].sort_values("demand_t_yr", ascending=False)
            sites.append(
                site
                | {
                    "zones_served": len(served),
                    "largest_zones": served["anchor_name"].head(5).map(display_name).tolist(),
                    "throughput_t_yr": float(throughput.get(j, 0.0)),
                    "share_of_volume_frac": float(throughput.get(j, 0.0) / throughput.sum()),
                    "next_day_share_of_site_frac": float(
                        within[assignment == j].sum() / served["demand_t_yr"].sum()
                    )
                    if len(served)
                    else 0.0,
                }
            )
        cost = record["cost_cr"]
        return out | {
            "sites": sites,
            "next_day_radius_km": self.radius_km,
            "cost_share_frac": {c: cost[c] / cost["total"] for c in COMPONENTS},
        }

    @property
    def radius_km(self) -> float:
        return self.params["service"]["next_day_radius_km"]["value"]

    def get_assumption_source(self, key: str) -> dict:
        """Value, unit, range, source and confidence of one assumption, or one site's rent."""
        dcs = {d["id"]: d for d in self.params["candidate_dcs"]}
        if key.upper() in dcs:
            d = dcs[key.upper()]
            return {
                "key": f"{d['id']} rent",
                "name": d["name"],
                "value": d["rent"],
                "unit": "INR / sq ft / month",
                "range": d.get("rent_range"),
                "source": d.get("source", ""),
                "confidence": d.get("confidence", ""),
            }
        node = self.params
        for part in key.removesuffix(".value").split("."):
            if not isinstance(node, dict) or part not in node:
                raise ValueError(f"Unknown assumption '{key}'; call list_parameters")
            node = node[part]
        if not isinstance(node, dict) or "value" not in node:
            raise ValueError(f"'{key}' is a section, not one assumption")
        fields = ("value", "unit", "range", "source", "confidence")
        return {"key": key} | {f: node[f] for f in fields if f in node}

    def rank_assumptions(self) -> dict:
        """The S9 tornado rows, widest cost swing first, with the recommended base (D-040)."""
        tornado = json.loads((self.scenario_dir / "S9_tornado.json").read_text())
        rec = self.recommended_record
        as_is = self.record("S0")["cost_cr"]["total"]
        return {
            "source_id": "S9_tornado",
            "recommended_id": self.recommended_id,
            "base_total_cr": rec["cost_cr"]["total"],
            "base_saving_vs_as_is_cr": as_is - rec["cost_cr"]["total"],
            "base_n_dcs": len(rec["open_dcs"]),
            "rows": [
                {
                    "parameter": r["parameter"],
                    "range_label": r["label"],
                    "low_total_cr": r["low_total"],
                    "high_total_cr": r["high_total"],
                    "swing_cr": r["swing_cr"],
                    "low_n_dcs": r["low_dcs"],
                    "high_n_dcs": r["high_dcs"],
                    "low_saving_vs_as_is_cr": r["low_saving"],
                    "high_saving_vs_as_is_cr": r["high_saving"],
                }
                for r in tornado
            ],
        }
