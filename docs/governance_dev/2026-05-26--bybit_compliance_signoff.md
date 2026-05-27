# Bybit Compliance Sign-off — Sprint 4 first Live + Earn Wave C readiness

**Date**: 2026-05-26
**Trigger**: P0-OPS-3 BB audit 5 operator-must-confirm (C-1~C-5) sequential closure
**Operator**: cloud@ncyu.me（per CONTEXT.md）
**Scope**: Sprint 4 first Live W18-21 (~2026-09) $500 + Earn Wave C first stake $100-200 Flexible-only
**Audit baseline**: `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-26--p0-ops-3-bybit-tos-geo-kyc-audit.md`

---

## Verdict 概要

| Confirm | 結果 | 對 Sprint 4 | 對 Earn Wave C |
|---|---|---|---|
| C-1 residence | ✅ Spain（EU member, MiCA-compliant, NOT in 16 restricted） | unblock | unblock |
| C-2 KYC tier | ✅ ≥ Advanced L2（Gov ID + face + utility bill；2M USDT/day withdraw）| unblock | unblock |
| C-3 API key state | ⚠️ 2 demo keys + 33d TTL（需 OP-1 a-f mainnet reissue 才能上 mainnet）| pending OP-1 | pending OP-1 |
| C-4 tax filing | ⚠️ Defer to first Live + 30d（~2026-10）| non-blocker | non-blocker（V100 audit trail mandatory）|
| C-5 Earn risk | ✅ 接受；first stake $100-200 **USDT Flexible only**（stablecoin 免幣價跌；Bybit 平台風險自承）| n/a | unblock |

**5/5 ship-stop axis cleared**：3 unblock + 2 conditional non-blocker。
**Pending**：OP-1 a-f mainnet key reissue（unblocks Sprint 4 + Earn 雙線）。

---

## C-1 Residence — ✅ Spain

- **Operator self-declared**: Spain（西班牙）
- **Bybit 16 restricted jurisdictions check**：Spain 不在以下名單：
  US / Mainland China / Hong Kong (2025+) / Singapore / Canada / France / Japan (2026 phase-out) / North Korea / Cuba / Iran / Syria / Sudan / Uzbekistan / Crimea / Donetsk+Luhansk / Sevastopol + Dubai (retail derivatives) + UK (derivatives only)
- **EU regulatory frame**：
  - MiCA（Markets in Crypto-Assets）2024+ applies — Bybit EU operations compliant
  - DAC8 automatic tax reporting 2026-01-01 生效 — Bybit reports to Spanish AEAT at threshold
- **No further verification required**

---

## C-2 KYC Tier — ✅ ≥ Advanced L2

- **Operator self-declared**: ≥ Advanced L2（Gov ID + face + utility bill）
- **Bybit KYC 三階對照**：
  - Standard L1 = Gov ID + face = 1M USDT/day withdraw（最低要求）
  - **Advanced L2 = + utility bill = 2M USDT/day** ← operator tier
  - Pro L3 = enhanced DD = 30-60M USDT/day
- **Sprint 4 $500 + Earn $100-200 capacity check**：L1 即足，L2 留 future scaling capacity
- **No further verification required**

---

## C-3 API Key State — ⚠️ Conditional (OP-1 pending)

- **Operator-reported state**: 2 demo API keys + ~33 days TTL remaining
- **Implication**:
  - LiveDemo phase（當前）：充分 — 不阻
  - Sprint 4 first Live W18-21（mainnet）：**需 OP-1 a-f mainnet key reissue**（Bybit Web UI 創新 key + Read+Trade+Earn scope + no IP restriction per `P1-OP1-IP-WHITELIST-CORRECTION` operator-decided 2026-05-25 (b)）
  - Earn Wave C first stake（per BB audit Bybit demo 無 spot lending）：同上必 mainnet
- **Earn scope auto-include check**：Bybit policy 2026-04-09 起新 key 自動含 Earn product scope；operator 確認 issuance date ≥ 2026-04-09 即可直跳 OP-1 d-f；< 2026-04-09 需 a-c reissue
- **Pending action**: OP-1 a-f 5-10 min hand action（per TODO §7 D+2-D+3 schedule）

---

## C-4 Tax Filing — ⚠️ Deferred to first Live + 30d

- **Operator decision**: Defer Spanish tax planning to first Live W18-21 + 30d window (~2026-10)
- **Rationale**: $500 scale 遠低於大多數 reporting threshold；first Live empirical data 出現後再做正式規劃
- **Persistent obligations**（即使 defer）：
  - Spanish IRPF capital gains 19-26%（self-report）
  - Modelo 100 (annual), Modelo 721 (crypto-specific 2024+)
  - Modelo 720 if >€50k abroad
  - EU DAC8 自動 reporting 2026-01-01+ at Bybit-side threshold
- **Mandatory regardless of defer**：
  - `learning.earn_movement_log` (V100) 為 Earn 唯一 audit trail（Bybit Account Statement excludes Earn / structured products）
  - Bybit Transaction Log + Order History CSV export 保留為 audit evidence
- **30d 提醒**：BB 在 first Live W18-21 + 30d 觸發 tax planning reminder

---

## C-5 Earn Risk Acceptance — ✅ USDT Flexible Only

- **Operator decision**: 接受 Earn Flexible 兩類風險；first stake **$100-200 USDT Flexible only**
- **Risk acknowledged**：
  1. **APR floating**：Bybit 隨時調整，可降至 0；本金大致不受影響
  2. **平台 default risk = total loss**：Bybit 倒（駭客 / 破產 / 跑路 / 監管關門）→ 本金可能歸零；無 FDIC/SIPC 類保險；歷史案例 Mt. Gox 2014 / FTX 2022 / Celsius 2022
- **USDT-only 風險降低**：免幣價跌風險面（BTC/ETH 不選）；僅承 Bybit 平台風險
- **Loss budget**: 最壞 $100-200 整存歸零；當作 Earn 流程學費
- **Acceptance scope**: OP-3 first stake $100-200 USDT Flexible；future Bybit Earn 增量（BTC/ETH/structured products）需 separate sign-off

---

## Pending Operator Actions（per C-1~C-5 closure）

| # | Action | Trigger | ETA |
|---|---|---|---|
| 1 | OP-1 a-f Bybit Web UI mainnet key reissue (Read+Trade+Earn, no IP restriction) | D+2-D+3 per TODO §7 | 5-10 min hand |
| 2 | OP-1-d Stage 0R Earn variant 仲裁（8 OQ per TODO §7） | post OP-1 a-c | 30-60 min hand |
| 3 | OP-3 first stake $100-200 USDT Flexible via tab-earn | post OP-2 | 5 min hand |
| 4 | Spanish tax planning（IRPF/Modelo）規劃 | first Live W18-21 + 30d (~2026-10) | self-planning |

---

## Sign-off

| Role | State | Date | Comment |
|---|---|---|---|
| Operator | ✅ APPROVED | 2026-05-26 | C-1~C-5 sequential confirmation |
| BB | ✅ APPROVED | 2026-05-26 | per `2026-05-26--p0-ops-3-bybit-tos-geo-kyc-audit.md` audit + C-1~C-5 closure |
| CC | PENDING | – | Sprint 4 first Live W18-21 pre-flight gate verify |
| QA | PENDING | – | Earn Wave C first stake E2E + Sprint 4 gradient 7d 0 CRITICAL verify |
| PM | PENDING | – | Sprint 4 first Live W18-21 ratify gate |

---

**Status**: ACTIVE — 阻塞 axis 5/5 cleared；OP-1 mainnet key reissue 待 D+2-D+3 operator hand action。
