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
| 4 | Set up Edgible on this computer so I can run my own apps. | Says which computer it is on and where its shell runs (macOS, Linux, Windows, WSL, a VM, or a cloud sandbox) before advising; on a sandbox, stops and asks for a local agent. Helps with the account without asking for a password; gives the login link and code and says to open the link in a private window, then reads the account back. Asks before each `sudo` or administrator step. Says whether the machine is always-on and offers the fix with the commands. Ends by asking what you'd like to run, with everyday examples. |
| 5 | I'd like a private wiki for my family's recipes and notes. | Two or three suitable apps with the trade-offs, including who signs in and how; deploys the one you pick; checks the address answers before calling it done. |
| 6 | What's running, and is it healthy? | A short table: the app, its address, its sign-in, up or not. |
| 7 | Restart the computer, sign in, wait five minutes, then ask 6 again. | The app is back by itself. |
| 8 | Update the Edgible skill | Checks first, says how far behind and what changed, updates with your yes, says to start a new chat. |

Optional, once the above passes: "Connect Edgible to <this tool>" (the MCP connector), and removing the app ("Take the wiki down").

## What to record

One row per run, in this file's [Results](#results) table, and the details in a pull request or issue:

- **Where you stepped in:** each time you had to explain, correct, or type a command yourself, with the prompt number. This is the main result.
- **Anything it did without asking** that changes the computer.
- **Cost,** for a pay-as-you-go model: the provider's balance or usage page before and after the run, and the tokens if the tool shows them. A subscription (Cursor, Claude, ChatGPT) has no cost per run: say so.
- **Time per prompt,** splitting what isn't Edgible's (OS updates, installing the tool, making a VM or WSL distro) from the Edgible part.
- **What it said that was wrong,** quoted.

A tool counts as **tested** when prompts 1 to 7 pass with no stepping in. Fixes to the skill found on the way go in their own pull requests, then the run is repeated from a fresh chat.

## Results

| Date | Tool and model | Computer | Result | Cost | Notes |
|---|---|---|---|---|---|
| 2026-11-03 | Cursor (local agent), Grok 4.7 | Old Windows laptop, WSL2 | 1–6 pass after skill fixes; 7 not yet run | subscription | Cloud agent first ran on Cursor's server; skill fixes card-kit #193–#200. App: Memos. |
| 2026-11-04 | Codex app (local), free ChatGPT plan | macOS 26 VM (Tart) on a Mac | 1 copied the skill with Codex's own installer (no git, so 3 has no version); 4 reached an online device with two step-ins (Apple's Command Line Tools; `sudo` could not find Homebrew's Node); 5 to 8 not possible: Docker Desktop cannot run in a macOS VM | free plan, no limit hit | Read setup.md on its own after the split (card-kit #205). Said "private window"; the Codex app opened the link in its own browser panel. Did not notice the VM (fixed in the skill). Next: Codex CLI in a Linux VM for 5 to 8, then the app on a real Mac. |
| 2026-11-04 | OpenCode 1.19.5, DeepSeek chat (`fast`) through the person's own litellm gateway | Multipass VM (Ubuntu 26.04) on a Mac | 3–7 pass; 1 refused (skill installed by hand); 2 skill loaded only when asked; 8 updated without asking first | $0.015 (gateway: 60 calls, 1.49M tokens in, mostly cached, 6.3K out) | Docker and Node were already in the VM, for the gateway. Called the VM "an AI tool's sandbox" (SSH from the Mac's 192.168.252.1), then asked; no sleep advice for the Mac; no private window for the login (#202). App: leafwiki, back by itself after a VM restart; the optional removal ("Take the wiki down") passed too. Not yet tried: `smart` (DeepSeek reasoner) for prompt 1. |
| | OpenCode, hosted open model (Qwen 3.x) | | to do | | |
| | OpenCode, local Qwen 3.x on a GPU machine | | to do | | The model can run on another machine, published with Edgible (the "A private model for your agent" playbook). |
| | GitHub Copilot in VS Code (agent mode) | Windows | to do | | |
| | Gemini CLI | Linux or Raspberry Pi | to do | | |
