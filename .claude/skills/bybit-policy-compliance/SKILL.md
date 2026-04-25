---
name: bybit-policy-compliance
description: Bybit 平台政策合規 — ToS / 地理禁區 / KYC / API 用戶協議 / Rate limit / Broker rebate / IP whitelist / UTA / Master-Sub account / 公告追蹤節奏。BB agent 主用，與 crypto-microstructure-knowledge 互補（後者技術微結構，本檔政策面）。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Bybit Policy Compliance（Bybit 政策合規手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

## 何時觸發

- BB 收到「新 endpoint 部署」「API 鎖 / 帳戶問題」「rate limit 警報」「broker rebate 申請」「政策變動公告」
- OpenClaw 接通新 Bybit 功能（如 spot lending / margin trading）前的合規 review
- 新地區 deployment 評估
- 違反 ToS 的設計 alert

## ★ BB 角色立場

**BB = Bybit 派來的合規 / 政策顧問**：
- 從 Bybit 立場 push back operator 違規設計
- 涵蓋技術 + 政策 + 程序面
- 與 OpenClaw `bybit_api_reference.md` 字典手冊配合

## 1. ToS / 用戶協議關鍵條款（須背）

### 1.1 地理禁區（Restricted Jurisdictions）

> ⚠️ **本清單為 reference snapshot（2026-04）；Bybit 真實禁區動態變動，2024-2026 已多次調整**。**最終以 [Bybit 官方 ToS / Restricted Countries](https://www.bybit.com/en/help-center) 為準**；本 skill 不取代官方公告。涉及新地區 deployment / KYC 變動 → 立即查官方再決定。

Bybit 禁止以下地區的 user 開戶 / 交易（snapshot 2026-04，**必須定期校對**）：
- USA + territories（部分產品）
- Mainland China
- Singapore（部分產品 derivatives）
- Canada（部分省）
- Cuba / Iran / North Korea / Syria（OFAC sanctions）
- Crimea / Donetsk / Luhansk
- 其他依各國 regulator 動態

**OpenClaw 部署需確認**：operator 所在地區 + 帳戶 KYC 地區是否被 Bybit 限制。

### 1.2 禁止行為
- Wash trading（自買自賣）
- Spoofing（大單放又撤）
- Insider trading
- Pump-and-dump 協同
- Front-running（含某些演算法情境）
- Multiple account 規避 limit

**OpenClaw 設計 review**：
- Grid trading 同 symbol 同方向密集 order 是否觸 wash trading 紅線（Bybit 用 anti-wash filter，可能 cancel order 而非禁帳）
- Multi-strategy 同 symbol 反向 order 同時下：不算 wash（不同邏輯起源），但需審計 trace

### 1.3 API 用戶協議
- API key 不可分享、不可委託他人使用
- 通過 API 的所有交易視為 user 自己的決策（包括 AI agent）
- API key 洩漏 → user 自負後果
- Bybit 保留隨時 revoke API key 的權利

## 2. KYC 邊界

### 2.1 KYC tier 對應 limit
| Tier | 限制 |
|---|---|
| Tier 0（無 KYC） | 出入金限額嚴 / 部分 derivatives 不開 |
| Tier 1（基本 KYC） | 標準限額 |
| Tier 2（進階 KYC） | 高限額 + 法幣通道 |

OpenClaw operator KYC tier 影響：
- 出入金頻率
- Position size 上限
- 部分新 listing 申購資格

### 2.2 KYC 程序
- 護照 / 身分證
- 地址證明
- 自拍 + liveness
- 通過後立即生效

**警告**：API key 不能繞過 KYC，account-level 限制照舊。

## 3. API Rate Limit

### 3.1 General limits

> ⚠️ **以下數字為 reference snapshot；Bybit 真實 rate limit 動態變動**（VIP tier / broker partnership 會升）。**verify 命令**：`curl -s https://api.bybit.com/v5/market/time` 後看 response header `X-Bapi-Limit*`，或查 [Bybit Rate Limit doc](https://bybit-exchange.github.io/docs/v5/rate-limit)。本表為起步參考。

| 端點類型 | Default rate (reference) |
|---|---|
| Public REST | 120 req / 5s per IP |
| Private REST (auth) | 600 req / 5s per UID |
| Public WS | 100 msg / 1s per connection |
| Private WS | 100 msg / 1s per UID |

### 3.2 Per-endpoint limit（特殊高量端點）
- `/v5/order/create`：10 req / 1s（VIP 有提升）
- `/v5/order/cancel`：10 req / 1s
- `/v5/order/cancel-all`：1 req / 1s
- `/v5/position/list`：50 req / 1s

### 3.3 OpenClaw 預警閾值
- 任何端點 rate ≥ 80% limit → BB warning
- ≥ 95% → BB critical（會被 throttle / IP ban）

### 3.4 Limit 升級
- VIP tier → rate 提升
- Broker partnership → 更高 rate
- 申請流程：聯繫 Bybit BD

## 4. Broker Rebate / Market Maker 計劃

### 4.1 Broker partnership
- 客戶帶交易量給 Bybit → 享 fee rebate
- 申請門檻：30d 累計 volume ≥ $10M
- 收益：taker fee 15-30% rebate

### 4.2 Market Maker 計劃
- 條件：maker volume ≥ $50M / 30d + maker ratio ≥ 60%
- 收益：maker rebate 提升至 -0.0050%（從 0%）
- 限制：必須維持 quote spread / uptime SLA

**OpenClaw 適用**：當前不夠資格（單帳戶 size 太小）；未來 scale 後可申。

## 5. API Key Management

### 5.1 Permission scope
- `read`：query 倉位 / 訂單 / 帳戶
- `trade`：下單 / 撤單 / 修改
- `withdraw`：出金（OpenClaw **絕不**啟用）
- `transfer`：account 內 sub 轉

### 5.2 IP whitelist
- Production API key 必設 IP whitelist
- 改 IP 需 24h 冷靜期 + 2FA 驗證
- OpenClaw production 走固定 server IP

### 5.3 UTA (Unified Trading Account)
- 整合 spot / derivatives / options 在單一 wallet
- 跨產品 cross margin
- 升級流程：one-click upgrade，**不可逆**
- API endpoint 部分變動（OpenClaw 已記在 BB-A1~A7 audit 系列）

### 5.4 Master / Sub account
- Master 控制多個 sub
- 每 sub 獨立 API key
- 用於資產隔離 / 不同策略獨立風控
- OpenClaw 可考慮 demo / live 各一 sub

## 6. 公告追蹤節奏

### 6.1 來源
- Bybit Announcement Page
- API Changelog（`https://bybit-exchange.github.io/docs/changelog/v5`）
- Trading Rules updates
- Listing / delisting announcements

### 6.2 BB 例行 audit 頻率
- 每週掃 changelog 看 deprecated / new endpoint
- 每月複查 ToS 變動
- 重大事件後（如 monetary regulator 調整）立即追加 audit

### 6.3 OpenClaw 整合
- 字典手冊 `docs/references/2026-04-04--bybit_api_reference.md` 同步更新
- 新 endpoint 進入手冊前必走 BB review

## 7. OpenClaw 特定政策 review 清單

| Item | 檢查 | OpenClaw 當前狀態 |
|---|---|---|
| 地理禁區 | operator KYC 地區 | （operator 確認）|
| 禁止行為 | wash / spoofing | grid 過密下單需 audit |
| API permission | withdraw 啟用？ | ❌ 必確認禁用 |
| IP whitelist | production key 設置 | ✅ trade-core IP |
| UTA 升級 | endpoint 變動同步 | ✅ BB-A1~A7 已修 |
| Rate limit | 80% 警報 | demo 狀況需查 |
| Broker rebate | volume threshold | 未達 |
| Funding rate compliance | settle 規則同步 | ✅ 字典已記 |
| Listing 公告 | 新 perp 加入 | weekly check |
| Delisting | OpenClaw 25 symbol 中無 delist | 監控中 |

## 8. 工作流（10 步政策 audit）

1. **API key permission 4 項驗**（read/trade/withdraw/transfer）
2. **IP whitelist 確認**（production key only）
3. **KYC tier vs 預期 trading limit 對照**
4. **rate limit 30d statistics**（grep limit hit log）
5. **wash trading risk**（grid 同 symbol 密集 order audit）
6. **withdraw permission 必須關**
7. **Bybit changelog last 30d**（deprecated / new endpoint）
8. **Listing / delisting 新動態**（影響 25 symbol）
9. **Broker rebate eligibility**（30d volume vs $10M）
10. **產出 BB AUDIT report**

## OpenClaw 特定核心

- **Bybit 為唯一交易所**（CLAUDE.md §一）：跨所策略 out of scope
- **demo / paper / live_demo / live 4 環境**：每個環境合規規則微異（demo no-KYC、live KYC required）
- **authorization.json HMAC**（CLAUDE.md §四）：Live gate 5；BB 不直接管簽名邏輯但須驗 ToS 對應
- **OPENCLAW_ALLOW_MAINNET=1** 是 OpenClaw 內部 gate，不替代 Bybit KYC
- **withdraw permission 永遠 false**：OpenClaw 只交易不出金（CLAUDE.md §四 隱含）
- **EDGE-P2-3 PostOnly**：maker fee rebate 路徑啟用，不違 ToS（PostOnly 是合規行為）
- **funding_arb（G-2 結案 negative）**：方向設計合 ToS，但 economic dead

## 反模式（見即升級）

- API key 含 `withdraw` permission
- production key 無 IP whitelist
- 從禁區 IP / KYC 地區交易
- 同 symbol 同方向密集 order 觸 wash filter
- 部分國家用 derivatives 但 KYC 不允
- Bybit deprecated endpoint 還在用
- rate limit > 80% 沒警報 / log
- 超出 KYC tier 的 size / 交易類別
- 違反 anti-spoofing（大單放又撤）
- multi-account 規避 limit
- broker rebate 申請 volume 不夠就申

## 輸出格式

```markdown
# BB Bybit Policy Audit — <date>

## API key permission audit
| Key | scope | IP whitelist | OK? |

## 4 環境合規
| Env | KYC | endpoint | 政策狀態 |

## Rate limit 30d
| Endpoint | peak rate | limit | % | warning? |

## 禁止行為 risk
- Wash: ...
- Spoofing: ...
- Multi-account: ...

## Bybit changelog 最近 30d
| Date | item | OpenClaw 影響 | 修復狀態 |

## Listing / delisting
| Symbol | event | OpenClaw 25 中? |

## Broker rebate eligibility
30d volume: X / threshold: $10M / eligible: Y/N

## OpenClaw 政策 review 清單
| Item | 狀態 |

## 結論
PASS / Conditional（X 個項目修）/ FAIL（CRITICAL）

BB AUDIT DONE: <report_path>
```
