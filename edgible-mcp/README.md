# edgible-mcp

An MCP server for Edgible: it finds cards for a need, and sees and looks after the apps of your Edgible organization. It is read-only unless you start it with `--allow-write`.

Read-only tools, always on:

- **find** searches the cards in [edgible-org/cards](https://github.com/edgible-org/cards) for a need described in plain words ("somewhere for my bookmarks", "Pocket shut down") or an app name. It returns the matching cards and the [needs map](../skills/edgible-cards/needs-map.yaml) entries: how well the need suits Edgible, the auth mode to publish with, what the machine needs, and the questions that change the answer.
- **describe** shows one card: its apps, images, ports, auth mode per hostname, minimum machine, test status, and its README's Why and What.
- **whats_running** lists the devices and published apps of the Edgible organization that the local Edgible CLI is signed in to. It checks that each https hostname answers the way its auth mode says, and for one app it adds `edgible app doctor`'s verdict. It needs the CLI signed in; find and describe do not.

Write tools, with `--allow-write` (or `EDGIBLE_MCP_ALLOW_WRITE=1`):

- **deploy_card** runs an app card on any device of the organization, with no shell on that device: the card becomes one self-contained Compose file (its `card.env` choices written in, the small files it mounts carried inside), which Edgible runs there as a managed docker-compose app. It deploys with `edgible stack deploy` and a declaration, not `edgible app create docker-compose`, which first runs `docker compose up` on the machine the CLI runs on. It takes app cards, and pattern cards that publish one app from one machine (such as edgible-agent), with no native install and no directory mounts. A card that declares its secrets (card.yml `secrets:`) makes them on the device, so no value is ever in the Compose file. For a password a person needs, such as an admin's, deploy_card makes a first-use one and hands it to the card through an Edgible organization secret (`<app>-first-use`, deleted with the app). It returns the password once, as `firstUse`, for the person to change at first sign-in. A key the person brings, such as a model's API key, is an Edgible organization secret they store once on a computer with the CLI (`edgible secret set gemini --from-file key=<file>`); deploy_card takes it by reference (`keys: {"GEMINI_API_KEY": "gemini:key"}`) and Edgible hands the value to the device, so it never passes through the conversation. **list_keys** names the stored secrets, never their values. **request_key** returns a one-time link, for 10 minutes, to a page where the person pastes a key from any device, even a phone: edgible-mcp stores it with `edgible secret set` and the assistant never sees it. The page is served at `/pages/key` in HTTP mode, reached through mcp-signin's `/pages/` on its sign-in address; `EDGIBLE_MCP_PAGES_URL` is that address plus `/pages`, as the edgible-connector pattern sets it. Without it, request_key answers with the CLI command instead. **gateway_key** makes a key for one app on a shared AI gateway (the litellm card, its API published as `litellm-api`), with a budget, and stores it as the organisation secret `<app>-gateway`, so deploy_card passes it to the app by reference and nobody sees it. It needs `EDGIBLE_MCP_GATEWAY_URL`, the gateway's API address, and the gateway's master key, which this server keeps for itself: `request_key` with `keep: "server"` gives the person a link to paste it, and it is kept under `EDGIBLE_MCP_STATE/keys`, readable by this server alone. **sign_in** signs this server's own Edgible CLI in without a shell: when it is not signed in, it starts the CLI's no-browser sign-in and gives the link and code for a person to approve from any device, a phone too. An agent with edgible-mcp beside it, such as the edgible-agent pattern deployed from a phone, gets signed in that way. **whoami** tells the assistant who is asking, by the email they sign in to Edgible with, and which Edgible account the tools act as: so a card setting that names Edgible accounts, such as openclaw's `OPENCLAW_USERS`, gets the right address. Cards that still keep secrets in `card.env` are refused with the reason.
- **move_card** moves such an app to another device with `edgible app move`, and **remove_card** removes one these tools deployed.
- **card_status** and **activity** show the apps these tools manage, and what they did.

Every change answers "needs confirmation" first, with the reasons to put to the person, and goes ahead only when called again with their agreement. Every change is written to a record (`activity.jsonl` under `EDGIBLE_MCP_STATE`, default `~/.edgible-mcp`), with who asked for it. `EDGIBLE_MCP_DEVICES` (device names, comma separated) limits changes to those devices, such as a test machine. The tools need the `edgible` CLI signed in, and `docker` with Compose for deploy_card.

It fetches the cards and this repo from GitHub's main branch and caches them for 15 minutes (`EDGIBLE_MCP_CATALOG_TTL`, in seconds).

## Run it

On your own machine, with Node 20 or later, and for whats_running and the write tools the `edgible` CLI, signed in with `edgible auth login`:

```bash
git clone https://github.com/edgible-org/card-kit ~/.card-kit
cd ~/.card-kit/edgible-mcp && npm ci --omit=dev
claude mcp add edgible-cards -- node ~/.card-kit/edgible-mcp/edgible-mcp.mjs
```

Add `--allow-write` at the end for the write tools, once you trust the setup. For another MCP client, the command is `node`, with the arguments `<path>/edgible-mcp.mjs` (and `--allow-write`). A desktop app needs the full path to `node`: it does not read the shell's `PATH`. The Edgible CLI has its own MCP server too, `edgible mcp`, for an app's status, logs and changes; the two work side by side.

`--http <port>` serves the same tools over Streamable HTTP at `/mcp`, on 127.0.0.1 unless `--host` says otherwise. It has no sign-in of its own. To use it from Claude's web, desktop and phone apps, run it behind the [mcp-signin card](https://github.com/edgible-org/cards/tree/main/mcp-signin), which signs people in with Edgible and passes on who they are in `X-MCP-User`, written to the record. For a client that sends a header, such as Claude Code, the [edgible-mcp card](https://github.com/edgible-org/cards/tree/main/edgible-mcp) publishes it on Edgible's `api-key` auth. Never publish it on `none`. Anyone who reaches it acts as the account its CLI is signed in to, so sign that CLI in as an account that may do what you allow.

## The image

[Dockerfile](Dockerfile) puts this server, the pinned Edgible CLI, and Docker's CLI with Compose (which `docker compose config` needs, with no Docker daemon) on `node:22-alpine`, and runs `edgible-mcp --http 8000`. The CLI keeps its sign-in in `/login`, and the write tools their record in `/data`. The [mcp-image](../.github/workflows/mcp-image.yml) workflow builds it for amd64 and arm64 on every pull request that changes this directory, and on main publishes it as `ghcr.io/edgible-org/edgible-mcp:<version>`, from `package.json`. A published version is never replaced: a change raises the version in `package.json` and in `server.mjs`.
