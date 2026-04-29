---
date: 2026-04-29 CEST
topic: 62-Finding Audit Remediation — Batch A 至 F 全程歸檔
type: archive (TODO.md 頭部敘述歸檔)
status: ✅ 全 62 findings 完成修復、簽核、tracking 更新並部署到 Linux
primary_commits:
  - bc3fa70  # 主修復（A-F 合併 PR）
  - 6539e4e  # 文檔同步
  - 5db4e29  # restart ownership hotfix
batch_signoff_reports:
  - docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_a_e_gap_reassessment.md   # 含 A 接手再驗
  - docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_b_critical_auth_secrets_api_signoff.md
  - docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_d_risk_config_fail_closed_signoff.md
  - docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_e_operator_runtime_ownership_signoff.md
  - docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_f_ml_agent_autonomy_prework.md
  - docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_f_ml_agent_autonomy_signoff.md
audit_source:
  - docs/audit/final_record_zh.md
  - docs/audit/final_summary.md
  - docs/audit/audit.md
  - docs/audit/remediation_groups.md
schedule:
  - docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--audit_62_findings_remediation_schedule.md
tracking_ledger: docs/audit/remediation_tracking.md
linear_milestones:
  - NCY-5  Batch A — Live write boundary freeze
  - NCY-6  Batch B — Critical auth / secrets / API exposure
  - NCY-7  Batch C — Trading record durability
  - NCY-8  Batch D — Risk / config fail-closed
  - NCY-9  Batch E — Operator / runtime ownership
  - NCY-10 Batch F — ML / agent autonomy readiness
linear_project: https://linear.app/ncyu/project/openclaw-62-finding-remediation-de1bc8f68e42
---

# 62-Finding Audit Remediation — Batch A 至 F 歸檔

本檔案承接 TODO.md 頭部 line 1~50 之歷次「最新更新」/「前次更新」chain，將 Batch A-F 全部 62 個 findings 的修復、驗證、簽核敘述歸檔，TODO.md 隨後以一行索引取代。

**總量**：62 findings（P1=29 / P2=29 / P3=4 / P0=0）。儘管無 P0 嚴重度，**含 live-release blockers**（Batch A 為 live write boundary freeze）。

**批次順序**（嚴格 PM gate，禁止單一大 patch 一次合 62 條）：
Batch A → Batch B → Batch C → Batch D → Batch E → Batch F

每個 implementation batch 必經 `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM` 工作鏈；涉及 live/auth/security 加 `CC/E3/BB` gate。

---

## Batch A — Live Write Boundary Freeze（Linear NCY-5）

**目標**：所有 live close/cancel/flatten/auth renewal path 必須通過唯一一條已簽署、mode-aware、operator-authorized 邊界，禁止旁路。

**Findings（5）**：`LP-001` · `OE-007` · `OS-001` · `RC-001` · `SW-002`

**Required chain**：
PM -> CC + E3 + BB + PA -> E1 + E1a -> E2 -> E4 -> QA -> PM

**Work split**：
- E1：Rust live auth watcher、live pipeline respawn、command sender refresh、exchange reduce-only flatten 語義
- E1a：FastAPI live renew/close routes、operator live flatten 腳本
- CC：16 根原則 #1 / #2 / #3 / #4 / #5 / #6 對照
- E3：authorization 與 bypass review
- BB：Bybit 端 reduce-only / close / cancel 兼容性

**Exit gate A**：
- Renew live authorization 必須以 exact live-reserved mode
- Direct REST live fallback 已移除或單獨 emergency-authorized
- Emergency flatten 無法在 exchange-aware reduce-only dispatch 確認或最終失敗前標 state flat
- Live respawn 會 refresh command senders 或使用 dynamic slots
- Tests 證明 fail-closed 行為涵蓋：non-live-reserved / expired auth / missing sender / direct script path

**Verification（合併進 A-E gap reassessment 後）**：
- A-E Python targeted suite **128 passed**
- Batch A targeted suite **69 passed**（含 11 既有 warnings）
- Batch A red test：real test fixture drift after Batch B auth hardening；direct handler test 改傳 actor with `operator` role + `live:trade` scope；handler behavior 仍 `409 unavailable stop channel`
- `bash -n` 修補的 lifecycle/bootstrap 腳本通過
- Static scan：broad engine kill / heredoc regression 無命中

**Sign-off**：
- 含括 A 的 gap reassessment：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_a_e_gap_reassessment.md`
- A-E 全部已 fixed locally；Linux fast-forward 並 `restart_all.sh --rebuild --keep-auth` 完成 redeploy 後 commit `bc3fa70` + `5db4e29` 進 runtime

---

## Batch B — Critical Auth / Secrets / API Exposure（Linear NCY-6）

**目標**：所有 state-changing routes 共享 operator/scope authorization；可重用之 privileged credentials 從 repo / log / proxy / process surfaces 中消失。

**Findings（14）**：`DAPI-001` ~ `DAPI-006` · `RC-003` · `SC-001` ~ `SC-007`

**Required chain**：
PM -> E3 + PA -> E1a -> E2 -> E4 -> PM

**Changes（已落地）**：
- 共享 operator+scope gates，覆蓋 high-risk write routes：AI budget、risk、paper/demo、live session/close/authority、strategy writes、executor shadow-toggle、scheduled restart、ML promote
- Server audit identity 來自 authenticated actor（AI budget writes）；client-supplied `updated_by` 忽略
- Dashboard HTML、DB health、model registry reads 需 auth；DB/model error details redact
- `/openclaw/*` proxy 只 forward header allowlist；預設 strip Cookie / Authorization
- API bearer handling 拒 placeholders、支援 strict mode、不再 print auto-generated token
- GUI 密碼載入拒 blank/placeholder；Cookie `Secure` 可強制或從 trusted proxy headers 推導
- Grafana provisioning 移除 committed bearer/Postgres/admin credentials；anonymous access 預設 off；host binding 預設 `127.0.0.1`
- Runtime scripts：DB URL / IPC HMAC 改 0600 secret files；長壽命 engine/API process 只接 `*_FILE` paths；migration scripts 用 `PGPASSFILE`；curl callers 用 0600 config/payload files
- Rust engine + Python API resolve `OPENCLAW_DATABASE_URL_FILE` + `OPENCLAW_IPC_SECRET_FILE`，保留直接 env 兼容

**Verification**：
- Targeted Python pytest **47 passed**（test_batch_b_security_auth + test_ai_budget_routes + test_reset_drawdown_route + test_executor_shadow_toggle_api）
- `py_compile` / `bash -n` / `plutil -lint` / `docker-compose config` 全綠
- `cargo check -p openclaw_engine` OK with existing warnings
- Static sweep 確認無 password-bearing `psql "$DSN"` / tokenized Telegram URL / `change-me` token docs / `3000:3000` Grafana bind / proxy Cookie/Auth forwarding / 長壽命 `OPENCLAW_IPC_SECRET="${...}"` 殘餘
- `cargo fmt --all --check` 仍受 pre-existing 全 repo Rust formatting drift 阻擋（不在本 batch 範圍）

**Sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_b_critical_auth_secrets_api_signoff.md`

---

## Batch C — Trading Record Durability（Linear NCY-7）

**目標**：WS batches、REST dispatch failures、DB writer failures、migration gaps 不得靜默抹除或誤述交易事實。

**Findings（12）**：`OE-001` ~ `OE-005` · `OE-008` · `OE-009` · `DBW-001` ~ `DBW-005`

**Required chain**：
PM -> PA + FA -> E1 + E1a -> E2 -> E4 -> QA -> PM

**Work split**：
- E1：Rust private WS parsing、execution listener dispatch、pending order/close terminal failure 語義、fill idempotency、writer channels
- E1a：SQL migration ordering、Python/API DB pool reset、migration/audit scripts
- FA：交易 lifecycle 重建 acceptance criteria

**Exit gate C**：
- Bybit private WS `data` arrays emit 全部 events
- REST dispatch failure 發 terminal events，clear 或標 pending state
- Fill persistence 用 Bybit `exec_id` 或等價 exchange-native idempotency
- Writer insert failures 不 clear buffers 而無 durable retry/outbox/alert
- Bounded channel full/closed 條件曝 counters，不靜默丟關鍵 rows
- `learning.exit_features` migration 在真實 migration 順序中
- 顯式 auto-migrate 對 `NoPool` fail-closed
- API DB pool 在歸還連線前 rollback/reset

**Sign-off**：含括於 A-E gap reassessment（`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_a_e_gap_reassessment.md`）+ tracking ledger `docs/audit/remediation_tracking.md`

---

## Batch D — Risk / Config Fail-Closed（Linear NCY-8）

**目標**：missing config、stale H0 refresh、rejected IPC updates、partial strategy parameter updates 不得弱化風控強制。

**Findings（8）**：`RC-002` · `RC-004` · `RC-005` · `RC-006` · `SADF-002` · `SADF-003` · `LP-002` · `OE-006`

**Required chain**：
PM -> CC + PA -> E1 + E1a -> E2 -> E4 -> PM

**Changes（已落地）**：
- H0 periodic status refresh 不再 reset cooldown/kill-switch state（新增 `H0Gate::risk_snapshot()` + `build_status_risk_snapshot(...)` 合併）
- Startup config loading：demo/live risk config 缺檔時 fail-closed（不再 fallback-to-default）
- Risk-governor tier constraints 在 order admission 一致強制：
  - new-entry blocking on `new_entries_allowed` / `reduce_only` / `requires_operator`
  - quantity scaling via governor `position_size_multiplier`
  - reducing/unwind intents cap 至既有 position quantity，避免 oversized opposite-side intents flip/open
  - demo/live dispatch 將 capped opposite-side orders 標為 close/reduce-only，跳過 proactive mirror insertion
- Legacy IPC `update_risk_config`：
  - send failure 回 JSON-RPC internal error
  - success 回應現等 event-consumer apply ack（`updated=true, queued=false, applied=true`）
  - apply/ack timeout 回 error 而非 false success
- Mixed strategy-params updates 為 atomic：typed validation 先於 `conf_scale` apply；validation failure 不部分 mutate strategy state
- Demo/Live strategy parameter load errors fail-closed 至 all-inactive；Paper 保留 exploration default fallback
- `clean_restart.sh` / `fresh_start.sh` 改用 canonical `openclaw_engine` package id（`cargo pkgid -p openclaw_engine` / `cargo build -p openclaw_engine`）
- Close dispatch retry path 加真實 per-attempt timeout budget（`CLOSE_ATTEMPT_TIMEOUT_MS=500`）

**Verification**：
- Batch D static pytest **8 passed**（test_batch_d_risk_fail_closed.py）
- D + E 合跑 **18 passed**
- Rust targeted **9+ passed**（含 status_risk_snapshot_preserves / governor 4 cases / conf_scale partial / update_risk_config send_failure + happy / strategy_params demo+live fail_closed / close_attempt_timeout 500ms）
- Regression：cargo lib **2355 passed** · intent_processor::tests **86 passed** · `cargo build --release` OK
- A-E Python targeted suite **128 passed**

**Sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_d_risk_config_fail_closed_signoff.md`

---

## Batch E — Operator / Runtime Ownership（Linear NCY-9）

**目標**：watchdog、cron、multi-worker startup、API restart、DB reset、launchd、reporting scripts 必須 idempotent、service-manager aware、難以誤用。

**Findings（13）**：`SW-001` · `SW-003` ~ `SW-007` · `OS-002` ~ `OS-007` · `DAPI-007`

**Required chain**：
PM -> E3 + PA -> E1 + E1a + TW -> E2 -> E4 -> PM

**Changes（已落地）**：
- `POST /api/v1/system/scheduled-restart` 已 disable（`HTTP 410`）並明確指向 service-manager / operator-script ownership（`launchctl` / `systemctl` 或 `helper_scripts/restart_all.sh`）
- `clean_restart.sh` / `fresh_start.sh` 在 stop 前先設 maintenance flag、用 `EXIT/INT/TERM` traps guard cleanup、用 validated API PID shutdown 避免誤殺 `:8000` 上其他 services
- `fresh_start_reset.py` execute confirmation 改 DSN/環境 fingerprinted；`fresh_start.sh` 必須帶 `--db-reset-confirm=...`，不再 auto-generate confirm token
- `restart_all.sh` / `stop_all.sh` / `clean_restart.sh` / `fresh_start.sh` 改用 validated engine PID ownership：accepted engine PIDs 必須匹配本 repo binary path 或從本 repo cwd 跑 expected engine command；移除 broad engine `pkill -f`
- 新增 `helper_scripts/deploy/launchd_preflight.sh` + 更新 deploy runbook 強制 preflight-before-load（含 plist placeholder checks + secret-file readiness）
- `mac_bootstrap_db.sh` 將 `trading_admin` 建為 least-privilege（`NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION`）；密碼以 psql variable substitution 綁定；SQL heredoc 正確閉合
- Cron wrappers 加 overlap lock guards（`mkdir` lockdir + trap cleanup）：`cron_daily_report.sh` / `cron_observer_cycle.sh` / `db/counterfactual_daily_cron.sh` / `db/passive_wait_healthcheck_cron.sh`
- `cron_daily_report.sh` 改用 `jq` build Telegram payload + `curl --config` + payload file，不再讓 tokenized URL 與 shell-interpolated JSON 出現在 argv
- Multi-worker ownership hardening：
  - Evolution scheduler leader election lock（`flock`）+ non-leader skip path
  - Reconciler alert monitor leader lock
  - Grafana writer leader lock + non-leader skip logging
  - ExperimentLedger 持久化 EXPIRY transitions via debounced save

**Verification**：
- Batch E runtime ownership pytest **10 passed**
- B + E 合跑 **20 passed**；D + E 合跑 **18 passed**
- `bash -n` 全綠（lifecycle / cron / launchd_preflight / mac_bootstrap_db）
- `py_compile` 全綠（control_legacy_routes / evolution_auto_scheduler / experiment_ledger / paper_trading_wiring / grafana_data_writer / strategy_wiring / main / fresh_start_reset）
- `rg -n 'pkill -f|...'` 對 broad-kill / heredoc fragment 無命中
- A-E Python targeted suite **128 passed**；Rust full lib **2355 passed**

**Sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_e_operator_runtime_ownership_signoff.md`

---

## Batch F — ML / Agent Autonomy Readiness（Linear NCY-10）

**目標**：ML、LinUCB、Teacher、Strategist 維持 observation-only 或顯式 bounded，直到 schema、labels、promotion、reward loops 一致為止。

**Findings（10）**：`MLM-001` · `MLM-002` · `MLM-003` · `MLM-004` · `MLM-005` · `SADF-001` · `SADF-004` · `SADF-005` · `SADF-006` · `LP-003`

**Required chain**：
PM -> QC + MIT + AI-E + PA -> E1 + E1a -> E2 -> E4 -> QA -> PM

**Execution note**：本 batch 因 worktree 已含 A-E broad dirty changes 在 adjacent files，PM 保留本地擁有權避免 cross-worker collisions；effective chain 為 PM(local) -> QC/MIT/PA local review -> E1/E1a impl -> E4 targeted -> PM sign-off。

**Changes（已落地）**：
- Feature compatibility 改採兩條 independent contracts：
  - schema hash（feature names / order）
  - definition hash（feature semantics）
- Runtime ONNX metadata validation 拒絕 feature-definition hash drift 的 artifacts
- Training ETL 改以 row-level `feature_schema_version` / `feature_schema_hash` / `feature_definition_hash` 過濾；malformed / missing feature JSON rows 拒絕（不再靜默 zero-fill）
- Quantile training/export/reporting 全帶 `feature_definition_hash`
- Model registry canary transition 改為 q10/q50/q90 serving trio atomic promote（一個 `(strategy, engine_mode, schema_version, train_date)` unit）
- `model_info` 拒 incomplete serving trios（不再 report lone quantile as active）
- Edge label backfill 只在 close quantity 完全覆蓋 entry quantity 時 finalize labels
- LinUCB Python trainer 改用 Rust-aligned 15-arm space + psycopg-compatible SQL placeholders
- LinUCB runtime 從 compatible `learning.linucb_state` warm-start；state missing/incompatible 時 explicit cold-start fallback
- Teacher command routing 預設不再走 Paper：
  - command sink 預設 Demo
  - disabled Paper 對 response-bearing commands 走 explicit error drain，不再靜默丟 oneshot responders
- Decision payloads 將 LinUCB metadata 標記為 `signal_observation_only` + `accepted_intent_bound=false`
- `boost_arm` 對 unsupported/invalid directive 回正確錯誤（不再 false `Applied`）
- Strategist Live metrics path 在 release mode fail-fast，直到 Live scaffold 顯式支持
- Paper auto-start 必須 `OPENCLAW_ENABLE_PAPER=1` + 解析現行 API response shapes；deploy README 不再建議透過 `ExecStartPost` 自動啟動 Paper

**Verification**：
- `py_compile` 全綠（parquet_etl / quantile_trainer / quantile_reports / run_training_pipeline / model_registry / edge_label_backfill / linucb_trainer / ml_routes）
- `bash -n helper_scripts/start_paper_trading.sh` OK
- `cargo check -p openclaw_engine` OK with existing warnings
- Bundled Python targeted suite **78 passed / 7 skipped**（parquet_etl / quantile_trainer / quantile_reports / model_registry / edge_label_backfill / linucb_trainer）
- Rust targeted：claude_teacher::strategy_ipc_impl 6 / boost_arm 3 / linucb::runtime 11 / decision_context_producer 6 / edge_predictor::features 20 / edge_predictor_ort metadata drift 1

**Residual gaps**（PM verdict 標明）：
- PostgreSQL integration coverage for model registry trio path 已更新，但仍需 `OPENCLAW_DATABASE_URL` 跑 live PG integration
- 無 full real-artifact ONNX load 跑通；ORT metadata mismatch test 驗證 runtime guard 已生效
- LinUCB boot warm-start 由 unit/helper tests + compile checks 覆蓋，未經 live engine boot smoke
- Existing Rust warnings 保留（不在 Batch F 範圍）

**Sign-off**：
- F0 prework：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_f_ml_agent_autonomy_prework.md`
- F final：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_f_ml_agent_autonomy_signoff.md`

---

## Post-deploy Healthcheck Status（採集 2026-04-29 CEST）

主修復 commit `bc3fa70` + 文檔同步 `6539e4e` + restart ownership hotfix `5db4e29` 均已 push 並 fast-forward 到 Linux `trade-core`。`restart_all.sh --rebuild --keep-auth` 已在 Linux 完成 rebuild/redeploy（需顯式 `PATH="$HOME/.cargo/bin:$PATH"`）。

**新 runtime**：
- engine PID **161957**（`openclaw-engine`）
- API master PID **162029** + 4 workers
- API `:8000` 已由新 control API venv 佔用，無 address-in-use
- watchdog `engine_alive=true`、demo snapshot fresh
- direct unauth `/openclaw/health` 與 `/api/v1/system/health` 回 401（auth enforced）
- GUI-origin API logs 200 OK
- Batch E runtime ownership pytest **10 passed**
- `bash -n` lifecycle scripts OK

**不能宣稱 full green**（最新 `passive_wait_healthcheck.sh --quiet`）：
- FAIL `[12] bb_breakout_post_deadlock_fix`
- FAIL `[22] trading_pipeline_silent_gap`（risk verdicts / DCS alive，但 fills/intents/orders stale；engine log 顯示 fee rates unavailable cold-boot fail-closed）
- WARN `[27] intents_counter_freeze`
- 暫態 `[16] strategist_cycle_fresh` 已清
- `[31] edge_diag_2_strategy_diversity` 在最新重跑未再出現

**Live pipeline gate**（依設計拒絕啟動）：
- `authorization.json` schema **v1 vs expected v2**
- 需 Operator 透過 `/api/v1/live/auth/renew` 或 renew-review 重新簽署
- **未繞過 live gate**

**剩餘 release gaps**：
- live PG integration（`OPENCLAW_DATABASE_URL` model registry trio path）
- real ONNX artifact e2e
- LinUCB live boot smoke
- `[22]` silent-gap / fee-rate cold-boot cost_gate fail-closed RCA

---

## Linear Milestone 對應（2026-04-29 operator 終版）

| Milestone | Linear ID | Batch | Findings count |
|---|---|---|---|
| Batch A — Live write boundary freeze | NCY-5 | A | 5 |
| Batch B — Critical auth/secrets/API exposure | NCY-6 | B | 14 |
| Batch C — Trading record durability | NCY-7 | C | 12 |
| Batch D — Risk/config fail-closed | NCY-8 | D | 8 |
| Batch E — Operator/runtime ownership | NCY-9 | E | 13 |
| Batch F — ML/agent autonomy readiness | NCY-10 | F | 10 |
| **Total** | | | **62** |

Linear project：[OpenClaw 62-Finding Remediation](https://linear.app/ncyu/project/openclaw-62-finding-remediation-de1bc8f68e42)

---

## 備註

- 本檔案僅做「TODO.md 頭部敘述歸檔」用途，不改動代碼、不改動 tracking ledger、不改動 sign-off 報告
- 進一步細節請查 sign-off 報告原文 + `docs/audit/remediation_tracking.md`
- TODO.md 將以一行索引指向本檔
