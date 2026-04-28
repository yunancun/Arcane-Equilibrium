# OpenClaw / Bybit 虧損根因 5 維拆解 V2（核驗修正版）

**日期**：2026-04-28
**V2 作者**：Codex
**原始報告**：`docs/CCAgentWorkSpace/CC/workspace/reports/2026-04-28--loss_attribution_5dim_third_party.md`
**原始報告標記 HEAD**：`85a4e2d`
**本次核驗工作區 HEAD**：`d1f96d5`

---

## 0. V2 核心結論

原始報告的大方向「虧損與 edge/cost 結構有關」成立，但有一個關鍵表述需要修正：

- **已確認**：`execType="Funding"` 沒有被交易級 PnL、策略歸因、edge label pipeline 正確納入。這會讓 funding_arb 這類依賴 funding payment 的策略在報表/策略績效上系統性低估收入，並污染後續 edge/ML 標籤。
- **高概率成立**：目前策略 edge/cost 結構偏弱。現有 audit 顯示 funding_arb v2 在 13 筆 demo exit 中 net edge 為 `-36.76 bps`、勝率 `0/13`；現有 `edge_estimates.json` 也只有 1 個 cell 且為負。
- **未能直接證明**：Funding settlement 導致「實際 Bybit 錢包餘額完全不變」。程式中仍存在 WS wallet update、REST balance refresh、以及 exchange balance reconcile 路徑。因此 funding omission 可以確認為「交易級/策略級 PnL 缺口」，但不能單靠目前證據宣稱它是「真實錢包虧損的唯一根因」。
- **尚未量化**：本地 Postgres 未提供可用 `openclaw` role/database，無法直接重跑交易庫 SQL，故「5/5 策略皆無 alpha」只能視為待量化假設，不是本次核驗已證明結論。

**修正版根因判定**：

> 若「虧損」指 dashboard、`trading.fills`、策略歸因、edge labels：根因是 **Funding settlement 未入交易級 PnL/標籤** + **策略 edge/cost 結構偏弱**。
> 若「虧損」指 Bybit 實際錢包：目前只能確認 trading PnL 歸因缺口，還需要 Bybit transaction log / wallet ledger 才能證明 funding 漏記造成多少真實帳戶差額。

---

## 1. 原始報告需要修正的點

| 原始說法 | V2 判定 | 修正理由 |
|---|---|---|
| Funding row 走 unattributed audit，balance 不變 | **部分成立** | 走 unattributed audit 成立；但 balance 仍有 WS/REST 對賬路徑，不能寫成完全不變 |
| Funding settlement 完全不入 PnL 是 Cost 維度 BROKEN | **成立，但範圍限於交易級/策略級 PnL** | normal fill handler 沒有 `exec_type == "Funding"` 分流，也沒有 funding ledger/apply path |
| 5/5 策略無結構性 alpha | **待量化** | 現有文件支持 edge 弱，但本地 DB 不可用，且目前 `edge_estimates.json` 樣本只剩 1 cell / n=3 |
| Donchian look-ahead 是當前虧損根因 | **未證明** | Donchian 確有 current-bar inclusion/bias 風險，但未與當前虧損交易逐筆連上 |
| ML train-serve skew 加重虧損 | **不是直接根因** | 它是 label/training blocker；若 ML 尚未主導 live/demo 決策，不能列為當前交易虧損主因 |

---

## 2. 已核驗證據

### 2.1 Bybit Funding event 已有欄位，但沒有專門處理路徑

Bybit private execution stream 會帶 `execType`，Bybit enum 中也包含 `Funding`：

- Bybit private execution docs: <https://bybit-exchange.github.io/docs/v5/websocket/private/execution>
- Bybit enum docs: <https://bybit-exchange.github.io/docs/v5/enum>

本 repo 的 execution parser 已經保留 `exec_type`：

- `rust/openclaw_engine/src/bybit_private_ws.rs:141-165`：`ExecutionUpdate` 內有 `exec_type: String`

但 event consumer 的 Fill 分支只做一般成交匹配：

- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs:386`：註解描述 match pending order 後呼叫 `pipeline.apply_confirmed_fill`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs:529`：匹配到 pending order 時呼叫 `pipeline.apply_confirmed_fill`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs:580`：未匹配成交走 `try_emit_unattributed_fill`

該區段沒有 `exec.exec_type == "Funding"` 分支，也沒有將 funding settlement 寫入策略 PnL 或 edge label 的 path。

### 2.2 Unattributed fill 不會補上 funding PnL

未匹配成交會被記成 unattributed audit：

- `rust/openclaw_engine/src/event_consumer/unattributed_emit.rs:168-204`：產生 `strategy_name = "unattributed:bybit_auto"` 類型 audit fill，且 `realized_pnl`/fee attribution 不等價於 funding settlement

這代表即便 funding execution 被保留下來，也不會被歸到原策略、持倉、edge label 或 funding_arb 的預期收益。對 trading-level PnL 來說，這是 confirmed defect。

### 2.3 但錢包 balance 不是完全沒有更新路徑

原始報告把「交易級 PnL 不入帳」延伸成「balance 不變」過於絕對。現有程式有三條 balance 對賬路徑：

- `rust/openclaw_engine/src/startup/private_ws.rs:95-102`：private WS wallet update 更新 shared `bybit_balance`
- `rust/openclaw_engine/src/startup/mod.rs:756-808`：週期性 REST wallet balance refresh 更新同一個 shared balance
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs:859-868`：event loop 將 shared Bybit balance reconcile 到 `paper_state`
- `rust/openclaw_engine/src/paper_state/accessor.rs:410-424`：`reconcile_balance_from_exchange` 只在 drift 大於 `0.1%` 時修正

所以更精準的說法是：

- funding settlement 沒有被交易事件語義化；
- 小額 funding 可能因 drift threshold 或 refresh timing 延遲/不顯著；
- 但若 Bybit 錢包餘額本身已反映 funding，系統有機會透過 balance reconcile 看到總餘額變化；
- 這仍然不會修復「策略級 attribution」和「per-trade label」。

### 2.4 funding_arb 的收益模型依賴 funding payment

funding_arb 明確把 funding rate 當作收益來源：

- `rust/openclaw_engine/src/strategies/funding_arb.rs:91-93`：`compute_edge = abs(funding_rate) - amortized_fee`
- `rust/openclaw_engine/src/strategies/funding_arb.rs:443-447`：positive funding 做 short，negative funding 做 long

因此 funding payment 若沒有被歸因，funding_arb 的 strategy PnL 會天然少一塊收益。這是該策略和 PnL pipeline 的一階矛盾。

### 2.5 funding_arb 既有 audit 支持「edge/cost 結構偏弱」

`docs/audits/2026-04-17--g2_funding_arb_clean_edge_v2.md` 顯示：

- 13 筆 demo strategy_exit
- 累積 realized PnL：`$-2.1879`
- 累積 fee：`$0.7090`
- net edge：`$-2.8969`
- edge bps：`-36.76 bps`
- 勝率：`0/13`

這支持「strategy parameters/cost budget 本身偏弱」的判斷。但該 audit 沒有提供交易所 funding ledger join，因此不能反推出「真實帳戶沒有收到 funding」。

### 2.6 現有 edge estimate 樣本太小，只能作弱證據

`settings/edge_estimates.json` 目前只有：

- `_meta.n_cells = 1`
- `_meta.grand_mean_bps = -45.7275`
- `grid_trading::ORDIUSDT.n = 3`
- `win_rate = 0`

這是負 edge 證據，但樣本量不足以支持「所有策略 5/5 無 alpha」這種強結論。

### 2.7 Donchian 有 current-bar inclusion 風險，但不是已證明主因

- `rust/openclaw_core/src/indicators/trend.rs:185-191`：Donchian 使用 `high[n-period..n]` 與 `low[n-period..n]`，包含當前 bar
- `rust/openclaw_engine/src/strategies/bb_breakout/mod.rs:537-556`：BB breakout 在 Hard/Score 模式使用 Donchian gate/score

這會導致同一根 bar 的 high/low 被拿來做當前突破門檻，對回測/實盤一致性與 breakout 判定有偏差風險。它值得修，但本次沒有足夠逐筆交易證據把它定為「當前虧損主根因」。

### 2.8 ML engine_mode skew 是 blocker，不是直接交易虧損根因

- `rust/openclaw_engine/src/mode_state.rs:38-52`：Live + demo endpoint 會標成 `live_demo`
- `program_code/ml_training/parquet_etl.py:396`：training query 預設 `engine_mode = %(engine_mode)s`
- `program_code/ml_training/parquet_etl.py:541`：export 限制只接受 `paper/demo/live`，不接受 `live_demo`
- `program_code/ml_training/edge_label_backfill.py:129`、`:246`：backfill 依 engine_mode 等值過濾，但 CLI 已允許 `live_demo`

這會造成 train/serve 或 export/backfill coverage 風險。若 ML 尚未實際控制下單，這是 pipeline blocker，不是直接交易虧損原因。

---

## 3. V2 版根因排序

| 排名 | 根因 | 狀態 | 對虧損的解釋力 | 備註 |
|---:|---|---|---|---|
| 1 | Funding settlement 未進交易級 PnL/策略歸因/edge labels | **已確認** | 高，尤其影響 funding_arb 報表與 label | 需新增 funding ledger/apply path |
| 2 | Strategy edge/cost 結構偏弱 | **高概率** | 高 | funding_arb audit 與 edge estimate 均偏負，但還需完整 DB quant |
| 3 | Funding omission 導致實際錢包虧損 | **未證明** | 待定 | 需 Bybit transaction log / wallet ledger join |
| 4 | Donchian current-bar inclusion | **確認有 bias 風險** | 中低，待逐筆連接 | 建議修，但不應寫成已證明主因 |
| 5 | ML engine_mode skew | **確認有 pipeline blocker** | 間接 | 若 ML 未主導交易，不能列當前虧損主因 |
| 6 | Risk layer | **未見主因證據** | 低 | 現有報告也傾向 risk 非主因 |

---

## 4. 建議修復優先級

### P0-A：補 funding settlement 的一等事件處理

在 `loop_handlers.rs` 的 execution Fill handling 進入一般 pending-order match 之前，先分流：

```text
if exec.exec_type == "Funding" {
    parse funding amount / symbol / side / exec_time;
    write funding ledger row;
    apply funding settlement to paper_state / exchange-pipeline state;
    attribute to open position strategy if position-context is known;
    emit audit event with exec_type=funding, not as unattributed trade fill;
    continue;
}
```

修復目標：

- funding 不再被記成 unattributed trade fill；
- strategy-level PnL 可以看到 funding income/cost；
- edge labels 能區分 trading PnL、fees、funding；
- funding_arb 的 expected edge 與 realized edge 才能同口徑。

### P0-B：先用 Bybit ledger 量化真實帳戶 funding

不要只看 `trading.fills` 判定真實帳戶虧損。需要拉 Bybit transaction log / wallet ledger，按 symbol/time/position notional join：

```sql
-- pseudo query: schema depends on actual ledger ingest table
SELECT
  symbol,
  SUM(funding_amount) AS funding_total,
  COUNT(*) AS funding_events
FROM bybit_transaction_log
WHERE event_type IN ('Funding', 'SETTLEMENT')
  AND ts BETWEEN :start_ts AND :end_ts
GROUP BY symbol;
```

再和 strategy exits / positions join，才能回答：

- 這段期間實際收到/支付多少 funding；
- 缺失的 funding attribution 能解釋多少 dashboard loss；
- 真實錢包 loss 和交易級 PnL loss 差多少。

### P0-C：funding_arb 在 settlement path 修好前降級

在 funding settlement 不能正確入帳前，funding_arb 的績效指標不可信。建議至少二選一：

- 暫停 funding_arb；
- 或在 dashboard/report 中標記 funding_arb PnL incomplete，不用它產生策略晉級/淘汰結論。

### P1-A：修 Donchian leak-free 計算並回測

把 entry decision 的 Donchian threshold 改成只看已完成歷史 bars，例如概念上使用 `high[n-period-1..n-1]` / `low[n-period-1..n-1]`，並補測：

- equal-length insufficient guard；
- current high/low 不應影響當前 threshold；
- bb_breakout Hard/Score 模式下 signal count 和 PnL 的 before/after 差異。

### P1-B：修 ML `live_demo` coverage

`edge_label_backfill.py` 已允許 `live_demo`，但 `parquet_etl.py` 的 export allow-list 仍缺 `live_demo`。建議把 training/export/backfill 對 engine_mode 的處理統一為明確 allow-list，或支持 operator 明確傳入 `demo,live_demo` 多模式集合。

---

## 5. 需要補跑的驗證

本次本地核驗無法連上預期 DB role/database，因此以下需要在正確資料庫環境補跑。

### 5.1 策略級 realized PnL / fee / edge

```sql
SELECT
  strategy_name,
  COUNT(*) AS fills,
  SUM(realized_pnl) AS realized_pnl,
  SUM(fee) AS fee,
  SUM(realized_pnl - fee) AS net_pnl
FROM trading.fills
WHERE ts >= :start_ts
GROUP BY strategy_name
ORDER BY net_pnl ASC;
```

### 5.2 funding event coverage

```sql
SELECT
  exec_type,
  COUNT(*) AS n,
  SUM(realized_pnl) AS realized_pnl,
  SUM(fee) AS fee
FROM trading.fills
WHERE ts >= :start_ts
GROUP BY exec_type
ORDER BY n DESC;
```

若 `trading.fills` 沒有 `exec_type`，這本身就是 schema/ingest 缺口。

### 5.3 wallet ledger 對帳

需要從 Bybit transaction log 或內部 wallet ledger 查：

- funding settlement amount；
- wallet balance delta；
- 同時間段 open position notional；
- strategy context。

只有這個 join 完成後，才能把「策略級 funding 漏記」升級成「真實錢包虧損根因」。

---

## 6. 最終判斷

原始報告可以作為排查方向，但不能原封不動當作已證明 RCA。V2 的正式結論是：

1. **Confirmed root cause**：Funding settlement 缺少一等事件處理，導致交易級 PnL、策略歸因、edge labels 不完整。
2. **Likely root cause**：策略 edge/cost 結構偏弱，funding_arb 既有 audit 已呈現負 edge，但需要完整 DB 補量化。
3. **Not proven**：Funding omission 單獨造成真實 Bybit 錢包虧損；Donchian bias 是當前虧損主因；5/5 策略皆無 alpha。

因此修復順序應該先處理 funding settlement ingestion/attribution 與 ledger 對帳，再重跑 strategy edge attribution。否則後續策略淘汰、ML labels、dashboard PnL 都會在錯誤口徑上做決策。
