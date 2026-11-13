import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings

from .groups import list_groups, save_group
from .keycafe import KeycafeAuth, KeycafeError, fetch_keys


class LocalGroupTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        setting = override_settings(TABLEAU_GROUPS_DB=str(Path(directory.name) / 'groups.sqlite3'))
        setting.enable()
        self.addCleanup(setting.disable)
        env = patch.dict(os.environ, {'KEYCAFE_DEMO_MODE': 'false'})
        env.start()
        self.addCleanup(env.stop)

    def test_group_lifecycle_and_persistence(self):
        created = self.client.post('/api/groups/', json.dumps({'name': ' Fleet ', 'keyIds': [123, '123', '456']}), content_type='application/json')
        self.assertEqual(created.status_code, 200)
        group = created.json()['group']
        self.assertEqual(group['keyIds'], ['123', '456'])
        self.assertEqual(Client().get('/api/groups/').json()['groups'], [group])
        url = f"/api/groups/{group['id']}/"
        response = self.client.put(url, json.dumps({'name': 'Empty', 'keyIds': []}), content_type='application/json')
        self.assertEqual(response.json()['group']['name'], 'Empty')
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(list_groups(), [])
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_validation(self):
        for payload in [[], {}, {'name': ' ', 'keyIds': []}, {'name': 'A', 'keyIds': [True]}, {'name': 'A', 'keyIds': ['../2']}, {'name': 'A', 'keyIds': [0]}]:
            with self.subTest(payload=payload), self.assertRaises(KeycafeError):
                save_group(payload)
        self.assertEqual(self.client.post('/api/groups/', '{', content_type='application/json').status_code, 400)

    def test_mutations_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        body = json.dumps({'name': 'Fleet', 'keyIds': []})
        self.assertEqual(client.post('/api/groups/', body, content_type='application/json').status_code, 403)
        token = client.get('/api/config/').json()['csrfToken']
        result = client.post('/api/groups/', body, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code, 200)
        url = f"/api/groups/{result.json()['group']['id']}/"
        self.assertEqual(client.delete(url).status_code, 403)
        self.assertEqual(client.put(url, body, content_type='application/json', HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN='https://evil.example').status_code, 403)

    @patch('keycafe_api.keycafe.fetch_key_detail_if_needed', side_effect=lambda auth, key: key)
    @patch('keycafe_api.keycafe.fetch_all_pages', return_value=[{'id': 123}, {'id': 456}])
    def test_membership_filters_before_enrichment_and_reports_missing(self, fetch, enrich):
        result = fetch_keys(KeycafeAuth('dummy'), key_ids=['123', '999'])
        self.assertEqual([key['id'] for key in result['keys']], [123])
        self.assertEqual(result['missingKeyIds'], ['999'])
        self.assertEqual(result['summary']['total'], 1)
        enrich.assert_called_once()
        self.assertNotIn('group', fetch.call_args.args[2])
        self.assertEqual(fetch_keys(KeycafeAuth('dummy'), key_ids=[])['keys'], [])

    @patch('keycafe_api.views.resolve_auth', return_value=KeycafeAuth('dummy'))
    @patch('keycafe_api.views.fetch_keys')
    def test_unknown_group_does_not_fetch_inventory(self, fetch, auth):
        self.assertEqual(self.client.get('/api/keys/?group=unknown').status_code, 404)
        fetch.assert_not_called()
