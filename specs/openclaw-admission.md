# OpenClaw to Spine Admission Boundary

Status: Draft v0.1.1; deferred protected-agent qualification proposal; not implemented or audited
Created: 2026-09-05
Scope: Message-specific identity evidence and protected command delegation for the first chat adapter

The immediate staging scope is [accounts-and-chat-attribution.md](accounts-and-chat-attribution.md).
Stable observed prompt metadata supports account lookup but does not satisfy this
stronger qualification. Trusted multi-operator use requires no OpenClaw extension or
executor token now. All protected-origin requirements below remain deferred and intact.
Broker instrumentation is deferred. Future verified origin
resolves a login account and its explicit subject binding, not a phone-number subject ID.

## 1. Authority and Evidence Status

[single-operator-admission.md](single-operator-admission.md) defines Spine admission;
[identity-and-access.md](identity-and-access.md) defines the architecture. This document
specifies requirements on a prospective OpenClaw bridge. It does not assert that
upstream OpenClaw implements or has accepted them. No OpenClaw source was inspected
locally to establish these guarantees, and no plugin hooks or field names below are
declared stable APIs by this draft.

The user supplied a read-only inspection report from the staging scheduling agent.
Its provisional evidence and unknowns are recorded separately in
[the inspection note](../docs/design-notes/openclaw-identity-inspection.md). In
particular, runtime-only requester context appears promising, whereas model-authored
`actor_subject_id` is not authoritative attribution. Qualification must verify the
deployed source and configuration, not promote those observations into guarantees.

The proposed consumer family is `spine.openclaw-admission.v1`; it is not an implemented
version or an upstream OpenClaw capability claim. The first target is WhatsApp-origin
requests; other channels require separate issuer/adapter qualification even if they
share an OpenClaw tool interface.

## 2. Trust Chain and Responsibilities

The intended chain is:

```text
WhatsApp linked-session transport and ingress policy
  -> qualified channel normalization
  -> protected per-message evidence broker
  -> delegated tool bridge using immutable runtime context
  -> authenticated Spine admission service
  -> existing command/services layer
```

The channel supplies observed origin. The evidence broker validates provenance and
binds that origin to an execution context. The tool bridge submits proposed domain
commands with that context. Spine authenticates the peer, maps the principal, and
checks command/effect and audience authority. The model may propose intent; it owns
neither origin evidence nor permission policy.

The broker may be a small integration component, not a new workflow engine. Its
security boundary is mandatory even if broker and bridge are implemented together:
general model-controlled tools must not have its ability to mint sender assertions.
Whether an existing OpenClaw extension can provide this separation is a qualification
question. A same-process plugin beside unrestricted same-user `exec` is not sufficient
unless the surrounding execution boundary actually isolates the credential/context.

## 3. Origin Qualification

For the exact deployed channel version, publish a field-level trace showing:

| Fact | Required proof |
|---|---|
| Issuer and receiving account | Configured channel identity namespace and linked account; not supplied by message body |
| Human sender | Raw provider field and its mapping for both direct and group messages |
| Conversation | Stable direct/group destination identity; separate from sender |
| Provider event identity | Namespace, uniqueness, duplicate/edit behavior, and account scope |
| Provider time and receive time | Provenance of each; trusted receive time cannot be replaced by user content |
| Message kind | Human-origin, local/self, bot/system, quoted, forwarded, edited, or unsupported classification |
| Agent execution association | How the runtime binds that event to a run and its tool calls |

Qualify the linked-session transport and ingress acceptance mechanism actually used.
Do not invent a signed webhook if this integration uses a linked WhatsApp Web session.
Ingress allowlists constrain who may be handled; they do not independently prove the
cryptographic authenticity of every normalized field or establish a Spine subject.
Document compromise assumptions: a compromised linked account or trusted broker can
misrepresent origin. Authenticating an account is not proof of a physical human.

Sender aliases must follow a deterministic namespace-specific normalization rule,
including missing/ambiguous cases. In group messages the conversation identifier must
never be substituted for the participant's sender identity. A display name, quoted
sender, group label, or `actor_subject_id` is not a normalization fallback.

The first qualified path accepts only recognized human-origin messages from explicitly
mapped identities. Self/system messages, ambiguous sender fields, and unsupported
message forms are denied or go through separately provisioned service paths. Quote or
mention gating may wake an agent but cannot confer sender authorization. Forwarded
content carries the forwarding sender's authority only, never the quoted author's.

## 4. Per-Message Context and Concurrent Tools

The broker assigns an immutable opaque origin reference bound to the verified event,
authenticated executor, destination audience, and a bounded lifetime. Possession of a
model-visible reference alone is not authorization. The bridge receives its context
through a protected runtime channel; request JSON cannot select a different reference.

A session key is not an identity. Every tool call must be associated with exactly one
origin event and execution run. The bridge must not use a process-global latest sender,
last message in history, prompt parsing, or a mutable group-session variable. Concurrent
turns from different senders, queued tools, retries, and delayed callbacks must preserve
the association or fail closed. No tool may merge authority from several messages.

If OpenClaw batches multiple inbound messages, the qualified bridge must either
preserve a separate origin for each proposed operation or reject the batch for protected
tools. Choosing the most privileged or most recent sender is forbidden. Even multiple
messages from one sender need a stable operation-to-origin association for replay.

Subagents and background jobs receive no implicit delegation from conversation history.
One-hop delegated requests are the first-slice limit. A delayed job either re-enters
with current authorized context or is an explicitly provisioned autonomous service;
it cannot extend an expired human context by changing its mode.

## 5. Tool Interface and Bypass Prevention

The public model-facing tool accepts a canonical command and its domain proposal.
It must not accept authentication assertions, issuer mappings, executor identities,
credentials, policy generations, filesystem database paths, or response-authority
overrides from the model. The trusted layer binds actor and retry metadata before
forming the existing domain request. Conflicting attribution is rejected.

The bridge calls protected Spine admission. A wrapper that merely appends a human ID
and shells out to the existing unrestricted CLI is insufficient. The deployment must
qualify all alternate access paths: general `exec`, Python imports, SQLite, old command
binaries, backups, policy/config files, service credentials, and tools running as a
more privileged OS identity. Denying one command name does not close those paths.

The model still controls proposed business arguments such as title and time; their
ordinary validation and any necessary user confirmation remain in effect. Verified
sender identity is not proof that a generated command faithfully expresses intent.
Prompt-injection resistance and governed-action approval are not solved by caller
authentication. Tools remain scoped to the request and executor's permitted effects.

## 6. Replay and Transport Retries

Qualification must document the provider event-ID namespace and maximum accepted
event age. The broker records trusted first receipt of an event; a retransmission
cannot reset that time. Old events outside the supported window are rejected, not
treated as fresh messages after local dedupe state expires. How to distinguish an
unseen delayed event from replay requires provider evidence and an explicit policy.

For each write operation, trusted orchestration allocates a stable operation slot and
prepares one exact normalized command request. Retries replay that prepared request.
Multiple commands use distinct slots; duplicate event handling must not regenerate
slot numbering from a newly sampled plan. A changed user intent needs a new operation.

The bounded retry spool is transient transport recovery, not the canonical receipt
authority. Its release contract must define atomic prepare-before-send, stable ID
derivation, crash recovery, retry horizon, byte/count caps, and terminal eviction.
On lost success acknowledgement, retry the prepared command through current admission.
If the prepared request is unavailable, stop for reconciliation rather than inventing
a replacement command and risking a second effect. Reads need no durable spool.

Do not claim end-to-end exactly-once delivery because OpenClaw has inbound dedupe or
outbound idempotency. Spine's command receipt protects the canonical mutation; chat
reply delivery and ordinary scheduled notification attempts have their own boundaries.

## 7. Audience and History Isolation

Spine output includes sensitive readbacks, receipts, route references, errors, and
tool traces. An approved reply endpoint alone is insufficient if the result first
enters a shared model session/history. Qualification must trace output through tool
callbacks, model context, transcript persistence, memory, logs, and outbound replies.

Baseline single-operator execution uses a provisioned private response audience and
private execution history. For a group-origin request, protected retrieval happens in
an isolated private context under an explicit routing rule, not the shared group
session. If OpenClaw cannot isolate that path, protected execution is blocked there.
The group may receive only an approved generic acknowledgement without item details.

An operator can separately accept a shared session as a ledger-wide disclosure
audience under the companion policy. That is an explicit privacy concession, not
per-user access control. All group participants and future access to that history
must be considered. Existing private history must not be copied to qualify a group.

Cross-audience caches, summaries, memory stores, or tools can defeat isolation even
when sender mapping is correct. If the same model can retrieve private data through
another unrestricted tool, the deployment cannot claim this protection. This does
not authorize a broad OpenClaw redesign; unresolved isolation is a release blocker.

## 8. Compatibility and Configuration Evidence

The qualification package must identify exact OpenClaw/channel-plugin build versions,
source locations for origin and tool context mapping, bridge version, configuration
revision, supported OS peer-auth mechanism, and required admission family. Record only
non-secret configuration facts; redact personal identifiers and credentials.

Do not auto-accept a later OpenClaw build because similarly named fields still exist.
Startup verifies the approved bridge/provider compatibility record, required hooks,
and protected policy generation. Changes to origin semantics, tool invocation context,
batching, or history handling require requalification; a declared unsupported build
fails closed. Do not impose a new capability descriptor on upstream OpenClaw by fiat:
the bridge may package its own tested compatibility record.

This first draft has no qualified build or approved live configuration. The Spine
[compatibility contract](compatibility.md) continues to specify implemented Tickerd
compatibility only; the future bridge record and tests must be added explicitly before
shipping this integration. No changes to Tickerd are implied.

## 9. Qualification Oracles and Handoff

| ID | Test and required result |
|---|---|
| OC-01 | Trace a redacted direct and group event to a protected tool call with stable sender/account/conversation/event association |
| OC-02 | Forged sender text, quoted author, forwarded author, mention gating, or model actor fields cannot alter the initiator |
| OC-03 | Two simultaneous group senders, interleaved callbacks, and mixed-message batches cannot exchange context |
| OC-04 | An unknown sender admitted by OpenClaw remains denied by Spine; no fallback to operator or bot authority |
| OC-05 | General execution tools cannot mint broker context, obtain credentials, modify policy, or reach the ledger directly |
| OC-06 | Duplicate delivery and crash/lost-ack retries preserve the prepared command and produce one canonical receipt |
| OC-07 | Expired event/context, unsupported edit, or missing retry state causes bounded rejection rather than a fresh effect |
| OC-08 | Private output, summaries, errors, and traces remain outside unapproved shared histories and replies |
| OC-09 | Broker/admission outage, configuration drift, and resource exhaustion cause no unauthorized processing or log flood |
| OC-10 | Human account relinking/revocation and operator reconfiguration require trusted administration, not chat assertions |

The next OpenClaw-side inquiry should provide redacted source/config evidence for
Sections 3, 4, 5, and 7, plus the exact deployed versions. It is read-only discovery,
not permission to install a bridge, change sandbox policy, or send test messages.
The resulting proposal must identify any required upstream/extension work before this
Spine draft can be completed with machine contracts and audited for implementation.
