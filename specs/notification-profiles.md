# Spine Item Archetypes and Notification Profiles

Status: Implemented v1 on ledger schema 10
Scope: Dynamic item classification, reusable notification-policy profiles, deterministic default resolution, and snapshot application
Created: 2026-08-28

## 1. Purpose

Family coordination contains recurring real-world patterns: appointments, lessons,
social events, flights, document renewals, and other commitments often receive a
recognizable set of reminders. Reauthoring those reminder policies for every item is
unnecessary operator choreography, while hiding them in an agent prompt makes their
meaning unstable and unauditable.

Spine therefore needs two separate canonical concepts:

- an **item archetype**, describing what kind of real-world coordination pattern an
  event or task represents; and
- a **notification profile**, describing how an operator normally wants to be reminded.

Profiles are reusable authoring inputs. Applying one produces ordinary item-owned
notification intents and policies governed by `specs/notifications.md`. Profiles do
not introduce a second notification engine, a live read-time policy inheritance layer,
or a route to an adapter.

This specification also preserves the existing ability to author any number of
ordinary custom reminder policies within current command limits. That capability
already exists. Profile application only reduces repetitive authoring and records why
particular policies were created.

## 2. Authority and Contract Family

This specification depends on:

- `specs/ontology.md` for item versions, subjects, groups, notification policies,
  work, audit, and receipts;
- `specs/notifications.md` for policy normalization, opportunity expansion,
  materialization, reconciliation, and delivery separation;
- `specs/schedule-create.md` and `specs/schedule-operations.md` for atomic schedule
  authoring and mutation;
- `specs/agent-command-contract.md` for transport, replay, dry-run, validation, and
  error rules; and
- `specs/architecture.md` for provider-independent orchestration and authority
  boundaries.

The implemented capability family is:

- `spine.item-archetypes.v1`;
- `spine.notification-profiles.v1`;
- `spine.notification-profile-bindings.v1`;
- `spine.notification-profile-application.v1`;
- `spine.notification-profile-readback.v1`; and
- `spine.notification-profile-catalog-cursor.v1`.

The machine contracts are published under
`contracts/schemas/notification-profile-*.schema.json`, with fixtures indexed by
`contracts/notification-profile-fixture-manifest.json`. Runtime `0.3.0` advertises
this family only with ledger schema 10, management commands, schedule integration,
snapshot readback, fixtures, and behavioral tests.

`spine.schedule-create.v2` and `spine.schedule-update.v2` are the sole implemented
high-level schedule authoring and mutation contracts. Both use the closed
`notification_plan` shape defined here. Direct reminder authoring uses `mode=none` on
create or `action=clear` on update with `custom_additions`; profile-backed authoring
uses the explicit or archetype-default branches. The runtime MUST NOT accept an
alternate top-level `reminders` field on either command.

## 3. Core Distinctions

### 3.1 Item type

`coordination_items.item_type` remains the structural and lifecycle authority.
`event` and `task` determine detail rows, legal anchors, and lifecycle transitions.
No archetype creates a new item type or subtype table.

### 3.2 Item archetype

An archetype is explicit versioned metadata describing a reusable real-world
coordination category, such as:

- `medical_appointment`;
- `lesson`;
- `social_event`;
- `flight`; or
- `document_renewal`.

Weekly cadence is normally recurrence truth, not an archetype. A weekly lesson is an
item with `item_type=event`, `archetype=lesson`, and a weekly recurrence rule.

Version 1 allows at most one primary archetype assignment on one current item version.
Descriptive tags may be added later, but they MUST NOT participate in profile
resolution unless a future contract defines their precedence.

### 3.3 Notification profile

A notification profile is an owner-scoped, dynamically authored, versioned collection
of notification-policy templates. A profile describes schedule and late-handling
behavior only. It does not own:

- recipient identity;
- delivery target, channel, adapter, or destination;
- item time, timezone, timezone-database version, recurrence, or location;
- permission to send;
- work materialization bounds; or
- external execution.

Those facts continue to come from the applying schedule command and existing canonical
authorities.

### 3.4 Profile binding

A profile binding declares that one profile is the default for one archetype within
one exact owner scope. Bindings make default selection deterministic; they do not
apply or mutate policies by themselves.

### 3.5 Profile application

A profile application is immutable provenance recording the exact profile revision,
archetype and binding facts when applicable, merge operations, and resulting ordinary
notification intent/policy identities created for an item.

The policies are snapshot item truth. They are not evaluated by joining to the current
profile revision on read or at delivery time.

## 4. Design Invariants

1. Archetype, notification profile, and notification policy are separate canonical
   facts.
2. Creating a profile does not require creating an archetype.
3. A profile may be unbound and applied explicitly.
4. One profile may be bound to several archetypes in different scopes.
5. One archetype may resolve to different profiles for different subjects or groups.
6. Creating or changing an archetype never changes notification policies implicitly.
7. Revising or retiring a profile never changes existing item policies implicitly.
8. Applying a profile snapshots one exact revision and creates ordinary policies.
9. Agent interpretation may propose an archetype or profile, but the accepted command
   records the selection explicitly.
10. Spine never classifies an item by reading its title, summary, location, or free text
    during canonical command handling.
11. Profile application preserves the existing notification/work/attempt lifecycle and
    never invokes an adapter.
12. Profile management and resolution are bounded, replay-safe, auditable, and
    independent of ledger-wide scans.

## 5. Canonical Logical Model

Exact SQL names may change during schema design, but the following authorities and
immutable relationships are normative.

### 5.1 Item archetype roots

An archetype root owns:

- `item_archetype_id`, immutable;
- `owner_kind=system|subject|subject_group`;
- matching nullable owner ID;
- owner-local `archetype_key`;
- `status=active|retired`;
- current revision identity;
- creation actor, command, and timestamp; and
- optional retirement actor, command, reason, and timestamp.

`(owner_kind, owner_id, archetype_key)` is unique. System keys occupy a reserved
namespace and cannot be created, revised, or retired by an ordinary operator command.
Retirement is one-way and prevents fresh assignment or binding; it does not invalidate
historical assignments or applications.

### 5.2 Item archetype revisions

An immutable archetype revision owns:

- root ID and contiguous decimal revision number;
- display name;
- optional description;
- non-empty sorted unique `compatible_item_types` drawn from `event|task` in v1;
- normalized content hash;
- actor, command, and timestamp.

Archetypes are classification metadata only. A revision cannot add executable code,
notification semantics, recurrence semantics, rendering behavior, or adapter behavior.

### 5.3 Item archetype assignments

An item assignment owns:

- `item_id` and exact item version;
- archetype root and exact revision;
- `selection_source=operator_explicit|agent_selected|imported`;
- actor, command, and timestamp; and
- optional source reference that contains no hidden scheduling behavior.

The assigned archetype MUST be active for a fresh assignment and compatible with the
item type. Every new item version materializes the complete current assignment set:
zero or one primary assignment. Copy-forward records `selection_source` as historical
accepted provenance; it does not reclassify the item.

Changing or clearing the primary archetype creates a new item version. It has no
notification effect unless the same atomic schedule command also requests a new
profile application.

### 5.4 Notification profile roots

A profile root owns:

- `notification_profile_id`, immutable;
- `owner_kind=system|subject|subject_group`;
- matching nullable owner ID;
- owner-local `profile_key`;
- display name and optional description;
- `status=active|retired`;
- current revision identity;
- creation actor, command, and timestamp; and
- optional retirement actor, command, reason, and timestamp.

`(owner_kind, owner_id, profile_key)` is unique. An operator may dynamically create
an unbound profile. A system starter profile is read-only and may be cloned into an
operator-owned profile by a future convenience command.

### 5.5 Notification profile revisions

An immutable profile revision owns:

- profile root ID and contiguous decimal revision number;
- sorted unique compatible item types drawn from `event|task`;
- one through 32 notification templates;
- normalized revision hash;
- actor, command, and timestamp.

Each template contains:

- unique `template_key` matching `^[a-z][a-z0-9_-]{0,63}$`;
- one ordinary notification `schedule` shape from
  `notification-types.schema.json#/$defs/schedule`; and
- one ordinary `late_handling` shape from the same schema family.

Templates do not store recipient, route, target anchor, application scope, materialized
work, or rendering output. On application, target anchor and application scope derive
exactly as they do for a direct reminder in the selected schedule contract:
`event_start` or `task_due`, and `item` or `each_occurrence` based on current
recurrence truth.

Two templates in one revision MUST NOT normalize to duplicate policies after
application to any permitted item type under the revision's declared constraints.
If that cannot be proven statically, profile creation or revision fails.

### 5.6 Default bindings

An active binding owns:

- `notification_profile_binding_id`;
- exact owner scope;
- archetype root ID;
- profile root ID;
- status `active|retired`;
- actor, command, and timestamp; and
- optional retirement facts.

At most one active binding exists for
`(owner_kind, owner_id, item_archetype_id)`. Binding targets a profile root, not a
revision, so a fresh default resolution selects that root's current active revision.
The applying receipt pins the selected revision. A binding and profile MUST have a
non-empty compatible item-type intersection with the archetype.

Retiring a binding affects only future default resolution.

### 5.7 Profile applications and policy provenance

An immutable application owns:

- application ID;
- item ID and version created by the applying command;
- profile root and exact revision;
- selection mode and explicit resolution scope chain;
- archetype assignment and binding identities when used;
- ordered suppress, replacement, and addition facts;
- normalized effective-policy-set hash;
- actor, command, and timestamp; and
- mappings from profile template or custom policy key to the created
  `notification_intent_id` and `notification_policy_id`.

Profile application provenance supplements ordinary notification policy truth. It
does not replace intent, policy, audit, or command receipt rows.

## 6. Ownership and Scope

Version 1 supports exact scopes:

- `system`;
- one `subject`; or
- one `subject_group`.

Owner references MUST resolve and be active for fresh operator-owned creation or
revision. Authorization to create or modify another owner's profile belongs to the
configured governance/command-authorization boundary; absence of authority fails
closed.

Profile ownership does not choose a notification recipient. The applying schedule
command still supplies one recipient and delivery route under existing rules.

Cross-owner fallback is never inferred from subject membership. A caller that wants a
personal, household, then system search supplies that exact ordered scope chain.

## 7. Selection and Default Resolution

A profile-aware schedule request selects exactly one mode:

### 7.1 `none`

No profile is applied. The request supplies one through 32 custom reminders and behaves
as direct multi-policy authoring.

### 7.2 `explicit`

The request supplies a profile root ID and either:

- `revision_resolution=current`; or
- `revision_resolution=exact` plus one profile revision ID.

Fresh current resolution requires an active root and snapshots its current revision.
Exact resolution requires that revision to belong to the root and remain legal for new
application. Replay never resolves again.

Explicit profile selection does not require an archetype assignment or binding.

### 7.3 `archetype_default`

The item MUST have a primary archetype assignment in the same accepted schedule
bundle. The request supplies a non-empty ordered `scope_chain` of at most eight unique
exact owner scopes.

Resolution checks each scope in request order and selects the first active binding
whose archetype matches and whose profile is active and compatible. It does not search
other groups, infer membership order, consult agent memory, or choose among multiple
matches. The binding uniqueness constraint makes one scope deterministic.

No match returns a structured no-match failure unless the request explicitly declares
`on_no_match=use_custom_only`, in which case custom additions must produce at least
one effective policy. The accepted branch is receipt-bearing.

### 7.4 Resolution read command

`notification_profile.resolve` performs the same bounded read-only resolution from
an explicit item type, archetype ID, and scope chain. It returns the selected profile
and revision or `effect=no_matching_profile`. It creates no receipt and does not
reserve the result. A later write re-resolves unless its request selects the returned
exact revision.

## 8. Effective Policy Composition

Profile-aware authoring computes:

```text
profile revision templates
− suppressed template keys
± complete replacements for named template keys
+ custom reminder additions
= effective ordinary notification policies
```

The request contains:

- sorted unique `suppress_template_keys`;
- sorted unique replacements, each naming exactly one existing template key and
  supplying complete replacement `schedule` and `late_handling`; and
- zero through 32 custom additions using the ordinary request-local `policy_key`,
  `schedule`, and `late_handling` shape.

A template key cannot be both suppressed and replaced. Unknown template keys fail
closed. Replacements retain provenance to the original template but produce ordinary
policies from the replacement semantics.

Canonical composition order is:

1. profile-derived entries by `template_key`;
2. profile replacements by `template_key`; and
3. custom additions by `policy_key`.

Origin and key are receipt/provenance facts, not additions to the existing
notification-policy identity preimage. After ordinary target, recipient, route,
schedule, and late-handling normalization, duplicate canonical policies fail with the
same `semantic_conflict` posture as direct multi-policy schedule authoring. They do
not create duplicate work.

The final effective set contains one through 32 policies. Materialization limits and
completeness apply to the final set. Profile resolution, composition, ordinary policy
normalization, provenance generation, requested work materialization, application
mapping, audit, and receipt commit in the same schedule transaction or all roll back.

## 9. Snapshot and Revision Semantics

Profile revisions are immutable. Revising a profile advances its current revision for
future `current` resolutions and future default applications only.

Existing applications remain pinned. They do not change when:

- the profile is revised or retired;
- a binding changes or retires;
- the item archetype definition is revised or retired; or
- a different profile becomes the default.

Existing notification policies continue under their ordinary lifecycle until an
explicit schedule update changes or disables them.

Through a profile-aware successor of `schedule.update`, an operator may explicitly
`retain` or `clear` an item's profile application, select a replacement through
`explicit` or `archetype_default`, or request `upgrade_current_revision`. Dry run MUST
expose every policy and stale-work effect before commit. Version 1 defines no implicit
bulk upgrade, background profile reconciliation, or live `follow_profile` mode.

## 10. Dynamic Management Commands

The implemented write commands are:

- `item_archetype.create`: create one root and first revision;
- `item_archetype.revise`: create the next immutable revision;
- `item_archetype.retire`: retire the root for future use;
- `notification_profile.create`: create one root and first revision;
- `notification_profile.revise`: create the next immutable revision;
- `notification_profile.retire`: retire the root;
- `notification_profile.binding.set`: create or replace one scoped default binding;
  and
- `notification_profile.binding.remove`: retire one active binding.

Every write requires `command_id`, `actor_subject_id`, an explicit action timestamp,
closed semantic input, deterministic identity, one audit record, and one command
receipt. Same-command compatible replay returns stored identities. Incompatible reuse
fails before reference or freshness checks. Retired roots and bindings are not
reactivated; create a new root or binding identity.

The implemented bounded reads are:

- `item_archetype.show|list`;
- `notification_profile.show|list`;
- `notification_profile.binding.list`; and
- `notification_profile.resolve`.

Lists require explicit limits, deterministic ordering, and revision-bound cursors.
Management commands never author an item, notification policy, work instance, or
attempt.

Profile cloning and `save_from_item` are useful future operator conveniences. They
must compile into an ordinary `notification_profile.create` request and are not
required for v1.

## 11. Schedule-Surface Integration

### 11.1 Profile-aware schedule creation

The implemented `spine.schedule-create.v2` contract accepts:

- optional primary archetype selection under `item`; and
- one closed `notification_plan` containing profile selection and effective-policy
  overlays from Sections 7 and 8.

Mode `none` is the direct-reminder path within the sole v2 contract. It creates no
profile application and composes the supplied custom additions directly into ordinary
item-owned notification policies.

The fresh response and receipt expose:

- archetype root/revision and selection source when present;
- selection mode and scope chain;
- profile root/revision and binding when present;
- normalized profile revision and effective-policy-set hashes;
- per-policy origin, template/custom key, intent ID, and policy ID;
- suppress/replacement/addition facts;
- ordinary opportunity, work, route, and lifecycle facts; and
- `delivery=not_attempted`.

### 11.2 Profile-aware schedule update

The implemented `spine.schedule-update.v2` contract accepts one complete desired notification plan
with profile action:

- `retain`;
- `clear`;
- `explicit`;
- `archetype_default`; or
- `upgrade_current_revision`.

Archetype mutation and profile action are separate request facts. Changing an
archetype while retaining the current profile changes no reminder automatically.
Selecting a new profile without changing the archetype is legal.

The command computes the complete desired effective policy set, preserves explicitly
retained custom additions, creates successor policies or disables omitted intents,
reconciles stale unstarted work, optionally materializes replacement work, and returns
per-policy effects in one transaction under `specs/schedule-operations.md`.

An overlay referencing a template absent from the newly selected revision fails with
decision pressure; it is never silently discarded.

### 11.3 Builder

A successor `schedule.build` contract may accept explicit archetype and profile
selection. It performs bounded resolution and returns a complete profile-aware
`schedule.create` request without writing. It does not classify free text, call a
model, consume a command ID, or reserve a profile revision.

### 11.4 Readback

`schedule.show` gains an explicit profile/archetype projection containing:

- current primary archetype assignment;
- current profile application;
- binding and scope-resolution facts;
- per-policy origin and template/custom keys;
- pinned versus currently available profile revision;
- whether an explicit upgrade is available; and
- bounded historical application identities when requested.

Readback computes no policy from a current profile revision. Current effective policies
remain the persisted ordinary policies on the item version.

### 11.5 Lower-level commands

`reminder.create`, `reminder.edit`, and `reminder.disable` remain valid. A reminder
created independently of a profile is an item custom policy. Lower-level edits do not
rewrite profile provenance; readback reports that the effective item policy has
diverged from its original application when applicable.

## 12. Classification and Agent Boundary

An agent may interpret “dentist appointment” and send
`selection_source=agent_selected` with an explicit archetype ID. That accepted field
is canonical command input, not proof that the classification was correct.

Spine MUST NOT:

- run a classifier or model during canonical command handling;
- derive archetype from title keywords;
- read agent memory to select a profile;
- create a new archetype because a new profile was requested; or
- treat confidence scores as scheduling authority.

An operator can correct the archetype through a new item version without changing
notifications. If the correction should also change reminders, the same atomic update
must explicitly request the profile action.

## 13. Examples

### 13.1 Same archetype, different preferences

```text
item_type: event
archetype: medical_appointment

profile appointment.standard
- 24 hours before
- 2 hours before

profile appointment.high_attention
- 7 days before
- 48 hours before
- 2 hours before
```

Both profiles apply to the same archetype. No new archetype is required.

### 13.2 Unbound reusable profile

```text
profile high_stakes_commitment
- 7 days before
- 24 hours before
- 2 hours before
- 30 minutes before
```

The profile may be applied explicitly to a flight, interview, legal deadline, or
medical appointment without any default binding.

### 13.3 Profile plus existing custom-reminder capability

```text
flight.standard@2
- 24 hours before
- 3 hours before

custom addition
- 45 minutes before
```

The effective item owns three ordinary notification policies. The custom addition uses
existing multi-policy notification capability; profile application only records the
origin of the first two.

### 13.4 New archetype

An operator creates `school_field_trip` because it is a reusable semantic category for
search, defaults, rendering, and future advisories. The operator may then bind an
existing profile or create a new one. Neither operation changes the event/task type or
adds new executable notification primitives.

## 14. Validation and Failure Posture

Minimum structured failures include:

- missing or inactive owner, archetype, profile, binding, item, actor, or route;
- stale item or profile revision;
- incompatible item type;
- duplicate owner-local key;
- duplicate template or custom policy key;
- invalid, unbounded, or duplicate normalized policy;
- unknown suppressed/replaced template key;
- one key both suppressed and replaced;
- no default match without accepted custom-only fallback;
- empty or over-limit effective policy set;
- ambiguous or unauthorized scope;
- retired root used for fresh assignment/application;
- overlay invalid after profile switch/upgrade; and
- incompatible command replay.

All failures occur before partial mutation. Schedule application uses existing schedule
validation order with profile owner/reference, selection, composition, and effective
policy normalization inserted before item/policy identity derivation and persistence.

## 15. Conformance Fixtures

Before implementation, the machine-contract package MUST include success and failure
fixtures for at least:

- dynamic creation of an unbound profile;
- revision with future-only current-pointer effect;
- personal and group defaults for one archetype;
- explicit ordered scope-chain resolution;
- no-match and accepted custom-only fallback;
- explicit profile application without archetype;
- archetype-default application;
- profile-only, custom-only, and profile-plus-custom creation;
- suppression and replacement;
- duplicate effective policy rejection;
- profile revision after an existing pinned application;
- profile switch and explicit upgrade through schedule update;
- archetype change with profile retained;
- overlay conflict after upgrade;
- retired profile/binding/archetype behavior;
- replay and dry run;
- readback origin/provenance; and
- proof that no application command creates a side-effect attempt or sends.

Computed vectors MUST publish normalized template order, resolution result, composition
order, effective-policy hash, application identity, and resulting ordinary policy
identities.

## 16. Acceptance Criteria

The capability is buildable when:

1. Item type, archetype, profile, binding, application, and ordinary notification
   policy have non-overlapping authorities.
2. Operators can dynamically create, revise, retire, list, and explicitly apply
   profiles without creating archetypes.
3. Operators can dynamically create and assign new archetypes without adding runtime
   code or notification semantics.
4. Default selection is deterministic from explicit archetype and scope-chain facts.
5. The same profile revision plus overlays and applying schedule facts produces the
   same effective policy set and identities across implementations.
6. Profile application snapshots exact revision provenance and never introduces live
   inheritance.
7. Existing direct multi-policy authoring remains valid and profile-plus-custom
   authoring composes through that same policy model.
8. Profile revision, retirement, or binding changes never mutate existing schedules.
9. Profile-aware schedule creation and update are atomic with ordinary policy/work
   reconciliation and do not alter delivery semantics.
10. Every generated policy is inspectable by origin, and every delivery still requires
    ordinary work and `side_effect_attempts`.
11. Direct and profile-backed scheduling both use the closed v2 notification-plan
    surface, with no alternate high-level request shape.
12. No agent prompt, free-text classifier, or group-membership traversal becomes
    hidden scheduling authority.

## 17. Deferred Decisions

The following are intentionally outside v1:

- live `follow_profile` inheritance;
- automatic bulk upgrade of existing schedules;
- model-driven classification inside Spine;
- multi-archetype profile stacking;
- conditional profiles based on weather, traffic, provider state, or arbitrary item
  queries;
- profiles that choose recipients or delivery routes;
- `save_from_item`, cloning, import/export, and marketplace behavior;
- task reminders that continue conditionally until completion, which require their own
  lifecycle-conditioned notification contract; and
- contextual advisory or LLM execution, which remains governed by
  `specs/contextual-advisories.md`.
