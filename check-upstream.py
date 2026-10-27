#!/usr/bin/env python3
"""Find what cards work around that an app's author could fix, and say which have no request yet.

Run it from the root of a cards repo:

    python3 check-upstream.py
    python3 check-upstream.py --json

It reads each card's card.yml, docker-compose.yml files and test.yml, changes nothing, and looks
for two things in the card's own app (the image named by `from:` in card.yml):

    secret-files   the card starts the app through an entrypoint that loads its secrets from
                   files and exports them, because the app reads them from the environment only
    healthcheck    the card declares a healthcheck for the app, and test.yml's image_facts say
                   the image has none of its own

A finding is a candidate, not a fact about the app: whether the app really has no `*_FILE`
setting, or no healthcheck, is checked against its source or docs before a request is written.
A candidate is left out when upstream/ already has a request for that card and topic, whatever
its status (a file named <card>-<topic>.md, or any file that names the card and ends -<topic>.md).

Exit 0 always, unless it cannot run (2).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

TOPICS = ("secret-files", "healthcheck")
# A pinned reference as the card writes it: ${VAR:-default}, or a plain image.
DEFAULT = re.compile(r"\$\{[A-Z0-9_]+:?-([^}]*)\}")
LOADER = re.compile(r"card-secrets/\.load|_FILE\b")


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}


def image_of(service: dict) -> str:
    """The image a Compose service uses, with ${VAR:-default} resolved to its default."""
    return DEFAULT.sub(r"\1", str(service.get("image", "")))


def same_image(a: str, b: str) -> bool:
    return bool(a) and bool(b) and (a == b or a.split("@")[0].split(":")[0] == b.split("@")[0].split(":")[0])


def app_images(card: Path) -> list[str]:
    """The images of the card's own apps, as card.yml names them, except those the card's owners
    build themselves, which are not another project's."""
    apps = load_yaml(card / "card.yml").get("applications") or []
    return [a["from"] for a in apps if isinstance(a, dict) and a.get("from")
            and "edgible-org" not in a["from"]]


def candidates(card: Path) -> list[dict]:
    images = app_images(card)
    facts = (load_yaml(card / "test.yml").get("image_facts") or {})
    found, seen = [], set()
    for compose in sorted(card.glob("*.y*ml")):
        services = (load_yaml(compose).get("services") or {}) if "compose" in compose.name else {}
        for name, service in services.items():
            if not isinstance(service, dict):
                continue
            image = next((i for i in images if same_image(image_of(service), i)), "")
            if not image:
                continue
            entry = service.get("entrypoint")
            entry = " ".join(entry) if isinstance(entry, list) else str(entry or "")
            if LOADER.search(entry) and "secret-files" not in seen:
                seen.add("secret-files")
                found.append({"topic": "secret-files", "image": image, "service": name,
                              "evidence": f"{compose.name}: {name} overrides the entrypoint to load its secrets from files"})
            has_own = facts.get(image, {}).get("healthcheck") is False
            if service.get("healthcheck") and has_own and "healthcheck" not in seen:
                seen.add("healthcheck")
                found.append({"topic": "healthcheck", "image": image, "service": name,
                              "evidence": f"{compose.name}: {name} declares a healthcheck, and test.yml says {image} has none"})
    return found


def requested(root: Path, card: str, topic: str) -> str:
    """The upstream/ file that already covers this card and topic, or ''."""
    for path in sorted((root / "upstream").glob(f"*-{topic}.md")):
        m = re.match(r"\A---\n(.*?)\n---\n", path.read_text(), re.S)
        names = (yaml.safe_load(m.group(1)) or {}).get("cards") or [] if m else []
        if path.name == f"{card}-{topic}.md" or card in names:
            return path.name
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Find what cards work around that an app's author could fix.")
    ap.add_argument("--json", action="store_true", help="print the findings as JSON")
    args = ap.parse_args(argv)
    root = Path.cwd()
    cards = sorted(p.parent for p in root.glob("*/card.yml"))
    if not cards:
        print("no cards here: run it from the root of a cards repo", file=sys.stderr)
        return 2
    new, known = [], []
    for card in cards:
        for c in candidates(card):
            have = requested(root, card.name, c["topic"])
            (known if have else new).append({"card": card.name, **c, **({"request": have} if have else {})})
    if args.json:
        print(json.dumps({"new": new, "known": known}, indent=2))
        return 0
    for c in new:
        print(f"new    {c['card']:<18} {c['topic']:<13} {c['image']}\n         {c['evidence']}")
    for c in known:
        print(f"known  {c['card']:<18} {c['topic']:<13} upstream/{c['request']}")
    print(f"{len(new)} without a request, {len(known)} with one, in {len(cards)} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
