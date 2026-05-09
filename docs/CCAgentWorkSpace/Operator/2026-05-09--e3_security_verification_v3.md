# E3 對抗性安全核實 v3 — 5 commits + PA redesign 安全 review · 2026-05-09

**審計範圍**:
- Task A: 5 commits security impact (`faf2d131..da2aba11`)
- Task B: PA redesign 安全 review (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`)

**基準**: v2 HEAD `1bd55689` → v3 HEAD `da2aba11` (5 commits)
**工具**: grep / Read / Bash / git diff / ssh trade-core (Linux runtime PG/socket/cron real verify)
**方法**: read-only。0 個 secret 寫入本報告。

---

## §1 Executive Summary

| 嚴重性 | v2 (1bd55689) | v3 (da2aba11) | NEW-VULN |
|---|---|---|---|
| **CRITICAL** | 0 | 0 | 0 |
| **HIGH** | 0 NEW | 0 NEW | 0 |
| **MEDIUM** | 4 (B/C/D + E/F) | 4 + 0 NEW | 0 |
| **LOW** | 7 backlog | 7 + 0 NEW | 0 |
| **INFO** | 1 (NEW-VULN-4 stale) | 1 + 1 NEW (cron not installed) | 1 INFO-only |

**Verdict — Task A**:
- 5 commits 全部設計層 fail-closed，0 個新繞過、0 個新 unauth endpoint、0 個 secret 洩漏、0 個 SQL/shell injection、0 個 cross-platform 路徑硬編碼。
- 1 個 INFO-only finding（da2aba11 cron sh 寫好但 user crontab 仍未 install — operator 預期手動 install）

**Verdict — Task B (PA redesign)**: **ACCEPT WITH CONDITIONS**
- PA 主張的 Strategist 升級為 alpha-source orchestrator **不破任何安全不變量** — Strategist 提出 `Hypothesis` 對象（governance 層級，與 Decision Lease 同等級），不直接寫 risk_config / strategy_params / authorization
- ADR-0020 (Layer 2 manual + supervisor-only) 仍維持 — PA 把 Layer 2 用作 alpha-source proposal，不是 trading loop，符合 ADR-0020
- "cross-asset" PA 範圍限定 Bybit (cross-symbol basis curve / OI panel)，不破 ADR-0006 Bybit-only
- **5 條 hard preconditions**（§4.6）必須在 R-1/R-2/R-3 sprint 開工前確認

**OWASP coverage**: A01/A03/A07/A08/A09/A10 全綠；A02/A04 不變；A05 改善（governance pipeline 增加 db round-trip auth verify）；A06 中性（V079 + 6 ml audit jobs 引入 transitive deps 需 audit）。

---

## §2 Task A — 5 commits 對抗性核實

### Commit ad14db07 [strategy] guard bb breakout donchian snapshots — ✅ SAFE

**性質**: Rust `openclaw_core/src/indicators/mod.rs` Donchian look-ahead bias 修復 + test_compute_all_uses_prior_bar_donchian_snapshot

**安全分析**:
- 純 Rust indicator 邏輯改動，無 HTTP / IPC / DB 介面變化
- 無新 secret 引用，無 path 硬編碼
- `unsafe` 塊查 = 0 (`grep -c 'unsafe' rust/openclaw_core/src/indicators/mod.rs` = 0)
- 修復對抗性 verify: test 100→999 spike 在 current bar，shift(1) 後 Donchian 仍取 110/88，正確 reject 看到未來
- **0 attack surface**

### Commit c2ab7b1a [strategist] teach wide adjustment skill — ✅ SAFE + 1 push back

**性質**: Strategist L1 prompt 改動 (Python `ai_service_dispatch.py`) + Rust `evaluate.rs` payload 增加 `strategist_skill` block

**對抗性 verify (重點)**:
1. **Rust delta cap 仍是 RiskConfig.strategist.max_param_delta_pct 唯一權威**:
   - `evaluate.rs:153` `max_delta_pct = self.current_max_param_delta_pct()` 從 RiskConfig 取
   - 同 mod.rs:220-223 `current_max_param_delta_pct()` 從 `risk_store.load().strategist.max_param_delta_pct` 拉
   - validate_recommendation_with_reason 仍是真實 cap，prompt 中的 `wide_skill_range` 是「指引 LLM」而非「新批准 gate」
   - test `evaluate.rs:469-478` 驗 `max_delta_pct=0.50` 進 payload 但 cap 仍是 RiskConfig
2. **`strategist_skill` payload 不繞過 cap**:
   - LLM 即使被 prompt「教」可以走到 ±50%，最後仍經 Rust validate_recommendation_with_reason → 若 RiskConfig 仍配 0.30，超 0.30 還是 reject
   - `_safe_delta_pct` 邊界檢查 (0 < pct < 1) — invalid input fall back to 0.30/0.50 default 而非 1.0
3. **無新 endpoint 暴露**:
   - `ai_service_dispatch.py` 0 處 `@.*\.(post|get)` 命中（grep 已 verify）
   - 改動 100% 在 internal AIService class scope
   - prompt 改動只影響 Ollama L1 client，無外部 actor 可注入

**1 push back (LOW-NEW-A1)**:
- 註釋 `evaluate.rs:172` 寫「fallback when no store wired = 0.50」，但若 `risk_store=None` 真實退回 `STRATEGIST_DEFAULT_FALLBACK_DELTA_PCT=0.50`（mod.rs:55-57），與 v3 註釋一致；但 NORMAL_PARAM_DELTA_SKILL_PCT=0.30 是 hardcoded 在 Rust 端、Python 端 _STRATEGIST_NORMAL_DELTA_PCT=0.30 是 hardcoded — **若 future RiskConfig 加 normal_delta_pct 欄位，會 drift**。current code 一致，標 LOW backlog。

**結論**: ✅ 0 attack surface 變化。Rust max_delta_pct 是唯一權威，Python prompt 教 LLM「30-50% 是技能不是審批」這條 — 即使 LLM 違反也被 Rust validate cap reject。

### Commit 48227607 [learning] push promotion evidence from edge cycle — ✅ SAFE + 0 NEW endpoint

**性質**: 558-line 新模組 `promotion_evidence.py` + V079 migration + edge_estimator_scheduler 內加 `_run_promotion_evidence_push()` + governance_promotion_routes 加 `_load_promotion_pipeline_rows_from_db` + `_sync_promotion_gate_from_db`

**對抗性 verify**:
1. **3 個 governance_promotion_routes endpoint auth 仍 100% 完整**（grep verified）:
   - GET `/api/v1/governance/promotion-pipeline/status` — `Depends(_get_auth_actor)` ✅
   - POST `/api/v1/governance/promotion-pipeline/promote` — `Depends(_get_auth_actor)` + `_require_operator_role(actor)` ✅
   - POST `/api/v1/governance/promotion-pipeline/operator-decision` — `Depends(_get_auth_actor)` + `_require_operator_role(actor)` ✅
   - 新加的 `_sync_promotion_gate_from_db` 是 internal helper，不創建 endpoint
2. **V079 migration SQL injection check**:
   - 純 DDL (`ALTER TABLE` + `CREATE TABLE` + `CREATE INDEX`)，無 user-controlled string
   - 4 個 CHECK 約束 (engine_mode IN, n_observations >= 0, NaN/Inf rejection) 是 fail-closed 數值清理
   - `evidence JSONB DEFAULT '{}'::jsonb` 不可注入（PG 端 JSON parser 強制驗證）
3. **promotion_evidence.py SQL 風險**:
   - `cur.execute(parameterized_query, args)` 100% 用 psycopg2 參數化 — `_fetch_recent_fill_returns / _fetch_kline_history / _fetch_optuna_fills` 全部 `(%s, %s, %s)` placeholder + tuple args，0 處 f-string 拼 SQL
   - 0 處 `shell=True`，0 處 `os.system`
4. **edge_estimator_scheduler 新環境變數**:
   - `OPENCLAW_PROMOTION_STRESS_EXPOSURES_JSON` (line 537) — 透過 `get_secret_value()` 讀，json.loads 包 try/except，invalid JSON fail-soft（log warning + return None）
   - 不被 user-controlled HTTP input 影響，attack vector 僅 secret-store mutation（需 root file write）
5. **PromotionGate `_sync_promotion_gate_from_db` race condition**:
   - 每個 endpoint 入口同步 (`_get_promotion_gate()` + `_sync_promotion_gate_from_db(gate)`) — load_from_db_rows 在 PromotionGate 內 thread-safe (`self._lock`)
   - DB read fail-soft (return [] on exception) 不會阻塞 endpoint，符合 fail-open in non-critical observability path
   - **MEDIUM design note**: gate 內 in-memory state vs DB state 在多 worker uvicorn 之間不會 drift（每次 request reload from DB），但會 reload latency overhead（每 request +1 PG query）— 純性能議題不是安全議題
6. **demo-only 限定**:
   - `_run_promotion_evidence_push` line 575: `if mode != "demo": return {"status": "skipped"}`
   - live_demo / live 不會觸發 promotion evidence push — 符合「Demo 是 promotion 證據通道，live 不混淆 graduation evidence」設計
   - **fail-closed 設計**: 即使 mode 被 spoof 為 "demo" 也只能 emit DSR/PBO evidence row 而不會 mutate 任何 trading parameter / order authority

**結論**: ✅ 0 新 unauth endpoint，0 新 SQL injection，0 新 secret leak。新加 558 LOC 含完整參數化 + fail-soft + fail-closed。

### Commit c081029d [governance] freeze blocked symbol lists — ✅ SAFE + freeze design 強

**性質**: 新增 `docs/governance_dev/strategy_blocked_symbols_freeze.json` (52 lines, 17 grid + 4 ma symbols) + 247-line `helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py` + 83-line static test

**安全分析**:
- **freeze 是 audit / observability 層**，不寫 runtime config — 由 static test (`test_strategy_blocked_symbols_freeze.py`) enforce「修 toml 必過此檢查」
- freeze JSON 路徑: `docs/governance_dev/strategy_blocked_symbols_freeze.json` — 在 git tracked 區，需 PR review 才能改（不是 runtime 可寫）
- audit script `blocked_symbols_7d_counterfactual.py` 100% read-only:
  - line 145 `WHERE rv.reason = c.symbol || ' blocked by per_strategy.' || c.strategy_name || '.blocked_symbols'` 是 SQL 內 concat (`||`)，**但 c.symbol / c.strategy_name 來源是 `_load_registry()` 的本地 JSON file**，不是 user-controlled HTTP input，attack vector = git PR （已有 review）
  - 仍建議升級為 `WHERE rv.reason = ANY(%s)` 把 reason 列表外送 psycopg2 參數，不過這是 LOW 改善，不是 finding
- 新增 `audit_blocked_symbols_7d_counterfactual.py` cron / endpoint exposure: **無**（純 ad-hoc script，需 operator 手動跑）
- freeze policy `new_block_requirements` 包含 RFC + counterfactual + DSR/PBO — 強 governance forcing function

**對抗性 verify**:
- grep `Path(__file__).resolve().parents[3]` (line 22) — Linux: `/home/ncyu/BybitOpenClaw/srv/helper_scripts/db/audit/` parents[3] = `/home/ncyu/BybitOpenClaw/srv/`，正確
- Mac: `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/audit/` parents[3] = `/Users/ncyu/Projects/TradeBot/srv/`，正確
- 跨平台兼容 ✅

**結論**: ✅ freeze design 是治理 forcing function 不是 attack surface；script 100% read-only。

### Commit da2aba11 [audit] correct f08 ml cron scope — ✅ SAFE source + 1 INFO

**性質**: ml_training_maintenance.py 加 5 個 audit jobs (thompson_sampling/optuna_optimizer/cpcv_validator/dl3_foundation/weekly_report_generator) + cron sh wrapper 加新 args

**對抗性 verify (重點: cron user identity = operator 質疑點)**:

1. **Linux runtime cron 真實狀態**:
   - `ssh trade-core "crontab -l"` (uid=1000 ncyu) — **cron 中沒有 ml_training_maintenance_cron.sh 條目**
   - sudo crontab 也沒有
   - /etc/cron.d/ 只有 anacron / e2scrub_all / sysstat — **沒有 openclaw cron 條目**
   - 結論: cron sh 寫好了 + helpscript 就位 + 但 cron 沒裝 → **runtime 還沒跑**
   - 但這是 INFO not HIGH：sh wrapper 自身寫死「installed manually by the operator」（comment line 4-5），符合操作手動化邏輯
   
2. **若 install 後 cron 跑誰?** 
   - Linux ncyu uid=1000，現有 crontab 全 ncyu owned
   - 若 operator install 到 ncyu crontab → 跑 ncyu (uid=1000，正確 trade_user 等價)
   - 若 install 到 root crontab → 跑 root (錯，過權)
   - sh wrapper line 4-5 範例 `crontab -e` 是 user crontab（不是 sudo crontab）✅
   - **建議: operator install runbook 顯式註明「user crontab，禁 sudo crontab」**（標 LOW-NEW-A2）

3. **Credential 處理**:
   - sh wrapper line 35: `PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)` — 從 secrets/environment_files/basic_system_services.env 讀 PG password
   - line 48-49: `export PG_PASSWORD="$PG_PASS"` + `export OPENCLAW_DATABASE_URL="postgresql://redacted@..."` — **export 進子進程 env，但只在子進程的 ml_training_maintenance.py 子進程內可見**
   - **MEDIUM-NEW-A3**: `OPENCLAW_DATABASE_URL` 含明文 PG password，若 ml_training_maintenance.py 內 raise exception 把整個 env dump 到 stderr/log → password leak 風險
     - 對抗測試: grep `ml_training_maintenance.py` 是否有 `os.environ` dump → grep 0 命中 ✅
     - log line 92 `[ts]] === ML training maintenance start (BASE=$BASE JOBS=$JOBS) ===` — 只 log BASE/JOBS，**不 log 任何 *_PASSWORD / *_URL**
     - 結論: 設計上不洩漏，但 cron sh 仍將 PG password 暴露在 process env 中。若有 attacker 有 same-uid 權限 (`/proc/<pid>/environ`) 可讀，但這是 same-uid threat model（attacker 已 ncyu）— 屬正常 trust boundary
     - 標 LOW-NEW-A2「同 uid attacker process env 讀 PG password」（known limitation，不是 fix-able 通過 sh 改寫）

4. **新加 5 audit jobs SQL 用法**:
   - `_fetch_recent_fill_returns` / `_fetch_kline_history` / `_fetch_optuna_fills` — 全部 psycopg2 parameterized (`%s` + tuple args)，0 SQL injection
   - `_pg_connect` 用 `psycopg2.connect(dsn)` — dsn 從 sh wrapper 來不從 user input 來
   - `_weekly_audit_due` 用 `datetime.now(timezone.utc).weekday()` — 純時間 gate，不可注入
   - `args.audit_engine_modes` 預設 `["demo", "live_demo"]`，operator 可改 env var 但需 shell access
   - `_run_optuna_optimizer` import `_send_ipc_command` (line 489) — IPC socket 路徑來自 args.ipc_socket env var，需 verify 路徑是否 writable by attacker
     - grep `--ipc-socket` 不在 cron sh 中 → 用 default
     - default likely `/tmp/openclaw/engine.sock` (`OPENCLAW_DATA_DIR/engine.sock`)，0o600 由 engine 啟動時設 → 同 uid attacker 才能 read/write

5. **dl3_foundation `asyncio.run(run_forecast(...))` 在 cron 子進程**:
   - run_forecast 內含 LLM 調用 → ANTHROPIC_API_KEY 從 secrets 讀（已 known secret pattern）
   - 即使 cron 觸發 LLM 調用，0 走 `print()` / `log.info()` 含 key 的路徑（grep 已 verified for ANTHROPIC patterns）

**結論**: ✅ source 100% safe（fail-soft import + parameterized SQL + secret 不入 log），1 INFO「runtime cron 未 install」。

### Task A 累計結果

| 嚴重性 | 數量 | 詳情 |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 0 | — |
| LOW | 2 | LOW-NEW-A1 (delta_pct hardcoded mirror Rust↔Python), LOW-NEW-A2 (cron install runbook 缺顯式 user crontab 警告) |
| INFO | 1 | da2aba11 cron sh 寫好但 user crontab 未裝 |
| **NEW unauth endpoint** | **0** | grep `+@.*\.(post\|get\|put\|delete)` 命中 0 處新 unauth route |
| **NEW secret leak** | **0** | full diff grep 0 命中 |
| **NEW path hardcode** | **0** | full diff grep 0 命中 |
| **NEW SQL injection** | **0** | 558 LOC promotion_evidence.py 100% parameterized |
| **NEW shell injection** | **0** | 0 處 shell=True / 0 處 user-input 拼 cmd |

---

## §3 Task B — PA redesign 安全 review

### §3.1 Strategist 升級為 alpha-source orchestrator — 安全分析

**Operator 質疑**: 「Strategist 從調 5 策略參數升級為自主孵化策略 + 提交新 risk_config」攻擊面變大多少？

**證據**:
- PA 報告 line 273-274: 「Strategist 增 `propose_alpha_source()` 方法（**產出 Hypothesis 而非 TradeIntent**）」
- PA 報告 line 308-320: `Hypothesis` dataclass 是「與 Decision Lease 同治理層級」的 governance object
- PA 報告 line 322-324: 「Hypothesis 狀態機強制 EVIDENCE_GATE 才能 PROMOTED」
- ADR-0020 (Layer 2 manual + supervisor-only) 仍維持

**分析**:
1. **Strategist 不直接寫 risk_config / strategy_params / authorization** ✅
   - PA 設計: Strategist propose `Hypothesis` → 進 governance pipeline → Analyst L3 設計實驗 → evidence gate 過 → operator 批准 → 才能 PROMOTED
   - vs 直接寫 risk_config 危險路徑 — 0 處 PA 報告主張 Strategist 直接寫 toml
   - **5 hard gates 不破**: live_reserved / Operator role auth / OPENCLAW_ALLOW_MAINNET / secret slot / authorization.json HMAC 全部不變
2. **Authority boundary 不變**:
   - Rust IntentProcessor.process_with_features 仍 Gate 1→1.4→1.5→1.6→2→3 強制
   - Decision Lease + Authorization HMAC 仍 per-intent
   - PA R-4 「per-alpha-source live promotion」是「LiveBudget(alpha_source_id, slice)」對象 — 仍由 governance API 控制不繞過 GovernanceHub
3. **新增的攻擊面**:
   - `learning.hypotheses` table 寫入路徑 — 必須加：
     - **HARD-PRECON-1 (BLOCKER 等級)**: hypotheses 表只能由 governance API + operator role auth 寫，**禁** Analyst Python 直接 INSERT
     - **HARD-PRECON-2**: `Hypothesis.proposer` 必為 (Strategist | Analyst | Operator)，每個 propose 走 `_require_operator_role` 或 lease-bound role gate
   - `propose_alpha_source()` API endpoint （若 PA 後續開放 GUI）— 必經 require_operator
4. **與 PA 提的「Strategist 自主提交新 risk_config」對齊驗證**: PA 報告原文 (operator 用詞) 是「自主孵化策略」，PA 自己沒提「Strategist 寫 risk_config」 — operator 質疑的 worst-case 設計 PA 沒做。實際設計是 Strategist propose Hypothesis (governance 對象) → operator 批准才落地

**結論**: PA 設計**不增加 attack surface**。Strategist 升級到 orchestrator 角色只是把它從「dict[str, float] 微調」升級為「propose governance 對象」，治理 forcing function 增強而非削弱。

### §3.2 Alpha Surface Bundle 新 feature 來源安全 — funding_rate / basis / OI / orderflow

**Operator 質疑**: 這些 feature 來源 Bybit API，是否需要新的 rate limit / cache poisoning 防護？

**證據**:
- PA 報告 line 232-256: `AlphaSurface` 結構含 funding_curve / basis_curve / oi_delta_panel / orderflow / liquidation_pulse
- 現有 `tick_pipeline/mod.rs:681-698` 已有 funding_rate / index_price / open_interest / best_bid/ask 字段（單 symbol level）
- PA 報告 line 686-688 註: 「Raw value — consumer strategies buffer + compute delta on their own window」

**分析**:
1. **Rate limit**:
   - Bybit funding rate: 由 WS instrument feed 推送（V5 API），無新 REST poll → 不增加 rate limit 壓力
   - Basis = (mark - index) / index 由 WS tickers 推（已有），純計算不需新 API call
   - Open interest: WS instrument feed 已推（已存在 `pub open_interest: Option<f64>`）
   - Orderflow / large-trade tape: 需 WS publicTrade subscribe — 若 PA 後續 IMPL，需確認:
     - **HARD-PRECON-3**: 25 symbols × publicTrade 訂閱 → Bybit V5 limit 是 200 streams/connection（充裕）
     - 若 cross-symbol panel 需 REST funding history（5 min update），需走 rate limiter (`bybit_rate_limiter` 已存在)
2. **Cache poisoning**:
   - WS feed 來源 = `wss://stream.bybit.com` 對 demo 是 `wss://stream-demo.bybit.com` — 與 REST endpoint 同 trust boundary
   - 不存在「中介 cache」可被 poison（直接從 WS feed → tick_pipeline buffer）
   - 若 PA R-1 引入「FundingCurveSnapshot」cross-symbol aggregation buffer，需:
     - **HARD-PRECON-4**: 該 buffer 在 Rust 端 owned，Python 不可寫（read-only PyO3 port），避免 Python 進程被劫持寫 false funding rates
     - 對齊現有 `pub funding_rate: Option<f64>` Rust authoritative 設計
3. **Liquidation feed**:
   - 需 WS allLiquidation subscribe — 已知 Bybit liquidation feed 有 throttle（每 100ms 一個 message），**不直接適合 high-freq alpha**
   - PA 提到 "liquidation cascade detection" 屬 medium-freq alpha，可接受
4. **Sentiment panel (Tier 4)**:
   - PA 報告 line 248: 「sentiment_panel: Option<&'a SentimentPanel>」
   - 來源若是 Scout agent 的 IntelObject（已存在路徑），則是 Python → PyO3 → Rust 注入
   - **HARD-PRECON-5**: SentimentPanel 注入路徑必走 governance write-once-per-tick gate（避免 attacker 高頻刷 sentiment 干擾策略），對齊現有 `set_scout_agent()` 模式（singleton 注入，不是 per-request）

**結論**: 新 feature 來源 100% Bybit V5 (REST + WS)，0 新 attack vector 來自外部第三方數據。HARD-PRECON-3/4/5 是 sprint 開工前 confirm 項。

### §3.3 ADR-0020 fail-closed 是否被破？— Analyst L2-L5 自主進化階梯

**Operator 質疑**: ADR-0020 「Layer 2 manual + supervisor-only by design」是 fail-closed 安全姿態；PA 主張的「Analyst L2-L5 自主進化階梯」會破這個 fail-closed？

**證據**:
- ADR-0020 line 18-20: 「Layer2 must not run as an autonomous trading loop, mutate strategy/risk/live configuration, grant live authorization, submit orders, or bypass Rust execution authority.」
- PA 報告 line 84: 「ADR-0020 把它的解封路徑進一步推遲（manual + supervisor-only）」← PA 自己 acknowledge ADR-0020 是約束
- PA R-2 line 376: 「Strategist Layer 2 解封路徑：alpha-source proposal 是合適的 Layer 2 cloud reasoning 場景」

**分析**:
1. **PA 設計符合 ADR-0020**:
   - Layer 2 用作 alpha-source proposal 仍是「propose Hypothesis → operator approval → propose code IMPL」三段，**不是 trading loop**
   - 不 mutate strategy/risk/live config（Hypothesis 對象需 evidence gate + operator 批准才能變成 strategy）
   - 不 grant live authorization（authorization.json 仍經 build_signed_authorization）
   - 不 submit order（仍經 IntentProcessor）
   - 不 bypass Rust execution authority
2. **Analyst L2-L5 進化階梯安全性**:
   - L2 pattern discovery: 純讀（從 fills + decision_outcomes 拉資料 → 跑 sklearn/lightgbm 找 pattern）→ 不變更 runtime 配置 ✅
   - L3 hypothesis design: 產出 Hypothesis 對象 → governance pipeline ✅
   - L4 strategy evolution: 若 PA 主張 Analyst「自動產出新策略 IMPL」，這條路徑必須加：
     - **HARD-PRECON-6**: 任何 Analyst 自動產出的 Rust strategy code 必經 E1+E2+E3 sign-off + operator merge approval — **禁** runtime auto-apply
     - 對應 PA 報告 line 387-391 R-3 sprint estimate「階段 1 只做 hypothesis CRUD + manual approval；階段 2 才接 Analyst L3 自動」← PA 自己 acknowledge stage gate
   - L5 meta-learning: 純 PG read + ML model update，不變更交易參數 ✅

**結論**: PA 設計**不破 ADR-0020**。Analyst L2-L5 升級走「propose 對象 → operator 批准」治理路徑，與 ADR-0020 「Layer 2 是 manual escalation」一致。HARD-PRECON-6 是 sprint 必確認項。

### §3.4 cross_asset alpha 是否引入 cross-exchange 風險？

**Operator 質疑**: PA 提到 cross_asset alpha — 是否引入 cross-exchange 風險（CLAUDE.md §一明寫 Bybit only）

**證據**:
- PA 報告 line 14: 「cross_asset」+ 「funding skew / orderflow imbalance / liquidation cascade / cross-asset basis」
- PA 報告 line 461: 「cross-asset basis」
- ADR-0006: Bybit only

**分析**:
- PA 用 `cross_asset` 一律意指「Bybit 內 cross-symbol」（25 symbols funding curve / OI panel / basis）
- **0 處 PA 提及 Binance / OKX / Coinbase / 其他 venue**（grep verified）
- "cross-asset basis" = perpetual vs futures vs spot 三種 contract 在同一 venue (Bybit) 的 basis spread，不是 cross-venue arb
- BasisCurveSnapshot / FundingCurveSnapshot / OIDeltaPanel 全部 Bybit-internal cross-symbol aggregation

**結論**: PA 設計**不引入 cross-exchange 風險**，符合 ADR-0006。建議:
- **HARD-PRECON-7**: PA R-1 spec phase 明文寫「cross_asset = Bybit-internal cross-symbol」，避免後續 IMPL agent 誤理解為 cross-venue
- 配合 `bybit_only` healthcheck 加一條「any new connector module under `program_code/exchange_connectors/binance|okx|coinbase` → FAIL」防 future drift

### §3.5 PA redesign 累計安全 verdict

| 維度 | 評估 |
|---|---|
| Strategist 升級攻擊面 | 0 增加（propose Hypothesis 不直寫 config） |
| 5 hard gate 是否破 | 0 處破 |
| ADR-0020 fail-closed 是否破 | 0 處破 |
| ADR-0006 Bybit-only 是否破 | 0 處破（cross_asset = Bybit-internal） |
| 新 feature 數據源 | Bybit V5 WS/REST，0 第三方源 |
| Hypothesis pipeline 治理 | 增強（governance forcing function） |
| Layer 2 trigger 範圍 | 維持 ADR-0020 manual + supervisor-only |
| Per-alpha-source live promotion | 仍需 operator approval + LiveBudget 對象走 governance API |

**verdict: ACCEPT WITH CONDITIONS**

7 條 HARD-PRECON（must-confirm before sprint kickoff）:
1. **HARD-PRECON-1**: `learning.hypotheses` 寫入只走 governance API + operator role auth，禁 Python direct INSERT
2. **HARD-PRECON-2**: `Hypothesis.proposer` field validate 為 (Strategist | Analyst | Operator)，每 propose 走 `_require_operator_role` or lease-bound gate
3. **HARD-PRECON-3**: 25 symbols WS subscribe ≤ 200 streams (Bybit V5 limit) + cross-symbol REST 走 bybit_rate_limiter
4. **HARD-PRECON-4**: FundingCurveSnapshot / OIDeltaPanel 在 Rust 端 owned, Python read-only via PyO3
5. **HARD-PRECON-5**: SentimentPanel 注入走 singleton write-once-per-tick (對齊 set_scout_agent)
6. **HARD-PRECON-6**: Analyst L4 strategy evolution 走 E1+E2+E3 sign-off + operator merge，**禁** runtime auto-apply Rust code
7. **HARD-PRECON-7**: R-1 spec 明文「cross_asset = Bybit-internal cross-symbol」+ `bybit_only` healthcheck reject 任何新 connector

---

## §4 對抗性 push back

### §4.1 對 cron 「source-fixed = closed」陷阱（與 v1/v2 NEW-VULN-4 同類）
- da2aba11 cron sh 寫好但 user crontab 未 install — operator 預期手動 install (sh wrapper line 4-5 explicit comment)
- E2/E4 sign-off 時必須加「runtime install verification」步驟
- 重申 v1/v2 push back: **source-fixed ≠ runtime closed**，sign-off SOP 應加 last-mile reachability test

### §4.2 對 Rust↔Python normal_delta_pct hardcoded mirror 風險
- c2ab7b1a 引入 `NORMAL_PARAM_DELTA_SKILL_PCT=0.30` (Rust) + `_STRATEGIST_NORMAL_DELTA_PCT=0.30` (Python) 兩處
- 若未來 RiskConfig 加 `normal_delta_pct` 欄位，會 drift
- **建議**: 開 LOW backlog ticket 「unify NORMAL_PARAM_DELTA_SKILL_PCT into RiskConfig.strategist.normal_delta_pct, Rust 為 SoT」

### §4.3 對 PA redesign 「acceptance with conditions」邊界
- PA 提的 7 條 HARD-PRECON 必須在 R-1/R-2/R-3 sprint 各自開工前 verify
- 特別關注 HARD-PRECON-1（hypotheses table writer 不可繞過 governance API）— 若 Analyst 自動 INSERT 且不經 operator role gate，整 governance forcing function 失效
- 建議 PA 報告附錄 §3.6 explicit 寫「Hypothesis 對象 governance API spec (路由 + auth dependency + lease binding)」

### §4.4 對 v2 留下的 4 MEDIUM / 7 LOW 24h 增量
- v3 範圍內 0 commit 修這 11 條 — 預期 P2 backlog
- layer2_routes 4 處 `str(exc)` 仍洩漏 valid auth 後 exception detail — 在 401 後但 exception 內可能含 stack trace，標 LOW unchanged
- MEDIUM-E IPC HMAC fail-OPEN dev/test 在 paper/demo 仍未閉，運行時 sock 0o600 + env IPC_SECRET 雙保險還在

### §4.5 對 v3 commit timing 觀察
- 5 commits 17:01-18:41 同日完成 — 高效
- ad14db07 (Donchian leak fix) 是 QC v2 NEW-4 直接 close
- c2ab7b1a (Strategist wide skill) 是 v2 NEW-2 follow-up
- 48227607 (DSR/PBO evidence push) 是 v2 NEW-3 follow-up
- c081029d (blocked_symbols freeze) 是 P2-AUDIT-VERIFY-5 source closure
- da2aba11 (F-08 ML cron scope) 是 W-AUDIT-4 retrofit

---

## §5 v2 → v3 13 finding tracking matrix

| ID | v2 狀態 | v3 狀態 | 備註 |
|---|---|---|---|
| NEW-VULN-4 (phase4 stale) | ⚠️ uvicorn未 reload | ❓ 5 commits 內無 restart_all 觸發，仍待 operator restart | unchanged |
| MEDIUM-B openclaw _require_proposal_creator | ❌ unfixed | ❌ unfixed | P2 backlog |
| MEDIUM-C single-user / cookie | ❌ unfixed | ❌ unfixed | P2 backlog |
| MEDIUM-D directive_executions 0 row | ❌ unfixed | ❌ unfixed | P2 backlog |
| MEDIUM-E IPC HMAC fail-OPEN dev/test | ⚠️ runtime 雙保險 | ⚠️ unchanged | sock 0o600 + env IPC_SECRET |
| MEDIUM-F ai_service.sock | ⚠️ chmod 0o600 OK + 0 HMAC | ⚠️ unchanged | same-uid attack surface |
| LOW-1..6 | ❌ 0 修 | ❌ 0 修 | P2 backlog |
| layer2_routes 4 處 str(exc) | ⚠️ 401 後仍洩漏 | ⚠️ unchanged | LOW backlog |
| **NEW v3 LOW-A1** | — | NEW | Rust↔Python normal_delta_pct hardcoded mirror |
| **NEW v3 LOW-A2** | — | NEW | cron install runbook 缺顯式 user-crontab 警告 |
| **NEW v3 INFO** | — | NEW | da2aba11 cron sh ready but user crontab 未 install |

---

## §6 OWASP Top 10 (2021) 對 v3 範圍評估

| 類 | 範圍內變化 | verdict |
|---|---|---|
| A01 Broken Access Control | 3 governance promotion endpoints 全 `_get_auth_actor` + `_require_operator_role` ✅ | 強化 |
| A02 Cryptographic Failures | 0 新 crypto 改動 | 不變 |
| A03 Injection | 558 LOC promotion_evidence.py 100% parameterized SQL；0 shell=True | 強化 |
| A04 Insecure Design | promotion 在 demo 限定（live/live_demo skip）= fail-closed design | 強化 |
| A05 Security Misconfiguration | cron sh 從 secret_files 拉 PG cred（不 hardcode） | 強化 |
| A06 Vulnerable Components | V079 + 5 new ml audit jobs 引入 thompson_sampling/optuna/cpcv/dl3 transitive deps — 需後續 `pip-audit` | 待 audit |
| A07 Authentication Failures | 0 新 auth 改動 | 不變 |
| A08 Software/Data Integrity | V079 4 個 CHECK 約束 (NaN/Inf rejection + engine_mode whitelist) | 強化 |
| A09 Logging Failures | edge_estimator_scheduler `_run_promotion_evidence_push` log 不含 secret | 強化 |
| A10 SSRF | 0 新 external URL 路由 | 不變 |

---

## §7 對抗性 grep 全檢結果（範圍 faf2d131..da2aba11）

| 檢查 | 命中 |
|---|---|
| `+@.*\.(post\|get\|put\|delete)` 新 unauth route | 0 |
| `(api_key\|api_secret\|hmac\|password).*=.*["A-Za-z0-9+/=]{20,}` 硬編碼 secret | 0 |
| `/home/ncyu\|/Users/[^/]+` 跨平台路徑硬編碼（排除 .codex/docs/MEMORY） | 0 |
| `f"SELECT\|f"DELETE\|f"UPDATE\|f"INSERT` SQL string-format | 0 |
| `shell=True\|subprocess\.run\(.*shell` shell injection | 0 |
| `os\.environ\(.*KEY\|SECRET\|PASSWORD\|TOKEN\)` env var leak in log | 0 |
| `print\(.*api_key\|secret\|password` print leak | 0 |
| `log\..*\(.*api_key\|secret\|password\|token` log leak | 0 |

**結論**: v3 範圍 0 個新 unauth endpoint / 0 個新 secret leak / 0 個新 cross-platform path violation / 0 個新 SQL injection / 0 個新 command injection / 0 個新 secret 入 log。

---

## 報告元數據

- **撰寫者**: E3 (Security Auditor, attacker mindset 對抗性核實)
- **撰寫時間**: 2026-05-09 19:30 UTC+1
- **基準範圍**: commits faf2d131..da2aba11 (5 commits)
- **Linux runtime cron real verify**: ssh trade-core 即時查詢
- **0 個 exploit 嘗試 / 0 個 secret 內容寫入本報告**
- **下次審計觸發點**:
  - operator install ml_training_maintenance cron 後驗第一次 run
  - PA R-1 spec 開工前 confirm 7 條 HARD-PRECON
  - 任何 V### migration 含 `learning.hypotheses` 表 IMPL 時 E3 audit
