# AMD-2026-05-25-02 — v5.5 Bot Positioning + Capital Structure Formalization

Date: 2026-05-25
Status: **Active** (Operator APPROVE 2026-05-27 — Workflow E cascade executing)
Operator Sign-off: 2026-05-25 directive — 確認 v5.5 §0 changelog 兩條轉變（Bot 定位反轉 + 副帳 1.5k→0）為 AMD-level governance；2026-05-27 final APPROVE + Workflow E cascade authorized
PM Sign-off: 2026-05-27 — cascade dispatch via PA Workflow E

Supersedes:
- `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.4.md` §2 Capital Structure (主帳 $8.5k + 副帳 Master Trader $1.5k)
- `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.4.md` §3 Strategy Portfolio (主帳+副帳 dual product framing)
- `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.4.md` §10 Master Trader Tier Ladder (Cadet/Bronze/Silver/Gold immediate Sprint 1 setup)
- `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.5.md` §0 changelog（informal record；本 AMD 升 AMD-level governance）

Related:
- ADR-0030 Copy Trading Y1末 4-gate evidence (本 AMD 對齊 Y2+ enable timing)
- ADR-0006 Bybit-only exchange + ADR-0033 Binance amendment (主帳 venue scope)
- AMD-2026-05-25-01 Commercialization Boundary (本 AMD 是商業化邊界的 Bot 定位前置)

---

## 1. Status

**Active** (Operator APPROVE 2026-05-27)

本 AMD 為 v5.5 execution-plan §0 changelog 兩條核心轉變的 AMD-level 正式化。當時（2026-05-21）v5.5 在 14 rounds reviewer audit cumulative drive 下完成 reframe，但**未立 AMD**（因 v5.x execution-plan 改太快、未進入 AMD 化階段）。Operator 2026-05-25 在 V1→V5.8 drift audit 過程中確認此兩條轉變應 AMD 化以解 governance gap，2026-05-27 final APPROVE + Workflow E cascade authorized。

### Approval Log

| Date | Event | Authority |
|---|---|---|
| 2026-05-25 | Draft + operator directive 確認兩條轉變 | Operator |
| 2026-05-27 | Final APPROVE + cascade dispatch via PA Workflow E | Operator |

---

## 2. Context

### 2.1 v5.4 → v5.5 兩條核心轉變（informal in v5.5 §0）

| Dimension | v5.4 (Superseded) | v5.5 onwards (Active) |
|---|---|---|
| Bot 定位 | Strategy Lab + Copy Trading Engine **雙產品** | **完整 quant bot 單一產品**，Copy Trading 是後續可選 monetization channel |
| 主帳 ambition | 部分 strategies (受 Copy Trading copy-able 限制) | **All strategies including those Copy Trading 無法 copy**（spot+perp delta-neutral / options multi-leg）|
| Copy Trading 時點 | Sprint 1 開副帳 (Cadet → Bronze → Silver → Gold tier ladder) | **Y2+ moat 完備 + ADR-0030 4-gate evidence 全 PASS 後 enable** |
| Y1 capital structure | 主帳 $8.5k + 副帳 Master Trader $1.5k | **100% 主帳 $7,500 active** + Off-exchange $2,500 |
| 工程 focus Y1 | 主帳 + 副帳並行 | **全力主帳 alpha + autonomy + learning** |
| Reverse-snipe moat | 部分提及 (作為 Copy Trading 防禦) | **獨立 moat construction track**（Sprint 8+ design, Y2 build before Copy enable）|

### 2.2 為什麼需要這個 AMD（Operator 2026-05-25 confirm）

主會話在 V1→V5.8 drift audit 中發現：
- v5.5 §0 changelog 是 informal record（execution-plan-level 自我聲明）
- AMD list 內 2026-05-21 → 2026-05-22 chain (AMD-2026-05-21-01 v1 → v2) 全聚焦 autonomy + fail-safe；無 AMD 對 Bot 定位 / 副帳 retire 顯式 land
- Operator 2026-05-25 確認此兩條轉變 rationale 與我推測一致：
  - **主帳完整 quant 能力 > Copy Trading 限制**（spot+perp delta-neutral / options multi-leg 無法 copy）
  - **Y1 全力主帳 + 副帳 Y2+ moat 完備後啟動**
- 必須 AMD 化以免未來 sub-agent dispatch 時 reviewer 不知道哪個是當前 baseline（v5.4 雙產品 vs v5.5 單一產品）

### 2.3 v5.5/v5.6/v5.7/v5.8 已對齊（無新 engineering work）

| Doc | 對齊狀態 |
|---|---|
| v5.5 §0 changelog | 自我記錄兩條轉變 |
| v5.6 §0 changelog + §3 Stream | 5 candidates portfolio 主帳；副帳 $0 Y1 |
| v5.7 §1 Honest Y1 Income | Y1 expected ~$421 100% 主帳；無副帳 income line |
| v5.8 §1 13 modules + §3 Sprint 1A | 全聚焦主帳 module；無副帳 Cadet/Bronze tier ladder spec |
| ADR-0030 Copy Trading evidence-gated | Y1末 4-gate evaluation；Y2 enable conditional |

本 AMD 只是 formalize, 不引入新 engineering。

---

## 3. Decision 1 — Bot Positioning 「完整 quant bot 單一產品」

### 3.1 核心 thesis

OpenClaw / 玄衡 · Arcane Equilibrium 是**單一產品的完整 quant bot**：
- 主帳承載**全部 strategies**（含 spot+perp delta-neutral 如 C10 funding harvest / options multi-leg 如 C13 VRP defined-risk / 其他 strategy 池）
- 主帳能力**不受 Bybit Copy Trading 可 copy 子集限制**
- Copy Trading 是**後續可選 monetization channel**，不是 product positioning

### 3.2 Strategy Copy-Tradeability Matrix (per v5.5)

| Strategy | Copy-tradeable | 限制原因 |
|---|---|---|
| C10 funding harvest | ❌ | spot leg + perp leg 不在同 Copy Trading scope |
| C13 options VRP defined-risk | ❌ | Bybit Copy 不支援 options multi-leg |
| Pairs trading | ⚠️ | 兩腿風險，partial copyable |
| Unlock SHORT | ✅ | perp short directional |
| Funding short-only | ✅ | perp short directional |

主帳策略池 ⊃ Copy 可 copy 子集 → Copy Trading 永遠是主帳的 subset，不能取代 single product framing。

### 3.3 對 v5.4 dual product framing 的 supersede

v5.4 §3 寫「Strategy Lab + Copy Trading Engine 雙產品」整段 retire。理由：dual product framing 隱含 Copy Trading 是平行 product line，但實際上 Copy Trading 是主帳的 monetization channel，非平行 product。

---

## 4. Decision 2 — Y1 Capital Structure 100% 主帳

### 4.1 Capital allocation

| Account | Y1 (本 AMD) | Y2+ Conditional |
|---|---|---|
| 主帳 (active trading) | **$7,500** | Continue + 加 capital scaling per ADR-0040 multi-venue gate |
| Off-exchange (Revolut + Wise) | $2,500 (3-4% APR ≈ $80-100/yr) | Maintain |
| 副帳 Master Trader Copy | **$0 Y1**（不開副帳）| Y2 enable conditional on ADR-0030 4-gate PASS |
| **Total** | **$10,000** | $10,000 + 後續 scaling |

### 4.2 副帳 Y2+ Conditional Enable

副帳開啟的硬條件（per ADR-0030 4-gate evidence + 本 AMD §4.2）：
1. **ADR-0030 Gate 1 Alpha**：≥1 strategy 90+d live, Sharpe ≥ 0.8, MaxDD ≤ 15%, hit_rate ≥ 50%, PnL ≥ $300
2. **ADR-0030 Gate 2 Governance**：Lease pass率 ≥ 95% / Guardian block ≤ 5/mo / Operator override ≤ 3/mo
3. **ADR-0030 Gate 3 Infrastructure**：Uptime ≥ 99% / WS reconnect ≤ 10/wk / Migration audit PASS / 0 P0 incident
4. **ADR-0030 Gate 4 Regulatory**：Bybit Copy ToS / KYC / jurisdiction / AML
5. **本 AMD 補充 Gate 5 Moat**：reverse-snipe defense IMPL + simulator fill rate > 95% + anti-snipe deployed + Master Trader API + ranking dashboard

5 gate 全 PASS 才考慮副帳 enable；任一 FAIL → 維持 Y1 100% 主帳格局，副帳 enable 推遲。

### 4.3 對 v5.4 副帳 $1.5k Sprint 1 setup 的 supersede

v5.4 §2 「主帳 $8.5k + 副帳 $1.5k」整段 retire。v5.4 §10 「Master Trader Cadet/Bronze/Silver/Gold tier ladder immediate Sprint 1 setup」**完整 cancel** — Cadet (100 USDT, profit share 10%) / Bronze (200 USDT + 50 USDT 7d) / Silver (1,000 USDT) / Gold (10,000 USDT) tier 全部 defer to Y2+ Conditional Enable phase。

---

## 5. Decision 3 — Engineering Implication (Zero New Work)

本 AMD 為 governance formalize，**不引入新 engineering work**：
- v5.5/v5.6/v5.7/v5.8 已對齊（per §2.3 表）
- Sprint 1A-10 dispatch packet 已不含副帳 task
- ADR-0030 已是 Y1末 4-gate evidence-gated

Cascade patch 範圍：
- `docs/README.md` AMD list 加本條目
- `docs/governance_dev/SPECIFICATION_REGISTER.md` Active AMD count +1
- `docs/CCAgentWorkSpace/PM/workspace/reports/` 產 PM sign-off report

---

## 6. Alternatives Considered

| Alternative | 棄因 |
|---|---|
| 不立 AMD，保留 v5.5 §0 informal record | governance gap；future sub-agent dispatch 可能誤反 implicit |
| 立 ADR 而非 AMD | strategy product positioning + capital structure 是 strategy-level directive，非 architecture decision；AMD 是正確 governance level |
| 改 CLAUDE.md baseline 寫「single product positioning」原則 | over-engineering；CLAUDE.md baseline 不動原則（per AMD-2026-05-21-01 v2 §6.3 Q1 amendment 並存路徑）|
| 拆 2 AMD（Bot 定位 + capital structure 分開）| 兩條轉變 logically coupled（capital structure 是 Bot 定位的 financial consequence）；單一 AMD 對齊 |

---

## 7. Consequences

### 7.1 Positive

- **Governance gap 補完**：v5.5/v5.6/v5.7/v5.8 dispatch-of-record 對齊 AMD-level
- **Sub-agent dispatch reviewer 明確 baseline**：未來不再有 v5.4 dual-product vs v5.5 single-product confusion
- **AMD-25-01 (commercialization 邊界) 對齊**：single product = exchange-native commercialization only 邏輯統一
- **副帳 Y2+ 4-gate 鎖死**：防範未來 operator 衝動開副帳繞 evidence gate

### 7.2 Negative / Risk

- **失去 v5.4 副帳 monetization Y1 income line**：v5.4 §10 預估 Y1 Copy income $200-800；現 Y1 = $0 副帳 income；mitigation = operator 2026-05-21 已接受 v5.5 informal record，本 AMD 只是 formalize
- **副帳 enable 推遲增加 Y2 Master Trader tier 爬升難度**：v5.4 計劃 Y1 末 達 Bronze；v5.5 Y2 才 start = Master Trader tier 整體推遲 ~1 year；mitigation = ADR-0030 4-gate evidence 嚴格性是 trade-off 必然

### 7.3 與既存設計協作

| 既存元素 | 與本 AMD 關係 |
|---|---|
| ADR-0030 Copy Trading evidence-gated | **核心對齊**；4-gate 為副帳 Y2+ enable 條件 |
| ADR-0006 + ADR-0033 venue scope | **主帳 venue 對齊**；Bybit primary Y1 + Binance market data only Y1 + Binance trade enable Y3+ |
| AMD-2026-05-25-01 Commercialization | **paired**；single product = exchange-native commercialization only |
| ADR-0040 Multi-Venue Gate | 主帳 venue gate spec；副帳 venue 待 Y2+ amendment |
| v5.8 13 modules + Sprint 1A-10 | 已對齊；無新 engineering |

---

## 8. Sign-off

| Role | Status | Date | Note |
|---|---|---|---|
| Operator | **APPROVE** | 2026-05-27 | Final approval + Workflow E cascade authorized（先 2026-05-25 directive given）|
| PM | **SIGN-OFF** | 2026-05-27 | Cascade dispatch via PA Workflow E |
| PA | **CASCADE EXECUTED** | 2026-05-27 | Workflow E：docs/README + SPECIFICATION_REGISTER + AMD-25-01 cross-ref + TODO cleanup |
| CC | DEFERRED | — | 16 root principles compliance（formalize only, no engineering work; §5/§11 compliance verified by v5.5 chain）|
| R4 | DEFERRED | — | docs/README + SPECIFICATION_REGISTER cascade executed by PA Workflow E |

---

## 9. Cascade Patch Checklist

待 operator confirm 後執行：

1. `docs/README.md`：AMD list 加本條目
2. `docs/governance_dev/SPECIFICATION_REGISTER.md`：Active AMD count +1
3. `docs/CCAgentWorkSpace/PM/workspace/reports/`：產 PM sign-off report
4. 不動：CLAUDE.md baseline（per amendment 並存路徑）
5. 不動：v5.5/v5.6/v5.7/v5.8 文本（已對齊）

---

**END AMD-2026-05-25-02**

Author: 主會話 PM (per operator 2026-05-25 confirmation during V1→V5.8 drift audit)
Co-Authored-By: Claude Opus 4.7 (1M context)
