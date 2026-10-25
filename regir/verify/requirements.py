"""Mechanical verification for compiled atoms and final requirements."""
from __future__ import annotations

import hashlib
import re

from regir.compile.atomize import grounded
from regir.ingest.parse import norm_label

NEGATION = re.compile(r"\b(?:no|not|never|without|prohibited|unless)\b", re.I)
MODAL = re.compile(r"\b(?:shall|must|may|should|required|permitted|allowed)\b", re.I)
NUMBER = re.compile(r"(?<![A-Za-z])(?:\d+(?:[.,]\d+)?(?:\s*(?:%|°C|°|mm|cm|m|km/h|V|A|Hz|N|cd))?)")


def _norm(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _anchors(pattern: re.Pattern, text: str) -> set[str]:
    return {_norm(x) for x in pattern.findall(text or "")}


def verify_atom(atom: dict, nodes: list, expected_version: str) -> dict:
    """Verify source identity, quote grounding and semantic-anchor preservation."""
    errors, warnings = [], []
    label = norm_label(atom.get("paragraph", ""))
    matches = [n for n in nodes if norm_label(n.label) == label]
    node = matches[0] if matches else None

    if node is None:
        errors.append("paragraph does not exist in parsed base regulation")
    else:
        page = atom.get("page")
        if not isinstance(page, int) or not node.page_start <= page <= node.page_end:
            errors.append(f"page {page!r} outside paragraph span {node.page_start}-{node.page_end}")
        if not grounded(atom.get("quote", ""), node.text):
            errors.append("quote is not grounded in the cited paragraph")

    if atom.get("version") != expected_version:
        errors.append(f"version {atom.get('version')!r} is not base version {expected_version!r}")

    text = atom.get("text", "")
    if not isinstance(text, str) or not text.strip():
        errors.append("requirement text is empty")
    elif len(text) > 2000:
        errors.append(f"requirement text exceeds 2000 characters ({len(text)})")

    quote = atom.get("quote", "")
    missing_numbers = sorted(_anchors(NUMBER, quote) - _anchors(NUMBER, text))
    if missing_numbers:
        warnings.append("text omits numeric anchors: " + ", ".join(missing_numbers))
    if NEGATION.search(quote) and not NEGATION.search(text):
        warnings.append("text may omit source negation/exception")
    if MODAL.search(quote) and not MODAL.search(text):
        warnings.append("text may omit source modality")

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def fingerprint(atom: dict) -> str:
    """Stable exact-duplicate key; semantic merging remains a separate reviewed step."""
    raw = "|".join((_norm(atom.get("regulation")), _norm(atom.get("version")),
                    norm_label(atom.get("paragraph", "")), _norm(atom.get("text"))))
    return hashlib.sha256(raw.encode()).hexdigest()

