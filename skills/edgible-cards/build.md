# Build, add, and contribute cards

Part of the edgible-cards skill: read [SKILL.md](SKILL.md) first.

## Build an app card

When nothing fits, offer to build an app card. First check the cards README's **What is not an app card** list: an open resolver or relay, an app with no maintained container image, or an archived project gets a plain no, with the reason.

1. Read the [cards README](https://github.com/edgible-org/cards#what-a-card-is) and the [card-kit README](https://github.com/edgible-org/card-kit), then copy the shape of the app card closest to the new app. Set `metadata.type: app`, `metadata.added` to today's date (`2026-10-18` form), `metadata.homepage` to the app's own site, and `metadata.license` to its SPDX licence when you have read it from the app's repository (leave it out when unsure).
2. Follow the format: pinned image versions; every variable, service and volume prefixed with the app's name; no `container_name`; each secret declared in `card.yml` `secrets:` (its kind, and for one made on the device its `make` command) and made by a `<card>-secrets` service, as card-kit's README says under Secrets, never a `card.env` value; a key the person brings is a `card.env` line, declared `external`; each hostname's auth mode chosen from the cards README's table; and `prepare.sh` when the first visitor would otherwise make the admin. When the app has source a person may change, add `source:` (the card-kit README says under Source what each field is), read the image as `${<APP>_IMAGE:-<pinned image>}` in the Compose file, and add a commented `# <APP>_IMAGE=` line to `card.env`, and write `customise:` in the README's YAML for anything particular to changing it.
3. Write the README with `card-readme`, and check the files with `check-cards` (see the card-kit README for `run`).
4. Test it on the person's serving device until it passes: `python3 test-card.py <name> --device <device> --by agent`. Put inputs only a person may fill in `test/inputs.env`, and the app's own end-to-end checks in `test/<name>.sh`.
5. Deploy it for the person from the tested files. Their app comes first, and contributing is optional.

## Add your own app

When the person built the app (often with an AI tool) and wants it on Edgible or in the catalog, there are three different goals, and they are not the same job. Ask which they want, and lead in this order, because most people stop after the first two:

1. **Get it live.** Publish it on a serving device so people can reach it: [Deploy](deploy.md#3-deploy), Publish, with `edgible app create existing` on the port the app listens on and the auth mode its callers need. A container is not needed to start.
2. **Keep it running.** For anything that should stay up, put it in a container with its data in a named volume and its secrets made on the machine, as a card of its own in their own repository ([Build an app card](#build-an-app-card)). Backups, moves and upgrades then work as for any card, and the card can stay private.
3. **Share it,** so others can run it. That is optional, and the rest of this section.

### Share it: check it is ready first

1. **Run `check-app`:** `python3 check-app.py <the app's folder> --image <name:tag> --steward <their GitHub name>` (card-kit's tool; `--json` for an agent). It lists what is **required** for a card (a public image with a version tag that runs on amd64 and arm64, a licence others can use, its settings written down, a port and a place for its data, no committed secret) and what is **nice to have** (no default password in the files, a healthcheck, a non-root user, `*_FILE` secrets, a backup note, an icon, tagged releases), with what to do for each gap. A third list, **your call**, holds who will be the steward: it never fails the check, because a card can be listed with none. Read it to the person in plain words: what must change before a card can exist, and what would make it a better one. Offer to build each missing piece (a Dockerfile, a published image for amd64 and arm64 (see **No image yet?** below), a licence, a tagged release, an `.env.example`, a healthcheck, an icon: a square logo, SVG if possible, which you can draw for them if they have none, and which a card keeps as `images/icon.svg`; without one the catalog shows the Edgible symbol). Change nothing in their app without their yes. Run it again until every required item passes. An agent working alone repeats this with `--json` until `ready` is true, and stops to ask when a required item needs a decision only the person can make, such as the licence. The steward is the person's to name too, never yours or an agent's.

   **No image yet?** Most authors who have never published one get stuck here, so walk them through it on GitHub, where their code already is. The image stays theirs, under their own name (`ghcr.io/<owner>/<repo>`), not Edgible's:

   1. Copy the skill's `publish-image.yml` into their repository as `.github/workflows/publish-image.yml`, with their yes. It builds for amd64 and arm64 on each version tag and needs no secrets. If the Dockerfile is not at the repository's root, change `context` (and add `file:`) in it. No Dockerfile at all? Write one with them first, and try it with `docker build` on this machine.
   2. Tag a release and push the tag, with their yes: `git tag v1.0.0 && git push origin v1.0.0`. Watch the run: `gh run watch` in their repository.
   3. **Check the image is public:** a card needs anyone to be able to pull it. Published this way from a public repository, it usually is already; `check-app` in the next step says so. If it is private (a private repository, or an image pushed by hand), the person makes it public on GitHub: the repository's Packages, the package, Package settings, Change visibility, Public. Say first that a public image cannot be made private again.
   4. Run `check-app` again with `--image ghcr.io/<owner>/<repo>:1.0.0`. Future releases need only a new tag.

2. **Name a steward, or none:** ask the person. It is the GitHub user or organisation that will review changes to the card and fix it when its test fails. It goes in `metadata.steward` in `card.yml`. If nobody will, say so: the card is listed as having no steward, and that is allowed.
3. **Build the app card** as in [Build an app card](#build-an-app-card), from the app's own Compose setup, with `source:` pointing at the repository that holds the Dockerfile, since the app is meant to be changed. The author knows its first-run steps, its secrets, and who calls each hostname, which decides the auth mode. Ask them rather than guess.
4. **Test it on a machine of their own** (below) until it passes.
5. **Contribute it** as in [Contribute](#contribute), and say in the pull request that the person is the app's author. Reviewers judge it by the same checklist as any card.
6. **Point to where self-hosters look.** awesome-selfhosted lists free software that meets its own inclusion rules: read its contributing guide before suggesting it. A short "Run it with Edgible" section in the app's README, linking to the card, helps people find it.

If the app is one part of a bigger setup, a pattern card that combines it with other app cards may suit better.

### Test it on a machine of their own

Test the card on a machine of theirs, signed in to their own Edgible account, never anyone else's. It can be a spare computer, or [a VM](setup.md#make-a-machine), with Docker and the Edgible agent ([Set up Edgible](setup.md#set-up-edgible)). Run `python3 test-card.py <name> --device <their device> --by person` (`--by agent` when an agent ran it). It publishes the card's apps in their own organisation under test names, checks them, and removes them. It takes a few minutes and the image downloads. A pass writes `test.yml` beside the card: who ran it, on what machine, the Edgible version, and a hash of the card's files, so a later edit shows up as stale. That is the author's own evidence. A maintainer tests the card again on Edgible's own devices before merging.

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
