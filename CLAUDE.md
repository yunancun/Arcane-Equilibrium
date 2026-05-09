# 玄衡 · Arcane Equilibrium
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）

---

## 一、項目定位

長期進化型 Agentic Trading Governance System。正式項目名為 **玄衡 · Arcane Equilibrium**；OpenClaw 保留為控制平面 / Gateway / Console / 通信服務族名稱；**Bybit 為唯一交易所**（專攻）。

**詞彙權威 → `srv/CONTEXT.md`** （domain glossary，所有新文檔/ADR/refactor/review 必對齊；2026-05-06 引入）。
**架構決策記錄 → `srv/docs/adr/0001..0014-*.md`** （14 條 ADR，硬要可逆 / surprising / real-trade-off 三條件；2026-05-06 引入）。

> Agent 自主完成交易決策與執行，對成本與收益有清晰感知，能感知自身狀態，能持續學習，在嚴格風控框架下逐步贏得更高自主權。

人類 Operator 角色：不定時檢查、審閱、矯正、批准關鍵步驟、推動策略演進。

**2026-05-06 軟更名與 OpenClaw 定位修正**：
- 正式項目名改為 **玄衡 · Arcane Equilibrium**；新文檔避免再用「OpenClaw Bybit」作總項目名。
- 短期不改 `openclaw_engine`、`OPENCLAW_*`、`/tmp/openclaw`、GitHub repo、Linux runtime path、Bybit connector path；這些屬 runtime / compatibility namespace。
- 唯一 canonical GUI 是現有 FastAPI console：`http://trade-core:8000/console`，後續命名為 **OpenClaw Control Console**。
- 外部 OpenClaw Gateway 僅作 Telegram/WebChat/mobile/operator 通信、上級匯總、cloud escalation、proposal/approval relay；不是第二套交易 GUI。
- 本地 5-Agent runtime 不遷入外部 OpenClaw Gateway；Scout / Strategist / Guardian / Analyst / Executor 繼續在 TradeBot FastAPI + Postgres + Rust engine 栈內運行。
- OpenClaw 不持 Bybit key、不直接下單、不直接改 live TOML；交易影響動作仍走 GovernanceHub + Decision Lease + Rust execution authority。
- 權威設計：`docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md`；落地方案：`docs/execution_plan/2026-05-06--openclaw_gateway_development_plan.md` + `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md`。

**交易所決策（2026-04-03）：** 早期規劃含 Binance 雙平台，現已明確專攻 Bybit。Binance 僅作為超長期可能方向保留。

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
12. **持續進化** — 系統必須從交易行為中自動學習（當前 demo 階段：Paper 驗證→參數進化，live 自動部署待 Phase 6 放權框架）
13. **AI 資源成本感知** — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉
14. **零外部成本可運行** — 基礎運營僅需 L0+L1（Ollama + 免費搜索）
15. **多 Agent 協作** — 5 Agent（Scout/Strategist/Guardian/Analyst/Executor），由 Conductor 編排（**Conductor 不是第六 Agent**），正式對象通信；外部 OpenClaw Gateway 只作通信/上級匯總/審批入口，不是交易 Agent
16. **組合級風險意識** — 監控關聯曝險、策略重疊持倉、資金分配合理性

**優先級序：** 帳戶生存 > 風控治理 > 系統健康 > 審計可追溯 > 人類終審 > 真實 Net PnL > 自主能力進化

**實施準則**：認知調製 ≠ 能力限制 — Agent 壓力下更審慎的方式是提高決策門檻，不是關閉能力。虛擬稀缺性（能量/積分/內部貨幣）被明確否決。

---

## 三、真實狀態全景（2026-05-09 W-AUDIT-1 sync）

本節只保留當前活躍狀態。歷史長敘述移到 `docs/CLAUDE_CHANGELOG.md`、
`docs/archive/`、`docs/CCAgentWorkSpace/*/workspace/reports/` 和 `TODO.md`。
帶 runtime 數值的行必附採集時間或 healthcheck id；滿 7 日未重驗即更新或移出。

### Runtime / Source

| 項 | 目前事實 |
|---|---|
| W-AUDIT-1 evidence source | `b91487f2`（`healthcheck: make scanner would-block evidence advisory`）；後續 docs/governance commit 只改文檔索引，當前 repo head 以 `git log -1` 為準。 |
| Runtime host | Linux `trade-core`；watchdog 2026-05-09 09:34 UTC：`engine_alive=true`，paper/demo/live snapshots fresh。 |
| Runtime env | `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`，`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`，`OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv`。 |
| Scanner config | `settings/risk_control_rules/scanner_config.toml` 無 `[authority]`；scanner 永遠作為 market context / evidence infrastructure 啟動，不再有 hard authority mode。 |
| Live boundary | 2026-05-09 09:12 UTC operator route `/api/v1/live/auth/renew` restored signed LiveDemo authorization (`tier=T0_ENTRY`, `approved_system_mode=live_reserved`, `valid_for_engine=true`, expires_at_ms=1778405563954). 2026-05-09 09:33 UTC rebuild/restart `--keep-auth` deployed `862e79b7`; watchdog shows live pipeline fresh. Mainnet 真 live 流量仍為 0 by design；未提供真 mainnet API。 |

### W-C / MAG-082

| Gate | 最新實測 | 結論 |
|---|---|---|
| `[55] agent_decision_spine_lineage` | 2026-05-08 22:09 UTC direct check PASS：`objects=505/505`、`edges=404/404`、`idempotency=101/101`、`chains=101`、`chains_with_lease=76`、`chains_with_report=101`、`bad_report_quality=0`。 | Shadow lineage and lease-bypass evidence are flowing. |
| MAG-082 readiness | `[55]` still reports `LINEAGE_READY_NOT_WINDOW_PASS window=1440m`。 | Stage 2 still needs the 24h window PASS before MAG-083 / MAG-084。 |
| Passive healthcheck | 2026-05-08 22:08 UTC：`SUMMARY: WARN`，無 hard FAIL。 | 可繼續觀察；WARN cluster 見下表。 |

### Strategy / Edge

- 2026-05-08 12-agent audit PA PG 直查：5 策略 7d demo gross 約 `-26.44 USDT`，live_demo gross 約 `+0.43 USDT`；舊 §三 的 `-6.98 USDT` 已過期。
- 2026-05-09 3C 7d audit：Overall `WARN`；`[40]` avg_net 比 baseline 下滑 `-1.12bps`（within tolerance），grid p50 lifetime shortened `47.6%`，demo gross PnL delta improved `+20.87 USD` vs baseline。
- `funding_arb` 新開倉仍按現有 risk configs 禁用 / 收斂；AMD-2026-05-09-02 / ADR-0018 已決定從 active strategy set 退休，W-AUDIT-6 做 RiskConfig 清理；2026-05-16 14d audit 保留作驗證/歷史工件。

### Current Observation Gates

| Gate | 2026-05-08/09 latest | 結論 |
|---|---|---|
| `[33]` maker fill rate | 7d demo/live_demo entry_fills=298，maker_like=89.6%，fee_drop=59.5%（target >=60%）。 | WARN：接近 fee-drop target，但未過。 |
| `[38]` grid lifecycle drift | passive 24h live_demo re_entry_rate=0.52；3C 7d audit post window p50 3.79min vs baseline 7.23min（-47.6%）。 | WARN：grid lifecycle 需 review，但不阻 passive observation。 |
| `[40]` realized edge | passive 24h MLDE rows=42，avg_net=-6.02bps；3C 7d audit demo current avg_net=-17.82bps vs baseline -16.70bps。 | WARN：edge 未轉正；P0-EDGE-1 仍 active。 |
| `[41]` scanner would-block evidence | `b91487f2` 後 WARN-only：legacy scanner would-block evidence later non-negative，scanner remains evidence-only。 | 源碼已修正：scanner contradiction 不再 hard FAIL。 |
| `[42b]/[42c]` attribution drift | settled eligible strategies ratio=1.000；低樣本策略標 `LOW_SAMPLE(n, need)`。 | WARN sample-maturity watch，不是 attribution drift。 |
| `[45]` pricing binding | demo/live_demo source=`bybit_v5`，age >1h but <24h。 | WARN：仍需 P0-LG-2 provider pricing binding foundation。 |
| `[51]` scanner opportunity shadow | routes/intents 100%；24h labels=39，positive_lcb_n=16，avg_net=-4.29bps，`opportunity_positive_n=0 LOW_SAMPLE`。 | WARN：shadow-only，calibrated positive sample 未成熟。 |
| `[56]` live pipeline active | 2026-05-09 09:34 UTC direct check PASS：`live pipeline active endpoint=live_demo auth=present snapshot_age=21.4s threshold=180s`。 | LiveDemo pipeline restored through signed route; check remains read-only and does not write auth. |

### Active Blockers

| Blocker | 狀態 |
|---|---|
| W-C / MAG-082 | Active evidence window；未達 24h PASS。 |
| MAG-083 / MAG-084 | Blocked until MAG-082 PASS。 |
| P0-EDGE-1 | Active；realized edge 未轉正。 |
| P0-LG-1 / P0-LG-2 / P0-LG-3 | H0 production caller、provider pricing binding、supervised-live state machine 仍需 IMPL。 |
| P0-OPS-1..4 | HTTPS/secure cookie、credential rotation、legal/ToS/geography、first-day live runbook 仍需收口。 |
| P0-DECISION-AUDIT-2/4/5 | 已由 AMD-2026-05-09-02 收口：SM-05 Option A、W-AUDIT-6 strategy verdict、openclaw_core sunset candidates、Layer2 manual supervisor-only。剩餘是 F-01/W-AUDIT-6/W-AUDIT-5/W-AUDIT-7 implementation，非 operator decision blocker。 |
| W-AUDIT-1..7 | W-AUDIT-1/W-AUDIT-2 已 source-closed；下一個可做項是 W-AUDIT-3。 |

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
decision_lease_emitted  = "shadow_bypass_lineage_only"  # 2026-05-08 operator-authorized W-C evidence mode:
                                                        # Linux `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`
                                                        # writes lease/bypass lineage into Agent Spine shadow
                                                        # ExecutionPlan rows. This is not true-live auth,
                                                        # not Executor order authority, and not MAG-083/084.
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
[I Decision Lease]       (*) GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 209 /api/v1 + non-api GUI 路由 + `/api/v1/openclaw/*` planned aggregation
[GUI + Learning]         OpenClaw Control Console（唯一 GUI；13 tabs）+ Learning Cockpit + Paper Trading Dashboard
[OpenClaw Gateway]       外圍通信 / mobile / supervisor / proposal relay；非交易 hot path，非第二 GUI
[Rust openclaw_engine]   paper / demo / live 三模式唯一引擎（1C-3-F 後）
                         tick pipeline + IntentProcessor + paper_state + governance + stop_manager
[Compute tiers]          L0 確定性 → L1 Ollama → L1.5 (Haiku/Perplexity) → L2 Claude manual/supervisor escalation only
[風控框架]               P0/P1/P2 三層 + 對抗性止損 + AI 注意力稅
[策略工具包]             KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator
[管線橋接]               PipelineBridge: Tick Fan-Out + Intent→Order + 治理 gate
[止損管理器]             StopManager: Hard/Trailing/Time Stop + ATR 動態倉位
```

**OpenClaw Control Console 13-tab dictionary（2026-05-06 current）**：
`system`, `replay`, `paper`, `demo`, `live`, `strategy`, `risk`,
`governance`, `ai`, `learning`, `agents`, `monitoring`, `settings`。GUI spec
must reference the current 13-tab console dictionary.

**(*) Decision Lease 路徑 A + W-C evidence mode（2026-05-09 current）**：
Sprint 3 Track H IMPL `dbcf845b` + Track I deploy `0ad79f67` 已落地；
W-C 於 2026-05-08 經 operator 授權在 Linux 啟用
`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`，並在
`OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow` 下把 lease/bypass lineage 寫入
Agent Spine shadow ExecutionPlan rows。這是 MAG-082 Stage 2 evidence
collection，不是 true-live 授權、不是 Executor order authority、不是
MAG-083/MAG-084 sign-off。§5.4 原定 2026-05-15 後翻 flag 的排程由
AMD §5.4.1 補件修訂；詳
`docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` 和
`docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`。

**EarnedTrust T0/T1/T2/T3 vs Decision Lease 兩者互補**：
- T0-T3：session 級 authorization TTL（24h-360h），管「整個 live session 多久重 auth」
- Decision Lease：per-intent 執行授權（0.1-300s），管「這一筆 intent 在 30 秒內可下單」
- 共同支撐 LG-5（Constrained Autonomous Live）

---

## 六、路徑與啟動

```
GitHub repo:    yunancun/BybitOpenClaw
本地主工作樹:   由 $OPENCLAW_BASE_DIR 決定（repo 任意絕對路徑皆可）
                Linux 預設: $HOME/BybitOpenClaw/srv（/home/ncyu/srv ← symlink, legacy）
                Mac   範例: /Users/ncyu/Projects/TradeBot/srv（或 $HOME/BybitOpenClaw/srv）
本地-only：     settings/（secrets）  trading_services/（runtime）
```

### 跨平台 Runtime 路徑（Mac/Linux 共用）

**Mac dev 必設**（Linux 上可選，默認 `/tmp/openclaw` + `$HOME/BybitOpenClaw/`）：
```bash
export OPENCLAW_BASE_DIR="/Users/ncyu/Projects/TradeBot/srv"   # repo 根
export OPENCLAW_DATA_DIR="$HOME/.openclaw_runtime"             # runtime / socket / log
export OPENCLAW_SECRETS_ROOT="$HOME/.openclaw_secrets"         # secrets 根（含 env_files + secret_files）
export OPENCLAW_SECRETS_DIR="$HOME/.openclaw_secrets/secret_files/bybit"  # Bybit slot base
export OPENCLAW_ARCHIVE_DIR="$HOME/.openclaw_archive"          # clean_restart / fresh_start dump

mkdir -p "$OPENCLAW_DATA_DIR" "$OPENCLAW_SECRETS_ROOT/environment_files" \
         "$OPENCLAW_SECRETS_ROOT/secret_files/bybit" "$OPENCLAW_ARCHIVE_DIR"
```

原因：Mac `/tmp` 是 `/private/tmp` symlink 且 LaunchAgents 看到不同路徑；Mac 上跑 pytest、`restart_all.sh`、IPC socket 都必須走 `$OPENCLAW_DATA_DIR`。Linux 上不設時 fallback 到 `/tmp/openclaw` + `$HOME/BybitOpenClaw/{secrets,archive}`，行為不變。

| env var | 指向 | 誰在讀 |
|---|---|---|
| `OPENCLAW_BASE_DIR` | repo 根（srv） | Rust `startup.rs` / `strategies` · Python 多處 · `start_paper_trading.sh` |
| `OPENCLAW_DATA_DIR` | runtime（sockets / logs / flags / snapshot） | Rust engine · API · scripts |
| `OPENCLAW_SECRETS_ROOT` | secrets/ 根（含 env_files + secret_files） | shell scripts（restart/clean/fresh） |
| `OPENCLAW_SECRETS_DIR` | secrets/secret_files/bybit（slot base） | Rust `bybit_rest_client` · Python `bybit_rest_client.py` · live_auth |
| `OPENCLAW_ARCHIVE_DIR` | archive（damaged_/fresh_start_ dumps） | clean_restart / fresh_start |
| `OPENCLAW_SRV_ROOT` | ⚠️ legacy alias，同 `OPENCLAW_BASE_DIR` | `bybit_path_policy.py` + 115 歷史 maintenance scripts — **新代碼用 `OPENCLAW_BASE_DIR`**，兩者互不 fallback，Mac 部署時建議 `export` 同值 |

**Mac 差異注意**：`$HOME/.openclaw_runtime` **不會**在開機時被清（Linux `/tmp` 每次重啟清空）：
- `engine_maintenance.flag` 若上次異常留下會阻塞 watchdog → 開工前先 `rm -f "$OPENCLAW_DATA_DIR/engine_maintenance.flag"`
- 舊 socket 檔殘留會讓新 process 拒綁 → 啟動前清或讓腳本 unlink
- 建議 `.zshrc` 加 `alias oc-clean-runtime='rm -f "$OPENCLAW_DATA_DIR"/{*.sock,engine_maintenance.flag}'`

### 啟動檢查（每次 session 起點）

**Mac 端（SSH bridge workflow）**：
```bash
git status && git log --oneline -5                                    # Mac 本地 repo 狀態
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -5"       # Linux repo 狀態（可能領先）
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status"  # engine 真實狀態
```

Mac 本地跑 watchdog 永遠回 `engine_alive: false`（engine 只跑 Linux）；必須透過 ssh 查。Mac 接手三連 = git status + ssh Linux git log + ssh Linux watchdog。

### TODO.md 強制規則（每次接手必須遵守）

**接手時：** 必須讀 `TODO.md` 確認當前工作狀態，找第一個 P0 未完成項作為起點。用戶有明確指令時以用戶為準。

**發現新問題時：** 立即追加到 TODO.md 對應 P0/P1/P2 層，不等會話結束。

**修復完成後：** 標 ✅ DONE，追加完成 commit 號，更新測試基準線。

---

## 七、代碼與文檔規範

### ★★ 跨平台兼容性（強制，所有開發必須遵守）

**大前提：項目必須隨時可以部署在 macOS 上運行。**

1. **路徑不硬編碼** — 所有路徑使用環境變量或 config，禁止 user-home 絕對路徑字面值（`/home/ncyu/`、`/Users/ncyu/`、`/Users/<name>/…/TradeBot` 等）。
   用 `os.environ.get("OPENCLAW_BASE_DIR", ...)`、docker-compose 相對路徑、或 `Path(__file__).parent`。
   E2 必查：`grep -E '(/home/ncyu|/Users/[^/]+)' <diff>` 命中 → 打回（歷史 worklog / dated snapshot / 政策反例引用不在此限）。

2. **LocalLLMClient 抽象乾淨** — 不洩漏 Ollama-specific 細節。所有 LLM 調用通過 `LocalLLMClient` ABC 接口，禁止業務邏輯直接調用 Ollama HTTP endpoint。

3. **服務部署可遷移** — systemd → launchd 遷移路徑清晰。服務配置邏輯寫成文檔或腳本（`helper_scripts/deploy/`）。

4. **依賴管理乾淨** — `requirements.txt` 保持更新，禁止隱式依賴。新增 `import` 同步更新 requirements。E2 必查。避免 Linux-only 依賴（如 `psutil` 的 Linux 特定 API），需要時加平台守衛。

### 注釋規範（2026-05-05 governance change：默認中文）

**新規（2026-05-05 operator 決定）**：
- **新建/修改的注釋默認只寫中文**（不再強制中英對照）
- **原有中英對照注釋不主動清理**（保持現狀）
- **修改既有中英對照塊時移除英文只保留中文**（當下動到的 block 端用此規則）

範圍：MODULE_NOTE / docstring / inline / fail-closed 路徑 / 安全代碼。

舊規（2026-05-05 之前）：每個新建/修改的注釋必須中英對照 — **2026-05-05 起作廢**。動機：bilingual mandate 使 runner.rs 等高內聚模組 41% 行是注釋，token + LOC 成本顯著（V055 5-round + R6 W1+W2 共增 ~4000 LOC 注釋），中文足以承載必要語義。

E2 review：新代碼 grep 發現注釋僅中文 → PASS（不再要求英文版）；發現注釋僅英文 → 仍 push back（中文是必要層）。

### SQL migration 規範

**Guard A/B/C 強制**（2026-04-24 V023 silent-noop postmortem 衍生 + 2026-05-02 V028-V034 retrofit 補完）：任何 `CREATE TABLE IF NOT EXISTS` 前必加 Guard A 驗欄位俱在；任何型別敏感的 `ADD COLUMN` 必加 Guard B 驗 `data_type`；hot-path 索引選用 Guard C 比對 `pg_get_indexdef()`。模板：`sql/migrations/templates/schema_guard_template.sql`。Idempotency 強制：每個 migration 本地跑兩次 `psql -f V<NNN>__<desc>.sql`，第二次必須不 RAISE。Range：V001-V027 多數 pre-postmortem 期未加 Guard（歷史視 idempotency 風險可接受）；V023+V028~V034 已 retrofit。詳述 → `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md`。

**Engine 自動遷移（opt-in）**：`OPENCLAW_AUTO_MIGRATE=1` env var 啟用；engine 啟動在 DbPool 連線後、writer 啟動前呼叫 `MigrationRunner::run_if_enabled()`。預設關，operator 逐步驗證。Rollback：`unset OPENCLAW_AUTO_MIGRATE` + `bash helper_scripts/linux_bootstrap_db.sh --apply` + 重啟。詳述 → `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md`。**2026-05-02 P0 sqlx hash drift incident**（commit `3681f83`）：`bin/repair_migration_checksum` binary 處理 V028-V034 file edit 後 DB checksum 沒同步問題。詳 `memory/project_2026_05_02_p0_sqlx_hash_drift.md`。

**Linux PG dry-run mandatory (2026-05-05 V055 5-round loop 衍生)**：任何 V### migration 涉及 PG reflection 函數（`pg_get_function_*` / `pg_proc` / `information_schema`）/ transaction control（SAVEPOINT / COMMIT / ROLLBACK）/ schema 假設（column existence / type / default）必先 PM 端做 Linux PG empirical query 驗證真實 schema/runtime semantic，再 dispatch E1 IMPL 設計。Mac mock pytest + static-parse review **絕對不夠**（V055 chain 5 round 都因 Mac 層 false-pass 而 Linux 撞 bug）。E2 review 必含 Linux PG dry-run gate，不只 Mac mock。詳 `memory/feedback_v_migration_pg_dry_run.md`。

### 被動等待 TODO 必附 healthcheck（強制）

任何「被動等待 Nd / Nw」TODO 必須同步附一條可執行 healthcheck（`helper_scripts/db/passive_wait_healthcheck.py` 加 `check_*()` function），由 cron 或 operator 手動間隔跑。check 回 `"PASS" / "WARN" / "FAIL"`，**Exit 1 = silent-dead 自動偵測**。違反 = E2 審查打回。當前 51 個 check（含 [42]/[42b] LG-5 reviewer + Sprint D 新增 [45] LG-3 pricing_binding + [46]-[50] REF-20 sentinel + [51] scanner opportunity shadow acceptance）。詳述觸發情境例 → `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md`。

### Sign-off 必檢 git status clean（強制，2026-05-02 LG-5 incident 衍生 P0-GOV-3）

任何 sign-off report 寫入後 commit 前，必檢 `git status --porcelain` 對應檔案 clean（不能有 staged/untracked 對應的代碼/測試檔）。違反 = PM 拒絕 sign-off。背景：LG5-W3-FUP-1 E1 sign-off report 自承「Branch: main (uncommitted; awaiting E2 review)」仍進入下一節流，導致 reviewer scheduler 從未進 git → 27 candidates 累積無人 review。

### 強制同步規則
- **Sprint/Wave 完成**：更新 §三 + §十 + `docs/CLAUDE_CHANGELOG.md` + README，與生產代碼同 commit
- **§三 衛生規則**：§三 只記載「現況/活躍狀態」+「過去 ≤2 天的完成里程碑」。任何完成里程碑當天 +2 日（以 `currentDate` 為準）必須在 commit 同次操作中歸檔到 `docs/archive/YYYY-MM-DD--claude_md_section3_*.md` 並從 §三 刪除。違反 = §三 膨脹回 ~10K tokens。
- **§三 數據 vs runtime drift 防線**：§三 任何「runtime 數值 + 狀態」必註明採集時間 + 對應 healthcheck id；滿 7 日未經自動化重驗即必須更新或從 §三 刪除；CC 收到 §三 數字當決策輸入時必先實測 source-of-truth 才採納，發現 drift 同 commit 修。E2 必查。
- **Commit 時**：摘要追加到 `docs/CLAUDE_CHANGELOG.md` 頂部
- **Context ≥90%**：立即寫 `docs/worklogs/YYYY-MM-DD--session_progress_N.md`
- **每日整合**：當天 worklog 碎片合併為 `YYYY-MM-DD--daily_summary.md`，刪碎片
- **新腳本**：MODULE_NOTE 雙語 + latest+dated 輸出 + contract check + 更新 SCRIPT_INDEX.md
- **docs/**：分類目錄 + `YYYY-MM-DD--描述.md` + 更新 `docs/README.md` 索引

### 本地 LLM 審核協作（Mac 環境，強制）

Operator 在 Mac 並行跑 Qwen3.6-35B（LM Studio）做代碼審核。CC 每完成一個任務，必寫結構化報告至：

    .claude_reports/YYYYMMDD_HHMMSS_<短描述>.md

（`.claude_reports/` 在 `.gitignore`，僅本機留存；6 節必備：任務摘要 / 修改清單 / 關鍵 diff / 治理對照 / 不確定之處 / Operator 下一步）

### Git 自動化（強制：所有 commit 必 push）

- CC 每完成一個合理可交付單位 → 自動 `git add` + `git commit` + `git push origin main`（三者同 Bash 鏈內完成）
- **無例外**：Mac CC / Linux CC 都遵守「commit 即 push」
- **Session 接手三連 sync**：`git fetch --prune origin` + 若 local 落後 `git pull --ff-only` + 若 local 超前 `git push origin main`
- **Mac CC 觸發 Linux 驗證前**：push 完接 `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"` 同步 Linux 工作樹
- **CC 絕不執行**：`pull` / `merge` / `checkout` / `reset` / `rebase`（狀態變更操作留給 operator）
- **Multi-session race 守則**（`feedback_git_commit_only_for_metadoc.md`）：CLAUDE.md / TODO.md / docs / memory 等 meta-doc 必用 `git commit --only <file>`，避免吸收隔壁 session 的 WIP

### Mac dev-only 模式

詳 README § Mac dev-only 模式。核心：3 個 secret slot rename 為 `*.dev_disabled_*` 避免與 Linux trade-core 撞單；Mac engine 即使被誤啟也無 credentials 可連 Bybit → 0 訂單衝突。

---

## 八、工作流編排、18 Agent 角色與自我改進循環

### ★ 工作流編排 6 條 + 3 底線

1. **規劃優先 Plan-First**：非平凡任務（≥3 步 / 涉架構決策）先進規劃模式再動手；前期寫詳細 spec 減歧義；過程遇阻即停重規劃，**禁強推**。
2. **Sub-agent 卸載**：研究/探索/並行分析一律派 sub-agent 保主上下文整潔；一 agent 一任務精準執行。
3. **自我改進循環**：operator 任何糾正 → 抽模式寫 `docs/lessons.md`；會話起手掃近期相關條目。
4. **完成前驗證 Verify-Before-Done**：永不先標 done；跑測試 / 查 log / 對比 main 分支行為差 / 自問「senior engineer + FA 會 approve 嗎？」
5. **追求優雅（平衡）**：非平凡修改前停問「有更優雅方式嗎？」；簡單/明顯修復跳過。
6. **自主 bug 修復**：收到 bug 直接修；指 log/錯誤/失敗測試再解。

**3 條核心底線**：**簡單優先**（只動必要代碼） · **不偷懶**（找 root cause，禁臨時 patch） · **最小影響**（變更只觸必要部分）。

### 18 Agent 角色體系與強制工作鏈

**真實接線**：18 個 subagent definition 在 `.claude/agents/<NAME>.md`（git tracked，雙端 git 同步）。每個 agent 含 Anthropic 官方 frontmatter（`tools` / `disallowedTools` / `skills` 預載 / `color` / `model: inherit`）+ 啟動序列（讀 `docs/CCAgentWorkSpace/<NAME>/{profile,memory}.md`）+ 完成序列（追加 memory + 存 `workspace/reports/`）。

**主會話 = PM + Conductor**（合一，**非** subagent）。Anthropic 限制：subagent 不能 spawn 另一 subagent。

| Tier | Agents |
|---|---|
| 管理層 | `@PM` `@FA` `@PA` |
| 質量保證層 | `@CC` `@E2` `@E3` `@E4` `@E5` |
| 執行層 | `@E1` `@E1a` |
| 專項審查層 | `@A3` `@R4` `@TW` |
| 分析顧問層 | `@AI-E` `@QA` `@QC` `@BB` `@MIT` |

**Invocation 三種 pattern**：
1. **Natural language 自動 delegate**：「讓 QC 看一下這個策略」→ Claude 主動 delegate
2. **`@-mention` 強制**：`@QC` → 100% trigger
3. **Session-wide**：`claude --agent QC`

**強制工作鏈**：`PM` + `@FA` 規格 → `@PA` 派發 → `@E1` / `@E1a` 並行 → **`@E2` 代碼審查 → `@E4` 測試回歸**（兩者絕不可跳）→ `@E5` 優化（每 Phase / Wave / ≥3 E1 任務強制）→ `@QA` → PM 確認。`@E3` / `@CC` / `@A3` / `@R4` / `@TW` / `@BB` 按需插入。`@AI-E` 季度跑。`@QC` 新策略提案 / 數學審計必活。`@MIT` ML pipeline / DB schema 審計必活。

**P0 快速通道**：`@PA` → `@E1`（≤5 並行）→ `@E2` → `@E4` → PM。可省 FA / E5 / E3 / CC，但 E2 + E4 永不跳。

**動態 isolation 派工準則**：單實例 sub-agent 操作單檔 → NOT isolation；並行 ≥2 sub-agent 操作不重疊檔 → NOT isolation；並行 ≥2 操作可能重疊檔 → 對重疊組加 `isolation: worktree`；destructive 動作（git reset / 大量 rm / 跨檔重構）→ 加 isolation；純審查類 → **永不需要** isolation。

**Skill 預載**：OpenClaw 24 個 custom skill 在 `.claude/skills/<name>/SKILL.md`（git tracked）— agent frontmatter `skills:` 預載相關子集。K-Dense-AI 134 個 scientific skill 在 `~/.claude/skills/k-dense-ai/scientific-skills/`（user-level）— agent body 寫路徑供按需 Read。

**雙端部署**：Master `srv/.claude/{skills,agents}/` git tracked；Mac CC 用 symlink；Linux CC 直讀。同步：Mac edit → `cd srv && git add + commit + push` → Linux `git pull --ff-only`。

**Bybit API 強制**：所有 Bybit 相關開發（REST/WS/IPC）先查字典手冊 `docs/references/2026-04-04--bybit_api_reference.md`，新增端點同步更新手冊，`@E2` 必查；`@BB` 從 Bybit 立場 push back 違規設計。

---

## 九、代碼結構約定

### 文件大小限制

- **800 行** ⚠️ 警告線（E2 必須標記）
- **2000 行** 🛑 硬上限（不允許 merge）

**2026-05-05 governance change**：硬上限從 1500→2000（operator 決定，REF-20 Sprint C 拍板）。理由：Sprint C 預估 `runner.rs` 1466 + R6-T1+T2 ~180 LOC = 1646 會破舊 1500 cap，需先 R0-T0 拆檔；operator 評估「文件內聚性 > 機械式 LOC 限制」，提升至 2000 給 high-cohesion 模組（router.rs / runner.rs / experiment_registry.py 等）合理 headroom。**警告線維持 800**。

**2026-05-02 governance change**（歷史）：硬上限從 1200→1500。`commands.rs` 1343 / `scanner/scorer.rs` 1437 等檔超舊 1200 限但單一檔內聚性高。

**Pre-existing baseline exception clause**：當檔案在某個 wave 開工前的 baseline 已超過 2000 行（pre-existing violation 來自更早歷史），允許下列例外：(1) 接受 wave 後 LOC ≤ pre-existing baseline + 5 LOC；(2) 同時開新 P2 ticket 處理 pre-existing violation；(3) PM Sign-off 必明文記錄 governance exception accept 理由。**僅適用 pre-existing 2000+ violation**，不適用「新 wave 把 ≤2000 推到 >2000」的場景。

### 模塊依賴方向（禁止循環 import）

```
state_models ← state_compiler ← state_store ← main_legacy ← main.py
其他 route 文件 ← main_legacy（通過 from . import main_legacy as base）
```

### Singleton 管理

| Singleton | 創建位置 | 用途 |
|-----------|---------|------|
| `settings` / `STORE` / `app` / `limiter` | main_legacy.py | 全局 base |
| `_pool` / `DEFAULT_LEASE_TTL_CONFIG` | db_pool.py / lease_ttl_config.py | DB 連線 + lease TTL config |
| `_backtest_engine` / `_scheduler` / `_evolution_engine` / `_ledger` | 內部懶加載 | 各路由模組 |
| `LeaseTTLConfigManager._instance` | lease_ttl_config.py | TTL config |
| `_BYBIT_CLIENT` | strategy_ai_routes.py | PYO3-ELIMINATE-1 後 = `app.bybit_rest_client.BybitClient` 純 httpx |
| `KLINE_MANAGER` / `INDICATOR_ENGINE` / `SIGNAL_ENGINE` / `ORCHESTRATOR` 等 12+ | strategy_wiring.py | 模組級全局 |
| `SCOUT_AGENT` | strategy_wiring.py:143 | 由 `set_scout_agent()` 寫入；class 在 `scout_agent.py` |
| `_SHARED_IPC_SLOTS` / `_SHARED_SLOT_LOCK` | ipc_dispatch.py | E5-P1-5 共享 IPC client |
| `_<AGENT>_AUDIT_CB` / `_GOV_HUB_FOR_<AGENT>` × 5 | strategy_wiring.py | 由 `agent_audit_bridge.make_agent_audit_callback(...)` 構造 |
| `_scheduler` / `_LEADER_LOCK_FD` | edge_estimator_scheduler.py | P1-7 B JS estimator 每小時 cycle + uvicorn workers leader election |
| `_CACHE_INSTANCE` / `_CACHE_LOCK` | executor_config_cache.py | G3-03 Phase B；shadow_mode_provider lambda 注入 ExecutorAgent ctor（注：`lambda: True` fail-close default 是 P1-FAKE-1 待修） |
| `_H_STATE_INVALIDATOR` | h_state_invalidator.py | G3-08 Phase 1C；env-gated `OPENCLAW_H_STATE_GATEWAY=1` 才 spawn（P1-FAKE-3 env 未設） |
| `MARKET_SCANNER` / `AUTO_DEPLOYER` / `_SCOUT_WORKER` | strategy_wiring_scanner.py | STRATEGY-WIRING-SPLIT P2 抽出 |
| `HStateCacheSlot` | rust/openclaw_engine/src/ipc_server/slots.rs | Rust 端 late-injected slot；env-gated（P1-FAKE-3） |
| `CostEdgeAdvisorDbSlot` | rust/openclaw_engine/src/cost_edge_advisor_boot.rs | Rust 端 late-injected slot；G3-09 Phase B；env-gated（P1-FAKE-3） |
| `Lg5ReviewConsumer` | program_code/exchange_connectors/bybit_connector/control_api_v1/app/lg5_review_consumer_scheduler.py | LG-5 W3 FUP-1 sibling CC commit `463890d`；待 deploy 後 spawn `/tmp/openclaw/lg5_review_consumer.leader.lock` |
| `_REGISTER_IDEM_CACHE` / `_REGISTER_IDEM_CACHE_THREAD_LOCK` | replay/experiment_registry.py | REF-20 Sprint A R2 round 2 fix H-1：register endpoint 的 in-memory idempotency cache（取代 manifest_jsonb `_idempotency_key` 注入，避免破 sha256(manifest_jsonb)==manifest_hash 不變式）。重啟丟 cache 是 accepted trade-off（V3 §5 30d TTL 跨重啟丟保證）；race-safe via threading.Lock + PG advisory xact lock 多層（caller 在 `asyncio.to_thread` 內，thread-level Lock 是正確原語；round 3 M-DEAD-LOCK 刪了 0 callsite 的 asyncio Lock）|

新增 singleton 必須在此表登記。禁止子模塊創建未登記的全局可變狀態。詳述 5 條 long-form 注釋 → `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md`。

### 其他

- Route Handler 只做 parse → call → format，不含業務邏輯
- 新 Pydantic model 放 `*_models.py` 或所屬模塊，不加入 main_legacy.py
- **Non-training surfaces**：`replay.simulated_fills` (V050) 是 replay 衍生數據，`evidence_source_tier` ∈ ('synthetic_replay', 'calibrated_replay', 'counterfactual_replay')。'synthetic_replay' 是 Sprint A R3 smoke run 寫入的 tier，**不可作 ML training data**。下游 SELECT replay.simulated_fills 必含 `WHERE evidence_source_tier IN ('calibrated_replay', 'counterfactual_replay')` 才能餵 MLDE / Dream / attribution writer。E3 安全審計 grep rule 加此檢查。

---

## 十、下一步工作指針

**當前焦點**：活躍任務以 `TODO.md` v14 為準。2026-05-08 已把 12-agent full audit PA fix plan 掛入 W-AUDIT-1..7。當前順序是：保持 `W-C` MAG-082 Stage 2 evidence window 觀察；`W-AUDIT-1` docs sync/governance compliance 與 `W-AUDIT-2` security IMPL 已 source-closed；下一步接 W-AUDIT-3 runtime/fake-live alignment，再接 W-AUDIT-4..7。仍不是 Telegram/WebChat、第二 GUI、Stage 3/4，或 true-live autonomy。

**關鍵路徑**：`W-C 24h PASS → MAG-083 QA audit → MAG-084 operator sign-off → W-AUDIT-1 docs/governance DONE → W-AUDIT-2 security IMPL DONE → W-AUDIT-3 runtime/fake-live alignment → W-AUDIT-4..7 + edge/data + LG-2/3/4 + ops gates → proposal/mobile relay only after explicit approval → true live`

**REF-20 / REF-21 狀態**：REF-20 Sprint A-D 與 REF-21 replay usability foundation 已收口；剩餘 replay 工作是 empirical calibration maturity、recorder history、baseline library，不替代 runtime lineage 或 live promotion。

**最早 Live 日期**（事件驅動，非 hard date）：以 2026-06-15 悲觀規劃帶為主。PA full audit 偏悲觀：edge 未轉正、LG-2/3/4 尚未 IMPL、W-AUDIT-1..7 未完、MAG-082 未 PASS、MAG-083/084 blocked。

**路線圖**：Phase 0-3 + Live GUI + 5-Agent 基礎接線 + Executor fake-live smoke + runtime Agent Spine shadow lineage + Decision Lease bypass lineage + REF-20/REF-21 replay foundation 均已落地。仍未完成的是 MAG-082 24h PASS、MAG-083/MAG-084、W-AUDIT-3..7、edge / execution-quality 驗收、Live Gate LG-2/3/4、Live infra、以及 true live 前的受監督/受限自主放權。

**Live 前置**：LIVE-GUARD-1 + LIVE-GATE-BINDING-1 代碼已存在；LiveDemo/live runtime currently authorized；Decision Lease router evidence flag is ON for shadow W-C only。True live 仍缺 MAG-082/083/084、edge decision、H0 production caller、pricing binding、supervised-live state machine、HTTPS/credentials/legal/runbook，以及 operator explicit sign-off。

**關鍵文件指針**（按需 Read，不要全載入）：
- TODO.md v14 active dispatch queue + `2026-05-08--full_audit_fix_plan.md`
- `docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md` for removed historical context
- **REF-20 Gap Closure Plan V1 (2026-05-04, current SoT for Sprint A-D)**：`docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md`
- REF-20 V3 SoT (legacy schema/route foundation)：`docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`
- REF-20 Sprint 4 final closure：`docs/execution_plan/2026-05-03--ref20_sprint4_final_closure.md`
- REF-20 Sprint 3 Track I Linux deploy runbook：`docs/execution_plan/2026-05-03--ref20_sprint3_track_i_linux_deploy_runbook.md`
- REF-20 Sprint 3 Track H reports：`docs/CCAgentWorkSpace/{PA,E1,E2,E4}/workspace/reports/2026-05-03--ref20_sprint3_track_h_*.md`
- AMD-2026-05-02-01 Decision Lease retrofit path A：`docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
- AMD-2026-05-03-01 Wave 7 amendment：`docs/governance_dev/amendments/2026-05-03--ref20_wave7_p5_impl_accept_deploy_blocked.md`
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`
- 4-day codex audit closure 詳細：`docs/archive/2026-05-02--TODO-pre-trim-snapshot.md`

---

## 十一、外部整合工具映射（**GitHub Issues active** posture）

**核心原則**：**git `srv/` 是唯一 source of truth**。外部工具僅為 *view layer*、*artifact store*，永不擁有交易參數 / 代碼 / 政策的權威。任何衝突一律以 git 為準。

**Posture（2026-05-08 operator 決定）**：**GitHub Issues 是 active issue tracker**。Linear 僅保留為歷史 / passive 參考，除非 operator 明確重新開啟。

### `.codex/` 平行目錄角色（2026-05-02 operator 決定）

`.codex/` 是 codex session 用的**純提示輔助目錄**（git tracked，方便雙端 sync），**不擁有任何治理權**：

- **唯一 governance SoT**：`CLAUDE.md` + `TODO.md` + `.claude/agents/<NAME>.md` + `docs/CCAgentWorkSpace/<NAME>/{profile,memory}.md`
- `.codex/agents/*.md` / `.codex/skills/INDEX.md` 等 = codex session 啟動時的提示鏡像，與 `.claude/agents/` 衝突時**一律以 `.claude/agents/` 為準**
- `.codex/MEMORY.md` / `.codex/WORKLOG.md` / `.codex/DISPATCH_LEDGER.md` = codex session 工作流水筆記，**不替代** Claude 端 memory
- 變更治理規則時：先改 CLAUDE.md / `.claude/agents/`，再人工或 codex 自己同步 `.codex/`；**禁止**反向

### 工具狀態表

| 工具 | 狀態 | 用途 |
|---|---|---|
| `srv/` git | **Source of truth** | 代碼 / CLAUDE.md / TODO.md / memory / docs |
| **GitHub Issues** | **🟢 ACTIVE** | issue / PRD / mattpocock engineering skills tracker |
| **Linear** | **🟡 HISTORICAL / PASSIVE** | 既有 62-finding remediation tracker 參考；不再作為新 issue 默認入口 |
| **Notion** | **❄️ FROZEN** | 2026-04-29 bootstrap 快照（5 pages），不再同步 |
| **Google Drive** | **🟡 PASSIVE** | 按需 binary artifact，0 SOP |
| **Coupler.io** | **❌ DECLINED** | 不啟用 dataflow |
| **MotherDuck** | **❌ DECLINED** | 已移除 connector |
| **Slack** | **❌ DECLINED**（可 revisit pre-live ~2026-05-15）| 不 authenticate；live 前 2 週評估純 alert channel |

### Bootstrap 入口

- **GitHub Issues**：repo `yunancun/BybitOpenClaw`；詳 `docs/agents/issue-tracker.md`
- **Linear (historical/passive)**：team `NCYu` · project [`OpenClaw 62-Finding Remediation`](https://linear.app/ncyu/project/openclaw-62-finding-remediation-de1bc8f68e42)
- **Notion (frozen)**：[OpenClaw — Operator Hub](https://www.notion.so/350dcd3b1eff81038de2d10874ae0fe4)

### SOP（簡化版）

**PM**：Wave/Batch Sign-off 後按需更新對應 GitHub issue（description checklist + status flip）；**Notion 不更新**；新 finding 判斷是否 mainline，是則建 GitHub issue。**不要**把 TODO.md 全鏡像 GitHub Issues。

**PA / 審計 agents**：RFC / audit 寫入 `docs/CCAgentWorkSpace/.../reports/` 或 `docs/audits/` / `.claude_reports/`。**不要**寫 Notion；issue 發布走 `docs/agents/issue-tracker.md` 的 GitHub workflow。

### 嚴禁事項

- 把 GitHub Issues / Linear / Notion 當有否決權；它們鏡像，git 決策
- 自動同步 TODO.md → GitHub Issues；策展鏡像 only
- 在任何外部工具發布 secrets / API keys / authorization tokens
- 啟用 Coupler.io dataflow / authenticate Slack（已 declined）
- 未經 operator 授權發布 runtime engine state 到任何外部工具

### 重新評估觸發點

只有以下情況才考慮重啟 declined / passive 工具：**Linear**（operator 主動要求重新融入）/ **Coupler.io**（本機 DuckDB / psql 真不可行）/ **Slack**（approaching live ~2026-05-15 需 mobile alert）/ **MotherDuck**（見 `memory/reference_external_tools.md`）/ **Notion**（operator 主動要求重新融入）。

---

## Agent skills

### Issue tracker

Issues and PRDs for mattpocock engineering skills are tracked in GitHub Issues for `yunancun/BybitOpenClaw`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default five-label triage vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo: read root `CONTEXT.md` and relevant ADRs under `docs/adr/`. See `docs/agents/domain.md`.
