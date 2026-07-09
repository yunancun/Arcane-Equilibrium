# PM Authorization - ALR P2-6 Retention Apply

Date: 2026-07-09
State: `AUTHORIZED_EXACT_P2_6_RETENTION_APPLY`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

PM accepts the fresh gate without expansion. Apply only V154, the reviewed role
contract, the source-head-pinned ALR unit update, and restart of that unit at
`14a09b5621f0c5e81018a0e9cd8ccccd1647c82a`. Production cache seed/sweep is not
authorized because no actual cache row exists. Stop on any drift or boundary
mismatch; all execution/proof/promotion/external paths remain denied.
