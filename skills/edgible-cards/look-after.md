# Look after a running app

Part of the edgible-cards skill: read [SKILL.md](SKILL.md) first, and its [Rules](SKILL.md#rules) apply here: ask before anything that stops, deletes, upgrades or moves.

## After it is running

**Two kinds of app.** One deployed with `deploy_card` is managed by Edgible: look after it with Edgible's tools, as each section below says first, with no commands. One set up by hand from a card's README runs from a folder on its machine, and Edgible only publishes its port: `list_applications` shows it as `existing`, and its containers and `card.env` are reached with the commands below. `activity` lists the apps the tools deployed.

**Not yet a tool**, for either kind: backups and restores, a move that keeps the app's data, commands inside an app (such as showing a generated password later), and changing a managed app's `card.env` or upgrading it (`deploy_card` refuses a name that exists; the way is `remove_card`, whose data stays on the device, then `deploy_card` again with the same app name and the new choices: ask first, and back up first where you can). Edgible does not yet collect a docker-compose app's own output, so `get_application_logs` comes back empty for cards: read it on the machine (`docker logs <container>`).

An app run from a folder: the card's directory on its machine holds its `card.yml`, its Compose files, and its `card.env`. The commands below use `dir` for that directory and `f` for a Compose file in it. Run them once per Compose file when the card has several, such as the ci card's `runner-compose.yml`: the one that holds its `card.yml`, its Compose files, and its `card.env`. The commands below use `dir` for that directory and `f` for a Compose file in it. Run them once per Compose file when the card has several, such as the ci card's `runner-compose.yml`:

```bash
dir=~/umami                    # the card's directory
f=docker-compose.yml
C="docker compose --env-file $dir/card.env -f $dir/$f"
project=$($C config --format json | python3 -c 'import json, sys; print(json.load(sys.stdin)["name"])')
```

### What is running

With the tools, `whats_running`: every device and app, each hostname checked against its auth mode. Answer from it, naming each app's device, address and auth mode. For apps run from a folder, the commands below also find the folder.

From PowerShell with the device in WSL, run these through `wsl.exe -d <distro> --`, with the signed-in `edgible` ([which one](SKILL.md#where-you-are-running)), and name the Edgible device in your answer with each app's address and auth mode.

```bash
docker compose ls --all    # each Compose project, with the path of its Compose file
edgible app list           # each published app: name, port, device, status
```

The path `docker compose ls` prints leads to the card's directory, and `metadata.name` in its `card.yml` names the card. An Edgible app on the same device with the port that the card's `card.env` sets (`<APP>_PORT`) is that card's app. Once apps carry tags, `--tag card=` says so directly. A project named `cardtest-*` is left over from an interrupted `test-card` run, not a deployment. Tell the person, and remove it only if they agree.

Answer with a short table: each card, its directory, its apps with hostname and auth mode, and whether each is up.

Then show the picture, without asking: `python3 ~/.card-kit/status-page.py` (from the card-kit folder this skill is in) writes a page of every app with a green or red dot, its address, device and who can reach it, and the devices online, and opens it in the browser. It changes nothing, and needs the network (outside your tool's sandbox). End your answer with its `file://` address, from the last line it prints, as a link. From a shell in WSL for a person on Windows, add its Windows form too (`wslpath -w <the file>`, such as `\\wsl.localhost\<distro>\home\<name>\.edgible\status.html`), since a Windows browser cannot open the Linux path. In an AI app with a browser panel of its own (the Codex app, where a clicked link opens beside the chat), run it with `--no-open` and give the link only. With Edgible's MCP tools in an app that shows MCP Apps, whats_running shows the same panel in the chat, so skip this there.

### Is it working

To prove an app works, show evidence from each layer:

1. **Containers:** with the tools, `get_application_status` (each device runs the current release) or `card_status` for an app they deployed; from a folder, `$C ps` shows each service running, and healthy when it has a healthcheck.
2. **Hostnames:** each hostname answers the way its auth mode says: `whats_running` with `app`, or by hand through Edgible's nameservers as in [Deploy](deploy.md#3-deploy).
3. **The card's own checks:** the scripts its README's Verify runs, in `etc/`, and those in `test/`. Run them with `card.env` exported and `HOSTNAME_<APP>` set to each hostname: `set -a; . $dir/card.env; set +a; export HOSTNAME_UMAMI=umami.example.edgible.app`.
4. **The goal:** what the person uses it for, end to end, such as signing in, a `git push`, a workflow run, or an event that shows up on a dashboard.
5. **The data path:** `whats_running` with `app` adds `edgible app doctor`'s verdict on the deployment, certificates, and the path from the gateway to the workload; by hand, `edgible app doctor <app>`.

Report each check with its result and the evidence, such as the status code or the line printed. Do not use `test-card` for this. It tests a fresh copy of the card and publishes apps of its own, not the person's running instance.

### Something is wrong

Work from the app outwards, and stop at the first layer that is broken. With the tools, start with `list_devices` (is the device online, and when was it last seen), then `get_application_status` (its deployment history says why a deploy is stalled) and `whats_running` with `app`, then the machine-level steps below that no tool reaches.

1. **The device first.** `list_devices` (or `edgible device list`): is the app's device online, and when was it last seen? When several apps on one device fail together, or Edgible reports them `degraded`, the device is the likely cause, not the apps: ask whether the machine is asleep, its lid closed, off, or off the network, before you look at any app. A laptop that sleeps stops its apps until it wakes: see [Is the machine always-on?](setup.md#is-the-machine-always-on).
2. **Containers:** `$C ps`, then `$C logs --tail 100 <service>`; for a managed app, `docker logs <container>` on its machine.
3. **On the machine:** `curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:<port>`, with the port from `card.env`. An `https` app is plain HTTP on the machine.
4. **Edgible:** the tools above, or by hand `edgible app doctor <app>`, `edgible app events <app>`, and `edgible certs`.
5. **The machine:** Docker is running, `edgible agent status`, `edgible doctor`, and [Keep it running](setup.md#keep-it-running) after a restart.
6. **The clock, on a VM:** compare `date -u` there with the real time. These all mean a wrong clock: `Forbidden` throughout `sudo journalctl -u edgible-agent`; an app stuck waiting on its certificate while `edgible certs` shows `attempts: 0`; a sign-in code that is refused. `edgible app doctor` may blame the certificate instead. `sudo chronyc makestep` fixes it, with no restart: Edgible recovers within a few minutes. To stop it recurring, see [Make a machine](setup.md#make-a-machine).
7. **DNS:** ask Edgible's nameservers before you decide a hostname is broken. The person's resolver may still remember it as missing.

Fix the cause, then run [Is it working](#is-it-working). If the card itself is wrong, see [Fix a card or card-kit](build.md#fix-a-card-or-card-kit).

### Sign in, passwords, and keys

- **The first sign-in:** the card's README says who the admin is, in How or Verify. A card with `secrets:` lists them in `card.yml`, each with its `kind`: a `human` one is for a person, and its `for:` says what it opens. Give the person the command that shows it, such as `docker compose --env-file ~/gitea/card.env -f ~/gitea/docker-compose.yml run --rm --no-deps gitea-secrets show GITEA_ADMIN_PASSWORD`. For a card without `secrets:`, list them with `grep -oE '^[A-Z0-9_]+(PASSWORD|SECRET|TOKEN|KEY)[A-Z0-9_]*=' $dir/card.env` and give the command that shows the one line, such as `grep '^BLOGLITE_ADMIN_PASSWORD=' ~/bloglite/card.env`.
- **Changing a password** happens in the app, by its own docs. The value the card made, or the one in `card.env`, only made the first admin; `show` keeps printing that first value after a change. Never edit or delete a file in the `<card>-secrets` volume: the card's database and apps read their own secrets there.
- **An `api-key` hostname:** for another app to use it, `app_key` makes the key and stores it as an organisation secret, unseen. For a person or a client of theirs, `edgible app api-keys create --app <app> --name <who-calls-it>` prints the key once. Give it to the person and do not store it. `edgible app api-keys list --app <app>` and `delete` manage the keys.
- **An `org` hostname** lets in the members of the person's Edgible organization. `--allowed-orgs` on `edgible app update` adds other organizations.

### Change a setting

- **Auth mode, and other settings Edgible holds:** with the tools, `get_application`, then `apply_application_change` with a patch to its declaration: the first call returns the preview to put to the person. By hand, `edgible app update <app> --auth-modes org`. Ask first before changing it to `none`.
- **Their own domain:** `add_address`, which returns the `CNAME` record to add at their domain provider.
- **A value in `card.env`**, for an app run from a folder (a managed app: see Not yet a tool, above): edit it, then run `$C up -d --wait`, which recreates the services the change affects. Run `check-env` first when the change is a port.
- **Host port or hostname, by hand:** the CLI cannot change a published app's port or hostnames. Change `<APP>_PORT` (or the card's `<APP>_URL`, for the person's own domain), run `$C up -d --wait`, then `edgible app delete <app> --yes` and publish it again as in the README, with `--hostnames` for an own domain. The generated hostname comes from the app's name, so it stays the same. An own domain is one the person controls, pointed at the generated hostname with a `CNAME`: Edgible refuses any name under `edgible.com`, which is reserved for the hostnames it generates. Expect a short outage, and verify through Edgible's nameservers.
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

Some cards run an app whose source a person may want to change (teamdesk is one). A card says so with `source:` on the app in `card.yml`: `repo`, and when they are set `ref`, `path`, `dockerfile`, `dev`. The README's **Customising** section is the same method in words. Read `source` from the card the person runs, from upstream `main`, not from memory. A card with no `source:` has no code to change: say so, and if the person still wants a change, offer the app's own settings, or a fork of the app's project that they build as in [Add your own app](build.md#add-your-own-app).

1. **Find the card's directory and the running image:** [What is running](#what-is-running), then `$C config --images`. Confirm it matches `from:` in `card.yml`, and look for an `<APP>_IMAGE` line in `card.env`: if it is set, the person has customised before, and that image name is what to build on.
2. **Get the code.** Ask where it should go, and fork it for them only with a yes (`gh repo fork <repo> --clone`). Start from `source.ref` when there is one, so they begin from the code that is running. If `repo` has no Dockerfile, stop: the card is wrong, see [Fix a card or card-kit](build.md#fix-a-card-or-card-kit).
3. **Make the change in the clone.** Read the repository's own notes first (`CLAUDE.md`, `README.md`), because they hold its rules. Try it from source with `source.dev` before building an image, and run the repository's own tests and checks.
4. **Build on the machine that runs the card:** `docker build -f <dockerfile> -t <app>:custom <path>`. Give the image its own tag, never one the card pinned. Push to a registry only if the person wants it on another machine, and ask first, because a pushed image is public unless the registry says otherwise. Build for each CPU the target machine has.
5. **Back up before switching** ([Back up and restore](#back-up-and-restore)). A change that adds a migration cannot be undone by putting the old image back: the data stays at the new version. Say this before the switch, in plain words.
6. **Switch.** Set `<APP>_IMAGE=<app>:custom` in `$dir/card.env` (the card documents the line; uncomment it), then `$C up -d --wait`. The Compose file is not touched, so a later [Upgrade](#upgrade) keeps the line like any `card.env` setting. A card with `source:` but no `<APP>_IMAGE` is out of date: see [Fix a card or card-kit](build.md#fix-a-card-or-card-kit).
7. **Prove it:** [Is it working](#is-it-working), then the change itself: do the new thing in the app, as the person would.
8. **Go back** by removing the `<APP>_IMAGE` line and `$C up -d --wait`, plus the backup when the data changed.

If the change would help others, offer a pull request to the app's repository, and once its image is released, the card can point at it: [Fix a card or card-kit](build.md#fix-a-card-or-card-kit). Open nothing without a yes.

### Upgrade Edgible

- **The CLI:** `edgible upgrade --check` says whether a newer release is out, and `edgible upgrade --yes` installs it, keeping the previous version. `edgible upgrade --version <version>` installs a given one, such as the previous version to go back. A CLI installed from npm (`@edgible-team/cli`, which stopped at 1.2.25) does not upgrade this way: `npm uninstall -g @edgible-team/cli`, then install it as in [Set up Edgible](setup.md#set-up-edgible).
- **The device software upgrades itself.** Edgible sends each device its updates, and the agent checks each one, switches to it, and goes back by itself if the new version fails its health check. There is nothing to run. `edgible version` shows the CLI, the latest release, and each device's agent version. A device far behind the others, or stuck, is a question for Edgible support (support@edgible.com) before anything else.

### Move to another machine

Ask first. With the tools, `move_card` moves an app they deployed to another device, except one that keeps data in volumes: Edgible would start it empty there and leave the data behind, so it refuses, and the steps below move it with a backup. A move is a copy, then a switch, then retiring the old copy, and the old copy keeps serving until the switch. The app is down only from deleting it on the old machine to answering on the new one, about a minute or two.

1. **The new machine** is a serving device that `edgible device list` shows online, with Docker, and room for the card: compare the card's `places:` with what the machine has free. A machine that runs something else that matters needs the margin, not just the total.
2. **Copy.** With a `data:` section: run `backup-card` on the old machine, make its backup directory visible to the new one (how is the person's choice: a drive, a network share, `rsync` over SSH if they have it; Edgible does not move it, but tell them the full path and that it holds `card.env`, so it should stay private), fetch the tools there as in [Back up and restore](#back-up-and-restore), and run `restore-card <backup> <new dir> --device <the new device's name>`, which also points `card.env` at the new machine. Into a new directory it restores the card under its own name, and ends with `verify-card`: the copy must pass before the switch. Do not pass `--move`: without it every secret and login comes across as it was, which is friendlier and adds no step that can fail. Say so. If the old machine or the backup may have been exposed, tell the person that the secrets can be replaced instead (`restore-card --move` applies each secret's `on-move` rule, so people sign in again), and do that only if they want it. It has not been run on a real move. Without a `data:` section: [back up](#back-up-and-restore) by hand, copy `$dir` with its `card.env` and the backups, run `$C create` on the new machine, restore each volume, `$C up -d --wait`, and check it on `127.0.0.1`.
3. **Changes after the copy.** Anything written on the old machine after the backup is not in it. For an app people change all day, take a second backup just before the switch and restore it over the copy (`restore-card <second backup> <new dir> --yes --no-backup`): it is quick, because little has changed.
4. **Switch the hostnames:** `edgible app delete <app> --yes`, then publish again as in the README, with the new device's id. The generated hostname stays the same.
5. Run [Is it working](#is-it-working) through the hostname. Then, on the old machine, `$C down`, and keep its volumes and the backup until the person is satisfied.

### Remove

With the tools, `remove_card` removes an app they deployed, asking first; its data stays on the device, which it says. For an app run from a folder, the steps here.

First, say in one message what you will do and what stays, and wait for a yes, even when the person asked for it: "take it down" can mean stop it for now, unpublish it, or delete it with its data. Name the app and the device it is on, and say which steps you can do from here: an app on another device that runs as plain Docker Compose there (not one Edgible manages) can be unpublished from anywhere, but stopping its containers needs a shell on that device, so say who does that and how. Then follow the card's README **Tear down**, in order: Unpublish, Stop, Delete the data (it backs up each volume to `.tgz` first), and Remove the card. Ask before deleting data. Before `rm -rf` of the card, tell the person that any kept backup needs `card.env` and the `<card>-secrets.tgz` copy, which hold its passwords and keys. Remove only the apps, containers, and volumes this card made.

To take Edgible itself off a machine, once its apps are gone: `edgible uninstall` removes the device software and asks whether to delete the device from the account and remove the CLI. `--yes --delete-device --cli` does all three without asking. A device installed with `sudo` needs `sudo edgible uninstall`. Ask first: it is the machine's link to Edgible.
