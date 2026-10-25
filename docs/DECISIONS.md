# Decision log

Modelling and engineering decisions, newest first. Each entry records the context, the decision, the alternatives rejected and the expected effect on results.

---

## 2026-10-25 — Supervisor pre-build decisions (spec v2)

**D-001 Service base case at 400 km / 80%.** Indian trucks average about 300–325 km/day (CRISIL), so the brief's 500 km overstates next-day reach. The prototype showed 90% at 400 km needs 12 DCs. The base is 80%; the final recommendation is picked from the S3 frontier. *Rejected:* 500 km / 90% (optimistic transit).

**D-002 Two-echelon model with hypothetical plants.** Haridwar, Silvassa and Puducherry were added so primary freight shapes DC location. *Rejected:* DC-to-zone only (biases towards many DCs near demand).

**D-003 Inventory via the square-root law, evaluated exactly after the solve.** The MILP uses a linear safety-stock proxy per open DC; the evaluator applies SS_j ∝ √D_j. *Rejected:* a piecewise-linear √ in the MILP (adds binaries for little gain at this scale).

**D-004 Demand from state totals plus MPCE index.** The city-only data misses about 55% of FMCG demand, and headcount alone over-weights Bihar and UP. *Rejected:* district-level nodes (double-counted populations, 70 districts without coordinates).

**D-005 PuLP pinned below 4.** PuLP 4.2.0 ships no CBC binary; 3.3.2 does (tested 25 Oct 2026). *Rejected:* HiGHS via `highspy` (works, but adds a dependency and departs from the brief's CBC).

**D-007 GitHub workflow: one branch and one pull request per phase.** Each phase is built on its own branch, pushed at the checkpoint and opened as a PR into `main`. GitHub Actions runs ruff and pytest on every push. The supervisor reviews the PR, and Shubham merges and tags `phase-N`. The repo stays private until Phase 5. *Rejected:* committing straight to `main` (no review point, messier history to show recruiters).

**D-006 Code-quality skills vendored into `.claude/skills/`.** Ponytail (minimal change, review) and obra/superpowers (systematic debugging, verification before completion), both MIT, plus three project skills. Vendoring was preferred over installing the plugins because it pins behaviour and needs no Node hooks on Windows.
