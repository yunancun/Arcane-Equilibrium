# helper_scripts/ — 腳本索引 (Script Index)

本目錄存放 OpenClaw 系統的維護、啟動、CI 輔助腳本。
最後更新：2026-05-27（P0-OPS-4 GAP-D Track A round 2 — 新增 `canary/healthchecks/check_pg_dump_freshness.py` Python 主入口 7-check（5 verify_pg_dump.sh + L0 schema coverage + governance audit trail） + wire `passive_wait_healthcheck/checks_cron_heartbeat.py` 加 `check_80_pg_dump_freshness()` wrapper；E1 IMPL DONE 待 E2 sign-off。同日保留 P0-OPS-1 HTTPS Track A IMPL + P0-OPS-4 first-day-live runbook GAP A + GAP F IMPL 索引 + 2026-05-25 Sprint 2 W2-F NEW QA-2 AC-19 ALT bucket cron + W2-B Alpha Tournament scaffold + Hygiene Option E Phase 1 Step 2 + 2026-05-23 Sprint 5+ Wave 1 §4.4 production hardening + 2026-05-20 P0-ENGINE-HALTSESSION-STUCK-FIX 索引）

## 2026-05-27 P0-OPS-4 GAP-D PG dump cron + healthcheck IMPL

| 腳本 | 用途 |
|------|------|
| `cron/install_pg_dump_cron.sh` | round 1 — `crontab -l` idempotent installer for `trading_ai_pg_dump_cron.sh`；Linux only；偵測 existing entry 避重複；`--dry-run` 預覽。對齊 PA spec §10 GAP-D + MIT empirical report §1.7 Phase 1 plan A（local-only）。 |
| `cron/trading_ai_pg_dump_cron.sh` | round 1 — daily 03:00 UTC PG `-Fc` dump wrapper：EXCLUDE `learning.decision_features_evaluations`（182GB / 17d / 無 retention）+ `*_damaged_*` quarantine 表；retention 30d；完成/失敗均 INSERT `learning.governance_audit_log` event_type `pg_dump_completed` / `pg_dump_failed`（V113 CHECK enum 補登 26-value）。Linux only；lock dir 防 overrun；cron heartbeat sentinel start-time touch `${OPENCLAW_DATA_DIR}/cron_heartbeat/trading_ai_pg_dump.last_fire`。 |
| `cron/verify_pg_dump.sh` | round 1 — Bash sidecar 5-check：backup dir / latest dump mtime < 26h / size > 1MB / md5 對齊 JSONL entry / retention prune 生效。operator SSH ad-hoc 場景下不需 venv 快速跑 14-step drill；Python 版 `check_pg_dump_freshness.py` 才是 healthcheck pipeline 主要入口。 |
| `canary/healthchecks/check_pg_dump_freshness.py` | round 2 — Python 主入口 7-check standalone（FA acceptance §E #7）：5 個對齊 `verify_pg_dump.sh` + 第 6 個 L0 schema coverage smoke（subprocess `pg_restore --list <latest> \| grep earn_movement_log` per FA §C.5）+ 第 7 個 governance_audit_log audit trail（last `pg_dump_completed` ts < 26h）。V113 未 apply / cron 未 fire → INSUFFICIENT_SAMPLE-skip fail-soft。stdlib + psycopg2 only；Linux only（`sys.platform` guard）。被 `passive_wait_healthcheck.checks_cron_heartbeat.check_80_pg_dump_freshness()` wrapper 引用。對齊 [80] healthcheck slot；JSON 輸出 + exit 0/1/2 對齊 `_common.py` 慣例。 |

## 2026-05-27 P0-OPS-1 HTTPS / Secure cookie / CSRF / CSP Track A IMPL

| 腳本 | 用途 |
|------|------|
| `lib/tls_cert.sh` | OPS-1 Track A — 跨平台 Tailscale cert 路徑與 renewal helper：`resolve_openclaw_tls_cert_dir`（Linux `/var/lib/tailscale/certs` / Darwin `$HOME/Library/Application Support/Tailscale/certs`）、`resolve_openclaw_tls_cert_host`（讀 env 或 `tailscale status --json`）、`tls_cert_days_remaining`（openssl + 跨平台 date）、`tls_cert_should_renew`（< 14d threshold）。被 install_caddy.sh + systemd unit 共用。 |
| `Caddyfile.template` | OPS-1 Track A — Caddy 反向代理設定模板。`envsubst` 處理：HTTPS bind tailnet IPv4 + Tailscale cert + reverse_proxy `127.0.0.1:8000` + X-Forwarded-Proto 傳遞。`admin off` 不暴露 :2019。HSTS header 在反代邊界加。 |
| `install_caddy.sh` | OPS-1 Track A — 一次性 Linux/macOS 部署：preflight Tailscale + 安裝 Caddy + envsubst 生 Caddyfile + `tailscale cert` 首次拉證書 + 安裝 systemd unit/timer + curl 驗證 + 首次 HTTPS cert trust checkpoint 提示。預設 `--dry-run`；`--apply` 才實際寫 `/etc/caddy/Caddyfile`。跨平台分支 (Linux apt / macOS brew + launchd 指引)。 |
| `canary/healthchecks/csrf_shadow_zero_verify.sh` | OPS-1 enforcing cutover gate — 掃描 `${OPENCLAW_DATA_DIR:-/tmp/openclaw}` 近 7d API/log JSONL 中 `csrf_shadow:` violation；0 → PASS，>0 → FAIL，無可掃 log → INSUFFICIENT_SAMPLE。用於 `OPENCLAW_CSRF_SHADOW=1` shadow soak 後 unset 前的自動化檢查。 |
| `systemd/openclaw-caddy.service` | OPS-1 Track A — Caddy reverse proxy systemd unit（`Type=notify` + `Restart=always` 5s 復活 + `CAP_NET_BIND_SERVICE` 不需 root 綁 443）。 |
| `systemd/openclaw-tls-renew.service` | OPS-1 Track A — Tailscale cert renewal `Type=oneshot`，由 sibling timer 觸發。引用 `lib/tls_cert.sh` 走 14d threshold 判定 + 拉新 cert + chown caddy + `systemctl reload openclaw-caddy.service`。`OnFailure=` 接 notify service。 |
| `systemd/openclaw-tls-renew.timer` | OPS-1 Track A — 每日 03:00 UTC `OnCalendar` 觸發 renew service。`Persistent=true` 機器關機跨午夜後補跑。 |
| `systemd/openclaw-tls-renew-notify.service` | OPS-1 Track A — renewal 失敗 hook（`OnFailure=` 才被拉起，**不可 enable**）。占位實作寫 stderr + journal；接 Telegram/Grafana 待 operator 提供接點。 |

## 2026-05-27 P0-OPS-4 GAP A + GAP F systemd unit IMPL

| 腳本 | 用途 |
|------|------|
| `systemd/openclaw-engine.service` | GAP F — Linux systemd unit for Rust openclaw-engine 主進程；Restart=on-failure + RestartSec=10 + StartLimitBurst=5 / 5min；PreStart 三檢（binary / ipc_secret / database_url file）；EnvironmentFile 載 basic_system_services.env；對應 macOS launchd `deploy/com.openclaw.engine.plist`。占位符 `__ENGINE_USER__ / __OPENCLAW_BASE_DIR__ / __OPENCLAW_DATA_DIR__ / __OPENCLAW_SECRETS_ROOT__` 由 install script sed 替換。 |
| `systemd/openclaw-watchdog.service` | GAP A — Linux systemd unit for engine_watchdog.py；Restart=always + RestartSec=10 + StartLimitBurst=10 / 10min；CLI args 對齊 restart_all.sh:226（--stale-threshold 45 / --grace-period 120 / --poll-interval 1）；解決 watchdog 自 crash 後無自動 respawn 的 RTO 鏈缺口（< 1min）。 |
| `systemd/install_engine_service.sh` | Linux-only installer for openclaw-engine.service；root + Linux guard；sed 替換 5 占位符；atomic mv + occupy-check + systemd-analyze verify + daemon-reload；install 後不自動啟動（留 operator 5-gate launch sequence）。 |
| `systemd/install_watchdog_service.sh` | Linux-only installer for openclaw-watchdog.service；自動偵測 python venv (PYTHON_BIN env > $HOME/.venv/bin/python3 > /usr/bin/python3)；sed 替換 6 占位符；同 root + Linux + daemon-reload pattern。 |
| `systemd/README.md` | systemd unit 部署文件：跨平台 portability / operator deploy 三段 hand-action checklist (A install / B enable+start / C restart_all.sh 共存) / RTO ≤ 5min 4-step 驗證 SOP（含 SIGKILL 模擬 + systemctl poll + snapshot age 恢復驗證）/ 反模式 / cross-reference spec。 |


## 2026-05-25 Sprint 2 W2-F NEW QA-2 AC-19 ALT bucket cron IMPL

| 腳本 | 用途 |
|------|------|
| `cron/ac19_alt_bucket_daily_query.sql` | AC-19 14d 監測 daily SQL：post-deploy window 5/19~6/2 + bucket-split (large_cap=BTC/ETH / alt=其它 15 symbol) + Wilson CI 95% lower/upper bound + 3 級 verdict (PASS / MARGINAL / FAIL / INSUFFICIENT_DATA)；psql --csv -f 直接跑。per W1-G SOP §2 canonical。 |
| `cron/ac19_alt_bucket_daily_cron.sh` | Daily 08:00 UTC cron wrapper：讀 secrets env file 取 PG creds → psql --csv 跑 SQL 寫 CSV → ac19_alt_bucket_jsonl_writer.py 將結果 append 到 14d 累積 JSONL summary + heartbeat sentinel + lock mkdir 防 overrun + day_index>14 idempotent skip。Exit code 對齊 verdict 聚合（0/1/2）。 |
| `cron/ac19_alt_bucket_jsonl_writer.py` | CSV → JSONL append + sanity verify：解析 psql --csv 輸出 / 重算 Wilson lower/upper（防 SQL ↔ Python 漂移；超過 1pp tolerance 寫 sanity_drift_pct）/ 重判 verdict / append-only fsync 寫累積 summary。stdlib only（無 psycopg2）。 |
| `cron/tests/__init__.py` | 測試 package marker。 |
| `cron/tests/test_ac19_alt_bucket_daily.py` | 44 pytest case：Wilson formula 5 case（大型/小樣本/邊界/完美 fills/fail-loud）/ 3 級 verdict 13 case（large_cap+alt 閾值 inclusive 邊界 + INSUFFICIENT_DATA + unknown bucket fail-loud）/ bucket 分類 3 case / day_index 5 case（day 1 / day 7 SOP baseline / day 8 cron target / day 14 邊界 / naive datetime）/ CSV 解析 4 case（兩 row / psql trailing line / 空 / malformed fail-loud）/ JSONL 構造 3 case（baseline 對齊 / sanity drift / INSUFFICIENT_DATA）/ append 2 case（新建 / 既存保留）/ exit code 聚合 5 case / CLI dry-run 2 case。 |

## 2026-05-25 Sprint 2 W2-B Alpha Tournament Stream A scaffold

| 腳本 | 用途 |
|------|------|
| `alpha_tournament/__init__.py` | helper package entry + MODULE_NOTE；標註 ADR-0026 track='direct_exploit' + V100/V103 actual schema + engine_mode IN ('demo','live_demo') hard invariants；read-only SELECT only。 |
| `alpha_tournament/attribution_daily.py` | Sprint 2 daily cron @02:30 UTC fire；14d demo bucket-split per strategy × symbol × date + Wilson CI 95% lower bound projection + Bonferroni K=2 alpha 調整 + sample size cumulative projection (target ≥ 30 per CR-6)；stdout JSON log；dry-run mode 不連 PG（驗 module import + SQL syntax）。 |
| `alpha_tournament/tournament_orchestrator.py` | Sprint 2 stub return 0；Sprint 3+ M11 counterfactual replay integration + candidate ranking 邏輯接續入口。 |
| `alpha_tournament/14d_bucket_split.sql` | psql -f 直接跑的 standalone SQL；對映 attribution_daily.py SQL 內嵌版本，供 cron wrapper / 手動 audit 使用。WHERE track = 'direct_exploit' + engine_mode IN ('demo','live_demo') + attribution_chain_ok = TRUE 三 invariant hard-coded。 |

## 2026-05-23 Sprint 5+ Wave 1 §4.4 production hardening

| 腳本 | 用途 |
|------|------|
| `db/health_60s_boundary_verify.sh` | Sprint 5+ Wave 1 §4.4.2 — REST latency 60s rolling window boundary verify SOP wrapper；對齊 passive_wait_healthcheck.sh 範式（venv-aware + secrets load + container psql）；3 SQL section（sample inter-arrival ±2s jitter / samples_per_min duplicate emit / 30min summary row_count ≥25）；exit 0/1/2 PASS/FAIL/DB-error。code-level 60s expire 已 verified（bybit_rest_client.rs:318-441 lazy expire `now.checked_sub(60s) → retain`）；本 wrapper 補 production runtime empirical verify（emitter scheduler tokio tick / task crash 等 runtime 失準路徑）。 |
| `db/health_60s_boundary_verify.sql` | Sprint 5+ Wave 1 §4.4.2 — pure SQL 配套；3 section LIMIT 20+30+per-metric；只覆蓋 api_latency + engine_runtime（60s emitter tick 對齊範疇）；不含 risk_envelope (300s) / pipeline_throughput (30s)。 |
| `db/health_f2_sanitize_monitor.sh` | Sprint 5+ Wave 1 §4.4.3 — F-2 NaN/inf sanitize fire log 監測；DISABLED-BY-DEFAULT 直到 Sprint 5+ §4.2.2 wireup PaperState SSOT 後 enable（Sprint 4+ Wave B placeholder 階段 F-2 fire 必 0，過早 enable 等同永遠 PASS）；grep-based 而非 PG-based（F-2 sanitize 在 in-process tracing::warn 觸發不寫 V106；engine.log 為唯一 SSOT）；cross-platform date (GNU `-d` / BSD `-v`)；OPENCLAW_F2_THRESHOLD=0 default = 任一 fire 即 alert。 |
| `db/ac1b_monthly_healthcheck.sh` | Sprint 5+ Wave 1 §4.4.4 — Sprint 4+ §4.1.4 AC-1b production verify monthly cron；對齊 Sprint 4+ Phase 3c 驗範式（30 min × 6 active domain × ≥5 row）；對齊 passive_wait_healthcheck.sh 範式（secrets load + container psql + sentinel mtime touch）；crontab spec `30 3 1 * *` 月初 03:30 UTC（避撞 passive_wait_healthcheck 6h cron）；exit 1 表 ≥1 domain < 5 row；對齊 operator Stage F §8.6 PM phase 3e 拍板「§4.4 全部進 hardening + AC-1b monthly cron」。 |

## 2026-05-20 P0-ENGINE-HALTSESSION-STUCK-FIX Layer B

| 腳本 | 用途 |
|------|------|
| `canary/engine_watchdog.py` | Layer B（spec v0.2 §4）擴增：新增 TRADING_INERT_PROLONGED 業務心跳探測；獨立於 ENGINE_CRASH 路徑（severity=WARNING，不重啟 engine）；trigger conditions = paper_paused 持續超 threshold OR recent_intents 滾動窗口無增長；per-engine 獨立 state；cooldown 防 alarm spam；TRADING_INERT_CLEARED transition log；in-memory + on-disk state（spec B-5：watchdog restart 不重置 incident）；CLI 加 `--disable-inert-probe` / `--inert-probe-config` 兩 flag。 |
| `canary/watchdog_inert_probe.toml` | Layer B per-env threshold 配置：demo=60min/20min（學習資料源 / grid-dominant aware）、live_demo=30min/15min（中間嚴格）、live=15min/10min（最敏感）、paper=demo defaults（dormant default）。fail-loud RAISE on TOML parse error；缺檔 fallback 預設值。 |
| `canary/test_engine_watchdog.py` | Layer B 32 unit tests：resolve_engine_label / load_inert_probe_config / detect_paper_paused_stuck / detect_intents_zero_delta / evaluate_inert_probe / state persistence / run_inert_probe_once；spec B-1/B-1a/B-2/B-3/B-4/B-5/B-7 全覆蓋。Mac unittest + pytest 32/32 PASS。 |

## 2026-05-20 P0-ENGINE-HALTSESSION-STUCK-FIX Layer A Round 2

| 腳本 | 用途 |
|------|------|
| `canary/halt_audit_pg_writer.py` | MUST-FIX-3：tail Rust engine 寫的 `halt_audit.log` JSONL → INSERT `learning.governance_audit_log`（V098 24-value allowlist 已含 3 個 halt_session_* event_types）；按 spec §3.8 / §3.9 audit contract；ON CONFLICT pattern 冪等（複合 dedup = process_pid + ts_ms + event）；cursor state file 保證重啟不丟資料 + 不重複；jsonschema validate fail-soft；20 unit tests PASS + Linux PG integration 3 rows + idempotent 已驗。 |
| `cron/halt_audit_pg_writer_cron.sh` | MUST-FIX-3：1min cron wrapper；對齊 sibling pattern（outcome_backfiller_live_cron）；env 從 `$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env` 讀；mkdir-based lock 防 overrun；source-only（operator 確認 V098 已 land 後手動 crontab -e 加）。 |
| `canary/test_halt_audit_pg_writer.py` | MUST-FIX-3 unit + PG mock 整合測試：5 大類 17 + 3 = 20 cases；JSONL robust parser、cursor state、validate、resolve paths、PG-absent / 3-rows / idempotent / V098-absent fallback 全覆蓋。 |

## 2026-05-09 W-AUDIT-1 補登

| 腳本 | 用途 |
|------|------|
| `db/audit/2026-05-09_3c_7d_audit.sh` | 3C deploy 7d follow-up read-only audit wrapper |
| `db/audit/2026-05-09_3c_7d_audit.py` | 3C deploy 7d follow-up SQL audit implementation |
| `db/audit/2026-05-16_funding_arb_14d_audit.sh` | funding_arb 14d audit wrapper |
| `db/audit/2026-05-16_funding_arb_14d_audit.py` | funding_arb 14d audit SQL implementation |
| `db/passive_wait_healthcheck/__main__.py` | `python -m helper_scripts.db.passive_wait_healthcheck` entrypoint |
| `db/passive_wait_healthcheck/runner.py` | Passive healthcheck orchestrator and output formatter |
| `db/passive_wait_healthcheck/checks_agent_spine.py` | `[55]` Agent Decision Spine lineage / MAG-082 readiness check |
| `db/passive_wait_healthcheck/checks_live_pipeline.py` | `[56]` Live / LiveDemo pipeline active healthcheck |
| `db/passive_wait_healthcheck/checks_btc_lead_lag.py` | `[57]` W2 A4-C BTC→Alt Lead-Lag panel 4 conditions healthcheck (W2-IMPL-3 2026-05-11) — panel freshness < 120s + cohort=7 + regime extreme < 5% + book_imbalance non-zero/non-null; opt-in `OPENCLAW_W2_HEALTHCHECK_ENABLED=1` |
| `db/passive_wait_healthcheck/checks_feature_baseline.py` | `[67]` W-AUDIT-4b feature_baselines readiness: active rows >0 + 34-dim feature vector contract |
| `db/passive_wait_healthcheck/checks_openclaw_gateway.py` | `[54]` OpenClaw proposal relay healthcheck |
| `db/passive_wait_healthcheck/checks_scanner_market.py` | `[41]` scanner would-block evidence and `[51]` opportunity shadow checks |
| `cron/ref21_market_microstructure_recorder.py` | REF-21 local BBO/orderbook/latency recorder |
| `cron/ref21_market_recorder_retention.py` | REF-21 recorder retention maintenance |
| `cron/ref21_symbol_universe_snapshot_cron.sh` | REF-21 V058 symbol universe snapshot cron |
| `operator/edge_p2_flip.sh` | Operator helper for Edge P2 guarded flip |
| `operator/edge_p2_revert.sh` | Operator helper for Edge P2 revert |
| `operator/generate_replay_signing_key.sh` | Replay signing key generation helper |
| `bybit/liquidation_topic_probe.py` | W-AUDIT-8a C1 standalone public WS probe；isolated connection checks `allLiquidation.{symbol}` plus canary market topics and writes latest+dated reports under `$OPENCLAW_DATA_DIR/audit/liquidation_topic_probe/`。Short smoke is not C1 proof；24h PASS + BB/MIT sign-off required before production topic revival。 |
| `research/bb_breakout_threshold_sweep.py` | bb_breakout threshold research sweep |
| `research/ma_crossover_counterfactual_replay.py` | ma_crossover counterfactual replay research helper |
| `research/shadow_disagreement_breakdown.py` | Shadow disagreement breakdown analysis |
| `reports/w2_paper_edge_report.py` | W2 A4-C BTC→Alt Lead-Lag — legacy thin CLI shim；保留舊入口相容，委派至 `reports/w2/w2_paper_edge_report.py`；AMD-2026-05-15-01 後不產 promotion evidence。 |
| `reports/w2/w2_paper_edge_report.py` | W2 A4-C BTC→Alt Lead-Lag — Stage 0R diagnostic report CLI (read-only PG query + metrics→render orchestration)，只輸出 `eligible_for_demo_canary=true/false`。配 `sql/queries/w2_btc_alt_lead_lag_counterfactual.sql`。 |
| `reports/w2/w2_paper_edge_metrics.py` | W2 spec v1.2 §7.1 6 mandatory metric 計算層：PSR(0) Bailey-LdP 2012、DSR K=95、block-bootstrap CI、R²(N)、counterfactual delta、Stage 0R diagnostic verdict。 |
| `reports/w2/w2_paper_edge_render.py` | W2 Stage 0R diagnostic report 展現層：`render_markdown` / `render_csv` / `render_json` / `per_symbol_breakdown_table`。 |
| `reports/w2/w2_paper_edge_smoke.py` | W2 Stage 0R diagnostic smoke：3 mock case (plus15/plus5_15/minus5) 不連 PG，可獨立執行。 |
| `reports/w_audit_8c_liquidation_cluster_stage0r.py` | W-AUDIT-8c Liquidation Cluster Reaction — Stage 0R replay 頂層 CLI wrapper（mirror sibling 8b shim 模式），委派至 `reports/w_audit_8c/liquidation_cluster_stage0r_report.py`。配 `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`。BB pre-flight gate 預設 True（2026-05-18 BB STRUCTURAL verdict 後）；spec v0.3 mandatory report fields + 4-agent (QC/MIT/FA/BB) review-ready Markdown + JSON。 |
| `reports/w_audit_8c/liquidation_cluster_stage0r_report.py` | W-AUDIT-8c Stage 0R 報告編排層（round 2 rework）：read-only PG 取數（fetch_panel_symbols + fetch_k_prior + _fetch_panel_rows with bucket_end_ts → bucket_end_ts_ms normalize）→ sibling 8C-S0R-2 `liquidation_cluster_stage0r_metrics` (compute_stage0r / compute_stage0r_sweep 真實 contract — dict 6 keys 含 sweep_cells/eligible_for_demo_canary_per_tier) → spec v0.3 14 mandatory fields JSON + 4-agent review-ready Markdown；落地至 `docs/CCAgentWorkSpace/{role}/workspace/reports/<date>--w_audit_8c_stage0r_<verdict>.{json,md}`。BB pre-flight gate fail-fast 不存在 BB STRUCTURAL report 即 exit 3。 |
| `reports/w_audit_8c/liquidation_cluster_stage0r_smoke_cli.py` | W-AUDIT-8c Stage 0R CLI 整合 smoke（round 2 sign-off invariant）：10 test 覆蓋 6 CRIT (1-6) + 4 HIGH (1,2,3,4) 修法，mock SQL panel → verify _extract_trigger_rows n>0 + sweep returns dict + Markdown 15 sections + 5 exclusion categories；不連 PG，可獨立執行。 |
| `deploy/launchd_preflight.sh` | macOS launchd deployment preflight |
| `db/passive_wait_healthcheck/checks_cron_heartbeat.py` | `[75]`-`[79]` P1-CRON-INSTALL-WAVE-1（2026-05-18）— 5 個 cron wrapper 已 source/test closed 但 crontab 尚未 install；以 sentinel mtime 推斷 cron 是否按時 fire。WARN-by-default；`OPENCLAW_CRON_HEARTBEAT_REQUIRED=1` 升 FAIL。配對 install recipe `docs/execution_plan/2026-05-18--p1_cron_install_wave_1_install_recipe.md`。 |
| `db/test_cron_heartbeat_healthchecks.py` | `[75]`-`[79]` 單元測試（42 PASS）：fresh/missing/stale + threshold 邊界 + REQUIRED=1 升 FAIL + path 解析（HEARTBEAT_DIR > DATA_DIR）。 |
| `security/compute_sri_hashes.sh` | P2-WP05-CSP-UNSAFE-INLINE（2026-05-18）— 為 GUI pinned CDN 計算 SHA-384 SRI integrity attribute；操作者跑一次將輸出 paste 進對應 `app/static/*.html` <script> / <link>。default URL = `lightweight-charts@4.1.0`；版本未 pin → WARNING + exit 1。 |

## Sprint 1A-ζ Track C M11 spike (sandbox only / 非 nightly cron)

> 2026-05-22 PA reconcile §3:此 3 條 entry 對應 `helper_scripts/replay/m11_spike/` IMPL reality;CLAUDE.md §七「新腳本必須更新 SCRIPT_INDEX.md」合規 closure。

| 腳本 | 用途 |
|------|------|
| `replay/m11_spike/spike_trigger.py` | Sprint 1A-ζ Track C 手動 1 次 trigger M11 replay (skeleton, 非 nightly cron)。scope 限 1 strategy × 1 symbol × 1 day, 接 `trading_ai_sandbox` PG 寫 V107 row (engine_mode='replay')。round 2 後正式 import sibling detector + 落地 baseline_5d_mean / sigma / noise_floor_threshold；default `--user sandbox_admin` (per Phase 0 §2.2;Phase 2 defer 時 fallback `--user trading_admin`)。**sandbox only**;production DB 物理拒絕 (pg_database 不含 'sandbox' substring → sys.exit(2))。 |
| `replay/m11_spike/divergence_d1_fill_chain.py` | D1 fill_chain divergence detector module (per M11 design spec §4.2 D1)。提供 `compute_5d_baseline` / `detect_with_baseline` / `leak_free_shift1_replay` / `inject_synthetic_fixture` 4 函數；caller = `spike_trigger.py`。落實 AC-7 leak-free shift(1) mandate (per feedback_indicator_lookahead_bias)。D1 only;D2-D7 不在 spike scope。 |
| `replay/m11_spike/dedup_contract_test.py` | AC-6 M11 → M7 dedup contract empirical verify。5+1 condition (round 2 LOW-1 拆 c1a/c1b + HIGH-1 新增 c5)：V107 row 存在 + flag=m7_decay_candidate + decay_signals 0 row + strategy_lifecycle 0 row + 6 forbidden column 0 hit + Guard A forbidden column reverse fire empirical。Cleanup ADD/DROP COLUMN 自包含, sandbox state 不殘留。 |

## REF-20 Sprint 1+2 新增 cron 與 helper

| 腳本 | 用途 |
|------|------|
| `cron/replay_key_rotation_check.sh` | REF-20 Wave 2 P2a-S1：90d signing key 輪替檢查（fingerprint align） |
| `cron/replay_key_archive_cleanup.py` | REF-20 Wave 2 P2a-S1：180d archive 清理 |
| `cron/replay_artifact_prune.py` | REF-20 Wave 3 P2a-S5：6h cron 跑 manifest quota 清理 |
| `cron/wave9_replay_no_live_mutation_watch.sh` | REF-20 Wave 9：每小時 cron 檢 trading.* WHERE source LIKE 'replay_%' = 0 |
| `cron/wave9_business_kpi_collector.py` | REF-20 Wave 9：每天 06:00 cron 採集 V047 business_kpi_snapshots（**2026-05-03 真實狀態**：Mac mock mode 跑過，Linux 真實 PG 0 跑 → 待 Sprint 3 deploy） |
| `cron/wave9_audit_incident_scan.py` | REF-20 Wave 9：每天 06:30 cron 掃 V048 audit_incident_summaries（同 Linux 0 跑） |
| `db/passive_wait_healthcheck/checks_governance.py::check_44_replay_manifest_key_presence` | REF-20 Sprint 1 Track B：replay manifest key.hex 存在性監測（V042 archive land 前 fallback 監測） |

---

## 頂層腳本 (Top-Level Scripts)

### 生命週期 (Lifecycle)

| 腳本 | 用途 |
|------|------|
| `restart_all.sh` | **輕量重啟**：停+啟 Rust 引擎 + API server（不動數據）。旗標：`--engine-only` / `--api-only` 限定範圍；`--rebuild` 先重建 openclaw-engine binary 再啟動（PYO3-ELIMINATE-1 Phase 3 後無 PyO3 wheel）；`--require-clean-build-window`（2026-05-25 Hygiene Option E Phase 1 Step 2）重啟前 fail-closed 檢查系統是否仍有 `cargo build`/`cargo test` 在跑,防 multi-session race 覆蓋 release binary inode;一般 operator 不直接帶,由 `build_then_restart_atomic.sh` 串接時自動帶入。**OPS-2 SECRET-SPLIT 2026-05-27 Phase 1**：`prepare_runtime_secret_files` 自動 seed `live_auth_signing_key.txt` 自 `ipc_secret.txt`（`[ ! -f ]` 條件嚴，已 rotate 之 key 不被覆蓋）+ engine/API spawn 注入 `OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE`；Rust + Python `_read_live_auth_signing_key` 提供 Phase 1 fallback，rate-limit WARN ≤1/h。 |
| `build_then_restart_atomic.sh` | **2026-05-25 Hygiene Option E Phase 1 Step 2**（per PA sub-agent a6326f17 hygiene 修法 Option B + memory `project_multi_session_memory_race`）：原子化 build → SHA snapshot → restart → verify deploy 鏈。flock(`$OPENCLAW_DATA_DIR/build_window.lock`) 持有 build window 期間禁第二 cargo;結束 verify `/proc/$PID/exe` SHA == on-disk binary SHA;任何 phase 失敗即 abort,杜絕「`cargo test --release` incremental rebuild 在 engine startup 後覆蓋 inode」的 multi-session race。Mac 無 procfs 則 fallback 驗 disk SHA 不被偷換。預期 operator 下次 deploy 跑 `bash helper_scripts/build_then_restart_atomic.sh` 一鍵完成。 |
| `stop_all.sh` | **優雅停止**：停引擎 + 建立 `engine_maintenance.flag`，讓 `engine_watchdog.py` 不自動重啟。`--engine-only` / `--api-only`。移除 flag: `rm /tmp/openclaw/engine_maintenance.flag` 或跑 `restart_all.sh`。 |
| `clean_restart.sh` | **交易所層重啟**：停引擎 → httpx BybitClient flatten demo/live 倉位 → 歸檔 runtime 文件（**不動 paper_state，不動 DB**）→ 檢查 binary 新舊 → 重建/重啟 → watchdog 驗證。輕度重置，保留歷史累計。旗標：`--yes` / `--mark-damaged`（歸檔 DB 交易表）/ `--include-live` / `--skip-flatten` / `--skip-build-check` |
| `fresh_start.sh` | **完整 DB 重置重啟**（2026-04-15 新增）：在 clean_restart 基礎上額外清空所有 PnL / 手續費 / 勝率 / 經驗數據（透過 `fresh_start_reset.py`）讓引擎從零歷史冷啟動。**保留**：市場數據（klines/funding/OI/LSR/liquidations/regime/news）、model_registry、linucb_state_archive、features.versions、ai_budget_config。**摧毀**：fills/intents/orders/outcomes/signals/agent 活動/學習狀態。旗標：`--yes` / `--include-live` / `--skip-flatten` / `--skip-build-check` |
| `lib/api_bind_host.sh` | Trading API bind host resolver：默認 auto 綁定 Tailscale IPv4（可用時）或 loopback；拒絕 `0.0.0.0` / `::`，供 restart/clean/fresh lifecycle scripts 共用。 |
| `start_paper_trading.sh` | Archive/diagnostic Paper runtime hook；不得接 systemd / cron 常規自動啟動或 promotion evidence |
| `mac_bootstrap.sh` | **macOS 冷裝引導**（Linux→Mac 遷移，2026-04-20 新增）：三段式獨立旗標 `--check`（診斷已裝/未裝，不動手）/ `--install-deps`（brew + rustup + Python venv + pip install）/ `--init-runtime`（建 `$OPENCLAW_DATA_DIR` + 清舊 socket + 寫 .zshrc env 段）。可選 `--no-ollama` / `--no-postgres` / `--all`。Linux 執行會被 platform guard 擋下。搭配 `docs/references/2026-04-20--cross_platform_redeploy_dependencies.md`。 |

### 平倉 (Flatten)

| 腳本 | 用途 |
|------|------|
| `clean_restart_flatten.py` | 交易所平倉助手（被 clean_restart.sh / fresh_start.sh 調用；亦可獨立 `--env demo\|mainnet [--dry-run]`）。PYO3-ELIMINATE-1 Phase 2 後改用 httpx BybitClient — 先 `refresh_instruments` 載入品種規格，再對每倉下 reduce_only 市價單 + 取消所有未成交單；5 輪 verify 循環掃殘尾 |

### 定時任務 / CI (Cron & CI)

| 腳本 | 用途 |
|------|------|
| `cron_daily_report.sh` | 每日自動採集 Paper Trading 指標 + Telegram 推送（Cron UTC 0:00） |
| `cron_observer_cycle.sh` | 每 5 分鐘執行 Observer 循環 + runtime snapshot 橋接 |
| `cron/ml_training_maintenance.py` | W-AUDIT-4 F-08 ML maintenance runner：covers operational MLDE jobs plus original audit targets `thompson_sampling` / `optuna_optimizer` / `cpcv_validator` / `dl3_foundation` / `weekly_report_generator`; source runner only, runtime crontab install requires operator authorization. |
| `cron/ml_training_maintenance_cron.sh` | F-08 cron wrapper around `ml_training_maintenance.py`; loads PG env, writes status JSON/log, uses lock dir, and does not install itself. |
| `cron/feature_baseline_writer_cron.sh` | W-AUDIT-4b cron wrapper around Rust `feature_baseline_writer`; uses `OPENCLAW_FEATURE_BASELINE_APPLY=1` env gate, no CLI apply/force flags, then runs `[67]` healthcheck. |
| `schema_diff.py` | CI 類型一致性：比對 Python shared_types vs Rust golden JSON schema |
| `golden_dataset_gen.py` | Rust↔Python 指標交叉驗證黃金數據集（確定性 OHLCV + 13 指標） |

## db/ — 數據庫維護 (Database Maintenance)

| 腳本 | 用途 |
|------|------|
| `db/fresh_start_reset.py` | 開發噪音清理：保留客觀市場數據，清除系統經驗數據。支援 `--report-only`（默認）/ `--dry-run` / `--execute --confirm "FRESH_START_YYYY_MM_DD"`。通常透過 `fresh_start.sh` 調用（一併停引擎/歸檔/重啟），獨立使用需自行停引擎。 |
| `db/canary_promote_cron.sh` | G4-03 Phase B canary auto-promote cron wrapper。默認 dry-run/read-only；apply 需 `OPENCLAW_CANARY_CRON_APPLY=1` + `OPENCLAW_AUTO_PROMOTE_ENABLED=1`。可選 `OPENCLAW_CANARY_EMIT_SIGHUP=1` + `OPENCLAW_ENGINE_PID_FILE` 在 applied promoting→production 後 SIGHUP engine。 |
| `db/feature_baseline_healthcheck.py` | Standalone `[67]` W-AUDIT-4b feature_baselines readiness check; used by `cron/feature_baseline_writer_cron.sh` after apply. |
| `db/counterfactual_exit_replay.py` | EDGE-DIAG-1 #3 反事實退場回放：READ-ONLY SELECT `learning.exit_features` 最近 N 天，模擬「peak − k × ATR 鎖利」net vs 實際 net。旗標：`--days N`（>0）/ `--cost-model {proxy,fee_only,both}`（default both；proxy 代數退化保留作透明度核驗、fee_only 為經驗有效模型）/ `--fee-bps-per-side 5.5`（Bybit taker default）/ `--include-funding-arb`（預設排除 funding_arb，含 funding payment 失真）/ `--engine-mode`（default demo,live_demo）/ `--cf-multiplier 0.3`（v2 asymptotic floor 線性近似）。產 stdout 雙表 + VERDICT + `$OPENCLAW_DATA_DIR/audit/counterfactual_exit_replay_latest.json` + dated sibling。**v1 Gate-4-only 線性 k=0.3；v2 non-linear + Gate 1/2/3 parity FUP**。 |
| `db/counterfactual_daily_cron.sh` | EDGE-DIAG-1 Phase 4 daily refresh wrapper：crontab 每日 06:00 UTC 呼叫 `counterfactual_exit_replay.py --days 2 --v2-parity --split-window --cost-model fee_only --bootstrap-ci --per-strategy-median --trimmed-mean-pct 5` 刷新 latest JSON，讓 `passive_wait_healthcheck.py [11]` 可讀到當日最新 post-P013-clean 樣本數。WRITE 端（刷 JSON）+ READ 端 check[11] 分離。載入 `$SECRETS_ROOT/environment_files/basic_system_services.env` POSTGRES_*、activate `$HOME/.venv`、log tee `$OPENCLAW_DATA_DIR/audit/counterfactual_daily_cron.log`；PIPESTATUS[0] 透傳 python 退出碼。CLAUDE.md §七「被動等待 TODO 必附 healthcheck」Phase 3 延後的 gate 守衛。 |
| `db/audit/blocked_symbols_7d_counterfactual.py` | P2-AUDIT-VERIFY-5 blocked-symbol freeze audit：READ-ONLY SELECT `trading.fills` + `trading.risk_verdicts` for cells frozen in `docs/governance_dev/strategy_blocked_symbols_freeze.json`，輸出 7d observed fill PnL、blocked rejection count、`decision_outcomes` counterfactual coverage；若 rejected rows 沒有 outcome labels，明確標 `no_rejected_outcome_labels`，不偽造 would-have-traded PnL。 |

## ci/ — CI 稽核腳本 (CI Audit)

> **2026-05-03 新增**（REF-20 Wave 3 R20-P2b-S10）：跨平台（macOS 主 / Linux 次）`replay_runner` binary symbol 稽核。L3 縱深防禦（L1=Cargo feature gate / L2=ReplayProfile::Isolated runtime / L3=本目錄 nm grep）。
> **2026-05-14 新增**（P2-N2-4）：`stable_id` 字面複製 grep guard，防止 W-D MAG-083 P1-1 抽出的 Agent Spine id helper 被未來 callsite 重新用 literal seed format 複製。

| 腳本 | 用途 |
|------|------|
| `ci/check_stable_id_duplication.sh` | P2-N2-4 — 快速 grep guard；掃描 Rust source，若 canonical Agent Spine helper/caller 外出現 `format!("{}:{}:{}:{}"...` 且同檔含 stable-id-like 變數名，即 exit 1 並列出 offending file:line。已接入 GitHub Actions `stable_id duplication guard` job。 |
| `ci/replay_runner_symbol_audit.sh` | REF-20 Wave 3 R20-P2b-S10 — `nm` symbol 稽核 `target/release/replay_runner` binary，驗 0 forbidden symbol class（Decision Lease / IPC / exchange pipeline / Bybit connector / live auth write / order placement / DB writer）。Darwin 用 `nm -gU`（BSD），Linux 用 `nm --extern-only --defined-only`（GNU）。Exit 0 PASS / 1 FAIL / 2 build / 3 nm-not-found / 4 binary-not-found。env：`SKIP_BUILD=1`（跳 cargo）/ `REPLAY_RUNNER_BIN=/path`（覆寫 binary path）。 |
| `ci/test_replay_runner_symbol_audit.sh` | 上述 audit script 的 mock-based bash 測試套（5 cases：clean / forbidden hit / nm absent / binary missing / multi-class hit）。用 nm shim 避免真 cargo build (~30-60s)。 |
| `ci/README.md` | 三層縱深防禦說明 + GitHub Actions / cron / pre-commit hook 整合範例。 |

## canary/ — 灰度驗證 (Canary / Soak Test)

| 腳本 | 用途 |
|------|------|
| `canary/engine_watchdog.py` | 引擎存活監控（`--status` 顯示健康狀態，`--stale-threshold` 設定過期秒數） |
| `canary/replay_runner.py` | 灰度回放：讀取 canary JSONL 並與 Python 基線比對 |
| `canary/canary_comparator.py` | Canary 記錄比對器：逐 tick 驗證 Rust vs Python 指標/信號/PnL |
| `canary/canary_schema.py` | Canary JSONL schema 定義（Pydantic model） |
| `canary/rollback_drill.sh` | 回滾演練腳本 |
| `canary/test_canary.py` | Canary 系統單元測試 |
| `canary/replay_earn_preflight.py` | Stage 0R Earn variant preflight harness (Sprint 1B Wave C) — first stake 前 5 sanity check (APY drift / 5-gate reject path / first stake LAL 0 / fail-closed exit code / ATR cap+drawdown);拉 Bybit V5 /v5/earn/apr-history public GET + 7d cumulative accrual day-by-day + mock 5 gate fail injection + 3 階 reconciliation cascade;產 `earn_first_stake_stage0r_<date>.json` verdict;CLI `--coin USDT --amount-usd 100 --days 7`;exit 1 任 1 FAIL。對齊 spec `docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md` §3。 |
| `canary/test_replay_earn_preflight.py` | Stage 0R Earn preflight harness 14 unit test:5 sanity check (含 PASS/FAIL/VACUOUS_PASS/DEFERRED 各 case) + 5 gate fail injection grid + 3 階 cascade + JSON schema 對齊 spec §4 AC-5。Mac unittest 14/14 PASS。 |
| `canary/healthchecks/_common.py` | Phase 1b close-maker-first healthcheck 共享層（PG conn + Wilson 95% CI + JSON formatter + CLI argparse），對齊 AMD-2026-05-15-02 v0.6 §4.1 + spec §8.1。 |
| `canary/healthchecks/62_close_maker_fill_rate.py` | `[62]` close_maker_fill_rate Wilson-CI gate（spec §8.1 Consensus-MF-2）：7d demo+live_demo maker fill rate + Wilson 95% CI，PASS lower≥0.60 / FAIL upper<0.40 / WARN 中段。CLI standalone for QA T+24h post-deploy verification。 |
| `canary/healthchecks/63_close_maker_fallback_audit.py` | `[63]` close_maker_fallback_audit（spec §8.1 Consensus-MF-3）：enum allowlist 完整性 + NULL ladder ratio (PASS ≤0.1% / WARN ≤1% / FAIL >1%)；safety path 三 enum 排除於 NULL ladder 之外。 |
| `canary/healthchecks/64_close_maker_rate_limit_pause_duration.py` | `[64]` rate-limit backoff scope（AMD §5.4 BB-MF-2 + spec §8.1 BB-SF-1）：per-symbol exp backoff + global pause sample/day ladder (5/30)；details.rate_limit_scope 完整性子檢查。 |
| `canary/healthchecks/65_reject_sample_healthcheck.py` | `[65]` PostOnly + MaxPending reject sample coverage（spec §8.3 BB-MF-5 / AC-15）：防 demo silent degradation，per env 7d 兩 category 各須 ≥1 樣本，否則 Phase 2b 無法 promote。 |
| `canary/healthchecks/80_liquidation_pulse_freshness.py` | `[80]` W-AUDIT-8a C1-LIQ-WRITER acceptance #3：market.liquidations 4-維健康度（topic freshness / row volume per-hour / cohort 25-sym coverage / parse guard side+finite），24h default window。CLI standalone for QA post-deploy verification。Linux empirical 2026-05-18 24h baseline 6134 row / 25/25 cohort / latest_age 15s = PASS。2026-05-25 由 [67] rename 為 [80] 避 passive_wait_healthcheck `[67] feature_baseline_readiness` 衝突（per operator directive）。 |
| `canary/healthchecks/tests/` | pytest 單元測試集（60 tests / 6 files）— Wilson CI 數值對 reference 表 / verdict ladder / SQL filter / multi-cell severity / liquidation pulse 4-維 freshness。Linux + Mac 同跑 60/60 PASS。 |

## phase4/ — Phase 4 學習/晉升工具 (Learning & Promotion)

| 腳本 | 用途 |
|------|------|
| `phase4/dl3_go_no_go.py` | DL-3 Go/No-Go 決策檢查 |
| `phase4/weekly_report.py` | 每週學習/交易績效報告 |

## maintenance_scripts/ — 維護腳本 (Maintenance)

| 腳本 | 用途 |
|------|------|
| `maintenance_scripts/prune_dated_files.sh` | 清理過期的 dated 輸出文件 |

### maintenance_scripts/bybit_connector/ — 舊治理鏈腳本 (Legacy H/I/J/K Chain)

> **2026-04-23 清理**：原本 60 檔（含 README），DEDUP-PY-RUST 系列尾聲刪除 53 個
> 一次性 H/I/J/K-chain 修復腳本（0 caller，DEAD-PY-2 後 Python 治理類已刪、依賴斷鏈，
> git history 可復原）。同步刪除 `program_code/exchange_connectors/bybit_connector/scripts/`
> 下對應的 45 個 REAL= shim wrappers。保留 6 個基礎工具：

| 腳本 | 用途 |
|------|------|
| `lib_trading_env.sh` | 共享環境變量設定（被 `run_with_trading_env.sh` source） |
| `run_with_trading_env.sh` | 在交易環境中運行任意命令（純 bash，無 Python 依賴） |
| `run_i10_canonical_h_chain_recheck.sh` | H 鏈權威檢查器（讀 runtime JSON + 嵌入式驗證） |
| `run_i10_canonical_decision_lease_recheck.sh` | I 鏈權威檢查器（讀 runtime JSON + 嵌入式驗證） |
| `_bybit_latest_wrapper.py` | Bybit API 最新值包裝器（通用工具，標準庫 only） |
| `repair_i10_stage_source_aliases.py` | 修復 I10 stage source 別名（無外部依賴） |

`program_code/.../scripts/` 下剩餘 5 檔：`lib_trading_env.sh` / `run_with_trading_env.sh`
兩個 shim 指向上面白名單，以及 3 個獨立原檔 `bybit_bind_active_route_env.sh`
（shim 指 `misc_tools/`）、`bybit_h1_report_utils.py`、`bybit_readonly_loop_writer.sh`。
