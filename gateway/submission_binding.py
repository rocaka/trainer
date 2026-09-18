"""Native-only adapter for existing workspace/source grants.

buffer_status must return authenticated extension metadata timestamped by the
server, for this binding. No client timestamp or cached online dot is sufficient.
No production extension metadata transport is wired here yet.
"""
import time


class SubmissionBindings:
    def __init__(self, workspaces, sources, buffer_status, clock=time.monotonic):
        self.workspaces, self.sources = workspaces, sources
        self.buffer_status, self.clock = buffer_status, clock

    def __call__(self, learner, binding_id):
        if learner != 'local':
            raise ValueError('仅支持当前本机学习者')
        def current():
            bindings = [b for b in self.workspaces.active() if b['id'] == binding_id and b['valid']]
            if len(bindings) != 1:
                raise ValueError('工作区关联已失效')
            return bindings[0]
        binding = current()

        def guard(paths):
            latest = current()
            if latest['root'] != binding['root'] or latest['plan_id'] != binding['plan_id']:
                raise ValueError('工作区关联已改变')
            allowed = set()
            for grant in self.sources.list_native():
                if grant['valid'] and grant['bindingId'] == binding_id:
                    allowed.update(grant['paths'])
            status = self.buffer_status(binding_id)
            fresh = False
            dirty = []
            if isinstance(status, dict) and status.get('bindingId') == binding_id:
                received = status.get('receivedAt')
                dirty = status.get('dirtyPaths', [])
                fresh = (type(received) in (int, float) and 0 <= self.clock() - received <= 5
                         and status.get('trusted') is True and status.get('local') is True
                         and status.get('untitled') == 0 and type(status.get('untitled')) is int
                         and isinstance(dirty, list) and all(isinstance(p, str) for p in dirty))
            return {'valid': True, 'authorizedPaths': sorted(allowed),
                    'dirtyPaths': dirty if isinstance(dirty, list) else [], 'buffersFresh': fresh}

        return {'root': binding['root'], 'planId': binding['plan_id'], 'guard': guard}
