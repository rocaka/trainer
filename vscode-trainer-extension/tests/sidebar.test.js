const { test } = require('node:test');
const assert = require('node:assert/strict');
const { rows } = require('../src/sidebar');
test('sidebar exposes supported operations and points submission to Trainer', () => {
  const items = rows({ label: '未连接', detail: '重试' }, []);
  for (const command of ['trainer.connect', 'trainer.bindWorkspace', 'trainer.submissionPreflight', 'trainer.connectionStatus', 'trainer.disconnect']) {
    assert.ok(items.some(item => item.command === command));
  }
  assert.ok(items.some(item => item.label.includes('在 Trainer 完成') && !item.command));
  assert.equal(items[0].label, '未连接');
});
test('workspace labels are plain text, not executable commands', () => {
  const items = rows({ label: '已连接' }, [{ name: '<script>', uri: { fsPath: '/project' } }]);
  const item = items.find(item => item.label === '<script>');
  assert.equal(item.detail, '/project');
  assert.equal(item.command, undefined);
});
