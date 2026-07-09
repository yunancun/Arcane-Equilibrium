# Sprint 1A-ζ Phase 1 — PA Refine Closure Report

**日期**：2026-05-21
**Owner**：PA (Project Architect)
**Phase**：Sprint 1A-ζ Phase 1（single-thread 4-6 hr；patches P-5/P-6/P-7/P-8/P-9 close）
**Verdict**：**READY for Phase 2 E1 IMPL Dispatch**（待 Phase 0 §6 6 confirm 全 PASS）

---

## 1. Phase 1 Scope

Phase 1 single-thread PA refine deliverable，目標：
- close 5 critical patch（P-5 sandbox + P-6 Vault + P-7 mock time + P-8 LAL CHECK + P-9 fetch SOP）
- 撰 3 E1 dispatch packet (Track A/B/C)
- 收 Phase 0 → Phase 1 → Phase 2 sign-off chain

---

## 2. 5 Deliverable 全部 land

### Deliverable 1: P-5/P-6 sandbox infrastructure prep checklist

**Path**：`/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_phase0_sandbox_prep_checklist.md`
**行數**：414 行（target 150-250；超出因含完整 SQL/Verify command + 9 section）
**內容**：
- §1 Phase 0 scope（sandbox DB + Vault TOTP + sample fills）
- §2 E3 task（trading_ai_sandbox DB 創建 + role + TimescaleDB + V096 baseline catch-up）
- §3 AI-E task（TOTP secret `$OPENCLAW_SECRETS_DIR/vault/totp_2fa_sandbox.json` + 14d rotation + fingerprint）
- §4 E3+MIT task（sample fills 100-500 rows bb_breakout BTCUSDT live_demo seed）
- §5 verify SQL 5 reflection（per V099_V116 SOP §10 Q1-Q5 pattern）
- §6 GO criteria 6 confirm（C1 sandbox DB / C2 TimescaleDB / C3 V096 baseline / C4 TOTP / C5 fills seed / C6 pgpass）
- §7 fallback (3 選 1：取消 spike / production with audit / defer + sandbox infra)
- §8 Phase 0 → Phase 1 → Phase 2 sign-off chain
- §9 cross-reference

### Deliverable 2: P-7 AC-5 amp cap 24h mock time hook spec

**Append location**：spike spec §4 line 349-465（target 30-50；超出因含完整 Rust test code + 對齊 M3 spec §3.3）
**設計選擇**：tokio::time::pause + advance（推薦；對齊 engine tokio runtime；feature flag `spike` 隔絕 production binary）；棄 mock-instant crate（引入 dep）+ 自寫 TestClock trait（構造參數污染）
**對齊**：ADR-0042 Decision 4 amplification cap + M3 spec §3.3 dwell time + flap suppression
**Verify command**：`cargo test --release --features spike test_amp_cap_24h_fire`

### Deliverable 3: P-8 AC-1 LAL reverse INSERT SQL + Rust assert

**Append location**：spike spec §4 line 280-347（target 30-50；超出因含完整 SQL + Rust test code）
**內容**：
- 2 SQL test：lal_level=-1 + lal_level=5 反向 INSERT 必 RAISE CHECK constraint
- 3 Rust assert test：LalTier::from_i32(-1)/from_i32(5) 必 Err；numeric_value 越大越嚴對齊 ADR-0034 line 41 + line 137-143
- 對齊 V112 spec §2.2 5 tier_name enum: LAL_0_AUTO / LAL_1_LIGHT_REVIEW / LAL_2_FULL_REVIEW / LAL_3_OPERATOR_APPROVAL / LAL_4_OPERATOR_ATTESTATION

### Deliverable 4: P-9 fetch SOP for 3 並行 E1 sub-agent dispatch

**Append location**：spike spec §6.3.1 line 557-620（target 20-30；超出因含完整反模式禁止清單 + 7 ceiling table）
**內容**：
- Pre-dispatch fetch check（git fetch + git branch -r grep）
- Stagger 5 min dispatch 順序（T+0 Track A → T+5 Track B → T+10 Track C）
- 獨立 working_branch hint per track 避撞
- Disconnect 三連檢查（memory log / git log / TODO entry）
- 7 sub-agent ceiling check (Phase 2 max 3 + Phase 3a max 3；不同步 → 不撞 7)
- 4 反模式禁止（不 stagger / 不 fetch / 同步 Phase 3a / 不三連檢查）

### Deliverable 5: 3 E1 dispatch packet (Track A/B/C)

**Path**：`/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_3_e1_dispatch_packet.md`
**行數**：438 行（target 250-400；超出因 3 Track 各完整 packet + §4 派發順序 + §5 GO criteria）
**內容**：
- §1 Track A E1 packet（M1 LAL + V112；12-18 hr；AC-1+2+3+4 含 AC-1.1）
  - V### apply: V113 transcribe + V112
  - Rust skeleton: lal_state_machine.rs + lal_tier_0_fill_blocker.rs (RETIRED check per ADR-0034 Decision 6)
  - Test: spike_lal_transition.rs (5 row + 反向 INSERT + Rust assert)
- §2 Track B E1 packet（M3 Health + V106；13-19 hr；AC-1+2+3+5 含 AC-5.1）
  - V### apply: V106 standalone
  - Rust skeleton: state_machine.rs + engine_runtime_domain.rs + amplification_cap.rs
  - Test: spike_health_amp_cap_fire.rs (mock time hook per AC-5.1)
- §3 Track C E1 packet（M11 Replay + V107 + Python skeleton；16-27 hr per Q4a override；AC-1+2+3+6）
  - V### apply: V107 standalone first
  - Python skeleton: spike_trigger.py + divergence_d1_fill_chain.py
  - Test: spike_m11_m7_dedup_contract.py (6 forbidden field grep + 0 learning.decay_signals write)
- §4 派發順序（V107 T+0 → V113+V112 T+5min → V106 T+10min；Rust skeleton 3 並行不撞 PG）
- §5 Phase 0 + Phase 1 GO criteria checklist 8 條（C1-C6 Phase 0 + C7-C8 Phase 1）
- §6 Phase 2 → Phase 3 sign-off chain（E2 對抗 review × 3 並行 per `feedback_impl_done_adversarial_review`）

---

## 3. C7 V103 EXTEND M4 PM Q1 Verdict 狀態確認

**結論**：carry-over Sprint 1A-ε 已 close（per Sprint 1A-β closure 2026-05-21）；不影響 Sprint 1A-ζ spike；無需 Phase 1 處理

---

## 4. Phase 0 → Phase 1 → Phase 2 Sign-off Chain

```
Phase 0 sandbox + Vault prep（本 Phase 1 deliverable 1 + 5 §5.1 6 confirm）
  │ E3 + AI-E + MIT 串行 4-6 hr
  │ §6 6 confirm 全 PASS = GO
  ↓
Phase 1 PA refine + 3 dispatch packet（本 Phase 1 deliverable 2/3/4/5）
  │ PA single-thread 4-6 hr
  │ 3 E1 dispatch packet land + spike spec append 3 subsection
  ↓
Phase 2 E1 IMPL × 3 並行（PM 派發 per §4 sequential ordering）
  │ stagger 5 min: V107 T+0 → V113+V112 T+5 → V106 T+10
  │ 35-55 hr / wall-clock 3-4 day
  ↓
Phase 3a E2 對抗 review × 3 並行（per `feedback_impl_done_adversarial_review`）
  ↓
Phase 3b-e E4 regression / QA empirical / TW report / PM verdict
```

---

## 5. Verdict

**READY for Phase 2 E1 IMPL Dispatch**

前置條件（PM 派 Phase 2 前必驗）：
1. Phase 0 §6 6 confirm 全 PASS（E3 + AI-E + MIT 串行 4-6 hr land 後）
2. Phase 1 deliverable 5 已 land（本報告即 PA Phase 1 closure）
3. PM stagger 5 min 派 3 並行 E1 sub-agent（Track C T+0 → Track A T+5 → Track B T+10）

**禁忌已守**：
- 不寫 IMPL Rust/Python/SQL code（Phase 2 E1 工作）
- 不執行 sandbox DB creation（E3 工作 per Phase 0）
- 不執行 Vault TOTP setup（AI-E 工作 per Phase 0）
- 不派下游 sub-agent（PA Phase 1 single-thread；PM 主會話統一收口 Phase 0 dispatch）
- 不 commit（PM 統一收口）
- 中文為主 / 不加 emoji

---

**PA DESIGN DONE**：report path `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_phase1_pa_refine.md`
