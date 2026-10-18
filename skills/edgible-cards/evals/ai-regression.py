#!/usr/bin/env python3
"""Measure the edgible-cards skill on several agents, indexed against Claude.

For each agent in agents.yaml that this machine can run, Coder Eval (coder-eval on PATH)
answers each prompt of an eval set, with the skill and, for the skill's lift, without it.
run-evals.py's judge then scores every answer against the prompt's expect and must_not items.
The report gives each agent's index: the expect items its answers met, as a percentage of
what the baseline's answers met on the same prompts, with the range over runs; must_not
breaks are counted beside it as critical failures, never in it.

Answering sessions are read-only: no shell, edits or web. Claude Code runs on the logged-in
subscription; OpenCode runs local models through Ollama on 127.0.0.1:11434.
"""
import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("run_evals", HERE / "run-evals.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

PLUGIN_ROOT = HERE.parents[2]          # holds skills/edgible-cards: what both harnesses load
NO_SKILL = HERE / "agents" / "no-skill"  # a plugin root with an empty skills/ folder
OLLAMA = "http://127.0.0.1:11434"
READ_ONLY = ["Skill", "Read", "Glob", "Grep"]
DISALLOWED = [*ev.NO_SHELL, "Task"]
# Each harness and the command it needs on PATH (Antigravity's ships inside coder-eval[antigravity]).
HARNESSES = {"claude-code": "claude", "opencode": "opencode", "codex": "codex", "antigravity": "coder-eval"}
# A usage or rate limit is not an answer, on any harness, and is never scored.
# Hosted models through OpenCode: the provider prefix and the key it needs. Keys come from the
# environment or from KEYS_FILE (NAME=value lines, kept out of any repo), and are never printed.
PROVIDER_KEYS = {"deepseek": "DEEPSEEK_API_KEY", "openrouter": "OPENROUTER_API_KEY", "gemini": "GEMINI_API_KEY"}
KEYS_FILE = Path.home() / ".config" / "ai-regression.env"
LIMIT = re.compile(r"You've hit your [a-z ]*limit|usage limit|rate limit|quota", re.I)


def load_agents(path: Path) -> list[dict]:
    """agents.yaml: a list of flat entries, `- id: x` then `  key: value` lines."""
    agents, current = [], None
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = re.sub(r"\s+#.*$", "", line) if not line.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        m = re.match(r"^(- |  )(\w+): (.+)$", line)
        if not m or (m.group(1) == "  " and current is None):
            sys.exit(f"{path.name} line {number}: not in the shape ai-regression.py reads: {line!r}")
        if m.group(1) == "- ":
            current = {}
            agents.append(current)
        value = m.group(3).strip()
        current[m.group(2)] = int(value) if value.isdigit() else value == "true" if value in ("true", "false") else value
    for a in agents:
        if not {"id", "harness", "model"} <= a.keys() or a["harness"] not in HARNESSES:
            sys.exit(f"{path.name}: {a.get('id', '?')} needs an id, a model, and a harness: {', '.join(HARNESSES)}")
    if sum(bool(a.get("baseline")) for a in agents) != 1:
        sys.exit(f"{path.name}: exactly one agent is the baseline")
    return agents


def memory_gb() -> float:
    if platform.system() == "Darwin":
        return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 2**30
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) / 2**20
    return 0


def ollama_models() -> set[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:
            return {m["name"] for m in json.load(r)["models"]}
    except OSError:
        return set()


def provider_keys() -> dict:
    keys = {}
    if KEYS_FILE.exists():
        for line in KEYS_FILE.read_text().splitlines():
            name, _, value = line.strip().removeprefix("export ").partition("=")
            if name in PROVIDER_KEYS.values() and value:
                keys[name] = value.strip().strip("'\"")
    return {**keys, **{k: os.environ[k] for k in PROVIDER_KEYS.values() if os.environ.get(k)}}


def why_not(agent: dict, mem: float, pulled: set[str], keys: dict) -> str:
    """Why this machine can't run the agent, or '' when it can."""
    binary = HARNESSES[agent["harness"]]
    if not shutil.which(binary):
        return f"no {binary} on PATH"
    key = (PROVIDER_KEYS["gemini"] if agent["harness"] == "antigravity" else
           PROVIDER_KEYS.get(agent["model"].split("/")[0]) if agent["harness"] == "opencode" else None)
    if key and key not in keys:
        return f"no {key} in the environment or {KEYS_FILE.name}"
    if agent.get("memory_gb", 0) > mem + 0.5:
        return f"needs {agent['memory_gb']} GB of memory, this machine has {mem:.0f}"
    if agent["model"].startswith("ollama/") and agent["model"].removeprefix("ollama/") not in pulled:
        return f"{agent['model'].removeprefix('ollama/')} is not pulled into Ollama"
    return ""


def write_task(scenario: dict, folder: Path) -> Path:
    """A Coder Eval task for one prompt. JSON is YAML, so the file is written as JSON."""
    should_load = not any("does not load" in e for e in scenario["expect"])
    task = {"task_id": scenario["id"], "description": f"edgible-cards eval prompt {scenario['id']}",
            "initial_prompt": scenario["prompt"], "tags": ["edgible-cards"],
            "success_criteria": [{"type": "skill_triggered", "description": "edgible-cards loads as it should",
                                  "skill_name": ev.SKILL, "expected_skill": ev.SKILL if should_load else ""}]}
    path = folder / f"{scenario['id']}.yaml"
    path.write_text(json.dumps(task, indent=2) + "\n")
    return path


def write_experiment(agent: dict, lift: bool, folder: Path) -> Path:
    if agent["harness"] == "claude-code":
        base = {"type": "claude-code", "model": agent["model"], "permission_mode": "default",
                "setting_sources": [], "allowed_tools": READ_ONLY, "disallowed_tools": DISALLOWED}
    elif agent["harness"] == "antigravity":
        # Gemini through Google's Antigravity harness, which enforces the tool lists (Bash is
        # its run_command) and approves the rest; Skill has no builtin, so it reads the files.
        base = {"type": "antigravity", "model": agent["model"],
                "allowed_tools": [t for t in READ_ONLY if t != "Skill"], "disallowed_tools": DISALLOWED}
    elif agent["harness"] == "codex":
        # Codex opens a skill by reading its files through its shell; plan is its read-only
        # sandbox.
        base = {"type": "codex", "permission_mode": "plan", "model": agent["model"]}
    else:
        # OpenCode has no tool allowlist Coder Eval can set: its config (opencode_env) switches
        # the shell, edit and fetch tools off instead.
        base = {"type": "opencode", "model": agent["model"], "permission_mode": "default",
                "require_token_telemetry": False}
    arms = [("skill", PLUGIN_ROOT)] + ([("no-skill", NO_SKILL)] if lift else [])
    limits = {"task_timeout": agent.get("timeout", 900), "turn_timeout": agent.get("timeout", 900)}
    experiment = {"experiment_id": f"ai-regression-{agent['id']}".replace(".", "-"),
                  "description": f"{agent['harness']} + {agent['model']}",
                  "variants": [{"variant_id": arm, "run_limits": limits,
                                "agent": {**base, "plugins": [{"type": "local", "path": str(root)}]}}
                               for arm, root in arms]}
    path = folder / f"{agent['id']}.yaml"
    path.write_text(json.dumps(experiment, indent=2) + "\n")
    return path


def opencode_env(agents: list[dict]) -> dict:
    models = {a["model"].removeprefix("ollama/"): {"name": a["model"]} for a in agents
              if a["model"].startswith("ollama/")}
    # OpenCode's own model list lags OpenRouter's, so name each OpenRouter model it is to use.
    routed = {a["model"].removeprefix("openrouter/"): {"name": a["model"]} for a in agents
              if a["model"].startswith("openrouter/")}
    config = {"$schema": "https://opencode.ai/config.json",
              "provider": {"ollama": {"npm": "@ai-sdk/openai-compatible", "name": "Ollama",
                                      "options": {"baseURL": f"{OLLAMA}/v1"}, "models": models},
                           **({"openrouter": {"models": routed}} if routed else {})},
              "permission": {"bash": "deny", "edit": "deny", "webfetch": "deny"},
              "tools": {t: False for t in ("bash", "write", "edit", "patch", "webfetch", "todowrite")}}
    # Without these, OpenCode loads ~/.claude/skills itself, and the no-skill arm has the skill.
    return {"OPENCODE_CONFIG_CONTENT": json.dumps(config), "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1"}


def final_text(task: dict) -> str:
    for turn in reversed(task.get("iterations") or []):
        text = (turn.get("result_summary") or {}).get("result") or turn.get("agent_output") or ""
        if text.strip():
            return text
    return ""


def cost(task: dict) -> float:
    return round((task.get("total_token_usage") or {}).get("total_cost_usd") or 0, 4)


def judged(task_json: Path, scenario: dict, judge_model: str) -> dict:
    """One answer, judged; kept beside its task.json so a rerun of the report judges nothing twice."""
    saved = task_json.with_name("judged.json")
    task = json.loads(task_json.read_text())
    if saved.exists():
        return {"cost_usd": cost(task), **json.loads(saved.read_text())}
    reply = final_text(task)
    crit = next((c for c in task.get("success_criteria_results", []) if c.get("criterion_type") == "skill_triggered"), {})
    row = {"prompt": scenario["id"], "arm": task_json.parts[-4], "run": task_json.parent.name,
           "status": task["final_status"], "seconds": round(task.get("duration_seconds") or 0),
           # At the provider's list price: what a subscription run would cost on an API key.
           "cost_usd": cost(task),
           "loaded": crit.get("observed_label") == "yes", "loaded_as_it_should": crit.get("score") == 1.0,
           "answer": reply}
    # A provider's refusal (a bad model, a limit) can land in the answer's place: not an answer.
    refused = [e["message"] for t in task.get("iterations") or [] for e in t.get("provider_errors") or []
               if not e.get("will_retry")]
    # A crashed run can carry its error text where the answer goes: never judge it.
    crashed = task["final_status"] == "ERROR" or any(t.get("crashed") for t in task.get("iterations") or [])
    if refused or crashed or not reply or LIMIT.search(reply[:300]):
        row["error"] = (refused[0] if refused else task.get("error_message") or reply.strip()) or "no answer"
    else:
        verdict = ev.judge(scenario, reply, timeout=600, model=judge_model)
        if "error" in verdict:
            row["error"] = verdict["error"]
        else:
            row["expect_met"] = sum(e.get("pass") is True for e in verdict.get("expect", []))
            row["critical_failures"] = [m["item"] for m in verdict.get("must_not", []) if m.get("violated") is True]
            row["better"] = verdict.get("better", "")
        row["verdict"] = verdict
    if "error" not in row or not LIMIT.search(row["error"]):
        saved.write_text(json.dumps(row, indent=2) + "\n")
    return row


def summarise(rows: list[dict], scenarios: list[dict], agents: list[dict]) -> list[dict]:
    """Per agent and arm: items met by run, indexed against the baseline's skill arm."""
    expect_total = {s["id"]: len(s["expect"]) for s in scenarios}
    baseline = next(a["id"] for a in agents if a.get("baseline"))
    scored = [r for r in rows if "expect_met" in r]
    base_prompts = {r["prompt"] for r in scored if r["agent"] == baseline and r["arm"] == "skill"}
    base_mean = {p: statistics.mean(r["expect_met"] for r in scored if r["agent"] == baseline
                                    and r["arm"] == "skill" and r["prompt"] == p) for p in base_prompts}
    out = []
    for agent in agents:
        for arm in ("skill", "no-skill"):
            mine = [r for r in rows if r["agent"] == agent["id"] and r["arm"] == arm]
            if not mine:
                continue
            ok = [r for r in mine if "expect_met" in r]
            prompts = sorted({r["prompt"] for r in ok} & base_prompts)
            line = {"agent": agent["id"], "arm": arm, "harness": agent["harness"], "model": agent["model"],
                    "answers": len(mine), "errors": len(mine) - len(ok), "prompts": len(prompts),
                    "expect_met": sum(r["expect_met"] for r in ok), "expect_total": sum(expect_total[r["prompt"]] for r in ok),
                    "critical_failures": sum(len(r["critical_failures"]) for r in ok),
                    "loaded_as_it_should": sum(r["loaded_as_it_should"] for r in mine),
                    "median_seconds": round(statistics.median(r["seconds"] for r in mine)),
                    "cost_usd": round(sum(r.get("cost_usd", 0) for r in mine), 4)}
            base = sum(base_mean[p] for p in prompts)
            if prompts and base:
                # One index per run number: run k's answers over the baseline's mean, on the same prompts.
                runs = sorted({r["run"] for r in ok})
                per_run = []
                for k in runs:
                    got = {r["prompt"]: r["expect_met"] for r in ok if r["run"] == k and r["prompt"] in prompts}
                    if len(got) == len(prompts):
                        per_run.append(100 * sum(got.values()) / base)
                mean = statistics.mean(r["expect_met"] for r in ok if r["prompt"] in prompts) * len(prompts)
                line["index"] = round(100 * mean / base)
                if per_run:
                    line["index_range"] = [round(min(per_run)), round(max(per_run))]
            out.append(line)
    for line in out:
        if line["arm"] == "skill":
            bare = next((o for o in out if o["agent"] == line["agent"] and o["arm"] == "no-skill"), None)
            if bare and bare.get("index") is not None and line.get("index") is not None:
                line["lift"] = line["index"] - bare["index"]
    return out


def report(summary: list[dict], skipped: list[tuple], rows: list[dict], meta: dict) -> str:
    lines = [f"# AI regression, {meta['date']}", "",
             f"Skill from card-kit `{meta['card_kit']}`, eval set `{meta['set']}` ({meta['prompts']} prompts, "
             f"{meta['runs']} run{'s' * (meta['runs'] != 1)} each), judged by `{meta['judge_model'] or 'default'}`, "
             f"Coder Eval {meta['coder_eval']}. Index: expect items met, as a percentage of what the baseline "
             f"`{meta['baseline']}` met on the same prompts; the range is over runs. Critical failures are must_not "
             "breaks, counted beside the index, never in it. Lift is the index with the skill minus without. Cost is at list price, "
             "so it shows what a subscription's runs would cost on an API key; local models cost nothing.", "",
             "| Agent | Arm | Index | Range | Lift | Critical failures | Skill loaded as it should | Items met | Median time | Cost | Errors |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        rng = "–".join(map(str, s["index_range"])) if "index_range" in s else ""
        lift = f"{s['lift']:+d}" if "lift" in s else ""
        # The arm without the skill has nothing to load, so it has no load rate.
        loads = f"{s['loaded_as_it_should']}/{s['answers']}" if s["arm"] == "skill" else "–"
        lines.append(f"| {s['agent']} | {s['arm']} | {s.get('index', '')} | {rng} | {lift} | {s['critical_failures']} | "
                     f"{loads} | {s['expect_met']}/{s['expect_total']} | "
                     f"{s['median_seconds']} s | ${s['cost_usd']:.2f} | {s['errors']} |")
    if skipped:
        lines += ["", "Not run on this machine:", ""] + [f"- {a}: {why}" for a, why in skipped]
    failures = [r for r in rows if r.get("critical_failures")]
    if failures:
        lines += ["", "## Critical failures", ""]
        lines += [f"- {r['agent']} {r['arm']}, {r['prompt']} run {r['run']}: {'; '.join(r['critical_failures'])}" for r in failures]
    errors = [r for r in rows if "error" in r]
    if errors:
        lines += ["", "## Not scored", ""]
        lines += [f"- {r['agent']} {r['arm']}, {r['prompt']} run {r['run']} ({r['status']}): {r['error'][:200]}" for r in errors]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="directory for the report, results and runs")
    ap.add_argument("--set", type=Path, default=HERE / "held-out.yaml")
    ap.add_argument("--agents", nargs="+", default=[], metavar="ID", help="only these agents (the baseline always runs)")
    ap.add_argument("--only", nargs="+", default=[], metavar="ID", help="only these prompts")
    ap.add_argument("--rotate", type=int, choices=range(7), metavar="DAY",
                    help="only this day's share of a 7-day rotation, as run-evals.py; --rotate today uses today")
    ap.add_argument("--runs", type=int, default=3, help="runs per prompt and arm (default 3)")
    ap.add_argument("--no-lift", action="store_true", help="skip the without-the-skill arm")
    ap.add_argument("--judge-model", default="sonnet")
    ap.add_argument("--plan", action="store_true", help="write the tasks and say what would run, then stop")
    argv = [str(date.today().weekday()) if a == "today" else a for a in argv]
    args = ap.parse_args(argv)
    if not shutil.which("coder-eval"):
        sys.exit("coder-eval is not on PATH: uv tool install coder-eval")

    scenarios = [s for s in ev.load_scenarios(args.set) if not args.only or s["id"] in args.only]
    if args.rotate is not None:
        scenarios = [s for i, s in enumerate(scenarios) if i % 7 == args.rotate]
    agents = load_agents(HERE / "agents.yaml")
    if unknown := set(args.agents) - {a["id"] for a in agents}:
        sys.exit(f"not in agents.yaml: {', '.join(sorted(unknown))}")
    agents = [a for a in agents if a.get("baseline") or not args.agents or a["id"] in args.agents]
    mem, pulled, keys = memory_gb(), ollama_models(), provider_keys()
    skipped = [(a["id"], why) for a in agents if (why := why_not(a, mem, pulled, keys))]
    runnable = [a for a in agents if a["id"] not in dict(skipped)]

    out = args.out.resolve()
    tasks, experiments = out / "tasks", out / "experiments"
    for d in (tasks, experiments, NO_SKILL / "skills"):
        d.mkdir(parents=True, exist_ok=True)
    task_files = [write_task(s, tasks) for s in scenarios]
    print(f"{len(scenarios)} prompts, {args.runs} runs, agents: {', '.join(a['id'] for a in runnable) or 'none'}")
    for a, why in skipped:
        print(f"  skipped {a}: {why}")
    if args.plan or not scenarios:
        return 0

    env = {**os.environ, **keys, "TELEMETRY_ENABLED": "false", **opencode_env(runnable)}
    env.pop("CLAUDECODE", None)
    by_id = {s["id"]: s for s in scenarios}
    rows, stopped, limited = [], False, []
    for agent in runnable:
        run_dir = out / "runs" / agent["id"]
        if not run_dir.exists():
            experiment = write_experiment(agent, not args.no_lift, experiments)
            print(f"{agent['id']}: answering", flush=True)
            subprocess.run(["coder-eval", "run", "-e", str(experiment), "--repeats", str(args.runs),
                            "--run-dir", str(run_dir), *map(str, task_files)],
                           env=env, cwd=out, stdout=open(out / f"{agent['id']}.log", "w"), stderr=subprocess.STDOUT)
        for task_json in sorted(run_dir.rglob("task.json")):
            task_id = json.loads(task_json.read_text())["task_id"]
            if task_id not in by_id:
                continue
            row = {"agent": agent["id"], **judged(task_json, by_id[task_id], args.judge_model)}
            rows.append(row)
            print(f"  {row['arm']:8} {task_id} #{row['run']}  loaded={row['loaded']}  "
                  + (f"ERROR {row['error'][:80]}" if "error" in row else
                     f"expect {row['expect_met']}/{len(by_id[task_id]['expect'])}  critical {len(row['critical_failures'])}"),
                  flush=True)
            if "error" in row and LIMIT.search(row["error"]):
                stopped = True
        if stopped:
            # Another provider's agents can still run.
            print(f"{agent['id']}: stopped at a usage limit", file=sys.stderr)
            stopped = False
            limited.append(agent["id"])

    git = lambda *a: subprocess.run(["git", "-C", str(HERE), *a], capture_output=True, text=True).stdout.strip()
    version = subprocess.run(["coder-eval", "--version"], capture_output=True, text=True).stdout.strip()
    meta = {"date": str(date.today()), "card_kit": git("rev-parse", "--short", "HEAD") or "unknown",
            "set": args.set.name, "prompts": len(scenarios), "runs": args.runs, "judge_model": args.judge_model,
            "baseline": next(a["id"] for a in agents if a.get("baseline")), "coder_eval": version,
            "memory_gb": round(mem), "machine": platform.node().split(".")[0]}
    summary = summarise(rows, scenarios, agents)
    public = [{k: v for k, v in r.items() if k not in ("answer", "verdict")} for r in rows]
    skipped += [(a, "stopped at a usage limit; the answers before it are scored") for a in limited]
    (out / "results.json").write_text(json.dumps({"meta": meta, "summary": summary, "skipped": skipped,
                                                  "answers": public}, indent=2) + "\n")
    (out / "report.md").write_text(report(summary, skipped, rows, meta))
    print(f"report: {out / 'report.md'}")
    return 2 if limited else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
