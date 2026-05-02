# CLAUDE.md 2026-05-02 Pre-trim Snapshot

**Reason for archive**: Operator 要求按真實進度全景重寫 CLAUDE.md / TODO.md / README.md。本檔保留 trim 前完整內容（554 lines · ≤2026-05-01 23:17 CEST PRE-LIVE-3 deploy snapshot）。

**Trim 觸發 panorama 來源**：2026-05-02 PA + FA cold panorama audit + Decision Lease archaeology + LG-5 reviewer 0 emit MIT root cause（共 4 份 .claude_reports 級報告，未寫 .md per agent dispatch instruction，內容入主會話 transcript）。

**主要 trim 動作**：
1. §三 runtime 狀態（commit `eaf0c7e` PRE-LIVE-3 deploy snapshot）改寫為 `9726b3b` 真實狀態 + 18-blocker 矩陣
2. §五 架構圖加 Decision Lease 路徑 A 待 retrofit 註腳（Rust `acquire_lease()` facade + router gate 待補；R-03 last-mile 漏做）
3. §七 V023 4-條 Guard 詳述 / Engine 自動遷移 opt-in 詳述 / 被動等待 healthcheck 4-條規則 → 各保留 2-3 行入口 + 詳述移本檔
4. §九 Singleton 表後 5 條長注釋（H_STATE_INVALIDATOR / scanner_wiring / HStateCacheSlot / CostEdgeAdvisorDbSlot / Lg5ReviewConsumer 等）→ 收成單行
5. §十一「一句話狀態」直接刪（已被 §三 替代）

---

# 原 CLAUDE.md（2026-05-01 23:17 CEST · 554 lines · commit `eaf0c7e` PRE-LIVE-3 snapshot）

> 完整內容見 git history `git show 9726b3b:CLAUDE.md`（trim 前最後一個 commit 是 5abb00e；但 9726b3b HEAD 上 CLAUDE.md 仍未變動）。
> 詳述章節見以下節錄：

## §七 V023 silent no-op postmortem 4 條 Guard 規則（trim 前完整版）

**背景**：2026-04-23 `V023__model_registry.sql` 入 repo 但在 Linux 上**靜默 no-op** —— V004 早已預建了缺 `canary_status/verdict` 的 legacy `learning.model_registry` stub；`CREATE TABLE IF NOT EXISTS` 看到表存在就跳過，下游 Rust 讀 `canary_status` 全空。`helper_scripts/db/audit_migrations.py` 事後才能抓到。**更好的防線是 migration 內的 DO block guard，對 legacy drift 主動 RAISE**。

**規則**（4 條，E2 必查）：
1. **Guard A 強制**：任何 `CREATE TABLE IF NOT EXISTS schema.table (...)` **前必加**一個 DO block，驗表若已存在則必要欄位俱在；缺 ≥1 即 `RAISE EXCEPTION`。模板見 `sql/migrations/templates/schema_guard_template.sql § Guard A`。
2. **Guard B 強制（型別 matters 時）**：`ALTER TABLE ... ADD COLUMN IF NOT EXISTS col TYPE` 前，若該 column 類型錯會讓下游 writer 失敗，**必加** Guard B 驗 `information_schema.columns.data_type`；型別不符即 RAISE。模板同檔 § Guard B。
3. **Guard C（hot-path 索引選用）**：`CREATE INDEX IF NOT EXISTS` 若索引欄位組合關鍵（production 熱查詢依賴），加 Guard C 比對 `pg_get_indexdef()`；純 audit / 低頻索引可略。
4. **Idempotency 驗證**：每個新 migration 本地跑兩次 `psql -f V<NNN>__<desc>.sql`，第二次必須**不 RAISE**（shape 已正確時 guard no-op）。違反 = E2 打回。
5. **範例** retrofit：`sql/migrations/V023__model_registry.sql`（Guard A `learning.model_registry`）+ `sql/migrations/V021__fills_exit_source.sql`（Guard A `learning.decision_shadow_exits` + Guard B `trading.fills.exit_source` + Guard B `learning.decision_shadow_exits.ts`）。新 migration 以此兩檔為 reference。

**測試**：`sql/migrations/tests/test_schema_guards.sql` 提供 9 個單測（3 guard × {pass / fail / no-op}），無 pgTAP infra 下直接 `psql -d <test_db> -f` 跑；grep NOTICE 無 `FAIL` 即綠。

**2026-05-02 retrofit chain 補完（AUDIT-2026-05-02-P1-1）**：5 SQL migration（V028/V030/V031/V032/V034）retrofit Guard A/B + V031 view shape-guard。Chain：E1 r1 → E2 r1 RETURN 3 finding → E1 r2 → E2 r2 PASS → E4 r2 FAIL（V031 view 非 idempotent against V034-extended 53-col state）→ E1 r3 Option B shape-guard → E2 r3 PASS → E4 r3 Linux production `trading_ai` PASS（V031 NOTICE-skip × 2、fixture 20/20、view col=53 preserved、audit OK、healthcheck WARN baseline 0 new FAIL）。Commit `e858ae2`（r1+r2）+ `6cb1c3b`（r3）。

## §七 Engine 自動遷移（opt-in，2026-04-24 Phase 2）— trim 前完整版

**背景**：V023/V019/V021 silent-noop postmortem 顯示 100% 手動 `psql < V*.sql` 會漏套用。Phase 2 在 `openclaw_engine` 啟動時加一條 opt-in 自動遷移管線，**預設關**，operator 逐步驗證後再開。

**兩條套用路徑並存**：
- **手動（預設）**：`bash helper_scripts/linux_bootstrap_db.sh --apply` — 既有流程不動，此 Phase 不移除。
- **自動（opt-in）**：環境變數 `OPENCLAW_AUTO_MIGRATE=1` 時，engine 啟動在 DbPool 連線後、writer 啟動前呼叫 `openclaw_engine::database::migrations::MigrationRunner::run_if_enabled()`：
  1. 自刻 parser 讀 `sql/migrations/V###__*.sql`（sqlx 內建 parser 不吃 Flyway 格式）；`V017_rollback.sql` / `V999__*.sql` 依檔名過濾。
  2. 若 `_sqlx_migrations` 空且 `learning.model_registry` 存在（V023 canary），seed V001-V023 為「已套用」狀態 — 符合 2026-04-24 postmortem 後的 live DB 狀態。
  3. 跑 `Migrator::run_direct` 套用 pending（目前無，V024+ 時才會有）；checksum 比對失敗 / 曖昧狀態 / canary 不成立 → 中止啟動（`exit 1`），**不靜默吞**。
- **安全準則**：ambiguous state（有 app schema 但無 V023 canary）= 硬性 RAISE，不自動猜測；operator 跑 `helper_scripts/db/audit_migrations.py` 後人工介入。

**Rollback path（engine refuse to start）**：若 `OPENCLAW_AUTO_MIGRATE=1` 打開後 engine 不肯啟動，operator 立即：
1. Stop engine（`restart_all.sh --stop`）。
2. 關 env：`unset OPENCLAW_AUTO_MIGRATE` 或 env file 改回空。
3. 回到手動流程 `bash helper_scripts/linux_bootstrap_db.sh --apply` 補任何 pending migration。
4. 重啟 engine（`--rebuild` 非必要，除非改了 Rust 碼）。

**測試**：`rust/openclaw_engine/src/database/migrations.rs` 15 個 unit tests（純解析 / 無 DB）+ `rust/openclaw_engine/tests/migrations_test.rs` 5 個整合測試（需 `OPENCLAW_TEST_PG` 連線字串；無則自動跳過；`fresh_db_applies_all_migrations_end_to_end` 另需 `OPENCLAW_TEST_PG_DESTRUCTIVE=1` ack）。

**2026-05-02 P0 sqlx hash drift incident**（`3681f83`）：`repair_migration_checksum` binary 處理 V028-V034 migration file edit 後 DB checksum 沒同步 — V## migration file 加 Guard 改了 checksum 但 DB `_sqlx_migrations.checksum` 沒同步，導致 engine restart 觸發 sqlx migrate 失敗。治本 = `bin/repair_migration_checksum.rs`（commit `3681f83`，TTY guard COMMIT prompt）；治理盲點 = audit closure SOP 漏 engine restart 實測（cargo test PASS ≠ runtime sqlx migrate 驗證）。詳 memory `project_2026_05_02_p0_sqlx_hash_drift.md`。

## §七 被動等待 TODO 必附 healthcheck（2026-04-23）— trim 前完整版

**背景**：2026-04-22 P0-13 ATR scale + P0-14 edge miss 雙 bug 經「被動等待 24h observation」流程放行；後續 review 才發現 7d `phys_lock` 0 fire 其實是 silent-dead，observation window 本身無法偵測。結論：**任何「被動等待 Nd / Nw」的 TODO 必須同步附一條可執行 healthcheck**，由 cron 或 operator 手動間隔跑，確認被動等待的前提（pipeline 活著 / 信號流通 / fires 發生中）仍成立。缺此項 = 無法區分「沒事所以沒動」vs「壞了所以沒動」。

**規則**（4 條，E2 必查）：
1. **登記門檻**：TODO 新增「被動等待 Nd / Nw」類條目時，必須同時：(a) 在 `helper_scripts/db/passive_wait_healthcheck.py` 加一個 `check_*()` function（通常 1 SQL or 1 oneliner）;(b) TODO 文本引用該 check id。
2. **檢查語意**：check 回 `"PASS" / "WARN" / "FAIL"`，**Exit 1 = silent-dead 自動偵測** — 不是「沒資料」就 PASS。若被動等待假設「每 N 小時該有 ≥1 次 fire」，check 就要驗 fire count ≥ 1 and ts > now() - N hours。
3. **節奏建議**：operator 每 6h cron 跑 `passive_wait_healthcheck.py`，任一 FAIL 即檢查該 TODO 的前提是否仍成立。本檔已有 7 個 check（close_fills / label_backfill / exit_features_writer / phys_lock / micro_profit / trailing_stop / edge_estimates freshness），新增按此樣式追加即可。
4. **違規處理**：新增被動等待 TODO 未附 healthcheck = E2 審查打回；已有被動等待 TODO 若對應 pipeline 沒 healthcheck 覆蓋 = 下一輪維護週期必補。

**觸發情境例**：
- 「等 21d demo 穩定」→ check：demo engine_alive last 24h + 0 engine_crash 次數
- 「等 7d counterfactual replay」→ check：replay 結果檔存在且 mtime > script last run
- 「等 1w PostOnly fee 驗證」→ check：maker fill rate > X% 且 demo fee 降幅達標

## §九 Singleton 表（trim 前完整 5 條長注釋版）

| Singleton | 創建位置 | 完整描述 |
|-----------|---------|---------|
| `_H_STATE_INVALIDATOR` / `_LOCK` | h_state_invalidator.py | 內部懶加載 `init_h_state_invalidator()`；G3-08 Phase 1C（2026-04-26）條件 spawn — 嚴格 `OPENCLAW_H_STATE_GATEWAY=="1"` 才建構 singleton，否則 `invalidate_async()` no-op 零負擔。Process-global ``HStateInvalidator`` 是 Python→Rust 失效提示通道（資料流與 G3-03 ExecutorConfigCache 相反）：每次 H1-H5 / 5-Agent 狀態變化由 fire-and-forget daemon thread + 私有 ``EngineIPCClient`` + ``asyncio.new_event_loop()`` 推送 ``invalidate_h_state`` JSON-RPC notification，提早 Rust ``h_state_cache`` poller 的 ad-hoc poll；Rust 端 10s 排程 poll 永遠仍會發生，漏一次提示最多多 ≤10s 過時、不破壞正確性。所有 IPC 例外於內部三層 try/except 吞掉（CLAUDE.md §二 原則 #6 fail-closed）。Wire site：`strategy_wiring_h_state.py`（STRATEGY-WIRING-SPLIT P2，2026-04-28；前為 `strategy_wiring.py:535`），`strategy_wiring.py` re-import 保 `app.strategy_wiring._H_STATE_INVALIDATOR` 屬性 grep 穩定。測試用 `_reset_for_tests()` 釋放 |
| `MARKET_SCANNER` / `AUTO_DEPLOYER` / `_SCOUT_WORKER` | strategy_wiring_scanner.py | `wire_market_scanner_and_workers(...)` 函數呼叫返回 `ScannerWiringResult`；`strategy_wiring.py` 在原 init 順序位置呼叫並 bind 回 module attribute（保 `app.strategy_wiring.MARKET_SCANNER` / `AUTO_DEPLOYER` 屬性 — 下游 `strategy_read_routes` / `strategy_write_routes` `from .strategy_wiring import MARKET_SCANNER, AUTO_DEPLOYER` 不破，`h_state_collectors` `getattr(_sw, ...)` 不破）。MarketScanner = 5-min linear+spot 機會掃描；StrategyAutoDeployer = max_symbols=30 / risk 3% / pinned BTCUSDT,ETHUSDT / spot reserved 5；ScoutWorker = 30-min 情報注入 ScoutAgent → MessageBus → Strategist。3 子塊 fail-open（任何一個 except → 該 singleton=None，主管線繼續）。STRATEGY-WIRING-SPLIT P2（2026-04-28）抽出 |
| `HStateCacheSlot` | rust/openclaw_engine/src/ipc_server/slots.rs | Rust 端 `Arc<RwLock<Option<Arc<HStateCache>>>>` late-injected slot pattern（G3-08 Phase 1A，commit `aa287c4`）。env=0 時 `main_boot_tasks::spawn_h_state_poller_if_enabled()` 跳過 spawn → slot 維持 `None` → `query_h_state` hot-path lookup 回 `None`、`get_h_state_status` 回 uninitialized；env=1 時建構 `Arc<HStateCache>` + spawn tokio daemon 每 10s pull `query_h_state_full` Python IPC + 收 `invalidate_h_state` 提示觸發 ad-hoc poll，DashMap shard lookup ≤1ms p99 達 hot-path SLA。Python crash → Rust 沿用 last good snapshot 並在 `staleness_ms > 30s` 時標 stale flag（fail-soft，CLAUDE.md §二 原則 #5/#9）。Schema 演化 forward-compat：`AgentState.stats: HashMap<String, i64>` + `#[serde(default)]` 吸收新欄位免 lock-step deploy |
| `CostEdgeAdvisorDbSlot` | rust/openclaw_engine/src/cost_edge_advisor_boot.rs | Rust 端 `Arc<tokio::sync::RwLock<Option<Arc<DbPool>>>>` late-injected slot pattern（G3-09 Phase B，2026-04-28；2026-04-28 Wave E split 從 main_boot_tasks.rs 移出至 cost_edge_advisor_boot.rs sibling per E2 PB1 LOC review）。鏡 `HStateCacheSlot` 設計：DB pool 啟動時延後注入 cost_edge_advisor daemon，30s populate-timeout；slot=None 時 daemon fallback 到 in-memory counter（不寫 `learning.cost_edge_advisor_log`），slot 注入後改走 DB INSERT 路徑。Engine restart 自動清空（`Arc` 隨 process 結束 drop）。Phase A advisor.evaluate() 不依賴此 slot — 純為 Phase B INSERT path 加 forward-compat（Phase A 評估邏輯仍跑於 in-memory，slot 注入後純加 persist 副作用）。HMAC secret 與 main loop 解耦，符合 CLAUDE.md §二 原則 #6（失敗默認收縮）+ 原則 #8（可審計） |

**post-trim 表中：以上 4 條收成單行（path + 一句話 purpose）。詳述見本檔。**

## §十一 一句話狀態（trim 前 ≤2026-05-01 23:17 CEST 版本）

> 截至 2026-04-30 22:28 CEST：**current code-bearing runtime checkpoint is active and healthcheck is WARN, but edge remains at-risk** — Strategy Edge Models + Dust residual prevention + MLDE demo autonomy are deployed; dust full-close behavior is proven on real Demo/LiveDemo `qty=0` close fills; post-reload maker execution is now near target, but rolling `[33]` and realized `[40]` remain below acceptance and `[38]` grid lifecycle drift is still WARN. Next work is G2-02/G2-01/P0-3 time-driven decisions. True live autonomy remains gated by GovernanceHub + Decision Lease + 5 live gates.

**post-trim：§十一 整節刪除**（已被 §三 真實狀態替代，避免雙寫 drift）

---

**Recovery instructions**：本檔內容 + `git show 9726b3b:CLAUDE.md` 即可完整還原 trim 前 554 行 CLAUDE.md。
