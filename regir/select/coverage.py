"""C3: Coverage solver — turn scored candidates into the final selected regulation set.
Handles: supersession (drop predecessor if successor applies), horizontal forced-includes,
and a p-threshold gate. Product-agnostic.

Strategy (greedy, no ILP needed at ≤20 candidates):
  1. Start with all candidates above P_THRESHOLD.
  2. Apply supersession: if both A and B are in the set and B supersedes A, drop A.
  3. Force-include horizontals whose trigger fired (regardless of p).
  4. Return the final set with explanations.
"""
from __future__ import annotations
import json
P_THRESHOLD = 0.14   # recall-weighted starting point; calibrate, do not tune on one gold case

# Only legally verified replacement relationships belong here. Scope overlap,
# title similarity and ordinary cross-references are candidate evidence, not
# proof that one regulation replaces another. An empty set is safer than a
# false edge that removes an applicable regulation.
CONFIRMED_SUPERSESSION: set[tuple[str, str]] = set()


def _supersession_edges(cards: dict) -> set[tuple[str, str]]:
    """Return only audited (predecessor, successor) relationships."""
    return {(a, b) for a, b in CONFIRMED_SUPERSESSION if a in cards and b in cards}


def solve(
    scored: list[dict],
    cards: dict,
    horizontal_forced: list[str] | None = None,
) -> list[dict]:
    """
    scored: output of scope_proof.score_all() — list of {regulation, p, verdict, branch, ...}
    cards: full cards dict
    horizontal_forced: regulations that must be included regardless of p (triggered by facets)

    Returns list of selected dicts with added key 'selection_reason'.
    """
    horizontal_forced = set(horizontal_forced or [])
    scored_map = {r["regulation"]: r for r in scored}

    # Step 1: candidates above threshold + forced
    selected = {
        r["regulation"]: r
        for r in scored
        if r["p"] >= P_THRESHOLD or r["regulation"] in horizontal_forced
    }
    for reg in horizontal_forced:
        if reg not in selected and reg in scored_map:
            selected[reg] = scored_map[reg]
        elif reg not in selected:
            # forced but not scored — add with p=0.5 placeholder
            selected[reg] = {"regulation": reg, "p": 0.5, "verdict": "partial", "branch": "component",
                             "scope_quotes": [], "excluding_quotes": [],
                             "advocate_reason": "horizontal trigger", "adversary_reason": ""}

    # Step 2: supersession — drop A if B is selected and B supersedes A
    edges = _supersession_edges(cards)
    superseded_by: dict[str, list[str]] = {}
    for a, b in edges:
        superseded_by.setdefault(a, []).append(b)

    to_drop = set()
    for reg in list(selected):
        successors_selected = [b for b in superseded_by.get(reg, []) if b in selected]
        if successors_selected:
            to_drop.add(reg)
            # Record why it was dropped
            selected[reg]["dropped_by"] = successors_selected

    # Only drop if NOT horizontally forced
    for reg in to_drop:
        if reg not in horizontal_forced:
            selected[reg]["selection_reason"] = f"superseded by {selected[reg]['dropped_by']}"
            del selected[reg]

    # Step 3: annotate each kept regulation with a selection reason
    result = []
    for reg, r in selected.items():
        if "selection_reason" not in r:
            parts = []
            if reg in horizontal_forced:
                parts.append("horizontal trigger (forced)")
            if r.get("scope_quotes"):
                parts.append(f"scope match (p={r['p']:.2f})")
            r = dict(r)
            r["selection_reason"] = "; ".join(parts) if parts else f"p={r['p']:.2f}"
        result.append(r)

    return sorted(result, key=lambda r: -r.get("p", 0))


def explain_dropped(scored: list[dict], selected_regs: set[str], cards: dict) -> list[dict]:
    """Return candidates that were considered but not selected, with reasons."""
    edges = _supersession_edges(cards)
    superseded_by: dict[str, list[str]] = {}
    for a, b in edges:
        superseded_by.setdefault(a, []).append(b)
    dropped = []
    for r in scored:
        reg = r["regulation"]
        if reg in selected_regs:
            continue
        reason = "p below threshold"
        successors_selected = [b for b in superseded_by.get(reg, []) if b in selected_regs]
        if successors_selected:
            reason = f"superseded by {successors_selected}"
        dropped.append({"regulation": reg, "p": r.get("p", 0), "reason": reason})
    return sorted(dropped, key=lambda r: -r.get("p", 0))


if __name__ == "__main__":
    import sys, json as J
    case_name = sys.argv[1] if len(sys.argv) > 1 else "dev-rear-lamp"
    sheet = J.load(open(f"data/facets/{case_name}.json"))
    cards = J.load(open("data/cards.json"))
    from regir.select.candidates import generate, _run_horizontal
    from regir.select.scope_proof import score_all
    cands = generate(sheet, cards)
    horizontals = _run_horizontal(sheet, cards)
    scored = score_all(cands, cards, sheet)
    selected = solve(scored, cards, horizontal_forced=horizontals)
    print(f"\nSelected ({len(selected)}):")
    for r in selected:
        print(f"  {r['regulation']:12s} p={r['p']:.2f} | {r['selection_reason']}")
    dropped = explain_dropped(scored, {r['regulation'] for r in selected}, cards)
    if dropped:
        print(f"\nDropped ({len(dropped)}):")
        for r in dropped[:8]:
            print(f"  {r['regulation']:12s} p={r['p']:.2f} | {r['reason']}")
