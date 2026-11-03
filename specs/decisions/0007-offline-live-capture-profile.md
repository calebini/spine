# 0007 — Separate offline live capture from deterministic work

Status: Accepted for the bounded SPINE-069 implementation, 2026-11-03.

The [live consumer contract](../contextual-notification-live-capture.md) adopts
the complete corrected Impetus schema from `5ff3c0c` under the unchanged
`impetus.openai.v1` wire version. It requires counting before one generation and
zero tools. The existing deterministic consumer, format 1, release 0.11.2, canonical
schema 19 and registered commands remain unchanged. This is a separately versioned
experimental module contract, not a new general runtime release or deployment.

Use a separate `LiveExperiment`, launcher and format-2 sidecar. Reuse existing source
projection and public synthetic authoring, without importing worker internals into
Spine. Format 2 atomically persists request bytes, source/config/disclosure
fingerprints and expected wire/schema/configuration/prompt bindings before launch.
The configuration encoding preserves insertion order; sorted JSON is not the
owner's revision encoding. SQL protects immutable export facts and append-only
captures; the launch marker can only move from zero to one.

The first initializer accepts only a new directory and creates its synthetic ledger
and sidecar. Low-level services assume a trusted operator and fresh synthetic source;
there is no claim to identify arbitrary real data by inspecting its content. There
is no format-1 migration, existing-opportunity profile switch or store reset path.

The launcher takes OS-trusted commands and a non-secret configuration artifact.
Invocation is disabled by default and validates that artifact against stored pins
before the durable marker. Readback uses a separate command and strips credential
environment variables and invocation flags. It may operate without the configuration
file or ambient profile JSON. Missing/changed ambient source configuration invalidates
hypothetical usability while preserving original execution readback.

A malformed response retains a normalized JSON digest when possible and a validation
classification, not unvalidated execution/accounting. Original request digests remain
over exact bytes. Valid failed/late/uncertain executions retain reported usage and
remaining reserves. Pending zero-call execution does not imply zero liability.
No fallback, resumed generation or new invocation follows missing evidence.

Qualification uses an independent worker process, fake clocks and mocked transport.
Every capture is selected=false/sent=false; canonical ledger writes and notification
attempts are outside capture. Real provider execution needs separate explicit
authorization and qualified configuration. General deferred resilience/storage work
and real-reminder disclosure are not prerequisites invented by this decision.
