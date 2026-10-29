# Evals for the edgible-cards skill

The prompts the skill is measured against, and how to measure it. [EXAMPLES.md](../EXAMPLES.md) shows the same prompts to people, with what a good answer does.

| File | What it is |
|---|---|
| [trigger-set.json](trigger-set.json) | 34 prompts, each marked `should_trigger`: 22 that should load the skill (needs described in people's words, a named app, a day-two problem, upgrading Edgible itself, sharing an app you built, AI tools, an agent asked to add an app) and 12 near-misses on the same topics that should not. Reviewed by a person. |
| [held-out.yaml](held-out.yaml) | 20 prompts, mostly real, four of them from builders who made an app and want it on Edgible or in the catalog, with what a good answer does (`expect`) and what fails it (`must_not`). Answers are scored against them, and the skill is never tuned to them. |
| [run-evals.py](run-evals.py) | Answers each held-out prompt in a fresh read-only session with the skill, has a second session judge the answer against its `expect`, `must_not`, and the skill's principles, and writes a report. |
| [eval-summary.py](eval-summary.py) | Combines the last week of nightly runs into one report, from each prompt's latest result. |
| [trigger-probe.py](trigger-probe.py) | Runs each trigger prompt in fresh, read-only `claude -p` sessions with the skill installed, and reports whether and at which step it loaded. |
| [ai-regression.py](ai-regression.py) and [agents.yaml](agents.yaml) | Run the held-out prompts on several agents (harness and model), with and without the skill, and index each against the baseline. |

## Measure triggering

With the skill installed (see the card-kit README's Agent skill section) and `claude` logged in:

```bash
python3 skills/edgible-cards/evals/trigger-probe.py            # every prompt, 2 runs each
python3 skills/edgible-cards/evals/trigger-probe.py --only 3 7 # just those prompts
```

Sessions get no shell, edits, or web access, so nothing is deployed. Each run is one short session on the logged-in subscription.

Use this, not skill-creator's `run_eval.py`. That tool installs the description under test as a temporary command file and counts a run only if loading it is the session's very first action. On 2026-10-11 it scored 1 of 12 should-trigger prompts, while the real skill loaded first in every probe run (8 of 8). Optimising the description against it would fix a problem real sessions do not have.

## Score answers

```bash
python3 skills/edgible-cards/evals/run-evals.py --out results/$(date +%F)
python3 skills/edgible-cards/evals/run-evals.py --out results/try --only tennis-club
```

Each prompt gets two sessions on the logged-in subscription: one answers, one judges. The answering session is read-only: it may read the skill's folder, and, when an Edgible MCP server is on the machine (`edgible-mcp`, or `--mcp <command>`), use its `find` and `describe` tools to look up cards, as a person's session would. It has no shell, edits, web, or any other MCP server. The judge has no tools.

A prompt passes when the skill loaded as it should, every `expect` item holds, and no `must_not` item happened. `report.md` gives each result, the items missed with the judge's evidence, and one line per answer on what would have made it better. Transcripts and answers are saved beside it.

**Nightly, in small batches.** `--rotate today` runs only today's share of the prompts: prompt *i* runs on weekday *i* mod 7, so each runs once a week and a night costs about N/7 prompts, two sessions each. `eval-summary.py results/` then combines the last seven nights, each prompt at its latest result. edgible-org/cards runs this every night ([skill-evals.yml](https://github.com/edgible-org/cards/blob/main/.github/workflows/skill-evals.yml)) and keeps the report in a public issue. `results.json` and `report.md` have no home folder in them, so they can be published; transcripts stay on the machine.

If the subscription's usage limit is reached, the run stops, reports the prompts it did not run, and exits 2. Nothing is scored from a limit message.

A session must be able to read the skill's folder by both of its paths (the skills symlink and where it points), or it answers without the needs map: `run-evals.py` passes both with `--add-dir`. Headless sessions refuse anything not allowed.

## Compare agents

`ai-regression.py` measures the skill on the agents in [agents.yaml](agents.yaml), not only Claude: Claude Code, Codex, Gemini, and open models, both local and hosted. [Coder Eval](https://coder-eval.com) runs the answers (`uv tool install "coder-eval[codex,antigravity]"`). Each prompt is answered with the skill, then without it, and `run-evals.py`'s judge scores every answer.

```bash
python3 skills/edgible-cards/evals/ai-regression.py --out results/try --plan                  # forecast cost and time, say what would run and why the rest won't
python3 skills/edgible-cards/evals/ai-regression.py --out results/agents-$(date +%F) --rotate today   # tonight's share of the prompts, 3 runs
python3 skills/edgible-cards/evals/ai-regression.py --out results/try --agents glm --only pocket-shutdown --runs 1
```

The report gives each agent's results against the baseline (the agent marked `baseline: true`) on the same prompts:

- **Index:** the expect items its answers met, as a percentage of what the baseline met, with the range over runs.
- **Lift:** the index with the skill minus the index without it.
- **Critical failures:** `must_not` breaks, counted beside the index, never in it.
- **Terminated:** answers stopped by a limit, or that ended without a word to the person. They score 0, since the person got nothing.
- **Too expensive:** answers that cost more than $0.25 at list price. A person wouldn't pay that for one reply.
- **Skill cost ×:** the cost of an answer with the skill, over one without it.
- **Skill loads:** how often the skill loaded as it should.
- **Time and cost** per answer.

`results.json` holds the same results without the answers. Each answer and its verdict are kept beside its run, so a rerun only judges answers that have no verdict yet. A usage or rate limit is never scored, and it stops only the agent that hit it.

### Limits

These are the same for every agent, so a slow or looping agent can't hide behind a generous timeout:

- **30 steps** per answer.
- **Time without the skill:** the answer without the skill gets 3× the time the answer with it took, and at least 120 s.
- **The answer with the skill** gets the agent's own `timeout`.

### Budgets

Answers on a prepaid key (DeepSeek, OpenRouter) cost money, so before it runs anything, the script forecasts each agent's cost and time from its earlier answers. It also checks the provider's live balance.

- **Per job:** each job spends at most $0.50 per prepaid provider. `--max-spend deepseek=2` raises one provider's cap.
- **Skipping:** an agent whose forecast, with half again to spare, doesn't fit is skipped, with the numbers.
- **During the run:** a running tally stops a provider's agents when its spend reaches the cap, which covers agents with no history to forecast from.

The Gemini free tier, the Claude subscription and a ChatGPT account have no balance to ask. Their limits stop an agent instead.

### Machines

Each entry in `agents.yaml` says what the agent needs:

- **`memory_gb`:** the machine's memory.
- **An `ollama/` model** pulled into Ollama on 127.0.0.1:11434.
- **For a hosted model, its key:** `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY` or `GEMINI_API_KEY`, in the environment or in `~/.config/ai-regression.env` (`NAME=value` lines, mode 600, never in a repo).

A machine without these skips the agent and says why. So adding a bigger device to the fleet adds its agents to the report, with no change here.

### What each harness needs

The answering sessions are read-only: they can't run commands, edit files or fetch from the web.

- **Claude Code:** the `claude` CLI, signed in. It runs with only Skill, Read, Glob and Grep, and none of the machine's own settings or skills.
- **Codex:** the `codex` CLI, signed in (`codex login`; a free ChatGPT account works), in its read-only sandbox. Name a model it allows, or Coder Eval fills in a Claude model, which ChatGPT refuses.
- **Gemini:** through Coder Eval's Antigravity harness, which enforces the tool lists. A free-tier key runs Flash but not Pro.
- **OpenCode:** npm's `opencode-ai` 1.19.x. Coder Eval passes `--dir` and `--pure`, which Homebrew's `opencode` 2.x no longer has. Coder Eval can't limit OpenCode's tools, so the script's OpenCode config turns off its shell, edit, fetch and subagent tools. It also turns off OpenCode's own loading of `~/.claude/skills`, so the arm without the skill really is without it.

## Rules

- A person reviews any change to these prompts, as a pull request: they are what the scores mean.
- Never tune the skill against `held-out.yaml`. A fix must help a pattern seen in generated prompts, and the held-out scores show whether it helped or hurt.
- Write prompts in everyday language, the way people ask. Real ones may be tidied for spelling and punctuation, keeping their wording. Leave out real names, domains, and anything private.
