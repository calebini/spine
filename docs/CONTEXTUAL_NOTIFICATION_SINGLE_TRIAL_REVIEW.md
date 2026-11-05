# First synthetic provider capture through Spine

On 2026-11-04 Europe/Paris, the operator-authorized SPINE-071 trial completed
through Spine checkpoint `1f7947d0e9894729ecd1d3cf46faf9a81fdb3595` and the
independent Impetus worker at `5ff3c0c4530fe07e81cc9067eddadd967a90acc4`.
There was **one provider count, one generation, zero retries/tools and zero
notification attempts**. The result was successful `no_addition`:

> The reminder is already clear, and no lesson details are provided to support a useful additional line.

The ordinary preview was `Reminder: Synthetic lesson in 1 hour`. This is a valid
outcome for the sparse synthetic input, not evidence of general reminder usefulness.
No real source ledger or recipient was used. All captures remain selected=false
and sent=false. No feature was activated or deployed.

The [preparation plan](CONTEXTUAL_NOTIFICATION_SINGLE_TRIAL_PLAN.md),
[implemented contract](../specs/contextual-notification-live-capture.md) and
[original handoff](CONTEXTUAL_NOTIFICATION_LIVE_CAPTURE_HANDOFF.md) define the
scope. SPINE-071 in [the backlog](BACKLOG.md) holds completion evidence and limits.

## Exact bindings and observed accounting

| Observation | Retained value |
| --- | --- |
| Wire interface / version | `contextual-notification-experiment` / `impetus.openai.v1` |
| Complete schema SHA-256 | `bf3d132392c41ab21e9f7bf44f765aa79799a8dd41f8666d1d39ad646c442c4b` |
| Original request SHA-256, including final newline | `105081cf36f52503d679756d12b1bc4a330f4260e8873f67e252d4b9074c3980` |
| Configuration revision | `openai.responses.v1:88ad7139cd591f01ceb017b46b491525554aa377be257aa2c64434dd6cdb8e12` |
| Prompt / model / effort | `helpful-personable-openai.v1` / `gpt-6-luna` / low |
| Owner execution start | 2026-11-03T23:58:34.856Z |
| Owner completion | 2026-11-03T23:58:39.278Z |
| Source cutoff / expiry | 2026-11-04T00:00:34Z |
| Execution elapsed / complete prepare-invoke-read wall time | 4.422 seconds / 4.935 seconds |
| Count ordinal 1 / generation ordinal 2 input | 244 / 244 tokens |
| Generation output / total | 92 / 336 tokens |
| Reported reasoning tokens, already included in output | 48 |
| Computed generation usage at configured rates | 152,800 nanodollars = USD 0.0001528 |
| Remaining generation reservation | 3,431,200 nanodollars = USD 0.0034312 |
| Retained unknown counting contingency | 1,000,000 nanodollars = USD 0.001 |
| Original admission / retained daily exposure | 4,584,000 nanodollars = USD 0.004584; one owner run |

Usage plus remaining reservations equals original admission. No reserve was
released, no zero counting fee was assumed, and reasoning was not charged twice.
Computed usage is not an invoice. An illustrative generation-only calculation at
published Standard short-input base rates is USD 0.0000704; final applicable
account/caching/counting charges were not independently observed.

Official [model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna)
and [pricing](https://developers.openai.com/api/docs/pricing) were reopened for
this trial. They still list Standard base USD 0.10 input / USD 0.50 output per
million. The table includes a USD 0.25 twelve-hour cache-write rate, and regional
premiums are described. Even the illustrative additive input allowance
`(0.10 + 0.25) * 1.10 = 0.385` and output `0.50 * 1.10 = 0.55` are below the
configured USD 0.40 / USD 0.60. That is conservative local arithmetic, not proof
of account billing. The [counting guide](https://developers.openai.com/api/docs/guides/token-counting)
does not establish a counting fee; its contingency remains an accepted allowance.

## Retained readback and the timestamp limitation

The initial invoke capture and immediate credential-free readback both passed
the owner schema and Spine's semantic checks, with current source and completion
before cutoff. Both nevertheless recorded hypothetical usability=false:

- Completion was `23:58:39.278Z`.
- Spine's observation formatter retained `23:58:39Z`, truncating fractional seconds.
- Its conservative `completion <= observation` comparison therefore failed.

A later actual credential-free read at `23:58:56Z`, still before cutoff, retained
the identical execution and correctly recorded usability=true. The first two
records remain unchanged. This was readback only; no count or generation repeated.
The three captures all have selected=false/sent=false.

This is a newly observed precision issue in the checkpointed capture code,
not provider lateness, stale source or an invalid result. This execution step
does not repair it. The next bounded implementation candidate is to preserve
appropriate observation precision and add an offline same-second completion
regression, without weakening freshness/cutoff checks or requiring another paid
trial. That was the next candidate at trial completion. The operator subsequently
selected the offline correction on 2026-11-05; SPINE-072 in the backlog records
its implementation and verification. The original trial records remain unchanged.

## Verification and limits

Offline post-run verification checked the complete request/read/response schemas
and consumer semantics; exact request bytes/digest in both stores; immutable
binding and marker=1; one owner run; operation order and count/generation body
digest linkage; prompt/config/model identity; tokens, usage and reserves; unchanged
logical canonical source; and zero `side_effect_attempts`. An additional independent
CLI read used an allowlisted credential-free environment, no live/config flags,
and left the owner's logical state unchanged. All execution values match across
the three captures and the independent read envelope.

The stores, original bytes, bindings, non-secret configuration, capture JSON,
independent readback, authorization/prelaunch manifests and verification report
are retained together in operator-owned local trial storage outside both
checkouts. Credential values and resolved credential-file locators are absent
from requests/configuration/captures/reports. Only Impetus opened the existing
private credential file; its contents were never displayed or copied into evidence.
No earlier owner's trial store was reused, renamed or changed.

At trial completion, runtime, tests, contracts/resources and Impetus files were unchanged.
Full regression and installed-wheel evidence from SPINE-069 described that
identical executable snapshot; SPINE-072 records subsequent offline verification
of the precision correction. This trial adds actual provider evidence for one
successful no-addition path, with the precision limitation above. It does not
qualify live addenda, failure/restart campaigns, real-reminder disclosure, final
billing, generated delivery or deployment. The single invocation authorization
is fulfilled and grants no further provider execution.
