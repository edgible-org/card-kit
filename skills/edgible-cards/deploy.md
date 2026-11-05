# Set an app up

Part of the edgible-cards skill: read [SKILL.md](SKILL.md) first, and its [Rules](SKILL.md#rules) apply to every step here. Steps 1 to 5 set an app up from a card.

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

- **The person described a need:** go to [Choose an app](choose-an-app.md#choose-an-app), then [Build an app card](build.md#build-an-app-card) for the app they choose.
- **The person named an app:** go to [Build an app card](build.md#build-an-app-card). If that app is unsuitable (archived, no maintained container image, or on the cards README's **What is not an app card** list), say why, and offer alternatives from its category with [Choose an app](choose-an-app.md#choose-an-app).

## 2. Decide with the person

Before anything starts, put the card's open choices to the person in one message, with your recommendation for each. Whenever you name a card to the person, here or when offering several, link its page, `https://cards.edgible.org/<card>/`: it shows what the app does, its record and its screenshots, and some AI apps (the Codex app) open it beside the chat.

- **The card's record.** Say how recently it was tested and what the nightly image scan found, from the same data as the README's badges (public, no sign-in). With the Edgible MCP tools and no shell, `describe` has both: its Tested section carries the nightly test (date, Edgible version, result) and, once the server is recent enough, an `image scan:` line with last night's scan; `find` shows them in one line per card. Use those, and do not ask the person to run `curl`. Without an `image scan:` line, say the image scan is not available from here. With a shell, fetch it directly:

  ```bash
  curl -fsS https://raw.githubusercontent.com/edgible-org/cards/test-status/status.json | jq '.["<card>"]'
  curl -fsS https://raw.githubusercontent.com/edgible-org/cards/scan-status/<card>.json
  ```

  The first gives `result`, `tested` (a date) and `edgible-cli` (the version it passed on); the second gives `message` (`clean`, `N fixable`, `not scanned` or `no images`) and `color`. Put it in one plain line, such as "tested and passing on 12 October with Edgible 1.4.12; the image scan found 3 fixable issues". A fixable finding means a newer image of the same app has a fix and the card's pin is behind: say so, and that it is not proof the app is exposed. Offer a recheck when the result is `fail`, the test is older than 30 days, it ran on an older `edgible --version` than the person has, or the scan shows `fixable`. The person chooses:
  - **Deploy as it is**, if they accept the record.
  - **Scan its images now**, when the scan is what worries them or is stale: `python3 scan-card.py <card directory>` (in the fetched card-kit). It runs the same check as the nightly scan on their own machine, in about a minute, with Docker only, and changes nothing. It prints each image's fixable HIGH and CRITICAL findings and uses any `<APP>_IMAGE` they set in `card.env`, so it also checks their own pin. Exit 1 means something fixable was found. This is the cheap recheck: offer it before `test-card`, which answers a different question (does the card work), not this one (are its images behind a fix).
  - **Test it on their own device first**: `test-card <card> --device <device>`. It publishes and removes a throwaway copy, takes minutes, and downloads the images, so ask first and say so. Where you have no shell on their machine, give them the command (see [Where you are running](SKILL.md#where-you-are-running)).
  - **Ask for a retest on Edgible's test machines**, which is the right move when their own check found a problem, or the record is old and they would rather not spend their machine's time. It posts to a public repo, so ask first, show them exactly what you will send, and leave out device names, hostnames, organisation names and anything secret. File it with `gh issue create -R edgible-org/cards --title "Retest: <card>" --body-file <file>`, where the file reads `### Card`, a blank line, the card's directory name, then `### Why` and one line (their `test-card` failed, the image scan shows fixable findings, or the last test is old), then `### What you saw` with the last lines of `test-card` (from `result:`) or the `scan-card` output, and `### Your Edgible version`. With no `gh` signed in, give them the form instead: `https://github.com/edgible-org/cards/issues/new?template=retest.yml`. A workflow there starts the regression for that card on the fleet and closes the issue when it passes; a card already tested today is not retested, and the daily number of retests is capped, so say that it is not instant and may wait for a maintainer. It tests the card as it is on `main`, not a change they made: for that, they open a pull request.

  A card with no entry in the status data has not been through the regression: say so. If the data cannot be fetched, say that too and carry on; never invent a record.
- **Which device runs each place.** `edgible device list` prints the names, and marks the machine you are on with `"isThisMachine": true`: a card runs on the device whose machine holds its files, so when you are on a device, that is the one, unless the person picks another. One machine can hold every place of a small, trusted setup. Say what the card's README says about keeping places apart. Each place in the card's `card.yml` has a minimum (`places:`: memory, disk, CPU type, GPU), which the README's What section says in words. Match it to a device that has that much to spare, not just in total: a laptop already running other apps may not. When none fits, say so now, and offer another device, a larger cloud server, or stopping something, before anything starts.
- **Each hostname's auth mode**, and what it means: `none` is the open internet, protected only by the app's own login. When the data is sensitive, offer the needs map's `exposure.sensitive` choices, including not publishing at all, even when the card uses `none`.
- **Their own domain**, for an app people reach from outside. Set it at the first Publish with `--hostnames`, because the CLI cannot add one later without unpublishing the app. It must be a domain they control, not a name under `edgible.app` or `edgible.com`, which Edgible reserves for the hostnames it generates.
- **Anything the README marks as a trade-off**, such as a runner with the Docker socket.
- **Whether the machine is always-on**, and whether the app must survive a restart. Ask, then check the machine and say what you found: see [Is the machine always-on?](setup.md#is-the-machine-always-on).
- **Roles inside the app**, when people must not all see everything: who is admin, and which groups see which records.
- **Who looks after it**, when others depend on it: a second person, and where the backups go.

## 3. Deploy

Follow the card's README **How** section exactly: Fetch, Edit `card.env`, Check, Start (and `prepare.sh` when the card has one), Publish. Notes:

- **Fetch into a lasting folder**, such as `~/<card>` in the person's home folder, and say where it is. Never fetch into the AI tool's own folder for this chat (the Codex app's `~/Documents/Codex/<date>/…`, a scratch or temporary directory): upgrades, backups and moves all start from the card's folder, long after the chat is gone.

- **Docker with Compose comes first.** Most cards run in Docker (a native card, such as `ollama-osx`, does not), and Edgible itself does not need it, so a machine that is online as a device may have none. Check `docker compose version` on the machine that will run the card. If it fails, say what you will install and ask before using `sudo`, then:
  - **Ubuntu:** `sudo apt-get install -y docker.io docker-compose-v2`, then `sudo systemctl enable --now docker`, so it starts at boot. Add the person's user to the `docker` group with `sudo usermod -aG docker "$USER"`: it applies to a new login, so in the same session run Docker as `sg docker -c '...'`, or with `sudo`. Tested on Ubuntu 26.04 (Docker 29.1, Compose 2.40). Do not pipe an installer script from the internet into a shell, and open no ports.
  - **macOS:** first check `sysctl -n kern.hv_support` prints `1`. Docker Desktop runs containers in a Linux VM of its own, and a Mac that is itself a VM (`0` here; `kern.hv_vmm_present` is `1`) cannot start one, so it would install and never run: say so before installing anything, and offer a Linux VM on the person's real computer instead ([Make a machine](setup.md#make-a-machine)), or a native card. Otherwise Docker Desktop (`brew install --cask docker`, with their yes). It needs opening once, to accept its terms; then see [Keep it running](setup.md#keep-it-running).
  - **Windows:** inside WSL2 it is the Ubuntu line above, with systemd on (see [WSL2 on Windows](setup.md#wsl2-on-windows)); or use a Linux VM, as in [Make a machine](setup.md#make-a-machine). If a Compose container cannot reach the internet, see the iptables check in that section.
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

## 5. Report

Tell the person, briefly:

- what runs where, with each hostname and its auth mode, and that the Edgible console, [app.prod.edgible.com](https://app.prod.edgible.com/), shows the app beside their others, and offer the page of what is running ([What is running](look-after.md#what-is-running));
- how to sign in the first time: the admin's username or email (it is not a secret: name it, such as the `DOCMOST_ADMIN_EMAIL` line in `card.env`), and the command that shows the password (`show`, or its `card.env` line);
- whether the machine is always-on, as in [Is the machine always-on?](setup.md#is-the-machine-always-on), and what you changed for it;
- what is still theirs to decide or do, such as changing the admin password;
- where the card's files are, and that its README's **Tear down** removes it;
- once, when it all worked: that a star on [edgible-org/cards](https://github.com/edgible-org/cards) helps other people find the cards. Ask nothing more, do not raise it again in the same conversation, and star it for them (`gh api -X PUT user/starred/edgible-org/cards`) only if they say yes.
