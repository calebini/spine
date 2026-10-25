# Timezone compatibility runtime v1

Status: Accepted implementation contract for SPINE-062 (2026-10-22).
Implements [Decision 0006](decisions/0006-evidence-bound-timezone-compatibility.md).

`spine.timezone-compatibility.v1` is a closed, deployment-owned JSON baseline
catalog, selected by absolute `SPINE_TIMEZONE_BASELINES`. It is not ledger data.
The schema is `contracts/timezone-compatibility.schema.json`, also packaged
with Spine. Missing configuration preserves exact-release resolution and rejects
cross-release resolution. Invalid configured catalogs reject substitutions.

One immutable baseline per exact `(authored_version, timezone)` is supported in
v1. Provisioning selects the original build applicable to that deployment. Duplicate
keys, including alternate builds, are rejected; a different build needs a separate
catalog/deployment with independently established original provenance. This avoids
selecting whichever legacy artifact matches current bytes. Readers never enroll or
change evidence. Catalog permissions and authenticated source selection are the
operator's trust boundary; JSON provenance is an assertion, not a signature verifier.

`spine-timezone-baseline` captures selected zones from an explicitly supplied trusted
provider root, requiring its exact expected version, build identity, source origin,
and authenticated artifact SHA-256. It records the provider's complete `tzdata.zi`
SHA-256 as well as the full TZif fingerprint. It refuses conflicting existing entries,
serializes writers with a file lock, and atomically replaces the complete catalog.
Do not provide a new release's files with an old expected version: capture rejects
that mismatch. Retain catalogs while any authored pins require them. Provision
legacy references from the authenticated original distribution build, not a newly
compiled candidate chosen because it matches the host. No archive is downloaded
or trusted automatically by Spine.

The resolver chooses the first TZPATH root containing the requested zone and requires
valid `tzdata.zi` metadata from that same root; no fallback after that selection.
Capture checks file identity, size, mtime and ctime before and after reads. Files are
bounded (1 MiB zone/catalog, 4 MiB metadata); catalogs hold at most 4096 baselines.
Reads cache at most 64 captured files, 256 decoded zones, and eight parsed catalogs,
keyed by file identity/stat or complete bytes. Metadata is never cached by version
alone. Detected concurrent replacement fails closed. Providers must publish coherent
release trees; stat checks cannot make a package manager's multi-file installation
transactional. Stop resolution during an in-place upgrade, or atomically publish an
immutable provider tree for uninterrupted availability.

The exact captured bytes construct `ZoneInfo.from_file` and feed recurrence gap
parsing. Cross-release admission compares SHA-256 and byte length with the original
baseline; any runtime label is eligible, without a release-pair list. Structured
`timezone_compatible_substitution` warnings go to operational logging (CLI stderr),
including requested/runtime versions, zone, evidence ID and digest. Repetition is
bounded by an LRU of 1024 provider/evidence identities. Canonical envelopes are
unchanged. Ledger schemas remain 19 on mainline and 15 on the 0.6.0 maintenance line.
