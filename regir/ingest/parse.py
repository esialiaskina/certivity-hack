"""A1+A2: PDF -> paragraph tree with exact PDF page spans.

Product-agnostic. Page numbers are 1-based PDF page indices (same as the scoring platform).
Node label scheme: "5.3.2.1" in the body; "Annex 8 2.1", "Annex 4 Part 1 1.2", "Annex 9 Appendix 1 3" in annexes
(the scorer normalises case/commas/spaces, so this matches the gold style).
"""
from __future__ import annotations
import re, json
from dataclasses import dataclass, field, asdict
import pymupdf

HEADER_RE = re.compile(r"^UN\s+(?:R|GTR)\s?\d+\w*,\s*version\s+[\d.]+\s*\|\s*page\s+\d+\s+of\s+\d+\s*$", re.I)
# "Annex 8 Testing procedures ...", "Annex 2A Information ...", "Annex 14 (RESERVED)", "Annex 5" alone
ANNEX_RE = re.compile(r"^Annex\s+(\d+[A-Z]?)(?:\s*$|\s+(?=[A-Z(]))(?!\s*[-–—]\s*Appendix)")
APPX_RE = re.compile(r"^Annex\s+(\d+[A-Z]?)\s*[-–—]\s*Appendix\s+(\d+)")
PART_RE = re.compile(r"^Part\s+(\d+)(?:\s*$|\s*[-–—:.]|\s+[A-Z])")
LABEL_DOT_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s+(\S.*)$")      # "5.3.2.1. Text"
LABEL_NODOT_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)*)\s+([A-Z].*)$")  # "6.5 Text" (>=2 parts, uppercase next)


@dataclass
class Node:
    label: str
    page_start: int
    page_end: int
    text: str = ""
    annex: str | None = None
    lines: list = field(default_factory=list, repr=False)

    def finish(self):
        self.text = "\n".join(l for _, l in self.lines).strip()
        self.page_end = self.lines[-1][0] if self.lines else self.page_start
        return self


def _num(annex_id: str) -> int:
    return int(re.match(r"\d+", annex_id).group())


def _match_label(line: str):
    m = LABEL_DOT_RE.match(line) or LABEL_NODOT_RE.match(line)
    return (m.group(1), m.group(2)) if m else None


def parse_pdf(path: str) -> list[Node]:
    doc = pymupdf.open(path)
    nodes: list[Node] = []
    cur: Node | None = None
    annex: str | None = None   # current annex id, e.g. "8" or "2A"
    sub: str | None = None     # "Part 1" / "Appendix 2" inside an annex

    def start(label, pno, line):
        nonlocal cur
        if cur: nodes.append(cur.finish())
        cur = Node(label, pno, pno, annex=annex); cur.lines.append((pno, line))

    for pno, page in enumerate(doc, start=1):
        for raw in page.get_text().split("\n"):
            line = raw.strip()
            if not line or HEADER_RE.match(line):
                continue
            ma = APPX_RE.match(line)
            if ma and annex is not None:
                annex, sub = ma.group(1), f"Appendix {ma.group(2)}"
                start(f"Annex {annex} {sub}", pno, line); continue
            ma = ANNEX_RE.match(line)
            # accept only the next annex in sequence (first must be Annex 1): guards against body cross-references
            if ma and ((annex is None and _num(ma.group(1)) == 1) or
                       (annex is not None and _num(annex) <= _num(ma.group(1)) <= _num(annex) + 2)):
                annex, sub = ma.group(1), None
                start(f"Annex {annex}", pno, line); continue
            if annex and (mp := PART_RE.match(line)):
                sub = f"Part {mp.group(1)}"
                start(f"Annex {annex} {sub}", pno, line); continue
            ml = _match_label(line)
            if ml:
                lbl = ml[0]
                full = lbl if not annex else (f"Annex {annex} {sub} {lbl}" if sub else f"Annex {annex} {lbl}")
                start(full, pno, line); continue
            if cur is None:
                cur = Node("front", pno, pno)
            cur.lines.append((pno, line))
    if cur: nodes.append(cur.finish())
    return nodes


def norm_label(s: str) -> str:
    """Same spirit as tools/score_local.py::_paragraph_key."""
    s = str(s or "").casefold().replace("§", " ")
    s = re.sub(r"[,;:()\[\]]", " ", s)
    s = re.sub(r"(?<![0-9a-z])\.|\.(?![0-9a-z])", " ", s)
    s = " ".join(s.split())
    return re.sub(r"^(paragraphs?|para|par|section|clause)\s+", "", s)


if __name__ == "__main__":
    import sys
    ns = parse_pdf(sys.argv[1])
    print(len(ns), "nodes")
    json.dump([{k: v for k, v in asdict(n).items() if k != "lines"} for n in ns], open(sys.argv[2], "w"), indent=1)
