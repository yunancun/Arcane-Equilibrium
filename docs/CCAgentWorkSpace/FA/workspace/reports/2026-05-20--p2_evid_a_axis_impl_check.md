# P2-EVID-A-AXIS-IMPL-CHECK — FA 雙端 IMPL audit

**日期**：2026-05-20
**Owner**：FA
**Trigger**：FA 2026-05-20 P2-ENTRY-CLOSE-MAKER 分析 EVID-2 的 25% probability IMPL bug 假設
**Status**：✅ AUDIT DONE — verdict ready

## VERDICT

**IMPL WIRED BUT DOMINATED — 更精確說：IMPL WIRED FOR LOG ONLY**

`offset_bps` 確認 silent dead in fill detection — Python sweep 與 Rust production 兩端 1:1 對應；fill_detection / fee_saving / adverse_selection 三個 path 全不引用 offset_bps。SD-1 report 在 PA workspace 已 verified：FA 2026-05-20 EVID-2 假設 25% probability「IMPL bug」**升級為 100% confirmed**，但**性質非 bug**，而是 **strict-passive close-maker 設計 intent**：限價 = BBO ± buffer×tick，`offset_bps` 在當前 Rust IMPL 僅做 warn log field（5 處），signature alignment leftover 與未來 last_price fallback path 預留 backward-compat。

## 5 條 Evidence

1. **`srv/helper_scripts/calibration/phase_1b_maker_price.py:115-117`** — Python port 明文注釋「為什麼保留 fallback_offset_bps 參數但未使用：與 Rust signature 一致；Rust 的 fallback_offset_bps 在 warn log 引用但不參與計算（strict-skip 路徑下無 last_price ± offset_bps fallback）」。

2. **`srv/helper_scripts/calibration/phase_1b_maker_price.py:131-148`** — `compute_post_only_price` price formula：`buffer = float(buffer_ticks) * tick; price = bid - buffer / ask + buffer / ask - cross_buffer / bid + cross_buffer`。**100% 無 offset_bps 引用**。

3. **`srv/rust/openclaw_engine/src/strategies/common/maker_price.rs:285-317`** — Rust production `compute_post_only_price` 完全等價公式：`let buffer = f64::from(buffer_ticks) * tick; let price = if is_long { match (bid, ask) { (Some(bid), _) => bid - buffer, ... } }`。`fallback_offset_bps` 只在 5 個 warn! 點作 log field（line 256, 277, 295, 311, 330, 355），生產 0 進入 price formula。

4. **`srv/helper_scripts/calibration/phase_1b_sweep_replay.py:259-264 + 308-322`** — sweep `simulate_cell_against_fill` 用 `limit_price` (= `compute_close_limit_price(...)` 回傳) 跟 BBO 比較判 fill：`if sample.best_bid >= (limit_price - FILL_PRICE_TOLERANCE)`。**fill 判定 100% 用已不含 offset 的 limit_price**；A axis 變化從 cell config → policy.offset_bps → 傳給 compute_post_only_price → 完全 ignored → 完全相同 limit_price → 完全相同 fill outcome。

5. **`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_sweep_anomalies_sd_report.md:84-95` (SD-1 verdict)** — empirical 證據：sweep_aggregate.csv 81 cells 中 A={0.5, 1.0, 2.0, 3.0} 4 cells × 18 row pairs **bit-identical 至 7 位小數**（precision higher than f64 noise threshold for any meaningful calculation involving offset_bps）。SD-1 已 verified spec design intent 而非 IMPL bug。

## 升級建議

**性質升級**：當前 spec v1.3 §4.2 表中 `offset_bps` 列為「限價偏好我方多少 bps（過大易 reject，過小易 timeout）」是 misleading（暗示 active price impact）。**真實語意**是「dead config field，無 runtime effect」。

**Action 路徑**（不需 patch IMPL）：
- **(a) SD-1 已建議 spec v0.3 amend note**（PA report §3.1）— 建議升級為「SHALL」標 deprecated，下一輪 sweep prune A axis（78 → ~20 cells，efficiency +75%）
- **(b) PM ratify offset_bps deprecation 半 / 全棄**：
  - 半棄：保留 field for future last_price fallback path（若未來 schema 改 enable BBO-missing 時走 fallback），保留 backward-compat
  - 全棄：next migration 拆除 field + Rust schema 改名（成本高，破 audit log；FA 不建議）
- **(c) sweep harness clean up**：phase_1b_maker_price.py 把 `fallback_offset_bps` 重命名 `_unused_offset_bps_compat` 防 future audit 再迷失

**重要**：cell pick G-AB-01-C90 (A=0.5) 仍 valid pilot；雖 4 cells fill rate identical，A=0.5 是 conservative baseline。

## Follow-up OQ

**OQ-C4-1**：spec v1.3 §4.2 表「offset_bps 0.5」for grid / phys lock family 是否需要 PM ratify 改成 `0` 或 hard-coded `null`？保留 0.5 + dead status 是 governance debt。

**OQ-C4-2**：Rust 的 `CloseMakerPricePolicy.offset_bps: f64` field 是否在下一輪 schema sweep 整理時 deprecate？若 deprecate，需確認沒有任何 future feature dependency 預期 enable last_price fallback path。

**OQ-C4-3**：sweep harness `phase_1b_sweep_cells.py` A axis 是否在下一輪 sweep run 中 collapse 到 1-value？這直接 affects calibration cell count（saves ~58 cells × ~17ms ≈ ~1s wall time + 大幅降低認知負擔）。

**OQ-C4-4**：如 future enable `BBO-missing → last_price ± offset_bps` fallback path（Rust line 257-258 注釋已暗示「no last_price fallback」是當前設計選擇），此 enable 是否需新 ADR + spec amend？因會重新賦活 offset_bps 並改變 strict-skip 行為。

**OQ-C4-5**：CC + FA 是否需在 `feedback_*.md` 或 `docs/agents/spec-compliance` skill 加一條反模式「sweep dimension parameter 必須先 grep production formula 確認真實 wiring」？SD-1 + EVID-2 都是同類陷阱，未來 sub-agent 可能再撞。

## 16/16 + 9/9 PASS（FA standard）

無業務代碼改動 / 無 IPC / 無 live auth / 0 BLOCKER。

## 報告交付規範注

FA 因 skill restriction 未自行寫此 .md report；本檔由 PM 主會話從 sub-agent 對話成果落檔（內容 1:1 自 FA findings）。
