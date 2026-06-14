# MIGRATION-TREE-1 — V005/V023 前向相容實作報告

- 日期：2026-06-14
- 角色：E1（Backend Developer）
- 狀態：IMPL DONE，待 E2 審查
- 改檔：`sql/migrations/V005__indexes_views.sql`、`sql/migrations/V023__model_registry.sql`（僅此兩檔）

## 任務摘要

照已 scratch-驗證的 PA 設計，使 V005 / V023 在 virgin DB（全新部署，無 V004 預留 legacy 表/stub）與 brownfield（既有部署）皆可前向相容遷移：

1. V005 PART4 的 5 個 legacy-bridge Grafana view 在 virgin DB（無 `*_legacy` base 表）時必須跳過建立，否則 CREATE VIEW 因 base 表缺失失敗、阻斷遷移鏈。
2. V023 在 V004 預留的空 legacy `model_registry` stub（有 `model_name`、無 `canary_status`）存在時自癒（drop 空 stub 讓新 shape 建起），但非空 legacy 絕不 drop（真-drift 仍交 Guard A RAISE）。

## 修改清單

### V005__indexes_views.sql（PART 4）
把 5 個 `FROM public.*_legacy` 的 view 各包進 `DO $WRAP$ ... IF EXISTS(...) THEN EXECUTE $VV$ ... $VV$; END IF; END $WRAP$;` 條件守衛：
- `public.account_snapshots`（FROM account_snapshots_legacy）
- `public.system_health`（FROM system_health_legacy）
- `public.paper_pnl_snapshots`（FROM paper_pnl_snapshots_legacy）
- `public.risk_events`（FROM risk_events_legacy）
- `public.learning_events`（FROM learning_events_legacy）

未動的 6 個 PART4 view（`position_snapshots`/`order_events`/`trade_executions`/`ai_cost_events`/`observer_verdicts`/`market_tickers`）指向 `trading.*`/`agent.*`/`market.*` 新 schema 表（非 legacy），不在設計範圍。

巢狀 dollar-quote tag `$WRAP$`/`$VV$` 經全庫 grep 確認唯一、不與 V005 既有 PART3 的裸 `$$ DO` block 撞號。

### V023__model_registry.sql（Schema Guard A 之前）
在 Guard A DO block 前插入 self-heal DO block：
- 偵測 legacy shape：`information_schema.columns` 有 `model_name` AND 無 `canary_status`。
- 動態 `EXECUTE 'SELECT count(*) FROM learning.model_registry' INTO v_legacy_rows`。
- 僅 `v_legacy_rows = 0`（空 stub / 虛擬產物）才 `DROP TABLE learning.model_registry`，讓下方既有 `CREATE TABLE IF NOT EXISTS` 建新 shape。
- 非空 legacy 不 drop → 續走 Guard A，按既有邏輯 RAISE，由 operator 人工裁決（避免誤刪真實資料）。

## 關鍵 diff

V005（每個 legacy view 同構，以 account_snapshots 為例）：
```sql
DO $WRAP$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'public' AND table_name = 'account_snapshots_legacy') THEN
        EXECUTE $VV$
            CREATE OR REPLACE VIEW public.account_snapshots AS
            SELECT id, ts, total_equity, available_balance, used_margin,
                   unrealized_pnl, account_type, coin, raw_json
            FROM public.account_snapshots_legacy;
        $VV$;
    END IF;
END $WRAP$;
```

V023 self-heal：
```sql
DO $$
DECLARE
    v_legacy_rows BIGINT;
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='learning' AND table_name='model_registry' AND column_name='model_name')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='learning' AND table_name='model_registry' AND column_name='canary_status')
    THEN
        EXECUTE 'SELECT count(*) FROM learning.model_registry' INTO v_legacy_rows;
        IF v_legacy_rows = 0 THEN
            DROP TABLE learning.model_registry;
        END IF;
    END IF;
END $$;
```

## Self-test（驗到哪層）

本機 PostgreSQL 16.13 (Homebrew) ephemeral scratch cluster（`initdb --locale=C -E UTF8`，port 54399，trust auth）。**真 PG 執行**而非語法 dry-parse。每個 scenario 在獨立 DB、預置精確前置狀態後執行被改片段：

| Scenario | 前置 | 結果 | 預期 | 判定 |
|---|---|---|---|---|
| V005-A virgin | 無 `*_legacy` 表 | 0 view 建立、無錯誤 | 跳過 | PASS |
| V005-A 冪等 | 同上再跑一次 | 無錯誤 | 冪等 | PASS |
| V005-B brownfield | 5 個 `*_legacy` 表（精確欄位）存在 | 5 view 建立、可 SELECT | 全建 | PASS |
| V005-B 冪等 | 同上再跑一次（CREATE OR REPLACE） | 無錯誤 | 冪等 | PASS |
| V023-C virgin | 無 model_registry | 新 shape 建立（canary_status=1 欄） | 新 shape | PASS |
| V023-D 空 legacy | model_name + 無 canary_status + 0 row | drop+重建：canary_status=1、model_name=0 | 自癒 | PASS |
| V023-E 非空 legacy | legacy shape + 1 真實 row | NOT drop（row 保留=1、仍 legacy shape）+ Guard A RAISE | 不刪+RAISE | PASS |
| V023 冪等（新 shape） | 已是新 shape 再跑 | no-op（self-heal 跳過、CREATE IF NOT EXISTS no-op） | 冪等 | PASS |
| V023 冪等（virgin） | virgin 雙 apply | 0 row、表完整 | 冪等 | PASS |

cluster 跑完即拆除（`pg_ctl stop -m immediate` + rm scratch 目錄與 temp SQL）。

**驗證層級**：真 PG DDL 執行 + 行為斷言（view 計數、欄位存在性、row 保留、Guard A 字串匹配、雙 apply 冪等）。未跑 Linux prod（鐵律：僅改檔 + scratch 驗，不 apply prod）。

## 治理對照

- 硬邊界：`grep` 確認兩檔 0 個 `max_retries`/`live_execution_allowed`/`execution_authority`/`system_mode` token。未碰。
- V004 未改（`grep` 確認無 self-heal 字串注入）。
- Guard A/B/C：本任務不新增 migration、不新增 `CREATE TABLE`，只在既有 V023 既有 Guard A 前加 self-heal（self-heal 本身就是 brownfield 安全前置，不替代 Guard A — 非空 legacy 仍由 Guard A RAISE）。
- 註釋：新增註釋全中文，僅保留 SQL/schema 技術識別字（`canary_status`/`model_name`/表名）為英文，符合 bilingual-comment-style 正本。
- checksum：改 V005/V023 字節必致 sqlx migration checksum drift（已知）。conductor 在 push 後跑 `repair_migration_checksum`。
- 未 commit（強制鏈 E1→E2→E4→QA→PM）；未 apply prod。

## 小決策（自行擇一，已註明理由）

- V023 self-heal 用 `BIGINT v_legacy_rows` + `EXECUTE ... INTO`（設計指定動態 EXECUTE）取代我初版誤寫的非法 `EXECUTE_count :=` 內聯賦值。理由：plpgsql 無此語法；設計明文要求 `EXECUTE 'SELECT count(*) ...'`，動態避免 cold-parse 階段 planner 硬綁此表。

## 不確定之處

- 本任務只 scratch 驗了兩個被改片段在各前置狀態下的行為，未在 Linux 上跑完整 V001..V023 遷移鏈。設計屬 PA 已 scratch-驗證，E4 回歸建議在 Linux 對完整鏈做一次 virgin（全新 DB）+ brownfield（既有 trading_ai）雙 apply 確認 checksum repair 後遷移仍綠。
- V005-B 測試用的 5 個 legacy 表是我按 view SELECT 欄位構造的最小 schema（非真 V004/init_trading_schema.sql 原表）；欄位名/型別足以驗 view 建立與可查，但真 prod legacy 表的完整欄位由既有部署決定（view 只 SELECT 子集，無相容性風險）。

## Operator / 下一步

1. E2 對抗審查兩檔 diff（重點：dollar-quote tag 不撞號、self-heal 非空不 drop 鐵則、5/5 view 覆蓋）。
2. E4 Linux 回歸：完整遷移鏈 virgin + brownfield 雙 apply + checksum repair。
3. QA / PM：通過後 conductor 統一 commit + push，push 後跑 `repair_migration_checksum`。
