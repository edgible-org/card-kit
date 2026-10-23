#!/usr/bin/env python3
"""Self-hosting fit: how well an app card's app suits self-hosting, from facts, never opinion.

    python3 card-fit.py gitea bloglite      # each card's checks, with their evidence

Each check is a yes or no about the app itself, with the evidence that decides it. A check
that does not apply is left out; one whose fact is not known yet waits. The fit is the checks
passed out of the checks known, so a card's own unfinished work never counts against its app.

From the card's files, read fresh on every build:
  secrets-off-env    no password or key it makes is a card.env line: the card makes them on the
                     device (card.yml secrets:)
  secrets-from-files its app reads them from files, rather than only from the environment
                     through the card's loader
  health             it has a health check: the image's own, or one in the card's Compose file
From the app's image, as test-card measured it (test.yml image_facts:):
  non-root           its image starts as a user other than root
  arm-and-x86        its image has builds for arm64 and amd64

Facts only an image can tell wait until test-card records them (test-card --image-facts adds
them without a full test). card-site.py shows the fit on each card's tile and page.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

SECRET_NAME = re.compile(r"(PASSWORD|SECRET|TOKEN|KEY|SALT)")


def _image(ref: str) -> str:
    """An image reference without its digest, as card.yml from: and test.yml image_facts: name it."""
    return ref.split("@")[0]


def _generated(env_text: str) -> list[str]:
    """card.env lines check-env generates that hold a secret, rather than another value."""
    names = re.findall(r"#[^\n]*Generate with:[^\n]*\n(?:#[^\n]*\n)*([A-Z][A-Z0-9_]*)=", env_text)
    return [n for n in names if SECRET_NAME.search(n)]


def fit(card_dir: Path) -> dict | None:
    """The card's checks, passed and known. None for a pattern card, which has no single app."""
    card = yaml.safe_load((card_dir / "card.yml").read_text())
    if (card.get("metadata") or {}).get("type", "app") != "app":
        return None
    apps = card.get("applications") or []
    native = any((p or {}).get("native") for p in (card.get("places") or {}).values())
    froms = {_image(a.get("from", "")) for a in apps if a.get("from")}
    services = {}
    for f in sorted(card_dir.glob("*compose*.yml")):
        services.update((yaml.safe_load(f.read_text()) or {}).get("services") or {})
    # An image may be ${APP_IMAGE:-default}, which the person overrides in card.env: read the default.
    default = lambda ref: re.sub(r"^\$\{[A-Z0-9_]+:-([^}]*)\}$", r"\1", ref)
    app_services = {n: s or {} for n, s in services.items() if _image(default(str((s or {}).get("image", "")))) in froms}
    env_path = card_dir / "card.env"
    generated = _generated(env_path.read_text()) if env_path.is_file() else []
    made = [n for n, s in (card.get("secrets") or {}).items() if (s or {}).get("kind") in ("internal", "human", "shared")]
    test_path = card_dir / "test.yml"
    test = (yaml.safe_load(test_path.read_text()) or {}) if test_path.is_file() else {}
    facts = {_image(k): v or {} for k, v in (test.get("image_facts") or {}).items() if _image(k) in froms}

    checks = []

    def check(key: str, label: str, ok: bool | None, evidence: str) -> None:
        checks.append({"check": key, "label": label, "ok": ok, "evidence": evidence})

    if made or generated:
        check("secrets-off-env", "Secrets kept out of card.env", not generated,
              f"{', '.join(generated)} {'is a card.env line' if len(generated) == 1 else 'are card.env lines'}"
              if generated else f"made on the device: {', '.join(made)}")
        loader = [n for n, s in app_services.items() if ".load" in " ".join(map(str, s.get("entrypoint") or []))]
        if generated:
            check("secrets-from-files", "Reads secrets from files", False,
                  "takes them only from the environment, and its image has no shell for the card's loader"
                  if not loader else "takes them only from the environment")
        else:
            check("secrets-from-files", "Reads secrets from files", not loader,
                  "takes them from the environment, through the card's loader" if loader
                  else "reads them from files itself")
    if not native and app_services:
        in_compose = [n for n, s in app_services.items() if s.get("healthcheck")]
        in_image = [i for i, v in facts.items() if v.get("healthcheck")]
        known = in_compose or in_image or (facts and set(facts) >= froms)
        check("health", "Has a health check", bool(in_compose or in_image) if known else None,
              "the image's own" if in_image else "in the card's Compose file" if in_compose
              else "none, in the image or the card" if known else "waiting for test-card to read the image")
    if not native and froms:
        if facts and set(facts) >= froms:
            users = {i: str(v.get("user") or "root") for i, v in facts.items()}
            root = [i for i, u in users.items() if u in ("root", "0", "0:0")]
            check("non-root", "Starts as a non-root user", not root,
                  f"starts as root ({', '.join(sorted(root))})" if root
                  else f"starts as {', '.join(sorted(set(users.values())))}")
            archs = [{str(x) for x in v.get("archs") or []} for v in facts.values()]
            both = all({"amd64", "arm64"} <= a for a in archs)
            check("arm-and-x86", "Builds for arm64 and amd64", both,
                  ", ".join(sorted(set().union(*archs))) or "no builds listed")
        else:
            check("non-root", "Starts as a non-root user", None, "waiting for test-card to read the image")
            check("arm-and-x86", "Builds for arm64 and amd64", None, "waiting for test-card to read the image")
    known = [c for c in checks if c["ok"] is not None]
    return {"checks": checks, "passed": sum(1 for c in known if c["ok"]), "known": len(known),
            "waiting": len(checks) - len(known)}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.split("\n\n")[1].strip(), file=sys.stderr)
        return 2
    for arg in argv:
        f = fit(Path(arg))
        if f is None:
            print(f"{arg}: a pattern card, no fit")
            continue
        waiting = f", {f['waiting']} waiting" if f["waiting"] else ""
        print(f"{arg}: fit {f['passed']}/{f['known']}{waiting}")
        for c in f["checks"]:
            mark = {True: "yes", False: "no", None: "..."}[c["ok"]]
            print(f"  {mark:3}  {c['label']}: {c['evidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
