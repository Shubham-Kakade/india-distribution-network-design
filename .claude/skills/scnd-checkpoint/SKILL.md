---
name: scnd-checkpoint
description: End-of-phase procedure for the India network design build — verify, self-review, log progress and stop for supervisor review. Use when a phase in docs/BUILD_SPEC_v2.md §15 is finished, or when about to say a phase or task is done.
---

# Phase checkpoint

The build is supervised. Each phase ends here, and no work on the next phase starts until the supervisor has reviewed it.

## 1. Verify with evidence

Run each command and keep its actual output (see `verification-before-completion`):

```
ruff format --check .
ruff check .
pytest -q
python -m src.<phase entry point>        # e.g. src.data_prep, src.model, src.scenarios
```

All four must pass. If one fails, fix it or report it as failing. Never describe a phase as done with a red check.

## 2. Check against the acceptance criteria

Open `docs/BUILD_SPEC_v2.md` §13 and go through the criteria for this checkpoint one by one. Mark each one **met**, **not met** or **partly met**, with the number or file that proves it.

## 3. Self-review the diff

Run the `ponytail-review` skill on everything changed in this phase and fix every **Must fix** finding. Then walk the checklist in `scnd-python-standards` §8.

## 4. Log, commit, push and open the pull request

- Append a dated entry to `docs/PROGRESS.md`: phase, what was built, headline numbers, deviations from the spec and why, open issues.
- Add any modelling choices to `docs/DECISIONS.md`.
- Commit the log updates: `docs: progress log for checkpoint <X>`.
- Pre-push safety check: run `git status` and `git diff main --stat`. Confirm there is no `.env`, no secrets, no file over 5 MB, and nothing outside the expected paths.
- Push the phase branch: `git push -u origin phase-<N>-<name>`.
- Open the pull request: `gh pr create --base main --title "Phase <N>: <summary>" --body-file <hand-back.md>`, where the body is the hand-back report from step 5. Wait for the CI check (`gh pr checks --watch`) and report its result.
- Do **not** merge. Merging happens only after the supervisor approves (see CLAUDE.md, Git and GitHub workflow).

## 5. Hand back in this format, then stop

```
## Checkpoint <A–E> · Phase <N> complete

Checks: ruff format ✔/✘ · ruff check ✔/✘ · pytest <passed>/<total> · entry point ✔/✘

Acceptance criteria (spec §13):
- <criterion> — met / not met / partly met — <evidence>

Sanity report:
<the printed sanity table for this phase>

Deviations from spec: <none | list with reason>
Decisions logged: <none | DECISIONS.md entries>
Open issues / questions for supervisor: <list>
Files changed: <list>
```

PR: <url>  ·  CI: <passed / failed>

Then stop and wait. Do not start the next phase.

## 6. After approval

When Shubham says the checkpoint is approved:

```
gh pr merge --merge --delete-branch
git checkout main && git pull
git tag phase-<N> && git push origin phase-<N>
```
