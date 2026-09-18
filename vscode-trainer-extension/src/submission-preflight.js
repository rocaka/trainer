const path = require('node:path');

// Metadata only: never call getText(), save(), or a network API here.
function inspectBuffers(root, documents) {
  const dirty = [];
  let untitled = 0;
  for (const document of documents) {
    if (!document.isDirty) continue;
    if (document.isUntitled) { untitled += 1; continue; }
    if (document.uri.scheme !== 'file') continue;
    const relative = path.relative(root, document.uri.fsPath);
    if (!relative || relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) continue;
    dirty.push(relative);
  }
  return { dirty: [...new Set(dirty)].sort(), untitled, ready: dirty.length === 0 && untitled === 0 };
}

function registerPreflight(vscode, context) {
  context.subscriptions.push(vscode.commands.registerCommand('trainer.submissionPreflight', async () => {
    if (!vscode.workspace.isTrusted || vscode.env.remoteName) {
      return vscode.window.showWarningMessage('仅支持已信任的本地工作区。未读取或提交文件。');
    }
    const folders = (vscode.workspace.workspaceFolders || []).filter(folder => folder.uri.scheme === 'file');
    if (!folders.length) return vscode.window.showWarningMessage('请先打开本地项目文件夹。');
    const folder = folders.length === 1 ? folders[0] : await vscode.window.showQuickPick(folders.map(folder => ({ label: folder.name, description: folder.uri.fsPath, folder }))).then(item => item?.folder);
    if (!folder) return;
    const result = inspectBuffers(folder.uri.fsPath, vscode.workspace.textDocuments);
    if (!result.ready) {
      const details = result.dirty.join('\n') + (result.untitled ? `\n另有 ${result.untitled} 个未命名文档，无法判断是否属于项目。` : '');
      return vscode.window.showWarningMessage('提交前检查：请先处理未保存修改。', { modal: true, detail: details + '\n请手动保存或放弃相关修改，再重新检查。不会自动保存、读取正文或上传。' });
    }
    return vscode.window.showInformationMessage('未发现未保存的编辑器文档。可回到 Trainer 点击提交；届时系统只会按课程合同采集已授权文件并自动评判。');
  }));
}

module.exports = { inspectBuffers, registerPreflight };
