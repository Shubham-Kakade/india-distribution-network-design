# CLAUDE.md: India Distribution Network Design

This file is loaded at the start of every Claude Code session in this folder. Read it fully before doing anything.

## What this project is

This is a portfolio project in supply-chain network design and network advisory. It decides how many distribution centres a hypothetical national FMCG brand should run in India, where, and which demand zones each serves, at minimum landed cost subject to a next-day service target. On top of the model sits a Claude tool-use agent that answers "what if" questions. The code will be read by reviewers, and the owner, Shubham, must be able to explain every line in an interview.

## Documents, in order of authority

1. `docs/BUILD_SPEC_v2.md` — the modelling and engineering contract. It wins over everything else.
2. `data/assumptions.yaml` — every parameter, with source and confidence. It is the only place numbers live.
3. `PROJECT_BRIEF.md` — purpose and definition of done.
4. `docs/DECISIONS.md` — modelling decisions taken during the build.
5. `docs/PROGRESS.md` — what has been done, phase by phase.

## How we work

- **Supervised, phase by phase.** Build only the phase you are asked for (spec §15). At the end of the phase, run the `scnd-checkpoint` skill and **stop**. A supervisor reviews each checkpoint before the next phase starts.
- **Ask, don't guess** when the spec is silent on something that changes results. Put the question in the checkpoint hand-back rather than inventing an assumption. Small engineering choices, such as a helper's name, are yours to make.
- **No silent deviations.** If you depart from the spec, say so in the hand-back and log it in `docs/DECISIONS.md`.

## Skills to use (committed in `.claude/skills/`)

| Skill | Use when |
|---|---|
| `scnd-python-standards` | **Before writing or changing any code.** Covers library-first lookup, when to make a function, naming with units, idioms and tests |
| `ponytail` | Every coding task: the smallest complete change; nothing speculative |
| `scnd-model-change` | Before touching `assumptions.yaml`, `demand.py`, `geo.py`, `costs.py`, `model.py` or scenario definitions |
| `systematic-debugging` | Any wrong number, failing test or surprise; root cause before fix |
| `verification-before-completion` | Before saying anything is done, fixed or passing |
| `ponytail-review` | Self-review of each phase's diff before the checkpoint |
| `scnd-checkpoint` | End of every phase |

## Non-negotiables

1. **Look before you write.** Search the repo, then the standard library, then the approved dependencies (listed in `scnd-python-standards`) before writing a new function. Adding a dependency needs a `docs/DECISIONS.md` entry.
2. **One cost engine.** All costs come from `src/costs.py::evaluate_network`.
3. **No magic numbers.** Parameters come from `assumptions.yaml` through `src/config.py`.
4. **Units in names:** `_km`, `_t`, `_t_yr`, `_inr`, `_cr`, `_sqft`, `_inr_tkm`, `_frac`.
5. **Functions** are for reuse, for named domain concepts, or for testability. They are not for shortening code or for imagined future needs.
6. **Vectorise** with numpy/pandas. No `iterrows` in `src/` on large tables, and no `print` in library code (use `logging`).
7. **Every formula and constraint cites its spec section** in a docstring or a one-line comment.
8. **Evidence before claims.** Show the actual `pytest` / `ruff` / run output.
9. **Never commit secrets.** The repo is public. The API key lives only in `.env`, which is git-ignored; never paste a key into code, tests, notebooks, logs or PR text.

## Git and GitHub workflow

- **Remote:** **public** GitHub repo `Shubham-Kakade/india-distribution-network-design` (public by owner decision, D-011). Every push is visible to anyone, so the pre-push safety check below is mandatory.
- **One branch per phase:** `phase-0-setup`, `phase-1-data`, `phase-2-model`, `phase-3-scenarios`, `phase-4-agent`, `phase-5-delivery`. Create the branch from an up-to-date `main` at the start of the phase. Never commit directly to `main` after Phase 0's initial commit.
- **Small commits within a phase**, each one a working state (tests and ruff green), using Conventional Commit messages: `feat(demand): two-layer state demand model`, `fix(geo): route NE pairs via Siliguri`, `test(costs): evaluator matches MILP`, `docs: update PROGRESS for checkpoint A`, `chore: pin pulp<4`. The subject stays under 72 characters, written in the imperative; the body says *why*.
- **At the checkpoint** (`scnd-checkpoint` skill): push the branch, open a pull request into `main` with `gh pr create`, using the hand-back report as the PR description, and stop. The supervisor reviews the PR.
- **After approval** (Shubham says "approved"): merge with `gh pr merge --merge --delete-branch`, tag `git tag phase-N && git push origin phase-N`, then pull `main`.
- **Before every push:** `git status` must show no `.env`, no data outside `data/raw` and `data/processed`, and no file over 5 MB. Run `git diff --cached --stat` and read it.
- Never force-push, rewrite published history, or change repo visibility without Shubham's explicit instruction.

## Where Claude Code runs

Sessions run either **locally** on Shubham's Windows laptop, or **in the cloud** at claude.ai/code (Linux VM; the repo is cloned from GitHub, and branches and PRs are pushed through the Claude GitHub App). The rules are the same in both places. In a cloud session, skip the Windows venv: dependencies come from the environment setup script (`pip install -r requirements.txt`), and paths are POSIX.

## Commands

```bash
# one-time, local Windows only (venv lives OUTSIDE OneDrive)
py -3.11 -m venv C:\venvs\scnd
C:\venvs\scnd\Scripts\activate
pip install -r requirements.txt

# daily
ruff format . && ruff check .
pytest -q                     # fast tests
pytest -q -m slow             # full-India smoke tests
python -m src.data_prep       # Phase 1 outputs + sanity report
python -m src.scenarios       # reproduces every result end to end
streamlit run app/streamlit_app.py
```

Run modules with `python -m src.<module>` from the project root, never `python src/<file>.py`. Imports are absolute: `from src.config import load_params`.

## Layout

```
src/        config, geo, demand, data_prep, costs, model, baseline, cog, scenarios, viz, agent_tools, agent
app/        streamlit_app.py
tests/      one test file per src module; tiny fixtures; slow full-India tests marked
data/raw/   untouched inputs (+ manual_fixes/)        data/processed/  generated, reproducible
outputs/    maps, charts, scenario JSON/CSV           docs/            spec, decisions, progress, case study
```

## Environment notes

- The machine is Windows and the folder is synced by OneDrive. Keep the venv and caches outside it, and use `pathlib` for every path.
- PuLP must be **< 4**; 4.x no longer bundles CBC. Check with `python -c "import pulp; print(pulp.listSolvers(onlyAvailable=True))"`, which should list `PULP_CBC_CMD`.
- Raw city data comes from GitHub `recurze/IndianCities`, which has known defects (spec §4.2). Never trust it without the checks.
