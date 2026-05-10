# E3 Memory — 工作記憶

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
