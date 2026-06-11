# helper_scripts/ — 腳本索引 (Script Index)

本目錄存放 OpenClaw 系統的維護、啟動、CI 輔助腳本。
最後更新：2026-06-10（P5-SM soak 第二輪 — `db/lease_ipc_mutating_smoke.py` 新增 S5(b) operator 一次性 mutating IPC smoke（N≥10 acquire+release、`soak_smoke:` intent 前綴、mainnet fail-closed exit 7、默認 dry-run、read-only V054/V078 row-shape 驗證；**禁接 cron/scheduler**）+ `db/passive_wait_healthcheck/checks_governance_lease_ipc.py` 新增 `[82] check_82_lease_ipc_soak_window`（S3/S4 soak 連續有效窗，V129 兩 row + V137 事件帳本跨 epoch 重建；非 active PASS-skip、active 下 flag-OFF/flusher 死/canary 死/記帳破洞逐一 fail-closed FAIL）+ runner `[82]` 註冊。歷史更新：同日 L2 Mesh P2p incident sentinel — 新增 `canary/incident_sentinel.py`（6 軸本地哨兵，alert-only never remediate：A1 engine 心跳 / A1b watchdog 活性 / A2 canary 事件消費 / A3 api healthz / A4 seam reject 暴增 / A5 agent.lessons 異常寫入 / A6 migration drift；告警 sibling-import `engine_watchdog._send_alert_best_effort`，dedup 獨立 state + 4h re-alert 窗，閾值 `OPENCLAW_SENTINEL_*` env-overridable）+ `canary/test_incident_sentinel.py`（隔離鐵則：0 真 DSN / 0 真外發 / 全 tmp_path）+ `cron/incident_sentinel_cron.sh`（5min wrapper：lock + stale-lock 自清 + heartbeat + fail-soft）+ `cron/install_incident_sentinel_cron.sh`（Linux-only idempotent installer，dry-run 預設，`OPENCLAW_SENTINEL_CRON_APPLY=1` 才寫，支援 `--remove`），詳見下節。歷史更新：同日 M4 dead-mode lessons seeder — `m4/seed_dead_mode_lessons.py` 新增 L2 P3b owed ② 冪等 seeder：6 條真實 NO-GO dead-mode 教訓（funding_arb_v2 / funding_short_v2 / cascade_fade_h2 / funding_tilt / grid_short_downtrend / textbook_scalping_family）→ `agent.lessons`（V133），symbol=`ml_advisory`（sink placeholder，檢索鏈一致）/ lesson_type=`dead_mode` / source=`dead_mode_seed` / context_id=`seed:<slug>` 冪等錨點（INSERT … WHERE NOT EXISTS）；默認 `--dry-run` 零連線，顯式 `--apply`（alias `--write`）+ `--dsn` 才落庫（不隱式讀 env DSN，承 0ce45a09 污染事故默認無害原則）；不 seed listing fade（active 主路徑非 dead mode）。歷史更新：2026-06-05 AEG-S2 (c) robustness matrix builder — `research/aeg_robustness_matrix/` 新增 artifact-only verdict matrix builder；歷史更新：2026-06-03 AEG-S2 (b) breadth ladder runner — `research/aeg_breadth_ladder/` 新增 AEG-S2 component (b) breadth ladder runner：read-from-storage-only，把任一候選 per-symbol PnL 在 FND-2 PIT universe 的 4 breadth tier 各跑一次→ deterministic `breadth_ladder.parquet`，報 per-tier net edge + significance + **monotonicity**。candidate-agnostic（`CandidateEvaluator` protocol → `TierResult`）。tier 組裝用 FND-2 `cohort_ids`（multi-membership）組 cumulative-nested（**NOT `recommended_tier`** single-pick）+ 機械驗 core25 ⊆ top_liq ⊆ full。**breadth ≠ n_independent**（time-cluster-bound，cost-wall 8-rebalance 牆機械化；招牌 bite：n_independent(full)==n_independent(core25)）。survivorship 繼承不重算（MIT b.2，0 自寫 listed_at）。top_liquidity asof-constant rank 降級 diagnostic-only（OQ-B3 待 MIT 確認）。8 模塊（tiers/universe_artifact/ladder/evaluator/artifact/harness/healthcheck/__init__）+ 26 test synthetic 全綠 + 端到端真 multiday adapter 驗證（Mac，bite 通過 + ladder_id 跨進程穩定 + parquet 生成）；真 829-sym universe + 真 market.klines 留 E4-Linux。待 E2 對抗審 + MIT leak/n_independent 審；E1 不自簽。歷史更新：2026-06-03 FND-2 PIT universe builder — `research/fnd2_pit_universe/` 新增 AEG-S1 point-in-time universe builder：read-only `market.symbol_universe_snapshots`（V058）→ deterministic PIT universe artifact（universe.parquet/.csv + universe_summary.json + manifest.json + artifact_index.json），**含已 delisted symbol**（survivorship 控制核心）。算法權威=PA 設計報告 §4 修正版（**非** contract §3 字面）：`listed_at`/`delisted_at` 是唯一 lifetime 權威，`first_seen_ts`/`last_seen_ts` 僅診斷（snapshot ts 只跨 27 天，coalesce 到 ts 會把舊上市幣 alive_from 錯夾到 2026-05=R-1 trap）；兩權威欄全 NULL 才標 unknown_lifetime。builder.py 純函數 0-DB（synthetic 可測）+ data_loader.py 唯讀 `set_session(readonly=True)` + cohorts.py（core25 從 seed 凍結 25 成員）+ artifact.py（跨平台 root + duckdb parquet 鏡像 + sha256 + universe_id digest）+ harness.py（CLI 顯式窗無隱式 now() + seed regression）。禁 current-survivor 捷徑 / `_fetch_historical_universe_snapshot_sync` / `max_symbols` / universe SQL LIMIT 截斷 / market_tickers liquidity 當 PIT alpha（只能 tier 排序）。測試 10 case（T1-T10）全 synthetic 19 passed；真跑 18mo USDT-perp（read-only PG，asof 2026-06-03 / window 2024-06-03→2026-06-03）included=829 / delisted_proof_count=255（≥200）/ survivor_rejection_status=PASS / unknown_lifetime=0 / determinism universe_id 兩跑一致 / seed sha256 match drift+32 全解釋。E1 IMPL DONE 待 E2 對抗審 + MIT universe-row 審（E1 不自簽）。歷史更新：2026-06-03 funding-tilt / 多日 funding carry 樞紐診斷 harness — `research/funding_tilt_diagnostic/` 新增 QC 協議證偽優先診斷：read-only canonical run-versioned `research.alpha_funding_rates_history`（固定 run `18b3c2f8…` 只讀它）+ `market.klines` 1d（open-to-open）+ listed_at survivorship；2 信號族（A cross-sectional funding-tilt tertile long-short L∈{3,9,21} / B time-series funding-extreme 80th pct expanding PIT）leak-free（funding_ts<open−ε）/naive 雙軌 + §3.0 funding 雙面會計（funding_pnl 獨立項 −side×F 不雙重計入）+ **per-leg long/short 分解**（MIT 強制：短腿擠壓不可藏）+ Step0 + 兩個 N_eff（price-return + funding-tiltscore PCA）+ funding persistence + funding-tilt forward HAC + §4.5 horizon-vs-cost-share 掃描 + §4b regime split + DSR(K=8)/PSR/PBO/block-bootstrap（復用 lib.stats_common）；per-symbol 從 funding_ts 間距推 interval（欄 100% NULL，TON/POL=4h）；regime vol-tercile leak 修為 expanding/prior-365。輸出 JSON+markdown，不寫庫不 commit。K 鎖 8。E1 IMPL DONE 待 E2 對抗審 + MIT leak/sample 審 + QC 最終判定（E1 不自簽）。歷史更新：2026-06-02 多日 trend 樞紐診斷 harness — `research/multiday_trend_diagnostic/` 新增 QC 協議 Phase 1 fail-fast 早期決策樹診斷：read-only PG（market.klines/funding_rates/symbol_universe_snapshots/regime_snapshots）+ 4 信號族 leak-free/naive 雙軌 + 多日成本（含 funding 累積）+ Step0 effective N + 正確尺度 TSMOM coherence gate（過去 k 日→未來 k 日 + Newey-West overlap-corrected t-stat，verdict 依據；daily-lag Ljung-Box 降級為 data_quality 廣度統計）+ ADF/KPSS/JB/ARCH 純 numpy 統計；輸出 JSON+markdown artifact，不寫庫不 commit。E1 IMPL DONE 待 E2 審查；真跑 verdict=NO-GO-TREND（正確尺度無相干 momentum：k40 孤立顯著無相鄰對 + k90 反轉 + 0/20 正自相關，表面 Sharpe 為 short-side 厚尾/funding artifact）。歷史更新：2026-05-31 M4 Stage 1 GovernanceHub lease provider seam — `m4/stage1_production_runner.py` 新增 opt-in GovernanceHub IPC lease provider；只接受 UUID-compatible lease，非 UUID lease 立即 release FAILED 並拒絕 INSERT。歷史更新：同日 A2 maker-fill feasibility diagnostic — 新增 `reports/alpha_candidate_stage0r/a2_maker_fill_feasibility.py` + smoke，以 read-only `market.liquidations` + `market.market_tickers` BBO 檢查 cascade trigger 後 60s PostOnly offset touch rate；只輸出 `reject` / `draft_only` / `observe_more`，不下單不寫庫。同日 M4 Stage 1 production DRAFT runner — 新增 `m4/stage1_production_runner.py` non-dry-run source read / candidate compute / gated writeback；writeback 必須每 row 提供真實 Decision Lease UUID，analysis lane `exploratory` 映射成 PG status `draft`。2026-05-29 P2-OPS-2-GITLEAKS — 新增 `git_hooks/` secret-scan pre-commit hook 基礎設施：canonical hook + installer + gitleaks config；E1 IMPL DONE 待 E2 sign-off。2026-05-27 P0-OPS-4 GAP-D Track A round 2 — 新增 `canary/healthchecks/check_pg_dump_freshness.py` Python 主入口 7-check（5 verify_pg_dump.sh + L0 schema coverage + governance audit trail） + wire `passive_wait_healthcheck/checks_cron_heartbeat.py` 加 `check_80_pg_dump_freshness()` wrapper；E1 IMPL DONE 待 E2 sign-off。同日保留 P0-OPS-1 HTTPS Track A IMPL + P0-OPS-4 first-day-live runbook GAP A + GAP F IMPL 索引 + 2026-05-25 Sprint 2 W2-F NEW QA-2 AC-19 ALT bucket cron + W2-B Alpha Tournament scaffold + Hygiene Option E Phase 1 Step 2 + 2026-05-23 Sprint 5+ Wave 1 §4.4 production hardening + 2026-05-20 P0-ENGINE-HALTSESSION-STUCK-FIX 索引）

## 2026-06-10 L2 Mesh P2p incident sentinel（本地哨兵，alert-only never remediate）

設計 SSOT：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--l2-p2p-incident-sentinel-design.md`。
watchdog 之外的獨立第二觀察者：覆蓋 watchdog 自身死亡盲區（2026-06-05 引擎 20h 事故）與
watchdog 不看的面（DB 異常寫入率 = 06-10 fixture 污染事故制度化、API liveness、migration drift）。

| 腳本 | 用途 |
|------|------|
| `canary/incident_sentinel.py` | 6 軸唯讀監測：A1 `pipeline_snapshot*.json` mtime>900s CRITICAL / A1b watchdog pgrep 唯讀 WARN（A1 未觸發才獨立發）/ A2 `canary_events.jsonl` ts-游標 tail（alertable={RESTART_FAILED,NETWORK_OUTAGE,TRADING_INERT_PROLONGED,RESTART_SKIPPED}，排除 watchdog 已自行 alert 與正向事件，多事件聚合一條，rotate-safe，首跑=now−1h）/ A3 healthz GET 5s timeout CRITICAL / A4 `l2_gate_seam_log` reject>10/h WARN / A5 `agent.lessons` 雙層（rate>6/h + source 白名單外≥1/24h）WARN / A6 `_sqlx_migrations` max vs repo V*.sql max + bool_and(success) WARN。DB 軸 psycopg2 延遲 import + read-only session + statement_timeout 10s；不可達=三軸聚合一條 db_unreachable WARN，file/HTTP 軸照常；per-axis 隔離。dedup=獨立 `incident_sentinel_state.json`（絕不碰 watchdog_state.json）+ 4h re-alert 窗；CRITICAL 恢復發 INFO RECOVERED、WARN 靜默清。告警 sibling-import `engine_watchdog._send_alert_best_effort`（fire-and-forget；短命進程 main 結束前 drain 6s）。自身審計 `incident_sentinel_events.jsonl` 每輪 verdict 摘要。CLI：`--data-dir/--base-dir/--once/--dry-run/--probe-alert`；閾值全 `OPENCLAW_SENTINEL_*` env-overridable；exit 0/1/2 對齊 `canary/healthchecks/_common.py`。**never remediate**：0 進程操作（pgrep 唯讀例外）/ 0 權威面寫入 / 唯二本地寫=自身 state+audit。 |
| `canary/test_incident_sentinel.py` | 設計 §8.4 全 9 條驗收：六軸 fault-injection / dedup 全語義 / per-axis 隔離 / db_unreachable / 游標 rotate+首跑 / never-remediate 結構斷言 / emitter 簽名 smoke（monkeypatch urlopen 下 4-arg 真調用）/ drain / 審計。隔離鐵則（§8.2，canary/ 無 conftest guard 庇護）：0 真 DSN / 0 psycopg2.connect / 0 真 urlopen / 全 tmp_path。 |
| `cron/incident_sentinel_cron.sh` | 5min cron wrapper（mirror halt_audit 模式）：mkdir lock 防 overrun + stale lock mtime>15min 自清 + grep-parse `basic_system_services.env`（缺檔不致命：file/HTTP 軸零 DB 依賴必須在 PG down 時也能告警）+ touch `cron_heartbeat/incident_sentinel.last_fire` + fail-soft exit 0。 |
| `cron/install_incident_sentinel_cron.sh` | idempotent installer（mirror install_pg_dump 模式）：Linux only / dry-run 預設 / `OPENCLAW_SENTINEL_CRON_APPLY=1` 才寫 crontab / 偵測既有條目 refuse / `--remove`（同受 APPLY gate）。Entry：`*/5 * * * *`。rollback = `--remove`，零殘留。 |

## 2026-06-10 P5-SM soak 第二輪（step-(i) soak gate S3/S4/S5）

per PA 設計 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--p5sm_soak_observability_redesign.md` + PM cadence 定案 `2026-06-10--p5sm_soak_cadence_decision.md`（120s ±10% jitter + 五條 fire-機率防護）。新 gate = S1（4a CI）+ S2（`[81]` P-LIVE）+ S3/S4（`[82]` soak-window）+ S5（operator 收口 checklist）。

| 腳本 / 模塊 | 功能 |
|---|---|
| `db/lease_ipc_mutating_smoke.py` | **S5(b) operator 一次性 mutating smoke（禁接 cron/scheduler，注釋 + 本表雙重明文）**。N≥10 輪 acquire(Production/TRADE_ENTRY/ttl 30s)+release(Consumed)，intent 帶 `soak_smoke:` 前綴（audit row 可逐筆歸因）；mainnet fail-closed（`OPENCLAW_ALLOW_MAINNET=1` → exit 7）；默認 dry-run，顯式 `--run`（+`--yes`）才真打；輪間 0.5s throttle。後半 read-only PG（`set_session(readonly=True)`）驗 V054 `lease_transitions` row shape：NOT NULL 欄 + to_state ∈ V078 10 值 + profile ∈ 3 值 + 每 lease ACTIVE/CONSUMED 雙痕跡（兩個 mutating arm 都留 audit）。profile=Production 是 deliberate：Validation/Exploration 繞過 SM（Bypass 無法 release）= 驗不到 mutating arm；demo 語義由環境層（mainnet guard + 引擎 LiveDemo）保證。exit 0 PASS / 1 FAIL / 2 env / 7 guard 拒。 |
| `db/passive_wait_healthcheck/checks_governance_lease_ipc.py` | 新增 `[82] check_82_lease_ipc_soak_window` — S3/S4 soak 連續有效窗評估（同檔 `[81]` 之後）。讀 V129 `'singleton'`+`'canary'` 兩 row + V137 `learning.lease_ipc_soak_events` 事件帳本，跨 epoch 重建連續窗（epoch_rollover prev_* 求和累計 probe）。S3：窗 ≥48h / 累計 probe ≥500 / 結構成功率 ≥99% / 窗內 0 `canary_fail_streak`。S4：0 flag-OFF 觀測（錨點重置語義）/ epoch 間隙 ≤30min（不可知間隙 fail-closed 重置）/ 0 counter regression（事件 + 無狀態交叉偵測雙軌）。非 active → PASS-skip；active 下基建死（V137 缺 / canary row 缺 / snapshot stale=flusher 死 / probe 不增長=canary 死 / 帳本空）逐一 fail-closed FAIL。 |
| `db/passive_wait_healthcheck/runner.py` | 新增 `[82] lease_ipc_soak_window` 註冊（import + cursor 區塊內 append；docstring ID 清單補 [81][82]）。 |

> 配對（control_api app，非 helper_scripts）：`governance_ipc_canary.py`（唯讀 IPC canary，kill-switch `OPENCLAW_SM_IPC_CANARY_ENABLED` 嚴格 "1" 默認 OFF，cadence env `OPENCLAW_SM_CANARY_INTERVAL_SECS` 默認 120s；singleton §2.5.5）+ `governance_divergence_flush.py` 擴充（V129 `'canary'` row 投影 + V137 事件鏈：epoch_rollover/flusher_start/flag_change/canary_leader_start/canary_fail_streak/counter_regression；trackers singleton §2.5.6）+ `restart_all.sh` 轉發兩個 canary env（operator-env 優先 → `basic_system_services.env` fallback）+ V137 `sql/migrations/V137__lease_ipc_soak_events.sql`（append-only 事件帳本，Guard A/C + 條件式 CHECK，Linux PG dry-run 雙跑冪等已證）。step-(iv) cleanup 整組退役。
## 2026-06-10 M4 dead-mode lessons seeder

| 腳本 | 用途 |
|------|------|
| `m4/seed_dead_mode_lessons.py` | L2 P3b owed ②：把 6 條真實 NO-GO dead-mode 教訓冪等 seed 進 `agent.lessons`（V133），供 hypothesize novelty 檢索（`_check_novelty` lesson_type=`dead_mode`）與 M4 bad-set。欄位 ground 在 `layer2_critic._retrieve_lessons_sync` filter 行為：symbol=`ml_advisory`（= executor sink placeholder；不一致=永 miss 死資料）、source=`dead_mode_seed`（第 4 namespace，純 provenance，filter 不含 source）、content 英文主幹（pg_trgm 字面 trigram，中文 vs 英文 hint 相似度≈0）、context_id=`seed:<slug>` 冪等錨點（`INSERT … WHERE NOT EXISTS`，重跑 inserted=0）、outcome_net_bps/session_cost_usd 恆 NULL（V133 forward-stub）。**默認 `--dry-run`（print 不寫，0 DB 連線）**；顯式 `--apply`（alias `--write`）+ **顯式 `--dsn`** 才落庫（不隱式讀任何 env DSN）。測試 `m4/tests/test_seed_dead_mode_lessons.py`（fake conn + sys.modules psycopg2 stub，零真連線）。 |

## 2026-06-05 AEG candidate metrics adapter（`research/aeg_candidate_metrics/`）

AEG robustness matrix 的下一個缺口是候選級 per-regime PnL、recent 90/180d
freshness 與 matrix-critical 統計欄位。`aeg_candidate_metrics` 是 fail-closed
adapter：從 trend/funding 等 diagnostic report 的 selected variant 抽 `per_regime_net`，輸出
`candidate_regime_metrics.csv` + `candidate_metrics_summary.json`。它**不把
mean_daily_bps 冒充為 matrix net_bps**；缺 `net_bps` 或 `recent_90d_net_bps` /
`recent_180d_net_bps`，或缺 `net_to_cost_ratio`、`n_independent`、PSR/DSR/PBO、
OOS Sharpe 等 matrix-critical 欄位時 row 直接 `metric_status=FAIL`，把「還缺什麼」
變成機械證據。它也**不把 n_days 冒充為 n_independent**；DSR 讀分數，不讀
K budget。v0.2 也支援 AEG-S3 harness 直接輸出 top-level `candidate_regime_metrics`
block（不必塞進舊 `signal_evaluation` 形狀）。artifact-only，0 DB / 0 runtime /
0 trading path。

| 檔 | 職責 |
|---|---|
| `research/aeg_candidate_metrics/__init__.py` | candidate regime metrics schema / runner 版本（v0.2 含 matrix-critical 欄位）。 |
| `research/aeg_candidate_metrics/builder.py` | 純函數 adapter：偵測 report type、選 selected/best variant 或 direct candidate metrics block、抽 per-regime metrics、標 freshness/net_bps/n_independent/PSR/DSR/PBO/OOS 缺口。 |
| `research/aeg_candidate_metrics/artifact.py` | `candidate_regime_metrics.csv` SoT + summary/manifest/index。 |
| `research/aeg_candidate_metrics/harness.py` | CLI：`--diagnostic-report-json` → artifact-only run dir。 |
| `research/tests/test_aeg_candidate_metrics.py` | synthetic bite tests：現有診斷缺 net/freshness 必 fail、net+freshness 但缺 matrix-critical 欄位仍 fail、完整欄位才 pass、direct candidate metrics block、DSR score 不被 K budget 污染、best-variant fallback、manifest/index、靜態禁 DB/runtime route。 |

## 2026-06-05 AEG execution realism builder（`research/aeg_execution_realism/`）

AEG verdict 必需的 `execution_realism.json` 產生器。輸入候選的 fee / slippage /
maker-fill / adverse-selection / latency / participation / capacity / order availability
證據 JSON，輸出 canonical artifact；輸入 `status` 不被信任，PASS/FAIL 由固定 gate
重算。PASS 只接受 empirical source tier（`calibrated_replay` / `demo_fills` /
`live_demo_fills` / `live_fills`）、樣本數 `>=30`、maker fill `>=0.60`（maker/mixed）、
latency p95 `<=2000ms`、participation p95 `<=5%`、adverse-selection p95 `<=3.5bps`
與正容量。缺任何必要欄位 fail-closed，讓 robustness matrix 能區分
`missing_execution_realism` 與「已提供但不合格」。

| 檔 | 職責 |
|---|---|
| `research/aeg_execution_realism/__init__.py` | schema/runner 版本與固定 gate 常數。 |
| `research/aeg_execution_realism/builder.py` | 純函數核心：重新計算 status、reject_reasons、execution_realism_mode 與 round-trip p95 成本。 |
| `research/aeg_execution_realism/artifact.py` | `execution_realism.json` + manifest + artifact_index；0 DB/0 runtime。 |
| `research/aeg_execution_realism/harness.py` | CLI：`--input-json` → artifact-only run dir。 |
| `research/tests/test_aeg_execution_realism.py` | synthetic bite tests：empirical PASS、assumption-only 假 PASS 被打回、缺欄 fail-closed、matrix loader 可讀、靜態禁 DB/runtime route。 |

## 2026-06-05 AEG-S2 (c) robustness matrix builder（`research/aeg_robustness_matrix/`）

AEG-S2 component (c) robustness matrix builder：artifact-only batch module，
消費 (a) regime labels artifact + (b) breadth ladder artifact + optional
`aeg_candidate_metrics` per-regime metrics artifact，產 S0 §2.9
`verdict_matrix.csv/.parquet`。嚴格 fail-closed：若缺 per-regime candidate
PnL、freshness rolling net、cluster-adjusted `n_independent` 或 execution_realism.json，
就把該 cell 標為 `insufficient evidence` 並寫入 `reject_reasons`；不把
aggregate breadth edge 或 `mean_daily_bps` 冒充成 regime-sliced `net_bps`。
selection-bias 統計不只查存在，還檢查 PSR/DSR/PBO 閾值（PSR/DSR >= 0.95，
PBO < 0.5），避免低統計品質的完整欄位 row 被誤標 durable。
0 DB write / 0 migration / 0 IPC / 0 order。

| 檔 | 職責 |
|---|---|
| `research/aeg_robustness_matrix/__init__.py` | verdict gate / schema 版本、S0 最小欄位、final label set。 |
| `research/aeg_robustness_matrix/builder.py` | 純函數核心：載入上游 artifact payload → 生成 regime × breadth × candidate metrics × freshness × survivorship × execution-realism matrix rows；缺證據或 PSR/DSR/PBO 閾值不過時 fail-closed。 |
| `research/aeg_robustness_matrix/artifact.py` | `verdict_matrix.csv` SoT、optional parquet mirror、summary、manifest、artifact_index。 |
| `research/aeg_robustness_matrix/harness.py` | CLI 編排：`--regime-run-dir` + `--breadth-run-dir` + optional `--candidate-metrics-run-dir` + optional `--execution-realism-json` → artifact。 |
| `research/tests/test_aeg_robustness_matrix.py` | Synthetic bite tests：缺 per-regime metrics 不可 promote、candidate metrics 接入不可單位偷換、完整 non-bull row 可形成 durable candidate、PSR/DSR/PBO 閾值不過必 reject、survivorship 未驗證必進 reject reason、manifest/index 完整、靜態禁 runtime/DB write route。 |

## 2026-06-05 AEG-S2 (a) regime label runner（`research/aeg_regime_runner/`）

AEG-S2 component (a) regime label runner：read-from-storage-only batch research
module，從 `market.klines` daily closed bars 產 V127-compatible regime label rows、
feature lineage artifact、transition artifact；默認 artifact-only，只有 CLI 顯式
`--write-db` 才寫 `research.aeg_regime_labels` / `research.aeg_regime_transitions`。
不重用 V002 `market.regime_snapshots`，不碰 order/auth/lease/IPC/runtime 交易面。

| 檔 | 職責 |
|---|---|
| `research/aeg_regime_runner/__init__.py` | AEG classifier/schema 版本常數、V127 vocabulary、feature rules digest。 |
| `research/aeg_regime_runner/classifier.py` | 純函數核心：用 prior complete daily close 計算 10 個 S0 feature、5-main regime、BTC market anchor、transition rows。 |
| `research/aeg_regime_runner/lineage.py` | 產生/驗證 `feature_lineage`，要求 `lag_ms >= feature_bar_ms`；promotion-grade lineage 不可偷看 current/future bar。 |
| `research/aeg_regime_runner/data_loader.py` | 唯讀 PG loader，強制 `set_session(readonly=True)`，讀 `market.klines` daily close；`close_ts_ms` 優先作 signal timestamp。 |
| `research/aeg_regime_runner/artifact.py` | `regime_labels.csv` / `feature_lineage.csv` / `regime_transitions.csv` + optional parquet mirror + summary/manifest/index。 |
| `research/aeg_regime_runner/db_writer.py` | 顯式 `--write-db` 路徑才使用的 V127 writer；默認 runner 不寫 DB。 |
| `research/aeg_regime_runner/harness.py` | CLI 編排：FND-2 artifact 或 `--symbols` → loader → classifier → lineage gate → artifact → optional DB write。 |
| `research/tests/test_aeg_regime_runner.py` | Synthetic bite tests：未來尾部波動不改 prefix label、current bar 不影響 same-signal label、lineage lag gate、V002 vocabulary reject、FND-2 alive mask filter、artifact 完整性。 |

測試：`python3 -m pytest helper_scripts/research/tests/test_aeg_regime_runner.py -q`；
整組 research regression：`python3 -m pytest helper_scripts/research/tests -q`。

## 2026-06-03 P5-SM-OPTION2 B-3 soak 可觀測性（SM Option 2 step-(i) cutover gate）

per PA 設計 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-03--p5_sm_soak_observability_redesign.md` + reconciliation `2026-06-03--p5_sm_soak_equiv_sampler_reconciliation.md`。**rework (b)+(b-i)（operator 拍板 2026-06-03）**：comparator 從硬 gate 降為**觀測性信號**（Option 2 下歷史 replay vs contemporaneous comparator 語意不可達，E2 HIGH-2）。**cutover gate = 4a CI 綠 AND P-LIVE soak 健康**（不含 comparator counter）。EQUIV sampler 已 DEPRECATED（不接 gate）。**不觸 Rust / 不動 comparator**（讀現有 V054 `learning.lease_transitions`）。

| 腳本 / 模塊 | 功能 |
|---|---|
| `db/lease_ipc_equiv_sampler.py` | **DEPRECATED（operator (b)+(b-i) 2026-06-03，不接 production）**。原為 P-EQUIV 真實樣本驅動器（O-2 keep-as-gate 前提），但 Option 2 下**語意不可達**：拿歷史 Rust-GRANTED row 對撞 Python hub 當前 auth state（steady-state 未授權）→ 每筆歷史 GRANTED→影子 DENIED→comparator gate 永卡死（E2 HIGH-2 + PA reconciliation `2026-06-03--p5_sm_soak_equiv_sampler_reconciliation.md`）。已從 soak gate 路徑移除；HIGH-1/MEDIUM-1 已知缺陷刻意不修（不接 gate 修無意義）。**保留檔案僅防他人重寫同一卡死設計**；module docstring 頂部標 DEPRECATED 說明。 |
| `db/passive_wait_healthcheck/checks_governance_lease_ipc.py` | `[81] check_81_lease_ipc_soak` — SM Option 2 step-(i) soak gate（`(cur)->(status,msg)` 與既有 checks_*.py 同契約）。**rework (b)+(b-i)**：gate 唯一條件 = **P-LIVE**（讀 V054 `learning.lease_transitions` count+freshness，預設 `<3600s`，operator 可調 O-3）。**fail-closed（G-1，僅對 P-LIVE）**：lease_transitions 表缺/V054 未 apply、0 row、stale → FAIL（**非 WARN**）。**這徹底解原 fake-pass**：gate 改讀真實熱路徑 `lease_transitions`（Rust 真寫），非空轉的 comparator counter。comparator（V129 `learning.lease_ipc_divergence_snapshot` 的 total/matches/divergences/snapshot_age/flag）降為 **observability 觀測欄**（msg 報數值供 triage，**非 gate**；讀不到/缺表/stale→觀測欄缺值不致 FAIL）。新 sibling 檔（checks_governance.py 已 1247 行近上限）。 |
| `db/passive_wait_healthcheck/runner.py` | 新增 `[81] lease_ipc_soak` 註冊（import + cursor 區塊內 append，純 SQL check）。 |

> 配對（control_api app，非 helper_scripts，故不列表但相關）：`governance_divergence_flush.py`（API process 內 best-effort 週期 flusher，leader-elected 單一 writer，讀 comparator `_COUNTERS` snapshot → UPSERT V129 表；**fail-soft 絕不影響權威 lease 路徑/comparator（G-2）**，PG I/O 不在 comparator lock 內）+ `main.py` `@app.on_event("startup")` asyncio.create_task 排程 + V129 `sql/migrations/V129__lease_ipc_divergence_snapshot.sql`（Guard A + 冪等，非 hypertable=current-value snapshot）。singleton `_FLUSHER_LEADER_LOCK_FD` 登記於 `docs/architecture/singleton-registry.md` §2.5.4。**rework (b)+(b-i) 後保留作觀測**（comparator 仍是觀測信號需被 flush 到 PG 供 SQL 觀測；healthcheck 不再 gate 它），邏輯 byte-unchanged。

## 2026-06-03 FND-2 PIT universe builder（`research/fnd2_pit_universe/`）

AEG-S1-FND-2 PIT universe builder（contract `docs/execution_plan/2026-06-01--aeg_s1_fnd2_pit_universe_builder_contract.md`
+ 算法權威 PA 設計報告 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-03--fnd2_pit_universe_builder_impl_design.md`
§4）。read-only batch research module，從 `market.symbol_universe_snapshots`（V058）產
deterministic PIT universe artifact（**含已 delisted symbol**，survivorship 控制核心），供
AEG-S2 component (b) breadth ladder / (c) robustness matrix 消費。artifact 寫
`${OPENCLAW_DATA_DIR:-/tmp/openclaw}/alpha_history_runs/<run_id>/`，不寫 PG / 不 commit。

**最 load-bearing 設計（R-1）**：snapshot `ts` 只跨 27 天（2026-05-07→2026-06-03）但
`listed_at` 跨 2018→2026、`delisted_at` 跨 2022→2026 → `listed_at`/`delisted_at` 是唯一
lifetime 權威，`first_seen_ts`/`last_seen_ts` **僅診斷**（contract §3 的 coalesce 到 ts 是
trap，會把舊上市幣 alive_from 錯夾到 2026-05）。兩權威欄全 NULL 才標 unknown_lifetime。

| 檔案 | 用途 |
|---|---|
| `research/fnd2_pit_universe/__init__.py` | package marker + 版本常數（BUILDER_VERSION / QUERY_SCHEMA_VERSION / MANIFEST/UNIVERSE schema），版本進 universe_id digest。 |
| `research/fnd2_pit_universe/cohorts.py` | 凍結 core25（從 seed CSV `in_core25_pinned=t` 25 行提取）+ recommended_tier 優先序（core25 > scanner-active > top_liquidity rank≤50 > full_survivorship）+ status_class 映射 + cohort_ids。turnover 缺失絕不排除（liquidity 只排序非 inclusion）。 |
| `research/fnd2_pit_universe/builder.py` | **純函數核心 0-DB**（Step D-H）：lifetime（listed_at/delisted_at 權威）→ inclusion（lifetime ∩ window 對稱判定含 delisted）→ effective lifetime clip → cohort/tier → universe rows + summary。`compute_universe_id`（sha256 of window+source+max snapshot ts+version+ordered row digest，row 固定排序+float %.12g）。`survivor_rejection_status`（PASS/FAIL/PROVEN_NONE_IN_WINDOW 機械化：窗內有 delisted 但 included 全 current-survivor=FAIL）。 |
| `research/fnd2_pit_universe/data_loader.py` | 唯讀 SELECT（強制 `set_session(readonly=True)` + statement_timeout）：lifecycle 聚合（status 不過濾，含 Closed/PreLaunch）+ latest 投影（`encode(payload_hash,'hex')`）+ turnover tier 排序源（to_regclass guard，**無 LIMIT 截斷**）+ scanner active_symbols overlap（LIMIT 1 取最新 snapshot，非 universe 截斷）。DSN 用 `lib.pg_connect.resolve_report_dsn()` 跨平台。禁用 `_fetch_historical_universe_snapshot_sync` / `max_symbols` / current-scanner fallback。 |
| `research/fnd2_pit_universe/artifact.py` | 跨平台 artifact root（`${OPENCLAW_DATA_DIR:-/tmp/openclaw}/alpha_history_runs/`）+ universe.csv（標準庫 SoT）+ universe.parquet（duckdb 鏡像 all_varchar，缺套件 skip 非阻斷）+ universe_summary.json + manifest.json（AEG-S0 §1.4 + universe_sources PIT gate + git provenance）+ artifact_index.json（每檔 path/sha256/byte_size/row_count/schema_version）。0 import runtime 模組。 |
| `research/fnd2_pit_universe/harness.py` | CLI 編排（`python3 -m fnd2_pit_universe.harness --run-id --asof --window-start --window-end --cutoff`，**顯式窗無隱式 now()**）：load → build → seed regression（比對 797-row seed CSV count/tier，drift 須解釋非 fail）→ write artifacts → 印 summary。exit 0=成功；survivor_rejection_status=FAIL 才是真失敗信號。 |
| `research/tests/test_fnd2_pit_universe.py` | 10 case T1-T10（synthetic，Mac 可跑，19 passed）。**bite-proof**=(T1)窗內 delisted 必 included 且 alive_to 精確=delisted_at；(T2/T2b)R-1 alive_from 用 listed_at 非 first_seen_ts；(T3)current-survivor-only=FAIL；(T4)determinism universe_id 兩跑一致 + 改 lifetime 改 id；(T5)seed regression sha256 鎖定+drift 解釋；(T6)forbidden-route 靜態（tokenize 去註釋後 0 禁用函數呼叫 + universe SQL 無 LIMIT）；(T7)lifetime-edge + unknown_lifetime 診斷排除；(T8)turnover 排序不截斷（NULL 不排除）；(T9)payload_hash hex；(T10)manifest/index 完整。`python3 -m pytest helper_scripts/research/tests/test_fnd2_pit_universe.py -q`。 |

真跑（Linux read-only PG，2026-06-03）：included=829 / delisted_proof_count=255（≥200 DoD）/
survivor_rejection_status=PASS / unknown_lifetime=0 / universe_id 兩跑一致（determinism）/
seed sha256 match + drift+32（全新上市 0 dropped，無 survivor truncation）。**待 E2 對抗審 +
MIT universe-row 審；E1 不自簽。**

## 2026-06-03 AEG-S2 (b) breadth ladder runner（`research/aeg_breadth_ladder/`）

AEG-S2 component (b) breadth ladder runner（算法權威 PA 設計報告
`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-03--aeg_s2_breadth_ladder_runner_impl_design.md`
+ MIT b.1–b.6 + S0 §1.3/§1.4/§2.8/§2.9）。read-from-storage-only batch research module：把
**任一候選的 per-symbol PnL 生成**在 FND-2 PIT universe 的 4 breadth tier 上各跑一次，產
deterministic `breadth_ladder.parquet`，報 per-tier net edge + significance + **monotonicity**
（edge 隨 breadth 加寬存活 vs 塌成 1-2 symbol fluke）。是 (c) robustness matrix `breadth_cohort`
軸的證據源。**candidate-agnostic**（`CandidateEvaluator` protocol → `TierResult`，候選由 caller
注入）。

| 檔 | 職責 |
|---|---|
| `aeg_breadth_ladder/__init__.py` | package marker + 版本常數（`BREADTH_LADDER_VERSION='aeg_breadth_v0.1.0'` / `LADDER_SCHEMA_VERSION` / `N_INDEPENDENT_PROMOTION_FLOOR=30`）。 |
| `aeg_breadth_ladder/tiers.py` | 凍結 `BREADTH_TIERS` + `assemble_tiers`（從 FND-2 **`cohort_ids` multi-membership** 組 cumulative-nested set，**NOT `recommended_tier`** single-pick）+ `assert_nested_invariant`（機械驗 core25 ⊆ top_liq ⊆ full）。純函數 0-DB。 |
| `aeg_breadth_ladder/universe_artifact.py` | 讀 FND-2 universe.csv（SoT）+ `build_alive_mask`（survivorship **繼承不重算**，MIT b.2，0 自寫 listed_at 查詢）+ `tier_quality_and_exclusion`（top_liquidity asof-constant rank 降級為 `liquidity_source_not_pit`/`excluded_from_promotion`，OQ-B3 待 MIT 確認）。0-DB 讀檔。 |
| `aeg_breadth_ladder/ladder.py` | 純函數核心：{tier→TierResult}→per-tier rows + monotonicity 判定（survives/collapses_to_narrow/insufficient_n_independent）+ **breadth≠n_independent 分離**（`n_independent_invariant_to_breadth` 自證 n_independent 不隨 symbol 膨脹）+ `ladder_id` digest（`%.12g` 固定格式 + 固定排序）。0-DB / 0 候選耦合。 |
| `aeg_breadth_ladder/evaluator.py` | `TierResult` schema + `CandidateEvaluator` protocol + `MultidayTrendReferenceEvaluator`（reference adapter，OQ-B2：n_independent 用 **time-cluster-bound** time-period count，**不沿用** multiday `eff_n=pooled_flips×cluster_factor` symbol-contaminated）+ `StubEvaluator`（測試）。 |
| `aeg_breadth_ladder/artifact.py` | breadth_ladder.csv（SoT）/.parquet（duckdb 鏡像）+ summary.json + manifest.json（fnd2_universe_id/fnd2_run_id provenance 鏈）+ artifact_index.json + sha256（mirror FND-2，跨平台 `OPENCLAW_DATA_DIR` root）。 |
| `aeg_breadth_ladder/harness.py` | CLI 編排（顯式窗無隱式 now()）：load FND-2 artifact → assemble tiers → alive_mask → per-tier candidate evaluate → ladder → write → 印 summary。 |
| `aeg_breadth_ladder/healthcheck.py` | `check_aeg_breadth_universe_pit()`（artifact-level，讀 breadth_ladder_summary.json + FND-2 universe_summary.json）：斷言 delisted-proof 充分 + survivorship 繼承自證，抓 silent regression 回 current-survivor（MIT b.6）。read-only 0-DB。 |
| `research/tests/test_aeg_breadth_ladder.py` | 26 case（synthetic，Mac 可跑，26 passed）。**bite-proof**=(T-tier-nest)cohort_ids 組 nested + recommended_tier 會 fail；(T-breadth-not-nindep)★招牌 n_independent(full)==n_independent(core25) + symbol-scaled 被偵測；(T-monotonic-survives/collapse)；(T-insufficient-n)n<30 sample 牆；(T-top-liq-pit-flag)asof-constant 降級；(T-determinism)ladder_id 跨進程穩定；(T-candidate-agnostic)兩 stub 隔離 + 0 候選硬編碼；(T-forbidden-route)0 control_api/0 DB write/OPENCLAW_DATA_DIR；(T-manifest-index)provenance 鏈；+ healthcheck 三態 + end-to-end run_ladder。`python3 -m pytest helper_scripts/research/tests/test_aeg_breadth_ladder.py -q`。 |

硬邊界：read-from-storage-only（FND-2 artifact 讀檔 + 候選 loader read-only PG，0 DB write / 0
backfill / 0 schema / 0 migration / 0 IPC / 0 auth / 0 order，絕不重抓 Bybit）；**survivorship
繼承不重算**（禁 current-survivor 捷徑）；**breadth ≠ n_independent**（time-cluster-bound，cost-wall
8-rebalance 牆機械化）；artifact 0 import control_api_v1 runtime。端到端真 adapter 驗證（Mac，
synthetic FND-2 artifact + 真 `MultidayTrendReferenceEvaluator` + 真 numpy tsmom + 真 duckdb
parquet）：bite 通過（n_independent core25==full=24 即使 breadth 5 vs 30）/ ladder_id 跨進程穩定 /
breadth_ladder.parquet 生成。**真 829-symbol universe + 真 market.klines 端到端留 E4-Linux（PG）。
待 E2 對抗審 + MIT leak/n_independent 審；E1 不自簽。**

## 2026-06-03 funding-tilt / 多日 funding carry 樞紐診斷 harness（`research/funding_tilt_diagnostic/`）

QC 證偽優先協議（`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-03--funding_tilt_carry_diagnostic_protocol.md`）
+ MIT cheap pre-check（`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-03--funding_tilt_data_task_precheck.md`，
PROCEED-TO-HARNESS conditional）的實作。對「perp-only directional funding-tilt 有扣成本後
edge」抱持懷疑、要求它證明自己；NO-GO / INCONCLUSIVE / regime-bet 是合法且（QC 預判清牆
~20-25%）最可能結果。**唯讀 PG**（只 SELECT，絕不寫 production 表），結果寫研究 artifact
（`${OPENCLAW_DATA_DIR:-/tmp/openclaw}/funding_tilt_diagnostic_runs/<run_id>/` 的 JSON +
markdown）。**三條紅線**聲明於報告：(1) demo 無 spot lending → perp-only directional（非
delta-neutral）；(2) funding cap SSOT=instruments-info upperFundingRate，禁從 history max
反推（信號用已實現 funding 排序不依賴 cap）；(3) funding 雙面會計 §3.0：`net = gross_price
+ funding_pnl − (fee+slip)`，funding_pnl 為**獨立項**（−side×F，多付空收），不雙重計入 cost。
**leak-free 鐵律**：funding 嚴格 `funding_ts < entry_open_ts − ε`（ε=1 結算間隔，排除與開盤
同時的當日 00:00 結算）+ naive 雙軌並列（協議 §2.1，gap>30% → NO-GO-B）。**不依賴
scipy/statsmodels**（純 numpy 自實作 + 復用 `lib/stats_common` 的 PSR/DSR/PBO/bootstrap）。
**verdict 主檢定 = funding-tilt forward significance**（pooled tertile long-short 前瞻 net
報酬 + Newey-West overlap-corrected HAC t-stat）+ §4.5 horizon-vs-cost-share 攤薄曲線。
**★ per-leg（long/short）分解（MIT 強制）**：分報兩腿 funding_pnl + gross_price + carry_share
——短-top leg 價格反向吃 carry（=squeeze）是核心問題，aggregate 正 net 不可藏單邊擠壓風險。
**K 鎖 8**（(K_A=3 + K_B=1) × 2 持有期，count_trial_budget 自檢；偷加 grid 不更新 K 被測抓）。
per-symbol 從 funding_ts 間距推 interval（欄 100% NULL；TON/POL=4h→7d=42 結算非 21）。regime
vol-tercile leak 修為 **expanding/prior-365**（修 trend full-sample cross-section leak）。
cohort 標 `breadth-limited / survivor-cohort / bull-heavy`（72.4% 正 funding）→ 任何正結果
= regime-bet / learning-only，除非 non-bull slice 獨立過。E1 IMPL DONE 待 E2 對抗審 + MIT
leak/sample 審 + QC 最終判定（E1 不自簽 sign-off）。

| 腳本 | 用途 |
|------|------|
| `research/funding_tilt_diagnostic/harness.py` | 編排器 + CLI：DATA TASK 0-5（canonical run+覆蓋 / funding 量級 / xsec 離散度 / fee tier / regime）+ Step0 樣本充分性 + 兩個 N_eff + funding persistence + funding-tilt forward HAC + §4.5 horizon-vs-cost-share 掃描（H_min∈{1,3,7,14} 診斷不入 K）+ §4b regime split + carry purity + DSR(K=8)/PSR/PBO/bootstrap，輸出 JSON+markdown。`--dry-run [--synthetic-carry|--synthetic-null]` 用合成資料（Mac 可跑不連 PG）；正式跑連 read-only PG。決策樹（§5）fail-fast：Step0→funding persistence→leak/naive→horizon-cost 攤薄→squeeze→net Sharpe→DSR/PSR/bootstrap→PBO→regime-bet→GO；verdict ∈ {INCONCLUSIVE-A/B, NO-GO-A/B/C/D/E, NO-GO(squeeze), regime-bet/learning-only, GO}。 |
| `research/funding_tilt_diagnostic/signals.py` | 2 信號族 leak-free/naive 雙軌：A cross-sectional funding-tilt tertile long-short（tiltscore=過去 L 結算已實現 funding 均值，L∈{3,9,21}；top tertile=short -1 / bottom=long +1，market-neutral）+ B time-series funding-extreme（per-symbol，θ=expanding 80th pct PIT）。`compute_tiltscore_series` 用 bisect 嚴格 funding_ts<open−ε；interval_uncertain symbol 從 rank 排除。`count_trial_budget()` 從枚舉算 K=8。 |
| `research/funding_tilt_diagnostic/cost_model.py` | §3.0 會計：`trading_cost_bps`（fee+slip RT，**不含 funding**）+ `funding_pnl_bps_for_settlements`（逐結算對齊 −side×F，多付空收，獨立項）+ `carry_cost_ratio`/`carry_share`（協議 §3.5 carry 歸因）。cap discipline：不讀也不反推 funding cap。 |
| `research/funding_tilt_diagnostic/pnl.py` | trade 構造（open-to-open，協議 §2.4）+ 2 持有期變體（daily / flip_hold_min H_min=7）+ funding_pnl 逐結算對齊持有窗（8h=21/4h=42 結算）+ **`trade_metrics_with_legs`：per-leg（long/short）會計三項 + carry_share + carry_cost_ratio 分解**（MIT 強制）。 |
| `research/funding_tilt_diagnostic/stats.py` | **純 numpy** 統計：`funding_persistence_ljung_box`（§4.1 carry 基礎）/ `funding_tilt_forward_significance`（**verdict 主檢定**：pooled forward + Newey-West overlap-corrected HAC t，含相對離散度地板 fail-closed 防退化 false-GO）/ `pca_effective_n`（price-return N_eff）/ `funding_tiltscore_pca_effective_n`（§4.3 新，回答 operator「funding 比 price 更獨立？」）/ Jarque-Bera（厚尾→PSR）/ ARCH-LM（vol clustering→bootstrap）/ 年化 ×365。與 `lib/stats_common`（PSR/DSR/PBO/bootstrap）互補不重疊。 |
| `research/funding_tilt_diagnostic/data_loader.py` | 唯讀載入器（強制 `set_session(readonly=True)`）：**canonical run-versioned** funding（`research.alpha_funding_rates_history`，固定 `CANONICAL_FUNDING_RUN_ID=18b3c2f8…` 只讀它，run_id=%s 過濾防跨 run 混讀）+ 日線 OHLC + listed_at survivorship。`infer_funding_interval_minutes`（從 funding_ts 間距推眾數，欄 100% NULL）。`compute_rule_based_regime` vol-tercile leak 修為 expanding/prior-365（leak-free PIT，禁 HMM）。DSN 用 `lib.pg_connect.resolve_report_dsn()` 跨平台不硬編碼。 |
| `research/tests/test_funding_tilt_diagnostic.py` | 32 測試（synthetic，Mac 可跑）。**最重要**=(1) leak-free PIT 雙向 bite（餵真 carry→forward significant=True、零均值→不顯著、退化 fail-closed 不 false-GO）；(2) per-leg long/short 分解正確（短腿擠壓不藏）；(3) funding 雙面會計符號（多付空收、對稱、cost 不含 funding、逐結算非均值）；(4) interval 推導（8h=480 / TON-POL 4h=240 / 混亂 uncertain）；(5) vol-tercile leak fix（未來 vol 不改過去 regime）；(6) HAC≤naive；(7) DSR K=8 自檢；(8) 決策樹各路徑（INCONCLUSIVE-A 低 effective N / null-carry 非 GO / 白噪音 funding NO-GO-A / 完整 run 強制區塊全在 / horizon scan 曲線）+ 唯讀 SQL 靜態檢查 + canonical run_id 固定 + signal A top-short/bottom-long + interval_uncertain 排除。`python3 -m pytest helper_scripts/research/tests/test_funding_tilt_diagnostic.py -q`。 |

## 2026-06-02 多日 trend/momentum 樞紐診斷 harness（`research/multiday_trend_diagnostic/`）

QC 證偽優先協議（`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-02--multiday_trend_diagnostic_protocol.md`）
的 **Phase 1 fail-fast 早期決策樹** 實作。對「多日 trend 有 edge」抱持懷疑、要求它證明
自己；INCONCLUSIVE/NO-GO 是合法且最可能結果。**唯讀 PG**（只 SELECT，絕不寫 production
表），結果寫研究 artifact（`${OPENCLAW_DATA_DIR:-/tmp/openclaw}/multiday_trend_diagnostic_runs/<run_id>/`
的 JSON + markdown）。leak-free shift(1) 鐵律 + naive 雙軌並列（協議 §2.2）。**不依賴
scipy/statsmodels**（Linux runtime 缺，全部統計純 numpy 自實作）。**verdict 依據 = 正確
尺度 TSMOM coherence gate**：過去 k 日報酬符號 vs 未來 k 日報酬，pooled 全 symbol、
Newey-West overlap-corrected t-stat（lag=k-1），k∈{20,30,40,60,90}；需 significant-positive k
中**至少一對相鄰**形成連續尺度 plateau 且無顯著反轉才算相干正動量（daily-lag Ljung-Box
測錯時間尺度，已降級為 data_quality 報告統計，非 verdict 依據）。真跑（20 perp × 730 日
2024-06→2026-06，read-only PG）verdict=**NO-GO-TREND**：唯一顯著正僅 k40 孤立（無相鄰對）
+ k90 顯著反轉 + 0/20 symbol 正自相關 → 無相干 momentum；表面 0.66 Sharpe 是 short-side
厚尾/funding-credit artifact（long net ~0bps、short net 扛全部）。Step0 effective N=237≥60 通過、
PCA n_eff=2.09（PC1=68.7% BTC beta）= binding constraint（longer-history backfill 對 trend
upside 有限）。E1 IMPL DONE 待 E2 審查 → MIT leak 審計 → QC 複核。

| 腳本 | 用途 |
|------|------|
| `research/multiday_trend_diagnostic/harness.py` | 編排器 + CLI：跑 DATA TASK 1-5 + Step0 effective N + 正確尺度 TSMOM coherence gate（取代舊 daily-Ljung-Box gate）/ leak-free-naive / net-Sharpe-cost 早期門檻，輸出 JSON+markdown。`--dry-run [--synthetic-trending]` 用合成資料（Mac 可跑不連 PG）；正式跑連 read-only PG。fail-fast 順序：Step0 → TSMOM coherence → leak/naive → cost；第一個命中的門檻即 verdict（INCONCLUSIVE-A / NO-GO-TREND / NO-GO-B / NO-GO-C / SURVIVES_EARLY_GATES_NEEDS_PHASE_2）。 |
| `research/multiday_trend_diagnostic/signals.py` | 4 信號族（A TSMOM / B vol-scaled / C MA-cross / D x-sectional），每族同算 leak-free（shift(1) 正式）+ naive（含 current bar 診斷）雙軌。`count_trial_budget()` 從枚舉算 K=24（改 grid 忘更新 K 自檢抓到）。 |
| `research/multiday_trend_diagnostic/cost_model.py` | 多日成本：fee（taker RT 11bps / maker RT 4bps）+ slippage（RT 10bps）+ funding 按時間累積（協議 §3 樞紐，非按交易次數攤薄）；多單付正 funding、空單收 funding；cost_edge_ratio 分級。 |
| `research/multiday_trend_diagnostic/pnl.py` | trade 構造（open-to-open，禁 t 日收盤執行 t 日信號）+ 2 持有期變體（daily / flip_hold_min H_min=5）+ 方向翻轉計數（effective N 原料）+ per-trade gross/net + 多空 + regime + funding 拆解。 |
| `research/multiday_trend_diagnostic/stats.py` | **純 numpy** 統計（無 scipy/statsmodels）：`tsmom_significance`（**verdict 依據**：正確尺度過去 k 日→未來 k 日 + Newey-West overlap-corrected t-stat，含相對離散度地板 fail-closed 防退化輸入 false-GO）/ Ljung-Box（降級為日尺度 data_quality 廣度統計）/ ADF / KPSS / Jarque-Bera（厚尾→PSR 非 normal）/ ARCH-LM / PCA effective N=(Σλ)²/Σλ² / 年化 ×365。χ²/常態臨界值查表。與既有 `lib/stats_common.py`（PSR/DSR/bootstrap）互補不重疊。 |
| `research/multiday_trend_diagnostic/data_loader.py` | 唯讀載入器（強制 `set_session(readonly=True)`）：日線 OHLC + funding 代表性均值（覆蓋僅 ~58 天→標 INCONCLUSIVE-on-coverage）+ listed_at survivorship + **本地 rule-based regime**（regime_snapshots 空 → BTC 200日MA+vol tercile，禁 HMM，leak-free PIT）。DSN 用 `lib.pg_connect.resolve_report_dsn()` 跨平台不硬編碼。 |
| `research/tests/test_multiday_trend_diagnostic.py` | 36 測試（synthetic，Mac 可跑）。**最重要**=證 leak-free shift(1) 有 bite（注入 look-ahead → naive Sharpe 顯著高於 leak-free + inflation>30%）；另覆蓋 funding 累積/多空符號、effective N 翻轉計數、PCA 高相關降維、正確尺度 TSMOM 顯著性（真 momentum 有 bite / 隨機漫步 null / HAC≤naive / **退化 ramp fail-closed 不 false-GO**）、TSMOM coherence 相鄰判定（孤立單 k / 相鄰對 / **非相鄰兩端** / 反轉破壞相干）、Ljung-Box/JB/ADF 在已知性質上判定、決策樹 fail-fast（端到端 NO-GO-TREND）、唯讀 SQL 靜態檢查、禁 HMM。`python3 -m pytest helper_scripts/research/tests/test_multiday_trend_diagnostic.py -q`。 |

## 2026-06-02 Gate-B 隔離 listing-capture 探針（`research/gate_b_*` + entry）

AEG Gate-B：以**完全獨立**的進程驗證「上市捕捉管線是否就緒」——量測新 symbol 從
PreLaunch→Trading 轉移時，本地 public WS 對首筆成交的 capture_lag 與 trigger 後
+30/+60/+300s markout。R-0 隔離紅線：絕不 import 任何生產模組（openclaw_engine /
SymbolRegistry / KlineManager / governance_hub / 生產 bybit client / scanner /
strategy / intent / decision_lease），零 auth / 零 order / 零 DB write，只打 public
market REST + public WS。SoT = live REST `GET /v5/market/instruments-info?...&status=PreLaunch`
（前瞻 launchTime / curAuctionPhase / preListingInfo.phases，**不**用 symbol_universe_snapshots
的過去 listed_at）。verdict 必含 `INCONCLUSIVE_NO_TRANSITION`（phase 轉移稀有，無事件
非 fail）+ `TRANSITION_BUT_NO_CAPTURE`（轉移發生卻有 symbol 沒抓到首成交，集合完備性
fail-closed，total-miss + partial-miss 同歸此判，絕不誤報 PASS_CAPTURE）。E2/E3/BB sign-off
通過；探針本身尚未執行（手動觸發留待後續，capture_lag/alpha 定論需 ~Q4 真實上市樣本）。

| 腳本 | 用途 |
|------|------|
| `research/aeg_gate_b_probe.py` | entry 組裝器：WS 背景執行緒跑 event loop + 主執行緒固定間隔輪詢 REST，把 PreLaunch 候選同步給 WS 動態訂閱、餵 launchTime 給 capture_lag 基準；到 `--duration-seconds`（預設 24h）收尾寫 manifest/summary/verdict/parquet。`--dry-run` 只建目錄寫 INCONCLUSIVE verdict（結構驗證，不連 WS/不打 REST）。匯入零副作用（只有 main/run_probe 才連線）。 |
| `research/gate_b_rest.py` | SoT 層：純 urllib（仿 `replay/bybit_public_client.py` 隔離模式但不 import 它）+ endpoint allowlist 輪詢 instruments-info，PreLaunch→Trading 純記憶體 phase 狀態機，落 `rest_phase_poll.jsonl`，回報需 WS 訂閱的候選集合。無 auth/簽名/下單/DB。 |
| `research/gate_b_ws.py` | 捕捉管線層：`websocket-client`（延遲 import；Linux runtime 已驗）獨立連 `wss://stream.bybit.com/v5/public/linear`，只在 symbol 進 PreLaunch 候選才動態 sub `kline.1.{sym}`+`publicTrade.{sym}`（分批 ≤10/則）+ 固定訂 BTC `publicTrade.BTCUSDT` 作 liveness/unpoisoned 哨兵（2026-04-05 handler-not-found 毒化教訓）。算 capture_lag（first publicTrade event_ts − launchTime；≤5min=PASS_CAPTURE）+ in-memory mid ring 回填 markout。每 row 帶 leak-free provenance（ingest_ts_local / event_ts_exchange / 差值）。 |
| `research/gate_b_artifact.py` | 封裝/裁決層：跨平台 artifact root `${OPENCLAW_DATA_DIR:-/tmp/openclaw}/aeg_gate_b_runs/<run_id>/`（禁硬編碼）、各 channel JSONL writer、manifest（point_in_time=true + 隔離聲明 + provenance 規格）、duckdb parquet 鏡像（延遲 import，缺套件 skip 不阻斷）、verdict（含 `INCONCLUSIVE_NO_TRANSITION`）。duckdb 只寫本地 parquet，非生產 PG。 |
| `research/tests/test_gate_b_probe.py` | 32 測試。**最重要**=import 隔離自證（子進程乾淨 sys.modules + 路徑式檢查：任一載入 module 的 `__file__` 不得落在 `program_code/`/`rust/`，對應 E3 grep I1-I4）；另覆蓋靜態 auth/order/DB 呼叫面=0、phase 狀態機、capture_lag PASS/SLOW（5min 閾值）、MidPriceRing markout 回填、BTC control unpoisoned、verdict 含 INCONCLUSIVE、artifact root 跨平台。`python3 -m pytest helper_scripts/research/tests/test_gate_b_probe.py -q`。 |

## 2026-06-01 helper_scripts/lib/ Python 共享 library（E5 finding #3 + #4 整併）

| 腳本 | 用途 |
|------|------|
| `lib/__init__.py` | `helper_scripts.lib` package marker — offline research / report scripts 的 Python 共享 library 入口。在此 package 出現前 `lib/` 只放 shell script，導致報告腳本各自 copy-paste PG 連線 + 統計公式。硬邊界：只服務 offline scripts，不得被 `control_api_v1/app/` runtime 匯入。 |
| `lib/stats_common.py` | 共享統計公式整併層（E5 #3）：`_safe_float` / `_safe_int` / `_normal_cdf` / `_skew` / `_kurtosis` / `psr_bailey_ldp`（PSR Bailey-LdP 2014）/ `dsr_with_k`（Deflated Sharpe）/ `block_bootstrap_ci`（stationary block bootstrap，seed 為必填參數）/ `wilson_ci_95(n,n_eff)` / `pbo_cscv`（CSCV PBO，seed 必填）/ `day_bucket` / `n_eff_horizon_overlap`（採 math.ceil canonical，根除 8b `// 5` floor latent bug）。原為 `w_audit_8b` / `w_audit_8c` metrics 兩份 copy-paste；alpha_candidate 透過 8b/8c 間接復用。8b/8c 兩份僅亂數 seed 與 n_eff floor/ceil 差異，整併保留各 caller 歷史 seed。純 stdlib；無 DB / 無 IO。 |
| `lib/pg_connect.py` | 共享 PG 連線 helper（E5 #4）：`resolve_report_dsn()`（優先 `OPENCLAW_DATABASE_URL`，否則由 `POSTGRES_*` 拼 DSN，host 預設 127.0.0.1 不硬編碼）+ `connect_report_pg(application_name, *, statement_timeout_ms_default, statement_timeout_env)`。整併 `w_audit_8b` / `w_audit_8c` / `alpha_candidate` 三個 report wrapper 的 byte-identical `_get_conn`（唯一差異 application_name 與預設 timeout）。延遲 import psycopg2；read-only；不引入 singleton。**刻意只收口 report wrapper 族**：其餘 ~20 個 cron/db/research 連線 helper 因 DSN env-var 口徑不同（`DB_URL` vs `OPENCLAW_DATABASE_URL`、secrets-file fallback 等）+ runtime cron 風險，留待後續分批整併；`app/governance_routes.py::_get_autonomy_pg_conn` 屬另一階段不碰。 |
| `lib/tests/test_stats_common.py` | `stats_common` + `pg_connect.resolve_report_dsn` 的 golden-value 測試（31 tests）：每個整併函數鎖「已知輸入→已知輸出」+ 邊界（n=0/1/all-equal/div-by-zero）+ seed 確定性 + n_eff ceil-vs-floor bug-fix 對照 + DSN 解析口徑。`python3 -m pytest helper_scripts/lib/tests/test_stats_common.py -q`。 |

## 2026-05-31 M4 Stage 1 production DRAFT runner

| 腳本 | 用途 |
|------|------|
| `m4/stage1_production_runner.py` | M4 Stage 1 non-dry-run core：透過既有 kline/fills/liquidations/funding source-loader SQL 讀 PG，生成 shift(1) leak-free cross-correlation + funding/liquidation event-window candidates。預設只計算不寫庫；`pattern_miner_stage_1.py --enable-writeback` 時每個 DRAFT row 必須提供一個真實 `decision_lease_draft_id` UUID，或顯式 `--acquire-governance-leases` 經 GovernanceHub IPC 取得 lease。V103 `decision_lease_draft_id` 目前是 UUID；非 UUID-compatible Governance lease 會 release FAILED 並 fail-closed 不 INSERT。analysis lane `exploratory` 不直接寫 `learning.hypotheses.status`，統一映射為 V100 enum 可接受的 `draft`。 |

## 2026-05-29 P2-OPS-2-GITLEAKS secret-scan pre-commit hook 基礎設施

| 腳本 | 用途 |
|------|------|
| `git_hooks/pre-commit` | canonical pre-commit hook：gitleaks 在 PATH → `gitleaks protect --staged --redact`（+ `--config git_hooks/.gitleaks.toml`），有 finding 即 exit 1 擋 commit（對 secret fail-closed）；gitleaks 不在 PATH → 印中文 WARN + SKIP → exit 0 放行（不因缺工具卡死所有人的 commit；真正 gate 是有人跑 installer，hook 本可 `--no-verify` 繞過）。`.git/hooks/` 不入版控，由 `install_git_hooks.sh` 複製落地。用 `git rev-parse --show-toplevel` 定位 config，不硬編碼路徑。 |
| `git_hooks/install_git_hooks.sh` | 把 `git_hooks/pre-commit` 複製進本 repo `.git/hooks/pre-commit` + chmod +x。鏡像 `systemd/install_*.sh` 風格（set -euo pipefail / `[install][OK\|FAIL\|WARN]` / 退出碼分級）。用 `git rev-parse --show-toplevel` + `--git-dir` 定位（不硬編碼路徑；支援 worktree 相對 git-dir 正規化）。既有 pre-commit 內容不一致時 refuse 無聲覆蓋；`--force` 才覆寫（先 backup 成 `.pre-commit.bak`）；內容一致則 idempotent 重裝。 |
| `git_hooks/.gitleaks.toml` | gitleaks config 起手版：`[extend] useDefault = true` 繼承內建 ruleset；`[allowlist]` regex 排除 cross-language HMAC test fixture 假陽性（pinned hex `1b2b18d7…b78fc` + 測試 signing key `test-live-auth-signing-key-do-not-use-in-prod`，OPS-2 runbook §10.5 byte-identical 測試向量，非真 credential）+ path 豁免 `credential_rotation.md`。Mac 未裝 gitleaks 無法實跑 → 標為起手版，首次實跑 + FP 調校待 gitleaks 安裝後 follow-up。 |

## 2026-05-27 P0-OPS-4 GAP-D PG dump cron + healthcheck IMPL

| 腳本 | 用途 |
|------|------|
| `cron/install_pg_dump_cron.sh` | round 1 — `crontab -l` idempotent installer for `trading_ai_pg_dump_cron.sh`；Linux only；偵測 existing entry 避重複；`--dry-run` 預覽。對齊 PA spec §10 GAP-D + MIT empirical report §1.7 Phase 1 plan A（local-only）。 |
| `cron/trading_ai_pg_dump_cron.sh` | round 1 — daily 03:00 UTC PG `-Fc` dump wrapper：EXCLUDE `learning.decision_features_evaluations`（182GB / 17d / 無 retention）+ `*_damaged_*` quarantine 表；retention 30d；完成/失敗均 INSERT `learning.governance_audit_log` event_type `pg_dump_completed` / `pg_dump_failed`（V113 CHECK enum 補登 26-value）。Linux only；lock dir 防 overrun；cron heartbeat sentinel start-time touch `${OPENCLAW_DATA_DIR}/cron_heartbeat/trading_ai_pg_dump.last_fire`。 |
| `cron/verify_pg_dump.sh` | round 1 — Bash sidecar 5-check：backup dir / latest dump mtime < 26h / size > 1MB / md5 對齊 JSONL entry / retention prune 生效。operator SSH ad-hoc 場景下不需 venv 快速跑 14-step drill；Python 版 `check_pg_dump_freshness.py` 才是 healthcheck pipeline 主要入口。 |
| `canary/healthchecks/check_pg_dump_freshness.py` | round 2 — Python 主入口 7-check standalone（FA acceptance §E #7）：5 個對齊 `verify_pg_dump.sh` + 第 6 個 L0 schema coverage smoke（subprocess `pg_restore --list <latest> \| grep earn_movement_log` per FA §C.5）+ 第 7 個 governance_audit_log audit trail（last `pg_dump_completed` ts < 26h）。V113 未 apply / cron 未 fire → INSUFFICIENT_SAMPLE-skip fail-soft。stdlib + psycopg2 only；Linux only（`sys.platform` guard）。被 `passive_wait_healthcheck.checks_cron_heartbeat.check_80_pg_dump_freshness()` wrapper 引用。對齊 [80] healthcheck slot；JSON 輸出 + exit 0/1/2 對齊 `_common.py` 慣例。 |

## 2026-05-28 M11 replay_runner Daily Stage A Smoke

| 腳本 | 用途 |
|------|------|
| `cron/install_m11_replay_runner_cron.sh` | M11.a daily 04:00 UTC cron installer：對齊 `install_pg_dump_cron.sh` 模式（Linux only / idempotent guard / DRY-RUN 預設 / env value validate `[[:space:]%[:cntrl:]"'\\\$\`]` + 長度 ≤ 200 / pre-flight 4 項 (secrets env + API token + fixture + release binary)）。`OPENCLAW_M11_REPLAY_CRON_APPLY=1` 才實際寫 crontab。避撞時段已驗：03:00 pg_dump / 03:17 ml_training_maintenance / 04:00 ★ / 04:41 feature_baseline_writer / 06:00 counterfactual_daily / 09:00 replay_key_rotation_check。對齊 PA proposal `2026-05-28--m11_replay_runner_schedule_proposal.md` §4.4 + operator confirm Daily 04:00 UTC (= M11.a)。 |
| `cron/m11_replay_runner_daily_cron.sh` | M11 Stage A single-fixture smoke heartbeat wrapper：POST `/api/v1/replay/experiments/register` + `/run` 走 in-tree `synthetic_btcusdt.json` fixture；Bearer auth 重用 operator API token（OQ-1 Service principal swap follow-up）；CSRF double-submit (cookie+header 同值 random 32B hex)；fail-soft exit 0 給 cron 避 mail spam。完成/失敗均 INSERT `learning.governance_audit_log` `event_type='audit_write_failed'` + `payload.alert_type='m11_replay_runner_smoke_completed/_register_failed/_failed'`（V035 未含 m11_* event；piggyback per `replay_key_rotation_check` pattern，Sprint 3 Phase A 同步擴 enum）。Linux only / lock dir / heartbeat sentinel `cron_heartbeat/m11_replay_runner_daily.last_fire` / JSONL audit。`[48]` healthcheck flip 預期：first fire 後 24h 內 FAIL → PASS（rows_24h ≥ 1 + rows_7d ≥ 1 條件達標）。 |

## 2026-06-08 Residual Stage-0R Preflight Producer Orchestrator（PART 4 Gap A/D）

| 腳本 | 用途 |
|------|------|
| `cron/residual_stage0r_preflight_cron.sh` | Stage-0R β-residualization producer orchestrator 手動 one-shot CLI shim（PART 4 Gap A/D）。把「數值預閘達標但缺 lineage」的 demo `mlde_shadow_recommendations` 候選，經多因子（btc+market+funding）residual + sign-flip permutation + Gap D selection-bias 斷言（K≥10/oos≥0.20/cv_protocol/embargo≥7）→ 註冊 replay experiment（`replay.experiments` + sealed `hidden_oos_state_registry`，重用 `residual_hidden_oos_bridge`）→ 寫 drar（`learning.demo_residual_alpha_reports`）→ 蓋 lineage（`mlde_shadow_recommendations.replay_experiment_id/manifest_hash/evidence_source_tier='calibrated_replay'`，WHERE replay_experiment_id IS NULL 防重蓋），使下游 `mlde_demo_applier` 的晉升閘真正審判真實候選。★ **三重 OFF（行為中性）**：`OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1` + `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` + `--jobs residual_preflight`（不在 DEFAULT_JOBS）皆滿足才寫 row。★ **NO peer synthesis**（單一配置 PBO 誠實 defer，`candidate_oos_returns=None`，不捏造 peer）。★ **DEMO lane only**（零 live/auth/order/risk/lease）。**net_side 從真實 fills 推導**（funding sign 正確，非 +1 預設）。必要時間窗 env：`OPENCLAW_RESIDUAL_PREFLIGHT_SINCE/OOS_START/DATA_END`（ISO-8601；缺則 skipped）。Linux only / lock dir / heartbeat sentinel `cron_heartbeat/residual_stage0r_preflight.last_fire` / fail-soft exit 0。內部呼 `ml_training_maintenance.py --jobs residual_preflight`（job dispatcher → `_run_residual_preflight` → `residual_stage0r_preflight.run_residual_stage0r_preflight`）。**Linux flag-ON 真寫驗證 owed to PM**（Mac 測試用 FakeCursor/injected fn）。 |

## 2026-05-27 P0-OPS-1 HTTPS / Secure cookie / CSRF / CSP Track A IMPL

| 腳本 | 用途 |
|------|------|
| `lib/tls_cert.sh` | OPS-1 Track A — 跨平台 Tailscale cert 路徑與 renewal helper：`resolve_openclaw_tls_cert_dir`（Linux `/var/lib/tailscale/certs` / Darwin `$HOME/Library/Application Support/Tailscale/certs`）、`resolve_openclaw_tls_cert_host`（讀 env 或 `tailscale status --json`）、`tls_cert_days_remaining`（openssl + 跨平台 date）、`tls_cert_should_renew`（< 14d threshold）。被 install_caddy.sh + systemd unit 共用。 |
| `Caddyfile.template` | OPS-1 Track A — Caddy 反向代理設定模板。`envsubst` 處理：HTTPS bind tailnet IPv4 + Tailscale cert + reverse_proxy `127.0.0.1:8000` + X-Forwarded-Proto 傳遞。`admin off` 不暴露 :2019。HSTS header 在反代邊界加。 |
| `install_caddy.sh` | OPS-1 Track A — 一次性 Linux/macOS 部署：preflight Tailscale + 安裝 Caddy + envsubst 生 Caddyfile + `tailscale cert` 首次拉證書 + 安裝 systemd unit/timer + curl 驗證 + 首次 HTTPS cert trust checkpoint 提示。預設 `--dry-run`；`--apply` 才實際寫 `/etc/caddy/Caddyfile`。跨平台分支 (Linux apt / macOS brew + launchd 指引)。 |
| `canary/healthchecks/csrf_shadow_zero_verify.sh` | OPS-1 enforcing cutover gate — 掃描 `${OPENCLAW_DATA_DIR:-/tmp/openclaw}` 近 7d API/log JSONL 中 `csrf_shadow:` violation；0 → PASS，>0 → FAIL，無可掃 log → INSUFFICIENT_SAMPLE。用於 `OPENCLAW_CSRF_SHADOW=1` shadow soak 後 unset 前的自動化檢查。 |

> **測試環境變數 — `OPENCLAW_CSRF_SHADOW=1`（canonical test env，per E4 F-NEW-1）**：跑
> `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/` 整個 pytest 套件時，
> **必須**設 `OPENCLAW_CSRF_SHADOW=1`。原因：CSRF enforcement 預設 fail-closed；測試 client 多數不帶
> double-submit cookie+header token，未設此旗標時約有 **66 個 false failure**（被 CSRF 擋下，非真 regression）。
> shadow 模式只記錄 `csrf_shadow:` violation 而不阻擋請求，讓測試針對被測邏輯而非 CSRF middleware。
> 範例：`OPENCLAW_CSRF_SHADOW=1 pytest control_api_v1/tests/`。注意：此旗標**僅供測試 / shadow soak**；
> production cutover 必 unset（fail-closed），unset 前以上方 `csrf_shadow_zero_verify.sh` 驗 0 violation。
| `systemd/openclaw-caddy.service` | OPS-1 Track A — Caddy reverse proxy systemd unit（`Type=notify` + `Restart=always` 5s 復活 + `CAP_NET_BIND_SERVICE` 不需 root 綁 443）。 |
| `systemd/openclaw-tls-renew.service` | OPS-1 Track A — Tailscale cert renewal `Type=oneshot`，由 sibling timer 觸發。引用 `lib/tls_cert.sh` 走 14d threshold 判定 + 拉新 cert + chown caddy + `systemctl reload openclaw-caddy.service`。`OnFailure=` 接 notify service。 |
| `systemd/openclaw-tls-renew.timer` | OPS-1 Track A — 每日 03:00 UTC `OnCalendar` 觸發 renew service。`Persistent=true` 機器關機跨午夜後補跑。 |
| `systemd/openclaw-tls-renew-notify.service` | OPS-1 Track A — renewal 失敗 hook（`OnFailure=` 才被拉起，**不可 enable**）。占位實作寫 stderr + journal；接 Telegram/Grafana 待 operator 提供接點。 |

## 2026-05-27 P0-OPS-4 GAP A + GAP F systemd unit IMPL

| 腳本 | 用途 |
|------|------|
| `systemd/openclaw-engine.service` | GAP F — Linux systemd unit for Rust openclaw-engine 主進程；Restart=on-failure + RestartSec=10 + StartLimitBurst=5 / 5min；PreStart 三檢（binary / ipc_secret / database_url file）；EnvironmentFile 載 basic_system_services.env；對應 macOS launchd `deploy/com.openclaw.engine.plist`。占位符 `__ENGINE_USER__ / __OPENCLAW_BASE_DIR__ / __OPENCLAW_DATA_DIR__ / __OPENCLAW_SECRETS_ROOT__` 由 install script sed 替換。 |
| `systemd/openclaw-watchdog.service` | GAP A — Linux systemd unit for engine_watchdog.py；Restart=always + RestartSec=10 + StartLimitBurst=10 / 10min；CLI args 對齊 restart_all.sh:226（--stale-threshold 45 / --grace-period 120 / --poll-interval 1）；解決 watchdog 自 crash 後無自動 respawn 的 RTO 鏈缺口（< 1min）。 |
| `systemd/install_engine_service.sh` | Linux-only installer for openclaw-engine.service；root + Linux guard；sed 替換 5 占位符；atomic mv + occupy-check + systemd-analyze verify + daemon-reload；install 後不自動啟動（留 operator 5-gate launch sequence）。 |
| `systemd/install_watchdog_service.sh` | Linux-only installer for openclaw-watchdog.service；自動偵測 python venv (PYTHON_BIN env > $HOME/.venv/bin/python3 > /usr/bin/python3)；sed 替換 6 占位符；同 root + Linux + daemon-reload pattern。 |
| `systemd/README.md` | systemd unit 部署文件：跨平台 portability / operator deploy 三段 hand-action checklist (A install / B enable+start / C restart_all.sh 共存) / RTO ≤ 5min 4-step 驗證 SOP（含 SIGKILL 模擬 + systemctl poll + snapshot age 恢復驗證）/ 反模式 / cross-reference spec。 |


## 2026-05-25 Sprint 2 W2-F NEW QA-2 AC-19 ALT bucket cron IMPL

| 腳本 | 用途 |
|------|------|
| `cron/ac19_alt_bucket_daily_query.sql` | AC-19 14d 監測 daily SQL：post-deploy window 5/19~6/2 + bucket-split (large_cap=BTC/ETH / alt=其它 15 symbol) + Wilson CI 95% lower/upper bound + 3 級 verdict (PASS / MARGINAL / FAIL / INSUFFICIENT_DATA)；psql --csv -f 直接跑。per W1-G SOP §2 canonical。 |
| `cron/ac19_alt_bucket_daily_cron.sh` | Daily 08:00 UTC cron wrapper：讀 secrets env file 取 PG creds → psql --csv 跑 SQL 寫 CSV → ac19_alt_bucket_jsonl_writer.py 將結果 append 到 14d 累積 JSONL summary + heartbeat sentinel + lock mkdir 防 overrun + day_index>14 idempotent skip。Exit code 對齊 verdict 聚合（0/1/2）。 |
| `cron/ac19_alt_bucket_jsonl_writer.py` | CSV → JSONL append + sanity verify：解析 psql --csv 輸出 / 重算 Wilson lower/upper（防 SQL ↔ Python 漂移；超過 1pp tolerance 寫 sanity_drift_pct）/ 重判 verdict / append-only fsync 寫累積 summary。stdlib only（無 psycopg2）。 |
| `cron/tests/__init__.py` | 測試 package marker。 |
| `cron/tests/test_ac19_alt_bucket_daily.py` | 44 pytest case：Wilson formula 5 case（大型/小樣本/邊界/完美 fills/fail-loud）/ 3 級 verdict 13 case（large_cap+alt 閾值 inclusive 邊界 + INSUFFICIENT_DATA + unknown bucket fail-loud）/ bucket 分類 3 case / day_index 5 case（day 1 / day 7 SOP baseline / day 8 cron target / day 14 邊界 / naive datetime）/ CSV 解析 4 case（兩 row / psql trailing line / 空 / malformed fail-loud）/ JSONL 構造 3 case（baseline 對齊 / sanity drift / INSUFFICIENT_DATA）/ append 2 case（新建 / 既存保留）/ exit code 聚合 5 case / CLI dry-run 2 case。 |

## 2026-05-25 Sprint 2 W2-B Alpha Tournament Stream A scaffold

> **scaffold ≠ done（P1-16，2026-05-29 TW）**：以下為 source scaffold，非
> Alpha Tournament 完成。`tournament_orchestrator.py` 仍是 Sprint 2 stub return
> 0，active = false，尚無 candidate verdict / Stage 0R evidence。SSOT 狀態見
> `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`（IMPL-PENDING）。

| 腳本 | 用途 |
|------|------|
| `alpha_tournament/__init__.py` | helper package entry + MODULE_NOTE；標註 ADR-0026 track='direct_exploit' + V100/V103 actual schema + engine_mode IN ('demo','live_demo') hard invariants；read-only SELECT only。 |
| `alpha_tournament/attribution_daily.py` | Sprint 2 daily cron @02:30 UTC fire；14d demo bucket-split per strategy × symbol × date + Wilson CI 95% lower bound projection + Bonferroni K=2 alpha 調整 + sample size cumulative projection (target ≥ 30 per CR-6)；stdout JSON log；dry-run mode 不連 PG（驗 module import + SQL syntax）。 |
| `alpha_tournament/tournament_orchestrator.py` | Sprint 2 stub return 0；Sprint 3+ M11 counterfactual replay integration + candidate ranking 邏輯接續入口。 |
| `alpha_tournament/14d_bucket_split.sql` | psql -f 直接跑的 standalone SQL；對映 attribution_daily.py SQL 內嵌版本，供 cron wrapper / 手動 audit 使用。WHERE track = 'direct_exploit' + engine_mode IN ('demo','live_demo') + attribution_chain_ok = TRUE 三 invariant hard-coded。 |

## 2026-05-23 Sprint 5+ Wave 1 §4.4 production hardening

| 腳本 | 用途 |
|------|------|
| `db/health_60s_boundary_verify.sh` | Sprint 5+ Wave 1 §4.4.2 — REST latency 60s rolling window boundary verify SOP wrapper；對齊 passive_wait_healthcheck.sh 範式（venv-aware + secrets load + container psql）；3 SQL section（sample inter-arrival ±2s jitter / samples_per_min duplicate emit / 30min summary row_count ≥25）；exit 0/1/2 PASS/FAIL/DB-error。code-level 60s expire 已 verified（bybit_rest_client.rs:318-441 lazy expire `now.checked_sub(60s) → retain`）；本 wrapper 補 production runtime empirical verify（emitter scheduler tokio tick / task crash 等 runtime 失準路徑）。 |
| `db/health_60s_boundary_verify.sql` | Sprint 5+ Wave 1 §4.4.2 — pure SQL 配套；3 section LIMIT 20+30+per-metric；只覆蓋 api_latency + engine_runtime（60s emitter tick 對齊範疇）；不含 risk_envelope (300s) / pipeline_throughput (30s)。 |
| `db/health_f2_sanitize_monitor.sh` | Sprint 5+ Wave 1 §4.4.3 — F-2 NaN/inf sanitize fire log 監測；DISABLED-BY-DEFAULT 直到 Sprint 5+ §4.2.2 wireup PaperState SSOT 後 enable（Sprint 4+ Wave B placeholder 階段 F-2 fire 必 0，過早 enable 等同永遠 PASS）；grep-based 而非 PG-based（F-2 sanitize 在 in-process tracing::warn 觸發不寫 V106；engine.log 為唯一 SSOT）；cross-platform date (GNU `-d` / BSD `-v`)；OPENCLAW_F2_THRESHOLD=0 default = 任一 fire 即 alert。 |
| `db/ac1b_monthly_healthcheck.sh` | Sprint 5+ Wave 1 §4.4.4 — Sprint 4+ §4.1.4 AC-1b production verify monthly cron；對齊 Sprint 4+ Phase 3c 驗範式（30 min × 6 active domain × ≥5 row）；對齊 passive_wait_healthcheck.sh 範式（secrets load + container psql + sentinel mtime touch）；crontab spec `30 3 1 * *` 月初 03:30 UTC（避撞 passive_wait_healthcheck 6h cron）；exit 1 表 ≥1 domain < 5 row；對齊 operator Stage F §8.6 PM phase 3e 拍板「§4.4 全部進 hardening + AC-1b monthly cron」。 |

## 2026-05-20 P0-ENGINE-HALTSESSION-STUCK-FIX Layer B

| 腳本 | 用途 |
|------|------|
| `canary/engine_watchdog.py` | Layer B（spec v0.2 §4）擴增：新增 TRADING_INERT_PROLONGED 業務心跳探測；獨立於 ENGINE_CRASH 路徑（severity=WARNING，不重啟 engine）；trigger conditions = paper_paused 持續超 threshold OR recent_intents 滾動窗口無增長；per-engine 獨立 state；cooldown 防 alarm spam；TRADING_INERT_CLEARED transition log；in-memory + on-disk state（spec B-5：watchdog restart 不重置 incident）；CLI 加 `--disable-inert-probe` / `--inert-probe-config` 兩 flag。 |
| `canary/watchdog_inert_probe.toml` | Layer B per-env threshold 配置：demo=60min/20min（學習資料源 / grid-dominant aware）、live_demo=30min/15min（中間嚴格）、live=15min/10min（最敏感）、paper=demo defaults（dormant default）。fail-loud RAISE on TOML parse error；缺檔 fallback 預設值。 |
| `canary/test_engine_watchdog.py` | Layer B 32 unit tests：resolve_engine_label / load_inert_probe_config / detect_paper_paused_stuck / detect_intents_zero_delta / evaluate_inert_probe / state persistence / run_inert_probe_once；spec B-1/B-1a/B-2/B-3/B-4/B-5/B-7 全覆蓋。Mac unittest + pytest 32/32 PASS。 |
| `canary/test_watchdog_alert.py` | WATCHDOG-ALERT-WIRE（2026-06-05）22 unit tests：共用 alert_config loader（file-primary / env-fallback / 壞檔安全 / save round-trip 0600 / mask_secret）、SSRF 守衛（阻擋 metadata 169.254.169.254 / loopback / RFC1918 / link-local，拒 http，放行 public https）、watchdog emit 去重（≤1/key）+ recovery 清 marker + 未配置 no-op 不拋 + 告警掛起不拖主循環。Mac pytest 22/22 PASS。 |

## 2026-05-20 P0-ENGINE-HALTSESSION-STUCK-FIX Layer A Round 2

| 腳本 | 用途 |
|------|------|
| `canary/halt_audit_pg_writer.py` | MUST-FIX-3：tail Rust engine 寫的 `halt_audit.log` JSONL → INSERT `learning.governance_audit_log`（V098 24-value allowlist 已含 3 個 halt_session_* event_types）；按 spec §3.8 / §3.9 audit contract；ON CONFLICT pattern 冪等（複合 dedup = process_pid + ts_ms + event）；cursor state file 保證重啟不丟資料 + 不重複；jsonschema validate fail-soft；20 unit tests PASS + Linux PG integration 3 rows + idempotent 已驗。 |
| `cron/halt_audit_pg_writer_cron.sh` | MUST-FIX-3：1min cron wrapper；對齊 sibling pattern（outcome_backfiller_live_cron）；env 從 `$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env` 讀；mkdir-based lock 防 overrun；source-only（operator 確認 V098 已 land 後手動 crontab -e 加）。 |
| `canary/test_halt_audit_pg_writer.py` | MUST-FIX-3 unit + PG mock 整合測試：5 大類 17 + 3 = 20 cases；JSONL robust parser、cursor state、validate、resolve paths、PG-absent / 3-rows / idempotent / V098-absent fallback 全覆蓋。 |

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
| `reports/w_audit_8c_liquidation_cluster_stage0r.py` | W-AUDIT-8c Liquidation Cluster Reaction — Stage 0R replay 頂層 CLI wrapper（mirror sibling 8b shim 模式），委派至 `reports/w_audit_8c/liquidation_cluster_stage0r_report.py`。配 `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`。BB pre-flight gate 預設 True（2026-05-18 BB STRUCTURAL verdict 後）；spec v0.3 mandatory report fields + 4-agent (QC/MIT/FA/BB) review-ready Markdown + JSON。 |
| `reports/w_audit_8c/liquidation_cluster_stage0r_report.py` | W-AUDIT-8c Stage 0R 報告編排層（round 2 rework）：read-only PG 取數（fetch_panel_symbols + fetch_k_prior + _fetch_panel_rows with bucket_end_ts → bucket_end_ts_ms normalize）→ sibling 8C-S0R-2 `liquidation_cluster_stage0r_metrics` (compute_stage0r / compute_stage0r_sweep 真實 contract — dict 6 keys 含 sweep_cells/eligible_for_demo_canary_per_tier) → spec v0.3 14 mandatory fields JSON + 4-agent review-ready Markdown；落地至 `docs/CCAgentWorkSpace/{role}/workspace/reports/<date>--w_audit_8c_stage0r_<verdict>.{json,md}`。BB pre-flight gate fail-fast 不存在 BB STRUCTURAL report 即 exit 3。 |
| `reports/w_audit_8c/liquidation_cluster_stage0r_smoke_cli.py` | W-AUDIT-8c Stage 0R CLI 整合 smoke（round 2 sign-off invariant）：10 test 覆蓋 6 CRIT (1-6) + 4 HIGH (1,2,3,4) 修法，mock SQL panel → verify _extract_trigger_rows n>0 + sweep returns dict + Markdown 15 sections + 5 exclusion categories；不連 PG，可獨立執行。 |
| `reports/alpha_candidate_stage0r.py` | Alpha Tournament Candidate Stage 0R Runner 頂層 CLI wrapper（Track B reduced scope；mirror 8b/8c shim），委派至 `reports/alpha_candidate_stage0r/candidate_stage0r_report.py`。read-only offline；A2 functional / A1 stub draft_only。 |
| `reports/alpha_candidate_stage0r/candidate_stage0r_report.py` | Alpha Candidate Stage 0R Runner 的 PG 取數 + argparse + JSON render IO 層（mirror 8c metrics.py / report.py 拆分）：read-only PG 取數（復用 `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql` + raw_buckets count denominator）→ 委派 `candidate_stage0r_runner.run_candidates` → 輸出 JSON packet。fail-closed exit code（PG connect=2 / query=1，propagate 不吞）。 |
| `reports/alpha_candidate_stage0r/candidate_stage0r_runner.py` | Alpha Tournament Candidate Stage 0R Runner 純 offline 計算層（不連 PG，由 caller 傳 rows）：A2（functional）/ A1（stub draft_only）→ 6 sanity check（time-block CSCV PBO + sample_sufficiency 三態）→ 單一 JSON packet（per-candidate six_check + 整體 stage0_ready）。A1 硬標 `draft_only(basis_panel_infra_missing)`（PG 無 basis 源，不建 dead cohort code）。AMD §3.2 forbidden-output 紀律：只 emit `eligible_for_demo_canary`；governance check 1/5/6 標 ATTEST 待 E2 grep（ATTEST ≠ PASS）。 |
| `reports/alpha_candidate_stage0r/a2_cascade_adapter.py` | A2 liquidation_cascade_fade candidate adapter：復用 W-AUDIT-8c per-event `compute_stage0r`（方向與 A2 一致，不改 8c SQL/metrics）+ 兩 candidate adapter — (a) k_total override（8c max(25,n)×11664 inflation → candidate 真實 trial count 4+k_prior，call 後重算 DSR，否則 DSR 永 fail 是 silent stat 錯）；(b) fixed-horizon dynamic-exit proxy 標註（8c 固定 60m mark = A2 動態出場 OR(TP/SL/time-stop/reverse) 保守 proxy）+ per-symbol notional threshold pin（BTC $500k / ETH $300k）。 |
| `reports/alpha_candidate_stage0r/a2_maker_fill_feasibility.py` | A2 maker-fill feasibility diagnostic：read-only `market.liquidations` 生成 BTC/ETH cascade triggers，join `market.market_tickers` BBO，估算 PostOnly passive entry offset 在 60s 內是否被 best bid/ask touch；主 gate default 1bp offset / fill-rate ≥50% / n≥30；只輸出 `reject` / `draft_only` / `observe_more`，不產生 Demo/order/writeback。 |
| `reports/alpha_candidate_stage0r/a2_maker_fill_feasibility_smoke.py` | A2 maker-fill diagnostic 合成 smoke：passive buy/sell touch、no-touch reject、spread guard skip、sample gate、SQL read-only grep、query row grouping、forbidden-output token 0 hit。 |
| `reports/alpha_candidate_stage0r/candidate_stage0r_smoke.py` | Alpha Candidate Stage 0R Runner smoke（13 test）：A2 packet 結構 / k_total override DSR 重算 / per-symbol threshold 過濾 / A1 draft_only stub / AMD §3.2 forbidden-output JSON 0 hit / 少樣本 observe_more / sample_sufficiency 三態 / time-block CSCV（<4d None vs ≥4d 非 None）/ 無 A1 cohort dead code 斷言；合成數據不連 PG，可獨立執行。 |
| `reports/alpha_candidate_stage0r/a3_pairs_precheck.py` | A3 BTC/ETH cointegration pairs stats-first DRAFT precheck：read-only `market.klines` 取 BTC/ETH 對齊 K 線，計 OLS hedge ratio、Engle-Granger proxy residual AR(1) half-life、shift(1) z-score next-bar entry replay、two-leg fee-adjusted net edge；只輸出 `reject` / `draft_only` / `observe_more`，不產生 Stage 0 / Demo / order activation。 |
| `reports/alpha_candidate_stage0r/a3_pairs_precheck_smoke.py` | A3 pairs precheck 合成 smoke：cointegrated fixture 應 `draft_only`、random-walk residual 應 `reject`、短資料 `observe_more`、entry_ts 必晚於 signal_ts、SQL read-only grep、forbidden-output token 0 hit。 |
| `deploy/launchd_preflight.sh` | macOS launchd deployment preflight |
| `db/passive_wait_healthcheck/checks_cron_heartbeat.py` | `[75]`-`[79]` P1-CRON-INSTALL-WAVE-1（2026-05-18）— 5 個 cron wrapper 已 source/test closed 但 crontab 尚未 install；以 sentinel mtime 推斷 cron 是否按時 fire。WARN-by-default；`OPENCLAW_CRON_HEARTBEAT_REQUIRED=1` 升 FAIL。配對 install recipe `docs/execution_plan/2026-05-18--p1_cron_install_wave_1_install_recipe.md`。 |
| `db/test_cron_heartbeat_healthchecks.py` | `[75]`-`[79]` 單元測試（42 PASS）：fresh/missing/stale + threshold 邊界 + REQUIRED=1 升 FAIL + path 解析（HEARTBEAT_DIR > DATA_DIR）。 |
| `security/compute_sri_hashes.sh` | P2-WP05-CSP-UNSAFE-INLINE（2026-05-18）— 為 GUI pinned CDN 計算 SHA-384 SRI integrity attribute；操作者跑一次將輸出 paste 進對應 `app/static/*.html` <script> / <link>。default URL = `lightweight-charts@4.1.0`；版本未 pin → WARNING + exit 1。 |

## Sprint 1A-ζ Track C M11 spike (sandbox only / 非 nightly cron)

> 2026-05-22 PA reconcile §3:此 3 條 entry 對應 `helper_scripts/replay/m11_spike/` IMPL reality;CLAUDE.md §七「新腳本必須更新 SCRIPT_INDEX.md」合規 closure。

| 腳本 | 用途 |
|------|------|
| `replay/m11_spike/spike_trigger.py` | Sprint 1A-ζ Track C 手動 1 次 trigger M11 replay (skeleton, 非 nightly cron)。scope 限 1 strategy × 1 symbol × 1 day, 接 `trading_ai_sandbox` PG 寫 V107 row (engine_mode='replay')。round 2 後正式 import sibling detector + 落地 baseline_5d_mean / sigma / noise_floor_threshold；default `--user sandbox_admin` (per Phase 0 §2.2;Phase 2 defer 時 fallback `--user trading_admin`)。**sandbox only**;production DB 物理拒絕 (pg_database 不含 'sandbox' substring → sys.exit(2))。 |
| `replay/m11_spike/divergence_d1_fill_chain.py` | D1 fill_chain divergence detector module (per M11 design spec §4.2 D1)。提供 `compute_5d_baseline` / `detect_with_baseline` / `leak_free_shift1_replay` / `inject_synthetic_fixture` 4 函數；caller = `spike_trigger.py`。落實 AC-7 leak-free shift(1) mandate (per feedback_indicator_lookahead_bias)。D1 only;D2-D7 不在 spike scope。 |
| `replay/m11_spike/dedup_contract_test.py` | AC-6 M11 → M7 dedup contract empirical verify。5+1 condition (round 2 LOW-1 拆 c1a/c1b + HIGH-1 新增 c5)：V107 row 存在 + flag=m7_decay_candidate + decay_signals 0 row + strategy_lifecycle 0 row + 6 forbidden column 0 hit + Guard A forbidden column reverse fire empirical。Cleanup ADD/DROP COLUMN 自包含, sandbox state 不殘留。 |

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
| `restart_all.sh` | **輕量重啟**：停+啟 Rust 引擎 + API server（不動數據）。旗標：`--engine-only` / `--api-only` 限定範圍；`--rebuild` 先重建 openclaw-engine binary 再啟動（PYO3-ELIMINATE-1 Phase 3 後無 PyO3 wheel）；`--require-clean-build-window`（2026-05-25 Hygiene Option E Phase 1 Step 2）重啟前 fail-closed 檢查系統是否仍有 `cargo build`/`cargo test` 在跑,防 multi-session race 覆蓋 release binary inode;一般 operator 不直接帶,由 `build_then_restart_atomic.sh` 串接時自動帶入。**OPS-2 SECRET-SPLIT 2026-05-27 Phase 1**：`prepare_runtime_secret_files` 自動 seed `live_auth_signing_key.txt` 自 `ipc_secret.txt`（`[ ! -f ]` 條件嚴，已 rotate 之 key 不被覆蓋）+ engine/API spawn 注入 `OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE`；Rust + Python `_read_live_auth_signing_key` 提供 Phase 1 fallback，rate-limit WARN ≤1/h。 |
| `build_then_restart_atomic.sh` | **2026-05-25 Hygiene Option E Phase 1 Step 2**（per PA sub-agent a6326f17 hygiene 修法 Option B + memory `project_multi_session_memory_race`）：原子化 build → SHA snapshot → restart → verify deploy 鏈。flock(`$OPENCLAW_DATA_DIR/build_window.lock`) 持有 build window 期間禁第二 cargo;結束 verify `/proc/$PID/exe` SHA == on-disk binary SHA;任何 phase 失敗即 abort,杜絕「`cargo test --release` incremental rebuild 在 engine startup 後覆蓋 inode」的 multi-session race。Mac 無 procfs 則 fallback 驗 disk SHA 不被偷換。預期 operator 下次 deploy 跑 `bash helper_scripts/build_then_restart_atomic.sh` 一鍵完成。 |
| `stop_all.sh` | **優雅停止**：停引擎 + 建立 `engine_maintenance.flag`，讓 `engine_watchdog.py` 不自動重啟。`--engine-only` / `--api-only`。移除 flag: `rm /tmp/openclaw/engine_maintenance.flag` 或跑 `restart_all.sh`。 |
| `clean_restart.sh` | **交易所層重啟**：停引擎 → httpx BybitClient flatten demo/live 倉位 → 歸檔 runtime 文件（**不動 paper_state，不動 DB**）→ 檢查 binary 新舊 → 重建/重啟 → watchdog 驗證。輕度重置，保留歷史累計。旗標：`--yes` / `--mark-damaged`（歸檔 DB 交易表）/ `--include-live` / `--skip-flatten` / `--skip-build-check` |
| `fresh_start.sh` | **完整 DB 重置重啟**（2026-04-15 新增）：在 clean_restart 基礎上額外清空所有 PnL / 手續費 / 勝率 / 經驗數據（透過 `fresh_start_reset.py`）讓引擎從零歷史冷啟動。**保留**：市場數據（klines/funding/OI/LSR/liquidations/regime/news）、model_registry、linucb_state_archive、features.versions、ai_budget_config。**摧毀**：fills/intents/orders/outcomes/signals/agent 活動/學習狀態。旗標：`--yes` / `--include-live` / `--skip-flatten` / `--skip-build-check` |
| `lib/api_bind_host.sh` | Trading API bind host resolver：默認 auto 綁定 Tailscale IPv4（可用時）或 loopback；拒絕 `0.0.0.0` / `::`，供 restart/clean/fresh lifecycle scripts 共用。 |
| `start_paper_trading.sh` | Archive/diagnostic Paper runtime hook；不得接 systemd / cron 常規自動啟動或 promotion evidence |
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
| `cron/incident_sentinel_cron.sh` | L2 P2p 哨兵 5min wrapper（lock + heartbeat + fail-soft）；詳見「2026-06-10 L2 Mesh P2p incident sentinel」節 |
| `cron/install_incident_sentinel_cron.sh` | 哨兵 cron idempotent installer（Linux only / dry-run 預設 / `OPENCLAW_SENTINEL_CRON_APPLY=1` / `--remove`） |
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
| `canary/incident_sentinel.py` | L2 P2p 6 軸本地哨兵（alert-only never remediate）；詳見「2026-06-10 L2 Mesh P2p incident sentinel」節 |
| `canary/test_incident_sentinel.py` | incident_sentinel 單元測試（隔離鐵則：0 真 DSN / 0 真外發 / 全 tmp_path） |
| `canary/replay_runner.py` | 灰度回放：讀取 canary JSONL 並與 Python 基線比對 |
| `canary/canary_comparator.py` | Canary 記錄比對器：逐 tick 驗證 Rust vs Python 指標/信號/PnL |
| `canary/canary_schema.py` | Canary JSONL schema 定義（Pydantic model） |
| `canary/rollback_drill.sh` | 回滾演練腳本 |
| `canary/test_canary.py` | Canary 系統單元測試 |
| `canary/replay_earn_preflight.py` | Stage 0R Earn variant preflight harness (Sprint 1B Wave C) — first stake 前 5 sanity check (APY drift / 5-gate reject path / first stake LAL 0 / fail-closed exit code / ATR cap+drawdown);拉 Bybit V5 /v5/earn/apr-history public GET + 7d cumulative accrual day-by-day + mock 5 gate fail injection + 3 階 reconciliation cascade;產 `earn_first_stake_stage0r_<date>.json` verdict;CLI `--coin USDT --amount-usd 100 --days 7`;exit 1 任 1 FAIL。對齊 spec `docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md` §3。 |
| `canary/test_replay_earn_preflight.py` | Stage 0R Earn preflight harness 14 unit test:5 sanity check (含 PASS/FAIL/VACUOUS_PASS/DEFERRED 各 case) + 5 gate fail injection grid + 3 階 cascade + JSON schema 對齊 spec §4 AC-5。Mac unittest 14/14 PASS。 |
| `canary/healthchecks/_common.py` | Phase 1b close-maker-first healthcheck 共享層（PG conn + Wilson 95% CI + JSON formatter + CLI argparse），對齊 AMD-2026-05-15-02 v0.6 §4.1 + spec §8.1。 |
| `canary/healthchecks/62_close_maker_fill_rate.py` | `[62]` close_maker_fill_rate Wilson-CI gate（spec §8.1 Consensus-MF-2）：7d demo+live_demo maker fill rate + Wilson 95% CI，PASS lower≥0.60 / FAIL upper<0.40 / WARN 中段。CLI standalone for QA T+24h post-deploy verification。 |
| `canary/healthchecks/63_close_maker_fallback_audit.py` | `[63]` close_maker_fallback_audit（spec §8.1 Consensus-MF-3）：enum allowlist 完整性 + NULL ladder ratio (PASS ≤0.1% / WARN ≤1% / FAIL >1%)；safety path 三 enum 排除於 NULL ladder 之外。 |
| `canary/healthchecks/64_close_maker_rate_limit_pause_duration.py` | `[64]` rate-limit backoff scope（AMD §5.4 BB-MF-2 + spec §8.1 BB-SF-1）：per-symbol exp backoff + global pause sample/day ladder (5/30)；details.rate_limit_scope 完整性子檢查。 |
| `canary/healthchecks/65_reject_sample_healthcheck.py` | `[65]` PostOnly + MaxPending reject sample coverage（spec §8.3 BB-MF-5 / AC-15）：防 demo silent degradation，per env 7d 兩 category 各須 ≥1 樣本，否則 Phase 2b 無法 promote。 |
| `canary/healthchecks/80_liquidation_pulse_freshness.py` | `[80]` W-AUDIT-8a C1-LIQ-WRITER acceptance #3：market.liquidations 4-維健康度（topic freshness / row volume per-hour / cohort 25-sym coverage / parse guard side+finite），24h default window。CLI standalone for QA post-deploy verification。Linux empirical 2026-05-18 24h baseline 6134 row / 25/25 cohort / latest_age 15s = PASS。2026-05-25 由 [67] rename 為 [80] 避 passive_wait_healthcheck `[67] feature_baseline_readiness` 衝突（per operator directive）。 |
| `canary/healthchecks/tests/` | pytest 單元測試集（60 tests / 6 files）— Wilson CI 數值對 reference 表 / verdict ladder / SQL filter / multi-cell severity / liquidation pulse 4-維 freshness。Linux + Mac 同跑 60/60 PASS。 |

## phase4/ — Phase 4 學習/晉升工具 (Learning & Promotion)

| 腳本 | 用途 |
|------|------|
| `phase4/dl3_go_no_go.py` | DL-3 Go/No-Go 決策檢查 |
| `phase4/weekly_report.py` | 每週學習/交易績效報告 |

## maintenance_scripts/ — 維護腳本 (Maintenance)

| 腳本 | 用途 |
|------|------|
| `maintenance_scripts/prune_dated_files.sh` | 清理過期的 dated 輸出文件 |
| `maintenance_scripts/regen_doc_inventory.py` | 重生 docs/_indexes/ 內 doc cleanup dry-run JSON（schema v2，含 supersedes_candidate 偵測；TW doc cleanup SOP 用） |

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
