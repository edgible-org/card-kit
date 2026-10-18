#!/usr/bin/env python3
"""Judge a Coder Eval run's answers with run-evals.py's judge, on the Claude CLI subscription.

usage: judge-run.py RUN_DIR EVAL_SET.yaml [--judge-model M]
Writes judged.json in RUN_DIR and prints one line per answer.
"""
import importlib.util
import json
import sys
from pathlib import Path

RUN_EVALS = Path(__file__).resolve().parent.parent / "run-evals.py"
spec = importlib.util.spec_from_file_location("run_evals", RUN_EVALS)
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def final_text(task: dict) -> str:
    turns = task.get("iterations") or task.get("turns") or []
    for turn in reversed(turns):
        text = (turn.get("result_summary") or {}).get("result") or turn.get("agent_output") or ""
        if text.strip():
            return text
    return ""


def triggered(task: dict) -> bool | None:
    for c in task.get("success_criteria_results", []):
        if c.get("criterion_type", c.get("type")) == "skill_triggered":
            return c.get("score") == 1.0
    return None


def main(argv: list[str]) -> int:
    run_dir, eval_set = Path(argv[1]), Path(argv[2])
    model = argv[argv.index("--judge-model") + 1] if "--judge-model" in argv else ""
    scenarios = {s["id"]: s for s in ev.load_scenarios(eval_set)}
    rows = []
    for path in sorted(run_dir.rglob("task.json")):
        task = json.loads(path.read_text())
        variant = path.relative_to(run_dir).parts[0]
        scenario = scenarios[task["task_id"]]
        reply = final_text(task)
        verdict = ev.judge(scenario, reply, timeout=600, model=model) if reply else {"error": "no answer"}
        expect = verdict.get("expect", [])
        broken = [m["item"] for m in verdict.get("must_not", []) if m.get("violated") is True]
        row = {"variant": variant, "task": task["task_id"], "replicate": path.parent.name,
               "skill_triggered": triggered(task), "expect_passed": sum(e.get("pass") is True for e in expect),
               "expect_total": len(scenario["expect"]), "critical_failures": broken,
               "answer": reply, "verdict": verdict}
        rows.append(row)
        print(f"{variant:14} {task['task_id']} #{row['replicate']}  skill={row['skill_triggered']}  "
              f"expect {row['expect_passed']}/{row['expect_total']}  critical {len(broken)}"
              + (f"  ERROR {verdict['error']}" if "error" in verdict else ""), flush=True)
    (run_dir / "judged.json").write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
