# v5.8 13-Module Autonomy Expansion 執行性審核 — CC 視角

**日期**：2026-05-21
**Verdict**：**GO-WITH-CONDITIONS**
**One-line summary**：13 module 大量逼近原則 3/4/7/11 紅線；7 個 must-fix 必須在 v5.8 派 PA 前補（M1 Tier 2 governance 細則 / M2 enable opt-in 路徑 / M6 Bayesian auto-apply 邊界 / M7 復活路徑 / M9 promotion gate / M13 Binance trade ADR / operator forgetfulness vs human-final-review 衝突解釋）；M6/M9/M13 Y2 部分必須延後至 Y1 evidence 收齊後新 5-gate review。

## 0. 16 根原則 vs 13 module 對照表

| # | 原則 | 狀態 | 適用 module + 理由 |
|---|---|---|---|
| 1 | 單一受控寫入口 | **WARN** | M1 Tier 2 + M6 Auto + M7 auto-demote + M12 + M13。13 module 將大量「auto-apply」決策注入 IntentProcessor / GovernanceHub；v5.8 §2 未明示新增的 Tier/Lifecycle/Weight/Routing 寫操作是否全部走 `submit_intent` 統一入口。M13 venue 拓寬到 Binance 後是否仍只有單一 IntentProcessor？未明示。 |
| 2 | 讀寫分離 | PASS | M4/M8/M9/M11 Y1 設計為 read-only logging；M2 STATE_COUNTERFACTUAL_ONLY 是 Y1 default；M10 Tier A 是現有。明確的 Y1 read-only / Y2 write 分階段是 healthy。 |
| 3 | AI 輸出 ≠ 命令 | **WARN-HIGH** | M1 Tier 2 Y2 Auto = AI/Allocator 提案 → 自動執行（雖然有「30 prior + 80% yes + opt-in」gate）。原文「opt-in 之後 auto」實質上把 operator 一次性 click 換成 AI 持續 click 權。v5.8 §2 M1 未明示 auto-approval 期間每筆仍走完整 Decision Lease + Guardian + risk envelope check 鏈條。同理 M6 ≤ 30% auto-apply、M7 auto-demote、M2 auto-disable/enable。 |
| 4 | 策略不繞 Guardian | **WARN** | M2 overlay auto-disable / M3 HEALTH_DEGRADED auto-throttle / M7 auto-demote → 50% size 都是「策略 sizing/state 自動變化」。v5.8 寫「Guardian-checked」但未明示這些自動觸發是否每次仍經 Guardian replay。 |
| 5 | 生存 > 利潤 | PASS | M3 HEALTH_CRITICAL auto-halt / M7 auto-demote → 50% / M2 auto-disable always-on / M8 anomaly active trigger Y2 全部是 fail-closed 方向 graduated response。 |
| 6 | 失敗默認收縮 | PASS | M3 graduated response 每階都向收縮側；M2 auto-disable triggers 5 條全是收縮觸發；M11 high-divergence → HEALTH_WARN。 |
| 7 | 學習 ≠ 改寫 Live | **WARN-HIGH** | M4 hypothesis 寫 DRAFT 到 learning.hypotheses 表 OK；但 M5 online learning「streaming update: model parameters update per N new fills」**直接改 live model state**。M6 Bayesian reward weight auto-update（Y2）也是「learning → Live allocator sizing」邊界模糊。 |
| 8 | 交易可解釋 | PASS | M11 nightly counterfactual replay + replay_divergence_log + M1 post-hoc transparency + M6/M8/M9/M7 各有 audit table = 強化可解釋性。 |
| 9 | 災難雙重防線 | PASS | M3 HEALTH_CATASTROPHIC 仍走 existing $3,000 kill；M13 Binance 加入後 multi-venue 但 Guardian 仍 extend to handle cross-venue netting。 |
| 10 | 認知誠實 | PASS | v5.8 §6「v5.8 does not accelerate Y2 90% target」+ §7「conditional on actually working」+ reviewer audit + operator reject Claude push-back 全程紀錄 = honest。 |
| 11 | Agent 最大自主（P0/P1 內） | **WARN** | 13 module 大幅擴張 agent autonomy（M1 Tier 2 Auto / M6 Auto weight / M7 auto-demote / M8 active trigger / M9 auto-promotion / M12 maker-vs-taker adaptive）。M10 capital-tier auto-trigger eval 涉及 AUM 越過閾值 → 自動啟動新 tier，邊界自動擴張，這跟原則 11 微妙衝突，必須 operator confirm via Console。 |
| 12 | 持續進化 | PASS | M4 + M11 + M6 + M10 = 13 module 整體就是「演化從證據」骨架；ADR-0024-lite 對齊。 |
| 13 | AI 成本感知 | **WARN** | v5.8 §4 Y1 engineering 2,780-3,930 hr vs v5.7 1,710 hr = 2.0-2.3x。13 module 大成本但 Y1 income 不變（Y1 $300-550），Y3+ 才見回報。但 §7「conditional on actually working」誠實標明 = WARN 非 FAIL。 |
| 14 | 零外部成本可運行 | PASS | M4/M5/M8 內部計算；M10/M11/M12/M13 internal infra；M2 macro/on-chain 走 free tier。 |
| 15 | 多 Agent 協作 | PASS | M1/M6/M7 全是 Advisory→Auto 雙階段，Allocator/Conductor 邊界不混；M4 寫 DRAFT 由 operator + Cowork review = operator-assistant 範式。 |
| 16 | 組合級風險 | PASS | M7 auto-demote 包含 portfolio 視角；M8 correlation structure break + coupled drawdown；M10 Tier C cross-asset correlation 直接 hits 原則 16。 |

**統計**：PASS 10 / WARN 6 / FAIL 0。6 條 WARN 集中：**原則 1 / 3 / 4 / 7 / 11 / 13**，源自「13 module 引入 auto-apply 路徑」。

## 0.5 9 安全不變量 vs 13 module

| # | 不變量 | 狀態 | 理由 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | PASS | M11 continuous replay 強化；M9 A/B 走 preregistration。 |
| 2 | Lease 必在執行前 acquired | **WARN** | M1 Tier 2 Auto 是否每筆 auto-approval 仍 emit individual lease + lease_id？還是 umbrella lease 覆蓋一個月 proposals？未明示。若後者 = 違反不變量 2。 |
| 3 | 執行回報必落 fills 表 | PASS | 13 module 沒新增不走 fills 表的執行路徑；M13 Binance 加入後需 V116 明示。 |
| 4 | 風控降級 → engine 自動止血 | PASS | M3 graduated response 強化此不變量；HEALTH_CATASTROPHIC → existing $3,000 kill。 |
| 5 | Auth 過期 → cancel_token shutdown | **WARN** | M13 Y2 Binance trade enable 後 authorization.json 是否含 venue 欄位？env_allowed 是否要新增 Binance？v5.8 §2 M13 未討論。 |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | PASS | 13 module 不繞此 env 變數；M13 Binance Y2 加入後仍應在 OPENCLAW_ALLOW_MAINNET 範圍內。 |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | **WARN** | M13 Y2 Binance 加入 → Binance API retCode != 0 等價 fail-closed 規範未明示。 |
| 8 | Reconciler 對賬差異 → 自動降級 paper | **WARN** | paper not active，需替換為「降級到 manual mode」。M11 nightly replay 是強化對賬，但「對賬差異 → 行為變化」未明示。 |
| 9 | Operator 角色 + live_reserved 缺一即拒 | **WARN** | M1 Tier 2 Auto 是「operator 一次 opt-in 後 AI auto-approve」—— operator role 仍存在但「人類最終 review」邏輯被部分讓渡。 |

**9 不變量統計**：PASS 4 / WARN 5 / FAIL 0。

## 1. Top 3 執行性風險

### Risk 1：M1 Decision Lease Tier 2 Auto 規格不足以保證原則 3+4+安全不變量 #2/#9
- 嚴重度：**CRITICAL**
- 涉及：M1 + M6 ≤ 30% auto-apply + M7 auto-demote via M1 Tier 1
- 描述：v5.8 §2 M1 列了 5 條 auto-approval gate criteria，但**未明示**：
  - (a) Auto-approval 期間每筆執行是否仍經完整 Decision Lease emit + Guardian replay？還是 umbrella authority？
  - (b) lease_id 是否 per-approval 唯一？
  - (c) 80% yes-rate 計算窗口
  - (d) Console toggle opt-in 是否需要重簽 authorization.json？
  - (e) 24h undo 範圍
- Must-fix：Sprint 1A-β 補 `2026-05-21--m1_lease_tier_governance_spec.md`：Auto-approval per-decision emit lease + Guardian replay（**不是** umbrella authority）；M6 weight ≤ 30% 仍走 Guardian。對應 ADR-0034 必須包含這些細節。

### Risk 2：M13 Y2 Binance trade enable 觸碰 5-gate + 9 不變量 + ADR-0006/0033
- 嚴重度：**HIGH**
- 涉及：M13 + M12 cross-venue routing Y2 + M10 Tier E venue evaluation Y3+
- 描述：v5.8 §2 §472「Binance perp trade enable Y2」把 read-only 升格為 trade authority。觸碰：CLAUDE.md §一「Bybit is the only exchange target」+ §四「Bybit retCode fails closed」需擴展 + ADR-0006/0033 重簽 + 5 gate authorization.json env_allowed + secret slot Binance + reconciler cross-venue。ADR-0040 trait stub 未涵蓋。
- Must-fix：v5.8 §2 M13 + ADR-0040 明示「Y2 Binance trade enable 前提 = 新 5-gate review + ADR 重簽 + CLAUDE.md §一 amend + authorization.json schema migration」；v5.8 §10 risk list 加第 6 條 risk。

### Risk 3：operator forgetfulness mitigation vs priority 5 "human final review" 衝突未明示
- 嚴重度：**MEDIUM**
- 涉及：M1 opt-in Auto + M2 auto-enable Y2 + M6 ≤ 30% + M7 auto-demote + M9 auto-promotion Y2
- 描述：CLAUDE.md §二 priority order 第 5「human final review」；v5.8 §11「operator forgetfulness」直接動 priority 5。§11 對 M1/M2/M6/M7/M9 沒明示「opt-in toggle = bounded delegation, not removal of final-review」。
- Must-fix：Sprint 1A-β 出 `AMD-2026-05-21-01-autonomy-vs-human-final-review.md`：定義「protected scope」（永遠 operator click）vs「opt-in scope」（toggle 後 auto）；M1 Tier 2 IMPL（Sprint 7-8）前完成。

## 2. ADR-0024-lite + AMD-2026-05-15-01 vs M1/M2/M4/M6/M7/M8/M9 衝突

- **ADR-0024-lite**：M4「Bot CAN propose / CANNOT promote / CANNOT execute」= 完全對齊。但 M1 Tier 2 + M6 ≤ 30% + M9 auto-promotion 把 Cowork 「propose only」邊界擴張到 「propose + auto-approve」—— 需 ADR-0024-lite **amend**。
- **AMD-2026-05-15-01**：M2 state machine 與 AMD-01 Stage 0R→4 是否獨立？M7 STAGE_DEMOTE_PROPOSED 與 AMD-01 stage 對齊 ✓。Must-fix：明示 M2 / M7 對應 AMD-01 stage。

## 3. 5-gate live boundary vs M13 Y2 Binance trade enable

| Gate | 對 M13 Y2 的影響 |
|---|---|
| 1 live_reserved | 不變 |
| 2 Operator role auth | 不變 |
| 3 OPENCLAW_ALLOW_MAINNET=1 | 不變，但 covers Binance |
| 4 secret slot | **擴展**：Binance secret slot 與 Bybit 分開 |
| 5 authorization.json env_allowed | **schema 擴展**：venue 維度 `{"bybit": ["mainnet","demo"], "binance": ["mainnet"]}` |

**結論**：5 gate **仍 hard binary fail-closed**；Gate 4+5 schema 必須在 ADR-0040 明示。

## 4. 13 module 是否補齊先前 autonomy verdict 的 gap

v5.7 PM autonomy verdict 指出 Y2 88% 是 framework shells。v5.8 補齊：

| Gap area | v5.8 補齊 |
|---|---|
| Auto-Allocator activation gate | M1 Tier 2 + M6 Auto = 實質骨架補齊 |
| Overlay enable gate | M2 state machine + auto-enable Y2 = 實質骨架補齊 |
| Copy Trading evidence gate | **未動**（保留 explicit operator click） |
| Long-term self-iteration | M4 self-supervised = 新增 |
| Capital scaling | M10 Tier A-E ladder = 新增 |
| Operator forgetfulness mitigation | M2/M3/M7/M8/M11 = 新增（但 vs priority 5 衝突未明示，見 Risk 3） |

**結論**：v5.8 補齊 5/6 gap。Y2 90% claim §622 合理，但**不應**讀作「Auto-Allocator gate 不再需要 6 個月 Advisory + 80%」—— v5.8 §730 明示「does NOT shortcut this」。

## 5. 對 PA+FA+PM 匯總的必收 top 3

1. **`2026-05-21--m1_lease_tier_governance_spec.md`**（CC must-fix Risk 1）—— Sprint 1A-β 派發必含；PM 簽收後 ADR-0034 才能 finalize
2. **`AMD-2026-05-21-01-autonomy-vs-human-final-review.md`**（CC must-fix Risk 3）—— priority order amendment；CC 此 AMD 不批 v5.8 拒 Sprint 1A-β 派發
3. **ADR-0040 擴展 + multi-venue gate spec**（CC must-fix Risk 2）—— Y2 Binance trade enable governance amend 為 hard prereq

## 6. v5.8 派發前 must-fix（7 條）

1. M1 Tier 2 Auto governance spec（Risk 1）
2. `AMD-2026-05-21-01` operator forgetfulness 與 priority 5 衝突解釋（Risk 3）
3. M2 overlay state machine 對齊 AMD-2026-05-15-01 Stage gate
4. M6 Bayesian auto-apply ≤ 30% 邊界明示走 Guardian
5. M7 auto-demote 對應 AMD-01 Stage 3 demote 路徑
6. M9 auto-promotion Y2 gate 與 Stage 4 LIVE 路徑對齊
7. M13 + ADR-0040 multi-venue governance prereq（Risk 2）

## 7. Sprint 1A-β-ε 期間 should-fix

1. **Sprint 1A-β**：M1 ADR-0034 含 Risk 1 五個細節；M6 reward_weight_history 表記錄 `change_pct` 和 `auto_applied_flag`；M7 strategy_lifecycle 表與 AMD-01 stage_transition_log align
2. **Sprint 1A-γ**：M2 overlay_state_transitions 表必含 `parent_stage`（AMD-01 stage reference）；M9 ab_tests 表 FK 到 learning.hypotheses；M10 capital_triggers 表必含 `requires_operator_console_click` BOOL default TRUE
3. **Sprint 1A-δ**：ADR-0035 (M5) 含「Y3+ IMPL 前重 5-gate review」；ADR-0040 (M13) 含 Risk 2 所有 governance prereq
4. **Sprint 1A-ε integration verify**：Cross-ADR consistency audit（ADR-0034-0040 + AMD-2026-05-21-01 + ADR-0024-lite amend）；CC + FA priority order walk-through
5. **Sprint 2+ should-fix**：M11 30d divergence baseline 收集；M8 Y1 read-only 90 day FPR < 5% gate

---

**CC AUDIT DONE: GO-WITH-CONDITIONS**

**核心結論**：
- v5.8 13 module 整體方向 align operator directive
- 6 條原則 + 5 條安全不變量 WARN 集中在「M1 Tier 2 Auto / M13 Binance trade / operator forgetfulness vs human final review」三 cluster
- Sprint 1A-β 派 PA 前必須補 7 個 must-fix
- 5 gate live boundary 仍 hard binary fail-closed
- Y2 90% claim §622 honest（§730 明示「Auto-Allocator gate unchanged」）
- 工時建議在 §3 schedule 內加 `+10% governance amend buffer` 約 60-90 hr
