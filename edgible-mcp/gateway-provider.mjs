// The AI gateway's providers: what a person's "add my OpenAI key" turns into. Pure functions
// (no network, no CLI), used by gateway_provider in write.mjs and tested in
// gateway-provider.test.mjs.
//
// The gateway answers to six labels (fast, smart, open, best, private, private-smart; fast also
// has a backup). Each label's model is a setting of the litellm card (LITELLM_*_MODEL), and each
// provider's key reaches LiteLLM in that provider's usual variable. A provider is added by giving
// the gateway its key by reference and, where it is not already served, pointing labels at it.
// Defaults only fill gaps: a label that already answers is never taken over without being asked.
//
// Default models are ones LiteLLM v1.106.2's own catalogue lists with the model name below; check
// them again when the card's LiteLLM pin moves. xai has none: the person names the models.

import YAML from 'yaml';

export const LABELS = ['fast', 'smart', 'open', 'best', 'private', 'private-smart'];

// Label (and 'fast-backup') -> the card.env setting that holds its model.
export const LABEL_ENV = {
  fast: 'LITELLM_FAST_MODEL',
  'fast-backup': 'LITELLM_FAST_FALLBACK_MODEL',
  smart: 'LITELLM_SMART_MODEL',
  open: 'LITELLM_OPEN_MODEL',
  best: 'LITELLM_BEST_MODEL',
  private: 'LITELLM_PRIVATE_MODEL',
  'private-smart': 'LITELLM_PRIVATE_SMART_MODEL',
};
export const ADDRESS_ENV = 'LITELLM_PRIVATE_URL';
export const REVISION_ENV = 'LITELLM_KEYS_REVISION';

// name -> the variable LiteLLM reads its key from, and the models a plain "add my key" can use.
export const PROVIDERS = {
  deepseek: { env: 'DEEPSEEK_API_KEY', title: 'DeepSeek', models: { fast: 'deepseek/deepseek-chat', smart: 'deepseek/deepseek-reasoner' } },
  gemini: { env: 'GEMINI_API_KEY', title: 'Google Gemini', models: { fast: 'gemini/gemini-3.5-flash', smart: 'gemini/gemini-pro-latest' } },
  anthropic: { env: 'ANTHROPIC_API_KEY', title: 'Anthropic', models: { fast: 'anthropic/claude-haiku-5-5', smart: 'anthropic/claude-sonnet-5-5', best: 'anthropic/claude-opus-5-5' } },
  openai: { env: 'OPENAI_API_KEY', title: 'OpenAI', models: { fast: 'openai/gpt-5-mini', smart: 'openai/gpt-5', best: 'openai/gpt-5.5' } },
  mistral: { env: 'MISTRAL_API_KEY', title: 'Mistral', models: { fast: 'mistral/mistral-small-latest', smart: 'mistral/mistral-large-latest' } },
  groq: { env: 'GROQ_API_KEY', title: 'Groq', models: { fast: 'groq/openai/gpt-oss-20b', smart: 'groq/openai/gpt-oss-120b' } },
  xai: { env: 'XAI_API_KEY', title: 'xAI', models: {} },
  openrouter: { env: 'OPENROUTER_API_KEY', title: 'OpenRouter', models: { open: 'openrouter/z-ai/glm-5.3' } },
  // Ollama serves the two private labels. Its key is only for an Ollama that Edgible publishes
  // from another machine (the ollama-osx card's app), reached at the address.
  ollama: { env: 'OLLAMA_API_KEY', title: 'Ollama', models: { private: 'ollama/qwen2.5:7b', 'private-smart': 'ollama/gpt-oss:20b' }, private: true },
};

// A cloud key alone fills these, if nothing answers there yet. best is never filled by default
// (the dearest), and open and the private labels are not filled by a plain cloud key.
const GAP_LABELS = ['fast', 'smart'];

export const providerOf = (model) => String(model || '').split('/')[0];

// Which key variables have a value: the ones Edgible hands the app by reference, and any the
// Compose file gives a value of its own.
export function keysPresent({ environment = {}, envFrom = [] }) {
  const set = new Set(envFrom.map((e) => e.name));
  for (const [k, v] of Object.entries(environment)) if (v !== null && v !== undefined && String(v).trim() !== '') set.add(k);
  return set;
}

// Does this label answer today? Its model's provider has a key. A local Ollama needs none.
export function served(label, { environment = {}, present = new Set() }) {
  const model = environment[LABEL_ENV[label]];
  if (!model) return false;
  const p = PROVIDERS[providerOf(model)];
  if (!p) return true;                     // a provider this table does not know: assume the person set it up
  if (p.private) return !/^https:/.test(String(environment[ADDRESS_ENV] || '')) || present.has(p.env);
  return present.has(p.env);
}

// What adding `provider` does, from the gateway's current settings.
//   labels: the labels the person named, if any; models: { label: 'provider/model' } they named.
// Returns { changes: { label: model }, address, left: [{label, why}], error }.
export function plan({ provider, environment, envFrom = [], labels, models = {}, address }) {
  const p = PROVIDERS[provider];
  if (!p) return { error: `I don't know a provider called ${provider}. Known: ${Object.keys(PROVIDERS).join(', ')}.` };
  // "Make smart use provider/model" names the label through its model.
  if (!labels?.length && Object.keys(models).length) labels = Object.keys(models);
  const present = keysPresent({ environment, envFrom });
  const ctx = { environment, present };
  const changes = {};
  const left = [];
  const named = Object.keys(models);
  for (const l of named) if (!(l in LABEL_ENV)) return { error: `${l} is not a label. The labels are ${LABELS.join(', ')}, and fast-backup.` };
  for (const l of labels || []) if (!LABELS.includes(l) && l !== 'fast-backup') return { error: `${l} is not a label. The labels are ${LABELS.join(', ')}, and fast-backup.` };
  const need = (label) => {
    const m = models[label] || p.models[label];
    if (!m) return { error: `${p.title} has no default model for ${label}; name one, such as {"${label}": "${provider}/<model>"}.` };
    if (providerOf(m) !== provider) return { error: `${m} is not a ${p.title} model; it should start with ${provider}/.` };
    return { model: m };
  };

  if (p.private) {
    for (const l of labels?.length ? labels : ['private', 'private-smart']) {
      if (!['private', 'private-smart'].includes(l)) return { error: `${p.title} serves private and private-smart, not ${l}.` };
      const r = need(l); if (r.error) return r; changes[l] = r.model;
    }
  } else if (labels?.length) {
    for (const l of labels) {
      if (['private', 'private-smart'].includes(l)) return { error: `${l} is for a model on your own machine; add Ollama for it.` };
      const r = need(l); if (r.error) return r; changes[l] = r.model;
    }
  } else if (provider === 'openrouter') {
    const r = need('open'); if (r.error) return r;
    if (served('open', ctx)) left.push({ label: 'open', why: `already uses ${environment[LABEL_ENV.open]}` }); else changes.open = r.model;
  } else {
    for (const l of GAP_LABELS) {
      if (!(l in p.models)) { left.push({ label: l, why: `${p.title} has no default model for it; name one to use it` }); continue; }
      if (served(l, ctx)) left.push({ label: l, why: `already uses ${environment[LABEL_ENV[l]]}` });
      else changes[l] = models[l] || p.models[l];
    }
    // A second provider for fast becomes its backup, if nothing backs it up yet.
    if (!changes.fast && 'fast' in p.models && served('fast', ctx) && providerOf(environment[LABEL_ENV.fast]) !== provider && !served('fast-backup', ctx)) {
      changes['fast-backup'] = models.fast || p.models.fast;
      const i = left.findIndex((x) => x.label === 'fast');
      if (i >= 0) left[i] = { label: 'fast', why: `already uses ${environment[LABEL_ENV.fast]}; ${p.title} is now its backup` };
    }
  }
  return { changes, left, address: p.private ? address : undefined };
}

// ---------- the declaration `edgible app export` prints, patched in place ----------

const decode = (b64) => Buffer.from(String(b64).replace(/^base64:/, ''), 'base64').toString('utf8');
const encode = (text) => `base64:${Buffer.from(text, 'utf8').toString('base64')}`;

// The workload and its Compose file, parsed: { workload, compose, service, environment }.
export function readGateway(declaration) {
  const workload = (declaration?.spec?.workloads || []).find((w) => w.type === 'compose' && w.composeFile);
  if (!workload) throw new Error('this app has no Compose workload');
  const compose = YAML.parse(decode(workload.composeFile));
  const service = Object.values(compose.services || {}).find((s) => s?.environment && LABEL_ENV.fast in (Array.isArray(s.environment) ? Object.fromEntries(s.environment.map((x) => x.split(/=(.*)/s))) : s.environment));
  if (!service) throw new Error('this is not the litellm card: no service sets LITELLM_FAST_MODEL');
  if (Array.isArray(service.environment)) service.environment = Object.fromEntries(service.environment.map((x) => x.split(/=(.*)/s)));
  return { workload, compose, service, environment: service.environment };
}

// Returns a new declaration with: the labels' models set, the provider's key variable passed on
// by reference (${VAR}, never an empty string, which would hide the value Edgible injects), the
// secret handed to the app, and a new revision, so the app gets a fresh release even when only a
// secret changed.
export function patch(declaration, { changes = {}, address, keyEnv, secret, revision = String(Date.now()) }) {
  const copy = structuredClone(declaration);
  const { workload, compose, service, environment } = readGateway(copy);
  for (const [label, model] of Object.entries(changes)) environment[LABEL_ENV[label]] = model;
  if (address) environment[ADDRESS_ENV] = address;
  if (keyEnv && secret) {
    environment[keyEnv] = '${' + keyEnv + '}';
    workload.envFrom = (workload.envFrom || []).filter((e) => e.name !== keyEnv);
    workload.envFrom.push({ name: keyEnv, secretRef: { secret: secret.secret, key: secret.key } });
  }
  environment[REVISION_ENV] = revision;
  service.environment = environment;
  workload.composeFile = encode(YAML.stringify(compose, { lineWidth: 0 }));
  return copy;
}

// The sentence the person is asked to agree to.
export function proposal({ provider, changes, left, address, restartSeconds = 60 }) {
  const p = PROVIDERS[provider];
  const parts = [`Add ${p.title} to the AI gateway: its key is passed on by reference and never shown.`];
  const set = Object.entries(changes);
  if (set.length) parts.push(`Labels: ${set.map(([l, m]) => `${l} uses ${m}`).join('; ')}.`);
  else parts.push('No label changes: the key is added and available.');
  if (address) parts.push(`Its address is ${address}.`);
  if (left.length) parts.push(`Left alone: ${left.map((x) => `${x.label} (${x.why})`).join('; ')}.`);
  parts.push(`The gateway restarts and does not answer for about ${restartSeconds} seconds.`);
  return parts.join(' ');
}
