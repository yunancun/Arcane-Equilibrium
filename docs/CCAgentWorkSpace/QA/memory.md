# QA Memory — 工作記憶

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
| 2026-05-04 REF-20 Sprint A R3 smoke E2E | 2026-05-04 | **BLOCK** — R3 deploy commit `66b650ea` 含 P0 FastAPI signature bug：`from __future__ import annotations` + lazy module import + module-level re-bind 三者組合，FastAPI signature inspection 把 `body: ReplayExperimentRegisterRequest` 視作 Query parameter（不是 BaseModel body）。`/api/v1/replay/experiments/register` + `/api/v1/replay/run` 兩 routes 100% 422 missing body；hermetic test 也 fail；4 個 Sprint A acceptance SQL count 全 = 0；無 trading.fills leak（vacuous truth — register 沒進到 mutation 點）。push back PM Option A/B/C；Sprint A R3 不可結案 |
| 2026-05-04 REF-20 Sprint A R3 smoke E2E **round 2 (post-hotfix)** | 2026-05-04 | **STILL BLOCK** — hotfix `cad8ed84` 移除 `from __future__ import annotations` **runtime 確認有效**（/openapi.json 200 vs round 1 500，register 改回 503 reason=`engine_binary_sha_not_provisioned` vs round 1 422 body missing；45 hermetic test pass）。但 P0 BLOCKER 降級為 P2-A（`OPENCLAW_ENGINE_BINARY_SHA` env 仍未注入 API process — restart_all.sh 沒 export）+ P2-B（`/tmp/openclaw/replay_fixtures/btc_1m_smoke.json` 不存在；可 reuse `rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json`）。**新發現 P0-INFRA**：Linux 工作樹有 hotfix uncommitted edit，但 origin/main 已 commit `cad8ed84`，`git status` dirty + behind origin/main 違反 §七 commit 即 push 規則。4 表 acceptance SQL 仍 0/0/0/0。push back PM 走 §八 強制鏈派發 R3 round 3 fix（restart_all 加 ENGINE_BINARY_SHA + REPLAY_FIXTURE_URI export + git working tree clean）|
| 2026-05-04 REF-20 Sprint A R3 smoke E2E **round 3 (post-`e9d547c0`)** | 2026-05-04 | **STILL BLOCK** — round 4 infra fix 真實落地（API process env 含 `OPENCLAW_ENGINE_BINARY_SHA=38c72877...`，commit `e9d547c0`/`2ae93992`；Linux working tree clean = `e9d547c0`），4 表 acceptance progression：experiments=1 (E1 round 4 row) + run_state=1 (R3 round 5 spawn 寫 status='failed') / report_artifacts=0 + simulated_fills=0。**新揭 P0-NEW root cause**：`route_helpers.build_default_manifest_payload` 寫 placeholder signature manifest，但 `replay_runner` Sprint 1 Track B (commit `edf33c0`) 已將 sibling key.hex 缺 fail-open 改為 **fail-closed**（line 548-557 `manifest_signer_key_missing`）。Sprint A R3 (`66b650ea`) 沒 ship 配套 key.hex provisioning → 必死。手動跑 replay_runner 同 manifest 取得 stderr 證實。**新揭 P0-NEW-INFRA**：`subprocess.Popen stderr=subprocess.DEVNULL` 吞所有 subprocess root cause。**Round 6 必補**：route_helpers 寫 sibling key.hex (dev fixture key `aabbccddeeff...`) + 用真實 HMAC sign manifest + stderr PIPE + 配套 hermetic test for sign+verify cycle。push back PM @八 強制鏈派 R3 round 6（不走 P0 快速通道；計劃中 deploy infra fix）。新建議 PM Sprint A close gate：hermetic + R3 smoke E2E full cycle + Wave 9 safety + FK lineage valid 三層全綠。FK lineage 已 valid（run_state.manifest_id == experiments.experiment_id）。No trading.fills leak（trivially PASS）|

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

| 報告 | 日期 | 關鍵發現 |

