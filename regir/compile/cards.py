"""A7 (deterministic part): regulation cards = title, scope text, supersession links, cross-reference graph.
No LLM, no product knowledge. Output: data/cards.json"""
from __future__ import annotations
import json, re, glob, collections
from regir.ingest.parse import parse_pdf

REF_RE = re.compile(r"UN\s+Regulation(?:s)?\s+(?:No\.?\s*)?(\d+[A-Z]?)|UN\s+GTR\s*(?:No\.?\s*)?(\d+)", re.I)
CEASE_RE = re.compile(r"(cease to grant approvals|shall cease to grant|no longer be (?:granted|required)|replac(?:e|ed|es)\b|supersed)", re.I)


SCOPE_HEAD_RE = re.compile(r"(?im)^\s*(?:\d+\.?\s*)?(?:scope(?:\s+and\s+\w+)?|field of application)\s*$|^\s*(?:\d+\.?\s*)?scope\b(?=\s+[A-Z])")
SCOPE_END_RE = re.compile(r"(?m)^\s*\d+\.?\s+(?:definitions?|application for approval|general|purpose|requirements)\b|(?<=\s)\d+\.\s+(?:Definitions?|DEFINITIONS)\b", re.I)


def scope_from_pages(pdf_path: str, max_pages: int = 6) -> str:
    """Heading-text based: handles '1 Scope', 'Scope', '1. SCOPE'. Falls back to '' if not found."""
    import pymupdf
    d = pymupdf.open(pdf_path)
    txt = "\n".join(pg.get_text() for pg in list(d)[:max_pages])
    txt = re.sub(r"(?m)^UN\s+(?:R|GTR)\s?\d+\w*,\s*version.*\|\s*page\s+\d+\s+of\s+\d+\s*$", "", txt)
    for m in SCOPE_HEAD_RE.finditer(txt):
        rest = txt[m.start():m.start() + 2500]
        e = SCOPE_END_RE.search(rest, 12)
        body = (rest[:e.start()] if e else rest[:1800]).strip()
        if len(body) > 40: return " ".join(body.split())
    return ""


def scope_text(nodes) -> str:
    """Body section 1 up to section 2: choose the occurrence with the longest text (skips table-of-contents hits)."""
    best = ""
    idx = [i for i, n in enumerate(nodes) if n.label == "1" and n.annex is None]
    for i in idx:
        buf = []
        for n in nodes[i:i + 40]:
            if n.label == "2" and n.annex is None: break
            buf.append(n.text)
        t = "\n".join(buf).strip()
        if len(t) > len(best): best = t[:3000]
    return best


def supersession(full_text: str, self_id: str) -> list[dict]:
    """Sentences near a 'cease to grant approvals / replaces' phrase that mention another UN Regulation."""
    out = []
    for m in CEASE_RE.finditer(full_text):
        win = full_text[max(0, m.start() - 350): m.end() + 250].replace("\n", " ")
        for r in REF_RE.finditer(win):
            ref = "UN R" + (r.group(1) or r.group(2)).upper() if r.group(1) else "UN GTR " + r.group(2)
            if ref.replace(" ", "") != self_id.replace(" ", ""):
                out.append({"ref": ref, "evidence": win[:420]})
    seen, res = set(), []
    for o in out:
        if o["ref"] not in seen: seen.add(o["ref"]); res.append(o)
    return res


def build(index_path="regulations/index.json", pdf_root="regulations/pdf"):
    index = json.load(open(index_path))
    cards, mentions = {}, collections.defaultdict(set)
    for r in index:
        reg = r["regulation"]; key = reg.replace(" ", "_")
        base = next(v for v in r["versions"] if v["role"] == "base")
        nodes = parse_pdf(f"{pdf_root}/{key}/base/{key}_base.pdf")
        full = "\n".join(n.text for n in nodes)
        refs = collections.Counter()
        for m in REF_RE.finditer(full):
            t = ("UN R" + m.group(1).upper()) if m.group(1) else ("UN GTR " + m.group(2))
            if t.replace(" ", "") != reg.replace(" ", ""): refs[t] += 1
        for t in refs: mentions[t].add(reg)
        cards[reg] = {"regulation": reg, "title": r["title"], "base_version": base["version_label"],
                      "has_latest": any(v["role"] == "latest" for v in r["versions"]),
                      "pages": max(n.page_end for n in nodes), "nodes": len(nodes),
                      "scope": scope_from_pages(f"{pdf_root}/{key}/base/{key}_base.pdf") or scope_text(nodes), "supersession_hints": supersession(full, reg),
                      "cites": dict(refs.most_common(12))}
    for reg, c in cards.items():
        c["cited_by_n_regs"] = len(mentions.get(reg, ()))
    return cards


if __name__ == "__main__":
    import os
    os.makedirs("data", exist_ok=True)
    cards = build()
    json.dump(cards, open("data/cards.json", "w"), indent=1, ensure_ascii=False)
    print(len(cards), "cards -> data/cards.json")
