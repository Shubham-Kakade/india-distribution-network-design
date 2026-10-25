import copy

import pytest

from src.config import PROJECT_ROOT, load_params, validate_params, with_overrides

SECONDARY_RATE_KEY = "transport.secondary_inr_per_tkm.value"


@pytest.fixture(scope="module")
def params() -> dict:
    return load_params()


def test_project_root_holds_assumptions():
    assert (PROJECT_ROOT / "data" / "assumptions.yaml").is_file()


def test_real_assumptions_load_with_expected_site_counts(params):
    # spec §4.4: 19 candidates, 3 plants, 15 as-is depots
    assert len(params["candidate_dcs"]) == 19
    assert len(params["plants"]["list"]) == 3
    assert len(params["as_is_depots"]["list"]) == 15


def test_with_overrides_changes_copy_only(params):
    before = copy.deepcopy(params)
    out = with_overrides(params, {SECONDARY_RATE_KEY: 9.9})
    assert out["transport"]["secondary_inr_per_tkm"]["value"] == 9.9
    assert params == before


def test_with_overrides_rejects_unknown_key(params):
    with pytest.raises(ValueError, match="Unknown parameter path"):
        with_overrides(params, {"transport.no_such_rate.value": 1})


def test_validate_rejects_missing_section(params):
    broken = {k: v for k, v in params.items() if k != "solver"}
    with pytest.raises(ValueError, match="solver"):
        validate_params(broken)


def test_validate_rejects_value_outside_own_range(params):
    broken = with_overrides(params, {"company.annual_volume_tonnes.value": 1})
    with pytest.raises(ValueError, match="outside range"):
        validate_params(broken)


def test_numbers_in_yaml_load_as_numbers(params):
    # PyYAML reads an exponent without a sign (1.0e7) as a string; crore must be numeric
    assert isinstance(params["meta"]["crore"], int | float)
