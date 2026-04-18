# Session 進度快照 — P0-6 永久修復 + pre-compact 交接

**日期**：2026-04-18
**主角色**：PM + Conductor（Claude Opus 4.7）
**觸發**：延續上一次 compact 前 session，operator 指示 `接手 todo → "a" (P0-6 永久修復)`

---

## 已完成

### 1. P0-6 永久修復（commit `293a808`，此 session 主交付）
- **問題**：前置 gate（cost_gate / qty_zero / risk_gate / duplicate_position / governance_not_authorized / confidence / ATR / predictor）拒絕時 `verdict_info: None` → `persist_verdict` 跳過，`trading.risk_verdicts.reasons` 永久丟失 Guardian 前段拒絕理由。
- **修法**：
  - `intent_processor/mod.rs` 新增三構造器：
    - `VerdictInfo::rejected(reason)`：`verdict="Rejected"`, `reasons=[reason]`
    - `IntentResult::rejected(reason)`：synthetic VerdictInfo + `submitted=false`
    - `ExchangeGateResult::rejected(reason)`：synthetic VerdictInfo + `approved=false`
  - `intent_processor/gates.rs`：`cost_gate_paper` / `cost_gate_moderate` / `cost_gate_live` 共 6 點改用構造器
  - `intent_processor/router.rs`：paper `process_with_features` ~7 點 + exchange `process_gates_only_with_features` 所有前置 gate 拒絕點改用構造器；Guardian-Rejected 路徑保留 `vi.take()` 走真實 Guardian verdict 不動
  - `intent_processor/tests.rs`：+2 單測
    - `test_p06_pre_guardian_reject_paper_carries_synthetic_verdict_info`
    - `test_p06_pre_guardian_reject_exchange_carries_synthetic_verdict_info`
- **測試**：engine lib **1454 passed / 0 failed**（baseline 1452 → +2）
- **bundle 進 commit**：`intent_processor/` 子目錄 pre-existing cargo fmt churn 一併（同模組、緊鄰拒絕點編輯，避免二度 touch）
- **TODO.md**：§P0-6「永久修復」`[ ]` → `[x]`
- **部署**：**待下次** `bash helper_scripts/restart_all.sh --rebuild` 一併上引擎

### 2. 上一 session 延續的既有 commit（本 session 開始前已 landed）
- `127feb4` fix(engine): P0-6 移除 on_tick DIAG 代碼
- `768a660` docs(todo): G-2 結案 + P0-6 觀察 ✅ + 2026-04-18 audit findings P1-9~P1-12

---

## 進行中 / 未完成

### P0-6 剩餘 `[ ]`（未動）
- **Demo 死循環打破**：P1-8 FUP `retriage_synthetic_owner` 已 tick-level 執行，等一週觀察 6 個 bybit_sync orphan 是否消化；若不消化再轉方案 B（臨時調 `correlated_exposure_max_pct`）或方案 C（修 P0-7 Close path）。**非即時行動項**。

### TODO 關鍵路徑下一個 actionable `[ ]`
按 CLAUDE.md §十 關鍵路徑 v3：
```
P0-0 ✅ → P0-4 R1 ✅ → LIVE-GUARD-1 ✅ → P0-9 STABILITY-1 ✅
  → P0-6 intent write gap ✅ 方案 A 部署 + 永久修復 ✅ (this session)
  → P0-7 order submit gap  ← 下一站
  → P0-3 Phase 5 edge 2w 重評 + P0-2 LG-1 21d demo
  → P1-7 LEARNING-PIPELINE-DORMANT-1
  → LG-4/5 → Live
```

**注意**：P0-6 RCA 已確認「不存在獨立的 order-submit gap」——0 fills 的根因就是 P0-6 cost gate cascade。P0-6 方案 A 部署後 live_demo fills = 1073 筆 / 24h，顯示 order submit path 本身健康。P0-7 名義上仍 `[ ]`，但實質已隨 P0-6 解鎖；需 operator 決定是否 archive 或等下次 rebuild 部署 P0-6 永久修復後再觀察確認關閉。

---

## 決策

1. **Bundle fmt churn 進 P0-6 commit**：同模組、無新邏輯，避免二度 touch。沿用上一 session 768a660 的 bundling 先例。
2. **P0-7 暫緩開工**：先等 P0-6 永久修復 rebuild 部署 + 1 週觀察 live_demo `trading.risk_verdicts.reasons` 是否確實寫入拒絕理由。確認後再判斷 P0-7 是否 archive。
3. **不碰其他 uncommitted 修改**：工作樹當前有 100+ 個其他未提交檔案（pre-existing，多為上 session cargo fmt churn + LIVE-GATE-BINDING-1 殘留），本 session 嚴格限定在 `intent_processor/` + `TODO.md`。

---

## 下一步（post-compact）

1. `bash helper_scripts/restart_all.sh --rebuild` 部署 P0-6 永久修復（operator 觸發）
2. 部署後 24–48h 查 `trading.risk_verdicts` live/live_demo 最新 verdict 欄位，確認：
   ```sql
   SELECT verdict, reasons, COUNT(*)
   FROM trading.risk_verdicts
   WHERE ts > NOW() - INTERVAL '24 hours'
     AND engine_mode IN ('live', 'live_demo')
     AND verdict = 'Rejected'
   GROUP BY verdict, reasons
   ORDER BY COUNT(*) DESC
   LIMIT 20;
   ```
   預期看到 `cost_gate(JS-*)` / `qty_zero:` / `duplicate_position:` / `governance_not_authorized` 等具體 reason（修復前僅 Guardian 端 reason 可見）
3. 若 reason 寫入正確 → TODO §P0-6 整體 archive；同時確認 P0-7 order submit gap 可否一併 archive
4. 接續關鍵路徑：P0-3 Phase 5 edge 2w 重評（等 demo 達 2 週乾淨累積）+ P0-2 LG-1 21d demo 觀察

---

## 檔案變動摘要

```
rust/openclaw_engine/src/intent_processor/mod.rs     | +105 新構造器 + fmt
rust/openclaw_engine/src/intent_processor/gates.rs   | +111 改用構造器
rust/openclaw_engine/src/intent_processor/router.rs  | +249 改用構造器（paper + exchange）
rust/openclaw_engine/src/intent_processor/tests.rs   | +543 新增 2 測試 + fmt
TODO.md                                              |   +2 -1 check off 永久修復
```

engine lib test：1452 → 1454 passed / 0 failed
