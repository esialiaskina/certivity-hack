"""Three-valued predicate evaluation over a facet sheet (deterministic; no LLM).
Facet sheet: {"vehicle.category": {"value": "M1", "status": "known|assumed|unknown", "evidence": "..."}, ...}
Predicate:   {"facet": f, "op": eq|ne|in|not_in|has|lacks|truthy|falsy|gte|lte, "value": v}
             {"all": [...]} | {"any": [...]} | {"not": p} | {"free": "text"}   ('free' is always UNKNOWN here: LLM judge handles it)
Result: (verdict in {'true','false','unknown'}, assumptions_used, missing_facets)"""
from __future__ import annotations

T, F, U = "true", "false", "unknown"


def _get(sheet, facet):
    f = sheet.get(facet)
    if not f or f.get("status", "known") == "unknown" or f.get("value") in (None, "", "unknown"): return None, None
    return f["value"], f.get("status", "known")


def _as_list(v): return v if isinstance(v, (list, tuple, set)) else [v]


def evaluate(pred, sheet):
    assum, miss = [], []

    def ev(p):
        if "all" in p:
            rs = [ev(q) for q in p["all"]]
            return F if F in rs else (U if U in rs else T)
        if "any" in p:
            rs = [ev(q) for q in p["any"]]
            return T if T in rs else (U if U in rs else F)
        if "not" in p:
            r = ev(p["not"]); return {T: F, F: T, U: U}[r]
        if "free" in p:
            miss.append("free:" + p["free"][:60]); return U
        facet, op, want = p["facet"], p["op"], p.get("value")
        val, status = _get(sheet, facet)
        if val is None: miss.append(facet); return U
        if status == "assumed": assum.append(facet)
        have = _as_list(val)
        if op == "eq": r = str(val).casefold() == str(want).casefold()
        elif op == "ne": r = str(val).casefold() != str(want).casefold()
        elif op == "in": r = any(str(h).casefold() in {str(w).casefold() for w in _as_list(want)} for h in have)
        elif op == "not_in": r = all(str(h).casefold() not in {str(w).casefold() for w in _as_list(want)} for h in have)
        elif op == "has": r = str(want).casefold() in {str(h).casefold() for h in have}
        elif op == "lacks": r = str(want).casefold() not in {str(h).casefold() for h in have}
        elif op == "truthy": r = bool(val) and str(val).casefold() not in ("false", "no", "none")
        elif op == "falsy": r = (not val) or str(val).casefold() in ("false", "no", "none")
        elif op == "gte": r = float(val) >= float(want)
        elif op == "lte": r = float(val) <= float(want)
        else: raise ValueError("unknown op " + op)
        return T if r else F

    verdict = ev(pred) if isinstance(pred, dict) else ev({"all": list(pred)})
    return verdict, sorted(set(assum)), sorted(set(miss))
