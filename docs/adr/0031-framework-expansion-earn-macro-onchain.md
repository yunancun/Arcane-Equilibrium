# ADR 0031: Framework Expansion — Earn Governance + Macro Counterfactual + On-Chain Counterfactual

Date: 2026-05-21
Status: **Proposed-pending-commit**（v5.7 §11 ADR-0029 提案順移為 0031；本 ADR 為三個正交 framework 同時鎖入治理 ledger）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via v5.7 §11 Reviewer Condition 2/3/6 + §12 governance recap）
Related: v5.7 §4 (Bybit Earn dynamic APR + governance) / v5.7 §5 (Macro/On-Chain counterfactual only Y1) / v5.7 §8 Sprint 1A (Earn API recorder + Macro feed + Tokenomist NEW) / v5.7 §11 Reviewer Conditions / ADR-0032 (Earn asset movement Guardian — 本 ADR 拆分後的 asset movement 細節)

## Context

### 起源

v5.7 dispatch-safe patch 第 2、5、6 三個 Reviewer correction 涉及三個正交但需要同時治理的 framework：

| Reviewer Correction | v5.6 Issue | v5.7 Fix 框架 |
|---|---|---|
| #2 | Earn APR hardcoded 4-8% (false: tiered 8-11% first $200 + 3% rest = $1k effective ~4.4%) | **Earn dynamic APR tracking framework** |
| #5 | Macro/on-chain counted +2-3% APR uplift (unverified features) | **Counterfactual-only logging framework Y1** |
| #6 | Earn deposits no governance policy (asset write operation) | **Earn movement Guardian policy framework** |

v5.7 §11 將此三個 framework 提案為 ADR-0029（**順移為本 ADR-0031**，因 ADR-0029 已被 market.public_trades + market.orderbook_l2_snapshot storage policy 占用）。

本 ADR 同時 lock 三個 framework 的**設計意圖 + Y1 邊界 + 治理基線**；其中 Earn asset movement Guardian 政策的執行細節（5-gate adapter / Decision Lease retrofit / audit log）由 ADR-0032 獨立拆分（細節較重需專屬 ADR）。

### 為什麼三個 framework 同時鎖入

三者看起來正交但有共同設計脈絡：

1. **三者都涉及「外部數據 / 外部資產」進入 system 的治理邊界** — Earn API（外部資產移動）+ Macro feed（外部事件數據）+ On-chain feed（外部鏈上信號）
2. **三者都需要 Y1 「先觀察、後 enable」的紀律** — Earn 在 §4 manual rebalance first 3 months；Macro / On-chain 在 §5 counterfactual only Y1
3. **三者都受同一 source of truth 約束**：v5.7 §1 honest income recompute **不算 macro / on-chain 為 income**，**只算 Earn tiered APR 為 income (~$26 Y1)**
4. **三者一起進治理 ledger 才能避免「framework 漂移」** — 例如未來如果只開 macro framework 而沒 lock counterfactual-only 紀律，會出現「macro 開了之後悄悄影響 strategy trigger」的 governance drift

### v5.6 三個 framework 的 issue 共性

v5.6 三個 issue 共享一個 root cause：**未區分「數據接入」與「production trigger 用」的治理邊界**：

- Earn：v5.6 把 APR 寫成靜態 4-8%，等於 APR data ingestion 與 strategy decision 變成耦合的 static config
- Macro：v5.6 算 +1-3% APR uplift 進 income，等於 macro feed ingestion = production trigger
- On-chain：v5.6 算 +1-2% APR uplift 進 income，等於 on-chain feed ingestion = production trigger

v5.7 把三者統一改為「**數據接入 ≠ production trigger**」紀律：所有 Y1 期間新接入的外部數據源默認為 read-only logging + counterfactual A/B；production trigger enable 需獨立 evidence-based decision（per Y1 末 evaluation 或對應 framework 的 promotion gate）。

### v5.7 §1 honest income recompute 對 framework 的反向約束

v5.7 §1 Y1 income 細項：

```
Bybit Earn cash management (tiered APR realistic):
  - First $200 @ ~10% = $14 (annualized $20 × 0.69 = $14)
  - Remaining $600 @ ~3% = $12 ($18 × 0.69 = $12)
  - Subtotal: $26 (vs v5.6 wrong $33)

Macro overlay: $0 counted (counterfactual logging only)
On-chain signals: $0 counted (counterfactual logging only)
```

**Earn $26 是 Y1 income** → Earn framework 必須在 Y1 真實接通 API + 寫盤
**Macro $0 / On-chain $0** → Macro/On-chain framework 在 Y1 是 evidence pipeline，不接 trigger

本 ADR 鎖定這個 income 區別的對應 framework 紀律。

## Decision

**Proposed**：Lock 三個 framework 的設計意圖 + Y1 邊界 + 治理基線；Earn asset movement Guardian 政策的執行細節拆分到 ADR-0032。

### Framework 1 — Bybit Earn Dynamic APR + Governance Policy

#### 1.1 APR Dynamic Tracking 設計意圖

| 元素 | 設計 |
|---|---|
| APR 數據源 | Bybit Earn API（v5.7 §8 Sprint 1A 新接入；read-only） |
| Tier 結構認知 | First $200 tier ~10%，subsequent tier ~3%；effective APR = weighted average per stake amount |
| 採樣頻率 | 每次 stake/redeem decision 前 query；不可用 cached static APR |
| 寫盤 | `learning.earn_apr_log` table（per stake event 留 APR snapshot） |
| Portfolio yield 重算 | 對齊 actual API rates；不再用 v5.6 hardcoded 4-8% |

#### 1.2 Earn Asset Movement Governance 設計意圖（細節 in ADR-0032）

- 每次 stake/redeem operation = asset write，需 authorization
- Guardian-checked：與 trading 同 risk envelope
- Decision Lease pattern：stake intent → guardian → execute → audit log
- Auto-redeem trigger：trading margin headroom < 30%
- Manual rebalance first 3 months；auto 後續（per Y1 評估）
- 內部 audit log：`learning.earn_movement_log` table

**詳細執行細節（5-gate adapter / Decision Lease 改造 / audit log schema）見 ADR-0032。**

#### 1.3 Earn Engineering Scope（per §4）

| 項目 | 工時 |
|---|---|
| Earn API integration (Bybit API extension) | ~15 hr |
| Governance integration (Guardian + Decision Lease) | ~20 hr |
| Audit log schema + writer | ~10 hr |
| **Total** | **~45 hr** |

（v5.6 估 10 hr 太低；v5.7 修為 45 hr）

#### 1.4 Earn Y1 邊界

- **Sprint 1A**：Bybit Earn API APR recorder（read-only，no stake yet）
- **Sprint 1B**：Earn governance policy land + first small manual stake $200-400
- **Sprint 1B-4 (3 months)**：Manual rebalance only；不開 auto
- **Sprint 5+**：若前 3 months 紀律無事故 → 開 auto-redeem gate（margin headroom < 30% trigger）
- **不允許**：Y1 期間任何「APR static config」、「stake 繞 Guardian」、「Decision Lease bypass」

### Framework 2 — Macro Overlay Counterfactual-Only Y1

#### 2.1 設計意圖

| 元素 | 設計 |
|---|---|
| 數據源 | Macro calendar feed（v5.7 §8 Sprint 1A 新接入：FOMC / CPI / halving） |
| Y1 模式 | **Read-only logging + Counterfactual A/B** |
| Counterfactual 結構 | 對每個 strategy decision，logger 記錄「假設 macro overlay enable 時是否會改變決策」 |
| Production trigger 接通 | **禁止**（Y1）；Y1 末 evidence 判斷後可能 Y2 enable |
| Y1 income 計入 | **$0**（counterfactual only） |
| Y1 末 evaluation | counterfactual evidence 顯示 macro overlay 對 strategy 真有 +2%+ alpha → Y2 enable |
| Y1 末 retire 條件 | counterfactual evidence 顯示 null/marginal → retire layer，save engineering |

#### 2.2 Macro Engineering Scope（per §5）

| 項目 | 工時 |
|---|---|
| Macro feed + counterfactual logger | 25-35 hr |
| A/B evaluation framework（共享 on-chain） | 15-20 hr |
| **Macro 部分小計** | **40-55 hr** |

#### 2.3 Macro Y1 邊界

- **Sprint 1A**：Macro calendar feed NEW + counterfactual logger 寫盤
- **Sprint 2-10**：持續累積 counterfactual A/B evidence
- **Sprint 10 W36-39**：Y1 末 evaluation 出 Y2 verdict（enable / retire）
- **不允許**：Y1 期間 macro overlay 影響 strategy trigger；不允許算 macro 為 Y1 income

### Framework 3 — On-Chain Signals Counterfactual-Only Y1

#### 3.1 設計意圖

| 元素 | 設計 |
|---|---|
| 數據源 | On-chain feed（v5.7 §8 隱含 Sprint 2 設置：on-chain counterfactual setup） |
| Y1 模式 | **Read-only logging + Counterfactual A/B** |
| Counterfactual 結構 | signal generation + outcome correlation；對每個 strategy outcome 留 on-chain signal value snapshot |
| Production trigger 接通 | **禁止**（Y1）；Y1 末 evidence 判斷後可能 Y2 enable |
| Y1 income 計入 | **$0**（counterfactual only） |
| Y1 末 evaluation | counterfactual evidence 顯示 on-chain signal 對 strategy 真有 +1%+ alpha → Y2 enable |
| Y1 末 retire 條件 | counterfactual evidence 顯示 marginal → retire layer |

#### 3.2 On-Chain Engineering Scope（per §5）

| 項目 | 工時 |
|---|---|
| On-chain feed + counterfactual logger | 30-40 hr |
| A/B evaluation framework | (共享 macro，已計上) |
| **On-chain 部分小計** | **30-40 hr** |

（Macro + On-chain framework 合計 70-95 hr，per §5 v5.7 fix）

#### 3.3 On-Chain Y1 邊界

- **Sprint 2**：On-chain counterfactual setup 啟動
- **Sprint 3-10**：持續累積 counterfactual A/B evidence
- **Sprint 10 W36-39**：Y1 末 evaluation 出 Y2 verdict
- **不允許**：Y1 期間 on-chain signal 影響 strategy trigger；不允許算 on-chain 為 Y1 income

### 三個 Framework 共享治理紀律

1. **數據接入 ≠ production trigger** — Earn API 接通是為了 APR query 而非「APR 自動觸發 stake」；Macro / On-chain feed 接通是為了 counterfactual logger 而非 strategy trigger
2. **Y1 末 evaluation cadence** — 三個 framework 都在 Sprint 10 W36-39 與 Copy Trading (ADR-0030) 共用 evaluation window
3. **Counterfactual A/B framework 共用** — Macro 與 On-chain 共享同一 A/B framework（v5.7 §5 估 15-20 hr 共享 cost）；架構需可 generalize 未來其他 counterfactual layer
4. **失敗默認 retire 而非升級** — Y1 末 evaluation 若 marginal/null → retire layer，避免 sunk cost fallacy 繼續維護無 alpha 的 layer

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **三個 framework 分三個 ADR（0031/0032/0033）** | 三者共享治理紀律 + Y1 末 evaluation cadence + counterfactual A/B framework，分三 ADR 會割裂 framework 共性；Earn asset movement Guardian 細節因執行複雜獨立拆出 ADR-0032 已足夠 |
| **Earn / Macro / On-chain 全部 Y1 接 production trigger** | (a) 違反 v5.7 §1 honest income recompute（Y1 macro/on-chain $0）；(b) 違反 §5 Reviewer correction（unverified features 不算 alpha）；(c) Earn 在未經 Guardian 紀律驗證前自動 stake = asset write 風險 |
| **三 framework 全 retire 不做** | (a) Earn API APR 是真實 Y1 income $26 不應放棄；(b) Macro / On-chain 是 Y2+ stretch upside（per v5.7 §2 Y2 with overlay verified +1-2% alpha），放棄等於主動關閉 optionality |
| **三 framework 全 Y1 末 evaluation 用同一 4-gate（如 ADR-0030 Copy Trading）** | 維度不同：Copy Trading 4 gate 是 Alpha/Governance/Infrastructure/Regulatory；Macro/On-chain 是純 counterfactual A/B evidence（單維度判斷）；Earn 是 governance 紀律驗證（first 3 months manual review）；強行對齊會引入無關 sub-criterion |
| **Earn API APR 在 Y1 一開始就 auto-stake** | 違反 §4「Manual rebalance initially (first 3 months); auto after proven」+ §6 Earn deposits no governance = asset write 風險 |

## Consequences

### Positive

- **三個 framework 統一治理紀律** — 「數據接入 ≠ production trigger」原則 lock 進 ADR，避免未來 framework 漂移
- **Y1 末 evaluation cadence 統一** — Sprint 10 W36-39 同時做 Copy Trading (ADR-0030) + Macro + On-chain 三個 evaluation，運維集中
- **Counterfactual A/B framework 復用** — Macro / On-chain 共享同一 A/B framework，未來其他 counterfactual layer 可重用，省工時
- **Earn $26 Y1 income 落地路徑明確** — Sprint 1A API recorder + Sprint 1B 首次 manual stake，與 v5.7 §1 honest income 對齊
- **失敗默認 retire 紀律** — 避免 sunk cost fallacy；evidence-based decision

### Negative / Risk

- **Earn governance integration 工時 45 hr 是 Sprint 1A/1B 主要工程** — 占 Sprint 1A 60-80 hr 一半以上；mitigation = Sprint 1A 派 E1 dispatch 時明確 Earn 為 P0 任務、其他 sensor (options recorder / Tokenomist / Binance perp WS) 與 Earn 並行避免阻塞
- **Counterfactual A/B framework Y1 evidence 量問題** — Macro 事件如 FOMC 一年 8 次、CPI 一年 12 次，Y1 樣本量可能太小無法判定 alpha；mitigation = Y1 末 evaluation 必須包含「樣本量不足」verdict option，不強迫 enable/retire 二選一
- **三 framework 共用 Sprint 10 evaluation window** — Sprint 10 70-100 hr 預算需同時處理 Copy Trading 4-gate + Macro + On-chain + Y1 review；mitigation = Sprint 9 100-140 hr 預備 evidence pipeline + dashboard，Sprint 10 主要做 verdict
- **Earn API tier 結構變動風險** — Bybit 可能在 Y1 期間調整 Earn tiered APR；mitigation = API 動態 query 設計已 cover；APR 變動本身屬於正常市場變化
- **Macro / On-chain Y1 evaluation 「marginal」判定主觀** — counterfactual A/B 是否「+2%+ alpha」是 binary 判定，但實際可能在 ±1% 邊界；mitigation = Y1 末 evaluation 加 MARGINAL verdict option + 90d cycle 重評（對齊 ADR-0030 Gate 評估流程）

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| ADR-0006 (Bybit-only exchange) | **Earn framework 對齊 Bybit-only**；不在 Binance 開 Earn |
| ADR-0008 (Decision Lease state machine) | **Earn asset movement Decision Lease pattern**（細節 in ADR-0032） |
| ADR-0017 (Scanner is evidence not authority) | **Macro / On-chain counterfactual evidence 對齊 evidence-not-authority 原則** |
| ADR-0030 (Copy Trading evidence-gated) | **Sprint 10 evaluation window 共用**；4 個 Y1 末 framework decision 集中處理 |
| ADR-0032 (Earn asset movement Guardian) | **本 ADR Framework 1 §1.2 細節拆分到 ADR-0032** |
| v5.7 §1 honest income recompute | **本 ADR Y1 income 邊界對齊**（Earn $26 / Macro $0 / On-chain $0） |
| v5.7 §4 Bybit Earn governance | **本 ADR Framework 1 spec** |
| v5.7 §5 Macro/On-chain counterfactual | **本 ADR Framework 2/3 spec** |
| v5.7 §8 Sprint 1A | **Earn API recorder + Macro feed + Tokenomist NEW 都在 Sprint 1A**；本 ADR 鎖入治理基線 |
| AMD-2026-05-15-01 Stage transitions | **Macro / On-chain Y1 末 Y2 enable 時須對齊 Stage 紀律**（Stage 0R replay preflight） |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | Earn stake 走 Decision Lease + Guardian（細節 ADR-0032）；Macro / On-chain Y1 不接 trigger |
| 2 | 讀寫分離 | ✅ | Y1 三 framework 主要是 read-only + counterfactual logging；Earn manual stake 是受控寫入 |
| 3 | AI 輸出 ≠ 命令 | ✅ | Earn auto-redeem trigger (Y1 後)、Macro/On-chain Y2 enable 皆走 evidence-based decision + Operator 仲裁 |
| 4 | 策略不繞風控 | ✅ | Earn stake 受 Guardian envelope；Macro / On-chain 不接 strategy trigger 等於不繞風控 |
| 5 | 生存 > 利潤 | ✅ | Earn manual first 3 months；Macro / On-chain 不接 trigger；保守紀律優先 |
| 6 | 失敗默認收縮 | ✅ | Y1 末 evaluation 預設 retire/marginal verdict，非「不 enable 就強升級」 |
| 7 | 學習 ≠ Live | ✅ | counterfactual 是學習；不影響 live state |
| 8 | 交易可解釋 | ✅ | Earn movement audit log + APR snapshot 完整；Macro / On-chain counterfactual A/B 完整可重現 |
| 9 | 雙重防線 | ✅ | Earn auto-redeem 走 Guardian + Decision Lease 雙層；Macro / On-chain 不接 trigger 沒風險 |
| 11 | Agent 最大自主 | ✅ | Agent 在 P0/P1 內自主使用三 framework 數據；不限縮 Agent 行為 |
| 12 | evidence-driven 演化 | ✅ | 三 framework 全部 evidence-gated；Y1 末 evaluation = 演化決策點 |
| 13 | cost 感知 | ✅ | Earn governance 45 hr + Macro/On-chain 70-95 hr 已在 v5.7 §9 預算內 |
| 14 | 零外部成本 | ✅ | Earn API + Macro feed + On-chain feed 都不引入付費服務（Macro 用 public calendar、On-chain 用 free tier RPC） |
| 16 | Portfolio > 孤立 trade | ✅ | Earn 是 portfolio-level cash management；Macro / On-chain 是 cross-strategy signal |

## Cross-References

- **v5.7 §1 honest Y1 income**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:30-103`（Earn $26 / Macro $0 / On-chain $0）
- **v5.7 §4 Bybit Earn governance**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:133-167`
- **v5.7 §5 Macro/On-chain counterfactual**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:171-204`
- **v5.7 §8 Sprint 1A**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:269-280`
- **v5.7 §11 ADR-0029 提案**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:367`（本 ADR 順移為 0031 因 0029 已被 market.public_trades + market.orderbook_l2_snapshot storage policy 占用）
- **ADR-0006**：`docs/adr/0006-bybit-only-exchange.md`（Earn framework 對齊 Bybit-only baseline）
- **ADR-0008**：`docs/adr/0008-decision-lease-state-machine.md`（Earn asset movement Decision Lease 細節 in ADR-0032）
- **ADR-0017**：`docs/adr/0017-scanner-is-evidence-not-authority.md`（counterfactual evidence 對齊原則）
- **ADR-0030**：本批次 Copy Trading evidence-gated（Sprint 10 evaluation window 共用）
- **ADR-0032**：本批次 Earn asset movement Guardian（Framework 1 §1.2 細節拆分）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via v5.7 §11 + §12 governance recap | 2026-05-21 | 🟡 PROPOSED-pending-commit |
| TW | 本文件起草（v5.7 §11 ADR-0029 提案順移為 ADR-0031 draft） | 2026-05-21 | ✅ Drafted |
| E1 | Earn API integration + counterfactual logger 實作 owner | TBD（Sprint 1A） | 🟡 PENDING |
| QC | Sprint 10 W36-39 Macro/On-chain counterfactual evidence verdict | TBD（Sprint 10） | 🟡 PENDING |
| FA | Sprint 10 W36-39 Earn governance 紀律 review | TBD（Sprint 10） | 🟡 PENDING |
| BB | Sprint 1A Bybit Earn API ToS + rate limit review | TBD（Sprint 1A） | 🟡 PENDING |
| PM | Sprint 10 W38 三 framework verdict 仲裁 + ADR-0031 amendment 落地 | TBD（Sprint 10 W38） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0031 — Framework Expansion: Earn Governance + Macro Counterfactual + On-Chain Counterfactual (Proposed)*
