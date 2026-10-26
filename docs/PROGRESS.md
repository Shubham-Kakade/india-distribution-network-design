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

---

## 2026-10-25 — Phase 2 (model), Checkpoint B

- Checkpoint A approved and PR #2 merged. The Bihar zones and the DNH & DD zone are kept (D-019).
- `src/costs.py`: `evaluate_network` returns a frozen `CostBreakdown` (six components, next-day and two-day share, share of revenue, and a warning outside 3.5–5.5%). The per-unit helpers it uses also build the MILP proxy.
- `src/model.py`: the spec §7 MILP in PuLP with CBC, all 8 constraint groups, and `build_and_solve(params, data, k, forced_open, forced_closed, fixed_assignment)`. Every solution is re-costed by the evaluator. Status, objective, bound, gap, time and proxy gap are reported, and infeasibility is returned as a status. `python -m src.model` prints the Checkpoint B report.
- `src/baseline.py`: 15 as-is depots at Grade B rents with state-based assignment; flows from the same MILP with the network pinned.
- Headline numbers (evaluator, INR Cr/yr):
  - Base case (400 km / 80%): 9 DCs (MUM_BHW, NCR_FRN, BLR_HSR, HYD_SMB, AMD_CHG, KOL_DNK, LKO_KNP, IDR_PTH, PAT_BHT), **244.1 Cr**, 4.07% of revenue, 80.1% next-day. Prototype: 9 DCs, 244.0 Cr.
  - As-is: **272.6 Cr**, 81.4% next-day. Prototype: 272.7 Cr, 81%.
  - Saving, base case vs as-is: **28.5 Cr (10.5%)**.
  - Sweep for k = 1–12: every total within 0.1% of the prototype; minimum at k = 4 (231.2 Cr), flat to k = 9 (238.1 Cr).
- Every solve is Optimal; the largest MIP gap is 0.12% (k = 5); the slowest solve is 17 s (k = 2); the full run takes 34 s and is deterministic (D-021).
- Proxy gap: at most 1.8% in absolute value in the sweep and as-is. The base case is at +3.2% because the free-run k_ref = 6 sizes each DC's safety stock for 6 DCs while 9 open. This is open question 1 for the supervisor.
- Tests: 49 fast (costs 6, model 9, baseline 3, config 7, plus the Phase 1 tests) and 2 slow, all passing.
- Decisions D-019 to D-026; spec §7 amended (D-021, D-022).

---

## 2026-10-25 — Phase 3 (scenarios), Checkpoint C

- Checkpoint B approved and PR #3 merged (merged in this session on the supervisor's approval; it was still open). Proxy-gap decision logged as D-027.
- `src/scenarios.py`: `python -m src.scenarios` rebuilds the processed data from raw and solves every scenario in dependency order:
  - S0 (as-is), S1 (cost only) and S2 (k = 1..12);
  - S3, the 3 × 6 service frontier, with infeasible cells kept;
  - the knee, which becomes the recommended network;
  - S4 to S8 and S9 (14-parameter tornado) at the recommended service target;
  - S7 rent switching points by bisection;
  - R (no-regret core vs swing sites);
  - the k-COG comparison (D-018, D-033).

  Outputs: 82 JSON scenario records plus R, S7 and S9 tables, `outputs/scenario_summary.csv` (82 rows), six §12 charts and five network maps.
- `src/viz.py`: the six §12 charts (INR Cr axes, footnote, hypothetical-client note, greyscale-legible) and the per-scenario network maps.
- `src/cog.py`: k-weighted centres of gravity with deterministic k-means++ seeding.
- Headline numbers:
  - **Recommended network:** 9 DCs at 400 km / 80% (the knee), INR 244.1 Cr, 80.1% next-day, saving 28.5 Cr against as-is. The Phase 2 base figures are unchanged.
  - **R:** no-regret core of Mumbai, NCR, Bengaluru–Hosur, Hyderabad–Shamshabad, Ahmedabad, Kolkata and Patna; the swing is Indore vs Nagpur (rent vs freight).
  - **Infeasible:** 300 km at 85%, 90% and 95%.
  - **S5a:** an NCR outage costs about 2.4 Cr a month and drops next-day coverage from 80% to 64%.
  - **S5b:** losing NCR permanently costs 2.2 Cr a year.
  - **S9:** fixed cost per DC moves the saving from 19.2 to 37.5 Cr.
  - **S7:** Patna stays open even at three times its rent.
  - **k-COG:** costs 3–11% more than the MILP at the same k.
- Full run: about 7.3 min (spec limit 15 min); two runs from raw give identical outputs apart from solve times.
- Decisions D-027 to D-033. Open questions for the supervisor: knee sensitivity at 400 km / 85% (D-028), the S8 footprint assumptions (D-031), and the S5a costing convention (D-029).
- Chore: pytest filters PuLP's 4.0 deprecation warnings (pinned below 4, D-005).

## 2026-10-26 — Phase 3 (scenarios), Checkpoint C revision

The supervisor approved Phase 3 with two changes. Both are on PR #4.
- **Two-pass free solves (D-034).** Each free solve runs with `k_ref = 6`, then re-solves with `k_ref = k*`, and keeps the lower exact cost. Both passes are recorded in each scenario JSON (`solve.passes`). 13 runs changed, all cheaper or equal. The base case stays at 244.1 Cr. The 400 km / 85% cell is now 248.5 Cr with 11 DCs (it was 250.1 Cr with 10).
- **Recommendation rule (D-028 rewritten).** The recommendation is the cheapest network at service comparable to today's: as-is is 81.4%, so the target is 80%. That gives the same 9 DCs at 244.1 Cr, 80.1% next-day and a 28.5 Cr saving. Kneedle is reported, not used: it now says 85%. The higher targets are priced as upgrade options in `S3_upgrade_options.json`:
  - 85%: +2 DCs (+Guwahati, +Rajpura, Nagpur for Indore), +4.4 Cr/yr;
  - 90%: 12 DCs, +11.3 Cr;
  - 95%: 14 DCs, +20.1 Cr.
- **Staging (D-038).** The 85% network does not contain Indore. A staging run (`S3_400km_80_staged`) puts Nagpur in Indore's place at 80% for +0.33 Cr/yr, after which the 85% upgrade only adds sites. Staged framing in the insights: 7 no-regret sites now, 9 for 80%, 11 for 85%. Above 85% the network re-shapes (NCR is dropped), so it is not a further stage.
- **Code split (D-035).** The scenario code is now three modules: `scenarios.py` (definitions and run loop), `robustness.py` (knee, comparable-service rule, upgrade pricing, R, k-COG) and `reporting.py` (JSON/CSV, charts, maps, printed report). A re-run matched the pre-split outputs file for file.
- **Runtime (D-037).** Two-pass solves pushed the full run to 1,030 s. The S7 site searches now run in a spawn process pool, which brings the run to 656 s (limit 900 s) with outputs identical to the serial run.
- **Write-up.** `docs/scenario_insights.md` was rewritten for the rule, the upgrade table, the staging and the D-036 answers. That includes the S5a line: lost sales and stranded stock are not costed, so the 2.4 Cr is a floor and the service drop is the headline.
- **Re-checked figures.** S4 skew 314.2; S6 +20% gives +17.2 with no site change; S8 no-Puducherry +28.4 (11.7%); S9 fixed-cost saving 19.5–37.5.
- **Decisions:** D-034 to D-038. Tests: 67 fast. Phase tags are created on GitHub by the owner (D-036).
