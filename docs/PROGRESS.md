# Progress log

One entry per checkpoint: phase, what was built, headline numbers, deviations from the spec, open issues.

---

## 2026-10-25 — Pre-build (supervisor)

- Brief reviewed; gap analysis and `docs/BUILD_SPEC_v2.md` written.
- `data/assumptions.yaml` populated (19 candidates, 3 plants, 15 as-is depots, all cost and service parameters with sources and confidence).
- Raw data defects identified and the patch file created (`data/raw/manual_fixes/city_coords_patch.csv`).
- Prototype run: base case 400 km / 80% → about 9 DCs, about INR 244 Cr per year; as-is about INR 273 Cr per year (see spec §3).
- Coding guidelines (`CLAUDE.md`, `.claude/skills/`, `pyproject.toml`) set up.

**Next:** Phase 0 (setup), in Claude Code.

---

## 2026-10-25 — Phase 0 (setup)

- Seven skills copied from `tooling/claude-skills/` to `.claude/skills/` (git-ignored by design).
- venv at `C:\venvs\scnd` (Python 3.12, see D-008); `pip install -r requirements.txt` succeeded; `pulp` 3.3.2 lists `PULP_CBC_CMD`; ruff 0.17.2 runs.
- `git init -b main`, initial commit `chore: project brief, spec, assumptions and guidelines`; branch `phase-0-setup` created.
- `src/config.py` (`load_params`, `validate_params`, `with_overrides`, `PROJECT_ROOT`) and `tests/test_config.py` (6 tests).
- Raw city, district and state CSVs downloaded and pinned (see `docs/sources.md`).
- **Blocked:** `gh repo create` failed with "Resource not accessible by personal access token (createRepository)". No remote exists, so nothing is pushed and no PR is open.

---

## 2026-10-25 — Phase 1 (data), Checkpoint A

- PR #1 (Phase 0) merged into `main` as `343e3c3`. Tag `phase-0` was created locally, but the push was refused (HTTP 403 from the cloud session's git proxy, which allows branch pushes only), so it still needs pushing from a local clone.
- `src/geo.py`: vectorised haversine and road distance (circuity 1.25, Siliguri waypoint when exactly one endpoint is in the North-East).
- `src/demand.py`: two-layer demand (city layer plus rest-of-state district fragments, HCES MPCE index, metro uplift), with the city multiplier solved in closed form at **3.376** (prototype: about 3.4). 158 zones.
- `src/data_prep.py`: every §4.2 defect handled and logged. That covers 37 zero-coordinate city rows (44.55 mn people) patched, the GHMC wards (24 rows in the file, not the 25 the spec says) collapsed and overridden to 6,809,970, 36 Telangana city rows re-mapped, Bally and GHMC duplicates collapsed, GVMC flagged, state names normalised, J&K set to 12,541,302 with Ladakh merged in, 3 non-numeric Mizoram districts dropped, and 69 zero-coordinate districts (85.76 mn people; the spec says 70) dropped. Population and distance calibration checks fail loudly. The Checkpoint A sanity report is printed.
- `src/cog.py`: Weiszfeld centre of gravity, 21.88°N, 78.62°E. `src/viz.py`: `outputs/demand_map.html`.
- Outputs: `data/processed/{zones,candidates,plants,dist_zone_dc,dist_plant_dc}.csv`, `outputs/demand_map.html`.
- Headline numbers: national population 1,210.2 mn (−0.01% against the Census net of the islands); demand 300,000 t/yr; largest zone Greater Mumbai at 3.63%; Delhi 3.29%, Bengaluru 3.21%, Hyderabad 3.17%; rest-of-state share 55.0%; all 7 calibration pairs within 9.6%.
- Tests: 30 pass (geo 6, demand 6, data_prep 10, cog 2, config 6).
- Decisions D-013 to D-018.
- **Open:** two Bihar zones (Muzaffarpur 1.89%, Bhagalpur 1.67%) are in the top 10, because only 4 Bihar cities make the top 150 and each zone gathers 18 to 36 mn mostly rural people. The supervisor needs to decide whether this is acceptable.
