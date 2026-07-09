# A3 UX 對抗性核驗 — OPS-1 HTTPS / Secure cookie / CSRF / CSP

**Owner**: A3 · **Date**: 2026-05-27 · **Verdict**: **CONDITIONAL APPROVE** 6.0/10 · **BLOCK commit**: NO (shadow mode 可過，但建議先修 4 raw fetch)

範圍：E1 IMPL 工作樹未 commit 變動（HEAD 未動）；20 HTML + 2 helper JS + 1 middleware + 2 auth/cookie + 1 Caddyfile + 7 systemd/shell。

> Reconstructed from sub-agent inline return (harness constraint).

## §1 影響檔案分類

| 類別 | 檔案 | A3 風險 |
|---|---|---|
| CSRF 插入 20 HTML | console / index / trading / tab-*（17）| 全部命中 line 7-10，common.js 前載入順序正確 |
| Cookie / Auth | auth_routes_common._proxy_headers_trusted + auth_legacy_routes login/logout + csrf_middleware HttpOnly=False | login response 同 issue oc_auth_token (HttpOnly) + oc_csrf (非 HttpOnly), SameSite=Strict + Secure |
| CSP / Report | main_legacy.py:355-403 + /api/v1/csp/report endpoint | Report-Only 14d shadow；endpoint 無 auth/origin allowlist/PG 持久化 |
| Track A 部署 | install_caddy + Caddyfile.template + lib/tls_cert + 4 systemd | Step 3 bind 127.0.0.1 → 徹底斷 Tailscale IPv4 直連 8000 fallback |
| Helper | fetch_with_csrf.js + common.js ocApi 自動補 X-CSRF-Token | 只覆蓋 ocApi，raw fetch 全漏 |

## §2 首次 operator 體驗 risk 矩陣

| Risk | 等級 | 證據 | 影響 |
|---|---|---|---|
| **R1: raw fetch 4 處 → 403 fail** | **HIGH BLOCKER 候選** | risk-tab.js:1079 AI budget; app.js:407-417 apiPost; handoff_helper.js:818; app-paper.js:694 _fetchReplayJson | enforcing 後 GUI AI budget/paper-trading/handoff/replay 全 403。Toast「csrf_token_mismatch (403)」無頭緒 |
| R2: 首次 HTTPS cert 不受信任警告 | MED | Tailscale internal CA 非系統信任 | 首次連 `https://trade-core.tail358794.ts.net/` 警告畫面；SOP §4 未提示 |
| R3: 100.x.x.x:8000 fallback 消失 | MED | OPENCLAW_BIND_HOST=127.0.0.1；lib/api_bind_host.sh:41 拒 0.0.0.0 | 既有手機書籤死連結；emergency unset+restart 才回 |
| R4: CSRF cookie 24h 與 auth cookie 24h 同步 | LOW | 兩 cookie max_age=86400 | 同期 expired → /login，行為一致 |
| R5: CSP report endpoint 無 origin / auth | LOW | main_legacy.py:384-403 stdout JSON log 無 schema | 外部 POST 灌爆 stdout log spam；tailnet 內可接受，建議補 rate limit |
| R6: index.html L36 inline logout fetch | LOW | logout 在 CSRF 豁免名單 | 安全 |
| R7: console/index/trading sync XHR /auth/check | LOW | 3 處 GET，自動跳過 CSRF | 安全 |
| R8: Shadow mode 14d 風險窗 | MED | OPENCLAW_CSRF_SHADOW=1 mismatch 只 log 不阻擋 | Sprint 4 first Live W18-21 撞期；建議 shadow ≤ 7d |
| R9: middleware ordering 注釋與行為矛盾 | LOW | main_legacy.py L317 SlowAPI 後 add CSRF → LIFO → CSRF 先執行；注釋寫「rate-limit 先擋洪流」 | 注釋與 Starlette LIFO 行為相反 |

## §3 UX checklist

- 防誤觸 ✅
- 認知負荷 ⚠（cert 警告 + 403 toast 看不懂）
- 錯誤狀態 ❌（reason_codes 全英文無修復連結）
- 一致性 ✅（20 HTML script tag 一致）
- 可審計 ⚠（CSP report log 無 trace_id）

## §4 五個 push back

1. **[BLOCKER]** enforcing 前必修 4 raw fetch 改走 ocApi 或 ocFetchWithCsrf
2. **[HIGH]** CSRF 403 toast 升級中文 + auto-reload hint（common.js ocApi 偵 csrf_token_mismatch → 顯示「會話安全令牌已過期，請重新整理頁面 F5」並 reload）
3. **[HIGH]** SOP §4 加 Step 0「首次 HTTPS cert 信任」— Tailscale CA 加系統信任或預期警告畫面
4. **[MED]** Shadow mode 縮 14d→7d + auto-check `csrf_shadow:` warning count dashboard
5. **[MED]** main_legacy.py:317 注釋與 LIFO 行為矛盾 — 修注釋或順序

## §5 Verdict：CONDITIONAL APPROVE

**Conditions**：
- **commit 前**：4 raw fetch BLOCKER push back #1 改完 + node --check PASS（或顯式接 shadow 過渡 + TODO follow-up）
- **commit 前**：push back #5 注釋/順序選邊修
- **enforcing 前 (≤7d shadow)**：push back #2/#3/#4 落地
- **commit 可進行**：CSP report endpoint R5 LOW；20 HTML 100% 正確；cookie/middleware 符合 spec

**BLOCK commit**：NO（technically shadow mode 可過）；建議先修 4 raw fetch 再一起 commit 避免 shadow 期 GUI 半 broken。

關鍵檔案：
- static/risk-tab.js:1079
- static/app.js:407-417
- static/handoff_helper.js:818-829
- static/app-paper.js:694-712
- main_legacy.py:317-323（注釋順序矛盾）

A3 UX AUDIT DONE: 6.0/10
