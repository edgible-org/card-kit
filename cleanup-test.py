#!/usr/bin/env python3
"""Remove what a stopped test-card run left behind.

test-card tears down what it made when it finishes. A run that is killed first (a CI job that
is cancelled or times out) leaves its Compose projects, their volumes, and the Edgible apps it
published, and the next test of that card stops at check-env's conflict check. Run this after
the test, whatever happened to it (a CI step with `if: always()`), from the folder test-card
ran in:

    python3 ../card-kit/cleanup-test.py chatwoot umami --since 2026-11-17T04:47:00Z

It removes, for each card:
  - the containers, volumes and networks of test-card's own Compose projects for it,
    cardtest-<card>-<file>, one per Compose file in the card's folder;
  - the Edgible apps of the card's apps, under their own names or test-<name>, created at or
    after --since, so an app the org had before the test started is never touched.

Nothing else on the machine is touched. A native card's test service left installed
(org.edgible.cardtest-<card>) is named, not uninstalled: its uninstall.sh is the card's own
code, for a person to run.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("test_card", HERE / "test-card.py")
test_card = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(test_card)


def run(args: list[str]) -> str:
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def when(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def docker_leftovers(card: Path) -> list[str]:
    done = []
    for f in sorted(card.glob("*compose*.yml")):
        project = f"cardtest-{card.name}-{f.stem}"
        label = f"label=com.docker.compose.project={project}"
        containers = run(["docker", "ps", "-aq", "--filter", label]).split()
        volumes = run(["docker", "volume", "ls", "-q", "--filter", label]).split()
        networks = run(["docker", "network", "ls", "-q", "--filter", label]).split()
        if containers:
            subprocess.run(["docker", "rm", "-f", *containers], capture_output=True)
        if volumes:
            subprocess.run(["docker", "volume", "rm", *volumes], capture_output=True)
        if networks:
            subprocess.run(["docker", "network", "rm", *networks], capture_output=True)
        if containers or volumes or networks:
            done.append(f"{project}: {len(containers)} containers, {len(volumes)} volumes, {len(networks)} networks")
    return done


def edgible_leftovers(card: Path, since: datetime, org_apps: list[dict]) -> list[str]:
    names = set()
    for app in test_card.read_apps(card / "card.yml"):
        names |= {app["name"], f"test-{app['name']}"}
    done = []
    for app in org_apps:
        created = app.get("createdAt")
        if app.get("name") in names and created and when(created) >= since:
            ok = subprocess.run(["edgible", "app", "delete", app["name"], "--yes"],
                                capture_output=True, timeout=600).returncode == 0
            done.append(f"Edgible app {app['name']}: {'deleted' if ok else 'could not be deleted'}")
    return done


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cards", nargs="+", help="card folders, as test-card was given them")
    p.add_argument("--since", required=True, help="when the test started (ISO 8601, UTC)")
    args = p.parse_args()
    since = when(args.since)
    try:
        org_apps = json.loads(run(["edgible", "app", "list", "--json"]) or "[]")
    except json.JSONDecodeError:
        org_apps = []
    for name in args.cards:
        card = Path(name)
        if not (card / "card.yml").exists():
            print(f"{name}: no card.yml here, nothing to clean")
            continue
        done = docker_leftovers(card) + edgible_leftovers(card, since, org_apps)
        plist = Path.home() / "Library" / "LaunchAgents" / f"org.edgible.cardtest-{card.name}.plist"
        if plist.exists():
            done.append(f"its native test service is still installed ({plist.name}): run the card's uninstall.sh by hand")
        print(f"{name}: " + ("; ".join(done) if done else "nothing left behind"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
