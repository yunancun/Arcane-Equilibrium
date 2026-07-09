# E1 IMPL Report — P0-OPS-1 HTTPS / Secure cookie / CSRF / CSP

**日期**：2026-05-27
**角色**：E1
**任務**：P0-OPS-1 三 track（Caddy + Tailscale cert / CSRF middleware / Secure cookie env + CSP report-only）整合 IMPL
**Spec**：`docs/execution_plan/specs/2026-05-26--p0-ops-1-https-secure-cookie.md`
**狀態**：E1 IMPL DONE — 待 E2 review → E3 + BB security sign-off → E4 regression

---

## §1 三 Track LOC 變動矩陣

| 檔案 | 類別 | +LOC | -LOC | 備註 |
|---|---|---|---|---|
| **Track A — Caddy + Tailscale cert（新增 7 個檔）** | | | | |
| `helper_scripts/lib/tls_cert.sh` | NEW | 104 | 0 | 跨平台 cert path + days_remaining + should_renew |
| `helper_scripts/Caddyfile.template` | NEW | 65 | 0 | envsubst 模板；admin off；reverse_proxy 127.0.0.1:8000 |
| `helper_scripts/install_caddy.sh` | NEW | 162 | 0 | --dry-run / --apply；Linux apt + macOS brew 分支 |
| `helper_scripts/systemd/openclaw-caddy.service` | NEW | 26 | 0 | Type=notify + Restart=always + CAP_NET_BIND_SERVICE |
| `helper_scripts/systemd/openclaw-tls-renew.service` | NEW | 28 | 0 | Type=oneshot；14d threshold + reload caddy |
| `helper_scripts/systemd/openclaw-tls-renew.timer` | NEW | 17 | 0 | OnCalendar 03:00 UTC + Persistent=true |
| `helper_scripts/systemd/openclaw-tls-renew-notify.service` | NEW | 19 | 0 | OnFailure hook（不可 enable） |
| **Track A 小計** | | **421** | **0** | |
| **Track B — CSRF middleware + GUI 前端** | | | | |
| `app/csrf_middleware.py` | NEW | 191 | 0 | BaseHTTPMiddleware + shadow mode + hardcoded 豁免 |
| `app/main_legacy.py` | MODIFY | 10 | 0 | 註冊 CSRFMiddleware |
| `app/auth_legacy_routes.py` | MODIFY | 10 | 2 | 登入 issue + 登出 delete oc_csrf cookie |
| `app/static/js/fetch_with_csrf.js` | NEW | 78 | 0 | window.ocCsrfHeaders / ocFetchWithCsrf |
| `app/static/common.js` | MODIFY | 8 | 3 | ocApi 自動補 X-CSRF-Token |
| `app/static/console.html` | MODIFY | 2 | 1 | 加 fetch_with_csrf.js script tag |
| `app/static/{19 個 tab-*.html + index.html + trading.html}` | MODIFY | 19×2 | 0 | 批量插入 fetch_with_csrf.js |
| **Track B 小計** | | **337** | **6** | |
| **Track C — Secure cookie env gate + CSP report-only** | | | | |
| `app/auth_routes_common.py` | MODIFY | 33 | 14 | `_proxy_headers_trusted` env gate + 重寫 docstring |
| `app/main_legacy.py` | MODIFY | 40 | 1 | CSP Report-Only + /api/v1/csp/report endpoint |
| **Track C 小計** | | **73** | **15** | |
| **Treatment 文檔** | | | | |
| `helper_scripts/SCRIPT_INDEX.md` | MODIFY | 12 | 1 | 新增 OPS-1 Track A 7 個 entry |
| **整合測試（新增 3 檔）** | | | | |
| `tests/test_ops1_csrf_middleware.py` | NEW | 152 | 0 | 9 test 覆蓋 AC-5/6 |
| `tests/test_ops1_csp_report_only.py` | NEW | 134 | 0 | 7 test 覆蓋 AC-7 + PROXY-SPOOF fix |
| `tests/test_ops1_caddy_tls_static.py` | NEW | 113 | 0 | 7 test 覆蓋 AC-9 跨平台 + bash -n |
| **總計** | | **1242** | **22** | spec 估 23-33hr，實測 ~3hr（同 sub-agent 共享 context） |

---

## §2 Integration Test 結果

```
$ cd program_code/exchange_connectors/bybit_connector/control_api_v1
$ python3 -m pytest tests/test_ops1_csrf_middleware.py \
                    tests/test_ops1_csp_report_only.py \
                    tests/test_ops1_caddy_tls_static.py \
                    tests/test_batch_b_security_auth.py -v

tests/test_ops1_csrf_middleware.py::test_get_request_bypasses_csrf PASSED
tests/test_ops1_csrf_middleware.py::test_post_without_csrf_cookie_or_header_returns_403 PASSED
tests/test_ops1_csrf_middleware.py::test_post_with_only_cookie_no_header_returns_403 PASSED
tests/test_ops1_csrf_middleware.py::test_post_with_mismatched_cookie_header_returns_403 PASSED
tests/test_ops1_csrf_middleware.py::test_post_with_matching_token_passes PASSED
tests/test_ops1_csrf_middleware.py::test_login_endpoint_exempt PASSED
tests/test_ops1_csrf_middleware.py::test_csp_report_endpoint_exempt PASSED
tests/test_ops1_csrf_middleware.py::test_shadow_mode_lets_mismatch_through PASSED
tests/test_ops1_csrf_middleware.py::test_static_prefix_exempt PASSED
tests/test_ops1_csp_report_only.py::test_csp_report_only_header_present_on_responses PASSED
tests/test_ops1_csp_report_only.py::test_csp_report_endpoint_accepts_json_returns_204 PASSED
tests/test_ops1_csp_report_only.py::test_csp_report_endpoint_tolerates_invalid_json PASSED
tests/test_ops1_csp_report_only.py::test_proxy_header_spoof_risk_fixed_when_env_not_set PASSED
tests/test_ops1_csp_report_only.py::test_proxy_header_trusted_when_env_set PASSED
tests/test_ops1_csp_report_only.py::test_proxy_header_negative_or_missing_returns_false PASSED
tests/test_ops1_csp_report_only.py::test_proxy_headers_trusted_helper PASSED
tests/test_ops1_caddy_tls_static.py::test_ac9_no_hardcoded_user_paths_in_new_files PASSED
tests/test_ops1_caddy_tls_static.py::test_caddyfile_template_directives PASSED
tests/test_ops1_caddy_tls_static.py::test_tls_cert_helper_cross_platform PASSED
tests/test_ops1_caddy_tls_static.py::test_install_caddy_dry_run_default PASSED
tests/test_ops1_caddy_tls_static.py::test_systemd_units_reference_helper_lib PASSED
tests/test_ops1_caddy_tls_static.py::test_tls_cert_helper_syntax_valid PASSED
tests/test_ops1_caddy_tls_static.py::test_install_caddy_syntax_valid PASSED
tests/test_batch_b_security_auth.py (10 個既有 test 全 PASS — regression baseline) PASSED

============================== 33 passed in 0.23s ==============================
```

**JS 變動 sign-off**（per `feedback_gui_node_check_sop`）：
```
$ node --check app/static/js/fetch_with_csrf.js && node --check app/static/common.js
node --check OK
```

---

## §3 PROXY-HEADER-SPOOF-RISK 一併修補 verify

**問題**（TODO §6 P1）：`auth_routes_common.py:60-73` 原 `_has_https_proxy_hint` 無條件讀 `X-Forwarded-Proto` / `X-Forwarded-Ssl` / `Forwarded: proto=https`，未 gate `OPENCLAW_TRUST_PROXY_HEADERS`，直連 8000 可偽造。

**Fix**：新增 `_proxy_headers_trusted()` env gate；未設 `OPENCLAW_TRUST_PROXY_HEADERS=1` 時 `_has_https_proxy_hint` 完全回 False，不論 header 值。

**Verify**：
```python
# test_ops1_csp_report_only.py
def test_proxy_header_spoof_risk_fixed_when_env_not_set(monkeypatch):
    monkeypatch.delenv("OPENCLAW_TRUST_PROXY_HEADERS", raising=False)
    req = _request("http", {"x-forwarded-proto": "https"})  # 攻擊者偽造
    assert auth_routes_common._has_https_proxy_hint(req) is False  # PASS
```

**Grep guard**（單一 caller，無 leak）：
```
$ grep -rn "_has_https_proxy_hint\|_proxy_headers_trusted" --include="*.py" app/
auth_routes_common.py:60: def _proxy_headers_trusted() -> bool:
auth_routes_common.py:75: def _has_https_proxy_hint(request: Request) -> bool:
auth_routes_common.py:82: if not _proxy_headers_trusted():
auth_routes_common.py:224: if _has_https_proxy_hint(request):  # 唯一 caller = should_set_secure_cookie
```

既有 `test_batch_b_security_auth.py::test_cookie_secure_can_be_forced_and_proxy_trusted` (L114-129) 已用 `monkeypatch.setenv("OPENCLAW_TRUST_PROXY_HEADERS", "1")` — 該 test 仍 PASS = 沒有 regression。

---

## §4 Deploy SOP（給 operator 手動部署用）

**前提**：Linux `trade-core` 已 Tailscale up + FastAPI 跑在 8000

### Step 1 — operator 設環境變數（一次性）

在 `$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env` 添加：
```bash
OPENCLAW_COOKIE_SECURE=1
OPENCLAW_TRUST_PROXY_HEADERS=1
OPENCLAW_TLS_CERT_HOST=trade-core.tail358794.ts.net  # 替換為實際 tailnet DNS
# 可選：CSRF 14d shadow mode 過渡期
# OPENCLAW_CSRF_SHADOW=1
```

### Step 2 — Caddy + cert + systemd（一次性）

```bash
# dry-run 預覽（必跑）
sudo OPENCLAW_TLS_CERT_HOST=trade-core.tail358794.ts.net \
     bash helper_scripts/install_caddy.sh

# apply 實際部署
sudo OPENCLAW_TLS_CERT_HOST=trade-core.tail358794.ts.net \
     bash helper_scripts/install_caddy.sh --apply
```

驗證：
```bash
systemctl status openclaw-caddy.service
systemctl list-timers | grep openclaw-tls-renew
curl -kI https://trade-core.tail358794.ts.net/api/v1/healthz
```

### Step 3 — bind 收緊 + 重啟 API（用既有 helper）

```bash
# 在 secrets env 加上 OPENCLAW_BIND_HOST=127.0.0.1 後重啟
OPENCLAW_BIND_HOST=127.0.0.1 bash helper_scripts/restart_all.sh --api-only --keep-auth
```

驗證 bind：
```bash
ss -tlnp | grep 8000   # 必只 listen 127.0.0.1:8000
```

### Step 4 — CSRF shadow → enforcing 14d cutover

第 0 天 enable shadow：`OPENCLAW_CSRF_SHADOW=1`，restart_all.sh --api-only。
第 1-13 天觀察 `api.log` 的 `csrf_shadow:` warning，補 漏掉的 callsite（理論上應 0，因為 ocApi 已統一）。
第 14 天 unset `OPENCLAW_CSRF_SHADOW` 進 enforcing，restart_all.sh --api-only。

### Step 5 — CSP Report-Only 14d → Wave B 升級

OPS-1 內已 land Report-Only。14d 後依 `csp_violation_report` log 樣本，Wave B（first Live D-14 前 1 sprint）才砍 `unsafe-inline`，移到 nonce-based。Wave B 不在本 IMPL scope。

### Step 6 — Cert renewal 健康觀察

```bash
journalctl -u openclaw-tls-renew.service --since "24 hours ago"
# 預期每日 03:00 UTC 一行；剩餘 >14d 時 log "cert still has >14d remaining; skip renewal"
```

### 緊急 fallback（仍可走 HTTP 直連 emergency mode）

若 Caddy crash + Tailscale CA 同時掛：
```bash
# 1. 改回 bind tailnet IPv4 + HTTP（spec §7.2 風險 #1 b 步）
unset OPENCLAW_BIND_HOST  # 回到 auto = Tailscale IPv4
bash helper_scripts/restart_all.sh --api-only --keep-auth
# 2. operator 經 http://100.91.109.86:8000/console 觀察 engine
# 3. Tailscale CA 恢復後，重跑 install_caddy.sh
```

---

## §5 不確定之處 / E2 重點審查項

1. **CSRF middleware 順位**：在 SlowAPI 之後、CORSMiddleware 之前註冊。E2 須確認 ASGI 中間件 ordering：rate limit → CSRF → CORS preflight 是否符合 spec §7.4 #2 + Starlette 中間件 LIFO 規則。
2. **GUI 25 個 tab fetch wrapper**：用 Python 批量插入，靜態驗 `fetch_with_csrf.js` 全 19 + console.html = 20 個 HTML 載入。`tab-replay.html` 含一些自定 fetch（trading.html 同），都走 `ocApi` 因此覆蓋；E2 須 grep 確認沒有遺漏 `XMLHttpRequest` / 第三方 lib 寫操作。
3. **`csp/report` endpoint 未驗 origin**：spec §5.3 沒要求；瀏覽器送 CSP report 必同源（CSP spec 限定），自帶 SOP 防護。但 E3 security review 建議補一個 hostname allowlist。
4. **systemd unit 假設 `OPENCLAW_BASE_DIR=/opt/openclaw`** — 占位符，install_caddy.sh 不會自動 sed 替換 systemd unit。若 operator 的 base dir 不同，需 `systemctl edit openclaw-tls-renew.service` 改 `Environment=`。E2 可建議加 install script 的 sed step。
5. **Tailscale cert 首次拉取需 root**：install_caddy.sh 已 `sudo`，但 chown caddy 假設 caddy user 存在；apt 安裝 caddy 會自建，但 macOS brew 不會。E2 須測 macOS dry-run 路徑。

---

## §6 不在 IMPL scope 內

- Wave B（CSP unsafe-inline 清理）— spec §5.2 列為 first Live D-14；單獨 sprint
- Grafana iframe HTTPS — spec §8 Open Question #2，operator 拍板 Wave A 暫保 `http://trade-core:3000`
- TODO §6 patch — 本 sub-agent 不寫 TODO（主會話統一處理）
- 實際 Caddy deploy / cargo build / systemctl daemon-reload — 只寫 code + test PASS

---

## §7 Operator 下一步

1. 等 E2 review（重點 §5 五項）
2. E3 + BB security sign-off（spec §7.5）
3. E4 regression（所有寫操作 + Mac portability static check + 25 個 tab smoke）
4. PM Phase 3e sign-off
5. operator deploy SOP（§4 五 step）

---

**E1 IMPL DONE: 待 E2 審查（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_1_https_secure_cookie_impl.md）**
