---
spec: Sprint 1A-ζ Phase 0 — Sandbox + Vault Prep Checklist
date: 2026-05-21
author: PA (Project Architect)；Phase 1 PA refine deliverable (P-5/P-6 patches close)
phase: Sprint 1A-ζ Phase 0（IMPL Spike 前置；wall-clock 0.5 day / 4-6 hr E3 + AI-E sequential）
status: SPEC-DRAFT-V0（待 PM 派 E3 + AI-E sequential；本 Phase 1 land 即進 Phase 0 dispatch）
parent specs:
  - srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md §6.1 Phase 0 + §7.2 sandbox DB + §12 operator Q1d/Q2 sign-off
  - srv/docs/execution_plan/2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md §10 5-Q reflection SOP
  - srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md §1 PG connection range
  - srv/docs/adr/0034-decision-lease-layered-approval-lal.md Decision 4 (Console toggle TOTP) + Decision 6 (LAL Tier 0 RETIRED blocker)
  - srv/docs/agents/context-loading.md §PG Connection Examples (Linux runtime authoritative)
scope: sandbox DB creation + role + extension + V096 catch-up + Vault TOTP secret + sample fills seed；非 IMPL；非 commit；非 派下游 sub-agent；非 production DB 改動
non-scope:
  - V099-V116 任何 V### 在 sandbox 跑（Phase 2 E1 工作）
  - Rust skeleton / Python skeleton（Phase 2 E1 工作）
  - GUI / Console patch（per Q1d operator decision — sandbox 隔絕 Console，0 GUI work）
  - Production DB schema 改動（spike 物理隔絕 production；per Q2 operator decision）
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# Sprint 1A-ζ Phase 0 — Sandbox + Vault Prep Checklist

## §1 Phase 0 Scope

Phase 0 是 Sprint 1A-ζ IMPL Spike 前置 0.5 day 工作窗口；必須在 Phase 1 PA refine 之後 + Phase 2 E1 IMPL 派發之前完成。

Phase 0 三個 deliverable：

1. **sandbox DB** `trading_ai_sandbox` 在 Linux `trade-core` 創建 + role + TimescaleDB extension + V096 baseline catch-up（per operator Q1d + Q2 sign-off：「sandbox DB 隔絕 production」+「sandbox CI + 0 production restart」）
2. **Vault TOTP secret** 生成 + 存於 `$OPENCLAW_SECRETS_DIR/vault/totp_2fa_sandbox.json`（per ADR-0034 Decision 4 + 6 — LAL Tier 0 fill query path / LAL Tier 1+ Console toggle auth 都需 TOTP 認證；spike Track A Tier 0/1 transition test 需 mock TOTP）
3. **Sample fills fixture** seed `trading.fills` 100-500 rows（per Track C C4 fill_chain detector empirical 需 5+ rows 跨 1 strategy × 1 symbol × 1 day window 真實 query）

Phase 0 owner：**E3（DB + extension + role + V096 catch-up）+ AI-E（TOTP secret 生成）+ MIT（sample fills fixture）**

Phase 0 工時：**4-6 hr E3 + AI-E + MIT 串行 / wall-clock 0.5 day**

---

## §2 E3 Task — sandbox DB `trading_ai_sandbox` 創建 (2-3 hr)

### 2.1 連線參考

per `2026-05-21--v103_v104_linux_pg_dry_run.md` §1 + `docs/agents/context-loading.md` §PG Connection Examples：

```bash
# production DB（已存在；spike 不動）：
psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai

# sandbox DB（本 Phase 0 創建）：
psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai_sandbox
```

### 2.2 SQL 步驟（E3 在 `trade-core` 跑）

```sql
-- Step 1: 確認 trading_admin 有 CREATEDB privilege
SELECT usecreatedb FROM pg_user WHERE usename = 'trading_admin';
-- expect: t

-- Step 2: 創 sandbox DB（template=template0 避帶 production collation/data；OWNER=trading_admin）
CREATE DATABASE trading_ai_sandbox
  OWNER trading_admin
  TEMPLATE template0
  ENCODING 'UTF8'
  LC_COLLATE 'en_US.UTF-8'
  LC_CTYPE 'en_US.UTF-8'
  CONNECTION LIMIT -1;

-- Step 3: 創 sandbox role（與 production trading_admin 隔絕）；E3 自決 password；
-- 後續 ALL sandbox 連線必走此 role；spike 結束 DROP ROLE
CREATE ROLE sandbox_admin LOGIN PASSWORD '<E3-decide>' VALID UNTIL 'now() + interval ''14 days''';
GRANT ALL PRIVILEGES ON DATABASE trading_ai_sandbox TO sandbox_admin;

-- Step 4: 切到 sandbox DB；裝 TimescaleDB extension（同 production V096 baseline）
\c trading_ai_sandbox
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Step 5: catch-up baseline schema (V001-V096) — 直接 dump 同步 production schema-only
-- 注意：schema-only；不帶 production fills/decisions/strategy_lifecycle data
```

### 2.3 V096 baseline catch-up（schema-only dump）

```bash
# 在 trade-core 跑：
ssh trade-core "pg_dump -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
  --schema-only \
  --no-owner \
  --no-privileges \
  --schema=trading \
  --schema=learning \
  --schema=governance \
  --schema=market \
  > /tmp/sandbox_baseline_v096.sql"

# 對 sandbox DB apply baseline
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U sandbox_admin -d trading_ai_sandbox \
  -f /tmp/sandbox_baseline_v096.sql"

# 驗 baseline 同 production V096
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U sandbox_admin -d trading_ai_sandbox \
  -c 'SELECT MAX(version) FROM _sqlx_migrations;'"
# expect: 96
```

### 2.4 `~/.pgpass` 更新（E3）

`~/.pgpass` 加一行 sandbox role 認證：

```
127.0.0.1:5432:trading_ai_sandbox:sandbox_admin:<E3-decide>
```

`chmod 600 ~/.pgpass` 確認權限。

### 2.5 E3 sign-off 證據（Phase 0 §6 GO 前）

```bash
# E1 接手前 E3 在 sandbox prep report 留：
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U sandbox_admin -d trading_ai_sandbox -c '
  SELECT current_database(), current_user, version();
  SELECT MAX(version) FROM _sqlx_migrations;
  SELECT extname, extversion FROM pg_extension WHERE extname = ''timescaledb'';
'"
# 預期：trading_ai_sandbox / sandbox_admin / PostgreSQL 14+ TimescaleDB / max version=96 / timescaledb 2.x
```

---

## §3 AI-E Task — Vault TOTP Secret Setup (1-2 hr)

### 3.1 為什麼需要 sandbox TOTP

per ADR-0034 Decision 4 + 6：
- LAL Tier 1 Auto-Approve On 切換 = Operator role + 2FA TOTP confirm
- LAL Tier 0 fill query path 接 V113 RETIRED blocker = 需 cross-module audit trail（含 TOTP-signed operator signature）

spike Track A A3 (M1 LAL state machine Rust skeleton) + A5 (Tier 0→1 transition test) **不能用 production TOTP**（會污染 audit log + 暴露 production credentials）；必須有 **sandbox-only** TOTP secret，物理隔絕。

### 3.2 Secret 存儲路徑

per CLAUDE.md §四 Hard Boundaries：「signed live authorization 必須走 approved Python renew/approve path」+ ADR-0040 line 81：`$OPENCLAW_SECRETS_DIR/external/<vendor>/api_key`。

sandbox TOTP secret 存：

```
$OPENCLAW_SECRETS_DIR/vault/totp_2fa_sandbox.json
```

`OPENCLAW_SECRETS_DIR` 預設 `/etc/openclaw/secrets`（Linux）；Mac 開發目標走 `~/Library/Application Support/openclaw/secrets`（per `feedback_cross_platform` no-hardcode 原則）。

### 3.3 Secret JSON schema

```json
{
  "schema_version": "1.0",
  "env": "sandbox",
  "issued_at": "2026-05-21T00:00:00Z",
  "expires_at": "2026-06-04T00:00:00Z",
  "totp_seed_b32": "<32-char base32 random; AI-E uses python-pyotp generate>",
  "totp_digits": 6,
  "totp_interval_sec": 30,
  "totp_algorithm": "SHA1",
  "rotation_policy": "14d_sandbox_only;rotation = spike closure trigger DROP",
  "scope": ["lal_tier_1_console_toggle_test", "lal_tier_0_fill_query_audit_log"],
  "fingerprint": "<SHA256 of totp_seed_b32>"
}
```

### 3.4 AI-E 生成步驟

```bash
# AI-E 在 trade-core 跑（避把 secret 帶過 SSH 明文 channel）：
ssh trade-core "python3 -c '
import pyotp, json, hashlib, datetime
seed = pyotp.random_base32()
fingerprint = hashlib.sha256(seed.encode()).hexdigest()
data = {
  \"schema_version\": \"1.0\",
  \"env\": \"sandbox\",
  \"issued_at\": datetime.datetime.utcnow().isoformat() + \"Z\",
  \"expires_at\": (datetime.datetime.utcnow() + datetime.timedelta(days=14)).isoformat() + \"Z\",
  \"totp_seed_b32\": seed,
  \"totp_digits\": 6,
  \"totp_interval_sec\": 30,
  \"totp_algorithm\": \"SHA1\",
  \"rotation_policy\": \"14d_sandbox_only;rotation = spike closure trigger DROP\",
  \"scope\": [\"lal_tier_1_console_toggle_test\", \"lal_tier_0_fill_query_audit_log\"],
  \"fingerprint\": fingerprint
}
print(json.dumps(data, indent=2))
' > \$OPENCLAW_SECRETS_DIR/vault/totp_2fa_sandbox.json"

# 權限收緊（避 0644 default）
ssh trade-core "chmod 600 \$OPENCLAW_SECRETS_DIR/vault/totp_2fa_sandbox.json"

# 驗
ssh trade-core "ls -la \$OPENCLAW_SECRETS_DIR/vault/totp_2fa_sandbox.json"
# expect: -rw------- 1 <user> <group> ~600 bytes
```

### 3.5 Rotation Policy

- **expires_at 14d** — spike wall-clock max 2 week；過期自動失效（避遺忘）
- **spike closure trigger DROP** — Phase 3e PM sign-off 後 AI-E 必 `rm $OPENCLAW_SECRETS_DIR/vault/totp_2fa_sandbox.json` + 寫 audit log
- **fingerprint mirror** — sandbox prep report 必含 fingerprint hash（避 spike 跑期間 mid-track 換 secret 偷渡）
- **scope hardcap** — 兩 scope only（LAL 1 toggle test / LAL 0 audit log）；其他用途必走 production TOTP（spike Track A 物理上不可能用 LAL 2/3/4 — Tier 2-4 stub `unimplemented!()`）

### 3.6 AI-E sign-off 證據（Phase 0 §6 GO 前）

```bash
ssh trade-core "python3 -c '
import json
data = json.load(open(\"\$OPENCLAW_SECRETS_DIR/vault/totp_2fa_sandbox.json\"))
print(\"schema_version:\", data[\"schema_version\"])
print(\"env:\", data[\"env\"])
print(\"expires_at:\", data[\"expires_at\"])
print(\"fingerprint:\", data[\"fingerprint\"])
print(\"scope:\", data[\"scope\"])
'"
# 預期：schema_version 1.0 / env sandbox / expires_at 14d / fingerprint hex64 / scope 2 entries
```

---

## §4 E3 + MIT Task — Sample fills fixture seed (1-2 hr)

### 4.1 為什麼需要

per Track C C4 (fill_chain count delta divergence detector) + Q4a override：M11 Python skeleton **+ 1 種 divergence type fill_chain detector empirical**；需要 sandbox `trading.fills` 表 100-500 rows 真實 query。

production fills 表是真實 trading data；spike 不能跨 DB query；必須在 sandbox seed fake fills。

### 4.2 Seed scope（最小化避過度設計）

| 維度 | scope |
|---|---|
| strategy_name | 1 個（`bb_breakout` — 因 production 已有 stable signal source） |
| symbol | 1 個（`BTCUSDT` — 因 production 對賬已驗） |
| 時間範圍 | 1 day（2026-05-15 00:00 UTC – 2026-05-15 23:59 UTC） |
| row count | 100-500 rows（per Track C empirical 需 fill_chain count > 5 觸發 D1 divergence type）|
| engine_mode | `'live_demo'`（spike 不測 paper / 不測 live；對齊 production engine_mode CHECK 5 值）|
| 結果分布 | 50% win / 50% loss（無 P0-EDGE-1 噪音）；P&L 範圍 [-50, +50] USDT |

### 4.3 Seed SQL（E3 + MIT 共同設計；E3 跑）

```sql
-- 在 sandbox DB 跑（trading_ai_sandbox）
-- prerequisite: V001-V096 baseline 已 catch-up (per §2.3)
INSERT INTO trading.fills (
  ts, fill_id, order_id, symbol, side, qty, price, fee, fee_currency,
  realized_pnl, is_paper, strategy_name, context_id, engine_mode, ...
) SELECT
  '2026-05-15 00:00:00 UTC'::timestamptz + (random() * interval '24 hours'),
  gen_random_uuid()::text,
  'spike_order_' || generate_series(1, 200)::text,
  'BTCUSDT',
  CASE WHEN random() > 0.5 THEN 'Buy' ELSE 'Sell' END,
  (random() * 0.1 + 0.001)::numeric(10,8),
  (60000 + random() * 5000)::numeric(20,8),
  (random() * 0.5)::numeric(10,8),
  'USDT',
  ((random() - 0.5) * 100)::numeric(20,8),
  false,
  'bb_breakout',
  'spike_context_' || generate_series(1, 200)::text,
  'live_demo',
  ...
FROM generate_series(1, 200);

-- 驗 row count
SELECT COUNT(*), MIN(ts), MAX(ts), strategy_name, engine_mode
FROM trading.fills
WHERE strategy_name = 'bb_breakout' AND symbol = 'BTCUSDT'
GROUP BY strategy_name, engine_mode;
-- expect: 200 rows / ts span ~24h / 'bb_breakout' / 'live_demo'
```

### 4.4 MIT sign-off 證據

```bash
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U sandbox_admin -d trading_ai_sandbox -c '
  SELECT COUNT(*) AS total_fills,
         MIN(ts) AS earliest,
         MAX(ts) AS latest,
         SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) AS wins,
         SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) AS losses,
         AVG(realized_pnl)::numeric(10,4) AS avg_pnl
  FROM trading.fills
  WHERE strategy_name = ''bb_breakout'' AND symbol = ''BTCUSDT'' AND engine_mode = ''live_demo'';
'"
# 預期：total ∈ [100, 500] / win-loss ratio ≈ 1:1 / avg_pnl ≈ 0 ± 5 USDT
```

---

## §5 Verify SQL — 5 Reflection per V099_V116 SOP §10 Q1-Q5

per `2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md` §4.1-4.12 pattern；本 Phase 0 在 sandbox DB 跑 5 reflection 確認 sandbox baseline 完整：

```sql
-- Q1: TimescaleDB extension version (sandbox vs production must align)
SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';
-- expect: timescaledb 2.x (與 production V096 baseline 對齊)

-- Q2: _sqlx_migrations head + 最近 5 條 (確認 V096 catch-up 完整)
SELECT version, success, installed_on
FROM _sqlx_migrations
ORDER BY version DESC
LIMIT 5;
-- expect: head = 96 / 全 success = t

-- Q3: trading.fills column inventory (確認 baseline schema 全 27 col 帶過來)
SELECT COUNT(*) AS col_count, ARRAY_AGG(column_name ORDER BY ordinal_position) AS cols
FROM information_schema.columns
WHERE table_schema = 'trading' AND table_name = 'fills';
-- expect: col_count = 27 (per v103_v104_linux_pg_dry_run §3 production baseline)

-- Q4: schema 列表 (trading / learning / governance / market 4 schema 全在)
SELECT schema_name FROM information_schema.schemata
WHERE schema_name IN ('trading', 'learning', 'governance', 'market')
ORDER BY schema_name;
-- expect: 4 rows / governance / learning / market / trading

-- Q5: hypertable count (TimescaleDB hypertable 帶過來，避只是 plain table)
SELECT hypertable_schema, hypertable_name FROM timescaledb_information.hypertables
ORDER BY hypertable_schema, hypertable_name;
-- expect: production V096 baseline 已有 N hypertable（per production state；E3 對比 production 跑同 query 確認 row count 一致）
```

---

## §6 Phase 0 GO Criteria — 6 Confirm 全 PASS

進入 Phase 2 E1 IMPL Dispatch 前，PA + PM 必須親手驗以下 6 項全 PASS：

| # | Confirm | Owner | Evidence |
|---|---|---|---|
| C1 | sandbox DB `trading_ai_sandbox` 存在 + 連線可進 | E3 | `psql -h 127.0.0.1 -U sandbox_admin -d trading_ai_sandbox -c "SELECT current_database();"` returns `trading_ai_sandbox` |
| C2 | TimescaleDB extension 已裝 + 版本對齊 production | E3 | `SELECT extversion FROM pg_extension WHERE extname='timescaledb'` 與 production 同 |
| C3 | V001-V096 baseline schema catch-up 完整 | E3 | `_sqlx_migrations` max version = 96 + 5 Q reflection 全 PASS |
| C4 | TOTP secret `$OPENCLAW_SECRETS_DIR/vault/totp_2fa_sandbox.json` 存在 + 14d 有效期 + fingerprint hex64 | AI-E | `ls -la` + `jq .fingerprint .expires_at` 驗 |
| C5 | Sample fills 100-500 rows 在 `trading_ai_sandbox.trading.fills` (strategy_name='bb_breakout', symbol='BTCUSDT', engine_mode='live_demo') | E3 + MIT | `SELECT COUNT(*)` returns ∈ [100, 500] |
| C6 | `~/.pgpass` 含 sandbox role 一行 + chmod 600 | E3 | `grep -c trading_ai_sandbox ~/.pgpass` = 1 + `ls -la ~/.pgpass` shows -rw------- |

**全 PASS** = Phase 0 closure；PA 寫 sandbox prep report；PM 派 Phase 2 E1 sub-agent dispatch（per Sprint 1A-ζ spec §6.1 dispatch 順序）

**任一 FAIL** = Phase 0 BLOCKED；走 §7 fallback

---

## §7 Fallback — Sandbox DB 不可建 / Vault 不可注 secret

### 7.1 fallback Trigger

| Trigger | Severity |
|---|---|
| `CREATE DATABASE trading_ai_sandbox` permission denied | BLOCKER |
| `CREATE EXTENSION timescaledb` 失敗 | BLOCKER |
| V001-V096 baseline dump apply 失敗（schema 不對齊） | BLOCKER |
| `$OPENCLAW_SECRETS_DIR` 寫不進去 | BLOCKER |
| `pyotp` Python library 不可裝 | BLOCKER（or AI-E manual base32 + HMAC-SHA1 generate） |

### 7.2 Operator Decision Routing

Phase 0 BLOCKER 觸發 → PA 升 BLOCKER + operator decision 三選一：

| 選項 | 描述 | trade-off |
|---|---|---|
| **(a) 取消 Sprint 1A-ζ spike** | spec doc land 但 IMPL 不跑；wall-clock 不延；Sprint 4 first Live IMPL 仍走 design-only baseline | Sprint 4 IMPL 風險仍存；P0 sqlx hash drift incident 教訓未補；不推薦 |
| **(b) 採 production PG with audit log + 嚴格 cleanup script** | spike Track A/B/C 直接 apply V112/V106/V107 在 production DB；spike 結束跑 `DROP TABLE` rollback；audit log 標 `spike=true` 全程留證 | 違反 Q1d/Q2 operator sign-off「sandbox 隔絕 production」；engine restart 真實觸發；P0 incident 重蹈風險；**強烈不推薦** |
| **(c) defer Sprint 1A-ζ + 先做 sandbox infra 升級** | E3 跑 sandbox infra IMPL（PG cluster / role policy / secret vault）；wall-clock +1 week；spike 延後 | wall-clock 延；但治理穩定；推薦若 (a) (b) 兩者都不可接 |

### 7.3 PA 推薦 fallback 預設

- 若 Phase 0 fail = permission/extension 級 = **(c) defer + 補 sandbox infra**（治理優先）
- 若 Phase 0 fail = pyotp lib only = **AI-E manual base32 + HMAC-SHA1** 替代（10 min fix；不升 BLOCKER）

---

## §8 Phase 0 → Phase 1 → Phase 2 Sign-off Chain

```
Phase 0 sandbox + Vault prep (本 spec)
  │ E3 + AI-E + MIT 串行 4-6 hr
  │ §6 6 confirm 全 PASS
  ↓
Phase 1 PA refine + 3 dispatch packet (本 spike spec §3.1 Phase 1)
  │ PA single-thread 4-6 hr
  │ 3 E1 dispatch packet land
  ↓
Phase 2 E1 IMPL × 3 track (本 spike spec §3.2 Phase 2)
  │ E1 × 3 sequential V### apply (V107 → V113 → V112 → V106) + 3 並行 Rust skeleton
  │ 35-55 hr / wall-clock 3-4 day
  ↓
Phase 3a-e closure (本 spike spec §3.3)
```

Phase 0 sign-off owner：**E3 (DB) + AI-E (TOTP) + MIT (fills seed)** 三方協同 + PA 收尾 sandbox prep report；PM 親手 verdict GO/BLOCK Phase 2 dispatch。

---

## §9 Cross-Reference

- Sprint 1A-ζ spike spec：`/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md`
- 3 E1 dispatch packet：`/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_3_e1_dispatch_packet.md`
- V099-V116 SOP：`/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md`
- V103/V104 PG dry-run 範式：`/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md`
- ADR-0034 Decision 4 (Console toggle TOTP) + Decision 6 (LAL Tier 0 RETIRED blocker)
- CLAUDE.md §四 Hard Boundaries / §六 Mac=Dev / Linux=Runtime / §Data Migrations And Validation

---

**END Sprint 1A-ζ Phase 0 — Sandbox + Vault Prep Checklist**
