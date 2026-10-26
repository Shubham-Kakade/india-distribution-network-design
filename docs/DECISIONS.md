# Decision log

Modelling and engineering decisions, newest first. Each entry records the context, the decision, the alternatives rejected and the expected effect on results.

---

## 2026-10-26 — Phase 5 follow-up (plain answers, owner decision)

**D-052 Owner decision: no named hiring firm, job post or recruiter in the current files.**
- *Decision (Shubham).* Remove every reference to the consultancy, its practice name, the job post and the recruiter from all current files. Git history is not rewritten and nothing is force-pushed.
- *Disclaimer.* One text, everywhere: "Independent portfolio project. The client and network are hypothetical; not affiliated with or endorsed by any company named in the sources." It lives in `meta.disclaimer` in `assumptions.yaml`. Charts and maps read it from there, and so do the README, the case study and the app footer.
- *Wording.* The project's purpose is described as a portfolio project in supply-chain network design and network advisory, in `PROJECT_BRIEF.md`, `CLAUDE.md` and the spec. The angle named after the firm became "the real-estate angle".
- *Sources and claims removed.* From `docs/sources.md`: the job post and three of the firm's market reports (India logistics and industrial leasing H1 2026, and its Pune and Mumbai market notes). From `PROJECT_BRIEF.md`: the market-context paragraph, which relied only on that report (record 36.2 mn sq ft gross leasing in the top 8 cities, +18% YoY; NCR 8.7, Chennai 6.1, Pune 5.9, Mumbai 4.7, Bengaluru 4.4 mn sq ft; 3PLs 34% of occupiers). No model input relied only on those sources: the Pune rent cites GRI Institute and Savills.
- *Effect on results.* None. The disclaimer text changes the sha of `assumptions.yaml`, so every scenario was re-run. All 83 scenario JSON files and the summary CSV are identical apart from `assumptions_sha256` and solve times. The six charts and six maps changed only in the disclaimer footnote. The two agent-made diesel ids change suffix (it hashes the assumptions file).

**D-053 Plain-English answers first; the six-part analysis behind "Show details".**
- *Why.* The D-049 answers are written for an analyst. A business manager needs the answer, what changes, why and what to do, in plain words.
- *The plain answer* (`src/agent_plain.py`) has four bold-labelled parts in order: In short, What changes, Why it costs more (or less), What to do. One italic line follows with the main limitation and the Source ids. An `explain_network` answer uses "Why it costs this much", since there is no before and after.
- *Limits.* About 120 words and five numbers. The 20 library answers run 81 to 118 words with 2 to 6 numbers. Numbers are rounded for reading ("about 80%", "about 17%", "about INR 2.9 Cr"). The grounding check already accepts these roundings and still rejects invented numbers (tested).
- *Vocabulary.* warehouse (not DC), market area (not zone), trucking from factories to warehouses (primary freight), delivery trucking (secondary freight), share of customers who get next-day delivery, cost of holding stock, running cost per warehouse, distance trucks drive (tonne-km). Places are named by city ("the Bengaluru warehouse (Hosur)"), and there are no ids except on the Source line.
- *Live.* The prompt and both worked examples ask for the plain answer, then a line `#### Details`, then the six parts. The structure check covers both layers. A reply that fails twice is templated as plain (first result) plus details (all results).
- *Offline and the app.* `Reply.text` is the plain answer and `Reply.details` the six parts, shown under `st.expander("Show details")`.
- *Rejected.* Asking the LLM to simplify the six-part answer itself. The plain layer would then not be testable offline, and its numbers would drift from the details.

**D-054 Display names, headline rules, and a reproducible library.**
- *Display names.* Zone anchors that are municipal bodies or official compound names (BBMP, DMC, GHMC, GVMC, Greater Mumbai, Haora, Ahmadabad, Nanded Waghala, Sangli Miraj Kupwad, Bhiwandi Nizampur) are mapped to the names readers know. The mapping lives in one place, `agent_tools.ZONE_DISPLAY_NAMES`, and only tool output uses it. Zone ids and the data are unchanged.
- *Headlines.* A headline never starts with a scenario id: the subject is named ("The best 4-warehouse network", "The network built for 85.1% next-day service"), and ids appear only on the Source line. Equal before-and-after values read "unchanged at X", not "X against X".
- *Library.* `outputs/agent_library.json` now stores agent-made records sorted by id and without solver wall-clock times. A rebuild is byte-identical whether the result cache is cold or warm (checked with two cold builds and one warm build). The answers never used solve times.

---

## 2026-10-26 — Phase 5 follow-up (agent answers)

**D-049 Answers are explanatory and follow one six-part structure, live and offline.**
- *The parts.* Every answer, live, offline or templated, has six bold-labelled parts:
  1. a one-sentence headline with the cost and service impact;
  2. what happens in the network: sites opened, closed or swapped, zones re-assigned and to which DC, and zones and demand share losing next-day;
  3. why: the two or three cost components that move most against the recommended network, each with its mechanism;
  4. what it means for the client;
  5. assumptions and limits;
  6. the source scenario ids.
- *Length.* About 180 words; the 20 library answers run 132 to 219 words including the labels and ids.
- *Tool fields.* The tool results now carry everything the explanation needs, computed in `agent_tools.py`, never in the agent:
  - the top cost drivers (components with a move of at least 0.05 Cr, largest first);
  - sites opened and closed, with names;
  - zones that change DC and their destinations;
  - zones and demand share losing or gaining next-day, on base demand and distances, except for S0, whose depots share no sites with the candidates;
  - the recommended network's next-day share;
  - the freight multiplier and diesel share for diesel runs;
  - cost shares for `explain_network`.

  The library change is purely additive: no existing value changed, and it rebuilds byte-identically.
- *Static text.* The "what it means" and limits lines are written per library question, consistent with `docs/scenario_insights.md`, and carry no digits. Every number therefore comes from a tool result, and all 20 answers pass the grounding check.
- *Mechanisms.* The mechanism phrases are true whatever the cause: "more tonne-km on inbound lanes", not "longer lanes", since growth also raises tonne-km. A diesel shock states its own mechanism: the rate per tonne-km rises on the same lanes.

**D-050 The live guardrail also checks the structure; the prompt carries two worked examples.** The grounding check is unchanged (D-041). A reply that fails it or leaves out any of the six labels is sent back once, naming the offending numbers and the missing parts; if it fails again, the answer is templated from the tool results by the same six-part writer. The system prompt requires the structure and plain business English, allows only numbers from tool results, and points to `explain_network` and `compare_scenarios` for more detail. It ends with two worked examples, the Hosur one-month outage and the +20% diesel shock. They are generated at start-up from the library records by the offline writer, so they always match the data and pass grounding (tested).

**D-051 Provider calls retry before falling back to offline.**
- *What retries.* HTTP 429, 500, 502, 503 and 504 are retried up to twice, waiting 2 s and then 5 s. A numeric `Retry-After` header replaces the wait, capped at 10 s; an HTTP-date value falls back to the backoff.
- *What doesn't.* 400, 401, 403 and 404 are not retried, because the request or the key is wrong and a retry cannot help. Connection errors and timeouts are not retried either; they fall back at once.
- *The SDK's own retries are off* (`max_retries=0`), so this is the only retry policy.
- *The fallback notice* keeps the error class and adds the HTTP status, and the whole notice is redacted (D-045).

---

## 2026-10-26 — Phase 5 (delivery)

**D-044 Tests run CBC serially; India runs keep `threads: 1`.** Root cause of the occasional 10 s test: with `-threads 1`, CBC starts its threaded branch-and-bound with one worker. When the root node solves the MIP (as every tiny fixture does), the worker is never used, and CBC sometimes waits 10 s on a timed wait before exiting. Its log reads "Thread 0 used 0 times, waiting to start 10.000255". In 80 identical tiny solves this happened 2 to 4 times. The test `params` fixture now sets `solver.threads` to 0 (CBC's serial code, still deterministic), and `pytest -q` falls from about 25 s to about 5 s. Serial CBC was also tried for the India runs. It cut the full run from 656 s to 466 s and left the base case and as-is figures unchanged, but 15 scenarios moved within the 0.5% MIP gap (by up to ±0.33 Cr), including the 400 km / 85% site set behind the staging finding. So production keeps D-021's setting, and every committed output is unchanged.

**D-045 Bring-your-own-key live mode (owner requirement).** The public app must never use the owner's key.
- *The key.* A visitor's key lives only in `st.session_state`. It is never written to disk, logs, the result cache, cache keys, error text, transcripts or the URL; the config repr omits it, and the password field is cleared once the key is in use. Provider errors are shown with the key and anything key-like (`AIza…`, `sk-…`, `gsk_…`, `Bearer …`) redacted.
- *Public mode.* `PUBLIC_DEMO=1`, set only in the hosting platform's settings, ignores `LLM_*` variables and `.env` entirely and hides Local Ollama. It also only calls `https` endpoints on public hosts. Without that, a visitor could point the server at localhost, a private network or a cloud metadata address.
- *Local use.* Without `PUBLIC_DEMO`, `.env` and environment keys work as before, and the sidebar names the active source ("your .env" or "key entered here"), never the key.
- *No key* means offline mode.
- *Code.* `src/llm_settings.py` holds the settings logic and `LLMConfig` (moved from `agent.py`); the app only wires it to widgets.

**D-046 Hosting on Streamlit Community Cloud.** The app runs from `app/streamlit_app.py` with `requirements.txt` only. At start-up it reads committed files (`data/processed/`, `outputs/scenarios/`, `outputs/agent_library.json`) and rebuilds nothing. From a clean clone in public mode the first page rendered in 4.1 s and the app wrote no files. PuLP 3.3.2 (pinned below 4) bundles CBC for Linux x86-64 and arm64, so no system packages are needed. `.streamlit/config.toml` sets the theme (the charts' blue) and turns usage statistics off. Deployment adds only the secret `PUBLIC_DEMO = "1"` and no API key; Streamlit exposes root-level secrets as environment variables.

**D-047 Local setup scripts.**
- `scripts/setup_local.sh` (macOS/Linux) creates a venv (default `.venv/`, path configurable).
- `scripts/setup_local.ps1` (Windows) creates one outside OneDrive by default (`C:\venvs\scnd`, `-VenvPath` to change) and warns if the path is inside OneDrive.

Both install `requirements.txt`, check that CBC is available, and copy `.env.example` to `.env` only if `.env` does not exist, so `LLM_API_KEY` is left empty. The shell script was run twice on a fresh clone: the second run left `.env` untouched. The PowerShell script could not be run here (no PowerShell in the Linux container). `.env.example` holds placeholders only, with Gemini as the default preset (`gemini-3.8-flash`, editable), an empty key, and a note that Gemini keys must be AI Studio keys.

**D-048 Case-study PDF tooling stays out of requirements.** `docs/case_study.pdf` (two A4 pages) is rendered from `docs/case_study.md` by the one-off `scripts/build_case_study_pdf.py`. The script converts the Markdown with the `markdown` package and prints the HTML to PDF with the Chromium that Playwright installs. Neither tool is needed to run the model or the app, so neither is in `requirements.txt`; the script's docstring says to `pip install markdown` first. Every number in the README and the case study was checked with the agent's own grounding function against the scenario records, the summary CSV, the insights and `data/processed/zones.csv`.

---

## 2026-10-26 — Phase 4 (agent)

**D-039 The agent uses an OpenAI-compatible endpoint, not the Anthropic API (owner decision).** The agent talks to any OpenAI-compatible chat-completions endpoint with tool calling, through the `openai` Python SDK. `openai` replaces `anthropic` in `requirements.txt`. Configuration comes only from `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` (environment variables, or a git-ignored `.env`). `.env.example` holds placeholder presets for Gemini, Groq and a local Ollama model (`qwen2.5:7b`). In a claude.ai/code cloud session the key is a network secret that the proxy attaches to requests to the provider's host, so `LLM_API_KEY` is the placeholder `proxy-injected` and the code never sees a key. With `LLM_BASE_URL` or `LLM_API_KEY` unset, the agent runs offline. Spec §10 "Stack" is amended to match, and the approved-dependency table in `scnd-python-standards` now names `openai`. *Why:* any provider (including a free tier or a local model) can run the demo, and the repository stays provider-neutral.

**D-040 Agent tools: where §10 is silent or adjusted.**
- *A seventh tool, `rank_assumptions`.* Demo question 5 ("the agent calls the tornado results") needs the S9 tornado, and none of the six §10 tools reads a table. The tool returns the S9 rows widest first, with the base total, DC count and saving. The spec §10 tool table gains the row.
- *`explain_network` gives each site's share of volume, not its share of cost.* The evaluator costs the network as a whole (one cost engine, §6); splitting cost by site would mean a second cost calculation. Throughput comes from the record's plant flows (exact for any scenario); per-site next-day shares use the base distances and demand, and the network total is the evaluator's figure.
- *What `run_scenario` may override.* The 14 ranged YAML parameters, the service target (range = the radii and targets swept in S3) and `diesel_shock_frac` (range = the S6 shocks, applied exactly as S6 does). An override may go at most 2x the range width beyond the range (spec §10). In addition, a non-negative range stays non-negative and a fraction stays at most 1. Free solves use the two-pass rule (D-034); demand, volume and circuity overrides rebuild the data as S9 does.
- *`simulate_disruption` reuses S5.* "Operational" is the S5a logic (open set fixed, 20% surge, freight only, months/12, D-029) for any recommended site and 0–12 months; "strategic" is the S5b logic. Each result also reports where the closed site's zones went.
- *Agent-made scenarios* get ids starting `AG_` (`AG_outage_BLR_HSR_1m`, `AG_loss_BLR_HSR`, `AG_<name>_<hash>`). Their full records are cached as JSON in `outputs/scenario_cache/` (git-ignored, spec §11), keyed by a sha256 of the tool, its validated arguments and `assumptions.yaml`, so a changed YAML never serves a stale result.
- *Two modules instead of one.* `agent.py` holds the live loop and the guardrails; `agent_offline.py` holds the deterministic answers and the 20-question library (`outputs/agent_library.json`, built by `python -m src.agent_offline`). The templated fallback and the offline answers are the same code, so both are grounded by construction.
- *Offline intent matching* is a fixed list of regex patterns, most specific first. A follow-up without a site ("and if we lost it permanently?") uses the site named in the previous question. Disruptions are pre-computed for Hosur, NCR and Mumbai (the two busiest sites and the demo site); other questions get the list of answerable questions.

**D-041 The grounding check.** A number in a reply is grounded if some number in any tool result of the conversation rounds to it at the reply's own precision. The tool number may be a fraction shown as a percentage (0.8012 → 80.1%), may have lost its sign ("falls by 33.1" for −33.1), and a round number with trailing zeros matches at its own magnitude (48,000 for 48,013). Numbers inside identifiers (`S3_400km_80`, `Z001`) and list markers are not figures. Tool results are rounded to 4 dp, so a reply rounded again to 1 dp cannot drift through double rounding. A failing reply is sent back once, naming the numbers; a second failure returns the templated answer. A reply that cites none of its scenario ids gets them appended. Provider errors (rate limit after the SDK's backoff retries, 5xx, 401/403), unknown tools and arguments that are not a JSON object fall back to the offline library with a visible notice. A tool's own refusal (an out-of-range override) is not an error: it goes back to the model to explain.

**D-042 scenarios.py pieces made reusable for the agent (no behaviour change).** `operational_outage` and `permanent_loss` (from S5), `diesel_overrides` (from S6) and `rebuild_data` (from S9). Re-solving the recommended network, S5a, S5b, S6 at 20% and 40%, and two tornado ends (circuity low, rest-of-state share low) matched the committed JSON exactly.

**D-043 The live demo is verified in Phase 5 on a local machine (supervisor decision).** In the cloud session the Gemini key is a network secret the proxy should attach, but three connectivity checks failed: HTTP 500 `INTERNAL`; then 403 `API_KEY_SERVICE_BLOCKED` (the standard key's API restrictions); then, with an AI Studio key, 400 "Missing or invalid Authorization header" (the secret was not being injected). Phase 4 is therefore approved on offline mode and the mocked-client tests. The live demo (the five §10 questions, the spot check of live numbers, and any grounding retry or template fallback) moves to Phase 5. It will run on Shubham's laptop against Gemini's OpenAI-compatible endpoint, with the key in a git-ignored `.env` (D-039). No code changes: the agent already reads `.env` through `python-dotenv`.

---

## 2026-10-25 — Phase 3 (scenarios)

**D-027 The proxy fidelity limit applies to sweep runs only (supervisor decision).** The 3% limit binds where `k_ref = k` (the DC-count sweep and other fixed-k solves). Free runs size the proxy at `k_ref = 6` and report their gap as information, not pass/fail: the proxy only guides the search, and the reported cost is always the exact evaluator figure. The self-consistent re-solve was rejected because it found a worse exact base network (244.4 vs 244.1). `model.py` warns only when k is fixed. *Superseded in part by D-034:* free runs now also try the re-sized proxy, and the lower exact cost is kept, so the base case keeps the 244.1 network either way (on the single-thread solver the re-sized pass gives 244.16; the 244.4 above came from the earlier four-thread runs).

**D-028 The recommended network is the cheapest network at service comparable to today's; higher targets are priced upgrade options (rewritten after the Checkpoint C review).** Rule: on the base-radius (400 km) frontier, take the highest target that the as-is network already meets (today's network is at 81.4% next-day, so 80%), and recommend the cheapest network at that target. Every feasible target above it is reported as an upgrade option, with its extra cost, extra service points, extra DCs, and the sites added and dropped against the recommendation (`outputs/scenarios/S3_upgrade_options.json`). The "Kneedle" knee (the point furthest below the line joining the frontier's ends, both axes scaled to 0–1) is still computed and reported openly, but it does not decide. *Why:* a knee rule lets small cost noise pick the service level, and service policy is the client's choice. This rule asks the like-for-like question (what does today's service cost on the best network?) and prices each step beyond it. S4–S9 and R stay built around the recommended network. *Superseded:* the first version of D-028, which picked the Kneedle knee (80% under the single-pass proxy, 85% once two-pass solves fixed the 85% cell, D-034).

**D-029 S5a operational outage: freight only, open set fixed, surge as larger capacity.** The busiest recommended DC is closed for `disruption_months`. The other DCs stay open, with no new sites (`forced_open` with k = n − 1). Its zones are re-assigned with no service target, and the 20% surge raises every DC's capacity by raising `max_dc_size_sqft` by 20% for that solve. The outage cost is the change in primary plus secondary freight × months/12. Rent, fixed cost and stock are treated as unchanged for a one-month outage (the closed site still pays rent), so the evaluator's lower fixed and space cost for the smaller network is not counted as a saving. At 300,000 t no DC comes near capacity, so the surge never binds (see insights). S5b re-optimises with the site excluded and the service target kept.

**D-030 R classifies sites on the stress tests of the recommended network only.** No-regret core: open in the recommended network and in every S4, S6, S7 and S8 run at its service target. Swing: open in some of them. The heatmap also shows S1, every feasible S3 cell and S5b as context columns that do not classify: S1 and S3 ask for different service levels, and S5b removes a site by design (counting it made NCR a "swing" site purely by construction). S5a is left out because its open set is fixed.

**D-031 S8 plant footprints are analyst assumptions.** *No Puducherry:* the remaining shares are renormalised to 0.5333 / 0.4667; without this, plant capacity (share × demand × 1.15) covers only 86% of demand and the model is infeasible. *Eastern plant:* Uluberia (Howrah), an existing FMCG cluster near the Bihar, West Bengal and Odisha demand, with a 20% share; the other three plants scale ×0.8. Both lists are in `scenarios.plant_footprints`.

**D-032 Scenario conventions where §9 is silent.**
- (a) S4–S9 and R run at the recommended service target, so each one stress-tests the recommendation.
- (b) S4 growth applies by the zone's anchor state, using the region lists in `scenarios.demand_growth.regions`. Revenue scales with volume at the same realisation, so the share of revenue stays comparable.
- (c) S6 multiplies both freight rates by (1 + 0.55 × shock) through parameter overrides; the evaluator has no fuel multiplier of its own (D-023).
- (d) S7 switching rents move one site's rent at a time, with the others fixed. Bisection between 1× and 3× today's rent, to INR 0.25; NaN means the site is still open at 3×. The search assumes a site, once dropped, stays dropped at higher rents.
- (e) The S9 tornado covers the 14 low/medium-confidence parameters with a range. Candidate rents are covered by S7, not here. Demand parameters rebuild zone demand from the cleaned raw data (the zone set is checked unchanged), and circuity rebuilds the distances. Each end also re-costs the as-is network, so the saving's sensitivity shows. The diesel share has no effect without a fuel shock, and its zero bar says so.
- (f) Scenario JSON records carry the overrides, the data changes and the SHA-256 of `assumptions.yaml`, not a full copy of the parameters.
- (g) Network maps are drawn for S0, S1, the recommended network, S5a and S5b. Next-day rings use the road radius ÷ circuity as a great-circle radius.

**D-033 The k-COG comparison builds a real network from each set of centres.** The k-weighted centres of gravity use a deterministic k-means++ seed, nearest-centre assignment and a Weiszfeld centre per cluster. Each centre then snaps to the nearest candidate whose metro group is still free (heaviest cluster first). Every zone goes to its nearest chosen site, and plant flows come from the MILP with that network pinned. The result is costed by the same evaluator as the MILP at the same k. The seeding replaced "k heaviest points" after a test showed two seeds landing in one cluster.

**D-034 Every free solve is two-pass; the lower EXACT cost is kept (supervisor decision, Checkpoint C).** `build_and_solve` with no fixed k solves once with the safety-stock proxy sized for `k_ref = 6`. It then re-solves with `k_ref = k*`, the number of DCs the first pass opened, and keeps the solution with the lower exact `evaluate_network` cost (on a tie, the first). Both passes are recorded in `Solution.passes` and in each scenario JSON (`solve.passes`). Fixed-k solves stay single-pass with `k_ref = k`. *Why:* a mis-sized proxy chose a costlier network at 400 km / 85% (250.1 Cr with 10 DCs, against 248.3 Cr with 11), and a proxy that can choose a costlier network must not decide the frontier. Taking the lower exact cost can only improve a reported network, so the base case stays at 244.1 Cr (pass 1: 244.08; pass 2: 244.16). This applies to every free solve: S1, S3, S4–S9, S5b and the S7 bisection.

**D-035 The scenario code is split by job (supervisor request, Checkpoint C).**
- `scenarios.py` holds the `Run` record, the scenario definitions and the run loop.
- `robustness.py` holds the pure "how robust is the answer" functions: the knee, the comparable-service rule, upgrade pricing, R classification and the k-COG network.
- `reporting.py` holds the JSON and CSV records, the charts and maps, and the printed report.

The split changed no behaviour: a full re-run matched the pre-split outputs file for file (JSON and summary CSV without solve times, PNG charts byte for byte, HTML maps with folium's random ids masked).

**D-036 Supervisor answers at Checkpoint C.**
- The S8 footprints (D-031) are accepted. Renormalising after removing Puducherry answers "where does the volume come from", not a capacity shortfall. Both footprints stay labelled as analyst assumptions.
- The S5a costing (D-029) is accepted as the correct one-month view. The write-up states that lost sales and stock stranded in the closed DC are not costed, so the outage cost is a floor and the service drop is the headline.
- The phase tags are created on GitHub by the owner.

**D-037 The S7 site searches run in parallel.** Two-pass free solves took the full run to 1,030 s, past the 15-minute limit (spec §14). Model building is not the bottleneck; CBC is, and the S7 rent bisection (one search per recommended site, each about 7 free solves) took about 575 s. Each site's search is independent, so `rent_switching_points` runs them in a process pool (`concurrent.futures`, standard library, no new dependency). The pool uses the "spawn" start method because Python 3.12 warns about forking a process that holds threads. Each solve stays single-threaded (D-021), so results do not depend on the worker count. The full run fell to 635 s, and its outputs matched the serial run file for file (same comparison as D-035).

**D-038 A staging run toward the first upgrade option.** The 85% upgrade network does not contain the whole 80% network: it adds Guwahati, Nagpur and Rajpura and drops Pithampur (Indore). `s3_staging` re-solves the recommended 80% target with the sites that the next upgrade drops closed (`forced_closed`). It records the extra cost and whether the result is nested in the upgrade network. Result: Nagpur replaces Indore at the 80% target for +INR 0.33 Cr a year (244.4 Cr), and the 85% upgrade then only adds Guwahati and Rajpura. The run is reported with S3 (`S3_400km_80_staged`); it is not part of R and does not change the recommendation. Indore stays recommended as the cheapest site at 80%; the staged network is the option to take if the client already expects to buy the 85% upgrade.

---

## 2026-10-25 — Phase 2 (model)

**D-019 Supervisor answers to the Checkpoint A questions.** The Bihar zones stay as they are. That only 4 Bihar cities anchor zones of 18–36 mn people each is a stated limitation ("lumpy rural zones"), to be named in the case study. The DNH & DD zone stays.

**D-020 As-is depots carry `state` and `metro_group` in the YAML; Ludhiana takes the default rent.** `state` serves North-East routing, as D-013 did for candidates. `metro_group` makes "same metro" in the §8 rent rule explicit. Each depot takes the nearest candidate in its group, less the 20% Grade B discount, which gives Bhiwandi 20.0, Kundli 19.2, Hyderabad 19.2 (Shamshabad is nearer than Medchal) and Bengaluru 20.8 (Hoskote). Ludhiana has no candidate in its metro, so it uses the new `as_is_depots.default_rent` of 17, taken as the final Grade B rent with no further discount (the literal reading of the YAML note). *Rejected:* a distance threshold for "same metro" (another magic number).

**D-021 CBC runs single-threaded (`solver.threads: 1`).** With 4 threads, repeated base-case solves returned different assignments within the 0.5% gap: the same 9 sites, but primary and secondary freight moved by about 0.1 Cr. Spec §11 requires deterministic results, and the case study's numbers must reproduce exactly. With 1 thread, repeat runs are identical, the base case reaches a 0.03% gap in about 2.5 s, and the whole Phase 2 run takes 34 s. Spec §7 is amended. *Rejected:* keeping 4 threads and rounding the reports (hides rather than removes the variation).

**D-022 The safety-stock proxy also charges the space safety stock occupies.** With the §7 v2 proxy (carrying cost only), the MILP objective sat 3.6–7.2% below the evaluator, outside the 3% fidelity limit. The missing term is the safety stock's floor space: at k = 4 the gap of 9.2 Cr equals the evaluator's safety-stock space cost of 9.3 Cr. The proxy is now `SS_ref × (carrying cost + area per tonne × (rent_j + opex) × 12)`, which is site-specific and still linear in y. Gaps fell to at most 1.2% in the sweep and 1.8% for the as-is network. The remaining negative gap at high k is the 50,000 sq ft minimum size, which a linear proxy cannot see. Spec §7 is amended.

**D-023 The MILP objective omits network-independent constants; the fidelity check adds them back.** Cycle-stock carrying cost (`i · v · cycle_days/365 · D_total`, 9.66 Cr) is the same for every network, so §7 leaves it out of the objective. The proxy-vs-evaluator comparison adds it back before comparing. Handling is constant too, but stays in the objective as §7 writes it. The evaluator applies no fuel multiplier; scenario S6 will scale the freight rates through overrides (§9).

**D-024 As-is plant flows come from the same MILP with the network pinned.** §8 asks for "a small LP" for plant-to-depot flows. `baseline.solve_as_is` calls `build_and_solve` with every depot forced open and every zone fixed to its state depot, which leaves only the flows free, so the as-is network passes through the same constraints (plant capacity, flow balance) and the same evaluator. The service target is switched off for this run, because today's network is evaluated, not constrained. This needed `fixed_assignment`, so the full §11 `build_and_solve` signature is built now.

**D-025 Processed tables load into a frozen `NetworkData` bundle.** `data_prep.load_network_data()` validates the columns of the five Phase 1 CSVs and returns zones, DC sites, plants, and wide zone-DC and plant-DC distance tables. The as-is network uses the same structure, with depots as the DC sites. Engineering only.

**D-026 `meta.crore` written as 10000000.** PyYAML reads `1.0e7` (an exponent without a sign) as the string `"1.0e7"`. Nothing used it before Phase 2. A regression test now checks that it loads as a number. No value change.

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
