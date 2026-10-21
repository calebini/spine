# SPINE-062 timezone compatibility evidence

Date: 2026-10-21. Local investigation and proposed-design evidence only. No runtime
patch, deployment, production access or ledger change was performed.

Policy update, 2026-10-22: Decision 0006 now accepts automatic comparison against
trusted authored-zone references, without a release-pair allowlist. The results
below remain the original local evidence; they do not activate that policy or
restrict its applicability to these two zones/releases.

## Source and compilation

Downloaded the official IANA archives over HTTPS:

| Archive | SHA-256 |
| --- | --- |
| [tzdata2026c.tar.gz](https://data.iana.org/time-zones/releases/tzdata2026c.tar.gz) | `e4a178a4477f3d0ea77cc31828ff72aa38feff8d61aa13e7e99e142e9d902be4` |
| [tzdata2026e.tar.gz](https://data.iana.org/time-zones/releases/tzdata2026e.tar.gz) | `b26882805f26aac59d5b222978e6580484b834ccdc98be89df2f05a6dc53a652` |

Extracted `europe`, `northamerica`, `version` and `NEWS`. Both releases were compiled
with macOS `/usr/sbin/zic`, reporting `zic (tzcode) 2022g`; binary SHA-256
`63ca061febe265f7d27a48c15ee139e6966b9dc0aacfdf81bbfef97dddb21331`.
The internal `version` files identify 2026c and 2026e respectively.
No lower/upper time-range truncation, leap input or rearguard conversion was used.
For each release, the exact command pattern was:

```sh
/usr/sbin/zic -b fat -d <release>/fat <release>/europe <release>/northamerica
/usr/sbin/zic -b slim -d <release>/slim <release>/europe <release>/northamerica
```

Temporary source/compiled files are under `/private/tmp/spine-tzdb-compatibility/`.
They are not durable release artifacts or installed runtime data.

## Whole-file identity result

Each row's complete TZif bytes are identical between 2026c and 2026e. The digest
covers transition data and the future-rule footer, not a sampled time interval.

| Zone | Encoding | Bytes | SHA-256 in both releases |
| --- | --- | ---: | --- |
| Europe/Paris | fat | 2962 | `ab77a1488a2dd4667a4f23072236e0d2845fe208405eec1b4834985629ba7af8` |
| Europe/Paris | slim | 1105 | `cd588e779c5737d70e4e47158dafab7945b026b2bb34454cc47741815459b068` |
| America/Chicago | fat | 3592 | `feba326ebe88eac20017a718748c46c68469a1e7f5e7716dcb8f1d43a6e6f686` |
| America/Chicago | slim | 1754 | `c27b739ff46a7df0594e120d725b439217e11e44ea9a50cdc49130383b5482e7` |

This establishes equality for these reference builds. It does not establish that
the production Ubuntu zone files have these fingerprints, nor that all compiler
versions/options/vendor patches produce identical bytes. An implemented admission
mechanism must verify the bytes actually used by its resolver.

Negative controls: `America/Winnipeg`, `America/Inuvik` and `Europe/Dublin`
produce different whole-file bytes between the releases in both encodings.
They do not satisfy this evidence method for these reference builds and cannot
inherit the Paris/Chicago comparison result.

## Boundary probes and current-code reproduction

CPython 3.14.6 loaded each of the four release/encoding combinations using
`ZoneInfo.from_file`. For each local value, both folds were converted to UTC and
round-tripped; only candidates returning the original local value were retained.
All 18 probes produced the same set of valid UTC instants in all four combinations:

| Zone | Local date-times tested |
| --- | --- |
| Europe/Paris | `1800-01-01T12:00:00`, `1911-03-10T23:55:00`, `1945-09-16T02:30:00`, `1970-01-01T12:00:00`, `2026-03-29T02:30:00`, `2026-10-25T02:30:00`, `2027-01-01T12:00:00`, `2500-07-01T12:00:00`, `9998-07-01T12:00:00` |
| America/Chicago | `1800-01-01T12:00:00`, `1883-11-18T12:00:00`, `1945-09-30T01:30:00`, `1970-01-01T12:00:00`, `2026-03-08T02:30:00`, `2026-11-01T01:30:00`, `2027-01-01T12:00:00`, `2500-07-01T12:00:00`, `9998-07-01T12:00:00` |

Both 2026 spring-gap probes returned no valid instant. The Paris fall fold returned
`2026-10-25T00:30:00Z` and `2026-10-25T01:30:00Z`; the Chicago fall fold returned
`2026-11-01T06:30:00Z` and `2026-11-01T07:30:00Z`. A compatible resolver must retain
Spine's existing earliest-UTC choice. Boundary sampling supplements whole-file
identity; it is not itself the proof of equivalence or runtime regression coverage.

In current mainline, patched only the reported result of
`spine.core.schedule.system_timezone_database_version` to `2026e`, then called
`resolve_local_instant('2026-10-21T12:00:00', timezone=<zone>,
timezone_database_version='2026c')` for each zone. Both fail with
`environment_failure:timezone_database_version` and the reported mismatch message.
This reproduces the preflight rejection; it is not a production-data replay or an
end-to-end agenda/worker test. The actual local system reports `2026d-rearguard`.

## Remaining evidence

The [accepted logical decision](../specs/decisions/0006-evidence-bound-timezone-compatibility.md)
defines the required runtime and integration coverage. Production 0.6.0/schema 15,
the 33 affected schedules and wrapper behavior are operator-reported facts, not
locally inspected production state. The current checkout is 0.10.0/schema 19.
The deployed wrapper location and exact deployed source revision are still needed
for a bounded wrapper repair and production backport. No runtime compatibility
behavior has been activated by this investigation.
