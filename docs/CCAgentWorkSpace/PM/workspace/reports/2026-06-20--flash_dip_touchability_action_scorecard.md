# FlashDip Touchability Action Scorecard

Date: 2026-06-20
Owner: PM
Scope: alpha-discovery runtime diagnostics only

## Summary

FlashDip was blocked as `CAPTURING_NO_TOUCH`, but the blocker only said to wait for a touchable dip or use L1 replay later. That was not enough: the existing touchability K-ladder already contained information about which shallower K bands are touchable.

This checkpoint adds a diagnostic-only action scorecard to the FlashDip touchability detail and carries it into the alpha-discovery profitability blocker row. It does not retune K, change strategy parameters, change order behavior, or authorize promotion.

## Source Change

- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - Added `_flash_dip_touchability_action_scorecard(touch_detail)`.
  - For fresh touchability artifacts, it reads current K, current touches, and the K-ladder.
  - If current K has zero touches but any lower K has touches, it selects the deepest lower-K candidate with touches and returns `SHALLOW_REPRICE_RESEARCH_BAND_PRESENT`.
  - All output is marked `diagnostic_only_not_retune_or_promotion_authority`.
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - FlashDip `CAPTURING_NO_TOUCH` blocker now includes action-scorecard fields.
  - When status is `SHALLOW_REPRICE_RESEARCH_BAND_PRESENT`, next trigger becomes `run_shallow_k_execution_realism_then_l1_replay_before_any_retune`.
- `helper_scripts/research/tests/test_alpha_discovery_throughput.py`
  - Pins the K15 no-touch / K6 shallow-candidate behavior and blocker next trigger.

## Runtime Evidence

Latest Linux alpha-discovery artifact:

- Path: `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
- SHA256: `8d5f58856ece9ff6e79839fbe055782a62a7517b41e1210b9fd6271a7160dd96`
- `created_at_utc`: `2026-06-20T17:38:03.411654+00:00`
- Global score: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- Ready/probe: `0`

FlashDip touchability:

- Current configured K: `15`
- Current touched count: `0/18`
- Current touch rate: `0.0%`
- Deepest lower-K research candidate: `K6`
- Candidate touched count: `2/18`
- Candidate touch rate: `11.1111%`
- Touchable lower-K candidate count: `7`

FlashDip blocker row:

- `blocker_class`: `event_wait`
- `primary_blocker`: `configured_flash_dip_limit_not_touchable`
- `touchability_action_status`: `SHALLOW_REPRICE_RESEARCH_BAND_PRESENT`
- `research_candidate_k_pct`: `6.0`
- `research_candidate_touched_count`: `2`
- `next_trigger`: `run_shallow_k_execution_realism_then_l1_replay_before_any_retune`

## Interpretation

The old state was correct but too passive: K15 is not touchable in the current sample. The stronger diagnosis is that the K-ladder already identifies K6 as the deepest shallower band with real touches. That does not make K6 profitable, executable, or safe, but it does define the next research test: rerun execution realism and L1 replay on the shallow-K candidate before any retune proposal.

## Verification

Mac:

- `env PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> `22 passed`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py` -> PASS
- `git diff --check` -> PASS

Linux selective source sync:

- Focused alpha-discovery pytest -> `22 passed`
- Runtime/discovery py_compile -> PASS
- Targeted `git diff --check` -> PASS
- Read-only alpha-discovery runtime smoke -> PASS

## Boundary

- No PG table write or schema migration.
- No Bybit private/signed/trading call.
- No engine/API rebuild or restart.
- No credential/auth/risk/order/strategy mutation.
- No live/demo retune.
- No promotion proof.
