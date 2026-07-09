# PM Apply Effect - ALR P2-7 Health State Metrics

Date: 2026-07-09
State: `P2_7_OPERATIONAL_COMPLETE_P2_8_ACTIVE`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

At source head `2a3a78465b802d8490a0e55b3452a87cbb46cf48`, PM applied V155,
re-applied the shadow role contract, and restarted only the ALR service with its
new source pin. Production appended one immutable health event and one health
snapshot artifact. Its payload shows watermark, scanner backlog `65`, outcome
feedback backlog `1`, latest target/run, four runs, three deferred feedback
gaps, restart duplicate count `0`, zero cache/retention bytes/events, zero
failure count, and zero run/feedback/exchange/trading/proof/serving authority
mismatches.

Health UPDATE/DELETE and scanner INSERT remain denied. Scanner count stayed
`79779`, and engine PID `1561777` remained unchanged. No venue/order/probe/
lease/Cost-Gate/proof/serving/promotion/_latest/deletion action occurred.

P2-8 is active: wait for three natural new Rust scanner cycles, then fresh-gate
one ALR-only restart/reconciliation to prove durable no-duplicate shadow soak.
