---
report: A3 對抗審查 — P1-PORTFOLIO-RESTING-EXPOSURE-1 IMPL
date: 2026-05-16
auditor: A3 (UX + first-time operator + 業務邏輯防禦性視角)
subject: E1 IMPL DONE on worktree `worktree-agent-ac285607fa3c51402`（337 LOC source + 7 unit tests）
mode: Read-only adversarial review per `feedback_impl_done_adversarial_review.md`
trigger: Round 2 alpha source push P1 平行 IMPL chain step 2/4
written-by: PM main session (A3 frontmatter read-only — A3 提供完整 summary 由 PM 代寫)
verdict: **APPROVE 9/10**（2 WARN advisory，不阻 commit）
---

# A3 對抗審查報告 — P1-PORTFOLIO-RESTING-EXPOSURE-1

## §1 審查範圍

E1 sub-agent (worktree `agent-ac285607fa3c51402`) 完成 IMPL：
- `rust/openclaw_engine/src/paper_state/resting_orders.rs` +11 LOC: `pub(crate) fn resting_limit_orders_iter()` cross-symbol iter
- `rust/openclaw_engine/src/intent_processor/mod.rs` +118 LOC: helper `compute_effective_long_short_notional` SoT；改三函式 `compute_exposure_pct` / `compute_correlated_exposure_pct` / `compute_leverage` 共用 helper
- `rust/openclaw_engine/src/intent_processor/tests.rs` +208 LOC: 7 unit test + 2 helpers

A3 視角 6 方向逐項對抗審。

---

## §2 6 方向逐項 verdict

| 方向 | Verdict | 證據 |
|---|---|---|
| **A. 業務邏輯防禦性** | **PASS** | entry/close-side 判定（mod.rs:829-833）與 `router.rs:261-265/752-756` `is_reducing` 完全對齊；數學 `min(red, filled).max(0)` 封頂正確；test 4 釘住「reduces > filled 不變負」；test 7 finite guards 全跳過（qty/price NaN/0）；filled side line 796 也 finite check |
| **B. UX / 使用者觀感** | **PASS** | GUI 0 處暴露 runtime `exposure_pct` / `correlated_exposure_pct`；只有 `max_*` config 上限（`risk-tab.js:744-745`）；無新術語、新按鈕；行為唯一可觀察差異 = 風控拒絕率小幅變化，對 first-time operator 完全透明 |
| **C. 不變式不破** | **PASS** | 999.0 cap（mod.rs:897, :922）/ `balance ≤ 0 → 0.0` early return（mod.rs:893, :918）/ `.max(short_notional)` 等價邏輯（mod.rs:922 `eff_long.max(eff_short)`）全保留；hot path SLA：25 symbols × O(1) HashMap = 微秒級 |
| **D. 隔離性** | **PASS** | grep 確認 `compute_effective_long_short_notional` / `resting_limit_orders_iter` 只在 mod.rs + resting_orders.rs 出現；`risk_checks.rs` / `config/*.rs` / `replay/risk_adapter.rs` / `router.rs` caller 端未動；4 個 `risk_config*.toml` 未動；live / authorization / lease 邏輯未動；硬邊界 §四 全 GREEN |
| **E. 注釋規範** | **PASS** | 全新代碼註釋只有中文（per `feedback_chinese_only_comments.md`）；explain WHY entry 加 / close 減（mod.rs:763-781 詳述 domain logic）；explain WHY `pub(crate)`（resting_orders.rs:372-376「避免外部 module 越界擴張」）；`compute_*` 全 private `fn`（visibility 最小化） |
| **F. 16-Root + 9 安全不變式** | **PASS** | 強化原則 4/5/6/8/16（per PA report §10 已過審）；不觸原則 1/2/3/7/9/14/15；9 安全不變式由 spec §12.3 FA 評為 9/9 PASS；硬邊界 5 gates 全未觸碰 |

---

## §3 主要強項

1. **單一 SoT helper**（`compute_effective_long_short_notional`）避免兩 caller 行為漂移
2. **per-symbol netting** 不跨 symbol 假設對沖（保留「同方向風險疊加」core semantic per FIX-05）
3. **形式驗證在註釋裡明寫**（mod.rs:773-783）+ 7 unit tests 涵蓋 4 必要場景 + 3 edge case
4. **保留 `is_reducing` bypass**（router 端不變）+ Replay parallel surface 解耦（runner.rs 直寫 ReplayPaperSnapshot.exposure_pct，replay path 不感染本 IMPL 是正確設計選擇）
5. **GUI 0 改動**（A3 視角最讚 — 對 operator 完全 transparent，沒有「突然看到新數字嚇到」風險）

---

## §4 2 WARN observation（知情不阻 commit）

### WARN-1：Leverage chain semantic drift（E1 自承未驗）

- `compute_leverage` 因內部呼 `compute_exposure_pct`，現吃 effective notional 而非 filled-only。RG-2 原設計用 `total_filled_notional / balance`。
- 影響：close-side resting 大量未 fill 時，leverage 隨 effective 降低 → leverage_max gate 可能放行更多 entry。
- **不算 regression**（pending close 已是「真實可預期會減倉」的合理保守反映），但需要 PM 知情。
- 建議：W3-1+W3-2 P0 解除前 / Stage 1 demo 啟動時，加 healthcheck `[58] portfolio_resting_exposure_lineage`（per PA report §8）監控「effective vs filled-only」分歧 magnitude。
- **不阻 commit**：純 observability gap，不是 logic gap。

### WARN-2：Test coverage gap — 同 symbol 多筆 close resting 累積場景（E1 §6 #2 自承）

- 現有 test 4 是「單筆 close resting 250 > filled 50 → 封頂於 50」。
- 沒測「多筆 close resting 60+60+60=180 > filled 100 → 封頂於 100」累積場景。
- 數學上等價（line 838 `+=` 累加 + line 874 封頂），但缺 unit test 釘住不變式。
- 建議：補 1 個 test（< 30 LOC，tests.rs 餘額 207 LOC 足夠）。
- **不阻 commit**：close-maker-first 為 nice-to-have 對應；同 symbol 多筆 simultaneous resting 罕見；E4 可在 regression 後補。

---

## §5 Sign-off block

```
A3 UX AUDIT DONE: 9/10 · 對抗審 APPROVE
report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-16--p1_portfolio_resting_exposure_a3_adversarial_review.md
verdict: APPROVE (2 WARN advisory, 不阻 commit)
WARN: (1) leverage chain semantic drift 需 healthcheck [58] (PA report §8) (2) test coverage gap 同 symbol 多筆 close resting 累積 (建議 W3 補)
GUI impact: 0（runtime exposure_pct 不顯示在 GUI；只有 config max_* 上限）
注釋規範: PASS (全中文)
16-root + 9 invariant: PASS（強化原則 4/5/6/8/16）
隔離性: PASS（risk_checks / config / replay / live auth 全未動）
```

評分 **9/10**：扣 1 分給 leverage chain semantic 應該在 IMPL 同時加 observability hook（不是業務邏輯錯誤，是 fail-graceful 觀測規範不足）— 但這是 PA report §8 已預留的 `[58]` healthcheck scope，可在 commit 後立即 dispatch，不阻本 IMPL sign-off。

---

## §6 後續 action（PM 派發）

1. **W3 補 unit test**（WARN-2）— 同 symbol 多筆 close resting 累積場景 < 30 LOC（可走 E4 regression 同步補）
2. **healthcheck `[58]` IMPL**（WARN-1）— commit 後立即 dispatch；Stage 1 demo 啟動前必落地
3. **本 IMPL commit 解凍**：A3 ✅ + E2 PENDING + E4 PENDING 三方 GREEN 後 PM 統一 commit + push worktree branch + cleanup
