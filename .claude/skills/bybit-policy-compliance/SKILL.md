---
name: bybit-policy-compliance
description: BB agent 主用：新 Bybit endpoint/功能接通前合規 review、API 鎖/帳戶異常、rate limit 警報、政策公告變動、新地區部署評估時讀（微結構歸 crypto-microstructure-knowledge）。
allowed-tools: Read, Grep, Glob, Bash, WebSearch, WebFetch
---

# Bybit Policy Compliance（Bybit 政策合規手冊）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：CEX ToS / KYC / rate limit 通識不在本檔重述；本檔只列本專案的合規 gate、snapshot 漂移警示與 SSOT 指針。official policy 一律以 Bybit 官方來源即時查證（BB 可 WebFetch），本檔 snapshot 不取代官方。

## 何時觸發

- BB 收到「新 endpoint 部署」「API 鎖 / 帳戶問題」「rate limit 警報」「broker rebate 申請」「政策變動公告」
- OpenClaw 接通新 Bybit 功能（如 spot lending / margin trading）前的合規 review
- 新地區 deployment 評估；違反 ToS 的設計 alert

## ★ BB 角色立場

**BB = Bybit 派來的合規 / 政策顧問**：從 Bybit 立場 push back operator 違規設計；涵蓋技術 + 政策 + 程序面；與 `bybit_api_reference.md` 字典手冊配合。

## 1. ToS 關鍵邊界（官方為準）

- **地理禁區動態變動**（2024-2026 已多次調整）：最終以 Bybit 官方 ToS / Restricted Countries 為準；OFAC sanctions 地區 + USA / Mainland China 等常駐名單靠內建知識起步，涉新地區 deployment / KYC 變動 → 立即查官方再決定。**OpenClaw 部署需確認 operator 所在地區 + 帳戶 KYC 地區**
- **禁止行為**（wash trading / spoofing / pump-dump 協同 / multi-account 規避 limit 等通識靠內建知識）。**OpenClaw 設計 review 專項**：
  - Grid trading 同 symbol 同方向密集 order 是否觸 wash trading 紅線（Bybit 用 anti-wash filter，可能 cancel order 而非禁帳）
  - Multi-strategy 同 symbol 反向 order 同時下：不算 wash（不同邏輯起源），但需審計 trace
- **API 用戶協議**：通過 API 的所有交易視為 user 自己的決策（**包括 AI agent**）；key 不可分享；洩漏自負後果；Bybit 保留隨時 revoke 權利
- **KYC**：API key 不能繞過 KYC，account-level 限制照舊；tier 影響出入金 / position size 上限 / listing 申購資格

## 2. API Rate Limit

> ⚠️ 具體數字動態變動（VIP tier / broker partnership 會升）。**verify**：response header `X-Bapi-Limit*`，或 Bybit Rate Limit 官方 doc（`https://bybit-exchange.github.io/docs/v5/rate-limit`）。

- 高量端點（order create / cancel / cancel-all / position list）各有 per-endpoint limit，以官方 doc 即時查
- **OpenClaw 預警閾值**：任何端點 rate ≥ 80% limit → BB warning；≥ 95% → BB critical（會被 throttle / IP ban）
- Limit 升級：VIP tier / Broker partnership（聯繫 Bybit BD）

## 3. Broker Rebate / Market Maker 計劃

> ⚠️ 門檻 / rebate 數字動態變動；申請評估 / eligibility 結論前必先 WebFetch 官方 Broker / Institutional 頁核對，本 skill 不取代官方條款。

OpenClaw 適用：當前不夠資格（單帳戶 size 太小）；未來 scale 後可申。MM 計劃有 quote spread / uptime SLA 義務。

## 4. API Key Management（專案 gate）

- Permission 4 scope：`read` / `trade` / `withdraw`（**OpenClaw 絕不啟用**）/ `transfer`
- Production API key 必設 IP whitelist（改 IP 需 24h 冷靜期 + 2FA）；OpenClaw production 走固定 server IP
- **UTA 升級 one-click 不可逆**；API endpoint 部分變動（已記在 BB-A1~A7 audit 系列）
- Master / Sub account：每 sub 獨立 API key，可用於資產隔離；OpenClaw 可考慮 demo / live 各一 sub

## 5. 公告追蹤節奏

- 來源：Bybit Announcement Page、API Changelog（`https://bybit-exchange.github.io/docs/changelog/v5`）、Trading Rules updates、listing / delisting
- BB 例行：每週掃 changelog 看 deprecated / new endpoint；每月複查 ToS；重大事件後立即追加 audit
- 新 endpoint 進 `docs/references/2026-04-04--bybit_api_reference.md` 前必走 BB review
- ⚠️ **字典手冊也會漂移**：手冊是 OpenClaw 維護的 mirror，Bybit 官方 changelog 變動後若未 sync → 手冊也是 snapshot。**最終以官方 changelog + 官方 API doc 為準**

## 6. Policy review 清單（空白模板，sub-agent 必查 SSOT 自行填）

OpenClaw 當前 policy compliance 狀態隨 operator 配置 + Bybit 公告變動，**本 skill 不寫死狀態**。

| Item | 檢查命令 / SSOT | 狀態 |
|---|---|---|
| 地理禁區 | operator 確認 KYC 地區 + Bybit ToS 對照 | (sub-agent 填) |
| API permission | Bybit API management UI | (確認 withdraw=false) |
| IP whitelist | production server IP vs API key | (sub-agent 填) |
| UTA endpoint sync | `docs/references/2026-04-04--bybit_api_reference.md` + Bybit changelog | (sub-agent 填) |
| Rate limit | 30d log peak vs limit | (sub-agent 填) |
| Broker rebate | 30d volume vs 官方門檻（§3 disclaimer） | (sub-agent 填) |
| Listing/delisting | Bybit changelog last 30d | (sub-agent 填) |

## 7. 工作流（10 步政策 audit）

1. API key permission 4 項驗（read/trade/withdraw/transfer）→ 2. IP whitelist 確認（production key only）→ 3. KYC tier vs 預期 trading limit 對照 → 4. rate limit 30d statistics（grep limit hit log）→ 5. wash trading risk（grid 同 symbol 密集 order audit）→ 6. withdraw permission 必須關 → 7. Bybit changelog last 30d（deprecated / new endpoint）→ 8. Listing / delisting 新動態 → 9. Broker rebate eligibility（先 WebFetch 核對 §3）→ 10. 產出 BB AUDIT report。

## 穩定平台 + governance rule（不會 drift）

Bybit 為唯一交易所（`CLAUDE.md` Product Boundary；跨所策略 out of scope）；demo/paper/live_demo/live 4 環境合規規則微異（demo no-KYC、live KYC required）；authorization.json HMAC 是 Live gate 5（`CLAUDE.md` Hard Boundaries）；`OPENCLAW_ALLOW_MAINNET=1` 是內部 gate 不替代 KYC；withdraw permission 永遠 false（架構級）；PostOnly 是合規行為（不違 ToS）。

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
- Wash / Spoofing / Multi-account: ...

## Bybit changelog 最近 30d
| Date | item | OpenClaw 影響 | 修復狀態 |

## Listing / delisting
| Symbol | event | OpenClaw 25 中? |

## Broker rebate eligibility
30d volume: X / threshold: <官方即時值> / eligible: Y/N

## OpenClaw 政策 review 清單
| Item | 狀態 |

## 結論
PASS / Conditional（X 個項目修）/ FAIL（CRITICAL）

BB returns an immutable `role_fragment_v1` with `payload_kind=gate_fragment_v1` for the task closure; no broker effect, automatic report, or memory append.
```
