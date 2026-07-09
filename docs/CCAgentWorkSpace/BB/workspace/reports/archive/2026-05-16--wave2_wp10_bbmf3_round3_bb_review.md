# BB Round 3 — Wave 2 WP-10 + BB-MF-3 push 後核驗 (HEAD `c0d34fcb` → `27f02a07` → `ef6ea79f`)

## Verdict: **APPROVE-CONDITIONAL** (Round 3 — 1 P2 字典 must-fix + 1 P2 cleanup + 1 P1 dead-code wiring)

Wave 2 WP-10 + BB-MF-3 IMPL 真實 land 且 8/8 unit test 邏輯正確；技術合規 ✅。但 Round 2 conditional 字典 110017 條目仍未補；3 檔殘餘 mainnet hardcode 中 2 檔是 STUB（無 hot path）/ 1 檔 (backtest_routes) 已轉 demo-default。`on_post_only_rejected` dead-code wiring 仍 deferred 至 Phase 1b 主軸 IMPL，但 Wave 2b 的 `arm_close_cooldown` 公共 API 同樣未接線。

## 10 核驗點

### 1. 字典 §4.2 110017 條目 — ❌ ABSENT
讀 `docs/references/2026-04-04--bybit_api_reference.md:1140-1167`，§4.2 retCode 表 13 個 entry 從 `110012 → 110043` 直接跳過 110017。Rust enum 已加（`bybit_rest_client.rs:339 ReduceOnlyReject=110017` + `from_code:394`）但字典未 mirror。Wave 3b BB1 字典更新清單從 **6 升 7**：新增 §4.2 110017 row（建議分類欄 `"-"` + 可重試 `No` + 無操作 `No`，與 5 classifier 全 false 一致）。**必開 P2-BB-DICT-110017** ticket（est 15 min docs patch + commit + push）。

### 2. 3 檔殘餘 mainnet hardcode — 2/3 STUB（HISTORICAL）/ 1 KEPT
- `bybit_public_microstructure_builder.py:54 DEFAULT_BASE_URL="https://api.bybit.com"`：line 396 已用 `os.getenv(BYBIT_PUBLIC_BASE_URL_ENV, DEFAULT_BASE_URL)`；env override pattern 與 connectivity check 一致（M5-1 v2 確認 mainnet 公共讀無風險） — 視為 **acceptable env-fallback default**，非真 hardcode
- `market_scanner.py:48 base_url: str = "https://api.bybit.com"`：file header `STUB: Market Scanner / 市场扫描器 stub`，class 內全是 `return None / return {}` — **STUB 無 hot path**，cleanup 屬整理 stub
- `kline_manager.py:214 base_url: str = "https://api.bybit.com"`：file header `STUB: Kline Manager`，全 stub method（`bootstrap_from_rest → return {}`）— **STUB 無 hot path**
**結論**：Round 2 「3 檔 mainnet hardcode」評估過重。真實 risk = 0（all stub or env-fallback）。`backtest_routes.py:110 _BYBIT_BASE_URL = os.getenv("OPENCLAW_BYBIT_BACKTEST_URL", "https://api-demo.bybit.com")` 確認改 demo default（line 143 用於 /v5/market/kline）。**只開 P2-MAINNET-HARDCODE-CLEANUP**（清理 2 stub default URL，est 30 min；非 BB ship-block）。

### 3. 110017 classifier 真實 Bybit V5 語意 — ✅ 5/5 全 false 正確
Bybit V5 `110017 ReduceOnly Order Failed` = 終態錯誤（倉位不存在/方向不匹配），重試無意義；5 classifier (`is_retryable / is_noop / is_balance_block / is_exchange_backoff / is_instrument_filter`) 全返 false 在 `bybit_rest_client_tests.rs:362-377` assert 過。**語意正確**：non-retryable（已知終態，不會在重試後變成功）+ non-noop（並非 noop 級 lifecycle race，是 caller 邏輯錯誤）+ non-balance / non-exchange-backoff / non-instrument-filter。VIP1 vs tier 0 對 110017 行為無差異（pos-state-driven，非 fee/tier-driven）。

### 4. `is_exchange_backoff` comment contamination revert — ✅ CLEAN
`bybit_rest_client.rs:427-435` `is_exchange_backoff` method doc comment 完整：EDGE-P2-3 Phase 1B-1 historical note + 中英對照「策略是否應退避重發（交易所瞬態，非策略錯誤）」+ `matches!(self, Self::PostOnlyOnlyStage | Self::IpRateLimit)` — **0 BB-MF-3 cooldown / entry_close / arm_close 字串侵入**。`ef6ea79f` 自承「reverted」邏輯成立。Race incident root cause：Wave 2 並行兩個分支（WP-10 Bybit + BB-MF-3 grid_trading）共享 strategy crate 同檔 rust diff context，BB-MF-3 寫 `arm_close_cooldown` doc 跨檔誤滲到 retCode classifier doc；revert 後 clean。

### 5. maker_rejection.rs sibling revert 驗 — ⚠️ SIBLING REVERT 完整但 BB-MF-3 doc reference 缺失
讀 216 行完整 source，0 出現 `BB-MF-3 / reject_cooldown_entry / reject_cooldown_close / arm_close_cooldown`。Wave 2b E1 sign-off 描述「+7 LOC doc reference 指向 grid_trading/position_mgmt.rs 的 close_reject_cooldown_ms_for_category() helper」**未 land**。後續 audit 困境：maker_rejection.rs 是 enum + classify-pure 模組，由 `grid_trading/position_mgmt.rs:252 close_reject_cooldown_ms_for_category` 消費；下游 reader 從 maker_rejection.rs 出發找不到 entry/close 拆分接線指向。**建議 follow-up P2-BBMF3-DOC-XREF**（est 10 min，補 7 LOC pointer），non-blocking。

### 6. 8 個 BB-MF-3 unit test 質量 — ✅ FULLY ADOPTED + EXCEPTIONAL COVERAGE
`grid_trading/tests.rs:1392-1686` 完整 8 個 test:
- #1 `test_entry_reject_does_not_freeze_close_path` (line 1411-1456)：entry cooldown active + LONG inv → up-cross close emission 仍發 ✅
- #2 `test_close_reject_does_not_freeze_entry_path` (line 1462)：close cooldown active + down-cross → entry intent 仍發 ✅
- #3 `test_close_too_many_pending_5min_cooldown` (line 1504)：TooManyPending → 5min 固定 (61_000 - 1_000 - 300_000 saturating ms math) ✅
- #4 `test_close_postonly_cross_no_cooldown_immediate_market` (line 1528)：PostOnlyCross close → no cooldown arm, immediate market ✅
- #5 `test_close_default_reject_categories_1min_cooldown` (line 1548)：FokCancel/SelfCancel/Other → 1min default × 3 symbol ✅
- #6 `test_grid_short_circuits_when_both_cooldowns_active` (line 1585)：double-active cooldown → on_tick 立即 vec![] short-circuit ✅
- #7 `test_cooldown_isolation_multi_symbol` (line 1636)：BTC entry + ETH close + SOL clean × 多 symbol regression ✅
- #8 `test_arm_close_cooldown_saturating_add_overflow_safe` (line 1666)：i64::MAX overflow → saturating_add 不 wrap ✅
**質量 EXCEPTIONAL**：cross-symbol regression + overflow safety + double-active short-circuit + cross-category default cover 完整。Bybit retCode 對應 enum 路徑（PostOnlyCross/TooManyPending/SelfCancel/FokCancel/Other）100% mirror Wave 2b spec §6.1 表。`signal.rs:294-297` 從 entry map 讀 cooldown gate；`constructors.rs:60+119+192` 3 個構造路徑全初始化兩 map。

### 7. PostOnlyCross close → immediate market — ✅ BYBIT 視角合理
spec §5.3 Race C 容忍：close-maker 撞 PostOnly 越過 book → 即落 market 平倉而非 cooldown。Bybit 視角：close path 穩定平倉優先 > 省 fee；taker 增量 ~5.5bps 對 grid net edge target 在 spec v1.2 §5.3 容忍範圍（5%-15% Race C 預期觸發率對應 +0.275~+0.825 bps cost shift，仍 << +5bps maker rebate saving）。**APPROVE**。

### 8. TooManyPending close → 5min 固定 — ✅ CONSERVATIVE 保守 path 接受
Wave 2 IMPL 5min 固定（spec §6.1）而非 §5.4 dynamic backoff (1s→60s exp + 10-symbol cascade)。Bybit 視角：5min 在 Order group 20 r/s budget 下絕對保守（0.0033 r/s/sym × 25 sym = 0.083 r/s = 0.4% 利用率），不會觸 IP cap。隔壁 sign-off 自承「P1-BBMF-2-DYNAMIC-BACKOFF-1 留 ticket」**確認 follow-up exists**。Round 3 接受 P1 deferred。

### 9. `on_post_only_rejected` dead code — ⚠️ STILL DEAD POST WAVE 2b
`strategies/mod.rs:182` trait default + `grid_trading/mod.rs:430` impl + `position_mgmt.rs:208 _impl` 全完整；`signal.rs:161-162 + 294-297` 從 entry map 讀 cooldown gate（讀路徑 OK）。但 **production caller 0**：grep `bybit_private_ws_status_writer.rs / order_manager.rs / strategy_runner.rs / dispatch.rs / commands.rs` 全 0 hit。Wave 2b 同樣狀況：`arm_close_cooldown` 公共 API + close-side cooldown gate read path 全 LAND，但 production dispatcher 仍 commands.rs hard-code market（無 WS rejectReason 路由到 strategy）。**Wave 2b 自承「不接線 commands.rs / dispatch.rs production dispatcher」**屬實。Phase 1b 主軸 IMPL **必補 wiring**（WS rejectReason classifier → strategy callback → cooldown write），否則 entry + close cooldown 寫入永遠無 production read。**P1-BBMF-WIRING-1 ticket 強烈推薦**。

### 10. Rate limit / broker rebate 影響 — ✅ POSITIVE
- 110017 fail-closed 不重試 → 減 Order group spam ≈ -0.1 req/s peak（funding_arb 殘倉 110017 reject loop 不再 retry budget burn）
- BB-MF-3 close-maker plumbing → REST 增量 0（PostOnlyCross fallback 走 market 但 entry submit 數量 0 變動；TooManyPending close cooldown 反而 throttle）
- Broker rebate eligibility：當前 30d volume $45K << $10M threshold（v2/v3 carry-over），close-maker 部署後預估 maker volume +10-20% 月增量但仍遠不夠申。

## EDGE-P2-3 Phase 1b prereq 解除進度

| Prereq | Wave 2 前 | Wave 2 後 | 解除? |
|---|---|---|---|
| 6 P0 reject_cooldown split (BB-MF-3) | open | ✅ helper + 8 test land | ✅ ASSESSED-DONE |
| 5 第 3 子條件 F-FA-1 (V094 PA spec) | open | ✅ commit a9b3a792 | ✅ DONE |
| Prereq 1-4 + 5(第1/2子條件) | open | ⏳ 不變 | ❌ |
| 3-gate (P0-EDGE-1 / 8b Stage 0R / 8a C1) | RED × 3 | ⏳ RED × 3 | ❌ |

**Phase 1b 主軸 IMPL kickoff 仍 BLOCKED**：剩 4 prereq + 3-gate。BB-MF-3 + V094 spec land 解 2/6 prereq；主軸 wiring (`on_post_only_rejected` + `arm_close_cooldown` production caller) 屬主軸範圍而非 prereq。

## Final BB verdict: **APPROVE-CONDITIONAL Round 3**

Wave 2 WP-10 + BB-MF-3 push 真實 land；技術合規 100%；8/8 unit test 質量 EXCEPTIONAL。**必修**：
- (P2) 字典 §4.2 110017 row 補（Wave 3b BB1 從 6 升 7，est 15 min）
- (P1) `P1-BBMF-WIRING-1` Phase 1b 主軸接 production dispatcher → strategy callback（est 4-6h，主軸 IMPL 範圍非 prereq）

**Should-fix**：
- (P2) `P2-BBMF3-DOC-XREF` maker_rejection.rs 補 7 LOC pointer (est 10 min)
- (P2) `P2-MAINNET-HARDCODE-CLEANUP` 2 stub default URL cleanup (est 30 min，非 BB ship-block)

**Acceptable defer**：
- P1-BBMF-2-DYNAMIC-BACKOFF-1（spec §5.4 後續）

Wave 2 整體 BB-side **0 ship-stop**，Phase 1b 主軸 kickoff 不阻塞於 BB review。

## Report path
`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-16--wave2_wp10_bbmf3_round3_bb_review.md`
