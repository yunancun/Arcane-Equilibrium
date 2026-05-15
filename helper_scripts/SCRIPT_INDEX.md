# helper_scripts/ — 腳本索引 (Script Index)

本目錄存放 OpenClaw 系統的維護、啟動、CI 輔助腳本。
最後更新：2026-05-15（W-AUDIT-8a C1 liquidation topic standalone probe + AMD-2026-05-15-01：W2 paper edge report 降級為 Stage 0R diagnostic；保留 W-AUDIT-4b feature baseline scheduled apply + [67] healthcheck 與 2026-05-09 W-AUDIT-1 catch-up 索引）

## 2026-05-09 W-AUDIT-1 補登

| 腳本 | 用途 |
|------|------|
| `db/audit/2026-05-09_3c_7d_audit.sh` | 3C deploy 7d follow-up read-only audit wrapper |
| `db/audit/2026-05-09_3c_7d_audit.py` | 3C deploy 7d follow-up SQL audit implementation |
| `db/audit/2026-05-16_funding_arb_14d_audit.sh` | funding_arb 14d audit wrapper |
| `db/audit/2026-05-16_funding_arb_14d_audit.py` | funding_arb 14d audit SQL implementation |
| `db/passive_wait_healthcheck/__main__.py` | `python -m helper_scripts.db.passive_wait_healthcheck` entrypoint |
| `db/passive_wait_healthcheck/runner.py` | Passive healthcheck orchestrator and output formatter |
| `db/passive_wait_healthcheck/checks_agent_spine.py` | `[55]` Agent Decision Spine lineage / MAG-082 readiness check |
| `db/passive_wait_healthcheck/checks_live_pipeline.py` | `[56]` Live / LiveDemo pipeline active healthcheck |
| `db/passive_wait_healthcheck/checks_btc_lead_lag.py` | `[57]` W2 A4-C BTC→Alt Lead-Lag panel 4 conditions healthcheck (W2-IMPL-3 2026-05-11) — panel freshness < 120s + cohort=7 + regime extreme < 5% + book_imbalance non-zero/non-null; opt-in `OPENCLAW_W2_HEALTHCHECK_ENABLED=1` |
| `db/passive_wait_healthcheck/checks_feature_baseline.py` | `[67]` W-AUDIT-4b feature_baselines readiness: active rows >0 + 34-dim feature vector contract |
| `db/passive_wait_healthcheck/checks_openclaw_gateway.py` | `[54]` OpenClaw proposal relay healthcheck |
| `db/passive_wait_healthcheck/checks_scanner_market.py` | `[41]` scanner would-block evidence and `[51]` opportunity shadow checks |
| `cron/ref21_market_microstructure_recorder.py` | REF-21 local BBO/orderbook/latency recorder |
| `cron/ref21_market_recorder_retention.py` | REF-21 recorder retention maintenance |
| `cron/ref21_symbol_universe_snapshot_cron.sh` | REF-21 V058 symbol universe snapshot cron |
| `operator/edge_p2_flip.sh` | Operator helper for Edge P2 guarded flip |
| `operator/edge_p2_revert.sh` | Operator helper for Edge P2 revert |
| `operator/generate_replay_signing_key.sh` | Replay signing key generation helper |
| `bybit/liquidation_topic_probe.py` | W-AUDIT-8a C1 standalone public WS probe；isolated connection checks `allLiquidation.{symbol}` plus canary market topics and writes latest+dated reports under `$OPENCLAW_DATA_DIR/audit/liquidation_topic_probe/`。Short smoke is not C1 proof；24h PASS + BB/MIT sign-off required before production topic revival。 |
| `research/bb_breakout_threshold_sweep.py` | bb_breakout threshold research sweep |
| `research/ma_crossover_counterfactual_replay.py` | ma_crossover counterfactual replay research helper |
| `research/shadow_disagreement_breakdown.py` | Shadow disagreement breakdown analysis |
| `reports/w2_paper_edge_report.py` | W2 A4-C BTC→Alt Lead-Lag — legacy thin CLI shim；保留舊入口相容，委派至 `reports/w2/w2_paper_edge_report.py`；AMD-2026-05-15-01 後不產 promotion evidence。 |
| `reports/w2/w2_paper_edge_report.py` | W2 A4-C BTC→Alt Lead-Lag — Stage 0R diagnostic report CLI (read-only PG query + metrics→render orchestration)，只輸出 `eligible_for_demo_canary=true/false`。配 `sql/queries/w2_btc_alt_lead_lag_counterfactual.sql`。 |
| `reports/w2/w2_paper_edge_metrics.py` | W2 spec v1.2 §7.1 6 mandatory metric 計算層：PSR(0) Bailey-LdP 2012、DSR K=95、block-bootstrap CI、R²(N)、counterfactual delta、Stage 0R diagnostic verdict。 |
| `reports/w2/w2_paper_edge_render.py` | W2 Stage 0R diagnostic report 展現層：`render_markdown` / `render_csv` / `render_json` / `per_symbol_breakdown_table`。 |
| `reports/w2/w2_paper_edge_smoke.py` | W2 Stage 0R diagnostic smoke：3 mock case (plus15/plus5_15/minus5) 不連 PG，可獨立執行。 |
| `deploy/launchd_preflight.sh` | macOS launchd deployment preflight |

## REF-20 Sprint 1+2 新增 cron 與 helper

| 腳本 | 用途 |
|------|------|
| `cron/replay_key_rotation_check.sh` | REF-20 Wave 2 P2a-S1：90d signing key 輪替檢查（fingerprint align） |
| `cron/replay_key_archive_cleanup.py` | REF-20 Wave 2 P2a-S1：180d archive 清理 |
| `cron/replay_artifact_prune.py` | REF-20 Wave 3 P2a-S5：6h cron 跑 manifest quota 清理 |
| `cron/wave9_replay_no_live_mutation_watch.sh` | REF-20 Wave 9：每小時 cron 檢 trading.* WHERE source LIKE 'replay_%' = 0 |
| `cron/wave9_business_kpi_collector.py` | REF-20 Wave 9：每天 06:00 cron 採集 V047 business_kpi_snapshots（**2026-05-03 真實狀態**：Mac mock mode 跑過，Linux 真實 PG 0 跑 → 待 Sprint 3 deploy） |
| `cron/wave9_audit_incident_scan.py` | REF-20 Wave 9：每天 06:30 cron 掃 V048 audit_incident_summaries（同 Linux 0 跑） |
| `db/passive_wait_healthcheck/checks_governance.py::check_44_replay_manifest_key_presence` | REF-20 Sprint 1 Track B：replay manifest key.hex 存在性監測（V042 archive land 前 fallback 監測） |

---

## 頂層腳本 (Top-Level Scripts)

### 生命週期 (Lifecycle)

| 腳本 | 用途 |
|------|------|
| `restart_all.sh` | **輕量重啟**：停+啟 Rust 引擎 + API server（不動數據）。旗標：`--engine-only` / `--api-only` 限定範圍；`--rebuild` 先重建 openclaw-engine binary 再啟動（PYO3-ELIMINATE-1 Phase 3 後無 PyO3 wheel）。 |
| `stop_all.sh` | **優雅停止**：停引擎 + 建立 `engine_maintenance.flag`，讓 `engine_watchdog.py` 不自動重啟。`--engine-only` / `--api-only`。移除 flag: `rm /tmp/openclaw/engine_maintenance.flag` 或跑 `restart_all.sh`。 |
| `clean_restart.sh` | **交易所層重啟**：停引擎 → httpx BybitClient flatten demo/live 倉位 → 歸檔 runtime 文件（**不動 paper_state，不動 DB**）→ 檢查 binary 新舊 → 重建/重啟 → watchdog 驗證。輕度重置，保留歷史累計。旗標：`--yes` / `--mark-damaged`（歸檔 DB 交易表）/ `--include-live` / `--skip-flatten` / `--skip-build-check` |
| `fresh_start.sh` | **完整 DB 重置重啟**（2026-04-15 新增）：在 clean_restart 基礎上額外清空所有 PnL / 手續費 / 勝率 / 經驗數據（透過 `fresh_start_reset.py`）讓引擎從零歷史冷啟動。**保留**：市場數據（klines/funding/OI/LSR/liquidations/regime/news）、model_registry、linucb_state_archive、features.versions、ai_budget_config。**摧毀**：fills/intents/orders/outcomes/signals/agent 活動/學習狀態。旗標：`--yes` / `--include-live` / `--skip-flatten` / `--skip-build-check` |
| `lib/api_bind_host.sh` | Trading API bind host resolver：默認 auto 綁定 Tailscale IPv4（可用時）或 loopback；拒絕 `0.0.0.0` / `::`，供 restart/clean/fresh lifecycle scripts 共用。 |
| `start_paper_trading.sh` | API server 就緒後自動啟動 Paper Trading（systemd / cron @reboot） |
| `mac_bootstrap.sh` | **macOS 冷裝引導**（Linux→Mac 遷移，2026-04-20 新增）：三段式獨立旗標 `--check`（診斷已裝/未裝，不動手）/ `--install-deps`（brew + rustup + Python venv + pip install）/ `--init-runtime`（建 `$OPENCLAW_DATA_DIR` + 清舊 socket + 寫 .zshrc env 段）。可選 `--no-ollama` / `--no-postgres` / `--all`。Linux 執行會被 platform guard 擋下。搭配 `docs/references/2026-04-20--cross_platform_redeploy_dependencies.md`。 |

### 平倉 (Flatten)

| 腳本 | 用途 |
|------|------|
| `clean_restart_flatten.py` | 交易所平倉助手（被 clean_restart.sh / fresh_start.sh 調用；亦可獨立 `--env demo\|mainnet [--dry-run]`）。PYO3-ELIMINATE-1 Phase 2 後改用 httpx BybitClient — 先 `refresh_instruments` 載入品種規格，再對每倉下 reduce_only 市價單 + 取消所有未成交單；5 輪 verify 循環掃殘尾 |

### 定時任務 / CI (Cron & CI)

| 腳本 | 用途 |
|------|------|
| `cron_daily_report.sh` | 每日自動採集 Paper Trading 指標 + Telegram 推送（Cron UTC 0:00） |
| `cron_observer_cycle.sh` | 每 5 分鐘執行 Observer 循環 + runtime snapshot 橋接 |
| `cron/ml_training_maintenance.py` | W-AUDIT-4 F-08 ML maintenance runner：covers operational MLDE jobs plus original audit targets `thompson_sampling` / `optuna_optimizer` / `cpcv_validator` / `dl3_foundation` / `weekly_report_generator`; source runner only, runtime crontab install requires operator authorization. |
| `cron/ml_training_maintenance_cron.sh` | F-08 cron wrapper around `ml_training_maintenance.py`; loads PG env, writes status JSON/log, uses lock dir, and does not install itself. |
| `cron/feature_baseline_writer_cron.sh` | W-AUDIT-4b cron wrapper around Rust `feature_baseline_writer`; uses `OPENCLAW_FEATURE_BASELINE_APPLY=1` env gate, no CLI apply/force flags, then runs `[67]` healthcheck. |
| `schema_diff.py` | CI 類型一致性：比對 Python shared_types vs Rust golden JSON schema |
| `golden_dataset_gen.py` | Rust↔Python 指標交叉驗證黃金數據集（確定性 OHLCV + 13 指標） |

## db/ — 數據庫維護 (Database Maintenance)

| 腳本 | 用途 |
|------|------|
| `db/fresh_start_reset.py` | 開發噪音清理：保留客觀市場數據，清除系統經驗數據。支援 `--report-only`（默認）/ `--dry-run` / `--execute --confirm "FRESH_START_YYYY_MM_DD"`。通常透過 `fresh_start.sh` 調用（一併停引擎/歸檔/重啟），獨立使用需自行停引擎。 |
| `db/canary_promote_cron.sh` | G4-03 Phase B canary auto-promote cron wrapper。默認 dry-run/read-only；apply 需 `OPENCLAW_CANARY_CRON_APPLY=1` + `OPENCLAW_AUTO_PROMOTE_ENABLED=1`。可選 `OPENCLAW_CANARY_EMIT_SIGHUP=1` + `OPENCLAW_ENGINE_PID_FILE` 在 applied promoting→production 後 SIGHUP engine。 |
| `db/feature_baseline_healthcheck.py` | Standalone `[67]` W-AUDIT-4b feature_baselines readiness check; used by `cron/feature_baseline_writer_cron.sh` after apply. |
| `db/counterfactual_exit_replay.py` | EDGE-DIAG-1 #3 反事實退場回放：READ-ONLY SELECT `learning.exit_features` 最近 N 天，模擬「peak − k × ATR 鎖利」net vs 實際 net。旗標：`--days N`（>0）/ `--cost-model {proxy,fee_only,both}`（default both；proxy 代數退化保留作透明度核驗、fee_only 為經驗有效模型）/ `--fee-bps-per-side 5.5`（Bybit taker default）/ `--include-funding-arb`（預設排除 funding_arb，含 funding payment 失真）/ `--engine-mode`（default demo,live_demo）/ `--cf-multiplier 0.3`（v2 asymptotic floor 線性近似）。產 stdout 雙表 + VERDICT + `$OPENCLAW_DATA_DIR/audit/counterfactual_exit_replay_latest.json` + dated sibling。**v1 Gate-4-only 線性 k=0.3；v2 non-linear + Gate 1/2/3 parity FUP**。 |
| `db/counterfactual_daily_cron.sh` | EDGE-DIAG-1 Phase 4 daily refresh wrapper：crontab 每日 06:00 UTC 呼叫 `counterfactual_exit_replay.py --days 2 --v2-parity --split-window --cost-model fee_only --bootstrap-ci --per-strategy-median --trimmed-mean-pct 5` 刷新 latest JSON，讓 `passive_wait_healthcheck.py [11]` 可讀到當日最新 post-P013-clean 樣本數。WRITE 端（刷 JSON）+ READ 端 check[11] 分離。載入 `$SECRETS_ROOT/environment_files/basic_system_services.env` POSTGRES_*、activate `$HOME/.venv`、log tee `$OPENCLAW_DATA_DIR/audit/counterfactual_daily_cron.log`；PIPESTATUS[0] 透傳 python 退出碼。CLAUDE.md §七「被動等待 TODO 必附 healthcheck」Phase 3 延後的 gate 守衛。 |
| `db/audit/blocked_symbols_7d_counterfactual.py` | P2-AUDIT-VERIFY-5 blocked-symbol freeze audit：READ-ONLY SELECT `trading.fills` + `trading.risk_verdicts` for cells frozen in `docs/governance_dev/strategy_blocked_symbols_freeze.json`，輸出 7d observed fill PnL、blocked rejection count、`decision_outcomes` counterfactual coverage；若 rejected rows 沒有 outcome labels，明確標 `no_rejected_outcome_labels`，不偽造 would-have-traded PnL。 |

## ci/ — CI 稽核腳本 (CI Audit)

> **2026-05-03 新增**（REF-20 Wave 3 R20-P2b-S10）：跨平台（macOS 主 / Linux 次）`replay_runner` binary symbol 稽核。L3 縱深防禦（L1=Cargo feature gate / L2=ReplayProfile::Isolated runtime / L3=本目錄 nm grep）。
> **2026-05-14 新增**（P2-N2-4）：`stable_id` 字面複製 grep guard，防止 W-D MAG-083 P1-1 抽出的 Agent Spine id helper 被未來 callsite 重新用 literal seed format 複製。

| 腳本 | 用途 |
|------|------|
| `ci/check_stable_id_duplication.sh` | P2-N2-4 — 快速 grep guard；掃描 Rust source，若 canonical Agent Spine helper/caller 外出現 `format!("{}:{}:{}:{}"...` 且同檔含 stable-id-like 變數名，即 exit 1 並列出 offending file:line。已接入 GitHub Actions `stable_id duplication guard` job。 |
| `ci/replay_runner_symbol_audit.sh` | REF-20 Wave 3 R20-P2b-S10 — `nm` symbol 稽核 `target/release/replay_runner` binary，驗 0 forbidden symbol class（Decision Lease / IPC / exchange pipeline / Bybit connector / live auth write / order placement / DB writer）。Darwin 用 `nm -gU`（BSD），Linux 用 `nm --extern-only --defined-only`（GNU）。Exit 0 PASS / 1 FAIL / 2 build / 3 nm-not-found / 4 binary-not-found。env：`SKIP_BUILD=1`（跳 cargo）/ `REPLAY_RUNNER_BIN=/path`（覆寫 binary path）。 |
| `ci/test_replay_runner_symbol_audit.sh` | 上述 audit script 的 mock-based bash 測試套（5 cases：clean / forbidden hit / nm absent / binary missing / multi-class hit）。用 nm shim 避免真 cargo build (~30-60s)。 |
| `ci/README.md` | 三層縱深防禦說明 + GitHub Actions / cron / pre-commit hook 整合範例。 |

## canary/ — 灰度驗證 (Canary / Soak Test)

| 腳本 | 用途 |
|------|------|
| `canary/engine_watchdog.py` | 引擎存活監控（`--status` 顯示健康狀態，`--stale-threshold` 設定過期秒數） |
| `canary/replay_runner.py` | 灰度回放：讀取 canary JSONL 並與 Python 基線比對 |
| `canary/canary_comparator.py` | Canary 記錄比對器：逐 tick 驗證 Rust vs Python 指標/信號/PnL |
| `canary/canary_schema.py` | Canary JSONL schema 定義（Pydantic model） |
| `canary/rollback_drill.sh` | 回滾演練腳本 |
| `canary/test_canary.py` | Canary 系統單元測試 |

## phase4/ — Phase 4 學習/晉升工具 (Learning & Promotion)

| 腳本 | 用途 |
|------|------|
| `phase4/dl3_go_no_go.py` | DL-3 Go/No-Go 決策檢查 |
| `phase4/weekly_report.py` | 每週學習/交易績效報告 |

## maintenance_scripts/ — 維護腳本 (Maintenance)

| 腳本 | 用途 |
|------|------|
| `maintenance_scripts/prune_dated_files.sh` | 清理過期的 dated 輸出文件 |

### maintenance_scripts/bybit_connector/ — 舊治理鏈腳本 (Legacy H/I/J/K Chain)

> **2026-04-23 清理**：原本 60 檔（含 README），DEDUP-PY-RUST 系列尾聲刪除 53 個
> 一次性 H/I/J/K-chain 修復腳本（0 caller，DEAD-PY-2 後 Python 治理類已刪、依賴斷鏈，
> git history 可復原）。同步刪除 `program_code/exchange_connectors/bybit_connector/scripts/`
> 下對應的 45 個 REAL= shim wrappers。保留 6 個基礎工具：

| 腳本 | 用途 |
|------|------|
| `lib_trading_env.sh` | 共享環境變量設定（被 `run_with_trading_env.sh` source） |
| `run_with_trading_env.sh` | 在交易環境中運行任意命令（純 bash，無 Python 依賴） |
| `run_i10_canonical_h_chain_recheck.sh` | H 鏈權威檢查器（讀 runtime JSON + 嵌入式驗證） |
| `run_i10_canonical_decision_lease_recheck.sh` | I 鏈權威檢查器（讀 runtime JSON + 嵌入式驗證） |
| `_bybit_latest_wrapper.py` | Bybit API 最新值包裝器（通用工具，標準庫 only） |
| `repair_i10_stage_source_aliases.py` | 修復 I10 stage source 別名（無外部依賴） |

`program_code/.../scripts/` 下剩餘 5 檔：`lib_trading_env.sh` / `run_with_trading_env.sh`
兩個 shim 指向上面白名單，以及 3 個獨立原檔 `bybit_bind_active_route_env.sh`
（shim 指 `misc_tools/`）、`bybit_h1_report_utils.py`、`bybit_readonly_loop_writer.sh`。
