# Facet-aware notification rendering

This is the trusted-local operator guide for the schema-19 rendering release.
Start with ordinary scheduling in [the quickstart](AGENT_QUICKSTART.md); use this
guide only when reminders should include explicitly selected facet facts.

## Quick decision

- Ordinary reminders need no definition or disclosure configuration. Their wording,
  work identity and delivery behavior stay unchanged.
- Details such as a flight number or terminal require a rendering definition,
  destination-specific disclosure authorization, and a recorded policy presentation.
- Full evidence uses `spine.schedule-show.v2`. `--compact` stays the existing short
  receipt: it deliberately excludes facet values and disclosure evidence.
- This release exposes the new families through the local command surface, **not**
  the current web command/facet registries. Existing web reads keep their established
  summaries or fail closed when their full old projection cannot represent v2.
- No definition, profile, pack or chat membership implicitly approves disclosure.

The CLI still requires a concrete ledger path. All examples below are request
shapes, not authorization to modify a real ledger or send a message.

## 1. Define what can appear

Use `notification_rendering_definition.create` with
`contract_version=spine.notification-rendering-definitions.v1`. An owner-scoped
definition pins the facet schema revision, field keys, labels and compatible item
types. It appends bounded deterministic details to the existing concise reminder;
it cannot contain executable templates, network lookups or model instructions.

Direct scalar values and explicitly permitted location **labels** are supported.
Location references remain references; do not copy addresses into string fields to
bypass that model. Location projection never releases an address, coordinates or
provider metadata. Canonical facts of referenced locations remain immutable.

For request shape and vocabulary, see
[definition authoring example](../tests/fixtures/notification_rendering_definitions/contracts/request_definition_create.json)
and [the command schemas](../contracts/schemas/notification-rendering-definition-commands.schema.json).
Use returned IDs, not fixture IDs, when configuring an actual ledger.

Read a root/revision with `notification_rendering_definition.show`. Publish a new
immutable revision with `.publish`; retire a root with `.retire`. Publishing does
not upgrade existing policy pins. Retirement blocks new selection, but existing
reminders retain their selected revision. Retirement is **not** disclosure revocation.

## 2. Record reusable, scoped disclosure

Use `notification_rendering_disclosure.provision` with
`contract_version=spine.notification-rendering-disclosures.v1`. Record the explicit
operator instruction and exact scope: item owner, definition root/revision, approved
selection keys, profile or direct-policy use, recipient, delivery target, channel,
adapter, destination source, target reference, and permitted location IDs.

For example: “Include flight number and terminal for this profile's reminders to
this family chat.” This is a reusable configuration, not approval of all fields in
the facet, all destinations, future definition revisions, or changes in a chat's
audience. Each policy records its resolved authorization and selected keys. An
event-specific exception can choose a narrower subset; it cannot broaden the grant.

Exact authorization IDs avoid ambiguity. Unique-match resolution succeeds only
when exactly one current authorization covers the request; ambiguous or missing
matches fail authoring atomically. `.show`/`.list` inspect grants; `.revoke` withdraws
one without changing historical attempt evidence. Use a new authorization for a
new scope rather than editing an immutable grant.

See [the scoped authorization example](../tests/fixtures/notification_rendering_definitions/contracts/request_disclosure_provision.json).

## 3. Apply without confusing presentation with scheduling

Select these request families explicitly:

| Operation | Request selector |
| --- | --- |
| Profile create/revise/show/list | `spine.notification-profiles.v2` |
| Composite creation | `spine.schedule-create.v3` |
| Composite update | `spine.schedule-update.v3` |
| Full readback | `spine.schedule-show.v2` |
| Direct reminder create/edit | nested `authoring_contract=spine.notification-schedule-authoring.v2` |

Profile v2 templates carry a `rendering` pin or explicit ordinary rendering. Applying
a profile resolves the actual disclosure authorization on the item policy; the
profile itself is not a disclosure grant. Existing v1 revisions and receipts retain
their original decoders and hashes. Use v2 full readback for successor revisions;
do not silently strip rendering to submit a v1 revision.

For a fresh trusted-local item:

1. Create with ordinary presentation and `materialization.mode=none`.
2. Establish the item owner through explicit `web_access.plan`/`web_access.apply`
   adoption. Creation does not infer ownership from the actor, route or archetype.
3. Attach/verify facet values and issue a v3 presentation-only update, again with
   `materialization.mode=none`, using current policy IDs and target item version.
4. Materialize a deliberate bounded horizon if delivery is wanted; verify evidence.

These are separate transactions. A failed later step does not undo earlier commits.
`materialization.mode=none` controls only that command, **not** the daemon or other
materializers. If details must be in place before any reminder can start, the
operator must exclude every concurrent materializer and drain in-flight operations
**before creation**, retaining exclusion through presentation commit (and through
explicit materialization/readback when that is the intended readiness checkpoint).
Do not automatically stop services from an agent authoring workflow. If setup fails,
finish it or explicitly accept ordinary delivery before releasing exclusion. No
late grace window is extended to compensate for setup time.

Presentation-only edits preserve opportunity/work/provider identities and queued,
leased, attempted and terminal history. They neither materialize absent work nor
rescue independently stale work. Started attempts replay their stored body; a new
retry evaluates current facet/disclosure facts under the same provider identity.

See [successor creation](../tests/fixtures/notification_rendering_integration/request_schedule_create_ordinary.json)
and [presentation update](../tests/fixtures/notification_rendering_integration/request_presentation_edit.json).

## 4. Verify precisely

Send this through the checkout-local `spine-command --db <ledger> --input - schedule show`:

```json
{
  "contract_version": "spine.schedule-show.v2",
  "item_id": "<returned-item-id>",
  "include": ["policies", "work", "attempts", "notification_profile"]
}
```

Current policy readback includes the exact presentation and hash. Profile evidence
contains pinned/current revisions, overlays, scope chain and origin mappings. Attempt
readback returns the stored v1 or v2 rendering, not a reconstruction from today's
facets. V2 includes the ordinary base rendering and bounded details evidence. Do not
claim that configuration, expanded opportunities or materialized work proves delivery.

Missing/out-of-scope details can yield the ordinary eligible reminder with a recorded
omission. Corrupt storage, unsupported decoders, or a failed transactional fence are
failures, not permission to send a guessed fallback. Unapproved values are not echoed
in omission diagnostics. Revocation affects new attempts; it cannot retract sent text.

## 5. Protected catalog pagination

Catalog `.list` commands require `SPINE_RENDERING_CURSOR_CONFIG`, including the first
page. This is separate from `SPINE_FACET_CURSOR_CONFIG`. Provision a non-symlink regular
file owned by the runtime user or root, with no group/other permissions (normally
`0600`), containing:

```json
{
  "contract_version": "spine.notification-rendering-cursor-config.v1",
  "key_id": "rendering-1",
  "key_generation": "generation-1",
  "ledger_instance_id": "<system.info ledger instance>",
  "secret_hex": "<32-64 cryptographically random bytes encoded as lowercase hex>"
}
```

Generate the secret outside model-authored requests; do not put it in chat, receipts,
repository files or logs. Keep filters, status and limit unchanged across pages.
Rotation, ledger restore/context changes, catalog/access epoch changes or expiry make
old cursors stale. Restart from the first page; do not decode and edit cursor payloads.

## Release and rollback checklist

Deployment is a separate operator action. Back up the ledger consistently and record
the matching old package/configuration before any migration. Stop **all** ledger
writers, including worker, web service and ad hoc commands. Migrate offline to schema
19, then run explicit `spine-ledger-migrate --verify-only`, bounded `system.info`,
protected-config checks and read-only v2/ordinary readbacks before restarting services.

Do not reopen schema 19 with an older runtime or attempt a down migration. On failure,
stop writers, retain the newer ledger and its evidence, and restore the verified
pre-migration backup **with its matching old runtime**. A real-send canary requires
separate approval. Keep existing operator capabilities and operational safeguards
when adding this guidance to agent Markdown.

Normative detail: [logical definitions](../specs/notification-rendering-definitions.md),
[integration contract](../specs/notification-rendering-integration.md), and
[release evidence](BACKLOG.md#spine-053--complete-rendering-readback-and-release-verification).
