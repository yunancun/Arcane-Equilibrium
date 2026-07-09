# Sprint N+1 D+1 Second-Day Dispatch SOP

**Date**: 2026-05-11 (D+1, 預期日期)
**Owner**: PM
**Predecessor**: D+0 sign-off + dispatch fire (per `2026-05-10--n0_signoff_n1_dispatch_fire_sop.md`)
**Scope**: D+1 24h 內派發的 9 wave sub-agent 工作 + spot check + end-of-day status

---

## §0 D+0 6h Spot Check Snapshot（2026-05-10 15:30 UTC, sign-off + 6h pre-sign-off）

**Engine 6h post-restart fill activity**:
| Strategy | Symbol | demo | live_demo | total |
|---|---|---|---|---|
| grid_trading | SOLAYERUSDT | 10 | 10 | 20 |
| grid_trading | SUIUSDT | 8 | 2 | 10 |
| grid_trading | INXUSDT | 8 | 6 | 14 |
| grid_trading | SAHARAUSDT | 2 | 2 | 4 |
| grid_trading | TONUSDT | **0** | **0** | **0** |
| ma_crossover | BILLUSDT | 2 | 2 | 4 |
| **Total** | — | 30 | 22 | **52** |

**INXUSDT duplicate_position reject 6h trend**:
- 11:00 hour: 2331 reject (PA #3 audit baseline burst)
- 13:00 hour: 1 reject (sporadic)
- 14:00+: 0 reject (完全消退)

→ **W7-3 fix 仍價值（防 cross-strategy desync 重燃）但 deploy 不 urgent**

**Metric 預測 (21:30 UTC sign-off)**:
- metric 1 chain integrity: ✅ MIT 提早 closed
- **metric 2 [40] avg_net forward trajectory**: 預期 PASS（fill 量 52 比 4.5h baseline 32 多 + grid 5 symbol 分散 healthy）
- **metric 3 TONUSDT cell isolate**: ✅ **預期 PASS**（TONUSDT 6h 0 fill = isolate confirmed + 沒擴散到任何 grid symbol）

**Surprise finding 待 D+1 verify**:
- ma_crossover BILLUSDT 4 fill — BILLUSDT 是否在 ma_crossover scope？
  - QC W6 RFC §3 對比 cluster benchmark BILLUSDT n=11 avg=-49.67 bps **frozen**
  - 但 frozen list 可能只 apply grid_trading（per `srv/docs/governance_dev/strategy_blocked_symbols_freeze.json`）
  - **D+1 PA verify**：(1) BILLUSDT 是否在 ma_crossover symbol scope (2) 4 fill outcome 跟 baseline -49.67 對比 (3) 如 ma_crossover 也應 freeze BILLUSDT → 加 P2 ticket

---

## §1 D+1 開工 (08:00 UTC, sign-off + 10h)

### §1.1 Pre-day 檢查
- [ ] D+0 deploy verified PASS（restart + 30min observation + 24h trend）
- [ ] git fetch + Linux sync 確認無 race（per memory `feedback_git_commit_only_for_metadoc`）
- [ ] watchdog `engine_alive=true` + chains_with_lease > 0
- [ ] 5 策略 fire pattern 觀察（grid 持續 5 symbol / ma_crossover 看 BILLUSDT 是否擴散其他 symbol / bb_breakout 等 W1 / bb_reversion + funding_arb dormant）

### §1.2 Day-2 dispatch wave (parallel sub-agent)

```
D+1 08:00 UTC: PM 派 9 wave 並行 sub-agent
```

#### Wave priority order (per dependency graph):

**Tier 1 — 無 dependency, 可立即派**:
1. **W7-2 + bb_reversion sync** (E1 single sub-agent, ~25 LOC + 4 unit test, 0.5 day)
   - file: `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` + `bb_reversion/strategy_impl.rs`
   - scope: entry path 用 `ctx.position_state.is_some()` skip + bb_reversion 同 pattern apply
   - acceptance: ma_crossover INXUSDT 24h reject < 10/h（baseline 自然消退已 PASS，fix deploy 維持 0 risk）；bb_reversion 0 cross-strategy desync 在 12h test scenario

2. **W4 RouterLeaseGuard Drop test** (E4, ~40 LOC Rust unit test, 0.5 day)
   - file: `srv/rust/openclaw_engine/src/intent_processor/router.rs` + `tests.rs`
   - scope: 1 unit test verify Drop release on rejection path（per E4 W4 design report）
   - acceptance: pytest existing 9 case 仍 PASS + 新 unit test PASS + [55] chains_with_lease query 5min PASS

3. **W5-E1-A P1-CANARY-STAGE-CRITERIA-1 IMPL** (E1, ~340 LOC, 1-2 day)
   - per W5 spec `srv/docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`
   - AMD-2026-05-10-05 起草

4. **W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1 IMPL** (E1, ~760 LOC + V090, 2-3 day, 與 A 100% 並行)
   - per W5 spec `srv/docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md`

5. **PA verify ma_crossover BILLUSDT scope** (PA, 0.5h, per §0 spot check finding)
   - 確認 BILLUSDT 是否在 ma_crossover symbol scope
   - 4 fill outcome vs baseline -49.67 bps 對比
   - 如 ma_crossover 應 freeze BILLUSDT → 加 P2 ticket

**Tier 2 — 等 Tier 1 部分完成**:
6. **W7-4 5 策略 systemic audit** (PA + E1, 1 day, 等 W7-2 D+1 完成後啟動)
   - 用 ctx.position_state field 跑 5 策略 audit
   - 出 P2 ticket list final（grid_trading / funding_arb / bb_breakout 系統 risk verdict）

7. **W7-5 on_fill + bootstrap import_positions** (E1, ~20 LOC + tests, 0.5 day, 等 W7-4 verdict)
   - on_fill update self.positions
   - bootstrap 從 paper_state import_positions 重建

**Tier 3 — 等 Wave 6 / 7 完成 (D+1 EOD ~ D+2)**:
8. **W6 RFC verdict 三角 sign-off** (PA + QC + MIT 並行 verify, 1.5h + 1h sync, D+1 上下午各 1 phase)
   - PA + QC + MIT 各 verify W6-1 RFC final verdict draft `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md`
   - 3 APPROVE → 升 AMD-2026-05-1X-W6-1-rfc-verdict + dispatch v3.7 §6 cross-ref + CLAUDE.md §三 W6 摘要 land

9. **W6 V086 IMPL** (E1, V086 two TEXT column + 30-90s in-migration backfill + trading.fills 17 row UPDATE, 1 day, 等 W6 RFC verdict APPROVE)
   - per spec `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_3b_enum_spec_final_pa_decision.md`
   - 同次加 W6-3 multi-class label split scope (12 reject_reason_code + 14 close_reason_code)

**Tier 4 — W1 + W2 IMPL chain (與 Tier 1-3 並行, 5-7 day):**
10. **W1 IMPL chain** (3 E1 sub-agent + WS-first per BB push back)
    - **E1-α leader: broadcast migration**（mpsc → broadcast critical gating dependency, 1 day）
    - **E1-β: funding_curve writer + V085**（rebase parallel after E1-α land, 2 day）
    - **E1-γ: oi_delta_panel writer + V087**（rebase parallel after E1-α land, 2 day）

11. **W2 IMPL chain v1.2** (5 E1 sub-agent, fast-track paper IMPL)
    - **C-IMPL-1 NO-OP** (trait c9fb0b8f land 已 verified)
    - **C-IMPL-2 lead-lag producer + V088** (E1, 2 day)
    - **C-IMPL-3 strategy paper-only 接收** (E1, 1 day, ma_crossover + grid_trading shadow log)
    - **C-IMPL-4 paper engine 7d evidence collection** (D+5 啟動, 跑到 D+12)
    - **MIT C-3 σ verify spec acceptance update** (per dual-layer reframe, D+1 PA sign-off 同次 update)

### §1.3 Wave dependency 衝突

**File 衝突風險**:
- `strategy_impl.rs` 5 file: W7-2 動 ma_crossover + bb_reversion；W7-5 動 on_fill 5 file；W7-4 read-only audit 不撞
- `slots.rs` + `step_4_5_dispatch.rs`: W1-α/β/γ + W2-C-IMPL-2 同 file 加 line（per PA D+0 anchor 隔離）
- V### migration: V085-V090 編號 reserved 不撞

**派發策略**:
- W7-2 + W7-5 同 file (`ma_crossover/strategy_impl.rs` 共用) → **sequential**（W7-2 D+1 完成後 W7-5 D+2）
- W1-β + W1-γ 跟 W2-C-IMPL-2 並行 anchor 隔離（per PA #1 trait final shape report §6 分工）
- W5-E1-A + W5-E1-B + W5-E1-C 完全並行 0 file 重疊（per PA W5 三 P1 spec predraft）

---

## §2 D+1 Mid-day Spot Check (15:00 UTC, sign-off + 17h)

### §2.1 必查項
```bash
# Engine + chain integrity
ssh trade-core "PG_PASS=\$(awk -F= '/^POSTGRES_PASSWORD=/{print \$2}' /home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env) && \
  pgrep -af openclaw_engine | head -1 && \
  PGPASSWORD=\$PG_PASS psql -h 127.0.0.1 -U trading_admin -d trading_ai -c \
  \"SELECT chains, chains_with_lease, chains_with_report, bad_report_quality FROM agent_decision_spine_lineage WHERE ts > NOW() - INTERVAL '15 minutes' ORDER BY ts DESC LIMIT 1;\""

# ma_crossover INXUSDT 24h post-deploy reject (W7-2 acceptance)
PGPASSWORD=$PG_PASS psql -c "SELECT COUNT(*) FROM trading.risk_verdicts WHERE ts > '<deploy_ts>' AND reason ILIKE '%duplicate_position%INXUSDT%';"

# ma_crossover BILLUSDT 24h fill outcome (per §0 PA verify)
PGPASSWORD=$PG_PASS psql -c "SELECT COUNT(*) n, AVG(o.outcome_24h) avg_24h FROM trading.fills f JOIN trading.decision_outcomes o USING(context_id) WHERE f.strategy_name='ma_crossover' AND f.symbol='BILLUSDT' AND f.ts > '<deploy_ts>';"
```

### §2.2 W6 RFC verdict 三角 sign-off 上午 phase verify status
- PA: ✅ / ⏳ / ❌
- QC: ✅ / ⏳ / ❌
- MIT: ✅ / ⏳ / ❌
- 3 APPROVE → 下午 1h sync phase 升 AMD

### §2.3 W7-2 + W4 status check
- W7-2: E1 IMPL DONE / E2 review / E4 regression
- W4: E4 cargo test PASS / [55] runtime smoke PASS

### §2.4 watch 觀察
- 5 策略 fire pattern (grid 持續 5 symbol / ma_crossover BILLUSDT 是否擴散 / bb_breakout 待 W1 / 其他 dormant)
- governance reject reason mix (per W6-4 [59] healthcheck)

---

## §3 D+1 EOD Status (21:30 UTC, sign-off + 24h)

### §3.1 D+1 完成 wave 預期
- ✅ W7-2 (含 bb_reversion sync) PR ready land + deploy
- ✅ W4 RouterLeaseGuard Drop test land + 4 invariant verified
- ✅ W6 RFC verdict 三角 sign-off + AMD-2026-05-1X-W6-1 land
- ✅ PA BILLUSDT scope verify (per §0 spot check finding)
- ⏳ W6 V086 IMPL（D+1 spec ready，IMPL D+2 起）
- ⏳ W1 IMPL E1-α broadcast migration land（D+1 leader）
- ⏳ W2 C-IMPL-2 lead-lag producer 開工（D+1 起，D+3 完）
- ⏳ W5-E1-A/C 開工（D+1 起，D+2-3 完）
- ⏳ W7-4 systemic audit (D+1 EOD verdict)

### §3.2 update 文件
- TODO.md §6.5 update 各 wave status
- memory `project_2026_05_10_sprint_n1_d0_readiness.md` → rename `project_2026_05_10_sprint_n1_progress.md`
- CLAUDE_CHANGELOG.md 加 D+1 entry

---

## §4 Risk + Mitigation

### §4.1 Wave Conflict Risk
- W1 broadcast migration 失敗 → W1-β/γ 不能 rebase parallel → blocked
  - Mitigation: E1-α leader 24h SLA hard cap；超時 PA 回 v3.7 §3.1 W1 review revise plan
- W6 RFC verdict 三角 1 conditional → AMD 不 land → W6-3c V086 IMPL blocked
  - Mitigation: PA 24h 內補修 draft；如 ≥1 REJECT 重 RFC（不應發生 per draft 已全 capture 三方立場）

### §4.2 Cross-Wave Race
- W7-2 + W7-5 同 file ma_crossover/strategy_impl.rs → strict sequential
- W6-3c V086 + W6-3a/b enum spec → V086 IMPL 必先 spec land
- W3 Stage 1 cohort 不在 D+1 派（等 W6 + W7 完成 ~D+3-4）

### §4.3 Hot Loop Re-emergence
- W7-3 deploy 後 monitor INXUSDT reject 24h < 240/24h（從 baseline 16k/24h 降 ≥ 60×；6h spot check 已 0 reject confirmed self-cool-down）
- 如 reject 重燃 → 確認 W7-3 fix 有效；否則 rollback `git revert b42731f6`

### §4.4 BILLUSDT scope drift (per §0 spot check)
- ma_crossover 4 fill BILLUSDT 是否符合 ma_crossover scope？
- 如 BILLUSDT 應 frozen for ma_crossover → P2 ticket（D+1 Tier 1 #5 PA verify 同次 raise）

---

## §5 Operator Touchpoint

### §5.1 D+1 EOD 必通報 operator
- W6 RFC verdict 三角 sign-off 結果（APPROVE / CONDITIONAL / REJECT）
- W7-2 + W4 land 結果
- W1 broadcast migration 進度（critical gating dependency）
- 5 策略 24h fire pattern + reject mix
- BILLUSDT scope verify verdict（ma_crossover trade 合規/不合規）

### §5.2 D+1 中途 operator approve gate
- AMD-2026-05-1X-W6-1-rfc-verdict 升 doc 前 operator final approve（per CC condition #3）
- AMD-2026-05-10-06 invariant 23 wording 同 W5 P1 IMPL commit land 前 operator approve（per CC condition #4）

---

## §6 Reference

- D+0 sign-off SOP: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--n0_signoff_n1_dispatch_fire_sop.md`
- D+0 sign-off DRAFT: `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-10--n0_high5_signoff_draft.md`
- Sprint N+1 dispatch v3.7: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md`
- W7-3 deploy SOP: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_3_deploy_sop.md`
- W6-1 RFC verdict draft: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md`
- W2 spec v1.2: `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`
- W1 spec v1.1: `srv/docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md`
- W5 三 P1 spec: `srv/docs/execution_plan/2026-05-10--p1_*.md`

---

**End of D+1 SOP**. PM use this 走 24h 內 9 wave 並行 dispatch 流程 + Mid-day + EOD spot check + BILLUSDT scope verify。
