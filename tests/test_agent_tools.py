"""Agent tools on the tiny network: argument validation, the cache and the S5 reuse (spec §10)."""

import hashlib
import json

import pytest

from src import agent_tools
from src.agent_tools import ToolBox, validate_overrides
from src.config import ASSUMPTIONS_PATH, with_overrides
from src.model import build_and_solve
from src.reporting import run_record
from src.scenarios import Run, diesel_overrides


@pytest.fixture
def full_service(params):
    # alpha = 1 forces two sites on the tiny network (D2 plus D1 or D3), so an outage has a
    # remaining site to fall back on
    return with_overrides(params, {"service.min_share_within_radius.value": 1.0})


@pytest.fixture
def toolbox(full_service, tiny, tmp_path):
    """A ToolBox over the tiny network, with its recommended record in a temporary folder."""
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    sha = hashlib.sha256(ASSUMPTIONS_PATH.read_bytes()).hexdigest()
    rec = Run("REC", "S3", "q", {}, build_and_solve(full_service, tiny))
    record = run_record(rec, full_service, sha)
    (scenario_dir / "REC.json").write_text(json.dumps(record, default=float))
    (scenario_dir / "S3_upgrade_options.json").write_text(
        json.dumps({"recommended": {"scenario_id": "REC"}})
    )
    return ToolBox(full_service, tiny, scenario_dir=scenario_dir, cache_dir=tmp_path / "cache")


def test_overrides_inside_the_widened_range_are_accepted(params):
    # secondary rate range [7, 11]: width 4, so up to 11 + 2 x 4 = 19 is accepted
    ok = validate_overrides(params, {"transport.secondary_inr_per_tkm.value": 19})
    assert ok == {"transport.secondary_inr_per_tkm": 19.0}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"transport.secondary_inr_per_tkm": 19.5}, "accepted values are [0, 19]"),
        ({"transport.diesel_share_of_freight_cost": 1.2}, "refused"),  # a fraction stays <= 1
        ({"transport.no_such_rate": 1.0}, "not an editable parameter"),
        ({"distance.circuity_factor": "high"}, "not a number"),
        ({"distance.circuity_factor": True}, "not a number"),
    ],
)
def test_bad_overrides_are_refused_with_a_reason(params, overrides, message):
    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        validate_overrides(params, overrides)


def test_repeated_run_is_served_from_the_cache(toolbox, full_service, tiny, monkeypatch):
    solves = []

    def counting_solve(*args, **kwargs):
        solves.append(1)
        return build_and_solve(*args, **kwargs)

    monkeypatch.setattr(agent_tools, "build_and_solve", counting_solve)
    args = {"name": "dearer freight", "overrides": {"transport.secondary_inr_per_tkm": 10}}
    first = toolbox.call("run_scenario", args)
    second = toolbox.call("run_scenario", args)
    reopened = ToolBox(
        full_service, tiny, scenario_dir=toolbox.scenario_dir, cache_dir=toolbox.cache_dir
    )
    third = reopened.call("run_scenario", args)
    assert len(solves) == 1  # the second call and a new session read the cached record
    assert first == second == third
    assert first["overrides"] == {"transport.secondary_inr_per_tkm": 10.0}


def test_diesel_shock_reuses_the_s6_freight_overrides(toolbox, full_service, tiny):
    result = toolbox.call(
        "run_scenario", {"name": "diesel", "overrides": {"diesel_shock_frac": 0.2}}
    )
    expected = build_and_solve(
        with_overrides(full_service, diesel_overrides(full_service, 0.2)[1]), tiny
    )
    assert result["cost_cr_per_yr"]["total"] == pytest.approx(
        expected.cost.total_inr / full_service["meta"]["crore"], abs=0.01
    )


def test_operational_outage_moves_the_closed_sites_zones(toolbox):
    rec_open = toolbox.recommended_record["open_dcs"]
    closed = next(j for j in rec_open if j != "D2")  # D1 or D3, whichever serves Z1
    result = toolbox.call(
        "simulate_disruption", {"dc_id": closed, "mode": "operational", "months": 1}
    )
    assert result["sites"] == [{"dc_id": "D2", "name": "Two"}]
    served = list(toolbox.recommended_record["assignment"].values()).count(closed)
    assert result["outage"]["reassigned_zones_by_site"] == {"D2": served}
    assert result["outage"]["zones_losing_next_day_count"] == 1  # Z1 is 500 km from D2


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ({"dc_id": "Three", "mode": "strategic"}, "not open in the recommended network"),
        ({"dc_id": "D2", "mode": "temporary"}, "mode must be"),
        ({"dc_id": "D2", "mode": "operational", "months": 0}, "months must be"),
        ({"dc_id": "Nowhere", "mode": "strategic"}, "does not name exactly one"),
    ],
)
def test_bad_disruption_arguments_are_refused(toolbox, args, message):
    if args["dc_id"] == "Three" and "D3" in toolbox.recommended_record["open_dcs"]:
        args = args | {"dc_id": "One"}
    with pytest.raises(ValueError, match=message):
        toolbox.call("simulate_disruption", args)


def test_explain_network_accounts_for_all_volume(toolbox):
    result = toolbox.call("explain_network", {"scenario_id": "REC"})
    assert sum(s["share_of_volume_frac"] for s in result["sites"]) == pytest.approx(1, abs=1e-3)
    assert sum(s["zones_served"] for s in result["sites"]) == 3


def test_unknown_tools_and_argument_names_raise_value_error(toolbox):
    with pytest.raises(ValueError, match="Unknown tool"):
        toolbox.call("delete_everything", {})
    with pytest.raises(ValueError, match="bad arguments"):
        toolbox.call("explain_network", {"id": "REC"})
    with pytest.raises(ValueError, match="Unknown scenario_id"):
        toolbox.call("explain_network", {"scenario_id": "../secrets"})
