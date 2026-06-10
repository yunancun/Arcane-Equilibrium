# 幽靈倉位記帳 bug 修復 + 部署 (2026-06-08)

## 觸發
Operator 從 GUI 觀察到 demo 一個 ~30 USDT(峰值 +44)盈利倉「消失」。深挖(Bybit execution/closed-pnl live 查詢 + PG position_snapshots + engine.log + watchdog.log)發現:

## RCA（鐵證）
- 標的 **TONUSDT demo**。Bybit execution list 在 17:00–17:43 CEST **只有 2 筆**:`oc_dm` Sell 437.3@1.5929 開 short(17:01)、`oc_risk_dm`(=trailing/risk close)Buy 437.3@1.5744 **完全平掉** short(17:03,closedSize=437.3)。淨額=0 → Bybit 17:03 後對 TON **空倉**;唯一 closed-pnl=+7.57(short)。
- 但引擎 `trading.position_snapshots`(engine_mode='demo')從 17:03:01 記了**幻影 LONG 437.3@1.5744**(entry=short 的 exit 價、qty=short 的 qty),28548 筆假快照,假浮盈峰值 +44/末 +34.50,活到 00:25:55。
- **根因**(PA `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-07--phantom-position-fill-bug-design.md`):`PaperState.positions` 被 **PositionUpdate 與 Fill 兩個無序源競態**。Bybit 平倉先推 `position(size=0)` → `fill_engine.rs` `positions_remove` 成 flat → 隨後平倉 Buy fill 到 `apply_fill`(`fill_engine.rs:295` `if let Some(pos)`)找不到倉 → 落 `:364` 開新倉分支 → 幻影 LONG。次要 bug:`:299` `close_qty=pos.qty.min(qty)` 翻倉餘量靜默丟棄(翻倉根本沒實作)。
- **後果**:① 幻影遮蔽「已空倉」→ 引擎以為持倉 → 沒重新開真 long → **錯過 TON 真實 +5%(~+34)機會**(這是 operator「不要錯過機會」的真實損失,非 trailing stop 失效);② 幻影自身 trailing(00:00 phys_lock_gate4_giveback)觸發卻平不掉 → 空轉 → 引擎 00:25 卡死 → watchdog 重啟 → 從 Bybit 重新同步抹掉幻影 = operator 看到的「消失」。
- **trailing stop 其實正常**:它在 17:03 平了真實 short(+7.57,oc_risk_dm)。+7.57 與 +44 是**不同倉位不同時間**;+44 是幻影假浮盈,從來沒有真倉可鎖。
- 為何 reconciler 沒抓到:`position_reconciler` 比的是「Bybit 上輪 vs Bybit 這輪」(both `pos_mgr.get_positions`),TON 一直 flat → 永遠 Match;**從不掃本地帳找 Bybit 無對應**=結構性盲視。

## 修法（Option A，PA→E1→E2→E4 全綠）
- `PositionUpdate` 降為 **advisory 只讀比對**(`loop_exchange.rs`),`size=0` 走既有 `converge_exchange_zero_close`;`apply_fill` 成為倉位**唯一 mutating 源** → 競態消失。
- 新 `apply_fill_with_close_semantics(is_close)`(`fill_engine.rs`):reduce-only/close 在本地無倉時 **fail-closed no-op**;真翻倉(qty>pos.qty)用餘量建反向倉。舊 `apply_fill` 保留為薄包裝(~90 caller,is_close=false,byte-identical)。
- `position_reconciler` 新增**幻影偵測軸**(本地 mirror vs Bybit current,presence+side,`absent`/`side_mismatch`),**只告警不收斂**,寫 DB `observability.engine_events`(type `reconcile_phantom_local`)+ canary。
- 偏差:T4 mirror 保留 bool(非 struct,blast radius 太大),用 presence+side 偵測(放棄 qty-band);E2 ACCEPT。純 Rust 無 Python parity(Python 無倉位帳本)。
- **需求 #2** 是 #1 下游:修好後平倉正確歸 flat → 策略「已持倉」檢查放行 → 自動重新入場;E2 驗 is_close 雙向(真開倉不被誤判 no-op)→ 不會吞掉真進場。未加投機性複利。

## commit / 部署
- Mac 修復:`74b2e264`(fix 8 檔 +753/−30)+ `6d312405`(E4 8 個整合 golden 3 檔),branch `feature/l2-critic-lessons-tools`,push 到 origin `fix/phantom-position-fill-race`。
- cherry-pick 到 main(零衝突,我的 5 修改檔在 b00c249d→main 之間 identical)→ origin/main `8cd4da1f→bdf15e4f`,trade-core 運行此版。
- **部署**:`helper_scripts/build_then_restart_atomic.sh`(flock → `cargo build --release -p openclaw_engine` 只建置不測 → `restart_all.sh --engine-only --keep-auth` → `/proc/PID/exe` SHA 原子驗證)。新引擎 **PID 630029**,SHA `b062e5c6…`,demo alive、空倉、reconciler(含新軸,interval 30s)已啟動,無 panic/FATAL。
- 驗證:Mac 4153/0;**Linux 權威 `cargo test --lib` 3787/0** + 20 phantom 測試 Linux 全綠(`g1 TON 17:03 重現`/`g3 三模式`/`orphan_adopt 自癒`)。

## 剩餘 / 教訓
- 告警**只到 DB 可查**(operator 選 defer 推播):查 `observability.engine_events` where event_type='reconcile_phantom_local'。canary_events.jsonl **無 forwarder**(pre-existing infra gap,push 推播是獨立 task)。
- Linux 全整合套件(40 binaries)未在 Linux 重跑(Mac 全綠 + Linux lib/phantom 綠,純 Rust 低風險)= owed。
- **LiveDemo pipeline 拒啟**(缺 `authorization.json`,6/6 21:32 起,非本次造成);恢復需 `POST /api/v1/live/auth/renew`。demo pipeline 正常。
- 行為層生產驗證待下次真實平倉/翻倉自然觸發;reconciler 持續監看。
- 教訓:GUI 顯示忠實反映引擎(錯誤)快照,非 GUI bug;「倉位消失」根因往往在引擎本地帳 vs 交易所背離。代碼路徑:`paper_state/fill_engine.rs`、`event_consumer/loop_exchange.rs`、`tick_pipeline/commands.rs`、`position_reconciler/mod.rs`。
- 承 [[project_2026_06_05_engine_selfheal_bindhost_incident]](同樣是引擎卡死+watchdog 重啟主題)。

## Post-deploy 審計 + mlde ambiguous-column 回歸修復 (2026-06-09)
operator 要求審「隨我 rebuild 一起上線的、我不熟的修復」。判定:我這次 rebuild 的 binary 實際**只多了 phantom 修復**(dispatch 110072/10001 Rust + residual/postmortem Python 在 01:45 June7 那次 rebuild 就部署了;我的 binary delta 只有 phantom)。逐一**真實數據**審:
- **dispatch 110072/10001**(Rust 平倉路徑):乾淨,零 dispatch/平倉錯誤,4 次真實平倉正常,idempotent handler 休眠(無重複 orderLinkId 觸發)。
- **residual hook**(Python,daily ML cron 03:17 帶 `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` **ON**,非 inert!engine/API 進程才是 OFF):運作正常,06-08 cron log `residual evidence attached to 9/9 recommendations`、`caps=22/22 residual_registry=on`;輸出表 `demo_residual_alpha_reports`/`hidden_oos_state_registry` 空=**按設計 defer**非失敗。
- **抓到真回歸**:`mlde_demo_applier` `AmbiguousColumn: engine_mode`。root cause:06-07 residual/hidden_oos registry join(`replay.experiments e`/`demo_residual_alpha_reports drar`/`hidden_oos_state_registry hos`)上線後,base 表 `learning.mlde_shadow_recommendations` 裸欄位與 e/drar/hos 同名欄(engine_mode/source/strategy_name/replay_experiment_id/manifest_hash/created_by)衝突 → cron 每天失敗 ~2 天。**learning 層,不影響交易/不造成幻影**。修法:base 表加 `msr` 別名 + 全裸欄位限定(SELECT/WHERE/ORDER BY/JOIN-ON/evidence_filter)。E1 commit `28e376c0`(off-main worktree),E2 PASS=**真 PG EXPLAIN 修前重現 ambiguous/修後 21-row plan + 6 mutation 驗 bite**,sibling 5 檔 clean(只此檔 multi-join+裸欄位)。
- **pre-existing**(非本次部署造成,別歸咎):`mlde_shadow_advisor` QueryCanceled timeout(根因 `mlde_try_float8` 慢查,log 112 次歷史)、`quantile_trainer` registry persistence DB 連線 precheck、insufficient-samples(MIN_SAMPLES=200 多策略不過)。
- **三端同步** `28e376c0`(push origin/main ff `6c1b015f→28e376c0` + trade-core ff pull,Linux pytest 26 passed,Python 無 rebuild,03:17 cron 生效)。phantom 修復持續健康(running binary `b062e5c6` 保留,bdf15e4f 為 28e376c0 祖先;main 無新 Rust 故 binary 不落後)。清掉冗餘 `origin/fix/phantom-position-fill-race` 分支(內容已在 main)。
- 剩:mlde fix 端到端待 03:17 cron 確認(查 `/tmp/openclaw/status/ml_training_maintenance_status.json` mlde_demo_applier 是否轉 ok);LOW follow-up=mock 測試抓不到 partial-qualification,建 PG-integration EXPLAIN 回歸測試;residual PART 4(`6c1b015f`,他 session,我未審)已在 trade-core source。
- 教訓:rebuild 部署會把 main 上**所有**未進舊 binary 的改動一起編譯上線——deploy 後須審「搭車」的非己改動;cron 帶的 env-flag(`=1`)可讓「進程裡 OFF」的功能其實在 cron 裡 ON,別只看進程 environ 下結論。


---

## [index-archive 2026-06-10] 原 MEMORY.md 索引條目全文(壓縮索引前歸檔,內容為當時點狀態)

- [幽靈倉位 fill 記帳 bug 修復+部署 (2026-06-08)](project_2026_06_08_phantom_position_fill_fix.md) — demo TON「~30盈利倉消失」根因=`PaperState` 被 PositionUpdate/Fill **無序雙寫競態**(Bybit 平倉先推 size=0 移除倉→隨後平倉 fill 落 `apply_fill` 開新倉分支→幻影反向倉,entry=平倉價/qty=平倉量)。**trailing stop 其實正常**(17:03 平真 short +7.57,oc_risk_dm);+44 是幻影假浮盈非真倉;幻影遮蔽空倉→錯過真實 +5%。修法 Option A:PositionUpdate 降 advisory、`apply_fill` 唯一 mutator + reduce-only fail-closed no-op + 翻倉餘量;reconciler 新增幻影偵測軸(本地 vs Bybit,只告警,DB `reconcile_phantom_local`)。PA→E1→E2(mutation 驗 bite)→E4(8 golden 含 TON 重現/三模式/自癒)全綠;Mac 4153/0+**Linux 3787/0**+20 phantom 測試 Linux 綠。**原子部署** `build_then_restart_atomic.sh`:PID 630029/SHA b062e5c6,demo alive 空倉 reconciler 啟動無 panic;commit `74b2e264`+`6d312405` cherry-pick→origin/main `bdf15e4f`。剩:告警只 DB 可查(push forwarder defer,operator 選)/Linux 全整合 40-bin owed/LiveDemo 缺 authorization.json 拒啟(既有非本次)。承 [[project_2026_06_05_engine_selfheal_bindhost_incident]]
