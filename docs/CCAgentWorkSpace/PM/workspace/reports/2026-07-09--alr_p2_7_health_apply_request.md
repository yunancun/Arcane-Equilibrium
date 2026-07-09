# PM Request - ALR P2-7 Health Apply

Date: 2026-07-09
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`
Target behavioral source head: `2a3a78465b802d8490a0e55b3452a87cbb46cf48`

Fresh facts: Linux source is clean/aligned; V155 is absent; three runs and two
feedback events exist; the current service is active on P2-6 source; and the
engine remains write-capable/excluded.

Requested actions: apply V155, reapply the role contract, update only the ALR
unit source head, daemon-reload/restart only that unit, then read one health
snapshot and verify false/zero authority, denied health UPDATE/DELETE, unchanged
engine, and no scanner/exchange/order/proof/serving/promotion action.
