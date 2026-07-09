# MIT DB Schema Audit — V115 panel.basis_panel · 2026-05-29

**Task**: P2-BASIS-PANEL-INFRA V115 migration hard-gate — 撰寫 V115 + Linux PG empirical double-apply dry-run
**Spec**: `docs/execution_plan/specs/2026-05-29--basis-panel-infra-spec.md`（PA design, CHEAP-DERIVED）
**Worktree**: `/Users/ncyu/Projects/TradeBot/wt-basis`（branch `feature/basis-panel-infra`, base HEAD d2bbc79a）
**V115 SQL**: `/Users/ncyu/Projects/TradeBot/wt-basis/sql/migrations/V115__panel_basis_panel.sql`（430 行）
**Verdict**: **PASS — ready for E1 writer IMPL**

---

## (1) V115 SQL 路徑 + Schema

`panel.basis_panel`（mirror V085 funding_rates_panel + V087 oi_delta_panel）

| column | type | null | 語義 |
|---|---|---|---|
| snapshot_ts_ms | BIGINT | NOT NULL | flush 時戳 ms epoch；hypertable time col |
| symbol | TEXT | NOT NULL | cohort sym |
| perp_last_price | DOUBLE PRECISION | NOT NULL | basis 分子 = last_price（非 mark_price） |
| index_price | DOUBLE PRECISION | NOT NULL | basis 分母（writer index>0 才寫 row） |
| basis_pct | DOUBLE PRECISION | NOT NULL | (last/index-1)*100 **SIGNED**（consumer 取 abs） |
| source_tier | TEXT | NOT NULL DEFAULT 'bybit_v5_ws_tickers' | provenance |

- **PK** (snapshot_ts_ms, symbol)
- **Hypertable**: snapshot_ts_ms BIGINT epoch ms 軸, chunk 1d (86400000 ms)
- **integer_now_func**: panel.unix_now_ms()（V085 已建；CREATE OR REPLACE idempotent）
- **Retention**: 14d (BIGINT 1209600000 ms)；對齊 sister V085/V087/V088 統一 14d
- **Compression**: 無（sister 皆無 add_compression_policy → surgical，per spec §3.1）
- **Index**: idx_basis_panel_ts_desc_symbol (snapshot_ts_ms DESC, symbol) + basis_panel_snapshot_ts_ms_idx (snapshot_ts_ms DESC)
- **不存 mark_price**（WS parser 不解析 + 非 basis 輸入 → 不引入死 column）
- **無 engine_mode column**（market 共享平面，對齊 sister panel）
- Guard A（CREATE TABLE shape check）/ Guard B（4 type check）/ Guard C（index col check）完整

## (2) Linux PG dry-run 結果（ssh trade-core, trading_ai, BEGIN/ROLLBACK double-apply）

Pre-audit: TimescaleDB 2.26.1；basis_panel 不存在；panel.unix_now_ms 已存在；max_migration=114（V115 FREE）。

| 維度 | 結果 | 證據 |
|---|---|---|
| Guard A (CREATE TABLE IF NOT EXISTS) | **PASS** | 6 col 全 NOT NULL，型別/順序對齊 spec |
| Hypertable (snapshot_ts_ms BIGINT 軸) | **PASS** | is_hypertable=1, chunk_interval=86400000 (1d) |
| **double-apply idempotency** | **PASS** | APPLY 2 全 NOTICE-skip（schema/table/hypertable/retention/index "already exists, skipping"），**0 RAISE**（V083/V084 gold pattern） |
| compression | **N/A by design** | sister 皆無；spec「無則不加」surgical |
| retention (14d) | **PASS** | jobs.config drop_after=1209600000 (14d) |
| integer_now_func | **PASS** | dimension integer_now_func=unix_now_ms |
| hot-path index | **PASS** | 3 index（PK + ts_desc_symbol + ts_ms_idx），Guard C col check 通過 |
| boundary index≤0 不寫 row | **PASS（schema 不需 CHECK）** | NOT NULL on index_price = 契約底線；MIT 裁決不加 CHECK(index_price>0)（writer skip 已 fail-closed；CHECK 會讓 batch flush 一條違反全 abort 反不利；對齊 sister 無 value-range CHECK） |
| post-rollback residue | **PASS（pristine）** | basis_panel_table=0, max_migration=114 → trading_ai 未污染 |

### 關鍵 empirical finding（非 bug，Mac mock 抓不到）
`create_hypertable` auto-create `basis_panel_snapshot_ts_ms_idx` on (snapshot_ts_ms DESC)，與 spec §3.1 explicit secondary index **byte-identical** → CREATE INDEX IF NOT EXISTS 正確 no-op skip。3 sister panel 全同此 auto-index pattern。secondary index 是 redundant no-op 但無害，符合 spec 意圖。再證 Linux PG empirical mandatory（V055/V114 教訓）。

### basis 公式 parity（E2 必驗，已 grep）
strategy live `funding_short_v2/mod.rs:155-157` compute_basis_pct(perp_price=ctx.price=last_price, index_price) = `((perp/ip)-1.0).abs()*100.0`。panel 存 signed；consumer 取 ABS。分子必 = last_price 非 mark_price。

## (3) Sign-off — ready for E1 writer IMPL

**APPROVE**：V115 SQL 通過全部 hard-gate 維度。E1 在同 wt-basis 接 basis.rs + panel_aggregator wire (B-2/B-3) + a1_funding_short_metrics.py as-of LATERAL (B-4)。

### 給 E1 的 writer 注意點
1. **fail-closed**：index≤0 / 缺失 → skip（不發 INSERT、不寫 0、不寫 NULL row）；NOT NULL 是 schema 防線但整批 INSERT 違反會 abort 全 flush → writer 必先過濾
2. basis_pct 存 **signed**（不取 abs）；source_tier 顯式寫 'bybit_v5_ws_tickers'
3. **ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE**（idempotent flush）
4. cohort 用 PanelAggregator 既有 cohort_symbols（單一 SSOT；避 8b round-1 RED self-imposed scarcity）
5. **latest-value cache**：index_price 只 ~1/8 frame 帶 → 跨 frame 保 last-known（對齊 funding_curve）；從未收過 index 的 sym 不入 cache
6. sqlx checksum：dry-run 未真 apply（max_migration 仍 114）→ operator AUTO_MIGRATE 路徑正常 land 無 hash drift 風險（與 V083/V084 手動 psql -f 場景不同）
7. **無 IPC slot**（spec §6.4 #5，offline replay 不需 AlphaSurface slot）；**無 healthcheck = CLAUDE.md §七缺口** → E1 IMPL 時補 basis_panel freshness check

MIT AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-29--v115_basis_panel_dry_run.md
