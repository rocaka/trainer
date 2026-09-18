import json
import tempfile
import unittest
from pathlib import Path
from extension_pairing import Pairings
from pairing_service import PairingService


class PairingServiceTests(unittest.TestCase):
    def test_native_status_distinguishes_paired_from_online(self):
        with tempfile.TemporaryDirectory() as root:
            store = Pairings(Path(root) / 'pair.db', clock=lambda: 1000)
            service = PairingService(store, 'native')
            route = '/v2/pairings/connection-status'
            self.assertEqual(service.handle('GET', route, '')[0], 401)
            pair = store.request('test'); store.approve(pair['id'], pair['code'])
            token = store.redeem(pair['id'], pair['claimSecret'])
            self.assertEqual(service.handle('GET', route, 'native')[1]['online'], 0)
            service.handle('POST', '/v2/pairings/session', '', json.dumps({'token': token}).encode())
            self.assertEqual(service.handle('GET', route, 'native')[1]['online'], 1)
            store.clock = lambda: 1060
            self.assertEqual(service.handle('GET', route, 'native')[1]['online'], 0)
            self.assertEqual(service.handle('GET', route, 'native')[1]['paired'], 1)
            store.revoke(token)
            self.assertEqual(service.handle('GET', route, 'native')[1]['paired'], 0)
    def test_course_picker_is_authenticated_and_metadata_only(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root).resolve()
            plans = root / 'plans'; plans.mkdir()
            store = Pairings(root / 'pair.db')
            service = PairingService(store, 'native', plans)
            route = '/v2/pairings/workspaces/courses'
            call = lambda token: service.handle('POST', route, '', json.dumps({'token': token}).encode())
            self.assertEqual(call('invalid')[0], 401)
            pair = store.request('test'); store.approve(pair['id'], pair['code'])
            token = store.redeem(pair['id'], pair['claimSecret'])
            (plans / ('a' * 64 + '.json')).write_text(json.dumps({'title': 'Go 入门', 'lessons': [{'id': 'one', 'body': 'PRIVATE CONTENT'}]}))
            (plans / ('b' * 64 + '.json')).write_text('broken')
            status, result = call(token)
            self.assertEqual(status, 200)
            self.assertEqual(result['courses'], [{'id': 'a' * 64, 'title': 'Go 入门', 'lessonCount': 1}])
            self.assertNotIn('PRIVATE CONTENT', str(result))

    def test_course_picker_uses_module_name_instead_of_first_lesson_for_legacy_plan(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root).resolve(); plans = root / 'plans'; plans.mkdir()
            store = Pairings(root / 'pair.db'); service = PairingService(store, 'native', plans)
            plan_id = 'c' * 64
            (plans / (plan_id + '.json')).write_text(json.dumps({
                'moduleTitles': ['1. 项目全景与环境验收'],
                'lessons': [{'id': 'one', 'title': '第一课的标题', 'language': 'Go'}]
            }))
            pair = store.request('test'); store.approve(pair['id'], pair['code'])
            token = store.redeem(pair['id'], pair['claimSecret'])
            _, result = service.handle('POST', '/v2/pairings/workspaces/courses', '', json.dumps({'token': token}).encode())
            self.assertEqual(result['courses'][0]['title'], '完整课程 · 项目全景与环境验收')
            self.assertEqual(result['courses'][0]['language'], 'Go')

    def test_workspace_requires_saved_course_and_native_approval(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root).resolve()
            plans = root / 'plans'; plans.mkdir()
            store = Pairings(root / 'pair.db')
            service = PairingService(store, 'native', plans)
            pair = store.request('test'); store.approve(pair['id'], pair['code'])
            token = store.redeem(pair['id'], pair['claimSecret'])
            call = lambda path, payload, native='': service.handle('POST', '/v2/pairings/workspaces' + path, native, json.dumps(payload).encode())
            payload = {'token': token, 'root': str(plans), 'planId': 'a' * 64}
            self.assertEqual(call('', payload)[0], 400)
            (plans / ('a' * 64 + '.json')).write_text('{"lessons": [{"id": "one"}]}')
            status, grant = call('', payload)
            self.assertEqual(status, 201)
            self.assertEqual(call('/approve', {'id': grant['id']})[0], 401)
            self.assertEqual(call('/approve', {'id': grant['id']}, 'native')[0], 200)
            self.assertTrue(call('/status', {'id': grant['id'], 'token': token})[1]['approved'])
            self.assertEqual(call('/summary', {'token': token, 'roots': [str(plans)]})[1]['linked'], 1)
            self.assertEqual(call('/summary', {'token': token, 'roots': []})[1]['linked'], 0)
            listing = service.handle('GET', '/v2/pairings/workspaces', 'native')[1]
            self.assertEqual(listing['active'][0]['id'], grant['id'])
            self.assertNotIn(token, str(listing))
            self.assertEqual(call('/revoke', {'id': grant['id']}, 'native')[0], 200)
            self.assertFalse(call('/status', {'id': grant['id'], 'token': token})[1]['approved'])
            self.assertEqual(call('/summary', {'token': token, 'roots': [str(plans)]})[1]['linked'], 0)
            self.assertEqual(service.handle('GET', '/v2/pairings/workspaces', 'native')[1]['active'], [])

    def test_roles_and_complete_pairing(self):
        with tempfile.TemporaryDirectory() as root:
            service = PairingService(Pairings(Path(root) / 'pair.db'), 'native-secret')
            call = lambda route, payload, token='': service.handle('POST', route, token, json.dumps(payload).encode())
            status, pair = call('/v2/pairings', {'name': 'VS Code'})
            self.assertEqual(status, 201)
            self.assertEqual(call('/v2/pairings/approve', {'id': pair['id'], 'code': pair['code']})[0], 401)
            self.assertEqual(call('/v2/pairings/approve', {'id': pair['id'], 'code': pair['code']}, 'native-secret')[0], 200)
            status, result = call('/v2/pairings/redeem', {'id': pair['id'], 'claimSecret': pair['claimSecret']})
            self.assertEqual(status, 200)
            self.assertEqual(call('/v2/pairings/approve', {'id': pair['id'], 'code': pair['code']}, result['token'])[0], 401)
            self.assertEqual(call('/v2/pairings/session', {'token': result['token']})[0], 200)
            self.assertEqual(call('/v2/pairings/disconnect', {'token': result['token']})[0], 200)
            self.assertEqual(call('/v2/pairings/session', {'token': result['token']})[0], 401)

    def test_pending_list_hides_secrets(self):
        with tempfile.TemporaryDirectory() as root:
            service = PairingService(Pairings(Path(root) / 'pair.db'), 'native-secret')
            _, pair = service.handle('POST', '/v2/pairings', '', b'{"name":"VS Code"}')
            status, listing = service.handle('GET', '/v2/pairings', 'native-secret')
            self.assertEqual(status, 200)
            self.assertNotIn(pair['claimSecret'], str(listing))
            self.assertNotIn('code_hash', str(listing))
            self.assertEqual(service.handle('GET', '/v2/pairings', '')[0], 401)
