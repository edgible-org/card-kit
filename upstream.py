"""Read the upstream/ folder of a cards repo: requests the cards' testing suggests the authors of
an app could act on. Not a tool of its own: check-cards checks the files and card-site shows each
card the ones that name it.

A file starts with a header between two --- lines:

    app:      the app, as in its card
    project:  https address of the project, where its issues are filed
    cards:    the cards it applies to, as a list
    status:   draft | sent | resolved | wontfix
    found:    YYYY-MM-DD
    sent:     https address of the issue, once filed (required when status is sent)

then a first line "# Title" and the request, ready to paste as an issue.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import yaml

STATUSES = ("draft", "sent", "resolved", "wontfix")
HEADER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)


def load(root: Path) -> list[dict]:
    """Every request in root/upstream, as {file, meta, title, body}; a file that cannot be read
    has meta None and an error."""
    found = []
    for path in sorted((root / "upstream").glob("*.md")):
        if path.name == "README.md":
            continue
        item = {"file": path.name, "meta": None, "title": "", "body": "", "error": ""}
        try:
            m = HEADER.match(path.read_text())
            if not m:
                item["error"] = "no header between --- lines at the top"
            else:
                meta = yaml.safe_load(m.group(1))
                if not isinstance(meta, dict):
                    raise ValueError("the header is not a list of fields")
                if isinstance(meta.get("found"), date):
                    meta["found"] = meta["found"].isoformat()
                item["meta"], item["body"] = meta, m.group(2).strip()
                t = re.search(r"^# (.+)$", item["body"], re.M)
                item["title"] = t.group(1).strip() if t else ""
        except (OSError, ValueError, yaml.YAMLError) as exc:
            item["error"] = str(exc)
        found.append(item)
    return found


def problems(root: Path, cards: set[str]) -> list[tuple[str, list[str]]]:
    """For each request, (file, what is wrong with it); an empty list means it is fine."""
    out = []
    for item in load(root):
        errs = [item["error"]] if item["error"] else []
        meta = item["meta"] or {}
        if item["meta"] is not None:
            for field in ("app", "project", "cards", "status", "found"):
                if not meta.get(field):
                    errs.append(f"{field}: is missing")
            if meta.get("status") and meta["status"] not in STATUSES:
                errs.append(f"status: {meta['status']} is not one of {', '.join(STATUSES)}")
            if meta.get("project") and not str(meta["project"]).startswith("https://"):
                errs.append("project: should be an https address")
            if meta.get("found") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(meta["found"])):
                errs.append("found: should be YYYY-MM-DD")
            names = meta.get("cards")
            if names and not isinstance(names, list):
                errs.append("cards: should be a list")
            for name in names if isinstance(names, list) else []:
                if name not in cards:
                    errs.append(f"cards: {name} is not a card in this repo")
            if meta.get("status") == "sent" and not str(meta.get("sent") or "").startswith("https://"):
                errs.append("sent: status is sent, so it needs the issue's https address")
            if not item["title"]:
                errs.append("no first line starting with '# ' for the title")
        out.append((item["file"], errs))
    return out


def for_card(requests: list[dict], card: str) -> list[dict]:
    """The requests that name this card, open ones first."""
    mine = [r for r in requests if r["meta"] and card in (r["meta"].get("cards") or [])]
    return sorted(mine, key=lambda r: (r["meta"].get("status") in ("resolved", "wontfix"), r["file"]))
