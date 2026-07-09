# W-AUDIT-8d — Per-Alpha-Source Live Promotion Gate（R-4 IMPL Spec）

**Wave 名稱**：W-AUDIT-8d "Per-Alpha-Source Live Promotion Gate"
**對應 ARCH-04 amendment**：R-4（ADR-0021 Accepted 2026-05-09）
**起草者**：PA（Project Architect）
**日期**：2026-05-09
**對齊上游**：
- `docs/adr/0021-alpha-source-architecture-upgrade.md`（Accepted 2026-05-09）R-4
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` Layer 3.3 + Layer 4 R-4
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md` §6.2 push back 5（Layer 2 解耦不衝突）
- `docs/governance_dev/EX-04.md` Reconciler（既有對賬層）
- ADR-0020 Layer 2 manual + supervisor-only（必維持 invariant）
- LG-1..LG-5 baseline（H0 production caller / pricing binding / supervised-live state machine 仍須完成）
**讀者**：Operator / PM / E1 / E2 / E4 / Guardian Agent author / GovernanceHub team
**前置（強）**：W-AUDIT-8a Phase D 完成、W-AUDIT-8b R-2 完成、W-AUDIT-8c R-3 完成、LG-1..LG-5 baseline IMPL 全 PASS（H0 production caller / pricing binding / supervised-live SM）
**並行**：W-AUDIT-3b/9（不衝突）；W-AUDIT-9 graduated canary 是 deploy substrate
**生效範圍**：Python `app/governance/live_budget_manager.py` 新模組 + `app/governance/per_alpha_source_promotion.py` + Guardian Agent 加 per-alpha-source veto path + GovernanceHub `acquire_alpha_source_budget()` API + V### migration `governance.live_budgets`；**不**改 Rust execution authority、**不** reverse `live_reserved` binary

---

## §0 命名 + 編號 alignment

| 來源 | R-4 對應 wave |
|---|---|
| ADR-0021 | R-4 |
| PA fix plan v2 §5 | W-AUDIT-8g |
| TODO.md v18 | W-AUDIT-8e |
| **本 spec** | **W-AUDIT-8d** |

---

## §1 Wave 範圍 + Goal

### 1.1 North Star

把 Live Promotion 從 **「整 system `live_reserved (yes/no)` binary」** 升級為 **「per-alpha-source live budget allocation」**：

- 新增 `LiveBudget(alpha_source_id, capital_cap_usd, max_concurrent_positions, max_drawdown_pct)` 對象
- GovernanceHub 加 `acquire_alpha_source_budget()` API（per-alpha-source 級授權）
- Guardian Agent 加 per-alpha-source veto path
- 每筆 Decision Lease 必對應一個 active LiveBudget（否則 fail-closed）
- **不** reverse 既有 `live_reserved` binary：本 wave 在「`live_reserved=true` 範圍內」加 per-alpha-source 細粒度

**ADR-0021 §「Supersedes / impacts」對應**：
- LG-X-02..05 system-wide promotion design 部分被 R-4 superseded
- LG-X 1-5 baseline IMPL（H0 production caller / pricing binding / supervised-live state machine）**仍須完成**作 substrate
- **本 wave 是 in-scope-of-Live 細粒度，不擴展 live boundary**

### 1.2 Wave 範圍邊界

**本 wave 含**：
1. V### migration `governance.live_budgets`（per-alpha-source budget 表 + history）
2. Python `app/governance/live_budget_manager.py`（CRUD + allocation + drawdown tracking）
3. Python `app/governance/per_alpha_source_promotion.py`（gate 評估 + Guardian veto integration）
4. GovernanceHub 加 `acquire_alpha_source_budget()` API（與既有 `acquire_lease()` 同層級）
5. Guardian Agent 加 per-alpha-source veto check（per_alpha_source_promotion.gate_check 結果）
6. IntentProcessor inject alpha_source_id 到 Decision Lease（從 ExecutionPlan 反查）
7. fill writer 寫入 LiveBudget realized PnL → drawdown tracking
8. healthcheck `[新-live_budget_allocation_health]`（每個 active alpha_source_id 的 budget 使用率 / drawdown 觀測）
9. Operator GUI 加「Live Budget Inventory」view（read-only + manual top-up route per alpha_source）

**本 wave 不含**（明確邊界）：
- `live_reserved` binary 移除（本 wave 在 binary=true 內加細粒度，不破 LG-X baseline）
- Layer 2 cloud reasoning 解封（ADR-0020 維持）
- Mainnet 流量自動 promotion（仍需 operator 顯式 sign-off）
- LG-1..LG-5 baseline IMPL（必先完成作 substrate；本 wave **不** include）
- AlphaSourceRegistry CRUD GUI write（W-AUDIT-8b 範圍）

### 1.3 為什麼這是 Tier-2 leverage（修正版）

**現況**（CLAUDE.md §四 + LG-X spec）：
- `live_reserved (yes/no)` binary → 整 system 一刀
- 即使 `funding skew spread` alpha source 有 graduate evidence，`TA strategy` 樣本不足無法 graduate → 整 system 卡 demo
- LG-X baseline 1-5（H0 / pricing / supervised SM）+ X-2 evidence + X-3 budget + X-4 monitor + X-5 self-aware 都 frame 為「整 system」

**新設計**：
- `funding skew spread` 樣本量足、`TA` 樣本量不足 → `funding skew spread` 先 graduate live with 5% capital budget，TA 留 demo
- 不需 「整 system 放權」 blocking on 5 個 TA 策略
- 每個 alpha source 有自己的 promotion clock，併發推進

**為什麼是 Tier-2 而非 Tier-1**：
- 必先 W-AUDIT-8a/8b/8c 全 PASS（前置成熟度高）
- 必先 LG-1..LG-5 baseline IMPL（substrate 成熟度高）
- W-AUDIT-9 graduated canary 已是 deploy substrate（5-stage canary 可 cover 多 alpha source 並行）
- 本 wave 是 **in-scope-of-supervised-live 細粒度**，不前置到 supervised live 規劃帶（6/15-7/15）

---

## §2 接口設計

### 2.1 `governance.live_budgets` table schema（V### migration）

```sql
CREATE TABLE IF NOT EXISTS governance.live_budgets (
    budget_id BIGSERIAL PRIMARY KEY,
    alpha_source_id VARCHAR(64) NOT NULL,         -- 對應 AlphaSourceTag.lowercase
    -- Allocation
    capital_cap_usd DECIMAL(15,2) NOT NULL,       -- 該 alpha source 的 capital ceiling（USD notional）
    max_concurrent_positions INT NOT NULL,
    max_drawdown_pct DECIMAL(6,3) NOT NULL,       -- 5.000 = 5% drawdown
    -- 治理約束
    requires_operator_approval BOOLEAN NOT NULL DEFAULT TRUE,  -- HIGH-impact: TRUE
    operator_approved_by VARCHAR(64),
    operator_approved_at_ms BIGINT,
    -- 狀態
    state VARCHAR(32) NOT NULL CHECK (state IN ('PENDING','ACTIVE','SUSPENDED','EXHAUSTED','REVOKED')),
    state_updated_ms BIGINT NOT NULL,
    -- Realized 觀測
    realized_pnl_usd DECIMAL(15,2) NOT NULL DEFAULT 0,
    realized_drawdown_pct DECIMAL(6,3) NOT NULL DEFAULT 0,
    realized_n_fills INT NOT NULL DEFAULT 0,
    last_fill_ms BIGINT,
    -- 時間戳
    created_ms BIGINT NOT NULL,
    expires_ms BIGINT,                            -- budget TTL（per alpha source）
    -- Audit
    audit_trace_id VARCHAR(128),                  -- GovernanceHub trace
    parent_lease_id BIGINT REFERENCES governance.decision_leases(lease_id),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_live_budgets_alpha_state ON governance.live_budgets(alpha_source_id, state);
CREATE INDEX IF NOT EXISTS idx_live_budgets_expires ON governance.live_budgets(expires_ms) WHERE state = 'ACTIVE';

-- History table（每 state transition + drawdown update 1 row）
CREATE TABLE IF NOT EXISTS governance.live_budgets_history (
    history_id BIGSERIAL PRIMARY KEY,
    budget_id BIGINT NOT NULL REFERENCES governance.live_budgets(budget_id),
    transition_at_ms BIGINT NOT NULL,
    from_state VARCHAR(32) NOT NULL,
    to_state VARCHAR(32) NOT NULL,
    realized_drawdown_pct DECIMAL(6,3),
    notes TEXT
);

-- Retention: 365 day（live budget audit 必須長期保留）
```

### 2.2 `LiveBudget` state machine

```
PENDING ──operator approve──→ ACTIVE
        │
        └── timeout 7d ──→ EXPIRED

ACTIVE ──realized_drawdown_pct >= max_drawdown_pct──→ SUSPENDED
       │
       └── realized_pnl_usd 盡 capital_cap_usd ──→ EXHAUSTED
       │
       └── operator manual revoke ──→ REVOKED
       │
       └── now > expires_ms ──→ EXPIRED

SUSPENDED ──operator manual reactivate──→ ACTIVE
          │
          └── 24h auto-revoke ──→ REVOKED

EXHAUSTED → terminal
REVOKED   → terminal
EXPIRED   → terminal
```

**強制機制**：
- **fail-closed default**：每筆 Decision Lease 必對應一個 ACTIVE LiveBudget；查不到 → 拒絕 lease
- HIGH-impact LiveBudget 必須 `operator_approved_by IS NOT NULL`（DOC-08 §12 §6 安全不變量延伸）
- Drawdown tracker：每 fill 後 update realized_drawdown_pct；達 cap → 自動 SUSPENDED
- Capital cap：每 fill 後 update realized_pnl_usd；達 capital_cap_usd → 自動 EXHAUSTED

### 2.3 `LiveBudgetManager` Python class

```python
# app/governance/live_budget_manager.py
class LiveBudgetState(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXHAUSTED = "EXHAUSTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"

class LiveBudgetManager:
    def request_budget(
        self,
        alpha_source_id: str,
        capital_cap_usd: float,
        max_concurrent_positions: int,
        max_drawdown_pct: float,
        ttl_ms: int,
        requested_by: str,
    ) -> int:
        """
        新建 PENDING LiveBudget；返回 budget_id
        - HIGH-impact (capital_cap_usd > $1000) requires_operator_approval=TRUE
        - LOW-impact (capital_cap_usd <= $100) can auto-approve via Guardian
        """

    def operator_approve(self, budget_id: int, approved_by: str) -> bool:
        """PENDING → ACTIVE（operator role auth required）"""

    def find_active_budget(self, alpha_source_id: str) -> Optional[LiveBudget]:
        """查詢 alpha source 當前 ACTIVE budget；查不到 → None（caller fail-closed）"""

    def update_realized(self, budget_id: int, fill: Fill) -> None:
        """每 fill 後 update realized_pnl_usd + realized_drawdown_pct + realized_n_fills"""

    def check_state_transition(self, budget_id: int) -> LiveBudgetState:
        """
        檢查 transition 條件：
        - realized_drawdown_pct >= max_drawdown_pct → SUSPENDED
        - realized_pnl_usd >= capital_cap_usd → EXHAUSTED
        - now > expires_ms → EXPIRED
        """

    def revoke(self, budget_id: int, reason: str) -> bool:
        """ACTIVE/SUSPENDED → REVOKED"""
```

### 2.4 GovernanceHub `acquire_alpha_source_budget()` API

```python
# app/governance/governance_hub.py（既有，加新方法）
class GovernanceHub:
    async def acquire_alpha_source_budget(
        self,
        intent: TradeIntent,
        alpha_source_id: str,
    ) -> Optional[LiveBudget]:
        """
        per-alpha-source budget 授權：
        1. find_active_budget(alpha_source_id) → 查不到 → return None (fail-closed)
        2. check budget cap: realized_pnl_usd + intent.size_usd <= capital_cap_usd
        3. check max_concurrent_positions
        4. Guardian per-alpha-source veto check
        5. 通過 → reserve budget slice → return LiveBudget snapshot
        """
```

**整合既有 `acquire_lease()` 流程**：
```
1. IntentProcessor 收到 intent
2. 從 intent.originating_hypothesis_id → query learning.hypotheses → 拿 target_alpha_sources
3. 對每個 target alpha_source_id：
   acquire_alpha_source_budget(intent, alpha_source_id)
   - 任一 None → fail-closed reject
   - 全 ACTIVE budget → continue
4. acquire_lease() 既有流程
5. lease 帶 (originating_hypothesis_id, alpha_source_ids, budget_ids) tuple
6. fill 時 update_realized() per alpha_source budget
```

### 2.5 Guardian per-alpha-source veto path

```python
# app/agent_runtime/guardian_agent.py（既有，加 per-alpha-source 路徑）
class GuardianAgent(BaseAgent):
    async def per_alpha_source_veto(
        self,
        intent: TradeIntent,
        alpha_source_id: str,
        budget: LiveBudget,
    ) -> VetoVerdict:
        """
        Guardian per-alpha-source 否決邏輯：
        1. 系統級 P0/P1 風控仍適用（既有）
        2. 加 per-alpha-source 收緊：
           - 該 alpha source 24h drawdown_pct ≥ max_drawdown_pct * 0.8 → veto
           - 該 alpha source 24h consecutive losses ≥ 5 → veto
           - 該 alpha source 24h sharpe < -1.5 → veto
        3. veto 結果同時寫 governance.live_budgets_history
        """
```

### 2.6 GUI Live Budget Inventory tab（A3 review）

新增 GUI tab `live_budgets`（15→16 tab 累加）：
- 每 active alpha source 一行：tag / state / capital_cap_usd / realized_pnl_usd / realized_drawdown_pct / realized_n_fills
- HIGH-impact PENDING budget operator approve action
- A3 review：a11y + focus management

---

## §3 Deliverable（Sub-task 拆分）

| Sub-task | Owner | Person-day | 並行度 |
|---|---|---:|---|
| **R4-T1** V### migration `governance.live_budgets` + history table | E1 + MIT review | 2.0 | 並行 |
| **R4-T2** Python `live_budget_manager.py` 6-state state machine + CRUD | E1 | 3.0 | 並行（mock DB） |
| **R4-T3** GovernanceHub `acquire_alpha_source_budget()` API | E1 + Guardian Agent author + E2 | 3.0 | 串行 R4-T2 |
| **R4-T4** Guardian per-alpha-source veto path | E1 + QC + E2 | 2.0 | 串行 R4-T3 |
| **R4-T5** IntentProcessor inject alpha_source_id 到 Decision Lease | E1 + E2 governance review | 2.0 | 串行 R4-T3 |
| **R4-T6** fill writer update_realized()（drawdown / pnl tracking）| E1 + MIT | 2.0 | 串行 R4-T5 |
| **R4-T7** healthcheck `[新-live_budget_allocation_health]` | E1 | 1.5 | 並行 |
| **R4-T8** GUI Live Budget Inventory tab + operator approve POST | E1a + A3 review | 3.0 | 並行 |
| **R4-T9** Integration test（Strategist propose → Hypothesis register → Budget request → operator approve → lease acquire → fill → drawdown trigger SUSPENDED）| E4 | 4.0 | 串行 R4-T1..T8 |
| **R4-T10** ADR-0021 References + LG-X-02..05 SPECIFICATION_REGISTER 標 superseded | PA + TW | 1.0 | 並行 |
| **總計** | | **~24 person-day（3 sprint）** | |

### 3.1 與 LG-1..LG-5 baseline 的串行關係

**強制串行**：LG-1 H0 production caller + LG-2 pricing binding + LG-3 supervised-live state machine + LG-4 monitor + LG-5 self-aware → R-4 IMPL

| Phase | 期 |
|---|---|
| LG-1..LG-5 baseline 全 PASS | Sprint N+0 |
| W-AUDIT-8a Phase D 完 + W-AUDIT-8b R-2 land + W-AUDIT-8c R-3 land | Sprint N+0 ~ N+1 |
| R4-T1/T2 開（migration + state machine） | Sprint N+1 |
| R4-T3/T4/T5 接線（GovernanceHub + Guardian + IntentProcessor） | Sprint N+1 ~ N+2 |
| R4-T6/T7/T8 收尾 | Sprint N+2 |
| R4-T9/T10 integration + ADR | Sprint N+2 ~ N+3 |

---

## §4 Acceptance Criteria

### 4.1 R4-T1 V### migration governance.live_budgets
- Guard A/B/C 完整
- 兩次 idempotent apply 驗 PASS
- Linux PG dry-run mandatory
- foreign key 對 `governance.decision_leases` 完整
- Retention 365d 已驗
- MIT review sign-off

### 4.2 R4-T2 live_budget_manager.py
- 6-state state machine 完整 IMPL
- atomic transition（advisory xact lock + INSERT history + UPDATE current）
- pytest coverage ≥ 90%

### 4.3 R4-T3 acquire_alpha_source_budget()
- fail-closed default：alpha_source_id 無 ACTIVE budget → return None
- capital cap check 嚴格（realized + intent.size_usd <= cap）
- E2 governance review sign-off
- 不繞過既有 `acquire_lease()` 流程

### 4.4 R4-T4 Guardian per-alpha-source veto
- 3 條 veto rule 完整 IMPL（drawdown 80% / consecutive losses 5 / 24h sharpe < -1.5）
- veto 結果寫 governance.live_budgets_history
- QC review sign-off

### 4.5 R4-T5 IntentProcessor inject
- intent.originating_hypothesis_id 反查 target_alpha_sources
- per alpha_source 並行 acquire_alpha_source_budget()
- 任一失敗 → fail-closed reject intent

### 4.6 R4-T6 fill writer update_realized()
- 每 fill 後 update realized_pnl_usd + realized_drawdown_pct + realized_n_fills
- atomic transaction（fill insert + budget update 在 one tx）
- check_state_transition 在 update 後立即跑

### 4.7 R4-T7 healthcheck
- `[新-live_budget_allocation_health]` 加入
- 每個 ACTIVE budget 觀察 realized_drawdown_pct < max_drawdown_pct
- alpha_source_id orphan budget 偵測（state=ACTIVE but expires_ms < now）
- PASS / WARN / FAIL 對齊

### 4.8 R4-T8 GUI Live Budget Inventory
- `/console#live_budgets` 路由
- HIGH-impact PENDING approve POST endpoint（operator role check）
- Read-only view + approve action
- A3 a11y review PASS

### 4.9 R4-T9 Integration test
- E2E：propose → hypothesis register → budget request → operator approve → lease acquire → fill → drawdown trigger SUSPENDED 全鏈路 PASS
- 7d shadow run 至少 1 完整 lifecycle

### 4.10 R4-T10 ADR + SPECIFICATION_REGISTER
- ADR-0021 R-4 IMPL DONE 補 References
- SPECIFICATION_REGISTER LG-X-02..05 entries 標「Superseded by ARCH-04 R-4 (Accepted)」（per ADR-0021 Consequences §「Supersedes / impacts」）

### 4.11 Wave 整體 acceptance
- 既有 `live_reserved` binary 仍在（W-AUDIT-8d 不 reverse）
- 至少 1 alpha source 真實取得 LiveBudget ACTIVE state（demo runtime 7d 觀察）
- TODO.md 加 W-AUDIT-8d 完成 status
- LG-1..LG-5 baseline 維持 PASS

---

## §5 依賴關係 + Risk

### 5.1 上下游依賴

| 依賴 | 性質 | 處理 |
|---|---|---|
| LG-1 H0 production caller | **Hard** | substrate；本 wave 不 IMPL |
| LG-2 pricing binding | **Hard** | substrate |
| LG-3 supervised-live state machine | **Hard** | substrate |
| LG-4 monitor | **Hard** | substrate |
| LG-5 self-aware | **Hard** | substrate |
| W-AUDIT-8a Phase D | **Hard** | AlphaSourceTag enum + 5 策略 declare 全完 |
| W-AUDIT-8b R-2 | **Hard** | AlphaSourceRegistry exists |
| W-AUDIT-8c R-3 | **Hard** | originating_hypothesis_id 全鏈路 propagate |
| W-AUDIT-9 graduated canary | **Soft** | per-alpha-source budget 可走 Stage 2/3 canary |
| ADR-0020 Layer 2 manual | **Hard invariant** | 不影響 R-4 |
| `live_reserved` binary | **Preserved** | 本 wave 在 binary=true 內加細粒度，不 reverse |

### 5.2 Risk + Fallback

| Risk | 機率 | Mitigation | Fallback |
|---|---|---|---|
| LG-1..LG-5 baseline 卡 → R-4 不能開 | **高** | LG-X 仍是 supervised live 真實 blocker；R-4 必後 | R-4 spec land 先，IMPL 等 LG PASS |
| `acquire_alpha_source_budget()` 與既有 `acquire_lease()` 流程衝突 | 中 | per-alpha-source 是「lease 內細粒度」不替代 lease | E2 review 必驗 |
| Guardian per-alpha-source veto 與系統級 P0/P1 衝突 | 中 | 系統級先 check，per-alpha-source 後 check | 任一 veto = reject |
| Operator approve UI 路由濫用 | 低 | operator role auth + audit log | route 限 admin role |
| HIGH-impact threshold（$1000）設定爭議 | 中 | 配置化（4 environment-specific risk_config TOML 加 entry） | 默認 conservative |
| `live_reserved` binary 被誤解為「可 R-4 後 remove」| 高 | 本 spec §1.3 明確「不 reverse 既有 binary」+ §「Supersedes / impacts」明確 LG-X baseline 仍須 | E2 review push back 任何 reverse 嘗試 |

### 5.3 與 W-AUDIT-3b/9 衝突點

| 衝突 | 性質 | Mitigation |
|---|---|---|
| W-AUDIT-3b ExecutorAgent runtime smoke | **無衝突** | R-4 在 Governance 端，不碰 ExecutorAgent |
| W-AUDIT-9 T6 LeaseScope::CanaryStagePromotion | **協同** | per-alpha-source budget 可 leverage 既有 stage promotion lease |
| W-AUDIT-9 graduated canary 5-stage | **協同** | 每個 alpha source 走 Stage 2/3 canary，per-budget 細粒度 |
| W-AUDIT-4b INSERT path | **正交** | R-4 不依賴 attribution writer |
| W-AUDIT-6 bb_reversion + portfolio_var | **正交** | R-4 不重寫策略 |

---

## §6 E2 Review Checklist

**E2 review 必查 7 點**：
1. **fail-closed default**：grep `acquire_alpha_source_budget` 各 fail path 都 return None；caller 收 None 必 reject
2. **HIGH-impact operator approval**：grep `operator_approved_by IS NOT NULL` 在 PENDING → ACTIVE transition 必查
3. **LG-X baseline 不被破壞**：grep `live_reserved` 仍存在 + binary check 仍 active；R-4 不 reverse
4. **既有 `acquire_lease()` 流程不變**：本 wave 加 per-alpha-source 在 lease 之前，不繞過
5. **Drawdown / capital cap atomic**：grep fill insert + update_realized 在 one transaction
6. **GuardianAgent 系統級 P0/P1 仍 first**：per-alpha-source veto 在系統級之後
7. **DOC-08 §12 安全不變量**：9 條全部仍成立

**E2 推回情況**：
- 任一 fail-closed path 被繞 → 推回
- HIGH-impact 自動 approve → 推回
- `live_reserved` 被 reverse → 推回（嚴重 BLOCKER）
- 系統級 P0/P1 被 per-alpha-source 取代 → 推回

---

## §7 E4 Regression Checklist

**E4 必跑 6 個 regression**：
1. **既有 Decision Lease 流程不變**：本 wave 加 per-alpha-source 在 lease 前；既有 lease test suite 100% PASS
2. **fail-closed default**：alpha_source_id 無 ACTIVE budget → 100% reject intent（10 種 random scenario 驗）
3. **6-state state machine**：PENDING/ACTIVE/SUSPENDED/EXHAUSTED/REVOKED/EXPIRED 6 狀態各 ≥ 1 happy path
4. **Drawdown auto-suspend**：drawdown 達 max_drawdown_pct 自動 SUSPENDED（5 random scenario 驗）
5. **Capital cap auto-exhaust**：realized_pnl_usd 達 capital_cap_usd 自動 EXHAUSTED
6. **7d shadow E2E**：1 alpha source 真實取得 ACTIVE budget 並產 1 fill

---

## §8 落地 Side Effect

### 8.1 CLAUDE.md §三 加 W-AUDIT-8d row

### 8.2 CLAUDE.md §五 16-tab 擴展
從 15 tab 升 16 tab，加 `live_budgets`：
```
"system", ..., "alpha_sources", "hypothesis_lab", "live_budgets"  ← 新加
```

### 8.3 CLAUDE.md §四 硬邊界補
§四 `# ── Live_Ready 真實狀態 ──` block 補：
```
# per-alpha-source live budget gate (W-AUDIT-8d / R-4):
#   path: app/governance/live_budget_manager.py
#   每筆 Decision Lease 必對應 ACTIVE LiveBudget
#   不 reverse 既有 live_reserved binary（in-scope-of-Live 細粒度）
```

### 8.4 ADR-0021 status update
R-4 IMPL DONE 補 References + Consequences §「Supersedes / impacts」LG-X-02..05 標 superseded。

### 8.5 SPECIFICATION_REGISTER
LG-X-02..05 entries 加 annotation「Superseded by ARCH-04 R-4 (Accepted 2026-05-09，IMPL completed 2026-XX-XX)」。

### 8.6 PA memory 更新
- 教訓：R-4 必先 LG-X baseline，不替代 substrate
- 經驗：per-alpha-source budget 是「在 binary=true 內」細粒度，不是「替代 binary」

---

## §9 PM 接收後動作

1. 確認 LG-1..LG-5 baseline 全 PASS（gate R-4 開始）
2. 確認 W-AUDIT-8a Phase D + W-AUDIT-8b R-2 + W-AUDIT-8c R-3 全 land
3. R4-T1/T2 並行（migration + state machine）
4. R4-T3/T4/T5 串行於 R4-T2
5. R4-T6/T7/T8 收尾
6. R4-T9 integration + R4-T10 ADR
7. PASS 後進 W-AUDIT-8e R-5 Spec-as-Code

---

`PA DESIGN DONE: report path: srv/docs/execution_plan/2026-05-09--w_audit_8d_per_alpha_source_promotion_gate_spec.md`
