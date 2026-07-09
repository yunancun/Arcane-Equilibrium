# PM Request - ALR P2-6 Retention Apply

Date: 2026-07-09
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`
Target behavioral source head: `14a09b5621f0c5e81018a0e9cd8ccccd1647c82a`

Fresh facts: Linux source is clean and aligned; V154/cache table is absent; two
ALR runs and one feedback event exist; the current service is active on the P2-5
source pin; the engine retains write-capable Demo flags and is excluded.

Requested actions: apply V154, reapply the ALR role contract, update only the
existing ALR unit source head, daemon-reload/restart only that unit, then verify
zero production cache entries/events, no non-cache write privileges, and no
engine/scanner/exchange/order/proof/serving/promotion action. No production test
cache entry may be inserted.
