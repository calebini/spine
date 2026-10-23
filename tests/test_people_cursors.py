"""Authenticated pc1 implementation against reviewed vectors and real roster reads."""

import base64
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_people_directory as directory_tests
import test_people_ledger as foundation

from spine.commands import CommandContext, people_candidate
from spine.commands.people_runtime import PeopleContracts, PeopleCursorCodec, PeopleCursorConfig, load_cursor_config, query_hash
from spine.core.errors import SpineValidationError

ROOT = Path(__file__).parents[1]
AT = foundation.NOW


class PeopleCursorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = PeopleContracts(ROOT)

    def config(self, ledger='ledger_fixture'):
        return PeopleCursorConfig('fixture_key', '1', ledger, bytes.fromhex('ab' * 32))

    def test_exact_reviewed_mac_and_query_vectors(self):
        values = json.loads((ROOT / 'tests/fixtures/people_and_responsibility/computed-vectors.json').read_bytes())
        codec = PeopleCursorCodec(self.contracts, self.config())
        for vector in values['cursor_vectors']:
            payload = vector['payload']
            self.assertEqual(codec.encode(payload), vector['token'])
            self.assertEqual(codec.decode(vector['token'], now=payload['issued_at_utc']), payload)
        vector = values['vectors'][0]
        self.assertEqual(query_hash('people.list', vector['preimage']['request']), vector['sha256'])

    def test_private_config_permissions_shape_duplicate_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'key.json'
            # Test-only filesystem fixtures, never production credentials.
            value = json.loads((ROOT / 'tests/fixtures/people_and_responsibility/contracts/cursor_config_test_only.json').read_bytes())
            path.write_text(json.dumps(value))
            os.chmod(path, 0o600)
            self.assertEqual(load_cursor_config(str(path)), self.config())
            os.chmod(path, 0o644)
            with self.assertRaises(SpineValidationError):
                load_cursor_config(str(path))
            os.chmod(path, 0o600)
            link = Path(temp) / 'link'
            link.symlink_to(path)
            with self.assertRaises(SpineValidationError):
                load_cursor_config(str(link))
            path.write_text(json.dumps(value)[:-1] + ',"key_id":"duplicate"}')
            with self.assertRaises(SpineValidationError):
                load_cursor_config(str(path))

    def test_malformed_crossfamily_noncanonical_and_authenticated_stale_bindings(self):
        witness = json.loads((ROOT / 'tests/fixtures/people_and_responsibility/computed-vectors.json').read_bytes())['cursor_vectors'][0]
        codec = PeopleCursorCodec(self.contracts, self.config())
        token = witness['token']
        def signed(raw):
            def b64(value):
                return base64.urlsafe_b64encode(value).decode().rstrip('=')
            return 'pc1.' + b64(raw) + '.' + b64(hmac.digest(codec.config.secret, b'spine.people-cursor.v1\0' + raw, hashlib.sha256))
        for bad in (token.replace('pc1.', 'fc1.'), token + '=', token[:-8] + 'different', '', 'pc1.a.b',
                    signed(json.dumps(witness['payload']).encode()),
                    signed(b'{"contract_version":"spine.people-cursor.v1","contract_version":"duplicate"}')):
            with self.subTest(token=bad[:20]), self.assertRaises(SpineValidationError):
                codec.decode(bad, now=witness['payload']['issued_at_utc'])
        for config in (replace(self.config(), ledger_instance_id='other'), replace(self.config(), key_generation='2')):
            with self.assertRaises(SpineValidationError) as caught:
                PeopleCursorCodec(self.contracts, config).decode(token, now=witness['payload']['issued_at_utc'])
            self.assertEqual(caught.exception.code, 'stale_cursor:cursor')
        with self.assertRaises(SpineValidationError) as caught:
            codec.decode(token, now=witness['payload']['expires_at_utc'])
        self.assertEqual(caught.exception.code, 'stale_cursor:cursor')


class PeopleLocalRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = PeopleContracts(ROOT)

    def setUp(self):
        directory_tests.PeopleDirectoryTests.setUp(self)
        for subject in ('s0', 's1', 's2'):
            self.member(subject)
        instance = self.db.execute('SELECT ledger_instance_id FROM ledger_instance_metadata').fetchone()[0]
        self.config = PeopleCursorConfig('test_key', '1', instance, b't' * 32)
        self.context = CommandContext(ledger=self.db, people_cursor_config=self.config)

    member = directory_tests.PeopleDirectoryTests.member

    def request(self, **kwargs):
        return {'contract_version': people_candidate.CONTRACT, 'owner': directory_tests.GROUP, 'limit': '1', **kwargs}

    def run_command(self, request=None, **kwargs):
        result = people_candidate.execute('people.list', request or self.request(), self.context,
                                          contracts=self.contracts, now=lambda: AT, **kwargs)
        self.contracts.validate('responses' if result['ok'] else 'failures', result,
                                definition='people.list' if result['ok'] else 'local', output=True)
        return result

    def test_all_pages_write_nothing_and_keep_original_issue_expiry(self):
        before = self.db.total_changes
        first = self.run_command()
        self.assertTrue(first['ok'], first)
        second = self.run_command(self.request(cursor=first['next_cursor']))
        third = self.run_command(self.request(cursor=second['next_cursor']))
        self.assertEqual([p['subjects'][0]['subject_id'] for p in (first, second, third)], ['s0', 's1', 's2'])
        self.assertFalse(third['has_more'])
        self.assertIsNone(third['next_cursor'])
        codec = PeopleCursorCodec(self.contracts, self.config)
        a, b = (codec.decode(p['next_cursor'], now=AT) for p in (first, second))
        for field in ('issued_at_utc', 'expires_at_utc', 'query_hash', 'source_hash', 'authorization_hash'):
            self.assertEqual(a[field], b[field])
        self.assertEqual(self.db.total_changes, before)

    def test_missing_configuration_query_source_and_release_change_refuse(self):
        result = people_candidate.execute('people.list', self.request(), replace(self.context, people_cursor_config=None),
                                          contracts=self.contracts)
        self.assertEqual(result['error']['field'], 'cursor_config')
        first = self.run_command()
        changed = self.run_command(self.request(cursor=first['next_cursor'], subject_kind='person'))
        self.assertEqual(changed['error']['code'], 'stale_cursor')
        with self.db:
            self.db.execute("UPDATE subjects SET display_name='Different' WHERE subject_id='s2'")
        stale = self.run_command(self.request(cursor=first['next_cursor']))
        self.assertEqual(stale['error']['code'], 'stale_cursor')
        def mutate():
            with self.db:
                self.db.execute("UPDATE subjects SET display_name='Release change' WHERE subject_id='s1'")
        failed = self.run_command(before_release=mutate)
        self.assertFalse(failed['ok'])
        self.assertEqual(failed['error']['code'], 'environment_failure')

    def test_hidden_filtered_metadata_does_not_invalidate(self):
        with self.db:
            self.db.execute("UPDATE subjects SET subject_kind='agent' WHERE subject_id='s2'")
        request = self.request(subject_kind='person')
        first = self.run_command(request)
        with self.db:
            self.db.execute("UPDATE subjects SET display_name='Hidden update' WHERE subject_id='s2'")
        second = self.run_command({**request, 'cursor': first['next_cursor']})
        self.assertTrue(second['ok'], second)
        self.assertEqual(second['subjects'][0]['subject_id'], 's1')

    def test_future_membership_insertion_changes_transition_fence_without_epoch(self):
        first = self.run_command()
        self.member('s3', start='2026-10-20T10:05:00Z')
        result = self.run_command(self.request(cursor=first['next_cursor']))
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'stale_cursor')
