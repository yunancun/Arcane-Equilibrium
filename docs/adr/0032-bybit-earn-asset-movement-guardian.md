# ADR 0032: Bybit Earn Asset Movement Guardian — 5-Gate Adapter + Decision Lease Retrofit + Audit Log

Date: 2026-05-21
Status: **Proposed-pending-commit**（v5.7 §12 ADR-0030 提案順移為 0032；本 ADR 為 ADR-0031 Framework 1 §1.2 Earn asset movement 細節獨立拆分）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via v5.7 §4 + §11 Reviewer Condition 6 + §12 governance recap）
Related: ADR-0031 (Framework expansion — Earn governance 父框架) / ADR-0008 (Decision Lease state machine) / v5.7 §4 (Bybit Earn dynamic APR + governance) / v5.7 §8 Sprint 1A-1B (Earn API recorder + Earn governance policy land)

## Context

### 起源

v5.7 §6 Reviewer correction：「Earn deposits no governance policy (asset write operation)」是 v5.6 重大缺陷。

v5.7 §4 fix：

> 2. Asset movement governance:
>    - Each stake operation = asset write, requires authorization
>    - Guardian-checked: same risk envelope as trading operations
>    - Decision Lease pattern: stake intent → guardian → execute → audit log
>    - Auto-redeem trigger: trading margin headroom < 30%
>    - Manual rebalance initially (first 3 months); auto after proven

v5.7 §12 將此提案為 ADR-0030（**順移為本 ADR-0032**，因 ADR-0030 已被 Copy Trading evidence-gated 占用，且本 ADR 內容已從 ADR-0031 Framework 1 §1.2 拆分出來）。

### 為什麼需要獨立 ADR 而非歸併 ADR-0031

ADR-0031 涵蓋三個 framework（Earn / Macro / On-chain）共用治理紀律。Earn asset movement Guardian 執行細節遠超 framework 級別：

- **5-gate adapter 設計**：與既有 Five-Gate（per `docs/architecture/*` 既有 5 gate baseline）對齊但 Earn 路徑有 surface 差異
- **Decision Lease retrofit**：既有 Decision Lease state machine 為 trading intent 設計，stake intent 需要 retrofit
- **Audit log schema**：`learning.earn_movement_log` 表結構需 spec
- **Manual first 3 months 紀律驗證流程**：runbook + healthcheck

這些細節若全塞進 ADR-0031 會把 framework ADR 撐爆；獨立 ADR-0032 保持單一職責。

### Earn asset movement 與 trading order 的核心差異

| 維度 | Trading order | Earn stake/redeem |
|---|---|---|
| 資產移動 | Spot/perp position change | Asset 在 wallet → Earn product 之間 |
| Reversibility | 訂單可 cancel + 反向平倉 | Redeem 有 unstake period（如某 Earn product 需 24h-7d） |
| 風險 envelope | Position size + leverage + liquidation distance | Asset 鎖定期內不可調用 + APR 變動風險 |
| Counterparty | Bybit exchange | Bybit Earn product issuer（可能是 Bybit 或第三方 issuer） |
| Authorization 需求 | Signed authorization.json | 同 trading（Guardian + Decision Lease + authorization） |
| 失敗 mode | 訂單拒、partial fill、liquidation | API 失敗、Earn product 額度滿、unstake fail |
| 監控頻率 | 即時（ms 級） | 慢（min/hr 級；APR 變動慢） |

**核心結論**：Earn stake/redeem 是「**慢資產移動**」，不需 trading hot path 的低延遲，但需要更嚴格的 reversibility check（unstake period 內 asset 鎖定）。

### v5.6 缺漏的具體治理 surface

v5.6 把 Earn 當作「**靜態 cash management**」設計，缺漏：

1. **Authorization gate** — stake intent 沒走 Operator role auth + authorization.json check
2. **Guardian risk envelope** — stake amount 沒被風控評估（如「stake 後 trading margin headroom 是否充足」）
3. **Decision Lease** — stake intent 沒走 lease pattern，無法 timeout / cancel / audit
4. **Audit log** — 沒紀錄 stake direction / amount / APR snapshot / governance approval / 後續對賬
5. **Manual review 紀律** — 沒定義 first 3 months 是 manual 還是 auto；沒 healthcheck 紀律

v5.7 §4 修正包含全 5 個 surface，但具體 spec 留給本 ADR 鎖定。

## Decision

**Proposed**：Earn stake/redeem 走 5-gate adapter（對齊既有 Five-Gate baseline）+ Decision Lease retrofit + audit log 完整路徑；Y1 first 3 months 強制 manual，後續 evidence-based 漸進開 auto-redeem。

### 5-Gate Adapter（對齊既有 Five-Gate baseline）

既有 Five-Gate（per `docs/architecture/*` baseline）是 trading-oriented；本 ADR 為 Earn 路徑設計對應 5 gate adapter，gate 編號與既有 Five-Gate 對齊：

#### Gate 1 — Authorization Gate

| 元素 | Earn-specific |
|---|---|
| Python `live_reserved` | 同既有 trading |
| Python Operator role auth | 同既有 trading；stake intent 需 Operator role |
| `OPENCLAW_ALLOW_MAINNET=1` | 同既有 trading（demo Earn 用 demo endpoint） |
| 有效 secret slot | 同既有 trading |
| Signed `authorization.json` 未過期 + env 對應 | 同既有 trading；不接受手寫 authorization.json |

**Fail mode**：任一條 fail → reject stake intent + log 到 `learning.earn_movement_log` with `gate=authorization` + `result=rejected`。

#### Gate 2 — Risk Envelope Gate（Guardian）

| Sub-criterion | Threshold | 計算來源 |
|---|---|---|
| Stake 後 trading margin headroom | ≥ 30%（per v5.7 §4 auto-redeem trigger 反向 baseline） | account balance + open positions notional |
| Stake amount / 主帳 total assets | ≤ 80%（剩下 20% 必須保留 trading 流動性） | 主帳 reconciliation |
| Earn product unstake period 與當前策略 deployment timeline | unstake period < 下個策略 promotion 預期時間 | strategy promotion calendar |
| Bybit Earn product issuer trust level | Bybit 自營 = PASS；第三方 issuer = 需 Operator manual approve | Bybit API product metadata |

**Fail mode**：任一 sub-criterion fail → Guardian block + log to `learning.guardian_block_log` with `block_reason=earn_*`。

#### Gate 3 — Decision Lease Gate

對齊 ADR-0008 Decision Lease state machine，但 stake intent 需要 retrofit：

| Element | Trading lease | Earn lease (retrofit) |
|---|---|---|
| Lease ID format | `lease_<strategy>_<symbol>_<ts>` | `lease_earn_<product>_<direction>_<ts>` |
| TTL | 通常 ms-sec 級 | min-hr 級（Earn 不需 trading hot path 速度） |
| State transitions | open / matched / submitted / cancelled | 對齊 + `unstake_pending`（Earn product 鎖定期內） |
| Idempotency key | `intent_id` | `intent_id`（同既有） |
| Cancel path | Operator override + Guardian block + TTL expire | 同既有 + 「unstake period 內 cancel」是 N/A（已 staked 無法取消，只能等 unstake period 結束） |

**Retrofit 工作量**：~8-10 hr（Decision Lease state machine 已存在；只需擴展 state + lease ID parser）。

#### Gate 4 — Execute Gate（API call）

| 元素 | Earn-specific |
|---|---|
| API endpoint | Bybit Earn API（stake/redeem endpoints — per v5.7 §8 Sprint 1A 新接入） |
| Timeout 處理 | Bybit Earn API timeout → fail-closed（per ADR §四 既有 Bybit API timeout 處理紀律）；不暗自 retry |
| Partial fill 處理 | Earn 通常 atomic（all-or-nothing）；若 Bybit 返回 partial → log + Operator manual review |
| API response 對齊 audit log | Bybit return 的 stake_id / unstake_id / 實際 stake amount 寫進 audit log |

#### Gate 5 — Audit Log Gate（post-execute）

| 元素 | Earn-specific |
|---|---|
| Audit log table | `learning.earn_movement_log`（NEW，per v5.7 §4 spec） |
| 寫盤紀錄 | direction (stake/redeem), amount, APR at time, governance approval (intent_id), Bybit API response, gate 1-4 evidence chain |
| Daily reconciliation | 對齊 Bybit account balance（per v5.7 §4 spec）；任何 diff → flag + RCA |
| Healthcheck | engine_mode IN ('live','live_demo') 的 stake/redeem 必須 100% 進 audit log；missing = HIGH severity alert |

### `learning.earn_movement_log` Schema 候選（待 MIT review）

```sql
CREATE TABLE IF NOT EXISTS learning.earn_movement_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    intent_id       TEXT        NOT NULL,    -- Decision Lease lease ID
    direction       TEXT        NOT NULL,    -- 'stake' / 'redeem'
    product         TEXT        NOT NULL,    -- Bybit Earn product identifier
    amount          REAL        NOT NULL,    -- USDT 等價金額
    asset           TEXT        NOT NULL,    -- 'USDT' / 'BTC' / 'ETH' / ...
    apr_at_time     REAL,                     -- API query 結果（tier-weighted effective APR）
    apr_tier_first  REAL,                     -- First $200 tier rate snapshot
    apr_tier_rest   REAL,                     -- Subsequent tier rate snapshot
    gate_1_auth     BOOLEAN     NOT NULL,    -- Authorization gate result
    gate_2_risk     BOOLEAN     NOT NULL,    -- Risk envelope gate result
    gate_3_lease    BOOLEAN     NOT NULL,    -- Decision Lease gate result
    gate_4_execute  BOOLEAN     NOT NULL,    -- API execute result
    bybit_resp      JSONB,                    -- Bybit API response payload
    initiator       TEXT        NOT NULL,    -- 'manual' / 'auto_redeem' / 'rebalance'
    operator_id     TEXT,                     -- 若 manual 由誰發起
    engine_mode     TEXT        NOT NULL,    -- 'live' / 'live_demo' / 'demo'
    rec_status      TEXT,                     -- Daily reconciliation status: 'pending' / 'matched' / 'diff'
    rec_diff        REAL,                     -- 對賬差異金額
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_earn_movement_intent_id ON learning.earn_movement_log(intent_id);
CREATE INDEX IF NOT EXISTS idx_earn_movement_ts ON learning.earn_movement_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_earn_movement_engine_mode ON learning.earn_movement_log(engine_mode);
```

**Migration 編號**：待 PA dispatch 分配 V### 編號（per v5.7 §3 schema migration number reconciliation）。

**Migration land timing**：Sprint 1A 期間 land；對齊 v5.7 §8 「Bybit Earn API APR recorder (read-only, no stake yet)」之後但 first manual stake Sprint 1B 之前。

### Manual First 3 Months 紀律驗證

#### 紀律 1 — 強制 manual stake/redeem（Sprint 1B 至 Sprint 4 結束）

| 元素 | 設計 |
|---|---|
| 觸發方式 | Operator 透過 Console / GUI 顯式發起 stake intent |
| Auto-redeem | **禁止** Sprint 1B-4 期間任何 auto-redeem |
| Stake size | first stake $200-400（per v5.7 §8 Sprint 1B）；後續按 evidence 逐步調整 |
| Operator 紀錄 | 每筆 stake/redeem 留 operator note 在 audit log `operator_id` + `initiator='manual'` |

#### 紀律 2 — Sprint 4 結束 evaluation（Earn manual 3 months review）

Sprint 4 結束（W15）做一次 Earn manual review verdict：

| Sub-criterion | Threshold | 數據源 |
|---|---|---|
| 期間任何 unauthorized stake/redeem | 0 次 | audit log gate_1_auth=FALSE 計數 |
| 期間任何 Guardian block | ≤ 2 次（多於此值 = 紀律有問題） | audit log gate_2_risk=FALSE 計數 |
| 期間任何 Decision Lease bypass | 0 次 | audit log gate_3_lease=FALSE 計數 |
| Daily reconciliation diff | 0 次（任何 diff = 立即 RCA） | audit log rec_status='diff' 計數 |
| Operator override 對 Earn 決策 | ≤ 1 次 | audit log operator override 數量 |

**PASS** → Sprint 5 開放 auto-redeem trigger（margin headroom < 30%）
**MARGINAL** → 延後 Sprint 6-7 重評
**FAIL** → Earn governance 紀律不足，回退至 manual-only

#### 紀律 3 — Auto-redeem trigger 設計（Sprint 5+ enable 後）

| 元素 | 設計 |
|---|---|
| Trigger 條件 | trading margin headroom 跌至 < 30%（per v5.7 §4 spec） |
| Trigger 路徑 | Risk monitor → emit auto-redeem intent → 5-gate adapter → Bybit Earn API |
| Redeem amount | 補齊到 margin headroom 30%（不一次 redeem 全部，避免 Earn product 全部清空） |
| Initiator field | `'auto_redeem'`（per audit log schema） |
| Cooldown | 24h 內最多 3 次 auto-redeem（避免反復觸發） |
| Override | Operator 可顯式 disable auto-redeem（feature flag） |

### v5.7 §1 Y1 income 對齊驗證

v5.7 §1 honest Y1 income: Earn ~$26 (annualized $20 + $18, 0.69x calendar weight)

本 ADR 設計支持 Earn $26 落地路徑：

- **Sprint 1A**：APR recorder（read-only API query）— $0
- **Sprint 1B**：first manual stake $200-400 → 主帳 active Earn balance ~$200-400 — Y1 income 開始累積
- **Sprint 1B-4 (3 months)**：manual stake/redeem 持續，stake amount 漸進到 $600-800 effective
- **Sprint 5+**：若紀律驗證 PASS，auto-redeem enable，stake amount 可達 v5.7 §2 Y2 baseline $800 effective
- **Y1 末**：累積 stake amount × 36/52 calendar weight × tiered APR (~10% first $200 + ~3% rest) = ~$26

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **Earn 走簡化「stake 不檢查 Guardian」路徑** | v5.6 既有問題；違反原則 4「策略不繞風控」+ 原則 8「交易可解釋」；asset write 不可繞 Guardian |
| **Earn lease 與 trading lease 共用同一 state machine（不 retrofit）** | trading lease TTL 是 ms-sec 級，Earn 需要 min-hr 級 + `unstake_pending` 新狀態；不 retrofit 會把 Earn lease 強塞進不合身的 state machine |
| **Audit log 用既有 `trading.fills` 表** | trading.fills 是 trading-specific schema；Earn movement direction (stake/redeem) + product + APR snapshot 都不在 trading.fills schema；混在一起會破壞 trading.fills schema 純度 |
| **不做 daily reconciliation** | 違反原則 8「交易可解釋」+ 原則 9「雙重防線」；Bybit Earn 與內部 audit log 不對賬 = 對 asset write 路徑無監控 |
| **First 3 months 直接開 auto-redeem** | 違反 v5.7 §4 spec「Manual rebalance initially (first 3 months); auto after proven」+ 原則 5/6 fail-closed |
| **Earn 在 demo 完全不接入，只在 live_demo / live 開** | demo 沒有 Earn = 缺一條學習路徑；Earn 紀律驗證需要在 demo 先預演，避免 live 時才發現 surface bug |
| **Earn 5-gate 設計用 4 gate（合併 Authorization 與 Decision Lease）** | Authorization 是 *who can initiate*（Operator role + signed auth），Decision Lease 是 *what & when*（intent → execute）；合併會丟失「intent 已 lease 但 authorization 失效」這個 edge case 的可審計性 |

## Consequences

### Positive

- **Earn 接入完整 Guardian 防線** — asset write 不繞風控，對齊原則 4
- **Decision Lease retrofit 保持 state machine 純度** — 新增 `unstake_pending` state 而非污染既有 trading state
- **Audit log 完整可審計** — 每筆 stake/redeem 從 intent 到 reconciliation 都有 trace，對齊原則 8
- **Manual first 3 months 紀律驗證** — Y1 evidence-based 升級 auto-redeem 路徑，避免 Y1 一開始就 surface auto 風險
- **與 v5.7 §1 Y1 income $26 對齊** — Sprint 1A/1B 接入路徑 → Sprint 5+ auto-redeem → Y1 末 cumulative
- **5-gate adapter 設計可重用** — 未來其他 asset-write framework（如未來的 lending / staking / cross-margin migration）可套同 5 gate

### Negative / Risk

- **45 hr Earn governance 工程量（per v5.7 §4 estimate）占 Sprint 1A/1B 主要工程** — mitigation = Sprint 1A 60-80 hr 中 Earn API recorder 15 hr 提前 land、Sprint 1B 50-70 hr 中 Guardian/Lease/Audit integration 30 hr land、E1 dispatch 時明確 Earn 為 P0
- **Decision Lease retrofit 可能引入 existing state machine regression** — `unstake_pending` state 新增可能影響既有 trading lease 路徑；mitigation = E2 review + E4 regression test 強制；retrofit 從 dedicated branch + dry-run 後 land
- **Audit log schema 待 MIT review** — 候選 schema 可能在 MIT calibration 後調整；mitigation = ADR 本身 lock 設計意圖，schema 細節屬於可 amendment 範圍
- **Daily reconciliation 對 Bybit Earn API 依賴** — 若 Bybit API rate limit 不足 daily query，可能無法每日對賬；mitigation = BB 在 Sprint 1A review Bybit Earn API rate limit；不夠則退到 weekly reconciliation + warning
- **Sprint 4 結束 evaluation 主觀性** — 5 sub-criterion 都是「事件計數 + threshold」設計，但 threshold 在實際 Y1 紀律未 lock 前是估計值；mitigation = Sprint 4 結束 evaluation 報告若 verdict 與 threshold 接近邊界，自動觸發延後到 Sprint 6-7 重評（per 紀律 2 MARGINAL verdict）
- **Auto-redeem trigger 24h 內 3 次 cooldown 可能不夠** — 若 trading margin 反復跌破 30% 但又自動恢復，3 次 cooldown 後 4th time fail to redeem；mitigation = cooldown 後若仍 margin 不足 → Operator manual escalation；不允許 silent fail

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| ADR-0008 (Decision Lease state machine) | **本 ADR retrofit 既有 lease state machine**；新增 `unstake_pending` state + Earn lease ID format |
| ADR-0031 (Framework expansion — Earn governance) | **本 ADR 為 ADR-0031 Framework 1 §1.2 拆分細節**；父框架對齊 |
| 既有 Five-Gate baseline（per `docs/architecture/*`） | **本 ADR 5-gate adapter 對齊既有 Five-Gate**；gate 編號一致 |
| `auth.authorization_audit` table | **Gate 1 Authorization 紀錄路徑共用**；Earn stake intent 也寫該表 |
| `learning.guardian_block_log` table | **Gate 2 Risk envelope block 紀錄共用**；Earn-specific block reason 用 `earn_*` prefix |
| v5.7 §4 Bybit Earn governance | **本 ADR 為 §4 spec 的執行細節落地** |
| v5.7 §8 Sprint 1A Earn API APR recorder | **本 ADR 5-gate adapter 在 Sprint 1A APR recorder 之後 land** |
| v5.7 §8 Sprint 1B first manual stake $200-400 | **本 ADR 紀律 1 Manual stake 對齊 Sprint 1B timing** |
| AMD-2026-05-15-01 Stage transitions | **Earn 路徑對齊 Stage 紀律**；Earn manual → auto 升級對齊 promotion gate pattern |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | Earn stake/redeem 走 Decision Lease + Guardian + Earn API；與 trading 共用 authorization 入口 |
| 2 | 讀寫分離 | ✅ | Earn API APR query 是 read；stake/redeem 是受控寫入，走 5 gate |
| 3 | AI 輸出 ≠ 命令 | ✅ | Earn stake intent 必經 Guardian + Decision Lease + authorization；auto-redeem 屬於 risk monitor 觸發但仍走 5 gate |
| 4 | 策略不繞風控 | ✅ | Earn 是 asset movement framework；同 trading 受 Guardian 約束 |
| 5 | 生存 > 利潤 | ✅ | Manual first 3 months + auto-redeem trigger margin headroom < 30%；trading 流動性優先於 Earn yield |
| 6 | 失敗默認收縮 | ✅ | API timeout → fail-closed；daily reconciliation diff → RCA；任一 gate fail → reject |
| 7 | 學習 ≠ Live | ✅ | Manual 3 months 是學習階段；evidence-based 升級 auto |
| 8 | 交易可解釋 | ✅ | Audit log + daily reconciliation 完整可審計 |
| 9 | 雙重防線 | ✅ | 5 gate 多層 + Guardian + Decision Lease + daily reconciliation |
| 11 | Agent 最大自主 | ✅ | Agent 在 P0/P1 內可發起 Earn intent；不限縮 Agent 自主 |
| 13 | cost 感知 | ✅ | 45 hr 工程在 v5.7 §9 預算內 |
| 14 | 零外部成本 | ✅ | Bybit Earn API 不引入新付費服務 |
| 16 | Portfolio > 孤立 trade | ✅ | Earn 是 portfolio-level cash management；margin headroom check 對齊 portfolio 風險 |

## Cross-References

- **v5.7 §4 Bybit Earn governance**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:133-167`
- **v5.7 §8 Sprint 1A-1B**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:269-289`（Earn API recorder + first manual stake timing）
- **v5.7 §11 ADR-0030 提案**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:368`（本 ADR 順移為 0032 因 0030 已被 Copy Trading evidence-gated 占用）
- **v5.7 §12 governance recap**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md:359-370`
- **ADR-0008**：`docs/adr/0008-decision-lease-state-machine.md`（本 ADR retrofit 對象）
- **ADR-0031**：本批次 Framework expansion — Earn governance 父框架（本 ADR 為 §1.2 細節拆分）
- **既有 Five-Gate baseline**：`docs/architecture/*`（5-gate adapter 對齊對象）
- **Bybit Earn API spec**：`docs/references/2026-04-04--bybit_api_reference.md`（待 v5.7 §8 Sprint 1A 接入時補充 Earn endpoints 章節）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via v5.7 §4 + §11 + §12 | 2026-05-21 | 🟡 PROPOSED-pending-commit |
| TW | 本文件起草（v5.7 §12 ADR-0030 提案順移為 ADR-0032 draft） | 2026-05-21 | ✅ Drafted |
| E1 | 5-gate adapter + Decision Lease retrofit + audit log writer 實作 owner | TBD（Sprint 1A-1B） | 🟡 PENDING |
| E2 | Decision Lease retrofit regression review | TBD（Sprint 1B） | 🟡 PENDING |
| MIT | `learning.earn_movement_log` schema review + migration 編號 | TBD（Sprint 1A） | 🟡 PENDING |
| BB | Bybit Earn API rate limit + ToS review | TBD（Sprint 1A） | 🟡 PENDING |
| FA | Sprint 4 結束 Earn manual 3 months 紀律 verdict | TBD（Sprint 4） | 🟡 PENDING |
| PM | Sprint 4 結束紀律 verdict 仲裁 + auto-redeem enable 決策 | TBD（Sprint 4-5 銜接） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0032 — Bybit Earn Asset Movement Guardian: 5-Gate Adapter + Decision Lease Retrofit + Audit Log (Proposed)*
