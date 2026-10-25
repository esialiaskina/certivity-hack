"""C2: Scope proof — for each candidate regulation, produce a grounded applicability score.
Two independent LLM calls: advocate (argues for applicability) + adversary (argues against).
Final p = weighted combination; quote grounding checked mechanically.
Product-agnostic."""
from __future__ import annotations
import json, re
from regir import llm

ADVOCATE_SYS = """You are a regulatory scope analyst arguing FOR applicability.
Given a product description and a regulation's scope text, identify how the product fits.

IMPORTANT: A regulation applies to a product if it covers the COMPLETE PRODUCT or ANY COMPONENT/PART of it.
For example, if the product contains an electronic sub-assembly, an EMC regulation applies even if the
top-level product is a different type. If the product contains a specialised component, the component-level regulation applies.

Rules:
1. "scope_quotes": 2-4 SHORT verbatim phrases copied EXACTLY from the scope text that show it applies.
2. "branch": which approval branch applies — one of: vehicle, system, component, ESA, STU, not_applicable.
3. "p": probability 0.0-1.0 that this regulation applies to the product or any of its parts.
   Score >= 0.5 if the scope explicitly names the product type or any of its named parts/functions.
4. "reason": one sentence.

Return JSON only:
{"scope_quotes": [...], "branch": "...", "p": 0.0, "reason": "..."}"""

ADVERSARY_SYS = """You are a regulatory scope analyst arguing AGAINST applicability.
Given a product description and a regulation's scope text, find reasons the product might NOT be covered.

Rules:
1. "excluding_quotes": 1-3 SHORT verbatim phrases from the scope that could exclude this product.
   If none exist, return [].
2. "exclusion_p": probability 0.0-1.0 that the product is excluded. 0.0 = no exclusion found.
3. "reason": one sentence.

Return JSON only:
{"excluding_quotes": [...], "exclusion_p": 0.0, "reason": "..."}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\n", " ")).strip().casefold()


def _grounded(quote: str, scope: str) -> bool:
    q = _norm(quote)
    return len(q) >= 8 and q in _norm(scope)


def _facet_summary(sheet: dict) -> str:
    lines = []
    for k, v in sheet.items():
        if k == "part.list":
            continue  # handled separately below
        val = v.get("value") if isinstance(v, dict) else v
        status = v.get("status", "known") if isinstance(v, dict) else "known"
        if val not in (None, [], "unknown", ""):
            lines.append(f"  {k} ({status}): {val}")
    # Include full parts list — critical for component-level regulation matching
    parts = sheet.get("part.list", {})
    pval = parts.get("value") if isinstance(parts, dict) else parts
    if pval:
        for p in pval[:10]:
            lines.append(f"  part: {p}")
    return "\n".join(lines)


def score(reg: str, card: dict, sheet: dict, model: str = llm.BULK) -> dict:
    """Return scoring dict with keys: p, verdict, scope_quotes, excluding_quotes, branch, advocate_reason, adversary_reason."""
    scope = card.get("scope", "")[:2000]
    product_desc = _facet_summary(sheet)
    user = f"Product:\n{product_desc}\n\nRegulation: {reg}\nScope text:\n{scope}"

    # Advocate
    try:
        adv = llm.call_json(ADVOCATE_SYS, user, model=model)
        p_adv = float(adv.get("p", 0.5))
        sq = [q for q in adv.get("scope_quotes", []) if isinstance(q, str) and _grounded(q, scope)]
        branch = adv.get("branch", "component")
        adv_reason = adv.get("reason", "")
    except Exception as e:
        p_adv, sq, branch, adv_reason = 0.5, [], "component", f"advocate error: {e}"

    # Adversary
    try:
        opp = llm.call_json(ADVERSARY_SYS, user, model=model)
        p_excl = float(opp.get("exclusion_p", 0.0))
        eq = [q for q in opp.get("excluding_quotes", []) if isinstance(q, str) and _grounded(q, scope)]
        adv2_reason = opp.get("reason", "")
    except Exception as e:
        p_excl, eq, adv2_reason = 0.0, [], f"adversary error: {e}"

    # Combine: advocate score reduced by exclusion probability.
    # Only boost exclusion if adversary found a quote NOT already used as a scope quote
    # (same quote appearing in both means it's the applicability text, not an exclusion).
    sq_norm = {_norm(q) for q in sq}
    novel_excl = [q for q in eq if _norm(q) not in sq_norm]
    if novel_excl:
        p_excl = max(p_excl, 0.4)  # grounded novel exclusion: strong signal
    p_final = round(p_adv * (1.0 - 0.6 * p_excl), 3)

    verdict = "applies" if p_final >= 0.5 else ("partial" if p_final >= 0.2 else "not")

    return {
        "regulation": reg, "p": p_final, "verdict": verdict, "branch": branch,
        "scope_quotes": sq, "excluding_quotes": eq,
        "advocate_reason": adv_reason, "adversary_reason": adv2_reason,
    }


def score_all(candidates: list[str], cards: dict, sheet: dict, model: str = llm.BULK) -> list[dict]:
    """Score all candidates in parallel."""
    items = [(reg, cards[reg]) for reg in candidates if reg in cards]
    results = llm.pmap(lambda x: score(x[0], x[1], sheet, model), items)
    return sorted(results, key=lambda r: -r["p"])


if __name__ == "__main__":
    import sys, json as J, pathlib
    case_name = sys.argv[1] if len(sys.argv) > 1 else "dev-rear-lamp"
    sheet = J.load(open(f"data/facets/{case_name}.json"))
    cards = J.load(open("data/cards.json"))
    from regir.select.candidates import generate
    cands = generate(sheet, cards)
    print(f"Candidates ({len(cands)}): {cands}")
    results = score_all(cands, cards, sheet)
    print("\nScope proof results:")
    for r in results:
        print(f"  {r['regulation']:12s} p={r['p']:.2f} verdict={r['verdict']:8s} branch={r['branch']:12s} | {r['advocate_reason'][:60]}")
