// MCP Apps views: small HTML pages that hosts supporting the MCP Apps extension (Claude, Claude
// Desktop, VS Code Copilot, and others) show inside the chat, beside a tool's text answer. Hosts
// without it ignore them and show the text, which stays complete on its own.
// Spec: https://modelcontextprotocol.io/extensions/apps/overview (protocol 2026-01-26).
// Each view is one self-contained page in views/: no external scripts, styles or fonts, so it
// needs no CSP. card-kit's status-page.py shows the same page outside any host, with the data
// written in, for agents without MCP Apps.
import { readFileSync } from 'node:fs';

export const UI_MIME = 'text/html;profile=mcp-app';
export const WHATS_RUNNING_URI = 'ui://edgible/whats-running.html';
export const WHATS_RUNNING_HTML = readFileSync(new URL('./views/whats-running.html', import.meta.url), 'utf8');
