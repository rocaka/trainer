const test = require('node:test');
const assert = require('node:assert/strict');
const { supported, request, connectionState, workspaceSummary } = require('../src/pairing');

test('workspace summary validates counts and sends only current roots', async () => {
  assert.deepEqual(await workspaceSummary('secret', ['/project'], async (path, body) => {
    assert.equal(path, '/v2/pairings/workspaces/summary');
    assert.deepEqual(body.roots, ['/project']);
    return { linked: 1 };
  }), { linked: 1 });
  await assert.rejects(workspaceSummary('secret', [], async () => ({ linked: -1 })));
});

test('connection state distinguishes missing, valid, revoked and offline without deleting credentials', async () => {
  assert.equal(await connectionState(undefined, () => { throw Error('must not call'); }), 'unpaired');
  assert.equal(await connectionState('secret', async () => ({ connected: true, scope: 'workspace:bind' })), 'connected');
  assert.equal(await connectionState('secret', async () => { throw Object.assign(Error(), { status: 401 }); }), 'expired');
  assert.equal(await connectionState('secret', async () => { throw Error('offline'); }), 'offline');
  assert.equal(await connectionState('secret', async () => ({ connected: true })), 'offline');
});

test('reject untrusted and remote workspaces', () => {
  const local = { workspace: { isTrusted: true, workspaceFolders: [{ uri: { scheme: 'file' } }] }, env: {} };
  assert.equal(supported(local), true);
  assert.equal(supported({ ...local, env: { remoteName: 'ssh-remote' } }), false);
  assert.equal(supported({ ...local, workspace: { isTrusted: false } }), false);
});

test('local pairing requests cannot follow redirects or include native token', async () => {
  const result = await request('/v2/pairings', { name: 'VS Code' }, async (url, options) => {
    assert.equal(url, 'http://127.0.0.1:8787/v2/pairings');
    assert.equal(options.redirect, 'error');
    assert.equal(options.headers['X-Trainer-Session'], undefined);
    assert.equal(JSON.parse(options.body).name, 'VS Code');
    return { ok: true, json: async () => ({ id: 'test' }) };
  });
  assert.equal(result.id, 'test');
});

test('upstream error body cannot leak secrets in error messages', async () => {
  await assert.rejects(request('/v2/pairings', {}, async () => ({ ok: false, status: 403, json: async () => ({ error: 'SECRET' }) })), error => !error.message.includes('SECRET'));
});
