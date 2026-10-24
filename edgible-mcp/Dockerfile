# Image for the edgible-mcp card: the edgible-mcp server, the Edgible CLI it calls, and Docker's
# CLI with Compose, which deploy_card uses to resolve a card (`docker compose config`, which
# needs no Docker daemon). The mcp-image workflow publishes it as
# ghcr.io/edgible-org/edgible-mcp:<version in package.json>.
FROM node:22-alpine

LABEL org.opencontainers.image.source=https://github.com/edgible-org/card-kit
LABEL org.opencontainers.image.description="Edgible MCP server: read-only by default, write tools with --allow-write"
LABEL org.opencontainers.image.licenses=MIT

# The CLI installer needs bash and curl; whats_running and card_status use curl; tar unpacks cards.
RUN apk add --no-cache bash curl tar docker-cli docker-cli-compose

# The Edgible CLI, pinned. As root, the installer puts it in /opt/edgible-cli and /usr/local/bin.
ARG EDGIBLE_CLI_VERSION=1.4.12
RUN curl -fsSL https://get.edgible.com/install.sh \
    | EDGIBLE_CLI_VERSION=$EDGIBLE_CLI_VERSION EDGIBLE_SKIP_NODE=1 bash -s -- --yes \
 && edgible --version

WORKDIR /opt/edgible-mcp
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund && npm cache clean --force
COPY *.mjs ./
RUN chmod 755 edgible-mcp.mjs && ln -s /opt/edgible-mcp/edgible-mcp.mjs /usr/local/bin/edgible-mcp

# HOME for the CLI's sign-in (the card's volume edgible-mcp-login), and the write tools' record
# and compose files (EDGIBLE_MCP_STATE, the volume edgible-mcp-data). Only root reads them.
RUN mkdir -m 700 /login /data
ENV HOME=/login EDGIBLE_MCP_STATE=/data
WORKDIR /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s CMD wget -qO- http://127.0.0.1:8000/healthz | grep -q ok
CMD ["edgible-mcp", "--http", "8000", "--host", "0.0.0.0"]
