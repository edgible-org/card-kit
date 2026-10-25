// node --test gateway-provider.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import YAML from 'yaml';
import { ADDRESS_ENV, LABEL_ENV, PROVIDERS, REVISION_ENV, deployNext, gatewayKeysRefusal, patch, plan, proposal, readGateway } from './gateway-provider.mjs';

// The litellm card's settings as deploy_card writes them with no keys: nothing answers.
const empty = () => ({
  LITELLM_FAST_MODEL: 'deepseek/deepseek-chat', LITELLM_FAST_FALLBACK_MODEL: 'gemini/gemini-3.5-flash',
  LITELLM_SMART_MODEL: 'deepseek/deepseek-reasoner', LITELLM_OPEN_MODEL: 'openrouter/z-ai/glm-5.3',
  LITELLM_BEST_MODEL: 'anthropic/claude-opus-5-5', LITELLM_PRIVATE_MODEL: 'ollama/qwen2.5:7b',
  LITELLM_PRIVATE_SMART_MODEL: 'ollama/qwen3.5:27b', LITELLM_PRIVATE_URL: 'http://host.docker.internal:11434',
  DEEPSEEK_API_KEY: '', GEMINI_API_KEY: '', OPENROUTER_API_KEY: '', ANTHROPIC_API_KEY: '', OLLAMA_API_KEY: 'ollama',
});

function declaration(environment = empty(), envFrom = [{ name: 'LITELLM_MASTER_KEY', secretRef: { secret: 'gw-first-use', key: 'LITELLM_MASTER_KEY' } }]) {
  const compose = { name: 'gw', services: { litellm: { image: 'ghcr.io/berriai/litellm:v1.106.2', environment }, 'litellm-db': { image: 'postgres:17.11-alpine' } } };
  return { apiVersion: 'v3', kind: 'Application', metadata: { name: 'gw' },
    spec: { workloads: [{ name: 'main', type: 'compose', composeFile: 'base64:' + Buffer.from(YAML.stringify(compose)).toString('base64'), envFrom }] } };
}

test('a first cloud provider fills fast and smart, and leaves best, open and the private labels', () => {
  const r = plan({ provider: 'deepseek', environment: empty() });
  assert.deepEqual(r.changes, { fast: 'deepseek/deepseek-chat', smart: 'deepseek/deepseek-reasoner' });
  assert.deepEqual(r.left, []);
});

test('a second provider does not take over a label that answers; it becomes fast\'s backup', () => {
  const env = empty();
  const r = plan({ provider: 'openai', environment: env, envFrom: [{ name: 'DEEPSEEK_API_KEY' }] });
  assert.deepEqual(r.changes, { 'fast-backup': 'openai/gpt-5-mini' });
  assert.equal(r.left.map((x) => x.label).join(), 'fast,smart');
  assert.match(r.left[0].why, /backup/);
  assert.match(r.left[1].why, /already uses deepseek\/deepseek-reasoner/);
});

test('with a key already behind the backup, a second provider changes nothing but the key', () => {
  const r = plan({ provider: 'openai', environment: empty(), envFrom: [{ name: 'DEEPSEEK_API_KEY' }, { name: 'GEMINI_API_KEY' }] });
  assert.deepEqual(r.changes, {});
  assert.equal(r.left.length, 2);
});

test('naming labels sets them, even over a label that answers', () => {
  const r = plan({ provider: 'openai', environment: empty(), envFrom: [{ name: 'DEEPSEEK_API_KEY' }], labels: ['smart'] });
  assert.deepEqual(r.changes, { smart: 'openai/gpt-5' });
});

test('best is only ever filled when asked for', () => {
  assert.equal(plan({ provider: 'anthropic', environment: empty() }).changes.best, undefined);
  assert.deepEqual(plan({ provider: 'anthropic', environment: empty(), labels: ['best'] }).changes, { best: 'anthropic/claude-opus-5-5' });
});

test('"make smart use provider/model" names the label through the model', () => {
  const r = plan({ provider: 'gemini', environment: empty(), models: { smart: 'gemini/gemini-3.1-pro-preview' } });
  assert.deepEqual(r.changes, { smart: 'gemini/gemini-3.1-pro-preview' });
});

test('a provider with no defaults asks for models; a model of another provider is refused', () => {
  assert.match(plan({ provider: 'xai', environment: empty() }).left[0].why, /name one/);
  assert.match(plan({ provider: 'xai', environment: empty(), labels: ['fast'] }).error, /name one/);
  assert.match(plan({ provider: 'openai', environment: empty(), models: { fast: 'gemini/gemini-3.5-flash' } }).error, /should start with openai\//);
});

test('openrouter fills open; a cloud key never fills the private labels', () => {
  assert.deepEqual(plan({ provider: 'openrouter', environment: empty() }).changes, { open: 'openrouter/z-ai/glm-5.3' });
  assert.match(plan({ provider: 'openai', environment: empty(), labels: ['private'] }).error, /own machine/);
});

test('ollama fills the two private labels and takes an address', () => {
  const r = plan({ provider: 'ollama', environment: empty(), address: 'https://ollama.example.edgible.app' });
  assert.deepEqual(r.changes, { private: 'ollama/qwen2.5:7b', 'private-smart': 'ollama/gpt-oss:20b' });
  assert.equal(r.address, 'https://ollama.example.edgible.app');
});

test('unknown providers and labels are refused', () => {
  assert.match(plan({ provider: 'nope', environment: empty() }).error, /Known:/);
  assert.match(plan({ provider: 'openai', environment: empty(), labels: ['huge'] }).error, /not a label/);
});

test('patch sets the models, passes the key on by reference, and bumps the revision', () => {
  const out = patch(declaration(), { changes: { fast: 'openai/gpt-5-mini' }, keyEnv: 'OPENAI_API_KEY', secret: { secret: 'openai', key: 'key' }, revision: '7' });
  const { workload, environment } = readGateway(out);
  assert.equal(environment[LABEL_ENV.fast], 'openai/gpt-5-mini');
  assert.equal(environment.OPENAI_API_KEY, '${OPENAI_API_KEY}');          // never an empty string
  assert.equal(environment[REVISION_ENV], '7');
  assert.deepEqual(workload.envFrom.map((e) => e.name), ['LITELLM_MASTER_KEY', 'OPENAI_API_KEY']);
  assert.deepEqual(workload.envFrom[1].secretRef, { secret: 'openai', key: 'key' });
  assert.equal(environment.LITELLM_SMART_MODEL, 'deepseek/deepseek-reasoner');   // untouched
});

test('patch replaces an existing reference instead of adding a second', () => {
  const first = patch(declaration(), { keyEnv: 'OLLAMA_API_KEY', secret: { secret: 'ollama', key: 'key' } });
  const second = patch(first, { keyEnv: 'OLLAMA_API_KEY', secret: { secret: 'ollama2', key: 'key' }, address: 'https://o.example.app' });
  const { workload, environment } = readGateway(second);
  assert.equal(workload.envFrom.filter((e) => e.name === 'OLLAMA_API_KEY').length, 1);
  assert.equal(workload.envFrom.find((e) => e.name === 'OLLAMA_API_KEY').secretRef.secret, 'ollama2');
  assert.equal(environment[ADDRESS_ENV], 'https://o.example.app');
});

test('patch leaves the input alone and refuses what is not the litellm card', () => {
  const d = declaration();
  patch(d, { changes: { fast: 'openai/gpt-5-mini' } });
  assert.equal(readGateway(d).environment.LITELLM_FAST_MODEL, 'deepseek/deepseek-chat');
  const other = { spec: { workloads: [{ type: 'compose', composeFile: 'base64:' + Buffer.from(YAML.stringify({ services: { web: { environment: { A: '1' } } } })).toString('base64') }] } };
  assert.throws(() => readGateway(other), /not the litellm card/);
});

test('every provider default is that provider\'s own model', () => {
  for (const [name, p] of Object.entries(PROVIDERS)) for (const m of Object.values(p.models)) assert.ok(m.startsWith(name + '/'), `${name}: ${m}`);
});

test('the proposal names the labels, what is left alone, and the restart', () => {
  const r = plan({ provider: 'openai', environment: empty(), envFrom: [{ name: 'DEEPSEEK_API_KEY' }] });
  const text = proposal({ provider: 'openai', ...r });
  assert.match(text, /OpenAI/);
  assert.match(text, /fast-backup uses openai\/gpt-5-mini/);
  assert.match(text, /Left alone: fast .*smart/);
  assert.match(text, /restarts/);
});

test('a gateway deployed with no key is said to have no provider, and the next step is offered', () => {
  const t = deployNext({ apiUrl: 'https://gw-api.example.edgible.app/v1' });
  assert.match(t, /Its API is https:\/\/gw-api\.example\.edgible\.app\/v1\./);
  assert.match(t, /no AI provider yet, so it cannot answer/);
  assert.match(t, /offer gateway_provider next/);
  assert.match(t, /Add my DeepSeek key to the gateway/);
});

test('a gateway deployed with keys says so and does not claim it has no provider', () => {
  const t = deployNext({ apiUrl: 'https://x/v1', given: ['DEEPSEEK_API_KEY', 'GEMINI_API_KEY'] });
  assert.match(t, /It was given DEEPSEEK_API_KEY, GEMINI_API_KEY/);
  assert.doesNotMatch(t, /no AI provider yet/);
  assert.match(t, /gateway_check/);
});

test('either way the person is kept away from the admin page and the master key', () => {
  for (const given of [[], ['OPENAI_API_KEY']]) {
    const t = deployNext({ apiUrl: 'https://x/v1', given });
    assert.match(t, /Never show or ask for the master key/);
    assert.match(t, /do not send the person to the gateway's admin page/);
  }
});

test('keys given to a gateway deploy are refused, naming them and the way to add a provider', () => {
  const t = gatewayKeysRefusal(['DEEPSEEK_API_KEY', 'ANTHROPIC_API_KEY']);
  assert.match(t, /no provider keys \(you gave DEEPSEEK_API_KEY, ANTHROPIC_API_KEY\)/);
  assert.match(t, /added afterwards with gateway_provider, one at a time/);
  assert.match(t, /Deploy it again without keys/);
});
