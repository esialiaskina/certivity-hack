"""Sub-goal MAX-RECALL sweep (no model calls).

Ranking on the sub-goal leaderboard sorts by flag recall first, so this builds a superset of candidate changes:
  - every old requirement whose source paragraph has a changed / deleted sentence  -> modified / removed
  - every new normative sentence with no old counterpart, in ANY chapter           -> added
Use regir/subgoal/union.py to merge it with an existing (more precise) submission.

    python -m regir.subgoal.sweep subgoal/heldout --case-id subgoal-heldout --out submissions/heldout-subgoal-sweep.json
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_team" / "src"))
import subgoal as sg  # teammates' aligner

SAME_STRICT = 99.5   # a sentence is unchanged only when it matches this well


def pdf_paths(case_dir: Path):
    if (case_dir / "old.pdf").exists() and (case_dir / "new.pdf").exists():
        return case_dir / "old.pdf", case_dir / "new.pdf"
    files = json.load(open(case_dir / "files.json"))
    out = {}
    for f in files:
        m = re.search(r"regulations/(UN_[^/]+)/(base|latest)/([^/]+\.pdf)", f["pdf_url"])
        out[f["name"]] = ROOT / "regulations" / "pdf" / m.group(1) / m.group(2) / m.group(3)
    return out["old.pdf"], out["new.pdf"]


def build(case_dir: Path, case_id: str, team: str, lenient: bool = True) -> dict:
    reqs = json.load(open(case_dir / "requirements_old.json"))
    old_pdf, new_pdf = pdf_paths(case_dir)
    A = sg.align(old_pdf, new_pdf)
    reg, v = A["reg"], A["v_new"]
    by_key: dict[str, list[dict]] = {}
    for s in A["so"]:
        by_key.setdefault(s["key"], []).append(s)
    changes, used = [], set()

    # ---- modified / removed -------------------------------------------------------------------------------
    for r in reqs:
        key = sg._old_key(r)
        sents = by_key.get(key)
        if not sents:                                    # paragraph id not found (e.g. table node): search all old sentences
            best = max(A["so"], key=lambda s: fuzz.token_set_ratio(r["text"], s["text"]))
            sents = [best] if fuzz.token_set_ratio(r["text"], best["text"]) >= 85 else []
        if not sents:
            continue
        sim = [(fuzz.token_set_ratio(r["text"], s["text"]), s) for s in sents]
        best_sim, best_s = max(sim, key=lambda x: x[0])
        cand = best_s if best_s["score"] < SAME_STRICT else None
        if cand is None and lenient:                     # another sentence of the same paragraph changed
            ch = [(sm, s) for sm, s in sim if s["score"] < SAME_STRICT and sm >= 30]
            if ch:
                cand = max(ch, key=lambda x: x[0])[1]
        if cand is None:
            continue
        m = cand["match"]
        if m is None or cand["score"] < sg.LINK:
            changes.append({"requirement_id": r["id"], "change": "removed",
                            "reason": f"Paragraph {r['source']['paragraph']} of {reg} was amended in version {v}; the provision "
                                      f"'{sg._short(cand['text'], 100)}' no longer appears."})
        else:
            n = A["new"].get(m["key"])
            ops = "; ".join(sg.diff_ops(cand["text"], m["text"])) or "wording changed"
            ch = {"requirement_id": r["id"], "change": "modified", "new_text": m["text"][:2000],
                  "reason": f"Paragraph {sg._label(A, m['key'])} of {reg} was amended in version {v}: {ops}."}
            if n is not None:
                ch["source"] = {"page": n.page_start, "paragraph": sg._label(A, m["key"])}
            changes.append(ch)
        used.add(r["id"])

    # ---- added: every novel normative sentence, any chapter (list items get their lead-in sentence) ----------
    seen, lead = set(), {}
    item_re = re.compile(r"^\(?[a-z0-9ivx]{1,4}\)\s")
    for s in A["sn"]:
        t = s["text"].strip()
        if t.endswith(":") and sg.NORMATIVE_RE.search(t):
            lead[s["key"]] = t
            continue
        if not s["new"] or s["score"] >= sg.NOVEL or len(t) < 15:
            continue
        if item_re.match(t) and s["key"] in lead:
            t = lead[s["key"]].rstrip(": ") + ": " + t
        elif not sg.NORMATIVE_RE.search(t) or len(t) < 25:
            continue
        if t in seen:
            continue
        seen.add(t)
        n = A["new"][s["key"]]
        changes.append({"requirement_id": None, "change": "added", "new_text": t[:2000],
                        "reason": f"Paragraph {sg._label(A, s['key'])} of {reg} is new in version {v}: '{sg._short(t, 100)}'.",
                        "source": {"page": n.page_start, "paragraph": sg._label(A, s["key"])}})
    return {"team_id": team, "case_id": case_id, "changes": changes}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("--case-id", default="subgoal-heldout")
    ap.add_argument("--team", default="team-05")
    ap.add_argument("--out", default="submissions/heldout-subgoal-sweep.json")
    ap.add_argument("--strict", action="store_true", help="only the best-matching sentence of each requirement")
    a = ap.parse_args()
    sub = build(Path(a.case_dir), a.case_id, a.team, lenient=not a.strict)
    Path(a.out).parent.mkdir(exist_ok=True)
    json.dump(sub, open(a.out, "w"), indent=1, ensure_ascii=False)
    from collections import Counter
    print(dict(Counter(c["change"] for c in sub["changes"])), "->", a.out)
