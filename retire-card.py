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

Removing a card is a person's decision. With --remove it then makes the edits, on a new branch of the
cards repo and one commit, and stops there: it never pushes or opens anything. The edits are the card's
folder, its row in the catalog table, and its name in each upstream/ request's `cards:` list (a request
left with no card is never deleted: it is about the app, so a person decides). With --kit PATH
it also takes the card out of the `cards:` lists in the skill's needs map in that card-kit checkout (its
own branch and commit; never ~/.card-kit, which the installed skill links to). Everything else it found
is only reported, because a person has to read it.

    python3 retire-card.py canary --remove
    python3 retire-card.py canary --remove --kit ~/CC/card-kit-catalog-site

It refuses to remove a card another card depends on unless --force, and refuses a working tree with
uncommitted changes.

The gentler step, with --deprecate: keep the card listed and say plainly not to start new setups on it.

    python3 retire-card.py canary --deprecate --replaced-by canary2 --reason "its test is no longer maintained"

On a new branch, in one commit: `status: deprecated` (and `replaced-by:` when given) in card.yml, and a
note under the README's title. Neither changes the card's test fingerprint, so nothing is retested. The
site shows a Deprecated pill and a note at the top of the card's page. Nothing is pushed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
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


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {out.stderr.strip()}")
    return out.stdout


def without(items: str, name: str) -> list[str]:
    return [i.strip() for i in items.split(",") if i.strip() and i.strip() != name]


def edit_readme(root: Path, name: str) -> str:
    path = root / "README.md"
    if not path.is_file():
        return ""
    lines = path.read_text().split("\n")
    keep = [l for l in lines if not re.match(rf"\|\s*\[{re.escape(name)}\]\({re.escape(name)}\)\s*\|", l)]
    if len(keep) == len(lines):
        return ""
    path.write_text("\n".join(keep))
    return f"README.md: removed {len(lines) - len(keep)} catalog row(s)"


def edit_upstream(root: Path, name: str) -> list[str]:
    done = []
    for f in sorted((root / "upstream").glob("*.md")):
        if f.name == "README.md":
            continue
        text = f.read_text()
        m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
        if not m:
            continue
        head = m.group(1)
        c = re.search(r"(?m)^cards:\s*\[([^\]]*)\]\s*$", head)
        if not c or name not in [i.strip() for i in c.group(1).split(",")]:
            continue
        rest = without(c.group(1), name)
        status = (re.search(r"(?m)^status:\s*(\S+)", head) or [None, ""])[1]
        if rest:
            f.write_text(text.replace(c.group(0), f"cards: [{', '.join(rest)}]", 1))
            done.append(f"upstream/{f.name}: took {name} out of cards:")
        else:
            # The request is about the app, and stays true when its card goes: a person decides whether to
            # send it, keep it under another card, or drop it.
            done.append(f"upstream/{f.name}: NEEDS A PERSON: status {status or '?'}, and it only names {name}; "
                        "left as it is, and check-cards will object until it names a card or goes")
    return done


def edit_needs_map(kit: Path, name: str) -> list[str]:
    path = kit / "skills" / "edgible-cards" / "needs-map.yaml"
    if not path.is_file():
        return [f"{kit}: no skills/edgible-cards/needs-map.yaml"]
    out, text = [], path.read_text()

    def fix(m: re.Match) -> str:
        items = [i.strip() for i in m.group(2).split(",") if i.strip()]
        if name not in items:
            return m.group(0)
        out.append(f"needs-map.yaml: {name} out of a cards: list ({m.group(2).strip()})")
        return f"{m.group(1)}[{', '.join(i for i in items if i != name)}]"

    new = re.sub(r"(?m)^(\s*cards:\s*)\[([^\]]*)\]", fix, text)
    if new != text:
        path.write_text(new)
    return out


def remove(root: Path, name: str, kit: Path | None, force: bool, deps: list[str]) -> int:
    if deps and not force:
        print(f"Refusing: {', '.join(deps)} depend on {name}. Decide about them first, or pass --force.", file=sys.stderr)
        return 1
    for repo in [root] + ([kit] if kit else []):
        if git(repo, "status", "--porcelain").strip():
            print(f"Refusing: {repo} has uncommitted changes.", file=sys.stderr)
            return 2
    branch = f"retire-{name}"
    git(root, "checkout", "-q", "-b", branch)
    git(root, "rm", "-rq", name)
    notes = [f"{name}/: folder removed"]
    for step in (edit_readme(root, name),):
        if step:
            notes.append(step)
    notes += edit_upstream(root, name)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", f"Remove the {name} card\n\nMade by retire-card --remove, on a person's decision.")
    print(f"cards repo, branch {branch}, one commit:")
    for n in notes:
        print(f"  {n}")
    if kit:
        git(kit, "checkout", "-q", "-b", branch)
        kit_notes = edit_needs_map(kit, name)
        if kit_notes:
            git(kit, "add", "-A")
            git(kit, "commit", "-q", "-m", f"Needs map: take {name} out\n\nIts card was removed from the catalog.")
            print(f"card-kit ({kit}), branch {branch}, one commit:")
            for n in kit_notes:
                print(f"  {n}")
        else:
            git(kit, "checkout", "-q", "-")
            git(kit, "branch", "-q", "-D", branch)
            print(f"card-kit ({kit}): nothing to change in the needs map")
    print("\nNothing was pushed. Read the branch, then push it and open the pull request yourself. "
          "Still mentioned, and for a person to read:")
    left = [m for m in scan(root, name, None, "cards") if m["kind"] == "firm"]
    for m in left:
        print(f"  {m['file']}:{m['line']}  {m['text']}")
    print("Also: the card's entry in the nightly status (the test-status branch) and its badge are not touched.")
    return 0


def deprecate(root: Path, name: str, replaced_by: str, reason: str) -> int:
    if replaced_by and not (root / replaced_by / "card.yml").is_file():
        print(f"Refusing: --replaced-by {replaced_by} is not a card here.", file=sys.stderr)
        return 2
    if git(root, "status", "--porcelain").strip():
        print(f"Refusing: {root} has uncommitted changes.", file=sys.stderr)
        return 2
    card_yml = root / name / "card.yml"
    text = card_yml.read_text()
    if re.search(r"(?m)^  status:\s*deprecated\s*$", text):
        print(f"{name} is already deprecated.", file=sys.stderr)
        return 2
    extra = "  status: deprecated\n" + (f"  replaced-by: {replaced_by}\n" if replaced_by else "")
    text = re.sub(r"(?m)^  (?:status|replaced-by):[^\n]*\n", "", text)
    m = None
    for key in ("steward", "license", "homepage", "added", "description"):
        found = list(re.finditer(rf"(?m)^  {key}:[^\n]*\n", text))
        if found:
            m = found[0]
            break
    if not m:
        print(f"{card_yml}: no metadata line to put it after.", file=sys.stderr)
        return 2
    card_yml.write_text(text[:m.end()] + extra + text[m.end():])
    sentence = ("**Deprecated.** " + (reason.rstrip(". ") + ". " if reason else "")
                + "Do not start a new setup on this card."
                + (f" Use [{replaced_by}](../{replaced_by}/) instead." if replaced_by else ""))
    readme = root / name / "README.md"
    if readme.is_file() and "**Deprecated.**" not in readme.read_text():
        lines = readme.read_text().split("\n")
        at = next((i for i, l in enumerate(lines) if l.startswith("# ")), -1) + 1
        lines[at:at] = ["", "> " + sentence]
        readme.write_text("\n".join(lines))
    branch = f"deprecate-{name}"
    git(root, "checkout", "-q", "-b", branch)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", f"Deprecate the {name} card\n\n{reason or 'On a person' + chr(39) + 's decision.'}\n"
                                    "Made by retire-card --deprecate.")
    print(f"cards repo, branch {branch}, one commit: {name} is deprecated"
          + (f", replaced by {replaced_by}" if replaced_by else "")
          + ". Nothing was pushed. The test fingerprint ignores both lines, so nothing is retested.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="What removing a card would touch.")
    ap.add_argument("card")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--loose", action="store_true", help="also list the loose mentions")
    ap.add_argument("--remove", action="store_true", help="make the edits on a new branch, in one commit; nothing is pushed")
    ap.add_argument("--kit", type=Path, metavar="PATH", help="with --remove: also edit the needs map in this card-kit checkout")
    ap.add_argument("--force", action="store_true", help="with --remove: even when another card depends on it")
    ap.add_argument("--deprecate", action="store_true", help="keep the card listed, marked deprecated, on a new branch")
    ap.add_argument("--replaced-by", metavar="CARD", default="", help="with --deprecate: the card that replaces it")
    ap.add_argument("--reason", default="", help="with --deprecate: why, in a sentence")
    args = ap.parse_args(argv)
    root = Path.cwd()
    own = root / args.card
    if not (own / "card.yml").is_file():
        print(f"{args.card}: not a card here (run it from the root of a cards repo)", file=sys.stderr)
        return 2
    if args.deprecate:
        return deprecate(root, args.card, args.replaced_by, args.reason)
    if args.remove:
        return remove(root, args.card, args.kit.resolve() if args.kit else None, args.force, dependents(root, args.card))
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
