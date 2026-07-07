# QA Memory — 工作記憶

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾

## 長期教訓

1. 健檢「keyspace/row-count 通過」≠「value-realism 通過」：aggregate PASS 後必抽 5-10 樣本看真實 value（filled_qty=0/'unknown' 全 PASS 是已踩盲點）；hand-tuned ratio gate 偵測不到 silent-drop，能改就改 deterministic per-row bidirectional invariant。
2. Producer/code 存在 ≠ 真的在跑：必 grep 帶括號的真 caller（`foo(`），0-caller 要雙向證（caller 端 + route/consumer 端）；區分 dead-code、by-design dormant scaffold（讀 dispatch packet/design 的 step/phase 拆分）、真 wiring gap——scaffold 測試 PASS ≠ runtime EV，兩階段不可混算。
3. Deploy 狀態必獨立驗、不信 PM/prompt 斷言：git 三角（`rev-parse HEAD` + `status --porcelain` + `rev-parse origin/main`）+ `/proc/<PID>/environ` env 注入 + 檔案存在 + running binary/process mtime；「fix 已 land」≠ runtime 配套完成（R3 5-round 6-layer blocker 鏈：Python fix 全對、deploy infra 配套 3/4 漏）。
4. endpoint 200/503 都不可盡信：200 必驗 downstream effect（DB row/artifact 真落地）；503 不代表 subprocess 死（control plane 與 data plane 可分裂）；silent-dead subprocess 必 ssh 手動同 argv reproduce 拿 stderr 才談 root cause；spawn 類設計 stderr 必落檔、禁 DEVNULL。
5. 驗收 SQL 紀律：先 `\d`/information_schema 驗 column 再寫（plan 給的模板常不對齊實際 schema）；deploy-cutoff/窗口時間一律 `+00`::timestamptz 強制 UTC（CEST 陷阱實踩 missed_n 假性 18）；寫 `learning.*`/`trading.*` 的 INSERT SQL 需 writer schema-grep regression（source-loader test 不 cover writer）。
6. 小樣本 binomial gate 必用 Wilson 95% lower bound（禁 naive 比例/normal approximation）；projection 數字必跑 empirical PG query 驗（E1 估值曾 +28% 通膨）+ 附 ±20-40pp drift sensitivity table；pilot/觀察窗長度由 empirical sample velocity × Wilson 收緊需求決定，窗中 verdict 看 projection 不只看當前值。
7. 短窗 snapshot 不可外推 long-term（orphan ER：deploy+78min 看 3% drop → +15h 實為 19-26%）；audit 必標 sample window + 外推風險；wiring correctness ≠ propagation rate，`try_send`/fail-soft 路徑必驗長窗 drop rate；engine restart 不是 throughput fix。
8. Engine alive 3-tier（PID + binary mtime + pipeline_snapshot mtime）之上還要第 4 tier「業務 path 最後 fire 時間」：process 活 ≠ 業務鏈 active（close_maker 28h stall 實例）；`ps -o etime` 是 MM:SS 易誤讀，必雙確認 `etimes`/`lstart`；engine log 是 binary blob 不可 strings 撈舊值，累積指標靠 snapshot JSON。
9. V### migration 雙路 verify：(a) `pg_get_constraintdef`/`\d` 證 runtime 真 live；(b) `_sqlx_migrations` register row 存在。raw `psql -f` apply 會留 register gap；checksum drift 與 raw-apply 是兩種根因、治本不同（repair_migration_checksum vs role + sqlx_migrate run），勿混。
10. QA 邊界 = 驗證 + push back，不 self-fix：知道修法也禁 patch 業務代碼/執行 IMPL/git stash-pull；fix 選項與 effort 估算寫進報告給 PM 派工；read-only 測試親跑屬 QA scope（不改碼/不動 runtime）。
11. 「前序全 PASS」必三角驗：report 檔缺席先 grep 各角色 memory.md 條目（合法 sign-off 載體，E3 慣例不存 .md）+ on-disk 真碼 + 自跑測試；design doc/上游 audit 的「現狀描述」帶 HEAD 戳記會過期（operator 中途 sink-move 使 MIT finding 失效實例），必對驗收 HEAD 重 grep INSERT target/接線。
12. 帶 premise 的驗收任務必先用 production 數據驗 premise 真偽（「bb_breakout 卡 BTC only」被 intents 數據證偽）；deploy/restart 時間別信 prompt 單點，用 `git log -S <fix-token>` + engine log 時間軸交叉定真 evidence window。
13. by-design 0-caller/dormant vs unwired 必分清；verdict 用 PASS WITH CAVEAT / KNOWN GAP / CONDITIONAL 精準分級；preventive fix 無觸發樣本時找「fix 在則必成立」的不變量給 PASS（如 runtime_bps==shrunk_bps 恆等），不硬判 INCONCLUSIVE；行為一致性推斷與正向確認要明文區分。
14. spec literal vs 現實漂移高頻：INSERT 範例缺 NOT NULL column、spec column 名 vs migration 實際 schema、script flag 不存在、test name 不符——採納 spec/dispatch literal 前必 cross-check `\d`、`<script> --help`、`cargo test -- --list`；grep-0 類 AC 要排除 RAISE/註解 context 再判。
15. 殘留誠實三件套：code-comment 記真實 RETURN 歷史 + 對抗 probe 量化邊界 + xfail(strict) 鎖契約（缺 strict 殘留會 silent regress 成 claimed-covered）；writer test 充分性看 inspect 真寫入點 call_args（非 return value）+ 雙向不變量（hash==sanitized AND hash!=raw）。
16. sign-off 分類紀律：criteria 拆 PASS-AUTO vs PENDING-operator/runtime 給 ratification 一眼可讀；scope 內 PASS 與 cross-scope dependency PENDING 不可混算 FAIL；APPROVE-CONDITIONAL 報告必附建議 commit subject/body 與條件清單。
17. 多 review 全綠後 QA 增量價值 = 業務鏈連貫 + cross-module 一致 + 獨立 ssh 全鏈 smoke 找 hidden risk（V099/V113/engine-dead 全是 sub-agent diff-scope review 看不見的 cross-cut）；獨立 verify 腳本（直接 parse CSV/DB 重算 gate）附報告供重跑。
18. 場景化規則勿誤套：close-maker 分析 post-deploy real verification 用 attempt × fallback matrix（禁 `oc_*` prefix 拆法）、pre-deploy replay harness 用 attempt-axis 分母；entry vs risk_exit 分流僅 spine lineage 場景適用；批次 deploy 同檔多 commit 必 `git diff` 看 hunk 行區判衝突。
19. pre-deploy green gate ≠ deployed-E2E：undeployed/uncommitted/dormant 條件下 deployed-E2E 結構性不可做，明標 owed-post-deploy 不假造；Mac/Linux 雙端 test count+skip+warning 一致是 cross-arch parity 證據（ssh 非互動 shell 需 `~/.cargo/bin/cargo` 全路徑；單層 ssh 才走 publickey）。

## 近期記錄

## 2026-06-02 P5 SM Option2 step-i chain-level E2E acceptance（HEAD e6aa5e37）

| 報告 | 日期 | 關鍵發現 |
|---|---|---|
| 2026-06-02 P5 step-i 業務鏈端到端驗收 | 2026-06-02 | **PASS（soak runtime gate operator-timed 除外）**。step-i 整條 lease IPC 權威路徑逐環接上、無 bug/gap/邏輯錯/斷線接線。Mac+Linux 雙端 133 passed/1 skipped（同 skip 同 warning，cross-arch parity）；Rust governance_ipc 13 passed + sm_contract 1 passed（Linux release 權威）。設計 doc 在 HEAD 344025f9 標的兩個 half-wire gap（§0.1 Rust 無 lease dispatch arm；§0.2 flag 不在 restart_all.sh）都被 a99bfa1d+e6aa5e37 關閉。flag-OFF 為當前 production 真實態（API PID 1804292 env empty/absent，basic_system_services.env 無此 flag）= dormant byte-unchanged。報告直接在主 session 輸出（未寫 .md）。 |

### 1. 「設計 doc 寫 half-wire」≠「現 HEAD 仍 half-wire」— PA design doc 的 HEAD 戳記是關鍵
SM Option2 migration design doc 自身標 `@ main HEAD 344025f9`，其 §0 "load-bearing reality corrections" 列「Rust 無 lease dispatch arm」「flag 不在 restart_all.sh」兩個 half-wire。但驗收標的 HEAD 是 `e6aa5e37`（design doc 之後 +2 commit：a99bfa1d Rust + e6aa5e37 Python）。QA 不能直接採信 design doc 的 reality correction 當現狀——必須對**驗收 HEAD** 重 grep：`dispatch.rs` 現有 7 個 `governance.*` arm；`restart_all.sh:717/734` 現讀+export flag 到 uvicorn。教訓：design doc 的「現狀描述」帶 HEAD 戳記，跨 commit 後即過期；驗收必以標的 HEAD 的源碼為準。

### 2. comparator「3 軸」死角分析必算「兩側皆有意見才算分歧」的覆蓋空間
governance_divergence.record_divergence 核心：`no_opinion = (rust==UNKNOWN or python==UNKNOWN); match = no_opinion or rust==python`。三軸覆蓋：(a) **auth-axis**（acquire 開頭 Step-2 前，is_authorized IPC vs 本地，雙向 grant/deny 全覆蓋，解 E2 HIGH#5 近盲）；(b) **acquire scope-axis**（rust acquire outcome vs Python 完整影子=is_authorized AND auth_permits_scope，雙向）；(c) **release/get presence**（steady-state Python 無意見=UNKNOWN→no-opinion 不算分歧，A3 修 over-fire；本地真持有相反才 fire）。**無死角**：acquire 時授權空間（auth + scope）被 a+b 雙向覆蓋；release/get 弱通道的 UNKNOWN 是「Python 在 flag-ON 下對 Rust-held lease 真的無獨立意見」的正確語義，記分歧才是 false-positive。驗收必跑 bite test 證每軸真能 fire：`test_auth_axis_rust_grants_python_denies...production_path`（NO monkeypatch，真 production 路徑，divergences==1）+ `test_flag_on_forced_divergence_bite...`（acquire-axis，divergences==1）。

### 3. soak instrument readiness = counter+consumer+sink+gate 四件全接，且 flag-OFF 時 total 恆 0
step-i 完成 gate 靠「0 divergence over N」，必驗：(a) `_COUNTERS{total,matches,divergences}` 單調不隨 ring FIFO 失真（cap 2048 但 counter 先累加）；(b) consumer = `/governance/health-check` POST route `governance_extended_routes.py:428-429` 真 surface `health["lease_ipc_divergence"]=get_divergence_counters()`，且包 try/except 不讓缺 comparator 弄崩 health-check；(c) sink+counter+lock 三 singleton 已登記 `singleton-registry.md §2.5`；(d) gate 讀法 = `divergences==0 and total>=N`。flag-OFF 時 acquire/release/get 不走 IPC 比對分支 → total 恆 0（route 仍回欄位但全 0）。

### 4. flag-ON + engine-down 下每筆 acquire 都記 divergence(rust=denied/python=granted) 是 feature 非 bug
`test_flag_on_ipc_error_fail_closed_records_deny_outcome`：IPC down → acquire 回 None（fail-closed，不靜默 fallback local SM）+ comparator 記 rust=DENIED vs python=GRANTED 分歧。這正確：soak 期間 engine 不健康會被 divergence counter 大聲 surface，**阻擋 step-ii/iii 晉升**——這是 soak gate 的設計目的。QA 不可把它誤判成 comparator over-fire bug。

### 5. step-i vs step-ii scope 邊界：Rust 把 7 method 全建好（additive），Python 只接 step-i 需要的 4 個
Rust dispatch 有全部 7 arm（3 lease + is_authorized + get_status + list_leases + get_risk_state）且全 13 test 過。但 Python 端只 wire 了 4 個：acquire/release/get（lease 操作路由）+ is_authorized（auth-axis comparator 源）。`get_status`/`list_leases`/`get_risk_state` **Python 無 METHOD 常數、無 _via_ipc consumer**，`hub.get_status()`（governance_hub_cascades.py:118）仍讀 local SM。這**不是 step-i gap**——design §5 step-(ii) 才是「Python projection 切讀 Rust」。Rust 提前建好（additive/dormant/tested）讓 step-ii 變純 Python change。QA 驗收這類 staged migration 必對照 design 的 step 切分判「未接 = 該 step 不需要」vs「未接 = 真 gap」，不能見 Rust 有 arm 而 Python 沒接就報 dead-wire。

### 6. drive_lease_expiry 在 step-i flag-ON 下仍驅本地 SM（空集），expiry 真權威在 Rust tick actor — step-ii 收尾項非 step-i bug
`governance_hub.drive_lease_expiry()` step-i 未改，仍 `_lease_sm.check_expiry()`。flag-ON 下 Rust-acquired lease 不在 local SM → 回 []。benign：Rust `GovernanceCore::check_expiry` 每 tick 跑 = expiry 真權威。design §1.3 標 step-ii/iii 把它降 no-op/projection。step-i「local SM 作 safety-net 並行」by-design，故未改 expiry 不是斷點。

### 7. cross-arch acceptance：Mac+Linux 同 test count/skip/warning 是 parity 證；ssh cargo 需 ~/.cargo/bin 全路徑
本次 Mac 133 passed/1 skipped/3 warning == Linux 完全一致（pytest-asyncio 9afb811a 已關 Linux async skip 洞，step-i async 測試兩端皆 run）。Rust 權威跑 Linux release：`ssh trade-core` non-interactive 不載 .bashrc → `cargo` 不在 PATH，須 `~/.cargo/bin/cargo`；workspace 在 `srv/rust/`（非 srv 根）。inline-module test（src/.../tests/governance_ipc_tests.rs）走 `Running unittests src/lib.rs` 段，整合 tests/ 目錄 0 matched 是正常（filter 不命中整合 bin）。

## 2026-06-03 alpha hygiene 4-fix post-deploy 驗收教訓（A-1/A-2/B/A-4，commit 324001c3）

| 報告 | 日期 | verdict |
|---|---|---|
| 2026-06-03 alpha hygiene A-1/A-2/B/A-4 post-deploy | 2026-06-03 | A-2 PASS（直接 runtime 證據）/ A-4 PASS（不變量證據，無正 cell 可激）/ B INCONCLUSIVE-needs-more-runtime（gate 行為一致但 0 post-gate fire；複查 2026-06-10）/ A-1 INCONCLUSIVE + 前提證偽（intents 數據顯示 bb_breakout 一直是 non-BTC 主導，非「卡 BTC only」；複查 2026-06-10）|

### 1. deploy 邊界要從 commit timestamp + engine restart log 推，不能信 prompt 給的「engine 6/3 00:40 重啟」單點
prompt 說 engine 6/3 00:40 restart（PID 2269678）→ 直覺以為 4 fix 只跑了 ~1h。實查 `git log -S require_mean_reverting_regime` 揭 4 fix 全在**單一 commit 324001c3（2026-06-01 21:19:35）**，engine-log mtime 顯示 6/1 21:24 就有一次 restart（commit 後 5 分）。A-2 的 `reject_other` 在 6/1 21:21 精準停寫＝6/1 21:24 engine 已帶 fix。**真 evidence window 是 ~1.2 天（6/1 21:24→now），不是 1h。** 6/3 00:40 rebuild 只是把同 commit 帶進新 binary。SOP：post-deploy 驗收先 `git log -S <fix-token>` 找 fix 真正落哪個 commit + `ls /tmp/openclaw/engine_logs/` 看 restart 時間軸，再對齊 DB 行為轉折點，不要單信 prompt 的「重啟時間」。

### 2. A-2 qty_zero 噪音的 reject_reason_code 是 `reject_other`（catch-all），不是字面 `qty_zero`
qty_zero reason 字串（router PNL-1 `qty_zero: final_qty=...` / 交易所取整 `qty_zero: exchange_precision_rounding_to_zero...`）不匹配 V086 12-enum 任一 prefix → 全落 `reject_other`（reject_reason_code.rs:138 catch-all）。驗證命中：`learning.decision_features` `reject_other` all-time 318768，其中 **BTCUSDT 313196（98.25%）**＝確認歷史噪音是 BTC 精度取整；`reject_other` last ts **2026-06-01 21:21**（fix deploy 點精準停）；6/3 00:40 後 0。同期 cost_gate reject 仍 01:46 活躍＝reject-write 路徑沒死，只是 qty_zero 停。**教訓：驗 reject 是否停寫，要先 grep Rust `map_reject_reason_to_code` 確認該 reason 映到哪個 code（多半 catch-all），不能直接 `WHERE reason ILIKE '%qty_zero%'`（trading.intents details 無 reason key，rejects 早就不寫 intents 了）。** qty_zero_skips counter 在 pipeline_snapshot stats（live=9/demo=0），確認 skip-not-reject 真生效。

### 3. A-4 edge_estimates 是 JSON 檔不是 DB 表；「無正 cell」時用 runtime_bps==shrunk_bps 不變量證明歸零已移除
`settings/edge_estimates.json`（demo，Rust 讀）+ `edge_estimates_live_demo.json`，非 PG。A-4 移除 Python 歸零後新碼 `runtime_bps = shrunk_values[i]`。當前 demo grand_mean −12bps → **0 個正 cell**＝歸零分支（shrunk>0 & unvalidated）根本不被激。但仍可證：兩檔 **runtime_bps==shrunk_bps 100%（192/192 + 174/174，0 mismatch）+ 0 個 OLD-BUG signature（shrunk>0 & runtime==0）** + cron updated_at fresh（6/3 01:42）＝歸零邏輯確定移除。**教訓：preventive fix 在「無觸發樣本」時不要硬判 INCONCLUSIVE；找一個「fix 在則必成立」的不變量（此處 rb==sb 恆等）即可給 PASS，並明標「當前無正 cell 故未在差異化場景下實測」。**

### 4. B regime gate 讀 in-memory Hurst regime，DB 無持久化 → 靠 pipeline_snapshot indicators 的 hurst regime 分布做行為一致性推斷
bb_reversion gate 讀 `ctx.indicators.hurst.regime`（"mean_reverting"=AntiPersistent，hurst.rs:70/83），**不持久化**：`market.regime_snapshots` all-time **0 row**（producer flush_regime_snapshots 沒在跑）；`trading.intents.details.scanner.market_regime` 是**另一套 scanner 分類**（range_bound/quiet/trending/one_way_shock），非 Hurst 標籤，不能當 gate 輸入證據。可用證據＝ `pipeline_snapshot_demo.json` indicators 31 symbol hurst regime 分布：random_walk 26 / trending 4 / **mean_reverting 1**。gate fail-closed（非 mean_reverting + None 全 skip）＝當下只 1/31 symbol 可入場 → 完美解釋「6/3 00:40 rebuild 後 bb_reversion 0 fire」。**但這是行為一致性（gate 邏輯+regime mix 解釋 0 fire），非正向確認（0 post-gate fire 無法觀測 accept 路徑真的在 mean_reverting 放行）。** Hurst 指標 31/31 非 None＝gate 有真輸入。verdict INCONCLUSIVE-needs-more-runtime（code/test 級已 PASS by E1/E2/E4，runtime 正向 fire 需更多時間）；複查 2026-06-10。

### 5. A-1 premise（bb_breakout 卡 BTC only）被 production intents 數據證偽——QA 要查 premise 真偽不能照單接受
prompt 說 bb_breakout「先前被某 gate 卡死只剩 BTC」。實查 35 天日線 BTC vs non-BTC intent：**每一天都是 non-BTC 壓倒性主導**（5/7 non-BTC 197 跨 6 symbol / 5/8 164），全期 **BTCUSDT 僅 4 筆**。bb_breakout 從來不是「只剩 BTC」，反而 BTC 幾乎不 fire。且 `enable_oi_signal=false`（demo/live/paper TOML 全 false）＝OI gate 的 `return vec![]` 阻斷路徑（舊碼在 false 時仍 skip OI-cohort-missing 的 non-BTC）邏輯上 fix 對，但 non-BTC 既然一直在 fire，OI gate 顯非 intents 層的 binding constraint。近期 bb_breakout 近全休眠（7d 僅 1 intent ICPUSDT 6/2，已是 non-BTC）＝cost_gate/confluence 不對齊主導，非 OI gate。**教訓：QA 收到帶 premise 的驗收任務（"先前被 X 卡死"），必先用 production 數據驗 premise 本身；本次 premise 證偽 → A-1 fix code 正確但「外幣恢復」無正向 runtime 證據可立（bb_breakout 活動量太低且本就 non-BTC）。signal 層（pre-cost-gate）OI gate 影響不落 decision_features（只記 post-cost-gate-eval）也不落 snapshot signals（那是 scanner 信號非 strategy 信號）＝OI gate 的 vec![] 抑制在現有持久化面不可觀測，只能靠 code+test。**

## 2026-06-08 · L2 D3 Phase 1（D3 Provenance & Audit 地基）pre-deploy 驗收 sign-off — PASS (green gate ready)

| 報告 | 日期 | 關鍵發現 |
|---|---|---|
| 2026-06-08 L2 D3 P1 pre-deploy QA acceptance | 2026-06-08 | **PASS — pre-deploy 範圍 green gate ready**。獨立驗收（不重做 E2/E3/E4 行級），驗組裝後整體達 P1 驗收標準 + 業務鏈連貫。執行方案 §2 P1 + L2_TODO §4 P1 逐條 MET。deployed-E2E（真引擎→真 prod ledger row）= owed-post-deploy（系統未部署、P1 未 commit、dirty tree branch `feature/l2-critic-lessons-tools` HEAD `6d312405`），明標未做不假造。 |

### 1. 前序鏈「PASS」證據可能不在 dated report 而在 agent memory（dirty tree 的 M 檔）
任務說「PA→E1→E2→E3→E4 全 PASS」但 `E2/E3/E4/workspace/reports/` 無本work dated .md（最新 E2=5/18、E3 無、E4=5/2）。**真證據在 `docs/CCAgentWorkSpace/{E2,E3,E4}/memory.md`（git status 顯示這些檔正是 modified `M`）**。E2 memory:5044/5063/5086 = v2 RETURN(29% over-redaction 24-case corpus 實測)→v3 RETURN(CRITICAL-1 fast-path gate leak 自抓 E1 測試未覆蓋)→v4 PASS to E4(78pass/4xfailed/0XPASS)。E3 memory:360-385 = redactor v3 E3 PASS + v4 LOW-1/LOW-2 閉。E4 memory:5265-5281 = V134/V135/V136 Linux PG 雙-apply 冪等 dry-run PASS。**教訓：QA 接「前序全 PASS」任務，前序 report 缺席時先 grep 對應 role 的 memory.md（尤其 dirty tree 的 M 檔），E3 慣例「返回 text output 給 parent 不存 .md」更要查 memory。別因無 dated report 就誤判鏈斷。**

### 2. E4 Linux PG dry-run 證據是 deployed-E2E 的「合法替代」但兩者範圍不同，不可混淆
E4 memory:5274-5279 的 dry-run 是真 Linux PG（容器 `trading_postgres`，scratch DB，prod `_sqlx_migrations` head=133 前後不變親驗×2 = 零觸碰）：first-apply 三 migration PSQL_EXIT=0、second-apply 冪等零 false-RAISE、append-only grant 實證（`has_table_privilege(trading_ai)` UPDATE=false DELETE=false / `column_privileges` UPDATE=0 rows / 唯一 `GRANT UPDATE(col)` grep 命中是註解 V134:24）、trading.fills columnstore ADD COLUMN 不 raise feature_not_supported。**但這驗的是「migration SQL 在真 PG 安全且冪等 + grant 生效」，非「真引擎跑真 L2 call→真 prod ledger row」**。後者（producer 端 runtime：engine `:655` `_record_l2_call_to_ledger` 在真 manual-trigger POST /trigger 下真寫一列 + forensic SELECT 讀回）= owed-post-deploy，需 commit + deploy + restart 才可驗。**教訓：sqlx migration dry-run PASS ≠ end-to-end runtime PASS；QA verdict 要把「schema/grant 已 Linux 實證」與「producer runtime row 未實證（owed）」分兩欄寫，避免 PM 誤判 P1 已 deployed-verified。**

### 3. 業務鏈連貫性驗收 = 把 forensic 協定每一查詢步對到「真欄 + 真索引」，非只看表建出來
§D.4 fault-localization 協定 4 步逐一對 schema：step1(source='l2'?)←V136 `source_l2_reply_id` 三表 NULL=non-L2；step2(`SELECT * FROM agent.l2_calls WHERE l2_reply_id=?`→full prompt+response+tags+contract/schema_ver)←V134 ledger 24 欄全含 + PK `(l2_reply_id,created_at)` 服務 WHERE；step3(`...l2_gate_seam_log WHERE l2_reply_id=?`→哪 gate/applied_as/applier)←V135 `idx_l2_gate_seam_reply ON (l2_reply_id,ts DESC)`；step4(replay 同 contract_ver+input_context)←ledger `input_context` JSONB(FULL)+`contract_ver`。**4 步全有真欄真索引背書 = 業務鏈（call→sanitize→ledger→forensic query）連貫**。producer 可達（engine:655 真接線，test `TestEngineWiring` 證非死碼），reader 正確 P2-deferred（singleton registry §2.6 caller_chain 明寫 consumer 在 P2 接）。**教訓：D3/audit-層驗收的「業務鏈連貫」不是跑交易鏈，是驗「operator 月後拿一個 bad param 能否照協定查到全 prompt+response+gate-seam」——每步 SELECT 的 WHERE 欄與 ORDER 都要有 index 命中，缺一即協定半癱。**

### 4. test「驗意圖」的判準：sanitize 用 param-inspection 不用 return-value、sha256 比對原文必證 !=
`test_l2_d3_ledger.py` 78pass/4xfailed bite 充分：sanitize 在 INSERT 前 = 從 mock cursor 取 `execute.call_args` 的 params tuple 斷言「無 secret verbatim + 有 `[REDACTED:*]`」（驗真寫入路徑非 return）；sha256-over-sanitized = `stored_psha == sha256(sanitized)` **AND** `stored_psha != sha256(raw_prompt)`（雙向證 hash 算在已消毒文本）；str(e) 不 verbatim = inject DSN exception 斷言 params blob 無 `fakepassw0rd` + `error_code==classified`;INSERT-only = 遍歷 `execute.call_args_list` 斷言每條 `UPDATE/DELETE not in sql`；store-original = 零-secret 輸入 `r.text.encode()==src.encode()` byte-identical；殘留 4 軸 `xfail(strict=True)`（0 XPASS 證殘留契約完整，誤「修好」會 strict-fail 逼 review）。**教訓：audit-層 writer 的 test 充分性看「是否 inspect 真寫入點的 args 而非信 return dict」+「不變量是否雙向（hash==sanitized AND hash!=raw）」+「殘留是否 code-level xfail-strict 非 prose 自陳」。**

### 5. 殘留誠實度三方收斂（design code-comment + E3 邊界 probe + xfail-strict）才算「誠實捕捉」
兩文件化殘留：(a) naked-context-free 高熵（bare alnum/64-hex/base64 無 keyword/結構）= 資訊論上不可分於合法高熵識別碼（git-SHA/sha256/config-flag/model-id），前一輪 blanket 高熵臂實測誤遮 29% 合法 forensic 內容毀 ledger 可重建（D3 目的本身）→ operator 2026-06-08 拍板 A 接受，最佳解在 P3 source-side；(b) cap-straddle 結構密鑰 MEDIUM 已被 v4 size cap(256KB)+「secret in retained region 仍遮」test 覆蓋。**三方印證**：redactor module docstring + `REDACTOR_VERSION` bump 註解誠實記 v2→v3→v4 歷史（不洗白 over-reach）；E3 memory:345 邊界 probe（18/20/23-char bare LEAK，24+ caught）量化殘留邊界；test 4 軸 xfail-strict。**教訓：「殘留誠實」不是 prose 寫一句「已知限制」，是 code-comment 記真實 RETURN 歷史 + 對抗審量化邊界 + xfail-strict 鎖契約 三者齊備，缺 xfail-strict 則殘留會 silent regress 成「claimed-covered」。**

## 2026-06-09 L2 Advisory Mesh Phase 2 (Orchestrator+registry+LANE_DIRECTION+admission+adjudication+guard+fail-safe) pre-deploy E2E 驗收 — verdict MET (green gate ready) with 1 PROCESS GAP

| 報告 | 日期 | 關鍵發現 |
|---|---|---|
| 2026-06-09 L2 P2 pre-deploy acceptance | 2026-06-09 | **P2 pre-deploy 驗收 MET（green gate ready）**——但前序鏈有 1 PROCESS GAP：**CC 載重 sign-off（stress-tests 5/6/10/15/16/18）無 on-disk artifact**（CC report 0 份、CC memory 最新條目停在 2026-04-24、grep carbon/linchpin/orchestrat=0 hit）。執行方案 §2 line 161 + L2_TODO line 36 明列 **CC 為 P2 named gate 且是 load-bearing**。E2(2 輪→PASS)/E3(2 輪→PASS)/E1(impl) 都在 memory 有 verdict，唯獨 CC 缺。**緩解**：CC stress-test 的 substance 已被 E2 對抗審（carbon-grep real-code-vs-comment mutation）+ 我獨立 runtime 驗證雙重覆蓋（見下），故是「缺 CC 角色 artifact」非「load-bearing 不變量未驗」。建議 PM 補正式 CC sign-off 或明文接受 E2+QA 覆蓋等效。 |

**獨立驗證（runtime assertion 非讀碼）全綠**：
1. **no-auto-path-to-live linchpin（業務鏈端到端）**：真建 3 enabled cap（neutral/contract/expand）跑 dispatch——HEALTHY 下 neutral→neutral_sink、contract→risk_governor_advisory（advisory INPUT）、**expand→manual_inbox(MANUAL) 即便 enabled+budget-OK+HEALTHY 永不 auto**；4 個 (tier×posture) combo expand 全 MANUAL（無解鎖）。LANE_DIRECTION 無 'live' key/value（runtime assert）；validated lane='live'→ValidationError。
2. **fail-safe subtraction-only**：NO_ADVICE/TRIPPED/GLOBAL_CONSERVATIVE 三態 advisory→routed_to='dropped'（=baseline）；expand 每態仍 MANUAL。SM escalation（ollama UP 全程）到達 TRIPPED+GLOBAL_CONSERVATIVE（MED-1 fix 真生效，非卡 DEGRADE_OLLAMA）；1 ok→HEALTHY。
3. **storm-control**：1000-trigger storm + 唯一 subject 擊穿 dedup + budget DENY → 0 admitted（DOC-08 $2/day 守）。
4. **C1 carbon-grep 獨立做**：promote_tier/order/lease/live-enabling token 在 5 模塊**全在 docstring/comment（line 31-35/72/143 等），0 in executable code**。
5. **loader 3 reject 親跑**：autonomy_level 宣告 / can_auto_deploy_to_paper-as-posture-token / lane='live' / unknown-field(extra=forbid) 全 reject load；enabled 預設 false；shipped TOML 載成空 skeleton（0 cap，fail-closed）。
6. **★ skeleton 正確性**：`L2AdvisoryOrchestrator.dispatch()` + `record_capability_spend()` **0 production caller**（grep 證：2 個 `.dispatch(` hit 是 ai_service_listener/ai_service_dispatch 別物件；get_l2_advisory_orchestrator 唯 3 routes 呼，皆 status/reload/reset 不呼 dispatch）。唯一 P2-live 路徑=layer2_engine:357-367 contract-version 改 registry-resolved + try/except fallback 既有常數→D3 row 仍寫得出（fail-soft 零回歸）。machinery reachable（test 88 pass）但 production dormant，P3 接 capability executor 即活。
7. **跨模塊一致 + 無 scope creep**：learning_tier_gate.py（can_modify_live_config=False@all-tiers）git diff 空=untouched；P2 production code 只動 L2 surface（5 新 module+TOML+2 wiring 檔）；residual PART4 'Gap A orchestrator'（helper_scripts/research）是**同名不同 workstream**，file-scope disjoint（命名碰撞陷阱，勿混）。
8. **round-2 fix 在 on-disk code**：_prune_stale_spend(:115/440)+RLock(:174)+/cost/reset&pricing operator-scope(:361/:400) 全在=E2/E3 round-2 PASS 對的是現碼。88 P2 test + 218 layer2-family test pass；7 檔 py_compile OK。

**owed-post-deploy（誠實，未假造）**：deployed-E2E（真觸發→真 agent.l2_calls/l2_gate_seam_log row，需 Linux PG + uvicorn）；full Linux regression post-commit；P2 ZERO migration（registry=TOML SSOT，admission/adjudication in-mem+記既有 V135 gate-seam，guard verdict 用既有 V134 col；V137 reserved-not-used，只在 operator 重開 DB-backed override 才取）；3E-ARCH 的 'live' 軸是**負驗證**（證 auto-loop 結構上不可達 live）非真 live exercise。

**教訓**：
1. **named gate 缺 artifact ≠ 不變量未驗，但仍是 process gap 必明標**——CC 是 P2 load-bearing sign-off，無 report/memory entry；不能因「E2+QA 已覆蓋 substance」就靜默放行 CC 角色，要 push PM 補正式 sign-off 或明文接受等效覆蓋（多角色工作鏈不可單方面跳）。
2. **「Phase 2 orchestrator」命名碰撞**——本 repo 同期有兩個「Phase 2 + orchestrator」workstream：L2 Advisory Mesh P2（app/l2_*）vs residual PART4 Gap A orchestrator（helper_scripts/research + program_code/ml_training）。E1 報告檔名 `2026-06-08--residual_part4_phase2_gap_a_orchestrator.md` 是**後者**，不是 L2 P2 的 E1 報告（L2 P2 的 E1 報告根本不存在 on-disk，verdict 只在 E2/E3 memory）。QA 接手必先 grep file-scope 區分，否則會誤採他 workstream 的 impl 報告當本任務證據。
3. **dormant-skeleton 的「0 caller」要雙向證**——既 grep `.dispatch(` caller（排除同名別物件），也從 route 端證 wired 的 3 routes 不呼 dispatch；單看一邊會誤判。skeleton 正確性 = machinery reachable（test 綠）AND production dormant（0 caller）AND 無 P3 capability 偷跑（TOML 空 + guard/executor 未接 dispatch）三者同時。
4. **fail-soft 要親跑 PG-down**——Mac 無 PG，dispatch 跑 record_gate_seam 時 'PG pool init failed' warning 但 dispatch 流程不斷=設計 fail-soft 真生效（D3 寫失敗不阻 advisory loop），比讀 try/except 可靠。

## 2026-06-09 — L2 Phase 3a `ml_advisory.v1`（diagnose_leak + interpret_result）pre-deploy 集成驗收

**Verdict：P3a pre-deploy 驗收 MET（green gate ready）** — 業務鏈連貫、inert-sink S-2 真閉（0 新執行權結構性成立）、skeleton 正確、owed 清楚。branch `feature/l2-critic-lessons-tools` @ `6a9dd0f1`，P3a **未 commit**（dirty tree）。前序 E2 PASS / E3 PASS / MIT APPROVE-CONDITIONAL(M3+M4 GRANTED)。QC/B1 N/A（P3a 無 alpha 斷言）。

### ★ 最關鍵驗收教訓 — MIT 報告的 sink finding 已 stale，必查 on-disk 現況
MIT report（`2026-06-09--l2_p3a_..._signoff.md`）描述 sink=`mlde_shadow_recommendations` 並開 S-1（V037 REVOKE）/S-2（applier 撿）兩 finding。**但該報告早於 sink-move**：operator 後續拍板把 sink 改寫 `agent.lessons`（E2 round-2 re-review 確認）。我**獨立查 on-disk** `l2_ml_advisory_executor.py:458` 唯一真 INSERT=`INSERT INTO agent.lessons`（mlde_shadow_recommendations 全在「解釋為何棄用」註解 + test 反向斷言）。⇒ 採信前序 sign-off 必對照當前碼，sink-move 這類 operator 中途決策會讓上游 audit finding 失效。

### ★ inert-sink S-2 真閉 = 獨立 code-grounded 證（非採信註解/旗標）
全庫 grep `agent.lessons` 的 prod 寫/讀者**完整集合**：(1) executor:458 INSERT（本 P3a sink）(2) layer2_critic:329/366 SELECT（trigram 唯讀回 LLM 推理）(3) layer2_critic:486 INSERT（critic persist）(4) layer2_engine:820 寫 insight。**無任何 applier/mutator 掃描 agent.lessons**。對比照妖鏡：`mlde_demo_applier.py:649 FROM mlde_shadow_recommendations` + `:756 UPDATE` →build_risk_patch→IPC mutate demo RiskConfig（原 S-2 洞）；該 applier **0 個 agent.lessons 引用**（grep -c=0）；`program_code/ml_training`+`learning_engine` 全樹 0 個 agent.lessons mutator。⇒ P3a 寫 agent.lessons ⇒ 0 applier 撿 ⇒ **0 新執行權結構性成立（非旗標約束）**。原 mlde_shadow_recommendations S-2 洞（被 mlde_demo_applier 掃描去 mutate 配置）因 sink-move **正確閉合**。

### ★ MIT S-1（V037 grant fail-close）對 NEW sink = MOOT，且 agent.lessons grant 有既有 precedent
sink 移出 mlde_shadow_recommendations ⇒ V037 REVOKE 不再適用 P3a 寫路徑。`V133__agent_lessons.sql` **無 REVOKE/GRANT/evidence-tier governance**（grep 空）。且 `layer2_critic.py:486` 既有 prod 就直接 `INSERT INTO agent.lessons` ⇒ control_api role 對 agent.lessons 的 INSERT 權**已被既有 critic producer 證可行**，P3a 用同表同 role。原 S-1（mlde_shadow_recommendations 專屬 V037 REVOKE）大幅去風險；formal Linux runtime grant 確認仍列 owed-post-deploy（Mac mock 不可驗真 grant）。

### 業務鏈連貫（on-disk 逐階證）
trigger(ml:training_complete) → admission `_admit:486`（dedup→debounce→coalesce→budget→tier；iron-rule budget stage4 守 DOC-08 $2/day 即便 debounce OFF）→ cascade（STAGE1 Ollama screen M4-gated/disabled→flag-MIT；STAGE2 cloud-L2 interpret survivors-only，**LLM 永不驗 alpha**，P3a 無 math gate 因斷言無 alpha；STAGE3 確定性 guard M3 source_class typing+regime_caveat；STAGE4 sink agent.lessons inert + D3 record_l2_call + 每階 record_gate_seam）。與 PA 設計 §D + execution-plan §2 Phase3 逐條對齊。`dispatch_and_execute:413-418` gating predicate=`admitted AND routed_to=neutral_sink AND capability.startswith('ml_advisory')` else 短路 0 model call。

### skeleton 正確（非死碼非過度）
`dispatch_and_execute`（orchestrator:379 定義）**0 production caller**（grep 全 prod 樹唯一非-def 命中是 :363 註解）；reachable via test（`TestDispatchReachability`:791）⇒ 非死碼。dormant 等 conductor trigger-wiring（P3 wiring 階段）。**無 P3b 偷跑**：TOML 只 2 P3a stanza（diagnose_leak/interpret_result）全 `enabled=false`、`lane=ml_backlog`→`LANE_DIRECTION="neutral"`；hypothesize（P3b）stanza 正確註解掉不啟用；executor 0 alpha-gate import（`test_executor_has_no_alpha_gate_imports`:737 grep dsr_gate/pbo_gate/beta_neutral/residual_alpha_gate=空）。0 hard-boundary touch（live_execution_allowed/OPENCLAW_ALLOW_MAINNET/place_order/acquire_lease/promote_tier 全在 docstring:29-30，0 in code）。

### 獨立測試（mac_dev venv py3.12 + pydantic 2.13.3 親跑）
P3a `test_l2_p3a_ml_advisory.py` **53 passed**（含 TestD3ContractVerProvenance 5 test=E2 LOW-2 fix lock；redactor mutation-bite；inert-sink 結構斷言）。4-檔 L2 surface（P2 orchestrator+P3a+D3 ledger+critic）**255 passed/4 xfailed**（xfail=pre-existing strict-bare 殘留非 P3a）。targeted sink/inert/redactor/neutral/alpha-gate/mutation **18 passed**（真 run 非 skip）。

### P3-deferred 誠實文件化（非 P3a gap）
- cap/mode 一致性斷言：grep 空，dispatch 未斷言 cap↔mode 配對一致 → 未來 conductor wiring 時加（E2 已標 dormant 路徑，cap/mode consistency 由未來 conductor 建立）。
- E3 2 LOW（非阻擋，非本 delta 引入）：LOW-1 dedup-dict(last_served_ts/debounce_pending keyed coarse_subject)無 evict/maxsize，P3 wire dispatch 上 route 且容許高基數 raw 文字時=memory DoS，現不可達（dispatch 0 caller）；LOW-2 已在 P2 round-2 閉（/cost/* operator-scope fold-in）。
- M4 benchmark artifact = MIT-owned 下一交付（screen 現 placeholder-DISABLED→everything-to-gate=safe 保守起點，flag MIT），非 P3a blocker。

### owed-post-deploy（明確標，不假造）
1. **deployed-E2E**：真 conductor 觸發 ml:training_complete → 真 dispatch_and_execute → 真 agent.l2_calls + agent.lessons row 落庫 + gate-seam chain。系統未部署（Mac 無 engine.sock=預期 CLAUDE §六）、P3a 未 commit、dispatch 0 caller dormant ⇒ **結構性不可在此環境做，不宣稱已做**。
2. **full Linux regression post-commit**：MIT 標 Mac 不能跑全 suite（環境）；E4-Linux full green owed。我用 mac_dev venv 補了 L2-surface 親跑（53/255 passed），但 Linux x86 + 真 PG 的 full-tree regression 仍 owed。
3. **Linux runtime grant 確認**：`has_table_privilege('<control_api_role>','agent.lessons','INSERT')`（雖 critic precedent 證可行，formal 確認仍 owed）。

**教訓沉澱**：(1) operator 中途 sink-move 會讓上游 audit finding（MIT S-1/S-2 對 mlde_shadow_recommendations）失效——採信任何 sign-off 前必 grep on-disk 真 INSERT target 對照。(2) 「inert sink」要用照妖鏡證：找對照的真 applier（mlde_demo_applier FROM mlde_shadow_recommendations →IPC mutate）證它 0 引用本 sink，比讀「genuinely inert」註解可靠。(3) deployed-E2E 在 undeployed/uncommitted/dormant 三條件下結構性不可做，QA 必明標 owed 不假造（呼應 evidence_discipline）。

## 2026-06-10 — L2 P3b ml_advisory.hypothesize（alpha-bearing）pre-deploy 驗收 = MET（green gate ready）

| 報告 | 日期 | 關鍵發現 |
|---|---|---|
| 2026-06-10 L2 P3b pre-deploy QA（findings 直接回 PM，無 report 檔，per evidence_discipline 指令） | 2026-06-10 | **P3b pre-deploy 驗收 MET（green gate ready，pre-deploy）**。獨立查源（非採信 prompt「前序全綠」）+ Mac 自跑測試。branch `feature/l2-critic-lessons-tools`@`aeae4da4`（P3a green committed；P3b 6 構件 untracked 未 commit）。 |

**核心方法教訓（再次命中「socket 中斷/上游自標完成不可信，查 on-disk」）**：prompt 宣稱「E1→E2→QC→MIT→E4 全綠」，但 **E1/E2/E4 無 P3b 獨立 report 檔**（最新 E1/E2/E4 report 皆 ≤05-31）；驗證走 **(a) 三角 = 各角色 memory.md 的 P3b 條目**（E1 06-09 IMPL + 06-10 fail-loud fix / E2 line 5224 TOML 2-stanza / E4 5363 Linux parity+altcap real-smoke）**(b) on-disk 真碼讀全文 (c) Mac 自跑測試**。只有 QC/MIT/PA 留了 06-09 spec/design 檔。**QA 不能因「無 report 檔」就判 chain 沒跑——memory 條目 + 真碼 + 自跑測試三角才是真相**。

**逐軸 MET（全部源碼 file:line 親驗 + Mac 自跑）**：
1. **業務鏈連貫 + math gate 唯一 alpha validator**：`l2_ml_advisory_executor._run_hypothesize_cascade:729` 階序 = Ollama screen→generate（cheap 結構化）→guard（form）→novelty（executor DB read，guard 0-DB 不變量保留）→**`_run_math_gate:984`（Q1→DSR→PBO→B1→leak，strictest-wins）**→cloud interpret **只在 math_res verdict==pass**（:837，cost-on-survivors root#13）→sink。`_run_math_gate` 984-1158 內 **0 LLM-invocation**（awk 掃 await/_provider_complete/engine. 僅命中 3 個確定性 gate import）。
2. **0 新 live authority（結構性）**：executor order/lease/promote grep 僅命中 :29-30 鐵律「註解」0 真呼叫；test `test_hypothesize_executor_zero_order_lease_promote` 在套。verdict routing：pass→backlog（`agent.lessons` inert/no-applier-scan，:879-880）/DEFER→backlog non-promotable/fail→logged-and-dropped 不 sink（:863-867）。promotion=`demo_stage1`=expand=forced-MANUAL（`l2_capability_registry.effective_autonomy` STEP-1 :118-120 non-overridable，LANE_DIRECTION 無 "live" key）。hypothesize stanza 雙閘 `enabled=false`+`min_tier=L3`+`tier_capability_flag=can_generate_hypotheses`。
3. **honest-DEFER（PBO single-config）**：`_run_math_gate` STEP2 `len(cpcv_returns)<2 → pbo_single_config_honest_defer DEFER`（:1034-1036，承 Gap-A 不捏造 peer）；strictest-wins 含 PBO=DEFER → **單配置候選 overall 結構性至多 DEFER**（永不 pass）；test `test_hypothesize_pbo_single_config_honest_defers` 證。
4. **fail-loud fix 確認**：`beta_neutral_check:162-183` int-bar-index 契約閘在 `_parse_series`「之前」，非 int key（date/datetime/str/mixed/bool）→ 顯式 DEFER reason `temporal_keys_unsupported_need_int_bar_index`+logger.warning（帶型別/值），非靜默空-series-DEFER；`_is_int_bar_index:465` 正確排除 bool（int 子類）；caller seam :1120 map `res.verdict` 無新 literal，新 reason 落 D3 為 `b1_temporal_keys_unsupported_need_int_bar_index`。
5. **skeleton/dormant 正確（非死碼 + 非過度）**：cascade 經 orchestrator dispatch :442 reachable，但 **`math_gate_inputs` 0 production writer**（grep 僅 executor :1011 read + beta_neutral docstring）→ 無真 producer 時全 stage DEFER（fail-closed）。無 P4/FDR 偷跑（`ResearchAlphaWealthController`/sealer/α-wealth 不在本 diff）、無 GUI（P5）。M4 benchmark/calibration JSON **皆 ABSENT** → loader fail-closes screen DISABLED（全進 gate，不丟 alpha）= 未假造 live-calibrated。0 新 mutable singleton（pure-function posture）。
6. **owed 誠實（E4/E1 已標，QA 確認文件化）**：★int-bar-index re-index before real-data wiring（E4 real-smoke 抓的 forward-integration，現 fail-loud DEFER）/ 6 ex-BTC symbol（ATOM/ETC/FIL/ICP/INJ/UNI）market.klines 1d 覆蓋 gap / V127 population（0 rows）/ agent.lessons seed 5-10 dead-modes（0 rows，M4 bad-set+novelty）/ producer→context assembly seam（conductor wiring，AEG-S3 候選接口未建）/ deployed-E2E（系統未部署+P3b 未 commit）/ full Linux regression（E4 temp-overlay 已跑 46==46 + producer 794/2 pre-existing scipy）。

**Mac 自跑（venvs/mac_dev/bin/python 3.12.13）**：P3b 4-suite = **53 passed**（beta_neutral 22[含 +7 fail-loud]/altcap 7/leak 14/hypothesize 10）；regression P3a executor+residual/dsr/pbo gate+P2 orch = **181 passed/0 failed**。0 新 fail。

**教訓沉澱**：(1) **alpha-bearing 能力可 lane=neutral**——hypothesize 是 alpha-bearing 但 lane=ml_backlog=neutral，因「晉升動作」是另一個 demo_stage1=expand=MANUAL lane；B1 gate 的是「promotion-relevant verdict」非 lane。讀 LANE_DIRECTION 表必懂「lane direction ≠ 能力是否產 alpha」。(2) **「無 report 檔」≠「chain 沒跑」**——memory 條目是合法 sign-off 載體；三角（memory+真碼+自跑測試）。(3) **dormant 區分「非死碼」vs「非過度」雙向**——cascade reachable 但 producer-pack-math_gate_inputs 0 caller=conductor wiring 缺（非死碼）；同時無 P4/FDR/GUI 偷跑（非過度）。兩個方向都要查。(4) **pre-deploy green gate ≠ deployed-E2E**——P3b 未 commit/未部署/producer 未 wire，deployed-E2E 結構性不可做，QA 明標 owed-post-deploy 不假造（呼應 P3a 教訓 + evidence_discipline）。
| 2026-06-10 AC-19 ALT bucket 14d final verdict | 2026-06-10 | **ALT FAIL 確證**（42/10/28=23.8%，Wilson lower 13.5%<20%，ex-OPUSDT 穩健；4 非timeout non-fill=postonly_reject）；large_cap n=9 INCONCLUSIVE-LOW-N（66.7%，gate 需 n≳200 不可判，勿讀成「也壞」）；cron 晚落地只捕 day12-14（E-2 PARTIAL）；窗後 8d alt 19.0% 無自癒；escalate→PA/QC/FA+operator，QA 建議 BB depth audit 先行。報告：srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-10--ac19_alt_bucket_14d_final_verdict.md |

## 2026-06-12 — P2 incident-policy dispatch trigger source QA acceptance
`P2-INCIDENT-POLICY-DISPATCH-TRIGGER` source acceptance PASS_WITH_CONDITIONS：Mac/Linux C4 true producer path 1p each、notify-only no-AllFail 1p each、engine_dead targeted canary 5p each；static scan confirms engine_dead no order/auth/DB/risk/trading mutation and sm_halt/position_drift only feed incident_policy. Runtime healthz/watchdog sanity OK, but no deployed-E2E or restart claim. Report `2026-06-12--incident_policy_dispatch_trigger_qa_acceptance.md`.

## 2026-07-07 — WP2.1 Training Run PIT Manifest Gate source QA acceptance
`WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE` source-only QA acceptance PASS：chain PM→PA→E1→E2 return→E1 fix→E2 PASS_TO_E4→E4→QA complete；contract-bound quantile PIT gate is before train/export/registry, canonical acceptance report binding is present, non-contract-bound is explicit `not_contract_bound`, pooled/legacy fail closed, and PIT/report persistence is atomic. E4 evidence accepted (`46 passed, 1 skipped` x2, registry `49 passed` x2, QA adjacency `90 passed, 1 skipped` x2, py_compile/diff-check PASS). Runtime/loss-control branch remains separate BLOCKED_BY_RUNTIME_ENV/STOP_LOSS_CONTROL and was not consumed. Report `2026-07-07--wp2_1_training_run_pit_manifest_gate_acceptance.md`.

## 2026-07-07 — WP3.1 Training Registry Contract Emission source QA acceptance
`WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION` source-only QA acceptance PASS：contract-bound quantile path builds canonical `registry_serving_contract_v1` from acceptance/PIT/binding/feature hashes and exact q10/q50/q90 artifact bytes, persists it into the acceptance report, passes the same contract to registry, and fails malformed trio before DB precheck. QA reran requested focused suite (`74 passed`) and diff-check PASS; runtime/loss-control/DB persistence/model reload/symlink/live remain out of scope and blocked. Report `2026-07-07--wp3_1_training_registry_contract_emission_acceptance.md`.

## 2026-07-07 — WP6 Reward Ledger ProofPacket Bridge source QA acceptance
`WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE` source-only QA acceptance PASS：`reward_ledger_v1` only accepts PROOF_READY ProofPacket + countable DemoMutationEnvelope, validates embedded source artifacts by recomputing ProofPacket/envelope/PIT/registry/acceptance hashes, rejects forged lineage/source artifacts after record_hash recompute, and requires explicit non-contradictory optional registry mode. QA reran focused suite (`112 passed`), forbidden-surface grep PASS(no matches), diff-check PASS, and two adversarial probes. Runtime/loss-control, DB persistence, registry persistence, Cost Gate, order/probe, live/mainnet, model reload, and symlink surfaces remain out of scope and blocked. Report `2026-07-07--wp6_reward_ledger_proofpacket_bridge_acceptance.md`.
