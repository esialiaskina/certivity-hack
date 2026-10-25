# ARCHITECTURE — "Compile once, prove per product"

Working name: **RegIR**. Target: Certivity challenge (main goal + sub-goal), Industrial Agents Hackathon, Munich, 24–25 Oct 2026.

Status legend used below: **[DATA]** = verified in the repo files. **[HYP]** = hypothesis, must be verified against the PDFs. **[DESIGN]** = our decision.

---

## 0. What the repo data actually tells us

All numbers below were computed from `cases/dev-rear-lamp/expected.json`, `regulations/index.json`, `subgoal/dev/*`.

| # | Fact [DATA] | Consequence for design |
|---|---|---|
| 1 | 56 regulations in the index, but the rear-lamp gold cites only **4**: R148 (63 reqs), R48 (56), R150 (39), R10 (32). Total 190. | Regulation selection is the main precision lever. 52 of 56 are distractors. |
| 2 | Gold does **not** cite R7 (position/stop lamps), R6, R23 (reversing lamps), R3 (retro-reflectors), R38, R128, R37, R104, although all are in the index and sound relevant. R148 and R150 are the newer consolidated regulations. | **[HYP]** Successor regulations supersede older single-function ones. Needs a supersession/coverage model, not keyword matching. |
| 3 | R10 (EMC) is cited with only 1 req from §5 and 25 from §6, plus 6 from annexes; all at **ESA (sub-assembly)** level. The lamp has "LED modules on PCB". | EMC is a **horizontal** regulation triggered by a technology facet (electronics), and inside it only the ESA branch applies, not the vehicle branch. Applicability is **conditional inside a regulation**. |
| 4 | Gold requirement ids run G-0001..G-0234 but only **190 exist** (gaps at 7, 25, 27–28, 30–35, ...). | Experts started from a fuller extraction (~234 atoms) and **removed ~44**. We must learn what gets removed (likely non-applicable branches). |
| 5 | 99.5% of gold texts contain "shall". Median length 212 chars. 62% contain a digit. 34 paragraphs yield more than one requirement. | Requirements are atomic `shall` statements; compound paragraphs are split. |
| 6 | Every gold item has `paragraph`; none has `test_case`. | Paragraph label is always available. Test cases are optional and not in gold. |
| 7 | Gold includes marking requirements (R148 §3.3, R150 §3.3), construction (§4), photometry (§6), and R10 test levels. It starts R148 at §3.3.1.1 (not §3.1/3.2 application procedure). | Procedural/administrative text (application for approval) is out; product-level obligations are in. We need a **role** attribute per atom. |
| 8 | Sub-goal dev (UN R175): 94 old reqs → 24 changes: 17 added, 6 modified, 1 removed. Reasons are literal word diffs, e.g. `'standstill.' became 'standstill and, as relevant, while creeping.'`. Old req R-001 is an *application procedure* sentence. | Reason text = deterministic diff. Also: the sub-goal's old list **does** contain procedural items, so "role" inclusion differs by task. |
| 9 | Scorer (README): regulation level, page level (page OR paragraph right, full page range of the expected paragraph), requirement level (LLM, one-to-one match on "same scope, condition, constraint"). Main goal uses **base** version; `latest` page = wrong page. | Always output paragraph + base-version page. Atom granularity must match "scope, condition, constraint". |

---

## 1. Design principles (the anti-bias contract)

1. **Compile the law, don't read it per product.** All regulation reading is product-agnostic and done offline for all 56 regulations. The held-out product (released Sun 08:00) then only needs product formalisation + evaluation.
2. **The LLM proposes, deterministic code disposes.** Every LLM output must pass a mechanical check (quote is a substring of the cited page, label exists in the parse tree, predicate is well-formed). Failing items are dropped or retried, never shipped.
3. **No rear-lamp knowledge in prompts or code.** Prompts use abstract facets and few-shot examples from unrelated domains (seat belts, tyres, glazing). The dev case is a **test set**, not a training set (see §9).
4. **Everything has a probability, then one global cutoff.** Per-atom `p(applies)` is calibrated; one threshold derived from the F2 objective decides inclusion (see §7.3).
5. **Unknown is a first-class value.** Missing product facts become explicit assumptions, shown in the UI, instead of silent guesses.
6. **Every output carries a proof object** (quote + page crop + facts used). This is the demo and the traceability score.

---

## 2. Overview

```
                    OFFLINE (tonight, product-agnostic, cached)
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 56 base PDFs ─► A1 layout parse ─► A2 paragraph tree + page spans     │
 │                 ─► A3 definitions + cross-ref graph                   │
 │                 ─► A4 atomizer (1 shall = 1 atom, verbatim quote)     │
 │                 ─► A5 role tagger  ─► A6 scope-condition compiler     │
 │                 ─► A7 regulation cards (scope, vertical/horizontal,   │
 │                        supersedes, covers[], domain tags)             │
 └───────────────────────────────┬──────────────────────────────────────┘
                                 │  RegIR store (JSONL + SQLite/FTS)
                    ONLINE (per product, minutes)
 ┌───────────────────────────────▼──────────────────────────────────────┐
 │ B  Product formaliser: spec.md + image ─► facet sheet (known/assumed/ │
 │    unknown, each with evidence)                                       │
 │ C  Regulation selector: candidates ─► scope proofs ─► coverage solver │
 │    (supersession, horizontal triggers)                                │
 │ D  Atom evaluator: predicates × facets, 3-valued (yes/no/unknown)     │
 │ E  Verifier: grounding, atomicity, ensemble vote, calibration, cutoff │
 └───────────────────────────────┬──────────────────────────────────────┘
                                 ▼
          requirements.json  +  proof objects  +  UI / 60s demo
 SUB-GOAL (parallel path): old atoms ⇄ new atoms alignment ─► diff ─► changes.json
```

---

## 3. Layer A — Regulation IR (offline)

### 3.1 Schemas

```jsonc
// Node: one numbered paragraph in the tree
{ "node_id": "UN_R10@7.2.0#6.9.1", "reg": "UN R10", "version": "7.2.0",
  "label": "6.9.1", "heading_path": ["6", "6.9", "6.9.1"],
  "heading_titles": ["Requirements", "...", "..."],
  "page_start": 12, "page_end": 12, "text": "…verbatim…", "parent": "…", "children": ["…"] }

// Atom: one obligation, derived from exactly one node
{ "atom_id": "UN_R10@7.2.0#6.9.1/a2", "node_id": "…",
  "quote": "…verbatim substring of node text…",
  "text": "normalised, self-contained obligation (subject + condition + constraint)",
  "role": "performance|construction|marking|test_condition|procedure|conformity|transitional|definition|informative",
  "modality": "shall|shall_not|may|should",
  "conditions": [ Predicate ],      // own conditions, parsed from this atom
  "inherited": [ Predicate ],       // from ancestors (headings like "ESA requirements")
  "refs": ["UN_R10#Annex 7", "UN_R48#6.2"], "split_of": "node_id or null" }

// Predicate over the product facet ontology (tiny DSL, see §4)
{ "facet": "product.approval_level", "op": "eq|in|not_in|gte|lte|has|lacks", "value": "ESA" }
// escape hatch for conditions we cannot formalise
{ "free": "where an optional lamp is mounted above 2100 mm" }
```

### 3.2 Steps

- **A1 Layout parse.** PyMuPDF text blocks with bbox, page index per block. Keep the **PDF page index** (1-based), the same as the platform. Store the printed page label separately. Rasterise on demand for the page-crop proof.
- **A2 Paragraph tree.** Regex over numbering (`5.4.2.3.`, `Annex 8, 2.1`, `(a)`, `(i)`); build the tree; a node's `page_start..page_end` covers spans (the scorer uses the full range of the expected paragraph). Tables and figures attach to the nearest preceding node as `attachments`.
- **A3 Definitions and cross-references.** §2 definitions → term table (used to expand terms in atoms and facets). Regex + LLM resolve "paragraph 2.3.10", "Annex 8", "UN Regulation No. 10" into edges. The graph yields the horizontal/vertical classification (A7).
- **A4 Atomizer.** LLM splits each node into atoms with the rule: *one engineering obligation = one subject + one condition set + one constraint*. Enumerations "(a) … (b) …" with different constraints become separate atoms; shared preamble is copied into each (self-contained text). **Hard check:** `quote` must be a substring of the node text after whitespace normalisation, else retry/drop. This removes invented requirements by construction.
- **A5 Role tagger.** Classify each atom's role (list above). One cheap call per node batch. The task-level role filter (§7.1) is configured later, not baked in.
- **A6 Scope-condition compiler.** Convert (a) heading-path scope ("ESA", "vehicles of category M1", "optional lamps") and (b) inline conditions ("where the device is fitted with LED modules") into predicates over the facet ontology. Predicates are produced offline and reviewable as data; unparseable ones stay `free`.
- **A7 Regulation cards.** Per regulation: scope sentence(s) (§1), `covers[]` (functions/devices claimed), `kind` ∈ {vertical, horizontal, out-of-domain}, `category_domain` (M/N vs L vs …), `supersedes` / `superseded_by` (detected from text and from index titles/series), `atom_count`, `horizontal_triggers` (e.g. `has_electronics`).

**Why this generalises:** nothing in A1–A7 mentions a product. The held-out bumper regulations (likely R42, R127, GTR 9, R26, R10, maybe R152/R131 …) are compiled the same way as the lamp regulations. **[HYP on which ones; the selector decides.]**

**Pre-compute all 56 tonight.** At roughly 60–110 pages for the larger regulations this is a modest, parallel job. Cache by `sha256` from `index.json`. On Sunday 08:00 only the held-out product's own processing remains.

---

## 4. Layer B — Product formaliser

### 4.1 Facet ontology (generic, not lamp-specific) [DESIGN]

```
product.kind_path        e.g. vehicle > body > bumper-system | lighting > lamp | restraint > belt
product.approval_level   vehicle | system | component | ESA | STU
vehicle.category         M1 M2 M3 N1 N2 N3 O* L*       (+ "applies to M and N" ranges)
function.set             signalling, illumination, conspicuity, braking, steering, restraint,
                         impact-protection, pedestrian-protection, sensing, communication, ...
location                 front | rear | side | roof | underbody | interior | exterior
tech.has_electronics     bool   (PCB, LED, ECU, sensor)
tech.sensors             radar | camera | ultrasonic | lidar | none
tech.has_software        bool
tech.light_sources       none | LED | filament | gas-discharge
tech.optics              lens | reflector | prism | none
material.classes         polymer | glass | metal | composite | ...
power.supply             none | 12V | 24V | HV
interfaces               bus | wiring | wireless
part.list                hierarchical parts from spec + exploded view, each with function + facets
```

Each facet value is `{value, status: known|assumed|unknown, evidence: [spec line | image region]}`.

### 4.2 Extraction

1. Vision model on the exploded view → labelled parts, relations, function per part (every part becomes a `part.list` entry).
2. LLM on `spec.md` → facet sheet with evidence; **must cite the spec line or image region** for each `known`.
3. **Assumption pass:** for every facet that matters to some compiled predicate but is unknown, emit an assumption with a default and a reason. These appear in the UI as "we assumed X; change it and the list updates" (cheap re-run because evaluation is deterministic).
4. **Taxonomy mapping:** map `kind_path` into the regulation cards' `covers[]` via embedding + LLM check, but keep both strings so a human can audit.

Anti-bias rule: the extraction prompt is the same for every product; the only product-specific input is the document.

---

## 5. Layer C — Regulation selection as a coverage problem

### 5.1 Candidate generation (high recall, four independent channels, then union)

1. **Title/card LLM:** product facets + all 56 regulation cards (small) → ranked candidates with reasons.
2. **Scope retrieval:** BM25 + embeddings of each card's scope + definitions against part names and function set.
3. **Term hit map:** for each part/function term, count hits in each regulation's definitions + scope + headings (cheap, high-signal for exact device names).
4. **Graph expansion:** follow cross-reference edges from already-selected regulations (a selected lighting regulation that cites an installation regulation pulls that in) and add **horizontal** regulations whose trigger facet is true (e.g. `has_electronics` → EMC; `has_software` → software-update/cyber regulations). **[HYP]** This is how R10 and R48 get in for the lamp.

### 5.2 Scope proof (precision gate)

For each candidate the model must produce, in one structured call:
```
{ "scope_quotes": [verbatim sentences from the regulation's scope],
  "matching_facts": [facet refs that satisfy the scope],
  "excluding_facts": [facet refs or text clauses that could exclude it ("does not apply to…")],
  "branch": "vehicle|system|component|ESA|…",     // which approval level applies
  "verdict": "applies|not|partial", "p": 0..1 }
```
Mechanical checks: quotes are substrings; facet refs exist. A second, independent call plays the **adversary** ("argue why this regulation does NOT apply, quote the exclusion"). Final `p` = calibrated combination; disagreement lowers `p`.

### 5.3 Coverage solver with supersession

Elements to cover: each product function/part. Each candidate `r` claims `covers(r)` (from its card + scope proof). Choose the set `S` that:
- covers every product function at least once (**coverage constraint**),
- does not select both a regulation and its successor unless the scope proof shows a residual function the successor does not cover (**supersession edge**),
- includes horizontal regulations when their trigger facet is true,
- maximises expected F2 (§7.3), using `p(r)` and the regulation's atom count (a wrong regulation with 60 atoms costs more than one with 6).

Small enough to solve with greedy + brute-force over ≤ 15 candidates; no ILP library needed.

**[HYP]** On the dev case this should select R148 over R7/R6/R23/R38, R150 over R3, plus R48 (installation) and R10 (electronics), which is exactly the gold set. We check this as a test, not as a target (§9).

---

## 6. Layer D — Atom evaluator

For each atom of each selected regulation:

1. Evaluate `inherited ∧ conditions` against the facet sheet with **three-valued logic**: `true / false / unknown`.
2. `false` → exclude (this is how the vehicle-level branch of EMC drops for a component, **[DATA #3]**).
3. `true` → include with high `p`.
4. `unknown` → LLM judge on only this atom + the facet sheet + assumptions; output `p` and the missing fact. Included as **conditional** ("applies if X").
5. `free` predicates are evaluated by the same LLM judge.

Deterministic where possible, LLM only where the predicate is irreducibly textual. The result is auditable: each requirement shows `facts → predicate → verdict`.

---

## 7. Layer E — Verification, calibration, operating point

### 7.1 Task-level role filter
Main goal keeps roles `performance, construction, marking, test_condition`; drops `procedure, conformity, transitional, definition, informative` **[DATA #7 supports; verify on the ~44 removed ids]**. The sub-goal keeps procedural roles (its old list contains them, **[DATA #8]**). This is a configuration, not code.

### 7.2 Verifiers (each is cheap and independent)
- **Grounding:** `quote ⊂ page text`, `label ∈ tree`, `page = node.page_start` (and we also emit `paragraph`, so a page off-by-one costs nothing, per README).
- **Atomicity:** a splitter model checks no atom contains two independent constraints; merged atoms are split (recall protection, "merges several obligations into one", brief §07).
- **Self-consistency:** evaluate borderline atoms with 3 prompts/models; `p` = vote share, tempered by disagreement.
- **Calibration:** map raw scores to probabilities with isotonic/Platt on the metamorphic and silver data (§9), not on the single gold case.

### 7.3 The right objective is F2, not "near-perfect precision"
The brief ranks by **F2 with recall as tie-break**. For a calibrated probability `p`, the F-beta-optimal rule is: include an item iff `p > F*/(1+β²)`, where `F*` is the best achievable score. For β = 2 this is `F*/5`. With `F* ≈ 0.6–0.7` the cutoff is **p ≈ 0.12–0.14**.

So the goal is **calibrated probabilities and one global cutoff**, not maximal precision on every item:
- be **strict at the regulation level** (a wrong regulation adds dozens of false positives and also fails the regulation-level metric),
- be **liberal inside selected regulations** (include `unknown`/conditional atoms, flag them),
- never pad with unrelated regulations.

We cannot honestly promise "almost perfect precision for every product". We can promise: no invented text (grounding), correct citations (tree), and measured, tunable precision/recall trade-offs.

---

## 8. Sub-goal pipeline (version diff)

Input: `requirements_old.json` (each with regulation, page, paragraph) + old/new PDFs.

1. Compile **old** and **new** with Layer A (no product conditions needed).
2. **Align** old atoms ↔ new atoms: first by paragraph label, then (for renumbering, e.g. "6.5 formerly") by embedding similarity inside the same heading subtree; solve one-to-one with Hungarian matching, with a positional prior.
3. For each old requirement, find its source atom(s) → status:
   - matched, token-diff empty → unchanged (omit),
   - matched, diff non-empty → LLM decides *materially changed?* → `modified`, `new_text` = the new atom text,
   - unmatched → `removed`.
4. **Added:** new atoms with no old counterpart, passed through the same role filter.
5. **Reason:** generated from the deterministic token diff (`'X' became 'Y'; 'Z' was added.` in the dev gold style), plus the new paragraph label and page.
6. Output `changes.json`; `requirement_id` is `null` for `added`.

Dev gold shows 17 added of 24 changes, so the **added** branch dominates recall: coverage of new atoms matters most.

---

## 9. Evaluation without overfitting to the rear lamp

One golden case is not a training set. We use it three ways only:

1. **Parser unit test.** For each gold item: does paragraph label `L` start on PDF page `P` in our parse? This validates A1–A2 on 190 items and the R175 old list on 94 more, using the gold for *infrastructure*, not for tuning.
2. **Two-domain calibration.** Atom style and role filter are tuned on **R175** (sub-goal old list, a totally different domain); applicability/selection is tested on the rear lamp. Neither is tuned on the other.
3. **One-shot final test.** Freeze prompts and ontology, run the dev case once as a test, and report the numbers honestly in the pitch.

Gold-free evaluation (works for any product):
- **Metamorphic tests.** (a) delete the electronics facet → EMC atoms vanish and nothing else changes; (b) change `vehicle.category` M1 → L3 → category-gated atoms/regulations flip; (c) add an irrelevant sentence ("has a cup holder") → output unchanged; (d) paraphrase the spec → Jaccard of outputs ≥ 0.9; (e) shuffle part order → identical.
- **Synthetic product zoo.** Generate 15–20 short specs in the `spec.md` format from the *scope sections of other regulations* (the regulation is the silver label for "this regulation applies"). Measures regulation-level precision/recall for any product class.
- **Knob list (the only things tuned on gold):** global cutoff, role filter set, adversary weight. Nothing else.

---

## 10. Demo design (60 seconds)

One screen, three columns, driven by the real pipeline (cached for the video, live for the finals):

1. **Product** — spec + exploded view with detected parts as clickable chips, facet sheet with *known / assumed / unknown* badges.
2. **Regulations** — accepted (with scope quote) and **rejected** (with exclusion quote and "superseded by R…"), a coverage matrix function × regulation.
3. **Requirements** — list; click one → PDF page opens with the paragraph highlighted + proof card (`facts → predicate → verdict`, confidence, "conditional on X").
4. **Toggle assumption** ("remove electronics") → list updates live (shows determinism and explainability).
5. **Version tab** — side-by-side diff with the generated reasons.

Timing script: 0–10 s problem; 10–30 s run; 30–45 s click-through proof; 45–55 s live assumption toggle; 55–60 s dev-case numbers.

---

## 11. Repo layout

```
regir/
  ingest/      parse.py tree.py defs.py xrefs.py
  compile/     atomize.py roles.py conditions.py cards.py   # offline, product-agnostic
  product/     ontology.py extract_text.py extract_image.py assumptions.py
  select/      candidates.py scope_proof.py coverage.py
  evaluate/    predicates.py judge.py
  verify/      grounding.py atomicity.py ensemble.py calibrate.py
  subgoal/     align.py diff.py
  eval/        parser_test.py metamorphic.py zoo.py score.py
  app/         api.py ui/
data/          (gitignored: PDFs, compiled IR)   # data licence: hackathon use only
```
Shared contract: the JSON schemas in §3.1 and the facet ontology in §4.1 are the interfaces. Each module reads/writes files, so four people can work in parallel without merge conflicts.

---

## 12. Build plan

Current time Sat 23:45; held-out released Sun 08:00; uploads close 13:00 (5/hour); code freeze 13:00.

| Level | What | Done when |
|---|---|---|
| **L0** (safety net) | Naive: pick regs by LLM over titles, extract per chunk, submit. | Passes `validate.py`, uploaded for dev case. |
| **L1** | A1–A5 + grounding verifier + paragraph/page correctness. | Parser test passes on gold; no ungrounded items. |
| **L2** | A6–A7, facet sheet, scope proof, coverage solver, 3-valued evaluator. | Dev case regulation set = {R148, R48, R150, R10} **without** lamp-specific hints. |
| **L3** | Ensemble, calibration, F2 cutoff, metamorphic suite, zoo. | Stable under paraphrase; cutoff chosen from silver data. |
| **Sub-goal** | §8. | Dev: recall on 24 changes, reasons as diffs. |

Order of work: 
1. **Now (≤ 30 min):** everyone clones; one person runs `python tools/fetch_regulations.py` (needs normal internet; my sandbox cannot reach the PDF host); fix the schemas in §3.1/§4.1.
2. **Tonight to ~02:30:** P1 ingest + parser test; P2 atomizer prototype on R175 and R150; P3 facet ontology + extraction on the dev spec; P4 UI shell reading the JSON files.
3. **Sleep 4 h.** Run compile for all 56 in the background first (cost estimate before launching).
4. **08:00:** pull held-out; run L2; manually review the regulation list; upload; iterate 08:30–12:30; **final upload must be the best one.**

Cut line: if L2 slips, ship L1 plus heading-path scope (no predicates) and per-section LLM applicability. Never drop grounding.

---

## 13. Open questions to verify when PDFs are available

1. Does R148's §1 scope list the position, stop, reversing lamp functions, and do R7/R23/R6 state a successor relationship? **[HYP #2]**
2. Is the gold page the paragraph's start page, and how do multi-page paragraphs behave? (README: full range counts.)
3. Which ~44 atoms were removed from the 234? Compare our unfiltered atoms with the 190 to learn the rule (role? branch? duplicates?).
4. How large is each regulation (pages, atoms)? Needed for cost estimate before the all-56 compile.
5. Do R7/R6/R23 remain in the index as deliberate distractors, and what do the bumper regulations look like (R42, R127, GTR 9, R26)? Check after 08:00.
6. Is the requirement-level judge sensitive to atom granularity (one-to-one)? Test with the two splitting extremes on the dev case.
