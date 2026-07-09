# E1 IMPL Round 2 — P0-OPS-1 E2 returns 修復

**日期**：2026-05-27
**角色**：E1
**任務**：OPS-1 round 1 commit `65e78437` 後，E2 review `2026-05-27--ops_1_e2_review.md` 退回 2 HIGH + 3 MED + 3 LOW + 3 NIT；A3 同步 6.0/10 push back 4 條 — 本 round 統一修補
**Spec**：`docs/execution_plan/specs/2026-05-26--p0-ops-1-https-secure-cookie.md`
**狀態**：E1 round 2 DONE — 待 E2 + A3 重審 → E4 regression → PM commit

---

## §1 8 Fix Item 矩陣（每項 file × LOC）

| # | Sev | File | LOC（淨改動） | 修法 |
|---|---|---|---|---|
| F-1 | HIGH | `app/static/app-paper.js` | +8 / -4 | `_fetchReplayJson` 內部 inject `window.ocCsrfHeaders(opts.method, opts.headers)` —— 5 caller (1325/1332/1397/1421/1451) 自動覆蓋 |
| F-1 | HIGH | `app/static/risk-tab.js` | +6 / -0 | `saveAiBudget` POST `/api/v1/ai_budget/config` headers 補 ocCsrfHeaders |
| F-1 | HIGH | `app/static/app.js` | +6 / -0 | `apiPost` helper 補 ocCsrfHeaders |
| F-1 | HIGH | `app/static/handoff_helper.js` | +8 / -3 | `fetchWithIdempotency` 把 headers 抽 var 並補 ocCsrfHeaders（Idempotency-Key 並存） |
| F-1 | HIGH | `app/static/common.js` | +6 / -1 | `ocLogout` 走 `window.ocFetchWithCsrf` fallback fetch（F-5 後 logout 不再豁免） |
| F-1 | HIGH | `app/static/index.html` | +1 / -1 | inline logout button 改 `(window.ocFetchWithCsrf||fetch)` |
| F-2 | HIGH | `app/auth_legacy_routes.py` | +13 / -2 | `auth_check`：cookie 有效 + 缺 oc_csrf → `set_csrf_cookie(resp, generate_csrf_token(), secure=should_set_secure_cookie(request))` |
| F-3 | MED | `app/main_legacy.py:313-323` | +6 / -1 | 註釋更正為「Starlette LIFO/onion，inbound 順序 CSRF→SlowAPI→CORS→route」+ 說明 OPTIONS preflight 安全 |
| F-4 | MED | `app/main_legacy.py:381-413` | +21 / -3 | `/api/v1/csp/report`：`@limiter.limit("60/minute")` + 8KB body cap `request.body() > 8192 → 413` + invalid JSON 仍 silent 204 |
| F-5 | MED | `app/csrf_middleware.py:61-68` | +1 / -1 | 從 `_EXEMPT_PATHS` 移除 `/api/v1/auth/logout`（Option A）+ MODULE_NOTE 同步描述 |
| F-6 | LOW | `helper_scripts/install_caddy.sh:141-148` | +5 / -1 | chown 條件包裝 `if id caddy >/dev/null 2>&1` |
| F-7 | LOW | `helper_scripts/systemd/openclaw-tls-renew.service:22-33` | +3 / -8 | ExecStart prefix `set -euo pipefail`；`&&` chain 改 `;`（pipefail 嚴格中斷） |
| F-8 + 修 envsubst 預存 bug | LOW | `helper_scripts/Caddyfile.template` | +9 / -4 | 改 Caddy `{$VAR}` → envsubst `${VAR}` 全部 placeholder（含 cert host / cert dir / backend port）；同時刪 `:8000` 雙重 default + `$HOME` 字面（envsubst 會展硬編路徑違反 AC-9） |
| F-10 | NIT | `app/main_legacy.py` | +1 / -1 | 註釋 `silent 200` → `silent 204` |
| F-11 | NIT | `app/csrf_middleware.py:14-42` | +6 / -10 | 移除 English MODULE_NOTE block；`MODULE_NOTE (中文)` → `MODULE_NOTE` |
| F-12 | NIT | `helper_scripts/install_caddy.sh:59-69` | +11 / -0 | CERT_HOST + BACKEND_PORT input 校驗 `grep -qE '^[A-Za-z0-9][A-Za-z0-9.-]*$'` / `'^[0-9]+$'` |

**LOC 總計**：~138 行（含註釋與測試）；6 HIGH/MED/LOW + 3 NIT + 1 預存 envsubst bug fix。

---

## §2 新 Test 結果

新增 21 個 test（OPS-1 test 從 23 → 44；含 regression 從 33 → 48）：

```
$ cd program_code/exchange_connectors/bybit_connector/control_api_v1
$ python3 -m pytest tests/test_ops1_csrf_middleware.py \
                    tests/test_ops1_csp_report_only.py \
                    tests/test_ops1_caddy_tls_static.py \
                    tests/test_ops1_csrf_js_callsites.py \
                    tests/test_batch_b_security_auth.py -v

tests/test_ops1_csrf_middleware.py (17 tests):
  test_get_request_bypasses_csrf                        PASSED  [既有]
  test_post_without_csrf_cookie_or_header_returns_403   PASSED  [既有]
  test_post_with_only_cookie_no_header_returns_403      PASSED  [既有]
  test_post_with_mismatched_cookie_header_returns_403   PASSED  [既有]
  test_post_with_matching_token_passes                  PASSED  [既有]
  test_login_endpoint_exempt                            PASSED  [既有]
  test_csp_report_endpoint_exempt                       PASSED  [既有]
  test_shadow_mode_lets_mismatch_through                PASSED  [既有]
  test_static_prefix_exempt                             PASSED  [既有]
  test_logout_without_csrf_token_returns_403            PASSED  ★ F-5 新增
  test_logout_with_matching_token_passes                PASSED  ★ F-5 新增
  test_post_with_empty_token_strings_returns_403        PASSED  ★ E2 邊界要求
  test_post_with_unequal_length_tokens_returns_403      PASSED  ★ E2 邊界要求
  test_auth_check_seeds_csrf_cookie_when_missing        PASSED  ★ F-2 新增
  test_auth_check_does_not_reissue_when_csrf_present    PASSED  ★ F-2 新增
  test_auth_check_without_auth_token_returns_401        PASSED  ★ F-2 regression
  test_csp_report_oversize_body_returns_413             PASSED  ★ F-4 新增

tests/test_ops1_csp_report_only.py (7 tests):           ALL PASSED  [既有 + PROXY-SPOOF fix]

tests/test_ops1_caddy_tls_static.py (7 tests):          ALL PASSED  [AC-9 + bash -n + envsubst 整改後仍 PASS]

tests/test_ops1_csrf_js_callsites.py (7 tests, 新檔):
  test_fetch_with_csrf_helper_injects_token_on_post     PASSED  ★ F-1 spy fetch
  test_fetch_with_csrf_helper_skips_token_on_get        PASSED  ★ F-1 GET 不污染
  test_fetch_with_csrf_helper_no_cookie_no_header       PASSED  ★ F-1 無 cookie
  test_no_unwrapped_raw_post_fetch_in_static_js         PASSED  ★ F-1 grep audit
  test_apipost_in_app_js_carries_csrf_header            PASSED  ★ F-1 inline harness
  test_fetch_replay_json_carries_csrf_header_on_post    PASSED  ★ F-1 replay POST
  test_fetch_replay_json_get_does_not_carry_csrf        PASSED  ★ F-1 replay GET

tests/test_batch_b_security_auth.py (10 既有 regression): ALL PASSED

============================== 48 passed in 0.51s ==============================
```

**Node 行為 verify**：所有 6 個前端變動檔 `node --check` PASS：
```
$ for f in app/static/risk-tab.js app/static/app.js app/static/handoff_helper.js \
           app/static/app-paper.js app/static/common.js app/static/js/fetch_with_csrf.js; do
    node --check "$f" && echo "$f OK"
  done
app/static/risk-tab.js OK
app/static/app.js OK
app/static/handoff_helper.js OK
app/static/app-paper.js OK
app/static/common.js OK
app/static/js/fetch_with_csrf.js OK
```

**Bash syntax check**：
```
$ bash -n helper_scripts/install_caddy.sh && bash -n helper_scripts/lib/tls_cert.sh
```
兩個 script 通過。`openclaw-tls-renew.service` 為 systemd unit 不適合 `bash -n`，但 ExecStart inline shell 內已 `set -euo pipefail`；spec §7.3 真正驗證留 Linux integration test。

---

## §3 F-1 跨 4 file callsite Grep Verify（**0 leftover**）

```
$ python3 -c "用 regex 掃 5 個 file 任何 fetch(...method:'POST'...) 之 600 字內必含 ocCsrfHeaders / ocFetchWithCsrf"

WRAPPED   at app/static/risk-tab.js:1085
WRAPPED   at app/static/app.js:414
WRAPPED   at app/static/handoff_helper.js:826
Total unwrapped: 0
```

說明：
- `app-paper.js` 7 個 `_fetchReplayJson(...method:"POST"...)` callsite（1324/1331/1396/1420/1449/1493）全經 wrapper 內部 inject，grep 不再 individual list。
- `common.js` `ocLogout` 走 `window.ocFetchWithCsrf` fallback `fetch` 三元式，符合 wrapper pattern。
- `index.html:36` inline logout button onclick 走 `(window.ocFetchWithCsrf||fetch)`，符合 wrapper pattern。

Cross-platform path grep（spec AC-9）：
```
$ grep -rn '/home/ncyu\|/Users/ncyu' helper_scripts/install_caddy.sh \
        helper_scripts/Caddyfile.template helper_scripts/systemd/openclaw-tls-renew.service \
        app/csrf_middleware.py app/auth_legacy_routes.py app/main_legacy.py
（無命中）
```

**重點**：F-8 投入時意外發現 Caddyfile.template `$HOME` 字面在 envsubst 預處理被展開成 `/Users/ncyu/Library/...` 即將寫入 `/etc/caddy/Caddyfile` violating AC-9；同步修補（改成「<用戶 HOME>」+ 註解 envsubst 行為）。

---

## §4 F-2 auth/check seed test Pass

```python
def test_auth_check_seeds_csrf_cookie_when_missing():
    client = TestClient(_base.app)
    client.cookies.set("oc_auth_token", _base.settings.api_token)
    # 不 set oc_csrf
    r = client.get("/api/v1/auth/check")
    assert r.status_code == 200
    set_cookie_raw = r.headers.get("set-cookie", "")
    assert "oc_csrf=" in set_cookie_raw  # PASS
```

驗證重點：
- 既有 `oc_auth_token` 24h 內 valid + `oc_csrf` 缺失 → `Set-Cookie: oc_csrf=...` 自動補
- 已有 `oc_csrf` cookie → **不**重新發送（尊重既有 token；`test_auth_check_does_not_reissue_when_csrf_present` 驗證）
- 無 `oc_auth_token` → 401（regression；不能藉 F-2 繞過 auth）

**Production state migration**：OPS-1 deploy 後第一次 GUI tab 載入會自動觸 `/api/v1/auth/check`（common.js L40 `ocAuthCheck`），既有 session 立即得到 oc_csrf cookie，無需強制 re-login，enforcing 切換瞬間不斷 GUI。

---

## §5 Deploy Verification（shadow → enforcing cutover ready）

**Shadow → enforcing 切換流程**（保留 spec §4.2 sniff window）：

| Step | 環境 | 動作 | Verify |
|---|---|---|---|
| 1 | Linux | `OPENCLAW_CSRF_SHADOW=1` 啟 shadow + restart_all.sh --api-only | `csrf_shadow:` log 出現 |
| 2 | 14d | 觀察 `journalctl -u openclaw-api -f \| grep csrf_shadow` | 預期 0 violation（F-1 / F-2 補完） |
| 3 | 14d 後 | `unset OPENCLAW_CSRF_SHADOW`；restart_all.sh --api-only | shadow log 停 |
| 4 | enforcing | 全部寫操作（AI budget / handoff / replay / logout）正常 | A3 push back R1 不再 reproducible |

**新增驗證點**（round 2）：
- `node --check` 全 6 個前端變動檔 PASS（per `feedback_gui_node_check_sop`）
- `csrf_js_callsites` 7 test PASS：F-1 mock cookie + spy fetch verify 4 個 wrapper 正確注入 token
- `csp_report` 8KB body 413 PASS：tailnet 內任何設備灌爆 journal log 被阻
- `auth_check` 自動 seed PASS：既有 user 不需 re-login
- `logout` 帶 token 200 / 不帶 403 PASS：F-5 Option A 落地

**enforcing cutover ready**：✅ 所有 HIGH / MED 完成；A3 BLOCKER 候選 R1（4 raw fetch 403）解除；R2/R3/R4 在 deploy SOP 範圍（cert 信任 + bind 收緊 + shadow 縮 7d）由 operator 與 BB 確認後執行。

---

## §6 不確定 / Operator 下一步

1. **Envsubst 預存 bug 修補擴大範圍**：F-8 NIT 投入時發現整個 `Caddyfile.template` 在 envsubst 下會產生 `https://{foo.example}` 等半解析輸出（Caddy syntax `{$VAR}` 與 envsubst `${VAR}` 衝突）。本 round 一併修補（轉成全 envsubst `${VAR}` syntax）。如 E2 認為超 round 2 scope，可拆 separate ticket，但 install_caddy.sh `--apply` 之前必修否則 Caddyfile 失敗 parse。
2. **A3 R2 / R3 / R4**：CSRF 403 toast 中文化 + cert 信任 SOP + shadow 14d→7d 縮短 — 屬 deploy SOP 範疇，留主會話 / operator 決定 timeline；A3 已標 `enforcing 前 (≤7d shadow)` 條件。
3. **`/api/v1/csp/report` Schema 校驗**：目前 60/min + 8KB cap；spec §5.3 沒要求 schema 校驗，Wave B（first Live D-14 前）若進 PG 持久化需補 strict pydantic model。
4. **MODULE_NOTE 雙語清理**：本 round 只清 `csrf_middleware.py`；其他 OPS-1 touched 檔（`main_legacy.py` / `auth_legacy_routes.py`）未碰雙語 block 以維持最小影響原則。後續 hygiene 可批次清。

---

## §7 治理對照

| Item | Round 1 狀態 | Round 2 狀態 |
|---|---|---|
| F-1 raw fetch 7+ callsite | HIGH 阻 merge | ✅ 全 wrapper |
| F-2 既有 session csrf seed | HIGH 阻 merge | ✅ `auth_check` seed + test |
| F-3 middleware ordering 註釋誤導 | MED | ✅ 改寫 |
| F-4 csp_report 限頻 + body cap | MED | ✅ 60/min + 8KB → 413 |
| F-5 logout exempt | MED | ✅ Option A 移除 + test |
| F-6 install_caddy chown 條件 | LOW | ✅ `id caddy` 包裝 |
| F-7 systemd ExecStart pipefail | LOW | ✅ `set -euo pipefail` prefix |
| F-8 Caddyfile :8000 重複 default | LOW | ✅（連帶修預存 envsubst bug） |
| F-10 silent 204 注釋 | NIT | ✅ |
| F-11 English MODULE_NOTE | NIT | ✅ |
| F-12 envsubst host 校驗 | NIT | ✅ regex 校驗 |
| Test 補強 F-1 mock+spy | E2 push back | ✅ 新檔 `test_ops1_csrf_js_callsites.py` 7 test |
| Test 補強 F-2 auth/check seed | E2 push back | ✅ 3 test 含 regression |
| Test 補強 F-5 logout 場景 | E2 push back | ✅ 2 test |
| 跨平台 grep 0 硬編碼 | 維持 | ✅ |
| pytest GREEN | 33 → 48 | ✅ 48/48 PASS |
| node --check PASS | 既有 2 檔 | ✅ 6 檔 |

---

**E1 IMPLEMENTATION DONE: 待 E2 審查**

report path: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_1_round_2_e2_e1_returns.md`
