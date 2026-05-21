---
spec: V103 + V104 — Earn / Hypothesis Registry / Pre-registration / Track-attribution Schema
date: 2026-05-21
author: MIT (consultant draft for PA Sprint 1A dispatch)
phase: v5.7 dispatch-safe patch Sprint 1A schema prerequisite
status: SPEC-DRAFT-V0（MIT 起草；待 PA C9 Linux PG dry-run 補資料 + v5.7 §3 reviewer 對齊後 SPEC-FINAL）
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.7.md §3 + §4 + §8 (Sprint 1A)
  - srv/docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md v3 (consolidation 對照)
  - srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-21--v57_executability_audit.md Risk 1
mirror precedent:
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C + NOT VALID CHECK + partial index 範式)
  - srv/sql/migrations/V083__fills_entry_context_id_close_check.sql (ALTER ADD COLUMN + NOT VALID CHECK 範式)
scope: design / spec only — 不寫 V103.sql / V104.sql 實檔，不在 Mac 跑 SQL，不改 Rust/Python writer，不執行 PG
---

# V103 + V104 Earn / Hypothesis / Track Schema Migration Spec

## §0 TL;DR

- **V103 新增 3 個 regular table**：`learning.hypotheses`（hypothesis registry）+ `learning.hypothesis_preregistration`（pre-registration ledger）+ `learning.earn_movement_log`（Bybit Earn stake/redeem audit）。
- **V104 條件性退號 / no-op**：`trading.fills.track` ADD COLUMN **已含於 V101 spec §3.2**（PA dispatch SoT v3，2026-05-20）。V104 推薦結論 = **退號為 no-op**，避免 ALTER COLUMN 命名衝突 + 維護 V101 single source of truth。
- **V103 / V104 與 V101 spec 衝突的設計面**：
  - V101 spec §3.3.1 `learning.hypotheses` 已用 UUID PK + state ENUM 7 值 + spec_json JSONB + track ENUM CHECK；v5.7 PA brief 要 BIGSERIAL PK + status ENUM 11 值 + expected_sharpe / capacity_estimate / min_sample_size / t_stat_min。兩套字段集相當不同 — **v5.7 vs V101 spec 路徑需 PA 仲裁**。本 spec 採 v5.7 PA brief 字段集（直接 exploit / asds 雙路線之共用 registry）。
  - V101 spec §3.3.2 `learning.hypothesis_preregistration` 已有 15 fields（ADR-0026 v3 spec）；v5.7 PA brief 要 payload_json + payload_hash + operator_signature 4 fields 為主。本 spec 採 v5.7 PA brief 字段集（簽署為主，統計門檻交給 hypotheses 本表）。
  - 上述兩處字段集差異需 PA 於 dispatch 前確認：**V103 採 v5.7 PA brief 字段集 / 廢棄 V101 spec §3.3.1+§3.3.2 字段集**（本 spec 假設此路線）；或 **V103 採 V101 spec 字段集 / 廢棄 v5.7 PA brief 字段集**（替代路徑）。
- **Guard A/B/C 完整**：3 個 NEW table 走 `CREATE TABLE IF NOT EXISTS`（Guard A）+ ENUM 值齊全驗（Guard C）+ idempotency；無 ALTER 既有 column 不需 Guard B（V104 退號後）。
- **Hot-path index 採 `CREATE INDEX CONCURRENTLY IF NOT EXISTS`**（Guard C 範式）— 3 表中 `earn_movement_log` 有 hot-path query（event_ts DESC / governance_approval_id JOIN）必加。
- **TimescaleDB hypertable 判斷 = 3 表全為 regular table**（hypotheses 低基數 ~hundreds 規模；preregistration 低基數 ~hundreds；earn_movement_log 低基數 ~daily events × 365 ≈ low thousands/yr）— 無時序壓力 hypertable 不必要。
- **engine_mode CHECK constraint 4 值齊全**（paper / demo / live_demo / live）所有 3 表必含；training filter 必 `IN ('live','live_demo')`（per CLAUDE.md §七 + MIT memory baseline）。
- **Linux PG empirical dry-run mandatory**（per CLAUDE.md §七 V055 mandate + feedback_v_migration_pg_dry_run.md）— 本 spec §4 列出 PA C9 待補的 3 條 SQL；spec sign-off 前必補。

---

## §1 Background + Scope

### 1.1 動機

v5.7 dispatch-safe patch §3 line 120-121 將 V103/V104 列為 NEW schema 但 spec 全 placeholder（14 agent CRITICAL 共識，7/14 agent 標 CRITICAL）。MIT 5.21 executability audit Risk 1 將「V103/V104 placeholder」列為派 PA 前的 hard precondition。

本 spec 目標：在 PA Sprint 1A dispatch 之前 land 完整 schema design — column inventory / type / index / Guard A/B/C / hypertable 判斷 / engine_mode CHECK / V101 consolidation 仲裁路徑 — 讓 PA 收到 dispatch brief 後直接 IMPL 不再現場補設計（避免 V055 5-round loop 同類風險）。

### 1.2 V101 consolidation 判斷（CRITICAL — v5.7 與 V101 spec 衝突仲裁）

| 對象 | V101 spec v3（2026-05-20 PA SoT） | v5.7 PA brief（2026-05-20 §3 + §4） | 衝突類型 | 本 spec 結論 |
|---|---|---|---|---|
| `learning.hypotheses` | §3.3.1 UUID PK + state 7 值 + spec_json JSONB + track ENUM CHECK + parent_hypothesis_id 自參考 | BIGSERIAL hypothesis_id + status 11 值 + pre_reg_ts/hash + expected_sharpe / capacity / t_stat_min / min_sample_size | **字段集衝突**（兩套 schema 都叫 hypotheses 但 column 集合 ~60% 不重疊） | **採 v5.7 brief 字段集**；廢棄 V101 §3.3.1（理由：§3 列出） |
| `learning.hypothesis_preregistration` | §3.3.2 UUID PK + 15 fields（strategy_name / hypothesis_text / expected_alpha_bps / variance_estimator / immutable_trigger_hash 等） | BIGSERIAL + FK to hypotheses + payload_json + payload_hash + operator_signature + signed_at | **字段集衝突**（V101 字段集中於統計門檻；v5.7 字段集中於簽署）| **採 v5.7 brief 字段集**；V101 §3.3.2 統計門檻字段移入 `hypotheses` 表 |
| `trading.fills.track` ADD COLUMN | §3.2 ALTER TABLE ADD COLUMN strategy_track ENUM NULL（含 12 表）；V102 後 NOT NULL + DEFAULT 'baseline' + 12 indexes + 4 P&L views | v5.7 §3 line 121「subset of V101 work; PA may consolidate」 | **重疊**（同 column 同 type 同語意） | **V104 退號為 no-op**；V101 已 land 此功能 |

**理由：採 v5.7 brief 字段集（推薦路徑 A）**：
1. v5.7 brief 字段集（expected_sharpe / capacity / t_stat_min / min_sample_size）服務 dual-track 路線（direct_exploit + asds_factory）+ Sprint 1B 統計 sample size gating；V101 字段集（spec_json / variance_estimator / immutable_trigger_hash）服務 ADR-0026 v3 single-track（direct_exploit only event-study）。
2. v5.7 是 2026-05-20 更新版策略路線，V101 spec v3 是 2026-05-20 同日但 ADR-0026 v3 specific scope。v5.7 brief 涵蓋面更廣。
3. V101 spec §3.3 兩表 status = 「new spec」尚未 IMPL（per V098 head + V099/V100 reserve 邏輯）→ 字段集 swap 0 runtime cost。
4. operator 在 prompt 中明示「V103/V104 schema spec 完全 placeholder（7/14 agent CRITICAL 共識）；需 land 4 表完整 DDL spec」+ 列出 v5.7 brief 字段集（不是 V101 字段集）→ 採 v5.7 brief 是 operator intent。

**替代路徑 B**：採 V101 字段集（廢棄 v5.7 brief 字段集）— 本 spec 不採；若 PA dispatch 時 PM 仲裁切此路徑，需重寫 §2 schema。

### 1.3 V101 consolidation 影響 V104 number 決策表

| 場景 | V104 狀態 | 理由 |
|---|---|---|
| V101 spec SPEC-FINAL 且 V101 已 land 到 Linux PG（含 `trading.fills.track` ADD COLUMN）| **V104 退號 → no-op** | 避免 ALTER COLUMN 命名衝突 + 維護 V101 single source of truth；V103 / V104 numbering 仍 reserve（PA dispatch 可重用 V104 slot 給其他 small migration 或 skip）|
| V101 spec land 但 PG apply 失敗 / V101 仍 dispatch pending | **V104 = V101 §3.2 子集**（只 ADD COLUMN to `trading.fills`）| 解 V101 dispatch 延後 blocker；V103 / V104 並行 |
| V101 spec 撤回 / 廢棄 | **V104 = V101 §3.2 完整 12 表 ADD COLUMN**（mirror V101 §3.2 邏輯）| V101 撤回時 V104 接手 |

**本 spec 假設情境 1**：V101 spec v3 已 SPEC-FINAL；V101 dispatch 在 V103 之前 land（per v5.7 §3 dispatch ordering）；故 V104 退號為 no-op。**本 spec §3 不寫 V104 SQL 邏輯**；列「V104 退號為 no-op」決策。

### 1.4 不在本 spec 範圍

- ❌ V103.sql 實檔寫作（E1 IMPL 工作）
- ❌ V104.sql 實檔（退號為 no-op 後無需）
- ❌ Mac 跑 V103 SQL（必 Linux PG empirical）
- ❌ V101 spec §3.3.1 + §3.3.2 字段集 reconciliation（PM 仲裁工作）
- ❌ Rust / Python writer 對應 hypothesis registry / earn_movement_log 寫入路徑（E1 IMPL 工作）
- ❌ healthcheck Python integration（E1 IMPL Worktree C 工作）
- ❌ ML training pipeline integration（permanently-banned；hypothesis registry 是 governance / pre-registration 層，不是 ML training feature）

---

## §2 Schema Changes

### 2.1 `learning.hypotheses` — Hypothesis Registry

#### 2.1.1 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.hypotheses (
    hypothesis_id           BIGSERIAL PRIMARY KEY,
    strategy_name           TEXT NOT NULL,
    pre_reg_ts              TIMESTAMPTZ NOT NULL,
    pre_reg_hash            TEXT NOT NULL,
    status                  TEXT NOT NULL
                            CHECK (status IN (
                                'draft',
                                'preregistered',
                                'shadow',
                                'stage_0r',
                                'stage_1',
                                'stage_2',
                                'stage_3',
                                'stage_4',
                                'live',
                                'retired',
                                'killed'
                            )),
    expected_sharpe         REAL,
    expected_dd             REAL,
    capacity_estimate_usdt  BIGINT,
    t_stat_min              REAL,
    min_sample_size         INTEGER,
    engine_mode             TEXT NOT NULL
                            CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### 2.1.2 設計理由

| Aspect | 設計 | 理由 |
|---|---|---|
| PK 類型 | `BIGSERIAL` | per v5.7 brief；sequential ID 利於 audit log temporal ordering；不需 UUID（無 cross-system import 需求） |
| `strategy_name` 不 enum | `TEXT` | 5 既有 + Sprint 2+ 新策略名（cointegration_pairs 等）動態擴增；CHECK enum 易過時 |
| `pre_reg_ts` + `pre_reg_hash` | 必 NOT NULL | pre-registration 不變式（per ADR-0026 v3 + DOC-08 §12 #8 交易可解釋）；hash 是 spec_json + config_hash 的 git-style content hash（algorithm 由 IMPL 期 trainer adapter 定）|
| `status` 11 值 ENUM CHECK | TEXT + CHECK | 統一 Sprint 1A canary stage 路徑 + Sprint 2 dual-track（draft → preregistered → shadow → stage_0r 是 ADR-0021 4-stage canary preflight + stage_1-4 是 promotion stage + live + retired/killed）|
| `expected_sharpe` / `expected_dd` / `capacity_estimate_usdt` / `t_stat_min` / `min_sample_size` | NULL allowed | Sprint 1A 起始 hypothesis 可暫不填 statistical thresholds；preregistered 後 IMPL 須 backfill（healthcheck 後續驗）|
| `expected_sharpe` REAL vs DOUBLE PRECISION | REAL (single-precision) | sharpe / dd / t_stat 4 byte 精度足夠；節省 storage |
| `capacity_estimate_usdt` BIGINT | 整數 USDT | capacity ~USDT amount (e.g. 50000 USDT)；不需 NUMERIC 小數精度（capacity 估計天然 round to USDT 整數）|
| `engine_mode` NOT NULL CHECK 4 值 | TEXT + CHECK | per CLAUDE.md §七 + MIT memory baseline；training filter 必 IN ('live','live_demo')；preregistration 期 engine_mode='paper' / shadow 期 'demo' / promotion 期 'live_demo' → 'live' |
| `created_at` + `updated_at` | DEFAULT now() | audit trail；updated_at 由 IMPL writer 維護（trigger 或 explicit UPDATE）|

#### 2.1.3 Indexes

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hypotheses_strategy_status
    ON learning.hypotheses (strategy_name, status);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hypotheses_pre_reg_ts
    ON learning.hypotheses (pre_reg_ts DESC);
```

**理由**：
- `(strategy_name, status)`：高頻 query `SELECT * FROM learning.hypotheses WHERE strategy_name=$1 AND status IN ('shadow','stage_0r','stage_1')` for canary dashboard
- `(pre_reg_ts DESC)`：audit log temporal 排序 / recent preregistration 列表

#### 2.1.4 Row 量級估算

- 5 既有策略 × per-strategy ~2 hypotheses/yr（major refactor / parameter sweep）= 10 row/yr
- Sprint 2+ 新策略 ASDS-generated cohort ~10-20 hypothesis/yr
- Sprint 1B+ Alpha Tournament dataset 一次性 ~50 hypothesis records
- **總量 ~100 row/yr**（regular table，無 hypertable / retention 需求）

### 2.2 `learning.hypothesis_preregistration` — Pre-registration Ledger

#### 2.2.1 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.hypothesis_preregistration (
    preregistration_id      BIGSERIAL PRIMARY KEY,
    hypothesis_id           BIGINT NOT NULL
                            REFERENCES learning.hypotheses(hypothesis_id),
    payload_json            JSONB NOT NULL,
    payload_hash            TEXT NOT NULL,
    operator_signature      TEXT NOT NULL,
    signed_at               TIMESTAMPTZ NOT NULL,
    engine_mode             TEXT NOT NULL
                            CHECK (engine_mode IN ('paper','demo','live_demo','live'))
);
```

#### 2.2.2 設計理由

| Aspect | 設計 | 理由 |
|---|---|---|
| FK to `hypotheses` | `BIGINT NOT NULL REFERENCES learning.hypotheses(hypothesis_id)` | 一對多（一 hypothesis 可有多次簽署版本，e.g. v1 → v2 amendment）|
| `payload_json` JSONB | NOT NULL | 序列化 hypothesis spec + statistical thresholds + variance estimator + trigger rule（V101 spec 字段集移入此 JSONB；保留 ADR-0026 v3 設計）|
| `payload_hash` TEXT NOT NULL | content hash 防 payload 篡改 | git-style hash of canonical JSON serialization |
| `operator_signature` TEXT NOT NULL | 簽署人 ID + cryptographic signature (Ed25519 / HMAC-SHA256 by IMPL 定) | per DOC-08 §12 + §四硬邊界 Operator 角色 |
| `signed_at` TIMESTAMPTZ NOT NULL | 簽署時間 | audit timestamp |
| `engine_mode` NOT NULL CHECK 4 值 | TEXT + CHECK | per CLAUDE.md §七 + MIT memory baseline |
| **無 `updated_at`** | append-only design | preregistration ledger 是 immutable audit log；任何 amendment = 新 row（hypothesis_id 同 / payload_hash 不同 / signed_at 不同）|

#### 2.2.3 Indexes

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_preregistration_hypothesis_signed
    ON learning.hypothesis_preregistration (hypothesis_id, signed_at DESC);
```

**理由**：高頻 query `SELECT * FROM learning.hypothesis_preregistration WHERE hypothesis_id=$1 ORDER BY signed_at DESC LIMIT 1` for latest signature lookup。

#### 2.2.4 Row 量級估算

- `hypotheses` ~100 row/yr × per-hypothesis 1-2 簽署版本 = ~150 row/yr
- regular table，無 hypertable / retention 需求

### 2.3 `learning.earn_movement_log` — Bybit Earn Stake/Redeem Audit

#### 2.3.1 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.earn_movement_log (
    movement_id                BIGSERIAL PRIMARY KEY,
    event_ts                   TIMESTAMPTZ NOT NULL,
    direction                  TEXT NOT NULL
                               CHECK (direction IN ('stake','redeem')),
    amount_usdt                NUMERIC(18,8) NOT NULL,
    apr_at_time                REAL,
    governance_approval_id     BIGINT REFERENCES governance.audit_log(id),
    bybit_response_payload     JSONB,
    engine_mode                TEXT NOT NULL
                               CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    api_scope_used             TEXT NOT NULL,
    reconciliation_status      TEXT NOT NULL DEFAULT 'pending'
                               CHECK (reconciliation_status IN (
                                   'pending',
                                   'matched',
                                   'mismatch'
                               ))
);
```

#### 2.3.2 設計理由

| Aspect | 設計 | 理由 |
|---|---|---|
| PK BIGSERIAL | sequential | audit log temporal ordering |
| `event_ts` NOT NULL | TIMESTAMPTZ | stake / redeem 真實時間（Bybit response 提供）|
| `direction` ENUM 2 值 (`stake` / `redeem`)| TEXT + CHECK | 雙向流動 |
| `amount_usdt` NUMERIC(18,8) | 高精度（小數 8 位） | Bybit Earn amount 可能含 satoshi-scale stable coin amount；NUMERIC 不 REAL（精度誤差不可接受）|
| `apr_at_time` REAL | single precision | APR 4-decimal float 足夠；NULL allowed for redeem（redemption 不 lock APR）|
| `governance_approval_id` BIGINT FK → `governance.audit_log.id` | 必驗 FK target | 必驗 governance.audit_log 真存在（**待 PA C9 確認 column name = `id`**）|
| `bybit_response_payload` JSONB NULL | API raw response | reconciliation / debug use；NULL allowed for paper/demo dry-run|
| `engine_mode` NOT NULL CHECK 4 值 | TEXT + CHECK | per CLAUDE.md §七 + MIT memory baseline |
| `api_scope_used` TEXT NOT NULL | Bybit API permission scope (e.g. `account:earn:write`) | per OpenClaw Bybit client expansion；audit trail 必含 scope evidence |
| `reconciliation_status` ENUM 3 值 | TEXT + CHECK + DEFAULT 'pending' | daily reconciliation cron 將 'pending' → 'matched' / 'mismatch'；service Sprint 1B daily_reconciliation 邏輯 |

#### 2.3.3 Indexes

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_earn_movement_event_ts
    ON learning.earn_movement_log (event_ts DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_earn_movement_governance_approval
    ON learning.earn_movement_log (governance_approval_id)
    WHERE governance_approval_id IS NOT NULL;
```

**理由**：
- `(event_ts DESC)`：daily reconciliation 跑 `SELECT * FROM earn_movement_log WHERE event_ts > now() - INTERVAL '24 hours'`
- `(governance_approval_id) WHERE NOT NULL` partial：JOIN to governance.audit_log audit chain；NULL approval (paper / demo dry-run) 不索引省空間

#### 2.3.4 Row 量級估算

- v5.7 §4 線：手動 rebalance 前 3 months → 每月 ~4-8 stake/redeem events
- 自動化 Sprint 3+ ：daily / weekly rebalance → ~30-60 event/yr
- **總量 ~100 row/yr**（regular table，無 hypertable / retention 需求；event_ts DESC index 即可滿足 query）

### 2.4 `trading.fills.track` ADD COLUMN（V104 退號決策）

#### 2.4.1 V101 spec §3.2 已涵蓋

V101 spec v3 line 94-95：

```sql
ALTER TABLE IF EXISTS trading.fills
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;
```

V101 spec v3 line 80-88 已 CREATE TYPE strategy_track ENUM (`direct_exploit`, `asds_factory`, `baseline`)；V101 V102 chain 已含 NOT NULL + DEFAULT + index + P&L views。

#### 2.4.2 V104 結論

**V104 退號為 no-op**。理由：
1. V101 spec v3 已 SPEC-FINAL（per spec header status line）
2. V101 dispatch 在 V103 之前 land（per v5.7 §3 + V101 spec preconditions）
3. ALTER COLUMN 同 column 二次 ADD 觸 sqlx migrate idempotent 風險（即使 IF NOT EXISTS）
4. 維護 V101 single source of truth；track column 演進歷史 deterministic

#### 2.4.3 替代情境 — 若 V101 land 延後

若 V101 dispatch 到 Linux PG apply 失敗 / V101 spec 撤回，V104 接手 V101 §3.2 子集：
- ADD COLUMN to `trading.fills` 同 V101 §3.2 line 94-95
- V104 不含 V101 其餘 11 表 ADD COLUMN（保持 V104 small + non-blocking）
- V101 後續若重啟 dispatch，V101 SQL 文件需改為「IF NOT EXISTS skip already-applied」（V101 IMPL 階段處理，不在本 spec 範圍）

**本 spec 假設情境 1（V101 已 land）**：V104 退號為 no-op；本 spec 不寫 V104 SQL 設計。

---

## §3 Guard A/B/C Templates（per CLAUDE.md §七 + V094 mirror）

V103 涉及 3 個 NEW table CREATE：

- **Guard A**：表已存在但 schema 不符 → RAISE
- **Guard B**：不需要（V103 無 ALTER 既有 column）
- **Guard C**：CHECK constraint + ENUM 值齊全 + index 對齊驗證 → RAISE on mismatch

### 3.1 Guard A — table existence + 既有 schema 對齊驗證

```sql
-- ============================================================
-- Guard A: V103 預檢 — 若 learning.hypotheses / learning.hypothesis_preregistration
-- / learning.earn_movement_log 已存在，必驗 V103 spec column 全俱在；缺即 RAISE
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    -- learning.hypotheses 已存在的情境下 check column 完整性
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='hypotheses'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'hypothesis_id', 'strategy_name', 'pre_reg_ts', 'pre_reg_hash',
            'status', 'expected_sharpe', 'expected_dd', 'capacity_estimate_usdt',
            't_stat_min', 'min_sample_size', 'engine_mode',
            'created_at', 'updated_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='hypotheses'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V103 Guard A FAIL: learning.hypotheses exists but missing columns: %. '
                'Possible V101 spec §3.3.1 stub conflict — resolve schema reconciliation before applying V103.',
                v_missing;
        END IF;
    END IF;

    -- learning.hypothesis_preregistration 已存在的情境
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='hypothesis_preregistration'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'preregistration_id', 'hypothesis_id', 'payload_json',
            'payload_hash', 'operator_signature', 'signed_at', 'engine_mode'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='hypothesis_preregistration'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V103 Guard A FAIL: learning.hypothesis_preregistration exists but missing columns: %. '
                'Possible V101 spec §3.3.2 stub conflict — resolve schema reconciliation before applying V103.',
                v_missing;
        END IF;
    END IF;

    -- learning.earn_movement_log 已存在的情境
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='earn_movement_log'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'movement_id', 'event_ts', 'direction', 'amount_usdt',
            'apr_at_time', 'governance_approval_id', 'bybit_response_payload',
            'engine_mode', 'api_scope_used', 'reconciliation_status'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='earn_movement_log'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V103 Guard A FAIL: learning.earn_movement_log exists but missing columns: %. '
                'Resolve schema drift before applying V103.',
                v_missing;
        END IF;
    END IF;

    -- governance.audit_log 必須存在（earn_movement_log FK target）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='audit_log'
    ) THEN
        RAISE EXCEPTION
            'V103 Guard A FAIL: governance.audit_log missing — '
            'V098 must apply before V103. Verify _sqlx_migrations.';
    END IF;
END $$;
```

### 3.2 Guard B — 不適用

V103 不 ALTER 既有 column type；無 type-sensitive 檢查需求。本 spec 不設 Guard B 段。

### 3.3 Guard C — CHECK constraint + ENUM 值齊全 + index 對齊驗證

```sql
-- ============================================================
-- Guard C: V103 預檢 — 重跑 V103 時 idempotent 檢查 CHECK constraint + index 對齊
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- hypotheses.status CHECK constraint 11 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.hypotheses'::regclass
      AND conname LIKE '%status%check%';
    IF v_actual IS NOT NULL THEN
        IF position('draft' IN v_actual) = 0
           OR position('preregistered' IN v_actual) = 0
           OR position('shadow' IN v_actual) = 0
           OR position('stage_0r' IN v_actual) = 0
           OR position('stage_1' IN v_actual) = 0
           OR position('stage_2' IN v_actual) = 0
           OR position('stage_3' IN v_actual) = 0
           OR position('stage_4' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
           OR position('retired' IN v_actual) = 0
           OR position('killed' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V103 Guard C FAIL: learning.hypotheses status CHECK enum mismatch. '
                'Actual: %. Expected to contain all 11 status values (draft/preregistered/shadow/stage_0r/stage_1-4/live/retired/killed).',
                v_actual;
        END IF;
    END IF;

    -- earn_movement_log.direction CHECK 2 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.earn_movement_log'::regclass
      AND conname LIKE '%direction%check%';
    IF v_actual IS NOT NULL THEN
        IF position('stake' IN v_actual) = 0
           OR position('redeem' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V103 Guard C FAIL: learning.earn_movement_log direction CHECK enum mismatch. '
                'Actual: %. Expected stake/redeem.',
                v_actual;
        END IF;
    END IF;

    -- earn_movement_log.reconciliation_status CHECK 3 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.earn_movement_log'::regclass
      AND conname LIKE '%reconciliation%check%';
    IF v_actual IS NOT NULL THEN
        IF position('pending' IN v_actual) = 0
           OR position('matched' IN v_actual) = 0
           OR position('mismatch' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V103 Guard C FAIL: learning.earn_movement_log reconciliation_status CHECK enum mismatch. '
                'Actual: %. Expected pending/matched/mismatch.',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 4 值齊全（3 表共用）
    FOR v_actual IN
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_class r ON c.conrelid = r.oid
        JOIN pg_namespace n ON r.relnamespace = n.oid
        WHERE n.nspname='learning'
          AND r.relname IN ('hypotheses', 'hypothesis_preregistration', 'earn_movement_log')
          AND c.conname LIKE '%engine_mode%check%'
    LOOP
        IF position('paper' IN v_actual) = 0
           OR position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V103 Guard C FAIL: engine_mode CHECK enum mismatch on 3 V103 tables. '
                'Actual: %. Expected paper/demo/live_demo/live.',
                v_actual;
        END IF;
    END LOOP;
END $$;
```

### 3.4 Guard 設計理念（per V094 mirror）

| Guard | 觸發場景 | RAISE 條件 | NOT RAISE 條件（idempotent）|
|---|---|---|---|
| A | 3 NEW table 已存在但 column 缺；or governance.audit_log 缺 | RAISE | 全 column 俱在 / table 不存在（首次跑）|
| C | CHECK constraint 缺 enum 值 | RAISE | constraint 不存在（首次跑）/ constraint 完整（重跑）|

**重跑 V103 第二次必不 RAISE**（idempotency per CLAUDE.md §七 V055/V083/V084 incident precedent）。

---

## §4 Linux PG Dry-Run Protocol（mandatory）

per CLAUDE.md §七 + `feedback_v_migration_pg_dry_run.md` + V055 5-round loop / V083 / V084 incident chain，V103 涉及：
- PG reflection（`information_schema.tables` + `information_schema.columns` for Guard A）
- CHECK constraint ENUM runtime semantic（Guard C）
- FK constraint to `governance.audit_log`（需 V098 已 land）

**必先 Linux PG empirical 驗證**，禁 Mac mock pytest 代替。

### 4.1 PA C9 待補的 3 條 SQL（spec sign-off 前必補）

per operator prompt + MIT 5.21 audit Risk 2，PA 在 dispatch 前必執行以下 ssh trade-core PG query，將真實 schema 對齊 V103 spec 假設：

```bash
# Query 1: _sqlx_migrations head + recent versions
ssh trade-core "psql -d openclaw -c 'SELECT max(version), array_agg(version) FROM _sqlx_migrations ORDER BY version DESC LIMIT 10'"
# Expected: head = V098（V097/V098 catch-up 後）; V103 接 V099-V102 之後

# Query 2: learning + trading schema 既有 column 對齊（hypotheses / preregistration / track 衝突檢測）
ssh trade-core "psql -d openclaw -c \"SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns WHERE table_schema IN ('learning','trading') AND (table_name LIKE '%hypothes%' OR column_name = 'track')\""
# Expected:
#   - 若 V101 已 land: trading.fills.track 存在 = strategy_track ENUM；learning.hypotheses / hypothesis_preregistration 已存在 = V101 §3.3 字段集 → V103 必 reconcile / 或 drop V101 stub 後重建
#   - 若 V101 未 land: 0 hypotheses table；0 track column → V103 直接 CREATE TABLE 即可

# Query 3: PG 容量 + governance.audit_log 是否存在
ssh trade-core "psql -d openclaw -c \"SELECT pg_total_relation_size(schemaname || '.' || tablename) / 1024 / 1024 AS mb, schemaname, tablename FROM pg_tables WHERE schemaname IN ('learning','trading','governance') ORDER BY mb DESC LIMIT 20\""
# Expected: governance.audit_log 存在（V098 head 後）；trading.fills 容量 ~hundreds MB；其他 learning.* 表容量分布

# Query 4 (extra)：governance.audit_log column 確認 FK target
ssh trade-core "psql -d openclaw -c \"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='governance' AND table_name='audit_log' ORDER BY ordinal_position\""
# Expected: governance.audit_log 含 'id' BIGSERIAL PK（待 PA empirical confirm；若 column name 不是 'id'，§2.3.1 FK 設計需 patch）
```

**注**：PG socket 連接可能需 host:port + user 配置；上述 ssh + psql shorthand 假設 trade-core 已配置 .pgpass / `PGPASSWORD` / `DATABASE_URL`。若不通，PA dispatch 可改用：
```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c '<SQL>'"
```
（per V094 spec §4.1 範式）

**待 PA C9 補資料的 4 處 placeholder**（spec sign-off 前必更新）：

1. `_sqlx_migrations` head 真實 = ?（spec 假設 V098；若 V099/V100/V101/V102 已 apply 需更新 V103 numbering）
2. `learning.hypotheses` 是否存在（V101 land 狀態確認 → V104 退號 / 替代路徑判斷）
3. `trading.fills.track` 是否存在（V104 退號決策直接相關）
4. `governance.audit_log.id` column name 確認（V103 §2.3.1 earn_movement_log FK target 路徑）

### 4.2 Round 1 — V103 SQL 真實 PG semantic empirical 驗證

```bash
# ssh trade-core 執行（不在 Mac 跑）
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V103__earn_hypotheses_registry.sql
"
```

**Round 1 必驗 8 項**（empirical SELECT verify after V103 apply）：

```sql
-- 1. learning.hypotheses 表存在 + 13 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='hypotheses';
-- Expected: 13

-- 2. learning.hypothesis_preregistration 表存在 + 7 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='hypothesis_preregistration';
-- Expected: 7

-- 3. learning.earn_movement_log 表存在 + 10 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='earn_movement_log';
-- Expected: 10

-- 4. CHECK constraint 11 status values
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.hypotheses'::regclass AND conname LIKE '%status%check%';
-- Expected: 含 11 個 status 值（draft, preregistered, shadow, stage_0r, stage_1-4, live, retired, killed）

-- 5. FK constraint 真存在 (preregistration → hypotheses)
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.hypothesis_preregistration'::regclass AND contype='f';
-- Expected: 1 row 含 REFERENCES learning.hypotheses(hypothesis_id)

-- 6. FK constraint 真存在 (earn_movement_log → governance.audit_log)
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.earn_movement_log'::regclass AND contype='f';
-- Expected: 1 row 含 REFERENCES governance.audit_log(id)

-- 7. Index 確認
SELECT indexname FROM pg_indexes
WHERE schemaname='learning'
  AND tablename IN ('hypotheses', 'hypothesis_preregistration', 'earn_movement_log')
ORDER BY indexname;
-- Expected: 至少 6 indexes（3 PK + idx_hypotheses_strategy_status + idx_hypotheses_pre_reg_ts
--                          + idx_preregistration_hypothesis_signed + idx_earn_movement_event_ts
--                          + idx_earn_movement_governance_approval）

-- 8. engine_mode CHECK 真 reject 非 4 值（empirical INSERT test）
BEGIN;
SAVEPOINT test_engine_mode;
INSERT INTO learning.hypotheses
    (strategy_name, pre_reg_ts, pre_reg_hash, status, engine_mode)
VALUES
    ('test_strategy', NOW(), 'test_hash', 'draft', 'INVALID_MODE');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_engine_mode;
ROLLBACK;
```

### 4.3 Round 2 — Idempotency 驗證

重跑 V103.sql 第二次必不 RAISE / 必不重複建 index / 必不 fail：

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V103__earn_hypotheses_registry.sql
"
# Expected exit code 0; all DO blocks output NOTICE-only PASS; 0 RAISE EXCEPTION
```

**Round 2 後驗證**：
```sql
-- 確認 V103 不 double-create
SELECT count(*) FROM information_schema.tables
WHERE table_schema='learning'
  AND table_name IN ('hypotheses', 'hypothesis_preregistration', 'earn_movement_log');
-- Expected: 3 (each table once)

-- 確認 index 不 double-create
SELECT count(*) FROM pg_indexes
WHERE schemaname='learning'
  AND indexname IN (
    'idx_hypotheses_strategy_status',
    'idx_hypotheses_pre_reg_ts',
    'idx_preregistration_hypothesis_signed',
    'idx_earn_movement_event_ts',
    'idx_earn_movement_governance_approval'
  );
-- Expected: 5
```

### 4.4 為何 Mac mock pytest 不夠（V055 5-round loop 教訓）

per memory `feedback_v_migration_pg_dry_run.md` + `project_2026_05_02_p0_sqlx_hash_drift`：
- Mac mock pytest 無法捕捉 PG runtime 真實 PL/pgSQL DO block semantic（特別是 Guard A `array_agg` + `unnest`）
- Mac static parse review 無法驗 `pg_get_constraintdef` 真實輸出對齊 spec
- Mac 無法驗 FK constraint cross-schema target（governance.audit_log）真存在
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug；V103 / V094 / V083 / V084 全須遵守 V055 mandate

**E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID**（per CLAUDE.md §七 + V094 §4.3 範式）。

---

## §5 sqlx Checksum Repair SOP

per memory `project_2026_05_02_p0_sqlx_hash_drift`（commit `3681f83`），V103 file edit 後 DB checksum 必同步：

```bash
# E1 IMPL：寫 V103.sql 完成後跑 Linux dry-run（per §4.2）
# 若 V103.sql 落地後又被 edit → DB checksum drift
# 必跑 repair binary 同步 checksum 到 _sqlx_migrations table

ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  cargo run --release --bin repair_migration_checksum -- --version 103
"
# Expected: V103 checksum updated in _sqlx_migrations table to match new file SHA
```

### 5.1 Engine restart 後驗證 sqlx migrate 不 panic

```bash
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"

ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/openclaw_engine/logs/engine.log 2>&1 | grep -E 'sqlx|migration|panic'"
# Expected: 0 panic; 'Applied migrations' 正常 log; V103 success=t in _sqlx_migrations

ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c 'SELECT version, success, description FROM _sqlx_migrations WHERE version=103;'"
# Expected: 1 row, success=t
```

### 5.2 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift` + V094 §5.3：cargo test PASS ≠ runtime sqlx migrate 驗證。E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。

---

## §6 IMPL Plan（簡）

### 6.1 E1 工作鏈

```
本 V103/V104 spec PM sign-off + PA C9 dry-run 補資料 land
  ↓
PA dispatch decide V101 spec consolidation 路徑 (採 v5.7 brief or 替代)
  ↓
E1 IMPL (1 worktree)：
  └─ Worktree A: 寫 V103.sql 含 Guard A/C + 3 CREATE TABLE + 5 CONCURRENTLY index
     (~120 LOC SQL, 1 E1-day，含 Linux PG dry-run × 2 round)
  ↓
（如 V104 退號）skip V104 worktree
（如 V104 替代路徑 = V101 §3.2 子集）寫 V104.sql ~20 LOC, 0.3 E1-day
  ↓
E2 review (≥30min, 重點查 §6.2 三高風險點)
  ↓
E4 regression (cargo test --release + pytest healthcheck)
  ↓
ssh trade-core 跑 V103.sql Linux PG dry-run × 2 round
  ↓
restart_all --rebuild deploy
  ↓
engine restart verify sqlx migrate runtime PASS
  ↓
QA cycle（Sprint 1A 整體 closure）
  ↓
PM sign-off
```

### 6.2 E2 Review 重點 3 項

#### 6.2.1 Linux PG dry-run gate 證據 ID 必出現

E2 PR 審查必拒「無 Linux PG dry-run × 2 round 證據 ID」的 V103 PR：
- E1 IMPL commit message 含 dry-run round 1 + round 2 commit ID 或 ssh trade-core 操作 ID
- 重跑 V103 SQL 第二次的 NOTICE 輸出 attached（idempotency 證明）

#### 6.2.2 V101 consolidation reconciliation 已決議

E2 必驗 V103 SQL 不與 V101 spec §3.3.1 / §3.3.2 column 集合衝突：
- 若 V101 已 land：V103 Guard A 在 hypotheses 已存在情境 RAISE（強制 reconciliation）
- 若 V101 未 land：V103 直接 CREATE TABLE，V101 spec 後續 SQL 必 patch 為「IF NOT EXISTS skip」或 V101 廢棄

#### 6.2.3 engine_mode CHECK constraint 不缺一值

E2 必跑 Guard C SQL 確認：
- hypotheses / hypothesis_preregistration / earn_movement_log 三 表的 engine_mode CHECK 都含 `'paper','demo','live_demo','live'` 4 值
- training filter `IN ('live','live_demo')` 在 future ML pipeline 才不漏 LiveDemo（per MIT memory baseline + CLAUDE.md §七）

---

## §7 Backward Compat

### 7.1 Append-only 設計

V103 是 **append-only schema migration**：
- 加 3 個 NEW table（learning schema 既有 + 1 governance FK target dependency）
- 0 ALTER 既有 column
- 0 DROP 既有 schema
- 0 RENAME

V104 = no-op（退號）。

### 7.2 不破現有 SELECT / INSERT / UPDATE

| 既有操作 | V103 影響 |
|---|---|
| `SELECT * FROM learning.*` | new tables 不影響既有 21+ learning tables |
| `INSERT INTO governance.audit_log` | V103 加 FK reference 但不改 audit_log 結構（V098 已 land 為 prereq）|
| `SELECT FROM trading.fills` | V104 退號為 no-op，0 影響 |
| 既有 healthcheck（55 個 check per V094 §7.5）| 0 影響（沒有 check 引用 V103 新表）；新 healthcheck Sprint 1B 才加 |

### 7.3 對 future writer behaviour

| Table | 第一個 row 來源 | Sprint |
|---|---|---|
| learning.hypotheses | E1 IMPL hypothesis registry writer / PA manual seed | 1A → 1B |
| learning.hypothesis_preregistration | Operator-signed preregistration via Python control_api_v1 endpoint | 1B |
| learning.earn_movement_log | Bybit Earn API client（Sprint 1B / governance Decision Lease 路徑）| 1B |

**Empty-table 期間**：3 表 V103 apply 後立即 0 row（Foundation stage per MIT pipeline maturity）；writer code spawn 是 Sprint 1B 工作（per MIT pipeline maturity audit Skeleton stage）。

---

## §8 Rollback Path

### 8.1 V103 rollback

```sql
DROP TABLE IF EXISTS learning.earn_movement_log;
DROP TABLE IF EXISTS learning.hypothesis_preregistration;
DROP TABLE IF EXISTS learning.hypotheses;
-- FK 依序 drop preregistration 在 hypotheses 之前
-- 0 row loss（V103 apply 後立即 0 row）
```

### 8.2 V104 rollback

V104 退號 = no-op，無 rollback。

### 8.3 V096 boundary

per V101 spec v3 §7：rollback 路徑不跨 V096（V096 drop dead tables 不可逆）。V103 / V104 rollback 全在 V096 之後（V096 < V098 < V101 < V103），無 boundary 風險。

---

## §9 風險評估 + 16 原則 / DOC-08 §12 / §四 觸碰

### 9.1 改動風險評級 = **低-中**

| Risk | 評級 | Mitigation |
|---|---|---|
| schema migration 失敗 | 低 | Linux PG empirical dry-run × 2 + sqlx checksum repair SOP（V055/V083/V084 incident precedent）|
| V101 字段集 reconciliation 漏接 | **中** | Guard A 強制 RAISE on existing hypotheses table missing v5.7 字段；PA dispatch 必跑 §4.1 C9 query 確認 V101 land 狀態 |
| FK to governance.audit_log column name 假設錯誤 | 低-中 | §4.1 Query 4 確認 column name；若不是 'id'，§2.3.1 FK patch |
| Sprint 1B writer 接線延後 | 低 | 3 表 V103 apply 後立即 0 row 屬 Foundation stage 設計預期；MIT pipeline maturity audit 接受 |
| backward-compat 風險 | 極低 | 全 NEW table，0 ALTER / 0 DROP / 0 RENAME |

### 9.2 16 根原則合規（16/16）

| 原則 | 狀態 | 證據 |
|---|---|---|
| #1 單一寫入口 | PASS | V103 不改 IntentProcessor / submit_intent 既有契約 |
| #2 讀寫分離 | PASS | hypotheses / preregistration / earn_movement_log 全是 governance / audit 表，非 trading 寫入路徑 |
| #3 AI→Lease→複核→執行 | PASS | hypothesis registry + preregistration 是 pre-registration 簽署層；earn_movement Decision Lease 路徑（per REF-20 Sprint 3 Track H dbcf845b 既有 Lease infra）|
| #4 策略不繞風控 | PASS | V103 不觸 Guardian / risk_envelope |
| #5 生存 > 利潤 | PASS | V103 audit trail 服務 §二 #5；hypotheses status='killed' 可顯式 retire underperforming hypothesis |
| #6 失敗默認收縮 | PASS | CHECK enum allowlist + NOT NULL + reconciliation_status DEFAULT 'pending' = fail-closed |
| #7 學習 ≠ 改寫 Live | PASS | hypothesis registry 是 governance layer **不是** ML training feature；earn_movement 走 Decision Lease 非 ML inference |
| #8 交易可解釋 | PASS（**strengthens**）| pre_reg_hash + payload_hash + operator_signature 三層 chain 強化 §二 #8 |
| #9 災難保護 | PASS | reconciliation_status 'mismatch' 為 daily reconciliation 失敗 signal，service Guardian |
| #10 認知誠實 | PASS | §1.2 顯式標 V101 vs v5.7 字段集衝突 + §4.1 列 PA C9 待補資料 + §4.4 spec/AMD wording drift caveat |
| #11 P0/P1 內自主 | PASS | V103 不觸 cognitive_modulator |
| #12 持續進化 | PASS | hypothesis registry 是進化前提（hypothesis pipeline 是 Layer 2 AI 推理鏈核心）|
| #13 AI cost 感知 | PASS | V103 不觸 AI |
| #14 零外部成本可運行 | PASS | V103 純 PG schema，無外部依賴 |
| #15 多 Agent 協作 | PASS | V103 不觸 MessageBus / agent topics |
| #16 組合風險 | PASS | V103 不觸 portfolio_var |

### 9.3 DOC-08 §12 9 條安全不變量觸碰（0/9）

| 不變量 | 觸碰 | 評估 |
|---|---|---|
| Pre-trade audit/replay 必開 | NO | V103 不改 pre-trade gate |
| Lease 必在執行前 acquired | NO | V103 不觸 lease（Sprint 1B earn_movement writer 才接 Lease）|
| 執行回報必落 fills 表 | NO | V103 不改 fills 寫入路徑 |
| 風控降級 → engine 自動止血 | NO | V103 不觸風控 |
| Authorization 過期 → cancel_token shutdown | NO | V103 不觸 authorization |
| Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒 | NO | V103 不觸 mainnet spawn |
| Bybit retCode != 0 → fail-closed 不重試 | NO | V103 不觸 retry（Sprint 1B Bybit Earn API client 才需 retry policy）|
| Reconciler 對賬差異 → 自動降級 paper | NO | V103 不觸既有 reconciler；earn_movement.reconciliation_status 是新 audit layer |
| Operator 角色與 live_reserved 缺一即拒 | NO | V103 不觸 operator auth；preregistration.operator_signature 是 audit signature，不替代 §四 5 gates |

### 9.4 §四 5 硬邊界觸碰（0/5）

`execution_state` / `execution_authority` / `live_execution_allowed` / `decision_lease_emitted` / `max_retries=0` 全 0 觸碰。

---

## §10 開放問題 / Caveat

### 10.1 待 PA C9 確認

1. **V101 land 狀態（CRITICAL）**：V101 已 apply 到 Linux PG？若是，§1.2 路徑 A 採 v5.7 brief 字段集需 reconcile V101 stub table（DROP + 重建？ALTER ADD COLUMN？PM 仲裁）
2. **governance.audit_log column name**：FK target column 是 `id` 還是 `audit_log_id`？§2.3.1 假設 'id'，§4.1 Query 4 確認
3. **Sprint 1A migration numbering**：若 V099/V100/V101/V102 已 apply，本 spec V103 = next-free slot；若否（V101 仍 pending），V103 可能順延 V101/V102 之後（per V101 spec v3 §0 line 5「V099/V100」reserve slot）
4. **`pre_reg_hash` algorithm**：git-style SHA-256? Ed25519? operator key signature 與 hash 是否相同 algorithm？由 IMPL 期 trainer adapter / governance API 定（不在本 spec 設計範圍）
5. **`payload_hash` canonical form**：JSON canonicalization protocol（RFC 8785 JCS / 直接 SHA-256 of sorted-key json.dumps）？由 IMPL 期定

### 10.2 已知 caveat

1. **採 v5.7 brief 字段集路徑（路徑 A）的代價**：V101 spec §3.3.1 + §3.3.2 統計門檻字段（variance_estimator / immutable_trigger_hash / hypothesis_text 等）若仍有 ADR-0026 v3 直接需求，須 IMPL 期透過 payload_json JSONB 序列化進 preregistration 表 — 失去 column-level CHECK constraint 約束
2. **`expected_sharpe` REAL 精度**：4-byte float 精度約 7 decimal digit；對 sharpe 值範圍 [-5, +5] 足夠；若未來需 backtest 報告 sharpe to 8+ digit precision，須 ALTER COLUMN to DOUBLE PRECISION（low cost 1 sec ALTER）
3. **`amount_usdt` NUMERIC(18,8) 精度**：sufficient for Bybit Earn stable coin amount；若擴展到 BTC / ETH stake（小數 18 位），須 NUMERIC(38,18) 或拆 amount_base + amount_quote
4. **V104 退號**：若 PM 仲裁路徑切替（V101 撤回 / 延後），V104 接手 V101 §3.2 子集；本 spec 不寫 V104 SQL；操作為 PA dispatch 期決策
5. **Sprint 1B writer 路徑未在本 spec 範圍**：V103 apply 後 3 表立即 0 row；MIT pipeline maturity audit 認列為 Foundation stage；Sprint 1B 補 writer 後升 Skeleton / Shadow

### 10.3 替代設計選項（路徑 B — V101 字段集路徑）

若 PM 仲裁切替路徑 B（採 V101 spec §3.3.1 + §3.3.2 字段集 / 廢棄 v5.7 brief 字段集），本 spec §2 需 patch：
- hypotheses 改 UUID PK + state 7 值 + spec_json JSONB + originating_alpha_sources / parent_hypothesis_id 自參考
- hypothesis_preregistration 改 15 fields per ADR-0026 v3
- earn_movement_log + V104 退號決策不變

該情境下 V101 spec v3 已涵蓋 hypotheses + preregistration → **V103 退號為 earn_movement_log 單表 spec**（小型 30-50 LOC）。

---

## §11 後續行動（給 PM 派發）

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 V103/V104 spec（路徑 A 採 v5.7 brief 字段集）or 仲裁路徑 B（採 V101 字段集）| PM | Sprint 1A schema prereq closure | P0 |
| PA C9 跑 §4.1 4 條 ssh PG query + 補 4 處 placeholder | PA | Sprint 1A pre-dispatch | P0 |
| Reconcile V101 spec v3 vs V103 spec（路徑 A 採用後，V101 §3.3.1+§3.3.2 廢棄；V101 §3.1 CREATE TYPE + §3.2 12 表 ADD COLUMN 保留）| PA | Sprint 1A pre-dispatch | P0 |
| IMPL kickoff（Sprint 1A 啟動）：派 E1 寫 V103.sql + Linux PG dry-run × 2 + E2/E4 + restart_all 部署 | PM | Sprint 1A | P1 |
| Sprint 1B writer 上線：hypothesis registry writer + Bybit Earn API client + earn_movement_log writer | E1 (Sprint 1B) | Sprint 1B | P2 |
| Healthcheck 加 [56-59] for V103 三表 first-row + freshness + status distribution（Sprint 1B 整合）| E1 (Sprint 1B) | Sprint 1B | P2 |

### 11.1 Sprint 1A schema prereq closure 標誌

本 spec PM sign-off + PA C9 dry-run 補資料 land + V101 vs V103 reconciliation 路徑 PM 仲裁完成 → Sprint 1A schema prereq 解除 → IMPL kickoff 派 E1。

---

## §12 關鍵文件指針（後續 IMPL agent / PM / E2 / E4 必讀）

- 本 V103/V104 spec：本檔
- v5.7 dispatch-safe patch：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.7.md` §3 + §4 + §8 Sprint 1A
- V101/V102 spec v3：`srv/docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md` v3
- V094 spec（Guard A/B/C + Linux PG dry-run 範式）：`srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- V083 mirror（ADD COLUMN + NOT VALID CHECK 範式）：`srv/sql/migrations/V083__fills_entry_context_id_close_check.sql`
- schema_guard_template：`srv/sql/migrations/templates/schema_guard_template.sql`
- repair binary：`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`
- V055 5-round loop + sqlx hash drift incident lessons：`memory/feedback_v_migration_pg_dry_run.md` + `memory/project_2026_05_02_p0_sqlx_hash_drift.md`
- CLAUDE.md §七 V### migration 規範：`srv/CLAUDE.md`
- MIT 5.21 executability audit Risk 1：`srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-21--v57_executability_audit.md`
- governance.audit_log V098 spec：`srv/sql/migrations/V098__governance_audit_log_halt_event_types.sql`

---

## §13 審計記錄

| Source agent | Role | Audit pattern coverage |
|---|---|---|
| MIT 5.21 executability audit | 起草者 | Risk 1 (V103/V104 placeholder) closure 路徑 / pipeline maturity 5 階段 / Guard A/B/C / Linux PG dry-run mandate |
| PA Sprint C v101_v102 spec v3 (2026-05-20) | 範式參考 | track ENUM 設計 / 12 表 ADD COLUMN / Phase 0 catch-up sequence / acceptance criteria 結構 |
| PA Wave 2 Track A2 v094 spec (2026-05-15) | 範式參考 | Guard A/B/C 完整 template / Linux PG dry-run × 2 round protocol / sqlx checksum repair SOP / 13 caller sites enumeration / §11 風險評估 + 16 原則 / §12 E2 review 重點 |
| db-schema-design-financial-time-series skill | DB schema audit | hypertable vs regular table 判斷 / hot-path index 選用 / engine_mode CHECK 4 值 / Guard A/B/C 規範 / partial index 設計 |
| ml-pipeline-maturity-audit skill | Pipeline stage 評級 | 3 表 V103 apply 後立即 0 row 屬 Foundation stage；Sprint 1B writer 接線後升 Skeleton；Sprint 1B+ row 累積 + consumer 接線後升 Shadow |
| feature-engineering-protocol skill | Leakage 防範 | hypotheses / preregistration 是 governance layer **非** ML training feature；engine_mode filter `IN ('live','live_demo')` rule（如 future ML pipeline 引用此 layer）|
| time-series-cv-protocol skill | CV 設計 | 不適用（hypotheses 表本身 ~100 row/yr 不訓練 ML）|
| data-drift-detection skill | Drift 偵測 | 不適用（hypotheses 表是 governance 層；statistical drift 監控屬 Sprint 1B+ healthcheck）|

### 13.1 待 PA dispatch 前補充

- [ ] PA C9 dry-run 4 條 ssh query 結果（§4.1）
- [ ] V101 vs V103 字段集 reconciliation PM 仲裁結論（§1.2 路徑 A vs B）
- [ ] governance.audit_log.id column 確認（§2.3.1 FK target）
- [ ] V101 land 狀態確認（V104 退號決策；§1.3）
- [ ] `pre_reg_hash` / `payload_hash` algorithm 決策（IMPL 期 trainer / governance API 定；§10.1）

---

**END V103 / V104 spec draft v0**
