/**
 * 玄衡 · Arcane Equilibrium — Shared Utilities
 * 共享工具库：認證、API 調用、格式化、解釋模式
 */

// ─── Auth ────────────────────────────────────────────────────────────────────
// APR01-MEDIUM-13: Token moved from localStorage to HttpOnly cookie.
// Cookie is set by /api/v1/auth/login, cleared by /api/v1/auth/logout.
// JS never touches the token — browser sends the cookie automatically.
// APR01-MEDIUM-13：Token 从 localStorage 移至 HttpOnly cookie。
// Cookie 由登录端点設置，由登出端点清除。JS 永遠不碰 token，浏览器自動發送 cookie。
const OC_TOKEN_KEY = 'oc_trading_token';   // Legacy key — used only for migration cleanup
const OC_USER_KEY = 'oc_username';
const OC_DEVELOPMENT_SUPPORT_MODE_KEY = 'oc_development_support_enabled';
const OC_GUI_DEVELOPMENT_MODE_KEY = 'oc_gui_development_mode_enabled';  // Legacy key

// On load, clean up any legacy localStorage tokens (one-time migration).
// 页面載入時清理旧的 localStorage token（一次性迁移）。
(function _ocMigrateLegacyToken() {
  if (localStorage.getItem(OC_TOKEN_KEY)) {
    localStorage.removeItem(OC_TOKEN_KEY);
  }
})();

function ocAuthCheck() {
  // Async auth check: replaces blocking synchronous XHR (which froze the entire page
  // when the server was not yet ready after a restart).
  // 非同步認證檢查：取代同步 XHR（同步 XHR 在服務器重啟後未就緒時會凍結整個頁面）。
  //
  // Strategy: kick off an async fetch in the background. If the server responds
  // with 401/403, redirect immediately. If the server is not up yet (network error
  // or timeout), wait for it via waitForServerUp() before redirecting — this avoids
  // a false-positive redirect to /login while the server is still starting.
  // 策略：在背景發起 async fetch。若 401/403 立即跳轉。若服務器未就緒（網絡錯誤或超時），
  // 先等待服務器就緒再判斷，避免啟動期間誤跳轉登錄頁。
  (async function _asyncAuthCheck() {
    try {
      const ctrl = new AbortController();
      const tid = setTimeout(() => ctrl.abort(), 3000);  // 3s timeout
      const r = await fetch('/api/v1/auth/check', {
        credentials: 'same-origin',
        signal: ctrl.signal,
      });
      clearTimeout(tid);
      if (r.status === 401 || r.status === 403) {
        ocRedirectToLogin();
      }
      // 200: already authenticated, continue page load
      // other: server might be starting up, treat as auth ok for now
    } catch (e) {
      // Network error or timeout: server may still be starting.
      // Do not redirect to login — the page will handle retries via waitForServerUp().
      // 網絡錯誤或超時：服務器可能正在啟動，不跳轉登錄頁，由 waitForServerUp() 處理重試。
      console.warn('[ocAuthCheck] server not reachable, will retry:', e && e.message);
    }
  })();
  // Return true synchronously so callers that check the return value still work.
  // 同步返回 true，保持向後兼容（調用方若檢查返回值仍能正常工作）。
  return true;
}

function ocIsUnauthenticatedDetail(detail) {
  if (detail === 'Not authenticated' || detail === 'Authentication required') {
    return true;
  }
  return !!(
    detail &&
    Array.isArray(detail.reason_codes) &&
    detail.reason_codes.includes('unauthenticated')
  );
}

function ocRedirectToLogin(redirectPath) {
  const rawCurrent = redirectPath || (window.location.pathname + window.location.search) || '/';
  const currentPath = window.location.pathname || '/';
  const current = currentPath.startsWith('/static/') ? '/' : rawCurrent;
  if (window.location.pathname !== '/login') {
    sessionStorage.setItem('oc_login_redirect', current);
    window.location.href = '/login';
  }
}

async function ocHandleUnauthenticatedResponse(response, redirectPath) {
  if (!response || response.ok) return false;
  let detail = null;
  try {
    const body = await response.clone().json();
    detail = body && body.detail;
  } catch (_) { /* response body is not JSON */ }

  if (ocIsUnauthenticatedDetail(detail)) {
    ocRedirectToLogin(redirectPath);
    return true;
  }
  return false;
}

/**
 * Poll /api/v1/system/startup-status until the server is up (or timeout).
 * 輪詢 startup-status 端點，直到服務器響應（或超時）。
 *
 * Replaces the old fixed `setTimeout(callback, 2000)` pattern used in console.html sidebar.
 * The server is considered "up" as soon as any response is received from the endpoint,
 * regardless of whether background tasks (e.g. SymbolCategoryRegistry) are complete.
 *
 * @param {Function} callback - called once server is up (or timeout reached)
 * @param {number} maxWaitMs - max wait in ms before forcing callback (default 15000)
 * @param {number} intervalMs - poll interval in ms (default 400)
 */
async function waitForServerUp(callback, maxWaitMs = 15000, intervalMs = 400) {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    try {
      const ctrl = new AbortController();
      const tid = setTimeout(() => ctrl.abort(), 2000);
      const r = await fetch('/api/v1/system/startup-status', {
        credentials: 'same-origin',
        signal: ctrl.signal,
      });
      clearTimeout(tid);
      if (r.ok) {
        callback();
        return;
      }
    } catch (_) { /* server not up yet, keep polling */ }
    await new Promise(res => setTimeout(res, intervalMs));
  }
  // Timeout: call anyway (fail-open), server may have started but startup-status route not available
  // 超時後仍強制執行回調（fail-open），避免 GUI 永久等待
  console.warn('[waitForServerUp] timeout reached, proceeding anyway');
  callback();
}

function ocGetToken() {
  // DEPRECATED: Token is now in HttpOnly cookie, not accessible from JS.
  // Returns empty string. Kept for backward compatibility — callers should
  // not rely on this value. fetch() with credentials:'same-origin' sends
  // the cookie automatically.
  // 已弃用：Token 現在在 HttpOnly cookie 中，JS 無法訪问。
  // 返回空字符串。保留仅为向后兼容。
  return '';
}

async function ocLogout() {
  // OPS-1 Track B (F-1 + F-5)：logout 從 CSRF 豁免名單移除後，必須帶 X-CSRF-Token；
  // 走 window.ocFetchWithCsrf 統一注入（fetch_with_csrf.js 載入早於 common.js）。
  // 調用服務端清除 HttpOnly cookie，然后跳转登录页。
  try {
    const _fetcher = (typeof window !== 'undefined' && typeof window.ocFetchWithCsrf === 'function')
      ? window.ocFetchWithCsrf : fetch;
    await _fetcher('/api/v1/auth/logout', { method: 'POST', credentials: 'same-origin' });
  } catch (e) { /* best-effort / 尽力而为 */ }
  localStorage.removeItem(OC_USER_KEY);
  window.location.href = '/login';
}

// ─── UUID fallback (crypto.randomUUID requires Secure Context / HTTPS) ───────
function _ocUUID() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Fallback for HTTP (non-secure) contexts
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

// ─── API Helper ──────────────────────────────────────────────────────────────
let _ocAuthFails = 0;
const _OC_AUTH_MAX = 5;
const _ocGetErrorToastAt = {};
let _ocCsrfReloadScheduled = false;

function ocIsCsrfTokenMismatchDetail(detail) {
  return !!(
    detail === 'csrf_token_mismatch' ||
    (
      detail &&
      Array.isArray(detail.reason_codes) &&
      detail.reason_codes.includes('csrf_token_mismatch')
    )
  );
}

function ocScheduleCsrfTokenReload() {
  if (_ocCsrfReloadScheduled) return;
  _ocCsrfReloadScheduled = true;
  ocToast('登入安全令牌已更新，頁面即將重新整理 / Security token refreshed; reloading', 'info');
  if (typeof window !== 'undefined' && window.location && typeof window.location.reload === 'function') {
    setTimeout(() => window.location.reload(), 1200);
  }
}

async function ocApi(path, opts) {
  // Auth 由 HttpOnly cookie 處理，JS 中無需 token。
  if (_ocAuthFails >= _OC_AUTH_MAX) {
    console.warn('[ocApi] Auth lockout active (' + _ocAuthFails + ' failures). Probing...');
  }

  const method = (opts && opts.method) || 'GET';
  const toastOnError = !(opts && opts.toastOnError === false);
  const timeoutMsRaw = opts && opts.timeoutMs;
  const timeoutMsNum = Number(timeoutMsRaw);
  const timeoutMs = Number.isFinite(timeoutMsNum) && timeoutMsNum > 0 ? timeoutMsNum : 8000;
  const headers = {};
  if (opts && opts.body) headers['Content-Type'] = 'application/json';

  // OPS-1 Track B: 寫操作（POST/PUT/DELETE/PATCH）自動附 X-CSRF-Token；讀操作
  // 不附以避免污染快取 / log。token 來源 = 登入時設定的 oc_csrf cookie（非
  // HttpOnly，可被 JS 讀取）。若 cookie 不存在（尚未登入），不附 header，
  // 後端會回 403 csrf_token_mismatch — 預期行為。
  if (typeof window !== 'undefined' && typeof window.ocCsrfHeaders === 'function') {
    window.ocCsrfHeaders(method, headers);
  }

  try {
    const r = await fetch(path, {
      method: method,
      headers: headers,
      credentials: 'same-origin',  // Send HttpOnly cookie automatically / 自動發送 HttpOnly cookie
      body: opts && opts.body ? JSON.stringify(opts.body) : undefined,
      signal: AbortSignal.timeout(timeoutMs),  // 預設 8s；慢只讀面板可 opt into 較長 timeout
    });
    if (!r.ok) {
      if (await ocHandleUnauthenticatedResponse(r)) return null;
      if (r.status === 401 || r.status === 403) {
        _ocAuthFails++;
        if (_ocAuthFails >= _OC_AUTH_MAX) {
          ocToast('認證多次失敗，請重新登入 / Auth failed, please re-login', 'error');
        }
      }
      // Parse error body and show toast with real error, then return null for backward compat
      let errMsg = 'HTTP ' + r.status;
      try {
        const errBody = await r.json();
        const detail = errBody.detail;
        if (ocIsCsrfTokenMismatchDetail(detail)) {
          console.warn('[ocApi] ' + method + ' ' + path + ' → ' + r.status + ': csrf_token_mismatch');
          ocScheduleCsrfTokenReload();
          return null;
        }
        if (typeof detail === 'string') errMsg = detail;
        else if (detail && detail.reason_codes) errMsg = detail.reason_codes.join(', ');
        else if (detail) errMsg = JSON.stringify(detail);
        if (errBody.message && typeof errBody.message === 'string') errMsg = errBody.message;
      } catch (_) { /* no JSON body */ }
      console.warn('[ocApi] ' + method + ' ' + path + ' → ' + r.status + ': ' + errMsg);
      if (method === 'POST') {
        ocToast(errMsg + ' (' + r.status + ')', 'error');
      } else if (toastOnError) {
        const key = method + ':' + path.split('?')[0] + ':' + r.status;
        const now = Date.now();
        if ((now - (_ocGetErrorToastAt[key] || 0)) > 30000) {
          _ocGetErrorToastAt[key] = now;
          ocToast(errMsg + ' (' + r.status + ')', 'error');
        }
      }
      return null;
    }
    _ocAuthFails = 0;
    return await r.json();
  } catch (e) {
    const errorName = e && e.name ? String(e.name) : '';
    if (errorName === 'AbortError') {
      console.info('[ocApi] Request aborted: ' + path, e);
      return null;
    }
    console.warn('[ocApi] Network error: ' + path, e);
    if (method === 'GET' && toastOnError) {
      const key = method + ':' + path.split('?')[0] + ':network';
      const now = Date.now();
      if ((now - (_ocGetErrorToastAt[key] || 0)) > 30000) {
        _ocGetErrorToastAt[key] = now;
        ocToast('API 連線失敗 / API request failed', 'error');
      }
    }
    return null;
  }
}

async function ocPost(path, body) {
  return ocApi(path, { method: 'POST', body: body || {} });
}

// ─── Development Support Visibility ─────────────────────────────────────────
// Browser-local setting: controls whether the global development support page
// and development-only controls are visible. It never changes trading mode,
// risk config, live auth, or engine runtime.
function ocReadCachedDevelopmentSupportMode() {
  try {
    const raw = localStorage.getItem(OC_DEVELOPMENT_SUPPORT_MODE_KEY);
    if (raw !== null) return raw === '1';
    return localStorage.getItem(OC_GUI_DEVELOPMENT_MODE_KEY) === '1';
  } catch (_) {
    return false;
  }
}

function ocCacheDevelopmentSupportMode(enabled) {
  const value = !!enabled;
  try {
    localStorage.setItem(OC_DEVELOPMENT_SUPPORT_MODE_KEY, value ? '1' : '0');
    localStorage.setItem(OC_GUI_DEVELOPMENT_MODE_KEY, value ? '1' : '0');
  } catch (_) {}
  try {
    window.dispatchEvent(new CustomEvent('ocdevelopmentsupportchange', {
      detail: { enabled: value }
    }));
  } catch (_) {}
  return value;
}

async function ocFetchDevelopmentSupportMode() {
  return ocReadCachedDevelopmentSupportMode();
}

function ocListenDevelopmentSupportMode(handler) {
  if (typeof handler !== 'function') return;
  window.addEventListener('message', function(ev) {
    if (ev.origin !== window.location.origin) return;
    if (!ev.data) return;
    if (
      ev.data.type !== 'openclaw-development-support-setting' &&
      ev.data.type !== 'openclaw-development-mode-setting'
    ) return;
    handler(ocCacheDevelopmentSupportMode(!!ev.data.enabled));
  });
  window.addEventListener('ocdevelopmentsupportchange', function(ev) {
    handler(!!(ev.detail && ev.detail.enabled));
  });
}

// Backward-compatible aliases for cached console/tab HTML from the prior build.
function ocReadCachedGuiDevelopmentMode() {
  return ocReadCachedDevelopmentSupportMode();
}

function ocCacheGuiDevelopmentMode(enabled) {
  return ocCacheDevelopmentSupportMode(enabled);
}

async function ocFetchGuiDevelopmentMode() {
  return ocFetchDevelopmentSupportMode();
}

function ocListenGuiDevelopmentMode(handler) {
  return ocListenDevelopmentSupportMode(handler);
}

// ─── Request Envelope ────────────────────────────────────────────────────────
function ocEnvelope(payload, stateRevision) {
  return {
    request_id: _ocUUID(),
    idempotency_key: _ocUUID(),
    operator_id: 'demo-operator',
    reason: 'gui-triggered action',
    client_ts_ms: Date.now(),
    expected_state_revision: stateRevision || 0,
    payload: payload || {},
  };
}

// ─── Currency Toggle System ───────────────────────────────────────────────────
// Three-way toggle: USDT → USD → EUR, persisted in localStorage.
// All monetary formatters (ocMoney, ocBalance) automatically apply the active
// currency. Toggling dispatches 'occurrencychange' so tabs can re-render.
// 三選計價货币：USDT → USD → EUR，状态持久化到 localStorage。
// 所有货币格式化函數自動適配當前货币；切换時发出 'occurrencychange' 事件触发页面刷新。

const _OC_CURRENCIES = ['USDT', 'USD', 'EUR'];
let _ocCurrIdx = parseInt(localStorage.getItem('oc_curr_idx') || '0');

// Fallback rates (USDT base). Updated by ocInitFx() from live API.
// 回退汇率（USDT 基准）。由 ocInitFx() 从在線 API 實時更新。
let _ocFxRates = { USDT: 1.0, USD: 1.0, EUR: 0.92 };

function ocCurrCode() {
  // Current currency code: 'USDT', 'USD', or 'EUR'
  // 當前計價货币代码
  return _OC_CURRENCIES[_ocCurrIdx] || 'USDT';
}

function ocCurrSymbol() {
  // Display symbol for current currency: '₮', '$', or '€'
  // 當前货币顯示符號（₮ = USDT/Tether）
  const c = ocCurrCode();
  if (c === 'EUR')  return '€';
  if (c === 'USDT') return '₮';
  return '$';  // USD
}

function ocFxConvert(v) {
  // Convert a USDT value to the current display currency.
  // 将 USDT 數值转换为當前顯示货币。
  if (v == null || isNaN(v)) return v;
  return Number(v) * (_ocFxRates[ocCurrCode()] || 1.0);
}

function ocToggleCurrency() {
  // Cycle to the next currency and notify all tabs.
  // 切换到下一個計價货币，并通知所有 Tab 刷新。
  _ocCurrIdx = (_ocCurrIdx + 1) % _OC_CURRENCIES.length;
  localStorage.setItem('oc_curr_idx', String(_ocCurrIdx));
  _ocSyncCurrencyBadges();
  window.dispatchEvent(new CustomEvent('occurrencychange', { detail: { currency: ocCurrCode() } }));
}

function _ocSyncCurrencyBadges() {
  // Update all .oc-curr-badge elements to show the active currency.
  // 更新所有 .oc-curr-badge 元素以顯示當前計價货币。
  document.querySelectorAll('.oc-curr-badge').forEach(b => {
    b.textContent = ocCurrCode();
  });
}

// Cross-iframe currency sync: when parent toggles currency, localStorage changes
// fire a 'storage' event in all same-origin iframes. Re-read index and re-dispatch.
// 跨 iframe 货币同步：父页面切换货币時 localStorage 变化会触发 storage 事件，
// iframe 重新读取索引并派发 occurrencychange 以刷新顯示。
window.addEventListener('storage', function(e) {
  if (e.key === 'oc_curr_idx' && e.newValue != null) {
    const newIdx = parseInt(e.newValue);
    if (!isNaN(newIdx) && newIdx !== _ocCurrIdx) {
      _ocCurrIdx = newIdx;
      _ocSyncCurrencyBadges();
      window.dispatchEvent(new CustomEvent('occurrencychange', { detail: { currency: ocCurrCode() } }));
    }
  }
});

let _ocFxTimer = null;  // handle for the 60-second refresh loop / 60秒刷新定時器句柄

async function ocInitFx() {
  // Fetch USDT/USD and USDT/EUR rates through the same-origin backend proxy.
  // Runs once immediately, then schedules itself every 60 s via setTimeout
  // (recursive, not setInterval — avoids overlap if the fetch is slow).
  // Only dispatches 'occurrencychange' when a rate actually moves by ≥ 0.0001,
  // so tabs don't re-render every minute when rates are stable.
  //
  // 經同源後端代理获取 USDT/USD 和 USDT/EUR 汇率，避免浏览器 CSP 放寬到第三方。
  // 首次立即執行，之后每 60 秒通過 setTimeout 遞歸調度（避免 fetch 延遲导致重叠）。
  // 仅在汇率变化 ≥ 0.0001 時才派发 'occurrencychange' 事件，避免無效重渲染。
  const prev = { USD: _ocFxRates.USD, EUR: _ocFxRates.EUR };
  try {
    const d = await ocApi('/api/v1/system/fx-rates');
    const rates = d && d.data && d.data.rates;
    if (rates) {
      if (rates.USD) _ocFxRates.USD = Number(rates.USD);
      if (rates.EUR) _ocFxRates.EUR = Number(rates.EUR);
    }
  } catch (_) { /* silent fallback / 靜默回退 */ }

  _ocSyncCurrencyBadges();

  // Notify tabs only if rates actually changed (threshold 0.0001)
  // 仅汇率實際变化時通知各 Tab 刷新，避免無意义的重渲染
  const changed = Math.abs(_ocFxRates.USD - prev.USD) > 0.0001 ||
                  Math.abs(_ocFxRates.EUR - prev.EUR) > 0.0001;
  if (changed) {
    window.dispatchEvent(new CustomEvent('occurrencychange', { detail: { currency: ocCurrCode(), rateUpdate: true } }));
  }

  // Schedule next refresh in 60 s (clear any existing timer first)
  // 60 秒后調度下次刷新（先清除已有定時器）
  if (_ocFxTimer) clearTimeout(_ocFxTimer);
  _ocFxTimer = setTimeout(ocInitFx, 60_000);
}

// ─── Formatters / Chip / Strategy / PnL ──────────────────────────────────────
// 已外移至 common-formatters.js（P2-COMMON-JS-LOC §九 hygiene 拆分）。
// 包含 ocMoney / ocBalance / ocNum / ocPct / ocDate / ocTime / ocEsc /
// ocSanitizeClass / ocChip / ocStrategy* / ocCategoryTag / ocPnl* /
// ocPerformance* / ocMiniTrendSvg / ocFillTime / ocPnlClass /
// ocFirstFinite / ocPositionEntryValue / ocFillExecValue。
// 載入順序：所有 tab HTML 必須在 common.js 之前載入 common-formatters.js。

// ─── Auto Refresh ────────────────────────────────────────────────────────────
let _ocRefreshTimer = null;
let _ocRefreshFn = null;
let _ocRefreshInFlight = false;

function ocStartRefresh(fn, interval) {
  _ocRefreshFn = function() {
    if (_ocRefreshInFlight) return;
    _ocRefreshInFlight = true;
    Promise.resolve()
      .then(fn)
      .catch(e => console.warn('[ocStartRefresh] refresh failed', e))
      .finally(() => { _ocRefreshInFlight = false; });
  };
  if (_ocRefreshTimer) clearInterval(_ocRefreshTimer);
  _ocRefreshTimer = setInterval(_ocRefreshFn, interval || 15000);
}

function ocStopRefresh() {
  if (_ocRefreshTimer) { clearInterval(_ocRefreshTimer); _ocRefreshTimer = null; }
}

// ─── DOM Helpers ─────────────────────────────────────────────────────────────
function $(id) { return document.getElementById(id); }

function ocSetText(id, text) {
  const el = $(id);
  if (el) {
    const next = text != null ? String(text) : '--';
    if (el.textContent !== next) el.textContent = next;
  }
}

function ocSetHtml(id, html) {
  const el = $(id);
  if (el && el.innerHTML !== html) el.innerHTML = html;
}

function ocSetClass(id, cls) {
  const el = $(id);
  if (el) el.className = cls;
}

// ─── Section Explainer HTML Generator ────────────────────────────────────────
function ocExplain(simple, deep) {
  let html = '<div class="oc-explain">';
  html += '<p class="oc-explain-simple">' + simple + '</p>';
  if (deep) {
    html += '<details class="oc-explain-deep"><summary>了解更多 / Learn more</summary>';
    html += '<div class="oc-explain-content">' + deep + '</div></details>';
  }
  html += '</div>';
  return html;
}

// ─── Toast Notification ──────────────────────────────────────────────────────
const _ocToasts = [];
function ocToast(msg, type) {
  const toast = document.createElement('div');
  toast.className = 'oc-toast oc-toast-' + (type || 'info');
  toast.textContent = msg;
  document.body.appendChild(toast);
  _ocToasts.push(toast);
  // Position before show so offsetHeight is available after DOM insertion
  _ocRepositionToasts();
  requestAnimationFrame(() => {
    _ocRepositionToasts();
    toast.classList.add('show');
  });
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => {
      toast.remove();
      const idx = _ocToasts.indexOf(toast);
      if (idx !== -1) _ocToasts.splice(idx, 1);
      _ocRepositionToasts();
    }, 300);
  }, 3500);
}
function _ocRepositionToasts() {
  let bottom = 20;
  for (let i = _ocToasts.length - 1; i >= 0; i--) {
    _ocToasts[i].style.bottom = bottom + 'px';
    bottom += (_ocToasts[i].offsetHeight || 40) + 8;
  }
}

// ─── Persistent Residual-Risk Banner ─────────────────────────────────────────
// 為什麼需要：不可逆 Live 寫操作（停止 / 平倉 / 緊急停止 / 模式切換）部分失敗時，
// 「仍有持倉/掛單殘留，請手動確認 Bybit」這類警示若用 3.5s 自動消失的 toast 呈現，
// 受壓操作員會錯過 → 然後 refreshPage() 重繪畫面顯「一切就緒」掩蓋殘留風險。
// 本 banner 是常駐的（fixed 置頂，只能點擊關閉），且 append 到 document.body，
// 不掛在任何被 refreshPage() 重繪的容器內 → refreshPage 不會把它清掉。
// 同 actionKey 重複呼叫時更新內容而非堆疊，避免操作員連點產生多條殘留橫幅。
const _ocResidualBanners = {};
function ocResidualRiskBanner(actionKey, msg) {
  const key = ocSanitizeClass(String(actionKey || 'live')) || 'live';
  let banner = _ocResidualBanners[key];
  if (!banner || !banner.isConnected) {
    banner = document.createElement('div');
    banner.className = 'oc-residual-banner';
    banner.setAttribute('role', 'alert');
    banner.setAttribute('aria-live', 'assertive');
    // 文字節點全程 ocEsc / textContent，杜絕後端 error 字串 XSS 注入。
    const txt = document.createElement('span');
    txt.className = 'oc-residual-banner-text';
    const closeBtn = document.createElement('button');
    closeBtn.className = 'oc-residual-banner-close';
    closeBtn.type = 'button';
    closeBtn.textContent = '我已確認 · 關閉';
    closeBtn.setAttribute('aria-label', '關閉殘留風險警示');
    closeBtn.onclick = function() {
      banner.remove();
      delete _ocResidualBanners[key];
      _ocRepositionResidualBanners();
    };
    banner.appendChild(txt);
    banner.appendChild(closeBtn);
    document.body.appendChild(banner);
    _ocResidualBanners[key] = banner;
  }
  banner.querySelector('.oc-residual-banner-text').textContent = String(msg || '');
  _ocRepositionResidualBanners();
  return banner;
}
// 多條殘留橫幅垂直堆疊置頂，避免互相遮蓋。
function _ocRepositionResidualBanners() {
  let top = 12;
  Object.keys(_ocResidualBanners).forEach(function(k) {
    const b = _ocResidualBanners[k];
    if (!b || !b.isConnected) { delete _ocResidualBanners[k]; return; }
    b.style.top = top + 'px';
    top += (b.offsetHeight || 44) + 8;
  });
}

// ─── Live Mutation Classifier ────────────────────────────────────────────────
// 為什麼需要：close-all / cancel-all / emergency-stop / 全局模式切換 等寫操作的
// 後端 envelope 已在 top-level 回報 partial_failure / closed_all / status /
// rust_synced；但前端歷史上各自讀錯巢狀欄位（如 d.data.close_result.errors），
// 在「部分失敗、仍有殘留風險」時誤顯綠色成功 → fake-success 反模式。
// 本 helper 是單一真相來源：任何部分失敗 / 未同步 Rust 都歸類為 error/blocking，
// 只有完全乾淨才回 success。符合 CLAUDE.md「GUI 寫面必反映 Rust 權威，不得假成功」。
//
// P1-04（close-all / emergency-stop）、P1-17（全局模式切換）共用此 helper。
//
// 契約：傳入 ocPost / ocApi 的回傳 envelope d。Live 回應被 _live_response 包了一層
// data，真實 payload 在 d.data；control 回應有時直接平鋪在 d。兩種都兼容。
// 回傳 { severity: 'success' | 'error', message: String, residualRisk: Boolean }。

// 收集所有可能殘留風險來源的錯誤訊息（多巢狀路徑冗餘）。
function _ocCollectMutationErrors(p) {
  const out = [];
  if (!p || typeof p !== 'object') return out;
  // 平鋪 errors
  if (Array.isArray(p.errors)) out.push.apply(out, p.errors);
  // close_result.errors（close-all 平倉結果）
  if (p.close_result && Array.isArray(p.close_result.errors)) {
    out.push.apply(out, p.close_result.errors);
  }
  // orphan_sweep：清掃孤兒倉/掛單；skipped / errors 任一非空都算殘留風險
  const sweep = p.orphan_sweep;
  if (sweep && typeof sweep === 'object') {
    if (Array.isArray(sweep.errors)) out.push.apply(out, sweep.errors);
    if (Array.isArray(sweep.skipped) && sweep.skipped.length) {
      // skipped 不是純錯誤字串陣列時，標記為殘留掃描項
      sweep.skipped.forEach(function(s) {
        out.push('orphan_sweep skipped: ' + (typeof s === 'string' ? s : JSON.stringify(s)));
      });
    }
  }
  // IPC 未同步錯誤（模式切換）
  if (p.ipc_error) out.push('IPC: ' + p.ipc_error);
  // 用 String() 正規化非字串錯誤項，避免 [object Object]
  return out.map(function(e) { return (typeof e === 'string') ? e : JSON.stringify(e); });
}

function classifyLiveMutation(d) {
  // d 不存在 = ocPost 已判定非 OK（fail-closed）
  if (!d) return { severity: 'error', message: '命令失敗，請檢查引擎狀態', residualRisk: true };
  // Live 回應 payload 在 d.data；control 回應可能平鋪在 d 本身
  const p = (d.data && typeof d.data === 'object') ? d.data : d;
  if (!p || typeof p !== 'object') {
    return { severity: 'error', message: '命令回應格式異常', residualRisk: true };
  }
  // 任一旗標為「部分失敗 / 未完成 / Rust 未同步」都視為失敗（不可顯綠）
  const partial = (p.partial_failure === true) ||
                  (p.closed_all === false) ||
                  (p.status === 'partial_failure') ||
                  (p.action_result === 'partial_failure') ||
                  (p.rust_synced === false);
  const errs = _ocCollectMutationErrors(p);
  if (partial || errs.length) {
    let msg = '部分失敗，可能殘留風險';
    if (p.rust_synced === false) msg = '未同步至 Rust 引擎，狀態未確認';
    if (errs.length) msg += '：' + errs.join('; ');
    return { severity: 'error', message: msg, residualRisk: true };
  }
  return { severity: 'success', message: (p.message || '完成'), residualRisk: false };
}

// ─── Tab Page Base CSS (injected by each tab) ────────────────────────────────
function ocInjectBaseCSS() {
  if (document.getElementById('oc-base-css')) return;
  const style = document.createElement('style');
  style.id = 'oc-base-css';
  style.textContent = `
    :root {
      --bg: #0d1117; --card-bg: #161b22; --border: #30363d;
      --text: #c9d1d9; --text-dim: #8b949e; --accent: #58a6ff;
      --green: #3fb950; --red: #f85149; --yellow: #d29922; --blue: #388bfd;
      --card-radius: 10px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; background: var(--bg); color: var(--text);
      font: 13px/1.6 -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Roboto, sans-serif; }
    body { padding: 16px; overflow-y: auto; }

    /* Cards */
    .oc-card { background: var(--card-bg); border: 1px solid var(--border);
      border-radius: var(--card-radius); padding: 16px; margin-bottom: 14px; }
    .oc-card h2 { font-size: 15px; font-weight: 600; margin-bottom: 4px; }
    .oc-card h3 { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--text); }
    .oc-card .subtitle { font-size: 12px; color: var(--text-dim); margin-bottom: 12px; }

    /* Metric Row */
    .oc-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
    .oc-metric { background: var(--bg); border: 1px solid #21262d; border-radius: 8px; padding: 10px 12px; }
    .oc-metric-label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.4px; }
    .oc-metric-val { font-size: 20px; font-weight: 700; margin-top: 2px; }
    .oc-metric-sub { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
    .oc-performance-metrics { grid-template-columns: repeat(auto-fit, minmax(184px, 1fr)); align-items: stretch; }
    .oc-performance-metrics .oc-metric { min-height: 118px; display: flex; flex-direction: column; }
    .oc-performance-metrics .oc-metric-label { min-height: 42px; line-height: 1.45; display: block; }
    .oc-performance-metrics .oc-metric-val { margin-top: auto; font-size: 18px; line-height: 1.2; overflow-wrap: anywhere; }
    .oc-edge-gate-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; }
    .oc-edge-gate-card { background: var(--bg); border: 1px solid #21262d; border-radius: 8px; padding: 12px; min-height: 160px; }
    .oc-edge-gate-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
    .oc-edge-gate-title { font-size: 12px; font-weight: 700; line-height: 1.35; color: var(--text); }
    .oc-edge-gate-sub { font-size: 10px; color: var(--text-dim); margin-top: 2px; line-height: 1.35; }
    .oc-edge-gate-values { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 8px 0; }
    .oc-edge-gate-value { min-width: 0; }
    .oc-edge-gate-value .label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; line-height: 1.25; }
    .oc-edge-gate-value .value { font-size: 14px; font-weight: 700; line-height: 1.25; overflow-wrap: anywhere; }
    .oc-edge-gate-summary { color: var(--text-dim); font-size: 11px; line-height: 1.45; margin-top: 6px; }
    .oc-mini-trend { width: 100%; height: 54px; display: block; background: rgba(13,17,23,0.45); border: 1px solid #21262d; border-radius: 6px; }
    .oc-mini-trend-zero { stroke: rgba(139,148,158,0.45); stroke-width: 1; stroke-dasharray: 3 3; }
    .oc-mini-trend-empty { height: 54px; display: flex; align-items: center; justify-content: center; color: var(--text-dim); font-size: 11px; border: 1px dashed #30363d; border-radius: 6px; }
    .oc-readiness-list { border: 1px solid #21262d; border-radius: 8px; margin-top: 10px; overflow: hidden; }
    .oc-readiness-row { display: grid; grid-template-columns: minmax(120px, 1fr) auto minmax(100px, 1fr); gap: 10px; align-items: center; padding: 9px 11px; border-top: 1px solid #21262d; }
    .oc-readiness-row:first-child { border-top: none; }
    .oc-readiness-label { font-size: 12px; font-weight: 600; min-width: 0; overflow-wrap: anywhere; }
    .oc-readiness-detail { font-size: 10px; color: var(--text-dim); line-height: 1.35; }
    .oc-readiness-target { color: var(--text-dim); font-size: 11px; text-align: right; overflow-wrap: anywhere; }

    /* Status Chips */
    .oc-chip { display: inline-flex; align-items: center; gap: 5px; border-radius: 999px;
      padding: 3px 10px; font-size: 11px; font-weight: 500; border: 1px solid transparent; }
    .oc-chip-good { background: rgba(63,185,80,0.12); border-color: rgba(63,185,80,0.25); color: var(--green); }
    .oc-chip-warn { background: rgba(210,153,34,0.12); border-color: rgba(210,153,34,0.25); color: var(--yellow); }
    .oc-chip-bad { background: rgba(248,81,73,0.12); border-color: rgba(248,81,73,0.25); color: var(--red); }
    .oc-chip-neutral { background: rgba(139,148,158,0.1); border-color: rgba(139,148,158,0.2); color: var(--text-dim); }
    .oc-chip-info { background: rgba(56,139,253,0.12); border-color: rgba(56,139,253,0.25); color: var(--blue); }
    .oc-chip-live { background: rgba(168,85,247,0.12); border-color: rgba(168,85,247,0.3); color: #a855f7; }

    /* Strategy Identity Chips */
    .oc-strategy-chip { display: inline-flex; align-items: center; gap: 5px; border-radius: 999px;
      padding: 2px 8px; font-size: 11px; font-weight: 700; border: 1px solid var(--strategy-border, rgba(139,148,158,0.22));
      background: var(--strategy-bg, rgba(139,148,158,0.1)); color: var(--strategy-color, var(--text)); white-space: nowrap; }
    .oc-strategy-dot { width: 7px; height: 7px; border-radius: 999px;
      background: var(--strategy-color, var(--text-dim)); box-shadow: 0 0 0 2px var(--strategy-bg, rgba(139,148,158,0.1)); flex: 0 0 auto; }
    .oc-strategy-grid_trading, .oc-strategy-card-grid_trading { --strategy-color: #58a6ff; --strategy-bg: rgba(88,166,255,0.13); --strategy-border: rgba(88,166,255,0.34); }
    .oc-strategy-ma_crossover, .oc-strategy-card-ma_crossover { --strategy-color: #3fb950; --strategy-bg: rgba(63,185,80,0.13); --strategy-border: rgba(63,185,80,0.34); }
    .oc-strategy-bb_reversion, .oc-strategy-card-bb_reversion { --strategy-color: #a855f7; --strategy-bg: rgba(168,85,247,0.13); --strategy-border: rgba(168,85,247,0.34); }
    .oc-strategy-bb_breakout, .oc-strategy-card-bb_breakout { --strategy-color: #f78166; --strategy-bg: rgba(247,129,102,0.13); --strategy-border: rgba(247,129,102,0.36); }
    .oc-strategy-funding_arb, .oc-strategy-card-funding_arb { --strategy-color: #d29922; --strategy-bg: rgba(210,153,34,0.13); --strategy-border: rgba(210,153,34,0.34); }

    /* Colors */
    .green { color: var(--green); } .red { color: var(--red); }
    .yellow { color: var(--yellow); } .blue { color: var(--blue); }

    /* Control Bar */
    .oc-control-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      padding: 12px 16px; background: var(--card-bg); border: 1px solid var(--border);
      border-radius: var(--card-radius); margin-bottom: 14px; }
    .oc-fill-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
    .oc-fill-tabs { display: inline-flex; gap: 6px; flex-wrap: wrap; }
    .oc-fill-tab { border: 1px solid var(--border); background: var(--bg); color: var(--text-dim);
      border-radius: 6px; padding: 5px 10px; font-size: 12px; cursor: pointer; font-family: inherit; }
    .oc-fill-tab.active { border-color: var(--blue); color: var(--blue); background: rgba(56,139,253,0.12); }
    .oc-fill-pager { display: inline-flex; align-items: center; gap: 8px; color: var(--text-dim); font-size: 11px; }
    .oc-fill-summary { color: var(--text-dim); font-size: 11px; line-height: 1.4; margin: 4px 0 8px; }
    .oc-fill-table { min-width: 1080px; }
    .oc-fill-table th, .oc-fill-table td { white-space: nowrap; }
    .oc-fill-table th:nth-child(3), .oc-fill-table td:nth-child(3) { white-space: normal; min-width: 140px; }
    .oc-fill-time { white-space: nowrap; }

    /* Buttons */
    .oc-btn { padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border);
      background: var(--bg); color: var(--text); font-size: 12px; cursor: pointer;
      transition: all 0.15s; font-family: inherit; white-space: nowrap; }
    .oc-btn:hover { border-color: var(--accent); color: #fff; }
    .oc-btn:disabled { opacity: 0.35; cursor: not-allowed; }
    .oc-btn-primary { background: rgba(56,139,253,0.15); border-color: var(--blue); color: var(--blue); }
    .oc-btn-primary:hover { background: rgba(56,139,253,0.3); }
    .oc-btn-success { background: rgba(63,185,80,0.12); border-color: var(--green); color: var(--green); }
    .oc-btn-success:hover { background: rgba(63,185,80,0.25); }
    .oc-btn-warning { background: rgba(210,153,34,0.10); border-color: rgba(210,153,34,0.36); color: var(--yellow); }
    .oc-btn-warning:hover { background: rgba(210,153,34,0.22); color: #fff; }
    .oc-btn-danger { background: rgba(248,81,73,0.08); border-color: rgba(248,81,73,0.3); color: var(--red); }
    .oc-btn-danger:hover { background: rgba(248,81,73,0.2); }
    .oc-btn-critical { border-width: 2px; font-weight: 700; }
    .oc-btn-destructive { border-style: dashed; background: rgba(248,81,73,0.12); border-color: rgba(248,81,73,0.48); color: #ff7b72; font-weight: 700; }
    .oc-btn-destructive:hover { background: rgba(248,81,73,0.26); color: #fff; }
    .oc-btn-future { border-style: dashed; opacity: 0.4; cursor: default; }
    .oc-btn-future:hover { border-color: var(--border); color: var(--text); }

    /* Action risk zoning: used to separate reversible, stop, and destructive controls. */
    .oc-action-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .oc-action-cluster { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap;
      padding: 3px; border: 1px solid transparent; border-radius: 8px; }
    .oc-action-cluster-state { background: rgba(139,148,158,0.06); border-color: rgba(139,148,158,0.18); }
    .oc-action-cluster-pause { background: rgba(210,153,34,0.06); border-color: rgba(210,153,34,0.22); }
    .oc-action-cluster-stop { background: rgba(248,81,73,0.05); border-color: rgba(248,81,73,0.24); }
    .oc-action-cluster-destructive { background: rgba(248,81,73,0.10); border-color: rgba(248,81,73,0.42);
      box-shadow: inset 3px 0 0 rgba(248,81,73,0.55); }
    .oc-toolbar-danger-action, .oc-row-close-action { min-width: 72px; }
    .oc-row-close-action { padding: 2px 8px; font-size: 10px; }

    /* Tables */
    .oc-table-wrap { overflow-x: auto; margin-top: 8px; }
    .oc-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .oc-table th { text-align: left; padding: 8px 10px; color: var(--text-dim); font-weight: 500;
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.4px;
      border-bottom: 1px solid var(--border); background: rgba(13,17,23,0.5); }
    .oc-table td { padding: 8px 10px; border-bottom: 1px solid #21262d; }
    .oc-table tr:last-child td { border-bottom: none; }
    .oc-table tr:hover td { background: rgba(56,139,253,0.04); }
    .oc-table .empty-row td { text-align: center; color: var(--text-dim); padding: 20px; }

    /* Explainer */
    .oc-explain { margin-bottom: 14px; }
    .oc-explain-simple { color: var(--text-dim); font-size: 12px; line-height: 1.7;
      padding: 10px 14px; background: rgba(13,17,23,0.6); border-left: 3px solid var(--accent);
      border-radius: 0 8px 8px 0; }
    .oc-explain-deep { margin-top: 4px; }
    .oc-explain-deep summary { color: var(--accent); font-size: 11px; cursor: pointer;
      padding: 4px 14px; user-select: none; }
    .oc-explain-content { padding: 10px 14px; color: var(--text-dim); font-size: 12px; line-height: 1.7;
      background: rgba(13,17,23,0.4); border-radius: 8px; margin-top: 4px; }

    /* Collapsed Section */
    .oc-collapse { border: 1px solid #21262d; border-radius: var(--card-radius); margin-top: 10px; }
    .oc-collapse summary { cursor: pointer; padding: 10px 14px; font-size: 13px;
      color: var(--text); user-select: none; list-style: none; }
    .oc-collapse summary::-webkit-details-marker { display: none; }
    .oc-collapse summary::before { content: '\\25B6  '; font-size: 9px; color: var(--text-dim); }
    .oc-collapse[open] summary::before { content: '\\25BC  '; }
    .oc-collapse[open] summary { border-bottom: 1px solid #21262d; }
    .oc-collapse .oc-collapse-body { padding: 12px 14px; }

    /* Two-column Grid */
    .oc-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .oc-grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
    @media (max-width: 700px) {
      .oc-grid-2, .oc-grid-3 { grid-template-columns: 1fr; }
      body { padding: 8px; }
      .oc-table td, .oc-table th { padding: 6px 7px; font-size: 11px; }
      .oc-control-bar { gap: 6px; padding: 8px 10px; }
      .oc-metrics { grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); }
      .oc-performance-metrics { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
      .oc-edge-gate-values { grid-template-columns: 1fr 1fr; }
      .oc-readiness-row { grid-template-columns: 1fr; gap: 5px; }
      .oc-readiness-target { text-align: left; }
      .oc-card { padding: 12px; }
      .oc-input, .oc-select { min-width: 0; width: 100%; }
      .oc-strat-grid { grid-template-columns: 1fr; }
    }

    /* Separator */
    .oc-sep { border: none; border-top: 1px solid #21262d; margin: 14px 0; }

    /* Toast */
    .oc-toast { position: fixed; right: 20px; padding: 10px 18px;
      border-radius: 8px; font-size: 13px; z-index: 9999; transform: translateY(20px);
      opacity: 0; transition: all 0.3s; pointer-events: none; max-width: 420px; word-break: break-word; }
    .oc-toast.show { transform: translateY(0); opacity: 1; }
    .oc-toast-info { background: #1f2937; color: var(--text); border: 1px solid var(--border); }
    .oc-toast-success { background: rgba(63,185,80,0.15); color: var(--green); border: 1px solid rgba(63,185,80,0.3); }
    .oc-toast-error { background: rgba(248,81,73,0.15); color: var(--red); border: 1px solid rgba(248,81,73,0.3); }
    /* warn = 黃色「需注意」語意；之前缺此 class → 'warn' toast 退回無樣式（透明背景無邊框）。
       對應 --yellow token，與 success(綠)/error(紅)/info(灰) 視覺區分。 */
    .oc-toast-warn { background: rgba(210,153,34,0.15); color: var(--yellow); border: 1px solid rgba(210,153,34,0.4); }

    /* Persistent Residual-Risk Banner / 常駐殘留風險橫幅 — 只能點擊關閉，refreshPage 不清除 */
    .oc-residual-banner { position: fixed; left: 50%; transform: translateX(-50%);
      max-width: 720px; width: calc(100% - 24px); z-index: 10000;
      background: rgba(248,81,73,0.16); border: 1px solid var(--red); border-radius: 8px;
      padding: 12px 16px; display: flex; align-items: center; gap: 14px;
      box-shadow: 0 4px 18px rgba(0,0,0,0.5); }
    .oc-residual-banner-text { color: var(--red); font-size: 13px; font-weight: 600;
      line-height: 1.5; flex: 1; word-break: break-word; }
    .oc-residual-banner-close { background: rgba(248,81,73,0.2); border: 1px solid var(--red);
      color: var(--red); border-radius: 6px; padding: 6px 12px; font-size: 12px;
      font-weight: 600; cursor: pointer; white-space: nowrap; flex-shrink: 0; }
    .oc-residual-banner-close:hover { background: rgba(248,81,73,0.32); }

    /* Danger Zone */
    .oc-danger-zone { background: rgba(248,81,73,0.04); border: 1px solid rgba(248,81,73,0.15);
      border-radius: var(--card-radius); padding: 14px; margin-top: 14px; }
    .oc-danger-zone h3 { color: var(--red); font-size: 12px; text-transform: uppercase;
      letter-spacing: 0.5px; margin-bottom: 8px; }

    /* Form Elements */
    .oc-input { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
      color: var(--text); padding: 7px 10px; font-size: 13px; font-family: inherit; }
    .oc-input:focus { outline: none; border-color: var(--accent); }
    .oc-select { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
      color: var(--text); padding: 7px 10px; font-size: 13px; font-family: inherit; cursor: pointer; }

    /* Strategy Cards */
    .oc-strat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
    .oc-strat-card { background: var(--bg); border: 1px solid #21262d; border-radius: 8px; padding: 14px; position: relative; overflow: hidden; }
    .oc-strat-card[class*="oc-strategy-card-"] { border-color: var(--strategy-border, #21262d); box-shadow: inset 3px 0 0 var(--strategy-color, transparent); }
    .oc-strat-card .strat-header { display: flex; justify-content: flex-start; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 8px; }
    .oc-strat-card .strat-name { font-weight: 600; font-size: 14px; }
    .oc-strat-card .strat-name .oc-strategy-chip { font-size: 13px; padding: 3px 10px; }
    .oc-strat-card .strat-meta { font-size: 11px; color: var(--text-dim); margin-bottom: 10px; }
    .oc-strat-card .strat-actions { display: flex; gap: 6px; }

    /* Loading Shimmer */
    .oc-loading { color: var(--text-dim); font-size: 12px; padding: 20px; text-align: center; }

    /* Pre/Code */
    .oc-pre { background: var(--bg); border: 1px solid #21262d; border-radius: 8px;
      padding: 12px; font-size: 12px; font-family: 'SF Mono', Consolas, monospace;
      overflow: auto; max-height: 300px; white-space: pre-wrap; word-break: break-word; }

    /* Not Configured State */
    .oc-not-configured { text-align: center; padding: 40px 20px; }
    .oc-not-configured .icon { font-size: 48px; margin-bottom: 16px; opacity: 0.5; }
    .oc-not-configured h3 { font-size: 16px; margin-bottom: 8px; }
    .oc-not-configured p { color: var(--text-dim); font-size: 13px; max-width: 400px; margin: 0 auto; }

    /* Currency Toggle Badge — clickable pill showing active currency */
    /* 計價货币切换徽章 — 點擊循環切换 USDT / USD / EUR */
    .oc-curr-badge { display: inline-block; padding: 2px 9px; border-radius: 999px;
      font-size: 11px; font-weight: 600; letter-spacing: 0.3px; cursor: pointer;
      background: rgba(56,139,253,0.12); border: 1px solid rgba(56,139,253,0.3);
      color: var(--blue); user-select: none; transition: background 0.15s; }
    .oc-curr-badge:hover { background: rgba(56,139,253,0.25); }

    /* Tooltip on metric labels — shows on hover */
    .oc-metric-label[title] { cursor: help; border-bottom: 1px dotted var(--text-dim); display: inline-block; }
    .oc-performance-metrics .oc-metric-label[title] { display: block; width: fit-content; max-width: 100%; }

    /* live-metric: unified alias for tab-live.html metric cells (§6.1 CSS unification)
       live-metric 是 oc-metric 的别名，用于實盤 tab。保持视觉一致，特殊修飾词在各 tab 自定义。
       Note: mc/mc-val (console.html sidebar) is a separate narrower context — not unified. */
    .live-metrics { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
    .live-metric { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
    .live-metric.span2 { grid-column: span 2; }
    .live-metric-label { font-size: 11px; color: var(--text-dim); margin-bottom: 4px; font-weight: 500; }
    .live-metric-val { font-size: 20px; font-weight: 700; }
    .live-metric-val.large { font-size: 24px; }
    .live-metric-val.pos { color: var(--green); }
    .live-metric-val.neg { color: #f87171; }
    .live-metric-val.neutral { color: var(--text); }
    .live-metric-val.purple { color: #a855f7; }
    .live-metric-sub { font-size: 10px; color: var(--text-dim); margin-top: 2px; }

    /* Load-error state / 載入失败状态 — used by ocLoadError() */
    .oc-load-error { color: var(--red); font-size: 12px; padding: 10px 0;
      display: flex; align-items: center; gap: 8px; }
    .oc-load-error button { padding: 2px 8px; font-size: 10px; }

    /* Diff-highlight on risk form cells / 風控表單原值對比高亮 — used by §4.1 diff mode */
    .oc-diff-changed { background: rgba(210,153,34,0.12) !important;
      border-color: rgba(210,153,34,0.4) !important; }
    .oc-diff-label { font-size: 9px; color: var(--yellow); margin-top: 3px; font-style: italic; }

    /* Generic confirm modal (shared across tab iframes) / 通用确認弹窗（各 tab iframe 共用） */
    .oc-confirm-overlay { display:none; position:fixed; inset:0; z-index:5000;
      background:rgba(0,0,0,0.7); align-items:center; justify-content:center; }
    .oc-confirm-overlay.show { display:flex; }
    .oc-confirm-dialog { background:var(--card-bg,#161b22); border:1px solid rgba(248,81,73,0.4);
      border-radius:12px; padding:24px; max-width:440px; width:90%; }
    .oc-confirm-dialog h3 { color:#f85149; font-size:15px; margin-bottom:8px; }
    .oc-confirm-dialog p { font-size:13px; color:#c9d1d9; white-space:pre-line; margin-bottom:16px; line-height:1.6; }
    .oc-confirm-dialog .btn-row { display:flex; gap:8px; justify-content:flex-end; }
    .oc-prompt-label { display:block; font-size:12px; color:var(--text-dim); margin-bottom:6px; }
    .oc-prompt-input, .oc-prompt-select, .oc-prompt-textarea { width:100%; box-sizing:border-box;
      background:var(--bg,#0d1117); color:var(--text,#c9d1d9); border:1px solid var(--border,#30363d);
      border-radius:8px; padding:9px 10px; font-size:13px; margin-bottom:10px; }
    .oc-prompt-textarea { min-height:96px; resize:vertical; line-height:1.5; }
    .oc-prompt-input:focus, .oc-prompt-select:focus, .oc-prompt-textarea:focus {
      outline:2px solid var(--accent,#58a6ff); outline-offset:1px; border-color:var(--accent,#58a6ff); }
    .oc-prompt-error { min-height:16px; color:var(--red,#f85149); font-size:12px; margin-bottom:10px; }
  `;
  document.head.appendChild(style);
}

// ─── Generic Confirm Modal ────────────────────────────────────────────────────
// openConfirmModal: shared confirm dialog for tab iframes where app.js isn't loaded.
// openConfirmModal: 在 app.js 未載入的 tab iframe 中提供通用确認弹窗。
// When app.js loads in the parent context, its version overrides this one there.
// 当 app.js 在父上下文載入時，会在該上下文覆盖此版本。

// ─── Load Error Display Helper ────────────────────────────────────────────────
/**
 * Show a user-friendly load-failure state inside an element.
 * 在元素內顯示用户友好的載入失败状态（區别于無聲 -- 占位）。
 * @param {string} elementId - container element id to replace content
 * @param {string} [retryFnName] - JS function name (string) to call on retry click, e.g. 'loadAll'
 * @param {string} [msg] - optional custom message
 */
function ocLoadError(elementId, retryFnName, msg) {
  var el = document.getElementById(elementId);
  if (!el) return;
  var retryBtn = retryFnName
    ? ' <button class="oc-btn" style="padding:2px 8px;font-size:10px" onclick="' + retryFnName + '()">↺ 重試 / Retry</button>'
    : '';
  el.innerHTML = '<div class="oc-load-error">⚠ ' +
    (msg || '连接失败，請檢查引擎状态 / Connection failed — check engine') +
    retryBtn + '</div>';
}

// ─── Mode Badge Component / Modals / Disabled State Card ─────────────────────
// 已外移以維持 §九 2000 LOC 硬上限（P2-COMMON-JS-LOC hygiene 拆分）：
//   - common-mode-badge.js：4 維 inline pill mode badge（REF-20 R20-P1-U7）。
//   - common-modals.js：openConfirmModal / openPromptModal / openTypedConfirmModal
//                       + window.OpenClawDisabledStateCard（REF-20 R20-P1-U8）。
// 載入順序：common-formatters.js → common-mode-badge.js → common-modals.js → common.js
// （tab HTML 必須按此順序載入；common.js 本身仍是 entry point）。
