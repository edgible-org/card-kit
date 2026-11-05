// MCP Apps views: small HTML pages that hosts supporting the MCP Apps extension (Claude, Claude
// Desktop, VS Code Copilot, and others) show inside the chat, beside a tool's text answer. Hosts
// without it ignore them and show the text, which stays complete on its own.
// Spec: https://modelcontextprotocol.io/extensions/apps/overview (protocol 2026-01-26).
// Each view is one self-contained page in views/: no external scripts, styles or fonts. The cards
// view shows each card's icon from cards.edgible.org, so its resource declares that domain (CSP).
// card-kit's status-page.py shows the whats-running page outside any host, with the data written
// in, for agents without MCP Apps.
import { readFileSync } from 'node:fs';

export const UI_MIME = 'text/html;profile=mcp-app';
const view = (file) => readFileSync(new URL(`./views/${file}`, import.meta.url), 'utf8');

export const WHATS_RUNNING_URI = 'ui://edgible/whats-running.html';
export const WHATS_RUNNING_HTML = view('whats-running.html');

export const CARDS_URI = 'ui://edgible/cards.html';
export const CARDS_HTML = view('cards.html');
// Images (the card icons) may load from the cards site; nothing else, and no connections.
export const VIEW_CSP = { resourceDomains: ['https://cards.edgible.org'] };
