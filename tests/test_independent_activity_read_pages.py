from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

from spine.commands import handle
from spine.core.canonical_json import canonical_json_bytes
from spine.core.hashing import hash_canonical_json
from spine.web.errors import WebError
from spine.web.read_cursor import DOMAIN, CursorCodec, cursor_identity
from spine.web.read_pages import ReadPager
from tests import test_independent_activity_read_contracts as contract_helpers
from tests import test_independent_activity_read_release as helpers
from tests.test_trusted_web_runtime import AT


class CursorCodecTests(unittest.TestCase):
    setUpClass = helpers.IndependentReadReleaseTests.__dict__["setUpClass"]

    def setUp(self):
        self.vector = copy.deepcopy(self.contracts.artifacts["trusted-web-read-cursor-vectors.v2.json"])
        self.codec = CursorCodec(self.contracts, key=b"private-test-key-" * 3)
        self.payload = self.vector["payload"]
        self.now = self.payload["issued_at_utc"]

    def signed(self, raw):
        def b64(b):
            return base64.urlsafe_b64encode(b).decode().rstrip("=")
        return "v2." + b64(raw) + "." + b64(hmac.digest(self.codec._key, DOMAIN + raw, hashlib.sha256))

    def reject(self, token, code="invalid_request", now=None):
        with self.assertRaises(WebError) as caught:
            self.codec.decode(token, now=now or self.now)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.details, {})

    def test_runtime_exact_published_vector_and_fixture_key_not_admitted(self):
        with self.assertRaises(WebError):
            CursorCodec(self.contracts, key=self.vector["public_test_key"].encode())
        # Exercise the actual codec with the public oracle key only by bypassing
        # construction in this test. Runtime construction always rejects it.
        self.codec._key = self.vector["public_test_key"].encode()
        self.assertEqual(self.codec.encode(self.payload), self.vector["wire"])
        self.assertEqual(self.codec.decode(self.vector["wire"], now=self.now), self.payload)
        self.assertEqual(canonical_json_bytes(self.payload).decode(), self.vector["canonical_json"])

    def test_all_closed_stream_shapes_roundtrip(self):
        schema = self.contracts.schemas["trusted-web-read-cursor.schema.json"]
        for variant in schema["oneOf"]:
            props = variant["properties"]
            payload = {k: v for k, v in self.payload.items() if k in props}
            payload.update(route=props["route"]["const"], stream=props["stream"]["const"])
            if "item_id" in props:
                payload["item_id"] = "root"
            if "range_basis" in props:
                basis = props["range_basis"]["const"]
                payload["range_basis"] = basis
                payload["last_key"] = ["2026-09-21T07:00:00Z"] + ["engine-key"] * (
                    2 if basis == "original_schedule" else 3
                )
            elif payload["route"] == "schedule.show":
                payload["last_key"] = ["resource"] * props["last_key"]["minItems"]
            elif payload["stream"] == "unplaced":
                payload["last_key"] = ["root"]
            with self.subTest(route=payload["route"], stream=payload["stream"], basis=payload.get("range_basis")):
                token = self.codec.encode(payload)
                self.assertEqual(self.codec.decode(token, now=self.now), payload)

    def test_computed_subject_revision_vector(self):
        vector = self.vector["subject_revision_vector"]
        self.assertEqual(canonical_json_bytes(vector["preimage"]).decode(), vector["canonical_json"])
        self.assertEqual(hashlib.sha256(vector["canonical_json"].encode()).hexdigest(), vector["sha256"])
        self.assertEqual(str(1 + int(vector["sha256"], 16)), vector["subject_revision"])
        identity = {**self.payload, "subject": vector["preimage"]["subject"], "binding_revision": "9"}
        actual = cursor_identity(identity)
        self.assertEqual(actual["subject_revision"], vector["subject_revision"])
        self.assertEqual(actual["account_subject_binding_revision"], "9")

    def test_noncanonical_and_malformed_tokens_are_generic(self):
        token = self.codec.encode(self.payload)
        raw = canonical_json_bytes(self.payload)
        variants = [
            "", "v1." + token[3:], token + "=", token.replace(".", ".=", 1), token + ".extra",
            token[:-1] + ("A" if token[-1] != "A" else "B"), "x" * 8193, "é" + token,
            self.signed(b" " + raw), self.signed(raw.replace(b'"access_epoch":"4"', b'"access_epoch":"4","access_epoch":"4"')),
            self.signed(raw.replace(b'"access_epoch":"4"', b'"access_epoch":4')),
            self.signed(raw.replace(b'"access_epoch":"4"', b'"access_epoch":"4","extra":"x"')),
            self.signed(raw.replace(b"2026-09-21", b"2026-02-31")),
            self.signed(b"[" * 1500 + b"]" * 1500), self.signed(b"\xff"),
        ]
        for value in variants:
            with self.subTest(token=value[:30]):
                self.reject(value)
        # Same decoded signature bytes, non-zero discarded base64 pad bits.
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        index = alphabet.index(token[-1])
        self.reject(token[:-1] + alphabet[index | 1])

    def test_signature_checked_before_json(self):
        token = self.codec.encode(self.payload)
        with patch("spine.web.read_cursor.json.loads", side_effect=AssertionError("parsed before MAC")):
            self.reject(token[:-4] + "AAAA")

    def test_expiry_future_issue_transition_and_invalid_lifetime(self):
        token = self.codec.encode(self.payload)
        for now in ("2026-09-20T07:59:59Z", "2026-09-20T08:10:00Z", "2026-09-20T08:15:00Z"):
            self.reject(token, "access_changed", now)
        self.codec.decode(token, now="2026-09-20T08:09:59Z")
        for patch_ in (
            {"expires_at_utc": "2026-09-20T08:15:01Z"},
            {"expires_at_utc": self.now},
            {"authorization_evaluated_at_utc": "2026-09-20T08:00:01Z"},
            {"authorization_valid_until_utc": self.now},
        ):
            with self.subTest(patch=patch_):
                self.reject(self.signed(canonical_json_bytes({**self.payload, **patch_})))

    def test_key_rotation_size_limits_and_private_key_admission(self):
        token = self.codec.encode(self.payload)
        self.codec = CursorCodec(self.contracts, key=b"another-private-key" * 2)
        self.reject(token)
        for key in (b"short", "a" * 32):
            with self.assertRaises(WebError):
                CursorCodec(self.contracts, key=key)
        self.payload["last_key"][-1] = "x" * 8000
        with self.assertRaises(WebError) as caught:
            self.codec.encode(self.payload)
        self.assertEqual(caught.exception.code, "capacity_exceeded")


class IndependentReadPageTests(unittest.TestCase):
    setUpClass = helpers.IndependentReadReleaseTests.__dict__["setUpClass"]
    ok, provision, event, run_command = (
        helpers.IndependentReadReleaseTests.ok, helpers.IndependentReadReleaseTests.provision,
        helpers.IndependentReadReleaseTests.event, helpers.IndependentReadReleaseTests.run_command,
    )
    snapshot, related, adopt, recurring, agenda_request = (
        helpers.IndependentReadReleaseTests.snapshot, helpers.IndependentReadReleaseTests.related,
        helpers.IndependentReadReleaseTests.adopt, helpers.IndependentReadReleaseTests.recurring,
        helpers.IndependentReadReleaseTests.agenda_request,
    )
    create, changed, mutate, update, grant = (
        helpers.IndependentReadReleaseTests.create, helpers.IndependentReadReleaseTests.changed,
        helpers.IndependentReadReleaseTests.mutate, helpers.IndependentReadReleaseTests.update, helpers.IndependentReadReleaseTests.grant,
    )

    def setUp(self):
        helpers.IndependentReadReleaseTests.setUp(self)
        self.pager = ReadPager(self.service.config, self.contracts)
        self.at = AT

    def read(self, identity=None, *, route="schedule.show", request=None, subject="owner", guards=None, **kwargs):
        kwargs.setdefault("now", lambda: self.at)
        kwargs.setdefault("selection", lambda: (self.accounts[subject], "selection"))
        response = self.pager.read(route, {
            "contract_version": "spine.trusted-web-api.v2", "request": request or {"item_id": identity}, **(guards or {}),
        }, **kwargs)
        contract_helpers.semantic_oracle(response)
        return response

    def detail_query(self, identity):
        return {"item_id": identity, "include": ["work", "policies"], "section_limit": "1"}

    def next_detail(self, identity):
        request = self.detail_query(identity)
        first = self.read(request=request)
        token = first["result"]["sections"]["work"]["next_cursor"]
        self.assertIsNotNone(token)
        return {**request, "section_cursors": {"work": token}}, first

    def test_subject_revision_closed_content_fingerprint_and_binding_mapping(self):
        identity = self.create()
        response = self.read(identity)
        subject = dict(self.db.execute("SELECT * FROM subjects WHERE subject_id='owner'").fetchone())
        expected = str(1 + int(hash_canonical_json({"contract_version": "spine.trusted-web-subject-revision.v1", "subject": subject}), 16))
        self.assertEqual(response["subject_revision"], expected)
        with self.snapshot() as snapshot:
            raw = {**snapshot.permissions.identity, "subject": subject, "selection_id": "selection"}
        self.assertEqual(cursor_identity(raw)["account_subject_binding_revision"], str(raw["binding_revision"]))
        self.mutate("UPDATE subjects SET display_name='Renamed' WHERE subject_id='owner'")
        self.assertNotEqual(self.read(identity)["subject_revision"], expected)

    def test_detail_pagination_has_no_duplicates_and_no_durable_effects(self):
        identity = self.create()
        request = self.detail_query(identity)
        before = "\n".join(self.db.iterdump())
        found, tokens, policy_pages = [], [], []
        for _ in range(10):
            page = self.read(request=request)
            section = page["result"]["sections"]["work"]
            found += [row["work_instance_id"] for row in section["entries"]]
            policy_pages.append(page["result"]["sections"]["policies"])
            if not section["has_more"]:
                break
            tokens.append(self.pager.codec.decode(section["next_cursor"], now=self.at))
            request["section_cursors"] = {"work": section["next_cursor"]}
            self.at = "2026-09-01T09:01:00Z"
        self.assertEqual(len(found), 6)
        self.assertEqual(found, sorted(set(found)))
        self.assertTrue(all(section == policy_pages[0] for section in policy_pages))
        for field in ("issued_at_utc", "expires_at_utc", "authorization_evaluated_at_utc", "source_snapshot_hash"):
            self.assertEqual(len({payload[field] for payload in tokens}), 1)
        self.assertEqual(before, "\n".join(self.db.iterdump()))

    def test_occurrence_pages_reuse_engine_order_and_ids_both_bases(self):
        identity = self.recurring()
        for basis in ("original_schedule", "expressed_time"):
            request = dict(item_id=identity, range_start="2026-08-14T00:00:00", range_end="2026-08-18T00:00:00", range_basis=basis)
            complete = self.read(route="item.occurrences", request=request)["result"]["occurrences"]
            request["limit"] = "1"
            rows = []
            for _ in range(4):
                page = self.read(route="item.occurrences", request=request)["result"]
                rows += page["occurrences"]
                if not page["has_more"]:
                    break
                request["cursor"] = page["next_cursor"]
            self.assertEqual(rows, complete)
            self.assertEqual(len(rows), 3)

    def test_agenda_shared_limit_resolved_then_unplaced_and_global_coverage(self):
        event = self.create("private-source")
        for n in range(2):
            task = self.related(event, command_id=f"hidden-source-task-{n}")
            self.adopt(task, "other")
        # Keep the source private; other gets a separate resolved event.
        resolved = self.create()
        self.grant(resolved)
        request = self.agenda_request(limit="2")
        first = self.read(route="agenda", request=request, subject="other")["result"]
        self.assertEqual(first["coverage"], "incomplete")
        self.assertEqual(len(first["entries"]), 1)
        self.assertEqual(len(first["unplaced_items"]), 1)
        payload = self.pager.codec.decode(first["next_cursor"], now=self.at)
        self.assertEqual(payload["stream"], "unplaced")
        second = self.read(route="agenda", request={**request, "cursor": first["next_cursor"]}, subject="other")["result"]
        self.assertFalse(second["has_more"])
        self.assertEqual(second["entries"], [])
        self.assertEqual(len(second["unplaced_items"]), 1)
        one = self.read(route="agenda", request={**request, "limit": "1"}, subject="other")["result"]
        self.assertEqual(one["coverage"], "incomplete")
        self.assertEqual(one["unplaced_items"], [])
        self.assertEqual(self.pager.codec.decode(one["next_cursor"], now=self.at)["stream"], "resolved")

    def test_tokens_bound_to_query_route_section_root_and_identity(self):
        identity = self.create()
        request, _ = self.next_detail(identity)
        token = request["section_cursors"]["work"]
        for changed in (
            {**request, "section_limit": "2"},
            {**request, "include": ["work"]},
            {**request, "section_cursors": {"policies": token}},
            {**request, "item_id": "other-root"},
        ):
            with self.subTest(request=changed):
                self.changed("invalid_request", lambda changed=changed: self.read(request=changed))
        self.changed("invalid_request", lambda: self.read(route="agenda", request={**self.agenda_request(), "cursor": token}))
        self.changed("access_changed", lambda: self.read(request=request, subject="other"))
        self.changed("access_changed", lambda: self.read(request=request, selection=lambda: (self.accounts["owner"], "new-selection")))

    def test_expiry_is_not_renewed_and_checked_after_fresh_proof(self):
        identity = self.create()
        request, _ = self.next_detail(identity)
        self.at = "2026-09-01T09:14:59Z"
        page = self.read(request=request)
        next_token = page["result"]["sections"]["work"]["next_cursor"]
        self.assertEqual(self.pager.codec.decode(next_token, now=self.at)["expires_at_utc"], "2026-09-01T09:15:00Z")
        self.changed("access_changed", lambda: self.read(
            request=request, before_release=lambda: setattr(self, "at", "2026-09-01T09:15:00Z"),
        ))
        self.changed("access_changed", lambda: self.read(request=request))

    def test_source_subject_and_access_changes_reject_continuation(self):
        identity = self.create()
        request, _ = self.next_detail(identity)
        self.changed("access_changed", lambda: self.read(request=request, before_release=lambda: self.update(identity)))
        self.changed("access_changed", lambda: self.read(request=request))
        request, _ = self.next_detail(identity)
        self.mutate("UPDATE subjects SET display_name='Changed' WHERE subject_id='owner'")
        self.changed("access_changed", lambda: self.read(request=request))
        request, _ = self.next_detail(identity)
        self.mutate("UPDATE ledger_access_state SET access_epoch=access_epoch+1")
        self.changed("access_changed", lambda: self.read(request=request))

    def test_invalid_selected_account_precedes_cursor_and_optional_failure(self):
        identity = self.create()
        request, _ = self.next_detail(identity)
        self.mutate("UPDATE subjects SET status='inactive' WHERE subject_id='owner'")
        request["section_cursors"]["work"] = "malformed"
        self.changed("identity_unavailable", lambda: self.read(request=request))

    def test_hidden_follower_changes_do_not_invalidate_continuation(self):
        identity = self.create()
        request, _ = self.next_detail(identity)
        hidden = self.related(identity)
        self.read(request=request)
        self.mutate("UPDATE coordination_item_versions SET title='Hidden changed' WHERE item_id=?", (hidden,))
        self.read(request=request)
        payload = self.pager.codec.decode(request["section_cursors"]["work"], now=self.at)
        self.assertNotIn(hidden, json.dumps(payload))
        self.assertNotIn("authorization_hash", payload)
        self.assertNotIn("probes", payload)

    def test_lost_proof_fails_closed_even_with_valid_signature(self):
        identity = self.create()
        request, _ = self.next_detail(identity)
        self.pager = ReadPager(self.service.config, self.contracts, cursor_key=self.pager.codec._key)
        self.changed("access_changed", lambda: self.read(request=request))

    def test_proof_store_is_bounded_and_expires_without_ledger_writes(self):
        identity = self.create()
        self.pager = ReadPager(self.service.config, self.contracts, max_proofs=1)
        request, _ = self.next_detail(identity)
        self.changed("capacity_exceeded", lambda: self.read(request={**self.detail_query(identity), "section_limit": "2"}))
        self.read(request=request)
        self.at = "2026-09-01T09:15:00Z"
        self.next_detail(identity)
        self.assertEqual(len(self.pager._proofs), 1)
        self.pager = ReadPager(self.service.config, self.contracts, max_proof_bytes=1)
        self.changed("capacity_exceeded", lambda: self.next_detail(identity))
        self.assertFalse(self.pager._proofs)

    def test_multiple_section_cursors_share_family_and_can_repeat_pages(self):
        identity = self.create()
        for n in range(3):
            self.adopt(self.related(identity, command_id=f"related-{n}"))
        request = {"item_id": identity, "include": ["related_items", "relations"], "section_limit": "1"}
        first = self.read(request=request)["result"]["sections"]
        cursors = {name: first[name]["next_cursor"] for name in request["include"]}
        self.assertTrue(all(cursors.values()))
        second = self.read(request={**request, "section_cursors": cursors})["result"]["sections"]
        again = self.read(request={**request, "section_cursors": cursors})["result"]["sections"]
        self.assertEqual(second, again)
        self.assertNotEqual(first["related_items"]["entries"], second["related_items"]["entries"])
        # Omitting another section's cursor restarts only that section in the
        # original family; the returned cursor still has the initial expiry.
        partial = self.read(request={**request, "section_cursors": {"relations": cursors["relations"]}})["result"]["sections"]
        self.assertEqual(partial["related_items"], first["related_items"])
        self.assertEqual(partial["relations"], second["relations"])
        self.at = "2026-09-01T09:01:00Z"
        fresh = self.read(request=request)["result"]["sections"]
        mixed = {"related_items": cursors["related_items"], "relations": fresh["relations"]["next_cursor"]}
        self.changed("invalid_request", lambda: self.read(request={**request, "section_cursors": mixed}))

    def occurrence_query(self, identity):
        return dict(item_id=identity, range_start="2026-08-14T00:00:00", range_end="2026-08-18T00:00:00",
                    range_basis="expressed_time", limit="1")

    def test_time_triggered_grant_expiry_blocks_next_page_without_epoch_change(self):
        identity = self.recurring()
        end = "2026-09-01T09:01:00Z"
        self.grant(identity, ends=end)
        request = self.occurrence_query(identity)
        first = self.read(route="item.occurrences", request=request, subject="other")["result"]
        self.assertTrue(first["has_more"])
        request["cursor"] = first["next_cursor"]
        payload = self.pager.codec.decode(request["cursor"], now=self.at)
        self.assertEqual(payload["authorization_valid_until_utc"], end)
        epoch = self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0]
        self.at = end
        self.changed("access_changed", lambda: self.read(route="item.occurrences", request=request, subject="other"))
        self.assertEqual(self.db.execute("SELECT access_epoch FROM ledger_access_state").fetchone()[0], epoch)

    def test_future_candidate_grant_and_membership_activation_bound_pages(self):
        visible = self.recurring()
        hidden = self.create()
        self.grant(visible)
        start = "2026-09-01T09:01:00Z"
        self.grant(hidden, starts=start)
        self.ok(handle("subject_group.upsert", {
            "command_id": "group", "actor_subject_id": "owner", "group_id": "group", "display_name": "Group",
            "updated_at_utc": AT,
        }, self.ctx))
        self.provision(memberships=[
            {"operation": "create", "group_id": "group", "subject_id": "owner", "role": "owner", "starts_at_utc": AT},
            {"operation": "create", "group_id": "group", "subject_id": "other", "role": "member", "starts_at_utc": start},
        ])
        request = self.agenda_request(limit="1")
        first = self.read(route="agenda", request=request, subject="other")["result"]
        payload = self.pager.codec.decode(first["next_cursor"], now=self.at)
        self.assertEqual(payload["authorization_valid_until_utc"], start)
        self.assertNotIn(hidden, json.dumps(payload))
        self.at = start
        self.changed("access_changed", lambda: self.read(
            route="agenda", request={**request, "cursor": first["next_cursor"]}, subject="other",
        ))

    def test_authorization_change_without_public_snapshot_change_cannot_replace_proof(self):
        identity = self.recurring()
        self.grant(identity)
        request = self.occurrence_query(identity)
        first = self.read(route="item.occurrences", request=request, subject="other")["result"]
        # Synthetic ledger mutation changes a checked grant fact without the
        # global epoch; source rows and all public family fields stay the same.
        self.mutate("UPDATE access_grants SET starts_at_utc='2026-09-01T08:00:00Z' WHERE resource_id=?", (identity,))
        self.changed("access_changed", lambda: self.read(
            route="item.occurrences", request={**request, "cursor": first["next_cursor"]}, subject="other",
        ))
        self.changed("access_changed", lambda: self.read(route="item.occurrences", request=request, subject="other"))

    def test_dst_occurrence_pages_match_canonical_overrides_and_exclusions(self):
        identity = self.recurring(seed="2026-10-31T10:00:00", count="4")
        request = dict(item_id=identity, range_start="2026-10-31T00:00:00", range_end="2026-11-05T00:00:00",
                       range_basis="expressed_time")
        initial = self.read(route="item.occurrences", request=request)["result"]
        recurrence = initial["activity"]["recurrence"]
        # Engine mutations use supported commands, preserving canonical keys.
        removed = self.ok(handle("recurrence.instance.remove", {
            "command_id": "remove", "actor_subject_id": "owner", "item_id": identity,
            "target_version": "1", "recurrence_set_id": recurrence["recurrence_set_id"],
            "recurrence_revision_id": recurrence["recurrence_revision_id"], "removed_at_utc": AT,
            "target_occurrence_key": initial["occurrences"][1]["occurrence_key"], "reason_code": "skip_one",
        }, self.ctx))
        self.ok(handle("recurrence.instance.override", {
            "command_id": "move", "actor_subject_id": "owner", "item_id": identity, "target_version": "2",
            "recurrence_set_id": removed["recurrence_set_id"], "recurrence_revision_id": removed["recurrence_revision_id"],
            "overridden_at_utc": AT, "target_occurrence_key": initial["occurrences"][2]["occurrence_key"],
            "expressed_scheduled_fact": "2026-11-03T12:00:00", "reason_code": "move_once",
        }, self.ctx))
        expected = self.read(route="item.occurrences", request=request)["result"]["occurrences"]
        rows = []
        request["limit"] = "1"
        for _ in range(5):
            page = self.read(route="item.occurrences", request=request)["result"]
            rows.extend(page["occurrences"])
            if not page["has_more"]:
                break
            request["cursor"] = page["next_cursor"]
        self.assertEqual(rows, expected)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["occurrence_key"], initial["occurrences"][2]["occurrence_key"])

    def test_optional_failure_preserves_core_and_prior_page_never_silently_degrades(self):
        from spine.web.read_context import OptionalReadUnavailable
        from spine.web.read_sections import Evidence

        identity = self.create()
        request, _ = self.next_detail(identity)
        with patch.object(Evidence, "work", side_effect=OptionalReadUnavailable):
            page = self.read(request=self.detail_query(identity))
            self.assertEqual(page["result"]["activity"]["item_id"], identity)
            self.assertEqual(page["result"]["sections"]["work"]["availability"], "unavailable")
            self.changed("access_changed", lambda: self.read(request=request))

    def test_page_serialization_is_inside_the_shared_deadline(self):
        identity = self.create()
        current = [0.0]
        encode = self.pager.codec.encode
        def slow_encode(payload):
            value = encode(payload)
            current[0] = 5.0
            return value
        with patch.object(self.pager.codec, "encode", side_effect=slow_encode):
            self.changed("capacity_exceeded", lambda: self.read(request=self.detail_query(identity), clock=lambda: current[0]))
        self.assertFalse(self.pager._proofs)

    def test_selected_identity_queries_use_primary_indexes(self):
        for sql, params in (
            ("SELECT * FROM subjects WHERE subject_id=?", ("owner",)),
            ("SELECT * FROM web_operators WHERE account_id=?", (self.accounts["owner"],)),
        ):
            plan = [r[3] for r in self.db.execute("EXPLAIN QUERY PLAN " + sql, params)]
            self.assertTrue(any("SEARCH" in row and "INDEX" in row for row in plan), plan)

    def test_terminal_series_pages_and_resolved_empty_do_not_claim_more(self):
        identity = self.recurring()
        self.ok(handle("event.cancel", {
            "command_id": "cancel", "actor_subject_id": "owner", "item_id": identity, "target_version": "1",
            "cancelled_at_utc": AT,
        }, self.ctx))
        request = self.occurrence_query(identity)
        found = []
        for _ in range(4):
            result = self.read(route="item.occurrences", request=request)["result"]
            found.extend(result["occurrences"])
            if not result["has_more"]:
                break
            request["cursor"] = result["next_cursor"]
        self.assertEqual(len(found), 3)
        self.assertTrue(all(row["lifecycle"] == "cancelled" and not row["actionable"] for row in found))
        empty = self.read(route="agenda", request=self.agenda_request(limit="1"))["result"]
        self.assertEqual(empty["entries"], [])
        self.assertEqual(empty["coverage"], "complete")
        self.assertFalse(empty["has_more"])
        self.assertIsNone(empty["next_cursor"])
        terminal = self.read(route="agenda", request=self.agenda_request(limit="1", include_terminal=True))["result"]
        self.assertTrue(terminal["has_more"])

    def test_empty_available_detail_and_unknown_time_have_no_cursor(self):
        identity = self.create()
        task = self.related(identity)
        self.adopt(task, "other")
        result = self.read(request={"item_id": task, "include": ["related_items"], "section_limit": "1"}, subject="other")["result"]
        self.assertEqual(result["activity"]["time"]["availability"], "unavailable")
        self.assertEqual(result["sections"]["related_items"], {
            "availability": "available", "scope": "authorized_only", "coverage": "complete",
            "entries": [], "has_more": False, "next_cursor": None,
        })

    def test_changed_off_page_candidate_invalidates_agenda_before_paging(self):
        identity = self.recurring()
        other = self.create()
        request = self.agenda_request(limit="1")
        first = self.read(route="agenda", request=request)["result"]
        off_page = other if first["entries"][0]["activity"]["item_id"] == identity else identity
        self.update(off_page)
        self.changed("access_changed", lambda: self.read(route="agenda", request={**request, "cursor": first["next_cursor"]}))

    def test_stale_follow_source_stays_unplaced_on_later_agenda_page(self):
        identity = self.create()
        task = self.related(identity)
        self.adopt(task)
        self.update(identity)
        request = self.agenda_request(limit="1")
        first = self.read(route="agenda", request=request)["result"]
        self.assertEqual(first["coverage"], "incomplete")
        self.assertEqual(first["unplaced_items"], [])
        second = self.read(route="agenda", request={**request, "cursor": first["next_cursor"]})["result"]
        self.assertEqual(second["entries"], [])
        self.assertEqual(second["unplaced_items"][0]["activity"]["item_id"], task)
        self.assertEqual(second["unplaced_items"][0]["activity"]["time"]["availability"], "unavailable")
        self.assertNotIn("anchors", second["unplaced_items"][0]["activity"]["time"])

    def test_page_size_is_hashed_and_hundred_row_max_is_rejected_before_assembly(self):
        identity = self.recurring()
        request = self.occurrence_query(identity)
        first = self.read(route="item.occurrences", request=request)["result"]
        self.changed("invalid_request", lambda: self.read(
            route="item.occurrences", request={**request, "cursor": first["next_cursor"], "limit": "2"},
        ))
        self.changed("invalid_request", lambda: self.read(route="item.occurrences", request={**request, "limit": "101"}))


if __name__ == "__main__":
    unittest.main()
