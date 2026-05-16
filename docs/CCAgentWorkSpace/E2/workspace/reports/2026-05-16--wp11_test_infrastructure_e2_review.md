# E2 PR Adversarial Review -- WP-11 Test Infrastructure -- 2026-05-16

## 改動範圍

7 files changed, +130 insertions, -79 deletions

| File | Type | Delta |
|---|---|---|
| test_track_a_spawn_argv.py | test | 10 test fixes (envelope keys, signing key, field count, allowlist) |
| test_ai_budget_routes.py | test | 1 test fix (IPC error dict format) |
| test_executor_shadow_toggle_api.py | test | 1 test fix (IPC error dict format) |
| test_strategist_promote_api.py | test | 1 test fix (IPC error dict format) |
| test_batch_d_risk_fail_closed.py | test | 1 test fix (dispatch_tests.rs file move) |
| test_replay_subtab_static_assets.py | test | 1 test fix (tab-live.html refactor) |
| E4/memory.md | docs | E4 memory entries for fixes |

Production code changes: **0** (verified via `git diff HEAD --name-only | grep -v tests/ | grep -v CCAgentWorkSpace` = empty)

## 8 items CLAUDE.md section 9 checklist

| Item | Status |
|---|---|
| Scope matches PA plan | PASS -- all 6 test files within stated WP-11 scope |
| No except:pass or silent swallow | PASS -- grep = 0 hit |
| Logging uses %s format (no f-string) | PASS -- no logging added |
| New API endpoint has _require_operator_role() | N/A -- no API endpoints |
| except HTTPException: raise before except Exception | N/A -- no exception handlers added |
| detail=str(e) replaced with "Internal server error" | N/A -- no production error paths |
| No blocking threading.Lock in asyncio routes | PASS -- no Lock added |
| No private attribute access (._xxx) | PASS -- grep = 0 hit |

## OpenClaw 9 items section 3 checklist

| Item | Status |
|---|---|
| Cross-platform grep (no /home/ncyu or /Users/[^/]+) | PASS -- 0 hit on all diff |
| Bilingual comments | PASS -- 2026-05-05 new rule: Chinese-only; all new comments are Chinese |
| Rust unsafe zero tolerance | N/A -- no Rust changes |
| Cross-language IPC schema consistency | N/A -- tests track existing schema |
| Migration Guard A/B/C | N/A -- no SQL migrations |
| Healthcheck pairing | N/A -- no passive-wait TODOs |
| Singleton registration | N/A -- no new singletons |
| File size 800/2000 limit | PASS -- test_track_a_spawn_argv.py = 733 lines (under 800) |
| Bybit API dictionary check | N/A -- no Bybit API changes |

## Adversarial cross-check results

1. Q: test_post_config_returns_503_on_ipc_error mocks RuntimeError on IPC call -- does this flow through ipc_error_handler generic path or _get_ipc_client path?
   A: patch_raising injects FakeRaisingClient which returns from _get_ipc_client() successfully, then raises on update_ai_budget_config(). This hits the except Exception at ai_budget_routes.py:222 -> raise_http_for_ipc_error -> ipc_error_handler.py:125 generic fallback -> sanitize_exc_for_detail(exc, "ipc_error"). Test assertion "ipc_error" in reason_codes is CORRECT.

2. Q: Envelope assertion weakened from exact value to existence-only -- is this papering over a bug?
   A: No. Round 6 changed write_manifest_fixture to compute real HMAC signatures (route_helpers.py:1048-1051). Signature value is non-deterministic (depends on key + body canonical bytes). Existence check is appropriate. Canonical byte-equal test (test_write_manifest_fixture_byte_equal_canonical_with_non_ascii) separately verifies signing integrity via SHA-256 cross-check. LOW finding, acceptable.

3. Q: _applyLiveTodayPnl(m) assertion less specific than old if (metricsData) version -- regression risk?
   A: Production tab-live.html:1682-1683 has `const m = d.data; _applyLiveTodayPnl(m);`. The substring `_applyLiveTodayPnl(m)` is unique in the file (2 total occurrences: definition + call). Tight enough.

4. Q: resolve_artifact_allowlist_root() in spawn tests -- does this create side effects on Mac dev filesystem?
   A: Returns `/tmp/replay_artifacts_test_only` on macOS. Test creates subdirs under it (test_argv, test_alive, test_dead). These are ephemeral test artifacts. No side effects on production paths.

5. Q: _signing_key_env fixture -- any risk of key leakage?
   A: Key = `"ab" * 32` (deterministic test-only). Written to `tmp_path` (pytest auto-cleaned). Env var set via monkeypatch (auto-reverted). No real secrets, no production paths. Clean.

## Findings

| Severity | Location | Description | Action |
|---|---|---|---|
| LOW | test_track_a_spawn_argv.py:114-116 | Envelope assertion weakened from exact value match to existence-only. Justified by non-deterministic HMAC signing. Canonical byte-equal test covers integrity. | Accepted, no action required. |

## Conclusion

**PASS to E4** -- 0 BLOCKER, 0 HIGH, 0 MEDIUM, 1 LOW (accepted)

All 15 test fixes correctly track real production behavior changes (WP-05 error sanitize dict format, Round 6 HMAC signing, dispatch_tests.rs file move, tab-live.html refactor). No assertion weakening that papers over bugs. Zero production code modified.
