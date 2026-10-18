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
MAX_STEPS = 30
# The answer without the skill gets three times the time the answer with it took (at least
# MIN_SECONDS). Past that it is stopped, recorded as terminated and scored 0: a person waiting
# on it would get nothing.
LIFT_TIME, MIN_SECONDS = 3, 120
# A forecast is a median: a prepaid provider's balance must cover it half again.
HEADROOM = 1.5
# Each prepaid provider's spend per job, unless --max-spend says otherwise: enough for a night's
# rotation, so a full run is a deliberate choice.
DEFAULT_SPEND = 0.50
TERMINATED = {"TIMEOUT": "over the time limit", "MAX_TURNS_EXHAUSTED": f"over {MAX_STEPS} steps",
              "TOKEN_BUDGET_EXCEEDED": "over the token budget", "COST_BUDGET_EXCEEDED": "over the cost budget"}
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


def provider(agent: dict) -> str:
    """Who bills the agent's answers: a prepaid provider, a subscription, or nobody (local)."""
    if agent["harness"] in ("claude-code", "codex"):
        return "subscription"
    if agent["harness"] == "antigravity":
        return "gemini"
    prefix = agent["model"].split("/")[0]
    return prefix if prefix in PROVIDER_KEYS else "local"


def balance(name: str, keys: dict) -> float | None:
    """What is left to spend, in USD, for a prepaid provider; None when it can't be asked."""
    try:
        if name == "deepseek":
            req = urllib.request.Request("https://api.deepseek.com/user/balance",
                                         headers={"Authorization": f"Bearer {keys['DEEPSEEK_API_KEY']}"})
            with urllib.request.urlopen(req, timeout=15) as r:
                infos = json.load(r).get("balance_infos", [])
            return sum(float(i["total_balance"]) for i in infos if i.get("currency") == "USD")
        if name == "openrouter":
            auth = {"Authorization": f"Bearer {keys['OPENROUTER_API_KEY']}"}
            with urllib.request.urlopen(urllib.request.Request("https://openrouter.ai/api/v1/credits", headers=auth), timeout=15) as r:
                d = json.load(r)["data"]
            left = d["total_credits"] - d["total_usage"]
            with urllib.request.urlopen(urllib.request.Request("https://openrouter.ai/api/v1/key", headers=auth), timeout=15) as r:
                k = json.load(r)["data"]
            # A key can carry its own spending cap, below the account's credit.
            if k.get("limit") is not None:
                left = min(left, k["limit"] - (k.get("usage") or 0))
            return left
    except (OSError, KeyError, ValueError):
        return None
    return None


def history(folder: Path) -> dict:
    """Median cost and time per answer, per agent and arm, from earlier runs' results.json."""
    seen: dict = {}
    for path in folder.rglob("results.json"):
        try:
            answers = json.loads(path.read_text()).get("answers", [])
        except ValueError:
            continue
        for a in answers:
            if "error" not in a:
                seen.setdefault((a["agent"], a["arm"]), []).append((a.get("cost_usd", 0), a.get("seconds", 0)))
    return {k: (statistics.median(c for c, _ in v), statistics.median(s for _, s in v), len(v)) for k, v in seen.items()}


def forecast(agents: list[dict], answers_per_arm: int, arms: list[str], past: dict) -> dict:
    """Per agent: predicted cost and time, from the medians of earlier answers (None if never run)."""
    out = {}
    for a in agents:
        known = [past[(a["id"], arm)] for arm in arms if (a["id"], arm) in past]
        if len(known) < len(arms):
            out[a["id"]] = None
            continue
        out[a["id"]] = (sum(c for c, _, _ in known) * answers_per_arm, sum(s for _, s, _ in known) * answers_per_arm)
    return out


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


def write_experiment(agent: dict, arm: str, seconds: int, folder: Path) -> Path:
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
    root = PLUGIN_ROOT if arm == "skill" else NO_SKILL
    # An answer needs a few steps: load the skill, read a file or two, reply. MAX_STEPS stops an
    # agent that loops (one tried to build an app it had no tools to write) before it runs up a bill.
    limits = {"task_timeout": seconds, "turn_timeout": seconds, "max_turns": MAX_STEPS}
    experiment = {"experiment_id": f"ai-regression-{agent['id']}-{arm}".replace(".", "-"),
                  "description": f"{agent['harness']} + {agent['model']}",
                  "variants": [{"variant_id": arm, "run_limits": limits,
                                "agent": {**base, "plugins": [{"type": "local", "path": str(root)}]}}]}
    path = folder / f"{agent['id']}-{arm}-{seconds}s.yaml"
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
              # task starts a subagent: a way around these limits, and a way to loop on a bill.
              "tools": {t: False for t in ("bash", "write", "edit", "patch", "webfetch", "todowrite", "task")}}
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


def judged(task_json: Path, scenario: dict, judge_model: str, run: str, limit: str) -> dict:
    """One answer, judged; kept beside its task.json so a rerun of the report judges nothing twice."""
    saved = task_json.with_name("judged.json")
    task = json.loads(task_json.read_text())
    if saved.exists():
        return {"cost_usd": cost(task), **json.loads(saved.read_text())}
    reply = final_text(task)
    crit = next((c for c in task.get("success_criteria_results", []) if c.get("criterion_type") == "skill_triggered"), {})
    row = {"prompt": scenario["id"], "arm": task["variant_id"], "run": run,
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
    status = "MAX_TURNS_EXHAUSTED" if task.get("max_turns_exhausted") else task["final_status"]
    if status in TERMINATED and not refused:
        # Stopped by our limits: scored 0, not judged, and counted on its own in the report.
        row.update(terminated=f"{TERMINATED[status]} ({limit})", expect_met=0, critical_failures=[])
    elif not reply and not refused and not crashed:
        # It ran and finished without a word to the person: what they got was nothing.
        row.update(terminated="finished without an answer", expect_met=0, critical_failures=[])
    elif refused or crashed or not reply or LIMIT.search(reply[:300]):
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
                    "terminated": sum("terminated" in r for r in mine),
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
             "breaks, counted beside the index, never in it. Lift is the index with the skill minus without. Terminated answers were stopped by "
             f"a limit (time, {MAX_STEPS} steps) and score 0; without the skill, the time limit is "
             f"{LIFT_TIME:g}× the time the answer with it took, at least {MIN_SECONDS} s. Cost is at list price, "
             "so it shows what a subscription's runs would cost on an API key; local models cost nothing.", "",
             "| Agent | Arm | Index | Range | Lift | Critical failures | Terminated | Skill loaded as it should | Items met | Median time | Cost | Errors |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        rng = "–".join(map(str, s["index_range"])) if "index_range" in s else ""
        lift = f"{s['lift']:+d}" if "lift" in s else ""
        # The arm without the skill has nothing to load, so it has no load rate.
        loads = f"{s['loaded_as_it_should']}/{s['answers']}" if s["arm"] == "skill" else "–"
        lines.append(f"| {s['agent']} | {s['arm']} | {s.get('index', '')} | {rng} | {lift} | {s['critical_failures']} | {s['terminated']} | "
                     f"{loads} | {s['expect_met']}/{s['expect_total']} | "
                     f"{s['median_seconds']} s | ${s['cost_usd']:.2f} | {s['errors']} |")
    if skipped:
        lines += ["", "Not run on this machine:", ""] + [f"- {a}: {why}" for a, why in skipped]
    failures = [r for r in rows if r.get("critical_failures")]
    if failures:
        lines += ["", "## Critical failures", ""]
        lines += [f"- {r['agent']} {r['arm']}, {r['prompt']} run {r['run']}: {'; '.join(r['critical_failures'])}" for r in failures]
    ended = [r for r in rows if "terminated" in r]
    if ended:
        lines += ["", "## Terminated", ""]
        lines += [f"- {r['agent']} {r['arm']}, {r['prompt']} run {r['run']}: {r['terminated']}" for r in ended]
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
    ap.add_argument("--plan", action="store_true", help="forecast cost and time, say what would run, then stop")
    ap.add_argument("--max-spend", nargs="+", default=[], metavar="PROVIDER=USD",
                    help=f"spend at most this much on a prepaid provider (deepseek, openrouter) in this job "
                         f"(default ${DEFAULT_SPEND:.2f} each)")
    ap.add_argument("--spend-anyway", action="store_true",
                    help="run prepaid agents even when the forecast does not fit the balance")
    ap.add_argument("--history", type=Path, help="folder of earlier runs to forecast from (default: --out's parent)")
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

    # Budget: forecast each agent from its earlier answers; a prepaid provider's agents must fit
    # its balance (or --max-spend) with HEADROOM to spare, or they are skipped.
    arms = ["skill"] + ([] if args.no_lift else ["no-skill"])
    per_arm = len(scenarios) * args.runs
    past = history((args.history or args.out.resolve().parent).resolve())
    predicted = forecast(runnable, per_arm, arms, past)
    caps = {p: str(DEFAULT_SPEND) for p in PROVIDER_KEYS if p != "gemini"} | dict(c.split("=", 1) for c in args.max_spend)
    print(f"{per_arm * len(arms)} answers per agent. Forecast from earlier answers, at list price:")
    for prov in sorted({provider(a) for a in runnable}):
        group = [a for a in runnable if provider(a) == prov]
        known = [predicted[a["id"]] for a in group if predicted[a["id"]] is not None]
        cost_sum = sum(c for c, _ in known)
        left = balance(prov, keys) if prov in PROVIDER_KEYS else None
        cap = min(x for x in (left, float(caps[prov]) if prov in caps else None) if x is not None) \
            if left is not None or prov in caps else None
        for a in group:
            f = predicted[a["id"]]
            print(f"  {a['id']:16} {prov:12} " + (f"${f[0]:6.2f}  {f[1] / 60:5.0f} min" if f else "  no earlier answers to forecast from"))
        unknown = [a["id"] for a in group if predicted[a["id"]] is None]
        if prov == "gemini":
            print("  gemini: a free-tier key is billed nothing; its quota stops an agent, as a limit")
        elif prov in PROVIDER_KEYS:
            note = f"  {prov}: forecast ${cost_sum:.2f}" + (f" plus {', '.join(unknown)} (no history yet)" if unknown else "")
            note += f", balance ${left:.2f}" if left is not None else ", balance unknown"
            note += f", cap ${float(caps[prov]):.2f}" if prov in caps else ""
            print(note)
            if cap is not None and not args.spend_anyway:
                # Fit the cheapest agents first; one with no history is assumed as dear as the dearest known.
                dearest = max((c for c, _ in known), default=0)
                spend = 0.0
                for a in sorted(group, key=lambda a: predicted[a["id"]][0] if predicted[a["id"]] else dearest):
                    need = (predicted[a["id"]][0] if predicted[a["id"]] else dearest) * HEADROOM
                    if spend + need > cap:
                        skipped.append((a["id"], f"forecast ${need / HEADROOM:.2f} (${need:.2f} with headroom) does not fit "
                                                  f"the ${cap - spend:.2f} left of this job's ${cap:.2f} on {prov}; "
                                                  f"raise it with --max-spend {prov}=USD"))
                    else:
                        spend += need
        elif prov == "subscription":
            print(f"  subscription: {per_arm * len(arms) * len(group)} answers and as many judge sessions; "
                  "usage limits are not visible beforehand, so a limit stops that agent")
    runnable = [a for a in runnable if a["id"] not in dict(skipped)]
    minutes = sum(predicted[a["id"]][1] for a in runnable if predicted[a["id"]]) / 60
    print(f"  time: about {minutes / 60:.1f} h for the agents with history, one after another")

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
    rows, limited = [], []
    # The forecast can't stop an agent it has no history for, so actual spend is tallied as the
    # job runs: when a prepaid provider reaches its cap, its agents stop.
    spent: dict = {}
    over: list = []

    def answer(agent: dict, arm: str, k: int, scenario: dict, task_file: Path, seconds: int, limit: str) -> dict:
        run_dir = out / "runs" / agent["id"] / f"r{k}" / scenario["id"] / arm
        if not any(run_dir.rglob("task.json")):
            experiment = write_experiment(agent, arm, seconds, experiments)
            with open(out / f"{agent['id']}.log", "a") as log:
                subprocess.run(["coder-eval", "run", "-e", str(experiment), "--repeats", "1",
                                "--run-dir", str(run_dir), str(task_file)],
                               env=env, cwd=out, stdout=log, stderr=subprocess.STDOUT)
        found = sorted(run_dir.rglob("task.json"))
        row = ({"agent": agent["id"], **judged(found[0], scenario, args.judge_model, str(k), limit)} if found else
               {"agent": agent["id"], "prompt": scenario["id"], "arm": arm, "run": str(k), "status": "ERROR",
                "seconds": 0, "cost_usd": 0, "loaded": False, "loaded_as_it_should": False,
                "error": f"coder-eval wrote no result; see {agent['id']}.log"})
        rows.append(row)
        spent[provider(agent)] = spent.get(provider(agent), 0) + row.get("cost_usd", 0)
        print(f"  {arm:8} {scenario['id']} #{k}  {row['seconds']:>4} s  loaded={row['loaded']}  "
              + (f"TERMINATED {row['terminated']}" if "terminated" in row else
                 f"ERROR {row['error'][:80]}" if "error" in row else
                 f"expect {row['expect_met']}/{len(scenario['expect'])}  critical {len(row['critical_failures'])}"),
              flush=True)
        return row

    for agent in runnable:
        print(f"{agent['id']}: answering", flush=True)
        full = agent.get("timeout", 900)
        hit = False
        prov = provider(agent)
        cap = float(caps[prov]) if prov in caps and not args.spend_anyway else None
        for k in range(args.runs):
            for scenario, task_file in zip(scenarios, task_files):
                if cap is not None and spent.get(prov, 0) >= cap:
                    print(f"{agent['id']}: {prov} reached this job's ${cap:.2f} cap (spent ${spent[prov]:.2f})", file=sys.stderr)
                    over.append((agent["id"], f"stopped: {prov} reached this job's ${cap:.2f} spend cap; "
                                              "the answers before it are scored"))
                    hit = True
                    break
                with_skill = answer(agent, "skill", k, scenario, task_file, full, f"{full} s")
                if hit := "error" in with_skill and bool(LIMIT.search(with_skill["error"])):
                    break
                if args.no_lift:
                    continue
                if "terminated" in with_skill or "error" in with_skill:
                    seconds, limit = full, f"{full} s, as the answer with the skill did not finish"
                else:
                    seconds = max(MIN_SECONDS, round(LIFT_TIME * with_skill["seconds"]))
                    limit = f"{seconds} s: {LIFT_TIME:g}× the {with_skill['seconds']} s the answer with the skill took"
                without = answer(agent, "no-skill", k, scenario, task_file, seconds, limit)
                if hit := "error" in without and bool(LIMIT.search(without["error"])):
                    break
            if hit:
                break
        if hit and over and over[-1][0] == agent["id"]:
            continue
        if hit:
            # Another provider's agents can still run.
            print(f"{agent['id']}: stopped at a usage limit", file=sys.stderr)
            limited.append(agent["id"])

    git = lambda *a: subprocess.run(["git", "-C", str(HERE), *a], capture_output=True, text=True).stdout.strip()
    version = subprocess.run(["coder-eval", "--version"], capture_output=True, text=True).stdout.strip()
    meta = {"date": str(date.today()), "card_kit": git("rev-parse", "--short", "HEAD") or "unknown",
            "set": args.set.name, "prompts": len(scenarios), "runs": args.runs, "judge_model": args.judge_model,
            "baseline": next(a["id"] for a in agents if a.get("baseline")), "coder_eval": version,
            "memory_gb": round(mem), "machine": platform.node().split(".")[0]}
    summary = summarise(rows, scenarios, agents)
    public = [{k: v for k, v in r.items() if k not in ("answer", "verdict")} for r in rows]
    skipped += [(a, "stopped at a usage limit; the answers before it are scored") for a in limited] + over
    meta["spent_usd"] = {k: round(v, 2) for k, v in spent.items() if k in PROVIDER_KEYS}
    (out / "results.json").write_text(json.dumps({"meta": meta, "summary": summary, "skipped": skipped,
                                                  "answers": public}, indent=2) + "\n")
    (out / "report.md").write_text(report(summary, skipped, rows, meta))
    print(f"report: {out / 'report.md'}")
    return 2 if limited else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
