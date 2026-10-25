"""A4+A5: node -> atomic obligations with verbatim quote (mechanically verified) and role.
Product-agnostic. Output: data/atoms/<REG>.jsonl"""
from __future__ import annotations
import re, json, os, sys, hashlib
from regir.ingest.parse import parse_pdf, norm_label
from regir import llm

CUE = re.compile(r"\b(shall|must|should|may not|may|is required|are required|required to|is prohibited|are prohibited|not be permitted|"
                 r"only if|only when|only in|mandatory|has to|have to|not exceed|at least|at most|minimum|maximum|not be less|not be more|"
                 r"not less than|not more than|permitted|allowed|in accordance with|provided that)\b", re.I)
ROLES = ["performance", "construction", "marking", "test_condition", "procedure", "conformity", "transitional", "definition", "informative"]

SYSTEM = """You convert one paragraph of a UN vehicle regulation into atomic engineering obligations.
Rules:
1. One atom = ONE obligation: one subject + its condition(s) + one constraint. Split paragraphs that contain several independent constraints
   (different subjects, different limits, enumerations (a)/(b) with different constraints). Do not split a single sentence just because it has "and" between two parts of one constraint.
2. `quote` must be a VERBATIM contiguous excerpt of the paragraph text (copy exactly, including numbers and units). Never paraphrase inside `quote`.
3. `text` is the obligation rewritten as a self-contained sentence an engineer can act on: copy numbers, units, conditions and scope exactly; resolve "it/they/this" using the context path; do NOT add facts that are not in the paragraph.
4. `role` is one of: performance (measurable limits/behaviour), construction (design/build requirement), marking (approval marks, labels), test_condition (how a test must be done), procedure (application/approval/administrative duty), conformity (conformity of production), transitional (dates/validity), definition, informative (no obligation).
5. If the paragraph contains no obligation, return {"atoms": []}.
Return JSON only: {"atoms":[{"quote":"...","text":"...","role":"...","modality":"shall|shall_not|only_if|may|should"}]}"""


ERRORS: list[str] = []


def _norm(s: str) -> str:
    s = s.replace("­", "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"-\n\s*", "-", s)                                  # collapse line-breaks after hyphens (keeps the hyphen for both word-wrap and identifiers)
    return re.sub(r"\s+", " ", s).strip().casefold()


def grounded(quote: str, node_text: str) -> bool:
    q = _norm(quote)
    return len(q) >= 12 and q in _norm(node_text)


def heading_chain(label: str, titles: dict) -> list[str]:
    parts, out = label.split("."), []
    for i in range(1, len(parts)):
        t = titles.get(norm_label(".".join(parts[:i])))
        if t: out.append(t[:90])
    return out


def candidates(nodes):
    return [n for n in nodes if n.label != "front" and len(n.text) > 25 and CUE.search(n.text)]


MAX_TOKENS = 8192  # enough for nodes with 20+ atoms; 4096 was causing truncation

def atomize_node(reg: str, version: str, node, chain: list[str], model=llm.BULK, fake=None):
    user = f"Regulation: {reg}\nContext path: {' > '.join(chain) or '(top level)'}\nParagraph label: {node.label}\n\nParagraph text:\n{node.text[:6000]}"
    for attempt in range(2):
        try:
            data = llm.call_json(SYSTEM, user + ("\n\n(Previous reply had a quote that is not verbatim. Copy quotes exactly.)" if attempt else ""),
                                 model=model, max_tokens=MAX_TOKENS, fake=fake)
        except Exception as e:
            ERRORS.append(f"{type(e).__name__}: {str(e)[:300]}")
            continue
        atoms, bad = [], 0
        for i, a in enumerate(data.get("atoms", [])):
            if not isinstance(a, dict) or not a.get("quote") or not a.get("text"): bad += 1; continue
            if not grounded(a["quote"], node.text): bad += 1; continue
            role = a.get("role") if a.get("role") in ROLES else "informative"
            atoms.append({"atom_id": f"{reg.replace(' ', '_')}@{version}#{node.label}/a{i+1}", "regulation": reg, "version": version,
                          "paragraph": node.label, "page": node.page_start, "page_end": node.page_end,
                          "chain": chain, "quote": a["quote"].strip(), "text": a["text"].strip(), "role": role,
                          "modality": a.get("modality", "shall")})
        if not bad: return atoms, 0
        if attempt: return atoms, bad
    return [], 1


def run(reg: str, limit: int | None = None, model=llm.BULK, fake=None):
    key = reg.replace(" ", "_")
    idx = {r["regulation"]: r for r in json.load(open("regulations/index.json"))}
    version = next(v["version_label"] for v in idx[reg]["versions"] if v["role"] == "base")
    nodes = parse_pdf(f"regulations/pdf/{key}/base/{key}_base.pdf")
    titles = {}
    for n in nodes:
        if n.annex is None and n.label != "front": titles.setdefault(norm_label(n.label), re.sub(r"^\S+\s+", "", n.text.split("\n")[0]))
    cand = candidates(nodes)[:limit]
    res = llm.pmap(lambda n: atomize_node(reg, version, n, heading_chain(n.label, titles), model, fake), cand)
    atoms = [a for r, _ in res for a in r]; bad = sum(b for _, b in res)
    os.makedirs("data/atoms", exist_ok=True)
    with open(f"data/atoms/{key}.jsonl", "w") as f:
        for a in atoms: f.write(json.dumps(a, ensure_ascii=False) + "\n")
    if ERRORS:
        from collections import Counter
        print(f"!! {len(ERRORS)} calls failed. Most common errors:")
        for e, c in Counter(ERRORS).most_common(3): print(f"   {c}x {e}")
    print(f"{reg}: {len(cand)} candidate nodes -> {len(atoms)} atoms, {bad} ungrounded/invalid dropped -> data/atoms/{key}.jsonl")
    return atoms


if __name__ == "__main__":
    import argparse; ap = argparse.ArgumentParser()
    ap.add_argument("reg"); ap.add_argument("--limit", type=int); ap.add_argument("--model", default=llm.BULK)
    a = ap.parse_args(); run(a.reg, a.limit, a.model)
