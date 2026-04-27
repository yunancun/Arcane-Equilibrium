# E2 Adversarial Review — `d4bc9eb` (healthcheck+observer 4 fixes)

**Date**: 2026-04-27
**Reviewer**: E2 (subagent — adversarial code reviewer)
**Verdict**: **RETURN to E1** (2 HIGH findings)

## Scope

7 files, +482 / -62 lines.
- `helper_scripts/db/passive_wait_healthcheck/checks_engine.py` — [3] ratio threshold + [23] JOIN fix
- `helper_scripts/db/passive_wait_healthcheck/checks_strategy.py` — [24] paper-disabled skip
- `program_code/exchange_connectors/bybit_connector/io_and_persistence/_bybit_private_check_stub.py` — NEW shared helper (155 lines)
- 4 thin wrapper rewrites (account/positions/order_history/execution_history)

## High-Severity Findings (2)

### H1 — `checks_strategy.py` exceeds CLAUDE.md §九 1200-line hard limit
- Pre-fix: 1154 lines · Post-fix: **1201 lines** (47-line addition pushes 1 over)
- CLAUDE.md §九 explicit rule: "1200 行 🛑 拒絕 merge"
- Fix: collapse 1 redundant inline comment line (e.g. lines 1119-1122 PAPER-DISABLED-SKIP Chinese inline can be 3 lines instead of 4) so `wc -l ≤ 1200`.

### H2 — [3] `check_exit_features_writer` regression at 50% drop boundary
- Post-fix logic: `ratio < 0.5 → FAIL`, `< 0.7 → WARN`, else PASS.
- Boundary case: 50% writer drop (close_fills=10, EF=5 → ratio=0.5) does NOT satisfy `< 0.5`, falls into `< 0.7` → **WARN, not FAIL**.
- `runner.py` line 8: "0 = all checks PASS or only WARN" — cron does NOT exit 1 on WARN, so operator is not paged.
- Pre-fix: same case (delta=5, threshold=max(3,3)=3, 5>3) → FAIL.
- **Detection capability lost**: low-volume periods (sparse fills) where writer half-dies will be silenced from FAIL → WARN.
- Fix A: `ratio <= 0.5 → FAIL` (catch 50% boundary).
- Fix B (recommended): keep ratio band but add absolute floor — `if ratio < 0.5 or (close_fills >= 20 and (close_fills - n) >= 10): FAIL`. Update docstring.

## Medium-Severity Findings (2 — non-blocking)

### M1 — Commit message claim "byte-identical" inaccurate
- Original `.orig` (commit `4073875`) checked `~/BybitOpenClaw/secrets/secret_files/bybit/prod/api_key` only.
- New helper `_bybit_private_check_stub._key_configured` checks `demo + prod` slots.
- On Linux production where operator only has demo slot populated, retMsg flips from `api_key_not_configured` → `not_implemented`.
- Verified downstream consumers (`bybit_private_rest_preflight_guard` / `bybit_snapshot_to_postgres` / `bybit_observer_acceptance_check` / `bybit_failure_policy_builder`) read only `ok` boolean — no text matching on retMsg → **functional behavior preserved**.
- Code is correct (demo+prod is the right Linux deploy reality); only commit message wording needs revision.
- Fix: in follow-up commit / changelog amendment, document as "schema-identical, retMsg now demo-aware".

### M2 — [24] paper-disabled-skip lacks mtime guard
- `pipeline_snapshot_paper.json` is rewritten by `main_pipelines.rs:228` on every engine startup; under normal flows the marker is fresh.
- Edge case: operator flips `OPENCLAW_ENABLE_PAPER=1` + restarts engine, but paper pipeline silently crashes before overwriting marker → marker stuck `disabled=true` → check perpetually PASS while paper writer is dead.
- Low-probability but real silent-dead vector, exactly what passive_wait_healthcheck is supposed to catch.
- Fix (follow-up): add 6h mtime guard: `if disabled and mtime > now-6h: fall through to staleness check`.

## Low-Severity Findings (2 — nits)

- `bybit_private_execution_history_check.py` no-op stops dated history writes; harmless for fossil-LATEST design but lose audit trail. Document as expected.
- `_bybit_private_check_stub.srv_root` "." fallback is fragile when cwd=`/`. Both Mac dev and Linux cron set the env vars explicitly so not triggered in practice, but `Path(__file__).resolve().parents[N]` would be more robust.

## Cross-Platform / §七 Compliance

- Bilingual MODULE_NOTE + docstring + inline comments throughout new code: PASS.
- No `/home/ncyu` or `/Users/[^/]+` hardcoded paths in new code: PASS.
- `OPENCLAW_SECRETS_DIR` → `OPENCLAW_SECRETS_ROOT` → repo-relative fallback chain validated (Mac dev resolves to `/Users/ncyu/Projects/TradeBot/secrets/...`).

## Adversarial Validation Performed

1. Verified Rust `trading_writer.rs:472-505` (`flush_orders` 11-column INSERT, no `context_id`) and `:259-338` (`flush_fills` 16-column INSERT, includes `order_id` and `context_id`). [23] JOIN fix is structurally correct.
2. Verified `4073875` original `.orig` content vs new helper `emit_stub` schema — same fields, different secret-slot lookup logic.
3. Verified `runner.py:107-111` exit-code contract — WARN does not exit 1.
4. Verified `cron_observer_cycle.sh:37` exports `OPENCLAW_SRV_ROOT="$REPO"` so cron-time srv_root resolves correctly even with `cwd=$HOME`.
5. Verified `main_pipelines.rs:147-228` paper disable marker is one-shot startup write.
6. Grep'd downstream retMsg consumers (`bybit_private_rest_preflight_guard`, `bybit_observer_acceptance_check`, `bybit_failure_policy_builder`, `bybit_snapshot_to_postgres`) — all read only `ok` boolean / `retCode == 0`, none match retMsg strings.

## Return Path

E1 to address H1 + H2; M1/M2/L1/L2 may be deferred to follow-up commits.
After fix → re-E2 → E4.
