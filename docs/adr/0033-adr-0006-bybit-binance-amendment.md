# ADR 0033: ADR-0006 Amendment — Binance Market-Data Approved · Binance Trading Defer Y2 · DEX/Hyperliquid NOT Approved · D12 + ToS Posture

Date: 2026-05-21
Status: **Accepted**（v5.7 §12 ADR-0006 amendment 提案落地為獨立 ADR；本 ADR 為 ADR-0006 amendment，不取代 ADR-0006）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via v5.7 §12 governance recap「ADR-0006 amendment: Bybit primary + Binance market data + DEX not approved」）
Related: ADR-0006 (Bybit-only exchange — 2026-04-03 baseline, amendment target) / v5.7 §6 (market.liquidations writer existing) / v5.7 §8 Sprint 1A (Binance market-data-only WebSocket NEW) / v5.7 §11 Reviewer Conditions / v5.7 §12 Governance Compliance Recap

## Context

### 起源

ADR-0006（2026-04-03 accepted）將 Bybit lock 為唯一 exchange，Binance「retained only as a hypothetical long-term option」。v5.7 dispatch-safe patch 期間 reviewer 與 PA / FA 評估後決定：

1. **保留 Bybit 為 primary trading venue**（ADR-0006 thesis 不變）
2. **新增 Binance 為 market-data-only auxiliary**（Y1 開放）— 用於 cross-venue funding rate / liquidation / volume comparison + counterfactual analysis；不在 Binance 下單
3. **Binance trading defer Y2**（Y1 不開放）— 評估 Y1 evidence 後再決定
4. **DEX / Hyperliquid 完全不開放** — 與 v5.6 thesis drift 區隔；明示「not approved」立場

v5.7 §12 將此立場提案為「ADR-0006 amendment」；本 ADR 為該 amendment 的獨立 ADR 落地。

### 為什麼 amendment 不取代 ADR-0006

ADR-0006 thesis「**Bybit is the sole execution venue**」**不變**：

- Bybit 仍為唯一 trading/order/risk/strategy venue
- 所有 Bybit-specific REST/WS/IPC integration 路徑（per `docs/references/2026-04-04--bybit_api_reference.md`）保留
- BB agent（Bybit Broker Compatibility Auditor）職權不變
- New Venue Adapter abstractions YAGNI 立場不變

本 ADR 只 amend ADR-0006 的「Binance retained only as a hypothetical long-term option」表述，改為「Binance market-data approved Y1，trading deferred Y2 evaluation」。

如果未來 Y2 evaluation 結果決定開 Binance trading，將是 ADR-0006 + ADR-0033 雙層 amendment（再開 ADR-XX 替換或補充）；本 ADR 不預判 Y2 結果。

### v5.7 §8 Sprint 1A 真實工作觸發 amendment 必要性

v5.7 §8 Sprint 1A 列「Binance market-data-only WebSocket NEW」工程任務。在沒有 ADR-0006 amendment 的情況下接 Binance WS 違反 ADR-0006 thesis（即使是 market-data-only），需要先正式 amendment ADR-0006 + 鎖入治理紀律才能合規 dispatch。

### 為什麼 DEX / Hyperliquid 需要明示 NOT approved

v5.6 → v5.7 過渡期間 reviewer 注意到一個風險：**「不提到 ≠ 不允許」**。如果 ADR-0006 amendment 只說「Binance 開放 market data」，不明示「DEX / Hyperliquid not approved」，未來可能出現以下漂移：

- PA 派工時誤認「ADR-0006 amend = 多 venue 開放」
- Sub-agent 自行判斷「ADR-0006 amendment 開了 Binance，那 DEX / Hyperliquid 應該也可以加」
- 工程開始接 DEX / Hyperliquid 數據源，後續才發現未授權

本 ADR 明示 DEX / Hyperliquid not approved 是「**proactive lock-down**」，避免漂移。

### v5.7 §10 honest aggregate outcomes 中的 Copy Trading scaling 不影響本 ADR

v5.7 §10 提到「Y2+ Copy Trading scaling: potential $50-150k Y10 stretch」。Copy Trading 在 Bybit 平台內進行（per ADR-0030），**不涉及 DEX / Hyperliquid 或其他 exchange**；本 ADR DEX/Hyperliquid not approved 立場與 Copy Trading scaling 不衝突。

### v5.7 §10 提及「skills + Copy Trading optionality」中的 skills 涵義

v5.7 §10 提及 Y10 differential 包含「skills」項。「Skills」指 self-trading 期間累積的 ML / trading / governance skills，**不是** cross-venue trading skill；本 ADR DEX/Hyperliquid not approved 不限縮 skills 累積路徑。

## Decision

**Proposed**：ADR-0006 amendment 為以下四項立場：

### Decision 1 — Binance Market Data Approved (Y1)

| 元素 | 設計 |
|---|---|
| 目的 | Cross-venue funding rate / liquidation / volume comparison + counterfactual analysis |
| 接入方式 | **Market-data-only WebSocket**（per v5.7 §8 Sprint 1A） |
| 接入範圍 | Spot/perp tickers + funding rate + liquidations + OHLCV；**禁止** trading endpoint 接入（包括 read-only order book endpoints 屬於 trading API 路徑也禁止接入） |
| Data 用途 | 純 read-only logging + analytics；**禁止**用作 strategy trigger（per ADR-0031 Framework 2/3 counterfactual-only 原則延伸） |
| 預期 Y1 income | $0（market data 不算 alpha） |
| Y1 engineering scope | per v5.7 §8 Sprint 1A 已估時間（Binance perp WS NEW，~10-15 hr 估算） |
| Schema 落地 | `market.binance_tickers` / `market.binance_funding_rates` / `market.binance_liquidations` 等獨立 namespace；不與 Bybit market table 混 |

#### Binance WS 對 Bybit baseline 的影響

- **不影響 Bybit-specific BB agent 職權**：BB 仍只負責 Bybit ToS / API spec 遵守；Binance 由獨立 review surface 處理
- **不影響 `bybit_api_reference.md`**：該文件保持 Bybit-only baseline；如需 Binance reference 另開 `binance_api_reference.md`（不在本 ADR 範圍）
- **不影響 V### migration 路徑**：Binance market data 用獨立 `market.binance_*` namespace，不污染既有 `market.*` Bybit schema

### Decision 2 — Binance Trading Defer Y2 (Conditional)

| 元素 | 設計 |
|---|---|
| Y1 模式 | **不開放任何 Binance trading endpoint** |
| Y1 期間禁止 | (a) 任何 Binance order placement (b) 任何 Binance authentication beyond market-data API key (c) 任何 Binance asset transfer / wallet operation |
| Y2 evaluation 觸發條件 | Y1 末（Sprint 10 W36-39）evaluation 包含「**Binance trading enablement gate**」sub-question |
| Y2 evaluation 通過條件 | (a) Y1 Bybit-only self-trading alpha 已驗證（per ADR-0030 Gate 1 Alpha） + (b) Y1 Binance market data analysis 顯示 cross-venue arbitrage / liquidation hunting 等 strategy 真有 +1%+ alpha vs Bybit-only baseline + (c) Operator 仲裁 + (d) BB confirmed Binance ToS / KYC 在我們的 jurisdiction 可行 |
| Y2 evaluation 失敗 → 繼續 defer | 任何條件 fail → 維持 Bybit-only trading，繼續 Y2 cycle 重評 |
| Y2 evaluation 永久放棄條件 | 連續 3 個 evaluation cycle (~12-18 months) fail → 開新 ADR 永久關閉 Binance trading optionality |

### Decision 3 — DEX / Hyperliquid NOT Approved (Y1 + Y2 Baseline)

| 元素 | 立場 |
|---|---|
| DEX (Uniswap / GMX / dYdX 等) | **NOT approved**（Y1 + Y2 baseline） |
| Hyperliquid | **NOT approved**（Y1 + Y2 baseline） |
| 為什麼 NOT approved | (a) DEX/Hyperliquid 是 on-chain settlement，違反 ADR-0006 single-venue thesis 的 architectural 簡化好處 (b) gas fee + bridge cost 對 $10k account 不經濟 (c) on-chain settlement 在 finality 不確定（rollup unwinds、reorgs）期間沒有 fail-closed pattern 對應 (d) Hyperliquid 雖然有 CEX-like 體驗但仍是 perp DEX，受 (a)/(b)/(c) 約束 |
| 未來開放的 ADR-debt | 若未來需要開放 DEX/Hyperliquid，必須開新 ADR 顯式 amendment 本 ADR；不可在沒有新 ADR 的情況下默認「框架擴展即可」 |
| 例外：on-chain feed read-only logging | per ADR-0031 Framework 3 (on-chain signals counterfactual-only Y1)，**read-only RPC query** （如查 token unlock event / on-chain TVL）**不屬於 DEX trading**，仍允許接入用於 counterfactual analysis |

### Decision 4 — D12 + ToS Posture

#### 4.1 D12（Diversification Rule 12）lock

| 元素 | 設計 |
|---|---|
| D12 定義 | Y1 期間任何單一 venue（含 Bybit）trading exposure 不可超過 80% 主帳；剩餘 20% 必須以 fiat / stablecoin 形式保留在 off-exchange (Revolut / Wise per v5.7 §1 honest income) |
| 計算範圍 | trading position notional + Earn stake amount + 主帳 free balance；分母為主帳 total assets |
| Bybit 適用 | 80% cap 對 Bybit total exposure（trading + Earn 合計）成立 |
| Off-exchange 用途 | 主帳被 freeze / Bybit ToS dispute / wallet incident 時的 emergency liquidity buffer |
| Trigger 行為 | Bybit total exposure > 80% → Guardian block 新 stake/order + alert Operator + 紀錄到 `learning.guardian_block_log` with `block_reason='d12_breach'` |

#### 4.2 ToS Posture

| 元素 | 設計 |
|---|---|
| Bybit ToS 遵守 | BB agent 持續監測（per ADR-0006 既有職權） |
| Binance ToS 遵守 | 新增 surface：Sprint 1A market-data WS 接入時需 Operator confirm Bybit + Binance KYC / API key 規範相容 |
| Cross-venue KYC dispute | 主帳 KYC 在 Bybit + Binance 兩平台保持一致（同 identity / address / source of funds 證明） |
| Y2 evaluation 包含 ToS 持續可行 | Decision 2 條件 (d) BB confirmed Binance ToS / KYC 在我們的 jurisdiction 可行；持續 monitoring |
| ToS 違反 fail-mode | 任一平台 ToS 違反 / dispute → 立即 freeze 該平台所有 outbound order；走 Operator 仲裁路徑 |

### ADR-0006 與本 ADR-0033 的關係

```
ADR-0006 (2026-04-03 accepted, baseline 不變)
  └─ Bybit is the sole execution venue
     └─ Multi-exchange support is descoped
        └─ Binance retained only as a hypothetical long-term option (← amendment 對象)

ADR-0033 (2026-05-21 proposed, amendment standalone)
  ├─ Decision 1: Binance market data approved Y1 (amend ADR-0006「only as hypothetical」)
  ├─ Decision 2: Binance trading defer Y2 (amend ADR-0006 同上)
  ├─ Decision 3: DEX/Hyperliquid NOT approved Y1+Y2 (擴展 ADR-0006 「single-venue thesis」明示邊界)
  └─ Decision 4: D12 + ToS posture (新增治理紀律，不在 ADR-0006 原範圍)
```

**ADR-0006 仍是 baseline 的 source of authority**；本 ADR-0033 是其唯一 amendment。任何未來進一步修改必須開新 ADR amend ADR-0033 + 標明對 ADR-0006 的相對立場。

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **直接 rewrite ADR-0006**（取代而非 amendment） | 違反 ADR governance pattern「ADR 接受後不修改，只能 superseded by 新 ADR」；ADR-0006 thesis Bybit-primary 不變，amendment 才是正確 pattern |
| **不寫 amendment，在 Sprint 1A 直接接 Binance WS** | 違反 ADR-0006「Bybit is the sole exchange」表述；即使是 market-data-only 也需 ADR 級立場 |
| **Amendment 只談 Binance，不提 DEX/Hyperliquid** | 「不提到 ≠ 不允許」漂移風險（per §Context）；proactive lock-down 是必要紀律 |
| **Amendment 開放 Binance trading Y1**（不 defer Y2） | (a) Y1 Bybit self-trading alpha 未驗證 + (b) Binance trading 引入新 surface (KYC dispute / API key 管理 / cross-venue position reconciliation) Y1 不該承擔；應走 evidence-gated 路徑 |
| **不設 D12 cap** | Y1 期間 single-venue freeze risk 對 $10k account 嚴重（80% 鎖在 Bybit 等於 100% exposure 給 Bybit incident）；D12 是 portfolio-level survival 紀律 |
| **D12 cap 設 50%（更保守）** | 50% off-exchange 意味著 50% 不參與 trading，違反 v5.7 §1 honest income recompute baseline（Y1 trading allocation $5,400-6,000）；80% cap 在 emergency liquidity 與 trading allocation 之間取平衡 |
| **DEX/Hyperliquid 改為「not approved Y1, defer Y2 evaluate」** | 與 Binance trading defer Y2 不同：Binance 有完整 KYC + spot/perp 與 Bybit 對等 architecture，evaluation 路徑可行；DEX/Hyperliquid 是 on-chain settlement 完全不同 architecture，evaluation 本身需要重新設計，Y1 + Y2 都不該 spend bandwidth |

## Consequences

### Positive

- **Binance market data 接入合規** — v5.7 §8 Sprint 1A 「Binance market-data-only WebSocket NEW」現在有 ADR 級授權；不違反 ADR-0006
- **明示 DEX/Hyperliquid not approved** — 避免「框架擴展即可」漂移；proactive lock-down
- **D12 cap 保護 single-venue freeze risk** — $10k account 在 Bybit incident 時仍有 20% emergency liquidity buffer
- **Y2 Binance trading evidence-gated** — 對齊 ADR-0030 / 0031 的 evidence-based decision pattern
- **ADR-0006 baseline 不變** — 不擾動既有 Bybit-only thesis 的工程與治理紀律
- **與 v5.7 §1 honest income recompute 對齊** — Binance market data $0 Y1 income；Off-exchange savings $80-100 Y1 income 與 D12 20% off-exchange 設計兼容
- **ToS posture 明確** — Bybit + Binance KYC 紀律統一，避免 cross-venue identity dispute

### Negative / Risk

- **Binance WS 接入引入新 surface（即使 market-data-only）** — 包括 API key 管理、ws reconnect、rate limit 規範等；mitigation = Sprint 1A 派 E1 dispatch 時對齊既有 Bybit WS 接入 pattern；Binance-specific 差異走獨立 module 不污染 `bybit_*` 模塊
- **D12 cap 80% 對 trading allocation 形成上限** — 若 Y1 Bybit Earn + trading exposure 接近 80% 時 auto-redeem 觸發頻繁；mitigation = ADR-0032 auto-redeem trigger margin headroom < 30% 與 D12 cap 80% 是兩個獨立 threshold，運作互補
- **Binance trading defer Y2 但 Y1 market data 已接入** — 容易在 Sprint 5-9 出現「市場機會看到但不能 Binance 下單」的 frustration；mitigation = 該 frustration 本身是 evidence accumulation 的一部分，Y1 末 evaluation 時可作為「Binance trading enable」的 sub-evidence
- **DEX/Hyperliquid 明示 not approved 可能在未來需要重新評估** — DeFi 生態 1-2 年內可能有新 surface；mitigation = 本 ADR 的 not approved 立場是 Y1+Y2 baseline，未來開新 ADR amendment 是允許路徑（per §Decision 3 ADR-debt note）
- **D12 計算邊界（Earn stake 是 Bybit exposure 嗎）** — Earn stake 在 Bybit Earn product，理論上 Bybit 自營 Earn = Bybit exposure，但第三方 issuer Earn 是 cross-counterparty exposure；mitigation = 本 ADR §4.1 明示「Bybit total exposure (trading + Earn 合計)」對 D12 cap 成立；第三方 issuer Earn 屬 ADR-0032 §Gate 2 Risk envelope sub-criterion 4「Bybit Earn product issuer trust level」處理
- **Off-exchange 20% 保留在 Revolut / Wise 也有 counterparty risk** — Revolut / Wise bank account freeze 屬於 single-counterparty exposure；mitigation = v5.7 §1 honest income recompute 已假設 Revolut + Wise 兩個帳戶分散；D12 設計與該假設兼容

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| ADR-0006 (Bybit-only exchange, 2026-04-03) | **本 ADR 為 ADR-0006 amendment**；ADR-0006 thesis 不變，只擴展 Binance market data + DEX/Hyperliquid not approved + D12 |
| `docs/references/2026-04-04--bybit_api_reference.md` | **保持 Bybit-only baseline**；Binance API reference 另開（不在本 ADR 範圍） |
| BB agent (Bybit Broker Compatibility Auditor) | **職權不變**；Binance review 屬於 BB 之外的 surface（Sprint 1A 派 E1 + BB 雙重 review） |
| ADR-0030 (Copy Trading evidence-gated) | **Copy Trading 在 Bybit 平台內進行**；本 ADR DEX/Hyperliquid not approved 不影響 Copy Trading |
| ADR-0031 (Framework expansion — Earn / Macro / On-chain) | **On-chain feed read-only logging 允許**（per §Decision 3 例外）；不違反 DEX/Hyperliquid not approved |
| ADR-0032 (Earn asset movement Guardian) | **D12 cap 與 ADR-0032 §Gate 2 Risk envelope 互補**；Earn stake 受 D12 + Earn Risk envelope 雙約束 |
| v5.7 §6 market.liquidations existing writer | **保留**；本 ADR Decision 1 Binance liquidations 接入用獨立 `market.binance_liquidations` namespace，不污染既有 `market.liquidations` Bybit baseline |
| v5.7 §8 Sprint 1A Binance market-data WS NEW | **本 ADR Decision 1 對應 ADR 級授權**；Sprint 1A dispatch 時 cite ADR-0033 |
| v5.7 §1 honest Y1 income (Off-exchange savings $80-100) | **D12 20% off-exchange 設計與該 income lane 兼容** |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | Bybit 仍為唯一 trading venue；Binance market-data 不創造寫入口 |
| 2 | 讀寫分離 | ✅ | Binance 是純讀 market data；DEX/Hyperliquid 不接入 |
| 3 | AI 輸出 ≠ 命令 | ✅ | Binance trading enable 走 Y2 evidence-based decision + Operator 仲裁 |
| 4 | 策略不繞風控 | ✅ | D12 cap 是新風控紀律；Binance market data 不影響 strategy trigger |
| 5 | 生存 > 利潤 | ✅ | D12 20% off-exchange = single-venue freeze risk 對策；off-exchange $80-100 income < trading allocation 但保命優先 |
| 6 | 失敗默認收縮 | ✅ | Binance trading defer Y2 = 預設不開；DEX/Hyperliquid not approved = 預設關閉 |
| 7 | 學習 ≠ Live | ✅ | Binance market data 是 evidence accumulation；Y1 不接 trigger |
| 8 | 交易可解釋 | ✅ | D12 breach event 進 guardian_block_log；Binance trading 若 Y2 enable 走 Decision Lease |
| 9 | 雙重防線 | ✅ | D12 cap + Bybit Earn Risk envelope（per ADR-0032）+ off-exchange 多層 |
| 11 | Agent 最大自主 | ✅ | Agent 在 P0/P1 內自主使用 Binance market data；trading 仍走 Bybit |
| 13 | cost 感知 | ✅ | Binance WS 接入估 10-15 hr 在 v5.7 §8 Sprint 1A 預算內 |
| 14 | 零外部成本 | ✅ | Binance market data WS 免費；Revolut + Wise 是個人 banking 不涉及付費服務 |
| 16 | Portfolio > 孤立 trade | ✅ | D12 cap = portfolio-level diversification；Binance market data 提供 cross-venue analytics 對齊 portfolio thinking |

## Cross-References

- **ADR-0006**：`docs/adr/0006-bybit-only-exchange.md`（本 ADR amendment 對象；不取代，並存）
- **v5.7 §1 honest Y1 income**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:30-103`（Off-exchange savings $80-100 與 D12 20% off-exchange 兼容）
- **v5.7 §6 market.liquidations writer existing**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:208-229`（Bybit baseline 不變；Binance liquidations 用獨立 namespace）
- **v5.7 §8 Sprint 1A Binance market-data WS NEW**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:278`（本 ADR Decision 1 對應 ADR 級授權）
- **v5.7 §11 Reviewer Conditions**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:341-355`
- **v5.7 §12 ADR-0006 amendment 提案**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:364`（本 ADR 為該提案落地）
- **ADR-0030**：本批次 Copy Trading evidence-gated（DEX/Hyperliquid not approved 不影響 Bybit-only Copy Trading）
- **ADR-0031**：本批次 Framework expansion — on-chain read-only logging 例外（per §Decision 3）
- **ADR-0032**：本批次 Earn asset movement Guardian（D12 cap 與 §Gate 2 Risk envelope 互補）
- **`docs/references/2026-04-04--bybit_api_reference.md`**：Bybit-only baseline 保持
- **Bybit ToS**：BB 持續監測
- **Binance ToS**：Sprint 1A 接入時 Operator + BB confirm

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via v5.7 §12 governance recap | 2026-05-21 | 🟡 PROPOSED-pending-commit |
| TW | 本文件起草（v5.7 §12 ADR-0006 amendment 提案落地為 ADR-0033 draft） | 2026-05-21 | ✅ Drafted |
| BB | Bybit + Binance ToS / KYC cross-venue review | TBD（Sprint 1A） | 🟡 PENDING |
| E1 | Binance market-data WS 接入 owner（Sprint 1A） | TBD（Sprint 1A） | 🟡 PENDING |
| FA | D12 cap calculation logic + Guardian breach trigger review | TBD（Sprint 1A） | 🟡 PENDING |
| QC | Y1 Binance market data → counterfactual analysis evidence pipeline review | TBD（Sprint 5-9） | 🟡 PENDING |
| PM | Sprint 10 W36-39 Binance trading enable Y2 evaluation 仲裁 | TBD（Sprint 10 W38） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0033 — ADR-0006 Amendment: Binance Market Data Approved · Binance Trading Defer Y2 · DEX/Hyperliquid NOT Approved · D12 + ToS Posture (Proposed, amendment standalone — original ADR-0006 historical reference: `docs/adr/0006-bybit-only-exchange.md` 2026-04-03 accepted, thesis unchanged)*
