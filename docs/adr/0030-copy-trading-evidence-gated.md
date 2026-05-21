# ADR 0030: Copy Trading Activation — Y1 末 4-Gate Evidence Evaluation, Y2 Enablement Conditional

Date: 2026-05-21
Status: **Proposed-pending-commit**（v5.7 §11 ADR-0028 提案順移為 0030；本 ADR 為 Y1 末 evaluation framework 鎖定，不 commit Y2 enablement decision）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via v5.7 §11 Reviewer Condition 5 + §12 governance recap）
Related: v5.7 §1 (Y1 income recompute) / v5.7 §9 (Sprint 10 Y1 Review + Copy Trading Evidence Gate) / v5.7 §11 (5 Reviewer Conditions Met) / ADR-0006 (Bybit-only exchange baseline) / ADR-0033 (ADR-0006 amendment — DEX/Hyperliquid NOT approved baseline)

## Context

### 起源

v5.7 dispatch-safe patch 對 Copy Trading optionality 採取「**self-trading primary, copy-trading evidence-gated**」立場。v5.6 → v5.7 演化過程中 reviewer 反復強調：

- Copy Trading 是 Y2+ optionality，**不是** Y1 income lane（per §1 Honest Y1 Income Recompute）
- Y1 期間禁止 Copy Trading 對外開放、禁止 follower 招募、禁止 take fee
- Y1 末（Sprint 10 W36-39）做一次 evidence-based evaluation 決定 Y2 是否 enable
- Self-trading 主路徑必須先在 Y1 證明 alpha 與 governance 紀律，否則 Copy Trading「複製」的就是 noise

v5.7 §11 將此立場提案為 ADR-0028（**順移為本 ADR-0030**，因 ADR-0028 已被 close_maker_fallback_reason 占用）。

### 為什麼需要 evidence-gated 而非 timeline-gated

「Y2 開 Copy Trading」如果只綁時間（如 W40 自動 enable）會在 Y1 alpha 失敗時把錯誤策略放大到 follower 端，**違反原則 5（生存 > 利潤）+ 原則 16（portfolio-level risk > 孤立 trade attractiveness）**。Evidence-gated 把「是否 enable」綁定 Y1 self-trading 實際表現的 4 個維度，確保 Y2 enable 時 follower 複製的是 verified alpha 而非希望。

### Y1 self-trading evidence accumulation 路徑

Sprint 1B → Sprint 10 期間 self-trading 持續產出以下 evidence 給 Y1 末 gate evaluation 用：

- **C10 funding harvest**（Sprint 1B live，36/52 週）— funding alpha 是否 net positive
- **Unlock SHORT**（Sprint 4 live，25/52 週）— token unlock event-driven alpha
- **Pairs trading**（Sprint 5 live，17/52 週）— cross-symbol mean reversion alpha
- **C13 defined-risk options VRP**（Sprint 6 live，11/52 週）— vol risk premium harvest
- **Funding short-only**（Sprint 6 live，13/52 週）— directional funding extreme

各策略 promotion 走 Stage 0R replay preflight → Demo Stage 1 → live 路徑（per AMD-2026-05-15-01 Stage transitions）；evidence 累積在 PG `trading.fills` + `learning.attribution_chain` + 對應 Track schema (V101/V102)。

### 為什麼用 4 gate 而非單一 PnL gate

單一 PnL gate（如「Y1 net positive 才 enable」）容易在 P&L 接近 0 時做出錯誤判斷——一條策略可能 P&L 正但 Sharpe 低、drawdown 大、governance 不紀律，這種「複製出去」對 follower 是 net negative。4 gate 把 evaluation 拆成正交維度：

1. **Alpha gate** — 策略真的有 edge（Sharpe / hit rate / drawdown）
2. **Governance gate** — 系統真的紀律（Decision Lease 通過率、Guardian 攔截次數、Operator override 次數）
3. **Infrastructure gate** — 系統真的穩定（uptime / WS reconnect / DB integrity / migration 紀錄）
4. **Regulatory gate** — Bybit Copy Trading ToS 在 Y1 末仍允許 + project 仍符合 ToS 要求

任一 gate fail = 不 enable Y2 Copy Trading；4 gate 同時 PASS = Y2 可進入 Copy Trading infrastructure build phase（v5.7 §9 Sprint 9 已預留 100-140 hr「Continue Advisory + Copy Infra build」）。

## Decision

**Proposed**：在 Y1 末（Sprint 10 W36-39）執行 4-gate evidence evaluation；4 gate 全 PASS 才 enable Y2 Copy Trading；任一 gate FAIL 則延後至下個 evaluation cycle（v5.7 thesis 不變但 timing 延後）。

### 4-Gate Evidence Evaluation Framework

#### Gate 1 — Alpha Gate（策略表現）

| Sub-criterion | Threshold | 數據源 |
|---|---|---|
| Aggregate Sharpe ratio (Y1 portfolio) | ≥ 0.8 net of cost | `learning.attribution_chain` + `trading.fills` aggregate |
| Per-strategy hit rate | ≥ 3/5 策略 hit_rate ≥ 50% live demo + live (`engine_mode IN ('live','live_demo')`) | per-strategy aggregation |
| Maximum drawdown (Y1) | ≤ 15% account peak-to-trough | account balance reconciliation |
| Net PnL (Y1, post-cost) | ≥ $300（per §1 honest Y1 lower bound） | trading.fills + 主帳 reconciliation |

**FAIL trigger**：任一 sub-criterion below threshold = Gate 1 FAIL。

#### Gate 2 — Governance Gate（系統紀律）

| Sub-criterion | Threshold | 數據源 |
|---|---|---|
| Decision Lease 通過率（intent → execute） | ≥ 95%（5% 以下被 Guardian 拒等於系統紀律問題） | `learning.decision_lease_log` |
| Guardian 攔截次數 / 月 | ≤ 5（多於此值 = 策略反復試探風控邊界） | `learning.guardian_block_log` |
| Operator override 次數 / 月 | ≤ 3（多於此值 = AI 判斷與 operator 持續分歧） | `learning.operator_override_log` |
| Authorization audit | 100% live 行動有 valid signed authorization | `auth.authorization_audit` |

**FAIL trigger**：任一指標超出 threshold 或 audit 缺漏 = Gate 2 FAIL。

#### Gate 3 — Infrastructure Gate（系統穩定）

| Sub-criterion | Threshold | 數據源 |
|---|---|---|
| Engine uptime (Y1) | ≥ 99.0%（rolling 30d） | systemd journal + watchdog |
| Bybit WS reconnect events / week | ≤ 10（多於此值 = 連線品質差） | `ws_client` log |
| DB integrity (Track attribution chain) | `attribution_chain_ok` rolling 7d ≥ 99% | `learning.attribution_chain_status` |
| Migration 紀錄完整 | V094-V104+ 全部 Linux PG dry-run + post-apply healthcheck 通過 | `helper_scripts/db/migration_audit.py` |
| Sprint 0-10 critical incident count | 0 P0 + ≤ 3 P1（資安、生存、不可逆動作） | `docs/worklogs/` + KNOWN_ISSUES.md |

**FAIL trigger**：任一指標超出 threshold = Gate 3 FAIL。

#### Gate 4 — Regulatory Gate（合規）

| Sub-criterion | Threshold | 數據源 |
|---|---|---|
| Bybit Copy Trading ToS 在 Y1 末仍允許 algorithmic copy | YES | Bybit ToS 最新版本 |
| Project authorization model 與 Bybit Copy Trading 要求兼容 | YES（如 master account 必須 verified + KYC 完整） | BB review + Bybit account dashboard |
| Local jurisdiction 對 algorithmic copy trading 立場 | YES（Y1 期間若任何 jurisdiction 立法禁止 = FAIL） | legal review（cost：minimal — 主要 read regulation update） |
| 反洗錢 / KYC 在 follower 端的可行性 | YES（Bybit 提供 follower KYC，project 不需自建） | Bybit Copy Trading product spec |

**FAIL trigger**：任一指標 NO = Gate 4 FAIL。

### Gate 評估流程（Sprint 10）

```
W36 (Sprint 10 開始):
  - PA 派 evidence collector cron job 跑 Y1 全 52w aggregation
  - 4 個 gate sub-criterion 全部 query 出來，evidence 落 PG learning.copy_trading_y1_evaluation table

W37:
  - QC + FA + BB 三方獨立 review 4 gate evidence
  - 每方獨立給 PASS/FAIL/MARGINAL verdict
  - 三方 verdict 不一致 → Operator 仲裁

W38:
  - 三方共識後出 verdict report
  - 4 gate 全 PASS → Y2 Copy Trading Infra build phase enabled
  - 任一 gate FAIL → 延後 90d，下個 evaluation cycle

W39 (Sprint 10 結束):
  - 結論進 ADR-0030 amendment（記錄 Y1 末 actual gate scores + decision）
  - 若 PASS：派 PA 啟動 Y2 Copy Trading infra spec
  - 若 FAIL：派 PA 出 self-trading remediation plan
```

### 為什麼 Y1 期間禁止任何 Copy Trading 對外行為

Y1 期間 strict prohibition：

1. **禁止 Bybit Copy Trading 平台註冊為 master trader** — Y1 self-trading 未證明 alpha 前 follower 即使加入也是 noise replication
2. **禁止任何 follower 招募 / marketing** — 包括社群媒體、Telegram、Discord、Twitter 等任何形式
3. **禁止 take fee / profit-share** — 沒有 follower 也沒有 fee 結構需要設計
4. **禁止 build Copy Trading infrastructure** — Sprint 1-8 完全不應在 Copy Trading 路徑寫代碼；Sprint 9 才開始 infra build（且 build = 設計而非啟動）

**例外**：Y1 期間可以做 Copy Trading **read-only research**——研究 Bybit Copy Trading 平台機制、follower 行為、市場上現有 master trader 表現模式——這類 research 屬於 Sprint 10 Gate 4 Regulatory 評估的準備工作。

### Y2 enable 後的後續治理（不在本 ADR 範圍）

若 Sprint 10 W38 verdict = PASS，Y2 進入 Copy Trading infra build phase 後的後續 ADR 應涵蓋：

- ADR-XX：Copy Trading follower 風險隔離（follower 不能損害 master 帳本）
- ADR-XX：Profit-share 結構與 take fee timing
- ADR-XX：Master trader 行為與 follower 期望管理（如 strategy disclosure、drawdown notification）
- ADR-XX：Copy Trading 與既有 5-Agent runtime 的協作邊界（Guardian 是否需擴展 follower-aware risk envelope）

本 ADR 只 lock Y1 末 gate evaluation framework；Y2 細節留待 PASS 後新 ADR。

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **Timeline-gated（Y2 W40 自動 enable）** | 違反原則 5/16；Y1 alpha 失敗時把錯誤策略放大到 follower 端 |
| **單一 PnL gate（Y1 net positive 即 enable）** | P&L 接近 0 時誤判；Sharpe / drawdown / governance 維度同等重要 |
| **2-gate evaluation（Alpha + Regulatory）** | 漏 Governance + Infrastructure，會在系統紀律不足時 enable，follower 將承受 Decision Lease bypass / Guardian 失靈風險 |
| **6-gate evaluation（額外加 ML 表現 + Operator 評估）** | 過度設計；ML 表現已包含在 Alpha gate 的 Sharpe，Operator 評估屬於 Governance gate Operator override 次數的 derived metric |
| **Y1 末不評估，直接放棄 Copy Trading** | 與 v5.7 §1 honest income recompute 提到的「+$50-150k Y10 stretch with Copy Trading scaling」相違；放棄 = 主動關閉 optionality |
| **Y1 末評估但 fail 後永久放棄** | 過於決絕；fail 可能因為 timing 而非 thesis（如某 quarter 市場特殊）；應該允許下個 90d cycle 重評 |

## Consequences

### Positive

- **Y2 Copy Trading enable 綁定 verified self-trading evidence** — 不會把錯誤策略放大到 follower 端，對齊原則 5/16
- **4 gate 正交設計** — Alpha / Governance / Infrastructure / Regulatory 各自獨立評估，避免單維度誤判
- **Y1 期間 strict prohibition** — Sprint 1-8 工程精力集中在 self-trading alpha 與系統紀律，不分散到 Copy Trading 路徑
- **延後機制設計** — Gate FAIL 不 = 永久放棄，下個 90d cycle 重評；保留 optionality
- **與 v5.7 §1 honest income recompute 對齊** — Y1 income $300-550 不含 Copy Trading；Y2+ Copy Trading 是 stretch upside 不是 baseline

### Negative / Risk

- **Sprint 10 W36-39 評估期 evidence aggregation 工作量** — 需 QC + FA + BB 三方 review，估 ~30-50 hr 共同投入；mitigation = Sprint 9 提前 100-140 hr「Continue Advisory + Copy Infra build」期間預備 evidence pipeline + dashboard，Sprint 10 主要做 verdict 而非 from-scratch query
- **4 gate threshold 主觀性** — 如 Sharpe 0.8 vs 0.9 是 PASS/FAIL boundary，可能引起爭議；mitigation = 三方獨立 review + Operator 仲裁；threshold 一旦進 ADR-0030 即 locked，後續調整需走 ADR amendment
- **Gate 4 Regulatory 對 jurisdiction 變化敏感** — Y1 期間若任何 jurisdiction 立法禁止 = FAIL 但項目本身未失敗；mitigation = legal monitoring 屬於 BB 持續責任，非 Sprint 10 才啟動
- **「永遠不 enable」風險** — 4 gate 設計嚴格可能導致永遠 enable 不了；mitigation = gate threshold 進 ADR 後若連續 2 cycle FAIL 應該觸發 ADR-0030 amendment 重審 threshold 而非繼續執行
- **Bybit Copy Trading 平台變動風險** — Bybit 可能在 Y1 期間調整 Copy Trading 機制（如 fee 結構、master 要求），mitigation = BB 持續監測 + Gate 4 sub-criterion 對齊最新 Bybit ToS

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| ADR-0006 (Bybit-only exchange) | **Copy Trading 在 Bybit 內進行**；ADR-0006 確認單一 exchange 立場意味著 Copy Trading 只能用 Bybit 既有平台機制，不擴展到 cross-venue copy |
| ADR-0033 (ADR-0006 amendment — DEX/Hyperliquid NOT approved) | **Copy Trading 不擴展到 DEX/Hyperliquid**；本 ADR 與 ADR-0033 都將 Bybit 鎖為唯一 venue |
| v5.7 §1 honest Y1 income | **Y1 不算 Copy Trading 為 income lane**；本 ADR 鎖定 Y1 strict prohibition 對齊該假設 |
| v5.7 §9 Sprint 10 evaluation timeline | **本 ADR 為該 evaluation 的 framework spec**；Sprint 10 W36-39 任務細節對齊本 ADR §Gate 評估流程 |
| AMD-2026-05-15-01 Stage transitions | **Y2 Copy Trading enable 時須對齊 Stage transitions**；follower-aware Stage 0R replay 是新議題，留待 Y2 ADR |
| ADR-0008 Decision Lease state machine | **Copy Trading 不繞 Decision Lease**；follower 端 mirror order 本質上是 master Decision Lease 的 replication，不創造新 lease 路徑（但 follower-aware lease ttl / cancel 邏輯待 Y2 spec） |
| ADR-0017 Scanner is evidence not authority | **Copy Trading evidence 評估對齊「evidence not authority」原則**；Sprint 10 verdict 報告是 evidence，Operator 仲裁是 authority |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | Copy Trading enable 後 follower 端 mirror 不繞 IntentProcessor，但 follower trade 本質上是 Bybit-side 機制（master 不直接代下單） |
| 2 | 讀寫分離 | ✅ | Sprint 10 evaluation 是純讀（query learning + trading 表）；不寫 live state |
| 3 | AI 輸出 ≠ 命令 | ✅ | 4 gate verdict 經 QC + FA + BB 三方 review + Operator 仲裁；不是 AI 自動決定 |
| 4 | 策略不繞風控 | ✅ | Copy Trading enable 後 follower 端 mirror 必須對齊 master Guardian-checked 路徑 |
| 5 | 生存 > 利潤 | ✅ | 4 gate 全 PASS 才 enable，避免把錯誤策略放大到 follower 端 |
| 6 | 失敗默認收縮 | ✅ | 任一 gate FAIL = 不 enable + 延後 90d；fail-closed 友善 |
| 7 | 學習 ≠ Live | ✅ | Y1 evaluation 是 learning 環節；不影響 live state 直到 Operator 仲裁批准 |
| 8 | 交易可解釋 | ✅ | 4 gate evidence 完整可審計；verdict 報告進 ADR-0030 amendment |
| 9 | 雙重防線 | ✅ | 4 gate 正交設計提供多層 sanity check |
| 11 | Agent 最大自主 | ✅ | Y1 Agent 在 P0/P1 邊界內自主；Y2 Copy Trading enable 後 Agent 行為照常，follower 是 Bybit 平台 mirror 不影響 Agent 自主 |
| 13 | cost 感知 | ✅ | Sprint 10 evaluation 30-50 hr 工時已在 v5.7 §9 Sprint 10 70-100 hr 預算內 |
| 14 | 零外部成本 | ✅ | Bybit Copy Trading 平台費用由 Bybit 收取，project 不引入新付費服務 |
| 16 | Portfolio > 孤立 trade | ✅ | 4 gate 採 portfolio-level Sharpe + 跨策略 hit rate；不單看任一策略 |

## Cross-References

- **v5.7 §1 Y1 income recompute**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:30-103`（Y1 honest $300-550 不含 Copy Trading）
- **v5.7 §9 Sprint 10**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:308`（Y1 Review + Copy Trading Evidence Gate + Overlay verdict 70-100 hr）
- **v5.7 §11 ADR-0028 提案**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:366`（本 ADR 順移為 0030 因 0028 已被 close_maker_fallback_reason 占用）
- **ADR-0006**：`docs/adr/0006-bybit-only-exchange.md`（Bybit-only 單一 exchange baseline）
- **ADR-0033**：本批次 ADR-0006 amendment（DEX/Hyperliquid NOT approved）
- **ADR-0008**：`docs/adr/0008-decision-lease-state-machine.md`（Copy Trading follower-aware lease 留待 Y2 spec）
- **ADR-0017**：`docs/adr/0017-scanner-is-evidence-not-authority.md`（evidence 評估對齊原則）
- **AMD-2026-05-15-01**：Stage transitions baseline（Y2 Copy Trading enable 後須對齊）
- **Bybit Copy Trading ToS**：BB 持續監測，最新版本以 Bybit 官網為準

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via v5.7 §11 + §12 governance recap | 2026-05-21 | 🟡 PROPOSED-pending-commit |
| TW | 本文件起草（v5.7 §11 提案落地為 ADR-0030 draft） | 2026-05-21 | ✅ Drafted |
| QC | Sprint 10 W37 4 gate evidence review owner（PASS/FAIL verdict） | TBD（Sprint 10） | 🟡 PENDING |
| FA | Sprint 10 W37 4 gate evidence review owner（PASS/FAIL verdict） | TBD（Sprint 10） | 🟡 PENDING |
| BB | Sprint 10 W37 Gate 4 Regulatory review owner + Y1 期間 Bybit ToS 持續監測 | TBD（持續 Y1 + Sprint 10） | 🟡 PENDING |
| PM | Sprint 10 W38 三方 verdict 仲裁 + ADR-0030 amendment 落地 | TBD（Sprint 10 W38） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0030 — Copy Trading Activation: Y1 末 4-Gate Evidence Evaluation, Y2 Enablement Conditional (Proposed)*
