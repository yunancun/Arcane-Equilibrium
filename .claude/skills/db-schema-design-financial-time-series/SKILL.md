---
name: db-schema-design-financial-time-series
description: 金融時序資料庫 schema 設計 — TimescaleDB hypertable / partition / compression / hot-path index / engine_mode 隔離 / Guard A/B/C migration 規範 / V001-V024 lessons。MIT agent 主用。
allowed-tools: Read, Grep, Glob, Bash
---

# DB Schema Design for Financial Time Series（金融時序 DB schema 手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > `TODO.md` active state / runtime evidence > `README.md` stable surfaces > `CLAUDE.md` operating rules > governance docs > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

## 何時觸發

- MIT 收到「新 ML / trading 表設計」「migration V### 寫法」「hypertable / chunk 規劃」「為何 query 慢」
- V023 / V019 / V021 silent-noop 類事件後的 retrofit
- PG 4-8GB memory constraint 下的 query optimization
- TimescaleDB / Postgres 邊界決定

## ★ 黃金法則

**金融時序資料 ≠ generic OLTP**：必用 hypertable + time-based partition。
**Migration 必含 Guard A/B/C**：silent-noop 失敗 → 下游 writer 假性成功 = 最難 debug 的 bug。
**schema 設計時就要預留 OpenClaw 5 strat × 25 symbol × 1m row 量級**。

## 1. TimescaleDB Hypertable

### 1.1 何時用 hypertable
| 場景 | 用 hypertable | 不用 |
|---|---|---|
| Per-tick / per-bar 資料 | ✅ | |
| Per-trade fills | ✅ | |
| Per-event audit log | ✅ | |
| Strategy config / parameters | | ✅ regular table |
| Model registry metadata | | ✅ regular table |
| Symbol whitelist | | ✅ regular table |

### 1.2 Chunk 設計
```sql
SELECT create_hypertable('learning.exit_features', 'ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);
```

**chunk_time_interval 選擇**：
- 1m timeframe + 5 strat × 25 symbol：每 day ~180k row → 7d chunk ~1.2M row（合適）
- 過小 → 太多 chunk，metadata overhead
- 過大 → query 慢、compression 效果差

**OpenClaw 建議起點**（**非治理硬規範**；具體 chunk size 隨資料量 + query pattern 動態調整，新表設計可由 MIT 提替代）：7 day chunk for 1m data，1 day chunk for tick data。

### 1.3 Compression
```sql
ALTER TABLE learning.exit_features SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, strategy_name',
    timescaledb.compress_orderby = 'ts DESC'
);

SELECT add_compression_policy('learning.exit_features', INTERVAL '30 days');
```

PG 4-8GB memory 下 compression 必開 — 30d+ 老資料壓縮可省 80-90%。

## 2. Migration Guard 規範

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

## 3. Idempotency

每個 migration 必須能 run 兩次不出錯：
```bash
psql -d test_db -f V###__name.sql   # first run, creates
psql -d test_db -f V###__name.sql   # second run, no-op (Guard 不 RAISE)
```

如第二次 RAISE → migration 寫錯，回 E2 改。

## 4. Hot-path Index 設計

### 4.1 OpenClaw 主要 query pattern
| Query | Index 必有 |
|---|---|
| edge per (strategy, symbol) last 24h | `(strategy_name, symbol, ts DESC)` |
| recent fills per symbol | `(symbol, ts DESC) WHERE engine_mode IN ('live','live_demo')` partial |
| model registry latest production | `(model_slot, train_date DESC) WHERE canary_status='production'` partial |
| outcome backfill per timeframe | `(timeframe, ts DESC) WHERE outcome_pnl IS NULL` partial |

### 4.2 Partial index 偏好
冷資料不索引 → 索引大小 ↓ → query 快：
```sql
-- 只索引 live + live_demo（paper 不查）
CREATE INDEX fills_live_idx ON trading.fills (symbol, ts DESC)
WHERE engine_mode IN ('live', 'live_demo');
```

### 4.3 Avoid index bloat
- 每月 `REINDEX` hot 表
- 監控 `pg_stat_user_indexes` idx_scan 為 0 的索引（dead）

## 5. engine_mode 隔離

### 5.1 為何重要
- `paper`：純 simulation，價格不真實，PnL 失真 → 不能進 edge / training
- `demo`：Bybit demo endpoint，價格真實，但帳戶 demo
- `live_demo`：Live 管線走 demo endpoint（authorization/TTL/風控按 Live 嚴格）
- `live`：真實 Mainnet

### 5.2 column 必加
```sql
CREATE TABLE learning.X (
    ...
    engine_mode VARCHAR(20) NOT NULL CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    ...
);
```

### 5.3 OpenClaw 教訓
- 歷史 43k 條 `engine_mode='live'` 實為 LiveDemo（memory `project_engine_mode_tag_live_demo`）
- ML training filter 必用 `engine_mode IN ('live','live_demo')`，不能 `='live'`
- outcome_backfiller fix（commit `5e2981d`）：INSERT 時補 engine_mode 字段

## 6. PG 4-8GB Memory 限制下的優化

> ⚠️ **本段數值為 typical baseline，OpenClaw 真實 `postgresql.conf` 未 verified**（postgres 跑在 container，host sudo 找不到 postgres user）。**真實 verify 命令**：
> ```bash
> # 用 OpenClaw PG credential 連線 (找 settings/.env 或 env var)
> psql "$DATABASE_URL" -c "SHOW work_mem; SHOW shared_buffers; SHOW max_connections; SHOW effective_cache_size;"
> ```
> 對應不上時以 `postgresql.conf` 為準，**不信本段建議值**。

### 6.1 work_mem 設定（typical baseline）
- query planner 用的 sort / hash 記憶體
- OpenClaw PG 4-8GB → work_mem 建議 32-64MB（per query）
- 太大 → 多並行 query 時 OOM

### 6.2 shared_buffers（typical baseline）
- 25% of 4-8GB = 1-2GB
- 不要超 25%（OS file cache 也要空間）

### 6.3 Connection pooling
- pgbouncer 必開（OpenClaw 多 worker）
- max_connections 50 內（待 verify）

### 6.4 Hypertable 自動 chunk drop
```sql
SELECT add_retention_policy('learning.tick_data', INTERVAL '90 days');
```
保留 90d，老資料自動 drop（節省空間 + 加速 query）。

## 7. Row 量規劃 — 不在本 skill 寫死

策略激活率 / Phase 階段 / tick density / retention policy 共同決定真實 row 量。**本 skill 不寫死 OpenClaw 表估算**避免 sub-agent 引過期值決定 hypertable / chunk / index 規模。

實際 row 量必跑 `SELECT count(*), max(ts) - min(ts), pg_size_pretty(pg_total_relation_size('learning.X')) FROM learning.X` 取真值。

**通用規劃 framework**（不會 drift）：per-tick / per-bar / per-fill / per-event audit log → hypertable + 7d chunk（1m data）/ 1d chunk（tick data）；per-symbol / per-strategy 配置 / metadata → regular table；高量資料（>100M rows / yr）必加 retention policy（90d 起跳）+ compression 30d+。

## 8. 工作流（10 步 schema 審計）

1. **table type 判斷**（hypertable vs regular）
2. **chunk_time_interval 設定** 對應 row 量級
3. **engine_mode 字段 + CHECK constraint**
4. **Guard A/B/C migration 寫法**
5. **Hot-path index** 對應主要 query pattern
6. **Partial index** for filter 條件穩定的場景
7. **Compression policy** 老資料 30d+
8. **Retention policy** 高量資料 90d+
9. **Test idempotency**（migration 跑兩次）
10. **audit_migrations.py** 驗 V### 序列完整

## OpenClaw context — 不在本 skill 重述

OpenClaw 特定 snapshot（具體 V### migration 編號 / commit hash / RAM 配比 / 當前 healthcheck check 數）會 drift。本 skill 不重述。

實際 context 必從 SSOT 拿（衝突信前者）：runtime TOML > Rust schema > `TODO.md` active state / runtime evidence > `CLAUDE.md` hard boundaries / operating rules > `audit_migrations.py` 實測 > git log > memory（operator 明示未必可信）。

**穩定不變的 schema rule**（架構級不變）：silent-noop postmortem 教訓 → 新 migration 必含 Guard A/B/C；engine_mode 4 值 paper/demo/live_demo/live；training filter `IN ('live','live_demo')`（不單 'live'）；schema 變動必同步加 healthcheck `check_X()` function。

## Cross-Skill 互引（避免重述）

- **C1.h ml-pipeline maturity / writer / consumer / decision-impact 4 維度**：本 skill 看 schema 設計（hypertable / partition / Guard）；**pipeline 狀態評級** + **stage（Foundation/Skeleton/Shadow/Canary/Production）** 走 `ml-pipeline-maturity-audit`
- **feature pipeline / leakage**：feature column 設計後的 leakage 偵測（look-ahead / target / survivorship 6 類）走 `feature-engineering-protocol`
- **CV 設計 / sample size**：對 hypertable 跑 ML 訓練的 train/test split 設計走 `time-series-cv-protocol`

## 反模式（見即 Reject）

- 沒 hypertable 的 per-tick / per-bar 資料表
- `CREATE TABLE IF NOT EXISTS` 沒 Guard A
- column 加 `IF NOT EXISTS` 但無 Guard B 驗 type
- 索引含 column 順序錯（如 `(ts, symbol)` 但 query filter `WHERE symbol=X`）
- 沒 engine_mode CHECK constraint
- 沒 compression policy（老資料浪費空間）
- migration 不能 idempotent
- work_mem 太大導致並行 OOM
- 用 normal table 存 1m × 25 symbol × 1y 級資料
- column type 用 `text` 但其實是 enum（用 VARCHAR + CHECK 或真 enum）
- 沒 audit_migrations.py 例行跑

## 輸出格式

```markdown
# MIT DB Schema Audit — <table_or_migration> · <date>

## Schema 設計
| Aspect | 狀態 | 備註 |
| Hypertable | | |
| Chunk interval | | |
| engine_mode field | | |
| Compression | | |
| Retention | | |

## Migration Guard 檢查
| Guard | 套用? | 理由 |
| A | | |
| B | | |
| C | | |
| Idempotency | | |

## Hot-path index
| Query pattern | Index 命中? |

## PG 資源評估
- 預估 row 量 / 1y
- chunk count
- compressed ratio
- index size

## V### 序列完整性
audit_migrations.py 結果

## 結論 + 建議
1. <具體 + 修法>

MIT AUDIT DONE: <report_path>
```
