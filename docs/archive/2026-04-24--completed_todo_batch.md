# 2026-04-24 批次歸檔 — P0-13 / P0-14 / P0-15 結案

本檔歸檔 2026-04-22 23:35 CEST 同次 `--rebuild` 部署的三項 P0（原 `TODO.md` §P0 — 阻塞 Live Gate 關鍵路徑），於 2026-04-23 24h+ runtime 驗收通過後全結。為避免 TODO.md 主文件膨脹，從 §P0 移出至本檔；TODO.md 主文件保留單行歸檔索引。

**三項同部署硬約束**（原始設計記錄）：P0-13 單修 → Gate 1 仍擋 99% 失觀測性；P0-14 單修 → Gate 4a mass close 災難；**必須同 commit 同 rebuild 一次部署**。實際 2026-04-22 commits `ff694e8`（P0-13）+ `2484263`（P0-14 A）+ `9710ff9`（P0-14 B）三連同 `restart_all.sh --rebuild` 部署。

---

## 1. ✅ P0-13 · ATR-SCALE-BUG-1 — **已部署 2026-04-22 23:35 CEST**（`ff694e8`）

**Runtime 狀態**：engine PID 213144 跑新 binary，三 consumer atr_pct 來源從 per-tick `compute_atr_pct` 切為 kline 1m OHLCV + `indicators::atr(14)`。Cold-start 15 min 內 `atr_pct = None`（不到 15 bars）下游保守 Hold。

**2026-04-23 24h+ 驗收（deploy 後 ~24h）** ✅ —
- `learning.exit_features.atr_pct` demo 24h avg **0.24338**（n=66，預期 0.05-0.5 ✅；pre-fix 0.003，~81× 放大回真實量級）
- `giveback_atr_norm` demo 24h avg **1.108**（預期 0.3-3.0 ✅；pre-fix DB avg 364.85，~329× 縮小回真實量級）
- Priority 6 `risk_close:phys_lock_gate4_giveback` demo 24h=**21 fires**（pre-fix 7d=0；healthcheck [4] FAIL → PASS）
- 所有三 consumer（`compute_dynamic_stop_pct` / `build_exit_features_for_tick` / `build_exit_feature_row`）atr 源已切換；`exit_features/v2.rs` Gate 3 `peak/atr >= 0.5` 重新具備判別力

**Fix 範圍**：
- `tick_pipeline/on_tick/step_6_risk_checks.rs:93-116`
- `tick_pipeline/pipeline_helpers.rs:277-294`（close-time `build_exit_feature_row`）
- `openclaw_core/src/risk/price_tracker.rs::compute_atr_pct` 加 `#[deprecated]`（保留給 fast_track）

### 🟡 原 P0-13 details（執行前 reference，保留供稽核）

- **現象**：`learning.exit_features` 實測 `atr_pct` 0.001-0.006 量級（per-tick percent-as-number），但三 consumer 假設「持倉期 ATR」(~1-2%) → `giveback_atr_norm` 放大 100-1000x（DB avg 364.85）
- **跨 consumer 影響**：
  - `compute_dynamic_stop_pct`：atr 小 100x 永遠 fallback base（**DYNAMIC STOP 7d 1 次**）
  - `build_exit_features_for_tick` / `build_exit_feature_row`：giveback 放大 100-1000x
  - `exit_features/v2.rs` Gate 3 `peak / atr >= 0.5`：永遠過，功能失效
- **QC 推薦 Option F**（score **0.91** vs A=0.72 / B=0.54 / C=0.43；詳 [`docs/worklogs/2026-04-22--p0_13_atr_scale_qc_research.md`](../worklogs/2026-04-22--p0_13_atr_scale_qc_research.md)）：
  - **reuse 既有 `openclaw_core::indicators::volatility::atr()`**（[`volatility.rs:75`](../../rust/openclaw_core/src/indicators/volatility.rs) production-quality Wilder 實作 + Kahan-summed + 既有 `test_atr_basic/edge` 單測）
  - **reuse 既有 `KlineManager`**（[`klines.rs:437`](../../rust/openclaw_core/src/klines.rs)）— 每 tick 已聚合 1m/5m/15m/1h/4h OHLCV，已在 `tick_pipeline/on_tick/step_1_2_klines_indicators.rs:37` 接線 runtime
  - 三 consumer `atr_pct` 來源同步切 `kline_manager.get_ohlcv(sym, "1m", 20).and_then(|o| atr(&o.high, &o.low, &o.close, 14)).map(|r| r.atr_percent)`
  - 舊 `compute_atr_pct` 加 `#[deprecated]` warning 保留給 `fast_track` 閃崩偵測（per-tick micro-volatility 語義合理）
  - **零 schema 變更、零重造輪子、與 counterfactual replay spec `ExitConfig` seed 完全相容**（`min_peak_atr_norm=0.5 / giveback_base=1.0 / slope=0.15 / floor=0.3` 保留原 interpretation）
- **Execution plan**（E1 實作 ~4-6h；E2 審查 ~2h；E4 測試 ~1h；deploy +24h 監控）：3 個 commits 同 `restart_all.sh --rebuild` 一次 deploy — Commit #1 P0-13 Option F atr source / Commit #2 P0-14 Option A Rust Gate 1 `missing_edge_fallback_bps` / Commit #3 P0-14 Option B Python JS proxy cells
- **必同 P0-14 deploy**（硬約束）：單修 P0-14 → Gate 4a mass close 災難；單修 P0-13 → Gate 1 仍擋 99%，失觀測性
- 觸發：2026-04-22 被動等待 audit，詳 `docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md` §3.0 + QC research `docs/worklogs/2026-04-22--p0_13_atr_scale_qc_research.md`

---

## 2. ✅ P0-14 · EDGE-ESTIMATES-MISS-1 — **已部署 2026-04-22 23:35 CEST**（`2484263` A + `9710ff9` B）

**Runtime 狀態**：
- **Option A（Rust Gate 1 fallback）**：`ExitConfig.missing_edge_fallback_bps = -10.0`（default 保守，仍 Hold；operator 可熱重載調高）
- **Option B（Python JS proxy cells）立即生效**：`edge_estimates.json` 從 43 cells（僅 grid + ma）→ **135 cells**（+4 sync-label strategies × 23 symbols = 92 proxy cells）· prefixes 全齊 `bybit_sync:23 / dust_frozen:23 / orphan_adopted:23 / orphan_frozen:23 / grid_trading:22 / ma_crossover:21`

**Fix 範圍**：
- Rust：`exit_features/v2.rs`（+99 / -6，2 new tests `test_v2_gate1_missing_edge_*`）
- Python：`program_code/ml_training/james_stein_estimator.py`（+113 / -2）+ `tests/test_james_stein_proxy_cells.py`（new 213 lines，9 tests）

**結果**：healthcheck [7] 從 WARN → PASS（135/135 populated cells，4 sync-label prefix 全出現）；runtime Priority 6 Gate 1 對 sync-label positions（P1-6 的 6 個 bybit_sync 倉位）首次可查到 edge_estimates cell（`shrunk_bps = grand_mean_bps` 弱先驗）。

**2026-04-23 24h+ 驗收（deploy 後 ~24h）** ✅ —
- `phys_lock_gate4_giveback` demo 24h=**21 fires**（pre-fix 7d=0，healthcheck [4] FAIL → PASS；Priority 6 鏈完整 live）
- `edge_estimates.json` populated **162/162 cells**（100%；prefixes bybit_sync:28 / dust_frozen:28 / grid_trading:27 / ma_crossover:23 / orphan_adopted:28 / orphan_frozen:28；mtime age 5m，scheduler 活躍）
- 備註：`learning.exit_features.est_net_bps` 24h 仍 100% NULL（66/66）— 屬 write-side gap（寫入時未讀 edge_estimates 快照），與 Gate 1 fallback 決策流獨立；21 筆 phys_lock 證明 `missing_edge_fallback_bps = -10.0` fallback path 工作中。**est_net_bps 落地需另案跟進**（非 P0）

### 🟡 原 P0-14 details（執行前 reference，保留供稽核）

- **現象**：`learning.exit_features` 7d 110 rows 中 109 個 `est_net_bps IS NULL`（99.1% miss）；healthcheck 觀察 `edge_estimates.json` populated cells 0/0（可能 JSON cells key mismatch 或實質空 list）
- **影響**：TRACK-P v2 Priority 6 Gate 1（`edge <= floor=5.0 → Hold`）對 `None` 一律 Hold → **v2 swap + T4 wiring 全鏈在 runtime 等效 dead code**
- **7d 0 `phys_lock_*` fire** 是此 bug 的直接後果（healthcheck FAIL [4]）
- **潛在根因假設**：
  1. `edge_estimates.json` 的 cells key 與 `edge_estimates.get_cell(strategy, symbol)` 查詢 key 不匹配
  2. JSON 用 `engine_mode:strategy:symbol` 三段式，T4 closure 只傳 2 段
  3. Scheduler 實際寫入 cells 遠少於預期（P1-19 症狀再現 — label 不足 → cells 少）
- **Fix path**：先 RCA 假設 1/2/3 → 若是 key mismatch 改 T4 closure 1-2 行；若是資料不足則 fallback Gate 1「edge=None → 保守但不 block」（加 config flag `gate_1_allow_null_edge=true`）
- **預估**：0.5-2d 視假設命中
- **必須**與 P0-13 一起部署
- 觸發：2026-04-22 被動等待 audit，詳 `docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md` §3.2

---

## 3. ✅ P0-15 · COST-EDGE-DEPRECATION-MICRO-PROFIT-GAP-1 — **結案 2026-04-23**（doc fix commit `2330360`；§3 併入 P0-3）

**結案摘要**：文檔敘事脫節已修正（§1-§2）；§3 edge baseline 重跑自然併入 P0-3 執行（P0-13/14 已 2026-04-23 24h+ 驗收通過，剩 PostOnly 1w 觀察窗 ~5d 到期，約 2026-04-28）

- **現象**：
  - `risk_checks.rs:250-264` 舊 COST EDGE gate 在 Track P T3 commit 被註解 deprecated；P0-3 原定依靠的「MICRO-PROFIT-FIX-1 narrow-band gate」其實是同一個 gate 的 runtime
  - 實證：demo `risk_close:COST EDGE%` 24h=0、7d=35（全集中在 2026-04-18/19 T3 rebuild **之前**）
  - 2026-04-19 T3 rebuild → 2026-04-21 晚 T4 接線 + `--rebuild` 期間 **2.5 天 0 退場層 fire**（除 trailing 5 / dynamic 1）
  - TODO/memory 裡「2026-04-20 demo 24 筆 MICRO-PROFIT close 100% 勝率 +$4.68」敘述為 cached window 誤判，實際 2026-04-20 後 0 fire
- **影響**：
  - P0-3 Phase 5 edge 重評的「MICRO-PROFIT 是當前最重要正 edge 安全網」論斷**基礎錯誤**
  - P1-10 STRATEGY-ASYMMETRY-1 「2026-04-20 R1 驗收」結論需 redo（當時退場分布查詢 stale cache）
  - CLAUDE.md §三 / TODO P1-10 推理鏈 / worklog narrative 需同步更正
- **Fix scope**（文檔 only，不動代碼）：
  1. 更正 TODO P1-10 §推理鏈 §1-§4 的 MICRO-PROFIT 敘述
  2. 更正 CLAUDE.md §三 「MICRO-PROFIT-FIX-1 正常運作」論斷
  3. 重跑 P0-3 Phase 5 edge baseline（待 P0-13/P0-14 修好 + PostOnly 1w 觀察期後）
- **預估**：~2h 文檔更正；edge baseline 重跑延後
- 觸發：2026-04-22 被動等待 audit，詳 `docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md` §3.3 + §3.4
- ✅ **2026-04-23 文檔更正完成**（commit `2330360` landed）— TODO.md P1-10 §推理鏈 R1 驗收表 + 關鍵判讀 bullets + P1-19 H3 RCA 連帶更正；CLAUDE.md §三 無 active MICRO-PROFIT claim（operator 已手動精簡吸收）；Fix scope §1-§2 達成，§3 edge baseline 重跑自然併入 P0-3（P0-13/14 2026-04-23 24h+ 驗收 PASS；PostOnly 1w 窗口 2026-04-21 起算，預計 ~2026-04-28 解鎖）

---

## 後續追蹤項（非 P0，另案）

1. **`learning.exit_features.est_net_bps` 100% NULL write-side gap** — P0-14 驗收揭露：24h 66/66 rows `est_net_bps IS NULL`。寫入時機未從 `edge_estimates.json` 讀快照注入。Gate 1 fallback pathway 已獨立工作（21 phys_lock fires 證明），但 `est_net_bps` 缺值讓 downstream ML / 觀測分析失參考。非 P0，待獨立 RCA（fix path 可能在 `pipeline_helpers.rs::build_exit_feature_row` 或 Rust side `edge_estimator::get_cell` 調用時機）
2. **P0-3 edge baseline 重跑** — P0-15 §3 併入 P0-3（Phase 5 策略 Edge 2w 重評）。觸發條件：PostOnly 1w 窗口解鎖（~2026-04-28）+ P0-13/14 24h+ 驗收已達（2026-04-23 ✅）

---

## 部署時序（參考）

| 時間 | 事件 |
|---|---|
| 2026-04-22 夜 | P0-13/14 被動等待 audit 揭 3 bug（ATR scale / edge miss / COST EDGE gate deprecation 敘事脫節） |
| 2026-04-22 23:35 CEST | `restart_all.sh --rebuild` 部署 commits `ff694e8` + `2484263` + `9710ff9`（P0-13 + P0-14 A + P0-14 B） |
| 2026-04-23 日間 | P0-15 doc fix commit `2330360` landed（TODO P1-10 推理鏈 + P1-19 H3 RCA 更正；CLAUDE.md 由 operator 手動吸收） |
| 2026-04-23 21:13 CEST | 後續 `--rebuild`（WS-RETIRE-1 + DEDUP A+B+C+D + INFRA-PREBUILD A/B；P0-13/14 runtime 承襲不變） |
| 2026-04-23 23:22 CEST | 24h+ runtime 驗收跑 `passive_wait_healthcheck.sh` + DB query — 三項指標全綠（atr_pct 0.24 / giveback 1.1 / phys_lock 21/24h） |
| 2026-04-24 | 結案歸檔（本檔） |

---

**相關**：
- 健康檢查基礎設施：`PASSIVE-WAIT-HEALTHCHECK-1` commit `edc4a21`（2026-04-22）+ CLAUDE.md §七 新規則 commit `b0b47b5`（2026-04-23）
- Counterfactual replay 驅動：`helper_scripts/db/counterfactual_exit_replay.py`（EDGE-DIAG-1 #3，2026-04-23）
- 24h+ 驗收 commit：`6d72dfe`（2026-04-23，本歸檔前置）
