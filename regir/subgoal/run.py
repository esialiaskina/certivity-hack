"""Sub-goal runner: old.pdf + new.pdf + requirements_old.json → changes.json

Uses only the deterministic diff from diff.py — no per-requirement LLM or
extra similarity search.  Keeps recall high; an LLM judge layer can be added
later without touching this file.

Usage:
    python -m regir.subgoal.run subgoal/dev --team my-team --out submissions/dev-changes.json
"""
from __future__ import annotations
import argparse, json, os, pathlib, re
from regir.subgoal.diff import run as diff_run, body
from regir.ingest.parse import norm_label

CUE = re.compile(
    r"\b(shall|must|should|may not|is required|are required|required to|"
    r"is prohibited|not be permitted|mandatory|has to|have to|not exceed|"
    r"at least|at most|minimum|maximum|not less than|not more than)\b",
    re.I,
)


def _extract_version(front_text: str) -> str:
    """Pull a version string from the front-page text, e.g. '(version 1.0.0)' -> '1.0.0'."""
    m = re.search(r"version\s+([\d.]+)", front_text, re.I)
    return m.group(1) if m else "latest"


def _first_obligation(node_text: str) -> str:
    for sent in re.split(r"(?<=[.!?])\s+", node_text.strip()):
        if CUE.search(sent):
            return sent[:1990]
    return node_text[:1990]


def _reason_modified(reg: str, version: str, old_label: str, new_label: str,
                     old_text: str, new_body: str) -> str:
    import difflib
    ow = re.sub(r"\s+", " ", old_text).split()
    nw = re.sub(r"\s+", " ", new_body).split()
    sm = difflib.SequenceMatcher(None, ow, nw, autojunk=False)
    ops = [(tag, " ".join(ow[i1:i2]), " ".join(nw[j1:j2]))
           for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
    parts = []
    for tag, o, n in ops[:4]:
        if tag == "replace":  parts.append(f"'{o}' became '{n}'")
        elif tag == "delete": parts.append(f"'{o}' was removed")
        elif tag == "insert": parts.append(f"'{n}' was added")
    diff_str = "; ".join(parts) if parts else "content was amended"
    formerly = f" (formerly {old_label})" if old_label != new_label else ""
    return f"Paragraph {new_label}{formerly} of {reg} was amended in version {version}: {diff_str}."


def _reason_removed(reg: str, version: str, old_label: str, req_text: str) -> str:
    snippet = req_text[:60].rstrip(".,; ")
    return (f"Paragraph {old_label} of {reg} was amended in version {version}; "
            f"the provision '{snippet}\u2026' no longer appears.")


def _reason_added(reg: str, version: str, new_label: str, new_body: str) -> str:
    snippet = new_body[:120].rstrip(".,; ")
    return f"Paragraph {new_label} of {reg} is new in version {version}: '{snippet}\u2026'."


def run_subgoal(
    case_dir: str | pathlib.Path,
    team_id: str = "regir-team",
    out_path: str | pathlib.Path | None = None,
    verbose: bool = True,
) -> dict:
    case_dir = pathlib.Path(case_dir)
    case_id  = case_dir.name
    old_pdf  = str(case_dir / "old.pdf")
    new_pdf  = str(case_dir / "new.pdf")
    old_reqs: list[dict] = json.load(open(case_dir / "requirements_old.json"))

    # Derive regulation name from the data, not from hard-coded strings
    reg_name = old_reqs[0]["source"]["regulation"] if old_reqs else "UN Regulation"

    if verbose: print(f"[diff] aligning {old_pdf}")
    on, nn, changed, removed_nodes, added_nodes = diff_run(old_pdf, new_pdf)

    # New version from front page of new PDF
    front = next((n for n in nn if n.label == "front"), None)
    new_version = _extract_version(front.text) if front else "latest"

    # Build lookups keyed by normalised paragraph label
    changed_by_label = {norm_label(o.label): (o, n, ratio, ops)
                        for o, n, ratio, ops in changed}
    removed_by_label = {norm_label(o.label): o for o in removed_nodes}

    changes: list[dict] = []

    # Map old requirements to changed / removed paragraphs
    for req in old_reqs:
        old_lbl  = norm_label(req["source"]["paragraph"])
        old_para = req["source"]["paragraph"]
        req_text = req.get("text", "")

        if old_lbl in changed_by_label:
            _, n_node, _, _ = changed_by_label[old_lbl]
            new_txt = _first_obligation(n_node.text)
            rsn = _reason_modified(reg_name, new_version, old_para,
                                   n_node.label, req_text, body(n_node))
            changes.append({
                "requirement_id": req["id"],
                "change":         "modified",
                "new_text":       new_txt[:1990],
                "reason":         rsn,
                "source":         {"page": n_node.page_start,
                                   "paragraph": n_node.label},
            })
        elif old_lbl in removed_by_label:
            rsn = _reason_removed(reg_name, new_version, old_para, req_text)
            changes.append({
                "requirement_id": req["id"],
                "change":         "removed",
                "reason":         rsn,
            })

    # Added paragraphs that contain obligation language
    for n in added_nodes:
        if not CUE.search(n.text):
            continue
        new_b   = body(n)
        new_txt = _first_obligation(n.text)
        rsn = _reason_added(reg_name, new_version, n.label, new_b)
        changes.append({
            "requirement_id": None,
            "change":         "added",
            "new_text":       new_txt[:1990],
            "reason":         rsn,
            "source":         {"page": n.page_start, "paragraph": n.label},
        })

    submission = {
        "team_id":  team_id,
        "case_id":  case_id,
        "changes":  changes,
    }

    if out_path is None:
        os.makedirs("submissions", exist_ok=True)
        out_path = pathlib.Path(f"submissions/{case_id}-changes.json")
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(submission, f, indent=2, ensure_ascii=False)

    if verbose:
        from collections import Counter
        cnt = Counter(c["change"] for c in changes)
        print(f"[subgoal] {dict(cnt)} -> {out_path}")
    return submission


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="RegIR sub-goal: old/new PDF -> changes JSON")
    ap.add_argument("case_dir", help="path to the case directory")
    ap.add_argument("--team",  default="regir-team")
    ap.add_argument("--out",   default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    run_subgoal(a.case_dir, team_id=a.team, out_path=a.out, verbose=not a.quiet)
