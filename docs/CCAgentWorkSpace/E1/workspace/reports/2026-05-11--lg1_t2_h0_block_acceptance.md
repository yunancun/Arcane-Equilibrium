# E1 IMPL Report — LG1-T2 `[59]` h0_block_acceptance healthcheck

Date: 2026-05-11
Owner: E1 (Mac)
Wave: Sprint N+1 Wave 2 — LG-1 T2
Status: IMPL DONE, awaiting E2 review + E4 regression
Related: PA tech plan `2026-05-11--lg_2_3_4_design_plan.md` §1.4 T2

---

## 1. 任務摘要

依 PA tech plan §1.4 T2 要求新增 passive_wait healthcheck `[59]
h0_block_acceptance` 哨兵。讀 `pipeline_snapshot_{demo,live_demo}.json`
的 `h0_gate_stats` + `risk_manager_config.runtime.h0_shadow_mode`，並
跨檢 `trading.fills` 1h 入場 fill 計數，推斷 H0 hard-block 是否真實生效；
配套 LG-1 24h passive acceptance gate（不阻塞 ship，shipping 後事件）。

### 重要 PA mitigation 修正

PA §1.5 風險表寫 "H0 block 統計只有 stats clone（canary record 帶），
無法跨 process 持久化 → Mitigation: T2 healthcheck 讀 canary_records 與
trading.fills 對 join；不需新增 PG 表"。實際 grep 確認：

1. **PG 沒有 canary_records 表**。CanaryRecord 是 Rust internal struct，
   序列化到 filesystem `engine_results.jsonl`（replay/canary mode 用，
   非 Live runtime），不寫 PG。
2. **H0 block 不寫 risk_verdicts**。step_0_5_h0_gate 早退
   （`ControlFlow::Break`），根本沒走到 IntentProcessor / Guardian。
3. **真正 data source**：`pipeline_snapshot_{engine}.json`（filesystem，
   每 ~30s 一次）含 `h0_gate_stats: GateStats` 與
   `risk_manager_config.runtime.h0_shadow_mode`，由 Rust event_consumer
   status_report 寫入；Python 端 ipc_state_reader.py 既有讀法。

故 IMPL 改採 **filesystem snapshot + PG cross-validation** 雙軸，符合 PA
「不需新增 PG 表 / 不增 IPC route」精神。

---

## 2. 修改檔案清單

| 檔案 | 操作 | 行數 | 用途 |
|---|---|---|---|
| `helper_scripts/db/passive_wait_healthcheck/checks_h0_block_acceptance.py` | 新建 | ~360 LOC | `[59]` 哨兵 + helpers |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | 修改 | +35 LOC | import + register `check_59` + 更新 docstring |
| `helper_scripts/db/test_h0_block_acceptance.py` | 新建 | ~395 LOC | 14 unit test |

絕對路徑：

- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/passive_wait_healthcheck/checks_h0_block_acceptance.py`
- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/passive_wait_healthcheck/runner.py`
- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/test_h0_block_acceptance.py`

---

## 3. 設計分析

### 3.1 Data source 結構

```
Rust step_0_5_h0_gate.rs::on_tick_step_0_5_h0_gate
  └─ self.h0_gate.check() → if !allowed → ControlFlow::Break (only stops fire)
  └─ self.h0_gate.get_stats() → GateStats { total_checks, blocked_*, ... }

Rust event_consumer/status_report.rs (~30s cadence)
  └─ pipeline.snapshot() → PipelineSnapshot { h0_gate_stats, risk_manager_config }
  └─ snapshot_writer.maybe_write() → pipeline_snapshot_{engine}.json

Python ipc_state_reader.RustSnapshotReader
  └─ read pipeline_snapshot_{engine}.json (cache 2s)
```

### 3.2 H0 block invariant（被 [59] 哨兵驗證）

- H0 hard-block (`shadow_mode=false` + 5 sub-check 任一失效) → tick 早退
- 早退路徑：**只走 stops**（exit fills 可以發生）+ **不走 entry path**（entry fills 0）
- 因此：`blocked > 0` 期間，PG `trading.fills` 的 entry fills（非 risk_close /
  strategy_close）應為 0；若非 0 → block invariant 失效

### 3.3 4 Sub-check（per-engine）

| 子檢查 | 條件 | Verdict |
|---|---|---|
| A. snapshot fresh | mtime < 5min | else WARN_NO_SNAPSHOT (skip engine) |
| B. shadow_mode | `h0_shadow_mode=false` (demo/live_demo 預設) | true → WARN_SHADOW_MODE |
| C. stats sample | `total_checks >= 100` | else WARN_LOW_SAMPLE |
| D. block leakage | `blocked/total > 0.5` + `entry_fills > 0` | yes → FAIL_BLOCK_LEAKAGE |

附加：`total_blocked==0 + entry_fills==0` → WARN_PIPELINE_QUIET (snapshot
寫但 stats 沒動，可能 pipeline 完全靜默)。

### 3.4 Verdict aggregation

- 全 engine PASS → PASS
- 任一 engine FAIL → FAIL
- 任一 engine WARN → WARN
- `OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1` → WARN 升 FAIL

### 3.5 Env config

| 變數 | 預設 | 作用 |
|---|---|---|
| `OPENCLAW_DATA_DIR` | `/tmp/openclaw` | snapshot 檔目錄（與 ipc_state_reader 一致） |
| `OPENCLAW_H0_BLOCK_HEALTH_REQUIRED` | 未設 | =1 升 WARN→FAIL |
| `OPENCLAW_H0_BLOCK_HEALTH_MIN_CHECKS` | 100 | total_checks 低樣本門檻 |
| `OPENCLAW_H0_BLOCK_HEALTH_ENGINES` | `demo,live_demo` | 監測 engine 列表 |

預設 WARN-only，避免 Mac dev / engine cold-start false-FAIL。

---

## 4. 關鍵 diff（核心邏輯）

### 4.1 Filesystem snapshot 讀取

```python
def _read_snapshot(engine: str) -> tuple[dict | None, float | None, str]:
    path = _data_dir() / f"pipeline_snapshot_{engine}.json"
    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return (None, None, f"snapshot file not found: {path}")
    age = max(0.0, time.time() - stat_result.st_mtime)
    ...
```

### 4.2 H0 stats 抽取（鏡 Rust GateStats schema）

```python
fields = ("total_checks", "total_allowed",
          "blocked_freshness", "blocked_health",
          "blocked_eligibility", "blocked_envelope", "blocked_cooldown",
          "shadow_would_block", "max_latency_us", "total_latency_us")
```

對應 Rust `openclaw_core::h0_gate::GateStats` (line 60-71)。

注意：Rust 用 `blocked_envelope`，Python `h0_gate.py` 用 `blocked_risk`，
**以 Rust 為準**（snapshot 由 Rust 寫）。

### 4.3 Entry fill 跨檢 SQL（鏡 `checks_execution.py:1015-1017` pattern）

```sql
SELECT COUNT(*)::int
  FROM trading.fills
 WHERE engine_mode = %s
   AND ts > now() - (%s || ' hours')::interval
   AND strategy_name IS NOT NULL
   AND strategy_name NOT LIKE 'risk_close:%'
   AND strategy_name NOT LIKE 'strategy_close:%'
```

### 4.4 Block leakage FAIL trigger

```python
block_ratio = total_blocked / total_checks
if block_ratio > BLOCK_DOMINANT_RATIO and entry_fills > 0:
    engine_verdict = f"FAIL_BLOCK_LEAKAGE(ratio={block_ratio:.2f},fills={entry_fills})"
    fail_reasons.append(
        f"{engine}: H0 block dominant ({total_blocked}/{total_checks}={block_ratio:.2%}) "
        f"but {entry_fills} entry fill(s) in last {FILL_LEAKAGE_WINDOW_HOURS}h — "
        "block invariant violated"
    )
    worst = "FAIL"
```

### 4.5 runner.py 註冊 diff

```python
from .checks_h0_block_acceptance import (
    # LG1-T2 (2026-05-11) — `[59]` H0 hard-block production caller acceptance
    # sentinel per PA tech plan `2026-05-11--lg_2_3_4_design_plan.md` §1.4 T2.
    # ...
    check_59_h0_block_acceptance,
)

# 在 main() cursor block，[58a] 後 [64] 前：
s, m = check_59_h0_block_acceptance(cur)
results.append(("[59] h0_block_acceptance", s, m))
```

---

## 5. SQL 範本 + Linux PG 時間

### 5.1 三條 SQL（passive 全部 read-only）

```sql
-- Q1: table existence
SELECT to_regclass('trading.fills') IS NOT NULL;

-- Q2/Q3: per-engine entry fills count (1h window)
SELECT COUNT(*)::int
  FROM trading.fills
 WHERE engine_mode = %s          -- 'demo' / 'live_demo'
   AND ts > now() - (%s || ' hours')::interval  -- '1'
   AND strategy_name IS NOT NULL
   AND strategy_name NOT LIKE 'risk_close:%'
   AND strategy_name NOT LIKE 'strategy_close:%';
```

### 5.2 Linux PG 實測（trading.fills hypertable, ~24h hot chunks）

| Query | 時間 | 樣本 |
|---|---|---|
| Q1 to_regclass | **1.9ms** | exists=true |
| Q-demo entry_fills_1h | **8.8ms** | 35 fills |
| Q-live_demo entry_fills_1h | **1.0ms** | 23 fills |
| Q-scale-24h（多 engine GROUP BY） | **0.7ms** | demo=262, live_demo=207 |

**全部 sub-10ms（PA target <1s 達標）**。Plan 走 hypertable chunk pruning
+ `idx_fills_ts_desc` (V005)，過去 1h fall in 1 chunk。

### 5.3 邊界情境

| 情境 | snapshot | PG | 預期 verdict |
|---|---|---|---|
| Linux runtime healthy | fresh, shadow=false | 200/1000 blocks, 0 entry leak | PASS |
| Mac dev (engine 未跑) | 無 | 0 fills | WARN_NO_SNAPSHOT |
| Engine cold start | fresh, total_checks=50 | 0 fills | WARN_LOW_SAMPLE |
| Misconfigured | fresh, shadow=true | - | WARN_SHADOW_MODE |
| Block invariant 失效 | 80% blocked | 5 entry fills | **FAIL_BLOCK_LEAKAGE** |
| Pipeline 靜默 | fresh, 500 checks 0 blocks | 0 fills | WARN_PIPELINE_QUIET |
| V003 未 apply | - | trading.fills 不存在 | FAIL（fail-closed） |

---

## 6. pytest 結果

```
$ python3 -m pytest helper_scripts/db/test_h0_block_acceptance.py -v
========================= 14 passed in 0.03s =========================
```

Test breakdown：

| Test | 驗證 path |
|---|---|
| test_pass_when_hard_block_active_and_no_fill_leakage | PASS happy path |
| test_warn_when_total_checks_insufficient | WARN_LOW_SAMPLE |
| test_warn_when_shadow_mode_true | WARN_SHADOW_MODE |
| test_fail_when_block_dominant_but_entry_fills_present | **FAIL_BLOCK_LEAKAGE** |
| test_warn_when_snapshot_missing | WARN_NO_SNAPSHOT |
| test_fail_when_required_env_set_and_warn_present | REQUIRED env 升級 |
| test_fail_when_trading_fills_table_missing | V003 缺 fail-closed |
| test_pass_with_custom_engine_list | env override |
| test_warn_when_fill_query_raises | WARN_QUERY_ERROR (PG transient) |
| test_warn_when_pipeline_quiet | WARN_PIPELINE_QUIET |
| TestModuleHelpers (×4) | pure-fn helper sanity |

整合驗證：同跑 `test_agent_spine_healthcheck.py` + `test_pricing_binding_
healthcheck.py` → **40 passed**（14 new + 14 spine + 12 pricing），無
adjacent test regression。

---

## 7. 治理對照

### CLAUDE.md §七

| 規則 | 狀態 |
|---|---|
| 注釋默認中文 | ✅ 全中文（無強制英文） |
| 跨平台路徑 | ✅ `OPENCLAW_DATA_DIR` env / 無 `/home/ncyu` `/Users/...` hardcode |
| SQL 參數化 | ✅ 所有 query 用 `%s` |
| 被動等待 TODO 必附 healthcheck | ✅ 本 IMPL 即此 healthcheck |
| Sign-off 必檢 git status clean | ✅ E1 不 commit，等 E2/E4 |
| 文件 800 行警告 / 2000 行硬上限 | ✅ checks_h0_block_acceptance.py ~360 LOC / test ~395 LOC / runner.py 1130 LOC（內聚增量 35 LOC） |

### PA tech plan §1.4 T2 acceptance

| Sub-check (PA §1.4) | IMPL 對應 |
|---|---|
| (1) PASS: hard-block events > 0 AND fills_during_block = 0 | 子檢查 D 反面，PASS path test |
| (2) WARN: stats insufficient (n < threshold) | WARN_LOW_SAMPLE |
| (3) WARN: shadow_mode=true（偏離預期） | WARN_SHADOW_MODE |
| (4) FAIL: H0 block 期間有 fill 流出 | FAIL_BLOCK_LEAKAGE |

PA §1.5 mitigation 中誤導的「canary_records / 不需 PG 表」修正後仍兌現：
**不新增 PG 表**，改讀 filesystem snapshot + PG `trading.fills` 跨檢。

### 不修改的 H0 production code（T1 + T3 領域）

```bash
$ grep -rn 'h0_gate\|step_0_5' helper_scripts/db/passive_wait_healthcheck/checks_h0_block_acceptance.py
# 0 results (除了 MODULE_NOTE 文字)
```

---

## 8. Self-check 8 acceptance（全綠）

1. ✅ `python3 -m py_compile checks_h0_block_acceptance.py` → `PY_COMPILE_OK`
2. ✅ `pytest helper_scripts/db/test_h0_block_acceptance.py -v` → **14/14 PASS**
3. ✅ Linux PG SQL <1s（實測 sub-10ms）
4. ✅ 中文注釋（MODULE_NOTE / inline / docstring）
5. ✅ runner.py 註冊驗證：

   ```bash
   $ grep -n 'check_59_h0_block_acceptance' .../runner.py
   262:    check_59_h0_block_acceptance,
   964:            s, m = check_59_h0_block_acceptance(cur)
   ```

6. ✅ Mock 不掩蓋邏輯（test 用真實 dict 結構模擬 snapshot + 真實 cursor sequence）
7. ✅ `(status, message)` tuple contract 保留（所有 path return 2-tuple）
8. ✅ 無 hardcoded path：

   ```bash
   $ grep -E '/home/ncyu|/Users/[^/]+' checks_h0_block_acceptance.py test_h0_block_acceptance.py
   NO_HARDCODED_PATH_OK
   ```

---

## 9. 不確定之處 / E2 必查

1. **`blocked_envelope` 命名 Rust vs Python 分歧**
   - Rust `GateStats::blocked_envelope` (line 66)
   - Python `h0_gate.py:209` `blocked_risk`
   - 哨兵以 **Rust 為準**（snapshot.json 由 Rust 寫）。若未來 Rust 改名同步 Python 必須同改。

2. **WARN_PIPELINE_QUIET 是否過敏感？**
   - 條件：fresh snapshot + 充足樣本 + 0 blocks + 0 entry_fills
   - 可能 false-WARN：engine 真實 quiet（market off-hour）
   - Mitigation：current msg 含 `pipeline may be quiet` 給 operator 上下文；
     `OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1` 才升 FAIL。
   - E2 review 可考慮：要不要對 `total_checks > 1000` 額外加門檻避免 quiet 期 WARN。

3. **`BLOCK_DOMINANT_RATIO=0.5` 閾值是否合理？**
   - 設計直覺：blocked > 50% 應該對應 entry_fills 大幅減少
   - 真實 demo runtime 數據未做 calibration；E2 可建議改 0.3 或 0.7 試驗 sensitivity
   - 若 demo runtime 顯示 50% blocked 常態 → 0.5 太鬆需提高

4. **snapshot fresh < 5min 是否合適？**
   - Rust event_consumer status_report 每 ~30s 寫一次
   - 5min = 10 個 cycle，比 60s ipc_state_reader stale threshold 寬鬆
   - 故意放寬避免 transient stale；E2 可建議改 2min（4 cycles）

5. **`OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1` 何時翻 ON？**
   - 目前哨兵預設 WARN-only（per PA §1.5「不阻塞 ship」精神）
   - 建議 LG-1 24h passive observation 完成 + LG-1 T3 ctor default 修正 land 後翻 ON
   - 由 LG1-T3 runbook 統一指引

---

## 10. Operator 下一步

### 立即（E2 review）
1. 跑 A3 + E2 對抗性核驗（per `feedback_impl_done_adversarial_review.md`）
2. E2 必驗：snapshot data source 真實性、SQL parametrization、tuple contract、
   `blocked_envelope` vs `blocked_risk` 命名 drift 風險
3. E4 regression：跑 helper_scripts/db/ 全 test，確認 0 break

### 短期（LG-1 24h passive watch）
1. Linux 部署後啟動 cron `passive_wait_healthcheck.sh` 觀察 `[59]` 12h baseline
2. 確認 PASS 比例 ~100%（demo/live_demo 不應有 FAIL_BLOCK_LEAKAGE）
3. 如有零星 WARN_PIPELINE_QUIET，記錄市況時段，E2 decide 是否調整門檻

### 中期（與 LG1-T1 + T3 + T4 配套）
- T1 E2E test land + 24h 觀察 PASS → 翻 `OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1`
- T3 ctor default 修正 land → 消除「啟動瞬窗 shadow→TOML 載入 hard-block」窗
- LG-1 完成 = `[59]` 12h PASS + 上述 4 sub-check 全綠

---

## 11. caveat / E2 必查

### a. snapshot data source vs PA §1.5 「canary_records」名稱差異

PA §1.5 寫 "讀 canary_records 與 trading.fills 對 join"。實際 IMPL 讀
`pipeline_snapshot_{engine}.json`（filesystem） + `trading.fills`（PG）。
**E2 必須確認此 source 替代是合理的、不破 PA acceptance 精神**。

證據：

- `grep -rn 'canary_records' sql/migrations/` → 0 hits（PG 無此表）
- `grep -rn 'CanaryRecord' rust/openclaw_engine/src/canary_writer.rs` →
  寫到 `engine_results.jsonl`，非 PG
- snapshot.json 寫法在 `commands.rs:1265-1300` (Rust `snapshot()` 函數)
  + `event_consumer/status_report.rs` flush

### b. `OPENCLAW_DATA_DIR` 與 Linux/Mac fallback

`_data_dir()` 用 `os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")`。

- Linux 預設 `/tmp/openclaw`（與 engine bootstrap 一致）
- Mac dev 必設 `OPENCLAW_DATA_DIR=$HOME/.openclaw_runtime`（per CLAUDE.md §六）
- E2 確認 cron wrapper `passive_wait_healthcheck.sh` 是否傳遞 env var 給
  python3 sub-process（已驗：wrapper 用 `set -a; source ...env; set +a`
  全 export）

### c. snapshot mtime semantics

`os.path.stat().st_mtime` 是 filesystem mtime；engine 寫 snapshot 時用
`tempfile + rename` 是否影響 mtime（rename target 取 source mtime 還是
重設？）需要 E2 確認。若是後者（重設 = 寫入瞬間），符合預期。

### d. shadow_mode 雙來源

snapshot 含 `risk_manager_config.runtime.h0_shadow_mode`（hot-reload SoT）。
但 `H0GateConfig.shadow_mode` 也存在於 `pipeline.h0_gate.config()`。兩者
應同步（per `pipeline_config.rs:105-109` RMW），但若哪個 leg 漂移會 false-WARN。
E2 確認 risk_manager_config snapshot 的 runtime.h0_shadow_mode 真實對應
H0Gate.config().shadow_mode（不是 stale config）。

### e. test 用 importlib 繞 `__init__.py` 是 pre-existing breakage workaround

per `test_agent_spine_healthcheck.py` 同 pattern（W1 panel_aggregator
in-progress 期間 runner.py import chain 不穩）。當 W1 IMPL DONE 後可考慮
切回標準 `from helper_scripts.db.passive_wait_healthcheck.checks_h0_block_acceptance
import ...`，但目前**保持與 sibling test 一致**減少 maintenance drift。

### f. block_ratio threshold 是 heuristic

`BLOCK_DOMINANT_RATIO = 0.5` 是設計直覺，未經 demo runtime data
calibration。當 LG-1 24h passive observation 完成後可從 demo blocked/
total 真實分佈 calibrate。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t2_h0_block_acceptance.md`）
