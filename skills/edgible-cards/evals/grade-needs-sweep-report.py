#!/usr/bin/env python3
"""Rebuild a graded needs-sweep report from one or more results.json batches.

Binary pass (100% expect) undersells near-misses. This writes report-graded.md with:

  hard-pass  — load OK, no must_not, expect 100%
  near-pass  — load OK, no must_not, expect >= --near-floor (default 70%)
  soft-fail  — load OK, no must_not, expect below floor
  hard-fail  — wrong skill load or must_not broken (or judge error)

Principles table uses Missed = failures/times-applied (no separate Applied column).

Examples:
  python3 grade-needs-sweep-report.py --out ~/edgible-needs-sweep/results/some-batch

  python3 grade-needs-sweep-report.py \\
    --merge ~/edgible-needs-sweep/results/batch-a \\
            ~/edgible-needs-sweep/results/batch-b \\
    --write-dir ~/edgible-needs-sweep/results/merged-graded
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SET = HERE / "needs-sweep.yaml"

EXPECT_STEMS = [
    "offers card(s) for this need before apps with no card",
    "gives each offered card its cards.edgible.org page address",
    "treats fit as",
    "states who reaches it and which auth mode fits",
    "asks a decision question along the lines of",
    "does not deploy or build anything before the person chooses",
    "says self-hosting with Edgible is a",
    "recommends what works instead",
]

PRINCIPLES = [
    "Answers the question the person asked first, before offering anything else.",
    "Gives honest options side by side, including hosted ones where they fit, and states the upkeep of self-hosting.",
    "Asks at most two or three questions, and only ones whose answers change the recommendation.",
    "Builds, deploys, or changes nothing before the person chooses, and does not claim to have done so.",
    "Chooses each hostname's auth mode by who uses it: org only for the person's own team; members, customers, or the public use the app's own accounts.",
    "Raises sensitivity (private or regulated data) and who sees what inside the app, when the need involves it.",
    "Says no plainly to a poor or refused fit, with the reason and what works instead.",
]


def expect_stem(item: str) -> str:
    text = (item or "").strip()
    for stem in EXPECT_STEMS:
        if text.startswith(stem):
            return stem
    return text if len(text) <= 72 else text[:69] + "…"


def load_ids(path: Path) -> list[str]:
    return re.findall(r"^- id: (\S+)$", path.read_text(), re.M)


def grade(r: dict, near_floor: float) -> tuple[str, str]:
    v = r.get("verdict") or {}
    if "error" in v:
        return "hard-fail", "judge error"
    load_ok = r.get("loaded") == r.get("should_load")
    must_broken = bool(r.get("must_not_violated"))
    et, ep = r.get("expect_total") or 0, r.get("expect_passed") or 0
    frac = (ep / et) if et else 0.0
    if not load_ok or must_broken:
        reasons = []
        if not load_ok:
            reasons.append("skill load wrong")
        if must_broken:
            reasons.append("must_not broken")
        return "hard-fail", ", ".join(reasons)
    if et and ep == et:
        return "hard-pass", f"expect {ep}/{et}"
    if frac >= near_floor:
        return "near-pass", f"expect {ep}/{et} ({frac:.0%})"
    return "soft-fail", f"expect {ep}/{et} ({frac:.0%})"


def merge_batches(dirs: list[Path]) -> tuple[list[dict], dict, dict]:
    """Later dirs win on id collisions. Returns results, meta (from last), sources."""
    by: dict[str, dict] = {}
    sources: dict[str, str] = {}
    meta: dict = {}
    for d in dirs:
        path = d / "results.json"
        if not path.is_file():
            sys.exit(f"no results.json in {d}")
        data = json.loads(path.read_text())
        meta = data.get("meta") or meta
        for r in data.get("results") or []:
            rid = r["id"]
            by[rid] = r
            sources[rid] = d.name
    return list(by.values()), meta, sources


def build_report(
    results: list[dict],
    meta: dict,
    sources: dict[str, str],
    *,
    near_floor: float,
    ids_order: list[str],
) -> str:
    graded = []
    for r in results:
        g, note = grade(r, near_floor)
        et, ep = r.get("expect_total") or 0, r.get("expect_passed") or 0
        frac = (ep / et) if et else 0.0
        graded.append({**r, "grade": g, "grade_note": note, "expect_frac": frac})

    by_id = {r["id"]: r for r in graded}
    n = len(graded)
    counts = Counter(g["grade"] for g in graded)
    mean_expect = sum(g["expect_frac"] for g in graded) / n if n else 0.0
    old_pass = sum(1 for r in results if r.get("pass"))
    hp, nr, sf, hf = counts["hard-pass"], counts["near-pass"], counts["soft-fail"], counts["hard-fail"]

    expect_tab: dict = {}
    must_tab: dict = {}
    prin_tab = {p: {"missed": 0, "applied": 0, "prompts": []} for p in PRINCIPLES}
    for r in graded:
        v = r.get("verdict") or {}
        if "error" in v:
            continue
        pid = r["id"]
        seen: set[str] = set()
        for e in v.get("expect", []):
            stem = expect_stem(e.get("item", ""))
            slot = expect_tab.setdefault(stem, {"missed": 0, "scored": 0, "prompts": []})
            slot["scored"] += 1
            if e.get("pass") is not True and stem not in seen:
                seen.add(stem)
                slot["missed"] += 1
                slot["prompts"].append(pid)
        for m in v.get("must_not", []):
            item = m.get("item", "")
            slot = must_tab.setdefault(item, {"violated": 0, "scored": 0, "prompts": []})
            slot["scored"] += 1
            if m.get("violated") is True:
                slot["violated"] += 1
                slot["prompts"].append(pid)
        for p in v.get("principles", []):
            item = p.get("item", "")
            if item not in prin_tab:
                prin_tab[item] = {"missed": 0, "applied": 0, "prompts": []}
            if p.get("pass") is None:
                continue
            prin_tab[item]["applied"] += 1
            if p.get("pass") is False:
                prin_tab[item]["missed"] += 1
                prin_tab[item]["prompts"].append(pid)

    model = meta.get("model") or "?"
    harness = meta.get("harness") or "?"
    judge = f"{meta.get('judge_harness', '?')} / {meta.get('judge_model', '?')}"
    lines = [
        f"# edgible-cards needs sweep (graded), {meta.get('date', str(date.today()))}",
        "",
        f"**Answer model (under test):** `{model}` via harness `{harness}`.",
        f"**Judge:** `{judge}`.",
        f"**Coverage:** {n} scored needs"
        + (f" of {len(ids_order)} in set" if ids_order else "")
        + ".",
        "",
        "## Headline (graded, not binary)",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| **Hard-pass** (load OK, no must_not, expect 100%) | **{hp}/{n}** ({100 * hp / n:.0f}%) |" if n else "| Hard-pass | 0 |",
        f"| **Near-pass** (load OK, no must_not, expect ≥{near_floor:.0%}) | **{nr}/{n}** ({100 * nr / n:.0f}%) |" if n else "| Near-pass | 0 |",
        f"| **Soft-fail** (load OK, no must_not, expect <{near_floor:.0%}) | {sf}/{n} ({100 * sf / n:.0f}%) |" if n else "| Soft-fail | 0 |",
        f"| **Hard-fail** (wrong load or must_not) | {hf}/{n} ({100 * hf / n:.0f}%) |" if n else "| Hard-fail | 0 |",
        f"| **Hard-pass + near-pass** | **{hp + nr}/{n}** ({100 * (hp + nr) / n:.0f}%) |" if n else "| Hard+near | 0 |",
        f"| **Mean expect%** | **{100 * mean_expect:.0f}%** |",
        f"| Old binary pass | {old_pass}/{n} ({100 * old_pass / n:.0f}%) |" if n else "| Old binary | 0 |",
        "",
        "Grading notes:",
        f"- **Hard-pass:** skill load correct, no `must_not` broken, every expect item passed.",
        f"- **Near-pass:** same safety bar, expect in [{near_floor:.0%}, 100%).",
        f"- **Soft-fail:** safe load/must_not, expect below {near_floor:.0%}.",
        f"- **Hard-fail:** wrong skill load or a `must_not` violation (or judge error).",
        "- Principles: **Missed** is failures / times applied (n/a prompts omitted from the denominator).",
        "",
        "## Per need",
        "",
        "| Prompt | Grade | expect | must_not | Principles missed | Note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    order_ids = ids_order if ids_order else sorted(by_id)
    for rid in order_ids:
        r = by_id.get(rid)
        if not r:
            lines.append(f"| {rid} | — | — | — | — | not scored |")
            continue
        et, ep = r.get("expect_total") or 0, r.get("expect_passed") or 0
        lines.append(
            f"| {r['id']} | {r['grade']} | {ep}/{et} ({r['expect_frac']:.0%}) | "
            f"{len(r.get('must_not_violated') or [])} | {len(r.get('principles_failed') or [])} | "
            f"{r['grade_note']} |"
        )
    for rid, r in sorted(by_id.items()):
        if rid not in order_ids:
            et, ep = r.get("expect_total") or 0, r.get("expect_passed") or 0
            lines.append(
                f"| {r['id']} | {r['grade']} | {ep}/{et} ({r['expect_frac']:.0%}) | "
                f"{len(r.get('must_not_violated') or [])} | {len(r.get('principles_failed') or [])} | "
                f"{r['grade_note']} |"
            )

    lines += ["", "## By grade band", ""]
    for band in ("hard-pass", "near-pass", "soft-fail", "hard-fail"):
        ids = [g["id"] for g in graded if g["grade"] == band]
        lines += [f"### {band} ({len(ids)})", "", (", ".join(ids) if ids else "*(none)*"), ""]

    lines += [
        "## Criteria across this batch",
        "",
        f"Miss rates over **{n}** scored needs.",
        "",
        "### Expect items",
        "",
        "| Criterion | Missed | Scored | Prompts |",
        "| --- | ---: | ---: | --- |",
    ]
    for stem, slot in sorted(expect_tab.items(), key=lambda kv: (-kv[1]["missed"], -kv[1]["scored"], kv[0])):
        prompts = ", ".join(slot["prompts"][:8]) + (", …" if len(slot["prompts"]) > 8 else "")
        lines.append(f"| {stem} | {slot['missed']}/{n} | {slot['scored']} | {prompts or '—'} |")

    lines += [
        "",
        "### Principles",
        "",
        "Missed = failures / times applied.",
        "",
        "| Principle | Missed | Prompts |",
        "| --- | ---: | --- |",
    ]
    for item in PRINCIPLES:
        slot = prin_tab.get(item, {"missed": 0, "applied": 0, "prompts": []})
        if slot["applied"] == 0:
            lines.append(f"| {item} | — | not tested |")
            continue
        prompts = ", ".join(slot["prompts"][:8]) + (", …" if len(slot["prompts"]) > 8 else "")
        lines.append(f"| {item} | {slot['missed']}/{slot['applied']} | {prompts or '—'} |")

    violated = [(k, v) for k, v in must_tab.items() if v["violated"]]
    lines += ["", "### must_not broken", ""]
    if not violated:
        lines.append("None broken in this batch.")
    else:
        lines += ["| must_not | Broken | Prompts |", "| --- | ---: | --- |"]
        for item, slot in sorted(violated, key=lambda kv: (-kv[1]["violated"], kv[0])):
            lines.append(f"| {item} | {slot['violated']}/{n} | {', '.join(slot['prompts'])} |")

    lines += ["", "## Details (near-pass, soft-fail, hard-fail only)", ""]
    for r in graded:
        if r["grade"] == "hard-pass":
            continue
        v = r.get("verdict") or {}
        lines.append(f"### {r['id']}: {r['grade']} — {r['grade_note']}")
        if "error" in v:
            lines += ["", f"- Judge error: {v['error']}", ""]
            continue
        for label, group in (
            ("Missed", [e for e in v.get("expect", []) if e.get("pass") is not True]),
            ("Broke", [m for m in v.get("must_not", []) if m.get("violated") is True]),
            ("Principle missed", [p for p in v.get("principles", []) if p.get("pass") is False]),
        ):
            for item in group:
                lines.append(f"- {label}: {item.get('item', '')}. {item.get('evidence', '')}")
        if v.get("better"):
            lines.append(f"- Would be better: {v['better']}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, help="single results directory (writes report-graded.md there)")
    ap.add_argument("--merge", nargs="+", type=Path, metavar="DIR",
                    help="merge several results dirs (later wins on id); requires --write-dir")
    ap.add_argument("--write-dir", type=Path, help="output dir for --merge (results.json + report-graded.md)")
    ap.add_argument("--near-floor", type=float, default=0.70, help="near-pass expect fraction (default 0.70)")
    ap.add_argument("--set", type=Path, default=DEFAULT_SET, help="needs-sweep.yaml for prompt order")
    args = ap.parse_args(argv)

    if args.merge:
        if not args.write_dir:
            sys.exit("--merge requires --write-dir")
        results, meta, sources = merge_batches(args.merge)
        write_dir = args.write_dir
        write_dir.mkdir(parents=True, exist_ok=True)
        meta = dict(meta)
        meta["graded_merge_from"] = [str(p) for p in args.merge]
        meta["sources"] = sources
        (write_dir / "results.json").write_text(
            json.dumps({"meta": meta, "results": results}, indent=2) + "\n"
        )
    elif args.out:
        results, meta, sources = merge_batches([args.out])
        write_dir = args.out
    else:
        sys.exit("pass --out DIR or --merge DIR… --write-dir DIR")

    ids_order = load_ids(args.set) if args.set.is_file() else []
    # Prefer needs-map order among scored; drop unscored from ordering noise when single batch
    report = build_report(results, meta, sources, near_floor=args.near_floor, ids_order=ids_order)
    path = write_dir / "report-graded.md"
    path.write_text(report)
    n = len(results)
    mean = sum(
        ((r.get("expect_passed") or 0) / (r.get("expect_total") or 1))
        for r in results
        if r.get("expect_total")
    ) / max(1, sum(1 for r in results if r.get("expect_total")))
    print(f"wrote {path} ({n} needs, mean expect ~{mean:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
