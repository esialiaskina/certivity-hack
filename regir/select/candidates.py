"""C1: Generate a short list of candidate regulations (high recall, ~15 from 56).
Three channels: LLM title ranking, horizontal triggers, cross-reference expansion.
Product-agnostic: all product knowledge comes from the facet sheet."""
from __future__ import annotations
import json
from regir import llm

# Horizontal trigger rules: facet predicate -> regulation key
# These are structural facts about the regulatory system, not product-specific.
HORIZONTAL_TRIGGERS: list[tuple[dict, str]] = [
    ({"facet": "tech.has_electronics", "op": "truthy"}, "UN R10"),          # EMC
    ({"all": [
        {"facet": "tech.has_software", "op": "truthy"},
        {"facet": "product.approval_level", "op": "eq", "value": "vehicle"},
    ]}, "UN R155"),  # vehicle cybersecurity; component software alone is insufficient
]

SYSTEM = """You are a vehicle regulatory expert.
Given a product's characteristics and a list of UN Regulations, select ALL regulations that
are likely to apply. Be generous: it is better to include a regulation that turns out not to apply
than to miss one that does. Output ONLY the regulations that have a real chance of applying.

Return JSON: {"candidates": [{"regulation": "UN Rxx", "reason": "one sentence"}]}
Order by decreasing relevance. Include at most 20 items."""


def _card_summary(cards: dict) -> str:
    lines = []
    for reg, c in cards.items():
        scope_snip = (c.get("scope") or "")[:200].replace("\n", " ")
        lines.append(f"{reg}: {c['title']} | scope: {scope_snip}")
    return "\n".join(lines)


def _facet_summary(sheet: dict) -> str:
    lines = []
    for k, v in sheet.items():
        if isinstance(v, dict):
            val = v.get("value")
            status = v.get("status", "unknown")
        else:
            val = v; status = "known"
        if val is not None and val not in ([], "unknown"):
            lines.append(f"  {k} ({status}): {val}")
    return "\n".join(lines)


def _run_horizontal(sheet: dict, cards: dict) -> list[str]:
    """Add regulations triggered by technology facets, regardless of LLM ranking."""
    from regir.evaluate.predicates import evaluate
    triggered = []
    for pred, reg in HORIZONTAL_TRIGGERS:
        if reg not in cards:
            continue
        verdict, _, _ = evaluate(pred, sheet)
        if verdict == "true":
            triggered.append(reg)
    return triggered


def _cross_expand(candidates: list[str], cards: dict, top_cites: int = 3) -> list[str]:
    """Add regs that are heavily cited by the current candidates (cross-ref expansion)."""
    cite_counts: dict[str, int] = {}
    for reg in candidates:
        for cited_reg, count in cards.get(reg, {}).get("cites", {}).items():
            if cited_reg not in candidates:
                cite_counts[cited_reg] = cite_counts.get(cited_reg, 0) + count
    # add only regs cited by 2+ candidates or cited >=5 times
    new = [r for r, cnt in cite_counts.items()
           if (cnt >= 5 or sum(1 for c in candidates if r in cards.get(c, {}).get("cites", {})) >= 2)
           and r in cards]
    return candidates + new[:top_cites]


def generate(sheet: dict, cards: dict | None = None, model: str = llm.STRONG) -> list[str]:
    """Return a deduplicated list of candidate regulation names."""
    if cards is None:
        cards = json.load(open("data/cards.json"))

    # Channel 1: LLM ranking
    user = f"Product characteristics:\n{_facet_summary(sheet)}\n\nRegulations available:\n{_card_summary(cards)}"
    try:
        raw = llm.call_json(SYSTEM, user, model=model, max_tokens=2000)
        llm_candidates = [c["regulation"] for c in raw.get("candidates", []) if c.get("regulation") in cards]
    except Exception as e:
        print(f"candidates LLM error: {e}; falling back to empty list")
        llm_candidates = []

    # Channel 2: horizontal triggers
    horizontals = _run_horizontal(sheet, cards)

    # Channel 3: cross-reference expansion
    all_cands = list(dict.fromkeys(llm_candidates + horizontals))  # preserve order, dedup
    all_cands = _cross_expand(all_cands, cards)
    all_cands = list(dict.fromkeys(all_cands))  # dedup again after expansion

    return all_cands


if __name__ == "__main__":
    import sys, json as J
    case = sys.argv[1] if len(sys.argv) > 1 else "cases/dev-rear-lamp"
    from regir.product.ontology import from_dict
    sheet_raw = J.load(open(f"{case.rstrip('/')}/facets.json" if (case + "/facets.json") else "data/facets/dev-rear-lamp.json"))
    import pathlib, os
    # Try data/facets/<casename>.json
    case_name = pathlib.Path(case).name
    sheet_raw = J.load(open(f"data/facets/{case_name}.json"))
    sheet = {k: v for k, v in sheet_raw.items()}  # keep as plain dict (predicates.py reads it)
    cards = J.load(open("data/cards.json"))
    cands = generate(sheet, cards)
    print("Candidates:", cands)
