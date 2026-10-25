"""Semantic adjudication for subgoal candidates.

Paragraph diffing proposes candidates for recall; this module decides which
individual old requirements materially changed and extracts genuinely new atoms.
"""
from __future__ import annotations

import difflib
import re

from regir import llm

ORDER_SENSITIVE = {
    "above", "after", "before", "behind", "below", "between", "except",
    "fewer", "following", "front", "greater", "less", "more", "not",
    "only", "preceding", "unless", "until", "without",
}
FUNCTION_WORDS = {
    "a", "an", "and", "as", "at", "be", "both", "by", "during", "for",
    "from", "in", "is", "of", "on", "or", "shall", "should", "than", "the",
    "to", "when", "where", "which", "while", "with",
}

MOD_SYSTEM = """You adjudicate requirement changes between OLD and NEW regulation paragraphs.
Return one decision for every supplied requirement: unchanged, modified, or removed.

Judge the specific obligation, not every surrounding paragraph edit. Reordering, punctuation,
renumbering, grammar and equivalent active/passive phrasing are unchanged. For modified items,
new_text must contain only the materially changed semantic obligation: preserve actor, action,
conditions, exceptions, negation, modal force, numbers, units, direction and cross-references;
omit independent unchanged sibling constraints. old_quote and new_quote must be short verbatim
contiguous excerpts supporting that obligation. A removed item has null new_text/new_quote.

Return JSON only:
{"decisions":[{"requirement_id":"...","decision":"unchanged|modified|removed",
"new_text":null,"old_quote":"...","new_quote":null}]}"""

ADD_SYSTEM = """Extract genuinely NEW engineering obligations from a NEW regulation paragraph.
Compare it with the OLD paragraph when supplied and with already-covered requirements. Do not
emit wording changes already represented by a modified requirement. One output is one semantic
obligation. Preserve actor, condition, exception, negation, modal force, values, units and
cross-references. source_quote must be a verbatim contiguous excerpt of the NEW paragraph.
Return JSON only: {"added":[{"new_text":"...","source_quote":"..."}]}"""


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def pure_reordering_equivalent(a: str, b: str) -> bool:
    wa, wb = _words(a), _words(b)
    if wa == wb or sorted(wa) != sorted(wb) or ORDER_SENSITIVE.intersection(wa):
        return wa == wb
    # A conditional adjunct may move before/after the main clause. Require an
    # explicit conditional marker and an exact cyclic rotation; arbitrary cyclic
    # rotations (which could reverse subject/object roles) remain changes.
    markers = {"when", "while", "during", "if", "where"}
    for marker in markers.intersection(wa):
        ia, ib = wa.index(marker), wb.index(marker)
        if ia != ib:
            for cut in range(1, len(wa)):
                if wa[cut:] + wa[:cut] == wb and (wa[cut] in markers or wa[0] in markers):
                    return True
    ca = [w for w in wa if w not in FUNCTION_WORDS]
    cb = [w for w in wb if w not in FUNCTION_WORDS]
    if not ca:
        return False
    same = sum(i2 - i1 for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(
        None, ca, cb, autojunk=False).get_opcodes() if tag == "equal")
    return same / max(len(ca), len(cb)) >= 0.8


def _grounded(quote: str | None, text: str | None) -> bool:
    if not quote or not text:
        return False
    norm = lambda s: " ".join(s.casefold().split())
    return len(norm(quote)) >= 8 and norm(quote) in norm(text)


def judge_group(old_text: str, new_text: str | None, requirements: list[dict], *, model=llm.STRONG, fake=None) -> list[dict]:
    if new_text is not None and pure_reordering_equivalent(old_text, new_text):
        return [{"requirement_id": r["id"], "decision": "unchanged", "new_text": None,
                 "old_quote": r["text"], "new_quote": None} for r in requirements]
    req_block = "\n".join(f"{r['id']}: {r['text']}" for r in requirements)
    user = f"OLD PARAGRAPH:\n{old_text}\n\nNEW PARAGRAPH:\n{new_text or '(no counterpart)'}\n\nREQUIREMENTS:\n{req_block}"
    try:
        raw = llm.call_json(MOD_SYSTEM, user, model=model, max_tokens=8000, fake=fake)
    except Exception:
        return [{"requirement_id": r["id"], "decision": "unresolved", "new_text": None,
                 "old_quote": "", "new_quote": None} for r in requirements]
    by_id = {r["id"]: r for r in requirements}
    out, seen = [], set()
    for item in raw.get("decisions", []):
        rid, decision = item.get("requirement_id"), item.get("decision")
        if rid not in by_id or rid in seen or decision not in {"unchanged", "modified", "removed"}:
            continue
        if decision == "modified":
            text = item.get("new_text")
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                continue
            if not _grounded(item.get("old_quote"), old_text) or not _grounded(item.get("new_quote"), new_text):
                continue
        elif decision == "removed":
            if not _grounded(item.get("old_quote"), old_text):
                continue
            item = {**item, "new_text": None, "new_quote": None}
        out.append(item); seen.add(rid)
    # Missing/invalid model decisions remain unresolved, never silently removed.
    for rid in by_id.keys() - seen:
        out.append({"requirement_id": rid, "decision": "unresolved", "new_text": None,
                    "old_quote": "", "new_quote": None})
    return out


def extract_added(old_text: str | None, new_text: str, covered: list[str], *, model=llm.BULK, fake=None) -> list[dict]:
    user = (f"OLD PARAGRAPH:\n{old_text or '(new paragraph)'}\n\nNEW PARAGRAPH:\n{new_text}\n\n"
            "ALREADY COVERED:\n" + ("\n".join(f"- {x}" for x in covered) or "(none)"))
    try:
        raw = llm.call_json(ADD_SYSTEM, user, model=model, max_tokens=6000, fake=fake)
    except Exception:
        return []
    out = []
    for item in raw.get("added", []):
        text, quote = item.get("new_text"), item.get("source_quote")
        if isinstance(text, str) and text.strip() and len(text) <= 2000 and _grounded(quote, new_text):
            out.append({"new_text": text.strip(), "source_quote": quote.strip()})
    return out

