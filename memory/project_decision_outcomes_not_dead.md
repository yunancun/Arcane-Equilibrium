---
name: decision_outcomes 不是 dead，但有 2 個 bug (2026-04-21 Linux 驗證後更正)
description: trading.decision_outcomes writer 活躍，但 (1) outcome_* 100% NULL 是 JOIN/horizon-window 斷鏈非 klines 稀疏 (2) engine_mode 100% 'paper' tagging 寫入邏輯故障；不可刪（LinUCB 依賴），升級 P1 fix
type: project
originSessionId: aaf4cf28-cfa5-48d0-9847-f0c087dbeed8
---

# trading.decision_outcomes 不是 dead，但發現 2 個 bug（2026-04-21 RCA + Linux 驗證後更正）

**原 TODO `DECISION-OUTCOMES-DEAD-1` → 歷經兩次更正**：
- v1 (2026-04-21 14:00 Mac RCA)：reframed as `ATTEMPT-LOG-NOT-DEAD-1`，P2 → P3 doc-only（**結論已被 Linux 驗證部分推翻**）
- v2 (2026-04-21 15:00 Linux 驗證後)：**升級回 P1**，拆分為 2 個具體 fix TODO（見下）

詳細 RCA + Linux 驗證結果 → `docs/worklogs/2026-04-21--decision_outcomes_rca.md`

## 確認事實（雙邊一致）

- **Writer 活躍**：Rust `outcome_backfiller.rs` 5 min tick loop + `main.rs:873` spawn ✓（264,800 rows 持續增長，24h 內新 row）
- **與 `exit_features` 語意正交**（entry-anchored label vs exit-anchored trajectory），不互相取代 ✓
- **下游 LinUCB 依賴**（`linucb_trainer.py:215` + `linucb_shadow_compare.py:188`），**絕不可刪** ✓
- **2026-04-18 設計文件「dead」判斷是誤判** ✓（writer 確實活躍）

## 已被 Linux 驗證推翻或更正的假設（Mac RCA 盲點）

### 盲點 1：「NULL 根因 = klines 稀疏」**錯** ❌
- Mac RCA sub-agent 從代碼推斷：「LATERAL 子查詢若無 kline 資料 → outcome_* 全 NULL」，推論「MARKET-KLINES-STALE-1 只修 forward-going → 歷史空洞造成 NULL」
- **Linux 實測反證**：`outcome_1m / outcome_5m / outcome_horizon_minutes` **100% NULL**（不是稀疏，是全空）；抽樣符號在 `market.klines` 有資料
- **真實根因**：`outcome_backfiller` 的 JOIN / horizon-window 邏輯**斷鏈**（具體位置 TBD by Linux code audit）

### 盲點 2：engine_mode tagging bug **新發現** 🚨
- Mac RCA 未查 engine_mode 分布事實，只看 V015 DEFAULT='paper' 就推斷「V015 後 row 全 'paper' 合理」
- **Linux 實測**：100% rows engine_mode='paper'，但 **context_id 前綴展示 demo_* / live_demo_* 混雜**
- PAPER-DISABLE-1 (2026-04-16) 後 paper 預設關閉，不可能全量都是真 paper → **engine_mode 欄位寫入邏輯故障**（writer 落 'paper' 而非用 INSERT 時的 context_id 前綴判斷 engine）
- 影響：所有 **outcome-based edge 歸因失效**（EDGE-P3-1 / Phase 5 JS 估計 / LinUCB reward 切 per-engine）

## 已拆成的 P1 fix TODO

1. `DECISION-OUTCOMES-ENGINE-MODE-TAG-BUG-1` (P1) — engine_mode 100% 'paper' 不符實際；fix writer 路徑正確 tagging
2. `OUTCOME-BACKFILL-JOIN-NULL-1` (P1) — outcome_* 100% NULL，audit `outcome_backfiller.rs` JOIN/horizon-window 實作，修好後 LinUCB 才有可用 reward

## 未來遇到這個表時

1. **優先信 Linux DB 實測結果**，不要只從代碼推論 NULL 成因
2. V015 後 row engine_mode 分布應該看 context_id 前綴對齊，全 'paper' 是 bug 訊號
3. outcome_* NULL 不代表 klines 稀疏 — 先驗證 klines 有資料再判斷 JOIN 邏輯

## Mac RCA 流程反省（認知誠實）

sub-agent RCA 時從代碼推論「klines 稀疏 → NULL」，我 QC 時信了沒要求 Linux DB 實測反證。應該更嚴格：**「假設需外部資料驗證」的結論不能採納情境 3 就結案**，至少等 Linux DB SQL 回來再決定 reframe vs fix。這次 Linux CC 的 5 task 驗證 + `bt_non_null ≈ total` + `o1h_non_null ≪ total` 條件判定是對的 — 實測才發現 `o1h_non_null = 0`（全空）和 `engine_mode` tagging 矛盾。
