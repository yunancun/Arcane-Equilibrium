# V089 Linux PG dry-run + apply + register — STOP at Step 1

**Status**: 🛑 **STEP 1 FAIL — STOP per task spec, awaiting PM ruling**
**Owner**: E1（Backend Developer）｜ **Date**: 2026-05-10
**Sprint**: N+1 D+0 follow-up — W5-E1-A V089 Linux PG dry-run
**Cross-ref**:
- Source spec: `docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`
- W5-E1-A IMPL report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w5_e1_a_canary_stage_criteria_1_impl.md`
- V089 SQL: `srv/sql/migrations/V089__governance_canary_stage_metric_seed.sql`
- W5-E1-A commit: `6529e37e`
- V086/V090 sha384sum register pattern (PM 已驗 success)

---

## 1. 任務摘要

PM 派 V089 Linux PG dry-run + apply + register（W5-E1-A IMPL DONE 後 follow-up，因 sub-agent 在 Mac 上沒 PG 無法跑 Linux dry-run）。預期流程：

1. Step 1 — `psql -f V089__... ` 第 1 次 apply (預期 18 row INSERT + Final NOTICE)
2. Step 2 — 第 2 次 apply (idempotency, 0 RAISE)
3. Step 3 — sha384sum register V89 至 `_sqlx_migrations`
4. Step 4 — 驗 V80-V90 全綠
5. Step 5 — `governance.canary_stage_metric_registry` 內容 verify

**實際結果**：Step 1 立即 PG syntax error → ON_ERROR_STOP=on transaction rollback → 0 row inserted → STOP per spec **「任一步 FAIL → STOP + 不繼續 + report + 等 PM 拍板」**。

---

## 2. 修改清單

**無 code 改動**。Mac repo 本地 working tree 有 unrelated WIP（layer2_*.py / provider_*.py / tab-ai.html）— 與 V089 task 無關，不碰。

---

## 3. 關鍵 diff / Step 1 實測輸出

### 3.1 Step 1: V089 dry-run 1st apply on Linux trade-core

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && PG_PASS=$(awk -F= "/^POSTGRES_PASSWORD=/{print \$2}" \
  /home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env) && \
  PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -U trading_admin -d trading_ai -v ON_ERROR_STOP=on \
  -f sql/migrations/V089__governance_canary_stage_metric_seed.sql 2>&1 | tail -50'
```

**Output**:
```
WARNING:  database "trading_ai" has no actual collation version, but a version was recorded
DO            ← Schema Guard A pass
DO            ← Schema Guard C pass
psql:sql/migrations/V089__governance_canary_stage_metric_seed.sql:121: ERROR:  syntax error at or near "ON"
LINE 13: ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTH...
         ^
```

**Diagnosis**：line 121 `ON CONFLICT` 之前一行 (line 120) VALUES 列表 last row 帶 trailing `,`。PG INSERT VALUES syntax 不允許 trailing comma — values list 結束 token 必須是 `)` 不能是 `,`。

### 3.2 7 處同模式 syntax bug 全部找到

`grep -n "^ON CONFLICT|),$|TRUE)$" V089__...sql` 結果：

| Line | Code | Bug type |
|------|------|----------|
| 120 → 121 | `'…(spec §2.3 QC HIGH push back 2)'),` → `ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTHING;` | Stage 1 promote 4-row block trailing `,` |
| 143 → 144 | `'…(spec §3)'),` → `ON CONFLICT …` | Stage 2 promote 5-row block trailing `,` |
| 168 → 169 | `'…(spec §4 + [55] healthcheck)'),` → `ON CONFLICT …` | Stage 3 promote 5-row block trailing `,` |
| 184 → 185 | `'…(spec §5 第 1 列)'),` → `ON CONFLICT …` | Stage 1 rollback 1-row block trailing `,` |
| 200 → 201 | `'…(spec §5 第 2 列)'),` → `ON CONFLICT …` | Stage 2 rollback 2-row block trailing `,` |
| 217 → 218 | `'…(spec §5 第 3 列)'),` → `ON CONFLICT …` | Stage 3 rollback 2-row block trailing `,` |
| 232 → 233 | `'…(spec §5 第 4 列)'),` → `ON CONFLICT …` | Stage 4 rollback 1-row block trailing `,` |

**修法（不在本任務範圍 — PM 拍板後派下次 wave）**：
7 處 line `'…')` **,** 全去掉末尾 comma → 改成 `'…')`. 例 line 120：

```sql
-- BEFORE (broken):
    (1, 'sample_size_floor_ms', 'promote_upper', 259200000, 604800000, TRUE,
     'Stage 1 → 2 sample floor 72h (spec §2.3 QC HIGH push back 2)'),
ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTHING;

-- AFTER (correct):
    (1, 'sample_size_floor_ms', 'promote_upper', 259200000, 604800000, TRUE,
     'Stage 1 → 2 sample floor 72h (spec §2.3 QC HIGH push back 2)')
ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTHING;
```

7 處同改即可。Schema Guard A/B/C 邏輯完好不需改。

### 3.3 Step 1 transaction rollback 確認

```bash
ssh trade-core 'PGPASSWORD=… psql -h 127.0.0.1 -U trading_admin -d trading_ai -t -A -F"|" \
  -c "SELECT count(*) FROM governance.canary_stage_metric_registry;"'
```

**Output**: `0`

→ ON_ERROR_STOP=on 命中 syntax error 後整 transaction rollback；governance.canary_stage_metric_registry 仍空（V080 schema 健在，無 seed）。**無 partial state**，無 corrupt risk。

### 3.4 _sqlx_migrations baseline pre-V089 (Step 4 預先驗)

```bash
SELECT version, success FROM _sqlx_migrations WHERE version >= 80 ORDER BY version DESC;
```

| version | success |
|---|---|
| 90 | t |
| 88 | t |
| 87 | t |
| 86 | t |
| 85 | t |
| 84 | t |
| 83 | t |
| 82 | t |
| 80 | t |

V81 absent（per memory: V81 ML feature schema 已退役），V89 missing as expected。

---

## 4. Step 2-5 全部 SKIP

per task spec **「任一步 FAIL → STOP + 不繼續」**：

- ❌ Step 2 idempotency 2nd run — SKIP (1st run failed)
- ❌ Step 3 sha384sum register V89 至 _sqlx_migrations — SKIP (V089 not applied)
- ❌ Step 4 全綠驗證 — SKIP (no V89 to verify)
- ❌ Step 5 seed content verify — SKIP (no seed)

任何 forward action 必先修 V089 SQL，但 task 明示 **「不改 V089 SQL 文件」** → 必須等 PM 派下次 wave 修檔 + re-dispatch。

---

## 5. 治理對照

### 5.1 SQL migration §七 規範違規確認

**V089 違反 CLAUDE.md §七 Idempotency 強制條款**：
> 「每個 migration 本地跑兩次 `psql -f V<NNN>__<desc>.sql`，第二次必須不 RAISE」

W5-E1-A IMPL report §7.4 自承：
> 「Mac 環境無 PG service…本 sub-agent 完成 SQL static review…但未 runtime verify」

→ Static review 不能 catch PG INSERT VALUES trailing comma syntax，因為 SQL 在 Mac 上沒 PG parser 跑得起來。**這正是 `feedback_v_migration_pg_dry_run.md` 教訓的覆蓋場景**：Mac mock + static-parse review 絕對不夠，必先 Linux PG empirical run。

### 5.2 §三 sign-off invariant 違規

W5-E1-A IMPL report §3 Acceptance 表把 #4 (Python evaluator cross-language verification) 標 🟡，#6 (boundary_violation_count source list 對齊) 標 🟡，#7 (E4 5×5 transition matrix) 標 🟡 — 但 #3 (V089 seed ≥12 row) 標 ✅ Done **錯誤** — 因為 V089 從未在 Linux PG 跑過，acceptance #3 根本未驗證。

E1 sub-agent IMPL report §8.3 PM 確認點 [x] commit + push 完成 (6529e37e) — `commit + push` 的事實正確，但「IMPL DONE」status 應為 **「IMPL DONE pending V089 PG dry-run」**，不應在 dry-run 前標 ✅ acceptance #3 Done。

→ 建議 PM 在派下次修檔 wave 同時要求 W5-E1-A IMPL report acceptance 表 #3 改回 🟡。

### 5.3 16 原則合規

無觸碰。本任務純 SQL apply attempt，無 code 改動，無下單路徑、無 authority manipulation、無 secret 操作。

### 5.4 硬邊界 5 項

無觸碰。

---

## 6. 不確定處 / D+1+ 注意事項

### 6.1 修檔範圍 — 純 SQL syntax fix（推薦）

**最小影響修法**：7 處 trailing comma 刪掉，**不動任何 INSERT data / Guard logic / Final NOTICE block**。建議派 E1 wave 修檔 + 同次 dispatch sub-agent 重跑 dry-run。

**不該擴大範圍**（per CLAUDE.md §八「最小影響」）：
- ❌ 不重構 INSERT block 為 single mega-INSERT（W5-E1-A IMPL §4.5 已 rationale 解釋 4 block 設計）
- ❌ 不改 ON CONFLICT clause 寫法（partial unique index conflict target 對齊 V080 設計）
- ❌ 不改 description text / threshold value（spec §2-§5 byte-identical）

### 6.2 Multi-session / V089 file ownership

V089 file 上次 commit 是 `6529e37e` (W5-E1-A 同 commit)，無中間其他 session 改過。修檔可直接 edit + commit + push 不需 worry merge race。

### 6.3 deploy gating

OPENCLAW_AUTO_MIGRATE=0 (sign-off 時暫關保 V089 NOT_RUN per design) **不需翻**。修檔後手動 `psql -f` 跑 dry-run 即可。auto-migrate flip 留給 PM 統一決定。

### 6.4 W3 cohort SQL pipeline 對齊（W5-E1-A spec §9 重點 1）

V089 修好 + apply 之後，[58a] healthcheck 才能跑 V089 seed coverage drift detection。但 W5-E1-A spec §9 重點 1（W3 cohort SQL pipeline byte-identical with V089 SQL）仍是 D+1 dispatch acceptance gate；本任務只解 V089 apply 阻塞，不替代 W3 cross-language verification。

### 6.5 sha384sum register pattern 預備（修檔後可立即用）

```bash
# Step 3 register V89 — 修檔 + dry-run pass 後直接跑此命令
ssh trade-core 'CHECKSUM_V89=$(sha384sum /home/ncyu/BybitOpenClaw/srv/sql/migrations/V089__governance_canary_stage_metric_seed.sql | awk "{print \$1}") && \
  PG_PASS=$(awk -F= "/^POSTGRES_PASSWORD=/{print \$2}" /home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env) && \
  PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -U trading_admin -d trading_ai \
  -c "INSERT INTO _sqlx_migrations (version, description, installed_on, success, checksum, execution_time) \
      VALUES (89, '"'"'governance canary stage metric seed'"'"', now(), TRUE, decode('"'"'$CHECKSUM_V89'"'"', '"'"'hex'"'"'), 0) \
      ON CONFLICT (version) DO NOTHING;" 2>&1 | tail -3'
```

注意：**checksum 必在修檔之後**算，因為修檔會改 sha384sum hash。修檔前先 dry-run 兩次 PASS 才 register checksum，避免 P0 sqlx hash drift incident（per `memory/project_2026_05_02_p0_sqlx_hash_drift.md`）。

---

## 7. Operator 下一步 / 給 PM 的 push back

### 7.1 PM 拍板選項

| 選項 | 動作 | 預期時間 |
|------|------|---------|
| **A** | 派 E1 wave **修 V089 7 處 trailing comma** + 同次 dispatch 重跑 dry-run + register | ~30 min |
| **B** | 將 V089 標為 **broken**，撤銷 W5-E1-A acceptance #3 ✅，要求 W5-E1-A re-IMPL with proper Linux PG dry-run gate before claiming IMPL DONE | ~重派 1-2h |
| **C** | 暫掛 V089 不修，[58a] healthcheck 永遠 WARN-on-V089-not-seeded（per IMPL §4.4 verdict-preserving 設計），等 W3 整合 wave 一併處理 | 0 min（風險: [58a] 永遠 WARN）|

**E1 推薦 A**：最小影響 + 解阻塞 + 不浪費 W5-E1-A 已 land 的其他組件（Rust pure-logic + Python evaluator + healthcheck + AMD）。修檔 7 處 trailing comma 屬 純 SQL syntax 修，不改 V080/spec/AMD/IMPL 任何設計決策。

### 7.2 sub-agent IMPL DONE adversarial review SOP 提醒

per `memory/feedback_impl_done_adversarial_review.md`：
> 「高風險 IMPL（GUI / IPC / 寫操作 / 共用 helper）sub-agent 自評 IMPL DONE 不接受單獨 sign-off；強制派 A3+E2 並行核驗」

W5-E1-A 屬 **DB schema 寫操作 + 共用 SQL migration**（高風險），但 IMPL DONE 後 **直接 commit + push** 沒派 A3+E2 並行核驗 → V089 syntax bug 漏網。建議 PM future SOP：

- DB migration IMPL 必有 Linux PG dry-run 通過才標 IMPL DONE（不只 cargo + pytest PASS）
- A3 並行驗 SQL syntax + ON CONFLICT pattern + Guard A/B/C 完整性

### 7.3 PM 確認點

- [ ] 拍板選項 A/B/C
- [ ] 若 A：派 E1 wave 修 7 處 trailing comma + dispatch 重跑此 dry-run + register 任務
- [ ] 若 B：撤銷 W5-E1-A acceptance #3 ✅；要求 IMPL DONE SOP 明文加 Linux PG dry-run gate
- [ ] 若 C：documented [58a] WARN tolerance + W3 wave 拍板時整合處理

### 7.4 unrelated WIP 通報

Mac 本地 working tree 有 unrelated unstaged WIP：
- `layer2_*.py` / `provider_*.py` / `tab-ai.html` modified
- `provider_model_catalog.py` / `provider_pricing_catalog.py` / `test_provider_keys_store.py` untracked

**未碰** — 與 V089 task 無關。屬其他 wave 流動工作。

---

## 8. 報告 commit

無 code 改動 — 只有本 report 寫入 `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--v089_dry_run_apply.md`。

**E1 SUB-AGENT 不主動 commit report**（per CLAUDE.md §七 鏈 E1→E2→E4→PM）。等 PM 拍板選項 A/B/C 後統一處理。

---

**E1 IMPLEMENTATION DONE: STEP 1 FAIL — V089 SQL syntax error，7 處 trailing comma，0 row inserted（transaction rollback），Step 2-5 全 SKIP，等 PM 拍板（推薦選項 A 派修檔 wave）**

**Report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--v089_dry_run_apply.md`**

**Critical reproduce**:
```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && PGPASSWORD=… psql -h 127.0.0.1 -U trading_admin -d trading_ai -v ON_ERROR_STOP=on -f sql/migrations/V089__governance_canary_stage_metric_seed.sql'
# → ERROR:  syntax error at or near "ON" (line 121)
```
