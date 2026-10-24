# Verified findings (measured on the repo data; update as we learn)

All numbers are reproducible: `python -m regir.eval.parser_test`, `python -m regir.eval.subgoal_eval`, `python -m regir.compile.cards`.

## Infrastructure
- Gold page = the PDF's own 1-based page index. Parser resolves **190/190** gold paragraphs (+ **94/94** R175 old reqs) to a node whose page span contains the cited page.
- Each PDF prints a header `UN R148, version 1.6.0 | page 7 of 48` (stripped by the parser).
- Annex headings only trustworthy as a *sequence starting at Annex 1* (body lines mimic headings). Ids like `2A`, sub-levels `Part N`, `Appendix N`.
- Known parser noise: UN R49 (engine tables parsed as paragraphs), UN R128 (one 32k-char node). Out of domain for M1 products.

## Regulation selection
- Index has 56 regulations; rear-lamp gold cites 4 (R148, R48, R150, R10).
- Horizontal regulations (cited by many others): R10 (11 regs), R48 (7), R155 (7), R79 (5), R128 (5).
- Supersession: text hint works for R6/R7 -> R148 ("cease to grant approvals ... UN Regulation No. 148"); generic "replaces" regex is noisy (R48->R37 wrong). **Scope containment** is the stronger signal: R148's scope enumerates position, stop, reversing, direction-indicator, rear-fog... lamps = superset of R6/R7/R23/R38.

## Selection INSIDE a regulation is the main precision lever
- 1,238 paragraphs containing "shall/must" in the 4 gold regulations; gold keeps ~119 paragraphs (~10%).
- R48: 421 shall-nodes, gold 35 paragraphs. In section 6 (per-device requirements, 218 shall-nodes) gold keeps exactly 6.4 Reversing lamp, 6.7 Stop lamp, 6.10 Rear position lamp, 6.14 Rear retro-reflector (non-triangular) = the product's functions; plus ~10 general provisions from section 5.
- R10: gold takes the ESA branch (section 6) + 2 annexes; vehicle branch excluded.
- R150: gold takes retro-reflector class sections (5.1), general 3.3/4.x, selected annex tests.
- Gold also includes paragraphs WITHOUT "shall" (e.g. R48 5.18 "may be installed ... only if"): shall-only detection misses ~13/35 R48 gold paragraphs. Modality detection must be broader (only if / is required / must / may not / mandatory).

## Keyword section router (no LLM) - baseline, regir/select/router.py
- R48 section 6: finds all four gold device sections from the spec's own part/function terms (6.4, 6.7, 6.10, 6.14) BUT also 3 wrong retro-reflector sections (6.15 triangular rear, 6.16 front, 6.17 side). Needs location/shape facets (shape unknown -> assumption).
- Covers only device-specific subsections: 19/35 R48, 2/29 R150, 4/40 R148, 0/15 R10 gold paragraphs. General sections and technology-triggered ones (R10) need other mechanisms.

## Sub-goal deterministic baseline (regir/subgoal/diff.py, R175 dev)
- Modified/removed: 7/7 found, flags 18 of 94 old reqs. Added: 17/17 labels found, 34 proposed. LLM judge only has to filter + write text.

## Implications for the design
1. Add hierarchical *section routing* (prune subtrees by heading vs facets) before atom evaluation; classify sections as device-specific / general / horizontal-trigger.
2. General sections of an accepted regulation: default include (recall), judged per atom.
3. Broader modality detection for atoms.
