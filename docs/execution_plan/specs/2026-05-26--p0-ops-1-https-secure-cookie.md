# P0-OPS-1 Spec — HTTPS / Secure Cookie / CSRF / CSP（Sprint 4 first Live W18-21 前 closure）

**日期**：2026-05-26
**Owner**：PA（spec）→ E1（IMPL）→ E2（review）→ E3 + BB（security sign-off）→ E4（regression）
**Status**：SPEC DRAFTED — pending operator sign-off + E1 IMPL dispatch
**來源**：`srv/docs/KNOWN_ISSUES.md:515-520`（P0-OPS-1 原始描述）+ `srv/TODO.md` §1 + `srv/TODO.md` §12 `P2-WP05-CSP-UNSAFE-INLINE`
**ADR refs**：ADR-0004 LiveDemo no degradation / ADR-0007 Mac-dev Linux-runtime split / ADR-0015 OpenClaw control-plane repositioning
**CLAUDE.md refs**：§四 Hard Boundaries（5-gate Live + LiveDemo 不降級）/ §六 路徑可移植（無硬編碼 `/home/ncyu`、Apple Silicon ready）
**Scope guard**：本 spec 只覆蓋 OPS-1。OPS-2（cred rotation）/ OPS-3（legal/ToS）/ OPS-4（first-day runbook）由各自 spec 處理。

---

## §0 摘要

| 項目 | 現況 | 目標 |
|---|---|---|
| Bind | `100.91.109.86:8000`（Tailscale IPv4，HTTP only，per `lib/api_bind_host.sh`）| 維持，加 reverse proxy 終結 TLS |
| TLS | 無 | **Caddy + Tailscale cert**（Tailscale magic DNS + ACME-like 自簽鏈）+ systemd timer renewal |
| Secure cookie | `auth_routes_common.py::set_auth_cookie` 已 HttpOnly + SameSite=Strict + 條件 Secure（`OPENCLAW_COOKIE_SECURE=auto` + `_has_https_proxy_hint`）| `OPENCLAW_COOKIE_SECURE=1` 強制 + `OPENCLAW_TRUST_PROXY_HEADERS=1` 顯式啟用 proxy header gate |
| CSRF | **只有 SameSite=Strict 一層**，沒有 token middleware | `fastapi-csrf-protect` double-submit token + 寫操作 (`POST`/`PUT`/`DELETE`/`PATCH`) 全 gate |
| CSP | `unsafe-inline` script-src + style-src + `http://trade-core:3000` frame-src（per `main_legacy.py:331-352`）| Wave A live deploy：先解 `http://trade-core:3000` 升 HTTPS；`unsafe-inline` 升 P1 → Wave B 用 nonce 或 hash 拆 inline；P2→P1 升級 trigger 已此 spec 設定 |
| Bind host | `100.91.109.86` Tailnet 直存取仍開放 | Live 後 bind 收緊 `127.0.0.1`，**只走 Caddy 反代** |

**核心決定**：所有 HTTPS / cert / TLS 終結都在 Caddy；FastAPI/uvicorn **永不**直接拿 cert / key。理由 §1.3。

---

## §1 TLS 終結方案 — 三選一推薦 Caddy + Tailscale cert

### 1.1 三方案對比

| 維度 | A. Caddy + Let's Encrypt（公網 DNS）| B. Tailscale Funnel（公開 HTTPS）| **C. Caddy + Tailscale cert（Tailnet-only HTTPS）** |
|---|---|---|---|
| 公網暴露 | 是（443 對外）| 是（Funnel 隧道） | **否**（HTTPS 只在 tailnet）|
| Cert 來源 | Let's Encrypt ACME | Tailscale internal CA | Tailscale internal CA（`tailscale cert <node>.tail358794.ts.net`）|
| 自動續期 | Caddy 內建 ACME，無需手動 | **無**（per [Tailscale Issue #8204](https://github.com/tailscale/tailscale/issues/8204)），需 systemd timer 自管 | **無**，需 systemd timer 自管（14d 內到期 trigger renewal）|
| 攻擊面 | 公網 443 全曝；DDoS / port scan / login brute | Funnel 暴露 GUI 在公網；Sprint 4 $500 first Live 不需要對外 | **僅 tailnet 內**，攻擊面 = 已認證 Tailscale 設備 |
| Mac 部署相容 | 需公網域名 + 80/443 入站；家用 NAT/CGNAT 經常死 | Funnel 跨平台 OK，但暴露 | **跨平台 OK**（Linux 現址 + Apple Silicon Mac 都能 `tailscale cert`）|
| Cert 失敗 mode | Let's Encrypt rate limit / ACME challenge fail | Tailscale 服務中斷 = cert 過期 | Tailscale 服務中斷 = cert 過期；GUI 仍可走原 HTTP fallback（dev 模式）|
| 設定複雜度 | 中（DNS + 80/443 路由 + reverse proxy）| 低（`tailscale funnel`）| 中（Caddy + cert renew systemd unit）|
| 對 5-gate Live boundary 影響 | 增加公網入口 = 增加 5-gate 外攻擊面 | 同上 | **無**（GUI 通道屬 control plane，不碰 execution / lease）|

### 1.2 推薦：**方案 C — Caddy + Tailscale cert（Tailnet-only HTTPS）**

**5 條理由**：

1. **Sprint 4 first Live $500 scale 不需要公網 GUI**。Operator 從筆電/手機透過 Tailscale 連線；公網 HTTPS 屬「未來 OpenClaw Gateway 對外場景」，不在 OPS-1 scope 內。
2. **攻擊面最小**：只允許已 Tailscale 認證設備存取 → 即使 Caddy 0day / 認證 cookie 洩漏，攻擊者仍需 tailnet 入侵。對齊 CLAUDE.md §四 Hard Boundaries「Mainnet env-var fallback 已關」精神 — defence-in-depth。
3. **Apple Silicon 可移植**（CLAUDE.md §六）：Tailscale + Caddy + systemd 都在 macOS（launchd）/ Linux（systemd）有對等實作；Mac 部署只需替換 service manager unit，配置 99% 重用。Let's Encrypt 方案要求公網域名 + 入站 80/443，家用 NAT/CGNAT 嚴重劣勢。
4. **失敗模式可控**：Tailscale CA 中斷時，Caddy 仍能服務舊 cert 直到過期；GUI 不會立刻不可用。systemd timer 14d 提前 renew + alert 觸發。
5. **與既有 bind 行為對齊**：`lib/api_bind_host.sh` 已 bind tailnet IPv4；TLS 加在同一層，**不需動 FastAPI/uvicorn 代碼**（spec §3.4 將 bind 改 `127.0.0.1`，Caddy reverse_proxy 過去 — 一個 helper script edit + Caddyfile 即可）。

**Reject 方案 A 的理由**：Let's Encrypt 要求公網域名 + 80/443 入站 + 持續續期成功率達標。Sprint 4 first Live 無公網 GUI 需求，A 把可選功能（公網存取）變必選，違反「least code, no speculative implementation」（CLAUDE.md Operating Style §2）。

**Reject 方案 B 的理由**：Funnel 把 GUI 推到公網，無 Tailscale 認證；登入頁直接暴露於互聯網爬蟲 / brute force。對 $500 scale 風險不對稱。

### 1.3 為什麼 Caddy 而不是 uvicorn TLS / nginx

- **uvicorn TLS**：把 cert/key 引入 Python 進程域 → 任何 Python uncaught exception 都可能 leak cert path / 內存。FastAPI/uvicorn TLS 主要為 dev convenience，不適合 production trust boundary。
- **nginx**：可行，但 nginx 對 Tailscale cert 自管 renew 需要自寫 reload hook；Caddy 設計就是 cert lifecycle first-class，跟 systemd timer 整合 1 行 `caddy reload`。對 Sprint 4 first Live 時程，Caddy 工時節省 4-6 hr。
- **同 5-gate Hard Boundary 對齊**：reverse proxy 不碰 Bybit credential / decision_lease / authorization.json；它只是 TLS 終結 + header sanitization。屬 control-plane layer（ADR-0015）。

### 1.4 不對 5-gate Live boundary 弱化的證明

| Live boundary（CLAUDE.md §四）| 本 spec 影響 | 證明 |
|---|---|---|
| `live_reserved` | 無 | 純 GUI 通道，不碰 execution settings |
| Operator role auth | **強化**（HTTPS + Secure cookie 防 cookie steal）| Auth cookie HttpOnly + Secure + SameSite=Strict 三層 |
| `OPENCLAW_ALLOW_MAINNET=1` | 無 | env-var；reverse proxy 不參與 |
| 有效 secret slot | 無 | secret 在 `secrets/`，Caddy 不存取 |
| `authorization.json` 簽名 + TTL | 無 | 純 Python 路徑 |
| **LiveDemo 不降級**（ADR-0004）| 強化（同 Live 認證流，HTTPS only）| 同 cookie 設定，無分流 |

---

## §2 TLS Cert Lifecycle

### 2.1 Cert issue

```bash
# Linux trade-core（systemd-managed）
sudo tailscale cert trade-core.tail358794.ts.net
# → /var/lib/tailscale/certs/trade-core.tail358794.ts.net.{crt,key}
# 權限：root:tailscale 0640
```

**Mac 部署**：對等命令 `sudo /Applications/Tailscale.app/.../tailscale cert <node>.tail358794.ts.net`，cert 路徑 `~/Library/Application Support/Tailscale/certs/`。Caddyfile 路徑用 env var `OPENCLAW_TLS_CERT_DIR` 抽象，per CLAUDE.md §六。

### 2.2 Renewal cadence

- **Tailscale cert 不自動續期**（per [Tailscale Issue #8204](https://github.com/tailscale/tailscale/issues/8204)）
- systemd timer **每日 03:00 UTC** check；剩餘 < 14 天 → 重發 + `systemctl reload caddy`
- Renewal 失敗 → systemd unit `OnFailure=` 觸 `notify_renewal_failure.sh` → Telegram + Grafana alert
- 證據：emit metric `openclaw_tls_cert_days_remaining`（Prometheus textfile collector），Grafana panel + 7d remaining trigger P1 alert

### 2.3 Failure mode

| 失敗類型 | 行為 | 復原 |
|---|---|---|
| Tailscale CA 中斷 | Caddy 繼續服務舊 cert 直到過期 | Tailscale 恢復後手動 `tailscale cert ...` |
| Cert 過期未察 | 瀏覽器 NET::ERR_CERT_DATE_INVALID；CLI curl 失敗 | 14d 預警未漏 = 30d cooldown；漏報 → 手動 renew + RCA |
| Caddy crash | systemd `Restart=always` 5s 內復活 | 若連續 5 次 fail → 降級 HTTP-only emergency mode（需 operator 確認解除）|
| reload 失敗 | 舊 worker 不關，新 cert 未生效 | systemd `ExecReload=caddy reload --config <file>` 校驗失敗則保留舊版 |

### 2.4 跨平台抽象（CLAUDE.md §六）

新增 helper `helper_scripts/lib/tls_cert.sh`：
```bash
# 抽象「拿到當前平台的 Tailscale cert 路徑」
resolve_openclaw_tls_cert_dir() {
    case "$(uname -s)" in
        Linux)  printf '%s\n' "${OPENCLAW_TLS_CERT_DIR:-/var/lib/tailscale/certs}" ;;
        Darwin) printf '%s\n' "${OPENCLAW_TLS_CERT_DIR:-$HOME/Library/Application Support/Tailscale/certs}" ;;
        *) echo "ERROR: unsupported platform" >&2; return 2 ;;
    esac
}
```

---

## §3 Secure Cookie

### 3.1 現況（已 land code）

`auth_routes_common.py::set_auth_cookie`（L207-225）：
- `key=oc_auth_token` + `httponly=True` + `samesite="strict"` + `max_age=86400` + `path="/"`
- Secure 由 `should_set_secure_cookie(request)` 決定（L181-204）

`should_set_secure_cookie`：
1. `OPENCLAW_COOKIE_SECURE=1/true/yes/on` → True（強制）
2. `OPENCLAW_COOKIE_SECURE=0/false/no/off` → False
3. `auto` 預設 → 看 `request.url.scheme == "https"` 或 `_has_https_proxy_hint`

### 3.2 此 spec 要求 IMPL 改

| 改動 | 位置 | 理由 |
|---|---|---|
| **Live 部署環境變數**：`OPENCLAW_COOKIE_SECURE=1`（強制 Secure）| `secrets/environment_files/basic_system_services.env` 新增；`restart_all.sh` 啟動時 assert | Live 不能依賴 `auto` 邏輯（萬一 proxy header 缺失 → cookie 仍能在 HTTP 用 = 洩漏）|
| **Live 部署環境變數**：`OPENCLAW_TRUST_PROXY_HEADERS=1` | 同上 | Caddy 會塞 `X-Forwarded-Proto: https`；現在 `_has_https_proxy_hint` 無條件讀 header（**這是潛在 spoof risk**：直連 8000 偽造 header 仍會被信任）— spec 要求 IMPL 把 `_has_https_proxy_hint` 加 env gate（沒設 `OPENCLAW_TRUST_PROXY_HEADERS=1` 就**完全不讀** proxy header），符合 docstring 原意 |
| **Bind 收緊**：Live 後 `OPENCLAW_BIND_HOST=127.0.0.1`（只 Caddy 能連）| `secrets/environment_files/basic_system_services.env` + `lib/api_bind_host.sh` 已支援 | 防止繞過 Caddy 直連 8000 偽造 proxy header |
| **SameSite=Strict 維持**（不改 Lax）| `auth_routes_common.py` 不動 | Strict 已是 CSRF 第一層；改 Lax 會放寬 |

### 3.3 LiveDemo 同 Live 標準（ADR-0004）

LiveDemo 走 Live 同套 cookie config（同 env）。不分流。

---

## §4 CSRF

### 4.1 現況評估

| 防線 | 強度 | 缺口 |
|---|---|---|
| SameSite=Strict cookie | 強（瀏覽器層阻擋 cross-site request 攜帶 cookie）| **只防瀏覽器發起**的 CSRF；不防 XSS 注入後同源偽請求；不防 subdomain takeover；不防 old browser（Safari < 13）|
| CORS allow_origins 白名單 | 中（per `main_legacy.py:271-303`，`OPENCLAW_CORS_ORIGINS` 控制）| `*` 已 strip；但若 list 留空 → 同源 only（safer default）|
| CSRF token | **缺**（grep 全 codebase 0 hit）| 無第二層；XSS 注入即可繞 |
| Rate limit | 部分（slowapi `120/min`，login 5/min）| 不防 CSRF 本身，只限頻 |

### 4.2 Token strategy 推薦

**double-submit cookie pattern**（最 minimal IMPL，不需 server-side session store）：

1. 登入成功時 `set_cookie('oc_csrf', <random_token>, httponly=False, samesite=strict, secure=true)` —— **非 HttpOnly**，讓 JS 讀
2. 前端 fetch wrapper 自動讀 `oc_csrf` cookie → 寫入 `X-CSRF-Token` header
3. FastAPI middleware（新增 `csrf_middleware.py`）對所有寫操作（POST/PUT/DELETE/PATCH）驗：
   - 必有 `X-CSRF-Token` header
   - header 值 === `oc_csrf` cookie 值（constant-time compare）
   - 不匹配 → 403 + reason_code `csrf_token_mismatch`
4. **GET / HEAD / OPTIONS 不驗**（純讀，無 side effect）
5. **白名單**：`/api/v1/healthz`、`/api/v1/login`（登入時 cookie 還沒存在）、static 路徑

**選 double-submit 不選 synchronizer token 的理由**：
- 不需要 server-side session（OpenClaw 是 stateless cookie 認證）
- IMPL 小（單 middleware + 前端 wrapper），4-6 hr
- 已 SameSite=Strict 第一層下，double-submit 第二層足夠 95% 場景

**library 推薦**：`fastapi-csrf-protect`（PyPI active；輕量）；或自寫 30 行 middleware（更可控）。Spec 偏好自寫，避免增加 deps。

### 4.3 GUI 前端改動

- 25 個 HTML/JS 文件（`static/tab-*.html` + 各 tab JS）的 fetch wrapper 統一過 helper `static/js/fetch_with_csrf.js`
- Login flow 不變（login response Set-Cookie 同時寫 `oc_auth_token` + `oc_csrf`）

### 4.4 Acceptance Criteria

- `curl -X POST` 不帶 `X-CSRF-Token` → 403
- 帶但值不匹配 cookie → 403
- 帶且匹配 → 通過（pre-CSRF 邏輯不變）
- Login endpoint exempt（保留 session-establishment）
- GET 路徑全部不受影響（regression baseline）

---

## §5 CSP unsafe-inline P2 → P1 升級路徑

### 5.1 現況

`main_legacy.py:342-350`：
```
script-src 'self' 'unsafe-inline' https://unpkg.com;
style-src 'self' 'unsafe-inline';
frame-src 'self' http://trade-core:3000;  ← 含 HTTP，CSP 升級時必同改 HTTPS
```

**blast radius**：25 個 HTML 文件含 `<script>` / `<style>` / `onclick=` inline。砍 `unsafe-inline` 需全部重構為 external JS + nonce。

### 5.2 兩階段升級

**Wave A（OPS-1 IMPL 內，必做）**：
1. `frame-src 'self' https://trade-core:3000` —— Grafana iframe 需 Grafana 自己也有 TLS；若 Grafana 暫無 HTTPS，spec 允許 Wave A 暫保 `http://trade-core:3000` + 記錄 CSP report
2. `Content-Security-Policy-Report-Only` 加 nonce-based 影子規則，**只記錄不阻擋**，蒐集 14 天 violation report 數據

**Wave B（live-gate 前 1 sprint，per TODO §12 `P2-WP05-CSP-UNSAFE-INLINE` 升 P1）**：
1. 25 個 HTML 全部把 inline `<script>` 移到 external `static/js/<tab>.js`
2. inline `<style>` 移到 external CSS
3. `onclick=` → `addEventListener`
4. 砍 `unsafe-inline`，加 `script-src 'self' 'nonce-<random>'`（per-request nonce）
5. Wave B 完成後 P2-WP05 CLOSE

**Wave B 觸發條件**：W18-21 first Live 前 2 週（D-14）。spec 在 TODO §1 列為 P1 ETA = first Live D-14。

### 5.3 CSP report-uri

新增 `POST /api/v1/csp/report` endpoint（Wave A IMPL），接 CSP violation report → 寫 `learning.csp_violation_log` 表（V### TBD，OPS-1 不開新 migration，先 stdout JSON log）。

---

## §6 Acceptance Criteria

### 6.1 Functional

| AC | 驗證 | 通過條件 |
|---|---|---|
| AC-1 TLS terminated | `curl -kI https://trade-core.tail358794.ts.net/api/v1/healthz` | HTTP 200 + 顯示 TLS 1.3 + Tailscale cert |
| AC-2 HTTP 拒絕 / 自動跳 HTTPS | `curl -I http://trade-core:8000/console`（從 tailnet 別的設備） | 308 redirect to HTTPS or 拒絕（per Caddy config）|
| AC-3 bind 127.0.0.1 | Linux `ss -tlnp \| grep 8000` | 只 listen `127.0.0.1:8000`，不 listen `100.91.109.86:8000` |
| AC-4 Secure cookie | login + 抓 Set-Cookie header | 含 `Secure; HttpOnly; SameSite=Strict` |
| AC-5 CSRF 阻擋 | `curl -X POST https://.../api/v1/governance/...` 無 token | 403 + `csrf_token_mismatch` |
| AC-6 CSRF 通過 | 正常 GUI flow | 寫操作成功（regression baseline）|
| AC-7 CSP report-only 工作 | 觸 inline script violation | CSP report endpoint 收到 JSON |
| AC-8 Cert renewal cron | `systemctl list-timers \| grep tailscale-cert` | timer enabled + 下次 fire 在 24h 內 |
| AC-9 Mac portability | spec 文件 + Caddyfile 對 launchd unit 預留 | helper script 在 Mac `uname -s == Darwin` branch 不報錯 |

### 6.2 Live boundary 不弱化（CLAUDE.md §四）

| 不變量（DOC-08 §12 9 條精選）| 此 spec 影響 | 證據 |
|---|---|---|
| Lease 必在執行前 acquired | 無 | 純 control-plane |
| Authorization 過期 → engine cancel_token shutdown | 無 | env-var path 不變 |
| Mainnet 無 `OPENCLAW_ALLOW_MAINNET` → spawn 拒絕 | 無 | 同上 |
| Operator 角色 + live_reserved 缺一即拒 | **強化** | HTTPS + Secure cookie 防身份劫持 |
| LiveDemo 不降級 | **強化** | 同 cookie / TLS 路徑 |

### 6.3 跨平台（CLAUDE.md §六）

- 無 `/home/ncyu` / `/Users/ncyu` 硬編碼於 Caddyfile / systemd unit / helper script
- TLS cert path 走 env var `OPENCLAW_TLS_CERT_DIR`
- helper `lib/tls_cert.sh` Linux + Darwin 雙分支

---

## §7 E1 IMPL Dispatch Packet

### 7.1 拆 3 個並行 E1（檔案互不重疊）

| Track | E1 | 檔案範圍 | 估時 | 依賴 |
|---|---|---|---|---|
| **A. Caddy 反代 + cert renew** | E1-A | `helper_scripts/lib/tls_cert.sh`（新）+ `helper_scripts/install_caddy.sh`（新）+ `helper_scripts/Caddyfile.template`（新）+ `systemd/openclaw-caddy.service` + `systemd/openclaw-tls-renew.{service,timer}`（新）+ `secrets/environment_files/basic_system_services.env`（加 3 env） | **10-14 hr** | 無；先 land |
| **B. CSRF middleware + 前端 wrapper** | E1-B | `app/csrf_middleware.py`（新）+ `app/main_legacy.py`（register middleware + exempt list）+ `app/static/js/fetch_with_csrf.js`（新）+ 25 個 tab HTML/JS 換 fetch wrapper + `tests/test_csrf_middleware.py`（新）| **8-12 hr** | E1-A 之後（HTTPS 起來才能測 Secure cookie 配合）|
| **C. Bind 收緊 + Cookie env 落地 + CSP report-only** | E1-C | `helper_scripts/restart_all.sh`（assert env + `OPENCLAW_BIND_HOST=127.0.0.1`）+ `app/auth_routes_common.py`（`_has_https_proxy_hint` 加 `OPENCLAW_TRUST_PROXY_HEADERS=1` gate）+ `app/main_legacy.py`（加 `Content-Security-Policy-Report-Only` header + `POST /api/v1/csp/report` endpoint）+ `tests/test_csp_report_only.py`（新）| **5-7 hr** | E1-A 之後 |

**Total E1 估時**：23-33 hr（3 並行最快 14 hr wall time）

### 7.2 風險清單（最關鍵 3 項）

| # | 風險 | 等級 | Mitigation |
|---|---|---|---|
| 1 | **Tailscale CA 中斷 + cert 過期同時發生** → GUI 不可用，operator 無法觀察 Live engine | **高** | (a) systemd timer 14d 提前 renew + 7d alert；(b) emergency fallback `OPENCLAW_BIND_HOST=auto` 環境變數可讓 operator SSH 進去改回 HTTP 直連（degraded mode，需 operator 手動觸發，不自動降級）；(c) Caddy crash → systemd 5s restart |
| 2 | **CSRF middleware 上線後既有 GUI 寫操作全 403**（25 個 HTML 漏改 fetch wrapper）| **中-高** | (a) 14d shadow mode：先 `Content-Security-Policy-Report-Only` 同款 — `X-CSRF-Token` 缺失只記 log 不阻擋；(b) E2 必查 25 個 HTML 全部過 helper；(c) E4 regression 跑所有 tab 寫操作 smoke test |
| 3 | **`_has_https_proxy_hint` env gate 改動意外讓現有 dev/test 環境 cookie 不再 Secure** → 開發機 cookie 在 HTTP 下能用，但 production 行為錯位 | **中** | (a) `OPENCLAW_TRUST_PROXY_HEADERS=1` 預設 unset = 不讀 proxy header（fail-closed）；(b) Test fixture 顯式 setenv；(c) E2 必看 `test_batch_b_security_auth.py` L120-128 兼容 |

**次要風險**（不阻 dispatch，但 E2 review 必看）：
- Grafana iframe HTTP 問題 → 若 Grafana 還沒 TLS，CSP 暫保 `http://trade-core:3000`，加 TODO entry 等 Grafana TLS
- Caddyfile reverse_proxy 對 WebSocket（FastAPI 沒用，但未來 `/ws/*` 加會卡）→ 預先在 Caddyfile 留 WS upgrade clause comment
- `slowapi` 速率限制 + Caddy 後 `client_ip` 變 `127.0.0.1` → `get_remote_address` 必須讀 `X-Forwarded-For`（已有 `_first_header_token` helper 可重用）

### 7.3 測試項

| Test ID | 類型 | 覆蓋 AC |
|---|---|---|
| `test_csrf_middleware.py::test_post_without_token_403` | unit | AC-5 |
| `test_csrf_middleware.py::test_post_with_matching_token_pass` | unit | AC-6 |
| `test_csrf_middleware.py::test_get_no_csrf_required` | unit | AC-6 regression |
| `test_csrf_middleware.py::test_login_endpoint_exempt` | unit | login flow |
| `test_csp_report_only.py::test_csp_report_endpoint_accepts_json` | unit | AC-7 |
| `tests/integration/test_tls_endpoint.sh` | integration（Linux only）| AC-1, AC-2, AC-3 |
| `tests/integration/test_cert_renewal_timer.sh` | integration（Linux only）| AC-8 |
| `tests/integration/test_mac_portability.py` | static check | AC-9（grep `/home/ncyu` / `/Users/ncyu` 在新檔 = fail）|

### 7.4 E2 重點審查 3 點

1. **`_has_https_proxy_hint` env gate 是否真的 fail-closed**：未設 `OPENCLAW_TRUST_PROXY_HEADERS=1` 時必須**完全忽略** proxy header，不是「讀但 log warning」
2. **25 個 HTML 寫操作全部過 CSRF wrapper**：grep `fetch(` / `XMLHttpRequest` in static/，每個寫操作呼叫必有 `X-CSRF-Token` 來源
3. **`secrets/environment_files/basic_system_services.env` 新增 env 不能洩漏 cert 路徑 / Tailscale token**：3 個新 env 只該是 boolean / port / bind host

### 7.5 E3 + BB security sign-off 要點

- E3：CSP regression 測 + Caddy config audit（無 `tls internal` 之類退路）
- BB：Bybit 不受 OPS-1 影響（pure control-plane），sign-off 是 NoOp 但記錄

---

## §8 Open Question（dispatch 前需 operator 拍板）

無真正 blocker；以下 3 個是 spec 假設，operator 不反對即可 dispatch：

1. **CSRF token 自寫 vs `fastapi-csrf-protect` 庫**：spec 偏好自寫（30 行 middleware，無新 deps）。若 operator 偏好用庫，E1 估時 +2 hr。
2. **Grafana HTTPS 是否 Wave A 內處理**：spec 暫定 Wave A 允許保留 `http://trade-core:3000`，Wave B 統一處理。若 operator 要求 Wave A 同步升，scope 擴 + 估時 +6 hr。
3. **Wave B（CSP unsafe-inline 清理）開始時機**：spec 列為 first Live D-14；TODO §12 已有 `P2-WP05-CSP-UNSAFE-INLINE`。確認 Sprint 排程是否能容納（25 HTML 重構 ~16-24 hr）。

---

## §9 Sign-off Sequence

1. **Operator** sign-off：方案 C（Tailnet-only）/ 3 並行 E1 拆法 / Open Question 拍板
2. **PA** dispatch 3 E1（A → B + C 並行）
3. **E1-A** land → **E1-B + E1-C** 並行
4. **E2** review（重點 3 條 §7.4）
5. **E3 + BB** security sign-off
6. **E4** regression（所有寫操作 + Mac portability static check）
7. **PM** Phase 3e sign-off
8. **TODO §12** `P2-WP05-CSP-UNSAFE-INLINE` 升級 P1 + 排 Wave B sprint

---

**Sources**:
- [Tailscale Funnel · Tailscale Docs](https://tailscale.com/docs/features/tailscale-funnel)
- [Enabling HTTPS · Tailscale Docs](https://tailscale.com/kb/1153/enabling-https)
- [HTTPS certificate renewal is based on hard-coded time until expiry · Issue #8204 · tailscale/tailscale](https://github.com/tailscale/tailscale/issues/8204)
- [Automatically regenerate Tailscale TLS certs using systemd timers](https://stfn.pl/blog/78-tailscale-certs-renew/)
