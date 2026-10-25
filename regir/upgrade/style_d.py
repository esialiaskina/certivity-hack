"""
Step A/B/C — Expert-style few-shot stage D.

Uses matched/unmatched requirements from dev gold (judge.json) as few-shot
examples for stage D, trained leave-one-regulation-out.

Usage:
    # LORO evaluation on dev case (Step A + B)
    python -m regir.upgrade.style_d --mode eval

    # Full run on a new case with all-dev few-shots (Step C)
    python -m regir.upgrade.style_d --mode run \\
        --candidates _team/runs/synth-front-bumper-upgrade-balanced/candidates.json \\
        --selection  _team/runs/synth-front-bumper-upgrade-balanced/selection.json \\
        --case synth-front-bumper

Budget: ~4 calls (classification) + 4 calls (stage D folds) + 4 calls (judge) ≈ 12 calls for Step A.
        3×4+4 = 16 more calls for Step B. Total ≈ 28 calls.
"""
from __future__ import annotations
import json, random, sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_team" / "src"))

# Patches must happen before other imports
import pipeline as rp
import reqagent

rp.PKG   = ROOT
reqagent.PKG = ROOT
CACHE_DIR = ROOT / "data" / "llm_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
rp.CACHE = CACHE_DIR

import hybrid7 as H7
from regparse import Corpus


# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DEV_RUN   = ROOT / "_team" / "runs" / "rearlamp-v7b"
DEV_CASE  = ROOT / "cases" / "dev-rear-lamp"
GOLD_REGS = ["UN R10", "UN R148", "UN R150", "UN R48"]


# ---------------------------------------------------------------------------
# Build few-shot examples from dev gold
# ---------------------------------------------------------------------------

CLASSIFY_SYSTEM = """You classify why a requirement extracted from a UN Regulation was
NOT included in the expert's final requirement list for a product.

Classify each item with exactly one label from:
- "applicant": obligation falls on the applicant, manufacturer's paperwork, approval authority
  or inspector, not on the device itself
- "test_setup": describes how the laboratory runs a test (apparatus, positioning, number of
  samples, sequence) rather than what the product must withstand or achieve
- "definition": is a definition, general announcement, scope statement, or purely informative
- "inapplicable": applies to a device category, function class or vehicle type the product
  does not have (not an open option)
- "redundant": states the same obligation as another requirement in the list
- "conditional_unclear": conditional obligation whose condition likely does not apply to this
  product, or whose applicability cannot be determined from the spec
- "other": none of the above apply clearly

Return a JSON array, one entry per input, in the same order."""

CLASSIFY_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "label", "short_reason"],
        "properties": {
            "id":           {"type": "string"},
            "label":        {"type": "string", "enum": [
                "applicant", "test_setup", "definition",
                "inapplicable", "redundant", "conditional_unclear", "other"]},
            "short_reason": {"type": "string"},
        },
    },
}

LABEL_TEXT = {
    "applicant":            "obligation is on the applicant / approval authority, not the device",
    "test_setup":           "describes laboratory test setup rather than what the product must achieve",
    "definition":           "is a definition, scope statement, or purely informative",
    "inapplicable":         "applies to a device category or function the product does not have",
    "redundant":            "duplicates another requirement",
    "conditional_unclear":  "conditional obligation whose applicability cannot be confirmed",
    "other":                "not applicable or too general for this product",
}


def _classify_batch(reqs: list[dict], tag: str) -> list[dict]:
    """Classify a list of not-kept requirements with generic drop reasons."""
    items = [{"id": r["id"], "text": r["text"][:300],
              "paragraph": r["source"]["paragraph"]} for r in reqs]
    user = [{"type": "text", "text":
             "Classify each requirement below. Return exactly the same number of items:\n\n"
             + json.dumps(items, indent=1, ensure_ascii=False)}]
    return rp.call_json(CLASSIFY_SYSTEM, user, CLASSIFY_SCHEMA,
                        max_tokens=8000, tag=tag)


def _build_few_shot_block(
    kept_reqs: list[dict],
    dropped_reqs: list[dict],
    classifications: dict[str, str],  # id -> short_reason
    corpus: Corpus,
    n: int = 16,
) -> str:
    """Return a text block with up to n kept and n not-kept examples."""

    def heading(r: dict) -> str:
        reg  = r["source"]["regulation"]
        para = r["source"]["paragraph"]
        for n_ in corpus.by_reg.get((reg, "base"), []):
            if n_.label == para:
                return n_.title or n_.heading or ""
        return ""

    rng = random.Random(42)
    kept_sample    = rng.sample(kept_reqs,    min(n, len(kept_reqs)))
    dropped_sample = rng.sample(dropped_reqs, min(n, len(dropped_reqs)))

    lines = ["", "### Expert selection examples from other regulations", ""]
    lines.append("REQUIREMENTS THE EXPERT **KEPT** (include these):")
    for r in kept_sample:
        h = heading(r)
        lines.append(f"  [§{r['source']['paragraph']}{' | ' + h if h else ''}] {r['text'][:200]}")

    lines.append("")
    lines.append("REQUIREMENTS THE EXPERT **DID NOT KEEP** (drop these):")
    for r in dropped_sample:
        h    = heading(r)
        rsn  = classifications.get(r["id"], "not specific to this product's obligations")
        lines.append(
            f"  [§{r['source']['paragraph']}{' | ' + h if h else ''}] {r['text'][:200]}"
            f"\n    → reason: {rsn}"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Modified FILTER_SCHEMA with probability
# ---------------------------------------------------------------------------

FILTER_SCHEMA_P = deepcopy(rp.FILTER_SCHEMA)
FILTER_SCHEMA_P["properties"]["decisions"]["items"]["required"].append("p")
FILTER_SCHEMA_P["properties"]["decisions"]["items"]["properties"]["p"] = {
    "type": "number",
    "description": (
        "Probability that a regulatory expert would include this requirement in the "
        "final list for this product. 1.0 = certainly keep, 0.0 = certainly drop. "
        "Soft signal: even if decision=keep, a low p means borderline."
    ),
}


# ---------------------------------------------------------------------------
# One stage D call with few-shot + p output
# ---------------------------------------------------------------------------

def stage_d_prior(
    reg: str,
    candidates: list[dict],
    product_summary: str,
    b_info: dict,
    few_shot_block: str,
    tag_suffix: str = "",
    shuffle_seed: int | None = None,
) -> list[dict]:
    """
    Run the modified stage D for one regulation.
    Returns list of decisions with {id, decision, reason, merged_text, p}.
    """
    if shuffle_seed is not None:
        rng = random.Random(shuffle_seed)
        candidates = rng.sample(candidates, len(candidates))

    # Build modified system prompt: original rules + few-shot block + p instruction
    system = (
        H7.FILTER_SYSTEM
        + few_shot_block
        + "\n\nFor every candidate also output p (0.0–1.0): the probability that a "
        "regulatory expert would include this requirement in the final list."
    )

    user = (
        "## Product\n" + product_summary
        + "\n\n## How this regulation applies\n"
        + json.dumps({k: b_info[k] for k in ("how_it_applies", "part_mapping", "open_options")},
                     indent=1, ensure_ascii=False)
        + f"\n\n## Candidates from {reg} ({len(candidates)})\n"
        + "\n".join(f"{q['id']} [§{q['source']['paragraph']}] {q['text']}" for q in candidates)
        + "\n\nReturn a decision for every id."
    )

    safe_reg = reg.replace(" ", "_")
    tag = f"SD_{safe_reg}{tag_suffix}"
    return rp.call_json(system, [{"type": "text", "text": user}], FILTER_SCHEMA_P,
                        max_tokens=64000, tag=tag)["decisions"]


# ---------------------------------------------------------------------------
# LORO evaluation
# ---------------------------------------------------------------------------

def loro_eval(seeds: list[int] = (0,)) -> dict:
    """
    Leave-one-regulation-out evaluation on the dev case.
    Returns {fold -> {reg, decisions_by_seed, final_kept, F2, P, R}}.
    """
    reqagent.load_env()
    corpus = Corpus(ROOT / "_team" / "data" / "pdf")

    sub     = json.loads((DEV_RUN / "submission.json").read_text())
    cands   = json.loads((DEV_RUN / "candidates.json").read_text())
    judge_j = json.loads((DEV_RUN / "judge.json").read_text())
    sel     = json.loads((DEV_RUN / "selection.json").read_text())

    sub_by_id = {r["id"]: r for r in sub["requirements"]}

    # Identify matched and unmatched submitted IDs per regulation
    matched_sids: dict[str, set] = defaultdict(set)
    for reg, v in judge_j["per_regulation"].items():
        for m in v["matches"]:
            matched_sids[reg].add(m["submitted_id"])

    kept_by_reg:    dict[str, list[dict]] = defaultdict(list)
    dropped_by_reg: dict[str, list[dict]] = defaultdict(list)
    for r in sub["requirements"]:
        reg = r["source"]["regulation"]
        if reg in GOLD_REGS:
            if r["id"] in matched_sids[reg]:
                kept_by_reg[reg].append(r)
            else:
                dropped_by_reg[reg].append(r)

    # Classify drop reasons (cached)
    classifications: dict[str, str] = {}
    for reg in GOLD_REGS:
        drops = dropped_by_reg[reg]
        if not drops:
            continue
        tag  = f"CLS_{reg.replace(' ', '_')}"
        try:
            results = _classify_batch(drops, tag)
            for item in results:
                rid = item["id"]
                label = item["label"]
                short = item.get("short_reason", LABEL_TEXT.get(label, "not applicable"))
                classifications[rid] = f"{LABEL_TEXT.get(label, label)}: {short}"
        except Exception as e:
            print(f"  classify warning {reg}: {e}")
            for r in drops:
                classifications[r["id"]] = "not specific to this product's obligations"

    # Pre-D candidates per regulation
    cand_by_reg: dict[str, list[dict]] = defaultdict(list)
    for r in cands["requirements"]:
        if r["source"]["regulation"] in GOLD_REGS:
            cand_by_reg[r["source"]["regulation"]].append(r)

    product_summary = sel["stageA"]["product_summary"]
    b_info = sel["stageB"]

    results = {}
    import judge as jdg
    expected = json.loads((DEV_CASE / "expected.json").read_text())

    for held in GOLD_REGS:
        print(f"\n=== Fold: hold out {held} ===")
        others = [r for r in GOLD_REGS if r != held]

        # Build few-shot block from the other 3 regulations
        kept_pool    = [r for reg in others for r in kept_by_reg[reg]]
        dropped_pool = [r for reg in others for r in dropped_by_reg[reg]]
        few_shot = _build_few_shot_block(
            kept_pool, dropped_pool, classifications, corpus, n=16
        )

        # Run stage D multiple times with different seeds
        all_decisions: list[list[dict]] = []
        for seed in seeds:
            tag_sfx = f"_s{seed}"
            decisions = stage_d_prior(
                held,
                cand_by_reg[held],
                product_summary,
                b_info.get(held, {}),
                few_shot,
                tag_suffix=tag_sfx,
                shuffle_seed=seed if len(seeds) > 1 else None,
            )
            all_decisions.append(decisions)
            print(f"  seed={seed}: {sum(1 for d in decisions if d['decision']=='keep')} kept "
                  f"of {len(cand_by_reg[held])}")

        # Average probabilities across seeds
        p_by_id: dict[str, list[float]] = defaultdict(list)
        vote_keep: dict[str, int] = defaultdict(int)
        for run_decisions in all_decisions:
            for d in run_decisions:
                p_by_id[d["id"]].append(d.get("p", 0.8 if d["decision"] == "keep" else 0.2))
                if d["decision"] == "keep":
                    vote_keep[d["id"]] += 1

        # Use first run as base for decision/merged_text; update with averaged p
        base_decisions = {d["id"]: d for d in all_decisions[0]}
        final_decisions = []
        n_seeds = len(seeds)
        for d_id, d in base_decisions.items():
            avg_p = sum(p_by_id[d_id]) / len(p_by_id[d_id]) if p_by_id[d_id] else 0.5
            votes = vote_keep[d_id]
            # Use majority vote for decision if multiple seeds
            decision = "keep" if votes >= n_seeds / 2 else "drop"
            if n_seeds == 1:
                decision = d["decision"]
            final_decisions.append({
                **d,
                "decision": decision,
                "p": round(avg_p, 3),
                "votes": votes,
            })

        results[held] = {
            "decisions": final_decisions,
            "n_seeds": n_seeds,
        }

    # Score all folds together
    print("\n=== Scoring ===")
    # Build a combined submission using the new decisions
    combined_reqs = []
    sub_by_id_orig = {r["id"]: r for r in sub["requirements"]}

    for held in GOLD_REGS:
        dec_map = {d["id"]: d for d in results[held]["decisions"]}
        for c in cand_by_reg[held]:
            d = dec_map.get(c["id"])
            if d is None or d["decision"] == "keep":
                item = dict(c)
                if d and d.get("merged_text"):
                    item["text"] = d["merged_text"].strip()[:2000]
                if d:
                    item["_p"] = d["p"]
                combined_reqs.append(item)

    # Renumber
    reqs = []
    for q in combined_reqs:
        item = {"id": f"R-{len(reqs)+1:04d}", "text": q["text"],
                "source": q["source"]}
        if q.get("_p") is not None:
            item["_p"] = q["_p"]
        reqs.append(item)

    sub_new = {**sub, "requirements": reqs}

    # Judge
    run_dir = ROOT / "_team" / "runs" / "style_d_loro"
    run_dir.mkdir(exist_ok=True)
    J = jdg.judge(sub_new, expected, run_dir)

    print(f"\nBaseline:   F2=0.676 P=0.443 R=0.779 ({len(sub['requirements'])} reqs)")
    print(f"Style-D:    F2={J['summary']['f2']:.3f} P={J['summary']['precision']:.3f} "
          f"R={J['summary']['recall']:.3f} ({len(reqs)} reqs)")

    # Per-regulation breakdown
    print(f"\n{'Reg':<12} {'base_F2':>8} {'new_F2':>8} {'delta':>7}")
    for reg in GOLD_REGS:
        v = J["per_regulation"].get(reg, {})
        e, s, m = v.get("expected", 0), v.get("submitted", 0), v.get("matched", 0)
        p_ = m / s if s else 0
        r_ = m / e if e else 0
        f2 = 5 * p_ * r_ / (4 * p_ + r_) if p_ + r_ else 0
        # baseline per-reg
        bv = {"UN R10": 0.718, "UN R148": 0.708, "UN R150": 0.693, "UN R48": 0.606}
        print(f"{reg:<12} {bv.get(reg, 0):>8.3f} {f2:>8.3f} {f2 - bv.get(reg, 0):>+7.3f}")

    # LORO from combined judge
    per = J["per_regulation"]
    print(f"\n{'Held':<12} {'F2':>8} {'P':>8} {'R':>8}")
    for held in GOLD_REGS:
        hm = sum(per.get(r, {}).get("matched", 0) for r in GOLD_REGS if r != held)
        he = sum(per.get(r, {}).get("expected", 0) for r in GOLD_REGS if r != held)
        hs = sum(per.get(r, {}).get("submitted", 0) for r in GOLD_REGS if r != held)
        hp = hm / hs if hs else 0
        hr = hm / he if he else 0
        hf2 = 5 * hp * hr / (4 * hp + hr) if hp + hr else 0
        print(f"{held:<12} {hf2:>8.3f} {hp:>8.3f} {hr:>8.3f}")

    results["_judge"] = J
    results["_sub_new"] = sub_new
    (run_dir / "judge.json").write_text(json.dumps(J, indent=1, ensure_ascii=False))
    (run_dir / "submission.json").write_text(json.dumps(sub_new, indent=1, ensure_ascii=False))

    return results


# ---------------------------------------------------------------------------
# Cutoff modes (Step B)
# ---------------------------------------------------------------------------

def cutoff_modes(results: dict, cutoffs: dict[str, float] | None = None) -> dict:
    """
    Apply cutoffs (recall/balanced/precision) to the per-fold decisions.
    Returns {mode -> {reqs, F2, P, R}}.
    Returns the chosen cutoffs too.
    """
    import judge as jdg
    reqagent.load_env()
    expected = json.loads((DEV_CASE / "expected.json").read_text())

    # Collect all p values from kept reqs to understand distribution
    all_p = []
    cands_j = json.loads((DEV_RUN / "candidates.json").read_text())
    cand_by_reg: dict[str, list[dict]] = defaultdict(list)
    for r in cands_j["requirements"]:
        if r["source"]["regulation"] in GOLD_REGS:
            cand_by_reg[r["source"]["regulation"]].append(r)

    for held in GOLD_REGS:
        for d in results[held]["decisions"]:
            all_p.append(d.get("p", 0.5))

    if cutoffs is None:
        # F2 math: at baseline P=0.443, R=0.779, F2=0.676
        # optimal threshold ≈ F2 / (1 + 4*F2/R) but we sweep
        cutoffs = {"recall": 0.14, "balanced": 0.40, "precision": 0.65}

    mode_results = {}
    for mode, thr in cutoffs.items():
        reqs = []
        for held in GOLD_REGS:
            dec_map = {d["id"]: d for d in results[held]["decisions"]}
            for c in cand_by_reg[held]:
                d = dec_map.get(c["id"])
                p = d.get("p", 0.5) if d else 0.5
                if p >= thr:
                    item = dict(c)
                    if d and d.get("merged_text"):
                        item["text"] = d["merged_text"].strip()[:2000]
                    item["_p"] = p
                    reqs.append(item)

        final = [{"id": f"R-{i+1:04d}", "text": r["text"], "source": r["source"]}
                 for i, r in enumerate(reqs)]
        sub_mode = {
            "team_id": "team-05",
            "case_id": "dev-rear-lamp",
            "requirements": final,
        }

        run_dir = ROOT / "_team" / "runs" / f"style_d_{mode}"
        run_dir.mkdir(exist_ok=True)
        J = jdg.judge(sub_mode, expected, run_dir)
        s = J["summary"]
        mode_results[mode] = {"cutoff": thr, "count": len(final), "J": J,
                               "f2": s["f2"], "p": s["precision"], "r": s["recall"]}
        print(f"  mode={mode:<10} cutoff={thr:.2f}  "
              f"F2={s['f2']:.3f} P={s['precision']:.3f} R={s['recall']:.3f}  n={len(final)}")

    return mode_results, cutoffs


# ---------------------------------------------------------------------------
# Step C: run on a new case
# ---------------------------------------------------------------------------

def run_on_case(
    case_name: str,
    candidates_path: Path,
    selection_path: Path,
    out_dir: Path,
    seeds: list[int] = (0, 1, 2),
    cutoffs: dict[str, float] | None = None,
) -> None:
    """Apply style-D few-shot reviewer to a new case (no gold available)."""
    reqagent.load_env()
    corpus = Corpus(ROOT / "_team" / "data" / "pdf")

    cands = json.loads(candidates_path.read_text())
    sel   = json.loads(selection_path.read_text())

    # Load dev gold for few-shot examples (all 4 regulations)
    sub_dev   = json.loads((DEV_RUN / "submission.json").read_text())
    judge_dev = json.loads((DEV_RUN / "judge.json").read_text())

    matched_sids: dict[str, set] = defaultdict(set)
    for reg, v in judge_dev["per_regulation"].items():
        for m in v["matches"]:
            matched_sids[reg].add(m["submitted_id"])

    kept_all:    list[dict] = []
    dropped_all: list[dict] = []
    for r in sub_dev["requirements"]:
        reg = r["source"]["regulation"]
        if reg in GOLD_REGS:
            if r["id"] in matched_sids[reg]:
                kept_all.append(r)
            else:
                dropped_all.append(r)

    # Classify drops (all 4 regs)
    classifications: dict[str, str] = {}
    for reg in GOLD_REGS:
        drops = [r for r in dropped_all if r["source"]["regulation"] == reg]
        if not drops:
            continue
        tag = f"CLS_{reg.replace(' ', '_')}"
        try:
            res = _classify_batch(drops, tag)
            for item in res:
                classifications[item["id"]] = (
                    f"{LABEL_TEXT.get(item['label'], item['label'])}: "
                    f"{item.get('short_reason', '')}"
                )
        except Exception as e:
            print(f"  classify warning {reg}: {e}")
            for r in drops:
                classifications[r["id"]] = "not specific to this product's obligations"

    few_shot = _build_few_shot_block(kept_all, dropped_all, classifications, corpus, n=20)

    product_summary = sel["stageA"]["product_summary"]
    b_info = sel["stageB"]

    # Candidates per regulation
    cand_by_reg: dict[str, list[dict]] = defaultdict(list)
    for r in cands["requirements"]:
        cand_by_reg[r["source"]["regulation"]].append(r)

    if cutoffs is None:
        cutoffs = {"recall": 0.14, "balanced": 0.40, "precision": 0.65}

    out_dir.mkdir(parents=True, exist_ok=True)

    # Run per regulation
    all_results: dict[str, list[dict]] = {}
    for reg, reg_cands in sorted(cand_by_reg.items()):
        b = b_info.get(reg, {})
        if not b.get("include", True):
            continue
        run_decisions: list[list[dict]] = []
        for seed in seeds:
            decisions = stage_d_prior(
                reg, reg_cands, product_summary, b,
                few_shot, tag_suffix=f"_new_s{seed}", shuffle_seed=seed
            )
            run_decisions.append(decisions)

        p_by_id: dict[str, list[float]] = defaultdict(list)
        vote_keep: dict[str, int] = defaultdict(int)
        for run_dec in run_decisions:
            for d in run_dec:
                p_by_id[d["id"]].append(d.get("p", 0.8 if d["decision"] == "keep" else 0.2))
                if d["decision"] == "keep":
                    vote_keep[d["id"]] += 1

        base_map = {d["id"]: d for d in run_decisions[0]}
        final = []
        for d_id, d in base_map.items():
            avg_p = sum(p_by_id[d_id]) / len(p_by_id[d_id]) if p_by_id[d_id] else 0.5
            votes = vote_keep[d_id]
            decision = "keep" if votes >= len(seeds) / 2 else "drop"
            final.append({**d, "decision": decision, "p": round(avg_p, 3), "votes": votes})
        all_results[reg] = final

    # Write three mode files
    import subprocess
    for mode, thr in cutoffs.items():
        reqs = []
        for reg, reg_cands in sorted(cand_by_reg.items()):
            dec_map = {d["id"]: d for d in all_results.get(reg, [])}
            for c in reg_cands:
                d = dec_map.get(c["id"])
                p = d.get("p", 0.5) if d else 0.5
                if p >= thr:
                    item = {"id": f"R-{len(reqs)+1:04d}", "text": c["text"],
                            "source": c["source"]}
                    reqs.append(item)

        sub_out = {"team_id": "team-05", "case_id": case_name, "requirements": reqs}
        out_path = ROOT / "submissions" / f"{case_name}-{mode}.json"
        out_path.write_text(json.dumps(sub_out, indent=1, ensure_ascii=False))
        val = subprocess.run(
            ["python", str(ROOT / "tools" / "validate.py"), str(out_path), "--strict"],
            capture_output=True, text=True)
        val_msg = (val.stdout or val.stderr).strip()[:120]

        # Counts per regulation
        by_reg: dict[str, int] = defaultdict(int)
        for r in reqs:
            by_reg[r["source"]["regulation"]] += 1
        print(f"\n  {mode} (p>={thr:.2f}): {len(reqs)} reqs | {val_msg}")
        for reg2, cnt in sorted(by_reg.items()):
            print(f"    {reg2}: {cnt}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["eval", "run", "cutoffs"], default="eval")
    ap.add_argument("--candidates", help="candidates.json for --mode run")
    ap.add_argument("--selection",  help="selection.json for --mode run")
    ap.add_argument("--case",       help="case name for --mode run")
    ap.add_argument("--seeds",      default="0", help="comma-separated seeds, e.g. 0,1,2")
    a = ap.parse_args(argv)

    seeds = [int(s) for s in a.seeds.split(",")]

    if a.mode == "eval":
        print("=== Step A: LORO evaluation (1 seed) ===")
        results = loro_eval(seeds=seeds[:1])
        if len(seeds) > 1:
            print("\n=== Step B: Multi-seed + cutoffs ===")
            results_multi = loro_eval(seeds=seeds)
            mode_res, cutoffs = cutoff_modes(results_multi)
            # Save cutoffs
            (ROOT / "data" / "cutoffs.json").write_text(
                json.dumps(cutoffs, indent=1, ensure_ascii=False))
            print(f"Cutoffs saved: {cutoffs}")

    elif a.mode == "run":
        if not a.candidates or not a.selection or not a.case:
            print("--candidates, --selection and --case are required for --mode run")
            return
        run_on_case(
            case_name=a.case,
            candidates_path=Path(a.candidates),
            selection_path=Path(a.selection),
            out_dir=ROOT / "submissions",
            seeds=seeds,
        )

    elif a.mode == "cutoffs":
        # Load existing results and just re-do cutoffs
        results_multi = loro_eval(seeds=seeds)
        mode_res, cutoffs = cutoff_modes(results_multi)
        (ROOT / "data" / "cutoffs.json").write_text(
            json.dumps(cutoffs, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
