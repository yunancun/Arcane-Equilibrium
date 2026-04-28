# PA RFC — G3-09 Phase C: cost_edge_advisor intent gate (reject 新倉)

- **Date**: 2026-04-28
- **Author**: PA
- **Predecessors**:
  - Phase A RFC (gate 設計初稿): `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_09_cost_edge_ratio_design.md` §4.4 / §7.3
  - Phase B RFC (observability): `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_09_phase_b_shadow_dryrun_design.md`
  - Phase B Wave 1 commits (V026 hypertable + DbSlot + healthcheck split + observation tooling): `31761a6` impl + `00db240` hotfix
  - Phase B FUP: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_phase_b_fup_sticky_ts.md`
- **HEAD**: `decf712` (origin/main, 2026-04-28)
- **Phase B baseline**: cargo lib **2299 / 0 fail** + persistence Linux PG **2 / 0 fail** + V026 idempotency RESTORED + healthcheck **32 PASS / 1 WARN / 0 FAIL**
- **Risk class**: 高（首次接 IntentProcessor 主路徑；新倉 reject 直接影響交易管線；Live 階段觸 5 項硬邊界其中 0 項，但「策略不能繞風控」#4 +「失敗默認收縮」#6 雙原則需嚴守）
- **Trade impact**: 第一次 != 0（gate 啟用後 reject 真實新倉 SubmitOrder）

> 本 RFC 是 Phase C 設計階段，**不依賴** Phase B 觀察期實測數據結果（Phase B observation 仍進行中，~04-30 才有 Tier 1 早期信號）。設計層面確定 gate 注入點 / dedup / exemption / 回滾路徑 / 派發策略，運行層面仍由 Phase B deliverable 提供 threshold calibration 證據後 PM 決定 Phase C 啟動 + flip flag。

---

## §1 Phase C 範圍

### 1.1 設計目的（從 Phase A RFC §4.4 + §7.3 沿用）

Phase A 已完成 advisory（log-only），Phase B 已完成 observability（V026 hypertable 採樣）。Phase C 完成 **binding gate**：當 `cost_edge_advisor.status == Trigger` 且 RiskConfig flag `cost_edge.gate_enabled=true` 時，**IntentProcessor reject 新倉 SubmitOrder**（不關現有倉位、不阻平倉、不阻減倉）。

從 CLAUDE.md §二 #13 「AI 資源成本感知 — `cost_edge_ratio ≥ 0.8` → 建議關倉」推導 Rust hot-path 落地：「建議關倉」= 最低破壞性實踐 = **阻新倉**（不是強制關現有倉，那會踩 #5 生存>利潤反向防線、產生 false-positive close 風險）。

### 1.2 範圍邊界（in / out）

**IN（Phase C 必做）**：
- IntentProcessor 入口插入 `cost_edge_gate_check()`（位置：Gate 1.6 與 Gate 2 之間，先於 Guardian）
- 新增 `RiskConfig.cost_edge.gate_enabled: bool`（預設 `false` — 雙保險：env=1 + RiskConfig.enabled=true + RiskConfig.gate_enabled=true）
- 新增 `RiskConfig.cost_edge.dedup_window_ms: i64`（預設 `60_000` — 60s window，避 reject spam）
- IntentProcessor 持 `Arc<CostEdgeAdvisor>` snapshot 讀路徑（與現行 `risk_config` snapshot pattern 同模式）
- 新增 `RejectionCode::CostEdgeAdvisorTrigger { ratio, threshold, triggered_at_ms }`
- Reject log 寫 `learning.cost_edge_advisor_log`（重用 V026 hypertable，新 `transition_from = "GATE_REJECT"` 標記）
- Python ExecutorAgent 接收 reject status 後處理（已有 `rejected_reason` 欄位，無需 schema 變更，僅需 reject reason 字串對齊）
- per-strategy override：`StrategyOverride.cost_edge_threshold_override: Option<f64>` + `cost_edge_exempt: bool`（emergency exit / risk_off 場景）
- IPC `patch_risk_config` 支援 hot-flip `gate_enabled` 60s 內生效（IPC 路徑已存在，僅需驗）
- Healthcheck `[31]` 新增：reject_per_hour count + per-strategy reject distribution

**OUT（Phase C 不做，留 Phase D / 後續 ticket）**：
- 強制關現有倉位（CLAUDE.md §二 #5 反向防線；Phase C 永不做）
- 阻平倉 / 阻減倉（gate 邏輯只阻「is_reducing == false」的新倉）
- per-symbol cost_edge_threshold（per-strategy 已涵蓋，per-symbol 屬 over-engineering）
- GUI tab 顯示 reject 原因（屬 Phase D / GUI 工作組）
- Live mainnet enable（per Phase A RFC §8.3，需 Operator 顯式批准 + ≥7d demo Phase B 觀察通過）
- shadow_reject_count（Phase B RFC §1.3 已明確此非 Phase B/C 範圍 — Phase C 直接 binding，跳過 shadow，因為 Phase B observability 已提供等價 ratio histogram + trigger frequency 證據）

### 1.3 與 Phase A/B 對比表

| 維度 | Phase A | Phase B | Phase C |
|---|---|---|---|
| evaluate 頻率 | 10s | 10s | 10s（不變） |
| Log 形式 | transition log only | + 1/min cycle row + transition row | + GATE_REJECT row（每次 reject 即時 INSERT） |
| IPC schema | 8 fields | + 4 observability fields | + 1 hot-path lookup（IntentProcessor 持 advisor snapshot） |
| Trade impact | 0 | 0 | **第一次 != 0**（gate flip 後 reject 真實新倉） |
| RiskConfig 改動 | `enabled` + `trigger_threshold` | 0 | + `gate_enabled` + `dedup_window_ms` |
| StrategyOverride 改動 | 0 | 0 | + `cost_edge_threshold_override` + `cost_edge_exempt` |
| RejectionCode 新增 | 0 | 0 | + `CostEdgeAdvisorTrigger` |

---

## §2 Gate 注入點 — IntentProcessor (Rust)

### 2.1 推薦：Rust 端 IntentProcessor，**不**在 Python ExecutorAgent

**決策：純 Rust 注入 + Python 端 0 改動**。

**Reasoning（4 條）**：

1. **單一寫入口（CLAUDE.md §二 #1）**：所有訂單通過唯一 IntentProcessor 路徑（不論來源是 Python 5-Agent SubmitOrder IPC 還是 Rust 內部 strategy → tick_pipeline → IntentProcessor）。在 IntentProcessor 注入 = 100% intent 經 gate；在 Python 注入 = 漏掉 Rust 內部直發 intent。
2. **Hot-path 性能**：Phase B advisor.snapshot() 已是 `Arc<RwLock<CostEdgeAdvisorState>>` clone（< 1μs），加 1 次 status enum 比對 + Optional triggered_at_ms 比對 — 完全 O(1) hot-path 可接受（vs Python IPC round-trip ~1-5ms 不可接受）。
3. **Cross-engine 一致**：Paper / Demo / Live 三 engine 各持自己的 IntentProcessor instance，gate 行為透過 RiskConfig 自動 cross-env 隔離（env-specific `risk_config_{paper,demo,live}.toml`，per memory `feedback_env_config_independence`）。
4. **與 cost_gate 並排**：既有 cost_gate（Gate 3）在 Rust 內，cost_edge_advisor gate 是同層 risk gate，物理同位 = 審計一致性 + E2 review 同視野。

**為何不在 Python ExecutorAgent**：
- ExecutorAgent 只負責 5-Agent 路徑（shadow_mode=True 預設下也只生 SubmitOrder IPC log），Rust 內部 strategy 直發 intent 走 tick_pipeline 直接到 IntentProcessor — 完全不經 Python，這 path 會漏 gate
- ExecutorAgent shadow_mode 拓撲屬 G3-03 範疇，與 cost_edge gate 正交；混在一起會讓 shadow→live 切換流程更複雜（rollback 路徑變雙倍）
- Python 改動 = 多一條 deploy 路徑（uvicorn restart），Rust 純改 = engine `--rebuild` 一次到位

### 2.2 Gate 在 IntentProcessor 主流程位置

從 `intent_processor/router.rs:38-300` 觀察既有 Gate 編號順序：

```
Gate 1   : Governance authorization
Gate 1.5 : Same-direction duplicate
Gate 1.6 : Negative-balance guard
Gate 1.7 : ★ NEW — cost_edge_advisor gate (insert here)
Gate 2   : Guardian 4-check
Gate 2.5 : Kelly sizing
Gate 2.6 : P1 hard cap
Gate 2.7 : Risk gate (check_order_allowed)
Gate 3   : Cost gate (per-intent EV)
Gate 3a  : Edge predictor (ML)
Gate 4   : Execute fill / enqueue resting order
```

**為何 Gate 1.7（在 1.6 後 + 2 前）**：

1. **早於 Guardian**：Guardian Gate 2 是「per-intent 風控」，要做完整 review 計算 risk_score；cost_edge gate 是 portfolio-level「拒新倉開」，不需 Guardian compute。Early-reject 省 Guardian 計算成本。
2. **晚於 Gate 1.6 negative-balance**：負餘額守門優先（更基本的存活檢查 — 沒錢什麼 gate 都不必跑）。
3. **晚於 Gate 1.5 duplicate**：duplicate 檢測 free（O(1) HashMap lookup），先排除明顯重複再進 advisor lookup。
4. **晚於 Gate 1 governance**：governance 不通 = 整個 path 死，advisor lookup 也是浪費。

**新倉 vs 平倉判定**（複用 Gate 2.7 既有 `is_reducing` pattern）：

```rust
let is_reducing = paper_state
    .get_position(&intent.symbol)
    .map(|p| p.is_long != intent.is_long)
    .unwrap_or(false);

// Gate 1.7: cost_edge_advisor gate (new entries only)
if !is_reducing {
    if let Some(reason) = self.check_cost_edge_gate(&intent.strategy) {
        return IntentResult::rejected(reason);
    }
}
```

**rationale `is_reducing == true` 完全跳過**：
- 平倉 / 減倉是「縮減曝險」動作，符合 #6 失敗默認收縮 + #5 生存>利潤
- gate 阻平倉 = false-positive 加倉位被困，可能引發風控連鎖（margin call）
- 方向反轉同樣放行（既有 Gate 1.5 已防同向重複，反向 = 平倉一部分 + 開新方向，整體淨曝險不一定增）

### 2.3 `check_cost_edge_gate()` 實作 sketch

```rust
// intent_processor/gates.rs (新方法)
impl IntentProcessor {
    /// G3-09 Phase C: cost_edge_advisor gate. Returns Some(reject reason) when
    /// advisor.status == Trigger AND gate_enabled AND not within dedup window
    /// AND strategy not exempt. Otherwise None (pass through).
    /// G3-09 Phase C：cost_edge_advisor 新倉 gate。
    pub(super) fn check_cost_edge_gate(
        &self,
        strategy: &str,
    ) -> Option<String> {
        let cfg = &self.risk_config.cost_edge;

        // Cheap escape: gate dormant
        if !cfg.gate_enabled {
            return None;
        }

        // per-strategy exempt path (StrategyOverride.cost_edge_exempt)
        if let Some(ovr) = self.risk_config.per_strategy.get(strategy) {
            if ovr.cost_edge_exempt {
                return None;
            }
        }

        // advisor snapshot lookup
        let advisor = match self.cost_edge_advisor.as_ref() {
            Some(a) => a,
            None => return None, // advisor not wired (env=0 or spawn failed) → pass
        };
        let state = advisor.snapshot();

        // per-strategy threshold override (default falls back to cfg.trigger_threshold)
        let effective_threshold = self
            .risk_config
            .per_strategy
            .get(strategy)
            .and_then(|ovr| ovr.cost_edge_threshold_override)
            .unwrap_or(cfg.trigger_threshold);

        // Gate evaluates effective_threshold against advisor's last ratio
        // (NOT advisor's status, because advisor uses portfolio threshold).
        // This lets per-strategy tighter threshold reject before portfolio-level
        // Trigger; portfolio-level Trigger still rejects all non-exempt strategies.
        let ratio = match state.ratio {
            Some(r) if r.is_finite() => r,
            _ => return None, // WarmUp / Disabled / Anomaly / Stale → pass (fail-closed on Trigger only)
        };

        // Per-strategy effective threshold OR portfolio-level Trigger status
        let per_strategy_breach = ratio <= effective_threshold;
        let portfolio_trigger = matches!(state.status, CostEdgeAdvisorStatus::Trigger);

        if !per_strategy_breach && !portfolio_trigger {
            return None;
        }

        // Dedup window: only emit reject log + count if last_reject_ms is older
        // than dedup_window_ms (avoid spam when advisor stays in Trigger).
        // NOTE: gate STILL rejects every intent in the window — dedup only
        // applies to the audit log emission, not the reject decision itself.
        // Rejecting every-intent is the correct semantic; dedup avoids DB spam.
        let now_ms = chrono::Utc::now().timestamp_millis();
        let should_log = self.cost_edge_last_reject_log_ms
            .as_ref()
            .map(|cell| {
                let mut last = cell.lock();
                if now_ms - *last >= cfg.dedup_window_ms {
                    *last = now_ms;
                    true
                } else {
                    false
                }
            })
            .unwrap_or(true);

        if should_log {
            self.emit_cost_edge_reject_log(strategy, ratio, effective_threshold,
                                            state.triggered_at_ms, now_ms);
        }

        Some(RejectionCode::CostEdgeAdvisorTrigger {
            ratio,
            threshold: effective_threshold,
            triggered_at_ms: state.triggered_at_ms,
        }.format())
    }
}
```

**關鍵 invariants（E2 必查）**：
1. **Reject decision 不被 dedup 影響** — 每個進來的新倉（非 reducing）都被 reject；dedup 僅控 log 寫入頻率
2. **`is_reducing == true` 完全跳過** — Gate 1.7 之前已判定 reducing 路徑直接 skip 整個 gate
3. **WarmUp / Stale / Anomaly 一律放行** — fail-open on uncertainty（advisor 沒辦法判斷時不阻新倉，否則 advisor 半死等於系統凍結，違反 #11 Agent 自主權）
4. **Per-strategy override 比對方向**：`override < cfg.trigger_threshold`（更嚴格）→ 該策略更早觸發；`override > cfg.trigger_threshold` → 該策略容忍更高 burn — validate 拒 `> 0.0`（threshold 必為負，loss 才 negative）

---

## §3 Reject 條件邏輯細節

### 3.1 三層判定

```
Layer 1: gate_enabled flag (RiskConfig.cost_edge.gate_enabled)
         ├─ false → pass (Phase A/B 行為)
         └─ true  → 進入 Layer 2

Layer 2: per-strategy exempt
         ├─ StrategyOverride.cost_edge_exempt == true → pass
         └─ false → 進入 Layer 3

Layer 3: ratio breach OR portfolio Trigger
         ├─ advisor.ratio is None / Stale / Anomaly → pass (fail-open uncertainty)
         ├─ ratio <= effective_threshold → REJECT
         ├─ status == Trigger → REJECT
         └─ otherwise → pass
```

### 3.2 Per-strategy 場景

| 場景 | 配置 | 結果 |
|---|---|---|
| 全局 Trigger，策略無 override | gate_enabled=true, override=None | reject（用 portfolio threshold） |
| 全局 OK 但策略 burn 嚴重 | override=-0.3 (更嚴), gate_enabled=true | 該策略 -0.3 触發，其他 OK |
| Emergency exit 策略豁免 | cost_edge_exempt=true | 永不 reject（即使 portfolio Trigger） |
| risk_off 場景 | 全策略 cost_edge_exempt=true 預設 | rollout 過渡期保護 |

### 3.3 Dedup window 細節

**問題**：advisor 持續處於 Trigger 數小時 → IntentProcessor 每 tick (10ms-100ms) 看到 intent → 每次都 INSERT reject log → DB 寫入失控。

**設計**：
- `dedup_window_ms` 預設 `60_000`（60s）
- IntentProcessor 持 `cost_edge_last_reject_log_ms: Option<Arc<Mutex<i64>>>`（Option 因 advisor 未 wire 時為 None）
- 每次 reject decision 確定後，比對 `now - last_reject_ms`：
  - >= dedup_window_ms → INSERT log 寫 V026 row，update `last_reject_ms`
  - < dedup_window_ms → skip log，但 reject decision 不變
- **counter 走 IPC counter**（IntentProcessor 內 `cost_edge_reject_24h: VecDeque<i64>`）：所有 reject 不論 log 寫不寫都 +1，rolling 24h trim
- IPC `get_cost_edge_advisor_status` 增 `reject_24h: u64` field（forward-compat `#[serde(default)]`）

**為何不每個 reject 都 INSERT**：
- 每 tick reject = 100-1000 INSERT/sec → DB 必爆
- 既然 dedup 後仍知道 reject 數量（IPC counter），log 1/min sample 已足診斷
- transition INSERT 仍由 advisor daemon 維護（Phase B），gate 不重複 daemon 工作

### 3.4 Per-strategy / per-symbol exemption 機制

| 機制 | 用途 | 配置 |
|---|---|---|
| `cost_edge_exempt: bool` | 策略級永久豁免（emergency exit / risk-off / market-maker 高頻） | `StrategyOverride.cost_edge_exempt = true` |
| `cost_edge_threshold_override: Option<f64>` | 策略級 threshold 個別校準（更嚴 or 更鬆，但 validate 拒 > 0.0） | `StrategyOverride.cost_edge_threshold_override = Some(-0.3)` |
| `gate_enabled = false` | 全局退回 Phase B 觀察期（系統凍結風險時 60s rollback） | IPC `patch_risk_config` flip false |
| `enabled = false` | 整個 advisor dormant（最終手段） | IPC flip false（daemon 退 Disabled state） |

**Per-symbol 不做**：
- 既有 `StrategyOverride.allowed_symbols / blocked_symbols` 已可達等效（策略 + 黑名單組合），重複設計
- per-symbol cost_edge 缺資料源 — H5 cost_edge_ratio 是 portfolio-level，不是 per-symbol（per-symbol ratio 屬 H5 升級工作，Phase D / G3-09 後續）

---

## §4 Reject 後行為

### 4.1 IntentProcessor 回 IntentResult

```rust
IntentResult {
    submitted: false,
    rejected_reason: Some("cost_edge_advisor_trigger: ratio=-0.62 threshold=-0.50 triggered_at_ms=1740..."),
    fill: None,
    verdict_info: Some(VerdictInfo::rejected(reason.clone())),  // 寫 trading.risk_verdicts
    approved_qty: 0.0,
    resting_order: None,
    maker_degraded_fallback: None,
}
```

**RejectionCode 新增**（`intent_processor/rejection_coding.rs`）：

```rust
pub(super) enum RejectionCode {
    // ... existing variants ...

    /// G3-09 Phase C: cost_edge_advisor portfolio-level Trigger or per-strategy
    /// threshold breach; new opens rejected, closes/reductions still allowed.
    /// G3-09 Phase C：cost_edge_advisor 觸發或策略門檻破，僅阻新倉。
    CostEdgeAdvisorTrigger {
        ratio: f64,
        threshold: f64,
        triggered_at_ms: i64,
    },
}

impl RejectionCode {
    pub(super) fn format(&self) -> String {
        match self {
            // ...
            Self::CostEdgeAdvisorTrigger { ratio, threshold, triggered_at_ms } => format!(
                "cost_edge_advisor_trigger: ratio={:.4} threshold={:.4} triggered_at_ms={}",
                ratio, threshold, triggered_at_ms
            ),
        }
    }

    pub(super) fn is_cost_edge_reject(&self) -> bool {
        matches!(self, Self::CostEdgeAdvisorTrigger { .. })
    }
}
```

字串前綴 `cost_edge_advisor_trigger:` 為 audit grep / Python downstream switch 提供穩定錨點。

### 4.2 Audit log 寫入

**雙寫**（per Phase A 既有 audit pattern）：
1. `trading.risk_verdicts` — Guardian 標準路徑（VerdictInfo::rejected）
2. `learning.cost_edge_advisor_log` — V026 hypertable（重用 Phase B schema）：
   - `transition_from = "GATE_REJECT"` 字串標記（distinguish 觀察 cycle row vs gate reject row）
   - `status = "Trigger"`（gate 只在 Trigger 時 reject）
   - `ratio` / `threshold` / `data_days` 等照 V026 欄位 fill
   - dedup window 控制 INSERT 頻率（per §3.3）

**`transition_from` 重用 GATE_REJECT 標記的合理性**：
- V026 schema `transition_from TEXT NULL`，目前 Phase B 只填 status enum string（如 'OK' for OK→Trigger transition）
- Phase C 新增 `'GATE_REJECT'` 為非 status enum 值，下游 query 可用 `WHERE transition_from = 'GATE_REJECT'` 切出 reject row
- 若 PM 後續需嚴格區分（避 transition_from 多語意），可加 `entry_kind: TEXT` column，本 RFC 推遲到 V027

### 4.3 Intent_id 標記（Audit trail）

Python ExecutorAgent → IPC SubmitOrder → Rust IntentProcessor 路徑下，intent 帶 `intent_id`（per ARCH-1 dedup window）。Phase C reject log 寫入時應 capture intent_id 供 audit trail 追溯。

**做法**：`OrderIntent` schema 加 `#[serde(default)] intent_id: Option<String>`（forward-compat），IntentProcessor reject 寫 V026 row 時帶入。**本 RFC 不展開 OrderIntent schema 變更**（屬 G3-03 / G8-01 範疇），Phase C 用 `strategy::symbol::ts_ms` 三元組作為 quasi-unique key 替代，待 OrderIntent intent_id 落地後 follow-up 加欄。

### 4.4 GUI surface（Phase C 不做）

**留 future ticket**：
- `G3-09-PHASE-C-FUP-GUI-REJECT-DASHBOARD P3` — Phase D 工作，GUI Tab 顯示 24h reject count + per-strategy 分布 + 最近 reject sample
- 本 RFC 只提供 IPC counter (`reject_24h`) 讓 GUI Phase D 接

---

## §5 Env-gate dual safeguard

### 5.1 三層保險（per Phase A pattern）

```
Layer 1: env var OPENCLAW_COST_EDGE_ADVISOR=1 (Phase A 已就位)
         └─ daemon 是否 spawn

Layer 2: RiskConfig.cost_edge.enabled = true (Phase A 已就位)
         └─ daemon 是否 evaluate（false → 短路 Disabled state）

Layer 3: ★ NEW RiskConfig.cost_edge.gate_enabled = true (Phase C)
         └─ IntentProcessor 是否 reject（false → Phase A/B 行為，advisor 仍 emit log 但 gate dormant）
```

**為何三層而非兩層**：
- env=1 + enabled=true 是 Phase B observation 啟動條件，必須先就位才會有 ratio histogram + trigger frequency 證據
- gate_enabled=true 是 Phase C 啟動條件，**獨立於** observation flag — 允許 operator 在 advisor 持續觀察的同時 flip gate（不必再先 enabled=false 切回 Phase A）
- 三層解耦 = rollback 路徑簡單（每層獨立 flip）

### 5.2 Default = false

per CLAUDE.md §二 #6（失敗默認收縮）：
- `gate_enabled: bool` default `false` — Phase C deploy 後若不 flip flag，IntentProcessor 行為與 Phase B 完全一致（0 reject）
- `cost_edge_threshold_override: Option<f64>` default `None` — per-strategy 不啟用即 fall back portfolio threshold
- `cost_edge_exempt: bool` default `false` — 不豁免（gate 啟用後所有非 reducing 策略受 gate 管轄）

### 5.3 Validate 約束

`RiskConfig::validate()` 加：
- `dedup_window_ms` ∈ `[1_000, 3_600_000]`（1s ~ 1h），預設 60_000
- `cost_edge_threshold_override` 若 Some 必為 finite + ∈ `[-100.0, 100.0]`（同 portfolio threshold 範圍）
- `gate_enabled = true` 必須 `enabled = true`（不能 gate enabled 但 advisor disabled）
- 啟動時若 `gate_enabled = true` 但無 advisor wired（env=0 spawn 失敗）→ `validate()` warn-log 但不 fail（fail-open，避免 startup death loop）

---

## §6 IntentProcessor changes vs ExecutorAgent changes

### 6.1 主要工作量分布

| 層 | 改動量 | 說明 |
|---|---|---|
| **Rust IntentProcessor** | ~250 LOC | gate 邏輯 + RejectionCode + 調用點注入 + setter for advisor snapshot |
| **Rust RiskConfig schema** | ~80 LOC | gate_enabled / dedup_window_ms / per-strategy override + validate |
| **Rust IntentProcessor tests** | ~250 LOC | unit tests for gate 邏輯 + dedup + exempt |
| **Rust integration test** | ~150 LOC | IntentProcessor → gate → reject log row |
| **Python ExecutorAgent** | **0 LOC** | 既有 `rejected_reason` 欄位即可承接，下游 log 已通用 |
| **Python downstream** | ~30 LOC | 在 ExecutorAgent reject metrics 加 `cost_edge_reject_count` counter（optional，Phase C 可不做） |
| **SQL** | 0 行（V027 不必） | 重用 V026 hypertable 加 `transition_from = 'GATE_REJECT'` |
| **Healthcheck** | ~80 LOC | 新增 `[31] cost_edge_gate_reject_freq`（rollout 期觀察 reject 流量） |
| **Config TOML** | ~6 行 × 3 env | `gate_enabled = false` 默認注三 env |

**ExecutorAgent 0 改動的 evidence**（從 `executor_agent.py:495-507`）：

```python
rejected_reason = result.get("rejected_reason") if isinstance(result, dict) else None
# ...
if rejected_reason:
    return ExecutionResult(
        # ...
        error=f"Order rejected: {rejected_reason}",
    )
```

ExecutorAgent 已 fully generic 處理 IPC 回的 `rejected_reason` 欄位，只要 Rust 把字串塞回去就完成。Phase C 唯一 Python 工作是加 1 個 metric counter（optional），用於 Operator dashboard 可見度。

### 6.2 為何不在 ExecutorAgent 注入額外邏輯

- Rust path 的 strategy → IntentProcessor 直發 intent 不經 ExecutorAgent — 在 ExecutorAgent 注入會漏 gate
- ExecutorAgent shadow_mode=True 預設下根本不發 SubmitOrder IPC（per `executor_agent.py:611-636`），Phase C gate 在 Rust 才有 100% intent coverage
- ExecutorAgent 新增邏輯 = uvicorn restart deploy；Rust 改動 = engine `--rebuild` deploy；只動 Rust 簡化 deploy

### 6.3 Phase B RFC §6.1 R-B6「IntentProcessor would_reject_intent shadow check」決議

Phase B RFC 明確標 R-B6 屬 Phase C scope。本 RFC 決議：**不做 shadow check 這一步**，直接 binding gate（為何）：

1. Phase B observation period 已提供等價證據（ratio histogram + trigger frequency + per-status distribution）— shadow check 提供的「假設 reject N intent / day」是次級 metric，可從 observation report 推導（`triggers_24h × intent_rate`）
2. 多一個 shadow stage = 多一週 observation + PM sign-off — Phase A→B→C-shadow→C-binding 四 phase 過長，operator UX 差
3. shadow check 改動 IntentProcessor hot path（即使 pure fn 也要 advisor.snapshot() lookup）— 與 binding gate 同等成本，多此一舉
4. dedup_window_ms + gate_enabled=false 預設已是「shadow」等價：deploy 後 0 reject，Operator 觀察 advisor state 滿意後 flip gate_enabled=true 即從 shadow → binding

→ Phase C 直接做 binding gate + dedup + exemption 三件事，跳過獨立 shadow stage。

---

## §7 回滾路徑（90s SOP）

鏡 EDGE-P2-flip pattern + Phase A IPC patch 路徑：

### 7.1 場景 A：reject spam（threshold 過嚴 / advisor false trigger）

```
Operator action (≤90s):
  1. 看 healthcheck [31] FAIL: reject_per_hour > 50
  2. ssh trade-core "curl -X POST <ipc>/patch_risk_config \
     --data '{\"cost_edge\":{\"gate_enabled\":false}}'"
  3. 60s 內 IntentProcessor 下次 risk_config sync 看到 gate_enabled=false → gate dormant
  4. healthcheck [31] 在下次 cron (6h) 自動回 PASS
  5. Operator 後續調 trigger_threshold or per-strategy override，再 flip gate_enabled=true
```

### 7.2 場景 B：advisor stuck Trigger（系統凍結）

```
Operator action (≤90s):
  1. 看 healthcheck [30] WARN: trigger lasting > 1h continuous
  2. 同上 ipc patch_risk_config gate_enabled=false
  3. 進階：若 advisor 本身 buggy，再 patch enabled=false 完全 dormant
  4. Engine restart 不必（IPC 60s 生效）
```

### 7.3 場景 C：per-strategy false-positive（單策略 burn 但其他 OK）

```
Operator action:
  1. patch per_strategy.<bad_strategy>.cost_edge_exempt=true
  2. 該策略立即繞過 gate，其他策略繼續受 gate 管轄
  3. 後續 root cause 該策略 PnL，再決定 unexempt
```

### 7.4 場景 D：完全災難回滾（Phase B 行為復原）

```
Engine restart with env var unset:
  unset OPENCLAW_COST_EDGE_ADVISOR
  bash helper_scripts/restart_all.sh --rebuild
  → daemon 不 spawn，advisor 全 dormant，gate 自動 pass-through
```

---

## §8 Test 規劃

### 8.1 Rust unit tests (intent_processor/tests.rs 新章節)

```
mod cost_edge_gate_tests {
  // gate_enabled=false → pass (advisor Trigger 也不擋)
  fn test_gate_dormant_when_flag_false()

  // gate_enabled=true + advisor None → pass (advisor not wired)
  fn test_gate_pass_when_advisor_unwired()

  // gate_enabled=true + advisor Trigger + non-reducing → reject
  fn test_gate_rejects_new_open_when_trigger()

  // gate_enabled=true + advisor Trigger + is_reducing → pass
  fn test_gate_passes_close_when_trigger()

  // gate_enabled=true + advisor Trigger + cost_edge_exempt=true → pass
  fn test_gate_respects_exempt_flag()

  // per-strategy threshold override stricter → reject before portfolio Trigger
  fn test_per_strategy_threshold_overrides()

  // advisor WarmUp / Stale / Anomaly → pass (fail-open uncertainty)
  fn test_gate_fail_open_on_uncertainty()

  // dedup window: 60 reject in 60s → only 1 INSERT log, but 60 reject decision
  fn test_dedup_window_logs_once()

  // dedup window expired: next reject INSERTs again
  fn test_dedup_window_expiry()

  // 24h rolling reject counter
  fn test_reject_counter_24h_rolling()
}
```

### 8.2 Rust integration test (`tests/cost_edge_gate_integration.rs`)

- spawn daemon (env=1 + enabled=true) → mock H5 cost_edge_ratio = -0.7 → wait for advisor.status = Trigger
- IntentProcessor.process(non-reducing intent) → assert IntentResult.submitted = false + rejected_reason starts_with "cost_edge_advisor_trigger:"
- IntentProcessor.process(reducing intent) → assert submitted = true (reducing not blocked)
- query `learning.cost_edge_advisor_log` WHERE transition_from='GATE_REJECT' → 1 row exists
- patch_risk_config gate_enabled=false → next process(non-reducing) submitted = true within 60s

### 8.3 Python integration test (control_api_v1)

- ExecutorAgent.execute_intent(intent) → SubmitOrder IPC → mock Rust reject `rejected_reason="cost_edge_advisor_trigger: ..."`
- assert ExecutionResult.error contains "cost_edge_advisor_trigger"
- assert metric counter `cost_edge_reject_count` += 1（若加 counter）

### 8.4 E4 Linux smoke (gate enabled)

- Demo engine restart with env=1
- IPC patch `enabled=true, gate_enabled=true, trigger_threshold=-0.3`（更鬆 threshold，迫 trigger 進入 reject）
- 觀察 1h：
  - healthcheck [30] PASS / WARN（不 FAIL）
  - healthcheck [31] (新增) reject_per_hour 在合理範圍（< 20/hr）
  - learning.cost_edge_advisor_log WHERE transition_from='GATE_REJECT' rows exist
- IPC patch gate_enabled=false → 60s 內 reject 停止

### 8.5 跨環境 smoke

- paper / demo / live engine 各自重啟啟用 gate，驗 reject 行為一致
- live mainnet **禁啟用**（Phase A RFC §8.3 鎖死，Operator 顯式批准 + ≥7d demo 觀察通過才考慮）

---

## §9 Wave 拆分

### 9.1 推薦 3 Wave

```
Wave 1 (Rust intent gate logic + log row + RejectionCode + RiskConfig schema)
  - E1: ~2d (estimated)
  - 改動：
    * config/risk_config_cost_edge.rs (+gate_enabled +dedup_window_ms +validate)
    * config/risk_config_per_strategy.rs (+cost_edge_threshold_override +cost_edge_exempt)
    * intent_processor/mod.rs (持 cost_edge_advisor: Option<Arc<CostEdgeAdvisor>> + setter)
    * intent_processor/router.rs (Gate 1.7 注入)
    * intent_processor/gates.rs (check_cost_edge_gate impl)
    * intent_processor/rejection_coding.rs (+CostEdgeAdvisorTrigger variant)
    * intent_processor/tests.rs (+10 unit tests)
    * tests/cost_edge_gate_integration.rs (1 file, ~150 LOC)
    * tick_pipeline/pipeline_ctor.rs (set_cost_edge_advisor wire)
    * settings/risk_config_{paper,demo,live}.toml (gate_enabled = false default)
  - Acceptance: cargo lib +12-15 tests / 0 failed (baseline 2299)
  - 依賴：Phase B already landed (advisor.snapshot() API + DbPool slot 重用)

Wave 2 (Python ExecutorAgent metric + GUI surface stub)
  - E1: ~1d
  - 改動：
    * executor_agent.py: 加 `cost_edge_reject_count: int` snapshot field (parse rejected_reason starts_with "cost_edge_advisor_trigger:")
    * 新 IPC handler get_cost_edge_advisor_status 增 `reject_24h` field consumer
    * GUI Tab 7 (Risk Dashboard) 加 1 個 sparkline (stub, future ticket Wave 4)
  - Acceptance: pytest +5 tests / 0 failed
  - 依賴：Wave 1 RejectionCode 字串前綴穩定

Wave 3 (Linux deploy + gate enabled smoke + observation period)
  - E4: ~0.5d active + ~7d passive observation
  - 工作：
    * --rebuild deploy Wave 1+2 改動到 demo engine
    * IPC patch_risk_config 啟用 gate_enabled=true (demo only)
    * cron 6h healthcheck [30] + [31] + [32] (新 reject freq)
    * 7d 觀察期 deliverable: docs/audits/YYYY-MM-DD--cost_edge_phase_c_observation.md
  - Live mainnet enable PM sign-off (Phase A RFC §8.3 checklist)
```

### 9.2 並行性

- Wave 1 + Wave 2 **可並行**（前提：Wave 1 RejectionCode 字串前綴 `cost_edge_advisor_trigger:` 鎖死契約，Wave 2 用此契約解析）
- Wave 3 **必須等** Wave 1+2 全綠

### 9.3 Wave 1 內部子任務（給單一 E1，不並行 — 改動互相依賴）

```
1.1 RiskConfig schema (cost_edge.gate_enabled / dedup_window_ms / per_strategy override)
    + validate
1.2 RejectionCode::CostEdgeAdvisorTrigger variant + format() + is_cost_edge_reject helper
1.3 IntentProcessor 持 advisor snapshot setter + cost_edge_last_reject_log_ms cell
1.4 IntentProcessor.check_cost_edge_gate() impl + dedup + exempt + override
1.5 router.rs Gate 1.7 注入點
1.6 emit_cost_edge_reject_log（V026 INSERT path）+ IPC counter
1.7 unit tests (10+)
1.8 integration test (1 file)
1.9 TOML 三 env default
```

順序強耦合：1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 1.7 → 1.8 → 1.9。

---

## §10 風險清單

### 10.1 風險矩陣

| # | 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|---|
| **R-C1** | False-positive reject 平倉（误判 reducing） | 低 | **高**（trade impact 極差） | (a) `is_reducing` 邏輯複用 Gate 2.7 既有 path（已產品化驗證）(b) Gate 1.7 早於 Guardian 但 Guardian 不關此判定 (c) unit test `test_gate_passes_close_when_trigger` 釘住 (d) E2 必查 Gate 1.7 之前 `is_reducing` 計算正確性 |
| **R-C2** | Dedup window 太短 → reject spam 撐爆 V026 | 低 | 中 | (a) 預設 60s 已 down-sample (b) 真實 reject 即使 1 hr 持續，也只 60 row/hr (c) hypertable 30d retention 自動清 (d) V026 `transition_from='GATE_REJECT'` 與 cycle row 同表共 retention |
| **R-C3** | Dedup window 太長 → 真信號被 dedup 漏記 | 低 | 低 | (a) Reject decision 不被 dedup 影響（每個 intent 仍 reject）(b) IPC counter `reject_24h` 始終準確（無 dedup）(c) 漏的只是 log 採樣，counter 仍可診斷 |
| **R-C4** | Per-strategy override 邏輯複雜 → bug 難發現 | 中 | 中 | (a) override schema 簡單 2 field (`threshold_override` + `exempt`) (b) validate 鎖 threshold 範圍 (c) unit test 覆蓋 override + exempt 組合 (d) Phase C 預設無策略 override / exempt，rollout 後 operator 手動加才生效 |
| **R-C5** | Live 階段 mainnet 提早啟用 → 真實虧損 | 低 | **高** | (a) Phase A RFC §8.3 已鎖 Operator 顯式批准 + ≥7d demo Phase B 觀察通過 (b) live mainnet TOML 預設 `gate_enabled=false` 不在 Phase C 自動 flip (c) 觸到 live 5 項硬邊界 0 條 |
| **R-C6** | gate_enabled=true 後 system 凍結（advisor stuck Trigger） | 低 | **高** | (a) IPC 60s rollback 路徑（§7） (b) healthcheck [30] WARN at 1h continuous Trigger (c) per-strategy exempt fast escape (d) Phase B observation 已提供 trigger frequency baseline，過嚴 threshold 在 Phase C 啟動前已知 |
| **R-C7** | Rust IntentProcessor 持 advisor snapshot 的 race condition（advisor restart 時 None） | 低 | 低 | (a) `Option<Arc<CostEdgeAdvisor>>` setter pattern（同 risk_config snapshot pattern）(b) `as_ref()?` early return 走 fail-open path |
| **R-C8** | 與 cost_gate (per-intent EV) 雙 reject → audit 混淆 | 低 | 低 | (a) RejectionCode prefix `cost_edge_advisor_trigger:` vs `cost_gate(JS):*` 字面區分 (b) classification helper `is_cost_edge_reject()` vs `is_cost_gate_reject()` (c) two gates 設計上 AND 條件（per Phase A RFC §6 R6） |
| **R-C9** | RiskConfig.gate_enabled=true + cost_edge.enabled=false（不一致狀態） | 低 | 中 | validate 強制 `gate_enabled=true → enabled=true`，否則 RAISE |
| **R-C10** | rollout 期 reject 衝擊既有 demo 策略（觀察期內 reject 過多） | 中 | 中 | (a) Wave 3 demo only enable，live 不動 (b) healthcheck [31] FAIL at reject_per_hour > 50 → operator 立即 rollback (c) 7d observation deliverable PM 審核 |

### 10.2 Top 3 風險細解

#### R-C1 False-positive reject 平倉

**情境**：Gate 1.7 注入點誤判 reducing 為 new entry → reject 平倉 intent → 該倉位無法平 → margin call 連鎖。

**緩解三防線**：
1. **複用既有 `is_reducing` 計算邏輯**（Gate 2.7 已驗證，多年 paper/demo 通過）
2. **Gate 1.7 之前計算 `is_reducing` 並記錄**：
   ```rust
   let is_reducing = paper_state.get_position(&intent.symbol)
       .map(|p| p.is_long != intent.is_long)
       .unwrap_or(false);
   if !is_reducing {  // GATE 1.7 only fires for new opens
       if let Some(reason) = self.check_cost_edge_gate(&intent.strategy) {
           return IntentResult::rejected(reason);
       }
   }
   ```
3. **Unit test 釘死**：`test_gate_passes_close_when_trigger` + `test_gate_passes_reduce_when_trigger`

#### R-C5 Live mainnet 提早啟用

**情境**：Operator 在 demo 觀察未滿 7d 即在 live mainnet 啟用 → 真實虧損 + 違反 Phase A RFC §8.3。

**緩解四道線**：
1. live mainnet TOML `gate_enabled = false` default（Phase C 改動 0 自動 flip）
2. Phase A RFC §8.3 Operator checklist 明確列 demo Phase B ≥7d 觀察 + reject_per_hour 在合理範圍
3. live mainnet IPC patch_risk_config 路徑與 demo 共用，但 RiskConfig audit log 會顯示 patch source — 非 Operator 顯式 patch 不可能 flip
4. PM sign-off 流程（Wave 3 Phase C deliverable PM approve → Operator manual SOP step）

#### R-C6 gate_enabled=true 後系統凍結

**情境**：advisor 持續 Trigger 數小時 → 所有非 exempt 策略無法開新倉 → 系統實質凍結 → Agent 自主權喪失（違反 #11）。

**緩解四防線**：
1. **IPC 60s rollback**（§7）— Operator 看到 healthcheck WARN 立即 patch gate_enabled=false
2. **healthcheck [30] WARN at 1h continuous Trigger**（Phase B 已就位 + Phase C 加 [31]）
3. **per-strategy exempt fast escape** — operator 可以針對單策略 patch exempt=true 立即繞過
4. **Phase B observation 預先校準** — Phase C 啟動前 Operator 已從 Phase B deliverable 知道真實 trigger frequency；threshold 過嚴在 Phase B 階段就應已 calibrate

---

## §11 §11 Self-contained E1 prompt template — Wave 1（Rust intent gate）

**派發給**：E1 (Rust 寫碼)
**isolation**：NOT 需要（單實例操作多檔，但檔案無重疊風險）
**branch**：直接 main work tree

---

````markdown
## 任務：G3-09 Phase C Wave 1 — cost_edge_advisor IntentProcessor gate (Rust binding reject 新倉)

### 背景

PA RFC `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_phase_c_intent_gate_design.md`
landed on HEAD `decf712`（2026-04-28）。Phase A advisor + Phase B observability
已 land。Phase C Wave 1 範圍 = 在 IntentProcessor 注入 cost_edge gate，當
advisor.status == Trigger 且 RiskConfig.cost_edge.gate_enabled=true 時 reject
新倉 SubmitOrder（不阻平倉、減倉），重用 Phase B V026 hypertable 寫 reject log。

**Phase C 第一次 trade impact != 0**（gate flip 後 reject 真實新倉）。但 default
`gate_enabled=false` → Wave 1 deploy 後若不 flip flag，IntentProcessor 行為與 Phase
B 完全一致（0 reject）。Wave 3 由 Operator 手動 IPC patch_risk_config 啟用。

### 前置驗證（開工前必跑）

```bash
# Phase B Wave 1 已 land
git log --oneline -10 | grep "G3-09 Phase B" || echo "ERROR Phase B not landed"

# Phase B baseline cargo lib
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib 2>&1 | tail -3"
# 預期：2299 passed / 0 failed

# Phase B V026 已套用
ssh trade-core "psql -d openclaw -c '\d learning.cost_edge_advisor_log'" | head -5
# 預期：表存在含 transition_from column
```

### 改動文件（修改 6 + 新建 1）

#### 修改

1. `rust/openclaw_engine/src/config/risk_config_cost_edge.rs`
   - `CostEdgeConfig` struct 加：
     - `pub gate_enabled: bool`（`#[serde(default)]` default false）
     - `pub dedup_window_ms: i64`（`#[serde(default = "default_dedup_window_ms")]` default 60_000）
   - `default_cost_edge_gate_enabled() -> bool { false }`
   - `default_dedup_window_ms() -> i64 { 60_000 }`
   - `validate()` 新增：
     - `dedup_window_ms ∈ [1_000, 3_600_000]`
     - `gate_enabled=true → enabled=true`（否則 Err）
   - 估 ~50 LOC

2. `rust/openclaw_engine/src/config/risk_config_per_strategy.rs`
   - `StrategyOverride` 加：
     - `pub cost_edge_threshold_override: Option<f64>`（`#[serde(default)]`）
     - `pub cost_edge_exempt: bool`（`#[serde(default)]` default false）
   - `validate_against_limits()` 加 cost_edge_threshold_override 範圍檢查（finite + ∈ [-100.0, 100.0]）
   - 估 ~40 LOC

3. `rust/openclaw_engine/src/intent_processor/rejection_coding.rs`
   - `RejectionCode` enum 加：
     ```rust
     CostEdgeAdvisorTrigger {
         ratio: f64,
         threshold: f64,
         triggered_at_ms: i64,
     },
     ```
   - `format()` 新分支輸出 `"cost_edge_advisor_trigger: ratio={:.4} threshold={:.4} triggered_at_ms={}"`
   - 加 `is_cost_edge_advisor_reject() -> bool` helper
   - 估 ~30 LOC

4. `rust/openclaw_engine/src/intent_processor/mod.rs`
   - `IntentProcessor` struct 加：
     - `cost_edge_advisor: Option<Arc<crate::cost_edge_advisor::CostEdgeAdvisor>>`
     - `cost_edge_last_reject_log_ms: Option<Arc<parking_lot::Mutex<i64>>>`
     - `cost_edge_reject_24h: Arc<parking_lot::Mutex<std::collections::VecDeque<i64>>>` (rolling counter)
     - `cost_edge_db_pool: Option<Arc<crate::database::pool::DbPool>>` (V026 INSERT path)
   - `new()` / `with_fee_rate()` 初始化新欄位為 None / empty
   - 加 setter:
     - `pub fn set_cost_edge_advisor(&mut self, advisor: Arc<...>)`
     - `pub fn set_cost_edge_db_pool(&mut self, pool: Arc<DbPool>)`
   - `IntentResult::rejected_with_verdict_kind` helper（optional refactor）
   - 估 ~80 LOC

5. `rust/openclaw_engine/src/intent_processor/gates.rs`
   - 新方法 `check_cost_edge_gate(&self, strategy: &str) -> Option<String>`（per RFC §2.3）
   - 新方法 `emit_cost_edge_reject_log(&self, strategy, ratio, threshold, triggered_at_ms, now_ms)` — tokio::spawn fire-and-forget V026 INSERT，`transition_from='GATE_REJECT'`，`status='Trigger'`，重用 Phase B INSERT pattern
   - 新方法 `record_cost_edge_reject(&self, now_ms)` — push to VecDeque + trim 24h
   - 估 ~140 LOC

6. `rust/openclaw_engine/src/intent_processor/router.rs`
   - 在 Gate 1.6 後、Gate 2 之前注入 Gate 1.7：
     ```rust
     // Gate 1.7: G3-09 Phase C cost_edge_advisor gate (new entries only)
     let is_reducing = paper_state.get_position(&intent.symbol)
         .map(|p| p.is_long != intent.is_long)
         .unwrap_or(false);
     if !is_reducing {
         if let Some(reason) = self.check_cost_edge_gate(&intent.strategy) {
             return IntentResult::rejected(reason);
         }
     }
     ```
   - 同樣注入 `process_gates_only_with_features` 路徑（exchange mode）
   - 估 ~30 LOC（兩處注入點）

7. `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs`
   - 加 `pub fn set_cost_edge_advisor(&mut self, advisor)` 委派給 self.intent_processor.set_cost_edge_advisor
   - 加 `pub fn set_cost_edge_db_pool(...)` 同上
   - 估 ~20 LOC

8. `settings/risk_config_paper.toml` / `risk_config_demo.toml` / `risk_config_live.toml`
   - `[cost_edge]` section 加：
     ```toml
     gate_enabled = false  # G3-09 Phase C — Operator IPC patch enable; default false per CLAUDE.md §二 #6
     dedup_window_ms = 60000
     ```
   - 估 ~6 行 × 3 env

#### 新建

9. `rust/openclaw_engine/tests/cost_edge_gate_integration.rs`
   - 至少 3 integration test:
     - `gate_rejects_new_open_when_advisor_trigger`
     - `gate_passes_close_when_advisor_trigger`
     - `gate_passes_when_flag_disabled_even_if_trigger`
     - `gate_dedup_window_logs_once_in_60s`
     - `gate_per_strategy_exempt_bypasses`
   - 估 ~250 LOC

#### 修改 (內部 unit tests)

10. `rust/openclaw_engine/src/intent_processor/tests.rs`
    - 加 `mod cost_edge_gate_tests` 子模組（per RFC §8.1 全 10 test）
    - 估 ~250 LOC

### 具體實作要點

#### Gate 注入點（router.rs）

完整 diff sketch:

```rust
// 既有 router.rs 第 73-74 行（Gate 1.6 結束）後插入：

// ─── Gate 1.7: G3-09 Phase C cost_edge_advisor gate (new entries only) ───
// Reject new opens when advisor.status == Trigger AND gate_enabled.
// Reducing/closing intents pass through (CLAUDE.md §二 #5 生存>利潤).
// G3-09 Phase C：cost_edge advisor gate 阻新倉；平倉/減倉放行。
let is_reducing_for_cost_edge = paper_state
    .get_position(&intent.symbol)
    .map(|p| p.is_long != intent.is_long)
    .unwrap_or(false);
if !is_reducing_for_cost_edge {
    if let Some(reason) = self.check_cost_edge_gate(&intent.strategy) {
        return IntentResult::rejected(reason);
    }
}
```

注：此 `is_reducing_for_cost_edge` 計算與 Gate 2.7 內部 `is_reducing` 重複；
Phase C 不重構（保 minimal diff），future ticket 提取為 helper。

#### Reject log INSERT（gates.rs）

```rust
fn emit_cost_edge_reject_log(
    &self,
    strategy: &str,
    ratio: f64,
    threshold: f64,
    triggered_at_ms: i64,
    now_ms: i64,
) {
    let pool = match self.cost_edge_db_pool.as_ref() {
        Some(p) => p.clone(),
        None => return, // DB not wired (test path / engine startup race) → skip log
    };
    let advisor = match self.cost_edge_advisor.as_ref() {
        Some(a) => a.clone(),
        None => return,
    };
    let strategy = strategy.to_string();
    let engine_mode = self.effective_engine_mode().to_string();

    tokio::spawn(async move {
        // Pull current advisor state for completeness
        let state = advisor.snapshot();
        let res = sqlx::query(
            "INSERT INTO learning.cost_edge_advisor_log \
             (ts_ms, engine_mode, status, ratio, threshold, data_days, \
              ai_spend_7d_usd, paper_pnl_7d_usd, is_stale, phase, transition_from) \
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
             ON CONFLICT (ts_ms, engine_mode) DO NOTHING"
        )
        .bind(now_ms)
        .bind(&engine_mode)
        .bind("Trigger")
        .bind(ratio)
        .bind(threshold)
        .bind(state.data_days as i32)
        .bind(state.ai_spend_7d_usd)
        .bind(state.paper_pnl_7d_usd)
        .bind(matches!(state.status, CostEdgeAdvisorStatus::Stale))
        .bind("C_gate")
        .bind(format!("GATE_REJECT:{}", strategy)) // strategy in transition_from for filter
        .execute(&pool).await;
        if let Err(e) = res {
            tracing::warn!(error=%e, strategy=%strategy,
                "cost_edge_gate reject log INSERT failed");
        }
    });
}
```

注：`transition_from` field 在 Phase B 是 status enum string；Phase C 用
`'GATE_REJECT:<strategy>'` 字面前綴避免與 status enum 撞。下游 query
`WHERE transition_from LIKE 'GATE_REJECT:%'` 切出 reject row。

### Acceptance criteria

#### Rust
- [ ] cargo test --lib **+13-15 tests / 0 failed**（baseline 2299 → 2312-2314）
- [ ] cargo test --release tests/cost_edge_gate_integration ≥5 通過
- [ ] RiskConfig.cost_edge.gate_enabled / dedup_window_ms forward-compat（既有 Phase A/B TOML 不加新 field 也能 deserialise，default 接管）
- [ ] StrategyOverride.cost_edge_threshold_override / cost_edge_exempt forward-compat
- [ ] gate_enabled=false default → IntentProcessor 行為與 Phase B 完全一致（0 reject path 觸發）

#### TOML
- [ ] paper/demo/live 三 env risk_config_*.toml `[cost_edge]` section 含 gate_enabled=false + dedup_window_ms=60000
- [ ] hot-reload smoke：IPC patch_risk_config gate_enabled=true → 60s 內 IntentProcessor 行為改變

#### Cross-env
- [ ] paper IntentProcessor.process(non-reducing intent, advisor=Trigger, gate=true) → reject
- [ ] demo 同上
- [ ] live IntentProcessor 對應路徑（process_gates_only_with_features）同上

### 工時

- E1 (Rust)：2.0d
- E2 review：0.5d
- E4 regression Linux + cross-env smoke：0.5d
- **全鏈 wall-clock：2.0d**（per RFC §9）

### Rollback

- TOML `gate_enabled = false`（重啟生效）
- IPC patch_risk_config gate_enabled=false（60s 內生效，無需重啟）
- per-strategy `cost_edge_exempt=true`（單策略繞 gate）
- 完全災難：env unset → daemon 不 spawn → setter 注入 None → gate 永遠 pass

### 高風險項（per RFC §10.2）

1. **★★★ R-C1 False-positive reject 平倉** — Gate 1.7 之前 `is_reducing` 必須計算正確。E2 必查：
   - `get_position(&intent.symbol).map(|p| p.is_long != intent.is_long).unwrap_or(false)` 完全複用 Gate 2.7 既有 pattern
   - unit test `test_gate_passes_close_when_trigger` 必通過
2. **★★ R-C2 Reject spam 撐爆 V026** — dedup_window_ms 預設 60s + tokio::spawn fire-and-forget INSERT。E2 必查：
   - 即使 reject 1 hr 持續，每分鐘最多 1 INSERT（60 row/hr）
   - INSERT 失敗 warn-log 不阻 IntentProcessor
3. **★ R-C9 gate_enabled=true 但 enabled=false** — validate 強制檢查並 RAISE。E2 必查：
   - `RiskConfig::validate()` 拒絕此組合
   - TOML 套用時若不一致 → engine startup fail-closed

### Files changed (預計 10 files: 9 修改 + 1 新建)

新建：
- `rust/openclaw_engine/tests/cost_edge_gate_integration.rs`

修改：
- `rust/openclaw_engine/src/config/risk_config_cost_edge.rs`
- `rust/openclaw_engine/src/config/risk_config_per_strategy.rs`
- `rust/openclaw_engine/src/intent_processor/mod.rs`
- `rust/openclaw_engine/src/intent_processor/router.rs`
- `rust/openclaw_engine/src/intent_processor/gates.rs`
- `rust/openclaw_engine/src/intent_processor/rejection_coding.rs`
- `rust/openclaw_engine/src/intent_processor/tests.rs`
- `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs`
- `settings/risk_config_paper.toml`
- `settings/risk_config_demo.toml`
- `settings/risk_config_live.toml`

### 完成後寫 .claude_reports/

```
.claude_reports/YYYYMMDD_HHMMSS_g3_09_phase_c_wave1_rust_gate.md
```
含 6 節（per CLAUDE.md §七 本地 LLM 審核協作）：任務摘要 / 修改清單 / 關鍵 diff /
治理對照（CLAUDE.md §二 #1 #4 #5 #6 #11）/ 不確定處 / Operator 下一步。
````

---

## §12 比較替代設計（≥3 alternatives）

### Alt 1：Python ExecutorAgent 注入 gate（拒絕）

**設計**：在 `executor_agent.py:execute_intent()` 早期插入 `check_cost_edge_advisor_status()` IPC，gate dormant 時 fall through，否則 reject。

**優點**：
- Python 端較易讀寫（5-Agent 範疇）
- ExecutorAgent 已有 metric pipeline

**拒絕理由**：
1. **漏 Rust 內部 strategy 直發 path** — KlineManager → SignalEngine → strategy → IntentProcessor 不經 Python，Python gate 漏 100% 此 path
2. **IPC round-trip 成本** — 每個 intent gate check 需 Python → Rust IPC ~1-5ms，hot-path 性能壓垮
3. **與 Rust 既有 cost_gate 不在同層** — audit 視野分裂、E2 review 困難
4. **shadow_mode 拓撲混淆** — ExecutorAgent shadow_mode=True 預設下根本不發 IPC，gate 無從生效

### Alt 2：在 Guardian 內注入（拒絕）

**設計**：擴 Guardian 4-check 為 5-check，第 5 check = cost_edge_gate。

**優點**：
- 統一風控入口（Guardian 已是「策略不繞風控」的物理化身）
- 單一檢查表結構

**拒絕理由**：
1. **Guardian 是 per-intent risk score 計算** — 加 portfolio-level gate 違反 Single Responsibility
2. **Guardian 在 `openclaw_core::guardian` crate** — IntentProcessor 在 `openclaw_engine`，注入需要跨 crate 暴露 advisor，circular dependency 風險
3. **Guardian 需 mock/no-op 機制** — Phase A advisor None 時 Guardian 仍要跑，每 check 加 None branch 污染 Guardian 純度
4. **既有 cost_gate 同樣是 portfolio-related 但放 IntentProcessor**（Gate 3） — Phase C 跟隨此 pattern 一致

### Alt 3：在 SubmitIntent IPC handler 層注入（拒絕）

**設計**：Rust IPC server `submit_intent` handler 在 dispatch 給 IntentProcessor 之前先做 gate check，failed 直接回 IPC error。

**優點**：
- 最早期 reject，省 IntentProcessor 整路
- 與 Python ExecutorAgent 對話最直接

**拒絕理由**：
1. **漏 Rust 內部 tick_pipeline 直接 process** — 既有 `tick_pipeline/event_consumer.rs` 路徑直接 call `intent_processor.process()` 不走 IPC，IPC 層 gate 漏此 path
2. **Audit log 寫入點不一致** — IPC handler reject 寫不到 `trading.risk_verdicts`（VerdictInfo path 在 IntentProcessor 內）
3. **與既有 reject path 不對齊** — 所有 Phase A/B reject 走 RejectionCode → IntentResult，IPC handler reject 是另一個 shape

### Alt 4：StopManager 監控 + 強制關現有倉（明確拒絕）

**設計**：cost_edge_advisor 觸發後，StopManager 強制 close 所有現有倉位（達成 CLAUDE.md §二 #13「建議關倉」字面）。

**拒絕理由**：
1. **CLAUDE.md §二 #5 生存>利潤反向防線** — 強制關倉 = 強制虧損實現，可能比繼續持倉更糟（市場已 dip 後再 force-close 鎖定底部）
2. **False-positive close 成本極高** — 即使 advisor 1 false trigger 也會清空所有 paper position
3. **違反 #11 Agent 自主權** — Agent 應自主決定何時關倉
4. **「建議關倉」設計上應為「阻新倉 + 觀察」**（per Phase A RFC §1.3 推導鏈），不是「強制關倉」

→ 採用 **方案 0（IntentProcessor Gate 1.7 注入）** 為唯一可行設計。

---

## §13 副作用識別

| 改動面 | 副作用 | 緩解 |
|---|---|---|
| `IntentProcessor` 持 advisor snapshot | 每個 IntentProcessor instance 多 1 個 Arc<...> 持有 | Option<Arc<...>>，None 時 zero overhead |
| Gate 1.7 注入 | 每個 process(intent) 多 1 次 advisor.snapshot() clone + status compare | < 1μs hot-path overhead；gate_enabled=false 時 1 boolean check 即跳過 |
| `RejectionCode::CostEdgeAdvisorTrigger` 新 variant | enum size 增；既有 match 需加 arm（or `_`）| Rust compiler 強制 exhaustive match → E2 review 自動 catch |
| `StrategyOverride` +2 fields | serde forward-compat | `#[serde(default)]` ✅ |
| `RiskConfig.cost_edge` +2 fields | serde forward-compat | `#[serde(default)]` ✅ |
| V026 INSERT 增 GATE_REJECT row | 每分鐘最多 1 row（dedup window） | 30d retention 自動清；transition_from 字面前綴可 query 切片 |
| TOML 三 env 加新 field | 既有 deploy 路徑不破（serde default 接管） | E4 smoke 驗 startup |
| IPC patch_risk_config | 既有路徑可 hot-reload cost_edge 子節（Phase A 已就位），new fields 自動 supported | 0 IPC schema 變更 |
| 4 IPC counter（reject_24h）| IPC response 增 ~20 byte | 可忽略 |

**未涉及**：
- ❌ 不改 §四 5 項 live 硬邊界
- ❌ 不改 H5 cost_tracker
- ❌ 不改 cost_gate (Gate 3 per-intent)
- ❌ 不改 Guardian
- ❌ 不改 OrderIntent schema（intent_id capture 推遲）
- ❌ 不改 Python ExecutorAgent IPC schema

---

## §14 Cross-env 安全保證

| 環境 | Phase C Wave 1 deploy 後預設行為 | Wave 3 enable 後行為 |
|---|---|---|
| **paper** | gate_enabled=false → 0 reject（Phase B 行為）| Operator demo 確認 ≥7d 無 false-positive close 後考慮 paper enable |
| **demo** | 同上 | Wave 3 主要 enable 環境（per memory `feedback_demo_over_paper_for_edge`）|
| **live (LiveDemo)** | 同上 | Wave 3 demo Phase C 觀察 ≥7d 通過後 PM sign-off enable |
| **live (Mainnet)** | 同上 + Phase A RFC §8.3 Operator checklist 鎖死 | **Wave 3 不啟用**；後續單獨 ticket + Operator 顯式批准 |

3 env TOML `[cost_edge]` section default `gate_enabled = false` 確保任何 deploy 路徑不自動啟用 reject。

---

## §15 16 根原則合規對照

| # | 原則 | Phase C 影響 | 措施 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | gate 在 IntentProcessor 唯一 entry path |
| 2 | 讀寫分離 | ✅ | advisor 仍只讀 H5；gate 寫 V026 / risk_verdicts 兩 audit 表 |
| 3 | AI 輸出 ≠ 命令 | ✅ | gate 是規則式比對，非 AI 生成；advisor.status = state machine 純 fn |
| 4 | 策略不繞風控 | ⭐⭐⭐ | ★ Phase C 是 #4 落地的 binding 機制 |
| 5 | 生存 > 利潤 | ✅ | gate 只阻新倉，不關現有倉位（反向防線） |
| 6 | 失敗默認收縮 | ⭐⭐⭐ | ★ gate_enabled=false default + WarmUp/Stale fail-open |
| 7 | 學習 ≠ 改寫 Live | ✅ | threshold 校準走 Operator manual approve（Phase B deliverable） |
| 8 | 交易可解釋 | ✅ | reject reason 含 ratio/threshold/triggered_at_ms；trading.risk_verdicts + V026 雙寫 |
| 9 | 災難保護 | ✅ | DB down → INSERT warn-log 不阻 gate；advisor None → fail-open |
| 10 | 認知誠實 | ✅ | engine_mode 明標 paper/demo/live_demo |
| 11 | Agent 自主權 | ✅ | exempt 機制 + per-strategy override 給 Agent 自主校準路徑 |
| 12 | 持續進化 | ✅ | reject log 入 V026 為後續 Phase D 學習資料 |
| 13 | AI 成本感知 | ⭐⭐⭐ | ★ Phase C 是 #13 的 binding gate 終態 |
| 14 | 零外部成本 | ✅ | 0 新 LLM/API 依賴 |
| 15 | 多 Agent 協作 | 中性 | gate 統一作用於所有 Agent intent |
| 16 | 組合級風險 | ⭐⭐⭐ | ★ portfolio-level cost_edge ratio 是 #16 一級指標 |

**§四 5 項 live 硬邊界**：全 5 項零觸碰 ✅

**EX-01 P0/P1/P2 三層風控對齊**：cost_edge_advisor gate 屬 **P2**（advisory + EV 過濾層）— 與 cost_gate 同層；不觸 P0（live_execution_allowed / authorization）也不觸 P1（hard limits）。

---

## §16 結語 + 派發策略

### 16.1 結論

Phase C = 「Phase A 已就位 advisor + Phase B 已就位 observability 基礎上加 binding gate，達成 CLAUDE.md §二 #13 的 Rust hot-path 終態」。

**主要 design choice**（≤200 字 summary）：
1. **Gate 在 Rust IntentProcessor Gate 1.7 位置**（非 Python ExecutorAgent，非 Guardian，非 IPC handler）— 唯一覆蓋 100% intent path 的注入點
2. **三層 default-off safeguard**：env=1 + RiskConfig.enabled=true + RiskConfig.gate_enabled=true，缺一不擋
3. **只阻新倉**（is_reducing=true 完全跳過）— 嚴守 #5 生存>利潤反向防線
4. **Dedup window 60s** 控 V026 INSERT 頻率，但 reject decision 不被 dedup 影響
5. **Per-strategy override + exempt** 給 emergency exit / risk-off 場景靈活性
6. **重用 Phase B V026 hypertable** 寫 GATE_REJECT row（`transition_from='GATE_REJECT:<strategy>'`）
7. **Python ExecutorAgent 0 改動** — 既有 rejected_reason 處理已 generic
8. **3 Wave 派發** — Wave 1 (Rust 2d) + Wave 2 (Python metric 1d 並行) + Wave 3 (Linux deploy + 7d observation)

### 16.2 Key risks

1. **R-C1 False-positive reject 平倉** — Gate 1.7 之前 is_reducing 計算必須複用 Gate 2.7 既有 pattern；E2 必查 + unit test 釘死
2. **R-C5 Live mainnet 提早啟用** — TOML default false + Phase A RFC §8.3 Operator checklist 鎖死
3. **R-C6 系統凍結（advisor stuck Trigger）** — IPC 60s rollback + healthcheck WARN at 1h continuous + per-strategy exempt fast escape

### 16.3 Phase C → 後續銜接

Phase C 落地後：
- Phase D (G3-09 後續): per-symbol cost_edge_threshold（需 H5 升級拆 per-symbol bucket）+ GUI Reject Dashboard
- 與 G3-03 ExecutorAgent shadow→live 整合（Phase C reject reason 提供 ExecutorAgent metric source）
- 與 G2-03 StrategyOverride 整合（cost_edge override 屬 G2-03 schema 演化第 2 期）

**全文完。next: PM 審本 RFC → 等 Phase B 觀察期 Tier 1（≥48h）+ Tier 2（≥7d）deliverable 落地 → PM Sign-off Phase C → 派 Wave 1 §11 prompt template 給 E1 → Wave 2 並行 Python metric → Wave 3 Linux deploy + 7d observation → live mainnet 單獨 PM sign-off。**
