const { inspectBuffers } = require('./submission-preflight');

// Heartbeat metadata only. Never read document text, save files or submit code.
async function reportBuffers(vscode, token, bindings, send) {
  if (!vscode.workspace.isTrusted || vscode.env.remoteName) return;
  const roots = (vscode.workspace.workspaceFolders || []).filter(f => f.uri.scheme === 'file').map(f => f.uri.fsPath);
  for (const binding of bindings) {
    if (!roots.includes(binding.root)) continue;
    const status = inspectBuffers(binding.root, vscode.workspace.textDocuments);
    await send('/v2/pairings/workspaces/buffers', {
      token, bindingId: binding.id, dirtyPaths: status.dirty.map(p => p.split(require('node:path').sep).join('/')),
      untitled: status.untitled, trusted: true, local: true,
      ...(typeof binding.checkId === 'string' && /^[a-f0-9]{32}$/.test(binding.checkId) ? {checkId: binding.checkId} : {})
    });
  }
}

function registerBufferSync(vscode, context, send) {
  let token, bindings = [], running = false, again = false, disposed = false;
  async function sync() {
    if (disposed || !token || !bindings.length) return;
    if (running) { again = true; return; }
    running = true;
    try { await reportBuffers(vscode, token, bindings, send); }
    catch { /* Server-side freshness expires; never report failure as clean. */ }
    finally {
      running = false;
      if (again && !disposed) { again = false; void sync(); }
    }
  }
  const timer = setInterval(() => { void sync(); }, 2000);
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument(() => { void sync(); }),
    vscode.workspace.onDidSaveTextDocument(() => { void sync(); }),
    vscode.workspace.onDidCloseTextDocument(() => { void sync(); }),
    vscode.workspace.onDidOpenTextDocument(() => { void sync(); }),
    { dispose() { disposed = true; token = undefined; bindings = []; clearInterval(timer); } }
  );
  return {
    update(nextToken, nextBindings) { token = nextToken; bindings = nextBindings; void sync(); },
    clear() { token = undefined; bindings = []; }
  };
}

module.exports = { reportBuffers, registerBufferSync };
