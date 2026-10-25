"""D: Section-level atom filter — given a selected regulation and the facet sheet,
return which atoms to include.

Strategy (three zones):
  1. GENERAL sections (scope, marking, construction, general provisions, cross-cutting annexes):
     always include all atoms with kept roles.
  2. DEVICE-SPECIFIC sections (e.g. R48 section 6.x per-device subsections):
     include only subtrees whose heading matches a product part or function.
  3. TECHNOLOGY-BRANCH sections (e.g. R10 section 6 ESA vs section 5 vehicle):
     include only the branch matching the product's approval level.

Role filter: drop transitional, definition. Keep others.
"""
from __future__ import annotations
import json, re, pathlib
from regir.select.router import toks, spec_terms, match_headings, subtree

DROP_ROLES = {"transitional", "definition", "informative"}

# Regulation-specific branch gates: (section_prefix, required_facet_predicate)
# If a section prefix matches, only include atoms if the predicate is satisfied.
BRANCH_GATES: list[tuple[str, str, dict]] = [
    # R10: section 6 = ESA/component branch.
    # Include section 6 only for component/ESA products.
    # Section 5 contains BOTH vehicle-level AND ESA-level provisions; include all of it.
    ("6.", "UN R10", {"facet": "product.approval_level", "op": "in", "value": ["component", "ESA", "system", "STU"]}),
]


def _label_prefix(label: str, prefix: str) -> bool:
    """True if label starts with prefix (section numbering aware)."""
    # Normalise: '6.' matches '6', '6.1', '6.10.5' but not '60'
    lbl = label.lstrip("0") or "0"
    return lbl == prefix.rstrip(".") or lbl.startswith(prefix.rstrip(".") + ".")


def _branch_included(atom: dict, reg: str, sheet: dict) -> bool:
    """Check branch gates for this atom's section."""
    from regir.evaluate.predicates import evaluate
    for section_pfx, gate_reg, pred in BRANCH_GATES:
        if gate_reg != reg:
            continue
        if _label_prefix(atom["paragraph"], section_pfx):
            verdict, _, _ = evaluate(pred, sheet)
            if verdict == "false":
                return False  # wrong branch
    return True


def _build_product_terms(sheet: dict) -> list[str]:
    """Extract product part names and function keywords from the facet sheet."""
    terms = []
    # From part.list
    parts = sheet.get("part.list", {})
    pval = (parts.get("value") if isinstance(parts, dict) else parts) or []
    for p in pval:
        name = p.split(":")[0].strip()
        terms.append(name)
    # From function.set
    fns = sheet.get("function.set", {})
    fval = (fns.get("value") if isinstance(fns, dict) else fns) or []
    if isinstance(fval, list):
        terms.extend(fval)
    elif isinstance(fval, str):
        terms.append(fval)
    return terms


def filter_atoms(reg: str, atoms: list[dict], sheet: dict) -> list[dict]:
    """Return the subset of atoms that should be included for this regulation+product."""
    if not atoms:
        return []

    # Build product terms from facet sheet
    product_terms = _build_product_terms(sheet)

    # Load nodes for this regulation to run the section router
    key = reg.replace(" ", "_")
    pdf_path = pathlib.Path(f"regulations/pdf/{key}/base/{key}_base.pdf")
    try:
        from regir.ingest.parse import parse_pdf
        nodes = parse_pdf(str(pdf_path))
        # Find device-specific section headings that match product terms
        matched_sections = match_headings(nodes, product_terms)
        matched_labels = {n.label for n, _ in matched_sections}
        # Build full subtree of matched labels
        matched_subtree_labels: set[str] = set()
        for lbl in matched_labels:
            for n in subtree(nodes, lbl):
                matched_subtree_labels.add(n.label)
    except Exception:
        matched_subtree_labels = set()
        nodes = []

    # Classify each node as general vs device-specific
    # A node is device-specific if it is in a section that has multiple device-subsections
    # (e.g. R48 §6 has 6.1, 6.2, ... 6.22 for different devices).
    # Heuristic: if the section is NOT matched by any product term AND is in a numbered
    # subsection ≥ 2 levels deep in a large section, it's device-specific (exclude).
    # For simplicity: include ALL atoms from general-looking sections and matched device sections.

    # Identify DEVICE-SPECIFIC sub-sections: a section is device-specific if its children
    # are each named after a different device type and SOME match product terms while
    # OTHERS do not. Only filter these; keep everything else.
    #
    # Heuristic: look one level below a large section; if some direct-children headings
    # match product terms and others explicitly match OTHER device names (not in product),
    # treat that parent section as device-gated.
    # We find this by: run match_headings, then see which parent sections have BOTH matched
    # AND unmatched children at the same depth.

    device_gated_parents: set[str] = set()  # labels whose children are per-device
    if nodes and matched_subtree_labels:
        from collections import defaultdict
        # For each node that IS a direct child of a section, record match status
        depth2_sections: dict[str, dict[str, bool]] = defaultdict(dict)
        for n in nodes:
            if n.annex is not None:
                continue
            parts = n.label.split(".")
            if len(parts) == 2:  # e.g. "6.7"
                parent = parts[0]  # "6"
                depth2_sections[parent][n.label] = (n.label in matched_labels)

        for parent, children in depth2_sections.items():
            matched_count = sum(1 for v in children.values() if v)
            total = len(children)
            match_ratio = matched_count / total if total else 0
            # Device-gated: has meaningful match ratio AND un-matched peers AND > 4 children.
            # Low ratio (< 15%) means the section is general provisions where a few headings
            # happen to name devices — don't treat it as device-gated.
            if matched_count > 0 and matched_count < total and total > 4 and match_ratio >= 0.15:
                device_gated_parents.add(parent)

    result = []
    for atom in atoms:
        # 1. Role filter
        if atom.get("role") in DROP_ROLES:
            continue

        # 2. Branch gate (e.g. R10 ESA vs vehicle branch)
        if not _branch_included(atom, reg, sheet):
            continue

        # 3. Section routing
        para = atom["paragraph"]
        # Always include Annex sections
        if "Annex" in para or "annex" in para:
            result.append(atom)
            continue

        # Check if in a device-gated parent section
        top_sec = para.split(".")[0] if "." in para else para
        if top_sec in device_gated_parents:
            # Only include if this atom is in a matched subtree
            if para in matched_subtree_labels:
                result.append(atom)
            # else: belongs to a different device's sub-section → skip
        else:
            # General or non-device section: include
            result.append(atom)

    return result


if __name__ == "__main__":
    import sys, json as J
    reg = sys.argv[1] if len(sys.argv) > 1 else "UN R48"
    case_name = sys.argv[2] if len(sys.argv) > 2 else "dev-rear-lamp"
    key = reg.replace(" ", "_")
    atoms = [J.loads(l) for l in open(f"data/atoms/{key}.jsonl")]
    sheet = J.load(open(f"data/facets/{case_name}.json"))
    kept = filter_atoms(reg, atoms, sheet)
    print(f"{reg}: {len(atoms)} atoms -> {len(kept)} after section filter")
    from collections import Counter
    print("  roles:", dict(Counter(a["role"] for a in kept).most_common()))
    gold_paras = None
    try:
        gold = J.load(open("cases/dev-rear-lamp/expected.json"))
        gold_paras = set(r["source"]["paragraph"] for r in gold["requirements"]
                        if r["source"]["regulation"] == reg)
        hit = sum(1 for a in kept if a["paragraph"] in gold_paras or a["paragraph"].split(". Table")[0] in gold_paras)
        miss = gold_paras - set(a["paragraph"] for a in kept) - set(a["paragraph"].split(". Table")[0] for a in kept)
        print(f"  gold coverage: {len(gold_paras)-len(miss)}/{len(gold_paras)} paragraphs  missed={sorted(miss)}")
    except Exception:
        pass
