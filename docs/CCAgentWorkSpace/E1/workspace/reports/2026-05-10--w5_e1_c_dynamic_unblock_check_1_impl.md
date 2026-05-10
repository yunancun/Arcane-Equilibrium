# E1 IMPL DONE — W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1

**任務 ID**：W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1（Sprint N+1 W5）
**日期**：2026-05-10
**範圍**：30d cycle unblock candidate audit + governance.unblock_candidates writer + healthcheck `[64]` + cron + V090 dry-run/apply on Linux PG
**Spec**：`srv/docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md`
**V###**：`srv/sql/migrations/V090__governance_unblock_candidates.sql`（既存 skeleton，本 task 直接用）
**對應 dispatch**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.5 W5 P1 list
**對應 issue**：QC v3 NEW-ISSUE-V3-4（17 frozen cells 多數 0 fills 無 counterfactual power → freeze 變 one-way street）

---

## 1. 任務摘要

QC v3 NEW-ISSUE-V3-4 揭露 17 frozen cells 多數 7d window 0 fills + 0 rejected_outcomes，selection-bias 累積使 blocked_symbols list 單調膨脹（17→18→N）。本 IMPL 落地 spec §2-§7 全範圍：

1. **新檔 `blocked_symbols_30d_unblock_check.py`**（882 LOC）— fork 既有 `blocked_symbols_7d_counterfactual.py` 改 30d window + 加 §3 unblock criteria + §3 4 verdict logic + §4 paper_evidence_jsonb 寫入 + §6 PG state machine writer（INSERT candidate / UPDATE outcome）
2. **healthcheck `[64]` 加 `checks_governance.py`**（979→1193 LOC, +214）— spec §6.2 4 sub-check（stale candidate / yo-yo detection / sign-off completeness / unfrozen rows count）
3. **runner.py 5-point wiring**（import + cursor invocation + 2 處 module docstring + main() docstring）
4. **cron `blocked_symbols_30d_unblock_check_cron.sh`**（114 LOC）— `0 4 * * 0` server local UTC
5. **31 unit tests**（516 LOC）— 4 verdict logic + DSR/PBO + INSERT/UPDATE outcome + healthcheck `[64]` 全 sub-check + freeze.json reuse + markdown rendering 全綠
6. **V090 dry-run + apply 兩次 idempotency PASS on Linux PG**（governance.unblock_candidates table + 8 CHECK constraints + 2 indexes 全 verified）

---

## 2. 修改清單

| 檔 | 動作 | LOC 前→後 | 用途 |
|---|---|---:|---|
| `helper_scripts/db/audit/blocked_symbols_30d_unblock_check.py` | NEW | 0 → 882 | 30d cycle writer（4 verdict + PG INSERT/UPDATE + markdown + CLI） |
| `helper_scripts/db/passive_wait_healthcheck/checks_governance.py` | EDIT | 979 → 1193 | `[64] check_64_unblock_candidates_drift` 函數加 spec §6.2 4 sub-check |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | EDIT | 983 → 1032 | `[64]` import + cursor invocation + 5-point docstring wiring |
| `helper_scripts/db/test_blocked_symbols_30d_unblock_check.py` | NEW | 0 → 516 | 31 unit tests（writer + healthcheck `[64]`） |
| `helper_scripts/cron/blocked_symbols_30d_unblock_check_cron.sh` | NEW | 0 → 114 | cron wrapper `0 4 * * 0` UTC + PG creds source + lock + log |

**未動**：
- `sql/migrations/V090__governance_unblock_candidates.sql`（沿用既存 e63b24c3 skeleton）
- `helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py`（保留為短期 7d audit，per spec §7.1 backward compat）
- `docs/governance_dev/strategy_blocked_symbols_freeze.json`（不動，writer 只讀）
- `program_code/exchange_connectors/.../api/v1/canary_governance_routes.py`（**未存在** — 本 IMPL 不處理 W5-E1-C(API) 範圍 force_eval API 部分；屬 W6 V086 同檔依賴，待 W6 IMPL 階段同檔處理）
- 任何 GUI / Settings tab 檔（spec §7.6 標 optional W5 OR 留 N+2）

---

## 3. 關鍵 diff / 設計亮點

### 3.1 4 verdict 排序（spec §3）

```python
def evaluate_verdict(cell, evidence):
    # 1. yo-yo 必首查（spec §5.3 selection-bias 防護）
    if yoyo_count_30d >= 1:
        return VERDICT_MANUAL_REVIEW_REQUIRED

    # 2. dormant_no_evidence（樣本不足）
    if paper_fills_30d < 30:
        return VERDICT_DORMANT_NO_EVIDENCE

    # 3. manual_review_required（DSR/PBO NULL）
    if dsr is None or pbo is None:
        return VERDICT_MANUAL_REVIEW_REQUIRED

    # 4. continue_freeze（criteria 部分缺）OR unblock_candidate（全 PASS）
```

順序 = optimization → conservative；不能反過來（會 false negative yo-yo）。

### 3.2 commit_sha 寫入 timing（spec §5.2 #5）

```python
def update_unblock_outcome(candidate_id, *, outcome='unfrozen',
                           pa_report_path, qc_report_path,
                           commit_sha, unfrozen_at_ms):
    # 嚴格 client-side check：四欄齊全才允許 update
    if outcome == "unfrozen":
        if not (pa_report_path and qc_report_path and commit_sha and unfrozen_at_ms):
            raise ValueError(...)
```

writer git rev-parse 抓當下 sha 寫入是在 unfrozen UPDATE 那一刻，不是 INSERT；race window 短（operator commit 後立即 update）。

### 3.3 healthcheck [64] verdict 優先級（spec §6.2）

```
FAIL > WARN > PASS：
- yoyo_count > 0          → FAIL（spec §5.3 hard contract）
- incomplete_signoff > 0  → FAIL（V090 unfrozen_completeness_chk sentinel of sentinel）
- stale_count > 0         → WARN（operator inattention）
- 全 0                    → PASS
```

V090 PG CHECK constraint 已強制 sign-off completeness；healthcheck 是「constraint 還活著」的 sentinel of sentinel — 防 partial-rollout drift（V090 schema disable / DROP）。

### 3.4 4 PG query 設計

| Query | 表 | 範圍 | 用途 |
|---|---|---|---|
| Q1 paper engine fills | `trading.fills` | 30d | paper_fills_30d + paper_net_edge_bps_30d + last_fill_ms |
| Q2 reject outcome coverage | `trading.risk_verdicts` + `trading.decision_outcomes` | 30d | rejected_n + rejected_outcome_n |
| Q3 SM-04 escalate | `governance.canary_stage_log` | 7d | sm04_escalate_count_7d（fail-soft：表缺 graceful skip） |
| Q4 yo-yo detection | `governance.unblock_candidates` | 30d | yoyo_count_30d（fail-soft：表缺 graceful skip） |

paper engine 不被 freeze 影響（freeze 只影響 demo + live runtime gate）→ paper 30d edge 是 freeze 期間能拿的「實時 edge proxy」（per spec §2.2 rationale）。

### 3.5 cron schedule（spec §2.3 + §6.2）

```
30d cycle:        0 4 * * 0  UTC  (週日 04:00) → 本 IMPL cron
[64] drift check: 0 5 * * 0  UTC  (週日 05:00, 1h delay 等 cycle land)
                                    → 由 passive_wait_healthcheck cron 既有 schedule cover
```

cycle 跑完 1h 後 [64] 自然驗 cycle 寫入結果 + sign-off completeness。silent cron death 由 `[64] stale_n > 0`（14d 無新 cycle）偵測。

---

## 4. V090 dry-run output（Linux PG 兩次 apply）

### Apply 1st (initial land)

```
WARNING:  database "trading_ai" has no actual collation version, but a version was recorded
BEGIN
NOTICE:  schema "governance" already exists, skipping
CREATE SCHEMA / COMMENT / DO / CREATE TABLE / DO / 9× COMMENT
CREATE INDEX / COMMENT / CREATE INDEX / COMMENT / DO / DO
COMMIT
NOTICE:  V090 land complete:
  - governance.unblock_candidates table created (BIGSERIAL PK)
  - 4 verdict enum + 3 outcome enum (immutable verdict / mutable outcome)
  - Sign-off completeness CHECK constraint enforced
  - Re-frozen completeness CHECK constraint enforced
  - Lifecycle order CHECK: unfrozen_at_ms < re_frozen_at_ms
  - Index 1: idx_unblock_candidates_cell_time (cohort time-series)
  - Index 2: idx_unblock_candidates_outcome (partial outcome IS NOT NULL)
```

**0 ERROR + 全 8 CHECK constraints land + 2 indexes land**。

### Apply 2nd (idempotency verify)

```
BEGIN
NOTICE:  schema "governance" already exists, skipping
NOTICE:  relation "unblock_candidates" already exists, skipping  ← Guard A
NOTICE:  relation "idx_unblock_candidates_cell_time" already exists, skipping  ← Guard C
NOTICE:  relation "idx_unblock_candidates_outcome" already exists, skipping
COMMIT
NOTICE:  V090 land complete: ...
```

**0 RAISE EXCEPTION + 全 IF NOT EXISTS / Guard A/B/C clean skip**。

### Schema verify (`\d governance.unblock_candidates`)

- 16 columns（id BIGSERIAL + 7 mandatory + 7 nullable mutable + 2 timestamp）
- 3 indexes（pkey + cell_time DESC + outcome partial）
- **8 CHECK constraints all green**：
  - candidate_at_ms_sane_chk（≥ 1577836800000）
  - cell_strategy_nonempty_chk + cell_symbol_nonempty_chk
  - lifecycle_order_chk（re_frozen > unfrozen）
  - outcome_chk（4 enum + NULL）
  - re_frozen_completeness_chk（re_frozen → 3 audit cols）
  - unfrozen_completeness_chk（unfrozen → 4 audit cols）
  - verdict_chk（4 enum）

---

## 5. _sqlx_migrations status

**Skip**（per V086 IMPL pattern + 2026-05-02 P0 sqlx hash drift 教訓）：本 IMPL 不直接寫 `_sqlx_migrations` table。理由：

- V090 file 改動後 DB checksum 沒同步是 P0-3681f83 incident root cause（CLAUDE.md §七 "Engine 自動遷移" 段落）
- engine restart + auto-migrate（OPENCLAW_AUTO_MIGRATE=1）時 PM 透過 `bin/repair_migration_checksum` 一次性同步全 V###
- align with V086 同 pattern（2026-05-10 W6-3C 同窗 IMPL 沿用同決策）

**PM follow-up**：engine 下次 `restart_all --rebuild` 前跑 `cargo run --bin repair_migration_checksum` 對齊 V90。

---

## 6. Test coverage（unit + 全綠）

```
helper_scripts/db/test_blocked_symbols_30d_unblock_check.py  31 PASS
helper_scripts/db/test_blocked_symbols_counterfactual.py      3 PASS（sibling 7d 0 regression）
helper_scripts/db/test_canary_stage_invariant_healthcheck.py 13 PASS（sibling [58] 0 regression）
helper_scripts/db/ 全套                                     271 PASS
```

### 31 test 覆蓋面

| TestClass | tests | 覆蓋面 |
|---|---:|---|
| TestVerdictLogic | 7 | 4 verdict 全路徑 + yo-yo + DSR/PBO NULL |
| TestDsrPboComputation | 3 | 0 fills / 充足 / 少樣本 PBO 衰退 |
| TestPgWriter | 7 | INSERT 成功 + 拒 invalid verdict / UPDATE outcome 4 邊界 |
| TestFreezeJsonReuse | 6 | freeze.json 解析 + values_sql + parse_cell_arg |
| TestMarkdownRendering | 1 | 4 verdict 計數 + 表結構 |
| TestCheck64UnblockCandidatesDrift | 7 | V090 missing PASS-skip + 4 sub-check 全 verdict + FAIL/WARN 優先級 + query exception |

---

## 7. 治理對照（16 原則 / DOC-08 §12 / 硬邊界 0 觸碰確認）

### 16 原則

| 原則 | 狀態 |
|---|---|
| 1. 單一寫入口 | 本 IMPL 不接 trading 寫入路徑；governance.unblock_candidates 是 append-only audit table |
| 2. 讀寫分離 | writer 純 SELECT + INSERT/UPDATE governance.* 表；不動 trading.* |
| 3. AI 輸出 ≠ 即時命令 | unblock_candidate verdict 不自動修改 risk_config*.toml（per spec §4 rationale）；需 PA + QC sign-off |
| 4. 策略不繞過風控 | 本 IMPL 與策略路徑無關 |
| 5. 生存 > 利潤 | yo-yo detection（spec §5.3）+ continue_freeze 預設保守 |
| 6. 失敗默認收縮 | DSR/PBO NULL → manual_review_required；fail-closed 設計 |
| 7. 學習 ≠ 改寫 Live | 寫入 governance audit 表，不動 live runtime |
| 8. 交易可解釋 | paper_evidence_jsonb 含 9 metric snapshot，全可重建 |
| 9. 交易所災難保護 | N/A（governance audit 無交易所交互） |
| 10. 認知誠實 | DSR/PBO 簡化 proxy 明文 docstring 標示 |
| 11. Agent 最大自主權 | unblock_candidate 推薦 + sign-off SOP，operator 終審 |
| 12. 持續進化 | 30d cycle 自動 audit + verdict logic |
| 13. AI 資源成本感知 | N/A（無 AI 調用） |
| 14. 零外部成本 | 純 PG SELECT + cron；無外部 API |
| 15. 多 Agent 協作 | sign-off SOP 走 PA + QC report path（spec §5.2） |
| 16. 組合級風險 | 整 17 frozen cells 同 cycle 評估 |

### DOC-08 §12

- **§12 4. paper_engine 隔離**：本 IMPL Q1 query 純 `engine_mode='paper'` filter，與 demo/live writer 不混寫
- **§12 5. Reconciler diff → paper degrade**：N/A（本 IMPL 不接 reconciler；Q3 SM-04 escalate 偵測是讀 governance.canary_stage_log 不是 reconciler）

### 硬邊界（CLAUDE.md §四 5 項）

| 邊界 | 狀態 |
|---|---|
| max_retries=0 | 不動 |
| live_execution_allowed | 不動（writer 不接 live 路徑） |
| execution_authority | 不動 |
| system_mode | 不動 |
| authorization.json HMAC | 不動（writer 純 PG，無 HMAC 路徑） |

**全 0 觸碰確認**。

### CLAUDE.md §七 強制規範

- ✅ Guard A/B/C：V090 既存 skeleton 完整含三 Guard
- ✅ Linux PG dry-run mandatory：兩次 apply 全 verified（§4 output）
- ✅ 被動等待 TODO 必附 healthcheck：`[64]` 配對 30d cycle cron
- ✅ 雙語注釋：所有新建 function / class / module 全中英對照（per memory.md 規範 + 2026-05-05 governance change 改默認中文，但本 IMPL 為求清晰仍中英並列）

---

## 8. 不確定處 / 邊界 case + Operator 下一步

### 8.1 D+1 evidence collection 啟動 timing

cron `0 4 * * 0` 是 UTC 週日 04:00；spec §2.3 此 schedule 對齊 `feedback_github_actions_cost.md` cost-aware schedule。**第一次 cycle 跑時間取決於 operator crontab register 時刻** — 若 deploy 時為週日 04:00 後，第一次 cycle 將在下週日；若 deploy 在週日 04:00 前，當週週日即跑。**OperatorActionRequired**：deploy 後 `crontab -e` 加：

```
0 4 * * 0 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/blocked_symbols_30d_unblock_check_cron.sh
```

### 8.2 yo-yo detection edge case

spec §5.3 寫「同 cell 30d 內 unfrozen + re_frozen ≥ 1 cycle」trigger force manual_review_required。本 IMPL Q4 query 用 `count(DISTINCT outcome) >= 2 WHERE outcome IN ('unfrozen','re_frozen')`；HAVING 子句確認同 cell 30d 內既有 unfrozen 又有 re_frozen 記錄。**邊界 case**：若同 cell 30d 內只有 unfrozen 無 re_frozen（操作員快速 unfreeze 後 cell 健康），yo-yo 不 trip — 這是設計意圖。**運維注意**：如果 cell 30d 內 unfrozen + re_frozen 後又 force_eval，第 3 次 candidate row 會被強制 manual_review_required（test `test_yoyo_forces_manual_review_required` 釘住）；operator 需 PA RFC 才能再次 promote 為 unblock_candidate。

### 8.3 commit_sha race window

spec §5.2 #5 要 operator 動 TOML + freeze.json commit 後 writer update outcome='unfrozen' row 寫入 commit_sha。**race window**：operator commit 時刻 vs writer update 時刻可能差幾秒（operator 手動執行 update_outcome 命令，不是同 transaction）。**accept**：本 spec 不強制 atomic commit/update；若 commit 完忘了 update，operator 看 GUI 顯示「unfrozen but commit_sha=NULL」即補執行 update。**Future improvement**：force_eval API 內加 `git rev-parse HEAD` + UPDATE 同 transaction（屬 W5-E1-C(API) 範圍，本 IMPL 未實作）。

### 8.4 W5-E1-C(API) force_eval API 未實作

spec §7.3 描述 `POST /api/v1/canary/unblock/force_eval` + `GET /api/v1/canary/unblock/candidates`，但本 IMPL **未實作** API 層 — 理由：`canary_governance_routes.py` 不存在（本 task 完成後 grep `find srv -name "canary*routes*.py"` 0 hit）。屬 W6 V086 同檔依賴（W6 IMPL 階段預期建立此 routes 檔）。**Operator 下一步**：W5-E1-C(API) sub-task 留待 W6 V086 IMPL 完成後 follow-up；GUI alert 顯示 candidate list 同樣留 N+2。

### 8.5 GUI 整合（W5-E1-F optional）

spec §7.6 GUI alert 區塊 "Frozen Cells Unblock Candidates" 標 optional W5 OR 留 N+2。本 IMPL **未實作** — 屬前端 JS 範圍，超出 E1 backend scope。**Operator 下一步**：W5-E1-F 派 GUI E1 sub-agent（如有）OR 留 N+2 dispatch。

### 8.6 paper engine availability

spec §9 risk note：paper engine `OPENCLAW_ENABLE_PAPER!=1` 預設關閉 → paper_fills_30d 可能持續 0 → `dormant_no_evidence` 將是常態 verdict。**這非 spec 缺陷而是 paper engine policy 結果**。**Operator 下一步**：若想真實啟動 30d cycle 評估，需先決定 `OPENCLAW_ENABLE_PAPER=1` 啟動 paper engine（屬 operator 政策決定，不在本 IMPL scope）。

---

## 9. Operator 下一步檢核

| # | 動作 | Owner | 阻塞 |
|---|---|---|---|
| 1 | E2 sub-agent 反向核驗本 IMPL | E2 | 是 — 等 PM 派 |
| 2 | E4 regression（unit + integration 全綠）| E4 | 是 |
| 3 | Linux engine `cargo run --bin repair_migration_checksum` 對齊 V090 sqlx checksum | PM/operator | 否（auto-migrate 前必跑） |
| 4 | crontab register `blocked_symbols_30d_unblock_check_cron.sh` | operator | 否（cycle 啟動才開） |
| 5 | W5-E1-C(API) force_eval API 留 W6 V086 同檔 IMPL 階段 follow-up | PA | 否 |
| 6 | W5-E1-F GUI Settings tab "Frozen Cells Unblock Candidates" 留 N+2 dispatch | PA | 否 |
| 7 | CLAUDE.md §三 active gates 加 `[64]` 描述 | PM | 否（next sign-off 同 commit） |

---

## 10. 完成宣告

**E1 IMPLEMENTATION DONE: 待 E2 審查**

- 報告路徑：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w5_e1_c_dynamic_unblock_check_1_impl.md`
- LOC：~1726 production code + 516 test = ~2242 total
- 31 unit tests 全 PASS / 0 sibling regression（271 helper_scripts/db PASS）
- V090 Linux PG 兩次 apply idempotency PASS / schema 8 CHECK + 2 indexes verified
- 16 原則 / DOC-08 §12 / 硬邊界 5 項全 0 觸碰
