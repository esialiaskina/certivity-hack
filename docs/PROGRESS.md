# RegIR Upgrade Progress

## Baseline metrics (pipeline.py judge — strict one-to-one matching)

| Regulation | Expected | Submitted | Matched | Precision | Recall | F2 |
|---|---|---|---|---|---|---|
| UN R10 | 32 | 46 | 25 | 0.543 | 0.781 | 0.718 |
| UN R148 | 63 | 108 | 51 | 0.472 | 0.810 | 0.708 |
| UN R150 | 39 | 82 | 33 | 0.402 | 0.846 | 0.693 |
| UN R26 | 0 | 6 | 0 | 0.000 | 0.000 | 0.000 |
| UN R48 | 56 | 98 | 39 | 0.398 | 0.696 | 0.606 |
| **all 4 gold** | **190** | **334** | **148** | **0.443** | **0.779** | **0.676** |

(hybrid.py judge, more permissive: F2=0.71, recall=0.82)

### Leave-one-regulation-out (LORO) F2

| Held-out | F2 | P | R |
|---|---|---|---|
| UN R10 | 0.668 | 0.427 | 0.778 |
| UN R148 | 0.661 | 0.429 | 0.764 |
| UN R150 | 0.672 | 0.456 | 0.762 |
| UN R48 | 0.706 | 0.462 | 0.813 |

### Loss analysis
- 26 reqs lost in 18 under-split paragraphs (merged reason dominant)
- 6 gold paragraphs never cited (not_extracted)
- UN R26 selected incorrectly: 6 pure FP (0 expected)
- No probability cutoff: every output req counted equally
- Overall FP rate: ~55% of submitted reqs are wrong

### Hard-coded lamp hints found (do not edit _team, flagged only)
- `hybrid.py:31` `LIGHT_SOURCE_REGS = {"UN R37", "UN R99", "UN R128"}` — lamp-specific exclusion set
- `hybrid.py:40-41` SCREEN_RULES — "Light-source regulations (R37 filament, R99 gas-discharge, R128 LED) apply only to replaceable light sources" — lamp-specific scope rule
- `hybrid7.py:95-96` FILTER_SYSTEM — "lamps incorporating a logo", "where optional lamps are installed", "replaceable light source modules" — lamp-specific keep-examples in the drop filter

### What is needed to run the pipeline on a new case
1. `ANTHROPIC_API_KEY` set in `_team/.env` (already set, len=106)
2. Regulation PDFs in `_team/data/pdf/` (pre-existing)
3. Either: `--profile <path>` pointing to a saved profile JSON, OR vision model call (builds profile automatically)
4. **No cache exists** — every run will make fresh API calls (~50-80 calls for a 4-regulation case)
5. PKG path bug: `pipeline.PKG` and `reqagent.PKG` both resolve to non-existent `industrial-ai-hackathon/industrial-ai-hackathon`; `evaluate.py` will fail at import. Workaround: skip `evaluate.py` import (not needed for submission); `validate.py` and `score_local.py` work via subprocess in hybrid7.py only when `expected.json` exists.
6. Run from `_team/` directory: `python src/hybrid7.py <case_dir> --run-name <name> --team <id> [--profile <path>]`

---

## Step 0 — Baseline  2026-10-25
Report: pipeline.py judge F2=0.676 (4 gold regs), LORO range 0.661–0.706. Main losses: splitting (26 reqs merged), false positives (55%), one wrong regulation (R26). No cache on disk; new runs cost ~50-80 API calls each.

## P6 — Operations / run.py  2026-10-25
`python -m regir.upgrade.run cases/synth-front-bumper --team team-05 --mode balanced` works end to end. PKG patched in wrapper (not _team). Cache persistent at data/llm_cache/. synth-front-bumper: 471.9s, 135 API calls, 657 reqs. Regs selected: R10 R26 R42 R79 R127 R152 R155 R156 R171 (no lamp regs — generalises). Model: claude-opus-5-5 (~$76/run est.); haiku-4-5 for stage C/C2 would cut cost ~80% — measure F2 loss before switching.

## P2 — Split pass (Step 1)  2026-10-25
REJECTED. v1: 115 new reqs, 1/115 matched gold, F2=0.605. v2 (table-row granularity prompt): 161 new reqs, ~2/161 matched, F2=0.595. LORO folds 0.577–0.629 vs baseline 0.668–0.706. Root cause: LLM over-generates from non-merged paragraphs; even paragraphs that ARE merged (e.g. R10 6.9.1) return empty because the merged req "covers" the table content. Correct fix requires re-running stage C with a more granular prompt; deferred to full pipeline re-run after P3/P5.
