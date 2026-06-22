# Sealed Horizon Preflight Refresh Wrapper

## 結論

v395 新增 `helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh`，把 sealed horizon bounded demo-probe preflight 從人工 one-off 命令提升為可重跑、可觀測的 artifact refresh wrapper。

這是盈利工程閉環的一小步：它讓系統能持續刷新「被 Cost Gate 擋掉但 sealed evidence 顯示可能有 edge」的 preflight 證據，避免最新指標停在手工 smoke 或讀錯 generic latest。它不降低 Cost Gate，也不授權 probe/order。

## Source Changes

- `helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh`
  - 讀 sealed learning evidence、optional explicit decision packet、decision-packet search root、activation preflight、stack health、operator review artifact。
  - 調用 `python -m cost_gate_learning_lane.sealed_horizon_probe_preflight`。
  - 寫 dated/latest `sealed_horizon_probe_preflight_*.{json,md}`。
  - 追加 `sealed_horizon_probe_preflight_refresh_status_v1` 到 `logs/sealed_horizon_probe_preflight.log`。
  - 更新 `cron_heartbeat/sealed_horizon_probe_preflight.last_fire`。
  - 缺 sealed evidence 時只記錄 `SEALED_HORIZON_EVIDENCE_MISSING`，不創建 fake latest。

- `helper_scripts/cron/tests/test_sealed_horizon_probe_preflight_cron_static.py`
  - 覆蓋 bash syntax、executable/strict mode、resolver search-root wiring、status fields、fail-soft missing evidence、forbidden trading/runtime tokens。

- `helper_scripts/SCRIPT_INDEX.md`
  - 登記 wrapper、建議 cron、輸出位置與 hard boundary。

## Verification

Mac:

- `bash -n helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh` passed.
- `PYTHONPATH=helper_scripts/research python3 -m py_compile ...` passed.
- Focused wrapper static pytest：`5 passed`.
- Combined wrapper + sealed preflight pytest with `--import-mode=importlib`：`10 passed`.
- Cron static directory：`144 passed`.
- No-evidence wrapper smoke wrote status `SEALED_HORIZON_EVIDENCE_MISSING`.
- `git diff --check` passed.

Linux `trade-core`:

- Source fast-forwarded to `1f82f87c2b4a069043865e8ef7b6316ee223c1ea`.
- `bash -n` passed.
- py_compile passed.
- Combined focused pytest：`10 passed`.
- Wrapper smoke refreshed canonical latest:
  - Output：`/tmp/openclaw/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json`
  - sha256：`5cae49e9837285aced6835ff8199e3b2183c669846b5fd8a59cd0c11a47b157d`
  - status：`OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED`
  - side-cell：`ma_crossover|BTCUSDT|Sell`
  - horizon：`240`
  - selected decision packet：`/tmp/openclaw/profitability_refresh/20260622T031320Z/profit_learning_decision_packet_v389/profit_learning_decision_packet_v389_latest.json`
  - `decision_packet_aligned=true`
  - blocking gates：`operator_sealed_horizon_review_recorded`, `production_learning_lane_accumulating`

## Boundary

- No CI run.
- No PG write/schema migration.
- No Bybit private/signed/trading call.
- No deploy/rebuild/restart.
- No crontab install.
- No env/auth/risk/order/strategy/runtime mutation.
- No Cost Gate lowering.
- No probe/order authority.
- No promotion proof.

## Profitability Implication

The current leading path remains `ma_crossover|BTCUSDT|Sell@240m`: offline sealed evidence says the rejected signals had positive 240m blocked-outcome markouts, but this is not yet execution proof.

The wrapper improves the system's ability to keep that path current and machine-checkable. The next profit-relevant gates are unchanged:

- actual operator review/approval artifact, not Codex-generated defer/pending review;
- production learning-lane accumulation via ledger/outcome rows;
- then a separate, bounded, Rust-authorized demo-probe decision if the previous gates pass.

The strategy remains to cross the Cost Gate through sealed side-cell/horizon specialization and real demo learning, not a global Cost Gate relaxation.
