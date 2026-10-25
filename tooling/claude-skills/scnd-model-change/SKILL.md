---
name: scnd-model-change
description: Workflow for changing anything that affects the numbers in the India network model — assumptions.yaml, the demand model, distances, the cost evaluator (costs.py), the MILP (model.py) or scenario definitions. Use before editing those files so results stay consistent, traceable and reproducible.
---

# Changing the model safely

A network study is only as credible as the traceability of its numbers. Every change to how a number is produced follows this workflow.

## The three invariants

1. **One cost engine.** `costs.evaluate_network()` is the only place a cost is computed. The MILP objective is a linear proxy of it; the as-is baseline, every scenario and every agent answer report the evaluator's numbers. Never compute a cost component anywhere else, including in charts or the agent.
2. **One source of parameters.** Every number lives in `data/assumptions.yaml` with `value`, `unit`, `source`, `confidence` and (if uncertain) `range`. Code reads it through `config.py`. A number in code is a defect.
3. **One command reproduces everything.** `python src/scenarios.py` rebuilds processed data, solves every scenario and regenerates every output from `data/raw/` plus the YAML.

## Workflow

1. **State the change and why** in one or two sentences. If it changes a modelling choice (not just a bug fix), add a dated entry to `docs/DECISIONS.md`: context, decision, alternatives rejected, expected effect on results.
2. **Capture the before.** Run the base case and save the headline row (sites, total INR Cr, each component, service share) from `outputs/scenario_summary.csv` or a quick solve.
3. **Change the parameter in YAML** (with source and confidence) or **change the code**, keeping the spec in step: if the formula or constraint changes, update `docs/BUILD_SPEC_v2.md` in the same change.
4. **Keep the proxy and the evaluator aligned.** If you change a cost formula in `costs.py`, check whether the MILP proxy term in `model.py` needs the same change. Re-run the proxy-fidelity check (gap ≤ 3%).
5. **Run tests and the base case.** `pytest -q`, `ruff check .`, then the base solve.
6. **Explain the delta.** Compare before and after. Every movement in total cost or the site set must have a one-line explanation that follows from the change. An unexplained movement means a bug until proven otherwise; use `systematic-debugging`.
7. **Record it.** Append to `docs/PROGRESS.md`: date, change, before → after headline numbers, explanation.

## Red flags — stop and investigate

- Demand total ≠ `company.annual_volume_tonnes` after any demand change.
- Total logistics cost outside 3.5–5.5% of revenue.
- A site set that changes when only a cost *level* changed uniformly (e.g. all rents ×1.1 flips three sites): check for a units error.
- MILP objective and evaluator differ by more than 3%.
- A scenario that was feasible becomes infeasible, or the reverse, without a service or candidate change.
- Solve time jumps by more than 10× (usually a formulation mistake, such as dense big-M constraints).

## Sanity anchors (from the supervisor prototype, spec §3)

Use these only to catch gross errors; small differences are expected.

| Check | Expected |
|---|---|
| Base case 400 km / 80% | about 9 DCs, about INR 244 Cr per year |
| Cost-only optimum | about 4 DCs, about INR 231 Cr per year |
| As-is 15 depots | about INR 273 Cr per year, about 81% next-day |
| Single DC | above INR 450 Cr per year |
| Demand centre of gravity | about 21.7°N, 79.0°E |
