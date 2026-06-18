# E1 — flash_dip enable-prep（死亡率監測 cron + restart_all flag 轉發） · 2026-06-18

STATUS: DONE — 兩件交付 Linux 實證通過（bash -n / dry read-only rc=0 / 三分支邏輯 / read-only fail-loud），無 commit，待 E2。

## 任務摘要
PA/PM 派的 flash_dip_buy demo pilot enable-prep（pilot commit 53da5f7b，flag-OFF inert）：
1. 新 read-only 死亡率監測 cron（DEFERRED phase-2 CUSUM auto-breaker 的 interim，alert-only）。
2. `restart_all.sh` engine-launch env allowlist 補 `OPENCLAW_FLASH_DIP_PILOT_ENABLED` 轉發（QA pre-flight blocker B1）。

E2-reconfirm / QA pre-flight 兩 lens 皆回 CHANGES_NEEDED。其中 **QA blocker B1（restart_all flag 未轉發）正是本任務 (2) 直接修掉**。其餘 finding 不在本 enable-prep 檔案範圍（見「reconfirm/QA 處理」）。

## 修改清單（檔案互不重疊，皆未 commit）
| 檔 | 性質 | 範圍 |
|---|---|---|
| `helper_scripts/cron/flash_dip_death_rate_cron.sh` | 新建 | 死亡率監測 cron，逐項 mirror `recorder_health_cron.sh` 安全語意 |
| `helper_scripts/restart_all.sh` | 改（2 hunk） | engine-launch env allowlist 補 1 個 flag 轉發 + 1 個 local-var grep-parse |
| `helper_scripts/SCRIPT_INDEX.md` | 改 | 新增 `## 2026-06-18` section + 更新「最後更新」日期 |

## 死亡率 metric（純 trading.fills，read-only）
- **closed 深-K slot** = flash_dip CLOSE fill：`strategy_name='flash_dip_buy' AND exit_reason IS NOT NULL AND engine_mode='demo' AND entry_context_id IS NOT NULL`（close fill 攜 realized_pnl + entry_context_id，V083 強制 close fill 必攜 entry_context_id）。
- **entry notional** = INNER JOIN 回 ENTRY fill（`exit_reason IS NULL AND context_id = close.entry_context_id AND strategy_name='flash_dip_buy'`）取 `price * qty`。long-only dip-buy，entry notional 為正基準。
- **realized_return** = `realized_pnl / NULLIF(entry_notional, 0)`；**death** = `realized_return <= -0.50`（`OPENCLAW_FLASH_DIP_DEATH_RETURN` 可覆寫）。
- **death_rate_pct** = deaths / n_closed_slots × 100；**n>=20 才 actionable**（`OPENCLAW_FLASH_DIP_DEATHRATE_MIN_N`），death_rate>3%（`OPENCLAW_FLASH_DIP_DEATHRATE_THRESHOLD_PCT`）才告警。
- 設計理由：用 entry notional 當分母（非 close fill 自身 price*qty）——close notional 是出場時名目（已含跌幅），用它低估虧損比例；entry notional 才是 -50% 的正確基準。缺 entry / notional<=0 → INNER JOIN + `WHERE entry_notional>0` 自動排除（fail-soft，不污染分母，並輸出 `n_dropped_no_entry` 診斷）。

## 治理對照
- **#1 不碰硬邊界**：cron read-only（PGOPTIONS 連線層 `default_transaction_read_only=on`，實證 fail-loud）；不啟 flag、不熔斷、不下單、不碰 auth/lease/risk_config；restart_all 僅補 1 flag 轉發，default 留空=fail-closed inert，未動 5-gate / mainnet guard。
- **安全語意逐項 mirror `recorder_health_cron.sh`**：`set -euo pipefail` / heartbeat start touch (`cron_heartbeat/flash_dip_death_rate.last_fire`) / mkdir lock+trap release / grep-parse `basic_system_services.env` creds（FATAL-on-missing，禁硬編 trading_admin）/ rc-capture `if psql …; then rc=0; else rc=$?; fi` / PGOPTIONS 連線層唯讀（**刻意不在 SQL 放 SET**，避 command-tag 污染 `-A -t` stdout——recorder_health 修掉的 bug）。
- **alert_sink schema 一致**：`ts_utc/subject/severity/body/channels_attempted/channels_ok`（severity=critical，body 明標 monitor 不採熔斷/disable 動作、phase-2 CUSUM DEFERRED）。
- **#3 healthcheck**：heartbeat sentinel 已落（與 recorder_health / recorder_mm_verdict 同 pattern，配對 healthcheck 監測 mtime）。
- **#4 跨平台**：無硬編 `/home/ncyu`；路徑全走 `OPENCLAW_DATA_DIR` / `OPENCLAW_SECRETS_ROOT` / `OPENCLAW_BASE_DIR`。
- **#7 SCRIPT_INDEX**：已新增條目。
- 註釋：新檔中文 MODULE_NOTE + why-fail-closed rationale（符 bilingual-comment-style 中文優先）。

## 關鍵 diff（load-bearing）
restart_all.sh — engine-launch env 區塊（L647，nohup 前 export）：
```
        OPENCLAW_RISKCONFIG_AGENT_TUNING_ENABLED="${riskconfig_agent_tuning}" \
        OPENCLAW_FLASH_DIP_PILOT_ENABLED="${flash_dip_pilot_enabled}" \
        nohup rust/target/release/openclaw-engine > "$DATA_DIR/engine.log" 2>&1 0<&- 200<&- &
```
local-var（L605-606，operator-env 優先 → env-file fallback → 空留空）：
```
    local flash_dip_pilot_enabled
    flash_dip_pilot_enabled="${OPENCLAW_FLASH_DIP_PILOT_ENABLED:-$(grep '^OPENCLAW_FLASH_DIP_PILOT_ENABLED=' "$SECRETS_ROOT/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2- || echo "")}"
```

## Linux 實證（ssh trade-core，read-only）
- `bash -n` 兩檔 clean（Mac + Linux 各一次）。
- cron dry-run rc=0（isolated `OPENCLAW_DATA_DIR=/tmp/openclaw_flashdip_drycheck`，跑後已清）：status JSON 良構，`n_closed_slots=0 / death_rate_pct=null / actionable=false / alerted=false`（pilot flag-OFF inert、零 flash_dip fills，正確不告警）；heartbeat sentinel touched；無 alerts 檔（正確）；PG WARNING（collation）只進 stderr/run-log，未污染 status JSON。
- read-only fail-loud 實證：`CREATE TEMP TABLE` → `ERROR: cannot execute CREATE TABLE in a read-only transaction`（證 PGOPTIONS 生效）。
- 三分支邏輯驗證（python 純算術，無 DB）：death 8%@n=25 → **alert 觸發**；2%@n=25 → no alert（< 門檻）；50%@n=10 → **not actionable, no alert**（min-n gate 抑制小樣本噪音）。
- flag 到達引擎 /proc/environ 驗證：當前 engine PID 2666511 環境無 flag（launched before 本次 edit，**未重啟**，預期）。**下次 `restart_all.sh` 帶 flag 重啟後**，L647 轉發行會注入 engine 進程 env（機制與已驗的 25fc4369 / 88b35727 轉發完全同構）——此為 operator restart 時點驗證，本任務 scope 不重啟。

## E2-reconfirm / QA pre-flight finding 處理
- **QA B1（restart_all flag 未轉發）= 本任務 (2) 直接修掉**，Linux 已驗轉發行就位 + bash -n clean。
- **QA B2（三鎖 enable runbook）**：strategy_params_demo.toml active=true + env flag=1 + risk_config_demo.toml `[per_strategy.flash_dip_buy].enabled=true`——非代碼，PM/operator runbook 落地。已在 SCRIPT_INDEX operator 激活段 + E1 memory 標註。
- **E2 HIGH（restart re-attribution 使 concurrency cap 被繞）+ MED（exchange-path concurrency-reject 測試缺口）**：這是 **router.rs / KNOWN_STRATEGY_NAMES(orphan_handler.rs) / tests.rs 引擎碼**的修復方向，屬 flash_dip 引擎 fix 的 **re-E2 ticket**，**不在本 enable-prep 任務的檔案範圍**（本任務只動 2 個 helper_scripts + 1 index）。未在此擅自擴 scope 改引擎碼——應由 PM 派一個獨立 E1 ticket（加 flash_dip_buy 進 KNOWN_STRATEGY_NAMES 或 triage 前還原真歸屬 + triage-path/exchange-path regression test）。

## 不確定之處
- 死亡率「within the hold」語意：本實作以**已了結 slot 的 realized return**衡量（close fill 的 realized_pnl 即整段 hold 的真實了結結果，N=3 hold 內若提早平倉也納入），非 hold 期內的 intra-hold mark-to-market 最低點（fills 表無逐 tick MTM，無法重建盤中極值）。這是 fills-only 可得的最忠實「死亡」定義；若 PA 要的是 intra-hold drawdown <=-50%（即使收盤回升仍算死），需另接 market.klines 重算，超出本任務「reads trading.fills」的明確指示——故採 realized-return 定義並在此標註。
- `n_dropped_no_entry`：歷史 close fills 可能 entry_context_id NULL（V083 NOT VALID，只對新 INSERT 強制）。pilot 啟用後新 fills 必攜，drop 應趨 0；status line 已輸出供觀測。

## Operator 下一步
1. E2 審查本兩檔（chain：E1→E2→E4→QA→PM，不可跳）。
2. PM 在 E2→E4 綠後從 Mac worktree 統一 commit（restart_all.sh + 新 cron + SCRIPT_INDEX.md）。
3. enable 時：B2 三鎖全開 + `OPENCLAW_FLASH_DIP_PILOT_ENABLED=1` 入 basic_system_services.env → restart_all.sh 重啟 → 驗 engine snapshot 出現 flash_dip_buy + /proc/environ 有 flag。
4. cron 安裝（手動）：`53 6 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/flash_dip_death_rate_cron.sh`。
5. PM 另派 re-E2 ticket 處理 E2 HIGH/MED 引擎碼 finding（router.rs restart re-attribution + 測試缺口），與本 enable-prep 分開。
