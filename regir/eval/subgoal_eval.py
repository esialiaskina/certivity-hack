import json, collections
from regir.ingest.parse import norm_label
from regir.subgoal.diff import run, reason

on, nn, changed, removed, added = run("subgoal/dev/old.pdf", "subgoal/dev/new.pdf")
old_reqs = json.load(open("subgoal/dev/requirements_old.json"))
exp = json.load(open("subgoal/dev/expected.json"))["changes"]
by_label = collections.defaultdict(list)
for r in old_reqs: by_label[norm_label(r["source"]["paragraph"])].append(r["id"])
changed_labels = {norm_label(o.label): (o, n, ratio, ops) for o, n, ratio, ops in changed}
removed_labels = {norm_label(o.label) for o in removed}
flagged_ids = {i for l in set(changed_labels) | removed_labels for i in by_label.get(l, [])}

mod = [c for c in exp if c["change"] in ("modified", "removed")]
hit = [c["requirement_id"] for c in mod if c["requirement_id"] in flagged_ids]
print(f"old nodes {len(on)}, new nodes {len(nn)}; changed {len(changed)}, removed {len(removed)}, added nodes {len(added)}")
print(f"modified/removed recall: {len(hit)}/{len(mod)}   | old requirement ids flagged: {len(flagged_ids)} of {len(old_reqs)} (precision proxy)")
for c in mod:
    if c["requirement_id"] not in flagged_ids: print("  MISSED:", c["requirement_id"], c["change"], c["source"])
exp_added = [norm_label(c["source"]["paragraph"]) for c in exp if c["change"] == "added"]
added_labels = {norm_label(n.label) for n in added}
# an expected 'added' paragraph counts as found if the label is an added node OR a changed node (text grew into it)
found = [l for l in exp_added if l in added_labels or l in changed_labels]
print(f"added recall (label level): {len(found)}/{len(exp_added)}   | added nodes proposed: {len(added)}")
for l in exp_added:
    if l not in added_labels and l not in changed_labels: print("  MISSED added label:", l)
print("\nexample reasons:")
for o, n, ratio, ops in changed[:4]: print(" ", o.label, "->", reason(ops)[:170])
