const test = require('node:test');
const assert = require('node:assert/strict');
const { reportBuffers } = require('../src/buffer-report');
const { registerBufferSync } = require('../src/buffer-report');

test('background sync reacts to edits and stops on disposal', async () => {
  const callbacks = {};
  const workspace = { isTrusted: true, workspaceFolders: [{uri: {scheme: 'file', fsPath: '/project'}}], textDocuments: [] };
  for (const event of ['onDidChangeTextDocument', 'onDidSaveTextDocument', 'onDidCloseTextDocument', 'onDidOpenTextDocument']) {
    workspace[event] = callback => { callbacks[event] = callback; return {dispose() {}}; };
  }
  const context = { subscriptions: [] }, calls = [];
  const sync = registerBufferSync({workspace, env: {}}, context, async (_, body) => calls.push(body));
  try {
    sync.update('token', [{id: 'binding', root: '/project'}]);
    await new Promise(resolve => setImmediate(resolve));
    workspace.textDocuments = [{isDirty: true, isUntitled: false, uri: {scheme: 'file', fsPath: '/project/main.py'}}];
    callbacks.onDidChangeTextDocument();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(calls.at(-1).dirtyPaths, ['main.py']);
    sync.clear();
    const count = calls.length;
    callbacks.onDidSaveTextDocument();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls.length, count);
  } finally { context.subscriptions.forEach(item => item.dispose()); }
});

test('reports only bound local buffer metadata without reading content', async () => {
  const vscode = { env: {}, workspace: { isTrusted: true, workspaceFolders: [{uri: {scheme: 'file', fsPath: '/project'}}],
    textDocuments: [{isDirty: true, isUntitled: false, uri: {scheme: 'file', fsPath: '/project/main.py'},
      getText() { throw new Error('must not read'); }}] } };
  const calls = [];
  await reportBuffers(vscode, 'token', [{id: 'binding', root: '/project'}, {id: 'other', root: '/outside'}],
    async (route, body) => calls.push({route, body}));
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].body.dirtyPaths, ['main.py']);
  assert.equal(calls[0].body.content, undefined);
  vscode.workspace.isTrusted = false;
  await reportBuffers(vscode, 'token', [{id: 'binding', root: '/project'}], async () => assert.fail('untrusted'));
});
