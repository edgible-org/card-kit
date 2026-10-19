# Image for the mcp-signin card: Sign in with Edgible in front of any MCP server. The
# mcp-image workflow publishes it as ghcr.io/edgible-org/mcp-signin:<version in package.json>.
FROM node:22-alpine

LABEL org.opencontainers.image.source=https://github.com/edgible-org/card-kit
LABEL org.opencontainers.image.description="Sign in with Edgible in front of any MCP server"
LABEL org.opencontainers.image.licenses=MIT

WORKDIR /opt/mcp-signin
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund && npm cache clean --force
COPY server.mjs oauth.mjs ./

# Tokens, kept hashed: the card's volume mcp-signin-data.
RUN mkdir -p /data && chown node:node /data
USER node
EXPOSE 8000 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD wget -qO- http://127.0.0.1:8000/healthz | grep -q ok
CMD ["node", "/opt/mcp-signin/server.mjs"]
