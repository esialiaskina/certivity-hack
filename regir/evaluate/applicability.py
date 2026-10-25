"""D: deterministic three-valued applicability with an auditable proof trace."""
from __future__ import annotations

from regir.evaluate.predicates import T, U, evaluate


def evaluate_atom(atom: dict, sheet: dict, *, allow_assumptions: bool = False) -> dict:
    """Evaluate one compiled atom against a product facet sheet.

    Assumption-dependent truth is reported as ``unknown`` by default. Callers may
    opt into an assumption scenario, but the trace always records the assumptions.
    """
    entries = []
    for origin in ("inherited", "conditions"):
        for item in atom.get(origin, []):
            pred = item["predicate"] if "predicate" in item else item
            verdict, assumptions, missing = evaluate(pred, sheet)
            entries.append({
                "origin": origin,
                "predicate": pred,
                "evidence": item.get("evidence", "") if isinstance(item, dict) else "",
                "verdict": verdict,
                "assumptions": assumptions,
                "missing": missing,
            })

    combined = {"all": [e["predicate"] for e in entries]} if entries else {"all": []}
    if entries:
        verdict, assumptions, missing = evaluate(combined, sheet)
    else:
        verdict, assumptions, missing = T, [], []

    effective = verdict
    if verdict == T and assumptions and not allow_assumptions:
        effective = U

    return {
        "atom_id": atom.get("atom_id"),
        "verdict": effective,
        "raw_verdict": verdict,
        "assumptions_used": assumptions,
        "missing_facets": missing,
        "checks": entries,
    }

