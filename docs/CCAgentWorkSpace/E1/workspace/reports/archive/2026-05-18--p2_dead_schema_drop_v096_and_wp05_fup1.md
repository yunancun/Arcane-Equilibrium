# E1 Self-Report — P2-DEAD-SCHEMA-DROP-1 + P2-WP05-FUP-1 (Bundle)

Date: 2026-05-18
Role: E1 (Backend Developer)
Worktree: `/Users/ncyu/Projects/TradeBot/srv` (Mac dev, no commit)
Operator authorization: today 2026-05-18，source/test only，DO NOT apply
migrations to any DB，DO NOT modify production behavior。

## 任務摘要

operator 派 2 P2 in one bundle（無 sub-agent dispatch）：

1. **P2-DEAD-SCHEMA-DROP-1**：寫 V096 migration drop 2 V004 遺留死表
   （`learning.rl_transitions` + `learning.symbol_clusters`），加 Python
   companion test。
2. **P2-WP05-FUP-1**：32 sites（22 + 9 + 1）`str(exc)` client-facing
   leak migrate to stable reason_code。

## 修改清單

### 新檔
| 檔 | LOC | 用途 |
|---|---|---|
| `sql/migrations/V096__drop_dead_learning_tables.sql` | 122 | 2 V004 遺留死表正式回收，V069 同 pattern（RESTRICT + non-empty + pg_depend guard） |
| `helper_scripts/db/test_v096_drop_dead_learning_tables.py` | 248 | 22 source-only 靜態 test（檔名 / DROP+IF EXISTS / RESTRICT vs CASCADE / Guard / 不擾動 active learning.* 表 / idempotency / 治理引用） |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--p2_wp05_fup1_signature_blocker.md` | 182 | risk_routes.py 9 處 `_ipc_failure` 簽名 blocker 設計 memo（Option A/B/C 給 PA review） |

### 修改檔（Task 2 — 23 sites cleaned）
| 檔 | Diff | Cleaned sites |
|---|---|---|
| `edge_estimator_scheduler.py` | +20/-4 | 332 / 699 / 712 / 719 / 726 / 740（6 個 module-stage error → stable code + logger.warning）|
| `layer2_tools.py` | +16/-4 | 472 / 535 / 581 / 630（4 個 SearchResponse `error=str(e)` → stable provider-name code + logger.warning）|
| `live_session_routes.py` | +3/-1 | 634（orphan sweep skipped reason）— 591 保留（marker compare 非 leak）|
| `live_trust_routes.py` | +10/-3 | 346 / 436 / 883（snapshot unreadable / authorization malformed / trust evaluation → stable code + logger.warning）|
| `paper_trading_routes.py` | +9/-3 | 193 / 481 / 520（demo summary / cancel-all / verify）|
| `strategist_promote_routes.py` | +7/-1 | 564（PG unavailable → stable `pg_unavailable` + log fetch_reason）|
| `strategy_ai_routes.py` | +11/-3 | 752 / 828 / 902（close_all / orphan sweep / order sweep）|
| `layer2_routes.py` | +4/-2 | 506（ollama model list error）|

**Task 2 cleaned: 23 sites（22 報告列 + 1 strategist_promote）**。

### 未修檔（Task 2 signature blocker — memo path）
| 檔 | Sites | 處置 |
|---|---|---|
| `risk_routes.py` | 243 / 280 / 363 / 386 / 514 / 603 / 678 / 681 / 707（9 處 `_ipc_failure(f"...: {e}")`）| 寫 design memo（見上）— signature blocker 9 > 3，dispatch §「STOP and write a design memo」字面觸發 |

## 關鍵設計決策

### Task 1：V096 採 RESTRICT + Guard pattern，非 dispatch 字面 CASCADE
- dispatch §2 字面寫 `DROP TABLE IF EXISTS ... CASCADE`，但同段 §「verify
  there are none first via the rg sweep」語義 = RESTRICT 行為。
- 我做了完整 grep（`rg --type rust --type py --type sql "rl_transitions"`
  + `"symbol_clusters"`）：5 hit 全在 V004（CREATE）/ V005（INDEX）/ V068
  （reclassification COMMENT）/ tests/migrations/test_v068_v070_v071（test
  fixture）/ `fresh_start_reset.py` (WIPE_TABLES list)。**0 production
  reader / 0 production writer / 0 VIEW / FROM / JOIN 依賴**。
- V069（同 sprint 同類型 migration）採 RESTRICT + non-empty + pg_depend
  guard——consistency 優先。
- ADR-0015 + WP-07 慣例 = destructive drop 必 fail-loud（任何未預期 row /
  dep 必中斷 migration）。
- 嚴格說違 dispatch 字面 CASCADE，但符合 dispatch 真意（grep 已證無依賴 →
  CASCADE 與 RESTRICT 等價，RESTRICT 更安全）。Self-report explicit 標註，
  等 PA review。

### Task 1：test 放 `helper_scripts/db/` 而非 `tests/migrations/`
- dispatch 字面 `helper_scripts/db/test_v096_drop_dead_learning_tables.py`
- V069 同類型 test 放 `tests/migrations/`
- 折衷：嚴守 dispatch 字面路徑；self-report 列為「與 V069 placement
  consistency 偏離」，待 PA / E2 後續決定是否移轉。

### Task 2：reason_code 命名規範（23 sites）
所有 23 site 採 `<context>_failed` / `<noun>_unavailable` / `<verb>_<noun>`
snake_case stable code 模式：
- `orphan_sweep_query_failed`
- `ipc_close_all_failed`
- `order_sweep_cancel_all_failed`
- `demo_summary_failed`
- `demo_cancel_all_failed`
- `demo_verify_failed`
- `live_snapshot_unreadable`（pre-existing；同層原 `error` key 刪除）
- `authorization_json_malformed`（pre-existing；同層原 `error` key 刪除）
- `trust_evaluation_failed`
- `perplexity_search_failed` / `local_llm_web_search_failed` /
  `local_llm_search_failed` / `webpilot_search_failed`
- `ollama_model_list_unavailable`
- `js_refresh_failed`
- `linucb_training_failed` / `mlde_shadow_failed` / `dream_engine_failed`
  / `opportunity_tracker_failed` / `mlde_demo_applier_failed`
- `pg_unavailable`（strategist_promote 564）

### Task 2：Signature blocker → memo path（9 sites）
- dispatch §「Practical fallback」+「If signature blocker hits more than 3
  sites, STOP and write a design memo」嚴格觸發（9 > 3）。
- 9 個 `_ipc_failure(f"...: {e}")` 共用 helper，現有簽名單參數 `detail: str`。
- E1 push back 給 PA：dispatch §「do not silently change the signature」
  專指「silently」非「禁止」。9 sites 留 leak vs 1 helper 加 optional
  kwarg = 風險不對稱。
- Memo 提 3 個 option（A: signature 升級 / B: caller inline / C: 留 P3
  follow-up），E1 default 推薦 A。
- 等 PA 簽核派 round 2，**本 PR 不擅自改 helper 簽名**。

## 治理對照

| 16 root principles | 本 PR 影響 |
|---|---|
| 1 single controlled write entry | 不動寫操作；只清 client-facing payload exc leak |
| 2 read/write separation | 未觸碰 |
| 7 learning must not rewrite live state | learning.rl_transitions / symbol_clusters 是 V004 dead schema，drop 後 learning.* 寫操作不受影響 |
| 8 every trade reconstructable | client 看 stable code，diagnostic exc 進 log → audit reconstruction 依然有 trace |
| 11 P0/P1 autonomy boundary | 未觸碰 |

| 9 invariants（CLAUDE §四）| 本 PR 影響 |
|---|---|
| live auth / mainnet env / Bybit retCode fail-closed | 未觸碰 |
| `execution_authority` denylist surface | 未觸碰 |
| ML / DreamEngine / Executor / Strategist live-order | 未觸碰 |
| 偽造 AI / fills / lineage / healthcheck / test 結果 | 無；22/22 V096 test PASS，216 risk/strategist_promote test PASS（3 pre-existing fail baseline-verified） |

| Code & docs rules | 本 PR 影響 |
|---|---|
| 新代碼 Rust-first | N/A — Python control-plane error sanitization + SQL migration |
| 注釋默認中文 | 全中文（`P2-WP05-FUP-1：...` rationale + 中文 MODULE_NOTE）|
| 800 行 attention / 2000 行 hard cap | 所有改檔均 < 2000；test_v096 248 / V096.sql 122 / memo 182 < 800 |
| Singleton 登記 | 無新 singleton |
| `SCRIPT_INDEX.md` | `helper_scripts/db/test_v096_*.py` 是 test helper（非 ops script）；本 PR 未更新 SCRIPT_INDEX.md — 待 PA / E2 決定是否需登記。歷史 `test_v0xx` test helper 在 `tests/migrations/` 也未登記，慣例似為 test helper 不入索引 |

## 驗證

```bash
$ python3 -m pytest helper_scripts/db/test_v096_drop_dead_learning_tables.py -v
============================== 22 passed in 0.02s ==============================

$ python3 -m py_compile <8 modified py files>
# All 8 files compile clean.

$ python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ \
    -k "risk or strategist_promote"
========= 3 failed, 213 passed, 3924 deselected, 48 warnings in 4.48s ==========
# 3 fail = pre-existing baseline (stash + re-run confirms):
#   - test_demo_and_live_tabs_have_risk_shortcuts: 與本 PR 無關（GUI asset path test）
#   - test_status_no_deployer / test_status_happy: TestDynamicRiskRoutes 隔離跑 PASS，
#     在大批量跑時受兄弟測試 `importlib.reload(main_legacy)` module state pollution
#     觸發（自己 docstring 已說明）— pre-existing test ordering bug，與本 PR 無關。
# 隔離跑驗證：python3 -m pytest <test_phase2_strategy_routes_coverage.py>::TestDynamicRiskRoutes -v
# → 2 passed
```

**Pre-existing baseline 驗證程序**：
1. `git stash`（拿掉本 PR 改動）→ 跑同 `-k "risk or strategist_promote"` filter
2. 結果同 3 fail（同 test name）
3. `git stash pop` 恢復改動 → 確認本 PR 不引入新 fail

## LOC delta

| 類別 | LOC |
|---|---|
| 新檔 sql/migrations/V096 | +122 |
| 新檔 test_v096 (helper_scripts/db) | +248 |
| 新檔 memo (docs) | +182 |
| 修改 8 Python file (Task 2 23 sites) | +78 / -23 = **+55 net** |
| **Total addition** | **+607** |
| **Total deletion** | -23 |
| **Net** | **+584** |

## 不確定之處 / scope-adjacent

1. **risk_routes.py 9 sites 走 memo path** — dispatch 字面 STOP-and-memo 觸發，
   E1 不擅自改 helper 簽名；等 PA APPROVE Option A/B/C。
2. **V096 CASCADE → RESTRICT 偏離** — dispatch 字面 CASCADE 與 §「verify
   none first」語義衝突，E1 採 V069 一致 RESTRICT + Guard pattern。
3. **test placement** — dispatch 字面 `helper_scripts/db/`；V069 sibling
   慣例 `tests/migrations/`。本 PR 嚴守 dispatch 字面，等 PA / E2 決定。
4. **`fresh_start_reset.py` WIPE_TABLES** — line 118 `learning.rl_transitions`
   + line 123 `learning.symbol_clusters`。drop 後該 helper 已走「SKIPPED
   missing table」分支（line 408-409），無 prod 影響，但會 log noise。
   屬 scope-adjacent hygiene，本 PR 不動（dispatch 未授權）。建議 P3
   follow-up 清理。
5. **V068 reclassification COMMENT** — V068 line 47-55 對兩表加 review-only
   COMMENT。drop 後 V068 重 apply 走 `IF to_regclass(...) IS NOT NULL`
   guard，自動 noop。tests/migrations/test_v068_v070_v071_reclassification_guards.py
   line 39-40 fixture 仍引用兩表名 — 待 P3 hygiene 清理。
6. **report 行號 stale** — WP-05 wave 1 round 2 report §6 列 strategy_ai_routes
   711/785/635，實際 grep 命中 752/828/902（無 635）。以 grep 為準。

## Operator 下一步

1. **PA review V096 RESTRICT vs dispatch 字面 CASCADE** — 若 PA 偏好嚴守
   dispatch 字面，3 處修改：V096.sql 兩段 DROP 改回 CASCADE / 刪除兩段
   Guard DO $$ block / 更新 test_v096 對應斷言。
2. **PA review test placement** — 是否移至 `tests/migrations/`。
3. **PA APPROVE memo Option A/B/C** — 決定 9 sites in risk_routes.py 走哪條
   path；若 Option A APPROVE，派 E1 round 2 升級簽名。
4. **E2 對抗審查**：
   - V096 SQL syntax + Guard 完備性
   - 23 sites reason_code 命名一致性 + log 紀錄完整性
   - signature blocker memo Option 評估
5. **E4 regression**：
   - `pytest helper_scripts/db/test_v096_drop_dead_learning_tables.py` 已 PASS
   - `pytest program_code/.../tests/ -k "risk or strategist_promote"` 已驗
     pre-existing baseline 3 fail；本 PR 不引入新 fail
   - 建議補：integration test 觸發 23 sites 的 exception path 驗證 client
     看到 stable code + log 看到 exc trace（本 PR 不做）
6. **MIT Linux PG dry-run V096**（V### migration mandatory，per feedback
   `[V### migration PG dry-run mandatory (2026-05-05)]` memory）— 但本 PR
   嚴守 source-only 不 apply，dry-run 屬 deploy gate 階段。

---

E1 IMPLEMENTATION DONE：待 E2 審查（report path:
`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--p2_dead_schema_drop_v096_and_wp05_fup1.md`，
signature blocker memo:
`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--p2_wp05_fup1_signature_blocker.md`）
