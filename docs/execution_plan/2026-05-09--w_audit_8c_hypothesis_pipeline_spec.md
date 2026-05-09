# W-AUDIT-8c — Hypothesis Pipeline First-Class Object（R-3 IMPL Spec）

**Wave 名稱**：W-AUDIT-8c "Hypothesis Pipeline"
**對應 ARCH-04 amendment**：R-3（ADR-0021 Accepted 2026-05-09）
**起草者**：PA（Project Architect）
**日期**：2026-05-09
**對齊上游**：
- `docs/adr/0021-alpha-source-architecture-upgrade.md`（Accepted 2026-05-09）R-3
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md` §1 Push Back 3 + Push Back 4 修正
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` Layer 3.4 + Layer 4 R-3
- `docs/decisions/EX-05_OpenClaw_Bybit_Learning_Boundary_..._V2.md`（Hypothesis 既有 Stage 3 定義 + POST endpoint 既有 spec）
- `docs/decisions/DOC-04_..._V2.md` §L3 「假說實驗」（Generate testable hypotheses + paper engine validation）
- `docs/decisions/DOC-06_..._V2.md` §「Generate hypotheses 🟢 GREEN — Analyst L2+ can auto-generate」
**讀者**：Operator / PM / E1 / E2 / E4 / MIT / QC / Analyst Agent author
**前置（強）**：W-AUDIT-4b 必先 land（label_close_tag NULL writer fix + 6 表 INSERT path）— Push Back 4 修正後嚴格 prerequisite
**前置（軟）**：W-AUDIT-8b R-2 land（Strategist→Analyst MessageBus topic + AlphaHypothesis schema 已 land）
**並行**：W-AUDIT-8a Phase B/C/D；W-AUDIT-9；W-AUDIT-3b
**生效範圍**：Python `analyst_agent.py` Hypothesis state machine + 新 V### migration `learning.hypotheses` + Decision Lease / ExecutionPlan / fills 加 `originating_hypothesis_id` 欄位 + attribution chain 重寫；**不**改 Rust strategies trait、**不**改 SM-04 ladder

---

## §0 命名 + 編號 alignment

| 來源 | R-3 對應 wave |
|---|---|
| ADR-0021 | R-3 |
| PA fix plan v2 §5 | W-AUDIT-8f |
| TODO.md v18 | W-AUDIT-8d |
| **本 spec** | **W-AUDIT-8c** |

---

## §1 Wave 範圍 + Goal

### 1.1 North Star（修正版，Push Back 3 + 4 接受）

把 Hypothesis 從 **「Analyst 內部欄位」** 升級為 **「Decision Lease 同治理層級的 first-class governance object」**：

- 新增 V### migration `learning.hypotheses` table + state machine（DRAFT → REGISTERED → EXPERIMENTING → EVIDENCE_GATE → PROMOTED|REJECTED|EXPIRED）
- Decision Lease + ExecutionPlan + fills 全 propagate `originating_hypothesis_id`
- attribution chain 重寫 base on hypothesis_id（而非當前 0.5% denominator artifact 路徑）
- Analyst L2-L3 真實 IMPL（Push Back 3 修正後：**獨立於 ADR-0020 Layer 2 manual**，L0+L1 Ollama 跑 95% workload）

**修正點（vs PA fix plan v2 §0 + Push Back 3 + Push Back 4）**：
- Push Back 3 採納：**Analyst L2-L3 IMPL 不需 ADR-0020 reverse**；L0+L1 Ollama 13B 模型對「找模式 / 列假設」夠用
- Push Back 4 採納：**W-AUDIT-4b 必先於 R-3** — 不修 attribution writer chain，hypothesis pipeline 設計再完美仍無 evidence 餵
- Push Back 1（Strategy Interface 偏差降一檔）部分被 4-agent consensus 推翻，但 R-3 仍是 first-class governance object（不是 ADR-0020 reverse）

### 1.2 Wave 範圍邊界

**本 wave 含**：
1. V### migration `learning.hypotheses` table + state machine + Guard A/B/C
2. Python `app/learning/hypothesis_pipeline.py` 新模組（state machine + CRUD + advisory lock）
3. `analyst_agent.py` L2-L3 IMPL：
   - L2 pattern discovery（從 `learning.attribution_chain` 真實餵 + `surface.regime` panel 觀察）
   - L3 hypothesis generation（從 L2 pattern → AlphaHypothesis emit → REGISTER 到 `learning.hypotheses`）
4. Decision Lease 加 `originating_hypothesis_id` 欄位（V### migration alter）
5. ExecutionPlan 加 `originating_hypothesis_id` 欄位（V### migration alter）
6. fills 加 `originating_hypothesis_id` 欄位（V### migration alter）
7. attribution chain 重寫：MLDE writer → hypothesis_id INSERT path
8. Operator GUI 加「Hypothesis Lab」view（read-only + manual verdict approval for HIGH-impact hypothesis）

**本 wave 不含**（明確邊界）：
- Per-alpha-source Live Promotion Gate（→ W-AUDIT-8d R-4）
- Layer 2 cloud reasoning auto-loop（ADR-0020 維持）
- Analyst L4-L5 IMPL（dormant by ADR-0020 spec）
- Hypothesis 自動 promotion 到 production（Phase 1 manual approval）

### 1.3 為什麼這是 Tier-1 leverage（修正版 + Push Back 4 採納）

當前 `attribution_chain_ok` 24h 0.5041%（v2 verification §1）= denominator artifact，分子 ok_n 只 +47% 增長，分母同步漲。**這不是 SQL bug，是沒有 hypothesis 來歸因**。

W-AUDIT-4b 修了 label_close_tag NULL writer + 6 表 INSERT path 後，**仍需要 hypothesis_id 才能讓 attribution chain 有意義**。每筆 fill 若有 originating_hypothesis_id，attribution 是 trivial：「fill outcome → hypothesis_id → win/loss → update DSR/PBO/Sharpe → verdict」。

R-3 解這個 leverage 缺口：把 hypothesis 從「散在各 Agent 的內部欄位」升為「PG 表 + state machine + audit chain」，attribution 的「為什麼這筆交易發生」永遠有 typed 答案。

---

## §2 接口設計

### 2.1 `learning.hypotheses` table schema（V### migration）

```sql
CREATE TABLE IF NOT EXISTS learning.hypotheses (
    hypothesis_id BIGSERIAL PRIMARY KEY,
    -- 提案來源
    proposer_agent VARCHAR(64) NOT NULL,        -- 'strategist' / 'analyst' / 'operator'
    proposed_at_ms BIGINT NOT NULL,
    -- 假設內容
    statement TEXT NOT NULL,                    -- 「ranging regime + funding skew > 1.5σ → spread alpha」
    null_hypothesis TEXT NOT NULL,              -- 「funding skew dispersion 對 ranging regime 無 effect」
    target_alpha_sources TEXT[] NOT NULL,       -- AlphaSourceTag array
    experiment_target_strategy VARCHAR(64),     -- 既有 strategy / NULL
    regime_context VARCHAR(32) NOT NULL,
    -- 證據契約
    evidence_n_min INT NOT NULL DEFAULT 100,
    evidence_dsr_min DECIMAL(10,6) NOT NULL DEFAULT 0.7,
    evidence_pbo_max DECIMAL(10,6) NOT NULL DEFAULT 0.3,
    evidence_sharpe_min DECIMAL(10,6),          -- optional
    -- 狀態機
    state VARCHAR(32) NOT NULL CHECK (state IN ('DRAFT','REGISTERED','EXPERIMENTING','EVIDENCE_GATE','PROMOTED','REJECTED','EXPIRED')),
    state_updated_ms BIGINT NOT NULL,
    -- 實驗 metadata
    experiment_started_ms BIGINT,
    experiment_completed_ms BIGINT,
    n_samples_observed INT NOT NULL DEFAULT 0,
    realized_sharpe DECIMAL(10,6),
    realized_dsr DECIMAL(10,6),
    realized_pbo DECIMAL(10,6),
    -- Verdict
    verdict_at_ms BIGINT,
    verdict VARCHAR(32) CHECK (verdict IN ('CONFIRMED','REJECTED','INCONCLUSIVE')),
    verdict_notes TEXT,
    verdict_approved_by VARCHAR(32),            -- 'analyst' (auto) / 'operator' (manual)
    -- 治理 trace
    audit_trace_id VARCHAR(128),                -- 對應 Strategist H1 ThoughtGate / Analyst L3 trace
    parent_hypothesis_id BIGINT REFERENCES learning.hypotheses(hypothesis_id),  -- 衍生 hypothesis chain
    notes TEXT,
    -- 時間戳
    created_ms BIGINT NOT NULL,
    updated_ms BIGINT NOT NULL
);

-- Guard A: column existence check before subsequent migrations
-- Guard B: state column type check
-- Guard C: hot-path index
CREATE INDEX IF NOT EXISTS idx_hypotheses_state ON learning.hypotheses(state, state_updated_ms);
CREATE INDEX IF NOT EXISTS idx_hypotheses_proposer ON learning.hypotheses(proposer_agent, proposed_at_ms);
CREATE INDEX IF NOT EXISTS idx_hypotheses_alpha_sources ON learning.hypotheses USING GIN(target_alpha_sources);

-- Retention policy: 365 day（hypothesis verdict 有長期 reference value）
```

**migration name**：`V0xx__learning_hypotheses_first_class.sql`（V### number 待 W-AUDIT-4b apply 後決定）

### 2.2 Hypothesis state machine

```
DRAFT  ──proposer signs──→  REGISTERED
        │
        └── timeout 7d ──→  EXPIRED

REGISTERED ──Analyst L3 dispatch──→  EXPERIMENTING
            │
            └── manual override ──→  REJECTED

EXPERIMENTING ──n_samples ≥ evidence_n_min──→  EVIDENCE_GATE
              │
              └── timeout 30d ──→  EXPIRED

EVIDENCE_GATE ──DSR ≥ min, PBO ≤ max, manual approve──→  PROMOTED
              │
              └── DSR < min OR PBO > max ──→  REJECTED

PROMOTED ──→  AlphaSourceRegistry.transition_stage(OBSERVING → ACTIVE)
REJECTED ──→  AlphaSourceRegistry.transition_stage(OBSERVING → DEPRECATED)
EXPIRED ──→  AlphaSourceRegistry.transition_stage(OBSERVING → SUNSET)
```

**強制機制**：
- 每個新策略 / 新參數 / 新 risk budget 變更必須有 originating Hypothesis（Phase 1 為 advisory，Phase 2 為 enforced）
- Hypothesis 狀態機強制 EVIDENCE_GATE 才能 PROMOTED
- HIGH-impact hypothesis（影響 risk budget / live promotion / strategy retire）verdict 必 manual approval（per EX-05 §5 spec）
- Verdict 持久化 → MLDE 訓練資料

### 2.3 Decision Lease + ExecutionPlan + fills 加欄位

```sql
-- Decision Lease
ALTER TABLE governance.decision_leases
    ADD COLUMN IF NOT EXISTS originating_hypothesis_id BIGINT
    REFERENCES learning.hypotheses(hypothesis_id);

CREATE INDEX IF NOT EXISTS idx_decision_leases_hypothesis
    ON governance.decision_leases(originating_hypothesis_id)
    WHERE originating_hypothesis_id IS NOT NULL;

-- ExecutionPlan
ALTER TABLE replay.execution_plan
    ADD COLUMN IF NOT EXISTS originating_hypothesis_id BIGINT
    REFERENCES learning.hypotheses(hypothesis_id);

-- fills
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS originating_hypothesis_id BIGINT
    REFERENCES learning.hypotheses(hypothesis_id);
```

**propagation 邏輯**：
1. Strategist `propose_hypothesis()` → INSERT `learning.hypotheses` (state=DRAFT)
2. Analyst L3 dispatch → UPDATE state=REGISTERED → EXPERIMENTING
3. Strategy 在 EXPERIMENTING 狀態下產生 StrategyAction → IntentProcessor inject `originating_hypothesis_id` to Decision Lease + ExecutionPlan
4. fill 時 fill writer 從 ExecutionPlan 拿 hypothesis_id 寫入 fills.originating_hypothesis_id
5. attribution writer 從 fills.originating_hypothesis_id 反查 update `learning.hypotheses.realized_*` 欄位

### 2.4 Python HypothesisPipeline class

```python
# app/learning/hypothesis_pipeline.py
class HypothesisState(str, Enum):
    DRAFT = "DRAFT"
    REGISTERED = "REGISTERED"
    EXPERIMENTING = "EXPERIMENTING"
    EVIDENCE_GATE = "EVIDENCE_GATE"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class HypothesisPipeline:
    def register(
        self,
        proposer: str,
        statement: str,
        null_hypothesis: str,
        target_alpha_sources: List[str],
        evidence_required: dict,
        regime_context: str,
        audit_trace_id: str,
    ) -> int:
        """DRAFT → REGISTERED；返回 hypothesis_id"""

    def dispatch_to_experiment(self, hypothesis_id: int) -> bool:
        """REGISTERED → EXPERIMENTING；接 Analyst L3"""

    def update_evidence(self, hypothesis_id: int, n_samples: int, sharpe: float, dsr: float, pbo: float) -> None:
        """EXPERIMENTING 狀態下 UPDATE realized_* 欄位"""

    def gate_check(self, hypothesis_id: int) -> Optional[Verdict]:
        """EXPERIMENTING → EVIDENCE_GATE；evidence 達標進 gate"""

    def submit_verdict(
        self,
        hypothesis_id: int,
        verdict: str,                  # CONFIRMED / REJECTED / INCONCLUSIVE
        approved_by: str,              # analyst / operator
        notes: str,
    ) -> bool:
        """EVIDENCE_GATE → PROMOTED / REJECTED；HIGH-impact 必 operator approve"""

    def expire_stale(self) -> int:
        """掃過期：DRAFT 7d / EXPERIMENTING 30d → EXPIRED"""
```

### 2.5 Analyst L2-L3 IMPL（Push Back 3 採納：L0+L1 only）

```python
# analyst_agent.py
class AnalystAgent(BaseAgent):
    async def l2_pattern_discovery(self):
        """
        L2: 從 learning.attribution_chain + surface.regime panel 觀察 patterns
        - 跑在 L0 規則 + L1 Ollama (~13B model)，**不**escalate Layer 2
        - 輸出 PatternInsight (regime / strategy / alpha_source / observed_effect_size)
        """

    async def l3_hypothesis_generation(self, pattern: PatternInsight) -> AlphaHypothesis:
        """
        L3: 從 L2 PatternInsight 生 testable hypothesis
        - 用 L1 Ollama 把 pattern 翻譯成 (statement, null_hypothesis, evidence_required)
        - 投 HypothesisPipeline.register()
        """

    async def l3_dispatch_experiment(self, hypothesis_id: int) -> None:
        """
        L3: 把 REGISTERED hypothesis dispatch 到 paper engine 跑 experiment
        - 設置 strategy ctor + alpha source binding
        - HypothesisPipeline.dispatch_to_experiment()
        """
```

**ADR-0020 invariant 維持**：
- Analyst L2-L3 完全在 L0 規則 + L1 Ollama 內跑
- 任何「跨 strategy 戰略級提案」（L4 / 政策變更）escalate Layer 2 manual + supervisor-only
- Layer 2 cloud reasoning 保 ADR-0020 manual + supervisor-only by design

### 2.6 GUI Hypothesis Lab tab（A3 review）

新增 GUI tab `hypothesis_lab`（14→15 tab）：
- 顯示 `learning.hypotheses` 全部 state（filter by state / proposer / alpha_source）
- HIGH-impact hypothesis verdict 提交（operator approve）：UI 提交 → POST `/api/v1/learning/hypothesis/{id}/verdict`（既有 EX-05 spec）
- A3 review：a11y + focus management

---

## §3 Deliverable（Sub-task 拆分）

| Sub-task | Owner | Person-day | 並行度 |
|---|---|---:|---|
| **R3-T1** V### migration `learning.hypotheses` + Guard A/B/C | E1 + MIT review | 2.0 | 並行 |
| **R3-T2** V### migration alter Decision Lease/ExecutionPlan/fills | E1 + MIT review | 1.0 | 串行 R3-T1 |
| **R3-T3** Python `hypothesis_pipeline.py` state machine + CRUD | E1 | 3.0 | 並行（mock DB） |
| **R3-T4** Analyst L2 pattern_discovery（L0 規則 + L1 Ollama） | E1 + AI-E review | 3.0 | 並行 |
| **R3-T5** Analyst L3 hypothesis_generation + dispatch_experiment | E1 + AI-E review | 3.0 | 串行 R3-T4 |
| **R3-T6** Decision Lease / ExecutionPlan / fills propagation 接線 | E1 + E2 governance review | 3.0 | 串行 R3-T2 |
| **R3-T7** attribution writer 重寫（base on hypothesis_id）| E1 + MIT review | 4.0 | 串行 R3-T6 |
| **R3-T8** GUI Hypothesis Lab tab + verdict POST endpoint | E1a + A3 review | 3.0 | 並行 |
| **R3-T9** Integration test（propose → register → experiment → gate → verdict 全鏈路）| E4 | 3.0 | 串行 R3-T1..T8 |
| **R3-T10** healthcheck `[新-hypothesis_pipeline_health]` | E1 | 1.0 | 並行 |
| **總計** | | **~26 person-day（3-4 sprint）** | |

### 3.1 與 W-AUDIT-4b 的串行關係（Push Back 4 採納）

**強制串行**：W-AUDIT-4b（label_close_tag NULL writer fix + 6 表 INSERT path） → R-3 IMPL

| Phase | 期 |
|---|---|
| W-AUDIT-4b 完成 | Sprint N+0 |
| R3-T1/T2/T3 開（migration + state machine） | Sprint N+0 後段 ~ N+1 |
| R3-T4/T5 開（Analyst L2-L3） | Sprint N+1 |
| R3-T6/T7 接線（lease/plan/fills/attribution） | Sprint N+1 ~ N+2 |
| R3-T8/T9/T10 收尾 | Sprint N+2 |

---

## §4 Acceptance Criteria

### 4.1 R3-T1 V### migration learning.hypotheses
- Guard A/B/C 完整
- 兩次 idempotent apply 驗 PASS
- Linux PG dry-run mandatory
- Retention 365d 已驗
- MIT review sign-off

### 4.2 R3-T2 alter migration
- Decision Lease / ExecutionPlan / fills 三表都加 `originating_hypothesis_id` 欄位
- foreign key constraint 對 `learning.hypotheses` 完整
- index 完整（hot-path query）
- 既有 row migration: NULL allow（既有 row 無 hypothesis_id，本 wave 不 backfill）

### 4.3 R3-T3 hypothesis_pipeline.py
- 7-state state machine 完整 IMPL
- atomic transition（advisory xact lock + UPDATE state + INSERT history）
- pytest coverage ≥ 90%
- 所有 7 種 transition path 各 ≥ 1 test

### 4.4 R3-T4 Analyst L2
- L0 規則：`learning.attribution_chain` 真實 read（W-AUDIT-4b 後 attribution_chain_ok > 50%）
- L1 Ollama：13B 模型 prompt 設計合 H3 ModelRouter 政策
- pattern_discovery 24h 至少 emit 1 PatternInsight
- AI-E review sign-off

### 4.5 R3-T5 Analyst L3
- hypothesis_generation 從 PatternInsight 生 valid AlphaHypothesis schema
- dispatch_experiment 設置 paper engine 跑 N=100 trial
- AI-E review sign-off

### 4.6 R3-T6 Decision Lease / ExecutionPlan / fills propagation
- IntentProcessor inject `originating_hypothesis_id` 到 Decision Lease（grep 確認 path）
- ExecutionPlan writer propagate hypothesis_id（grep 確認）
- fill writer 從 ExecutionPlan 拿 hypothesis_id 寫 fills（grep 確認）
- E2 governance review sign-off

### 4.7 R3-T7 attribution writer
- attribution_chain INSERT 帶 hypothesis_id（NULL 仍 backward compat）
- realized_sharpe / realized_dsr / realized_pbo 從 fills 反向 update `learning.hypotheses`
- MIT review sign-off
- 7d demo run attribution_chain_ok > 50%（W-AUDIT-4b 修復後 baseline）

### 4.8 R3-T8 GUI Hypothesis Lab
- `/console#hypothesis_lab` 路由生效
- HIGH-impact verdict POST endpoint（per EX-05 spec）
- Read-only filter + verdict approve action
- A3 a11y review PASS

### 4.9 R3-T9 Integration test
- E2E：Strategist propose → Analyst L3 dispatch → paper experiment → evidence gate → verdict 全鏈路 PASS
- 7d shadow run 至少 1 個 hypothesis 從 DRAFT → PROMOTED 或 REJECTED 完整 lifecycle
- E4 sign-off

### 4.10 R3-T10 healthcheck
- `[新-hypothesis_pipeline_health]` 加入 `helper_scripts/db/passive_wait_healthcheck.py`
- 24h ≥ 1 state transition
- 24h 0 orphan transition row
- PASS / WARN / FAIL 三檔對齊

### 4.11 Wave 整體 acceptance
- ADR-0021 R-3 IMPL DONE → ADR References 補
- attribution_chain_ok 24h ≥ 50%（修復前 0.5% denominator artifact）
- TODO.md 加 W-AUDIT-8c 完成 status

---

## §5 依賴關係 + Risk

### 5.1 上下游依賴

| 依賴 | 性質 | 處理 |
|---|---|---|
| W-AUDIT-4b label_close_tag fix + 6 表 INSERT | **Hard** prerequisite | 必先 land；attribution_chain 修復後才有 evidence 餵 |
| W-AUDIT-8b R-2 Strategist propose | **Soft** | propose 端可由 Analyst 自身觸發；Strategist propose 是補充路徑 |
| W-AUDIT-8a Phase B Tier 2 panel | **Soft** | L2 pattern discovery 需 surface.funding_curve 真實 data |
| ADR-0020 Layer 2 manual | **Hard invariant** | Analyst L2-L3 全在 L0+L1 跑 |
| EX-05 Hypothesis 既有 spec | **Spec compliance** | POST `/learning/hypothesis/{id}/verdict` 端對齊既有 spec |

### 5.2 Risk + Fallback

| Risk | 機率 | Mitigation | Fallback |
|---|---|---|---|
| W-AUDIT-4b 卡住 → R-3 不能開 | **高** | Push Back 4 採納，串行 prerequisite | R-3 spec land 先，IMPL 等 4b PASS |
| Analyst L1 Ollama 13B 模型對「找模式」不夠 | 中 | 先 prompt engineering + L0 規則 floor | 升級 L1 模型 14B-30B（費 RAM 不費 cloud token） |
| Hypothesis state machine race（multi Analyst worker）| 中 | advisory xact lock + UPDATE...RETURNING | E2 review 必驗 |
| Decision Lease alter migration 影響既有 lease 功能 | 中 | NULL allow + 既有 row 不 backfill | rollback alter migration（remove column） |
| attribution writer 重寫破壞 MLDE 既有訓練 | 高 | 漸進切換：原 writer 保留作 fallback；新 writer 帶 `feature_flag` | feature flag 切回原 writer |
| GUI HIGH-impact verdict 路由濫用 | 低 | operator role auth check + audit log | 路由限 admin role |

### 5.3 與 W-AUDIT-3b/9 衝突點

| 衝突 | 性質 | Mitigation |
|---|---|---|
| W-AUDIT-3b ExecutorAgent runtime smoke | **無衝突** | R-3 在 Analyst + DB schema，不碰 ExecutorAgent |
| W-AUDIT-9 T6 LeaseScope::CanaryStagePromotion | **無衝突** | R-3 加 hypothesis_id 欄位，不影響 lease scope |
| W-AUDIT-4b INSERT path | **必先** | Push Back 4 採納，串行 prerequisite |
| W-AUDIT-6 bb_reversion + portfolio_var | **正交** | R-3 不重寫策略 |
| W-AUDIT-8b R-2 Strategist propose | **協同** | R-2 emit AlphaHypothesis → R-3 register；R-3 land 前 R-2 emit 只到 audit row + MessageBus |

---

## §6 E2 Review Checklist

**E2 review 必查 6 點**：
1. **State machine atomicity**：grep `ROLLBACK` + `COMMIT` + advisory xact lock；7 種 transition 路徑全 atomic
2. **Decision Lease/ExecutionPlan/fills 三表 hypothesis_id propagation**：grep IntentProcessor / ExecutionPlan writer / fill writer 三處全 propagate
3. **EX-05 既有 spec compliance**：POST `/learning/hypothesis/{id}/verdict` 端 schema 對齊既有 spec（`docs/decisions/EX-05_..._V2.md`）
4. **HIGH-impact verdict operator role check**：grep operator role auth + audit log 雙保險
5. **Layer 2 invariant**：grep Analyst L2-L3 IMPL 路徑沒 escalate Layer 2（ADR-0020）
6. **Forward compatibility**：既有 row hypothesis_id NULL 仍可 query；attribution writer NULL backward compat

**E2 推回情況**：
- 任何 state transition 非 atomic → 推回
- HIGH-impact verdict 缺 operator role check → 推回
- Layer 2 escalation 出現 → 推回

---

## §7 E4 Regression Checklist

**E4 必跑 5 個 regression**：
1. **State machine 7 路徑全 PASS**：DRAFT→REGISTERED / REGISTERED→EXPERIMENTING / EXPERIMENTING→EVIDENCE_GATE / EVIDENCE_GATE→PROMOTED / EVIDENCE_GATE→REJECTED / DRAFT→EXPIRED / EXPERIMENTING→EXPIRED 各 1 happy path
2. **既有 Decision Lease 行為不變**：本 wave 加 hypothesis_id NULL allow；既有 lease test suite 100% PASS
3. **既有 ExecutionPlan / fills 行為不變**：同上
4. **attribution writer migration**：原 writer + 新 writer 並行跑 24h，新 writer attribution_chain_ok ≥ 原 writer + 30%
5. **7d shadow E2E**：Strategist propose → Analyst register → experiment → gate → verdict 至少 1 完整 cycle；no panic / no orphan row

---

## §8 落地 Side Effect

### 8.1 CLAUDE.md §三 加 W-AUDIT-8c row + healthcheck `[新-hypothesis_pipeline_health]` row

### 8.2 CLAUDE.md §五 15-tab 擴展
從 14 tab（含 alpha_sources）升 15 tab，加 `hypothesis_lab`：
```
"system", "replay", ..., "alpha_sources", "hypothesis_lab"  ← 新加
```

### 8.3 ADR-0021 status update
R-3 IMPL DONE 補：
```
- W-AUDIT-8c R-3 IMPL spec: docs/execution_plan/2026-05-09--w_audit_8c_hypothesis_pipeline_spec.md
- W-AUDIT-8c R-3 IMPL completion commit: <hash>
- W-AUDIT-4 攜入 R-3 完成（ADR Consequences §「Supersedes / impacts」最後一行 close）
```

### 8.4 EX-05 spec compliance
EX-05 Stage 3 Hypothesis + Stage 5 Verdict 既有 spec 完整 IMPL；POST endpoint 對齊。

### 8.5 PA memory 更新
- 教訓：Push Back 3 + Push Back 4 採納，避免「Layer 2 dormant by design = Analyst 進化 loop 不需要 IMPL」誤推；Analyst L2-L3 在 L0+L1 跑是合 ADR-0020 invariant 解
- 經驗：Hypothesis as first-class object 比「Analyst 內部欄位」治理摩擦低 ~10x

---

## §9 PM 接收後動作

1. 確認 W-AUDIT-4b 完成時點（gate R-3 開始）
2. R3-T1/T2 land 後派 R3-T3/T4 並行
3. R3-T5 串行於 R3-T4；R3-T6/T7 串行於 R3-T2
4. R3-T8/T9/T10 收尾
5. PASS 後進 W-AUDIT-8d R-4 Per-alpha-source Live Promotion Gate

---

`PA DESIGN DONE: report path: srv/docs/execution_plan/2026-05-09--w_audit_8c_hypothesis_pipeline_spec.md`
