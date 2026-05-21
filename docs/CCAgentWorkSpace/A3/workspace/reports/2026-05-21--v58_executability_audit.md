# v5.8 13-Module Autonomy Expansion 執行性審核 — A3 視角

**日期**：2026-05-21
**Verdict**：**GO-WITH-CONDITIONS**
**One-line summary**：v5.8 13-module 設計符合「operator 可能忘記/犯錯」直覺與 APR 最大自動化目標，但 §3 Sprint 1A 工時表只列 13 個 schema/ADR DESIGN 工時（468-692 hr），完全沒列任何 GUI 工時；v5.7 A3 已識別 104-151 hr GUI 缺口；v5.8 又新加 6+ 個 high-risk operator surface → 系統性失明擴大到 **157-223 hr 新增 GUI 工時**（v5.7+v5.8 累計 ~261-374 hr 未列）；v5.7 H2 Console tab 歸屬決策仍未做即又加 6+ surface；認知負荷（5-7 attention 上限）在 Sprint 7 末已 ~25 concurrent 監控項；Sprint 1A 派發 1A-β 前必補完工時 + tab 歸屬 + A3 sign-off gate；evaluator 評 7.0/10。

## 0. 13 module 新增 GUI surface 清單 + 工時估算

| Module | GUI surface | 工時 (hr) | 防誤等級 | 落點建議 |
|---|---|---|---|---|
| **M1** | Tier 2 auto-approval Console toggle + 24h undo button per decision + Tier eligibility tracker | **15-20** | Lv 3 (toggle/undo) + Lv 4 (Tier 2 enable Auto) | `governance` sub-section「Lease Tier」 |
| **M2** | Overlay 5-state machine viewer + manual disable/enable + auto-disable reason badge | **12-18** | Lv 3 | `learning` sub-section「Overlay State」 |
| **M3** | HEALTH state machine dashboard（5 domain × 5 state matrix）+ per-domain drilldown + degradation history | **25-35** | Lv 2 (manual recovery override) | `system` sub-section「Health Domains」 |
| **M6** | Weight change preview / diff view（5 λ 視覺化）+ > 30% change manual confirmation modal + bounds editor | **10-15** | Lv 3 (>30% confirm) + Lv 2 (bounds edit) | `governance` sub-section「Reward Weights」 |
| **M7** | Decay demote alert banner + 14d RECOVER / RETIRE review window UI + signal evidence breakdown | **12-18** | Lv 3 (RECOVER) + Lv 4 (RETIRE) | `governance` sub-section「Decay Lifecycle」 |
| **M8** | Anomaly severity dashboard + Slack ack integration（讀 ack state）+ severity timeline + filter | **15-20** | Lv 1 (ack only) + Lv 3 (manual escalate) | `learning` sub-section「Anomalies」 |
| **M9** | A/B test creation form + result viewer（mSPRT + CI）+ preregistration link | **25-35** | Lv 3 (create test) + Lv 4 (promote variant) | `learning` sub-section「A/B Tests」 |
| **M10** | Capital tier activation confirmation modal（Tier A-E）+ AUM threshold display + active tier badge | **8-12** | Lv 4 (tier activation) | `system` sub-section「Capital Tier」 |
| **M11** | Daily replay divergence report viewer（PnL diff / decision count / slippage）+ Slack hook view | **10-15** | Lv 0 (read-only) | `learning` sub-section「Replay Divergence」 |
| **M12** | Routing profile editor（Sprint 6+）+ maker-vs-taker breakdown + slicing config + bounds editor | **15-20** | Lv 3 (bounds 改) + Lv 4 (single-order $size cap) | `settings` sub-section「Order Routing」 |
| **M13** | Venue selector（Y2+）+ AssetClass picker + cross-venue position aggregator | **10-15** | Lv 4 (venue enable) | `settings` sub-section「Venues」 |

**v5.8 新增 GUI 工時總計：~157-223 hr**

**v5.7 + v5.8 累計 GUI 工時缺口：~261-374 hr**

## 0.5 v5.8 §3 / §4 工時是否含 GUI

**不含。** 直接證據：
- §3 Sprint 1A 工時表 13 module 全部只列「Schema」「ADR」「Interface stub」字樣；**沒有任何一行寫 GUI / 前端 / E1a / Console**
- §4 Y1 總表 Sprint 4「Top-1 live + Top-2 + M1 Tier 1 IMPL」未拆 GUI
- §14 scope change 列「+1,505-2,220 hr engineering Y1」**未列 +XXX hr GUI**

**結論**：v5.8 工時 1505-2220 hr 在 GUI 維度與 v5.7 §9 同樣失明；§4 Y1 總工時應改為 ~3,041-4,304 hr（v5.8 文本 2,780-3,930 hr → +261-374 hr）

## 0.6 Console tab 歸屬建議（不擴張 16 tab）

```
governance tab 內 sub-section（決策授權型）：
  ├─ Decision Lease（既有）
  ├─ Lease Tier（M1 NEW）            ← Tier 0-4 toggle + Tier 2 24h undo
  ├─ Reward Weights（M6 NEW）         ← λ 視覺化 + > 30% confirm modal
  └─ Decay Lifecycle（M7 NEW）        ← demote/RECOVER/RETIRE 14d window

learning tab 內 sub-section（學習/評估型）：
  ├─ Strategy Learning Metrics（既有）
  ├─ Overlay State（M2 NEW）
  ├─ Anomalies（M8 NEW）
  ├─ A/B Tests（M9 NEW）
  └─ Replay Divergence（M11 NEW）

system tab 內 sub-section（系統/容量型）：
  ├─ Engine + WS Health（既有）
  ├─ Health Domains（M3 NEW）
  └─ Capital Tier（M10 NEW）

settings tab 內 sub-section（配置型）：
  ├─ Risk Config（既有）
  ├─ Order Routing（M12 NEW）
  └─ Venues（M13 NEW）
```

**結論**：4 個 tab 各加 2-4 sub-section，**Console 維持 16 tab 不擴張**

## 1. Top 3 執行性風險（UX）

### Risk 1：v5.7 + v5.8 累計 ~261-374 hr GUI 工時失明 — Sprint 1A-β 第一天 PA dispatch 找不到 E1a owner
- **嚴重度**：CRITICAL
- **位置**：v5.8 §3 + §4 + v5.7 §9
- **描述**：
  - M1 Sprint 4 Tier 1 IMPL 必含 governance toggle UI
  - M2 Sprint 3 hook 必有 5-state badge 展示
  - M3 Sprint 5 auto-degradation 必有 5×5 dashboard
  - M6 Sprint 7 Advisory 必有 weight diff preview
  - M7 Sprint 8 必有 14d review UI
  - M11 Sprint 3 nightly replay 必有 daily report viewer
  - §4 Sprint 7 220-320 hr 含 Allocator GUI（20-30 hr）+ M1 Tier 2 toggle（15-20 hr）+ M6 weight diff（10-15 hr）= **45-65 hr GUI 全沒拆**
  - 若 PA 沒列 E1a，會默認 E1 兼任 → 但 E1 已被 5 個 module 工程佔滿
  - Sprint 4 末「M1 Tier 1 IMPL」會在沒有 governance toggle UI 的情況下標 DONE
- **Must-fix**：
  1. §3 工時表加「E1a GUI hours」欄
  2. §4 Y1 sprint 表拆 E1a 工時行 ~157-223 hr v5.8 + 104-151 hr v5.7
  3. §14 scope change 加「+261-374 hr GUI engineering Y1」
  4. PA dispatch packet 模板每 sprint 必含「E1a deliverable 清單」section

### Risk 2：M1/M2/M6/M7/M10/M13 6 個 surface 全是 Lv 3-4 高危操作，A3 sign-off gate 未列入 §12 dispatch chain
- **嚴重度**：HIGH
- **位置**：v5.8 §12 + CLAUDE.md §八「Sub-agent IMPL DONE 必走 A3+E2 對抗性核驗」
- **描述**：
  - M1 Tier 2 toggle = Lv 4（一鍵授權自治權）
  - M1 24h undo = Lv 3
  - M6 weight > 30% = Lv 3
  - M7 RETIRE = Lv 4（策略歸零）
  - M10 capital tier activation = Lv 4（觸發 200-400 hr Y2-Y3 IMPL chain）
  - M13 venue enable = Lv 4（新交易所接線）
  - v5.8 §12 dispatch plan 完全沒提 A3；§7/§8 sprint 計畫也沒列 A3 sign-off invariant
- **Must-fix**：
  1. §12 dispatch plan 補一段 A3 sign-off invariant：列 6 surface + 對應 sprint
  2. PA dispatch packet 強制：每 surface 配對 E1a IMPL → A3 ux audit → E2 對抗性 review 三角 sign-off
  3. modal Lv4 強制打字確認 + cooldown ≥ 30s
  4. 禁用 browser-native `confirm()` / `prompt()`

### Risk 3：認知負荷在 Sprint 7 末超載 — ~25 concurrent attention items
- **嚴重度**：HIGH
- **位置**：v5.8 §1 + §6 autonomy outcomes
- **描述**：ux-checklist 維度 2 認知負荷上限：**單頁 ≤ 7 個關注點**
  - v5.7 A3 已識別 Sprint 6 末 20+ items
  - v5.8 Sprint 7 末加：M1 Tier 2 24h undo list + M2 overlay 5 state + M3 5 health domain × 5 state + M6 5 λ weights + M7 strategy decay signal + M8 anomaly severity feed + M11 daily replay divergence
  - operator Sprint 7 月度 review 要看 ~25 個關注點 → **嚴重超過 5-7 上限**
  - 對 80% approval rate gate 影響：rubber-stamp → gate 變統計噪音
- **Must-fix**：
  1. Sprint 1A-ε 末新增「Operator Monthly Review Dashboard」spec：聚合 6 個關鍵 KPI 為單頁
  2. 每 sub-section 配 traffic-light：4 燈總覽 → 異常才 drilldown
  3. 進度 telemetry：收集「operator 每月 review dwell time」指標
  4. §6 autonomy 表加「UX usability index」

## 2. operator forgetfulness mitigation UX 完整度

| Failure mode | v5.8 §11 mitigation | UX 落實度 | Gap |
|---|---|---|---|
| 忘記 approve monthly Allocator | M1 Tier 2 auto + opt-in | **未指 GUI** | 沒 toggle UI → opt-in 不可能 |
| 忘記 disable overlay | M2 auto-disable | **未指 GUI** | 沒 viewer → operator 不知道現在哪 state |
| 漏看 anomaly alert | M8 → M3 auto-degrade | **部分指 Slack** | Slack 只到 send 未到 ack/read confirm |
| 忘記 retire decayed strategy | M7 auto-demote → 50% | **未指 GUI** | 沒 14d window UI |
| 忘記 check counterfactual | M11 daily Slack | **指 Slack only** | Slack 不夠（mute 可能）；Console viewer fallback 必需 |
| 忘記 evaluate Copy Trading | v5.7 evidence gate | **v5.7 §10 0 GUI** | v5.7 已識別未補 |

**完整度評：3/10**。設計直覺正確但 UI 層 0 落實 → 「忘記」mitigation 反而更易遺忘

**Must-fix**：
1. v5.8 §11 表加「UX surface」欄
2. 加「UX work hours」欄計入 §3
3. Slack-only mitigation 必須有 Console fallback viewer

## 3. 認知負荷 (5-7 attention 上限)

```
Sprint 1B 末（W3）：~5 items — 合規
Sprint 4 末（W19）： ~9 items — 邊界
Sprint 6 末（W25）： ~17 items — 已超
Sprint 7 末（W28）： ~25 items — 嚴重超
Sprint 8 末（W31）： ~30+ items — 紅區
Sprint 10 末（W37-44）：~35+ items — 不可操作
```

**結構性 mitigation**：
1. 聚合儀表盤 + traffic-light
2. operator role 篩選（viewer/researcher/operator 不同密度）
3. monthly review wizard
4. 「未變化」摺疊

**Must-fix**：Sprint 1A-ε 末加「Monthly Operator Review Wizard」+「Traffic-light + 摺疊規則」16-24 hr

## 4. 防誤觸 Lv 3+ 要求 module 清單

```
Lv 4 (modal + 雙 actor + 打字 + cooldown ≥ 30s)：
  M1 Tier 2 enable Auto
  M7 RETIRE
  M10 capital tier activation/deactivation
  M13 venue enable

Lv 3 (modal + 打字確認):
  M1 24h undo
  M6 weight > 30%
  M7 RECOVER
  M12 single-order $size cap
  M2 manual disable / enable
  M8 manual escalate severity
  M9 create A/B test

Lv 2 (modal):
  M2 view auto-disable reason ack
  M3 manual recovery override
  M6 bounds 編輯
  M9 promote A/B variant

Lv 1 (modal):
  M11 view daily replay
  M11 download replay diff
```

**Lv 4 = 4 個，Lv 3 = 7 個**。每 Lv 3-4 操作必須：
1. modal 顯示具體影響
2. 打字短語確認（具體字串）
3. 30s+ cooldown（Lv 4）
4. 雙 actor（Lv 4：M1 Tier 2 + M13 venue）

**Must-fix**：v5.8 §2 各 module spec **加防誤觸等級欄**；統一防誤觸 modal helper 在 Sprint 1A-ε

## 5. A3 sign-off gate 在 Sprint 1A-β-ε

| 節點 | 涉及 surface | A3 sign-off | hr |
|---|---|---|---|
| Sprint 1A-β 末 | M1/M3/M6/M7/M11 mockup + tab nav 樣板 | 5 × 1.5 hr + 樣板 2 hr | 9-11 |
| Sprint 1A-γ 末 | M2/M4/M8/M9/M10 mockup | 5 × 1.5 hr | 7-9 |
| Sprint 1A-δ 末 | M5/M12/M13 stubs | 3 × 0.5 hr | 2 |
| Sprint 1A-ε 末 | Monthly Review Wizard + traffic-light | 3 × 2 hr | 6 |
| Sprint 4 末 | M1 Tier 1 IMPL governance toggle | 5 維度 + Lv 4 modal | 3-4 |
| Sprint 7 末 | M1 Tier 2 + M6 weight + Allocator viewer | 3 × 3 hr | 9 |
| Sprint 8 末 | M7 14d + M3 dashboard + M8 anomaly + M11 daily | 4 × 2 hr | 8 |
| Sprint 10 末 | Y1 review + M10 capital tier | 2 × 2 hr | 4 |

**A3 工時總計：~48-53 hr Y1**

**Must-fix**：v5.8 §12 dispatch plan 末加 §12.5「A3 sign-off invariants」+ 48-53 hr 進入 §4

## 6. 對 PA+PM 匯總必收 top 3

1. **§3 + §4 工時表加 GUI + A3 兩欄**：累計 ~309-427 hr 加入；§4 Y1 總工時改為 ~3,089-4,357 hr（非 2,780-3,930）
2. **Console tab 歸屬決策必須在 Sprint 1A-α 末 sign-off**：4 tab × 各 sub-section 規劃 + sub-section accordion 樣板
3. **A3 sign-off gate 列入 §12 + §4**：8 個節點 × A3 對抗性核驗；統一 modal helper Sprint 1A-ε

## 7. v5.8 派發前 must-fix（GUI 工時補位）

- [F1] §3 工時表加「E1a GUI hours」欄
- [F2] §4 Y1 sprint 表拆 E1a 工時行（補 ~261-374 hr）
- [F3] §12 加「A3 sign-off invariants」+ 48-53 hr
- [F4] §14 scope change 加「+261-374 hr GUI + 48-53 hr A3 Y1」
- [F5] Console tab 歸屬決策（§0.6）寫入 v5.7 H2 closure + v5.8 §12
- [F6] §11 operator forgetfulness 表加「UX surface」+「UX hours」欄
- [F7] §2 各 module spec 加「防誤等級」欄

## 8. Sprint 1A-β-ε 期間 should-fix

- [S1] Sprint 1A-ε 末「Monthly Operator Review Wizard」+「Traffic-light + 摺疊規則」16-24 hr
- [S2] sub-section 設計含「摺疊 default 規則」
- [S3] Lv 3-4 modal helper 統一在 Sprint 1A-ε（8-12 hr）
- [S4] Slack ack（M8）/ Slack daily（M11）的 Console fallback viewer 同 sprint 上線
- [S5] M10 capital tier activation modal 顯示「該 tier 後續 IMPL 範圍 + 工時 + 不可逆性」
- [S6] v5.7 H2「Console tab 歸屬」NEEDS-OPERATOR-DECISION 一併在 Sprint 1A-α 末 closure
- [S7] PA dispatch packet 模板加「E1a deliverable + A3 sign-off + 防誤等級」三必填欄

---

**A3 UX AUDIT DONE: 7.0/10**

評分說明：thesis 與 operator forgetfulness 設計通過；扣 3 分：（a）GUI 工時系統性失明放大化（−1.0）（b）Console tab 歸屬延遲未做（−0.5）（c）A3 sign-off gate 在 §12 缺席（−0.5）（d）認知負荷 Sprint 7-10 末嚴重超 5-7 上限（−0.5）（e）operator forgetfulness mitigation UX 落實 6/6 gap（−0.5）。Sprint 1A-β 派發前若補完 F1-F7 + §0.6 tab 歸屬決策，可升至 8.5/10 unconditional GO
