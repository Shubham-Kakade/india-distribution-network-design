# Claude Code skills for this project

These are the source copies of the project skills. Phase 0 copies them into `.claude/skills/`, where Claude Code discovers them. Edit them here and re-copy, so the versions stay tracked in git.

| Skill | Origin | Purpose |
|---|---|---|
| scnd-python-standards | project | Library-first ladder, when to make a function, units in names, idioms, tests |
| scnd-model-change | project | Safe workflow for anything that changes the numbers |
| scnd-checkpoint | project | End-of-phase verify, self-review, log and hand-back |
| ponytail | DietrichGebert/ponytail (MIT) | Smallest complete change; no speculative code |
| ponytail-review | DietrichGebert/ponytail (MIT) | Plain-English code review: correct, safe, tested, lean |
| systematic-debugging | obra/superpowers (MIT) | Root cause before fix |
| verification-before-completion | obra/superpowers (MIT) | Evidence before claiming done |

Optional: the full Ponytail plugin, with its session hooks and status line, installs with `/plugin marketplace add DietrichGebert/ponytail`, then `/plugin install ponytail@ponytail`, sent as two separate prompts. It needs Node on PATH. The vendored skills work without it.
