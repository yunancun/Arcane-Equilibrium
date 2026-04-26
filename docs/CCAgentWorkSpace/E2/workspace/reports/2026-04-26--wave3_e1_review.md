# E2 Adversarial Review — Wave 3 第二波 E1 兩交付

**日期**：2026-04-26
**Reviewer**：E2（Senior Backend Code Reviewer + Adversarial Auditor）
**範圍**：
- G2-02 `srv/helper_scripts/research/ma_crossover_counterfactual_replay.py`（773 行）
- G8-02 `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/{test_executor_decision_parity.py, fixtures/executor_parity_cases.yaml}`（503 + 838 行）
- E1 兩個 push back 的判定（PM 已接受，本 review 重新質疑）

**結論**：**PASS with conditions**（兩交付主體可進 E4，但 G2-02 必須補一段 doc 揭露 partial-close / accumulate counterfactual 偏差；G8-02 必須修正 `synthetic_replay` 的描述誤導 + 移除 dead imports）

---

## §1 G2-02 review

### 1.1 SQL 設計核心驗證（adversarial 對 E1 push back）

E1 的 push back 是改用 `trading.fills` self-INNER-JOIN 取代 PM 規格的 `trading.orders` JOIN。我獨立核實如下：

#### 1.1.1 「`realized_pnl` 是 GROSS」**確認屬實** ✅

讀 `rust/openclaw_engine/src/paper_state/fill_engine.rs:273-279`：
```rust
let pnl = if pos.is_long {
    (fill_price - pos.entry_price) * close_qty
} else {
    (pos.entry_price - fill_price) * close_qty
};
self.balance += pnl;
self.total_realized_pnl += pnl;
```
純價差，未扣 fee。Fee 在 line 264 從 balance 另外扣 (`self.balance -= fee`)，但 `total_realized_pnl` 累加的是 GROSS pnl。

讀 `rust/openclaw_engine/src/database/trading_writer.rs:307`：`b.push_bind(sanitize_f64_or_zero(*realized_pnl) as f32)` — 寫入 PG 的 `realized_pnl` 即是 `apply_fill` 算出的 GROSS pnl。Fee 寫到獨立的 `fee` column（line 305）。

E1 對 source-of-truth 驗證可靠。Counterfactual 公式 `cf_net_bps = gross_pnl_bps - 2 × scenario_fee_bps` 邏輯成立。

#### 1.1.2 V017 FILL-CONTEXT-LINKAGE-1 schema 確認

讀 `sql/migrations/V017__edge_predictor_tables.sql:131-140`：
- `trading.fills.entry_context_id` 是 V017 新增 column（非復用 `context_id`）
- 開 fill 寫 NULL（pre-V017 還原 fill 也是 NULL）
- 平倉 fill 攜帶 entry 的 `context_id`

E1 設計 INNER JOIN 捨棄 NULL entry_context_id 的 close fills 是正確的（counterfactual 需 entry 側資料才能算 actual_net_bps）。

#### 1.1.3 ⚠️ JOIN 的 partial-close / accumulate 偏差（對抗發現）

**這是 E1 沒講清楚的 edge case**。讀 `paper_state/fill_engine.rs:282-313` + `paper_state/accessor.rs:194-209` + `tick_pipeline/commands.rs:184-188`：

- **Fresh open** → `paper_state.set_entry_context_id` 設為當下的 `context_id`。
- **Same-direction accumulate** → 不覆蓋 `entry_context_id`（comment 明示）；新 fill 自身 context_id 是新生成的，但 position 仍指向第一筆 open 的 ctx。
- **Partial close（fast_track ReduceToHalf）** → position 保留，下一筆 close 仍寫同樣的 `entry_context_id`。

對 SQL `INNER JOIN trading.fills entry ON entry.context_id = close.entry_context_id` 的影響：

| 場景 | JOIN 結果 | Counterfactual 偏差 |
|---|---|---|
| 1 open + 1 close | 1 row · 1 entry + 1 close | **正確**（cf 扣 2 × fee_bps，符合實際 entry+exit 各 1 次費）|
| 1 open + N partial close（fast_track） | N rows · 每 row 共用同一 entry · 全 N rows 共扣 (N+1) 次 fee 才符合實況 | cf 扣 **2N × fee_bps**（每 row 都扣 2），**過扣 (N-1) × fee_bps** |
| 多 accumulate + 1 close | 1 row · 只看到第 1 筆 entry · 漏掉其他 accumulate 的 entry-side | cf 只扣 2 × fee_bps，但實況有 (M_entry+1) 筆 fee → **少扣 (M_entry-1) × fee_bps** |

對 ma_crossover：策略本身只發 `StrategyAction::Close`（無同向加倉），所以 accumulate 路徑大概率不會觸發。但 **fast_track ReduceToHalf** 確實存在（`rust/openclaw_engine/src/fast_track.rs:81-260`，多處 `FastTrackAction::ReduceToHalf`）→ partial close **可能發生**。

E1 報告的 docstring 寫「×2 because counterfactual assumes both entry + exit pay the scenario rate symmetrically」對 1:1 場景成立，但**沒揭露 partial-close 偏差**。實際 demo 上 ma_crossover 觸發 ReduceToHalf 比率多大需 SQL 算（不在本 review 範圍），但偏差方向是 **counterfactual 比真實更悲觀**（過扣 fee）。

**Severity**：**MEDIUM**。對 ma_crossover 預期影響不大（策略不主動 accumulate），但 docstring 欺騙性強。**動作**：退回 E1 補一段 doc 揭露 + （可選）在 markdown 輸出尾部加一行 `_Note: counterfactual assumes 1 entry × 1 close per JOIN row; partial closes via fast_track over-charge entry fee. Validate via SELECT entry_context_id, COUNT(DISTINCT context_id) FROM trading.fills WHERE realized_pnl != 0 GROUP BY entry_context_id._`

#### 1.1.4 ⚠️ JOIN 缺 engine_mode / strategy_name 防禦（理論問題）

`PAIRED_FILLS_SQL` line 122-125：

```sql
INNER JOIN trading.fills AS entry
    ON entry.context_id = close.entry_context_id
WHERE close.strategy_name = %s
  AND close.engine_mode = %s
```

`entry.context_id` 來自 `make_context_id(em, symbol, ts_ms)`（含 engine_mode 但不含 strategy_name）。理論上同 em 同 symbol 同 ms 但不同 strategy 的兩筆 entry 會 collide。`make_context_id` 為確定性 hash，實務 collision 機率極低（同 ms 觸發兩個策略已經很罕見，加上 paper_state 為單一倉位 SoT），但 **adversarial 立場應該加防禦**：

建議加：
```sql
AND entry.engine_mode = close.engine_mode
AND entry.symbol = close.symbol
```

Severity：**LOW**（極端 edge case，但成本 0 加防禦）。**可選 fix**，不阻塞。

### 1.2 Counterfactual math review

#### 1.2.1 公式正確性

```python
notional = close.qty × close.price          # close-side notional
gross_pnl_bps = realized_pnl / notional × 10000
cf_net_bps = gross_pnl_bps - 2 × scenario_fee_bps
```

- `notional` 用 close-side：對 1:1（1 open + 1 close 等量）場景，等於 entry-side notional。對 partial close 場景，每 row 的 notional 是該 close batch 的 notional，**math 在每筆獨立看是正確的**。
- 「× 2」：entry+exit 各 1 次費。1:1 場景成立。partial-close / accumulate 場景偏差見 §1.1.3。

數學自身沒錯，但「實況 vs counterfactual 1:1 假設」的 framing 需在 doc 補揭露。

#### 1.2.2 smoke test 自我驗證

跑 `--smoke-test`：
- Synthetic row 1: gross=4 / notional=4000 → 10 bps gross; fee=2.0 → cf=10-4=6 win
- Synthetic row 2: gross=-8 / notional=4000 → -20 bps gross; fee=2.0 → cf=-20-4=-24 loss
- Edge=(6-24)/2=-9, R:R=|6/-24|=0.25 ✅

聚合器數學正確。

### 1.3 Edge cases

| Edge case | 處理 | 評估 |
|---|---|---|
| `n_trades < 10` 全部 → exit 1 | 在 line 757-759 | 設計合理 |
| Per-symbol < 5 不入 markdown 但入 AGGREGATE | line 406-407（kept/dropped split）+ AGGREGATE 重跑 raw rows（line 320-359） | **正確設計**：AGGREGATE 從 raw rows 重跑，**不會被 small-sample 污染**。E1 註解 line 316-319 已說明 |
| `fee_bps <= 0` | line 479 RaiseError | 正確 |
| `fee_bps > 1000` | line 481-484 sanity ceiling | 正確 |
| `lookback_days <= 0` | line 665-667 | 正確 |
| `notional <= 0` | line 221-225 defensive 0 return | 正確（即使 SQL 已 filter `qty > 0 AND price > 0`） |
| NaN / Inf realized_pnl | 無顯式檢查 | **LOW**：依賴 Rust `sanitize_f64_or_zero` 輸入端清洗。可加一行 `import math; if not math.isfinite(gross_pnl): continue` 防禦，但實務 PG 端應該已 sanitized |
| 空 rows | line 708-714 印 empty markdown + return 1 | 正確 |

### 1.4 規範合規

| 規則 | 結果 |
|---|---|
| CLAUDE.md §七 雙語注釋 MODULE_NOTE/docstring/inline | ✅ 全部齊備（11 個函數 + 模組頂部）|
| §七 跨平台路徑硬編碼 grep `/home/ncyu` `/Users/ncyu` | ✅ 0 命中（純 env / `Path(__file__)`）|
| §七 lazy import psycopg2 in main | ✅ line 182 lazy import in `_open_conn()` |
| §九 8 條 checklist | ✅ 全綠（無 except:pass / log %s 格式 / 無 detail=str(e) / 無 blocking lock / 無 _xxx 私穿透）|
| §九 800/1200 行 | ✅ 773 行（< 800 警告）|
| Read-only：無新 migration / 無 healthcheck pair 需求 | ✅ N/A |
| Singleton 登記 §九 | ✅ N/A（無新 singleton） |
| Bybit API 改動 | ✅ N/A（純 PG read-only） |

### 1.5 G2-02 findings

| # | 嚴重性 | 位置 | 描述 | 動作 |
|---|---|---|---|---|
| G2-02-F1 | **MEDIUM** | `ma_crossover_counterfactual_replay.py` 模組 docstring + `compute_per_trade_bps` docstring | partial-close（fast_track ReduceToHalf）+ accumulate（理論可能）下，counterfactual 公式假設「1 entry × 1 close per JOIN row」會偏差；docstring 沒揭露 | **退回 E1**：補 docstring 段落說明此 caveat，並在 markdown 輸出尾部加備註行 |
| G2-02-F2 | **LOW** | `PAIRED_FILLS_SQL` line 122-125 | INNER JOIN 缺 `entry.engine_mode = close.engine_mode AND entry.symbol = close.symbol` 防禦 | **LOW，可選**：E1 加上即可（一行 SQL，零成本防禦）|
| G2-02-F3 | **LOW** | line 757-766 | exit code 規格曖昧處理寬鬆於 spec（spec 嚴格要求 ≥1 symbol ≥30 才 0；E1 改成「全部 < 10 才 1」） | E1 報告 §不確定處 #4 已聲明；PM 已接受。**保留** |

---

## §2 G8-02 review

### 2.1 70-case 設計 adversarial

#### 2.1.1 「70 case 全聚焦 shadow_mode 是 trivial pass 嗎？」

**部分屬實，但設計仍有價值**。分析：

- 70 case：30 golden + 40 synthetic
- 40 cases shadow_mode=true → expected `block_shadow`
- 30 cases shadow_mode=false → expected `submit`
- Reference spec：`if shadow_mode: ("block_shadow", "shadow_mode") else ("submit", "live_intent_passthrough")` — 1 行 boolean check
- Python ExecutorAgent runtime：`if self._shadow_mode_provider(): → ipc_shadow path; else → ipc_real`

**100% agree 是定義性結果**：兩側都讀同一個 boolean。**測試的真正價值**：保護 G3-03 修復（移除 hardcoded `_shadow_mode = True`）不被 regression。如果未來有人再次 hardcode `shadow_mode = True`，30 個 `shadow=false` cases 會集體 disagree → 測試失敗。

但「parity test ≥95%」這個 framing 嚴重 **oversells 實際驗證內容**。實際是「ExecutorAgent runtime 對 shadow_mode boolean 的響應 vs schema 文義」，不是「Python ↔ Rust 跨進程 parity」。**E1 報告 §3.3 已誠實揭露這點**：「Reference spec is the schema's intent ... not Rust runtime」。**PM 接受了 E1 的解釋**。

**Adversarial 重審**：scope 收緊本身是合理的（cap/pct gate 確認未 wired，§2.1.2 驗證），但**「synthetic replay」這個詞極具誤導性**。詳見 §2.2.2。

#### 2.1.2 cap/pct gate 確認未 wired

我獨立 grep 驗證 E1 的 push back：

```bash
grep -rn "per_symbol_position_cap\|max_position_pct" \
  rust/openclaw_engine/src --include="*.rs" | grep -v test
```

結果：所有命中**只在** `config/risk_config_advanced.rs:770-843`（schema + validate）+ `config/risk_config.rs:134`（comment 說明哪些 knobs 屬此 sub-config）。**0 命中於 `intent_processor/`**。

讀 Python `executor_agent.py:511-567`：`_execute_via_ipc` **只**讀 `_shadow_mode_provider()`，無 cap / pct check。

**E1 push back 正確**：cap/pct 確實是 schema-only / runtime not gated → 屬 G3-08。將 cap/pct 用 `pytest.skip` 標明 deferred 是恰當設計。

### 2.2 Fixture 結構 review

#### 2.2.1 YAML schema vs ParityCase dataclass

7 fields 對齊：`case_id / source / description / config / intent / expected_decision / expected_reason`。✅
- `expected_decision` enum: `block_shadow | submit`（YAML 驗證 70 cases 全合規）
- `expected_reason` enum: `shadow_mode | live_intent_passthrough`
- 所有 case_id 唯一（`test_fixture_loaded_correctly` 驗證）

#### 2.2.2 ⚠️ 「synthetic_replay」是誤導性命名（對抗發現）

YAML 第 5 行宣稱：「`synthetic_replay` — deterministic seeded fake decision_outcomes」。

**事實**：40 個 `synthetic_*` cases 都是**手動寫的 YAML 字面量**。沒有 seed、沒有 generator、沒有 PG snapshot replay。和 30 個 `golden_*` 沒有結構性差別，只是命名不同。

讀 line 519-590 的 synthetic cases（樣本）：
```yaml
- case_id: synthetic_01_replay
  source: synthetic_replay
  description: replay row · BTCUSDT shadow=true buy
  config: { shadow_mode: true, max_position_pct: 0.05, per_symbol_position_cap: {} }
  intent: { symbol: BTCUSDT, side: Buy, qty: 0.0123, current_position_qty: 0.0 }
  expected_decision: block_shadow
  expected_reason: shadow_mode
```

完全是手寫，無「replay」性質。`description` 寫「replay row」是文字遊戲。

**Severity**：**MEDIUM**。文檔欺騙性強，會誤導 PM/QC 以為測試已從真實 `decision_outcomes` 取樣驗證。實際只是 70 個 hand-crafted cases 而已。**動作**：退回 E1 把 `synthetic_replay` 改成 `synthetic_handcrafted` 或 `extra_handcrafted`，並修正 fixture 註解 + test class docstring + 報告對應段落。

#### 2.2.3 PG 連線確認未開

讀 test 全文：無 `psycopg2.connect`、無 `OPENCLAW_DATABASE_URL`、無 SQL 字串。✅
fixture 從 YAML 讀，`Path(__file__).resolve().parent`。✅

### 2.3 Mock 邊界 review

#### 2.3.1 IPC channel 確實未開

`_drive_python_decision` 用 `cache._inject_snapshot_for_tests(snapshot)` + `cache._mark_initialized_for_tests()` 直接注入。讀 `executor_config_cache.py:377-388` 確認這兩個 method 只動 `_snapshot` + `_initialized`，不啟動 `_thread`。✅

`paper_trading_routes._ipc_command` 用 `_IpcCallRecorder` patch（`unittest.mock.patch`）。✅

#### 2.3.2 ⚠️ Singleton reset 跨 case 隔離是 **dead code**

`setup_method` / `teardown_method` 呼 `ecc_mod._reset_for_tests()`，但 `_drive_python_decision` 創建的是**本地 cache 實例**（line 234: `cache = ExecutorConfigCache()`），不是 singleton（`get_executor_config_cache()`）。

讀 `executor_agent.py` 全文：無 `get_executor_config_cache` 呼叫。`ExecutorAgent` 只透過注入的 `shadow_mode_provider` 讀 cache，所以本地實例的 lambda 完全和 singleton 隔離。

**結論**：`setup_method` / `teardown_method` 的 `_reset_for_tests()` 在當前測試結構下是 **defensive no-op**。功能正確（不會傷害），但語義偏差 — 註解說「防止 stale snapshot leak」，實際根本沒 leak 風險（因為沒用 singleton）。

**Severity**：**LOW**。可選清理：要嘛改用 `get_executor_config_cache()` + `_reset_for_tests()` 形成 self-consistent 配對，要嘛刪掉 reset 並改註解說明「本地 cache 實例，無需 reset」。**保留 fix 自由給 E1**。

#### 2.3.3 `_IpcCallRecorder` 真實性

讀 line 181-204 的 recorder：
- async `__call__` 簽名匹配 `paper_trading_routes._ipc_command`（method, params） → Awaitable[dict]
- shadow path 預期 `calls == []`（line 271-274）
- live path 預期 `calls == [submit_order]`（line 280-283）
- 還含 `success=False` 路徑可選（line 197-198）但 70 case 沒用到

設計乾淨 ✅。

### 2.4 規範合規

| 規則 | 結果 |
|---|---|
| CLAUDE.md §七 雙語注釋（class / method docstring + MODULE_NOTE） | ✅ 全部齊備 |
| §七 跨平台路徑 grep `/home/ncyu` `/Users/ncyu` | ✅ 0 命中 |
| §七 LocalLLMClient 不洩漏 | ✅ N/A（不調用 LLM） |
| §九 8 條 checklist | ✅ 全綠 |
| §九 800/1200 行 | ⚠️ test 主檔 503 < 800 ✅；fixture 838 > 800 但 fixture 是 data 非 code，**不算違規**（規範針對代碼檔案）|
| Singleton 登記 §九 | ✅ 不新增 singleton（測試用既有 `_CACHE_INSTANCE`） |
| Bybit API | ✅ N/A |
| PA RFC Q2 「3 decision points」 | ⚠️ E1 收緊到 1（shadow_mode）+ skip cap/pct；驗證後此收緊正確 |
| PA RFC Q2 「70 case ≥67/70 = 95.7%」 | ✅ 70/70 = 100%（trivially） |

### 2.5 ⚠️ Dead imports

```python
import asyncio  # line 67 — 只在 _execute_via_ipc 內部 `import asyncio` 重 import，本檔內未直接使用
import os       # line 68 — 全檔未使用
```

**Severity**：**LOW**。E2 規則允許直接修。

### 2.6 G8-02 findings

| # | 嚴重性 | 位置 | 描述 | 動作 |
|---|---|---|---|---|
| G8-02-F1 | **MEDIUM** | `executor_parity_cases.yaml` line 5 + 513-518；`test_executor_decision_parity.py` MODULE_NOTE + class docstring 多處；E1 報告對應段 | 「synthetic_replay」用詞誤導 — 40 個 case 是手寫 YAML 字面量，無 seed、無 generator、無 PG replay；實際是 hand-crafted，名實不符 | **退回 E1**：rename `synthetic_replay` → `synthetic_handcrafted`（或 `extra_handcrafted`）；同步更新 fixture 註解、test class docstring、report 對應段 |
| G8-02-F2 | **LOW** | line 67-68 | `import asyncio` + `import os` 未使用 | **E2 直接 fix**（dead import 屬規則允許直修） |
| G8-02-F3 | **LOW** | `setup_method` / `teardown_method` line 320-326 | `ecc_mod._reset_for_tests()` 在當前測試結構下是 dead code（本地 cache 實例不是 singleton） | **可選 LOW**：建議 E1 補註解說明 reset 是防禦性，或改用 singleton 走完整路徑 |

---

## §3 對 E1 兩個 push back 的判定

### 3.1 G2-02 push back：PM SQL spec 有 7 個欄位錯，E1 改用 `trading.fills` self-INNER-JOIN

**判定**：✅ **E1 push back 正確且必要**

E1 的 schema 反查精確：
- PM spec 用 `o.realized_pnl_bps`、`o.entry_price`、`o.exit_price`、`o.owner_strategy`、`ef.fee_bps_total`、`ef.entry_fee_rate`、`ef.exit_fee_rate` — 我獨立驗證 V003 / V008 / V015 / V017 / V999 schema 都不存在這些欄位
- E1 改 design 用 `trading.fills` self-JOIN + V017 `entry_context_id` linkage 是當前 schema 唯一可行的 entry/close 配對方式
- 「`realized_pnl` 是 GROSS」結論經我獨立讀 `fill_engine.rs::apply_fill` line 273-279 + `trading_writer.rs:307` 確認屬實

**唯一需補強的地方**（§1.1.3 G2-02-F1）：partial close / accumulate 偏差未在 docstring 揭露 — 這不是 push back 本身的問題，是 E1 設計的次生 caveat 沒講清。退回補 doc 即可。

### 3.2 G8-02 push back：scope 收緊到 shadow_mode + cap/pct skip-marker

**判定**：✅ **E1 push back 技術上正確**，但**附帶誤導命名**（§2.2.2）

驗證：
- 我獨立 grep `rust/openclaw_engine/src --include="*.rs"` 確認 `per_symbol_position_cap` / `max_position_pct` 在 schema 外無 runtime 使用
- 讀 `executor_agent.py::_execute_via_ipc` 確認 Python 端只 gate 在 shadow_mode
- E1 設計 `TestExecutorDecisionParityDeferred` + `pytest.skip` reason 字串標明 G3-08 dependency 是合理的「保留 gap 可見度但不阻塞 Wave-3 收尾」

**G3-08 dependency 是真的還是假的？**
- **真的**。G3-08 不是「等 H1-H5 / Rust IPC Gateway」這個高層需求；是更具體的 `intent_processor` 內加 `executor.per_symbol_position_cap` / `executor.max_position_pct` gate 邏輯。schema 已落但 enforce code 未寫，需要新 PR 動 `intent_processor/mod.rs`。
- **PM 描述的「H1-H5 → Rust IPC Gateway 才能補」是誤判**。實際 G3-08 只需 Rust intent_processor 加幾行 cap/pct check + Python ExecutorAgent 加對應 pre-IPC gate（鏡像）。和 H1-H5 / IPC Gateway 沒有直接耦合。
- E1 用 `pytest.skip` + reason 字串「intent_processor cap gate depends on G3-08」是準確的（G3-08 是這個 PR 編號，不是更深的 phase）。

**push back 本身正確**。但 **§2.2.2 的「synthetic_replay」命名誤導**讓整個交付的「驗證了什麼」對 PM / QC 不透明。退回 E1 修命名。

### 3.3 PM 已接受兩個 push back — 是否該 override？

**不 override**。我同意兩個 push back 的核心技術判斷：
1. G2-02：PM SQL spec 是 schema 錯誤；E1 改設計合理
2. G8-02：cap/pct 不在 runtime → skip marker 是合理 deferred 處理

但兩個交付都需要**補強透明度**（doc / 命名）才達到 senior dev 的水準。Wave 3 不阻塞，但兩個 conditions 必修。

---

## §4 E2 結論

### Verdict：**PASS with conditions**

兩個交付**不需要重新設計或重寫業務代碼**，主體可進 E4。但以下 conditions 必須在進 E4 前由 E1 修完：

#### 退回 E1 必修清單

| # | Severity | 對應 finding | 修法 |
|---|---|---|---|
| 1 | MEDIUM | G2-02-F1 | `ma_crossover_counterfactual_replay.py` 模組 docstring 補一段 ~10-15 行說明 partial-close + accumulate counterfactual 偏差；`render_markdown` 尾部加 `_Note:_` 行揭露此 caveat |
| 2 | MEDIUM | G8-02-F1 | rename `source: synthetic_replay` → `source: synthetic_handcrafted`（或 `extra_handcrafted`）於 YAML 70 case 中 40 個；對應更新 fixture 註解 line 5 + line 513-518、test class docstring（`source` enum 描述）、E1 report 對應段 |

#### E2 直接 fix（已授權範圍）

| # | Severity | 修法 |
|---|---|---|
| 3 | LOW | G8-02-F2 移除 `import asyncio` + `import os`（dead import）|

#### 可選（不阻塞，但建議）

| # | Severity | 建議 |
|---|---|---|
| 4 | LOW | G2-02-F2 `PAIRED_FILLS_SQL` 加 `AND entry.engine_mode = close.engine_mode AND entry.symbol = close.symbol` 防禦 |
| 5 | LOW | G8-02-F3 `setup_method` / `teardown_method` 補註解說明本地 cache 不需 reset，或改走 singleton 一致化 |

#### G2-02-F3（exit code spec 寬鬆解讀）

E1 已在報告聲明 + PM 已接受 → **保留現狀**。

---

## E2 直接 fix 執行記錄

E2 規則允許直接 fix `obvious typo / lint / dead import`。本 review 將 G8-02-F2（dead imports）執行如下：

```python
# 修前 line 67-68
import asyncio
import os

# 修後
（兩行刪除）
```

修完後跑一次 pytest collection 確認沒有破壞（asyncio 在 `_execute_via_ipc` 內部 `import asyncio` 重 import，本檔內無外層需求；os 全檔 0 使用）。

---

## 資料補充：對抗反問記錄

| 問題 | E1 答案 / 我的驗證 | 評估 |
|---|---|---|
| 「你說 realized_pnl 是 GROSS — 讀過 apply_fill 哪幾行？」 | E1 引 fill_engine.rs:apply_fill 第 3 段；我讀 line 264 (balance -= fee), 273-279 (pnl = price diff), 307 (writer push_bind) 三點交叉確認 | ✅ E1 驗證可靠 |
| 「partial close 怎處理？」 | E1 沒主動說；我獨立發現 fast_track::ReduceToHalf 觸發 partial close → JOIN 多 row → counterfactual 過扣 fee | ⚠️ 揭出 G2-02-F1 |
| 「entry_context_id 在 accumulate fills 上的行為？」 | E1 docstring 未涵蓋；我讀 accessor.rs:194-209 set_entry_context_id 註解「accumulate fills must not overwrite」+ commands.rs:184 `if was_open && realized_pnl == 0.0` 確認 | ⚠️ 揭出 accumulate 漏 entry-side 多筆的 caveat |
| 「synthetic 真有 replay 嗎？」 | E1 報告 §3.3 自稱「synthetic seeded random」；我讀 fixture 全 70 case 都是 hand-crafted YAML，0 generator code、0 PG snapshot | ⚠️ 揭出 G8-02-F1 命名誤導 |
| 「cap/pct 真不在 runtime 嗎？」 | E1 grep `executor\\.` 確認；我獨立 grep 驗證 0 命中於 intent_processor | ✅ 確認 |
| 「Singleton reset 在做什麼？」 | E1 docstring 「防止 stale snapshot leak」；我讀 `_drive_python_decision:234` 創建本地 cache 實例 + executor_agent.py 0 個 `get_executor_config_cache` 呼叫 → reset 是 dead code | ⚠️ 揭出 G8-02-F3 |

---

## 完成標誌

```
E2 REVIEW DONE: PASS with conditions
report path: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-26--wave3_e1_review.md

退回 E1 必修：
  - G2-02-F1 (MEDIUM, doc) — partial-close / accumulate counterfactual 偏差揭露
  - G8-02-F1 (MEDIUM, naming) — synthetic_replay → synthetic_handcrafted

E2 直接 fix（dead imports）：
  - G8-02-F2 (LOW) — remove import asyncio + import os from test_executor_decision_parity.py

可選改進（不阻塞）：
  - G2-02-F2 (LOW) — JOIN 加 engine_mode/symbol 防禦
  - G8-02-F3 (LOW) — setup/teardown reset 註解或改用 singleton

E1 兩個 push back 判定：
  - G2-02 push back ✅ 正確且必要
  - G8-02 push back ✅ 技術正確（但命名誤導需修）

PM 已接受兩個 push back — 不 override。
```
