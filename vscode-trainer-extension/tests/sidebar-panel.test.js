const { test } = require('node:test');
const assert = require('node:assert/strict');
const { commandFor, html } = require('../src/sidebar-panel');
test('save refresh completes without invoking notification command', async () => {
  const { registerSidebar } = require('../src/sidebar-panel');
  let provider, listener, calls = 0;
  const disposable = () => ({ dispose() {} });
  const vscode = { workspace: { isTrusted: true, workspaceFolders: [], textDocuments: [], onDidChangeWorkspaceFolders: disposable, onDidChangeTextDocument: disposable, onDidSaveTextDocument: disposable, onDidCloseTextDocument: disposable }, env: {},
    window: { registerWebviewViewProvider(id, p) { provider = p; return disposable(); } },
    commands: { executeCommand() { calls++; return new Promise(() => {}); } } };
  registerSidebar(vscode, { subscriptions: [] });
  provider.resolveWebviewView({ webview: { postMessage() {}, onDidReceiveMessage(fn) { listener = fn; return disposable(); } }, onDidDispose: disposable });
  await listener({ action: 'check' });
  assert.equal(calls, 0);
});
test('webview messages can only invoke fixed Trainer actions', () => {
  assert.equal(commandFor('bind'), 'trainer.bindWorkspace');
  for (const action of ['__proto__', 'constructor', 'workbench.action.closeWindow', {}, null]) assert.equal(commandFor(action), undefined);
});
test('panel uses restrictive CSP and safe text rendering', () => {
  const page = html('testnonce');
  assert.ok(page.includes("default-src 'none'"));
  assert.ok(page.includes("script-src 'nonce-testnonce'"));
  assert.ok(page.includes('textContent=r.name'));
  assert.ok(!page.includes('innerHTML'));
  assert.ok(page.includes('prefers-reduced-motion'));
});
