#!/usr/bin/env python3
"""What removing a card from the catalog would touch, before anyone does it.

Run it from the root of a cards repo:

    python3 retire-card.py canary
    python3 retire-card.py canary --json

It changes nothing. It lists every place that mentions the card, outside the card's own folder, in this
cards repo and in the card-kit checkout this file sits in: the catalog table, requests in upstream/ that
name it, other cards that use it, the skill's needs map, tests and examples. A mention is *firm* when it
is a path or link to the card (`canary/`, `/canary/`), a name in a `cards:` or `needs:` list, or a table
row for it, and *loose* when it is only the word (short names such as `ci` match ordinary words, so
loose ones are counted, and shown with --loose).

It exits 1 when another card depends on this one (a pattern that includes it), because removing it
would break that card: say so first, then decide. It exits 0 otherwise, 2 when it cannot run.

Removing a card is a person's decision. This tool only shows the cost; a later step makes the edits as
a pull request.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
SKIP_DIRS = {".git", "node_modules", "_site", "_site_try", "__pycache__", ".card-kit", ".native"}
TEXT = {".md", ".yml", ".yaml", ".py", ".sh", ".mjs", ".js", ".json", ".txt", ".env", ""}


def files(root: Path, own: Path | None):
    for p in sorted(root.rglob("*")):
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        if (own and own in p.parents) or p == Path(__file__).resolve():
            continue
        if p.suffix in TEXT and p.stat().st_size < 400_000:
            yield p


def scan(root: Path, name: str, own: Path | None, label: str) -> list[dict]:
    n = re.escape(name)
    firm = re.compile(
        rf"(?:\]\({n}\)|\[{n}\]|(?:tree|blob)/main/{n}\b|edgible\.org/{n}/|\.\./{n}/|(?<![\w/.:-]){n}/|"
        rf"(?:cards|needs|provides|depends|pairs)\s*:\s*\[[^\]]*(?<![\w-]){n}(?![\w-])|"
        rf"^\s*-\s*{n}\s*$|\|\s*{n}\s*\|)", re.M)
    word = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
    found = []
    for p in files(root, own):
        try:
            text = p.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            kind = "firm" if firm.search(line) else ("loose" if word.search(line) else "")
            if kind:
                found.append({"where": label, "file": p.relative_to(root).as_posix(), "line": n,
                              "kind": kind, "text": line.strip()[:140]})
    return found


def dependents(root: Path, name: str) -> list[str]:
    """Other cards that use this one: a pattern that lists it, or a card whose Compose or card.yml names
    its folder. Read from files only."""
    out = []
    for card in sorted(root.glob("*/card.yml")):
        other = card.parent.name
        if other == name:
            continue
        text = "\n".join(p.read_text() for p in [card, *card.parent.glob("*compose*.yml")] if p.is_file())
        if re.search(rf"\.\./{re.escape(name)}/|from card {re.escape(name)}\b|"
                     rf"(?:includes|parts|uses|needs|provides)\s*:\s*\[[^\]]*(?<![\w-]){re.escape(name)}(?![\w-])", text):
            out.append(other)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="What removing a card would touch.")
    ap.add_argument("card")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--loose", action="store_true", help="also list the loose mentions")
    args = ap.parse_args(argv)
    root = Path.cwd()
    own = root / args.card
    if not (own / "card.yml").is_file():
        print(f"{args.card}: not a card here (run it from the root of a cards repo)", file=sys.stderr)
        return 2
    mentions = scan(root, args.card, own, "cards") + (scan(KIT, args.card, None, "card-kit") if KIT != root else [])
    deps = dependents(root, args.card)
    firm = [m for m in mentions if m["kind"] == "firm"]
    loose = [m for m in mentions if m["kind"] == "loose"]
    if args.json:
        print(json.dumps({"card": args.card, "dependents": deps, "firm": firm, "loose": len(loose)}, indent=1))
        return 1 if deps else 0
    print(f"Removing {args.card} would touch its folder ({sum(1 for _ in own.rglob('*') if _.is_file())} files) and:")
    if deps:
        print(f"\nDEPENDS ON IT: {', '.join(deps)}. Removing it would break these; decide about them first.")
    for label in ("cards", "card-kit"):
        rows = [m for m in firm if m["where"] == label]
        print(f"\nFirm mentions in {label} ({len(rows)}):")
        for m in rows:
            print(f"  {m['file']}:{m['line']}  {m['text']}")
    print(f"\nLoose mentions (the word alone): {len(loose)}" + (" (use --loose to list)" if loose and not args.loose else ""))
    if args.loose:
        for m in loose:
            print(f"  {m['where']}/{m['file']}:{m['line']}  {m['text']}")
    print("\nAlso outside the files: the card's nightly status and badge, any open Renovate pull request or "
          "issue about it, and anything that links to its page on the site.")
    return 1 if deps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
