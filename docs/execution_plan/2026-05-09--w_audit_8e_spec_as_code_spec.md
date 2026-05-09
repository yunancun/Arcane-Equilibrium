# W-AUDIT-8e — Spec-as-Code + Module Lifecycle State Machine（R-5 IMPL Spec）

**Wave 名稱**：W-AUDIT-8e "Spec-as-Code"
**對應 ARCH-04 amendment**：R-5（ADR-0021 Accepted 2026-05-09）
**起草者**：PA（Project Architect）
**日期**：2026-05-09
**對齊上游**：
- `docs/adr/0021-alpha-source-architecture-upgrade.md`（Accepted 2026-05-09）R-5
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` Layer 3.6 + Layer 4 R-5 + Cluster D + Cluster E
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md` §1 Push Back 5 修正（Spec-Runtime drift 自動偵測缺位是真正 Root Cause 5）
- CLAUDE.md §三 衛生規則 + §三 數據 vs runtime drift 防線
- CLAUDE.md §七 SQL migration 規範 + Linux PG dry-run mandatory
- `helper_scripts/db/passive_wait_healthcheck.py`（既有 51 個 healthcheck）
**讀者**：Operator / PM / E1 / E2 / E4 / TW / R4 / CC compliance reviewer
**前置**：無 hard prerequisite；可與 W-AUDIT-8a/8b/8c/8d 全並行
**並行**：W-AUDIT-1..7（doc sync wave 直接 reframe）；W-AUDIT-3b/9（不衝突）
**生效範圍**：CI gate（GitHub Actions / pre-commit）+ helper_scripts/ci/ 新模組 + CLAUDE.md §三 stale check + Module Lifecycle header convention + 自動 SCRIPT_INDEX / SPECIFICATION_REGISTER 抽取；**不**改業務代碼、**不**改 GovernanceHub / Decision Lease

---

## §0 命名 + 編號 alignment

| 來源 | R-5 對應 wave |
|---|---|
| ADR-0021 | R-5 |
| PA fix plan v2 §5 | W-ARCH-3 |
| TODO.md v18 | W-AUDIT-8f |
| **本 spec** | **W-AUDIT-8e** |

---

## §1 Wave 範圍 + Goal

### 1.1 North Star（Push Back 5 採納）

把 **「Spec / Runtime / Doc 三套 SoT 漂移」**（Push Back 5 真正 Root Cause 5）從「人工 verify」升級為 **「CI forcing function 自動偵測 + 阻擋」**：

- CI gate：CLAUDE.md §三 stale > 7 day auto-fail
- 每個 module / table 加 `# LIFECYCLE: active|observing|deprecated|sunset` header convention
- helper_scripts/ci/spec_runtime_drift_check.py 與 healthcheck 整合
- 自動從代碼抽 SCRIPT_INDEX.md / SPECIFICATION_REGISTER（Doc Plane 從 first-class write surface 改為 derived）

**Push Back 5 採納**：
- 原 redesign Root Cause 5「5-Agent 拆分本身正確但靈魂沒裝」是「結論」不是 root cause
- 真正 Root Cause 5 = **「Spec-Runtime drift 自動偵測缺位，所有 audit 必須 PA/operator 手動 verify runtime 才知 spec 是否落地」**
- v2 verification 5/5 P0-DECISION-AUDIT 都需要 operator 手動拍板才能 close drift；W-AUDIT-3 runtime restart fail-closed metrics 仍未驗（spec 寫了無法核實）；W-AUDIT-4 6 表 INSERT 仍 0（source claim 與 runtime fact 漂移）

### 1.2 Wave 範圍邊界

**本 wave 含**：
1. CI gate `helper_scripts/ci/spec_runtime_drift_check.py`：
   - CLAUDE.md §三「runtime 數值 + 採集時間」row 滿 7 日 auto-fail
   - SPECIFICATION_REGISTER entries 與 PG schema 對應（table not exists → drift）
   - SCRIPT_INDEX.md entries 與 helper_scripts/ 實際檔案對應
2. Module Lifecycle Header Convention：
   - 所有 Python module 在 `# MODULE_NOTE` 或第一個 docstring 加 `# LIFECYCLE: active|observing|deprecated|sunset`
   - 所有 Rust mod 在 `//!` 起始注釋加 `// LIFECYCLE: ...`
   - 所有 PG table COMMENT 加 `LIFECYCLE: ...`
3. 新增 V### migration `governance.module_lifecycle`（Module + Table lifecycle 元資料表）
4. 自動抽 SCRIPT_INDEX.md：`helper_scripts/ci/extract_script_index.py` 從 `helper_scripts/**/MODULE_NOTE` 抽
5. 自動抽 SPECIFICATION_REGISTER：`helper_scripts/ci/extract_specification_register.py` 從 `docs/decisions/*.md` + `docs/governance_dev/*.md` 抽
6. CLAUDE.md §三 cron healthcheck `[新-claude_md_section3_freshness]`：每日掃 §三 row 採集時間 stale
7. pre-commit hook：commit 改動 module / table 時必 check LIFECYCLE header 存在
8. healthcheck `[新-spec_runtime_drift_health]`：總體 drift 計數 < threshold

**本 wave 不含**（明確邊界）：
- 重寫既有 docs/decisions/ 全部 .md（漸進補 LIFECYCLE annotation，不一次大改）
- 自動同步 TODO.md → GitHub Issues（CLAUDE.md §十一「策展鏡像 only」）
- AI 自動寫 spec（仍 PA / operator 寫，CI 只 verify drift）
- ML pipeline / DB schema 自動審計（W-AUDIT-4b 範圍）

### 1.3 為什麼這是 Tier-2 leverage（修正版）

**證據**（PA fix plan v2 §1 Push Back 5）：
- v2 verification §3 P0-DECISION-AUDIT 5/5 拍板過程都需 operator 手動介入解 spec 衝突
- v2 §6 outstanding：W-AUDIT-3 runtime restart fail-closed metrics 未驗（spec 寫了無法核實）
- v2 §6：DSR/PBO promotion gate source/test closed 但 runtime evidence 0
- v2 §6：W-AUDIT-4 6 表 0 INSERT + cron not installed = source claim 與 runtime fact 漂移

**Tier-2 而非 Tier-1 理由**：
- 本身不直接生產 alpha（不像 R-1 / R-2 / R-3）
- 但是 R-1..R-4 的「治理 forcing function」substrate（沒有 spec-as-code，R-1..R-4 仍會 drift）
- 與 W-AUDIT-1 doc sync wave 高度重疊（per fix plan v2 §5 表「W-ARCH-3 Spec-as-Code 替原 R-5」）

**漸進策略**：
- Phase 1（Sprint N+0）：CI gate + healthcheck + LIFECYCLE convention（不強制 backfill）
- Phase 2（Sprint N+1）：漸進 backfill 既有 module / table 的 LIFECYCLE header（每 sprint ~20 module）
- Phase 3（Sprint N+2）：自動抽 SCRIPT_INDEX / SPECIFICATION_REGISTER

---

## §2 接口設計

### 2.1 LIFECYCLE header convention

**Python module 範例**：
```python
"""
MODULE_NOTE: app/governance/live_budget_manager.py
功能：per-alpha-source live budget 管理 6-state state machine
LIFECYCLE: active
SUNSET_TRIGGER: ARCH-04 R-4 superseded by next-gen budget model
依賴：governance.live_budgets table、AlphaSourceRegistry、Decision Lease
"""
```

**Rust module 範例**：
```rust
//! tick_pipeline/mod.rs — TickContext + AlphaSurface populate + 5 strategy dispatch
//!
//! LIFECYCLE: active
//! SUNSET_TRIGGER: 無（核心 hot path）
```

**PG table COMMENT 範例**：
```sql
COMMENT ON TABLE learning.hypotheses IS 'LIFECYCLE: active; SUNSET_TRIGGER: ARCH-04 R-3 obsolete by Foundation Model autonomous learning. R-3 IMPL: docs/execution_plan/2026-05-09--w_audit_8c_hypothesis_pipeline_spec.md';
```

**4 stage 定義**：

| Stage | 定義 | 例子 |
|---|---|---|
| `active` | Production 正常使用 | tick_pipeline / Decision Lease / Guardian |
| `observing` | 新引入 / 灰度中 / 待 evidence | AlphaSourceRegistry observing entries |
| `deprecated` | 已廢棄但仍 dispatch / read（避免 sudden drop）| funding_arb v2 / `_REGIME_STRATEGY_PREFERENCES` hardcoded |
| `sunset` | 終止使用，等下一個 cleanup wave 刪除 | 已退役 strategy / 過期 ML schema |

### 2.2 `governance.module_lifecycle` table schema

```sql
CREATE TABLE IF NOT EXISTS governance.module_lifecycle (
    lifecycle_id BIGSERIAL PRIMARY KEY,
    -- Module 定位
    module_kind VARCHAR(32) NOT NULL CHECK (module_kind IN ('python_module','rust_mod','pg_table','pg_function','helper_script','spec_doc','adr','agent','skill')),
    module_path TEXT NOT NULL,                    -- e.g. 'app/governance/live_budget_manager.py'
    -- Lifecycle 狀態
    stage VARCHAR(32) NOT NULL CHECK (stage IN ('active','observing','deprecated','sunset')),
    sunset_trigger TEXT,                          -- 「ARCH-04 R-4 superseded」
    -- Audit
    last_verified_ms BIGINT NOT NULL,             -- CI 最後跑 drift check 通過時間
    last_modified_ms BIGINT NOT NULL,             -- git log 最後修改時間
    drift_score INT NOT NULL DEFAULT 0,           -- 0=clean, 1+=drift detected
    drift_reason TEXT,
    -- Metadata
    owner VARCHAR(64),
    notes TEXT,
    -- 時間戳
    created_ms BIGINT NOT NULL,
    updated_ms BIGINT NOT NULL,
    UNIQUE (module_kind, module_path)
);

CREATE INDEX IF NOT EXISTS idx_module_lifecycle_stage ON governance.module_lifecycle(stage, drift_score);
CREATE INDEX IF NOT EXISTS idx_module_lifecycle_drift ON governance.module_lifecycle(drift_score) WHERE drift_score > 0;
```

### 2.3 CI gate `helper_scripts/ci/spec_runtime_drift_check.py`

```python
# helper_scripts/ci/spec_runtime_drift_check.py
"""
MODULE_NOTE: spec_runtime_drift_check.py
功能：CI forcing function 自動偵測 spec / runtime / doc 三套 SoT drift
LIFECYCLE: active
SUNSET_TRIGGER: 無（治理基礎設施）
"""

class SpecRuntimeDriftChecker:
    def check_claude_md_section3_freshness(self) -> CheckResult:
        """
        掃 CLAUDE.md §三「runtime 數值 + 採集時間」row：
        - 每行解析「2026-05-09 09:41 UTC」格式 timestamp
        - 滿 7 day auto-fail
        - 返回 stale row list + suggested update
        """

    def check_specification_register_alignment(self) -> CheckResult:
        """
        SPECIFICATION_REGISTER entries 與實際對應：
        - LG-X / EX-X / SM-X / DOC-X 命名
        - status: Active / Superseded / Frozen
        - 引用 IMPL spec doc 路徑存在
        """

    def check_script_index_alignment(self) -> CheckResult:
        """
        SCRIPT_INDEX.md entries 與 helper_scripts/ 實際檔案對應：
        - SCRIPT_INDEX.md 列出但 file 不存在 → drift
        - file 存在但 SCRIPT_INDEX.md 無 → drift
        """

    def check_module_lifecycle_headers(self) -> CheckResult:
        """
        每個 module / table / spec doc 必有 LIFECYCLE header：
        - Python: 第一個 docstring 含 'LIFECYCLE: '
        - Rust: //! 起始注釋含 'LIFECYCLE: '
        - PG table: COMMENT ON TABLE 含 'LIFECYCLE: '
        - PA / E2 / TW review failure 阻 PR
        """

    def check_pg_schema_drift(self) -> CheckResult:
        """
        SPECIFICATION_REGISTER 列出的 PG table / function 與實際 PG 對應：
        - table_exists check
        - function_signature check
        - migration history 對齊
        """

    def overall_drift_score(self) -> int:
        """總 drift count；高於 threshold → CI fail"""
```

### 2.4 GitHub Actions workflow

```yaml
# .github/workflows/spec_runtime_drift_check.yml
name: Spec-Runtime Drift Check

on:
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 8 * * *'  # daily 08:00 UTC

jobs:
  drift_check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run drift check
        run: |
          python3 helper_scripts/ci/spec_runtime_drift_check.py --strict
      - name: Fail on drift
        if: failure()
        run: |
          echo "::error::Spec-Runtime drift detected. See report for details."
          exit 1
```

### 2.5 pre-commit hook

```yaml
# .pre-commit-config.yaml（新增 hook）
- repo: local
  hooks:
    - id: lifecycle-header-check
      name: LIFECYCLE header check
      entry: python3 helper_scripts/ci/lifecycle_header_check.py
      language: system
      files: ^(app/|rust/|sql/migrations/|helper_scripts/).*\.(py|rs|sql)$
```

### 2.6 自動抽 SCRIPT_INDEX / SPECIFICATION_REGISTER

```python
# helper_scripts/ci/extract_script_index.py
"""從 helper_scripts/**/*.py 的 MODULE_NOTE 抽 SCRIPT_INDEX.md"""

def extract_module_notes() -> Dict[str, ModuleInfo]:
    """掃所有 helper_scripts/**/*.py，抽 MODULE_NOTE block"""

def render_script_index_md(modules: Dict[str, ModuleInfo]) -> str:
    """生成 docs/SCRIPT_INDEX.md（覆寫，git diff verification）"""

# CI: 跑此腳本後 git diff 必 clean，否則 fail
```

```python
# helper_scripts/ci/extract_specification_register.py
"""從 docs/decisions/*.md + docs/governance_dev/*.md 抽 SPECIFICATION_REGISTER"""

def extract_spec_registers() -> List[SpecRegister]:
    """掃 docs/decisions/ 含 LG-X/EX-X/SM-X 命名的 spec doc"""

def render_specification_register_md(specs: List[SpecRegister]) -> str:
    """生成 docs/SPECIFICATION_REGISTER.md"""
```

---

## §3 Deliverable（Sub-task 拆分）

| Sub-task | Owner | Person-day | 並行度 |
|---|---|---:|---|
| **R5-T1** V### migration `governance.module_lifecycle` | E1 + MIT review | 1.5 | 並行 |
| **R5-T2** `helper_scripts/ci/spec_runtime_drift_check.py` 主檢查器 | E1 + TW + R4 review | 3.0 | 並行 |
| **R5-T3** GitHub Actions workflow | E1 + CC compliance review | 1.0 | 並行 |
| **R5-T4** pre-commit hook lifecycle_header_check | E1 | 1.0 | 並行 |
| **R5-T5** `extract_script_index.py` + render SCRIPT_INDEX.md | E1 + TW review | 1.5 | 並行 |
| **R5-T6** `extract_specification_register.py` + render SPECIFICATION_REGISTER.md | E1 + TW review | 1.5 | 並行 |
| **R5-T7** healthcheck `[新-spec_runtime_drift_health]` + `[新-claude_md_section3_freshness]` | E1 | 1.0 | 並行 |
| **R5-T8** 漸進 backfill 既有 module LIFECYCLE header（top 30 critical module）| E1×3 並行 | 4.5 | 並行 |
| **R5-T9** 漸進 backfill 既有 PG table COMMENT LIFECYCLE | E1 + MIT | 2.0 | 並行 |
| **R5-T10** Integration test（PR with drift → CI fail / PR clean → CI PASS）| E4 | 2.0 | 串行 R5-T2/T3/T4 |
| **R5-T11** ADR + W-AUDIT-1 reframe | PA + TW | 1.0 | 並行 |
| **總計** | | **~20 person-day（2-3 sprint）** | |

### 3.1 Phase 漸進策略

| Phase | Sprint | 內容 |
|---|---|---|
| Phase 1 (must) | N+0 | R5-T1/T2/T3/T4/T7/T10 — CI gate + healthcheck land |
| Phase 2 | N+1 | R5-T8/T9 — 漸進 backfill top 30 critical module + PG table |
| Phase 3 | N+2 | R5-T5/T6 — 自動抽 SCRIPT_INDEX / SPECIFICATION_REGISTER |
| Phase 4 | N+3+ | 持續 backfill 剩餘 module（ongoing maintenance） |

**漸進策略理由**：避免一次大改破壞 PR velocity；CI gate 先 land 為 forcing function，backfill 隨 wave 進度 piggyback。

---

## §4 Acceptance Criteria

### 4.1 R5-T1 V### migration governance.module_lifecycle
- Guard A/B/C 完整
- 兩次 idempotent apply 驗 PASS
- Linux PG dry-run mandatory

### 4.2 R5-T2 spec_runtime_drift_check.py
- 5 個 check function 完整 IMPL（CLAUDE.md §三 / SPECIFICATION_REGISTER / SCRIPT_INDEX / module lifecycle / PG schema）
- 每個 check function 各 ≥ 3 unit test（happy path / drift detected / edge）
- TW + R4 review sign-off

### 4.3 R5-T3 GitHub Actions
- workflow 在 PR + daily cron 都觸發
- drift detected → CI fail
- CC compliance review sign-off

### 4.4 R5-T4 pre-commit hook
- commit 改動 module / table / migration 時必 check LIFECYCLE header
- header 缺失 → commit reject

### 4.5 R5-T5 extract_script_index.py
- 從 MODULE_NOTE 抽 ≥ 50 helper_scripts entries
- render SCRIPT_INDEX.md 與既有檔案 git diff clean
- TW review sign-off

### 4.6 R5-T6 extract_specification_register.py
- 從 docs/decisions/ + docs/governance_dev/ 抽 ≥ 30 spec entries
- render SPECIFICATION_REGISTER.md 與既有檔案 git diff clean

### 4.7 R5-T7 healthcheck
- `[新-spec_runtime_drift_health]` 24h 0 high-severity drift
- `[新-claude_md_section3_freshness]` 0 stale > 7d row
- PASS / WARN / FAIL 對齊

### 4.8 R5-T8/T9 backfill
- top 30 critical module（Decision Lease / Guardian / SM-04 / IntentProcessor / 5 strategies / GovernanceHub / Strategist / Analyst / Executor / etc）全有 LIFECYCLE header
- 至少 20 個 PG table 有 LIFECYCLE COMMENT

### 4.9 R5-T10 Integration test
- 構造 1 個 drift PR（CLAUDE.md §三 row 改 timestamp 8 day ago）→ CI fail
- 構造 1 個 clean PR → CI PASS

### 4.10 R5-T11 ADR + W-AUDIT-1 reframe
- ADR-0021 R-5 IMPL DONE 補
- W-AUDIT-1 doc sync wave 加「Spec-as-Code 自動化 dimension」（per fix plan v2 §5 表「W-ARCH-3 替原 R-5」）

### 4.11 Wave 整體 acceptance
- TODO.md 加 W-AUDIT-8e 完成 status
- CI gate 連續 3 個 PR 跑 PASS（無 false positive）
- 24h 自動 drift count 比 baseline -50%

---

## §5 依賴關係 + Risk

### 5.1 上下游依賴

| 依賴 | 性質 | 處理 |
|---|---|---|
| W-AUDIT-1 doc sync wave | **Soft** | R-5 reframe W-AUDIT-1 為 doc 自動化 wave |
| W-AUDIT-3b runtime smoke | **無** | 並行 |
| W-AUDIT-4b INSERT path | **無** | 並行 |
| W-AUDIT-8a/8b/8c/8d | **無** | 並行（R-5 是 forcing function，不 produce alpha） |
| 既有 healthcheck 系統 | **整合** | 加 2 個新 healkcheck |
| 既有 SCRIPT_INDEX.md | **改寫源** | 從 manual 改自動抽 |

### 5.2 Risk + Fallback

| Risk | 機率 | Mitigation | Fallback |
|---|---|---|---|
| CI gate false positive 阻 PR | **高** | Phase 1 先「warn-only」mode，Phase 2 切「strict」 | feature flag 切 warn-only |
| pre-commit hook 拒 commit 引發 operator 摩擦 | 中 | hook 提供 `# LIFECYCLE: active` quick template | hook 加 skip flag（緊急 commit） |
| backfill workload 大 ~30 module + 20 table | 中 | 漸進策略，per-sprint ~10 backfill | 不阻 R-5 land；ongoing maintenance |
| extract_script_index / extract_spec_register render 與 manual 既有不一致 | 高 | Phase 3 才開；先手動對齊 baseline | 對 conflict diff 手動 resolve |
| LIFECYCLE 4 stage 過細 / 過粗 | 中 | 4 stage 與 AlphaSourceRegistry 對齊（R-2 同 schema） | 漸進加 sub-stage |

### 5.3 與 W-AUDIT-3b/9 衝突點

| 衝突 | 性質 | Mitigation |
|---|---|---|
| W-AUDIT-3b ExecutorAgent runtime smoke | **無衝突** | R-5 不碰 ExecutorAgent |
| W-AUDIT-9 graduated canary | **協同** | R-5 LIFECYCLE 對 5-stage canary 有對應（observing / active 對 stage 1/4） |
| W-AUDIT-1 doc sync wave | **reframe** | per fix plan v2 §5 表 W-AUDIT-1 升級為 doc 自動化 wave |

---

## §6 E2 Review Checklist

**E2 review 必查 5 點**：
1. **CI gate 無 false positive**：5 check function 各跑 100 random scenario，false positive < 1%
2. **pre-commit hook 不阻常規 commit**：既有 module 修改不需補 LIFECYCLE（漸進 backfill）；只新建 module 必補
3. **extract_script_index / extract_spec_register render 確定性**：100 random run 結果 byte-identical
4. **LIFECYCLE convention 對齊 AlphaSourceRegistry stage**：4 stage 與 R-2 一致（避免不同 schema）
5. **CLAUDE.md §三 stale check 不誤殺**：採集時間 7 day 內 100% PASS；7 day +1 hr 100% FAIL

**E2 推回情況**：
- false positive > 5% → 推回
- pre-commit hook 阻常規 commit → 推回
- LIFECYCLE 4 stage 與 R-2 schema 不一致 → 推回

---

## §7 E4 Regression Checklist

**E4 必跑 5 個 regression**：
1. **既有 51 healthcheck 不破**：本 wave 加 2 healthcheck，既有 49+2 全 PASS
2. **既有 PR velocity 不退化**：sample 30 個既有 PR replay，全 CI PASS
3. **drift PR detection**：構造 5 種 drift scenario，全 CI fail
4. **clean PR baseline**：構造 5 種 clean PR，全 CI PASS
5. **render determinism**：extract_script_index 跑 10 次，git diff clean 10 次

---

## §8 落地 Side Effect

### 8.1 CLAUDE.md §三 加 W-AUDIT-8e row + healthcheck `[新-spec_runtime_drift_health]` + `[新-claude_md_section3_freshness]`

### 8.2 CLAUDE.md §七 加 LIFECYCLE convention 章節

新加 sub-section 「Module Lifecycle Header Convention」：
```
所有新 module（Python / Rust / PG table / spec doc）必含 LIFECYCLE header（active / observing / deprecated / sunset）。
template:
- Python: docstring 加 `LIFECYCLE: active`
- Rust: //! 加 `LIFECYCLE: active`
- PG: COMMENT 加 `LIFECYCLE: active; SUNSET_TRIGGER: ...`
CI gate: helper_scripts/ci/spec_runtime_drift_check.py
```

### 8.3 W-AUDIT-1 doc sync wave reframe

W-AUDIT-1 從「manual doc sync」reframe 為「automated doc sync via R-5 spec-as-code substrate」（per ADR-0021 Consequences §「Supersedes / impacts」）。

### 8.4 ADR-0021 status update
R-5 IMPL DONE 補 References。

### 8.5 SPECIFICATION_REGISTER + SCRIPT_INDEX
從 manual maintain 改 auto-extracted。

### 8.6 PA memory 更新
- 教訓：Push Back 5 採納；原 redesign Root Cause 5「5-Agent skeleton without soul」是結論不是 root cause
- 經驗：Spec-as-Code 是 R-1..R-4 的 forcing function substrate，不直接 produce alpha 但保 architectural drift 不累積

---

## §9 PM 接收後動作

1. R5-T1/T2/T3/T4/T7 並行（CI gate Phase 1）
2. R5-T10 串行驗 CI gate
3. R5-T8/T9 漸進 backfill（Sprint N+1）
4. R5-T5/T6 自動抽 INDEX/REGISTER（Sprint N+2）
5. R5-T11 ADR + W-AUDIT-1 reframe
6. PASS 後 Track A 全 wave 完成 → roadmap 進 supervised live 規劃帶評估

---

`PA DESIGN DONE: report path: srv/docs/execution_plan/2026-05-09--w_audit_8e_spec_as_code_spec.md`
