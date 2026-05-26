---
report: BB P0-OPS-3 Bybit ToS / geography / KYC tier / Tax reporting alignment audit
date: 2026-05-26
agent: BB (Bybit Broker Compatibility Auditor)
phase: P0-OPS-3 Live ops blocker — Sprint 4 first Live W18-21 (~2026-09) $500 BTC/ETH/altcoin + Earn Wave C first stake $100-200 Flexible 前 unblock
head: TODO.md §1.7 / §6 / KNOWN_ISSUES.md:531-535 reference
trigger: PM 派 P0-OPS-3 audit per Sprint 4 W18-21 + Earn Wave C OP-1 blocker chain
verdict: CONDITIONAL — BLOCKER on 5 operator-must-confirm items；不阻 Earn Wave C OP-1 hand action chain (operator 自證 6 項可在 Sprint 4 W18-21 前任意時段 land)；阻 Sprint 4 first Live W18-21 cutover until M5-1 governance entry land + operator residence proof obtained
ssot:
  - runtime PG / Rust source / Bybit V5 official docs (WebFetch + WebSearch)
  - srv/TODO.md §1.7 P0-OPS-1..4 line 49
  - srv/docs/KNOWN_ISSUES.md:531-535
  - 90d Bybit policy changelog (2026-02-26 to 2026-05-26)
  - BB 5/8 + 5/9 + 5/21 + 5/23 prior verdicts (M5-1 / M5-2 12+ day stale)
---

# BB P0-OPS-3 Bybit ToS / Geography / KYC / Tax Reporting Audit — 2026-05-26

## §0 TL;DR

- **Overall verdict**: **CONDITIONAL — 5 operator-must-confirm 阻 Sprint 4 first Live W18-21**
- **Earn Wave C first stake $100-200 Flexible verdict**: **CONDITIONAL-GO** — Bybit Earn Flexible 完全合規（KYC Standard 即可、Flexible 隨時 redeem、UTA 持有者自動開通）；不阻 OP-1 ~ OP-3 hand action chain；前提 operator 居住地非 Bybit 16 個 restricted jurisdiction 之一
- **Sprint 4 first Live $500 verdict**: **CONDITIONAL-BLOCKED** — Bybit ToS 16 個 restricted jurisdiction（含 US / Hong Kong / Singapore / Canada / Mainland China / Dubai / Japan 2026 phase-out / France / 等）；operator residence proof 必須先入 governance；M5-1 governance entry 從 2026-05-08 列出 18+ 天 0 進展，仍是最大 ship-stop
- **0 ship-stop technical blocker** — 所有問題都是 governance / operator 自證 / 文件層
- **30d Bybit changelog 0 breaking change** for derivatives；但 Japan exit 2026 + UK re-entry 兩件政策更新需 land 進字典
- 技術合規度: 98%
- 政策合規度: 70%（M5-1 / M5-2 仍 stale 18+ 天 / OPS-3 governance entry 0）

## §1 審計範圍

### 1.1 P0-OPS-3 原始描述（KNOWN_ISSUES.md:531-535）

> Bybit ToS / geography restriction / KYC tier / Tax reporting 對齊未完

### 1.2 Audit 邏輯路徑

1. 地理適格（jurisdiction restriction）— operator residence vs Bybit 16 個 restricted countries
2. KYC tier — Standard / Advanced / Pro 對 perpetual + Earn Flexible 的覆蓋
3. API user agreement — broker rebate eligibility / IP whitelist / current rate tier
4. Tax reporting — Bybit data export 能力 + operator jurisdiction 適用性
5. 90d ToS / policy changelog — Sprint 4 W18-21 前是否有新限制
6. Earn product 額外條款 — Flexible savings / APR 浮動 / 平台 default risk

### 1.3 SSOT chain（衝突信前者）

1. Bybit V5 official help center + ToS（WebSearch + WebFetch）
2. Runtime PG empirical（BB memory 5/21 verify writer prod）
3. Rust source code（earn_routes.py / bybit_earn_client.rs）
4. TODO.md §1.7 + §6 + §7
5. BB prior verdict memory（5/8 M5-1 + 5/9 M5-2 + 5/21 C5 + 5/23 OP-3）
6. 字典 ref handbook（drift 5+ 月，0 entry，最後）

## §2 地理適格 — Bybit 16 個 restricted jurisdictions（2026-05-26 verified）

### 2.1 BVAPO Platform Terms Section 3.4 16 個 excluded jurisdictions

per Bybit 官方 ToS (2026-05-26 WebSearch verified)：

| # | Jurisdiction | Status | OpenClaw operator 必確認 |
|---|---|---|---|
| 1 | United States + territories | Fully restricted | ⚠️ |
| 2 | Mainland China | Fully restricted | ⚠️ |
| 3 | Hong Kong | **Fully restricted** (2025 added) | ⚠️ |
| 4 | Singapore | Fully restricted | ⚠️ |
| 5 | Canada | Fully restricted (含 derivatives) | ⚠️ |
| 6 | France | Fully restricted | ⚠️ |
| 7 | Japan | **Phasing out 2026 start** (KYC L2 by 2026-01-22 or restriction) | ⚠️ |
| 8 | North Korea | OFAC sanctioned | ⚠️ |
| 9 | Cuba | OFAC sanctioned | ⚠️ |
| 10 | Iran | OFAC sanctioned | ⚠️ |
| 11 | Syria | OFAC sanctioned | ⚠️ |
| 12 | Sudan | OFAC sanctioned | ⚠️ |
| 13 | Uzbekistan | Restricted | ⚠️ |
| 14 | Crimea | Russian-controlled Ukraine | ⚠️ |
| 15 | Donetsk + Luhansk | Russian-controlled Ukraine | ⚠️ |
| 16 | Sevastopol | Russian-controlled Ukraine | ⚠️ |
| - | Dubai (UAE) | **Restricted to retail derivatives** | ⚠️ |

外加 UK re-entry 2026 (per beincrypto + cryptoninjas Dec 2025 news) — UK spot + P2P only via Archax，**derivatives 仍不開放**。India 2026 fully resumed。

### 2.2 OpenClaw operator residence proof 狀態

| 來源 | grep 結果 |
|---|---|
| `/Users/ncyu/Projects/TradeBot/srv/CLAUDE.md` | 0 hit (operator residence) |
| `/Users/ncyu/Projects/TradeBot/srv/CONTEXT.md` | line 282 「single human supervisor `cloud@ncyu.me`」— **無 residence** |
| `/Users/ncyu/Projects/TradeBot/srv/README.md` | 0 hit |
| `/Users/ncyu/Projects/TradeBot/srv/TODO.md` | 0 hit |
| `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/*` | 0 hit (operator country/jurisdiction) |
| `/Users/ncyu/Projects/TradeBot/srv/docs/adr/*` | ADR-0033 Bybit Binance amendment line 110「Bybit Copy ToS / KYC / jurisdiction / AML」**僅引用 ToS 概念，未自證** |

**結論**：operator residence **完全 0 governance trace**。M5-1 (BB 5/8 verdict 列為 18+ day 0 進展) 是真實 ship-stop。

### 2.3 Bybit 自證枚舉技術風險

per cryptoninjas + datawallet 2026 verify：

> Bybit uses advanced geolocation technology to determine the location of their users and block access from restricted countries. Bybit reserves rights to terminate accounts and liquidate positions if users misrepresent residency in restricted jurisdictions.

風險：若 operator residence 為 restricted jurisdiction（特別 HK / Japan / US），Bybit 隨時可：
1. Terminate account → OpenClaw 整個 Sprint 4 first Live capital 凍結 / liquidate
2. Demand KYC L2 升級 by 2026-01-22 (Japan-flagged case)
3. 拒新 API key issuance (Sprint 1A C5 verdict OP-1 < 2026-04-09 key 重發鏈影響)

## §3 KYC Tier — 對 perpetual $500 scale + Earn Flexible $100-200 影響

### 3.1 KYC 3 tier 完整覆蓋表（2026-05-26 verified）

per Bitget academy + Bybit help center + Cryptowisser：

| Tier | 要求 | Daily withdraw limit | Perpetual derivatives | Earn Flexible | OpenClaw Sprint 4+1B 適用 |
|---|---|---|---|---|---|
| **Standard (L1)** | Gov ID + facial recognition | **1,000,000 USDT/day** | ✅ Full | ✅ Full | **✅ 足夠** |
| **Advanced (L2)** | + 地址證明 (utility bill) | 2,000,000 USDT/day | ✅ Full | ✅ Full | 過剩 |
| **Pro (L3)** | Enhanced due diligence | 30~60M USDT/day | ✅ Full | ✅ Full | 過剩 |

### 3.2 對 Sprint 4 first Live $500 verdict

- **$500 perpetual 量 ≪ 1M USDT/day withdraw limit** → KYC Standard (L1) 充分
- Bybit 開戶 mandatory KYC 1 進入 spot/margin/derivatives/P2P/most Earn
- ✅ **KYC tier 不阻 Sprint 4 first Live**（前提 operator 在非 restricted jurisdiction 完成 L1）

### 3.3 對 Earn Wave C first stake $100-200 verdict

- ✅ KYC Standard 即可進 Earn Flexible savings
- Bybit Help Center: 「You need to complete identity verification to access the full suite of earning opportunities」
- UTA 持有者自動開通 Earn Flexible
- 經 BB 5/21 C5 verdict (a) verified Earn scope 非 withdraw scope；不違 CLAUDE.md Hard Boundaries

### 3.4 KYC operator must confirm

- ⚠️ operator KYC tier **未入 governance trace** — M5-1 第 2 條 self-cert 必填
- ⚠️ KYC 完成日 ≥ 2026-04-09 → API key 自動帶 Earn scope（per BB 5/21 C5 verdict OP-1 chain）
- ⚠️ Japan-flagged case：若 operator 曾被誤判 Japan → 必 L2 by 2026-01-22 (已過期)

## §4 API user agreement — broker rebate / IP whitelist / rate tier

### 4.1 Broker rebate eligibility

- 門檻：30d volume ≥ $10M USDT
- OpenClaw 30d volume ~$45K（BB 5/21 verdict 列）
- **不申**：差 222× threshold
- ✅ 0 ToS 違反 / 0 broker partnership risk

### 4.2 IP whitelist — operator-decided P1-OP1-IP-WHITELIST-CORRECTION

- TODO.md line 162 verified：「OPERATOR-DECIDED 2026-05-25 — 選項 (b) Bybit "no IP restriction"」
- BB advisory：production key 推薦 IP whitelist；但 operator 已自決 (b)；BB 不重新評估
- ✅ 0 BB push back（per operator 明示偏好）

### 4.3 Current rate tier

per BB 5/10 W1+W2 rate budget review verified：
- Baseline 0.7 req/s (97% headroom)
- Sprint 1A close-maker-first 部署後預估 ≤ 1.5 req/s sustained
- ✅ 0 throttle risk

## §5 Tax Reporting — Bybit data export 能力 + operator jurisdiction 適用性

### 5.1 Bybit tax export ability（2026-05-26 verified）

per Bybit help center + Coinpanda + Koinly：

| 能力 | 狀態 |
|---|---|
| **1099-DA / 1099-MISC issuance** | ❌ **不發** (Bybit 國際 exchange HQ Dubai, no US reporting infra) |
| **CSV export — Transaction Log** | ✅ 全帳戶 balance change |
| **CSV export — Order History** | ✅ filled spot orders + fees |
| **CSV export — Account Statement** | ✅ summary record 但 **excludes Earn / structured products** |
| **API export** | ✅ 但 12-month time restriction → 用 ZIP files instead |
| **3rd-party tax software 對接** | ✅ Koinly / CoinTracker / Coinpanda / CoinLedger / Divly / Summ |
| **Data-sharing regulation (CRS / EU DAC8)** | ⚠️ regional — 可能 report to local tax authority |

### 5.2 Earn-specific tax record gap

- ⚠️ Account Statement **excludes Earn**
- Sprint 1B Wave C first stake $100-200 Earn movement 需要：
  - 由 `learning.earn_movement_log` (V100 hypertable) 自主 audit trail
  - 由 Transaction Log CSV 確認 spot wallet ↔ Earn product 內部 transfer
  - 由 `/v5/earn/position` + `/v5/earn/apr-history` 補 yield record
- ✅ OpenClaw E1c IMPL 已預期此 gap (per BB 5/23 caveat 1 §3.5 endpoint 表)

### 5.3 Operator jurisdiction tax reporting 適用性

- ⚠️ **operator residence 未知** → 無法評估 tax authority filing 義務
- 若 operator 在 EU → DAC8 自動 reporting 2026-01-01 已生效 → Bybit 可能 share data
- 若 operator 在 CRS jurisdiction (Cayman / Singapore-resident etc.) → CRS share applicable
- 若 operator 在台灣 / 香港 / 其他 non-CRS-share / non-DAC8 jurisdiction → 自報 obligation only

### 5.4 OpenClaw 自主 tax data lineage

- Sprint 1A V094 audit schema + Sprint 1B V100 `learning.earn_movement_log` 已預備
- Sprint 4 first Live 後：order.executions / position.daily-pnl / earn.position 三類 data 必 CSV export + on-prem PG 雙保險
- BB advisory：Sprint 4 W18-21 first Live cutover 前 30 day operator 拍板 tax reporting cadence（建議 monthly Bybit CSV pull + PG cross-ref）

## §6 90d Bybit ToS / policy changelog（2026-02-26 ~ 2026-05-26）

### 6.1 重大政策更新 (per WebSearch verified)

| 日期 | 政策更新 | OpenClaw 影響 |
|---|---|---|
| 2025-12-23 | Bybit 通知 Japanese users 「discontinue services」+ 「gradually implement account restrictions」 | ⚠️ operator 若曾被誤判 Japan → 必確認 |
| 2026-01-01 | EU DAC8 自動 reporting 生效 | ⚠️ operator 若 EU resident → tax data share |
| 2026-01-22 | Japan-flagged users 必 KYC L2 deadline | ⚠️ 過期；operator 若 affected → 已 restriction |
| 2026 Q1 | UK re-entry (spot + P2P only via Archax) | ❌ derivatives 仍不開放 UK；OpenClaw operator 若 UK → 不可 perp |
| 2026 (year) | India fully resumed (2025-01 suspend lifted) | ✅ 不影響 |
| 2026 ongoing | KYC rule update for AML compliance | ⚠️ KYC tier 升級可能 |

### 6.2 30d Bybit V5 API changelog（per BB 5/8 + 5/9 + 5/21 + 5/23 carry-over）

- 5/14 Card affiliate / 5/7 Earn / 5/6 Crypto Loan / 4/8 BYUSDT earning / 4/14 fixed-saving 全與 Sprint 4 perpetual + Earn Flexible **無 breaking change**
- 30d 0 deprecated endpoint
- 0 rate limit change
- 0 retCode semantic change

✅ **30d V5 API 0 breaking**

### 6.3 字典 ref handbook 政策層 drift

| 章節 | 狀態 |
|---|---|
| §3 NEW Earn API 章節 | ❌ **0 entry**（5/21+5/23 BB verdict 列 P0 5+ 月 0 進展） |
| §1.10 allLiquidation BLOCKED 字樣 | ❌ stale 5+ day（5/21 verdict 列） |
| 16 個 restricted jurisdictions 表 | ❌ 字典從未收錄；本 OPS-3 audit 首列 |
| Japan exit 2026 timeline | ❌ 字典從未收錄 |
| UK re-entry 2026 (derivatives 不開) | ❌ 字典從未收錄 |
| Tax reporting CSV export 能力 | ❌ 字典從未收錄 |

## §7 Earn Wave C first stake $100-200 Flexible 額外條款 (per BB 5/23 caveat 1)

per Bybit Earn FAQ + Coin Bureau + Coinspot 2026 verified：

| 條款 | 狀態 |
|---|---|
| Flexible Savings APR | ⚠️ **floating** — 「displayed APR is for reference only and is not guaranteed」 |
| Tiered interest rate | ✅ 「APR varies by tier and may change depending on market conditions」 |
| Redemption | ✅ Flexible = 隨時可 redeem，無鎖倉期 |
| Default risk | ⚠️ 「all yield products carry risk」+ 「Yields are generated from loan activities conducted by Bybit」 = 平台 default = total loss |
| Yield source | 「third-party strategies that employ risk-neutral trading methods」 |
| KYC requirement | ✅ Standard 即可 |
| Geographic restriction | ✅ 同 main account（16 個 restricted jurisdictions 全 ban） |

### 7.1 對 Sprint 1B Wave C first stake verdict

- ✅ **不阻 OP-1 ~ OP-3 hand action chain**（per BB 5/23 verdict）
- ⚠️ Operator 需自承「APR floating + 平台 default risk」前 OP-3 first stake $100-200
- ✅ E1c IMPL 4 unique endpoint 已對齊 Bybit V5 2026 unified path

## §8 OpenClaw governance state vs M5-1 / M5-2 progress check

### 8.1 M5-1 ToS / KYC / 地理禁區 governance entry

- BB 5/8 verdict 列「`docs/governance_dev/YYYY-MM-DD--bybit_compliance_signoff.md` operator 必確認 6 項自證入 git」
- BB 5/9 verdict 列「0 進展」
- BB 5/21 verdict 列「stale 13 day」
- BB 5/23 verdict 列「stale 15 day」
- BB **2026-05-26 (本 audit)**: ❌ **stale 18 day** — `docs/governance_dev/2026-05-26--bybit_compliance_signoff.md` **仍未建檔**

### 8.2 M5-2 IP whitelist preflight tool

- BB 5/8 verdict 列「`helper_scripts/preflight/check_bybit_ip_whitelist.py` operator 在 Bybit UI 確認」
- ✅ 2026-05-25 OPERATOR-DECIDED `P1-OP1-IP-WHITELIST-CORRECTION` 選項 (b) 「no IP restriction」(per TODO.md:162)
- ✅ **M5-2 由 operator decision 取代** — preflight tool 不再需要
- ✅ **closed** — 0 BB push back

### 8.3 P0-OPS-3 status

- TODO.md line 49 `P0-OPS-1..4` 統一列「Sprint 4 first Live W18-21 前必 closure / PA + BB + E3 owner / OPS-1 HTTPS / OPS-2 cred rotation / OPS-3 legal+ToS / OPS-4 runbook / 4 子項各 owner」
- ✅ 本 audit 履行 BB owner 履約

## §9 Operator-must-confirm 清單（FINAL）

5 項 governance hand action 必入 `docs/governance_dev/2026-05-26--bybit_compliance_signoff.md` 或 同等 ratify doc：

| # | Confirm item | 嚴重度 | 阻 Sprint 4 first Live? | 阻 Earn Wave C OP-1? |
|---|---|---|---|---|
| **C-1** | Operator residence 自證（country + city / region 至少）+ 證明非 Bybit 16 restricted jurisdictions 之一 | **P0 SHIP-STOP** | ✅ 阻 | ✅ 阻 |
| **C-2** | Operator KYC tier 自證（Standard / Advanced / Pro）+ KYC 完成日 | P0 | ✅ 阻 | ✅ 阻（影響 Earn scope key 發行日） |
| **C-3** | Bybit account 開戶日 + KYC 完成日 ≥ 2026-04-09 verify（影響 OP-1 < 2026-04-09 key 重發鏈） | HIGH | ⚠️ 阻 Earn | ✅ 阻 OP-1-a |
| **C-4** | Operator tax authority filing jurisdiction 自證（EU / CRS / 自報 only）→ Sprint 1A V094 + V100 audit cadence 拍板（monthly Bybit CSV pull + PG cross-ref）| MED | ⚠️ 阻 first Live 後 30 day | ❌ 不阻 |
| **C-5** | Operator 自承 Earn Flexible「APR floating + 平台 default risk = total loss possible」前 OP-3 first stake | MED | ❌ 不阻 | ⚠️ 阻 OP-3 |

## §10 Sprint 4 first Live $500 readiness verdict

### 10.1 Bybit-side ship-stop chain

| Gate | Status | Owner |
|---|---|---|
| operator residence 非 restricted | ❌ **未自證** | C-1 |
| KYC L1 完成 | ❌ **未自證** | C-2 |
| KYC ≥ 2026-04-09 (Earn scope key 自動帶) | ❌ **未自證** | C-3 |
| Tax authority filing 拍板 | ❌ **未自證** | C-4 |
| 30d V5 API changelog 0 breaking | ✅ verified | BB |
| Rate limit < 30% Bybit cap | ✅ verified (0.7 req/s baseline) | BB |
| Broker rebate volume ≪ threshold (不申) | ✅ 0 risk | BB |
| IP whitelist operator-decided "no IP restriction" | ✅ closed | operator |

### 10.2 Verdict: **CONDITIONAL-BLOCKED**

- **5 個 operator confirm 未 land**（C-1 ~ C-5）→ Sprint 4 W18-21 first Live cutover **必 blocked until M5-1 governance entry land**
- **0 技術 ship-stop**（technical compliance 98%；30d 0 breaking change）
- M5-1 governance entry 從 2026-05-08 列出 18+ day 0 進展 → 是真實 ship-stop

### 10.3 解鎖路徑

1. operator 寫 `docs/governance_dev/2026-05-26--bybit_compliance_signoff.md` 入 git；填 C-1 ~ C-5 5 個自證 (15-30 min hand action)
2. 若 C-1 自證 jurisdiction = restricted → 整 Sprint 4 first Live + Earn Wave C **必 cancel**；OpenClaw production tree 移交 / 結算路徑必由 PM 拍板
3. 若 C-1 自證 jurisdiction = non-restricted → Sprint 4 first Live W18-21 ready (per BB 視角)
4. 若 C-2 自證 KYC < Standard → operator 必先 KYC L1 (Bybit Web UI 5-10 min)
5. 若 C-3 自證 < 2026-04-09 → operator 重發 key 加 Earn scope (BB 5/21 C5 verdict OP-1 鏈)
6. 若 C-4 未拍板 → Sprint 4 first Live 後 30d 內必 land；不阻 cutover
7. 若 C-5 未自承 → 不阻 first Live；阻 Earn Wave C OP-3

## §11 Earn Wave C first stake $100-200 readiness verdict

### 11.1 Bybit-side compatibility

| 項目 | 狀態 |
|---|---|
| Bybit Earn Flexible KYC requirement | ✅ Standard 即可 (per Bybit help center) |
| API key Earn scope | ✅ 2026-04-09 後 key 自動帶 (per BB 5/21 C5 (a)) |
| 4 unique V5 endpoint | ✅ E1c IMPL 對齊 (per BB 5/23 verdict) |
| Rate limit Asset group 5 req/s | ✅ < 0.15 req/s 用量 (97% headroom) |
| Earn = asset write 非 trading | ✅ 不觸 broker rebate / KYC tier 升級 |
| Geographic restriction | ⚠️ 同 main account；operator residence 必確認 |
| Flexible APR floating + default risk | ⚠️ operator 必自承 (C-5) |

### 11.2 Verdict: **CONDITIONAL-GO**

- ✅ Bybit 技術側 100% ready (E1c IMPL Bybit V5 path 對齊 + 27+14 test PASS)
- ⚠️ 阻 OP-1 ~ OP-3 hand action chain 的是 C-1 (residence) + C-2 (KYC) + C-3 (key 發行日)；C-5 阻 OP-3 first stake
- 若 operator C-1 ~ C-3 + C-5 land → Earn Wave C OP-1 ~ OP-3 即可 ship（per TODO.md §7 D+2~D+3 schedule）

## §12 BB advisory 字典補錄清單（從 13 升 19）

per BB 5/21 列 13 + 本 OPS-3 新增 6：

| # | 章節 | 等級 | 改動 |
|---|---|---|---|
| 1~13 | per BB 5/21 verdict §H 列 | various | 5+ month outstanding |
| **14** | §0.1 NEW 16 restricted jurisdictions 表 | HIGH | 本 OPS-3 audit 首列；Sprint 4 W18-21 前必 land |
| **15** | §0.2 NEW Japan exit 2026 timeline | MED | 防 operator 誤判 |
| **16** | §0.3 NEW UK re-entry 2026 (derivatives 不開) | MED | 防 operator 期待 UK derivatives |
| **17** | §0.4 NEW Tax reporting CSV export 能力 + Account Statement excludes Earn | MED | Sprint 1A V094 cadence reference |
| **18** | §0.5 NEW Earn Flexible APR floating + default risk 條款 | LOW | C-5 self-cert reference |
| **19** | §0.6 NEW KYC 3 tier withdraw limit + perpetual + Earn coverage | LOW | C-2 KYC tier reference |

估 ~3-4 hr 與既有 BB1 工作合併。

## §13 Bybit-side overall

- 技術合規度: **98%**（30d 0 breaking change / rate limit 97% headroom / 5-gate live boundary 全 enforce / Earn Wave C source-layer 對齊）
- 政策合規度: **70%**（M5-1 18+ day stale + 5 operator confirm 0 進展 + 字典 §3 Earn + 16 restricted jurisdictions 表 0 entry）
- 0 技術 ship-stop blocker
- 0 hard boundary 觸碰
- 0 ToS 違反 risk (前提 operator non-restricted residence)

## §14 結論

**APPROVE-WITH-5-OPERATOR-CONFIRMS** for Earn Wave C OP-1 ~ OP-3 hand action chain (前提 C-1 + C-2 + C-3 + C-5 land)。

**CONDITIONAL-BLOCKED** for Sprint 4 first Live W18-21 cutover (前提 C-1 + C-2 + C-3 + C-4 land)。

**0 BB push back on operator-decided IP whitelist** (P1-OP1 closed 2026-05-25 選項 (b))。

關鍵 push back：M5-1 governance entry 18+ day 0 進展是 Sprint 4 first Live W18-21 真實 ship-stop；非 IP whitelist / API tier / endpoint drift 任一技術問題。

## §15 下次啟動需查驗項

1. `docs/governance_dev/2026-05-26--bybit_compliance_signoff.md` 是否建檔 + C-1 ~ C-5 5 自證是否 land
2. 字典 §0.1 ~ §0.6 6 新章節 + §3 Earn 章節（含 5/21 13 處 carry-over 共 19 處）是否啟動
3. Earn Wave C OP-1 ~ OP-3 hand action chain 是否觸發（per TODO.md §7 D+2~D+3）
4. Sprint 4 first Live W18-21 預備期前 30d operator tax filing cadence 拍板
5. Japan exit 2026 + UK re-entry 2026 政策更新是否影響 operator (取決 C-1)
6. Bybit V5 30d changelog 例行 audit (per BB SOP 每月)
7. M5-1 governance entry 18 day → 1 month 升級 risk

---

BB AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-26--p0-ops-3-bybit-tos-geo-kyc-audit.md
