#!/usr/bin/env python3
"""Score needs-sweep prompts using a local Ollama model as the answering harness.

    python3 run-needs-sweep-ollama.py \\
      --model qwen3.5:9b \\
      --out ~/edgible-needs-sweep/results/try \\
      --only bookmarks-and-link-sharing

Does not modify run-evals.py or the Cursor harness. Injects SKILL.md + needs-map.yaml
into the system prompt (no Cursor Agent / no Cursor quota). Judge defaults to Cursor
Composer so scoring stays comparable without burning Other Models.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = Path(os.environ.get("EDGIBLE_NEEDS_SWEEP_DIR", Path.home() / "edgible-needs-sweep"))
CURSOR_SKILL = Path.home() / ".cursor" / "skills" / "edgible-cards"
CARD_KIT_SKILL = HERE.parent
DEFAULT_BASE = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


ev = load_module("run_evals", HERE / "run-evals.py")
cursor = load_module("run_needs_sweep_cursor", HERE / "run-needs-sweep-cursor.py")


def skill_root() -> Path:
    for p in (CURSOR_SKILL, CARD_KIT_SKILL):
        if (p / "SKILL.md").is_file() and (p / "needs-map.yaml").is_file():
            return p.resolve()
    sys.exit(
        f"edgible-cards skill not found at {CURSOR_SKILL} or {CARD_KIT_SKILL} "
        "(need SKILL.md + needs-map.yaml)."
    )


def build_system_prompt(root: Path) -> str:
    skill = (root / "SKILL.md").read_text()
    needs = (root / "needs-map.yaml").read_text()
    return f"""You are an AI assistant helping a person choose self-hosted apps.
You have the Edgible cards skill and needs map below. Follow them.
Prefer cards from the needs map; give cards.edgible.org links; ask before deploying.
Do not invent card URLs that are not in the map. Keep the answer practical and concise.

<skill path="SKILL.md">
{skill}
</skill>

<needs_map path="needs-map.yaml">
{needs}
</needs_map>
"""


def ollama_chat(
    *,
    base: str,
    model: str,
    system: str,
    user: str,
    timeout: int,
    temperature: float,
) -> dict:
    url = f"{base}/v1/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        return {"error": f"ollama HTTP {e.code}: {err[:500]}", "raw": err, "events": []}
    except Exception as e:  # noqa: BLE001 — surface any transport failure
        return {"error": f"ollama request failed: {e}", "raw": "", "events": []}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "ollama returned non-JSON", "raw": raw, "events": []}

    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {"error": "ollama response missing choices[0].message.content", "raw": raw, "events": []}

    # Skill was injected into the system prompt — treat as loaded for score().
    event = {
        "type": "result",
        "subtype": "success",
        "harness": "ollama",
        "model": model,
        "usage": data.get("usage") or {},
        "result": answer,
    }
    return {
        "answer": (answer or "").strip(),
        "tools": [],
        "skill_loaded_at": 0,
        "events": [
            {"type": "system", "subtype": "init", "model": model, "base": base},
            {"type": "user", "message": {"role": "user", "content": user}},
            event,
        ],
        "raw": raw,
        "usage": data.get("usage") or {},
    }


def list_ollama_models(base: str, timeout: int = 10) -> list[str]:
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:  # noqa: BLE001
        return []


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--rewrite-report", action="store_true")
    ap.add_argument("--set", type=Path, default=HERE / "needs-sweep.yaml")
    ap.add_argument("--only", nargs="+", default=[], metavar="ID")
    ap.add_argument("--model", default="qwen3.5:9b", help="Ollama model tag (ollama list)")
    ap.add_argument("--base-url", default=DEFAULT_BASE, help="Ollama base URL (default OLLAMA_HOST or localhost)")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--judge-model", default="composer-2.5",
                    help="judge model (Cursor id when --judge-harness cursor)")
    ap.add_argument("--judge-harness", choices=("claude", "cursor", "none"), default="cursor",
                    help="who judges; 'none' writes answers only (no score). Default cursor/Composer.")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--list-models", action="store_true", help="print Ollama tags and exit")
    args = ap.parse_args(argv)

    if args.list_models:
        models = list_ollama_models(args.base_url)
        if not models:
            sys.exit(f"no models (is Ollama up at {args.base_url}?)")
        print("\n".join(models))
        return 0

    if args.rewrite_report:
        return cursor.rewrite_report(args.out)

    card_kit = HERE.parents[2]
    try:
        args.out.resolve().relative_to(card_kit.resolve())
        print(f"warning: --out is inside card-kit ({card_kit}); prefer ~/edgible-needs-sweep/…", file=sys.stderr)
    except ValueError:
        pass

    scenarios = [s for s in ev.load_scenarios(args.set) if not args.only or s["id"] in args.only]
    if not scenarios:
        sys.exit("no prompts to run")

    root = skill_root()
    system = build_system_prompt(root)
    available = list_ollama_models(args.base_url)
    if available and args.model not in available:
        print(
            f"warning: model {args.model!r} not in ollama list ({', '.join(available)}); trying anyway",
            file=sys.stderr,
        )

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "system-prompt.md").write_text(system)

    git = lambda *a: subprocess.run(
        ["git", "-C", str(CARD_KIT_SKILL), *a], capture_output=True, text=True
    ).stdout.strip()
    meta = {
        "date": str(date.today()),
        "harness": "ollama",
        "model": args.model,
        "base_url": args.base_url,
        "card_kit": git("rev-parse", "--short", "HEAD") or "unknown",
        "claude": f"ollama {args.model} @ {args.base_url}",
        "agent": f"ollama/{args.model}",
        "mcp": "none (prompt-injected skill)",
        "judge_harness": args.judge_harness,
        "judge_model": args.judge_model if args.judge_harness != "none" else "none",
        "set": str(args.set),
        "skill_injection": "SKILL.md+needs-map.yaml in system prompt",
    }

    results, stopped = [], ""
    for s in scenarios:
        print(f"{s['id']}: answering (ollama/{args.model})", flush=True)
        run = ollama_chat(
            base=args.base_url,
            model=args.model,
            system=system,
            user=s["prompt"],
            timeout=args.timeout,
            temperature=args.temperature,
        )
        (args.out / f"{s['id']}.transcript.jsonl").write_text(
            "\n".join(json.dumps(e) for e in run.get("events", [])) + "\n"
        )
        (args.out / f"{s['id']}.raw.txt").write_text(run.get("raw", "") + "\n")
        if "error" in run:
            stopped = f"{s['id']}: {run['error']}"
            print(f"stopped, not scored: {stopped}", flush=True)
            break
        (args.out / f"{s['id']}.answer.md").write_text(run["answer"] + "\n")

        if args.judge_harness == "none":
            verdict = {
                "expect": [{"item": e, "pass": True, "evidence": "judge skipped"} for e in s["expect"]],
                "must_not": [{"item": m, "violated": False, "evidence": "judge skipped"} for m in s["must_not"]],
                "principles": [{"item": p, "pass": None, "evidence": "judge skipped"} for p in ev.PRINCIPLES],
                "better": "judge skipped (--judge-harness none)",
            }
            # Force fail visually? Better: mark unscored — still run score for loaded check
            r = ev.score(s, run, verdict)
            r["pass"] = False  # unscored batch should not look like a green sweep
            r["verdict"]["better"] = "judge skipped (--judge-harness none)"
            results.append(r)
            print(f"{s['id']}: answered (judge skipped)", flush=True)
            continue

        print(f"{s['id']}: judging ({args.judge_harness})", flush=True)
        if args.judge_harness == "claude":
            verdict = ev.judge(s, run["answer"], args.timeout, args.judge_model)
            if "error" in verdict and ev.LIMIT.search(
                json.loads(verdict["raw"]).get("result", "")
                if verdict.get("raw", "").strip().startswith("{")
                else verdict.get("raw", "")
            ):
                stopped = f"{s['id']}: Claude judge usage limit"
                print(f"stopped, not scored: {stopped}", flush=True)
                break
        else:
            verdict = cursor.judge_cursor(s, run["answer"], args.judge_model, args.timeout)
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
    report_text = cursor.needs_sweep_report(results, meta).replace(
        "needs sweep (Cursor)", "needs sweep (Ollama)"
    )
    (args.out / "report.md").write_text(home(report_text))
    print(f"\n{sum(r['pass'] for r in results)}/{len(results)} pass. Report: {args.out / 'report.md'}")
    if stopped:
        print(f"Not run: {', '.join(meta['not_run'])}")
        return 2
    if args.judge_harness == "none":
        return 0
    return 0 if results and all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
