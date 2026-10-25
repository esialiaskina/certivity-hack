"""
Step 1 — Split pass.

For each paragraph cited in a submission, one LLM call checks whether
any distinct obligations were merged into a single requirement and returns the
missing ones with a verbatim support quote.

"Distinct" means:
- different test condition or severity
- different angle or direction
- different device / category
- each lettered list item (a)/(b)/(c) that imposes something
- each value-row of a table that the expert would list separately

No gold paragraph numbers are used; this logic applies to any product.

Usage:
    python -m regir.upgrade.split_pass \\
        --submission _team/runs/rearlamp-v7b/submission.json \\
        --expected   cases/dev-rear-lamp/expected.json \\
        --out        submissions/split-test.json
"""
from __future__ import annotations
import argparse, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_team" / "src"))

import pipeline as rp
import reqagent
from regparse import Corpus

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
SPLIT_SYSTEM = """You review requirements extracted from a single paragraph of a UN Regulation.
Your task is GRANULARITY CHECKING: the expert who created the gold standard writes
ONE requirement per distinct test condition. The extractor may have bundled several
into one. You must generate the individual requirements that are MISSING.

GRANULARITY RULES (apply all of them):
1. TABLE ROW RULE: If the paragraph contains a table where each row defines a different
   test condition (e.g. different pulse number, frequency band, voltage level, angle, lamp
   category, colour coordinate bound), the expert writes one requirement PER ROW.
   If an existing requirement bundles multiple rows into a single text ("Pulse 1: X; Pulse 2a: Y;
   Pulse 2b: Z"), each row that does NOT have its own dedicated requirement is MISSING.
   Generate one requirement per missing row, quoting its specific values verbatim.

2. DIRECTION RULE: If the paragraph specifies requirements for multiple directions or axes
   (e.g. horizontal AND vertical angles, or inward AND outward visibility), each direction
   is a SEPARATE requirement. If the existing requirements only cover one direction, the
   other direction(s) are missing.

3. LIST ITEM RULE: If the paragraph has lettered list items (a), (b), (c) each imposing
   a distinct obligation, each item is a separate requirement.

4. CATEGORY RULE: If the paragraph imposes different obligations depending on device category,
   function class or system voltage (12 V vs 24 V, M1 vs N1, etc.) and these have different
   pass/fail criteria, each variant is a separate requirement.

Do NOT generate:
  * requirements for test SETUP or PROCEDURE (how the lab does the test)
  * requirements that are already fully expressed by one of the already-written requirements
  * definitions, purely informative statements, or applicant/approval-body obligations

If nothing is missing, return an empty list."""

SPLIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["missing"],
    "properties": {
        "missing": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "verbatim_quote", "why_distinct"],
                "properties": {
                    "text": {"type": "string"},
                    "verbatim_quote": {"type": "string"},
                    "why_distinct": {"type": "string"},
                },
            },
        }
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_table_suffix(para: str) -> str:
    return re.sub(r"\. Table.*$", "", para).strip()


def _node_key_from_para(para: str, nodes_by_label: dict):
    base = _strip_table_suffix(para)
    return nodes_by_label.get(base)


def _should_check(node, submitted_count: int) -> bool:
    """Heuristic: run the split call only when there is real risk of merging."""
    if submitted_count >= 2:
        return True                        # already multiple reqs — worth checking
    text = node.text or ""
    if "|" in text and re.search(r"\|\s*[-\d\+]", text):
        return True                        # has embedded table rows with values
    # Look for list markers or table delimiters in raw text
    if re.search(r"\|\s*[-\d]", text):
        return True                        # looks like a table row
    if re.search(r"\(\s*[a-f]\s*\)", text, re.IGNORECASE):
        return True                        # has lettered list items
    if len(text) > 600:
        return True                        # long paragraph
    return False


def _render_node(n) -> str:
    """Return the rendered text of a parsed node (same format as reqagent.render)."""
    d = {**asdict(n), "id": "n0"}
    return reqagent.render(d)


# ---------------------------------------------------------------------------
# Core split call
# ---------------------------------------------------------------------------

def split_one(
    reg: str,
    node,
    existing_reqs: list[dict],
    tag: str,
) -> list[dict]:
    """Ask the LLM what obligations are missing from `existing_reqs` in this node."""
    have = "\n".join(
        f"- [{r['id']}] {r['text']}" for r in existing_reqs
    ) or "(none yet)"

    user_text = (
        f"## Paragraph text\n\n{_render_node(node)}\n\n"
        f"## Requirements already extracted from this paragraph\n\n{have}"
    )
    res = rp.call_json(
        SPLIT_SYSTEM,
        [{"type": "text", "text": user_text}],
        SPLIT_SCHEMA,
        max_tokens=8000,
        tag=tag,
    )
    return res.get("missing", [])


# ---------------------------------------------------------------------------
# Run split pass over a full submission
# ---------------------------------------------------------------------------

def run_split_pass(
    sub: dict,
    corpus: Corpus | None = None,
    workers: int = 8,
) -> tuple[list[dict], list[dict]]:
    """
    Given a submission dict, return (new_reqs, skipped) where new_reqs are
    the extra requirements the split pass discovered, ready to be appended
    before final renumbering.

    new_reqs items: {"text", "source": {...}, "verbatim_quote", "why_distinct"}
    """
    if corpus is None:
        corpus = Corpus(ROOT / "_team" / "data" / "pdf")

    # Group submitted reqs by (reg, base_para)
    by_node: dict[tuple[str, str], list[dict]] = {}
    for r in sub["requirements"]:
        reg = r["source"]["regulation"]
        base = _strip_table_suffix(r["source"]["paragraph"])
        by_node.setdefault((reg, base), []).append(r)

    # Build lookup: (reg, label) -> Node
    node_lookup: dict[tuple[str, str], object] = {}
    for reg in set(r for r, _ in by_node):
        key = (reg, "base")
        if key not in corpus.by_reg:
            continue
        for n in corpus.by_reg[key]:
            node_lookup[(reg, n.label)] = n

    # Build job list
    jobs = []
    skipped = []
    for (reg, para), reqs in sorted(by_node.items()):
        node = node_lookup.get((reg, para))
        if node is None:
            skipped.append({"reg": reg, "para": para, "reason": "node not found"})
            continue
        if not _should_check(node, len(reqs)):
            skipped.append({"reg": reg, "para": para, "reason": "heuristic skip"})
            continue
        jobs.append((reg, para, node, reqs))

    print(f"split_pass: {len(jobs)} paragraphs to check ({len(skipped)} skipped by heuristic)")

    # Run in parallel
    new_reqs: list[dict] = []
    lock_results: list[tuple] = [None] * len(jobs)

    def _one(i):
        reg, para, node, reqs = jobs[i]
        safe_tag = f"SP2_{reg.replace(' ', '_')}_{para.replace(' ', '_')[:30]}"
        missing = split_one(reg, node, reqs, safe_tag)
        return i, reg, para, node, missing

    with ThreadPoolExecutor(workers) as pool:
        for i, reg, para, node, missing in pool.map(_one, range(len(jobs))):
            for m in missing:
                new_reqs.append({
                    "text": m["text"].strip()[:2000],
                    "source": {
                        "regulation": reg,
                        "version": node.version,
                        "page": node.page_start,
                        "paragraph": para,
                    },
                    "verbatim_quote": m.get("verbatim_quote", ""),
                    "why_distinct": m.get("why_distinct", ""),
                    "_pass": "split",
                })

    print(f"split_pass: found {len(new_reqs)} new candidate requirements")
    return new_reqs, skipped


# ---------------------------------------------------------------------------
# Merge + evaluate
# ---------------------------------------------------------------------------

def merge_and_score(
    original_sub: dict,
    new_reqs: list[dict],
    out_path: Path,
    expected_path: Path | None,
    run_dir: Path | None = None,
) -> dict:
    """Append new_reqs to the original submission, renumber, write out_path, score."""
    reqs = list(original_sub["requirements"]) + [
        {
            "id": f"R-{len(original_sub['requirements']) + i + 1:04d}",
            "text": r["text"],
            "source": {
                "regulation": r["source"]["regulation"],
                "version": r["source"]["version"],
                "page": r["source"]["page"],
                "paragraph": r["source"]["paragraph"],
            },
        }
        for i, r in enumerate(new_reqs)
    ]
    sub_new = {**original_sub, "requirements": reqs}
    out_path.write_text(json.dumps(sub_new, indent=1, ensure_ascii=False))
    print(f"Wrote {len(reqs)} requirements to {out_path}")

    if expected_path and expected_path.exists():
        if run_dir is None:
            run_dir = out_path.parent
        import judge as jdg
        J = jdg.judge(sub_new, json.loads(expected_path.read_text()), run_dir)
        print(f"Judge: F2={J['summary']['f2']:.3f} P={J['summary']['precision']:.3f} R={J['summary']['recall']:.3f}")
        return J
    return {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submission", default="_team/runs/rearlamp-v7b/submission.json")
    ap.add_argument("--expected",   default="cases/dev-rear-lamp/expected.json")
    ap.add_argument("--out",        default="submissions/split-test.json")
    ap.add_argument("--workers",    type=int, default=8)
    ap.add_argument("--dry-run",    action="store_true", help="print job counts only, no API calls")
    a = ap.parse_args(argv)

    reqagent.load_env()
    sub = json.loads(Path(a.submission).read_text())
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    corpus = Corpus(ROOT / "_team" / "data" / "pdf")

    if a.dry_run:
        # Count jobs without calling the LLM
        by_node: dict[tuple[str, str], list[dict]] = {}
        for r in sub["requirements"]:
            reg = r["source"]["regulation"]
            base = _strip_table_suffix(r["source"]["paragraph"])
            by_node.setdefault((reg, base), []).append(r)
        node_lookup = {}
        for reg in set(r for r, _ in by_node):
            key = (reg, "base")
            if key not in corpus.by_reg:
                continue
            for n in corpus.by_reg[key]:
                node_lookup[(reg, n.label)] = n
        will_check, will_skip = 0, 0
        for (reg, para), reqs in by_node.items():
            node = node_lookup.get((reg, para))
            if node and _should_check(node, len(reqs)):
                will_check += 1
            else:
                will_skip += 1
        print(f"Dry run: {will_check} API calls needed, {will_skip} skipped")
        return

    new_reqs, skipped = run_split_pass(sub, corpus, a.workers)

    exp_path = Path(a.expected) if a.expected else None
    run_dir = Path(a.out).parent / "split_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save new candidates separately for inspection
    (run_dir / "split_candidates.json").write_text(
        json.dumps(new_reqs, indent=1, ensure_ascii=False)
    )

    merge_and_score(sub, new_reqs, out_path, exp_path, run_dir)


if __name__ == "__main__":
    main()
