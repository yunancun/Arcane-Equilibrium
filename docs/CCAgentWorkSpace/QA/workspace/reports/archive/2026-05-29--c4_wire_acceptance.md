# QA 整合驗收 — P2-PACKET-C-C4-PIPELINE-WIRE（半 wire scope）

**Date**: 2026-05-29
**Auditor**: QA — Quality Assurance（最後集成驗收 / Wave 完成前 sign-off gate）
**Scope**: C4 自主 fail-safe 接進 runtime（in-band escalate + owner handler + ATR 注入 + paper 雙 noop + watcher spawn）的**半 wire** 整合驗收
**Worktree**: `/Users/ncyu/Projects/TradeBot/wt-c4` · branch `fix/packet-c-c4-wire` · base HEAD `2b65ffe6`（C4 = working-tree uncommitted +647 LOC 全 Rust，10 modified + 1 untracked test）
**前置鏈**: E2 APPROVE-WITH-CONDITIONS（5 cond）+ BB APPROVE-WITH-GUARD（1 advisory G-1）+ E4 PASS（上游 module 107/0）
**Boundary**: read-only；不 commit / 不改碼 / 不改 runtime；ssh 只讀。半 wire 是已知設計（非缺陷）。
**Verdict**: **ACCEPT-WITH-CONDITIONS** — 可 commit + 進 batched deploy；2 conditions 必 merge 前清（C2 singleton 登記 + C4 Sprint 3 ticket 註冊），其餘為 Sprint 3 scope 或 advisory。

---

## §1 — wire 整合結構完整（非 dead-stub）— PASS

| 組件 | 落點 | 真接 / Noop-with-reason | 證據 |
|---|---|---|---|
| in-band command | `tick_pipeline/mod.rs` `PipelineCommand::NotificationFailsafeEscalate{reason, response_tx}` | 真 enum variant（與 D2 `ConvergeExchangeZero` 同 enum 不同 variant，0 衝突） | git diff +32 |
| async 攔截路由 | `loop_handlers.rs::handle_pipeline_command` | 真攔截（含 await），`handle_paper_command` 同步分支 fail-loud（回 Err 不靜默 drop） | git diff +17 / handlers/mod.rs +18 |
| owner handler | `handlers/risk.rs::handle_notification_failsafe_escalate` | 真 production 邏輯：`paper_state.positions()` snapshot + `kline_manager` ATR14 注入 + `execute_failsafe_escalation`（SM-04 transition + lock-profit + exchange sync + audit） | git diff +217（risk.rs 822 行） |
| ATR 注入 | `compute_position_atr`（risk.rs）`kline_manager.get_ohlcv→indicators::atr(...,14).atr` 絕對值 | 真接 owner-task kline；缺 bar→None→0.0 fail-closed 跳該倉（誠實 warn `atr_missing`） | 對齊 spec §1.2/§1.3 |
| exchange sync | `InBandStopSync`（risk.rs）→ `pipeline.stop_channel()` = 既有 `stop_request_tx` 雙軌 | 真接既有 server-side stop consumer→`set_trading_stop`（**不新構第二 PositionManager client**，比 spec 原 `BybitExchangeStopSync` 更貼 Root Principle 1） | BB §1 grep 三方一致 |
| watcher seam | `single_watcher.rs::timer_expired_and_claim()` 取代 runtime `check_timer`（標 `#[cfg(test)]`） | 真 production seam（claim-before-await 同鎖 set flag）；舊 check_timer 保留供 test，明標非 dead | git diff +150 |
| spawn wire | `tasks.rs::spawn_notification_failsafe_watcher` ← `main_boot_tasks.rs` 緊隨 reconciler 呼 1 次 | 真單例 external task（`SHARED_WATCHER` OnceLock）；spawn fn 1 def + 1 caller（E2 grep 驗） | tasks.rs +131 / main_boot +6 |
| watcher 端 provider | `NoopPositionProvider` / `NoopExchangeStopSync` / `NoopAuditEmitter` | **Noop-with-reason**（真值下放 owner handler；init 簽名要求 5 trait → 注 Noop 占位，runtime 不被呼） | single_watcher.rs doc §1.3/§2.3 明標 |
| C3 `RestPositionProvider` | superseded（snapshot 改 owner-task） | 明標 superseded（保留供未來 out-of-band probe + C3 test 覆蓋），非 silent dead | spec §1.3 / E2 確認 |

**結論**：8 production 組件全真接、3 watcher-端 provider 是明標 Noop-with-reason（真值在 owner handler），無 silent dead-stub。**唯一刻意未接 = incident-trigger（Sprint 3）**。

---

## §2 — 機制鏈 test 覆蓋（半 wire scope）— PASS + 明標 gap

**QA 親跑 Mac arm64 dev build**（read-only test，不改碼/runtime）：

```
cargo test -p openclaw_engine --lib c4_failsafe   → 3 passed / 0 failed
cargo test -p openclaw_engine --lib               → 3622 passed / 0 failed / 1 ignored (pre-existing)
cargo test -p openclaw_engine --lib notification_failsafe → 108 passed / 0 failed
```

baseline：D2 後 lib 3619 → C4 +3 = 3622 (+1 ignored)。spec §6.3 預估 +4~6，實際 +3（恰 3 wire test）。0 既有 test 被刪/ignore/改 assertion 遮蓋。

| 可測機制（半 wire 內） | test | 覆蓋 |
|---|---|---|
| SM-04 Normal→Defensive transition | `e2e_c4_failsafe_inband_escalate_demo` | ✅ from=NORMAL/to=DEFENSIVE/succeeded=true |
| ATR lock-profit StopAdjustment 生成 | 同上 | ✅ adjustments_count≥1 + SL=entry+atr×0.5=50250>entry |
| 雙軌 exchange sync（demo 真路徑） | 同上 | ✅ stop channel 收 StopRequest(BTCUSDT, is_long, SL>entry) |
| claim-once idempotent（claim-before-await） | `e2e_c4_watcher_allfail_arms_then_claims_once` | ✅ 未到期 false / 到期首次 true / 第二次 false / ack 解除後新武裝可再 claim |
| 誤升雙防線（PartialFail/未到期不武裝） | 同上 + evaluate_dispatch（C3 既有） | ✅ AllFail 才 arm；未到期 claim=false |
| paper noop（SM-04 升但不打交易所） | `e2e_c4_paper_skips_exchange_sync` | ✅ paper 升 Defensive + 0 StopRequest |

**識別 gap（Sprint 3 QA scope，非本次缺陷）**：
- incident_policy 偵測事件 → `dispatcher.dispatch_3way` → `outcome_tx.send` 的**自發觸發**（C4 test 用手動 `observe_dispatch`/直呼 handler 模擬，production producer 不存在）。
- 真 V114 PG audit row 落地（C4 test 用 `audit_pool=None` fail-soft noop，Mac 無 PG；owner handler PgAuditEmitter 路徑未跑 testcontainers）。
- live slot 真實 respawn 時 cmd_tx 不 stale 的 runtime 驗（test 不起 LiveAuthWatcher）。
- 真實 Bybit `set_trading_stop` retCode fail-closed（BB §3 靜態審 PASS；runtime 觸發 Sprint 3 才有）。

→ 4 gap 全 = incident-trigger 接上後才能測，已正確劃為 Sprint 3 QA scope。

---

## §3 — dormant-safety（deploy 安全核心）— PASS（源碼雙重證）

deploy 後 watcher 在跑但 escalate **dormant**。確認不誤升 Defensive（會平倉）/ 不誤打 set_trading_stop。源碼證鏈（grep + read 驗）：

1. 唯一武裝入口 = `evaluate_dispatch(AllFail)` set `timer_armed_at_ms`（mod.rs:305-309）；`AllSuccess` 解除、`PartialFail=>NoAction`（mod.rs:294/314）。
2. production 端 `observe_dispatch` 唯一 caller = watcher loop `tasks.rs:997`，只在 `outcome_rx.recv()→Some(outcome)` 時跑。
3. `outcome_tx` 唯一持有點 = `FAILSAFE_FEED_SENDERS` OnceLock（single_watcher.rs:88）；getter `failsafe_feed_senders()` **0 production caller**（grep 全 src 僅 1 def，Sprint 3 incident_policy 才是第一個取用者）。
4. ∴ `outcome_rx` 永空 → `timer_armed_at_ms==None` → `timer_expired`（mod.rs:345-348）`None=>false` → `timer_expired_and_claim()` 永回 false → escalate command 永不發 → owner handler 永不跑 → `InBandStopSync` 永不 send → `set_trading_stop` 永不被 C4 觸及。
5. 兜底：default state `timer_armed_at_ms:None`；`timer_expired` 首查 `escalated_for_current_arm` guard。

**watcher task 本身** = 30s 空轉 `tokio::select!`（cancel / timer tick→claim 永 false / outcome_rx 永 pending / ack_rx 永 pending），0 副作用、不 busy-loop（`FAILSAFE_FEED_SENDERS` 保活 tx 使 `Some(_)=recv()` 臂正常 pending 而非立即 None 退化 spin）。

cross-verify：BB §6 獨立追同一鏈得同結論（「C4 deploy 後交易所面 0 實際影響」）。**dormant-safety 成立 — deploy 後 0 誤升 / 0 誤打 stop。**

---

## §4 — batched-deploy pre-flight checklist

| 項 | 檢查 | 結果 |
|---|---|---|
| (a) 無新 V### migration | git status / diff 全 worktree | ✅ **NONE**（C4/D2/D-hygiene 皆無新 migration；C2 V114 schema 是 C2 已 land，C4 不新增） |
| (b) 三者合併無 source 衝突 | C4 改檔 ∩ main-only commit 改檔 | ✅ overlap=2（`main_boot_tasks.rs` + `E2/memory.md`）；`main_boot_tasks.rs` **不同行區**（C4=production `spawn_position_reconcilers` L140 / D-hygiene=test `mod edge_reload_tests` L637+ ENV_GUARD）→ 3-way auto-merge clean；memory.md append-style 低風險 |
| (b') 拓撲 | merge-base(branch,main)==branch HEAD | ⚠️ **main 領先 branch 5 commit**（含 D-hygiene `af92e2ca`）；D2 `a5e1ded1`+HIGH-1 `3423f0f7` 在 branch ancestry；**D-hygiene NOT 在 branch** → commit C4 後須先 ff/rebase 上 main 再 merge（無 Rust file-scope 衝突，僅拓撲整理） |
| (c) rebuild+restart 影響 | ssh 實測 | engine PID 113386 alive（release binary, start 17:51 CEST）；Linux main HEAD=`af92e2ca` 已含 D2+D-hygiene+HIGH-1，running binary post-date 三者 → **C4 是 batch 內唯一 net-new source**；`restart_all --rebuild` = engine 重啟 + demo/live 短暫中斷 + auto-migrate **0 新項**（無 V###） |
| (c') Linux byte-equiv | C4 在 Mac worktree，未上 Linux | ⚠️ deploy 後須 `ssh trade-core cargo test -p openclaw_engine --lib` 驗跨平台同 3622/0（Mac arm64 ≠ Linux x86-64 byte-equiv，per memory 12.6 + project_2026_05_02_p0_sqlx「cargo test PASS ≠ runtime sqlx migrate 驗」） |
| (d) 9 安全不變量 + 5-gate | C4 是風控收緊（Normal→Defensive reduce-only），不放鬆 | ✅ 0 觸碰 `live_execution_allowed`/`max_retries`/`OPENCLAW_ALLOW_MAINNET`/`authorization.json`/`live_reserved`；transition 走既有 `governance.risk.transition`（收緊非繞過）；exchange sync 走既有單一寫入口 + retCode fail-closed 不重試（BB §3）；Root Principle 1/4/5/6/9 對齊（BB §交易所面 + PA §7 self-attest） |

---

## §5 — conditions / follow-up 追蹤

| 來源 | 條件 | 狀態 | 必清時點 |
|---|---|---|---|
| E2 C1 | BB 審 set_trading_stop 交易所面 | ✅ **DONE** — BB APPROVE-WITH-GUARD（`2026-05-29--c4_set_trading_stop_trust.md`） | — |
| E2 C2 | `SHARED_WATCHER`+`FAILSAFE_FEED_SENDERS` 登記 singleton 表 | ❌ **OPEN** — `docs/architecture/singleton-registry.md` 0 hit；C4 未改該檔（CLAUDE §九「new mutable singleton 須 merge 前登記」違反） | **merge 前** |
| E2 C3 | risk.rs 822 行（>800 review 門檻） | ⚠️ **NOTED** — 已 review attention（本次 +217 推過 800）；未來再長須評估拆分 | 監控 |
| E2 C4 | Sprint 3 `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` ticket 開 | ❌ **OPEN** — TODO 0 該 ticket（只有 C5 在）；spec §5.3 mandate「C4 closure 必同時開」未做 | **merge / closure 前** |
| E2 C5 | deploy batched + E4 Linux 跨平台同 baseline + restart 實測 | ⏳ **deploy-gated** — 見 §4(c')，deploy 後 operator/E4 跑 | deploy 後 |
| BB G-1 | 字典補 set_trading_stop long/short SL 方向約束 + lock-profit 未獲利倉被拒屬預期 fail-closed | ⏳ **advisory（非阻）** — 併 BB 字典 backlog；防未來誤加 retry | 下次 BB 啟動 |
| BB FU-2 | Sprint 3 incident-trigger 接上時 BB mandatory re-review | ⏳ **Sprint 3** — set_trading_stop 屆時真觸發 | Sprint 3 |

**新識別（QA）**：本次任務 framing「E4 PASS 已過」指的是上游 module（2026-05-28 notification_failsafe 107/0, commit `920f8299`）regression，**不是** C4 wire（+647 working-tree）的 E4。C4 wire 在此 worktree state **無獨立 E4 report**。QA 已親跑補上機制驗證（§2，3 PASS + lib 3622/0），但**正式 E4-on-C4-diff（含 clippy + Linux 跨平台）建議補一輪**或併入 E2 C5 deploy-gate。

---

## §6 — 結論

**ACCEPT-WITH-CONDITIONS for commit + batched deploy**

1. **wire 結構完整非 dead-stub** ✅ — 8 production 組件真接 + 3 watcher-端 Noop-with-reason（真值下放 owner handler）+ C3 RestPositionProvider 明標 superseded；唯一刻意未接 = incident-trigger（Sprint 3）。
2. **機制鏈 test 覆蓋** ✅ — 3 c4 wire test 覆蓋 SM-04 transition / ATR lock-profit / 雙軌 sync / claim-once idempotent / paper noop（QA 親跑 3 PASS + lib 3622/0）；4 gap 全 = incident-trigger 後才可測，正確劃 Sprint 3 QA scope。
3. **dormant-safety** ✅ — 源碼雙重證（武裝入口 0 production caller + `timer_armed_at_ms` 永 None）+ BB cross-verify：deploy 後 0 誤升 Defensive / 0 誤打 set_trading_stop / watcher 0 副作用不 busy-loop。
4. **batched-deploy pre-flight** ✅ — 0 新 V### migration；`main_boot_tasks.rs` 衝突點不同行區（auto-merge clean）；C4 是 batch 內唯一 net-new source（D2+D-hygiene 已在 Linux main+binary）；9 invariant + 5-gate 不受影響（C4 收緊非放鬆）。⚠️ 2 deploy-後驗：拓撲 ff/rebase 上 main + Linux 跨平台同 3622/0。
5. **conditions** — E2 C1 ✅DONE / **C2 singleton 登記 OPEN（merge 前）** / C3 NOTED / **C4 Sprint3 ticket OPEN（merge 前）** / C5 deploy-gated / BB G-1 advisory / BB FU-2 Sprint3。

**BLOCK 條件（無，但 merge 前必清 2）**：
1. **C2** — 在 `docs/architecture/singleton-registry.md` 登記 `SHARED_WATCHER` + `FAILSAFE_FEED_SENDERS`（owner: E1 / PA；CLAUDE §九 merge 前要求）。
2. **C4** — TODO 開 `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` ticket（owner: PM；spec §5.3 防半空 wire 長期擱置）。

**deploy 後驗**（E2 C5 / 拓撲）：ff/rebase C4 上 main → `restart_all --rebuild --keep-auth` → `ssh trade-core cargo test -p openclaw_engine --lib` 同 3622/0 → health-freeze 3 條 `[48]/[74]/[56]` 零 regression baseline。

---

## §7 — 報告路徑 + cross-ref

- 本報告：`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-29--c4_wire_acceptance.md`
- spec：`srv/docs/execution_plan/specs/2026-05-29--packet-c-c4-pipeline-wire-spec.md`
- BB：`srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-29--c4_set_trading_stop_trust.md`
- E2 review（C4 entry）：`srv/docs/CCAgentWorkSpace/E2/memory.md`（2026-05-29 APPROVE-WITH-CONDITIONS C1-C5）
- E4（上游 module，非 C4 wire）：`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-28--e4_packet_c_m11_full_regression.md`
- 核心 source（worktree wt-c4）：`event_consumer/handlers/risk.rs`（handle_notification_failsafe_escalate）/ `tick_pipeline/mod.rs`（PipelineCommand::NotificationFailsafeEscalate）/ `loop_handlers.rs`（async 攔截）/ `notification_failsafe/providers/single_watcher.rs`（timer_expired_and_claim + FAILSAFE_FEED_SENDERS）/ `tasks.rs`（spawn_notification_failsafe_watcher）/ `main_boot_tasks.rs`（wire 點）/ `event_consumer/tests/c4_failsafe_wire_tests.rs`（3 wire test）
- memory：`feedback_no_dead_params`（半 wire 允許明標）/ `project_2026_05_02_p0_sqlx_hash_drift`（cargo test ≠ runtime）/ `feedback_v_migration_pg_dry_run`（0 新 migration 免）/ LIVE-AUTH-WATCHER（live slot 不 stale）

---

**QA E2E ACCEPTANCE DONE: ACCEPT-WITH-CONDITIONS · report path: srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-29--c4_wire_acceptance.md**
