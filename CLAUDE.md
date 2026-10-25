# CLAUDE.md — RegIR project handoff (read first)

Team: Yesieniia + 3 (beginners). Industrial Agents Hackathon Munich, Certivity track. Goal: WIN.
Held-out case `heldout-front-bumper` released Sun 25 Oct 08:00; uploads close 13:00 (LAST valid upload counts, 5/hour); code freeze 13:00; finals 15:00.

## Task
Input: product spec.md (+ exploded-view image). Output JSON `{team_id, case_id, requirements:[{id,text,source:{regulation,version,page,paragraph}}]}`
citing UN Regulations (BASE version, 1-based PDF page, paragraph label). Scored vs hidden gold: F2 (recall-weighted), 40%.
Optional sub-goal: diff old vs new regulation version (modified/removed/added + reason), 15%. Demo/UI 20% (60 s video), impact 15%, pitch 10%.
Validate with `tools/validate.py`, score with `tools/score_local.py` (dev case: cases/dev-rear-lamp, subgoal/dev).

## Architecture
Full design: ARCHITECTURE.md ("RegIR": compile regulations once product-agnostically -> atoms with verbatim quotes -> roles -> scope predicates;
online: formalise product into facet sheet (known/assumed/unknown), select regulations as coverage problem with supersession + horizontal triggers,
hierarchical section routing, 3-valued predicate evaluation, verifiers (quote grounding, atomicity, ensemble, calibration), F2 cutoff p > ~0.12-0.14).
Do NOT overfit to the single dev rear-lamp case. Everything must generalise to any product.

## Done (branch `regir`, orphan branch, never look back at old code)
- regir/ingest/parse.py: paragraph tree parser, 190/190 gold pages (run `python -m regir.eval.parser_test`)
- regir/compile/cards.py, regir/subgoal/diff.py (7/7, 17/17 on dev), regir/select/router.py, supersession.py (noisy candidate generator only)
- regir/llm.py (cache, retries; NO temperature arg with anthropic SDK 2.x), regir/compile/atomize.py (grounded atoms), regir/evaluate/predicates.py (T/F/U engine)
- docs/FINDINGS.md: verified facts about gold (190 reqs over R148/R48/R150/R10; only ~10% of "shall" paragraphs kept)

## Next (in order)
1. `python -m regir.llm` must print ok for both models; then `python -m regir.compile.atomize "UN R150" --limit 15`; check atoms vs gold.
2. Atomize the 4 dev regs (UN R148, R48, R150, R10), measure recall/granularity against gold, learn which kinds were dropped.
3. Facet ontology + product formaliser (spec + image vision).
4. LLM section router + scope-proof selector (adversarial), coverage solver with supersession.
5. Atom evaluator, verifiers, F2 cutoff, output writer + validate/score.
6. Sub-goal LLM judge; UI + 60 s demo.

## Rules
- Secrets: `.env` is gitignored; never print or commit keys. data/ and regulations/pdf/ are gitignored.
- The user runs git commits; propose commit commands, end messages with the attribution trailer if committing.
- Keep explanations short and beginner-friendly; build step by step, test each step.
