#!/usr/bin/env python3
"""Is this app ready to become an Edgible card? A readiness report for the person who wrote it.

Run it from the app's folder, or point it at one, on the machine where you build the app:

    python3 check-app.py                                   # the current folder
    python3 check-app.py ~/code/my-app --image ghcr.io/me/my-app:1.2.0 --steward my-github-name
    python3 check-app.py ~/code/my-app --image ghcr.io/me/my-app:1.2.0 --json

It reads the app's files and asks the registry about the image (it needs Docker for that, and the
network). It changes nothing, and it prints only the names of what it finds, never a value.

Three lists. REQUIRED is what a card needs: a public image with a version tag that runs on both amd64 and
arm64, a licence others can use, settings that are written down, a port and a place for the data, and
nobody's secrets committed. YOUR CALL is who answers for the card (the steward, a GitHub name): a card can
be listed with none, so it never fails the check, but the person should choose. NICE TO HAVE is what makes
it a better card: a healthcheck, a non-root user, secrets that can come from files, a backup note, an icon.
Each gap says what to do. Exit 0 when every required item passes, 1 when one does not, 2 when it cannot run.

--json prints the same as data, for an agent: it can loop until `ready` is true.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

LICENSES = {
    "MIT": r"\bMIT License\b|Permission is hereby granted, free of charge",
    "Apache-2.0": r"Apache License,?\s+Version 2\.0",
    "AGPL-3.0": r"GNU AFFERO GENERAL PUBLIC LICENSE",
    "GPL-3.0": r"GNU GENERAL PUBLIC LICENSE\s+Version 3",
    "GPL-2.0": r"GNU GENERAL PUBLIC LICENSE\s+Version 2",
    "LGPL": r"GNU LESSER GENERAL PUBLIC LICENSE",
    "MPL-2.0": r"Mozilla Public License,?\s+[Vv]ersion 2\.0",
    "BSD": r"Redistribution and use in source and binary forms",
    "ISC": r"\bISC License\b|Permission to use, copy, modify, and/or distribute",
    "Unlicense": r"This is free and unencumbered software",
}
DEFAULTS = {"admin", "password", "changeme", "change-me", "123456", "root", "secret", "test", "postgres",
            "default", "example", "letmein", "pass", "admin123", "demo"}
# Values in these folders are for local development and examples, so they are reported as defaults, not as secrets.
DEV_DIRS = {"scripts", "test", "tests", "testdata", "fixtures", "docs", "doc", "examples", "example", "dev", ".github",
            "e2e", "demo", ".devcontainer", "contrib"}
SECRETISH = re.compile(r"(PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE_?KEY|SALT)", re.I)
TEXT_SUFFIXES = {".env", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".conf", ".sh", ""}
SKIP = {".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv", "venv"}


def read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def find(root: Path, *names: str) -> list[Path]:
    return [p for n in names for p in sorted(root.glob(n)) if p.is_file()]


def project_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and not (SKIP & set(p.relative_to(root).parts)) and p.stat().st_size < 300_000:
            yield p


def image_platforms(image: str) -> tuple[list[str] | None, str]:
    """The platforms a public image runs on, or None and why it could not be read."""
    try:
        out = subprocess.run(["docker", "manifest", "inspect", image], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return None, "Docker is not installed here, so the image could not be checked"
    except subprocess.TimeoutExpired:
        return None, "the registry did not answer in time"
    if out.returncode != 0:
        why = out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "no answer"
        return None, f"the registry says: {why[:120]}"
    try:
        data = json.loads(out.stdout)
    except ValueError:
        return None, "the registry's answer could not be read"
    manifests = data.get("manifests")
    if manifests:
        return sorted({f"{m['platform']['os']}/{m['platform']['architecture']}" for m in manifests
                       if m.get("platform") and m["platform"].get("architecture") != "unknown"}), ""
    return [], "the image is a single-platform manifest; its architecture is not listed here"


def item(id_: str, title: str, ok: bool | None, detail: str, fix: str = "") -> dict:
    return {"id": id_, "title": title, "ok": ok, "detail": detail, "fix": "" if ok else fix}


def check(root: Path, image: str, steward: str) -> dict:
    files = list(project_files(root))
    names = {p.relative_to(root).as_posix() for p in files}
    # The app's own Dockerfile and Compose file, wherever the project keeps them (not those of examples or tests).
    real = [p for p in files if not (DEV_DIRS & set(p.relative_to(root).parts[:-1]))]
    dockerfiles = [p for p in real if p.name == "Dockerfile" or p.name.startswith("Dockerfile.") or p.name.endswith(".Dockerfile")]
    composes = [p for p in real if re.match(r"(docker-)?compose.*\.ya?ml$", p.name)]
    dtext = "\n".join(read(p) for p in dockerfiles)
    ctext = "\n".join(read(p) for p in composes)
    readme = next((read(p) for p in find(root, "README.md", "README", "readme.md")), "")
    required: list[dict] = []
    decide: list[dict] = []
    nice: list[dict] = []

    # image
    if not image:
        required.append(item("image", "A public image with a version tag", False,
                             "no --image given", "Publish the app as a container image on a public registry such as GitHub "
                             "Container Registry or Docker Hub, tag it with a version, and run this again with --image <name:tag>."))
        required.append(item("arch", "The image runs on amd64 and arm64", None, "not checked without --image"))
    else:
        tag = image.rsplit("/", 1)[-1].partition(":")[2].split("@")[0]
        if "@sha256:" in image and not tag:
            tag = "digest"
        ok_tag = bool(tag) and tag != "latest"
        platforms, why = image_platforms(image)
        required.append(item("image", "A public image with a version tag",
                             ok_tag and platforms is not None,
                             (f"tag {tag}" if ok_tag else "the tag is missing or latest") + ("" if platforms is not None else f"; {why}"),
                             "Pin a version tag (1.2.0, not latest) and make sure the image can be pulled without signing in."))
        if platforms is None:
            required.append(item("arch", "The image runs on amd64 and arm64", None, why))
        else:
            have = {p.split("/")[-1] for p in platforms}
            ok = {"amd64", "arm64"} <= have
            required.append(item("arch", "The image runs on amd64 and arm64", ok,
                                 "platforms: " + (", ".join(platforms) or "none listed"),
                                 "Build for both, for example docker buildx build --platform linux/amd64,linux/arm64 --push. "
                                 "People run Edgible on Intel servers and on Apple Silicon."))

    # licence
    lic_text = " ".join(read(p)[:3000] for p in find(root, "LICENSE", "LICENSE.*", "LICENCE", "COPYING", "license", "LICENSE-*"))
    found = next((k for k, pat in LICENSES.items() if re.search(pat, lic_text)), "")
    required.append(item("licence", "A licence that lets others run it", bool(found),
                         found or ("a licence file is there but I did not recognise it" if lic_text.strip() else "no licence file"),
                         "Add a LICENSE file with a licence that lets others run and change the app (MIT, Apache-2.0, AGPL-3.0 and "
                         "similar). Without one, the law reserves every right to you, and nobody else may run it."))

    # settings written down
    sample = find(root, ".env.example", ".env.sample", ".env.template", "env.example", "example.env", "*/.env.example")
    env_in_readme = bool(re.search(r"\b[A-Z][A-Z0-9]{2,}_[A-Z0-9_]{2,}\b", readme))
    in_docs = any(re.search(r"\b[A-Z][A-Z0-9]{2,}_[A-Z0-9_]{2,}\b", read(p)) for p in files
                  if p.suffix in (".md", ".1", ".txt", ".rst") and ({"docs", "doc"} & set(p.relative_to(root).parts[:-1])
                                                                  or p.suffix == ".1"))
    documented = bool(sample) or env_in_readme or in_docs or bool(re.search(r"(?m)^\s*environment:", ctext))
    required.append(item("settings", "Its settings are written down", documented,
                         "an example env file, the README, the docs or a Compose file lists them" if documented else "no list of settings found",
                         "List every setting (environment variable) the app reads, with what it does and its default, in the README "
                         "or an .env.example."))

    # port and data
    port = bool(re.search(r"(?mi)^\s*EXPOSE\s+\d+", dtext)) or bool(re.search(r"(?m)^\s*-\s*[\"']?[\d.:${}A-Za-z_-]*:\d+[\"']?\s*$", ctext))
    data = bool(re.search(r"(?mi)^\s*VOLUME\b", dtext)) or bool(re.search(r"(?m)^\s*volumes:\s*$", ctext)) \
        or bool(re.search(r"(?i)\b(data|database|storage) (is|are)? ?(kept|stored|saved|lives?)\b|/data\b", readme))
    required.append(item("port-data", "It names its port and where its data lives", port and data,
                         f"port: {'yes' if port else 'no'}; data location: {'yes' if data else 'no'}",
                         "Say which port the app listens on (EXPOSE in the Dockerfile) and which folder holds its data "
                         "(a VOLUME, and a line in the README). A card keeps that folder in a named volume and backs it up."))

    # secrets committed (names only)
    committed, defaults = [], []
    for p in files:
        rel = p.relative_to(root).as_posix()
        if p.suffix not in TEXT_SUFFIXES and p.name != ".env":
            continue
        for line in read(p).splitlines():
            k, sep, v = line.partition("=")
            if sep and SECRETISH.search(k) and re.fullmatch(r"[A-Za-z0-9_]+", k.strip().split()[-1] if k.strip() else "x") \
                    and v.strip().strip("\"'") and not v.strip().startswith(("${", "$", "<", "your", "change", "CHANGE", "example")) \
                    and p.name not in (".env.example", ".env.sample", ".env.template", "example.env") and ".example" not in p.name:
                dev = bool(DEV_DIRS & set(p.relative_to(root).parts[:-1])) or p.name in ("Makefile", "makefile")
                (defaults if dev or v.strip().strip("\"'").lower() in DEFAULTS else committed).append(f"{k.strip().split()[-1]} ({rel})")
        if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", read(p)):
            (defaults if DEV_DIRS & set(p.relative_to(root).parts[:-1]) else committed).append(f"a private key ({rel})")
    required.append(item("secrets", "No secrets are committed", not committed,
                         "none found" if not committed else "names: " + ", ".join(sorted(set(committed))[:8]),
                         "Remove them from git (and change them: they are public now). A card makes secrets on the machine "
                         "at first start; the app should read them from the environment or, better, from files."))

    # steward: a choice, not a requirement, since a card can be listed with none
    decide.append(item("steward", "Who answers for it (the steward)", None if not steward else True,
                       f"steward: {steward}" if steward else "none named: the card will be listed as having no steward",
                       "Optional. Give the GitHub user or organisation that will review changes to the card and fix it "
                       "when its test fails: --steward <github-name>. If nobody will, leave it: that is allowed."))

    # nice to have
    health = bool(re.search(r"(?mi)^\s*HEALTHCHECK\b", dtext)) or bool(re.search(r"(?m)^\s*healthcheck:", ctext))
    nice.append(item("default-passwords", "No well-known default password in the files", not defaults,
                     "none found" if not defaults else "names: " + ", ".join(sorted(set(defaults))[:6]),
                     "A card makes its own passwords on the machine. A default such as admin in a script or example is "
                     "fine for local development, but say so, and never let the container start with it."))
    nice.append(item("healthcheck", "A healthcheck", health, "found" if health else "none",
                     "Add a HEALTHCHECK to the Dockerfile on an endpoint the app already answers, so tools can wait for healthy."))
    user = re.findall(r"(?mi)^\s*USER\s+(\S+)", dtext)
    nonroot = bool(user) and user[-1].lower() not in ("root", "0")
    nice.append(item("nonroot", "It does not run as root", nonroot, f"USER {user[-1]}" if user else "no USER line",
                     "Add a USER line with an unprivileged user, so a flaw in the app does not give root in the container."))
    files_env = any(re.search(r"_FILE\b", read(p)) for p in files if p.suffix in (".py", ".js", ".ts", ".go", ".rb", ".php", ".sh", ".java", ".rs", ".md"))
    nice.append(item("secret-files", "It can read secrets from files (*_FILE)", files_env,
                     "a *_FILE setting is mentioned" if files_env else "none found",
                     "Accept SECRET_FILE (a path) as well as SECRET, so a secret need not sit in the environment, where "
                     "docker inspect shows it."))
    backup = bool(re.search(r"(?i)back\s?up", readme))
    nice.append(item("backup", "The README says how to back it up", backup, "found" if backup else "no mention",
                     "Add a short Backup section: what to copy (the data folder, the database) and how to restore it."))
    tags = (subprocess.run(["git", "-C", str(root), "tag", "--list"], capture_output=True, text=True).stdout.split()
            if (root / ".git").exists() else [])
    icons = [n for n in sorted(names) if re.search(r"(^|/)(icon|logo|favicon)[^/]*\.(svg|png)$", n, re.I)]
    nice.append(item("icon", "It has an icon", bool(icons), icons[0] if icons else "none found",
                     "Add a square icon, SVG if you can (or PNG), the app's own logo. An AI tool can draw a simple one in a minute. "
                     "A card keeps it as images/icon.svg; without one the catalog shows the Edgible symbol."))
    nice.append(item("releases", "It makes versioned releases", len(tags) > 0, f"{len(tags)} git tag(s)" if tags else "no git tags",
                     "Tag releases (v1.2.0), so a card can pin a version and a bump bot can propose the next one."))

    return {"app": str(root), "image": image, "required": required, "decide": decide, "nice": nice,
            "ready": all(i["ok"] is True for i in required)}


def show(report: dict) -> None:
    def mark(i: dict) -> str:
        return {True: "ok  ", False: "FIX ", None: "?   "}[i["ok"]]
    print(f"Readiness of {report['app']}" + (f" ({report['image']})" if report["image"] else ""))
    print("\nREQUIRED")
    for i in report["required"]:
        print(f"  {mark(i)}{i['title']}: {i['detail']}")
        if i["fix"]:
            print(f"        -> {i['fix']}")
    print("\nYOUR CALL")
    for i in report["decide"]:
        print(f"  {mark(i)}{i['title']}: {i['detail']}")
        if i["fix"] and i["ok"] is not True:
            print(f"        -> {i['fix']}")
    print("\nNICE TO HAVE")
    for i in report["nice"]:
        print(f"  {mark(i)}{i['title']}: {i['detail']}")
        if i["fix"]:
            print(f"        -> {i['fix']}")
    todo = sum(1 for i in report["required"] if i["ok"] is False)
    unknown = sum(1 for i in report["required"] if i["ok"] is None)
    print("\n" + ("Ready: every required item passes." if report["ready"]
                  else f"Not ready: {todo} required item(s) to fix" + (f", {unknown} not checked" if unknown else "") + "."))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Is this app ready to become an Edgible card?")
    ap.add_argument("folder", nargs="?", default=".", help="the app's folder (default: here)")
    ap.add_argument("--image", default="", help="the app's public image, name:tag")
    ap.add_argument("--steward", default="", help="the GitHub user or organisation that answers for the card")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.folder).resolve()
    if not root.is_dir():
        print(f"{root}: not a folder", file=sys.stderr)
        return 2
    report = check(root, args.image, args.steward)
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        show(report)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
