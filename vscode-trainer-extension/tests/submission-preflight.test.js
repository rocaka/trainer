const { test } = require('node:test');
const assert = require('node:assert/strict');
const { inspectBuffers } = require('../src/submission-preflight');
const doc = (name, dirty = true) => ({ uri: { scheme: 'file', fsPath: name }, isDirty: dirty, getText() { throw Error('must not read'); } });
test('dirty files scoped to selected project, not sibling prefix', () => {
  const result = inspectBuffers('/project', [doc('/project/a.go'), doc('/project2/a.go'), doc('/project/b.go', false)]);
  assert.deepEqual(result.dirty, ['a.go']);
  assert.equal(result.ready, false);
});
test('untitled document blocks readiness without reading text', () => {
  assert.equal(inspectBuffers('/project', [{ isDirty: true, isUntitled: true }]).ready, false);
  assert.equal(inspectBuffers('/project', []).ready, true);
});
