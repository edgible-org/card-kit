#!/usr/bin/env python3
"""Draft needs-sweep.yaml from needs-map.yaml, and sample batches without replacement.

    python3 make-needs-sweep.py --write-set          # rewrite needs-sweep.yaml from the map
    python3 make-needs-sweep.py --sample 10 --seed 20261109

The prompt set lives in this folder. The ledger of drawn ids lives outside the card-kit
repo (default ~/edgible-needs-sweep/needs-sweep-ledger.json) so sampling does not dirty git.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
NEEDS_MAP = SKILL / "needs-map.yaml"
SET_PATH = HERE / "needs-sweep.yaml"
DEFAULT_DATA = Path(os.environ.get("EDGIBLE_NEEDS_SWEEP_DIR", Path.home() / "edgible-needs-sweep"))
LEDGER_NAME = "needs-sweep-ledger.json"


def slug(category: str) -> str:
    s = category.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def parse_list(text: str) -> list[str]:
    """Parse a YAML [a, b, "c, d"] list without a YAML library."""
    inner = text.strip()
    if not (inner.startswith("[") and inner.endswith("]")):
        return []
    inner = inner[1:-1].strip()
    if not inner:
        return []
    items, buf, in_str, quote = [], [], False, ""
    i = 0
    while i < len(inner):
        ch = inner[i]
        if in_str:
            buf.append(ch)
            if ch == quote and (len(buf) < 2 or buf[-2] != "\\"):
                in_str = False
            i += 1
            continue
        if ch in "\"'":
            in_str = True
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == ",":
            item = "".join(buf).strip().strip("\"'")
            if item:
                items.append(item)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    item = "".join(buf).strip().strip("\"'")
    if item:
        items.append(item)
    return items


def parse_needs_map(path: Path) -> list[dict]:
    text = path.read_text()
    chunks = re.split(r"(?m)^- category: ", text)[1:]
    entries = []
    for chunk in chunks:
        lines = chunk.splitlines()
        category = lines[0].strip()
        body = "\n".join(lines[1:])
        jobs_m = re.search(r"(?m)^  jobs: (\[.*\])\s*$", body)
        replaces_m = re.search(r"(?m)^  replaces: (\[.*\])\s*$", body)
        cards_m = re.search(r"(?m)^  cards: (\[.*\])\s*$", body)
        ask_m = re.search(r"(?m)^  ask: (\[.*\])\s*$", body)
        fit_m = re.search(r"(?m)^  fit: \{rating:\s*(\w+),\s*why:\s*(.+)\}\s*$", body)
        exp_default = re.search(r"(?m)^    default: (.+)$", body)
        why = ""
        rating = "good"
        if fit_m:
            rating = fit_m.group(1)
            why = fit_m.group(2).strip().strip('"')
        entries.append({
            "category": category,
            "id": slug(category),
            "jobs": parse_list(jobs_m.group(1)) if jobs_m else [],
            "replaces": parse_list(replaces_m.group(1)) if replaces_m else [],
            "cards": parse_list(cards_m.group(1)) if cards_m else [],
            "ask": parse_list(ask_m.group(1)) if ask_m else [],
            "fit": rating,
            "fit_why": why,
            "exposure_default": exp_default.group(1).strip().strip('"') if exp_default else "",
        })
    return entries


def yaml_quote(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def draft_prompt(entry: dict) -> str:
    job = entry["jobs"][0] if entry["jobs"] else entry["category"]
    replaces = entry["replaces"]
    if replaces:
        return (
            f"I want to {job}. I've been using {replaces[0]} and I'm looking for something "
            f"I can run myself. What would you recommend?"
        )
    return f"I want to {job}. Is there a good way to do that myself, without a hosted service?"


def draft_expect(entry: dict) -> list[str]:
    expect = []
    fit = entry["fit"]
    if fit in ("poor", "refused"):
        expect.append(
            f"says self-hosting with Edgible is a {fit} fit for this need, with the reason"
        )
        expect.append("recommends what works instead (hosted or home-network-only as appropriate)")
    else:
        if entry["cards"]:
            named = ", ".join(entry["cards"][:3])
            expect.append(
                f"offers card(s) for this need before apps with no card: {named}"
            )
            expect.append("gives each offered card its cards.edgible.org page address")
        expect.append(
            f"treats fit as {fit}" + (f" ({entry['fit_why']})" if entry["fit_why"] else "")
        )
        if entry["exposure_default"]:
            expect.append(
                "states who reaches it and which auth mode fits "
                f"(from the needs map: {entry['exposure_default']})"
            )
    for q in entry["ask"][:2]:
        expect.append(f"asks a decision question along the lines of: {q}")
    expect.append("does not deploy or build anything before the person chooses")
    return expect


def draft_must_not(entry: dict) -> list[str]:
    items = [
        "build, deploy, or change anything before the person chooses",
        "claim to have already set the app up",
    ]
    if entry["fit"] in ("poor", "refused"):
        items.append("push self-hosting with Edgible as the only or best path")
    if entry["fit"] == "refused":
        items.append("offer to publish this as an Edgible app card")
    return items


def write_set(entries: list[dict], path: Path) -> None:
    lines = [
        "# Needs-sweep prompts: one per needs-map category. Used to learn and improve the skill.",
        "# Not held-out: you may tune against findings from these. Regenerated by make-needs-sweep.py --write-set.",
        "# Shape matches run-evals.py (id, prompt, expect, must_not).",
        "",
    ]
    for e in entries:
        lines.append(f"# category: {e['category']} (fit: {e['fit']})")
        lines.append(f"- id: {e['id']}")
        lines.append(f"  prompt: {yaml_quote(draft_prompt(e))}")
        lines.append("  expect:")
        for item in draft_expect(e):
            lines.append(f"    - {item}")
        lines.append("  must_not:")
        for item in draft_must_not(e):
            lines.append(f"    - {item}")
        lines.append("")
    path.write_text("\n".join(lines))


def load_ids_from_set(path: Path) -> list[str]:
    ids = []
    for line in path.read_text().splitlines():
        m = re.match(r"^- id: (\S+)$", line)
        if m:
            ids.append(m.group(1))
    return ids


def data_dir(path: Path | None) -> Path:
    root = path or DEFAULT_DATA
    root.mkdir(parents=True, exist_ok=True)
    return root


def load_ledger(path: Path) -> dict:
    if not path.is_file():
        return {"drawn": [], "batches": []}
    return json.loads(path.read_text())


def save_ledger(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2) + "\n")


def sample(ids: list[str], n: int, seed: int, ledger_path: Path, commit: bool) -> list[str]:
    ledger = load_ledger(ledger_path)
    drawn = set(ledger.get("drawn", []))
    remaining = [i for i in ids if i not in drawn]
    if not remaining:
        sys.exit(f"no needs left in the pool ({len(drawn)} drawn). Use --reset-ledger for a new epoch.")
    rng = random.Random(seed)
    take = min(n, len(remaining))
    chosen = rng.sample(remaining, take)
    print(f"seed={seed} sample={take} remaining_before={len(remaining)} remaining_after={len(remaining) - take}")
    print("chosen:")
    for i in chosen:
        print(f"  {i}")
    if commit:
        ledger.setdefault("drawn", []).extend(chosen)
        ledger.setdefault("batches", []).append({
            "date": str(date.today()),
            "seed": seed,
            "ids": chosen,
        })
        save_ledger(ledger_path, ledger)
        print(f"ledger updated: {ledger_path} ({len(ledger['drawn'])} drawn total)")
    else:
        print("ledger not updated (--no-commit)")
    # Write last sample for the shell wrapper to pick up.
    last = ledger_path.parent / "last-sample.json"
    last.write_text(json.dumps({"date": str(date.today()), "seed": seed, "ids": chosen}, indent=2) + "\n")
    print(f"last sample: {last}")
    return chosen


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write-set", action="store_true", help=f"rewrite {SET_PATH.name} from needs-map.yaml")
    ap.add_argument("--sample", type=int, metavar="N", help="draw N unused needs without replacement")
    ap.add_argument("--seed", type=int, default=int(date.today().strftime("%Y%m%d")))
    ap.add_argument("--data-dir", type=Path, default=None, help=f"ledger/results root (default {DEFAULT_DATA})")
    ap.add_argument("--ledger", type=Path, default=None, help="ledger path (default <data-dir>/needs-sweep-ledger.json)")
    ap.add_argument("--no-commit", action="store_true", help="print a sample without updating the ledger")
    ap.add_argument("--reset-ledger", action="store_true", help="clear the ledger (new epoch)")
    ap.add_argument("--release-unscored", nargs="+", metavar="ID",
                    help="remove these ids from the ledger so they can be drawn again")
    ap.add_argument("--status", action="store_true", help="print drawn / remaining counts")
    args = ap.parse_args(argv)

    root = data_dir(args.data_dir)
    ledger_path = args.ledger or (root / LEDGER_NAME)

    if args.write_set:
        entries = parse_needs_map(NEEDS_MAP)
        write_set(entries, SET_PATH)
        print(f"wrote {len(entries)} scenarios to {SET_PATH}")

    if args.reset_ledger:
        save_ledger(ledger_path, {"drawn": [], "batches": []})
        print(f"reset ledger: {ledger_path}")

    if args.release_unscored:
        ledger = load_ledger(ledger_path)
        release = set(args.release_unscored)
        ledger["drawn"] = [i for i in ledger.get("drawn", []) if i not in release]
        for batch in ledger.get("batches", []):
            batch["ids"] = [i for i in batch.get("ids", []) if i not in release]
        save_ledger(ledger_path, ledger)
        print(f"released {sorted(release)}; drawn now {len(ledger['drawn'])}")

    if not SET_PATH.is_file() and (args.sample or args.status):
        sys.exit(f"{SET_PATH} missing; run with --write-set first")

    ids = load_ids_from_set(SET_PATH) if SET_PATH.is_file() else []

    if args.status:
        ledger = load_ledger(ledger_path)
        drawn = set(ledger.get("drawn", []))
        remaining = [i for i in ids if i not in drawn]
        print(f"total={len(ids)} drawn={len(drawn)} remaining={len(remaining)}")
        print(f"ledger={ledger_path}")

    if args.sample is not None:
        if args.sample < 1:
            sys.exit("--sample must be >= 1")
        sample(ids, args.sample, args.seed, ledger_path, commit=not args.no_commit)

    if not (args.write_set or args.sample is not None or args.status or args.reset_ledger or args.release_unscored):
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
