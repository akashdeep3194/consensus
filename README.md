# Project Consensus 3D

A deterministic, asynchronous social prediction game. Player votes elect a
three-digit collective outcome — the three most-voted digits, ranked, always
distinct — and predictions are scored against it by per-digit distance.
Organising voting blocs is intended gameplay.

**Status:** design review complete, ruleset V1.1 agreed. No implementation started.

## Documents

| | |
|---|---|
| [`project_vision/`](project_vision/) | Source design — Project Consensus 3D v2.1 Implementation Design (10pp) |
| [`docs/00-ruleset.md`](docs/00-ruleset.md) | **Ruleset V1.1 — authoritative game rules.** Supersedes v2.1 §1–§3 |
| [`docs/01-design-evaluation.md`](docs/01-design-evaluation.md) | Evaluation of v2.1 — 13 findings, graded blocking / important / decide |
| [`docs/02-tech-stack.md`](docs/02-tech-stack.md) | Stack recommendation, two disagreements with §7.1, and the layers v2.1 left unspecified |
| [`docs/03-roadmap.md`](docs/03-roadmap.md) | 12 modules across 4 milestones, with exit criteria |
| [`docs/04-open-questions.md`](docs/04-open-questions.md) | 11 decisions that block implementation |
| [`analysis/`](analysis/) | Outcome-rule verification, coordination analysis, and the D'Hondt measurement that motivated the rule change |

## Start here

Read [`docs/00-ruleset.md`](docs/00-ruleset.md) — it is what the engine gets built
from. Then `docs/01-design-evaluation.md` for the twelve open implementation
findings, and `docs/04-open-questions.md` for the two new decisions (N1, N2) that
the rule change introduced.

```bash
python3 analysis/outcome_rule.py             # V1.1 rule, coordination effects, order penalty
python3 analysis/dhondt_equilibrium.py       # why D'Hondt was replaced
python3 analysis/dhondt_verify_examples.py   # reproduces the v2.1 §2.3 examples
```

## Core principle, carried forward from v2.1

> PostgreSQL defines what happened. The game rules define who won.
