# End-to-end test: an AI tool sets up Edgible

The other evals score answers in read-only sessions. This one is done by a person, on a real computer: an AI tool with the skill goes from nothing to a working app, and the tester notes every place it needed help. Run it for each AI tool (and model) before the site calls that tool tested.

## Before you start

- **A computer with nothing on it:** no Edgible, no skill, ideally a fresh OS install or a fresh user. Note the OS, edition and version.
- **The AI tool, running on that computer.** Check it is a local agent, not a cloud one: Cursor's cloud agents, Codex cloud, and Claude Code on the web run on a server, and anything they install is thrown away. Note the tool, its version, and the model.
- **An Edgible account the tester can sign in to.** If the browser is signed in to another Edgible account, approve the login link in a private window.
- **A notebook** for the record below. Time each step.

## The prompts, in order

Each in a **new chat**, typed as written. Don't add hints such as "this is Windows" or "use the Edgible skill": if the tool needs one, that is a finding.

| # | Say | A pass |
|---|---|---|
| 1 | Install the Edgible skill from github.com/edgible-org/card-kit | Installs on this computer, asking before anything it installs (such as git); links the skill into the folder this tool reads; says to start a new chat. |
| 2 | What can you do with Edgible cards? | Answers from the skill, so the tool found it. |
| 3 | Which version of the Edgible skill do I have? | A date and a short commit hash. |
| 4 | Set up Edgible on this computer so I can run my own apps. | Says which computer it is on and where its shell runs (macOS, Linux, Windows, WSL, a VM, or a cloud sandbox) before advising; on a sandbox, stops and asks for a local agent. Helps with the account without asking for a password; gives the login link and code, then reads the account back. Asks before each `sudo` or administrator step. Says whether the machine is always-on and offers the fix with the commands. Ends by asking what you'd like to run, with everyday examples. |
| 5 | I'd like a private wiki for my family's recipes and notes. | Two or three suitable apps with the trade-offs, including who signs in and how; deploys the one you pick; checks the address answers before calling it done. |
| 6 | What's running, and is it healthy? | A short table: the app, its address, its sign-in, up or not. |
| 7 | Restart the computer, sign in, wait five minutes, then ask 6 again. | The app is back by itself. |
| 8 | Update the Edgible skill | Checks first, says how far behind and what changed, updates with your yes, says to start a new chat. |

Optional, once the above passes: "Connect Edgible to <this tool>" (the MCP connector), and removing the app ("Take the wiki down").

## What to record

One row per run, in this file's [Results](#results) table, and the details in a pull request or issue:

- **Where you stepped in:** each time you had to explain, correct, or type a command yourself, with the prompt number. This is the main result.
- **Anything it did without asking** that changes the computer.
- **Time per prompt,** splitting what isn't Edgible's (OS updates, installing the tool, making a VM or WSL distro) from the Edgible part.
- **What it said that was wrong,** quoted.

A tool counts as **tested** when prompts 1 to 7 pass with no stepping in. Fixes to the skill found on the way go in their own pull requests, then the run is repeated from a fresh chat.

## Results

| Date | Tool and model | Computer | Result | Notes |
|---|---|---|---|---|
| 2026-11-03 | Cursor (local agent), Grok 4.7 | Old Windows laptop, WSL2 | 1–6 pass after skill fixes; 7 not yet run | Cloud agent first ran on Cursor's server; skill fixes card-kit #193–#200. App: Memos. |
| | Codex | Mac | to do | |
| | OpenCode, hosted open model (DeepSeek or Qwen 3.x) | | to do | |
| | OpenCode, local Qwen 3.x on a GPU machine | | to do | The model can run on another machine, published with Edgible (the "A private model for your agent" playbook). |
| | GitHub Copilot in VS Code (agent mode) | Windows | to do | |
| | Gemini CLI | Linux or Raspberry Pi | to do | |
