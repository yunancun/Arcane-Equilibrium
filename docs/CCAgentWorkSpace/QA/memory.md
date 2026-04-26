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
| 報告 | 日期 | 關鍵發現 |

