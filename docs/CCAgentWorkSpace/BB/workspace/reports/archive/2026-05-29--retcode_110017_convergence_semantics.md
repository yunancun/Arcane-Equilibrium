# BB — retCode 110017 收斂語意安全審查（PHYS-LOCK zero-position close loop 治本修法）

- 日期：2026-05-29
- 角色：BB（Bybit Broker Compatibility Auditor，外部 Bybit 立場）
- 模式：read-only 靜態審計 — 不打真實 API；ssh 僅 read-only（demo_state.json + grep）
- 範圍：PA RCA `2026-05-29--phys_lock_zero_position_close_loop_rca.md` §5 主修（110017 Structural→NoOp + 消費端本地收斂）的 exchange-facing 語意安全性
- 證據分級：[FACT] / [INFERENCE] / [ASSUMPTION]

## VERDICT 摘要

**APPROVE-WITH-MANDATORY-GUARD** — 不可「無條件收到 110017 就本地刪倉」。
PA 主修方向（110017→已平收斂）對本系統正確，但 110017 在 Bybit V5 **不是零倉專屬碼**，必須加 close-intent + reduce-only guard 才能安全。one-way mode 是本系統的關鍵安全前提（已驗），它把多數 corner case 排除，但仍需 defensive guard 防 race + 防未來 mode 漂移。

---

## (1) 110017 = exchange flat 是否可靠？+ corner cases

[FACT 字典] 字典 §4.2 line 1283/1295：110017 = ReduceOnlyReject，明文「(a) 無倉位 / (b) 方向反 / (c) qty > position size」三 trigger，BB 自己於 WP-10 標註「**切勿視為 idempotent silent success**」。
[FACT 官方] Bybit V5 reduce-only doc + error 表交叉確認：110017 retMsg「current position is zero, cannot fix reduce-only order qty」最常見語意 = 「下 reduce-only 時該 contract 無未平倉位」；但 110017 family **不限零倉**，也會在「qty > position size」「hedge mode 方向/positionIdx 不符」回。

**結論：110017 ≠ 可靠地等價於「exchange 端零倉」。** 它是「reduce-only rule not satisfied」族碼。直接「收到 110017 就刪本地倉」**不安全**（誤刪真倉 = 災難）。

corner cases（會在「實際仍有倉」時回 110017）：
- **C-1 [FACT] qty > position size**：本系統全平 form 是 `qty=0 + reduceOnly + closeOnTrigger`（close_sizing.rs），交易所自行 flatten，**不送顯式大 qty → C-1 不適用於本系統全平路徑**。但若未來改送顯式 qty 且 stale（> 實際倉），會撞 110017 而倉仍在 → 此時刪本地倉 = 誤刪。
- **C-2 [FACT] hedge mode positionIdx/方向不符**：hedge mode 下對 buy-side 倉送 sell-side reduce-only 會回 110017 但 buy-side 倉仍在。**本系統 one-way mode（見 §3）→ C-2 當前不適用**，但若帳戶被切 hedge 則此修法會誤刪。
- **C-3 [INFERENCE] 剛成交未結算 race**：理論上「倉剛開、exchange position view 尚未反映」期間送 reduce-only 可能短暫回 110017。實務上本迴圈場景是「倉早已不存在」非「剛開」，但 guard 仍應防此 race（見 §3 guard G-4）。

---

## (2) 對齊 110001 / 110009 是否語意正確？

[FACT code] dispatch.rs:288 `110001 | 110009 => NoOp`。
[FACT 官方語意]
- **110001** = OrderNotFound「Order does not exist」(字典) / 官方亦表述為 order 不存在（可能已成交/已撤）。對 close 而言「要撤/改的單已不在」≈ 等效完成。
- **110009** = 字典寫 PositionNotFound「持倉不存在」；**注意官方 error 表另一版本把 110009 列為「stop orders 超過上限」** — 存在 doc 版本歧義（已記入 §5 follow-up）。本系統 dispatch 註解寫「Order/position not found on a close → 等效成功」，按 PositionNotFound 語意處理。

**對齊判定**：110001（order 不存在）+ 110009（持倉不存在，按本系統採用語意）確實同屬「close 時目標已不在 → 等效已平」族；110017（current position is zero）**核心語意同族**（都指向「沒東西可平」）。**因此 110017→NoOp 在語意方向上正確且自洽**。

**但兩個關鍵差異，使「對齊」不能是無腦複製**：
- **差異 A [FACT]**：現有 NoOp 消費端（dispatch.rs:708-734）**只發 `LeaseOutcome::Consumed` + log，不本地刪倉**。意即 110001/110009 現在落 NoOp 也**不會** positions_remove。所以「110017→NoOp」單獨改 classifier **無法斷迴圈**（NoOp 不刪倉，下 tick 倉仍在重發）。PA 主修的「消費端觸發本地 positions_remove」是**新行為**，不是既有 NoOp 行為 → 這對 110001/110009 也是行為變更，E1/E2 必須意識到此改動會讓三個碼都開始本地刪倉，需確認 110001/110009 既有路徑不會因此 regression。
- **差異 B [FACT]**：110001/110009 語意更「窄」（明確指向 order/position 不存在），110017 語意更「寬」（reduce-only rule 泛化）。**正因 110017 較寬，必須加 guard（§3）才能安全收斂，而 110001/110009 本身較安全。** 不可把 110017 直接放進 `110001 | 110009 => NoOp` 同一 arm 而不加 guard。

---

## (3) 安全收斂 guard 建議（E1 可直接照用）

### 倉位模式判定（治本安全性的地基）

[FACT] **本系統 = Bybit one-way mode**，多重指紋：
1. `OrderDispatchRequest`（tick_pipeline/mod.rs:623）**無 positionIdx 欄位**；order create body（order_manager place_order）**不送 positionIdx**。
2. `switch_position_mode`（position_manager.rs:356，POST /v5/position/switch-mode mode=3 hedge）**0 production caller**（grep 全碼庫無調用）→ 帳戶停在 Bybit 預設 one-way。
3. demo_state.json TRXUSDT `position_idx = None`（非 1/2）。
4. close path side 正確反向：commands.rs:982 `is_long: !is_long`（one-way 下正確；不會方向錯誤觸發 110017）。

[INFERENCE] one-way mode 下，§1 的 corner case C-2（hedge positionIdx 不符）**結構性不存在**；C-1（qty>size）因全平用 qty=0 form **不適用全平路徑**。**這就是為何本修法在本系統可安全**——但安全性「條件依賴於 one-way mode 不變」，必須把此假設變成顯式 guard。

### 安全收斂條件（全部 AND，缺一不收斂）

E1 在「110017 → 本地 positions_remove + pending_close_symbols.remove」前，必須滿足：

- **G-1 [必須] close intent**：僅對 `req.is_close == true` 的 dispatch 收斂。開倉/非平倉方向的 110017 永不刪倉。
- **G-2 [必須] reduce_only == true**：僅對 `reduce_only=Some(true)` 的 close 收斂（本系統 close 必帶 reduceOnly；非 reduce-only 的 110017 不在此語意域）。
- **G-3 [必須] one-way mode 前提守衛**：收斂邏輯註解 + （建議）一個 `debug_assert`/啟動期不變量「positionIdx 未被設為 1/2」。**若未來啟用 hedge mode（switch_position_mode 被接線），本收斂路徑必須先被重新審查**（C-2 會復活，無 positionIdx-aware 比對會誤刪）。建議在 G-3 處留顯式 TODO/guard 註解綁定此前提。
- **G-4 [強烈建議] qty=0-form 限定 OR position-query 確認**：
  - 路徑 a（最小改動，本系統適用）：限定收斂只發生在 **qty=0 全平 form**（close_sizing 的 primary exchange-mode full close）。qty=0 form 下 Bybit 不可能因「qty>size」回 110017（沒有顯式 qty），故 110017 在 qty=0 form 下**可靠等價零倉**。這把 §1 的 C-1 從風險面移除，是最乾淨的 guard。
  - 路徑 b（更保守，可選）：收斂前發一次 `GET /v5/position/list?symbol=X` 確認 size==0 再 remove。**代價**：每次 drift 多 1 Position-group REST（20 r/s cap，用量微不足道）+ 引入額外 race window。**BB 評估：本系統 qty=0 form 已使路徑 a 足夠安全，路徑 b 非必須**；若 E1/E2 對「誤刪真倉」零容忍可採 b 作 defense-in-depth，但會增加複雜度。
- **G-5 [建議] 連發熔斷而非首發即刪（防 C-3 race）**：對同 symbol 同 110017，可設「連續 N 次（如 ≥2）或持續 T 秒（如 ≥3s）後才本地收斂」，避免「剛開倉未結算」單發 race 誤刪。本案場景（倉早已不存在、每秒 1.4 次連發）任何 N≥2 都立即滿足，不影響止迴圈時效，但能擋住理論 race。對齊 PA §5 D3 熔斷思路。

**最小安全集 = G-1 ∧ G-2 ∧ G-4(路徑a)**；G-3 為前提守衛（防未來漂移）；G-5 為 race 防護（建議納入）。

---

## (4) live 安全性

[FACT] 此 classifier 改動對所有 engine_mode（demo / live_demo / live）生效（dispatch.rs 是共用主路徑，無 env 分支）。

- **live 真倉送 close 收到 110017 → 收斂刪倉 = 正確**：若 live 真有倉，送 qty=0 全平 form，Bybit 不會回 110017（會正常成交回 Ok/fill）；只有當 exchange 端確實已無倉（手動平/強平/liquidation）才回 110017，此時刪本地倉 = 對齊真相，正確。
- **誤刪真倉風險面**：唯一能在「live 真倉仍在」時回 110017 的情境是 §1 的 C-1/C-2。G-4(路徑a) 消除 C-1；one-way mode（G-3）消除 C-2 → **在 guard 齊備下，live 誤刪真倉的結構性路徑為空**。
- [INFERENCE] **live-specific 殘餘風險**：liquidation 後本地倉狀態與 exchange 短暫不一致期間若觸發 close，會收到 110017 並收斂刪本地倉——這正是「對齊真相」的期望行為（倉已被強平），非誤刪。
- **硬邊界對齊**：CLAUDE.md §四「Bybit nonzero retCode fails closed；不得為 trading effect 加隱藏 retry」。110017→NoOp **不是加 retry**（NoOp 仍 no-retry，single attempt）；fail-closed 的保護對象是「**開倉**別漏成功」+「**close 別假裝平了其實沒平**」。110017 在 guard 下恰恰證明「倉已不在」→ 收斂是 survival-correct（Root Principle 5），不違反 fail-closed 開倉語意。**BB 背書此判定**，但綁定 §3 全部 guard 成立為條件。

---

## (5) rate-limit / ToS 風險（順帶評估）

[FACT] 當前迴圈 ~1.4 reduce-only create / sec（多執行緒 ThreadId 17/25/26/29 並發）。

- **rate limit**：reduce-only create 走 Order group（20 req/s cap per UID）。1.4 req/s = **7% 利用率**，**不觸發 throttle/ban**。即使乘 4 執行緒峰值瞬時也遠低於 cap。無 IP-level（403/10min cooldown）風險。
- **ToS / broker 行為**：[INFERENCE] 連續失敗下單**不構成 ToS 違規**（非 wash trading：單向 reduce-only、無對敲成交；非 spoofing：非掛撤；非 multi-account）。Bybit 對「無倉 reduce-only reject」是正常拒單回應，不計入異常行為風控。與 2026-05-02/05-08 BUSDT funding_arb 110017 reject loop 同性質（memory line 200-202：「reject loop 是正常拒單行為，非 ToS 違規，是 OpenClaw 該做 retry budget control」）。
- **真實成本**：[FACT/INFERENCE] 無真錢損失（demo + reject 不成交）；但 (a) 污染 demo edge 樣本 / (b) ~27k 110017 噪音 log（PA RCA §6）/ (c) log 膨脹。屬 **resource-burn + observability 污染**，非合規 risk。**BB 風險等級：rate-limit/ToS = 0；治理 = P1（PA 已建議開 ticket）。**

---

## E1 直接照用的「安全收斂條件」（一句話）

> 僅當 `is_close==true` ∧ `reduce_only==true` ∧ qty=0 全平 form ∧（建議）同 symbol 連續 ≥2 次 110017，才在 NoOp 消費端執行本地 `positions_remove` + `pending_close_symbols.remove`；one-way mode 為前提（hedge 啟用須重審）；110017 不可裸放進 `110001|110009` arm，須帶上述 guard 分支。

---

## §5 follow-up（字典 / 治理）

1. **字典 §4.2 110017 row 升級**：現字典標「切勿視為 idempotent silent success」是 WP-10 時對「funding_arb 反覆 reject 應做 retry budget」的正確警告，但**未涵蓋「qty=0 全平 form + one-way + close intent 下可安全收斂」的新語意**。修法 land 後字典需補：「110017 在 one-way + qty=0 reduce-only 全平 form 下可靠等價零倉，可觸發本地收斂；裸 110017（顯式 qty / hedge）仍不可視為 silent success」。避免字典與新 code 行為 drift（SSOT：code 為真）。
2. **110009 doc 版本歧義**：官方 error 表存在「110009 = PositionNotFound」vs「110009 = stop orders 超上限」兩版本表述。本系統 dispatch 採 PositionNotFound 語意。建議 E1/字典確認當前 Bybit V5 對 110009 的權威定義，避免 NoOp 誤吞 stop-order-limit 錯誤（若 110009 真是 stop 上限，落 NoOp 會靜默吞掉一個該 fail 的 SL/TP 設置失敗 — 此為**既有潛在風險**，本次修法不引入但應順查）。
3. **G-3 hedge-mode 前提守衛**：建議在 EX-01 / 字典記錄「one-way mode 是 reduce-only 收斂安全的前提」，若未來策略需 hedge mode，收斂路徑為 mandatory re-review 項。

## Bybit-side overall

- 技術合規度：97%（修法不新增 endpoint / 0 字典結構 drift；僅 retCode 語意分類擴充）
- 政策合規度：unchanged（本修法 0 ToS/KYC/geo/rate-budget 影響）
- 30d changelog：0 breaking change（繼承 2026-05-29 v80 cold audit）
- ship-stop blocker：0（修法為 bug fix，guard 齊備即安全）
- 硬邊界：fail-closed 開倉語意不破壞（BB 背書，綁 §3 guard 條件）

BB AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-29--retcode_110017_convergence_semantics.md
