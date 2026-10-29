# card-kit

The format of an Edgible card, and the tools that check and build one. [edgible-org/cards](https://github.com/edgible-org/cards) holds the cards people share, and runs these tools. The catalog site, [cards.edgible.org](https://cards.edgible.org), is built from it with [card-site](#card-site).

If the cards help you, star [edgible-org/cards](https://github.com/edgible-org/cards) rather than this repo: it is where people find them, so it is where we count.

## What a card is

A card records a deployment pattern so someone else can reproduce it: the programs, the images, the ports, the auth mode on each hostname, and which apps share a serving device. It leaves out device names, hostnames, the organization id, and passwords, so the next person maps each place to a serving device they have.

Most apps are web apps published over `https`. An app that is not web, such as a game server or SSH, is published over `tcp` or `udp`. Such an app has no auth mode, so its `authModes` is `[none]`, and its port must be from `20000` to `29999`, the range the managed gateway opens. Treat it as reachable by anyone.

A card is a directory whose name is the card's name. In a cards repo, every top-level directory that holds a `card.yml` is one card.

A card's `metadata` in `card.yml` has `name`, `description`, `type`, and optional lines: `added: 2026-10-18`, the date it joined the catalog (the site shows it and lists the newest); `homepage: https://...`, the app's own home page; `license: AGPL-3.0-only`, the app's licence as an SPDX identifier (leave it out when unsure); and `status: experimental | stable | deprecated`, stable when left out. None of them affects whether a card needs testing again. A card is one of two types, set as `metadata.type`: `steward: <github user or organisation>`, who answers for the card: reviews changes to it, approves its upgrades, fixes it when its test fails, and can be reached through its issues (the site links it to github.com/<steward>; leave it out when nobody does and the card is shown as having no steward, still tested every night); `reviewed: 2026-10-29`, the date a person last read the card and its test. Like `added`, `homepage`, `license` and `status`, these two are left out of a card's test fingerprint, so changing them never makes a test stale. Machines may do the routine work (Renovate bumps, the nightly regression, drafts by an agent); the steward is the person who answers for the result.

- **`app`**: one self-hosted app, such as Gitea or Umami, ready to run on its own or to build other cards from. The app may sit on more than one hostname and bring its own database, but not a second app. An app card always has `test.yml`, one Compose file, and one place, and names every service and volume after itself (`umami`, `umami-db`, `umami-db-data`) with no `container_name`, so two app cards drop into one Compose file without a clash. `check-cards` checks these rules.
- **`pattern`**: several apps wired together for a purpose, possibly across several machines, such as a Git server with a CI runner. A pattern is built from app cards. Its README says which.

| File | What it is |
| --- | --- |
| `card.yml` | The apps, ports, auth modes, and places. [card.schema.json](card.schema.json) is the source of truth for it. |
| `README.md` | How to run the card, under five headings: Why, What, How, Verify, and Tear down. |
| `card.env` | Machine settings, read by the Compose file. Secrets are empty in git. |
| `*compose*.yml` | The Compose files the card runs, next to `card.yml`. |
| `prepare.sh` | Optional: what runs after Start and before Publish, such as making the admin so no setup page is ever public. See [Prepare](#prepare). |
| `images/` | Optional pictures: `card-light.svg` and `card-dark.svg`, drawn from `card.yml` by `card-image`, and `icon.svg` (or `icon.png`), the app's own logo, square, fetched by `card-icon`. The catalog site shows the icon on the card's tile and page, and the Edgible symbol for a card without one. |
| `etc/` | Optional sample files the card hands you, such as a PDF or a page. |
| `test/` | Optional inputs for `test-card`: values only a person may fill, and the card's own checks. See [Test inputs](#test-inputs). |
| `test.yml` | The latest run of the card's lifecycle. Every app card has one; for a pattern it is optional. See [Test results](#test-results). |

## The README

Copy the shape from a card like yours and change the names, so every card reads the same way.

- **Why** is the problem the card solves.
- **What** is the apps and the places.
- **How** is how to fetch the card, edit `card.env`, check the machine, start the Compose file, and publish.
- **Verify** comes after Publish. It checks the card, not the apps. Each app gets one check that its hostname answers the way its auth mode says: `none` with the app, `org` with a redirect to the Edgible sign-in, and `api-key` with `401` until a key is sent. Add the first sign-in when the app makes its admin on the first visit. End with a link to that app's docs.
- **Tear down** is last, with the same four steps as every other card: Unpublish each app, Stop with `down`, Delete the data after copying each volume to a `.tgz`, and Remove the card.

A card holds what depends on Edgible or on another app in the card: hostnames, auth modes, devices, and how the apps reach each other. What is the same on any host belongs to the app: its users, its settings, and how to use it. Link to the app's docs. Do not copy them.

Leave device names, hostnames, organization ids, and passwords out of the README, the Compose files, and `card.env` in git. The schema does not check the README.

## Prepare

Some apps let the first visitor set them up: make the admin, or finish an install wizard. Published first, that is anyone on the internet. Such a card makes it safe before Publish, in `prepare.sh`, a short `sh` script next to `card.yml`. The README's Start step runs it with `sh <card>/prepare.sh` and shows it in full, and `test-card` runs the same file, so what a person runs is what was tested.

It starts the same way in every card, so it runs from anywhere and in a test:

```sh
#!/bin/sh
# Prepare for the gitea card: make the admin.
# Run it after Start and before Publish, from the directory that holds gitea/:
#   sh gitea/prepare.sh
set -eu
cd "$(dirname "$0")"
set -a; . ./card.env; set +a
COMPOSE=${COMPOSE:-docker compose --env-file card.env -f docker-compose.yml}

$COMPOSE exec -T -u git gitea gitea admin user create --admin --username gitadmin ...
```

Use `$COMPOSE` for every Compose command: `test-card` sets it to the test's own project. Use `-T` with `exec` and `run`, because a test has no terminal. Keep what only a person can do, such as adding their own name to a whitelist, in the README instead.

## Minimum recommended

A card can say how big a machine each place needs, in an optional `places:` section at the end of `card.yml`. The numbers are the minimum recommended for everything in that place together: every app, database, and helper that runs there.

```yaml
places:
  web:
    memory: 2 GB             # for all the containers in the place together
    disk: 6 GB               # the images and the data to start with
    arch: [amd64, arm64]     # architectures every image in the place runs on
    gpu: none                # none, optional, or required
```

Sizes are a number, a space, and `MB`, `GB`, or `TB`. Each field is optional, and a card without `places:` is still valid. `check-cards` checks that each place named there is one the apps use. `check-env` compares the places being started with the machine, adding them up when two places share it, and reports a shortfall as a warning, not a conflict.

The README's What section says the same numbers in words, so a reader who never opens `card.yml` sees them. An app card always has `places:`, from the sizes its test measured (see `measured:` under [Test results](#test-results)) plus a margin.

## Data

A card says what its volumes hold in a `data:` section, before `places:` (which `test-card --write-places` rewrites). Moves, backups, upgrades, and checks after a restore all read it.

```yaml
data:
  volumes:
    gitea-db-data:
      class: irreplaceable
      dump:                        # optional: a consistent copy without stopping the app
        service: gitea-db
        command: pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"       # writes to stdout
        restore: pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean   # reads stdin
    gitea-data:
      class: irreplaceable
  fingerprint:
    service: gitea-db
    command: psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select json_build_object('users', (select count(*) from \"user\"))"
```

Every named volume in the card's Compose files has an entry, with a class: `irreplaceable` (back it up, and check it after a restore), `rebuildable` (the app recreates it from irreplaceable data, such as a search index), or `cache` (safe to drop, such as thumbnails). Without a `dump`, a consistent copy stops the app. `card.env` is always data and needs no entry.

A card with an irreplaceable volume has a **fingerprint**: one command, run with `sh -c` in `service`, that prints one line of JSON describing the data, such as `{"bookmarks": 412, "latest": "2026-10-14"}`. It holds counts (integers) and ISO dates only, never content, because it appears in test results and reports; one to eight lower_case keys, in the app's own words. It is read-only, takes seconds even on a large install, prints zeros on an empty one, and prints the same line for the same data on any machine. After a restore, the fingerprint must match the one taken with the backup. A pattern card inherits `data:` from its app cards and declares only what it adds.

## Secrets

A card says what its secrets are in a `secrets:` section, beside `data:`: every password, key and token it uses, by the variable that holds it, what kind it is, and what happens to it on a move. The design is in [Card secrets declarations](https://claude.ai/code/artifact/b0f5f681-db89-4081-8b40-31899831352c).

```yaml
secrets:
  UMAMI_DB_PASSWORD:
    kind: internal            # internal | shared | human | external
    use: password             # internal: password | signing | encryption | token
    make: openssl rand -hex 16
    update:                   # applies a new value to the data on a move
      service: umami-db
      command: psql -U umami -c "ALTER USER umami PASSWORD '$UMAMI_DB_PASSWORD'"
  UMAMI_TWO_FACTOR_KEY:
    kind: internal
    use: encryption           # carried on a move: the data is locked with it
    make: openssl rand -hex 32
  UMAMI_ADMIN_PASSWORD:
    kind: human
    make: openssl rand -hex 16
    for: the admin's first sign-in
```

- **internal** (only the app's services need it), **human** (a person needs it once) and **shared** (apps of the card on different machines) are made **on the device**, at first start, by the card's `<card>-secrets` service: the image `ghcr.io/edgible-org/card-secrets`, with one line `NAME=command` per secret in its `CARD_SECRETS`, the same commands as `make`. It writes each into the card's secrets volume, one file per secret under `/run/card-secrets`, and never changes one that exists. They are never `card.env` lines or `${NAME}` in a Compose file.
- An app reads them through its own `*_FILE` setting where it has one, such as `POSTGRES_PASSWORD_FILE: /run/card-secrets/UMAMI_DB_PASSWORD`, or starts through the loader the service also writes: `entrypoint: ["sh", "/run/card-secrets/.load"]` with the image's own start command in `command:`. Mount the volume read-only into each service that needs it.
- **external** secrets, which someone else issued (a model key), are `card.env` lines the person fills, with `from:` saying where to get one.
- `on-move` defaults by use: `new` for signing and token, `new-then-update` for password (then `update` is required), `carry` for encryption and the other kinds. `restore-card --move` applies them; the `update` service must mount the secrets volume.
- A person sees a human secret with `docker compose … run --rm <card>-secrets show <NAME>`, on the machine.

`check-cards` checks that each declared internal, human or shared secret is made by the card-secrets service with its `make`, that none is a `card.env` line or a `${NAME}`, that each external one is a `card.env` line, and that each `update` runs in one of the card's services. A card without `secrets:` keeps `# Generate with:` lines in `card.env`, and `check-cards` prints a note until it moves over.

`test-card` reads the secrets a card made with `show` once it starts, hides their values in what it prints, and exports them to the card's checks as it does `card.env`, so a check can sign in with the admin's password.

## Source

Some apps come with source a person may want to change: a small internal tool, a workshop app, anything the author wrote to be adapted. An app with `source:` in `card.yml` says where that code is, so a reader, and an agent, can find it, change it, and rebuild the image the card runs.

```yaml
applications:
  - name: teamdesk
    from: ghcr.io/example/teamdesk:1.0.0
    ...
    source:
      repo: https://github.com/example/teamdesk   # required: the code and the Dockerfile
      ref: v1.0.0                                  # optional: the tag the pinned image was built from
      path: .                                      # optional: the build context, default the root
      dockerfile: Dockerfile                       # optional: relative to path, default Dockerfile
      dev: bun install && bun run dev              # optional: run from source, before building an image
```

`repo` is the repository the image's `org.opencontainers.image.source` label names, and it must hold the Dockerfile: the repository an app was forked from may not. `ref` makes a person start from the code that runs, not from whatever the default branch is now. Leave `source:` out for an app nobody is meant to change, such as Gitea or Postgres: the card then has no Customising section.

The README gets a **Customising** section from it, written by [card-readme](#card-readme) and required by [check-cards](#check-cards). The method is the same for every card:

1. Fork the repository and clone it, at `ref` when there is one.
2. Change it, and try the change with `dev`.
3. Build an image on the machine that runs the card (`docker build`). A tag that exists only on that machine is enough there; push to a registry the person controls only to run it elsewhere, or on another CPU.
4. Back the card up with [backup-card](#backup-card), because a new version's migrations cannot be undone.
5. Set `<APP>_IMAGE` in `card.env` to the new image and run `up -d --wait`. The volumes stay. Verify again.

Going back is removing the `<APP>_IMAGE` line, plus the backup when the data changed. The Compose file is never edited: an app with `source:` reads its image as `image: ${TEAMDESK_IMAGE:-ghcr.io/example/teamdesk:1.0.0}`, the pinned image being the default, and `card.env` carries a commented `# TEAMDESK_IMAGE=` line that says so. The variable is `<APP>_IMAGE`, named like `<APP>_PORT`. `check-cards` requires both, and `card-fit` reads the default as the app's image. Tests and upgrades run the default.

## Self-hosting fit

How well an app card's app suits self-hosting, as a count of checks it passes: `fit 4/5` on the card's tile on the cards site, with each check and the fact that decides it on its page. Each check is a yes or no about the app itself, never an opinion, and never a card's own unfinished work. [card-fit.py](card-fit.py) decides them; it writes nothing into a card.

| Check | Passes when | Read from |
| --- | --- | --- |
| Secrets kept out of card.env | no password or key it makes is a `card.env` line: the card makes them on the device ([Secrets](#secrets)) | card files |
| Reads secrets from files | its app reads them from files itself, not only from the environment through the card's loader | card files |
| Has a health check | the image has one, or the card's Compose file adds one | image, card files |
| Starts as a non-root user | the image's user is not root | image |
| Builds for arm64 and amd64 | the image has builds for both | image |

A check that does not apply is left out, such as the secrets checks for an app with none. The image facts are what `test-card` measured on the images it ran, in `test.yml` under `image_facts:`; `test-card <card> --image-facts` adds them without a full test. Until a card has them, those checks wait, and the site says so rather than guessing. A failed check is a fact to fix upstream, such as asking an app to read a `*_FILE` setting, not a mark against the app.

## Places with no app

Some services publish nothing: they only connect out. A CI runner asks a forge for jobs, a backup job sends copies away, a worker takes tasks from a queue. When one of them runs beside a published app, it is just another service in that app's Compose file, and it goes wherever that file goes. When it should run on a machine of its own, give it a place with no app, and say which Compose files it runs:

```yaml
places:
  forge:
    memory: 512 MB
  runner:
    runs: [runner-compose.yml]   # a place no app uses
    memory: 1 GB
```

- A place no app uses must have `runs:`. A place with apps may have it too, to tie a Compose file to it explicitly.
- `card.env` has a device line for every place, these included: `FORGE_DEVICE`, `RUNNER_DEVICE`.
- These places start after Publish, because what they connect to is usually an app the card has just published. The README says so, in a step after Publish: Start the runner.
- `check-env`, `test-card`, and Tear down treat them like any other place. There is just nothing to publish or verify by hostname.

A service that mounts the Docker socket, runs privileged, or uses the host's network has full control of its machine. A runner usually needs the socket. That is allowed, but the README must say so in words, and `check-cards` fails a card whose README does not mention it. `check-env` notes it too.

## Native cards

Some apps need the machine itself, which Docker cannot give them. Ollama on a Mac is the first: Docker on macOS runs a Linux VM with no access to the Mac's GPU, so the models run several times slower there. Such an app gets a card of its own, beside the Docker one (`ollama-osx` beside `ollama`), not a variant inside one card, so each stays one tested path.

A native place says which OS it runs on:

```yaml
places:
  ollama:
    native: macos
    memory: 8 GB
    disk: 2 GB
    arch: [arm64]
```

In place of a Compose file, the card has two scripts, which run with `card.env` exported:

- **`install.sh`** installs a pinned release (a `VERSION=` line), checked against its SHA-256, into the card's own directory, and starts it as a background service named by `SERVICE` in `card.env`. Running it again restarts it, and with a new `VERSION`, upgrades it.
- **`uninstall.sh`** stops the service and removes it and the release. It deletes nothing outside the card's directory by path. Data the person pointed elsewhere, such as a models folder they already had, is never the card's to delete.

The rules are stricter than for a Compose card, because the card changes the machine itself. Its README says what is installed where. Tear down leaves the machine as it was. The grow job never makes a native card, and `check-cards --untrusted` refuses one. `check-env` checks the machine instead of Docker: its OS and CPU, memory, disk, each app's port, and whether `SERVICE` is free or already this card's. `test-card` runs `install.sh` for Start and `uninstall.sh` for Tear down, under a service name of its own, so it never touches a copy the machine already runs. The regression sends the card to a runner of that OS: `macOS` for `native: macos`.

## Conventions

`card.yml` stays short because the tools read the rest from names. `<APP>` is the app name in capitals, with `-` written `_`. `check-cards` checks the first four.

| What | Name |
| --- | --- |
| The host port of an app | `<APP>_PORT` in `card.env`, set to the port in `card.yml`. Apps that are one process share the first one's variable, so list that app first. |
| The Compose file that runs an app | The one that reads `${<APP>_PORT`. |
| The serving device | `DEVICE` for a card with one place. `<PLACE>_DEVICE` for each place of a card with more. |
| The Compose project | A top-level `name:` in each Compose file. Pick one that says which card it is, because two Compose files with the same `name:` on one machine replace each other's containers. |
| The URL an app gives out | Built from `ORG_LABEL` and `EDGIBLE_DOMAIN`: `https://<app>.${ORG_LABEL}.${EDGIBLE_DOMAIN:-edgible.app}` is the hostname Publish generates, so nothing changes after Publish. `EDGIBLE_DOMAIN` is a line in `card.env`, `edgible.app` for apps published since October 2026; an app published earlier keeps its `edgible.com` hostname, so its `card.env` says `edgible.com`. For your own domain, an `<APP>_URL` override wins over both, such as `${ACCOUNTS_URL:-https://accounts.${ORG_LABEL:?set ORG_LABEL in card.env}.${EDGIBLE_DOMAIN:-edgible.app}}`. |
| A secret | Empty in git, with a `# Generate with: <command>` comment above it. `check-env` fills it with that command. |
| A value the card cannot run without | `${VAR:?set VAR in card.env}` in the Compose file. |

A card that may be combined with others reads better with names that say which app they belong to: `UMAMI_DB_PASSWORD` rather than `POSTGRES_PASSWORD`, a service called `umami-db` rather than `db`, and no `container_name`. App cards must follow this, so they combine cleanly, and `check-cards` checks it. For a pattern it is advice.

## Test results

A card can carry `test.yml`, the latest result of its whole lifecycle: Check, Start, Publish, Verify, and Tear down. Git history holds the earlier ones.

Commit `test.yml` only when something material changes: the result, a step's outcome, the images, or the files. A rerun with the same outcome and the same images leaves the file alone, so `tested` is the day of the run that produced this result, not the most recent run. [test.schema.json](test.schema.json) is its source of truth, and `check-cards` checks it when it is there. Every app card has one; for a pattern it is optional.

```yaml
tested: 2026-10-10
result: pass                 # pass only when no step failed
card-kit: 3f2a9c1            # the card-kit commit the checks came from
edgible-cli: 1.4.6
files: sha256:e0a0fb12ab72ca14  # the card's files when tested
machine: linux/amd64, docker 29.4
images:
  - gitea/gitea:1.24.6
  - postgres:17-alpine
steps:
  check-env: pass
  start: pass                # up --wait, every service running or healthy
  publish: pass
  verify:                    # one entry per app in card.yml
    gitea: pass
    gitea-ssh: pass
  teardown: pass
duration: 4m12s
by: agent                    # agent, person, or ci
```

A run can also record what it measured for each place, which is where the numbers in `places:` come from:

```yaml
measured:
  gitea:
    memory: 310 MB           # peak memory of the place's containers together
    images: 420 MB           # the images, as stored on the machine
    data: 64 MB              # the volumes at the end of the run
```

A card can also record checks only it knows how to make, under `steps:`, run after Verify:

```yaml
steps:
  ...
  checks:
    runner-online: pass      # the runner registered with Gitea
    workflow-runs: pass      # a workflow ran on it to the end
```

`files` is a fingerprint of every file in the card but `README.md`, `images/`, `test.yml`, and hidden files. When it no longer matches, the card changed since its test: `check-cards` says so in a note, and `check-cards --fresh`, which the cards repo runs on every pull request, fails it unless its last test passed. A change to a passing card, such as a setting or its secrets, stays a note, and the nightly regression retests the changed card on the fleet.

### Test inputs

Everything `test-card` needs is in the card, so anyone, or a CI job, runs the same test with no options. Besides `prepare.sh`, which people run too, it is in the card's `test/` directory:

- **`test/inputs.env`** sets values in the test's copy of `card.env`, for the ones only a person may fill: accepting a licence (`MINECRAFT_EULA=TRUE`), or a folder a person picks (`JELLYFIN_MEDIA_DIR=./test-media`, which lands inside the test's copy). Each key must already be a line in `card.env`. It is never a secret; `check-env` generates those.
- **`test/<name>.sh`** is a check only the card knows how to make, recorded as `<name>` under `checks:`. It runs after Verify with `card.env` exported and `HOSTNAME_<APP>` set to each published hostname, and is retried until it exits 0. Its `curl` reaches each https hostname at the address Edgible's own nameservers give, through a `.curlrc` in `CURL_HOME`, so a resolver that still remembers the name as missing does not fail it. A helper it needs, such as a small Python script, sits beside it in `test/` and is found from `$(dirname "$0")`; only `.sh` files are checks.

`--set` and `--check` add to these from the command line.

Each step is `pass`, `fail`, or `skip`. `check-cards` fails a `test.yml` that gives no Verify result for an app, says `pass` while a step failed, or names a hostname or an address. Like the rest of a card, it leaves out device names, hostnames, and the organization id: `machine` is the operating system, architecture, and Docker version, not the device.

## Upstream requests

A cards repo may have an `upstream/` folder: requests the cards' testing suggests the authors of an app could act on, each a file ready to paste as an issue in the app's own project. A file starts with a header (`app`, `project`, `cards`, `status`, `found`, and `sent` once it is filed), then a `# Title` line and the request. `status` is `draft`, `sent`, `resolved` or `wontfix`. The header is the only place a card is linked to a request, so `card.yml` does not change when one does. `check-cards` (run on the whole repo) checks the header, that each name in `cards` is a card, and that a `sent` request has the issue's address. [card-site](#card-site) lists a card's requests on its page, under Known upstream issues. `check-upstream` (run from the root of a cards repo, changes nothing) lists what the cards work around that an app's author could fix: an app started through an entrypoint that loads its secrets from files (it reads them from the environment only), and an app whose image has no healthcheck of its own while the card declares one (from `test.yml`'s `image_facts`). Each is a candidate to check against the app's source or docs, and it is left out when `upstream/` already has a request for that card and topic. `retire-card <card>` (run from the root of a cards repo, changes nothing) lists what removing a card would touch before anyone does it: its folder, the catalog table, `upstream/` requests that name it, the skill's needs map and other cards that use it, with the firm mentions (a link, a path or a name in a list) kept apart from the loose ones. It exits 1 when another card depends on it. Removing a card is a person's decision; deprecate it with `status: deprecated` first. With `--remove` it makes the edits, on a new branch and one commit of the cards repo (the folder, the catalog row, the card's name in each `upstream/` request's `cards:` list) and, with `--kit PATH`, of that card-kit checkout (the needs map); it never pushes, never deletes an upstream request (it is about the app, so a person decides), refuses a card another card depends on unless `--force`, and refuses a working tree with uncommitted changes.

## Tools

There are two kinds of tool, and the difference decides how each one runs.

A tool that works on files in a repo runs through `run`, in the image from [Dockerfile](Dockerfile). It may use any package; add the package to the Dockerfile. Docker is the only thing an author installs.

A tool that checks the machine a card runs on does not run in a container, because a container sees its own ports, processes, and files, not the machine's. That tool is one Python file that uses only the standard library, so it runs with `python3` anywhere, and a card README can fetch it with `curl`. `check-env`, `test-card`, `test-cards`, `backup-card`, `restore-card`, `verify-card` and `scan-card` are these; `run` refuses them. `scan-card <card>` scans the images a card pins for fixable HIGH and CRITICAL vulnerabilities with Trivy, run as a container, changing nothing: the same check as the nightly scan in edgible-org/cards, for one card on your machine, with your `card.env` overrides.

### run

Clone this repo beside the repo you work in, and run a tool by its name from that repo's root:

```bash
git clone https://github.com/edgible-org/card-kit ../card-kit
../card-kit/run check-cards
../card-kit/run card-image website
```

`run` mounts the repo you run it from and the kit, separately. Paths are relative to the directory you run it from. The first run builds the image, which takes about half a minute; later runs reuse it, and an edit to the Dockerfile builds a new one. A change to a tool script needs no rebuild. The tool runs as your user, so the files it writes are yours.

### card-readme

Writes a card's `README.md`. The parts only a person knows come from a short YAML file; the rest comes from `card.yml` and the Compose files, the same way on every card: How (Fetch, Edit card.env, Check, Start with `prepare.sh` when the card has one, Publish), each app's Verify check by its auth mode, Customising when an app has `source:`, Tear down, and the sizing sentence in What, from `places:`. After Publish it adds a "Without Edgible" note: only Publish is Edgible's, and any reverse proxy or tunnel can take its place.

Start runs `pull` before `up --wait` and says what the first start downloads: about how much (the image size test-card measured, in `test.yml`: about what is downloaded, a little different by CPU), and about how long on a typical home connection. So a slow first start reads as the app's images arriving, once, not as Edgible being slow. A card with no measurement yet gets the same sentence without a size.

```yaml
why: The problem the card solves, with a link to the app.
what: The apps, the places, and the choices made, such as the auth mode.
data: Where the data lives.
edit: What to set in card.env.
start: Anything after `up --wait`, such as why the admin is made before Publish.
after-prepare: What prepare.sh prints, and anything left for a person to do.
customise: Anything specific to changing this app, such as a rule its migrations follow.
verify:
  gitea: What the check proves, and the first sign-in.
docs: [Gitea, https://docs.gitea.com]
```

```bash
../card-kit/run card-readme gitea gitea-readme.yml
```

The YAML file must be inside the repo, because `run` mounts only the repo and the kit. Keep it out of the commit unless you want it there. Fetch reads from `edgible-org/cards`.

### check-cards

Checks each `card.yml` against [card.schema.json](card.schema.json), checks that `metadata.name` matches the directory name, and checks the first four conventions above. When a card has `test.yml`, it checks that too. It checks [`data:`](#data): an entry for every Compose volume and none for a volume that is not there, a fingerprint when a volume is irreplaceable, and dumps and fingerprints that run in a service of the card; a card with volumes and no `data:` yet gets a note, not a failure. With no arguments it checks every top-level `*/card.yml` in the current directory. Each failure says what to change. An app card must also follow the app rules in [What a card is](#what-a-card-is). The cards repo runs this on every pull request. `--untrusted` is for a card nobody has reviewed yet, such as one an agent just wrote, before it runs anywhere: it refuses anything that reaches outside the card (a host path, the Docker socket, privileged mode, the host's network or processes, devices, or extra capabilities). `--before-test` leaves out the rule that an app card has `test.yml`, for a new card about to be tested for the first time, since `test-card` writes that file; every other rule still applies.

```bash
../card-kit/run check-cards
../card-kit/run check-cards website/card.yml
```

### pick-app

Picks the next app to make an app card for, from the first gap in the skill's [needs map](skills/edgible-cards/needs-map.yaml): a category people ask about that no card covers yet. It lists that category's apps on awesome-selfhosted that a card can be made from (a Docker image, not archived, updated in the last six months, no third-party service, not already a card or excluded), most starred first, as JSON. Categories Edgible adds, mostly AI tools, have no awesome-selfhosted data and are listed separately. edgible-org/cards' nightly grow job uses it.

```bash
../card-kit/run pick-app --exclude wallabag
```

`--app` picks a named app instead, by its name on awesome-selfhosted, and gives the needs-map category it belongs to, preferring one no card covers yet. Grow uses it when it is started for one app, so the merged card still lands in its category.

```bash
../card-kit/run pick-app --app ownCloud
```

### card-image

Writes `images/card-light.svg` and `images/card-dark.svg` for a card. The picture lists the apps, ports, auth modes, and places, from `card.yml`. If a `what` line does not fit its row, the command fails and you shorten that line.

```bash
../card-kit/run card-image website
```


### card-icon

Fetches a card's icon, its app's own logo, into `images/icon.svg`, or `icon.png` when no SVG exists. It looks the card's name up in two open sets of self-hosted app logos, [dashboard-icons](https://github.com/homarr-labs/dashboard-icons) (Apache-2.0) and [selfh.st icons](https://github.com/selfhst/icons) (CC BY 4.0), SVG first. `--slug` names the app when it differs from the card. A pattern, or a card for a generic service, needs no icon: the site shows the Edgible symbol. The logos stay their apps' trademarks, used to name the app.

```bash
../card-kit/run card-icon umami
```
### card-site

Builds the catalog site from a cards repo: a page per card (its README, picture, apps, places, and latest test), a page per need in the skill's [needs map](skills/edgible-cards/needs-map.yaml) (what people say, whether self-hosting suits it, how to publish it, and its cards, titled by the hosted products people leave for it, such as "Self-hosted alternatives to Pocket, Raindrop.io and Instapaper"), an index of each, and `llms.txt`, `sitemap.xml`, and `robots.txt`. The index can be searched by name, description, app, category, the services a card replaces, and the needs in people's words, and filtered by category, type, a public page, ARM, fitting in 2 GB, and a passing test. The filters go in the address, such as `?cat=analytics&arm=1`, so a filtered view can be shared. A card's categories are the needs that name it in the needs map, so they are kept in one place. Each page carries Open Graph tags, so a shared link shows its title and description. `--status` is the regression's `status.json` from the cards repo's `test-status` branch. `--stars` is the cards repo's star count, shown on the site's Star button from 25 on. A card whose test measured its images gets a First start section with the size and time, and a pill on its tile from 1 GB. The kit's `site` workflow starts the cards site's build when card-site, its assets, or the needs map change, with the `CARDS_SITE_TOKEN` secret. It also writes `/ops/`, an unlisted phone-sized page (not in the sitemap, `noindex`) for whoever looks after the repo: it reads `latest.json` from the repo's `reports` branch, which the daily report writes, and shows what ran overnight, what failed, and what waits for a person, with pull requests sorted into ready, review, and hold. A card whose latest test failed stays listed, dimmed and with no link, and its own page opens with a note saying so and linking to its regression issue, so nobody starts a new setup on it until it passes.

The output is a plain folder with relative links, so the same build works on GitHub Pages, in an nginx container, or in a bucket, at any path. `--base-url` is the canonical address, used only for each page's canonical link, the sitemap, and `llms.txt`. edgible-org/cards' site job runs it and publishes the result.

```bash
git show origin/test-status:status.json > _status.json
../card-kit/run card-site --out _site --status _status.json --base-url https://cards.edgible.org
```

### check-map

Checks the skill's [needs map](skills/edgible-cards/needs-map.yaml): every entry has its fields, a fit rating, and both exposure choices. Each category must still be a category in awesome-selfhosted's data, unless the entry has `source: edgible` (a category Edgible added, mostly for AI tools, which must say in `find` where its apps come from), and each card it names must exist in edgible-org/cards. It notes a card that no entry names, so a new one gets a place in the map. It reads those sources over the network, and the kit's CI runs it on every pull request.

```bash
./run check-map
```

### check-env

Checks a fetched card against the machine it is about to run on, after `card.env` is edited and before the containers start. A card README fetches it on its own:

```bash
curl -fsSLo check-env.py https://raw.githubusercontent.com/edgible-org/card-kit/main/check-env.py
python3 check-env.py website
python3 check-env.py website -f kuma-compose.yml
```

Compose resolves each file with `card.env`, so the ports and names it checks are the ones `docker compose up` would use. When `card.yml` has `places:`, a Sizing section compares them with the machine: memory from `docker info`, less what the containers already running use; CPU type; free disk where Docker keeps its data; a GPU when a place requires one; and the architectures each image is published for. What can never work here is a conflict: no image build for this CPU, a required GPU missing, more memory than Docker has in total, or less free disk than the minimum. A card that fits in total but not alongside what is already running is a warning. Each Docker and `edgible` call has a two-minute limit, and one that does not answer stops the check, naming the command. It looks for empty required values, host ports already in use, container names already taken, Compose project names used by another file, volumes left by an earlier run, `DEVICE` values that match no device, and Edgible apps with the same name. Each conflict prints a remedy. `--project-prefix <prefix>` checks each Compose file as project `<prefix><file stem>` instead of its `name:`, as `test-card` runs it.

A Notes section adds what is worth knowing but is not a problem: a service the card starts that already runs elsewhere on the machine, an image tag such as `latest` that moves with each release, and where each service's healthcheck comes from. Notes never count as conflicts or warnings.

The report ends with the remedies as lines to paste into a shell. A value that `card.env` says how to generate is generated there, and a taken port moves to a free one. All `card.env` edits are one `sed`, so `card.env.bak` is the copy from before them. A line that stops or deletes something starts with `#`. `--commands` prints only those lines, for `> fix.sh`. Exit 0 means no conflicts, 1 means at least one, and 2 means the check could not run.

It needs only `python3` and Docker, and uses `edgible` when that is installed and logged in.

### test-card

Tests a card's whole lifecycle on a serving device and writes `test.yml`. Like `check-env`, it checks the machine, so it runs directly with `python3`, from the directory that holds the card, and `run` refuses it.

```bash
python3 ../card-kit/test-card.py gitea --device macbookair
```

It works on a copy of the card, through the same steps a person follows. Places with no app start after Verify, and `--check NAME=COMMAND` (repeatable) runs a card's own check after that, retrying until it passes or `--check-wait` runs out; `card.env` is exported, and `HOSTNAME_<APP>` holds each published hostname.

1. **Check:** runs `check-env` with `--project-prefix`, so it checks the test's own Compose projects and a copy of the card already running on the machine is no conflict. It fills empty secrets the way `card.env` says, moves a taken host port, and stops on a conflict. Publish and Verify use the moved port, not the one in `card.yml`.
2. **Start:** `up --wait`, as its own Compose project (`cardtest-<card>-<file>`), so a test never touches the machine's own containers or volumes.
3. **Prepare:** the card's [`prepare.sh`](#prepare), when it has one. `$COMPOSE` is the test's compose command; `card.env` is exported. `--prepare COMMAND` runs a command in its place.
4. **Publish:** each app in `card.yml`. A name already taken in the org is published as `test-<name>`, and the existing app is never touched.
5. **Verify:** each hostname by its auth mode. `none` answers, `org` redirects to the Edgible sign-in, `api-key` answers `401`, and `tcp` connects. `udp` is skipped. It asks Edgible's own nameservers for the address, because resolvers keep a "does not exist" for 15 minutes when a new name is looked up too early.
6. **Fingerprint:** when `card.yml` has `data.fingerprint`, it runs it after the checks (which may have added data) and records `steps.fingerprint` and the line it printed as `fingerprint:` in `test.yml`. A line that is not one JSON object of counts and ISO dates fails the run.
7. **Tear down:** deletes the apps it published, and removes the containers and volumes it started, and nothing else.

While it runs, it measures each place: the peak memory of its containers together, its images, and its data at the end. It writes `test.yml` with `measured:`, unless nothing material (the result, a step, the images) changed since the last one. It prints a suggested `places:`: memory with half again as headroom, at least 256 MB; disk as images and data plus 1 GB; the architectures every image has. `--write-places` writes that into `card.yml`. Raise a number if the app documents a higher minimum.

`--org-label` is read off an app the org already has, if you leave it out. `--by agent` marks a run made by an agent. `--keep` leaves the card running and published after Verify. It needs `dig` and `edgible`, logged in, besides Docker.

### test-cards

Tests every card in a repo that carries `test.yml` and needs a test, one at a time, and keeps a status for each: the command a CI job runs. That is every app card, and each pattern that has a test. Like `test-card`, it runs with `python3` on a serving device, from the repo's root.

```bash
python3 ../card-kit/test-cards.py --device macbookair --status ../status
```

A card needs a test when it has no status yet, when its files changed since its last status, or when `edgible --version` differs from the version of its last status, so a new Edgible version retests every card. `--all` tests every card, and `--only gitea immich` tests those. `--spread 7` spreads the work over a week: a new or changed card is tested at once, a card that failed is tested again the next day (and every day until it passes), and any other test (a new Edgible version, or a week without one) waits for the card's turn, card *i* on day *i* mod 7, so each card is also retested weekly and a night tests about a seventh of the cards.

The status directory holds `status.json`, every card's latest result, Edgible version, date and fingerprint, and one `<card>.json` per card in the shape of a [shields.io endpoint badge](https://shields.io/badges/endpoint-badge), labelled with the Edgible version it ran on: `Edgible 1.4.6 | passing`. Keep the directory on a branch of its own, such as `status`, and a README can show each card's badge from it without a commit to `main`.

It never changes the repo. `test.yml` is the author's record of a version of a card, and the status is CI's record of whether it still passes. It exits 1 when a card it tested failed.

A fleet of machines splits the work, and `test-card` does not change. `--plan FILE` tests nothing: it writes the cards due as a GitHub Actions matrix, one job per card, with the runner labels each job needs. Cards that publish an app of the same name, such as `gitea` and `ci`, share a job, so two machines never publish it at once. Each job runs `test-cards.py --only` on its cards with a status directory of its own, and `--merge DIR...` copies those results into the status. Each result records the `device` it ran on.

```bash
python3 ../card-kit/test-cards.py --status ../status --spread 7 --plan plan.json --machines runners.json
python3 ../card-kit/test-cards.py --status ../status --merge results/*
```

The labels come from the card's `places:`. Every job needs `self-hosted` and `edgible-test`, the label of a machine that tests cards. test-card runs every place on one machine, so their memory is added up. More than 1 GB needs the next `mem-<n>g` label up (2, 4, 8, 16, 32 or 64), and a machine carries the label of every tier it meets: `mem-2g,mem-4g,mem-8g` on a 9 GB one. A card whose `arch` leaves out `amd64` or `arm64` needs the other (`ARM64` or `X64`, GitHub's own labels), `gpu: required` needs `gpu-nvidia`, and a card that publishes a `tcp` or `udp` app needs `tcp`: a machine whose Edgible agent forwards those to `127.0.0.1`, where every card binds them. The Linux agent does not yet, so only macOS machines carry it. `--machines` is a JSON list of the label lists of the machines online; a card none of them can run is left out with "no machine online", rather than waiting for one. The plan has no `edgible` to ask, so it compares with `--cli`, or the newest version in the status.

### backup-card

Backs up a running card's data on the machine that runs it, the way its [`data:`](#data) says. Like `test-card`, it runs with `python3`, and `run` refuses it. Give it the directory the card runs from.

```bash
python3 ../card-kit/backup-card.py ~/linkding --dry-run
python3 ../card-kit/backup-card.py ~/linkding
```

1. **Dumps:** each irreplaceable volume with a `dump` runs its command in its service while the app stays up, and keeps what the command writes as `<volume>.dump`.
2. **Fingerprint:** it runs `data.fingerprint` after the dumps and before any stop, so the fingerprint describes the data the copies hold.
3. **Copies:** for each irreplaceable volume without a dump, it stops the running services that mount it, copies the volume to `<volume>.tgz`, and starts them again with `--wait`. This is the outage, and it records how long it lasted. Other services keep running.
4. **Skipped:** rebuildable and cache volumes are listed, not copied. A volume another place runs on another machine is listed as not here: back it up there.
5. **The card:** it copies the card's files with `card.env` (mode 600), because the copies need its passwords.

It writes everything to `<card dir>-backups/<YYYYmmdd-HHMM>/`, or to `--to`, with `backup.json`: the card, when and where the backup was taken, the Edgible version, the card's files hash, the fingerprint, the outage, and each volume's class, method, file, size and sha256. The directory is named `.partial` until the backup is whole. `--dry-run` says what it would copy and how, which services would stop, and whether the disk has room, and changes nothing. A card with volumes and no `data:` is refused, and so is one whose volumes are not on the machine; a card with no volumes is backed up as its files and `card.env`.

A copy on the same machine does not survive the loss of that machine: copy the directory somewhere else too.

### restore-card

Restores a backup that `backup-card` wrote, over the card or as a copy beside it, and then runs `verify-card` against it. It runs with `python3` on the machine that will run the card.

```bash
python3 ../card-kit/restore-card.py ~/linkding-backups/20261018-1001 ~/linkding-copy --as linkding-copy
python3 ../card-kit/restore-card.py ~/linkding-backups/20261018-1001 ~/linkding
python3 ../card-kit/restore-card.py ~/linkding-backups/20261018-1001 ~/linkding-new --as linkding-new --move
```

1. **Check:** every file against its sha256 in `backup.json`. A file that differs stops it.
2. **A copy, with `--as NAME`:** the card goes into a new directory with its own Compose project, and container names when the card sets them, named after `NAME`. Each `*_PORT` in `card.env` that is taken moves to the next free port. The running card is never touched. This is how a move restores under a temporary name before the switch. A `*_URL` in `card.env` keeps its value: change it if the copy will be published.
3. **New, without `--as`, into a directory that is empty or not there yet:** the card under its own name, as on the machine a move goes to. It refuses when the machine already has the card's volumes. A taken `*_PORT` still moves.
4. **In place, without `--as`:** it asks first (`--yes` skips the question, and a run with no terminal needs it), backs the card up with `backup-card` (`--no-backup` skips that, when the data is already lost), stops the card, and removes the volumes it restores. The card's `card.env` before the restore is kept as `card.env.before-restore-<stamp>`.
5. **Volumes:** it creates them, loads each `.tgz`, starts each dump's service alone and feeds the dump to its `restore` command, and leaves rebuildable and cache volumes empty for the app to rebuild.
6. **Secrets, with `--move`:** on the target of a move (with `--as`, or into a new directory), each secret in `secrets:` follows its `on-move` rule. `carry` keeps it. `new` drops it, so the card's `<card>-secrets` service makes a fresh one at start. `new-then-update` makes a fresh one too, then runs its `update` command in its service, which reads the new value from `/run/card-secrets` there, so the data takes it. A move then rotates every secret the data does not need. Without `--move`, as in a restore after a loss, every secret comes back as it was.
7. **Start and verify:** `up --wait`, then `verify-card --against` the backup. Its exit is restore-card's. A one-shot service, such as `<card>-secrets`, passes when it ran and exited 0.

`--dry-run` checks the files and says what it would do, and changes nothing.

### verify-card

Checks that a card runs on the machine and, with `--against` a backup, that it holds the same data.

```bash
python3 ../card-kit/verify-card.py ~/linkding-copy --against ~/linkding-backups/20261018-1001
```

**Running:** every service of each Compose file on the machine is running, and healthy when it has a healthcheck. **Answering:** every TCP port it publishes accepts a connection. **Fingerprint:** it runs `data.fingerprint`. With `--against`, the line must equal the one in `backup.json`, the proof that the data came back whole; when they differ it prints both. It exits 1 when a check fails.

## Agent skill

[skills/edgible-cards](skills/edgible-cards/SKILL.md) teaches an AI agent to self-host with Edgible the way this README says. It finds a card that fits. When the person describes a need that none meets, it shortlists apps from awesome-selfhosted for them to choose from. It puts the open choices to the person. Then it deploys and verifies by the card's README. After that, it answers what is running and whether it works, troubleshoots, and handles sign-in and API keys, settings, pausing, backup and restore, upgrades, moves, and removal. It also sets Edgible itself up on a machine that has none, the CLI, the sign-in and the device, and upgrades it. When nothing fits, it builds an app card and tests it with `test-card`, and with the person's yes it offers the card, or a fix, as a pull request. It is a plain `SKILL.md` in the open Agent Skills format, with shell commands only, so agents that read that format can use it.

Most people describe a need, not an app. [needs-map.yaml](skills/edgible-cards/needs-map.yaml), next to the skill, maps needs to a self-hosted answer. Each entry is an awesome-selfhosted category, or a category Edgible added where that list has none yet, mostly AI tools, with the needs people describe in their own words, the services they leave, why they self-host it, how well it suits Edgible, how to publish it (including when the data is sensitive), what the machine needs, its cards, and the questions that change the answer. A new card gets its place in the map in the same pull request. `check-map` checks it.

[EXAMPLES.md](skills/edgible-cards/EXAMPLES.md) shows what to ask, with what a good answer does, and [evals/](skills/edgible-cards/evals/) holds the same prompts for testing the skill.

For Claude Code, clone this repo and link the skill into your skills directory. A `git pull` then updates it:

```bash
git clone https://github.com/edgible-org/card-kit ~/.card-kit
mkdir -p ~/.claude/skills
ln -s ~/.card-kit/skills/edgible-cards ~/.claude/skills/edgible-cards
```

For another agent, put the `edgible-cards` directory where that agent reads skills.

The skill links here for the format rather than copying it. A change to the format or a tool that changes what a person does goes into the skill in the same pull request.

## MCP server

[edgible-mcp](edgible-mcp/README.md) gives an MCP client read-only tools: `find` searches the cards and the needs map for a need, `describe` shows one card, and `whats_running` lists the apps of your Edgible organization and checks that each hostname answers the way its auth mode says. With `--allow-write` it also deploys, moves and removes app cards on any device of the organization, asking first and recording each change. Run it locally over stdio, or over HTTP behind the `mcp-signin` card for Claude's web, desktop and phone apps; its image is `ghcr.io/edgible-org/edgible-mcp`.

[mcp-signin](mcp-signin/README.md) puts Sign in with Edgible in front of any MCP server, so Claude on the web and phone can use a server on your own machine as a connector, and only members of your Edgible organisation (or the people you list) get in. Its image is `ghcr.io/edgible-org/mcp-signin`.

## License

[MIT](LICENSE).
