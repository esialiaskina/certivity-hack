"""
regir.upgrade.run — wrapper around _team/src/hybrid7.py that:

1. Fixes the PKG/tools path (both reqagent.PKG and pipeline.PKG point to
   a non-existent directory; we patch them before any other _team import).
2. Redirects the cache to data/llm_cache/ (persistent across sessions, same
   sha256 key so old dev-case hits are reused).
3. Adds --mode recall|balanced|precision (placeholder until P5 calibration).
4. Writes submissions/<case_id>.json alongside the run directory.

Usage:
    python -m regir.upgrade.run cases/synth-front-bumper --team team-05 --mode balanced
    python -m regir.upgrade.run cases/dev-rear-lamp --team team-05 --mode recall \\
        --profile _team/data/product/dev-rear-lamp.profile.json
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]   # industrial-ai-hackathon/
TEAM_SRC  = REPO_ROOT / "_team" / "src"
CACHE_DIR = REPO_ROOT / "data" / "llm_cache"

# ---------------------------------------------------------------------------
# Path + cache patches — must happen before any _team module is imported
# ---------------------------------------------------------------------------
sys.path.insert(0, str(TEAM_SRC))

import pipeline as rp
import reqagent

# Fix broken PKG pointers
rp.PKG    = REPO_ROOT
reqagent.PKG = REPO_ROOT

# Redirect cache to persistent location
CACHE_DIR.mkdir(parents=True, exist_ok=True)
rp.CACHE  = CACHE_DIR

# ---------------------------------------------------------------------------
# Now import _team modules that may use PKG/CACHE
# ---------------------------------------------------------------------------
import hybrid  as H
import hybrid7 as H7


def _count_calls() -> int:
    """Return number of cache files (proxy for unique LLM calls made this session)."""
    return len(list(CACHE_DIR.glob("*.json")))


def run(case_dir: Path, team: str, mode: str,
        profile_path: Path | None,
        threshold: float = 0.3,
        sure: float = 0.6) -> dict:
    """Run the full pipeline; return the submission dict."""
    reqagent.load_env()
    case     = case_dir.resolve()
    run_name = f"{case.name}-upgrade-{mode}"
    run_dir  = REPO_ROOT / "_team" / "runs" / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    calls_before = _count_calls()
    t0 = time.time()
    times: dict[str, float] = {}

    lines: list[str] = []
    def log(s: str):
        print(s, flush=True)
        lines.append(s)

    # ---- profile --------------------------------------------------------
    if profile_path and profile_path.exists():
        base = json.loads(profile_path.read_text())
    else:
        import profile as prof
        log("Building product profile…")
        base = prof.build_profile(case, use_model=True)
        (run_dir / "profile.json").write_text(json.dumps(base, indent=1, ensure_ascii=False))
    profile  = base.get("model") or base["deterministic"]
    from extend_profile import product_blocks
    blocks   = product_blocks(case, base)
    times["profile"] = time.time() - t0

    # ---- stage A --------------------------------------------------------
    t = time.time()
    A = H.stage_a(blocks, profile, threshold, log)
    times["A"] = time.time() - t

    # ---- filter candidates to parsed regulations only -------------------
    missing = [r for r in list(A["candidates"]) if (r, "base") not in A["C"].by_reg]
    if missing:
        log(f"dropping unparsed candidates: {missing}")
        for r in missing:
            del A["candidates"][r]

    # ---- stage B --------------------------------------------------------
    t = time.time()
    B = H.stage_b(A, blocks, sure, log)
    H7.collapse_nested(B)
    times["B"] = time.time() - t

    # ---- stage C + C2 ---------------------------------------------------
    t = time.time()
    jobs = H.section_jobs(A, B, profile)
    log(f"stage C: {len(jobs)} section calls")
    examples = H.style_examples()
    from concurrent.futures import ThreadPoolExecutor

    def c_one(job):
        res = rp.call_json(
            reqagent.SYSTEM + H.C_EXTRA,
            [{"type": "text", "text": H.job_prompt(A, job, examples)}],
            H.C_SCHEMA, max_tokens=64000, tag=H.job_tag("H_C", job))
        return H.tie(job, res["requirements"])

    with ThreadPoolExecutor(8) as pool:
        c_res = list(pool.map(c_one, jobs))
    c_qs = [q for qs in c_res for q in qs]
    log(f"stage C: {len(c_qs)} requirements")

    c2_qs = H7.stage_c2(A, jobs, dict(enumerate(c_res)), log)
    times["C+C2"] = time.time() - t

    # ---- assemble + stage D ---------------------------------------------
    t = time.time()
    cand, dropped_post = H.assemble(c_qs + c2_qs, case.name, team)
    log(f"post: {len(cand['requirements'])} candidates ({len(dropped_post)} dropped)")
    kept, dropped_d = H7.stage_d(A, B, cand["requirements"], log)
    times["D"] = time.time() - t

    # ---- mode filter (P5 placeholder) -----------------------------------
    cutoffs_path = REPO_ROOT / "data" / "cutoffs.json"
    if cutoffs_path.exists():
        cutoffs = json.loads(cutoffs_path.read_text())
        cutoff  = cutoffs.get(mode, 0.0)
        if cutoff > 0:
            kept = [q for q in kept if q.get("prob", 1.0) >= cutoff]
            log(f"mode={mode} cutoff p>={cutoff:.3f}: {len(kept)} kept")
    # else: all modes identical until P5

    # ---- final submission -----------------------------------------------
    reqs = []
    for q in kept:
        item = {"id": f"R-{len(reqs)+1:04d}", "text": q["text"], "source": q["source"]}
        if q.get("test_case"):
            item["test_case"] = q["test_case"]
        reqs.append(item)
    sub = {"team_id": team, "case_id": case.name, "requirements": reqs}

    elapsed = time.time() - t0
    calls_made = _count_calls() - calls_before

    sub_path = REPO_ROOT / "submissions" / f"{case.name}.json"
    sub_path.parent.mkdir(exist_ok=True)
    sub_path.write_text(json.dumps(sub, indent=1, ensure_ascii=False))
    (run_dir / "submission.json").write_text(json.dumps(sub, indent=1, ensure_ascii=False))
    (run_dir / "candidates.json").write_text(json.dumps(cand, indent=1, ensure_ascii=False))
    (run_dir / "dropped.json").write_text(
        json.dumps({"post": dropped_post, "filter": dropped_d}, indent=1,
                   ensure_ascii=False, default=str))
    (run_dir / "selection.json").write_text(
        json.dumps({"stageA": {k: A[k] for k in ("product_summary", "regulations",
                                                   "candidates", "bm25")},
                    "stageB": B}, indent=1, ensure_ascii=False))
    (run_dir / "log.txt").write_text("\n".join(lines) + "\n")

    # ---- validate -------------------------------------------------------
    import subprocess
    val = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "validate.py"), str(sub_path), "--strict"],
        capture_output=True, text=True)
    log("validate: " + (val.stdout or val.stderr).strip()[:200])

    # ---- score (only when expected.json present) ------------------------
    expected = case / "expected.json"
    if expected.exists():
        subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "score_local.py"),
                        str(sub_path), "--expected", str(expected)])
        import judge as jdg
        J = jdg.judge(sub, json.loads(expected.read_text()), run_dir)
        log(f"judge: F2={J['summary']['f2']:.3f} P={J['summary']['precision']:.3f} "
            f"R={J['summary']['recall']:.3f}")
    (run_dir / "log.txt").write_text("\n".join(lines) + "\n")

    # ---- report ---------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"Submission : {sub_path}")
    print(f"Run dir    : {run_dir}")
    print(f"Total time : {elapsed:.1f}s")
    print(f"New API calls this session: {calls_made}")
    print(f"Time per stage: " + " | ".join(f"{k} {v:.1f}s" for k, v in times.items()))
    print(f"Model      : {rp.MODEL}  (opus-5-5, ~$15/Mtok in, ~$75/Mtok out)")
    print(f"{'='*60}")
    return sub


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case_dir")
    ap.add_argument("--team",      default="team-05")
    ap.add_argument("--mode",      choices=["recall", "balanced", "precision"],
                    default="balanced")
    ap.add_argument("--profile",   help="path to saved profile JSON")
    ap.add_argument("--threshold", type=float, default=0.3)
    ap.add_argument("--sure",      type=float, default=0.6)
    a = ap.parse_args(argv)
    run(Path(a.case_dir), a.team, a.mode,
        Path(a.profile) if a.profile else None,
        a.threshold, a.sure)


if __name__ == "__main__":
    main()
