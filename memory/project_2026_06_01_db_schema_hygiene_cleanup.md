---
name: project_2026_06_01_db_schema_hygiene_cleanup
description: 2026-06-01 DB schema 衛生審計（regime_1h 死欄位觸發）——真空間浪費=903MB 被遺忘的 risk_verdicts_damaged 事故備份表；NULL 欄位 ~0 空間是 schema 清晰度問題；V116 清理方案待 CC+dry-run+operator
metadata: 
  node_type: memory
  type: project
  originSessionId: 07386332-55ba-43c0-a468-02f0f16dd863
---

2026-06-01 operator 因 [[project_2026_06_01_fail_closed_gate_stack_root_cause]] 的 regime_1h 死欄位，要求全面排查 DB 死/僵欄位+表並研究清理。MIT read-only 審計（PG trading_ai 15 schema head V115 + 代碼 grep HEAD 2e809b96）結論：

**真空間浪費（唯一物質收益）= 4 個 2026-04-14 事故損壞備份表 ~909MB**：`trading.risk_verdicts_damaged_20260414_130607`(418萬行/**903MB**) + fills/intents/orders_damaged_*(~6MB)。0 代碼/view 引用，plain table（非 hypertable）→ DROP TABLE 無約束。**operator「DB 膨脹」直覺對，但真兇是被遺忘的備份表不是 NULL 欄位。**

**NULL 欄位 ~0 空間**（PG null bitmap ~1bit/row），刪它們純 schema 清晰度（防 regime_1h 式誤導）非省空間。

**關鍵教訓（深化 regime_1h）**：「全庫零讀」要查**兩層**——(1) application code (Rust/Python grep) (2) **PG object 層 pg_depend / view**。regime_1h + 5 兄弟(news_driven/scorer_ev_prediction/scorer_divergence/microstructure/mark_price) 被 V005 view `learning.scorer_training_features` SELECT（主會話 grep 漏了 view 層，MIT pg_depend 抓到）→ naive DROP COLUMN 會 cascade 壞 view。該 view 本身也死（零 runtime 消費者，只 mlde_edge_training_rows 被用）。

**分類（per-(table,column)，同名不同表 liveness 不同）**：
- 真死可刪：decision_context_snapshots 8 乾淨死欄位(recent_sequences/predictor_decision/shrinkage_decision/predict_latency_us/disagreed/predicted_q10/q50/q90) + 6 view-fronted(regime_1h 組,需先處理 view)。該表是 hypertable 但未壓縮→DROP COLUMN 不需 decompress。
- **避開的假陽性**：linucb_state_archive(rollback infra 永久留)/promotion_pipeline(有 writer+reader 休眠 pipeline)/paper_pnl_snapshots_legacy+system_health_legacy(Grafana 還在寫,178MB 但活)/predicted_q* 在 decision_shadow_fills(影子 ML 有 writer,**同名不同表**)/close_reason_code(V086 mutex 設計非廢棄)。無 write-only 垃圾欄位。

**V116 清理方案（待 CC 審+Linux double-apply dry-run+operator 拍板,本輪只研究未執行）**：仿 V096/ADR-0015。Packet1 DROP 4 damaged 表(pg_depend-only guard+RESTRICT+MODULE_NOTE 註記故意非空 drop，因 V096 的 count=0 guard 對 damaged 表不適用)；Packet2 DROP 6 空 legacy 表(ai_cost_events/market_tickers/observer_verdicts/order_events/position_snapshots/trade_executions,完整 guard)；Packet3 DROP 8 乾淨死欄位；**Packet4 分離/延後**(6 view-fronted 欄位需先 drop/recreate scorer_training_features view,blast radius 大,單獨簽收+QC 知會,drop view 前須對 program_code/ml_training/ 動態 SQL 做決定性 consumer grep)；延後 3 個 view-fronted 空 legacy 表(8-9 compat view 依賴,≈0 收益)。全 IF EXISTS+RESTRICT 冪等;改檔後 repair_migration_checksum。
鏈：MIT(done)→CC schema 審→E1 寫 migration(Packet1-3)→MIT Linux dry-run→operator deploy。與 alpha-fix batch(A-1/A-2/B/A-4)是獨立 batch 不綁。
- **CC schema 審完成（2026-06-01）= B CONDITIONAL，抓到 3 個真問題（MIT 漏的）**：(1) **BLOCKER 編號：V116 已被 M7 Decay 佔用**（TODO:149/260，V116-V125 全保留：M7/WorkflowB-V117/模組 V118-124/AEG-V125）→ PM 查實際 head V115、V116-125 全保留 → **清理 migration 改用 V126**（V105/108/110/111 空洞在 head 下 sqlx 順序拒，不可用）。(2) **BLOCKER：Packet3 的 recent_sequences 是 view-fronted**（被 V005 scorer_training_features view SELECT，CC 親讀 V005:267）→ DROP COLUMN RESTRICT 首次 apply 會報錯 → 移出 Packet3 併入延後 Packet4，**Packet3 縮為 7 欄**（predictor_decision/shrinkage_decision/predict_latency_us/disagreed/predicted_q10/q50/q90，CC 驗 0 view-dep/writer/reader）。(3) **硬前置：risk_verdicts_damaged 必須先 dump 再刪**（CC 裁定不接受直接永久刪：903MB/418萬行是 2026-04-14 FA-PHANTOM-1 事故唯一凍結快照、DROP 不可逆、live 表 24+ 天後無法重建事故現場；且既有 PA F-20 已明文「DROP+NAS dump」V116 設計漏了）→ DROP 前 pg_dump 4 表→NAS+checksum 附 PR，operator deploy 前確認。CC 確認交易/風控/授權語義全乾淨（16 原則 0 違反、9 不變量 0 觸碰、硬邊界 0 觸碰；親讀 context_writer.rs 26 欄 INSERT 確認 8 drop 目標 0 在 live 寫入路徑）。**校正後 V126 = Packet1(4 damaged 表,先 dump)+Packet2(6 空 legacy)+Packet3(7 乾淨欄,recent_sequences 移 Packet4)**；apply 時 MIT Linux double-apply dry-run 驗 legacy count=0/decision_context_snapshots compression_enabled=false/damaged pg_depend=0/冪等/repair_migration_checksum。

**V126 已部署（2026-06-02，commit e3233647）**：完整鏈 CC schema 審→E2 APPROVE→MIT Linux PG 實證 dry-run（真 TSDB 2.26.1，V126 用 `BEGIN…ROLLBACK` 不持久化破壞性 DROP、不長鎖 live dcs；guard 前提全成立 damaged pg_depend=0×4/legacy count=0×6/dcs plain-table compression=0/recent_sequences 正確留 Packet4；冪等 double-apply）→**dump-first**（targeted `pg_dump -Fc` 4 damaged 表→`/home/ncyu/pg_backups/v126_forensic_damaged_tables_*.dump` 60MB+md5+`pg_restore --list` 驗 4 表 TABLE+DATA 完整）→engine `restart_all --rebuild --keep-auth` auto-migrate apply（max version 115→**126**，auto_migrate Applied(2)）。**實測結果**：damaged 4 表 drop=**909MB 回收**、legacy 6 個 Packet2 target 全 drop（剩 5 個 `%_legacy`=account_snapshots/learning_events/paper_pnl_snapshots/risk_events/system_health 是刻意保留的活表/Packet4 view-fronted）、dcs 7 死欄 drop、recent_sequences 留存。**部署機制學到**：`OPENCLAW_AUTO_MIGRATE` 預設=0（V023 silent-noop postmortem 後 opt-in），restart_all 只從 `secrets/environment_files/basic_system_services.env` 讀此旗標（無 inline override）→ deploy 須暫設 file=1、restart、復原=0；migration 走 engine auto-migrate = sqlx fresh-register 無 hash-drift（不需 repair_migration_checksum，與手動 psql -f 不同）。


---

## [index-archive 2026-06-10] 原 MEMORY.md 索引條目全文(壓縮索引前歸檔,內容為當時點狀態)

- [DB schema 衛生清理 (2026-06-01)](project_2026_06_01_db_schema_hygiene_cleanup.md) — regime_1h 死欄位觸發全庫排查：真空間浪費=903MB 被遺忘的 risk_verdicts_damaged 事故備份表（+3 個小 damaged + 6 空 legacy 表≈909MB），NULL 欄位 ~0 空間是 schema 清晰度；教訓「全庫零讀」要查 code+pg_depend 兩層（regime_1h 被 V005 dead view SELECT，grep 漏 view 層）；避開假陽性 linucb_state_archive/Grafana-live legacy/predicted_q*同名不同表；V116 清理方案(Packet1-3 安全+Packet4 view-coupled 分離)待 CC+dry-run+operator
