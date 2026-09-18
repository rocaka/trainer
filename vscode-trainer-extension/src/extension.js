const vscode = require('vscode');

function activate(context) {
  require('./submission-preflight').registerPreflight(vscode, context);
  const updateSidebar = require('./sidebar-panel').registerSidebar(vscode, context);
  require('./pairing').registerPairing(vscode, context, updateSidebar);
  context.subscriptions.push(vscode.commands.registerCommand('trainer.explainSelection', () => {
    vscode.window.showInformationMessage('旧选区自动生成入口已停用，避免绕过项目授权。请先连接 Trainer；新工作区提交入口完成后将替代此命令。');
  }));
}

function deactivate() {}
module.exports = { activate, deactivate };
