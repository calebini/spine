# Decision 0002: First-Class Delivery Targets

Status: Accepted
Date: 2026-07-14

## Decision

Spine will model delivery endpoints as first-class canonical routing records owned by either a subject or a subject group.

Transport-specific endpoint references, such as WhatsApp group JIDs, Discord channel IDs, email addresses, and direct-message handles, are delivery target facts. They are not subject IDs, group IDs, or actor identity facts.

The canonical routing surface is a `delivery_targets`-style table with an explicit owner kind:

- `owner_kind=subject` binds the target to a `subjects.subject_id`.
- `owner_kind=subject_group` binds the target to a `subject_groups.group_id`.

Exactly one owner reference is valid for a delivery target. Group delivery is first-class and must not be represented by creating a fake person subject whose ID is a transport-specific group reference.

## Rationale

Spine owns coordination truth. Adapters own vendor projection and side-effect execution details. A transport target is the address of a side effect, not the durable identity of the recipient.

The current MVP command path overloaded `work_subject_ref` as both canonical recipient identity and OpenClaw delivery target. That was acceptable for disposable canary evidence, but it is not acceptable for production-like agent use because it conflates:

- who or what the reminder is for
- which channel should be used
- where an adapter should send

Group delivery needs to be an ordinary routing case, not an exception. A household, team, project group, or stage WhatsApp group may be the intended recipient owner for a reminder. That owner should be represented as a group in Spine and routed through a delivery target.

## Consequences

`subjects` remains for people, agents, and durable subject identity anchors. `subject_groups` remains for households, teams, and other actor groupings.

Reminder authoring has a production-like routed path that identifies the recipient owner and selected delivery target rather than relying on a vendor address as a subject ID. The legacy `work_subject_ref` branch remains compatibility-only for existing subject-recipient rows.

Runtime notification adapters must resolve outbound destination from the selected delivery target. They must not treat `subjects.subject_id`, `subject_groups.group_id`, or `work_instances.work_subject_ref` as a transport `target_ref`.

`side_effect_attempts` remains Spine's canonical adapter attempt ledger. Delivery target routing does not reintroduce Kinflow's notification-specific `delivery_attempts` as a second ledger.

Canary paths for production-like use should create or reuse an explicit recipient owner and delivery target. Any remaining path that stores a WhatsApp target as a `person` subject is legacy/disposable compatibility behavior.
