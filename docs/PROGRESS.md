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
