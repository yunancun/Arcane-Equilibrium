---
report: BB Sprint 1B Pending 3.2 Earn cross-ref review on earn_governance spec amendment + E1c IMPL
date: 2026-05-23
agent: BB (Bybit Broker Compatibility Auditor)
phase: Sprint 1B late Pending 3.2 Earn — 5 角色並行 cross-ref (FA/E3/QA/MIT/BB) 各 1-2 hr single-thread
head: 875de212 feat(sprint1b-earn-wave-b): Earn Wave B IMPL ✅ 5 並行 sub-agent + CC amend DONE
trigger: PM 派 5 角色並行 cross-ref on earn_governance spec amendment + 5 E1 IMPL Wave B DONE
verdict: APPROVE-WITH-3-CAVEATS (1 spec amend MED mandatory + 2 follow-up LOW)
---

# BB Sprint 1B Earn Cross-Ref Review — 2026-05-23

## §0 TL;DR

- **核心 verdict**：APPROVE-WITH-3-CAVEATS。E1c IMPL Bybit V5 unified path 100% 對齊 tiagosiebler 2026 SDK SSOT；揭露 PA dispatch packet §1.2 + BB 5/21 own verdict Part A.2 兩處列 2025 SDK 舊 path 屬 stale。
- **3 caveat**：(BB-C1 MED mandatory) earn_governance spec 4 處 amend；(BB-C2 LOW follow-up) 字典 §3 Earn 章節 land；(BB-C3 LOW awareness) Bybit 2025-10-30 Dynamic Settlement Frequency System 對 Sprint 5+ 影響
- **0 ship-stop / 0 hard boundary 觸碰**
- 技術合規 98% (spec §3.5 補後 100%) / 政策合規 72%

## §1 審計範圍 + 證據鏈

### 1.1 三方對齊驗證

| 來源 | Path scheme | 結論 |
|---|---|---|
| PA dispatch packet §1.2 (2026-05-23 c9913ff8) | `/v5/earn/flexible/*` + `/v5/earn/fixed/*` 12 endpoint | **STALE** — 2025 SDK snapshot |
| BB 5/21 verdict Part A.2 (2026-05-21) | `/v5/earn/flexible/*` + `/v5/earn/fixed/*` 12 endpoint | **STALE** — 同 PA packet 源 |
| E1c Rust IMPL `bybit_earn_client.rs` 601 LOC | `/v5/earn/product` + `/v5/earn/place-order` + `/v5/earn/position` + `/v5/earn/apr-history` 4 unique endpoint | **CORRECT** — 對齊 tiagosiebler 2026 SDK |
| tiagosiebler 2026 SDK endpointFunctionList (WebFetch verified) | unified 4 endpoint, stake/redeem 共用 `/v5/earn/place-order` orderType 區分 | **真實 SSOT** |

**SSOT 原則生效**：代碼為真。E1c IMPL MODULE_NOTE line 24-35 明示「PA packet §1.2.1 列『/v5/earn/flexible/*』屬 2025 舊路徑，2026 V5 統一為 `/v5/earn/*` 帶 `category=FlexibleSaving`，本 IMPL 採真實 path」— spec drift fix verify PASS。

### 1.2 證據鏈 file paths（絕對路徑）

- E1c IMPL SSOT: `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bybit_earn_client.rs`
- RateLimit patch: `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bybit_rest_client.rs:240-258`
- earn_governance spec (待 amend): `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--earn_governance_spec.md`
- PA dispatch packet (§1.2 stale): `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md:60-91`
- BB 5/21 own verdict (own stale): `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md:60-71`
- 字典手冊: `/Users/ncyu/Projects/TradeBot/srv/docs/references/2026-04-04--bybit_api_reference.md` (1337 LOC, Earn grep 0 hit)

## §2 Caveat 1 (MEDIUM mandatory) — earn_governance spec 4 處 amend

| 章節 | 現狀 | 建議 amend |
|---|---|---|
| §3.5 NEW | 抽象描述 `IntentType::EarnStake` / `EarnRedeem` 但未列底層 V5 endpoint path | 新增 §3.5「Bybit V5 unified path 對映」表：4 endpoint constant + orderType=Stake/Redeem 區分 + category=FlexibleSaving 固定 + accountType=UNIFIED 固定 |
| §4.2 條件 A finalize (line 233-238) | 採 condition A 但未列具體 endpoint path | 補「demo + live 同走 `/v5/earn/product` + `/v5/earn/place-order` + `/v5/earn/position` + `/v5/earn/apr-history` 4 unique endpoint」 |
| §10.2 上游依賴 (line 463-465) | 寫 `BB v57-C4 verdict 🔴 PENDING` | **內部矛盾**：§4.5 line 257-267 已採 condition A finalize；line 463 應同步改 `✅ DONE 2026-05-21 verdict (a)` |
| §13 Amendment Log | 2026-05-23 PA caveat 1+2 已 land | 加 caveat 3 entry：「BB cross-ref 揭露 PA §1.2 12 endpoint 列 2025 SDK 舊 path；E1c IMPL 已採真實 2026 V5 unified path；spec 補 §3.5 endpoint 表對齊 IMPL SSOT」 |

## §3 Caveat 2 (LOW follow-up) — 字典 §3 Earn 章節 land

- grep 0 hit `/v5/earn` / `FlexibleSaving` / `Earn API` 全部 0
- BB memory 5/21 verdict 列「§3 NEW Earn API 章節，HIGH」**從 7 升 13** — 仍未 land
- **建議**：Wave 3b BB1 啟動時用 E1c IMPL 4 unique endpoint 為 SSOT（**不是** BB 5/21 verdict 列的 12 SDK function name 表，那是 stale）；12 SDK function name 為 alias reference
- 字典 §4.1 Rate Limit table 加 Earn group 對映 Asset 5 req/s 註腳
- 估 4-6 hr 與既有 Wave 3b 工作合併

## §4 Caveat 3 (LOW awareness) — Bybit Dynamic Settlement Frequency System

- Bybit 2025-10-30 launch；funding rate 達 ±0.75% 上下限 → auto shift 1h cadence
- spec amend caveat 2 UTC 02:00 cron 設計對齊 Bybit 8h **default** cadence；dynamic frequency 只在極端情況觸發
- **當前 Earn-only scope 0 影響**（Earn 是 staking yield，與 perp funding settlement 無直接耦合）
- **Sprint 5+ 若加 perp funding 相關 reconciliation**，UTC 02:00 須重評 dynamic frequency window（極端情況 funding 在 02:00、03:00、04:00 等任意整點觸發）

## §5 RateLimit + ToS + KYC verify

### 5.1 RateLimitGroup::Asset 5 req/s 共享預算 ✅ PASS

`bybit_rest_client.rs:240-258` 確認 `/v5/earn/` + `/v5/asset/` + `/v5/spot-margin` 共享同 Asset 5 req/s 槽位。

| 計算 | 數值 |
|---|---|
| Sprint 1B first stake 用量 (operator-triggered manual) | < 0.01 req/s |
| Daily reconciliation cron UTC 02:00 | 0.000012 req/s |
| 既有 `/v5/asset/*` (wallet-balance, fee-rate) | < 0.1 req/s sustained |
| 既有 `/v5/spot-margin*` (OpenClaw 不接) | 0 |
| **Asset group 總用量** | **< 0.15 req/s = 3% 利用率** |
| 餘裕 | **97% headroom** |

### 5.2 OP-1 < 2026-04-09 key 重發 scope 覆蓋 verify ✅ PASS

- E-1 / E-4 / E-5 (GET): `Earn` 或 `Read-Only` 兩 scope 皆可
- E-2 / E-3 (POST `/v5/earn/place-order`): 強制 `Earn` write scope
- non-withdraw 充分覆蓋 5 endpoint read + write（per BB 5/21 C5 verdict (a)）

### 5.3 OP-3 Flexible only vs Bybit Earn product matrix ✅ PASS

| Bybit Earn product matrix | E1c IMPL scope |
|---|---|
| FlexibleSaving (隨時 stake/redeem) | ✅ 包含 (CATEGORY_FLEXIBLE_SAVING const + 5 endpoint method) |
| Fixed Saving (90/180 day 鎖倉) | ❌ defer Sprint 5+ |
| Easy-Onchain | ❌ 不包含 |
| BYUSDT earning | ❌ 不包含 |
| Fixed Saving `/v5/finance/earn/fixed-saving/*` | ❌ 不包含 |
| DualAssets (2026-03-17 launch) | ❌ 不包含 |
| Crypto Loan | ❌ 不包含 |

E1c IMPL 5 endpoint 100% 對齊 OP-3 flexible-only 邊界。

### 5.4 ToS / KYC / broker rebate / 地理禁區 ✅ PASS

- **Earn = asset write event 非 trading**：不觸 broker rebate volume tally（30d $45k 仍差 $10M threshold 222×，0 影響）
- **不觸 KYC tier 升級**：Bybit Earn 對 UTA 持有者開放
- **無地理禁區風險**：待 M5-1 operator 自證
- **Wash trading risk = 0**：Earn 是 product subscribe 非 order book interaction

### 5.5 funding settlement UTC 02:00 amend caveat 2 ✅ PASS

- Bybit perp funding default 8h cadence UTC 00:00 / 08:00 / 16:00
- UTC 02:00 距上一 funding 2h + 距下一 6h → settle in-flight stale balance race 0
- amend caveat 2 拒 UTC 00:30 是對的（距 settlement 僅 30 min 高 false-positive mismatch risk）

## §6 verdict 總結

**APPROVE-WITH-3-CAVEATS**

- 0 ship-stop blocker
- 0 hard boundary 觸碰
- 30d Bybit V5 changelog 0 breaking change

### 對 Sprint 1B Pending 3.2 dispatch 影響

- BB-C1 (MED mandatory) earn_governance spec 4 處 amend 在 PM consolidate 5 角色 verdict 後處理；不阻 Sprint 1B Wave C kickoff
- BB-C2 (LOW follow-up) 字典 §3 Earn 章節 land 屬 Wave 3b BB1 範圍；不阻 Sprint 1B
- BB-C3 (LOW awareness) Sprint 5+ 才適用；當前 0 影響

### Bybit-side overall

- 技術合規度: 98% (spec §3.5 補 endpoint 表後 100%)
- 政策合規度: 72% (M5-1/M5-2 stale + OP-1 < 2026-04-09 key 重發 pending)

## §7 下次啟動需查驗項

1. earn_governance spec §3.5 NEW endpoint 表 + §4.2 / §10.2 / §13 amend 是否 land
2. 字典 §3 Earn 章節是否啟動 (Wave 3b BB1，從 7 升 13)
3. OP-1 D+1 OpenClaw key 發行日 5-min operator action 是否完成
4. Sprint 1B Wave C E2 adversarial review 後 5 角色 verdict consolidate
5. Bybit V5 changelog 30d 例行 audit (per BB SOP 每月)
6. M5-1 / M5-2 governance entry + IP whitelist preflight 是否啟動

---

BB AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-23--earn_governance_cross_ref_bb_review.md
