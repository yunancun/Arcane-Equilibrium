# PM Apply Effect - ALR P2-6 Retention Guardian

Date: 2026-07-09
State: `P2_6_OPERATIONAL_COMPLETE_P2_7_ACTIVE`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

At aligned source head `14a09b5621f0c5e81018a0e9cd8ccccd1647c82a`, PM applied
V154, re-applied the revised role contract, and restarted only
`openclaw-alr-shadow.service` with the exact source-head pin.

Production did not receive synthetic cache data. The first guardian pass found
zero derived-cache entries and appended zero retention events. The isolated
probe separately proved quarantine -> grace recheck -> sweep against one
ALR-owned rebuildable cache while preserving its artifact/event lineage.

Live privilege reflection: cache UPDATE/DELETE are true; training-run
UPDATE/DELETE and scanner INSERT are false. Readback has zero cache entries,
zero retention events, three research-only runs, two deferred feedback events,
and zero duplicate source keys. Scanner count stayed `79770`; engine PID
`1561777` was unchanged. No external/order/probe/lease/Cost-Gate/proof/serving/
promotion/_latest/deletion outside derived cache action occurred.

P2-7 is active for health, state, metrics, restart-recovery, and authority
counters.
