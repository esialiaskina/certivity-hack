"""
Step 0 utility: run the pipeline.py judge on any submission.json and print
leave-one-regulation-out (LORO) F2/P/R.

    python -m regir.upgrade.baseline _team/runs/rearlamp-v7b/submission.json \
        cases/dev-rear-lamp/expected.json
"""
from __future__ import annotations
import json, sys
from pathlib import Path


def _metrics(matched: int, submitted: int, expected: int) -> tuple[float, float, float]:
    p = matched / submitted if submitted else 0.0
    r = matched / expected if expected else 0.0
    f2 = 5 * p * r / (4 * p + r) if (p + r) else 0.0
    return round(p, 3), round(r, 3), round(f2, 3)


def loro_from_judge(judge_path: Path) -> None:
    """Print per-regulation and LORO F2 from an existing judge.json."""
    j = json.loads(judge_path.read_text())
    per = j["per_regulation"]

    print(f"{'Regulation':<12} {'exp':>5} {'sub':>5} {'matched':>8} {'P':>7} {'R':>7} {'F2':>7}")
    print("-" * 55)
    gold_regs = []
    for reg, v in per.items():
        e, s, m = v["expected"], v["submitted"], v["matched"]
        p, r, f2 = _metrics(m, s, e)
        print(f"{reg:<12} {e:>5} {s:>5} {m:>8} {p:>7.3f} {r:>7.3f} {f2:>7.3f}")
        if e > 0:
            gold_regs.append(reg)

    print()
    # Full 4-gold-reg total
    tot_m = sum(per[r]["matched"] for r in gold_regs)
    tot_e = sum(per[r]["expected"] for r in gold_regs)
    tot_s = sum(per[r]["submitted"] for r in gold_regs)
    p, r, f2 = _metrics(tot_m, tot_s, tot_e)
    print(f"{'All '+str(len(gold_regs))+' gold regs':<12} {tot_e:>5} {tot_s:>5} {tot_m:>8} {p:>7.3f} {r:>7.3f} {f2:>7.3f}")
    print()

    print("Leave-one-regulation-out (LORO):")
    print(f"  {'Held out':<12} {'F2':>7} {'P':>7} {'R':>7}")
    for held in gold_regs:
        hm = sum(per[r]["matched"] for r in gold_regs if r != held)
        he = sum(per[r]["expected"] for r in gold_regs if r != held)
        hs = sum(per[r]["submitted"] for r in gold_regs if r != held)
        hp, hr, hf2 = _metrics(hm, hs, he)
        print(f"  {held:<12} {hf2:>7.3f} {hp:>7.3f} {hr:>7.3f}")

    print()
    print(f"Summary: {j['summary']}")


def per_reg_from_submission(sub_path: Path, exp_path: Path) -> dict[str, dict]:
    """Return per-regulation {matched, submitted, expected} counts from raw submission
    and expected.json using simple paragraph-level overlap (no LLM — for quick checks)."""
    sub = json.loads(sub_path.read_text())
    exp = json.loads(exp_path.read_text())
    sub_by_reg: dict[str, list] = {}
    for r in sub["requirements"]:
        sub_by_reg.setdefault(r["source"]["regulation"], []).append(r)
    exp_by_reg: dict[str, list] = {}
    for r in exp["requirements"]:
        exp_by_reg.setdefault(r["source"]["regulation"], []).append(r)
    all_regs = sorted(set(sub_by_reg) | set(exp_by_reg))
    out = {}
    for reg in all_regs:
        sr = sub_by_reg.get(reg, [])
        er = exp_by_reg.get(reg, [])
        sub_paras = {r["source"]["paragraph"] for r in sr}
        exp_paras = {r["source"]["paragraph"] for r in er}
        out[reg] = {
            "submitted": len(sr),
            "expected": len(er),
            "para_recall": len(exp_paras & sub_paras) / len(exp_paras) if exp_paras else 0,
            "missing_paras": sorted(exp_paras - sub_paras),
            "extra_paras": sorted(sub_paras - exp_paras),
        }
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 1:
        judge_path = Path(args[0])
        if judge_path.name == "judge.json":
            loro_from_judge(judge_path)
        else:
            print("Usage: python -m regir.upgrade.baseline <judge.json>")
            print("    or: python -m regir.upgrade.baseline <submission.json> <expected.json>")
    elif len(args) == 2:
        sub, exp = Path(args[0]), Path(args[1])
        result = per_reg_from_submission(sub, exp)
        for reg, v in result.items():
            print(f"{reg}: sub={v['submitted']} exp={v['expected']} para_recall={v['para_recall']:.2f}")
            if v["missing_paras"]:
                print(f"  missing paras: {v['missing_paras']}")
    else:
        loro_from_judge(Path("_team/runs/rearlamp-v7b/judge.json"))
