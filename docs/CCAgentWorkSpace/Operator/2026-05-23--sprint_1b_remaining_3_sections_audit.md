---
report: PA Sprint 1B 剩 3 章節 audit + dispatch plan
date: 2026-05-23
author: PA (Project Architect)
phase: Sprint 1B late + Sprint 5+ cascade dispatch readiness OPEN（per Sprint 4+ PM Phase 3e §5.3）
status: AUDIT-DONE / DISPATCH-PLAN-READY
parent reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md §5.3
  - srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_business_consolidation.md §6 §7
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md
  - srv/docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md §1
  - srv/docs/execution_plan/2026-05-21--earn_governance_spec.md
  - srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md
not in scope:
  - 不 IMPL Rust / Python / SQL
  - 不改 既有 strategy / bybit_rest_client
  - 不改 ADR / V###
  - 不 commit
  - 不派下游 sub-agent
---

# PA Sprint 1B 剩 3 章節 audit + dispatch plan — 2026-05-23

## §0 TL;DR

Sprint 4+ first Live carry-over PASS WITH 8 CARRY-OVER 後，Sprint 1B late + Sprint 5+ cascade dispatch readiness OPEN。Sprint 1B 「剩 3 章節」per PM Phase 3e §5.3：(1) C10 Stage 1 Demo、(2) Earn first stake、(3) v5.7 baseline 收口。

**核心結論**：
- **C10 funding harvest strategy 0 IMPL**（既有 `funding_arb.rs` 是 V2 directional dormant per ADR-0018，與 C10 delta-neutral 不同概念）。Stage 1 Demo 真實工作 = **新建 Rust strategy + spot leg paper-only emulation + risk_config TOML + Stage 0R replay preflight gate**，估 **PA spec 8-12 hr + E1 IMPL 30-45 hr**。
- **Earn first stake 0 IMPL**（既有 `bybit_rest_client.rs` 12 個 Bybit Earn endpoint 完全沒接；既有 `OrderIntent` struct 無 `IntentType` enum；既有 `LeaseScope` enum 無 `EarnStake/Redeem` variant）。前置 = **Bybit Earn API client 新建 + IntentProcessor enum extension + LeaseScope extension + V###（earn_movement_log table missing per V099/V100/V101 P0 base table audit）**。估 **PA + E1 35-55 hr**，**operator 親手 5 min query OpenClaw key 發行日 + first stake $200-400 拍板**。
- **v5.7 baseline 收口** = **誤導命名 — 真實狀態是「12 prefix DESIGN-DONE 已 100% closed via Sprint 1A-α + Wave 2 + Wave 2.5」**。剩餘真實工作 = **operator D+1 5 min OpenClaw API key query** + **operator D+5 Console tab 歸屬決策**（per Sprint 1A-β D+5 12-check #8/#9 carry-over）。**不存在 baseline IMPL 工作**。

**驗收 dispatch verdict**（per 3 章節 dispatch readiness）：
- **Pending 3.1 C10 Stage 1 Demo**：**READY-TO-DISPATCH**（前置 Sprint 1B late §4.1 V99-V102 base table audit 不阻塞 C10 Rust strategy IMPL；可並行）
- **Pending 3.2 Earn first stake**：**NEEDS-OPERATOR-DECISION**（D+1 OpenClaw key 發行日 query 5 min + first stake $200-400 拍板 + V99-V102 base table audit 含 `learning.earn_movement_log` 必須先 closure）
- **Pending 3.3 v5.7 baseline 收口**：**DOWNGRADE-TO-NON-WORK**（misnamed task；無實質 IMPL；建議從 Sprint 1B scope 移除 + TODO §1.2 line 61 措辭修正）

---

## §1 C10 funding harvest Stage 1 Demo audit

### §1.1 既有 C10 IMPL 狀態 audit

**grep verify**：
```bash
# 既有 strategies/ 目錄
ls rust/openclaw_engine/src/strategies/
# → bb_breakout/ bb_reversion/ common/ confluence.rs cross_asset/
#   cross_strategy_attribution_integrity.rs funding_arb.rs grid_helpers.rs
#   grid_trading/ ma_crossover/ maker_rejection.rs mod.rs params.rs
#   registry.rs strategy_params.rs test_harness.rs tests.rs

grep -rln "C10\|funding_harvest" rust/openclaw_engine/src/strategies/
# → 0 hits

grep -rln "funding_harvest" rust/openclaw_engine/src/ program_code/strategies/
# → 0 hits

# 既有 strategies/mod.rs pub mod 列表
# → bb_breakout / bb_reversion / common / confluence / cross_asset
#   / funding_arb / grid_helpers / grid_trading / ma_crossover
#   / maker_rejection / params / registry / strategy_params
# → 無 funding_harvest 或 C10 module

# 既有 settings TOML
grep -l "C10\|funding_harvest" settings/strategy_params*.toml settings/risk_control_rules/*.toml
# → 0 hits
```

**verdict**：C10 funding harvest **0 既有 IMPL**。

### §1.2 funding harvest vs funding_arb 概念對齊

**關鍵區分**（per memory `project_funding_arb_v2_deprecation_path.md` + FA §6 §7 + v5.7 §1）：

| 項目 | funding_arb (既有, dormant) | C10 funding harvest (新建) |
|---|---|---|
| 設計 | **directional**（單腿 perp，跟 funding rate 方向走，賺 funding payment）| **delta-neutral**（spot long + perp short matched notional，hedge ratio 1:1） |
| ADR | ADR-0018 retire（QC 2026-05-02 量化分析否決）| 新（v5.7 §1）|
| 文件 | `rust/openclaw_engine/src/strategies/funding_arb.rs` 1198 行（active=false dormant） | **0 既有** |
| 風險 | directional 暴露於 spot-perp 反向風暴 | delta-neutral，理論上 spot↔perp price 漂移自動對沖 |
| Demo 可行性 | demo 可 perp single-leg backtest | **Bybit demo 不支援 spot lending** → Stage 1-3 demo 灰度需 paper-only spot leg |
| 入場條件 | 拋棄（per QC 否決，break-even 7.6 day too costly）| BTCUSDT funding annualized > 5%（per FA §2）|
| 平倉條件 | dormant | funding annualized < 2% OR spot-perp basis drift > 0.5% absolute |

**結論**：C10 funding harvest **是新策略**，與既有 funding_arb 共用「funding rate」概念但 IMPL **完全不重疊**。建議：
- **保留** `strategies/funding_arb.rs` 為 V2 directional dormant marker（per memory；R-02 重設計 slot 預留）
- **新建** `strategies/funding_harvest/`（建議 directory，與 `bb_breakout/` `grid_trading/` 結構對齊）

### §1.3 Stage 1 Demo 部署實質工作

per AMD-2026-05-15-01 graduated canary + FA §6 Stage matrix C10 row + Sprint 1A dispatch packet §1：

```
Stage 0R Replay Preflight → Stage 1 Demo Micro-Canary 7d → Stage 2 14d → Stage 3 21d → Stage 4 LIVE
```

Stage 1 Demo gate 條件（per FA §6）：
- fills ≥ 5；7d cum PnL ≥ -0.5%；P0 breach=0
- size $100（spot leg paper-only；perp leg demo $100 matched notional）
- 前置 Stage 0R Replay Preflight PASS：replay 30d historical funding harvest fills；attribution_chain_ok=100%；PnL 偏離 < 1%

**Stage 1 Demo 部署實質工作清單**：

| # | 工作項 | Owner | 估時 | 前置 |
|---|---|---|---|---|
| 1 | **PA spec** — C10 funding harvest strategy 設計（入場/出場/size/rebalance/異常退出/spot leg paper-only emulation 機制） | PA | 8-12 hr | – |
| 2 | **C10 strategy IMPL**（`strategies/funding_harvest/` 新 module；perp leg = Rust strategy；spot leg = paper-only simulator state machine；basis drift 計算；funding rate listener；72h max hold；2h rebalance check） | E1 | 18-26 hr | #1 |
| 3 | **risk_config TOML**（`settings/strategy_params_demo.toml` + `risk_control_rules/risk_config_demo.toml` 新增 `[funding_harvest]` block + stop_loss override + position_size cap $100） | E1 | 1-2 hr | #2 |
| 4 | **Stage 0R replay preflight harness**（replay engine 接 C10 strategy 對 30d historical funding harvest fills；spot leg paper sim；attribution_chain_ok=100% verify；PnL 偏離 < 1% verify） | E1 + QC | 8-12 hr | #2 |
| 5 | **E2 review**（adversarial review of strategy IMPL + 16 原則 4/5/9 風控合規 + delta-neutral 數學驗證 + paper spot leg emulation 邊界） | E2 | 2-3 hr | #2 #4 |
| 6 | **E4 regression**（cargo test + pytest + integration test + cross-strategy attribution_chain_ok） | E4 | 1-2 hr | #5 |
| 7 | **QA Stage 0R replay preflight Acceptance** + **Stage 1 Demo Acceptance**（per Strategy × Stage gate matrix）| QA | 2-4 hr | #5 #6 |
| 8 | **PM closure**（Phase 3e sign-off） | PM | 1 hr | #7 |

**合計**：~41-62 hr（5-7 並行 sub-agent wall-clock 2-3 day）。

### §1.4 spot leg paper-only emulation 設計關鍵風險

per memory `project_funding_arb_v2_deprecation_path` §2 + BB C4 verdict + Bybit V5 API：
- **Bybit demo endpoint 不支援 spot lending**（C10 spot long 在 demo 需「paper-only emulation」），這是 C10 demo 灰度的核心技術難點
- Sprint 1B C10 spot leg **不接 Bybit demo spot order**，純 internal state machine 模擬 fill + price drift
- spot leg paper sim 必滿足：
  1. price source = real Bybit demo BTCUSDT spot price WS feed（read-only）
  2. fill latency = production live spot 平均（即時模擬，不延遲）
  3. balance accounting = engine-internal mock USDT balance（不寫 PG live balance；mock 同 paper engine）
  4. Stage 4 LIVE 升級時，spot leg paper-only → spot leg live（透過 IntentProcessor 既有 spot order path；該 path Sprint 4 IMPL 在 §4 carry-over Sprint 5+ cascade 中）

**側風險**：Bybit demo 不支援 spot order → spot leg 必走 paper-only，**這違反 demo 等同 live 嚴格度的原則**（per memory `feedback_live_no_degradation_by_endpoint`）。FA + QA + QC 已 consensus 接受此例外（per FA §6 row 1）。PA 立場：**接受**（無更好替代方案；其他選項 = 不做 C10 demo，但這就失 Sprint 1B 唯一可做的 strategy）。

### §1.5 C10 Stage 1 Demo 前置條件

| 前置 | 狀態 | 影響 |
|---|---|---|
| Stage 0R Replay Preflight infrastructure | **PARTIAL** — 既有 replay engine（per `helper_scripts/canary/*`）；需擴 C10 spot paper sim hook | 阻 Stage 0R PASS |
| Bybit demo BTCUSDT funding rate WS feed | **READY** — 既有 bybit_private_ws + WS funding rate listener（per Sprint 4+ instrumentation） | – |
| Bybit demo BTCUSDT spot price WS feed | **READY** — 既有 spot price feed for ML/edge | – |
| Demo perp endpoint | **READY** — production engine PID 3654935 active | – |
| risk_config_demo.toml strategy_params 框架 | **READY** | – |
| Funding harvest acceptance criteria（per FA §2） | **READY**（spec 完整 5 條） | – |

**verdict**：C10 Stage 1 Demo 技術前置 95%+ ready，dispatch readiness **OPEN**。

---

## §2 Earn first stake audit

### §2.1 Bybit Earn API client 既有狀態

**grep verify**：
```bash
# Bybit Earn API endpoint 在 既有 client
grep -i "earn\|stake\|/v5/earn\|liquidity_mining\|dual_investment" \
  rust/openclaw_engine/src/bybit_rest_client.rs
# → 0 functional hit（僅 "learning" 字串 substring，與 Earn 無關）

# Bybit Earn 在 Python API
grep -rn "earn\|stake" program_code/api/
# → 0 hits

# 既有 spot 訂單支援
grep "category.*spot\|/v5/spot\|spot_buy\|spot_sell" rust/openclaw_engine/src/bybit_rest_client.rs
# → 只有 rate limit path detection（/v5/spot-lever-token/ + /v5/spot-margin/）
# → 無真實 spot order submit / spot balance query / spot transfer
```

**Bybit Earn V5 API 12 endpoint**（per BB C4 verdict）：
- 6 read-only (`Read-Only` scope sufficient): product list / position query / order history / apr history × flexible + fixed
- 6 write (`Earn` scope required): subscribe/redeem flexible + place/redeem fixed-term + modify

**既有 Rust client 對 Earn 12 endpoint 覆蓋**：**0/12**

**verdict**：Bybit Earn API client **0 既有 IMPL**。

### §2.2 first stake 數額 / 賬戶 / 風險範圍 spec

per FA §6 §7 + Sprint 1A dispatch packet §1.2 + earn_governance_spec.md：

| 項目 | 規格 |
|---|---|
| 數額範圍 | $200-400 USDT（per Sprint 1B brief；first manual stake） |
| 賬戶 | Bybit primary live account 主帳（**Earn 不支援 Bybit demo** — per BB C4 verdict Part A §96 demo 0 product 待 curl smoke verify） |
| 風險範圍 | 3%/trade 不適用（Earn 不是 trade event）；max position $400 absolute |
| 產品種類 | **Bybit Earn flexible USDT savings**（tier 1 first $200 @ ~10% / remaining $200 @ ~3%） |
| 簽署 | 5-gate boundary 全適用 + Operator role manual approve（Layer 1 不接 auto stake；per ADR-0020 + earn_governance_spec §2） |
| Lease | `lease_type='earn_stake'`（新增 variant；既有 LeaseScope enum 缺）|
| Intent | `IntentType::EarnStake`（新增；既有 OrderIntent struct 缺 IntentType enum）|
| Audit | `learning.earn_movement_log`（新表；V099/V100/V101 base table audit 確認後 land）|

### §2.3 Bybit Earn API gap（per Sprint 4+ PM Phase 3e §5.3 Sprint 1B late）

| Gap | 狀態 | 阻 first stake 拍板? |
|---|---|---|
| Bybit Earn 12 endpoint client IMPL | **0/12** | YES |
| `OrderIntent::IntentType` enum 新建（per PA v57 12-prefix verify §3.3）| **0 hits**；既有 OrderIntent 無 IntentType field | YES |
| `LeaseScope::EarnStake` + `LeaseScope::EarnRedeem` variant | **0 hits**；既有 4 variant only (TradeEntry/TradeExit/PositionAdjust/CanaryStagePromotion)| YES |
| `learning.earn_movement_log` table | **V103 是 M4 hypothesis 不是 earn_movement_log；V104 spec land 但 .sql 未 land**；per Sprint 4+ PM Phase 3e §4.1.1 V99-V102 base table audit 待 closure | YES |
| Bybit demo Earn endpoint support | **UNVERIFIED**（per BB C4 §96 smoke test pending） | 阻決定 demo / live path |
| OpenClaw API key `Earn` scope | **UNKNOWN**（per BB C5 + TODO §0 D+1 5 min check）— 若 key 在 2026-04-09 前發行，需 operator 重發 key 加 `Earn` scope | YES |
| Earn governance spec 五角色 cross-ref final sign-off | **DRAFT**（per earn_governance_spec.md status DRAFT-FOR-FIVE-ROLE-CROSS-REF；FA + E3 + QA + MIT 四角色 cross-ref 後 sign-off）| 阻 IMPL 派發 |

### §2.4 first stake 部署實質工作

| # | 工作項 | Owner | 估時 | 前置 |
|---|---|---|---|---|
| 0 | **operator D+1 action** — OpenClaw Bybit key 發行日 5 min query | operator | 5 min | – |
| 0a | **operator first stake 拍板** — 數額 $200-400 + flexible vs fixed | operator | 10 min | 0 |
| 1 | **PA spec** — Bybit Earn API client + IntentProcessor::IntentType enum + LeaseScope::EarnStake variant 接線設計 | PA | 6-8 hr | 0 |
| 2 | **V099 (假設名) earn_movement_log table** PA schema spec + Linux PG dry-run（依 V99-V102 base table audit 結果決定編號）| PA + E1 | 4-6 hr | Sprint 4+ §4.1.1 V99-V102 audit |
| 3 | **Bybit Earn API client IMPL**（`rust/openclaw_engine/src/bybit_earn_client.rs` 新建；6 read-only endpoint + 6 write endpoint；rate limit group 對齊；retCode != 0 fail-closed） | E1 + BB | 10-15 hr | #1 |
| 4 | **IntentProcessor::IntentType enum** 新建 + 既有 OrderIntent struct 擴 IntentType field（+ 5 既有 variant 對齊：OpenLong/Short/CloseLong/Short + EarnStake/Redeem 兩新 variant） | E1 + PA | 4-6 hr | #1 |
| 5 | **LeaseScope::EarnStake + EarnRedeem variant** + `requires_operator_authority=true` + `default_ttl_ms=60000` + SQL CHECK constraint 同步 | E1 | 2-3 hr | #1 |
| 6 | **Earn governance spec finalize**（FA + E3 + QA + MIT 四角色 cross-ref sign-off） | CC + 4 agent | 4-6 hr 並行 | – |
| 7 | **Daily reconciliation cron** 02:00 UTC + mismatch → disable Earn 邏輯 | E1 | 4-6 hr | #3 #4 |
| 8 | **E1a GUI Earn manual stake form**（governance tab sub-section；type-to-confirm；A3 wizard）| E1a | 8-12 hr | #4 #5 #6；H2 Console tab 決策 |
| 9 | **E2 review**（adversarial review；16 原則 1/3/4/8 + 5-gate boundary + fail-closed） | E2 | 3-5 hr | #3 #4 #5 #7 #8 |
| 10 | **BB review** + **E3 review**（Bybit ToS / KYC / 地理 + secret slot 治理） | BB + E3 | 2-4 hr | #1 #6 |
| 11 | **E4 regression** + **QA Earn first stake Acceptance** | E4 + QA | 2-4 hr | #9 |
| 12 | **PM closure** | PM | 1 hr | #11 |

**合計**：~50-78 hr（5-7 並行 sub-agent wall-clock 3-4 day；含 operator 親手 30 min + 5 hr 並行 review 預留）。

### §2.5 first stake 風險矩陣

| Risk | 嚴重度 | 緩解 |
|---|---|---|
| Bybit demo 不支援 Earn → 直接 live first stake **嚴於** trading demo $0 → live $500 promotion path | HIGH | 接受；first stake $200 是有意低額；Earn 非 trading 風險源；governance spec 已明文 5-gate 全適用 |
| OpenClaw key 2026-04-09 前發 → 無 Earn scope → 需 operator 重發 key + 三端同步 | MED | D+1 5 min query 結果決定；若需重發，前置 +30-60 min operator action |
| `learning.earn_movement_log` table 缺 → first stake audit log 寫入失敗 | CRITICAL | 必前置完成 V99-V102 base table audit + V099/V100 (per audit 結果) land |
| OrderIntent struct 無 IntentType enum field → CC earn_governance spec 設計假設不真 | HIGH | per PA v57 verify §3.3 已 catch；E1 IMPL #4 必新建 enum |
| LeaseScope enum 無 EarnStake/Redeem → 既有 GovernanceCore.acquire_lease facade 不接 Earn | HIGH | per PA v57 verify §3.4 已 catch；E1 IMPL #5 必擴 variant |
| Bybit Earn API rate limit / IP geofence / KYC | MED | BB review #10 closure |
| stake 後 Bybit 撤回 product → 自動 redeem 不接 → 資金被卡 | MED | governance spec §3.7 + Daily reconciliation cron 必接 |
| Daily reconciliation mismatch → 自動 disable Earn until manual review | MED | governance spec §3.8 already designed |

### §2.6 first stake dispatch readiness verdict

**NEEDS-OPERATOR-DECISION + DEPENDS-ON-§4.1.1-CLOSURE**

阻塞鏈：
1. operator D+1 5 min query OpenClaw key 發行日 → 拍 first stake $200-400 + flexible/fixed
2. Sprint 4+ §4.1.1 V99-V102 base table audit + `learning.earn_movement_log` schema land
3. CC + 4 agent earn_governance spec final sign-off
4. PA spec + E1 IMPL + E2 + E4 + QA + PM 鏈條 ~50-78 hr 並行

**不可單獨於 §4.1.1 之前 dispatch**。

---

## §3 v5.7 baseline 收口 audit

### §3.1 v5.7 「12 prefix」是什麼？

per TODO §1.1 line 28：
> Sprint 1A-α   DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED (W0-1.5, 2026-05-21 PM-signed)  v5.7 12 prefix + PM signoff

per PA v57_dispatch_consolidation §50-62 行 + PA v57_12_prefix_tech_verify §1：

**「12 prefix」= Sprint 1A-α C1-C12 12 個 dispatch must-fix**：

| # | Prefix | 內容 | Status（per Sprint 4+ 2026-05-23 audit）|
|---|---|---|---|
| C1 | TODO §-0 + git tree | v5.7 主檔 land `docs/execution_plan/2026-05-20--execution-plan-v5.7.md` | ✅ DONE |
| C2 | 4 ADR draft（0030/0031/0032/0033） | 4 file land in `docs/adr/` | ✅ DONE |
| C3 | V103/V104 schema spec | `docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` 52K | ✅ DONE |
| C4 | Bybit Earn API endpoint 存在性 | BB verdict (a) API exists + 12 endpoint | ✅ DONE |
| C5 | Bybit Earn API key scope | BB verdict (a) non-withdraw `Earn` scope | ✅ DONE（operator 查 D+1 5 min 仍 pending） |
| C6 | liquidation writer 24h PROOF | BB verdict PG empirical 31,473 rows 3.7 day → 推翻 v57 Risk 1 BLOCKED | ✅ DONE |
| C7 | Sprint 1B C10 reframe Stage 0R + Stage 1 Demo | Sprint 1A dispatch packet §1 + Stage 真實 live 排程表 | ✅ DESIGN-DONE；本 audit Pending 3.1 = C7 對應 IMPL |
| C8 | Earn governance spec | `docs/execution_plan/2026-05-21--earn_governance_spec.md` 30K | ✅ DESIGN-DONE；本 audit Pending 3.2 = C8 對應 IMPL |
| C9 | V103/V104 Linux PG dry-run | `docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md` | ✅ DONE |
| C10 | 工時上修 + 並行 sub-agent mandate | dispatch_packet §2 + 39 週 calendar | ✅ DONE |
| C11 | Apple Silicon CI tuple | dispatch_packet §3 + R4 cross-ADR audit 修正 | ✅ DONE（per Sprint 1A-ε R4 patches）|
| C12 | 中文注釋 + SCRIPT_INDEX + MODULE_NOTE | dispatch_packet §4 + enforce grep | ✅ DONE |

**12/12 ✅ DONE**（per Sprint 1A-α PM sign-off commit `26ee2f06` + Wave 2 `77d5c54e` + Wave 2.5 `957491ee` + Sprint 1A-β/γ/δ/ε/ζ closure chain）。

### §3.2 已完成 via 後續 Sprint mapping

| C# | DESIGN-DONE | IMPL-DONE | Sprint |
|---|---|---|---|
| C1 | ✅ 2026-05-21 | ✅ runtime（v5.7 主檔 in git）| 1A-α |
| C2 | ✅ 2026-05-21（4 ADR）| ✅ docs runtime | 1A-α |
| C3 | ✅ V103/V104 schema spec | ⏳ V104 .sql NOT land；V103 land Sprint 1A-ζ；V099/V100/V101 base table audit pending Sprint 4+ §4.1.1 | 1A-ζ partial |
| C4 | ✅ BB verdict | n/a（read-only verify task）| – |
| C5 | ✅ BB verdict | ⏳ operator D+1 5 min check pending | – |
| C6 | ✅ BB verdict | n/a（既有 writer active）| – |
| C7 | ✅ Stage 排程表 | ⏳ **本 audit Pending 3.1** = C7 對應 strategy IMPL | – |
| C8 | ✅ Earn governance spec | ⏳ **本 audit Pending 3.2** = C8 對應 IMPL | – |
| C9 | ✅ PA PG dry-run report | n/a（read-only verify task）| – |
| C10 | ✅ 工時 + mandate | n/a（計劃文檔）| – |
| C11 | ✅ CI tuple condition + R4 patches | n/a（已 enforce in dispatch packet）| 1A-ε |
| C12 | ✅ 注釋 mandate | n/a（已 enforce per E2 review）| 1A-α |

### §3.3 真實剩餘工作

**「v5.7 baseline 收口」字面理解 = 12 prefix 全 closure**：

**12/12 ✅ DONE**（DESIGN 級別 + 5 個 file/docs 級別 IMPL 全 land）。

**真實「剩」的 work**：

| # | 工作 | 屬性 | 對應 章節 |
|---|---|---|---|
| 1 | C7 Sprint 1B C10 Stage 1 Demo strategy IMPL | **不是 baseline 收口**，是新策略 IMPL | **Pending 3.1**（本 audit C10 章節）|
| 2 | C8 Earn first stake IMPL | **不是 baseline 收口**，是新功能 IMPL | **Pending 3.2**（本 audit Earn 章節）|
| 3 | operator D+1 OpenClaw key 5 min query（C5 carry-over） | **operator-bound action**，不是 IMPL | Sprint 1B late operator action |
| 4 | operator D+5 Console tab 4 sub-section 歸屬決策（Sprint 1A-β D+5 12-check #9） | **operator-bound action**，不是 IMPL | Sprint 1B late operator action |
| 5 | V99-V102 base table audit（含 `learning.earn_movement_log` V099 假設名）| Sprint 4+ §4.1.1 已 routing | Sprint 1B late §4.1.1 |
| 6 | V104 .sql 從 spec 變 file land | per `P1-PG-CHECKSUM-ALIGNMENT-DECISION-2-C`（TODO §5.1） | Sprint 2 deploy window |

**「v5.7 baseline 收口」這個命名是 misnomer**。真實的「baseline 收口」工作已被吸收到：
- Pending 3.1（C10 strategy IMPL）
- Pending 3.2（Earn first stake IMPL）
- Sprint 4+ §4.1.1 V99-V102 base table audit
- Sprint 2 V104 deploy
- operator D+1 + D+5 action

### §3.4 verdict

**v5.7 baseline 收口** = **誤導命名 → 真實狀態 12/12 ✅ DONE**。

**建議**：
1. **TODO §1.2 line 61** 措辭修正：
   - 從：`v5.7 baseline + C10 Stage 1 Demo + Earn first stake + M3 partial`
   - 到：`C10 Stage 1 Demo + Earn first stake + M3 partial`（移除 「v5.7 baseline」措辭，避 misnomer 阻 dispatch judgement）
2. **PM Phase 3e §5.3** 同步措辭修正：
   - 從：「v5.7 baseline 收口」
   - 到：「Sprint 1A-α C1-C12 已 12/12 closure；剩餘 operator D+1 OpenClaw key 5 min query + D+5 Console tab 決策」
3. **不單獨 dispatch** 任何 sub-agent 做「v5.7 baseline 收口」工作；僅 operator 拍 D+1 D+5 兩個 action 即「收口」

---

## §4 3 章節 dispatch plan

### §4.1 Pending 3.1 — C10 funding harvest Stage 1 Demo

**chain**：PA spec → E1 IMPL（並行 #2 #3 #4） → E2 review → E4 regression → QA Stage 0R + Stage 1 Demo Acceptance → PM closure

**dispatch readiness verdict**：**READY-TO-DISPATCH**（不阻塞 Sprint 4+ §4.1.1 V99-V102 base table audit；C10 strategy IMPL 不依賴 earn_movement_log；spot leg paper-only emulation 自包含）

**並行 sub-agent dispatch 設計**：

```
Wave A（並行，wall-clock 4-6 hr）
├─ PA1: C10 funding harvest strategy spec（8-12 hr）
└─ PA2: Stage 0R replay preflight C10 spot paper sim harness spec（per PA1 完成後跟）

Wave B（並行，wall-clock 1.5-2 day）
├─ E1a: strategies/funding_harvest/ 新 module IMPL（18-26 hr）
├─ E1b: risk_config TOML + strategy_params TOML 接線（1-2 hr）
├─ E1c: Stage 0R replay preflight harness IMPL（8-12 hr）
└─ QC: delta-neutral 數學驗證 + replay PnL 偏離 1% 閾值 calibration（2-4 hr 並行）

Wave C（sequential 1 day）
├─ E2 round 1: adversarial review（2-3 hr）
└─ E1: round 2 fix（0-4 hr）

Wave D（並行 0.5 day）
├─ E4: cargo + pytest + integration regression（1-2 hr）
└─ QA: Stage 0R + Stage 1 Demo Acceptance（2-4 hr）

Wave E（sequential 0.5 day）
└─ PM: Phase 3e sign-off（1 hr）
```

**estimated effort**：~41-62 hr core + 並行 sub-agent wall-clock 3-4 day。

**Operator decision points**：
- 無（C10 strategy IMPL 純內部 design + IMPL；Stage 1 Demo size $100 cap + spot paper-only 已 FA 決議 acceptance）
- 偶有 PA + QC adversarial review verdict 衝突時，operator 仲裁 1 次 ~10 min

**前置 / 後置依賴**：
- 前置：無（C10 strategy 不依賴 V99-V102 audit；不依賴 Earn first stake；不依賴 production engine V107/V112）
- 後置：阻 Sprint 2 Alpha Tournament cohort 加入 C10（Stage 1 Demo 7d 結果決定 Stage 2 14d gate）

### §4.2 Pending 3.2 — Earn first stake

**chain**：operator decision → PA spec + V099/V100 base table closure 雙前置 → E1 IMPL（並行 #3 #4 #5 #7 #8）→ E2 + BB + E3 review → E4 regression → QA Earn first stake Acceptance → PM closure

**dispatch readiness verdict**：**NEEDS-OPERATOR-DECISION**（D+1 5 min OpenClaw key query + first stake $200-400 拍板）+ **DEPENDS-ON-§4.1.1**（V99-V102 base table audit + earn_movement_log schema land）

**並行 sub-agent dispatch 設計**：

```
Wave 0（operator action, ~30 min）
├─ operator: D+1 OpenClaw key 發行日 5 min query
├─ operator: 拍 first stake $200-400 + flexible/fixed
└─ operator: 拍 Earn governance spec final sign-off（CC + 4 agent cross-ref）

Wave A（並行，wall-clock 0.5-1 day）
├─ PA1: Bybit Earn API client + IntentProcessor enum + LeaseScope extension 接線 spec（6-8 hr）
├─ PA2: V099 (假設名) earn_movement_log table schema spec + Linux PG dry-run（4-6 hr；前置 §4.1.1 closure）
└─ CC + FA + E3 + QA + MIT: earn_governance spec 五角色 cross-ref final sign-off（4-6 hr 並行）

Wave B（並行，wall-clock 2-3 day；前置 Wave A 完成）
├─ E1a: rust/openclaw_engine/src/bybit_earn_client.rs 新建（10-15 hr）
├─ E1b: IntentProcessor::IntentType enum 新建 + OrderIntent struct extension（4-6 hr）
├─ E1c: LeaseScope::EarnStake + EarnRedeem variant + SQL CHECK constraint（2-3 hr）
├─ E1d: Daily reconciliation cron + mismatch disable 邏輯（4-6 hr）
└─ E1a (GUI): governance tab Earn manual stake form + type-to-confirm + A3 wizard（8-12 hr；阻於 H2 Console tab 決策）

Wave C（並行 0.5-1 day）
├─ E2: adversarial review（3-5 hr）
├─ BB: Bybit ToS / KYC / 地理 review（1-2 hr）
└─ E3: secret slot 治理 + Bybit key scope 重發確認 review（1-2 hr）

Wave D（sequential 0.5 day）
├─ E1: round 2 fix（0-4 hr）
└─ E4: regression（1-2 hr）

Wave E（並行 0.5 day）
├─ QA: Earn first stake Acceptance + 5-gate boundary verify（2-4 hr）
└─ operator: GUI manual stake $200 first execution + verify learning.earn_movement_log row insert（10-30 min）

Wave F（sequential 0.5 day）
└─ PM: Phase 3e sign-off（1 hr）
```

**estimated effort**：~50-78 hr core + 並行 sub-agent wall-clock 4-6 day + operator parallel actions ~45 min。

**Operator decision points**：
1. D+1 OpenClaw key 發行日 query verdict（5 min）
2. first stake $200-400 + flexible/fixed 拍板（10 min）
3. Earn governance spec final approve（5 min）
4. Wave E GUI manual stake first execution + verify（10-30 min）
5. （若 key 2026-04-09 前發）重發 key + 三端同步（30-60 min）

**前置 / 後置依賴**：
- 前置 P0：
  1. Sprint 4+ §4.1.1 V99-V102 base table audit + V099 earn_movement_log schema land
  2. operator D+1 OpenClaw key query
  3. earn_governance spec final sign-off
- 後置：
  1. Sprint 4+ §4.4 Earn auto-redeem trigger Sprint 5+ Stage 2 cascade
  2. Sprint 2 Earn first stake daily reconciliation cron 7d evidence accumulation

### §4.3 Pending 3.3 — v5.7 baseline 收口

**chain**：N/A — **DOWNGRADE-TO-NON-WORK**

**verdict**：**不單獨 dispatch sub-agent**。實質工作 = TODO §1.2 line 61 措辭修正 + operator D+1 + D+5 兩 action 完成即「收口」。

**操作**：
1. PA 報告（本 audit）建議 TODO §1.2 line 61 措辭修正
2. PM 接受 verdict 後修 TODO line 61（操作 ~5 min）
3. operator D+1 + D+5 兩 action 完成（已 TODO §1.4 active）
4. 「收口」自動完成；不需 dispatch

### §4.4 3 章節並行性 / 依賴矩陣

| 章節 | 可獨立並行? | 依賴 §4.1.1 | 依賴 operator action | 依賴 其他章節 |
|---|---|---|---|---|
| Pending 3.1 C10 Stage 1 Demo | **YES**（完全自包含） | 否 | 否 | 否 |
| Pending 3.2 Earn first stake | 否 | **YES**（V099 earn_movement_log）| **YES**（D+1 5 min + 拍板 + 4 review approve）| 否（C10 / baseline 都不依賴）|
| Pending 3.3 v5.7 baseline 收口 | n/a（DOWNGRADE） | 否 | 否 | 否 |

**結論**：
- **Pending 3.1 C10 Stage 1 Demo 可即刻並行 dispatch**（無前置阻塞）
- **Pending 3.2 Earn first stake** 必前置 §4.1.1 closure + operator D+1 action；但可與 Pending 3.1 並行 prep（PA spec + earn_governance final sign-off）
- **Pending 3.3 v5.7 baseline 收口** 不需 dispatch；TODO 措辭修正即 closure

---

## §5 Sprint 1B 剩 3 章節 readiness verdict

### §5.1 Overall readiness verdict

**PASS WITH 2 OPERATOR-BOUND ACTION**

- **Pending 3.1 C10 Stage 1 Demo**：✅ **READY-TO-DISPATCH**（estimate 41-62 hr / 並行 3-4 day；無前置阻塞）
- **Pending 3.2 Earn first stake**：⏳ **NEEDS-OPERATOR-DECISION + DEPENDS-ON-§4.1.1**（estimate 50-78 hr / 並行 4-6 day；前置 D+1 5 min + V99-V102 audit closure + governance spec final sign-off）
- **Pending 3.3 v5.7 baseline 收口**：✅ **DOWNGRADE-TO-NON-WORK**（misnomer；不單獨 dispatch；TODO 措辭修正即 closure）

### §5.2 PM 拍板路徑建議

**路徑 A — 先 C10 後 Earn**（per operator 「先做 1 部分做完進 2」邏輯）：
1. **W+0**：dispatch Pending 3.1 C10 Stage 1 Demo（並行 3-4 day）
2. **W+0 並行**：operator D+1 OpenClaw key 5 min query + governance spec final sign-off prep
3. **W+0 並行**：Sprint 4+ §4.1.1 V99-V102 base table audit dispatch（與 C10 並行）
4. **W+1（C10 closure 後）**：dispatch Pending 3.2 Earn first stake（並行 4-6 day）
5. **W+1.5（同時）**：PM 修 TODO §1.2 line 61 措辭（5 min；v5.7 baseline 收口 自動 closure）

**路徑 B — C10 + Earn 雙並行**（per PA dispatch packet §2 50-60% workload 走並行 sub-agent mandate）：
1. **W+0**：同時 dispatch Pending 3.1 C10 + Pending 3.2 Earn first stake（Earn 等 §4.1.1 + operator D+1）
2. **W+0 並行**：operator D+1 + §4.1.1 + governance spec final sign-off
3. **W+1（C10 closure）**：Earn 進 Wave B IMPL
4. **W+1.5**：兩章節同步 closure

**路徑 C — 暫停 Pending 3.2 + 只做 Pending 3.1**：
1. **W+0**：dispatch Pending 3.1 C10 only
2. **operator 暫不拍 first stake**：Sprint 1B 末 Earn first stake 推遲至 Sprint 1B 結束後
3. **W+1**：C10 closure；Sprint 1B late §4.1.1 + Sprint 5+ cascade IMPL 接力

**PA 建議路徑 A**：
- C10 strategy 是 Sprint 1B 唯一可立即 dispatch 的 IMPL（無前置阻塞）
- Earn first stake 阻於 §4.1.1 + operator D+1，需 prep 期；同 wall-clock 跑等於浪費 sub-agent 帶寬
- 路徑 A 工時總 ~110-130 hr core / 並行 6-8 day；路徑 B 並發 wall-clock 5-6 day 但 sub-agent 帶寬 peak 高，operator 並行 review 負荷重
- 路徑 C 過保守，浪費 Sprint 1B late 唯一 IMPL 窗口

### §5.3 Risk 紀要

| Risk | 嚴重度 | 緩解 |
|---|---|---|
| Pending 3.2 阻於 §4.1.1（V99-V102 base table audit + V099/V100 IMPL）| HIGH | §4.1.1 PA spec 4-6 hr + E1 IMPL 6-8 hr 已 routing to Sprint 1B late P0；可並行 C10 IMPL 期間 prep |
| operator D+1 OpenClaw key 過期或需重發 | MED | per BB C5 verdict (a) non-withdraw scope sufficient；若需重發 30-60 min operator action（已 TODO §1.4 active）|
| C10 spot leg paper-only emulation 邊界 — Stage 4 LIVE 升級時轉 live spot order 路徑未驗 | MED | Sprint 5+ cascade IMPL window；Stage 1-3 Demo 7d/14d/21d gate 期間 PA + E1 在 4-5 hr buffer 完成 live spot order 接 IntentProcessor 路徑 spec |
| C10 替代既有 funding_arb V2 dormant slot — 命名衝突 | LOW | 維持 funding_arb.rs dormant marker + 新建 funding_harvest/ 並列；docs 補 cross-ref note |
| Sprint 1B「baseline 收口」措辭誤導其他 sub-agent / operator | LOW | 本 audit §3 + TODO §1.2 line 61 措辭修正 |
| Pending 3.1 + 3.2 並行 sub-agent 帶寬超過 5 並行 mandate ceiling | MED | 建議路徑 A 序列 dispatch；若路徑 B 則 PM 主動 traffic shape |

### §5.4 Sprint 1B 剩 3 章節 收口時序

```
W+0 ──→ PA dispatch Pending 3.1 C10（並行）+ §4.1.1 V99-V102 audit dispatch（並行）
        operator D+1 OpenClaw key 5 min query
        CC + 4 agent earn_governance spec final sign-off（並行）

W+0.5 ─→ TODO §1.2 line 61 措辭修正（5 min PM 操作）
        Pending 3.3 v5.7 baseline 收口 ✅ closure（自動）

W+1 ──→ Pending 3.1 C10 Stage 1 Demo 進 QA + PM signoff
        §4.1.1 V99-V102 audit closure
        earn_governance spec sign-off

W+1.5 ─→ dispatch Pending 3.2 Earn first stake（PA + E1 Wave A）
        operator first stake $200-400 + flexible/fixed 拍板

W+2 ──→ Pending 3.2 Wave B IMPL（並行 sub-agent 5+ 條）

W+2.5 ─→ Pending 3.2 進 QA + operator first stake 執行 + PM signoff
        Sprint 1B late 全 closure
```

**整體 wall-clock**：~2-3 weeks（per Sprint 1B (full) W9-12 165-220 hr range；含 Sprint 4+ §4.1.1 base table audit 並行）

---

## §6 PA 對 PM 的 dispatch 建議

### §6.1 立即 dispatch（W+0）

1. **Pending 3.1 C10 Stage 1 Demo**：PA dispatch packet 起草（PA 自己 1-2 hr）→ 5-7 並行 sub-agent dispatch chain
2. **Sprint 4+ §4.1.1 V99-V102 base table audit + V099 earn_movement_log spec**：與 C10 並行
3. **CC + 4 agent earn_governance spec final sign-off**：與 C10 並行

### §6.2 W+0 完成後

1. **TODO §1.2 line 61 措辭修正**：5 min PM 操作 → **Pending 3.3 v5.7 baseline 收口 自動 closure**
2. **operator D+1 OpenClaw key 5 min query**：operator 親手；同 wall-clock 跑

### §6.3 W+1 完成（C10 + §4.1.1 + governance spec sign-off）後

1. **operator first stake $200-400 + flexible/fixed 拍板**：10 min
2. **Pending 3.2 Earn first stake dispatch**：5-7 並行 sub-agent

### §6.4 risk 紅線

- ❌ **不可** 在 §4.1.1 closure 前 dispatch Pending 3.2 IMPL Wave B（Earn API client + IntentProcessor + LeaseScope IMPL 必依賴 earn_movement_log schema）
- ❌ **不可** 跳過 earn_governance spec 五角色 cross-ref 直接 IMPL Wave B（spec status DRAFT-FOR-FIVE-ROLE-CROSS-REF）
- ❌ **不可** 在 C10 Stage 0R replay preflight FAIL 後 直接進 Stage 1 Demo（per AMD-2026-05-15-01 graduated canary gate）
- ❌ **不可** 將 spot leg paper-only 模擬視為 Stage 4 LIVE spot order 路徑 ready（Stage 4 LIVE spot order path 屬 Sprint 5+ cascade IMPL §4.2/§4.3）

---

## §7 PA 4 條完成回報

### 7.1 C10 funding harvest Stage 1 Demo audit + 既有 IMPL 狀態

- **0 既有 C10 IMPL**（grep 0 hit；strategies/mod.rs 無 funding_harvest）
- 既有 funding_arb.rs 是 V2 directional dormant per ADR-0018，與 C10 delta-neutral 完全不同概念，保留為 R-02 重設計 slot marker
- C10 funding harvest = 新建 Rust strategy + spot leg paper-only emulation；Bybit demo 不支援 spot lending 是 Stage 1-3 demo 灰度核心技術難點
- Stage 1 Demo 部署實質工作 ~41-62 hr / 並行 3-4 day（PA spec + Rust strategy + paper sim + risk_config + Stage 0R replay preflight harness + E2/E4/QA/PM 全鏈）
- **dispatch readiness**：✅ **READY-TO-DISPATCH**（無前置阻塞；可即刻並行 dispatch）

### 7.2 Earn first stake audit + Bybit Earn API gap

- **0 既有 Bybit Earn API client IMPL**（12 endpoint 全缺；既有 bybit_rest_client.rs 僅有 `/v5/spot-*` rate limit path detection，無真實 spot/Earn 訂單路徑）
- Gap：
  1. Bybit Earn 12 endpoint client（**0/12**）
  2. IntentProcessor::IntentType enum 新建（既有 OrderIntent 無 IntentType field）
  3. LeaseScope::EarnStake + EarnRedeem variant（既有 4 variant only）
  4. `learning.earn_movement_log` table（V103 是 M4 hypothesis 不是 earn；V099/V100 audit pending Sprint 4+ §4.1.1）
  5. Bybit demo Earn endpoint 支援 unverified（per BB C4 §96 smoke pending）
  6. OpenClaw API key `Earn` scope 待 operator D+1 5 min query
  7. earn_governance spec 五角色 cross-ref final sign-off（DRAFT）
- Earn first stake 部署實質工作 ~50-78 hr / 並行 4-6 day + operator parallel action ~45 min
- **dispatch readiness**：⏳ **NEEDS-OPERATOR-DECISION + DEPENDS-ON-§4.1.1**（前置 Sprint 4+ §4.1.1 V99-V102 base table audit + earn_movement_log schema land + operator D+1 + governance spec final sign-off）

### 7.3 v5.7 baseline 收口 audit + 真實剩餘工作

- v5.7 「12 prefix」= Sprint 1A-α C1-C12 12 個 dispatch must-fix（governance + V103/V104 spec + Bybit Earn verdict + Stage reframe + 工時上修 + CI tuple + 注釋 mandate）
- **12/12 ✅ DONE** via Sprint 1A-α PM sign-off + Wave 2 + Wave 2.5 + 1A-β/γ/δ/ε/ζ closure chain
- 真實「剩」的工作：
  1. Pending 3.1 C10 IMPL（= C7 對應；本 audit Pending 3.1）
  2. Pending 3.2 Earn IMPL（= C8 對應；本 audit Pending 3.2）
  3. operator D+1 OpenClaw key 5 min query（C5 carry-over；TODO §1.4 active）
  4. operator D+5 Console tab 4 sub-section 歸屬決策（Sprint 1A-β D+5 12-check #9）
  5. Sprint 4+ §4.1.1 V99-V102 base table audit（含 earn_movement_log）
  6. Sprint 2 V104 .sql land + checksum alignment
- **「v5.7 baseline 收口」是 misnomer**；真實剩餘工作已被 Pending 3.1/3.2 + §4.1.1 + operator action 吸收
- **dispatch readiness**：✅ **DOWNGRADE-TO-NON-WORK**（建議 TODO §1.2 line 61 措辭修正 + PM Phase 3e §5.3 同步 措辭修正；不單獨 dispatch）

### 7.4 3 章節 dispatch plan + Sprint 1B 剩 3 章節 readiness verdict

**dispatch plan**：

| 章節 | dispatch readiness | chain | estimated effort | operator decision points |
|---|---|---|---|---|
| Pending 3.1 C10 Stage 1 Demo | ✅ READY-TO-DISPATCH | PA → E1×3 並行 → E2 → E4 → QA → PM | ~41-62 hr / 並行 3-4 day | 無（內部 design + IMPL） |
| Pending 3.2 Earn first stake | ⏳ NEEDS-OPERATOR-DECISION + DEPENDS-ON-§4.1.1 | operator action → PA + 五角色 cross-ref → E1×5 並行 → E2 + BB + E3 → E4 + QA → PM | ~50-78 hr / 並行 4-6 day | 4 個（D+1 query / first stake 拍板 / governance final sign / stake 執行）|
| Pending 3.3 v5.7 baseline 收口 | ✅ DOWNGRADE-TO-NON-WORK | TODO 措辭修正（PM 5 min）| ~5 min | 無 |

**Sprint 1B 剩 3 章節 readiness verdict**：**PASS WITH 2 OPERATOR-BOUND ACTION**

- **PA 推薦路徑 A**（先 C10 後 Earn 序列 dispatch；§4.1.1 + earn_governance prep 並行）
- **整體 wall-clock**：~2-3 weeks
- **整體 effort**：~110-130 hr core + 並行 sub-agent + operator ~45 min

---

**END OF PA Sprint 1B 剩 3 章節 audit + dispatch plan**
