"""Load and validate data/assumptions.yaml: the only way parameters enter the code."""

import copy
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSUMPTIONS_PATH = PROJECT_ROOT / "data" / "assumptions.yaml"

REQUIRED_SECTIONS = (
    "meta",
    "company",
    "demand",
    "distance",
    "transport",
    "service",
    "warehousing",
    "plants",
    "candidate_dcs",
    "as_is_depots",
    "solver",
    "scenarios",
)


def load_params(path: Path | None = None) -> dict:
    """Read assumptions.yaml into a plain dict and validate it (spec §0)."""
    with (path or ASSUMPTIONS_PATH).open(encoding="utf-8") as f:
        params = yaml.safe_load(f)
    validate_params(params)
    return params


def validate_params(params: dict) -> None:
    """Fail early on a missing section, an empty site list or a value outside its own range."""
    missing = [s for s in REQUIRED_SECTIONS if s not in params]
    if missing:
        raise ValueError(f"assumptions.yaml is missing sections: {missing}")
    site_lists = {
        "candidate_dcs": params["candidate_dcs"],
        "plants.list": params["plants"]["list"],
        "as_is_depots.list": params["as_is_depots"]["list"],
    }
    for name, sites in site_lists.items():
        if not sites:
            raise ValueError(f"assumptions.yaml section '{name}' is empty")
    for dotted_key, entry in entries_with_range(params):
        low, high = entry["range"]
        if not low <= entry["value"] <= high:
            raise ValueError(f"{dotted_key}: value {entry['value']} outside range [{low}, {high}]")


def with_overrides(params: dict, overrides: dict[str, object]) -> dict:
    """Return a deep copy of params with dotted-key overrides applied (spec §9).

    Example: {"transport.secondary_inr_per_tkm.value": 9.9}. Unknown keys raise ValueError so a
    typo cannot silently run the base case.
    """
    out = copy.deepcopy(params)
    for dotted_key, new_value in overrides.items():
        *parents, leaf = dotted_key.split(".")
        node = out
        for part in parents:
            if not isinstance(node, dict) or part not in node:
                raise ValueError(f"Unknown parameter path: {dotted_key}")
            node = node[part]
        if not isinstance(node, dict) or leaf not in node:
            raise ValueError(f"Unknown parameter path: {dotted_key}")
        node[leaf] = new_value
    return out


def entries_with_range(node: object, prefix: str = ""):
    """Yield (dotted_key, entry) for every numeric {value, range} entry in the tree."""
    if isinstance(node, dict):
        value, rng = node.get("value"), node.get("range")
        if isinstance(value, int | float) and isinstance(rng, list) and len(rng) == 2:
            yield prefix, node
        for key, child in node.items():
            yield from entries_with_range(child, f"{prefix}.{key}" if prefix else key)
    elif isinstance(node, list):
        for i, child in enumerate(node):
            yield from entries_with_range(child, f"{prefix}[{i}]")
