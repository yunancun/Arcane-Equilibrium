# Sprint 2 Entry Lock — grill-me + PA cross-verify + hybrid 方案 C ratified

**日期**：2026-05-28
**Owner**：PM session（main conductor）
**TODO 版本**：v77
**前置 report**：
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--sprint2_alpha_tournament_entry_checklist.md`（PA 獨立 verdict）
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-28--wave5_packetc_engine_integration_a_level_sweep.md`（v76 上半 session）

---

## 1. 目的

按 operator menu [5] = a+b 平行：
- 軌 a：grill-me skill 在同 session 對 operator 質詢，列出 Sprint 2 啟動前必收的最小 P0 子集（5 lock decision）
- 軌 b：背景派 PA agent 獨立產出 Sprint 2 entry checklist + ratify/reject/conditional 矩陣

兩端產出後交叉驗證 4 共識 + 1 重大分歧；分歧由 operator 拍板 hybrid 方案 C 收口。

---

## 2. grill-me 5 lock decision

| Q | 問題 | Operator 拍板 |
|---|---|---|
| Q1 | Sprint 2 framing 真的叫 Alpha Tournament 嗎？ | a — **改名 Stage 0R Replay Preflight Sprint**（廢 Tournament 業務 framing，但保 activation spec future use per Q2 雙軌） |
| Q2 | Tournament 設計怎麼「凍而不丟」？ | a 雙軌 — **PA 寫 activation spec / 不寫 runner code / N=5 strategy pool / M=15 per-strategy n** |
| Q3 | P0-EDGE-1 root closure 是 Sprint 2 entry hard gate 還是平行收？ | b — **路線 2 平行收 + Stage 0R green 只當 evidence accept + demo canary 升 Stage 1 另開 sprint** |
| Q4 | Stage 0R 對哪些策略跑？ | X / P → 後改 **C hybrid**（見 §4） |
| Q5 | Wave 5 Packet C wire 是否進 Sprint 2？ | **路線 2 完整 wire（pipeline_ctor + 3-way dispatcher + audit emitter）拉進 Sprint 2 並行軌** |

---

## 3. PA cross-verify 對齊矩陣

| 主題 | grill-me 拍 | PA verdict | 對齊狀態 | 收口 |
|---|---|---|---|---|
| Framing | 廢 Tournament 業務 framing | 保留 Tournament framing（multi-candidate 並行 ROI） | **可調和** | 保 Sprint 2 業務性 framing 改名，內部走 Stage 0R direct；Tournament activation spec 為 future use 另開 ticket（`P2-ALPHA-TOURNAMENT-ACTIVATION-SPEC`） |
| Activation threshold | N=5 / M=15 | SSOT n≥30 是 candidate stage0_ready **出口** gate | **不衝突** | M=15 是 strategy 進 tournament **入口** activation；n≥30 是 candidate 出 stage0_ready；兩層共存 |
| 平行 vs hard gate | 平行收 + Stage 0R green 只 evidence accept + canary 另開 sprint | CONDITIONAL GO Wave 1+2 dispatch + Wave 3 6 Reject gate + Sprint 3+ canary | ✅ **完全共識** | 無需收口 |
| Stage 0R 對誰跑 | grid+ma + 30 天 catch-up bb_breakout/bb_reversion | A1+A2 主 IMPL / 5 textbook 全 B0 不進 | 🔴 **重大分歧** | operator 拍 **hybrid 方案 C** 解決（見 §4） |
| Packet C wire | 路線 2 完整 wire 進 Sprint 2 | Gate-10 認為 Sprint 3+ Level 2 路徑工作；§6 Day 0 action 列為並行軌 | **可調和** | 放 Sprint 2 並行軌，Wave 3 stage0_ready 出口不依賴 Packet C，Sprint 3+ Level 2 promotion 之前 land = 進度 |

---

## 4. Q4 重大分歧 → hybrid 方案 C ratified

### 4.1 分歧本質

| 視角 | Sprint 2 性質 | 主策略 |
|---|---|---|
| operator (Q4 X/P) | 用 replay preflight 測**既有策略** | grid + ma 進 Stage 0R + 30 天 catch-up bb_breakout/bb_reversion |
| PA verdict | IMPL **新策略 candidate** | A1 funding_short_v2 + A2 liquidation_cascade_fade 主投，5 textbook 全 B0 baseline 不 IMPL |

### 4.2 PA push back 證據

- grid 7d avg_bps = -2.55 / ma 7d avg_bps = -12.75（demo + live_demo 14d empirical）
- 兩者不過 SSOT §3 P3 gate（avg_bps positive + Wilson lower>0 + n≥30）
- 跑 Stage 0R PA 預測 = reject（fee-adjusted edge 結構性負）
- 5 textbook 結構性 alpha-deficient 已是 QC 2026-05-11 audit verdict

### 4.3 operator 拍 hybrid 方案 C — Sprint 2 並行三軌

| 軌 | 內容 | 投資 | 來源 |
|---|---|---|---|
| **主軌** | A1 funding_short_v2 + A2 liquidation_cascade_fade Rust struct + TOML default `active=false` 30-40 hr IMPL per W2-A §11.3 12 action checklist | 主要 IMPL bandwidth | PA |
| **對照軌** | grid + ma 進 Stage 0R 作 B0 baseline 控制組 — 驗 QC 5 textbook 結構性 alpha-deficient verdict（PA 預測 reject = 確認 verdict / positive = 推翻 verdict） | 順帶低成本 | operator + PA hybrid |
| **catch-up 軌** | bb_breakout + bb_reversion 維持 demo 累積，D+30 ~2026-06-27 評估是否進 M7 decay_signals RETIRED（30 天 = 半路線 Y retire + grace window，per agent push back acknowledged） | 0 hr Sprint 2 內 | operator (30 天語意接受) |

### 4.4 ROI 評估

- 主軌 = 新 alpha source 探索（funding rate dislocation + liquidation cascade fade）
- 對照軌 = baseline 永遠存在（SSOT §3 B0 概念），順帶跑 Stage 0R 等於再 verify QC verdict，沒有額外 wall-clock cost
- catch-up 軌 = 結構性 entry 嚴的策略一個合理判決窗口；不破口 M=15 governance number

---

## 5. Sprint 2 dispatch ready 狀態

按 PA CONDITIONAL GO + hybrid 方案 C：

### 5.1 Wave 1 dispatch（D+0 起）= **GO**
- 10 Ratify gate 已收齊（per PA report §0）
- 無治理債阻
- A1+A2 W2-B E1 IMPL dispatch ready per W2-A §11.3 12 action checklist

### 5.2 Wave 2 IMPL（D+5-D+12）= **GO**
- W2-A pre-spec finalize 完成
- W2-B E1 IMPL 30-40 hr ready
- 並行：LG-3 V104 IMPL + M11 replay_runner schedule + Packet C wire

### 5.3 Wave 3 sign-off + stage0_ready 出口（D+18-21）= **CONDITIONAL**
- 6 Reject gate 全收齊才出 stage0_ready：
  1. Stage 0R 6 sanity（Leak/Lookahead / Bias-Selection / DSR-PSR / PBO-Bootstrap / Replay tier / Runtime boundary）
  2. M11 replay_runner schedule 接線（per `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL`）
  3. W2-E E2 grep 18 focus 0 hit on relaxation pattern
  4. W2-F MIT post-IMPL audit attribution_chain_ok 100%
  5. AC-S2-A-3 ≥1 candidate 達 demo 7d avg_net>5bps + Wilson lower>0 + n≥30
  6. W3-C TW + PM sign-off
- 否則出 draft_only（V103 EXTEND DRAFT writeback 等 Sprint 3+）

### 5.4 Sprint 3+ Stage 0R → Stage 1 demo canary 升 = **HARD STOP**
- 等 P0-EDGE-1 root closure + P0-LG-3 V104 supervised live + OPS-2 Phase 2 cutover

---

## 6. 新 ticket 落地

v77 三個新 ticket：

| Ticket | 描述 |
|---|---|
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` | Sprint 2 主 ticket — 含三軌 + 5 lock 全紀錄 + ETA 2.5 week / 248-351 hr 7 並行 |
| `P2-ALPHA-TOURNAMENT-ACTIVATION-SPEC` | 派 PA 寫 activation spec（N=5 / M=15 / 退出機制 / 排名 slot 預留 / 不寫 runner code）；ETA 2-3 hr |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 30 天 catch-up grace clock 給 bb_breakout / bb_reversion；D+30 = 2026-06-27 評估 retire vs continue |

---

## 7. push-back 紀錄（透明化）

### 7.1 agent push back operator（被 operator overrule）

- **Q4 30 天 vs 60 天**：agent 推薦 60 天 catch-up；operator 拍 30 天。Agent 接受 = 「半路線 Y retire + grace window」語意，誠實寫進 ticket。

### 7.2 PA push back operator Q4（觸發 hybrid 方案 C）

- PA 認為 5 textbook 結構性 alpha-deficient，跑 Stage 0R = 浪費 wall-clock。Operator 接受並拍 hybrid 方案 C：保留主軌 PA 路線，並把 grid+ma 對照軌當 SSOT §3 B0 baseline 順帶跑。

### 7.3 agent push back operator Q5（被 operator 接受）

- agent 推薦路線 3（Packet C spec but not IMPL）；operator 選路線 2（完整 IMPL）。理由：「直接全部做掉」明示接受 scope creep / ETA 拉長代價。

### 7.4 PA 自評 5 條 push-back

per PA report §8，5/5 全 mitigable；最強 push back = M11 replay_runner 0 cron（Gate-9），但 `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL` 派發路徑已覆蓋。

---

## 8. Sprint 2 啟動 Day 0 action（彙整）

per PA §6 + hybrid 方案 C 修正：

1. **D+0**：本 v77 sign-off + commit + push 三端 ✅（本檔）
2. **D+0 ~ D+1**：派 PA agent A — M11 replay_runner schedule proposal（2-4 hr）
3. **D+0 ~ D+1**：派 PA agent B — Alpha Tournament activation spec N=5 / M=15（2-3 hr）
4. **D+1**：operator 拍 M11 cadence + E1 cron install（1-2 day）
5. **D+1 ~ D+3**：W2-B E1 IMPL dispatch（per W2-A §11.3 12 action checklist；30-40 hr）— 主軌 A1+A2
6. **D+1 ~ D+5**：並行 Wave 5 Packet C 完整 wire（pipeline_ctor + 3-way dispatcher + audit emitter）— Q5 路線 2
7. **D+2 ~ D+5**：LG-3 V104 IMPL DISPATCH（~2026-05-30 + 2 day Wave 2.4.A）
8. **D+0 起**：14d demo accumulation cron @02:30 UTC（per W2-A §3.4）— 主軌 A1+A2 + 對照軌 grid+ma
9. **D+30 ~ 2026-06-27**：bb_breakout / bb_reversion 評估 catch-up clock（per `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`）

---

## 9. 簽署

- **grill-me session**：5/5 Q 拍板完成；無懸而未決 branch
- **PA agent**：CONDITIONAL GO + 15 entry gate + 5 自評 push-back 全 mitigable
- **Cross-verify**：4 可調和 + 1 重大分歧由 hybrid 方案 C 解決
- **3 新 ticket**：dispatch / activation spec / catch-up clock 全 land 進 TODO v77
- **三端同步**：本 commit + push + Linux pull 待執行

Sprint 2 status: **DISPATCH READY pending operator GO**。
