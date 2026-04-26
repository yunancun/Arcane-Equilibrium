# RFC — EDGE-P1b 7 維閾值 bind contract

**日期**：2026-04-26 CEST
**作者**：PA (Project Architect)
**範圍**：EDGE-P1b（Wave 3）`exit_features` 累積 ≥1w + 7 維閾值 bind 設計合約
**狀態**：DRAFT，待 PM + QC + MIT review → 第三波 E1 派發前定稿

---

## § 1. 7 維清單 confirm（per `V999__exit_features.sql:33-41`）

| # | 欄位 | SQL 型別 | 語意 | 來源 |
|---|------|---------|------|------|
| 1 | `est_net_bps` | `real` | 估計 net edge（bps）— JS edge + cost_gate 推算 | `edge_estimates.json::shrunk_bps` 經 cost 推算 |
| 2 | `peak_pnl_pct` | `real` | 自開倉以來 max favorable pnl % | `PaperPosition.max_favorable_pnl_pct` |
| 3 | `atr_pct` | `real` | 當時 ATR / price | `kline_manager + indicators::atr(14)` |
| 4 | `giveback_atr_norm` | `real` | (peak - current) / ATR，歸一化回吐幅度 | `exit_features::builder` 計算 |
| 5 | `time_since_peak_ms` | `bigint` | 自 peak 達到以來的毫秒數 | builder 計算 |
| 6 | `price_roc_short` | `real` | 短窗（默認 300ms）price rate-of-change | tick buffer |
| 7 | `entry_age_secs` | `real` | 自 entry 以來的秒數 | now - entry_ts |

**核實結論**：MIT 列表正確，無需修正。所有 7 維均為 `nullable real/bigint`（forward compatibility），代表 bind 後 schema 無需 migration（向後兼容）。

**重要區分**（FA report §gap-1 + MIT §2 共識）：本 RFC 的「閾值 bind」**不是** P1-14 cost_gate 的 JS estimator → cost_gate（後者依 `grand_mean > -50` + ≥2 策略 shrunk_bps>0），而是 **Track P 物理層 ExitConfig 的 7 維閾值**（peak/giveback/ATR/time/ROC/age 觸發點）寫回 `RiskConfig.exit.*`。

---

## § 2. Bind contract 設計

### § 2.1 bind 目標欄位（推薦 ExitConfig 直接擴 7 個 percentile 字段）

當前 `ExitConfig` (in `rust/openclaw_engine/src/exit_features/v2.rs:66`) 已有 8 字段：
```
min_net_floor_bps / min_hold_secs / min_peak_atr_norm / stale_peak_ms /
giveback_base / giveback_slope / giveback_floor / missing_edge_fallback_bps / shadow_enabled
```

這 8 字段全已是 IPC `patch_risk_config` deep-merge 路徑可寫（per `ipc_server/tests/config.rs:535+` 的 `test_g3_05_patch_exit_shadow_enabled_via_patch_risk_config` 證明）。**bind 路徑沿用不開新 method**。

bind 後**不擴 ExitConfig schema**，而是**修改現有 5 字段**的數值（從工程常數改為 percentile-derived）：
| ExitConfig 字段 | 改成 7 維 percentile-derived | 來源維度 |
|---|---|---|
| `min_net_floor_bps` | profit cohort 的 `est_net_bps` p10 | dim 1 |
| `min_peak_atr_norm` | profit cohort 的 `peak_pnl_pct/atr_pct` p25 | dim 2/3 |
| `giveback_base` | profit cohort 的 `giveback_atr_norm` p75 | dim 4 |
| `giveback_floor` | profit cohort 的 `giveback_atr_norm` p25 | dim 4 |
| `stale_peak_ms` | profit cohort 的 `time_since_peak_ms` p75 | dim 5 |
| `min_hold_secs` | profit cohort 的 `entry_age_secs` p25 | dim 7 |

`giveback_slope` 不直接 percentile，而是 `(giveback_base - giveback_floor) / max(peak_atr_norm)` 的線性外推。dim 6 (`price_roc_short`) **此 bind 不直接消費**（沒有對應 ExitConfig 字段），保留作 future ML feature input。

**設計理由**：
1. ExitConfig 8 字段已有 IPC 寫入路徑 + 熱重載 + 測試覆蓋；不開新 schema = 0 migration risk
2. bind 是純值替換，不變動 v2 4-Gate 邏輯
3. 任何後續想要的 7th-dim ROC gate 可作 v3 schema follow-up（不阻塞此 bind）

### § 2.2 bind 觸發時機 — 推薦 cron + IPC patch 組合

**選項 A**：每週 cron job（`helper_scripts/research/exit_threshold_calibrator.py` 新增），讀 `learning.exit_features` 算 percentile + 寫 IPC `patch_risk_config`。Operator manual approve 模式（cron 算結果 → 寫 staging file → operator review → operator confirm 後手動觸發 IPC）。

**選項 B**：完全自動化每週寫入 IPC patch。

**PA 推薦 A**：
- 與 §五 IPC config 「不可降低安全」相容：自動 IPC 寫風控值違反 §四 硬邊界守則（即使 ExitConfig 不算硬邊界，操作員審查值是常態）
- W3 階段尚無 closed-loop 安全驗證，自動 bind 風險高
- 每週 1 次 manual approve 工時 ~10 min/週，可承受
- Phase B 自動化視 W4-W5 穩定度再決定（升級為 Phase C 新 RFC）

### § 2.3 percentile 計算方法

**stratification**：per-strategy。grid_trading vs ma_crossover 的 7 維 distribution 形態完全不同（grid 高頻短週期 / ma 低頻長週期），pooled percentile 會被 dominant strategy 帶偏（MIT §2 立場）。

**cohort filter**：只取 `realized_net_bps > 0` rows（profit cohort）。理由：閾值 bind 目標是「保護獲利倉位的退場時機」，loss cohort 反映的是其他失敗模式不可作 reference。

**rolling window vs strict-week**：採 **rolling 14d + 7d embargo**（MIT §2 建議）—
- rolling 14d：足夠穩態樣本
- 7d embargo：避免 regime shift 污染（per `time-series-cv-protocol`）
- **不**用 ISO calendar week（會把 regime boundary 切碎）

**樣本量門檻**：per-strategy ≥200 rows（MIT 立場 P1-14 同等嚴格度），全策略合計 ≥1000 rows。當前 447 rows/週 → ~5/03 滿週但 per-strategy ≤200，建議**延至 5/10**等 per-strategy 達標（MIT §2 結論）。

### § 2.4 bind 失敗 / partial fill 處理

**情境**：某策略 cohort 不足 200 rows（如 bb_breakout disabled、funding_arb dormant）：
- **不**為該策略產 percentile（policy: insufficient sample → 跳過）
- 該策略繼續用全局 ExitConfig 預設值（或 G7-09 後遺留調整值）
- healthcheck `[14] exit_features_accumulation_rate` 加 per-strategy 切片，FAIL 時阻擋 bind

**fail-closed 默認**：calibrator 若觸發任何 anomaly（NaN / inf / extreme outlier）→ skip bind + log + 等下週

---

## § 3. 數據量需求

| 項目 | 推薦 | 理由 |
|---|---|---|
| total rows | ≥1000 | 防 noise floor，5 strategy × 200 |
| per-strategy rows | ≥200 | bootstrap CI 寬度 < target diff |
| time window | rolling 14d + 7d embargo | regime stationarity |
| profit cohort fraction | ≥30% | <30% 代表策略結構性虧損，bind 反加重 |
| ETA | ~5/10（per-strategy 滿） | 447/週 × ~3 週 |

**驗證 hook**：calibrator 啟動前先跑 `helper_scripts/research/exit_features_summary.py`（新工具）報告當前 sample distribution per strategy + cohort fraction，operator review 過再 approve。

---

## § 4. 回滾路徑

bind 後若 threshold 過緊（healthcheck [4] phys_lock_runtime fire 突降 / [3] exit_features_writer 異常）：

**Path 1 — IPC 熱重載**（10s 內生效）：
```bash
# 將 ExitConfig 5 字段恢復為「pre-bind 默認值」備份
ssh trade-core 'curl -X POST http://localhost:8002/api/v1/ipc/exit_config/restore_defaults'
```
新增 IPC method `restore_exit_config_defaults`（純讀備份檔 → patch_risk_config）。

**Path 2 — TOML edit + IPC reload**（30s 內）：
```bash
# 改 settings/risk_control_rules/risk_config_demo.toml 的 [exit] 段
ssh trade-core 'curl -X POST http://localhost:8002/api/v1/ipc/reload_risk_config?engine=demo'
```

**Path 3 — engine restart**（90-180s）：only if Path 1+2 fail（極端 schema 不一致），不需 rebuild。

**回滾 trigger**：
- healthcheck [4] phys_lock_runtime FAIL（24h fire 突降 ≥80%）
- healthcheck [10] intents_writer_ratio 異常波動
- operator manual judgement

備份策略：calibrator 寫入 IPC 之前先 dump 當前 ExitConfig snapshot 至 `settings/exit_config_backup/<timestamp>.toml`，回滾時 read。

---

## § 5. E1 子任務拆分（推薦 ≤4 並行）

| 子任務 | 範圍 | 工時 | 依賴 | E1 instance |
|---|---|---|---|---|
| **P1b-T1** | calibrator script `helper_scripts/research/exit_threshold_calibrator.py`（含 percentile 計算 + per-strategy stratification + cohort filter + dry-run 模式） | 1.5d | 無 | E1-Alpha |
| **P1b-T2** | summary tool `helper_scripts/research/exit_features_summary.py`（per-strategy distribution + cohort fraction + sample sufficiency check） | 0.5d | 無（可與 T1 並行） | E1-Beta |
| **P1b-T3** | IPC method `restore_exit_config_defaults` + backup 寫入路徑（calibrator 寫前先 dump snapshot） | 1d | T1 接口定 | E1-Alpha（與 T1 同實例，T1 完後做） |
| **P1b-T4** | healthcheck [14] 升級 per-strategy 切片 + cohort fraction 監控 | 0.5d | 無 | E1-Beta（與 T2 同實例） |

**檔案 isolation 評估**：
- T1: `helper_scripts/research/exit_threshold_calibrator.py`（新檔）
- T2: `helper_scripts/research/exit_features_summary.py`（新檔）
- T3: `rust/openclaw_engine/src/ipc_server/handlers/risk.rs`（既有檔，但 T3 加 method，不衝突 §三 已知改動）
- T4: `helper_scripts/db/passive_wait_healthcheck.py`（既有檔，line 1511-1524 區段擴展）

**衝突風險**：
- T1+T3 同 E1-Alpha 串接 → 0
- T2+T4 同 E1-Beta 串接 → 0
- T3 動 Rust IPC handler；隔壁 session 可能撞 G3-* IPC 工作 → 派發前 PM `git fetch` + 查遠端 branch（per memory `feedback_fetch_before_dispatch`）

**強制鏈**：T1+T2 → E2 review（重點：percentile 計算正確性 + cohort filter 不污染） → E4 regression → MIT review（per-strategy stratification 是否壓制 dominant 策略） → PM Sign-off

---

## § 6. isolation 評估

**動態 isolation per PM.md §35-39**：
- 並行 ≤2 E1 instance（Alpha + Beta），各操作不重疊新檔 → **NOT** isolation
- T3 動既有 Rust 檔，但無與 G3 / G7 series 已知撞檔 → **NOT** isolation
- 純讀派發（calibrator 是 read-only research tool，dry-run 預設）→ **NOT** destructive
- 主樹進行即可

**worktree 不需要**。

---

## § 7. 與其他 Wave 3 工作項依賴

| 依賴項 | 影響 | 緩解 |
|---|---|---|
| EDGE-P3 解鎖（[11] 連 3d PASS） | EDGE-P1b 不依賴 P3，可並行 | 無 |
| EDGE-P2-flip（shadow→live）| 完全獨立模組（Track P vs Combine Layer）| 無 |
| G2-01 PostOnly fee verdict | maker fee 影響 `est_net_bps` 計算 → calibrator 需用 G7-09 後 fee mode | passive 等 ~5/07 + G7-09 fee fix 已 live |
| P1-14 (cost_gate JS bind) | 完全 separate bind 路徑（同名混淆） | 文檔註明區分（已在本 RFC §1 說明）|

**P1b 啟動順序**：等 ~5/07 G7-09 fee 穩定 + ~5/10 per-strategy ≥200 rows，再啟 calibrator。**派發 RFC 不待**這些 trigger（先有 spec，後 trigger 達就執行）。

---

## § 8. E2 重點審查 3 點

1. **percentile 計算公式無 lookahead bias**：rolling 14d window 必須對 `ts < (now - embargo)` 過濾，calibrator dry-run mode 必須產 leak-free 證明（embargo cutoff timestamp + 對應 cohort row count）
2. **per-strategy stratification 不洩漏**：strategy_name filter 必為精確比對（grid_trading ≠ grid_*），避免 ml_training 階段 prefix 撞名
3. **fail-closed default**：任何 NaN / inf / 0-row strategy → 跳過 bind 不寫 IPC，**不可** fallback 到舊 pooled percentile（會破壞 stratification 不變量）

---

## § 9. 治理對照

- **DOC-01 §5.7 學習 ≠ 改寫 Live**：calibrator 屬 learning plane（read learning.exit_features），bind 寫 RiskConfig 屬 live plane edge，**符合**「跨 plane 寫入需 operator approve」（§ 2.2 選項 A）
- **DOC-08 §12 安全不變量 #4 風控降級**：bind 不會降低風控，只調 percentile-derived 值；invariant 保持
- **CLAUDE.md §四 硬邊界**：ExitConfig 不在 5 項 live 門控 list；bind 不觸碰
- **memory `feedback_risk_changes_scoped`**：calibrator 只寫 5 ExitConfig 字段，不連帶改其他 RiskConfig 段；遵守

---

## § 10. 不確定 / 未決問題

1. **profit cohort 比例 < 30% 時要否強制阻擋 bind**：當前 grid + ma R:R 結構問題 → cohort 可能 < 30%（QC 報告 §Q2 警示），W3 此值需 operator 拍板
2. **giveback_slope 線性外推 vs 二次擬合**：當前 v2 採線性 `base - slope × peak_atr_norm`；calibrator 可能發現非線性更貼分布，PA 推薦先保線性 + 觀察殘差，FUP 再升級
3. **per-strategy bind 結果是否覆蓋全局 ExitConfig**：當前 ExitConfig 是全局單一 struct（無 per-strategy 段）。Phase 1 bind 寫**全局聚合 percentile**（worst-case per strategy），per-strategy ExitConfig 留 v3（需 RiskConfig schema 擴展）

---

**PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--edge_p1b_7dim_bind_rfc.md`**
