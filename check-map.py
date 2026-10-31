#!/usr/bin/env python3
"""Check the edgible-cards skill's needs map against the sources it names.

    ../card-kit/run check-map          # from any repo, with card-kit beside it
    ./run check-map                    # from card-kit itself

Each entry in skills/edgible-cards/needs-map.yaml must have every required field, no field
the map does not define, a fit rating the skill knows, and the default and sensitive
exposure choices (regulated is optional). Its category must be a category name in
awesome-selfhosted's data, which renames one now and then, unless the entry has source
edgible: a category Edgible added, which must say in find where its apps come from, and
must not reuse an awesome-selfhosted name. Its cards must exist in edgible-org/cards. It also
lists the cards that no entry names, so a new one gets a place in the map.

It reads awesome-selfhosted-data and the GitHub API over the network, and exits 1 on a
problem.
"""
from __future__ import annotations

import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

import yaml

MAP = Path(__file__).resolve().parent / "skills" / "edgible-cards" / "needs-map.yaml"
SOURCES_FILE = MAP.with_name("sources.yaml")
READ_BY = {"code", "agent", "person"}
TAGS = "https://github.com/awesome-selfhosted/awesome-selfhosted-data/archive/refs/heads/master.tar.gz"
FIELDS = {"category", "jobs", "replaces", "drivers", "fit", "exposure", "machine", "cards", "ask"}
OPTIONAL = {"permissions", "builders", "source", "find", "candidates", "cards_wanted"}
SOURCES = {"edgible"}
EXPOSURE = {"default", "sensitive", "regulated"}
FITS = {"good", "conditional", "poor", "refused"}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "edgible-card-kit"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def categories() -> set[str]:
    names = set()
    with tarfile.open(fileobj=io.BytesIO(get(TAGS)), mode="r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile() and "/tags/" in m.name and m.name.endswith(".yml"):
                names.add(yaml.safe_load(tar.extractfile(m))["name"])
    return names


def cards(repo: str) -> set[str]:
    """The top-level directories of an Edgible repo: each one with a card.yml is a card."""
    tree = json.loads(get(f"https://api.github.com/repos/edgible-org/{repo}/git/trees/main?recursive=1"))
    return {path.split("/")[0] for path in (i["path"] for i in tree.get("tree", []))
            if path.count("/") == 1 and path.endswith("/card.yml") and not path.startswith(".")}


def main() -> int:
    entries = yaml.safe_load(MAP.read_text())
    known, card_names = categories(), cards("cards")
    problems = []
    for e in entries:
        c = e.get("category", "?")
        problems += [f"{c}: no {k}" for k in sorted(FIELDS - set(e))]
        problems += [f"{c}: unknown field {k}" for k in sorted(set(e) - FIELDS - OPTIONAL)]
        source = e.get("source")
        if source is None and c not in known:
            problems.append(f"{c}: not a category in awesome-selfhosted (or add source: edgible)")
        if source is not None and source not in SOURCES:
            problems.append(f"{c}: source must be one of {', '.join(sorted(SOURCES))}")
        if source == "edgible" and c in known:
            problems.append(f"{c}: is an awesome-selfhosted category, so drop source: edgible")
        if source == "edgible" and not e.get("find"):
            problems.append(f"{c}: source edgible needs find")
        if "cards_wanted" in e and not (isinstance(e["cards_wanted"], int) and e["cards_wanted"] >= 1):
            problems.append(f"{c}: cards_wanted must be a whole number, 1 or more")
        if e.get("candidates") and source != "edgible":
            problems.append(f"{c}: candidates are for source edgible; awesome-selfhosted supplies the rest")
        for cand in e.get("candidates", []):
            if not {"name", "repo", "why"} <= set(cand) or "/" not in str(cand.get("repo", "")):
                problems.append(f"{c}: a candidate needs name, repo (owner/name) and why: {cand}")
        if e.get("fit", {}).get("rating") not in FITS:
            problems.append(f"{c}: fit rating must be one of {', '.join(sorted(FITS))}")
        if not {"default", "sensitive"} <= set(e.get("exposure", {})):
            problems.append(f"{c}: exposure needs default and sensitive")
        problems += [f"{c}: unknown exposure {k}" for k in sorted(set(e.get("exposure", {})) - EXPOSURE)]
        problems += [f"{c}: no card {s} in edgible-org/cards" for s in e.get("cards", []) if s not in card_names]
    listed = yaml.safe_load(SOURCES_FILE.read_text())
    for src in listed.get("sources", []):
        for k in ("name", "url", "good_for", "read_by", "used_for", "reviewed"):
            if not src.get(k):
                problems.append(f"sources.yaml: {src.get('name', '?')}: no {k}")
        if src.get("read_by") not in READ_BY:
            problems.append(f"sources.yaml: {src.get('name', '?')}: read_by must be one of {', '.join(sorted(READ_BY))}")
    for item in listed.get("passed_over", []):
        for k in ("name", "repo", "date", "why"):
            if not item.get(k):
                problems.append(f"sources.yaml: passed over {item.get('name', '?')}: no {k}")
    for p in problems:
        print(p)
    named = {s for e in entries for s in e.get("cards", [])}
    for missing in sorted(card_names - named):
        print(f"note: {missing} is in no entry of the map")
    print(f"{len(entries)} entries: " + ("ok" if not problems else f"{len(problems)} problem(s)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
