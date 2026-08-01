---
name: db-schema-design-financial-time-series
description: MIT agent 主用：設計新 ML/trading 表、寫 V### migration、規劃 hypertable/chunk、PG 慢查詢或 migration silent-noop 排查時讀。
allowed-tools: Read, Grep, Glob, Bash
---

# DB Schema Design for Financial Time Series（金融時序 DB schema 手冊）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：TimescaleDB / PG tuning 通識不在本檔重述；本檔只列本專案的 Guard 規範、engine_mode 隔離、教訓與 SSOT 指針。

## 何時觸發

- MIT 收到「新 ML / trading 表設計」「migration V### 寫法」「hypertable / chunk 規劃」「為何 query 慢」
- V023 / V019 / V021 silent-noop 類事件後的 retrofit
- PG 4-8GB memory constraint 下的 query optimization

## ★ 黃金法則

**金融時序資料 ≠ generic OLTP**：per-tick / per-bar / per-fill / per-event 必用 hypertable + time-based partition；strategy config / model registry metadata / symbol whitelist 用 regular table。
**Migration 必含 Guard A/B/C**：silent-noop 失敗 → 下游 writer 假性成功 = 最難 debug 的 bug。

## 1. Hypertable 專案配置

- **OpenClaw 建議起點**（**非治理硬規範**；隨資料量 + query pattern 動態調整）：7 day chunk for 1m data（1m + 5 strat × 25 symbol：每 day ~180k row → 7d chunk ~1.2M row），1 day chunk for tick data
- Compression 必開（PG 4-8GB 下 30d+ 老資料可省 80-90%）：`compress_segmentby = 'symbol, strategy_name'`、`compress_orderby = 'ts DESC'`、`add_compression_policy(…, INTERVAL '30 days')`
- 高量資料（>100M rows / yr）必加 `add_retention_policy(…, INTERVAL '90 days')` 起跳

## 2. Migration Guard 規範（唯一正本）

### Guard A — 表已存在但 schema 不符
```sql
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='learning' AND table_name='X') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_schema='learning' AND table_name='X'
                         AND column_name='required_col') THEN
            RAISE EXCEPTION 'V023 silent-noop: learning.X exists but missing column required_col';
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.X (...);
```

### Guard B — column 型別不符
```sql
DO $$
DECLARE
    col_type text;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema='trading' AND table_name='Y' AND column_name='exit_source';

    IF col_type IS NOT NULL AND col_type != 'character varying' THEN
        RAISE EXCEPTION 'V021 type mismatch: trading.Y.exit_source is % (expected varchar)', col_type;
    END IF;
END $$;

ALTER TABLE trading.Y ADD COLUMN IF NOT EXISTS exit_source VARCHAR(64);
```

### Guard C — 索引選用
```sql
DO $$
DECLARE
    idx_def text;
BEGIN
    SELECT pg_get_indexdef(c.oid) INTO idx_def
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='learning' AND c.relname='X_hot_idx';

    IF idx_def IS NOT NULL AND idx_def NOT LIKE '%(symbol, strategy_name, ts DESC)%' THEN
        RAISE EXCEPTION 'V### index drift: X_hot_idx exists with wrong column order';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS X_hot_idx ON learning.X (symbol, strategy_name, ts DESC);
```

### Idempotency
每個 migration 必須能 run 兩次不出錯（第二次 no-op，Guard 不 RAISE）；第二次 RAISE → migration 寫錯，回 E2 改。

## 3. Hot-path Index（OpenClaw 主要 query pattern）

| Query | Index 必有 |
|---|---|
| edge per (strategy, symbol) last 24h | `(strategy_name, symbol, ts DESC)` |
| recent fills per symbol | `(symbol, ts DESC) WHERE engine_mode IN ('live','live_demo')` partial |
| model registry latest production | `(model_slot, train_date DESC) WHERE canary_status='production'` partial |
| outcome backfill per timeframe | `(timeframe, ts DESC) WHERE outcome_pnl IS NULL` partial |

偏好 partial index（冷資料不索引）；每月 REINDEX hot 表；監控 `pg_stat_user_indexes` idx_scan=0 的 dead index。

## 4. engine_mode 隔離

- 4 值語義：`paper`（純 simulation，PnL 失真，不能進 edge / training）/ `demo`（Bybit demo endpoint，價格真實）/ `live_demo`（Live 管線走 demo endpoint，Live 嚴格標準）/ `live`（真實 Mainnet）
- column 必加：`engine_mode VARCHAR(20) NOT NULL CHECK (engine_mode IN ('paper','demo','live_demo','live'))`
- **OpenClaw 教訓**：歷史 43k 條 `engine_mode='live'` 實為 LiveDemo（memory `project_engine_mode_tag_live_demo`）；ML training filter 必用 `engine_mode IN ('live','live_demo')`，不能 `='live'`；outcome_backfiller fix（commit `5e2981d`）INSERT 時補 engine_mode

## 5. PG 資源 — 必 verify 不信 baseline

> ⚠️ OpenClaw 真實 `postgresql.conf` 未 verified（postgres 跑在 container）。**verify 命令**：
> ```bash
> psql "$DATABASE_URL" -c "SHOW work_mem; SHOW shared_buffers; SHOW max_connections; SHOW effective_cache_size;"
> ```
> 對應不上時以 `postgresql.conf` 為準。tuning 通識（work_mem/shared_buffers 比例、pgbouncer）靠內建知識；4-8GB 約束下大 query 必分批、防多並行 OOM。

## 6. Row 量規劃 — 不在本 skill 寫死

策略激活率 / Phase 階段 / tick density / retention policy 共同決定真實 row 量。**本 skill 不寫死 OpenClaw 表估算**。實際 row 量必跑 `SELECT count(*), max(ts) - min(ts), pg_size_pretty(pg_total_relation_size('learning.X')) FROM learning.X` 取真值。

## 7. 工作流（10 步 schema 審計）

1. table type 判斷（hypertable vs regular）→ 2. chunk_time_interval 對應 row 量級 → 3. engine_mode 字段 + CHECK constraint → 4. Guard A/B/C migration 寫法 → 5. Hot-path index 對應 query pattern → 6. Partial index → 7. Compression policy 30d+ → 8. Retention policy 90d+ → 9. Test idempotency（跑兩次）→ 10. `audit_migrations.py` 驗 V### 序列完整。

## 穩定 schema rule（架構級不變）

silent-noop postmortem 教訓 → 新 migration 必含 Guard A/B/C；engine_mode 4 值 paper/demo/live_demo/live；training filter `IN ('live','live_demo')`（不單 'live'）；schema 變動必同步加 healthcheck `check_X()` function。

## Cross-Skill 互引（避免重述）

- **C1.h pipeline 狀態評級**：本 skill 看 schema 設計；**評級 + 5 階段**走 `ml-pipeline-maturity-audit`
- **feature pipeline / leakage**：走 `feature-engineering-protocol`
- **CV 設計 / sample size**：走 `time-series-cv-protocol`

## 反模式（見即 Reject）

- 沒 hypertable 的 per-tick / per-bar 資料表；用 normal table 存 1m × 25 symbol × 1y 級資料
- `CREATE TABLE IF NOT EXISTS` 沒 Guard A；column 加 `IF NOT EXISTS` 但無 Guard B 驗 type
- 索引 column 順序錯（如 `(ts, symbol)` 但 query filter `WHERE symbol=X`）
- 沒 engine_mode CHECK constraint；沒 compression policy
- migration 不能 idempotent；work_mem 太大導致並行 OOM
- column type 用 `text` 但其實是 enum（用 VARCHAR + CHECK 或真 enum）
- 沒 audit_migrations.py 例行跑

## 輸出格式

```markdown
# MIT DB Schema Audit — <table_or_migration> · <date>

## Schema 設計
| Aspect | 狀態 | 備註 |
| Hypertable / Chunk interval / engine_mode field / Compression / Retention | | |

## Migration Guard 檢查
| Guard | 套用? | 理由 |
| A / B / C / Idempotency | | |

## Hot-path index
| Query pattern | Index 命中? |

## PG 資源評估
預估 row 量 / 1y、chunk count、compressed ratio、index size

## V### 序列完整性
audit_migrations.py 結果

## 結論 + 建議
1. <具體 + 修法>

MIT returns an immutable `role_fragment_v1` with `payload_kind=finding_fragment_v1` for the task closure; no automatic report or memory append.
```
