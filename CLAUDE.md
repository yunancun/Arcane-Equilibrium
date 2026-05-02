# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）

---

## 一、項目定位

長期進化型 AI Agent 自動交易系統。OpenClaw 為中樞、**Bybit 為唯一交易所**（專攻）。

> Agent 自主完成交易決策與執行，對成本與收益有清晰感知，能感知自身狀態，能持續學習，在嚴格風控框架下逐步贏得更高自主權。

人類 Operator 角色：不定時檢查、審閱、矯正、批准關鍵步驟、推動策略演進。

**交易所決策（2026-04-03）：** 早期規劃含 Binance 雙平台，現已明確專攻 Bybit。Binance 僅作為超長期可能方向保留，當前開發、設計、架構決策均不需考慮 Binance 兼容性。

**系統管線：** 市場數據 → H0 本地判斷 → H1-H5 AI 治理 → I Decision Lease → 執行適配層 → 學習/歸因

---

## 二、16 條根原則（DOC-01 項目憲法 §5.1–§5.16，不可違背）

1. **單一寫入口** — 所有訂單/執行動作通過唯一受控入口
2. **讀寫分離** — 研究/GUI/學習：只讀。寫入權限極度受限、可審計、可鎖定
3. **AI 輸出 ≠ 即時命令** — AI → Decision Lease（帶時效、可撤銷）→ 本地復核 → 執行
4. **策略不能繞過風控** — 所有交易意圖必須經 Guardian 審批
5. **生存 > 利潤** — 先判斷「不會螺旋崩潰」，再判斷「能否盈利」
6. **失敗默認收縮** — 不確定時默認保守：不開新倉、降頻率、降風險
7. **學習 ≠ 改寫 Live** — 學習平面與 Live 平面隔離
8. **交易可解釋** — 每筆交易必須可重建：為什麼、何時、風控審批、授權、執行、結果
9. **交易所災難保護** — 本地止損 + 交易所條件單雙重防線
10. **認知誠實** — 所有結論區分事實 / 推斷 / 假設
11. **Agent 最大自主權** — P0/P1 硬邊界內，Agent 完全自主決定：幣種、策略、參數、時機
12. **持續進化** — 系統必須從交易行為中自動學習（當前 demo 階段：Paper 驗證→參數進化，live 自動部署待 Phase 3 放權框架）
13. **AI 資源成本感知** — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉
14. **零外部成本可運行** — 基礎運營僅需 L0+L1（Ollama + 免費搜索）
15. **多 Agent 協作** — 5 Agent（Scout/Strategist/Guardian/Analyst/Executor）+ Conductor 編排，正式對象通信
16. **組合級風險意識** — 監控關聯曝險、策略重疊持倉、資金分配合理性

**優先級序：** 帳戶生存 > 風控治理 > 系統健康 > 審計可追溯 > 人類終審 > 真實 Net PnL > 自主能力進化

**實施準則（從根原則衍生，非憲法級但強制遵守）：**
- **認知調製 ≠ 能力限制** — Agent 壓力下更審慎的方式是提高決策門檻，不是關閉能力。虛擬稀缺性（能量/積分/內部貨幣）被明確否決。（衍生自原則 #11，見 `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`）

---

## 三、當前系統狀態摘要

**Runtime（2026-05-01 23:17 CEST · ssh verify · G6-04 §三 drift 規則）**：Linux source and runtime are redeployed to `eaf0c7e` via `restart_all.sh --rebuild --keep-auth` after ff-only pull. Code-bearing source includes `[22]` calibration `b283fda`, G8-05/LG-5 checkpoint `25d8e54`, scanner Python/MLDE surface `be8fe37`, canonical GUI performance metrics `569e06b`, doc checkpoint `daca52f`, and PRE-LIVE-3 trend/readiness API/UI `eaf0c7e`. Engine PID **2455097** + API uvicorn PID **2455171** + engine_watchdog PID **3450754** + openclaw-gateway PID **3973441** alive。watchdog `engine_alive=true`，paper/demo/live snapshots fresh。API `/api/v1/strategy/prelive/edge-gates` returns 401 unauthenticated rather than 404（route loaded）。Manual passive healthcheck wrapper SUMMARY **WARN** exit 0；current WARNs include `[4]`, `[10]`, `[33]`, `[38]`, `[40]`, `[41]`, and `[11]`. No DB migration apply, strategy/risk parameter change, or live auth mutation was performed; `--keep-auth` preserved existing authorization.

**Active edge state**：Strategy Edge Repair + Strategy Edge Models + scanner market judgement / five-strategy context are deployed. Current observation gates are `[22] trading_pipeline_silent_gap`, `[33] maker_fill_rate`, `[38] grid_trading_lifecycle_drift`, `[40] realized_edge_acceptance`, and `[41] scanner_market_gate_confirmation`; interpret rolling windows with post-deploy cutoffs because they still mix old samples. Wave 4 pre-stage RFCs for LG-2 H0 blocking verification, MLDE-6 live promotion contract, and LG-3 provider pricing binding are ready at `5ce777b`. `ec8f0f4` adds STRK-FUP broader RFC, LG-4 RFC, dormant G7-04 CUSUM hook, and G4-03 canary Phase B. `25d8e54` adds the G8-05 AI Cost ROI Monitor static UI and LG-5 constrained autonomous live RFC. `be8fe37` exposes Rust scanner trend/fitness context to Python `/scanner/opportunities`, ScoutWorker intel, MLDE shadow advisor, and DreamEngine; V034 migration file is present but runtime DB apply was not performed. `569e06b` adds a backend-authored Demo/Paper/Live performance metric contract and shared GUI renderer. `eaf0c7e` completes and deploys PRE-LIVE-3 with read-only `/api/v1/strategy/prelive/edge-gates`, Live [33]/[38]/[40] trend cards, and a readiness checklist. The main live-demo issue remains fee quality / realized edge; grid lifecycle drift is rolling-WARN. Primary metric remains post-fee `net_bps_after_fee`; PnL and win-rate are secondary references.

**Dust residual prevention**：`8efe71b` + `b1cd9a8` are in source and runtime. Primary exchange full-close uses Bybit `qty=0 + reduceOnly + closeOnTrigger`; normal zero-qty orders still fail closed; fast-track partial reduce skips residuals that would fall below minNotional; `DUST_FROZEN` / `orphan_frozen` remain visible. Runtime proof completed 2026-04-30 21:10-21:52 CEST: 8 Demo/LiveDemo `qty=0` close orders joined to nonzero fills, including Demo `APEUSDT` `orphan_frozen` qty 0.1 and LiveDemo `XAGUSDT` `orphan_frozen` qty 0.001, with no later position snapshot for those residues.

**MLDE / Dream edge-unblock**：Demo autonomy is active and live-governed. `[35]` learning data contract, `[36]` advisory/live lease boundary, and `[37]` demo applier audit all PASS. Live/live_demo auto-apply remains forbidden without GovernanceHub + Decision Lease + the 5 live gates. Rust active LinUCB arm-space remains `v1_15`; richer `mlde_arm_id` stays shadow/advisory until a future migration.

**Live boundary**：LiveDemo/live pipeline is currently authorized and running under live-grade auth. This does **not** grant autonomous live trading or live parameter mutation. True live actions still require the hard gates in §四, Operator role auth, signed authorization, and Decision Lease governance.

**Closed history removed from active state**：62-finding remediation Batch A-F, STRKUSDT P0 wave, Wave A-H, and older Wave 1-3 implementation narratives are closed history. Active snapshots before this cleanup are preserved at `docs/archive/2026-04-30--CLAUDE-pre-cleanup-snapshot.md`, `docs/archive/2026-04-30--TODO-pre-cleanup-snapshot.md`, and `docs/archive/2026-04-30--README-pre-cleanup-snapshot.md`.

**Next decisions**：Continue post-cutoff edge observation from scanner/five-strategy deploys. Latest manual wrapper at 2026-05-01 23:17 CEST: `[33]` 7d maker_like 27.2% / fee_drop 22.0%; `[38]` lifetime_ratio 0.41 WARN (demo p50 7.9min vs live_demo 3.2min); `[40]` 24h rows=37 avg_net -17.21bps; `[41]` gates fired but labels insufficient; `[11]` rolling 2d replay remains WARN not FAIL; `[4]` phys_lock recent停火 and `[10]` intents_writer_ratio under-firing remain WARN. G2-02 ma_crossover dual-track around 2026-05-03; P0-2 + G2-01 PostOnly acceptance around 2026-05-07/08; P0-3 edge decision around 2026-05-15. Rank 9 HTTPS deploy still needs explicit runtime/deploy approval; next safe non-deploy candidates are P03-PREP-1, DOC-1, TEST-1, or PRE-LIVE-1.

**Durable architecture**：Rust `openclaw_engine` remains the canonical paper/demo/live engine and ConfigStore authority. Python is control plane/GUI/bridge only, not the trading truth layer. Guardian remains a RiskConfig-derived view. **禁止 restart-to-apply** remains binding for trading/strategy/risk parameter behavior.

**History pointers**（do not reload unless needed）:
- 2026-04-30 active-doc cleanup summary: `docs/archive/2026-04-30--active_docs_cleanup_archive.md`
- 2026-04-30 active-doc snapshots: `docs/archive/2026-04-30--CLAUDE-pre-cleanup-snapshot.md`, `docs/archive/2026-04-30--TODO-pre-cleanup-snapshot.md`, `docs/archive/2026-04-30--README-pre-cleanup-snapshot.md`
- 62-finding Batch A-F: `docs/archive/2026-04-29--62finding-batch-A-to-F.md`
- STRKUSDT P0 Wave: `docs/archive/2026-04-29--strkusdt-p0-wave.md`
- Wave A-H narrative: `docs/archive/2026-04-29--wave-A-to-H-narrative.md`
- 2026-04-22~24 runtime/detail archive: `docs/archive/2026-04-29--claude_md_section3_pre_04_27_detail.md`
- Earlier §三 snapshots: `docs/archive/2026-04-21--claude_md_section3_snapshot.md`, `docs/archive/2026-04-20--claude_md_section3_snapshot.md`, `docs/archive/2026-04-15--claude_md_section3_snapshot.md`

---

## 四、硬邊界（永遠不能違背）

```python
# ── Live_Ready 真實狀態 ──
# LIVE-P0/P1/P2 代碼完整（SM-01/02/04 + Reconciler + 3E-ARCH），0 真實 live 流量
# （歷史 43k 條 engine_mode="live" 實為 LiveDemo）。

# 真實 live 門控（Rust 端可驗證 = 4 項 / 全部 = 5 項）：
#   1. Python `live_reserved` global mode           （Python 側，重啟會丟）
#   2. Python Operator 角色 auth                    （Python 側）
#   3. OPENCLAW_ALLOW_MAINNET=1 env var             （Rust 側，僅 Mainnet）
#   4. secret slot 有 api_key + api_secret          （Rust 側，憑證空 → Err；
#        Mainnet env-var fallback 封閉，來源優先級見 bybit_rest_client.rs:386-497）
#   5. authorization.json 簽名+未過期+env_allowed 匹配  （Rust 側，HMAC-SHA256）
#        路徑：$OPENCLAW_SECRETS_DIR/live/authorization.json
#        檢查點：build_exchange_pipeline 啟動 + main.rs 每 5 min re-verify
#        失效 → engine 優雅 shutdown（cancel_token）
#        涵蓋 LiveDemo + Mainnet（LiveDemo 不因 api-demo endpoint 降級）
#        **必經** Python renew/approve 路由 `_write_signed_live_authorization()`，不可手動寫

# execution_authority：Rust 僅為 P0/P1 denylist 字串常量
# （claude_teacher/applier.rs:226），非真實授權邏輯；「auto_granted_on_start」屬 Python 概念。
decision_lease_emitted  = False
max_retries             = 0

# 永不允許的硬錯誤：
# - 繞過 Operator 角色認證或 live_reserved 直接啟動 live session
# - 自動修改 engine trading_mode 為 live（需 operator 顯式配置）
# - ML / DreamEngine / ExecutorAgent / StrategistAgent 直接 live 下單或修改 live 參數而未經 GovernanceHub + Decision Lease 批准
# - Bybit API timeout / retCode != 0 → fail-closed，不重試
# - should_call_ai=true 但 invocation 沒發生；偽造 AI 調用或交易活動
# - Mainnet 下無 OPENCLAW_ALLOW_MAINNET=1，或用 env var 當唯一憑證來源
# - Live（含 LiveDemo）下無有效 authorization.json 即 spawn pipeline
```

---

## 五、架構總覽

```
[數據與觀察層]           Bybit REST + WS → Postgres + Observer
[H0 本地判斷內核]        freshness / health / eligibility / risk envelope（<1ms SLA）
[GovernanceHub]          SM-01 授權 + SM-04 風控 + SM-02 租約 + EX-04 對賬
[H1-H5 AI 治理層]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 209 /api/v1 + 11 non-api 路由（2026-04-16 audit 實測）
[GUI + Learning]         11-Tab 控制台 + Learning Cockpit + Paper Trading Dashboard
[Rust openclaw_engine]   paper / demo / live 三模式唯一引擎（1C-3-F 後）
                         tick pipeline + IntentProcessor + paper_state + governance + stop_manager
[Layer 2 AI 推理]        L0 確定性 → L1 Ollama → L2 Claude
[風控框架]               P0/P1/P2 三層 + 對抗性止損 + AI 注意力稅
[策略工具包]             KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator
[管線橋接]               PipelineBridge: Tick Fan-Out + Intent→Order + 治理 gate
[止損管理器]             StopManager: Hard/Trailing/Time Stop + ATR 動態倉位
```

---

## 六、路徑與啟動

```
GitHub repo:    yunancun/BybitOpenClaw
本地主工作樹:   由 $OPENCLAW_BASE_DIR 決定（repo 任意絕對路徑皆可）
                Linux 預設: $HOME/BybitOpenClaw/srv（/home/ncyu/srv ← symlink, legacy）
                Mac   範例: /Users/ncyu/Documents/Projects/TradeBot（或 $HOME/BybitOpenClaw/srv）
本地-only：     settings/（secrets）  trading_services/（runtime）
```

### 跨平台 Runtime 路徑（Mac/Linux 共用）
**Mac dev 必設**（Linux 上可選，默認 `/tmp/openclaw` + `$HOME/BybitOpenClaw/`）：
```bash
# Repo 位置（任意路徑皆可，例如 /Users/ncyu/Documents/Projects/TradeBot）
export OPENCLAW_BASE_DIR="/Users/ncyu/Documents/Projects/TradeBot"

# Runtime / socket / log 目錄（Mac /tmp 是 /private/tmp symlink，必須顯式設）
export OPENCLAW_DATA_DIR="$HOME/.openclaw_runtime"

# Secrets 根目錄（含 environment_files/ + secret_files/）
export OPENCLAW_SECRETS_ROOT="$HOME/.openclaw_secrets"

# Bybit slot base（Rust/Python 專用，= $SECRETS_ROOT/secret_files/bybit）
export OPENCLAW_SECRETS_DIR="$HOME/.openclaw_secrets/secret_files/bybit"

# 歸檔目錄（clean_restart / fresh_start 寫入）
export OPENCLAW_ARCHIVE_DIR="$HOME/.openclaw_archive"

mkdir -p "$OPENCLAW_DATA_DIR" "$OPENCLAW_SECRETS_ROOT/environment_files" \
         "$OPENCLAW_SECRETS_ROOT/secret_files/bybit" "$OPENCLAW_ARCHIVE_DIR"
```
原因：Mac `/tmp` 是 `/private/tmp` symlink 且 LaunchAgents 看到不同路徑；Mac 上跑 pytest、`restart_all.sh`、IPC socket 都必須走 `$OPENCLAW_DATA_DIR`。Linux 上不設時 fallback 到 `/tmp/openclaw` + `$HOME/BybitOpenClaw/{secrets,archive}`，行為不變。

**env var 語義速查**：
| env var | 指向 | 誰在讀 |
|---|---|---|
| `OPENCLAW_BASE_DIR` | repo 根（srv） | Rust `startup.rs` / `strategies` · Python 多處 · `start_paper_trading.sh` |
| `OPENCLAW_DATA_DIR` | runtime（sockets / logs / flags / snapshot） | Rust engine · API · scripts |
| `OPENCLAW_SECRETS_ROOT` | secrets/ 根（含 env_files + secret_files） | shell scripts（restart/clean/fresh） |
| `OPENCLAW_SECRETS_DIR` | secrets/secret_files/bybit（slot base） | Rust `bybit_rest_client` · Python `bybit_rest_client.py` · live_auth |
| `OPENCLAW_ARCHIVE_DIR` | archive（damaged_/fresh_start_ dumps） | clean_restart / fresh_start |
| `OPENCLAW_SRV_ROOT` | ⚠️ legacy alias，同 `OPENCLAW_BASE_DIR` | `bybit_path_policy.py` + 115 歷史 maintenance scripts — **新代碼請用 `OPENCLAW_BASE_DIR`**，兩者互不 fallback，Mac 部署時建議 `export` 同值 |

**Mac 差異注意**：`$HOME/.openclaw_runtime` **不會**在開機時被清（Linux `/tmp` 每次重啟清空），因此：
- `engine_maintenance.flag` 若上次異常留下會阻塞 watchdog → 開工前先 `rm -f "$OPENCLAW_DATA_DIR/engine_maintenance.flag"`
- 舊 socket 檔（`engine.sock` / `ai_service.sock`）殘留會讓新 process 拒綁 → 啟動前清或讓腳本 unlink 舊 socket
- 建議 Mac `.zshrc` 加 `alias oc-clean-runtime='rm -f "$OPENCLAW_DATA_DIR"/{*.sock,engine_maintenance.flag}'`

### 啟動檢查（每次 session 起點）

**Linux 端（trade-core 本地 session）**：
```bash
git status && git log --oneline -5
python3 helper_scripts/canary/engine_watchdog.py --data-dir "$OPENCLAW_DATA_DIR" --stale-threshold 45 --grace-period 120 --status
```

**Mac 端（SSH bridge workflow，2026-04-21 起）**：
```bash
git status && git log --oneline -5                                    # Mac 本地 repo 狀態
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -5"       # Linux repo 狀態（可能領先）
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status"  # engine 真實狀態
```
Mac 本地跑 watchdog 永遠回 `engine_alive: false`（engine 只跑 Linux，見 `memory/project_dev_runtime_split.md`）；必須透過 ssh 查。Mac 接手三連 = git status + ssh Linux git log + ssh Linux watchdog。

R-07 Go/No-Go 已 PASS（見 `memory/archive/project_rust_migration_status.md`）。watchdog 回 `engine_alive: false` 代表引擎沒在跑，按 TODO.md 重啟指引處理（Mac 端：`ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"`）。

### TODO.md 強制規則（每次接手必須遵守）

**接手時：** 必須讀 `TODO.md` 確認當前工作狀態，找第一個 `[ ]` 未完成項作為起點。用戶有明確指令時以用戶為準。

**發現新問題時：** 立即追加到 TODO.md，不等會話結束。

**修復完成後：** `[ ]` → `[x]`，追加完成 commit 號，更新測試基準線。

---

## 七、代碼與文檔規範

### ★★ 跨平台兼容性（強制，所有開發必須遵守）

**大前提：項目必須隨時可以部署在 macOS 上運行。**

1. **路徑不硬編碼** — 所有路徑使用環境變量或 config，禁止任何 user-home 絕對路徑字面值（`/home/ncyu/`、`/Users/ncyu/`、`/Users/<name>/…/TradeBot` 等）。
   用 `os.environ.get("OPENCLAW_BASE_DIR", ...)`、docker-compose 相對路徑（`../../settings/...`），或 `Path(__file__).parent` 相對路徑。
   E2 必查：`grep -E '(/home/ncyu|/Users/[^/]+)' <diff>` 新代碼命中 → 打回（歷史 worklog / dated snapshot / 政策反例引用不在此限）。

2. **LocalLLMClient 抽象乾淨** — 不洩漏 Ollama-specific 細節。
   所有 LLM 調用通過 `LocalLLMClient` ABC 接口（Phase 1 任務 1.8）。
   禁止在業務邏輯中直接調用 Ollama HTTP endpoint。

3. **服務部署可遷移** — systemd → launchd 遷移路徑清晰。
   服務配置邏輯寫成文檔或腳本（`helper_scripts/deploy/`）。
   不依賴 systemd-specific 特性（如 `sd_notify`）。

4. **依賴管理乾淨** — `requirements.txt` 保持更新，禁止隱式依賴。
   新增 `import` 時同步更新 requirements。E2 必查。
   避免 Linux-only 依賴（如 `psutil` 的 Linux 特定 API），需要時加平台守衛。

### 雙語注釋（強制）
每個新建/修改的函數、類、模塊必須中英對照注釋（MODULE_NOTE / docstring / inline / fail-closed 路徑 / 安全代碼）。E2 必查。

### 新 SQL migration 規範（強制，2026-04-24 V023 postmortem 新增）

**背景**：2026-04-23 `V023__model_registry.sql` 入 repo 但在 Linux 上**靜默 no-op** —— V004 早已預建了缺 `canary_status/verdict` 的 legacy `learning.model_registry` stub；`CREATE TABLE IF NOT EXISTS` 看到表存在就跳過，下游 Rust 讀 `canary_status` 全空。`helper_scripts/db/audit_migrations.py` 事後才能抓到。**更好的防線是 migration 內的 DO block guard，對 legacy drift 主動 RAISE**。

**規則**（4 條，E2 必查）：
1. **Guard A 強制**：任何 `CREATE TABLE IF NOT EXISTS schema.table (...)` **前必加**一個 DO block，驗表若已存在則必要欄位俱在；缺 ≥1 即 `RAISE EXCEPTION`。模板見 `sql/migrations/templates/schema_guard_template.sql § Guard A`。
2. **Guard B 強制（型別 matters 時）**：`ALTER TABLE ... ADD COLUMN IF NOT EXISTS col TYPE` 前，若該 column 類型錯會讓下游 writer 失敗，**必加** Guard B 驗 `information_schema.columns.data_type`；型別不符即 RAISE。模板同檔 § Guard B。
3. **Guard C（hot-path 索引選用）**：`CREATE INDEX IF NOT EXISTS` 若索引欄位組合關鍵（production 熱查詢依賴），加 Guard C 比對 `pg_get_indexdef()`；純 audit / 低頻索引可略。
4. **Idempotency 驗證**：每個新 migration 本地跑兩次 `psql -f V<NNN>__<desc>.sql`，第二次必須**不 RAISE**（shape 已正確時 guard no-op）。違反 = E2 打回。
5. **範例** retrofit：`sql/migrations/V023__model_registry.sql`（Guard A `learning.model_registry`）+ `sql/migrations/V021__fills_exit_source.sql`（Guard A `learning.decision_shadow_exits` + Guard B `trading.fills.exit_source` + Guard B `learning.decision_shadow_exits.ts`）。新 migration 以此兩檔為 reference。

**測試**：`sql/migrations/tests/test_schema_guards.sql` 提供 9 個單測（3 guard × {pass / fail / no-op}），無 pgTAP infra 下直接 `psql -d <test_db> -f` 跑；grep NOTICE 無 `FAIL` 即綠。

### Engine 自動遷移（opt-in，2026-04-24 Phase 2 新增）

**背景**：V023/V019/V021 silent-noop postmortem 顯示 100% 手動 `psql < V*.sql` 會漏套用。Phase 2 在 `openclaw_engine` 啟動時加一條 opt-in 自動遷移管線，**預設關**，operator 逐步驗證後再開。

**兩條套用路徑並存**：
- **手動（預設）**：`bash helper_scripts/linux_bootstrap_db.sh --apply` — 既有流程不動，此 Phase 不移除。
- **自動（opt-in）**：環境變數 `OPENCLAW_AUTO_MIGRATE=1` 時，engine 啟動在 DbPool 連線後、writer 啟動前呼叫 `openclaw_engine::database::migrations::MigrationRunner::run_if_enabled()`：
  1. 自刻 parser 讀 `sql/migrations/V###__*.sql`（sqlx 內建 parser 不吃 Flyway 格式）；`V017_rollback.sql` / `V999__*.sql` 依檔名過濾。
  2. 若 `_sqlx_migrations` 空且 `learning.model_registry` 存在（V023 canary），seed V001-V023 為「已套用」狀態 — 符合 2026-04-24 postmortem 後的 live DB 狀態。
  3. 跑 `Migrator::run_direct` 套用 pending（目前無，V024+ 時才會有）；checksum 比對失敗 / 曖昧狀態 / canary 不成立 → 中止啟動（`exit 1`），**不靜默吞**。
- **安全準則**：ambiguous state（有 app schema 但無 V023 canary）= 硬性 RAISE，不自動猜測；operator 跑 `helper_scripts/db/audit_migrations.py` 後人工介入。

**Rollback path（engine refuse to start）**：若 `OPENCLAW_AUTO_MIGRATE=1` 打開後 engine 不肯啟動，operator 立即：
1. Stop engine（`restart_all.sh --stop`）。
2. 關 env：`unset OPENCLAW_AUTO_MIGRATE` 或 env file 改回空。
3. 回到手動流程 `bash helper_scripts/linux_bootstrap_db.sh --apply` 補任何 pending migration。
4. 重啟 engine（`--rebuild` 非必要，除非改了 Rust 碼）。

**測試**：`rust/openclaw_engine/src/database/migrations.rs` 15 個 unit tests（純解析 / 無 DB）+ `rust/openclaw_engine/tests/migrations_test.rs` 5 個整合測試（需 `OPENCLAW_TEST_PG` 連線字串；無則自動跳過；`fresh_db_applies_all_migrations_end_to_end` 另需 `OPENCLAW_TEST_PG_DESTRUCTIVE=1` ack）。

### 被動等待 TODO 必附 healthcheck（強制，2026-04-23 新增）

**背景**：2026-04-22 P0-13 ATR scale + P0-14 edge miss 雙 bug 經「被動等待 24h observation」流程放行；後續 review 才發現 7d `phys_lock` 0 fire 其實是 silent-dead，observation window 本身無法偵測。結論：**任何「被動等待 Nd / Nw」的 TODO 必須同步附一條可執行 healthcheck**，由 cron 或 operator 手動間隔跑，確認被動等待的前提（pipeline 活著 / 信號流通 / fires 發生中）仍成立。缺此項 = 無法區分「沒事所以沒動」vs「壞了所以沒動」。

**規則**（4 條，E2 必查）：
1. **登記門檻**：TODO 新增「被動等待 Nd / Nw」類條目時，必須同時：(a) 在 `helper_scripts/db/passive_wait_healthcheck.py` 加一個 `check_*()` function（通常 1 SQL or 1 oneliner）;(b) TODO 文本引用該 check id。
2. **檢查語意**：check 回 `"PASS" / "WARN" / "FAIL"`，**Exit 1 = silent-dead 自動偵測** — 不是「沒資料」就 PASS。若被動等待假設「每 N 小時該有 ≥1 次 fire」，check 就要驗 fire count ≥ 1 and ts > now() - N hours。
3. **節奏建議**：operator 每 6h cron 跑 `passive_wait_healthcheck.py`，任一 FAIL 即檢查該 TODO 的前提是否仍成立。本檔已有 7 個 check（close_fills / label_backfill / exit_features_writer / phys_lock / micro_profit / trailing_stop / edge_estimates freshness），新增按此樣式追加即可。
4. **違規處理**：新增被動等待 TODO 未附 healthcheck = E2 審查打回；已有被動等待 TODO 若對應 pipeline 沒 healthcheck 覆蓋 = 下一輪維護週期必補。

**觸發情境例**：
- 「等 21d demo 穩定」→ check：demo engine_alive last 24h + 0 engine_crash 次數
- 「等 7d counterfactual replay」→ check：replay 結果檔存在且 mtime > script last run
- 「等 1w PostOnly fee 驗證」→ check：maker fill rate > X% 且 demo fee 降幅達標

### 強制同步規則
- **Sprint/Wave 完成**：更新 §三 + §十一 + `docs/CLAUDE_CHANGELOG.md` + README，與生產代碼同 commit
- **§三 衛生規則（強制）**：§三 只記載「現況/活躍狀態」+「過去 ≤2 天的完成里程碑」。**任何完成里程碑當天 +2 日（以 `currentDate` 為準）必須在 commit 同次操作中歸檔到 `docs/archive/YYYY-MM-DD--claude_md_section3_*.md`** 並從 §三 刪除，僅在「已完成里程碑索引」表保留 1 行條目。違反 = §三 膨脹回 ~10K tokens、context 提早撞 compact。
- **§三 敘述 vs runtime drift 防線（強制，2026-04-24 G6-04 V023 postmortem 衍生）**：§三 任何「runtime 數值 + 狀態」（cell count / row count / fill rate / binary mtime / commit progress / fire 次數）必註明採集時間 + 對應 healthcheck id；滿 7 日未經自動化重驗即必須更新或從 §三 刪除；CC 收到 §三 數字當決策輸入時必先實測 source-of-truth 才採納，發現 drift 同 commit 修。詳 `docs/lessons.md` 條目「2026-04-24 · CLAUDE.md §三 敘述 vs runtime drift」。E2 必查。
- **Commit 時**：摘要追加到 `docs/CLAUDE_CHANGELOG.md` 頂部，格式 `### 標題（YYYY-MM-DD · commit XXXXXXX）`
- **Context ≥90%**：立即寫 `docs/worklogs/YYYY-MM-DD--session_progress_N.md`（已完成/進行中/未完成/決策/下一步）
- **每日整合**：當天 worklog 碎片合併為 `YYYY-MM-DD--daily_summary.md`，刪碎片
- **新腳本**：MODULE_NOTE 雙語 + latest+dated 輸出 + contract check + 更新 SCRIPT_INDEX.md
- **docs/**：分類目錄 + `YYYY-MM-DD--描述.md` + 更新 `docs/README.md` 索引

### 本地 LLM 審核協作（Mac 環境，強制）

Operator 在 Mac 並行跑 Qwen3.6-35B（LM Studio）做代碼審核。CC 每完成一個任務，必寫結構化報告至：

    .claude_reports/YYYYMMDD_HHMMSS_<短描述>.md

（`.claude_reports/` 在 `.gitignore`，僅本機留存；供本地 LLM 審核 + 開發編年史 — 與 `docs/worklogs/` 職能互補：worklog 是會話時序流水，claude_report 是單任務審核單位）

**6 節必備**（中文，繁簡皆可）：
1. **任務摘要** — operator 意圖白話重述 + 完成狀態
2. **修改清單** — 逐檔 `path | 新增/修改/刪除 | 行數 | 一句話說明`
3. **關鍵 diff** — 最能說明變更的片段（非全量）
4. **治理對照** — 涉及的 DOC/SM/EX/P0 編號 + 符合 / 違反 / 未規範 / 建議修改文件
5. **不確定之處** — 未確認假設 / 跨平台風險（對照 §七.★★）/ 測試覆蓋判斷
6. **Operator 下一步** — 審查重點 / Mac CC 透過 SSH bridge 已做的驗證（cargo test / psql / engine log）/ 若需 operator 親自動手的步驟（high-risk per-case 授權項 / Linux 端 interactive 操作）

**Git 自動化（強制，2026-04-21 operator 加嚴：所有 commit 必 push）**：
- CC 每完成一個**合理可交付單位**（任務完成 + 本節 report 已寫 + 無跑不過的測試）→ 自動 `git add` + `git commit` + **`git push origin main`**（三者同 Bash 鏈內完成，不允許 commit 後留著沒 push 就結束回合）
- **無例外**：Mac CC / Linux CC 都遵守「commit 即 push」；維持 Mac / Linux / origin 三處 state 一致性
- **Session 接手三連 sync**（所有 CC 起手必做）：`git fetch --prune origin` + 若 local 落後 `git pull --ff-only` + 若 local 超前（前 session 漏 push）`git push origin main` —— 例行自動做，不待 operator 提醒
- **Mac CC 觸發 Linux 驗證前**：push 完接 `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"` 同步 Linux 工作樹
- **ff-only pull 失敗（divergent branches）**：報告 operator，不擅自 merge/rebase（CC 本地規則仍禁這 3 op）
- 詳 memory `project_ssh_bridge_workflow.md`「硬規則：commit 完必 push」章節
- **CC 絕不執行**：`pull` / `merge` / `checkout` / `reset` / `rebase`（狀態變更操作留給 operator）

### Mac dev-only 模式（環境檢測 + 操作細節）

**環境檢測**：CC 從 system prompt `Platform:` 讀取，**不分大小寫**做子串比對：含 `darwin` → Mac dev-only · 含 `linux` → trade-core 生產（Linux session 實測回 `Linux`，Mac 回 `darwin`）。下面 4 條僅在 Mac 端生效，**不必詢問 operator**。

1. **pytest 必從 srv root 跑** — 部分測試用絕對 import `from program_code.…`，從 `control_api_v1/` 內跑會 `ImportError: No module named 'program_code'`（例：`test_earned_trust_engine.py`）。
2. **整合測試打真實 Bybit 會 fail —— by design** — 3 個 secret slot 已 rename 為 `*.dev_disabled_*`（避免與 Linux trade-core 撞單；還原見 README § Mac dev-only 模式）。任何 connect 真實 Bybit 的 test 拿不到 credentials → fail-closed。Mock-based unit test 不受影響。**Reproduce release 基準**（engine lib 1827 / 0 failed 等）現可 `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"` 直驗，不需要離開 Mac session。
3. **Sub-agent (E1) 寫碼若 refuse** — Linux 端 2026-04-19「第 3 次驗證解除」refuse pattern，但跨平台/跨 session 仍偶發。Workaround：主 session 直接寫。
4. **Mac↔Linux SSH bridge workflow（2026-04-21 採納，取代原「同步單向」）** — 詳 memory `project_ssh_bridge_workflow.md`。核心：Mac CC 為 SSOT，透過 `ssh trade-core`（Tailscale + key auth，免密碼）遠端觸發 Linux runtime 任務（cargo test / psql / restart_all / git 操作 / engine log）。
   - ✅ **Mac 本地 git 放寬**：允許 `git fetch` + `git pull --ff-only`（純 fast-forward，衝突時 abort 不破壞 state）；**仍禁** `git merge <branch>` / `rebase` / `reset --hard` / `checkout <branch>`
   - ✅ **SSH 允許**：ssh trade-core 跑 cargo/psql/git pull&push/restart_all/tail log/watchdog/rm tmp sentinel
   - 🚫 **SSH 需 operator per-case 授權**：觸及 live API/authorization.json/secrets、刪 remote branch（本 session 已試 trigger guardrail 成功擋住）、刪 worktree、DROP/TRUNCATE table 資料、改 risk_config TOML
   - **工作流**：Mac 寫碼 → `git add/commit/push` → `ssh trade-core "git pull --ff-only && cargo test --release"` → 看結果 → 綠就完成，紅就回頭 fix。**不再派 Linux CC 做寫 prompt 的 round-trip**（除非需要 interactive rebase/amend 等 Mac CC 禁做的動作）。
   - **Linux CC 剩餘職能**：24h 守夜監控、interactive git 操作、operator 急令 hotfix、Mac CC 離線時兜底。

---

## 八、工作流編排、16 Agent 角色與自我改進循環

### ★ 工作流編排 6 條 + 3 底線（2026-04-22 operator 指令融合）

1. **規劃優先 Plan-First**：非平凡任務（≥3 步 / 涉架構決策）先進規劃模式再動手；前期寫詳細 spec 減歧義；過程遇阻即停重規劃，**禁強推**；驗證階段同樣套規劃節點。Auto mode 下放寬「開工前 operator confirm」，但規劃思考仍要做。
2. **Sub-agent 卸載**：研究/探索/並行分析一律派 sub-agent 保主上下文整潔；一 agent 一任務精準執行；複雜問題投更多算力。詳 memory `feedback_subagent_first.md`。
3. **自我改進循環**：operator 任何糾正 → 抽模式寫 `docs/lessons.md`（場景 / 錯誤模式 / 預防規則 / 相關檔案）；會話起手掃近期相關條目；對錯誤率無情迭代。lessons.md = 可 grep 技術/流程錯誤庫，與 auto-memory `feedback_*.md`（跨 session 偏好）互補不重複。
4. **完成前驗證 Verify-Before-Done**：永不先標 done；跑測試 / 查 log / 對比 main 分支行為差 / 自問「senior engineer + FA 會 approve 嗎？」。強化既有 E2/E4 + memory `feedback_working_principles.md` 原則 3 對抗性驗證。
5. **追求優雅（平衡）**：非平凡修改前停問「有更優雅方式嗎？」；修復像 patch 就重做「基於現在所知一切實作優雅解」；**簡單/明顯修復跳過本條禁過度設計**。
6. **自主 bug 修復**：收到 bug 直接修；指 log/錯誤/失敗測試再解；CI 紅直接修不等手把手；operator 零上下文切換。詳 memory `feedback_minimal_confirmation.md`。

**3 條核心底線**：**簡單優先**（只動必要代碼，禁無關重構） · **不偷懶**（找 root cause，禁臨時 patch，senior/FA 標準） · **最小影響**（變更只觸必要部分，禁引 bug）。

**會話任務管理 6 步**（與 §六 TODO.md 強制規則同體，流程化版）：1) TODO.md 先寫 checkbox 計畫 → 2) 開工前 operator confirm（auto mode 跳過）→ 3) 逐步勾選進度 → 4) 每步高階摘要 → 5) TODO.md 結尾補 Review 章節 → 6) 任何糾正後寫入 `docs/lessons.md`。

### 18 Agent 角色體系與強制工作鏈（2026-04-25 真實接線）

**真實接線**：18 個 subagent definition 在 `.claude/agents/<NAME>.md`（git tracked，雙端 git 同步）。每個 agent 含 Anthropic 官方 frontmatter（`tools` / `disallowedTools` / `skills` 預載 / `color` / `model: inherit`）+ 啟動序列（讀 `docs/CCAgentWorkSpace/<NAME>/{profile,memory}.md` + 最新 report）+ 完成序列（追加 memory + 存 `workspace/reports/`）。CCAgentWorkSpace 仍是 SSOT，`.claude/agents/<NAME>.md` 是路由器；完整角色定義見各 `profile.md`，激活矩陣見 `docs/CLAUDE_REFERENCE.md`。

**主會話 = PM + Conductor**（合一，**非** subagent）。Anthropic 限制：subagent 不能 spawn 另一 subagent — 派發鏈必須由主會話編排。

**18 Agent 速查**（typeahead `@<NAME>` 直呼）：

| Tier | Agents |
|---|---|
| 管理層 | `@PM` `@FA` `@PA` |
| 質量保證層 | `@CC` `@E2` `@E3` `@E4` `@E5` |
| 執行層 | `@E1` `@E1a` |
| 專項審查層 | `@A3` `@R4` `@TW` |
| 分析顧問層 | `@AI-E` `@QA` `@QC` `@BB` `@MIT` |

**Invocation 三種 pattern**（Anthropic 官方）：
1. **Natural language 自動 delegate**：「讓 QC 看一下這個策略」→ Claude 主動 delegate（基於 description "Use proactively for..." 匹配）
2. **`@-mention` 強制**：`@QC` → 100% trigger 該 agent，不交 Claude 判斷
3. **Session-wide**：`claude --agent QC` → 整個 session 走該 agent system prompt + tool 限制

**何時用哪個**：
- **強制工作鏈**（不可跳過）→ **@-mention**：`@E1` 完 → `@E2` → `@E4` → `@QA` → PM Sign-off
- **多角色 adversarial review**（重大決策） → **@-mention 並行**：`@QC` + `@FA` + `@CC` + `@PM`（memory `feedback_multi_role_strategic_review`）
- **Routine 探索 / 分析** → **natural language**：「研究 ML pipeline 狀態」→ Claude 自動派 `@MIT`
- **長時間單角色任務** → **`--agent`**：例如整個 session 跑 QC audit

**標準工作鏈**（強制，memory `feedback_workflow_audit_chain`）：
`PM` + `@FA` 規格 → `@PA` 派發 → `@E1` / `@E1a` 並行 → **`@E2` 代碼審查 → `@E4` 測試回歸**（兩者絕不可跳）→ `@E5` 優化（每 Phase / Wave / ≥3 E1 任務強制）→ `@QA` → PM 確認。`@E3` / `@CC` / `@A3` / `@R4` / `@TW` / `@BB` 按需插入。`@AI-E` 季度跑。`@QC` 新策略提案 / 數學審計必活。`@MIT` ML pipeline / DB schema 審計必活。
**P0 快速通道**：`@PA` → `@E1`（≤5 並行）→ `@E2` → `@E4` → PM。可省 FA / E5 / E3 / CC，但 E2 + E4 永不跳。

**動態 isolation 派工準則**（PM 編排時 per-invocation 決定，避免 branch 過多）：
- 單實例 sub-agent 操作單檔 → **NOT** isolation（主 work tree）
- 並行 ≥2 sub-agent 操作不重疊檔 → **NOT** isolation
- 並行 ≥2 sub-agent 操作可能重疊檔 → 對重疊組加 `isolation: worktree` per-invocation
- destructive 動作（git reset / 大量 rm / 跨檔重構）→ 加 isolation（即使單實例）
- 純審查類（CC/QC/A3/R4/TW/E2 讀/E3/AI-E/PM/FA/PA/BB/MIT）→ **永不需要** isolation

**Skill 預載 vs 按需 Read**：
- **OpenClaw 24 個 custom skill** 在 `.claude/skills/<name>/SKILL.md`（git tracked）— agent frontmatter `skills:` 預載相關子集（自動注入 system prompt）
- **K-Dense-AI 134 個 scientific skill** 在 `~/.claude/skills/k-dense-ai/scientific-skills/<name>/`（user-level，Mac + Linux 各自 clone 一次）— agent body 寫路徑供按需 Read（**非** always-on，避免 trigger 噪音）

**雙端部署**（memory `project_18_agent_runtime_wired`）：
- Master：`srv/.claude/{skills,agents}/`（git tracked，`.gitignore` 對 `.claude/*` ignore 但 `!.claude/skills/`、`!.claude/agents/` 例外；`settings.local.json` + `worktrees/` 仍 ignore）
- Mac CC cwd `/Users/ncyu/Projects/TradeBot`：symlink `.claude/{skills,agents}` → `../srv/.claude/...`
- Linux CC cwd `~/BybitOpenClaw/srv/`：直讀 srv/.claude/
- 同步：Mac edit → `cd srv && git add + commit + push` → Linux `git pull --ff-only`
- 新 session 起手 / 修改 agent definition 後：`/agents` 重 load 或 restart CC

**Bybit API 強制**：所有 Bybit 相關開發（REST/WS/IPC）先查字典手冊 `docs/references/2026-04-04--bybit_api_reference.md`，新增端點同步更新手冊，`@E2` 必查；`@BB` 從 Bybit 立場 push back 違規設計。審計：`docs/audits/2026-04-04--bybit_api_infra_audit.md`。

---

## 九、代碼結構約定

### 文件大小限制
- **800 行** ⚠️ 警告線（E2 必須標記）
- **1200 行** 🛑 硬上限（不允許 merge）

**Pre-existing baseline exception clause（2026-04-28 governance addition per Wave E E2 retroactive review MED-1）**：當檔案在某個 wave 開工前的 baseline 已超過 1200 行（pre-existing violation 來自更早歷史），允許下列例外處理：
- **(1) 接受 wave 後 LOC ≤ pre-existing baseline + 5 LOC**（wave 不擴大違規幅度，且純 cleanup wave 應顯著減少 LOC）
- **(2) 同時開新 P2 ticket** 處理 pre-existing violation（如 `<FILE>-PRE-EXISTING-CLEANUP P2`），標明「ETA next maintenance wave」
- **(3) PM Sign-off 必明文記錄** governance exception accept 理由（避免 silent drift）

此例外 **僅適用 pre-existing 1200 + violation**，不適用「新 wave 把 ≤1200 推到 >1200」的場景（後者必拒）。E2 retroactive review 時引此條款判斷 governance accept vs RETURN to E1。範例：Wave E `2f88c40` main.rs 1208(pre-existing) → 1230(Wave 1 deepens) → 1210(Wave E split shrinks Wave 1 contribution +22→+2)，PM accept 1210 短期 + 開 MAIN-RS-PRE-EXISTING-CLEANUP P2 → Wave G `54e468a` 完成清零至 1158（解 baseline + 留 +42 headroom）。

### 模塊依賴方向（禁止循環 import）
```
state_models ← state_compiler ← state_store ← main_legacy ← main.py
其他 route 文件 ← main_legacy（通過 from . import main_legacy as base）
```

### Monkey-patch 安全
被 main.py patch 的函數（compile_state / STORE / envelope_response 等），新模塊必須通過 `main_legacy` 命名空間間接引用，不可直接 import 原始版本。

### Singleton 管理
| Singleton | 創建位置 | 導入方式 |
|-----------|---------|---------|
| `settings` | main_legacy.py | `base.settings` |
| `STORE` | main_legacy.py（main.py 重建） | `base.STORE` |
| `app` | main_legacy.py | `base.app` |
| `limiter` | main_legacy.py | `base.limiter` |
| `_pool` | db_pool.py | `from .db_pool import get_conn` |
| `DEFAULT_LEASE_TTL_CONFIG` | lease_ttl_config.py | `from .lease_ttl_config import DEFAULT_LEASE_TTL_CONFIG` |
| `_backtest_engine` | backtest_routes.py | 內部懶加載 `_get_backtest_engine()` |
| `_scheduler` | evolution_auto_scheduler.py | 內部懶加載 `start_scheduler()` |
| `_evolution_engine` | evolution_routes.py | 內部懶加載 `get_evolution_engine()` |
| `_ledger` | experiment_routes.py | 內部懶加載 `get_experiment_ledger()` |
| `LeaseTTLConfigManager._instance` | lease_ttl_config.py | `LeaseTTLConfigManager.get_instance()` |
| `_BYBIT_CLIENT` / `_BYBIT_CLIENT_AVAILABLE` | strategy_ai_routes.py | 內部懶加載 `_get_rust_client()`（PYO3-ELIMINATE-1 Phase 2 後指向 `app.bybit_rest_client.BybitClient` 純 httpx；函數名為 grep-stability 保留） |
| `KLINE_MANAGER` / `INDICATOR_ENGINE` / `SIGNAL_ENGINE` / `ORCHESTRATOR` 等 12+ | strategy_wiring.py | 模組級全局，import 時初始化 |
| `SCOUT_AGENT` | strategy_wiring.py:143（建構＋start）；scout_routes.py:61（mutable handle，由 `set_scout_agent()` 寫入） | 模組級全局，import 時初始化；外部直接 `from .strategy_wiring import SCOUT_AGENT` 或經 scout_routes 模組屬性。G3-08-FUP-MAF-SPLIT-CLEANUP P3 補登（pre-existing gap，2026-04-28；class 定義於 `scout_agent.py`，maf 經 PEP 562 `__getattr__` lazy re-export 維持向後相容） |
| `_SHARED_IPC_SLOTS` / `_SHARED_SLOT_LOCK` | ipc_dispatch.py | 內部懶加載 `get_or_connect_shared_client(slot_key)`（E5-P1-5） |
| `_<AGENT>_AUDIT_CB` / `_GOV_HUB_FOR_<AGENT>` × 5（Scout/Strategist/Guardian/Analyst/Executor） | strategy_wiring.py | 模組級，由 `agent_audit_bridge.make_agent_audit_callback(...)` 構造；各 agent ctor 注入 `audit_callback`（E5-FN-3 Analyst pilot + FN-3-FUP-a~d 4 agents 補接線）。ImportError 時 GOV_HUB=None → bridge fail-open 靜默丟事件。`agent_audit_bridge` 本身無狀態工廠（不持 singleton） |
| `_scheduler` / `_scheduler_lock` | edge_estimator_scheduler.py | 內部懶加載 `start_scheduler()`（P1-7 B JS estimator，每小時 cycle）。QC-3 audit FUP 補登（2026-04-23） |
| `_LEADER_LOCK_FD` / `_LEADER_LOCK_PATH` | edge_estimator_scheduler.py | 模組級全局；`_acquire_leader_lock()` 取得 flock fd 後寫入，OS 進程退出自動釋放（含 SIGKILL）。uvicorn --workers 4 leader election sentinel。測試用 `_reset_for_tests()` 釋放。EDGE-SCHEDULER-LEADER-1（2026-04-23 `f32629c`）|
| `_CACHE_INSTANCE` / `_CACHE_LOCK` | executor_config_cache.py | 內部懶加載 `get_executor_config_cache()`；G3-03 Phase B（2026-04-25）。process-global ``ExecutorConfigCache`` 持 Rust ``RiskConfig.executor`` 子切片快照（背景 daemon thread 每 N 秒 IPC poll，預設 10s 由 `OPENCLAW_EXECUTOR_CACHE_POLL_SEC` 覆寫）；首次 IPC 成功前 fail-closed 預設 `shadow_mode=True`，IPC 暫時失敗保留前一個好 snapshot。`shadow_mode_provider()` lambda 注入 ``ExecutorAgent`` ctor 取代原 `_shadow_mode = True` 硬編碼（CLAUDE.md §二 原則 #3 fix）。`strategy_wiring.py:467` 區段 init + `start_polling()`。測試用 `_reset_for_tests()` 釋放 |
| `_H_STATE_INVALIDATOR` / `_LOCK` | h_state_invalidator.py | 內部懶加載 `init_h_state_invalidator()`；G3-08 Phase 1C（2026-04-26）條件 spawn — 嚴格 `OPENCLAW_H_STATE_GATEWAY=="1"` 才建構 singleton，否則 `invalidate_async()` no-op 零負擔。Process-global ``HStateInvalidator`` 是 Python→Rust 失效提示通道（資料流與 G3-03 ExecutorConfigCache 相反）：每次 H1-H5 / 5-Agent 狀態變化由 fire-and-forget daemon thread + 私有 ``EngineIPCClient`` + ``asyncio.new_event_loop()`` 推送 ``invalidate_h_state`` JSON-RPC notification，提早 Rust ``h_state_cache`` poller 的 ad-hoc poll；Rust 端 10s 排程 poll 永遠仍會發生，漏一次提示最多多 ≤10s 過時、不破壞正確性。所有 IPC 例外於內部三層 try/except 吞掉（CLAUDE.md §二 原則 #6 fail-closed）。Wire site：`strategy_wiring_h_state.py`（STRATEGY-WIRING-SPLIT P2，2026-04-28；前為 `strategy_wiring.py:535`），`strategy_wiring.py` re-import 保 `app.strategy_wiring._H_STATE_INVALIDATOR` 屬性 grep 穩定。測試用 `_reset_for_tests()` 釋放 |
| `MARKET_SCANNER` / `AUTO_DEPLOYER` / `_SCOUT_WORKER` | strategy_wiring_scanner.py | `wire_market_scanner_and_workers(...)` 函數呼叫返回 `ScannerWiringResult`；`strategy_wiring.py` 在原 init 順序位置呼叫並 bind 回 module attribute（保 `app.strategy_wiring.MARKET_SCANNER` / `AUTO_DEPLOYER` 屬性 — 下游 `strategy_read_routes` / `strategy_write_routes` `from .strategy_wiring import MARKET_SCANNER, AUTO_DEPLOYER` 不破，`h_state_collectors` `getattr(_sw, ...)` 不破）。MarketScanner = 5-min linear+spot 機會掃描；StrategyAutoDeployer = max_symbols=30 / risk 3% / pinned BTCUSDT,ETHUSDT / spot reserved 5；ScoutWorker = 30-min 情報注入 ScoutAgent → MessageBus → Strategist。3 子塊 fail-open（任何一個 except → 該 singleton=None，主管線繼續）。STRATEGY-WIRING-SPLIT P2（2026-04-28）抽出 |
| `HStateCacheSlot` | rust/openclaw_engine/src/ipc_server/slots.rs | Rust 端 `Arc<RwLock<Option<Arc<HStateCache>>>>` late-injected slot pattern（G3-08 Phase 1A，commit `aa287c4`）。env=0 時 `main_boot_tasks::spawn_h_state_poller_if_enabled()` 跳過 spawn → slot 維持 `None` → `query_h_state` hot-path lookup 回 `None`、`get_h_state_status` 回 uninitialized；env=1 時建構 `Arc<HStateCache>` + spawn tokio daemon 每 10s pull `query_h_state_full` Python IPC + 收 `invalidate_h_state` 提示觸發 ad-hoc poll，DashMap shard lookup ≤1ms p99 達 hot-path SLA。Python crash → Rust 沿用 last good snapshot 並在 `staleness_ms > 30s` 時標 stale flag（fail-soft，CLAUDE.md §二 原則 #5/#9）。Schema 演化 forward-compat：`AgentState.stats: HashMap<String, i64>` + `#[serde(default)]` 吸收新欄位免 lock-step deploy |
| `CostEdgeAdvisorDbSlot` | rust/openclaw_engine/src/cost_edge_advisor_boot.rs | Rust 端 `Arc<tokio::sync::RwLock<Option<Arc<DbPool>>>>` late-injected slot pattern（G3-09 Phase B，2026-04-28；2026-04-28 Wave E split 從 main_boot_tasks.rs 移出至 cost_edge_advisor_boot.rs sibling per E2 PB1 LOC review）。鏡 `HStateCacheSlot` 設計：DB pool 啟動時延後注入 cost_edge_advisor daemon，30s populate-timeout；slot=None 時 daemon fallback 到 in-memory counter（不寫 `learning.cost_edge_advisor_log`），slot 注入後改走 DB INSERT 路徑。Engine restart 自動清空（`Arc` 隨 process 結束 drop）。Phase A advisor.evaluate() 不依賴此 slot — 純為 Phase B INSERT path 加 forward-compat（Phase A 評估邏輯仍跑於 in-memory，slot 注入後純加 persist 副作用）。HMAC secret 與 main loop 解耦，符合 CLAUDE.md §二 原則 #6（失敗默認收縮）+ 原則 #8（可審計） |

新增 singleton 必須在此表登記。禁止子模塊創建未登記的全局可變狀態。

### 其他
- Route Handler 只做 parse → call → format，不含業務邏輯
- 新 Pydantic model 放 `*_models.py` 或所屬模塊，不加入 main_legacy.py

---

## 十、下一步工作指針

**當前焦點**：活躍任務與週次排期以 `TODO.md` 為準（P0/P1/P2/P3/P4 分層）。CLAUDE.md 不重複列週。

**關鍵路徑（2026-04-30 校準後）**：
`post-deploy edge observation + dust residual runtime proof → G1-04/G2-02/G2-01 time-driven decisions → P0-3 edge decision → LG-2/3/4/5 → true live`
- **最早 Live 日期**（事件驅動，非 hard date）：仍以 2026-05-23 樂觀 / 2026-05-30 中位 / 2026-06-15 悲觀為規劃帶，但需先通過 P0-3 edge decision。
- **當前 active gates**：`[33]` maker quality, `[38]` grid lifecycle, `[40]` realized edge, dust residual full-close proof, and MLDE live-governed boundary.
- 詳見 `TODO.md` current active block；TODO 保留 v3 單一時間軸記錄，已確認過時的 active-mainline 段落另歸檔。

**路線圖**：Phase 0-6、Live GUI、5-Agent/H1-H5 基礎接線、Executor shadow toggle、MLDE demo autonomy、Strategy Edge Repair、Strategy Edge Models、Dust residual prevention 均已落地。仍未完成的是正 edge / execution-quality 驗收、P0-3 decision、Live Gate LG-2/3/4/5、以及 true live 授權後的受監督/受限自主放權。

**Live 前置**：LIVE-GUARD-1 + LIVE-GATE-BINDING-1 代碼已存在；LiveDemo/live runtime currently authorized. True live still requires valid signed authorization, operator role auth, Rust hard gates, GovernanceHub/Decision Lease, and P0-3 edge decision. API key 填入 ≠ 即可上線。

**關鍵文件指針**（按需 Read，不要全載入）：
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-30 22:28 CEST：**current code-bearing runtime checkpoint is active and healthcheck is WARN, but edge remains at-risk** — Strategy Edge Models + Dust residual prevention + MLDE demo autonomy are deployed; dust full-close behavior is proven on real Demo/LiveDemo `qty=0` close fills; post-reload maker execution is now near target, but rolling `[33]` and realized `[40]` remain below acceptance and `[38]` grid lifecycle drift is still WARN. Next work is G2-02/G2-01/P0-3 time-driven decisions. True live autonomy remains gated by GovernanceHub + Decision Lease + 5 live gates.

---

## 十二、外部整合工具映射（**Linear-only active** posture）

**核心原則**：**git `srv/` 是唯一 source of truth**。外部工具僅為 *view layer*、*artifact store*，永不擁有交易參數 / 代碼 / 政策的權威。任何衝突一律以 git 為準。

**Posture（2026-04-29 operator 簡化決定）**：**Linear 是唯一 active workflow tool**。其他工具不融入工作流（不寫 SOP gate、不要求每 Wave 更新）。

### `.codex/` 平行目錄角色（2026-05-02 operator 決定 · AUDIT-2026-05-02-P2-4）

`.codex/` 是 codex session 用的**純提示輔助目錄**（git tracked，方便雙端 sync），**不擁有任何治理權**：

- **唯一 governance SoT**：`CLAUDE.md` + `TODO.md` + `.claude/agents/<NAME>.md` + `docs/CCAgentWorkSpace/<NAME>/{profile,memory}.md`
- `.codex/agents/*.md` / `.codex/skills/INDEX.md` / `.codex/AGENT_DISPATCH_PROTOCOL.md` 等 = codex session 啟動時的**提示鏡像**，與 `.claude/agents/` 內容衝突時**一律以 `.claude/agents/` 為準**
- `.codex/MEMORY.md` / `.codex/WORKLOG.md` / `.codex/DISPATCH_LEDGER.md` = codex session 的工作流水筆記，等同 `docs/CCAgentWorkSpace/<NAME>/memory.md` 的 codex 版本，但**不替代** Claude 端 memory；CC 不需閱讀 `.codex/*` 來做決策
- 變更治理規則時：先改 CLAUDE.md / `.claude/agents/`，再人工或 codex 自己同步 `.codex/`；**禁止**反向（`.codex/` → CLAUDE.md）
- 若 `.codex/` 與 CLAUDE.md drift：以 CLAUDE.md 為準，drift 由 codex session 自行修復

**Why option (a) not (b)/(c)**：(a) 零破壞、保留 codex 自走；(b) symlink 把 codex 拖進 Anthropic frontmatter 約束反而限制 codex；(c) 移除可能讓 codex 失去入口導致每次 session 重新 bootstrap。 

### 工具狀態表（2026-04-29 終版）

| 工具 | 狀態 | 用途 | 維護要求 |
|---|---|---|---|
| `srv/` git | **Source of truth** | 代碼 / CLAUDE.md / TODO.md / memory / docs | 每 commit 強制 |
| **Linear** | **🟢 ACTIVE** | 62-finding remediation tracker | Wave/Batch Sign-off 後主會話更新對應父 issue |
| **Notion** | **❄️ FROZEN**（保留但不維護） | 2026-04-29 bootstrap 快照（5 pages） | **不要更新** — operator 決定不融入工作流 |
| **Google Drive** | **🟡 PASSIVE** | 按需 binary artifact（PDF / screenshot） | 0 SOP；只在 operator 明確要求才用 |
| **Coupler.io** | **❌ DECLINED** | — | 不啟用 dataflow；連接器 slot 留著零成本 |
| **MotherDuck** | **❌ DECLINED** | — | 同上（已移除 connector） |
| **Slack** | **❌ DECLINED**（may revisit pre-live ~2026-05-15） | — | 不 authenticate；live 前 2 週評估純 alert channel |

### Bootstrap 入口

- **Linear**：team `NCYu` · project [`OpenClaw 62-Finding Remediation`](https://linear.app/ncyu/project/openclaw-62-finding-remediation-de1bc8f68e42) · 6 milestones (Batch A-F) · 7 labels (P1/P2/P3/live-release-blocker/backlog/time-driven/edge-diag) · 12 issues (`NCY-5..16`)
- **Notion (frozen)**：[OpenClaw — Operator Hub](https://www.notion.so/350dcd3b1eff81038de2d10874ae0fe4) — 5 pages 為 2026-04-29 快照，內容保留但**不再同步**；任何看到的條目需以 git 為準

### SOP（簡化版）

#### PM（主會話 / Conductor）
1. Wave / Batch Sign-off git commit landed 之後：
   - 更新對應 Linear 父 issue（description checklist + status flip）
   - **Notion 不更新**（凍結快照）
2. 新 finding：判斷是否屬 mainline（62-finding / time-driven / 重要 backlog），是則建 Linear issue；否則只進 TODO.md
3. **不要**把 TODO.md 全鏡像 Linear；只篩 mainline / time-driven cutoff items

#### PA / 審計 agents
1. RFC / audit 寫入 `docs/CCAgentWorkSpace/.../reports/` 或 `docs/audits/` / `.claude_reports/`
2. **不要**寫 Notion（凍結）；**不要**直接寫 Linear（PM 提案）
3. 若產生新 finding 上 mainline，向 PM 提案 Linear issue

### 嚴禁事項

- **Don't** 把 Linear / Notion 當有否決權；它們鏡像，git 決策
- **Don't** 自動同步 TODO.md → Linear；策展鏡像 only
- **Don't** 在任何外部工具發布 secrets / API keys / authorization tokens
- **Don't** 啟用 Coupler.io dataflow（已 declined；本機 DuckDB / psql 替代）
- **Don't** authenticate Slack（已 declined to live -2w）
- **Don't** 未經 operator 授權發布 runtime engine state（PID / snapshot freshness / fill rates）到任何外部工具

### 與 §六.六 SSH bridge 工作流關係

Mac CC = SSOT，可寫 Linear / git；Linux runtime 透過 `ssh trade-core` 觸發；Linear 寫入從 Mac 主會話發起。**Multi-session race 守則**（`feedback_git_commit_only_for_metadoc.md`）對 CLAUDE.md / TODO.md / memory 仍適用：用 `git commit --only <file>`。

### 重新評估觸發點

只有以下情況才考慮重啟已 declined 的工具，不要主動評估：
- **Coupler.io**：本機 DuckDB / psql 真的不可行
- **Slack**：approaching live trading（~2026-05-15）需 mobile alert channel
- **MotherDuck**：見 `memory/reference_external_tools.md` §Declined
- **Notion**：operator 主動要求重新融入（單方面解凍）
