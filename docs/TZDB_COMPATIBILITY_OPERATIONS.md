# Operating timezone compatibility (SPINE-062)

The patch is available separately as mainline **0.10.1 / schema 19** and maintenance
**0.6.0+tzdb.1 / schema 15**. The maintenance branch starts at the operator-confirmed
production commit `a28bdf0e20cdb671e4a3862572d85c952f354056`. The `+tzdb.1` version
identifies a local maintenance build; it does not include the intervening releases.
Pin the full wheel version and commit when deploying. Neither patch migrates a ledger.

The resolver accepts another timezone release automatically when the complete TZif
bytes for the exact zone match a trusted authored-release fingerprint. It does not
need a release-pair allowlist. Changed bytes, missing evidence, or malformed provider
data still fail closed. Readback, receipts, occurrence IDs and work IDs retain their
authored timezone version. The [runtime contract](../specs/timezone-compatibility.md)
and [decision](../specs/decisions/0006-evidence-bound-timezone-compatibility.md) are authoritative.

## Provision the original reference

Catalog provisioning is a trusted deployment operation. Obtain the original
provider build from an authenticated distribution archive, verify the archive's
SHA-256 through that distribution's trusted metadata, and extract it into a
separate immutable directory. For this incident use the actual original Ubuntu
build, not a macOS compilation or the host's newer files. If the original build is
ambiguous, do not choose a fingerprint because it happens to match today's host.

After substituting verified paths and provenance, capture each required zone:

```sh
spine-timezone-baseline \
  --root /srv/spine/tzdb/original-2026c/usr/share/zoneinfo \
  --expected-version 2026c \
  --build-id ubuntu-tzdata-2026c-0ubuntu0.24.04.1 \
  --origin '<authenticated package origin and build provenance>' \
  --artifact-sha256 '<verified package SHA-256>' \
  --zone Europe/Paris --zone America/Chicago \
  --catalog /etc/spine/timezone-baselines.json
```

The tool compares the expected release to the supplied provider metadata, validates
complete TZif files, and atomically records their fingerprints and provenance.
It refuses replacement of an existing `(authored_version, timezone)` reference,
including a different build. Repeating the identical capture is safe. Retain the
catalog and trusted artifacts for as long as schedules require them. Back up the
catalog separately from the ledger; never manufacture old references from newer
files or edit receipts to supply evidence. Secure the catalog and parent directory
against writes by untrusted processes; the runtime only reads it.

Set `SPINE_TIMEZONE_BASELINES=/etc/spine/timezone-baselines.json` in every relevant
runtime environment (agent commands, agenda jobs, worker, and web service). A missing
variable preserves exact-release behavior and rejects cross-release resolution.
Readers never create the catalog. Before future host upgrades, capture current
trusted references for all zones used by newly authored schedules and retain earlier
references. This can be automated by deployment machinery; successful byte matching
does not require approval or catalog edits for each new runtime release.

## Validate the candidate before production rollout

Use the maintenance wheel for the existing schema-15 deployment. Verify `system info`
reports the expected full runtime version, schema and actual host timezone version.
On an approved disposable production backup, run both reported route agendas with
their original request parameters and the configured catalog. Verify all expected
items, original authored pins, unchanged receipts and read-only ledger state. Test
notification preparation with fake transport only. Record loaded zone digests and
the `timezone_compatible_substitution` diagnostic, which includes requested/runtime
versions, exact zone, evidence ID and actual digest. CLI diagnostics are logged to
stderr; worker/service operators must retain their stderr or configured Python logs.
CLI JSON stdout remains unchanged. Verify the service user can read the catalog.

A package manager can replace provider files non-atomically. Stop timezone-dependent
work during an in-place tzdata upgrade, or configure Python's `PYTHONTZPATH` to an
atomically published immutable tree. The resolver detects changes during capture
and invalidates caches by file identity; it cannot make a package installation
transactional. No migration or canonical-data rewrite is required for this patch.
Rollback restores the prior application wheel/configuration; removing the baseline
catalog restores cross-release rejection, and does not recover availability when
the original timezone data remains absent.

The actual OpenClaw daily-agenda wrapper is outside this repository. Its reported
failure-to-success exit handling remains a separate integration fix requiring its
source/location. This patch preserves the Spine CLI's nonzero failure exit and
`ok: false` envelope. It does not silently omit unresolved schedules from agendas.

Detailed local results: [two-line patch validation](TZDB_COMPATIBILITY_VALIDATION.md).

## Local validation boundary

Checked-in test fixtures are complete IANA 2026c/2026e TZif files compiled on macOS,
with unchanged Paris/Chicago/Toronto and changed Winnipeg/Dublin controls. Tests cover
unknown and reverse runtime releases, historical offsets, gaps/folds, distant future
footer rules, immutable baseline ingestion, malformed data, provider/cache races,
CLI agenda/read-only invariants, opportunity identities and worker preparation with
fake transport. These tests validate the mechanism; they do not authenticate the
production Ubuntu build or replace the disposable-production-backup check above.
