---
name: scnd-python-standards
description: How Python is written in the India Distribution Network Design project — library-first lookup, when to extract a function, naming with units, typing, docstrings, pandas/numpy idioms, config, logging, errors and tests. Use before writing or changing any file under src/, app/ or tests/, and when reviewing code in this repo.
---

# Python standards for this project

The code is a portfolio piece that a supply-chain hiring manager will read and the owner must explain line by line in an interview. Optimise for **a reader who knows supply chain and basic Python but has never seen this repo**. Clear beats clever. Short beats long only when it is still clear.

These rules sit on top of the `ponytail` skill (smallest complete change). Where they seem to conflict, the tie-breaker is: *would the owner be able to explain this to an interviewer in one sentence?*

---

## 1. Look before you write (library-first ladder)

Before writing any new function, walk this ladder and stop at the first rung that works. State in one line which rung you used when it is not obvious.

1. **Already in this repo?** `grep -rn "<concept>" src/ tests/`. Search for the concept, not only the name (e.g. `haversine`, `distance`, `great_circle`). Reuse it.
2. **Python standard library?** `math`, `statistics`, `itertools`, `functools`, `dataclasses`, `pathlib`, `json`, `logging`, `hashlib`, `copy`.
3. **An approved dependency?** Check the table below before writing a loop. Most "I'll just write a quick helper" moments are one call in pandas or numpy.
4. **One clear line?** Use it.
5. **Otherwise** write the minimum function, with a docstring and a test.

### Approved dependencies and what to reach for

| Need | Use | Not |
|---|---|---|
| Tabular data, joins, group totals | `pandas` (`merge`, `groupby().agg`, `assign`, `pivot_table`) | Python dict-of-lists loops |
| Distance matrices, vector math | `numpy` broadcasting (`np.radians`, `np.sin`… on arrays) | nested `for` loops over rows |
| Nearest-point assignment | `numpy.argmin` on a distance matrix | `iterrows` + `min` |
| MILP / LP | `pulp` with `PULP_CBC_CMD` (`lpSum`, `LpVariable.dicts`) | hand-rolled heuristics |
| Config | `pyyaml` → plain dicts, `copy.deepcopy` for overrides | custom config classes |
| Structured results | `dataclasses.dataclass(frozen=True)` | ad-hoc dicts passed around 3+ functions |
| Maps | `folium` | custom Leaflet JS |
| Charts | `matplotlib` | seaborn/plotly (not approved) |
| Paths | `pathlib.Path`, anchored on one `PROJECT_ROOT` in `config.py` | string concatenation, `os.chdir` |
| Caching scenario results | `hashlib.sha256` of sorted JSON overrides + JSON files | pickle, joblib |
| Tests | `pytest`, `pytest.approx`, `tmp_path` | unittest classes |
| LLM | `openai` SDK against any OpenAI-compatible endpoint, tool calling (D-039) | LangChain or other frameworks; the Anthropic API |
| Secrets | environment variables, or `python-dotenv` reading a git-ignored `.env` | hard-coded keys |
| Lint/format | `ruff check` and `ruff format` | black + flake8 + isort |

**Adding a dependency** needs a one-paragraph entry in `docs/DECISIONS.md` (what it replaces, why the approved list cannot do it). Never add one for something that is a few lines with numpy or pandas. `geopy`, `scikit-learn`, `networkx`, `plotly`, `ortools` and `pyomo` are **not** needed for this project.

---

## 2. When to make a function

Make a function when **any** of these is true:

- **Reuse:** the same logic is (or will be in the current phase's plan) used in two or more places. Example: distance between points is needed for zone→DC, plant→DC, as-is depot→zone.
- **Named domain concept:** the logic is something a supply-chain reader would name. Examples: `haversine_km`, `road_distance_km`, `safety_stock_t`, `space_required_sqft`, `evaluate_network`, `centre_of_gravity`. These get their own function and their own test even if used once, because they are what the reviewer will look for.
- **Testability:** the logic has a branch or edge case that needs a test (the North-East waypoint rule, the min-distance floor, the J&K population fix).

Do **not** make a function:

- just to shorten a long function (split by job, never by line count);
- as a one-line wrapper around a library call (`def load_csv(p): return pd.read_csv(p)`);
- for a "future" use that is not in `docs/BUILD_SPEC_v2.md`.

**One function, one job.** A function that loads, cleans *and* plots is three functions. A function's name says its job as `verb_noun` (`build_zones`, `solve_network`, `plot_cost_curve`). Data-returning functions are named for what they return (`zone_demand_t`).

**Pure where possible.** Domain functions take inputs and return outputs; they do not read files, read globals or print. File I/O happens in thin `load_*` / `save_*` functions and in each module's `main()`.

**Module size guide:** if a module passes ~300 lines, check whether it is doing two jobs. If a function passes ~50 lines, check the same. These are prompts to look, not limits.

---

## 3. Names carry units

Every numeric variable, column and parameter that has a unit carries it as a suffix. This removes a whole class of bugs (km vs road-km, tonnes vs kg, INR vs INR Cr) and makes formulas readable.

| Suffix | Meaning | Example |
|---|---|---|
| `_km` | road km unless named `_gc_km` (great-circle) | `dist_zone_dc_km` |
| `_t` | tonnes | `demand_t`, `safety_stock_t` |
| `_t_yr` | tonnes per year | `throughput_t_yr` |
| `_inr` | rupees | `secondary_cost_inr` |
| `_cr` | INR crore — only at the presentation layer | `total_cost_cr` |
| `_sqft` | square feet | `space_required_sqft` |
| `_inr_tkm` | INR per tonne-km | `secondary_rate_inr_tkm` |
| `_inr_sqft_month` | rent / opex | `rent_inr_sqft_month` |
| `_days` | days of demand | `cycle_stock_days` |
| `_frac` | 0–1 share | `service_share_frac` |

Compute in INR internally; convert to crore only when writing reports and charts (`to_crore(x_inr)` lives in one place).

IDs use the codes in `assumptions.yaml` (`MUM_BHW`, `P_HDW`, `AS_DEL`). Never index sites by list position across modules; pass IDs.

---

## 4. Readability conventions

- **Type hints** on every public function signature. `pd.DataFrame`, `np.ndarray`, `dict[str, float]`, `Path`. No need to annotate local variables.
- **Docstrings** (Google style, short) on every public function: one-line summary, then `Args`/`Returns` only when not obvious from names and hints. For any formula, write the formula and cite the spec section:

  ```python
  def safety_stock_t(
      dc_demand_t_yr: float, national_demand_t_yr: float, ss_days_single_dc: float
  ) -> float:
      """Safety stock held at one DC under the square-root law (spec §6).

      SS_j = (ss_days_1 / 365) * D_total * sqrt(D_j / D_total)
      """
  ```

- **DataFrame contracts.** Each processed table has its columns listed once, as a constant in the module that creates it (`ZONE_COLUMNS = ["zone_id", "anchor_city", "state", "lat", "lon", "demand_t_yr", ...]`) and validated with a small `assert_columns(df, ZONE_COLUMNS)` helper on load.
- **Spec cross-references.** The MILP constraints carry a one-line comment naming the spec constraint: `# spec §7 (3): capacity`. The reader can hold the spec in one hand and the code in the other.
- **Comments say why, not what.** `# Siliguri corridor: only road link to the North-East` — not `# add two distances`.
- **No magic numbers.** Every parameter comes from `assumptions.yaml` via `config.py`. Physical constants (`EARTH_RADIUS_KM = 6371.0`, `DAYS_PER_YEAR = 365`) are named module constants.
- **Shortcuts are labelled** in the form ponytail uses: `# shortcut: single aggregated SKU, upgrade to multi-product if client data has SKU mix`.
- **f-strings** for formatting; thousands separators in reports (`f"{x:,.1f}"`).
- **Imports:** standard library, third-party, local — `ruff` sorts them. No wildcard imports.

---

## 5. pandas and numpy idioms

- Vectorise. `df.iterrows()` is not allowed in `src/` except in tests or on tables known to be < 50 rows (and then add a `# small table` comment).
- Build distance matrices with broadcasting:

  ```python
  lat1, lon1 = np.radians(a_lat)[:, None], np.radians(a_lon)[:, None]
  lat2, lon2 = np.radians(b_lat)[None, :], np.radians(b_lon)[None, :]
  ```

- Prefer method chains with `assign` for derived columns when it stays readable; break into named steps when a chain passes ~5 calls.
- Never mutate a DataFrame passed in as an argument; return a new one (`df = df.copy()` at the top if you must modify).
- Merges state `validate="one_to_one"` / `"many_to_one"` so silent duplication fails loudly.
- After every aggregation that should conserve a total (population, demand), assert it: `assert np.isclose(out.demand_t_yr.sum(), total_t_yr)`.

---

## 6. Config, logging and errors

- `config.load_params(path=None) -> dict` loads and validates `assumptions.yaml` once. `config.with_overrides(params, overrides) -> dict` returns a deep copy with dotted-key overrides (`{"transport.secondary_inr_per_tkm.value": 9.9}`). Every function takes `params` explicitly.
- Use `logging.getLogger(__name__)`. INFO for each data fix applied and each solve summary; WARNING for data anomalies and proxy-vs-evaluator gaps. Never `print` in library code; ruff rule T201 enforces this. The only exception is a module's `print_sanity_report()` function, whose `print` lines carry `# noqa: T201`.
- Fail early and specifically at trust boundaries: raw files, YAML, agent tool arguments. Raise `ValueError` with a message naming the field and the bad value. Inside the domain code, trust validated inputs; do not wrap everything in `try/except`.
- Never swallow exceptions. A bare `except:` or `except Exception: pass` is a defect.
- A solver status other than `Optimal` is returned as data (`status="Infeasible"`), not raised, because infeasibility is a finding.

---

## 7. Testing

- `pytest` in `tests/`, one file per `src/` module (`test_geo.py`, `test_demand.py`, `test_costs.py`, `test_model.py`).
- Test **behaviour and invariants**, not implementation: distances match known pairs, demand is conserved, every zone is assigned once to an open DC, flows balance, the evaluator agrees with the MILP solution.
- Use tiny hand-built fixtures (3 zones, 2 DCs, 1 plant) for model tests so they run in under a second and the expected answer is obvious by inspection. The full India run is a smoke test, marked `@pytest.mark.slow`.
- For a bug: write the failing test first, see it fail, fix, see it pass (see `systematic-debugging`).
- `pytest -q` and `ruff check .` must both pass before any checkpoint (see `scnd-checkpoint`).

---

## 8. Quick self-review before you hand back

Run through this list on your own diff:

1. Did I search the repo and the approved libraries before writing each new function?
2. Is every new function either reused, a named domain concept, or needed for a test?
3. Do names carry units? Any magic numbers?
4. Any `iterrows`, nested loops over DataFrames, or `print` in `src/`?
5. Does every formula cite its spec section?
6. Are totals conserved and asserted?
7. Tests and ruff green, with the output shown?
8. Could the owner explain each new function in one sentence?

For a full review, run the `ponytail-review` skill on the change.
