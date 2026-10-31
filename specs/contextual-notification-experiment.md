# Contextual notification experiment

Version: `0.1.0-draft.1`

Status: Broader experimental design remains draft. The synthetic capture subset is
implemented with Impetus under [the adopted capture contract](contextual-notification-capture.md);
real reminders, live providers and delivered additions remain unimplemented.

Date: 2026-10-29

## 1. Question and scope

Can a bounded LLM worker make ordinary reminders more helpful or more personable
when given their archetype, permitted facets, timing and already-rendered content?

Exercise the same objective across opted-in real event reminders rather than wait
for one rare travel scenario. A flight one week away, a lesson tomorrow and an
activity later today are examples of different context, not separate hard-coded
research workflows. A short friendly line can be worthwhile without new external
information. No addition is also a successful outcome; do not require filler.

Start with non-sensitive, non-recurring events and capture-only evaluation. Medical
and other sensitive context is excluded from this initial scope. Facet availability,
an archetype or permission to render details to a recipient does not establish
permission to disclose those details to a model or tool. Spine exports only the
explicitly permitted experiment context; free-text notes and unrelated items are
excluded by default. Exact disclosure selection remains implementation design work.

This is a separate experiment without a governance service. It does not implement
`read_only_contextual_advisory.v1` or weaken the requirements in
[contextual-advisories.md](contextual-advisories.md). No Threshold or Light grant,
native acceptance or governance eligibility is asserted. Impetus's current
governor-based specifications need an explicit experimental-mode decision before
implementation. Later governed integration remains a separate direction.

## 2. Small execution boundary

| Owner | Responsibility |
| --- | --- |
| Spine | Opt-in, source truth, minimized context, immutable work/request, notification timing, local result selection and delivery |
| Impetus | Configured model/tool adapters, bounded execution, durable claim/result, truthful call and failure records |
| Existing notification path | Ordinary rendering, routing, persisted attempt before send and actual delivery outcome |

Spine invokes a small Impetus entry point through an adapter. A local command with
JSON over standard input/output is the proposed first transport; Impetus owns its
state and credentials. No shared database, model code in Spine core or additional
network service is needed for that proposal. The exact invocation/readback commands
and process supervision are for the Impetus owner to settle.

Spine checks current source truth and experiment opt-in before export/invocation,
then checks source and disclosure again before use. A retained snapshot is not a
source lock; changes during execution can make a completed result unusable.

The request supplies an objective and finite limits under explicitly enabled local
operator configuration. It is not a native authorization. Impetus verifies the
configured caller/context and supported limits; arbitrary reminder content cannot
enable tools or choose provider endpoints. No tool is mandatory. Start with a small
named read-only capability set selected with Impetus; weather is a candidate, not
a universal recipe. Missing tool inputs cannot be guessed. Task instructions and
retrieved text cannot enlarge the configured capability set.

## 3. Request and result sketch

The [request example](../examples/contextual-notification-experiment.request.json)
and [result example](../examples/contextual-notification-experiment.result.json)
are design examples, not published schemas or supported commands. Example source
identifiers are readable aliases, not valid production identifier fixtures.

A request carries:

- Stable work identity and the original item/version, notification opportunity,
  policy, facet/rendering pins and immutable experiment-definition revision.
- Minimized archetype/event/facet context, the ordinary rendered reminder and its
  nominal notification time relative to the event. Preserve timezone information;
  the model does not infer chronology from prose alone.
- The objective, proposed allowed tools, finite execution/output limits and a firm
  content-selection cutoff. The trusted installed configuration may narrow them.

Suggested objective: **Make this reminder more helpful or more personable. Add a
brief, relevant line when worthwhile; avoid repeating the reminder. Use an available
read-only tool only when it could add practical value. Do not invent facts, imply
unperformed checks, or infer personal preferences. Returning no addition is fine.**

Spine persists the exact UTF-8 request bytes before invocation. The result echoes
their SHA-256 digest (bare lowercase hex) and work identity. This digest is an
experimental integrity binding, not authentication or a native governance hash.
It covers the complete original request file, including its trailing newline in
the example. No canonicalization or hash field inside the request is required.

Execution and proposal remain separate. A successful execution proposes either an
`addendum` or `no_addition`; a failed, interrupted or uncertain execution has no
usable proposal. An addendum can have practical value, personable wording or both.
Its basis distinguishes provided context, retrieved facts or a combination. Include
source references for retrieved claims and a brief review note, not private reasoning.
A context-only friendly line needs neither a lookup nor a fabricated citation.

The example proposes ceilings of two model calls, one optional tool call, 30 seconds
elapsed execution and a 512-byte UTF-8 addendum. These are discussion values for
this experiment, not changes to Impetus's existing bounds. Impetus must select the
backend, model input/output bounds, tool configuration, accounting and process controls
before live use. Call counts alone do not establish a hard monetary ceiling.
The example's empty allowed-tool set disables tools despite its numerical ceiling.
An actual tool-enabled configuration needs explicit supported capability bindings.

## 4. Timing, replay and failures

One opted-in ordinary notification opportunity has one persisted experimental work
identity, including the ledger instance namespace. Exact identifier derivation,
uniqueness constraints and storage/migration design must be settled before runtime.
Rediscovery resolves the existing opportunity before rendering/capturing again.
Capture time, model output, prompt edits or new transport IDs cannot reopen it.
Source changes invalidate that work for use; they do not automatically authorize
replacement research. A genuinely new notification opportunity can be new work.

Spine retains the original request bytes and their digest. Reuse of a work identity
with changed bytes conflicts. Impetus durably claims that identity and request digest
before any provider call and retains the terminal result. Neither owner retries
research automatically. A lost response is resolved through readback of that claim;
absence while the original invocation may still arrive is not permission to resend.
Restart recovers evidence for old claims, not replacement research. Admission of
genuinely new work requires known continuity; resetting a store is not recovery.

Use one active experiment run and serial calls initially. Impetus records possible
call entry before I/O; timeout or lost provider response remains uncertain, with
observed usage retained. A timeout does not prove that remote work or billing stopped.
Expired deadlines stop new calls; failure does not become `no_addition`.

Spine sets a bounded research lead time and selection cutoff relative to the ordinary
reminder. Lead time is execution preparation, not permission to notify early. Cutoff,
request expiry and local execution duration must fit the existing delivery window;
their concrete configuration and clock behavior remain owner decisions. Research must
not hold the reminder open indefinitely or extend ordinary late-handling rules.

## 5. Capture, consumption and learning

The first milestone captures proposals alongside the normal notification. Ordinary
reminders retain their existing rendering and delivery. The experiment records
source/request binding, prompt/configuration revision, call/tool facts, result,
timing and whether it would have been usable at the cutoff. Pending work remains
observable; a final review record can be completed after the cutoff. Unknown or
failed execution is shown as such, including when no terminal result is available.

Review every sampled opportunity, including successful `no_addition`, failure and
late/unusable output. Judge practical value and tone separately: useful information,
pleasant wording, repetition, unsupported claims, inappropriate familiarity, tool
necessity and timeliness. A personable result need not discover new facts. Compare
the proposed addition with the actual ordinary reminder, not a context-free baseline.

Later operator-enabled inclusion appends a bounded validated addendum; canonical
event facts and the ordinary reminder remain authoritative. Spine checks the exact
request/result binding, source/definition/disclosure freshness, information validity
for retrieved facts, cutoff and normal notification eligibility. Model text cannot
select recipients, alter schedules or suppress the underlying reminder. `no_addition`
and unusable results leave independently eligible ordinary fallback available.

Retain one logical notification identity. Once fallback is committed or any delivery
attempt starts, late results cannot create another message or reopen selection.
Before any attempt, newly stale enrichment may downgrade to ordinary content when
eligible. Selection/materialization failure needs an explicit recovery path using
retained results, without repeating research or bypassing the existing attempt ledger.
These delivery extensions require their own contracts and tests before enablement.

## 6. Handoff and next decisions

The [Impetus handoff](../docs/CONTEXTUAL_NOTIFICATION_EXPERIMENT_HANDOFF.md) separates
this proposal from its current governor-based commitments and names the next owner
decisions. Resolve source/disclosure and timing mappings in Spine; resolve experimental
admission/readback, backend/tool support and execution limits in Impetus. Agree the
small exact request/result schemas and independent fixtures before runtime code.
No general workflow engine or separate profile for each archetype is implied.

The first connected proof uses a synthetic, non-sensitive event in real Spine,
the independent Impetus entry point with a deterministic model adapter, optional
tool behavior, and real Spine capture. Include a context-only personable addendum,
no addition, a sourced useful addendum, conflict/replay, lost response, source change,
late output and restart without repeat research. Live providers and evaluation across
opted-in everyday reminders follow explicit backend/disclosure configuration.
Notification inclusion is a later operator decision, not part of capture-only proof.
