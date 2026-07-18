> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）

# V116 / M7 — Decay Detector (DETECTOR layer only) + Lifecycle Schema

**Spec date**: 2026-05-31
**Author**: PA
**Ticket**: `M7-DECAY-DETECTOR-V116`
**Status**: pre-IMPL design spec (design only — 不寫 IMPL code、不在 Mac 跑 SQL、不碰任何 already-applied migration；可 ssh read-only)
**改動風險**: **高**（新 learning hypertable + 6-state lifecycle ENUM + 新 Rust detector module；觸 M1 LAL `DecayStateProvider` 未來 wire 點）；硬邊界 **0 觸碰**
**Scope 紅線（一句話）**: 本次只做 **detector 層**——4 signal 計算 + 寫 `decay_signals` + FSM transition **只到** `NORMAL_LIVE → DECAY_DETECTED`（alert + 啟動 14d clock，**絕不改任何 live sizing**）；所有 demote / 50%-cut / enforcement / RETIRED-blocker enum **全 land 但 transition 邏輯不接線**（`unimplemented!()` / feature-flag off，mirror M1 LAL Tier 2/3/4 既有範式）。
**v5.8 autonomy freeze 例外**: operator 2026-05-31 拍板——13 autonomy 模組凍結（M1/M2/M6/M8/M9 active IMPL 停），**唯一例外 = M7 decay detector 提前 IMPL**（協同 P0-EDGE-1 診斷識別 alpha-deficient 策略）。

---

## §0 摘要與最關鍵架構判斷

### §0.1 一句話

V116 建 `learning.decay_signals`（hypertable，多 module 共寫的 signal ledger）+ `learning.strategy_lifecycle`（M7 唯一寫入的 6-state FSM）。Detector 層只接 signal 計算 + 單一 transition（`NORMAL_LIVE → DECAY_DETECTED`，2+ signal 觸發）；其餘 5 條 FSM 邊（含 50% sizing cut）enum land 但 `unimplemented!()`，因為它們是 autonomy active path #6（§11.5）需 LAL approval，已凍結。

### §0.2 ⚠️ 三條 E1 必知的環境真相（PA 已 grep 自證）

| 讀證 | 事實 |
|---|---|
| `git fetch` + `ls sql/migrations/V11*` | on-disk migration head = **V115**（`V115__panel_basis_panel.sql`）；runtime `_sqlx_migrations max=115`（per TODO §0 v87）。**V116 free**。V117 保留 ADR-0046 funding_arb V3，**不碰**。 |
| `grep -rlE 'decay_signals|strategy_lifecycle' sql/migrations/` | 命中 V107/V112 **僅為註解引用**（placeholder query target），**無實際 table 定義**。V116 是這兩表的首建。 |
| `grep -rn 'decay_signals' rust/.../governance/lal/mod.rs:179-228` | M1 LAL 已有 `DecayStateProvider` trait（`lifecycle_state(strategy_id) -> Option<String>`）+ `FailClosedDecayProvider` stub。**這是 schema-agnostic 抽象，非 hard-coded column ref**；Sprint 4+ 才 wire PG。→ V116 detector **不需**也**不可**改 LAL；只負責讓 `strategy_lifecycle` 表存在 + 被 detector 寫入。 |

### §0.3 ⚠️ 解決 V113 doc 的 schema 設計張力（最重要 PA 判斷）

2026-05-21 V113 placeholder doc 的 §2.1 早期大綱把 `lifecycle_state` 放在 `decay_signals` 上，但 §8 full DDL 又把 6-state 同時放在 `decay_signals.lifecycle_state`。這與 ADR-0044 Decision 1「`strategy_lifecycle` 寫入權 M7 唯一」**衝突**：若 lifecycle state 寫在多 module 共寫的 `decay_signals` 上，single-authority enforcement 就破了。

**PA 拍定（V116 採此，覆蓋 V113 doc §8 的 column placement）**:

- `decay_signals` = **純 signal ledger**（多 module emit；**無 lifecycle_state column**）。signal source 寫 metric / threshold / severity，不寫 FSM state。
- `strategy_lifecycle` = **唯一 FSM state 表**（M7 exclusive write，`decision_authority='M7'` CHECK hard-lock per ADR-0044 Decision 1）。`current_state` 6-enum 在這裡。
- M1 LAL `DecayStateProvider` 未來 query 的是 `strategy_lifecycle.current_state`（不是 `decay_signals`）——這對齊 ADR-0044 Decision 6 + 修正 V113 doc 的歧義。spec §6.3 留 LAL alignment note。

> 衝突標記（per CLAUDE Operating Style §7）：V113 doc §8 `decay_signals.lifecycle_state` 為 cleanup debt；V116 不沿用，採 single-authority 分離。MIT dry-run + CC review 須確認此 placement 收斂。

### §0.4 為什麼 detector-only 是正確切分

- detector 純 **read + compute + emit**（讀 fills/equity curve → 算 signal → 寫 signal ledger + 單一 alert transition）。完全落在原則 2「讀寫分離；研究/學習 mostly read-only」+ 原則 7「學習 ≠ 改寫 live」。
- 任何「改 live sizing」（50% cut / halt / RETIRED block）= 動 trading state，必經 LAL gate + GovernanceHub（原則 3/4），且是 §11.5 autonomy active path #6——**這正是凍結的東西**。detector 不碰，零 live-state 副作用。

---

## §1 IN / OUT Scope 硬邊界（E1 不得越界）

### §1.1 IN（本次 IMPL = detector 層）

| # | 項目 | 落地 |
|---|---|---|
| IN-1 | 4 signal source 計算（per ADR-0044 §2 Decision 2）：A Sharpe decay (rolling 30d) / B Drawdown widening (7d vs envelope) / C OOS degradation (live 30d vs backtest 90d OOS Sharpe) / D N-consecutive-loss（hit-rate plummet 代理） | Rust detector module 純計算 |
| IN-2 | M11 replay divergence **ingest as 5th signal**（M11 已驗 divergence → count as 1-of-5；M7 不重跑 replay，per ADR-0044 Decision 2 + §6.3） | 讀 V107 `replay_divergence_log`，emit 到 `decay_signals` |
| IN-3 | `learning.decay_signals` 寫入（detector + 其他 module 都 emit 到此 ledger） | V116 hypertable |
| IN-4 | `learning.strategy_lifecycle` 建表 + 6-state ENUM **全 land** | V116 regular table |
| IN-5 | FSM transition **只接** `NORMAL_LIVE → DECAY_DETECTED`：2+ signal source 同時 trigger → 寫 `strategy_lifecycle` 一筆 + **M3 alert WARN + 啟動 14d clock**（記 `clock_started_at` + `clock_expires_at`）。**絕不改 sizing** | M7 detector |
| IN-6 | 單 signal trigger → DRAFT advisory（寫 `decay_signals` severity=WARN，**不寫 lifecycle**，無 transition；per ADR-0044 §2「單 signal → DRAFT advisory」） | M7 detector |
| IN-7 | DECAY_DETECTED 的 **auto-clear / 14d clock 過期語意**（防 first-detection deadlock，詳 §5） | M7 detector + FSM |
| IN-8 | Bonferroni 多重檢驗校正：1.5σ trigger 必加 second confirmation（連續 5 trading day；per ADR-0044 §2） | signal 計算層 |

### §1.2 OUT（凍結；建表/enum 預留但 transition 邏輯不接線）

| # | 凍結項 | 凍結理由 | 落地範式 |
|---|---|---|---|
| OUT-1 | `DECAY_DETECTED → DEMOTE_PROPOSED`（3+ signal OR 14d sustained） | demote proposal = autonomy；超 detector 域 | `unimplemented!()` + spec note |
| OUT-2 | `DEMOTE_PROPOSED → DECAY_ENFORCED`（**50% size cut**） | = autonomy active path #6（§11.5），需 LAL approval + AMD-2026-05-21-01 protected scope；**operator 凍結的核心** | feature-flag off + `unimplemented!()` |
| OUT-3 | `DECAY_ENFORCED` enforcement（改 live sizing × 0.5 / continue at reduced） | 動 live trading state；原則 3/4 必經 GovernanceHub | enum land；enforcement path 不寫 |
| OUT-4 | `DECAY_ENFORCED → RECOVERY` / `RECOVERY → NORMAL_LIVE`（7d gradient 還原 sizing） | 同樣動 sizing；依賴 OUT-2/3 先解凍 | `unimplemented!()` |
| OUT-5 | `DECAY_ENFORCED → RETIRED`（halt / size=0）+ §9 14d×50% 累積虧損即時 retire | halt = 最高風險 live action | `unimplemented!()` |
| OUT-6 | M1 LAL **Tier 0 RETIRED blocker** wire（ADR-0044 Decision 6） | M1 凍結；LAL `DecayStateProvider` 維持 `FailClosedDecayProvider` stub 不動 | **不碰 LAL mod.rs** |
| OUT-7 | M6 reward weight downweight（ADR-0044 §7）+ Allocator demote proposal | M6 凍結 | 不接 |

**OUT enum land 但不接線範式（mirror M1 LAL）**：`rust/.../governance/lal/mod.rs:34` 既有範式——「Tier 2/3/4 transition 邏輯本 spike 不寫；未來呼叫 `unimplemented!()` 立即 panic」。M7 FSM 的 OUT transition 函數簽名全 land（讓 E4 proptest 能 enumerate 6-state matrix），body = `unimplemented!("OUT-scope per V116 spec §1.2; LAL-gated, frozen 2026-05-31")`。任何 OUT transition 在 runtime 被呼即 panic（fail-loud），杜絕「凍結項偷偷半接線」。

### §1.3 Scope 紅線一句話（給 E1）

> **只能讓策略從 NORMAL_LIVE 走到 DECAY_DETECTED（純 alert + 啟 14d clock，不動一分錢倉位）。任何會改 live sizing 的 transition（特別是 50% cut、halt、RETIRED block）都是凍結的 `unimplemented!()`，碰了就是越界。**

---

## §2 DDL — `learning.decay_signals`（hypertable，signal ledger）

> Port 自 V113 doc §8.1，**移除 `lifecycle_state` / `lifecycle_prev_state` column**（per §0.3 single-authority 分離）；signal ledger 不存 FSM state。

```sql
-- V116__m7_decay_signals_lifecycle.sql （Linux PG only；不在 Mac 跑）

CREATE SCHEMA IF NOT EXISTS learning;

CREATE TABLE IF NOT EXISTS learning.decay_signals (
    id                          BIGSERIAL,
    strategy_id                 TEXT NOT NULL,
    symbol                      TEXT NOT NULL,
    signal_source               TEXT NOT NULL
                                CHECK (signal_source IN (
                                    'SHARPE_DECAY',          -- Signal A
                                    'DRAWDOWN_WIDEN',        -- Signal B
                                    'OOS_DEG',               -- Signal C
                                    'CONSECUTIVE_LOSS',      -- Signal D (hit-rate plummet 代理)
                                    'M11_REPLAY_DIVERGENCE'  -- 5th ingest source
                                )),
    signal_severity             TEXT NOT NULL
                                CHECK (signal_severity IN ('INFO','WARN','CRITICAL')),
    signal_metric_name          TEXT NOT NULL,   -- e.g. 'sharpe_30d','dd_max_7d','consecutive_loss_count'
    signal_value                NUMERIC(18,8) NOT NULL,
    signal_threshold            NUMERIC(18,8) NOT NULL,
    window_size_days            INTEGER NOT NULL CHECK (window_size_days BETWEEN 1 AND 365),
    live_window_days            INTEGER NOT NULL DEFAULT 30,
    oos_window_days             INTEGER NOT NULL DEFAULT 90,
    -- 5-day second-confirmation 計數（Bonferroni 校正；per ADR-0044 §2）
    confirmation_day_count      INTEGER NOT NULL DEFAULT 0 CHECK (confirmation_day_count BETWEEN 0 AND 90),
    -- M11 ingest reference（V107 source；UUID NULL 直到 V107 final type 確認，per V113 doc §8.1 note）
    m11_replay_divergence_ref   UUID NULL,
    -- detector 對此 signal 的判定（不寫 lifecycle；只記 advisory 決策）
    decision_action             TEXT NULL
                                CHECK (decision_action IN (
                                    'NO_ACTION_UNDER_THRESHOLD',
                                    'DRAFT_ADVISORY_SINGLE_SIGNAL',
                                    'CONTRIBUTED_TO_DECAY_DETECTED'
                                ) OR decision_action IS NULL),
    evidence_json               JSONB,
    engine_mode                 TEXT NOT NULL
                                CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    observed_at                 TIMESTAMPTZ NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, observed_at)   -- hypertable 必含 partition column（per V107/V104 樣板硬邊界）
);
```

### §2.1 Hypertable + compression + retention（per ADR-0044「hypertable 必」）

```sql
SELECT create_hypertable('learning.decay_signals', 'observed_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

ALTER TABLE learning.decay_signals SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'strategy_id, signal_source',
    timescaledb.compress_orderby = 'observed_at DESC'
);

SELECT add_compression_policy('learning.decay_signals', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('learning.decay_signals', INTERVAL '180 days', if_not_exists => TRUE);
-- 180d = 90d M7 historical query window + 90d post-incident audit buffer（per V113 doc §8.2）
```

### §2.2 Indexes

```sql
-- per-strategy signal timeline（detector aggregate hot path）
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decay_signal_strategy_observed
    ON learning.decay_signals (strategy_id, symbol, observed_at DESC);

-- alert dashboard partial（WARN/CRITICAL）
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decay_signal_severity
    ON learning.decay_signals (signal_severity, observed_at DESC)
    WHERE signal_severity IN ('WARN','CRITICAL');

-- M11 ingest dedup hot path
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decay_signal_m11
    ON learning.decay_signals (strategy_id, observed_at DESC)
    WHERE signal_source = 'M11_REPLAY_DIVERGENCE';
```

> 注：hypertable 上 `CREATE INDEX CONCURRENTLY` 在 TimescaleDB ≥ 2.x 對 chunk 逐一建；MIT dry-run 須驗 concurrently 在新 hypertable（0 chunk）下不報錯。若 dry-run 顯示 transactional migration 不容 CONCURRENTLY（sqlx 單一 tx），降級為非-CONCURRENTLY（0 row 新表無鎖風險）——**此降級決策由 MIT Linux empirical 拍**，spec 不預設。

---

## §3 DDL — `learning.strategy_lifecycle`（M7 唯一寫入，6-state FSM）

```sql
CREATE TABLE IF NOT EXISTS learning.strategy_lifecycle (
    lifecycle_id            BIGSERIAL PRIMARY KEY,
    strategy_id             TEXT NOT NULL,
    symbol                  TEXT NOT NULL,
    -- 6-state ENUM 全 land（per ADR-0044 Decision 3）；detector 只寫到 DECAY_DETECTED
    current_state           TEXT NOT NULL
                            CHECK (current_state IN (
                                'NORMAL_LIVE',
                                'DECAY_DETECTED',
                                'DEMOTE_PROPOSED',    -- OUT-1（enum land，transition frozen）
                                'DECAY_ENFORCED',     -- OUT-2/3（enum land，transition frozen）
                                'RECOVERY',           -- OUT-4（enum land，transition frozen）
                                'RETIRED'             -- OUT-5（enum land，transition frozen）
                            )),
    previous_state          TEXT
                            CHECK (previous_state IN (
                                'NORMAL_LIVE','DECAY_DETECTED','DEMOTE_PROPOSED',
                                'DECAY_ENFORCED','RECOVERY','RETIRED'
                            ) OR previous_state IS NULL),
    -- 觸發本次 transition 的 signal（FK 弱關聯 decay_signals.id）
    triggering_signal_id    BIGINT NULL,
    triggering_signal_count INTEGER NOT NULL DEFAULT 0,   -- 觸發時 active signal source 數（2+ 才進 DECAY_DETECTED）
    -- 14d clock（DECAY_DETECTED 啟動；§5 auto-clear / 過期語意）
    clock_started_at        TIMESTAMPTZ NULL,
    clock_expires_at        TIMESTAMPTZ NULL,
    -- §9 14d×50% 累積虧損即時追蹤欄位（OUT-5 用；detector 階段恆 NULL）
    cumulative_pnl_in_state NUMERIC(20,8) NULL,
    -- CR-7 single decay authority hard-lock（per ADR-0044 Decision 1）
    decision_authority      TEXT NOT NULL DEFAULT 'M7'
                            CHECK (decision_authority = 'M7'),
    governance_audit_ref    BIGINT NULL,    -- FK 弱關聯 governance.audit_log.id（OUT transition 才填）
    evidence_json           JSONB,
    engine_mode             TEXT NOT NULL
                            CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    entered_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### §3.1 Constraints + Indexes

```sql
-- 同 strategy+symbol 同時刻不重複 lifecycle entry
CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_lifecycle_entry
    ON learning.strategy_lifecycle (strategy_id, symbol, entered_at);

-- active decay state partial（非 NORMAL_LIVE 的當前狀態 hot path）
CREATE INDEX IF NOT EXISTS idx_strategy_lifecycle_active
    ON learning.strategy_lifecycle (current_state, entered_at DESC)
    WHERE current_state <> 'NORMAL_LIVE';

-- per-strategy lifecycle history（latest-state-per-strategy 查詢 + LAL 未來 wire）
CREATE INDEX IF NOT EXISTS idx_strategy_lifecycle_strategy_entered
    ON learning.strategy_lifecycle (strategy_id, symbol, entered_at DESC);

-- 14d clock 過期掃描 hot path（§5 auto-clear sweep）
CREATE INDEX IF NOT EXISTS idx_strategy_lifecycle_clock_expiry
    ON learning.strategy_lifecycle (clock_expires_at)
    WHERE current_state = 'DECAY_DETECTED' AND clock_expires_at IS NOT NULL;
```

> **`strategy_lifecycle` 故意非 hypertable**：per-strategy 1-2 lifecycle event/yr × 5 strategy ≈ 10 row/yr（per V113 doc §2.5）；regular table 足夠，append-only history（每次 transition INSERT 新 row，不 UPDATE）。latest-state 查詢走 `DISTINCT ON (strategy_id, symbol) ... ORDER BY entered_at DESC`。

### §3.2 Single-authority enforcement（per ADR-0044 Decision 1 反模式）

`decision_authority = 'M7'` CHECK hard-lock = schema 級 enforce「其他 module 不得直寫 `strategy_lifecycle`」。其他 module（M11/M8/M2/M9）只能 INSERT 到 `decay_signals`（emit signal），由 M7 polling + aggregate 後決定是否寫 lifecycle。任何非 'M7' 的 `strategy_lifecycle` INSERT 即被 CHECK reject（ADR-0044 反模式 (a) M11 直接寫 strategy_lifecycle 繞 M7）。

> **PG role grant 補強（建議，非阻塞）**：Linux PG 可額外 `REVOKE INSERT ON learning.strategy_lifecycle FROM <non-m7-role>`；但本系統單一 `openclaw` role，role-level 分離不可行，故 CHECK constraint + application 紀律是主要 enforcement。MIT dry-run 須驗 CHECK 真 reject 非-'M7' INSERT。

---

## §4 Guard A / B / C（per CLAUDE §七 + V104/V107 樣板）

### §4.1 Guard A — table/extension/FK-target 存在性

```sql
-- 包在 migration 開頭 DO block
DO $$
BEGIN
    -- TimescaleDB extension 必在（hypertable infra prereq）
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname='timescaledb') THEN
        RAISE EXCEPTION 'V116 Guard A FAIL: timescaledb extension not installed.';
    END IF;
    -- learning schema（V116 自建 IF NOT EXISTS，此處僅確認可建）
    -- V107 replay_divergence_log 存在（m11_replay_divergence_ref ingest source；弱關聯不強制 FK）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='replay_divergence_log'
    ) THEN
        RAISE WARNING 'V116 Guard A WARN: learning.replay_divergence_log (V107) absent; '
                      'M11 ingest signal (5th source) will be inert until V107 present.';
        -- WARN 非 FAIL：M11 ingest 是 decay-relevant 非 decay-essential（ADR-0044 §Negative）；
        -- 4 主 signal 仍可獨立 trigger。
    END IF;
END $$;
```

### §4.2 Guard B — 不適用

V116 是**新建表**（CREATE TABLE IF NOT EXISTS），不 ALTER 既有 column type。無 type-sensitive `ADD COLUMN`。本 spec 不設 Guard B 段（與 V113 doc §3「Guard B 不適用」一致）。

### §4.3 Guard C — post-apply 完整性後驗（**V104 timestamptz 教訓必納**）

```sql
DO $$
DECLARE
    v_chunk_interval    DOUBLE PRECISION;
    v_lifecycle_check   TEXT;
    v_authority_check   INTEGER;
BEGIN
    -- ============ V104 教訓核心（v86 增量）============
    -- Guard C 對 timestamptz hypertable 必用 time_interval + EXTRACT(EPOCH ...)；
    -- 絕不用 integer_interval（後者只對 BIGINT/epoch-ms time column 有值，
    -- timestamptz 維度讀 integer_interval = NULL → 誤判 false-pass/false-fail）。
    -- 對齊 V104:387-400 + V107:631-644 模式。
    SELECT EXTRACT(EPOCH FROM time_interval) INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_schema = 'learning'
      AND hypertable_name = 'decay_signals'
      AND column_name = 'observed_at';
    IF v_chunk_interval IS NULL THEN
        RAISE EXCEPTION 'V116 Guard C FAIL: decay_signals hypertable not created on observed_at '
                        '(timestamptz time_interval read NULL — 勿改用 integer_interval).';
    END IF;
    IF v_chunk_interval <> 604800 THEN
        RAISE EXCEPTION 'V116 Guard C FAIL: chunk_time_interval = % sec (expected 604800 = 7 days).',
            v_chunk_interval;
    END IF;

    -- decay_signals signal_source CHECK 含 5 source（探首/尾/M11）
    PERFORM 1 FROM pg_constraint
        WHERE conrelid='learning.decay_signals'::regclass AND contype='c'
          AND position('M11_REPLAY_DIVERGENCE' IN pg_get_constraintdef(oid)) > 0
          AND position('SHARPE_DECAY' IN pg_get_constraintdef(oid)) > 0;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'V116 Guard C FAIL: decay_signals signal_source CHECK missing 5-source enum.';
    END IF;

    -- strategy_lifecycle current_state CHECK 含 6-state 全（探 NORMAL_LIVE + DECAY_DETECTED + RETIRED）
    SELECT pg_get_constraintdef(oid) INTO v_lifecycle_check
    FROM pg_constraint
    WHERE conrelid='learning.strategy_lifecycle'::regclass AND contype='c'
      AND position('current_state' IN pg_get_constraintdef(oid)) > 0
    LIMIT 1;
    IF v_lifecycle_check IS NULL
       OR position('NORMAL_LIVE' IN v_lifecycle_check) = 0
       OR position('DECAY_DETECTED' IN v_lifecycle_check) = 0
       OR position('DEMOTE_PROPOSED' IN v_lifecycle_check) = 0
       OR position('DECAY_ENFORCED' IN v_lifecycle_check) = 0
       OR position('RECOVERY' IN v_lifecycle_check) = 0
       OR position('RETIRED' IN v_lifecycle_check) = 0 THEN
        RAISE EXCEPTION 'V116 Guard C FAIL: strategy_lifecycle current_state CHECK missing 6-state enum. '
                        'Actual: %.', v_lifecycle_check;
    END IF;

    -- CR-7 single authority hard-lock CHECK 真存在
    SELECT COUNT(*) INTO v_authority_check
    FROM pg_constraint
    WHERE conrelid='learning.strategy_lifecycle'::regclass AND contype='c'
      AND position('decision_authority' IN pg_get_constraintdef(oid)) > 0
      AND position('M7' IN pg_get_constraintdef(oid)) > 0;
    IF v_authority_check = 0 THEN
        RAISE EXCEPTION 'V116 Guard C FAIL: strategy_lifecycle decision_authority=''M7'' CHECK missing '
                        '(ADR-0044 Decision 1 single-authority enforcement).';
    END IF;

    -- compression + retention policy 各 1（policy_compression / policy_retention）
    IF (SELECT COUNT(*) FROM timescaledb_information.jobs
        WHERE hypertable_name='decay_signals'
          AND proc_name IN ('policy_compression','policy_retention')) <> 2 THEN
        RAISE EXCEPTION 'V116 Guard C FAIL: decay_signals compression+retention policy expected 2 jobs.';
    END IF;

    RAISE NOTICE 'V116: all guards PASS — decay_signals hypertable (observed_at 7d chunk, '
                 '5-source enum, compress+retention), strategy_lifecycle (6-state enum, M7 authority lock). '
                 'DETECTOR layer only — OUT transitions land as enum but unimplemented!() per spec §1.2.';
END $$;
```

---

## §5 First-Detection Deadlock 防護 + 14d Clock 過期語意（必納）

> 教訓來源：memory `feedback_first_detection_deadlock_pattern`（2026-04-24 bb_breakout FIX-26-DEADLOCK-1）——`is_none()` guard + 無過期 auto-clear → symbol 永久 dormant。M7 的等價陷阱：策略進 `DECAY_DETECTED` 後若 signal 退去但**無 auto-clear**，且 OUT scope 凍結了 `DECAY_DETECTED → DEMOTE_PROPOSED`（往前的出口被凍），策略會**永久卡 DECAY_DETECTED**——既不前進（凍結）也不後退（無 auto-clear）= 死狀態。

### §5.1 死狀態風險具體推導

```
進入：2+ signal trigger → NORMAL_LIVE → DECAY_DETECTED（IN-5）+ 啟 14d clock
往前出口：DECAY_DETECTED → DEMOTE_PROPOSED  ← OUT-1 FROZEN（unimplemented!）
往後出口：DECAY_DETECTED → NORMAL_LIVE      ← 若不設計 = 不存在 → 永久卡
```

**這在 detector-only scope 下尤其致命**：因為往前的邊被凍結，detector 階段唯一能讓策略離開 DECAY_DETECTED 的路只有「往後回 NORMAL_LIVE」。**所以 detector 層必須 IMPL `DECAY_DETECTED → NORMAL_LIVE` 這條 auto-clear 邊**（它不改 sizing，純狀態回退 + alert clear，落在 IN scope）。

### §5.2 14d Clock 過期 + auto-clear 三條語意（detector 必 IMPL）

| # | 條件 | Action | scope |
|---|---|---|---|
| AC-1 | DECAY_DETECTED 期間 **active signal source 數退回 < 2**（signal 退去；連續 7d 都 < 2，per recovery 對稱於 entry 的 2-signal 門檻） | `DECAY_DETECTED → NORMAL_LIVE`（auto-clear）；clear 14d clock；M3 alert RESOLVE | **IN**（純狀態回退 + alert，不改 sizing） |
| AC-2 | 14d clock **過期**（`now() >= clock_expires_at`）且 active signal **仍 ≥ 2** | detector-only scope：**不能**自動進 DEMOTE_PROPOSED（OUT-1 凍結）→ 改為 **emit M3 alert ESCALATE-PENDING（advisory）+ 寫 `decay_signals` decision_action='CONTRIBUTED_TO_DECAY_DETECTED' severity=CRITICAL**，**狀態維持 DECAY_DETECTED**（不前進不後退，但**有可見 alert + audit 記錄**，非靜默死狀態） | **IN**（alert only；transition 仍凍） |
| AC-3 | 14d clock 過期且 active signal 已退（< 2） | 等同 AC-1，回 NORMAL_LIVE | **IN** |

> **AC-2 是關鍵防死狀態設計**：detector 不能前進（OUT-1 凍）但**絕不靜默**。clock 過期 + signal 持續 = 升級為 CRITICAL advisory alert，operator 透過 M3 看到「此策略 decay 持續 14d+ 但 enforcement 凍結中，需人工決策或解凍 M7 enforcement」。這把「永久卡」從**靜默死鎖**轉成**可見的 pending-human 狀態**——對齊原則 6「uncertainty defaults to conservative」+ 原則 8「可解釋」。E4 dead-state scan 必驗：不存在任何 `current_state` 在無 alert / 無 audit row 下停滯 > 14d。

### §5.3 Auto-clear sweep 機制

- detector nightly cron（與 signal 計算同 cycle；non hot-path per 原則 13）掃 `idx_strategy_lifecycle_clock_expiry`（§3.1）：所有 `current_state='DECAY_DETECTED' AND clock_expires_at <= now()` 的 row。
- 對每 row 重算 active signal count → 套 AC-1/AC-2/AC-3。
- **append-only**：auto-clear 回 NORMAL_LIVE = INSERT 新 lifecycle row（`previous_state='DECAY_DETECTED'`, `current_state='NORMAL_LIVE'`），不 UPDATE 舊 row（保 audit 鏈，原則 8）。
- **`is_none()` 反模式對策**：latest-state 查詢若回 `None`（無 row）= 新策略視為 NORMAL_LIVE（合理）；但 detector **必有過期 auto-clear sweep**，故不會出現「進了 DECAY_DETECTED 就無人 re-evaluate」的 bb_breakout dormant 重演。E2 deadlock scan 必確認 sweep cron 真 spawn 且真掃過期 row。

---

## §6 Rust Detector Module 設計（架構切分，E1 IMPL）

### §6.1 模組落點

新模組 `rust/openclaw_engine/src/learning/decay_detector/`（mirror `governance/lal/` 的 module-doc-header + trait-stub 範式）。**不放 governance/ 下**（detector 是 learning 平面，read+compute；governance/ 是執行授權域）。對齊原則 2 讀寫分離 + 原則 7 學習≠live。

> singleton 註冊：若 detector 持有長運行 state（如 signal cache / cron handle），須登記 singleton authority table（per CLAUDE §七「New mutable singletons must be registered」）。E1 IMPL 時確認。

### §6.2 核心 trait / struct（簽名 land，OUT body = unimplemented!）

```rust
// 純計算層 — 4 signal + M11 ingest
pub trait DecaySignalSource {
    fn evaluate(&self, ctx: &StrategyWindowCtx) -> Result<Option<DecaySignal>, DecayError>;
}
// SharpeDecaySignal / DrawdownWidenSignal / OosDegradationSignal /
// ConsecutiveLossSignal / M11DivergenceIngest 各 impl

// FSM — 6-state enum 全 land
pub enum LifecycleState {
    NormalLive, DecayDetected, DemoteProposed, DecayEnforced, Recovery, Retired,
}

pub struct DecayFsm { /* ... */ }
impl DecayFsm {
    // ===== IN scope（detector 真接線）=====
    pub fn evaluate_normal_to_detected(&self, active_signals: &[DecaySignal]) -> Option<LifecycleTransition>; // 2+ signal
    pub fn evaluate_detected_autoclear(&self, st: &LifecycleRow, active_count: usize, now: DateTime<Utc>)
        -> Option<LifecycleTransition>; // §5 AC-1/2/3

    // ===== OUT scope（enum land，body = unimplemented! per §1.2）=====
    pub fn evaluate_detected_to_demote_proposed(&self, _: &LifecycleRow) -> ! {
        unimplemented!("OUT-1 per V116 spec §1.2 — DEMOTE_PROPOSED is autonomy active path #6, frozen 2026-05-31")
    }
    pub fn enforce_decay_50pct_sizing(&self, _: &LifecycleRow) -> ! {
        unimplemented!("OUT-2/3 per V116 spec §1.2 — 50% size cut is LAL-gated autonomy, frozen 2026-05-31")
    }
    pub fn evaluate_enforced_to_recovery(&self, _: &LifecycleRow) -> ! { unimplemented!("OUT-4 frozen") }
    pub fn evaluate_enforced_to_retired(&self, _: &LifecycleRow) -> ! { unimplemented!("OUT-5 frozen") }
}
```

> feature-flag 替代方案（E1 二選一，與 M1 LAL 一致即可）：若團隊偏好 compile-time gate，OUT transition 用 `#[cfg(feature = "m7_enforcement")]`（default off）；spec 不強制，但 **runtime 被呼必 fail-loud**（panic 或 compile-out），杜絕半接線。

### §6.3 M1 LAL alignment note（不碰 LAL，只記契約）

M1 LAL `DecayStateProvider::lifecycle_state(strategy_id)`（`lal/mod.rs:179`）未來 wire 時 query 的是 **`learning.strategy_lifecycle.current_state`**（latest-per-strategy），**不是** `decay_signals`。V116 讓此表存在 + 被 detector 寫入 DECAY_DETECTED/NORMAL_LIVE。**OUT-6**：本次**不碰 LAL mod.rs**，`FailClosedDecayProvider` stub 維持原樣（RETIRED blocker 隨 M1 解凍才 wire）。spec 在此留契約紀錄供 M1 解凍時對齊。

### §6.4 M11 ingest 邊界（per ADR-0044 Decision 2 + §6.3 dedup）

M7 讀 V107 `replay_divergence_log` 的已驗 divergence（M11 CRITICAL 或 WARN 持續 14d）→ emit 為 `decay_signals` 的 `M11_REPLAY_DIVERGENCE` source（count as 1-of-5）。**M7 不重跑 replay**；M11 down → 少 1 signal 但 4 主 signal 仍可獨立 trigger（decay-relevant 非 decay-essential）。**反模式**：M11 直寫 `strategy_lifecycle`（被 §3.2 CHECK 擋）。

---

## §7 Linux PG Empirical Dry-Run SOP（IMPL sign-off 前置；mandatory）

> per memory `feedback_v_migration_pg_dry_run`：Mac mock 抓不到 PG runtime semantic；**double-apply（first + re-apply 都 PASS）是 load-bearing gate**（V055 5-round + V114 3-round 教訓；first-apply PASS ≠ re-apply 安全；TimescaleDB compressed-twin column-level 地雷）。**此 SOP 由 MIT 在 Linux 跑，非 E1，非 Mac。**

### §7.1 SOP（dryrun DB，非 production）

```bash
# Step 1 — runtime head 對齊（確認 V115 head + V116 forward-only）
ssh trade-core "psql \$OPENCLAW_PG_URL -c \"SELECT MAX(version) FROM _sqlx_migrations;\""
# 預期 = 115

# Step 2 — Mac SSOT 寫 V116__m7_decay_signals_lifecycle.sql 後 scp → dryrun apply
#   scp srv/sql/migrations/V116__m7_decay_signals_lifecycle.sql trade-core:/tmp/V116_dryrun.sql
ssh trade-core "psql \$OPENCLAW_PG_URL_DRYRUN -f /tmp/V116_dryrun.sql"
# 預期：Guard A/C NOTICE PASS；0 ERROR

# Step 3 — ⚠️ Idempotency double-apply（re-apply 必 0 ERROR / 0 重複 hypertable / 0 重複 policy / 0 重複 index）
ssh trade-core "psql \$OPENCLAW_PG_URL_DRYRUN -f /tmp/V116_dryrun.sql"
# 預期：第二次仍 PASS；IF NOT EXISTS + if_not_exists=>TRUE 全 fail-safe；Guard C 再次 NOTICE PASS

# Step 4 — schema reflection 驗（5 項）
ssh trade-core "psql \$OPENCLAW_PG_URL_DRYRUN -c \"
  -- 4a decay_signals column 全 land
  SELECT count(*) FROM information_schema.columns WHERE table_schema='learning' AND table_name='decay_signals';
  -- 4b hypertable on observed_at（timestamptz time_interval = 604800）
  SELECT EXTRACT(EPOCH FROM time_interval) FROM timescaledb_information.dimensions
    WHERE hypertable_name='decay_signals' AND column_name='observed_at';
  -- 4c strategy_lifecycle 6-state CHECK
  SELECT pg_get_constraintdef(oid) FROM pg_constraint
    WHERE conrelid='learning.strategy_lifecycle'::regclass AND contype='c'
      AND position('current_state' IN pg_get_constraintdef(oid))>0;
  -- 4d compression + retention 2 jobs
  SELECT proc_name FROM timescaledb_information.jobs WHERE hypertable_name='decay_signals';
  -- 4e indexes
  SELECT indexname FROM pg_indexes WHERE schemaname='learning' AND tablename IN ('decay_signals','strategy_lifecycle');
\""
```

### §7.2 Empirical CHECK reject 驗（single-authority + 6-state hard-lock）

```bash
# decision_authority CHECK 真 reject 非-'M7'（ADR-0044 Decision 1 enforcement）
ssh trade-core "psql \$OPENCLAW_PG_URL_DRYRUN -c \"
  INSERT INTO learning.strategy_lifecycle
    (strategy_id, symbol, current_state, decision_authority, engine_mode)
    VALUES ('grid','BTCUSDT','DECAY_DETECTED','M11','live');\""
# 預期：ERROR — violates check constraint（M11 寫 lifecycle 被擋）

# current_state CHECK 真 reject 第 7 個值
ssh trade-core "psql \$OPENCLAW_PG_URL_DRYRUN -c \"
  INSERT INTO learning.strategy_lifecycle
    (strategy_id, symbol, current_state, engine_mode)
    VALUES ('grid','BTCUSDT','INVALID_STATE','live');\""
# 預期：ERROR — violates check constraint
```

### §7.3 Engine restart 實測（per 2026-05-02 sqlx hash drift 教訓）

```bash
# V116 land + Mac commit + push origin 後
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only && bash helper_scripts/restart_all.sh --rebuild --keep-auth"
# 預期：engine PID 重啟；engine.log 0 sqlx panic；_sqlx_migrations V116 success=t
# 若 checksum drift → helper_scripts/db/repair_migration_checksum（per 2026-05-02 incident SOP）
```

> **memory 紀律重申**：cargo test PASS ≠ runtime sqlx migrate 驗證（2026-05-02 P0 hash drift 教訓）；engine restart 實測是 closure SOP 必含步驟。

---

## §8 Rollback + Reversibility

```sql
-- V116 rollback（Linux PG only；不在 Mac 跑）
SELECT remove_retention_policy('learning.decay_signals', if_exists => TRUE);
SELECT remove_compression_policy('learning.decay_signals', if_exists => TRUE);
DROP TABLE IF EXISTS learning.strategy_lifecycle;
DROP TABLE IF EXISTS learning.decay_signals;
-- 不跨 V107（M11 schema）/ V112（LAL）boundary
```

- **V116 apply 後立即 0 row**：rollback 0 loss（foundation stage）。
- **有 data 後 rollback**：丟 decay signal + lifecycle history；先 export `/tmp/backup_v116_*.csv`。
- **無強 FK cascade**：`m11_replay_divergence_ref` / `triggering_signal_id` / `governance_audit_ref` 皆弱關聯（無 FK constraint），V107/V112 rollback 不 cascade 到 V116。

---

## §9 Acceptance Criteria

| # | Criteria | Test |
|---|---|---|
| AC-1 | Guard A pass：timescaledb extension 在；V107 absent 只 WARN 不 FAIL | §7.1 Step 2 |
| AC-2 | Guard C pass：decay_signals hypertable observed_at **time_interval=604800**（非 integer_interval）；5-source enum；strategy_lifecycle 6-state enum；M7 authority CHECK；compress+retention 2 jobs | §7.1 Step 4 + §4.3 |
| AC-3 | **Idempotency double-apply pass**：re-apply 0 ERROR / 0 重複 hypertable / 0 重複 policy / 0 重複 index | §7.1 Step 3 |
| AC-4 | single-authority empirical：非-'M7' INSERT 被 reject；第 7 個 state 被 reject | §7.2 |
| AC-5 | Engine restart：sqlx V116 success=t + engine.log 0 panic | §7.3 |
| AC-6 | **detector IN transition**：2+ signal → 寫 strategy_lifecycle DECAY_DETECTED + M3 WARN + clock_started/expires 填 + **0 sizing 改動**（驗 live size 表/IPC 無寫） | E1 unit + E4 FSM proptest |
| AC-7 | **deadlock 防護**：DECAY_DETECTED 14d clock 過期 sweep 真跑；AC-1/2/3 語意正確；不存在無 alert/audit 停滯 > 14d 的死狀態 | E2 deadlock scan + E4 dead-state scan |
| AC-8 | **OUT scope 真凍結**：所有 OUT transition（特別 50%-cut enforce）= `unimplemented!()` / feature-off；runtime 被呼即 panic；**grep 證 0 處改 live sizing** | E2 adversarial（50%-cut 真 OUT 確認）+ E4 |
| AC-9 | M1 LAL 未被碰：`lal/mod.rs` diff = 0；`FailClosedDecayProvider` 原樣 | E2 + CC |

---

## §10 副作用清單（PA）

| # | 副作用面 | 評估 |
|---|---|---|
| 1 | 其他模組 import？ | M1 LAL `DecayStateProvider` 是 **未來** consumer（現為 FailClosedProvider stub）；V116 detector **不觸 LAL**。新模組 `learning/decay_detector/` 無既有 importer。 |
| 2 | mock 測試脆弱點 | signal 計算依賴 fills/equity-curve 讀取；E1 須確認 read source（Postgres fills 表 / equity snapshot）的既有 query helper，勿新造 DB 抽象。 |
| 3 | asyncio/threading 邊界 | detector = nightly cron（non hot-path）；不進 tick pipeline；無 async/thread 混用風險（對比 C4 watcher 的 in-band command 複雜度，此處乾淨）。 |
| 4 | API response schema | **無**——detector 不改任何 Control API endpoint；若未來 GUI 要顯 lifecycle state 是另開 read-only endpoint（非本 scope）。 |
| 5 | RustEngine ↔ Python IPC schema | **無**——detector 全 Rust + PG；不新增 IPC message。 |
| 6 | live sizing / trading state | **零**——這是 detector-only 的核心保證；AC-6/AC-8 grep 證明 0 處改 sizing。 |
| 7 | sqlx compile-time 查詢 | 若 detector 用 `sqlx::query!` 宏，須 `cargo sqlx prepare` 更新 `.sqlx/` offline cache（否則 CI 掛）；E1 IMPL 注意。 |

---

## §11 E1 Dispatch §（並行波次 + 文件不重疊）

### §11.1 開頭給 E1 — 該知道的 5 條 + scope 紅線

> 見本回報開頭「E1 該知道的」段（與此處同步）。

### §11.2 波次設計（最大並行，文件互不重疊）

| Wave | Task | Owner | 文件範圍 | 阻塞關係 |
|---|---|---|---|---|
| **W1** | V116 migration SQL（§2/§3/§4 DDL + Guard A/C） | E1-a | `sql/migrations/V116__m7_decay_signals_lifecycle.sql`（新檔） | 無；最先；MIT dry-run 卡 W2 sign-off |
| **W2-1** | 4 signal source 計算 + M11 ingest（§6.2 `DecaySignalSource` impl × 5） | E1-b | `rust/.../learning/decay_detector/signals.rs`（新） | 等 W1 schema land（讀 decay_signals 寫入結構） |
| **W2-2** | FSM 6-enum + IN transition（normal→detected）+ §5 auto-clear（AC-1/2/3）+ OUT `unimplemented!()` | E1-c | `rust/.../learning/decay_detector/fsm.rs`（新） | 等 W1（strategy_lifecycle 結構）；與 W2-1 並行（不同檔） |
| **W2-3** | detector cron orchestration（nightly：算 signal → aggregate → 寫 ledger → FSM evaluate → §5.3 sweep）+ M3 alert emit（WARN / RESOLVE / ESCALATE-PENDING） | E1-d | `rust/.../learning/decay_detector/mod.rs` + scheduler spawn 接點 | 等 W2-1 + W2-2（組裝它們）；**串行於 W2 末** |

> W2-1 / W2-2 可完全並行（signals.rs vs fsm.rs 不同檔）。W2-3 是組裝層，等 W2-1+W2-2。W1 是所有 W2 的 schema 前置。

### §11.3 文件重疊檢查（PA 已驗）

- `learning/decay_detector/` 是**全新目錄**，無既有檔。
- **不碰** `governance/lal/mod.rs`（OUT-6）、不碰任何 already-applied migration（V099-V115）、不碰 tick_pipeline / IPC。
- scheduler spawn 接點（main.rs 或 tasks.rs）= W2-3 唯一觸及既有檔處；E1-d 須 mirror 既有 `spawn_*_scheduler` 範式（如 M3 `spawn_metric_emitter_scheduler` @ main.rs:1555 per PA memory），surgical add 一個 spawn 行。

### §11.4 Role chain（後續）

```
E1 IMPL (W1→W2)  →  MIT V116 Linux-PG dry-run（§7 double-apply mandate）
                 →  E2（adversarial：① 確認 50%-cut 真 OUT/unimplemented ② deadlock scan §5）
                 →  E4（FSM proptest 6-state matrix + dead-state scan AC-7/AC-8）
                 →  CC 16-root（§11.5 + 原則 2/3/4/7 + 硬邊界 0 觸碰）
                 →  PM sign-off
```

### §11.5 E2 必重點審查 3 點（高風險）

1. **50%-cut / 任何 sizing 改動真 OUT**：grep 全 detector module，確認 0 處呼 sizing 寫入 API / 0 處改 live size；`enforce_decay_50pct_sizing` 等 OUT 函數 body 真 `unimplemented!()`（非偷偷半接線）。這是 operator 凍結 autonomy active path #6 的核心紅線。
2. **first-detection deadlock（§5）**：DECAY_DETECTED auto-clear sweep cron 真 spawn + 真掃過期 row；AC-2（clock 過期 + signal 持續）真 emit CRITICAL advisory 而非靜默卡；不存在 `is_none()` guard 導致永久 dormant 的 bb_breakout 重演。
3. **single-authority + M1 LAL 不被碰**：`decision_authority='M7'` CHECK 真擋非-M7 寫入；`lal/mod.rs` diff = 0；detector 寫 lifecycle 走 `current_state` 不污染 decay_signals。

---

## §12 Cross-References

- **ADR-0044**：`docs/adr/0044-m7-decay-enforced-single-authority.md`（Decision 1 single authority / Decision 2 signal / Decision 3 6-state FSM / Decision 5 14d×50% / Decision 6 RETIRED→Tier 0；OUT-2/5/6 對應 frozen 部分）
- **M7 design spec**：`docs/execution_plan/2026-05-21--m7_decay_enforced_design_spec.md`（§2 signal 數學 / §3 FSM transition + dwell / §5 window rationale / §9 反向 attack）
- **V113 placeholder doc（被 V116 取代 + 修正 schema 張力）**：`docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md`（§0.3 標記其 `decay_signals.lifecycle_state` placement 為 cleanup debt）
- **V104 timestamptz Guard C 教訓**：`sql/migrations/V104__supervised_live_audit.sql:387-400`（`time_interval` + EXTRACT EPOCH，非 integer_interval）+ spec `docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md`
- **V107 hypertable 樣板**：`sql/migrations/V107__replay_divergence_log.sql`（forbidden-column Guard A 反模式 + timestamptz Guard C 632-644）
- **M1 LAL DecayStateProvider 契約**：`rust/openclaw_engine/src/governance/lal/mod.rs:179-228`（schema-agnostic trait；未來 wire `strategy_lifecycle.current_state`）+ unimplemented! 範式 line 34
- **first-detection deadlock 教訓**：memory `feedback_first_detection_deadlock_pattern`（bb_breakout FIX-26-DEADLOCK-1）
- **PG dry-run mandate**：memory `feedback_v_migration_pg_dry_run`（double-apply load-bearing gate）
- **autonomy freeze 例外**：operator 2026-05-31 拍板（M7 唯一例外提前 IMPL）

---

## §13 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| PA（本 spec）| DONE | 2026-05-31 | detector-only scope 拍定 + V113 schema 張力收斂（single-authority 分離）+ V116 編號 + V104 timestamptz Guard C 教訓納入 + §5 deadlock 防護 |
| E1 | PENDING | — | W1 SQL → W2 Rust detector（§11 波次） |
| MIT | PENDING | — | V116 Linux PG **double-apply** dry-run（§7 mandate） |
| E2 | PENDING | — | adversarial：50%-cut 真 OUT + deadlock scan（§11.5） |
| E4 | PENDING | — | FSM proptest 6-state + dead-state scan（AC-7/AC-8） |
| CC | PENDING | — | 16-root（原則 2/3/4/7 + 硬邊界 0；§11.5 autonomy path #6 確認凍結） |
| PM | PENDING | — | sign-off closure |

**END V116 M7 decay detector spec — DETECTOR layer only.**
