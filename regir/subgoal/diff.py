"""Sub-goal, deterministic half: align old/new paragraph trees and compute word-level diffs.
Candidate generator tuned for RECALL; an LLM judge later decides 'materially changed' and writes new_text."""
from __future__ import annotations
import re, difflib, collections
from regir.ingest.parse import parse_pdf, norm_label


def words(t: str) -> list[str]:
    return re.sub(r"\s+", " ", t).split()


def body(node) -> str:
    """Node text without its own leading label token, so renumbering alone is not a change."""
    return re.sub(r"^\s*\S+\s+", "", node.text, count=1)


def word_diff(old: str, new: str):
    a, b = words(old), words(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = [(tag, " ".join(a[i1:i2]), " ".join(b[j1:j2])) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
    return sm.ratio(), ops


def reason(ops) -> str:
    parts = []
    for tag, o, n in ops[:6]:
        if tag == "replace": parts.append(f"'{o}' became '{n}'")
        elif tag == "delete": parts.append(f"'{o}' was removed")
        elif tag == "insert": parts.append(f"'{n}' was added")
    return "; ".join(parts) + ("." if parts else "")


def align(old_nodes, new_nodes, min_sim=0.6):
    """label match first; then similarity match for the rest (handles renumbering, e.g. 6.5 -> 6.5.2)."""
    new_by = collections.defaultdict(list)
    for n in new_nodes: new_by[norm_label(n.label)].append(n)
    pairs, used, left_old = [], set(), []
    for o in old_nodes:
        c = [n for n in new_by.get(norm_label(o.label), []) if id(n) not in used]
        if c: pairs.append((o, c[0])); used.add(id(c[0]))
        else: left_old.append(o)
    left_new = [n for n in new_nodes if id(n) not in used]
    for o in left_old:
        best, bs = None, 0.0
        for n in left_new:
            if id(n) in used or len(words(body(o))) < 5: continue
            s = difflib.SequenceMatcher(None, words(body(o)), words(body(n)), autojunk=False).quick_ratio()
            if s > bs: best, bs = n, s
        if best is not None and bs >= min_sim and difflib.SequenceMatcher(None, words(body(o)), words(body(best)), autojunk=False).ratio() >= min_sim:
            pairs.append((o, best)); used.add(id(best))
        else: pairs.append((o, None))
    added = [n for n in new_nodes if id(n) not in used]
    return pairs, added


def run(old_pdf, new_pdf):
    on, nn = parse_pdf(old_pdf), parse_pdf(new_pdf)
    pairs, added = align(on, nn)
    changed, removed = [], []
    for o, n in pairs:
        if n is None: removed.append(o); continue
        ratio, ops = word_diff(body(o), body(n))
        if ops: changed.append((o, n, ratio, ops))
    return on, nn, changed, removed, added
