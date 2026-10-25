"""B: Product formaliser — spec.md text → facet sheet.
Product-agnostic: the prompt uses only abstract facet descriptions, no product-specific hints.
Usage:
    python -m regir.product.extract_text cases/dev-rear-lamp/spec.md
"""
from __future__ import annotations
import json, pathlib, sys
from regir import llm
from regir.product.ontology import (
    FACET_SCHEMA, ASSUMED_DEFAULTS, FacetValue, empty_sheet, to_dict
)

# ---------- prompt -----------------------------------------------------------

_FACET_LINES = "\n".join(
    f'  "{k}": {meta["desc"]}  (type: {meta["type"]})'
    for k, meta in FACET_SCHEMA.items()
)

SYSTEM = f"""You are a product classification expert for automotive and vehicle regulations.
Given a product specification, extract a structured facet sheet with these fields:

{_FACET_LINES}

Rules:
1. For each facet, output: {{"value": ..., "status": "known"|"assumed"|"unknown", "evidence": "spec line N: 'exact quote'"}}
2. "known" = explicitly stated in the spec. "assumed" = reasonable default you supply; say why. "unknown" = cannot determine.
3. For list-type facets, always output a JSON array even if one item.
4. For bool-type facets, output true or false (JSON boolean).
5. "function.set" values must be from: signalling, illumination, conspicuity, braking, steering, restraint, impact-protection, pedestrian-protection, sensing, communication, structural, sealing, thermal.
6. "product.kind_path" uses ' > ' as separator, most general first: e.g. 'lighting > lamp > rear-lamp' or 'body > bumper-system > front-bumper'.
7. "part.list" entries are strings like "outer lens: light transmission and colour definition".
8. Never invent facts not in the spec for "known" items. If something is clearly implied (e.g. 'LED modules' implies has_electronics=true), mark it "known".

Return ONLY valid JSON: {{"facets": {{ ... each facet key ... }}}}"""


def _user_msg(spec_text: str) -> str:
    return f"Product specification:\n\n{spec_text}"


# ---------- post-processing --------------------------------------------------

def _apply_assumptions(sheet: dict[str, FacetValue]) -> dict[str, FacetValue]:
    """Fill unknown facets with ASSUMED_DEFAULTS and mark them 'assumed'."""
    for k, default in ASSUMED_DEFAULTS.items():
        if sheet[k].status == "unknown":
            sheet[k] = FacetValue(
                value=default, status="assumed",
                evidence=f"assumed: default value '{default}' used (not found in spec)"
            )
    return sheet


def _verify_known_evidence(spec_text: str, sheet: dict[str, FacetValue]) -> dict[str, FacetValue]:
    """Downgrade unsupported ``known`` facts instead of silently trusting them."""
    import re
    lines = spec_text.splitlines()
    pattern = re.compile(r"spec line\s+(\d+)\s*:\s*['\"](.+?)['\"]\s*$", re.I)
    for key, facet in list(sheet.items()):
        if facet.status != "known":
            continue
        match = pattern.search(facet.evidence or "")
        supported = False
        if match:
            line_no, quote = int(match.group(1)), match.group(2)
            if 1 <= line_no <= len(lines):
                supported = " ".join(quote.split()).casefold() in " ".join(lines[line_no - 1].split()).casefold()
        if not supported:
            sheet[key] = FacetValue(
                value=facet.value,
                status="unknown",
                evidence=f"unverified model claim: {facet.evidence or '(no evidence)'}",
            )
    return sheet


def extract(
    spec_path: str | pathlib.Path,
    model: str = llm.STRONG,
    *,
    assume_defaults: bool = False,
) -> dict[str, FacetValue]:
    """Parse spec.md → facet sheet. Returns dict[facet_name, FacetValue]."""
    spec_text = pathlib.Path(spec_path).read_text()
    raw = llm.call_json(SYSTEM, _user_msg(spec_text), model=model, max_tokens=4000)

    sheet = empty_sheet()
    facets_raw = raw.get("facets", raw)  # tolerate missing wrapper

    for k, v in facets_raw.items():
        if k not in sheet:
            continue  # ignore unknown keys
        if isinstance(v, dict) and "value" in v:
            sheet[k] = FacetValue(
                value=v["value"],
                status=v.get("status", "unknown"),
                evidence=v.get("evidence", ""),
            )
        else:
            sheet[k] = FacetValue(value=v, status="known", evidence="(inline)")

    _verify_known_evidence(spec_text, sheet)
    if assume_defaults:
        _apply_assumptions(sheet)
    return sheet


# ---------- CLI / test -------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="cases/dev-rear-lamp/spec.md")
    parser.add_argument("--assume-defaults", action="store_true")
    args = parser.parse_args()
    path = args.path
    sheet = extract(path, assume_defaults=args.assume_defaults)
    print(f"\n=== Facet sheet for: {path} ===")
    for k, v in sheet.items():
        status_badge = {"known": "✓", "assumed": "~", "unknown": "?"}.get(v.status, " ")
        print(f"  [{status_badge}] {k:<28} = {str(v.value):<40}  ({v.evidence[:60]})")

    # Save to data/facets/<case>.json
    import os
    case = pathlib.Path(path).parent.name
    os.makedirs("data/facets", exist_ok=True)
    out = f"data/facets/{case}.json"
    with open(out, "w") as f:
        json.dump(to_dict(sheet), f, indent=2, ensure_ascii=False)
    print(f"\nSaved -> {out}")
