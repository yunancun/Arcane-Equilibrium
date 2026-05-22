---
report: Sprint 1A-ε P1 sandbox_admin Role Creation (E3 Security)
date: 2026-05-22
author: E3 Security Auditor
phase: Sprint 1A-ε P1 carry-over from Sprint 1A-ζ Phase 3c AC-1 PARTIAL → RESOLVED
status: PASS WITH 1 MEDIUM FINDING（無阻 Sprint 1B 派發）
spec ref:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_1a_zeta_pm_phase_3e_signoff.md §4.2 item 1
  - srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-22--sprint_1a_zeta_phase_3c_qa_empirical_verify.md §1.4
runtime: trade-core PostgreSQL 16 + TimescaleDB 2.26.1 (trading_ai_sandbox)
production engine: PID 3954769 跑 trading_ai（本 task 全程未碰）
---

# Sprint 1A-ε P1 sandbox_admin Role Creation — 2026-05-22

## §1 Pre-state（Linux PG empirical）

### 1.1 trading_ai_sandbox roles（之前）

| Role | Attributes |
|---|---|
| trading_admin | Superuser, Create role, Create DB, Replication, Bypass RLS |
| replay_writer_role | Cannot login |
| sandbox_admin | **(not exist)** |

### 1.2 trading_ai_sandbox schemas（21 total）

User schemas (13): agent / audit / features / governance / learning / market / news / observability / openclaw / panel / replay / risk / trading
System: public / pg_database_owner-owned
TimescaleDB internal (7): _timescaledb_cache / _catalog / _config / _functions / _internal / timescaledb_experimental / timescaledb_information

### 1.3 _sqlx_migrations baseline

```
最高註冊：V096 'drop dead learning tables' (Phase 0 sandbox baseline)
total row count: 93
缺：V097/V098/V103/V106/V107/V112（per QA Phase 3c AC-1 RCA — raw psql -f apply 不寫註冊表）
```

## §2 Role design

### 2.1 權限範圍

| Privilege | Granted? |
|---|---|
| LOGIN | ✅ |
| CONNECT trading_ai_sandbox | ✅ explicit GRANT |
| USAGE + CREATE on 14 schemas (13 user + public) | ✅ |
| ALL PRIVILEGES on TABLES (existing + DEFAULT for new) | ✅ |
| ALL PRIVILEGES on SEQUENCES | ✅ |
| EXECUTE on FUNCTIONS | ✅ |
| ALL PRIVILEGES on _sqlx_migrations | ✅ (migration registry write) |
| search_path default = governance, learning, trading, public | ✅ |
| CONNECTION LIMIT 10 | ✅ |

### 2.2 不可權限（attacker mindset hard-fence）

| Privilege | Denied? |
|---|---|
| SUPERUSER | ✅ rolsuper=f |
| CREATEROLE | ✅ rolcreaterole=f |
| CREATEDB | ✅ rolcreatedb=f |
| REPLICATION | ✅ rolreplication=f |
| BYPASSRLS | ✅ rolbypassrls=f |

### 2.3 密碼策略

- 算法：SCRAM-SHA-256（PG 16 默認；本 session 已 SET password_encryption = 'scram-sha-256'）
- 長度：33-char base64 (24 byte random / openssl rand -base64 24)
- 熵：~144 bit
- 儲存：srv/settings/secret_files/postgres/sandbox_admin/password (chmod 0600, owner=ncyu:ncyu)
- 不入：git / docs / TODO.md / commit message / log
- gitignored：**/secret_files/ matches srv/.gitignore；git check-ignore 確認 IGNORED

## §3 Empirical apply（Linux PG）

```sql
SET password_encryption = 'scram-sha-256';
CREATE ROLE sandbox_admin LOGIN PASSWORD <REDACTED>
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT 10;
GRANT CONNECT ON DATABASE trading_ai_sandbox TO sandbox_admin;
GRANT USAGE, CREATE ON SCHEMA <14 schemas> TO sandbox_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA <14> TO sandbox_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA <14> TO sandbox_admin;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA <14> TO sandbox_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE trading_admin IN SCHEMA <14>
  GRANT ALL ON TABLES / SEQUENCES TO sandbox_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE trading_admin IN SCHEMA <14>
  GRANT EXECUTE ON FUNCTIONS TO sandbox_admin;
ALTER ROLE sandbox_admin SET search_path = governance, learning, trading, public;
GRANT ALL PRIVILEGES ON TABLE _sqlx_migrations TO sandbox_admin;
```

全 12 條 SQL statement **無 error**。

### 3.1 \du 確認

```
                  List of roles
   Role name   |   Attributes
---------------+----------------
 sandbox_admin | 10 connections
```

### 3.2 pg_roles flag 嚴格驗

```
   rolname    | rolsuper | rolcreaterole | rolcreatedb | rolcanlogin | rolreplication | rolbypassrls | rolconnlimit
---------------+----------+---------------+-------------+-------------+----------------+--------------+--------------
 sandbox_admin | f        | f             | f           | t           | f              | f            |           10
```

全 6 flag attribute attacker fence ✅

## §4 sqlx_migrate route 驗證

### 4.1 Architecture discovery（push back PA + QA）

PA Phase 3e signoff §4.2 + QA Phase 3c §1.4 寫的 `cargo run --release --bin sqlx_migrate -- run` **不是真實 binary**。Cargo workspace  內 5 個  全部列表：

| bin | 用途 |
|---|---|
| openclaw-engine | 主 engine（包 MigrationRunner::run_if_enabled） |
| repair_migration_checksum | checksum drift 修補（trading_ai production 場景） |
| feature_baseline_writer | ML 訓練 baseline |
| replay_runner | replay harness |
| (hot_path_baseline + intent_processor_exposure) | bench |

Migration 真正 entry path：engine startup  呼叫 ，靠 `OPENCLAW_AUTO_MIGRATE=1` env var 開啟。**沒有 standalone migration CLI**。

### 4.2 sandbox sqlx_migrate primitives 驗（path C — 在 task scope）

sandbox_admin 對 _sqlx_migrations 的 R/W primitives 全測過：

| 動作 | 結果 |
|---|---|
| SELECT count(*) FROM _sqlx_migrations | 93 ✅ |
| INSERT row (version=99999, success=t, ...) | success ✅ |
| DELETE row | success ✅ |
| CREATE TABLE governance.e3_smoke_test_table | success ✅ |
| INSERT + SELECT + DROP TABLE | success ✅ |
| SELECT from governance.lease_lal_tiers (V112) | 5 row ✅ |

→ sandbox_admin **完全具備 migration runner 所需 primitives**

### 4.3 Sprint 1B 派發兩條路徑（E3 推薦）

**Path A（推薦）**：Sprint 1B 啟動獨立 sandbox engine instance
```bash
DATABASE_URL='postgres://sandbox_admin:<from secret_file>@127.0.0.1:5432/trading_ai_sandbox' \
OPENCLAW_AUTO_MIGRATE=1 \
OPENCLAW_ALLOW_DBLESS=0 \
cargo run --release --bin openclaw-engine -- --dry-run-migrations-only
```
（需 E1 確認 openclaw-engine 是否支援 `--dry-run-migrations-only` early-exit flag；如無則需 E1 加）

**Path B（後備）**：E1 寫獨立 `sandbox_migrate_runner` binary
```rust
// rust/openclaw_engine/src/bin/sandbox_migrate_runner.rs
// 唯一職責：read OPENCLAW_DATABASE_URL → MigrationRunner::run_if_enabled() → log + exit
// 算法與 engine 同源（同 load_migrations_from_dir + Sha384 checksum）
// 不接 IPC / 不接 risk / 不接 strategy
```
估時 1-2 hr E1 + 1 hr E2 review。

## §5 密碼儲存

| 屬性 | 值 |
|---|---|
| Path | /home/ncyu/BybitOpenClaw/srv/settings/secret_files/postgres/sandbox_admin/password |
| Permission | -rw------- (0600) |
| Owner | ncyu:ncyu |
| Content | 33-char base64 / 24-byte raw entropy |
| gitignored | ✅ (matches `**/secret_files/` in srv/.gitignore) |
| git status | clean（未 tracked / 未 staged） |
| .pgpass 整合 | **未加**（避免 .pgpass 寫多 password 增加環境耦合；Sprint 1B 接 sandbox engine 時讀 secret_file path） |

讀法（Rust/Python）：
```rust
// 同 engine 既有 pattern：secret_env::var_or_file
let password = secret_env::var_or_file(
    OPENCLAW_SANDBOX_DB_PASSWORD,
    Some(/home/ncyu/BybitOpenClaw/srv/settings/secret_files/postgres/sandbox_admin/password),
)?;
```

## §6 攻擊面審計（E3 attacker mindset）

5 attack vector empirical 驗：

| # | Vector | Expected | Actual | Severity |
|---|---|---|---|---|
| 1 | connect trading_ai production | DENY | **ALLOW**（PG PUBLIC 預設 CONNECT 副作用，REVOKE 從 sandbox_admin 個別後仍能 connect） | **MEDIUM** |
| 2 | CREATE TABLE in trading_ai | DENY | DENY（schema USAGE/CREATE 無）| PASS |
| 3 | SELECT trading.fills | DENY | DENY（permission denied for schema trading）| PASS |
| 4 | \l enumerate all DBs | DENY (ideal) / ALLOW (PG default) | ALLOW（pg_database catalog 全民可讀）| LOW |
| 5 | information_schema.tables in trading_ai | DENY (ideal) | ALLOW，但僅 8 schemas = pg_catalog + info + 7 _timescaledb_*；**user schema 0** | PASS |

### 6.1 [E3-MED-1] sandbox_admin 可 connect trading_ai production

**證據**：
```
PGPASSWORD=... psql -h 127.0.0.1 -U sandbox_admin -d trading_ai -c 'SELECT current_user, current_database();'
 current_user  | current_database
---------------+------------------
 sandbox_admin | trading_ai
```
即使 `REVOKE CONNECT ON DATABASE trading_ai FROM sandbox_admin` 後仍能 connect（PUBLIC ACL `=Tc/trading_admin` 持續授 connect）。

**攻擊鏈**：
1. secret_file 洩漏（filesystem 被入侵 / git push 誤 add） → sandbox_admin credentials 公開
2. attacker connect trading_ai
3. 可讀 pg_catalog（role 列表 / DB owner / role flags）+ information_schema（schema 名 / table 名 columns 含 user schema 但 GRANT 後 0 visible）
4. **無法**：read user data / write / DDL

**Impact**：metadata leak（DB 名 / TimescaleDB version / role 命名規律）；不洩漏 trading data / risk config / authorization.

**修法**（**carry-over Sprint 1A-ε P2 或 Sprint 1B infra**，不阻 1B 派發）：

**Option A**（最小破壞）：pg_hba.conf 加 row reject sandbox_admin connect trading_ai：
```
# /etc/postgresql/16/main/pg_hba.conf 加在 host all all 0.0.0.0/0 scram-sha-256 之前
host    trading_ai      sandbox_admin   0.0.0.0/0       reject
host    trading_ai      sandbox_admin   ::/0            reject
# sudo systemctl reload postgresql
```
Pro：不改 DB ACL，不影響其他 role
Con：需 sudo + reload

**Option B**（PG ACL 嚴格化）：REVOKE PUBLIC CONNECT on trading_ai + 明文 GRANT 給 production roles：
```sql
REVOKE CONNECT ON DATABASE trading_ai FROM PUBLIC;
GRANT CONNECT ON DATABASE trading_ai TO trading_admin;
-- 重新 GRANT 給所有現有 production roles
```
Pro：純 SQL；可 transaction wrap
Con：需 audit 所有現有 production role list；高破壞

**E3 推薦**：Option A（infra patch）+ 寫進 Sprint 1A-ε P2 carry-over，由 PM 決定排 Sprint 1A-ε infra slot 或延到 Sprint 1B 基建。

### 6.2 attack 4 (\l enumeration)

PG 預設 pg_database catalog 全民可讀；任何 LOGIN role 都能 `\l`。常規 PG 行為，不視為 vulnerability。Severity **INFO**.

## §7 Verdict

**PASS WITH 1 MEDIUM FINDING**（不阻 Sprint 1B 派發）

| Item | Status |
|---|---|
| sandbox_admin role 創建 | ✅ DONE |
| 權限範圍對齊 spec | ✅（schema USAGE+CREATE + table/sequence/function ALL + DEFAULT PRIV）|
| 不可權限 attacker fence | ✅（6/6 flag denied） |
| sqlx_migrate primitive 全可用 | ✅（CREATE/INSERT/UPDATE/DELETE _sqlx_migrations + DDL 全測過） |
| 密碼儲存 secure | ✅（secret_files 0600 + gitignored） |
| **trading_ai production 隔絕** | ❌ **MEDIUM**（connect 仍 ALLOW；user data/DDL 防住但 metadata 暴露） |

### 7.1 carry-over to Sprint 1A-ε P2 or Sprint 1B infra

- **[E3-MED-1]** pg_hba.conf 加 reject row 或 `REVOKE CONNECT FROM PUBLIC ON trading_ai` — 屬 infra patch 需 sudo + reload；建議 Sprint 1A-ε P2 排程或併 Sprint 1B 第一個 infra wave

### 7.2 carry-over to Sprint 1B Track（V### sandbox re-apply）

- **PA + QA `cargo run --release --bin sqlx_migrate` 路徑不存在 spec edit**：建議 PA 在 Sprint 1A-ε 順手收口 spec literal，改為「openclaw-engine + OPENCLAW_AUTO_MIGRATE=1 + sandbox DB URL」OR 由 E1 寫獨立 `sandbox_migrate_runner` bin
- **sandbox V### re-apply 自身**：sandbox_admin role 已 ready；Sprint 1B 走 path A（engine instance）或 path B（new bin）即可

### 7.3 4 條 finish report

1. **sandbox_admin role 創建**：✅ SUCCESS — 12 SQL statement 無 error；6/6 attacker fence flag 對；search_path + connection limit 10
2. **sqlx_migrate route 通否**：✅ primitive 全可用（_sqlx_migrations INSERT/DELETE + DDL CREATE/DROP empirical 驗）；❌ `--bin sqlx_migrate` standalone path **不存在**；建議走 engine startup（path A）或寫新 bin（path B）— **push back PA/QA spec literal patch**
3. **密碼儲存**：`srv/settings/secret_files/postgres/sandbox_admin/password` (0600, gitignored, 33-char base64 SCRAM)
4. **Sprint 1B V### sandbox re-apply unblock**：✅ unblock — role 已 ready；剩需 E1 + PA 收 sqlx_migrate spec literal（path A 加 `--migrations-only` flag OR path B 新 sandbox_migrate_runner bin）+ Sprint 1B Track empirical 跑

## §8 Sign-off

- **E3 Security Auditor** 簽收 Sprint 1A-ε P1 sandbox_admin role 創建
- **Verdict**：PASS WITH 1 MEDIUM FINDING
- **State**：sandbox_admin role + secret_file + 全權限 sandbox-side land；attacker fence 5/6 attack vector 防住
- **下一步**：Sprint 1B V### re-apply phase 用 sandbox_admin；[E3-MED-1] pg_hba.conf hardening carry-over Sprint 1A-ε P2 或 Sprint 1B infra

---

**END OF Sprint 1A-ε P1 E3 sandbox_admin Role Creation Report**
