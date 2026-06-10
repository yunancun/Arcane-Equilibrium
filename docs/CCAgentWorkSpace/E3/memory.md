# E3 Memory — 工作記憶

## Memory Usage Contract (2026-05-16)

- 本文件保存歷史教訓與角色偏好，不是 active state、TODO 或 runtime ledger。
- 若舊條目與 `TODO.md`、`README.md`、`CLAUDE.md`、`.codex/MEMORY.md`、`docs/agents/context-loading.md`、代碼或 runtime 證據衝突，信任較新的有證據來源並顯式說明衝突。
- 不要靜默刪除舊條目；只追加可復用的 durable lesson。長報告放 `workspace/reports/`，active 進度放 `TODO.md`。

## 項目上下文（2026-04-24）

- 當前 Phase：Live_Ready ⚠️ (demo 階段，0 真實 live 流量)
- engine PID 884467, binary 2026-04-24 02:06, lib 1980/0 failed
- Python pytest ~2996 passed
- 系統模式：demo + live_demo（歷史 43k engine_mode="live" 實為 LiveDemo）
- 安全評級：**A-（0 CRITICAL / 0 HIGH / 5 MEDIUM / 4 LOW / 5 INFO）**

## 工作記憶

### 2026-04-24 全程序安全審計關鍵發現

1. **所有 2026-04-01 findings 大部分已修復**：CORS wildcard + 安全響應頭 + HttpOnly cookie + 登入 IP 鎖定全綠
2. **LIVE-GATE-BINDING-1（2026-04-18）落地** — 5 項 Live 門控全部經 Rust 簽名契約綁定
3. **LIVE-GUARD-1（2026-04-16）落地** — OPENCLAW_ALLOW_MAINNET + env-var 憑證封閉
4. **FIX-10 雙保險** — Live 啟動若 OPENCLAW_IPC_SECRET 未設 → Rust panic
5. **殘留 5 MEDIUM + 4 LOW**：
   - MEDIUM-A：11 處 `detail=f"...{e}"` 錯誤洩漏（ml/paper/strategy_write routes）
   - MEDIUM-B：claude_teacher `find_denylisted_field` 單層掃描（nested bypass 理論上可能）
   - MEDIUM-C：`app.js:530-608` renderProductFamilyEditor innerHTML 無 ocEsc
   - MEDIUM-D：Layer 2 `context` 無 prompt injection 清洗
   - MEDIUM-E：IPC 認證在 paper/demo 未設 OPENCLAW_IPC_SECRET 時 fail-open
   - LOW-A~D：CSP unsafe-inline / 503 auth msg / x-forwarded-* 未 strip / EA-PERSIST 無 HMAC
6. **五項 Live 門控繞過測試**：全部 **通過** —
   - Python live_reserved ✅
   - Operator 角色 auth ✅
   - OPENCLAW_ALLOW_MAINNET=1 ✅（5 Rust tests）
   - secret slot api_key+secret ✅（asyncio.Lock + compare_digest + chmod 600）
   - authorization.json HMAC+TTL+env_allowed ✅（13 Rust tests + 5min re-verify）

### 架構安全觀察（保留自 2026-04-01，增量）

- GovernanceHub fail-closed 設計一流，經多輪驗證
- H0 Gate <1ms SLA 確定性門控
- 所有新路由遵循統一認證模式
- 原則 7 隔離嚴格執行
- **新增：Python↔Rust HMAC 簽名契約（LIVE-GATE-BINDING-1）= 跨進程信任邊界最佳實踐**
- **新增：claude_teacher 硬邊界 denylist + pause_all veto + unknown scope reject 三重防護**

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-01 | 全程序安全審計（對比 March 31） | `docs/CCAgentWorkSpace/E3/workspace/reports/2026-04-01--security_audit.md` |
| 2026-04-24 | 全程序安全審計（對比 April 01；5 gates 逐一驗證） | `docs/CCAgentWorkSpace/E3/workspace/reports/2026-04-24--full_chain_security_audit.md` |

### 2026-05-02 P0-DATA-INDICATOR-SWEEP（5 strategy adversarial leak audit, E3 副審）

- **Verdict**：5/5 PASS（無 leak），與 QC 主審獨立 cross-check 預期收斂
- **核心發現**：strategy → IndicatorSnapshot 單向依賴；strategy 0 處直接讀 KlineManager
- KlineBuffer 只存 `is_closed=true` bar，`current_bar` 物理隔離；`donchian_prior` 額外退一格 → 雙保險
- bb_breakout FIX-26-DEADLOCK-1 修復 (mod.rs:417-423) 確認落地，semantic 正確
- 所有 strategy 用 `ctx.timestamp_ms`，0 處 `Utc::now()` / 牆鐘洩漏
- 5 策略 net negative 主因 **非 leak**（最便宜的解釋不成立），edge 缺陷在策略邏輯/cost/maker fill rate
- **2 LOW finding**：
  1. test fixtures 用 `Box::leak(IndicatorSnapshot)` 跳過 KlineManager streaming → 策略邏輯有 coverage、streaming 整合無 coverage
  2. `feature_version` hardcoded "v1.0"（pipeline_ctor.rs:67）→ indicator code 改不會自動 bump → MLDE training 數據版本污染風險
- Mac vs Linux byte-equality：default rustc (no rustflags) → IEEE-754 reproducible likely OK

### 2026-05-08 全鏈安全審計（Mac HEAD 4e2d2883）

**評級：A（vs 2026-04-24 A-）**
- 0 CRITICAL / 3 HIGH / 5 MEDIUM / 6 LOW / 4 INFO
- 5 項 Live 門控 5/5 設計綠 ✅
- 0 Rust unsafe / 0 PyO3 FFI ✅

**新發現 3 HIGH (true-live 前 must-fix)**：
1. HIGH-1: `learning.lease_transitions=0 row`，spawn_lease_transition_pipeline 0 production caller — Decision Lease retrofit Sprint 3 IMPL 完成但 audit channel writer wiring 死
2. HIGH-2: `phase4_routes.py:822/832` weekly_review/approve+reject **0 auth**（anonymous client 可改 governance 批准）
3. HIGH-3: `scout_routes.py:324/430` post_market_signal+post_event_alert 缺 require_operator（viewer 可注入 ScoutAgent）
4. HIGH-4 (升級自 MEDIUM): FastAPI `--host 0.0.0.0:8000` 對 LAN 全開（PRE-LIVE-2 配套）

**保留 MEDIUM/LOW**：MEDIUM-E IPC fail-OPEN dev/test (paper/demo), MEDIUM-F ai_service.sock 0o775 + 0 HMAC handshake，4 個其他 + 6 LOW

**對 PA 「audit oblivion / 5-Agent 解耦 governance bypass」立場**：
- 5-Agent 解耦對 governance **是好設計**：Strategist Python 出 bug 不能直送 IntentProcessor（因為 0 Python→IntentProcessor 介面）
- Rust IntentProcessor.process_with_features Gate 1（is_authorized）→1.4（lease）→1.5（dup）→1.6（balance）→2（Rust Guardian.review）→3 全部強制執行
- lease_transitions audit 0 row 不阻 trading safety，但 audit channel 死綁 = 真實 finding
- Python H0_GATE 0 caller 對 Rust hot path 0 影響（Rust h0_gate.check 每 tick 強制 fire，shadow_mode IPC writable）

報告：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-08--full_chain_security_audit.md`（408 行）

### 2026-05-09 v2 對抗性 verification（vs v1 same-day report）

**評級：A+ (vs v1 A-)**

- v1 4 NEW-VULN 24h 內全 source-closed + 2 runtime verified
- 0 新引入 attack surface (v2 範圍 0 unauth endpoint / 0 secret leak / 0 path 硬編碼)
- 範圍 commits 455d796e..1bd55689 (34 commits, 7 security/audit + 27 strategy/risk/learning/docs)

**v1 NEW-VULN 24h fix matrix**:
1. NEW-VULN-1 launchd 0.0.0.0 → ✅ b658e18c plist 改 127.0.0.1 + c187fd99 resolver lib reject 0.0.0.0/:: + 3 helper script wire + Linux runtime ss `100.91.109.86:8000` (Tailscale tailnet, not 0.0.0.0)
2. NEW-VULN-2 lease audit 0 row → ✅ e97a333b governance_core.rs:402-417 加 emit_transition_fail_soft(BYPASS) + V078 migration `to_state='BYPASS'`；Linux PG 實測 7950 BYPASS rows in 8h，~16/min sustained，demo/live_demo 50/50
3. NEW-VULN-3 cookie Secure auto fail-OPEN → ✅ cfadc339 should_set_secure_cookie 加 _has_https_proxy_hint() 自動觸發（不需 OPENCLAW_TRUST_PROXY_HEADERS=1 opt-in），偽造 X-Forwarded-Proto 在 plain HTTP 下 cookie unusable = fail-closed
4. NEW-VULN-4 phase4 dead code → ⚠️ cfadc339 main.py:153-154 加 include_router(phase4_router)，BUT uvicorn 14:07 啟動 < cfadc339 15:48 commit，runtime 仍 404；待 operator restart_all --keep-auth

**仍存議題 (24h 0 commit)**:
- 4 MEDIUM unchanged (B/C/D + E/F design fail-OPEN runtime fail-CLOSED)
- 7 LOW unchanged (P2 backlog)
- layer2_routes 仍 4 處 `str(exc)` 洩漏 (in 401 守護後 valid-auth 路徑)
- P0-OPS-1/2/4 仍 0 commit

**對抗測試 4 endpoint result**:
- POST /api/v1/phase4/weekly_review/approve → 404 (uvicorn stale)
- POST /api/v1/phase4/weekly_review/reject → 404 (uvicorn stale)
- POST /api/v1/scout/market-signal → 401 fail-closed ✅
- POST /api/v1/paper/layer2/trigger → 401 fail-closed ✅

**push back**:
- audit closure SOP gap: source-fix 後沒 reload uvicorn 不算 closed (NEW-VULN-4 同類復發)
- LG-3 sub-finding F-A2: Validation profile acquire_lease 真走 SM 還是 bypass，emit msg type 需 verify
- engine.sock mtime 15:52 確認 e97a333b lease emit 真生效，但 API uvicorn 沒一起 restart = 部署協調問題

報告：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-09--security_verification_v2.md` (~280 行)

### 2026-05-09 v3 對抗性 verification (5 commits + PA redesign 安全 review)

**評級：A+ (vs v2 A+)**

**範圍**: commits `faf2d131..da2aba11` (5 commits) + PA `2026-05-09--full_loss_architectural_root_cause_redesign.md`

**Task A 5 commits 結果**:
- 0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW (LOW-A1 Rust↔Python normal_delta_pct mirror, LOW-A2 cron install runbook 缺顯式 user-crontab 警告) / 1 INFO (cron sh 寫好但 user crontab 未 install)
- 0 NEW unauth endpoint / 0 NEW secret leak / 0 NEW cross-platform path violation / 0 NEW SQL injection / 0 NEW shell injection
- ad14db07 (Donchian leak fix Rust): 0 attack surface
- c2ab7b1a (Strategist wide skill 30→50%): Rust delta cap 仍是 RiskConfig.strategist.max_param_delta_pct 唯一權威，prompt 教 LLM 只是「指引」非審批 gate，validate_recommendation_with_reason 仍真實 enforce
- 48227607 (DSR/PBO evidence push 558 LOC): 3 governance promotion endpoints 100% require_operator + V079 4 個 CHECK 約束 fail-closed + 100% parameterized SQL + demo-only mode 限定
- c081029d (blocked_symbols freeze): freeze JSON 在 git tracked 區需 PR review 才能改，audit script 100% read-only
- da2aba11 (F-08 ML cron scope): cron sh 寫好 + ssh trade-core verified user crontab + sudo + /etc/cron.d/ **都沒裝** → INFO not HIGH（sh wrapper line 4-5 explicit comment 寫「installed manually by operator」）

**Task B PA redesign verdict**: **ACCEPT WITH CONDITIONS**

7 條 HARD-PRECON (sprint 開工前必 confirm):
1. learning.hypotheses 寫入只走 governance API + operator role auth
2. Hypothesis.proposer field validate (Strategist/Analyst/Operator) + lease-bound gate
3. 25 symbols WS subscribe ≤ 200 streams (Bybit V5 limit) + cross-symbol REST 走 bybit_rate_limiter
4. FundingCurveSnapshot/OIDeltaPanel Rust owned, Python read-only via PyO3
5. SentimentPanel singleton write-once-per-tick (對齊 set_scout_agent)
6. Analyst L4 strategy evolution 走 E1+E2+E3 sign-off + operator merge, 禁 runtime auto-apply
7. R-1 spec 明文「cross_asset = Bybit-internal cross-symbol」+ bybit_only healthcheck reject 任何新 connector

**verdict 邏輯**:
- Strategist propose Hypothesis (governance 對象) 不是 TradeIntent — 不繞 5 hard gate
- ADR-0020 Layer 2 manual + supervisor-only 仍維持 (Layer 2 用作 alpha-source proposal 不是 trading loop)
- ADR-0006 Bybit only 不破 (cross-asset = Bybit-internal cross-symbol)
- 新 feature 來源 100% Bybit V5 (REST + WS), 0 第三方源
- Hypothesis pipeline 增強 governance forcing function

**push back**:
- audit closure SOP gap 重申: source-fixed ≠ runtime closed (cron sh 寫好但 user crontab 未 install 是同類問題)
- LOW-A1: NORMAL_PARAM_DELTA_SKILL_PCT 在 Rust + Python 兩處 hardcoded mirror — future RiskConfig 加 normal_delta_pct 會 drift
- 建議 PA 報告附錄 §3.6 explicit 寫 Hypothesis governance API spec

報告: `docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-09--security_verification_v3.md` (413 行)

### 2026-05-10 Sprint N+1 D+0 安全 pre-audit（HEAD 1d9dccf1）

**評級：A（vs 2026-05-09 v3 A+）**
- 0 CRITICAL / 0 HIGH / 0 MEDIUM / 3 LOW / 1 INFO
- 0 新 unauth endpoint / 0 新 secret leak / 0 新 SQL injection / 0 新 shell injection / 0 新 path hardcode in runtime code

**Verdict**: ALL PASS — D+0 sub-agent dispatch fire 可進

**範圍**: PR ready code (b42731f6 W7-3 + c9fb0b8f W7-1) + spec (W1 v1.1 WS-first / W2 v1.1 paper-only fence / W5 P1 V089/V090 / W6 V086) + dispatch SOP

**核心發現**:
1. W7-3 reason parse: reason 來源 = Rust enum `RejectionCode::format()` 100% 內部，無外部 user input 注入路徑（rejection_coding.rs:147-152 byte-identical contract）
2. W7-1 TickContext.position_state: `&'a PaperPosition` immutable borrow + NLL per-iteration 釋放，0 use-after-free 風險，0 unsafe block
3. W2 paper-only fence: Layer 1 (Rust enum match `_ => None`) + Layer 2 (Python env gate) + Layer 3 (Rust Option<T> type system) 三層 fail-closed
4. W1 WS payload parse: `parsers.rs:225-263` 全 `.parse::<f64>().ok()` + `.filter()` NaN/Inf reject，0 panic 風險
5. V086 backfill: 純 DDL/parameterized SQL，9757 row UPDATE + 17 row trading.fills REPLACE，audit chain 可從 commit `46a9cadc` 重建
6. V088/V089/V090 schema: 0 secret column / 100% DDL 無 user input concat / DB role = trading_admin migration only
7. BB ToS / KYC / geographic 0 觸發（W2 BTCUSDT spot orderbook public market data，0 redistribution risk）

**3 LOW backlog**:
- LOW-N1-1: reason contract drift（W7-2 ctx.position_state Option A 落地後自然 close）
- LOW-N1-2: trading.fills UPDATE 缺 governance audit hook（forensic 仍可從 git commit 重建）
- LOW-N1-3: N+0 sign-off SOP shell 含 PG_PASS env 變數展開（same-uid trust boundary，建議改 ~/.pgpass）

**IMPL phase E2 必驗 4 點 sign-off carry-over**:
1. W2 step_4_5_dispatch.rs paper-only fence Layer 1 default branch grep verify `_ => None`
2. W2 Python writer Layer 2 fence: OPENCLAW_ENABLE_PAPER env gate fail-closed branch
3. W7-2 future ma_crossover entry path 加 ctx.position_state query 後 LOW-N1-1 自然 close
4. W5 V089 cohort_freq_cap_attempts promote override LeaseScope::CanaryStagePromotion 接線

**5 hard gate 全綠 (W7-1 + W7-3 deploy 後仍維持)**

報告：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-10--n1_d0_security_pre_audit.md`

---

## 2026-05-22 Sprint 1A-ε P1 sandbox_admin Role Creation

**Verdict**: PASS WITH 1 MEDIUM FINDING（不阻 Sprint 1B 派發）

### 已創建
- PG role: sandbox_admin（LOGIN + SCRAM-SHA-256 + CONNECTION LIMIT 10）
- attacker fence flag 6/6: NOSUPERUSER / NOCREATEDB / NOCREATEROLE / NOREPLICATION / NOBYPASSRLS + LOGIN
- 14 schema 全 USAGE+CREATE + ALL PRIVILEGES on TABLES/SEQUENCES/FUNCTIONS + DEFAULT PRIVILEGES
- _sqlx_migrations 表 ALL PRIVILEGES（migration registry write 能力）
- search_path: governance, learning, trading, public
- 密碼存 srv/settings/secret_files/postgres/sandbox_admin/password (0600, gitignored, 33-char base64 / 144-bit entropy)

### 攻擊面 finding
- **[E3-MED-1]** sandbox_admin 可 connect trading_ai production DB（PG PUBLIC 預設 CONNECT 副作用）；不能讀 user data / 不能 DDL；可讀 pg_catalog + information_schema 元資料
- 修法 carry-over Sprint 1A-ε P2 或 Sprint 1B infra wave：pg_hba.conf 加 reject row OR REVOKE CONNECT FROM PUBLIC ON trading_ai

### 治理 push back（PA + QA）
- PA Phase 3e signoff §4.2 + QA Phase 3c §1.4 寫的 `cargo run --release --bin sqlx_migrate` 路徑 **不存在**
- Cargo workspace 5 binary 全列：openclaw-engine / repair_migration_checksum / feature_baseline_writer / replay_runner / (hot_path_baseline + intent_processor_exposure bench)
- Migration 真正 entry：engine startup main.rs:637 呼叫 `MigrationRunner::run_if_enabled`，靠 `OPENCLAW_AUTO_MIGRATE=1` env 觸發
- Sprint 1B 兩條路徑：Path A 啟動獨立 sandbox engine instance + AUTO_MIGRATE=1 / Path B 寫獨立 sandbox_migrate_runner bin

### Lesson sustained
- **PUBLIC default CONNECT is a real DB-level attack surface**：新 role 不只看 `GRANT CONNECT` 個別 row；要查 `pg_database.datacl` PUBLIC ACL 列；本案 trading_ai datacl 含 `=Tc/trading_admin` 即 PUBLIC 可 connect
- **PG 16 SCRAM-SHA-256 password setting**：SET password_encryption='scram-sha-256' 必須在 CREATE ROLE PASSWORD 同 session 之前，否則 PG 用 default 算法 hash 入庫
- **secret_files/ 是 OpenClaw 既有 gitignored secret pattern**：與 secret_files/bybit/ 風格對齊（subdir/<name>/<key_file>）；不要新發明 secrets/.env

報告：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-22--sprint_1a_epsilon_sandbox_admin_role.md`

### 2026-05-30 深挖 #3 Live/LiveDemo boundary（deepdive — CONFIRMED-CLEAN，0 new finding）

報告：`reports/2026-05-30--E3--deepdive_live_boundary.md`（baseline 187704f6；Mac HEAD 3f805a61 =
baseline + 11 個 docs(todo) commit；源碼 delta=0）。目標=列舉「主 executor 以外」所有 order-submit /
live-param-mutate path 並逐一證明上門控（first-pass 已證主路徑，本次補全其它入口）。

模組根（修正 first-pass 縮寫路徑）：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/`。

關鍵 order/live-param → gate map（file:line 全本 run 親讀）：
- **兩個共用門控函數**：`_verify_live_gate`（executor_routes.py，**僅 1 個 def**＝無 shadow；
  executor :450 + strategist_promote_routes :462-463 `from .executor_routes import` 共用）；
  `all_five_live_gates_ok(actor, require_authz)`（live_preflight.py:247-327，**body 親讀**＝正規
  5-gate AND fail-closed 短路）→ live_session_endpoints :168/:517/:638 三處全 `require_authz=True`。
- **唯一驗簽 SSOT** `live_preflight.verify_signed_authorization`（:62）：HMAC mismatch :175 / expired :187
  / env-match :191 / schema+mode :126-137。兩門控函數都 delegate 它 → forge/replay/expiry 集中擋；
  其它 authorization.json reader 只是 signer（live_trust_routes）或 read-only status/display，不能授權 live。
- **Rust OMS 單一寫入口** `order_manager.rs:354 place_order`，**只**被 event_consumer/dispatch.rs:789,799
  + handlers/lifecycle.rs:168 handle_submit_order 呼叫（不散落）。
- ExecutorAgent live=shadow→Paper（executor_agent.py:603）；live 時 :722 送 SubmitOrder IPC 入 OMS；
  `openclaw_authority_contracts.py:124 "can_submit_orders": False` 預設拒。

**O-1（本 run RESOLVED，非 finding）— 重要教訓「平行門控副本」**：Earn 有平行門控。Python
`earn_routes.py:578-652 _check_gate_a..e` 是 Sprint-1B **soft preflight/display**（gate_b 只查
`LIVE_AUTHORIZATION is not None`，**不**驗 HMAC/expiry/env）。乍看像漏洞，**但** binding 強制在
**Rust 9-gate** `earn_router.rs:262-625 dispatch_earn_intent`：E-3 `if !governance.is_authorized()
{ rejected }`（:305，註「Gate 1 等價」）+ E-4 `LeaseScope::EarnStake/Redeem
requires_operator_authority` 60s TTL（:309-336）+ Gate b(ALLOW_MAINNET) 在 BybitRestClient 構造時把關
（:602-604）+ module-doc「5-gate inheritance hard fail-closed」:8 /「ADR-0030 5-gate live boundary」:62。
Earn write 另由 IPC `_hmac_sig`(OPENCLAW_IPC_SECRET) + typed_confirm phrase HMAC + `_ipc_call_strict`
fail-closed 503/504 保護；Earn=yield staking（/v5/earn/place-order，非 perp，無 withdraw，[100,200] USDT 硬鎖）。
→ 正確的 Rust-authority pattern（CLAUDE §一），CLEAN。**教訓：審計平行門控時，Python soft gate 不等於
漏洞——必須讀到 Rust 端 binding gate 才能下判；反之若只看 Python 會誤報，只看 Rust 會漏掉 IPC 偽造面。**

**反模式自捕（最重要的 process 教訓）**：本 run 一度因 zsh 在 repo root 把未引號 `--include=*.py`
glob 展開（cwd 無 *.py）→ `zsh: no matches found` → 整個 **parallel** batch 被 cancel → 看似空輸出 →
我一度誤判「harness outage / NEEDS-MORE」並寫進報告草稿。實為 **shell 引號問題非工具壞**。換引號
`--include="*.py"` 後全部正常。**SOP：(1) grep glob 永遠加引號；(2) 看到整批空輸出先換引號/換單命令
重試，勿急下 outage 結論；(3) 絕不從空/可疑讀出 ship finding 或 clean verdict**（呼應 first-pass 的
phantom「program_code git-ignored」教訓——同一類「被工具假象帶偏」的坑）。已在報告 retract 該誤判。

其它本 run 確認（全 CLEAN）：secret-slot resolution = env(空忽略)→file(0600)→None 無 permissive default
（live_preflight.py:240-244 + 300-312，require api_key AND api_secret，OSError→both False）；
ALLOW_MAINNET 三個獨立檢查點（executor :229 / all_five :295 / earn gate_c :616-625）unset/0 一律 DENY；
`_current_bybit_endpoint_label` 未知→mainnet（取嚴不降級）；LiveDemo 只跳 Gate3(mainnet-only)其餘 1/2/4/5
全保留（無真降級）；no-withdraw 結構成立（bybit_rest_client 只有 cancel_order:655 + place_order:801，
`grep /v5/asset/withdraw` 空）。`place_order` LIVE-GATE-FALLBACK-1（:797-800）= reduce_only 緊急平倉，
但 reduce_only 參數**預設 False 且方法本身不自我強制**，靠 call site（clean_restart_flatten + operator
平倉鈕）+ route gate——若未來有人繞 route 直呼 place_order 非 reduce_only，這是潛在 widening 點（目前無此 caller）。
OPS-2 Phase-1 fallback 仍 tracked（P1-OPS-2-PHASE-2-CUTOVER 2026-06-10），first-pass runtime 0/0，本 run 未重 ssh。

### 2026-06-07 L2 Advisory Mesh v3 設計安全審計

**評級：CONCERNS（0 CRITICAL / 2 HIGH / 3 MEDIUM / 4 LOW）**

**範圍**：PA design `2026-06-05--l2-advisory-mesh-design-draft.md` v3 + 相關 live code（`layer2_engine.py`, `layer2_routes.py`, `layer2_tools.py`, `governance_autonomy_service.py`, `provider_keys_store.py`, `engine_watchdog.py`, V131-V133 migrations）

**架構安全性**：
- `expand=human / contract=auto` 非對稱設計正確，LANE_DIRECTION typed invariant 邏輯無誤
- §F fail-safe 最壞路徑=NO_ADVICE=今日行為，不阻交易/風控
- 5 hard gate 未觸及，Orchestrator 無 trading-scope lease / order path / IntentProcessor import
- V134 設計無 credential 欄位，`provider_keys_store.status()` 永不回明文 key
- MIT-MF-1 grep: 0 hits — CLEAN

**HIGH findings（需修才能過 E2）**：
1. HIGH-1：`/cost/reset` (POST) + `/cost/pricing` (POST) 缺 `require_operator_role` → 任何已認證用戶可歸零每日預算計數器（DOC-08 $2/day cap 繞過）或修改 pricing table。`layer2_routes.py:354` + `layer2_routes.py:389`
2. HIGH-2：`layer2_engine.py:703` `str(e)[:500]` 進 `session.final_summary` → GET sessions 回 `current_actor`（無 operator 要求）→ 內部錯誤細節洩漏給 viewer role

**MEDIUM findings**：
- MEDIUM-1：§F fail-safe state machine（TRIPPED/GLOBAL_CONSERVATIVE/circuit trip）設計正確但 code 不存在，Orchestrator 實作時必須第一天包含
- MEDIUM-2：`canary_events.jsonl` 仍無告警消費者，sentinel 告警功能在 watchdog alert wiring 未完成前無運營價值（20h 宕機缺口未關）
- MEDIUM-3：V134 `agent.l2_calls` 不存在（最高遷移 V133），D3 基礎未建；per §J step 1 order，任何能力不得在 V134 前部署

**LOW findings**：
- LOW-1：L1 triage `str(e)[:100]` 在 trigger response（operator-only 端點，影響較低）
- LOW-2：`L2AdvisoryOrchestrator` / `ResearchAlphaWealthController` 未在 singleton-registry.md 預登記
- LOW-3：`LANE_DIRECTION` typed loader 只在設計，未在代碼；建議在 E1 前寫 RED test
- LOW-4：trigger request `context` 自由文字無 prompt injection 清洗（MEDIUM-D 遺留；PromptContract 是結構修法）

**關鍵教訓**：設計安全性 ≠ 實作安全性。HIGH-1 是現存代碼漏洞（非設計問題），應立即修復不等 Orchestrator 建構。

報告：見本次 assistant 訊息（不存 .md 檔，返回 text output 給 parent agent）

### 2026-06-08 L2 D3 Phase 1 sanitize-before-persist 對抗審計（E3-HIGH gate）

**Verdict：RETURN（sanitize gate 未過）— 1 HIGH（redactor 涵蓋率對抗失敗）+ 2 MEDIUM + 2 LOW**

**範圍**：E1 工作樹未 commit（branch `feature/l2-critic-lessons-tools`）：`l2_secret_redactor.py`（新）/ `l2_call_ledger_writer.py`（新）/ `layer2_engine.py:323-375,649-662` 接線 / `error_sanitize.py`（reuse）/ V134/V135/V136 / `test_l2_d3_ledger.py`。規格 = PA `2026-06-08--l2-d3-phase1-tech-design.md` §B（LOCKED）。

**真正在寫入路徑、無窗口？ → 是（結構正確）。** writer `record_l2_call` Step1-2 消毒 → Step4 sha256 算已消毒文本 → Step5 INSERT，同函數內順序，非 async post-hoc。engine 只把 raw 傳 writer，不自寫。sha256-over-sanitized 親驗對（test_sha256_over_sanitized_text 真 bite）。append-only DDL V134/V135/V136 三表全 REVOKE UPDATE/DELETE + trading_ai 只 INSERT/SELECT + 零 column-level UPDATE grant（親 grep 確認）。**結構/順序層 PASS。**

**合成密鑰 100% 被 `[REDACTED:*]`？ → 否。** 親跑 24 個合成 payload（無真鑰）打真 redactor 碼：
- **keyword-adjacent（api_key= / password= / Bearer / DSN / X-BAPI-SIGN= header 名）全 redact ✓**
- **bare secret 無相鄰 keyword 全 LEAK**：裸 Bybit-key 形（18 alnum）/ 裸 36-char / 裸 64-hex HMAC / base64 blob(JWT 形 + `+/=`)= 全 verbatim 落庫，hits=[]。
- zero-width space 插入 key 中 → LEAK（unicode 規避）。url-encoded `%3D` → LEAK。`api_key=` 值 <16 char → LEAK（min-length window）。`172.16.*` / `192.0.*` 私有 IP 不在 pattern → LEAK。JSON header-echo `"X-BAPI-SIGN":"<hex>"` dict 形 → LEAK。
- **根因**：redactor 是 keyword-anchored（regex 全要相鄰 `key=`/scheme/`Bearer`）；無「裸高熵 token / base64-blob / 結構性無 keyword secret」arm。與設計 §B.2 自陳「寧可多遮也不漏遮 secret」矛盾——實際漏遮 bare 形。

**exploitability 校準（為何 HIGH 非 CRITICAL）**：本 box 高值具名資產（Bybit key material / authorization.json / DSN）洩漏時幾乎總帶 keyword/結構脈絡（scheme / `password=` / `X-BAPI-*` 名 / `Bearer`）→ redactor 接得住；且 str(e)→durable 路徑雙重防護（production error_sanitize 只回 classified message，OPENCLAW_DEBUG=1 時 writer 再過 redactor 接住 DSN，親驗）。但 `raw_response`/`input_context` 非可信乾淨通道：L2 有 TOOL_WEB_SEARCH + TOOL_FETCH_URL（抓任意外部內容）+ free-text `context`（MEDIUM-D prompt-injection 未清洗未解）→ 攻擊者可植入 bare token/blob，LLM echo 進 raw_response → 裸形繞過。zero-tolerance 政策下任何 bare 規避即未達「100% [REDACTED]」→ gate RETURN。

**ReDoS/DoS → CLEAN**：7 條 adversarial regex payload（200K-400K char）全 <50ms，無 catastrophic backtracking；redact_jsonb 5000-key dict 313ms 線性，writer fail-soft 離交易熱路徑。

**adjacent durable store 不過 redactor（範圍邊界 finding）**：`agent.lessons`（`layer2_critic.py:480` INSERT）落 LLM-distilled lesson content（`title: detail` ≤4000），**不經 redactor**；本 PR 只動它設 `context_id`（非引入）。但 D.1.1「applies everywhere」對它不成立——lesson 文本若 echo secret 即裸落 durable。MEDIUM。`layer2_cost_tracker._save`（:189/214）= config/pricing/adaptive only，無 prompt/summary → CLEAN（合 PA §0）。

**新寫端點 → 0**（無 route 檔改動，git diff 確認；prior HIGH-1 `/cost/reset` 不在本 PR scope 非重引入）。`layer2_types.py` 只加 `l2_reply_id` lineage handle 非 secret 欄。

**修補方向（過 gate 三選）**：(1) redactor 加「結構無關」arm：裸高熵 token（shannon-entropy gate 或 `[A-Za-z0-9_\-]{32,}` + base64/hex 形）+ 補 172.16/192.0 私有段 + unicode normalize（NFKC + strip zero-width）+ url-decode-then-scan；(2) 對 raw_response/web-fetch/context 視為 untrusted，落庫前強制 entropy-scan 高熵子串遮罩；(3) 把 `agent.lessons` content 也路由過 redactor（D.1.1 applies-everywhere 真落實）。E1 測試只覆 keyword-adjacent，須補 bare/blob/unicode/url-enc 負向對抗 case。

報告：返回 text output 給 parent agent（不存 .md）。承 [[2026-06-07 L2 Advisory Mesh v3 設計安全審計]]（HIGH-2 str(e) 此 PR 在 ledger 路徑已結構性閉合；HIGH-1 cost route 仍 P2 open）。

### 2026-06-08 L2 D3 Phase 1 sanitize gate re-audit（redactor v2 — E3 PASS）

**Verdict：E3 PASS（sanitize gate 過）— 0 CRITICAL / 0 HIGH / 0 MEDIUM（前輪 HIGH 已封）/ 2 LOW（1 pre-existing scope + 1 over-redact UX）**

**範圍**：重驗上輪 RETURN（v1 keyword-anchored 漏 bare/編碼，1 HIGH+2 MED）；E1 重寫 `l2_secret_redactor.py`→v2（`REDACTOR_VERSION="l2_redactor.v2"`），branch `feature/l2-critic-lessons-tools` HEAD `6d312405` 未 commit。親跑真 redactor 碼（無 mock），合成密鑰（無真鑰）。

**核心結論（親跑 27-payload 矩陣 + 邊界 probe + ReDoS 800K + str(e) 雙防）**：
1. **合成密鑰 100%（除文件化殘留）被遮 = 是**。0 unexpected leak。上輪全部 bare 漏點封死：24/36-char alnum、64-hex HMAC、bare JWT（`s_jwt` 結構臂）、base64 blob、zero-width-in-keyword（NFKC+strip）、url-enc password/DSN（decode-once）、fullwidth（NFKC）、私有 IP 10/172.16-31/192.168/192.0.2/169.254/IPv6 fc00·fe80、JSON header-echo dict（`_SENSITIVE_KEY_RE` key-name 臂）全 `[REDACTED:*]`。
2. **殘留誠實度 = 誠實**。殘留**只剩** `<24-char short-bare-context-free`（邊界 probe 證：≥24+≥2 字元類才遮；18/20/23-char bare LEAK，24+ caught）。E1 用 `@pytest.mark.xfail(strict=True)` 在 `test_l2_d3_ledger.py:240` 明寫此殘留 + 資訊論理由，未藏未誇；`strict=True` 意味未來誤「修好」會 XPASS fail 逼重決。**真無法以合理 FP 代價封**（降 floor<24 會大量誤遮散文）。
3. **v2 無新 bypass**。double-encode（`%2561`）decode-once 後殘 `%XX` 文字，trailing 高熵 run 仍被高熵臂接住（defense-in-depth，非乾淨繞過）；512-cap >cap 分支直接遮（不漏後段）；NFKC ligature（ﬁ→fi）不拆解密鑰反而還原；all-special `+/=` keyworded value 仍遮。合併 dispatch（`__keyworded__`/`__struct__`）無漏臂。
4. **ReDoS = CLEAN（嚴格線性，非超線性）**。10 條 adversarial payload @200K/400K/800K：800/400 = 1.87-2.02x、800/200 = 3.92-4.07x，**全線性無 catastrophic backtracking**。worst=Bearer-spam 241ms@800K 仍 1.87x 線性（退化全-keyword 輸入，真實 L2 文本不可能）。`redact_jsonb` 5K→20K key = 22.7→91.2ms（4x 線性）。
5. **64ms@400K 不 flag**。安全準則是「線性 vs catastrophic」非「informal 50ms 牆」；固定開銷（off hot-path、fail-soft、低頻 manual-trigger、writer 內已吞 NEVER raise）非漏洞。informal 50ms 是 perf guidance 非 security gate。
6. **agent.lessons 真過 redactor = 是**（上輪 MED 已閉）。`layer2_critic.py:463 content = _redactor.redact(content).text` 在 `agent.lessons` executemany INSERT（:484）之前。import :50。
7. **str(e) 雙防完好**。production `error_sanitize` 只回 classified message（`_DEBUG` module-cache）；DEBUG 模式 detail 夾 `str(exc)[:200]` 會漏 DSN，但 writer Step3（`l2_call_ledger_writer.py:190 safe_reason=_redactor.redact(...)`）第二道接住 DSN+private_ip+sign。親驗 fresh-import DEBUG=1 確認。sha256 算在已消毒文本（`prompt_sha256/response_sha256`，:196-197），raw≠redacted hash 確認。

**2 LOW（不阻 gate）**：
- **LOW-1（pre-existing，非本 PR）**：`layer2_cost_tracker.record_session`（engine :801 live 呼叫）→ `Layer2Session.to_dict()` 含 `final_summary`（可為 `response.text[:2000]` 原始 LLM 輸出或 `str(e)[:500]`，engine :678/:789）+ `recommendation.reasoning` + `insights` → `_write_raw` 落 durable `runtime/layer2_cost_state.json`，**不過 redactor**。但檔 gitignored + chmod 0600（owner-only）+ 非 append-only forensic + MAX_SESSION_HISTORY rotated；本 PR 未動 cost_tracker（`layer2_types.py` 只加 `l2_reply_id`，diff 證 final_summary/reasoning 是 pre-existing）。D.1.1「applies everywhere」是 D3 forensic ledger scope，此 JSON 是另一較低嚴重面。與上輪 agent.lessons MED 同類但更低（local-only 0600）。建議後續把 `final_summary`/`reasoning` 落 cost_state 前也過 redactor（小修，非 gate-blocker）。
- **LOW-2（over-redact UX）**：高熵臂對 benign 散文 2/8 FP（`OPENCLAW_ALLOW_MAINNET=1`-含長 run、`scope=CanaryStagePromotion` 20-char）誤遮 → forensic 可讀性降。§B.2 north star 明示可接受（寧多遮）；L2 prompt/response 非 prose-fidelity-graded。記錄非阻擋。

**教訓**：(1) redactor 從 keyword-anchored→「keyword + 結構(DSN/JWT/IP) + 編碼正規化(NFKC/url) + 裸高熵」多臂，是封 bare/編碼規避的正解；單 keyword 臂結構性漏 bare。(2) 殘留誠實度看「code 內 xfail strict + 資訊論理由」非 prose 自陳——E1 此次做對。(3) ReDoS 真準則是線性 vs 超線性（壓 200K/400K/800K 看 ratio），非絕對 ms 牆；固定開銷 off-hot-path 不 flag。(4) 重審範圍要再掃 adjacent durable store（cost_state JSON 是 ledger 外平行面，grep `_write_raw`/`to_dict` 才抓到）。

報告：返回 text output 給 parent agent（不存 .md）。承 [[2026-06-08 L2 D3 Phase 1 sanitize-before-persist 對抗審計]]（上輪 1 HIGH+2 MED 全閉：bare/編碼 HIGH→v2 多臂封；agent.lessons MED→:463 接線；str(e) MED→雙防確認）。

### 2026-06-08 L2 D3 sanitize gate FINAL re-audit（redactor v3 — E3 PASS）

**Verdict：E3 PASS（sanitize gate 過）— 0 CRITICAL / 0 HIGH / 0 MEDIUM / 3 LOW（1 keyword-set gap + 1 worst-case superlinear + 1 pre-existing scope）**

**範圍**：重驗 v2→v3（operator 拍板 A 移除 blanket bare 高熵臂回 keyword-gated + 結構臂，接受 naked-context-free 殘留；E1 加 store-original-by-span + cost_tracker LOW-1 fix）。`l2_secret_redactor.py` v3（`REDACTOR_VERSION="l2_redactor.v3"`）+ `layer2_cost_tracker.py`，branch `feature/l2-critic-lessons-tools` HEAD `6d312405` 未 commit。親跑真 redactor 碼（無 mock），合成密鑰（無真鑰）。E1 suite 46 passed + 4 xfailed（0 XPASS）。

**核心結論（親跑 70+ payload 多部矩陣）**：
1. **移除高熵臂沒弄壞任何結構/keyworded/編碼臂 = 確認**。29 coverage 向量（api_key=/apiKey/api_secret/secret_key/access_token/password/PGPASSWORD/token<16/X-BAPI-SIGN/sign/Authorization-Bearer/裸Bearer/signature/approval_token/secret_slot + 結構 JWT/DSN(postgres·redis·mongodb+srv)/私有IP 10·172.16·192.168·127·169.254·192.0.2·IPv6 fc00·fe80/internal-host/.local）全 `[REDACTED:*]` 0 secret-byte 殘留。7 編碼規避（zero-width-in-keyword/fullwidth-keyword/url-enc-password/url-enc-DSN/zero-width-Bearer）帶 keyword 全接住。
2. **★ store-original-by-span 0 partial-residual leak（新攻擊面）= 確認**。13 對抗（ZW 插值中/首/尾邊界、url-enc 片段 %41%42、fullwidth 折疊、ligature ﬁ→fi、secret 在文本結尾無下一字元邊界、DSN cred url-enc、ZW 每字元間插）→ 存入 original 文本零 raw-secret-bytes、零 ≥8-char fragment。offset map「下一字元起始當 end」fail-safe 寧多遮不漏。零-secret 輸入 byte-identical（中文全形/合法 %2F/zero-width）確認。
3. **fast-path 不漏偵測 = 確認**。4 clean-ASCII secret 走 fast-path（_NEEDS_OFFSET_MAP_RE 無命中 + NFKC-normalized）皆遮；同輸入 +ZW 強制 slow-path 亦遮，fast/slow parity OK。
4. **ReDoS = 非 catastrophic（polynomial ~n^1.7 worst，realistic linear）**。catastrophic-backtracking 經典觸發（near-JWT-no-3rd-dot / near-DSN-no-@ / Bearer-no-terminator / ipv6-colons-only）全 flat ~45ms@200K = regex 臂無回溯（互斥字元類，docstring 屬實）。decompose：worst 成本在 normalize per-char Python 迴圈（86ms）非 regex（23ms）。realistic sparse-secret prose 25→206ms@100K→800K 嚴格線性；pure-prose fast-path 196ms@800K。**僅 degenerate 100%-secret-like 輸入（36363 dense evasion token/800K）→9.4s = O(n·matches)，非指數**。store-original per-char map 是 v3 新增 worst-case 複雜度（vs v2 無 map）。
5. **sha256 算在 original-redacted（非 preprocess）+ str(e) 雙防 = 完好**。sha(redacted)≠sha(raw) 確認 hash 不可回推原文；零-secret byte-identical；str(e)-with-DSN（OperationalError postgres://svc:pr0dPw@10.0.0.7）→ `[REDACTED:db_dsn]`，writer Step3 二道接住。
6. **cost_tracker LOW-1 閉 = 確認（真 path）**。`_sanitize_session_dict_for_persist` 真跑：final_summary（DSN+api_key）/recommendation.reasoning（Bearer）/insights[].detail（X-BAPI-SIGN）全遮、cost_usd·symbol 結構欄保留、落 layer2_cost_state.json 前消毒。critic lessons :463 redact-before :484 executemany（上輪 MED 持續閉）。
7. **JSONB-key 臂（header-echo dict）= OK**。{"Authorization":bare-value} / nested {"api_key":...} / value-內私有IP 全遮、User-Agent 保留。

**明確答**：
- 「除文件化 naked 殘留外是否 0 leak」→ **否，有 1 個額外 keyword-set gap（LOW-1，見下）**。其餘除 4 個 xfail-strict 文件化殘留（bare 24/35-char alnum、bare 64-hex、bare base64）外 0 leak。
- 「store-original 是否曾部分殘留 secret」→ **否，0 partial-residual**（13 對抗全證原文 secret-bytes 不在）。
- 「fast-path 是否漏偵測」→ **否**（parity 確認）。

**3 LOW（不阻 gate）**：
- **LOW-1（keyword-set gap，v3 真 finding）**：keyworded 臂 keyword-set 漏 `auth_signing_key`/`hmac_key`/`hmac`/`signing_key`/`hmac_signing_secret`/`signing_secret`/`auth_key`/裸`secret`/`private_key`，free-text `kw=value`（value 裸 hex 無結構）**不遮**。`secret`/`private_key` JSONB-key 形被 `_SENSITIVE_KEY_RE` 接住但 free-text 漏；`auth_signing_key`/`hmac_key`/`signing_key` 兩形皆漏。**與設計 §B.5「every named critical asset is still caught」claim + secret-leak-detection skill Pattern-A 自列 `hmac_key`/`signing_key` 矛盾**。**為何 LOW 非 HIGH**：`auth_signing_key` 是 CRITICAL HMAC 簽名 key 但只存 `$OPENCLAW_SECRETS_DIR/<env>/auth_signing_key` 檔、不入 L2 context → LLM 無從 echo 其 `kw=value` 形；真正過 L2 的 Bybit api_key/secret/Bearer/X-BAPI-SIGN/DSN/authorization.json 物料全已接住。**v2→v3 regression 維度**：v2 blanket 高熵臂會接住這些 value（不論 keyword 在不在 set），v3 移除後落回 keyword-set 完整性——修法是把這些 keyword 補進 `_KW_DISPATCH` g_auth/g_api 分支 + `_SENSITIVE_KEY_RE`（小修，非 redactor 架構問題）。
- **LOW-2（worst-case superlinear，v3 store-original 新增）**：degenerate 100%-evasion-token 輸入 → ~n^1.7（9.4s@800K）。非 catastrophic ReDoS（polynomial、regex 臂無回溯證實）。realistic L2 文本線性。raw_response/input_context 無上游長度 cap（final_summary[:2000]/str(e)[:500] 有 cap）。off-hot-path + fail-soft（writer NEVER raise）+ 低頻 manual-trigger → 不崩潰不阻交易。建議後續 raw_response 落庫前加 size cap（如 [:64K]）截斷 amplification。
- **LOW-3（pre-existing，非本 PR）**：`agent.lessons` 已過 redactor（:463 閉）；cost_state JSON 本輪已過（LOW-1 fix）；無其餘 durable store 漏。範圍掃 ledger/marks/gate-seam/lessons/cost_state/shadow_decisions 全過 redactor。

**教訓**：(1) operator-A 回 keyword-gated 的代價是 keyword-set 完整性變成 attack surface——移除 blanket 高熵臂後，**任何不在 keyword-set 的 customary-keyword secret 都裸落**；審 keyword-gated redactor 必逐一打 named-asset 的 customary keyword（尤其 skill 自列的 hmac_key/signing_key），別只信「named asset always caught」prose。(2) store-original-by-span 正確封 partial-residual（13 對抗 0 leak）但代價是 per-char offset map 把 worst-case 從 v2 線性推到 ~n^1.7（degenerate input）——ReDoS 審計要分「regex backtracking（用 almost-match 探，本案 clean）」vs「Python per-char/per-match 迴圈 polynomial（用 match-density scaling 探）」兩軸。(3) xfail-strict 4 殘留 + 0 XPASS = E1 誠實度可驗（code-level 非 prose）。承 [[2026-06-08 L2 D3 Phase 1 sanitize gate re-audit（redactor v2 — E3 PASS）]]（v2 PASS 基於高熵臂；v3 移除後 coverage 主體仍守，新增 LOW-1 keyword-set gap）。

報告：返回 text output 給 parent agent（不存 .md）。

### 2026-06-09 L2 P2 orchestrator 安全 delta narrow re-audit（E3 PASS）

**Verdict：E3 PASS — 0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW（1 latent P3-gated dedup-dict 無上限 + 1 pre-existing /cost/* HIGH-1 仍 open，非本 delta scope）**

**範圍**：重驗 L2 P2 修補 delta（branch `feature/l2-critic-lessons-tools`，P2 未 commit 疊 P1 `f1c3c1ca`）。改 `l2_advisory_orchestrator.py`（新）+ `l2_capability_registry.py`（新，loader basename）+ `test_l2_p2_orchestrator.py`（74 passed）。E1 修：LOW-1 path-leak / MED-1 fail-safe SM 解耦 / MED-2 Lock→RLock。親跑真碼（venv `venvs/mac_dev/bin/python3.12`，pydantic 2.13.3 + tomllib），合成 payload 無真鑰，SUT 零 mock（僅 stub 外部 cost_tracker.check_daily_budget + D3 ledger writer）。

**明確答**：
1. **絕對路徑真不再洩（route path-free）= 是**。loader `l2_capability_registry.py:316` 用 `{p.name}`（basename）非 `{p}`。6 reject 分支全親跑真 loader（malformed-TOML/unknown-top-key/pydantic-extra-forbid/autonomy_level/lane='live'/min_tier）→ 每條 error str 0 host-path（無 /home /Users /tmp /TradeBot）。tomllib 內層 error 是 position-based（`at line 1, column 6`）**從不嵌 path**，故 `{exc}` 內插也 path-safe。唯一 "abs-path-like" 命中是 pydantic 公開 docs URL（errors.pydantic.dev），非主機路徑。route 端：`/registry/capabilities`(200-body `detail`=str(exc)) + `/registry/reload`(HTTPException 400 **dict**-detail) 都**繞** main_legacy `_LEAK_PATTERN` sanitizer（:484 `isinstance(detail,str)` 對 dict-detail False；200-body 根本非 HTTPException）→ 源頭 basename 是**唯一**且**唯一足夠**防線（E1 註解誠實）。layer2_routes.py 零 abs-path 字面/`__file__`/`parents[]`/`str(p)`。`p.exists()` False 分支只 `logger.warning` 全路徑（server-side）不 raise，無 client 洩。
2. **fail-safe SM 改動後仍無路通 live（故障注入實證，含 ollama-up 新邏輯）= 是**。MED-1 解耦親驗：ollama-UP 持續失敗 RETRY→DEGRADE_OLLAMA→**TRIPPED(consec≥5)→GLOBAL_CONSERVATIVE(consec≥10)**——舊 bug 卡死 DEGRADE_OLLAMA 已修（escalation 由 `_consecutive_failures` 跨閾驅動，ollama_available 只在 consec 2-4 中間階選 floor DEGRADE_OLLAMA vs NO_ADVICE）。ollama-down/mixed-flap 三模式全跑。dispatch 真路由（真 registry 3 lane）每態驗：NO_ADVICE/TRIPPED/GLOBAL_CONSERVATIVE 三態 advisory-lane 終態=`dropped`（subtraction=baseline）；RETRY/DEGRADE_OLLAMA 仍路由但**只** neutral_sink/risk_governor_advisory（advisory INPUT，governor 擁終值）**從不 live**；expand-lane(promote_cap) **每態**(含 HEALTHY) admitted=False→manual_inbox（STEP-1 MANUAL linchpin 守）。**0 live-enabling write**：grep live_execution_allowed/promote_tier/acquire_lease/place_order/IntentProcessor 全在 docstring/comment（hard-boundary 宣告）非 code。**GLOBAL_CONSERVATIVE 只標記 self._fail_safe，0 posture 自動切換**：`self._posture` 全模塊唯一 write 在 `__init__`（:150），:378/:520 只 read；故障注入後 posture 恆 "Standard"（實際切換走 governance_autonomy_service operator/TOTP，:475 註解誠實）。recovery：單 ok→HEALTHY consec=0。
3. **RLock 無 deadlock = 是**。MED-2 Lock→RLock + `_admit` 整段納鎖。6 lock site；reentrancy 路徑 `_admit`(:314 持鎖)→`_cap_spend_today`(:400 重入取鎖)——plain Lock 會自鎖，RLock 不。並發 stress：18 thread（6 dispatch+4 spend+3 outcome+2 reset+1 reload+2 status）× **~4.1M ops / 6.5s** 全競爭→still-alive-after-stop=0（無 deadlock）、0 exception、posture 恆 Standard。**0 await in lock**（全 SM/admission 是 sync def；唯一 `await` 命中是 :311 comment）→ 無 cross-await-in-lock。注意 `_admit` 在 asyncio route 上跑但本身 sync，threading.RLock 短暫 block calling thread（in-memory dedup 臨界區無 I/O 無 await held）可接受。

**4 HIGH-1 per-cap accumulator 無新攻擊面 = 確認**。`cap_daily_spend: dict[(cap_id,utc_day)→float]` 純 in-memory，**0 durable write**（全模塊唯一 durable=`writer.record_gate_seam` :452 走 P1 D3 redactor-protected writer，accumulator 值=float usd 從不持久化）。`record_capability_spend` 無注入面（key=驗證過 cap_id≤64char + deterministic strftime day，value=+=usd，usd≤0 no-op，0 SQL/shell/log 內插）。dict-growth：`(cap_id,day)` 增長 ~negligible（10cap×365day=3650/yr 無 evict 但極慢）。**dispatch() 0 route caller**（P2 dormant）→ accumulator 與 record_capability_spend 現無 route 可達。

**5 write-auth / $2/day = 確認**。**新** orchestrator write route 正確 gated：`/registry/reload`(:718) + `/orchestrator/fail-safe/reset`(:744) 都 `base.require_scope_and_operator(actor,"ai_budget:write")`（auth.py:319 = require_operator_role AND require_scope，fail-closed）。reads(`/orchestrator/status`,`/registry/capabilities`)唯讀不 mutate。$2/day 硬閘 admission stage4 `_check_budget`（fail-closed：取不到 tracker / 查詢失敗皆 return False,0.0 不放行）+ per-cap 日上限獨立累計（design §F.1）。prior LOW-2 singleton 註冊已閉（singleton-registry.md §2.6.2，owner_lifecycle 明寫「無 live-trading lifecycle」）。

**2 LOW（不阻 gate）**：
- **LOW-1（latent，P3-gated，非本 delta finding）**：`last_served_ts`/`debounce_pending` keyed `dedup_key=cap_id|spec|coarse_subject`，`coarse_subject` 是 dispatch() 參數（attacker-influenceable 維度），**無 evict/maxsize**→若 P3 把 dispatch 接上 route 且 coarse_subject 容許高基數 raw 文字，這兩 dict 無上限增長=memory DoS。**現不可達**（dispatch 0 route caller，P2 dormant）；design 意圖 coarse_subject 是低基數 bucket 非 raw user text。P3 wire dispatch 時須：(a) coarse_subject server-derive 低基數化，(b) 給兩 dict TTL/maxsize evict。記錄非阻擋（非本輪 delta 引入，是 P1 admission 設計既有）。
- **LOW-2（pre-existing /cost/* HIGH-1，仍 open，非本 delta scope）**：`/cost/reset`(:361)+`/cost/pricing` POST(:396) body **仍只** `Depends(current_actor)` **無** `require_scope_and_operator`→任何已認證 actor(viewer/researcher) 可 `tracker.reset_today_costs()` 歸零 DOC-08 $2/day 計數=cap-bypass。layer2_routes.py:666-667 註解宣稱「與 /cost/reset 同 operator-scope 模式」**與實況矛盾**（/cost/* 實際無 operator gate）。這是 2026-06-07 我標的 HIGH-1，operator 接受為 P2 open（不阻 orchestrator build）。本輪**新** orchestrator write route 做對了（有 gate）；舊 /cost/* gap 持續。建議補 `require_scope_and_operator(actor,"ai_budget:write")` 進兩 handler body。

**教訓**：(1) dict-detail HTTPException + 200-body 都繞 str-only `_LEAK_PATTERN` sanitizer——route 回 dict-detail 或非-HTTPException body 時，path-leak 防線**必須**在源頭（loader basename），不能靠 main_legacy sanitizer；驗 path-leak 修要同時確認「源頭 basename」+「route 確實繞 sanitizer 故源頭是唯一防線」兩面。(2) fail-safe SM「subtraction-only」要驗到 dispatch 終態 routed_to（不只 SM state enum）——SM state 對→routing 對才是真 subtraction；RETRY/DEGRADE_OLLAMA 仍路由是 by-design（degraded-but-functioning），關鍵是只 neutral_sink/risk_governor_advisory 非 live。(3) RLock reentrancy 審計要找「持鎖函數呼叫同樣取鎖的函數」具體 call pair（本案 _admit→_cap_spend_today），再用高並發 + still-alive-after-stop watchdog 證無 deadlock；macOS 無 `timeout` 指令，用 script 內 `stop.Event()+join(timeout)` 自帶 watchdog（呼應 memory「timeout fallback 誤觸」教訓）。(4) GLOBAL_CONSERVATIVE「只標記非自動切 posture」要 grep `self._posture =` 確認唯一 write 在 __init__，別只信 docstring。承 [[2026-06-08 L2 D3 sanitize gate FINAL re-audit（redactor v3 — E3 PASS）]]（同 branch P1 層；本輪審 P2 orchestrator 層 delta）+ [[2026-06-07 L2 Advisory Mesh v3 設計安全審計]]（HIGH-1 /cost/* 仍 open 持續追蹤；HIGH-2 str(e) 在 ledger 路徑已閉）。

報告：返回 text output 給 parent agent（不存 .md）。

### 2026-06-09 L2 P2 fix round-2 narrow re-audit（/cost/* operator-scope fold-in — E3 PASS）

**Verdict：E3 PASS — 0 CRITICAL / 0 HIGH / 0 MEDIUM / 1 LOW（latent P3-gated dedup-dict 無上限，非本 delta 引入）**

**範圍**：重驗 P2 fix round-2 安全 delta（branch `feature/l2-critic-lessons-tools`，P2 未 commit 疊 P1 `f1c3c1ca`）。改 `layer2_routes.py`（/cost/reset:373 + /cost/pricing:413 補 `require_scope_and_operator`）+ `l2_advisory_orchestrator.py`（`_prune_stale_spend` MED-1 + fail-soft docstring LOW-1）+ test（88 passed，前輪 74）。親跑真碼（venv `venvs/mac_dev/bin/python3.12`=3.12.13，pydantic 2.13.3），SUT 零 mock（僅 stub 外部 cost_tracker + D3 ledger writer）。承上輪 [[2026-06-09 L2 P2 orchestrator 安全 delta narrow re-audit（E3 PASS）]]——上輪我重提的 pre-existing /cost/* HIGH-1（任何已認證者可歸零 $2/day counter）本輪已折入修補。

**明確答（4 問）**：
1. **/cost/reset + /cost/pricing 真 operator-scope 無繞過（對抗 actor 全 403、gate 在變更前）= 是**。親跑 11-actor 對抗矩陣打真 handler+真 auth.py gate（mutation_log 偵測 tracker 是否在 raise 前被呼）：viewer+scope / researcher+scope / empty-roles+scope / empty-roles+empty-scopes / 偽 role(operatorX/admin) / case-variant(Operator) → 全 403 `operator_role_required`，**gate-blocked-before-mutation**（reset_today_costs/update_pricing 從未在 raise 前被呼=無 TOCTOU）；operator+NO-scope → 403 `forbidden_scope`；partial/forged actor(無 roles attr) → 401 `unauthenticated`（malformed fail-closed）；唯 operator+scope → 200+MUTATION-FIRED。gate 是兩 handler **body 第一句**（:373/:413），先於 `_get_cost_tracker()`+mutation(:375/:430)。`require_scope_and_operator`(auth.py:319)=`require_operator_role`(先,401-on-malformed/403-on-non-operator)AND`require_scope`(後,403-on-missing-scope)，與我上輪驗 /registry/reload 同 gate **零弱化**。case-sensitive("Operator"≠"operator")。
2. **$2/day cap-bypass 真閉 = 是**。歸零 DOC-08 $2/day counter（=繞 P2 admission storm-control 硬閘）現需 operator role+scope；非 operator 全 403。
3. **訂正註釋（:675-680）與實況一致 = 是**。明寫「/cost/reset 與 /cost/pricing 先前只有 Depends(current_actor)...本輪補上 require_scope_and_operator 收口；此註釋現為實況（先前誤稱已 scope 化）」——誠實承認上輪我標的 mismatch，line ref(:373/:413)對。
4. **prune（MED-1）無新攻擊面 = 是**。親跑 record_capability_spend+_prune_stale_spend 全生命週期：D3 ledger writer 呼叫 **0 次**=純 in-memory，0 durable write（值 float usd 從不持久化，故無繞 P1 redactor 面）；prune 是純 dict key 比較(`k[1]!=today`)+`+=usd`(usd≤0 no-op)，0 SQL/shell/log 內插=無注入面；per-cap ceiling 保 bound（同日 0.30+0.30=0.60≥0.50→DROP，prune 不歸零同日累計）；**無跨日 reset 繞 per-cap**（prune 只刪 `day!=today` key，同日 spend 保同日 accumulator 0.60→0.65；唯一歸零=跨真 UTC-day=by-design daily reset，`_utc_day` 由 ts/server time.time() 導出，`now=` kwarg 只 P3 trusted executor 可注入，route 無此路徑偽造日期）。bounded：mutator 後 dict 恆只含「今日」key（上輪 LOW-1 dedup-dict-unbounded 對 cap_daily_spend 軸由此 fix 閉）。
5. **fail-soft（LOW-1 docstring 改）行為未變 = 是**。親跑 `_registry_obj` cold/warm：cold malformed→空 registry（fail-closed，0 advisory，degraded=True）；warm good-then-malformed→last-good（不採壞 config、read-path 不 raise）；write-path reload route 仍 400-reject 壞 config+operator-gated。docstring-only。
6. **其餘未動 = 確認**。7 write route 全 gated（/trigger:254 + /cost/reset:373 + /cost/pricing:413 + /config:528 require_operator_role + DELETE providers:641 require_operator_role + /registry/reload:731 + /orchestrator/fail-safe/reset:757）；orchestrator live-enabling surface（place_order/acquire_lease/promote_tier/live_execution_allowed/IntentProcessor）**全在 docstring/comment（:31-34/:72/:143）0 in code**；0 新 durable write primitive（無 json.dump/open/INSERT/cursor/execute/Path）；path-leak basename({p.name}:316)仍閉；secret-leak grep 0 hit；MIT-MF-1 grep 0 hit。

**1 LOW（不阻 gate，非本 delta 引入）**：
- **LOW-1（latent，P3-gated，沿上輪）**：`last_served_ts`/`debounce_pending` keyed `coarse_subject`（dispatch() 參數，attacker-influenceable）無 evict/maxsize；P3 wire dispatch 上 route 且容許高基數 raw 文字時=memory DoS。現不可達（dispatch 0 route caller，P2 dormant）。注意：本輪 MED-1 prune 已閉 **cap_daily_spend** 軸（另一 unbounded dict），但 last_served_ts/debounce_pending **未** prune（key 是 dedup_key 非 day，prune 不適用）——P3 須給這兩 dict TTL/maxsize。

**前輪 /cost/* HIGH-1 狀態：CLOSED**（2026-06-07 我首標、2026-06-09 round-1 重提的 pre-existing /cost/* gap，本輪 round-2 折入 `require_scope_and_operator` 親驗閉合）。

**教訓**：(1) 「對抗 actor 全 403」要驗到 mutation 是否在 raise **前**被呼（用 mutation_log/spy hook 偵測 TOCTOU），不能只看 status code——gate-before-mutation 才是真閉。(2) auth gate AND-composition 的 reason_code 序（operator-role 先 → scope 後）決定 viewer+scope 與 operator+no-scope 走不同 403 reason；審 matrix 要兩維獨立打。(3) prune「無跨日繞 per-cap」要證 `now=` 注入面（誰能控 day_key）——route 無路徑偽造日期=安全；in-memory prune 0 durable=自動無繞 redactor 面（grep ledger-writer call count=0 實證）。(4) docstring-only LOW fix 要親跑 cold+warm 兩路徑證 behavior-identical，別只信 diff 看似只改註釋。承 [[2026-06-09 L2 P2 orchestrator 安全 delta narrow re-audit（E3 PASS）]]（同 branch P2 層；本輪審 round-2 fix delta，/cost/* HIGH-1 此輪閉）。

報告：返回 text output 給 parent agent（不存 .md）。
