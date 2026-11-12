// The Edgible CLI's own MCP server (`edgible mcp`), served through this one, so a person adds one
// Edgible connector and gets both: the cards tools here, and the CLI's tools for an app's record,
// status, logs and settings. The CLI runs as a child process, signed in as this server's CLI is.
//
// Served as the CLI defines them: list_applications, get_application, get_application_status,
// get_application_logs, list_devices, preview_application_change. Left out, because this server
// has its own: whoami, and redeploy_application (restart_card asks first and is recorded).
// With writes on, apply_application_change is served with this server's rules on top: the app's
// devices must be allowed (EDGIBLE_MCP_DEVICES), the first call returns the preview as "needs
// confirmation", and the change is written to the record.

import { z } from 'zod';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { appDevices, apps, needs, notAllowed, record, refused, text } from './write.mjs';

const SKIP = new Set(['whoami', 'redeploy_application']);
const GUARDED = 'apply_application_change';
const ENV = { ...process.env, NO_COLOR: '1', EDGIBLE_NO_UPDATE_NOTIFIER: '1', EDGIBLE_NO_INTERACTIVE: '1' };

let client = null;
let connecting = null;
let defs = [];

async function connect(allowWrite) {
  const c = new Client({ name: 'edgible-mcp', version: '1' });
  const transport = new StdioClientTransport({
    command: 'edgible', args: allowWrite ? ['mcp', '--allow-write'] : ['mcp'], env: ENV, stderr: 'ignore',
  });
  transport.onclose = () => { if (client === c) client = null; };
  await c.connect(transport);
  return c;
}

async function child(allowWrite) {
  if (client) return client;
  if (!connecting) connecting = connect(allowWrite).then((c) => { client = c; return c; }).finally(() => { connecting = null; });
  return connecting;
}

// Called once at start. Without a working `edgible` CLI the cards tools still serve, without these.
export async function loadCliTools(allowWrite) {
  try {
    const { tools } = await (await child(allowWrite)).listTools();
    defs = tools.filter((t) => !SKIP.has(t.name) && (allowWrite || t.annotations?.readOnlyHint !== false));
    return defs.map((t) => t.name);
  } catch (err) {
    console.error(`edgible-mcp: the CLI's tools are not served: ${err.message}`);
    return [];
  }
}

async function call(allowWrite, name, args) {
  let c = await child(allowWrite);
  try {
    return await c.callTool({ name, arguments: args });
  } catch (err) {
    if (client) throw err;            // the child is still up: a real error
    c = await child(allowWrite);      // the child had exited: start it again, once
    return c.callTool({ name, arguments: args });
  }
}

const resultText = (r) => (r.content || []).filter((x) => x.type === 'text').map((x) => x.text).join('\n');

async function applyChange(allowWrite, { application, patch, baseVersion, confirm = [] }) {
  const live = (await apps()).find((a) => a.name === application || a.id === application);
  if (!live) return text(refused(`no app called ${application}`));
  const where = appDevices(live);
  if (notAllowed(...where)) return text(refused(notAllowed(...where)));
  if (!confirm.includes('apply')) {
    const preview = await call(allowWrite, 'preview_application_change', { application, patch });
    if (preview.isError) return preview;
    return text({
      ...needs([{ token: 'apply', reason: `Changing ${live.name} on ${where.join(', ') || 'its device'}. Put this preview to the person in plain words, including anything marked restart, disruptive or fixed:` }]),
      preview: resultText(preview),
    });
  }
  const args = { application, patch, confirm: true, ...(baseVersion === undefined ? {} : { baseVersion }) };
  const r = await call(allowWrite, GUARDED, args);
  await record({ tool: GUARDED, app: live.name, confirmed: confirm, patch, result: r.isError ? 'failed' : 'applied', detail: r.isError ? resultText(r).slice(0, 400) : undefined });
  return r;
}

export function registerCliTools(server, allowWrite) {
  const shown = new Map();
  for (const t of defs) {
    if (t.name === GUARDED) {
      server.registerTool(t.name, {
        title: 'Change an app\'s settings',
        description: `${t.description} Through this server, the first call returns the preview as "needs confirmation": put it to the person, and call again with confirm: ["apply"] only after they agree. Changes are limited to the allowed devices and recorded.`,
        inputSchema: {
          application: z.string().min(1).describe('Application id or exact name'),
          patch: z.record(z.string(), z.unknown()).describe(t.inputSchema?.properties?.patch?.description || 'JSON Merge Patch against the declaration get_application returns'),
          baseVersion: z.number().int().optional().describe('The baseVersion the preview returned. The change is refused if the application changed since.'),
          confirm: z.array(z.string()).optional().describe('Tokens from an earlier "needs confirmation" result, only after the person agreed'),
        },
        annotations: t.annotations,
      }, async (args) => {
        try { return await applyChange(allowWrite, args); } catch (err) { return { isError: true, ...text(`Failed: ${err.message}`) }; }
      });
      continue;
    }
    // Arguments pass through as they are; the CLI checks them against its own schema.
    server.registerTool(t.name, {
      title: t.title, description: t.description, inputSchema: z.object({}).passthrough(), annotations: t.annotations,
    }, async (args) => {
      try { return await call(allowWrite, t.name, args); } catch (err) { return { isError: true, ...text(`Failed: ${err.message}`) }; }
    });
    shown.set(t.name, t.inputSchema);
  }
  // List the passed-through tools with the CLI's own input schemas, not the open one above.
  const handlers = server.server._requestHandlers;
  const list = handlers?.get('tools/list');
  if (list && shown.size) {
    server.server.setRequestHandler(ListToolsRequestSchema, async (req, extra) => {
      const out = await list(req, extra);
      for (const tool of out.tools) if (shown.has(tool.name)) tool.inputSchema = shown.get(tool.name);
      return out;
    });
  }
  return server;
}
