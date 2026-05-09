# E3 對抗性安全核實 v2 — 24h 修復後續驗證 · 2026-05-09

審計範圍：v1 verification 留下的 4 NEW-VULN + 4 ⚠️ + 7 ❌ 在 v2 commits 修復狀態
基準：v1 baseline `455d796e` → v2 HEAD `1bd55689` (34 commits, 含 7 security/audit + 27 strategy/risk/learning/docs)
工具：grep / Read / Bash / ssh trade-core (Linux runtime PG/socket/port real verify) / curl 對抗 (4 endpoint unauth POST)
方法：read-only。0 個 secret 寫入本報告。

---

## §1 Executive Summary

| 嚴重性 | v1 (5/9 03:31) | v2 (5/9 16:32) | NEW-VULN |
|---|---|---|---|
| **CRITICAL** | 0 | 0 | 0 |
| **HIGH** | 4 NEW-VULN-1 (launchd) + lease audit blind | ✅ 1 source-fixed (launchd loopback) + ✅ 1 真實 emit (7950 BYPASS rows in 8h) | 0 |
| **MEDIUM** | NEW-VULN-3 cookie secure fail-OPEN | ✅ source-fixed (proxy hint trigger) | 0 |
| **INFO** | NEW-VULN-4 phase4 dead code | ✅ phase4 mounted in main.py:153-154 | 1 (runtime stale) |
| **新 attack surface** | — | 0 new unauth POST | — |

**Verdict**：v1 4 個 NEW-VULN 全 source-fixed；HIGH 級 (launchd + lease emit) 真實 runtime verify 通過；2 個 MEDIUM 級 (cookie secure / lease audit observability) source 落地；INFO 級 (phase4 dead code) source 落地但 **runtime 仍未 reload**。0 新 attack surface 引入。

**OWASP coverage**：A01/A05/A09 顯著強化；A02/A03/A04/A07/A08/A10 不變；A07 cookie Secure flag 在 reverse proxy 部署後 fail-CLOSED。

---

## §2 v1 NEW-VULN 4 條對抗性核實

### NEW-VULN-1 [HIGH] Mac launchd plist 0.0.0.0 - ✅ FULLY FIXED

**v1 finding**：`com.openclaw.trading-api.plist:56-57` 仍硬編 `0.0.0.0`，跨平台兼容性允 Mac 部署 → Mac 整 LAN 可 reach :8000

**v2 修復 (`b658e18c` security: harden launchd api bind default)**：
- `com.openclaw.trading-api.plist:56-57` 改 `127.0.0.1` (verified via Read)
- 新增 `helper_scripts/deploy/launchd_preflight.sh` static guard
- 新增 `c187fd99` `helper_scripts/lib/api_bind_host.sh` resolver：
  - default `auto` mode = Tailscale IPv4 → loopback fallback
  - `0.0.0.0` / `::` 顯式 reject (line 40-44, exit 2)
  - 3 個 helper script (restart_all/clean_restart/fresh_start) 全 wire 過 resolver
- 新增 Batch E static regression test

**對抗性 verify**：
- File diff confirmed: launchd plist line 56-57 = `<string>--host</string><string>127.0.0.1</string>`
- Source grep `0.0.0.0` in `helper_scripts/` (excluding .bak): 0 命中
- Linux runtime port: `LISTEN 0 2048 100.91.109.86:8000` (Tailscale IPv4, NOT 0.0.0.0)
- API process command: `uvicorn app.main:app --host 100.91.109.86 --port 8000 --workers 4`

**結論**：✅ source + runtime 雙落地。v1 NEW-VULN-1 完全閉合。
- **附加觀察**：Linux runtime 改 Tailscale IPv4（不是 v1 預期的純 127.0.0.1），這是 c187fd99 ops decision — 用 OPENCLAW_BIND_HOST=auto 的 Tailscale autodetect 路徑保留 GUI 跨機 access，**比純 0.0.0.0 限定（限 tailnet 100.64.0.0/10 members）**，且 0.0.0.0 在 resolver 顯式 reject。屬於 secure-by-default + opt-in tailnet pattern，符合 ops 需求。

### NEW-VULN-2 [HIGH] HIGH-1 lease audit pipeline wire 但 0 row emit - ✅ FULLY FIXED

**v1 finding**：lease pipeline wire 完成 + env var ON + introspect=true，BUT `learning.lease_transitions` PG row count = 0 / 0 / 0 (total / 24h / 8h)，因 `governance_core.rs:405-407` non-Production profile 直 return Bypass 不 emit

**v2 修復 (`e97a333b` governance: audit non-production lease bypass)**：
- `governance_core.rs:402-417` diff verified: `if !profile.requires_lease()` 內加 `build_bypass_transition_msg(...)` + `emit_transition_fail_soft(...)` 後 return `LeaseId::Bypass`
- 新增 `build_bypass_transition_msg` in `governance_emit.rs`
- V078 migration 加 `to_state` 域擴 `BYPASS` 狀態
- 新增 Rust 測試 `governance_bypass_audit.rs` + Python migration shape test

**對抗性 verify (Linux PG ssh trade-core)**：
```sql
SELECT count(*) FROM learning.lease_transitions; -- 7950
SELECT to_state, count(*) FROM learning.lease_transitions GROUP BY to_state;
-- BYPASS | 7950
SELECT max(created_at), now() - max(created_at);
-- 2026-05-09 16:31:01 | 00:00:09  (latest 9.5s ago)
SELECT engine_mode, count(*) FROM learning.lease_transitions GROUP BY engine_mode;
-- demo      | 4039
-- live_demo | 3911
SELECT count(*) FILTER (WHERE created_at > now() - interval '8 hour') AS h8, count(*) AS total;
-- 7950 | 7950   (100% in last 8h, ~16/min sustained)
```

**結論**：✅ v1 期間 0 row → v2 期間 **7950 BYPASS rows in 8h**，~16 row/min sustained emit rate，demo/live_demo 50/50 split。HIGH-1 audit channel 真實工作中。observability 死角徹底封閉。lineage rate 為 mainnet promote 提供穩定基線。

### NEW-VULN-3 [MEDIUM] Cookie Secure flag default `auto` reverse proxy fail-OPEN - ✅ SOURCE-FIXED

**v1 finding**：`auth_routes_common.py:should_set_secure_cookie` 在未配 `OPENCLAW_TRUST_PROXY_HEADERS` 時，X-Forwarded-Proto 不被信任 → cookie 無 Secure flag

**v2 修復 (`cfadc339` security: close cookie and phase4 follow-ups)**：
- 新增 `_first_header_token()` + `_has_https_proxy_hint()` helpers
- 邏輯改：positive HTTPS proxy hint (X-Forwarded-Proto / X-Forwarded-Ssl / Forwarded proto=https) → return True，**不再需要 OPENCLAW_TRUST_PROXY_HEADERS=1 opt-in**
- 註釋 fail-CLOSED 說明：spoofing 該 hint on direct HTTP → cookie 在 HTTP 下 unusable
- `OPENCLAW_COOKIE_SECURE=1/0` 強制 override 仍存

**對抗性 verify**：
- Source grep `secure=` cookie set sites: 2 處（auth_routes_common.py:222,238），全用 `should_set_secure_cookie(request)`
- Header parsing 邏輯：3 個 proxy hint header（X-Forwarded-Proto / X-Forwarded-Ssl / Forwarded）獨立檢查，逗號 split first token
- 真 HTTPS / HTTPS proxy → Secure=True；plain HTTP 無 hint → Secure=False (dev-friendly auto)
- 偽造 X-Forwarded-Proto:https + 真 plain HTTP → cookie set with Secure → browser refuse to send over HTTP → fail-closed

**結論**：✅ source 落地。runtime 未驗（uvicorn 14:07 起仍跑舊代碼，cfadc339 是 15:48 commit），但 source 邏輯正確 + 設計 fail-closed。reverse proxy 部署 (P0-OPS-1) 時 default secure。

### NEW-VULN-4 [INFO] HIGH-2 phase4 endpoint 0 mount in main.py - ⚠️ SOURCE-FIXED, RUNTIME STALE

**v1 finding**：HIGH-2 phase4 weekly_review approve/reject add `require_scope_and_operator` source-level perfect，但 0 處 `include_router(phase4_router)` → router 不 reachable, attack surface = 0 但屬 dead-code defensive fix，audit closure transparency bug

**v2 修復 (`cfadc339`)**：
- `main.py:153-154` 加 `from .phase4_routes import phase4_router  # noqa: E402` + `app.include_router(phase4_router)` (verified via grep)
- 新增 `test_new_vuln_3_4_security_static.py` static regression coverage

**對抗性 runtime verify (Linux ssh)**：
```bash
# 4 個 endpoint adversarial unauthenticated POST (via tailnet IP):
POST /api/v1/phase4/weekly_review/approve  -> HTTP 404  (unexpected!)
POST /api/v1/phase4/weekly_review/reject   -> HTTP 404  (unexpected!)
POST /api/v1/scout/market-signal           -> HTTP 401  ✅ fail-closed
POST /api/v1/paper/layer2/trigger          -> HTTP 401  ✅ fail-closed
```

**Phase4 仍 404 root cause**：
- Linux git head = `1bd55689` ✅ 同步
- Linux source main.py:153-154 ✅ 真有 include_router(phase4_router) 行
- **uvicorn worker process start time = 14:07:35**, cfadc339 commit time = **15:48:10**
- API 服務未 reload，當前進程 import main.py 是 cfadc339 之前快照
- engine.sock mtime = 15:52 (engine 已重啟 + e97a333b lease emit fix 真生效)，但 API uvicorn 沒一起 restart

**結論**：⚠️ source-fixed but runtime stale (degraded INFO 至 LOW)。本次 audit 沒「本日重新 deploy」事件，operator 必須跑 `bash helper_scripts/restart_all.sh --keep-auth` 才能 phase4 mount 生效。當前 attack surface 仍 = 0（404 等同 NEW-VULN-4 v1 狀態），無新風險，但 audit closure 「source-fixed = closed」結論在 reload 前不能套用。

---

## §3 v1 9 條 ⚠️/❌ findings 24h 增量

| ID | v1 狀態 | v2 狀態 | 備註 |
|---|---|---|---|
| HIGH-1 lease audit wire | ⚠️ wire OK 0 row emit | ✅ 7950 row 真實 emit | NEW-VULN-2 解決 |
| HIGH-2 phase4 weekly_review | ⚠️ source OK + dead code | ⚠️ source OK + uvicorn 未 reload | NEW-VULN-4 source 解、runtime 待 reload |
| HIGH-3 scout market-signal/event-alert | ✅ runtime 401 verified | ✅ 維持 401 | unchanged |
| HIGH-4 0.0.0.0 binding | ⚠️ Linux 127.0.0.1 + Mac plist 0.0.0.0 | ✅ Linux 100.91.109.86 (tailnet) + Mac plist 127.0.0.1 + reject 0.0.0.0 in resolver | NEW-VULN-1 + new layer |
| MEDIUM-A layer2 /trigger | ✅ runtime 401 verified | ✅ 維持 401 | unchanged |
| MEDIUM-B openclaw _require_proposal_creator | ❌ 未修 | ❌ 未修 (24h 0 commit) | P2 backlog |
| MEDIUM-C single-user / cookie | ❌ 未修 | ❌ 未修 (待 multi-user IMPL) | P2 backlog |
| MEDIUM-D directive_executions 0 row | ❌ 未修 | ❌ 未修 (與 5-Agent track) | P2 backlog |
| MEDIUM-E IPC HMAC fail-OPEN | ⚠️ design fail-OPEN runtime fail-CLOSED | ⚠️ unchanged | Linux runtime sock 0o600 + env IPC_SECRET 雙保險 |
| MEDIUM-F ai_service.sock | ⚠️ chmod 0o600 OK + 0 HMAC | ⚠️ unchanged (sock 0o600 confirmed in Linux) | same-user attack surface 保留 |
| LOW-1..6 | ❌ 0 修 | ❌ 0 修 (P2 backlog) | layer2_routes 仍 4 處 `str(exc)` 洩漏 |

---

## §4 v2 新引入 attack surface 評估

**v2 範圍 (455d796e..1bd55689)** 新代碼掃描：

| 檢查項 | 結果 |
|---|---|
| 新增 router endpoint 帶 unauth | 0 條（grep `+@.*\.(post\|get\|put\|delete)\(` only matched test assertion mirrors） |
| 新增 ContextDistiller `context_distiller.py` (35f81a7b) | helper class only，0 endpoint，0 router；通過 layer2_routes Existing 401 守護 |
| 新增 `promotion_gate.py` (716eb3d6) | learning_engine internal logic，0 endpoint |
| 新增 `portfolio_var.py` (cc6476dd) | learning_engine internal logic，0 endpoint |
| 新增 `feature_baseline_writer.rs` (7657bd25) | Rust internal writer，dry-run default，0 HTTP exposure |
| 新增 healthcheck [56] live_pipeline_active (c15985a5) | passive check，read-only，0 endpoint |
| 跨平台路徑硬編碼 grep `/home/ncyu\|/Users/[^/]+` 在新 route/lib | 0 命中 |
| Secret leak grep `(api_key\|api_secret\|hmac\|password\|signing).*=.*"[A-Za-z0-9+/=]{20,}"` v2 全 diff | 0 命中 |
| log statement 含 secret pattern | 0 命中 |
| 新 SQL 動態拼 (`f"SELECT...{var}"`) | 0 命中 |
| 新 subprocess shell=True | 0 命中 |

**結論**：v2 0 個新 unauth endpoint / 0 個新 secret leak / 0 個新 cross-platform path violation / 0 個新 SQL injection / 0 個新 command injection。新代碼全為 internal helper / Rust writer / passive healthcheck。

**特別關注**：
- ContextDistiller 處理 prompt context 但 max_chars bounded (default 2000)，無 prompt injection 直接 attack surface（攻擊路徑需經 layer2 /trigger，而 /trigger 已 401 守護）
- Selection bias gate / portfolio_var 是 promotion pipeline 內部邏輯，無 HTTP exposure
- 34-dim feature_baseline_writer.rs default dry-run，無 PG write 直 fire

---

## §5 對抗性 push back

### §5.1 audit closure SOP gap (重申)
v1 NEW-VULN-4 已 push back「audit closure 應 verify 端點 reachability」。v2 cfadc339 修了 phase4 mount 但**沒 reload uvicorn 即聲稱閉合**，仍是同類問題：
- source 改了 ≠ runtime 生效
- E2/E4 sign-off 應加「最低限度：commit 後測 endpoint reachability」
- HIGH-1 lease emit 是 e97a333b commit 後 engine 跑 `--rebuild` 才生效（engine.sock 15:52 mtime），但 API 沒一起 restart
- **建議 SOP**：security fix touching API code → operator 跑 `restart_all.sh --keep-auth` (full restart) 才算「runtime 閉合」

### §5.2 對 cookie Secure 的 fail-closed 設計 - A 級
NEW-VULN-3 fix 設計優於 v1 期望：
- v1 期望「需設 OPENCLAW_TRUST_PROXY_HEADERS=1 opt-in」
- v2 改成「positive proxy hint 自動觸發 Secure，不需 opt-in」
- 偽造攻擊在 plain HTTP 下不可逃 (cookie set Secure → browser refuse send) = fail-closed
- 比 v1 reasoning 更安全：deploy runbook 不需要記得 set env var

### §5.3 對 NEW-VULN-2 的延伸 - LG-3 audit emit policy
HIGH-1 BYPASS emit 只在 non-Production profile。LG-3 supervised live (Validation profile) 走進真 lease SM transition，那 emit msg 來自 acquire_lease 真實 SM，不再需要 build_bypass_transition_msg。但要 verify：
- Validation profile 真 acquire_lease 路徑下 emit msg type 是否 = `BYPASS` 還是其他 SM state
- 若 Validation 也走 BYPASS（i.e. Validation profile 的 requires_lease=true 但 acquire_lease 內走 bypass route），審計 lineage 會混淆
- **建議**：`@PA / @E1` 開 LG-3 sub-finding `F-A2`：「Validation profile audit emit policy verification — review build_msg_from_last_transition vs build_bypass_transition_msg 路徑分流」

### §5.4 對「24h 修 4 NEW-VULN」節奏 - A+ 級
v1 23:31 報告 → v2 16:32 完整核實 = 21h
- NEW-VULN-1: 5 個 commit (b658e18c + c187fd99 + 8dcc1f17 + 修 helper 3 個) — **systemic fix**（不只 plist）
- NEW-VULN-2: 1 個 commit (e97a333b) + V078 migration + Rust + Python tests — **clean fix + observability tier**
- NEW-VULN-3: 1 個 commit (cfadc339) + helper refactor + 38-line static test — **secure-by-default + dev-friendly**
- NEW-VULN-4: cfadc339 同次處理 — source 落地
- 24h 內 4 NEW-VULN 全 source-closed + 2 個 runtime verified = 罕見效率

### §5.5 仍未做的 24h 觀察點
- P0-OPS-1 HTTPS deploy 仍 0 commit (NEW-VULN-3 fix 等 reverse proxy 才生效)
- P0-OPS-2 credential rotation 仍 0 commit
- P0-OPS-4 first-day live runbook 仍 0 commit
- 7 LOW finding 24h 0 commit（P2 backlog 預期，但 layer2_routes 4 處 `str(exc)` 在 401 後仍洩漏 valid auth 流量的 exception detail）

---

## 報告元數據

- 撰寫者：E3 (Security Auditor, attacker mindset 對抗性核實)
- 撰寫時間：2026-05-09 16:32 UTC+1
- 基準範圍：commits 455d796e..1bd55689 (34 commits)
- Linux runtime PG/socket/port 真實值：ssh trade-core 即時查詢
- 對抗測試：4 個 unauth POST（2 phase4 + 1 scout + 1 layer2）→ 預期 401 → 2/4 真 401 + 2/4 phase4 router 因 uvicorn 未 reload 仍 404
- 0 個 exploit 嘗試 / 0 個 secret 內容寫入本報告
- 下次審計觸發點：
  - operator 跑 `restart_all.sh --keep-auth` 後重測 phase4 endpoint
  - P0-OPS-1 HTTPS deploy 後驗 cookie Secure 真生效
  - LG-3 IMPL 後驗 Validation profile audit emit policy
  - mainnet canary 流量觸發後驗真 SM transition lease emit (不只 BYPASS)
