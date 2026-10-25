"""A6: compile regulatory scope and inline conditions into predicate DSL.

This pass is product-agnostic: it sees one compiled atom and its regulatory
heading context, but never the product being evaluated. Every predicate carries
source evidence so later decisions can be audited.
"""
from __future__ import annotations

import re
import argparse
import json
import pathlib
from typing import Any

from regir import llm
from regir.product.ontology import FACET_SCHEMA

OPS = {"eq", "ne", "in", "not_in", "has", "lacks", "truthy", "falsy", "gte", "lte"}

SYSTEM = """You compile applicability conditions from one regulatory obligation.
You receive its verbatim source quote, self-contained requirement text, and heading path.
Do not use or imagine any product. Extract only conditions that determine WHEN or TO WHAT
the obligation applies; do not turn the required performance itself into a condition.

Use only the supplied facet names and operators. Preserve AND/OR/NOT structure. If a
condition cannot be represented faithfully, use {"free": "verbatim condition"}.
For every predicate return a short evidence phrase copied verbatim from the quote or heading path.
Heading-derived predicates go in `inherited`; quote-derived predicates go in `conditions`.
Return JSON only:
{"conditions":[{"predicate": {...}, "evidence":"..."}],
 "inherited":[{"predicate": {...}, "evidence":"..."}]}"""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _grounded(evidence: str, source: str) -> bool:
    return len(_norm(evidence)) >= 3 and _norm(evidence) in _norm(source)


def valid_predicate(pred: Any) -> bool:
    """Validate the recursive predicate DSL without evaluating it."""
    if not isinstance(pred, dict) or not pred:
        return False
    structural = [k for k in ("all", "any", "not", "free") if k in pred]
    if structural:
        if len(structural) != 1:
            return False
        key = structural[0]
        if key in ("all", "any"):
            return isinstance(pred[key], list) and bool(pred[key]) and all(valid_predicate(p) for p in pred[key])
        if key == "not":
            return valid_predicate(pred[key])
        return isinstance(pred[key], str) and bool(pred[key].strip())
    facet, op = pred.get("facet"), pred.get("op")
    if facet not in FACET_SCHEMA or op not in OPS:
        return False
    return op in {"truthy", "falsy"} or "value" in pred


def compile_atom(atom: dict, model: str = llm.BULK, fake=None) -> dict:
    """Return a copy of ``atom`` with grounded ``conditions`` and ``inherited``."""
    chain = atom.get("chain") or []
    heading_source = " > ".join(chain)
    quote_source = atom.get("quote", "")
    facets = "\n".join(f"- {name}: {meta['desc']}" for name, meta in FACET_SCHEMA.items())
    user = (
        f"Available facets:\n{facets}\n\n"
        f"Heading path:\n{heading_source or '(none)'}\n\n"
        f"Verbatim quote:\n{quote_source}\n\n"
        f"Requirement text:\n{atom.get('text', '')}"
    )
    raw = llm.call_json(SYSTEM, user, model=model, max_tokens=3000, fake=fake)

    out = dict(atom)
    for field, source in (("conditions", quote_source), ("inherited", heading_source)):
        accepted = []
        for item in raw.get(field, []):
            if not isinstance(item, dict):
                continue
            pred, evidence = item.get("predicate"), item.get("evidence", "")
            if valid_predicate(pred) and _grounded(evidence, source):
                accepted.append({"predicate": pred, "evidence": evidence.strip()})
        out[field] = accepted
    return out


def compile_file(
    atoms_path: str | pathlib.Path,
    out_path: str | pathlib.Path | None = None,
    *,
    model: str = llm.BULK,
    workers: int = 8,
    fake=None,
) -> list[dict]:
    """Compile every atom in a JSONL file and persist enriched JSONL."""
    atoms_path = pathlib.Path(atoms_path)
    atoms = [json.loads(line) for line in atoms_path.read_text().splitlines() if line.strip()]
    compiled = llm.pmap(lambda atom: compile_atom(atom, model=model, fake=fake), atoms, workers=workers)
    target = pathlib.Path(out_path) if out_path else atoms_path.with_name(atoms_path.stem + ".compiled.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(json.dumps(atom, ensure_ascii=False) + "\n" for atom in compiled))
    return compiled


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile atom applicability conditions")
    parser.add_argument("atoms", help="input atoms JSONL")
    parser.add_argument("--out", help="output compiled JSONL")
    parser.add_argument("--model", default=llm.BULK)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    result = compile_file(args.atoms, args.out, model=args.model, workers=args.workers)
    print(f"compiled {len(result)} atoms")

