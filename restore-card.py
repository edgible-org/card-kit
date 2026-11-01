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
  new       without --as, into a directory that is empty or not there yet: the card under
            its own name, as on the machine a move goes to; a taken *_PORT still moves
  in place  without --as, over the card that is there: it asks first (--yes skips that),
            backs the card up with backup-card (--no-backup skips that, when its data is
            already lost), stops it, and removes the volumes it restores
  volumes   creates them, loads each .tgz, starts each dump's service alone and loads the
            dump, and leaves rebuildable and cache volumes empty for the app to rebuild
  --move    the target of a move (with --as, or into a new directory): each secret in card.yml's
            secrets: follows its on-move rule. carry keeps it; new drops it, so the card's
            <card>-secrets service makes a fresh one at start, and people sign in again; new-then-
            update makes a fresh one too, then runs its update command in its service, which reads
            the new value from /run/card-secrets, so the data takes it. A move then rotates every
            secret the data does not need. Without --move, every secret is restored as it was.
  --device  a move or a copy: writes DEVICE=NAME in the new card.env, so Publish uses the new machine
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
    if new == old:
        return value
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


# What happens to a secret on a move when card.yml does not say, by its use (card-kit README, Secrets).
ON_MOVE = {"signing": "new", "token": "new", "password": "new-then-update", "encryption": "carry"}


def read_secrets(card_yml: Path) -> dict[str, dict]:
    """secrets: from card.yml, {NAME: {kind, use, on-move, update: {service, command}}}, read
    without a YAML library: names two spaces in, their fields four, update's six."""
    m = re.search(r"\nsecrets:\s*\n((?:[ \t]+.*\n?|\s*\n)+)", card_yml.read_text())
    out, name, sub = {}, None, None
    for line in (m.group(1) if m else "").splitlines():
        if re.match(r"^  ([A-Z][A-Z0-9_]*):\s*$", line):
            name, sub = line.strip()[:-1], None
            out[name] = {}
        elif name and (f := re.match(r"^    ([a-z-]+):\s*(.*)$", line)):
            key, value = f.groups()
            if key == "update":
                sub = out[name].setdefault("update", {})
            else:
                sub = None
                out[name][key] = re.sub(r"\s+#.*$", "", value).strip().strip('"')
        elif name and sub is not None and (f := re.match(r"^      ([a-z]+):\s*(.*)$", line)):
            sub[f.group(1)] = f.group(2).strip()
    return out


def on_move(secret: dict) -> str:
    if secret.get("on-move"):
        return secret["on-move"]
    if secret.get("kind") == "internal":
        return ON_MOVE.get(secret.get("use", ""), "carry")
    return "carry"


def secrets_volume(composes: list) -> tuple[object, str, str] | None:
    """The card-secrets service: (its Compose file, its service, the volume holding the secrets)."""
    for c in composes:
        config = json.loads(sh(f"{c.cmd} config --format json").stdout)
        for name, spec in (config.get("services") or {}).items():
            if "CARD_SECRETS" in ((spec or {}).get("environment") or {}):
                for m in spec.get("volumes") or []:
                    if m.get("type") == "volume" and m.get("target") == "/run/card-secrets":
                        return c, name, c.volumes[m["source"]]
    return None


def env_value(env: Path, key: str) -> str:
    m = re.search(rf"(?m)^{re.escape(key)}=(.*)$", env.read_text())
    return m.group(1).strip() if m else ""


def set_env(env: Path, key: str, value: str) -> None:
    """Set KEY=value in a card.env, adding the line when it is not there."""
    text = env.read_text()
    if re.search(rf"(?m)^{re.escape(key)}=", text):
        text = re.sub(rf"(?m)^{re.escape(key)}=.*$", f"{key}={value}", text)
    else:
        text = text.rstrip("\n") + f"\n{key}={value}\n"
    env.write_text(text)


def give_to_invoking_user(target: Path) -> None:
    """Run under sudo, the new directory would belong to root and the person could not read card.env."""
    import os, pwd
    user = os.environ.get("SUDO_USER")
    if os.geteuid() != 0 or not user:
        return
    pw = pwd.getpwnam(user)
    for p in [target, *target.rglob("*")]:
        os.chown(p, pw.pw_uid, pw.pw_gid, follow_symlinks=False)
    print(f"gave {target} to {user}")


def make_copy(card: Path, name: str, original: str) -> list[str]:
    """Name the copy's projects and containers after NAME, and move each taken *_PORT."""
    changes = []
    for f in backup_card.compose_files(card):
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
    ap.add_argument("--move", action="store_true",
                    help="the target of a move: each secret follows its on-move rule in card.yml")
    ap.add_argument("--device", help="the device the card will be published from, written to DEVICE in card.env "
                    "(a move: the new machine's name; only with --as or a new directory)")
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

    fresh = not args.name and (not target.exists() or not any(target.iterdir()))
    if args.name:
        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", args.name):
            print("--as takes a lower-case name, such as linkding-copy", file=sys.stderr)
            return 2
        if target.exists() and any(target.iterdir()):
            print(f"{target} is not empty: a copy goes in a new directory", file=sys.stderr)
            return 2
        mode = f"as a copy named {args.name} in {target}; the running card is not touched"
    elif fresh:
        mode = f"as {manifest['card']} in the new directory {target}, as on a new machine"
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
    if not args.name and not fresh:
        print("  first: " + ("no backup of the card (--no-backup)" if args.no_backup else "backup-card of the card as it is"))
    print("  then: start, and verify-card against the backup" +
          (f" (fingerprint {json.dumps(manifest['fingerprint'])})" if manifest.get("fingerprint") else ""))
    if args.device:
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9-]*$", args.device):
            print("--device takes a device name: letters, digits and hyphens", file=sys.stderr)
            return 2
        if not args.name and not fresh:
            print("--device is for a copy (--as) or a new directory, not for restoring over the card", file=sys.stderr)
            return 2
        print(f"  DEVICE in card.env: {args.device}")
    secrets = read_secrets(backup / "card" / "card.yml") if args.move else {}
    if args.move and not args.name and not fresh:
        print("--move is for the target of a move: with --as, or into a new directory", file=sys.stderr)
        return 2
    for s, spec in secrets.items():
        rule = on_move(spec)
        print(f"  secret {s}: {'kept as it was' if rule == 'carry' else 'made new at start' if rule == 'new' else 'made new, then ' + spec.get('update', {}).get('service', '?') + ' takes it'} ({rule})")
    if args.dry_run:
        print("dry run: nothing changed")
        return 0

    if not args.name and not fresh and not args.yes:
        if not sys.stdin.isatty():
            print("restoring over the card replaces its data: run it again with --yes", file=sys.stderr)
            return 2
        if input("This replaces the card's data. Type yes to go on: ").strip() != "yes":
            print("nothing changed")
            return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.name or fresh:
        shutil.copytree(backup / "card", target, symlinks=True, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("._*", ".DS_Store"))
        if fresh:
            taken = [n for f in backup_card.compose_files(target)
                     for n in backup_card.Compose(target, f).volumes.values() if backup_card.volume_exists(n)]
            if taken:
                shutil.rmtree(target)
                print(f"this machine already has {', '.join(taken)}: a card of the same name runs here. "
                      "Restore over its directory, or as a copy with --as.", file=sys.stderr)
                return 2
        for line in make_copy(target, args.name or manifest["card"], manifest["card"]):
            print(f"copy: {line}")
    else:
        if not args.no_backup:
            if backup_card.main([str(target), "--to", str(target.parent / f"{target.name}-backups" / f"before-restore-{stamp}")]) != 0:
                print("the backup of the card failed, so nothing was restored. If its data is already lost, "
                      "run again with --no-backup.", file=sys.stderr)
                return 1
        for c in [backup_card.Compose(target, f) for f in backup_card.compose_files(target)]:
            sh(f"{c.cmd} down", timeout=600)
            for key, name in c.volumes.items():
                if key in manifest["volumes"] and manifest["volumes"][key]["method"] != "elsewhere":
                    sh(f"docker volume rm {shlex.quote(name)}", check=False)
        shutil.copy2(target / "card.env", target / f"card.env.before-restore-{stamp}")
        shutil.copytree(backup / "card", target, symlinks=True, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("._*", ".DS_Store"))
    (target / "card.env").chmod(0o600)
    if args.device:
        set_env(target / "card.env", "DEVICE", args.device)
    elif args.name or fresh:
        old = env_value(target / "card.env", "DEVICE")
        if old:
            print(f"note: card.env still says DEVICE={old}: publish from that device, or run again with --device NAME")
    if args.name or fresh:
        give_to_invoking_user(target)

    composes = [backup_card.Compose(target, f) for f in backup_card.compose_files(target)]
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
        rotate = {s: on_move(spec) for s, spec in secrets.items() if on_move(spec) != "carry"}
        if rotate:
            found = secrets_volume(here)
            if not found:
                raise RuntimeError("card.yml declares secrets, but no card-secrets service keeps them in /run/card-secrets")
            sc, maker, volume = found
            # Dropped, the card's secrets service makes each one fresh when the card starts.
            sh(f"docker run --rm -v {shlex.quote(volume)}:/s alpine rm -f "
               + " ".join(shlex.quote(f"/s/{s}") for s in rotate), timeout=300)
            sh(f"{sc.cmd} up {shlex.quote(maker)}", timeout=600)
            for s, rule in rotate.items():
                if rule != "new-then-update":
                    print(f"secret {s}: new")
                    continue
                update = secrets[s].get("update") or {}
                service, command = update.get("service"), update.get("command")
                if not service or not command:
                    raise RuntimeError(f"secret {s} is new-then-update, but card.yml gives it no update")
                c = next((c for c in here if service in c.services), None)
                if c is None or volume not in {c.volumes.get(k) for k in c.mounts.get(service, set())}:
                    raise RuntimeError(f"secret {s}: {service} must mount the secrets volume to take the new value")
                sh(f"{c.cmd} up -d --wait {shlex.quote(service)}", timeout=900)
                # The value goes from the file to the command inside the container, never on a command line here.
                r = sh(f"{c.cmd} exec -T {shlex.quote(service)} sh -c "
                       + shlex.quote(f'{s}="$(cat /run/card-secrets/{s})"; export {s}; {command}'),
                       check=False, timeout=600)
                if r.returncode != 0:
                    raise RuntimeError(f"secret {s}: the update in {service} failed (exit {r.returncode}): "
                                       f"{(r.stderr or r.stdout)[-300:]}")
                print(f"secret {s}: new, and {service} took it")
        for c in here:
            sh(f"{c.cmd} up -d --wait", timeout=1800)
        print("started")
    except Exception as exc:
        print(f"restore failed: {exc}", file=sys.stderr)
        if not args.name and not fresh and not args.no_backup:
            print(f"the card as it was is in {target.parent / f'{target.name}-backups' / f'before-restore-{stamp}'}",
                  file=sys.stderr)
        return 1

    return verify_card.main([str(target), "--against", str(backup)])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
