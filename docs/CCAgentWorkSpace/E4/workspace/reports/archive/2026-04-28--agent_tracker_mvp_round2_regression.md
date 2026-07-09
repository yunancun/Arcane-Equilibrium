# E4 Linux Regression — Agent Tracker MVP feature branch (plan aa-nifty-walrus round 2)

**Branch**: `feature/agent-tracker-mvp`
**HEAD**: `d1c6911` (feature `ab12207` E1 9 files + `d1c6911` E4 test fix)
**Date**: 2026-04-28
**Verdict**: **APPROVED FOR PM SIGN-OFF**
**Engine rebuild**: NOT required (0 Rust diff，0 trade impact，純 Python read-only routes + frontend JS + tests)

## 對象

Plan `aa-nifty-walrus` round 2 post-E2-CONDITIONAL-APPROVED — Agent Tracker MVP backend + frontend。

| File | Type | Lines |
|---|---|---|
| `app/agents_routes.py` | new | 334 |
| `app/agents_routes_helpers.py` | new | 783 |
| `app/static/js/agent-tracker.js` | new | 954 |
| `tests/test_agents_routes.py` | new | 762 → 870（E4 strip-helper +112） |
| `tests/static/test_agent_tracker_contract.html` | new | 311 |
| `app/main.py` | modified | +12（agents_router include） |
| `app/executor_agent.py` | modified | +63（summary_zh contract） |
| `app/strategist_agent.py` | modified | +42（summary_zh contract） |
| `app/static/tab-learning.html` | modified | +144（sub-section） |

## Test 結果（Linux trade-core）

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| `test_agents_routes.py` 1st run | 19 | 2 | — | — |
| `test_agents_routes.py` 2nd run（after E4 fix `d1c6911`） | 21 | 0 | — | +21 vs baseline absent |
| `test_agents_routes.py` 3rd run（flaky verify） | 21 | 0 | — | 0 |
| Full control_api_v1 baseline | **3138** | **0** | 3117 (Wave H) | **+21 / 0 fail（baseline 不退）** |

**Non-flaky 確認**：3 次跑同綠（21/21 in 0.51s + 0.46s + 0.35s）。

### 21 個 test 名單

| # | 名稱 | 類別 |
|---|---|---|
| 1 | test_roster_returns_200_when_pg_down | round-1 fail-closed |
| 2 | test_roster_returns_200_when_singletons_missing | round-1 fail-closed |
| 3 | test_roster_happy_path_with_costs_and_counts | round-1 happy |
| 4 | test_strategist_summary_zh_evaluating_format | round-1 contract |
| 5 | test_strategist_summary_zh_budget_low_template | round-1 contract |
| 6 | test_strategist_summary_zh_no_raw_json_leak | round-1 contract |
| 7 | test_executor_offline_when_state_not_running | round-1 fail-closed |
| 8 | test_statement_timeout_set_on_pg_query | round-1 SQL guard |
| 9 | test_h3_no_like_agent_underscore_anywhere | **H-3 invariant**（round-2 修 strip-docstring） |
| 10 | test_recent_rejects_happy_path | C-1a |
| 11 | test_recent_rejects_pg_outage_returns_degraded | C-1a fail-closed |
| 12 | test_recent_rejects_limit_validation | C-1a |
| 13 | test_recent_rejects_sql_filters_only_rejected | C-1a SQL contract |
| 14 | test_shadow_vs_live_summary_happy_path | C-1b |
| 15 | test_shadow_vs_live_summary_unions_live_and_live_demo | C-1b engine_mode union |
| 16 | test_shadow_vs_live_summary_pg_outage_returns_degraded | C-1b fail-closed |
| 17 | test_shadow_vs_live_summary_unknown_since_falls_back_24h | C-1b validation |
| 18 | test_h1_executor_card_uses_real_get_stats_shadow_mode | **H-1 ExecutorAgent ctor integration**（防 round-1 contract drift） |
| 19 | test_h1_executor_card_provider_exception_fail_closed | **H-1 fail-closed** |
| 20 | test_grep_no_write_paths | **module invariant**（round-2 修 strip-docstring） |
| 21 | test_helpers_module_under_size_guards | M-3 file-size guard |

## Round 2 自我修復（test 寫法 bug，非業務代碼）

E1 round 2 提交 21 test，初跑 2 fail：

- `test_h3_no_like_agent_underscore_anywhere`：assertion `"LIKE 'agent_" not in src` 在 helpers module docstring（行 14, 22, 215）誤觸 — docstring 自證政策「禁 LIKE 'agent_%' (H-3 改 IN)」反被自我反噬
- `test_grep_no_write_paths`：assertion `" INSERT " not in src.upper()` 同樣在 routes 行 19 docstring `"grep -E ' INSERT | UPDATE | DELETE ' is 0 in this file"` 誤觸；line 101 inline comment `# post-update` 含 substring `UPDATE` 也誤觸

**根因**：naive substring grep on raw source。
**修復**（E4 commit `d1c6911`）：加 `_strip_comments_and_docstrings()` helper：
- tokenize 移 `#` comment
- ast 移所有 module/class/function body 的 bare-string `Expr` statement（不依賴 PEP 257，因為作者用 `from __future__ import annotations` + module-note pattern）
- 保留 SQL `f"""SELECT ..."""` 等 string literal（child of `Call`/`Assign`/`Return`，非 bare `Expr`）
**驗證**：helpers stripped 28815→21354 chars，仍含 `SELECT`，不含 `LIKE 'agent_`、`INSERT`、`UPDATE`、`DELETE`。未來真實 INSERT SQL 進 helpers/routes 仍會 trip invariant。

E4 profile §硬約束「test 本身寫錯，可以直接修 test」適用 — **不退 E1**。

## 不變量 grep

| Invariant | Result | 備註 |
|---|---|---|
| 1. `grep -nE 'INSERT\|UPDATE\|DELETE'` agents_routes.py + helpers | 1 hit (line 19 docstring 自證) | **PASS** — strip-aware test (#20) 自動覆蓋 |
| 2. `grep -nE 'POST\|PUT\|DELETE\|onclick.*post'` agent-tracker.js | 2 hits (line 8 中文 / line 25 英文 JSDoc 自證) | **PASS** — 0 真實 fetch write |
| 3. `grep -nE '/home/ncyu\|/Users/[a-z]+'` 4 source files | **0** | **PASS** — 跨平台 |
| 4. File size | routes 334<400, helpers 783<800, executor 804<1200, strategist 824<1200, js 954<1200 | **PASS** |
| 5. `_LIKE_` pattern | 0 | **PASS** |

## SQL EXPLAIN ANALYZE（Linux trade-core PG）

### 1. `_fetch_today_costs_by_role`（H-3 ANY whitelist）
```
WHERE time >= NOW() - INTERVAL '24h' AND scope = ANY(ARRAY[...5 roles...])
```
- ai_usage_log 空表 → planner 折成 `One-Time Filter: false`，0.025ms
- 索引 `idx_ai_usage_log_scope_time(scope, time DESC)` **存在** (確認 via pg_indexes)
- production cost-based 自動切 Index Scan
- **PASS**（dev sandbox 表空無法直接演示，但索引齊全 + plan 形態正確）

### 2. `_fetch_recent_rejected_verdicts`（C-1a）
```
WHERE verdict = 'REJECTED' ORDER BY ts DESC LIMIT 5
```
- **Custom Scan ChunkAppend** + **Index Scan via `idx_verdicts_verdict`**（3 hypertable chunks 每個都走 index）
- Execution Time: **0.100ms**
- **PASS** — hypertable partition prune + index scan 雙重命中

### 3. `_fetch_shadow_vs_live_summary`（C-1b）
```
WHERE engine_mode IN ('demo','live','live_demo') AND ts >= NOW() - make_interval(hours => 24) GROUP BY bucket
```
- **Custom Scan ChunkAppend** (Chunks excluded during startup: 2)
- 1 active chunk 內部 Seq Scan 過濾 1330 / 2599 rows
- Execution Time: **1.5ms**
- **PASS** — partition prune 在 ChunkAppend 已生效；單 chunk 內 cost-based seq scan 比 index access 快是正常 PG 行為（小資料量）

## Endpoint Smoke（Linux temp uvicorn port 18001 + viewer Bearer token）

| Endpoint | HTTP | Time | Body shape |
|---|---|---|---|
| `/api/v1/agents/roster` | **200** | ~100ms | `{ts, agents:[5 cards w/ role+label_zh+state+summary_zh+today_cost_usd], scan_interval_s, degraded:false}` |
| `/api/v1/agents/recent_rejects?limit=5` | **200** | 6.5ms | `{rows:[], degraded:false}`（prod 無 REJECTED 行） |
| `/api/v1/agents/shadow_vs_live_summary?since=24h` | **200** | 6.4ms | `{since, demo:{count:673,total_pnl_usd:-26.68,avg_slippage_bps:34.18}, live_demo:{count:653,...}, diff:{fill_rate_delta_pct,slippage_delta_bps}}` |

Auth：`Authorization: Bearer <token from .secrets/api_token>` → 401 → 200 切換正確（fail-closed 邏輯 OK）。

Executor card 帶 `shadow_mode:true` + `engine_mode:"paper"` + `today_orders:0` —— GUI 三層強隔離（深藍底色 + banner + 計數）後端 contract 對。

## P99 Latency 估算（10 次 /agents/roster）

```
min:    91ms
median: 97ms
p90:    120ms
p99 (worst of 10): 121ms
```

SLA 500ms（plan 30s refresh），p99 餘量充足（24% utilisation）。

## Mock 審查

E4 round-2 fix 純改 test，**0 業務代碼變動**。E1 落地的 21 test 中：

- 大部分用 fake DB connection（`_pg_returns(scripts)` context manager，hermetic）— **mock IO，business logic 真跑** ✓
- H-1 整合 test 用真實 ExecutorAgent ctor + mock BybitClient + mock MessageBus — **沒 mock 業務 stats 邏輯，只 mock 外部 IO** ✓
- 無 mock 業務邏輯（如 RiskManager.should_allow / Strategist 推理）

符合 skill 4.1 安全規則。

## Healthcheck（Linux trade-core full sweep — feature branch 不影響 runtime）

跳過（feature branch 程式碼未進 running uvicorn / engine；當前 main branch runtime healthcheck 結果與 Wave H baseline 一致，agent tracker 不改變這些 check 行為）。

## 跑兩遍結果（skill 強制）

- 1st run（initial）：19 pass / 2 fail（test 寫法 bug）
- 2nd run（after `d1c6911` strip-docstring fix）：**21 pass / 0 fail**（0.46s）
- 3rd run（non-flaky verify）：**21 pass / 0 fail**（0.35s）
- Full baseline 1st: 3138 / 0 / 3 skipped（61.46s）

**Non-flaky** ✓

## 結論 / Sign-off

**APPROVED FOR PM SIGN-OFF** — Agent Tracker MVP feature branch 全綠：

1. 21/21 agent tracker test PASS（plan 預期 12，E1 落地 21 — 涵蓋更廣）
2. Full control_api_v1 3138/0（vs Wave H 3117 = +21 = 純新增 test，0 既有 fail）
3. 3 endpoint smoke 全 200 + body shape 對 plan §F + p99 121ms < SLA 500ms
4. 3 SQL EXPLAIN: hypertable partition prune live + 索引齊全 + execution time 0.1-1.5ms
5. 5 不變量 grep PASS（純讀 / no JS write / 無硬編路徑 / file size / no LIKE）
6. Mock 審查 PASS（mock IO，業務邏輯真跑）
7. Non-flaky（3 次跑同綠）
8. 0 Rust diff，0 engine impact，無需 `--rebuild`

**PM 部署提示**：merge `feature/agent-tracker-mvp` → main → `bash helper_scripts/restart_all.sh --keep-auth`（不需 --rebuild，純 Python + JS 變動）。authorization.json 保持，避免 operator 重 approve。

無 BLOCKER；無需退回 E1。

## 退回 E1 修復清單

N/A — 所有 fail 都是 test 寫法問題，E4 自修。
