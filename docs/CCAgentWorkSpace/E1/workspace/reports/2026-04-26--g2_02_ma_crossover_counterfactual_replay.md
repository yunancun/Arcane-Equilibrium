# Wave 3 G2-02 — ma_crossover counterfactual fee replay tool

**日期**：2026-04-26
**執行者**：E1 (Backend Developer)
**任務**：寫 helper script 驗證「若 fee=2bps（PostOnly maker rate）會如何改變 ma_crossover 的 R:R」
**狀態**：實作完成 + smoke-test 全綠，待 E2/E4 review

---

## 任務摘要

PM 派發 Wave 3 G2-02：寫 read-only PG helper script，從歷史 fills 重算「若所有 ma_crossover 交易 fee=2bps」的 R:R / win_rate / net_edge_bps，做 QC 立場「fee fix 不能救 R:R」的 counterfactual 證明。**理論軌**（本 script）會與 1w post-G7-09 真實 demo（**現實軌**）~05-03 對齊。

完成狀態：
- Script 寫完：`srv/helper_scripts/research/ma_crossover_counterfactual_replay.py`（540 行 < 800 警告線）
- `--smoke-test` 跑通：SQL placeholder count vs args count 自檢、聚合器數學自檢、3 種 renderer 全綠
- 業務代碼 0 改動（純 helper script，PM 強調的「不直接改 production 代碼」）

---

## 修改清單

| 路徑 | 新增/修改/刪除 | 行數 | 說明 |
|---|---|---|---|
| `srv/helper_scripts/research/ma_crossover_counterfactual_replay.py` | 新增 | 540 | counterfactual 重算工具，read-only PG，CLI argparse + smoke-test |
| `srv/docs/CCAgentWorkSpace/E1/memory.md` | 修改 | +30 | 報告索引 + 教訓條目 |
| `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--g2_02_ma_crossover_counterfactual_replay.md` | 新增 | (本檔) | 報告 |

無 production 代碼改動。

---

## 關鍵 diff

### 重大設計決策：PM 規格 vs 真實 schema mismatch

**PM 規格的 SQL** 引用以下欄位：
```sql
o.realized_pnl_bps         -- ❌ 不存在於 trading.orders
o.entry_price              -- ❌ orders 只有 price (single-leg event)
o.exit_price               -- ❌ 同上
o.owner_strategy           -- ❌ 實際是 strategy_name
ef.fee_bps_total           -- ❌ 不存在於 learning.exit_features
ef.entry_fee_rate          -- ❌
ef.exit_fee_rate           -- ❌
```

**真實 schema**（V003 / V008 / V015 / V017 / V999）：
- `trading.orders` 是事件溯源表（每 status change 一行），無 PnL 欄位
- `trading.fills.realized_pnl` 是 USDT (REAL/float32)，**GROSS** （讀 Rust `paper_state/fill_engine.rs::apply_fill` 確認 — fee 從 balance 另扣，不從 PnL 扣）
- `trading.fills.fee_rate` 是 ratio 形式 `0.00055 = 5.5bps`
- `trading.fills.entry_context_id`（V017 FILL-CONTEXT-LINKAGE-1）= close fill 指向 entry fill 的 pointer；entry fill 自己這欄 NULL
- `trading.fills.context_id` = 該 fill 自己的 id（close fill 用 `make_context_id` 重新生成）

**設計修正**（push back PM 規格，基於真實 schema）：
```sql
-- 從 fills 直接 INNER JOIN 自己抓 (entry, close) pair：
SELECT close.qty, close.price, close.realized_pnl, close.fee, close.fee_rate,
       entry.qty, entry.price, entry.fee, entry.fee_rate
FROM trading.fills AS close
INNER JOIN trading.fills AS entry
    ON entry.context_id = close.entry_context_id
WHERE close.strategy_name = %s
  AND close.engine_mode = %s
  AND close.realized_pnl != 0
  AND close.entry_context_id IS NOT NULL
  AND close.qty > 0 AND close.price > 0
  AND entry.qty > 0 AND entry.price > 0
  AND close.ts > now() - (%s || ' days')::interval
```

### Counterfactual 公式（讀 Rust 源碼後簡化）

```python
# realized_pnl 是 GROSS（fill_engine.rs:apply_fill 第 3 段確認）
# realized_pnl is GROSS (verified at fill_engine.rs:apply_fill)
gross_pnl_usdt = close.realized_pnl
notional       = close.qty * close.price
gross_pnl_bps  = gross_pnl_usdt / notional * 10000

# Counterfactual：×2 因 entry+exit 對稱各付一次（fills schema 即是雙邊各記）
# Counterfactual: ×2 because entry+exit each pay symmetrically (mirrors fills schema)
cf_net_bps = gross_pnl_bps - 2.0 * scenario_fee_bps
```

PM 規格寫「先把實際 fee 加回去再減 scenario」— 不必要，因 `realized_pnl` 已是 fee-free gross。

### Aggregator AGGREGATE 行的 honest weighting

```python
# AGGREGATE 從原始 rows 重跑一次，不從 per-symbol 再聚合
# AGGREGATE recomputes from raw rows (avoid arithmetic-mean vs notional-weighted mismatch)
for fee_bps in fee_scenarios:
    cf_list, notional_list = [], []
    for r in rows:
        m = compute_per_trade_bps(r, fee_bps)
        cf_list.append(m["cf_net_bps"])
        notional_list.append(m["notional_usdt"])
    net_pnl_total = sum(cf * notional / 10000.0 for cf, notional in zip(cf_list, notional_list))
```

---

## 治理對照

| 編號 | 規則 | 符合 / 違反 / 未規範 |
|---|---|---|
| CLAUDE.md §七 雙語注釋 | MODULE_NOTE / docstring / inline 中英對照 | **符合**（每函數 + 模組頂部全雙語）|
| CLAUDE.md §七 跨平台兼容 | 路徑不硬編碼 | **符合**（全用 ENV，無 `/Users/...`/`/home/...`）|
| CLAUDE.md §七 跨平台兼容 | 依賴乾淨 | **符合**（psycopg2-binary 已裝；lazy import 進 main，模組頂部不需要）|
| CLAUDE.md §七 SQL Migration Guard A/B/C | — | **不適用**（本任務為 helper script，無新 migration）|
| CLAUDE.md §七 被動等待必附 healthcheck | — | **不適用**（本任務為 read-only 分析工具，非被動等待管線）|
| CLAUDE.md §九 800 行警告 / 1200 行硬上限 | — | **符合**（540 行）|
| 原則 #1 單一寫入口 | — | **符合**（read-only，0 寫入）|
| 原則 #4 策略不能繞過風控 | — | **不適用**（read-only 分析工具）|
| 原則 #6 失敗默認收縮 | DB 連線失敗 → exit 2 | **符合**（fail-closed，print error 不靜默）|
| 原則 #10 認知誠實 | orphan 數量 WARN 報出 | **符合**（不隱藏 V017 之前缺 entry_context_id 的歷史 row）|
| skill `bilingual-comment-style` | MODULE_NOTE 含關聯文件 / 上游下游 / 不變量 | **符合**（雖無上下游，因為純讀腳本，但有 PnL 公式不變量說明）|

---

## 不確定之處

1. **PM 規格中提到 `--engine-mode <demo|live_demo|paper>` default demo，但 `live` 也是合理選項**（雖然 demo audit 用，但 spec 嚴格列舉）
   - **決策**：argparse `choices` 加上 `live`，help 文案註「rarely used here」 — 不違反 PM 但有彈性
   - 風險：若 PM 真的不希望加 live，回退即可

2. **`--min-per-symbol` 默認 5 vs PM 規格「per-symbol 樣本 < 5 → 該 symbol 不入 markdown table」**
   - 我加了 CLI flag 讓 operator 可調（例：實際發現 ETHUSDT n=87，但其他 symbol 都 < 5，operator 可調 `--min-per-symbol 1` 看完整對比）
   - PM 規格未禁止可配置，但默認值 = 5 與規格一致 ✅

3. **Symbols 沒匹配時 INNER JOIN 丟棄 orphan close fills（V017 之前資料 entry_context_id NULL）**
   - 我用 `ORPHAN_COUNT_SQL` 計數並結尾 WARN 顯示，避免 operator 誤以為 fill 數少於預期
   - 風險：若 V017 之前的歷史資料對 counterfactual 也有重要意義，operator 可能希望也納入；但 PM 規格說「`realized_pnl_bps IS NULL` 的 row 跳過」+ 缺 entry fee 資料下 counterfactual 不可信，所以 INNER JOIN 是正確的設計

4. **Exit code 規格曖昧**：「成功 + 至少一個 symbol 有 ≥30 trades → 0」vs「任何 cell 全部 < 10 → 1」
   - 兩條件之間有一段灰色區（per-symbol 5-29 trades，AGGREGATE > 30）
   - **決策**：保守處理 — 只有「ALL cells < 10」才 exit 1；其他情況 exit 0（warn message 清楚），避免 spurious red 阻擋 operator 流水線
   - 若 QC 嚴格要求 ≥30 才綠，下一輪可加 strict mode flag

5. **跨平台風險**：psycopg2 lazy import — Mac 端跑 `--smoke-test` 完全不需 psycopg2，但實際跑時若 Mac dev 沒裝會 ImportError
   - **無風險**：規格說「user-level 已裝」，且 Mac 端通常不直連 Linux PG（透過 SSH bridge 在 Linux 跑）
   - 報告 Operator：建議 Linux 端跑（trade-core）

6. **未做 unit test**（規格「不寫 unit tests」明確 OK）— 但 `--smoke-test` 內含 aggregator 自檢 + renderer 自檢 + SQL placeholder 計數自檢，足夠

---

## Operator 下一步

### 已驗證（Mac 端）

```
$ python3 srv/helper_scripts/research/ma_crossover_counterfactual_replay.py --smoke-test
[OK] smoke test passed — SQL templates valid + math + renderers OK.
```
更多 smoke variants 也驗證過：
- `--symbols BTCUSDT,ETHUSDT --fee-scenarios 1.5,3.0,5.5 --output-format json --lookback-days 14` → ANY(%s) 注入 + 4 placeholders/4 args ✅
- `--fee-scenarios 0.0` → 拒絕（>0 驗證）✅
- `--help` → 文案完整 + Examples ✅

### Linux 端真實跑（待 operator 觸發 / 待 E2 review 後）

```bash
# Linux trade-core (透過 SSH bridge，operator 自行決定何時跑)：
ssh trade-core "cd ~/BybitOpenClaw/srv && \
  OPENCLAW_DATABASE_URL=postgresql://... \
  python3 helper_scripts/research/ma_crossover_counterfactual_replay.py \
    --engine-mode demo --lookback-days 30 --fee-scenarios 2.0,5.5"
```

### Review 重點（給 E2 / E4）

- **E2 必查**：
  - SQL template 與真實 schema 對齊（PM 規格欄位 mismatch 已修正，見「治理對照」）
  - psycopg2 lazy import（不在模組頂部）✅
  - `paired_sql.count("%s") == len(paired_args)` 自檢覆蓋 with/without symbols 兩種 build query 路徑 ✅
  - Inner JOIN 丟棄 orphan + WARN 報出（不靜默）
  - Exit code 0/1/2 三態都有 message
  - 雙語注釋齊備（MODULE_NOTE + docstring + inline）

- **E4 必查（regression）**：
  - 跑 `--smoke-test` 通過（CI 友善）
  - 在 Linux 真實 PG 環境跑 demo lookback 30d，比對 `aggregator self-test` 結果是否合理
  - **若 demo n_trades 為 0**：表示 V017 之後 ma_crossover 在 demo 下沒有任何 closed paired trade（可能 SCANNER-GATE 或 dormancy）— 這是真實狀態，不是 bug
  - **若 orphan_count > 0 且 paired n=0**：表示所有 demo close fills 缺 entry_context_id（V017 串線中斷 root cause 候選） — 觸發 root cause investigation，非本工具範圍

- **QC 接收 (報告貼上後)**：
  - 比對 cf_2.0 vs cf_5.5 的 R:R 差距
  - 若 cf_2.0 R:R 仍 < 1.0 → QC 立場（fee 不能救 R:R）成立 → support disable ma_crossover
  - 若 cf_2.0 R:R > 2.0 → 可能 fee 是主因 → 觸發 PostOnly fee 部署 + 1w 真實驗證等待

### 不需要 operator 親自做的步驟

無。本 script 是 read-only 分析工具，operator 可隨時跑（含 production runtime 不影響）。

---

## E1 IMPLEMENTATION DONE

待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--g2_02_ma_crossover_counterfactual_replay.md`）。
