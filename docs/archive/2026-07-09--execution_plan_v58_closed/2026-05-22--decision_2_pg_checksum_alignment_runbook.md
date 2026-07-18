> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）

# 決定 2 — trading_ai PG checksum 對齊 C 路線 Runbook

**日期**：2026-05-22
**作者**：PM 主會話 (Sprint 1A audit verdict synthesis 派生)
**對應 audit**：MIT 紅線 2 + R4 HIGH-D-3 + Sprint 1A audit 綜合 verdict §六 必修順序 B
**Status**：DESIGN-DONE / IMPL-PENDING（待 E1 + MIT Linux runtime 執行）
**TODO ref**：§5.1 P1 `P1-PG-CHECKSUM-ALIGNMENT-DECISION-2-C`

---

## 一、背景

Sprint 1A audit (2026-05-22) MIT 紅線 2 揭露：

- **trading_ai 主 PG** `_sqlx_migrations` MAX(version) = **96**
- **V103 / V106 / V107 / V112** 4 個 .sql 已寫入 `sql/migrations/`（Sprint 1A-ζ Phase 2 commit `2f6d1761`）但**僅 sandbox apply**（V103 via Sprint 1A-ε P1 `454f26f3` / V106+V107+V112 via Sprint 1A-ζ Phase 2）
- trading_ai 主 DB **零 production apply** Sprint 1A V### 任一條

**風險**：下次 engine restart 若 `OPENCLAW_AUTO_MIGRATE=1`：
1. sqlx 跑 V103 file content checksum
2. V103 file content 自 V003 base 改過（Sprint 1A-ε P1 land + Sprint 1B Track C sandbox apply）但 trading_ai `_sqlx_migrations` 表 0 row → sqlx 視為新檔
3. 若 V103 base 在 trading_ai 已 apply（per V003 base hypotheses table 存在）→ sqlx checksum mismatch RAISE
4. **重蹈 P0 2026-05-02 sqlx hash drift incident**（per memory `project_2026_05_02_p0_sqlx_hash_drift`）

operator 拍板路線 = **C 中間路線**（per 2026-05-22 audit AskUserQuestion）：30 min 立即動作 + Sprint 2 normal flow 內含 staging full apply test，不打斷 Sprint 2，預防 2026-05-02 反模式。

---

## 二、5 Step Execution Plan

**前置**：本 SOP 必須由 E1 + MIT 在 Linux runtime（`ssh trade-core`）執行；Mac 端只負責 spec + commit 不負責 PG 動作（per CLAUDE.md §六 Mac 為開發端）。

### Step 1 — `OPENCLAW_AUTO_MIGRATE=0` env override（立即 / 5 min）

**目的**：撤掉 next engine restart 的 auto-trigger 撞 checksum 風險。

**動作**：
```bash
ssh trade-core
# 找 engine env 配置（推測位置 settings/ 或 systemd unit env file）
grep -r "OPENCLAW_AUTO_MIGRATE" /home/ncyu/Projects/TradeBot/srv/settings/ /etc/systemd/system/openclaw*.service 2>/dev/null
# 將 OPENCLAW_AUTO_MIGRATE=1 改為 OPENCLAW_AUTO_MIGRATE=0
# OR 在 systemd unit 加 Environment=OPENCLAW_AUTO_MIGRATE=0 override
sudo systemctl daemon-reload  # 若改 systemd unit
# 驗證 engine 當前 PID 環境變數
sudo cat /proc/$(pgrep -f openclaw_engine)/environ | tr '\0' '\n' | grep OPENCLAW_AUTO_MIGRATE
```

**驗證 AC**：
- `cat /proc/<pid>/environ` 顯示 `OPENCLAW_AUTO_MIGRATE=0` OR env 完全 unset（即 default=false per Rust MigrationRunner）
- 不重啟 engine PID（保留 v1 v2 等運行狀態）

**Rollback**：如果改 systemd unit 後不慎觸發 reload 致 engine 重啟，立即 revert override 並走 Step 2 dry-run。

---

### Step 2 — `bin/repair_migration_checksum --dry-run` 標記 drift（10 min）

**目的**：empirical 探出 trading_ai 與 sql/migrations/ 之間哪些檔有 checksum drift；不修補只標記。

**動作**：
```bash
ssh trade-core
cd /home/ncyu/Projects/TradeBot/srv
# 對 trading_ai 主 DB 跑 dry-run（per Sprint 1A-ε P2 N1 patch 路徑：MigrationRunner real path 非 cargo run --bin sqlx_migrate fiction）
OPENCLAW_DB_URL=postgres://trading_admin@127.0.0.1:5432/trading_ai \
  cargo run --release --bin repair_migration_checksum -- --dry-run --report 2>&1 | tee /tmp/checksum_drift_$(date +%F).log
```

**驗證 AC**：
- log 列出每條 V### 的：(a) file content sha256 (b) `_sqlx_migrations` table 紀錄 sha256 (c) match / mismatch
- 預期：V001-V096 全 match（既有 production apply）；V097/V098 視 file 是否 existed at 96-apply time；V103/V106/V107/V112 全 "table not registered"（不是 mismatch 是 absent）
- 0 destructive 操作 — `--dry-run` 必確認 SQL execution = 0 ROW affected

**警告**：如果某 V<=096 顯示 mismatch（非「absent」），**暫停執行**，立即報告 — 屬於更深層 drift 不在本 SOP scope。

---

### Step 3 — V103/V106/V107/V112 metadata register（10 min）

**目的**：把 sandbox 已 apply 的 4 條 V### 註冊到 trading_ai `_sqlx_migrations` 表（**僅 metadata insert，不動 schema**），讓未來 `OPENCLAW_AUTO_MIGRATE=1` 重啟時 sqlx 視為「已 apply 不再重跑」。

**前提 verify**：
- trading_ai 主 DB 實際 schema 是否含 4 條 V### 對應 table？預期 **否**（per MIT 紅線 2: trading_ai 0 apply）
- 如果預期外 trading_ai 已含 health_observations / replay_divergence_log / lease_lal_tiers / hypotheses 4 表 → **暫停執行**，需重新評估 schema drift

**動作（V103 為例，其他 3 條同理）**：
```bash
# 1. 算 V103 file sha256
sha256sum sql/migrations/V103__extend_m4_hypothesis_columns.sql
# 假設輸出 abc123...

# 2. 對 trading_ai 主 DB 插入 _sqlx_migrations row（V103/V106/V107/V112 共 4 條）
# 注意：execution_time 用 sandbox apply 實測時間或填 0；checksum 必符合 file 真實 sha256
docker exec trading_postgres psql -d trading_ai -U trading_admin <<'SQL'
BEGIN;
-- V103
INSERT INTO _sqlx_migrations (version, description, installed_on, success, checksum, execution_time)
VALUES (103, 'extend m4 hypothesis columns', NOW(), TRUE,
  decode('<V103_sha256_hex>', 'hex'), 0)
ON CONFLICT (version) DO NOTHING;
-- V106
INSERT INTO _sqlx_migrations (version, description, installed_on, success, checksum, execution_time)
VALUES (106, 'health observations', NOW(), TRUE,
  decode('<V106_sha256_hex>', 'hex'), 0)
ON CONFLICT (version) DO NOTHING;
-- V107
INSERT INTO _sqlx_migrations (version, description, installed_on, success, checksum, execution_time)
VALUES (107, 'replay divergence log', NOW(), TRUE,
  decode('<V107_sha256_hex>', 'hex'), 0)
ON CONFLICT (version) DO NOTHING;
-- V112
INSERT INTO _sqlx_migrations (version, description, installed_on, success, checksum, execution_time)
VALUES (112, 'decision lease lal tiers', NOW(), TRUE,
  decode('<V112_sha256_hex>', 'hex'), 0)
ON CONFLICT (version) DO NOTHING;
-- verify
SELECT version, description, installed_on, success, encode(checksum,'hex') FROM _sqlx_migrations WHERE version IN (103,106,107,112);
COMMIT;
SQL
```

**驗證 AC**：
- `SELECT MAX(version) FROM _sqlx_migrations` 仍是 96（因 V97/V98 缺 → V99+ 都不視為 contiguous max；但 V103/V106/V107/V112 4 行已存在）
- **Schema 不變**：`\dt trading_ai.*` 仍是 V096-time 狀態，不含 health_observations / replay_divergence_log / lease_lal_tiers 4 表
- 4 row 的 checksum hex 與 `sha256sum sql/migrations/V###.sql` 對齊

**Rollback**：
```sql
BEGIN; DELETE FROM _sqlx_migrations WHERE version IN (103,106,107,112); COMMIT;
```

**重要**：此 step **不**註冊 sandbox 的 V### 對應 schema（這些只在 sandbox apply）；只是讓 trading_ai sqlx 知道「這 4 條 spec 已被 reviewed，但 schema apply 留到 Step 5 staging+deploy window 統一執行」。如此可保：(a) AUTO_MIGRATE=1 restart 時 V103/V106/V107/V112 不會被 sqlx 視為「未 apply」而觸發 schema apply（schema 物理上不存在但 metadata 已標記 = 合法 mismatch fail-loud 路徑，比 schema apply 失敗 panic 更可恢復）

⚠️ **alt 方案**（更保守）：**不**註冊 4 條 metadata，繼續維持 `_sqlx_migrations` MAX=96；只靠 Step 1 AUTO_MIGRATE=0 阻擋；Step 5 staging+deploy window 同時 apply schema + 註冊 metadata。此 alt 更乾淨但需要 Sprint 2 staging 階段必走 5 V### sequential apply（V103→V106→V107→V112，注意 V103 是 base 其他是 hypothesis）。

**決策 owner**：MIT 於 Linux PG empirical 之後拍板採 Step 3 路徑 OR alt 路徑；本 SOP 建議 alt（更保守，metadata 與 schema 不脫鉤）。

---

### Step 4 — Sprint 2 staging full apply test（Sprint 2 normal flow / ~2-4 hr）

**目的**：在 Sprint 2 Wave 1 IMPL（含 V099 + V108 + V109 + V110 + V111 + V113 共 6 條新 V###）期間，於 staging env 完整跑一次 V096 → V113 連續 apply，驗證：

1. **idempotency**：apply 兩次仍 GREEN（per CLAUDE.md §Data Migrations）
2. **Guard A/B/C empirical fire**：V106/V109 反向 INSERT forbidden action → RAISE EXCEPTION
3. **FK type alignment**：V108 `m11_replay_divergence_ref BIGINT`（已 patch UUID → BIGINT 2026-05-22 per MIT 紅線 3）+ V107 PK BIGINT bigserial 對齊
4. **cross-V### dependency**：V107 ← V103/V109/V113；V108 ← V103；V109 Guard A 黑名單反模式 RAISE
5. **engine restart 0 panic with AUTO_MIGRATE=1**：staging engine `--rebuild --keep-auth` + AUTO_MIGRATE=1 → migrate 順利完成 + LAL/health/M11 模組 init 0 panic

**動作**：併入 Sprint 2 Wave 1 dispatch packet（已有 spec at `2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md`）；本 SOP Step 4 為 prerequisite 加入 Wave 1 Track C database_pool ready 之前。

**驗證 AC**：
- staging engine `journalctl -u openclaw-engine --since "5 min ago"` 0 panic / 0 sqlx error
- staging trading_ai `_sqlx_migrations` MAX = 113（V099-V113 全 land）
- 6 condition forbid（health_observations engine_mode='replay' INSERT / anomaly_events hmm INSERT / etc.）反向 fire RAISE confirmed

**Rollback**：staging-only 不影響 production；若 fail，回 Step 3 alt 路徑保 trading_ai metadata=96 + 6 V### spec 修正再 retry。

---

### Step 5 — Sprint 2 deploy window 統一 apply（per Sprint 2 第一個 first Live ready 前 / TBD）

**目的**：staging Step 4 全 GREEN 後，在 Sprint 2 結束接 Sprint 3+ 之間的 deploy window 一次性對 trading_ai 主 DB apply V099-V113。

**前置 hard requirements**（必前置完成）：
- ✅ Step 1 AUTO_MIGRATE=0 仍維持
- ✅ Step 3 metadata 一致（採 alt 路徑為 MAX=96；採 Step 3 路徑為 4 條 metadata 已註冊但 schema 缺）
- ✅ Step 4 staging 7d 連續 0 panic（per CLAUDE.md §Data Migrations + Sprint 1A-ζ AC-3 production restart 0 panic carry-over）
- ✅ E2 + E4 + QA + PM 4 方 sign-off staging report

**動作**：
```bash
ssh trade-core
# 1. Stop engine（graceful）
sudo systemctl stop openclaw-engine

# 2. Backup trading_ai
docker exec trading_postgres pg_dump -U trading_admin -d trading_ai -Fc -f /var/backups/trading_ai_pre_v113_$(date +%F).dump

# 3. Set AUTO_MIGRATE=1
sudo systemctl edit openclaw-engine.service  # 或改 settings/
# Environment=OPENCLAW_AUTO_MIGRATE=1
sudo systemctl daemon-reload

# 4. Start engine — sqlx 跑 V097/V098/V099/V103/V105/V106/V107/V108/V109/V110/V111/V112/V113 連續 apply
sudo systemctl start openclaw-engine
sudo journalctl -u openclaw-engine -f  # 觀察 30 min

# 5. Verify
docker exec trading_postgres psql -d trading_ai -U trading_admin -c "SELECT MAX(version) FROM _sqlx_migrations;"
# 預期 MAX=113

# 6. Set AUTO_MIGRATE=0 again（防後續 Sprint 3+ V### 意外 auto-trigger）
sudo systemctl edit openclaw-engine.service
# Environment=OPENCLAW_AUTO_MIGRATE=0
sudo systemctl daemon-reload
# 不重啟（engine 已運行）
```

**驗證 AC**：
- `_sqlx_migrations` MAX=113
- 10 個 target table 全存在（health_observations / degradation_state / replay_divergence_log / reward_weight_history / decision_lease_lal_tiers / lal_eligibility_log / decay_signals / strategy_lifecycle / earn_movement_log / hypotheses）
- engine LAL Tier 0 evaluation 在 production fire 至少 1 次（per ADR-0034 LAL 0-4 PG CHECK runtime fire）
- 30 min observation 0 panic / 0 sqlx error / 0 schema mismatch

**Rollback**：
```bash
# 如 30 min 內任何 panic / mismatch
sudo systemctl stop openclaw-engine
docker exec trading_postgres pg_restore -U trading_admin -d trading_ai -c /var/backups/trading_ai_pre_v113_$(date +%F).dump
# revert AUTO_MIGRATE=0
sudo systemctl start openclaw-engine
# Status：trading_ai 退回 96；Sprint 2 deploy 失敗；需 PA + MIT + PM 共同 audit
```

---

## 三、4 路線比較重申

| Step | 動作 | 何時 | 風險 |
|---|---|---|---|
| Step 1 | AUTO_MIGRATE=0 env override | 立即 5 min | 極低（僅 env，不動 PG） |
| Step 2 | dry-run drift report | 立即 10 min | 0（dry-run） |
| Step 3 | V103/V106/V107/V112 metadata register (or alt) | 立即 10 min | 低（仅 metadata 4 row INSERT） |
| Step 4 | staging full apply test V099-V113 | Sprint 2 Wave 1 期 | 中（staging-only；rollback 可恢復） |
| Step 5 | trading_ai 統一 apply V099-V113 | Sprint 2 結束 deploy window | 中-高（production；有 pg_dump backup） |

**選 C 路線而非 A/B 的核心理由**：
1. **2026-05-02 P0 sqlx hash drift 教訓不重蹈** — Step 1+3 + staging Step 4 嚴格 dry-run mandate
2. **不打斷 Sprint 2 flow** — Step 1+2+3 共 25 min 立即動作；Step 4 併 Wave 1；Step 5 等 staging GREEN
3. **CLAUDE.md §Data Migrations 合規** — PG empirical dry-run + Linux runtime + staging full apply
4. **CLAUDE.md §四 Hard Boundaries 不觸碰** — 5 gates、authorization、Bybit retCode、fake AI 等全 0 動

---

## 四、SOP Owner + ETA

| Step | Owner | ETA | Trigger |
|---|---|---|---|
| Step 1 | E1 + MIT | D+0 (立即) | TODO §5.1 `P1-PG-CHECKSUM-ALIGNMENT-DECISION-2-C` claim |
| Step 2 | MIT | D+0 (Step 1 後即時) | Step 1 verified |
| Step 3 (or alt) | MIT + E1 (joint sign-off) | D+0 (Step 2 後 10 min) | Step 2 dry-run log clean (V<=096 全 match) |
| Step 4 | E1 + MIT + QA | Sprint 2 Wave 1 期內 (~D+5..D+10) | Sprint 2 Wave 1 dispatch READY |
| Step 5 | PM + E1 + MIT + QA + E2 + E4 | Sprint 2 結束 deploy window (TBD ~D+25..D+30) | Step 4 staging 7d 0 panic |

---

## 五、References

- **Sprint 1A audit 綜合 verdict 2026-05-22**：本 session 主 PM 派 6 sub-agent 並行核驗 — MIT 紅線 2 + R4 HIGH-D-3 觸發本 SOP
- **memory `project_2026_05_02_p0_sqlx_hash_drift`**：上次 sqlx checksum drift incident 反模式來源
- **`feedback_v_migration_pg_dry_run`** (2026-05-05)：Mac mock pytest 不可代替 Linux PG empirical
- **CLAUDE.md §Data, Migrations, And Validation**：Guard A/B/C + idempotency + Linux empirical mandatory
- **`docs/agents/context-loading.md` PG Connection Examples**：Linux runtime authoritative connection guide
- **Sprint 1A-ε P2 N1 patch (commit `6cd3d631`)**：MigrationRunner real path （非 `cargo run --bin sqlx_migrate` fiction）
- **V099 spec**：`docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`（568 LOC；Step 4 Wave 1 必含）
- **V108 patch 2026-05-22**：UUID → BIGINT type fix（per MIT 紅線 3 + 本 audit）
- **TODO §5.1 P1 queue**：本 SOP claim `P1-PG-CHECKSUM-ALIGNMENT-DECISION-2-C`

---

## 六、Sign-off 路徑（Sprint 2 deploy window 前）

1. **E1 + MIT joint sign-off Step 1+2+3** — D+0 完成後 30 min report at `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-XX--decision_2_step123_signoff.md`
2. **E2 review** — Step 3 metadata INSERT SQL adversarial review；確認無 schema 動作
3. **QA staging report** — Step 4 7d 0 panic
4. **PM final sign-off** — Step 5 deploy window 開始前
5. **Operator final approve** — Step 5 deploy window 命令觸發（per CLAUDE.md §四 Hard Boundaries true-live 5-gate 不繞）

---

**Status**：本 runbook DESIGN-DONE 2026-05-22；IMPL-PENDING 等 E1 + MIT claim `P1-PG-CHECKSUM-ALIGNMENT-DECISION-2-C` 後執行。
