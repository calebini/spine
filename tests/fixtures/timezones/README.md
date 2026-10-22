# TZif compatibility fixtures

Full fat TZif files compiled from the public-domain IANA 2026c/2026e `europe`
and `northamerica` sources using macOS `/usr/sbin/zic` (2022g), `-b fat`.
See docs/TZDB_COMPATIBILITY_EVIDENCE.md for archive/compiler hashes and provenance.
`manifest.json` records each complete file digest; `tzdata.zi` is a test-only
version header. Paris, Chicago and Toronto match; Winnipeg and Dublin differ.
Tests relabel copies to exercise unknown/reverse releases. These are synthetic
provider fixtures, never a production baseline catalog.
