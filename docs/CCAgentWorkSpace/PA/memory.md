# PA Memory — 工作記憶

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾。

## 長期教訓（2026-06-10 壓實蒸餾，源自原第 1-7242 行；原文見 memory-archive.md）

- 任何 brief/spec/operator/前審 claim（「0 caller」「已刪除」「IPC seam 已 live」「writer healthy」「V### 已 land」）必親 grep/ssh 證偽後才採用——代碼註釋與 plan 文字是 aspiration 非 runtime fact；deletion claim 必附 commit SHA；phase 推進會使 greenfield/migration-number 假設 stale，必對當前 HEAD 重驗。
- Linux PG empirical 是唯一可靠 schema 防線：Mac mock pytest/cargo test/sqlx parser 全不驗 runtime semantic；migration 派發前必 ssh 查 `_sqlx_migrations` + 真實 schema + V###/ADR 編號占用（spec 浮動編號是 dispatch race source），double-apply 必測；PG 連線用 trading_admin/trading_ai（非 openclaw），timezone 以 `date -u` 對齊。
- exhaustive caller grep 必含間接鏈：helper_scripts/*.sh→*.py、`pub use` re-export、shell→python 呼叫；漏查會把生產路徑誤判為死碼。
- runtime 證據 > filesystem/git 證據：binary mtime、engine boot kind（Manual --rebuild vs watchdog Auto respawn）、「檔案 mtime 新 ≠ engine 看到新值」；deploy verify 必先 check boot kind；「engine silent」≠「engine broken」。
- fail-closed 設計鐵則：fail-OPEN guard（`if x>0 {gate} else {pass through}`）是反模式；placeholder/snapshot 必走 OK band 防 DEGRADED 染色；cold-start fail = conservative boot + alert 而非 crash；projection/IPC fail 一律 deny，永不 fabricate permissive。
- 環境事實：Mac srv 全源可讀（引擎在 `rust/openclaw_engine/src/` 488 .rs；兩度誤判 fixture stub 皆因查錯路徑），但 IPC/PG/engine runtime 必須 ssh trade-core；Mac engine not_running 是預期。
- 派發 SOP：self-contained dispatch packet（AC + 必讀 + 反模式 + Disconnect Recovery + NO-OP exit）；派發前 grep TODO active state + 既有代碼字面 + 編號占用；prompt 給的 module path/SQL schema/數字不可盲信（數字 6h 即漂移，crate ownership 用 find 5 秒可驗）。
- PA+E1 合一僅限：純 test split / isolated refactor + 規格清晰 + 既有 sibling 範本可循；高風險 IMPL 必走 A3+E2 對抗鏈；PA 任務字面誘導越界 IMPL 時主動 push back。
- §九 LOC 治理慣例：800 警告 / 2000 hard cap；sibling extract（`pub(crate)` struct+fn；persist.rs 是教科書範本）優於把工作擠回既有檔；拆分計劃必含外部 caller 全盤點 + 未來 N 次成長 headroom。
- 維度衛生：enum aggregation key 禁拼動態 trace 字串（free-text 屬 trace dim）；任何 enum column 配 cardinality healthcheck；healthcheck 必設 key-existence + value-quality 雙層；severity 排序 INSUFFICIENT_SAMPLE > PASS。
- async/sync 邊界：設計方案前先確認 caller 是 async 還是 sync——FastAPI async 路由禁 threading.Lock 阻塞操作，on_tick 同步線程可用；async fn 遞迴必 `Box::pin`。
- multi-session race 慣例：不 revert 非己改動、meta-doc 用 `git commit --only`、接手前 `git fetch` + `git log -5`；sibling 可能無害撞單（同做相同收口）；判 regression 看 `0 failed` 非 test count。
- leak/look-ahead 紀律：rolling(N) 含 current bar 必 mean-revert（必並列 shift(1) 對比）；sub-bar event timing 必做「事件落在 bar 開瞬間」boundary 思想實驗——1m bar 用 (open+close)/2 會洩漏 post-event 價格；alpha 驗證走 entry_index=i+1 + leakage_scan。
- 統計判讀：RED 先分「sample insufficient vs signal failure」（比對 baseline 採樣率，差千倍即 gate self-imposed scarcity）；trigger gate rate 是 design choice 可 sensitivity sweep；breadth ≠ n_independent（time-cluster-bound，不隨 symbol 數膨脹）。
- SM/audit 治理：append-only event log——transition 描述既有 object 狀態變化，不在新建 object 掛 from_state；audit table 是 multi-process SM 的 SoT 真值權威；AMD supersede 用 callout 保 historical lineage 而非刪檔/strikethrough 全文。
- 上游 verdict 不照單全收：operator「已確認事實」可大半錯、QC verdict inline 升級必 codebase grep 驗、audit report 的 call-site 清單必親 grep 重數；cross-finding reconcile 先對齊 definition 再對齊 verdict；兩源 push back 同事項必明標兩源合併 AC。
- spec 字面陷阱：「parallel group」標記必驗 file overlap + IPC contract/state import + lexical scope；容差/閾值一刀切誤讀是 sub-agent dispatch 最大誤讀源；「metric classify」vs「SM band dwell」類用詞不清是 IMPL drift 根因——spec 必把 named-but-underspecified gate 釘成 phase-bound 驗收。
- 工具慣例：`psql 2>/dev/null` 吞 SQL error 必交叉檢核；大檔分段 offset/limit 讀 + grep 定位勿整檔讀；ssh runtime 解讀易錯（systemd scope/transient PID），優先 sub-agent 驗證或接受 operator 更正；給 operator 的 shell 一律單行。

## 近期記錄

## 2026-06-07 — 幻影倉位記帳 bug 定位 + 修復設計（TONUSDT demo phantom LONG）

**RCA 鐵證鏈（已驗，非假設）**：幻影 LONG 不是 `apply_fill` 算錯，是 **WS `PositionUpdate` 與 `Fill`
兩條訊息對同一份 `PaperState.positions` map 亂序雙寫**：
- 兩回調共用同一 unbounded channel（`startup/private_ws.rs:95/143-162/167-179`），相對順序=Bybit 推送
  順序，引擎不保序不關聯。
- Bybit 平倉先推 `position(side=None,size=0)` → `loop_exchange.rs:550` `upsert_position_from_exchange(0)`
  → `fill_engine.rs:98` `positions_remove` 把 short 移除（flat）→ 隨後 close `Buy` `Fill` 才到 →
  `apply_fill`（`fill_engine.rs:295`）`if let Some(pos)` 落空 → 落到 `:364` **開新倉分支** → 開出
  `is_long=true,qty=437.3,entry=1.5744` LONG（指紋=平倉價+平倉量，完全吻合）。
- `commands.rs:686` `was_open` 落空 + `:710` 把這筆當新倉寫 `entry_context_id` → 幻影被賦正規血緣。
- GAP-7 `on_tick_helpers.rs:700` 每 1000 ticks 遍歷 `paper_state.positions()` 寫 `position_snapshots`
  （`trading_writer.rs:645`，engine_mode 來自 `effective_engine_mode`）→ 28548 假快照來源。

**關鍵架構事實（更正 PM 推測）**：①所有 PipelineKind（Paper/Demo/Live）共用同一 `PaperState`
（`pipeline_ctor.rs:52`），snapshot 對**所有模式**都來自 `PaperState` 非 Bybit 拉取 → **bug 非 demo 專屬，
live_demo/真 live 同樣脆弱 = 極高風險**。②`position_manager.rs`（Bybit 拉取）只給 reconciler 對賬，
非 snapshot 源。③Python `control_api` **無倉位帳本**（grep apply_fill/upsert/position_snapshots 全空，
不讀 snapshots）→ 倉位帳 Rust 單一權威，**無跨語言 parity**。

**reconciler-miss 結論（call-path grep proof）**：reconciler 在跑、覆蓋 demo，但**對賬軸接錯**——
`reconcile_once`/cycle 的 baseline 與 current **都來自 `pos_mgr.get_positions(Bybit)`**
（`mod.rs:296/438/470`），比「Bybit 上輪 vs Bybit 這輪」。TON 17:03 後 Bybit 一直 flat → baseline 每輪
seed flat → `classify(None,None)=Match` 永不 drift。reconciler **有讀** `engine_positions_mirror`
（paper_state 鏡像，`mod.rs:826`）但只是 Ghost verdict **已成立後**取方向派平倉（`process_ghosts:838`
第一行 `if !matches!(verdict,Ghost) continue`），**mirror 是「方向來源」非「偵測來源」**。即「偵測 Bybit
自我跨輪變化」與「偵測本地帳 vs Bybit 背離」是兩條軸，reconciler 只做前者 → 本地幻影結構性盲視 7.4h。

**修復設計**：①根因修 Option A（推薦）=`PositionUpdate` 降為 advisory 只讀比對，不再 add/flip/remove
本地帳，size=0 走既有 `converge_exchange_zero_close`（`commands.rs:1267` 已測），倉位唯一 mutating 源
變回 `apply_fill` → 競態消失。②`apply_fill` 補翻倉餘量（`:299` `qty>pos.qty` 時餘量被丟、目前**完全沒
實作翻倉**=附帶 bug）+ reduce-only fill 本地無倉時 no-op 不開倉（fail-closed 縱深）。③告警新軸=
reconcile cycle 加 mirror-vs-Bybit-current phantom 偵測（2-cycle streak+點查 gate），復用
`spawn_reconcile_audit`→`observability.engine_events` + canary_events.jsonl（事故②宕機 20h 無人知教訓）。
首版只告警不自動收斂。④需求 #2（錯過+5%）是 #1 下游：幻影佔位→引擎以為持倉→不再入場；#1 修好自動解。

**E1 拆解**：T1 fill_engine（根因+翻倉，linchpin）/T2 loop_exchange（PositionUpdate advisory+傳 is_close）
/T3 commands（透傳 is_close）/T4 paper_state mirror 升 struct 帶 qty/T5 reconciler phantom 軸。
Wave1 並行 T1/T3/T4，Wave2 serial T2(待T1簽名)/T5(待T4)。檔互不重疊。E4 核心=**17:03 亂序回歸 golden
test**（先 PositionUpdate(size=0) 後 Fill(Buy,is_close) → 斷言 flat 非 LONG、不寫幻影血緣）。

**教訓**：①「記帳 bug」先別怪算術——`apply_fill` 邏輯本身對，真因是**兩個無序寫入源競爭同一 state map**
（B-1 Phase 2 把 WS position 也接進本來純 fill 累積的 PaperState）。查 bug 要查「誰還會寫這份 state」。
②reconciler「沒抓到」≠「沒在跑」——**對賬軸接的對象**才是關鍵（baseline=Bybit 自我快照 vs =本地帳，
天差地別）。mirror 被讀≠被當偵測軸。③同一 channel 串行處理保留 venue 推送順序=venue 不保序時的隱藏
競態源。④共用 PaperState 跨三模式 → demo bug 自動是 live 風險，評級必須拉到極高。報告路徑
`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-07--phantom-position-fill-bug-design.md`。

## 2026-06-08 — L2 D3 Phase-1 (provenance & audit) tech design (design-only, E1-READY)
- 交付: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--l2-d3-phase1-tech-design.md`。承 v4-final design draft + execution plan Phase 1。
- **設計修正(ground 在 file:line)**: ① hypotheses 真表 = `learning.hypotheses`(PK `hypothesis_id BIGSERIAL`, V100:273-274), **非** design 寫的 `research.hypotheses`/`hid`。② `replay.experiments`(V041:81) 是 plain TEXT-PK 表, **非** hash-chained(V131/V132 才是 residual/hidden-OOS registry)。③ strategy-variant **無物理表**(grep CREATE TABLE 0 命中; Track-B 是 `trading.fills.track` enum, V101:79-82)→P1 該 hop N/A/DEFER。④ demo fills = `trading.fills`(engine_mode='demo', V003+V015:15), 是 columnstore hypertable → ADD COLUMN 必 nullable/無 DEFAULT/無 SET NOT NULL(V077/V101:170-181 feature_not_supported 陷阱)。
- **append-only 真相**: repo 兩模式。D3 用 DB-level REVOKE(強): `REVOKE UPDATE,DELETE FROM PUBLIC` + DO-block `REVOKE FROM trading_ai`(V099:298-307 最貼近語意; app role=`trading_ai`, 訂正 role=`trading_admin`)。application-discipline-only(V133/V064/V035)較弱不用於 ledger。
- **consequential 矛盾解法**: 推薦 Option(b) V114 narrow-column UPDATE 例外(`GRANT UPDATE(consequential) TO trading_admin` only, V114:204-265), **P1 不開 compression** 避 compressed-twin column-grant abort(V114:208-216 = feedback_v_migration_pg_dry_run V114 教訓本身)。writer INSERT-only; consequential promote 走獨立 trading_admin path。
- **redactor reuse-or-build**: hybrid。reuse `error_sanitize.py`(reason_code→safe msg) 解 str(e) 半; **新建** `l2_secret_redactor`(secret-pattern 大文本掃描, repo 無)。sanitize 在 D3 writer INSERT 前; sha256 over SANITIZED text(design:698-699)。
- **migration 號**: V134=ledger(+§C additive ALTER), V135=gate-seam(跳 V128 軟保留 reserved-if-needed breadth, V127:125)。
- **hypertable 強制 composite PK** `(l2_reply_id, created_at)`(design "text PRIMARY KEY" 是陷阱; V035:135/V064:163/V114:178 先例)。`agent.ai_invocations`(ledger:222-227) 只存 prompt_hash+response_summary 非 full → D3 確為 NEW table reuse helpers(_sha256_text:49, deterministic_event_ts:55)。
- 教訓: design draft 是 heads/grep 讀, in-full 親查推翻 3 個表名/結構斷言(research.hypotheses / replay hash-chained / strategy-variant 表存在)。**call-path grep + 親讀 migration 全文 > 採信 design 文字**。R2-5 live hop 按 operator 拍板 EXPLICITLY DEFERRED, 只 shape-note 不設計。

## 2026-06-08 (later) — L2 D3 Phase-1 design LOCKED to operator final decisions (overrode 2 PA recs)
- 同檔 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--l2-d3-phase1-tech-design.md` 由 "recommendation" 鎖成 LOCKED design。operator 拍板覆蓋我原 rec 兩處：
- **① consequential → Option (c) side-table（非我推的 (b)）**。理由=長期可擴展：ledger 純 append-only、**零 column-level UPDATE grant** → 未來可自由開 TimescaleDB compression，**V114 compressed-twin column-grant abort 根本不發生**（這是 (c) 勝 (b) 的長期 key；我親驗 `V114:208-216` twin-abort + `:249-257` nested-exception kludge 確為 column-level grant 專屬陷阱）。新 append-only side-table `agent.l2_consequential_marks`(mark_id/l2_reply_id/marked_at/reason/lane/marked_by/details, 建在 V134, 純 REVOKE, 同樣零 column-grant)。precedent cite=`learning.lease_transitions`(`V054:225`, PK `(transition_id,created_at):240`, event-sourced 每筆 append 非 mutate)。
- **at-creation 子變體選 (i)**（非 ii）：ledger 留**不可變** `consequential_at_creation BOOLEAN`（INSERT 設一次永不 UPDATE→零 grant），marks 表給 later-discovered。理由：known-at-creation 是多數→cheap 單欄掃描免 join；(i) INSERT-only 不重新引入 V114 trap。predicate=`consequential_at_creation=true OR EXISTS(marks)`。
- **② provenance §C ALTER → 獨立 V136**（非我推的 fold 進 V134）。理由：ledger 全可現 designable→V134 早定稿乾淨；provenance 有 Linux-verify 未決(`trading.fills` columnstore 形 / `decision_outcomes` table-vs-jsonb)→拆 V136 讓 V134 不等、rollback/dry-run blast radius 更清。P1=**V134**(ledger+marks)·**V135**(gate-seam)·**V136**(provenance ALTER)。三號全 free, 不撞 V128 軟保留（親驗 ls=V133 head, V128 absent）。
- **retention/compression**: P1 只鎖 shape, **不含 drop 邏輯、不開 compression**。post-P1 drop=anti-join marks 表 + at-creation flag。partial index 隨 retention deferred（舊 `WHERE consequential=false` 單欄 index 移除：(c) 下 false-at-creation 仍可能因 later mark 而 retention-worthy，單 predicate 錯）。
- **新發現(ground)**: `trading.decision_outcomes` = **plain table**(`V075:8` "2 plain tables")非 columnstore→plain ADD COLUMN 可；但 decision_outcomes provenance 屬 deferred R2-5 live hop **不在 P1 V136**。`agent` schema 已存(`V001:35`/`V064:18`/`V133:38`)→V134 mirror `CREATE SCHEMA IF NOT EXISTS agent` 即可不假設。
- **§H Linux dry-run checklist** 改覆蓋全三 migration：V134 兩表雙 apply 冪等 + 證 `trading_ai` 無 UPDATE/DELETE on 兩表 + 證 V134 **零 `GRANT UPDATE(...)`**(grep 0 hits)；V135；V136 columnstore-safe ALTER(nullable/無 DEFAULT/無 SET NOT NULL)。
- **內部一致性驗**: grep 確認 0 殘留 (b)/narrow-column/fold 肯定句(只剩標明「rejected」「overrides earlier」的 LOCKED 文字)、24-col 不變(rename 非加減)、marks 命名一致、V134/V135/V136 全 free。design-only 本 pass 0 碼/0 apply/0 DB write。E1-READY LOCKED。
- 教訓：operator 用「長期可維護/可擴展」軸推翻「reuse vetted pattern」軸——(b) 雖是 repo 已 dry-run 的 V114 pattern，但它**永久把 ledger 綁死在 V114 ordering+nested-exception**且擋掉 compression；(c) 多一張表卻換來 ledger 純淨可壓縮。短期 reuse-vetted ≠ 長期最優；column-level UPDATE grant on hypertable 是「會傳染 compressed twin」的長期負債，不只是「需 idempotency kludge」。

---

## 2026-06-08 — Gap-A PBO peer-validity ruling (residual gap-closure follow-up; PM methodology challenge)

**任務**：PM 質疑 residual gap-closure design 的 Gap A「A1-lite peer generation」是否 PBO theater。要求 code-grounded 裁決 + 修正 P2 scope。

**Code-ground 結論（5 問）**：
1. **A1-lite 機制**：PM 描述「re-bucketing candidate's own demo round-trips under param-perturbed exit/entry rules computed offline from trading.fills」= **re-grouping 同一條 fills**，不是 per-variant re-simulation。對照 `residual_alpha_gate.py:791-800` `_probability_of_backtest_overfit`（degenerate proxy：只比 peer **means** vs observed mean）+ line 728 註解自承「最小近似…正式 CPCV/peer beta 可在後續版本取代」。
2. **A1-lite PBO 無效**：PBO/CSCV（`pbo_gate.py:200-205`/`_cscv_pbo`）按定義需 **N 條 genuinely different config 的 OOS series** 做 IS-rank→OOS-rank。Re-group 同一序列 ≠ 不同 config → PBO invalid theater。**A1-lite 不得 fabricate peers**。
3. **DSR 不需 peers（確認）**：`dsr_gate.py:381` `compute_dsr(observed_sharpe, n_trials:int, ...)`，`n_trials` 是 **count**，`_compute_expected_max_sharpe(K)` 走理論 Gaussian E[max]；`trial_sharpes` optional。residual gate 內 `_deflated_psr(psr, n_trials)` 同理（count-based）。**DSR/PSR/beta-residual/permutation 全 peer-independent，single-config 可跑**。
4. **Promotion 對 PBO fail-closed（確認）**：`promotion_gate.py:106,125-131` — `candidate_oos_returns is None or <2` → `pbo_verdict=missing_cpcv_returns` → 整體 `verdict=defer_data`（除非已 block），`passes = verdict=='promote'`。即 **PBO defer → whole candidate defer，即使 DSR pass**。Rust 側 `canary_promotion.rs:376-388` 同構：`pbo=None`→Pending（不 fail 不 promote），Stage3→4 需 `DSR PASS + PBO≤0.5`。**結論：fake 2 peers 與 pass None 的 defer outcome 相同——除非 fake peers 真把 PBO 翻成 promote（正是要避免的 theater）。所以建 real peers 必須 A-full（Rust replay 真 variant series）**。
5. **修正建議（確認 PM 的）**：P2 = orchestrator wiring A1(residual/beta)+A2(DSR by n_trials count)+A3(permutation) on real candidates（關 defer-by-absence，gate 在 beta-masquerade P0 維度真正 active），**誠實 defer PBO 維度**（single-config，標 `pbo_not_applicable`/沿用 `missing_cpcv_returns` defer path）直到 A-full（P3）Rust replay 供 genuine variant series。

**關鍵架構事實**：
- 現役 production peer 語意（`promotion_evidence.py:184-236` `build_strategy_promotion_evidence`）：peer = **同一 config 跨 symbol 的 per-cell return series**（`candidate_key=symbol`），K=symbol-cell 數。是 cross-sectional 軸（不同 instrument=不同 sub-portfolio，legitimate-ish CSCV），**從來不是 param-variant，也從來不是 re-group 單序列**。A1-lite 的 re-group 比這還弱。
- **無既有 A-full variant-series producer**：`replay_runner.rs:378` 註解「T2 will land formal comparison route + DSR/PBO metrics」=Rust replay 尚未產 per-variant 比較序列。genuine PBO peers 須新建（=P3/A-full）。
- residual_alpha_gate 已內建誠實 defer：`_is_defer_only_reason`（line 892）把 `pbo_missing_candidate_returns` 當 defer-only（非 hard fail）→ `defer_data`；docstring（line 97-98）明寫 `allow_missing_pbo_for_core_tests` 只給 unit diagnostic「不得作 promotion evidence」。**設計已誠實，A1-lite 是多此一舉且有害的 fabrication**。

**教訓**：「真實有效」的 gate 設計，缺維度要 **honest defer 而非 synthesize peers**。PBO 的 input 契約（N 條獨立 config series）本身就否決了任何「從單 config 變出 peers」的捷徑——無論 re-group 還是 Python mini-backtest（後者還有 Rust↔Python 行為發散風險）。defer outcome 在 fail-closed policy 下與 fake-peers 相同，故 fabrication 零收益純風險。承 [[project_2026_06_05_residual_producer_build]]（當時已因「讓閘可信會誠實 defer」對單配置一律 defer，本裁決與之收斂）。

---

## 2026-06-08 — L2 Advisory Mesh Phase 2 (Orchestrator+registry+contracts+guard+admission+adjudication) 技術設計 [CC linchpin]

**任務**：產 P2 設計（design-only，no feature code / no migration apply / no deploy）。接 P1 D3（已落 `f1c3c1ca`：V134/V135/V136 + `l2_call_ledger_writer.py` + `l2_secret_redactor.py` + 78 tests）。報告 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--l2-p2-orchestrator-tech-design.md`。

**關鍵 grounding 修正（execution-plan 文字已 stale）**：plan §0「V134 next free / V13x after V134」是舊的——**P1 已吃掉 V134/V135/V136**（在 disk @ f1c3c1ca）。P2 真正 next-free = **V137**（驗 `V13[7-9]/V14*` = 0 hits）。但 **P2 結論=不需 migration**（registry=TOML SSOT；admission/adjudication=in-memory+log 進既有 V135 gate-seam；guard verdict 用既有 V134 `guard_verdict` 欄；C1 promote-inbox `learning.l2_promote_candidates` 是 **P5** 非 P2）。V137 reserved-not-used，只在 operator 重開「DB-backed runtime registry override」才取。

**carbon-layer invariants 全 ground 在真碼（CC 會逐條 grep）**：
- `promote_tier` auto-raise L1→L4 with `approved_by=None`：`learning_tier_gate.py:520`(def)/`:525`(approved_by None)/`:550-553`(只 L5 要)/`:570-574`(AUTO_PROMOTE L2/L3/L4) — **C1 hazard 真實**。
- `can_auto_deploy_to_paper=True@all-tiers`：`:185/196/205/218/231` + property `:660-662` — **C2 no-signal 真實**。
- `can_modify_live_config` 硬回 `False`：`:178`(field)/`:664-671`(property literal False, "EX-05 §8.2") — live hard line 已在碼。
- operator-scope WRITE 雙 pattern：`governance_routes.py:129-152` `_require_operator_auth`（docstring 自稱 "standard Depends() target for all write/state-change endpoints"）；TOTP-gated switch `governance_autonomy_service.py:598-601`（C1 promote-confirm 重用此）。`_AUTONOMY_PATH_MATRIX` `:80,116-130`（asymmetry 半成品：(e)/(j) auto-trigger=contract、(a)/(c)/(d) operator manual=expand）。
- `/cost/reset`(`:354`)+`/cost/pricing`(`:389`) POST **已** operator-scope（`require_scope_and_operator(...,"ai_budget:write")` `layer2_routes.py:247`）→ E3-E1 對這兩個是「確認非新增」，只有新 Orchestrator/registry route 要新硬化。

**D3 wiring 接點（P2 wire 進 P1 writer）**：`l2_call_ledger_writer.py:113 record_l2_call / :266 record_consequential_mark / :314 record_gate_seam / :367 get_l2_call_ledger_writer`（全 INSERT-only，已登記 singleton-registry §2.6.1 line 351）。engine 今天已在 `layer2_engine.py:352` 呼 `record_l2_call`，但傳 **hardcoded** `L2_DEFAULT_CAPABILITY_ID`/`L2_PROMPT_CONTRACT_VER`/`L2_OUTPUT_SCHEMA_VER`（`:89-92`/`:355/359/360`）→ **P2 wiring delta = 改成 registry/contract-driven**，既有 manual path 留作 seed `l2.manual_reasoning` capability（無 regression）。

**CC-grep-verifiable 的設計手法（每個 invariant 設成單一 construct 非 emergent）**：LANE_DIRECTION = 一個 loader-owned table（無 `live` key）+ 一個 STEP-1 `if expand: return MANUAL`（function 頂、不可被 tier/posture 覆寫）；C1 = Orchestrator module「0 個 promote_tier ref」；C2 = 「0 個 can_auto_deploy_to_paper posture branch」+ loader-reject；F.2 = table-driven adjudicator「內部 0 model call」；fail-safe iron rule = 「每個 state 都是 L2 capability 的減法、0 個 live-enabling write，worst case=NO_ADVICE=今日 baseline」。

**reuse-vs-new ground 確認**：~70% wiring（LearningTier `:165-234` + path matrix `:80` + P1 writer + operator-auth `:129` + budget gate `layer2_cost_tracker.py:286` + `check_daily_budget` + DOC-08 cap `budget_config.toml:9 daily_usd_max=2.0` + `ConfigDict(extra="forbid")` `agent_contracts.py:109` + RiskConfig TOML SSOT）；~30% net-new（Orchestrator/registry/LANE_DIRECTION/contract registry/guard registry/admission/adjudication 全 greenfield 0 hits）。

**verdict**：E1-ready，**conditional on 1 operator confirm**——鎖「P2 ships TOML-SSOT registry, no DB table, no V137」（§N.1）。其餘 design-decided。CC 擁 load-bearing audit（stress-test 5/6/10/15/16/18）；E3 擁 write-auth + fail-safe-under-fault。殘留 Linux-verify=無（P2 無 migration/無 PG semantic/無 Rust IPC）；E4 欠標準 Mac+Linux test regression。

**教訓**：execution-plan 的 migration-number 文字會被 phase 推進 stale（P1 吃掉 V134-136 但 plan 還寫「V134 next free」）——PA 設計時必 `ls sql/migrations/` + git log 對當前 HEAD 重新確認 next-free，不可信 plan 文字。承 [[project_2026_06_08_l2_d3_phase1]]（同 session P1 設計）。

---

## 2026-06-09 — L2 Advisory Mesh Phase 3 `ml_advisory.v1`（FIRST L2 capability）技術設計 [接 ML 管線]

**任務**：產 P3 設計（design-only，no feature code / no migration / no deploy）。接 P2 Orchestrator（已落 `6a9dd0f1`：**整套 mesh scaffolding 已 commit**——`l2_advisory_orchestrator.py`/`l2_capability_registry.py`+`settings/l2_capability_registry.toml`(skeleton 0 stanza)/`l2_prompt_contract_registry.py`/`l2_out_of_bound_guard.py`/`l2_conflict_adjudicator.py`，全 capability enabled=false）。報告 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-09--l2-p3-ml-advisory-tech-design.md`。

**關鍵框架修正（execution-plan/design 文字假設 P3 較 greenfield）**：P2 已 commit 整套 orchestration plumbing。**P3 不是 greenfield orchestration**——是 (a) 3 個 TOML capability stanza、(b) `ml_advisory.*.v1` PromptContract+OutputSchema 入 contract registry、(c) `ml_advisory.guard.v1` clause 入 guard registry（P2 `get_guard` 是 placeholder echo `l2_out_of_bound_guard.py:154-159`，P3 改 callable registry）、(d) **cascade executor** 接入 P2 dispatch seam（`l2_advisory_orchestrator.py:300-301` 明寫「P3 接各 capability executor + parsed_output」）、(e) **deterministic math gate 含 B1 beta_neutral_check（NEW，QC-gated）**。真問題是 data+math-gate，不是 plumbing。

**ML 管線 seam（全 ground:file:line，execution-plan §0 命令 read in full）**：
- `run_training_pipeline.py:474` `run_pipeline` → `PipelineResult{verdict, metrics{pinball_skill/crossing_rate/decile_lift/feature_schema_hash}, acceptance_report_path, onnx_artifacts}`；sink=fs acceptance-report JSON `:299-312` + `learning.model_registry`(V023) `:374`（gate verdict≠no_ship）。
- `mlde_shadow_advisor.py:578` → `list[ShadowRecommendation]` → **`learning.mlde_shadow_recommendations`** via `verify_replay_evidence_and_insert` `:469-489`，**`p_applied=false`:480 / `p_requires_governance=true`:481 hardcoded**。
- `leakage_check.py:41` `check_feature_leakage(names, strict)` → `(passed, violations)`，**僅 name-pattern**（FORBIDDEN_PATTERNS `:20-30` + ALLOWED_PREFIXES `:33-38`），78 行確認。pure fn 無 sink。
- **advisory sink CONFIRMED 雙層**：schema-enforced（V031 `applied DEFAULT FALSE`:432 / `requires_governance DEFAULT TRUE`:433 / live-gate CHECK 需 decision_lease_id `:444-449` / COMMENT「Not an execution queue」`:466`）+ producer-enforced（advisor hardcode applied=false）。→ ml_advisory feed 此 sink = **0 new exec authority**。

**beta_neutral_check 判定 = MUST BE BUILT（但有可重用 machinery）**：
- grep `beta_neutral` = **0 hits**。必建。
- **BUT `residual_alpha_gate.py` 已存在**（2026-06-05 residual-producer build）：`DEFAULT_REQUIRED_FACTORS=("btc","market")` `:23`，train-window beta fit→OOS residual `:4-5`，`ResidualEdgeReport{residual_mean_bps, beta_loadings, beta_edge_share, r_beta_retention, dsr_residual...}` `:101-127`，`evaluate(candidate_returns, factor_panel, protocol)` `:147`。**這是 B1 重用的 OLS/factor-fit machinery**，但非 B1 本身（residual gate 用 beta_edge_share<0.5；B1 要 `|β_btc|<0.15 AND |β_alt|<0.15 AND |β_down|<0.15` 確定性閾值 + down-market 子樣本 + altcap factor；且 factor_panel 是 caller-supplied，不產 BTC/altcap 序列）。memory「grep beta=0 殺你5次的維度沒接進 gate」=此 machinery 存在但未綁進 production gate。

**B1 data availability 判定（最重要交付）**：
- **BTC return series = READY**（V125 `alpha_history_storage` + daily-kline backfill 14505 日線，承 2026-06-02 aeg infra）。
- **down-market regime label = schema+writer READY, population OWED Linux-verify**：**V127 `research.aeg_regime_labels`** 有 `ret_30d`/`ret_90d`/`main_regime`/`market_anchor_regime`(BTC-anchored)，versioned+leak-free PIT daily（`V127:5-21,68-71`），writer `aeg_regime_runner/db_writer.py:28-79`。down-market mask(30d dd>8% OR 7d<-5%)可從 ret_30d/ret_90d 衍生。**BUT V127 只經 runner `--write-db` 填**（`db_writer.py:6`「默認只產 artifact」；migration `:17-21` 只建表不含 runner data）→ **Linux `SELECT count(*)` owed**。
- **★ PIT cap-weighted altcap basket return series = DOES NOT EXIST，必建（最大 B1 gap）**：grep `altcap/cap_weight/basket/market_cap/weighted-return` over research+ml_training = **0 producer**。FND-2 `fnd2_pit_universe` 只產 **symbol-list artifact**（included/cohort_ids/alive_from，`aeg_breadth_ladder/universe_artifact.py:3-10`；builder.py 0 return/price/cap-weight），**非 return series**。cap-weighted return basket 還需 per-symbol PIT cap × daily return。→ **QC/MIT-data construction item**。

**shift1_compliance / is_oos_gap（M3 leak-typing）判定**：
- **`shift1_compliance` = 0 hits（必建）**。
- **`is_oos_gap` = 只有 namesake-different metric**：`sample_weight_sensitivity.py:329-334` 是 train-vs-OOS **RMSE gap-ratio overfitting** detector，**非** M3 的「真 in-sample→out-of-sample 時序 gap」source-class。leak-typing producer 必建。
- 只 `name_pattern_check` 存在（leakage_check.py）。M3：ml_advisory 不得宣稱 leakage_check 輸出=leak-free PIT；每 leak claim 帶 `source_class∈{name_pattern_check,shift1_compliance,is_oos_gap}`；name_pattern_check 不滿足 math-gate leak 前提。**P3a 只需 source_class typing 強制；producer 是 MIT-owned，gate P3b**。

**3 modes + cascade**：全 `direction=neutral`（`LANE_DIRECTION["ml_backlog"]="neutral"` `l2_capability_registry.py:70`），0 new exec，feed 既有 advisory sink。diagnose_leak/interpret_result（L1，assert no alpha）+ hypothesize（**L3** because `can_generate_hypotheses` first True @L3 `learning_tier_gate.py:203`，bind `tier_capability_flag`）。cascade=Ollama screen(recall≥0.85，reuse layer2_critic)→**deterministic math gate（唯一 alpha validator）**→cloud-L2 interpret only survivors。**LLM 永不驗 alpha**（math gate 唯一，design §G.2:1224）。接 P2 orchestrator `:300-301` executor seam。dsr_gate.compute_dsr(`:381` count-based n_trials，single-config 可跑) reuse；pbo honest-defer single-config（承 2026-06-08 Gap-A PBO ruling）。

**★ P3a/P3b split（最重要建議，execution-plan §1:79-82/§2:197-199 明示）**：
- **P3a**（diagnose_leak+interpret_result，assert no alpha）：gate=**E2+MIT(M3 typing+M4 recall)**，**NOT B1**。**可現在 ship**——證 cascade+D3+M3+M4 於 zero-alpha 面，不等 B1 final / altcap data。
- **P3b**（hypothesize，promotion-relevant verdict）：**HARD-BLOCKED** on **QC(B1 final 4 numbers + altcap construction + leak-free PIT) + (L3 tier) + shift1/is_oos producers**。理由：B1 是 unattended-gate command-line（design §N.1:1864）；P3b 提前 ship 會讓 down-beta masquerade 過無人閘（殺 5 候選的失敗）。tier 對齊強化（L3 + enabled=false 雙閘）。

**Migration 判定 = P3 NO migration**：advisory sink V031 / D3 V134-135 / novelty agent.lessons V133 / regime V127+V125 全既有；registry=TOML。V137 reserved-not-used——只在 QC 要 altcap persisted table 才取（**PA rec：altcap on-the-fly/artifact 避 migration**，mirror FND-2 CSV-artifact）。shift1/is_oos 是 compute 非 schema（讀既有 data）無 migration。

**verdict**：**P3a E1-ready now**（design-decided+grounded，gate E2+MIT 非 B1）。**P3b design-ready 但 EXECUTION-BLOCKED**（QC B1 final + altcap basket 不存在 + shift1/is_oos producers）。rec：先派 P3a 證 cascade，平行開 QC B1-finalize + altcap-construction track。需 operator 鎖「P3 no migration；altcap on-the-fly」或重開 V137。

**教訓**：(1) phase 推進使「greenfield 假設」stale——P2 已 commit 整套 plumbing，PA 必先 `find l2_*.py` + 讀 P2 已 shipped 碼確認 seam（`:300-301` executor hook），不可信 design/plan 文字當 P3 greenfield。(2) 「data 存在」要分三層查：schema(migration) vs writer(producer code) vs **population(Linux runtime)**——V127 schema+writer 在但 population owed；altcap 連 producer 都無。(3) namesake collision 陷阱：`is_oos_gap` 在 sample_weight_sensitivity 是 RMSE-gap 非 M3 leak-typing，grep 命中≠語義命中，須讀 context。承 [[project_2026_06_08_l2_d3_phase1_green]]（同 session P1/P2 設計）+ [[project_2026_06_05_residual_producer_build]]（residual_alpha_gate machinery 來源）+ [[project_2026_06_03_v58_archive_audit_s2_design]]（V127 aeg_regime_labels 來源）。

## 2026-06-09 — L2 Phase 3b 實作設計（hypothesize alpha-bearing + B1 beta_neutral_check + altcap + leak producers）[design-only, E1-READY]
- 交付 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-09--l2-p3b-implementation-design.md`。整合 QC B1 spec（4 numbers FINALIZED, altcap=EQUAL-WEIGHT operator-鎖）+ MIT spec（shift1 reuse / is_oos build / M4 / V127 0-rows）。承 P3a `aeae4da4`（cascade executor 已 ship diagnose/interpret 2 mode）。
- **最 load-bearing 架構真相**：hypothesize alpha-bearing 但 lane 仍 `ml_backlog=neutral`（`l2_capability_registry.py:70`）。verdict 是 promotion-relevant，但**promotion 動作**是另一條 `demo_stage1=expand=MANUAL`（`effective_autonomy` STEP-1 `:119-120`）。B1 gate 的是 verdict 不是 lane → hypothesize 可 neutral 又 B1-gated。alpha 驗證在 cascade 內**確定性 math gate**（唯一 validator，LLM 永不驗，iron-rule grep target `l2_ml_advisory_executor.py:27-35` 已驗 comment-only 0 calls）。
- **B1 插 math gate 序（§A.5）**：STEP0 Q1(N_trades_oos≥50→DEFER via `dsr_gate.compute_dsr(min_observations=50)`→insufficient_observations→defer_data `:465-507`)→STEP1 DSR(K)→STEP2 PBO honest-defer(single-config，承 2026-06-08 Gap-A 不 fabricate peers)→**STEP3 beta_neutral_check(pooled β_btc/β_alt on≥90d + down-leg β_down on≥180d-span)**→STEP4 leak precondition(shift1/is_oos leak_free=True 否則 DEFER)。overall=strictest-wins(fail>DEFER>pass，mirror `residual_alpha_gate._verdict_from_blocking_reasons:882-889`)。B1 是與 DSR 同 tier 的 hard precondition（design §N.1(5)）。
- **SE 加法點（§A.2）**：reuse `residual_alpha_gate._fit_factor_beta:619-624`(np.linalg.lstsq)**不 fork**，wrap 加 SE=sqrt(σ²_resid·diag((X'X)⁻¹))（QC formula）；DW<1.5→HAC Newey-West（Bartlett kernel，hand-roll 無 statsmodels，仿 dsr_gate `:161-164`）。β_upper=β+1.96·SE<0.20 殺 noisy-small-β（5 候選失敗模式）。down-mask=klines-direct lagged-PIT（MIT Path B，不硬依 V127，V127 0-rows runtime-verified）。
- **altcap producer（§B）**：`program_code/research/altcap_basket.py` 新建，equal-weight ex-BTC CORE25 24 檔（`cohorts.py:27-33` minus BTCUSDT）daily-rebal on-the-fly。**PIT walk-forward**用 FND-2 `alive_from`/`alive_to`（`builder.py:235-236` clip-to-window；`SymbolLifecycle.listed_at/delisted_at:79-80` 是 lifetime 權威，first/last_seen_ts:83-84 診斷-only snapshot 27d 陷阱）。bar t 用 t-時 alive set 非今日 survivors，no zombie forward-fill = **唯一 M3 leak hot-spot**。producer 無 → altcap_returns=None → B1 DEFER（BTC-only）。**NO V137**。
- **shift1_compliance（§C）**=thin adapter reuse `feature_engineering_validator.py`（`is_leaky_sql:43`/`is_leakfree_sql:51`/`validate_shift1_pattern:72-113`）emit source_class；any DEFER→leak_free=False fail-closed。**is_oos_gap（§D）**=新建 `check_oos_gap`（distinct 名避 `sample_weight_sensitivity.py:329` RMSE-gap namesake，MIT option(a) 保 source_class string `:157` PA concur），temporal-sep+embargo+purge+no-shuffle 4 檢查。兩 producer 缺→math gate leak precondition unmet→hypothesize DEFER。
- **hypothesize mode（§E）**：TOML stanza `min_tier=L3`(`learning_tier_gate.py:203` can_generate_hypotheses first True@L3)+`tier_capability_flag=can_generate_hypotheses`+`enabled=false` 雙閘。executor 擴 `_P3A_MODES:563` 加 hypothesize + 插 math-gate STAGE(guard 後 sink 前，只 hypothesize)。guard 擴：reuse clause D(axes `:277-287`)+clause C(regime/bull-only `:257-275`)+NEW empty-mechanism curve-fit clause；**novelty dedupe 不在 guard（guard 0-DB 不變式 `:24`）改在 executor 跑 `retrieve_lessons(lesson_type=dead_mode)` DB 讀**（修正 naive「guard 做 novelty」誤讀）。promotion routing=demo_stage1 expand MANUAL，auto 須 B2 forward-OOS≥21d demo-only。**0 promote_tier/order/lease import；can_modify_live_config=False 不碰；C1 AUTO_PROMOTE_L3_TO_L4 `:119` 不觸**。
- **Migration 判定=P3b ZERO-migration，V137 reserved-not-used**（全 compute/JSON/TOML；altcap on-the-fly；V127 schema 已 applied sqlx_max=133 只欠 population）。
- **2 個 E1 implementation decisions（非 blocker）**：(i) cascade order reconcile——P3a executor cloud-first(`:591` before guard `:611`)，design §G.2 要 Ollama-generate→math-gate→cloud-interpret-survivors（cost 紀律 root principle 13），E1 implement §G.2 序；(ii) M4 artifact path 對齊 `..._screen_benchmark.json`(MIT) vs `..._screen_calibration.json`(P3a loader `:153`)。
- **owed-runtime（非 design blocker，blocks verdict-going-live）**：V127 population / agent.lessons seed 5-10 dead-modes / down-bars≥30 確認(full-span=309,last-90d=23) / altcap Linux smoke。
- **verdict=E1-READY** conditional on 4 cross-team sign-off（operator altcap=equal-weight+zero-migration 已 prompt CONFIRMED；QC B1 final；MIT M3/M4 + is_oos option(a)）。其餘 design-decided ground file:line。
- **教訓**：①hypothesize「alpha-bearing」但 lane 仍 neutral——promotion-relevant 是 verdict 屬性非 lane 屬性，promotion 動作走獨立 expand/MANUAL。設計時別把「會 promote」誤當「lane=expand」。②novelty dedupe 需 DB 讀 → 不能塞進 0-DB 的 guard，要放 executor（已有 DB I/O）。guard 純確定性無 DB 是 load-bearing 不變式，別為 novelty 破它。③SE 是 residual_alpha_gate 唯一沒做的——OLS 全可 reuse(`_fit_factor_beta`)，wrap 加 SE+DW+HAC 即可，不 fork lstsq。④P3a executor cloud-first 與 design §G.2 math-gate-first 衝突——phase 推進使 executor 既有路徑與後階設計不一致，E1 須 reconcile，PA 設計時要抓出這種「既有實作 vs 後階 spec」的序差。承 [[project_2026_06_09_l2_p3_ml_advisory]]（同 session P3 設計）+ [[project_2026_06_08_l2_d3_phase1_green]]。

## 2026-06-10 — L2 P3b owed-before-enable：conductor wiring（owed ①③）+ dead-modes seed（owed ②）+ deployed-E2E 入口設計 [design-only, E1-READY]
- 交付 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--l2-p3b-owed-conductor-wiring-design.md`（worktree `/tmp/wt-l2-owed` branch `fix/l2-owed` @ `0ce45a09`）。main 已 deploy P1-P3b（sqlx=136，3 表 dormant，registry 全 enabled=false）；`dispatch_and_execute`（orchestrator :379）零 production caller = 本輪要補的洞。
- **三個 load-bearing 偵察事實**：① math gate 真契約比任務描述多 2 鍵——leak stage 讀 `shift1_compliance_leak_free`/`is_oos_gap_leak_free`（executor :1139-1140），映射表必含。② **AEG-S3 候選來源無 daily return series**——`aeg_candidate_metrics/builder.py`（main `f3d4a29e`）輸出 per-regime 標量 rows（n_independent/oos_sharpe/k_trials...），harness 內部 series 不進 report JSON → candidate_returns 缺=B1 DEFER 誠實；**嚴禁標量合成常數序列（OLS β≈0 → B1 偽 pass，比 DEFER 危險——直接放行 down-beta 偽裝）**。③ `retrieve_lessons` filter=`WHERE symbol=%s`（必）+lesson_type+trgm；**source 完全不參與 filter**（layer2_critic :326-340）→ seed source 用第 4 namespace `dead_mode_seed` 純 provenance 區分；**symbol 才是命中關鍵**：seed 全用 placeholder `ml_advisory`（=_SINK_SYMBOL_PLACEHOLDER :444）+ 配套 `_check_novelty` 6 行 union 修補（先具體 symbol 後 placeholder），否則帶 symbol 的 dispatch miss 全部 seed=死資料。
- **設計決策**：觸發入口=(a) 新 operator-scope route `POST /api/v1/paper/layer2/ml-advisory/dispatch`（reuse require_scope_and_operator :254 pattern；inline-only evidence 零 path traversal；cron 拒=P2 open question+manual 哲學；CLI=curl 薄殼）。deployed-E2E 兩段：E2E-0 zero-enable（disabled dispatch → `_record_admission_seam` :330 真 seam row=鏈路證明，零 model call）+ E2E-1 operator-gated（enable diagnose_leak L1 一次→真 l2_calls→disable；不用 hypothesize 做 E2E）。owed ③=新 `app/l2_candidate_evidence_adapter.py` 兩層（純函數 build_math_gate_context + DB 層 load_factor_bundle reuse altcap producer/compute_down_market_mask）；regime 多行無顯式選擇→DEFER（防 cherry-pick selection bias）。owed ①=新 `learning_engine/bar_index_reindex.py` 純函數；**push back 任務的「0..N-1」**：`_span_days` 對 int key 用 max−min 當天數（beta_neutral_check :569-592），down-leg ≥180d 是 calendar span 語意→dense 0..N-1 在缺 bar 時低估 span，採 ordinal-day offset（無缺 bar 時恰=0..N-1；雙規則實作 index_rule 參數可切）；4h fail-loud 不支持（toordinal 撞 key）。owed ②=6 條英文主幹 seed（funding_arb_v2/funding_short_v2/cascade_fade/funding_tilt/grid_short_downtrend/textbook_scalping；**不 seed listing fade**=active 主路徑且在 M4 good-set 側）；工具=helper_scripts/m4/seed_dead_mode_lessons.py 默認 --dry-run 顯式 --write+--dsn、context_id=seed:<slug> 冪等錨點。
- **E1 拆分**：E1-A（learning_engine+helper_scripts）∥ E1-B（control_api app/）檔案零重疊；全部新測試強制 autouse `_no_real_db`（承 `0ce45a09` prod 污染 RCA：mock 不掩蓋邏輯的對偶=連線層必隔離；Mac fail-soft 吞錯假綠、連得上 prod 的環境就真寫）。layer2_routes 760→~835 超 800 review 線（標註）。
- **教訓**：①「producer 接口存在」≠「序列存在」——aeg_candidate_metrics 名字像 series producer 實為標量 normalizer，owed ③ 設計前親讀 builder 全文推翻「轉換層只是欄位改名」的隱含假設；缺的維度（daily series）誠實 DEFER + 契約預留，而非在 adapter 層補洞。② pg_trgm 檢索的三重對齊（symbol 相等 + lesson_type 相等 + content 語言同 hint）任一錯=seed 永 miss；中文 content vs 英文 statement 相似度≈0 是最隱蔽的死資料模式——seed 落庫前必須用 retrieve_lessons 真查驗收，不能只驗 INSERT 成功。③ re-index 規則不是純編號問題：int key 的數值差會被 `_span_days` 當天數消費，「交集後怎麼編號」直接改變 QC 檢查的語意，設計 re-index 必先 grep 誰消費 key 的數值（非只有序）。承 [[project_2026_06_08_l2_d3_phase1_green]]（P3b 設計同鏈）。
