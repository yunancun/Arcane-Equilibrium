# ADR 0022: Strategist 30%→50% Cap 升級為 Wide Parameter Adjustment Skill（Freedom-not-Gate）

Date: 2026-05-10
Status: **Accepted**
Operator Sign-off Date: 2026-05-09 (Sprint N+0 拍板「不加新 supervised gate / 不 revert 30%」)
Sign-off Mode: 主會話 PM 拍板 + Sprint N+0 sign-off invariant 17 補件
Supersedes: TODO v18 line 552 中對 `P0-V2-NEW-2-STRATEGIST-CAP-NO-GATE` 的 ad-hoc decision；正式記錄為 ADR-0022 freedom-not-gate rationale + SM-05 張力處理 + 50% 偏離監測指標

## Context

### 起源

`P0-V2-NEW-2-STRATEGIST-CAP-NO-GATE`（TODO v19 line 310）— Strategist Agent
`max_param_delta_pct` 由 30% 拉至 50%（涵蓋 grid spacing / risk per trade / cooldown
/ confidence threshold 等可調 strategy_params 欄位）。原 30% cap 的設計動機是
「small adjustment heuristic」— 在 normal regime 下避免 Strategist over-tune；
但在 4-agent loss audit（PA + FA + QC + MIT 2026-05-09 共識）後揭露：

1. 5 textbook 策略 7d demo gross **-26.44 USDT**，不是 alpha 缺失而是 fail-closed
   default 累積（22 條，per AMD-2026-05-09-03 §1.2）
2. Strategist 在 normal regime cap 30% 內已被 Cognitive Modulator + Guardian veto
   + cost_gate + Decision Lease 多層收緊；額外的 cap 30% 等同雙重保險
3. 罕見場景（regime shift / liquidation cascade / cross-asset divergence）下，
   Strategist 需要快速跨 30% 邊界做 deliberate wide adjustment（如 grid spacing
   30%→48% 應對 vol regime 切換），現行 cap 強制截斷 = 系統性錯失 alpha 機會

### 兩個替代路徑（已評估 + 棄）

**Option A**：保 30% cap + 加新 `wide_adjustment_supervised_gate`（new operator
approval flow）— 棄。理由：(a) 違反 §二 原則 11「Agent 最大自主權」，把 Strategist
重新鎖回 supervised loop；(b) 與 ADR-0020 Layer2 manual-only by design 重疊
（Layer2 已經是 manual escalation）；(c) 增加 GUI/SOP/audit 維護成本，無對應 alpha
回報證據

**Option B**：永久 revert 至 30%（接受截斷成本）— 棄。理由：(a) 4-agent audit
明確指 alpha-poverty 而非 over-tuning 是當前根因；(b) 與 AMD-2026-05-09-03
graduated canary 的「stage 內保留 evidence collection 路徑」哲學矛盾；(c) operator
2026-05-09 直接拍板「不加新 supervised gate / 不 revert 30%」

## Decision

把 Strategist 的 `max_param_delta_pct` 30%→50% **解讀為 freedom-not-gate**：
30%→50% 不是放寬風控 ceiling（max envelope 仍由 RiskConfig 強制；Guardian veto / cost_gate / SM-04 ladder
/ Decision Lease 全鏈不變），而是 explicit 教 Strategist「你有 wide_parameter_adjustment 這個
deliberate skill，用於 normal-zone 之外的少數合理場景」。Rust prompt payload 升級為
**雙 zone 教學**：

```rust
// rust/openclaw_engine/src/agents/strategist/prompt_payload.rs (concept)
pub struct StrategistPromptPayload {
    pub normal_range_pct: (f64, f64),       // (0.0, 30.0) — 常規 tuning zone
    pub wide_skill_range_pct: (f64, f64),   // (30.0, 50.0) — wide_parameter_adjustment skill zone
    pub wide_skill_reason_hint: String,     // 教學提示：「跨 30% 必須 explicit 寫 reason
                                             //          且僅用於 regime shift / liquidation
                                             //          cascade / cross-asset divergence」
    pub current_envelope: RiskEnvelope,     // 風控 ceiling 不變，仍由 RiskConfig 強制
}
```

Strategist `propose_param_adjustment()` 邏輯：
- delta_pct ≤ 30% → normal tuning，無額外 metadata 要求
- 30% < delta_pct ≤ 50% → wide_parameter_adjustment skill invocation：
  - **必須**附 `wide_skill_reason: WideSkillReason` enum（`RegimeShift` /
    `LiquidationCascade` / `CrossAssetDivergence` / `Other(String)`）
  - **必須**emit `agent.strategist_wide_skill_invocations` ledger row
    （schema 詳 §配套機制）
  - 觸發 §配套機制 monthly Guardian veto review

### Rationale (freedom-not-gate)

1. **不是降低風控 ceiling**：50% 上限對應 RiskConfig.strategy_params 內的 envelope
   (Guardian-enforced max position pct / max leverage / per-symbol cap 等)
   **完全不變**。Strategist 提案 50% 仍經 Guardian 審批（per §二 原則 4）；不通過
   即 reject。
2. **是 explicit 教 Strategist 兩個 zone**：normal (0-30%) 與 wide skill (30-50%)
   是 deliberate 區分，不是「規則放鬆」。Strategist 的 LLM payload 收到的是
   「skill 知識」，不是「環境 unlock」。
3. **對齊 §二 原則 11**：Agent 最大自主權 = 在硬邊界內完全自主，包含「跨常規
   tuning zone 的 deliberate adjustment」。沿用 30% 強切等同把 Agent 鎖在
   「過於審慎到錯失合理機會」象限。
4. **與 AMD-2026-05-09-03 graduated canary 哲學一致**：fail-closed 是門檻語義不是
   stage 語義；`wide_parameter_adjustment` 是 Strategist 的 stage 內 evidence
   collection 路徑（normal zone 不夠用時往 wide skill zone 拓展），rollback 條件
   仍是 Guardian veto + monthly review 軟收縮。

### SM-05 張力處理

SM-05 invariants（per AMD-2026-05-09-01 §3 / §4）對 50% 上限**完全保留**，無放寬：

| SM-05 invariant | 對 wide_parameter_adjustment 的適用 |
|---|---|
| IPC failure → fail-closed | wide skill invocation 走同一 IPC path；IPC 掛 = 整 Strategist 鏈 fail-closed，wide skill 不例外 |
| Cache miss → fail-closed | `ExecutorConfigCache.shadow_mode_provider()` miss 仍 fail-closed Stage 0；wide skill 不繞 |
| Schema fail → fail-closed | wide skill 提案 schema 必含 `wide_skill_reason`；缺即 schema reject |
| Provider exception → fail-closed | `_read_shadow_mode()` exception 仍 fail-closed；wide skill 提案 drop |
| `lambda: True` 移除（F-01） | `ExecutorConfigCache.shadow_mode_provider()` 是唯一 truth；wide skill 不重新引入 fallback |

**換言之**：wide_parameter_adjustment 是 Strategist 的 LLM payload 升級，不是 SM-05
fail-closed 邏輯的鬆動。任何 IPC/cache/schema/provider 失敗，wide skill 提案與
normal 提案同等 fail-closed。

### 50% 偏離監測指標

每次 wide_parameter_adjustment skill invocation 應 emit
`agent.strategist_wide_skill_invocations` ledger row：

```sql
-- 預期 schema（W-AUDIT-7 IMPL 落地時 V### migration 拍板）
CREATE TABLE IF NOT EXISTS agent.strategist_wide_skill_invocations (
    id BIGSERIAL PRIMARY KEY,
    invoked_at_ms BIGINT NOT NULL,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    delta_pct NUMERIC(6,3) NOT NULL CHECK (delta_pct > 30.0 AND delta_pct <= 50.0),
    wide_skill_reason TEXT NOT NULL CHECK (
        wide_skill_reason IN ('regime_shift', 'liquidation_cascade',
                              'cross_asset_divergence', 'other')
    ),
    reason_detail TEXT,                          -- 'other' 必填 free-text
    commit_hash TEXT NOT NULL,                   -- runtime engine binary hash
    guardian_verdict TEXT NOT NULL,              -- 'approved' | 'rejected' | 'pending'
    decision_lease_id TEXT,                      -- nullable; pending → null
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_strategist_wide_skill_strategy_time
    ON agent.strategist_wide_skill_invocations (strategy_id, invoked_at_ms DESC);
```

**Monthly threshold** = N=10（建議）：
- 任一 strategy_id × 30d window 內 wide skill invocations > 10 → trigger Guardian
  veto review（GUI W-AUDIT-7 surface 顯示 + email/Slack alert per W-G escalation）
- review 結論：(a) 接受 — strategy 確實在 wide regime / (b) reject — Strategist
  drift detection，需 prompt payload 重新調整 / (c) escalate Layer2 manual review
- threshold 預設 10/month；可由 operator 在 Settings tab 拍板覆蓋（per
  AMD-2026-05-09-03 §4.3 GUI surface 同 tab）

**healthcheck 配套**：W-AUDIT-7 IMPL land 後加
`[59] strategist_wide_skill_drift_detection`：
- 對所有 active strategy_id 跑 monthly invocation count
- count > 10 → WARN（觸 Guardian review）
- count > 20 → FAIL（強制 Layer2 manual escalation per ADR-0020）
- 與 §二 原則 6 失敗默認收縮一致：drift 偵測即收縮 Strategist 行為

## Consequences

### Positive

- Strategist 真有自主 tuning 空間：normal zone 30% 內任意，wide skill zone
  30-50% 帶 reason + Guardian review，符合 §二 原則 11
- 對齊 4-agent audit 共識：alpha-poverty 是當前根因，過度收緊 Strategist 反而
  阻碍 evidence collection
- 與 AMD-2026-05-09-03 graduated canary + ADR-0021 alpha source architecture
  upgrade 哲學一致（保留 evidence collection 路徑，不 binary cut）

### Negative / Risk

- **Strategist 可能 over-use wide skill**：LLM 偶爾誤判 normal 為 wide → 觸發
  Guardian review → 增加 review 工作量
- **wide_skill_reason enum 演化**：`Other(String)` 是 escape hatch，可能成為
  drift collector；mitigation = §配套機制 monthly review 抓 `Other` 比例
- **與 AMD-2026-05-09-03 §3.5 graduated canary 互動**：Stage 1/2/3 cohort
  strategy 觸發 wide skill 時須額外驗 cohort 一致性（per W-AUDIT-9 T3 fix
  shadow_mode_provider stage-aware 完成後）

### Risk Mitigation

1. **skill_invocations ledger** 全量落地（per §配套機制 schema）— 任何 wide skill
   提案有 audit trail
2. **monthly Guardian review**（threshold N=10/month）— Drift detection
3. **Layer2 manual escalation**（per ADR-0020）— count > 20/month 觸發
4. **healthcheck `[59]` `strategist_wide_skill_drift_detection`** — silent-dead
   自動偵測（W-AUDIT-7 IMPL 期間 land）
5. **§二 16 原則合規 weekly 校核**（per CLAUDE.md §三 7d drift line）— wide skill
   不可繞過原則 1/4/5/6/9 任一

## §二 16 根原則合規確認（per ADR template + CLAUDE.md §二）

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | wide skill 提案仍走 IntentProcessor |
| 2 | 讀寫分離 | ✅ | GUI/研究只讀；wide skill 變更走 IPC + Guardian + Lease |
| 3 | AI 輸出 ≠ 命令 | ✅ | wide skill 提案經 Decision Lease + Guardian veto |
| 4 | 策略不繞風控 | ✅ | Guardian 審批所有 wide skill 提案 |
| 5 | 生存 > 利潤 | ✅ | StopManager + liquidation_buffer 不被觸碰 |
| 6 | 失敗默認收縮 | ✅ | drift detection (count > 10/20) 觸 review/escalation = 收縮 |
| 7 | 學習 ≠ Live | ✅ | wide skill 提案經 graduated canary stage（per AMD-03） |
| 8 | 交易可解釋 | ✅ | `agent.strategist_wide_skill_invocations` 全量 audit |
| 9 | 雙重防線 | ✅ | wide skill 不影響本地 + 交易所條件單 |
| 11 | Agent 最大自主 | ✅ | wide skill 是 §二 原則 11 的具體 IMPL（Agent 真有 tuning 自主） |
| 13 | cost 感知 | ✅ | cost_gate / cost_edge_ratio 對所有提案查 |

## Cross-references

- **AMD-2026-05-09-03 graduated canary default**：wide_parameter_adjustment 與
  graduated canary 共用「fail-closed 是門檻語義不是 stage 語義」哲學
- **AMD-2026-05-09-01 SM-05 polling design**：SM-05 invariants 對 wide skill
  完全保留
- **AMD-2026-05-09-02 §2 Option A**：W-A demo fail-closed posture 不變；wide
  skill 是 Strategist LLM payload 升級不是 executor 行為改動
- **ADR-0020 Layer2 manual-only**：count > 20/month 觸發 Layer2 escalation 與
  ADR-0020 一致
- **ADR-0021 Alpha Source Architecture Upgrade**：R-2 Strategist scope reframe
  IMPL（W-AUDIT-8e）後，wide skill enum / threshold 可能需重新校核

## Followup actions（Sprint N+0 / N+1 / W-AUDIT-7 IMPL 落地時）

| # | 動作 | Owner | 時點 |
|---|---|---|---|
| 1 | Rust prompt_payload 升級為雙 zone 教學（normal + wide_skill_range） | E1 (W-AUDIT-7 sub-task) | Sprint N+1+ |
| 2 | V### migration `agent.strategist_wide_skill_invocations` 加 schema + Guard A/B/C + Linux PG dry-run | E1 + MIT review | Sprint N+1+ |
| 3 | healthcheck `[59] strategist_wide_skill_drift_detection` IMPL + cron `0 */12 * * *` | E1 + ops | Sprint N+1+ |
| 4 | GUI W-AUDIT-7 surface 加「Strategist Wide Skill Invocations」面板（read-only history + monthly count + Guardian review queue） | E1a + A3 review | Sprint N+2+ |
| 5 | TODO §5.3 invariant 17 close 後同步移至 §5.3 invariant 23（建議 N=10/month threshold + healthcheck `[59]` runtime active） | PM | Sprint N+0 sign-off 後 |

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | Sprint N+0 拍板「不加新 supervised gate / 不 revert 30%」 | 2026-05-09 | ✅ Accepted |
| PA | 本文件作者（invariant 17 closure 派發） | 2026-05-10 | ✅ Drafted |
| FA | TODO v19 §5.3 invariant 17 來源 | 2026-05-09 | ✅ 認同 freedom-not-gate framing |
| PM | TBD（本 ADR commit 後通知） | 2026-05-10 | 🟡 Pending sign-off post-commit |

---

*OpenClaw / Arcane Equilibrium ADR-0022 — Strategist 30%→50% Cap as Wide Parameter Adjustment Skill (Freedom-not-Gate)*
