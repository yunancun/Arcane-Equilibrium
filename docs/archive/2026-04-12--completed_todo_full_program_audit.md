# 已完成歸檔：2026-04-12 全程序鏈審計修復
# Completed Archive: Full Program Chain Audit Fixes (2026-04-12)

> 來源：TODO.md「2026-04-12 全程序鏈審計」段落
> 歸檔日期：2026-04-12
> PM 確認報告：`docs/audits/2026-04-12--full_audit_fix_plan_pm_confirmed.md`
> PA 原始報告：`docs/CCAgentWorkSpace/PA/2026-04-12--consolidated_fix_plan.md`

---

## P0 — Live 阻塞 ✅ 8/8 完成

- [x] **FIX-10** ← E3: SEC-D01 [CRITICAL] — IPC HMAC 認證 Live 模式下應強制 ✅ main.rs panic guard
- [x] **FIX-03** ← FA: #2 [BLOCKER] · E3: SEC-A01 [LOW] · E5: D-01 [Medium] — FastTrack ReduceToHalf/PauseNewEntries 已處理 ✅ on_tick.rs 半倉+暫停開倉
- [x] **FIX-04** ← FA: #2 [BLOCKER] · E3: SEC-A01 [LOW] — fast_track 真實 price_drop_pct + margin_utilization_pct ✅ PriceHistoryTracker.max_drop_pct() + paper_state notional
- [x] **FIX-19** ← BB: BB-A4 [P1] [PARSE-ERROR] — execution.fast execFee 缺失時用 taker_fee_rate 估算 ✅ event_consumer/mod.rs
- [x] **FIX-13** ← E4: P0-#1 [P0-CRITICAL] — edge_estimates.rs +14 tests ✅ JSON 解析/空值/邊界/clamp
- [x] **FIX-14** ← E4: P0-#2 [P0-CRITICAL] — REST fail-closed +7 tests ✅ NoCredentials/Transport/retCode/timeout
- [x] **FIX-15** ← E4: P0-#3 [P0-CRITICAL] — 三管線並發寫入 +1 integration test ✅ 3 thread×50 writes 無損壞
- [x] **FIX-09** ← E3: SEC-E01 [HIGH] + SEC-B03 [MEDIUM] — ocEsc() 加單引號 `&#39;` 轉義 ✅ common.js

## P1 — 架構缺陷 ✅ 19/19 完成

- [x] **FIX-05** ← QC: RG-1 [P1] — correlated_exposure_pct 永遠 0.0 ✅ compute_correlated_exposure_pct() 實現
- [x] **FIX-06** ← QC: RG-3 [P1] + H5 [P1] — GridTrading grid_levels TOML→runtime ✅ grid_count 字段 + update_params 接線
- [x] **FIX-07** ← QC: RG-4 [P1] — OU theta clamp → non-OU fallback None ✅ b≥0 return None
- [x] **FIX-11** ← E3: SEC-D02 [HIGH] — Cookie secure auto-detect ✅ request.url.scheme=="https"
- [x] **FIX-16** ← E4: P1-#4 — startup.rs +5 tests ✅ FIX-16b: 2 trivial→meaningful
- [x] **FIX-17** ← E4: P1-#9 — Config hot-reload 並發 +2 tests ✅
- [x] **FIX-18** ← E4: 四.2 — Price=0 +2 tests ✅
- [x] **FIX-20** ← BB: BB-A5 [P1] [RISK] — pre_check_order() 刪除 ✅ dead code 移除
- [x] **FIX-22** ← FA: #8 [MAJOR] + #6 [MAJOR] — 4 個 MlSwitches 假欄位刪除 ✅
- [x] **FIX-29** ← E5: R-02 [High] — on_tick() 1307→1186 行 ✅ 抽出 on_tick_helpers.rs
- [x] **FIX-30** ← E5: P-01 [High] — symbol.clone() 審查 ✅
- [x] **FIX-32** ← E5: P-04 [Medium] — risk_config() 改用借用 ✅
- [x] **FIX-39** ← A3: §5.1 — Danger Zone → openConfirmModal() ✅
- [x] **FIX-40** ← A3: §5.1 — 策略刪除 → openConfirmModal("delete-strategy") ✅
- [x] **FIX-47** ← TW: §4.1 — CLAUDE_REFERENCE.md 更新至 2026-04-12 ✅
- [x] **FIX-48** ← TW: §4.1 — KNOWN_ISSUES.md 更新 ✅
- [x] **FIX-52** ← R4: §四 P1-#5 — SCRIPT_INDEX.md 全面更新 ~11%→~90% ✅
- [x] **FIX-55** ← BB: BB-A1+A2+A3 [P1] — 3 API paths verified correct ✅

## P2 — Rust 7 項 ✅ 完成（commit `84f00eb`）

- [x] **FIX-24** ← QC: RG-2 [P2] — bb_reversion RSI 閾值可配
- [x] **FIX-25** ← QC: H1 [P2] — grid_trading fee_rate 字段取代硬編碼
- [x] **FIX-26** ← QC: H4 [P2] — bb_breakout squeeze bool→時間戳過期
- [x] **FIX-27** ← QC: H3 [P2] — kelly_sizer 負 edge 返回 0.0
- [x] **FIX-28** ← QC: H2 [P2] — intent_processor account_leverage 字段
- [x] **FIX-31** ← E5: D-03 [Low] — PriceEventKind typed enum
- [x] **FIX-33** ← E5: P-03 [Medium] — event_consumer exec_id 去重 O(1)

## P2/P3 — Session 3.3 追加 ✅ 完成

- [x] **FIX-36** ← FA: #15 [MINOR] — delegation_framework.py 孤立模組刪除
- [x] **FIX-42** ← A3: §2.1 [MAJOR] — console.html 雙重導航移除
- [x] **FIX-43** ← A3: §2.1 [MAJOR] — tab-trading.html 雙層 iframe 消除
- [x] **FIX-49** ← TW: §3.1 [MISSING] — 3 個 daily_summary 補建
- **FIX-37** ← FA: #14 [MINOR] — PIPELINE_BRIDGE None：**by design**
- **FIX-50** ← TW: §7.1 — CHANGELOG 超長：**自然解決**（925 行 < 1200 限）
- **FIX-58** ← E3: SEC-F05 — Unix socket chmod：**已完成**（0o600）

## PNL-FIX-1~4 ✅ 全部完成

- [x] **PNL-1** — Phase 5 reframing（CLAUDE.md + memory 重寫）
- [x] **PNL-2** — Fee underreporting 修復（emit_close_fill 寫真實費用 + charge_fee helper）
- [x] **PNL-3** — Per-strategy edge breakdown（656 round trips，4 策略 gross 負 edge）
- [x] **PNL-4** — fast_track 觸發根因（price_drop/margin_util 為死碼，唯一觸發=CB）
- [x] **QoL-4** — Paper PnL 異常大根因（commit `2a422fa` PNL-FIX-1，跨 symbol close 路徑修復）
