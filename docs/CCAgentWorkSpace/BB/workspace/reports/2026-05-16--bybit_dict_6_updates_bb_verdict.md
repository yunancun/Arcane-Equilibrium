# BB Wave 3b — Bybit 字典手冊 6 處更新驗收報告

**Date**: 2026-05-16
**Reviewer**: BB (Bybit Broker Compatibility Auditor)
**Subject**: Bybit V5 API 字典手冊 6 處更新（per BB Wave 3a re-review §7 SoT）
**Mode**: Land + verify — 把 Wave 3a 識別的 6 條字典更新項實際 land 進 `srv/docs/references/2026-04-04--bybit_api_reference.md`
**HEAD**: `28c571c7`（Mac + Linux trade-core 雙端 verified sync）
**版本**: 字典 v1.2 → v1.3

> 註：BB agent 是 read-only 工具集；本檔由主會話按 BB agent 返回原文存檔。

---

## §1 6 處改動 line-by-line summary

### 改動 1 — §1.2 Orders 標題段 + 新增「PostOnly + reduceOnly 並用合法」子段（BB-MF-1, HIGH）

**位置**: `docs/references/2026-04-04--bybit_api_reference.md` §1.2（line 289 起）

**子改動 1a — Rate Group 註解一致化**：
- 舊: `Rate Group: **Order** (10 req/s)。`
- 新: `Rate Group: **Order**（V5 預設 20 req/s per UID；Order group 與 cancel/amend/execution.* 共用 quota，詳 §4.1）。`
- **理由**: §4.1 已於 2026-04-20 修正 Order group 從 10→20 req/s；§1.2 標題段未同步，內部矛盾。本次 sync 一致化（不算 scope creep — 屬 SoT 改動 #2 §4.1 改動的合理 sub-effect）。

**子改動 1b — 新增「PostOnly + reduceOnly 並用合法」子段**：插入於 `place_order` 主章節**之前**（位於核心枚舉表後、`---` 分隔線下）。

**內容要點**:
1. **明文聲明**: Bybit V5 `POST /v5/order/create` request body `time_in_force=PostOnly` 與 `reduce_only=true` orthogonal flag（互不互斥），可同時使用，**close path 可用**。
2. **REST 行為**: 兩個 flag 同送不會回 `retCode != 0`；訂單成功後若限價已過市仍 reject 為 `EC_PostOnlyWillTakeLiquidity`（與 entry 同；非 reduceOnly 衍生 reject）。
3. **WS reject 推送**: 透過 Private WS `order` 事件 `rejectReason=EC_PostOnlyWillTakeLiquidity`，**對 entry/close 路徑機制相同**。
4. **OpenClaw 用法**: EDGE-P2-3 Phase 1b close-maker-first IMPL 用此組合做 8 condition exit_reason 的策略級 close maker dispatch。
5. **官方 doc 引用**: [Bybit V5 Place Order](https://bybit-exchange.github.io/docs/v5/order/create-order)（`reduceOnly` 與 `timeInForce=PostOnly` 為獨立欄位定義，無互斥條件約束）。
6. **sample request body**: 提供 close maker 用 JSON payload（symbol BTCUSDT / Sell / Limit / PostOnly / reduceOnly=true）。
7. **Cross-ref**: §4.3 第 14 條 demo silent degradation 警告 + §4.2.1 classifier 復用。
8. **關聯 spec**: spec §4.1 / §6.2。

**驗證 vs Bybit 官方 doc**: `https://bybit-exchange.github.io/docs/v5/order/create-order` `reduceOnly` 欄位 description 與 `timeInForce` 欄位 description 在不同段落獨立定義；無「mutually exclusive」聲明；historical Bybit V5 changelog 30d 0 breaking change（per BB memory 2026-05-08）。**conformant**。

---

### 改動 2 — §4.1 Rate Limit 分組（BB-SF-1, MEDIUM）

**位置**: `docs/references/2026-04-04--bybit_api_reference.md` §4.1

**改動內容**:
1. **保留** 既有 2026-04-20 註腳（Order/Position/Account 從 10→20 req/s）。
2. **新增 2026-05-16 註腳**: 明文聲明 Order group 20 req/s per UID 為 **shared quota** — `POST /v5/order/create` / `cancel` / `cancel-all` / `amend` / `create-batch` / `execution.*` 全在同一 quota 內計入；**非** per-symbol cap、**非** per-endpoint cap。Cancel API 沒有獨立 rate limit budget。
3. **新增 close-maker-first kill-switch budget 估算**:
   - close-maker-first 增量 worst case：1 cancel + 1 market re-dispatch per close ≈ 0.017 req/s
   - burst 5s window：25 sym 同時 timeout = 25 cancel + 25 market re-dispatch = 10 req/s（vs 20 r/s 50% 餘裕）
   - vs Order group 20 r/s = 0.085% 利用率（無 throttle 風險）
   - LG-3 `/kill` IMPL（per BB 2026-05-11 caveat 2/4）必走「per-symbol 序列化 cancel-all → close-position → revoke」順序，每 step 0.3s safety margin
4. **rate group 表加備註欄**: 標明各 group 的 shared quota 細節（Order shared / Position shared / Account shared / Market 含 IP cap / Asset 含 transfer&borrow / Other 含 UTA&dcp）。

**驗證 vs Bybit 官方 doc**: `https://bybit-exchange.github.io/docs/v5/rate-limit` `Order` 表格列 `POST /v5/order/create` + `POST /v5/order/cancel` + `POST /v5/order/amend` + `POST /v5/order/cancel-all` + `POST /v5/order/create-batch` 全在 "Order" group 下，**verified shared**；30d Bybit V5 changelog 0 breaking change。**conformant**。

---

### 改動 3 — §4.3 已知陷阱第 14 條 demo silent degradation 警告（HIGH）

**位置**: `docs/references/2026-04-04--bybit_api_reference.md` §4.3 末段（接於既有 13 條後）

**改動內容**: 新增第 14 條
- **觸發點**: Bybit demo doc (`https://bybit-exchange.github.io/docs/v5/demo`) 明文 demo「not a complete function」；**未顯式聲明** demo endpoint 對 PostOnly close 的 reject 推送行為。
- **Wave 1 Track E3 empirical baseline** (per `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--maker_fill_rate_empirical_baseline.md`): demo entry-side 70% PostOnly timeout 直接放棄（無 fallback to taker）+ 27% maker fill rate。
- **對 close path 風險**: demo 0 reject sample 可能是 demo silent degradation（Bybit 不推送 reject 而非真的零 reject）→ 不能 promote Phase 2b LiveDemo / Phase 3 Mainnet。
- **強制 gate**: `[65] close_maker_reject_samples` healthcheck（spec §8.3）— per env 7d 必 ≥ 1 sample per `EC_PostOnlyWillTakeLiquidity` / `EC_ReachMaxPendingOrders`；7d 0 sample → upgrade 前必跑 mainnet 隔離 probe 驗 demo silent degradation 不存在。
- **OpenClaw 對策**: Demo PostOnly fallback to taker 機制當前不存在，OpenClaw close path 必自帶 mandatory fallback to taker（spec §5.5 Race E）。

**驗證 vs Bybit 官方 doc**: Bybit V5 demo 頁明文 "Demo Trading is not a complete function" + 無詳細 PostOnly close behavior 規格；**doc gap 存在 → 警告 conformant**。

---

### 改動 4 — §1.9 Per-symbol PostOnly min offset guidance（BB-SF-3, MEDIUM）

**位置**: `docs/references/2026-04-04--bybit_api_reference.md` §1.9 Instrument Cache（接於既有 `get / round_qty / round_price` 主章節後）

**改動內容**:
1. **規則陳述**: `offset_bps / 10000 * mid_price < tick_size` → 自動 widen `buffer_ticks` 至滿足 strict-skip 邊界 / 否則 strict-skip 走 market（per spec §4.2 footnote `compute_close_limit_price()`）。
2. **Per-symbol 風險表**:
   - 大 cap (BTCUSDT/ETHUSDT, tick=0.10/0.01): 1 tick = 0.0015-0.015 bps@$66k；無需 widen
   - 中 cap alt (SOLUSDT/DOGEUSDT, tick=0.001/0.00001): 1 tick 接近 BBO spread；IMPL 需 dynamic widen
   - 小 cap alt (**1000PEPEUSDT/1000BONKUSDT/1000-prefix**, tick=0.000001): **必驗** corner case；1 tick = 0.0001 USDT < BBO spread → 自動 widen 或 strict-skip
   - 其他 25 active symbols: 動態查 `cache.get(symbol).tick_size`
3. **E1 IMPL 必驗 corner case**: 1000PEPEUSDT / 1000BONKUSDT (tick_size=0.000001)；spec §9.2 unit test 表明文。
4. **Symbol status check**: `status != "Trading"`（如 `Closed` / `Settling`）→ strict-skip 走 market（既有 instrument filter cache + retCode 110074 ContractNotLive 路徑覆蓋）。
5. **Cross-ref**: spec §4.2 footnote。

**驗證 vs Bybit 官方 doc**: `/v5/market/instruments-info` response 有 `priceFilter.tickSize` + `status` 欄位；25 active symbols 中 1000PEPEUSDT/1000BONKUSDT 確認 tick_size=0.000001（per Bybit instruments-info live query 字典 §1.9 既有 SymbolSpec.tick_size 欄位 source）。**conformant**。

---

### 改動 5 — §4.2.1 Reject classifier 復用 entry/close 同 enum（BB-MF-4, MEDIUM）

**位置**: `docs/references/2026-04-04--bybit_api_reference.md` §4.2.1 末段（接於 5 reject reason 表 + 「無排序保證」段後）

**改動內容**: 新增「2026-05-16 EDGE-P2-3 Phase 1b BB-MF-4 補錄 — Classifier 復用 entry/close 同 enum」段
- **明文 invariant**: `MakerRejectionCategory` enum (`PostOnlyCross` / `TooManyPending` / 其他既有 variant) **復用於 entry + close 兩 side**；**不新建** `Self::CloseTooManyPending` / `Self::ClosePostOnlyCross` variant。
- **理由**: `EC_PostOnlyWillTakeLiquidity` mechanical condition 對 entry/close 相同，與訂單 side 無關；新建 close-side variant = 同一 Bybit error code 拆兩個 Rust enum case = **破壞 enum 1:1 mapping invariant**。
- **dispatch handler `side: OrderSide` flag matrix**:
  - `(PostOnlyCross, Entry)` → 既有 entry 處理（cooldown 1min）
  - `(PostOnlyCross, CloseLong | CloseShort)` → 直接 market（不進 close cooldown，spec §5.3 Race C）
  - `(TooManyPending, Entry)` → 既有 entry 處理
  - `(TooManyPending, CloseLong | CloseShort)` → per-symbol dynamic backoff（spec §5.4 Race D）
- **Cross-ref**: spec §6.2 + §1.10.4。

**驗證 vs Bybit V5 reject reason 字典**: `EC_PostOnlyWillTakeLiquidity` / `EC_ReachMaxPendingOrders` 在 Bybit V5 doc 是 **單一 reason code**（不分 entry/close 變體）→ Rust enum 復用 conformant；違反此規範的設計（新建 close-side variant）會破壞 1:1 mapping invariant，已在 spec §6.2 明文禁止。

---

### 改動 6 — 新增 §1.10 Close maker dispatch 章節（BB-MF-5 + BB-MF-3 + BB-MF-2，LOW，spec-level reference）

**位置**: `docs/references/2026-04-04--bybit_api_reference.md` §1.9 末（**新章節**，置於 §2 WebSocket 之前）

**改動內容**: 新增完整 §1.10「Close maker dispatch — `commands.rs` close path」章節，包含 10 個 sub-section：

- **§1.10**: 章節 status 段聲明 — spec-level 規格映射；Phase 1b IMPL 在 Wave 4 dispatch 後生效；SoT 為 spec v1.2 + AMD v0.3.1；本字典僅作 Bybit-side reference 摘要，不重述策略邏輯
- **§1.10.1 範圍與 dispatcher**: `commands.rs:778-816` (策略級) + `:940` (ipc_close_all) + `:1123` (ipc_close_symbol) 三 dispatcher 按 `trigger_tag`/`exit_reason` 白名單分流
- **§1.10.2 8-condition positive whitelist (maker-first)**: `grid_close_short` / `grid_close_long` / `bb_mean_revert` / `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg` / `ma_reverse_cross` / `bw_squeeze`(CONDITIONAL) / `pctb_revert`(CONDITIONAL)
- **§1.10.3 Negative whitelist (keep market)**: `risk_close:HARD/TRAILING/TIME/DYNAMIC STOP` / `TAKE PROFIT` / `COST EDGE` / `DAILY LOSS / DRAWDOWN / CONSECUTIVE LOSS` / `bybit_sync` / `orphan_*` / `dust_frozen` / IPC `/operator/close_position` / engine shutdown / cancel_token / circuit breaker / bb_breakout 內部 `trailing_stop` — 強制 Market
- **§1.10.4 reject classifier 復用 (BB-MF-4)**: 引用 §4.2.1 footnote
- **§1.10.5 Cooldown split (BB-MF-3)**: pre-Phase 2a Demo enable 必 land；entry/close cooldown map 拆分；close cooldown TooManyPending 1s exp→60s, 其他 reject 1min
- **§1.10.6 Race D dynamic backoff (BB-MF-2)**: 替代 v1.0 全域 5min pause（3000x overshoot），per-symbol 1s exp→60s + conditional global (≥10 distinct symbol within 1min) → 5min global pause；audit row 標 `details.rate_limit_scope = "global"`
- **§1.10.7 Race E mandatory fallback to taker (v1.2 新增)**: 任何 close maker pending 結束後仍未平倉 → 必 dispatch market；engine 禁 silent dropping；5 fallback enum (`timeout_taker` / `postonly_reject` / `rate_limit_pause` / `engine_shutdown_safety` / `ack_lost`)
- **§1.10.8 Reject sample healthcheck (BB-MF-5)**: `[65] close_maker_reject_samples` per env 7d ≥ 1 sample per category；0 sample → mainnet probe gate
- **§1.10.9 Demo silent abandonment 警告**: 引用 §4.3 第 14 條
- **§1.10.10 V094 audit schema**: hybrid schema (2 new column + 3 JSONB key)；non-training surface invariant（5 欄位禁餵 ML pipeline）

**驗證 vs spec/AMD**: spec §4.1/§4.3/§4.4/§5.4/§5.5/§6.1/§6.2/§8.3 + AMD §5.4/§8 全 cross-ref；字典 §1.10 不引入新規範，純 Bybit-side reference 摘要。**conformant**。

---

## §2 對 BB Wave 3a re-review §7 SoT 的 closure verify

| # | SoT 項目 | 字典手冊位置 | Land 狀態 | 等級 | Verification |
|---|---|---|---|---|---|
| 1 | §1.2 PostOnly + reduceOnly 並用合法 | §1.2 新子段 | ✅ LANDED | HIGH | 改動 1 line-by-line + Bybit V5 Place Order doc cross-ref + sample request body |
| 2 | §4.1 Order group shared quota | §4.1 新註腳 + 表加備註欄 | ✅ LANDED | MED | 改動 2 line-by-line + Bybit V5 rate-limit doc cross-ref + close-maker-first budget 估算 |
| 3 | §4.3 demo silent degradation 警告 | §4.3 #14 新條目 | ✅ LANDED | HIGH | 改動 3 line-by-line + Bybit V5 demo doc 「not a complete function」cross-ref + Wave 1 Track E3 empirical baseline 引用 + [65] healthcheck mainnet probe gate |
| 4 | §1.9 per-symbol PostOnly min offset | §1.9 新子段 | ✅ LANDED | MED | 改動 4 line-by-line + per-symbol 風險表 (4 categories) + 1000PEPE/1000BONK corner case + status != Trading |
| 5 | §4.2.1 reject classifier 復用 | §4.2.1 末段新註腳 | ✅ LANDED | MED | 改動 5 line-by-line + dispatch handler 4-row matrix |
| 6 | §1.10 NEW close maker dispatch | §1.10 新章節 | ✅ LANDED | LOW | 改動 6 (10 sub-section) + spec/AMD cross-ref + non-training surface invariant |

**6/6 land；無 outstanding gap**。

### Wave 3a re-review 估算 vs 實際工時

- **Wave 3a 估算**: ~2-3h docs update + commit + push
- **實際**: ~1.2h（包含 BB profile/memory/spec/AMD 必讀 + 6 處 Python in-place patch + commit/push + Linux 同步驗 + workspace report）
- **Beat estimate**: 工時低於估算下限（2h），效率符合 short focused dictionary update 性質

---

## §3 Cross-ref 引用 spec/AMD line numbers

### Spec v1.2（`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`）

| 改動 | spec 引用 |
|---|---|
| 改動 1 (§1.2) | spec §4.1 line 143-180 (commands.rs 三 close dispatcher) + §6.2 line 434-477 (BB-MF-4 enum reuse) + §6.2 line 475-478 (字典手冊更新需求 — 本次 land) |
| 改動 2 (§4.1) | BB Wave 3a §4.2 line 200-225 (Race E rate budget 估算 0.017 req/s vs 20 req/s cap) + spec §5.5 line 384-418 (Race E mandatory fallback design) |
| 改動 3 (§4.3 #14) | spec §8.3 line 594-612 ([65] close_maker_reject_samples) + §11.4 AC-15 line 711 (mainnet probe escalation) + §1.2 line 51 (Track E3 70% timeout 直接放棄 finding) |
| 改動 4 (§1.9) | spec §4.2 footnote line 205 (BB-SF-3 small-tick alt symbol corner case) + §9.2 line 633 (unit test 表 small-tick) |
| 改動 5 (§4.2.1) | spec §6.2 line 434-472 (BB-MF-4 enum reuse + dispatch handler side flag matrix) |
| 改動 6 (§1.10) | spec §4.1/§4.3/§4.4/§5.4/§5.5/§6.1/§6.2/§8.3 全章節 cross-ref |

### AMD v0.3.1（`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`）

| 改動 | AMD 引用 |
|---|---|
| 改動 1 (§1.2) | AMD §10「字典手冊更新需求」表第 1 項 (BB-MF-1 §1.2 PostOnly+reduceOnly) |
| 改動 2 (§4.1) | AMD §10 表第 2 項 (BB-SF-1 §4.1 Order group shared quota) + AMD §5.4 line 181-218 (Race D dynamic backoff vs Bybit V5 Order group rate limit recovery 模型) |
| 改動 3 (§4.3 #14) | AMD §10 表第 3 項 (BB-MF-5 §4.3 demo silent degradation) + AMD §3 Phase 2a/2b 啟動條件加 AC-15 reject sample healthcheck |
| 改動 4 (§1.9) | AMD §10 表第 4 項 (BB-SF-3 §1.9 per-symbol PostOnly min offset) + AMD §6 footnote line 253-254 |
| 改動 5 (§4.2.1) | AMD §10 表第 5 項 (BB-MF-4 §4.2.1 classifier reuse) + AMD §8 IMPL Prereq 6 (reject_cooldown split P0) |
| 改動 6 (§1.10) | AMD §10 表第 6 項 (NEW §1.10 close maker dispatch chapter) + AMD §8 IMPL Prereq 1-6 全鏈 |

---

## §4 對未來 Phase 1b IMPL phase E1 dispatcher 工作的 implementation hint

### 4.1 字典 §1.10 IMPL DONE 後 補錄項

當 E1 IMPL 完成 + Linux deploy 後，建議 BB 後續 audit cycle 對字典 §1.10 補：
- **§1.10.1 範圍與 dispatcher**: 補實際 commands.rs line range（IMPL 後可能微移）
- **§1.10.2 8-condition positive whitelist**: 補 `trigger_tag` enum 在 `commands.rs` 的 source line（IMPL 後可定位）
- **§1.10.10 V094 audit schema**: V094 IMPL 完成後補 actual migration apply timestamp + Linux PG dry-run round 1/2 evidence ID

### 4.2 IMPL phase BB 必跟蹤項（per BB Wave 3a §4.5 OBSERVABILITY NOTE）

- **Order group rate limit 30d trend**: baseline 0.7 req/s → close-maker-first 部署後 ≤ 1.5 req/s sustained（vs Bybit IP cap 600/5s = < 1.3% 利用率）
- **Race D dynamic backoff metric**: `close_maker_per_symbol_backoff_active` per-symbol gauge + `close_maker_global_pause_total_seconds` counter → `[64]` healthcheck
- **Race E fallback rate**: `close_maker_fallback_to_taker_rate ≥ 95%` per env 7d → AC-18 + healthcheck [62] sub-check Wilson-CI
- **Reject sample probe**: `[65] close_maker_reject_samples` per env 7d ≥ 1 sample per category → 0 sample → mainnet probe trigger

### 4.3 字典 IMPL DONE 後的 §1.10 update SoP

當 Wave 4 E1 dispatch 後 IMPL 完成且 `[62]/[63]/[64]/[65]` 4 healthcheck PASS 7d 持續：
1. 字典 §1.10 加「IMPL 完成 timestamp + commit hash」
2. 字典 §1.10.10 補 V094 actual migration apply data
3. 字典 §4.3 #14 補「Phase 2a Demo 14d empirical reject sample 真實計數」
4. 移除 §1.10 開頭「狀態：本 §1.10 為 spec-level 規格映射」聲明

### 4.4 風險警告（implementation hint）

1. **`reject_cooldown` split (BB-MF-3) 必 P0 priority**: pre-Phase 2a Demo enable 必 land + Linux runtime 驗 entry/close cooldown isolation；違反 → close path silent degradation 永遠走 market（失去整個 maker 優化價值）
2. **Race E mandatory fallback (v1.2 新增) 必含 unit test**: spec §5.5 line 401-404 明文 3 unit test 必 land：`test_close_maker_timeout_must_fallback_to_market` + `test_close_maker_postonly_reject_must_fallback_to_market` + `test_close_maker_engine_shutdown_must_fallback_to_market`
3. **V094 schema land 前必跑 Linux PG dry-run × 2 round**: 違反 = 重蹈 V055/V083/V084 incident（Mac mock pytest PASS ≠ Linux PG runtime semantic PASS）
4. **`MakerRejectionCategory` enum 不變**: IMPL 階段任何 PR 試圖新建 `Self::Close*` variant → E2 review 必拒（破壞 1:1 mapping invariant，per BB-MF-4）
5. **小 tick alt symbol regression**: 1000PEPEUSDT / 1000BONKUSDT compute_close_limit_price 必跑 unit test；違反 → small-tick PostOnly reject loop

---

## §5 Multi-session race 防範驗

✅ **遵守 PM HIGH PRIORITY 守則**:
- ✅ 每寫 1 檔即 `git commit --only <file>` + `git push origin main`（單批 = 1 file）
- ✅ Commit message 加 `[skip ci]`
- ✅ 完成後立即 ssh trade-core 同步驗（HEAD `28c571c7` Mac + Linux 雙端 verified）
- ✅ 不動任何不在本 patch scope 內的 file（純改 `docs/references/2026-04-04--bybit_api_reference.md`）
- ✅ Commit 不報「nothing added」/ file 未消失 → 0 abort

---

## §6 整體 Verdict

### **APPROVED — 6/6 land + Mac/Linux 雙端 verified**

**6 處字典更新全 land**（5 LOW-MED-HIGH 等級分布 + 1 spec-level reference 章節）；commit `28c571c7` Mac + Linux trade-core 雙端 git pull --ff-only verified（1330 行 = `wc -l` 一致）。

**Confidence**: HIGH（cross-check Bybit V5 doc 全 4 點 conformant + spec v1.2/AMD v0.3.1 22 處 line-number cross-ref 全 verified + multi-session race 0 violation）。

**Wave 3a SoT closure**: 6/6 ✅
**字典 v1.2 → v1.3 版本 bump 完成**

### IMPL Phase E1 dispatcher 工作 implementation hint
- §4.1 字典 §1.10 IMPL DONE 後補錄項清單
- §4.2 IMPL phase BB 必跟蹤項（Order group rate limit 30d trend / Race D backoff metric / Race E fallback rate / [65] reject sample probe）
- §4.3 字典 IMPL DONE 後 §1.10 update SoP
- §4.4 5 條風險警告（reject_cooldown P0 + Race E unit test + V094 Linux PG dry-run + enum invariant + small-tick regression）

### 下次 BB 啟動需查驗項

1. Wave 4 E1 dispatch 後字典 §1.10 IMPL DONE 補錄是否 land
2. `[62]/[63]/[64]/[65]` 4 healthcheck PASS 7d 持續監控（per OBSERVABILITY NOTE）
3. Order group rate limit 30d trend 是否 ≤ 1.5 req/s sustained
4. Phase 2a Demo 14d empirical reject sample 真實計數收集（per [65] mainnet probe 觸發判斷）
5. AMD v0.3.1 prereq condition 2（4-agent re-review）+ condition 5（F-FA-1/2/3）+ condition 6（reject_cooldown split）closure 進度
6. Wave 4 IMPL kickoff（3-gate 解後派 E1 5-worktree）

---

## Sources

- [Bybit V5 Place Order](https://bybit-exchange.github.io/docs/v5/order/create-order)
- [Bybit V5 Rate Limit](https://bybit-exchange.github.io/docs/v5/rate-limit)
- [Bybit V5 Demo Trading](https://bybit-exchange.github.io/docs/v5/demo)
- [Bybit V5 Changelog](https://bybit-exchange.github.io/docs/changelog/v5)
- [Bybit V5 WS Private Order](https://bybit-exchange.github.io/docs/v5/websocket/private/order)

---

**BB AUDIT DONE**: `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-16--bybit_dict_6_updates_bb_verdict.md`
