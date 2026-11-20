#!/usr/bin/env python3
"""Leave a published app's appPaths to its own login, the way its card.yml says.

Run it wherever `edgible` is logged in, after Publish, with the card's directory and the app:

    python3 app-paths.py vaultwarden vaultwarden --dry-run
    python3 app-paths.py vaultwarden vaultwarden
    python3 app-paths.py vaultwarden vaultwarden --name family-vault

An app on org is behind Edgible's sign-in, which clients that are not a web browser, such as
phone apps and browser extensions, cannot pass. card.yml's appPaths names the paths those
clients call, and what protects them:

    authModes: [org]
    appPaths:
      - paths: [/api/*, /icons/*]
        for: the Bitwarden apps' vault calls, each with a Vaultwarden token

Edgible keeps the rest of the app behind its sign-in and sends these paths straight to the
app (a path policy with auth mode app-native, with for as its reason). The CLI has no flag for
path policies, so this exports the app's declaration, sets them, and deploys it again with
`edgible stack deploy`. Running it twice changes nothing more.

--name is the app's name in Edgible when it is not the card's name for it. --dry-run prints the
path policies it would set and changes nothing. The exported declaration holds the app's
settings in full, so it is written to a private temporary folder and removed after.

Needs python3 and the Edgible CLI. Only the standard library, because it runs on a fresh machine.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1].replace("''", "'") if s[0] == "'" else json.loads(s)
    return s


def app_paths(card_yml: Path, app: str) -> list[dict]:
    """appPaths of one application in card.yml, read without pyyaml: each item is
    `- paths: [/a, /b/*]` and `for: text`, in either order."""
    text = card_yml.read_text()
    block = next((b for b in re.split(r"\n\s*- name: ", text.split("\nsecrets:")[0])[1:]
                  if b.split("\n", 1)[0].strip() == app), None)
    if block is None:
        sys.exit(f"{card_yml} has no application named {app}")
    lines = block.split("\n")
    start = next((i for i, l in enumerate(lines) if re.match(r"^\s+appPaths:\s*$", l)), None)
    if start is None:
        return []
    indent = len(lines[start]) - len(lines[start].lstrip())
    items: list[dict] = []
    for line in lines[start + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        m = re.match(r"^\s*(-\s+)?(paths|for):\s*(.+?)\s*$", line)
        if not m:
            continue
        if m.group(1) or not items:
            items.append({})
        key, value = m.group(2), m.group(3)
        items[-1][key] = ([unquote(p) for p in value.strip("[]").split(",") if p.strip()]
                          if key == "paths" else unquote(value))
    for item in items:
        if not item.get("paths") or not item.get("for"):
            sys.exit(f"{card_yml}: each appPaths item needs paths and for")
    return items


def policies(items: list[dict]) -> list[dict]:
    return [{"paths": i["paths"], "modes": ["app-native"], "justification": i["for"]} for i in items]


def with_policies(declaration: str, pp: list[dict]) -> tuple[str, int]:
    """The exported YAML with pathPolicies set under each access's policies.auth, replacing any
    there. pathPolicies is written as one JSON line, which YAML reads as it is."""
    lines, out, done = declaration.split("\n"), [], 0
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = re.match(r"^(\s*)auth:\s*$", line)
        prev = next((l for l in reversed(out[:-1]) if l.strip()), "")
        if m and re.match(rf"^\s*policies:\s*$", prev) and len(prev) - len(prev.lstrip()) < len(m.group(1)):
            base = len(m.group(1))
            body = []
            i += 1
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > base):
                body.append(lines[i])
                i += 1
            child = next((len(l) - len(l.lstrip()) for l in body if l.strip()), base + 2)
            # Drop an existing pathPolicies key and everything under it.
            kept, skipping = [], False
            for l in body:
                ind = len(l) - len(l.lstrip())
                if l.strip() and ind == child:
                    skipping = l.strip().startswith("pathPolicies:")
                if not skipping:
                    kept.append(l)
            out += kept + [" " * child + "pathPolicies: " + json.dumps(pp)]
            done += 1
            continue
        i += 1
    return "\n".join(out), done


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("card", type=Path, help="the card's directory")
    ap.add_argument("app", help="the application's name in card.yml")
    ap.add_argument("--name", help="its name in Edgible, when not the same")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    items = app_paths(args.card / "card.yml", args.app)
    if not items:
        print(f"{args.app} has no appPaths in card.yml: nothing to do")
        return 0
    pp = policies(items)
    name = args.name or args.app
    for p in pp:
        print(f"{name}: {', '.join(p['paths'])} reach the app's own login ({p['justification']})")
    if args.dry_run:
        return 0
    with tempfile.TemporaryDirectory(prefix="app-paths-") as tmp:
        f = Path(tmp) / "edgible.yml"
        r = subprocess.run(["edgible", "app", "export", name, "--out-file", str(f)], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"edgible app export {name} failed: {(r.stderr or r.stdout).strip()[:400]}")
        text, done = with_policies(f.read_text(), pp)
        if not done:
            sys.exit(f"{name}'s declaration has no access with an auth policy to add path policies to")
        f.write_text(text)
        r = subprocess.run(["edgible", "stack", "deploy", "-f", str(f)], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"edgible stack deploy failed: {(r.stderr or r.stdout).strip()[-600:]}")
    print(f"{name}: path policies set on {done} hostname{'s' if done > 1 else ''}; the rest stays behind Edgible's sign-in")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
