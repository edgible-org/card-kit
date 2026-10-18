# Agent spike (Coder Eval)

A spike, not yet wired into CI: run an eval prompt on several agents with and without the skill using [Coder Eval](https://coder-eval.com) (`uv tool install coder-eval`). Then judge the answers with `run-evals.py`'s judge on the Claude CLI subscription.

What the agents need:

- Claude Code is logged in (`claude login`).
- OpenCode is npm's `opencode-ai` 1.19.x. Coder Eval 0.12.14 passes `--dir` and `--pure`, which Homebrew's `opencode` 2.x no longer has.
- Ollama answers on 127.0.0.1:11434 with `gpt-oss:20b`.

```bash
export CARD_KIT=~/.card-kit EMPTY_PLUGIN=$PWD/empty-plugin TELEMETRY_ENABLED=false
# OpenCode would otherwise load ~/.claude/skills in the bare arm too
export OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1 OPENCODE_DISABLE_EXTERNAL_SKILLS=1
# Ollama provider; shell, write and fetch tools switched off
export OPENCODE_CONFIG_CONTENT="$(cat opencode-config.json)"
coder-eval run -e experiments/spike.yaml tasks/pocket-shutdown.yaml
python3 judge-run.py runs/latest ../held-out.yaml --judge-model claude-opus-5-5
```

Coder Eval can't apply `allowed_tools` to OpenCode. `opencode-config.json` is what keeps it to read-only tools.
