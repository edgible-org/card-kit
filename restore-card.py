#!/usr/bin/env python3
"""Restore a backup made by backup-card, over the card or as a copy beside it, and verify it.

Run it on the machine that will run the card:

    python3 restore-card.py ~/linkding-backups/20261018-1001 ~/linkding-copy --as linkding-copy
    python3 restore-card.py ~/linkding-backups/20261018-1001 ~/linkding --dry-run
    python3 restore-card.py ~/linkding-backups/20261018-1001 ~/linkding

In order:

  check     every file against its sha256 in backup.json; one that differs stops it
  card      the card's files and card.env from the backup into the target directory
  --as      a copy beside the original: its own Compose project (and container names) named
            after NAME, and a free host port for each *_PORT that is taken, so the running card
            is never touched. This is the "restore under a temporary name" step of a move.
  in place  without --as, over the card that is there: it asks first (--yes skips that),
            backs the card up with backup-card (--no-backup skips that, when its data is
            already lost), stops it, and removes the volumes it restores
  volumes   creates them, loads each .tgz, starts each dump's service alone and loads the
            dump, and leaves rebuildable and cache volumes empty for the app to rebuild
  start     up --wait
  verify    verify-card against the backup: running, answering, and the same fingerprint

--dry-run checks the files and says what it would do, and changes nothing.

Needs python3 and Docker with compose. Only the standard library, because it runs on the
machine that serves the card.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shlex
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup_card = load("backup_card", "backup-card.py")
verify_card = load("verify_card", "verify-card.py")
sh = backup_card.sh


def renamed(value: str, old: str, new: str) -> str:
    """A project or container name for the copy: the card's own prefix swapped for NAME."""
    return new + value[len(old):] if value == old or value.startswith(old + "-") or value.startswith(old + "_") \
        else f"{new}-{value}"


def port_taken(port: int, also: set[int]) -> bool:
    if port in also:
        return True
    with socket.socket() as s:
        s.settimeout(0.3)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return True
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))
    except OSError:
        return True
    return False


def make_copy(card: Path, name: str, original: str) -> list[str]:
    """Name the copy's projects and containers after NAME, and move each taken *_PORT."""
    changes = []
    for f in sorted(card.glob("*compose*.yml")):
        text = f.read_text()
        def project(m):
            changes.append(f"{f.name}: project {m.group(2)} -> {renamed(m.group(2), original, name)}")
            return m.group(1) + renamed(m.group(2), original, name)
        text = re.sub(r"(?m)^(name:\s*)([A-Za-z0-9_.-]+)\s*$", project, text)
        def container(m):
            changes.append(f"{f.name}: container {m.group(2)} -> {renamed(m.group(2), original, name)}")
            return m.group(1) + renamed(m.group(2), original, name)
        text = re.sub(r"(?m)^(\s+container_name:\s*)([A-Za-z0-9_.-]+)\s*$", container, text)
        f.write_text(text)
    env = card / "card.env"
    lines, chosen = env.read_text().splitlines(), set()
    for i, line in enumerate(lines):
        m = re.match(r"^([A-Z0-9_]*PORT)=(\d+)\s*$", line)
        if not m:
            continue
        port = int(m.group(2))
        if port_taken(port, chosen):
            new = port + 1
            while port_taken(new, chosen):
                new += 1
            lines[i] = f"{m.group(1)}={new}"
            changes.append(f"card.env: {m.group(1)} {port} -> {new} (taken)")
            port = new
        chosen.add(port)
    env.write_text("\n".join(lines) + "\n")
    return changes


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backup", type=Path, help="a directory backup-card wrote, with backup.json")
    ap.add_argument("target", type=Path, help="the card's directory: the one it runs from, or a new one with --as")
    ap.add_argument("--as", dest="name", help="restore as a copy beside the original, named NAME")
    ap.add_argument("--yes", action="store_true", help="restore over the card without asking")
    ap.add_argument("--no-backup", action="store_true", help="in place: skip the backup of the card first")
    ap.add_argument("--dry-run", action="store_true", help="check the files, say what it would do, change nothing")
    args = ap.parse_args(argv)

    backup = args.backup.expanduser().resolve()
    target = args.target.expanduser().resolve()
    try:
        manifest = json.loads((backup / "backup.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"{backup} has no readable backup.json ({exc}): give a directory backup-card wrote", file=sys.stderr)
        return 2

    # Every file as it was written.
    bad = []
    for v, entry in manifest["volumes"].items():
        if entry.get("file"):
            file = backup / entry["file"]
            if not file.is_file() or backup_card.sha256(file) != entry["sha256"]:
                bad.append(entry["file"])
    if not (backup / "card" / "card.env").is_file():
        bad.append("card/card.env")
    if bad:
        print(f"the backup is damaged or incomplete: {', '.join(bad)}. Use another backup.", file=sys.stderr)
        return 1
    print(f"restore of {manifest['card']}, taken {manifest['taken']} on {manifest['host']}: files check out")

    if args.name:
        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", args.name):
            print("--as takes a lower-case name, such as linkding-copy", file=sys.stderr)
            return 2
        if target.exists() and any(target.iterdir()):
            print(f"{target} is not empty: a copy goes in a new directory", file=sys.stderr)
            return 2
        mode = f"as a copy named {args.name} in {target}; the running card is not touched"
    else:
        if not (target / "card.yml").is_file():
            print(f"{target} has no card.yml: give the card's directory, or a new one with --as", file=sys.stderr)
            return 2
        mode = f"over the card in {target}, replacing its data"
    print(f"  {mode}")
    for v, entry in manifest["volumes"].items():
        how = entry["method"]
        if how == "dump":
            print(f"  {v}: load {entry['file']} in {entry.get('service')}")
        elif how == "tar":
            print(f"  {v}: load {entry['file']}")
        elif how == "skip":
            print(f"  {v}: starts empty ({entry['class']}); the app rebuilds it")
        else:
            print(f"  {v}: not in this backup: restore it on the machine that runs it")
    if not args.name:
        print("  first: " + ("no backup of the card (--no-backup)" if args.no_backup else "backup-card of the card as it is"))
    print("  then: start, and verify-card against the backup" +
          (f" (fingerprint {json.dumps(manifest['fingerprint'])})" if manifest.get("fingerprint") else ""))
    if args.dry_run:
        print("dry run: nothing changed")
        return 0

    if not args.name and not args.yes:
        if not sys.stdin.isatty():
            print("restoring over the card replaces its data: run it again with --yes", file=sys.stderr)
            return 2
        if input("This replaces the card's data. Type yes to go on: ").strip() != "yes":
            print("nothing changed")
            return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.name:
        shutil.copytree(backup / "card", target, symlinks=True, dirs_exist_ok=True)
        for line in make_copy(target, args.name, manifest["card"]):
            print(f"copy: {line}")
    else:
        if not args.no_backup:
            if backup_card.main([str(target), "--to", str(target.parent / f"{target.name}-backups" / f"before-restore-{stamp}")]) != 0:
                print("the backup of the card failed, so nothing was restored. If its data is already lost, "
                      "run again with --no-backup.", file=sys.stderr)
                return 1
        for c in [backup_card.Compose(target, f) for f in sorted(target.glob("*compose*.yml"))]:
            sh(f"{c.cmd} down", timeout=600)
            for key, name in c.volumes.items():
                if key in manifest["volumes"] and manifest["volumes"][key]["method"] != "elsewhere":
                    sh(f"docker volume rm {shlex.quote(name)}", check=False)
        shutil.copy2(target / "card.env", target / f"card.env.before-restore-{stamp}")
        shutil.copytree(backup / "card", target, symlinks=True, dirs_exist_ok=True)
    (target / "card.env").chmod(0o600)

    composes = [backup_card.Compose(target, f) for f in sorted(target.glob("*compose*.yml"))]
    here = [c for c in composes
            if not c.volumes or any(manifest["volumes"].get(k, {}).get("method") != "elsewhere" for k in c.volumes)]
    try:
        for c in here:
            sh(f"{c.cmd} create", timeout=1800)
        for v, entry in manifest["volumes"].items():
            c = next((c for c in here if v in c.volumes), None)
            if c is None or entry["method"] != "tar":
                continue
            sh(f"docker run --rm -v {shlex.quote(c.volumes[v])}:/data -v {shlex.quote(str(backup))}:/backup:ro alpine "
               f"sh -c 'find /data -mindepth 1 -delete && tar -xzf /backup/{entry['file']} -C /data'", timeout=7200)
            print(f"loaded {v}")
        for v, entry in manifest["volumes"].items():
            if entry["method"] != "dump":
                continue
            dump = backup_card.read_volumes(target / "card.yml")[v]["dump"]
            c = next(c for c in here if dump["service"] in c.services)
            sh(f"{c.cmd} up -d --wait {dump['service']}", timeout=900)
            with (backup / entry["file"]).open("rb") as f:
                r = subprocess.run(f"{c.cmd} exec -T {dump['service']} sh -c {shlex.quote(dump['restore'])}",
                                   shell=True, stdin=f, capture_output=True, timeout=7200)
            if r.returncode != 0:
                raise RuntimeError(f"{v}: the restore command failed (exit {r.returncode}): "
                                   f"{r.stderr.decode(errors='replace')[-300:]}")
            print(f"loaded {v}")
        for c in here:
            sh(f"{c.cmd} up -d --wait", timeout=1800)
        print("started")
    except Exception as exc:
        print(f"restore failed: {exc}", file=sys.stderr)
        if not args.name and not args.no_backup:
            print(f"the card as it was is in {target.parent / f'{target.name}-backups' / f'before-restore-{stamp}'}",
                  file=sys.stderr)
        return 1

    return verify_card.main([str(target), "--against", str(backup)])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
