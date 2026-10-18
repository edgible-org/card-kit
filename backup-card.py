#!/usr/bin/env python3
"""Back up a running card's data on this machine, the way its card.yml data: section says.

Run it on the machine that runs the card, with the card's directory:

    python3 backup-card.py ~/linkding --dry-run
    python3 backup-card.py ~/linkding
    python3 backup-card.py ~/gitea --to /mnt/backups/gitea

In order:

  dumps        each irreplaceable volume with a dump: runs its command in its service while
               the app stays up, and keeps what it writes to stdout as <volume>.dump
  fingerprint  data.fingerprint's command, after the dumps and before any stop, so it
               describes the data the copies hold
  copies       each irreplaceable volume without a dump: stops the services that mount it,
               copies it to <volume>.tgz, and starts them again. This is the short outage.
  skipped      rebuildable and cache volumes: listed in the manifest, not copied
  card         the card's own files with its card.env (mode 600), which the copies need:
               the databases in them expect its passwords

It writes everything to <card dir>-backups/<YYYYmmdd-HHMM>/ (or --to), with backup.json, a
manifest of what each file holds and its sha256, and the fingerprint. restore-card and
verify-card read it. The directory is named .partial until the backup is whole.

--dry-run says what it would copy, how, whether the app would stop, and whether the disk has
room, and changes nothing.

Needs python3 and Docker with compose. Only the standard library, because it runs on the
machine that serves the card.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("test_card", HERE / "test-card.py")
test_card = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_card)
sh = test_card.sh


# --- The card ---------------------------------------------------------------

def scalar(value: str) -> str:
    if value[:1] == "'" and value[-1:] == "'":
        return value[1:-1].replace("''", "'")
    if value[:1] == '"' and value[-1:] == '"':
        return json.loads(value)
    return value


def read_volumes(card_yml: Path) -> dict[str, dict]:
    """data.volumes from card.yml: {volume: {class, dump: {service, command, restore}}}. Dump
    fields are plain or quoted scalars on one line, or a | or > block below them."""
    m = re.search(r"\ndata:\s*\n((?:[ \t]+.*\n?|\s*\n)+)", card_yml.read_text())
    lines = (m.group(1) if m else "").splitlines()
    volumes, current, in_volumes, i = {}, None, False, 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^  \S", line):
            in_volumes = bool(re.match(r"^  volumes:\s*$", line))
        elif in_volumes and (vm := re.match(r"^    ([A-Za-z0-9][A-Za-z0-9_.-]*):\s*$", line)):
            current = volumes.setdefault(vm.group(1), {})
        elif in_volumes and current is not None and (cm := re.match(r"^      class:\s*(\S+)\s*$", line)):
            current["class"] = scalar(cm.group(1))
        elif in_volumes and current is not None and re.match(r"^      dump:\s*$", line):
            current["dump"] = {}
        elif in_volumes and current is not None and "dump" in current \
                and (fm := re.match(r"^        (service|command|restore):\s*(.*?)\s*$", line)):
            if fm.group(2)[:1] in ("|", ">"):
                block = []
                while i + 1 < len(lines) and (lines[i + 1].startswith("          ") or not lines[i + 1].strip()):
                    i += 1
                    block.append(lines[i][10:])
                current["dump"][fm.group(1)] = ("\n" if fm.group(2)[0] == "|" else " ").join(block).strip()
            else:
                current["dump"][fm.group(1)] = scalar(fm.group(2))
        i += 1
    return volumes


def card_name(card: Path) -> str:
    m = re.search(r"\nmetadata:\s*\n\s+name:\s*(\S+)", "\n" + (card / "card.yml").read_text())
    return m.group(1) if m else card.name


class Compose:
    """One of the card's Compose files, as the card's README runs it."""

    def __init__(self, card: Path, path: Path):
        self.path = path
        self.cmd = f"docker compose --env-file {shlex.quote(str(card / 'card.env'))} -f {shlex.quote(str(path))}"
        config = json.loads(sh(f"{self.cmd} config --format json").stdout)
        self.project = config["name"]
        self.services = set(config.get("services") or {})
        self.mounts = {s: {m.get("source") for m in (spec or {}).get("volumes") or [] if m.get("type") == "volume"}
                       for s, spec in (config.get("services") or {}).items()}
        self.volumes = {k: (v or {}).get("name") or f"{self.project}_{k}" for k, v in (config.get("volumes") or {}).items()}

    def present(self) -> bool:
        """Whether this machine has the file's containers, running or not."""
        return bool(sh(f"{self.cmd} ps --all -q", check=False).stdout.strip())

    def running(self) -> list[str]:
        out = sh(f"{self.cmd} ps --status running --services", check=False).stdout
        return [s for s in out.split() if s]


def volume_exists(name: str) -> bool:
    return sh(f"docker volume inspect {shlex.quote(name)}", check=False).returncode == 0


def volume_bytes(name: str) -> int:
    r = sh(f"docker run --rm -v {shlex.quote(name)}:/data:ro alpine du -sk /data", check=False, timeout=600)
    return int(r.stdout.split()[0]) * 1024 if r.returncode == 0 and r.stdout.split() else 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


# --- The backup -------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("card", type=Path, help="the card's directory, as it runs on this machine")
    ap.add_argument("--to", type=Path, help="where the backup goes (default: <card>-backups/<stamp>)")
    ap.add_argument("--dry-run", action="store_true", help="say what it would do, and change nothing")
    args = ap.parse_args(argv)

    card = args.card.expanduser().resolve()
    if not (card / "card.yml").is_file() or not (card / "card.env").is_file():
        print(f"{card} has no card.yml and card.env: give the directory the card runs from", file=sys.stderr)
        return 2
    declared = read_volumes(card / "card.yml")
    composes = [Compose(card, f) for f in sorted(card.glob("*compose*.yml"))]
    if not declared and any(c.volumes for c in composes):
        print(f"{card / 'card.yml'} has no data: section, so backup-card cannot tell what its volumes hold. "
              "Declare them first (see card-kit's README, Data).", file=sys.stderr)
        return 2
    owner = {v: next((c for c in composes if v in c.volumes), None) for v in declared}
    missing = [v for v, c in owner.items() if c is None]
    if missing:
        print(f"data: names {', '.join(missing)}, which no Compose file of the card has", file=sys.stderr)
        return 2
    here = {v: owner[v].volumes[v] for v in declared if volume_exists(owner[v].volumes[v])}
    elsewhere = [v for v in declared if v not in here and not owner[v].present()]
    lost = [v for v in declared if v not in here and v not in elsewhere]
    if lost:
        print(f"{', '.join(lost)}: the card's containers are on this machine but these volumes are not. "
              "Nothing to back up from them; check the card before anything else.", file=sys.stderr)
        return 1
    if declared and not here:
        print(f"none of the card's volumes are on this machine. Start the card first, "
              "or run backup-card on the machine that runs it.", file=sys.stderr)
        return 1

    plan = {}
    for v, spec_ in declared.items():
        if v not in here:
            plan[v] = "elsewhere"
        elif spec_.get("class") != "irreplaceable":
            plan[v] = "skip"
        elif spec_.get("dump"):
            plan[v] = "dump"
        else:
            plan[v] = "tar"
    fingerprint_spec = test_card.read_fingerprint(card / "card.yml")
    running = {c.path: c.running() for c in composes}
    # Only the running services that mount a volume it copies stop; the rest keep serving.
    copied = {v for v, how in plan.items() if how == "tar"}
    to_stop = [(c, stop) for c in composes
               if (stop := [s for s in running[c.path] if c.mounts.get(s, set()) & copied])]

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    dest = (args.to.expanduser().resolve() if args.to else card.parent / f"{card.name}-backups" / stamp)
    if dest.exists():
        print(f"{dest} exists already: give another --to", file=sys.stderr)
        return 2

    sizes = {v: volume_bytes(here[v]) for v, how in plan.items() if how in ("tar", "dump")}
    print(f"backup of {card_name(card)} from {card}")
    print(f"  to {dest}")
    for v, how in plan.items():
        size = f" ({test_card.human(sizes[v])})" if v in sizes else ""
        if how == "dump":
            print(f"  {v}: dump in {declared[v]['dump'].get('service')} while the app runs{size}")
        elif how == "tar":
            print(f"  {v}: copy to {v}.tgz while the app is stopped{size}")
        elif how == "skip":
            print(f"  {v}: not copied ({declared[v].get('class')})")
        else:
            print(f"  {v}: not on this machine (another place runs it); back it up there")
    if not declared:
        print("  no volumes: the backup is the card and its card.env")
    if fingerprint_spec:
        print(f"  fingerprint: in {fingerprint_spec[0]}, before any stop")
    elif declared:
        print("  fingerprint: none declared; verify-card will have nothing to compare")
    if to_stop:
        stopped = ", ".join(s for _, stop in to_stop for s in stop)
        print(f"  outage: stops {stopped} while it copies {test_card.human(sum(sizes[v] for v in plan if plan[v] == 'tar'))}")
    else:
        print("  outage: none")
    free_at = next(p for p in [dest, *dest.parents] if p.exists())
    free, need = shutil.disk_usage(free_at).free, sum(sizes.values())
    print(f"  disk: {test_card.human(free)} free at {free_at}, about {test_card.human(need)} needed (less once compressed)")
    if free < need:
        print("not enough room: free some space or give another --to", file=sys.stderr)
        return 1
    if args.dry_run:
        print("dry run: nothing changed")
        return 0

    partial = dest.with_name(dest.name + ".partial")
    partial.mkdir(parents=True, mode=0o700)
    manifest = {
        "card": card_name(card),
        "taken": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "edgible": sh("edgible --version", check=False).stdout.strip() or None,
        "files": test_card.files_hash(card),
        "fingerprint": None,
        "volumes": {},
    }
    try:
        # The dumps, while the app runs.
        for v in [v for v, how in plan.items() if how == "dump"]:
            dump = declared[v]["dump"]
            c = next((c for c in composes if dump["service"] in c.services), None)
            if c is None or dump["service"] not in running[c.path]:
                raise RuntimeError(f"{v}: its dump runs in {dump['service']}, which is not running. Start the card first.")
            file = partial / f"{v}.dump"
            with file.open("wb") as out:
                r = subprocess.run(f"{c.cmd} exec -T {dump['service']} sh -c {shlex.quote(dump['command'])}",
                                   shell=True, stdout=out, stderr=subprocess.PIPE, timeout=3600)
            if r.returncode != 0 or file.stat().st_size == 0:
                raise RuntimeError(f"{v}: the dump failed (exit {r.returncode}): {r.stderr.decode(errors='replace')[-300:]}")
            print(f"dump {v}: {test_card.human(file.stat().st_size)}")

        # The fingerprint, before any stop, so it describes what the copies hold.
        if fingerprint_spec:
            service, command = fingerprint_spec
            c = next((c for c in composes if service in c.services), None)
            if c is None or service not in running[c.path]:
                print(f"fingerprint: skipped ({service} is not running); verify-card will have nothing to compare")
            else:
                r = sh(f"{c.cmd} exec -T {service} sh -c {shlex.quote(command)}", check=False, timeout=120)
                value, problem = test_card.fingerprint_problem(r.stdout) if r.returncode == 0 else (None, f"exit {r.returncode}")
                if value is None:
                    raise RuntimeError(f"fingerprint: {problem}")
                manifest["fingerprint"] = value
                print(f"fingerprint: {json.dumps(value)}")

        # The copies, with the app stopped.
        tars = [v for v, how in plan.items() if how == "tar"]
        if tars:
            stopped_at = time.monotonic()
            for c, stop in to_stop:
                sh(f"{c.cmd} stop {' '.join(stop)}", timeout=600)
            try:
                for v in tars:
                    sh(f"docker run --rm -v {shlex.quote(here[v])}:/data:ro -v {shlex.quote(str(partial))}:/backup "
                       f"alpine tar -czf /backup/{v}.tgz -C /data .", timeout=7200)
                    print(f"copy {v}: {test_card.human((partial / f'{v}.tgz').stat().st_size)}")
            finally:
                for c, stop in to_stop:
                    r = sh(f"{c.cmd} start --wait --wait-timeout 300 {' '.join(stop)}", check=False, timeout=600)
                    state = "healthy again" if r.returncode == 0 else "started, but not healthy: check it now"
                    print(f"{', '.join(stop)}: {state}")
                if to_stop:
                    manifest["outage_seconds"] = round(time.monotonic() - stopped_at)
                    print(f"outage: {manifest['outage_seconds']} s")

        for v, how in plan.items():
            entry = {"class": declared[v].get("class"), "method": how}
            if how in ("dump", "tar"):
                file = partial / f"{v}.{'dump' if how == 'dump' else 'tgz'}"
                entry.update(file=file.name, bytes=file.stat().st_size, sha256=sha256(file))
                if how == "dump":
                    entry["service"] = declared[v]["dump"]["service"]
            manifest["volumes"][v] = entry

        # The card, with its card.env.
        shutil.copytree(card, partial / "card", symlinks=True,
                        ignore=shutil.ignore_patterns(".git", "__pycache__"))
        os.chmod(partial / "card" / "card.env", 0o600)
        (partial / "backup.json").write_text(json.dumps(manifest, indent=2) + "\n")
        partial.rename(dest)
    except Exception as exc:
        print(f"backup failed: {exc}\nthe incomplete copy is in {partial}", file=sys.stderr)
        return 1

    print(f"backed up to {dest}")
    if elsewhere:
        print(f"not here: {', '.join(elsewhere)}. Run backup-card on the machine that runs them.")
    print("A copy on this machine does not survive the loss of this machine: copy the directory somewhere else too.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
