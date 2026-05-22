---
report: Sprint 1A-ε P2 N3 — E3-MED-1 sandbox_admin trading_ai connect block
date: 2026-05-22
author: E3 (Security Auditor)
phase: Sprint 1A-ε P2 (post-Sprint 1A-ζ closure)
status: SIGNED-OFF · E3-MED-1 CLOSED
parent: docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-22--sprint_1a_epsilon_sandbox_admin_role.md (P1 + E3-MED-1 finding)
---

# E3 Sprint 1A-ε P2 N3 sandbox_admin trading_ai connect block — 2026-05-22

## §1 Pre-state attack surface 確認

- sandbox_admin → trading_ai connect 成功: current_user=sandbox_admin / current_database=trading_ai;
  metadata 完全暴露 (\\dn 列 trading_ai 全 14 schema 名 + owner trading_admin)
- production engine user = trading_admin; 當前 engine PID 2934602 (非 spec 寫的 3954769;
  engine 已重啟 23h17m); 20 PG connection 全 trading_admin
  (18 從 docker bridge 172.18.0.1 + 1 socket + 1 background worker)
- 只 2 個 LOGIN role: sandbox_admin + trading_admin
- PUBLIC default CONNECT 確認: pg_database.datacl 兩 DB 都含 =Tc/trading_admin
  (PUBLIC 有 TEMP + CONNECT); 這是 E3-MED-1 根本副作用
- pg_hba.conf path: /var/lib/postgresql/data/pg_hba.conf
  (docker container trading_postgres 內; image timescale/timescaledb:latest-pg16)
- Docker bridge NAT 結構: trade-core host → 127.0.0.1:5432 → Docker NAT → container 看到
  client_addr 172.18.0.1; line 119 host all all 127.0.0.1/32 trust 對外部 ssh 訪問無效;
  外部都走 line 128 host all all all scram-sha-256

## §2 Option choice

Option B pg_hba.conf reject row per QA Phase 3c report 拍板 (最小破壞)。

## §3 Apply

- Backup: docker exec trading_postgres cp /var/lib/postgresql/data/pg_hba.conf
  /var/lib/postgresql/data/pg_hba.conf.bak.2026-05-22
  (pristine sha256 af0fdb73...; perm 600)
- Insertion 位置: 在 line 121 local all all trust 之前 (first-match-wins 必須優先 reject)
- 兩個 reject row:
  ```
  # Sprint 1A-epsilon P2 N3 2026-05-22: block sandbox_admin from trading_ai production DB (E3-MED-1 closure)
  local   trading_ai      sandbox_admin                           reject
  host    trading_ai      sandbox_admin   all                     reject
  ```
- Reload: SELECT pg_reload_conf() returned t; 未重啟 PG / 未斷現有 22 個 trading_admin connection
- 新文件 sha256: 14c683c4b55a82c26dffbf6065b4e0002fe34193bb9670ca15cc0bdda79e3664;
  permission 對齊 backup 為 600

## §4 Verify (7/7 PASS)

| # | Vector | 預期 | 實測 |
|---|---|---|---|
| 1 | sandbox_admin → trading_ai (host 127.0.0.1) | REJECT | ✅ pg_hba.conf rejects connection for host "172.18.0.1" |
| 2 | sandbox_admin → trading_ai_sandbox (host 127.0.0.1) | ALLOW | ✅ current_user=sandbox_admin / db=trading_ai_sandbox |
| 3 | sandbox_admin → trading_ai (local socket inside container) | REJECT | ✅ pg_hba.conf rejects connection for host "[local]" |
| 4 | sandbox_admin → trading_ai_sandbox (local socket inside container) | ALLOW | ✅ current_user=sandbox_admin |
| 5 | trading_admin → trading_ai | ALLOW | ✅ 22 active connection 健康; engine PID 2934602 仍跑 23h17m |
| 6 | trading_admin → trading_ai_sandbox | ALLOW | ✅ current_user=trading_admin / db=trading_ai_sandbox |
| 7 | sandbox_admin → trading_ai pg_catalog metadata read | REJECT | ✅ SELECT * FROM pg_catalog.pg_class LIMIT 1 直接被 fence at connection 層 |

### Rollback path (未真實執行; backup 存在 + 路徑清楚)

```
ssh trade-core "docker exec trading_postgres cp /var/lib/postgresql/data/pg_hba.conf.bak.2026-05-22 /var/lib/postgresql/data/pg_hba.conf"
ssh trade-core "PGPASSWORD=\$(awk -F: '\$3==\"trading_ai\" && \$4==\"trading_admin\" {print \$5}' ~/.pgpass) psql -h 127.0.0.1 -U trading_admin -d trading_ai -c 'SELECT pg_reload_conf();'"
```

## §5 Verdict

| Item | Status |
|---|---|
| pg_hba.conf 加 reject row (Option B per QA 拍板) | ✅ DONE |
| sandbox_admin → trading_ai connect (host + local) 雙向 fence | ✅ DONE |
| sandbox_admin → trading_ai_sandbox 仍通 | ✅ DONE |
| trading_admin → trading_ai 不誤殺 (engine PID 2934602 + 22 connection 健康) | ✅ DONE |
| pg_catalog metadata leak 路徑閉合 (connection-level reject) | ✅ DONE |
| backup + rollback path 完整 | ✅ DONE |
| 無 secret plaintext 寫入 git / docs | ✅ DONE |
| production engine 未重啟 (pg_reload_conf 不影響現有 connection) | ✅ DONE |

**Verdict**: PASS — E3-MED-1 CLOSED

| 嚴重性 | 位置 | 攻擊路徑 | 修法 |
|---|---|---|---|
| MEDIUM → CLOSED | sandbox_admin → trading_ai connect via PUBLIC=Tc/trading_admin default ACL | secret_file 洩漏 → attacker host connect 127.0.0.1:5432 → pg_hba scram-sha-256 → metadata read pg_catalog/information_schema | pg_hba.conf 加 reject row × 2 (local + host) → pg_reload_conf() |

## §6 Lessons sustained (E3 memory.md append)

1. **Docker bridge NAT 影響 pg_hba 規劃**: trade-core host → 127.0.0.1:5432 → container 看到
   client_addr 172.18.0.1 (Docker default bridge gateway), 不是 127.0.0.1;
   host all all 127.0.0.1/32 trust line 對外部 ssh 訪問無作用; 任何 reject row address 必用 all 或 172.18.0.1/32
2. **pg_hba.conf first-match-wins + reject 必須最先匹配**: local all all trust 在 PG default config line 121 是 ground rule;
   把 reject row 放到它之後雖然語法合法但 trust 先匹配 → reject 無效; reject row 必須在所有 trust/allow row 之前
3. **pg_reload_conf() 不殺現有 connection**: production engine PID 2934602 + 22 trading_admin connection 全 reload 後仍健康;
   reload 只影響 new connection auth path; 但攻擊者已連 trading_ai 的 sandbox_admin session reload 不會 kick — 同類 fix 在「持續攻擊中」場景要配合 pg_terminate_backend(pid)
4. **task spec PID drift**: spec 寫 production engine PID 3954769, 實測 PID = 2934602 (已重啟 23h17m);
   多 session 多進程環境下 PID 是 mutable, 必須用 ps -eo pid,user,cmd | grep openclaw-engine 動態 verify 而非信任 spec literal

E3 AUDIT DONE: 0 CRITICAL · 0 HIGH · 0 NEW MEDIUM · E3-MED-1 (sandbox_admin trading_ai connect) CLOSED
