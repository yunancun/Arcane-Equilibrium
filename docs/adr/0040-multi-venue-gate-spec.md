# ADR 0040: Multi-Venue Gate Spec — M13 Binance Trade Enable Defer Y3+ At Earliest

Date: 2026-05-21
Status: **Accepted**（per operator D4 2026-05-21；本 ADR 為 ADR-0033 §Decision 2 時點 amendment standalone）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via BB 5.21 v5.8 audit push back + PM final verdict §四 D4「M13 Y2 Binance trade enable → Y3+ at earliest」批准）
Supersedes: ADR-0033 §Decision 2 「Y1 末（Sprint 10 W36-39）evaluation」時點 → 改 Y3+ first quarter (~Y2 末 W104+) evaluation；ADR-0033 §Decision 1（Binance market-data Y1 approved）+ §Decision 3（DEX/Hyperliquid not approved）+ §Decision 4（D12 + ToS posture）**不變**
Sign-off chain note: ADR-0033 + ADR-0040 在同一 operator sign-off session（2026-05-21 主會話 PM dispatch）一起確認。邏輯順序為 ADR-0033 sign-off 先成立（v5.7 §12 ADR-0006 amendment 提案落地）→ ADR-0040 sign-off 包含對 ADR-0033 §Decision 2 的 timing supersede（v5.8 BB audit push back 觸發）；治理 trail = ADR-0006 baseline → ADR-0033 baseline amendment → ADR-0040 timing amendment，三 ADR 並存形成完整 cross-venue gate evidence chain。
Related: ADR-0006 (Bybit-only baseline 2026-04-03 — thesis 不變) / ADR-0033 (ADR-0006 amendment Binance market-data + Y2 evaluation — 本 ADR 為其 §Decision 2 時點 amendment) / ADR-0034 (LAL 4 capital structure / venue change always operator) / ADR-0035 (M5 online learning interface reservation；同 Sprint 1A-δ deliverable + 同 interface-reservation pattern) / CLAUDE.md §一 Bybit-only + §四 mainnet boundary / AMD-2026-05-21-01 autonomy-vs-human-final-review / v5.8 §2 M13 (Multi-asset class / multi-venue capacity) / v5.8 §5 capital-tier ladder

## Context

### 起源 — v5.8 M13 Y2 Binance trade enable 與既有 governance 字面衝突

v5.8 主檔 §2 M13 (line 460-487) 列出 Multi-asset class / multi-venue 的 roadmap：

```
Y1: Bybit perp + Bybit spot (Earn) + Bybit options (C13 VRP)
Y2: + Binance perp (price-equivalent symbols only; per ADR-0006 amendment Binance market-data primary, trade secondary)
```

BB 5.21 v5.8 audit push back 揭露此處與既有 governance **字面衝突**：

1. **與 ADR-0033 §Decision 2 衝突**：ADR-0033 §Decision 2 明寫「Y1 不開放任何 Binance trading endpoint」+「Y2 evaluation 通過條件 = 4 條 (a)(b)(c)(d)」（Y1 Bybit alpha 驗證 + Y1 Binance market data 顯示 +1%+ alpha + Operator 仲裁 + BB confirmed ToS/KYC）。v5.8 M13 「Y2: + Binance perp trade secondary」直接寫死 Y2 trade enable，**未經 Y2 evaluation gate**。
2. **與 CLAUDE.md §一 衝突**：CLAUDE.md §一 Product Boundary 仍寫「Bybit is the only exchange target」。M13 Y2 Binance trade 與此字面立場直接衝突。

### Y1 末 evidence 可能不足支撐 Y2 evaluation

進一步分析揭露：即使按 ADR-0033 §Decision 2 走 Y2 evaluation gate，**Y1 末 evidence 可能不足**：

- **Y1 Bybit alpha 未必已驗**：Sprint 4 first Live 在 W17.5-W20.5 才開始，加上 P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 阻塞，Y1 末（Sprint 10 W36-39）可能只累積 ~16 週 Live evidence，不足以支撐「sustained Sharpe ≥ X for 12-18 months」 alpha gate
- **Y2 evaluation deadline 緊**：Sprint 10 W36-39 evaluation window 加上 W17.5-W36 之間 4 個月實際 trade evidence 累積，evaluation 評估時可能 evidence base 過薄導致 (a) gate inconclusive
- **Copy Trading evidence 未 land**：ADR-0030 Copy Trading evidence-gated 設計 Y1 末 evaluation；若 Copy Trading Y1 evidence 未通過，Y2 enable Binance trade 同時打開兩條新 surface 風險疊加過高

### Operator D4 決策路徑

Operator D4 採 BB audit verdict + PM final verdict §四 D4 推薦：**M13 Y2 Binance trade enable → Y3+ at earliest**

- Y2 期間 Binance 仍維持 **market-data only**（ADR-0033 §Decision 1 不變）
- Y3+ evaluation 條件 = ADR-0033 §Decision 2 4 條件 + 新增 2 條（Y2 Bybit alpha sustained + Copy Trading evidence land）
- ADR-0033 不取代；本 ADR-0040 為 venue 層獨立 ADR，**amend ADR-0033 §Decision 2 時點**（Y2 → Y3+），其他 §Decision 1/3/4 全部保留

### 為什麼本 ADR 是 standalone 而非 inline edit ADR-0033

per ADR governance pattern「ADR 接受後不修改，只能 superseded by 新 ADR」+ ADR-0033 本身就是 ADR-0006 amendment standalone 的同類 pattern：

- ADR-0033 §Decision 2 「Y1 末 evaluation」立場在當時（2026-05-21 v5.7 §12 提案時）符合 v5.7 預估 evidence base；本 ADR 是 v5.8 dispatch 過程中 BB audit 新發現的 timing 約束 amendment
- 治理 trail 完整性：ADR-0033 為 baseline amendment，ADR-0040 為其 timing amendment，兩 ADR 並存形成完整 cross-venue gate evidence chain
- 未來若 Y3+ evaluation 通過 enable Binance trade，將開新 ADR-XX 第三層 amendment；不在本 ADR 預判

### 為什麼是「Y3+ at earliest」而非硬鎖 Y3 / Y4 / 永久 defer

- **Y3+「at earliest」**：reflects evidence-gated 立場 — Y3+ 是**最早可能的 evaluation timing**，不是固定 enable timing；若 Y3+ evaluation 6 條件任一 fail 則繼續 defer
- **不硬鎖 Y3**：Y2 末實際 evidence base 未知；可能 Y3 Q1 不夠完整需順延到 Y3 末甚至 Y4
- **不永久 defer**：multi-venue 對沖 long-run optionality 仍有戰略價值（D12 single-venue freeze risk 對 $50k+ AUM 帳更顯著）；保留 reopen 路徑

## Decision

**Proposed**：為 v5.8 M13 multi-venue capacity 設定 venue 層 gate 規範，包含 5 個獨立 decision：

### Decision 1 — Binance Trade Enable 時點 Amend Y2 → Y3+ At Earliest

| 元素 | 設計 |
|---|---|
| ADR-0033 §Decision 2 原時點 | Y1 末（Sprint 10 W36-39）evaluation |
| **本 ADR amend 後時點** | **Y3+ first quarter (~Y2 末 W104+) evaluation** |
| Y2 期間 Binance posture | **Market-data only**（ADR-0033 §Decision 1 不變）|
| Y2 期間禁止 | (a) 任何 Binance order placement (b) 任何 Binance authentication beyond market-data API key (c) 任何 Binance asset transfer / wallet operation —— 與 ADR-0033 §Decision 2 Y1 期間禁止項完全一致 |
| Y3+ evaluation 觸發 window | Y2 末（W100-W104）prep；Y3 Q1（W105-W117）evaluation |
| Y3+ evaluation 通過條件 | per §Decision 3 6 條（合併 ADR-0033 4 條 + 本 ADR 新增 2 條）|
| Y3+ evaluation 失敗 → 繼續 defer | 任何 6 條件 fail → 維持 Bybit-only trading，繼續 Y3+ cycle 重評（per ADR-0033 §Decision 2 失敗 → defer 邏輯延伸）|
| Y3+ evaluation 永久放棄條件 | 連續 3 個 evaluation cycle (~12-18 months) fail → 開新 ADR 永久關閉 Binance trading optionality（per ADR-0033 §Decision 2 邏輯保留）|

### Decision 2 — Per-Venue 5-Gate Schema

ADR-0033 + CLAUDE.md §四 既有 5-gate live boundary（Python `live_reserved` / Operator role / `OPENCLAW_ALLOW_MAINNET` / valid secret slot / signed `authorization.json`）**擴展為 venue-aware**：

| Gate | 既有設計 | Venue-aware 擴展 |
|---|---|---|
| 1. Python `live_reserved` | Bybit-only | 仍為 venue-agnostic gate；任一 venue trading 啟用都需通過 |
| 2. Operator role 授權 | Bybit-only | 仍為 venue-agnostic gate；任一 venue trading 啟用都需通過 |
| 3. `OPENCLAW_ALLOW_MAINNET=1` | Bybit-only | 仍為 venue-agnostic gate；任一 venue trading 啟用都需通過 |
| 4. Valid secret slot | `$OPENCLAW_SECRETS_DIR/api_key`（Bybit only） | **Per-venue**：`$OPENCLAW_SECRETS_DIR/external/<vendor>/api_key`（per H-21 external secret slot policy）；Bybit 走原 path，Binance 走 `external/binance/api_key` |
| 5. Signed `authorization.json` | environment-bound（demo / live） | **Venue-aware**：authorization.json 必含 `venue` field（默認 = `'bybit'`）；非 `'bybit'` 必經 Y3+ Binance enable gate（per Decision 3）|

**Fail-closed 邊界**：5-gate 任一 fail → fail-closed **該 venue 全部 outbound order**（不影響其他 venue）

- 例：Bybit secret slot expired → Bybit trading freeze，**不影響** Binance market-data read（per ADR-0033 §Decision 1）
- 例：Binance authorization.json venue field 校驗 fail → Binance trading freeze（Y3+ enable 後），**不影響** Bybit trading

### Decision 3 — Y3+ Binance Trade Enable Gate Criteria（6 條合併）

合併 ADR-0033 §Decision 2 4 條 + 本 ADR 新增 2 條（Y2 末額外 evidence）：

| # | Criterion | 來源 | 評估方法 |
|---|---|---|---|
| (a) | Y1 + Y2 Bybit self-trading alpha 已驗證 | ADR-0033 §Decision 2 (a) 延伸 | Sharpe ≥ X for **12-18 months sustained**（per ADR-0030 Gate 1 Alpha 延伸；Y1+Y2 累積 ~22 months 樣本足夠）|
| (b) | Y1 + Y2 Binance market data analysis 顯示 cross-venue arbitrage / liquidation hunting 等 strategy 真有 +1%+ alpha vs Bybit-only baseline | ADR-0033 §Decision 2 (b) 延伸 | Counterfactual replay using Binance market data Y1+Y2 兩年累積；vs Bybit-only baseline alpha attribution |
| (c) | Operator 仲裁 | ADR-0033 §Decision 2 (c) 不變 | **New 5-gate review session**（per Decision 2 venue-aware authorization.json 簽署需 Operator session）|
| (d) | BB confirmed Binance ToS / KYC 持續可行 | ADR-0033 §Decision 2 (d) 不變 | BB 提供 Bybit + Binance KYC + ToS cross-venue 持續性 audit 報告 |
| (e) | **Y2 末 Copy Trading evidence land** | **本 ADR 新增** | per ADR-0030 Copy Trading evidence-gated；Y2 末 Copy Trading 必須通過 4-Gate evaluation 並 land 為 active income stream（不要求 scaling，要求 evidence land）|
| (f) | **AUM ≥ $50k sustained 30d** | **本 ADR 新增** | per v5.8 §5 capital-tier ladder Y3+ AUM 估計；$50k 是 Binance trade enable 的 capital efficiency 門檻（cross-venue position reconciliation + KYC dispute mitigation 成本對小帳不經濟）|

**6 條 AND 邏輯**：6 條全 PASS → Y3+ evaluation PASS → 開新 ADR 落地 Binance trade enable；任一 FAIL → continue defer

### Decision 4 — Venue Enum Hardcode

| 元素 | 設計 |
|---|---|
| Rust `Venue` enum | `BybitPerp` / `BybitSpot` / `BybitOption` / `BinancePerpMarketData` (Y1+Y2 active) / `BinanceSpotMarketData` (Y1+Y2 active；per ADR-0033 §Decision 1 spot tickers + OHLCV 範圍) / `BinancePerpTrade` (Y3+ gated; enum slot 預留但 trading code path inactive) |
| **Hardcode 拒絕的 venue** | **DEX**（Uniswap / GMX / dYdX 等）/ **Hyperliquid** —— 不在 enum 中保留 slot，從根源拒絕（per ADR-0033 §Decision 3 + CLAUDE.md §一）|
| Enum 邊界 | 任何 IMPL **不可繞 enum 走 string literal venue ID**（per ADR-0006 / ADR-0033 architectural 簡化好處）；string literal 容易繞過編譯期 venue check，違反 fail-closed 紀律 |
| 未來開放新 venue 路徑 | 若未來需開放新 venue（如 OKX / Coinbase），必須開新 ADR 顯式 amend 本 ADR + 新增 enum variant + 對應 per-venue 5-gate schema；不可在沒有新 ADR 的情況下 hot-patch 加 string venue |
| Read-only on-chain query 例外 | per ADR-0033 §Decision 3 例外 + ADR-0031 Framework 3 on-chain counterfactual-only Y1 立場；**不創造 venue enum slot**（read-only RPC query 不屬於 trading venue）|

**Note**：`BinanceSpotMarketData` enum slot 對應 ADR-0033 §Decision 1 「Spot/perp tickers + funding rate + liquidations + OHLCV」接入範圍中的 spot 部分；funding rate / liquidations / OHLCV 不需獨立 enum slot（屬於 market data feed dimension 而非 venue）。

### Decision 5 — Per-Venue Authorization 流程

| 元素 | 設計 |
|---|---|
| Per-venue secret slot 寫入 | **Operator 手寫**（per CLAUDE.md §四 mainnet env-var fallback closed + ADR-0008 Decision Lease 簽署紀律）|
| Per-venue authorization.json 簽署綁定 | **venue + environment + secret slot 三元組綁定**（per AMD-2026-05-15-01 + ADR-0008 Decision Lease）—— 三元組任一 mismatch 即 fail-closed |
| `venue` field schema 強制性 | authorization.json schema 強制 `venue` field（默認 = `'bybit'` 維持既有 backward compatibility）；non-bybit venue 必須顯式寫 `venue` field |
| 簽署時的 5-gate review | per Decision 3 (c) Operator 仲裁 = **new 5-gate review session**；session 中 Operator 必須逐一確認 5 gate + 6 條 evaluation criteria + 簽署 venue + environment + secret slot 三元組 |
| Lease tier 對齊 | per ADR-0034 LAL 4 capital structure：**venue change 永遠走 LAL 4** = Operator approval mandatory，Agent 無法自主提案 venue enable / disable |

**Wave 5 v2 sync（2026-05-28）**：AMD-2026-05-21-01 v2 / Autonomy Level Toggle Q2 拍板不改本 Decision 的 final-action 邊界。Venue gate 的 deterministic evaluation（6 條 hard gate verify）可以自動計算並展示，但 **venue enable / disable / authorization 三元組簽署在 Level 1 與 Level 2 下都仍需 operator approve manual**。Level 2 Standard 不把 venue change 納入 auto path。

## §ADR-0033 ↔ ADR-0040 關係圖

```
ADR-0006 (2026-04-03 accepted, baseline 不變)
  └─ Bybit is the sole execution venue
     └─ Binance retained only as a hypothetical long-term option

ADR-0033 (2026-05-21 proposed, amendment standalone)
  ├─ Decision 1: Binance market data approved Y1 ✅ 不變
  ├─ Decision 2: Binance trading defer Y2 evaluation ← 時點被 ADR-0040 amend
  ├─ Decision 3: DEX/Hyperliquid NOT approved Y1+Y2 ✅ 不變且強化
  └─ Decision 4: D12 + ToS posture ✅ 不變且 extend to Y3+

ADR-0040 (2026-05-21 proposed, venue gate amendment standalone)
  ├─ Decision 1: Binance trade enable 時點 amend Y2 → Y3+ at earliest
  ├─ Decision 2: Per-venue 5-gate schema (venue-aware authorization)
  ├─ Decision 3: 6 條 Y3+ Binance trade enable gate criteria (ADR-0033 4 + new 2)
  ├─ Decision 4: Venue enum hardcode + DEX/Hyperliquid 拒絕 (強化 ADR-0033 §Decision 3)
  └─ Decision 5: Per-venue authorization 三元組綁定
```

**ADR-0033 仍是 multi-venue baseline 的 source of authority**；ADR-0040 是其 timing amendment + venue gate schema 擴展。任何未來 Y3+ evaluation 通過後的 enable 落地，必須開新 ADR amend ADR-0040 + 標明對 ADR-0033 / ADR-0006 的相對立場。

## Cross-References with ADR-0033

| ADR-0033 元素 | 本 ADR-0040 對應 | 說明 |
|---|---|---|
| §Decision 1 (Binance market data approved Y1) | **不變** | Y2 期間 Binance 仍維持 market-data only；本 ADR Decision 1 明示 Y2 期間 market-data 持續 |
| §Decision 2 (Binance trading defer Y2 evaluation 4 條件) | **改 Y3+ at earliest evaluation 6 條件** | 本 ADR Decision 1（時點 amend）+ Decision 3（6 條合併）取代原 §Decision 2 時點 + 條件 |
| §Decision 3 (DEX / Hyperliquid NOT approved) | **不變且強化** | 本 ADR Decision 4 venue enum hardcode 從根源拒絕（不留 enum slot），比 ADR-0033 「不接入」立場更嚴 |
| §Decision 4 (D12 + ToS posture) | **不變且 extend to Y3+** | D12 cap 80% 對 Y3+ Binance trade enable 後成立（trading exposure 跨 Bybit + Binance 合計）；ToS 持續 monitoring |

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **維持 v5.8 M13 Y2 enable**（無 amendment） | ADR-0033 §Decision 2 4 條件不夠 robust 風險（Y1 末 evidence 可能不足 + Copy Trading evidence 未 land + AUM 未達門檻）+ operator D4 已批 defer；維持原案違反 BB audit verdict |
| **完全關閉 Binance trade option**（Y3+ 也禁） | 違反 ADR-0033 §Decision 2 Y2 evaluation reopen path（雖 timing 改 Y3+ 但 evidence-gated 路徑保留）；multi venue 對沖 long-run optionality 對 $50k+ AUM 仍有戰略價值（D12 single-venue freeze risk mitigation）|
| **Y3+ 時點改 Y4+**（更保守） | AUM 增長路徑 per v5.8 §5 capital-tier ladder Y3 Q2 估 $25-50k 已過 Binance trade enable AUM 門檻 (f)；Y4 過於保守且無 evidence 支撐 |
| **不擴展 5-gate 為 venue-aware**（保持 venue-agnostic） | 若 Y3+ Binance trade enable，venue-agnostic 5-gate 無法區隔不同 venue 的 fail-closed scope；單一 secret slot expired 會誤殺所有 venue trading，違反 ADR-0033 §Decision 1 Binance market-data 持續 read 立場 |
| **不 hardcode venue enum**（允許 string literal venue ID） | string literal venue 容易繞過編譯期 venue check（如 PR 中混入 `"hyperliquid"` 而未 ADR review）；違反 ADR-0033 §Decision 3 proactive lock-down 紀律 |
| **新增 2 條 evidence gate (e)(f) 改為 (e) 或 (f) 二選一** | (e) Copy Trading evidence 與 (f) AUM 門檻是**不同維度**約束 —— (e) 證明既有 income lane 可持續，(f) 證明 capital efficiency 達標；二選一無法同時覆蓋兩個風險面 |

## Consequences

### Positive

- **ADR-0033 4 條件不夠 robust 風險化解** — Y3+ at earliest 給予 Y1+Y2 累積足夠 evidence + Copy Trading land 時間
- **Y2 期間 Binance 持續累積 cross-venue analytics** — per ADR-0033 §Decision 1 不變；Y3+ evaluation 時有 ~22 months 樣本支撐 (a)(b) gate
- **Per-venue 5-gate schema 對齊 H-21 external secret slot policy** — secret slot 已有 per-vendor 路徑設計，本 ADR Decision 2 為 H-21 在 governance 層的對應 amendment
- **Venue enum hardcode 對齊 CLAUDE.md §一 Bybit-only** — DEX/Hyperliquid 從 enum 根源拒絕，不需運行時 string check，編譯期即 fail-closed
- **Per-venue authorization 三元組綁定對齊 AMD-2026-05-15-01** — venue + environment + secret slot 三元組是 Decision Lease 紀律的自然延伸
- **與 ADR-0034 LAL 4 對齊** — venue change always operator approve；Agent 無法自主提案 venue enable，本 ADR Decision 5 為其 capital structure 對應

### Negative / Risk

- **v5.8 §2 M13 文本 + §5 capital-tier ladder + §6 autonomy estimate 需同步更新** —— Y3 Q2 95% 估計仍 hold 因 Binance trade Y3+ 開後 capacity ↑，但實際 enable 可能 Y3 末 / Y4；mitigation = 主會話 v5.8 主檔 update 時 cite 本 ADR；§5 capital-tier ladder 不需動 AUM 估計（M13 Binance trade 不在 Y1+Y2 income lane）
- **Y3+ evaluation 6 條件中 (a) 12-18 months sustained 可能 evidence base 仍不足** —— Y1+Y2 累積實際 22 months 但 Live trading 起始 Sprint 4（Y1 W17.5），實際 sustained alpha window ≈ 18-20 months；mitigation = 若 (a) inconclusive，繼續 defer 至 Y3 末或 Y4 即可
- **Per-venue secret slot 額外管理負擔** —— Operator 需管理多個 secret slot（Bybit + future Binance）；mitigation = H-21 external secret slot policy 已設計分層；運維負擔在 Y3+ 才出現
- **Venue enum 演進 ADR-debt** —— 未來若需開放新 venue（如 OKX）必須開新 ADR 加 enum variant + per-venue 5-gate；mitigation = enum-driven 演進是受控路徑，比 string literal 的隱性擴展風險低
- **(f) AUM ≥ $50k 門檻可能延遲 Binance trade enable** —— 若 v5.8 §5 capital-tier ladder Y3 Q2 estimate 過樂觀（$25-50k mid-range），可能 Y3 Q3-Q4 才達 $50k sustained 30d；mitigation = 6 條 AND 邏輯本身就是 evidence-gated，延遲是設計意圖

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| ADR-0006 (Bybit-only baseline 2026-04-03) | **不變**；本 ADR 為 ADR-0033 timing amendment，不擾動 ADR-0006 thesis |
| ADR-0033 (ADR-0006 amendment 2026-05-21) | **§Decision 2 時點被 ADR-0040 amend**；§Decision 1/3/4 全部保留並引用 |
| ADR-0008 (Decision Lease state machine) | **本 ADR Decision 5 三元組綁定為其 venue 維度延伸**；venue 是 Decision Lease 新 dimension |
| ADR-0030 (Copy Trading evidence-gated) | **本 ADR Decision 3 (e) Y2 末 Copy Trading evidence land 引用 ADR-0030 4-Gate evaluation** |
| ADR-0031 (Framework expansion — Earn / Macro / On-chain) | **On-chain read-only RPC query 例外不在 venue enum**（per Decision 4 註）；不違反 DEX not approved |
| ADR-0032 (Earn asset movement Guardian) | **D12 cap 與 Earn Risk envelope 互補延伸 Y3+**（per ADR-0033 §Decision 4 不變且 extend）|
| ADR-0034 (LAL 4 capital structure / venue change always operator) | **本 ADR Decision 5 為其 venue 維度對應**；venue change 永遠走 LAL 4 即 operator approval mandatory |
| AMD-2026-05-21-01 (autonomy-vs-human-final-review) | **venue change always operator** 立場；本 ADR Decision 5 三元組綁定 + Decision 1 Y3+ at earliest 對齊該 amendment |
| CLAUDE.md §一 Bybit-only | **字面立場保留**；本 ADR Decision 1 Y3+ at earliest 不違反「only exchange target」當前狀態；若 Y3+ enable 通過則同步 update CLAUDE.md（另 ADR-debt）|
| CLAUDE.md §四 mainnet boundary | **本 ADR Decision 2 + Decision 5 為其 venue 維度擴展**；5-gate live boundary venue-aware |
| v5.8 §2 M13 (Multi-asset class / multi-venue capacity) | **本 ADR Decision 1 amend M13 Y2 → Y3+**；主會話需 update v5.8 主檔 cite 本 ADR |
| v5.8 §5 capital-tier ladder | **本 ADR Decision 3 (f) AUM ≥ $50k sustained 30d 引用 v5.8 §5 Y3 Q2 estimate**；ladder 本身不動 |
| H-21 external secret slot policy | **本 ADR Decision 2 per-venue secret slot 為其 governance 層對應**；H-21 IMPL 路徑不動 |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 per venue | ✅ | Bybit 仍為唯一 active trading venue；Binance Y3+ enable 後 per-venue 5-gate 確保各 venue 單一寫入口；DEX/Hyperliquid enum-level 拒絕 |
| 2 | 讀寫分離 | ✅ | Binance Y2 仍 market-data only（純讀）；trading 走 Decision Lease + 5-gate（per venue）|
| 3 | AI 輸出 ≠ 命令 | ✅ | venue change 走 LAL 4（per ADR-0034）= Operator approval mandatory；Agent 無法自主提案 |
| 4 | 策略不繞風控 | ✅ | per-venue 5-gate 任一 fail → 該 venue 全部 outbound order freeze；策略無法繞 venue gate |
| 5 | **生存 > 利潤** | ✅ | Y3+ at earliest = 更保守時點，給 Y1+Y2 evidence 累積時間；defer 而非 push 是生存優先 |
| 6 | 失敗默認收縮 | ✅ | Y3+ evaluation 6 條件任一 fail → 繼續 defer；連續 3 cycle fail → 永久關閉 |
| 7 | 學習 ≠ Live | ✅ | Y2 期間 Binance market data 為 evidence accumulation；Y3+ enable 走 Decision Lease + 5-gate |
| 8 | 交易可解釋 | ✅ | per-venue authorization 三元組綁定（venue + environment + secret slot）+ Decision Lease 確保 venue 維度可追溯 |
| 9 | 雙重防線 | ✅ | per-venue 5-gate + 6 條 evaluation gate + LAL 4 operator approval = 多層 |
| 10 | 分離事實 / 推論 / 假設 | ✅ | Y3+ at earliest 反映「Y1 末 evidence 可能不足」是推論 + Operator D4 是事實；本 ADR 明示兩者 |
| 11 | **Agent 自主在 P0/P1 內 / venue change 屬 LAL 3-4 protected** | ✅ | venue enable / disable 走 LAL 4（per ADR-0034）；Agent 在 venue 啟用後可在 P0/P1 內自主使用該 venue trading |
| 12 | 系統行為從證據演進 | ✅ | 6 條 evaluation criteria 全部 evidence-based（alpha sustained / counterfactual / Copy Trading land / AUM）|
| 13 | AI 調用 cost 感知 | ✅ | venue change 不涉及 LLM 調用 cost；governance cost 在 Operator 5-gate review session |
| 14 | 零外部成本 baseline | ✅ | Binance API 接入 free tier；secret slot 管理屬於本地運維 |
| 15 | 多 agent 協作 formal | ✅ | venue gate 涉及 PM / BB / FA / E3 / Operator 多 role；per Sign-off table |
| 16 | Portfolio > 孤立 trade | ✅ | Y3+ enable 後 D12 cap 80% 跨 venue 合計（per ADR-0033 §Decision 4 extend）；portfolio-level diversification |

## Cross-References

- **ADR-0006**：`docs/adr/0006-bybit-only-exchange.md`（Bybit-only baseline 2026-04-03；thesis 不變）
- **ADR-0033**：`docs/adr/0033-adr-0006-bybit-binance-amendment.md`（本 ADR 為其 §Decision 2 時點 amendment standalone；§Decision 1/3/4 不變）
- **ADR-0008**：`docs/adr/0008-decision-lease-state-machine.md`（per-venue authorization 三元組為其 venue 維度延伸）
- **ADR-0030**：`docs/adr/0030-copy-trading-evidence-gated.md`（本 ADR Decision 3 (e) Y2 末 Copy Trading evidence land 引用）
- **ADR-0031**：`docs/adr/0031-framework-expansion-earn-macro-onchain.md`（on-chain read-only RPC query 例外不在 venue enum）
- **ADR-0032**：`docs/adr/0032-bybit-earn-asset-movement-guardian.md`（D12 cap 與 Earn Risk envelope 互補延伸 Y3+）
- **ADR-0034**：LAL 4 capital structure / venue change always operator approve（**待落地**；本 ADR 對齊其立場）
- **AMD-2026-05-21-01**：autonomy-vs-human-final-review（**待落地**；venue change always operator 立場對齊）
- **CLAUDE.md §一**：Bybit-only product boundary（字面立場保留；Y3+ enable 後另開 ADR-debt 同步 update）
- **CLAUDE.md §四**：mainnet hard boundary（本 ADR Decision 2 + Decision 5 為其 venue 維度擴展）
- **v5.8 §2 M13**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:460-487`（本 ADR Decision 1 amend M13 Y2 → Y3+）
- **v5.8 §5 capital-tier ladder**：本 ADR Decision 3 (f) AUM ≥ $50k sustained 30d 引用
- **H-21 external secret slot policy**：本 ADR Decision 2 per-venue secret slot 對應 governance 層
- **PA dispatch consolidation**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §1 CR-4
- **PM final verdict**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md` §四 D4
- **BB 5.21 v5.8 audit push back**：揭露 ADR-0033 §Decision 2 與 v5.8 M13 字面衝突

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via PM final verdict §四 D4（M13 Y2 Binance trade enable → Y3+ at earliest 已批） | 2026-05-21 | 🟢 APPROVED (D4 已批) |
| TW | 本文件起草（per operator D4 派工 + BB push back + ADR-0033 + CLAUDE.md §一 三方衝突落地為 ADR-0040 draft） | 2026-05-21 | ✅ Drafted |
| BB | Bybit + Binance ToS / KYC cross-venue review（v5.8 audit verdict 已採；本 ADR 為其 push back 落地） | 2026-05-21 | ✅ Drafted (audit verdict 已採) |
| E3 | Per-venue 5-gate schema review（secret slot path + authorization.json venue field schema） | TBD（Sprint 1A） | 🟡 PENDING |
| FA | Per-venue authorization 三元組綁定 + LAL 4 venue change interaction review | TBD（Sprint 1A） | 🟡 PENDING |
| PM | Y3+ first evaluation @ Y3 Q1 (W105-W117) 仲裁 | TBD（Y3 Q1） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0040 — Multi-Venue Gate Spec: M13 Binance Trade Enable Defer Y3+ At Earliest (Proposed, venue gate amendment standalone — ADR-0033 §Decision 2 timing amendment; ADR-0033 §Decision 1/3/4 unchanged; ADR-0006 baseline unchanged)*
