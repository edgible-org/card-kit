---
name: edgible-cards
description: Self-host apps with Edgible from tested Edgible cards, on a machine you control (at home, in the office, or a small cloud server), and look after them. Use when someone wants to self-host, run, or publish an app (Gitea, Umami, WordPress, a CI runner, and so on); wants their own version of a hosted service (a website, bookmarks, passwords, photos, files, analytics, a wiki, a knowledge base, bookings) for cost, privacy, or control, or is leaving one; pays too much to host a site or tool; needs sign-in or member accounts for a site; needs a shared tool for a club, team, or small business; asks what tools to build a prototype or startup on; wants AI tools reachable from anywhere (an MCP server, a vector database, a local model, a chatbot); asks whether Edgible has an MCP server, or wants to use Edgible or their own MCP server from Claude's desktop, web, or phone app, Cursor, or another AI app; asks what is running or why it broke; wants to change keys or settings, back up, upgrade, move, or remove such an app; needs Edgible itself set up, upgraded, or removed; shares an app they built; or has built an app, by hand or with an AI tool, and wants it live on Edgible, kept running, or shared in the card catalog; or a card needs building or fixing. Load it before suggesting Edgible or self-hosting to anyone, so its honest-advice rules apply.
---

# Self-host with Edgible cards

A **card** is a self-hosted setup written down so anyone can run it: [edgible-org/cards](https://github.com/edgible-org/cards). It is one of two types, `metadata.type` in its `card.yml`. An **app card** is one self-hosted app, tested end to end on a real Edgible serving device. A **pattern card** is several apps wired together for a purpose, often across several machines, built from app cards. App cards used to be called starters, in a repo now archived. Both types use one format, written down in [edgible-org/card-kit](https://github.com/edgible-org/card-kit), which also holds the tools that check and test them. The card-kit README is the source of truth for the format. Read it rather than guessing.

Work from a card whenever one fits. Its README is a tested path, and following it gives the same result for everyone. Improvise only where the card leaves a choice open, and say so when you do.

Most people describe a need, not an app. Start with [Understand the need](#understand-the-need), which reads [needs-map.yaml](needs-map.yaml) next to this file, and, when they have not asked to self-host, [When to suggest it](#when-to-suggest-it). A person who names an app goes straight to [Find](#1-find). Steps 1 to 5 set an app up. [After it is running](#after-it-is-running) covers everything after that: what is running, whether it works, fixing it, signing in, changing it, pausing, backing up, upgrading, moving, and removing it.

## Where you are running

Check this first, because it decides how you act on anything below.

- **With a shell on the person's machine** (Claude Code, or another agent in a terminal there): run the commands in this skill as written.
- **With Edgible MCP tools** (tools from an Edgible MCP server, such as `find`, `describe`, and `whats_running`): use them for what they cover. Prefer them over the matching commands: `find` and `describe` instead of listing and reading the repos in [Find](#1-find), and `whats_running` for [What is running](#what-is-running) and the Edgible layers of [Is it working](#is-it-working). `edgible mcp`'s tools (`list_applications`, `get_application_status`, `get_application_logs`, and the rest) answer the same questions from Edgible's side, and its write tools change an app only after the person agrees, as the [Rules](#rules) say. When `deploy_card` returns `firstUse`, a password a person needs, such as the admin's, give it to them in that reply, once, and tell them to sign in and change it now: it is not shown again, and the card made every other secret on the device, where nobody sees it. A card that needs a key the person brings, such as a model's API key, takes it from an Edgible organisation secret: `list_keys` shows which are stored, and `deploy_card` takes one by reference in `keys`. Never ask for the key itself in the conversation; if it is not stored yet, call `request_key` for a one-time link where they paste it themselves (from their phone too), or tell them the `edgible secret set` command to run on a computer. A setting that names Edgible accounts, such as openclaw's `OPENCLAW_USERS`, takes the email the person signs in to Edgible with: `whoami` gives it, so never guess it from another address. Asked about AI spending: as an agent (your own spend, budget, what is left), call `agent_spend`; through the owner's connector (everything, by app and model), call `gateway_spend`. Neither needs a key from you, and never try to read one. An agent cannot see other apps' spending: don't offer it; say the owner sees every app, by model, by asking Claude (or whichever assistant has their connector) for their AI spending. Deploying the `litellm` card with `deploy_card` makes it the person's AI gateway, wired to this server; `gateway_check` then sends one tiny question through it and says which provider answered, how fast, and at what cost ("does my AI gateway work?"). For an app that should use the person's shared AI gateway, `gateway_key` makes its key with a budget and stores it as a secret; deploy the app with that key by reference and the gateway's address. An Edgible account holds a limited number of apps (20 during the public beta, across its organisations; each published address is one, and a pattern may publish several). A deploy that fails with `QUOTA_EXCEEDED` needs room: say so plainly, list the apps, and let the person choose what to remove; never guess another cause. When an Edgible tool says its server is not signed in, `sign_in` gives a link and code: pass them to the person to approve with their Edgible login, and never approve it for them. They read upstream `main` and the person's own Edgible account. They find cards; they do not decide whether self-hosting fits. Understand the need first, and use them for the options you then offer.
- **With no shell on the person's machine** (Claude's desktop or web app, where a skill runs in a sandbox): do not run `edgible`, `docker`, `test-card`, or `check-env` in the sandbox. They would not reach the person's machine or Edgible account, and a sandbox result is not theirs. Use the MCP tools where they cover the step. For the rest, give the person each command to run on their machine, one step at a time, and ask them to paste what it prints. The needs map and the rest of this skill still apply: read them from this folder.

Say which of these you are working in when it changes what the person has to do.

## Edgible's MCP servers

Edgible has MCP servers, so an AI app can see and look after a person's Edgible apps itself. Answer "does Edgible have an MCP?" or "can I use Edgible from Claude, or Cursor?" with this:

- **`edgible mcp`**, in the Edgible CLI. Tools: who is signed in, the apps and devices, an app's status and logs, and a preview of a change. With `--allow-write`, it also applies changes and redeploys. It runs on the person's machine, signed in as their CLI. Start read-only, and add `--allow-write` once they trust it. `edgible mcp --help` lists the tools.
- **edgible-mcp**, from card-kit: `find` and `describe` cards, and `whats_running`, which checks each app answers the way its auth mode says. Its [README](https://github.com/edgible-org/card-kit/tree/main/edgible-mcp) says how to run it.
- **From anywhere:** Claude's web and phone apps take only remote connectors. See [Use an MCP server from Claude anywhere](#use-an-mcp-server-from-claude-anywhere).

A local server needs the CLI installed and logged in on that machine first ([Set up Edgible](#set-up-edgible)). Then add it:

- **Claude Code:** `claude mcp add edgible -- edgible mcp`.
- **Claude's desktop app:** Settings, Developer, Edit Config. In `claude_desktop_config.json`, add `"edgible": {"command": "<path>", "args": ["mcp"]}` under `mcpServers`, where `<path>` is what `command -v edgible` prints: the app does not read the shell's `PATH`. Quit and reopen the app, and the tools appear in a chat's tools menu.
- **Cursor:** the same entry in `~/.cursor/mcp.json`. Settings, MCP, lists its tools.
- **Another app:** the command `edgible` with the argument `mcp`, as that app's docs say.

**Offer it** when you work in an app that takes MCP servers (Claude's desktop app, Cursor, Claude Code) without Edgible MCP tools, and the person wants to know what is running, why something broke, or an app's status or logs: once, in a sentence, say that with `edgible mcp` added you could check these yourself instead of asking them to paste output. Do not offer it again if they decline, or in Claude's web or phone app, which cannot run it.

## Use an MCP server from Claude anywhere

Claude's web, desktop, and phone apps use a remote MCP server as a custom connector, which Claude's own servers call with no browser. So the server needs a public address and OAuth: a sign-in page alone (auth mode `org`) or an API key will not do. The [mcp-signin](https://github.com/edgible-org/cards/tree/main/mcp-signin) card is that OAuth, with Edgible doing the signing in. The same works for Edgible's own tools, as edgible-mcp behind mcp-signin.

1. **The server.** One that speaks HTTP, or a stdio server through the `mcp-bridge` card. Start it, but do not publish it.
2. **mcp-signin in front.** Point `MCP_UPSTREAM_URL` at the server, in the same Compose project (`http://<service>:<port>/mcp`). Publish both its addresses as its README says, and set `MCP_SIGNIN_USERS` when not every member of the organisation should get in.
3. **The connector.** In Claude on the web or desktop: Settings, Connectors, Add custom connector, with `https://<mcp-signin hostname>/mcp` and the OAuth fields empty. That is the hostname of the app published on `none`, never the `-login` one, which is the sign-in page people see behind Edgible's sign-in: given that address, Claude cannot check or register with the connector ("Couldn't check the server", "Couldn't register"), and its authorize page says not found. When you finish setting one up, end with that one address, complete with `/mcp`, labelled as the address to paste. It appears on the phone too: the phone cannot add one.
4. **Connect.** Edgible's sign-in, then a page asking to allow Claude: Allow. The connector lists the server's tools.

Before setting up Edgible's own connector (the edgible-connector card), check whether the organisation already has one (`edgible app list`: an `mcp-signin` app beside an `edgible-mcp`): say so, and offer to keep using it before making a second.

Never also publish the server behind mcp-signin: mcp-signin tells it who signed in, and it must hear that from nowhere else. A client that sends a header, such as Claude Code, needs no mcp-signin: publish the server on `api-key` instead, with one key per person.

## When to suggest it

The person may describe a problem, not a request to self-host: a hosting bill, a service that shut down, data they would rather keep, a team that needs a shared tool. Self-hosting is sometimes the best answer, and often it is not. Offer it as one option among others, never as the only answer.

**Signals that it may fit:** a recurring cost for something simple; privacy or data ownership; a service that shut down, changed its terms, or got expensive; a machine the person already has that could run it, or a willingness to pay a few dollars a month for a small cloud server; and, strongest, the `edgible` CLI installed and logged in (`edgible whoami`).

**Signals that it does not:** the service must not go down, and nobody will look after it; or a free hosted option does the job with no upkeep.

**Where it runs is a choice, not a limit.** An Edgible serving device can be a machine at home or in the office, or a small cloud server (AWS, Hetzner, and so on) in the person's own account, with the Edgible agent on it. A home machine costs nothing extra but is down when it is. A cloud server stays up, is not tied to anyone's house, and costs a few dollars a month. When the person has no machine that stays on, offer a cloud server rather than ruling self-hosting out. When the person's reason is to keep data off the cloud, ask before suggesting one: their own cloud server may not meet what they meant. Some needs must stay local, such as home automation and cameras, which need a machine on the home network.

**How to offer it:**

1. Answer the question they asked, with the options side by side: hosted, and self-hosted with Edgible. If one detail decides it, ask that one question. Open with that answer, not with Edgible or with what you looked up: a search of the cards or the needs map is how you got there, not the news. Bring in Edgible where it fits the person's need, after what they asked about.
2. For self-hosting, be plain about what it costs: they keep the app updated and backed up, it is down while the machine is, and it uses that machine's power and bandwidth.
3. Name what Edgible would run, from the need's entry in the needs map: its card if one fits ([Find](#1-find)), or the shortlist from [Choose an app](#choose-an-app). Say what its fit and exposure mean for this person.
4. Do nothing until the person chooses. If they choose self-hosting, continue at [Find](#1-find).

**Example.** "Hosting my small marketing website costs $40 a month. Is there a better way?"

- **If the site is static** (pages, no logins, no editing in a CMS): free static hosting, such as Cloudflare Pages, Netlify, or GitHub Pages, is usually best. It has no machine to keep up and no bill.
- **If it is edited in a CMS such as WordPress:** the `wordpress` card on a machine they already own can take the bill to nearly nothing, in return for the upkeep above. A managed WordPress host is the middle way.
- Ask which it is, and recommend from the answer.

Do not suggest self-hosting when the person's problem has nothing to do with running a service.

## Rules

- **Ask first** before any of these: publishing an admin or personal interface with auth mode `none`; mounting the Docker socket (a CI runner does), because that gives full control of the machine; stopping, deleting, or changing anything this task did not create; deleting data, upgrading, or moving an app; and anything that leaves the machine for other people, such as a pull request or an issue.
- **A native card changes the machine itself.** A card whose `card.yml` has `native:` in a place, such as `ollama-osx`, installs a program and a background service on the machine, not in Docker. Before `install.sh`, tell the person what it installs and where, as its README says, and ask. Never write a native card yourself: offer an issue instead.
- **Back up before anything that can lose data:** an upgrade, a restore, a move, or deleting volumes. See [Back up and restore](#back-up-and-restore).
- **Never print a secret.** A card that declares `secrets:` in its `card.yml` makes its passwords and keys on the machine at first start, in its `<card>-secrets` service's volume, and none is in `card.env`. Give the person the command that shows the one they need, `docker compose … run --rm --no-deps <card>-secrets show <NAME>`, to run on the machine. The rest of a card's secrets, and those of a card without `secrets:`, live in `card.env`: run `chmod 600` on it, tell the person which line holds what they need, and give them the command that shows that one line.
- **End with what the person must act on.** When you stop for the person, or finish a step that gives them something to copy or open (an address, a sign-in link and code), make that the last thing in your reply, alone on its line. Earlier output may have scrolled out of sight.
- **Addresses as plain links.** Give any address a person should open as a plain link, `https://…` written out with no code formatting around it: many chat apps, phones especially, don't make code-formatted text tappable. Code formatting is for commands and settings only.
- **Don't ask what the card decides.** When a card allows only one auth mode (its `card.yml` lists one in `authModes`), use it without asking, and say in a line which it is and why, as its README explains (linkding: its own login, so its browser extension and apps work). Ask only when there is a real choice.
- **Say what you fixed along the way.** A problem you found and fixed that the person did not ask about, such as a wrong clock, goes in your reply in one line.
- **Run every step the README gives, in order.** Never skip Check. Stop at the first step that fails, and fix it or report it. Do not work around it silently.
- **Change only `card.env`** for this machine's settings. A change to any other file in a card is a fix: see [Fix a card or card-kit](#fix-a-card-or-card-kit). Rebuilding an app from its source is also a `card.env` line, `<APP>_IMAGE`: see [Customise the source](#customise-the-source).
- **Fetch from upstream `main`.** A local clone of the cards repo may be old.

## Understand the need

Skip this step when the person names an app ("self-host Miniflux"). Go to [Find](#1-find).

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
- **No entry matches:** pick the category from awesome-selfhosted's `tags/` instead, as in [Choose an app](#choose-an-app), and reason about fit and exposure the same way. For an AI need the list does not cover, use the sources in [Choose an app](#choose-an-app) for AI tools.

Then go to [Find](#1-find), with the entry's `cards` as the first candidates. If none fits, go to [Choose an app](#choose-an-app) with the entry's category.

When someone asks what Edgible's gateway can see, or where TLS ends, point to Edgible's documentation. Do not answer from memory.

## 1. Find

The person names an app ("self-host Miniflux") or describes a need ("something for bookmarks"). Either way, look for a card first. For a need, read each candidate's **Why** to see whether it meets that need.

List what exists. Cards are the top-level directories that hold a `card.yml`, and the repo's README lists them by type, with each one's test status:

```bash
gh api repos/edgible-org/cards/contents \
  --jq '.[] | select(.type == "dir" and (.name | startswith(".") | not)) | .name'
```

Read the README of each candidate: the **Why** and **What** sections say what it does, which places (machines) it needs, and the auth mode on each hostname. If an app card fits but the person wants several apps together, the cards README says how to combine app cards into a pattern.

The Edgible catalog (`edgible template list`) has managed templates. Read a template's description for its limits before you offer it. A template's choices are fixed, and a card can be changed.

If nothing fits:

- **The person described a need:** go to [Choose an app](#choose-an-app), then [Build an app card](#build-an-app-card) for the app they choose.
- **The person named an app:** go to [Build an app card](#build-an-app-card). If that app is unsuitable (archived, no maintained container image, or on the cards README's **What is not an app card** list), say why, and offer alternatives from its category with [Choose an app](#choose-an-app).

## 2. Decide with the person

Before anything starts, put the card's open choices to the person in one message, with your recommendation for each:

- **The card's record.** Say how recently it was tested and what the nightly image scan found, from the same data as the README's badges (public, no sign-in). With the Edgible MCP tools and no shell, `describe` has both: its Tested section carries the nightly test (date, Edgible version, result) and, once the server is recent enough, an `image scan:` line with last night's scan; `find` shows them in one line per card. Use those, and do not ask the person to run `curl`. Without an `image scan:` line, say the image scan is not available from here. With a shell, fetch it directly:

  ```bash
  curl -fsS https://raw.githubusercontent.com/edgible-org/cards/test-status/status.json | jq '.["<card>"]'
  curl -fsS https://raw.githubusercontent.com/edgible-org/cards/scan-status/<card>.json
  ```

  The first gives `result`, `tested` (a date) and `edgible-cli` (the version it passed on); the second gives `message` (`clean`, `N fixable`, `not scanned` or `no images`) and `color`. Put it in one plain line, such as "tested and passing on 12 October with Edgible 1.4.12; the image scan found 3 fixable issues". A fixable finding means a newer image of the same app has a fix and the card's pin is behind: say so, and that it is not proof the app is exposed. Offer a recheck when the result is `fail`, the test is older than 30 days, it ran on an older `edgible --version` than the person has, or the scan shows `fixable`. The person chooses:
  - **Deploy as it is**, if they accept the record.
  - **Scan its images now**, when the scan is what worries them or is stale: `python3 scan-card.py <card directory>` (in the fetched card-kit). It runs the same check as the nightly scan on their own machine, in about a minute, with Docker only, and changes nothing. It prints each image's fixable HIGH and CRITICAL findings and uses any `<APP>_IMAGE` they set in `card.env`, so it also checks their own pin. Exit 1 means something fixable was found. This is the cheap recheck: offer it before `test-card`, which answers a different question (does the card work), not this one (are its images behind a fix).
  - **Test it on their own device first**: `test-card <card> --device <device>`. It publishes and removes a throwaway copy, takes minutes, and downloads the images, so ask first and say so. Where you have no shell on their machine, give them the command (see [Where you are running](#where-you-are-running)).
  - **Ask for a retest on Edgible's test machines**, which is the right move when their own check found a problem, or the record is old and they would rather not spend their machine's time. It posts to a public repo, so ask first, show them exactly what you will send, and leave out device names, hostnames, organisation names and anything secret. File it with `gh issue create -R edgible-org/cards --title "Retest: <card>" --body-file <file>`, where the file reads `### Card`, a blank line, the card's directory name, then `### Why` and one line (their `test-card` failed, the image scan shows fixable findings, or the last test is old), then `### What you saw` with the last lines of `test-card` (from `result:`) or the `scan-card` output, and `### Your Edgible version`. With no `gh` signed in, give them the form instead: `https://github.com/edgible-org/cards/issues/new?template=retest.yml`. A workflow there starts the regression for that card on the fleet and closes the issue when it passes; a card already tested today is not retested, and the daily number of retests is capped, so say that it is not instant and may wait for a maintainer. It tests the card as it is on `main`, not a change they made: for that, they open a pull request.

  A card with no entry in the status data has not been through the regression: say so. If the data cannot be fetched, say that too and carry on; never invent a record.
- **Which device runs each place.** `edgible device list` prints the names. One machine can hold every place of a small, trusted setup. Say what the card's README says about keeping places apart. Each place in the card's `card.yml` has a minimum (`places:`: memory, disk, CPU type, GPU), which the README's What section says in words. Match it to a device that has that much to spare, not just in total: a laptop already running other apps may not. When none fits, say so now, and offer another device, a larger cloud server, or stopping something, before anything starts.
- **Each hostname's auth mode**, and what it means: `none` is the open internet, protected only by the app's own login. When the data is sensitive, offer the needs map's `exposure.sensitive` choices, including not publishing at all, even when the card uses `none`.
- **Their own domain**, for an app people reach from outside. Set it at the first Publish with `--hostnames`, because the CLI cannot add one later without unpublishing the app. It must be a domain they control, not a name under `edgible.app` or `edgible.com`, which Edgible reserves for the hostnames it generates.
- **Anything the README marks as a trade-off**, such as a runner with the Docker socket.
- **Whether the machine is always-on**, and whether the app must survive a restart. Ask, then check the machine and say what you found: see [Is the machine always-on?](#is-the-machine-always-on).
- **Roles inside the app**, when people must not all see everything: who is admin, and which groups see which records.
- **Who looks after it**, when others depend on it: a second person, and where the backups go.

## Set up Edgible

The machine that runs a card needs the `edgible` CLI, logged in, and the machine set up as a serving device. Check first: `edgible whoami` says whether the CLI is logged in, and `edgible device list` marks this machine with `"isThisMachine": true` when it is a device. When both are there, skip to [Deploy](#3-deploy).

Edgible's own walk-through is [Start here](https://guides.edgible.com/) on guides.edgible.com. The steps below are the same, for an agent working on the machine. Ask before each step that uses `sudo`, and say what it installs.

1. **An account, first.** Ask: "Do you already have an Edgible account?" Nothing else in this section works without one, and the login in step 4 only approves an account that exists, so settle this before installing anything. If not, the person signs up at [www.edgible.com](https://www.edgible.com) in their own browser (free during the beta, no credit card) and creates an organisation there. The console is [app.prod.edgible.com](https://app.prod.edgible.com/). Wait until they say it is done. If they have more than one Edgible account, ask which one this machine is for. Never ask for their password.
2. **What the installer needs:** `curl`, `unzip`, and Node.js 20 or later (`node -v`). On Ubuntu 26.04, `sudo apt-get install -y curl unzip nodejs` installs all three; Ubuntu's Node is 22 there. Ubuntu 24.04 packages Node 18, which is too old: run the installer in a terminal, where it offers to install Node 20, or, with the person's yes, set `EDGIBLE_INSTALL_NODE=1` before it, which adds NodeSource's repository with `sudo`. On macOS, `brew install node`. On Windows, WSL2 with Ubuntu 26.04 works and is the lighter route: see [WSL2 on Windows](#wsl2-on-windows). A Linux VM, as the guide does, is the alternative.
3. **The CLI:**

   ```bash
   curl -fsSL https://get.edgible.com/install.sh | bash
   export PATH="$HOME/.local/bin:$PATH"     # this shell; new shells find it
   edgible --version
   ```

   It installs for the user, under `~/.edgible/cli`, checks the download's sha256, and keeps the previous version. A step it cannot pass stops it with an `EDG` code and the fix.
4. **Log in:** `edgible auth login --no-browser` prints a link and a code, then waits up to 10 minutes. Give both to the person, and make them impossible to miss: end your message with them, as three short lines with a blank line between each and nothing after the link on its line (no full stop, no bracket, no markdown link): **Open this link**, then the link alone on its own line, then **Confirm this code: XXXX-XXXX**, then "I'm waiting here: tell me when you have approved, or if it shows the wrong account." Print the link exactly as the CLI gave it, in plain text, so the person can select it or click it (many terminals open a link on Cmd or Ctrl and click). They open it in their browser, signed in to Edgible as the account they mean, check the code, and approve. When the command prints nothing because there is no terminal, run it as `script -qfc 'edgible auth login --no-browser' /tmp/edgible-login.log` (Linux) in the background and read the link from that file. Then don't end your turn: the person approving is what you are waiting for. Check `edgible whoami` every few seconds until it shows them logged in (up to 10 minutes), then carry on by yourself. Whenever you do stop to wait on the person, end that message with the link and code again, since earlier output may have scrolled out of sight. Then `edgible whoami` shows the account and organisation. With several, `edgible auth select-org`. **Always read the account back to the person and ask them to confirm it is the one they meant:** the approval signs this machine in as whichever Edgible account that browser was signed in to, which may not be the one they wanted (a work account in the same browser, say). If it is wrong, run `edgible auth logout` on this machine only, have them sign in to the right account (a private browser window helps), and run the login again.
5. **The device.** Ask for a name: letters, digits and hyphens, unique in the organisation, such as the machine and its OS (`minipc`, `office-mac`, `edgible-vm`). Then ask how it should run:
   - **Always on** (recommended for anything others rely on): a system service that starts at boot, with nobody logged in. The CLI is in the user's `~/.local/bin`, which `sudo` does not search, so link it first:

     ```bash
     sudo ln -sfn "$HOME/.local/bin/edgible" /usr/local/bin/edgible
     sudo edgible install --device-name minipc --yes
     ```

   - **Under the person's account**, without `sudo`: `edgible install --device-name minipc --yes`. It stops when they log out and does not start at boot. On Linux, `sudo loginctl enable-linger "$USER"` keeps it running.

   It takes under a minute and ends with `Agent is online`. Use `--yes`: `--non-interactive`, in older guides, is deprecated. A machine that was a device before reconnects to it, apps included. `edgible install --help` lists the choices for that, such as `--device` and `--new-device`.
6. **Check:** `edgible agent status` shows it running and online, and `edgible device list` shows the device `online`. Then [Keep it running](#keep-it-running) applies to it too.

### Which host?

Say what has been tried, so the person picks with their eyes open. Edgible has been run and apps published on:

| Host | Status | What to know |
|---|---|---|
| **Ubuntu 24.04 or 26.04**, on a spare computer, a server, or a cloud instance | Tested | The reference target. Node 20 or later (see step 2 of [Set up Edgible](#set-up-edgible)). A cloud instance is the same Ubuntu, and the always-on choice for apps other people rely on. |
| **Ubuntu 24.04 or 26.04 in a virtual machine** (Multipass; VirtualBox or Hyper-V on Windows) | Tested | Isolated and easy to delete. Runs only while the computer is on and awake, and needs a task to start it after a restart. |
| **macOS** | Tested | Docker Desktop for container cards. Keep it from sleeping if the app must stay up. |
| **Windows with WSL2 and Ubuntu 26.04** | Tested; recommended on Windows | No extra tools, and lighter than a VM. The distro stops 15 to 25 seconds after its last session ends, so it needs a keep-alive task; see [WSL2 on Windows](#wsl2-on-windows). Shares one network and one memory cap with every other distro. |
| **Other Linux** (Debian, Fedora, and so on), **Windows Home or 10 with WSL2**, **WSL1** | Not tried | May work. Say it has not been tried, and be ready to read the errors. |

**Native (macOS, or WSL2) or a virtual machine?** Native means Edgible and Docker run on the person's own system; a VM puts them in a separate Ubuntu. Plus and minus:

- **Native, plus:** lighter (WSL2 with the agent and two small containers used about 1.5 GB); nothing extra to install on Windows (WSL2) or Mac beyond Docker; files and ports are easy to reach from the host; no VM to start, size or update.
- **Native, minus:** it shares the machine with everything else. WSL2 distros share one network and one memory cap, so another distro's Docker once blocked Compose's network (seen once, not after a restart). A card's volumes and containers sit beside the person's own. Removing it cleanly takes more care than deleting a VM. macOS cannot run the Ubuntu-only steps in this skill, and apps that need Linux behave as Docker Desktop's VM allows.
- **VM, plus:** isolated, so a mistake or a bad card stays inside it; the same Ubuntu on any host; its own memory and disk; deleted or moved in one step.
- **VM, minus:** more to install (Multipass, and VirtualBox or Hyper-V on Windows); heavier, with memory reserved while it runs; its clock falls behind when the computer sleeps and needs the fix in [Make a machine](#make-a-machine); it does not start again after a restart without a task.

On Windows, recommend WSL2 first. Choose a VM when the person wants to keep experiments away from their own system, or already runs other Docker or WSL setups; choose native when they want the lightest setup. Say which you would pick and why, and let them decide.

Whatever the host, sleep stops it: a laptop that sleeps, or a VM or WSL on a computer that sleeps, is not always-on (see [Is the machine always-on?](#is-the-machine-always-on)). For a first try or for learning, any tested host will do. For an app other people use, point them to a machine that stays on.

### Make a machine

Someone with no spare computer, or who doesn't want to change theirs, can try Edgible in a virtual machine on the computer they have: nothing to buy, nothing on their own system to break, and deleted in one step when they are done. Use Multipass (Canonical's, on macOS, Windows and Linux; on macOS `brew install --cask multipass`, with their yes), and ask before making one:

```bash
multipass launch 26.04 --name edgible-vm --cpus 2 --memory 8G --disk 30G
```

**On Windows, recommend WSL2 with Ubuntu 26.04** (see [WSL2 on Windows](#wsl2-on-windows)): it is the lightest and needed no extra tools when tested. Offer a virtual machine instead when they already run Docker Desktop or other WSL distros, want their experiments kept apart from their own system, or are on Windows Home or 10, which has not been tried with WSL2. For a VM, steer them to VirtualBox with Multipass and Ubuntu 26.04, unless they already use Hyper-V or know what it is: then let them use Multipass's Hyper-V driver (Windows Pro or Enterprise), which is native and faster. VirtualBox works on every edition, Home included. The steps below are for the VM. Do these in order, in PowerShell (or `multipass.exe` and `powershell.exe` from inside WSL), and say what you find before you change anything:

1. **Check the machine.** `(Get-CimInstance Win32_OperatingSystem).Caption` is the edition. `(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB` is the memory in GB; they need at least 8 GB, more if they run other things, and 4 GB is too little. `(Get-PSDrive C).Free / 1GB` is the free disk in GB; they need about 40. Hardware virtualization must be on: `(Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled`, or `(Get-CimInstance Win32_ComputerSystem).HypervisorPresent`, should be `True`. If neither is, it is off in the BIOS or UEFI setup: tell them how to find it for their make (often "Intel VT-x", "SVM Mode" or "Virtualization Technology") and stop until they have turned it on, because you cannot do that for them.
2. **Install the two tools, with their yes.** `winget install Oracle.VirtualBox` and `winget install Canonical.Multipass`. Both need administrator rights and show a Windows prompt; say so first. Then `multipass set local.driver=virtualbox`. If they chose Hyper-V, skip VirtualBox and use `multipass set local.driver=hyperv` (the Hyper-V feature must be on, which needs an elevated PowerShell and a restart). VirtualBox runs alongside Hyper-V, which WSL2 and Docker Desktop also turn on, only more slowly.
3. **Make the VM** with the `multipass launch 26.04 ...` command above, then set the clock rule below.
4. **Make the VM start again after a restart.** Windows stops it when the computer restarts, and Multipass does not bring it back. With their yes, a scheduled task that runs at their sign-in does it: `Register-ScheduledTask -TaskName 'Edgible VM' -Trigger (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME") -Action (New-ScheduledTaskAction -Execute 'multipass.exe' -Argument 'start edgible-vm')`. Registering a task can need an elevated PowerShell. Put the commands in a `.ps1` file and run that, because quoting `$env:` inside a one-line command from bash expands it to nothing. Show them the task and how to remove it (`Unregister-ScheduledTask -TaskName 'Edgible VM'`).
5. **Keep Windows awake while they use it.** The VM stops when Windows sleeps: see [Is the machine always-on?](#is-the-machine-always-on), and check it on the Windows host, not in the VM.

I have not run steps 2 to 4 on a Windows machine; the commands are the documented ones. If one fails, say what it printed and ask, rather than trying another driver.

Size it for what they want to run: 2 GB for a website, 4 GB for an AI gateway, 8 GB for an AI agent with its gateway (less and the agent is stopped mid-answer), 20 to 30 GB of disk. Docker is not in a new VM: the first card needs it, as [Deploy](#3-deploy) says. Open no ports, in the VM or on the host: Edgible connects out. A VM's clock falls behind while the computer sleeps, and a wrong clock breaks sign-in, HTTPS and Edgible's own agent, whose every call is then refused with a bare "Forbidden". Ubuntu 26.04 keeps time with chrony, whose default (`makestep 1 3`) steps the clock only in its first three updates, so a VM that missed hours of sleep stays slow for good, though `timedatectl` says the NTP service is active. Right after making the VM, run `echo 'makestep 1 -1' | sudo tee /etc/chrony/conf.d/makestep.conf` and `sudo systemctl restart chrony`: it then steps the clock whenever it is more than a second off (tested on 26.04: a clock pushed back two minutes corrected itself within five seconds). Check that `date -u` in the VM agrees with the host's, after making the VM and again before signing in, and if not, `sudo chronyc makestep`. Ubuntu 24.04 uses systemd-timesyncd instead: `sudo timedatectl set-ntp true` and `sudo systemctl restart systemd-timesyncd`. Then set Edgible up inside it as above, running each command through `multipass exec edgible-vm -- bash -lc '...'`, with `sudo` there for the steps that need it. There is no terminal in that route, so the sign-in runs in the background as step 4 says. Name the device after the VM, such as `edgible-vm`. Say plainly that the VM runs only while their computer is on and awake: fine for trying and learning, and when other people come to rely on an app, move it to a machine that stays on, as in [Move to another machine](#move-to-another-machine). For a small cloud server instead, the person makes the account and pays; you set it up over SSH the same way, with key sign-in and no inbound ports besides SSH.

### WSL2 on Windows

WSL2 can publish apps with Edgible, and needs no extra tools on Windows. Tested 2026-11-01 with a fresh Ubuntu 26.04 distro: the `static-site` card (no sign-in) and `otter-wiki` (organisation sign-in, data volume kept across `compose down` and `up`) both answered over HTTPS with a valid certificate, and came back by themselves after a Windows restart. What to do, in order:

1. **Systemd on.** `/etc/wsl.conf` needs `[boot]` and `systemd=true`, then `wsl --terminate <distro>` from Windows. Without it Docker and the Edgible agent do not start as services.
2. **Install as for Ubuntu**: the packages in [Make a machine](#make-a-machine) step 2 and `docker.io docker-compose-v2` from [Deploy](#3-deploy), then the CLI and `sudo edgible install --device-name <name> --yes`.
3. **Keep it up.** WSL stops the distro 15 to 25 seconds after its last session ends, even with systemd, the agent and Docker running, and the app is then unreachable. See [Is the machine always-on?](#is-the-machine-always-on): a scheduled task at sign-in that runs `wsl.exe -d <distro> --exec /bin/sh -c "exec sleep infinity"`, with `ExecutionTimeLimit` set to 0 so Windows does not kill it after 72 hours. It needs an elevated PowerShell and the person's yes. After a restart, with the task, the app was back about four minutes after sign-in.
4. **If a Compose container cannot reach the internet** while `docker run` can, check `sudo iptables-legacy -S FORWARD`. All WSL2 distros share one network, so another distro's Docker (or Docker Desktop) using iptables-legacy can leave a FORWARD policy of DROP with accept rules only for `docker0`, which blocks Compose's `br-*` bridges. Narrow fix, lost on restart: `sudo iptables-legacy -I FORWARD -i br-+ -j ACCEPT` and `sudo iptables-legacy -I FORWARD -o br-+ -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT`. Do not set the policy to ACCEPT for everything. A machine with one distro, or after a restart, may not have this at all; it was seen once and not after a Windows restart.

The WSL VM is shared by all distros and capped by `.wslconfig` (this one: 4 GB, 2 CPUs); the agent and two small containers used about 1.5 GB. Like a VM, WSL2 stops when Windows sleeps (see [Is the machine always-on?](#is-the-machine-always-on)). From Windows, `curl.exe` can fail with `CRYPT_E_REVOCATION_OFFLINE` (http code 000) when the certificate revocation server is unreachable: that is the Windows client, not the app; `--ssl-no-revoke` works. Not tried: Windows Home, Windows 10, other distros.

## 3. Deploy

Follow the card's README **How** section exactly: Fetch, Edit `card.env`, Check, Start (and `prepare.sh` when the card has one), Publish. Notes:

- **Docker with Compose comes first.** Most cards run in Docker (a native card, such as `ollama-osx`, does not), and Edgible itself does not need it, so a machine that is online as a device may have none. Check `docker compose version` on the machine that will run the card. If it fails, say what you will install and ask before using `sudo`, then:
  - **Ubuntu:** `sudo apt-get install -y docker.io docker-compose-v2`, then `sudo systemctl enable --now docker`, so it starts at boot. Add the person's user to the `docker` group with `sudo usermod -aG docker "$USER"`: it applies to a new login, so in the same session run Docker as `sg docker -c '...'`, or with `sudo`. Tested on Ubuntu 26.04 (Docker 29.1, Compose 2.40). Do not pipe an installer script from the internet into a shell, and open no ports.
  - **macOS:** Docker Desktop (`brew install --cask docker`, with their yes). It needs opening once, to accept its terms; then see [Keep it running](#keep-it-running).
  - **Windows:** inside WSL2 it is the Ubuntu line above, with systemd on (see [WSL2 on Windows](#wsl2-on-windows)); or use a Linux VM, as in [Make a machine](#make-a-machine). If a Compose container cannot reach the internet, see the iptables check in that section.
  Then run `docker compose version` again, and carry on.

- Find `ORG_LABEL` in a hostname `edgible app list` prints: it is the part after the app name, such as `example` in `umami.example.edgible.app`. `EDGIBLE_DOMAIN` in `card.env` is the rest: `edgible.app` for apps published since October 2026. An app published before then keeps its `edgible.com` hostname: when you re-start, upgrade or move such an app, set `EDGIBLE_DOMAIN=edgible.com` in its `card.env`, or its links and sign-in break.
- Check: run `check-env` until it says `no conflicts`. Its fixes can come in more than one pass. Secrets come first, and a moved port can come next once the Compose file resolves. Paste the lines it prints, and read any line that starts with `#` before running it. Run it on the machine that will run the card, because its Sizing section measures that machine. A sizing conflict (an image with no build for this CPU, a GPU it lacks, more memory than Docker has, or not enough disk) means the card cannot run there: do not work around it. Take it back to the person with the remedy it prints. A sizing warning (it fits, but not alongside what is already running) is theirs to decide: tell them before Start.
- **Start: say what the wait is before it begins.** The first start downloads the app's images, once. The README's Start step says about how much (the image size test-card measured: about what is downloaded, a little different by CPU) and how long on a typical home connection. Tell the person that first, in your own words: the wait is the app's registry and their connection, not Edgible, and later starts and upgrades take seconds because the images stay on the machine. Run `pull` as its own step before `up`, as the README does, so the slow part shows by itself. A pull can look stalled for minutes: do not interrupt it, retry it or start `up` alongside it. Where your tool can run it in the background, do, tell the person when it ends, and meanwhile ask what is left (hostname, device). With `deploy_card` the device does the download after the tool returns: its result carries `download` (size and time) and a `next` line saying the same, so relay it before the person waits; `card_status` also reports the certificate (a new address waits for one, which Edgible issues on its own, usually within a minute) and, for an app deployed in the last hour that does not answer yet, a note saying why. Nothing can push a message into the chat when it is ready, so ask `card_status` with `app` and `wait_seconds` (up to 60) to hold one call until it answers, and while a note shows, wait and do not redeploy.
- Publish: if `edgible app create existing --help` lists `--tag`, add `--tag card=<name>` to every app the card publishes, so the deployment can be counted and found later.
- **Do not look up a hostname before Publish has created it.** Resolvers remember "does not exist" for up to 15 minutes. After Publish, ask Edgible's own nameservers:

  ```bash
  host=umami.example.edgible.app
  ns=$(dig +short NS "${host#*.*.}" | head -1)   # the zone's nameserver
  ip=$(dig +short "@$ns" "$host" A | tail -1)
  curl -sS -o /dev/null -w '%{http_code}\n' --resolve "$host:443:$ip" "https://$host"
  ```

## 4. Verify

Run the card's README **Verify** section. Each hostname answers the way its auth mode says: `none` with the app, `org` with a redirect to the Edgible sign-in, `api-key` with `401` until a key is sent, and `tcp` with a connection. Run the card's own checks too, in `etc/` or `test/`, when it has them.

Then check what the person actually asked for, end to end. For a Git forge, that is a real `git clone` and `git push`. For a CI runner, it is a workflow that runs to success. A green Verify is necessary but is not the whole answer.

## Keep it running

### Is the machine always-on?

An app is reachable only while its machine is on and awake. A laptop that sleeps at night, or a Windows machine that restarts for updates, takes its apps down with it. Find this out before the first Publish, not after the first complaint. Use the words "always-on" with the person, not "keep-alive" or "wake lock".

1. **Ask.** One plain question, with the reason: "Will this computer stay on and awake, so people can reach the app any time? That is what always-on means. If it is only on while you use it, the app will be down the rest of the time. That is fine for trying things." Two answers are enough: always-on, or sometimes. A cloud server or a machine in a rack is always-on; say so rather than asking.
2. **Detect.** Read the settings without changing anything, then say what you found in one or two sentences. A setting shows what the machine is told to do, not what it has done, so say "set to sleep after 30 minutes" and not "it sleeps". Run the check on the machine that hosts the device, which is the VM's host for a Multipass VM.
   - **What kind of machine.** `hostnamectl chassis` (Linux; `laptop`, `desktop`, `server`, `vm`), `systemd-detect-virt` (a VM or container, so the host decides), `grep -i microsoft /proc/version` (WSL: the Windows host decides, and WSL itself stops when idle unless something keeps it running). A battery means a laptop: `ls /sys/class/power_supply/ | grep -i bat`, or `pmset -g batt` on macOS.
   - **Linux.** `systemctl is-enabled sleep.target suspend.target hibernate.target` prints `masked` for each when sleep is off. A desktop session can still suspend on idle even then: `gsettings get org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type` should be `'nothing'` (GNOME). For the lid, `systemd-analyze cat-config systemd/logind.conf | grep -i HandleLidSwitch`; `ignore` is what a laptop that stays on wants.
   - **macOS.** `pmset -g` lists `sleep` (minutes, `0` is never) and `displaysleep`, for the power source in use. `pmset -g custom` lists them for battery and for the charger.
   - **Windows.** `powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE` prints `Current AC Power Setting Index` and `Current DC Power Setting Index` in seconds, and `0x00000000` is never. Plugged in is AC and on battery is DC. The lid-close action is hidden on some machines and `powercfg` shows nothing for it: ask the person to look under Control Panel → Power Options → "Choose what closing the lid does".
   - **What has actually happened.** `uptime -s` (Linux) or `uptime` shows the last start. A start time of a few hours ago on a machine meant to run for weeks means it has restarted or slept.
3. **Compare and say so.** If they said always-on and the machine can sleep, or it is a laptop on battery, a VM on a computer that sleeps, or a WSL instance with nothing keeping it up, say that plainly and what it means for the app. If they said sometimes, or the machine already stays on, say that and go on.
4. **Offer, then set it only if they say yes.** Give the choices:
   - **Make this machine stay on.** Show the exact command, say it changes a system setting and how to undo it, and ask. Change the plugged-in setting only: leave battery alone, because a laptop that sleeps when unplugged is a sensible default, and say so.
     - **Linux:** `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target` (undo with `unmask`). For the lid, set `HandleLidSwitchExternalPower=ignore` in `/etc/systemd/logind.conf.d/edgible.conf` and `sudo systemctl restart systemd-logind`, which can end a graphical login, so say so first.
     - **macOS:** `sudo pmset -c sleep 0` (plugged in only; undo with a non-zero number, such as `sudo pmset -c sleep 10`). `caffeinate -s` holds it awake only while that command runs.
     - **Windows:** `powercfg /change standby-timeout-ac 0` (plugged in only). For WSL, a scheduled task at sign-in that runs `wsl.exe -d <distro> --exec /bin/sh -c "exec sleep infinity"` keeps the WSL VM and its services up and starts them after a restart. It needs an elevated PowerShell to register, and a task you create for them is a persistent change: show it and ask.
   - **Move it to a machine that stays on**: a small cloud server, or a spare computer. See [Move to another machine](#move-to-another-machine).
   - **Leave it as it is** and tell anyone who uses the app that it is there only when the computer is on.
5. **Check, and put the result in the report.** Run the detect step again after a change. Say in [Report](#5-report) whether the machine is always-on, and what you changed to make it so.

### Surviving a restart

When the setup must survive a restart:

- **For uptime others rely on, a small cloud server** in the person's own account, running the Edgible agent, is usually better than a home machine: it is not switched off, asleep, or behind someone's home connection. Edgible's getting-started guides cover setting one up.

- **macOS with Docker Desktop:** in Docker Desktop's Settings → General, turn on "Start Docker Desktop when you sign in". If that option is greyed out, macOS has refused Docker's background item. Turn on Docker under System Settings → General → Login Items & Extensions → Allow in the Background. Or, with the person's agreement, add Docker to Open at Login: `osascript -e 'tell application "System Events" to make login item at end with properties {path:"/Applications/Docker.app", hidden:true}'`. Check sleep with `pmset -g`, because a sleeping Mac serves nothing.
- **Linux:** `systemctl is-enabled docker` should print `enabled`.
- The Edgible agent: `edgible agent status` says how it is installed. A user-level agent runs only while that user is logged in: see [Set up Edgible](#set-up-edgible), step 5.
- The Compose services use `restart: unless-stopped` in every card, so they come back with Docker.

## 5. Report

Tell the person, briefly:

- what runs where, with each hostname and its auth mode;
- how to sign in the first time, and the command that shows the password (`show`, or its `card.env` line);
- whether the machine is always-on, as in [Is the machine always-on?](#is-the-machine-always-on), and what you changed for it;
- what is still theirs to decide or do, such as changing the admin password;
- where the card's files are, and that its README's **Tear down** removes it;
- once, when it all worked: that a star on [edgible-org/cards](https://github.com/edgible-org/cards) helps other people find the cards. Ask nothing more, do not raise it again in the same conversation, and star it for them (`gh api -X PUT user/starred/edgible-org/cards`) only if they say yes.

## After it is running

Each card runs from a directory on its machine: the one that holds its `card.yml`, its Compose files, and its `card.env`. The commands below use `dir` for that directory and `f` for a Compose file in it. Run them once per Compose file when the card has several, such as the ci card's `runner-compose.yml`:

```bash
dir=~/umami                    # the card's directory
f=docker-compose.yml
C="docker compose --env-file $dir/card.env -f $dir/$f"
project=$($C config --format json | jq -r .name)
```

### What is running

```bash
docker compose ls --all    # each Compose project, with the path of its Compose file
edgible app list           # each published app: name, port, device, status
```

The path `docker compose ls` prints leads to the card's directory, and `metadata.name` in its `card.yml` names the card. An Edgible app on the same device with the port that the card's `card.env` sets (`<APP>_PORT`) is that card's app. Once apps carry tags, `--tag card=` says so directly. A project named `cardtest-*` is left over from an interrupted `test-card` run, not a deployment. Tell the person, and remove it only if they agree.

Answer with a short table: each card, its directory, its apps with hostname and auth mode, and whether each is up.

### Is it working

To prove an app works, show evidence from each layer:

1. **Containers:** `$C ps` shows each service running, and healthy when it has a healthcheck.
2. **Hostnames:** each hostname answers the way its auth mode says, checked through Edgible's nameservers as in [Deploy](#3-deploy).
3. **The card's own checks:** the scripts its README's Verify runs, in `etc/`, and those in `test/`. Run them with `card.env` exported and `HOSTNAME_<APP>` set to each hostname: `set -a; . $dir/card.env; set +a; export HOSTNAME_UMAMI=umami.example.edgible.app`.
4. **The goal:** what the person uses it for, end to end, such as signing in, a `git push`, a workflow run, or an event that shows up on a dashboard.
5. **The data path:** `edgible app doctor <app>` checks the deployment, certificates, and the path from the gateway to the workload.

Report each check with its result and the evidence, such as the status code or the line printed. Do not use `test-card` for this. It tests a fresh copy of the card and publishes apps of its own, not the person's running instance.

### Something is wrong

Work from the app outwards, and stop at the first layer that is broken:

1. **Containers:** `$C ps`, then `$C logs --tail 100 <service>`.
2. **On the machine:** `curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:<port>`, with the port from `card.env`. An `https` app is plain HTTP on the machine.
3. **Edgible:** `edgible app doctor <app>`, `edgible app events <app>`, and `edgible certs`.
4. **The machine:** Docker is running, `edgible agent status`, `edgible doctor`, and [Keep it running](#keep-it-running) after a restart.
5. **The clock, on a VM:** compare `date -u` there with the real time. These all mean a wrong clock: `Forbidden` throughout `sudo journalctl -u edgible-agent`; an app stuck waiting on its certificate while `edgible certs` shows `attempts: 0`; a sign-in code that is refused. `edgible app doctor` may blame the certificate instead. `sudo chronyc makestep` fixes it, with no restart: Edgible recovers within a few minutes. To stop it recurring, see [Make a machine](#make-a-machine).
6. **DNS:** ask Edgible's nameservers before you decide a hostname is broken. The person's resolver may still remember it as missing.

Fix the cause, then run [Is it working](#is-it-working). If the card itself is wrong, see [Fix a card or card-kit](#fix-a-card-or-card-kit).

### Sign in, passwords, and keys

- **The first sign-in:** the card's README says who the admin is, in How or Verify. A card with `secrets:` lists them in `card.yml`, each with its `kind`: a `human` one is for a person, and its `for:` says what it opens. Give the person the command that shows it, such as `docker compose --env-file ~/gitea/card.env -f ~/gitea/docker-compose.yml run --rm --no-deps gitea-secrets show GITEA_ADMIN_PASSWORD`. For a card without `secrets:`, list them with `grep -oE '^[A-Z0-9_]+(PASSWORD|SECRET|TOKEN|KEY)[A-Z0-9_]*=' $dir/card.env` and give the command that shows the one line, such as `grep '^BLOGLITE_ADMIN_PASSWORD=' ~/bloglite/card.env`.
- **Changing a password** happens in the app, by its own docs. The value the card made, or the one in `card.env`, only made the first admin; `show` keeps printing that first value after a change. Never edit or delete a file in the `<card>-secrets` volume: the card's database and apps read their own secrets there.
- **An `api-key` hostname:** `edgible app api-keys create --app <app> --name <who-calls-it>` prints the key once. Give it to the person and do not store it. `edgible app api-keys list --app <app>` and `delete` manage the keys.
- **An `org` hostname** lets in the members of the person's Edgible organization. `--allowed-orgs` on `edgible app update` adds other organizations.

### Change a setting

- **Auth mode:** `edgible app update <app> --auth-modes org`. Ask first before changing it to `none`.
- **A value in `card.env`:** edit it, then run `$C up -d --wait`, which recreates the services the change affects. Run `check-env` first when the change is a port.
- **Host port or hostname:** the CLI cannot change a published app's port or hostnames. Change `<APP>_PORT` (or the card's `<APP>_URL`, for the person's own domain), run `$C up -d --wait`, then `edgible app delete <app> --yes` and publish it again as in the README, with `--hostnames` for an own domain. The generated hostname comes from the app's name, so it stays the same. An own domain is one the person controls, pointed at the generated hostname with a `CNAME`: Edgible refuses any name under `edgible.com`, which is reserved for the hostnames it generates. Expect a short outage, and verify through Edgible's nameservers.
- **Pause:** `edgible app update <app> --target-state suspended`, then `$C stop`. **Resume:** `$C start`, then `--target-state running`. The data stays.

### Back up and restore

**When the card's `card.yml` has a `data:` section**, use card-kit's tools on the machine that runs the card. They know which volumes matter, dump databases while the app keeps running, stop only what they must, and prove a restore with the card's fingerprint:

```bash
for t in backup-card restore-card verify-card test-card; do   # restore and verify need all four
  curl -fsSLo "$t.py" "https://raw.githubusercontent.com/edgible-org/card-kit/main/$t.py"
done
python3 backup-card.py "$dir" --dry-run     # what it copies, what stops, and for how long
python3 backup-card.py "$dir"               # writes $dir-backups/<stamp>/, with backup.json
```

Tell the person what the dry run says will stop before the real run. The backup holds the card's files and `card.env`, so keep it private.

**Where the backup lives is the person's to choose, and moving it is theirs to do.** By default it goes beside the card, in `$dir-backups/<stamp>/`; `--to <folder>` puts it in any folder this machine can write to (an external drive, a mounted network drive). Ask where they want it, and tell them the full path of the folder you wrote, which is what they need to know. Edgible does not copy it between machines or to storage services: that is for the person, or their assistant if they ask, to arrange. `restore-card` reads a backup from any folder this machine can read. It needs the whole folder, the one that holds `backup.json`, because it checks every file against it first and stops on a damaged one. So before a restore, say where the backup folder must be, and let them bring it there.

**Restore** replaces the current data. Ask first. `restore-card` checks every file of the backup, backs the card up as it is, restores, and runs `verify-card`, which passes only when the data's fingerprint matches the backup's:

```bash
python3 restore-card.py "$dir-backups/<stamp>" "$dir" --dry-run
python3 restore-card.py "$dir-backups/<stamp>" "$dir" --yes
```

`--as <name>` restores a copy beside the running card instead, under its own name and a free port, to look at an old backup without touching the card. `--no-backup` skips the backup first, when the data is already lost.

**When the card has no `data:` section** yet, copy every volume by hand. A copy is whole only while the containers are stopped, so a backup is a short outage. Keep `card.env` and the `<card>-secrets` volume with the copies: the databases in them expect those passwords, and some data is locked with those keys.

```bash
backups=$dir-backups; stamp=$(date +%Y%m%d-%H%M); mkdir -p "$backups"
$C stop
for v in $(docker volume ls -q --filter "label=com.docker.compose.project=$project"); do
  docker run --rm -v "$v:/data:ro" -v "$backups:/backup" alpine tar -czf "/backup/$v-$stamp.tgz" -C /data .
done
cp "$dir/card.env" "$backups/card.env-$stamp"; chmod 600 "$backups/card.env-$stamp"
$C start
```

A copy on the same machine does not survive the loss of that machine. Say so, and that a copy somewhere else, such as an external drive or another storage service, is a good idea and the person's to arrange. Give them the path of `$backups`, and remind them it holds `card.env` and the secrets volume, so wherever it goes it should stay private.

To restore one of these by hand, ask first, and make a fresh backup first unless the data is already lost. Use the `card.env` that was saved with the copy:

```bash
$C stop
for v in $(docker volume ls -q --filter "label=com.docker.compose.project=$project"); do
  docker run --rm -v "$v:/data" -v "$backups:/backup" alpine \
    sh -c "find /data -mindepth 1 -delete && tar -xzf /backup/$v-$stamp.tgz -C /data"
done
$C start
```

Then run [Is it working](#is-it-working).

### Upgrade

1. **See what changed.** Fetch the card from upstream `main` into a new directory, and compare it with `$dir`. Its Fetch step replaces `card.env`, so never fetch over `$dir` itself.

   ```bash
   new=$(mktemp -d)
   curl -fsSL https://github.com/edgible-org/cards/archive/refs/heads/main.tar.gz \
     | tar -xz --strip-components=2 -C "$new" cards-main/umami
   diff -ru -x card.env -x images -x test.yml "$dir" "$new"
   diff <(grep -oE '^[A-Z0-9_]+=' "$dir/card.env") <(grep -oE '^[A-Z0-9_]+=' "$new/card.env")
   ```

2. **Tell the person** what will change, especially image versions and new settings. **If a database image changes major version**, such as `postgres:17` to `postgres:18`, stop: the data needs that database's own upgrade, which a new image alone does not do. Point the person to the database's docs.
3. **Back up**, and keep the old files: `cp -R "$dir" "$dir.before-upgrade"`.
4. **Copy the new files in, keeping `card.env`:** `rsync -a --exclude card.env "$new/" "$dir/"`. Add each new `card.env` line with its default, and run `check-env` to fill any new secret. A secret the new version adds to `secrets:` is made at the next Start; existing ones never change.
5. **Start:** `$C pull` downloads the new images, only the layers that changed, then `$C up -d --wait` starts them. Say first that the download is the app's registry and their connection, not Edgible. Run `prepare.sh` again only if the card's README says an upgrade needs it, because it usually makes the first admin.
6. Run [Is it working](#is-it-working). If it fails, put back `$dir.before-upgrade` and the backup, start, and check again.

The published apps stay as they are, unless the card's ports or apps changed.

### Customise the source

Some cards run an app whose source a person may want to change (teamdesk is one). A card says so with `source:` on the app in `card.yml`: `repo`, and when they are set `ref`, `path`, `dockerfile`, `dev`. The README's **Customising** section is the same method in words. Read `source` from the card the person runs, from upstream `main`, not from memory. A card with no `source:` has no code to change: say so, and if the person still wants a change, offer the app's own settings, or a fork of the app's project that they build as in [Add your own app](#add-your-own-app).

1. **Find the card's directory and the running image:** [What is running](#what-is-running), then `$C config --format json | jq -r '.services[].image'`. Confirm it matches `from:` in `card.yml`, and look for an `<APP>_IMAGE` line in `card.env`: if it is set, the person has customised before, and that image name is what to build on.
2. **Get the code.** Ask where it should go, and fork it for them only with a yes (`gh repo fork <repo> --clone`). Start from `source.ref` when there is one, so they begin from the code that is running. If `repo` has no Dockerfile, stop: the card is wrong, see [Fix a card or card-kit](#fix-a-card-or-card-kit).
3. **Make the change in the clone.** Read the repository's own notes first (`CLAUDE.md`, `README.md`), because they hold its rules. Try it from source with `source.dev` before building an image, and run the repository's own tests and checks.
4. **Build on the machine that runs the card:** `docker build -f <dockerfile> -t <app>:custom <path>`. Give the image its own tag, never one the card pinned. Push to a registry only if the person wants it on another machine, and ask first, because a pushed image is public unless the registry says otherwise. Build for each CPU the target machine has.
5. **Back up before switching** ([Back up and restore](#back-up-and-restore)). A change that adds a migration cannot be undone by putting the old image back: the data stays at the new version. Say this before the switch, in plain words.
6. **Switch.** Set `<APP>_IMAGE=<app>:custom` in `$dir/card.env` (the card documents the line; uncomment it), then `$C up -d --wait`. The Compose file is not touched, so a later [Upgrade](#upgrade) keeps the line like any `card.env` setting. A card with `source:` but no `<APP>_IMAGE` is out of date: see [Fix a card or card-kit](#fix-a-card-or-card-kit).
7. **Prove it:** [Is it working](#is-it-working), then the change itself: do the new thing in the app, as the person would.
8. **Go back** by removing the `<APP>_IMAGE` line and `$C up -d --wait`, plus the backup when the data changed.

If the change would help others, offer a pull request to the app's repository, and once its image is released, the card can point at it: [Fix a card or card-kit](#fix-a-card-or-card-kit). Open nothing without a yes.

### Upgrade Edgible

- **The CLI:** `edgible upgrade --check` says whether a newer release is out, and `edgible upgrade --yes` installs it, keeping the previous version. `edgible upgrade --version <version>` installs a given one, such as the previous version to go back. A CLI installed from npm (`@edgible-team/cli`, which stopped at 1.2.25) does not upgrade this way: `npm uninstall -g @edgible-team/cli`, then install it as in [Set up Edgible](#set-up-edgible).
- **The device software upgrades itself.** Edgible sends each device its updates, and the agent checks each one, switches to it, and goes back by itself if the new version fails its health check. There is nothing to run. `edgible version` shows the CLI, the latest release, and each device's agent version. A device far behind the others, or stuck, is a question for Edgible support (support@edgible.com) before anything else.

### Move to another machine

Ask first. A move is a copy, then a switch, then retiring the old copy, and the old copy keeps serving until the switch. The app is down only from deleting it on the old machine to answering on the new one, about a minute or two.

1. **The new machine** is a serving device that `edgible device list` shows online, with Docker, and room for the card: compare the card's `places:` with what the machine has free. A machine that runs something else that matters needs the margin, not just the total.
2. **Copy.** With a `data:` section: run `backup-card` on the old machine, make its backup directory visible to the new one (how is the person's choice: a drive, a network share, `rsync` over SSH if they have it; Edgible does not move it, but tell them the full path and that it holds `card.env`, so it should stay private), fetch the tools there as in [Back up and restore](#back-up-and-restore), and run `restore-card <backup> <new dir> --device <the new device's name>`, which also points `card.env` at the new machine. Into a new directory it restores the card under its own name, and ends with `verify-card`: the copy must pass before the switch. Without a `data:` section: [back up](#back-up-and-restore) by hand, copy `$dir` with its `card.env` and the backups, run `$C create` on the new machine, restore each volume, `$C up -d --wait`, and check it on `127.0.0.1`.
3. **Changes after the copy.** Anything written on the old machine after the backup is not in it. For an app people change all day, take a second backup just before the switch and restore it over the copy (`restore-card <second backup> <new dir> --yes --no-backup`): it is quick, because little has changed.
4. **Switch the hostnames:** `edgible app delete <app> --yes`, then publish again as in the README, with the new device's id. The generated hostname stays the same.
5. Run [Is it working](#is-it-working) through the hostname. Then, on the old machine, `$C down`, and keep its volumes and the backup until the person is satisfied.

### Remove

Follow the card's README **Tear down**, in order: Unpublish, Stop, Delete the data (it backs up each volume to `.tgz` first), and Remove the card. Ask before deleting data. Before `rm -rf` of the card, tell the person that any kept backup needs `card.env` and the `<card>-secrets.tgz` copy, which hold its passwords and keys. Remove only the apps, containers, and volumes this card made.

To take Edgible itself off a machine, once its apps are gone: `edgible uninstall` removes the device software and asks whether to delete the device from the account and remove the CLI. `--yes --delete-device --cli` does all three without asking. A device installed with `sudo` needs `sudo edgible uninstall`. Ask first: it is the machine's link to Edgible.

## Choose an app

Use this step only when the person described a need and no card meets it, or when the app they named is unsuitable. Do not pick from memory. Shortlist from [awesome-selfhosted](https://awesome-selfhosted.net), a curated list of free self-hosted software, through its machine-readable data. That data has one YAML file per app, with its categories (`tags`), platforms, licence, stars, last update, and whether it is archived.

```bash
ash=$(mktemp -d)
curl -fsSL https://github.com/awesome-selfhosted/awesome-selfhosted-data/archive/refs/heads/master.tar.gz \
  | tar -xz --strip-components=1 -C "$ash"
ls "$ash/tags"    # the categories; the needs map names the category for the needs it covers
```

Then list that category's apps, with each one's description, most starred first:

```bash
tag="Bookmarks and Link Sharing"   # the name: line of the category's file in tags/
for f in $(grep -l -- "- $tag\$" "$ash"/software/*.yml); do
  awk -v app="$(basename "$f" .yml)" '
    /^stargazers_count:/ {stars = $2}
    /^updated_at:/       {updated = $2}
    /^  - Docker$/       {docker = "docker"}
    /^archived: true/    {note = note " archived"}
    /^depends_3rdparty: true/ {note = note " needs-3rd-party"}
    /^description:/      {sub(/^description: /, ""); desc = $0}
    END {printf "%s\t%s\t%s\t%s\t%s\t%s\n", stars, app, updated, (docker ? docker : "-"), note, desc}' "$f"
done | sort -rn | head -25
```

**Rank by how well an app does the job, not by stars.** Stars measure popularity, and a popular app in the category may do a different job: for "members book our tennis courts", the most-starred Booking and Scheduling apps book appointments with a person or hotel rooms, and the right one, a resource-booking app, has a small fraction of their stars. Read each app's `description` against the person's job, and use stars only to choose between apps that fit equally well.

**AI tools.** awesome-selfhosted covers few of them. When the entry has `find`, shortlist from those sources as well, with the same rules. Two that cover most AI needs:

```bash
# MCP servers: the official registry. Servers with packages run on your own machine.
curl -fsS "https://registry.modelcontextprotocol.io/v0/servers?search=postgres&version=latest&limit=50" \
  | jq -r '.servers[].server | select(.packages) | [.name, .repository.url // "-", .description] | @tsv'
# Other AI tools: GitHub topics, most starred, updated recently
gh api "search/repositories?q=topic:vector-database+pushed:>$(date -v-6m +%F 2>/dev/null || date -d '6 months ago' +%F)&sort=stars&per_page=15" \
  --jq '.items[] | [.stargazers_count, .full_name, .description] | @tsv'
```

The registry does not rank or review servers, and many are near-copies. Prefer one from the maker of the tool it connects to, then one whose repository is active and well used, and read what its tools can do before offering it. Most packaged servers speak `stdio` (the registry's `transport`), which only a local client can use: the `mcp-bridge` app card serves it over Streamable HTTP.

Keep only apps that list `Docker`, are not archived, were updated within about six months, and do not need a third-party service. Read the shortlisted apps' own docs for what the list does not say: the containers and database they need, how the first admin is made, and whether they have phone or desktop apps. Apps with their own clients need an auth mode other than `org` on some hostname: see the cards README's auth table.

Offer two or three candidates in one message. For each, give what it is best at and what it costs to run: containers, database, memory, and the auth trade-off. Recommend one and say why, and let the person choose. A simple app that meets the need usually beats the one with the most features.

## Build an app card

When nothing fits, offer to build an app card. First check the cards README's **What is not an app card** list: an open resolver or relay, an app with no maintained container image, or an archived project gets a plain no, with the reason.

1. Read the [cards README](https://github.com/edgible-org/cards#what-a-card-is) and the [card-kit README](https://github.com/edgible-org/card-kit), then copy the shape of the app card closest to the new app. Set `metadata.type: app`, `metadata.added` to today's date (`2026-10-18` form), `metadata.homepage` to the app's own site, and `metadata.license` to its SPDX licence when you have read it from the app's repository (leave it out when unsure).
2. Follow the format: pinned image versions; every variable, service and volume prefixed with the app's name; no `container_name`; each secret declared in `card.yml` `secrets:` (its kind, and for one made on the device its `make` command) and made by a `<card>-secrets` service, as card-kit's README says under Secrets, never a `card.env` value; a key the person brings is a `card.env` line, declared `external`; each hostname's auth mode chosen from the cards README's table; and `prepare.sh` when the first visitor would otherwise make the admin. When the app has source a person may change, add `source:` (the card-kit README says under Source what each field is), read the image as `${<APP>_IMAGE:-<pinned image>}` in the Compose file, and add a commented `# <APP>_IMAGE=` line to `card.env`, and write `customise:` in the README's YAML for anything particular to changing it.
3. Write the README with `card-readme`, and check the files with `check-cards` (see the card-kit README for `run`).
4. Test it on the person's serving device until it passes: `python3 test-card.py <name> --device <device> --by agent`. Put inputs only a person may fill in `test/inputs.env`, and the app's own end-to-end checks in `test/<name>.sh`.
5. Deploy it for the person from the tested files. Their app comes first, and contributing is optional.

## Add your own app

When the person built the app (often with an AI tool) and wants it on Edgible or in the catalog, there are three different goals, and they are not the same job. Ask which they want, and lead in this order, because most people stop after the first two:

1. **Get it live.** Publish it on a serving device so people can reach it: [Deploy](#3-deploy), Publish, with `edgible app create existing` on the port the app listens on and the auth mode its callers need. A container is not needed to start.
2. **Keep it running.** For anything that should stay up, put it in a container with its data in a named volume and its secrets made on the machine, as a card of its own in their own repository ([Build an app card](#build-an-app-card)). Backups, moves and upgrades then work as for any card, and the card can stay private.
3. **Share it,** so others can run it. That is optional, and the rest of this section.

### Share it: check it is ready first

1. **Run `check-app`:** `python3 check-app.py <the app's folder> --image <name:tag> --steward <their GitHub name>` (card-kit's tool; `--json` for an agent). It lists what is **required** for a card (a public image with a version tag that runs on amd64 and arm64, a licence others can use, its settings written down, a port and a place for its data, no committed secret) and what is **nice to have** (no default password in the files, a healthcheck, a non-root user, `*_FILE` secrets, a backup note, an icon, tagged releases), with what to do for each gap. A third list, **your call**, holds who will be the steward: it never fails the check, because a card can be listed with none. Read it to the person in plain words: what must change before a card can exist, and what would make it a better one. Offer to build each missing piece (a Dockerfile, a multi-architecture build with `docker buildx build --platform linux/amd64,linux/arm64 --push`, a licence, a tagged release, an `.env.example`, a healthcheck, an icon: a square logo, SVG if possible, which you can draw for them if they have none, and which a card keeps as `images/icon.svg`; without one the catalog shows the Edgible symbol). Change nothing in their app without their yes. Run it again until every required item passes. An agent working alone repeats this with `--json` until `ready` is true, and stops to ask when a required item needs a decision only the person can make, such as the licence. The steward is the person's to name too, never yours or an agent's.
2. **Name a steward, or none:** ask the person. It is the GitHub user or organisation that will review changes to the card and fix it when its test fails. It goes in `metadata.steward` in `card.yml`. If nobody will, say so: the card is listed as having no steward, and that is allowed.
3. **Build the app card** as in [Build an app card](#build-an-app-card), from the app's own Compose setup, with `source:` pointing at the repository that holds the Dockerfile, since the app is meant to be changed. The author knows its first-run steps, its secrets, and who calls each hostname, which decides the auth mode. Ask them rather than guess.
4. **Test it on a machine of their own** (below) until it passes.
5. **Contribute it** as in [Contribute](#contribute), and say in the pull request that the person is the app's author. Reviewers judge it by the same checklist as any card.
6. **Point to where self-hosters look.** awesome-selfhosted lists free software that meets its own inclusion rules: read its contributing guide before suggesting it. A short "Run it with Edgible" section in the app's README, linking to the card, helps people find it.

If the app is one part of a bigger setup, a pattern card that combines it with other app cards may suit better.

### Test it on a machine of their own

Test the card on a machine of theirs, signed in to their own Edgible account, never anyone else's. It can be a spare computer, or [a VM](#make-a-machine), with Docker and the Edgible agent ([Set up Edgible](#set-up-edgible)). Run `python3 test-card.py <name> --device <their device> --by person` (`--by agent` when an agent ran it). It publishes the card's apps in their own organisation under test names, checks them, and removes them. It takes a few minutes and the image downloads. A pass writes `test.yml` beside the card: who ran it, on what machine, the Edgible version, and a hash of the card's files, so a later edit shows up as stale. That is the author's own evidence. A maintainer tests the card again on Edgible's own devices before merging.

## Contribute

Offer this, and do it only with the person's yes.

[CONTRIBUTING.md](https://github.com/edgible-org/cards/blob/main/CONTRIBUTING.md) in edgible-org/cards is the process. Read it and follow it. Where it differs from what is written here, it wins. In short:

- **Scrub before anything leaves the machine.** Remove device names, hostnames, the organization id, secrets, and the person's own domain from every file. `check-cards` catches some of them, and you check the rest.
- **Check the name is free:** a 404 from `gh api repos/edgible-org/cards/contents/<name>` means it is.
- **Use a fork** unless the person can push to the Edgible repo: `gh repo fork edgible-org/cards --clone`. Work on a branch, and never push to `main`.
- **Fill in the repo's pull request template.** Read `.github/PULL_REQUEST_TEMPLATE.md`, write its sections into the body with the `result:` lines of the passing `test-card` run, tick only the checklist items you actually checked, and tick the box that says an AI agent made it. Pass that as `gh pr create --body-file`.
- **If you could not make it pass,** do not open a pull request. Offer an issue from the repo's request template instead: read `.github/ISSUE_TEMPLATE/app-request.md` (or `pattern-request.md` for a pattern), fill in its sections with what you tried and where it failed, and run `gh issue create --repo edgible-org/cards --title "App request: <app>" --label app-request --body-file <file>`.

A maintainer tests a new card on their own device before merging. Once merged, the nightly regression keeps testing it.

## Fix a card or card-kit

When a card's steps or a card-kit tool are wrong, and not the person's machine:

1. Find the cause in the files, not just a workaround.
2. Fix it on a branch, and prove the fix with a real run (`test-card`, or the card's own steps) on the case that failed.
3. Offer the pull request, with what failed, why, and the run that proves the fix. Open it only with the person's yes.
