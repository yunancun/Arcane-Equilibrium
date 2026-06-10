# E4 Memory — 工作記憶

> 本檔＝長期教訓＋近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 `memory-archive.md`（append-only，勿刪改）；agent 完成序列照常追加於檔尾。
> 壓實歷史：2026-06-10 首次壓實，原 memory.md 第 1-5249 行已逐字遷入 memory-archive.md。

## 長期教訓

- 任何寫死數字都不可作 baseline（task brief／E1 self-report／commit msg／TODO／CLAUDE.md／profile.md／本檔歷史數全會 stale）：必親跑命令取即時值；改動前基線在同 worktree 同 commit 用 `git stash`／throwaway worktree 實測；delta 必逐 commit attribution 到 0 unexplained。
- 跑兩遍 deterministic identical 是 PASS 必要條件：fail 名單逐條 byte-identical 對比（非只比 count）；首跑 PASS 不算綠、首跑 FAIL 也不直接退 E1。
- 測試數對賬到名字級：collect-only node-ID diff 證 REMOVED=0／ADDED=N；rename＋語意翻轉在 set-diff 是「1 removed＋1 added」須逐名分辨；parametrize 使 fn 數≠item 數；node 數 vs outcome 總數有 module import-skip 口徑差；刪測試僅限被移除功能的行為測試且須有「功能已死」負向取代。
- mock 只允許 stub IO 邊界（PG cursor／socket／filesystem／env／外部通知），受測業務邏輯必真跑；逐測 trace「真 vs stub」分界；e2e 不可 patch 受測 seam（合成注入繞過真選取＝當初漏 bug 的同盲點）；capturing-wrapper／FakeCursor／loader-only monkeypatch 是正確形態。
- 關鍵測試必做 mutation-bite 親驗：暫改業務碼（負向測試＝把被禁行為加回去）證測試必紅，還原後 `git diff` byte-clean＋mutation marker grep=0 再證綠——證 catcher 非 tautology、非 mock self-consistency。
- Mac PASS ≠ Linux PASS：Linux trade-core 是 runtime／PG／TimescaleDB／systemd 權威；V### migration 必 Linux PG empirical double-apply 驗冪等（first-apply 與 re-apply 路徑不同要分別驗）；真連線 smoke 抓得到 mock 蓋不住的缺陷。
- flaky vs regression 判別三條齊全才可排除：隔離單跑＋git diff 證測試／SUT 未 touch＋改動不在代碼路徑；timing benchmark 必 standalone-vs-standalone 同條件並獨立重做 base 裁定（stash 或共享 CARGO_TARGET_DIR 重編 base）；cargo 預設 fail-fast，取全 binary 計數必 `--no-fail-fast`。
- pre-existing fail 必逐條 attribution：stash／checkout parent 同條件重現＋失敗名單 diff＝空才可歸 pre-existing；留意 sibling commit 造成的 fail 名單 swap-in／out（總數不變但個別 test 名換了）。
- 跨機驗證用 full-tree rsync／git worktree 一次帶齊 companion（逐檔 scp 漏一個＝整包假 fail）＋md5 對齊關鍵檔；temp 樹須複製真 repo 目錄深度（`parents[N]` 解析）；fresh worktree 首跑可能大量假失敗（warmup 競態），丟棄首跑取 3 遍穩定值；跑完清 temp＋確認 prod 零觸碰。
- 環境坑速查：ssh 非互動 PATH 無 cargo（先 `source ~/.cargo/env`）；Linux repo 在 `~/BybitOpenClaw/srv`；healthcheck 須先 source secrets env；密碼含 `()` 要 single-quote inline 注入；`cmd | tail` 的 rc 是 tail 的，cargo 結果必 grep `^test result:`；macOS 無 `timeout` 指令；tomllib 需 py≥3.11（Mac 用 `srv/venvs/mac_dev`、Linux 用 `control_api_v1/.venv`）。
- pytest 已知互斥／假 fail 模式：`OPENCLAW_CSRF_SHADOW=1` 修 write-endpoint 403 但翻紅 csrf-middleware 斷言（雙模互斥，兩側對稱出現即非回歸）；`from program_code...` 絕對 import 必從 srv root＋PYTHONPATH；test_pure_utils 重名 collection error 用 `--import-mode=importlib` 或雙 `--ignore`；對失敗檔加 `-p no:asyncio` 仍同 fail＝與插件無關的鐵證法。
- E4 邊界：不改業務邏輯（發現 issue 退 E1 不代寫；test 自身寫錯可直接修）；不 commit／push／deploy 除非任務授權；驗不到的面（Linux full run／deploy-gated 真 row／flag-ON 路徑）誠實標 owed 而非假裝覆蓋；本檔 append-only（`cat >> EOF`），meta-doc 用 `git commit --only`。
- 自報數字與 closure doc 必對抗核實：fake-PASS retract 用 grep 產物 present＋standalone 真跑；「opt-in env-gated」test CI 默認不跑＝不算 e2e 證據，e2e 必 PG runtime row 直查。
- 所有改動 JS／inline script 必跑 `node --check`：brace／paren diff=0 抓不到 const/let 重複宣告等 lexical error，只有真 parser 能 catch。
- source land ≠ runtime 生效：engine 需 `restart_all.sh --rebuild` 後才跑新 binary；E4 acceptance＝source land＋test PASS，runtime 觀察期屬 PM／deploy gate；release binary strings／nm 0 hit 常是 build 時序或 symbol stripping，非 fail。
- hot-path 改動跑 bench 取分位數（p50/p99）而非只 cargo test；非 per-tick 路徑可定性論證免 micro-bench；cross-language 1e-4 只適用 indicator／共用浮點，control-flow／純 SQL／純 Python lane 在報告明確聲明 N/A 而非靜默跳過。
- 檔名／path glob／spec 字面不是核實標準，substance 等效即 PASS；spec 引用的 test 檔名、SQL column、count 常 stale——退回 design doc／information_schema／`pytest --collect-only` 查真實（無 test_ prefix 的檔不會被 collect）。
- PG 實證模板：多 case dry-run 用獨立 BEGIN/ROLLBACK pair（單一 txn 首個 ERROR abort 後續全跳）；`CREATE OR REPLACE VIEW` 須 shape-guard 防 future-shape drift（PG 不許 drop col）；Seq Scan ≠ index-miss（cost-based 正常）；驗 runtime env 真值用 `/proc/<pid>/environ` 非 env-file grep（雙 env file 衝突會 silent 吃掉操作）。
- 角色鏈紀律：E2 已 APPROVE 的 design intent 不重啟審查（task 字面與 E2 verdict 衝突走 E2 verdict）；PM 直派跳 E2 時 E4 須兼任 E2 必查點並在報告標明；stalled／silent-killed sub-agent 的工件以 test 真跑 PASS＋report file 內容為 ground truth，spot-check 重採即可確認。

## BASELINE

- 2026-06-10 BASELINE 重置：舊基線（2555/17）隨配置遷移作廢；下次全量回歸建立新行（格式: BASELINE: YYYY-MM-DD passed=N failed=M）
- （說明：全檔 BASELINE 行集中於本節；上行同見近期記錄 2026-06-10 L2 P3b 條目原文。新基線建立後追加於此節。）

## 近期記錄

## 2026-06-08 · residual PART 4 Phase 1 (Gap B+C) regression + E2 LOW#2 closure (PASS)

**被驗**：worktree `/private/tmp/wt-residual-act`，branch `feature/residual-activation`，commit `da3aec6f`（base=`da3aec6f~1`=merge-base origin/main=`8cd4da1f`）。Gap B 多因子殘差化（funding-carry PIT）+ Gap C sign-flip permutation，flag-gated OFF、behavior-neutral。E2+MIT 已 PASS（report 未落 disk，僅 PA design 為 untracked dirty）。Python-only。

**全量決定性 ×2（`PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0`、先清 __pycache__；ml_training/tests+learning_engine/tests）**：HEAD `da3aec6f` = **826 passed / 31 skipped**（run1=run2 identical，無 flake）。pytest 9.0.3 / py3.10.1。

**★ 權威 baseline reconcile（throwaway worktree `git worktree add --detach 8cd4da1f`，跑完 remove）**：base `8cd4da1f` 全量實跑 = **794 passed / 31 skipped**（精確等於 E1 claim）。collect-only node-ID diff（base 823 vs HEAD 855）：**REMOVED=0 / ADDED=32**，逐 fn 對賬 gate +14 / cycle +2 / producer_db +11 / report_contract +5 = +32。delta = 826−794 = **+32 = 100% 新增測試、0 regression**。spec 的「770」是 PART-2 之前史料；當前 HEAD 真 base = 794（mlde-hook+PART-2 neighbor commits 已進 8cd4da1f）。

**skip-set delta = 0（決定性）**：base 與 HEAD 各 `-rs` dump skip nodeid+reason 排序 `diff` = NO DIFF。31 skips byte-identical（全 benign：sklearn/lightgbm/optuna/pyarrow/psycopg 未裝 + real-PG opt-in gate）。Gap B/C 加 0 skip，32 新測全 run+pass，無 mock/skip 藏真失敗。

**E2 LOW #2 closure（唯一 business-relevant 新測）**：E2 mutation #3 證既有 `test_permutation_determinism_same_seed_same_p`（fixture mean=1.0/std=2.0/n=50）p **飽和到 0.0** → 打斷 seed binding（`default_rng()` 忽略 seed）後 `assert p1==p2` 仍過（0.0==0.0），不咬 broken seed（我實證：broken seed 下該舊測仍 PASS）。新增 `test_permutation_determinism_borderline_p_binds_seed`：弱訊號手構 fixture（27×+0.5/23×-0.5、n=50、obs mean=0.04bps）使 p 落 ~0.66–0.69 非飽和、隨 seed 變動。斷言：同 seed(20260608) 兩呼 p=0.668 嚴格相等 + 異 seed(777) p=0.6812 close-but-not-identical（|diff|=0.0132，皆∈[0.60,0.75]）。值在 HASHSEED=0 下跨 run 可重現（PCG64 整數抽樣平台無關）。**mutation-bite 親驗**：暫拿掉 line 839 `rng=default_rng(int(seed))`→`default_rng()`，我的測試 **FAIL**（同 seed 兩呼發散 0.662 vs 0.68），舊測同條件仍 PASS。還原後 git diff 業務檔空、grep E4-MUTATION=0、新測綠×2。

**mock-doesn't-hide-logic（獨立驗，非盲信 E2/MIT）**：(1) 真路徑 0 業務 mock — funding PIT `test_bucketed_funding_factor_pit_only_settled_rows` 驅真 `bucketed_funding_factor`（未來費率 9.0 排除斷言真咬 PIT）；beta-trap `test_evaluate_cell_funding_carry_beta_trap_fails` 驅真 `evaluate_cell` 全鏈（殘差化還原 funding_beta≈1.5、raw+→residual≤0）；permutation 全測直呼真 `_permutation_residual_alpha`。(2) IO 邊界 stub（允許）— `test_load_funding_rates_converts_and_drops_bad` 用 `_MultiConn/_MultiCursor` fake DB 連線，真跑 `load_funding_rates`（timestamptz→epoch、壞 rate drop）。(3) 唯一 stub-thing-under-test = `test_attach_residual_reports_maps_to_payload`（**pre-existing 非我 +32**）monkeypatch `build_cycle_residual_reports`，正確隔離 payload-mapping wrapper 並真跑 `validate_signal_spec`。32 新測**無一** stub 受測對象。

**behavior-neutrality（含我新測在 tree）**：cross-worktree 親算 default-report canonical SHA256 = base `8cd4da1f` 與 HEAD 皆 **`1571eade7def...`**（同 19-key keyset、permutation OFF 無 perm 欄位）。我的測試純加性（直呼 bare permutation fn 帶顯式 seed，不碰 default `evaluate()` 路徑），byte-identity 不動。全量 ×2 含新測 = **827/31**（commit 後 HEAD `c6cc1578` 再跑 = 827/31）。

**cross-lang float = N/A**（pure-Python evidence lane，無 Rust hot path / IPC / 共用浮點）——明確聲明。

**Linux owed（誠實標）**：funding settlement-timing dry-run on real `market.funding_rates`（Mac 用合成 settlement 列；**MIT 已做 settlement-timing dry-run**）；真 PG multi-factor DB cycle 載入。**Gap-A（非本批）**：Stage-0R orchestrator 接 DB loaders、net_side/orchestrator 接線。worktree 未提交主線、未 push/deploy/restart。

**commit**：`c6cc1578`（`git commit --only` 隔離 test 檔，+44 行，**未 push**；untracked PA design doc 未動）。

**教訓**：(1) 「seed 綁定」的 determinism 測試只有在**非飽和 p**（borderline regime）才有 bite——強訊號 fixture 把 p 釘在 0.0/1.0 時 `p1==p2` 對 broken seed 無鑑別力。補測要先實證舊測在 mutation 下仍綠，再構造弱訊號 fixture 落到 p 隨 seed 變動的中段，並用「同 seed 兩呼嚴格相等」當 bite 點（broken→entropy 播種發散）。(2) 鎖 magic p 值前必跑兩遍確認 PCG64 跨 run 重現（HASHSEED=0），documented 值用 `pytest.approx(abs=1e-9)` 而非 ==。(3) baseline reconcile 仍用 throwaway-worktree 三點實測法：spec 引用的舊數（770）是史料，HEAD 真 base 以 `merge-base` checkout 實跑為準（794）。

**VERDICT: PASS（ready for P2）**。退 E1 清單：無。

---

## 2026-06-08 · L2 D3 Phase 1 (V134/V135/V136) Linux PG 雙-apply 冪等 dry-run + columnstore ADD COLUMN — PASS

**被驗（branch `feature/l2-critic-lessons-tools`，3 migration 全 untracked 未提交，scp 入 Linux/容器 temp，不 commit）**：V134 `agent.l2_calls`(24-col forensic ledger)+`agent.l2_consequential_marks`(append-only side-table) / V135 `learning.l2_gate_seam_log` / V136 additive `source_l2_reply_id TEXT NULL` ALTER 到 `learning.hypotheses`+`replay.experiments`+`trading.fills`。md5 三檔 Mac==Linux 親驗（V134 87d82568 / V135 95165c3b / V136 718880e1）。E2+E3 sanitize gate 已 PASS。

**PG 拓樸（先查容器名鐵律）**：PG 在 docker container **`trading_postgres`**（timescale/timescaledb:latest-pg16，127.0.0.1:5432），prod db `trading_ai`，superuser `trading_admin`，**TimescaleDB 2.26.1**。`docker exec trading_postgres psql -U trading_admin -d <db>`。**坑：app role `trading_ai` 在 prod 不存在**（只 trading_admin）→ migration 的 grant 分支在 prod 走「role absent NOTICE」路；要真測 append-only grant 必須在 scratch 自建 `trading_ai` role 讓 GRANT/REVOKE 分支真 fire。

**★ scratch DB 建法（schema-only clone 有兩個真陷阱）**：(1) `CREATE DATABASE` 從預設 template1 在此 TS image **靜默失敗**（無 error 無 DB）→ 必用 `TEMPLATE template0`。(2) **`pg_dump --schema-only`+`timescaledb_pre/post_restore` 不重建 hypertable+compression catalog**——`trading.fills` restore 回來變 plain table（`timescaledb_information.hypertables` 0 rows，雖然內部 `_hyper_NN_chunk` 在）→ 用 schema-only scratch 測 columnstore ADD COLUMN = **false PASS**（等同 Mac mock 盲點）。**修法：手動把 `trading.fills` 重建為 faithful 壓縮 hypertable**（drop→CREATE 對齊 prod 28 欄+`track public.strategy_track`〔dump 把 enum 落 public 非 trading〕→`create_hypertable(ts,7d)`→`SET (timescaledb.compress, compress_segmentby='symbol')`〔對齊 prod compression_settings〕→INSERT 50 row→`compress_chunk(if_not_compressed)`），驗到 `compression_enabled=t`、`compressed_chunks=1/1` 才是真 columnstore。其餘兩 plain target（hypotheses/experiments）schema-only restore OK。

**驗收項 1-6 全 PASS（真 psql 輸出）**：
1. **first-apply** V134→V135→V136 全 `PSQL_EXIT=0` 零 EXCEPTION：V134 兩表+兩 hypertable(created_at/marked_at 7d)、Guard A/B/C 無 raise、trading_ai grant 分支 fired；V135 表+hypertable(ts 7d)+grant fired；**V136 `Guard A PASS` NOTICE + 三 ALTER 全成功（含 fills columnstore）**。
2. **second-apply 冪等** 全 `PSQL_EXIT=0` 零 false-RAISE：所有 IF NOT EXISTS no-op（"already exists/already a hypertable, skipping"）、Guard A 反映既存欄無 raise、**V136 Guard B 三表印 "PASS: already text NULL (idempotent)"**、三 `ADD COLUMN IF NOT EXISTS` no-op（含 fills 二次 ADD 仍不 raise）。
3. **append-only grant**：`has_table_privilege(trading_ai,...)` 三新表 **UPDATE=false DELETE=false INSERT=true SELECT=true**；`information_schema.column_privileges` trading_ai UPDATE = **0 rows**。"column_update_grants_count=39" **全部 grantee=trading_admin（owner 隱含，無害）**，trading_ai 零 column-UPDATE。grep SQL：唯一 UPDATE(col) 命中是**註解**（V134:24 解釋為何避免），**0 條可執行 `GRANT UPDATE(col)`**；所有 GRANT = table-level `SELECT,INSERT` + BIGSERIAL `USAGE ON SEQUENCE`。`consequential_at_creation` 無 UPDATE 路徑（INSERT-set-once）。
4. **★ columnstore-safe ALTER（Mac 絕對測不到、最高價值）**：`trading.fills` 真壓縮 columnstore（compression_enabled=t、1/1 compressed chunk）上 `ADD COLUMN source_l2_reply_id TEXT NULL`（nullable/無 DEFAULT/不 SET NOT NULL）**first+second apply 皆不 raise `feature_not_supported`**（V077/V101 陷阱不觸發）；新欄 `text/YES` 傳播到 compressed chunk（`compress_hyper_2_2_chunk` 顯 USER-DEFINED = 正常 compressed-segment 表示）。ALTER 後 fills 仍 compression_enabled=t、1/1 compressed。
5. **零 column-grant → compression-ready**：因三表 0 條 column-level UPDATE grant，未來開 compression 不撞 V114 compressed-twin 42703 abort（結構性確認）。
6. **★ prod 零觸碰**：dry-run 前後 `_sqlx_migrations` **head=133 rows=116 不變**（親驗 ×2）；prod 0 l2 tables、0 source_l2_reply_id 欄；`trading_ai_sandbox` 鄰庫未動。**坑：role 是 cluster-global**——我在 scratch `CREATE ROLE trading_ai` 後它在 prod `pg_roles` 也可見（但 0 grant/0 owned object，nosuperuser）→teardown 必 `DROP ROLE` 還原（drop scratch DB 先，再 drop role；確認 prod_trading_ai_role=false 復原）。

**回歸（SECONDARY）— redactor 純-Python parity = PASS**：`test_l2_d3_ledger.py` import `l2_secret_redactor`+`l2_call_ledger_writer`，writer 又拉 `db_pool/error_sanitize`，wiring/lessons/cost-tracker 測拉 `layer2_engine/critic/types/cost_tracker`。**不污染真 Linux 樹**：rsync 真 control_api_v1→`/tmp/l2_dryrun/cav1` 再丟新檔（真 runtime checkout 全程零觸碰，親驗 3 新檔仍 absent）。裸 temp 只丟 2 新檔 → 5 fail（`Layer2Session 無 l2_reply_id`/`layer2_engine 無 _get_l2_ledger_writer`/lesson+session redaction）**全是 companion-artifact**：`layer2_cost_tracker/critic/engine/types` 是 **Mac uncommitted `M`**，Linux 是舊 committed 版。逐一 scp 4 companion 後 **full file Linux 78 passed/4 xfailed/0 failed ×2 非 flaky == Mac 78/4/0**（含 4 strict-xfail naked-context-free 高熵殘留兩端同 xfail）→**零真 Linux 分歧**。redactor-only 類 Linux 62 passed/4 xfailed（Mac 同檔 redactor 類 63 passed〔`-k Redactor` 含 fast-path/keyword/sizecap/store-span 子類〕；prompt 引用 272 是跨多檔 layer2-family in-scope 總數，本檔貢獻 redactor 類）。pytest Linux 9.0.2 / pytest-asyncio 1.3.0。

**owed（誠實標）**：**full layer2-family Linux 完整回歸 = owed-post-commit/push**（4 companion + 2 新檔 + test 全 untracked，整包不便在真樹跑；本次以 temp-tree 證 file-level parity，full-suite delta 待 push）。真 sqlx-migrate apply（OPENCLAW_AUTO_MIGRATE）= operator-gated deploy（本 dry-run 純 psql -f，未走 sqlx，prod 未 register 134/135/136）。

**教訓**：(1) schema-only clone 測 columnstore 必先驗 `timescaledb_information.hypertables` 真有 row——pg_dump 不帶 hypertable catalog，restore 回 plain table 會給 columnstore ADD COLUMN false PASS，等同 Mac mock 盲點；要手搓 faithful 壓縮 hypertable（對齊 prod compress_segmentby + 真 compress_chunk）才測得到 V077/V101 陷阱。(2) PG role 是 cluster-global 非 per-DB——為測 grant 分支在 scratch CREATE ROLE 會洩漏到 prod pg_roles，teardown 必 DROP ROLE 並親驗 prod 復原 false（"prod 零觸碰"不只看 schema/migrations 還要看 cluster-global role）。(3) untracked test 依賴 untracked companion production 改動時，Linux temp-tree 跑會以 missing-companion 形式報假 fail；逐一 scp Mac `M` companion 把 fail 收斂到 0 才證「零真 Linux 分歧」，否則 5 fail 會被誤讀成 redactor parity 破。(4) `CREATE DATABASE` 在 timescale image 用 template1 靜默失敗→一律 TEMPLATE template0。

**VERDICT: PASS（ready for PM commit/push；migration dry-run 全綠、prod 零觸碰 133 不變、redactor parity 確認）**。退 E1 清單：無。

## 2026-06-08 · residual PART 4 FINAL regression — whole gap-closure (P1+P2) at HEAD 67730b7b (PASS, ready for PM deploy flag-OFF)
**被驗**：worktree `/private/tmp/wt-residual-act` branch `feature/residual-activation` HEAD `67730b7b`（P2 MIT HIGH-1/HIGH-2）。全鏈 = P1(B+C, `da3aec6f`+`c6cc1578`) → P2 orchestrator(`2a5df09e`→`7d2cdcba`→`67730b7b`)。Python-only。worktree 業務檔 byte-clean（僅 E2 memory.md `M` + 1 untracked PA design doc，非業務）。
**全量決定性 ×3 同綠非 flaky**（`PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0`、先清 __pycache__+.pytest_cache；ml_training/tests+learning_engine/tests）：HEAD = **855 passed / 31 skipped / 0 failed**（run1=35.14s, run2=34.84s, run3 `-p no:cacheprovider`=34.76s，三跑 identical 無 ordering/cache 耦合）。cron tests（`helper_scripts/cron/tests`）= **53 passed ×2**。pytest 9.0.3 / py3.10.1。
**★ 權威 baseline reconcile（throwaway worktree 三點實測，跑完 remove）**：base `8cd4da1f`（origin/main merge-base）= **794/31**（精確）；P1 `c6cc1578` = **827/31**；HEAD `67730b7b` = **855/31**。collect-only node-ID diff（含 sort -u 去重）：base 823 nodes → HEAD 884 nodes，**REMOVED=0 / ADDED=61**（= 855−794）。逐段 0-removed：base→P1 ADDED=33（gate+15/cycle+2/producer_db+11/report_contract+5）、P1→HEAD ADDED=28（orchestrator preflight+26/gate+2）。**skip-set delta = 0**（31 SKIPPED node-IDs base 與 HEAD `diff` 完全相同）。**884 vs 855+31=886 的 2-node 差 = module-level import-skip**（optuna/pyarrow/sklearn/lightgbm 未裝 Mac → 整模組 SKIPPED outcome 但 collect-only 不列其內函數），pre-existing 環境 skip、base/HEAD 一致、非我引入。
**mock-doesn't-hide-logic（P2 orchestrator 新風險面，獨立驗）**：FakeCursor(`_Cursor`/`_DrarStampCursor`/`_Conn`) 只捕 SQL/params+腳本化 to_regclass probe，**不替換** register-extract/persist 邏輯；`_RegisterSpy` 是 capturing wrapper，記錄 bridge **真算**並放進 `body.manifest_jsonb` 的 report+registry_residual_hash（非捏造）；`_patch_db` 只 monkeypatch DB **loader**（IO 邊界），其 `_fake_load_candidate_net_side` 呼**真** `derive_net_side_from_fills`。**真路徑（驅真碼於合成資料）**：`test_six_step_flow`/`test_no_peer_synthesis`/`test_cross_writer_hash_byte_identity_with_permutation`/`test_single_config_defers_pbo` 驅真 `evaluate_cell`+真 `_canonical_sha256`+真 `register_residual_candidate_experiment`；**deciding-factor e2e** `test_beta_trap_end_to_end_gate_vetoes` 驅真 `build_live_candidate_evidence_from_source` on orchestrator 實寫 payload，並做 (A)有report→真 math reason `residual_alpha:passes_not_true` vs (B)無report→`residual_alpha:not_dict` 對照，證 HIGH-1 修復把判據從「缺席默拒」改成「真 math verdict」；per-symbol net_side `test_net_side_per_symbol_overrides_strategy_wide_short`（顯式 mutation guard `assert side_sym != side_all`）+ e2e `test_orchestrator_threads_candidate_symbol_into_net_side` 重現 MIT RAVEUSDT 發散驅真 `derive_net_side_from_fills`；**-0.0 hash** `test_to_dict_normalizes_negative_zero_to_positive_zero`（fixture 以 copysign 證真帶 -0.0）+ mutation-bite `test_negative_zero_drift_without_normalization_would_break_hash`（證未正規化 `_canon_sha256(raw_neg)!=raw_pos`→漂移，正規化後相等）。**唯二 stub-thing 的 `_fake_eval`**（`test_drar_hash_matches_registry_when_report_passes`/`test_pass_report_in_payload_passes_first_gate`）注入合成 PASS report——**非掩蓋 gate**：真 gate 對單配置誠實 defer（無 peer→無 PBO），這兩測只驗下游 wiring（drar hash byte-identity + source-contract 第一道過閘），真 gate veto 路徑由 beta_trap/no_peer 測獨立覆蓋。**無一新測 stub 受測對象**。
**獨立 mutation-bite 親驗**（非盲信）：暫改 orchestrator `load_candidate_net_side(... symbol=symbol ...)`→`symbol=None`（退回 strategy-wide）→ `test_orchestrator_threads_candidate_symbol_into_net_side` **FAIL**（`assert None == 'RAVEUSDT'`），還原後 git diff 業務檔空 byte-clean。
**cross-language float**：N/A（純 Python）。唯一 real-PG 語義點 = `-0.0` PG-jsonb 丟符號位，由 MIT 在 Linux 真 PG round-trip 驗（本 Mac 測在 in-memory 層證 `_normalize_zeros` chokepoint 已先抹平使 jsonb 丟符號成 no-op）。
**behavior-neutrality（triple-OFF → 0 writes / orchestrator unreachable）三層親驗**：(1) orchestrator `run_residual_stage0r_preflight` 三重 gate `cfg.enabled AND stage0r_preflight_enabled() AND residual_producer_enabled()`，任一 OFF 在開 conn 前早退（`test_behavior_neutral_*`/`test_cfg_disabled_zero_writes` 用 conn_factory raise AssertionError 證零連線）；(2) cron `_run_residual_preflight` wrapper 再 check 雙 flag → skipped；(3) `residual_preflight` 在 OPTIONAL_JOBS **非** DEFAULT_JOBS（預設 cron 不 dispatch）。**OFF-path 報告 canonical SHA byte-identity**：`ResidualEdgeReport.to_dict()`（permutation OFF=default→pop 3 perm key）18-key SHA256 = base `8cd4da1f` 與 HEAD 皆 **`5b884182...`**。Gap B/C/D 全純加性。`derive_net_side_from_fills` `symbol=None` default 保留既有 caller 行為；`write_demo_residual_alpha_report` 是從 `_persist_residual_alpha_report` 抽出共用薄 helper（原 caller 改 delegate，behavior-neutral by construction）。
**未改既有測試**：PART 4 只動 6 個 residual test 檔（5 main + 1 cron），0 pre-existing test 檔被改、0 assertion 被刪/弱化（git diff `*/tests/*` non-residual = 空）。
**Linux owed（operator deferred ACTIVATION run）**：branch 未 push、Linux trade-core 在 main@`8cd4da1f` 無這些新檔。flag-ON real-write activation 需 (1) rebase+push+deploy branch (2) signal_spec producer 真啟用仍 pending (3) hidden_oos sealer 真 activation 仍 pending。本次純 Python+test（無 Rust/無浮點跨語言/無新 migration/無 async race 新面）→ Mac pytest ×3 足以建信心；Linux full regression 待 PM 協調 push 後補（且 -0.0 PG round-trip 已由 MIT Linux 驗）。
**verdict = PASS**（ready for PM deploy flag-OFF）。我**未**改任何業務邏輯、**未**新增測試（既有 +61 覆蓋充分含 mutation-bite，無 uncovered regression）。throwaway worktree 已 remove。
**教訓**：(1) collect-only node-ID 三點 diff（base/P1/HEAD 各 throwaway-worktree 實跑）逐段證 0-removed 比單點絕對數可靠——一次釐清 794→827(P1 +33)→855(P2 +28)=+61 全鏈。(2) `--collect-only` node count（884）會少於 `-q` summary outcome（855+31=886），差額 = 整模組 import-fail 的 collection-time SKIP（其內函數無法 collect 故不在 node 列但算 1 SKIPPED outcome）——reconcile 時要認得這口徑差，否則誤判「2 node 不見了」。(3) capturing-wrapper register_fn / FakeCursor / loader-only monkeypatch 是 mock-doesn't-hide 的正確形態：受測對象（gate/hash/source-contract/net_side derive）全真跑，只 stub IO 邊界與捕捉寫入——驗證時要逐測 trace「真 vs stub」分界，並對關鍵 e2e 親做 mutation-bite（symbol-threading 拔掉→測紅）證非 tautology。

## 2026-06-09 · residual PART 4 Gap-A market-basket fix — final regression at HEAD 2fca92fe (PASS, ready for PM deploy flag-OFF)
**被驗**：worktree `/private/tmp/wt-residual-act` branch `feature/residual-activation` HEAD `2fca92fe`（PART 4 Gap A：替換字母序 basket 選取 `sorted(set(active))[:N]`→`load_liquid_basket_symbols`〔read-only count 查詢，按 4h-bar 計數排序，`symbol = ANY(active)` 夾在 PIT-active 集內保 survivorship〕），parent=`67730b7b`（PART-4 FINAL，TODO baseline=855/31）。4 檔改（+314/-3）：`residual_alpha_producer_db.py`〔新 `load_liquid_basket_symbols`+`_LIQUID_BASKET_QUERY`+`__all__`〕、`residual_stage0r_preflight.py`〔`_load_multi_factor_inputs` seam 改 caller〕、+2 test 檔（+4 tests）。E1 已在真 Linux PG 驗（basket 60/60 bar>0、market_buckets=113、gate 產真 report）；E2 PASS（0 finding，survivorship-safe，mutation-verified）。Python-only。worktree 業務檔 byte-clean（僅 TODO.md+E2 memory `M`+1 untracked PA design doc，非業務）。pytest 9.0.3/py3.10.1。

**全量決定性（`PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0`、每跑前清 __pycache__+.pytest_cache；ml_training/tests+learning_engine/tests）**：HEAD `2fca92fe` = **859 passed / 31 skipped / 0 failed**，跑 **5 遍同綠**（含 2 次 `-p no:cacheprovider`，run 23.3–34.0s）非 flake、無 ordering/cache 耦合。cron（`helper_scripts/cron/tests`）= **53 passed ×2**。

**★ 權威 baseline reconcile（throwaway worktree `git worktree add --detach 67730b7b`，跑完 remove）**：parent `67730b7b` 全量 = **855 passed / 31 skipped**（精確等於 TODO header + E1/E2 claim），跑 3 遍穩定。collect-only node-ID diff（normalize 路徑前綴後 sort -u）：parent 884 → fix 888，**REMOVED=0 / ADDED=4**（= 859−855），4 個 ADDED 逐一對賬 = 正是 3× `load_liquid_basket_symbols` unit（`test_liquid_basket_picks_data_bearing_not_alphabetical`/`_respects_limit_keeps_most_liquid`/`_empty_candidates_returns_empty`）+ 1× orchestrator real-seam（`test_load_multi_factor_inputs_selects_data_bearing_not_alphabetical`）。0 regression。**skip-set delta = 0**（`-rs` dump skip nodeid+reason 排序 `diff` = NO DIFF；31 skips byte-identical，全 benign optional-dep/opt-in-PG：sklearn 6/lightgbm 7/optuna 1/pyarrow 1/psycopg 13/real-PG opt-in 3；4 新測加 0 skip、全 RUN+PASS）。

**★ flake 觀察（記教訓）**：剛 `git worktree add` 後的**第一次** combined 跑出現 15 failed/840 passed（全在 `test_residual_stage0r_preflight.py`），但同失敗測試**單獨跑 PASS**、`ml_training/tests` 單獨 629/31/0、`learning_engine/tests` 單獨 226/0、隨後 3 次 combined 重跑全部回到 855/31。判定 = **freshly-created-worktree 首跑 settling 假象**（路徑/bytecode warmup 競態），非 parent 真 regression、非 fix 引入。教訓：throwaway-worktree 首跑要丟棄並重跑數遍取穩定值，勿把首跑假失敗當 baseline。

**mock-doesn't-hide-logic（獨立驗，非盲信 E2/E1）— 命名 real-code-on-synthetic vs IO-boundary stub**：
- **orchestrator real-seam（real-code-on-synthetic）**：`test_load_multi_factor_inputs_selects_data_bearing_not_alphabetical` **刻意不 patch `load_liquid_basket_symbols`**（diff 證：只 monkeypatch lifecycles/klines/funding loaders），驅動**真**選取 seam 經 `_load_multi_factor_inputs` 全鏈；`_OrchCountConn/_OrchCountCursor` 模擬 PG GROUP BY count(*)（不回 0-bar symbol）= IO 邊界；lifecycles 讓字母序前綴空 symbol 全 PIT-active（舊 `sorted(active)[:N]` 必選之）→ 這正是抓「回歸到字母序」的 bite 點。
- **3 units（IO-boundary stub，受測對象真跑）**：直呼**真** `load_liquid_basket_symbols`，`_CountCursor/_CountConn` 只 capture SQL+params 並回腳本化 rows（IO 邊界 stub），函數內部 syms 清洗/空-guard/RealDictCursor row 抽取/append 全真做。`test_liquid_basket_picks…` 另斷言 query-building（`ANY(%(symbols)s)`/`GROUP BY symbol`/`ORDER BY count(*) DESC`/params symbols=候選域/limit/tf）。**無一新測 stub 受測對象本身**。

**獨立 mutation-bite 親驗（2 個，逐一改業務碼跑必 FAIL→還原綠）**：
1. orchestrator seam `load_liquid_basket_symbols(...)`→`sorted(set(active))[:N]`（退回字母序）：`test_load_multi_factor_inputs_selects_data_bearing_not_alphabetical` **FAIL**（basket 選到 0GUSDT/1000000BABYDOGEUSDT/1000000CHEEMSUSDT 空 symbol → 正是修復前 market_buckets=0 根因）；**3 units 仍 PASS**（直呼函數不走 seam）→ 證 orchestrator 測釘 seam-wiring、units 釘函數內部邏輯的分工。
2. `load_liquid_basket_symbols` 末行 `return out`→`return sorted(syms)[:limit]`（無視 DB rows）：`_picks_data_bearing` + `_respects_limit_keeps_most_liquid` + orchestrator e2e 三者 **FAIL**；`_empty_candidates_returns_empty` 仍 PASS（空-guard 在 mutated line 前短路）→ 證 units 真咬 DB-row 過濾/排序非 tautology。
還原後 `git diff 2fca92fe` 業務檔空 byte-clean、grep E4-MUTATION=0。

**cross-language float = N/A**（純 Python evidence lane，無 Rust hot path / IPC / 共用浮點）——明確聲明。

**behavior-neutrality（task 5）**：orchestrator test file = **27 passed** = 26 pre-existing（全綠未動）+ 1 新 seam 測；flag-OFF/default 路徑（`-k behavior_neutral or disabled or zero_writes or cfg_disabled`）= **3 passed**。修復純粹改 `_load_multi_factor_inputs` 內**選哪些 symbol 進 basket**（只在 gate 真計算的 flag-ON reachable 路徑生效），triple-OFF 早退與 zero-write guard 完全未動。未改任何 pre-existing 測試、未刪/弱化 assertion（git diff `*/tests/*` 僅 +4 新測）。

**Linux owed（operator-deferred ACTIVATION run）**：branch 未 push、Linux trade-core 在 main 無此新 commit。flag-ON real-write activation 仍 operator-deferred（E1 已單獨在 Linux PG 驗 basket 60/60 + market_buckets=113 + gate 產真 report）。本批純 Python+test（無 Rust/無浮點跨語言/無新 migration/無 async race 新面）→ Mac pytest ×5 足以建信心；Linux full regression 待 PM 協調 push 後補。

**verdict = PASS（ready for PM deploy flag-OFF）**。我**未**改任何業務邏輯、**未**新增測試（既有 +4 覆蓋充分含雙重 mutation-bite，無 uncovered regression）。throwaway worktree 已 remove。退 E1 清單：無。

**教訓**：(1) 「real-code-on-synthetic」與「IO-boundary stub」要逐測命名分界：orchestrator 測**不可** patch 受測 seam 函數（否則就是當初漏 bug 的同盲點——合成注入繞過 DB 選取），units 才用 FakeCursor stub IO 邊界、函數本體真跑。一條 e2e（不 patch seam）+ N 條 unit（stub IO）的組合才同時釘住 wiring 與內部邏輯。(2) 一對「seam 退回字母序」+「函數無視 DB rows」的鏡像 mutation 能精準分離「seam 是否接對」與「函數邏輯是否對」——bite 1 只紅 orchestrator、bite 2 紅 units+orchestrator，分工被證實非 tautology。(3) `git worktree add` 後首跑可能因路徑/bytecode warmup 競態報假大量失敗（本次 15 failed/840），單測卻 PASS——必丟棄首跑、重跑 3 遍取穩定 baseline，否則誤判 parent regression。

### 2026-06-09 L2 P3a ml_advisory（diagnose/interpret，0 migration）Linux parity + agent.lessons sink grant/schema 回歸驗證

**Trigger**：E2 PASS + E3 PASS + MIT APPROVE-CONDITIONAL（M3 leak-typing / M4 Ollama recall calibration GRANTED；2 sink findings owed-verify）。E4 對 P3a 做 Linux parity + agent.lessons sink grant/schema（MIT S-1 類比）。branch `feature/l2-critic-lessons-tools` @ `6a9dd0f1`（P3a 未 commit）。**不改業務邏輯/不新增測試**。

**VERDICT: PASS。退 E1 清單：無。**

**Linux parity（PRIMARY 1）= 完全對齊 Mac，0 真回歸**：rsync 真 `control_api_v1`(38M/1528f) → `/tmp/l2_p3a_dryrun/srv/.../control_api_v1` + Mac(modified) settings TOML → `/tmp/.../srv/settings/`，`OPENCLAW_BASE_DIR=/tmp/l2_p3a_dryrun/srv`（registry `_default_registry_path` 用 env+parents[5]，base=srv）。**full-tree rsync 一次抓齊所有 companion**（executor import `db_pool/l2_out_of_bound_guard/l2_prompt_contract_registry/l2_secret_redactor/l2_call_ledger_writer`；orchestrator 再拉 layer2_engine 等——全是 Mac uncommitted `M`/untracked），**避開上輪 D3 的 companion-artifact 假 fail 陷阱**（逐 scp 易漏；full-tree 0 drift）。`test_l2_p3a_ml_advisory.py` **53 passed/0 ×2 非 flaky == Mac 53**；layer2-family 8 檔（d3_ledger/p2_orchestrator/p3a/critic/escalation/g3_08/layer2/tools）**439 passed/4 xfailed/0 ×2 非 flaky == Mac 439**（4 xfail=既有 naked-context-free 高熵殘留兩端同 xfail）。**Linux py3.12.3/pytest9.0.2/pydantic2.12.5/tomllib/pytest_asyncio1.3.0 是權威**——Mac py3.10(有pytest+pydantic無tomllib)/py3.12(有tomllib無pytest+pydantic)**雙環境皆無法跑全套**（MIT 同此盲點），故 Linux run 即 parity 權威，誠實標「Mac 53/439 由 E1/E2 建，E4 本地無法獨立重現全套」。

**★ agent.lessons sink grant/schema（PRIMARY 2）= INSERT 有權、非 silent-drop、schema 精確對賬**：**關鍵 reconcile——MIT 報告（早期態）寫 sink=`learning.mlde_shadow_recommendations` direct INSERT（S-1=V037 REVOKE PUBLIC INSERT 致 silent-drop HIGH），但 `6a9dd0f1` 真碼已採 MIT 建議(a)把 sink 搬到 `agent.lessons`(V133)**（executor MODULE_NOTE + `write_ml_advisory_advisory_sink:404` `INSERT INTO agent.lessons(symbol,lesson_type,content,session_trigger,context_id,outcome_net_bps,session_cost_usd,source)` values `(sym,mode,content,trigger,l2_reply_id,NULL,NULL,'ml_advisory')`）。**教訓再現：prompt 與 MIT 都說某事，必讀真碼核對——sink 目標表已變，privilege 檢查對象隨之變**。Linux PG（`trading_postgres`/`trading_ai`）：control_api login role = **`trading_admin`**（db_pool `PG_USER` default + runtime secret URL `postgresql://trading_admin@127.0.0.1:5432/trading_ai` 雙證）。**`has_table_privilege('trading_admin','agent.lessons','INSERT')=true`**（SELECT=true），且 **table owner=trading_admin**（owner 隱含 INSERT，比 V037-affected mlde_shadow〔被 REVOKE PUBLIC INSERT〕結構性更強）；`role_table_grants` 只 trading_admin 全權、**無 PUBLIC REVOKE 模式**→**S-1 silent-drop 風險在 agent.lessons sink 結構性不存在**（E1 搬 sink 消滅了 MIT S-1 HIGH）。**schema 精確對賬**：Linux 真 `agent.lessons` 10 欄 == V133 file（無 drift）；sink 寫的 8 欄全存在型別相容，3 NOT NULL（symbol/lesson_type/content/source）皆得非空值（symbol 空→placeholder 'ml_advisory'；source 顯式 'ml_advisory' override default 'l2_session' 分離 critic namespace），`outcome_net_bps=NULL` 對齊 V133 forward-stub 契約。注意 agent.lessons 現 **0 rows**（critic persist 尚未在 prod 落真 lesson），故「critic 寫成功則 role 有權」無 live 證據可用——但 `has_table_privilege` 直查更硬更定論（critic 同 `db_pool.get_pg_conn`同表同 role，路徑等價）。

**D3 contract_ver（PRIMARY 3）= schema 支援已驗，真 row 雙重 owed**：Linux `_sqlx_migrations` max=**133**（V133 agent.lessons 已 deploy；V134/135/136 **未 apply**=feature-branch operator-gated）。`agent.l2_calls` 表**Linux 不存在**（需 V134）。`record_l2_call(contract_ver=...)` 真 DB 落值 owed-**雙重**：(a) V134 deploy（agent.l2_calls 建表），(b) dispatch 0 production caller dormant（真 dispatch 才產 row）。**schema 支援已驗**：V134 file:124 `contract_ver TEXT NOT NULL` 存在→deploy 後可寫。標 **owed-post-deploy（deployed-E2E）**。

**mock 審查 PASS**：sink 測用 `_conn_provider_factory`→`_CapturingConn`（純 IO 邊界 stub，捕 SQL+params 進 in-memory store）；**業務邏輯全真跑**（content 構造/redactor 真消毒〔spy 驗真呼叫〕/namespace tag/D3 context_id threading/INSERT SQL 構造），斷言真 code 產的 SQL/params（`params[5]=='ml_advisory'`/`'mlde_shadow_recommendations' not in sql`）。**因 conn 是 stub，pytest run 0 真 INSERT 觸 Linux PG**（驗：run 前後 agent.lessons 恆 0 rows）。

**prod 零觸碰確認**：(1) 真 checkout 仍 main@`28e376c0` working tree clean、P3a 檔仍 ABSENT；(2) agent.lessons 0 rows 不變（0 test 污染）；(3) **PG cluster 零 mutation**（無 CREATE ROLE/DB、無 schema 改、只 has_table_privilege+information_schema 唯讀查）——比 D3 上輪「scratch CREATE ROLE 洩 prod pg_roles」更乾淨（本次根本不需建 role/scratch DB）；(4) `/tmp/l2_p3a_dryrun` 已 remove 確認 gone。

**教訓**：(1) **sink 目標表會在 MIT→E1 之間搬家**（MIT 建議(a)落地）：privilege 檢查前必讀「當前真碼」的 INSERT target，不可信 MIT 報告寫的舊表名——本次若照 prompt/MIT 字面查 mlde_shadow_recommendations 就查錯對象。(2) **owner-role 連線比 granted-role 更強且免 PUBLIC-REVOKE 風險**：trading_admin 是 agent.lessons owner→S-1 class（V037 REVOKE PUBLIC INSERT 致 silent-drop）對 owner 不適用；查 grant 要分「owner 隱含」vs「顯式 GRANT」。(3) **deploy-gated 表的真-row 驗證是雙重 owed**（表需 migration apply + dispatch 需 production caller）：只能驗 migration-file schema 支援，真 row 標 deployed-E2E。(4) **full-tree rsync > 逐 scp companion**：untracked test 依賴一串 uncommitted `M` companion 時，full-tree 一次同步 0 drift，逐檔 scp 漏一個就假 missing-companion fail。(5) **Mac 雙 python 環境互補但皆殘缺**（3.10 無 tomllib / 3.12 無 pytest+pydantic）→ L2 全套只能 Linux 跑，E4 須誠實標 Mac 數由前序 agent 建、本地無法獨立重現全套。

---

## 2026-06-10 — L2 P3b Linux 回歸 + altcap real-smoke (E4)

**branch** `feature/l2-critic-lessons-tools` @ `aeae4da4`（P3b 未 commit）。Linux=`trade-core` main@`28e376c0`。temp-overlay 法（rsync program_code+helper_scripts+settings+sql+rust/openclaw_engine/src 到 /tmp，prod 零觸碰）。

**verdict = E4 PASS**（無真回歸；1 forward-integration caveat owed E1/AEG-S3）。

**Linux parity**：P3b 4-suite（altcap/beta_neutral/leak/hypothesize）= **46 passed == Mac 46**，2 run 同綠非 flaky。producer gate（learning_engine+ml_training+research）temp **794 passed / 2 failed**，2 fail = `test_half_life_estimator.py`（pre-existing：Linux 缺 scipy→default_14d，main 亦 fail，非 P3b）。layer2 廣套件 199 passed。

**★ altcap real-smoke（最高價值，QC/MIT owed）真 DB（trading_ai，read-only）**：
- FND-2 型別相容 ✅：`alive_from_utc`/`alive_to_utc` 真型別 = **`str`**（ISO `"2026-03-06T00:00:00+00:00"`），altcap `_to_date()` 正確解析，PIT walk-forward 真跑通。
- market.klines 1d 覆蓋：CORE25 ex-BTC 24 檔中 **18 有資料/6 無**（ATOM/ETC/FIL/ICP/INJ/UNI=0 bars，90d 窗）。basket return series sane：87 bars、0 NaN/inf、range [-0.041, 0.059]、mean 0.00085、N_constituents=18。
- **down-bars 計數**：BTC 1d full=730 bars（2024-06..2026-06）。**integer-bar-indexed**（producer 契約形）：full-span **301**（≈QC/MIT 309，≥30 PASS）、last-90d **16**（<30 DEFER，印證 QC/MIT 23）、last-180d 67（≥30，驗 ≥180d span 設計）。

**★ 真連線抓到 mock 蓋不住的 forward-integration 缺陷（owed E1/AEG-S3，非本輪 blocker）**：`compute_down_market_mask` + 整個 `beta_neutral_check` gate 經 `_parse_series`→`residual_alpha_gate._parse_candidate_returns`，其 `_in_fit_scope` 用 `_WideFitWindow` 的 `±inf` 邊界。**date/datetime/str key 與 ±inf 比較 raise TypeError→`_is_ordered_or_equal` 吞掉回 False→全 temporal-key row 被 silently drop→empty mask/empty series**。只有 **int(bar-index) key** 過。unit test 全用 int key 故綠，但**真 market.klines date-key 路徑→0 down-bars（我初跑 date-key=0，int-key=301 才對上 309）**。教訓再現「真連線 smoke > mock」。**caller**：`l2_ml_advisory_executor.py:1120 _run_b1_stage` 從 `gate_inputs` dict 取序列，**目前無 production 路徑 populate 真 market 序列**（AEG-S3 候選接口未建，缺→DEFER fail-closed），故 latent 非 active bug。**E1/AEG-S3 接真資料時必須把 candidate/btc/altcap/mask 全 re-index 成共同 int bar-index，否則 universal silent DEFER**。

**66 control-plane fail 分類**：CSRF_SHADOW OFF→**66 failed**（main 4371 passed，write-endpoint 403 enforcement-mode，documented mutually-exclusive，0 碰 P3b）。CSRF_SHADOW=1→main **6 failed**（全 `test_ops1_csrf_middleware.py` enforcement 測，反向 mutually-exclusive）。temp overlay 多 3 fail（batch_b/batch_d/sm_contract_parity）**經驗證在 main 全 PASS = temp 缺檔 artifact（rust/openclaw_core/tests/fixtures 等未 rsync）非真 fail 非 P3b**。

**陷阱記錄**：temp-overlay 法初跑漏 sql/ + rust/ → 25 假 fail（V082/V084 SQL read + 跨語言 Rust source read FileNotFound）；補 rsync 後歸零。branch divergence：main 有 residual-producer 8 test 檔我舊 branch 無（103 test gap，非 P3b）。**結論：temp 多 fail 全為 (a)缺 scipy (b)temp 缺檔 (c)CSRF mode — 0 P3b 真回歸**。

**owed（operator/E1）**：V127 population（regime-labels seed）、agent.lessons seed、★B1 gate temporal-key re-index（AEG-S3 wiring 前必修）、6 ex-BTC symbol market.klines 1d 覆蓋（ATOM/ETC/FIL/ICP/INJ/UNI）。prod 零觸碰，temp 已清。

- 2026-06-10 BASELINE 重置：舊基線（2555/17）隨配置遷移作廢；下次全量回歸建立新行（格式: BASELINE: YYYY-MM-DD passed=N failed=M）

## 2026-06-10 · OPS-2 Phase-2 cutover 全回歸 @ `cf1b9320`（PASS；E4 +1 測試 `e34a8772`）

**被驗**：worktree `/tmp/wt-ops2-cutover` branch `fix/ops2-phase2-cutover`，`a3d27729`+`cf1b9320` off main `28e376c0`（E2 兩輪 ACCEPT）。移除 secret-split Phase-1 IPC fallback，env 缺失 fail-loud。報告 `2026-06-10--ops2_phase2_cutover_regression.md`。

**數字（全親跑，跑兩遍同綠）**：Rust full `--no-fail-fast` 43 targets = **4154/1/4ign ×2**（唯一紅 = stress_tick_latency_benchmark；total 4155 == E1/E2）；Python（venvs/mac_dev 3.12.13）`pytest tests/ --ignore=tests/replay` = **66 failed/4256 passed/6 skipped ×2**，FAILED 清單 run1==run2 byte-identical；+E4 測試後 = 66/4257/6。base `28e376c0`（自建 throwaway worktree）= 66/4255/6，**FAILED 66 條整列 diff = 空**（勝過抽 5 條）；probe 1 條 = 403 write-endpoint = Mac CSRF-enforcement 環境 artifact（無 CSRF_SHADOW=1 → 66 紅 mode，與 2026-05-30 F-NEW-1 一致）。

**★ stress flake 裁定 SOP（記住此法）**：兩輪 full 紅（1135.5/1117.3μs vs <1000μs debug）→ (a) 結構：PR 0 觸碰 stress 檔；(b) HEAD standalone ×3 = 1059-1073μs 全紅；(c) **base standalone ×3（共享 CARGO_TARGET_DIR 重編 base，省 dep 重編）= 1068-1076μs 全紅** → base 本機今日同紅且 HEAD 值不劣（均值 1066.7 vs 1072.3）= 環境性非回歸，tick path 零劣化。跨 session（E1 紅/E2 紅/E1-fix 綠）= session 噪音。**獨立重做 base 裁定而非沿用 E1 stash 證據**。

**測試數對賬（名字級，非僅總數）**：Python `def test_` 4316→4317(+1=記帳)；Rust `#[test]` 4186→4189(+3=main.rs ops2 mod)。名字 diff：Rust live_authorization 24→24（刪 `phase1_fallback_reads_ipc_secret_when_live_auth_unset` + rename `primary_wins_over_ipc_fallback`→`primary_read_ignores_ipc_secret`，+`ipc_secret_alone_no_longer_provides_signing_key`）；Python secret_split 8→9（刪 3 WARN + 1 rename，+5 新負向）。**被刪全為被移除功能（Phase-1 fallback）的行為測試且有「fallback 已死」負向取代 = 合法刪除類**；0 靜默消失。坑：zsh `$rev:rust/...` 會吃 `:r`（modifier）→ 必 `${rev}:path`。

**mock-bite 親驗**：promote gate-chain 測試非 mock 短路——毒 `_read_live_auth_signing_key`→`""` → 紅 403 `gate_failed=authorization`+Phase-2 hint（真走 live_preflight HMAC 驗證）；還原 byte-clean。四象限（Rust panic live/非 live 不 panic/Py sign raise/Py verify reason）+ Rust verify 負向 + cross-lang pinned `1b2b18d7…78fc` 雙端全綠 named-run 親驗。

**E4 新增 1 測試（缺口真實非為加而加）**：gate-chain 層唯獨缺「授權檔有效+簽名 key 缺」永久負向（grep tests/ 0 檔引用 live_preflight；E2 Finding-1 正是此 surface 顯形）→ `test_live_flip_signing_key_missing_403_authorization`（toggle gate-5 cluster；legacy IPC 在場不得救；hint 含新 env 名）。bite：暫重加 IPC fallback → 此測試紅 → 還原。commit `e34a8772`（僅測試檔）。

**教訓**：(1) 負向測試的 mutation-bite 方向是「把被禁行為加回去」（重加 fallback→測試應紅），不是把正路徑弄壞；一條 bite 同時證測試非 tautology + 鎖回歸方向。(2) base-side flake 裁定用共享 CARGO_TARGET_DIR 重編 base worktree（dep 全 reuse，僅 workspace crates 重編，分鐘級）；跑完把 HEAD 重編回來恢復 cache 一致。(3) full-suite 下 timing benchmark 值（1135μs）vs standalone（1066μs）差 ~7% = suite 負載，flake 對比必 standalone-vs-standalone 同條件。(4) patch.dict(os.environ) context 內 pop 是安全 hermetic 手法（退出整體還原）——unittest 風格檔內清 env 不需 monkeypatch。

**VERDICT: PASS**（Linux full regression owed 隨 merge+`--rebuild` 部署 gate；origin/main 已進 L2 Mesh 7 commits，E2 證 0 overlap）。退 E1 清單：無。
