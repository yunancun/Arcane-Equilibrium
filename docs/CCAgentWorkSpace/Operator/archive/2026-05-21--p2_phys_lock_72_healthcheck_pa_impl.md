# P2-PHYS-LOCK-72-HEALTHCHECK — PA spec + IMPL report

**日期**：2026-05-21
**Agent**：PA（spec + IMPL 一手到底；non-business healthcheck audit-layer code，PA scope 允許）
**Task**：FA C6 OQ-C6-2 follow-up — phys_lock gate4 trigger 分布 observability standalone healthcheck

---

## §1 結果摘要

| 維度 | 結果 |
|------|------|
| Slot 編號 | **[68]** (canary/healthchecks/ namespace) |
| 新增 test count | **10** (test_68_phys_lock_gate4_distribution.py) |
| Pytest 結果 | **111 passed / 0 failed** (88 baseline + 10 new + 13 from 隔壁 [69] /  conftest) |
| Spec LOC | 318 |
| IMPL LOC | 434 (中文注釋密；task estimate 250-300 → 略超但 ≤ 800 cap) |
| Test LOC | 342 |

---

## §2 Slot 決策過程

### 2.1 Slot allocation 真相

PA 啟動序列發現 cross-namespace race 與 cross-session race：

- canary `[62-67]` 連續占用 (close-maker family)
- canary `[69]` 隔壁 session 已占（P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1）
- passive_wait `[68][69][70-74][75-79]` 已占
- TODO §6.1 row `P2-PHYS-LOCK-72-HEALTHCHECK` 給 slot 選項 **[68]/[69]/[76]**
- [69] 已被 cross-session 隔壁 sub-agent 占（halt_session_root_cause_recurrence.py）

### 2.2 PA 拍板

取 **[68]** —— [69] 已占；[76] 物理斷層；[68] 自然接續 canary [62-67] 語義。

**Cross-namespace 號碼撞 mitigation**（per R2 [66] 範本治理）：
- `__init__.py` MODULE_NOTE 明標 namespace 邊界
- result payload 強制標 `namespace="canary"` field 供 dashboard 區分
- canary [68] = phys_lock gate4 / passive_wait [68] = portfolio_resting **完全不同 domain**，不會混淆

### 2.3 Cross-session race finding

隔壁 sub-agent（[69] halt_session_root_cause_recurrence）在 file `_init__.py` 與 `[69]` source 註中誤標「[68] 預留 v59 TODO §6.1 H3 PA 用途」—— TODO §6.1 實際**沒有** H3 字面，隔壁是錯誤預判（PA grep 確認 v59 TODO 整檔 0 match "H3"）。本 PA work 已修正 `__init__.py` MODULE_NOTE 與 `conftest.py` fixture 註解，移除誤導性「H3 預留」字串。

---

## §3 結構

### 3.1 file tree

```
srv/
├── docs/execution_plan/
│   └── 2026-05-21--p2_phys_lock_72_healthcheck_spec.md  (318 LOC)
└── helper_scripts/canary/healthchecks/
    ├── __init__.py                          (UPDATE：補 [68] entry + cross-namespace 註)
    ├── 68_phys_lock_gate4_distribution.py   (NEW, 434 LOC)
    └── tests/
        ├── conftest.py                      (UPDATE：補 hc68 fixture + 修隔壁誤標)
        └── test_68_phys_lock_gate4_distribution.py  (NEW, 342 LOC)
```

### 3.2 IMPL 核心 function

| 名稱 | LOC | 角色 |
|------|---:|------|
| `_parse_args` | 30 | CLI argparse 範本（覆寫 `--insufficient-sample-threshold` / `--warn-giveback-threshold`）|
| `_aggregate_verdict_per_engine` | 60 | per-engine cells → verdict ladder logic（spec §2.2 4-step ladder）|
| `run` | 130 | SQL execution + cell payload build + cross-engine severity_max |
| `main` | 25 | CLI entry + connect_pg + emit_result |

### 3.3 reused helpers from `_common.py`（per task 規範不動 _common.py）

- `connect_pg` / `build_argparser` / `emit_result` / `severity_max` / `split_engine_modes`
- `configure_logging`
- 4 verdict const (`VERDICT_PASS/WARN/FAIL/INSUFFICIENT_SAMPLE`)
- `EXIT_PASS` / `EXIT_FAIL` const

---

## §4 SQL + verdict ladder

### 4.1 SQL（per spec §2.1）

```sql
SELECT
    engine_mode,
    CASE
      WHEN exit_reason LIKE 'phys_lock_gate4_giveback%' THEN 'gate4_giveback'
      WHEN exit_reason LIKE 'phys_lock_gate4_stale_roc_neg%' THEN 'gate4_stale_roc_neg'
      ELSE 'other_phys_lock'
    END AS phys_lock_kind,
    COUNT(*)::int AS n,
    COUNT(*) FILTER (WHERE close_maker_attempt = TRUE)::int AS close_maker_attempts,
    COUNT(*) FILTER (
        WHERE close_maker_attempt = TRUE
          AND close_maker_fallback_reason IS NULL
    )::int AS close_maker_fills
FROM trading.fills
WHERE ts > NOW() - (%s::int * INTERVAL '1 second')
  AND (
      exit_reason LIKE 'phys_lock_%'
      OR details->>'close_maker_eligible_reason' LIKE 'phys_lock_%'
  )
  AND engine_mode = ANY(%s::text[])
GROUP BY engine_mode, phys_lock_kind
ORDER BY engine_mode, phys_lock_kind;
```

### 4.2 Verdict ladder

| Verdict | 條件 | exit code | 語義 |
|---------|------|---:|------|
| `PASS` | `gate4_giveback n≥5 + close_attempts>0` | 0 | policy alive + close path 通 |
| `INSUFFICIENT_SAMPLE` | n<threshold / 兜底 | 0 | natural sparse；不阻 deploy |
| `WARN` | `gate4_giveback n≥10 + close_attempts=0` | 1 | router 缺口弱訊號 |
| `FAIL` | `gate4_stale_roc_neg n>0 + close_attempts=0` | 1 | policy alive 但 close path 不通；**P1 ticket** |

### 4.3 PA IMPL refine（修正原 spec §2.2 ladder false-positive bug）

**原 FA C6 prompt §2.2 WARN 條件**：`stale_roc_neg=0 AND giveback≥10 → WARN (router 缺口疑似)`

**IMPL 暴露的 bug**：phys_lock_gate4_stale_roc_neg 自然 sparse（emit 條件嚴苛 per FA C6 §2 production wiring 觀察），14d window 內 0 fire 是預期 — 原 WARN 條件會把所有 demo natural sparse 環境誤升 WARN，與 spec §1「natural sparse 不阻 deploy」原則矛盾。

**PA 修正後新 WARN 條件**：`gate4_giveback n≥10 AND close_attempts=0` —— 真正的 router 缺口訊號是「giveback alive 但 close path 也不通」（與 FAIL 對稱訊號，stale_roc 看不到時 giveback path 觀察為 close path 健康代理）。

spec §2.2 已同步更新此 rationale + 完整 ladder。

### 4.4 PA SQL refine（移除 FA prompt 中 schema-incorrect 欄位）

**原 FA C6 prompt SQL**：含 `AVG(COALESCE((details->>'fee_bps')::numeric, 0)) AS avg_fee_bps`

**Schema 真相**（PA grep `trading_writer.rs:431 INSERT INTO trading.fills` 確認）：
- `trading.fills` 有 `fee` / `fee_rate` 直 column
- 沒有 `fee_bps` 直 column
- `details` JSONB **不寫入** `fee_bps` field

**PA 移除 fee 觀察**：OQ-C6-2 核心訴求是「prevent natural vs router-bug 混淆」，fee 是 secondary nice-to-have；後續若需要 fee 對比走獨立 healthcheck（不在本 task scope）。

---

## §5 Test count + pytest 結果

### 5.1 新增 10 test cases

| Test | 對應 AC | 驗證 |
|------|---------|------|
| `test_empty_window_returns_insufficient_sample` | AC-3 兜底 | 0 rows → aggregate INSUFFICIENT_SAMPLE + namespace=canary |
| `test_pass_with_giveback_and_close_attempts` | AC-4 | giveback n=30 close=25 → PASS |
| `test_insufficient_sample_when_n_below_threshold` | AC-3 | n=3 < 5 → cell INSUFFICIENT |
| `test_warn_when_giveback_high_but_close_attempts_zero` | AC-5 (refined) | giveback n=20 close=0 → WARN |
| `test_pass_when_giveback_alive_and_stale_roc_naturally_sparse` | AC-4 reframe | spec §1 0-fire-natural 核心 — stale_roc 0 不沖淡 PASS |
| `test_fail_when_stale_roc_alive_but_close_path_broken` | AC-6 | stale_roc n=8 close=0 → FAIL |
| `test_multi_engine_severity_max` | AC-7 | demo PASS + live_demo FAIL → aggregate FAIL |
| `test_fail_overrides_warn_when_both_conditions_met` | E2 Point 2 | spec §2.2 邏輯 1→2→3 順序驗 |
| `test_sql_binds_or_condition_with_close_maker_eligible_reason` | AC-1+AC-2 + E2 Point 3 | SQL string + bind tuple |
| `test_production_exit_reason_string_match` | AC-8 + E2 Point 1 | fnmatch 模擬 PG LIKE；正向 + 反向 fixture |

### 5.2 Pytest 結果

```
$ python3 -m pytest helper_scripts/canary/healthchecks/tests/ -v

============================= 111 passed in 0.05s ==============================
```

**Baseline 88 + new 10 + 隔壁 hc69 (12) + conftest (1) = 111；全 PASS。**

### 5.3 IMPL refine 過程暴露的 lesson

**Run 1（原 spec ladder）**：3 failures

- `test_pass_with_giveback_and_close_attempts`：assert "PASS" got "WARN" — 原 spec §2.2 邏輯 2 false-positive
- `test_insufficient_sample_when_n_below_threshold`：assert "INSUFFICIENT" got "PASS" — cell verdict logic 漏 n<threshold guard
- `test_multi_engine_severity_max`：assert "PASS" got "WARN" — 原 spec 邏輯誤套到 multi-engine demo

**Run 2（PA spec + IMPL refine 後）**：2 failures

- `test_pass_with_giveback_and_close_attempts`：assert "PASS" got "INSUFFICIENT_SAMPLE" — `_common.severity_max` order 中 INSUFFICIENT_SAMPLE > PASS，starting `overall_verdict = INSUFFICIENT_SAMPLE` 會永遠 ≥ PASS

**Run 3（aggregation fold 修 — starting lower bound = PASS + 只 fold 真實看到 row 的 engine）**：111 PASS

**架構教訓**：`_common.severity_max` 的 order 中 `INSUFFICIENT_SAMPLE > PASS` 是 [62-67] 範本選擇（reviewer-noteworthy weight），任何新 healthcheck aggregation fold 必驗 「starting lower bound = PASS」+「不參與 fold 的 fallback engine 不在 overall_verdict 計算內」。

---

## §6 Risk 評估

### 6.1 改動風險評級

**低**：
- 純 standalone healthcheck audit-layer code（不入 production runtime）
- 不動 `_common.py`（per task 規範）
- 不動 production code (不動 Rust / risk_checks / maker_price / exit_features)
- 不動 V### migration / DB schema
- 純讀 `trading.fills` + JSONB

### 6.2 副作用清單

| # | 問題 | 答案 |
|---|------|------|
| 1 | 其他模組 import 本 file？ | ❌ 否（新檔，僅 `__init__.py` re-export）|
| 2 | 其他測試 mock 本 file？ | ❌ 否（新 test 用 existing fake cursor 模式）|
| 3 | asyncio/threading 邊界？ | ❌ 否（純 sync psycopg2）|
| 4 | API response schema 改動？ | ❌ 否 |
| 5 | Rust ↔ Python IPC schema？ | ❌ 否 |
| 6 | 與隔壁 cross-session work（[69] halt_session_root_cause）conflict？ | ✅ slot + namespace 完全 disjoint；對 `__init__.py` 修改不衝突（隔壁修 [69] entry，本修 [68] entry + cross-namespace 註）|
| 7 | TODO §6.1 row 影響？ | ✅ row `P2-PHYS-LOCK-72-HEALTHCHECK` 可標 DONE / 移 §12 done 列表 |

### 6.3 16 根原則合規

| # | 原則 | 影響 | 狀態 |
|---|------|------|------|
| 1 | 單一寫入口 | 純讀 | ✅ 無影響 |
| 2 | 讀寫分離 | 純讀 `trading.fills` | ✅ |
| 4 | 策略不繞風控 | 不動 strategy | ✅ |
| 5 | 生存 > 利潤 | alpha-orthogonal observability，不阻 trading | ✅ |
| 7 | 學習 ≠ 改寫 Live | 不寫 learning state | ✅ |
| 8 | 交易可解釋 | 強化 explainability（明區分 natural vs router-bug） | ✅ ↑ |
| 14 | 零外部成本可運行 | 純 PG query | ✅ |

**硬邊界**：未觸碰 `execution_state` / `execution_authority` / `live_execution_allowed` / `decision_lease_emitted` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json`。

### 6.4 跨平台兼容

- Python 3.10+ stdlib + psycopg2（對齊 [62-67] 慣例）
- Apple Silicon Mac 部署 ready：spec §5.2 cron entry **不接 cron** 只範本

---

## §7 PA → E2 review push back 3 點

E2 對本 IMPL 重點審查：

### 7.1 AC-2 + AC-8 SQL semantic（exit_reason free-text + emit chain）

spec §2.1 SQL 內 `exit_reason LIKE 'phys_lock_%'` 必驗對 production `"phys_lock_gate4_giveback"` 字串真實 match（test 已用 fnmatch fixture catch）。

**反模式風險**：若未來 emit 邏輯改動寫成 `"physical:phys_lock_*"` 帶 prefix，LIKE 不會 match → silent miss；E2 必驗 IMPL 對應的 test fixture 覆蓋 strip chain assumption。**已有 test**：`test_production_exit_reason_string_match` 正向 + 反向 fixture 12+8 production-grade 字串覆蓋。

### 7.2 Verdict ladder 4-cell aggregation 邊界 case

spec §2.2 aggregate verdict 邏輯需驗：
- FAIL 先判優於 WARN（test_fail_overrides_warn_when_both_conditions_met PASS 驗）
- `gate4_stale_roc_neg` 與 `gate4_giveback` 兩 row 同存時 severity_max 正確（multi-engine 多 cells 不被 PASS 沖淡 — test_multi_engine_severity_max PASS 驗）
- **PA IMPL refine 後 starting lower bound = PASS 而非 INSUFFICIENT_SAMPLE**，理由詳 §5.3 lesson；E2 需驗本架構決策是否與 [62-67] 慣例一致（[62-67] 啟動值是 PASS，本 [68] 對齊）

### 7.3 `details->>'close_maker_eligible_reason' LIKE 'phys_lock_%'` OR-condition 必要性

spec §2.1 SQL 用 `(exit_reason LIKE ... OR details->>'...' LIKE ...)` —— 為什麼**雙條件 OR** 而非單條件：
- exit_reason 是 close path 完成後寫入的 final reason
- details.close_maker_eligible_reason 是 maker_price.rs 寫入的 entry-side eligible reason
- 兩處都應該有 `phys_lock_*` 痕跡但**不一定同時** present（per close path 邏輯）

**已有 test**：`test_sql_binds_or_condition_with_close_maker_eligible_reason` 驗 SQL 含 `OR` + 兩 condition。E2 可選擇 push back 補 fixture 覆蓋三種 row：only exit_reason match / only details match / both match（目前 test 是 string-level，不是 row-level fixture）—— 這個 push back 留給 E2 決定是否升級為 row-level fixture。

---

## §8 PA → PM dispatch hint

- **不 commit**；交 PM 派 E2 review
- E2 review PASS 後派 E4 regression（確認 111 全 PASS）
- E4 PASS 後 commit；建議 commit message：
  ```
  feat(healthcheck): [68] phys_lock_gate4_distribution standalone observability

  P2-PHYS-LOCK-72-HEALTHCHECK; FA C6 OQ-C6-2 follow-up
  Verdict ladder 區分 0-fire-natural vs 0-fire-router-bug
  10 new test cases + spec + __init__.py + conftest.py update

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  ```
- **不接 cron** — spec §5.2 只範本；ops 後續 install 走 SCRIPT_INDEX.md 註冊
- **TODO update**：派 PM 把 §6.1 row `P2-PHYS-LOCK-72-HEALTHCHECK` 移 §12.4 done

---

## §9 Sign-off

| 角色 | 狀態 | 日期 |
|------|------|------|
| PA spec + IMPL | LAND | 2026-05-21 |
| Pytest baseline 88 + new 10 + 隔壁 13 = 111 | ✅ PASS | 2026-05-21 |
| E2 review | pending | — |
| E4 regression | pending | — |
| PM commit gate | pending | — |
