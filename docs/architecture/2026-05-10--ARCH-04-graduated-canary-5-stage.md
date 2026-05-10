# ARCH-04: Graduated Canary 5-Stage Architecture

Date: 2026-05-10
Status: **Accepted (architecture spec)** — IMPL via W-AUDIT-9 Sprint N+0
Authority Source: AMD-2026-05-09-03 (graduated canary default for alpha-bearing pathways)
Cross-references:
- AMD-2026-05-09-01 (SM-05 polling design)
- AMD-2026-05-09-02 (operator decision audit closure §2 Option A)
- AMD-2026-05-02-01 §5.4.1 (W-C lease router evidence flag)
- ADR-0008 (Decision Lease state machine)
- ADR-0009 (Hot config ArcSwap no restart)
- ADR-0017 (Scanner is evidence not authority)
- ADR-0020 (Layer2 manual + supervisor only)
- ADR-0021 (Alpha Source Architecture Upgrade)
- ADR-0022 (Strategist 30%→50% wide adjustment skill)
- DOC-08 §12 (9 條安全不變量)
- CLAUDE.md §四 (硬邊界) / §二 (16 根原則)

---

## 1. Architecture Overview

Graduated Canary 是 alpha-bearing pathway 的 5-stage 狀態機，把
`executor.shadow_mode` 的 binary `bool` 升級為 `canary_stage: u8 (0..=4)` +
cohort scope 描述。每 stage 都是條件 fail-closed（自動升級條件 + auto-rollback
metric 雙鎖）。

### 5-stage 狀態機

```
Stage 0 (shadow only)  ── operator manual approve ──▶  Stage 1 (paper × 7d × 1S × 1Sym)
                                                              │
                                            auto-promote:    │ entry_fills ≥ 10
                                                              │ AND boundary_violation == 0
                                                              ▼
                                                        Stage 2 (demo × 14d × 1S × 1Sym)
                                                              │
                                            auto-promote:    │ gross_pnl > -5 USDT
                                                              │ AND DSR > 0.5
                                                              │ AND entry_fills ≥ 30
                                                              │ AND boundary_violation == 0
                                                              ▼
                                                        Stage 3 (demo × 21d × 5S × full universe)
                                                              │
                                            auto-promote:    │ gross_pnl > 0
                                                              │ AND DSR/PBO PASS (W-AUDIT-6)
                                                              │ AND chain_ok ratio ≥ 0.7
                                                              │ AND boundary_violation == 0
                                                              ▼
                                                        Stage 4 (LIVE_PENDING — operator MAG-084 + LG-X-04)
                                                              │
                                                              ▼
                                                          [TRUE LIVE — Mainnet]

  ▲                                                                ▲
  │           auto-rollback to Stage 0                             │
  └────────────────── ANY of: ──────────────────────────────────────┘
       lease IPC failure rate 24h > 0.5%
       authorization invalid
       SM-04 ≥ L3 escalate (any cohort)
       [40] realized_edge_acceptance FAIL
       [55] chain_with_lease ratio drop ≥ 10%
       [42b] settled eligible ratio < 0.95
       任一 healthcheck 收 hard FAIL
       Stage ≥ 2: gross_pnl < -10 USDT (Stage 2) / < -20 USDT (Stage 3)
       DSR < 0
       chain_ok ratio < 0.3 (Stage 3)
       previous-stage rollback condition 持續 ≥ 6h (Stage 1) / 12h (Stage 2)
```

**Auto-rollback 永遠回 Stage 0**（不是 stage-1）— 與 §二 原則 6
「失敗默認收縮」一致。

### Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                      Operator GUI Layer                          │
│  (Settings tab / Governance tab — ARCH-04 §4 GUI Surface)        │
│                                                                   │
│  ┌────────────────────┐  ┌────────────────────┐                  │
│  │ Cohort Status      │  │ Promote/Rollback   │                  │
│  │ - active stage     │  │ Buttons            │                  │
│  │ - elapsed time     │  │ (IPC + Lease)      │                  │
│  │ - metric live      │  └────────────────────┘                  │
│  └────────────────────┘                                          │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼ (governance_canary_routes.py)
┌──────────────────────────────────────────────────────────────────┐
│              FastAPI Control API v1 Layer                        │
│  /api/v1/openclaw/canary/{stage,cohort,promote,rollback,history} │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼ (IPC patch_risk_config + Decision Lease)
┌──────────────────────────────────────────────────────────────────┐
│                   Rust openclaw_engine Layer                     │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ ExecutorCanaryConfig (ArcSwap hot-reload, ADR-0009)         │  │
│  │   shadow_mode: bool   (legacy projection: stage == 0)       │  │
│  │   canary_stage: u8    ← SoT                                 │  │
│  │   canary_cohort: Option<CanaryCohort {strategy,symbol,env}> │  │
│  │   stage_entered_at_ms: i64                                  │  │
│  │   observation_period_ms: u64                                │  │
│  └────────────────────┬───────────────────────────────────────┘  │
│                       │                                          │
│  ┌────────────────────▼───────────────────────────────────────┐  │
│  │ CanaryStage Enum + Promote/Rollback Logic                   │  │
│  │   transitions emit governance.canary_stage_log row          │  │
│  │   metric_snapshot JSONB captured                            │  │
│  └────────────────────┬───────────────────────────────────────┘  │
│                       │                                          │
│  ┌────────────────────▼───────────────────────────────────────┐  │
│  │ LeaseScope::CanaryStagePromotion (manual_promote 必填)      │  │
│  │ — TTL 60s, by GovernanceHub.acquire_lease()                │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────┬────────────────────────────────────────┘
                          │
                          ▼ (PG writer)
┌──────────────────────────────────────────────────────────────────┐
│                    Postgres Persistence                          │
│                                                                   │
│  ┌─────────────────────────┐  ┌─────────────────────────┐        │
│  │ governance.             │  │ governance.             │        │
│  │ canary_stage_log        │  │ canary_stage_metric_    │        │
│  │ (append-only)           │  │ registry                │        │
│  │ — transition history    │  │ — metric SQL + threshold│        │
│  └─────────────────────────┘  └─────────────────────────┘        │
└─────────────────────────┬────────────────────────────────────────┘
                          │
                          ▼ (cron 0 */6 * * *)
┌──────────────────────────────────────────────────────────────────┐
│        helper_scripts/db/passive_wait_healthcheck/               │
│        checks_governance.py                                      │
│                                                                   │
│  check_58_graduated_canary_stage_invariant(cur)                  │
│   1. promote/rollback metric registry 存在                        │
│   2. rollback metric trip → FAIL                                 │
│   3. observation_period 一致性                                    │
│   4. cohort 規範 (Stage 1/2 必 1S × 1Sym, Stage 3 必 full universe)│
│   5. SM-04 ≥ L3 → hard FAIL → 觸 stage = 0 rollback              │
└──────────────────────────────────────────────────────────────────┘
                          ▲
                          │ (read by stage-aware shadow_mode_provider)
┌─────────────────────────┴────────────────────────────────────────┐
│                Python 5-Agent Runtime Layer                      │
│                                                                   │
│  shadow_mode_provider() 升級為 stage-aware：                       │
│  - cohort match 計算 (strategy_id × symbol × environment)          │
│  - observation_period 計算 (停留時長)                             │
│  - auto-promote 條件 eval (per stage 規格)                         │
│  - rollback metric eval (任一 trip → return Stage 0)              │
│  - exception path → fail-closed Stage 0 (不是 Stage 1)            │
│                                                                   │
│  ExecutorAgent._read_shadow_mode():                              │
│  - shadow = (stage == 0)  legacy projection                      │
│  - cohort 內 strategy × symbol → 真送 intent                       │
│  - cohort 外 → 仍 fail-closed shadow                              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Stage Transition Criteria

### 2.1 5-stage 詳表（per AMD-2026-05-09-03 §2.2）

| Stage | Cohort scope | 觀察期 | 自動升級條件（**全部** AND） | Auto-rollback 觸發（**任一** OR） |
|---|---|---|---|---|
| **0** | shadow only — 不送 intent 到 Rust submit path | 0（持續態，無自動升級） | n/a — 升 Stage 1 必須 operator 顯式核准（GUI Settings tab toggle 或 IPC `patch_risk_config`） | n/a |
| **1** | 1 strategy × 1 symbol × `Environment::Paper` | 7d wall-clock | `entry_fills ≥ 10` AND `boundary_violation_count == 0` | 任一 fail-closed metric trip：lease IPC 失敗率 24h > 0.5% / authorization invalid / SM-04 ≥ L3 / `[40]` realized_edge_acceptance FAIL / `[55]` chain_with_lease ratio drop ≥ 10% / `[42b]` settled eligible ratio < 0.95 / 任一 healthcheck 收 hard FAIL |
| **2** | 1 strategy × 1 symbol × `Environment::Demo` | 14d wall-clock | `gross_pnl_usdt > -5.0` AND `DSR > 0.5` AND `entry_fills ≥ 30` AND `boundary_violation_count == 0` | `gross_pnl_usdt < -10.0` OR `DSR < 0` OR Stage 1 任一 rollback 條件持續 ≥ 6h |
| **3** | 5 active strategies × `Environment::Demo` full universe | 21d wall-clock | `gross_pnl_usdt > 0` AND `DSR/PBO PASS by W-AUDIT-6 acceptance` AND `attribution_chain_ok ratio ≥ 0.7` AND `boundary_violation_count == 0` | `gross_pnl_usdt < -20.0` OR `DSR < 0` OR `attribution_chain_ok ratio < 0.3` OR Stage 2 任一 rollback 條件持續 ≥ 12h |
| **4** | `LIVE_PENDING` — 等待 operator MAG-084 + LG-X-04 supervised-live state machine + 全部 5-gate live boundary 滿足 | n/a — operator 顯式拍板（不自動升級） | operator + signed authorization + Decision Lease per-intent + Rust execution authority 全鏈 | n/a — 任何 boundary 失敗即 cancel_token shutdown，回退至 Stage 0（不是 Stage 3） |

### 2.2 Boundary（5-gate Live Boundary 不被觸碰）

graduated canary **不適用** Live boundary 5-gate（CLAUDE.md §四 line 125-136）：

1. Python `live_reserved` global mode
2. Python Operator 角色 auth
3. `OPENCLAW_ALLOW_MAINNET=1` env
4. secret slot api_key + api_secret
5. signed authorization.json HMAC-SHA256 + 未過期 + env_allowed match

→ Stage 4 enter 必須**全部**滿足。Stage 1-3 不可作為 live gate 替代。

### 2.3 DOC-08 §12 9 條安全不變量 + SM-04 ladder 仍硬不變

詳見 AMD-2026-05-09-03 §3.1 / §3.2。任何 stage 違反任一條 = 立即 auto-rollback
至 Stage 0 + 觸發 incident。

### 2.4 §二 16 根原則的硬不變式（4 範圍）

per AMD-2026-05-09-03 §3.4：
- 原則 1（單一寫入口）/ 原則 2（讀寫分離）/ 原則 4（策略不繞風控）
- 原則 5（生存 > 利潤）/ 原則 7（學習 ≠ Live）/ 原則 9（雙重防線）
- 原則 13（cost_edge_ratio 感知）/ 原則 14（L0+L1 零外部成本）

→ 所有 stage 都查；graduated canary **不放寬**這些。

---

## 3. Component Specification

### 3.1 Rust Schema (`ExecutorCanaryConfig`)

```rust
// rust/openclaw_engine/src/config/risk.rs (concept; W-AUDIT-9 T1 IMPL)
pub struct ExecutorRiskConfig {
    /// Backward-compat projection: shadow_mode = (canary_stage == 0)
    /// 讀到 legacy `shadow_mode=false` 但 `canary_stage=0` → fail-closed reject + log
    pub shadow_mode: bool,

    /// SoT for graduated canary; default 0.
    pub canary_stage: u8,                       // 0..=4

    /// None = Stage 0 / Stage 3 / Stage 4 全 universe；Some = Stage 1/2 cohort
    pub canary_cohort: Option<CanaryCohort>,

    /// 預設 0（Stage 0 永久）；stage transition 時更新
    pub stage_entered_at_ms: i64,

    /// 預設 0（Stage 0 不觀察）；per-stage 規格觀察期（ms）
    pub observation_period_ms: u64,

    // ... 既有欄位（max_position_pct / per_symbol_position_cap 等）
}

pub struct CanaryCohort {
    pub strategy: String,
    pub symbol: String,
    pub environment: Environment,
}

pub enum CanaryStage {
    Stage0,  // shadow only
    Stage1,  // paper 7d × 1S × 1Sym
    Stage2,  // demo 14d × 1S × 1Sym
    Stage3,  // demo 21d × 5S × full universe
    Stage4,  // LIVE_PENDING
}
```

**ArcSwap hot-reload**（per ADR-0009）：stage 變更不需 engine restart。

### 3.2 PG Schema (`governance.canary_stage_log` + `canary_stage_metric_registry`)

詳見 AMD-2026-05-09-03 §4.2。Guard A/B/C 強制；Linux PG dry-run mandatory（per
ADR-0011 + `feedback_v_migration_pg_dry_run.md`）。

**關鍵 invariant**（per TODO v19 §5.3 invariant 11 + 12）：
- `canary_stage_log.decision_lease_id` for `manual_promote` PG NOT NULL 強制
  （`CHECK (transition_kind != 'manual_promote' OR decision_lease_id IS NOT NULL)`)
- healthcheck `[58]` 對 SM-04 ≥ L3 escalate 必 hard FAIL → 觸 stage = 0 rollback

### 3.3 Python `shadow_mode_provider` Stage-aware

```python
# program_code/.../executor_config_cache.py (concept; W-AUDIT-9 T3 IMPL)
def shadow_mode_provider() -> ShadowModeReading:
    """
    Stage-aware shadow_mode evaluation.

    Returns:
        ShadowModeReading with:
        - is_shadow: bool (legacy projection)
        - canary_stage: int
        - cohort: Optional[CanaryCohort]
        - reason: str

    Invariant:
        Exception path always returns Stage 0 (not Stage 1).
        Cache miss / IPC failure / schema fail → fail-closed Stage 0.
    """
    try:
        config = _read_executor_canary_config()  # IPC read
    except (IpcError, SchemaError, CacheError):
        # FAIL-CLOSED: Stage 0
        return ShadowModeReading(is_shadow=True, canary_stage=0, cohort=None,
                                 reason="exception_fallback_stage_0")

    stage = config.canary_stage
    cohort = config.canary_cohort

    if stage == 0:
        return ShadowModeReading(is_shadow=True, canary_stage=0, cohort=None,
                                 reason="stage_0_default")

    # Stage 1/2: cohort match check
    if stage in (1, 2):
        if cohort is None:
            # Cohort missing for Stage 1/2 → fail-closed Stage 0
            return ShadowModeReading(is_shadow=True, canary_stage=0, cohort=None,
                                     reason="stage_1_2_missing_cohort_fallback")
        # cohort 內 → 真送；cohort 外 → shadow
        # 每筆 intent 在 ExecutorAgent._read_shadow_mode 時 cohort match 計算

    # Stage 3: full active universe
    if stage == 3:
        # 全 universe 都送

    # Stage 4: LIVE_PENDING — 仍走 5-gate live boundary
    if stage == 4:
        # 不在此處決定送/不送；Live boundary 5-gate 才是 truth

    return ShadowModeReading(is_shadow=False, canary_stage=stage,
                             cohort=cohort, reason=f"stage_{stage}_active")
```

**關鍵 invariant**（per TODO v19 §5.3 invariant 9）：
`shadow_mode_provider` exception path 必 fail-closed Stage 0（**不是** Stage 1）。
這是 `_read_shadow_mode` 的 invariant，break 即整 W-A 復活雞蛋死循環
（per AMD-2026-05-09-03 §1.2 FA push back）。

### 3.4 LeaseScope::CanaryStagePromotion

```rust
// rust/openclaw_engine/src/governance/lease.rs (concept; W-AUDIT-9 T6 IMPL)
pub enum LeaseScope {
    Intent(IntentId),
    OrderSubmit(OrderId),
    CanaryStagePromotion {
        from_stage: u8,
        to_stage: u8,
        cohort: Option<CanaryCohort>,
        operator_id: String,
    },
    // ... 既有 scopes
}

// TTL 60s
// audit chain：canary_stage_log.decision_lease_id 必填 for transition_kind = 'manual_promote'
```

### 3.5 healthcheck `[58] graduated_canary_stage_invariant`

詳見 AMD-2026-05-09-03 §4.1。**Cron**：`0 */6 * * *`（與 passive_wait_healthcheck
同期）。**Exit code**：FAIL → exit 1（silent-dead 自動偵測）；WARN → exit 0 + log。

### 3.6 GUI Surface (`tab-governance.html` + `governance_canary_routes.py`)

詳見 AMD-2026-05-09-03 §4.3。

**關鍵元素**：
1. 當前 active cohort 列表（environment × strategy × symbol × stage × elapsed）
2. 每 cohort 升級進度條（自動升級條件分項 PASS/PENDING）
3. 每 cohort rollback metric live + margin
4. 手動 promote / rollback 按鈕（IPC + Decision Lease，不直寫 PG）
5. 歷史 transition timeline（讀 `governance.canary_stage_log` 最近 30 天）

**Read-only 預設**：GUI 只 SELECT；任何 stage 變更必經 IPC + Lease。

---

## 4. Boundary（不適用範圍）

### 4.1 graduated canary **僅適用** alpha-bearing pathway

per AMD-2026-05-09-03 §3.5：
- 5-Agent 鏈下單真值流（Strategist → Guardian → Executor → IntentProcessor → Rust submit path）
- Layer 2 escalation **proposal 階段**（不是 Layer2 自主下單，per ADR-0020 仍 manual + supervisor-only）
- Promotion Pipeline trigger（從 paper 候選 → demo cohort）
- `cost_edge_advisor` 的 cost_gate 是否強制 fail-closed（stage ≥ 2 可放寬至 advisory）
- Cognitive Modulator 的 conservative-default 落地強度
- 新 alpha source IMPL（R-1 Alpha Surface Foundation 之後新增的 alpha source 必走完整 5-stage canary）

### 4.2 不適用（仍維持 binary fail-closed）

- DOC-08 §12 9 條安全不變量
- SM-04 CIRCUIT_BREAKER 5 ladder
- Live boundary 5-gate（CLAUDE.md §四）
- §二 16 根原則的硬不變式（4 範圍：原則 1/2/4/5/7/9/13/14）

---

## 5. 配套 Invariants（TODO v19 §5）

### 5.1 結構 invariant

| # | Invariant | 對應 ARCH-04 元件 |
|---|---|---|
| 1 | Sprint N+0 W-AUDIT-9 7 sub-task 全 land + `[58]` PASS + `governance.canary_stage_log` active | §3.5 healthcheck + §3.2 PG schema |
| 4 | W-AUDIT-9 Stage 1 cohort active + 7d wall-clock 觀察期未提前升級（standalone milestone） | §2.1 Stage 1 觀察期 7d |

### 5.2 安全 invariant

| # | Invariant | 對應 ARCH-04 元件 |
|---|---|---|
| 9 | `shadow_mode_provider` exception path fail-closed Stage 0（**不是** Stage 1） | §3.3 Python provider invariant |
| 10 | W-AUDIT-9 Stage 0 binary fail-closed 不變式保留（Live boundary 5-gate / SM-04 ladder / DOC-08 §12 / §二 16 原則 4 範圍均不被 graduated canary 觸碰） | §4.2 不適用範圍 |

### 5.3 治理 invariant

| # | Invariant | 對應 ARCH-04 元件 |
|---|---|---|
| 11 | `canary_stage_log.decision_lease_id` for `manual_promote` PG NOT NULL 強制 | §3.2 PG schema CHECK |
| 12 | healthcheck `[58]` 對 SM-04 ≥ L3 escalate 必 hard FAIL → 觸 stage = 0 rollback | §3.5 + §2.3 boundary |

### 5.4 (未來) invariant 23 — Cohort Scope Frequency Cap

CC final review §7.2 建議（per W-AUDIT-9 IMPL 落地後 Sprint N+1+ 加入）：

> Cohort 變更不可頻繁（建議 7d window 內 Stage 1 / Stage 2 cohort
> 切換 ≤ 3 次）。違反 = WARN + Guardian review。
> 動機：避免 operator 在 evidence collection 過程過度切換 cohort
> 阻碍 stage 觀察期完整性。

待 W-AUDIT-9 IMPL land 後 PA 拍板加入 TODO §5.3 invariant 23。

---

## 6. IMPL Wave: W-AUDIT-9

詳見 AMD-2026-05-09-03 §5。Sprint N+0 W1-W2 dispatch 7 sub-task：

| Sub-task | E1 | 文件範圍 | ARCH-04 對應 |
|---|---|---|---|
| W-AUDIT-9-T1 Rust schema | E1-A | `rust/openclaw_engine/src/config/risk.rs` + serde | §3.1 |
| W-AUDIT-9-T2 V### migration | E1-B | `sql/migrations/V0XX__governance_canary_stage.sql` | §3.2 |
| W-AUDIT-9-T3 shadow_mode_provider stage-aware | E1-C | `executor_config_cache.py` + `executor_agent.py` | §3.3 |
| W-AUDIT-9-T4 healthcheck [58] | E1-D | `helper_scripts/db/passive_wait_healthcheck/checks_governance.py` | §3.5 |
| W-AUDIT-9-T5 GUI surface | E1-E (stand-by) | `tab-governance.html` + `governance_canary_routes.py` | §3.6 |
| W-AUDIT-9-T6 manual promote Decision Lease | E1-D | `governance_hub.py` LeaseScope + Rust facade | §3.4 |
| W-AUDIT-9-T7 E4 regression | E1-G | `tests/test_graduated_canary_*.py` 5 stage transition | §2.1 全部 |

---

## 7. 與其他 wave 的互動

per AMD-2026-05-09-03 §5.4：

- **W-AUDIT-3 fake-live alignment**：W-AUDIT-3b runtime smoke `fake_live_smoke_test`
  必加 Stage 0/1/2 三層驗證（per TODO v19 §5.4 invariant 20）
- **W-AUDIT-4b ML 基座**：M1 → M2 → M3 串行 IMPL 不被 ARCH-04 直接影響；
  R-3 Hypothesis Pipeline (W-AUDIT-8f) IMPL 後 hypothesis 升 EVIDENCE_GATE 時必 read
  對應 cohort canary stage
- **W-AUDIT-6 策略 verdict**：funding_arb 退役不變；新策略（如 bb_breakout 5m
  redesign）必走 Stage 1 入場
- **W-AUDIT-7 GUI/AI**：Layer2 manual trigger UI 與 §3.6 GUI surface 同 tab，
  可合併設計
- **W-AUDIT-8a Alpha Surface Foundation**：R-1 後新增 alpha source 必走完整
  5-stage canary（per AMD-2026-05-09-03 §3.5）；不可繞道直接 Stage 3+
- **ADR-0022 Strategist wide_parameter_adjustment skill**：Stage 1/2/3 cohort
  strategy 觸發 wide skill 時須額外驗 cohort 一致性（W-AUDIT-9 T3 IMPL 完成後）

---

## 8. 失敗 Fallback（per AMD-2026-05-09-03 §5.5）

如果 W-AUDIT-9 IMPL 期間發現：
- Rust schema 升級觸發 IPC schema break → 回退到「保留 binary `shadow_mode`
  + 新增 `canary_stage` 並列 field」的 dual-field 方案
- healthcheck `[58]` metric SQL 撞 DB 性能瓶頸 → 改成 `[58a]` 6h 抽樣
  + `[58b]` daily full
- GUI surface 開發超期 → Stage 0/1 用 IPC CLI 觸發（不阻塞 Stage 1 entry），
  Stage 2/3 等 GUI ready

**絕不回退**：不接受「回到 binary shadow_mode default」+「P0-EDGE-1
死循環復活」。

---

## 9. Risk Acceptance（per AMD-2026-05-09-03 §6.2）

最壞情境：
- Stage 1：1 strategy × 1 symbol × paper × 7d → paper 不是真錢損失
- Stage 2：1 strategy × 1 symbol × demo × 14d → 達到 rollback 閾值 -10 USDT 即 trip → 實際損失 ≤ -10 USDT，demo endpoint 不影響真 mainnet
- Stage 3：5 active strategies × demo × 21d → 達到 rollback 閾值 -20 USDT 即 trip → 實際損失 ≤ -20 USDT

**對比當前持續損失**：CLAUDE.md §三 7d demo gross -26.44 USDT（averaging
-3.78 USDT/day），而當前 binary fail-closed 不會自動止血。**graduated canary
的最壞 case Stage 2 / Stage 3 rollback 損失 ≤ 當前持續損失的 7-10 天累積**。

---

## 10. §二 16 原則合規確認

per AMD-2026-05-09-03 §6.3 — 16 條全綠。詳見 ARCH-04 §2.4 + §4.2 範圍區分。

---

*OpenClaw / Arcane Equilibrium Architecture Spec ARCH-04 — Graduated Canary 5-Stage Architecture*
