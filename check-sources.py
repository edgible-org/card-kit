#!/usr/bin/env python3
"""Check that the places we find apps are still in good order: sources.yaml and the needs map's candidates.

    ../card-kit/run check-sources                 # print the report
    ../card-kit/run check-sources --out report.md # also write it, for an issue

It looks at four things and only reports; it never edits the data, because a "reviewed"
date means a person looked, and a person decides what to drop.
  a source's address no longer answers
  a source's reviewed date is older than --stale-days (default 90)
  a needs-map candidate's repository is archived or has had no push in six months
  an app looked at but not yet a card (passed_over) whose check: unarchived now holds

GITHUB_TOKEN, when set, raises GitHub's rate limit; without it a long list can run out, and
the apps that could not be checked are listed as such, not as problems. Exit code is 0
whether or not there are findings; the first line of the report says how many.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent / "skills" / "edgible-cards"
UA = {"User-Agent": "edgible-card-kit"}


def reachable(url: str) -> str | None:
    """None when the address answers, else why it does not."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=30):
                return None
        except urllib.error.HTTPError as e:
            # Some sites refuse HEAD or bots; a refusal to a script is not a dead address.
            if method == "HEAD" or e.code in (403, 405, 429):
                if e.code in (403, 405, 429) and method == "GET":
                    return None
                continue
            return f"answers {e.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return f"does not answer ({getattr(e, 'reason', e)})"
    return "does not answer"


def repo_facts(repo: str) -> dict | str:
    """archived and pushed_at from GitHub, or a string saying it could not be read."""
    headers = dict(UA, Accept="application/vnd.github+json")
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        return "not found, or renamed" if e.code == 404 else f"GitHub answered {e.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return f"could not reach GitHub ({getattr(e, 'reason', e)})"
    return {"archived": d["archived"], "pushed": datetime.fromisoformat(d["pushed_at"][:10]).date()}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stale-days", type=int, default=90, help="a reviewed date older than this is reported")
    ap.add_argument("--out", type=Path, help="also write the report to this file")
    args = ap.parse_args(argv)

    today = date.today()
    sources = yaml.safe_load((SKILL / "sources.yaml").read_text()) or {}
    needs = yaml.safe_load((SKILL / "needs-map.yaml").read_text()) or []
    findings: list[str] = []
    unchecked: list[str] = []

    for s in sources.get("sources", []):
        if str(s["url"]).startswith("http"):
            why = reachable(s["url"])
            if why:
                findings.append(f"**{s['name']}** ({s['url']}) {why}.")
        reviewed = s.get("reviewed")
        if reviewed:
            day = reviewed if isinstance(reviewed, date) else datetime.fromisoformat(str(reviewed)[:10]).date()
            if today - day > timedelta(days=args.stale_days):
                findings.append(f"**{s['name']}** was last reviewed {day}, over {args.stale_days} days ago.")

    seen: set[str] = set()
    for n in needs:
        for c in n.get("candidates", []):
            if c["repo"] in seen:
                continue
            seen.add(c["repo"])
            facts = repo_facts(c["repo"])
            if isinstance(facts, str):
                (findings if "not found" in facts else unchecked).append(f"**{c['name']}** ({c['repo']}) {facts}.")
            elif facts["archived"]:
                findings.append(f"**{c['name']}** ({c['repo']}), a candidate for {n['category']}, is archived.")
            elif today - facts["pushed"] > timedelta(days=183):
                findings.append(f"**{c['name']}** ({c['repo']}), a candidate for {n['category']}, has had no push since {facts['pushed']}.")

    for p in sources.get("passed_over", []):
        if p.get("check") == "unarchived":
            facts = repo_facts(p["repo"])
            if isinstance(facts, str):
                unchecked.append(f"**{p['name']}** ({p['repo']}) {facts}.")
            elif not facts["archived"]:
                findings.append(f"**{p['name']}** ({p['repo']}) is no longer archived: {p.get('revisit', 'worth another look')}.")

    lines = [f"{len(findings)} thing{'s' if len(findings) != 1 else ''} to look at in the sources and candidates ({today})."]
    if findings:
        lines += ["", *[f"- {f}" for f in findings]]
    if unchecked:
        lines += ["", "Could not be checked this time:", *[f"- {u}" for u in unchecked]]
    lines += ["", "To review a source, check it still serves the cards and set its `reviewed` date in "
                  "`skills/edgible-cards/sources.yaml` in edgible-org/card-kit. To drop a candidate, remove it "
                  "from the needs map and, if it is worth remembering, add it to `passed_over`."]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.out:
        args.out.write_text(report)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
