"""Structural supersession: regulation A is superseded by B when A's own title terms (the device/system it regulates)
are all contained in B's scope text, B is more general (longer scope list) and B is a 'consolidated' successor.
Combined with transitional-clause hints from cards.json. Deterministic, product-agnostic."""
from __future__ import annotations
import re, json

STOP = {"the", "of", "and", "for", "a", "an", "with", "to", "in", "on", "regulation", "vehicle", "vehicles", "systems", "system",
        "devices", "device", "installation", "approval", "equipment", "m1", "n1"}


def stem(t: str) -> str:
    return re.sub(r"(ive|ing|ors?|ion|ers?|s)$", "", t)[:6]


def tset(text: str) -> set[str]:
    text = re.sub(r"[-/]", " ", text.lower())
    return {stem(t) for t in re.findall(r"[a-z]{3,}", text) if t not in STOP}


def containment(cards: dict, min_title_tokens=2, overlap=0.10) -> list[tuple[str, str, float]]:
    out = []
    scopes = {k: tset(v["scope"]) for k, v in cards.items()}
    for a, ca in cards.items():
        ta = tset(re.sub(r"\(.*?\)", "", ca["title"]))
        if len(ta) < min_title_tokens: continue
        for b, cb in cards.items():
            if a == b: continue
            sb = scopes[b]
            cov = len(ta & sb) / len(ta)
            # B must be broader than A (its scope mentions clearly more distinct terms) and cover A's whole title
            inter = len(scopes[a] & sb); jac = inter / max(1, len(scopes[a] | sb))
            # B must cover A's whole title AND be about the same family (scopes overlap), and A's title must not be broader than B's
            if cov == 1.0 and jac >= overlap and not (tset(re.sub(r"\(.*?\)", "", cb["title"])) <= scopes[a]):
                out.append((a, b, round(jac, 2)))
    return out


def hints(cards: dict) -> set[tuple[str, str]]:
    return {(a, h["ref"]) for a, c in cards.items() for h in c.get("supersession_hints", [])}


if __name__ == "__main__":
    cards = json.load(open("data/cards.json"))
    cont = containment(cards); hs = hints(cards)
    print(f"{len(cont)} containment pairs (A superseded-by B candidate):")
    for a, b, j in sorted(cont): print(f"  {a:9s} -> {b:9s} jac={j:.2f} {'[+transitional hint]' if (a, b) in hs else ''}  | {cards[a]['title'][:40]}")
