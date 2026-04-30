# Active Docs Cleanup and Progress Recalibration

Date: 2026-04-30
Owner: PM

## Dispatch

Used the repo role roster instead of anonymous runtime names:

- `CC(default)`: compliance/doc-governance audit
- `FA(default)`: functional progress audit
- `E5(explorer)`: document bloat and archive target audit
- `PA(default)`: next-work arrangement
- `MIT(default)`: runtime/data calibration

## Verified Current Truth

- Mac/Linux source is at `5ba9b1c`.
- Linux runtime has been rebuilt from current source.
- Current health risk is not the old `[16]` gate; it is strategy edge observation: maker fill quality, grid lifecycle drift, and realized edge acceptance.
- Strategy Edge Models are deployed and need post-deploy cutoff observation.
- Dust Residual Prevention is deployed but still needs one real close-path proof.
- MLDE demo autonomy is active; live/live_demo auto-mutation remains governed by GovernanceHub, Decision Lease, and the live gates.

## Cleanup Decisions

Removed from active docs:

- closed 62-finding Batch A-F execution narrative
- STRKUSDT P0 wave / Wave A-H / old Wave 1-3 history from entrypoint/current-state summaries
- stale 2026-04-29 runtime facts
- obsolete `[16]`-as-main-blocker framing
- duplicated README hard-boundary code block

Correction after operator feedback:

- `TODO.md` was restored to the v3 single-timeline record shape.
- Only the confirmed stale active-mainline block was removed from TODO and archived separately at `docs/archive/2026-04-30--TODO-stale-active-mainline.md`.
- Historical Wave/Backlog records remain in TODO for continuity.

Preserved before trimming:

- `docs/archive/2026-04-30--CLAUDE-pre-cleanup-snapshot.md`
- `docs/archive/2026-04-30--TODO-pre-cleanup-snapshot.md`
- `docs/archive/2026-04-30--README-pre-cleanup-snapshot.md`
- `docs/archive/2026-04-30--active_docs_cleanup_archive.md`

## Updated Active Work Arrangement

1. P0: post-deploy edge observation through `[33]`, `[38]`, `[40]`; use post-deploy cutoff only.
2. P0: dust residual runtime proof on one real Demo/Live close path.
3. P1: G1-04 final fee/R:R compute around 2026-05-01/02.
4. P1: G2-02 ma_crossover replay around 2026-05-03.
5. P1: G2-01 PostOnly acceptance around 2026-05-07/08.
6. P3: Scout heartbeat production caller wiring.

## Linear Update

Updated Linear project `OpenClaw 62-Finding Remediation` as a high-level mirror:

- project summary/description now reflects closed remediation and active edge/dust follow-up
- Batch A-F issues `NCY-5`..`NCY-10` marked Done
- stale deploy/RCA issues `NCY-15` and `NCY-17` closed/superseded
- `NCY-12` moved to In Progress for G2-01 PostOnly acceptance
- new follow-up issues: `NCY-18` post-deploy edge observation, `NCY-19` dust residual runtime proof, `NCY-20` Scout heartbeat production caller wiring

Linear intentionally omits detailed runtime process state, secrets, and precise fill/fee internals.
