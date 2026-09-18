const { randomBytes } = require('node:crypto');
const { inspectBuffers } = require('./submission-preflight');
const commands = Object.freeze({ connect: 'trainer.connect', bind: 'trainer.bindWorkspace', check: 'trainer.submissionPreflight', refresh: 'trainer.connectionStatus', disconnect: 'trainer.disconnect' });
function commandFor(value) { return typeof value === 'string' && Object.hasOwn(commands, value) ? commands[value] : undefined; }
function registerSidebar(vscode, context) {
  let view, busy = false;
  let state = { label: '正在检查连接', detail: '等待本地服务响应', checking: true };
  function update() {
    const supported = vscode.workspace.isTrusted && !vscode.env.remoteName;
    if (view) void view.webview.postMessage({ ...state, busy, roots: (vscode.workspace.workspaceFolders || []).map(f => ({ name: f.name, path: f.uri.fsPath,
      saving: supported && f.uri.scheme === 'file' ? inspectBuffers(f.uri.fsPath, vscode.workspace.textDocuments) : null })) });
  }
  context.subscriptions.push(vscode.window.registerWebviewViewProvider('trainer.overview', {
    resolveWebviewView(value) {
      view = value;
      value.webview.options = { enableScripts: true, localResourceRoots: [] };
      const nonce = randomBytes(18).toString('hex');
      value.webview.html = html(nonce);
      context.subscriptions.push(value.webview.onDidReceiveMessage(async message => {
        if (message?.action === 'ready') return update();
        if (message?.action === 'check') return update();
        const command = commandFor(message?.action);
        if (!command || busy) return;
        busy = true; update();
        try { await vscode.commands.executeCommand(command); }
        catch { state.detail = '操作未完成，请重试或查看 VS Code 通知。'; }
        finally { busy = false; update(); }
      }), value.onDidDispose(() => { if (view === value) view = undefined; }));
    }
  }), vscode.workspace.onDidChangeWorkspaceFolders(update));
  let timer;
  const schedule = () => { clearTimeout(timer); timer = setTimeout(update, 250); };
  context.subscriptions.push(vscode.workspace.onDidChangeTextDocument(schedule), vscode.workspace.onDidSaveTextDocument(schedule), vscode.workspace.onDidCloseTextDocument(schedule), { dispose() { clearTimeout(timer); } });
  return (text, detail, checking = false, connection = state.connection, bindings = state.bindings || []) => {
    state = { label: text.replace(/\$\([^)]+\)\s*/g, ''), detail: detail || '', checking, connection, bindings };
    update();
  };
}
function html(nonce) {
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';"><style nonce="${nonce}">
*{box-sizing:border-box}body{margin:0;padding:18px 14px;color:var(--vscode-foreground);font:13px var(--vscode-font-family);background:var(--vscode-sideBar-background)}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}h1{font-size:21px;letter-spacing:-.6px;margin:0}small,.muted{color:var(--vscode-descriptionForeground)}.tag{font-size:10px;letter-spacing:1.5px;margin-bottom:7px}.card{border:1px solid var(--vscode-widget-border, #8884);border-radius:12px;padding:16px;margin-bottom:16px;background:var(--vscode-editor-background)}
.status{background:linear-gradient(130deg,#7568f514,transparent),var(--vscode-editor-background)}.line{display:flex;gap:10px;align-items:center}.dot{width:9px;height:9px;flex-shrink:0;border-radius:50%;background:var(--vscode-descriptionForeground)}.checking{animation:pulse 1.5s ease-in-out infinite;background:var(--vscode-progressBar-background)}@keyframes pulse{50%{opacity:.35;box-shadow:0 0 12px var(--vscode-progressBar-background)}}.online{background:#39cdb0;box-shadow:0 0 9px #39cdb066}
h2{font-size:14px;margin:0;line-height:1.5}p{font-size:12px;line-height:1.7;margin:10px 0 0;overflow-wrap:anywhere}button{font:inherit;border:1px solid transparent;border-radius:6px;cursor:pointer;padding:9px 12px;background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground)}button:hover{background:var(--vscode-button-secondaryHoverBackground)}button:focus-visible,summary:focus-visible{outline:2px solid var(--vscode-focusBorder);outline-offset:2px}button:disabled{opacity:.5;cursor:wait}.primary{background:var(--vscode-button-background);color:var(--vscode-button-foreground);width:100%;margin-top:14px}.primary:hover{background:var(--vscode-button-hoverBackground)}.icon{padding:5px 9px;font-size:18px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.project{padding:10px 0;border-bottom:1px solid var(--vscode-widget-border,#8883);overflow-wrap:anywhere}.project:last-child{border:0}.project small{display:block;margin-top:5px;font-size:11px;overflow-wrap:anywhere}
.step{display:flex;align-items:flex-start;gap:10px;margin-top:14px}.number{border:1px solid var(--vscode-widget-border,#8885);border-radius:50%;font-size:11px;width:22px;height:22px;display:grid;place-items:center;flex-shrink:0}.step p{margin:3px 0 0}.step b{font-size:12px}details{font-size:12px;color:var(--vscode-descriptionForeground);margin:18px 2px}summary{cursor:pointer}details button{margin-top:12px}footer{font-size:11px;line-height:1.7;color:var(--vscode-descriptionForeground)}@media(max-width:230px){body{padding:12px 9px}.card{padding:12px}.grid{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){.checking{animation:none}}
</style></head><body><header><div><div class="tag muted">YOUR LEARNING SPACE</div><h1>Trainer</h1></div><button class="icon" data-action="refresh" aria-label="刷新连接状态" title="刷新连接状态">↻</button></header>
<section class="card status"><div class="line"><span id="dot" class="dot"></span><h2 id="status">正在检查连接</h2></div><p id="detail" class="muted"></p><button class="primary" data-action="connect">连接 / 重新配对</button></section>
<section class="card"><div class="tag muted">工作区</div><div id="projects"></div><div class="grid"><button data-action="bind">关联课程</button><button data-action="check">检查保存状态</button></div><p class="muted">保存状态实时同步 · 此处不读取或上传源码</p></section>
<section class="card"><h2>提交路径</h2><div class="step"><span class="number">1</span><div><b>关联项目与课程</b><p class="muted">点击“关联课程”，选择后到 Trainer 确认。</p></div></div><div class="step"><span class="number">2</span><div><b>确认源码范围</b><p class="muted">在 Trainer 连接面板授权课程允许读取的文件。</p></div></div><div class="step"><span class="number">3</span><div><b>在 Trainer 一键提交</b><p class="muted">Trainer 按课程合同自动选取、去重并评判多文件；无需在 VS Code 逐个选择。</p></div></div></section>
<details><summary>连接管理</summary><button data-action="disconnect">断开当前配对</button></details><footer>本地连接 · 源码不会因配对自动上传<br>配对、源码读取、AI 外发是独立权限。</footer>
<script nonce="${nonce}">const api=acquireVsCodeApi();document.querySelectorAll('button[data-action]').forEach(b=>b.addEventListener('click',()=>api.postMessage({action:b.dataset.action})));window.addEventListener('message',({data:s})=>{document.getElementById('status').textContent=(s.connection==='connected'?'已连接 · ':'')+s.label;document.getElementById('detail').textContent=s.detail;document.getElementById('dot').className=s.checking?'dot checking':s.connection==='connected'?'dot online':'dot';document.querySelectorAll('button').forEach(b=>b.disabled=!!s.busy||(b.dataset.action==='connect'&&s.connection==='connected'));const p=document.getElementById('projects');p.replaceChildren();if(!s.roots.length){p.textContent='尚未打开本地项目';}s.roots.forEach(r=>{const d=document.createElement('div');d.className='project';const n=document.createElement('strong');n.textContent=r.name;const t=document.createElement('small');t.textContent=r.path;const save=document.createElement('p');save.textContent=!r.saving?'保存状态不可检查':r.saving.ready?'已保存 · 可回到 Trainer 一键提交':'请先保存 '+r.saving.dirty.length+' 个文件'+(r.saving.untitled?'，另有未命名文档':'');d.append(n,t,save);(s.bindings||[]).filter(b=>b.root===r.path).forEach(b=>{const result=document.createElement('p');const job=b.submission;const labels={queued:'等待评判',evaluating:'AI 正在评判…',failed:'评判失败 · 在 Trainer 重试',cancelled:'已取消'};result.textContent=!job?'尚未提交 · 在 Trainer 完成练习后提交':job.status==='completed'?(job.outcome==='passed'?'静态评审通过 · 在 Trainer 查看详情':'需要修改 · 在 Trainer 查看反馈'):(labels[job.status]||'提交状态未知');result.setAttribute('role','status');d.append(result);});p.append(d);});});api.postMessage({action:'ready'});</script></body></html>`;
}
module.exports = { registerSidebar, commandFor, html };
