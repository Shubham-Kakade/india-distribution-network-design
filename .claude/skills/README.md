# Claude Code skills for this project

These skills are committed here so that every Claude Code session finds them, whether it runs locally or in the cloud at claude.ai/code. Edit them in place.

| Skill | Origin | Purpose |
|---|---|---|
| scnd-python-standards | project | Library-first ladder, when to make a function, units in names, idioms, tests |
| scnd-model-change | project | Safe workflow for anything that changes the numbers |
| scnd-checkpoint | project | End-of-phase verify, self-review, log, push and pull-request hand-back |
| ponytail | DietrichGebert/ponytail (MIT) | Smallest complete change; no speculative code |
| ponytail-review | DietrichGebert/ponytail (MIT) | Plain-English code review: correct, safe, tested, lean |
| systematic-debugging | obra/superpowers (MIT) | Root cause before fix |
| verification-before-completion | obra/superpowers (MIT) | Evidence before claiming done |

Each vendored skill keeps its LICENSE and a SOURCE.md naming the upstream commit.

Optional: the full Ponytail plugin, with its session hooks and status line, installs with `/plugin marketplace add DietrichGebert/ponytail`, then `/plugin install ponytail@ponytail`. It needs Node on PATH. The vendored skills work without it.
