# QA Runtime Acceptance - ALR P2-8 Shadow Soak

Date: 2026-07-10
Verdict: `PASS_DONE_OPERATIONAL_SHADOW`
Authority chain: PM -> E3 -> BB -> QA -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

Source verification at behavioral commit `26401fbbce9a97e68583a5b8f069ffa3fba0a4d1`
passed the full ALR suite (`220 passed`), `py_compile`, and `git diff --check`.
The production soak used raw scanner baseline `79786` at
`2026-07-09 23:53:38.956+02`, then a temporary one-shot UTC cursor. The closed
window through `2026-07-09 23:59:24.432076+02` proves raw scanner rows / ALR
source rows / raw-only / ALR-only / duplicate keys = `5/5/0/0/0`. The three
required post-baseline identities are present `3/3`, with zero missing.

`openclaw-alr-shadow.service` restarted from PID `1973155` to `1982389` with
the cursor, then to `1982461` after its drop-in was removed. It remains active
with `NRestarts=0`; no soak drop-in remains. The first restart produced a
bounded normal drain plus five cursor rows, and the recovery restart produced a
second `DEFER_EVIDENCE` scanner statistical target/run. Health snapshots at
`23:59:20+02` and `23:59:24+02` recorded zero duplicate keys and zero authority
mismatches. Scanner privileges remain SELECT-only for `alr_shadow`; INSERT,
UPDATE, DELETE, and training-run UPDATE/DELETE are denied.

At `23:59:57+02`, after the closed ALR validation window, an unattributed
external engine restart changed its PID from `1561777` to `1983100`. No ALR
operation touched that process, but this drift means every future Demo/P3 gate
must refresh runtime state. It does not alter the timestamped P2 source-set,
restart, target, or zero-authority evidence above.
