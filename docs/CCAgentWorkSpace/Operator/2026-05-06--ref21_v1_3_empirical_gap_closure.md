# REF-21 V1.3 Empirical Gap Closure

**Date:** 2026-05-06
**Status:** P0 partial closure landed; R2/R3 remain BLOCKED

Accepted the final real-code audit and patched the highest-risk drift:

- §10 replay baseline no longer confuses pytest `2555/17` with replay fixture
  rows and decisions.
- full-chain prepare now requires `OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP=1` under
  live release profile before any bulk Bybit fetch.
- V057-V060 now exist as migration files, so MIT can run a real Linux PG
  dry-run instead of reviewing markdown sketches.
- GUI/CLAUDE tab contract is corrected to 13 tabs.
- LOC governance is restored in REF-21 active plan.

Remaining hard blockers: MIT PG dry-run, real SECURITY DEFINER calculator body,
true `/api/v1/replay/full-chain/run`, replay-dedicated rate/IP isolation, and
Bybit ToS/fair-use operator review.
