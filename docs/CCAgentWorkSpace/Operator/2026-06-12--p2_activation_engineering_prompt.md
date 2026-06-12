# P2 批次激活工程 prompt（交 codex 執行）

> 背景:2026-06-12 一批 dormant 功能已 E1→E2×2→E3→MIT→E4 全鏈綠並三端同步(Mac=Linux=origin),
> 但所有 runtime 激活項按治理慣例(installer APPLY-gate)留 operator 一鍵執行。rtk CLA(owed #1)operator 已簽。
> 本檔=剩餘 owed #2-#6 的完整執行 prompt。codex 在同一 repo + Linux runtime(trade-core)上執行。

---

## 0. 全局紀律(先讀,不可違反)

1. 這是**真實交易系統的 prod 環境**。16 根原則:存活 > 風險治理 > 系統健康。任何一步不確定→停下報告,不猜。
2. **prod DB 寫操作(migration apply)是最高風險**。本批新增的全部代碼/表都是 **dormant**(flag 默認 0、cron 未裝、新表 0 rows、零 live 寫路徑)。激活順序=「先低風險可獨立止損的,後依賴項」。
3. 每個階段**獨立可止損**:做完一個階段驗證綠再做下一個,不要一口氣全做。
4. runtime 真相在 Linux `trade-core`(`~/BybitOpenClaw/srv`);Mac 是開發機。PG 連線範式見 `docs/agents/context-loading.md` §"PG Connection Examples"。
5. 三端當前 HEAD 應 = `61803917`(codex 開工前先 `git -C ~/BybitOpenClaw/srv pull --ff-only` 確認最新)。
6. 誠實報告:任何測試/apply 失敗如實說,不軟化;跳過的步驟說明原因。

## 1. 必讀文檔(執行前按需讀,路徑相對 repo 根 `~/BybitOpenClaw/srv/`)

| 主題 | 文檔 |
|---|---|
| L2 記憶層完整設計(DDL/模組/flag/healthcheck 號) | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-11--l2_memory_layer_design.md` |
| E4 prod apply 計劃 + scratch 彩排證據(**最關鍵,含 V138→V139 順序/冪等/Guard 漂移負測**) | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-06-12--p2_batch_regression_dryrun.md`(看 §C-2 + owed) |
| MIT schema ratify(C-2 連帶 V138 + checksum 預檢) | `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-11--l2_memory_schema_ratify.md` |
| L2 cron/seed/V140 用法 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-11--l2_memory_m2_cron_seed.md` |
| BB 哨兵 installer + endpoint 紀律 | `docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-11--bybit_announcement_sentinel_advisory.md` + `docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-11--alert_sink_bb_sentinel.md` |
| polymarket 軸 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-11--polymarket_axis_port.md` + `docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-11--polymarket_axis_discipline.md` |
| migration 套用機制 | `rust/openclaw_engine/src/database/migrations.rs` + `helper_scripts/restart_all.sh` + CLAUDE.md §"Data, Migrations, And Validation" |

---

## 階段 A — prod migration V138 + V139(owed #2,最高風險,其餘階段不強制依賴除 B)

**目標**:prod `_sqlx_migrations` head 從 137 → 139。V138=P4 research FDR 表(別的 session 的 owed,本次連帶消費此 operator-gated 決策);V139=本批 L2 記憶 store。兩者皆 **dormant 純增表,套用後 0 rows、零 live 影響**。

**前置驗證(必跑,任一不符就停)**:
```
# 1. prod head 確認 = 137(雙 pending)
psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -At -c "select max(version) from _sqlx_migrations"
# 2. checksum drift 預檢:已套用的 migration 的 checksum 不得與 repo 檔漂移(MIT C-2 硬要求)
#    讀 migrations.rs 確認 sqlx 校驗機制;若有獨立 migrate 命令優先;否則靠 engine 啟動時 auto-migrate 的 checksum gate
# 3. V138/V139 檔存在且與 Mac 一致
ls -la sql/migrations/V138__research_fdr_tables.sql sql/migrations/V139__agent_memory_store.sql
```

**apply 機制(讀 `migrations.rs` 確認後選一,優先不 restart 的路徑)**:
- 我們的 migration 是 engine 啟動時 `auto_migrate` 套用(歷史:V131/V132/V133 即此路徑)。
- ⚠️ **full restart 會 revert operator-env flag**(歷史教訓):restart 前先 `crontab -l` + 查有無 RUNNING soak / operator-set env flag(如 `OPENCLAW_RESIDUAL_ALPHA_PRODUCER`),記錄下來,restart 後逐一恢復。
- 若 `migrations.rs`/`restart_all.sh` 暴露**獨立 migrate 子命令**(不全量 restart engine),優先用它,避免 flag revert。
- E4 已在 scratch 實證:V138 先 apply RC=0 → V139 RC=0(兩表+5 索引+生成列+三 CHECK+grant 分支)→ re-apply 9 個 "already exists, skipping" 零 ERROR = 冪等。prod 行為應一致。

**apply 後驗證**:
```
# head = 139
psql ... -At -c "select max(version) from _sqlx_migrations"
# V139 兩表存在且 0 rows(dormant)
psql ... -c "select count(*) from agent.agent_memory; select count(*) from agent.agent_memory_embedding_meta"
# Guard/CHECK 健全:讀 E4 報告 §A 的探針,確認 supersede 無指針/mem_type 非法/priority=-2 三 CHECK 拒
# DELETE REVOKE:trading_ai role 現 prod 不存在=latent fail-closed,無需動作(E4 INFO-2 已釋疑:owner 隱含權,REVOKE 宣示性)
```
**回滾**:migration 是純增表,無需回滾;若 apply 中途失敗,事務性保證 0 半套用(E4 Guard A 漂移負測已證 0 索引殘留)。報告失敗原文即可。

---

## 階段 B — L2 記憶層激活(owed #5+#6,**依賴階段 A 完成**)

L2 蒸餾管線需要 V139 表存在。分三步,可只做到任一步止損:

**B1. embedding 軸(pgvector + bge-m3,可選——不做則 FTS-only 自動降級)**:
```
# V140 是 manual apply(刻意不入 sql/migrations/,防 sqlx fail-stop)
bash helper_scripts/db/apply_manual_V140_agent_memory_vector.sh   # 讀腳本確認 dry-run/apply gate
# E4 已證 trading_admin 有 CREATE EXTENSION vector 權限;冪等可雙跑
ollama pull bge-m3   # embedding 模型(~1-2GB);缺則 L2 走 FTS-only(word_similarity 0.3,E4 三語召回已驗)
```

**B2. seed 初始記憶(dry-run 先看,--apply 才寫)**:
```
python3 helper_scripts/memory/seed_agent_memory.py            # dry-run 默認,列將寫入何物
python3 helper_scripts/memory/seed_agent_memory.py --apply    # 真寫(A 源 agent.lessons dead-modes + B 源 MEMORY.md 索引行)
# 驗證:select count(*),origin from agent.agent_memory group by origin  (應見 l2_curated 等)
```

**B3. 激活 daily 蒸餾 cron(會每天 05:23 UTC 跑真 Ollama 蒸餾)**:
```
OPENCLAW_L2_MEMORY_DISTILL_CRON_APPLY=1 bash helper_scripts/cron/install_l2_memory_distill_cron.sh  # 讀腳本確認確切 APPLY env 名
# 然後設 pipeline flag 開啟(否則 cron fire 但 inert):確認 flag 名 OPENCLAW_L2_MEMORY_PIPELINE,寫進 engine/cron 的 env 源
# 驗證:healthcheck [88][89] 由 PASS-skip 轉真檢;runner.py 跑一次看 [88][89] 狀態
```
⚠️ B3 開 flag 後管線會真調 Ollama qwen3.5:9b 蒸餾前一日 `l2_calls`。先確認 Ollama 在(`curl -s http://127.0.0.1:11434/api/tags`)。

---

## 階段 C — BB 公告哨兵激活(owed #3,獨立,**會真告警**)

```
OPENCLAW_SENTINEL_CRON_APPLY=1 bash helper_scripts/cron/install_bybit_announcement_sentinel_cron.sh  # 讀腳本確認 APPLY env 名 + cron 30min
# 先手動單跑一次驗證(首輪 baseline 模式:全標 seen 不告警,防洪)
python3 helper_scripts/canary/bybit_announcement_sentinel.py --once --data-dir <engine data-dir>
```
⚠️ **告警通道**:哨兵告警走 `alert_sink.py`(耐久落 `<data-dir>/alerts/alerts.jsonl`),但 **Telegram creds 仍是 owed**(operator 後補項)。激活後若無 Telegram 配置,告警只落 jsonl 不推送。要推送先配 Telegram creds(見 `engine_watchdog.py` `_load_alert_creds` 的 creds 檔位置)。哨兵 **alert-only,絕不自動觸發任何交易動作**。

---

## 階段 D — polymarket 採集軸激活(owed #4,獨立,artifact-only)

```
OPENCLAW_POLYMARKET_AXIS_CRON_APPLY=1 bash helper_scripts/cron/install_polymarket_axis_cron.sh  # 讀腳本確認 APPLY env + daily 04:41 UTC
# 先手動單跑驗證
python3 -m helper_scripts.research.polymarket_axis.cli --mode daily   # 確認 CLI 入口/參數
```
⚠️ 存儲 ~20-50MB/day(raw per-row);hourly 行默認停用(QC 裁:活化=operator)。artifact-only,**零 PG / 零 signal 輸出 / 不進交易鏈**;數據先積累,假說後驗(進交易鏈前必走 quant 三段鏈,見 QC discipline memo §0)。

---

## 執行順序建議

1. **階段 C + D 可先做**(獨立、不碰 prod DB、低風險),立即開始監測/積累數據。
2. **階段 A**(prod migration)挑低交易活動窗口做,做好 flag 盤點+恢復。
3. **階段 B** 在 A 綠之後;B1/B2/B3 可分次,FTS-only(跳 bge-m3)也能跑。

每階段完成後在 `TODO.md` 對應 owed 行打勾 + 留 commit/驗證證據(codex 按 `.codex/` 自身的 sync/worklog 協議記錄)。全部完成後三端同步。

---
*生成:Claude Code session(P2 批次 PM),2026-06-12。本批代碼 commits `131bd560`/`9bc57548`/`d4994f6b`/`5e3820f3`/`61803917`。*
