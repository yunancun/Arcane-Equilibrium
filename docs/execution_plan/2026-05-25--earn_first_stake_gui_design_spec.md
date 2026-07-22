---
spec: Earn first stake GUI design — Layer 1 Bybit Earn-only mainnet first stake 的 governance tab 介面
date: 2026-05-25
author: PA agent (Sprint 1B Earn Wave C carry-over「GUI scope 仲裁」)
phase: Sprint 1B late Pending 3.2 Earn Wave C — EARN-FIRST-STAKE-GUI-DESIGN-DRAFT
status: DRAFT-PA-DESIGN
parent specs:
  - srv/docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md §5 §7.10 §8
  - srv/docs/execution_plan/2026-05-21--earn_governance_spec.md §2 §3 (5-gate / IntentProcessor / EarnIntentPayload schema)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md §7.3 (Wave B E1a GUI 8-12 hr sub-task)
  - srv/rust/openclaw_engine/src/intent_processor/earn_router.rs (9-gate E-0..E-9 IMPL contract)
  - srv/rust/openclaw_engine/src/bybit_earn_client.rs (5 endpoint: products / place-order × 2 / position / apr-history)
  - srv/.claude/skills/gui-style-guide/SKILL.md (Vanilla JS / 既有 README-listed tab / 中文界面 / a11y)
  - srv/.claude/skills/ux-checklist/SKILL.md (5 維度 / 防誤等級表 / 打字確認模式)
related ADRs:
  - ADR-0032 Bybit Earn asset movement Guardian
  - ADR-0034 Decision Lease Layered Approval LAL
scope: GUI design / spec / 不寫 code / 不執行 / 不改 schema 實檔
not in scope:
  - 後續 stake / redeem / reparam GUI flow (Sprint 5+;本 spec 鎖 first stake only)
  - Earn dashboard 高級視覺 (APY 走勢圖 / cumulative accrual chart;Sprint 5+)
  - Layer 2 Earn Auto-Allocator GUI (Sprint 5+;§5.2 (d) Auto-Allocator activation N/A)
  - operator OP-1 Bybit Web UI key 重發 walkthrough (operator 行為,非 GUI scope)
---

# Earn First Stake GUI Design Spec — Layer 1 Mainnet Earn-only GUI Scope

## §1 Status + Date + Author + Trigger

| Element | Value |
|---|---|
| Status | DRAFT-PA-DESIGN (等待 A3+QA cross-ref + operator OQ 拍板) |
| Date | 2026-05-25 |
| Author | PA agent (Sprint 1B Earn Wave C carry-over「GUI scope 仲裁」) |
| Trigger | operator 拍板 Earn first stake 上線 (Layer 1 Bybit Earn-only mainnet key + GUI 同時 IMPL);Stage 0R Earn variant spec §7.10 提到「GUI Earn governance tab → type-to-confirm $100-200 USDT FlexibleSaving」但未詳描 IMPL 細節,需本 spec 設計 GUI scope |
| Supersedes | 無 (Sprint 1B 首次 Earn first stake GUI 設計) |
| Related governance | earn_governance_spec.md §2 (5-gate) + §3.2 (EarnIntentPayload schema) + Stage 0R Earn variant spec §5 (5-gate inheritance) + §7.10 (operator first stake walkthrough) |

### 1.1 為什麼需要本 spec

Stage 0R Earn variant spec §7.10 line 540-549:

```
GUI Earn governance tab → type-to-confirm $100-200 USDT FlexibleSaving
→ 5-gate 全 PASS → IntentProcessor EARN_STAKE branch → bybit_earn_client.subscribe_flexible
→ V100 earn_movement_log INSERT placeholder → Bybit API ack → UPDATE outcome
→ Linux PG empirical query SELECT * FROM learning.earn_movement_log ORDER BY created_at DESC LIMIT 1
→ AC-3 PASS
```

該段為「IMPL walkthrough 一行」,但缺:
- GUI 位置決策 (新 tab vs governance section vs live tab)
- UI 元素 scope (account balance / products list / stake form / 5-gate panel / positions / history)
- FastAPI route schema (路徑 + auth gate + payload + 寫操作鏈)
- 5-gate UI 可視化方案 (5 lights / status grid / detail drawer)
- 防誤觸 mechanism (typed-confirm phrase + cooldown + role re-auth)
- Stage 0R preflight 與 GUI 整合 (preflight pending status / JSON ref attach)
- E1 / E1a 分工與 parallel/sequential 順序

本 spec 補齊以上,為 Wave C IMPL dispatch 解封口。

### 1.2 對齊既有 governance / earn 框架

| 維度 | 對齊 |
|---|---|
| Tab 系統 | `console.html` TABS 陣列「governance」group (per `tab-governance.html`);Earn 為治理對象 (operator-bound asset write),不為交易 (trading group) 或 ops |
| 寫操作 fail-closed | 走既有 `_require_operator_role` (governance_routes.py:331) + `live_reserved` Global Mode 同步 (live_session_routes.py:16 dual gate pattern) |
| 5-gate API | IntentProcessor 後端已 IMPL 9-gate (E-0..E-9 per earn_router.rs);GUI 只負責 (1) 前端可視化 status (2) submit 後 dispatch 真實 9-gate |
| typed-confirm | 既有 `openTypedConfirmModal()` (common-modals.js:339) 已支援 phrase + actor + impact + rollback;本 spec 直接復用,不新建 modal |
| EarnIntentPayload | 對齊 earn_governance_spec §3.2 (intent_id / intent_type / amount_usdt / direction / expected_apr_bps / approval_id / actor_id / submitted_ts / rationale 9 field) |

---

## §2 GUI 位置決策

### 2.1 三 candidate 對比

| Candidate | 位置 | Pros | Cons | Verdict |
|---|---|---|---|---|
| **(A) 新建 `tab-earn.html`** | TABS 陣列加新 entry,group='governance' 或新 'earn' group | 獨立空間;UI 元素全展開不擠;後續 Sprint 5+ Earn 範圍擴張 (multi-product / cross-product / Auto-Allocator) 不需重組 | 16 tab → 17 tab 認知負荷 +6%;Sprint 1B 範圍只 first stake,獨立 tab 顯得「未充滿」;與其他 governance tab 切換摩擦 | **採納** (條件:Sprint 1B 鎖最小 UI;Sprint 5+ 擴展) |
| (B) `tab-governance.html` 加 Earn section | governance tab 加 `<details>` collapsible 區塊 | 0 新 tab;與 5-gate / Decision Lease 同 tab 上下文連貫 | governance tab 已 1700+ LOC (per `wc -l` 已知);加 Earn ~300+ LOC 會觸及現行 2000 行門檻;認知負荷高 (canary / 5-gate / lease / decision-lease / earn 五個 sub-section);Sprint 5+ Earn 擴張會破 cap | **拒絕** (LOC + cognitive load) |
| (C) `tab-live.html` 加 Earn section | live tab 加 Earn balance section | Earn 真實主帳本 (USDT) 與 live trading 同位;operator 視覺一致「真實資金面」 | live tab 已 1500+ LOC + dust / orders / fills / readiness 多元素;加 Earn section 與 trading 元素互相干擾;Earn ≠ trading,語意混淆;不適合 first stake 階段 0 倉位的「空狀態」展示 | **拒絕** (語意 + LOC) |

### 2.2 採納 (A) 的理由 + Mitigation

**採納 (A) 新建 `tab-earn.html`**,理由:

1. **語意一致**:Earn 是 asset write event (per earn_governance §1.1),屬「治理對象」非「交易對象」;新 tab 對齊 16 原則 #2 讀寫分離 + GUI tab 各自單一職責
2. **LOC 健康**:獨立 tab ~500-700 LOC (per §3 元素 scope) 遠低於現行 2000 行門檻;不污染既有 1700+ LOC governance tab
3. **擴展性**:Sprint 5+ 加 stake/redeem/reparam variant + APY tracker + cross-product allocator GUI 不破壞既有 tab;單一 Earn tab 線性增長
4. **認知負荷**:operator 進 Earn tab 之前已知「我在做 Earn 操作」,不需在 governance tab 內子 section 切換找入口;對齊 ux-checklist 2.1「單頁 ≤ 7 個關注點」

**Mitigation** 認知負荷 +6%:
- Sprint 1B 鎖最小 UI (§3 列 7 sections,每 section ≤ 1 屏);保證即使 17 tab 切換,Earn tab 內部資訊密度低
- Earn tab 加入 group `'governance'` (per console.html TABS line 363 governance group 既有 mapping);不新建 group,保留 6 group 結構 (TAB_GROUP_LABELS line 317)
- icon 用 `💰` (money bag,語意對齊 Earn = staking yield;與既有 16 個 icon 不衝突)
- label = `Earn 理財`,labelEn = `Earn`

### 2.3 console.html TABS 陣列補丁 (示意 — E1a Wave C IMPL)

```javascript
// console.html line 350-376 TABS 陣列加新 entry (位置:governance group 內,Risk 之後)
{ id: 'earn',       group: 'governance', label: 'Earn 理財',       labelEn: 'Earn',      icon: '&#x1F4B0;', src: `/static/tab-earn.html?v=${_v}` },
```

不破壞既有 16 tab 順序;新 tab 加在「治理 governance」group (line 362 risk → line 363 governance → 新 earn → 364 ai)。

---

## §3 UI 元素詳列 (First Stake Scope)

### 3.1 7 sections (上→下)

```
┌──────────────────────────────────────────────────────────────────────┐
│ §3.1 標頭橫條 (header bar)                                            │
│   Earn 理財 | Live / Demo 標識 | engine_mode | refresh button          │
├──────────────────────────────────────────────────────────────────────┤
│ §3.2 Earn 帳戶餘額 (account balance card)                              │
│   USDT Earn balance | total claimable yield | last reconciliation ts  │
├──────────────────────────────────────────────────────────────────────┤
│ §3.3 5-gate status panel                                              │
│   5 light (a/b/c/d/e) + detail expand + last check ts                 │
├──────────────────────────────────────────────────────────────────────┤
│ §3.4 Available products list (Flexible only)                          │
│   table:productId / coin / estimateApr / minStake / maxStake / status  │
├──────────────────────────────────────────────────────────────────────┤
│ §3.5 First stake form (write surface;受 5-gate gate)                  │
│   coin select (USDT only) + productId (auto-pick) + amount input       │
│   ($100-200) + expected_apr_bps (auto) + rationale textarea + submit  │
├──────────────────────────────────────────────────────────────────────┤
│ §3.6 Active positions (current stakes)                                │
│   table:productId / amount / totalPnl / claimableYield / status        │
├──────────────────────────────────────────────────────────────────────┤
│ §3.7 Records history (audit log)                                      │
│   table:ts / direction / amount / apr / outcome / lease_id / movement │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 各 section 詳細 spec

#### §3.1 Header bar (~50 LOC)

| 元素 | 規格 |
|---|---|
| Title | `💰 Earn 理財` (中文主) + `Earn` (en sub) |
| Env badge | `Live` (red-gold) / `LiveDemo` (orange) / `Demo` (orange) — `bybit_env` field from `/api/v1/earn/status` |
| Engine mode | `live` / `live_demo` / `demo` — 對齊 V100 schema CHECK 4 enum |
| Refresh button | 點擊重新拉 §3.2-§3.7 五端點;15s auto-refresh (同 console.html sidebar 慣例) |
| Status footer | `採集時間:<UTC> <local>` (對齊 ux-checklist 2.5 audit-aware footer) |

#### §3.2 Earn 帳戶餘額 (~60 LOC)

| 元素 | 規格 | API source |
|---|---|---|
| USDT Earn balance | Decimal (2 位) | `GET /api/v1/earn/balance` |
| Total claimable yield | Decimal (4 位) | 同上 |
| Last reconciliation ts | UTC + local 雙標 | 同上 (Daily cron 02:00 UTC 對賬最新 row) |
| Reconciliation status badge | `ok` / `mismatch` / `mismatch_critical` (per earn_governance §6.2) | 同上 |

**空狀態 (first stake 前)**:USDT Earn balance = `0.0000` + claimable yield = `0.0000` + reconciliation status = `pending_first_stake` (灰色 badge,提示 operator 尚未首次 stake)。

#### §3.3 5-gate status panel (~120 LOC)

| 元素 | 規格 | UI 視覺 |
|---|---|---|
| Gate (a) Operator role auth | `✅` (PrimaryOperator/BackupOperator) / `❌` (其他) | 綠燈 / 紅燈 + tooltip 顯 actor_id |
| Gate (b) Signed authorization.json | `✅` (HMAC valid + not expired + earn-write scope) / `❌` | 同上 + tooltip 顯 authz_id + expiry ts |
| Gate (c) OPENCLAW_ALLOW_MAINNET | `✅` (env=live 且 =1) / `N/A` (env=demo;per earn_governance §4.5 條件 A) / `❌` | 三狀態 (綠/灰/紅) |
| Gate (d) Bybit secret slot | `✅` (slot 有 earn scope 且 < 6 mo lifetime) / `⚠️` (close to expiry) / `❌` | 三狀態 + tooltip 顯 last edited date |
| Gate (e) IntentProcessor wired | `✅` (bybit_earn_client + earn_movement_writer 均 injected) / `❌` (Gate E-0 unwired) | 綠/紅 + tooltip 顯 capability check |

**整體 verdict line**:`5/5 PASS - Stake submit unlocked` / `<N>/5 PASS - Submit disabled (修復:<gate 名稱>)`

**source**:`GET /api/v1/earn/preflight` 一次性回傳 5 gate status 物件;不需 5 個 endpoint。

#### §3.4 Available products list (~70 LOC)

| 元素 | 規格 | API source |
|---|---|---|
| Product list table | productId / coin / estimateApr (%) / minStake / maxStake / precision / status | `GET /api/v1/earn/products` |
| Filter | `coin == 'USDT'` AND `category == 'FlexibleSaving'` AND `status == 'Available'` |
| Empty state | `Bybit Earn 產品下架 / 維護` 訊息 (per Stage 0R AC-1 fallback) |
| Sort | estimateApr DESC (高 APR 在前;operator 視野對齊) |

**Sprint 1B first stake 鎖 USDT FlexibleSaving 1 product**:若 Bybit 返回多 product,前端只 highlight 第一個 + 註明「Sprint 1B 鎖 flexible USDT;其他產品 Sprint 5+ 開放」。

#### §3.5 First stake form (主寫表單;~150 LOC)

| 元素 | 規格 | 驗證 |
|---|---|---|
| Coin select | dropdown `USDT` (only option,disabled,純展示) | 硬鎖 USDT (per OP-3 flexible-only USDT) |
| Product ID (auto-pick) | hidden field,自 §3.4 第一個 USDT FlexibleSaving product 帶入 | 必須 status='Available' |
| Amount input | number input `$100.00 - $200.00 USDT` | 前端 onChange 即時校驗:< $100 紅色 / > $200 紅色 / 非數字 紅色 / [100, 200] 綠色 |
| Expected APR display | read-only `<X>.<XX> %` (自 §3.4 product.estimateApr 帶入 + 轉 bps) | 純展示;backend 從 product 取 expected_apr_bps |
| Rationale textarea | required,min 10 字,max 200 字 | 對齊 EarnIntentPayload.rationale (per earn_governance §3.2 GUI 必填) |
| Stage 0R preflight indicator | `Stage 0R: ✅ PASS / ⏳ PENDING / ❌ FAIL` + JSON ref link | per §7 Stage 0R integration |
| Submit button | red-gold `提交 Stake (typed-confirm)`;disabled 條件:5-gate 任一 FAIL / amount 非合法 / rationale < 10 字 / Stage 0R != PASS / Stage 0R missing | 對齊 ux-checklist 防誤等級 4 (打字確認 + cooldown) |

**Submit 流程**:見 §6 防誤觸 mechanism。

#### §3.6 Active positions (~70 LOC)

| 元素 | 規格 | API source |
|---|---|---|
| Position table | productId / coin / amount / totalPnl / claimableYield / status (Holding/PendingRedeem) / orderId | `GET /api/v1/earn/positions` |
| Empty state (first stake 前) | `尚未有 Earn 持倉;首次 stake 後此處顯示` (灰色) |
| Refresh | 15s auto;手動 refresh button (header) |

#### §3.7 Records history (~80 LOC)

| 元素 | 規格 | API source |
|---|---|---|
| Record list | ts (UTC + local) / direction (stake/redeem) / amount / apr / outcome (success/failure/pending) / lease_id / movement_id | `GET /api/v1/earn/records?limit=50` |
| Filter | direction (all/stake/redeem) + outcome (all/success/failure) |
| Click row | 展開 detail drawer 顯 bybit_request_payload + bybit_response_payload + governance_audit_log cross-ref |
| Export | CSV/JSON button (含 commit sha + 採集時間 footer per gui-style-guide 原則 2) |

### 3.3 UI 元素總估算

| Section | LOC 估算 |
|---|---|
| §3.1 Header | ~50 |
| §3.2 Balance | ~60 |
| §3.3 5-gate | ~120 |
| §3.4 Products | ~70 |
| §3.5 Form | ~150 |
| §3.6 Positions | ~70 |
| §3.7 Records | ~80 |
| 共用 styles + i18n | ~80 |
| **總 tab-earn.html** | **~680 LOC** (低於現行 2000 行門檻) |

---

## §4 FastAPI Routes Spec

### 4.1 Router 結構

新建 `earn_routes.py` (per `program_code/.../control_api_v1/app/`),`prefix='/api/v1/earn'`,對齊既有 governance_routes.py / live_session_routes.py 範式。

```python
# earn_routes.py 偽 code 結構
from fastapi import APIRouter, Depends, HTTPException
earn_router = APIRouter(prefix="/api/v1/earn", tags=["earn"])

@earn_router.get("/balance")             # §3.2 source
@earn_router.get("/products")            # §3.4 source
@earn_router.get("/preflight")           # §3.3 5-gate source + Stage 0R status
@earn_router.get("/positions")           # §3.6 source
@earn_router.get("/records")             # §3.7 source
@earn_router.post("/stake")              # §3.5 主寫操作
```

### 4.2 端點詳列

| 端點 | Method | Auth gate | Payload | Response |
|---|---|---|---|---|
| `/api/v1/earn/balance` | GET | session valid | — | `{usdt_balance, claimable_yield, last_recon_ts, recon_status, bybit_env}` |
| `/api/v1/earn/products` | GET | session valid | — | `{products: [FlexibleProduct], filtered_for: 'USDT_FlexibleSaving'}` |
| `/api/v1/earn/preflight` | GET | session valid | — | `{gate_a, gate_b, gate_c, gate_d, gate_e, all_pass: bool, stage_0r: {status, json_path, last_run_ts}}` |
| `/api/v1/earn/positions` | GET | session valid | — | `{positions: [FlexiblePosition]}` |
| `/api/v1/earn/records` | GET | session valid | `limit, direction, outcome` (query) | `{records: [EarnMovementRow], total}` |
| `/api/v1/earn/stake` | POST | `_require_operator_role` + `live_reserved` check | `{coin, product_id, amount_usdt, expected_apr_bps, rationale, typed_confirm_phrase}` | `{intent_id, lease_id, movement_id, submitted, rejected_reason, bybit_response}` |

### 4.3 `/api/v1/earn/stake` 寫操作詳列

**Auth gate** (Python 層,在 Rust 9-gate 前):
1. `_require_operator_role(actor)` (governance_routes.py:_require_operator_role) — Operator 角色驗
2. `live_reserved` Global Mode 驗 (對齊 live_session_routes.py line 16 dual gate pattern)
3. `typed_confirm_phrase` 後端再驗一次 (前端 typed-confirm 不可信;後端 case-sensitive compare `CONFIRM EARN STAKE $<amount> USDT`)

**Payload schema** (Pydantic model `EarnStakeRequest`):

```python
class EarnStakeRequest(BaseModel):
    coin: Literal["USDT"]
    product_id: str
    amount_usdt: Decimal = Field(ge=100, le=200)  # Sprint 1B 範圍硬鎖
    expected_apr_bps: int = Field(ge=0)
    rationale: str = Field(min_length=10, max_length=200)
    typed_confirm_phrase: str  # 後端驗 = "CONFIRM EARN STAKE $<amount> USDT"
```

**處理鏈** (對齊 earn_router.rs 9-gate):

```
1. Python auth gate (Operator + live_reserved + typed_confirm)
2. 構造 EarnIntentPayload (per earn_governance §3.2)
3. 呼 Rust IPC `IntentProcessor.process_earn_intent` (await)
4. Rust 走 E-0..E-9 9-gate (capability / payload / type / governance / lease / amount / placeholder / bybit / outcome)
5. Rust 回傳 IntentResult { submitted, rejected_reason, lease_id, movement_id }
6. Python 包裝 response 加 audit_log row ref + Stage 0R preflight JSON ref
7. 回傳前端 GUI 顯示成功/失敗 toast + 跳轉到 §3.7 records 高亮新 row
```

**Fail-closed** (per earn_governance §5):
- Python auth gate fail → HTTP 403 + reason
- Rust 9-gate 任一 fail → HTTP 200 + `submitted=false` + `rejected_reason` (per IntentResult)
- typed_confirm_phrase 不匹配 → HTTP 400 + reason
- Bybit retCode != 0 → 走 Rust E-9 write_failure path,Python 直接 propagate

### 4.4 audit-aware response footer

所有 6 端點 response 加 footer:
```json
{
  "data": {...},
  "_audit": {
    "actor": "PrimaryOperator",
    "ts_utc": "2026-05-26T...",
    "commit_sha": "abc1234",
    "trace_id": "uuid-v4"
  }
}
```

對齊 ux-checklist 2.5 + gui-style-guide 原則 2。

---

## §5 5-Gate UI Visualization

### 5.1 5 gate 對齊 (per earn_governance §2 + Stage 0R Earn variant §5.1)

| Gate | 名稱 | 後端 source | UI 顏色 + tooltip |
|---|---|---|---|
| (a) Operator role auth | `_require_operator_role` (governance_routes.py) | session.actor_role ∈ {Primary, Backup} | 綠/紅 + tooltip:當前 actor_id |
| (b) Signed authorization.json | governance.authorization_state_machine | HMAC valid + not expired + scope ⊇ earn-write | 綠/紅 + tooltip:authz_id + expiry UTC ts |
| (c) OPENCLAW_ALLOW_MAINNET | engine env capability | env=live ⇒ 必須 =1;env=demo ⇒ N/A (per §4.5 條件 A) | 綠/灰/紅 三狀態 + tooltip:env + value |
| (d) Bybit secret slot | secret_slot manager | slot 有 earn scope + < 6 mo since edit | 綠/⚠️/紅 + tooltip:last edited (per OP-1 < 2026-04-09 必重發) |
| (e) IntentProcessor wired | engine capability check | bybit_earn_client + earn_movement_writer 都 Some (per earn_router.rs E-0) | 綠/紅 + tooltip:capability injection check |

### 5.2 UI 視覺 layout

```
┌──────────────────────────────────────────────────────────────┐
│ 5-Gate 預檢 / 5-Gate Preflight (last check 2026-05-26 14:32 UTC) │
├──────────────────────────────────────────────────────────────┤
│  (a) 🟢 Operator    (b) 🟢 Authz     (c) 🟢 Mainnet            │
│  (d) 🟢 Secret      (e) 🟢 Engine                              │
│                                                                │
│  整體 verdict:  ✅ 5/5 PASS — Stake submit unlocked            │
│  Stage 0R:      ✅ PASS — last run 2026-05-26 13:00 UTC        │
│                 JSON:  earn_first_stake_stage0r_20260526.json  │
└──────────────────────────────────────────────────────────────┘
```

### 5.3 任 gate FAIL 行為

- 紅燈 + tooltip 詳述 fail 原因 + 提示修復 link (e.g. `(d) Secret` fail → tooltip 顯「Bybit Web UI 重發 key:see runbook earn_operations §1.2」)
- 整體 verdict 變 `❌ N/5 PASS - Submit disabled`
- §3.5 form submit button **disabled** (gray + "5-gate fail" tooltip)
- 5-gate 任 fail audit event_type `earn_intent_reject_gate_<a/b/c/d/e>` (per earn_router.rs error 分類)

### 5.4 polling 頻率

- 15s auto-refresh (對齊 sidebar)
- §3.5 form submit 前再 force-fetch 一次 `/api/v1/earn/preflight` (避免 stale 狀態下放行 — 對齊 ux-checklist 1 防誤觸)
- 後端 `/preflight` endpoint 內部緩存 5s (避免 burst poll)

---

## §6 防誤觸 Mechanism

### 6.1 對齊 ux-checklist 防誤等級

| 操作 | 防誤等級 | 本 spec 處置 |
|---|---|---|
| Earn stake (主寫) | **4** (改 risk_config 級) | 雙 gate (Operator + live_reserved) + typed-confirm + cooldown |
| Earn redeem (Sprint 5+) | 4 | 同 stake;Sprint 5+ 設計 |
| 查 balance / products / positions / records | 0 | 純 GET,無確認 |

### 6.2 Typed-confirm phrase 設計

**phrase 強制**:`CONFIRM EARN STAKE $<amount> USDT`

範例:
- amount=100 → phrase=`CONFIRM EARN STAKE $100 USDT`
- amount=150 → phrase=`CONFIRM EARN STAKE $150 USDT`
- amount=200 → phrase=`CONFIRM EARN STAKE $200 USDT`

**為什麼帶 amount**:
- 反 muscle memory:operator 過去 typed-confirm `CONFIRM` 或固定字串 (canary-tab.js phrase=`PROMOTE`),Earn 多帶 amount 避免「順手打完按 enter」誤觸
- 反 copy-paste:operator 必須親手鍵入 amount 數字 → 確認 amount 與表單一致 (對齊 ux-checklist 防誤等級 4 雙重防護)
- 後端再驗一次 (Python typed-confirm phrase match) → 防前端 bypass

**case-sensitive**:per common-modals.js:343 既有 SOP。

### 6.3 Modal 內容 (per common-modals.js `openTypedConfirmModal` options)

```javascript
openTypedConfirmModal({
  title: '確認 Earn First Stake / Confirm Earn First Stake',
  body: '此操作將寫入真實 Bybit Earn balance,動主帳 USDT。\n失敗範圍:Bybit retCode != 0 → fail-closed reject + audit log;成功則 7d Stage 1 Demo micro-canary 觀察期啟動。',
  phrase: `CONFIRM EARN STAKE $${amount} USDT`,
  confirmLabel: '提交 Stake / Submit Stake',
  confirmClass: 'oc-btn-danger',
  actor: actorId,
  impact: `${amount} USDT FlexibleSaving stake @ ~${apr}% APR (預期年化 ~$${(amount * apr / 100).toFixed(2)})`,
  rollback: 'Redeem 走 /api/v1/earn/redeem (Sprint 5+;Sprint 1B first stake 後 7d 觀察期內不 redeem)',
});
```

### 6.4 Cooldown ≥ 30s (per ux-checklist 防誤等級 4)

- Submit button 點擊 → modal 顯示 → typed-confirm 過 → submit (此時間 ≥ 30s 因 operator 打字 + 思考時間自然構成 cooldown)
- 不額外加 30s 等待 timer (per common-modals.js 既有設計 + operator 體驗);依靠 typed-confirm 自然摩擦
- **但** 失敗後 cooldown 60s 才允許 retry (對齊 earn_governance §5.3 連續失敗計數 + ux-checklist 2.2 認知負荷)

### 6.5 Pre-submit local validation (前端)

submit button enable 條件 (前端 onChange 即時驗):
1. amount ∈ [100, 200] (per OP-2 拍板)
2. coin == 'USDT'
3. product_id != null AND product.status == 'Available'
4. rationale.length ∈ [10, 200]
5. 5-gate all_pass == true
6. Stage 0R status == 'PASS'
7. Stage 0R JSON ref 存在 (preflight 必須跑過)

任一不滿足 → button disabled + 紅色提示 + 具體 reason text。

### 6.6 Anti-pattern 8 條 cross-ref

per A3 ux-checklist 既有 8 反模式 (來自 W-AUDIT 系列):

| # | Anti-pattern | 本 spec 防護 |
|---|---|---|
| 1 | 單擊 yes/no 高破壞性 | §6.2 typed-confirm phrase |
| 2 | phrase 過短 (`Y` / `CONFIRM`) | §6.2 `CONFIRM EARN STAKE $<amount> USDT` 帶 amount + 30+ char |
| 3 | phrase case-insensitive | §6.2 case-sensitive (per common-modals.js:343) |
| 4 | 前端 typed-confirm 後端無驗 | §4.3 後端再驗一次 phrase |
| 5 | Submit button 0 防 double-click | §6.4 cooldown + button 提交後 disabled 直到 response |
| 6 | 錯誤狀態 ambiguous | §6.5 局部 reason text + modal rollback 明示 |
| 7 | Audit log 無 actor/ts/rationale | §4.4 _audit footer + rationale required |
| 8 | 5-gate UI 缺視覺 | §3.3 + §5 5 light 視覺 |

8/8 防護 = ux-checklist A 級。

---

## §7 Stage 0R Preflight Integration

### 7.1 Stage 0R harness 與 GUI 關係

per Stage 0R Earn variant spec §3 + §7.4:
- Harness file:`helper_scripts/canary/replay_earn_preflight.py` (E1 IMPL 待 Wave C 派工)
- Harness CLI:`python helper_scripts/canary/replay_earn_preflight.py --coin USDT --amount-usd 100 --days 7`
- Harness output:JSON file `earn_first_stake_stage0r_<date>.json` 在 `$OPENCLAW_DATA_DIR/canary/`
- Harness verdict:`eligible_for_first_stake = true/false`

GUI 與 harness 的整合方式:**讀取 harness JSON output + 顯示狀態**,不替 harness 跑;harness 仍由 operator CLI 觸發 (per Stage 0R spec §7 chain)。

### 7.2 GUI 顯示 Stage 0R status (3 狀態)

| 狀態 | 條件 | UI |
|---|---|---|
| ✅ PASS | JSON file 存在 + age < 24h + `eligible_for_first_stake=true` | 綠燈 + last run ts + JSON link |
| ⏳ PENDING | JSON file 不存在 OR age > 24h | 黃燈 + 提示「請先跑 Stage 0R preflight:`python helper_scripts/canary/replay_earn_preflight.py ...`」+ 命令 copy button |
| ❌ FAIL | JSON file 存在 + `eligible_for_first_stake=false` | 紅燈 + 顯 fail reason (從 JSON `reasons` field 提取) + JSON link |

### 7.3 後端 endpoint 整合

`GET /api/v1/earn/preflight` response 加 `stage_0r` 子物件:

```json
{
  "gate_a": "PASS", "gate_b": "PASS", "gate_c": "PASS", "gate_d": "PASS", "gate_e": "PASS",
  "all_pass": true,
  "stage_0r": {
    "status": "PASS" | "PENDING" | "FAIL",
    "json_path": "$OPENCLAW_DATA_DIR/canary/earn_first_stake_stage0r_20260526.json" | null,
    "last_run_ts": "2026-05-26T13:00:00Z" | null,
    "eligible_for_first_stake": true | false | null,
    "fail_reasons": [] | ["apy_drift_check: drift_pct=7.5 > 5.0"]
  }
}
```

後端 `/preflight` endpoint 邏輯:
1. 掃 `$OPENCLAW_DATA_DIR/canary/earn_first_stake_stage0r_*.json` glob (most recent)
2. 讀 JSON `eligible_for_first_stake` + `reasons` field
3. 計算 age = now - JSON.run_ts;> 24h → status=PENDING
4. 構造 stage_0r 子物件 return

### 7.4 Submit button gate

§3.5 form submit button **disabled** 條件含 `stage_0r.status != "PASS"`:
- PENDING → button disabled + tooltip「請先跑 Stage 0R preflight」+ 命令 copy
- FAIL → button disabled + tooltip 顯 fail_reasons + 提示重跑

對齊 Stage 0R spec §4.4 AC-4 fail-closed reject (harness fail → Stage 1 Demo micro-canary launcher refuse to start)。

### 7.5 Operator workflow (GUI + CLI hybrid)

```
1. Operator 進 Earn tab → 看到 Stage 0R: ⏳ PENDING
2. 開 SSH terminal:python helper_scripts/canary/replay_earn_preflight.py --coin USDT --amount-usd 100 --days 7
3. Harness 跑 ~2-3 min → JSON file land
4. 回 GUI 點 refresh → Stage 0R: ✅ PASS + 5-gate all green
5. 填 §3.5 form (amount $100, rationale)
6. 點 submit → typed-confirm modal
7. 鍵入 `CONFIRM EARN STAKE $100 USDT` → 確認
8. Backend dispatch → Rust 9-gate → Bybit place-order → V100 INSERT → response
9. GUI 顯示成功 toast + §3.7 records 高亮新 row
```

### 7.6 Stage 0R spec §7.4 E1 IMPL 阻塞關係

per Stage 0R Earn variant spec §7.4:`replay_earn_preflight.py` 尚未 IMPL (E1 Wave C 派工 ~4-6 hr)。

**GUI 是否 wait?**:**否,GUI 與 Stage 0R harness IMPL 可並行**。理由:
1. GUI `/preflight` endpoint 邏輯純 read-file (掃 JSON glob);harness 未產出 JSON 時自然 status=PENDING + tooltip 提示
2. GUI E1 / E1a 派工不需 harness 已 land;harness JSON schema (eligible_for_first_stake / reasons / run_ts) 已在 Stage 0R spec §3.3-§3.5 明示
3. operator first stake 走 GUI 之前 Stage 0R harness 必先 land (Wave C IMPL chain:E1 harness → E1a GUI 或 parallel → operator first stake)

**Sequential 部分**:operator 第一次 first stake 真實執行前,Stage 0R harness 必 IMPL + run 至少 1 次 (否則 §3.5 submit button 永遠 disabled)。

---

## §8 IMPL Roadmap (E1 + E1a)

### 8.1 階段鏈

```
[PA] 本 spec land (~4 hr) ← CURRENT
   ↓
[A3 + QA cross-ref] (parallel, ~2-3 hr 各)
   ↓
[PM] 仲裁 + operator OQ 拍板 (~1 hr)
   ↓
[E1 + E1a parallel dispatch] (~12-18 hr 並行)
   - E1 FastAPI Python earn_routes.py (~5-7 hr)
   - E1a Frontend Vanilla JS tab-earn.html + earn-tab.js (~7-11 hr)
   - E1 Stage 0R harness replay_earn_preflight.py (~4-6 hr;per Stage 0R spec §7.4;可並行)
   ↓
[E2] Adversarial review (~3-4 hr)
   ↓
[E4] Regression (cargo test + pytest + node --check + smoke) (~2-3 hr)
   ↓
[A3 + QA] UX + AC verify (~2-3 hr 各)
   ↓
[PM] Phase 3e sign-off (~1 hr)
   ↓
[Operator] OP-1 Bybit key 重發 (~30-60 min)
   ↓
[Operator] Stage 0R harness run + first stake via GUI (~10-30 min)
```

### 8.2 E1 (FastAPI Python) 工作 (~5-7 hr)

**檔案**:
- 新建:`program_code/.../control_api_v1/app/earn_routes.py` (~400 LOC)
- 修改:`program_code/.../control_api_v1/app/main.py` (or similar) — 加 `earn_router` include

**Scope**:
- 6 端點 IMPL (per §4.2)
- Auth gate + `_require_operator_role` + `live_reserved` dual gate
- Pydantic `EarnStakeRequest` model
- IPC 呼 Rust `IntentProcessor.process_earn_intent` (走既有 IPC channel;對齊 trading intent dispatch)
- Stage 0R JSON file glob + parse
- Audit footer + trace_id 注入

**依賴**:
- `BybitEarnClient` Rust binding (already wave B IMPL per dispatch packet §7.3)
- `EarnMovementWriter` Rust binding (already wave B)
- `governance_routes._require_operator_role` (既有)
- `live_session_routes` live_reserved Global Mode check (既有)

### 8.3 E1a (Frontend Vanilla JS) 工作 (~7-11 hr)

**檔案**:
- 新建:`program_code/.../control_api_v1/app/static/tab-earn.html` (~680 LOC per §3.3 估算)
- 新建:`program_code/.../control_api_v1/app/static/earn-tab.js` (~400 LOC,對齊 canary-tab.js + governance-tab.js 範式)
- 修改:`program_code/.../control_api_v1/app/static/console.html` TABS 陣列 (1 line per §2.3)
- 修改:`program_code/.../control_api_v1/app/static/i18n_zh.js` 加 Earn 鍵 (~20 line)

**Scope**:
- 7 sections IMPL (per §3.1)
- 5-gate visualization (per §5)
- typed-confirm modal 整合 (復用 `openTypedConfirmModal`)
- 15s auto-refresh + manual refresh
- 5 端點 GET poll + 1 endpoint POST submit
- a11y (aria-label / role="dialog" / tab order;對齊 gui-style-guide)
- i18n 中文主 (per `feedback_chinese_output`)

**依賴**:
- `common-modals.js` (typed-confirm,既有)
- `common.js` (apiGet/apiPost,既有)
- `common-formatters.js` (decimal/timestamp,既有)
- `i18n_zh.js` (鍵注入,既有)

### 8.4 E1 / E1a Parallel 可行性

| 維度 | Parallel 可? | 理由 |
|---|---|---|
| 開發環境 | ✅ | E1 = Python backend,E1a = Vanilla JS frontend;兩者 0 文件重疊 |
| Schema 對齊 | ✅ | 本 spec §4.2 (Response schema) + §3.5 (Form fields) = SSOT;雙方對齊 spec 不對齊代碼 |
| Sub-agent 分派 | ✅ | E1 (5-7 hr) + E1a (7-11 hr) 並行;walltime = max(E1, E1a) = 7-11 hr 而非 sequential 12-18 hr |
| 整合測試 | sequential | E1 + E1a 都完 → E2 adversarial → E4 smoke (curl + browser)|

**結論**:E1 + E1a **建議並行** (parallel sub-agent dispatch);Stage 0R harness `replay_earn_preflight.py` 也可並行 (E1 wave Earn harness owner;單獨第三條 sub-agent)。

### 8.5 E1 / E1a sub-agent prompt 範本要點

| Sub-agent | Prompt 必引 |
|---|---|
| E1 (earn_routes.py) | 本 spec §4 + earn_governance §3.2 EarnIntentPayload + earn_router.rs E-0..E-9 contract + governance_routes._require_operator_role 範式 + live_session_routes.py auth dual gate 範式 |
| E1a (tab-earn.html + earn-tab.js) | 本 spec §3 / §5 / §6 + gui-style-guide skill + common-modals.js typed-confirm API + canary-tab.js 範式 + governance-tab.js 範式 + i18n_zh.js 既有 i18n pattern |
| E1 (Stage 0R harness, parallel) | Stage 0R Earn variant spec §3 + §7.4 + replay_funding_harvest.py 範式 |

### 8.6 E2 Adversarial Review 重點 3 點

per PA profile.md:

1. **Python typed-confirm 後端驗 (§4.3 第 3 條)** — backend 是否真的 case-sensitive compare phrase;若漏驗則前端 bypass 即繞;grep `typed_confirm_phrase` 後端 IMPL
2. **Stage 0R JSON ref 防偽** — `/api/v1/earn/preflight` 是否驗 JSON age < 24h + signature/hash;若僅看 file 存在則 stale JSON 誤放行
3. **5-gate UI 與後端 9-gate 對齊** — 前端 5 light 是否精確對映後端 E-0..E-9 (不是 1:1,5 light 是 5 governance gate;9 gate 含 capability/payload 等技術 gate);避免 UI 顯示「5/5 PASS」但後端 E-0 unwired (e.g. earn_movement_writer not injected)

### 8.7 E4 Regression Scope

- `cargo test` (Wave B 既有 30+ test 不 regress)
- `pytest program_code/.../control_api_v1/tests/` (新加 earn_routes 6 端點 test)
- `node --check tab-earn.html` + `node --check earn-tab.js` (per `feedback_gui_node_check_sop` 強制)
- Smoke:`curl /api/v1/earn/balance` 5 端點 200 OK + `curl /api/v1/earn/stake` 預期 403 (無 auth)
- Browser smoke:console open Earn tab,各 section 顯示,5-gate 顯示,submit button disabled (預期無 Stage 0R)

---

## §9 Acceptance Criteria (GUI 完成度)

### 9.1 AC-1 — Tab-earn.html load + 7 sections 完整渲染

| Element | Spec |
|---|---|
| Verify path | Browser open `http://trade-core:8000/console` → 切到 Earn tab → 7 sections (§3.1-§3.7) 全部 DOM 載入 |
| Verification owner | A3 + QA |
| Empirical evidence | Screenshot 7 sections + DOM inspector 確認 `id` 對齊 §3 spec |
| Failure path | section 缺失 / DOM 漏 → A3 reject |

### 9.2 AC-2 — 5-gate UI 與後端對齊 (5 light 全綠 ↔ all_pass=true)

| Element | Spec |
|---|---|
| Verify path | `/api/v1/earn/preflight` 5 gate 後端 mock 5 種狀態組合;前端 5 light 顯示對映 |
| Verification owner | E2 + A3 |
| Empirical evidence | mock fixture × 5 case (all PASS / a fail / b fail / c fail / d fail / e fail) × UI screenshot |
| Failure path | UI 顯 PASS 但 backend FAIL → BLOCKER |

### 9.3 AC-3 — Typed-confirm phrase 強制 + 後端驗

| Element | Spec |
|---|---|
| Verify path | (1) Frontend modal phrase = `CONFIRM EARN STAKE $<amount> USDT`,case-sensitive (2) Backend `/api/v1/earn/stake` 驗 phrase 不匹配 → HTTP 400 |
| Verification owner | E2 + A3 |
| Empirical evidence | (1) Modal screenshot phrase string (2) curl mismatched phrase → 400 + reason |
| Failure path | 前端 bypass / 後端忽略 → BLOCKER (per A3 anti-pattern #4) |

### 9.4 AC-4 — Stage 0R 整合 (PENDING/PASS/FAIL 3 狀態)

| Element | Spec |
|---|---|
| Verify path | (1) JSON 不存在 → PENDING + tooltip 命令 (2) JSON `eligible=true` + age<24h → PASS (3) JSON `eligible=false` → FAIL + fail_reasons |
| Verification owner | E2 + QA |
| Empirical evidence | mock JSON × 3 case × UI screenshot |
| Failure path | UI 顯 PASS 但 JSON missing / age > 24h → BLOCKER |

### 9.5 AC-5 — Operator first stake real-run AC-3 backbone (V100 row INSERT)

| Element | Spec |
|---|---|
| Verify path | operator 走 §7.5 workflow first stake $100 → V100 row INSERT (per Stage 0R AC-3 deferred) |
| Verification owner | QA + Operator |
| Empirical evidence | Linux PG `SELECT * FROM learning.earn_movement_log ORDER BY created_at DESC LIMIT 1` → row content: direction='stake', amount_usdt=100, engine_mode='live_demo' or 'live', outcome='matched', governance_approval_id NOT NULL |
| Failure path | 0 row / outcome != matched / engine_mode wrong → 修 IMPL 不通過 |

### 9.6 5 AC 全 PASS verdict gate

```
gui_ready_for_first_stake = (
  AC-1 == PASS  # 7 sections render
  AND AC-2 == PASS  # 5-gate UI align
  AND AC-3 == PASS  # typed-confirm enforce
  AND AC-4 == PASS  # Stage 0R integration
  AND AC-5 == 'deferred_to_operator_first_stake'  # V100 row verify by real-run
)
```

---

## §10 Open Questions (Operator 拍板項)

### 10.1 OQ-1: Earn tab 屬 governance group 還是新建 'earn' group?

**選項**:
- (a) **governance group** (本 spec 立場) — Earn 是 asset write governance 對象;6 group 結構保留;認知一致
- (b) 新建 'earn' group — Sprint 5+ Earn 範圍擴張 (multi-product / Auto-Allocator) 後預留;但 Sprint 1B 只 1 tab,新 group 不夠飽和

**PA 建議**:(a) governance group。理由 = Sprint 1B 範圍小,新 group 不飽和;Sprint 5+ 若 Earn 範圍擴 (≥ 3 tab) 再拆 group。

### 10.2 OQ-2: 後續 stake / redeem variant GUI 何時 IMPL?

**選項**:
- (a) Sprint 1B 同 first stake 一起 IMPL (~+10-15 hr GUI)
- (b) **defer Sprint 5+** (本 spec 立場) — Sprint 1B 鎖 first stake;後續 variant 隨 Rust IntentProcessor stake/redeem 支援 + Stage 0R variant spec 擴張同步

**PA 建議**:(b) defer。理由 = Sprint 1B 過短;先 first stake 真實寫入 V100 後再評估 redeem GUI 必要性;避免 over-engineering。

### 10.3 OQ-3: Typed-confirm phrase 是否帶 amount?

**選項**:
- (a) **`CONFIRM EARN STAKE $<amount> USDT`** (本 spec 立場) — amount 動態,反 muscle memory + reinforces operator intent
- (b) 固定 `CONFIRM EARN STAKE` (不帶 amount) — 與既有 canary-tab.js phrase=`PROMOTE` 統一風格;但失 reinforces

**PA 建議**:(a) 帶 amount。理由 = Earn 動主帳本,風險級 4 (per ux-checklist),雙重 reinforces (form amount + phrase amount) 對齊 anti-pattern #2 phrase 過短;canary `PROMOTE` 不動主帳本,風險低於 Earn,phrase 不需多反 muscle memory。

### 10.4 OQ-4: Stage 0R harness 觸發是否走 GUI button?

**選項**:
- (a) **CLI only** (本 spec 立場) — operator 開 SSH 跑 `python helper_scripts/canary/replay_earn_preflight.py ...`;GUI 顯狀態 + copy 命令
- (b) GUI button 觸發 → 後端 fork subprocess → 監聽 JSON output → 前端輪詢

**PA 建議**:(a) CLI。理由 = 對齊 C10 funding_harvest preflight 範式 (CLI 觸發,GUI 讀 JSON);Stage 0R 是 design 性 preflight 不應 GUI 一鍵 (gate 過嚴形式之一,operator 親手 CLI 跑 = 額外 sanity check);GUI fork subprocess 引入新 attack surface + 進程管理 complexity。

### 10.5 OQ-5: §3.6 Active positions / §3.7 Records 是否 Sprint 1B IMPL?

**選項**:
- (a) **IMPL** (本 spec 立場) — first stake 後 operator 必看到 1 條 position (active stake) + 1 條 record (audit row);否則 AC-5 V100 row verify 走 SSH PG query 摩擦高
- (b) defer Sprint 5+ — Sprint 1B 只 IMPL §3.1-§3.5 (header / balance / 5-gate / products / form);positions + records 後續加

**PA 建議**:(a) IMPL。理由 = positions + records 是 read-only GET 端點 + table render,LOC ~150 (10-15% E1a 工時),投入產出比高;operator 體驗連貫 (stake → 立即看到 position + record 確認成功);AC-5 走 GUI 而非 SSH PG query 更符 ux-checklist 5 可審計。

### 10.6 OQ-6: GUI POST /api/v1/earn/stake 是否同步 wait Bybit ack?

**選項**:
- (a) **Sync wait Bybit ack** (本 spec 立場) — Python endpoint 同步呼 Rust IPC + Rust 同步呼 Bybit;GUI 顯 spinner ≤ 10s;timeout 後顯 error (per ux-checklist 3.3)
- (b) Async pattern — POST return immediately + intent_id;GUI 後續 poll status endpoint

**PA 建議**:(a) sync。理由 = first stake 只 1 次 + Bybit place-order normal latency < 5s;sync simpler + 對齊 既有 trading intent dispatch 範式;async 引入 status poll endpoint + state machine complexity 不值;若 Bybit > 10s timeout 走 fail-closed (per earn_governance §5.1)。

---

## §11 Cross-References

- Stage 0R Earn variant design spec: `docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md`
- Earn governance spec: `docs/execution_plan/2026-05-21--earn_governance_spec.md`
- Earn first stake dispatch packet (Wave A-E IMPL chain): `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md`
- Earn router IMPL (9-gate E-0..E-9): `rust/openclaw_engine/src/intent_processor/earn_router.rs`
- Bybit Earn client IMPL (5 endpoint): `rust/openclaw_engine/src/bybit_earn_client.rs`
- typed-confirm modal API: `program_code/.../control_api_v1/app/static/common-modals.js` line 339 `openTypedConfirmModal`
- governance_routes auth gate: `program_code/.../control_api_v1/app/governance_routes.py` `_require_operator_role`
- live_session_routes dual gate: `program_code/.../control_api_v1/app/live_session_routes.py` line 16
- canary-tab.js typed-confirm 範式: `program_code/.../control_api_v1/app/static/canary-tab.js` (phrase=PROMOTE)
- console.html TABS 陣列: `program_code/.../control_api_v1/app/static/console.html` line 350-376
- gui-style-guide skill: `.claude/skills/gui-style-guide/SKILL.md`
- ux-checklist skill: `.claude/skills/ux-checklist/SKILL.md`

---

## §12 Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| PA | 本 spec 起草 (Sprint 1B Earn Wave C carry-over「GUI scope 仲裁」) | 2026-05-25 | ✅ DRAFT-DESIGN-DONE |
| A3 | UX 審查 (7 sections + 5-gate UI + typed-confirm + Stage 0R integration) | TBD (Wave C) | 🟡 PENDING |
| QA | AC-1~5 testability + Pydantic schema + smoke test design | TBD (Wave C) | 🟡 PENDING |
| E1 | earn_routes.py IMPL | TBD (Wave C) | 🟡 PENDING |
| E1a | tab-earn.html + earn-tab.js IMPL | TBD (Wave C) | 🟡 PENDING |
| E2 | Adversarial review (3 重點 per §8.6) | TBD (Wave C) | 🟡 PENDING |
| E4 | Regression (cargo + pytest + node --check + smoke) | TBD (Wave C) | 🟡 PENDING |
| PM | Phase 3e GUI closure sign-off | TBD (Wave C) | 🟡 PENDING |
| Operator | OP-1 Bybit key 重發 + first stake via GUI + AC-5 V100 row verify | TBD (Wave E) | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium Sprint 1B Earn Wave C Earn First Stake GUI Design Spec — 對齊 Stage 0R Earn variant spec §5/§7.10 + earn_governance §2/§3 + gui-style-guide + ux-checklist 5 維度 + common-modals typed-confirm + 16 tab GUI 架構*
