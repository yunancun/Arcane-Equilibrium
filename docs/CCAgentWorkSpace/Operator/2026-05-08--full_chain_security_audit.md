# E3 全鏈安全審計 — 玄衡 Arcane Equilibrium · 2026-05-08

審計範圍：CLAUDE.md §四 5 項 live 門控 / Decision Lease retrofit / 5-Agent ↔ Rust 解耦 / OWASP Top 10 (2021) / 密鑰洩漏 / Rust unsafe / IPC / GUI auth
基準 commit：`4e2d2883`（Mac HEAD，2026-05-08）
工具：grep / Read / Bash / ssh trade-core（Linux runtime 真實 PG / socket / 端口 verify）
方法：read-only。0 個 exploit 嘗試。0 個真實 secret 內容寫入本報告。

---

## §1 Executive Summary

| 嚴重性 | 數量 | 等級 |
|---|---|---|
| **CRITICAL** | **0** | — |
| **HIGH** | **3** | weekly_review 0 auth / scout post-X 缺 require_operator / lease audit channel 死綁 |
| **MEDIUM** | **5** | IPC HMAC dev fail-open / ai_service.sock 0 auth / Layer 2 prompt injection / Operator 單一角色設計 / FastAPI 0.0.0.0 binding |
| **LOW** | **6** | CSP unsafe-inline / detail=str(e) info leak 7 處 / chmod 鬆 / ai_service sock 0o775 / DNS rebinding / x-forwarded-* trust |
| **INFO** | **4** | 0 Rust unsafe / 0 PyO3 FFI / git history grep 0 concrete secret leak / Decision Lease facade ON 但 audit channel 0 row（design state） |

**Verdict — true-live 前必修**：3 HIGH 全部 + 2 MEDIUM（IPC HMAC fail-open in dev/test、scout/openclaw 寫端點 RBAC tightening）+ 1 INFO 升 HIGH（lease audit channel writer wiring）。所有 CRITICAL = 0。

**重大改進** vs 2026-04-24：4 項 LIVE-GATE-BINDING-1 / LIVE-GUARD-1 / FIX-10 / EA-PERSIST 仍綠；新增 Decision Lease retrofit Sprint 3 已 land facade + router gate + Python bridge，但 audit writer 沒實際 spawn；H0 gate 在 Rust hot path 強制每 tick 執行（PA panorama 提到的「Python H0 dead」對交易安全 0 影響，因 hot path 在 Rust）。

**對 PA panorama 的回應**：`lease_transitions audit channel 0 row` ≠ 漏洞，但**碼好 wiring 死**（spawn function 0 production caller）—  flag flip 後仍不可能寫 audit。`5-Agent ↔ Rust hot path 解耦`對風控**反而是好事**：Rust IntentProcessor.process_with_features 內部 Gate 1（is_authorized）→ Gate 1.4（lease）→ Gate 1.5（dup check）→ Gate 1.6（balance）→ Gate 2（內建 Guardian.review）→ Gate 3 全部強制執行，不依賴 Python guardian/strategist 結果。Strategist 出 bug 不能直送 IntentProcessor — 因為 5-Agent Python 完全沒 IntentProcessor 介面。

---

## §2 5 項 Live 門控繞過矩陣

| # | 門控 | 位置 | 寫入路徑 | 繞過分析 | TOCTOU / Race | Verdict |
|---|---|---|---|---|---|---|
| **1** | Python `live_reserved` global mode | `state_compiler.py:210/238/266/318/338/538` + `live_session_routes.py:582` | GUI `/api/v1/openclaw/proposals` 或直寫 STORE | (a) global STORE 在記憶體，重啟丟（已知設計）；(b) operator role 守衛 `_require_live_trade` covers `/session/start`；(c) 不可從 env var override（`_REQUIRED_LIVE_GLOBAL_MODE` 由代碼常量繫住）；(d) Rust 端 LIVE-GATE-BINDING-1 `approved_system_mode` 必須 `live_reserved`（live_authorization.rs:50/316）— 簽名涵蓋此欄位防 tamper | 寫 STORE 與寫 authorization.json 分兩步：window 中 operator 撤回 global mode 但 authorization.json 殘留 → Rust 5 sec 輪詢仍認可至下次 verify。Window ≤ 5s + watcher 收到 trigger_live_auth_recheck 即時。**接受 trade-off** | ✅ 安全 |
| **2** | Python Operator 角色 auth | `auth.py:299/319` `require_operator_role` + `require_scope_and_operator` | cookie auth（HttpOnly + SameSite=Strict + Secure-by-config） | (a) `OPENCLAW_AUTH_ROLES` env var 預設值 `viewer,operator,operator_guarded,...` — 任何 cookie 通過者**都自動拿到 operator role**（**single-user design**，CLAUDE.md §一）；(b) 真實守衛 = 擁有 oc_auth_token cookie；(c) Login 5/min rate limit + IP lockout；(d) cookie 不可 JS 讀（HttpOnly），SameSite=Strict 防 CSRF；(e) **0.0.0.0 binding 漏 firewall** = 同 LAN client 也能 reach（HIGH） | actor.roles 是 immutable per-request，settings.auth_actor_id boot-time 凍結，TOCTOU 不可 exploit（auth.py:352-361 acknowledged） | ⚠️ MEDIUM（單一 cookie = 全 operator 權限；HTTPS deploy 前需 firewall + Tailscale ACL） |
| **3** | `OPENCLAW_ALLOW_MAINNET=1` | `bybit_rest_client.rs:526` Rust + `bybit_rest_client.py:251` Python | 啟動前 export env var | (a) Rust 構造 BybitClient 時驗 mainnet → env var → 否則直接 `BybitApiError::Business`（line 526-533）；(b) env var injection：能改 systemd unit / shell env 的攻擊者已是同 user 完全控制；(c) Mainnet env var fallback 為憑證**已封閉**（line 549 `if is_mainnet { None }`） — 即使能設 `BYBIT_API_KEY` env var 也無效；(d) **無 secret slot file → 構造 fail（line 581-585）**；(e) Demo / LiveDemo 不需此 env，符合設計 | env 在 process 啟動時讀取一次，無 race | ✅ 安全（Rust + Python 雙端對稱） |
| **4** | secret slot api_key + api_secret | `bybit_rest_client.rs:557/571` `read_secret_file(slot, "api_key")` + `..."api_secret"` | `_atomic_write_json` + `os.chmod(0o600)` for authorization.json（live_trust_routes.py:135-163）；slot/api_key 等其他檔案由 secret_files 結構 GUI tab-settings 寫入 | (a) symlink attack on parent dir：`os.chmod(parent, 0o700)` 在 _atomic_write_json line 142 設置 — 但 best-effort（OSError 吞掉，line 143-144）；攻擊者若已能寫 parent dir 早已超 user boundary；(b) secret slot 構造同步（asyncio.Lock + compare_digest 之前 audit）；(c) Mainnet credentials empty → `BybitApiError::Business` not silent fallback（line 577-585） | tempfile + os.replace = atomic POSIX rename，無 partial-read window | ✅ 安全 |
| **5** | authorization.json HMAC + TTL + env_allowed | `live_authorization.rs:308-352`（Rust verify）+ `live_trust_routes.py:205-267`（Python sign+write） | `_write_signed_live_authorization` 強制 `_require_live_reserved_global_mode` 守衛（line 188-201） + signed payload 涵蓋 (version, tier, issued_at_ms, expires_at_ms, operator_id, approved_system_mode, env_allowed_sorted_csv) | (a) HMAC-SHA256 + constant-time compare（live_authorization.rs:290-298）；(b) version=2 mismatched rejected before signature；(c) approved_system_mode 必須 `live_reserved`（line 316-322）— 即使有 valid cookie 寫 authorization.json 也需 global mode = live_reserved；(d) HMAC key = `OPENCLAW_IPC_SECRET` env var or file，不在 git；(e) Live + LiveDemo 同等嚴格（live_demo 不降級）；(f) 5 sec 輪詢 + trigger_live_auth_recheck IPC 即時通知；(g) 過期 → `cancel_token` shutdown live pipeline；(h) 13 + 9 Rust unit tests cover all rejection paths | tempfile.mkstemp + os.replace = atomic on POSIX；Rust load_and_verify 是純讀無 race；認證簽名涵蓋全 7 欄位 → 任何欄位 tamper → BadSignature | ✅ 安全 |

**結論**：5 項門控**設計綠**。實踐風險集中在 #2（cookie盜取攻擊面）+ HTTPS-only deploy（CLAUDE.md §三 #15 PRE-LIVE-2 已知 blocker）+ 0.0.0.0 binding 需網路層收緊。

---

## §3 Decision Lease audit oblivion 攻擊面

### §3.1 真實狀態（PG empirical query）

```
learning.lease_transitions          : 0 row（writer 0 caller）
learning.directive_executions       : 0 row（claude_teacher applier 0 production fire）
trading.risk_verdicts               : 18,467,774 row（極活躍）
agent.messages                      : 2 row（5-Agent runtime 解耦）
```

### §3.2 設計鏈

1. `governance_core.rs:166` `pub lease: Mutex<DecisionLeaseSm>` + `lease_transition_tx: Option<LeaseTransitionSender>`（line 176，**default None**）
2. `set_lease_transition_tx()` setter 存在（line 318）— 0 production caller
3. `acquire_lease` 內 emit hook（line 493）：`emit_transition_fail_soft(self.lease_transition_tx.as_ref(), msg)` — `lease_transition_tx == None` → 無 op
4. `database/lease_transition_writer.rs:96` `pub fn spawn_lease_transition_pipeline(..., pool, config, cancel)` 啟動 bridge thread + tokio writer task — **0 grep hit 在 main.rs / main_boot_tasks.rs / pipeline_ctor.rs**
5. `pipeline_ctor.rs:188-189` 只 set `engine_mode_tag`（為 future audit row 準備）— 沒 set `lease_transition_tx`
6. `intent_processor/router.rs:218` Gate 1.4 `if governance.router_gate_enabled()` — env var `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default OFF（governance_core.rs:200）→ 短路、走 None lease

### §3.3 Verdict

**HIGH-1**：即使 Operator 把 `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` flip → router gate ON → `acquire_lease` 真呼 → emit hook fire → 但 `lease_transition_tx == None` → 0 audit row 仍進 PG。**audit channel writer wiring 完全死**。

**攻擊面**：在當前狀態下，惡意 Operator（持 cookie）若 flip flag + 直送 lease（透過 Python `governance_lease_bridge.py`），lease 用過後**完全無 PG 紀錄**。但 Rust IntentProcessor Gate 1.4 仍會驗證 `acquire_lease` 不 panic（即使 audit silent），且 Gate 1.5/1.6/2/3 仍把關 — 不可繞過 Guardian 風控；只能靜悄運作。

**修法（建議）**：在 `pipeline_ctor.rs::with_governance` 啟動 audit pipeline。在 `main.rs` 預配 `mpsc::channel(1024)` + 呼 `spawn_lease_transition_pipeline(rx, pool, config, cancel)` + 將 tx 注入 `governance.set_lease_transition_tx(tx)`。每 pipeline 一通道。

**為何沒有 CRITICAL**：當前 `flag=OFF` 狀態下，audit channel 即使 wiring 死也不影響任何決策；且即使 flag flip，lease 仍真實 enforced、Guardian 仍真實 review，只是 audit 缺失。canary 前需修。

---

## §4 5-Agent ↔ Rust hot path 解耦的 governance bypass 風險

### §4.1 PA panorama 的擔憂

「Python Guardian verdict 永遠不到 Rust dispatch」、「一個 Strategist 出 bug 就能直送 IntentProcessor」？

### §4.2 真實架構

`tick_pipeline/on_tick/step_4_5_dispatch.rs:107` `on_tick_step_4_5_dispatch`：

```
Tick → strategy.evaluate() → IntentProcessor.process_with_features(intent, governance, paper_state, atr, profile, features, context_id, now_ms)
    ↓
    Gate 1: governance.is_authorized() — fail-closed if frozen / 0 effective auth
    Gate 1.4: Decision Lease（router_gate_enabled flag-gated）
    Gate 1.5: same-direction duplicate position reject
    Gate 1.6: negative balance reject
    Gate 2: Guardian.review (Rust 端，self.guardian — 內建 Rust check_drawdown / check_leverage / check_position_size / check_correlation 4-check)
    Gate 3: per-strategy/symbol risk_config rejection
    → submit / reject
```

### §4.3 Verdict

**5-Agent Python 解耦 ≠ 風控解耦**：
- Strategist Python = Rust 內 strategy traits 的 Mock-replacement，**不接 IntentProcessor**
- Rust Strategy（`strategies/{ma_crossover, bb_breakout, ...}.rs`）才產生 `OrderIntent` → 進 IntentProcessor
- Python Guardian = ai_service.sock 的 advisory layer（shadow），**不接 Gate 2**
- Gate 2 用 Rust 內建 `crate::guardian::Guardian` （非 Python guardian_check IPC）

**Strategist Python 出 bug 不能直送 IntentProcessor**：因為 IntentProcessor 入口在 `tick_pipeline/on_tick`（每 tick 由 Rust orchestrator 呼），完全跑在 Rust 內，Python 沒任何介面 push intent。

**唯一 Python → Rust 影響面**：
1. IPC `update_strategy_active` / `update_risk_config` — 改參數，不送 intent。需 Operator role auth 守衛。
2. claude_teacher applier 寫 `learning.directive_executions` + 改 strategy_active flag（applier.rs:200 P0/P1 denylist 三重防護）— 不直送 intent。

**結論**：原則 4「策略不能繞過風控」**完全成立**。5-Agent 解耦對 governance 是好設計。

---

## §5 OWASP Top 10 (2021) 逐項

### A01 Broken Access Control — **HIGH**

- **HIGH-2**：`phase4_routes.py:822/832` `weekly_review/approve` + `weekly_review/reject`：**0 actor parameter / 0 Depends**。anonymous client 可改 `learning.weekly_review_log` 批准狀態。**修：加 `actor: Depends(base.current_actor)` + `_require_phase4_review(actor)` 走 `require_scope_and_operator(actor, "learning:manage")`**
- **HIGH-3**：`scout_routes.py:324/430` `post_market_signal` / `post_event_alert`：有 `actor: Depends(base.current_actor)` 但 **0 require_operator**。viewer/researcher cookie 都能注入 ScoutAgent → MessageBus → 影響下游。**修：加 `require_scope_and_operator(actor, "learning:write")`**。
- **MEDIUM-A**：`layer2_routes.py:174` `/trigger`：viewer 都能 trigger Layer 2 session 消耗 budget（cost DOS）。**修：加 `require_scope_and_operator(actor, "ai_budget:write")`**。
- **MEDIUM-B**：`openclaw_routes.py:961` `_require_proposal_creator`：`{operator, operator_guarded, service}` 任意 → `service` role 無 RBAC 區隔。**修：明確 `service` role 簽發路徑或棄用**。
- 其他 17 個寫路徑 `paper_trading_routes.py` / `risk_routes.py` / `strategy_*_routes.py` / `replay_*_routes.py` / `live_session_*` / `governance_*_routes.py` / `live_trust_routes.py`：**全綠**（require_scope_and_operator 完整）。

### A02 Cryptographic Failures — **GREEN**

- HMAC-SHA256（live authorization + IPC handshake）：`hmac.compare_digest` constant-time（auth.py:234, live_authorization.rs:290-298）
- API key/secret：不入 git（.gitignore: `secrets/**`, `**/secret_files/`, `*.env`）
- HTTPS：對 Bybit api.bybit.com 強制（hardcoded URL，rest_base_url() rust:85-90）
- 不自寫 crypto（用 ring / rustls / pyca-cryptography）

### A03 Injection — **LOW**

- **LOW-1**：`replay_data_coverage.py:271` `cur.execute(f"...FROM {name};")` — table name 是 hardcoded list，**非 user input** → 安全 trade-off；建議改 `psycopg.sql.SQL().format(sql.Identifier(name))`
- **0 SQL injection**：所有 user-input 走參數化（asyncpg `execute(query, *args)` / sqlx `query!()`）
- **0 shell=True / os.system**
- **subprocess.run** 全用 list args + `--` separator（layer2_tools.py:498 web-pilot + settings_routes.py:328 _dev_git）
- **0 dynamic eval / exec**

### A04 Insecure Design — **GREEN**

- 寫操作 fail-closed（auth.py / Rust IntentProcessor Gate 1）
- `OPENCLAW_ALLOW_MAINNET=1` + 憑證雙驗（bybit_rest_client.rs:526/577）
- Rate limit 全覆蓋（slowapi 120/min default + 5/min login）
- Idempotency：`replay/experiment_registry.py:_REGISTER_IDEM_CACHE` cover register

### A05 Security Misconfiguration — **HIGH (HTTP bind) / MEDIUM**

- **HIGH-4**（升 HIGH-7 in §9）：FastAPI `--host 0.0.0.0:8000`（restart_all.sh / clean_restart.sh / fresh_start.sh / deploy/README.md）— 不限 Tailscale / loopback。需網路層 firewall / VPN ACL 配合 cookie auth + rate limit。
- CORS：default same-origin only；設 `OPENCLAW_CORS_ORIGINS` 時自動 strip `*`（main_legacy.py:273-280）
- DB：`trading_admin` 角色，schema 分離（trading / learning / agent / risk / market / replay / observability）
- systemd unit：deploy/README.md 有但操作者自配，無強制 `User=`

### A06 Vulnerable Components — **NOT-AUDITED**（out of scope）

- requirements.txt + Cargo.lock 鎖版本 ✅
- 建議：CI 加 `pip-audit` + `cargo audit` daily

### A07 Authentication Failures — **MEDIUM**

- HttpOnly + SameSite=Strict + Secure-by-config cookies（auth_routes_common.py:197-205）
- Login 5/min rate limit + 15min IP lockout 5 fails（auth.py:50-55）
- Constant-time credential compare（hmac.compare_digest）
- **MEDIUM-C**：`OPENCLAW_AUTH_ROLES` 預設值含 `operator,operator_guarded,config_admin,...` — single-user design 內所有 cookie auth user = operator。Cookie 盜取 = 全權限。修：HTTPS-only deploy + Tailscale-only firewall + 1 Operator cookie。

### A08 Software/Data Integrity — **GREEN**

- Migration V###.sql：Guard A/B/C 強制（CLAUDE.md §七）
- `OPENCLAW_AUTO_MIGRATE=1` opt-in
- Cargo.lock + requirements.txt 鎖版本

### A09 Logging Failures — **MEDIUM**

- `change_audit_log.py` 存在但 0 grep hit production write — review 寫入點
- **MEDIUM-D**：`learning.directive_executions` = 0 row（claude_teacher applier 0 production fire）— audit 設計做完但沒實際 directive 落地
- **HIGH-1**（§3）：`learning.lease_transitions` = 0 row — wiring 死
- 失敗 auth attempt log（auth_legacy_routes.py 有）

### A10 SSRF — **GREEN**

- `layer2_tools.py:894` `_fetch_url`：scheme 限 http/https + hostname 排除 localhost/127/0.0.0.0/.local/.internal/.corp + IP private/loopback/link_local/reserved 阻擋 + `follow_redirects=False`
- **LOW-2**：DNS rebinding（hostname 解析後再 connect 時不 re-validate IP）
- Bybit URL hardcoded enum

---

## §6 密鑰洩漏 grep 結果

### §6.1 git history scan（2245 commits）

```
規則 A: ^\+(BYBIT_API_KEY|BYBIT_API_SECRET|GRAFANA_ADMIN_PASSWORD|POSTGRES_PASSWORD|PGPASSWORD)\s*=\s*[^<\$].{6,}
命中: 5 commits (a3b54ce, 9bf6ee7, 63563d0, aa41e76, 8e0cccd)
真實洩漏: 0 (全部是 PG_PASS="$(grep ...)" 等讀檔/變數模式，無具體值)
```

### §6.2 .gitignore 檢查

```
*.env
.env
.env.*
secrets/
**/secret_files/
**/environment_files/
**/service_configs/
.claude_reports/
```

完整覆蓋 — settings/ 從未進 git。

### §6.3 CLAUDE.md §三 #16 提的「PG password + Grafana admin 6 commit 公開」

在 srv repo 2245 commit 中**找不到具體值**。可能在：
1. OpenClaw Gateway 外部 repo
2. 其他舊 history（已 force push）
3. operator 個人記憶基於其他來源

**Recommendation**：請 operator 確認具體 commit hash + repo + 文件，方可走 incident response（key rotation + filter-repo）。Live 前須確認此項已 close。

### §6.4 真實 secret 檔案 chmod check（Linux）

需 ssh trade-core 看 `~/BybitOpenClaw/secrets/secret_files/bybit/{demo,live}/` 0o600 / parent dir 0o700。E5 P1-1 chmod audit 中已驗，**保留 INFO**。

---

## §7 Rust unsafe / FFI / IPC 安全

### §7.1 Rust unsafe scan

```
$ grep -rn "unsafe" rust/openclaw_engine/src rust/openclaw_core/src
2 hits — 全是注釋說明「無 unsafe」
```

**INFO-1**：openclaw_engine + openclaw_core **0 unsafe block / fn / impl**（vs 2026-04-24 同等）。整個 hot path memory-safe by Rust type system。

### §7.2 FFI / PyO3

```
$ grep -rE "pyo3|extern \"" rust/ (excluding target/)
0 hits in src
```

PYO3-ELIMINATE-1（PA panorama 確認）後**0 PyO3 binding**。Python 與 Rust 全走 IPC（JSON-RPC over Unix socket）。記憶安全邊界乾淨。

### §7.3 IPC socket security

| socket | 路徑 | 權限 | 認證 |
|---|---|---|---|
| **engine.sock** | `/tmp/openclaw/engine.sock` | `srw-------` (0o600) | HMAC-SHA256 handshake `__auth` (Live mandatory，main.rs:356 panic if unset；paper/demo dev fail-OPEN) |
| **ai_service.sock** | `/tmp/openclaw/ai_service.sock` | `srwxrwxr-x` (0o775) ⚠️ | **0 auth handshake** — Rust ai_service_client → Python ai_service_listener 直接送 JSON-RPC |
| `/tmp/openclaw` parent | drwx------ (0o700) | owner-only | — |

**MEDIUM-E**（已知 2026-04-24 memory）：IPC HMAC auth 在 `OPENCLAW_IPC_SECRET` 未設時 fail-OPEN — Live 強制（main.rs:356 panic），**paper/demo 跳 auth**。同 user 任意 process 可發 JSON-RPC（含 `update_risk_config` 等寫端點）。但 `/tmp/openclaw` 0o700 parent dir + single-user 部署 = 攻擊面限同 user。
**MEDIUM-F**：`ai_service.sock` 用 `asyncio.start_unix_server` **沒 chmod**（line 149 ai_service_listener.py）— 0o775 group/others readable。Rust client → Python service 連接也**0 HMAC handshake**。Same single-user defense-in-depth：parent 0o700 阻其他 user。但未來 multi-user host 立即洩漏 attack surface。
**LOW-3**：socket bind race window：`set_permissions` after `UnixListener::bind`（server.rs:325-336）— 介於兩者之間 socket 是 default umask 權限。Live 模式問題小（mandatory HMAC），dev 模式有 microsecond 攻擊窗口。

### §7.4 IPC handler input validation

`ipc_server/handlers/risk.rs` / `governance.rs` / `strategy.rs` 等用 `param_extractor` (`optional_bool` / `required_str` / `optional_u64`) 強制型別檢查。**OK**。

---

## §8 GUI auth + Operator role

### §8.1 認證鏈

```
GUI POST /api/v1/auth/login
  ↓ verify_login_credentials (constant-time, 5/min rate limit, IP lockout 15min)
  ↓ set_auth_cookie (HttpOnly + SameSite=Strict + Secure-by-config)
  ↓ oc_auth_token cookie

GUI 後續 request：
  ↓ verify_token_constant_time(cookie.value)
  ↓ build_authenticated_actor(actor_id="demo-operator", roles={viewer, operator, operator_guarded, config_admin, finance_input}, scopes={...})
  ↓ Depends(base.current_actor) → AuthenticatedActor
  ↓ _require_*(actor) → require_scope_and_operator → check role + scope
```

### §8.2 真實權限矩陣

`OPENCLAW_AUTH_ROLES` env 預設 5 role：
- `viewer`：只讀
- `operator`：寫操作
- `operator_guarded`：governance approval
- `config_admin`：配置寫
- `finance_input`：cost / event / note input

`OPENCLAW_AUTH_SCOPES` env 預設 ~30 scope：每 route family 有獨立 `xxx:write` scope。

但**所有 cookie auth user 拿到所有 5 role**（single-user design）— role 不分人。Real-world auth 是「持 oc_auth_token = 全權限」。

### §8.3 攻擊面

1. **Cookie 盜取**：HTTPS not enforced（CLAUDE.md §三 #15 PRE-LIVE-2 0 行 IMPL）+ `--host 0.0.0.0` → 同 LAN MITM 可截取 cookie
2. **CSRF**：SameSite=Strict 阻 ✅
3. **XSS → cookie 讀取**：HttpOnly 阻 ✅，但 `'unsafe-inline'` script CSP（main_legacy.py:340）+ 5 處 innerHTML（tab-live.html 等）有 XSS surface
4. **Login brute force**：5/min rate limit + 15min lockout ✅
5. **Tailscale-only**：未強制（HIGH-7） — 需網路層補

### §8.4 推薦修法（true-live 前）

1. PRE-LIVE-2 LAND：HTTPS reverse proxy（caddy / nginx）+ Cookie Secure flag forced
2. `--host 127.0.0.1` 或 firewall ACL（trading.openclaw.local + Tailscale-only）
3. CSP 加 `nonce-` 替 `'unsafe-inline'`（XSS hardening；non-trivial GUI 改動）
4. ✅ HSTS header
5. ✅ Audit log 寫入「login from new IP」事件

---

## §9 Top 15 Vulnerability（CVSS-like 排序）+ 修復順序

| # | ID | 等級 | OWASP | CVSS-like | 修法 |
|---|---|---|---|---|---|
| 1 | **HIGH-1** | HIGH | A09 | 7.0 | `lease_transition_writer::spawn_lease_transition_pipeline` wire 進 main.rs / pipeline_ctor.rs；audit channel 配 mpsc 後注入 governance.set_lease_transition_tx |
| 2 | **HIGH-2** | HIGH | A01 | 8.5 | `phase4_routes.py:822/832` weekly_review/approve+reject 加 `actor: Depends(base.current_actor)` + `require_scope_and_operator(actor, "learning:manage")` |
| 3 | **HIGH-3** | HIGH | A01 | 7.0 | `scout_routes.py:324/430` post_market_signal+post_event_alert 加 `require_scope_and_operator(actor, "learning:write")` |
| 4 | **HIGH-4 (was MEDIUM)** | HIGH | A05 | 6.5 | restart_all.sh / clean_restart.sh / fresh_start.sh `--host 0.0.0.0` 改 `--host ${OPENCLAW_BIND_HOST:-127.0.0.1}` + Tailscale serve front-end |
| 5 | **MEDIUM-E** | MEDIUM | A07 | 5.5 | IPC connection 在 `OPENCLAW_IPC_SECRET` 未設時 fail-OPEN — paper/demo 加 `--require-ipc-auth=false` opt-in flag，default require auth |
| 6 | **MEDIUM-F** | MEDIUM | A05 | 5.0 | `ai_service_listener.py:149` 加 `os.chmod(socket_path, 0o600)` after `start_unix_server`；Rust ai_service_client + Python listener 加 HMAC handshake（與 engine.sock 一致） |
| 7 | **MEDIUM-A** | MEDIUM | A01 | 4.5 | `layer2_routes.py:174` /trigger 加 `require_scope_and_operator(actor, "ai_budget:write")` |
| 8 | **MEDIUM-B** | MEDIUM | A01 | 4.0 | openclaw_routes._require_proposal_creator: `service` role 用法明確化或棄用 |
| 9 | **MEDIUM-C** | MEDIUM | A07 | 4.0 | Operator single-user → multi-user：HTTPS + Tailscale + 個人 cookie（PRE-LIVE-2 + REAL-USER-DB） |
| 10 | **MEDIUM-D** | MEDIUM | A09 | 3.5 | `learning.directive_executions` 0 row — claude_teacher applier production fire 是另議題；audit infra 已就位 |
| 11 | **LOW-1** | LOW | A03 | 2.5 | replay_data_coverage.py:271 改 sql.Identifier |
| 12 | **LOW-2** | LOW | A10 | 2.5 | layer2_tools._fetch_url DNS rebinding：解析後 connect 前 re-validate IP |
| 13 | **LOW-3** | LOW | A05 | 2.0 | engine.sock chmod race window：UnixListener bind + chmod 兩步間 microsecond 窗口；Live mandatory HMAC 已是真正 defense |
| 14 | **LOW-4** | LOW | A03 | 2.0 | 7 處 `detail=f"...{e}"` info leak（paper_trading_routes 5 處 / strategy_write 1 處 / ml_routes 1 處）— sanitize exception type only |
| 15 | **LOW-5** | LOW | A05 | 1.5 | CSP 'unsafe-inline'（main_legacy.py:340）— 改 nonce-based（GUI 大改） |

**修復順序**：HIGH-1 / HIGH-2 / HIGH-3 / HIGH-4 立即（true-live 前 must-fix）；MEDIUM-E / MEDIUM-F 一個 sprint；其餘 P2 backlog。

---

## §10 E3 Verdict + true-live 前必修 vulnerability 列表

### §10.1 整體 Verdict

**安全評級：A（vs 2026-04-24 A-）**：
- 0 CRITICAL ✅
- 5 項 Live 門控 5/5 設計綠（vs 2026-04-24 5/5 綠）
- 0 Rust unsafe ✅
- 0 PyO3 FFI ✅
- 0 SQL injection ✅
- 0 真實 secret leak in srv repo ✅
- HMAC-SHA256 + constant-time + atomic write ✅

**新增風險**（vs 2026-04-24）：
- HIGH-1：Decision Lease audit channel writer wiring 死（Sprint 3 IMPL 完，spawn 沒接）
- HIGH-2：phase4_routes 2 端點 0 auth（regression？或 5-Agent track 後新增）
- HIGH-3：scout_routes 2 端點缺 require_operator
- HIGH-4：FastAPI 0.0.0.0 binding 對外（部署層問題）

### §10.2 true-live 前必修 vulnerability list（4 條）

```
1. HIGH-1: spawn_lease_transition_pipeline + set_lease_transition_tx wire
   理由: AMD-2026-05-02-01 §5.4 flag flip canary 24h 前必須能 audit
   ETA: 0.5 sprint
   Owner: E1 (Rust ipc/pipeline) + E4 (PG verify)

2. HIGH-2: phase4_routes weekly_review/approve+reject 補 require_operator
   理由: 任何 anon client 可改 governance 批准狀態
   ETA: 0.1 sprint (5-min code change)
   Owner: E1

3. HIGH-3: scout_routes 2 端點補 require_scope_and_operator
   理由: viewer 角色可注入 ScoutAgent → 影響下游 5-Agent
   ETA: 0.1 sprint (5-min code change)
   Owner: E1

4. HIGH-4: --host 從 0.0.0.0 改 OPENCLAW_BIND_HOST default 127.0.0.1
   理由: 同 LAN client 可繞 cookie + brute force
   ETA: 0.2 sprint (更新 4 個 helper script + systemd unit + Tailscale serve frontend)
   Owner: E1 + E4 (Linux deploy verify)
```

### §10.3 PRE-LIVE-2 already-known blocker（CLAUDE.md §三 #15）

HTTPS deploy + Cookie Secure forced — 與 HIGH-4 配合，3-day work。Live 前 must。

### §10.4 不必修但 monitoring

- MEDIUM-A/B/C/D/E/F + 6 LOW：MEDIUM-E / MEDIUM-F 推進到 P1 sprint；其餘 P2 backlog。
- INFO：claude_teacher directive_executions 0 row（applier 設計 OK，未實際 fire — 5-Agent 未對接 directive sink，不是漏洞）

### §10.5 對 PA panorama 「lease_transitions 0 row + H0_GATE 0 caller」的 security 立場

**lease_transitions 0 row**：HIGH-1 必修（audit channel writer 死綁）— 但**不阻 trading safety**（Gate 1.4 仍 enforced，Guardian Gate 2 仍把關）。

**Python H0_GATE 0 caller**：對 trading **無安全影響**。Rust h0_gate.check 每 tick 強制執行（step_0_5_h0_gate.rs:41），shadow_mode 由 Operator IPC 改 — 是 Rust hot path 唯一 H0 gate caller。Python 端 H0 是死 wiring 不影響 Rust。

**5-Agent 解耦**：對 governance 是好設計。Strategist Python 出 bug 不能直送 IntentProcessor，因為**沒任何 Python → IntentProcessor 介面存在**。

---

## 報告元數據

- 撰寫者：E3（Security Auditor，attacker mindset）
- 撰寫時間：2026-05-08
- 基準 commit：4e2d2883（Mac HEAD）
- Linux runtime PG 真實值由 ssh trade-core 即時查詢 verify
- 手檢檔案：~30 個
- grep 規則：~25 條（Pattern A-G + OWASP 各條 + 5 gate trace）
- 0 個 exploit 嘗試 / 0 個 secret 內容寫入本報告
- 下次審計觸發點：HIGH-1/2/3/4 fix 後 rerun + canary flip 前 + Wave 7 P5 deploy 前

