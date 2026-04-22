---
title: 被動等待 silent fail 系統性 audit — Track P / MICRO-PROFIT / ExitFeatures 三層失效
date: 2026-04-22
status: P0 critical — 揭露 runtime 退場層 ≥2.5 天空窗期
trigger: operator push-back「等資料積累阻礙後續施工但後面發現根本沒數據寫進去不能接受」
related: P1-19 RCA · TRACK-P-V2-SWAP-1 · EXIT-FEATURES-TABLE-1
---

# 被動等待 silent fail 系統性 audit

## 0. TL;DR

Operator 對 P1-19 結案（「backfill 等 22 天才能過 200 labels」）提出系統性反饋 — 發起對**所有被動等待 pipeline 的批量驗收**。查出 **3 個新的 P0 silent failure** + 1 個文檔與現實脫節。runtime 退場層有 **2.5 天空窗期**（2026-04-19 晚 ~ 2026-04-22 晚）。

**3 個 runtime silent failure**（嚴重度：critical）：

1. **`builder.rs:110` giveback_atr_norm unit scaling bug**：`(peak%) / (atr小數)` → 放大 100x（DB avg 364.85 vs 正確 ~3.0）
2. **`learning.exit_features.est_net_bps` 99% NULL**：T4 closure 的 `edge_estimates.get_cell` 99.1% miss（109/110 rows）→ Gate 1 永遠 Hold
3. **Priority 6 退場層在 T3 rebuild 與 T4 接線之間有 ~2 天完全空窗**：2026-04-19 晚 COST EDGE 註解 + PHYS-LOCK features=None + T4 未接 → 0 退場機制 fire 除 trailing（5）/ dynamic stop（1）

**1 個文檔/現實脫節**：

4. **MICRO-PROFIT-FIX-1 narrow-band gate「正常運作」敘述錯誤**：2026-04-19 的 31 個 `risk_close:COST EDGE:*` fills 發生在 T3 rebuild **之前**（runtime 仍跑舊 COST EDGE），之後 3 天 0 fire。TODO/memory/worklog 把這個 cached 現象當作「narrow-band gate live」，誤導 2026-04-20 R1 驗收結論。

---

## 1. 觸發事件 / Trigger

Operator 2026-04-22 22:30 CEST 反饋：

> 「看看是否有什麼可以做的。這種等待數據積累阻礙後續施工但是後面發現根本沒有數據寫進去的情況是不能接受的」

P1-19 發現「BLURUSDT 47 labels 3 天 0 成長 → 按現速率需 22 天而非原估 3-5d」— operator 不只要結案這個項目，是要建立**系統性防線**防止同類「被動等待但 silent fail」發生。

## 2. 查詢範圍 / Scope

對當前**所有 runtime 被動等待 pipeline** 跑 PG `trading_ai` 查 24h + 7d 實際數據流入狀況（operator 明確授權 prod DB read）：

| Pipeline | 預期數據流 | 實測 24h rate | 狀態 |
|---|---|---:|---|
| `learning.decision_features` label backfill | P1-7 C 每日新 labels | 14 | ✅ 對齊 close_fills |
| `learning.exit_features` Rust writer | EXIT-FEATURES-TABLE-1 每 close 一 row | 14 | ✅ 對齊 close_fills |
| `trading.fills WHERE exit_reason LIKE 'risk_close:phys_lock_%'` | TRACK-P v2 runtime fire | **0** | 🔴 7d 0 fire |
| `trading.fills WHERE exit_reason LIKE 'risk_close:COST EDGE%'` | MICRO-PROFIT-FIX-1 narrow-band | **0** (vs 2026-04-19: 31) | 🔴 3 天 0 fire |
| `trading.fills WHERE exit_reason LIKE 'stop_trigger:%'` | StopManager hard/time stop | **0** (7d: 1) | ⚠️ 近 0 fire |
| `trading.fills WHERE exit_reason LIKE 'risk_close:TRAILING STOP%'` | trailing stop | 0（7d: 5 全 2026-04-19 前） | ⚠️ 停火 |
| `trading.fills WHERE exit_reason LIKE 'strategy_close:%'` | 策略自 emit Close | 14（7d: 230） | ✅ alive |

**關鍵對比**：close_fills 14 筆中 **100% 都是 `strategy_close:*`**（ma_reverse_cross / grid_close / bb_mean_revert），**0 個退場來自風險層**。

## 3. 各 silent failure 詳述

### 3.1 `giveback_atr_norm` unit scaling bug（`builder.rs:110`）🔴 P0

**Code**（`rust/openclaw_engine/src/exit_features/builder.rs:104-114`）：

```rust
let giveback_atr_norm = match atr_pct {
    Some(atr) if atr > 0.0 && atr.is_finite() => {
        let gb = f64::from(peak_pnl_pct) - current_pnl_pct;
        if gb < 0.0 {
            Some(0.0f32)
        } else {
            Some((gb / atr) as f32)   // ← BUG: gb is in %, atr is fraction
        }
    }
    _ => None,
};
```

**問題**：
- `peak_pnl_pct` = `snap.max_favorable_pnl_pct`，**單位 %**（e.g. 2.33 代表 2.33%）
- `current_pnl_pct` = `(current - entry) / entry * 100`，**單位 %**
- `atr_pct` = 傳入的 `snap.atr_pct` 或類似，**單位 fraction/decimal**（e.g. 0.0077 代表 0.77%）
- 結果：`gb(%) / atr(fraction)` 被放大 **100 倍**

**DB 實證**（`trading_ai` psql 2026-04-22 22:15 CEST）：
- 7d 110 rows avg `giveback_atr_norm = 364.85`
- 7d 110 rows avg `peak_pnl_pct = 2.33`, avg `atr_pct = 0.0077` → 正確值應約 **3.0 ATRs**，實測 **364 ATRs**（精確對應 100x 放大）

**影響**：
- Gate 3（`peak_pnl_pct / atr_pct >= min_peak_atr_norm=0.5`）— 永遠 ≥100，永遠通過，**原意過濾 shallow-peak 倉位的功能完全失效**
- Gate 4a（`gb_norm >= threshold ∈ [0.3, 1.0]`）— 一旦 Gate 1 過，giveback_atr_norm=364 >> threshold 會立刻 Lock（mass close winners 風險）

**為什麼還沒爆炸**：被 §3.2 的 est_net_bps NULL 掩蓋 — Gate 1 永遠 Hold，根本不到 Gate 4a。**若有人修了 §3.2，Gate 4a 會立刻引發 mass close 災難。**

**Fix scope**：1 行改 `peak_pnl_pct / 100.0` 或 `atr * 100.0` 統一單位 + 新增 4-5 個 regression tests。~4h。

**單測為何沒抓到**：`v2.rs` 的 31 個單測手動構造 `ExitFeatures { giveback_atr_norm: Some(0.9), ... }` 繞過 builder，`builder.rs` 的 12 個單測 assert value 範圍但用 round-number 的測試資料（peak=5%, atr=0.02→gb=2.5）剛好看不出 100x 偏差。**真實運行資料才暴露**。

### 3.2 `est_net_bps` 99% NULL（T4 closure 99.1% edge miss）🔴 P0

**Code**（`rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs`，T4 closure）：

```rust
let est_net_bps = edge_estimates_ref
    .get_cell(&snap.owner_strategy, &row.symbol)
    .map(|c| c.shrunk_bps as f32);
```

**DB 實證**：7d demo exit_features 110 rows 中只有 **1 row 有 `est_net_bps`**（with_edge=1/110 = 0.9%）

**可能原因**：
1. `edge_estimates.json` cells（104 個）僅覆蓋 P1-7 有 label 的 slice（47 個 labeled + 邊緣），多數 (strategy × symbol) combo 無 cell → `get_cell` 返回 None
2. `snap.owner_strategy` 字串與 JSON key 不匹配（e.g. "ma_crossover" vs "ma_crossover_v2" vs "trend_following"）
3. JSON key 用 `engine_mode:strategy:symbol` 三段式，T4 closure 只傳 2 段 → 永遠 miss

**影響**：
- Gate 1（`edge <= min_net_floor_bps=5.0 → Hold`）— `None → Hold`（fail-safe）
- Priority 6 永遠 Hold → 物理層 phys_lock 0 fire（符合 TRACK-P v2 swap 部署後 7d 0 `phys_lock_*` fill 的觀察）

**諷刺**：v2 swap commit `306993e`（2026-04-22）+ T4 wiring `e95c779`（2026-04-21）的完整意圖是讓 Priority 6 在 runtime 實際 fire；但 Gate 1 的 `est_net_bps NULL → Hold` 保守 fail-safe 讓整個鏈在 runtime **等效 dead code**。

**Fix scope**：
- 先確認假設 1/2/3（讀 `edge_estimator_scheduler.py` 寫 JSON 的 key 格式 + `edge_estimates.get_cell(..)` 查詢格式對照）
- 最可能 fix：path 1 — 等 P1-7 C 資料累積更多 cells（非 code fix，data 問題）
- 或 fix fallback — Gate 1 加「edge=None → 走保守但不 block」分支（`min_net_floor_bps → min_net_floor_bps_with_null`？）
- ~0.5-2d 視假設命中

### 3.3 Runtime 退場層 2026-04-19 晚 → 2026-04-21 晚 2.5 天全空窗 🔴 P0

**Timeline**：

| 時期 | Priority 6 runtime | COST EDGE fire | PHYS-LOCK fire | 退場層有效機制 |
|---|---|---:|---:|---|
| 2026-04-17 ~ 2026-04-19 T3 rebuild 前 | COST EDGE enabled | 3 (04-18) / 31 (04-19) | N/A | ✅ COST EDGE + trailing |
| **2026-04-19 T3 rebuild 後 → 2026-04-21 T4 接線 rebuild 前** | PHYS-LOCK（features=None） | **0** | **0** | 🔴 **僅 trailing 5 + dynamic stop 1 七天全部** |
| 2026-04-21 晚 ~ 2026-04-22 晚 v2 swap 前 | PHYS-LOCK v1 linear（features=real 但 edge NULL） | 0 | 0 | 🔴 仍 0 風險層退場 |
| 2026-04-22 晚 ~ 現在 | PHYS-LOCK v2 non-linear（features=real 但 edge NULL + unit bug） | 0 | 0 | 🔴 仍 0 |

**後果**：
- 2026-04-20 起 demo close_fills 14-54/day **全** 來自策略自己 emit Close（ma_reverse_cross / grid_close / bb_mean_revert），**0 個**來自風險層 winner-pick / cost gate
- 倉位 peak 達 13.9%, 22.6%, 32.3% 後 trailing 觸發（4-19 之前），之後這條 path 也停火（peak 普遍更小？）
- 沒有任何機制阻止「有微利就套現」— MICRO-PROFIT-FIX-1 intent 完全落空

**Root cause**：T3 deprecation + T4 延遲接線 + T4 接線後 est_net_bps / unit bug 疊加，讓設計上的**退場多層防線**全部失效。

**Fix**：§3.1 + §3.2 修好後，退場層回到設計意圖。~1-2d（在 §3.1 §3.2 之上）。

### 3.4 文檔與現實脫節：MICRO-PROFIT「正常運作」錯誤敘述

**TODO（截至 2026-04-22 22:00 CEST 的 P1-10 推理鏈）：**

> 「**但 MICRO-PROFIT-FIX-1 narrow-band gate（ratio ≥ 0.20 & pnl ∈ [0.30%, 0.55%]）正常運作**，close 時 strategy_name 仍寫 risk_close:COST EDGE:... 舊 label」
> 「2026-04-20 24h 實測：demo 24 筆 + paper 12 筆 MICRO-PROFIT close，**100% 勝率 / +$4.68 / +$7.49**，是當前最重要的正 edge 安全網」

**實測對帳**（`trading.fills WHERE strategy_name LIKE 'risk_close:COST EDGE%'` 按日聚合）：

| day | count |
|---|---:|
| 2026-04-18 | 3 |
| 2026-04-19 | 31 |
| 2026-04-20 | 0 ← 這裡應有 24 |
| 2026-04-21 | 0 |
| 2026-04-22 | 0 |

**結論**：TODO/memory 裡「2026-04-20 demo 24 筆 MICRO-PROFIT close」**從未發生**。最可能來源：
- 2026-04-20 R1 驗收看的是 24h 滑動窗口，該窗口當時涵蓋 2026-04-19 白天 rebuild 前的 cached 數據，誤判為「當前 runtime 正常」
- 或者 2026-04-20 R1 查詢的 SQL 對了 ts 過濾 off-by-one 天
- 或者 R1 `engine_mode` 含 `demo_archive_*`（未 gate）

**影響**：P0-3 Phase 5 edge 重評的「MICRO-PROFIT 是當前最重要正 edge 安全網」論斷**基礎錯誤**。此敘述需從 CLAUDE.md §三 + TODO P1-10 + 多個 worklog 更正為「MICRO-PROFIT-FIX-1 2026-04-20 起 silent-死，Priority 6 空窗 2.5 天」。

## 4. 被動等待定期驗收工具 / Healthcheck tool

為避免未來同類 silent fail，產出 `helper_scripts/db/passive_wait_healthcheck.py`：

- 一鍵查 7 個關鍵 pipeline 的 24h/7d rate
- 對每個 pipeline 定義「健康指紋」（e.g. `exit_features_24h == close_fills_24h ± 2`）
- 任一異常 → 非零 exit code + human-readable summary
- 建議 operator 每日手動 `python3 helper_scripts/db/passive_wait_healthcheck.py` 跑一次 **或** 每 6h cron

**入口設計**（non-blocking read-only）：
- PG 連線同 `phase1a_c_readiness.py` pattern（`POSTGRES_*` env）
- 輸出 stdout 表格 + exit code 反映健康狀態
- 不寫任何 DB / 檔案，零副作用

## 5. P0 TODOs 新開

| ID | 標題 | Scope | 依賴 |
|---|---|---|---|
| **P0-13** | EXIT-FEATURES-UNIT-BUG-1 | `builder.rs:110` giveback unit fix + 4 regression tests | 無 |
| **P0-14** | EDGE-ESTIMATES-MISS-1 | T4 closure est_net_bps 99% NULL RCA + fix path（code vs data） | 需 P0-13 先修（否則 fix 後引發 Gate 4a mass close） |
| **P0-15** | COST-EDGE-DEPRECATION-MICRO-PROFIT-GAP-1 | 文檔/現實對齊 + CLAUDE.md §三 / TODO P1-10 更正 + P0-3 Phase 5 edge 重評 baseline 重算 | 無（文檔 only） |
| **P2 NEW** | PASSIVE-WAIT-HEALTHCHECK-1 | 新 tool `passive_wait_healthcheck.py` + CLAUDE.md §六 接手三連補一步 | 無 |

## 6. CLAUDE.md § 規則提議

加入 §七（代碼與文檔規範）「**被動等待項規則**」：

> 任何 TODO 標記為「等 Nd/Nw 觀察後才能結案」的被動等待項，必須同步產出一個 healthcheck 查詢/腳本（通常是 1 條 SQL 或 1 個 Python oneliner），能單命令驗證「資料實際在流入」。缺此 check 的被動等待項不允許登記。定期 healthcheck 由 `helper_scripts/db/passive_wait_healthcheck.py` 統一跑。

## 7. 下一步 / Next

**按優先序**：

1. (今) 新增 3 個 P0 TODOs + 1 個 P2 tool TODO 到 TODO.md
2. (今) 寫 `passive_wait_healthcheck.py`（獨立 commit）
3. (今) CLAUDE.md §三 / TODO P1-10 文檔更正（§3.4 要求）— 不改代碼
4. (下次) P0-13 修 giveback unit bug（4h）
5. (下次) P0-14 RCA est_net_bps NULL（需 read `edge_estimator_scheduler.py` 寫 JSON 的 cell key 格式）
6. (下次) 新 restart/rebuild 後自動跑 healthcheck（或 24h 首次）

**不立刻做**：
- Runtime 部署 fix — unit bug fix + edge 路徑 fix **必須一起 deploy**，否則部分 fix 會把 Gate 4a 從 "under-fire" 推到 "over-fire"
- 直接動代碼 — 需完整 work chain（E1 → E2 → E4 → `--rebuild`），本 session 只做 audit/doc/tool

## 8. 經驗教訓 / Lessons（寫入 `docs/lessons.md` 候選）

- **「被動等待」必須配「主動驗收」**：任何「等 Nd」的 TODO 無定期 healthcheck 等同賭運氣
- **文檔只在 commit 當下為真**：P1-10 R1 驗收 `risk_close:COST EDGE` 31 筆 → 誤以為當前 runtime 還 fire，沒查「commit 後 runtime 是否重啟過」
- **單測無法取代真實資料**：v2.rs 單測 Some(0.9) 繞過 builder 計算，builder.rs 單測用 round-number 看不出 100x unit error — **需要 periodic DB avg vs unit test value 對比**
- **deprecation 不是「可無視」**：code 註解「DEPRECATED」但依賴它的上層（MICRO-PROFIT-FIX-1 內部統計 / TODO narrative）沒同步更新 → 文檔敘事成為活化石

— END —
