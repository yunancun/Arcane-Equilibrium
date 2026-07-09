# BB — D2 position_reconciler Ghost = exchange-truth 信任邊界審查

- 日期：2026-05-29
- 角色：BB（Bybit Broker Compatibility Auditor，外部 Bybit 立場）
- 模式：read-only 靜態審計 — 不打真實 API
- 範圍：Track C `P2-110017-D2-RECONCILE`（worktree `wt-c-d2`，branch `fix/retcode-110017-d2-reconcile`）
- 對照：`docs/references/2026-04-04--bybit_api_reference.md` §get_positions + Bybit V5 官方 position API doc
- 證據分級：[FACT] / [INFERENCE] / [ASSUMPTION]

## VERDICT：RETURN（1 CRITICAL exchange-truth 缺陷，必修才能 ship）

D2 的 `process_ghosts` 收斂邏輯本身（streak / mirror / no-CloseSymbol / fail-closed-on-fetch-error）設計乾淨、測試紮實。
**但 D2 與 D1 的安全地基根本不同**：D1 靠「qty=0 全平 form 撞 110017 = 交易所自證倉已不在」；
D2 拋棄了該自證信號，改為**純粹相信 reconciler 一次 `/v5/position/list` fetch 的完整性**來判 Ghost → 刪本地倉。
而該 fetch **不完整**：單頁、default limit=20、丟棄 `nextPageCursor`，universe 上限 40 symbol。
這是一條結構性「交易所有真倉但被當 Ghost 誤刪」的路徑，且**對 live 真錢生效**。streak + fail-closed **擋不住**此缺陷
（截斷是穩態、非抖動，連續 N cycle 都截斷）。

---

## (1) Ghost = exchange 真無倉 可靠嗎？+ 分頁/filter 陷阱

### (1a) size==0 判定本身 — 可靠 ✅
[FACT code] `position_info_to_view`（mod.rs:206）：`size<=0 || side=="None"` → None；`classify`（mod.rs:164）`(Some(baseline), None) => Ghost`。
[FACT 官方] Bybit V5 `/v5/position/list` 回的 `side="None"` 或 `size=0` 確實代表該 (symbol, positionIdx) 槽位無倉。
→ **若該 symbol 真的出現在 fetch 回應裡且 size==0，判 Ghost 在語意上可靠。**

### (1b) ★ CRITICAL — 分頁截斷陷阱「不在回應 ≠ size==0」
[FACT code] Ghost 不只在「size==0」觸發，更在「**該 symbol 完全不在 `current` map**」觸發
（mod.rs:307-313 取 baseline∪current key 聯集，`current.get(key)=None` → classify → Ghost）。
即 **「沒查到」與「查到 size==0」走同一條 Ghost 路徑** — 這正是 prompt 點名的陷阱，且**成立**。

[FACT code] fetch 完整性缺陷三連：
1. `fetch_current_view`（mod.rs:278）→ `get_positions(OrderCategory::Linear, None)`。
2. `get_positions`（position_manager.rs:158-178）：`None` symbol → 加 `settleCoin=USDT`，**單次** `get_checked`，**無 cursor 迴圈、無顯式 limit**。
3. `parse_position_list`（position_manager.rs:545）：**只讀 `result.list`，完全忽略 `nextPageCursor`**。

[FACT 官方 Bybit V5 position doc] `GET /v5/position/list`：
- `limit` 範圍 [1,200]，**default = 20**；
- 回應**分頁**，含 `nextPageCursor`；
- `symbol=null + settleCoin` 時「returns position size greater than zero」（只回有倉的，可被分頁截斷）。

[FACT config] `settings/risk_control_rules/scanner_config.toml`：`[universe] max_symbols = 40`（25 pinned + 15 dynamic）。

[INFERENCE — CRITICAL] 帳戶同時持倉 > 20 個 USDT-linear symbol 時：
page 1 只回前 20 個（Bybit 按 updatedTime 排序），**第 21+ 個真倉不在回應 → `current` 缺該 key → 判 Ghost**。
D2 在 streak 滿足後 → `dispatch_ghost_converge` → `converge_exchange_zero_close` → **positions_remove 真倉**。
本地以為已平、不再對其平倉/止損 → **裸露的交易所真倉無本地止損守護（違 Root Principle 5/9）**。

**為何此缺陷在 D1 不存在、在 D2 才致命**：D1 收斂的觸發是「我主動送 close → Bybit 回 110017」，
交易所**主動針對該 symbol** 給出「無倉」信號，不依賴列舉完整性。
D2 收斂的觸發是「該 symbol 不在我抓的那頁」— 把「列舉完整性」變成 silent 安全前提，而該前提被 limit=20 打破。

**為何 streak/fail-closed 擋不住**：分頁截斷是**穩態**（只要持倉數 > 20，每輪都截掉同一批尾端 symbol），
不是 fetch 抖動。連續 2、3、N cycle 都會把同一個第 21+ symbol 判 Ghost → streak 必然滿足 → 收斂。
fail-closed 只在 `Err` arm（REST 整個失敗）生效；截斷回的是 `Ok(20 條)`，**走 happy path，fail-closed 不觸發**。

### (1c) one-way vs hedge — 當前安全，但前提守衛已就位
[FACT] 本系統 one-way mode（D1 報告 §3 多重指紋；switch_position_mode 0 production caller；order create 不送 positionIdx）。
[FACT code] D2 註解（mod.rs:737-739）已明列 hedge 啟用須 MANDATORY re-review，`key()` 用 `symbol|side` 已 hedge-aware。
[INFERENCE] one-way 下每 symbol 單 side，hedge 多 positionIdx entry 場景不存在 → 1c 當前不增風險。**G-3 守衛已對齊 D1，APPROVE。**

---

## (2) 2-cycle streak 拍板：≥2 正確且該 mandatory，但**非 C-3 的充分防護**

[拍板] **2 cycle 是合理下限，維持 mandatory（缺一不可），不需加碼到 3+。**

[INFERENCE Bybit 結算延遲] 開倉成交後 position 進 `/v5/position/list` 通常 <1s（execution → position WS 與 REST 近即時）；
C-3「剛開倉、position view 尚未反映」窗口在 perp linear 上是亞秒級，極少跨越 30s reconcile cycle 邊界。
→ 2 cycle（≥30s，實測週期）已遠超結算延遲時間尺度，對 C-3（暫態 size==0）**綽綽有餘**；3+ 只增收斂延遲無實益。

[但必須澄清 streak 的能力邊界] 2-cycle streak 防的是**暫態抖動**（單 cycle 偶發 size==0 / 偶發 fetch 缺漏）。
它**防不住穩態錯誤**——即 (1b) 的分頁截斷，與「API 持續性結算延遲/長時抖動」。
**不要把 streak 當成 (1b) 的補償**：streak 對「每輪都截斷同一 symbol」零作用。這是 RETURN 的核心理由。

---

## (3) live 誤刪防護：**不足**（因 1b）

[FACT code] reconciler 對 Mainnet|LiveDemo 也 spawn（tasks.rs:860-864，`reconciler_label` 映射 live）→ D2 收斂跑 live 真倉。
[FACT code] paper 不 spawn reconciler；即使到達，`converge_exchange_zero_close` 內 `is_exchange()` 二重守衛回 noop（mirror D1）。

逐項：
- **暫態 API 抖動 / 短暫 size==0**：2-cycle streak + fail-closed（Err arm 保留 baseline 不刪）→ **足夠**。✅
- **穩態分頁截斷（持倉 > 20）**：streak/fail-closed **無效**（見 (2)）→ **live 真倉被誤刪的結構性路徑開啟**。❌
- 結論：在當前 universe（max 40）下，**只要 live 同時持倉 > 20 symbol，就有真錢倉被靜默刪除 + 失去本地止損的路徑**。
  即使現階段 live allowed_symbols 受限（demo BTCUSDT/ETHUSDT），D2 是 env-agnostic 共用碼，universe 一旦放開即觸發；
  不可靠「現在持倉少」作為 ship 理由（fail-loud / survival-first 原則要求結構安全，非偶然安全）。

---

## (4) rate-limit：0 額外負擔 ✅

[FACT code] `process_ghosts` 復用 `reconcile_once` 已抓的 `current`（`drifts` 是分類產物），**不發任何新 REST**。
收斂走 IPC `PipelineCommand::ConvergeExchangeZero`（engine 內部 channel）→ `positions_remove`，**0 Bybit API call**。
[FACT] reconciler 既有 `/v5/position/list` 每 30s 一次 = 0.033 req/s，Position group 20 r/s cap = 0.17% 利用率。
D2 增量 = **0 req/s**。rate-limit / ToS / broker 行為 = **0 風險**。✅

---

## 修復條件（RETURN → APPROVE 的最小集）

**MUST（解除 RETURN）— 修復 fetch 完整性，二擇一：**
- **修法 A（推薦，最小且最安全）**：`process_ghosts` 收斂前，對每個候選 Ghost symbol 發
  `get_positions(Linear, Some(symbol))` 單 symbol 確認 size==0 再刪。
  - 單 symbol query 不受 limit=20 截斷（精準命中）→ 結構性消除 (1b)。
  - 成本：每個 Ghost 候選 +1 Position-group REST。Ghost 罕見（drift 才有）→ 增量 ≈ 0；即使 burst 也遠 < 20 r/s。
  - 對齊 D1 報告 §3 G-4 路徑 b 的 defense-in-depth 思路，且把「列舉完整性」換成「點查確定性」。
- **修法 B（治本但較大）**：`get_positions` 加 `nextPageCursor` 分頁迴圈 + 顯式 `limit=200`，使 `current` 真正列舉全部持倉。
  - 治本所有依賴 `get_positions(None)` 完整性的 caller（reconciler baseline、orphan 判定亦受惠）。
  - 成本：持倉 ≤200 時仍單頁（limit=200 涵蓋 universe 40）→ 實務上 1 次 REST，0 額外 round-trip；> 200 才翻頁。
  - **BB 偏好修法 B**：它同時修掉 reconciler 既有的 Orphan/baseline 完整性盲區（非 D2 引入但同根），SSOT 更乾淨。

**SHOULD：**
- 新增一條 test：構造「baseline 有 symbol、current（截斷頁）缺該 symbol」→ 驗證修法後**不**收斂 / 或先點查確認。
  當前 6 個新 test 全在 `process_ghosts` 下游（已分類 drifts），**完全沒覆蓋分頁截斷上游**——這是測試盲區，非 process_ghosts 之過，但修法後須補。
- D2 spec（prompt 引用的 `2026-05-29--retcode-110017-d2-reconcile-spec.md` 在 worktree 不存在）落檔時，
  S-2 條件描述「Bybit fetch 成功且該 symbol size==0」應改為「**完整列舉**確認 size==0」，明列 limit/cursor 前提，避免字典/spec drift。

**已正確、無需改（背書）：**
- streak ≥2 mandatory（C-3 暫態防護）✅
- fail-closed on REST Err（baseline 保留不刪）✅
- 走 converge_exchange_zero_close 不走 ipc_close_symbol（避 110017 重入）✅
- mirror 無方向不收斂 ✅
- one-way G-3 前提守衛 + hedge re-review 註解 ✅
- 0 額外 rate-limit ✅

---

## Bybit-side overall

- 技術合規度：96%（D2 收斂語意/IPC/audit 乾淨；扣分在依賴的 `get_positions` 列舉不完整 = exchange-truth 信任邊界破口）
- 政策合規度：unchanged（0 ToS/KYC/geo/rate-budget 影響）
- 30d changelog：0 breaking change（繼承 2026-05-29）
- ship-stop blocker：**1**（(1b) 分頁截斷誤刪 live 真倉）
- 硬邊界：CLAUDE.md §四 fail-closed — D2 收斂非 retry，方向自洽；但「列舉不完整→刪真倉」違反 Root Principle 5（survival）+ 9（本地止損守護），必修

## 字典 follow-up

- `docs/references/2026-04-04--bybit_api_reference.md` §get_positions（line 527-542）應補：
  「`/v5/position/list` default limit=20、max 200、分頁 nextPageCursor；`get_positions(None)` 當前單頁不翻頁——
  caller 不可假設回應已列舉全部持倉（reconciler Ghost/Orphan 判定的完整性前提）」。SSOT：code 為真，修法 B land 後同步更新。

BB AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-29--d2_reconcile_ghost_exchange_truth.md
