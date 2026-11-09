#!/usr/bin/env python3
"""Score needs-sweep prompts using the Cursor Agent CLI as the answering harness.

    python3 run-needs-sweep-cursor.py --out ~/edgible-needs-sweep/results/try --only bookmarks-and-link-sharing

Does not modify run-evals.py. Imports its scenario loader, Claude judge, score, and report
helpers so scoring stays comparable to held-out. Answers come from `agent -p --mode ask`
(read-only). Output should live outside the card-kit repo.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = Path(os.environ.get("EDGIBLE_NEEDS_SWEEP_DIR", Path.home() / "edgible-needs-sweep"))
CURSOR_SKILL = Path.home() / ".cursor" / "skills" / "edgible-cards"
CARD_KIT_SKILL = HERE.parent


def load_run_evals():
    path = HERE / "run-evals.py"
    spec = importlib.util.spec_from_file_location("run_evals", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


ev = load_run_evals()


def agent_bin() -> str:
    for name in ("agent", "cursor-agent"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit("Cursor Agent CLI not on PATH (expected `agent` or `cursor-agent`)")


def skill_dirs() -> list[Path]:
    dirs = []
    for p in (CURSOR_SKILL, CARD_KIT_SKILL):
        if (p / "SKILL.md").is_file():
            dirs.append(p.resolve())
    # Unique while preserving order.
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    if not out:
        sys.exit(
            f"edgible-cards skill not found at {CURSOR_SKILL} or {CARD_KIT_SKILL}. "
            "Install/link it for Cursor before running."
        )
    return out


def parse_stream_json(raw: str) -> dict:
    """Best-effort parse of Cursor stream-json output."""
    events, assistant_texts, tools = [], [], []
    result_text = ""
    skill_loaded_at = None
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(obj)
        typ = obj.get("type") or obj.get("event") or ""
        if typ in ("assistant", "message", "agent_message"):
            msg = obj.get("message") or obj.get("content") or obj
            content = msg.get("content") if isinstance(msg, dict) else msg
            if isinstance(content, str):
                assistant_texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        assistant_texts.append(block.get("text", ""))
                    elif isinstance(block, dict) and "text" in block:
                        assistant_texts.append(str(block["text"]))
        # Prefer the final result event: it is the completed answer once.
        if typ == "result" and isinstance(obj.get("result"), str) and obj.get("result").strip():
            result_text = obj["result"].strip()
        tool_call = obj.get("tool_call") if isinstance(obj.get("tool_call"), dict) else {}
        for key in tool_call:
            tools.append(key)
        blob = json.dumps(obj).lower()
        if any(s in blob for s in ("edgible-cards", "needs-map.yaml", "skill.md")):
            if skill_loaded_at is None:
                skill_loaded_at = len(events)
    if not events and raw.strip().startswith("{"):
        try:
            obj = json.loads(raw)
            events = [obj]
            if isinstance(obj.get("result"), str):
                result_text = obj["result"].strip()
        except json.JSONDecodeError:
            pass
    answer = result_text or "\n\n".join(t.strip() for t in assistant_texts if t and t.strip()).strip()
    if not answer:
        answer = raw.strip()
    # Drop a leading one-line "Checking…" status if the final result duplicated the body.
    return {
        "answer": answer,
        "tools": tools,
        "skill_loaded_at": skill_loaded_at,
        "events": events,
        "raw": raw,
    }


CURSOR_LIMIT = re.compile(r"(usage limit|rate limit|Authentication required|not logged in)", re.I)


def answer_cursor(prompt: str, model: str, timeout: int, mcp_config: Path | None) -> dict:
    """One read-only Cursor Agent session (--mode ask)."""
    skills = skill_dirs()
    with tempfile.TemporaryDirectory(prefix="needs-sweep-cursor-") as tmp:
        workspace = Path(tmp)
        if mcp_config and mcp_config.is_file():
            cursor_dir = workspace / ".cursor"
            cursor_dir.mkdir()
            (cursor_dir / "mcp.json").write_text(mcp_config.read_text())
        cmd = [
            agent_bin(),
            "-p",
            "--mode", "ask",
            "--output-format", "stream-json",
            "--trust",
            "--workspace", str(workspace),
        ]
        for d in skills:
            cmd.extend(["--add-dir", str(d)])
        if model:
            cmd.extend(["--model", model])
        if mcp_config:
            cmd.append("--approve-mcps")
        env = {k: v for k, v in os.environ.items()}
        try:
            done = subprocess.run(
                cmd + [prompt],
                capture_output=True,
                text=True,
                env=env,
                cwd=workspace,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
            err = (exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
            return {"error": f"timeout after {timeout}s", "events": [], "raw": out + "\n" + err}

        raw = (done.stdout or "") + (("\n" + done.stderr) if done.stderr else "")
        if done.returncode != 0 and CURSOR_LIMIT.search(raw):
            return {"error": raw.strip() or f"agent exited {done.returncode}", "events": [], "raw": raw}
        if done.returncode != 0 and not done.stdout.strip():
            return {"error": raw.strip() or f"agent exited {done.returncode}", "events": [], "raw": raw}

        parsed = parse_stream_json(done.stdout or raw)
        if CURSOR_LIMIT.search(parsed["answer"][:500] if parsed["answer"] else raw):
            return {"error": parsed["answer"] or raw.strip(), "events": parsed["events"], "raw": raw}
        if not parsed["answer"]:
            return {"error": "no answer from Cursor agent", "events": parsed["events"], "raw": raw}
        # If stream never mentioned the skill name, still treat a long advisory answer as
        # possibly loaded; score() uses skill_loaded_at vs should_load. Prefer detecting
        # skill via Skill tool or reading SKILL.md / needs-map in events.
        if parsed["skill_loaded_at"] is None:
            for e in parsed["events"]:
                s = json.dumps(e).lower()
                if "needs-map.yaml" in s or "skill.md" in s or "edgible-cards" in s:
                    parsed["skill_loaded_at"] = 1
                    break
        return {
            "answer": parsed["answer"],
            "tools": parsed["tools"],
            "skill_loaded_at": parsed["skill_loaded_at"],
            "events": parsed["events"],
            "raw": raw,
        }


def write_mcp_config(path: Path, command: str) -> None:
    path.write_text(json.dumps({
        "mcpServers": {
            "edgible": {"command": command, "args": []}
        }
    }, indent=2) + "\n")


def judge_cursor(scenario: dict, reply: str, model: str, timeout: int) -> dict:
    """Same judge contract as run-evals.judge, answered by Cursor ask mode (no tools needed)."""
    items = {"expect": scenario["expect"], "must_not": scenario["must_not"], "principles": ev.PRINCIPLES}
    prompt = f"""You are judging an AI assistant's answer to a person, for a test of an agent skill.
Judge only the answer below, strictly and fairly. Quote the answer as evidence.

The person asked:
<prompt>
{scenario['prompt']}
</prompt>

The assistant answered:
<answer>
{reply or '(no answer)'}
</answer>

Judge three lists:
- expect: what a good answer does. For each, pass is true only if the answer clearly does it.
- must_not: what fails an answer outright. For each, violated is true if the answer does it.
- principles: general principles. For each, pass is true, false, or null when it does not apply to this prompt.

{json.dumps(items, indent=2)}

Then give better: one sentence on what would most have improved this answer, or "" if nothing.

Reply with only this JSON, no other text:
{{"expect": [{{"item": "...", "pass": true, "evidence": "..."}}],
  "must_not": [{{"item": "...", "violated": false, "evidence": "..."}}],
  "principles": [{{"item": "...", "pass": null, "evidence": "..."}}],
  "better": "..."}}"""
    run = answer_cursor(prompt, model, timeout, mcp_config=None)
    if "error" in run:
        return {"error": run["error"], "raw": run.get("raw", "")}
    text = run["answer"]
    try:
        return json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {"error": "the Cursor judge did not return JSON", "raw": text[-2000:]}



def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="directory for report and transcripts (outside card-kit)")
    ap.add_argument("--set", type=Path, default=HERE / "needs-sweep.yaml")
    ap.add_argument("--only", nargs="+", default=[], metavar="ID")
    ap.add_argument("--model", default="", help="Cursor --model id (from agent --list-models)")
    ap.add_argument("--judge-model", default="",
                    help="model for the judging session; for --judge-harness claude, a Claude CLI model "
                         "(e.g. sonnet); for cursor, a Cursor --model id")
    ap.add_argument("--judge-harness", choices=("claude", "cursor"), default="claude",
                    help="who judges: Claude Code (default, same as held-out) or Cursor Agent ask mode")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--mcp", default=shutil.which("edgible-mcp") or "",
                    help="stdio Edgible MCP command for find/describe; default edgible-mcp on PATH; '' for none")
    args = ap.parse_args(argv)

    # HERE = …/card-kit/skills/edgible-cards/evals → parents[2] is card-kit
    card_kit = HERE.parents[2]
    try:
        args.out.resolve().relative_to(card_kit.resolve())
        print(f"warning: --out is inside card-kit ({card_kit}); prefer ~/edgible-needs-sweep/…", file=sys.stderr)
    except ValueError:
        pass

    scenarios = [s for s in ev.load_scenarios(args.set) if not args.only or s["id"] in args.only]
    if not scenarios:
        sys.exit("no prompts to run")

    skill_dirs()  # fail fast if skill missing
    args.out.mkdir(parents=True, exist_ok=True)

    mcp_config = None
    if args.mcp:
        mcp_config = args.out / "mcp.json"
        write_mcp_config(mcp_config, args.mcp)

    git = lambda *a: subprocess.run(
        ["git", "-C", str(CARD_KIT_SKILL), *a], capture_output=True, text=True
    ).stdout.strip()
    agent_ver = subprocess.run([agent_bin(), "--version"], capture_output=True, text=True).stdout.strip()
    meta = {
        "date": str(date.today()),
        "harness": "cursor",
        "model": args.model or "default",
        "card_kit": git("rev-parse", "--short", "HEAD") or "unknown",
        # run-evals.report() expects meta['claude']; put the Cursor agent version there.
        "claude": f"cursor-agent {agent_ver} model={args.model or 'default'}",
        "agent": agent_ver,
        "mcp": "edgible find/describe" if args.mcp else "none",
        "judge_harness": args.judge_harness,
        "judge_model": args.judge_model or "default",
        "set": str(args.set),
    }

    results, stopped = [], ""
    for s in scenarios:
        print(f"{s['id']}: answering (cursor)", flush=True)
        run = answer_cursor(s["prompt"], args.model, args.timeout, mcp_config)
        (args.out / f"{s['id']}.transcript.jsonl").write_text(
            "\n".join(json.dumps(e) for e in run.get("events", [])) + "\n"
        )
        (args.out / f"{s['id']}.raw.txt").write_text(run.get("raw", "") + "\n")
        if "error" in run:
            stopped = f"{s['id']}: {run['error']}"
            print(f"stopped, not scored: {stopped}", flush=True)
            break
        (args.out / f"{s['id']}.answer.md").write_text(run["answer"] + "\n")
        print(f"{s['id']}: judging ({args.judge_harness})", flush=True)
        if args.judge_harness == "claude":
            verdict = ev.judge(s, run["answer"], args.timeout, args.judge_model)
            if "error" in verdict and ev.LIMIT.search(
                json.loads(verdict["raw"]).get("result", "")
                if verdict.get("raw", "").strip().startswith("{")
                else verdict.get("raw", "")
            ):
                stopped = f"{s['id']}: the Claude judge hit the usage limit (try --judge-harness cursor)"
                print(f"stopped, not scored: {stopped}", flush=True)
                break
        else:
            verdict = judge_cursor(s, run["answer"], args.judge_model or args.model or "composer-2.5", args.timeout)
            if "error" in verdict:
                stopped = f"{s['id']}: {verdict['error']}"
                print(f"stopped, not scored: {stopped}", flush=True)
                break
        r = ev.score(s, run, verdict)
        results.append(r)
        print(
            f"{s['id']}: {'pass' if r['pass'] else 'FAIL'} "
            f"(expect {r['expect_passed']}/{r['expect_total']}, "
            f"skill {'loaded' if r['loaded'] else 'not loaded'})",
            flush=True,
        )

    meta["not_run"] = [s["id"] for s in scenarios[len(results):]]
    meta["stopped"] = stopped
    home = lambda text: text.replace(str(Path.home()), "~")
    (args.out / "results.json").write_text(
        home(json.dumps({"meta": meta, "results": results}, indent=2)) + "\n"
    )
    report_text = ev.report(results, meta)
    # Label harness clearly at the top.
    report_text = report_text.replace(
        "# edgible-cards skill evals,",
        "# edgible-cards needs sweep (Cursor harness),",
        1,
    )
    (args.out / "report.md").write_text(home(report_text))
    print(f"\n{sum(r['pass'] for r in results)}/{len(results)} pass. Report: {args.out / 'report.md'}")
    if stopped:
        print(f"Not run: {', '.join(meta['not_run'])}")
        return 2
    return 0 if results and all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
