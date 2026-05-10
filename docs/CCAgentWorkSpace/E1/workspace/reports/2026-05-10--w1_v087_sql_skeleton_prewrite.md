# E1 — W1 V087 panel.oi_delta_panel SQL skeleton 預寫

**日期**：2026-05-10
**性質**：W1 W-AUDIT-8a Phase B Tier 2 collector OI delta panel SQL skeleton；NOT_RUN artifact，D+1 IMPL 階段 Linux PG dry-run + verify + deploy
**對應 wave**：Sprint N+1 D+0 pre-dispatch readiness — W1 sibling V085 funding_curve / V087 oi_delta_panel（本檔）/ V088 btc_lead_lag_panel
**前置**：
- W1 PA spec v1.1 (WS-first revision) `srv/docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md` §3
- 對齊 trait typedef `srv/rust/openclaw_core/src/alpha_surface.rs:159-175` `OIDeltaPanel`
- Sister V086 NOT_RUN 模板 `srv/sql/migrations/V086__governance_reject_close_reason_code.sql` (commit `87da03b7`)
- Guard 模板 `srv/sql/migrations/templates/schema_guard_template.sql`
- TimescaleDB extension guard pattern V002 line 179-185

---

## §1 任務摘要

預寫 V087 SQL migration skeleton，建 `panel.oi_delta_panel` TimescaleDB hypertable + 14d retention + hot-path index + Guard A/B/C 三層完整保護，作為 W1 W-AUDIT-8a Phase B B-2 OI delta panel aggregator 的 PG schema artifact。D+1 W1 IMPL 階段 Rust `panel_aggregator/oi_delta.rs` 直接寫此 table（雙寫 PG + Rust slot），無需 E1 從零寫 SQL。

PA hint 預期 ~150 LOC，實際 374 LOC（多出來在完整 Guard B 5 個 type check + 7 個 COMMENT ON COLUMN + final NOTICE block，皆為治理紅線層需要）。

## §2 修改清單

| Path | LOC | Status |
|---|---|---|
| `srv/sql/migrations/V087__panel_oi_delta_panel.sql` | 374 | NEW · COMMITTED `326dab49` · PUSHED to origin/main · NOT_RUN |
| `srv/docs/CCAgentWorkSpace/E1/memory.md` | +30 (教訓 11/12 + 工具偏好) | MODIFIED |

無既有 V### migration 修改。無 Rust / Python 改動。

## §3 關鍵 diff（V087 結構摘要）

```sql
BEGIN;

-- §1 CREATE SCHEMA IF NOT EXISTS panel
CREATE SCHEMA IF NOT EXISTS panel;

-- Guard A: panel.oi_delta_panel 既存 shape 對齊驗證 (7 column)
DO $$ ... RAISE EXCEPTION 'V087 Guard A FAIL: ...' ... END $$;

-- §2 CREATE TABLE IF NOT EXISTS panel.oi_delta_panel (
CREATE TABLE IF NOT EXISTS panel.oi_delta_panel (
    snapshot_ts_ms      BIGINT           NOT NULL,
    symbol              TEXT             NOT NULL,
    oi_delta_5m_pct     DOUBLE PRECISION,
    oi_delta_15m_pct    DOUBLE PRECISION,
    oi_delta_1h_pct     DOUBLE PRECISION,
    oi_abs              DOUBLE PRECISION NOT NULL,
    source_tier         TEXT             NOT NULL DEFAULT 'bybit_v5_public',
    PRIMARY KEY (snapshot_ts_ms, symbol)
);

-- Guard B: 5 個 type check (3 delta_pct + oi_abs + snapshot_ts_ms canonical type)
DO $$ ... 5 column type checks ... END $$;

-- §3 TimescaleDB hypertable + 14d retention (extension-guarded for non-Timescale env)
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('panel.oi_delta_panel', 'snapshot_ts_ms',
        chunk_time_interval => 86400000, if_not_exists => TRUE);
    PERFORM add_retention_policy('panel.oi_delta_panel',
        INTERVAL '14 days', if_not_exists => TRUE);
END IF;
END $$;

-- §4 Hot-path index
CREATE INDEX IF NOT EXISTS idx_oi_panel_ts_desc_symbol
    ON panel.oi_delta_panel (snapshot_ts_ms DESC, symbol);

-- Guard C: index column list 比對 'snapshot_ts_ms DESC' + 'symbol'
DO $$ ... pg_get_indexdef substring check ... END $$;

-- §5 COMMENT ON TABLE + 7 COMMENT ON COLUMN

COMMIT;

-- §6 Final NOTICE block (post-COMMIT, operator runbook)
DO $$ BEGIN RAISE NOTICE 'V087 land complete:' ... END $$;
```

## §4 治理對照

| 項目 | Status | 證據 |
|---|---|---|
| CLAUDE.md §七 SQL migration Guard A/B/C 強制 | PASS | Guard A (table shape) + Guard B (5 column type) + Guard C (index column list)；對應 schema_guard_template.sql 三層 |
| CLAUDE.md §七 idempotency 強制 | PASS | 全 DDL `IF NOT EXISTS` (SCHEMA / TABLE / INDEX) + hypertable & retention `if_not_exists => TRUE` + extension guard wrap；連跑兩次第二次必 no-op |
| CLAUDE.md §七 Linux PG dry-run mandatory | DEFERRED | D+1 W1 IMPL phase 必跑 Linux PG `psql -f V087...sql` 驗 hypertable + retention 實 land + 連跑 idempotency；Mac mock pytest 不夠（per `feedback_v_migration_pg_dry_run` 2026-05-05 V055 5-round 教訓）|
| CLAUDE.md §七 注釋默認中文 | PASS | 新檔注釋默認中文（per `feedback_chinese_only_comments` 2026-05-05），canonical SQL keyword + technical name 仍英文（`text` / `bigint` / `double precision` 等規範名必小寫對齊 PG `information_schema.columns.data_type`）|
| CLAUDE.md §七 跨平台兼容 | PASS | extension guard 包 hypertable + retention，Mac mock pytest 環境無 timescaledb extension 也能 land；無 user-home 硬編碼路徑 |
| CLAUDE.md §九 文件 800 行警告 | PASS | 374 LOC，遠在 800 警戒線下 |
| 不擴大 PA spec 範圍 | PASS | 對齊 W1 spec v1.1 §3.2 schema 6 column，無順手優化 |
| 不修既有 V### migration | PASS | 純新建 V087 file |
| Sibling pattern 對齊 | PASS | `CREATE SCHEMA IF NOT EXISTS panel` 一行對齊 W1 spec snippet + 並行 V088 author teaching 9 一致；不繞回 V086 DO block 包裝風格 |
| Trait typedef alignment | PASS | 7 column 1:1 mapping `OIDeltaPanel.{symbols, oi_delta_5m_pct, oi_delta_15m_pct, oi_delta_1h_pct, oi_abs, snapshot_ts_ms, source_tier}` (alpha_surface.rs:165-175) |

### E2 self-review 35 點 adversarial check

PASS 34 / FALSE-ALARM 1（`if_not_exists => TRUE` 字串計數含 comment 引用，實際 DDL 呼叫 2 個 hypertable + retention 各 1 正確）。詳見 `python3 << 'EOF' ... EOF` 內聯 script output（不存盤）。

## §5 不確定之處 / D+1 IMPL 階段需 E2 review 補充

1. **chunk_time_interval = 1 day (86400000 ms) 是否合理**：對齊 W1 spec §3.2 + 並行 V085 funding_curve sister 統一 1d chunk。25 sym × 1440 row/day × 60s flush = 36000 row/day chunk。若 D+1 dry-run 實測 chunk 過大（PG TimescaleDB 默認 chunk size 警告 ~25M row），需縮短至 6h chunk（21600000 ms）。建議 D+1 IMPL phase 跑 1 個 dry-run 驗 chunk 行為再決。

2. **PRIMARY KEY 順序 (snapshot_ts_ms, symbol)**：snapshot_ts_ms 在前因 TimescaleDB partition column 必在 PK 內。Rust IPC slot pull 時 GROUP BY 最新 snapshot_ts_ms 構造 `Vec<symbol>` 並對齊 `Vec<oi_delta_*_pct>` — 此 query pattern 仰賴 (snapshot_ts_ms DESC, symbol) hot-path index。E2 必驗此 query plan。

3. **source_tier 預設 'bybit_v5_public'**：W1 spec §3.2 預設值。後續 W-AUDIT-8d hybrid source 上線（WS 持續 + REST 5min 加固）後可寫 'bybit_v5_ws_tickers' / 'bybit_v5_rest_open_interest' 區分；當前 V087 不 enforce CHECK constraint（為 W-AUDIT-8d 預留 enum 加固餘地）。

4. **Linux PG dry-run mandatory**（per `feedback_v_migration_pg_dry_run` 2026-05-05）：本 file Mac sqlparse 結構驗證 17 statement parse + 5 DO block 對稱 + 35 點 adversarial check 34 PASS — 但 Mac 不裝 timescaledb extension，hypertable + retention path 從未真跑。D+1 W1 IMPL phase 必跑 Linux PG empirical query + `psql -f V087...sql` 兩次驗 idempotency + healthcheck `[58]` 加 panel.oi_delta_panel freshness query。

## §6 Operator 下一步

1. **PM 21:30 UTC sign-off**：審本 V087 SQL skeleton + 對照 W1 PA spec v1.1 §3 OI delta panel + 對照 alpha_surface.rs:159-175 trait typedef + 確認 V085/V087/V088 三 sibling SCHEMA pattern 一致

2. **Sign-off PASS 後 D+1 W1 IMPL phase**：
   - E1 Linux PG dry-run V087 (跑兩次驗 idempotent + 確認 hypertable + retention 真 land)
   - E1 IMPL Rust `panel_aggregator/oi_delta.rs`（cold-start REST batch backfill + WS broadcast subscribe + 60s flush 雙寫 PG + slot）
   - E1 IMPL `slots.rs` `OIDeltaPanelSlot` late-injection（PA D+0 anchor line 174）
   - E1 IMPL `step_4_5_dispatch` wire（slot read → AlphaSurface.oi_delta_panel borrow → bb_breakout consume）
   - E1 IMPL bb_breakout `on_tick` 真實 consume `surface.oi_delta_panel` (B-4 E1-γ)
   - E1 加 healthcheck `[58]` PG-side panel.oi_delta_panel freshness (30s WARN / 300s FAIL per spec §3.4)
   - E2 review (Guard A/B/C 完整性 + chunk size 實測 + slot late-injection thread safety + bb_breakout fail-closed 真實 wire)
   - E4 regression test
   - PM commit + deploy

3. **D+5-D+6 W1 IMPL land deadline**（per spec §1 schedule）

---

## §7 多 session race transparent disclosure（incident 報告）

**事故**：本任務 commit 步驟我用 `git add sql/migrations/V087... && git commit -m "..."` 而非 `git commit --only sql/migrations/V087... -m "..."`。並行 V088 author（W2 sub-agent）剛好也在 stage V088，於是我的 commit `326dab49` 被 swept 進 V087 + V088 兩 file +796 LOC（非我所願）。

**事後**：
- sandbox 主動拒絕 `git reset --soft HEAD~1`（理由：rewrites local history that bundled WIP, violates multi-session race protocol） — **正確 fail-safe**，我未強推 undo
- V088 author 後續又 push 了 PM sign-off DRAFT commit `8f4147bb`，origin/main 已含 V087 + V088 + PM 三 commit
- V087 內容本身正確且 in origin/main；V088 是合法 NOT_RUN skeleton（並行 author 後續 polish diff 也合理）；事故無 data loss / 無治理破壞，僅破「一 commit = 一 author = 一 task」原則

**Root cause**：`git add <file>` 確實只 stage 該 file，但 `git commit -m` 不接 pathspec 時 commit 整個 staging area。並行 author 此前已 stage V088 在 staging area。

**正確 SOP**（補入 E1 memory 教訓 11，擴展 `feedback_git_commit_only_for_metadoc.md` 範圍從 meta-doc 到 sql/migrations/ 同 wave 並行）：
```
git commit --only sql/migrations/V<NNN>__<desc>.sql -m "..."
```

**對 PM 的建議**：sign-off 階段 review commit `326dab49` 含 V087 + V088 兩 file 是 race 結果，非 V087 author（我）有意 bundle。V088 sign-off 由並行 V088 author（教訓 8/9/10 寫入 E1 memory）負責。

---

## §8 NOT_RUN 標記

- **COMMITTED**: V087 + bundled V088 已 in commit `326dab49`，已 push 到 origin/main（非我自己 push，由並行 author 接 PM sign-off DRAFT commit `8f4147bb` 一併 push）
- **NOT_DEPLOYED**: 未跑 `psql -f V087__*.sql`，無 DB schema 改動
- **NOT_RUN**: 無 `cargo test` / 無 `pytest` / 無任何 runtime exec
- **PM sign-off 條件**: 等 21:30 UTC HIGH-5 12h watch sign-off 窗口；PM 對照本 report + V087 file 內容 + W1 PA spec v1.1 §3 + trait typedef 三方做最後 verdict

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w1_v087_sql_skeleton_prewrite.md）
