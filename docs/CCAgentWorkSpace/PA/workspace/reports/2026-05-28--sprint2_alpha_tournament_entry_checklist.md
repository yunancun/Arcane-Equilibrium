# Sprint 2 Alpha Tournament 啟動 Entry Checklist + Ratify-or-Reject Gates

**Date**: 2026-05-28
**Author**: PA（背景任務；不諮詢其他 agent，本 task 與 grill-me main session 平行；produce 後交叉驗證）
**Source SoT 對齊**:
- Alpha Tournament SSOT: `srv/docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`
- Sprint 2 dispatch packet: `srv/docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md`
- W2-A pre-spec finalize: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--w2a_alpha_tournament_pre_spec_finalize.md`
- v5.8 §4 + §10.5 P0 precondition: `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- AMD-2026-05-15-01 Stage 0R replay preflight: `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- AMD-2026-05-26-01 funding_arb retirement
- AMD-2026-05-21-01 v2 Layered Autonomy / ADR-0034 LAL
- ADR-0044 / ADR-0045 / ADR-0026 direct_exploit / ADR-0008 Decision Lease
- TODO v76（2026-05-28 HEAD `920f8299`）

**Runtime evidence**: 2026-05-28 SSH empirical (本 task pre-flight)
- demo+live_demo 14d fills by strategy (`ts` filter, non-risk-close):
  - grid_trading: 354 / ma_crossover: 89 / bb_reversion: 16 / bb_breakout: 2
  - funding_arb: 0（retired per AMD-26-01）
- demo+live_demo 7d avg_bps (excluding risk_close): grid -2.55 / ma -12.75 / bb_reversion -2.22 / bb_breakout +33.11 (n=2 noise) — **0/4 textbook 達 AC-A (i)**
- runtime live_demo 7d net = −1.99 USDT（不滿足 AC-A (iii) portfolio gross 正向）
- `replay.experiments` total=23 / last_age=407h（M11 Track C 0 cron）

**Status**: PA INDEPENDENT — Sprint 2 啟動條件審計 + 軟化路徑分析

---

## §0 TL;DR — Verdict

### Sprint 2 啟動 verdict: **CONDITIONAL GO（Wave 1 spec/IMPL 啟動）+ HARD STOP at promotion gate**

**核心判定**：
- Sprint 2 = **evidence machine + DRAFT writeback 路徑**，不直接觸 live、不直接寫 RiskConfig、不繞 5-gate（per Alpha Tournament SSOT §2/§7/§11 + AMD-2026-05-15-01 §3.2 forbidden output）
- 因此 Sprint 2 **W2-B 起 IMPL（Rust strategy struct + TOML default `active = false`）+ 14d demo accumulation** 不阻於 P0-EDGE/LG/OPS residual gate；這些 gate 阻的是 **Stage 0R replay preflight → Stage 1 demo micro-canary 晉升路徑** 與 **Sprint 4 first Live**
- 但 Sprint 2 SSOT §6 `stage0_ready` 輸出 vs `draft_only` 輸出 = 兩條完全不同的下游 chain：`stage0_ready` 必須卡住 Stage 0R replay preflight 6 sanity gate；`draft_only` 只走 V103 EXTEND DRAFT writeback
- Sprint 2 啟動 = **Wave 1 spec / Wave 2 IMPL + 14d demo evidence accumulation** 完全可以啟（不阻）；**Sprint 2 終局 Wave 3 stage0_ready 升等決策**才被以下 gate 阻

**Gate 分類結論**：
- **Ratify (現有 evidence 已可進入 Sprint 2 Wave 1 dispatch)**: **10 個**
- **Reject (必收齊才能 Sprint 2 stage0_ready 出口)**: **6 個**
- **Conditional (軟化或繞行)**: **5 個**

**verdict**: **CONDITIONAL GO** — Wave 1+2 dispatch 不需要等任何 P0 closure；Wave 3 出口（stage0_ready）需 6 個 Reject gate 全收口。

---

## §1 Entry Gate 列表（按必要程度排序）

### P0 Gate（Sprint 2 終局 stage0_ready 出口 hard blocker）

#### Gate-1: **P0-EDGE-1 root closure path 確認（不是 closure 本身）**
- **理由**: Alpha Tournament 存在的根本目的 = P0-EDGE-1 closure path (ii)；若 P0-EDGE-1 結構性無法 closure（例如 fee-adjusted edge 永遠負），Sprint 2 IMPL 是浪費 wall-clock 不是浪費治理。**但 Sprint 2 啟動 ≠ Sprint 2 證 P0-EDGE-1**；Sprint 2 = Sprint 2 給 Sprint 3+ 喂 evidence。
- **現狀**: 🔴 0/3 AC path satisfied
  - (i) **0/4 textbook** 達 demo 7d avg>5bps + Wilson lower>0 + n≥30
    - grid_trading n=68 但 avg_bps=−2.55（fail）
    - ma_crossover n=42 但 avg_bps=−12.75（fail）
    - bb_breakout n=2（insufficient sample）
    - bb_reversion n=6 demo+live_demo（insufficient sample）
  - (ii) Sprint 2 Alpha Tournament = 此 path 的唯一前置；待 Sprint 2 IMPL
  - (iii) live_demo 7d net = −1.99 USDT（fail portfolio 正向）
- **通過判據**: Sprint 2 Wave 3 出口 ≥1 candidate 達 demo 7d avg_net>5bps + Wilson CI lower>0 + n≥30；或 Sprint 3+ 接續
- **阻塞 ETA**: **Sprint 2 W12-15 Wave 3 ~D+21**（W2-B IMPL Wave 1 不阻）
- **作用**: Sprint 2 啟動 path (ii) 的 enabler；Gate-1 對 Wave 1 dispatch = **GO**（這 gate 反而 demand Sprint 2 啟動）

#### Gate-2: **Stage 0R Replay Preflight 6 sanity check pass-or-waiver**
- **理由**: per AMD-2026-05-15-01 §3.3：Sprint 2 任何候選若想升 `stage0_ready` 必先過 Stage 0R 6 sanity gate（Leak/Lookahead / Bias-Selection / DSR-PSR / PBO-Bootstrap / Replay data tier / Runtime boundary）。Sprint 2 SSOT §10 ACs 1+2 = IMPL + 14d demo accumulation；SSOT §6 `stage0_ready` 才阻 Stage 0R。
- **現狀**: ⚠️ M11 `replay.experiments` last_age=407h（17d stale）；replay_runner binary built but 0 cron；Stage 0R 路徑邏輯 spec'd 但 runtime evidence 0
- **通過判據**:
  - (a) `replay_runner` 重啟（per `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL` PA proposal pending）
  - (b) 各 candidate（funding_short_v2 + liquidation_cascade_fade）跑 Stage 0R 6 sanity，輸出 `eligible_for_demo_canary=true/false` + evidence packet
  - (c) leak/lookahead grep 證 `rolling(N).max()` 等 leakage 0 hit（per memory `feedback_indicator_lookahead_bias`）
- **阻塞 ETA**: Sprint 2 W3-A acceptance gate (D+18-21)；W2-B IMPL 不阻
- **作用**: Wave 1 dispatch **GO**；Wave 3 `stage0_ready` 出口 **REJECT** if missing

#### Gate-3: **5-Gate Live Boundary inheritance contract（W2-B IMPL 即須對齊）**
- **理由**: 16 原則 #4 Strategies cannot bypass Guardian + #5 Survival > Profit + AMD-25-02 + DOC-08 §12。Sprint 2 Rust strategy struct 即使 `active=false` default 也必繼承 5-gate；W1-A spec §4.1 寫明全 inherit
- **現狀**: ✅ W1-A spec §4.1 + W2-A §4.3 contract 完整：A `live_reserved` / B Operator role / C `OPENCLAW_ALLOW_MAINNET=1` / D valid secret slot / E signed authorization.json env match
- **通過判據**: W2-E E2 review grep `live_reserved|max_retries|live_execution_allowed|OPENCLAW_ALLOW_MAINNET|authorization\.json|execution_authority|execution_state|decision_lease_emitted` 在 IMPL diff = 0 hit on relaxation pattern；strategy 內 `active=false / enabled=false` TOML default
- **阻塞 ETA**: Sprint 2 W2-E E2 review (D+12-D+15)；W2-B IMPL 本身不阻但設計時必 honor
- **作用**: Wave 1 GO; Wave 2 IMPL 必 honor; Wave 3 review hard fail-closed

#### Gate-4: **Decision Lease + Guardian + V103 EXTEND DRAFT writeback 路徑（per ADR-0034 LAL）**
- **理由**: 16 原則 #3 AI 輸出 ≠ 命令；Sprint 2 SSOT §2 + §5 Governance gate hard reject；W2-A §4 + §3.5 = IMPL must honor V103 actual schema (`learning.hypotheses` + `hypothesis_source_module='M4_AUTO'` + state='draft')；不寫 `learning.m4_hypotheses_extended`（虛構）；不用 `alpha_short_carry / alpha_microstructure_fade` track（虛構）；必 track='direct_exploit' per ADR-0026
- **現狀**: ✅ W2-A 已 inline amend；W1-A spec v1.1 已 land；W2-E grep 守護寫明
- **通過判據**: W2-F MIT post-IMPL audit 跑 §3.5 INSERT pattern；W2-E grep `m4_hypotheses_extended` / `attribute_*` / `alpha_short_carry|alpha_microstructure_fade` = 0 hit；V103 EXTEND 6 column 全填；track='direct_exploit' 100% row
- **阻塞 ETA**: Wave 2 IMPL 本身有 spec 不阻；Wave 3 W2-F MIT audit (D+18-21)
- **作用**: Wave 1 GO；W2-B IMPL 必 honor W2-A 修正版 schema；Wave 3 hard fail-closed if leak

#### Gate-5: **P0-LG-3 V104 IMPL DISPATCH（supervised live SM）**
- **理由**: P0-LG-3 supervised live state machine 是**所有策略 supervised live activation gate**（per §15 #1 verdict reframe 2026-05-26）；funding_arb retired 與 LG-3 解耦；但 Sprint 2 candidate **Sprint 3+ 晉升 Stage 0R → Stage 1 demo canary 路徑 必經 LG-3**（每 candidate 必 supervised live gate）
- **現狀**: ⚠️ PA verify ✅ + MIT V104 dry-run ✅ 9/9 PASS + 2 bonus / Gate (2) UNBLOCKED 2026-05-27 / Gate (1) v56 P0 Layer B + 24h ~2026-05-30 待；Gate (3) MIT dry-run ✅ done；Gate (4) Option B race-aware dispatch
- **通過判據**: V104 actual apply + 24h soak post v56 P0 Layer B + IMPL DISPATCH（PA + E1 + MIT + E2 chain）
- **阻塞 ETA**: ~2026-05-30 V104 ready；Wave 2.4.A V104 apply 後 2 day Wave；Sprint 2 W2-B IMPL Wave 1+2 不阻（LG-3 是 Sprint 3+ Stage 0R → Stage 1 晉升才需）
- **作用**: Wave 1+2 GO（LG-3 不阻 Sprint 2 內 IMPL）；Wave 3 `stage0_ready` 出口若 candidate 不過 LG-3 supervised live = 不 stage0_ready；Sprint 3+ 晉升 hard fail-closed

#### Gate-6: **P0-OPS-1..4 Phase 2 cutover + restore drill**
- **理由**: OPS-1 HTTPS / OPS-2 cred rotation / OPS-3 legal / OPS-4 runbook 全 **不是 Sprint 2 IMPL precondition** 而是 **Sprint 4 first Live W17.5-20.5 precondition**（per v5.8 §10.5）。但 OPS-2 D+14 Phase 2 cutover (2026-06-10) 卡 14d soak；OPS-4 first restore drill 卡 backup/restore 可靠度
- **現狀**:
  - OPS-1 ✅ CLOSED 2026-05-28 by `22466a81`
  - OPS-2 ⚠️ Phase 1 SOURCE DONE 2026-05-27；Phase 2 cutover ETA 2026-06-10（D+14 soak）；14d soak D+1 0 fallback log
  - OPS-3 ✅ CLOSED 2026-05-26 sequential operator confirm 5/5
  - OPS-4 ⚠️ GAP-B pg_restore drill not exercised；GAP-D pg_dump cron land + first dump 4.6G PASS 2026-05-28
- **通過判據**: 
  - Sprint 2 IMPL：**完全不阻**（OPS gate target = Sprint 4 first Live not Sprint 2 evidence path）
  - Sprint 4 first Live：OPS-1+OPS-2 Phase 2 + OPS-4 restore drill + OPS-3 legal 全 closure
- **阻塞 ETA**: OPS-2 Phase 2 = 2026-06-10；OPS-4 first restore drill = operator timing call；Sprint 4 first Live = W17.5-20.5 (~2026-09)
- **作用**: Sprint 2 啟動 **GO**（不阻）；Sprint 2 → Sprint 3 transition 不阻；Sprint 4 first Live 阻

---

### P1 Gate（軟化路徑可行 / 部分阻 / 治理債）

#### Gate-7: **Live `/auth/renew` operator action（authorization_json missing）**
- **理由**: Live engine 目前 fail-closed `authorization_json_missing`（`[56] live_pipeline_active`）；live_demo + live mainnet 都 dead；只 demo engine alive。Sprint 2 demo evidence 不需要 live engine alive（Sprint 2 SSOT §2 engine_mode=Demo/LiveDemo only for promotion evidence；paper 排除）。
- **現狀**: ⚠️ `[56] live_pipeline_active = authorization_json_missing`；Operator-only signed `/auth/renew` flow（per CLAUDE.md §四 Hard Boundaries）；agent 不動
- **通過判據**: Operator OP-1-e + OP-1-f：ssh trade-core 鍵入 + 改 bybit_endpoint demo→mainnet + Python `/auth/renew` 簽 authorization.json（per TODO §7 D+2-D+3）
- **阻塞 ETA**: Operator hand-action timing（D+2-D+3 calendar 但 operator [1]=defer TOTP enrollment 預示也許延）
- **作用**: Sprint 2 demo+live_demo evidence path **GO**（live_demo 不需要 live engine alive，只需要 LiveDemo endpoint pipeline）；Sprint 4 first Live 阻
- **軟化路徑**: Sprint 2 純 demo evidence path 就足夠；live_demo 補強但非 hard requirement（W2-A §3.3 WHERE engine_mode IN ('demo', 'live_demo')）

#### Gate-8: **TOTP enrollment（per operator [1]=defer per 2026-05-28）**
- **理由**: Operator 拍 TOTP enrollment 等系統正式上線；TOTP backend source land + 10 pytest PASS；runtime vault missing → autonomy switch fail-closed by design
- **現狀**: 🟦 DEFERRED per operator decision；Autonomy Level 2 (Standard) 不可切換；Conservative (Level 1) by default 不受影響
- **通過判據**: 不適用 Sprint 2 啟動；TOTP enrollment 是 **Level 2 promotion gate** 不是 **tournament 入口 gate**
- **阻塞 ETA**: 不阻 Sprint 2
- **作用**: Sprint 2 啟動 **GO**；Sprint 2 alpha candidate 預設 Conservative Level 1 即可
- **軟化路徑**: Sprint 2 IMPL 在 Conservative Level 完整跑；Level 2 promotion 在 Sprint 3+ + TOTP enrollment 後再評

#### Gate-9: **M11 Track C replay_runner schedule（per operator [4]=b PA proposal pending）**
- **理由**: Stage 0R replay preflight 卡 Gate-2；replay_runner 23 row last_age=407h 證 M11 evidence 不續流；無 runner = candidate Stage 0R preflight 無法跑（per AMD-15-01 §3.3 6 sanity 需 replay infrastructure）
- **現狀**: 🟡 `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL` ticket NEW 2026-05-28；PA proposal pending；3 cadence option 待
- **通過判據**: PA proposal land + operator 拍 cadence（hourly/6h/daily/on-demand）+ E1 cron install
- **阻塞 ETA**: PA proposal 2-4 hr + operator 決策；總計 1-2 day
- **作用**: Sprint 2 W2-B IMPL **GO**（IMPL 不需要 replay 跑）；Sprint 2 Wave 3 `stage0_ready` 出口 **需要** Stage 0R replay preflight pass = M11 runner alive
- **軟化路徑**: Sprint 2 candidate 出 `draft_only` verdict（per SSOT §6）就不需要 Stage 0R preflight；只有 `stage0_ready` 必須 preflight pass

#### Gate-10: **Wave 5 Packet C engine integration（pipeline_ctor 未接）**
- **理由**: notification_failsafe module SOURCE LAND 920f8299 但 dead-code module（不接 pipeline_ctor）；SM-04 Defensive auto-escalate 未 runtime wire；alpha candidate runtime fail-safe 路徑不全（per AMD-21-01 v2 三路通知 fail → 1h wait → SM-04 Defensive）
- **現狀**: 🟡 SOURCE LAND + Linux rebuild GREEN 16:18 UTC；pipeline_ctor wire PENDING；engine notification timeout caller + exchange conditional SL sync + audit emit 缺
- **通過判據**: Packet C 真實 wire（pipeline_ctor 接線 + notification 3-way dispatcher + exchange conditional SL sync + audit emit）
- **阻塞 ETA**: 下一 Wave Packet C 真實接線；E1 IMPL ~ 16-30 hr per W4 estimate
- **作用**: Sprint 2 Conservative Level (Level 1) IMPL **GO**（不需要 SM-04 Defensive auto-escalate）；Level 2 + 多策略 portfolio fail-safe 需要 Packet C wire
- **軟化路徑**: Sprint 2 跑 Conservative + 單策略 micro-canary（per AMD-15-01 §4.1 Stage 1 = 1 strategy × 1 symbol × 7d），不需要 SM-04 auto-escalate runtime

---

### P2 Gate（治理 backlog / 不阻 Sprint 2）

#### Gate-11: **5 textbook strategy alpha-deficient 結構性問題 cope path**
- **理由**: 4/4 textbook (funding_arb retired) `insufficient_total_samples` 或 negative runtime_bps；P0-EDGE-1 AC-A (i) 路徑 5/11 verdict 已標 structural alpha-deficient；Sprint 2 IMPL 路徑 = (ii) 新 alpha source path
- **現狀**: 🟦 SSOT §3 B0 = 5 textbook 控制組 (control group)；不投 engineering 重啟動
- **通過判據**: Sprint 2 SSOT §2 鎖定 = baseline only；不需 Sprint 2 啟動前再驗
- **阻塞 ETA**: 不阻
- **作用**: GO；Sprint 2 啟動本身就是 5 textbook cope path（用新 alpha source 取代）
- **軟化路徑**: 5 textbook 繼續 demo 累積（不投新 engineering），funding_arb V2 已 deprecated commit 待 D+7 `#[deprecated]` IMPL；其餘 4 textbook 在 Sprint 2 期間轉 baseline / control group 角色

#### Gate-12: **demo 流量結構性不足（`[74]` close_maker_reject_samples）**
- **理由**: demo 7d `close_maker_attempt=TRUE` 17 rows 中 0 row matches `rate_limit_*` 或 `EC_ReachMaxPendingOrders` = `max_pending_samples=0` 結構性無法被 demo 流量觸發；Sprint 2 evidence path 流量訊號弱會影響 candidate evidence 累積速率
- **現狀**: ⚠️ `[74]` healthcheck FAIL；Sprint 2 SSOT §5 Sample gate n≥30 minimum bar；當前 grid_trading 354 row 14d ≈ 25/day = 14d 達標但 ma_crossover 89 row = 6.4/day 14d ≈ 89 達 30+；bb_breakout n=2 / bb_reversion n=16 結構性不足
- **通過判據**: Sprint 2 IMPL candidate（funding_short_v2 + liquidation_cascade_fade）達 n≥30 over 14d；BTC/ETH symbol coverage 提供 baseline 流量
- **阻塞 ETA**: 不阻 Sprint 2 啟動；Sprint 2 Wave 3 AC-S2-A-2 evidence accumulation 14d 後驗
- **作用**: GO；Sprint 2 candidate cohort 限 BTC+ETH 即可避開 alt thin-volume 流量問題
- **軟化路徑**: per Sprint 2 W1-A spec：funding_short_v2 cohort BTCUSDT+ETHUSDT only；liquidation_cascade_fade 同 cohort；流量足夠累積 30 fills/14d

#### Gate-13: **`authorization_json_missing` operator-only flag（不是 dev blocker）**
- **理由**: per TODO §0 三條 OPS residual 不反轉 OPS-1 closure；`[56]` operator-only；agent 不動
- **現狀**: 🟡 operator hand-action queue；TOTP defer + OP-1 a-f mainnet key reissue pending
- **通過判據**: Operator OP-1 series
- **阻塞 ETA**: 不阻 Sprint 2 evidence path（Sprint 2 demo only）
- **作用**: GO

#### Gate-14: **Sprint 1A-γ V111 land（Stream C 後端 Optuna 依賴）**
- **理由**: Sprint 2 Stream C (Optuna 後端 skeleton) 依賴 V111 land；per v5.8 §3 line 612 順序限制；Sprint 1A-γ 與 Sprint 2 並行需仲裁
- **現狀**: ⚠️ V111 spec 推遲 to Sprint 1A-γ Wave 1（per PA W2-A Stream C 推薦 §1.3 PM #2 = (a)）
- **通過判據**: Sprint 1A-γ V111 spec land 必先於 Sprint 2 Wave 1 W1-D；Stream C 後端 Optuna IMPL 不依賴 V111；W2-C V111 schema deploy 等 1A-γ V111 spec land
- **阻塞 ETA**: Sprint 1A-γ Wave 1 land timing
- **作用**: GO；Stream A (alpha tournament 2 candidate) 不依賴 V111；Stream C 可延後

#### Gate-15: **close_maker_audit table missing P1**
- **理由**: PA W2-A §6.4 verdict: 屬 Sprint 1B follow-up 非 Sprint 2 cross-cutting；trading.fills 已有 close_maker 兩 column
- **現狀**: ⚠️ `P1-LEARNING-CLOSE-MAKER-AUDIT-TABLE-MISSING` NEW 2026-05-25；E1 spec + V### migration ~4-6 hr
- **通過判據**: Sprint 1B follow-up；不阻 Sprint 2 evidence path
- **阻塞 ETA**: 不阻
- **作用**: GO

---

## §2 P0-EDGE / P0-LG / OPS prereq 矩陣

| Prereq | 種類 | 現狀 | Sprint 2 是否真阻 | 軟化路徑 | Owner |
|---|---|---|---|---|---|
| **P0-EDGE-1 (i) 4 textbook ≥3 達 demo 7d>5bps + Wilson + n≥30** | P0 | 🔴 0/4 達標 | **不阻 Sprint 2 啟動** — Sprint 2 = 路徑 (ii) 的 enabler；(i) failure 反而是啟動理由 | 路徑 (ii) Sprint 2 Alpha Tournament IMPL；textbook 維持 baseline | QC + PA |
| **P0-EDGE-1 (ii) ≥3 alpha-bearing 新 source 達同標** | P0 | 🔴 Sprint 2 待 IMPL | **不阻 Sprint 2 啟動** — Sprint 2 是這 path 的本體；Sprint 2 終局 Wave 3 出口才需要 1 個 candidate 達標 = AC-S2-A-3 partial closure | Sprint 2 IMPL 2 candidate + 14d demo accumulation；Sprint 3+ 再加 candidate | PA + E1 + MIT + QC |
| **P0-EDGE-1 (iii) portfolio 7d gross 正向** | P0 | 🔴 live_demo 7d net=-1.99 USDT | **不阻 Sprint 2 啟動** — Sprint 2 不直接動 portfolio sizing | Sprint 3+ M11 counterfactual replay attribution；Sprint 4+ first Live 後評 | QC |
| **P0-LG-3 V104 schema + IMPL DISPATCH** | P0 | ⚠️ PA verify ✅ + MIT 9/9 PASS + 2 bonus / Gate (2) UNBLOCKED 2026-05-27 / Gate (1) v56 P0 Layer B + 24h ~2026-05-30 待 / Gate (3) MIT dry-run ✅ done | **不阻 Sprint 2 IMPL Wave 1+2**（LG-3 是所有策略 supervised live activation gate；Sprint 2 demo evidence accumulation 不需 supervised live） / **阻 Sprint 2 → Sprint 3+ stage 1 demo canary 晉升** | 等 ~2026-05-30 v56 P0 Layer B + 24h；Wave 2.4.A IMPL Dispatch；Sprint 2 IMPL 期間 parallel | PA + E1 + MIT + E2 |
| **P0-OPS-1 HTTPS shadow cutover + enforcing-ready** | P0 | 🟢 CLOSED 2026-05-28 by `22466a81` | 不阻 | — | E1 + A3 |
| **P0-OPS-2 cred rotation Phase 2 cutover (D+14)** | P0 | ⚠️ Phase 1 SOURCE DONE 2026-05-27；14d soak D+1 0 fallback log；Phase 2 ETA 2026-06-10 | **不阻 Sprint 2 IMPL**；**阻 Sprint 4 first Live**（per v5.8 §10.5） | Sprint 2 evidence 路徑 demo+live_demo only 不需 mainnet key rotation | E1 + CC + BB |
| **P0-OPS-3 legal sign-off (5/5)** | P0 | 🟢 CLOSED 2026-05-26 sequential confirm | 不阻 | — | operator + BB |
| **P0-OPS-4 GAP-B first restore drill** | P0 | ⚠️ MIT SOP + post_restore_validation.sql + drill template land；first drill operator-blocked timing call；4.6G dump verify PASS | **不阻 Sprint 2 IMPL**；**阻 Sprint 4 first Live 信心**；不阻 evidence path | Sprint 2 期間 operator 排 low-trading window 跑 drill (4 hr per SOP scenario S1) | operator + MIT |
| **P0-OPS-4 GAP-D pg_dump cron + freshness** | P0 | 🟢 cron installed 2026-05-28 03:00 UTC；first dump 4.6G PASS | 不阻 | — | E1 + MIT |
| **Stage 0R Replay Preflight 6 sanity gate (per AMD-15-01)** | P0+ governance | ⚠️ `replay.experiments` last_age=407h；M11 Track C 0 cron | **不阻 W2-B IMPL**；**阻 Wave 3 stage0_ready 出口**；強 leak-free shift(1) + DSR/PSR + PBO + replay tier exclude synth + runtime boundary | M11 Track C replay_runner schedule proposal (PA pending)；W2-E E2 leakage scan grep | PA + E1 + MIT |
| **Live `/auth/renew` operator action** | P0 | 🔴 `authorization_json_missing` (OP-1 a-f pending) | **不阻 Sprint 2 demo evidence**；**阻 Sprint 4 first Live** | Sprint 2 IMPL 期間 demo only；Sprint 4 first Live 前 operator hand-action | operator |
| **TOTP enrollment（Autonomy Level 2 切換 only）** | P1 | 🟦 DEFERRED per operator [1] 2026-05-28 | **不阻 Sprint 2 啟動**；Sprint 2 跑 Conservative Level 1 即可 | Sprint 2 不依賴 Level 2；Level 2 promotion 是 Sprint 3+ + TOTP enrollment 後 | operator |
| **M11 Track C replay_runner schedule** | P2 | 🟡 PA proposal pending per operator [4]=b | **不阻 W2-B IMPL**；**阻 Wave 3 stage0_ready 出口 Stage 0R preflight 跑** | PA proposal 2-4 hr + operator 拍 cadence + E1 cron install；軟化 = Sprint 2 出 `draft_only` 不出 `stage0_ready` | PA + operator + E1 |
| **Wave 5 Packet C pipeline_ctor wire** | P1 | 🟡 SOURCE LAND + Linux rebuild GREEN；dead-code module；pipeline_ctor 不接 | **不阻 Sprint 2 Conservative Level 1 IMPL**；阻 Level 2 + SM-04 Defensive runtime | Sprint 2 跑 Conservative + 單策略 micro-canary | E1 + PA |
| **5 textbook structural alpha-deficient cope** | P2 | 🟦 SSOT §3 B0 baseline only | 不阻 | 5 textbook 維持 control group；funding_arb D+7 `#[deprecated]` IMPL | QC + E1 |
| **demo 流量結構性不足 `[74]`** | P2 | ⚠️ `max_pending_samples=0` | 不阻；BTC+ETH cohort 足夠累積 | Sprint 2 candidate cohort 限 BTC+ETH | (no owner; evidence-driven softening) |

---

## §3 Ratify-or-Reject Gates

### Ratify（已收齊 / Sprint 2 Wave 1 dispatch 可進）— 10 gate

1. **W2-A pre-spec finalize complete + 2 CRITICAL schema drift inline amend closed**（per W2-A report §13 + Step X closure 2026-05-25）
2. **W1-A 2 spec v1.1 land**（funding_short_v2 + liquidation_cascade_fade；track='direct_exploit' + V103 EXTEND schema 已修）
3. **Alpha Tournament SSOT spec final**（2026-05-26）— scoring contract / minimum evidence gate / Stage output / candidate pool all locked
4. **Sprint 2 dispatch packet land**（2026-05-25）— 5 stream × 7 並行 sub-agent；W1-3 wave timeline
5. **P0-OPS-1 CLOSED**（2026-05-28 by `22466a81`）— HTTPS shadow cutover + enforcing-ready；不阻 Sprint 2
6. **P0-OPS-3 CLOSED**（2026-05-26 operator confirm 5/5）— legal sign-off
7. **P0-OPS-4 GAP-D pg_dump cron + first dump**（2026-05-28 PASS）— backup infrastructure ready
8. **5-gate boundary inheritance contract（W1-A spec §4.1）**— W2-B IMPL 直接 inherit；Sprint 2 strategy 內 `active=false / enabled=false` TOML default
9. **funding_arb V2 retired closure（per AMD-26-01 + Workflow F closed）**— 5→4 textbook roster 收斂；Sprint 2 不再依賴 funding_arb V2 evidence
10. **Conservative (Level 1) Autonomy default + TOTP defer 不阻 Sprint 2**— Sprint 2 跑 Conservative Level 1 IMPL；Level 2 promotion 是 Sprint 3+ 議題

### Reject（必收齊才能 Sprint 2 stage0_ready 出口）— 6 gate

1. **Stage 0R Replay Preflight 6 sanity gate pass per candidate**（per AMD-15-01 §3.3）
   - 通過判據: `eligible_for_demo_canary=true/false` boolean + evidence packet per candidate；leak/lookahead grep PASS + DSR/PSR sane + PBO bootstrap stable + replay tier exclude synth-only + runtime boundary 不繞
   - 阻 Wave 3 stage0_ready；不阻 Wave 1+2

2. **M11 Track C replay_runner schedule active**（per `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL`）
   - 通過判據: PA proposal land + operator cadence 拍 + E1 cron install + `replay.experiments` rows 續流
   - 阻 Stage 0R preflight 6 sanity 跑；不阻 IMPL

3. **W2-E E2 adversarial review 18 focus point 全 PASS**（per W1-A spec §9 7+8 點 + W2-A §10 新增 3 點）
   - 通過判據: 18/18 review focus PASS；schema drift grep 0 hit；look-ahead bias proof；leak-free shift(1)
   - 阻 Wave 3；不阻 Wave 2 IMPL

4. **W2-F MIT post-IMPL audit + attribution_chain_ok 100% (per Sprint N+0 範式)**
   - 通過判據: track='direct_exploit' 100% rows；V103 EXTEND 6 column writeback；DRAFT state='draft' 不 auto-promote；attribution_chain_ok ≥ 90%
   - 阻 Wave 3；不阻 Wave 2

5. **AC-S2-A-3 ≥1 candidate 達 demo 7d avg_net > 5bps + Wilson CI > 0 + n≥30**
   - 通過判據: funding_short_v2 OR liquidation_cascade_fade 達 demo 7d threshold（per W1-A spec §8 AC-C1-7/8 + AC-C4-9/10）
   - 阻 Sprint 2 出 stage0_ready；軟化 = 出 `draft_only` 還可（Sprint 3+ 累積 evidence）

6. **W3-C TW + PM Sprint 2 acceptance sign-off**（per dispatch packet W3-C）
   - 通過判據: 5 AC main + 22 AC sub 全 PASS；3 PM decision points 全拍；docs/README + SPECIFICATION_REGISTER update
   - 阻 Sprint 2 closure；不阻 Sprint 2 啟動

### Conditional（軟化或繞行）— 5 gate

1. **P0-LG-3 V104 IMPL DISPATCH（per Gate-5）**
   - 條件: Sprint 2 Wave 1+2 不阻；Sprint 2 → Sprint 3 stage 1 demo canary 晉升才需
   - 軟化: Sprint 2 出 `draft_only` 不需 LG-3；出 `stage0_ready` 必 LG-3 active
   - reviewer: PA + E1 + MIT；ETA ~2026-05-30 V104 + 2 day Wave

2. **P0-OPS-2 Phase 2 cutover 2026-06-10**
   - 條件: 阻 Sprint 4 first Live；不阻 Sprint 2 evidence path
   - 軟化: Sprint 2 demo+live_demo only；不需 cred rotation Phase 2 完成
   - reviewer: E1 + CC + BB

3. **P0-OPS-4 first restore drill**
   - 條件: 阻 Sprint 4 first Live 信心；不阻 Sprint 2 IMPL
   - 軟化: Sprint 2 期間 operator 排 low-trading window；4 hr per SOP S1
   - reviewer: operator + MIT

4. **Wave 5 Packet C pipeline_ctor wire（per Gate-10）**
   - 條件: 阻 Level 2 + SM-04 Defensive runtime；不阻 Conservative Level 1
   - 軟化: Sprint 2 Conservative Level + 單策略 micro-canary
   - reviewer: E1 + PA

5. **Live `/auth/renew` operator action（per Gate-7）**
   - 條件: 阻 Sprint 4 first Live；不阻 Sprint 2 demo evidence
   - 軟化: Sprint 2 demo only；Sprint 4 前 operator hand-action
   - reviewer: operator

---

## §4 Sprint 2 Entry 後第一輪 Tournament 候選策略

### §4.1 既有策略 settled 100% chain_ok 結果（2026-05-28 SSH 14d empirical）

| Strategy | demo+live_demo 14d n | 7d avg_bps | Tournament 角色 | 進 Tournament? |
|---|---|---|---|---|
| **grid_trading** | 354 (242+112) | −2.55 (demo) / −2.57 (live_demo) | B0 baseline / control | ❌ NO — 不符 SSOT §3 B0 設計（baseline only）；avg_bps 結構性負；engineering 不投 |
| **ma_crossover** | 89 (71+18) | −12.75 (demo) / −22.93 (live_demo) | B0 baseline / control | ❌ NO — 同上；avg_bps 結構性負 |
| **bb_breakout** | 2 | +33.11 (demo n=2 noise) | B0 baseline / control | ❌ NO — sample 不足；不能用 n=2 PASS noise 升 candidate |
| **bb_reversion** | 16 (10+6) | −2.22 (demo) / +0.89 (live_demo n=2) | B0 baseline / control | ❌ NO — sample 不足 |
| **funding_arb** | 0 | retired | retired | ❌ NO — per AMD-26-01 deprecated |
| **C10 funding_harvest** | 0 demo（C10 Stage 1 dormant pending verdict） | n/a | A0 baseline / carry source（per SSOT §3） | 🟡 半進 — C10 是 baseline carry source，per SSOT §3 已 Sprint 2 觀察中；不是新 Tournament IMPL slot |

**結論**: **0 個既有策略可進 Sprint 2 tournament IMPL slot**。5 textbook 全標 baseline / control group（SSOT §3 B0）；funding_arb retired；C10 是 baseline carry source 觀察中（不是 IMPL slot）。

### §4.2 新策略提案 — Sprint 2 IMPL 2 candidate（per W1-A spec land 2026-05-25 + W2-A finalize 2026-05-25）

| ID | Candidate | Sprint 2 角色 | SSOT §3 引用 | Status |
|---|---|---|---|---|
| **A1** | **Funding Short-only v2** (funding_threshold_annualized=0.30；只 short side；BTC+ETH cohort) | Primary IMPL slot | A1 | ✅ W1-A spec v1.1 land；W2-A finalize；W2-B E1 IMPL dispatch ready (per W2-A §11.3 12 action checklist) |
| **A2** | **Liquidation Cascade Fade** (BTC threshold $500k 5m；ETH threshold $300k；isolated cluster + book recovery + PostOnly maker) | Primary IMPL slot | A2 | ✅ W1-A spec v1.1 land；W2-A finalize；W2-B E1 IMPL dispatch ready |
| **A3** | **BTC/ETH Cointegration Pairs** | DRAFT slot（stats-first；不 Sprint 2 IMPL） | A3 | 🟡 stats-first；需 cointegration + half-life precheck；Sprint 2 不 IMPL |
| **A4** | **C13 Defined-Risk Options / VRP** | defer Sprint 2-6 | A4 | 🟦 data/liquidity gate first |
| **A5** | **Token Unlock Short** | defer Sprint 3+ | A5 | 🟦 external unlock feed required |

**結論**: Sprint 2 IMPL 2 candidate + DRAFT 1 + defer 2；A1+A2 W2-B E1 IMPL 派發 ready per W2-A §11.3。

### §4.3 5 textbook strategy cope path

per SSOT §2 lock + 16 原則 #11（agent 在 P0/P1 邊界內自主）：

- **不投** Sprint 2 engineering 重啟動 5 textbook（per SSOT §2 + §11 explicit non-goal）
- **維持** 5 textbook baseline / control group 自然累積 demo data
- **funding_arb V2** D+7 (~2026-06-02) E1 `#[deprecated]` IMPL；retired 後 0 sample 累積
- **替換路徑** = Sprint 2 A1+A2 + Sprint 3+ A3+A4+A5 + Sprint 6+ M4 pattern miner stage 2 auto-discovery

---

## §5 對抗性 Push Back

### §5.1 「Sprint 2 不應現在啟動」反方論點 5 條（PA 自評）

#### Argument 1: P0-EDGE-1 路徑 (ii) 是雞蛋論
**論點**: Sprint 2 = P0-EDGE-1 路徑 (ii) closure path；但 Sprint 2 自己 也不過是 "Sprint 3+ 累積 evidence 的 enabler"；Sprint 2 → Sprint 3 → Sprint 4 first Live 鏈條長 ~5 month；每階段 funnel 都可能 fail。
**反駁**: 真實有 alternative。如果 Sprint 2 不啟，P0-EDGE-1 路徑 (i) 已 0/4，路徑 (iii) live_demo 7d net=−1.99 USDT 也 fail；Sprint 4 first Live 完全不會發生。Sprint 2 是**唯一可預期 closure path**（per TODO §1 line 53）。延遲啟動 = 把 Sprint 4 first Live 順移 ~6 week 或無限延期。
**Verdict**: 反駁站；Sprint 2 啟動是合理 ROI。

#### Argument 2: Stage 0R replay preflight 路徑直入應跳過 tournament framing
**論點**: AMD-15-01 §3 Stage 0R replay preflight 已是 supervised live 標準晉升路徑；為什麼還需要 Tournament framing？直接每個 candidate 跑 Stage 0R + Stage 1 demo micro-canary 不就好？
**反駁**: Alpha Tournament SSOT §1 明寫 = evidence machine（compare candidates under one scoring contract；reject fee-dragged or non-replayable ideas quickly；promote only candidates with demo evidence into Stage 0/Stage 0R planning）。Tournament framing 是**多 candidate 並行 + 統一 scoring + cross-cutting collision 防護**；如果直入 Stage 0R 一條條跑，**容易失去 cross-candidate 比較基準**（risk_adjusted_net_edge 排序）且**重複勞**（Stage 0R 路徑每 candidate 獨立跑同 6 sanity 不共享 evidence）。Tournament = 階段降本路徑。
**Verdict**: 反駁站；Tournament framing 對 Sprint 2 多 candidate 並行（A1+A2）有 ROI。但若 Sprint 2 只 IMPL 1 candidate，Tournament framing ROI 弱。
**修正**: Sprint 2 A1+A2 兩 candidate 並行才能 justify Tournament framing；如果某時刻 only A1 IMPL ready，回 Stage 0R 直入路徑 sense。

#### Argument 3: 14d demo evidence accumulation 對 Sprint 4 first Live 太薄
**論點**: Sprint 2 W2-A §3 + W1-A spec AC-S2-A-2 = n≥30 over 14d minimum bar；但 Sprint 4 first Live $500 需要的 evidence 量 = 至少 30d demo + ~$200 demo gross PnL stable + replay 100 events bootstrap 穩定；14d / 30 fills 太薄。
**反駁**: Sprint 2 不是 Sprint 4 first Live 的 evidence；Sprint 2 出 `stage0_ready` 是**走進 Stage 0R replay preflight + Stage 1 demo micro-canary** 的入場券，Stage 1 還有 7d demo 真實 fill-lineage evidence + Stage 2 demo extended 14d；Sprint 2 14d + Stage 1 7d + Stage 2 14d = 共 35d，加 Stage 0R replay preflight bootstrap，到 Sprint 4 first Live 前 evidence packet 充分。
**Verdict**: 反駁站；Sprint 2 14d 是**進入 Stage ladder 的最低門檻**不是 first Live 全部 evidence。

#### Argument 4: M11 Track C replay_runner 0 cron + Wave 5 Packet C pipeline_ctor 0 wire + LG-3 V104 未 land = 三條治理債積壓，先還債再啟 Sprint 2
**論點**: 啟 Sprint 2 = 增加新 candidate strategy；每個 strategy 走 demo evidence 累積 + Wave 3 stage0_ready 評估都需要 M11 replay + Packet C runtime fail-safe + LG-3 supervised live SM；三條都未 ready。先還債再啟 Sprint 2 比較乾淨。
**反駁**: 
1. M11 Track C 是 Wave 3 stage0_ready 出口阻塞，不是 Wave 1+2 IMPL 阻塞；Wave 1+2 ~D+12 wall-clock 期間 PA proposal + operator cadence + E1 cron install 1-2 day 足夠並行 land
2. Packet C pipeline_ctor wire 是 Level 2 + SM-04 Defensive auto-escalate 必要；Sprint 2 跑 Conservative Level 1 + 單策略 micro-canary（per AMD-15-01 §4.1）即可；Packet C 是 Sprint 3+ Level 2 promotion path 工作
3. LG-3 V104 ~2026-05-30 v56 P0 Layer B + 24h 即 ready；Sprint 2 W2-B IMPL Wave 2 估 D+5-D+12 land，與 LG-3 Wave 2.4.A 並行
4. 三條皆與 Sprint 2 IMPL 路徑 **parallel不 serial**
**Verdict**: 反駁站；治理債並行還；Sprint 2 啟動本身不增加治理債。

#### Argument 5: 5 textbook 結構性 alpha-deficient 還沒 closure；funding_arb deprecated 才 D+2；急著 IMPL 新 candidate 像「跳船找新方向」
**論點**: 4 textbook structural alpha-deficient 結論是 QC 2026-05-11 audit verdict；如果系統性 fee drag + slippage + selection bias 是根本原因，新 candidate (funding short + liquidation fade) 不會免疫；可能 Sprint 2 IMPL 完還是負 edge，浪費 30-40 hr 在無望策略。
**反駁**: 
1. 新 candidate **failure mode 不同於 textbook 結構性問題**：funding_short_v2 alpha source = funding rate dislocation（exchange-native carry source，不是 mean-reversion）；liquidation_cascade_fade alpha source = adverse selection of stop runs（市場結構性訊號，不是趨勢延續假設）；都不依賴於 textbook 的 mean-reversion / breakout 假設
2. Sprint 2 SSOT §4 + §5 強制 fee gate = candidate 不過 fee-adjusted edge 直接 reject；不會浪費 wall-clock 在 fee-dragged 策略
3. Sprint 2 SSOT §3 P3 minimum gate = `n>=30`；如果 14d 累積不足，自動降 `observe_more` 不會強升 stage
4. Tournament framing **就是** 為了快速 reject 不過 gate 的 candidate；如果 funding_short_v2 + liquidation_cascade_fade 14d 後也是負 edge，Sprint 2 出 `reject` verdict，Sprint 3+ 再提 A3+A4+A5 candidate，並非「無限蒼蠅亂撞」
**Verdict**: 反駁站；Tournament framing 自帶 reject 機制；不過 gate 自動踢出不會浪費。

### §5.2 5 reverse argument 整體 verdict
5/5 reverse argument 都有合理反駁；無一可推翻「Sprint 2 啟動是 CONDITIONAL GO」。**PA 最終 verdict 不變**：**CONDITIONAL GO (Wave 1+2 IMPL)** + **HARD STOP at stage0_ready promotion gate** waiting for 6 Reject gate 收齊。

### §5.3 但若 operator/PM 偏好「先還治理債」path 的替代方案

若 operator 認為 Argument 4「先還債」path 更穩妥，PA 可接受替代方案：
- **Sprint 2 PRE-Wave 0**（~ 1 week）：M11 replay_runner cron land + LG-3 V104 IMPL DISPATCH + Packet C 真實接線（pipeline_ctor wire + 3-way dispatcher + audit emit）
- **然後** Sprint 2 W2-B E1 IMPL 起 Wave 1+2 dispatch
- **代價**: Sprint 2 開始時間順移 ~1 week → Sprint 4 first Live W17.5 → W18.5；Sprint 2 W12-15 calendar 撞 Sprint 1A-γ Wave 1 + LG-3 Wave 2.4.A，wave-X3 拉到 7 並行 ceiling 邊緣

PA 個人判斷：**並行還債 + 啟 Sprint 2 ROI 較高**；但接受 operator/PM 偏好序貫還債的判斷。

---

## §6 Verdict 總結

### Sprint 2 啟動 verdict: **CONDITIONAL GO**

- **Wave 1 dispatch（D+0 起）**: ✅ **GO** — 10 Ratify gate 已收齊；無治理債阻；W2-B E1 IMPL `funding_short_v2` + `liquidation_cascade_fade` Rust struct + TOML default `active=false` 可立即派發
- **Wave 2 IMPL（D+5-D+12）**: ✅ **GO** — W2-A pre-spec finalize 完成；schema drift 已 inline amend；W2-B E1 IMPL action checklist 12 條 ready；並行 LG-3 V104 IMPL + M11 replay_runner schedule + Packet C wire
- **Wave 3 sign-off + stage0_ready 出口（D+18-21）**: 🟡 **CONDITIONAL** — 6 Reject gate 全收齊才可出 `stage0_ready`；否則出 `draft_only`（V103 EXTEND DRAFT writeback）等 Sprint 3+ 再評
- **Sprint 3+ Stage 0R → Stage 1 demo canary 晉升**: 🔴 **HARD STOP** waiting for full P0-EDGE/LG-3/OPS residual gate closure + M11 replay 路徑 alive + Packet C wire

### Sprint 2 啟動 Day 0 action
1. PA proposal land for `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL`（2-4 hr）
2. operator 拍 M11 cadence + E1 cron install（1-2 day）
3. W2-B E1 IMPL dispatch（per W2-A §11.3 12 action checklist；30-40 hr）
4. 並行 Wave 5 Packet C pipeline_ctor wire（per Sprint 3+ promotion 需要）
5. LG-3 V104 IMPL DISPATCH（~2026-05-30 + 2 day Wave 2.4.A）
6. 14d demo accumulation cron @02:30 UTC（per W2-A §3.4）

---

## §7 References

### Source SoT
- `srv/docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md` — Alpha Tournament SSOT
- `srv/docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md` — dispatch packet
- `srv/docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md` — A1 spec v1.1
- `srv/docs/execution_plan/2026-05-25--alpha_candidate_4_liquidation_cascade_fade_spec.md` — A2 spec v1.1
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--w2a_alpha_tournament_pre_spec_finalize.md` — W2-A pre-spec finalize + Step X closure
- `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §4 + §10.5 — Sprint 2 row + P0 precondition

### Governance + AMD
- `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md` — Stage 0R replay preflight + Stage 1 demo micro-canary
- AMD-2026-05-21-01 v2 — Layered Autonomy with Fail-Safe + ADR-0034 LAL
- AMD-2026-05-26-01 — funding_arb deprecation
- AMD-2026-05-25-01 — Commercialization Exchange-Native Only
- AMD-2026-05-25-02 — v5.5 Bot Positioning + Capital Structure Formalization
- ADR-0008 Decision Lease state machine
- ADR-0025 Track-based strategy attribution
- ADR-0026 direct_exploit bypass CPCV
- ADR-0034 Decision Lease LAL
- ADR-0044 M7 decay
- ADR-0045 M4 hypothesis discovery governance

### Memory + skills
- `feedback_indicator_lookahead_bias` — rolling shift(1) 強制
- `feedback_demo_loose_live_strict_policy` — demo evidence policy
- `feedback_env_config_independence` — paper/live/demo 三 config 分開
- `project_2026_05_10_sprint_n0_closure` — attribution_chain_ok 0.5%→100% 範式
- `project_funding_arb_v2_deprecation_path` — funding_arb V2 retired
- 16 root principles #3 #4 #5 #7 #11
- skill `16-root-principles-checklist` (本 task 載入)

### Runtime evidence (2026-05-28 SSH empirical)
- demo+live_demo 14d fills: grid 354 / ma 89 / bb_reversion 16 / bb_breakout 2 / funding_arb 0
- demo+live_demo 7d avg_bps: grid −2.55 / ma −12.75 / bb_reversion −2.22 / bb_breakout +33.11 (n=2 noise)
- live_demo 7d net = −1.99 USDT
- `replay.experiments` total=23 / last_age=407h

---

## §8 PA Push-Back 自評（3-5 條最強反對 Sprint 2 啟動的理由）

per task 要求底部加自評；以下是 PA 認為**最強的 5 條 push-back**（按強度遞減；§5 已逐條反駁）：

1. **M11 replay_runner 0 cron + Packet C pipeline_ctor 0 wire + LG-3 V104 未 land = 三條治理債積壓**（per Argument 4）— 啟 Sprint 2 = 增加新 strategy candidate，每條都依賴 M11 replay + Packet C runtime fail-safe + LG-3 supervised live SM；治理債並行還的複雜度可能超出 Sprint 2 W12-15 7 並行 capacity 上限
   - **強度**: 中—並行還債在過去 1 month 已 demonstrated（Sprint 1A-α/β/γ/δ/ε 五波並行）；但 Sprint 2 業務 sprint + 3 條 P0/P1 debt 並行 = 8 並行，超過 7 ceiling
   - **緩解**: 排序 = D+0 M11 PA proposal land → D+1 operator 拍 cadence → D+2 W2-B IMPL 起 + LG-3 Wave 2.4.A 並行 + Packet C wire 並行

2. **AC-S2-A-3 ≥1 candidate 達 demo 7d avg_net > 5bps 的命中機率不確定**（per Argument 5 partial）— 5 textbook 結構性 alpha-deficient verdict 在；新 candidate funding_short_v2 expected edge 22 bps cost / liquidation_cascade_fade 50 bps cost；如 Bybit 流動性結構與 spec 預期偏離，可能 Sprint 2 終局 0/2 candidate 達 stage0_ready
   - **強度**: 中—funding rate dislocation 與 liquidation cascade 是 microstructure 經驗證的 alpha source，但 Bybit demo 流量微結構與 mainnet 可能偏差；不能 100% pre-commit
   - **緩解**: Sprint 2 SSOT §6 four output lane（reject / draft_only / observe_more / stage0_ready）= 即使 0/2 達 stage0_ready 也 acceptable output；Sprint 3+ 再加 A3+A4+A5

3. **Stage 0R replay preflight 在 M11 runner 跑起來之前不能 fire**（per Gate-2 + Gate-9 dependency） — 即使 Sprint 2 W2-B E1 IMPL 完美完成 + 14d demo evidence 累積完美，如果 M11 replay_runner 沒在 Wave 3 之前真實接線跑出 evidence，stage0_ready 路徑封鎖
   - **強度**: 高—M11 Track C SOURCE LAND 但 0 cron + 23 row last_age=407h 真實證明 runtime 未證
   - **緩解**: PA proposal 已派（`P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL`）；如果 operator [4]=b 拍 proposal 1-2 day land + cron 接線 → Wave 1+2 期間有充分時間累積 replay evidence；不阻 Sprint 2 啟動，只阻 stage0_ready 出口

4. **Sprint 2 W12-W14.5 wall-clock = 2.5 week，但 dispatch packet 估 248-351 hr 7 並行**（per dispatch packet §1.5）— 35-50 hr per sub-agent；某些 wave（W1-A 8 hr + W2-B 30-40 hr + W2-E 10-15 hr）累積在單一 sub-agent 上會超出 Sprint 2 calendar
   - **強度**: 中—7 並行 capacity ceiling 已 demonstrated；但 248-351 hr 上限值得抽查 sub-agent assignment
   - **緩解**: PA W2-A 已 finalize 拆 12 action checklist；7 sub-agent allocation 對齊 dispatch packet §1.2-§1.4 wave；如果某 wave 延遲，回退到 `draft_only` lane 不阻

5. **「啟動 Sprint 2」與「PM 真實 push 業務 sprint」之間的 governance signaling 模糊**（per Sprint 2 Phase Banner = 🟡 SSOT SPEC-FINAL / IMPL NOT STARTED）— SSOT spec 鎖定不等於業務 Sprint 真實 dispatch；TODO 顯示 Sprint 2 IMPL NOT STARTED 是 design 結果（W12 calendar 等 1A-γ V111 land）非 stop signal
   - **強度**: 低—governance signaling 確實模糊，但屬 PM cluster naming convention 問題不是 entry gate 問題
   - **緩解**: Sprint 2 phase banner 應 update 為 W12 dispatch ready；TODO v77 可清晰 mark 「Sprint 2 業務 Alpha Tournament Wave 1 DISPATCH READY pending operator GO」

### §8.2 自評 push-back 整體 verdict
5/5 反對理由全 mitigable；無一強到推翻「Sprint 2 啟動是 CONDITIONAL GO」結論。**最強 push-back = Gate-9 M11 replay_runner 0 cron**，但已有 `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL` 派發路徑覆蓋；不是 Wave 1 dispatch blocker。

---

**Report END**

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--sprint2_alpha_tournament_entry_checklist.md`
