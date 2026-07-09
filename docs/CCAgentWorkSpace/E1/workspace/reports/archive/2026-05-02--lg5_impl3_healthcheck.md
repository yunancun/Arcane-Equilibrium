# LG-5-IMPL-3 Healthcheck `[42]` + `[42b]` — E1 完成報告

**Date**: 2026-05-02 15:24 UTC
**Wave**: LG-5 Wave 3 並行任務 #1 of 2（與 IMPL-4 integration tests 並行）
**RFC source**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md` §6 IMPL-3

---

## 1. 任務摘要

實作 LG-5-IMPL-3 兩個被動等待 healthcheck：

- **`[42] live_candidate_eval_contract`** — 驗 `review_live_candidate` 1h SLA + audit row 寫入；contract 系統性破裂時 lease_revoke_trigger 觸發。
- **`[42b] live_candidate_attribution_drift`** — 5 個 LG-5 strategy 7d 滾動 attribution_chain_ratio drift 偵測；PASS ≥ 0.50 / WARN [0.10, 0.50) / FAIL < 0.10。

驗證 12 unit test 全綠、0 regression、跨平台 0 hit、git diff --check 0、雙語注釋齊備。

完成狀態：✅ 已完成，待 E2 審查 → E4 回歸。

---

## 2. 修改清單

| Path | 動作 | 行數 | 說明 |
|---|---|---|---|
| `helper_scripts/db/passive_wait_healthcheck/checks_governance.py` | NEW | 344 | `[42]` + `[42b]` 兩個 check 實作 + 雙語 MODULE_NOTE + RFC 章節對齊 |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | MODIFIED | +35 | import + cursor block 內 wire-up + docstring 註冊 `[42]`/`[42b]` |
| `helper_scripts/db/passive_wait_healthcheck/__init__.py` | MODIFIED | +9 | re-export `check_42_*` / `check_42b_*` + `__all__` 更新 |
| `helper_scripts/db/test_lg5_healthchecks.py` | NEW | 213 | 12 unit test：`[42]` 5 path / `[42b]` 6 path / constants 1 |
| `docs/healthchecks/2026-05-02--lg5_health_checks.md` | NEW | 142 | 雙 healthcheck 觸發條件 / threshold / RFC 對應章節文件 |

**總計**：5 檔，2 新建 module + 2 wire-up + 1 doc。所有檔 < 800 LOC 警告線。

---

## 3. 關鍵 diff

### `[42]` SQL 核心 (RFC v2 §6 IMPL-3 line 451-454)

```python
sql_unaudited = (
    "SELECT count(*)::int AS unaudited_candidates "
    "FROM learning.mlde_param_applications c "
    "WHERE c.engine_mode = 'live' "
    "  AND c.application_type = 'live_promotion_candidate' "
    "  AND c.status = 'candidate' "
    f"  AND c.ts < now() - {CANDIDATE_AUDIT_SLA_INTERVAL} "
    "  AND NOT EXISTS ( "
    "    SELECT 1 FROM learning.governance_audit_log a "
    "    WHERE a.candidate_id = c.id "
    "      AND a.event_type = 'review_live_candidate' "
    "  )"
)
```

### `[42b]` per-strategy 7d ratio 計算 (RFC v2 §3 R-meta line 366-367)

```python
sql = (
    "SELECT strategy_name, "
    "       count(*)::int AS total, "
    "       count(*) FILTER (WHERE attribution_chain_ok)::int AS chain_ok, "
    "       (count(*) FILTER (WHERE attribution_chain_ok))::float "
    "         / nullif(count(*), 0)::float AS ratio "
    "FROM learning.mlde_edge_training_rows "
    f"WHERE ts > now() - {ATTRIBUTION_DRIFT_WINDOW} "
    "  AND engine_mode IN ('demo', 'live_demo', 'live') "
    "  AND strategy_name IS NOT NULL "
    "GROUP BY strategy_name"
)
```

### Verdict band 邏輯（pseudocode 對齊 RFC）

```python
worst_strategy = min(LG5_STRATEGIES, key=lambda s: ratios[s])
worst_ratio = ratios[worst_strategy]

if worst_ratio >= 0.50:    # ATTRIBUTION_RATIO_PASS_FLOOR
    return ("PASS", ...)
if worst_ratio >= 0.10:    # ATTRIBUTION_RATIO_FAIL_FLOOR
    return ("WARN", ...)   # R-meta defer
return ("FAIL", ...)       # pipeline-level alert; lease_revoke_trigger
```

### Runner wire-up（cursor block，`[41]` 之後）

```python
s, m = check_42_live_candidate_eval_contract(cur)
results.append(("[42] live_candidate_eval_contract", s, m))

s, m = check_42b_live_candidate_attribution_drift(cur)
results.append(("[42b] live_candidate_attribution_drift", s, m))
```

---

## 4. 治理對照

### RFC v2 對齊

| RFC 章節 | 對齊點 |
|---|---|
| §3 R-meta line 366-367 | `[42b]` PASS floor 0.50 — 與 `review_live_candidate` defer 閾值一致 |
| §3 line 377 | `[42b]` FAIL floor 0.10 — pipeline-level alert + MIT MF-M5 cross-ref |
| §4 line 404 | `[42]` 列為 `lease_revoke_triggers` — FAIL msg 明文標示「lease_revoke_trigger fires」 |
| §4 line 405 | `[42b]` 列為 `lease_revoke_triggers` — FAIL msg 明文標示「GovernanceHub must auto-revoke active leases」 |
| §6 IMPL-3 line 451-454 | `[42]` 1h SLA + audit row 契約完整實作 |

### CLAUDE.md 規範

| 規範 | 符合性 |
|---|---|
| §七 雙語注釋（MODULE_NOTE / docstring / inline） | ✅ 全 6 個函數中英對照、模組 MODULE_NOTE 雙語、constants 雙語注釋 |
| §七 跨平台兼容性（路徑禁硬編碼） | ✅ `grep -E '/home/ncyu\|/Users/[^/]+/'` 0 hit |
| §七 「被動等待 TODO 必附 healthcheck」 | ✅ 本實作即為該規範的標準範例 — 兩個 check 各回 PASS/WARN/FAIL，FAIL 即觸發告警 |
| §九 800 行警告 / 1500 硬上限 | ✅ checks_governance 344 / test 213 / runner 659（含新增） |
| §九 新 singleton 必登記 | ✅ 不引入新 singleton |

### 不觸動硬約束（per task spec）

- ✅ 未動 V035 / V001-V034 SQL（已 land）
- ✅ 未動 `governance_hub_live_candidate_review.py` / `mlde_demo_applier.py` / `governance_hub.py`
- ✅ 未動 strategy params toml / risk_config toml
- ✅ 未 commit / push（PM 統一 Wave 3 batch）
- ✅ 未動 RFC v2 文檔
- ✅ 純 Python control plane，未碰 Rust

---

## 5. 不確定之處

### 5.1 `[42b]` PASS floor 邏輯：與 RFC §3 完全一致

RFC §3 R-meta defer 閾值 < 0.50。本實作 PASS = ≥ 0.50 / WARN = [0.10, 0.50)，
保證任何進入 `review_live_candidate` defer 區間的 strategy 在 healthcheck 至少 WARN。
RFC v2 §3 line 377 提到 `[42b]` 有「per-strategy <0.10 = pipeline-level alert」描述，
本實作 FAIL floor 對齊。

**風險點**：RFC 沒明文說 `[0.10, 0.50)` 該 WARN 還是 FAIL。task spec 給的偽碼明文寫 WARN，
本實作採 task spec。E2 / QC 若認為 0.30-0.50 應 FAIL（避免 review_live_candidate 進 defer 才被動發現），
可調整 `ATTRIBUTION_RATIO_PASS_FLOOR` 常量；改動點集中於 1 個常量。

### 5.2 `[42]` SLA 1h 是否需配合 IMPL-2 consumer 實際延遲

如果 IMPL-2 consumer 實際處理時間經常接近 1h（例如 cron 跑 30min 或 lock 競爭多），
WARN band（1-2 件）可能成為 noise。建議部署後 7d 觀察 `unaudited_over_1h` 計數分布，
必要時 PA 可提案調整 SLA。本 sentinel 採 RFC 給定 1h，不擅自放寬。

### 5.3 first-deploy / production silent 路徑

`[42b]` 若全 5 個 strategy 在 7d 內 0 row，目前回 WARN 而非 FAIL。設計理由：
- greenfield deploy / 全靜默期 FAIL 過嚴（會觸發 lease_revoke_trigger 但無實際 attribution 漂移）。
- 但可能掩蓋「pipeline 全死」場景。

替代方案：與 `[24] signals_writer_freshness` / `[35] mlde_learning_data_contract` 組合判讀。
本 sentinel 維持 WARN（與 task spec 偽碼一致）。

### 5.4 跨平台風險

零跨平台代碼（純 SQL + dict）。Mac dev / Linux runtime 行為一致。

### 5.5 測試覆蓋判斷

- `[42]` 5 個 path：PASS（unaudited=0）/ WARN（unaudited=2）/ FAIL（unaudited=5）/ V035-missing / V032-missing。完整覆蓋 verdict band 邊界 + fail-closed。
- `[42b]` 6 個 path：PASS（all ≥ 0.50）/ WARN（worst=0.30）/ FAIL（worst=0.05）/ missing-strategy / silent-deploy / V031-missing。覆蓋 verdict band + edge case + fail-closed。
- 未覆蓋：DB connection rollback 失敗（用 try/except 吞，不變更 verdict path），SQL exception fallback 路徑（單獨測 noise；既有 `test_mlde_healthchecks.py` 也未覆蓋此細節）。

---

## 6. Operator 下一步

### 已驗證（Mac CC 直接跑）

- ✅ `python3 -m py_compile` 0 error（4 個檔）
- ✅ `python3 -m unittest helper_scripts.db.test_lg5_healthchecks` 12 tests OK
- ✅ `python3 -m pytest helper_scripts/db/test_lg5_healthchecks.py -q --co` 12 tests collected
- ✅ `python3 -m unittest helper_scripts.db.test_mlde_healthchecks helper_scripts.db.test_lg5_healthchecks` 23 tests OK（0 regression）
- ✅ Package import 端到端：`from helper_scripts.db.passive_wait_healthcheck import check_42_*, check_42b_*, main` 成功
- ✅ `wc -l` 全部 < 800 警告線
- ✅ `git diff --check` 0 whitespace 問題
- ✅ Cross-platform path grep（`/home/ncyu` / `/Users/[^/]+/`）0 hit

### 待 E2 審查（next agent in chain）

- 雙語注釋密度合規（MODULE_NOTE / docstring / inline / SAFETY 完整性）
- SQL 注入安全（無 user input；常量唯一）
- runner.py wire-up 順序（cursor block 內，`[41]` 之後 `conn.close()` 之前）
- 與既有 check 風格一致性（`tuple[str, str]` 返回 / `cur.connection.rollback()` defensive）

### 待 E4 回歸（E2 審查通過後）

- 在 Linux runtime 對 real DB 跑 `passive_wait_healthcheck.py`，確認 `[42]` / `[42b]` 列出於 SUMMARY 行（不會 crash runner）
- 觀察首次部署 verdict（預期 `[42]` PASS、`[42b]` 視 7d 樣本量可能 PASS / WARN）

### 待 PM Sign-off + Wave 3 batch commit

- 不單獨 commit，等 IMPL-4 integration tests 同 wave 完成 → E2 全 wave 審查 → E4 回歸 → PM 統一 commit + push

### 不需 operator 親自動手

- 全部 Mac local 驗證完成，無需 SSH bridge 觸發 Linux 任務
- 無 high-risk per-case 授權項（純 Python control plane，不碰 secrets / authorization / Rust hot path）

---

## 7. 偽碼 threshold 對齊 RFC R-meta + MIT MF-M5

| Threshold | RFC source | 實作常量 |
|---|---|---|
| `[42]` SLA 1h | §6 IMPL-3 line 451-454 | `CANDIDATE_AUDIT_SLA_INTERVAL = "interval '1 hour'"` |
| `[42]` PASS=0 / WARN≤2 / FAIL≥3 | task spec 偽碼 + §4 lease_revoke_trigger 嚴重度 | `UNAUDITED_PASS_MAX=0` / `UNAUDITED_WARN_MAX=2` |
| `[42b]` PASS floor 0.50 | §3 R-meta line 366-367（defer 閾值） | `ATTRIBUTION_RATIO_PASS_FLOOR = 0.50` |
| `[42b]` FAIL floor 0.10 | §3 line 377 + MIT MF-M5 cross-ref | `ATTRIBUTION_RATIO_FAIL_FLOOR = 0.10` |
| `[42b]` 7d window | task spec | `ATTRIBUTION_DRIFT_WINDOW = "interval '7 days'"` |
| 5 LG-5 strategies | RFC §3 R-meta + §6 IMPL-1 (per-strategy dict 5 keys) | `LG5_STRATEGIES = ('grid_trading', 'ma_crossover', 'bb_breakout', 'bb_reversion', 'funding_arb')` |

---

## 報告路徑

- 本檔：`srv/.claude_reports/20260502_152434_lg5_impl3_healthcheck.md`
- 同步：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-02--lg5_impl3_healthcheck.md`
