#!/usr/bin/env python3
"""Preflight Cursor Other-Models burn for a needs-sweep job.

Cursor CLI does not expose remaining allowance. Snapshot it once from
Settings → Plan & Usage / Spending into:

  ~/edgible-needs-sweep/cursor-budget.json

Then estimate this job from past *.transcript.jsonl usage (answer sessions)
and model list prices, and optionally refuse to launch if the hit is too large.

Example:
  python3 preflight-needs-sweep.py \\
    --model claude-opus-5-5-high --sample 35 --judge-harness cursor

  # after updating the budget file:
  python3 preflight-needs-sweep.py --model … --sample 35 --require-budget --max-pct 40
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA_DEFAULT = Path.home() / "edgible-needs-sweep"
BUDGET_NAME = "cursor-budget.json"

# Cursor docs list prices ($ / million tokens). Keys are matched as prefixes
# against --model (lowercased). First match wins.
RATES = [
    ("claude-opus-5-5", dict(input=4.0, cacheWrite=5.0, cacheRead=0.2, output=20.0)),
    ("claude-opus-5", dict(input=5.0, cacheWrite=6.25, cacheRead=0.5, output=25.0)),
    ("claude-opus", dict(input=5.0, cacheWrite=6.25, cacheRead=0.5, output=25.0)),
    ("claude-sonnet-5", dict(input=2.0, cacheWrite=2.5, cacheRead=0.2, output=10.0)),
    ("claude-sonnet", dict(input=3.0, cacheWrite=3.75, cacheRead=0.3, output=15.0)),
    ("composer", dict(input=0.5, cacheWrite=0.5, cacheRead=0.2, output=2.5)),  # Composer 2.5; cacheWrite unused
]


def rates_for(model: str) -> tuple[str, dict]:
    m = (model or "").lower()
    for prefix, rates in RATES:
        if prefix in m:
            return prefix, rates
    return "claude-sonnet-5 (fallback)", RATES[3][1]


def is_cursor_model(model: str) -> bool:
    """Models that draw from Pro 'Cursor Models' pool (not Other Models)."""
    m = (model or "").lower()
    return any(s in m for s in ("composer", "grok-4", "grok4", "cursor-"))


def cost_usd(usage: dict, rates: dict) -> float:
    return (
        usage.get("inputTokens", 0) * rates["input"]
        + usage.get("cacheWriteTokens", 0) * rates.get("cacheWrite", rates["input"])
        + usage.get("cacheReadTokens", 0) * rates["cacheRead"]
        + usage.get("outputTokens", 0) * rates["output"]
    ) / 1e6


def load_usage_stats(results_dir: Path, model_hint: str) -> dict | None:
    """Average answer-session usage from past runs whose dirname contains model_hint."""
    hint = re.sub(r"[^a-z0-9]+", "-", (model_hint or "").lower()).strip("-")
    # Prefer exact-ish model dirs; fall back to any claude-*/composer-* with usage.
    dirs = sorted(
        (p for p in results_dir.glob("needs-sweep-cursor-*") if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    preferred = [d for d in dirs if hint and hint[:20] in d.name.lower()]
    search = preferred or dirs

    totals = defaultdict(float)
    n = 0
    source = None
    for d in search:
        for p in d.glob("*.transcript.jsonl"):
            usage = None
            for line in p.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "result" and isinstance(obj.get("usage"), dict):
                    usage = obj["usage"]
            if not usage:
                continue
            n += 1
            source = d.name
            for k, v in usage.items():
                if isinstance(v, (int, float)):
                    totals[k] += v
        if n >= 5 and preferred:
            break
        if n >= 15:
            break
    if n == 0:
        return None
    avg = {k: totals[k] / n for k in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens")}
    return {"n": n, "avg": avg, "source": source}


def default_avg_for(model: str) -> dict:
    """When no history: sonnet-like token mix observed on this machine (~200k billable)."""
    # Rough prior from Sonnet needs-sweep answer sessions.
    return {
        "inputTokens": 15,
        "outputTokens": 3800,
        "cacheReadTokens": 160000,
        "cacheWriteTokens": 28000,
    }


def load_budget(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def budget_template() -> dict:
    return {
        "pool": "other_models",
        "plan": "Pro",
        "remaining_usd": None,
        "included_usd": None,
        "remaining_pct": None,
        "reset_date": None,
        "on_demand": None,
        "on_demand_cap_usd": None,
        "updated_at": None,
        "notes": "Fill remaining_usd and/or remaining_pct + reset_date from Cursor Spending, then re-run preflight.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=DATA_DEFAULT)
    ap.add_argument("--model", default="", help="answer model id (same as run wrapper; required unless --write-budget-template)")
    ap.add_argument("--sample", type=int, default=0, help="number of needs in this job (required unless --write-budget-template)")
    ap.add_argument("--judge-harness", choices=("claude", "cursor"), default="cursor")
    ap.add_argument("--judge-multiplier", type=float, default=0.0,
                    help="extra Cursor cost as fraction of answer cost when judge-harness=cursor "
                         "(default 0.7). Ignored for claude judge (0).")
    ap.add_argument("--budget", type=Path, help=f"default: <data-dir>/{BUDGET_NAME}")
    ap.add_argument("--write-budget-template", action="store_true",
                    help="create budget JSON skeleton if missing, then exit")
    ap.add_argument("--require-budget", action="store_true",
                    help="exit 2 if budget file missing or has no remaining_*")
    ap.add_argument("--max-pct", type=float, default=0.0,
                    help="exit 3 if estimated job uses more than this %% of included/remaining pool")
    ap.add_argument("--max-usd", type=float, default=0.0,
                    help="exit 3 if estimated job USD exceeds this")
    ap.add_argument("--allow-other-models", action="store_true",
                    help="do not refuse third-party models when budget.prefer_cursor_models is set")
    ap.add_argument("--json", action="store_true", help="print machine-readable summary")
    args = ap.parse_args()

    data = args.data_dir
    data.mkdir(parents=True, exist_ok=True)
    budget_path = args.budget or (data / BUDGET_NAME)

    if args.write_budget_template:
        if budget_path.exists():
            print(f"already exists: {budget_path}", file=sys.stderr)
            return 1
        budget_path.write_text(json.dumps(budget_template(), indent=2) + "\n")
        print(f"wrote {budget_path}")
        print("Fill remaining_usd / remaining_pct / reset_date from cursor.com/dashboard → Spending")
        return 0

    if not args.model or args.sample <= 0:
        ap.error("--model and --sample are required (unless --write-budget-template)")

    rate_name, rates = rates_for(args.model)
    stats = load_usage_stats(data / "results", args.model)
    if stats:
        avg = stats["avg"]
        hist = f"{stats['n']} sessions from {stats['source']}"
    else:
        # Cross-model fallback: any sonnet history, else prior
        stats2 = load_usage_stats(data / "results", "claude-sonnet")
        if stats2:
            avg = stats2["avg"]
            hist = f"no {args.model} history; using {stats2['n']} sonnet sessions ({stats2['source']})"
        else:
            avg = default_avg_for(args.model)
            hist = "no transcripts yet; using built-in prior (~sonnet mix)"

    per_answer = cost_usd(avg, rates)
    judge_mult = 0.0 if args.judge_harness == "claude" else (args.judge_multiplier or 0.7)
    per_need = per_answer * (1.0 + judge_mult)
    job = per_need * args.sample
    billable = sum(avg.get(k, 0) for k in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"))

    budget = load_budget(budget_path)
    remaining_usd = remaining_pct = included = reset = None
    budget_age = None
    if budget:
        remaining_usd = budget.get("remaining_usd")
        remaining_pct = budget.get("remaining_pct")
        included = budget.get("included_usd")
        reset = budget.get("reset_date")
        budget_age = budget.get("updated_at")
        if remaining_pct is None and remaining_usd is not None and included:
            remaining_pct = 100.0 * float(remaining_usd) / float(included)
        if remaining_usd is None and remaining_pct is not None and included:
            remaining_usd = float(included) * float(remaining_pct) / 100.0

    has_remaining = remaining_usd is not None or remaining_pct is not None
    if args.require_budget and not has_remaining:
        print(
            f"missing budget snapshot at {budget_path}\n"
            f"  1) open Cursor Spending / Plan & Usage\n"
            f"  2) python3 {Path(__file__).name} --write-budget-template\n"
            f"  3) fill remaining_usd or remaining_pct (+ reset_date, updated_at)\n"
            f"  4) re-run preflight",
            file=sys.stderr,
        )
        return 2

    impact_pct_of_remaining = None
    after_usd = None
    after_pct = None
    if remaining_usd is not None and float(remaining_usd) > 0:
        impact_pct_of_remaining = 100.0 * job / float(remaining_usd)
        after_usd = float(remaining_usd) - job
    if remaining_pct is not None and included:
        # job as % of full included pool
        impact_pct_of_pool = 100.0 * job / float(included)
    elif remaining_pct is not None and remaining_usd:
        impact_pct_of_pool = None
    else:
        impact_pct_of_pool = None
    if remaining_pct is not None and included:
        after_pct = max(0.0, float(remaining_pct) - (100.0 * job / float(included)))
    elif remaining_pct is not None and remaining_usd and float(remaining_usd) > 0:
        after_pct = max(0.0, float(remaining_pct) * (1.0 - job / float(remaining_usd)))

    summary = {
        "model": args.model,
        "rate_table": rate_name,
        "sample": args.sample,
        "judge_harness": args.judge_harness,
        "judge_multiplier": judge_mult,
        "history": hist,
        "avg_billable_tokens_per_answer": round(billable),
        "usd_per_answer_session": round(per_answer, 4),
        "usd_per_need_with_judge": round(per_need, 4),
        "usd_job_estimate": round(job, 2),
        "budget_path": str(budget_path),
        "remaining_usd": remaining_usd,
        "remaining_pct": remaining_pct,
        "included_usd": included,
        "reset_date": reset,
        "budget_updated_at": budget_age,
        "impact_pct_of_remaining": round(impact_pct_of_remaining, 1) if impact_pct_of_remaining is not None else None,
        "after_job_remaining_usd": round(after_usd, 2) if after_usd is not None else None,
        "after_job_remaining_pct": round(after_pct, 1) if after_pct is not None else None,
        "pool_note": "Pro Other Models (third-party). Composer jobs use Cursor Models pool instead.",
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("Needs-sweep preflight (Cursor Other Models)")
        print(f"  model:     {args.model}  [{rate_name} rates]")
        print(f"  job:       {args.sample} needs, judge={args.judge_harness}"
              + (f" (×{1+judge_mult:.2f} vs answer-only)" if judge_mult else " (judge not on Cursor pool)"))
        print(f"  history:   {hist}")
        print(f"  ~tokens/answer (all cats): {billable:,.0f}")
        print(f"  ~$/answer: ${per_answer:.3f}   ~$/need: ${per_need:.3f}")
        print(f"  ≈ job burn: ${job:.2f}")
        if has_remaining:
            rem = []
            if remaining_usd is not None:
                rem.append(f"${float(remaining_usd):.2f}")
            if remaining_pct is not None:
                rem.append(f"{float(remaining_pct):.0f}%")
            print(f"  budget:    {' / '.join(rem)} left"
                  + (f"  (reset {reset})" if reset else "")
                  + (f"  snapshot {budget_age}" if budget_age else ""))
            if impact_pct_of_remaining is not None:
                print(f"  impact:    ~{impact_pct_of_remaining:.0f}% of remaining"
                      + (f"  → ~${after_usd:.2f} left after" if after_usd is not None else ""))
            if after_pct is not None:
                print(f"  after %:   ~{after_pct:.0f}% of included pool")
        else:
            print(f"  budget:    not set — copy Spending into {budget_path}")
            print(f"             (python3 {Path(__file__).name} --write-budget-template)")
        print("  truth:     cursor.com/dashboard → Spending (CLI cannot read remaining %)")

    # Gates
    prefer = bool(budget and budget.get("prefer_cursor_models"))
    floor = float((budget or {}).get("refuse_other_models_below_pct") or 30)
    rem_pct = float(remaining_pct) if remaining_pct is not None else None
    if (
        prefer
        and not args.allow_other_models
        and not is_cursor_model(args.model)
        and rem_pct is not None
        and rem_pct < floor
    ):
        print(
            f"REFUSE: Other Models only ~{rem_pct:.0f}% left (< {floor:.0f}%); "
            f"{args.model} burns that pool.\n"
            f"  Use a Cursor model (e.g. composer-2.5), or pass --allow-other-models.",
            file=sys.stderr,
        )
        return 4
    if args.max_usd and job > args.max_usd:
        print(f"REFUSE: estimate ${job:.2f} > --max-usd {args.max_usd}", file=sys.stderr)
        return 3
    if args.max_pct and impact_pct_of_remaining is not None and impact_pct_of_remaining > args.max_pct:
        print(
            f"REFUSE: ~{impact_pct_of_remaining:.0f}% of remaining > --max-pct {args.max_pct}",
            file=sys.stderr,
        )
        return 3
    if args.max_pct and impact_pct_of_remaining is None and args.require_budget:
        print("REFUSE: --max-pct set but remaining budget unknown", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    # touch updated_at helper unused; keep import honest for future
    _ = datetime, timezone
    raise SystemExit(main())
