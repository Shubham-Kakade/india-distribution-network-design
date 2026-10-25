# Decision log

Modelling and engineering decisions, newest first. Each entry records the context, the decision, the alternatives rejected and the expected effect on results.

---

## 2026-10-25 — Phase 1 (data)

**D-013 Each candidate DC and plant carries its `state` in `assumptions.yaml`.** The North-East waypoint rule (spec §5) needs to know whether each endpoint is in the North-East, and sites only had coordinates. An explicit field is easier to audit than guessing the state from the nearest district centroid. No number changes. As-is depots will need the same field in Phase 2. *Rejected:* nearest-district lookup (a hidden data step, and wrong near state borders).

**D-014 Checkpoint reference values live in a new `checks:` section of `assumptions.yaml`; the J&K fix lives in `data/raw/manual_fixes/state_population_patch.csv`.** The Census 2011 total, the §5 calibration pairs and the tolerances are numbers, so they belong in the YAML, not in code. The J&K override sits beside the existing city patch so every manual data fix is in one folder. The states file's Ladakh row repeats the same bogus 1,247,953 (Puducherry's figure), so it is dropped and J&K's 12,541,302 covers both, as spec §4.2 requires. Ladakh's districts become J&K districts.

**D-015 Zone anchors combine the §4.2 and §4.3 rules: 158 zones.** §4.3 adds an anchor for each unanchored state above 1 mn people; the §4.2 table also requires a zone for each state with no city of 1 lakh or more. Applying both gives the top 150 cities, plus Aizawl, Imphal, Shimla, Shillong and Dimapur (above 1 mn), plus North Goa, Papum Pare and Dadra and Nagar Haveli (no city; most populous valid district centroid). Total: 158 zones, which matches the spec's estimate. Ladakh has no zone of its own because it is merged into J&K. Sikkim (0.61 mn, with Gangtok as a city) gets no anchor and joins the nearest zone overall, Siliguri. *Rejected:* §4.3 alone (157 zones, which leaves DNH & DD without the zone §4.2 asks for). *Effect:* DNH & DD is a 98 t/yr zone next to the Silvassa plant; negligible for cost.

**D-016 Distance files are long tables of raw road km; the 25 km floor is applied in the cost engine.** `dist_zone_dc.csv` has columns (zone_id, dc_id, dist_km) and `dist_plant_dc.csv` has (plant_id, dc_id, dist_km). Specs §6 and §7 write the floor as `max(d_zj, 25)` in the cost terms, while the service constraint uses `d_zj ≤ S` on the unfloored distance. Storing the raw distance keeps both uses possible. Phase 2's `costs.py` and `model.py` must apply the floor.

**D-017 The centre of gravity is the Weiszfeld geometric median, which minimises tonne-km.** Spec §11 asks for Weiszfeld. On the 158 zones it gives 21.88°N, 78.62°E, 44 km from the prototype's 21.7°N, 79.0°E. The prototype figure matches the demand-weighted **mean** (21.64°N, 79.01°E), so the gap is a method difference, not a data difference. The sanity report prints both. The update averages degrees as if they were planar, which lands about 15 km from the exact spherical optimum (0.01% more weighted tonne-km). This shortcut is labelled in `cog.py`.

**D-018 `src/viz.py` is created in Phase 1, holding only the demand map; k-COG is deferred.** Spec §11 places folium maps in `viz.py`. The k-weighted centre of gravity exists to compare against the MILP on cost and service (§16), and that comparison needs `costs.evaluate_network`, so it is built with that comparison in Phase 2 or 3. The map uses the default OpenStreetMap tiles, because CartoDB tiles now need an API key.

---

## 2026-10-25 — Supervisor pre-build decisions (spec v2)

**D-001 Service base case at 400 km / 80%.** Indian trucks average about 300–325 km/day (CRISIL), so the brief's 500 km overstates next-day reach. The prototype showed 90% at 400 km needs 12 DCs. The base is 80%; the final recommendation is picked from the S3 frontier. *Rejected:* 500 km / 90% (optimistic transit).

**D-002 Two-echelon model with hypothetical plants.** Haridwar, Silvassa and Puducherry were added so primary freight shapes DC location. *Rejected:* DC-to-zone only (biases towards many DCs near demand).

**D-003 Inventory via the square-root law, evaluated exactly after the solve.** The MILP uses a linear safety-stock proxy per open DC; the evaluator applies SS_j ∝ √D_j. *Rejected:* a piecewise-linear √ in the MILP (adds binaries for little gain at this scale).

**D-004 Demand from state totals plus MPCE index.** The city-only data misses about 55% of FMCG demand, and headcount alone over-weights Bihar and UP. *Rejected:* district-level nodes (double-counted populations, 70 districts without coordinates).

**D-005 PuLP pinned below 4.** PuLP 4.2.0 ships no CBC binary; 3.3.2 does (tested 25 Oct 2026). *Rejected:* HiGHS via `highspy` (works, but adds a dependency and departs from the brief's CBC).

**D-012 Skills committed in `.claude/skills/` (2026-10-26).** Moved from `tooling/claude-skills/` and un-ignored, so cloud sessions at claude.ai/code, which only see the repo, load the same skills as local sessions. This supersedes the "copy in Phase 0, git-ignore the copy" part of D-006. Local setups must delete their untracked `.claude/skills/` copy before pulling.

**D-011 Repository is public from day one (owner decision, 2026-10-25).** This supersedes the "private until Phase 5" part of D-007. Consequences: the pre-push secret and large-file check is mandatory on every push; GitHub secret-scanning push protection applies; work-in-progress branches are visible, so commit messages and PR descriptions are written for an outside reader.

**D-007 GitHub workflow: one branch and one pull request per phase.** Each phase is built on its own branch, pushed at the checkpoint and opened as a PR into `main`. GitHub Actions runs ruff and pytest on every push. The supervisor reviews the PR, and Shubham merges and tags `phase-N`. The repo stays private until Phase 5. *Rejected:* committing straight to `main` (no review point, messier history to show recruiters).

**D-006 Code-quality skills vendored into `.claude/skills/`.** Ponytail (minimal change, review) and obra/superpowers (systematic debugging, verification before completion), both MIT, plus three project skills. Vendoring was preferred over installing the plugins because it pins behaviour and needs no Node hooks on Windows.

---

## 2026-10-25 — Phase 0 setup

**D-008 Python 3.12 venv instead of 3.11.** Only Python 3.12 is installed on the machine (`py -3.11` finds no runtime). `pyproject.toml` allows `>=3.11`, all pinned dependencies install, and `pulp` 3.3.2 lists `PULP_CBC_CMD`. CI still runs 3.11. *Rejected:* installing 3.11 via winget (a machine-level change nobody asked for). Revisit if a 3.11-only behaviour difference shows up in CI.

**D-009 `pythonpath = ["."]` added to `[tool.pytest.ini_options]`.** Without it `pytest -q` (as CI runs it) cannot import `src`. One line, no other change to `pyproject.toml`.

**D-010 Python snippet in `scnd-python-standards/SKILL.md` reformatted by `ruff format`.** Ruff formats code blocks in Markdown, so `ruff format --check .` in CI would otherwise fail on that file. Content unchanged apart from line wrapping.
