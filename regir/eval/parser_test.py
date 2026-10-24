"""Gold-as-infrastructure-test: does our tree contain each gold paragraph on a gold-cited page?
Never used to tune extraction prompts; only to validate parsing."""
import json, sys, collections
from regir.ingest.parse import parse_pdf, norm_label

gold = json.load(open("cases/dev-rear-lamp/expected.json"))["requirements"]
trees, res, bad = {}, collections.Counter(), []
for r in gold:
    s = r["source"]; k = s["regulation"].replace(" ", "_")
    if k not in trees:
        trees[k] = collections.defaultdict(list)
        for n in parse_pdf(f"regulations/pdf/{k}/base/{k}_base.pdf"):
            trees[k][norm_label(n.label)].append(n)
    import re
    lab = re.sub(r"\s+table.*$", "", s["paragraph"], flags=re.I)  # gold sometimes appends a table caption
    cands = trees[k].get(norm_label(lab), [])
    if not cands: res["label missing in tree"] += 1; bad.append((s["regulation"], s["paragraph"], s["page"], "missing")); continue
    if any(n.page_start <= s["page"] <= n.page_end for n in cands): res["ok (page within node span)"] += 1
    else: res["label found, page differs"] += 1; bad.append((s["regulation"], s["paragraph"], s["page"], [(n.page_start, n.page_end) for n in cands]))
print(dict(res), "of", len(gold))
for b in bad[:25]: print(b)
