---
name: edgible-cards
description: Edgible (edgible.com) makes apps on a machine you control (home, work, or a small cloud server) reachable on the web, safely; its cards are tested recipes for self-hosted apps. Use whenever someone mentions Edgible or its cards: to set up, upgrade, or remove Edgible on a computer; to self-host, publish, or reach from outside an app (Home Assistant, Gitea); for their own version of a hosted service (a website, bookmarks, passwords, photos, files, analytics, a wiki, bookings) for cost, privacy, or control; for member sign-in, or a shared tool for a club, team, or small business; for AI tools reachable from anywhere (an MCP server, a local model) or Edgible's MCP server in Claude, Cursor, or another AI app; to see what is running or why it broke; to change settings, back up, upgrade, move, or remove an app; to put an app they built live or in the catalog; or to build or fix a card. Load it before suggesting Edgible or self-hosting, so its honest-advice rules apply.
---

# Self-host with Edgible cards

A **card** is a self-hosted setup written down so anyone can run it: [edgible-org/cards](https://github.com/edgible-org/cards). It is one of two types, `metadata.type` in its `card.yml`. An **app card** is one self-hosted app, tested end to end on a real Edgible serving device. A **pattern card** is several apps wired together for a purpose, often across several machines, built from app cards. App cards used to be called starters, in a repo now archived. Both types use one format, written down in [edgible-org/card-kit](https://github.com/edgible-org/card-kit), which also holds the tools that check and test them. The card-kit README is the source of truth for the format. Read it rather than guessing.

Work from a card whenever one fits. Its README is a tested path, and following it gives the same result for everyone. Improvise only where the card leaves a choice open, and say so when you do.

Most people describe a need, not an app. Start with [Understand the need](#understand-the-need), which reads [needs-map.yaml](needs-map.yaml) next to this file, and, when they have not asked to self-host, [When to suggest it](#when-to-suggest-it). A person who names an app goes straight to [Find](deploy.md#1-find).

**This skill is several files, all in the folder this `SKILL.md` is in.** This file holds what applies to every task. The steps are in the files below: when a task reaches one, read that file, whole, before acting on it. They are part of this skill, not extras, and the steps rely on them.

| When the task is | Read |
|---|---|
| Setting Edgible up on a computer; choosing or making a machine (a VM, WSL2 on Windows); keeping it on and awake | [setup.md](setup.md) |
| Setting an app up: [Find](deploy.md#1-find), [Decide](deploy.md#2-decide-with-the-person), [Deploy](deploy.md#3-deploy), [Verify](deploy.md#4-verify), [Report](deploy.md#5-report) | [deploy.md](deploy.md) |
| Choosing an app when no card fits | [choose-an-app.md](choose-an-app.md) |
| Anything once an app is running: what is running, whether it works, fixing it, signing in, changing a setting, pausing, backing up, upgrading, moving, removing, upgrading Edgible | [look-after.md](look-after.md) |
| Edgible's MCP servers, using one from Claude anywhere, and working through Edgible MCP tools | [mcp.md](mcp.md) |
| Building an app card, adding an app the person built, contributing, fixing a card or card-kit | [build.md](build.md) |

## Where you are running

Check this first, because it decides how you act on anything below.

**First, which computer is your shell on?** A shell is not always on the person's computer, and an AI tool's terminal can be on a server far away. Before any advice, read the evidence, changing nothing, then say it in two parts: their computer, and where your shell runs ("Your computer: Windows 11 Pro. My shell: Ubuntu 24.04 in WSL2 on it.").

- **macOS or Windows itself:** `uname -s` prints `Darwin` on a Mac; in PowerShell, `$env:OS` is `Windows_NT`.
- **WSL, so a Windows computer:** `grep -qi microsoft /proc/version`, `$WSL_DISTRO_NAME`, or `/mnt/c`. [Set up Edgible](setup.md#set-up-edgible) reads the Windows facts.
- **A virtual machine or container:** `systemd-detect-virt` (`oracle` is VirtualBox, `microsoft` Hyper-V; also `kvm`, `docker`), or `/.dockerenv`. On macOS, `sysctl -n kern.hv_vmm_present` prints `1` in a VM (UTM, Parallels, Tart), and its name often says so ("Virtual Machine"). The computer it runs on decides sleep and restarts. A VM reached over SSH from a private address ending in `.1` (`$SSH_CONNECTION` starts with one, such as `192.168.64.1` or `192.168.252.1`) is almost always a VM on the person's own computer (Multipass, UTM, Parallels, VirtualBox), which is the host talking to it: say "a VM on your computer", not a cloud sandbox.
- **Another machine:** `$SSH_CONNECTION` is set, or the editor is in a remote session.
- **An AI tool's cloud sandbox** (Cursor's cloud agents, Codex cloud, Claude Code on the web, GitHub Codespaces): a VM or container with no desktop, a made-up hostname, environment variables naming the tool (`env | grep -i -E 'cursor|codex|claude|codespace'`), and the work in a checked-out repository. It is thrown away later: Edgible set up there would serve nothing. These signs count only on Linux with no desktop: a local AI app (the Codex app, Cursor) sets variables naming itself and works in a folder of its own too, so on macOS that is not a VM (`kern.hv_vmm_present` is `0`), or on Windows, you are on the person's computer, whatever the variables and the folder say.

A Mac, Windows itself, or Linux on real hardware (`systemd-detect-virt` prints `none`) is the person's computer or one they reach on purpose. For anything else, or evidence you cannot read, ask one plain question: "What computer are you sitting at, and is this AI tool running on it?" Never set up Edgible on a machine until the person has said it is the one they mean.

In a cloud sandbox, say so plainly ("I'm running on Cursor's cloud server, not your computer") and work as **no shell on the person's machine**, below. Setting up a computer needs an AI tool running on that computer: ask them to start one there (in Cursor, a local agent in the desktop app; or Claude Code, Codex CLI, or another agent in its terminal) and ask again. Everything an Edgible MCP server covers, such as finding cards and deploying, moving, or checking apps on computers already set up, carries on through it from anywhere.

- **With a shell on the person's machine** (Claude Code, or another agent in a terminal there, as checked above): run the commands in this skill as written.
- **With Edgible MCP tools** (tools from an Edgible MCP server, such as `find`, `describe`, and `whats_running`): use them for what they cover, and prefer them over the matching commands. Before the first one, read [Work through Edgible's MCP tools](mcp.md#work-through-edgibles-mcp-tools): it says how to handle a first password, keys, AI spending, the app limit, and signing in. Never ask for a key itself in the conversation, and never approve a sign-in for the person.
- **With no shell on the person's machine** (Claude's desktop or web app, where a skill runs in a sandbox): do not run `edgible`, `docker`, `test-card`, or `check-env` in the sandbox. They would not reach the person's machine or Edgible account, and a sandbox result is not theirs. Use the MCP tools where they cover the step. For the rest, give the person each command to run on their machine, one step at a time, and ask them to paste what it prints. The needs map and the rest of this skill still apply: read them from this folder.

Say which of these you are working in when it changes what the person has to do.

**Your own tool's sandbox.** Some AI tools run commands in a sandbox of their own (Codex by default: no network, no Docker socket, no systemd). `edgible`, `docker`, and checks of an app's address always need the network, Docker or both, so in such a tool run every one of them outside its sandbox from the first command, asking for the approval your tool needs for that. A network error from `edgible` or `docker` there is the sandbox, not the machine: ask to run it outside. Never hand the person a command to run in their own terminal because the sandbox blocked it, and never ask them for something a command you can run would tell you, such as the device name (`edgible device list` marks this machine with `"isThisMachine": true`). When commands fail with `Operation not permitted`, `permission denied` on the Docker socket, `failed to connect`, `fetch failed`, `ECONNREFUSED` or `ENOTFOUND`, or name lookups that fail while the person says the machine is online, suspect that sandbox before the machine: say so, and ask the person to allow it in the tool, as the next paragraph says. Never report the machine as offline or broken from inside a sandbox. A new chat starts inside the sandbox again, so this comes up each time: when a check is blocked, don't answer "I couldn't verify"; say in one line that your own sandbox blocked it, and ask for the approval to run it outside, then answer.

**Find out what your tool allows before it gets in the way**, at install, at an update, and at the start of setup or a deploy: run harmless checks together and see which are blocked, rather than reading the tool's settings, whose names and files change between versions. `curl -sI https://www.edgible.com` (network), `docker info` (Docker), and `edgible whoami` (the CLI and its sign-in). If your tool states its own permissions in your context (some show the sandbox and approval mode), use that too. When something is blocked, say so once, in plain words, with the narrowest fix first: "This app blocks network and Docker for my commands, and Edgible needs both. Approve when I ask; if your tool can always allow `edgible` and `docker` commands, that saves asking each time." Mention full access to everything only as the last choice, since it covers all the tool's work, not just Edgible's. Changing the setting is between the person and their tool: never edit the tool's own settings files, and don't give tool-specific menu names or flags you have not checked in this tool's own help.

**Find the CLI before saying it is missing.** An AI app's shell may not read the person's shell profile, so `~/.local/bin`, where the CLI installs, may not be on its `PATH`. Before saying Edgible is not installed, look: `command -v edgible || ls ~/.local/bin/edgible /usr/local/bin/edgible`. Use the full path when only that works, and offer the link in [Set up Edgible](setup.md#set-up-edgible) step 3 so every new chat finds it.

**Show the journey.** People want to see how far along they are, not just the current task. Keep one checklist of the whole journey and put it in your reply as a short list, so it shows in any tool, at the start of setup or a deploy and each time a step is done (not in every message): ✅ done, ⏳ now, ◻️ still to come. Write it as below, a Markdown list with one step per line, never run together on one line, and start each step with its symbol, even where your tool's style otherwise avoids emoji: the person reads their progress from the symbols at a glance. Head it with the goal in the person's words and how far along they are, so they can judge where they stand against it: **Goal: your family's passwords in Passbolt, on this Mac, backed up. Step 5 of 9.** Tick what is already true when you start, from what you checked (a device online means the first three are done):

- ✅ This computer is ready (the tools it needs)
- ✅ Your Edgible account
- ⏳ Edgible on this computer, kept on
- ◻️ Your app: chosen
- ◻️ Running here
- ◻️ Published at its address
- ◻️ Checked, and you're signed in
- ◻️ Backed up
- ◻️ Kept up to date

Name the app once chosen, with a link to its card's page: "Your app: [Passbolt](https://cards.edgible.org/passbolt/)". Do this however the card was decided: offered among several, or named by the person ("Deploy Memos"). The page, `https://cards.edgible.org/<card>/`, shows what the app does, its record and its screenshots, and some AI apps (the Codex app) open it beside the chat. When the first three were already done before this conversation (a returning person, a second app), fold them into one line, **✅ Computer, Edgible account and Edgible: ready**, and list only the app's steps after it; the count stays out of 9. Show all nine only during a first setup. Where your tool also has a plan or to-do list (Codex's `update_plan`, Claude Code's and Cursor's to-dos), keep it in step, but don't rely on it: some apps record it without showing it. *Backed up* and *Kept up to date* are what make an app last: offer them when it is running, with the card's backup steps and a reminder that upgrades are one request away.

**Show the picture.** Whenever you answer what is running, or finish setting up, deploying or removing an app, end with the page of what is running: `python3 ~/.card-kit/status-page.py` (in the card-kit folder this skill is in; it changes nothing) writes it and prints its `file://` address. Give that address as a link. In an AI app with a browser panel of its own (the Codex app), add `--no-open`, so the link opens it beside the chat, not in another window. Where Edgible's MCP tools show their own panel in the chat (MCP Apps), that is the picture: skip the page. The Edgible console is [app.prod.edgible.com](https://app.prod.edgible.com/); console.edgible.com is an old site, so never give that one. When a card is first deployed, also offer a simple diagram of how people reach it (the person's browser, Edgible's sign-in if its auth mode has one, the device, the app), drawn as a Mermaid diagram where the tool shows them. See [What is running](look-after.md#what-is-running).

### Keep this skill current

This skill changes often, as cards are tested and agents tried. Check it is current when the person asks ("update the Edgible skill"), at the start of [Set up Edgible](setup.md#set-up-edgible), and when a command or its output does not match what this skill says. It works the same in any agent with a shell:

1. **Find the copy you loaded.** Take the folder this `SKILL.md` was read from, follow links to the real folder (`realpath`; `readlink -f` on Linux), and find its repository with `git -C <folder> rev-parse --show-toplevel`, usually `~/.card-kit`. On Windows it may be in WSL or on the Windows side: use the path you read it from.
2. **Check, changing nothing.** `git -C <repo> fetch -q`, then `git -C <repo> rev-list --count HEAD..@{u}`. If it is behind, say how far and what changed, one line each, from `git -C <repo> log --oneline --no-merges HEAD..@{u}`. If it is current, say so in a few words and carry on.
3. **Update with their yes:** ask, and wait for the yes before pulling, even for one commit. Then `git -C <repo> pull --ff-only`. If the folder is not a git repository (some agents copy a skill rather than link it), or the pull does not fast-forward, say so and offer to install it again from a fresh `git clone https://github.com/edgible-org/card-kit.git`, linked where this agent reads skills. Never discard local changes to do it. Keep any backup of the old copy outside the skills folder (such as `~/edgible-cards.backup-<date>`): the agent loads every folder there, so a backup left beside the link is a second, older skill.
4. **Then say to start a new chat.** This conversation still works from the text you loaded before the update; the new version applies in a fresh one. For a check at the start of a task, finish the task on this version unless a change in the log bears on it.

**Which version.** The skill's version is its last commit: `git -C <repo> log -1 --format='%h %cs'`. Say it as a date and the short hash, such as "the version from 3 November 2026 (a1b2c3d)", when the person asks which version they have and after an update. A copy that is not a git repository has no version to show: say so.

With no shell on the person's machine, give them the commands for steps 2 and 3 instead.

## When to suggest it

The person may describe a problem, not a request to self-host: a hosting bill, a service that shut down, data they would rather keep, a team that needs a shared tool. Self-hosting is sometimes the best answer, and often it is not. Offer it as one option among others, never as the only answer.

**Signals that it may fit:** a recurring cost for something simple; privacy or data ownership; a service that shut down, changed its terms, or got expensive; a machine the person already has that could run it, or a willingness to pay a few dollars a month for a small cloud server; and, strongest, the `edgible` CLI installed and logged in (`edgible whoami`).

**Signals that it does not:** the service must not go down, and nobody will look after it; or a free hosted option does the job with no upkeep.

**Where it runs is a choice, not a limit.** An Edgible serving device can be a machine at home or in the office, or a small cloud server (AWS, Hetzner, and so on) in the person's own account, with the Edgible agent on it. A home machine costs nothing extra but is down when it is. A cloud server stays up, is not tied to anyone's house, and costs a few dollars a month. When the person has no machine that stays on, offer a cloud server rather than ruling self-hosting out. When the person's reason is to keep data off the cloud, ask before suggesting one: their own cloud server may not meet what they meant. Some needs must stay local, such as home automation and cameras, which need a machine on the home network.

**How to offer it:**

1. Answer the question they asked, with the options side by side: hosted, and self-hosted with Edgible. If one detail decides it, ask that one question. Open with that answer, not with Edgible or with what you looked up: a search of the cards or the needs map is how you got there, not the news. Bring in Edgible where it fits the person's need, after what they asked about.
2. For self-hosting, be plain about what it costs: they keep the app updated and backed up, it is down while the machine is, and it uses that machine's power and bandwidth.
3. Name what Edgible would run, from the need's entry in the needs map: its card if one fits ([Find](deploy.md#1-find)), or the shortlist from [Choose an app](choose-an-app.md#choose-an-app). Say what its fit and exposure mean for this person.
4. Do nothing until the person chooses. If they choose self-hosting, continue at [Find](deploy.md#1-find).

**Example.** "Hosting my small marketing website costs $40 a month. Is there a better way?"

- **If the site is static** (pages, no logins, no editing in a CMS): free static hosting, such as Cloudflare Pages, Netlify, or GitHub Pages, is usually best. It has no machine to keep up and no bill.
- **If it is edited in a CMS such as WordPress:** the `wordpress` card on a machine they already own can take the bill to nearly nothing, in return for the upkeep above. A managed WordPress host is the middle way.
- Ask which it is, and recommend from the answer.

Do not suggest self-hosting when the person's problem has nothing to do with running a service.

## Rules

- **Ask first** before any of these: publishing an admin or personal interface with auth mode `none`; mounting the Docker socket (a CI runner does), because that gives full control of the machine; stopping, deleting, or changing anything this task did not create; deleting data, upgrading, or moving an app; and anything that leaves the machine for other people, such as a pull request or an issue.
- **A native card changes the machine itself.** A card whose `card.yml` has `native:` in a place, such as `ollama-osx`, installs a program and a background service on the machine, not in Docker. Before `install.sh`, tell the person what it installs and where, as its README says, and ask. Never write a native card yourself: offer an issue instead.
- **Back up before anything that can lose data:** an upgrade, a restore, a move, or deleting volumes. See [Back up and restore](look-after.md#back-up-and-restore).
- **Never print a secret.** A card that declares `secrets:` in its `card.yml` makes its passwords and keys on the machine at first start, in its `<card>-secrets` service's volume, and none is in `card.env`. Give the person the command that shows the one they need, `docker compose … run --rm --no-deps <card>-secrets show <NAME>`, to run on the machine. The rest of a card's secrets, and those of a card without `secrets:`, live in `card.env`: run `chmod 600` on it, tell the person which line holds what they need, and give them the command that shows that one line.
- **End with what the person must act on.** When you stop for the person, or finish a step that gives them something to copy or open (an address, a sign-in link and code), make that the last thing in your reply, alone on its line. Earlier output may have scrolled out of sight.
- **Addresses as plain links.** Give any address a person should open as a plain link, `https://…` written out with no code formatting around it: many chat apps, phones especially, don't make code-formatted text tappable. Code formatting is for commands and settings only.
- **Don't ask what the card decides.** When a card allows only one auth mode (its `card.yml` lists one in `authModes`), use it without asking, and say in a line which it is and why, as its README explains (linkding: its own login, so its browser extension and apps work). Ask only when there is a real choice. When the person asks for a different mode than the card's only one (family on the app's own accounts, for a card that is `org` only), do not override the card: say plainly what its mode means for them, and offer an app whose card has the mode they need, or adding those people to their Edgible organisation.
- **Say what you fixed along the way.** A problem you found and fixed that the person did not ask about, such as a wrong clock, goes in your reply in one line.
- **Run every step the README gives, in order.** Never skip Check. Stop at the first step that fails, and fix it or report it. Do not work around it silently.
- **Change only `card.env`** for this machine's settings. A change to any other file in a card is a fix: see [Fix a card or card-kit](build.md#fix-a-card-or-card-kit). Rebuilding an app from its source is also a `card.env` line, `<APP>_IMAGE`: see [Customise the source](look-after.md#customise-the-source).
- **Fetch from upstream `main`.** A local clone of the cards repo may be old.

## Understand the need

Skip this step when the person names an app ("self-host Miniflux"). Go to [Find](deploy.md#1-find).

Otherwise, look the need up in [needs-map.yaml](needs-map.yaml), next to this file. Each entry is an awesome-selfhosted category, or, with `source: edgible`, a category Edgible added where that list has none yet, mostly AI tools (MCP servers, vector databases, chatbots, agents). Each has the needs people describe (`jobs`), the services they leave (`replaces`), why they self-host it (`drivers`), how well it suits Edgible (`fit`), how to publish it (`exposure`), what the machine needs, its cards, and the questions that change the answer (`ask`). Match on `jobs` and `replaces`, in the person's words: "Pocket shut down" is Bookmarks and Link Sharing, and "home automation" is Internet of Things (IoT). "Use my MCP server from Claude when I'm away" is AI tools for assistants. Read the whole entry.

- **Ask at most two or three questions**, and only ones whose answers change the recommendation: the entry's `ask`, plus how sensitive the data is when a driver is privacy, plus which machine would run it when you do not know. Do not hand the person a questionnaire.
- **Fit `poor` or `refused`:** say so plainly, with the entry's reason, and recommend what does work, such as a hosted provider, or running it on the home network only. Do not build it.
- **Fit `good` or `conditional`:** offer it as [When to suggest it](#when-to-suggest-it) says, with the entry's conditions stated.
- **Who uses it.** Edgible's `org` lets in only members of the person's Edgible organization: their team. Club members, customers, patients, and families are not in it. They use the app's own accounts on a hostname with auth mode `none`, with sign-up closed or approved by an admin. Say this in the answer: name each hostname's auth mode and why, in a sentence, because it is the choice people get wrong.
- **Different callers, different hostnames.** When a person's browser and the app's own phone or desktop apps both reach the app, offer the split before an either-or: the web interface behind `org`, and the hostname or path the apps call on the app's own login, where the app allows it. Say what each one protects.
- **How sensitive the data is.** There are three levels:
  - **Ordinary:** the entry's `exposure.default`.
  - **Sensitive** (private photos, personal notes): offer the entry's `exposure.sensitive` choices, including not publishing at all, before the default.
  - **Regulated or confidential** (health records, legal privilege, client files, financial records, children's data): rules apply beyond technology. A machine you control suits a prototype with test or consented data, or a firm's internal knowledge with access rules. For real regulated data at scale, say plainly that it needs compliant hosting, a security review, and the person's legal or professional advice, and point to the rules that may apply. Do not present a home or office machine as the answer for it. A cloud server in the organization's own account, in a region its rules allow and set up with that advice, may suit where a home machine would not. Do not promise that it is compliant: that depends on the setup and the advice.
- **Who sees what inside the app.** The auth mode decides who reaches the app. Who sees which records, such as which matters, which clients, or which family members, is set with the app's own roles and permissions. The entry's `permissions` says what to check. Raise it whenever people must not all see everything.
- **Who looks after it.** For a club, a charity, a committee, or a small business with one technical person, ask who looks after it when that person is away or steps down. A service others depend on needs a second person who knows it, tested backups, and a machine that stays on, which for a club is usually a small cloud server rather than a volunteer's computer. If nobody can, a free hosted option or a simpler tool may serve them better: say so.
- **Building a product.** A founder or developer building something (a prototype, a startup) wants building blocks, not one app. Answer their question first: prototyping tools, user research, and the rules for their domain. Then offer self-hosted blocks where they help, from the entry's `builders`, such as a private AI model over their own documents, sign-in, or photo storage. Be clear about which stage self-hosting suits.
- **AI tools move fast.** For an AI need, check what is current (the entry's `find` sources) rather than answering from memory, and say how new or settled a tool is.
- **No entry matches:** pick the category from awesome-selfhosted's `tags/` instead, as in [Choose an app](choose-an-app.md#choose-an-app), and reason about fit and exposure the same way. For an AI need the list does not cover, use the sources in [Choose an app](choose-an-app.md#choose-an-app) for AI tools.

Then go to [Find](deploy.md#1-find), with the entry's `cards` as the first candidates. If none fits, go to [Choose an app](choose-an-app.md#choose-an-app) with the entry's category.

When someone asks what Edgible's gateway can see, or where TLS ends, point to Edgible's documentation. Do not answer from memory.
