# PM Request - ALR P2-4 Shadow Apply R2

Date: 2026-07-09
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`
Target behavioral source head: `cf2fb7607b5bacf35bc2a50f168453f10dfbada9`

R1's disposable container reached real `alr_shadow` reconciliation then exposed
the timestamp canonicalization defect. It was removed, and no production V152,
role change, unit change, or restart occurred. R1 authorization is not reused.

Fresh facts: Linux is clean at `7f5a56f44`, V152 is absent, the existing ALR
unit is active but unpinned, and 65 durable source rows remain. The existing
engine retains write-capable Demo flags and is excluded.

Requested actions are exactly: fast-forward source to the R2 head; apply V152;
reapply the reviewed ALR role contract; substitute only the R2 head into the
existing ALR unit; daemon-reload and restart that unit; read back the append-only
run and authority evidence. All prior exclusions remain in force.
