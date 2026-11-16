#!/usr/bin/env python3
"""Change the address a running card's app gives out, the way its card.yml address: says.

Run it on the machine that runs the card, with the card's directory and the new address:

    python3 set-address.py ~/wordpress https://www.ourclub.org --dry-run
    python3 set-address.py ~/wordpress https://www.ourclub.org
    python3 set-address.py ~/wordpress https://www.ourclub.org --local http://127.0.0.1:8085

Many apps keep their own address: in a setting, and some also in their data (WordPress's
links inside posts). Moving an app at the edge alone leaves them sending people to the old
name. An app's address: in card.yml says how to change it:

    address:
      url: https://wordpress.${ORG_LABEL}.${EDGIBLE_DOMAIN:-edgible.app}   # as the Compose file builds it
      setting: WORDPRESS_URL      # the card.env line that overrides it
      change: $COMPOSE ... wp search-replace "$OLD_URL" "$NEW_URL" ...  # optional: fix the app's data

In order:

  old       the address now: --from, else the setting in card.env, else address.url filled in
            from card.env
  card.env  sets the setting to the new address, after a copy to card.env.bak-<time>
  restart   up -d --wait for each Compose file, so the app starts with the new address
  change    address.change, when the card has one, run in the card's directory with card.env
            exported, $COMPOSE set, and $OLD_URL and $NEW_URL
  check     asks the new address (or --local, with the new address's host name) for its first
            page: it must answer, must not redirect to the old name, and must not link to it

It does not change where the app is published: publish the new address with Edgible first
(your own domain, or another hostname), or after, and then run it again to check.

--dry-run says the old and new address and what it would run, and changes nothing. It exits 1
when a step or the check fails.

Needs python3 and Docker with compose. Only the standard library, because it runs on the
machine that serves the card.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


def compose_files(card: Path) -> list[Path]:
    return sorted(f for f in card.glob("*compose*.yml") if not f.name.startswith("._"))


def read_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if m:
            value = m.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            env[m.group(1)] = value
    return env


def addresses(card_yml: Path) -> dict[str, dict[str, str]]:
    """Each application's address: block, by app name. A small reader for the three scalar keys,
    so the tool needs no YAML library on the machine."""
    out: dict[str, dict[str, str]] = {}
    app = None
    block_indent = None
    for line in card_yml.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        m = re.match(r"\s*-\s+name:\s*(\S+)", line)
        if m:
            app, block_indent = m.group(1), None
            continue
        if app and re.match(r"\s*address:\s*$", line):
            block_indent = indent
            out[app] = {}
            continue
        if block_indent is not None:
            if indent <= block_indent:
                block_indent = None
                continue
            m = re.match(r"\s*(url|setting|change):\s*(.*?)\s*$", line)
            if m:
                value = m.group(2)
                if " #" in value and not value.startswith(("'", '"')):
                    value = value.split(" #", 1)[0].rstrip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                out[app][m.group(1)] = value
    return out


def expand(pattern: str, env: dict[str, str]) -> str:
    """${VAR}, ${VAR:-default} and ${VAR:?message}, as Compose fills them in."""
    def one(m: re.Match) -> str:
        name, op, arg = m.group(1), m.group(2), m.group(3) or ""
        value = env.get(name, "")
        if value:
            return value
        if op == ":-":
            return arg
        raise SystemExit(f"set-address: {name} is not set in card.env ({arg or 'needed for the address'})")
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-|:\?)([^}]*))?\}", one, pattern)


def normal(url: str) -> str:
    url = url.strip().rstrip("/")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.path or parts.query:
        raise SystemExit(f"set-address: {url!r} is not an address like https://www.example.org")
    return url


def set_line(path: Path, key: str, value: str) -> None:
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"\s*{re.escape(key)}=", line):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(new: str, old: str | None, local: str | None) -> list[str]:
    """What is wrong at the new address, or nothing."""
    target = (local.rstrip("/") if local else new) + "/"
    request = urllib.request.Request(target, headers={"User-Agent": "edgible-card-kit set-address"})
    if local:
        request.add_header("Host", urllib.parse.urlsplit(new).netloc)
        request.add_header("X-Forwarded-Proto", urllib.parse.urlsplit(new).scheme)
    opener = urllib.request.build_opener(NoRedirect)
    old_host = urllib.parse.urlsplit(old).netloc if old else None
    try:
        with opener.open(request, timeout=30) as r:
            body = r.read(2_000_000).decode("utf-8", "replace")
            status, location = r.status, ""
    except urllib.error.HTTPError as e:
        status, location = e.code, e.headers.get("Location", "")
        body = e.read(2_000_000).decode("utf-8", "replace") if e.fp else ""
    except (urllib.error.URLError, OSError) as e:
        return [f"{target} did not answer ({getattr(e, 'reason', e)}): publish the new address first, or use --local"]
    problems = []
    if old and 300 <= status < 400 and urllib.parse.urlsplit(urllib.parse.urljoin(new + "/", location)).netloc == old_host:
        problems.append(f"it redirects to the old address: {location}")
    elif status >= 400:
        problems.append(f"it answered {status}")
    links = body.count(old) if old else 0
    if links:
        problems.append(f"its first page still links to the old address {links} times")
    return problems


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("card", type=Path, help="the card's directory, with its card.env")
    p.add_argument("address", help="the new address, such as https://www.ourclub.org")
    p.add_argument("--app", help="which application, when the card has more than one with an address:")
    p.add_argument("--from", dest="old", help="the old address, when card.env no longer says it")
    p.add_argument("--local", help="check the app here, such as http://127.0.0.1:8085, with the new host name")
    p.add_argument("--dry-run", action="store_true", help="say what it would do, and change nothing")
    args = p.parse_args(argv)

    card = args.card.expanduser().resolve()
    env_path = card / "card.env"
    if not (card / "card.yml").is_file() or not env_path.is_file():
        raise SystemExit(f"set-address: {card} needs card.yml and card.env")
    found = addresses(card / "card.yml")
    if not found:
        raise SystemExit("set-address: no application in card.yml has an address:, so its address is only where it is "
                         "published: change that with Edgible, nothing in the app to update")
    if args.app:
        if args.app not in found:
            raise SystemExit(f"set-address: {args.app} has no address: (ones that do: {', '.join(found)})")
        name = args.app
    elif len(found) == 1:
        name = next(iter(found))
    else:
        raise SystemExit(f"set-address: say which with --app: {', '.join(found)}")
    spec = found[name]
    if not spec.get("setting") or not spec.get("url"):
        raise SystemExit(f"set-address: {name}'s address: needs url: and setting:")

    env = read_env(env_path)
    old = normal(args.old or env.get(spec["setting"]) or expand(spec["url"], env))
    new = normal(args.address)
    files = compose_files(card)
    compose = f"docker compose --env-file {shlex.quote(str(env_path))} -f {shlex.quote(str(files[0]))}" if files else ""
    print(f"{name}: {old} -> {new}")
    if old == new:
        problems = check(new, None, args.local)
        print("check:", "ok" if not problems else "; ".join(problems))
        return 1 if problems else 0
    if args.dry_run:
        print(f"card.env: {spec['setting']}={new} (a copy first, card.env.bak-<time>)")
        print(f"restart: up -d --wait, {', '.join(f.name for f in files)}")
        print(f"change: {spec['change']}" if spec.get("change") else "change: none, the setting is all the app keeps")
        print(f"check: {(args.local or new)}/ answers, with no redirect to and no link to {old}")
        return 0

    backup = card / f"card.env.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(env_path, backup)
    backup.chmod(0o600)
    set_line(env_path, spec["setting"], new)
    print(f"card.env: {spec['setting']} set (old copy {backup.name})")

    for f in files:
        cmd = f"docker compose --env-file {shlex.quote(str(env_path))} -f {shlex.quote(str(f))} up -d --wait --wait-timeout 600"
        r = subprocess.run(cmd, shell=True, cwd=card, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"restart: FAILED for {f.name}\n{(r.stderr or r.stdout)[-1500:]}")
            print(f"To go back: cp {backup} {env_path}, then up -d --wait again.")
            return 1
    print("restart: ok")

    if spec.get("change"):
        run_env = dict(os.environ, **read_env(env_path), COMPOSE=compose, OLD_URL=old, NEW_URL=new)
        r = subprocess.run(["sh", "-c", spec["change"]], cwd=card, env=run_env, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"change: FAILED (exit {r.returncode})\n{(r.stdout + r.stderr).strip()[-1500:]}")
            return 1
        said = [l for l in r.stdout.splitlines() if l.strip()]
        print("change: ok", said[-1].strip() if said else "")

    problems = check(new, old, args.local)
    print("check:", "ok" if not problems else "; ".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
