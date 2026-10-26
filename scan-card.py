#!/usr/bin/env python3
"""Scan the images a card pins for fixable vulnerabilities, on this machine, right now.

Run it from a fetched card, before Start or any time after:

    python3 scan-card.py website
    python3 scan-card.py website --json

The argument is the card directory. It reads each docker-compose.yml in it, resolves
${VAR:-default} from card.env (so an <APP>_IMAGE you set is the image scanned, and the report
says the card is customised), and scans every distinct image with Trivy, which it runs as a
container: Docker is the only requirement. Nothing is deployed, published or changed. A scan of
a few images takes about a minute the first time, while Trivy fetches its vulnerability
database, and less after.

It reports fixable HIGH and CRITICAL findings only: ones where a newer package version has the
fix. A finding means the card's pinned image is behind a fix. It is not proof that the app is
exposed, and the fix is a newer image of the same app, which the card's maintainers test
before they bump the pin (upgrading a running app is the skill's Upgrade steps).

The nightly scan of edgible-org/cards runs the same check on every card and feeds the README's
"images" badge; this is the same check for one card, on demand, with a pin of your own.

Only the standard library. Exit 0 when nothing fixable is found, 1 when something is, 2 when
the check cannot run.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TRIVY = "ghcr.io/aquasecurity/trivy:0.76.1"   # same version as edgible-org/cards' nightly scan
CACHE = "trivy-cache"
IMAGE = re.compile(r"^\s*image:\s*(\S+)", re.M)
VAR = re.compile(r"\$\{([A-Za-z0-9_]+):-([^}]*)\}")


def read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            m = re.match(r"^\s*([A-Za-z0-9_]+)=(.*)$", line)
            if m:
                env[m.group(1)] = m.group(2).strip().strip("\"'")
    return env


def card_images(card: Path) -> tuple[list[str], list[str]]:
    """The distinct images in the card's Compose files, and the variables that changed one."""
    env = read_env(card / "card.env")
    images: list[str] = []
    customised: list[str] = []

    def resolve(m: re.Match) -> str:
        name, default = m.group(1), m.group(2)
        if env.get(name):
            customised.append(name)
            return env[name]
        return default

    for compose in sorted(card.glob("*compose*.yml")):
        for ref in IMAGE.findall(compose.read_text()):
            ref = VAR.sub(resolve, ref).strip("\"'")
            if "${" not in ref and ref not in images:
                images.append(ref)
    return images, sorted(set(customised))


def scan(ref: str) -> dict:
    cmd = ["docker", "run", "--rm", "-v", f"{CACHE}:/root/.cache", TRIVY, "image", "--quiet",
           "--format", "json", "--severity", "HIGH,CRITICAL", "--ignore-unfixed",
           "--scanners", "vuln", ref]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        lines = done.stderr.strip().splitlines()
        return {"error": lines[-1] if lines else "the scan failed"}
    findings = []
    for result in json.loads(done.stdout or "{}").get("Results", []):
        for v in result.get("Vulnerabilities") or []:
            findings.append({"id": v["VulnerabilityID"], "severity": v["Severity"],
                             "package": v["PkgName"], "installed": v["InstalledVersion"],
                             "fixed": v.get("FixedVersion", "")})
    return {"findings": findings}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("card", type=Path, help="the card directory")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    args = ap.parse_args()

    if not args.card.is_dir():
        print(f"{args.card} is not a directory", file=sys.stderr)
        return 2
    if not shutil.which("docker"):
        print("docker is not installed: scan-card runs Trivy as a container", file=sys.stderr)
        return 2
    images, customised = card_images(args.card)
    if not images:
        print(f"no images found in {args.card}")
        return 0

    report = {}
    for ref in images:
        print(f"scanning {ref}", file=sys.stderr)
        report[ref] = scan(ref)

    found = sum(len(r.get("findings", [])) for r in report.values())
    broken = [ref for ref, r in report.items() if "error" in r]
    if args.json:
        print(json.dumps({"card": args.card.name, "customised": customised, "images": report}, indent=2))
    else:
        for ref, r in report.items():
            if "error" in r:
                print(f"- {ref}: not scanned ({r['error']})")
                continue
            worst = "CRITICAL" if any(f["severity"] == "CRITICAL" for f in r["findings"]) else "HIGH"
            print(f"- {ref}: " + (f"{len(r['findings'])} fixable (worst {worst})" if r["findings"] else "clean"))
            for f in sorted(r["findings"], key=lambda f: (f["severity"] != "CRITICAL", f["id"]))[:5]:
                print(f"    {f['id']} {f['severity']} {f['package']} {f['installed']} -> {f['fixed']}")
            if len(r["findings"]) > 5:
                print(f"    and {len(r['findings']) - 5} more")
        if customised:
            print(f"\nCustomised: {', '.join(customised)} set in card.env, so the scan used your image, not the card's pin.")
        print(f"\n{found} fixable finding{'s' * (found != 1)} in {len(images)} image{'s' * (len(images) != 1)}"
              + (f"; {len(broken)} not scanned" if broken else ""))
        if found:
            print("A finding means a newer image has the fix; it is not proof the app is exposed. "
                  "Until the card's pin moves, keep the hostname on org or paused if it holds sensitive data.")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
