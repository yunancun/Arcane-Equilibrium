---
report: PA — Sprint 1B Pending 3.1 C10 design summary
date: 2026-05-23
author: PA (Project Architect)
phase: Sprint 1B late · Pending 3.1 dispatch design summary
status: DESIGN-DONE · DISPATCH-PACKET-READY
parent reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_c10_funding_harvest_stage1_demo_dispatch_packet.md (full packet)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_remaining_3_sections_audit.md §1 §4.1
not in scope:
  - 不 IMPL Rust strategy
  - 不 commit
  - 不派下游 sub-agent
---

# PA Sprint 1B Pending 3.1 C10 PA design — summary

## §0 TL;DR

C10 funding harvest Stage 1 Demo dispatch packet 完成。**READY-TO-DISPATCH**，0 hard blocker，1 soft 諮詢（MIT V101 schema 0.5 hr）。estimate **41-62 hr** core + 並行 **wall-clock 4 day to cohort open + 7d 觀察 = 11d to verdict**。

## §1 C10 spec + delta-neutral design

- **delta-neutral 二腿**：perp short BTCUSDT (real demo fill) + spot long BTCUSDT (paper-only synthetic accounting；Bybit demo 不支援 spot lending)
- 入場：annualized funding > 5% AND basis_pct < 0.4% (= 0.5 × 0.8 entry_basis_ratio) AND funding > 0 AND cost-edge guard PASS
- 平倉：annualized funding < 2% OR basis_pct > 0.5% OR 72h max hold OR funding flip 負
- size：Stage 1 cap $100 absolute（hard ceiling in validate()）
- rebalance：每 2h tick check delta_drift_pct > 2% → SyntheticSpotLedger.rebalance() (純 in-memory book-keeping)
- 異常 fail-closed 矩陣：WS stale / Bybit retCode != 0 / SM-04 ≥ L3 / [55] FAIL / replay drift > 5% → demote
- 詳細 §1 + §4 dispatch packet

## §2 strategies/funding_harvest/ Rust module 設計

- 新建 `rust/openclaw_engine/src/strategies/funding_harvest/` directory（6 .rs file ~1230 LOC）
- 對齊 既有 `bb_breakout/` directory 結構：mod.rs / params.rs / runtime_params.rs / synthetic_spot.rs + tests.rs + tests_synthetic.rs
- 保留 `funding_arb.rs` V2 dormant marker per ADR-0018 + memory `project_funding_arb_v2_deprecation_path`；不刪除不改動
- Strategy trait impl: name() = "funding_harvest" / declared_alpha_sources = [FundingSkew, Basis]
- 不擴 governance 表面（不新增 LeaseScope variant / IntentType field）；既有 perp leg governance pipeline 完整覆蓋
- registry.rs StrategyFactory::create_with_params 接線 + strategies/mod.rs pub mod 註冊
- 詳細 §2 + §2.2 mod.rs 代碼骨架

## §3 spot leg paper-only synthetic accounting

- `SyntheticSpotLedger` struct in `synthetic_spot.rs` (~200 LOC)
- State machine: Closed → Open(via on_fill perp confirmed) → rebalance() × N → Closed(via on_close_confirmed)
- `is_synthetic_spot=true` flag 必傳到 V101 trading.fills.track (conditional on Sprint 4+ §4.1.1 base table audit verdict)
- `parent_perp_fill_id` cross-leg reference 在 audit query 可 JOIN 兩腿 fill row
- 不違反 16 root principles §1/§4/§8（不發 Bybit order；不繞風控；可重建可解釋）
- 唯一 acceptance exception: PnL 報告必雙列 — perp leg real PnL + synthetic spot leg notional PnL；total 對 demo balance 影響只有 perp
- 詳細 §3 dispatch packet

## §4 5 AC + Stage 0R replay preflight harness

**5 Acceptance Criteria** per FA §6 Stage 1 Demo gate：
1. fills ≥ 5 (real demo perp fills 排除 synthetic)
2. 7d cumulative PnL ≥ -0.5% (= -$5 absolute on $100 cap)
3. P0 breach = 0
4. size $100 absolute per fill
5. Stage 0R replay preflight PASS（6 sanity check PASS + eligible_for_demo_canary=true）

**Stage 0R replay preflight harness**：
- `helper_scripts/canary/replay_funding_harvest.py` 新檔 ~800 LOC
- 擴展既有 `replay_runner.py` 既有架構（fetch_klines / synthesize_ticks / JSONL output）
- 新增 fetch_funding_rates (Bybit V5 /v5/market/funding/history) + fetch_spot_klines + replay_funding_harvest simulation + compute_synthetic_pnl + output_preflight_verdict
- 6 sanity check: leak/lookahead / selection bias / DSR/PSR / PBO/bootstrap / replay data tier / runtime boundary
- output JSON schema with `eligible_for_demo_canary` + reasons + evidence_refs
- 詳細 §6 + §7 dispatch packet

## §5 8-step dispatch chain + 41-62 hr estimate

```
Wave A (W+0, 0.5-1 day): PA spec 8-12 hr // QC PSR/PBO review 2-4 hr // PA→MIT V101 schema 0.5 hr 諮詢
Wave B (W+0.5, 1.5-2 day, 5 並行 sub-agent):
  B1 E1a Rust module IMPL 18-26 hr
  B2 E1b registry+mod.rs 接線 2-3 hr
  B3 E1c TOML 接線 6 files 1-2 hr
  B4 E1d Python replay harness IMPL 8-12 hr
  B5 E1e V### migration is_synthetic_spot column conditional 0-3 hr
Wave C (W+2.5, 0.5 day): E2 adversarial review 2-3 hr // A3 UI reuse 0.5-1 hr
Wave D (W+3, 0.5 day, 並行): E1 round 2 fix 0-4 hr // E4 regression 1-2 hr
Wave E (W+3.5, 0.5-1 day, 並行): QA Stage 0R Acceptance 2-3 hr // QA Stage 1 pre-fly 1 hr // PM Phase 3e signoff 1 hr
Stage 1 Demo cohort open W+4 → 7d 觀察期 → W+11 Stage 1 verdict
```

**Total core effort 46.5-79 hr / compressed 41-62 hr per parallel 30-40%**：
- PA spec/harness 8-12 hr
- E1 IMPL Rust + Python + TOML + (V###) 31-46 hr
- E2/A3/QA/E4/PM 6-11 hr
- QC review 2-4 hr

**Wall-clock** ~4 day to cohort open + 7d 觀察 = 11d to verdict。

## §6 dispatch readiness verdict

**READY-TO-DISPATCH**
- 0 hard blocker
- 1 soft 諮詢（MIT V101 schema 預留 `is_synthetic_spot` column，0.5 hr W+0；結論決定 B5 並行性）
- 0 operator decision points needed
- AMD-2026-05-15-01 Stage 1 pre-launch gate 6 條全對齊

**PA 對 PM 立場**：可即刻 Wave A dispatch。

## §7 E2 重點審查 3 條

per dispatch packet §10 + 高風險點：

1. **Delta-neutral 數學正確性** — 4 條子驗（basis_pct abs formula / net_edge use |funding_rate| / annualized × 3 × 365 對齊 Bybit 8h cycle / delta_drift_pct 用 spot_notional 分母）
2. **SyntheticSpotLedger 邊界 + attribution** — 5 條子驗（不發 Bybit order / is_synthetic_spot flag 寫 V101 / parent_perp_fill_id JOIN / close 用 current spot price / on_external_close orphan handle）
3. **16 root principles 合規 + AMD §4.4 rollback** — 6 條子驗（單一寫入口 / 不繞風控 / 生存優先 stop_loss override / 可解釋 fills.track / Stage 1 demo evidence 6 條 / replay drift > 5% rollback）

## §8 副作用 + 跨模塊影響識別

| 改動 | 影響模塊 | 副作用 |
|---|---|---|
| 新 `strategies/funding_harvest/` module | strategies/mod.rs / registry.rs / params.rs | 加 pub mod + StrategyFactory case + StrategyParamsConfig field；不影響 5 既有策略 |
| `OrderIntent.strategy="funding_harvest"` 新值 | IntentProcessor / Guardian / cost_gate / DecisionLease / paper_state | 字串值新增；既有 hard-code 策略名清單需檢查（grep `"ma_crossover"\|"bb_reversion"\|...` 各 module） |
| `paper_state.owner_strategy="funding_harvest"` 新值 | paper_state.positions() filter / import_positions | 既有 5 策略 import_positions 既已 filter，新策略加自己 filter 即可 |
| `trading.fills.track is_synthetic_spot` column (conditional) | V101 schema / ML training feature / GUI display | 必確認 ML training query 對 `is_synthetic_spot=true` row 的處理（建議默認 exclude，per memory `feedback_demo_over_paper_for_edge` 範式） |
| `replay_runner.py` 擴展 fetch_funding_rates + spot_klines | helper_scripts/canary/*.py | 新增 ~80+50 LOC；既有 canary_comparator.py 不動 |
| `strategy_params_demo.toml [funding_harvest]` block | StrategyParamsConfig::funding_harvest field | 既有 5 策略 TOML pattern 對齊；TOML deserialize 默認 fall-back active=false 安全 |
| `risk_config_demo.toml [strategy_overrides.funding_harvest]` | risk_envelope per-strategy override | 既有 [strategy_overrides] section 範式（如有）對齊；如無 section 則新建 |

**asyncio/threading 混用邊界**：on_tick 同步調用，SyntheticSpotLedger 純 in-memory；不涉及 async。

**API schema 改動**：仅 conditional V101 column 新增；既有 control_api endpoint 不動（除非 GUI 加 funding_harvest tab，但 §10 A3 verdict = reuse strategy_performance tab）。

**Mock 測試最脆弱**：grep 既有 `mock_strategy` / `fake_strategy_name=` 在 tests 找；若有 hard-coded 5 策略清單，需加 funding_harvest。

## §9 PA 對 PM dispatch 建議

per audit §6 路徑 A：
- **W+0**：PM 拍板本 packet → dispatch Wave A（PA spec + QC review + PA→MIT V101 諮詢）
- **W+0.5**：Wave B 5 並行 sub-agent (E1a + E1b + E1c + E1d + E1e conditional)
- **W+2.5**：Wave C E2 review
- **W+3-3.5**：Wave D round 2 fix + E4 + QA
- **W+4**：PM Phase 3e sign-off + Stage 1 Demo cohort 開啟
- **W+11**：Stage 1 Demo 7d verdict

**並行性**：C10 dispatch 與 Sprint 4+ §4.1.1 V99-V102 base table audit **可並行**（C10 strategy 不依賴 earn_movement_log）。

**risk 紅線**：
- ❌ 不可在 Stage 0R replay preflight FAIL 後 直接進 Stage 1 Demo（per AMD §3）
- ❌ 不可將 SyntheticSpotLedger 當 Stage 4 LIVE spot order 路徑 ready（屬 Sprint 5+ cascade）
- ❌ 不可改 `position_cap_usd` 超過 100.0 而不過 PM signoff（FundingHarvestParams::validate() 強制 ≤ 100）

---

**END OF PA Sprint 1B Pending 3.1 C10 PA design summary**
