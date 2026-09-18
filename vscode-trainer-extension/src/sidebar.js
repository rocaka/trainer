function rows(state, roots) {
  return [
    { label: state.label, detail: state.detail, icon: state.checking ? 'sync~spin' : 'pulse' },
    { label: '连接 Trainer', command: 'trainer.connect', icon: 'plug' },
    { label: '关联工作区与课程', command: 'trainer.bindWorkspace', icon: 'folder-opened' },
    { label: '检查未保存文件', command: 'trainer.submissionPreflight', icon: 'checklist' },
    { label: '刷新连接状态', command: 'trainer.connectionStatus', icon: 'refresh' },
    { label: '断开当前配对', command: 'trainer.disconnect', icon: 'debug-disconnect' },
    ...roots.map(root => ({ label: root.name, detail: root.uri.fsPath, icon: 'folder' })),
    { label: '源码授权：在 Trainer 中管理', detail: '连接面板 → 已关联项目 → 设置源码读取范围。配对不等于源码授权。', icon: 'shield' },
    { label: '提交与 AI 评判：在 Trainer 完成', detail: '点击 Trainer 的提交按钮后，系统按课程合同自动选取、去重并评判已授权文件；无需逐个选择。', icon: 'verified' }
  ];
}

function registerSidebar(vscode, context) {
  const emitter = new vscode.EventEmitter();
  let state = { label: '正在检查连接…', detail: '仅查询连接与目录关联，不读取源码。', checking: true };
  const provider = {
    onDidChangeTreeData: emitter.event,
    getChildren() { return rows(state, vscode.workspace.workspaceFolders || []); },
    getTreeItem(row) {
      const item = new vscode.TreeItem(row.label, vscode.TreeItemCollapsibleState.None);
      item.tooltip = row.detail || row.label;
      item.iconPath = new vscode.ThemeIcon(row.icon);
      if (row.command) item.command = { command: row.command, title: row.label };
      return item;
    }
  };
  const view = vscode.window.createTreeView('trainer.overview', { treeDataProvider: provider, showCollapseAll: false });
  context.subscriptions.push(view, emitter, vscode.workspace.onDidChangeWorkspaceFolders(() => emitter.fire()));
  return (text, detail, checking = false) => {
    state = { label: text.replace(/\$\([^)]+\)\s*/g, ''), detail, checking };
    emitter.fire();
  };
}
module.exports = { rows, registerSidebar };
