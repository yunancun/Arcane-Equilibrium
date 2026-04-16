# P0-0 RECONCILER-BURST-FIX — RCA + 修復 Spec

**日期**：2026-04-16
**狀態**：Spec 完成，實作進行中
**路徑**：`rust/openclaw_engine/src/position_reconciler/{mod.rs, escalation.rs}` + `rust/openclaw_core/src/sm/risk_gov.rs`

---

## 1. 症狀

2026-04-15 demo 引擎重啟後 46 分鐘內觀察到：

- `18:55:13.747` reconciler 首輪分類 9 drifts = **6 Ghost + 2 Orphan + 1 MinorDrift**
- Ghost + Orphan 合計 ≥5 → 觸發 `BURST_DRIFT_COUNT` threshold → `auto-escalation NORMAL→DEFENSIVE (burst)`
  - 日誌 `reason=6 simultaneous drifts (burst, streak=1)`（6 為 `actionable_count`，扣除 MinorDrift 後實際 8 → 文字 "6" 疑為早期統計口徑；門檻仍為 5）
- FAST_TRACK 在 Defensive 級別下觸發 `ReduceToHalf`（全組合半倉）+ `ft_pause_new_entries`（鎖新開倉）
- `risk_gov.rs:617` policy `// Only escalate, never auto-de-escalate` → reconciler de-escalate 有自己路徑，但**本輪不觸發**，因為 baseline 仍會繼續看到殘留 drift
- 結果：`risk_level=Reduced` log 168,205 筆 vs Defensive 1 筆；G-2 FundingArb 12.5h 窗口僅 ~46min 可開倉、3 筆 open、0 筆 strategy_exit

## 2. 根因

`ReconcilerState` **無「啟動寬限期（startup grace window）」機制**。

具體路徑：

1. 引擎重啟後 `run_position_reconciler` 啟動
2. Warmup（`mod.rs:370-389`）：拉取當下 Bybit 真相播種 baseline，**不做分類**
3. 首個正常 tick（~30s 後）：拉取 Bybit → 與 warmup baseline diff
4. **問題**：warmup baseline 是「Bybit 真相」，但 local `paper_state` 重載自 snapshot / disk，可能落後於當前 Bybit 狀態（Bybit 側 demo 有外部手動操作 / 前次引擎未 flush 的持倉變化）
5. 即 baseline vs paper_state 並未同步 → 首次 tick 分類會把「paper_state 認為有、Bybit 無」標記為 Ghost；「Bybit 有、paper_state 無」標記為 Orphan
6. 達 ≥5 即觸發 `BURST_DRIFT_COUNT` → 升級到 Defensive（首次）；若下一輪殘留 drift 仍 ≥5 → CircuitBreaker + CloseAll

## 3. 為什麼 orphan_handler 不夠

ORPHAN-ADOPT-1 Phase 1/2A 已處理 Orphan（B2 正邊際 probe → adopt；否則關倉）：

- 事故中 2 筆 Orphan **在 `process_orphans()` 中被移除**，不進 `evaluate_actions()`
- 但 6 筆 **Ghost** 未被 orphan_handler 處理（Ghost 不屬於 Orphan 分類）
- Ghost 5+ 仍觸發 burst

Ghost 的本質：本地 paper_state 認為持倉、Bybit 側已無 → local state 過時，應以 Bybit 為真相（baseline reseed 已處理）而非視為 live drift burst。

## 4. 影響範圍

| 場景 | 影響 |
|---|---|
| 每次 `restart_all.sh --rebuild` | 啟動後高機率首輪 burst → Defensive/CB + `ReduceToHalf` 全組合半倉 + `ft_pause_new_entries` 鎖新開倉 |
| 冷啟動後 clean_cycle 累積 | 需 30 clean_cycle × 30s = 15min + 牆鐘 15min → 最快 15min Cautious→Normal、20 cycle + 10min 各級往下 → 實測「46min 才恢復」與 45min+ recovery（從 Defensive 一路降級）相符 |
| FAST_TRACK | Defensive + 異常價格 → `ReduceToHalf` 可能減半既有倉位（非 drift 所有權範圍內的倉位），造成 PnL 干擾 |
| 阻塞 | P0-1（G-2 FundingArb 驗證）、P0-3（Phase 5 edge 2w 重評） |

## 5. 修復方案（採 A + 部分 B）

### 核心：STARTUP_GRACE_MS 常量 + `ReconcilerState.startup_ms` 欄位

**原理**：引擎啟動後首 N 分鐘（建議 **5 分鐘 = 300000 ms**）視為寬限期。期間：

1. **不觸發任何 auto-escalation**（不論 burst / persistent drift / single drift / REST failure）
2. **保持 orphan_handler 正常運作**（Phase 1/2A adopt 或關倉繼續）
3. **保持 V014 audit 正常記錄**（觀察性不降級）
4. **保持 baseline 更新**（每輪 `rc_state.baseline = current` 照常）
5. Grace 期內 drift_streak / burst_drift_streak / clean_cycles counter **不累加、不衰減**（避免計數累加在 grace 結束瞬間集中觸發）

寬限期設計原則：

- **5 分鐘的選擇**：reconcile interval 30s → 10 個完整週期，足夠 Bybit 外部殘留被 orphan_handler 清除或 adopt、paper_state 同步收斂；同時小於 `PER_SYMBOL_COOLDOWN_MS=30min` 與 `RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS=15min`，不破壞既有時間尺度
- **超過 5 分鐘**：若 Bybit 側仍有真實 drift，正常升級邏輯接手；此時觸發升級視為「運行期真實事件」，保留 Phase 6 自動降級響應

### 為什麼不用方案 B 單獨（orphan-only 不升級）

事故中 6 筆 burst drift **全為 Ghost**（不是 Orphan）。方案 B 只處理 Orphan burst → 本次事故不被覆蓋。

若未來新增 Ghost adoption 路徑（本地 paper_state 的 cleanup / reseed），可補 B 層作為 runtime 保險；P0-0 不納入此範圍。

### 為什麼不用方案 C（governance auto-demote）

`risk_gov.rs:617` 的 `// Only escalate, never auto-de-escalate` 是 PnL-driven 自動評估路徑的 policy，核心安全邊界。不應為 startup 情況破壞此不變式；reconciler 已有自己的 `reconciler_de_escalate_to()` 路徑負責自動恢復。

修復點放在 reconciler 側（source of escalation），不動 governance。

## 6. 實作清單

### 6.1 `rust/openclaw_engine/src/position_reconciler/escalation.rs`

1. 新增常量：
   ```rust
   /// P0-0 RECONCILER-BURST-FIX: startup grace window during which reconciler
   /// auto-escalation is suppressed. Baseline drifts observed during engine
   /// warmup (legacy Bybit orphans, stale paper_state ghosts) are cleaned
   /// by orphan_handler / baseline reseeding, not treated as live drift bursts.
   /// P0-0：啟動寬限期，期間 reconciler 自動升級被抑制。warmup 期間看到的
   /// baseline drift（legacy Bybit orphan、stale paper_state ghost）由
   /// orphan_handler / baseline 重播種處理，不視為 live drift burst。
   pub const STARTUP_GRACE_MS: u64 = 5 * 60 * 1000; // 5 minutes
   ```

2. `ReconcilerState` 新增欄位：
   ```rust
   /// Timestamp (ms) when reconciler task started. 0 = not yet started.
   /// Used by `evaluate_actions()` to suppress auto-escalation during the
   /// startup grace window (`STARTUP_GRACE_MS`).
   /// 對帳器任務啟動時間戳。0 = 尚未啟動。
   pub startup_ms: u64,
   ```
   `ReconcilerState::new()` 初始為 `0`。

3. `evaluate_actions()` 入口（行 146 後，actions 宣告後、state 更新前）加入：
   ```rust
   // P0-0 RECONCILER-BURST-FIX: suppress all auto-contraction during the
   // startup grace window. ...（含完整雙語 comment）
   if state.startup_ms > 0
       && now_ms.saturating_sub(state.startup_ms) < STARTUP_GRACE_MS
   {
       let actionable_count = drifts
           .iter()
           .filter(|(_, v)| matches!(
               v,
               DriftVerdict::MajorDrift
                   | DriftVerdict::SideFlip
                   | DriftVerdict::Orphan
                   | DriftVerdict::Ghost
           ))
           .count();
       if actionable_count > 0 {
           tracing::info!(
               count = actionable_count,
               grace_remaining_ms =
                   STARTUP_GRACE_MS.saturating_sub(now_ms.saturating_sub(state.startup_ms)),
               "reconciler escalation suppressed during startup grace (P0-0) / 啟動寬限期抑制自動升級"
           );
       }
       return actions;
   }
   ```
   早退返回空 `actions`。State（drift_streak / burst_drift_streak / clean_cycles）**不更新**，等 grace 結束後從 0 開始計數。

4. `check_rest_failure_escalation()` 入口加相同 grace 檢查，early-return `None`。

### 6.2 `rust/openclaw_engine/src/position_reconciler/mod.rs`

在 `run_position_reconciler()` 入口設置 startup 時間：

```rust
let mut rc_state = ReconcilerState::new();
rc_state.startup_ms = now_ms_util();  // P0-0 RECONCILER-BURST-FIX
```

放在 `ReconcilerState::new()` 之後、warmup select 之前（約 mod.rs:365）。

### 6.3 單元測試（`escalation.rs` `mod tests`）

新增：

1. `test_startup_grace_suppresses_burst_escalation` — grace 期內 5 drifts 不升級
2. `test_startup_grace_suppresses_persistent_drift` — grace 期內連續 drift 不累加 streak
3. `test_startup_grace_suppresses_single_drift` — grace 期內單個 drift 不升級 Cautious
4. `test_after_grace_burst_escalates_normally` — 超出 grace 後正常 burst 升級
5. `test_grace_with_rest_failures_suppresses` — grace 期內 REST failure tier 不升級
6. `test_grace_with_startup_ms_zero_is_noop` — backward-compat：`startup_ms=0`（未設置）時不觸發 grace

## 7. 驗收

### Unit test
`cargo test -p openclaw_engine` → 1330 (ort) / 1323 (default) + 6 新測試 = **1336 / 1329** 全綠。

### 部署驗證（operator）
1. `bash helper_scripts/restart_all.sh --rebuild`
2. 重啟後前 5 min：`tail -f /tmp/openclaw/engine.log | grep "startup grace"` 應看到 suppression 日誌
3. 前 5 min 內 governance 級別保持 `NORMAL`（查 `risk_gov` V014 audit events）
4. 5 min 後若 Bybit 仍有 drift 殘留，正常升級路徑生效（持續 drift → Defensive 驗證 6-RC-3 仍有效）
5. 乾淨環境測：無 Bybit 殘留下 30 min 內 governance 保持 NORMAL（驗收條件）

### 注入測試（可選 follow-up）
E2E test `tests/reconciler_e2e.rs` 加場景：
- `startup_grace_window_ignores_orphan_storm` — 注入 10 orphan + 10 ghost 於 grace 期內 → 無 escalate 分發，orphan adoption 命令照常發出

## 8. 不在此範圍

- **Ghost adoption / cleanup 路徑**（paper_state 主動 sync to Bybit）— 有架構價值但超出本修復範圍，P0-0 只解決 warmup 期抑制
- **BURST_DRIFT_COUNT 配置化**（從 hardcoded 改 RiskConfig）— 不影響此修復，可單獨做
- **Governance 側 startup_grace hook** — 不動 `risk_gov.rs`，保持其單向升級不變式
- **FAST_TRACK 與 reconciler 的互動邊界審視** — 事故中 `ReduceToHalf` 與 `ft_pause_new_entries` 的觸發都是既定邏輯在 Defensive 下的正確響應，不是 bug；修 reconciler 不升級即解此鏈路

## 9. 預估工時

- Spec（本文件） 0.5d ✅
- 實作（escalation.rs + mod.rs） 0.3d
- Unit test × 6 0.3d
- 回歸 + 文件 0.3d
- **Total ~1.5d**

## 10. 關聯

- 阻塞者：無
- 解鎖：P0-1（G-2 FundingArb 驗證）、P0-3（Phase 5 edge 2w 重評）
- 相關 commit（歷史）：6-RC-6 FIX-B（連續兩輪 burst 才觸發 CB）— 今次新增 grace 層在其之上
