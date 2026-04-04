# SQL Migrations / SQL 遷移

## 命名規範 / Naming Convention

```
V{NNN}__{description}.sql
```
- `V` prefix + 3-digit version number
- Double underscore `__` separator
- Snake_case description
- Example: `V001__create_schemas.sql`

## 文件清單 / File List

| File | Content | Status |
|------|---------|--------|
| `V001__create_schemas.sql` | CREATE 8 schemas (market, trading, agent, learning, features, observability, risk, news) | DRAFT |
| `V002__market_tables.sql` | market.* tables (tickers, ob, trade_agg, klines, funding, OI, LSR, liq, regime, news) + hypertable | DRAFT |
| `V003__trading_agent_tables.sql` | trading.* + agent.* tables | DRAFT |
| `V004__learning_features_obs_risk_news_tables.sql` | learning.* + features.* + observability.* + risk.* tables | DRAFT |
| `V005__indexes_views.sql` | All indexes + scorer_training_features VIEW + legacy rename + Grafana VIEW bridge | DRAFT |

## 執行方式 / Execution

### 手動執行（Phase 0a）/ Manual Execution (Phase 0a)

```bash
# 備份 / Backup first
pg_dump -U trading_admin -d trading_ai -F c -f backup_pre_migration.dump

# 依序執行 / Execute in order
for f in V001 V002 V003 V004 V005; do
  psql -U trading_admin -d trading_ai -f sql/migrations/${f}__*.sql
done
```

### 驗證 / Verification

```sql
-- 確認 8 個 schema / Verify 8 schemas
SELECT schema_name FROM information_schema.schemata
WHERE schema_name IN ('market','trading','agent','learning','features','observability','risk','news')
ORDER BY schema_name;

-- 確認所有表 / Verify all tables
SELECT schemaname, tablename FROM pg_tables
WHERE schemaname IN ('market','trading','agent','learning','features','observability','risk','news')
ORDER BY schemaname, tablename;
```

## 設計來源 / Design Sources

- 融合方案 v0.5: `docs/references/2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md`
- DB 架構 V1: `docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md`
- DB 設計: `docs/references/2026-04-03--data_storage_architecture_optimal_draft_v0.1.md`
- 執行計劃 V1: `docs/references/2026-04-04--execution_plan_v1.md`

## 注意事項 / Notes

- TimescaleDB hypertable 語句用 `DO $$ ... IF EXISTS timescaledb ... END IF; END $$;` 包裹，無 TimescaleDB 環境不會報錯
- PRIMARY KEY 包含時間列（TimescaleDB 要求）
- Hypertable FK 不受支持，改用應用層 CHECK + 文檔化邏輯 FK
- 現有 public schema 11 表 + trading_raw schema 5 表加 `_legacy` 後綴
- Grafana VIEW 橋接確保 Dashboard 不中斷
