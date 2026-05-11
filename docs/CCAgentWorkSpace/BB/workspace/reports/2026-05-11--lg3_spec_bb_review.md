# BB Review — LG-3 Supervised-Live State Machine Spec v1

**Auditor**: BB (Bybit Broker Compatibility Auditor)
**Date**: 2026-05-11
**Spec**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md` (PA spec v1, 1221 lines)
**Wave**: Sprint N+1 Wave 2.1.5 (QC + BB + MIT parallel review)
**Scope**: Bybit V5 endpoint compatibility + authorization renew flow + WS subscription + rate limit + ToS / KYC / geographic / broker rebate

---

## 1. Verdict — **APPROVE WITH 6 BYBIT CAVEATS**

PA spec v1 在 Bybit 端整合面 **sound**：approval RPC 與既有 `_write_signed_live_authorization()` 端點對接乾淨；WS subscription 不破；rate limit 0 增量；30d Bybit V5 changelog 0 breaking change。**0 ship-stop blocker**。

但對 PA spec v2 final 提 **6 個 caveats**（5 Bybit-specific 必補章節 + 1 mainnet 解鎖 follow-up checklist），不直接阻 IMPL 但 spec v2 必明文回應。

---

## 2. A-G 逐條結論

### A. Bybit V5 endpoint integration

**A.1 LG3-T7 Approval RPC 接 Bybit V5 endpoint inventory**

LG-3 SM transition 觸發的 Bybit V5 endpoint 路徑（從 spec 推導）：

| Spec event | Rust call | Bybit V5 endpoint | Rate group |
|---|---|---|---|
| `approval_granted` → `ACTIVE_PRE_AUTH` | `_write_signed_live_authorization()` | **0 Bybit API call**（純本機檔案寫入 + HMAC sign） | n/a |
| `auth_file_observed` → `ACTIVE_AUTHED` | engine `build_exchange_pipeline()` 啟動 / 繼續 | `GET /v5/account/wallet-balance` + `GET /v5/position/list` + Private WS auth | Account 20 r/s, Position 20 r/s |
| `lease_acquired` → `ACTIVE_TRADING` | `OrderManager::place_order()` per intent | `POST /v5/order/create` | Order 20 r/s |
| `kill_api` / `kill_ipc` → `CLOSED` | cancel pending + close_position + revoke auth | `POST /v5/order/cancel-all` (per symbol) + `POST /v5/order/create` (reduce_only flip side) + 本機 `revoke_live_authorization()` | Order 20 r/s + 本機 |
| `drawdown_breach` → `DRAWDOWN_PAUSE` | 既有 SM-04 path | 同 kill 但走 `revoke_live_authorization()` 自動 | Order 20 r/s |
| `auth_recheck_fail` → `CLOSED` | main.rs 5min re-verify fail → cancel_token | engine graceful shutdown（cancel pending orders if grace window 允許） | Order 20 r/s |

**B-side verdict**：所有觸發的 Bybit endpoint 都在字典手冊 §1.1–§1.3 v1.2 涵蓋；0 新 endpoint；0 deprecated endpoint 觸碰。

**A.2 SM state 切換是否需重訂 WS subscription？**

PA spec §7.5 + §1.2 不顯式提 WS subscription 變動。BB 確認：

- LG-3 SM transition **不變動** WS subscription set
- `BybitEnvironment::private_ws_topics()` 仍由 engine boot 時決定（demo `[order, execution, position, wallet, dcp]` / mainnet `[order, execution.fast, position, wallet, dcp]`）
- `auth_file_observed` → `ACTIVE_AUTHED` 階段 Private WS 已 auth + subscribed；SM state 是 control plane meta，**不觸 WS re-subscribe**
- `kill_api/ipc` → `CLOSED` 階段 engine `cancel_token` 觸發 graceful shutdown 才 close WS connection（per `revoke_live_authorization()` 既有 path）

**B-side verdict**：✅ WS subscription 不受 SM transition 干擾（PA spec §9.2 BB pushback 預期 5 已確認）。

**A.3 WS reconnect 後 SM state 是否安全 resume？**

PA spec 未顯式回應此情境。BB 補：

- WS reconnect 是 `ws_client/run_loop.rs` + `bybit_private_ws.rs` 內部 retry path（指數退避 3-60s）；SM state **不受 WS reconnect 直接影響**
- authorization.json 仍 valid（未過 5min re-verify cycle）→ `ACTIVE_AUTHED/ACTIVE_TRADING` SM state 維持
- 若 WS reconnect 失敗 + authorization.json expired → 5min re-verify fire `auth_recheck_fail` → `CLOSED`

**caveat 1**：spec v2 應明文加 `WS reconnect 不觸 SM transition` 段，避免後續 IMPL 誤判 WS disconnect 為 `auth_file_invalid` event。

**A.4 Rate limit per Bybit V5 spec 受影響？**

LG-3 IMPL 額外 rate 增量（per § 8 task LOC 估算）：

| Surface | 增量 endpoint | Peak rate | 對應 group cap |
|---|---|---|---|
| Approval RPC `/approve` | 0 Bybit call（本機 file write） | n/a | n/a |
| `/kill` | `POST /v5/order/cancel-all` × N symbols + `POST /v5/order/create` × N positions | peak ~5 calls × 25 sym = 125 calls 瞬發但分散到 5-10s | Order 20 r/s × 5s = 100 cap，**邊緣**，建議 batch_wait pattern |
| `[59] [60] [61]` healthcheck | 0 Bybit call（純本機 PG query + file stat） | n/a | n/a |
| Reconciler 30s loop | 0 Bybit call（5 SoT 均本機 source） | n/a | n/a |

**B-side push back 2**：kill scenario 在 25 symbol full universe trading session 觸發時 cancel-all + close-position 可能瞬發 ~125+ Order group calls。Spec v2 應加：

- `/kill` IMPL 必走 `OrderManager::place_order()` 既有 rate_limit_remaining 預檢路徑
- 25 symbol cancel + close 序列化（不並發），允許 ≤10s 完整 kill 時間（per spec §6.3 confirmation flow 不寫 SLA）
- 若 IMPL 不分散 → 風險 Bybit IP rate-limit 403 + 10min cooldown（kill 中 engine 失能更糟）

### B. Authorization renew flow (per CLAUDE.md §四 5min re-verify)

**B.1 authorization.json HMAC 簽名格式仍符 Bybit V5？**

authorization.json 是 OpenClaw **內部 fail-closed 機制**（非 Bybit endpoint）：

- 預存 `version|tier|issued_at_ms|expires_at_ms|operator_id|approved_system_mode|env_allowed_sorted_csv` HMAC-SHA256（per `live_trust_routes.py:57`）
- Bybit V5 對此檔案 **0 認知** — 純 OpenClaw 自我授權 gate
- Bybit V5 真實 API 認證走 `X-BAPI-API-KEY/SIGN/TIMESTAMP/RECV-WINDOW` 4 header（仍 HMAC-SHA256，每 request 簽）

**B-side verdict**：✅ authorization.json HMAC 仍是內部 5-gate invariant 5；Bybit V5 不知不問。

**B.2 SM 5-SoT 同步在 5min re-verify cycle 內可完成？**

PA spec §2.4 reconciler 30s loop interval + connecting 2-cycle 防 false-positive = 60s + 30s = 90s window。**5min re-verify cycle = 300s** → reconciler 至少跑 6-10 cycles before next re-verify fire。

**B-side verdict**：✅ 60s 連 2-cycle disagree detection 完全在 5min re-verify cycle 內；不會與 `auth_recheck_fail` event 競爭。

**B.3 Renew 失敗 → 哪個 SM state？是否與 Bybit endpoint TTL 對齊？**

PA spec §1.2 已 list `auth_recheck_fail` → `CLOSED`（fail-closed）。BB 加：

- LiveDemo authorization.json TTL = operator approve 時設（5min - 8h），與 Bybit V5 API key TTL **完全解耦**
- Bybit V5 API key 無 TTL 概念（操作員手動 revoke），所以 OpenClaw authorization.json 是「自我提醒 + 自我止血」機制
- Renew flow：operator 重打 `/api/v1/live/auth/renew`（既有路徑 per `live_trust_routes.py`）→ 寫新 authorization.json → 下次 5min re-verify pass

**caveat 3**：spec v2 應加章節「LG-3 SM 不直接 IMPL renew；renew 走既有 `live_trust_routes.renew()` 端點，SM 收到 `auth_file_observed` event 後 transition 正常」。避免 LG3-T1 / T3 IMPL 重複 renew logic。

**B.4 operator 手動 revoke 與 Bybit 端 cancel orders 流程整合？**

PA spec §6.3 confirmation flow 已 list 行為：

```
revoke_live_authorization() (per drawdown_revoke same path) →
  audit row written + SSE broadcast + GUI session table updated
```

**B-side push back 4**：spec §6.3 沒 explicit 講 Bybit 端 cancel-all + close-position 何時 fire。Spec v2 應加 explicit flow：

1. operator click kill → 5s countdown → CONFIRM
2. Python `/kill` route：audit row INSERT + IPC `trigger_kill_switch(session_id)`
3. Rust SM：CLOSED 同步 fire 三項並行
   - `POST /v5/order/cancel-all` (per symbol)
   - `POST /v5/order/create` reduce_only flip side (per open position)
   - 本機 `revoke_live_authorization()` (刪 authorization.json + engine cancel_token)
4. 等三項完成 + audit row `action="kill_api"` final + GUI update

**沒做這個 sequence 的後果**：revoke_live_authorization → engine cancel_token → engine 死前 cancel-all 沒 fire → Bybit 端 stale pending orders → **這正是 DCP 設計來止血的 case**（per 字典 §1.6 + gotcha #7）。**DCP 是 fallback，不應依賴**：spec v2 應 explicit 寫 kill 必走 「cancel-all THEN revoke」順序，DCP 是 backup 而非 primary。

### C. Demo vs LiveDemo vs Mainnet 三環境差異

**C.1 PA spec 區分情況**

PA spec §3.1 + §4.1 + §0:

- approval `engine_mode` enum `live` only（spec L31「LiveDemo + 'mainnet pending operator final sign-off' 兩態，**不啟動真實 mainnet 流量**」）
- audit table `engine_mode CHECK (live, live_demo)` — 區分 live 與 live_demo
- spec §0 non-scope 第 4 條：「True live mainnet 訂單路徑 IMPL（仍為 supervised live，LiveDemo + mainnet pending operator final sign-off 兩態）」

**C.2 三環境 SM 行為對比**

| 環境 | Bybit endpoint | Authorization 嚴格 | SM 行為 |
|---|---|---|---|
| **Demo** | `api-demo.bybit.com` | n/a (no signed auth required) | LG-3 SM **不適用**（PA spec §3.3 Gate 2 要求 `live_reserved` 全 mode；Demo runtime 不在此 mode）|
| **LiveDemo** | `api-demo.bybit.com` | authorization.json mandatory (`env_allowed` includes `live_demo`) | LG-3 SM 完整流程；SM 7-state 全 reachable |
| **Mainnet** | `api.bybit.com` | authorization.json mandatory + OPENCLAW_ALLOW_MAINNET=1 + non-empty mainnet slot | LG-3 SM 完整流程；額外 5-gate item 3+4 強制 |

**B-side verdict**：✅ SM 在 LiveDemo / Mainnet 行為「對稱」（per spec §4.1 `engine_mode CHECK` 兩值並列）。spec L31 explicit「mainnet pending operator final sign-off」澄清 LG-3 ship 不解鎖 mainnet 真實流量，本身是 supervised live container。

**caveat 5（已 land in spec）**：spec §3.3 Gate 5 + Gate 6 (cohort awareness + boundary check) 已涵蓋三環境 transition 條件，無補。

### D. Bybit ToS / KYC / geographic risk

**D.1 ToS 對 algorithmic trading 限制（per `bybit-policy-compliance` skill）**

LG-3 IMPL 不引入新 ToS 觸碰點：

- 不變動 wash trading filter（grid_trading 同 symbol 密集 order 仍走既有 anti-wash filter，per BB skill §1.2）
- 不變動 spoofing 風險（OpenClaw 0 大單 quote 放又撤行為，per 既有 IntentProcessor）
- LG-3 SM 是「control plane meta」非「order routing 變動」

**D.2 KYC level 對 max position / max leverage 影響**

PA spec §7.4 EarnedTrust T0-T3 cap 列：
- T0 cap 1 strategy；T1 cap 2；T2 cap 3；T3 cap 5
- T0 max 30 min；T1 60 min；T2 120 min；T3 480 min

**B-side push back 6**：spec §7.4 沒 explicit 講 Bybit KYC tier 上限。例：

- Bybit Tier 0 (no KYC) 對部分 derivatives 0 access — OpenClaw 若無 KYC 帳戶連 LiveDemo Stage 4 都打不通
- Bybit Tier 1 (基本 KYC) 是當前 operator 帳戶級別（per BB memory 2026-05-08 M5-1 仍 outstanding）
- max position notional 受 risk_limit_tier（per BB skill §1）影響：較高 size 觸發較嚴 MMR

**caveat 6（spec v2 必補）**：spec v2 §7.4 EarnedTrust 章節應加 sub-table「Bybit KYC tier 與 EarnedTrust tier cross-ref」：

```
| EarnedTrust tier | Bybit KYC required | Bybit risk_limit_tier impact |
|---|---|---|
| T0 | Tier 0+ | risk_limit base |
| T1 | Tier 1+ | risk_limit base |
| T2 | Tier 2+ (法幣通道) | risk_limit base |
| T3 | Tier 2+ | risk_limit base (notional may upgrade) |
```

approval Gate 7 應 cross-check operator account KYC tier vs request `EarnedTrust.current_tier`。否則 approval pass 但 Bybit 端 retCode=10005 (PermissionDenied) → 該 transition 浪費 + audit row 留 noise。

**D.3 Geographic restrictions（如 US / restricted regions 不可 enable）**

PA spec **完全不提**。BB skill §1.1 列：

- USA + territories（部分產品）
- Mainland China
- Singapore（部分產品 derivatives）
- Canada（部分省）
- Cuba / Iran / North Korea / Syria（OFAC sanctions）
- Crimea / Donetsk / Luhansk
- 其他依各國 regulator 動態（**清單 dynamic，以 Bybit 官方 ToS 為準**）

**LG-3 supervised live 不引入新地區風險**：operator 帳戶所在地 + KYC 地區決定 Bybit-side 可否操作 derivatives；spec 任何 IMPL 都不繞 Bybit 自身 geofencing。

**caveat 6 補充**：M5-1 governance entry 仍是 LG-3 mainnet 解鎖前 mandatory pre-flight。spec v2 §7 + §16 (Compliance Check) 表應 explicit cross-ref M5-1。

**D.4 Broker rebate / market maker eligibility（PostOnly fill ratio 要求）**

LG-3 不變動 PostOnly fill ratio 行為（per A.1 verdict：LG-3 不變動 IntentProcessor / OrderManager / PostOnly）。

當前 OpenClaw 30d volume ~$45K << $10M broker rebate threshold（per BB memory 2026-05-08）。LG-3 supervised live 不增大 volume（risk_limits cap ≤ P1 ceiling 由 spec §5.1 強制 min-only formula）。

**B-side verdict**：✅ broker rebate / market maker eligibility 完全不受 LG-3 影響。

### E. Bybit API changelog drift 風險

**E.1 字典手冊 (2026-04-04 v1.2) vs 今天 2026-05-11 1 月+ drift**

繼承 BB v3 (2026-05-10) audit + WebSearch 結果（changelog 來源：[Bybit V5 changelog](https://bybit-exchange.github.io/docs/changelog/v5)）：

- 30d Bybit V5 changelog 0 breaking change（v3 verify 維持）
- 新欄位：`takerVol30Day` `makerVol30Day` `tradeVol30Day` 等（fee-rate-related，OpenClaw serde(default) 兼容）
- 新 topic：替換舊 `liquidation`（per-1s push）為 full liquidation feed — OpenClaw allLiquidation handler 2026-04-06 刪除（per BB v3 NEW-6），W-AUDIT-8c 復活時必走 W-AUDIT-8a Phase C+1 sprint
- 新 enum：`stopOrderType` 加 `OcoOrder` — OpenClaw 0 use spot OCO
- 新 enum：`timeInForce` 加 RPI Order — OpenClaw 0 use RPI
- 新 endpoint：Fund Custodial sub acct list / BYUSDT Advanced-Earn DualAssets — OpenClaw 0 use

**B-side verdict**：✅ LG-3 spec 內所有 endpoint 仍 valid，0 deprecated 觸碰。

**E.2 LG-3 IMPL 用到的 Bybit endpoint 是否仍有效？**

per A.1 inventory 表，LG-3 觸發的 5 endpoint:

| Endpoint | 字典手冊 v1.2 |
|---|---|
| `POST /v5/order/create` | ✅ line 306 + line 1054 active |
| `POST /v5/order/cancel-all` | ✅ line 389 active |
| `GET /v5/account/wallet-balance` | ✅ line 638 active |
| `GET /v5/position/list` | ✅ line 502 active |
| Private WS auth + `order, execution, position, wallet, dcp` | ✅ line 1000 active |

**B-side verdict**：✅ 5/5 endpoint 仍 active，無 drift。

**E.3 你建議 PA spec v2 加哪些 Bybit 端 latest changelog check？**

**caveat（meta-spec recommendation）**：spec v2 §13.4 Wave 2.4 IMPL phase 應加一條「LG3-T1 / T3 / T5 IMPL pre-flight」：

> 在 LG3-T1 / T3 / T5 IMPL 啟動前（Wave 2.4 Phase 1/2 開始），E1 或 BB 自跑 `WebSearch site:bybit-exchange.github.io changelog v5 2026-05-11..今天`，confirm 0 breaking change since 字典 v1.2 + BB v3 audit baseline 2026-05-09。發現 breaking 立即 push back 暫停 IMPL。

當前 (2026-05-11 BB review time) verify：0 breaking change。

### F. Mainnet 解鎖 path 風險

**F.1 PA spec §硬邊界 acknowledge mainnet 仍封閉，但 LG-3 enabled 後 mainnet path 是否「near-ready」？**

從 BB Bybit-side 視角，LG-3 enabled 後：

| Item | LiveDemo 狀態 | Mainnet 額外 gap |
|---|---|---|
| LG-3 SM IMPL | LG3-T1..T7 land 後 reachable | **0 gap（code path identical）** |
| 5-gate boundary | gate 1+2+4+5 強制 (gate 3 OPENCLAW_ALLOW_MAINNET n/a for LiveDemo) | gate 3 OPENCLAW_ALLOW_MAINNET=1 + gate 4 non-empty mainnet slot |
| authorization.json env_allowed | `live_demo` only | `mainnet` only（per `live_trust_routes._current_bybit_endpoint_label()`）|
| API key permission | demo key | mainnet key（withdraw=false強制 + IP whitelist 強制）|
| Bybit account KYC | demo 不需 | Tier 1+ KYC required |
| Geographic | demo 不限 | 受 ToS §1.1 限制 |
| Broker rebate eligibility | 不適用（demo 0 volume） | 30d $10M threshold（gap 222×） |
| risk_limit_tier on mainnet | n/a | base tier，size scale up 觸 MMR 收縮 |

**B-side verdict**：✅ LG-3 IMPL 後 code path 90%+ share LiveDemo + Mainnet；剩餘 10% 差是 5-gate boundary 既有強制 + KYC + IP whitelist + 帳戶設定 — 完全 LG-3 外部。

**F.2 後續 mainnet 啟用前還需哪些 BB 工作？**

**caveat 7（Mainnet 解鎖前 BB review checklist，spec v2 §15.4 加）**：

1. **M5-1 governance entry**：`docs/governance_dev/2026-05-11--bybit_compliance_signoff.md` 必建檔（KYC tier + 地理 + API permission + IP whitelist 6 項 operator 自證）
2. **M5-2 IP whitelist preflight**：`helper_scripts/preflight/check_bybit_ip_whitelist.py` 必 IMPL，restart_all 啟動時跑（mainnet only）
3. **mainnet API key 配置驗證**：withdraw=false（架構級不變式）+ trade=true + read=true + IP whitelist set（24h cool-down 後生效）
4. **首日 mainnet runbook**：P0-OPS-4 仍 outstanding，BB review 切 mainnet 前 mandatory
5. **mainnet authorization.json env_allowed=['mainnet']** 與 LiveDemo `['live_demo']` 必 explicit 分隔（既有 `live_trust_routes._current_bybit_endpoint_label()` 已 handle）
6. **首日 limit**：spec v2 §7.4 EarnedTrust T0 30min cap + 1 strategy + 1 symbol cohort = mainnet 首日 ship 上限
7. **mainnet 切 LiveDemo 切換不可 hot-swap**：spec v2 應 explicit 寫 SM 重啟 + authorization re-issue 才能切環境（已 implicit per `_current_bybit_endpoint_label` engine-boot 讀取）
8. **broker partnership eligibility check**：每月 BB 例行驗（per BB skill §6.2），mainnet ramp-up 後 30d 內第一次跑

### G. Broker rebate / Maker incentive 配置

**G.1 W-C P-1.6 期間 maker fill rate 100% (n=6) — 是否合 Bybit 銀牌 / 金牌 market maker 條件？**

per BB skill §4.2:
- 條件：maker volume ≥ $50M / 30d + maker ratio ≥ 60%

OpenClaw 當前狀態:
- 30d volume ~$45K << $50M threshold（1100× gap）
- maker fill rate per [33] healthcheck 89.6%（per CLAUDE.md §三 active gates）— **滿足 60% maker ratio**，但 volume 完全不夠

**B-side verdict**：banner mainnet ramp-up 後可能逐步合格，但 LG-3 ship 本身不貢獻 volume increase（risk_limits min-only formula 確保不擴大）。

**G.2 BB 視角看 PA spec 是否需強化 PostOnly path 防降級**

PA spec §0 non-scope 第 4 條 explicit「不啟動真實 mainnet 流量」+ §15.1 16 原則 4「策略不繞風控」session_override min-only。**PostOnly path 不在 LG-3 IMPL 範圍**（仍由既有 IntentProcessor / OrderManager handle）。

**B-side verdict**：✅ PostOnly path 完全不受 LG-3 影響；W-C [33] 89.6% maker ratio 維持 + funding_arb retire 後不再被 BUSDT taker reject loop 拉低，Sprint N+1 不變。

---

## 3. Bybit V5 endpoint 對齊（spec v1 vs 字典手冊 v1.2）

| LG-3 觸發 endpoint | 字典 v1.2 位置 | 對齊 | Rate group | LG3-T# |
|---|---|---|---|---|
| `POST /v5/order/create` | line 306 + line 1054 (paper shadow) | ✅ | Order 20 r/s | T5 (`/kill` close_position) |
| `POST /v5/order/cancel-all` | line 389 | ✅ | Order 20 r/s | T5 (`/kill` cancel pending) |
| `GET /v5/account/wallet-balance` | line 638 | ✅ | Account 20 r/s | engine boot post auth_file_observed |
| `GET /v5/position/list` | line 502 | ✅ | Position 20 r/s | engine boot + reconcile |
| Private WS `order, execution, position, wallet, dcp` | line 1000-1015 | ✅ | n/a (WS) | engine boot |
| `POST /v5/order/disconnected-cancel-all` (DCP fallback) | line 781 | ✅ | Other 10 r/s | n/a (kill 故意不依賴) |

**0 drift / 0 deprecated endpoint / 0 missing entry**.

---

## 4. ToS / KYC / geographic 風險

| Risk | LG-3 IMPL 引入新風險？ | 緩解 |
|---|---|---|
| ToS algorithmic trading 限制 | ❌ 不引入 | 既有 anti-wash + 不變動 spoofing 行為；LG-3 是 meta 不是 routing 變動 |
| KYC tier 對 max position / leverage | ⚠️ spec 未顯式 cross-ref Bybit KYC tier | **caveat 6**：spec v2 §7.4 EarnedTrust 加 KYC tier cross-ref + approval Gate 7 |
| Geographic restrictions | ❌ 不引入新地區 | M5-1 governance entry 仍 outstanding（Mainnet 解鎖前 mandatory） |
| Broker rebate / market maker | ❌ 不引入；當前 30d $45K << $10M threshold | 自然 ramp-up 後例行驗（per BB skill §6.2） |
| API key withdraw permission | ❌ 永遠 false（架構級不變式） | 不變 |
| IP whitelist | ⚠️ M5-2 preflight 工具 IMPL 仍欠 | **caveat 7**：mainnet 解鎖前 mandatory |
| Multi-account 規避 limit | ❌ 不引入 | LG-3 是 session-level per-operator scope，無 multi-account |
| Anti-spoofing（大單放又撤） | ❌ 不引入 | 不變 |

---

## 5. 給 PA spec v2 必補事項

### caveat 1（MEDIUM）— A.3 WS reconnect 不觸 SM transition

**位置**：spec v2 §7 Integration Points 新增 §7.6

**文字（建議）**：
```
### 7.6 WS reconnect 不觸 SM transition

WS reconnect 是 `ws_client/run_loop.rs` + `bybit_private_ws.rs` 內部 retry path
（指數退避 3-60s）；LG-3 SM state 不受 WS reconnect 直接影響。
若 WS reconnect 失敗 + authorization.json expired → 5min re-verify fire
`auth_recheck_fail` event → CLOSED（既有 path）。
WS connection 斷開單獨不觸 `auth_file_invalid` event。
```

### caveat 2（HIGH）— A.4 `/kill` 必走 batch_wait rate-limit pattern

**位置**：spec v2 §6 GUI Kill Button 新增 §6.6 / §1.2 transition table 加註

**文字（建議）**：
```
### 6.6 Kill Rate-Limit Pattern

`/kill` IMPL 必走 `OrderManager::place_order()` 既有 rate_limit_remaining
預檢路徑。25 symbol cancel + close 序列化（不並發），允許 ≤10s 完整 kill 時間。

順序：
1. for each symbol in session.symbols（依 ASCII sort）：
   - POST /v5/order/cancel-all (per symbol)
   - if open position exists: POST /v5/order/create (reduce_only flip side)
   - wait 0.3s（per Bybit Order group 20 r/s × 0.3s safety margin）
2. revoke_live_authorization() (本機檔案刪)
3. engine cancel_token fire（graceful shutdown）
4. audit row action="kill_api" final + GUI update

禁止：並發發出 25 cancel + 25 close = 瞬發 50 calls 超 Order group 20 r/s
× 5s cap (~100)
觸發 IP rate-limit 403 + 10min cooldown 風險。DCP 是 fallback 而非 primary。
```

### caveat 3（LOW）— B.3 Renew flow 走既有 endpoint

**位置**：spec v2 §3 Approval RPC 新增 §3.6

**文字（建議）**：
```
### 3.6 Renew Flow Clarification

LG-3 SM 不直接 IMPL renew；renew 走既有 `live_trust_routes.renew()` 端點
（`_write_signed_live_authorization()` 同 path）。
SM 收到 LiveAuthWatcher 觀察的 `auth_file_observed` event 後 transition
ACTIVE_PRE_AUTH → ACTIVE_AUTHED 正常。

LG3-T1 / T3 / T5 IMPL 不重複 renew logic。
若 operator 需 extend session：當前 active session 內無法 renew TTL；
需 kill → new approve（per spec §3.5 anti-pattern guard）。
```

### caveat 4（HIGH）— B.4 Kill 順序 explicit

**位置**：spec v2 §6.3 confirmation flow + §1.2 `kill_api` row Side Effects 加註

**文字（建議）**：合併到 caveat 2 §6.6 sequence 中。額外 §6.3 改：

```
revoke_live_authorization() 必在 cancel-all + close-position 完成後 fire。
**禁止**：先 revoke → engine cancel_token → cancel-all 沒 fire → DCP fallback 救場。
DCP 是 backup 而非 primary。Operator 視 DCP fire 為 "kill 沒做完整"，
應觸發 RCA。
```

### caveat 5（MEDIUM）— D.2 Bybit KYC tier 與 EarnedTrust tier cross-ref

**位置**：spec v2 §7.4 EarnedTrust 接入 加 sub-table + approval Gate 7 加

**文字（建議）**：
```
### 7.4 EarnedTrust T0-T3 接入（追加 Bybit KYC cross-ref）

per BB push back caveat 6：approval Gate 7 必 cross-check operator Bybit
KYC tier vs request `EarnedTrust.current_tier`。

| EarnedTrust tier | Bybit KYC required (minimum) | Bybit risk_limit_tier 影響 |
|---|---|---|
| T0 | Tier 0+ (any) | risk_limit base |
| T1 | Tier 1+ (基本 KYC) | risk_limit base |
| T2 | Tier 2+ (進階 KYC) | risk_limit base |
| T3 | Tier 2+ | risk_limit base (notional may upgrade) |

Gate 7（新增）位置在 §3.3 approval 流程 Gate 6 之後：

```python
# Gate 7: Bybit KYC tier vs EarnedTrust tier cross-ref
kyc_tier = await query_bybit_kyc_tier()  # GET /v5/user/query-api permissions or cache
trust_tier = earned_trust_engine.get_state_snapshot().current_tier
if kyc_tier < REQUIRED_KYC_TIER[trust_tier]:
    raise HTTPException(403, detail={
        "reason_codes": ["bybit_kyc_tier_below_trust_tier_requirement"]
    })
```

Reason code: `bybit_kyc_tier_below_trust_tier_requirement`。
```

### caveat 6（HIGH）— F.2 Mainnet 解鎖前 BB review checklist

**位置**：spec v2 §15.4 新增（補充 hardboundary 5 項）

**文字（建議）**：
```
### 15.4 Mainnet 解鎖前 BB Mandatory Checklist

LG-3 ship 後 LiveDemo + mainnet code path 90%+ share。Mainnet 真實流量
啟動前 BB review mandatory 8 項：

1. M5-1 governance entry: `docs/governance_dev/<date>--bybit_compliance_signoff.md` 建檔
   （KYC tier + 地理 + API permission + IP whitelist + ToS 6 項 operator 自證）
2. M5-2 IP whitelist preflight: `helper_scripts/preflight/check_bybit_ip_whitelist.py` IMPL + restart_all 啟動跑
3. mainnet API key: withdraw=false 強制 + trade=true + read=true + IP whitelist set（24h cool-down 後生效）
4. P0-OPS-4 首日 runbook 收口
5. mainnet authorization.json env_allowed=['mainnet'] 與 LiveDemo `['live_demo']` explicit 分隔
   （既有 `live_trust_routes._current_bybit_endpoint_label()` 已 handle，無補）
6. 首日 limit 在 spec §7.4 T0 30min cap + 1 strategy + 1 symbol cohort 內
7. mainnet 切 LiveDemo 不可 hot-swap，必 engine restart + authorization re-issue
8. broker partnership eligibility 例行驗（每月，per BB skill §6.2）—
   mainnet ramp-up 30d 內第一次跑

BB 在 mainnet 解鎖前最終發 final audit report 確認 8/8 closed。
```

### caveat 7（LOW，meta-spec）— E.3 Wave 2.4 IMPL pre-flight changelog 自查

**位置**：spec v2 §13.4 Wave 2.4 IMPL phase 加一句

**文字（建議）**：
```
### 13.4 Wave 2.4 IMPL Pre-flight

每個 LG3-T# IMPL 啟動前（Phase 1 / Phase 2 / Phase 3 各前），E1 或 BB
自跑 changelog drift check：

```bash
WebSearch site:bybit-exchange.github.io changelog v5 <baseline_date>..<today>
```

baseline_date = 字典手冊 v1.2 ship 日 (2026-04-26 G9-01 audit + 2026-05-08 BB)。
發現 breaking change 立即 push back 暫停 IMPL，BB ad-hoc audit。

當前 (2026-05-11 BB review time) verify: 0 breaking change since baseline。
```

---

## 6. Mainnet 解鎖前 review checklist（彙總，per caveat 6 + 全 spec 整合）

| # | 項目 | 當前狀態 | 責任方 | spec v2 cross-ref |
|---|---|---|---|---|
| 1 | M5-1 governance entry (KYC + 地理 + API permission + IP whitelist + ToS) | 0 進展（>12 day stale） | Operator | §15.4 item 1 |
| 2 | M5-2 IP whitelist preflight 工具 IMPL + restart_all 接線 | 0 進展（>12 day stale） | E1 / Operator | §15.4 item 2 |
| 3 | Mainnet API key 配置（withdraw=false + IP whitelist 24h cool-down） | TBD | Operator | §15.4 item 3 |
| 4 | P0-OPS-4 首日 mainnet runbook | outstanding | PM / TW | §15.4 item 4 |
| 5 | mainnet authorization.json env_allowed=['mainnet'] vs LiveDemo `['live_demo']` 分隔 | ✅ 既有 code handle | E1 | §15.4 item 5 |
| 6 | 首日 limit T0 cap | LG-3 IMPL 後 enforced | E1 + Operator | §7.4 + §15.4 item 6 |
| 7 | mainnet 切 LiveDemo restart 規程 | LG-3 IMPL 後 enforced | E1 / Operator | §15.4 item 7 |
| 8 | broker partnership eligibility 例行驗 | 當前 30d $45K << $10M（自然不合格） | BB monthly | §15.4 item 8 |
| 9 | BB final mainnet audit report | LG-3 IMPL + 8/8 closed 後 | BB | §15.4 final |

---

## 7. BB 採納驗證對 PA spec v1

PA spec §9.2 BB pushback 預期 2 條 (BB-Approve-with-2-caveat-preview）：

1. ✅ "supervised live 但 LiveDemo endpoint vs mainnet endpoint 區分" — spec 答對：approval `engine_mode="live"` 對齊既有區分機制（authorization.json env_allowed），不強制單一
2. ✅ "kill 後 Bybit 仍有 pending order race window" — spec 答對：cancel + close best-effort + audit row 完整反映 + 後續 reconciler 觸發。**但 BB 補 caveat 2 + 4** 要求 spec v2 必明文 batch_wait 順序 + cancel-then-revoke 順序，DCP 是 backup 不是 primary。

PA spec §11 (Risk + Mitigation) 11.1-11.8 8 條風險全 cover；BB 補一條 §11.9：

> **11.9 (中) Kill 序列化 vs Bybit rate-limit 競爭**
>
> - **Mitigation 1**：cancel-all + close-position 序列化 per symbol（per caveat 2 §6.6）
> - **Mitigation 2**：每 step 0.3s safety margin 在 Order 20 r/s 之內
> - **Mitigation 3**：DCP 為 fallback 不為 primary kill mechanism

---

## 8. Final Verdict

**APPROVE WITH 6 BYBIT CAVEATS**：

PA 可進 spec v2 final + 後續 Wave 2.4 IMPL，**只要 spec v2 明文涵蓋 6 個 caveats**：

| # | 嚴重度 | 章節位置 | 補完工 |
|---|---|---|---|
| 1 | MEDIUM | §7.6 new | WS reconnect 不觸 SM |
| 2 | HIGH | §6.6 new + §1.2 行更新 | Kill batch_wait pattern |
| 3 | LOW | §3.6 new | Renew 走既有 endpoint |
| 4 | HIGH | §6.3 改 | Cancel-all THEN revoke 順序 |
| 5 | MEDIUM | §7.4 改 + §3.3 Gate 7 加 | KYC tier cross-ref |
| 6 | HIGH | §15.4 new | Mainnet 解鎖前 8 項 checklist |
| 7 (meta) | LOW | §13.4 改 | Pre-flight changelog 自查 |

當前 (2026-05-11 BB review time) 30d Bybit V5 changelog 仍 0 breaking change，字典 v1.2 vs PA spec v1 endpoint reference 100% align。LG-3 不引入新地區 / KYC / API permission / broker rebate 風險。

**0 ship-stop blocker**；**0 endpoint deprecation 觸碰**；**WS subscription 不破**；**rate limit 0 增量除 kill scenario**；**5-gate live boundary 不放寬**。

---

## 9. 下次 BB 啟動需查驗項

1. PA spec v2 是否採納 6 個 caveats（特別 caveat 2 + 4 HIGH 必接）
2. Wave 2.4 IMPL 啟動前 Bybit V5 changelog 0 breaking change verify（per caveat 7）
3. LG3-T5 IMPL `/kill` 序列化是否真用 0.3s safety margin（per caveat 2）
4. LG3-T3 approval Gate 7 是否加 Bybit KYC tier check（per caveat 5）
5. spec v2 §15.4 Mainnet 解鎖 8 項 checklist 是否完整入 spec
6. M5-1 / M5-2 進展（仍 12+ day 0 進展，mainnet 解鎖 mandatory）

---

**BB AUDIT DONE**: srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-11--lg3_spec_bb_review.md


---

## Sources

- [Bybit V5 API Documentation](https://bybit-exchange.github.io/docs/v5/intro)
- [Bybit V5 Changelog](https://bybit-exchange.github.io/docs/changelog/v5)
- [Bybit V5 Error Codes](https://bybit-exchange.github.io/docs/v5/error)
- 字典手冊 v1.2: `/Users/ncyu/Projects/TradeBot/srv/docs/references/2026-04-04--bybit_api_reference.md`
- 歷史 audit baseline: `/Users/ncyu/Projects/TradeBot/srv/docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 上次 BB report (Sprint N+0): `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-10--sprint_n0_final_bybit_compatibility_review.md`
- PA spec v1: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md`
- W-C lease router authorization: `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`
