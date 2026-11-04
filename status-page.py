#!/usr/bin/env python3
"""A page of what is running, for any AI agent with a shell: no MCP needed.

It asks the Edgible CLI on this machine for the organisation's devices and apps, checks that each
https hostname answers the way its auth mode says (as edgible-mcp's whats_running does), and
writes the same panel that MCP Apps hosts show (edgible-mcp/views/whats-running.html) with the
data in it, then opens it. It changes nothing.

    python3 status-page.py              # write ~/.edgible/status.html and open it
    python3 status-page.py --no-open    # write it and print its path
    python3 status-page.py --out f.html --app otter-wiki --device minipc
"""
import argparse
import concurrent.futures
import datetime
import http.client
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIEW = HERE / "edgible-mcp" / "views" / "whats-running.html"


def find_cli():
    """The edgible CLI: on PATH, or where its installer and setup put it (an AI app's shell may
    not have ~/.local/bin on its PATH)."""
    for c in (shutil.which("edgible"), str(Path.home() / ".local/bin/edgible"), "/usr/local/bin/edgible"):
        if c and os.access(c, os.X_OK):
            return c
    sys.exit("The Edgible CLI is not installed here (not on PATH, in ~/.local/bin or /usr/local/bin).")


def edgible(cli, *args, timeout=60):
    env = {**os.environ, "NO_COLOR": "1", "EDGIBLE_NO_UPDATE_NOTIFIER": "1", "EDGIBLE_NO_INTERACTIVE": "1"}
    try:
        r = subprocess.run([cli, *args], capture_output=True, text=True, timeout=timeout, env=env)
        return json.loads(r.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def auth_modes(detail):
    modes = []
    for a in (detail or {}).get("access") or []:
        for r in a.get("routes") or []:
            for m in r.get("auth") or []:
                m = "org" if m == "edgible-login" else m
                if m not in modes:
                    modes.append(m)
    return modes


def expected(modes):
    if "none" in modes:
        return "the app answers", lambda s, loc: 0 < s < 500
    if "org" in modes and "api-key" in modes:
        return "a redirect to sign in, or 401", lambda s, loc: s == 401 or (300 <= s < 400 and bool(loc))
    if "org" in modes:
        return "a redirect to the Edgible sign-in", lambda s, loc: 300 <= s < 400 and bool(loc)
    if "api-key" in modes:
        return "401 until a key is sent", lambda s, loc: s == 401
    return "an answer", lambda s, loc: 0 < s < 500


def probe(host, modes):
    want, ok = expected(modes)
    try:
        c = http.client.HTTPSConnection(host, timeout=10)
        c.request("GET", "/")
        r = c.getresponse()
        loc = (r.getheader("location") or "").split("?")[0]
        c.close()
        return ok(r.status, loc), f"{host}: {r.status}{' -> ' + loc if loc else ''} (expected {want})"
    except Exception as e:  # noqa: BLE001: any failure is the evidence
        return False, f"{host}: {type(e).__name__} (expected {want})"


def build(cli, app=None, device=None):
    who = edgible(cli, "whoami") or {}
    if not who.get("loggedIn"):
        sys.exit("The Edgible CLI is not signed in: run `edgible auth login --no-browser` first.")
    apps = edgible(cli, "app", "list")
    if apps is None:
        sys.exit("`edgible app list` did not answer.")
    devices = edgible(cli, "device", "list") or []
    system = [a for a in apps if a.get("name", "").startswith("device-") and a.get("name", "").endswith("-ingest")]
    if app:
        apps = [a for a in apps if app in (a.get("name"), a.get("id"))]
    else:
        apps = [a for a in apps if a not in system]
    if device:
        apps = [a for a in apps if any(device in (d.get("name"), d.get("id")) for d in a.get("devices") or [])]
        devices = [d for d in devices if device in (d.get("name"), d.get("id"))]
    status_of = {d.get("id"): d.get("status") for d in devices}

    def one(a):
        detail = edgible(cli, "app", "get", a["id"])
        modes = auth_modes(detail)
        probes = [probe(h, modes) for h in a.get("hostnames") or []] if a.get("protocol") == "https" else []
        certs = [f"certificate {c.get('hostname')}: {c.get('status')}" for c in (detail or {}).get("certificates") or [] if c.get("status") != "issued"]
        issues = [i.get("message") or json.dumps(i) for i in (detail or {}).get("deploymentIssues") or []]
        offline = any(status_of.get(d.get("id")) == "offline" for d in a.get("devices") or [])
        if a.get("protocol") != "https":
            works = "not checked"
        else:
            works = "yes" if probes and all(p[0] for p in probes) and not certs and not issues else "no"
        evidence = [p[1] for p in probes] + certs + issues + (["its device is offline"] if offline else [])
        return {
            "name": a.get("name"), "device": ", ".join(d.get("name", "") for d in a.get("devices") or []),
            "port": a.get("port"), "protocol": a.get("protocol"), "hostnames": a.get("hostnames") or [],
            "auth": modes if a.get("protocol") == "https" else ["none"], "status": a.get("status"),
            "works": works, "deviceOffline": offline, "evidence": "; ".join(evidence),
        }

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(one, apps))
    return {
        "organization": (who.get("organization") or {}).get("name"), "account": who.get("account"),
        "connector": None, "checkedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "filter": {}, "devices": [{"name": d.get("name"), "status": d.get("status"), "agentVersion": d.get("agentVersion")} for d in devices],
        "apps": rows, "system": 0 if app else len(system),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default=str(Path.home() / ".edgible" / "status.html"))
    p.add_argument("--app")
    p.add_argument("--device")
    p.add_argument("--no-open", action="store_true", help="write the page and print its path, without opening it")
    args = p.parse_args()
    view = build(find_cli(), args.app, args.device)
    data = json.dumps(view).replace("</", "<\\/")
    html = VIEW.read_text().replace("<script>", f"<script>window.EDGIBLE_VIEW = {data};</script>\n<script>", 1)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    ok = sum(1 for a in view["apps"] if a["works"] == "yes" and not a["deviceOffline"])
    print(f"{len(view['apps'])} apps, {ok} working; page: file://{out}")
    if not args.no_open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
