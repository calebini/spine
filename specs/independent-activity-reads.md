# Independent Authorized Activity Reads

Status: Draft v0.1; specification only, not implemented or advertised
Created: 2026-09-13
Tracking: [SPINE-015](../docs/BACKLOG.md#spine-015--read-authorized-activities-independently-of-unavailable-linked-resources)

## 1. Outcome, scope, and authority

An authorized event MUST remain readable when an inaccessible task follows it. Spine
supplies canonical dates, times, effective lifecycle, and occurrence identity;
consumers do not reconstruct missing facts or expand recurrence themselves.

This draft proposes a separately versioned web read projection. It does not change
the implemented complete-or-deny v1 web surface, local CLI responses, recurrence
identity, ownership, or write authorization. MUST/SHOULD below describe the proposed
contract after acceptance, not current runtime behavior.

[Resource permissions](permissions.md) owns authorization;
[the trusted web spec](trusted-multi-operator-web-api.md) owns selected-account admission;
[recurrence](recurrence.md), [schedule readback](schedule-show.md),
[schedule operations](schedule-operations.md), and
[temporal bindings](relative-temporal-bindings.md) own canonical facts and lifecycle.
This draft owns only read selection, safe projection, and availability semantics.

Non-goals include implementation, deployment, staging changes, ownership repair,
authentication changes, authorization from task assignment, recurrence in Kinflow,
new external effects, and family-facing wording. Atomic intended ownership during
task creation is a distinct requirement and cannot solve legitimate access differences.

## 2. Observed failure and repository evidence

The operator reports that a recurring Science class owned by `stage-whatsapp-group`
cannot be read through `schedule.show` because a following task, “Drive Callan to
Science class,” has no web-access ownership. Assignment to Caleb does not establish
web ownership. Kinflow currently contains the failed detail read and reports an
incomplete calendar. These staging facts are supplied evidence, not independently
reproduced by this specification task.

Local inspection of [the web service](../src/spine/web/service.py) shows:

- `command` calls `bound_items` for item-bearing reads, including `schedule.show`
  and `item.occurrences`, before invoking their canonical handlers.
- `query` calls `bound_items` for every scoped agenda candidate.
- `bound_items` traverses active bindings in both directions, requires item access
  and the same owner as the origin, and bounds the connected traversal at 100 items.
- Writes use the same traversal with edit checks for connected items.
- The [v1 registry](../contracts/spine.trusted-web-command-registry.v1.json) declares
  `item_read_all_returned_references` and `canonical_complete_or_deny`; runtime
  admission checks those values. Canonical schedule readback includes nested
  references, counts, and evidence that cannot simply be deleted from a v1 response.

Thus the reported problem is broader than an optional `relations` include. Omitting
that include does not bypass the pre-read traversal, and removing the traversal
alone would not establish safe field-level projection or derived-time validity.

## 3. Separate requested facts, dependencies, and optional context

Authorization follows the facts being released or used to establish their current
validity. A graph connection does not grant access and does not automatically make
every connected item a prerequisite for a read.

| Surface | Required read authority | Treatment of bindings and context |
|---|---|---|
| Existing v1 `schedule.show` | Existing full-response checks | Retains complete-or-deny behavior until an explicit separately versioned migration |
| New schedule view | Requested item's core facts; any necessary temporal source as below | No traversal into followers to read an independently scheduled event; optional sections use Section 5 |
| Existing v1 `item.occurrences` | Existing admitted canonical response checks | Remains unchanged for old consumers |
| New occurrence read | Requested recurrence root, its canonical revisions/overlays, and any source necessary for its own time | Expand in Spine without traversing downstream followers; separately governed overlay references must be projected safely |
| New scoped agenda | Each selected item and its own temporal prerequisites | Authorize before expansion, ordering, diagnostics, and pagination; hidden followers cannot exclude an authorized event |
| Related items, relations, binding detail | Each returned item plus permission to disclose the relationship and every separately governed reference | No endpoint IDs, binding headers, or provenance are emitted unless their complete returned content is authorized |
| Updates, cancellation, completion, binding operations | Existing command/effect-specific write checks | Section 8; read success never substitutes for these checks |

For the new projection, a link between two readable resources may be returned when
the existing relation-read policy permits it even if their owner scopes differ.
This does not remove the existing same-owner restriction from v1 or from writes.
Reading both endpoints alone cannot override a separately protected relation.

Core activity facts are a closed projection of the requested item's ID, type, current
version, authorized title, shell/detail lifecycle, and temporal view. They are not a
copy of the full `item.show` object. Subject roles, owner details, catalog references,
routes, receipts, policies, work, attempts, relations, bindings, and location references
require their own disclosed-section rules. A field needed for the calendar cannot
carry a hidden reference merely because its parent item is readable.

## 4. Canonical temporal facts and unavailable time

### 4.1 Independent event and occurrence facts

An event whose own schedule is independently resolvable MUST NOT require authorization
for a downstream following task. Use shared canonical recurrence and agenda logic for
dates, local/UTC interpretation, pinned timezone data, effective occurrence overlays,
exclusions, moves, DST handling, and deterministic ordering. No expansion or read
persists occurrence provenance, receipts, reconciliation, or work.

The occurrence projection preserves exact canonical `occurrence_id`, `occurrence_key`,
`recurrence_set_id`, `recurrence_revision_id`, root/current source version, original
and expressed scheduled facts, lifecycle, actionability, and applicable timezone and
resolution fields. Return canonical event start/end or date/window semantics after
effective overrides. If no end was authored or derived by the canonical contract,
represent its absence; do not invent duration. Agenda recurring entries additionally
carry canonical occurrence ID, not just a locally derived calendar key. Identity
algorithms and lifecycle precedence remain those of the domain contracts.

`schedule.show` still does not itself expand occurrences. Its new web view returns
the current temporal state and recurrence identity; the new occurrence and agenda
reads provide the supported bounded expansion path. Full recurrence authoring data
is not required in order for Kinflow to render returned occurrences.

### 4.2 Closed temporal availability union

Every new activity view has a required `time` object with `availability`:

| Value | Meaning and payload |
|---|---|
| `available` | Current authorized temporal facts have been resolved and validated; contains the applicable canonical scheduled facts and resolution evidence |
| `not_scheduled` | Spine can prove the readable item currently has no applicable authored schedule; no temporal values |
| `unavailable` | Spine cannot safely establish the requested item's current time; `reason_code=temporal_facts_unavailable`, no temporal values |

Item read permission permits disclosure of this item's own time availability, not
the existence or identity of another resource. `unavailable` deliberately conflates
missing, unowned, denied, stale, inconsistent, ambiguous, and unresolvable temporal
prerequisites. Do not add a dependency-specific reason, source ID, binding state,
stored due date, last-known deadline, offset, or source-derived diagnostic.

An active `follow_source` task requires authorization to the temporal source and a
bounded proof of current item/binding/recurrence versions under the binding contract.
A stored concrete due anchor alone is not proof of current time. If the source is
inaccessible or the binding needs reconciliation, return readable task core with
`time.availability=unavailable`. Do not reconcile during the read. Independently
authored or valid snapshot time may be returned only when currentness can be proven
without inaccessible source facts; source provenance remains independently protected.

Unavailable start, end, or another required temporal prerequisite makes the temporal
view unavailable as a unit. No guessed partial interval, stale anchor, alternate
timezone database, fabricated actionability, or synthetic occurrence may be returned.
Core shell/detail lifecycle may remain available; temporal actionability does not.
Internal corruption that prevents trusting the core itself fails the whole read.

### 4.3 Range results

The new occurrence result returns `time`, `occurrences`, and `coverage`.
If time is unavailable, return no occurrences, `coverage=incomplete`,
`has_more=false`, and `next_cursor=null`;
this is explicitly not an empty resolved series. A resolved range with zero canonical
occurrences has `coverage=complete`, an empty array, and `has_more=false`.
Valid recurrence omissions/exclusions retain their canonical meaning.

The new agenda returns resolved `entries` and a separately typed `unplaced_items`
collection of readable candidate cores whose required time is unavailable. Do not
place them on the last-known date, mark them unscheduled, or infer whether they fall
inside the requested range. `unplaced_items` applies to the selected authorized
candidate set after non-temporal filters, not a claim of range membership. Truly
unscheduled items remain available through the existing scoped item list.

Agenda `coverage=complete|incomplete` describes temporal resolution for the entire
authorized candidate snapshot, not global ledger visibility or page exhaustion.
Any unplaced candidate makes it incomplete. Pagination is separate: the logical stream
contains canonically ordered resolved entries, then unplaced cores ordered by item ID.
The shared limit counts both collections; the cursor binds the stream category and
ordering key. `has_more=false` only when both are exhausted. A page can be temporally
complete while more pages remain, or be exhausted while temporal coverage is incomplete.
Unknown-time candidates cannot prevent a resolved event from appearing in the stream.

## 5. Optional sections and disclosure-safe completeness

### 5.1 Authorized projection, not a hidden-resource inventory

New schedule views have a fixed `sections` map. Section names are declared by the
contract, never added only when a hidden relation exists. Initial names are
`related_items`, `relations`, `temporal_bindings`, `primary_location`, `notification_profiles`,
`policies`, `work`, `attempts`, `delivery_targets`, `subject_roles`, and `authoring_receipt`.
Includes default to none. Unknown includes deny as `invalid_request`; capability
discovery reports supported section names independently of per-item hidden state.
Agenda optional summaries follow the same rules; their exact section mapping must
be codified before release.

Every section has `availability=available|not_requested|unavailable` and
`scope=authorized_only`. An available collection contains authorized entries,
`has_more`, and `next_cursor`. It has `coverage=complete` for its authorized query
snapshot; page exhaustion is expressed separately. No global total is returned.
A singleton has `coverage=complete` and a disclosed value or null within the same
scope. `not_requested` has no values, coverage, reason code, or pagination.
`unavailable` has no values or pagination,
`coverage=incomplete`, and only `reason_code=context_unavailable`.

Authorize relation membership and nested content before section selection and
pagination. Omit an indivisible row if any protected field required to render that
row cannot be disclosed; do not emit partial binding or attempt objects. Authorized
related tasks continue to appear, with their own independent temporal availability.
An unrelated hidden row MUST NOT flip a section from `available` to `unavailable`.

**Default non-disclosure rule:** zero actual related tasks, only unowned related tasks,
only inaccessible related tasks, and an absent/inaccessible relation all produce the
same available empty authorized projection. With a fixed authorized subset, adding,
removing, renaming, assigning, or moving hidden tasks MUST NOT change the section's
values, coverage, counts, pagination, or public diagnostics. `scope=authorized_only`
is always present and does not assert that anything was withheld.

Thus `available`, `coverage=complete`, empty entries, and `has_more=false` means
“no entries in this authorized projection,” not “there are no linked tasks anywhere.”
Do not emit `has_hidden`, `withheld_count`, `hidden_resource`, `ownership_missing`, or
a hidden binding count. Do not run an all-relations count merely to decide a badge.

### 5.2 When incompleteness may be acknowledged

A requested section can be independently unavailable when a public service capability
or bounded authorized-data computation cannot supply that section. This is safe only
if the signal can be produced without learning whether hidden rows exist; examples
are a section-wide service outage or an authorized collection exceeding its published
section budget. It says nothing about hidden membership. Do not downgrade an
authorization change or an uncertain root read into optional-context unavailability.

No initial policy grants disclosure of the existence of inaccessible related items.
Therefore this draft does not return a hidden-membership-specific `withheld` state,
even to someone who can read the parent or is a group admin. A later contract could
distinguish globally complete-empty from withheld only with independently established,
versioned authority to know relationship membership, checked at release time. Do not
infer that authority from all currently found rows being readable, prior cached
knowledge, an assignment, or a client assertion. That extension is outside this slice.

These rules deliberately distinguish safe incomplete computation from inaccessible
membership. Kinflow may explain the former; it must not explain an authorized-only
empty projection as evidence that another person's task exists.

### 5.3 Projection and resource budgets

Use explicit per-section field allowlists; never serialize an unrestricted canonical
response and then redact a few keys. Audit IDs, hashes, signed-but-readable cursor
payloads, diagnostics, embedded rendering text, provenance, and summary aggregates as
potential disclosures. Do not copy canonical full-ledger counts or lifecycle summaries
into a filtered section under their old “complete” labels. Define each new summary
over an explicit authorized-only evidence predicate. Hidden evidence alone cannot
change availability or produce a warning. If that bounded authorized computation
fails for a safely disclosable reason under Section 5.2, the summary is independently
unavailable; an unrepresentable legacy global summary is unsupported for every item,
not selectively unavailable when hidden rows exist.

Core expansion has reserved bounded work and byte budgets; optional work cannot consume
them and starve the authorized event. Collection pagination examines only bounded
authorized candidates and uses proper continuation, not hidden-row offset scans.
Hidden graph size must not cause a public graph-capacity error for an independent event.
If the outer core/time budget cannot prove a result or valid continuation, return
`capacity_exceeded`, not a falsely complete partial result. An optional section may use
`context_unavailable` only within its separate budget and with a valid core snapshot.

## 6. Structured public outcomes

| Situation | Public result |
|---|---|
| Requested root absent, unowned, or unauthorized | Existing generic 404 `resource_unavailable`; no item body or root-specific availability details |
| Authorized event with unavailable follower | Successful core/time and occurrences; related sections obey the authorized-only rules |
| Authorized task with unsafe own time | Successful core; closed unavailable-time union, without a source-specific explanation |
| Publicly requested optional context cannot be computed safely | Successful core and independently `unavailable` section if Section 5 permits disclosure |
| Identity/binding/access epoch or checked grant changes during assembly | Discard the assembled result; generic `access_changed` where admission still permits it |
| Invalid/unavailable selected account | Existing generic admission failure, no partial core |
| Core budget exceeded or core integrity cannot be trusted | Existing bounded generic failure; no success wrapper containing guessed facts |

Applications branch on contract tags, `time.availability`, section availability/scope,
coverage, and pagination fields. They MUST NOT parse error text. Spine returns reason
codes, not family-facing explanations. Requesting an explicit hidden related ID remains
a direct generic denial, not confirmation that it is linked to a readable parent.

## 7. Snapshot, epoch, version, and pagination guarantees

All released core, time, sections, and occurrences MUST come from one bounded consistent
read snapshot. Item/current source versions and recurrence revisions are explicit for
authorized facts. An exact required item or recurrence version mismatch produces a
generic structured version conflict; never mix a new detail view with an old occurrence
page. The new read request contracts include optional `expected_access_epoch`,
`expected_item_version`, and, where recurrence applies, `expected_recurrence_revision_id`.
The latter two mismatches return 409 `version_changed`, with no current hidden values.
Malformed versions are `invalid_request`; root admission precedes version comparison.

Before release, revalidate selected account/subject/binding revisions and access epoch
in a fresh authorization snapshot, including expiry of grants/memberships without an
epoch write. Recheck authorizations actually used for disclosed facts and time sources.
Loss or gain of query-visible authorization during assembly invalidates the result;
do not assemble half a response under each policy. Freeze the initial authorization
evaluation time and bound validity by the next relevant grant/membership transition;
release or continuation at/after it requires a fresh query, even without an epoch bump.
Future activation as well as expiry needs coverage in the authorization snapshot.
This is an implementation gate, not a claim that v1 already proves every such race.

Before release also fence versions of the authorized facts used for time and sections;
changed relevant item/recurrence/binding facts require retry (`version_changed` for
direct reads, `access_changed` for stale cursor context). A new result is current at
that release fence; later changes cannot retract bytes already released. Binding
source checks are limited to necessary temporal dependencies, not downstream followers.

Integrity-protected opaque cursors bind the read contract, ledger/realm, account/subject
and selected binding revision, selection ID, access epoch, normalized query/includes/
limits, authorized source snapshot, section or stream kind, last ordering key, and
original expiry. Preserve the existing 15-minute maximum and never renew on pagination.
Each next-page request rechecks source versions and current authorization; changed
access or authorized source facts returns `access_changed`, never a silently mixed page.
Section cursors cannot be replayed for agenda or another section, item, or identity.

Hashes and cursor payloads MUST NOT include inaccessible resource IDs, counts, titles,
binding facts, or graph size. Hidden follower mutations alone cannot invalidate an
independent event's snapshot. The existing global access epoch remains a deliberately
coarse invalidation signal: its change may invalidate all reads but MUST NOT identify
which resource changed. Timers/capacity diagnostics must not reveal hidden traversal;
constant-time database access is not claimed, but hidden graph enumeration is forbidden.

Consumers discard previous selections, stale epochs, and superseded query generations,
including responses arriving out of order. Exact repeated requests at the same admitted
snapshot produce equivalent facts/order; reads create no durable receipt or side effect.

## 8. Cross-resource writes stay separately protected

This slice changes no v1 write resolver or allowlist. `schedule.update`, `schedule.cancel`,
and `task.complete` retain root edit authority, current target-version checks,
applicable reference/catalog/route/content-release checks, and the current bounded
active-binding traversal with connected-item edit and same-owner restrictions.
Missing ownership or inaccessible connected items continue to deny; the response stays
generic where more detail would disclose protected facts. Replay retains its current
receipt/account binding and authorization rules, including no duplicate mutation.

The current traversal can be stricter than the direct persisted effect set. This read
proposal does not relax it, and does not claim source cancellation synchronously mutates
every follower. Canonical binding freshness and eventual reconciliation remain unchanged.
Any future narrowing requires a separate effect inventory and accepted write contract.

Binding create/reconcile/retire and other graph mutations are not newly exposed on the
web. A later admission contract must enumerate source, target, binding, relationship,
work and content-release effects and authorize them atomically. A successful new read,
an omitted section, or an item-level edit hint cannot authorize a connected mutation.
Do not compute new per-command denial explanations from hidden graph structure.

## 9. Compatibility and migration assessment

This is a behavioral and schema change, not a patch to generic error prose. A partial
projection cannot carry `spine.schedule-show.v1` or claim its complete counts/evidence.
Likewise, new time unions and unplaced agenda items do not fit the closed v1 schemas.

Proposed names below are reserved by this draft only; no route or capability exists
until machine contracts and behavioral tests ship together:

| Surface | Proposed compatibility choice |
|---|---|
| Read transport | Separate `/api/v2/commands/schedule.show`, `/api/v2/commands/item.occurrences`, and `/api/v2/agenda`; selected identity admission retained; no v2 write routes |
| Outer envelope | `spine.trusted-web-api.v2`, explicitly closed read-only request/response variants with current identity, selection, epoch, and exact result tag |
| Schedule result | `spine.trusted-web-schedule-view.v1`, a new projected family, never canonical `spine.schedule-show.v1` |
| Occurrence result | `spine.trusted-web-occurrences.v1`, a projected family preserving canonical occurrence identity and effective temporal facts |
| Scoped agenda | `spine.trusted-web-agenda.v2`, including coverage, unplaced items, and explicit temporal/context availability |
| Read registry | `spine.trusted-web-read-registry.v1`, closed two-command registry plus explicit agenda route contract; new read-specific resolvers and projection labels |
| Cursor | `spine.trusted-web-cursor.v2`, covering projected snapshots, section cursors, authorization transition fences, and combined agenda ordering |
| Persistence | No canonical schema change or data repair is inherently required; an eventual query/index design must separately assess migration need |

Keep `/api/v1`, its command registry, result tags, schema pins, complete-or-deny
semantics, and all writes unchanged for old clients. Do not alter the v1 registry's
`canonical_complete_or_deny` enum or bypass its startup admission. Do not inject an
inner version into v1's untagged `schedule.show` or `item.occurrences` requests.
New projected requests reuse compatible field meanings but have their own closed
schemas and explicit outer version. Unknown versions deny; no silent downgrade.

Codification must add separate schema definitions for core field projections,
time/section unions, occurrence overlays, agenda entry/unplaced variants, summaries,
generic errors, expected-version guards, cursor preimages, and capability discovery.
Publish an exhaustive field-to-authority mapping, particularly for source fields,
subject roles, location snapshots, stored rendered text, and authoring receipts.
Pin exact transitive canonical dependencies without mutating old pins merely to pass
validation. Register/package new offline assets and runtime capability versions only
with matching implementation, registry admission, migration assessment, and tests.
Machine JSON schemas cannot prove authorization, disclosure safety, or atomic snapshots.

Keep current read and write complete-or-deny regression tests. Add the new suite as
separate behavior with its own vectors, not replacement expectations for v1. No change
to Tickerd, local CLI, recurrence identifiers, durable attempts, or canonical scheduling
versions is implied by a new web projection.

Kinflow migrates by explicit capability negotiation and exact version support. Before
the capability exists, retain its current incomplete-calendar handling without claiming
the cause is a hidden/unowned task. After adoption, use new agenda/occurrence reads as
the calendar source; optional detail failures cannot erase successfully read core
occurrences. Unknown contracts remain unsupported, never interpreted as empty results.
Mixed-client rollout and rollback must preserve old v1 semantics and invalidate v2
caches/cursors on loss of capability. See [consumer handoff](../docs/INDEPENDENT_READS_KINFLOW_HANDOFF.md).

## 10. Proposed contract-test matrix

These are future executable oracles, not tests run or staging results. Use isolated
fixtures with distinct selected subjects, explicit ownership/grants, exact versions,
and fake-only delivery. Compare released shapes and authorization effects, not just
HTTP success codes. Paired privacy fixtures hold authorized facts and evaluation time
constant; opaque nonce/signature bytes and the coarse global epoch are not hidden-data
content to compare literally.

| ID | Fixture or action | Required oracle |
|---|---|---|
| IR-01 | Read owned recurring event with unowned following task | New show core, occurrence dates/IDs/effective status, and agenda event succeed; task assignment grants nothing; no writes |
| IR-02 | Replace follower with one in inaccessible scope | Same disclosed event/related projection as IR-01; no task IDs, title, owner, assignee, count, binding details, or existence signal |
| IR-03 | Both endpoints and relation readable, including distinct permitted scopes | Authorized related task appears normally; canonical task time only when its own source proof is valid; v1/write owner restrictions unchanged |
| IR-04 | No related rows versus only missing/unowned/denied related rows | Identical available empty authorized-only section, no hidden flag/count; empty never asserts global absence |
| IR-05 | Public optional section outage/budget limit | Core remains usable; requested section is structured unavailable/incomplete; omitted section is not_requested; signal independent of hidden membership |
| IR-06 | Direct read or explicit agenda IDs name absent, unowned, or unauthorized item | Generic denial and no partial item data; explicit related-ID requests do not confirm linkage |
| IR-07 | Read authorized follow task with unavailable/stale/unresolvable source | Own time unavailable, one generic temporal reason; no stored deadline, source/binding details, guessed date, or synthetic occurrence; agenda places core only in unplaced_items |
| IR-08 | Resolved empty recurrence range, truly unscheduled task, and unresolved time | Three distinct states per Section 4; unresolved is never reported as complete-empty or not_scheduled |
| IR-09 | Moves/exclusions/overrides, terminal instance, all-day/local/UTC windows, DST | New reads match canonical dates, start/end, effective lifecycle/actionability and occurrence identities without Kinflow expansion |
| IR-10 | Access revoked or granted during assembly; membership expires or activates without epoch write | Release fence invalidates the whole affected read; no mixed authorization snapshot or optional-section downgrade |
| IR-11 | Item/recurrence/source/binding changes during assembly or pagination | Expected-version guards and source fences reject stale results; unrelated hidden follower changes alone do not invalidate independent event facts |
| IR-12 | Multiple pages of occurrences, agenda and related sections; unplaced items | Deterministic ordering, combined limit, no duplicates/skips, valid authorized snapshots, fixed expiry; replay across account/selection/query/section/epoch denies |
| IR-13 | Read succeeds, then attempt update/cancel/complete with unavailable bound item | Existing edit/owner/reference restrictions still deny; no partial effects or authorization from read success; replay unchanged |
| IR-14 | Hidden graph grows or nested rendered/receipt/history content contains protected references | No hidden-dependent counts/cursors/diagnostics, serialization leak, or event traversal-capacity denial; indivisible protected evidence omitted safely |
| IR-15 | Old client/server, new client/server, unknown capability, rollback | Exact v1 contracts and failures preserved; v2 never mislabeled as canonical complete response; unknown/lost capability clears caches and stays explicitly unsupported |
| IR-16 | Kinflow identity switch, late response, unavailable optional details, unplaced task | Public contract suffices to render event occurrences and safe limitations; no parsing error messages, recurrence computation, hidden-task explanation, or stale deadline |

## 11. Remaining promotion gates

Ratify the separate read surface, authorized-only disclosure model, unavailable-time
union, and agenda unplaced stream. Then codify the complete field mappings, schemas,
registry, cursor normalization and authorization-transition proof, query/index budgets,
and executable matrix before runtime delivery. This draft and its handoff satisfy the
specification deliverables; they do not prove implementation conformance or staging
repair. Any later implementation or deployment is separate work.
