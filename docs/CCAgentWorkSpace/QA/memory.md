# QA Memory — 工作記憶

## Memory Usage Contract (2026-05-16)

- 本文件保存歷史教訓與角色偏好，不是 active state、TODO 或 runtime ledger。
- 若舊條目與 `TODO.md`、`README.md`、`CLAUDE.md`、`.codex/MEMORY.md`、`docs/agents/context-loading.md`、代碼或 runtime 證據衝突，信任較新的有證據來源並顯式說明衝突。
- 不要靜默刪除舊條目；只追加可復用的 durable lesson。長報告放 `workspace/reports/`，active 進度放 `TODO.md`。

## 項目上下文（2026-03-31）

- 當前 Wave：Wave 4 完成，Wave 5 規劃中
- 測試基準：2555 passed
- 系統模式：demo_only

## 工作記憶

（首次啟動，記憶從這次任務開始積累）

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| — | — | — |

## 審計發現（2026-04-24）

### Healthcheck 框架狀況
- **12 個檢查已全部實現** — close_fills / label_backfill / exit_features / phys_lock / micro_profit / trailing_stop / edge_estimates / model_registry / intents / bb_breakout / shadow_exit / counterfactual_clean_window
- **5 個缺陷待修**（優先級 A 2 週內）：
  1. label_backfill_context_linkage JOIN ratio
  2. phys_lock net 邊際效果驗證
  3. clean_window progress 百分比指示
  4. edge_estimates.json 結構完整性
  5. leader_election flock age
- **被動等待 TODO 必附 healthcheck 規則已加** — CLAUDE.md §七新規則 2026-04-23

### Regression Risk Top 3
1. **Python sweep leak-free vs Rust parity** — Phase 2 Phase 需 unit test 驗證
2. **INFRA-PREBUILD dormant 激活順序** — TOML flip vs uvicorn reload 無自動檢查
3. **Healthcheck 依賴順序** — [1] FAIL 時後續無意義但仍 skip-warn

### 「已完成」項驗收狀態
- **P0-13/14/15** — code PASS 但 P0-14 grand_mean 仍負，cost_gate bind 延遲到 P0-3
- **EDGE-DIAG-1 Phase 1/2/4** — Python sweep + counterfactual 完成，Phase 3 被動等待 clean n≥200 (ETA ~2026-05-01)
- **FIX-26-DEADLOCK-1** — Rust bug 已修，待 `--rebuild` 部署；[12] healthcheck 已加

### 最關鍵發現
1. **Healthcheck 反而隱瞞根本問題** — code 通過 ≠ 功能驗收。需 7d 灰度驗邊際效果
2. **軟 coupling 風險最高** — Python↔Rust parity / TOML sync / DAG 順序

| 報告 | 日期 | 關鍵發現 |
|---|---|---|
| 2026-04-24 QA 審計 | 2026-04-24 | 12 healthcheck 框架完整，5 缺陷待修；regression risk 聚焦軟 coupling |
| P1-11 多角 audit | 2026-04-24 | F3 leak-free Donchian 後消失（measurement bias）；FIX-26-DEADLOCK-1 確認；engine lib 1980 |
| EDGE-DIAG-1 報告 | 2026-04-24 | Phase 1/2/4 完成；clean window n~74 目標 200；counterfactual 顯示 phys_lock 可救但 edge 根本負 |
| 2026-04-26 Wave 3 E2E acceptance | 2026-04-26 | PASS — 5 大功能（G2-06 disable / EDGE-P1b / EDGE-P2-flip / G2-03 schema / IPC ms→s）全 runtime verify 通過；17/18 healthcheck PASS（[11] 75% pre-existing P013，[16] rebuild 後 PASS）；HMAC fix runtime log 確認；StrategyOverride symbol 在 binary；bb_breakout 24h 0 intents；Wave 3 派發 100% PASS to next Phase |
| 2026-05-10 W-C MAG-082 Stage 2 sign-off | 2026-05-10 | **CONDITIONAL_PASS** — 51h W-C 窗口 2555 objects 174 complete chains（97 demo + 77 live_demo 5 types 全平衡）；[55] direct run PASS；env 100% match auth file；replay substitution=0；boundary 全守。**2 caveat surface**：(1) `agent.decision_state_changes` 0 row all-time（producer code 存在 `agent_spine_writer.rs:217-260` + `store.rs:105`，但 0 caller 呼 `put_state_transition`，是 P1 wiring gap）；(2) 174/174 ExecutionReport.payload `filled_qty=0.0` + `liquidity_role='unknown'`（real fills 在 `trading.fills` 86 rows 但沒 propagate 到 Agent Spine ExecutionReport）。`[55]` `bad_report_quality=0` 只查 keyspace 不查 value-realism 是 healthcheck 盲點。Lease_id 100% `'bypass'` 是 by-design 不 caveat。W-D 可派但 MAG-083 audit pack 必明文標 caveat 1+2；建議開 P0-AGENT-2/3 FUP P1 ticket。報告：`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-10--w_c_signoff_audit.md` |

## 教訓（2026-05-10 W-C audit 衍生）

1. **健康檢查的「keyspace 通過」≠「value-realism 通過」** — `[55]` `bad_report_quality=0` 給人 false confidence；payload 4 個 key 都存在但 value 全是 `0` / `'unknown'`，依然 PASS。QA 在類似 sign-off 必須**抽 5-10 個樣本實際看 value**，不能只信 aggregate row count。
2. **Producer code 存在 ≠ producer 真的在跑** — `agent_spine_writer.rs` flush_state_transitions 完整存在，store.rs put_state_transition 完整 impl，但 0 caller。grep producer wire-up 必須**找實際 caller**（`grep 'put_state_transition('` 而非 `grep 'put_state_transition'`），否則會把 dead-code 當 active-code 過。
3. **Auth file 字面 scope vs design intent 區分** — 2026-05-08 auth file 只承諾「lineage 寫入」不承諾「real fill 寫入 payload」，所以 caveat 2 在字面 scope 內 PASS 但偏離 MAG-082 「evidence reconstruction」原意；CONDITIONAL_PASS 比 PASS / FAIL 都準確。
4. **bypass lease_id 是 evidence-mode by-design，不是 bug** — 174/174 plans `lease_id='bypass'` 完全符合 auth file「Record router-gate bypass / lease ids」描述。後續 Stage 3 promotion 不能 inherit `'bypass'` 當真 lease（建議文檔化）。
5. **`learning.lease_transitions` 是真正的 lease lifecycle SoT** — 24h 62,600 rows 高活躍度；`agent.decision_state_changes` 0 row 不代表 lease 沒在跑，代表 lease 沒被同步到 Agent Spine。兩個表的角色要在 MAG-083 reviewer brief 寫清楚，否則會誤判 SM-02 R-04 retrofit 失敗。
6. **跨 ssh 不能套 ssh** — `ssh trade-core "ssh trade-core ..."` permission denied；單層 ssh 才走 publickey forwarding。
| 2026-05-04 REF-20 Sprint A R3 smoke E2E | 2026-05-04 | **BLOCK** — R3 deploy commit `66b650ea` 含 P0 FastAPI signature bug：`from __future__ import annotations` + lazy module import + module-level re-bind 三者組合，FastAPI signature inspection 把 `body: ReplayExperimentRegisterRequest` 視作 Query parameter（不是 BaseModel body）。`/api/v1/replay/experiments/register` + `/api/v1/replay/run` 兩 routes 100% 422 missing body；hermetic test 也 fail；4 個 Sprint A acceptance SQL count 全 = 0；無 trading.fills leak（vacuous truth — register 沒進到 mutation 點）。push back PM Option A/B/C；Sprint A R3 不可結案 |
| 2026-05-04 REF-20 Sprint A R3 smoke E2E **round 2 (post-hotfix)** | 2026-05-04 | **STILL BLOCK** — hotfix `cad8ed84` 移除 `from __future__ import annotations` **runtime 確認有效**（/openapi.json 200 vs round 1 500，register 改回 503 reason=`engine_binary_sha_not_provisioned` vs round 1 422 body missing；45 hermetic test pass）。但 P0 BLOCKER 降級為 P2-A（`OPENCLAW_ENGINE_BINARY_SHA` env 仍未注入 API process — restart_all.sh 沒 export）+ P2-B（`/tmp/openclaw/replay_fixtures/btc_1m_smoke.json` 不存在；可 reuse `rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json`）。**新發現 P0-INFRA**：Linux 工作樹有 hotfix uncommitted edit，但 origin/main 已 commit `cad8ed84`，`git status` dirty + behind origin/main 違反 §七 commit 即 push 規則。4 表 acceptance SQL 仍 0/0/0/0。push back PM 走 §八 強制鏈派發 R3 round 3 fix（restart_all 加 ENGINE_BINARY_SHA + REPLAY_FIXTURE_URI export + git working tree clean）|
| 2026-05-04 REF-20 Sprint A R3 smoke E2E **round 3 (post-`e9d547c0`)** | 2026-05-04 | **STILL BLOCK** — round 4 infra fix 真實落地（API process env 含 `OPENCLAW_ENGINE_BINARY_SHA=38c72877...`，commit `e9d547c0`/`2ae93992`；Linux working tree clean = `e9d547c0`），4 表 acceptance progression：experiments=1 (E1 round 4 row) + run_state=1 (R3 round 5 spawn 寫 status='failed') / report_artifacts=0 + simulated_fills=0。**新揭 P0-NEW root cause**：`route_helpers.build_default_manifest_payload` 寫 placeholder signature manifest，但 `replay_runner` Sprint 1 Track B (commit `edf33c0`) 已將 sibling key.hex 缺 fail-open 改為 **fail-closed**（line 548-557 `manifest_signer_key_missing`）。Sprint A R3 (`66b650ea`) 沒 ship 配套 key.hex provisioning → 必死。手動跑 replay_runner 同 manifest 取得 stderr 證實。**新揭 P0-NEW-INFRA**：`subprocess.Popen stderr=subprocess.DEVNULL` 吞所有 subprocess root cause。**Round 6 必補**：route_helpers 寫 sibling key.hex (dev fixture key `aabbccddeeff...`) + 用真實 HMAC sign manifest + stderr PIPE + 配套 hermetic test for sign+verify cycle。push back PM @八 強制鏈派 R3 round 6（不走 P0 快速通道；計劃中 deploy infra fix）。新建議 PM Sprint A close gate：hermetic + R3 smoke E2E full cycle + Wave 9 safety + FK lineage valid 三層全綠。FK lineage 已 valid（run_state.manifest_id == experiments.experiment_id）。No trading.fills leak（trivially PASS）|
| 2026-05-04 REF-20 Sprint A R3 smoke E2E **round 5 (post-`3a425447`)** | 2026-05-05 01:43 | **STILL BLOCK** — Round 8 hotfix `3a425447` 部署 100% 配套（3 env injected + key.hex provisioned + git tree clean Mac=Linux=origin），subprocess **真實 status=completed**（10 events 處理 + 1 fill emitted + net_pnl=+630 + replay_report.json + replay_runner.stderr 「completed」）但 route 仍 **503 reason `replay_runner_spawn_failed`**。**新揭 P0-NEW-2 ROOT CAUSE**：route_helpers.py:639-650 「pathological clean-exit branch」把 `replay_runner` 在 1.5s poll grace 內 clean exit 0 視為失敗（return `spawn_died_early:exit=0`），下游 replay_routes.py:657-680 把 `spawn_died_early:` 全部映射到 503，**不區分 exit=0 success vs exit=N failure**。R6-T4 hermetic test 明確接受 exit=0（line 206 `assert err == "spawn_died_early:exit=0"`）但只直接測 `spawn_replay_runner` callable，沒測 route handler downstream。4 表 acceptance：experiments=3 + run_state=3 (status=failed 純 route 誤標) + report_artifacts=0 + simulated_fills=0（finalize 因 status=failed 拒接 409）。Wave 9 safety GREEN（trading.fills 0 leak / governance_audit 0 critical / FK lineage 3/3 valid）。**Round 9 必補單一 P0**：選項 A — replay_routes.py:657-680 從 503 list 移除 `spawn_died_early:exit=0` + 新增 elif 走 finalize-from-disk-report path。預估 30-50 LOC + 1 hermetic route E2E test。push back PM 不走 P0 快速通道，走 §八 強制工作鏈。Sprint A close gate v3 加 (D) Route /run E2E acceptance test 必過 |

## Wave 3 集成驗收教訓（2026-04-26）

### 真機 ssh 驗證重要性
- PA「mod.rs 1262 行」實測為 457 行 — sub-agent 報告數字 stale 或誤指模組，QA 不獨立 ssh 驗就會誤採。
- bb_breakout disable 不在 risk_config_*.toml 而在 strategy_params_*.toml — 第一次猜路徑錯，實際 grep 後找到正確位置。
- engine.log 路徑為 `/tmp/openclaw/engine.log`（不是 systemd journal 也不是 srv/log_files/），需 `readlink /proc/<pid>/fd/{1,2}` 才知道。
- DB connection string 在 engine 環境 `/proc/<pid>/environ` 變數內，QA 可讀；但 `OPENCLAW_IPC_SECRET` 同源讀取被沙盒擋下（合理 — 抓秘鑰超出 read-only QA 範圍）。

### Schema-only staging 的驗證手法
- G2-03 「0 production callers」要從 source code grep（grep `_with_override` 排除 test_ + 排除 batch_insert.rs 既有助手）+ binary symbol（`strings binary | grep StrategyOverride...`）雙重佐證。
- `effective_sl_max_pct` / `effective_tp_max_pct` fn 在 risk_checks.rs L50/L70 已 production wired（caller 在 L287/L288），**並非 PM 預期的「未綁定不算」**。schema staging 的精準語意是「TOML side `[per_strategy.<name>]` 沒填具體值 → fn 拿 Default 走全局 limits」，而不是「fn 不被呼叫」。

### Runtime 反 silent-dead 三角檢
- 同一個「disable」結論需 3 處互相佐證：(a) TOML active=false (b) engine log 0 mention (c) DB intents 0 row。三個都對才確定「disable 真生效」，缺一就可能是 silent-dead 假象。

### 工具 dry-run 的 fail-closed 設計
- EDGE-P2-flip dry-run 在裸 shell 下 c/d 「FAIL」是設計正確 — 沒 `OPENCLAW_IPC_SECRET` 就 refuse，並把如何 source 的 hint 印出。Operator wrapper L113-115 自動載入。QA 不能讀環境秘鑰時，該用 wrapper script 內嵌邏輯做 source-level 驗證即可。

### Rebuild 對 healthcheck [16] 的修復
- `strategist_cycle_fresh` FAIL 在 pre-rebuild 是真問題；rebuild 22 分鐘後實測已 PASS（with "fresh boot, by design" message）。PM gap 5 預測正確。

## 2026-05-21 LG-1 / LG-2 7d closure + Phase 2a T+72h verify 教訓

| 報告 | 日期 | 關鍵發現 |
|---|---|---|
| 2026-05-21 LG-1/LG-2 7d closure + Phase 2a T+72h | 2026-05-21 | LG-1 PASS WITH 1 KNOWN GAP（H0 production wired 18M+ tick verified, P1-LG1T3-RMW-WIRE hot-reload gap still open, NEW P1-LG1-DEMO-SLA-VIOLATION max_latency_us=2454μs > 1ms SLA）；LG-2 PASS WITH 1 CAVEAT（startup assertion fire confirmed, but production tick path 0 caller for fee_source() is BY-DESIGN per spec §2.4 — LG-3 supervised live 須 IMPL tick-time pricing-source consumer）；Phase 2a T+72h HEALTHY VELOCITY (28 rows, 0.39/h, 14d projection ~140) BUT AC-1/AC-2/AC-4 projection FAIL (maker_fill 35.71% << 60% gate)，AC-20 secondary WARN projection；engine STOPPED at 09:58 UTC 須 PM restart 或標 deliberate pause。報告：`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-21--lg1_lg2_7d_closure_phase2a_t72h_verify.md` |

### 1. Engine logs 是 binary blob — 不可 strings 撈 plain-text status_report
- `/tmp/openclaw/engine_logs/engine-*.log` 是 `file` 報 "data" 不是 text；`strings` 撈不到舊 `status_report` h0_checks 累積數值
- 只有 current `/tmp/openclaw/engine.log` (5h window with hourly rotation `.1.gz/.2.gz/.3.gz`) 是 plain text
- **QA verify limitation**：10d cumulative `h0_blocked` count 不可獲；必須依賴 `pipeline_snapshot_*.json` snapshot writer
- **建議 PM**：若這對 fail-closed semantic verify 是 critical，open ticket 改 engine log rotate format plain text 或加 sidecar JSON metrics writer

### 2. H0 production caller verify 必看 source code + pipeline_snapshot, 不只看 engine.log
- engine.log 內 `h0_blocked` 出現在 `event_consumer::status_report` 每 30s 一行；要算累積須 snapshot JSON file (`/tmp/openclaw/pipeline_snapshot_{demo,live,paper}.json` 含 `h0_gate_stats` block)
- 真 production caller verify = grep `step_0_5_h0_gate.rs` confirm `h0_gate.check()` 在 production path + status_report 顯示累積 `h0_checks` 18M+

### 3. Fail-closed semantic「真實 fire 過」是高要求
- LG-1 7d observation 期 `h0_blocked=0, shadow_would_block=0` — **fail-closed 從未實際 reject 任何 tick**
- semantic correctness 靠 LG1-T1 unit test 5 (`test_h0_shadow_to_hardblock_race_safe`) PASS 證明，runtime 未被測試過
- 這不等於 wiring failure — H0 真的有跑 (18M+ check)，但 H0 沒 trigger（freshness / health / eligibility / envelope / cooldown 五門都 0 violation）
- QA verdict 用「PASS WITH 1 KNOWN GAP」更精準

### 4. SLA verify 不要只看 average 也要看 max
- LG-1 demo `max_latency_us=2454` (2.5ms) > 1ms SLA — single tick outlier 在 18M sample 內 confirmed
- Live `max_latency_us=19μs` 完美
- 找 P99 / max latency 才是 SLA verify 重點；average 0us 是 micros 解析度限制

### 5. By-design 0-caller vs unwired 0-caller 必須分清楚
- LG-2 `fee_source()` 在 tick_pipeline / strategies = 0 caller，**但這是 spec §2.4 by-design**（assertion + IPC contract, not tick-time consumer）
- 不能誤標「LG-2 unwired」；要正確標「LG-2 spec scope 是 startup + IPC；future LG-3 supervised live 要 wire tick-time consumer」
- QA verdict 「PASS WITH 1 CAVEAT」+ caveat 明文寫進 P0 DONE annotation

### 6. Phase observation window verdict 看 projection 不只看當前
- Phase 2a T+72h sample velocity 健康 (0.39 rows/h) 但 AC-1 (60% maker fill gate) projection FAIL — 因為當前 35.71% Wilson lower 18-22%，14d sample 增到 ~140 也很難 swing to 60%
- AC-20 (secondary) 計算 projection：16 bucket × (336h/72h) extrapolated covers ~22 buckets（可能 PASS 18 gate）但 per-hour n ≥3 大多會 fail
- QA 該主動 surface PM **verdict 視窗前** decision 路徑：(a) calibration round 2 / (b) accept regime baseline + spec amend / (c) Phase 2b LiveDemo recalibrate

### 7. PG audit log 不是所有 wiring 都寫
- LG-1 H0 BLOCKED 用 `tracing::warn!` → engine.log not PG (by-design)
- LG-2 live_spawn_audit 用 `tracing::info!` → engine.log not PG (by-design per E2 MEDIUM-4)
- 查 `learning.governance_audit_log` 對 H0/LG2 沒結果是正常 — 不能誤判「LG-1/2 wiring 完全沒 log」

## Round 2 hotfix retry 教訓（2026-05-04）

### git working tree dirty + uncommitted vs origin/main 不一致 = false-PASS 風險
- PM 宣稱「Linux deploy verified」「HEAD `cad8ed84`」，但實際 Linux working tree 在 `66b650ea` + 有 uncommitted edit（hotfix 內容等同 `cad8ed84` 但沒 commit）。
- 直覺驗法是 `git rev-parse HEAD`，但若不 also 跑 `git status` 會被「working tree 跑得對」誤導以為 git tracking 也對。
- QA 接手三連必補：`git rev-parse HEAD` + `git status --porcelain` + `git rev-parse origin/main` 三角比對才可信。

### Hotfix runtime 驗證的 3 條最短信號
- /openapi.json 從 HTTP 500（PydanticUserError）→ HTTP 200 = signature inspection 已修
- register 從 HTTP 422 (`loc=["query","body"]`) → HTTP 503（next blocker reason）= body 不再被誤判 Query
- hermetic pytest `tests/test_replay_*` PASS = code-level 邏輯也對

三條同時滿足 = hotfix 確認有效，可往下個 BLOCKER 推進。

### "下個 BLOCKER" 不該倒退到 round 1 verdict
- 雖然 4 表 acceptance SQL 仍 0/0/0/0（仍 FAIL），但 BLOCKER root cause 從 P0（routes signature bug）降到 P2（env + fixture），這是真實進展。
- QA round 2 verdict 應是 "STILL BLOCK 但 progression 真實" 不是 "和 round 1 一樣 BLOCK"。

### Plan 守則 push back 而非 self-patch
- Plan 明文「**這個 fix 上去前先 push back 給 PM**，不要自己 patch restart_all.sh」+「**fixture 不存在時先停下來告訴 PM**」。
- 即使我知道修法（`export OPENCLAW_ENGINE_BINARY_SHA=$(sha256sum ...)`），也不執行；engine SHA 已算好附在 §15.5 給 PM 參考。
- 違反 = 越權 + 違 §八 強制工作鏈（QA 不寫業務代碼）。

### CC 不執行 git stash/pull 的限制
- Linux working tree dirty 解決需要 `git stash drop && git pull --ff-only`，但 CLAUDE.md §七「CC 絕不執行 pull/merge/checkout/reset/rebase」。
- QA 把該動作寫進 §15.6 給 operator 手動 issue，不嘗試自動化。

## Round 3 final smoke 教訓（2026-05-04）

### 「register 200 OK」≠「整條 replay flow 跑通」
- E1 round 4 sign-off 只驗 register 沒驗 /run，誤導 PM 以為 R3 已 unblock；R3 round 5 揭示 /run 仍會 503 spawn_died_early
- **QA SOP 強化**：任何 endpoint 「200 OK」必驗 downstream effect — 對 /run = subprocess truly executed + report_artifact written + simulated_fills written；不只看 200 OK return

### `subprocess.Popen stderr=subprocess.DEVNULL` 是 silent-dead 反模式
- route_helpers.py:549 `stderr=subprocess.DEVNULL` 是 fail-closed 設計但 root cause 永久看不到
- R3 round 5 必 ssh 到 Linux **手動跑同 manifest 同 argv** 才看到 `manifest_signer_key_missing`
- 任何 spawn-then-poll 設計 stderr 必落到 file（subprocess.PIPE + read in poll grace + write to `<output_dir>/replay_runner.stderr`）

### Sprint integration drift 的偵測手法 — 跨 commit chain audit
- Sprint 1 Track A pre-`edf33c0`：placeholder fall-through 預期
- Sprint 1 Track B `edf33c0`：fail-closed verifier，**修了 fail-open 漏洞但破了 placeholder 預期行為**
- Sprint A R3 `66b650ea`：寫 finalize/writer/spawn flow 但沒注意到 Track B 的 fail-closed 影響
- **Lesson**：跨 commit / 跨 wave 的 design contract 改動必審 downstream callsite 是否仍 hold contract

### Schema verify SQL 必先驗 column name 再 cluster
- `trading.fills` 用 `ts` 不是 `created_at`；`learning.governance_audit_log` 用 `ts` 不是 `created_at` + 沒 `severity` 列
- 寫 acceptance SQL 必先 `\d <table>` 或 `SELECT column_name FROM information_schema.columns WHERE table_schema='X' AND table_name='Y'`
- Plan 給的 SQL 模板不一定對齊實際 schema（plan 寫 `severity IN ('high','critical')` 但 governance_audit_log 沒此欄）

### 4-table acceptance 部分 PASS 可信度評估
- experiments + run_state PASS = register + spawn 路徑通
- report_artifacts + simulated_fills FAIL = subprocess execute 鏈未通
- 不能因「2/4 PASS」就 partial close — 整條 evidence chain 必全通才有意義
- 但 partial PASS 確實證明 round 4 infra fix（`e9d547c0`）是真進展，不是 round 1 全 0/0/0/0 的 vacuous truth

### Manual subprocess reproduce 是 silent-dead 唯一武器
- API log 只寫 "spawn_died_early:exit=1 (likely CLI schema mismatch / manifest fail-closed)" — 「likely」是因為 API 不知道 stderr
- ssh trade-core 直接跑 `<runner_bin> --manifest <path> --output-dir <dir>` 立即拿到真實 Error: 文字
- **任何 silent-dead subprocess 必先 manual reproduce 才談 root cause**

## 教訓（2026-05-04 R3 round 4 — 「pre-spawn ValueError 不會留 stderr 證據」）

### Round 4 核心新教訓 — fail-closed 設計鏈鏈相扣，配套缺一即死

R6+R7 commit `f51f4e2e` 設計了 3 層 fail-closed 鏈：
1. **R6-T1** — `_resolve_manifest_signing_key()` 3-tier (env override → secrets_dir → fail-closed ValueError)
2. **R6-T2** — subprocess.Popen stderr → disk file (post-spawn 診斷武器)
3. **R6-T3a** — `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env 注入 restart_all.sh

deploy 配套：
- T3a 是 `restart_all.sh` 改動 (1 export line)
- T1 + T2 是純 Python code 改動 (沒改 restart_all.sh)
- **T1 的「step 2 secrets_dir lookup」依賴 `OPENCLAW_SECRETS_DIR` env**

**漏的是**：T1 沒有把對應 deploy infra（secrets_dir env + signing_key 文件 provisioning）一起 ship。`restart_all.sh` R6-T3a diff 只 inject FIXTURE_DEFAULT，沒 SECRETS_DIR。

結果：runtime 進到 step 3 fail-closed → 但因為**ValueError 發生在 subprocess.Popen 之前**，T2 stderr disk file 從未開檔。Operator 唯一證據是 `tail /tmp/openclaw/api.log` 找一行 `OPENCLAW_SECRETS_DIR not set`。

**反模式：QA 看 deploy commit 不能只看「Python code fix 對不對」，必驗「配套 infra 在 runtime 真的 inject 了」**：

```bash
# 必跑三件套（R6+R7 應 inject 的所有 env）
ssh trade-core 'API_PID=$(pgrep -f "uvicorn app.main:app" | head -1); \
  for v in OPENCLAW_ENGINE_BINARY_SHA OPENCLAW_REPLAY_FIXTURE_DEFAULT OPENCLAW_SECRETS_DIR; do \
    grep -aE "^$v=" /proc/$API_PID/environ | head -1 || echo "$v MISSING"; \
  done'
```

如果出現 1 個 MISSING → deploy 半完成 → 重跑 `restart_all.sh` 也修不了（因為 restart_all.sh 沒 ship export 該 env）。

### Pre-spawn ValueError 不會觸發 stderr disk file

R6-T2 stderr disk fix 只在 subprocess.Popen invoke 後生效。pre-spawn ValueError（`manifest_signing_key_unavailable`）路徑下：
- output_dir 已 mkdir 但**空 directory**
- 0 file written（no manifest_fixture.json / no key.hex / no fixture.json / no replay_runner.stderr）
- caller 直接 raise → 包成 `manifest_fixture_write_failed:ValueError` pg_err → 503 reason `replay_runner_spawn_failed`

**改善建議**（也是新教訓）：`route_helpers.py::write_manifest_fixture` catch ValueError 後 `log.error()` print full traceback。當前 caller 寫 503 但 swallow exception traceback 到 api.log 只剩 step 2 的「OPENCLAW_SECRETS_DIR not set」print 一行 — 不夠完整。

### PM plan 開頭斷言 vs runtime 實況的 4 round 差距

每一 round 都揭露 PM 開頭聲稱「fix 已 land」與 runtime 配套不一致：

| Round | PM 斷言 | runtime 真實狀態 |
|---|---|---|
| 1 | 「R3 deploy 完成 (`66b650ea`)」 | from `__future__` annotations 把 body 變成 query param |
| 2 | 「hotfix `cad8ed84` resolved」 | OPENCLAW_ENGINE_BINARY_SHA env not provisioned |
| 3 | 「`e9d547c0` + `2ae93992` resolved」 | placeholder signature collision with Sprint 1 Track B fail-closed verifier |
| 4 | 「core fix 已 land — 4-layer blocker fix」 | OPENCLAW_SECRETS_DIR + replay_signing_key 未 provisioning |

**Pattern**：每一 round 修一層 P0，但揭露下一層配套缺 P0。**4 layer trajectory: 2/2 → 2/2 → 1/1 → 2/2**（experiments + run_state 寫鏈通了，但 report_artifacts + simulated_fills 鏈仍 untested）。

QA 教訓：**「PM plan 寫『fix land』≠ runtime 真實 deploy 完成」**。每次 round 必獨立驗 deploy 配套（git status / process env / file existence）。

### deploy half-step 反模式累積

5 round 累積總結（包括這次）：
- ✅ Python code 層 fix：4/4 都做對（cad8ed84 / e9d547c0 / R6-T1 / R6-T2 / R6-T3a）
- ❌ Deploy infra 層配套：3/4 漏（hotfix 沒重啟 / e9d547c0 沒同步 ENGINE_BINARY_SHA env / round 4 沒同步 SECRETS_DIR + key file）

**根因**：commit author 看「pytest 全 PASS（hermetic）」就以為 deploy 安全。pytest 在 mocked env 下跑，runtime infra 與 commit chain 解耦。

**Sprint A close gate 補強建議**（governance update）：
- (A) hermetic pytest gate（既有）
- (B) Linux runtime smoke (R6-T4 提供 `OPENCLAW_REPLAY_E2E_SMOKE=1` opt-in 但要求每次 deploy 必跑)
- (C) `/proc/$API_PID/environ` ENV 三件套 grep（必跑，0 missing 才 close）

## 教訓（2026-05-20 Layer A halt TTL pre-deploy QA — durable lessons）

### 12.6 Mac uncommitted IMPL → Linux byte-equiv verify 必延後到 deploy gate

當 IMPL 在 Mac dirty tree（未 push），Mac aarch64 cargo test PASS 但 Linux x86-64 沒 Layer A source；E4 §3.2 標 deferred 但 QA 必須升至 deploy gate（C-1 BLOCKER）。**SOP**：QA report 必含 Step 4 post-deploy verify 跑 `ssh trade-core cargo test -p openclaw_engine --release` 預期 cross-arch byte-equiv count 一致；若 +/- 偏離 > 2 個 test → return E1 RCA。本次 Mac 3264 vs Linux pre-Layer A 3219 = +45 預期（Round 1 34 + Round 2 9 + parser variant 1-2）。

### 12.7 V098 dry-run 副作用：DB 已 land 但 source code 未 push

E1 Round 1 §6.1 揭：V098 Linux PG dry-run `psql -f` 過程中已 apply 到 production DB（24-value CHECK 已 active）。但 V098 SQL file 仍在 Mac dirty tree 未 commit。**lessons**：
- 這是 healthy 的 audit-vs-action 分離（操作已完成 / lineage commit 跟 deploy 一起 push）
- 但若 Linux 重新 build env（fresh init）需 V098 re-apply — `IF NOT EXISTS` guard 保護冪等
- QA 必驗 `pg_get_constraintdef` 看 CHECK 是否真有 3 halt_session_*；不能依賴「sql 文件存在 = 已 deploy」

### 12.8 jsonschema validate roundtrip 必須測 sample line ts_iso 格式

halt_audit_schema.json 用 `^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{3}Z$` 強制 ms-precision；QA 第一次測 `'2026-05-19T20:00:00Z'`（無 .000Z）失敗，加 `.000Z` 後 PASS。Rust 端 halt_audit.rs 用 `chrono::SecondsFormat::Millis` 對齊，emit `2026-05-20T00:23:45.123Z`。**lessons**：jsonschema validate sample 不能隨手用簡化 ISO-8601；必先看 schema regex 把所有 conformance 嚴守，OR 看 Rust 端 emit format 精確 mirror。schema-vs-emitter mismatch 是 silent-skip 反模式。

### 12.9 24h passive watch 期間「halt 事件頻率低 → runtime EV lazy verify」是合理 pattern

A-2-EV / A-4-EV runtime evidence pending 是 acceptable。已通過 unit + integration + Linux PG empirical INSERT 三層驗證；runtime EV 是 over-fit observation，0 自然事件期間不阻 deploy；7d 仍 0 自然事件可選 synthetic inject。**這是 deploy 後 lazy verify 模式的合理 pattern**，不是 acceptance gap。QA 必明文寫進報告區分「unit/integration verified」與「runtime EV lazy verify」，避免 PM 誤判 acceptance 不全。

### 12.10 Cross-wave dirty tree scope check 必走 `git diff --stat HEAD -- <module-paths>`

不能僅看 `git status --porcelain`；必須加 `git diff --stat HEAD -- <module-paths>` 確認改動全部在預期 scope 內。W-AUDIT-7c precedent (2026-05-08) 顯示「Mac dirty tree pre-deploy 必清 scope」是 SOP。本次 28 modified + 13 untracked / 全 Layer A scope clean → 0 其他 wave leak。

### 12.11 commit subject + body 必含完整 fix lineage

E2 Round 2 APPROVE + E4 PASS + QA APPROVE-CONDITIONAL 之後，commit message 必 reference 5 個 report path（E1 R1+R2 / E2 R1+R2 / E4 / QA 本份）+ 6 fix 鏈（MUST-FIX 1-4 + E3 MEDIUM-1 + spec §6.3 replay）+ spec compliance。**QA SOP**：APPROVE-CONDITIONAL 報告必含「建議 commit subject + body」具體模板給 operator/PM 採納；不可只給 verdict 不給 commit guidance。

## 教訓（2026-05-05 R3 round 5 — 「subprocess 真實 status=completed 但 API 仍 503」）

### 第 6 layer 是 route handler 設計缺陷

5 round 累積：layer 1-5 全是 deploy infra（Python annotations / 3 env / HMAC key 配套）；round 5 揭示 layer 6 是 **route control flow design bug** — `replay_routes.py:657-680` 把 `spawn_died_early:exit=0` 與真死同等映射到 503。

**反模式**：`spawn_replay_runner` 對「subprocess 跑得太快」(rc=0 在 poll_grace 1.5s 內) 視為「pathological clean-exit branch」。code comment 明確寫「downstream wait/UPDATE assumes a live PID」並 return `(None, "spawn_died_early:exit=0")`。但下游 route 沒對 exit=0 做特例處理，全 503。

### Hermetic test 覆蓋率盲點：直接呼叫 callable vs 走 route handler

R6-T4 hermetic test (`test_replay_e2e_round6_smoke.py:206`) 明確接受 `spawn_died_early:exit=0`：
```python
# Allow exit=0 (fixture ran fully); reject any non-zero early death.
assert err == "spawn_died_early:exit=0", (...)
```

但該 test 直接呼叫 `spawn_replay_runner(...)`，**沒走 route handler**。production 路徑是 `POST /run → app/replay_routes.py → spawn_replay_runner → return → route handler decision`. Route handler 把 exit=0 也 503，hermetic 永遠看不到。

**QA 教訓 / Sprint A close gate v3**：必加 (D) **Route /run E2E acceptance test** — 必須測 register → /run → finalize → 4 表 row 全 > 0 整鏈，**禁** hermetic 直接呼叫底層 callable 跳過 route handler。

### API 503 不一定代表 subprocess 死

Round 5 必查證據：
1. `/tmp/openclaw/replay_artifacts/<run_id>/` 內所有 file（key.hex / manifest.json / replay_report.json / replay_runner.stderr）
2. `replay_runner.stderr` 內容（true source of truth — 寫了什麼）
3. `replay_report.json` 的 `result.status` 實際是 `completed` 還是 `aborted`
4. `api.log` 看 route 邏輯說了什麼（本 round 看到 `replay_runner exited 0 within poll grace` 是 route 自打臉）

**只看 HTTP code 503 = QA 偽 PASS 風險**：subprocess 成功 + report on disk + route 503 = control plane 與 data plane 分裂。

### subprocess 真實成功 + route 標 failed = 不一致 state

Round 5 後 DB 狀態：
- 3 row in `replay.experiments` (register 成功)
- 3 row in `replay.run_state` 標 `status=failed` + `subprocess_pid=NULL` + `completed_at=NOW()`
- 3 個對應的 artifact dir 在 disk 含真實成功 report
- `report_artifacts` + `simulated_fills` 0 row（finalize 從未 called）

**Operator 必跨 DB + disk 才能識別**：DB 看是「3 個 failed」；disk 看是「3 個成功 report」。沒有 reconciliation path。

### finalize from disk report 是 Sprint A 缺的最後 helper

當前架構下：
- /run 503 → run_state.status=failed
- POST /finalize 要求 status IN ('starting','running') → 拒接 409

沒有 recovery path 從 disk 讀 replay_report.json 補 INSERT report_artifacts + simulated_fills。Round 9 必加 helper：
- 選項 A：replay_routes.py 在 spawn_died_early:exit=0 路徑直接 inline call finalize-from-disk
- 選項 B：finalize endpoint 加 force_from_disk 模式（接受 status=failed 但有 disk report）

選項 A 較簡單，符合 Sprint A scope。

### Push back vs self-fix 邊界守則（再強化）

QA 知道修法（route_helpers.py:639-650 + replay_routes.py:657-680 改動），**禁止自己 patch**。Plan 守則明白：
- 不 commit
- 不寫業務代碼
- 4/4 不達 → 報告真實 root cause + push back PM
- 4/4 達 → PM 後續做 Sprint A close commit

QA 把 fix 建議寫進 §18.5 + §18.7 給 PM/PA/E1，但不執行。違反 = 越權。

## Round 6 FINAL acceptance 教訓（2026-05-05 02:05 UTC; commit `2531c011`）

### 4/4 acceptance PASS — Sprint A 達成

6-Layer blocker chain 全清：L1 from __future__ → L2 ENGINE_BINARY_SHA → L3 placeholder signature → L4 stderr DEVNULL → L5 signing key not provisioned → L6 exit=0 误判 failure。每一 round 修一層，round 6 終止。

**4 表 row count**: experiments=4 / run_state=4（首次出現 status=completed）/ report_artifacts=1（first ever）/ simulated_fills=1（first ever，evidence_source_tier=synthetic_replay）。

**Wave 9 safety GREEN**: 0 trading.fills leak / 0 critical replay audit / FK lineage 4/4 valid。

### Layer 6 fix `2531c011` 設計教訓

route_helpers.py:639-650 把 subprocess `exit=0 within poll grace` 從 failure 改回 success（return `(-1, None)` sentinel 而非 `(None, "spawn_died_early:exit=0")`）。replay_routes.py 接 `pid=-1` 標 status='running'，response envelope 加 `subprocess_completed_in_poll` flag。

**反模式被修**：「subprocess 跑得太快」(< 1.5s poll grace) 在 round 5 被誤歸為 pathological clean-exit branch，違反「subprocess 成功完成 = 成功」常識。Layer 6 fix 顯式區分 exit=0 (success sentinel) vs exit≠0 (true failure)。

### Layer 7 風險預警 NOT triggered

Round 5 曾預警 round 6 可能再被「/finalize 拒接 subprocess_pid IS NULL」「synthetic walker 0 fills」絆倒；實測 round 6 兩個風險都 GREEN：
- /finalize 接受 subprocess_pid=NULL（HTTP 200 + fills_inserted=1）
- synthetic walker 真的 emit 1 fill（events_processed=10, fills_emitted=1, net_pnl=+630）

### writer_errors 邊角警告（non-BLOCKER）

`writer_errors: ["strategy_name_missing_from_v049_manifest_jsonb"]` 出現是因為 smoke payload 把 `manifest_jsonb={"smoke":true}` 沒含 strategy/symbol 字段。simulated_fills.strategy_name fallback 到 `unknown_strategy`。**不影響 row count acceptance**（Plan §6.R3 不要求 strategy_name 正確）。Sprint B 改 register 自動 inject。

### Sprint A close gate v3 (D) 項驗證

加入 (D) Route /run E2E acceptance test 後 round 6 走完整路徑：register → /run → finalize → 4 表 row > 0。**不再走 hermetic 直接呼叫 spawn_replay_runner 跳過 route handler 路徑**。Plan V1 close gate 升級為 4 條 ABCD 全綠。

### REF-20 label 升級條件達成

從 `closed-with-known-gap (Sprint A in flight)` → `Sprint A R3 closed (4/4 real evidence)`。Sprint B (Wave 4-5 R4-R5) 啟動 0 BLOCKER。

| 報告 | 日期 | 關鍵發現 |
| 2026-05-04 REF-20 Sprint A R3 round 6 FINAL | 2026-05-05 02:05 | **PASS — Sprint A 達成**；6 layer blocker chain 100% 清；4 表 acceptance 4/4 GREEN（first-ever simulated_fills + report_artifacts）；Wave 9 safety GREEN（0 trading.fills leak / 0 critical audit / FK 4/4 valid）；Layer 7 預警 NOT triggered；唯一邊角警告 strategy_name_missing manifest_jsonb (non-BLOCKER, Sprint B 處理); push back PM 進行 close commit + Sprint B 派工 |
| 2026-05-25 W1-G AC-19 ALT bucket 14d monitor SOP | 2026-05-25 | **PASS (AC-S2-E-1 + AC-S2-E-4)** — SOP land 含 Wilson CI 95% inline SQL + cron wrapper spec + 3 級 verdict trigger (PASS≥30% / MARGINAL 20-30% / FAIL<20%) + spec §4.3 Option α (ATR-aware adaptive offset) / β (BB depth audit → demote ALT to live-only)；day 7 empirical re-verify: ALT 35/9/23 = 25.7%, Wilson lower **14.1%** << 30% gate → WARN trajectory；large_cap 6/4/1 = 66.7%；4 個 AC: E-1 SOP ✅ / E-2 pending E1 IMPL (3 helper + crontab paste) / E-3 pending 6/2 final verdict / E-4 ✅；caveat §5.2 demo-vs-mainnet drift 明示；只 15 ALT 有 close_maker_attempt (1 ALT symbol 0 attempts)；OPUSDT 重 sample (n=10) 拖低 ALT bucket。報告：`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--ac19_alt_bucket_14d_monitor_sop.md` |

## 教訓（2026-05-25 W1-G AC-19 ALT bucket SOP）

### 1. Wilson CI 95% lower bound 對小樣本 fail-rate gate 必要
- ALT n=35 / p_hat=0.257 → Wilson lower **14.1%**；naive 25.7% 看似 marginal，Wilson lower 揭示真實統計顯著程度離 30% gate 還很遠
- 對小 n 高方差 binomial，必用 Wilson 不用 normal approximation（z·sqrt(p(1-p)/n) 在 p→0/1 / n 小時 normal 會給出 < 0 lower）
- Wilson CI 95% formula: `(p_hat + z²/2n ± z·sqrt(p_hat(1-p_hat)/n + z²/4n²)) / (1 + z²/n)`；z=1.96 for two-sided 95%
- SQL 內須 `GREATEST(..., 0)` 防 floating point SQRT 負數 panic

### 2. SOP 只寫 SQL + cron line spec，不 IMPL helper script
- QA 邊界 = SOP doc author；E1 邊界 = IMPL（helper script + crontab edit）
- SOP 寫到 "spec only — not written by QA" 明示
- 過去 round 5 教訓 (route_helpers self-fix vs push back) 對齊 — 知道 IMPL 不執行 IMPL

### 3. 14d window expiry trigger 必 documented + clock 預設
- 2026-05-19 → 2026-06-02 14d clock；day 7 (今日) 是 baseline + start cron daily fire 後最快 day 8 開始才能進 jsonl
- final verdict 是 manual 觸發 by QA at 6/2，不應放 cron 自動 verdict（避免 silent verdict drift）
- cron wrapper script 可加 idempotent expiry check (day > 14 skip + log "window expired")

### 4. demo-vs-mainnet drift caveat 必明示
- ALT bucket 在 demo book depth 可能比 mainnet 更薄 (per BB Q1 prior + PA Phase 1b §4.4)
- 6/2 final verdict 即使 FAIL 也不能直接 extrapolate 到 mainnet 必 FAIL
- 必 §5.2 明寫 caveat + 6/2 verdict 必 reference 此 caveat

### 5. 對抗 SQL 必 ts >= 起點 AND ts <= 終點（明確 timestamptz UTC）
- 不要只寫 `ts > '2026-05-19 00:00:00'`（無 timezone literal 易導 server TZ 解析錯）
- 必 `'2026-05-19 00:00:00+00'::timestamptz` 強制 UTC（per 2026-05-11 W-C re-audit 教訓 #1 時區陷阱）
- 14d 終點 cap `ts <= '2026-06-02 00:00:00+00'::timestamptz` 必加，避免 cron 在 6/3+ 仍累積


## 2026-05-11 W-C MAG-082 Stage 2 RE-AUDIT — PASS

**Trigger**: 2026-05-10 1st audit CONDITIONAL_PASS（3 caveat）→ operator Option B 修 → PA/E1×3/E2×2/E5/E4 全 APPROVE → deploy ccf7a4bc → re-audit
**Deploy_ts (UTC)**: 2026-05-11T00:01:55+00:00
**Verdict**: **PASS** — W-C → WINDOW_PASS operator-ready；W-D MAG-083 可派
**Report**: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_c_reaudit_post_fix.md`

### Caveat 對齊（1st audit → re-audit）
- **Caveat 1** decision_state_changes 0 rows → **CLOSED**：post-deploy 82 rows / 24 last 5min / ~4.8 row/min
- **Caveat 2** ExecutionReport stub-only → **CLOSED**：6/6 entry-fill 100% real-fill ER propagation；UTC strict cutoff adversarial SQL missed_n=0；payload 真實 filled_qty/maker/avg_price/fees/fee_bps
- **Caveat 3** lease_id='bypass' → **DEFERRED**：by-design per 2026-05-08 auth，不在 fix scope，W-D reviewer brief 處理

### 關鍵教訓

1. **時區陷阱**：對抗 SQL 用 `+02::timestamptz` 等同 CEST = UTC-2，會把 deploy 前 1.5h fills 算進 post-deploy → missed_n 假性 18。**UTC strict `+00:00`** cutoff 後 entry=6 missed=0 100% PASS。Operator 給 deploy_ts 寫 UTC，QA SQL 必對齊 UTC。**未來 SOP**：任何 deploy-cutoff SQL 必用 `+00:00` 或 `'<ts>'::timestamptz at time zone 'utc'`，禁混 CEST/UTC。

2. **trading.fills 含 entry + risk_exit**：原 PA §4.3 對抗 SQL 沒區分 `oc_*` (entry) vs `oc_risk_*` (risk_exit)。risk_exit 走 StopManager 不走 spine emit_fill_completion_lineage（by-design），分子分母混算會誤判 fix 失敗。SQL 必加 `order_id LIKE 'oc_%' AND order_id NOT LIKE 'oc_risk_%'`。
   > **2026-05-20 v55 reframe（重要修正）**：本條教訓**僅適用 spine lineage propagation 驗證**（即 `agent.decision_state_changes` ↔ `trading.fills` 對接）。
   > 適用於 **close maker** 分析（Phase 1b activator AC-A 等場景）時，QC v55 critical reframe 揭露此 ID prefix 拆法是**結構性誤分類**：entry-close 與 risk-exit 走同一條 `execute_position_close()`；一次 attempt 內若 maker timeout → fallback 成 market exit 或 cancel grace expired → 強制走 risk-exit takeover，同筆 attempt 會出現 `oc_close_mf_fb_*` 與 `oc_risk_*` 兩種 order_id，**ID prefix 拆法會把同一 attempt 的兩段生命週期算成「entry path 0% maker / risk path 100% maker」誤導結論**。
   > 自 2026-05-20 起，**post-deploy close maker verification 改用 attempt × fallback matrix**（PM template `2026-05-18--pm_24h_post_deploy_verification_audit_packet.md` §3.1）：attempt 軸 = `maker_close_attempt` vs `sweep_taker`；fallback 軸 = `maker_filled` / `timeout_taker` / `postonly_reject_retry` / `cancel_grace_expired` / `risk_exit_takeover`。
   > backlog ticket：`P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX`（已 IMPL 2026-05-20）。

3. **[55] WARN ≠ FAIL**：分母 chains_with_real_fill_report=6/210=2.86% 是 transition 期，分母含 204 pre-deploy stub-only chains。24h steady-state rolling 後分母換新 chains 自動 ≥ 50% gate。WARN 接受為 transition characteristic，不是 fix failure。

4. **短窗 vs 24h 重等**：PA §4.4 論證 5 點全接受。caveat 修正是 deterministic wiring fix 而不是 statistical sampling fix；30min empirical 已證 missed_n=0 + cross-language byte-equal contract，比預期更快收斂；歷史 51h evidence 不消失。**短窗有效**節省 23-23.5h critical path。

5. **Cross-language byte-equal contract empirical 驗證**：Rust `DecisionEdgeType::ExecutedBy → "executed_by"` + `details = {"fill_completion": true}` 字面對齊 Python SQL `edge_type='executed_by' AND (details->>'fill_completion')::boolean IS TRUE`。實機驗證 6 命中 = 6 real ER = 6 entry fills 1:1:1。設計時若 enum→string serialization / JSON key snake_case 對不齊，整個 healthcheck 會 silent zero — empirical join 是唯一保護。

6. **W1 wave pre-existing breakage 不阻本 audit**：helper_scripts/db full pytest collection ImportError `check_panel_freshness` 是 W1 sub-task 3 wave WIP，E1/E2/E5/E4 全已 flag；isolation import workaround 合理；W-C unit test 14/14 PASS 不掩蓋此 breakage。**規律**：sibling wave pre-existing breakage 接受作為 LOW caveat 但不阻 deploy；E1/E2/E4 必 cross-flag。

### 為何能短窗收斂這麼快
- spine writer 2s flush interval；try_send 非阻塞
- 5 build transitions per chain × 7 chains/min × 2 mode = ~70 transitions/min build path
- 2 change transitions per fill × ~2 fills/min ~= 4 transitions/min change path
- emit_fill_completion_lineage 在 loop_exchange.rs fully_filled 區塊；24h ~86 fill 但 deploy+10min 已有 6 fill empirically 驗 propagation
- Cross-language byte-equal contract 是 deterministic，第一個 entry-fill 即可驗

### 治理 SOP 加固

- **deploy-cutoff SQL UTC mandatory**：任何 post-deploy verification SQL 用 `+00:00` 或 `at time zone 'utc'`，禁混 local timezone（CEST/EST/etc）。納入 PA spec template + QA audit template default。
- **entry vs risk_exit 分流必要**：trading.fills cross-join 必區分 `oc_*` 與 `oc_risk_*`；spine lineage 是 entry-path-only，stopmanager 走獨立 path（fix scope 之外）。**僅 spine lineage 場景**適用。
- **close maker 分析必用 attempt × fallback matrix（2026-05-20 v55 起）**：post-deploy `close_maker_attempt` AC verification 禁用 ID prefix 拆法；改用 `close_maker_attempt` boolean × `close_maker_fallback_reason` enum 兩軸切。範本 = PM template `2026-05-18--pm_24h_post_deploy_verification_audit_packet.md` §3.1，含 grid + bb_breakout 兩個範例。同一 attempt 的 fallback 後階段不可被當成「另一條 path」雙計。
- **[55] WARN vs FAIL 細分**：bad_report_value_quality=0 + state_changes ≥ N 是 fix correctness gate；chains_with_real_fill_report ratio 是 calibration / transition gate。前者強 fail-closed，後者接受 WARN transition。

---

## 2026-05-11 W-D MAG-083 QA Audit

**任務**：W-D MAG-083 final release audit（QA 視角，三角之 1/3）；PA + QC 平行 audit。
**Verdict**：**APPROVE WITH RESERVATIONS**
**Report**：`docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_d_mag083_qa_audit.md`

### 關鍵 finding

1. **時間軸初步誤判**：engine etime `ps -o etime` 顯示 `23:01` 我誤讀為 23h，實際為 23min（MM:SS）。後續用 `etimes`（秒）+ `lstart`（絕對時間）確認 engine 從 deploy+51s 起跑，audit 時間為 deploy+78min。SOP：**`ps -o etime` 後續必同步取 `etimes` 或 `lstart` 雙確認**，避免類似誤讀。

2. **Caveat 2 fix 有 emergent edge case（R-1 new finding）**：
   - deploy+10min adversarial：4/4 100% matched (re-audit baseline)
   - deploy+78min adversarial：30/31 matched (96.8%)；6 個 orphan real-fill ER（real ER 寫了但 trading.fills 沒對應 row）；1 個 missed
   - 6 個 orphan 集中在 deploy+72-73min 4-min burst window（03:13-03:14 UTC+2 = 01:13-01:14 UTC），symbol = grid_trading DOTUSDT/SUIUSDT/ARBUSDT/ETCUSDT × demo/live_demo
   - orphan ER `fill_id` 在 trading.fills 完全找不到（strip `bybit-` 後也沒有）；後續 DOTUSDT/ETCUSDT 真實 fill 用了**不同 fill_id**
   - 經 audit 期 5 分鐘後再查仍是 6+1，不是 lag = 是 stuck，但新累積仍 100% propagation
   - 可能成因：trading_writer dispatch race / 同 order Bybit 多 exec event / fully_filled 路徑邊緣 case；非系統性 wiring failure
   - **不阻 MAG-084**：fix correctness 邊界 case 不破，符合 PA 50% 觀察期 gate；reviewer brief 章節 2 升級

3. **Cross-wave Sprint N+1 D+0/D+1 source-land 60+ commit**：W-C sign-off `1ebdb9c9` 之後 W7-3/W6 V086/W1 V085/V087/V088/W2 cross_asset/IPC slot/W1 BB WS V092 都 source land；9 SQL migration V082-V092 applied；3 panel writer 活躍（V085=251 row / V087=996 row / V088=75 row）。但 **engine PID 1597560 自 deploy 後未重啟**（binary mtime 02:01:30 stable），所有 Rust source change 未進 runtime。

4. **W-AUDIT-9 canary_stage_log 0 row（dormant）**：Stage 0 binary fail-closed 不變式 hold；等 W6+W7 完成 ~D+3-4 cohort 啟動。W-C 修復不誤觸 stage 機制。

5. **Sign-off file PID typo（R-3）**：寫 `1596779` 實際 `1597560`，純 doc accuracy。建議 PM 在 MAG-084 commit 同次修正。

### Reviewer brief 從 4 章節擴 5 章節

| # | 章節 | 升級點 |
|---|---|---|
| 1 | Caveat 1+2 fix wiring verified | 無變 |
| 2 | **Real-fill propagation transition (升級)** | 加 burst window emergent edge case 描述；long-term ratio 96-100% range |
| 3 | Caveat 3 by-design | 無變 |
| 4 | Cross-language byte-equal | 無變 |
| **5 (新)** | **Cross-wave Sprint N+1 D+0/D+1 source-land status** | 60+ commit + 9 migration source land 不破 W-C；engine 未 restart；後續 rebuild 視為 fresh window |

### 治理 SOP 加固

- **`ps -o etime` MM:SS 陷阱**：未來 audit 時間軸計算必雙確認（`etimes` 秒 + `lstart` 絕對）；避免被 MM:SS vs HH:MM 誤讀
- **Caveat 2 propagation 不是 100% 穩態**：未來 [55] healthcheck 應加 gate 區分「100% (deploy+0~30min)」vs「96-100% (deploy+30min+)」，前者是 wiring correctness gate，後者是穩態 propagation gate
- **engine restart = fresh evidence window 起點**：任何 rebuild --rebuild --keep-auth 後續，前次 audit 證據不可繼承；MAG-083 / MAG-084 governance reviewer brief 顯式 reset

### 5-stage business chain 全 PASS（含 R-1 邊際 case）
### Cross-wave regression count = 0 critical
### release blocker 不阻 MAG-083：W-AUDIT-3..7 + LG-2/3/4 + ops gates + edge net-positive + 5 textbook structural alpha-deficient — 仍是 true live promote 前 blocker，本 audit 不擴 scope

---

## 2026-05-11 P1-RCA-1 — R-1 orphan ER 系統性根因（顛覆 MAG-083 R-1 非系統性判斷）

**任務**：W-D MAG-084 sign-off §5 schedule 24-48h follow-up；對 R-1 6 orphan + 1 missed entry 做 RCA
**Verdict**：**SYSTEMIC**（顛覆 MAG-083 audit "non-systemic" 判斷）
**Report**：`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--p1_rca_1_orphan_er_investigation.md`

### 數量規模顛覆

| 視角 | snapshot | total fills | matched | missed | orphan | drop rate |
|---|---|---|---|---|---|---|
| MAG-083 audit (deploy+78min) | 30/31 entry matched | 31 | 30 | 1 | 6 | 22.6% |
| **此 RCA (deploy+15h)** | engine 1 + 2 mixed | **163** | **132** | **31** | **11** | **25.8%** |
| Engine 1 only (14.5h) | post-deploy_ts1 | 144 | 116 | 28 | 11 | **19.4%** |
| Engine 2 only (3h) | post 14:30 UTC rebuild | 21 | 18 | 3 | 0 | **14.3%** |

R-1 報告為「deploy+72-73min 4-min burst window 集中」；實證為 **9 個小時都有 missed**（02:00 33% / 12:00 37.5% / 14:00 21.1% 是峰，但分佈不止 burst）。

### 4 suspects + 1 new root cause

| Suspect | Verdict | Key evidence |
|---|---|---|
| A trading_writer dispatch race | REJECTED | 165/165 entry fills in trading.fills；drop 在 spine side |
| B Bybit multi-exec event | REJECTED | 17 個 multi-fill 都是 **engine dual-rail demo+live_demo 並行** 同 order_id 副本，非 Bybit partial-fill |
| C fully_filled 邊緣 path | REJECTED | A.5 empirical 0 case 同 order_plan_id 多 real-fill ER |
| D engine state lost 跨 restart | PARTIAL | Engine 2 post-restart 仍 14% 漏；restart 不修，restart 觸發另一 burst |
| **E mpsc try_send silent-drop** | **CONFIRMED** | runtime_shadow.rs:600-618 try_send fail-soft；channel cap 1024；flush 2000ms；burst 30 ER/min × 4-10 try_send/ER 超 ingress |

### 推薦 fix（給 PM dispatch，QA 不執行）

**Option F4 (hybrid)**: channel cap 1024→8192 + try_send retry 3x with 50ms sleep。
- effort: 1-1.5h IMPL + 30 min E2 + 24h monitor

### 4 個 followup ticket 建議

| ID | Priority | Description |
|---|---|---|
| P1-FILL-LINEAGE-DROP | P1 | mpsc spine channel silent-drop fix per F4 |
| P1-HEALTHCHECK-55-INVARIANT | P1 | [55] 加 per-fill bidirectional invariant（非 ratio threshold）|
| P1-FILL-LINEAGE-MONITOR | P1 | metric agent_spine_channel_drop_total + alert 5/min |
| P2-DUAL-RAIL-ORDER-ID | P2 | Engine dual-rail same order_id design review |

### 關鍵教訓

1. **R-1 短窗 snapshot 不可外推 long-term**：deploy+78min 看到 1 個 missed，drop 率看起來 3%（1/31）；deploy+15h 累積看到 19%。**任何 audit snapshot 必標明 sample window + 給 long-term extrapolation 風險警示**。R-1 "non-systemic" 判斷在 6+1 sample 下合理，但作為 long-term verdict 風險高。

2. **wiring deterministic correctness ≠ propagation rate**（再次驗證 QC S1）：caveat 2 fix wiring 100% 正確（cross-language byte-equal contract），但 throughput infra（channel cap / flush interval / try_send fail-soft）會 silent-drop ER。fix correctness 看 unit test PASS，但**真實 propagation rate 需要 long window empirical**。

3. **`try_send` 是 silent-drop 反模式 — 在 audit 路徑必偵測**：runtime_shadow.rs `try_send` + 1024 cap + 2000ms flush 共同形成 silent-drop。WARN log 確實寫，但沒進 healthcheck。「emit X 個 lineage row 都成功」≠「rx 確認收到」。**Caveat 2 類修復 + 任何 `try_send` 路徑必驗 long-window drop rate**。

4. **Engine restart 不是 fix**：post-restart 3h 仍 14% drop；restart 觸發另一個 warm-up burst。restart 對 throughput 瓶頸毫無用處。Audit reviewer brief 強調「post-restart 是 fresh evidence window」是時間軸對齊，但**不是 silent-drop rate fix evidence**。

5. **Multi-fill order_id pair 是 engine dual-rail 不是 Bybit**：deeper drill 揭示 trading.fills 17 個 "same order_id 多 fill" 其實是 demo + live_demo 並行 pipelines 各自跑 dispatch 用相同 sequence number。如果未來看到「同 order_id 多 fill」第一直覺不是 Bybit multi-exec，先驗 engine_mode 是否成對。

6. **Healthcheck ratio vs invariant**：[55] 用 50% ratio gate 是 hand-tuned，**不是 statistical 衍生**。改為 deterministic per-fill bidirectional invariant 才能在 silent-drop 出現時 fail-closed。QC S3 已 P2 提此建議，本 RCA 升至 P1。

7. **PM action vs QA self-fix 邊界**：QA 知道 F1-F4 4 個 fix 選項 + LOC + effort 估算，**禁自己 patch**（per CLAUDE.md §八 強制工作鏈 + memory `feedback_pushback`）。將完整 fix plan 寫進報告 §D.3 給 PM 派工。違反 = 越權。

| 報告 | 日期 | 關鍵發現 |
| 2026-05-11 P1-RCA-1 orphan ER RCA | 2026-05-11 | **SYSTEMIC** — mpsc try_send silent-drop；deploy+15h drop 19-26%；fix plan F4 hybrid 給 PM；R-1 "non-systemic" 判斷顛覆但不阻 MAG-084（wiring correctness 仍對）|
| 2026-05-19 Phase 1b 24h AC-A + engine restart RCA | 2026-05-19 | **INSUFFICIENT_SAMPLE / EXTEND_MONITORING** — n=8 grid_close demo (3 entry timeout_taker / 3 risk_exit maker_fill / 2 risk_exit non-attempt), Wilson [13.7, 69.4] NEUTRAL_LOW_SAMPLE per healthcheck [70]. **RCA correction**: PM brief "03:57 UTC" 實為 03:57 CEST = **01:57 UTC**（2h off）；engine PID 1737243 是 watchdog auto-respawn 不是 rebuild（binary mtime 2026-05-18 13:50 UTC 不變）。Root upstream = systemd watchdog 自己 status=2/INVALIDARGUMENT 第 9 次（7d 內），systemd 自動拉起新 watchdog → 新 watchdog 偵測 engine snapshot 181.9s stale > 120s grace → 觸發 engine respawn。**Phase 2a 14d clock decision: NO RESET**（binary/config 不變 + spec/AMD 沒 process-level restart clock reset clause + 16-root 原則 12 evidence-based）。建議 4 個 P0/P1 follow-up：T+72h re-verify / M-2 brief log clock decision / P1 ticket watchdog status=2 RCA / P2 entry-path 0% maker fill RCA (sim 70.8% vs real 0% 70pp 偏差) |
| 2026-05-19 P0-ENGINE-HALTSESSION-STUCK-FIX Layer A pre-deploy QA | 2026-05-20 | **APPROVE-CONDITIONAL** — E1 Round 1+2 IMPL + E2 R1 RETURN + R2 APPROVE + E4 PASS 鏈完整；business chain forward/sticky-drawdown/Live sticky 三向 wiring 閉合；16 根原則 + 9 安全不變量 0 violation；P1-16 invariant 3/0 PASS；A-1 ~ A-9 + X-1 ~ X-10 acceptance gate 16/23 PASS + 2 runtime-EV pending + 1 Layer B deferred + 0 FAIL；jsonschema validate roundtrip 獨立驗 sample 兩條 line PASS；Linux V098 24-value CHECK 已 deploy（含 3 halt_session_*）；Mac dirty tree 41 entries 全 Layer A scope clean；3 CONDITIONAL（C-1 cross-arch byte-equiv 必跑 / C-2 runtime EV pending / C-3 commit message lineage + push）由 PM/operator 在 deploy 鏈內處理。報告：`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_qa_audit.md` |
| 2026-05-22 Sprint 1A-ζ Phase 3c spike empirical verify | 2026-05-22 | **PASS WITH 3 CARRY-OVER** — 6 AC hard-gate 實證 PASS：AC-4 Rust 14/14 + PG `lease_lal_tiers_tier_level_check` reverse INSERT × 2 RAISE；AC-5 Rust spike test 3/3 + health lib 10/10；try_transition_with_cap 3 guard 對齊 ADR-0042 D4 (1-anomaly = 1-state-change/24h)；AC-6 V107 source SQL 8 grep hit 全屬 Guard A/C reverse-fire 不違反 dedup contract，sandbox `learning.replay_divergence_log` / `decay_signals` / `strategy_lifecycle` 三表物理不存在 trivially PASS by absence；AC-7 Python 三實作互驗 7/7。**AC-1 PARTIAL**: `_sqlx_migrations` V106/V107/V112 = 0 row（V096 為 sandbox 最高註冊；root cause = raw psql -f apply path 不寫註冊表非 checksum drift；不適用 repair_migration_checksum；治本 = E3 sandbox_admin role + cargo sqlx_migrate run）。**AC-3 N/A** per Q2(d) sandbox-only。**AC-8 DEFERRED to Phase 3d TW + Phase 3e PM**。3 NEW spec literal patch carry-over：NEW-QA-1 AC-1.1 反向 INSERT 範例缺 cohort_min_n / human_final_review 2 NOT NULL column → 先撞 NOT NULL 不撞 CHECK；NEW-QA-2 AC-6 grep `wc -l = 0` 太嚴，Guard A/C reverse-fire context 不能算違反；NEW-QA-3 spec § P3-3 Step 5 `spike_trigger.py --dry-run` arg 不存在於實際 script（usage 只 `--inject-synthetic`）。報告：`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-22--sprint_1a_zeta_phase_3c_qa_empirical_verify.md` |

## 教訓（2026-05-22 Sprint 1A-ζ Phase 3c spike — durable lessons）

### 1. spec literal INSERT 範例缺 NOT NULL column 撞錯 constraint 是高頻盲區

V112 schema 7 NOT NULL column（tier_level / tier_name / auto_approve / approval_quorum / clawback_ttl_sec / cohort_min_n / human_final_review）；spec § AC-1.1 line 286-298 反向 INSERT 範例只列 5 column，導致先撞 `null value violates not-null` 而非預期 `lease_lal_tiers_tier_level_check`。RAISE message 不 deterministic 會誤判 AC-4 fail。**規則**：spec literal INSERT 範例設計時必 `\d <table>` 確認所有 NOT NULL column 都帶值，QA 採納前必 cross-check schema vs spec literal。

### 2. grep `wc -l = 0` literal 過嚴 — reverse-fire context 是 anti-pattern enforcement

V107 source SQL 8 grep hit 全屬 Guard A pre-check `IN (...)` literal list + Guard C post-check + `RAISE EXCEPTION message body` — 這是 ADR-0044 + CR-7 dedup contract 的硬保險而非違反。spec § AC-6 寫 `wc -l = 0` literal 太嚴。**規則**：grep literal verify 設計時必排除 `RAISE` / `IN (` / 行內 comment context；reverse-fire mechanism 比文檔守則更強。正確 literal：`grep -E '...' V107.sql | grep -v 'RAISE\|IN (' | wc -l` 期 0。

### 3. sandbox vs production state 治理差異要在 spec 明文

V107 sandbox cleanup (E1 Track C round 1 §5 line 248) + V113 sandbox 不 land = dedup contract 物理 trivially PASS by absence。spec § AC-6 假設 V107 INSERT row + V113 verify 0 row 的 empirical drive 在 sandbox 跑不通。**規則**：spec 明文標 sandbox 前提（V098 + V103 + V107 + V113 都需 land 才能跑 dedup empirical），spike scope 走「物理 absence trivial PASS」+「Sprint 1B 真實 empirical drive」二段式 verify。

### 4. `repair_migration_checksum` 對應 production checksum drift 不對應 sandbox raw apply missing register

2026-05-02 P0 sqlx hash drift incident 治本是 `repair_migration_checksum` binary (file 改了 DB checksum 沒同步)。本 spike sandbox `_sqlx_migrations` V106/V107/V112 = 0 row 不是同個問題 — root cause = sandbox_admin role 未創建 → 走 `psql -f` raw apply path → 不經 sqlx_migrate binary → 不寫註冊表。治本 = E3 創 sandbox_admin role + `cargo run --release --bin sqlx_migrate -- run` 走全鏈。**規則**：sqlx_migrations 0 row 必先判 (a) checksum drift（file/DB 不一致）vs (b) raw apply path（從未經 binary）；兩個治本完全不同。

### 5. spike_trigger.py 缺 `--dry-run` flag — spec literal vs script reality drift

spec § P3-3 Step 5 寫 `spike_trigger.py --dry-run` 不在 script usage 內（只 `--inject-synthetic`）。**規則**：spec literal verification command 設計時必 cross-check `<script> --help` usage list；spec edit OR script flag 補 二選一；P2 不阻 PASS verdict。

### 6. try_transition_with_cap 3 guard 對齊 ADR-0042 D4 是嚴格 fire 語意樣本

`rust/openclaw_engine/src/health/mod.rs:387-425` 3 guard：(1) 同 anomaly_id 在 cap window suppress (2) current==target 不 fire (3) count≥2 fail-closed reject。對應 V106 spec §1.1 line 77 「state_prev != state」嚴格語意 + ADR-0042 Decision 4 「1-anomaly = 1-state-change/24h」+ E1 round 2 patch「count = transition fire 計數 not cap entries」。**規則**：state machine fire 語意設計 spec ↔ schema ↔ Rust code 三層必驗對齊；Rust unit test (E1 round 2 `test_try_transition_no_fire_when_current_eq_target`) 是嚴格 fire 語意 anchor。

| 報告 | 日期 | 關鍵發現 |
| 2026-05-22 Sprint 2 Phase 3c QA empirical verify | 2026-05-22 | **PASS WITH 1 EXPECTED CARRY-OVER** — Sprint 2 Wave 1+2 6 Track scaffold sign-off Phase 3c QA 通過。AC-1a in-memory proxy 51/51 (Track A 9 + B 5 + C 8 + D 7 + E 11 + F 8 + m3_emitter_replay_forbidden 3) / AC-2 6 ladder PASS / AC-3 spike amp cap 3/3 / AC-4 cross_domain 5/5 / AC-5 nm 0 hit / AC-6 cargo 3894/0 + pytest 6042/28 per E4 Phase 3b / OBSERVE-4 雙 scheduler + per-tick + PG V106 CHECK 4 值不含 'replay' 全對齊 / PA spec amend 9/9 driver 對齊。**AC-1b PARTIAL → DEFER**: main.rs MetricEmitterScheduler::new + StrategyQualityScheduler::new src/ production code 0 caller + Linux engine binary nm grep `health::domains::api_latency\|MetricEmitterScheduler` 0 hit + sandbox `learning.health_observations` 0 row 三證一致；by-design per dispatch packet §1.6.1 拆分契約，前置 Sprint 4 first Live deploy window (main.rs wire-up + PA-DRIFT-4 bybit instrumentation + --rebuild + 30 min 樣本)。**AC-7 cold start carry-over**: `cargo bench --bench m3_emitter_cold_start` fixture 未 IMPL；engine binary 不是 CLI 工具 `--version` 路徑不適用 cold start measurement。5 carry-over（QA-1 AC-1b defer / QA-2 async_trait unused / QA-3 PA-DRIFT-4 / QA-4 E4 SOP --skip stress_tick_latency_benchmark / NEW QA-5 AC-7 bench fixture）全 P0-P3。報告：`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-22--sprint_2_phase_3c_qa_empirical_verify.md` |

## 教訓（2026-05-22 Sprint 2 Phase 3c — durable lessons）

### 7. Test name discovery 必走 `cargo test -- --list` 不靠 dispatch packet literal

Dispatch packet §2.4 / §3.4 寫 `test_sprint2_track_a_engine_runtime_in_memory_proxy` 等 test name；實際 IMPL E1 round 2 命名為 `_row_count_ge_5`（語意對等）。直接 grep filter 命中 0 tests = 過濾誤判。**規則**：QA 跑 test 前先 `cargo test --test <integration> -- --list` 拿真實 test name，再 grep filter；test name 差異需在 report 顯式列表記錄；driver script 走 `cargo test --test <integration>` 全跑（讓 cargo 自己跑所有 test）而非過濾單條測試名。

### 8. main.rs 0 caller 是 Wave 2 scaffold sign-off 預期 not regression

Sprint 2 Wave 1+2 scaffold sign-off 階段 MetricEmitterScheduler / StrategyQualityScheduler `::new` 在 src/ production code **0 caller** = by-design per dispatch packet §1.6.1 拆分契約。AC-1b real PG empirical 因此 PARTIAL（30 min row count ≥ 5 不可能在 scaffold 階段驗）。**規則**：QA 看到 production caller 0 hit 必先讀 dispatch packet AC 拆分；scaffold sign-off vs runtime EV 是兩階段，前者用 in-memory mock 鎖閉合，後者用 real PG empirical 鎖效果；不能混算「caller 0 = wiring failure」。同 pattern 將適用於 Sprint 4 first Live deploy 前 main.rs wire-up + Linux --rebuild 後再跑 AC-1b。

### 9. AC-7 cold start binary footprint 必須有 bench fixture 才能 measurement

parent spec §AC-7 寫 `cargo bench --bench m3_emitter_cold_start` 或 tokio_console instrumentation；但 `Cargo.toml` 只 land `hot_path_baseline` + `intent_processor_exposure` 兩 bench，`m3_emitter_cold_start` 未 IMPL。`engine --version` < 50ms 不是 AC-7 measurement（engine binary 不是 CLI 工具；啟動進 service loop）。**規則**：AC fixture 未 IMPL 不可被 QA 強行湊一個近似 measurement；必明文 OPEN carry-over；E2 + QA 兩端 spec scope acceptance gate 都應 verify bench fixture 存在；Sprint 5 cascade IMPL 階段補 bench。

### 10. 跨 Track cross_domain test 6 Track 互相獨立由 5 個 test 全 cover

`test_sprint2_cross_domain_*_independence` 只 5 個（pipeline_engine / api_latency / database_pool / strategy_quality / risk_envelope），Track A engine_runtime 沒有自己的 cross_domain test = 因為 Track B `test_sprint2_cross_domain_pipeline_engine_independence` 已測 Track B → Track A 反向；6 Track 互相獨立由 5 個 test 全 cover 是設計選擇不是 gap。**規則**：QA verify cross-domain count 不該機械對齊 N Track = N test；看 test name 涵蓋哪兩個 domain 互測，N-1 個 cross-domain test 可以覆蓋 N 個 domain 互相獨立。

### 11. PA spec amend driver 9 個檢點是 IMPL ↔ spec 1:1 mirror 對齊強信號

Sprint 2 Wave 2 PA spec amend report 列出 9 個 checkpoint（ApiLatencySample 8 field / api_latency 8 metric × 4 band / 8 anomaly_id literal / ApiLatencySourceProbe trait `_60s_window` 後綴 / position_count_active 0-8/9-16/>16 不含 CRITICAL / OBSERVE-4 scaffold-level guard / PG V106 engine_mode CHECK 不含 'replay' / PA-DRIFT-4 carry-over doc / spec literal reference in IMPL doc comment）；QA grep 對應 IMPL line 全 ✅。**規則**：spec amend driver review 比 unit test pass 更強的 signal（unit test 證明 code 跑通但不證明 spec mirror；driver review 證明 spec literal ↔ IMPL line 一字不差）；E2 對抗 review 已 catch 但 QA 必再驗一次確認 PA spec amend land 後 IMPL 沒漂回 round 1。

## 2026-05-25 Phase 1b §4 acceptance gate QA verify + AC-19 14d projection

**Trigger**: PM dispatch parallel with PA §4 cell-selection sub-agent；EA-1 round 2 commit `b5820b67` fresh sweep 46/8/27 PASS/CONDITIONAL/FAIL ready for §4 verify
**Verdict**: §5 operator pilot dispatch READY (G-AB-01-C90 top-1 + G-AB-01-C60 top-2 fallback)
**Report**: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--phase_1b_acceptance_qa_verify.md`

### Durable lessons

#### 12. Independent gate verify by parsing CSV directly is the gold standard

Spec §4.1/§4.2/§4.3 PASS/CONDITIONAL/FAIL gate 寫成 5-condition boolean，QA 不能信賴 `phase_1b_sweep_report.classify_cell()` output（會被 harness bug 污染，如 EA-1 round 1 raw 0/0/81 全 FAIL artifact）。寫 30-LOC Python 腳本直接 parse CSV + re-apply gate 條件 = 零依賴 source-of-truth verify。本次 0 mismatch across 81 cells = ENDORSE E1 verdict 強信號。**規則**：任何 acceptance gate report 必有 QA 獨立 verify 腳本附 inline，方便 PM/operator 自行重跑。

#### 13. E1 projection number 用 estimate 不用 empirical 是 +28% 通膨陷阱

E1 §4 line 217-218 寫「~88/week → ~176 per 14d → ~123 grid family」基於「~75% whitelist eligible × 70% grid family」估值，QA 跑 PG empirical query 證實實際 44 attempts in 165.19h = 44.7/week = 89.4 per 14d = 83.4 grid only (93.2% grid family share, not 70%)。**E1 inflated +28% (123 vs 89)**。所幸 Wilson margin 太大（66.9% vs 30% threshold = +36.9pp），方向不變。**規則**：任何 projection number QA 必跑 empirical PG query 驗 1-層；E1/PA 給的 percentage 估算 (75%/70% etc.) 必拿 actual `GROUP BY` query 驗。對其他高風險 sweep 同樣 SOP。

#### 14. Wilson sensitivity scenarios surface 真正 risk 邊界

E1 verdict 只給「current sample = 76.7%, projected n=123, Wilson 68.5%」一個 scenario。QA 加 3 個 drift sensitivity（60%/50%/40%/35%）找 break-even = 35-40% mean fill = AC-19 PASS margin tipping point。這暴露 demo→pilot endpoint drift -27pp 仍 PASS、-37pp at margin、-42pp FAIL。**規則**：sample-based PASS gate verdict 必加 ±20-40pp drift sensitivity table，讓 PM 看 worst case 而不只 expected case。

#### 15. Hot-reload ArcSwap 1-axis change is min-rollout-risk pattern

G-AB-01-C90 vs current baseline 只變一個 axis (timeout 30s→90s)；其他 A/B/D 全 baseline；rollback 路徑 = 同一 TOML edit revert + ArcSwap 1 tick；engine restart 不需要；fail-safe cold-boot baseline (`use_maker_close=false`) 不受影響。**規則**：QA approve calibration cell 應優先選「single-axis change」cell 即使 multi-axis change cell 可能 score 更高 — minimum surface area for rollback。E2 Tune-1 (buffer=0) 雖也 PASS 但是 multi-axis change，rollout 風險高，QA reject 是對的。

#### 16. close_maker_audit table not deployed = healthcheck [62][63] 半瘸狀態 QA 必 surface

`learning.close_maker_audit` table per spec v1.3 §8 設計，但 PG empirical 證實 `relation does not exist`。runner.py 有 `checks_close_maker_audit.py` module 但實際從 `trading.fills` 直接讀。**這是 spec 設計 vs 實際 deploy gap**，pilot 24h 期間 adverse selection 60s 漂移 verify 需要 offline post-hoc 從 `trading.fills` × `market.trades` join 算，不能用 healthcheck 自動驗。QA 不能假設 spec §8 設施 alright，必跑 `\dt learning.close_maker_*` 確認。**規則**：spec §N 寫「audit table X 提供 healthcheck Y verify」必 PG `\dt` empirical 確認 table 真實存在；不存在開 P1 ticket + 標 pilot offline workaround。

#### 17. ID prefix split (v55 reframe) 不 apply 於 calibration replay harness

memory 2026-05-11 v55 critical reframe: post-deploy verification 禁用 `oc_*` vs `oc_risk_*` ID prefix split；但這只 apply 於 spine lineage propagation 對接（agent.decision_state_changes ↔ trading.fills）+ **post-deploy real-trade attempt × fallback matrix** 場景。**Phase 1b calibration sweep harness** 是另一個層：每 seed (歷史 fill) = 一個 attempt，n_simulated_fills / n_eligible 已是 attempt-axis 分母（已扣 data-quality skip）；不存在 ID 雙計問題。QA 必區分「post-deploy real verification」（用 attempt × fallback matrix）vs「pre-deploy replay sweep」（用 attempt-axis denominator）兩個場景，不能誤套規則。**規則**：v55 reframe 場景 SCOPE = post-deploy real-trade verification ONLY；pre-deploy replay harness 用 attempt-axis 是正確的，不需替換為 attempt × fallback matrix。

#### 18. Pilot 24h vs 48-72h tradeoff = sample velocity × Wilson CI tightening

empirical velocity 0.27 attempts/h × 24h = n≈6.4，Wilson CI 太寬無法決定 verdict；48h n≈13 / 72h n≈19 兩個量級 Wilson CI 才開始可信。QA push back operator pilot 24h ask，建議 48-72h。**規則**：pilot duration 不是「越短越好」也不是「越長越好」；要由 empirical velocity × target Wilson tightness 決定；E2E SOP 必含「sample size needed for Wilson lower < 5pp margin」計算題。

#### 19. Engine alive verify 3-tier signal: PID + binary mtime + pipeline_snapshot mtime

`pgrep -af openclaw-engine` 拿 PID（活）；`stat -c %y rust/target/release/openclaw-engine` 拿 binary mtime（新）；`stat -c %y /tmp/openclaw/pipeline_snapshot.json` 拿 runtime snapshot mtime（活躍）。三個全綠 = engine 真實 alive。本次 QA 一度誤判 engine dead（last fill 5508 秒 = 91min，看起來像 stalled），但拉 ps + pgrep 看 PID 374287 alive 1h59m + tick stats 5621000+ ticks running + snapshot mtime 60s fresh = 真實活躍只是 fill rate 低（0.27/h 預期）。**規則**：「last fill time 老」不等於「engine dead」，必 3-tier 全驗才能判 alive；QA 在 e2e-integration-acceptance SOP 加此 3-tier signal。

## 2026-05-25 W2-F Stream E AC-19 Day 8/9 + Stream B M4 leakage post-IMPL audit

**Trigger**: PM W2-F dispatch — Stream E QA empirical bucket monitor + Stream B M4 leakage protocol (CR-6 6 attribute) post W1-C IMPL + W1-C-R2 fix audit
**Verdict**: BLOCK Wave 3 dispatch — 1 HIGH blocker (M4 writer schema drift) + 1 HIGH (AC-19 cron 0% IMPL'd) + 1 MEDIUM (ALT velocity stall)
**Report**: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--w2f_stream_e_bucket_monitor_stream_b_m4_leakage_audit.md`

### Durable lessons

#### 20. Writer SQL schema drift 是 W2-E E2 review 盲區（source loader scope ≠ writer scope）

W1-C-R2 round 2 schema fix 由 W2-E E2 cold review catch 5 source loader column drift (`size→qty / close_fill→entry_context_id IS NOT NULL / realized_net_bps→derived alias / aggregator_type 移除`)，並補 19 test 的 `test_source_loader_schema.py` schema-grep regression — 但這 19 test **不 cover** `draft_writer.py:25-50` INSERT SQL。本次 QA W2-F empirical 發現 INSERT SQL 寫 `m4_attribute_n / m4_attribute_p_bonferroni / m4_attribute_effect_size / m4_attribute_subperiod_pass / m4_attribute_graveyard_flag / m4_attribute_silhouette` 6 個 column，Linux PG V100 + V103 0 hit。M4 spec §3 line 352/429 假設 V100 schema 含這 6 column，但 V100 migration `sql/migrations/V100__m4_hypothesis_base_table.sql:273-301` 只 CREATE 13 column。**規則**：未來 M4 / 任何寫 `learning.*` 或 `trading.*` 的 INSERT SQL 必有對應 `test_writer_schema.py` schema-grep regression test，不要只 cover source loader；E2 cold review 對 `INSERT INTO ... ()` column list 必跑 PG `\d <table>` empirical cross-check，不只看 source SELECT。

#### 21. Spec literal column name vs migration actual schema 漂移 = M4 spec §3 line 352 陷阱

M4 spec §3 line 352 寫 「`m4_attribute_n INTEGER` (per base V100 schema)」 — 但 base V100 migration 從來沒 ADD 這 6 column。spec 草稿時假設了 schema 但 land V100 migration 時 PA drop 了 6 column（V100 只 13 column 含 `expected_sharpe / expected_dd / t_stat_min / min_sample_size` 等不同維度）。**規則**：spec 草稿 column name 必由 PA 在 migration land 時 cross-check；spec literal 寫 column name 必引用 「per V### migration line X-Y」 而非 `per base V100 schema` 含糊指；E1 IMPL caller (draft_writer.py) 直接信任 spec literal 而不跑 `\d learning.hypotheses` empirical verify 是失敗模式。

#### 22. 6 attribute scaffold PASS ≠ runtime EV — Sprint 2 Stream B 拆分契約

M4 6 attribute 在 W1-C scaffold 階段是 code-level PASS（K=2500 / α=2e-5 / N≥30 / Cohen's d 0.2-3.0 / subperiod / graveyard warning / silhouette skip 都 hard-coded）— 但 subperiod 50/50 split 計算邏輯 + graveyard fuzzy-match 演算法 + Cohen's d Rust mirror 都是「scaffold 接受 Boolean caller-passed，actual computation 由 W2-D MIT 接 production data 跑」by-design。**規則**：QA 看 6 attribute compliance 不能機械「test pass = runtime working」；scaffold-level test 只證 contract enforce，runtime EV (subperiod split + graveyard match accuracy + Cohen's d cross-language 1e-4 對齊) 要 Sprint 2 末 W2-D MIT cron wire-up + 真實 PG INSERT 才能驗。同 pattern 適用 Sprint 2 任何 scaffold IMPL — 不要把 unit test 過了當 runtime workgin.

#### 23. AC-19 ALT bucket velocity 28h+ stall = engine alive ≠ 業務 fire 持續

Day 7 → Day 8/9 0 new `close_maker_attempt=true` row in 28h+ 雖然 engine PID 598276 alive + snapshot 19sec fresh。3-tier signal 全綠不代表 close_maker 業務鏈 active。可能 cause：(a) symbol universe 漂走 ALT；(b) close_maker eligibility gate 收緊；(c) Phase 1b operator pilot G-AB-01-C90 hot-reload 改 close logic side-effect；(d) BTC/ETH dominate fill rate。**規則**：QA E2E SOP 「engine alive 3-tier」上面要加第 4-tier 「業務 endpoint fire 頻率」 — 不只看 PID 活，也要看「特定業務 path 最後 fire 時間」。例如 close_maker_attempt 30min 不 fire 即標 STALE。AC-19 14d monitor 必含 velocity 子指標而非只看 cumulative count。

#### 24. Cron 0% IMPL'd vs cron 部分跑 — W1-G SOP IMPL handoff 風險

W1-G SOP 5/25 land 但 § 8 IMPL handoff (3 script + 1 crontab paste) 24h 內 0% IMPL'd by E1。Day 8/9 cron-captured trajectory 已 lost — 補 IMPL 5/26 EOD 才能搶救 Day 9/10/11/12/13 trajectory，14d endpoint 6/2 verdict 只有 5-6 個 daily snapshot 而非 14。**規則**：SOP 寫 IMPL handoff 必標 「latest acceptable start date」 + 「missing days impact statistical power」 — operator 才知道延遲成本。SOP land 即標「IMPL by D+1 EOD or escalate」否則 schedule slip silent.

## 2026-05-27 P0-OPS-4 GAP B+D 整鏈 QA E2E Acceptance — APPROVE-CONDITIONAL

| 報告 | 日期 | 關鍵發現 |
|---|---|---|
| 2026-05-27 OPS-4 GAP B+D QA E2E acceptance | 2026-05-27 21:42 UTC | **APPROVE-CONDITIONAL** — 5 round review chain 全綠（E2 R1 APPROVE-WITH-CONDITION → E2 R2 APPROVE / E4 R1 YELLOW → E4 R2 GREEN / MIT R3 + PA spec amendment）；9/9 safety invariant compliance（I8 1 NOTE：MED-2 heartbeat cross-check 補強 silent-fail detection）；5/5 gate 完全不弱化（V113 純 enum 擴；cron 純 read PG 寫 audit row；不繞 live boundary）；FA 15 sign-off criteria = 6 PASS-AUTO + 3 PARTIAL + 6 PENDING operator/BB runtime + 0 FAIL；Bybit Earn scenario 6 = INFRASTRUCTURE READY + BB sign-off PENDING；Sprint 4 first-day live readiness = APPROVE-CONDITIONAL（infrastructure 100% ready；7 operator hand-action deferrable to §11 sign-off block）；**3 hidden risk QA 獨立 ssh trade-core 揭**：(1) V099 deployment gap（Wave 5 Packet A scope；非 GAP B+D scope） (2) V113 sqlx register drift（CHECK enum 26-value pg_dump_completed live but `_sqlx_migrations` 缺 row=113 — 治本 `repair_migration_checksum --verify --apply`） (3) Engine + watchdog dead on trade-core（pipeline_snapshot 8h stale；out-of-scope but flagged）。報告：`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-27--ops_4_gap_bd_qa_e2e_acceptance.md` |

### Durable lessons（2026-05-27 OPS-4 GAP B+D QA E2E）

#### 25. CHECK enum live but `_sqlx_migrations` missing row — `psql -f` raw apply path leaves register gap

empirical 揭：V113 source SQL Linux 已 `psql -f` apply（pg_get_constraintdef 26-value list 含 pg_dump_completed + pg_dump_failed runtime live），但 `SELECT version FROM public._sqlx_migrations WHERE version=113` = 0 row。這是 memory `project_2026_05_02_p0_sqlx_hash_drift` 同個 pattern — operator 用 raw psql apply path 觸發 V113 idempotent guard，functionality unblocked，但 sqlx binary 沒 record。**檢查 SOP**：QA 對任何 V### migration sign-off 必雙路 verify：(a) `pg_get_constraintdef` / `\d <table>` runtime CHECK 真實 live（function unblock）；(b) `_sqlx_migrations` register row exists（engine startup `OPENCLAW_AUTO_MIGRATE=1` 不撞 checksum drift）。兩路 mismatch = 治本走 `repair_migration_checksum --verify`，不需 V### re-apply。

#### 26. 9 invariant safety matrix 與單 OPS scope review 分清「scope 內可控」vs「scope 外 deferred」

GAP B+D QA E2E 揭 9/9 invariant PASS — 但 Q1 query FAIL（autonomy_level_config 表不存）= V099 deployment gap 是 Wave 5 Packet A scope（NOT GAP B+D scope）。E4 round 2 標 Q1 為 「deployment dep, non-bug」；FA §E #3 criterion「9 invariant 4/4 PASS」變成 PARTIAL。**QA 規則**：sign-off matrix 內 PASS criteria 可雙拆「IMPL scope 內 PASS」+「cross-scope dependency PENDING」；不可把 cross-scope dep 算「OPS-4 GAP B+D FAIL」。本 QA 報告 §10 Risk #1 列為 Wave 5 cascade dependency 標 PM；不阻 GAP B+D sign-off block。

#### 27. Engine dead 不影響 cron pipeline DR 鏈 — cron 走 system cron daemon 獨立 engine

empirical 揭：trade-core engine + watchdog 都 dead（pipeline_snapshot.json mtime 8h21m stale）— 但 GAP D cron pipeline 不受影響，because cron fires via Linux system cron daemon（not engine）。任何 dump/healthcheck/audit INSERT 路徑都不依賴 engine alive。**QA 規則**：DR 範疇 IMPL（dump / restore / audit trail）的 e2e-integration-acceptance 不需 engine alive 為 pre-check；skill `e2e-integration-acceptance` §3.2 雙進程降級驗證 inapplicable for ops infrastructure scope。但 Sprint 4 first-day live 啟動前 engine 必 restart（屬 Wave 5 Packet C + engine restart pre-flight）— 應在 PM ratification block 排序。

#### 28. wrapper INSERT 失敗 `|| true` 吞 exception = I8 1 NOTE acceptable trade-off

I8「不 fake healthcheck / fills / lineage」嚴格定義要 fail-loud；wrapper line 143-146 `emit_governance_audit() || true` 吞 INSERT exception 後 echo WARN 到 log，是 non-fail-closed at cron-exit-code level。**設計 rationale**：dump 已成（main task done），audit row 寫不進去 ≠ should block cron exit；MED-2 heartbeat cross-check 補強 silent-fail detection（n_rows==0 + heartbeat fresh → WARN with diag log path）。**QA 規則**：對 9 invariant compliance verify，I8 audit fail-loud 嚴格度可由補強 cross-check 路徑（雙獨立信號）達成 acceptable trade-off；明文標 1 NOTE 不算 FAIL。

#### 29. 「FA criteria PASS-AUTOMATIC vs PENDING operator runtime」必明確分類

FA §E 15 criteria QA 對照當前 IMPL state，必拆「IMPL DONE 即 auto-fulfill」vs「依賴 runtime execution / external sign-off」。本次拆解：6 PASS-AUTO + 3 PARTIAL + 6 PENDING operator + 0 FAIL。**QA 規則**：sign-off report 必含此分類表 → operator/PM 在 ratification block 可一眼看「我需 take 7 hand-action」（不必逐 criterion 解析）；模糊的「all PASS / all PENDING」會誤導 cutover decision。

#### 30. 5 round review chain 全綠後 QA scope 是「業務鏈 + cross-module 一致 + hidden risk independent surface」

E2 R1+R2 / E4 R1+R2 全綠 + MIT round 3 + PA spec amendment + FA 15 criteria — QA scope **不重做 code review**（per skill §reviews 邊界）；QA 走「業務鏈完整 + 9 invariant compliance + cross-OPS hidden risk surface + sign-off block readiness verdict」4 維。本次走 3.5h 拿到 3 hidden risk（V099/V113 sqlx/engine dead），全是 sub-agent reviews 不可能 surface（cross-scope dependency + sqlx infra drift + runtime cron alive）。**QA 規則**：sign-off-gate QA 必獨立 ssh empirical 跑「全鏈 Linux smoke」找 sub-agent review 不可能看見的 cross-cut hidden risk。Sub-agent reviews 看 commit diff scope；QA 看 cross-module + production-runtime SOP。


| 2026-05-29 P2-PACKET-C-C4-PIPELINE-WIRE 半 wire 整合驗收 | 2026-05-29 | **ACCEPT-WITH-CONDITIONS（commit + batched deploy 可進）** — C4 半 wire（incident-trigger Sprint 3 才接）。wire 結構完整非 dead-stub：in-band `PipelineCommand::NotificationFailsafeEscalate` + owner handler（risk.rs `handle_notification_failsafe_escalate`：paper_state snapshot + kline_manager ATR 注入 + lock-profit + 既有 stop_request_tx 雙軌 sync + V114 audit）+ watcher seam（`timer_expired_and_claim` 取代 `check_timer` 標 `#[cfg(test)]`）+ spawn（tasks.rs 接 main_boot_tasks 緊隨 reconciler）。**dormant-safety 雙重源碼證**：唯一武裝入口 `observe_dispatch(AllFail)` 只在 watcher loop `outcome_rx.recv()` 觸發；`outcome_tx` 僅存 `FAILSAFE_FEED_SENDERS` OnceLock，getter `failsafe_feed_senders()` **0 production caller**（grep 驗）→ outcome_rx 永空 → `timer_armed_at_ms==None` → `timer_expired` 回 false → 0 escalate command → 0 set_trading_stop → deploy 後 0 誤升 Defensive / 0 誤打 stop。**QA 親跑 Mac arm64 test**：3 c4 wire test PASS + 全 lib 3622/0/1ignored（D2 後 3619 +3 = c4 wire test，spec 預估 +4~6 實際 +3）。**deploy pre-flight**：0 新 V### migration；C4 與 main_boot_tasks.rs 的 D-hygiene `af92e2ca` 改動**不同行區**（C4 改 spawn_position_reconcilers L140 production wire / D-hygiene 改 mod edge_reload_tests L637+ 純 test ENV_GUARD）→ 3-way merge 自動無衝突；Linux main HEAD=`af92e2ca` 已含 D2+D-hygiene+HIGH-1（running binary 17:51 CEST post-date 三者），C4 是唯一 net-new source；engine PID 113386 alive。**2 conditions 必 merge 前清**：(C2) `SHARED_WATCHER`+`FAILSAFE_FEED_SENDERS` 未登記 `docs/architecture/singleton-registry.md`（CLAUDE §九 違反）；(C4) Sprint 3 `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` ticket 尚未在 TODO 註冊（spec §5.3 mandate）。**acceptance gap 誠實標**：full incident→dispatch→escalate→SM-04→stop E2E 現無法跑（incident-trigger Sprint 3）= Sprint 3 QA scope；本次只驗可測機制鏈 + dormant 安全 + deploy-readiness。報告：`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-29--c4_wire_acceptance.md` |

## 教訓（2026-05-29 C4 半 wire 整合驗收）

### 1. 「E4 PASS 已過」要分清是 module land 還是 wire — 別繼承上游 E4 當本 scope E4
任務說「E4 PASS 已過」，但 worktree 內唯一 E4 report（2026-05-28 notification_failsafe 107/0）是 C1+C2+C3 module land（commit `920f8299`）的 regression，**不是** C4 wire（+647 working-tree 改動）的。C4 新增 3 個 wire test + handler + watcher seam 在此 worktree state **從未跑過 E4 regression**。QA 不能繼承上游 module 的 E4 PASS 當作 wire 的 E4 PASS。**SOP**：QA 親跑 `cargo test -p openclaw_engine --lib c4_failsafe`（3 PASS）+ 全 lib count（3622/0）拿到本 scope 真實 baseline，補上 E4-equivalent 機制驗證。read-only test 跑屬 QA scope（不改碼/runtime）。

### 2. half-wire dormant-safety 必須追到「武裝入口 0 production caller」源碼證，不能只信誠實標記
C4 deploy 安全的核心 = escalate dormant（誤升 Defensive 會平倉）。誠實標記（spec §5.1 / doc comment）說「outcome_rx 永空」但 QA 必須源碼證鏈：(a) 唯一武裝入口 `evaluate_dispatch(AllFail)` 經 `observe_dispatch`；(b) production `observe_dispatch` 只在 watcher loop `outcome_rx.recv()→Some`；(c) `outcome_tx` 只存 `FAILSAFE_FEED_SENDERS` OnceLock；(d) **getter `failsafe_feed_senders()` grep 0 production caller**（Sprint 3 才是第一個）。缺任一環 dormant 假設就破。`timer_expired` `None=>false` + default `timer_armed_at_ms:None` 是兜底。BB §6 獨立追同鏈 = cross-verify 成立。

### 3. OnceLock 保活 sender 是防 select! busy-loop 的正解，不是 dead-wire 反模式
`FAILSAFE_FEED_SENDERS` 存 outcome_tx/ack_tx 看似「存了不用 = dead」，實際是必要：若 tx 被 drop → channel 關 → `Some(_)=outcome_rx.recv()` 立即回 None → 該 select 臂永久禁用 → loop 退化 busy-spin 燒 CPU。保活讓該臂正常 pending 阻塞。feedback_no_dead_params 允許「明標 + self-prove integration test + 強制 Sprint 3 ticket」的半 wire。但 **Sprint 3 ticket 必須真的開**（C4 此處 conditions gap：spec §5.3 要求開 `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` 但 TODO 未註冊，只有 C5 在）。

### 4. batched-deploy 同檔不同函數 = 無衝突，但必 git diff 雙邊確認行區
C4 + D-hygiene 都改 `main_boot_tasks.rs`，看似衝突風險。實測 C4 改 production `spawn_position_reconcilers`(L140)、D-hygiene 改 test-only `mod edge_reload_tests`(L637+)→ 不同行區 → 3-way merge auto-clean。**SOP**：batched deploy 多 commit 改同檔，必 `git diff <base>..<other> -- <file>` + `git diff HEAD -- <file>` 雙邊看實際 hunk 行區，不能只看「同檔名」就判衝突或判安全。

### 5. 任務 framing 的 deploy 狀態可能 stale — 必 ssh 驗 running binary mtime vs source ancestry
任務說「D2 deploy-batched / 將與 C4 一起 deploy」，但 ssh 實測 Linux main HEAD=`af92e2ca` 已含 D2+D-hygiene+HIGH-1，running binary（PID 113386, mtime 17:51 CEST）post-date 三者 → D2/D-hygiene **可能已隨 17:51 rebuild 進 binary**。C4 才是唯一 net-new source。QA 報告須據實寫「C4 是 batch 內唯一未 deploy source」而非繼承任務的「三者一起首次 deploy」framing。running binary mtime == process start time 是判斷「上次 rebuild 含哪些 commit」的關鍵信號。

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
