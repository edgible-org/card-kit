#!/usr/bin/env python3
"""Check that a card runs on this machine and, against a backup, that it holds the same data.

    python3 verify-card.py ~/linkding-copy --against ~/linkding-backups/20261018-1001
    python3 verify-card.py ~/linkding

  running      every service of each Compose file that runs here is running, and healthy; a
               one-shot service (restart: "no") has run and exited 0
               when it has a healthcheck
  answering    every TCP port it publishes on the machine accepts a connection
  fingerprint  data.fingerprint's command; with --against, its line must equal the one in
               the backup's backup.json, the proof that the data came back whole

It prints both lines when they differ. It exits 1 when a check fails.

Needs python3 and Docker with compose. Only the standard library.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shlex
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("backup_card", HERE / "backup-card.py")
backup_card = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_card)
test_card, sh = backup_card.test_card, backup_card.sh


def services_state(c) -> dict[str, str]:
    """Each service's state: running, healthy, done, or what Docker says instead. done is a
    one-shot service (restart: "no"), such as a card's <card>-secrets, that ran and exited 0."""
    out = sh(f"{c.cmd} ps --all --format json", check=False).stdout.strip()
    rows = json.loads(out) if out.startswith("[") else [json.loads(l) for l in out.splitlines() if l.strip()]
    config = json.loads(sh(f"{c.cmd} config --format json", check=False).stdout or "{}").get("services") or {}
    state = {}
    for r in rows:
        health = r.get("Health") or ""
        state[r["Service"]] = health if r.get("State") == "running" and health else r.get("State", "?")
        if (r.get("State") == "exited" and r.get("ExitCode") == 0
                and str((config.get(r["Service"]) or {}).get("restart", "no")) in ("no", "False", "false")):
            state[r["Service"]] = "done"
    return state


def published_ports(c) -> list[tuple[str, str, int]]:
    config = json.loads(sh(f"{c.cmd} config --format json").stdout)
    ports = []
    for service, spec_ in (config.get("services") or {}).items():
        for p in spec_.get("ports") or []:
            if p.get("published") and p.get("protocol", "tcp") == "tcp":
                host = p.get("host_ip") or "127.0.0.1"
                ports.append((service, "127.0.0.1" if host in ("0.0.0.0", "::") else host, int(p["published"])))
    return ports


def answers(host: str, port: int, wait: int = 60) -> bool:
    deadline = time.monotonic() + wait
    while True:
        with socket.socket() as s:
            s.settimeout(2)
            if s.connect_ex((host, port)) == 0:
                return True
        if time.monotonic() > deadline:
            return False
        time.sleep(3)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("card", type=Path, help="the card's directory, as it runs on this machine")
    ap.add_argument("--against", type=Path, help="a directory backup-card wrote: the fingerprint must match its own")
    args = ap.parse_args(argv)

    card = args.card.expanduser().resolve()
    if not (card / "card.yml").is_file():
        print(f"{card} has no card.yml", file=sys.stderr)
        return 2
    manifest = json.loads((args.against.expanduser().resolve() / "backup.json").read_text()) if args.against else None
    composes = [backup_card.Compose(card, f) for f in sorted(card.glob("*compose*.yml"))]
    failed = False

    here = [c for c in composes if services_state(c)]
    if not here:
        print("running: fail (none of the card's services exist on this machine)")
        return 1
    for c in here:
        state = services_state(c)
        for service in sorted(c.services):
            s = state.get(service, "missing")
            ok = s in ("running", "healthy", "done")
            failed |= not ok
            print(f"running {service}: {'pass' if ok else 'fail'} ({s})")
        for service, host, port in published_ports(c):
            ok = answers(host, port)
            failed |= not ok
            print(f"answering {service} on {host}:{port}: {'pass' if ok else 'fail'}")

    fingerprint_spec = test_card.read_fingerprint(card / "card.yml")
    if fingerprint_spec:
        service, command = fingerprint_spec
        c = next((c for c in here if service in c.services), None)
        value, problem = None, f"no Compose file running here has {service}"
        for _ in range(5):
            if c is None:
                break
            r = sh(f"{c.cmd} exec -T {service} sh -c {shlex.quote(command)}", check=False, timeout=120)
            value, problem = test_card.fingerprint_problem(r.stdout) if r.returncode == 0 else (None, f"exit {r.returncode}")
            if value is not None:
                break
            time.sleep(5)
        if value is None:
            failed = True
            print(f"fingerprint: fail ({problem})")
        elif manifest is None:
            print(f"fingerprint: {json.dumps(value)}")
        elif manifest.get("fingerprint") is None:
            print(f"fingerprint: {json.dumps(value)} (the backup has none to compare)")
        elif value == manifest["fingerprint"]:
            print(f"fingerprint: pass, same as the backup {json.dumps(value)}")
        else:
            failed = True
            print(f"fingerprint: fail, the data differs from the backup\n"
                  f"  backup: {json.dumps(manifest['fingerprint'])}\n  now:    {json.dumps(value)}")
    else:
        print("fingerprint: none declared, so the data cannot be compared")

    print("verify: " + ("fail" if failed else "pass"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
