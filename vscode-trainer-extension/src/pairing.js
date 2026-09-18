const BASE = 'http://127.0.0.1:8787';
const SECRET_KEY = 'trainer.pairing.token';

async function request(path, payload, fetcher = fetch) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetcher(BASE + path, {
      method: 'POST', redirect: 'error', signal: controller.signal,
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw Object.assign(new Error(`Trainer 请求失败（${response.status}），请检查连接或配对状态。`), { status: response.status });
    return result;
  } finally { clearTimeout(timeout); }
}

function supported(vscode) {
  return vscode.workspace.isTrusted && !vscode.env.remoteName &&
    (vscode.workspace.workspaceFolders || []).every(folder => folder.uri.scheme === 'file');
}

async function connectionState(token, send = request) {
  if (!token) return 'unpaired';
  try {
    const result = await send('/v2/pairings/session', { token });
    return result.connected === true && result.scope === 'workspace:bind' ? 'connected' : 'offline';
  } catch (error) { return error.status === 401 ? 'expired' : 'offline'; }
}

function registerPairing(vscode, context, publish = () => {}) {
  let busy = false;
  let checking = false;
  let disposed = false;
  let refreshAgain = false;
  let connection = 'unknown';
  let bindings = [];
  const bufferSync = require('./buffer-report').registerBufferSync(vscode, context, request);
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
  status.command = 'trainer.connectionStatus';
  const labels = {
    unpaired: ['$(plug) Trainer 未配对', '运行“Trainer: 连接本地教学应用”开始配对。'],
    connected: ['$(check) Trainer 已连接', '仅配对有效，工作区尚未授权；不会上传源码。'],
    expired: ['$(warning) Trainer 连接已失效', '凭证已撤销或过期，请重新配对。'],
    offline: ['$(debug-disconnect) Trainer 不可达', '请启动 Trainer 后点击重试。保留凭证，不自动重新配对。']
  };
  async function refresh() {
    if (disposed) return;
    if (checking) { refreshAgain = true; return; }
    checking = true;
    status.text = '$(sync~spin) Trainer 检查中';
    publish(status.text, '正在查询连接与关联状态，不读取源码。', true);
    try {
      const token = await context.secrets.get(SECRET_KEY);
      const state = await connectionState(token);
      connection = state;
      bindings = [];
      if (state !== 'connected' || !supported(vscode)) bufferSync.clear();
      if (!disposed) [status.text, status.tooltip] = labels[state];
      if (state === 'connected' && supported(vscode)) {
        try {
          const roots = (vscode.workspace.workspaceFolders || []).map(folder => folder.uri.fsPath);
          const summary = await workspaceSummary(token, roots);
          bindings = summary.bindings || [];
          bufferSync.update(token, summary.bindings || []);
          if (!disposed) {
            status.text = summary.linked ? `$(check) Trainer · ${summary.linked} 个目录已关联` : '$(plug) Trainer · 当前目录未关联';
            status.tooltip = '配对连接有效；目录关联不代表已授权源码读取或 AI 外发。点击刷新。';
          }
        } catch {
          bufferSync.clear();
          if (!disposed) { status.text = '$(warning) Trainer · 关联状态未知'; status.tooltip = '请确认 Gateway 已更新并点击重试；不会将查询失败当成未关联。'; }
        }
      } else if (state === 'connected' && !disposed) {
        status.text = '$(warning) Trainer · 工作区不支持';
        status.tooltip = '仅支持可信本地工作区；未查询目录关联。';
      }
    } catch {
      bufferSync.clear();
      connection = 'unknown';
      if (!disposed) { status.text = '$(warning) Trainer 凭证不可读'; status.tooltip = '请检查系统安全存储后重试。'; }
    } finally { checking = false; if (!disposed) publish(status.text, status.tooltip, false, connection, bindings); if (refreshAgain && !disposed) { refreshAgain = false; void refresh(); } }
  }
  status.show();
  const heartbeat = setInterval(() => { void refresh(); }, 15000);
  context.subscriptions.push(status,
    vscode.commands.registerCommand('trainer.connectionStatus', refresh),
    vscode.window.onDidChangeWindowState(state => { if (state.focused) void refresh(); }),
    vscode.workspace.onDidChangeWorkspaceFolders(() => { void refresh(); }),
    { dispose() { disposed = true; clearInterval(heartbeat); } });
  void refresh();
  context.subscriptions.push(vscode.commands.registerCommand('trainer.bindWorkspace', async () => {
    if (busy) return;
    if (!supported(vscode) || !vscode.workspace.workspaceFolders?.length) {
      return vscode.window.showInformationMessage('请先打开可信的本地项目文件夹。');
    }
    busy = true;
    try {
      const token = await context.secrets.get(SECRET_KEY);
      if (!token) return vscode.window.showInformationMessage('请先连接 Trainer。');
      const folder = await vscode.window.showWorkspaceFolderPick({ placeHolder: '选择要关联的项目目录，不读取源码' });
      if (!folder) return;
      const catalog = await request('/v2/pairings/workspaces/courses', { token });
      if (!catalog.courses?.length) return vscode.window.showInformationMessage('暂无可关联课程，请先在 Trainer 生成并保存课程。');
      const course = await vscode.window.showQuickPick(catalog.courses.map(item => ({
        label: item.title,
        description: `完整课程 · ${item.lessonCount} 课${item.language ? ` · ${item.language}` : ''}`,
        detail: `课程编号 ${item.id.slice(0, 8)} · 工作区只会关联整套课程，不会上传源码`,
        planId: item.id
      })), { placeHolder: '选择要与当前工作区关联的完整课程', matchOnDescription: true, matchOnDetail: true });
      const planId = course?.planId;
      if (!planId || !supported(vscode) || !vscode.workspace.workspaceFolders.some(item => item.uri.toString() === folder.uri.toString())) return;
      const result = await request('/v2/pairings/workspaces', { token, root: folder.uri.fsPath, planId });
      const action = await vscode.window.showInformationMessage('请在 Trainer 的 VS Code 连接页刷新并确认工作区关联。', { modal: true }, '已确认，检查状态');
      if (!action) return;
      const state = await request('/v2/pairings/workspaces/status', { token, id: result.id });
      vscode.window.showInformationMessage(state.approved ? '目录与课程已关联。请在 Trainer 授权课程所需源码；完成练习后可在 Trainer 一键提交。' : '尚未确认或请求已失效，请在 Trainer 检查。');
    } catch { vscode.window.showErrorMessage('工作区关联失败，请检查配对、课程 ID 和目录；服务需更新至支持工作区关联的版本。'); }
    finally { busy = false; await refresh(); }
  }));
  context.subscriptions.push(vscode.commands.registerCommand('trainer.connect', async () => {
    if (busy) return;
    if (!supported(vscode)) {
      vscode.window.showInformationMessage('当前仅支持可信的本地工作区；暂不支持 SSH、容器或 WSL。'); return;
    }
    busy = true;
    try {
      const pair = await request('/v2/pairings', { name: 'VS Code · Trainer Learning Bridge' });
      const action = await vscode.window.showInformationMessage(
        `配对码：${pair.code}。请在 Trainer → 学习档案 → VS Code 连接中核对请求并输入此码，5 分钟内有效。配对不会上传源码。`,
        { modal: true }, '已在 Trainer 确认');
      if (!action) return;
      const result = await request('/v2/pairings/redeem', { id: pair.id, claimSecret: pair.claimSecret });
      if (typeof result.token !== 'string' || result.scope !== 'workspace:bind') throw new Error('配对结果无效');
      await context.secrets.store(SECRET_KEY, result.token);
      vscode.window.showInformationMessage('Trainer 配对成功。配对本身不会读取或上传代码；请继续关联课程并在 Trainer 确认源码范围。');
    } catch (error) { vscode.window.showErrorMessage(error.name === 'AbortError' ? 'Trainer 连接超时，请重新尝试。' : error.message); }
    finally { busy = false; await refresh(); }
  }));
  context.subscriptions.push(vscode.commands.registerCommand('trainer.disconnect', async () => {
    const token = await context.secrets.get(SECRET_KEY);
    if (!token) return vscode.window.showInformationMessage('没有保存的 Trainer 配对。');
    try {
      await request('/v2/pairings/disconnect', { token });
      await context.secrets.delete(SECRET_KEY);
      vscode.window.showInformationMessage('Trainer 配对已撤销。');
    } catch { vscode.window.showErrorMessage('未能确认服务端撤销，保留本地凭证以便重试；请启动 Trainer 后再次断开。'); }
    finally { await refresh(); }
  }));
}

async function workspaceSummary(token, roots, send = request) {
  const result = await send('/v2/pairings/workspaces/summary', { token, roots });
  if (!Number.isInteger(result.linked) || result.linked < 0 || result.linked > roots.length) throw new Error('关联状态无效');
  if (result.bindings !== undefined) {
    if (!Array.isArray(result.bindings) || result.bindings.length > 1000 || result.bindings.some(b =>
      !b || typeof b.id !== 'string' || !/^[a-f0-9]{32}$/.test(b.id) || !roots.includes(b.root))) throw new Error('关联清单无效');
    return { linked: result.linked, bindings: result.bindings };
  }
  return { linked: result.linked };
}

module.exports = { registerPairing, supported, request, connectionState, workspaceSummary };
