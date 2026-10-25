"""Section router (deterministic baseline): prune the paragraph tree by heading titles vs product terms.
Generic: terms come from the spec's own part/function lists; nothing lamp-specific is hard-coded."""
from __future__ import annotations
import re
from regir.ingest.parse import norm_label

STOP = {"the", "of", "and", "for", "a", "an", "with", "to", "in", "on"}


def toks(s: str) -> list[str]:
    s = re.sub(r"[-/]", " ", s.lower())
    s = s.replace("retroreflect", "retro reflect")
    out = []
    for t in re.findall(r"[a-z0-9]+", s):
        if t in STOP: continue
        out.append(re.sub(r"(ing|ors?|s)$", "", t) if len(t) > 5 else t.rstrip("s") if len(t) > 3 else t)
    return out


def spec_terms(spec_md: str) -> list[str]:
    """Bullets under '## Main Parts' and '## Function' (the partner's spec.md layout)."""
    terms = []
    for sec in ("Main Parts", "Function"):
        m = re.search(rf"(?ms)^##\s*{sec}\s*\n(.*?)(?=^##\s|\Z)", spec_md)
        if m:
            for b in re.findall(r"(?m)^\s*[-*]\s*(.+?)\s*$", m.group(1)):
                terms.append(re.sub(r"\(.*?\)", "", b).strip())
    return terms


def heading_title(node) -> str:
    first = node.text.split("\n")[0]
    return re.sub(r"^\S+\s+", "", first)[:90]


def match_headings(nodes, terms, max_title_words=12):
    """Return nodes whose SHORT heading title contains all tokens of some product term."""
    tt = [(t, set(toks(t))) for t in terms if toks(t)]
    hits = []
    for n in nodes:
        if n.label == "front": continue
        title = heading_title(n)
        title_no_parens = re.sub(r"\([^)]*\)", "", title).strip()  # strip (R1, R2, MR) etc.
        if len(title_no_parens.split()) > max_title_words: continue  # a sentence, not a heading
        ts = set(toks(title))
        for term, tset in tt:
            if tset and tset <= ts:
                hits.append((n, term)); break
    return hits


def subtree(nodes, root_label):
    r = norm_label(root_label)
    out = []
    for n in nodes:
        l = norm_label(n.label)
        if l == r or l.startswith(r + "."):
            out.append(n)
    return out
