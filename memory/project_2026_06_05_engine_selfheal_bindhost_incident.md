---
name: project_2026_06_05_engine_selfheal_bindhost_incident
description: Demo/live 全部平倉失敗根因=引擎宕機 20h+自愈被 OPENCLAW_BIND_HOST=0.0.0.0 卡死；含恢復 runbook + close-all 全 IPC 結構真相 + 仍開的告警缺口
metadata: 
  node_type: memory
  type: project
  originSessionId: a3f8d2a5-7e24-4357-b277-3ec27ea89a3e
---

2026-06-05 事故：operator 報「demo GUI 全部平倉失敗」。根因**不是平倉代碼**，是 Rust 引擎宕機 ~20h 且自愈被卡死。

**結構真相（durable，調試平倉必看）**：demo 與 live 的 close-all/flatten **100% 走 Rust IPC** —— 主 `close_all_positions` IPC + orphan-sweep 的逐倉 `close_position` 也是 IPC（`strategy_ai_routes.py:_sweep_demo_orphan_positions` / `live_session_routes.py:_sweep_live_orphan_positions`）。**引擎掛=GUI 零平倉路徑**，端點仍回 HTTP 200 + GUI 彈綠勾（誤導）。**live REST 兜底被 P1-03 治理裁定永久禁止**（所有 live 寫入必過 Rust 執行權威），demo 雖保留 REST helper 但 position-close 仍走 IPC。承 [[project_openclaw_positioning]]。

**為何引擎起不來（runbook）**：`~/.bashrc` + `~/.config/environment.d/openclaw.conf` + systemd user-manager env 三處都有 `export OPENCLAW_BIND_HOST=0.0.0.0`（operator 過時的 Tailscale 訪問 override）。watchdog 是 `openclaw-watchdog.service`（systemd --user），從 environment.d 繼承 → 每次 `restart_all.sh --engine-only` 撞 bind-host 安全守衛（`helper_scripts/lib/api_bind_host.sh` 對 0.0.0.0/:: 及 tailscale-unavailable `return 2`）→ exit=2。**修法**：三處改 `auto`（resolver `auto`→Tailscale IP 100.91.109.86，與 API 綁定一致，GUI 訪問保留且守衛滿足，**勿用 0.0.0.0**）；`systemctl --user set-environment OPENCLAW_BIND_HOST=auto`；`OPENCLAW_BIND_HOST=auto bash helper_scripts/restart_all.sh --engine-only --require-clean-build-window`（無 rebuild 跑現成 binary `rust/target/release/openclaw-engine`；預設 fail-closed 清 auth → live 需 /auth/renew 重批，demo 不受影響）；`systemctl --user restart openclaw-watchdog.service`。已恢復：引擎 PID 3289963 健康。

**watchdog 自愈雙 bug（已修 commit 072b8e20，待 Linux 部署）**：① `on_engine_crash` 在 `engine_alive` 已 False 時 early-return → restart 是 edge-trigger，restart 持續失敗時永不重試（first-detection deadlock，同 [[project_first_detection_deadlock_pattern]]），架空 MAX_CONSECUTIVE_FAILURES=5+backoff。改 level-trigger（每 poll 經 should_restart gate 重試）+ counting 仍 edge。② trigger_restart subprocess 裸繼承污染 env → 加 sanitize（危險 bind-host→auto）。③ RESTART_SKIPPED canary 用 reason_key 去重防洪。E1→E2(2M+1H)→E1→E2 PASS→E4 PASS，118 test green。

**告警缺口已 code-閉合（commit 92cdcc41，待 operator 填 creds + 重啟服務啟用）**：原 `canary_events.jsonl`（RESTART_FAILED/CIRCUIT_BROKEN）**無告警消費者**=宕機 20h 無人知的根因。已建 **GUI 可配置告警**：`app/alert_config.py`（共享 stdlib loader，`<DATA_DIR>/alert_config.json` 0600，SSRF guard）+ `settings_routes` GET/POST/test 端點 + tab-settings「告警通知」卡（Telegram+Webhook，遮罩/partial-safe/armed-not-enabled 狀態）+ watchdog `_send_alert_best_effort`（daemon thread 5s timeout，**絕不在 restart 關鍵路徑**）觸發熔斷/長宕機/恢復。app 與 standalone watchdog 讀同一檔（E4 執行級驗證 0 drift）。全鏈 PA→E1/E1a→E2(退 HIGH 缺 seam test)→E2 PASS+E3 PASS(SSRF/遮罩/0600)+A3+E4 PASS(103+14 test,0 app regression)。**no-op until creds**。**剩**：①operator 在 GUI 填 Telegram/Webhook creds ②重啟 API+watchdog 啟用（feature 已三端同步 92cdcc41 但服務跑舊碼）③companion: systemd 單元漂移（缺 Restart=always）重裝模板。承 [[project_2026_05_22_layered_autonomy_with_failsafe]]。


---

## [index-archive 2026-06-10] 原 MEMORY.md 索引條目全文(壓縮索引前歸檔,內容為當時點狀態)

- [引擎自愈 bind-host 宕機事故 (2026-06-05)](project_2026_06_05_engine_selfheal_bindhost_incident.md) — demo/live「全部平倉失敗」根因=引擎掛 20h（非平倉碼）：`OPENCLAW_BIND_HOST=0.0.0.0`（.bashrc+environment.d+systemd-user-env 三處）卡死 watchdog 重啟（撞 bind-host 守衛 exit=2）。**結構真相：close-all 全走 Rust IPC，引擎掛=GUI 零平倉路徑，live REST 兜底被 P1-03 禁**。已改 auto 恢復（引擎 PID 3289963 健康）+ watchdog 自愈雙 bug 修在 **commit 072b8e20**（edge-trigger deadlock→level-retry + env sanitize + canary throttle，E1→E2→E4 全 PASS，待 Linux 部署）。**仍開：canary_events.jsonl 無告警消費者=宕機 20h 無人知**
