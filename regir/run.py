"""Full pipeline: spec.md → requirements JSON.

Usage:
    python -m regir.run cases/dev-rear-lamp --team my-team --out submission.json
    python -m regir.run cases/dev-rear-lamp  # uses defaults
"""
from __future__ import annotations
import argparse, json, os, pathlib, sys

from regir import llm
from regir.product.extract_text import extract as extract_facets
from regir.product.ontology import to_dict
from regir.select.candidates import generate as gen_candidates, _run_horizontal
from regir.select.scope_proof import score_all
from regir.select.coverage import solve as coverage_solve
from regir.select.section_filter import filter_atoms
from regir.evaluate.applicability import evaluate_atom
from regir.ingest.parse import parse_pdf
from regir.verify.requirements import fingerprint, verify_atom


# ---------- helpers ----------------------------------------------------------

def _load_atoms(reg: str) -> list[dict]:
    key = reg.replace(" ", "_")
    compiled = pathlib.Path(f"data/atoms/{key}.compiled.jsonl")
    path = compiled if compiled.exists() else pathlib.Path(f"data/atoms/{key}.jsonl")
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _req_id(reg: str, atom: dict, idx: int) -> str:
    # e.g. "R148-0001"
    short = reg.replace("UN ", "").replace(" ", "")
    return f"{short}-{idx:04d}"


# ---------- main pipeline ----------------------------------------------------

def run(
    case_dir: str | pathlib.Path,
    team_id: str = "regir-team",
    out_path: str | pathlib.Path | None = None,
    facets_path: str | pathlib.Path | None = None,
    assume_defaults: bool = False,
    verbose: bool = True,
) -> dict:
    case_dir = pathlib.Path(case_dir)
    case_id = case_dir.name

    # --- Step B: facet extraction -----------------------------------------
    if facets_path and pathlib.Path(facets_path).exists():
        sheet = json.load(open(facets_path))
        if verbose: print(f"[B] loaded facets from {facets_path}")
    else:
        suffix = ".assumed" if assume_defaults else ""
        cached = pathlib.Path(f"data/facets/{case_id}{suffix}.json")
        if cached.exists():
            sheet = json.load(open(cached))
            if verbose: print(f"[B] loaded cached facets: {cached}")
        else:
            spec_path = case_dir / "spec.md"
            if not spec_path.exists():
                raise FileNotFoundError(f"spec.md not found in {case_dir}")
            if verbose: print(f"[B] extracting facets from {spec_path} ...")
            fv = extract_facets(spec_path, assume_defaults=assume_defaults)
            sheet = to_dict(fv)
            os.makedirs("data/facets", exist_ok=True)
            with open(cached, "w") as f:
                json.dump(sheet, f, indent=2, ensure_ascii=False)
            if verbose: print(f"[B] saved facets -> {cached}")

    # --- Step C1: candidate generation ------------------------------------
    cards = json.load(open("data/cards.json"))
    candidates = gen_candidates(sheet, cards)
    horizontals = _run_horizontal(sheet, cards)
    if verbose: print(f"[C1] candidates ({len(candidates)}): {candidates}")

    # --- Step C2: scope proof ---------------------------------------------
    scored = score_all(candidates, cards, sheet)
    if verbose:
        for r in scored:
            print(f"  {r['regulation']:12s} p={r['p']:.2f} verdict={r['verdict']}")

    # --- Step C3: coverage solver -----------------------------------------
    selected = coverage_solve(scored, cards, horizontal_forced=horizontals)
    selected_regs = [r["regulation"] for r in selected]
    if verbose: print(f"[C3] selected ({len(selected_regs)}): {selected_regs}")

    # --- Step D: section filter + atom collection -------------------------
    requirements = []
    proofs = []
    seen_fingerprints = set()
    index = {r["regulation"]: r for r in json.load(open("regulations/index.json"))}
    req_counter = 1
    for entry in selected:
        reg = entry["regulation"]
        atoms = _load_atoms(reg)
        if not atoms:
            if verbose: print(f"  {reg}: no atoms found (not yet atomized)")
            continue
        kept = filter_atoms(reg, atoms, sheet)
        if verbose: print(f"  {reg}: {len(atoms)} atoms -> {len(kept)} after section filter")
        key = reg.replace(" ", "_")
        nodes = parse_pdf(f"regulations/pdf/{key}/base/{key}_base.pdf")
        expected_version = next(
            v["version_label"] for v in index[reg]["versions"] if v.get("role") == "base"
        )
        for atom in kept:
            verification = verify_atom(atom, nodes, expected_version)
            proof = evaluate_atom(atom, sheet)
            proof["regulation"] = reg
            proof["paragraph"] = atom.get("paragraph")
            proof["verification"] = verification
            proofs.append(proof)
            if not verification["valid"]:
                continue
            # Recall-oriented policy: exclude only mechanically proven false.
            # Unknown/assumption-dependent atoms remain in the submission and
            # are visible in the proof artifact for review.
            if proof["verdict"] == "false":
                continue
            fp = fingerprint(atom)
            if fp in seen_fingerprints:
                proof["duplicate"] = True
                continue
            seen_fingerprints.add(fp)
            req = {
                "id": _req_id(reg, atom, req_counter),
                "text": atom["text"],
                "source": {
                    "regulation": atom["regulation"],
                    "version": atom["version"],
                    "page": atom["page"],
                    "paragraph": atom["paragraph"],
                },
            }
            requirements.append(req)
            req_counter += 1

    submission = {
        "team_id": team_id,
        "case_id": case_id,
        "requirements": requirements,
    }

    # --- Write output -------------------------------------------------------
    if out_path is None:
        os.makedirs("submissions", exist_ok=True)
        out_path = pathlib.Path(f"submissions/{case_id}.json")
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(submission, f, indent=2, ensure_ascii=False)

    proof_path = out_path.with_suffix(".proofs.json")
    proof_path.write_text(json.dumps({
        "case_id": case_id,
        "policy": "exclude definite false; retain true and unknown",
        "proofs": proofs,
    }, indent=2, ensure_ascii=False))

    if verbose:
        counts = {v: sum(p["verdict"] == v for p in proofs) for v in ("true", "false", "unknown")}
        print(f"  applicability: {counts}")
        print(f"\n[out] {len(requirements)} requirements -> {out_path}")
        print(f"[proofs] {proof_path}")
    return submission


# ---------- CLI --------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="RegIR pipeline: spec → requirements JSON")
    ap.add_argument("case_dir", help="path to the case directory (contains spec.md)")
    ap.add_argument("--team", default="regir-team", help="team_id for the submission")
    ap.add_argument("--out", default=None, help="output JSON path (default: submissions/<case_id>.json)")
    ap.add_argument("--facets", default=None, help="pre-computed facets JSON to skip extraction")
    ap.add_argument("--assume-defaults", action="store_true", help="evaluate an explicit default-assumption scenario")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    run(a.case_dir, team_id=a.team, out_path=a.out, facets_path=a.facets,
        assume_defaults=a.assume_defaults, verbose=not a.quiet)
