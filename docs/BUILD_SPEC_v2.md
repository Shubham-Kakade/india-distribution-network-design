# India Distribution Network Design: Build Specification v2

**Owner:** Shubham Kakade  |  **Prepared:** 25 Oct 2026  |  **Supersedes:** sections 3, 4 and 9 of `PROJECT_BRIEF.md` where they conflict
**Audience:** Claude Code (builder) and the supervising reviewer. Claude Code must read this file in full before writing code.

---

## 0. How to use this document

`PROJECT_BRIEF.md` remains the statement of purpose: the target role, the business question and the definition of done. This specification is the engineering and modelling contract. Wherever the two disagree, this document wins. Every parameter lives in `data/assumptions.yaml`, which has been populated with sourced values, confidence ratings and sensitivity ranges. Code must read from that file and never hard-code a number.

The build runs in six phases (section 15). Each phase ends at a checkpoint, where the supervisor reviews outputs against the acceptance criteria in section 13 before the next phase starts. Claude Code should stop at each checkpoint and print the sanity summary specified for that phase.

---

## 1. Summary of changes from the original brief

The original brief is sound in scope but would produce a model that a network-design practitioner would challenge within the first five minutes of an interview. The table below lists the material changes, ordered by how much each one affects the credibility of the final recommendation.

| # | Gap in original brief | Why it matters | Resolution in v2 |
|---|---|---|---|
| 1 | The city dataset has broken records: Mumbai, Delhi, Bengaluru and Hyderabad have coordinates of (0, 0), and Hyderabad is split into 25 ward rows | 37 rows, 44.6 mn people and about 20% of the urban layer would be placed in the Gulf of Guinea, silently distorting every result | Coordinate patch file, ward collapse, state re-mapping (section 4.2) |
| 2 | Demand covers cities only; rural India and towns under 1 lakh are missing | Rural is about 45% of FMCG revenue; a city-only model under-weights the Gangetic plain and the East | Two-layer demand model built from state totals (section 4.3) |
| 3 | Demand is driven by headcount alone | Bihar and UP towns rank as top demand zones despite the lowest per-capita spend | State consumption index from MoSPI HCES 2023-24 (section 4.3) |
| 4 | No inbound (plant to DC) leg | Without primary freight the model is blind to plant proximity and over-opens DCs near demand | Three hypothetical plants with capacity; continuous primary flow variables (section 7) |
| 5 | Only fixed rent penalises extra DCs | The cost curve has no realistic minimum, and inventory pooling, the core trade-off in network design, is absent | Space cost tied to stock held, square-root-law safety stock, per-DC fixed overhead (section 6) |
| 6 | One freight rate for all legs | FTL primary and part-load secondary differ by a factor of about 1.6 per tonne-km | Separate primary (INR 5.5) and secondary (INR 9.0) rates (assumptions §4) |
| 7 | 500 km taken as next-day | Indian trucks average about 300-325 km/day; 500 km overstates next-day reach | 400 km base, 300 / 500 as sensitivities (assumptions §5) |
| 8 | Circuity 1.3 everywhere | Kolkata–Guwahati comes out at 681 km against about 1,030 km by road because of the Siliguri corridor | Calibrated 1.25 plus a Siliguri waypoint for North-East routes (section 5) |
| 9 | No as-is baseline | A network study without "savings versus today" has no business case | Hypothetical 15-depot pre-GST state C&F network evaluated on the same cost engine (section 8) |
| 10 | Candidate set leaves Kerala, Odisha and the North outside every 400 km ring | High service targets become infeasible, which is a data artefact rather than an insight | 19 candidates, including Kochi, Bhubaneswar, Rajpura, Jaipur, Patna, Lucknow, Indore, Guwahati |
| 11 | `pulp` unpinned | PuLP 4.x no longer bundles CBC (verified 25 Oct 2026: 4.2.0 lists no solvers, 3.3.2 lists `PULP_CBC_CMD`) | Pin `pulp>=2.8,<4` |
| 12 | Unverified rents for Pune, NCR, Kolkata, Nagpur | The real-estate angle is the C&W hook, so weak rent data undermines it | Sourced to Knight Frank, Colliers and H1 2026 consultancy data; low-confidence rows explicitly flagged |
| 13 | Disruption treated only as "force-close the top DC" | Conflates a one-month operational outage with a strategic site loss | Two disruption modes: operational recourse and strategic re-optimisation (section 9) |
| 14 | Agent design unspecified | An LLM that computes or invents numbers would discredit the demo | Tool-only numerics, parameter guardrails, scenario cache, offline mode (section 10) |
| 15 | No affiliation disclaimer | The project uses C&W's name and market data | README and app footer carry an "independent portfolio project, not affiliated" line |

---

## 2. Gap analysis by lens

The review applied five lenses that a network-design engagement lead would use on a junior team's model.

**Problem framing.** The brief asks a greenfield question but frames the business case around an existing "ad-hoc" network. A client always asks what it saves compared with today. v2 therefore runs three studies on one cost engine: an **as-is** evaluation of the current depots, a **greenfield** optimum, and a **service-constrained** optimum. India-specific framing matters here. Before GST, national FMCG companies typically ran one carrying-and-forwarding depot per state, to manage interstate tax rather than logistics. GST removed that constraint, and the resulting consolidation into regional mega-DCs is the dominant warehousing story of the last eight years. The as-is network is built to reflect that history.

**Data integrity.** Section 4.2 lists the defects in the source data verbatim. They were found by inspection, not assumed, and the build must reproduce the checks.

**Model structure.** The original formulation is a single-echelon capacitated facility-location problem with transport and fixed cost only. v2 makes it two-echelon (plant to DC to demand zone). It adds the three cost drivers that create the classic U-shaped total-cost curve: secondary freight falls as DCs are added, while fixed overhead and pooled safety stock rise. Rent is made a per-tonne cost that differs by cluster, so the real-estate data actually influences site choice.

**Analysis design.** The original scenario list varies inputs but has no structure for drawing insight. v2 organises scenarios around four questions a client steering committee asks: what it costs, what service it buys, how robust the answer is, and what would change the answer. It adds a tornado analysis and a site-robustness heatmap so the write-up can separate robust conclusions from fragile ones.

**Delivery and credibility.** Each number shown to a reader traces to a source and a confidence level. Low-confidence assumptions are named in the README, and the tornado shows that the recommendation survives them. The agent never produces a number that the model did not compute.

---

## 3. Supervisor prototype: indicative results

Before writing this specification, the supervisor ran a throwaway prototype of the v2 model on the populated `assumptions.yaml` to confirm that the parameters produce a sensible, non-degenerate answer. **These figures are for calibration only and must not be quoted in the deliverables.** Claude Code's implementation must reproduce them independently. Any difference above about 5% on a total, or a different site set at the base case, must be explained at Checkpoint B.

**Cost by number of DCs (no service constraint), INR Cr per year**

| DCs | Primary | Secondary | Space | Handling | Inventory | Fixed | **Total** | Demand ≤ 400 km |
|---|---|---|---|---|---|---|---|---|
| 1 | 148.2 | 280.6 | 8.4 | 6.6 | 18.0 | 3.0 | **464.8** | 10% |
| 2 | 64.0 | 207.4 | 12.6 | 6.6 | 21.4 | 6.0 | **317.9** | 30% |
| 3 | 32.6 | 165.0 | 14.1 | 6.6 | 23.9 | 9.0 | **251.3** | 40% |
| 4 | 57.5 | 113.9 | 14.8 | 6.6 | 26.2 | 12.0 | **231.0** | 49% |
| 6 | 61.3 | 100.9 | 16.8 | 6.6 | 29.4 | 18.0 | **232.9** | 60% |
| 9 | 66.8 | 83.4 | 20.0 | 6.6 | 34.1 | 27.0 | **237.9** | 70% |
| 12 | 79.3 | 62.9 | 24.5 | 6.6 | 37.6 | 36.0 | **247.0** | 80% |

**Cost-optimal network for each service target (DC count chosen by the model)**

| Radius | α = 80% | α = 85% | α = 90% | α = 95% |
|---|---|---|---|---|
| 300 km | 14 DCs, 257.4 | infeasible | infeasible | infeasible |
| 400 km | 9 DCs, 244.0 | 11 DCs, 248.2 | 12 DCs, 255.3 | 14 DCs, 264.0 |
| 500 km | 7 DCs, 238.4 | 8 DCs, 240.8 | 9 DCs, 244.4 | 11 DCs, 249.8 |

**As-is (15 state depots, Grade B):** total INR 272.7 Cr, with 81% of demand within 400 km.

Six observations follow from the prototype. They are hypotheses that the full build should test and, if they hold, turn into the narrative of the case study.

1. **The cost curve is flat-bottomed.** Total cost varies by about 3% between four and nine DCs. That spread is within the uncertainty of the low-confidence inputs, so cost alone cannot pick the DC count. Service policy and real-estate factors decide it, and that is precisely the C&W value proposition: network modelling narrows the field, then real-estate expertise selects within it.
2. **Service is the binding driver.** The cost-only optimum (four DCs) reaches only about half of demand next-day. Reaching 80% at 400 km costs about INR 13 Cr per year more (about 6%), and each further five points of service costs more again. The "price of service" curve is the hero chart.
3. **Consolidation saves about 10% against the as-is network at the same service level.** That is about INR 29 Cr per year (272.7 down to 244.0), while secondary freight rises from 58.5 to 71.4. The trade-off reads cleanly: fewer, larger DCs exchange higher last-mile freight for lower fixed, inventory and primary cost.
4. **The savings headline depends heavily on the fixed cost per DC.** About INR 18 Cr of the INR 29 Cr saving comes from running six fewer sites at INR 3 Cr each, which is a low-confidence assumption. The tornado must show this openly; it is the first question an interviewer will ask.
5. **The network core is stable under fuel and growth shocks, and central India is the swing site.** At the base case (400 km / 80%), diesel +20% and demand +30% each keep eight of the nine sites. Indore–Pithampur is swapped for Nagpur–MIHAN, consistent with the demand centre of gravity at about 21.7°N, 79.0°E, just north of Nagpur. The write-up should present central India as "one site, location to be decided by real-estate diligence".
6. **Mumbai and Pune are near-perfect substitutes.** At 500 km / 90%, losing Bhiwandi permanently shifts the West to Chakan at a penalty under 1%. The interesting disruption is therefore the **operational** one-month outage, where the network cannot re-site.

Two caveats from the prototype must be carried into the build. Patna–Bihta is selected in almost every scenario, but its rent is a low-confidence estimate and Grade A supply in Patna is thin, so the real-estate overlay must flag it. Plant locations also shape the answer heavily: the three-DC solution sits next to the three plants. A plant sensitivity (scenario S8) is therefore recommended.

---

## 4. Data specification

### 4.1 Sources

Use the GitHub repository `recurze/IndianCities` as the single source of population and coordinates. Do not use the Kaggle dataset, which requires a login and breaks one-command reproducibility. Download `final_cities.csv`, `final_districts.csv` and `final_states.csv` into `data/raw/` and commit them, since they are small and pinning them guarantees reproducibility. Record the commit hash in `docs/sources.md`.

### 4.2 Known defects (verified by the supervisor on 25 Oct 2026)

| File | Defect | Required handling |
|---|---|---|
| `final_cities.csv` | 37 rows with Latitude = Longitude = 0, covering 44.6 mn people (Greater Mumbai, DMC Delhi, BBMP Bengaluru, all GHMC rows, GVMC, Hubli-Dharwad and others) | Apply `data/raw/manual_fixes/city_coords_patch.csv`; then `assert (lat != 0).all()` |
| `final_cities.csv` | Hyderabad split into 25 "GHMC" ward rows summing to 8.27 mn, above the 2011 urban agglomeration of 7.75 mn | Collapse to one city and override the population to 6,809,970 (GHMC M.Corp 2011), as set in the patch file |
| `final_cities.csv` | Telangana cities labelled "Andhra Pradesh" (pre-2014 state) | Re-map to Telangana where District ∈ {Adilabad, Nizamabad, Karimnagar, Medak, Hyderabad, Rangareddy, Mahbubnagar, Nalgonda, Warangal, Khammam} |
| `final_cities.csv` | Duplicate city rows (Bally ×2, GHMC ×25) | Group by (State, City) and sum population |
| `final_cities.csv` | GVMC population equals the first GHMC row (1,730,320), a likely copy error; the true 2011 figure is about 1.73 mn | Keep, but log a warning |
| `final_cities.csv` | State spellings ("Jammu & Kashmir", "Andaman & Nicobar Islands") differ from the states file | Normalise names through one mapping dict in `data_prep.py` |
| `final_cities.csv` | Goa, Arunachal Pradesh, DNH & DD and Ladakh have no cities ≥ 1 lakh | Create their demand zone from the most populous valid district centroid |
| `final_states.csv` | Jammu & Kashmir population recorded as 1,247,953 (should be 12,541,302 in Census 2011 including Ladakh) | Override and treat J&K plus Ladakh as one state for demand |
| `final_districts.csv` | Population stored as text, with "-" for three Mizoram districts | `pd.to_numeric(errors="coerce")` and drop the nulls |
| `final_districts.csv` | 70 districts (85.8 mn people) with zero coordinates; post-2011 district splits double-count (state sums exceed state totals by up to 22%) | Use districts **only as within-state spatial weights** for the rest-of-state layer; drop zero-coordinate rows and rescale the weights within each state |

After cleaning, national population must be within 0.5% of 1,210.9 mn (Census 2011), net of the excluded island territories.

### 4.3 Demand model

Demand is built in two layers per state, then aggregated into demand zones.

**City layer.** Each cleaned city with population of 1 lakh or more is a point of urban demand.

**Rest-of-state layer.** Rest-of-state population = state population − sum of city-layer population in that state. It is spread across the state's valid district centroids in proportion to district population (rescaled within the state).

**Zones.** Take the 150 most populous cities as zone anchors, add one anchor for every state above 1 mn population that has none, and expect about 158 zones. Assign each city and each district fragment to the nearest anchor **in the same state**, falling back to the nearest anchor overall when the state has none. A zone's location is its anchor city, which represents where the distributor or super-stockist sits.

**Per-capita index.** City-layer population is weighted by `(state urban MPCE / All-India urban MPCE) ^ elasticity` × the metro uplift where applicable × a city-layer multiplier. Rest-of-state population is weighted by `(state rural MPCE / All-India rural MPCE) ^ elasticity`. The city-layer multiplier is solved in closed form so that the rest-of-state layer delivers `residual_share_target` (55%) of national demand; the prototype solves it at about 3.4. Finally, scale demand so the national total equals `company.annual_volume_tonnes` (300,000 t).

**Expected result.** Delhi, Mumbai, Bengaluru and Hyderabad zones each carry about 3% of national volume; the North-East is represented through Guwahati; and no zone exceeds 5%.

### 4.4 Candidate and source tables

Candidate DCs (19), plants (3) and as-is depots (15) are defined in `assumptions.yaml`. The `metro_group` field enforces at most one site per metro, so the model chooses Hoskote **or** Hosur and Medchal **or** Shamshabad. That choice between micro-markets is a deliberate real-estate feature to discuss in the write-up.

---

## 5. Distance model

The road distance between two points is the haversine distance multiplied by the circuity factor (1.25), with one exception. If exactly one endpoint lies in the North-East states listed in `assumptions.yaml` (including Sikkim), the route is forced through the Siliguri waypoint: `d = circuity × (hav(a, Siliguri) + hav(Siliguri, b))`.

A floor of `intra_zone_min_distance_km` (25 km) applies to every DC-to-zone distance, so that a DC inside a zone still incurs local delivery cost.

**Calibration check.** `data_prep.py` must print these pairs against reference road distances and fail if any is off by more than 15%: Mumbai–Delhi about 1,420 km; Bengaluru–Chennai about 345; Delhi–Lucknow about 555; Hyderabad–Bengaluru about 570; Mumbai–Pune about 150; Mumbai–Ahmedabad about 530; Kolkata–Guwahati about 1,030.

An optional enhancement, if time allows after Phase 3, is to replace the haversine proxy with OSRM table-API road distances cached to `data/processed/road_km.csv`. The model must still run fully offline from the cached file.

---

## 6. Cost model: one evaluator for everything

All costs are computed by a single function, `costs.evaluate_network(open_dcs, assignment, flows, params, data) -> CostBreakdown`. The MILP solution, the as-is network, every scenario and every agent query pass through this one function, so the numbers stay comparable. The MILP objective is a **linear proxy** of this evaluator, as described in section 7. The evaluator is the exact cost, and it is the figure that is reported.

| Component | Formula (annual, INR) | Notes |
|---|---|---|
| Primary freight | Σ_p Σ_j r_p · d_pj · f_pj | r_p = primary rate × freight multiplier |
| Secondary freight | Σ_z D_z · r_s · max(d_zj, 25) for the assigned j | r_s = secondary rate × freight multiplier |
| Handling | h · Σ_z D_z | constant in total, but kept for completeness and for scenario deltas |
| Safety stock (t) | SS_j = (ss_days_1 / 365) · D_total · √(D_j / D_total) | square-root law: total SS rises with the number of DCs |
| Cycle stock (t) | CS_j = (cycle_days / 365) · D_j | |
| Space (sq ft) | A_j = max(min_size, (CS_j + SS_j) / density / utilisation), capped at max_size | |
| Space cost | Σ_j A_j · (rent_j + opex) · 12 | rent_j is cluster-specific |
| Inventory carrying | i · v · Σ_j (CS_j + SS_j) | v = realisation × COGS share × 1,000 per tonne |
| Fixed | F · number of open DCs | |
| Service | share of D within the radius, computed from the assigned distances | reported alongside 2-day share |

The breakdown is returned as a dataclass and also expressed as a percentage of revenue. A total logistics cost of 3.5–5.5% of revenue is the plausibility band for Indian FMCG; outside it, the evaluator logs a warning.

---

## 7. Optimisation model (PuLP + CBC)

**Sets.** Plants *P*, candidate DCs *J*, zones *Z*, metro groups *M*.

**Decision variables.**
- `y_j ∈ {0,1}`: DC *j* is open.
- `x_zj ∈ {0,1}`: zone *z* is served by DC *j* (single sourcing).
- `f_pj ≥ 0`: tonnes per year from plant *p* to DC *j*.

**Objective (linear proxy).**

```
min  Σ_j (F + SS_proxy) · y_j
   + Σ_z Σ_j D_z · ( r_s · d̃_zj + h + s_j ) · x_zj
   + Σ_p Σ_j r_p · d_pj · f_pj
```

where `d̃_zj = max(d_zj, 25)`; `s_j = (cycle_days/365) / density / utilisation × (rent_j + opex) × 12` is the space cost per tonne of throughput at site *j*; and `SS_proxy = i · v · (ss_days_1/365) · D_total / √k_ref` is the average safety-stock carrying cost per DC. Use `k_ref` = k in the DC-count sweep and 6 in free runs.

**Constraints.**
1. Σ_j x_zj = 1 for every zone.
2. x_zj ≤ y_j.
3. Σ_z D_z · x_zj ≤ Cap_j · y_j, where Cap_j = max_size × utilisation × density × 365 / (cycle_days + ss_days_1).
4. Σ_p f_pj = Σ_z D_z · x_zj (flow balance at each DC).
5. Σ_j f_pj ≤ plant share × D_total × headroom.
6. Σ_z Σ_j D_z · x_zj · [d_zj ≤ S] ≥ α · D_total (service).
7. Σ_{j∈m} y_j ≤ 1 for each metro group *m*.
8. Optional: Σ_j y_j = k (sweep); y_j = 0 for forced closures; y_j = 1 for forced opens; x fixed for operational-recourse runs.

**Solver settings.** CBC with a relative gap of 0.5%, a 300 s time limit and 4 threads, all from `assumptions.yaml`. Report status, objective, best bound, gap and wall-clock time for every solve. A solve that returns anything other than Optimal must be reported as such (for example "infeasible at 300 km / 85%"), never silently dropped, because infeasibility is itself an insight.

**Expected scale.** About 158 × 19 ≈ 3,000 binaries plus 57 continuous variables. The prototype solved most instances in under 2 seconds, with a worst case of about 30 seconds.

**Proxy fidelity check.** For every solve, compare the MILP objective with `evaluate_network` on the same solution. If the difference exceeds 3%, log a warning; it would indicate that the safety-stock proxy needs recalibrating.

---

## 8. As-is baseline

The as-is network is hypothetical but deliberately realistic: 15 state carrying-and-forwarding depots in Grade B space, at the cluster rent discounted by 20%. Each zone is served by its own state's depot under the mapping in `assumptions.yaml`; states not listed map to the nearest depot. Plant-to-depot flows are optimised with a small LP, on the reasoning that today's planners already source sensibly. The as-is network is evaluated with the same `evaluate_network`. The case study must label it clearly as an illustrative baseline, not observed client data.

---

## 9. Scenarios

Each scenario is a named parameter override applied to a deep copy of the assumptions. It is solved and evaluated, then written to `outputs/scenarios/<id>.json` with full inputs, open sites, assignments and cost breakdown. A single summary row per scenario goes to `outputs/scenario_summary.csv`.

| ID | Question for the steering committee | Change | Primary output | Insight the write-up must state |
|---|---|---|---|---|
| S0 | What does today cost? | As-is depots | Cost breakdown, service map | The baseline everything is compared against |
| S1 | What is the cheapest possible network? | Greenfield, no service constraint | Sites, cost | Cost-optimal network and its service shortfall |
| S2 | How many DCs? | k = 1…12 | U-curve with stacked components | Location and flatness of the minimum |
| S3 | What does service cost? | S ∈ {300, 400, 500} × α ∈ {0.70, 0.75 … 0.95} | Cost-vs-service frontier | Price of each service step; recommended knee point |
| S4 | Does growth change the answer? | Demand +30% uniform, plus a regional-skew variant | Sites and cost deltas | Stability of the site set; capacity headroom |
| S5a | What if a site goes down for a month? | Highest-throughput DC closed; open set fixed; zones re-assigned; capacity +20% surge allowed | Cost and service hit × months/12 | Operational resilience; which zones lose next-day service |
| S5b | What if we lose the site permanently? | Same DC excluded; full re-optimisation | New sites, cost | Strategic substitute site and its penalty |
| S6 | Fuel shock? | Diesel +20% and +40% → freight × (1 + 0.55 × shock) | Cost deltas, any site changes | Whether higher freight pushes towards more DCs |
| S7 | Real-estate sensitivity? | Rents ±20%; per-site rent switching point by bisection | Rent at which each chosen site drops out | How much rent headroom each recommended site has (the C&W angle) |
| S8 | Does plant footprint drive the answer? | Remove Puducherry; or add an eastern plant | Sites, cost | Separates network design from sourcing footprint |
| S9 | Which assumptions matter? | Each low/medium-confidence parameter at its range ends | Tornado on total cost and on the recommended DC count | Which conclusions are robust and which are fragile |
| R | Which sites are no-regret? | Across S1–S8 | Site × scenario open/closed heatmap | No-regret core sites versus swing sites |

The **recommendation** is the network at the knee of the S3 frontier, cross-checked against the R heatmap. It is stated as "open N DCs at …; INR X Cr per year; Y% of demand next-day; INR Z Cr per year saving versus today," together with the swing sites and the condition under which each would change.

---

## 10. Agentic layer

**Purpose.** The agent shows the "agentic AI in supply chain optimisation" capability named in the job post. Its job is to translate a business question into a model run and explain the trade-off. The model does the computing; the agent does the explaining.

**Stack.** `anthropic` Python SDK with tool use; model name read from the environment variable `ANTHROPIC_MODEL`, defaulting to `claude-sonnet-5-5`; API key from `.env` via `python-dotenv`; Streamlit front end.

**Tools** (JSON schema in `src/agent_tools.py`, implementations calling `scenarios.py`):

| Tool | Arguments | Returns |
|---|---|---|
| `list_parameters()` | none | Editable parameters with current values, bounds and confidence |
| `run_scenario(name, overrides)` | dict of parameter overrides, validated against bounds | scenario_id, sites, cost breakdown, service, deltas against base |
| `simulate_disruption(dc_id, months, mode)` | mode ∈ {operational, strategic} | Cost and service impact, re-assigned zones |
| `compare_scenarios(ids)` | list of scenario_ids | Side-by-side table |
| `explain_network(scenario_id)` | id | Structured facts: each site's zones, throughput, share of cost, next-day share |
| `get_assumption_source(key)` | key | Value, source and confidence for that parameter |

**Guardrails.**
- The system prompt states that every number in a reply must come from a tool result in the current conversation, and that the scenario_id must be cited.
- Overrides outside the YAML ranges, by more than 2× the range width, are rejected with an explanation.
- Results are cached by a hash of the overrides, so repeated questions answer instantly.
- Tool calls are capped at 6 per user turn.
- An **offline mode** pre-computes a library of 20 common scenarios, so the recorded demo cannot fail on API or network issues.

**User interface.** The left pane is a chat. The right pane shows a folium map of the current scenario and a cost-breakdown bar chart compared with base. A footer carries the disclaimer.

**Demo script** (for the GIF and the DM):
1. "What's our recommended network and what does it cost?"
2. "What if Hosur shuts for a month?" (operational disruption)
3. "And if we lost it permanently?"
4. "Diesel just went up 20%. Should we change anything?"
5. "Which of our assumptions should I worry about most?" (the agent calls the tornado results)

---

## 11. Code architecture and engineering standards

```
src/
  config.py         load + validate assumptions.yaml; deep-copy + override helper
  data_prep.py      clean raw -> processed (cities, zones, candidates, plants, distances); sanity report
  geo.py            haversine, NE waypoint routing, distance matrices
  demand.py         two-layer demand + calibration
  costs.py          evaluate_network() and the CostBreakdown dataclass   <- single source of truth
  model.py          build_and_solve(params, data, k=None, forced_open=(), forced_closed=(), fixed_assignment=None)
  baseline.py       as-is network evaluation
  cog.py            single and k-weighted centre-of-gravity (Weiszfeld) for comparison
  scenarios.py      S0-S9 + R; `python -m src.scenarios` reproduces everything end to end
  viz.py            folium maps, matplotlib charts (consistent palette, INR Cr axis labels)
  agent_tools.py    tool schemas + implementations
  agent.py          Claude tool-use loop, guardrails, cache
app/streamlit_app.py
tests/              pytest: geo, demand conservation, evaluator, model invariants
```

**Standards.**
- Python 3.11 or later. Pin `pulp>=2.8,<4`.
- Create the virtual environment **outside the OneDrive folder** (for example `C:\venvs\scnd`), or OneDrive will try to sync thousands of package files.
- Initialise git in the project folder with a `.gitignore` covering `.env`, `__pycache__/`, `.venv/`, `outputs/scenario_cache/` and large intermediates.
- Every function that takes parameters takes the params dict explicitly; nothing reads global state.
- Results are deterministic: fixed seeds wherever anything is random, and sorted iteration over sets.
- Logging uses the `logging` module at INFO level, never bare prints, except for the phase sanity reports.

**Minimum tests.**
- Haversine Mumbai–Delhi lies between 1,140 and 1,170 km.
- The North-East waypoint applies only when exactly one endpoint is North-East.
- Zone demand sums to the national volume (tolerance 1e-6).
- Every zone has exactly one assignment, and only to an open DC.
- Flow balance holds at every DC.
- The evaluator gives the same result whether called with the MILP solution or with a re-built assignment.
- The as-is network uses the same evaluator.
- k = 1 cost exceeds k = 4 cost.

---

## 12. Outputs and visual standards

| File | Content |
|---|---|
| `outputs/demand_map.html` | Zones sized by demand, coloured by layer mix; candidates; plants; single centre of gravity |
| `outputs/network_<scenario>.html` | Open DCs sized by throughput, assignment lines, 400 km rings, uncovered zones highlighted |
| `outputs/charts/cost_curve.png` | S2 stacked components by DC count, with the total line and the minimum marked |
| `outputs/charts/service_frontier.png` | S3 cost against α for each radius, with the knee annotated |
| `outputs/charts/as_is_vs_recommended.png` | Waterfall from as-is total to recommended total by component |
| `outputs/charts/tornado.png` | S9 |
| `outputs/charts/site_robustness.png` | R heatmap |
| `outputs/charts/rent_headroom.png` | S7 switching rent compared with current rent per recommended site |
| `outputs/scenario_summary.csv` | One row per scenario |

All monetary axes are in INR Cr per year. Every chart carries a source/assumption footnote and a "hypothetical client" note. Charts follow one palette and must be legible in greyscale.

---

## 13. Acceptance criteria per checkpoint

**Checkpoint A (after Phase 1, data).**
- National population is within 0.5% of 1,210.9 mn.
- No zero coordinates remain.
- About 158 zones; demand sums to 300,000 t; no zone above 5%.
- The top 10 zones are dominated by metros, not Bihar towns.
- The calibration table passes the 15% tolerance.
- The centre of gravity falls in central India; the prototype puts it at about 21.7°N, 79.0°E, just north of Nagpur.
- The demand map renders.

**Checkpoint B (after Phase 2, model).**
- The base case (400 km / 80%) solves to Optimal with a gap of 0.5% or less.
- MILP proxy versus evaluator is within 3%.
- Totals reproduce the section 3 table within about 5%, or any difference is explained.
- The as-is network evaluates at about INR 270 Cr.
- All tests pass.

**Checkpoint C (after Phase 3, scenarios).**
- All scenarios run with `python -m src.scenarios` in under 15 minutes.
- Infeasible combinations are reported explicitly.
- Every chart in section 12 exists.
- One paragraph of insight per scenario is drafted in `docs/scenario_insights.md`.

**Checkpoint D (after Phase 4, agent).**
- The five demo questions answer correctly in both live and offline modes.
- No number appears in a reply without a matching tool result; spot-check three.
- Out-of-range overrides are refused gracefully.

**Checkpoint E (after Phase 5, delivery).**
- The README reads as a case study.
- A two-page PDF exists.
- The demo GIF is under 10 MB.
- The repository is public, has no secrets in its history, and a clean clone runs.
- The disclaimer is present.

---

## 14. Case-study storyline (Phase 5)

The write-up follows a situation–complication–question–answer structure and reads like a steering-committee pre-read.

- **Situation.** A national FMCG brand serves India through 15 legacy state depots designed around pre-GST tax boundaries.
- **Complication.** GST removed the reason for that footprint, and costs and service now lag peers. Leadership needs to decide how many DCs to run, where, and which markets each serves.
- **Question.** Which network minimises landed cost while meeting a next-day service promise, and how robust is that answer?
- **Answer.** The recommended network: sites, cost, service, saving against today. This is followed by three supporting insights (the price of service, the robust core sites, and the rent headroom per site) and an honest limitations section: Census 2011 shares, a single aggregated product, haversine distances, hypothetical plants and as-is network, and the low-confidence rents named explicitly.

Close with "what we would do next on a real engagement": client shipment data, SKU-level demand, actual lane rates, a site visit for the swing locations, and C&W MarketBeat availability checks for the low-confidence clusters.

---

## 15. Phase plan and Claude Code prompts

Run each prompt in a fresh Claude Code session in the project folder, or in the same session after the checkpoint is passed.

**Phase 0: Setup (about 30 minutes)**
```
Read CLAUDE.md, PROJECT_BRIEF.md and docs/BUILD_SPEC_v2.md in full. Do Phase 0 only:
1. Install the project skills: copy every folder in tooling/claude-skills/ into
   .claude/skills/ (keep LICENSE and SOURCE.md files), then list .claude/skills/
   and confirm the seven skills are visible to you.
2. Load the scnd-python-standards and ponytail skills and follow them from here on.
3. Create a Python 3.11 venv outside OneDrive (C:\venvs\scnd) and pip install -r
   requirements.txt. Confirm pulp.listSolvers(onlyAvailable=True) includes
   PULP_CBC_CMD and ruff runs.
4. Git and GitHub (see CLAUDE.md, Git and GitHub workflow): check that git and
   gh are installed and gh is logged in (gh auth status). git init -b main and
   make an initial commit on main of the files that already exist
   ("chore: project brief, spec, assumptions and guidelines"). The .gitignore,
   pyproject.toml and .github/workflows/ci.yml already exist; do not rewrite
   them. Create the private remote and push main:
   gh repo create Shubham-Kakade/india-distribution-network-design --private
     --source . --remote origin --push
   Then create the branch phase-0-setup for the remaining steps.
5. Create the src/ package (with __init__.py) and tests/ skeleton from spec §11.
   Only create files that Phase 0 needs: src/config.py (load + validate
   data/assumptions.yaml, with_overrides helper, PROJECT_ROOT) and
   tests/test_config.py. No empty placeholder modules.
6. Download final_cities.csv, final_districts.csv and final_states.csv from
   github.com/recurze/IndianCities into data/raw/ and record the commit hash in
   docs/sources.md.
Then run the scnd-checkpoint skill and stop.
```

**Phase 1: Data and baseline analytics**
```
Start from an up-to-date main on a new branch phase-1-data.
Implement spec §4 and §5: src/geo.py, src/demand.py, src/data_prep.py and
src/cog.py, handling every defect in the §4.2 table explicitly (log each fix).
Produce data/processed/{zones,candidates,plants,dist_zone_dc,dist_plant_dc}.csv
and outputs/demand_map.html. Write tests for geo and demand conservation.
Print the Checkpoint A sanity report from spec §13. Do not start the
optimisation model. Stop and report.
```

**Phase 2: Cost engine and optimisation model**
```
Start from an up-to-date main on a new branch phase-2-model.
Implement spec §6, §7 and §8: src/costs.py (evaluate_network is the single
source of truth), src/model.py and src/baseline.py. Solve the base case
(400 km / 80%), the k = 1..12 sweep and the as-is network; print a table in
the format of spec §3 and compare it with the supervisor prototype numbers.
Report MILP-vs-evaluator gaps and solve times. Write the model invariant tests.
Stop at Checkpoint B.
```

**Phase 3: Scenarios and visuals**
```
Start from an up-to-date main on a new branch phase-3-scenarios.
Implement spec §9 and §12 in src/scenarios.py and src/viz.py so that
`python -m src.scenarios` reproduces every output from raw data. Draft
docs/scenario_insights.md with one paragraph per scenario stating the insight,
not just the numbers. Stop at Checkpoint C.
```

**Phase 4: Agentic layer**
```
Start from an up-to-date main on a new branch phase-4-agent.
Implement spec §10: src/agent_tools.py, src/agent.py, app/streamlit_app.py,
including guardrails, the cache and offline mode with a 20-scenario
pre-computed library. Run the five demo questions in both modes and save the
transcripts to docs/agent_demo_transcripts.md. Stop at Checkpoint D.
```

**Phase 5: Case study and publication**
```
Start from an up-to-date main on a new branch phase-5-delivery.
Write README.md as the case study following spec §14, export
docs/case_study.pdf (2 pages), add the disclaimer, record the demo GIF and
prepare the repository to go public: scan the full history for secrets
(git log -p | findstr /i "sk-ant api_key"), confirm the disclaimer is present.
Do not change visibility; the supervisor approves that after Checkpoint E.
Stop at Checkpoint E.
```

---

## 16. Interview defensibility: questions the project must answer

These are the questions an SCLA lead is likely to ask, with where the answer lives.

| Question | Where answered |
|---|---|
| Why this many DCs and not one more or one fewer? | S2 curve and S3 knee; the flat bottom explained |
| How did you model inventory? | Section 6: square-root law, with a proxy in the MILP and exact cost in evaluation |
| How would the answer change with real client data? | Limitations and next steps; tornado shows which inputs matter |
| Why not just use centre of gravity? | `cog.py` comparison: k-COG versus MILP on cost and service |
| Single or multi-sourcing, and why? | Single sourcing reflects distributor-level practice; multi-sourcing as an extension |
| How confident are you in the rent data? | Confidence column in the YAML; S7 headroom shows how much rent error each site tolerates |
| How does this compare with Coupa Supply Chain Modeler or Optilogic? | Same formulation class (MILP facility location); those tools add multi-period, multi-product and simulation |
| What does the agent add over a dashboard? | Turns a business question into the right model run and explains the trade-off; tool-grounded numbers |

---

## 17. Open items still to verify

1. Cluster rents for Lucknow, Indore, Jaipur, Rajpura, Patna, Kochi and Bhubaneswar are analyst estimates. A C&W or Knight Frank secondary-market note would upgrade them. The model works without them; the README flags them.
2. The Nagpur rent is from Knight Frank 2023. Refresh it if a 2025–26 figure surfaces.
3. Warehouse opex, handling, fixed cost per DC, storage density and stock-days are analyst benchmarks (low confidence). They are covered by the tornado.
4. Primary and secondary rates are derived from one marketplace's lane quotes, cross-checked against NCAER's 2025 averages. Optionally triangulate with two or three more lanes.
5. HCES state MPCE covers the 18 major states plus Chandigarh and Sikkim. Smaller states and UTs default to the All-India value.

---

## 18. Sources added in v2

- Knight Frank, India Warehousing Market Report 2025: city weighted-average rents (NCR 21.9, Pune 28.0, Mumbai 25.2, Kolkata 25.0), stock and vacancy, Guwahati cluster rents.
- Colliers India via Outlook Business, 18 May 2026: Farukh Nagar and NH-48 at INR 21–28 per sq ft per month (Q1 2026).
- Knight Frank via PTI/NewsDrum: Kolkata Dankuni at INR 18–25, NH-16 at 18–27 (Grade A); 2025 leasing 4.6 mn sq ft.
- GRI Institute, Indian Logistics & Warehousing Outlook H2 2026 (7 Aug 2026): Chakan–Talegaon at 22–35, Pune vacancy 3.2%, NCR at 18–25, Kolkata NH-16 at 17–26.
- Knight Frank IWMR 2023 via The Hitavada (14 Jun 2023): Nagpur MIHAN and MIDC at INR 194–237 per sq m per month.
- NCAER for DPIIT, *Assessment of Logistics Cost in India* (via ThePrint, 26 Sep 2025): road INR 3.78 per tonne-km; heavy truck 1.51; light truck 11.03.
- FR8 marketplace, Mumbai–Delhi lane rates (1,439 km): 32 ft MXL INR 92,000; 20–24 ft container INR 48,050.
- IISD Global Subsidies Initiative: fuel is about 55% of Indian trucking operating cost.
- CRISIL (Nov 2017): trucks average about 300–325 km per day after GST.
- MoSPI HCES 2023-24 press note (27 Dec 2024): state average MPCE, rural and urban.
- IBEF via Indian Retailer (Dec 2023): rural about 45% of FMCG revenue.
- Address Advisors (2026): add-on warehouse charges of about INR 10 per sq ft.
- Supervisor inspection of `recurze/IndianCities` (25 Oct 2026): the data defects in section 4.2.
- Supervisor environment test (25 Oct 2026): PuLP 4.2.0 ships no CBC; 3.3.2 does.
