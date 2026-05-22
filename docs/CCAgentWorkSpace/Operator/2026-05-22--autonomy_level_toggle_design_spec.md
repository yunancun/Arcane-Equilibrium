# Autonomy Level Toggle — Design Spec

Date: 2026-05-22
Status: **PROPOSED — pending operator confirm**（AMD-2026-05-21-01 v2 §Decision 1 Q2 拍板 IMPL 設計依據）
Owner: PA
Operator Source: 2026-05-22 directive Q2「PM 推薦 Path B 設一個自動等級，CC 設另外一個等級，可以在設置裡切換 autonomy level」
Related:
- AMD-2026-05-21-01 v2（`docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`，v2 draft 未 cascade patch 狀態，本 spec 為其 §Decision 1 IMPL 設計依據）
- ADR-0008（Decision Lease state machine baseline；不動）
- ADR-0034（LAL 0-4 per-decision approval depth；本 spec Level toggle 為其 governance 上層正交維度）
- ADR-0040（Multi-Venue Gate Spec §Decision 5 venue change always operator；本 spec 與其交互在 §6）
- ADR-0010（TimescaleDB hypertable Guard A/B/C migrations）
- ADR-0011（V### migration Linux PG empirical dry-run mandatory）
- AMD-2026-05-15-01（Stage 0R-4 strategy promotion progress；正交維度）
- CLAUDE.md §二 16 根原則 + §四 Hard Boundaries
- CC v2 compliance preview（`docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--amd_2026_05_21_01_v2_fully_autonomy_compliance_preview.md`）

---

## §1 概念與正交維度

### 1.1 Autonomy Level Toggle 是什麼

**Autonomy Level** 是 system-wide policy 設置，控制「在 fail-safe 自動觸發 robustness 為主防線」的設計 thesis 下，**哪些 protected/opt-in path 走 LAL 自動路徑、哪些仍走 operator approve manual**。

v2 AMD §Decision 1 列出 14 條 path（原 v1 protected 6 條 a-f + opt-in 8 條 g-n）+ 5-gate operator role + venue change（ADR-0040 §Decision 5），這 16 個 governance surface 並非「全自動」或「全手動」二分；operator 2026-05-22 Q2 拍板「設一個自動等級 + 一個 CC 等級 + 可切換」即把這個 thesis spectrum 顯式化為 **2 個 system-wide preset**：

- **Level 1 (Conservative — 預設 / CC stance)**：5-gate operator role HMAC 簽署永鎖 + protected (a)-(f) 6 條 operator approve manual + opt-in (g)-(n) 8 條 auto with §Decision 2 5 條 fail-safe hard requirements
- **Level 2 (Standard — PM Path B)**：5-gate operator role HMAC 簽署永鎖 + venue change（ADR-0040 §Decision 5）operator approve manual + 其他 protected (a)/(c)/(d)/(e)/(f) 5 條 + opt-in (g)-(n) 8 條 = 13 條 auto with §Decision 2 5 條 fail-safe hard requirements

**Default = Level 1 Conservative**（fail-closed posture；engine cold start 從 DB 讀；DB 無紀錄 → Level 1）。

### 1.2 與既有維度的正交關係

Autonomy Level **與下列既有維度全部正交**，三維度乘積構成最終 per-decision approval 行為：

| 維度 | 對象 | 表示什麼 | 顆粒度 |
|---|---|---|---|
| **Autonomy Level** | System-wide policy | 哪些 protected/opt-in path 走 LAL auto vs operator approve | 1 個 global state（Level 1 / Level 2） |
| **LAL 0-4**（per ADR-0034） | Per-decision approval depth | 該決策 lease 需要多深的 approval gate | Per-decision（每筆 emit 時打 lal_level） |
| **Stage 0R-4**（per AMD-2026-05-15-01） | Per-strategy promotion progress | 該 strategy 走到多遠的 live readiness | Per-strategy |

**讀法**：
- Level 決定「**該 path 是否進入 LAL auto-eligible 集合**」
- LAL 決定「**該 path 在 auto-eligible 集合內仍需通過哪些 per-decision approval gate criteria**」（per ADR-0034 §Decision 5 6 條 hard gate + AMD v2 §Decision 2 5 條 fail-safe hard requirements）
- Stage 決定「**該 strategy 物理上能否進入該 LAL path**」（per ADR-0034 LAL ↔ Stage 對齊矩陣）

**核心 invariant**：**Level 只動 path 集合邊界，不動 LAL gate eligibility 紀律 + 不動 Stage 對齊矩陣 + 不動 §Decision 2 5 條 fail-safe hard requirements**。

### 1.3 為什麼是 system-wide policy 而非 per-decision flag

| 替代方案 | 棄因 |
|---|---|
| **Per-decision Level 標記** | 沒有意義 — Level 是 governance posture 不是 per-decision 屬性；每筆 lease 都打 level 是 over-engineering |
| **Per-strategy Level** | Sub-agent / reviewer 在跨策略決策時無法判斷哪個 Level 主導；違反 thesis 一致性 |
| **無 Level 概念（v1 立場）** | CC + PM 立場分歧無 governance surface 表達；operator 拍板要兩個 preset 切換 |
| **3+ Level（細粒度 spectrum）** | 過度設計；operator 拍板只要 2 個；增加 IMPL + UX + audit 複雜度且無 evidence-based 需求 |

### 1.4 與 v2 §Decision 2 5 條 Fail-Safe Hard Requirements 的關係

**critical invariant**：Level 1 / Level 2 兩 level 下，**所有進入 auto path 的 decision 仍須通過 §Decision 2 5 條 fail-safe hard requirements**（per AMD-2026-05-21-01 v2 §Decision 2）：

1. **4.1** 每個 auto path 必有 deterministic hard gate（不依賴 operator click）
2. **4.2** Hard gate 必 evidence-based（樣本 N ≥ 30 + Wilson CI 95% lower bound + 30d rolling）
3. **4.3** 任何 gate FAIL → 自動 reject + 自動 alert + 自動 fallback to advisory
4. **4.4** Regime change / Guardian alert / 5-gate kill → 自動 freeze auto path
5. **4.5** Fail-safe code path 不可被 runtime config override（compile-time hard-coded only）

**Level toggle 不影響 §Decision 2**。Level 改的是「哪些 path 進入 auto-eligible 集合」；§Decision 2 是「進入集合後仍須 PASS 的硬門控」。Level toggle 不是「跳過 fail-safe」的後門。

---

## §2 Level 1 vs Level 2 完整對照矩陣

### 2.1 14 條 path + 5-gate + venue change 完整對照

| # | Path | 對應 v2 §Decision 1 分類 | Level 1 行為（Conservative / CC） | Level 2 行為（Standard / PM Path B） | 依賴 source |
|---|---|---|---|---|---|
| **5-gate-A** | Python `live_reserved` | hard-locked baseline | HMAC sign manual + Operator role | HMAC sign manual + Operator role | CLAUDE.md §四 / ADR-0008 |
| **5-gate-B** | Python Operator role | hard-locked baseline | HMAC sign manual + Operator role | HMAC sign manual + Operator role | CLAUDE.md §四 |
| **5-gate-C** | `OPENCLAW_ALLOW_MAINNET=1` | hard-locked baseline | env-var manual | env-var manual | CLAUDE.md §四 |
| **5-gate-D** | Valid secret slot | hard-locked baseline | secret slot manual + per-venue（per ADR-0040 §Decision 2）| 同 Level 1 | ADR-0040 §Decision 2 |
| **5-gate-E** | Signed `authorization.json` | hard-locked baseline | renew/approve manual path（不可手寫） | 同 Level 1 | CLAUDE.md §四 |
| **(a)** | Stage LAL 3-4 promotion | v1 protected → v2 auto-eligible | **operator approve manual** | auto with §Decision 2 fail-safe 全 PASS | ADR-0034 §Decision 6 LAL ↔ Stage 對齊 + AMD v2 §Decision 1 |
| **(b)** | 5-gate live boundary toggle | v1 protected → v2 auto-eligible（但 5-gate 永鎖） | **operator approve manual** | **operator approve manual**（5-gate 永鎖永遠不可繞）| CLAUDE.md §四 / AMD v2 §Decision 1 (b) |
| **(c)** | Copy Trading enable | v1 protected → v2 auto-eligible | **operator approve manual** | auto with ADR-0030 4-Gate + §Decision 2 fail-safe 全 PASS | ADR-0030 + AMD v2 §Decision 1 (c) |
| **(d)** | Auto-Allocator activation | v1 protected → v2 auto-eligible | **operator approve manual** | auto with ADR-0034 LAL Tier 2 gate criteria + §Decision 2 fail-safe 全 PASS | ADR-0034 §Decision 5 + AMD v2 §Decision 1 (d) |
| **(e)** | Kill criteria 觸發 | v1 protected → v2 auto-trigger（既設 fail-closed） | auto-trigger（既設）+ §Decision 2 fail-safe 全 PASS | 同 Level 1（既設 fail-closed 兩 level 都 auto）| AMD v2 §Decision 1 (e) |
| **(f)** | ADR-debt land | v1 protected → v2 auto-eligible | **operator approve manual** | auto with §Decision 2 fail-safe 全 PASS + R4 cross-ref 自動 verify | AMD v2 §Decision 1 (f) |
| **(g)** | LAL 1 intra-strategy reparam | v1 opt-in → v2 auto-eligible | auto with §Decision 2 fail-safe 全 PASS | 同 Level 1 | ADR-0034 §Decision 5 + AMD v2 §Decision 1 (g) |
| **(h)** | LAL 2 cross-strategy reweight | v1 opt-in → v2 auto-eligible | auto with §Decision 2 fail-safe 全 PASS | 同 Level 1 | ADR-0034 §Decision 5 + AMD v2 §Decision 1 (h) |
| **(i)** | M2 always-on overlay | v1 opt-in → v2 auto-eligible | auto with §Decision 2 fail-safe 全 PASS | 同 Level 1 | AMD v2 §Decision 1 (i) |
| **(j)** | M3 Tier 1+2 health degradation | v1 opt-in → v2 auto-trigger（既設 fail-closed） | auto-trigger（既設）+ §Decision 2 fail-safe 全 PASS | 同 Level 1 | ADR-0042 + AMD v2 §Decision 1 (j) |
| **(k)** | M6 ≤30% reward weight adjustment | v1 opt-in → v2 auto-eligible | auto with §Decision 2 fail-safe 全 PASS | 同 Level 1 | ADR-0043 + AMD v2 §Decision 1 (k) |
| **(l)** | M7 demote enforced 14d × 50% | v1 opt-in → v2 auto-eligible | auto with §Decision 2 fail-safe 全 PASS | 同 Level 1 | ADR-0044 + AMD v2 §Decision 1 (l) |
| **(m)** | M8 anomaly active trigger Y2 | v1 opt-in → v2 auto-eligible | auto with §Decision 2 fail-safe 全 PASS（Y2 onset 後）| 同 Level 1 | AMD v2 §Decision 1 (m) |
| **(n)** | M10 capital tier evaluation | v1 opt-in → v2 auto-eligible | auto with §Decision 2 fail-safe 全 PASS | 同 Level 1 | AMD v2 §Decision 1 (n) |
| **venue** | Venue change（ADR-0040 §Decision 5） | v2 §Decision 1「venue change」獨立列 | **operator approve manual**（per ADR-0040 §Decision 5 不動）| **operator approve manual**（Q2 拍板「venue change 兩 level 都不動」） | ADR-0040 §Decision 5 + Q2 拍板 |

### 2.2 矩陣讀法 + 不變量

- **5-gate 5 條（A-E）**：永遠 manual + Operator role + HMAC 簽署；兩 level 都不動；**hard-coded compile-time invariant**（per §7.5）
- **Venue change**：per Q2 拍板「兩 level 都不動 venue」+ 與 ADR-0040 §Decision 5 對齊；雖 AMD v2 §Decision 1 列為「auto with 6 條 hard gate 自動 verify 全 PASS」但 Q2 在 Level toggle 設計階段顯式 carve out
- **Kill criteria (e)** + **M3 health (j)**：既設 fail-closed auto-trigger；兩 level 都 auto；Level toggle 不影響
- **Level 1 manual scope** = (a) + (b) + (c) + (d) + (f) + venue = **6 條 manual**（含 (b) 5-gate 永鎖 + venue）
- **Level 2 manual scope** = (b) + venue = **2 條 manual**（5-gate 永鎖 + venue carve-out）
- **Level 1 → Level 2 切換語意** = (a)/(c)/(d)/(f) 4 條從 manual 升為 auto with §Decision 2 fail-safe

### 2.3 雙 level 共同不變量（cross-level invariants）

無論 Level 1 / Level 2，下列 6 條不變量必成立（不可被 toggle override）：

1. **5-gate 5 條永鎖**：HMAC sign + Operator role + env-var + secret slot + authorization.json renew path — 兩 level 都 manual（per CLAUDE.md §四）
2. **Venue change 永鎖**：per ADR-0040 §Decision 5 + Q2 拍板，兩 level 都 manual
3. **§Decision 2 5 條 fail-safe hard requirements** 對所有 auto path 都生效（per §1.4）
4. **每筆 auto decision 仍 emit individual lease**（per ADR-0034 §Decision 1，不接受 umbrella lease 或 aggregate counter）
5. **Decision Lease state machine 不變**（per ADR-0008 baseline；emit / sign / settle / replay / Guardian gate 全保留）
6. **三路冗餘通知**（Slack + email + Console banner）對所有 auto decision + 所有 Level toggle action 都 emit（per AMD v2 §Decision 3.1）

---

## §3 DB Schema（per ADR-0011 Linux PG dry-run mandatory）

### 3.1 設計目標

- **單一權威 state**：當前 Autonomy Level 必有 single row of truth 在 DB；engine restart 從 DB 讀
- **完整 audit chain**：所有 Level 切換進 append-only audit table；INSERT-only 無 UPDATE/DELETE auto path（per AMD v2 §Decision 3.2 audit immutability）
- **與既有 `learning.lal_toggle_audit` 對齊**：Level toggle 是 governance-layer toggle，與 LAL per-strategy toggle 正交但設計範式對齊（actor / before / after / 2FA result / timestamp）

### 3.2 新表 1：`system.autonomy_level_config`（當前狀態 single row）

```sql
-- placeholder V### number；具體編號由後續 PA dispatch 階段拍（與 cascade patch V### 隊列協調）
CREATE TABLE IF NOT EXISTS system.autonomy_level_config (
    -- 設計為 single-row table；row id 永遠 = 1
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),

    -- 當前 Autonomy Level（1 = Conservative / CC stance，2 = Standard / PM Path B）
    current_level smallint NOT NULL CHECK (current_level IN (1, 2)) DEFAULT 1,

    -- 最近一次切換時間（UTC）
    last_switched_at timestamptz NOT NULL DEFAULT now(),

    -- 切換者（actor identifier；對應 operator role authentication 結果）
    switched_by text NOT NULL DEFAULT 'system_default',

    -- 切換理由（operator 必填；自由文本，audit 用途）
    switch_reason text NOT NULL DEFAULT 'cold_start_default_level_1',

    -- bookkeeping
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- 確保只有一行（Guard）
CREATE UNIQUE INDEX IF NOT EXISTS uniq_autonomy_level_config_singleton
    ON system.autonomy_level_config (id);

-- updated_at trigger（與既有 timestamp pattern 對齊）
CREATE OR REPLACE FUNCTION system.touch_autonomy_level_config()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_touch_autonomy_level_config
    ON system.autonomy_level_config;
CREATE TRIGGER trg_touch_autonomy_level_config
    BEFORE UPDATE ON system.autonomy_level_config
    FOR EACH ROW EXECUTE FUNCTION system.touch_autonomy_level_config();

-- Cold start seed（idempotent）
INSERT INTO system.autonomy_level_config (id, current_level, switched_by, switch_reason)
    VALUES (1, 1, 'system_default', 'cold_start_default_level_1')
    ON CONFLICT (id) DO NOTHING;
```

**Guard 對齊**（per ADR-0010）：
- **Guard A**：`CREATE TABLE IF NOT EXISTS` — table 重 create 不破壞既有 row
- **Guard B**：N/A — 本表初版無 ADD COLUMN
- **Guard C**：N/A — 本表為 single-row config 不上 hypertable

### 3.3 新表 2：`system.autonomy_level_switch_audit`（append-only history）

```sql
-- placeholder V### number；與 §3.2 同 V### migration 或 next V### 由後續 dispatch 階段拍
CREATE TABLE IF NOT EXISTS system.autonomy_level_switch_audit (
    audit_id bigserial PRIMARY KEY,

    -- 切換時間（UTC ms 精度）
    switched_at timestamptz NOT NULL DEFAULT now(),

    -- Actor + auth result
    actor text NOT NULL,
    actor_role text NOT NULL CHECK (actor_role IN ('operator', 'system_default')),

    -- Before / after level（Guard against silent corruption）
    level_before smallint NOT NULL CHECK (level_before IN (1, 2)),
    level_after smallint NOT NULL CHECK (level_after IN (1, 2)),
    CHECK (level_before != level_after OR actor_role = 'system_default'),

    -- 2FA verification result（Operator switch 必填；system_default 為 NULL）
    twofa_verify_result text NULL CHECK (twofa_verify_result IN ('PASS', 'FAIL', NULL)),
    twofa_method text NULL,  -- 'TOTP' / 'hardware_key' / NULL

    -- 切換理由（operator 自由文本必填；system_default 為固定字串）
    switch_reason text NOT NULL,

    -- 是否屬於 emergency override path（24h cooldown 內強制切換；per §4.2）
    emergency_override boolean NOT NULL DEFAULT false,
    emergency_override_reason text NULL,
    CHECK (
        (emergency_override = false) OR
        (emergency_override = true AND emergency_override_reason IS NOT NULL)
    ),

    -- 三路通知 emit 結果（per AMD v2 §Decision 3.1）
    notification_slack_status text NULL CHECK (notification_slack_status IN ('SENT', 'FAILED', 'SKIPPED', NULL)),
    notification_email_status text NULL CHECK (notification_email_status IN ('SENT', 'FAILED', 'SKIPPED', NULL)),
    notification_banner_status text NULL CHECK (notification_banner_status IN ('SHOWN', 'FAILED', 'SKIPPED', NULL)),

    -- bookkeeping
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Append-only constraint（per AMD v2 §Decision 3.2 audit immutability）
-- DENY UPDATE / DELETE on auto path；operator manual data-correction 走 ADR-0006 紀律
REVOKE UPDATE, DELETE ON system.autonomy_level_switch_audit FROM PUBLIC;
REVOKE UPDATE, DELETE ON system.autonomy_level_switch_audit FROM trading_ai;

-- Index for last-switched query（per §4.2 24h cooldown check）
CREATE INDEX IF NOT EXISTS idx_autonomy_audit_switched_at
    ON system.autonomy_level_switch_audit (switched_at DESC);

CREATE INDEX IF NOT EXISTS idx_autonomy_audit_actor_role
    ON system.autonomy_level_switch_audit (actor_role, switched_at DESC);
```

**Guard 對齊**（per ADR-0010）：
- **Guard A**：`CREATE TABLE IF NOT EXISTS` — table 重 create 不破壞既有 audit row
- **Guard B**：N/A — 本表初版無 ADD COLUMN
- **Guard C**：N/A — switched_at index 是普通 B-tree，非 hypertable；audit table 規模小（預期 lifetime < 1000 row）不需 hypertable

### 3.4 V### migration 路徑

| 項目 | 設計 |
|---|---|
| V### number | **placeholder**；具體 V### number 由後續 PA cascade patch dispatch 階段協調拍板（與 v2 AMD §9.5 V112 schema spec patch 隊列共識）|
| 命名建議 | `V###_autonomy_level_toggle_schema.sql`（與 v2 V112 LAL schema patch 在同一 wave 落地） |
| 依賴 | 不依賴其他 V### migration（schema 完全 standalone）|
| Idempotency | `CREATE TABLE IF NOT EXISTS` + `INSERT ON CONFLICT DO NOTHING` + `CREATE INDEX IF NOT EXISTS` — apply 兩次安全 |
| Dry-run mandatory | per ADR-0011，**Linux PG empirical dry-run before E1 IMPL sign-off**；不接受 Mac mock pytest 通過就 land |
| Dry-run 必驗 | (1) Guard A 雙 apply 不錯 (2) Insert seed row 後 current_level=1 (3) UPDATE 觸發 updated_at touch (4) Append-only constraint：trading_ai role 嘗試 UPDATE / DELETE 必拒 (5) CHECK constraint：current_level=3 必拒 (6) Audit insert with twofa_verify_result='FAIL' 必成功（記錄 fail 嘗試） |
| Rollback | 本 spec 不設計 rollback（schema additive；rollback 需手動 DROP TABLE 走 ADR-0006 數據訂正紀律）|

### 3.5 GUI handler PG 訪問權限

- **READ**：`system.autonomy_level_config` row id=1 可被 `trading_ai`、`trading_admin` 讀（GUI Console banner 顯示當前 Level）
- **WRITE**：`system.autonomy_level_config` 只可被 `trading_admin` 透過 explicit auth handler 寫；`trading_ai` 無 write 權
- **APPEND**：`system.autonomy_level_switch_audit` 只可被 `trading_admin` INSERT；UPDATE / DELETE 全拒（per §3.3 REVOKE）

---

## §4 切換 Governance

### 4.1 Auth 要求（per CLAUDE.md §四 hard boundary）

| 維度 | 要求 |
|---|---|
| Role | **Operator role only**（per CLAUDE.md §四 5-gate B）；不接受 Viewer / Analyst |
| 2FA | **TOTP 或 hardware key confirm**（per ADR-0034 §Decision 4 toggle auth pattern 對齊） |
| Console warning | 切換前顯式 warning banner：「Switching to Level X will enable auto-execution for N of 14 protected/opt-in items; this changes system-wide autonomy posture per AMD-2026-05-21-01 v2 §Decision 1.」 |
| Switch reason | Operator 自由文本必填（最少 20 字元；audit 用途） |
| HMAC chain | switch audit row 必含 HMAC signature（per Operator 三條 design DNA 之 auditability）；HMAC 用 `authorization.json` 同等 secret slot |

### 4.2 Cooldown — 24h 切換間隔

**規則**：Level toggle 切換成功後 24h 內**不可再切換**（防快速切換攻擊；防 operator 反覆切換造成系統震盪）。

**強制路徑**：Engine check `system.autonomy_level_config.last_switched_at`；若 `now() - last_switched_at < INTERVAL '24 hours'` → 切換拒絕 + emit alert + 寫 audit。

**Emergency override path**：
- Operator 透過 emergency override flag 強制切換（不繞 cooldown）
- Emergency override 必填 `emergency_override_reason`（per §3.3 audit table CHECK constraint）
- Emergency override 必額外觸發 Slack + email + Console banner 三路通知 + 標記為「emergency_override=true」audit
- Emergency override **不繞 2FA + Operator role**；只繞 24h cooldown

**反模式（明示禁止）**：
- (a) Cooldown < 24h（如 1h / 6h）→ 防快速切換不足
- (b) Cooldown 用 in-memory cache 不查 DB → engine restart 後 reset 失效
- (c) Emergency override 不需 reason → audit chain 無法分辨意圖
- (d) Emergency override 自動 grant 給 system_default actor → 違反 Operator role gate

### 4.3 生效時間

| 場景 | 生效時機 |
|---|---|
| 切換成功 commit | **立即生效**（DB row updated_at touched 後，state machine 下一個 lease emit 時 honor 新 Level） |
| In-flight lease（已 emit 未 acquired） | **走切換前 Level**（lease 已 emit 含 lal_level 字段；retroactive change 違反 ADR-0008 lease 完整性） |
| In-flight lease（已 acquired 未 settled） | **走切換前 Level**（per ADR-0008 lease lifecycle integrity） |
| Engine restart | Cold start 從 DB 讀 `current_level`；DB row 不存在或 read fail → fail-closed default = Level 1 |

**讀法**：Level 切換是 **forward-looking policy change**；不 retroactive 影響既有 lease。已 emit 的 lease 帶當時的 level snapshot，繼續走完 lifecycle。

### 4.4 Notification — 三路冗餘

per AMD v2 §Decision 3.1 三路冗餘紀律：

| 通道 | SLA | 失敗 fallback |
|---|---|---|
| Slack | ≤ 10s emit notification 到 operator-designated channel | Slack fail 不阻其他兩路；Slack status 寫 audit `notification_slack_status='FAILED'` |
| Email | ≤ 60s emit email | Email fail 不阻其他兩路；audit `notification_email_status='FAILED'` |
| Console banner | ≤ 5s 全局 banner 顯示「Autonomy Level switched to Level X @ timestamp」 + 24h 內可見 | banner fail 不阻其他兩路；audit `notification_banner_status='FAILED'` |
| **三路全 fail** | **freeze 切換 + rollback DB row + emit alert**（per AMD v2 §Decision 3.1 三路全 fail = freeze auto path 直到通道恢復）|

### 4.5 Audit 完整性

每次切換進 `system.autonomy_level_switch_audit` row：
- `actor` / `actor_role`（must be 'operator' for user-initiated switch；'system_default' 只允許 cold start seed）
- `level_before` / `level_after`
- `twofa_verify_result` ('PASS' / 'FAIL'；FAIL 也寫 audit row 標記嘗試失敗)
- `switch_reason` 必填
- `emergency_override` boolean + reason（若 emergency override）
- 三路通知 status

**Append-only invariant**：per §3.3 REVOKE UPDATE/DELETE；只有 ADR-0006 數據訂正紀律可動 audit row（且訂正本身留 ADR-0006 audit trail）。

---

## §5 GUI Integration

### 5.1 切換點位置

**Console tab 歸屬**：Governance tab / Settings sub-section（per A3 console tab 歸屬決策；與 LAL toggle 同 tab 但獨立 sub-section）。

**Read-only display**：Console 全局永遠顯示當前 Level（banner 角落 + Governance tab Settings header）+ last_switched_at + switched_by + switch_reason。

### 5.2 UI Flow（切換）

```
[1] Operator 在 Governance tab / Settings 點「Switch Autonomy Level」 button
    └─ Console 顯示當前 Level 1 → 提議切到 Level 2（或反向）

[2] 系統顯式 warning modal：
    "Switching to Level 2 (Standard / PM Path B) will enable auto-execution
     for 13 of 14 protected/opt-in items in AMD-2026-05-21-01 v2 §Decision 1.
     5-gate operator role HMAC signing + venue change remain manual.
     This changes system-wide autonomy posture.
     Type 'CONFIRM SWITCH TO LEVEL 2' to proceed."
    └─ Operator type 確認字串

[3] Switch reason 自由文本必填（≥ 20 字元；audit 用途）

[4] 2FA confirm modal：
    "Enter TOTP / hardware key signature"
    └─ Verify 結果寫 audit twofa_verify_result

[5] System verify：
    (a) Operator role check（CLAUDE.md §四 5-gate B）
    (b) 2FA result PASS
    (c) 24h cooldown check（query last_switched_at）
        ├─ PASS → 進 step 6
        └─ FAIL → 顯示「24h cooldown active；emergency override path?」
                  └─ Yes → 走 emergency override path（補 reason 後進 step 6）
                  └─ No  → 切換 abort + 寫 audit twofa PASS 但 24h cooldown FAIL
    (d) System assertion：current_level != target_level（防 no-op switch）

[6] System execute：
    (a) UPDATE system.autonomy_level_config SET current_level=target,
        switched_by=actor, switch_reason=reason, last_switched_at=now()
    (b) INSERT system.autonomy_level_switch_audit (...)
    (c) Emit Slack + email + Console banner 三路通知（≤ 10s / ≤ 60s / ≤ 5s SLA）
    (d) Console banner 顯示「Autonomy Level: Level X (Conservative/Standard) -
        switched 2026-XX-XX @ HH:MM by <actor>」

[7] 引擎下一個 lease emit 時 honor 新 Level
```

### 5.3 冷啟動默認

| 場景 | 行為 |
|---|---|
| Engine 首次啟動（DB row 不存在） | Cold start seed `current_level=1`（per §3.2 INSERT ON CONFLICT DO NOTHING）+ actor='system_default' + reason='cold_start_default_level_1' |
| Engine restart（DB row 存在） | Read `current_level` from DB；honor 之 |
| Engine restart（DB read fail） | **fail-closed default = Level 1**（per CLAUDE.md §二 原則 6「失敗默認收縮」）+ emit Console banner red warning「Autonomy Level config read failed; defaulted to Level 1 Conservative」 + alert operator |

### 5.4 Read-only display 設計

| 顯示元素 | 內容 |
|---|---|
| Console 全局 banner（top right corner） | "Autonomy Level: Level X" + 顏色 code（Level 1 = blue / Level 2 = amber）|
| Governance tab Settings header | "Current Level: X (Conservative/Standard) - Last switched: YYYY-MM-DD HH:MM UTC by <actor> - Reason: <reason>" |
| Settings sub-section detail panel | 14 path × 2 level 完整對照表（per §2.1）+ 5-gate 永鎖 + venue change 永鎖 marker |

### 5.5 GUI handler 設計約束

- **No fake-success**：GUI handler 必走 PG 真 write（per feedback_no_dead_params + CLAUDE.md §七「GUI write surfaces must write through Rust authority, not Python fake-success paths」）
- **Authorization 對齊**：handler 必走 既有 Operator role authentication path（per ADR-0034 §Decision 4 toggle auth handler pattern）
- **JS sign-off**：per `feedback_gui_node_check_sop`，GUI JS 變動必跑 `node --check` 才算 sign-off
- **Vanilla JS**：per CLAUDE.md §七 GUI is Vanilla JS；不引入 React/Vue/Angular

---

## §6 與 LAL Gate 互動

### 6.1 LAL 0-4 紀律不變

per ADR-0034，LAL 0-4 對 per-decision approval depth 的紀律**不被 Level toggle 影響**：

| LAL | Approval depth | Level 1 行為 | Level 2 行為 |
|---|---|---|---|
| **LAL 0** | per-fill | 既有 Guardian auto（兩 level 都 auto） | 同 Level 1 |
| **LAL 1** | intra-strategy reparam | auto with §Decision 2 fail-safe（per (g)） | 同 Level 1 |
| **LAL 2** | cross-strategy reweight | auto with §Decision 2 fail-safe（per (h)） | 同 Level 1 |
| **LAL 3** | new strategy promotion | **operator approve manual**（per (a) Level 1 manual） | auto with §Decision 2 fail-safe（per (a) Level 2 auto） |
| **LAL 4** | capital structure / venue change | **operator approve manual**（per venue + (d) Level 1 manual） | **operator approve manual** for venue + auto for (d) Auto-Allocator activation |

### 6.2 Auto path 在 Level + LAL 雙維度下的 eligibility

每筆 decision 進入 auto path 的條件是 **Level allow** AND **LAL gate eligibility**：

```
auto_eligible(decision) =
    Level allows this decision path（per §2.1 矩陣）
    AND
    LAL gate eligibility（per ADR-0034 §Decision 5 6 條 hard gate）
    AND
    §Decision 2 5 條 fail-safe hard requirements（per AMD v2 §Decision 2）
    AND
    Stage compatible（per ADR-0034 LAL ↔ Stage 對齊矩陣）
```

**任一 fail → fallback to advisory（v5.7 baseline operator manual approve queue）**。

### 6.3 Level 1 下的 protected (a) 拒絕路徑（範例）

| 路徑 | 行為 |
|---|---|
| (a) Stage LAL 3-4 promotion 在 Level 1 下 | 即使 LAL gate 6 條 PASS + §Decision 2 5 條 PASS + Stage compatible，**Level 1 政策拒絕進入 auto path** |
| 拒絕後 fallback | 進入 advisory queue（v5.7 baseline）操作員 Console manual approve |
| 拒絕 emit lease 嗎？ | **必 emit lease**（per ADR-0034 §Decision 1）但 lease state 為「advisory pending operator approval」非 auto-signed |
| 拒絕 emit 三路通知嗎？ | **必 emit**（per §Decision 3.1）含「rejected by Level 1 policy: protected (a) operator-approve-only」 |

**核心 invariant**：Level 1 拒絕 ≠ 沉默拒絕；每筆被 Level policy 拒絕的 decision 仍走 lease emit + 三路通知 + advisory queue。

### 6.4 §Decision 2 5 條 hard requirements 對兩 level 雙生效

per §1.4 + 重申：

| Hard requirement | Level 1 下 | Level 2 下 |
|---|---|---|
| 4.1 Deterministic hard gate | 所有 Level 1 auto-eligible path 全生效 | 所有 Level 2 auto-eligible path 全生效（含原 protected (a)/(c)/(d)/(f)） |
| 4.2 Evidence-based gate（N ≥ 30 + Wilson CI + 30d rolling） | 同上 | 同上 |
| 4.3 Gate FAIL → fallback advisory | 同上 | 同上 |
| 4.4 Regime change / Guardian / 5-gate kill → freeze auto path | 同上 | 同上 |
| 4.5 Fail-safe code path compile-time hard-coded | 同上（含 Level toggle 自身不可繞 fail-safe；per §7.5）| 同上 |

---

## §7 與 §Decision 2 Fail-Safe Hard Requirements 對齊

### 7.1 §Decision 2 4.1 — Deterministic Hard Gate

| Level | 對 4.1 的對應 |
|---|---|
| Level 1 | 8 條 auto-eligible path((g)-(n) + (e) auto-trigger) 各對應 deterministic hard gate（LAL gate / M3 health domain / M7 decay state / etc.）；Level toggle 自身不影響 gate determinism |
| Level 2 | 13 條 auto-eligible path（Level 1 8 條 + (a)/(c)/(d)/(f) 4 條）各對應 deterministic hard gate；Level toggle 不放寬 gate determinism；4 條新增 path 對應 gate 必明示 source ADR commit hash 紀錄 |

### 7.2 §Decision 2 4.2 — Evidence-Based（N ≥ 30 + Wilson CI + 30d rolling）

| Level | 對 4.2 的對應 |
|---|---|
| Level 1 | 8 條 auto-eligible path 對應 evidence-based gate（per ADR-0034 §Decision 3 + ADR-0042/0043/0044 module spec）；Level toggle 不放寬樣本 N / Wilson CI / 窗口長度紀律 |
| Level 2 | 13 條 auto-eligible path 對應 evidence-based gate；新增 4 條 path（(a)/(c)/(d)/(f)）evidence-based gate 由各 source ADR 提供（ADR-0030 4-Gate Copy Trading / ADR-0034 §Decision 5 6 條 hard gate Auto-Allocator / R4 cross-ref 自動 verify ADR-debt） |

### 7.3 §Decision 2 4.3 — Gate FAIL → 自動 reject + alert + fallback advisory

| Level | 對 4.3 的對應 |
|---|---|
| Level 1 | 任一 gate FAIL → fallback to advisory（operator manual approve queue）+ Slack + email + Console banner |
| Level 2 | 同 Level 1；4 條新增 auto path gate FAIL 路徑與既有 (g)-(n) 行為一致；Level toggle 不創造「Level 2 下 gate FAIL silent」分支 |

### 7.4 §Decision 2 4.4 — Freeze Auto Path（regime change / Guardian / 5-gate kill）

| Level | 對 4.4 的對應 |
|---|---|
| Level 1 | 6 條 freeze trigger（M3 health domain CRITICAL/DEGRADED / M7 lifecycle DECAY_ENFORCED/RETIRED / Guardian alert active / 5-gate kill / M8 anomaly Y2 / regime change）任一命中 → Level 1 內所有 auto path freeze；freeze 不縮 Level 範圍 |
| Level 2 | 同 Level 1；Level 2 內 13 條 auto path 全 freeze；freeze 期間 Level toggle 切換被拒絕（防 freeze 期間 operator 切換 Level 規避 freeze 紀律）|

**新增 invariant（per §7.4）**：**Freeze state active 期間 Level toggle 禁切換**；只有 freeze clear + 30d cooling window 後可切換（per AMD v2 §Decision 2.4 freeze 持續紀律）。

### 7.5 §Decision 2 4.5 — Compile-Time Hard-Coded（不可 runtime config override）

**核心 invariant**：**Autonomy Level toggle 自身不可繞 fail-safe**；Level 改 path 集合邊界，**不可改 §Decision 2 5 條 hard requirements 任一條**。

| 元素 | 設計 |
|---|---|
| Level toggle 代碼路徑 | E1 IMPL 必把 Level → auto-eligibility 邏輯寫在 Rust `openclaw_engine` compile-time const 路徑；DB row 提供 current_level 值但 mapping 邏輯 hard-coded |
| 允許 runtime tune | 只有「Level 1 / Level 2 二選一」可 runtime change；Level 1 對應 path 集合 + Level 2 對應 path 集合本身 hard-coded |
| 不允許 runtime tune | (a) 「Level 1 下放寬 (a) 為 auto」runtime override (b) 「Level 2 下動態擴展 venue change 為 auto」(c) 「§Decision 2 5 條 hard requirements 任一條被 Level toggle 繞過」 |
| E2 review 必 grep | `level_toggle_override` / `disable_failsafe` / `bypass_fail_safe_for_level_X` patterns 確保零出現 |

---

## §8 Risk + Mitigation

### 8.1 Attack vectors（≥ 5 條）

| # | Attack vector | Mitigation |
|---|---|---|
| **1** | 快速 level 切換攻擊 — operator session 被 hijack 後反覆切換 Level 1↔Level 2 造成系統震盪 + auto path eligibility 反覆變化 + lease emit 紀錄不一致 | **24h cooldown**（per §4.2）+ Emergency override 需顯式 reason + 三路通知 audit；快速切換攻擊上限 1次/24h，且每次留 audit trail |
| **2** | 切換 audit log 被偽造 — 攻擊者 INSERT 假 audit row 標記「Level 已切換」但實際未切換 | **Append-only constraint**（per §3.3 REVOKE UPDATE/DELETE on auto path）+ **HMAC chain**（per §4.1 audit row HMAC signature 用 authorization.json 同等 secret slot）+ Append-only 雙簽（PG REVOKE + Rust assertion）|
| **3** | Level 2 下 protected (e) Kill criteria auto 變成 noise — 過多自動 kill 觸發造成 alert fatigue + operator 對 kill notification 鈍化 | **§Decision 2 5 條 hard req 把關**（per AMD v2 §Decision 2.2 Wilson CI + N ≥ 30 + 30d rolling 防 noise kill）+ **Kill criteria deterministic gate** + 三路通知 + per-strategy kill rate metric panel（per ADR-0042 M3 health monitoring 對齊）|
| **4** | Engine restart 後 level 漂移 — cold start 從 DB read fail 或 DB row corrupted 導致 Level state 飄移 | **Cold start fail-closed default = Level 1**（per §5.3）+ DB row PRIMARY KEY id=1 + CHECK constraint current_level IN (1,2) + read fail emit Console banner red warning + alert operator |
| **5** | 切換 reason 字段被濫用 — operator 填「test」「abc」之類 placeholder 繞 audit 紀律 | **Free text minimum length 20 字元**（per §4.1 + GUI handler enforce）+ **Audit review SLA**：PM 每月對 audit table sample 抽查 reason 質量；發現 placeholder reason → operator notify + corrective action |
| **6**（補充） | Emergency override 被濫用為 cooldown bypass 默認路徑 | Emergency override 必填 `emergency_override_reason` + 額外觸發三路通知標記「emergency_override=true」+ 每月 PM audit；若 emergency override 比率 > 30% 觸發 governance review；emergency override 不繞 Operator role + 2FA（per §4.2）|
| **7**（補充） | Level 2 下 protected (a) Stage LAL 3-4 promotion auto 引爆 immature strategy | **§Decision 2 4.2 evidence-based gate**（N ≥ 30 + Wilson CI + 30d rolling）+ **Stage 0R-4 promotion gate**（per AMD-2026-05-15-01 Canary Rebase Replay Preflight）+ **Stage 4 stable 30d 紀律**（per ADR-0034 §Decision 5 gate criteria #1）= 三層 evidence-gated 把關 |
| **8**（補充） | Freeze state active 期間 operator 切換 Level 規避 freeze 紀律 | **§7.4 新增 invariant**：Freeze state active 期間 Level toggle 禁切換；engine 在 toggle handler 拒絕；audit emit「rejected: freeze active」|

### 8.2 Mitigation 層級總結

- **層 1 — DB constraint**：CHECK / REVOKE / PRIMARY KEY / INDEX uniqueness
- **層 2 — Engine 代碼 hard-coded**：§Decision 2 5 條 fail-safe + Level toggle 自身不繞 fail-safe（per §7.5）
- **層 3 — Auth gate**：Operator role + 2FA + Console warning + HMAC chain
- **層 4 — Audit immutability**：Append-only + ADR-0006 訂正紀律 + monthly PM review
- **層 5 — Notification**：Slack + email + Console banner 三路冗餘
- **層 6 — Time-based throttle**：24h cooldown + emergency override audit + freeze period block
- **層 7 — Cold start fail-closed**：DB read fail → Level 1（per §5.3）

---

## §9 Cascade Patch Checklist

| # | Patch 對象 | Patch 內容 | 估時 (hr) | Owner |
|---|---|---|---|---|
| **9.1** | AMD-2026-05-21-01 v2 draft（`docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`） | §Decision 1 重寫納入「Autonomy Level Toggle 雙層 preset」+ 14 path × 2 level 矩陣引用本 spec §2.1；§Decision 4 補釋 Level 是 system-wide policy 維度不取代 priority order；§9 cascade checklist 新增本 spec V### migration patch；§10 sign-off 加 Operator + PA + E1 + E2 + CC + A3 + FA + PM 對應 row | 4-6 | PM + TW（並行 dispatch） |
| **9.2** | ADR-0034 LAL 對齊矩陣（`docs/adr/0034-decision-lease-layered-approval-lal.md`） | §LAL ↔ Stage 對齊矩陣 line ~143 「never auto」cell 補釋「LAL 3/4 在 Level 1 下 operator approve manual；Level 2 下 LAL 3 auto with §Decision 2 fail-safe，LAL 4 venue change 仍 manual」；補入 LAL × Stage × Level 三維 cross-ref matrix | 4-6 | PA + E2 |
| **9.3** | ADR-0040 §Decision 5 venue change（`docs/adr/0040-multi-venue-gate-spec.md`） | §Decision 5 line ~119-126 補釋「venue change 在 Level 1 + Level 2 兩 level 下都 operator approve manual；per AMD v2 Q2 拍板 venue change carve out from auto path 設計」；§Decision 5 LAL Tier 4 對齊不動 | 2-3 | PA + BB |
| **9.4** | V### migration schema + Linux PG empirical dry-run | per §3 V### migration spec 落 schema spec file `docs/execution_plan/specs/2026-05-22--v###-autonomy-level-toggle.md`；Linux PG empirical dry-run（per ADR-0011）+ 6 條 dry-run 必驗（per §3.4） | 8-12 | MIT + E1 + E4（dry-run） |
| **9.5** | GUI Governance tab Settings sub-section toggle component | A3 design + E1 IMPL：Console banner real-time display + Settings sub-section UI flow（per §5.2）+ 14 path × 2 level 對照表 + read-only display + warning modal + 2FA confirm + reason 字段 + emergency override path + cooldown check + 三路通知 emit；JS `node --check` sign-off | 16-24 | A3 + E1 + E3（auth path）+ E2 |
| **9.6** | 5 個其他 module ADR wording 對齊（ADR-0041 ContextDistiller v4 / ADR-0042 M3 / ADR-0043 M6 / ADR-0044 M7 / ADR-0045 M4） | 各 ADR cross-ref AMD v2 + 補釋「Level 1/2 下對應 auto path 的對齊」；不動 module 本身設計，只動 cross-ref + 對齊段落 | 5-8 | R4 + PA |
| **9.7** | CLAUDE.md §四 hard boundaries 補釋 + 16 root principles skill 對齊（`srv/.claude/skills/16-root-principles-checklist/SKILL.md`） | §四 補入「Autonomy Level toggle 自身不可繞 §Decision 2 5 條 fail-safe hard requirements；Level 1 default fail-closed posture」；skill SKILL.md 加 Autonomy Level toggle attack vector grep pattern + 16 原則 walkthrough 補釋 | 2-3 | PM + CC |
| **9.8** | TODO.md §0.5 / §1.4 staging entry + docs/README.md index 補本 spec | 本 spec land 為 staging entry；docs/README.md 加 reference；TODO §1.4 D+2-D+3 entry 加「review Autonomy Level Toggle design spec」+ §0.5 加本 spec V### migration staging | 1-2 | PM + TW |

**合計 cascade patch 估時**：**42-64 hr**，並行 5-7 sub-agent → wall-clock **~1.5 working days**（含 V### PG dry-run）。

**並行 wave 設計**：
- **Wave 1**（並行，~2-3 hr wall-clock）：9.1 + 9.3 + 9.7（TW / BB / CC 並行；不撞文件）
- **Wave 2**（並行，~4-6 hr wall-clock）：9.2 + 9.6（PA + R4 並行；ADR cross-ref 路徑）
- **Wave 3**（並行，~8-12 hr wall-clock）：9.4 + 9.5（MIT/E1 dry-run + A3/E1 GUI；不撞 PG schema layer 與 GUI layer 互斥）
- **Wave 4**（serial，~1-2 hr wall-clock）：9.8（TODO/README index 最後 reconcile）

---

## §10 Sign-off

| Role | Source / 任務 | Date | Status |
|---|---|---|---|
| **Operator** | 2026-05-22 directive Q2 拍板「設一個自動等級，CC 設另外一個等級，可以在設置裡切換」 | 2026-05-22 | ✅ Q2 PROPOSED-pending-confirm（本 spec 為 IMPL 落地） |
| **PA** | 本 spec 起草 + 14 path × 2 level 矩陣設計 + 3 DB schema + Cascade checklist + §8 attack vectors | 2026-05-22 | ✅ DRAFTED |
| **CC** | 16 根原則 walkthrough（Level toggle 對原則 1/3/4/5/6/8/9/11 影響）+ §四 hard boundaries 對齊（5-gate 永鎖 + venue change 永鎖）+ §Decision 2 5 條 hard req 對 Level 1+2 雙生效驗證 | TBD（Wave 1） | 🟡 PENDING |
| **PM** | 9.1 AMD v2 draft §Decision 1 重寫 + 9.7 CLAUDE.md §四 補釋 + Q1/Q2 unresolved design 仲裁 | TBD（Wave 1+4） | 🟡 PENDING |
| **TW** | 9.1 AMD v2 draft format + 9.8 docs/README index 補本 spec + V### migration spec format | TBD（Wave 1+4） | 🟡 PENDING |
| **PA** （cascade） | 9.2 ADR-0034 LAL 對齊矩陣三維 cross-ref + 9.3 ADR-0040 §Decision 5 補釋 + 9.6 cross-ADR cross-ref 統籌 | TBD（Wave 2） | 🟡 PENDING |
| **R4** | 9.6 5 個 module ADR wording 對齊（0041/0042/0043/0044/0045）cross-ref 自動 verify | TBD（Wave 2） | 🟡 PENDING |
| **BB** | 9.3 venue change 從 always-operator 在 Level 2 下仍 carve-out manual 風險評估 + ADR-0040 §Decision 5 對齊 | TBD（Wave 2） | 🟡 PENDING |
| **MIT** | 9.4 V### migration schema patch + Linux PG empirical dry-run + 6 條 dry-run 必驗 + Append-only constraint 驗證（trading_ai REVOKE） | TBD（Wave 3） | 🟡 PENDING |
| **E1** | 9.4 V### migration IMPL + 9.5 GUI Governance tab Settings sub-section toggle IMPL（Console banner + warning modal + 2FA + reason 字段 + emergency override + cooldown check + 三路通知 emit）| TBD（Wave 3） | 🟡 PENDING |
| **A3** | 9.5 GUI design sign-off — Governance tab 歸屬 + Settings sub-section UI flow + 14 path × 2 level 對照表 + warning modal copy + Vanilla JS pattern | TBD（Wave 3） | 🟡 PENDING |
| **E2** | 9.4 + 9.5 review — Level toggle handler review + JS `node --check` + Rust compile-time const grep（per §7.5 反模式 grep pattern）+ Append-only constraint 反向 attack | TBD（Wave 3） | 🟡 PENDING |
| **E3** | 9.5 GUI Operator role authentication path + HMAC chain + 2FA flow security review | TBD（Wave 3） | 🟡 PENDING |
| **E4** | 9.4 + 9.5 regression test — V### dry-run 雙 apply idempotent + GUI flow 7 step e2e regression + cold start fail-closed default = Level 1 + 三路通知 emit fail scenario regression | TBD（Wave 3） | 🟡 PENDING |
| **FA** | §Decision 2 5 條 fail-safe hard req 在 Level 1+2 雙 level 下對齊驗 + 16 原則合規 walkthrough + Level toggle 自身不繞 fail-safe（per §7.5）audit | TBD（Wave 2 or 3） | 🟡 PENDING |
| **QA** | LAL × Stage × Level 三維 cross-ref matrix 對齊驗 + 14 path × 2 level 矩陣字面一致性 + 字面碰撞 re-verify | TBD（Wave 2） | 🟡 PENDING |

**任何 Level toggle IMPL land 前必須完成全部 sign-off**。

---

## §11 PA Unresolved Design 問題（needing operator confirm）

### Q1 — Emergency override path 設計範圍

**背景**：§4.2 設計「24h cooldown + emergency override path」。Emergency override 需要：
- 顯式 reason 必填
- 額外觸發三路通知（標記 emergency_override=true）
- 不繞 Operator role + 2FA
- 月度 PM audit review

**Open question**：Emergency override 是否要設「每月 N 次硬上限」？

**選項**：
- **Path A**（本 spec default）：不設硬上限；只靠 monthly PM review + audit；信任 operator judgment + reason text 紀律
- **Path B**：設每月 3 次 emergency override 硬上限；超過必走 ADR amendment + operator + PM joint approval
- **Path C**：不設硬上限但加 governance review trigger — emergency override 比率 > 30%（本 spec §8.1 #6 已 informally 列出）自動觸發 PM review session

**PA 推薦**：Path C（informally 已寫進 §8.1 #6，但未 hard-coded）；如果 operator 要嚴格度更高可選 Path B。Path A 太鬆易被當默認 cooldown bypass。

### Q2 — Level 2 default-OFF cold start 是否真要 default Level 1 而非「無 Level state」

**背景**：§5.3 設計「Engine 首次啟動 → Level 1 seed」+ §1.1 Default = Level 1 Conservative。

**Open question**：是否考慮過 cold start 留「Level uninitialized」狀態強制 operator 顯式選擇？

**選項**：
- **Path A**（本 spec default）：Cold start auto seed Level 1（fail-closed posture）；engine 直接運行 conservative mode；operator 可後續切換 Level 2
- **Path B**：Cold start state = `level_uninitialized`；engine 拒絕 emit 任何 auto path lease 直到 operator 顯式選 Level 1 或 Level 2；強制 operator 第一次部署時做 governance decision
- **Path C**：Cold start auto seed Level 1 但加 「first 7d 內必須 operator 手動 confirm Level 1 或切換 Level 2」alert spam，過 7d 仍未 confirm 觸發 Console banner red warning

**PA 推薦**：Path A（per CLAUDE.md §二 原則 6「失敗默認收縮」+ 原則 14「零外部成本可運行 baseline」+ engine 首次啟動需 minimal friction；Level 1 Conservative 本身就是 fail-closed default）。Path B 為 over-engineering（增加 cold start fail 模式 + UX 摩擦）。Path C 為中間方案但 alert spam 違反 alert fatigue 紀律。

---

## §12 與 PM v2 Draft §Decision 2 5 Hard Requirements 對齊驗

per §7 + 重申零 wording conflict 結論：

| §Decision 2 hard req | 本 spec 對應 | Wording conflict? |
|---|---|---|
| 4.1 Deterministic hard gate | §7.1 + §6.2 雙維度 eligibility | ❌ 無 conflict — 本 spec 不放寬 determinism |
| 4.2 Evidence-based gate (N ≥ 30 / Wilson CI / 30d rolling) | §7.2 + §1.4 + §8.1 #3 #7 | ❌ 無 conflict — 本 spec 不放寬 evidence 紀律 |
| 4.3 Gate FAIL → fallback advisory | §7.3 + §6.3 拒絕路徑 | ❌ 無 conflict — Level 1 拒絕 ≠ silent；走 advisory queue + 三路通知 |
| 4.4 Freeze auto path（regime / Guardian / 5-gate kill） | §7.4 + 新增 invariant「freeze 期間 Level toggle 禁切換」 | ❌ 無 conflict — 本 spec 強化（freeze 期間禁切換 Level）|
| 4.5 Compile-time hard-coded（不可 runtime override） | §7.5 + §8.1 #2 + Level toggle 自身不繞 fail-safe | ❌ 無 conflict — Level toggle 是 single 2-choice runtime config，但 path mapping + fail-safe 邏輯 hard-coded |

**結論**：本 spec 與 AMD v2 draft §Decision 2 5 hard requirements **零 wording conflict**；Level toggle 是 §Decision 1 governance scope 的 IMPL 設計，**完全不觸碰 §Decision 2 fail-safe hard requirements 任一條**。

---

## §13 Non-Goals

本 spec **不**做下列：

- 取消 operator 介入路徑（emergency halt button / 24h undo / operator override authority 全保留，per AMD v2 §Decision 3.3）
- 放寬 §四 hard boundaries 任一條（5-gate / authorization / Bybit retCode fail-closed / OPENCLAW_ALLOW_MAINNET / ML 不可 live order without Guardian）
- approve true-live, Mainnet 任一 deploy 動作（本 spec 只是 IMPL 設計依據）
- 改 16 根原則 #1-#16 本身（per CLAUDE.md §二）
- 改 ADR-0008 Decision Lease state machine baseline
- 改 ADR-0034 LAL 0-4 per-decision approval depth 紀律
- 改 ADR-0040 §Decision 5 venue change 紀律（per Q2 拍板兩 level 都不動 venue）
- 設計 3+ Level（per §1.3 棄因）
- 設計 per-decision / per-strategy Level（per §1.3 棄因）

---

*OpenClaw / 玄衡 Arcane Equilibrium — Autonomy Level Toggle Design Spec — IMPL 設計依據 for AMD-2026-05-21-01 v2 §Decision 1 Q2 拍板（PROPOSED-pending-operator-confirm; PM v2 draft cascade patch 待 PA 統籌）*
