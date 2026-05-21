# Changelog — 玄衡 · Arcane Equilibrium 執行計畫版本紀錄

> 本檔為 Execution Plan 版本級 changelog，不是日常工程歷史。日常 Wave / Sprint / Batch 等
> 工程紀錄請見 `docs/CLAUDE_CHANGELOG.md`。
>
> 規則：
> - 每個版本一個 `## [v5.x] — YYYY-MM-DD` H2 section。
> - 採 keep-a-changelog 風格欄位（Added / Changed / Deprecated / Removed / Security /
>   Performance / Test / Docs / Sign-off）。
> - 對應 `docs/execution_plan/YYYY-MM-DD--execution-plan-v5.x.md` 主檔。
> - thesis-shift 版（v5.4→v5.5、v5.6→v5.7）+ scope-expansion 版（v5.7→v5.8）才在本檔登記；
>   微版（patch、rebase）走 `docs/CLAUDE_CHANGELOG.md`。
> - 16 根原則（CLAUDE.md §二）每版必須在 Sign-off 確認 0 紅線。

## [v5.8] — 2026-05-21

### Thesis 摘要

13-module autonomy expansion thesis 落地。v5.7 dispatch packet 保留不動；v5.8 在
v5.7 之上層加 13 個 autonomy module（M1-M13），對應 7 個新 ADR（0034-0040）+ 1 個
新 AMD（2026-05-21-01）+ 1 個 ContextDistiller v4 治理 ADR（0041）+ 4 個延伸 ADR
（0042 M3 / 0043 M6 / 0044 M7）。Sprint 1A 從 v5.7 的 1.5 週擴張為 5 階段
（1A-α / 1A-β / 1A-γ / 1A-δ / 1A-ε）+ PM push back 後 IMPL Prototype Spike 階段
（1A-ζ）共 10 週 wall-clock。

v5.7 thesis 不變：Self-Trading Lab 為主、Copy Trading evidence-gated、Bybit
framework、5 strategies portfolio。v5.8 把 Y2 達 90% / Y3 達 95% autonomy
目標從「framework shells only」升級為「substantively realizable」。

### Added

- 13-module autonomy expansion thesis（M1-M13 + 5 個 ADD-per-operator module）
  - M1 Decision Lease Layered Approval (LAL) — autonomous proposal-to-execution loop
  - M2 Overlay enable / disable mechanism（macro + on-chain auto-trigger）
  - M3 Self-monitoring + auto-diagnostics + health-aware degradation
  - M4 Self-supervised hypothesis discovery（Pattern miner DRAFT writeback）
  - M5 Online learning / incremental model update（Y3+ interface stub only）
  - M6 Multi-objective reward function tuning（Bayesian weight calibration）
  - M7 Strategy decay detection + auto-retirement
  - M8 Anomaly detection（DESIGN initial / IMPL phased）
  - M9 A/B testing framework（DESIGN initial / IMPL phased）
  - M10 Autonomous strategy / market / regime discovery pipeline
  - M11 Counterfactual replay automation + continuous validation
  - M12 Adaptive order routing（OrderRouter trait + maker_fill_rate_30d metric）
  - M13 Multi-asset class / multi-venue capacity（Bybit + Binance Y3+ at earliest）
- 11 個新 ADR + 1 個延伸 AMD：
  - ADR-0034 — Decision Lease Layered Approval (LAL) — M1（Sprint 1A-β）
  - ADR-0035 — M5 online learning interface reserved（Sprint 1A-δ）
  - ADR-0036 — M8 anomaly detection + M10 Tier D model blacklist
    （HMM / Markov-switching / GARCH 永久禁用；Sprint 1A-γ）
  - ADR-0037 — M9 A/B framework + mSPRT + Bonferroni statistical methodology
    （Sprint 1A-γ）
  - ADR-0038 — M11 continuous counterfactual replay + self-hosted PG
    `market.liquidations` source（Sprint 1A-β）
  - ADR-0039 — M12 OrderRouter trait + maker_fill_rate_30d metric
    （interface reservation；Sprint 1A-δ）
  - ADR-0040 — M13 multi-venue gate spec（Binance trade enable Y3+ at earliest；
    Sprint 1A-δ）
  - ADR-0041 — ContextDistiller v4 layered snapshot + DOC-08 §4 AI cost cap
    amendment（800 token hard cap；Y1 $60/月 + Y2 conditional $150-200/月 走
    LAL 4 approval）
  - ADR-0042 — M3 health monitoring（DESIGN reference；Sprint 1A-β 延伸）
  - ADR-0043 — M6 Bayesian reward weight 5 λ + GP Matern 5/2 + EI + 30d 30%
    rollback cap（Sprint 1A-β 延伸）
  - ADR-0044 — M7 DECAY_ENFORCED single authority（M7 vs M11 dedup 條約；
    DECAY_ENFORCED rename 對齊 CR-7；Sprint 1A-β 延伸）
- AMD-2026-05-21-01 autonomy-vs-human-final-review
  - protected scope 6 條（a-f：true-live kill / signed authorization /
    `OPENCLAW_ALLOW_MAINNET=1` mainnet env / Bybit retCode fail-closed /
    fake AI 寫入禁 / paper promotion 禁）— 此 6 條永遠不開放 auto path
  - opt-in scope 8 條（g-n：M1 LAL 1+2 / M2 / M3 Tier 1+2 / M4 DRAFT writeback /
    M6 ≤30% / M7 demote / M8 Y2 trigger / M10 tier eval）— 走 5-mitigation 機制
  - 反向 attack counter-mitigation 6 條（M1 fill 不可逆 / M2 false anomaly /
    M3 healthy burst alert-only / M7 14d × 50% / M8 4-級 severity / M11 5d
    unack auto-escalate）
- 12 個 V### schema migration / extension（V105-V116）：
  - V105 overlay_state_transitions + counterfactual_to_state hooks — M2
  - V106 health_observations + degradation_state — M3（hypertable 7d chunk +
    7d compression + 90d retention 必）
  - V107 replay_divergence_log — M11（hypertable 必；← V103/V109/V113）
  - V108 ab_tests + ab_assignments + ab_results — M9（← V103 共用 hypothesis
    schema）
  - V109 anomaly_events + severity — M8（hypertable 必；CHECK constraint 禁
    HMM/Markov/GARCH）
  - V110 reward_weight_history + bayesian_opt_runs — M6
  - V111 discovery_tier_config + capital_triggers — M10（Tier D 用 ATR-vol +
    funding 9-cell NOT HMM/GARCH）
  - V112 decision_lease_lal_tiers + lal_eligibility_log + lal_toggle_audit
    + `lal_pre_proposal_config_snapshot jsonb NOT NULL` — M1
  - V113 decay_signals + strategy_lifecycle — M7（hypertable 必；M7 single
    decay authority；schema 禁含 demote field）
  - V114 / V115 / V116 reserve frontmatter only — M5 / M12 / M13
- 8 份 runbook draft（皆 2026-05-21 land）：
  - `runbooks/2026-05-21--m1_lal_operator_runbook.md`（370 行）— 5-tier × 24h
    undo / 6 hard gate / LAL 4 attestation / clawback / 6 反向 attack 內嵌
  - `runbooks/2026-05-21--m3_health_oncall_runbook.md`（407 行）— 4-state ladder
    × 6 domain triage × amplification loop cap
  - `runbooks/2026-05-21--m7_decay_alert_runbook.md`（397 行）— 4 source × 6
    FSM enum 響應矩陣 + 14d × 50% 強制 SUSPENDED
  - `runbooks/2026-05-21--m11_replay_divergence_triage_runbook.md`（432 行）—
    5-7 divergence type × 4-level severity 對齊 M8 NOISE/WARN/CRITICAL/HALT +
    4h budget + 5d unack auto-escalate
  - `runbooks/2026-05-21--earn_governance_runbook.md`（418 行）— 5-Gate
    Adapter + manual rebalance first 3 months + APY 異常 3 trigger
  - `runbooks/2026-05-21--counterfactual_quality_report_runbook.md`（453 行）—
    monthly cron + 4 quality metric + Y1 末 ADR-0030 4-gate evidence packet
  - M2 overlay state-machine runbook（draft；Sprint 1A-γ 補完整 DDL）
  - M9 A/B variant cluster runbook（draft；Sprint 1A-γ 補 4-variant cluster
    statistical methodology）
- Sprint 1A-ζ IMPL Prototype Spike 階段（NEW phase；PM push back 2026-05-21）
  - 5 module spike：M1 LAL Tier 1 / M3 statistical detector / M6 Bayesian
    weight / M7 decay signal / M11 nightly replay
  - 1.5 wall-clock week + 2-3 sub-agent 並行 + 60-90 hr engineering
  - 完成後輸出 PASS / FAIL (a) revise / FAIL (b) accept limited / FAIL (c)
    defer first Live 四選一 verdict
- 12 個 CONTEXT.md 新詞條（Alpha autonomy taxonomy）
- 本 CHANGELOG.md 新建（首版 v5.7→v5.8 transition）

### Changed

- Sprint 1A wall-clock：7 週 → **10 週**（含 +1.5w cross-ADR collision risk
  + 1.5w spike phase）
- Sprint 1A 五階段 wall-clock：
  - 1A-α W0-1.5（v5.7 dispatch；PM-signed 2026-05-21）
  - 1A-β W1.5-3.5（CRITICAL DESIGN：M1/M3/M6/M7/M11）
  - 1A-γ W3.5-5.5（ADD-per-operator DESIGN：M2/M4/M8/M9/M10）
  - 1A-δ W5.5-6.5（interface stub：M5/M12/M13）
  - 1A-ε W6.5-8.5（cross-ADR consistency + Mac CI 13-module verify）
  - 1A-ζ W8.5-10（IMPL Prototype Spike + PASS/FAIL verdict）
- Y1 末 calendar：W44-55 → **W45-56**（順移 1-2w due to spike phase）
- Sprint 4 首次 Live：W18-21 → **W19-22**（順移 1-2w）
- Y1 engineering 工時：v5.7 1,275-1,710 hr → v5.8 **3,500-5,200 hr PM 整合**
  （+2.7-3.0x；CR-13）
- M1 Tier 0-4 → **LAL 0-4 rename**（per ADR-0034 + D2 已批；避 AMD-2026-05-15-01
  Stage 0R-4 字面碰撞）
- M8 anomaly detection HMM / Markov-switching / GARCH **永久禁用**（per ADR-0036；
  改用 ATR-vol + funding 9-cell state + RV percentile + block bootstrap）
- M10 Tier D regime auto-classify 同樣禁 HMM/GARCH（per ADR-0036）；改用 9-cell
  ATR-vol × Funding state
- M13 Binance trade enable：Y2 → **Y3+ at earliest**（per ADR-0040；BB push back
  落地；Y2 期間 Binance 維持 market-data only per ADR-0033）
- M7 decay state：`STAGE_DEMOTED` → **`DECAY_ENFORCED` rename**（per CR-7；避
  Stage 跨域字面碰撞 per AMD-2026-05-15-01）
- v5.8 §10 ADR roster：擴張為 7 ADR（0034-0040）+ ADR-0041 ContextDistiller v4
- §3 Sprint 1A engineering：543-797 hr / 7w → **670-1,015 hr / 8.5w**（含
  GUI/TW/MIT spec buffer + governance buffer + A3 sign-off + AI cost reserve）
- §3.5 PM 整合上修明文化：CR-11 GUI +261-374 hr / CR-12 TW +450-640 hr / CR-8
  MIT spec +90-140 hr / A3 sign-off +48-53 hr / governance amend +60-90 hr
  / AI cost Y1 $505-865 + Y2 $1,344-2,556 / cross-Sprint collision buffer
  +80-120 hr
- Sprint 1A-α + Wave 2 + Wave 2.5 + 1A-β + 1A-γ + 1A-δ + 1A-ζ planning 全
  land 2026-05-21
- M9 4-variant cluster：parameter / signal source / risk profile / exit logic
  （per ADR-0037 + AMD-2026-05-21-01）
- M11 nightly replay：market.liquidations source 從 Bybit historical API 改為
  **self-hosted PG**（per ADR-0038 Decision 1；不依賴 Bybit historical API
  退出風險）

### Deprecated / Removed

- M5 online learning Y3+ IMPL deferred（per ADR-0035 retirement criteria：
  daily retrain 證實不足 + AUM > $50k + operator opt-in 三條件同時觸發才啟動）
- M14 hot-swap 動態 add/remove strategy 不重啟 engine — **deferred 至 v5.9**
- M15 capacity-aware sizing → 併入 **extended M6 acceptance #4**（orderbook
  depth threshold + liquidity 感知降權）
- M16 cross-strategy correlation re-sizing → 併入 **extended M1 LAL acceptance**
  （correlation-adjusted weight + 同向同 symbol 自動 down-weight）

### Security / Boundaries

- 5-gate auto path inheritance hard invariant 明文化（per v58-CR-15 + E3 + CC
  audit）：
  - 7 條 auto path 全列 §11.5 表（M1 LAL 1 + M1 LAL 2 + M2 auto-disable +
    M3 auto-degrade + M6 weight ≤30% + M7 DECAY_ENFORCED + M10 tier
    activation）
  - 任一 gate fail → fall-back Advisory（不繞 gate 直寫）
- M4 DRAFT writeback Decision Lease 紀律（per CR-15 + ADR-0024-lite）：
  - M4 pattern miner DRAFT 寫入 V103 EXTEND 必經 Decision Lease + HMAC
    signature + `ml-training-pattern-miner` role + rate limit
  - DRAFT 寫入 rate limit：≤ 10 / hr / instance + ≤ 100 / day（per AI-E cost
    guard ADR-0041）
  - **DRAFT 不可 auto promote 到 preregistered + 不可 auto trigger trial
    activation**
- LAL Tier 4 manual override **不可繞 M7 RETIRED → NORMAL_LIVE**（per
  AMD-2026-05-21-01 protected scope；ADR-0034 §LAL ↔ Stage 對齊矩陣）
- Cowork hybrid path：Y1 read-only / Y2 LAL Tier 2 auto-suggest（per ADR-0041
  D5；M4 Cowork operator-assistant scope 落實 ADR-0024-lite）
- DEX / Hyperliquid hardcode rejection（compile-time error in M13 Venue enum；
  per ADR-0040；D1a operator 已批永久 declined）
- M9 A/B test variant 不可 promote variant to live 不經 operator approval +
  Stage gate（per ADR-0037 + AMD-2026-05-21-01 opt-in scope）

### Performance / Cost

- AI cost Y1 baseline **$505-865 / yr**（per DOC-08 §4 $60/月 cap +
  ContextDistiller v4 800 token hard cap per ADR-0041）
- AI cost Y2 estimated **$1,344-2,556 / yr**（超 cap 1.9-3.5x；conditional
  opt-in raise to $150-200/月 per ADR-0041 LAL 4 approval）
- M11 nightly replay budget **< 4h wall-clock**（per M11 design spec §AC-3 +
  ADR-0038）
- PG buffer V106 health 高頻表 6mo +1.25-2.5 GB（占 buffer 16-63%）—
  mitigated by hypertable 7d chunk + 7d compression + 90d retention
- ContextDistiller token：v5.7 700-900 → v5.8 1,200-1,500 撞 L1 Ollama 9B
  <3s SLA → **800 token hard cap 強制 per ADR-0041 D2**
- M4 Cowork hybrid path 成本縮減 5x（Pattern miner 純規則 + DRAFT template
  summary + LLM 僅 narrative ≤ 5k token + 月度 ≤ 30 DRAFT cap）
- M11 narrative L1-first cadence 成本縮減 10-20x（daily L1 Ollama 9B + L2
  僅 CRITICAL/HALT ≥ 3σ + $50 + 月度 ≤ $5 cap）

### Test / CI

- Mac CI 全 13 module cross-compile verify（Sprint 1A-ε deliverable；CI tuple
  `aarch64-apple-darwin` 必含）
- 12 個 V### Linux PG empirical dry-run SOP 強制化（per CR-9 + CLAUDE.md §Data,
  Migrations, And Validation + feedback_v_migration_pg_dry_run 2026-05-05 V055
  教訓）
- IPC schema 增量清單（per H-13）必先寫入 `docs/ipc/INCREMENTAL_CHANGES.md`
  再 IMPL
- Cross-language 1e-4 fixture harness（per H-18）— Rust ↔ Python ↔ SQL 三方
  numeric round-trip 必 < 1e-4 epsilon
- §STATE-MACHINE-TEST proptest 窮舉 + dead-state scan + `is_none()` reset
  auto-clear 反模式 scan（per E4 H-14 + memory `feedback_first_detection_deadlock_pattern`）
- M9 mSPRT 演算法正確性 unit test（per E4 audit；確保 type-I error 控制
  Bonferroni / FDR correction 落地）

### Docs

- ~46 個新文件 land Sprint 1A-β/γ/δ + 1A-ζ planning（per R4 HOLD verdict 統計）
- `docs/README.md` index 補 ~30-46 條 entries（含 ADR 0034-0044 + AMD 1 條 +
  spec doc + 8 runbook + V### spec 12 條）
- TW 工時 **+450-640 hr Y1 written**（per CR-12；Sprint 1A 五階段 135-175 hr
  critical-path + 1B-10 ADR/spec/runbook 漸增）
- CHANGELOG.md v5.7→v5.8 entry land（本 entry）
- CONTEXT.md 12 詞條補錄 land（新 H3 section「Autonomy expansion taxonomy」）
- 兩份 spec doc：
  - `docs/execution_plan/2026-05-21--m4_minimum_bar_and_leakage_protocol.md`
  - `docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md`

### Operator Sign-off

- v5.7 12-prefix PM-signed 2026-05-21 commit `26ee2f06`
- v5.8 16-CR DONE 2026-05-21 commit `77d5c54e`
- Sprint 1A-α / 1A-β / 1A-γ / 1A-δ / 1A-ζ planning 全 PM-signed 2026-05-21
- 16 根原則合規：CC audit 6 WARN（M1 Tier 2 Auto governance 規格不足）— v5.8
  §11.5 5-gate auto path inheritance + §11 operator forgetfulness mitigation
  + AMD-2026-05-21-01 protected vs opt-in scope 三層補完，紅線 0
- 14 multi-agent audit verdict：11 GO-WITH-CONDITIONS / 3 HOLD（E2 + R4 + TW）
  / 0 NO-GO；3 HOLD 補完後全升 GO
- D1-D5 operator decision 全批：D1 13-module scope ✓ / D2 LAL rename ✓ /
  D3 timeline + engineering uplift ✓ / D4 M13 Y3+ ✓ / D5 AMD-2026-05-21-01 ✓

### References

- 主檔：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- v5.7 baseline：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md`
- PM final verdict：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`
- PA dispatch consolidation：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- 14-agent v5.8 audit reports：`docs/CCAgentWorkSpace/{A3,AI-E,BB,CC,E2,E3,E4,E5,FA,MIT,QA,QC,R4,TW}/workspace/reports/2026-05-21--v58_executability_audit.md`
- ADR-0034 至 ADR-0044：`docs/adr/0034..0044*.md`
- AMD-2026-05-21-01：`docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`

---

## [v5.7] — 2026-05-20

### Thesis 摘要

Dispatch-Safe Patch：v5.6 → v5.7 純工程精度修正，thesis 不變。15 rounds
reviewer audit 收斂 + 6 個 hard issue 全修：V### number reconciled / Earn
APR dynamic tracking / market.liquidations 已有 writer healthcheck 而非新建 /
Auto-Allocator Sprint 9 advisory-only Y2 active / macro+on-chain Y1
counterfactual-only / Earn movement Guardian-checked policy。

### Added

- ADR-0030 Copy Trading evidence-gated（v5.7 §11/§12 4 ADR draft；TW 2026-05-21
  C2 land；順移自 ADR-0028）
- ADR-0031 Framework expansion Earn + Macro + On-chain（順移自 ADR-0029）
- ADR-0032 Earn asset movement Guardian-checked policy（M2 Bybit Earn 必走 5-Gate
  Adapter；TW C2 land）
- ADR-0033 ADR-0006 Bybit-Binance amendment（Binance market-data primary，
  trade secondary Y3+ at earliest；standalone amendment 不取代 ADR-0006）
- 5 strategies portfolio：C10 funding harvest / Unlock SHORT / Pairs trading
  / C13 options VRP / Funding short-only
- Y1 honest income recompute：$300-550（v5.6 $547 overstated）
- Y2 mature run-rate honest estimate：$850-1,050（無 overlay alpha 計入）
- Stage 0R replay preflight + Stage 1-4 五階段 promotion gate framework
- §3.5.5 cross-V### dependency graph（V099-V116 順序限制 + PG dry-run mandate）

### Changed

- v5.6 → v5.7：6 個 engineering precision issue 全修
- Migration number reconciled：V101 → V103 / V104（schema-minimal；避 Track
  schema V101 衝突）
- Earn APR：hardcoded 4-8% → dynamic API tiered tracking（first $200 @ 10% +
  remaining @ 3% = $1k effective ~4.4%）
- market.liquidations writer：標 "NEW" → 標 "healthcheck/extend"（已 land 在
  `rust/openclaw_engine/src/database/market_writer.rs`）
- Auto-Allocator：Sprint 9 active → Sprint 9 advisory only + Auto activation
  defer to Y2
- Macro / on-chain：+2-3% APR uplift → counterfactual logging only Y1（不計入
  alpha）+ Y2 verification 後才考慮 enable
- Earn deposits：no governance policy → Guardian-checked policy + manual stake
  initially（per ADR-0032）

### Operator Sign-off

- v5.6 → v5.7 thesis dispatch-of-record（2026-05-20）
- 12-CRITICAL prefix PM-signed 2026-05-21 commit `26ee2f06`
- Sprint 1A-α dispatch packet PM-signed 2026-05-21
- 4 v5.7 follow-up D+1 land：V103 audit fields / V### re-number / PG conn
  範例 / Earn 五角色 cross-ref

### References

- 主檔：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md`
- v5.6 baseline：`docs/execution_plan/2026-05-13--execution-plan-v5.6.md`
- 12-CRITICAL prefix sign-off：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md`
- v5.7 autonomy verdict：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_autonomy_verdict.md`
- Sprint 1A-α dispatch packet：`docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md`
- ADR-0030 / 0031 / 0032 / 0033：`docs/adr/0030..0033*.md`
