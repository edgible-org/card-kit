# mcp-signin

Sign in with Edgible in front of any MCP server, so you can use a server on your own machine from Claude on the web and phone, or from any MCP client that follows the [MCP authorization spec](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization), and only the people you allow get in.

Claude's connectors call a server from Claude's own servers, with no browser, so Edgible's `org` sign-in cannot sit in front of it, and they accept OAuth, not an API key. mcp-signin is that OAuth, with Edgible doing the signing in:

1. The client calls `/mcp` and gets 401, with the address of mcp-signin's OAuth metadata. It registers itself (dynamic client registration) and opens the person's browser at `/authorize`.
2. mcp-signin sends the browser to its sign-in page, on a second address published behind Edgible's `org` sign-in. Edgible signs the person in and tells the page who they are (`X-Auth-Email`, `X-Auth-Organization-Id`); Edgible's agent deletes any `X-Auth-*` header a caller sent itself.
3. The page asks the person to allow the client, naming the client and where it will send them, so a link from someone else's client cannot sign them in silently.
4. The client gets a token for an hour, renewed in the background for 30 days, and calls `/mcp` with it. mcp-signin passes each call to the MCP server behind, with `X-MCP-User` set to the person's email.

Who may sign in: members of one Edgible organisation, or only listed email addresses. Tokens are kept hashed in `/data`, so a restart signs no one out.

## Two ports, two addresses

| Port | Edgible auth mode | Serves |
| --- | --- | --- |
| 8000 | `none` | `/mcp` (with a token), `/register`, `/token`, `/authorize`, the OAuth metadata, `/healthz` |
| 8001 | `org` | `/signin`, the page the person sees |

Publish 8001 only behind `org`: the page trusts the headers Edgible's sign-in sets.

## Settings

| Variable | Meaning |
| --- | --- |
| `MCP_UPSTREAM_URL` | The MCP server behind, such as `http://edgible-mcp:8000/mcp`. Keep it unpublished: it trusts `X-MCP-User` |
| `MCP_SIGNIN_PUBLIC_URL` | The address of port 8000, such as `https://mcp.example.edgible.app` |
| `MCP_SIGNIN_LOGIN_URL` | The address of port 8001 |
| `EDGIBLE_ORGANIZATION_ID` | The organisation whose members may sign in (`edgible whoami --json`) |
| `MCP_SIGNIN_USERS` | Optional: only these email addresses, comma separated |
| `MCP_SIGNIN_NAME`, `MCP_SIGNIN_PURPOSE` | What the consent page calls the server, and what it lets the client do |

Run it with the [mcp-signin card](https://github.com/edgible-org/cards/tree/main/mcp-signin), which publishes both addresses.

## The image

The mcp-image workflow publishes `ghcr.io/edgible-org/mcp-signin:<version>` for amd64 and arm64 when this directory changes on main. A published version is never overwritten: raise the version in `package.json` and `server.mjs` together.
