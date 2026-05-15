# Amendment AMD-2026-05-09-03 — Graduated Canary Default for Alpha-Bearing Pathways

**對應 spec**：SM-05 · DOC-01 §5.5 / §5.6 / §5.11 · ADR-0017 · ADR-0018 · ADR-0020
**Supersedes**：AMD-2026-05-09-02 §2 (Operator Decision Audit Closure — `P0-DECISION-AUDIT-2` Option A "shadow_mode = fail-closed default") *只取代「W-A demo 預設姿態」字面*，AMD-2026-05-09-02 §3 / §4 / §5（策略 verdict / openclaw_core sunset / Layer2 boundary）保持不變
**Cross-references**：AMD-2026-05-09-01（SM-05 polling design，源實作不變）· AMD-2026-05-02-01（SM-02 R-04 retrofit Path A，§5.4.1 W-C 授權）· `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`
**日期**：2026-05-09
**作者**：PA（Operator Decision-1 拍板後起草）
**狀態**：Accepted — planning authority；F-01 source 不再以「binary fail-closed default」為唯一姿態，但實作必待 §5 IMPL wave land 後 runtime active
**索引**：`SPECIFICATION_REGISTER.md` Amendments section
**TODO 連結**：W-AUDIT-3 / W-AUDIT-6 / W-AUDIT-9（新）/ P0-EDGE-1 / P0-LG-2 / P0-LG-3 / P0-LG-4 / R-1（Alpha Surface Foundation pre-req）

---

> **2026-05-15 supersession note**: AMD-2026-05-15-01 supersedes this document's Stage 1 paper cohort semantics. `Environment::Paper × 7d` is removed as a promotion stage; Stage 0R Replay Preflight now outputs only `eligible_for_demo_canary=true/false`, and Stage 1 is `Environment::Demo` micro-canary evidence. Historical rationale below is retained for audit context only.

## 1. 修訂背景

### 1.1 AMD-2026-05-09-02 §2 Option A 原文

AMD-2026-05-09-02（PM 2026-05-09 拍板）§2 Option A 條文：

> `executor.shadow_mode=true` is the W-A demo fail-closed posture. The local 5-Agent Executor path is not permanently shadow-only, but `shadow_mode=false` may be used only after `P0-EDGE-1` plus supervised promotion gates.

該條文配合 AMD-2026-05-09-01 §3 / §4 SM-05 invariants，等同把「demo 環境 5-Agent Executor 整鏈 shadow」設為**單一二元姿態**（`true / false`），其中 `true` = 全部 alpha-bearing pathway 不下單、`false` = 全部 alpha-bearing pathway 真下單。沒有中間態。

### 1.2 4-agent 共識與 FA push back

2026-05-09 PA（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`）+ FA（同日 audit fix verification v2）+ QC + MIT 四 agent 在獨立視角 audit 後達成共識：當前架構在 demo 上**累積 22 個 fail-closed default**（cost_gate / Decision Lease shadow / executor shadow_mode / Cognitive Modulator default conservative / SM-04 ladder / Guardian veto / Layer2 manual-only / lambda:True 移除 / `shadow_mode_provider` IPC fail / `_read_shadow_mode` exception fallback / OPENCLAW_LEASE_ROUTER 單向 / `risk_envelope` 默認收縮 / strategy active=false default for new strategies / promotion gate min_observations=200 / DSR/PBO 卡 None evidence / Kelly tier hardcoded / `[40]` realized edge tolerance / `[33]` maker fill-rate target / `[55]` chain coverage / `[42b]` LOW_SAMPLE / `[51]` opportunity_positive_n=0 / `funding_arb` ADR-0018 退役 default）。

**FA 「P0-EDGE-1 雞生蛋蛋生雞死循環」論證**（PA 報告 §1.5 + Cluster B 公因式）：

- `P0-EDGE-1` 解封條件 = realized edge 轉正
- realized edge 轉正條件 = 5 策略在 demo 撞上**真實**的 Bybit fee + slippage + cancel rate
- demo 撞上真實 cost 的條件 = `executor.shadow_mode=false` 在 demo 至少跑出 ≥ N 筆真 demo fill
- `shadow_mode=false` 的條件（per AMD-2026-05-09-02）= `P0-EDGE-1` 已解封 + supervised promotion gates 已 pass

→ **死循環**：edge 證據需要真 demo fill / 真 demo fill 需要 shadow_mode 翻 / shadow_mode 翻需要 edge 證據。

「期望 alpha = 0」具體數學形態：當 22 個 fail-closed default 在 demo 累加時，**進入下單路徑的條件機率**乘積 = `Π_{i=1..22} P(passi)` ≈ 0（每條路徑單獨 P 約 0.5-0.9，22 條乘積在 1e-3 量級），故 demo 環境本身就在生產 0 fill / 0 evidence / 0 edge / 0 promotion 的 stationary fixed point。當前 7d demo gross `-26.44 USDT` 不是策略產生的 negative alpha，是「極稀疏 fill 撞極端 fee event」的 sampling artifact，與真實策略 expected value 無關。

### 1.3 為何 binary 升級為 graduated canary

FA push back 採納的核心：**fail-closed 是門檻語義，不是 stage 語義**。binary 模型把「accept」與「reject」之間的所有中間 evidence collection 路徑封死，於是 P0-EDGE-1 永遠拿不到收斂證據。

graduated canary 的 governance 語義是：
- 在 alpha-bearing pathway 上**保留 5 個離散 stage**（shadow / single-symbol-paper / single-symbol-demo / multi-symbol-demo / live-pending）
- **每 stage 都是條件 fail-closed**（自動升級條件 + auto-rollback metric 雙鎖），不放棄 fail-closed 哲學
- evidence collection 從「等 binary flip」改為「stage 內 SLA 觀察期」
- 與 §二 原則 #6（失敗默認收縮）相容：失敗時 auto-rollback 到 stricter shadow，**仍滿足收縮語義**

---

## 2. 修訂內容（核心）

### 2.1 新姿態定義

把 `executor.shadow_mode` 從 binary `bool` 升級為 **5-stage graduated canary cohort**。Rust `RiskConfig.executor` schema 仍保留 `shadow_mode: bool` 字段為 backward-compat，但其語義從「全鏈授權旗標」窄化為「stage 0 vs stage ≥1 的 boolean projection」。權威 SoT 改為新欄位 `executor.canary_stage: u8 (0..=4)` + `executor.canary_cohort: CanaryCohort{strategy: Option<String>, symbol: Option<String>, environment: Environment}` + `executor.stage_entered_at_ms: i64` + `executor.observation_period_ms: u64`。

### 2.2 5-Stage 表

| Stage | Cohort scope | 觀察期 | 自動升級條件（**全部** AND）| Auto-rollback 觸發（**任一** OR）|
|---|---|---|---|---|
| **0** | shadow only — 不送 intent 到 Rust submit path | 0（持續態，無自動升級）| n/a — 升 Stage 1 必須 operator 顯式核准（Settings tab toggle 或 IPC `patch_risk_config`）| n/a |
| **1** | 1 strategy × 1 symbol × `Environment::Paper` | 7d wall-clock | `entry_fills ≥ 10` AND `boundary_violation_count == 0`（boundary = lease IPC 失敗 / authorization revoke / SM-04 escalate ≥ L3 / Decision Lease deny / Guardian veto / `_read_shadow_mode()` exception 任一）| 任一 fail-closed metric trip：lease IPC 失敗率 24h > 0.5% / authorization invalid / SM-04 ≥ L3 / `[40]` realized_edge_acceptance FAIL / `[55]` chain_with_lease ratio drop ≥ 10% / `[42b]` settled eligible ratio < 0.95 / 任一 healthcheck 收 hard FAIL |
| **2** | 1 strategy × 1 symbol × `Environment::Demo` | 14d wall-clock | `gross_pnl_usdt > -5.0` AND `DSR > 0.5` AND `entry_fills ≥ 30` AND `boundary_violation_count == 0` | `gross_pnl_usdt < -10.0` OR `DSR < 0` OR Stage 1 任一 rollback 條件持續 ≥ 6h |
| **3** | 5 active strategies × `Environment::Demo` full universe | 21d wall-clock | `gross_pnl_usdt > 0` AND `DSR/PBO PASS by W-AUDIT-6 acceptance` AND `attribution_chain_ok ratio ≥ 0.7` AND `boundary_violation_count == 0` | `gross_pnl_usdt < -20.0` OR `DSR < 0` OR `attribution_chain_ok ratio < 0.3` OR Stage 2 任一 rollback 條件持續 ≥ 12h |
| **4** | `LIVE_PENDING` — 等待 operator MAG-084 + LG-X-04 supervised-live state machine + 全部 5-gate live boundary 滿足 | n/a — operator 顯式拍板（不自動升級）| operator + signed authorization + Decision Lease per-intent + Rust execution authority 全鏈 | n/a — 任何 boundary 失敗即 cancel_token shutdown，回退至 Stage 0（不是 Stage 3）|

### 2.3 預設姿態

**demo 環境**：`shadow_mode_provider` 動態返回 `canary_stage = 1` 為預設**啟用**狀態（非 Stage 0）。對 cohort 內 1 strategy × 1 symbol，executor 真實送 intent；對 cohort 外的 4 strategy × 24 symbol，executor 仍 fail-closed shadow（即 `shadow_mode=true` legacy projection）。

**paper 環境**：默認 `canary_stage = 1`（paper 本身就是 simulation；等同 baseline）。

**live 環境**（LiveDemo + Mainnet）：默認 `canary_stage = 0`，**graduated canary default 完全不適用 live**。要 Stage 4 必須走 §3 列舉的不適用範圍以外的所有 live boundary。

### 2.4 Cohort 初始選擇規則

Stage 1 / Stage 2 cohort 由 **operator 在 Settings tab 顯式選擇**（不由 system auto-pick）。操作流程：
1. operator 在 Settings tab 看 §4.3 GUI surface 顯示的「策略/symbol Sharpe-by-regime ranking」
2. operator 從候選 strategy list 拍板 1 strategy + 從 active universe 拍板 1 symbol
3. cohort 變更必經 IPC `patch_risk_config` + Decision Lease + audit log（與 risk_config 任何欄位變更同等治理）
4. cohort 切換 = 重置觀察期 timer

---

## 3. 不適用範圍（仍維持 fail-closed）

graduated canary **不適用**下列場景，這些場景仍**強制** binary fail-closed：

### 3.1 DOC-08 §12 9 條安全不變量
（pre-trade audit replay / lease acquired before submit / fills writer / SM-04 auto bleed / authorization expired → cancel_token / Mainnet OPENCLAW_ALLOW_MAINNET / Bybit retCode != 0 / Reconciler diff → paper degrade / Operator 角色 + live_reserved 缺一即拒）— **任何 stage 違反任一條** = 立即 auto-rollback 至 Stage 0 + 觸發 incident。

### 3.2 SM-04 CIRCUIT_BREAKER 5 ladder
SM-04 escalate ≥ L3 = 自動 rollback 至 Stage 0 across all cohorts。canary stage 不能繞過 SM-04 ladder（即使 Stage 3 cohort 全 healthy，只要全局 SM-04 ≥ L3 就 stage = 0）。

### 3.3 Live boundary 5-gate
（CLAUDE.md §四 line 125-136：Python `live_reserved` global mode / Python Operator 角色 auth / `OPENCLAW_ALLOW_MAINNET=1` env / secret slot api_key+api_secret / signed authorization.json HMAC-SHA256 + 未過期 + env_allowed match）— Stage 4 enter 必須**全部**滿足。Stage 1-3 不可作為 live gate 替代。

### 3.4 §二 16 根原則的硬不變式
- 原則 1（單一寫入口）：所有 stage 都通過唯一 IntentProcessor
- 原則 2（讀寫分離）：學習/GUI/研究永遠只讀，graduated canary 不放寬寫入面
- 原則 4（策略不繞風控）：所有 stage 的下單意圖必經 Guardian 審批
- 原則 5（生存 > 利潤）：StopManager / liquidation_buffer / hard_stop 在所有 stage active
- 原則 7（學習 ≠ Live）：學習平面與 Live 平面隔離不變
- 原則 9（雙重防線）：本地 + 交易所條件單在 Stage ≥ 1 都必 active
- 原則 13（cost_edge_ratio ≥ 0.8 → 建議關倉）：所有 stage 都查
- 原則 14（L0+L1 零外部成本可運行）：graduated canary 不依賴 L2 cloud LLM

### 3.5 graduated canary **僅適用** alpha-bearing pathway

明確列出**適用**範圍：
- 5-Agent 鏈下單真值流（Strategist → Guardian → Executor → IntentProcessor → Rust submit path）
- Layer 2 escalation **proposal 階段**（不是 Layer2 自主下單，per ADR-0020 仍 manual + supervisor-only）
- Promotion Pipeline trigger（從 paper 候選 → demo cohort）
- `cost_edge_advisor` 的 cost_gate 是否強制 fail-closed（stage ≥ 2 可放寬至 advisory）
- Cognitive Modulator 的 conservative-default 落地強度（stage 越高，modulator 對 Strategist 的「降頻」建議權重越大，但永不解除原則 4/5/11 硬邊界）
- 新 alpha source IMPL（R-1 Alpha Surface Foundation 之後新增的 alpha source 必走完整 5-stage canary，不可繞道直接 Stage 3+）

---

## 4. 配套機制

### 4.1 Healthcheck `[58] graduated_canary_stage_invariant`

新增 healthcheck（package `helper_scripts/db/passive_wait_healthcheck/checks_governance.py`，與 `[55]` `[56]` 同 family），check 名稱 `check_58_graduated_canary_stage_invariant(cur)`。

**語義**：
- 讀 `governance.canary_stage_log`（§4.2 新建表）取 latest active stage per (environment, strategy, symbol) cohort tuple
- 對每 active cohort，驗證：
  1. **升級條件 metric 存在**：每 stage 的自動升級條件對應 SQL query 在 cron 偵測表 `governance.canary_stage_metric_registry`（new in §4.2）有 row → 不存在 = **WARN**（spec drift signal）
  2. **rollback metric 存在**：每 stage 的 auto-rollback metric 同上 → 不存在 = **WARN**
  3. **rollback trip 偵測**：對 active cohort 跑 rollback metric SQL，若返回 `tripped=true` → **FAIL**（必觸發 stage = 0 rollback）
  4. **observation_period 一致性**：`stage_entered_at_ms` 與當前 stage 規格觀察期對齊 → 不一致 = **WARN**
  5. **cohort 規範**：Stage 1/2 cohort 必為 1 strategy × 1 symbol；Stage 3 必為 active universe；違反 = **FAIL**

**Cron**：`0 */6 * * *`（與 passive_wait_healthcheck 同期）。

**Exit code**：FAIL → exit 1（silent-dead 自動偵測）；WARN → exit 0 + log。

### 4.2 PG 持久化（V### migration）

新建 schema `governance` 下兩表：

```sql
-- governance.canary_stage_log
-- 每次 stage transition 落地，append-only。
CREATE TABLE IF NOT EXISTS governance.canary_stage_log (
    id BIGSERIAL PRIMARY KEY,
    transitioned_at_ms BIGINT NOT NULL,        -- ms epoch
    environment TEXT NOT NULL,                  -- 'paper' | 'demo' | 'live_demo' | 'mainnet'
    cohort_strategy TEXT,                       -- nullable (Stage 0/3 全 universe)
    cohort_symbol TEXT,                         -- nullable
    from_stage SMALLINT NOT NULL CHECK (from_stage BETWEEN 0 AND 4),
    to_stage SMALLINT NOT NULL CHECK (to_stage BETWEEN 0 AND 4),
    transition_kind TEXT NOT NULL,              -- 'manual_promote' | 'auto_promote' | 'auto_rollback' | 'incident_rollback'
    reason TEXT NOT NULL,                       -- 自動升級條件 PASS detail / rollback metric trip detail / operator note
    initiated_by TEXT NOT NULL,                 -- 'operator:<role>' | 'system:auto_promote' | 'system:auto_rollback' | 'system:sm04_l3_escalate'
    decision_lease_id TEXT,                     -- nullable; manual_promote 必填
    metric_snapshot JSONB,                      -- 升級/rollback 當時各 metric 取值
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_canary_stage_log_env_cohort_time
    ON governance.canary_stage_log (environment, cohort_strategy, cohort_symbol, transitioned_at_ms DESC);

-- governance.canary_stage_metric_registry
-- §4.1 healthcheck 用以驗 metric SQL 是否存在 / drift。
CREATE TABLE IF NOT EXISTS governance.canary_stage_metric_registry (
    metric_id TEXT PRIMARY KEY,                 -- e.g. 'stage1_promote_entry_fills'
    stage SMALLINT NOT NULL CHECK (stage BETWEEN 1 AND 4),
    metric_kind TEXT NOT NULL,                  -- 'promote_condition' | 'rollback_trigger'
    metric_sql TEXT NOT NULL,                   -- parameterized SQL ($1=cohort_strategy, $2=cohort_symbol, $3=stage_entered_at_ms)
    metric_threshold JSONB NOT NULL,            -- {gt: 10} / {lt: -10.0} / {ratio_lt: 0.7} 等
    rationale TEXT NOT NULL,                    -- 為何這個 metric / 引用 spec 段落
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Guard A/B/C**：依 CLAUDE.md §七 SQL migration 規範。Linux PG dry-run 強制（per ADR-0011 + `feedback_v_migration_pg_dry_run.md`）。

### 4.3 GUI surface（Settings tab 或新 Governance tab subsection）

加 **「Graduated Canary Cohort Status」** 區塊（OpenClaw Control Console 13-tab dictionary 內 `settings` tab 或 `governance` tab subsection，由 W-AUDIT-7 GUI implementer 拍板）：

**顯示元素**：
1. **當前 active cohort 列表**：environment × strategy × symbol × stage × stage_entered_at（human-readable elapsed）
2. **每 cohort 升級進度條**：自動升級條件分項 PASS/PENDING（如 Stage 1 的 `entry_fills 7/10`、`boundary_violation_count 0/0`）
3. **每 cohort rollback metric live**：rollback 條件分項當前值 + 距 trip 閾值的 margin
4. **手動 promote / rollback 按鈕**：操作必經 IPC `patch_risk_config` + Decision Lease（按鈕只 emit IPC，不直寫 PG）
5. **歷史 transition timeline**：reads `governance.canary_stage_log` 最近 30 天 transitions

**Read-only 預設**：GUI 只 SELECT；任何 stage 變更必經 IPC（與 risk_config 變更同等流程）。

### 4.4 Rust schema 升級

`RiskConfig::executor` 加新欄位（向後相容 — 預設值對應「Stage 0 全鏈」）：

```rust
// rust/openclaw_engine/src/config/risk.rs (concept)
pub struct ExecutorRiskConfig {
    pub shadow_mode: bool,                      // legacy projection: shadow_mode = (canary_stage == 0)
    pub canary_stage: u8,                       // 0..=4，default 0
    pub canary_cohort: Option<CanaryCohort>,    // None = Stage 0/3/4 全 universe
    pub stage_entered_at_ms: i64,               // 預設 0（Stage 0 永久）
    pub observation_period_ms: u64,             // 預設 0（Stage 0 不觀察）
    // ... 既有欄位
}

pub struct CanaryCohort {
    pub strategy: String,
    pub symbol: String,
    pub environment: Environment,
}
```

**Backward compat**：legacy `shadow_mode: true` ⇔ `canary_stage: 0`；legacy `shadow_mode: false` 在 IMPL wave land 後**不再合法**（必伴隨 `canary_stage ≥ 1` + cohort 字段），讀到 legacy `shadow_mode=false` 但 `canary_stage=0` 的 config = fail-closed reject + log。

**ArcSwap hot-reload**：與 ADR-0009 一致；stage 變更不需 engine restart。

### 4.5 Decision Lease 接線

stage 升級 / rollback **不**走 per-intent Decision Lease（per AMD-2026-05-02-01 SM-02 scope），但 **manual stage promotion** 必伴隨一個 `LeaseScope::CanaryStagePromotion` 的 lease（新 scope kind），TTL 60s，由 operator GUI 動作 trigger。

**audit chain**：`canary_stage_log.decision_lease_id` 必填 for `transition_kind = 'manual_promote'`，否則 `[58]` healthcheck FAIL。

---

## 5. IMPL Ownership

### 5.1 Wave 派發

新建 **W-AUDIT-9 "Graduated Canary Foundation"**（不併入既有 W-AUDIT-1..7，避免 wave scope creep）。

**Wave dependency**：
- **可獨立啟動**（不阻塞於 W-AUDIT-3 fake-live alignment）— W-AUDIT-9 與 W-AUDIT-3/-4/-5/-6/-7 可並行
- **必須在 R-1 Alpha Surface Foundation IMPL 之前完成** — R-1 後新增的 alpha source 必走 5-stage canary，故 5-stage 機制必先 ready
- **與 P0-EDGE-1 解封時序**：W-AUDIT-9 IMPL land + Stage 1 開觀察 ≥ 7d → 是 P0-EDGE-1 evidence collection 的**新路徑**，取代「等 binary flip」的死路徑

### 5.2 Sprint 估算

**1.5-2 sprint**（PA 估算 base on §4 IMPL items size）：
- Sprint 1：Rust schema 升級（§4.4）+ V### migration（§4.2）+ healthcheck `[58]`（§4.1）+ shadow_mode_provider stage-aware refactor
- Sprint 2：GUI surface（§4.3）+ Settings/Governance tab integration + Decision Lease scope 新增 + E2/E4 regression + cohort initial selection wizard

### 5.3 E1 派發設計（PA 預先設計，待 PM 拍板派出）

| Sub-task | E1 | 文件範圍 | 阻塞關係 |
|---|---|---|---|
| W-AUDIT-9-T1 Rust schema | E1-A | `rust/openclaw_engine/src/config/risk.rs` + serde 上下游 | 無 |
| W-AUDIT-9-T2 V### migration | E1-B | `sql/migrations/V0XX__governance_canary_stage.sql` + Linux PG dry-run | 無（與 T1 並行） |
| W-AUDIT-9-T3 shadow_mode_provider stage-aware | E1-C | `executor_config_cache.py` + `executor_agent.py` `_read_shadow_mode` | T1 完 |
| W-AUDIT-9-T4 healthcheck [58] | E1-D | `helper_scripts/db/passive_wait_healthcheck/checks_governance.py` | T2 完 |
| W-AUDIT-9-T5 GUI surface | E1-E | OpenClaw Control Console settings/governance tab + IPC client | T1 + T2 完 |
| W-AUDIT-9-T6 manual promote Decision Lease | E1-F | `governance_hub.py` LeaseScope 新增 + Rust facade | T1 完 |
| W-AUDIT-9-T7 E4 regression | E1-G | `tests/test_graduated_canary_*.py` 5 stage transition + rollback + boundary | 全部完 |

T1+T2+T3+T6 可 4-way parallel；T4+T5 待 T2/T1 完；T7 final。

### 5.4 與其他 wave 的互動

- **W-AUDIT-3 fake-live alignment**：W-AUDIT-3 仍是 baseline，`fake_live_smoke_test` 必加 stage 0/1/2 三層驗證
- **W-AUDIT-4 ML 基座**：併入 R-3 Hypothesis Pipeline 的 wave 仍照原計劃；hypothesis 升 EVIDENCE_GATE 時必 read 對應 cohort canary stage
- **W-AUDIT-6 策略 verdict**：funding_arb 退役不變；W-AUDIT-6 IMPL 後新策略（如 bb_breakout 5m redesign）必走 Stage 1 入場
- **W-AUDIT-7 GUI/AI**：W-AUDIT-7 的 Layer2 manual trigger UI 與 §4.3 GUI surface 同 tab，可合併設計

### 5.5 失敗 fallback

如果 W-AUDIT-9 IMPL 期間發現：
- Rust schema 升級觸發 IPC schema break → 回退到「保留 binary `shadow_mode` + 新增 `canary_stage` 並列 field」的 dual-field 方案
- healthcheck `[58]` metric SQL 撞 DB 性能瓶頸 → 改成 `[58a]` 6h 抽樣 + `[58b]` daily full
- GUI surface 開發超期 → Stage 0/1 用 IPC CLI 觸發（不阻塞 Stage 1 entry），Stage 2/3 等 GUI ready

**絕不回退**：不接受「回到 binary shadow_mode default」+「P0-EDGE-1 死循環復活」。

---

## 6. Decision rationale & risk acceptance

### 6.1 Operator 為何接受此 amendment

1. **4-agent 共識壓力**：PA + FA + QC + MIT 在獨立視角下指向同一公因式（Cluster A + B），共識強度高於單方面 audit
2. **雞蛋死循環論證的明確數學形態**：22 個 fail-closed default 累加後 P(全 PASS) ≈ 0 是可量化的，不是抽象擔憂
3. **與 §二 原則 #6 的相容性**：graduated canary 不放鬆 fail-closed 哲學，只把「fail-closed 觸發點」從 binary 邊界改為 stage 邊界，rollback 仍是 stricter（回 Stage 0），完全滿足「不確定時保守」精神
4. **時序窗口已成熟**：F-01 source（AMD-2026-05-09-01）已落地、SM-02 R-04 retrofit Path A 已 sign-off、W-C lease router 已開觀察 — graduated canary 是這些 foundation 的合理 next layer

### 6.2 風險接受（quantified）

**最壞情境分析（Stage 1 worst case）**：
- 1 strategy × 1 symbol × paper × 7d
- paper 無真 fee（per ADR-0003 paper pipeline disabled by default，Stage 1 paper 是 simulated），「loss」實為 simulator 輸出
- 假設 simulator 噪音給出 `gross_pnl = -2 USDT/day` × 7d = `-14 USDT` simulated
- 但 paper PnL **不是真錢損失**

**Stage 2 worst case**：
- 1 strategy × 1 symbol × demo × 14d
- 假設達到 rollback 閾值 `-10 USDT` 即 trip → 實際 demo 損失 ≤ `-10 USDT`
- demo 環境 Bybit demo endpoint，**不影響真 mainnet 餘額**

**Stage 3 worst case**：
- 5 active strategies × demo × 21d
- 假設達到 rollback 閾值 `-20 USDT` 即 trip → 實際 demo 損失 ≤ `-20 USDT`

**對比當前持續損失**：CLAUDE.md §三 W-AUDIT-1 sync 顯示 7d demo gross `-26.44 USDT`（averaging `-3.78 USDT/day`），而當前 binary fail-closed 不會自動止血、僅持續累積稀疏 fill 撞極端 fee 的 sampling artifact。**graduated canary 的最壞 case Stage 2 / Stage 3 rollback 損失 ≤ 當前持續損失的 7-10 天累積**，且 graduated canary 至少可以**收斂到證據**（不論升或降）。

### 6.3 §二 16 原則合規確認

- 原則 1（單一寫入口）：所有 stage 仍通過 IntentProcessor — ✅
- 原則 2（讀寫分離）：GUI 顯示 read-only，stage 變更走 IPC + Lease — ✅
- 原則 3（AI ≠ 命令）：stage promote 必 lease + audit — ✅
- 原則 4（策略不繞風控）：Guardian veto / SM-04 ladder 在所有 stage active — ✅
- 原則 5（生存 > 利潤）：StopManager + 對抗性止損所有 stage active — ✅
- 原則 6（失敗默認收縮）：rollback 永遠回 Stage 0（stricter），不向 Stage 4 漂移 — ✅
- 原則 7（學習 ≠ Live）：學習平面與 live 平面隔離不變 — ✅
- 原則 8（交易可解釋）：每 transition 落 `canary_stage_log` + metric_snapshot — ✅
- 原則 9（雙重防線）：本地 stop + 交易所條件單在 Stage ≥ 1 都 active — ✅
- 原則 10（認知誠實）：metric_snapshot 區分 PASS / threshold / margin — ✅
- 原則 11（Agent 最大自主）：cohort 內 Agent 自主不變，cohort 邊界由 operator 拍 — ✅
- 原則 13（cost 感知）：所有 stage 查 cost_edge_ratio — ✅
- 原則 14（零外部成本）：graduated canary IMPL 純 L0 + DB + GUI，不依賴 L2 — ✅
- 其他 16 條已逐條校核（per CLAUDE.md §二 + DOC-01 V2 §5.1-§5.16），無違反

### 6.4 與既有 amendment / ADR 的關係

- **AMD-2026-05-09-01 §3 SM-05 invariants**：`fail-closed for cache miss / IPC failure / schema failure / provider exception` 條款**完全保留** — graduated canary 不放寬這些
- **AMD-2026-05-09-02 §2 Option A**：「fail-closed default」字面語義改寫為「Stage 0 default + condition for Stage ≥ 1」；§3 / §4 / §5 不變
- **AMD-2026-05-02-01 SM-02 R-04**：Decision Lease per-intent 不變；本 amendment 新增 `LeaseScope::CanaryStagePromotion` 是擴充 not replacement
- **ADR-0017 Scanner is evidence not authority**：scanner 在所有 stage 都是 evidence — ✅
- **ADR-0018 funding_arb retire**：funding_arb 不在 active strategy set，故不可選為 Stage 1/2/3 cohort — ✅
- **ADR-0020 Layer2 manual + supervisor only**：Layer2 不參與 stage transition automation — ✅

---

## 7. 後續動作（Sprint N+0 必跟進的 5 條）

| # | 動作 | Owner | Sprint 時點 |
|---|---|---|---|
| 1 | healthcheck `[58]` IMPL + 接 cron `0 */6 * * *` + Linux runtime 部署 | E1-D | Sprint N+0 W1 |
| 2 | PG migration `V0XX__governance_canary_stage.sql` 加 `governance.canary_stage_log` + `governance.canary_stage_metric_registry` + Guard A/B/C + Linux PG dry-run | E1-B | Sprint N+0 W1 |
| 3 | `shadow_mode_provider` 升級為 stage-aware（含 cohort match + observation_period 計算 + auto-promote/rollback eval）| E1-C | Sprint N+0 W2 |
| 4 | Settings tab GUI 升級顯示 cohort + stage + rollback metric live + manual promote 按鈕（IPC 動作）| E1-E | Sprint N+0 W2 |
| 5 | CLAUDE.md §三 同步（active gates 加 `[58]`）+ §四 硬邊界 explicit 引用 AMD-2026-05-09-03 + DOC-01 §5.5 / §5.6 implementation guidance 加 graduated canary section | TW + PA | Sprint N+0 W1 |

**E2 重點審查 3 點**（PA 標）：
1. `shadow_mode` legacy `false` 配 `canary_stage=0` 的組合必 reject；`shadow_mode_provider` exception path 仍 fail-closed 至 Stage 0（不是 Stage 1）— 這是 `_read_shadow_mode` 的 invariant，break 即整 W-A 復活雞蛋死循環
2. `canary_stage_log.decision_lease_id` for `manual_promote` 必填的 NOT NULL constraint 在 PG 層強制（不只 application 層）
3. healthcheck `[58]` 對 SM-04 ≥ L3 的 escalate 必 hard FAIL → 觸 stage = 0 rollback；不可降為 WARN

---

## 8. Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 Decision-1 | 2026-05-09 | ✅ Accepted（採納 FA push back，4-agent 共識）|
| PA | 本文件作者 | 2026-05-09 | ✅ Drafted + IMPL 拆分設計 |
| FA | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` Cluster A/B 引用 | 2026-05-09 | ✅ Push back 採納 |
| QC | 同 PA 報告 引用 | 2026-05-09 | ✅ 共識 |
| MIT | 同 PA 報告 引用 | 2026-05-09 | ✅ 共識 |
| PM | TBD（本 amendment commit 後通知）| 2026-05-09 | 🟡 Pending sign-off post-commit |

---

*OpenClaw / Arcane Equilibrium Governance Amendment — AMD-2026-05-09-03*
