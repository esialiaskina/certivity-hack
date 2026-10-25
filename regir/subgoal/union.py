"""Merge an existing sub-goal submission (precise) with the max-recall sweep (broad).

Existing entries are kept unchanged. From the sweep we add
  - modified/removed for requirement ids the existing file did not flag,
  - added items whose new_text is not a near-duplicate of anything already in the file.

    python -m regir.subgoal.union existing.json sweep.json --out final.json
"""
import argparse, json
from rapidfuzz import fuzz

ap = argparse.ArgumentParser()
ap.add_argument("existing"); ap.add_argument("sweep")
ap.add_argument("--out", required=True)
ap.add_argument("--dup", type=float, default=80, help="added items above this similarity to an existing one are dropped")
a = ap.parse_args()
E, S = json.load(open(a.existing)), json.load(open(a.sweep))
out = list(E["changes"])
ids = {c["requirement_id"] for c in out if c.get("requirement_id")}
texts = [c["new_text"] for c in out if c.get("new_text")]
add_m = add_a = 0
for c in S["changes"]:
    if c.get("requirement_id"):
        if c["requirement_id"] not in ids:
            out.append(c); ids.add(c["requirement_id"]); add_m += 1
    elif c["change"] == "added":
        if all(fuzz.token_set_ratio(c["new_text"], t) < a.dup for t in texts):
            out.append(c); texts.append(c["new_text"]); add_a += 1
res = {"team_id": E["team_id"], "case_id": E["case_id"], "changes": out}
json.dump(res, open(a.out, "w"), indent=1, ensure_ascii=False)
print(f"existing {len(E['changes'])} + sweep: {add_m} modified/removed, {add_a} added -> {len(out)} total -> {a.out}")
