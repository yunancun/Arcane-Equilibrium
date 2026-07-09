# PM Authorization - ALR P2-7 Health Apply

Date: 2026-07-09
State: `AUTHORIZED_EXACT_P2_7_HEALTH_APPLY`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

PM accepts the fresh gate without expansion. Apply only V155, the reviewed role
contract, source-head-pinned ALR unit update, and restart of that one service at
`2a3a78465b802d8490a0e55b3452a87cbb46cf48`. Stop on drift/mismatch; external,
execution, proof, serving, promotion, `_latest`, and deletion paths remain denied.
