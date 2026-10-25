# People and responsibility

Runtime: Spine 0.11.1, ledger schema 19. People commands were introduced in 0.11.0;
0.11.1 also integrates the timezone compatibility fix. No new migration for an
existing schema-19 ledger.
Authority: [logical contract](../specs/people-and-responsibility.md),
[exact machine registry](../contracts/people-and-responsibility.v1.json),
[runtime evidence](PEOPLE_RUNTIME_EVIDENCE.md).

## Start here

- Event participants say who attends. Task assignees say who is responsible.
- Access ownership says who may read/edit. Reminder policies/routes say who receives messages.
- These are independent. Adding somebody to an event/task grants no access and creates no reminder.
- Use exact subject IDs. Resolve names with `people.list` in an explicit owner scope; do not infer from a chat name, route or account.
- Existing command versions, local schedule/agenda reads and compact receipts still work unchanged.

Check `system info` through the installed command. Require schema 19 and the complete
`spine.people-and-responsibility.v1` family, scheduling v4, people receipt/continuity,
and cursor declarations before using the new operations. Use full output for people
evidence; the frozen compact receipt intentionally has no new people fields.

## Trusted-local commands

Use the host-selected `SPINE_COMMAND` and `SPINE_DB` from the
[operator guide](AGENT_OPERATOR_GUIDE.md). Requests below go on stdin with `--input -`.
Replace example IDs, actor, command IDs, expected version and timestamps with verified facts.

| Command | Selector | Meaning |
| --- | --- | --- |
| `people list` | `spine.people-and-responsibility.v1` | Bounded current roster in one explicit subject/group scope |
| `item people show` | `spine.people-and-responsibility.v1` | Complete current or exact historical managed role set |
| `item people update` | `spine.people-and-responsibility.v1` | Atomic full replacement of the applicable role set |
| `schedule create` | `spine.schedule-create.v4` | Existing atomic bundle plus optional top-level `people` |
| `schedule update` | `spine.schedule-update.v4` | Existing atomic update plus optional `patch.people` |

Local discovery (requires cursor configuration below):

```json
{"contract_version":"spine.people-and-responsibility.v1","owner":{"owner_kind":"subject_group","owner_group_id":"example-group"},"subject_status":"active","subject_kind":"person","limit":"25"}
```

Follow `next_cursor` while `has_more=true`, preserving the exact original filters and
limit. A small page does not bypass source/resource limits; capacity failure is not a
partial successful roster. `owner_scope.list` remains local ownership inventory, not
the protected people directory. Subject/account/group provisioning remains separate.

Current read (omit `version`) or historical read:

```json
{"contract_version":"spine.people-and-responsibility.v1","item_id":"example-task","version":"2"}
```

Replace task assignees:

```json
{"contract_version":"spine.people-and-responsibility.v1","command_id":"operator-unique-people-update","actor_subject_id":"operator-subject","item_id":"example-task","target_version":"2","updated_at_utc":"2035-01-01T12:00:00Z","people":{"assignees":["caleb"]}}
```

Events use `participants`, tasks use `assignees`; unsupported keys are invalid even
when empty. A present array replaces the complete managed set; `[]` clears it. Null,
duplicates and an empty people object are invalid. Omitted update people preserve
the set; omitted creation people normalize to an empty set. Other role kinds and
historical rows remain unchanged. An open unscheduled task can be assigned directly.

Scheduling v4 examples are additions to the ordinary full scheduling request:

```json
{"people":{"participants":["lynn"]}}
```

```json
{"patch":{"people":{"assignees":["caleb"]}},"materialization":{"mode":"none"}}
```

These two fragments are not complete requests. V4 rejects legacy
`task_detail.subject_roles` rather than accepting competing inputs; v2/v3 remain
valid with their original semantics. People-only updates require
`materialization.mode=none`; mixed schedule changes use the existing reconciliation
rules and one transaction/version. Presentation-only edits remain exclusive.

## Protected web surface

Use the existing trusted-identity Host, Origin, JSON-content and selected account/
selection headers. This remains honest self-identification on a trusted deployment,
not proof of authentication. No subject/account/privilege override belongs in JSON.

All requests use outer `contract_version=spine.trusted-web-people.v1` and `request`.
Writes require `expected_access_epoch`; creation also requires explicit
`create_owner_scope`. The inner actor must match the admitted subject. Exact schemas
and per-route prerequisites live in the machine registry; old web envelopes are not
accepted as people envelopes.

| POST path | Operation |
| --- | --- |
| `/api/v3/commands/people.list` | Scoped people directory |
| `/api/v3/commands/item.people.show` | Current/historical people |
| `/api/v3/commands/item.people.update` | Atomic people replacement |
| `/api/v3/commands/schedule.create` | Atomic scheduling v4 |
| `/api/v3/commands/schedule.update` | Scheduling v4 update |
| `/api/v3/commands/schedule.show` | Independent activity/time with optional `people` |
| `/api/v3/agenda` | Authorized agenda, optional `people` and `person_filter` |
| `/api/v3/commands/item.occurrences` | Authorized occurrences with optional `person_filter` |

For schedule/agenda reads, request `include:["people"]` when needed. The complete
optional section has `available`, `not_requested` or `unavailable`; it has no separate
cursor. Existing `subject_roles` stays self-only. Local schedule/agenda/occurrence
reads are unchanged; use local `item.people.show` for local role evidence.

Agenda/occurrence `person_filter` accepts one exact `subject_id` and optional unique
`roles:["assignee","participant"]` (default both, OR semantics). It narrows already
authorized current active tuples before expansion and pagination. It is not a subject
existence lookup or permission grant. Inactive subjects can still match retained
active associations. An unavailable-time task remains unplaced, not dropped.

Any active group member can read its current group roster. Fresh protected references
must be eligible for the actual target owner scope and require directory authority.
Item-only grantees may retain/remove existing references, not enumerate a roster or
probe fresh outsiders. A subject-owned private item cannot acquire another assignee
merely because they share a group. A readable tuple can disclose its subject ID while
its current label is only `not_disclosed`; this does not hide or delete the tuple.

## Protected cursor setup

Timezone baseline evidence is separate configuration: preserve
`SPINE_TIMEZONE_BASELINES` for agent CLI commands, web, worker and agenda jobs.
It is not supplied by the people cursor file. See
[timezone operations](TZDB_COMPATIBILITY_OPERATIONS.md).

Provision one operator-owned, persistent secret file outside Git, for this ledger
instance. This is separate from facet cursor configuration. Its exact schema is
[people cursor configuration](../contracts/schemas/people/cursor-config.schema.json).
Use `ledger_instance_id` returned by `system.info`, not a web deployment ledger label.
Generate a cryptographically random 32–64-byte secret; never paste it into chats/logs.
The regular file must be owned by root or the runtime user with no group/other
permissions (normally mode 0600); symlinks are refused. Do not overwrite a live key
without deliberate rotation. Back it up independently of the ledger.

Local roster discovery reads `SPINE_PEOPLE_CURSOR_CONFIG=/absolute/protected/file.json`.
Web service startup takes `--people-cursor-config /absolute/protected/file.json`.
The file contains `contract_version=spine.people-cursor-config.v1`, opaque `key_id`,
`key_generation`, exact `ledger_instance_id`, and lowercase `secret_hex`. No secret
or config path belongs in a request body. Missing/bad local configuration refuses
listing; missing/bad web configuration disables the entire v3 family with 503 while
the frozen v1/v2 families remain usable. A wrong ledger instance is also refused.

`pc1` cursors bind original filters/limits, contributing source, identity/access,
ledger and key generation. They expire within 900 seconds or at an earlier relevant
authority transition. On local `stale_cursor` or protected `access_changed`, discard
the old cursor and start a fresh read deliberately; do not mix pages across selections.
No cursor row, receipt or durable read cache is created.

## Mutation evidence and reminders

Verify changed/no-op/replay effect, original immutable association IDs, expected/current
versions and receipt. Standalone updates always report `work_changed=false`. A no-op
keeps version/association IDs; compatible replay returns the original receipt/history
without new writes. Labels are current authorized read metadata, not receipt facts.
Dry-run uses real validation then rolls back. Retry an uncertain mutation with its
original command ID, not a new one.

People-only edits preserve eligible/retry/in-progress work and immutable attempt
history only under their strict separate continuity proof. They never create missing
work, notify a new assignee, change a route or resend. Independently stale work stays
stale. A source event's people edit still stales its `follow_source` dependents; use
explicit `schedule.binding.reconcile` rather than assuming people edits refresh pins.
Snapshot-bound tasks remain independent. Names are not added to notification text.

If a proof or bound fails, stop and inspect the structured failure. Do not repair by
raw SQL, widen roster access, truncate role sets or cancel all reminders. Deployment,
Packs installation, UI adoption and real-send permission remain separate operations.
