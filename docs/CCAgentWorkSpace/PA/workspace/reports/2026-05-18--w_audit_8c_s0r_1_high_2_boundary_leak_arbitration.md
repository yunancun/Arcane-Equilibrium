# PA Arbitration — W-AUDIT-8c S0R-1 HIGH-2 Boundary Leak

- **日期**：2026-05-18
- **裁決對象**：E2 round 1 review `HIGH-2`「`quiet_window_sec=0` + bar-boundary `bucket_end_ts` 的 partial leak」
- **PA 自身被指控**：design §2.3 line 261 `>=` 與 §8.1 line 653 `MUST be ≥ ... quiet_window=0 special case test for boundary correctness` 互相矛盾
- **裁決範圍**：boundary semantic only；不重開 CRIT-1 / CRIT-2 / HIGH-1 等其他 finding

## 一行裁決

**Verdict = D (改 `entry_mid = open only`，保留 `>=`)；NOT A / NOT B / NOT C。**

理由摘要：問題不在 `>=` vs `>`，問題在 `(open+close)/2` 把「進場後 60s 的 close」混入「進場價」。改 `entry_mid = k_entry.open` 一字之差，從根源消除 partial leak，所有 `quiet_window_sec` 值（含 0）都安全，K_total 維持 11_664，無 spec 改動成本。

E2 列的 (a)/(b)/(c)/(d) 中我選 **(d) 的變體**（E2 寫「改 entry 用 open-only」屬同方向，但 E2 並沒指出這也應同步應用到 exit_mid）。

## 二、事實核查

### 2.1 `market.klines.ts` 是 OPEN 還是 CLOSE 時間？

**事實**：`market.klines.ts` = **bar open time**。

- 證據：`srv/sql/migrations/V002__market_tables.sql:122`：
  ```
  ts              TIMESTAMPTZ NOT NULL,   -- bar open time
  ```
- 同時有 `open_ts_ms` (line 123) 與 `close_ts_ms` (line 124) 精確毫秒欄位
- 一根 `timeframe='1m'` bar 若 `ts = 12:34:00` → bar 涵蓋 `[12:34:00, 12:35:00)`
  - `open` = 第一筆 trade price (~12:34:00 附近)
  - `close` = bar 結束前最後 trade price (~12:34:59.x)

### 2.2 PA design `market.klines_1m` 是 phantom table

- 實際 schema 沒有 `market.klines_1m` 表
- 正確寫法是 `market.klines WHERE timeframe='1m'`
- E1 self-report §3 已 catch 並 deviation #2 documented（E1 改正為 `market.klines + timeframe='1m'` filter，這是合理 deviation）
- **此處 PA design 應該補一份 schema-name fix 但與本次仲裁無關**（已被 E1 改了）

### 2.3 8b precedent 的 boundary 慣例

**事實**：8b 不用 `>=` 也不用 `>`，**用 exact equality**：

```sql
LEFT JOIN market.klines f15
    ON f15.symbol = b.symbol
   AND f15.timeframe = '5m'
   AND f15.close_ts_ms = b.signal_ts_ms + 900000  -- exact match
```

8b 用 `close_ts_ms = signal_ts_ms + horizon_ms` deterministic 指定特定 bar，沒有 `>=` vs `>` 的 ambiguity 可繼承。

8b 同時 entry 用 `close_px`（line 9）+ `prior_5m_return_bps`，forward 用 `close_15m / close_30m / close_60m` — **全部 close-to-close**，零 (open+close)/2 平均。

**重要 implication**：8b 不能直接為 8c 提供 `>=` vs `>` 的 mirror 答案，但 8b 用 close-only 是 8c 應該效法的更安全慣例。

### 2.4 E1 實際 SQL 落點

從 origin/feature/w-audit-8c-s0r-1-sql-query-template HEAD `bd1b2443`：
```sql
-- entry kline
AND ts >= tc.bucket_end_ts + (%(quiet_window_sec)s::int * INTERVAL '1 second')
ORDER BY ts ASC LIMIT 1
```
+ `entry_mid = (k_entry.open + k_entry.close) / 2.0`

E1 follow 了 PA design line 263 + 266 字面。E1 self-report §4 也提到 deviation 但沒挑這個 boundary semantic。

### 2.5 PA design 自相矛盾的精確 wording

- §2.3 line 261-266：「first kline mid **at OR after** ... `ts >= bucket_end_ts + quiet_window`」 → 字面 `>=`
- §8.1 line 653：「kline entry/exit time MUST be ≥ ... `>` not; quiet_window=0 special case test for boundary correctness」 → 字面也 `>=`，但語意是「quiet_window=0 邊界情況要測對」
- **解讀**：PA 自身在 line 653 並不是要 `>`，是要 E2 review 確認 `>=` 在 boundary case 下的行為對；line 261 與 line 653 **同方向**（都是 `>=`）。E2 review 把「`MUST be ≥ ... quiet_window=0 special case test for boundary correctness`」誤讀為「兩個指令互相矛盾」其實是「`>=` 但要 review 邊界情況」。
- **PA 自承**：line 653 wording 過於精簡導致 E2 解讀為「自相矛盾」，這是 PA design 表達責任，但**設計意圖不矛盾**。

### 2.6 真正的 leak 機制

事實序列：
1. `bucket_end_ts = max(ts)` from `market.liquidations`（per E1 line 131-133）
2. 假設 `bucket_end_ts = 12:34:00.000` (整分鐘) + `quiet_window_sec=0`
3. Option A `ts >= 12:34:00` → 命中 kline `ts=12:34:00`
4. 此 kline 涵蓋 `[12:34:00.000, 12:35:00.000)`，**open price** = bar 開瞬間（~12:34:00 + δ），**close price** = bar 結束前（~12:34:59.x）
5. `entry_mid = (open + close)/2` 把進場後完整 60s 的 close 混入進場價
6. 若該 60s 內 mean-reversion 已發生 N bps，則 `entry_mid` 偏離真實「進場瞬間市價」N/2 bps
7. `gross_bps = expected_dir × (exit_mid - entry_mid) / entry_mid × 10000`
   - 若 reversion 是 + 方向、`entry_mid` 已包含 +N/2 bps → 與 exit_mid 差距縮小 → gross_bps 低估 N/2 bps

**這不是 look-ahead bias（不是用未來價做決策），是 entry-fill underestimation（用未來價當進場價）**。對 Stage 0R replay 而言：
- 方向：systematic **低估 alpha**（保守誤差）
- 數量：1m bar 內若有顯著 reversion ~5-20 bps，低估幅度 2.5-10 bps
- 嚴重度：對 5m primary horizon = ~5-10% relative；對 1m sensitivity = ~30-50% relative；對 15m = <3%

### 2.7 Cross-ref `feedback_indicator_lookahead_bias.md`

該 memory 講「`rolling(N).max()` 含 current bar → breach=current 是 N-bar max → 必然 mean-revert」。**本案不是該模式**，但有 **同根 spiritual sin**：用「事件當下到 60s 後的平均」當「進場價」，等於 `entry_mid = (event_time_price + post_60s_price) / 2` —「事件當下價」對 `event_time + 60s 收益測量` 而言已有部分洩漏，等同 rolling window 含 current bar。

memory 給出 prescription：**`shift(1)` 排除 current bar**。本案 spiritual equivalent = **`entry_mid = open only`**（排除 current bar 的 close）。

## 三、Option 評估

| Option | 描述 | 修改成本 | 數學正確性 | K_total 影響 | Risk |
|---|---|---|---|---|---|
| A | 維持 `>=` + `(open+close)/2` | 0 | ❌ partial leak | 11_664 | quiet=0 cell 低估 alpha |
| B | 改 `>` + `(open+close)/2` | 1 字 | ❌ leak 仍在 | 11_664 | quiet=0 → 第二根 kline → 60-120s 後 → leak 反而更大；exit 同步改後 horizon 也漂移 |
| C | 強制 `>=` + 額外 1m_interval | 多參 | ⚠️ 過保守 | 11_664 | quiet=0 cell 等同 quiet=60，sweep 失去意義 |
| **D** | **維持 `>=` + 改 `open only`（entry + exit 同步）** | **1 字** | **✅ 零 leak** | **11_664** | **無；與 8b close-only 仍不一致但 mid→open 是 8c 短 horizon 合理選擇** |
| E | 禁 `quiet_window_sec=0` cell | 改 spec | ✅ 但 hack | **7_776** | spec 改動成本 + sweep dimensionality 損失 + 沒解決根因 |

**Option B 為什麼錯**：
- 改 `>` 後，`bucket_end_ts=12:34:00` + quiet=0 → 第一個 `ts > 12:34:00` 是 `ts=12:35:00` kline → entry bar 是 `[12:35:00, 12:36:00)` → entry_mid 包含 60-120s 後價格 → 比 A 漂得更遠
- 對 `bucket_end_ts=12:34:30` + quiet=0 → `ts > 12:34:30` 仍是 `ts=12:35:00` → 與 A 完全相同（A 在這 case 已選 12:35:00）
- 結論：B 只在 boundary case 與 A 不同，且 B 在該 case 更差

**Option C 為什麼錯**：
- 強制 +1m interval 等於把 quiet_window=0 cell hard-fold 成 quiet_window>=60 cell
- 但 spec 的 sweep 0/30/60 設計目的是測**「最快進場 vs 等 quiet」效益對比**
- C 消除 0 cell 的物理意義 → sweep 失去信息量

**Option D 為什麼對**：
- 1m bar 的 `open` 是該 bar 物理上**最接近進場決策時刻**的 price proxy（bar 開瞬間第一筆 trade）
- `bucket_end_ts=12:34:00` + quiet=0 → kline `ts=12:34:00` → `entry_open` = 12:34:00 + δ price，δ << 1 second
- 對 boundary case：entry 物理時刻 ≈ event 時刻，無 leak
- 對 non-boundary case：entry 物理時刻 = 「event 後第一根新 bar 開始時」≈ event + δ′ (δ′ < 60s)，仍合理
- exit 同步改 `open only`：horizon=5m，exit bar `ts = bucket_end_ts + quiet + 300s` → `exit_open` 是該 bar 開瞬間 price，與 entry 對稱
- 收益 = `(exit_open - entry_open) / entry_open × 10000` — 與 8b close-to-close 模式 spiritual 一致，只是 8c 採 open-to-open（因 8c 短 horizon 1-15m，open gap 更乾淨）

**Why NOT close-to-close like 8b**：
- 8b horizon 15/30/60m，bar close 與 next bar open 的 overnight/microstructure gap 影響 <5%
- 8c horizon 1-15m，若用 close-to-close：`entry_close = bar[12:34:00].close ≈ 12:34:59.x` 比 `bucket_end_ts=12:34:00` 晚 ~60s（無 quiet_window 的 case），相當於「自動加了 60s implicit quiet_window」，破壞 sweep 0/30/60 設計
- 8c open-to-open 與 bucket_end_ts 對齊更乾淨

## 四、Verdict + Implementation

### 4.1 Verdict = D

**E1 rework S0R-1 SQL change 必要：YES（小規模）。**

具體 diff（E1 在 rework round 一併修，與 CRIT-1/CRIT-2/HIGH-1 同 round）：

```diff
-- forward_returns CTE
    (SELECT
-       (k_entry.open + k_entry.close) / 2.0
+       k_entry.open::float8 AS entry_open
       FROM market.klines k_entry
      WHERE k_entry.symbol = tc.symbol
        AND k_entry.timeframe = '1m'
        AND k_entry.ts >= tc.bucket_end_ts + (%(quiet_window_sec)s::int * INTERVAL '1 second')
      ORDER BY k_entry.ts ASC LIMIT 1) AS entry_mid,  -- 欄位名沿用 entry_mid 維持下游契約

    (SELECT
-       (k_exit.open + k_exit.close) / 2.0
+       k_exit.open::float8
       FROM market.klines k_exit
      WHERE k_exit.symbol = tc.symbol
        AND k_exit.timeframe = '1m'
        AND k_exit.ts >= tc.bucket_end_ts
                         + (%(quiet_window_sec)s::int * INTERVAL '1 second')
                         + (%(horizon_min)s::int * INTERVAL '1 minute')
      ORDER BY k_exit.ts ASC LIMIT 1) AS exit_mid
```

**注意**：
- 欄位名 `entry_mid` / `exit_mid` **保留**（下游 Python `_compute_gross_bps()` 已用此名），避免 cascade 改動
- semantic 改為 open-only，但欄位名稱保留「mid」是技術債（合理 trade-off：欄位 rename 影響 MIT 計算模組）
- 在 MODULE_NOTE 加 explicit 中文註解說明：「entry_mid/exit_mid 取該 bar `open` price（避免 1m bar `(open+close)/2` 含 60s post-event partial leak）；命名沿用『mid』是契約鎖定」

### 4.2 `>=` vs `>` 維持 `>=`

**`>=` 維持不變**。理由：
- 改 D 之後 `entry_mid = open`，bar boundary case 不再 leak
- `>=` 在 non-boundary case 行為與 `>` 完全一致（兩者都選下一根 bar 的 open）
- `>=` 在 boundary case `bucket_end_ts = 12:34:00.000` + quiet=0 命中 `ts=12:34:00` bar 的 open ≈ event time price，這是物理上最快可進場的 proxy，符合 spec「next available tradable mark」(line 231)
- 改 `>` 會在 boundary case 強制延後一根 bar (60s)，反而違反 spec「next available」語意

### 4.3 `quiet_window_sec=0` 維持為合法 sweep cell

不採 E2 option (c)「強制 quiet_window_sec >= 1」。理由：
- 0 cell 物理意義 = 「事件後立刻進場（無 quiet）」，是 sweep 對照組
- 改 D 後 0 cell 已無 leak
- K_total 維持 11_664，spec 不需改

## 五、PA design §2.3 + §8.1 footnote 修補

**PA 自承**：line 261 + line 653 雖然設計意圖一致（都 `>=`），但 wording 不夠精確導致 E2 誤讀為「自相矛盾」+ entry_mid 用 `(open+close)/2` 是 PA 自己引入的 leak source。

### 5.1 §2.3 line 261-274 amendment text

PA 本仲裁不直接改 design 報告（per task constraint）；推薦 E1 rework round 一併把以下中文 inline comment 加入新 SQL：

```sql
-- Entry mid: bucket_end_ts + quiet_window 之後第一根 1m kline 的 open price
-- （仲裁裁決 D：取 open 而非 (open+close)/2 避免 1m bar 內 close 包含
--  event 後 60s reversion 的 partial leak；欄位名沿用 entry_mid 是
--  下游 Python contract 鎖定）
-- 邊界 case：bucket_end_ts = 12:34:00.000 + quiet=0 → 命中 ts=12:34:00 bar
-- 的 open ≈ event time price，無 leak；ts >= 是 spec line 231 "next available"
-- 語意，不是 lookahead bias（事件已知，價格未知）。
```

### 5.2 §8.1 line 653 amendment text

下次 PA design report（不是這份仲裁）應把：
> `kline entry/exit time MUST be ≥ bucket_end_ts + quiet_window not >; quiet_window=0 special case test for boundary correctness`

改為更清晰：
> `kline join 使用 ts >= bucket_end_ts + quiet_window（非 >），以保留 quiet_window=0 cell 的物理意義（事件後立刻進場 sweep 對照）；entry/exit price 取該 bar 的 open 而非 (open+close)/2，避免 1m bar 內 close 含 event 後 60s reversion 的 partial leak（仲裁 2026-05-18 HIGH-2 verdict D）。`

## 六、Forward governance hardening

### 6.1 Stage 0R replay 共通檢查清單（PA 應 nominate 加入 future spec/replay 模板）

任何 replay 模板若涉及「事件 timestamp → 後續價格 lookup」必須回答：
1. **price aggregation window**：用 single trade、bar open、bar close、bar mid、VWAP？是否涵蓋事件當下？
2. **bar OPEN/CLOSE 語意**：DB 欄位 `ts` 是 bar 開還是收？（V002 是 open，這個項目易誤記）
3. **boundary alignment**：事件 timestamp 若 align bar 邊界，是否進入該 bar 還是下一 bar？
4. **leak direction**：fill price 包含事件後價格 = 低估 alpha（保守）；fill price 包含事件前價格 = 高估 alpha（攻擊性，REJECT）

本案是 type-1 leak（保守）：未阻塞 stage 0R 但需修，因為**對 cost_edge_ratio 判斷敏感**（一旦 net_bps 接近 cost_bps，systematic 低估 5-10% 可能把 marginal positive cell 推到 RED）。

### 6.2 PA 自身的 design SOP 補強

**Lesson**：PA design §2.3 把 entry/exit 寫 `(open+close)/2` 是直接抄 generic mid-price 慣例而沒檢查 1m bar 在 sub-minute event 邊界的 leak 風險。Future PA design 涉及 sub-bar event timing + bar price aggregation 時，必須在 design 階段對 boundary case 走過一次「假設 event 在 bar 開瞬間發生」的 thought experiment。

不為此單獨開新 governance doc；已 capture 在本仲裁與 §5.2 amendment text 中。

## 七、給主會話的回報

| 項目 | 答案 |
|---|---|
| Verdict | **D (entry_mid + exit_mid 從 `(open+close)/2` 改為 `open` only；`>=` 維持；K_total 11_664 維持)** |
| E1 rework S0R-1 SQL 需改？ | **YES**（小範圍：2 處 `(open+close)/2` 改 `open`；欄位名 `entry_mid`/`exit_mid` **保留**；MODULE_NOTE 加中文註釋）；E1 rework round 與 CRIT-1/CRIT-2/HIGH-1 合併處理 |
| PA design §2.3 footnote 修補？ | **YES**（不直接改 design 報告；amendment text 已在本仲裁 §5.1/§5.2 給出，由 E1 rework SQL 內 comment 體現 + 下次 PA design 改 wording） |
| `quiet_window_sec=0` 維持合法 sweep cell | YES |
| 8b precedent 是否強制 mirror | NO — 8b 用 close-to-close 且 horizon 15-60m，與 8c 1-15m horizon 物理性不同；8c open-to-open 是合理 cross-spec 選擇 |
| 影響其他 finding 嗎 | NO — 本仲裁與 CRIT-1 (notional_pct_floor)、CRIT-2 (sibling consistency)、HIGH-1 (sentinel-split) 完全正交，可同 rework round 一併修 |

PA DESIGN DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8c_s0r_1_high_2_boundary_leak_arbitration.md`
