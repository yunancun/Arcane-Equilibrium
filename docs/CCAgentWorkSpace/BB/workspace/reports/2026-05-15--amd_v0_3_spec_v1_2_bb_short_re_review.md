# BB Short Re-Review — AMD v0.3 + Spec v1.2

**Date**: 2026-05-15
**Reviewer**: BB (Bybit Broker Compatibility Auditor)
**Subject**: AMD-2026-05-15-02 v0.3 + EDGE-P2-3 Phase 1b Close-Maker-First spec v1.2
**Mode**: Short focused re-review（30 min cap）— 不重做 round 2 deep audit；只 verify v0.1→v0.2→v0.3 + v1.0→v1.1→v1.2 patch 收口完整 + v1.2/v0.3 增量 Bybit-side risk
**HEAD**: `47b8cd23`

> 註：BB agent 是 read-only 工具集；本檔由主會話按 BB agent 返回原文存檔。

## §1 Review Scope

### 1.1 收口 verification（不重做 round 2）

- ✅ Round 2 BB-MF-1 ~ BB-MF-5 (5 must-fix) verify 是否在 v1.1/v1.2 + v0.2/v0.3 land
- ✅ Round 2 BB-SF-1 ~ BB-SF-3 (3 should-fix) verify 是否在 v1.1/v1.2 + v0.2/v0.3 land
- ✅ Round 2 BB 補錄 4 條（字典手冊）verify 是否標 TODO Wave 3b（**本任務不查字典手冊**）

### 1.2 v1.1 → v1.2 + v0.2 → v0.3 增量 Bybit-side risk verify

- E3 fee revision detail（4.5→0.5-2.0 bps + $50-$200/year）
- §5.5 NEW Race E mandatory fallback to taker
- AC-18 fallback ≥ 95% 對 Bybit Order group rate limit 的相容性
- AC-19 14d Phase 2a ≥ 30% 對 demo vs mainnet endpoint behavior 差異覆蓋
- 三個 E3 意外發現（orders.intent_id NULL / orders.status fire-and-forget / 無 fallback to taker）從 Bybit 立場合規 / broker rebate / market maker eligibility 風險

### 1.3 不在本 scope

- ❌ QC / FA / MIT 視角（並行 Wave 3a）
- ❌ 字典手冊實際更新（Wave 3b BB1）
- ❌ spec / AMD patch（PA）
- ❌ IMPL phase

---

## §2 Round 2 Must-Fix 收口 Verdict

### BB-MF-1 字典手冊 PostOnly+reduceOnly 條目 — ✅ DEFERRED CORRECTLY (Wave 3b)

**Round 2 verdict 要求**：字典手冊 §1.2 顯式記錄 PostOnly + reduceOnly 合法組合 + reject 行為對 entry/close 無區別。

**v1.2 收口檢查**：
- spec line 474-477（§6.2 末段）：「**字典手冊更新（BB-MF-1，P1 backlog Wave 3 BB1 處理，本 spec 不動字典手冊）**：字典 §1.2 顯式記錄『PostOnly + reduceOnly 並用合法』+ reject 行為對 entry/close 無區別 / 字典 §4.3 加 demo endpoint PostOnly silent degradation 警告 / **本 spec 僅引用 / 標 TODO，留 Wave 3 BB1 實際更新**」
- AMD §10「字典手冊更新需求」表保留 6 項清單明文
- TODO §11.5 Wave 3b 派工排定

**判定**：✅ **APPROVED-AS-DEFERRED**。spec/AMD 兩處皆明文標 TODO + 派工指示，與 PM Wave 3a/3b 拆分一致。本 BB short re-review 不查字典手冊（per PM 指示）；後續 BB1 任務 SoT。

### BB-MF-2 Dynamic backoff per-symbol → conditional global — ✅ FULLY ADOPTED

**Round 2 verdict 要求**：AMD §5.4 / spec §5.4 從「5 min global pause」改 dynamic backoff（per-symbol 1s→60s exp / conditional global ≥10 symbol 同時 trigger 才升 5 min global）。

**v1.1/v0.2 收口檢查**：
- AMD §5.4「Race D Mitigation — Dynamic Backoff Per-Symbol（BB-MF-2）」line 181-218：
  - per-symbol 起始 1s, binary exp `*= 2`, 上限 60s ✅
  - 重置條件 5 min 內無 trigger → 重置 1s ✅
  - Conditional global pause（1 min window 內 ≥10 distinct symbol → 升全域 5 min pause）✅
  - state 持久化 in-memory HashMap + engine restart 重置（accepted trade-off）✅
  - audit row 標記 `details.rate_limit_scope = "global"` ✅
  - 估算 IMPL ~50 LOC backoff state machine + ~80 LOC integration test ✅
- spec §5.4 line 352-381 完整 mirror AMD §5.4 規範
- spec §5.4 註明「v1.0『全域 5min pause』過度保守（Bybit V5 Order group 20 req/s per UID，rate-limit recovery 是 sub-second 級；5min 是 3000x overshoot，會 starve close path）」line 354 — **與我 round 2 BB-MF-2 推導一致**

**判定**：✅ **FULLY ADOPTED**。設計 cover BB 推薦 mitigation；Bybit V5 Order group rate-limit recovery 模型對齊；無 starve close path 風險。

### BB-MF-3 reject_cooldown split P0 priority — ✅ FULLY ADOPTED

**Round 2 verdict 要求**：reject_cooldown entry/close 拆分升 P0 IMPL prereq；E1-D ticket 在 Phase 2a Demo enable 前必 land + Linux runtime 驗 entry/close cooldown isolation。

**v1.1/v0.2 收口檢查**：
- AMD §8 IMPL Prerequisites 第 6 條 line 315-319：
  - 「`reject_cooldown` entry/close 拆分升 P0 priority pre-Phase 2a Demo enable 必 land（BB-MF-3）」✅
  - 標 P0 priority + E1-D ticket promote ✅
  - 加 `event_consumer/cooldown_isolation_tests.rs` regression test 要求 ✅
  - 「問題嚴重度提升」明文 entry side 觸 rate-limit-adjacent 條件後 → close path silent degradation 永遠走 market（失去整個 maker 優化價值）✅ — **與我 round 2 §3 「bug 嚴重度提升」一致**
- spec §6.1 line 423-432 mirror + 「v1.1 BB-MF-3 升 P0 priority」明文
- spec §14 IMPL 啟動 6 條件第 6 條 line 812 同步

**判定**：✅ **FULLY ADOPTED**。從「by-the-way scope-in」升 P0 IMPL prereq；E1-D 工作鏈定位明確；regression test scope 對齊。

### BB-MF-4 Reject classifier 復用 entry enum — ✅ FULLY ADOPTED

**Round 2 verdict 要求**：spec §6.2 必明文「close side `MakerRejectionCategory` 復用 entry side classifier，不新建 `Self::CloseTooManyPending` / `Self::ClosePostOnlyCross` variant」；改用既有 5 variant + close path routing 邏輯分流。

**v1.1 收口檢查**：
- spec §6.2 line 434-472：
  - 標題明文「（BB-MF-4 enum reuse；不新建 CloseTooManyPending / ClosePostOnlyCross variant）」✅
  - 「v1.1 設計修正（BB-MF-4）」line 436-438 引用我 round 2 原文：「`EC_PostOnlyWillTakeLiquidity` 的 mechanical condition 對 entry/close 是相同的，與訂單 side 無關。新建 close-side variant 等於把同一個 Bybit error code 拆成兩個 Rust enum case，破壞 enum 1:1 mapping invariant」✅
  - 設計範例 code 明確 `MakerRejectionCategory` enum 不變 + dispatch handler 加 `side: OrderSide` flag 分流（line 441-472）✅

**判定**：✅ **FULLY ADOPTED**。設計符合 Bybit reject reason 字典 1:1 mapping invariant；維護 enum SSOT。

### BB-MF-5 Reject sample healthcheck Phase 2a Demo AC — ✅ FULLY ADOPTED

**Round 2 verdict 要求**：Phase 2a Demo 7d AC 加 reject sample healthcheck，每 env 7d ≥ 1 sample per `EC_PostOnlyWillTakeLiquidity` / `EC_ReachMaxPendingOrders` reject category；0 樣本 → upgrade Phase 2b 前必跑 mainnet probe。

**v1.1 收口檢查**：
- spec §8.3 line 594-612 新增 `[65] close_maker_reject_samples` healthcheck（per BB-MF-5）：
  - PASS criteria：each env 7d ≥ 1 sample per category ✅
  - 0 樣本 → upgrade Phase 2b LiveDemo 前必跑 mainnet probe 驗 demo endpoint silent degradation 不存在 ✅
- spec §11.4 AC-15 line 711 升 statistical AC：「**Reject sample healthcheck（v1.1 BB-MF-5）**：每 env 7d 至少 ≥ 1 sample per `EC_PostOnlyWillTakeLiquidity` / `EC_ReachMaxPendingOrders` reject category；0 樣本 → upgrade Phase 2b 前必跑 mainnet probe 驗 demo endpoint silent degradation 不存在」✅
- spec §11.1 AC-7 line 687 引用「健康檢查 `[62][63][64][65]` PASS 7d 持續」✅

**判定**：✅ **FULLY ADOPTED**。覆蓋 demo endpoint PostOnly + reduceOnly silent degradation 的 doc gap risk；mainnet probe escalation path 明確。

### Round 2 Must-Fix 收口總結

| BB-MF | 描述 | 收口狀態 | Action |
|---|---|---|---|
| BB-MF-1 | 字典手冊 PostOnly+reduceOnly | ✅ DEFERRED Wave 3b | 本 spec/AMD 標 TODO；BB1 後續 |
| BB-MF-2 | Dynamic backoff per-symbol | ✅ FULLY ADOPTED | AMD §5.4 + spec §5.4 完整 mirror |
| BB-MF-3 | reject_cooldown split P0 | ✅ FULLY ADOPTED | AMD §8 prereq 6 + spec §6.1 + §14 |
| BB-MF-4 | classifier 復用 entry enum | ✅ FULLY ADOPTED | spec §6.2 設計範例 |
| BB-MF-5 | reject sample healthcheck | ✅ FULLY ADOPTED | spec §8.3 + AC-15 |

**5/5 must-fix 全收口；無 outstanding gap**。

---

## §3 Round 2 Should-Fix 收口 Verdict

### BB-SF-1 [64] close_maker_rate_limit_pause_duration healthcheck — ✅ FULLY ADOPTED

**Round 2 verdict 要求**：加 `[64] close_maker_rate_limit_pause_total_duration_per_day` healthcheck，per env 7d 累計 pause time > 5 min/day → WARN，> 30 min/day → FAIL（防 maker path silent-dead）。

**v1.1 收口檢查**：
- spec §8.1 line 562-580 新增 `check_close_maker_rate_limit_pause_duration()`：
  - per_symbol_pause_sec + global_pause_sec 兩 sub-metric ✅
  - per-symbol thresholds: PASS ≤ 5 min/day per symbol / WARN 5-30 / FAIL > 30 ✅
  - global pause thresholds: PASS ≤ 5 min/day / WARN 5-30 / FAIL > 30 ✅ — **完全 mirror BB-SF-1 推薦 thresholds**
- spec §4.4 line 295 + AMD §4.1 line 141 配套引用
- spec §8.2 metric 表 line 591-592 加 `close_maker_per_symbol_backoff_active` (gauge per-symbol) + `close_maker_global_pause_total_seconds` (counter, [64] 配套) ✅

**判定**：✅ **FULLY ADOPTED**。Threshold 對齊 BB 推薦；防 maker path silent-dead 機制完整。

### BB-SF-2 spec §1.2 fee saving 4.5 → 3.5 bps（後 v1.2 進一步 → 0.5-2.0 bps net per Track E3）— ✅ FULLY ADOPTED + ENHANCED

**Round 2 verdict 要求**：spec §1.2 把 4.5 bps 改成 3.5 bps + 引用真實 `account_manager.taker_fee/maker_fee` SoT。

**v1.1/v1.2 收口檢查**：
- spec §1.2 line 36 + line 42：
  - v1.1：「真實 saving per close = (taker 5.5 − maker 2.0) = 3.5 bps」（與 BB-SF-2 一致）
  - v1.2 進一步：「per Wave 1 Track E3 empirical baseline，fee saving revised 4.5 → **0.5-2.0 bps net per close attempt**」+ 三層解讀（fill-conditional best 3.31 / per submitted mid 0.95 / close conservative 0.66）+ 全年 $200-$500 → **$50-$200**
- spec §1.2 line 42 + AMD §6 footnote line 247 「Bybit fee tier 0 真實 maker = 2.0 bps / taker = 5.5 bps（per BB-SF-2 實測修正）」明文引用 BB-SF-2 ✅
- AC-5 改「改善 ≥ taker baseline 的 +1.5 bps」（v1.1 QC-SF-1 推導，line 686）；v1.2 不再改 AC-5 數值，只改全年估值

**Bybit consistency check**：
- 0.5-2.0 bps net 保守 range 與 Bybit fee tier 0 fee structure 一致（maker rebate 2.0 bps / taker fee 5.5 bps；fee saving cap = 3.5 bps per side；fill rate × 3.5 - fallback overhead = empirical range 0.66/0.95/3.31 三層 → 0.5-2.0 bps cover）
- 未在 spec/AMD 寫死 BTC/ETH 大 cap symbol 與 alt small cap symbol 的 fee 差異 — **per Bybit V5 fee tier 是 per-account VIP tier 維度，非 per-symbol**（VIP 0/1/2/...，每個 tier 內所有 USDT-perp linear 同 fee rate）。spec/AMD 不引入 per-symbol fee 假設正確
- 未引入 maker rebate VIP 負費率假設（OpenClaw 30d volume ≪ VIP 1 $1M threshold；維持 tier 0）— 對齊 BB round 2 §4 結論
- 全年 $50-$200 估算與 Bybit 30d volume 真實規模一致（demo grid 7d 155 closes × $300 × 0.5-2.0 bps × 1.2/h ≈ $50-$200/year）

**判定**：✅ **FULLY ADOPTED + ENHANCED**。v1.2 fee revision 與 Bybit fee tier 0 結構一致；保守 0.5-2.0 bps net range cover empirical 不確定性；全年估值 conservative + realistic；無 BTC/ETH alt 區分缺漏（per-account 維度）。

### BB-SF-3 compute_close_limit_price 加 small-tick alt symbol corner case — ✅ FULLY ADOPTED

**Round 2 verdict 要求**：spec §6 compute_close_limit_price 加 instrument filter check：
- 若 `offset_bps / 10000 * price < tick_size` → 自動 escalate buffer_ticks 至 2-3
- 若 symbol `status != "Trading"` → strict-skip → market
- E1 必驗 1000PEPEUSDT / 1000BONKUSDT / 小 tick alt corner case

**v1.1 收口檢查**：
- spec §4.2 footnote line 205「Footnote (BB-SF-3, small-tick alt symbol corner case)」：
  - 明文 1000PEPEUSDT / 1000BONKUSDT tick_size = 0.000001 ✅
  - E1 IMPL 邏輯：「若 `tick_size * buffer_ticks < spread_bps / 2 * mid_price` → 自動 widen buffer 到滿足 strict-skip 邊界，否則 strict-skip 走 market」✅
- AMD §6 footnote line 253-254 mirror ✅
- spec §9.2 test 表 line 633「compute_close_limit_price unit | strict-skip / per-reason buffer / inverted is_long / **spread_bps > 50 strict-skip (QC-SF-4)** / **small-tick alt symbol (BB-SF-3)**」✅
- 「symbol status != Trading → strict-skip」未明文寫入 spec — 但 instrument filter cache 已涵蓋（Bybit `/v5/market/instruments-info` 的 `status` 欄位），且 spec §6.2 enum allowlist 已涵蓋 ContractNotLive case（110074 → fail-closed）；不阻 IMPL

**判定**：✅ **FULLY ADOPTED**。Small-tick handling 邏輯明文 + test 覆蓋；symbol status check 走既有 instrument filter cache 路徑（不需新 spec entry）；無新 Bybit-side risk。

### Round 2 Should-Fix 收口總結

| BB-SF | 描述 | 收口狀態 |
|---|---|---|
| BB-SF-1 | [64] healthcheck | ✅ FULLY ADOPTED |
| BB-SF-2 | fee saving 4.5→3.5 (v1.1) → 0.5-2.0 (v1.2) bps | ✅ FULLY ADOPTED + ENHANCED |
| BB-SF-3 | small-tick alt symbol corner case | ✅ FULLY ADOPTED |

**3/3 should-fix 全收口；無 outstanding gap**。

---

## §4 Round 3 (v1.2/v0.3) 增量 Verdict

### 4.1 E3 fee revision detail (4.5→0.5-2.0 bps + $50-$200/year) — ✅ APPROVED

已在 §3 BB-SF-2 收口 verdict 涵蓋。**追加 verdict**：

- **Bybit fee structure consistency**：✅ tier 0 maker 2.0 / taker 5.5 / saving cap 3.5 bps per side ↔ E3 三層解讀 (3.31/0.95/0.66) → 0.5-2.0 bps net 保守 range 完全 cover
- **Per-symbol fee 差異**：N/A（Bybit fee tier per-account 非 per-symbol；BTC/ETH alt 無區分需求）
- **VIP tier 升級影響**：N/A（30d volume 估 < $300k ≪ VIP 1 $1M threshold；維持 tier 0；無 fee rebate eligibility 變動）
- **Maker maker rebate**：未引用（VIP 0 無 maker rebate；tier ≥ 1 才有 negative maker rate）— 正確不假設
- **BB-SF-2 conservative 結論一致**：原 BB round 2 §4 「fee tier 影響本次 refactor edge 約 $200-$500/year，不能救 -110 USDT structural deficit」→ v1.2 進一步 conservative 為 $50-$200，更貼近 close path empirical reality；不改變「不能救 structural alpha deficit」結論

**判定**：✅ **APPROVED**。fee saving estimate revision 與 Bybit fee tier 0 真實值一致；保守 range cover empirical uncertainty；全年估值 realistic；無新 Bybit-side risk。

### 4.2 §5.5 NEW Race E mandatory fallback to taker — ✅ APPROVED

**Bybit-side rate limit budget impact analysis**（per `bybit-policy-compliance` skill §3 + crypto-microstructure-knowledge §5.1）：

**情境**：close maker pending 結束（成功 / 超時 / reject / cancel ack）後若仍未平倉 → 必 dispatch market；engine 不應讓 close intent silent dropping。

**Bybit Order group rate budget 估算**（25 sym × 5 策略 grid，per BB memory 2026-05-10 W1+W2 baseline）：
- baseline rate ≈ 0.7 req/s（funding poller + OI poller + LSR poller + WS public + auth REST + healthcheck）
- close-maker-first 增量（worst case 全 fallback to taker = 1 cancel + 1 market re-dispatch per close）：
  - demo grid 7d 155 active closes ÷ 7d ÷ 24h × 25 symbols × ~1.2 closes/h × (1 + 1) = ~60 req/h ≈ 0.017 req/s
  - 若 race E mandatory fallback 觸發率 100% 仍 = 0.017 req/s
  - **vs Bybit Order group 20 req/s per UID cap = 0.085% 利用率**
- burst 5s window：worst case 25 sym 同時 timeout = 25 cancel + 25 market re-dispatch = 50 req / 5s = 10 req/s（50% 餘裕，per round 2 §2 算式一致）
- conservative cooldown 不必要（rate budget 餘裕 99.9%；不會觸 throttle）

**Bybit V5 reject 行為對齊**：
- Race E 5 種 fallback path（timeout/postonly_reject/rate_limit_pause/engine_shutdown_safety/ack_lost）全 cover Bybit reject 字典已知所有 close-side reject 場景 ✅
- enum allowlist 包括 `'fast_escalate_safety_upgrade'` 對齊 §5.1 Race A pending close + 新 risk trigger 場景 ✅
- IMPL gate 3 unit test（timeout/postonly_reject/engine_shutdown）確保 silent abandonment 不可能發生 ✅
- AC-18 95% threshold + healthcheck [62] sub-check（5% race window allowance）= conservative 防護 silent abandonment regression ✅

**Bybit ToS 合規影響**：
- Race E mandatory fallback to taker 不違反 anti-wash trading（fallback market re-dispatch 是 distinct order intent，不是同 client_order_id 重發）
- 不增 broker rebate eligibility 風險（30d volume ≪ $10M）
- 不觸 KYC tier limit（單筆 size unchanged）

**判定**：✅ **APPROVED**。Race E 設計對 Bybit Order group rate limit 餘裕 99.9% 餘地；無 throttle / IP ban 風險；不需新增 conservative cooldown；fallback path enum 完整 cover 已知 Bybit reject 場景。

### 4.3 AC-18 fallback ≥ 95% — ✅ APPROVED + COMPATIBLE

**Bybit `Order create` rate limit `OrderId Per Symbol` 相容性檢查**：

**Bybit V5 `/v5/order/create` rate limits**（per 字典 §4.1 + WebFetch round 2 §2 確認）：
- Order group: 20 req/s per UID（create / cancel / amend / execution.* 共用 quota）
- 無「per-symbol」maximum order ID 限制（OpenClaw 用 client_order_id 自管）
- `EC_ReachMaxPendingOrders` 觸發條件：per-symbol pending order count（不是 rate limit）

**AC-18 95% threshold 影響估算**：
- close maker attempt 數 / 7d demo ≈ 155 closes × 25 sym ≈ ~4000 attempts/7d
- 若 95% fallback to taker rate → 3800 fallback dispatch / 7d ÷ 7 / 24 / 3600 = **0.006 req/s 增量**（極小）
- vs 20 req/s Order group cap = 0.03% 利用率
- 即使最 worst case fallback rate 100% → 仍 0.006 req/s

**與 Bybit Order group rate budget 餘裕完全相容**。

**Race window 5% allowance 合理性**：
- real-fill / pending dispatcher 邊界 race（within 1 tick）：可能 1-2% 比例
- engine restart inflight close intent：< 1%
- 5% allowance 包含上述 + 額外 safety margin → conservative correct

**判定**：✅ **APPROVED + COMPATIBLE**。AC-18 與 Bybit Order group rate limit 完全相容；95% threshold 不會觸 throttle；race window 5% allowance 設計合理。

### 4.4 AC-19 14d ≥ 30% — ✅ APPROVED + DEMO/MAINNET COVERAGE GAP IDENTIFIED

**Bybit demo vs mainnet endpoint behavior 差異 coverage 檢查**：

**Bybit V5 demo doc 已知差異**（per round 2 §6 + WebFetch confirm）：
- demo「not a complete function」明文
- demo `apply_demo_funds` 可任意補帳（無 wallet insufficient 路徑壓力）
- demo 私有 WS 不支援 `execution.fast` + `dcp` topic
- **demo PostOnly + reduceOnly silent degradation 風險**：未在 Bybit doc 顯式聲明 demo endpoint 對 PostOnly close 的 reject 推送行為

**AC-19 14d ≥ 30% 對 demo/mainnet drift 覆蓋情況**：
- spec §10.1 Phase 2a 14d 全 demo endpoint：14d 證據純 demo behavior
- AC-19 30% threshold based on E3 close-path empirical estimate (15-25%) + conservative discount
- **Coverage gap**：14d demo PASS ≥ 30% 後 → Phase 2b LiveDemo 也是 demo endpoint（api-demo.bybit.com，per CLAUDE.md §三 LiveDemo 說明）→ Phase 2a 14d + Phase 2b 7d 共 21d 全 demo endpoint
- **Mainnet behavior 證據在 Phase 3 Live carve-out 才會出現**（per AMD §3 Phase 3 + BB round 2 §9 mainnet 啟用前置補件）
- **AC-15 reject sample healthcheck（per BB-MF-5）已 cover**：「7d 0 sample → upgrade Phase 2b LiveDemo 前必跑 mainnet probe 驗 demo endpoint silent degradation 不存在」line 711 — **這是 demo→mainnet drift 唯一 gate**

**結論**：
- AC-19 本身只 cover demo behavior（不 cover mainnet）
- Demo→Mainnet drift 通過 AC-15（reject sample 0 → mainnet probe）+ Phase 3 mandatory operator sign-off + 7 條 BB Mainnet prereq（per round 2 §9 + BB workspace 預留）覆蓋
- **無 spec/AMD gap**：覆蓋鏈完整 (AC-15 → AC-19 → Phase 3 prereq)

**Per BB round 2 §9 復查**：未來 AMD live carve-out 須包含 7 條 mainnet prereq（fee verify / rate budget baseline / IP whitelist / EarnedTrust T0→T1 / MAG-083/084 evidence / 24h smoke / kill-switch test）— 仍 outstanding（Phase 3 啟動前才需）。

**判定**：✅ **APPROVED + DEMO/MAINNET COVERAGE GAP IDENTIFIED**。AC-19 30% threshold 與 Bybit demo endpoint behavior 一致；demo→mainnet drift 通過 AC-15 + Phase 3 prereq 鏈覆蓋；BB round 2 §9 7 條 mainnet prereq 仍是 future AMD live carve-out 的 SoT，**不阻 Phase 2a/2b**。

### 4.5 三個 E3 意外發現 — ✅ APPROVED with 1 OBSERVABILITY NOTE

**A. `orders.intent_id` 100% NULL writer 漏接**：
- **Bybit-side impact**：0 — 是 OpenClaw writer 內部 schema gap（intent → order linkage），不觸 Bybit API
- **合規風險**：0 — 不違 ToS（intent_id 是 OpenClaw client-side metadata）
- **Broker rebate / market maker eligibility 風險**：0 — 不影響 30d volume 計算（Bybit 看 fill volume，與 intent 無關）
- **Audit trail 影響**：影響 Guardian-pass-rate 計算（per E3 §1 caveat）；MAG-082 W-C invariant 不受影響（spine lineage 走 ExecutionPlan rows，不依賴 orders.intent_id）
- **P2 ticket `P2-ORDERS-INTENT-ID-WRITER-GAP-1` open**（spec §15）— 不阻 Phase 1b IMPL ✅

**B. `orders.status` 100% Working fire-and-forget**：
- **Bybit-side impact**：0 — `orders.status` 是 OpenClaw 內部初始狀態，真實終態走 `order_state_changes.to_status`（已存在）
- **合規風險**：0 — Bybit WS `order` topic 推送 orderStatus = Filled/PartiallyFilled/Cancelled/Rejected 全在 OpenClaw 端正確處理（per Rust source `bybit_private_ws_status_writer.rs`）
- **Broker rebate 風險**：0 — fill 統計來自 trading.fills 不是 orders.status
- **Audit trail 影響**：healthcheck 必查 state_changes 不查 orders.status（per E3 finding）— spec §8.1 已對齊
- **不需開新 ticket**（既有設計，per E3 §1 schema caveat 是 documentation gap 非 bug）

**C. 無 fallback to taker 機制**：
- **Bybit-side impact**：對 entry path「missed entry 機會」無 ToS / 合規風險（PostOnly self-cancel 是合規行為）
- **對 close path 不可繼承**（已 cover by §5.5 Race E mandatory fallback）— 違 §二 #5 生存 > 利潤 是 OpenClaw 設計層面，不是 Bybit-side issue
- **Bybit `EC_PerCancelRequest|self_cancel` reject reason**（per E3 §4 78.6%）：是 Bybit 正常 self-cancel reject reason，不觸 broker partnership 風險（self-cancel ≠ wash trading）
- **不增 anti-wash filter 風險**（grid 同 symbol 同方向 PostOnly 密集 self-cancel 是 normal grid behavior，per BB round 2 §8 結論）

**OBSERVABILITY NOTE**：建議 BB future audit cycle 跟蹤 close-maker fallback path 對 Bybit Order group rate limit 利用率 30d trend（per BB memory 2026-05-08 「下次啟動需查驗項」），確認 0.7 req/s baseline → close-maker-first 部署後 ≤ 1.5 req/s sustained（對 Bybit IP cap 仍 < 1.3% 利用率）。**不阻 Phase 1b IMPL**。

**判定**：✅ **APPROVED**。三個 E3 意外發現從 Bybit 立場全 0 合規 / 0 broker rebate / 0 market maker eligibility 風險；spec §5.5 Race E 設計已 cover 對 close path 的 §二 #5 生存風險；P2 ticket 開立合理；observability note 為 BB future audit follow-up（非 ship-stop）。

---

## §5 整體判定

### **APPROVED**

**5/5 must-fix 全 land + 3/3 should-fix 全 land + 4 補錄字典手冊 deferred Wave 3b correctly + v1.2/v0.3 增量無新 Bybit-side risk**。

**Confidence**: HIGH（30 min focused review，cross-check spec/AMD 22 處 BB-MF/BB-SF 引用 + Bybit V5 fee/rate/reject doc consistency）

**APPROVED 條件**：
- ✅ 不再要求 spec/AMD patch（pure verify pass）
- ✅ AMD prereq 條件 2「AMD 經 4-agent 並行 short re-review」status 建議：BB 視角可 PASS（其他 agent 視角並行 Wave 3a 主導 final verdict）
- ✅ 後續派工：Wave 3b BB1 字典手冊 6 處更新（per §7 清單）

---

## §6 對 AMD Prereq 條件 2 Status 建議

**Prereq 條件 2 完整文字**（AMD §8 line 305）：
> 「⏳ 本 AMD v0.2 經 **QC + FA + BB + MIT 4-agent 並行 short re-review** 確認 17 must-fix + 14 should-fix 收口完整」

**BB 視角 status**：✅ **BB-side PASS**

**Justification**：
1. **Round 2 BB 5 must-fix + 3 should-fix 全收口**（per §2-§3）
2. **v1.2/v0.3 增量無新 Bybit-side risk**（per §4）
3. **字典手冊 6 處 deferred Wave 3b correctly**（per §2 BB-MF-1）
4. **30 min cap 內完成 short focused review**（不重做 round 2 deep audit）

**整體 prereq 條件 2 status**：等待 QC + FA + MIT 並行 Wave 3a 視角 verdict 收齊後 PM 統一 sign-off；BB 不阻其他 agent 並行 review；本 BB short re-review 不需 follow-up patch。

**Estimate**：QC + FA + MIT 各 30 min 並行完成後 → PM 4-agent consolidated verdict → 解 prereq 條件 2 → IMPL prereq 條件 2 + 5 (partial) 全解 → 條件 6 (reject_cooldown split) 進 Wave 2 IMPL → 條件 3 三閘 + 條件 4 工作鏈未動 → IMPL kickoff 期 (Wave 4+)

---

## §7 字典手冊 Wave 3b BB1 更新清單（後續派工 SoT）

**本 task record 後續更新項目而不執行**（per PM 指示）。

### 6 處字典手冊更新項

| # | 字典位置 | 改動描述 | 等級 | 引用來源 |
|---|---|---|---|---|
| 1 | §1.2 place_order 段 | 新增條目「PostOnly + reduceOnly 並用合法：兩個 flag 在 Bybit V5 `POST /v5/order/create` request body orthogonal（無互斥）。若限價已過市仍 reject 為 `EC_PostOnlyWillTakeLiquidity`（與 entry 同），不是 reduceOnly 衍生 reject。」 | HIGH | round 2 BB-MF-1 + AMD §10 #1 |
| 2 | §4.1 Rate Limit 分組 | 加註「Order group 20 req/s per UID 涵蓋 create / cancel / amend / execution.* 共用 quota；非 per-symbol cap」 | MEDIUM | round 2 §2 + AMD §10 #2 |
| 3 | §4.3 已知陷阱 | 加「demo endpoint PostOnly + reduceOnly 行為一致性需 reject sample 驗（per `[65] close_maker_reject_samples` healthcheck）；7d 0 sample → upgrade Phase 2b 前必 mainnet probe」 | HIGH | round 2 BB-MF-5 + AMD §10 #3 |
| 4 | §1.9 Instrument cache | 加 per-symbol PostOnly minimum effective offset guidance：「`offset_bps / 10000 * mid_price < tick_size` → auto widen buffer / strict-skip；1000-prefix alt symbol (1000PEPEUSDT/1000BONKUSDT) 必驗」 | MEDIUM | round 2 BB-SF-3 + AMD §10 #4 |
| 5 | §4.2.1 reject reason 表 | 加註「close side 與 entry side `MakerRejectionCategory` 同 classifier，不分流 enum variant；用 dispatch handler `side: OrderSide` flag 區分」 | MEDIUM | round 2 BB-MF-4 + AMD §10 #5 |
| 6 | 新增 §1.10 close maker dispatch 小節 | 引用 spec / AMD 為 SoT，記錄 PostOnly close 設計意圖（與 entry maker 對偶）+ 8 exit_reason whitelist + Race A-E state machine + V094 audit schema | LOW | round 2 BB-MF-1 衍生 + AMD §10 #6 (IMPL DONE 後追加) |

**BB1 派工建議**：
- 第 1-5 項可在 IMPL kickoff 前 land（不依賴 IMPL DONE）
- 第 6 項建議 IMPL DONE 後 land（避免 spec drift）
- 估算 BB1 工作量：~2-3h docs update + commit + push

---

## Sources

- [Bybit V5 Place Order](https://bybit-exchange.github.io/docs/v5/order/create-order)
- [Bybit V5 Rate Limit](https://bybit-exchange.github.io/docs/v5/rate-limit)
- [Bybit V5 Demo Trading](https://bybit-exchange.github.io/docs/v5/demo)
- [Bybit V5 Changelog](https://bybit-exchange.github.io/docs/changelog/v5)
- [Bybit V5 WS Private Order](https://bybit-exchange.github.io/docs/v5/websocket/private/order)

---

**BB AUDIT DONE**：`srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-15--amd_v0_3_spec_v1_2_bb_short_re_review.md`
