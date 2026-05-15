/**
 * 玄衡 · Arcane Equilibrium — Shared Utilities
 * 共享工具库：认证、API 调用、格式化、解释模式
 */

// ─── Auth ────────────────────────────────────────────────────────────────────
// APR01-MEDIUM-13: Token moved from localStorage to HttpOnly cookie.
// Cookie is set by /api/v1/auth/login, cleared by /api/v1/auth/logout.
// JS never touches the token — browser sends the cookie automatically.
// APR01-MEDIUM-13：Token 从 localStorage 移至 HttpOnly cookie。
// Cookie 由登录端点设置，由登出端点清除。JS 永远不碰 token，浏览器自动发送 cookie。
const OC_TOKEN_KEY = 'oc_trading_token';   // Legacy key — used only for migration cleanup
const OC_USER_KEY = 'oc_username';
const OC_DEVELOPMENT_SUPPORT_MODE_KEY = 'oc_development_support_enabled';
const OC_GUI_DEVELOPMENT_MODE_KEY = 'oc_gui_development_mode_enabled';  // Legacy key

// On load, clean up any legacy localStorage tokens (one-time migration).
// 页面加载时清理旧的 localStorage token（一次性迁移）。
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
  // 已弃用：Token 现在在 HttpOnly cookie 中，JS 无法访问。
  // 返回空字符串。保留仅为向后兼容。
  return '';
}

async function ocLogout() {
  // Call server to clear the HttpOnly cookie, then redirect to login.
  // 调用服务端清除 HttpOnly cookie，然后跳转登录页。
  try {
    await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'same-origin' });
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

async function ocApi(path, opts) {
  // Auth is handled by HttpOnly cookie — no token in JS needed.
  // 认证由 HttpOnly cookie 处理，JS 中无需 token。
  if (_ocAuthFails >= _OC_AUTH_MAX) {
    console.warn('[ocApi] Auth lockout active (' + _ocAuthFails + ' failures). Probing...');
  }

  const method = (opts && opts.method) || 'GET';
  const headers = {};
  if (opts && opts.body) headers['Content-Type'] = 'application/json';

  try {
    const r = await fetch(path, {
      method: method,
      headers: headers,
      credentials: 'same-origin',  // Send HttpOnly cookie automatically / 自动发送 HttpOnly cookie
      body: opts && opts.body ? JSON.stringify(opts.body) : undefined,
      signal: AbortSignal.timeout(8000),  // 8s timeout prevents GUI freeze on slow API / 8 秒超时防止 API 慢时 GUI 卡死
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
        if (typeof detail === 'string') errMsg = detail;
        else if (detail && detail.reason_codes) errMsg = detail.reason_codes.join(', ');
        else if (detail) errMsg = JSON.stringify(detail);
        if (errBody.message && typeof errBody.message === 'string') errMsg = errBody.message;
      } catch (_) { /* no JSON body */ }
      console.warn('[ocApi] ' + method + ' ' + path + ' → ' + r.status + ': ' + errMsg);
      if (method === 'POST') ocToast(errMsg + ' (' + r.status + ')', 'error');
      return null;
    }
    _ocAuthFails = 0;
    return await r.json();
  } catch (e) {
    console.warn('[ocApi] Network error: ' + path, e);
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
// 三选计价货币：USDT → USD → EUR，状态持久化到 localStorage。
// 所有货币格式化函数自动适配当前货币；切换时发出 'occurrencychange' 事件触发页面刷新。

const _OC_CURRENCIES = ['USDT', 'USD', 'EUR'];
let _ocCurrIdx = parseInt(localStorage.getItem('oc_curr_idx') || '0');

// Fallback rates (USDT base). Updated by ocInitFx() from live API.
// 回退汇率（USDT 基准）。由 ocInitFx() 从在线 API 实时更新。
let _ocFxRates = { USDT: 1.0, USD: 1.0, EUR: 0.92 };

function ocCurrCode() {
  // Current currency code: 'USDT', 'USD', or 'EUR'
  // 当前计价货币代码
  return _OC_CURRENCIES[_ocCurrIdx] || 'USDT';
}

function ocCurrSymbol() {
  // Display symbol for current currency: '₮', '$', or '€'
  // 当前货币显示符号（₮ = USDT/Tether）
  const c = ocCurrCode();
  if (c === 'EUR')  return '€';
  if (c === 'USDT') return '₮';
  return '$';  // USD
}

function ocFxConvert(v) {
  // Convert a USDT value to the current display currency.
  // 将 USDT 数值转换为当前显示货币。
  if (v == null || isNaN(v)) return v;
  return Number(v) * (_ocFxRates[ocCurrCode()] || 1.0);
}

function ocToggleCurrency() {
  // Cycle to the next currency and notify all tabs.
  // 切换到下一个计价货币，并通知所有 Tab 刷新。
  _ocCurrIdx = (_ocCurrIdx + 1) % _OC_CURRENCIES.length;
  localStorage.setItem('oc_curr_idx', String(_ocCurrIdx));
  _ocSyncCurrencyBadges();
  window.dispatchEvent(new CustomEvent('occurrencychange', { detail: { currency: ocCurrCode() } }));
}

function _ocSyncCurrencyBadges() {
  // Update all .oc-curr-badge elements to show the active currency.
  // 更新所有 .oc-curr-badge 元素以显示当前计价货币。
  document.querySelectorAll('.oc-curr-badge').forEach(b => {
    b.textContent = ocCurrCode();
  });
}

// Cross-iframe currency sync: when parent toggles currency, localStorage changes
// fire a 'storage' event in all same-origin iframes. Re-read index and re-dispatch.
// 跨 iframe 货币同步：父页面切换货币时 localStorage 变化会触发 storage 事件，
// iframe 重新读取索引并派发 occurrencychange 以刷新显示。
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

let _ocFxTimer = null;  // handle for the 60-second refresh loop / 60秒刷新定时器句柄

async function ocInitFx() {
  // Fetch real-time USDT/USD and USDT/EUR rates from CoinGecko (free, no key).
  // Runs once immediately, then schedules itself every 60 s via setTimeout
  // (recursive, not setInterval — avoids overlap if the fetch is slow).
  // Only dispatches 'occurrencychange' when a rate actually moves by ≥ 0.0001,
  // so tabs don't re-render every minute when rates are stable.
  //
  // 从 CoinGecko 获取实时 USDT/USD 和 USDT/EUR 汇率（免费，无需 API Key）。
  // 首次立即执行，之后每 60 秒通过 setTimeout 递归调度（避免 fetch 延迟导致重叠）。
  // 仅在汇率变化 ≥ 0.0001 时才派发 'occurrencychange' 事件，避免无效重渲染。
  const prev = { USD: _ocFxRates.USD, EUR: _ocFxRates.EUR };
  try {
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), 6000);
    const r = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=usd,eur',
      { signal: ctrl.signal }
    );
    clearTimeout(tid);
    if (r.ok) {
      const d = await r.json();
      const t = d && d.tether;
      if (t) {
        if (t.usd) _ocFxRates.USD = Number(t.usd);
        if (t.eur) _ocFxRates.EUR = Number(t.eur);
      }
    }
  } catch (_) { /* silent fallback / 静默回退 */ }

  _ocSyncCurrencyBadges();

  // Notify tabs only if rates actually changed (threshold 0.0001)
  // 仅汇率实际变化时通知各 Tab 刷新，避免无意义的重渲染
  const changed = Math.abs(_ocFxRates.USD - prev.USD) > 0.0001 ||
                  Math.abs(_ocFxRates.EUR - prev.EUR) > 0.0001;
  if (changed) {
    window.dispatchEvent(new CustomEvent('occurrencychange', { detail: { currency: ocCurrCode(), rateUpdate: true } }));
  }

  // Schedule next refresh in 60 s (clear any existing timer first)
  // 60 秒后调度下次刷新（先清除已有定时器）
  if (_ocFxTimer) clearTimeout(_ocFxTimer);
  _ocFxTimer = setTimeout(ocInitFx, 60_000);
}

// ─── Formatters ──────────────────────────────────────────────────────────────
function ocMoney(v, decimals) {
  // PnL display: converts to active currency, adds +/- prefix.
  // Example: ocMoney(100) → "+USDT 100.00" / "+$100.00" / "+€92.00"
  // PnL 显示：转换为当前货币，添加 +/- 前缀。
  if (v == null || isNaN(v)) return '--';
  const d = decimals != null ? decimals : 2;
  const converted = ocFxConvert(Number(v));
  const prefix = converted >= 0 ? '+' : '-';
  return prefix + ocCurrSymbol() + Math.abs(converted).toFixed(d);
}

function ocBalance(v, decimals) {
  // Balance display: converts to active currency, no +/- prefix.
  // Example: ocBalance(9994) → "USDT 9994.00" / "$9994.00" / "€9194.48"
  // 余额显示：转换为当前货币，无 +/- 前缀。
  if (v == null || isNaN(v)) return '--';
  const d = decimals != null ? decimals : 2;
  const converted = ocFxConvert(Number(v));
  return ocCurrSymbol() + converted.toFixed(d);
}

function ocNum(v, decimals) {
  if (v == null || isNaN(v)) return '--';
  return Number(v).toFixed(decimals != null ? decimals : 2);
}

function ocFirstFinite(obj, keys) {
  if (!obj || !Array.isArray(keys)) return null;
  for (const k of keys) {
    const raw = obj[k];
    if (raw == null || raw === '') continue;
    const n = Number(raw);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function ocPositionEntryValue(pos) {
  // Position entry notional. Prefer exchange-provided value for Bybit
  // LiveDemo/Mainnet rows; otherwise fall back to current qty * entry price.
  // 持倉開倉名義金額。Bybit 行優先用 positionValue，否則用當前數量 * 開倉均價。
  const direct = ocFirstFinite(pos, ['positionValue', 'position_value', 'entry_value', 'entryValue']);
  if (direct != null && direct > 0) return direct;
  const qty = ocFirstFinite(pos, ['size', 'qty', 'position_qty', 'positionQty']);
  const entry = ocFirstFinite(pos, ['avgPrice', 'avg_price', 'avg_entry_price', 'entry_price']);
  const absQty = qty == null ? null : Math.abs(qty);
  if (absQty != null && entry != null && absQty > 0 && entry > 0) return absQty * entry;
  return null;
}

function ocFillExecValue(fill) {
  // Execution notional. Bybit exposes execValue; DB / engine fallback rows can
  // be computed from qty * price.
  // 成交名義金額。Bybit 有 execValue；DB/engine 備援列用 qty * price 回推。
  const direct = ocFirstFinite(fill, [
    'execValue', 'exec_value', 'executed_value', 'cumExecValue', 'cum_exec_value',
    'notional', 'trade_value',
  ]);
  if (direct != null && direct > 0) return direct;
  const qty = ocFirstFinite(fill, ['execQty', 'exec_qty', 'qty', 'fill_qty']);
  const price = ocFirstFinite(fill, ['execPrice', 'exec_price', 'price', 'fill_price']);
  const absQty = qty == null ? null : Math.abs(qty);
  if (absQty != null && price != null && absQty > 0 && price > 0) return absQty * price;
  return null;
}

function ocAmount(v, decimals) {
  if (v == null || isNaN(v) || Number(v) <= 0) return '--';
  const abs = Math.abs(Number(v));
  const d = decimals != null ? decimals : (abs > 0 && abs < 0.01 ? 4 : 2);
  return ocBalance(v, d);
}

function ocPct(v) {
  if (v == null || isNaN(v)) return '--';
  return (v * 100).toFixed(1) + '%';
}

function ocDate(ts) {
  if (ts == null || ts === '') return null;
  const raw = typeof ts === 'string' ? ts.trim() : ts;
  if (raw === '') return null;
  const n = typeof raw === 'number' ? raw : Number(raw);
  const d = Number.isFinite(n) ? new Date(n > 1e12 ? n : n * 1000) : new Date(raw);
  return Number.isFinite(d.getTime()) ? d : null;
}

function ocTime(ts) { const d = ocDate(ts); return d ? d.toLocaleString('zh-CN', { hour12: false }) : '--'; }
function ocTimeShort(ts) { const d = ocDate(ts); return d ? d.toLocaleTimeString('zh-CN', { hour12: false }) : '--'; }

function ocFillTime(ts) {
  const d = ocDate(ts);
  if (!d) return '--';
  const p = n => String(n).padStart(2, '0');
  let tz = '';
  try { const t = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(d).find(x => x.type === 'timeZoneName'); tz = t ? t.value : ''; } catch (_) {}
  return p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ' UTC (local: ' + p(d.getHours()) + ':' + p(d.getMinutes()) + (tz ? ' ' + tz : '') + ')';
}

function ocPnlClass(v) {
  if (v == null) return '';
  return v >= 0 ? 'green' : 'red';
}

// Canonical backend performance metric helpers shared by Demo/Paper/Live.
// Demo/Paper/Live 共用的後端 canonical performance metric 輔助函式。
function ocPerformanceMetricByKey(metrics, key) {
  if (!Array.isArray(metrics)) return null;
  return metrics.find(m => m && m.key === key) || null;
}

// Return a metric value by key for compact status cards.
// 依 key 回傳 metric value，供小型狀態卡使用。
function ocPerformanceMetricValue(metrics, key) {
  const metric = ocPerformanceMetricByKey(metrics, key);
  return metric ? metric.value : null;
}

// Choose canonical metrics from an API payload; empty legacy arrays must fall back to DB truth.
// 從 API payload 選 canonical metrics；空 legacy 陣列必須回落到 DB truth。
function ocPerformanceMetricsFromPayload(payload) {
  if (Array.isArray(payload)) return payload;
  const top = payload && Array.isArray(payload.performance_metrics) ? payload.performance_metrics : null;
  const dbMetrics = payload && payload.db_true_metrics && Array.isArray(payload.db_true_metrics.performance_metrics)
    ? payload.db_true_metrics.performance_metrics : null;
  if (top && top.length > 0) return top;
  if (dbMetrics && dbMetrics.length > 0) return dbMetrics;
  return top || dbMetrics || [];
}

// Format backend metric descriptors without each tab duplicating unit logic.
// 格式化後端 metric 描述，避免各 tab 重複實作單位邏輯。
function ocFormatPerformanceMetric(metric) {
  if (!metric) return '--';
  const value = metric.value;
  if (value == null || value === '') return '--';
  if (value === 'inf') return '∞';
  const unit = String(metric.unit || '');
  const n = Number(value);
  if (!Number.isFinite(n)) return '--';
  if (unit === 'count') return String(Math.round(n));
  if (unit === 'money' || unit === 'usdt') return ocMoney(n);
  if (unit === 'money_abs') return ocBalance(n, 4);
  if (unit === 'bps') return n.toFixed(2) + ' bps';
  if (unit === 'rate') return (n * 100).toFixed(1) + '%';
  if (unit === 'percent') return n.toFixed(2) + '%';
  if (unit === 'ratio') return ocNum(n, 2);
  if (unit === 'seconds') {
    if (n >= 3600) return (n / 3600).toFixed(1) + ' h';
    if (n >= 60) return (n / 60).toFixed(1) + ' min';
    return Math.round(n) + ' sec';
  }
  return ocNum(n, 2);
}

// Apply positive/negative coloring only to explicit PnL-polarity metrics.
// 僅對明確標記為 PnL polarity 的 metric 套用正負色。
function ocPerformanceMetricClass(metric) {
  if (!metric || metric.polarity !== 'pnl') return '';
  const n = Number(metric.value);
  if (!Number.isFinite(n) || n === 0) return '';
  return n > 0 ? 'green' : 'red';
}

// Render the canonical performance metric grid.
// 渲染 canonical performance metric grid。
function ocRenderPerformanceMetrics(metrics) {
  if (!Array.isArray(metrics) || metrics.length === 0) {
    return '<div class="oc-loading">暂无指标数据</div>';
  }
  return metrics.map(metric => {
    const key = ocEsc(metric.key || '');
    const label = ocEsc(metric.label || metric.key || '--');
    const tooltip = ocEsc(metric.tooltip_zh || '');
    const source = ocEsc(metric.source || '');
    const cls = ocPerformanceMetricClass(metric);
    const value = ocEsc(ocFormatPerformanceMetric(metric));
    return '<div class="oc-metric oc-perf-metric" data-metric-key="' + key + '" data-source="' + source + '">' +
      '<div class="oc-metric-label" title="' + tooltip + '">' + label + '</div>' +
      '<div class="oc-metric-val ' + cls + '">' + value + '</div>' +
    '</div>';
  }).join('');
}

// Render a compact inline sparkline for dashboard gate trends.
// 渲染 dashboard gate 趨勢使用的小型 inline sparkline。
function ocMiniTrendSvg(values, opts) {
  var nums = Array.isArray(values)
    ? values.map(function(v) { return Number(v); }).filter(function(v) { return Number.isFinite(v); })
    : [];
  if (nums.length < 2) {
    return '<div class="oc-mini-trend-empty">collecting trend</div>';
  }
  opts = opts || {};
  var width = Number(opts.width || 180);
  var height = Number(opts.height || 54);
  var pad = Number(opts.pad || 5);
  var minV = Math.min.apply(null, nums);
  var maxV = Math.max.apply(null, nums);
  if (opts.includeZero) {
    minV = Math.min(minV, 0);
    maxV = Math.max(maxV, 0);
  }
  var span = maxV - minV;
  if (span <= 0) span = 1;
  var usableW = width - pad * 2;
  var usableH = height - pad * 2;
  var points = nums.map(function(v, i) {
    var x = nums.length === 1 ? width / 2 : pad + (i / (nums.length - 1)) * usableW;
    var y = pad + (1 - ((v - minV) / span)) * usableH;
    return x.toFixed(1) + ',' + y.toFixed(1);
  }).join(' ');
  var tone = opts.tone || 'info';
  var stroke = tone === 'good' ? 'var(--green)'
             : tone === 'bad' ? 'var(--red)'
             : tone === 'warn' ? 'var(--yellow)'
             : 'var(--blue)';
  var zeroLine = '';
  if (opts.includeZero && minV < 0 && maxV > 0) {
    var zy = pad + (1 - ((0 - minV) / span)) * usableH;
    zeroLine = '<line x1="' + pad + '" y1="' + zy.toFixed(1) + '" x2="' + (width - pad) +
      '" y2="' + zy.toFixed(1) + '" class="oc-mini-trend-zero" />';
  }
  return '<svg class="oc-mini-trend" viewBox="0 0 ' + width + ' ' + height +
    '" preserveAspectRatio="none" aria-hidden="true">' + zeroLine +
    '<polyline points="' + points + '" fill="none" stroke="' + stroke +
    '" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />' +
    '</svg>';
}

// ─── Status Chip HTML ────────────────────────────────────────────────────────
function ocChip(text, type) {
  // type: good, warn, bad, neutral, info
  return '<span class="oc-chip oc-chip-' + (type || 'neutral') + '">' + ocEsc(text) + '</span>';
}

// ─── Escape HTML ─────────────────────────────────────────────────────────────
function ocEsc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ─── Sanitize CSS class name (P2-NEW-6) ─────────────────────────────────────
// Only allow letters, digits, hyphens, underscores — strip everything else.
// 僅允許字母、數字、連字符、底線，其餘字符全部過濾。
function ocSanitizeClass(s) {
  if (s == null) return '';
  return String(s).replace(/[^a-zA-Z0-9\-_]/g, '');
}

// ─── Strategy Identity Color / 策略身份顏色 ─────────────────────────────────
// Shared by Strategy, Demo, and Live so one strategy keeps the same color everywhere.
const OC_STRATEGY_COLOR_META = {
  grid_trading: { label: 'grid_trading', zh: '网格', color: '#58a6ff' },
  ma_crossover: { label: 'ma_crossover', zh: '均线', color: '#3fb950' },
  bb_reversion: { label: 'bb_reversion', zh: '回归', color: '#a855f7' },
  bb_breakout: { label: 'bb_breakout', zh: '突破', color: '#f78166' },
  funding_arb: { label: 'funding_arb', zh: '费率', color: '#d29922' },
};

function ocStrategyKey(strategy) {
  if (strategy == null) return '';
  const raw = String(strategy).trim();
  if (!raw || raw === '--') return '';
  const normalized = raw
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
    .toLowerCase();
  const aliases = {
    grid: 'grid_trading',
    grid_trading: 'grid_trading',
    ma_crossover: 'ma_crossover',
    bb_reversion: 'bb_reversion',
    bb_breakout: 'bb_breakout',
    funding_arb: 'funding_arb',
    funding_rate_arb: 'funding_arb',
    fundingrate_arb: 'funding_arb',
  };
  if (aliases[normalized]) return aliases[normalized];
  for (const key of Object.keys(OC_STRATEGY_COLOR_META)) {
    if (normalized === key || normalized.startsWith(key + '_')) return key;
  }
  if (normalized.startsWith('funding_rate_arb_') || normalized.startsWith('fundingrate_arb_')) return 'funding_arb';
  return '';
}

function ocStrategyMeta(strategy) {
  const key = ocStrategyKey(strategy);
  if (!key || !OC_STRATEGY_COLOR_META[key]) return null;
  return Object.assign({ key: key }, OC_STRATEGY_COLOR_META[key]);
}

function ocStrategyLabel(strategy) {
  const meta = ocStrategyMeta(strategy);
  if (!meta) return strategy == null ? '' : String(strategy);
  return meta.label + ' / ' + meta.zh;
}

function ocStrategyChip(strategy, options) {
  const raw = strategy == null ? '' : String(strategy);
  if (!raw || raw === '--') return '--';
  const meta = ocStrategyMeta(raw);
  if (!meta) return ocEsc(raw);
  const opts = options || {};
  const text = opts.label || meta.label;
  const title = meta.label + ' / ' + meta.zh;
  return '<span class="oc-strategy-chip oc-strategy-' + meta.key + '" title="' + ocEsc(title) + '">'
    + '<span class="oc-strategy-dot"></span>' + ocEsc(text) + '</span>';
}

// ─── Product Category Tag / 產品品類標籤 ─────────────────────────────────────
// Renders a colored chip showing the Bybit product category for positions/orders/fills.
// 在持倉/訂單/成交旁顯示帶顏色的品類標籤，便於區分不同產品類型。
const _OC_CAT_CONFIG = {
  linear:  { label: 'U本位',   color: '#3b82f6', bg: 'rgba(59,130,246,0.15)' },
  spot:    { label: '现货',     color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
  inverse: { label: '币本位',   color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
  option:  { label: '期权',     color: '#a855f7', bg: 'rgba(168,85,247,0.15)' },
};
function ocCategoryTag(category) {
  const cat = (category || 'linear').toLowerCase();
  const cfg = _OC_CAT_CONFIG[cat] || { label: cat, color: '#94a3b8', bg: 'rgba(148,163,184,0.15)' };
  return '<span style="display:inline-block;font-size:10px;padding:1px 5px;border-radius:3px;'
    + 'color:' + cfg.color + ';background:' + cfg.bg + ';border:1px solid ' + cfg.color + ';'
    + 'margin-left:4px;vertical-align:middle;line-height:14px">' + ocEsc(cfg.label) + '</span>';
}

// Render a cumulative-PnL trend polyline into an existing SVG.
// Accepts fills with any of: realized_pnl / closedPnl / pnl. Oldest fill on the
// left, newest on the right; y-axis spans [min, max] but always includes 0 so
// the zero-reference line visually splits wins from losses.
// Pass zeroLineId to also place the dashed zero baseline at the right y.
// 渲染累計盈虧走勢。字段兼容：realized_pnl / closedPnl / pnl。左舊右新；
// y 軸總是包含 0，方便零線直觀分隔盈虧。zeroLineId 可選，傳入會自動調整
// 虛線 y 座標。
function ocPnlTrend(lineId, labelId, fills, zeroLineId) {
  var lineEl = document.getElementById(lineId);
  var labelEl = document.getElementById(labelId);
  if (!lineEl) return;
  if (!fills || !fills.length) {
    lineEl.setAttribute('points', '');
    if (labelEl) { labelEl.textContent = 'no data'; labelEl.setAttribute('fill', 'var(--text-dim)'); }
    return;
  }
  var sorted = fills.slice().reverse().slice(0, 50);
  var cumulative = 0;
  var series = sorted.map(function(f) {
    var v = f.realized_pnl != null ? f.realized_pnl
          : (f.closedPnl != null ? f.closedPnl
          : (f.pnl != null ? f.pnl : 0));
    var n = parseFloat(v);
    if (!isFinite(n)) n = 0;
    cumulative += n;
    return cumulative;
  });
  if (series.length < 2) {
    lineEl.setAttribute('points', '');
    if (labelEl) labelEl.textContent = 'collecting data...';
    return;
  }
  var W = 400, H = 120, pad = 8;
  var minV = Math.min(0, Math.min.apply(null, series));
  var maxV = Math.max(0, Math.max.apply(null, series));
  var range = (maxV - minV) || 1;
  var yFor = function(v) { return H - pad - ((v - minV) / range) * (H - pad * 2); };
  var points = series.map(function(v, i) {
    var x = pad + (i / (series.length - 1)) * (W - pad * 2);
    return x.toFixed(1) + ',' + yFor(v).toFixed(1);
  }).join(' ');
  lineEl.setAttribute('points', points);
  var last = series[series.length - 1];
  lineEl.setAttribute('stroke', last >= 0 ? 'var(--green)' : 'var(--red)');
  if (zeroLineId) {
    var zEl = document.getElementById(zeroLineId);
    if (zEl) {
      var zy = yFor(0).toFixed(1);
      zEl.setAttribute('x1', pad);
      zEl.setAttribute('x2', W - pad);
      zEl.setAttribute('y1', zy);
      zEl.setAttribute('y2', zy);
    }
  }
  if (labelEl) {
    labelEl.textContent = (last >= 0 ? '+' : '') + last.toFixed(4) + ' USDT (' + series.length + ' fills)';
    labelEl.setAttribute('fill', last >= 0 ? 'var(--green)' : 'var(--red)');
  }
}

function ocPnlSeriesTrend(lineId, labelId, points, zeroLineId, summary) {
  var lineEl = document.getElementById(lineId);
  var labelEl = document.getElementById(labelId);
  if (!lineEl) return;
  var rows = Array.isArray(points) ? points : [];
  if (!rows.length) {
    lineEl.setAttribute('points', '');
    if (labelEl) { labelEl.textContent = 'no data'; labelEl.setAttribute('fill', 'var(--text-dim)'); }
    return;
  }
  var series = rows.map(function(p) {
    var n = Number(p && p.cumulative_net_pnl);
    return Number.isFinite(n) ? n : 0;
  });
  var W = 400, H = 120, pad = 8;
  var minV = Math.min(0, Math.min.apply(null, series));
  var maxV = Math.max(0, Math.max.apply(null, series));
  var range = (maxV - minV) || 1;
  var yFor = function(v) { return H - pad - ((v - minV) / range) * (H - pad * 2); };
  var pointsAttr = series.map(function(v, i) {
    var x = series.length > 1 ? pad + (i / (series.length - 1)) * (W - pad * 2) : W / 2;
    return x.toFixed(1) + ',' + yFor(v).toFixed(1);
  }).join(' ');
  lineEl.setAttribute('points', pointsAttr);
  var last = series[series.length - 1];
  lineEl.setAttribute('stroke', last >= 0 ? 'var(--green)' : 'var(--red)');
  if (zeroLineId) {
    var zEl = document.getElementById(zeroLineId);
    if (zEl) {
      var zy = yFor(0).toFixed(1);
      zEl.setAttribute('x1', pad);
      zEl.setAttribute('x2', W - pad);
      zEl.setAttribute('y1', zy);
      zEl.setAttribute('y2', zy);
    }
  }
  if (labelEl) {
    var fills = summary && Number.isFinite(Number(summary.fills)) ? Number(summary.fills) : 0;
    var rangeLabel = summary && summary.range ? String(summary.range).toUpperCase() : '';
    labelEl.textContent = (last >= 0 ? '+' : '') + last.toFixed(4) + ' USDT' +
      (rangeLabel ? ' · ' + rangeLabel : '') + ' · ' + fills + ' fills';
    labelEl.setAttribute('fill', last >= 0 ? 'var(--green)' : 'var(--red)');
  }
}

function ocPnlSeriesTableRows(points) {
  var rows = Array.isArray(points) ? points.slice() : [];
  rows = rows.filter(function(p) {
    return p && (Number(p.fills) || Number(p.net_pnl) || Number(p.funding_pnl));
  }).slice(-14).reverse();
  if (!rows.length) {
    return '<tr class="empty-row"><td colspan="5">no PnL buckets</td></tr>';
  }
  return rows.map(function(p) {
    var net = Number(p.net_pnl);
    var cum = Number(p.cumulative_net_pnl);
    var fees = Number(p.fees);
    return '<tr>' +
      '<td>' + ocEsc(ocTime(p.ts_ms)) + '</td>' +
      '<td>' + (Number(p.fills) || 0) + '</td>' +
      '<td class="' + ocPnlClass(net) + '">' + ocMoney(Number.isFinite(net) ? net : 0, 4) + '</td>' +
      '<td class="' + ocPnlClass(cum) + '">' + ocMoney(Number.isFinite(cum) ? cum : 0, 4) + '</td>' +
      '<td>' + ocBalance(Number.isFinite(fees) ? fees : 0, 4) + '</td>' +
      '</tr>';
  }).join('');
}

function ocPnlSeriesFromFills(fills, rangeKey) {
  var rows = Array.isArray(fills) ? fills.slice() : [];
  rows = rows.map(function(f) {
    var ts = f && (f.exec_time || f.execTime || f.ts_ms || f.ts || f.time);
    var d = ocDate(ts);
    var grossRaw = f && (f.realized_pnl != null ? f.realized_pnl
      : (f.closedPnl != null ? f.closedPnl : (f.pnl != null ? f.pnl : 0)));
    var feeRaw = f && (f.fee != null ? f.fee : (f.execFee != null ? f.execFee : 0));
    var gross = Number(grossRaw);
    var fee = Number(feeRaw);
    if (!Number.isFinite(gross)) gross = 0;
    if (!Number.isFinite(fee)) fee = 0;
    return {
      ts_ms: d ? d.getTime() : 0,
      gross_pnl: gross,
      fees: fee,
      funding_pnl: 0,
      net_pnl: gross - fee,
      fills: 1,
    };
  }).filter(function(p) {
    return p.ts_ms > 0;
  }).sort(function(a, b) {
    return a.ts_ms - b.ts_ms;
  });
  var rangeMsMap = {
    '1h': 60 * 60 * 1000,
    '6h': 6 * 60 * 60 * 1000,
    '24h': 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000,
    '30d': 30 * 24 * 60 * 60 * 1000,
  };
  var key = String(rangeKey || '').toLowerCase();
  if (rangeMsMap[key]) {
    var cutoff = Date.now() - rangeMsMap[key];
    rows = rows.filter(function(p) { return p.ts_ms >= cutoff; });
  }

  var cumulative = 0;
  var points = rows.map(function(p) {
    cumulative += Number(p.net_pnl) || 0;
    return {
      ts_ms: p.ts_ms,
      fills: p.fills,
      gross_pnl: Number(p.gross_pnl) || 0,
      fees: Number(p.fees) || 0,
      funding_pnl: 0,
      net_pnl: Number(p.net_pnl) || 0,
      cumulative_net_pnl: cumulative,
      source: 'recent_fills_fallback',
    };
  });
  return {
    available: points.length > 0,
    source: 'recent_fills_fallback',
    range: rangeKey || 'fills',
    fills: points.length,
    points: points,
  };
}

function ocSetPnlRangeButtons(containerId, activeRange) {
  var el = document.getElementById(containerId);
  if (!el) return;
  var active = String(activeRange || '').toLowerCase();
  el.querySelectorAll('button[data-pnl-range]').forEach(function(btn) {
    var isActive = String(btn.getAttribute('data-pnl-range') || '').toLowerCase() === active;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    btn.style.borderColor = isActive ? 'rgba(56,139,253,0.75)' : '';
    btn.style.background = isActive ? 'rgba(56,139,253,0.16)' : '';
    btn.style.color = isActive ? 'var(--blue)' : '';
  });
}

// Render a colored PnL <td> cell. Opening fills (PnL≈0) show as dim dash;
// closing fills show signed value tinted green (profit) or red (loss).
// Accepts multiple field names: realized_pnl (Rust engine) / closedPnl (Bybit API).
// 渲染盈亏单元格。开仓单 PnL≈0 显示灰色破折号；平仓单显示带符号的绿/红金额。
function ocPnlCell(raw) {
  const pnl = parseFloat(raw);
  if (!isFinite(pnl) || Math.abs(pnl) < 0.0001) {
    return '<td style="color:var(--text-dim)">—</td>';
  }
  const cls = pnl >= 0 ? 'green' : 'red';
  const sign = pnl >= 0 ? '+' : '';
  return '<td class="' + cls + '">' + sign + pnl.toFixed(4) + '</td>';
}

// ─── Auto Refresh ────────────────────────────────────────────────────────────
let _ocRefreshTimer = null;
let _ocRefreshFn = null;

function ocStartRefresh(fn, interval) {
  _ocRefreshFn = fn;
  if (_ocRefreshTimer) clearInterval(_ocRefreshTimer);
  _ocRefreshTimer = setInterval(fn, interval || 15000);
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
    /* 计价货币切换徽章 — 点击循环切换 USDT / USD / EUR */
    .oc-curr-badge { display: inline-block; padding: 2px 9px; border-radius: 999px;
      font-size: 11px; font-weight: 600; letter-spacing: 0.3px; cursor: pointer;
      background: rgba(56,139,253,0.12); border: 1px solid rgba(56,139,253,0.3);
      color: var(--blue); user-select: none; transition: background 0.15s; }
    .oc-curr-badge:hover { background: rgba(56,139,253,0.25); }

    /* Tooltip on metric labels — shows on hover */
    .oc-metric-label[title] { cursor: help; border-bottom: 1px dotted var(--text-dim); display: inline-block; }
    .oc-performance-metrics .oc-metric-label[title] { display: block; width: fit-content; max-width: 100%; }

    /* live-metric: unified alias for tab-live.html metric cells (§6.1 CSS unification)
       live-metric 是 oc-metric 的别名，用于实盘 tab。保持视觉一致，特殊修饰词在各 tab 自定义。
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

    /* Load-error state / 加载失败状态 — used by ocLoadError() */
    .oc-load-error { color: var(--red); font-size: 12px; padding: 10px 0;
      display: flex; align-items: center; gap: 8px; }
    .oc-load-error button { padding: 2px 8px; font-size: 10px; }

    /* Diff-highlight on risk form cells / 风控表单原值对比高亮 — used by §4.1 diff mode */
    .oc-diff-changed { background: rgba(210,153,34,0.12) !important;
      border-color: rgba(210,153,34,0.4) !important; }
    .oc-diff-label { font-size: 9px; color: var(--yellow); margin-top: 3px; font-style: italic; }

    /* Generic confirm modal (shared across tab iframes) / 通用确认弹窗（各 tab iframe 共用） */
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
// openConfirmModal: 在 app.js 未加载的 tab iframe 中提供通用确认弹窗。
// When app.js loads in the parent context, its version overrides this one there.
// 当 app.js 在父上下文加载时，会在该上下文覆盖此版本。

// ─── Load Error Display Helper ────────────────────────────────────────────────
/**
 * Show a user-friendly load-failure state inside an element.
 * 在元素内显示用户友好的加载失败状态（区别于无声 -- 占位）。
 * @param {string} elementId - container element id to replace content
 * @param {string} [retryFnName] - JS function name (string) to call on retry click, e.g. 'loadAll'
 * @param {string} [msg] - optional custom message
 */
function ocLoadError(elementId, retryFnName, msg) {
  var el = document.getElementById(elementId);
  if (!el) return;
  var retryBtn = retryFnName
    ? ' <button class="oc-btn" style="padding:2px 8px;font-size:10px" onclick="' + retryFnName + '()">↺ 重试 / Retry</button>'
    : '';
  el.innerHTML = '<div class="oc-load-error">⚠ ' +
    (msg || '连接失败，请检查引擎状态 / Connection failed — check engine') +
    retryBtn + '</div>';
}

// ─── Mode Badge Component (REF-20 R20-P1-U7) ────────────────────────────────
// MODULE_NOTE
// 模組目的：4 維 inline pill 化 mode badge — 在 Paper Replay Lab 顯示
//          每個 replay 結果的「資料層級 / 輸出策略 / 校準新鮮度 / 執行可信度」
//          四個維度，配合 UX subdoc §7 防認知欺詐 + §10 a11y 規範。
// Module purpose: 4-dimension inline pill mode badge — displays four dimensions
//                 of every replay result in the Paper Replay Lab (data tier /
//                 output policy / calibration freshness / execution confidence),
//                 conforming to UX subdoc §7 anti-cognitive-fraud rules and
//                 §10 accessibility requirements.
//
// 上游契約：
//   - UX subdoc §7 Mode Badges
//   - Workplan §4 Wave 2 R20-P1-U7
//   - V3 §12 #25 replay_ml_maturity_label（雙驗 DB + UI surface）
//
// 防誤觸詐核心：execution_confidence='none' 必灰底 + ⚠️ icon + tooltip + 紅邊
// （memory feedback_workflow_audit_chain.md 風險 #17）。
//
// XSS 防護：所有動態文字經 ocEsc() 包裝；所有動態 class token 經 ocSanitizeClass()
// 過濾，禁直接 innerHTML 拼接外部資料。
//
// i18n hook：tooltip 文案此版本 EN inline + 中文輔助；REF-20 R20-P1-U9 將以
// `i18n_zh.js` 對照表替換 `_OC_MODE_BADGE_DEFS` 內的 label/tip 字串。
//
// 注意（ambiguity for PM/A3 review）：UX subdoc §7 列出的 4 維是 run_mode /
// data_tier / execution_confidence / runtime_environment；本任務 dispatch 文
// 的 4 維為 data_tier / output_policy / calibration_freshness / execution_confidence。
// 本 component 將 task dispatch 的 4 維作為 canonical mock seed，並在
// `_OC_MODE_BADGE_DEFS` 同時保留 UX subdoc §7 的兩個備援 dimension（run_mode /
// runtime_environment），待 PM/A3 final 對齊後選一套呈現。

// State → variant 顏色對應表（per UX subdoc §10 「不可只靠顏色」原則：每個
// state 同時帶 icon + 文字 label，並控制色僅作為輔助視覺信號）。
// State → variant color map. Per UX subdoc §10, color is supplementary only;
// every state additionally renders an icon and a text label.
//
// variant 對應 oc-chip 樣式：good=綠 / info=藍 / warn=黃 / bad=紅 / neutral=灰。
// Variants reuse oc-chip styles: good=green / info=blue / warn=yellow / bad=red /
// neutral=grey.
var _OC_MODE_BADGE_DEFS = {
  // 1. Data Tier — 資料層級
  // dispatch 4 維版本：real / synthetic / mixed
  // UX subdoc §7 補充：S0 / S1 / S2 / S3 / S4 evidence source（可選別名 alt_states）
  data_tier: {
    label_en: 'Data Tier',
    label_zh: '資料層級',
    states: {
      real:      { variant: 'good',    icon: '●', label_en: 'Real',      label_zh: '真實資料',    tip_en: 'Real exchange feed data', tip_zh: '真實交易所行情資料' },
      synthetic: { variant: 'warn',    icon: '◆', label_en: 'Synthetic', label_zh: '合成資料',    tip_en: 'Synthetic / generated data', tip_zh: '合成或生成的資料' },
      mixed:     { variant: 'info',    icon: '◐', label_en: 'Mixed',     label_zh: '混合資料',    tip_en: 'Mixed real + synthetic data', tip_zh: '真實與合成混合資料' },
      unknown:   { variant: 'neutral', icon: '○', label_en: 'Unknown',   label_zh: '未知',        tip_en: 'Data tier not yet determined', tip_zh: '資料層級尚未判定' },
    },
  },
  // 2. Output Policy — 輸出策略
  // dispatch 4 維版本：actionable / advisory / none
  output_policy: {
    label_en: 'Output Policy',
    label_zh: '輸出策略',
    states: {
      actionable: { variant: 'good',    icon: '✓', label_en: 'Actionable', label_zh: '可執行',     tip_en: 'Result may inform live trading',  tip_zh: '結果可作為實盤決策參考' },
      advisory:   { variant: 'info',    icon: 'ℹ', label_en: 'Advisory',   label_zh: '僅建議',     tip_en: 'Advisory only, not actionable',   tip_zh: '僅建議用途，不可作為實盤依據' },
      none:       { variant: 'neutral', icon: '—', label_en: 'None',       label_zh: '無',         tip_en: 'No output policy assigned',       tip_zh: '尚未指派輸出策略' },
    },
  },
  // 3. Calibration Freshness — 校準新鮮度
  // dispatch 4 維版本：fresh / stale / unknown
  calibration_freshness: {
    label_en: 'Calibration',
    label_zh: '校準新鮮度',
    states: {
      fresh:   { variant: 'good',    icon: '✓', label_en: 'Fresh',   label_zh: '新鮮',       tip_en: 'Calibration freshness <=72h (per V3 §12 #15)', tip_zh: '校準資料 <=72 小時' },
      stale:   { variant: 'warn',    icon: '⚠', label_en: 'Stale',   label_zh: '陳舊',       tip_en: 'Calibration freshness exceeded; refit suggested', tip_zh: '校準已過期，建議重新校準' },
      unknown: { variant: 'neutral', icon: '?',      label_en: 'Unknown', label_zh: '未知',       tip_en: 'Calibration freshness not yet computed', tip_zh: '校準新鮮度尚未計算' },
    },
  },
  // 4. Execution Confidence — 執行可信度（防誤觸詐關鍵維度）
  // dispatch 4 維版本：high / medium / low / none
  // UX subdoc §7：none / limited / calibrated（保留別名）
  execution_confidence: {
    label_en: 'Exec Confidence',
    label_zh: '執行可信度',
    states: {
      high:    { variant: 'good',    icon: '✓', label_en: 'High',    label_zh: '高',         tip_en: 'Calibrated execution confidence', tip_zh: '已校準的高執行可信度' },
      medium:  { variant: 'info',    icon: '●', label_en: 'Medium',  label_zh: '中',         tip_en: 'Limited / partial execution confidence', tip_zh: '部分校準的中等執行可信度' },
      low:     { variant: 'warn',    icon: '⚠', label_en: 'Low',     label_zh: '低',         tip_en: 'Low execution confidence; treat with caution', tip_zh: '低執行可信度，請謹慎判讀' },
      // 'none' = 防誤觸詐 SENTINEL：灰底 + ⚠️ + tooltip + 紅邊（卡片右上）
      // 'none' = anti-cognitive-fraud SENTINEL: grey background + warning icon
      // + tooltip + red border (card top-right). Renderer additionally sets
      // data-confidence-none="1" attribute so caller cards can light up the
      // red border per UX subdoc §7 Rule 1.
      none:    { variant: 'bad',     icon: '⚠', label_en: 'None',    label_zh: '無',         tip_en: 'Execution confidence=none — result is NOT actionable', tip_zh: '執行可信度為「無」— 結果不可作為實盤依據', danger: true },
    },
  },
  // ── UX subdoc §7 補充維度（暫不放 mock seed，等 PM/A3 final）─────────────
  // ── UX subdoc §7 supplementary dimensions (not in mock seed pending review) ──
  run_mode: {
    label_en: 'Run Mode',
    label_zh: '運行模式',
    states: {
      paper_session:      { variant: 'info',    icon: '▶', label_en: 'Paper Session',      label_zh: 'Paper 會話',       tip_en: 'Live paper session',           tip_zh: 'Paper 即時會話' },
      replay_smoke:       { variant: 'warn',    icon: '◆', label_en: 'Smoke Replay',       label_zh: '煙霧回放',         tip_en: 'P2 non-actionable smoke test', tip_zh: 'P2 非可執行煙霧測試' },
      calibrated_replay:  { variant: 'good',    icon: '✓', label_en: 'Calibrated Replay',  label_zh: '校準回放',         tip_en: 'Calibrated P3+ report',        tip_zh: '已校準 P3+ 回放' },
      advisory:           { variant: 'info',    icon: 'ℹ', label_en: 'Advisory',           label_zh: '建議證據',         tip_en: 'Advisory recommendation',      tip_zh: '建議用途的證據' },
      handoff:            { variant: 'good',    icon: '→', label_en: 'Handoff',            label_zh: '候選交接',         tip_en: 'Bounded demo handoff',         tip_zh: '受限 demo 候選交接' },
      unknown:            { variant: 'neutral', icon: '○', label_en: 'Unknown',            label_zh: '未知',             tip_en: 'Run mode not yet determined',  tip_zh: '運行模式尚未判定' },
    },
  },
  runtime_environment: {
    label_en: 'Runtime',
    label_zh: '執行環境',
    states: {
      linux_trade_core:        { variant: 'good',    icon: '■', label_en: 'Linux Trade Core',       label_zh: 'Linux 交易主機',       tip_en: 'Linux trade-core production runtime',           tip_zh: 'Linux trade-core 生產執行環境' },
      mac_dev_smoke_test_only: { variant: 'warn',    icon: '⚠', label_en: 'Mac Dev (Smoke Only)',    label_zh: 'Mac 開發機（僅煙霧）',  tip_en: 'Mac dev smoke test only — not production',     tip_zh: 'Mac 開發機僅供煙霧測試 — 非生產環境' },
      unknown:                 { variant: 'neutral', icon: '○', label_en: 'Unknown',                 label_zh: '未知',                  tip_en: 'Runtime environment not yet determined',       tip_zh: '執行環境尚未判定' },
    },
  },
};

// Internal helper: resolve a (dimension, state) tuple to render metadata.
// Falls back to a neutral 'Unknown' shape when either is missing — the
// component must never throw on stale or partial data because P1 mock
// state is 全 unknown / none.
//
// 內部輔助：把 (dimension, state) 元組解析為渲染所需的 metadata。
// 任一缺失即回退中性 unknown 形狀；component 不可在資料缺失時拋例外，
// 因為 P1 階段 mock state 全 unknown / none。
function _ocResolveModeBadge(dim, state) {
  var def = _OC_MODE_BADGE_DEFS[dim];
  if (!def) {
    return null;  // 未知 dimension 直接 skip / unknown dimension is silently skipped
  }
  var sv = (state == null ? '' : String(state)).toLowerCase();
  var entry = def.states[sv] || def.states.unknown || {
    variant: 'neutral',
    icon: '○',
    label_en: 'Unknown',
    label_zh: '未知',
    tip_en: 'State unknown',
    tip_zh: '狀態未知',
  };
  return {
    dim: dim,
    state: sv || 'unknown',
    dim_label_en: def.label_en,
    dim_label_zh: def.label_zh,
    variant: entry.variant || 'neutral',
    icon: entry.icon || '○',
    label_en: entry.label_en,
    label_zh: entry.label_zh,
    tip_en: entry.tip_en || '',
    tip_zh: entry.tip_zh || '',
    danger: !!entry.danger,
  };
}

// Lookup state label from i18n_zh.js (MED-5 retrofit). Defensive against
// i18n_zh.js not loaded yet (script-order race) and against miss returns
// (t_zh's documented behavior is to return the raw key path on miss).
//
// 從 i18n_zh.js 查 state label（MED-5 retrofit）。防 i18n_zh.js 未載入
// (script 載入順序競爭) + 防 t_zh miss return raw key 兩種失敗模式。
//
// Fallback chain:
//   1. window.t_zh('mode_badge.<dim>.<state>') if function exists and result
//      != raw key path (miss signal)
//   2. meta.label_zh (def 內既有中文)
//   3. meta.label_en (最後保險)
//
// SAFETY / 不變量：返回值必為 non-empty string；caller 後續經 ocEsc 過濾。
// SAFETY / Invariant: returns non-empty string; caller pipes through ocEsc.
function _ocLookupModeBadgeStateLabel(meta) {
  if (!meta) return '';
  var keyPath = 'mode_badge.' + meta.dim + '.' + meta.state;
  if (typeof window.t_zh === 'function') {
    var looked = window.t_zh(keyPath);
    // t_zh miss → return raw key path; 用 strict !== 確認真有 hit。
    // t_zh miss returns raw key path; strict !== confirms a real hit.
    if (typeof looked === 'string' && looked !== keyPath && looked.length > 0) {
      return looked;
    }
  }
  return meta.label_zh || meta.label_en || '';
}

// Render a single pill HTML string. XSS-safe: every dynamic text token is
// passed through ocEsc(); class token is sanitized via ocSanitizeClass().
//
// 渲染單一 pill HTML 字串。XSS 安全：所有動態文字經 ocEsc()；class token 經
// ocSanitizeClass() 過濾。
//
// A11y：
//   - role="status" 讓螢幕閱讀器讀出 state 變化
//   - aria-label 同時包含 dimension + state，避免 SR 只念 icon（中英並列）
//   - tabindex="0" 讓鍵盤可 focus
//   - title 提供 hover tooltip（瀏覽器 native，非 framework popover）
//
// i18n 行為（REF-20 R20-P1-U9 + Wave 2 Batch 1 MED-5 retrofit）：
//   - operator 中文 dominant 偏好 (per memory feedback_chinese_output)，
//     state label 優先取 i18n_zh.js `mode_badge.<dim>.<state>` 中文文案；
//     i18n_zh.js 未載入或 key miss 時 fallback 至 def 內既有 label_zh / label_en。
//   - dim label 用 def 內 label_zh（i18n_zh schema 沒對應 dim 級條目，
//     既有 def label_zh 已是中文，免重複表）。
//   - tooltip 保 EN + 中文並列 (`tip_en / tip_zh`)，i18n_zh schema
//     execution_confidence / calibration_freshness 詳細表只 cover 部分 state，
//     不全 cover 4 維所有 state，故 tooltip 暫沿 def 內既有 inline 字串。
//
// i18n behavior (REF-20 R20-P1-U9 + Wave 2 Batch 1 MED-5 retrofit):
//   - Per operator Chinese-dominant preference, state label first looks up
//     i18n_zh.js path `mode_badge.<dim>.<state>`. Falls back to def-internal
//     label_zh, then label_en, when t_zh() is unavailable or returns the raw
//     key path on miss (i18n_zh.js's documented miss signal).
//   - Dim label uses def-internal label_zh (i18n_zh.js schema has no
//     dim-level entry; def already carries Chinese).
//   - Tooltip stays bilingual (EN / 中文) from def-internal tip_en / tip_zh.
function _ocRenderModeBadgePill(meta) {
  if (!meta) return '';
  // 防誤觸詐：execution_confidence=none 用 bad variant + ⚠️ icon + 紅邊框
  // Anti-cognitive-fraud: execution_confidence=none uses bad variant +
  // warning icon + red outline.
  var variant = ocSanitizeClass(meta.variant);
  var dimSlug = ocSanitizeClass(meta.dim);
  var stateSlug = ocSanitizeClass(meta.state);
  var dangerAttr = meta.danger ? ' data-confidence-none="1"' : '';
  // i18n lookup: state label 優先取 i18n_zh.js `mode_badge.<dim>.<state>`
  // 中文；t_zh 缺載入或 miss → fallback def 既有 label_zh → label_en。
  // i18n lookup: state label prefers i18n_zh.js `mode_badge.<dim>.<state>`
  // Chinese; t_zh missing or miss → fallback to def label_zh → label_en.
  var dimLabel = ocEsc(meta.dim_label_zh || meta.dim_label_en);
  var stateLabel = ocEsc(_ocLookupModeBadgeStateLabel(meta));
  var icon = ocEsc(meta.icon);
  var tipEn = meta.tip_en || '';
  var tipZh = meta.tip_zh || '';
  // operator 中文 dominant：tooltip 用「zh / EN」順序 (operator 直視 channel)；
  // aria-label (screen reader) 仍保 EN 在前以維護 a11y baseline。
  // operator zh-dominant: tooltip uses "zh / EN" order (operator-facing channel);
  // aria-label keeps EN-first for screen-reader a11y baseline.
  var titleText = tipZh + (tipEn ? ' / ' + tipEn : '');
  var ariaLabel = meta.dim_label_en + ': ' + meta.label_en
    + ' / ' + (meta.dim_label_zh || meta.dim_label_en)
    + ': ' + (meta.label_zh || meta.label_en)
    + (meta.danger ? ' (warning, not actionable / 警告，不可作為實盤依據)' : '');
  return '<span class="oc-mode-badge oc-chip oc-chip-' + variant + '"'
    + ' data-mode-dim="' + dimSlug + '"'
    + ' data-mode-state="' + stateSlug + '"'
    + dangerAttr
    + ' role="status"'
    + ' tabindex="0"'
    + ' aria-label="' + ocEsc(ariaLabel) + '"'
    + ' title="' + ocEsc(titleText) + '"'
    + '>'
    + '<span class="oc-mode-badge-icon" aria-hidden="true">' + icon + '</span>'
    + '<span class="oc-mode-badge-dim">' + dimLabel + ':</span>'
    + '<strong class="oc-mode-badge-state">' + stateLabel + '</strong>'
    + '</span>';
}

// Public API exposed on window.OpenClawModeBadge.
// 對外公開 API，掛在 window.OpenClawModeBadge 命名空間上。
window.OpenClawModeBadge = {
  /**
   * Render the four-mode pill row into a container in one shot.
   * 一次渲染 4 維 pill 列到指定 container。
   *
   * @param {string} containerId - DOM element id of the slot
   * @param {Object} modes - { data_tier, output_policy, calibration_freshness, execution_confidence }
   *                         每個 value 為 string state token；缺失即視為 unknown。
   *                         Optional extra keys: run_mode, runtime_environment（UX subdoc §7 dim）
   * @returns {boolean} true on success, false if container not found
   */
  render: function(containerId, modes) {
    var el = document.getElementById(containerId);
    if (!el) {
      console.warn('[OpenClawModeBadge.render] container not found: ' + containerId);
      return false;
    }
    modes = modes || {};
    // Render 4 canonical dimensions (per task dispatch) + 任何額外傳入的 UX
    // subdoc §7 dimension。Order matters：先 data_tier → output_policy →
    // calibration_freshness → execution_confidence（最後一格剛好放在右側
    // 醒目位置，符合 UX subdoc §7 Rule 1）。
    // Render 4 canonical dimensions + any extras passed by caller. Order is
    // deliberate so execution_confidence sits on the rightmost slot per UX §7.
    var canonical = ['data_tier', 'output_policy', 'calibration_freshness', 'execution_confidence'];
    var extras = ['run_mode', 'runtime_environment'];
    var pills = [];
    canonical.forEach(function(dim) {
      var meta = _ocResolveModeBadge(dim, modes[dim]);
      if (meta) pills.push(_ocRenderModeBadgePill(meta));
    });
    extras.forEach(function(dim) {
      if (Object.prototype.hasOwnProperty.call(modes, dim)) {
        var meta = _ocResolveModeBadge(dim, modes[dim]);
        if (meta) pills.push(_ocRenderModeBadgePill(meta));
      }
    });
    el.classList.add('oc-mode-badge-row');
    // innerHTML safe here — every interpolated value already routed through
    // ocEsc / ocSanitizeClass inside _ocRenderModeBadgePill.
    // 此處 innerHTML 安全：所有插入值已在 _ocRenderModeBadgePill 內部過濾。
    el.innerHTML = pills.join('');
    return true;
  },

  /**
   * Update a single dimension's pill in place to avoid full-row flicker.
   * 單 dim 原地更新 pill，避免整列 re-render flicker。
   *
   * @param {string} containerId
   * @param {string} dim - one of data_tier / output_policy / calibration_freshness / execution_confidence / run_mode / runtime_environment
   * @param {string} state - new state token
   * @returns {boolean} true on success
   */
  update: function(containerId, dim, state) {
    var el = document.getElementById(containerId);
    if (!el) return false;
    var meta = _ocResolveModeBadge(dim, state);
    if (!meta) {
      console.warn('[OpenClawModeBadge.update] unknown dim: ' + dim);
      return false;
    }
    var slug = ocSanitizeClass(dim);
    var existing = el.querySelector('[data-mode-dim="' + slug + '"]');
    var html = _ocRenderModeBadgePill(meta);
    if (existing) {
      // Replace via temp wrapper to keep the rendered nodes parsed by
      // browser HTML parser — innerHTML on parent would re-render siblings.
      // 用臨時 wrapper 替換，避免 parent.innerHTML 重渲所有同層 pill。
      var tmp = document.createElement('div');
      tmp.innerHTML = html;
      var fresh = tmp.firstChild;
      if (fresh) existing.replaceWith(fresh);
    } else {
      // 該 dim 尚未存在於列中，append 到尾端。
      // Dimension not yet present in row — append.
      el.insertAdjacentHTML('beforeend', html);
    }
    return true;
  },

  /**
   * Diagnostic helper: list all known dimensions + states. Useful for
   * smoke test harness and downstream U9 i18n table builder.
   * 診斷輔助：列出所有已知 dimension + state，供 smoke test 與 U9 i18n 表生成。
   */
  describe: function() {
    var out = {};
    Object.keys(_OC_MODE_BADGE_DEFS).forEach(function(dim) {
      out[dim] = Object.keys(_OC_MODE_BADGE_DEFS[dim].states);
    });
    return out;
  },
};

// CSS injection: append mode-badge-specific rules to the base CSS payload.
// Keeps oc-chip skeleton; adds row layout + danger outline + a11y focus ring.
// CSS 注入：在 base CSS 之上附加 mode-badge 專用規則。沿用 oc-chip 骨架，
// 額外加 row 排版、danger 外框、a11y focus 環。
(function _ocInjectModeBadgeCSS() {
  if (document.getElementById('oc-mode-badge-css')) return;
  var style = document.createElement('style');
  style.id = 'oc-mode-badge-css';
  style.textContent = [
    '.oc-mode-badge-row {',
    '  display: inline-flex; flex-wrap: wrap; gap: 6px;',
    '  align-items: center;',
    '}',
    '.oc-mode-badge {',
    '  font-size: 11px; line-height: 1.3;',
    '  padding: 3px 9px; gap: 5px;',
    '  cursor: help;',
    '}',
    '.oc-mode-badge:focus { outline: 2px solid var(--accent); outline-offset: 1px; }',
    '.oc-mode-badge:focus:not(:focus-visible) { outline: none; }',
    '.oc-mode-badge-icon { font-size: 11px; opacity: 0.85; }',
    '.oc-mode-badge-dim { color: var(--text-dim); font-weight: 500; letter-spacing: 0.2px; }',
    '.oc-mode-badge-state { font-weight: 700; }',
    '.oc-mode-badge[data-confidence-none="1"] {',
    '  /* Anti-cognitive-fraud SENTINEL: grey base + warning icon + red outline. */',
    '  /* 防誤觸詐 SENTINEL：灰底 + 警告 icon + 紅外框 */',
    '  background: rgba(139,148,158,0.12);',
    '  color: var(--red);',
    '  border: 1px solid var(--red);',
    '  box-shadow: 0 0 0 1px rgba(248,81,73,0.35) inset;',
    '}',
    '.oc-mode-badge[data-confidence-none="1"] .oc-mode-badge-icon {',
    '  color: var(--red); opacity: 1;',
    '}',
    '@media (max-width: 700px) {',
    '  .oc-mode-badge-row { gap: 4px; }',
    '  .oc-mode-badge { font-size: 10px; padding: 2px 7px; }',
    '}',
  ].join('\n');
  document.head.appendChild(style);
})();

/** Per-action metadata for dangerous operations / 危险操作的确认文本元数据 */
var _OC_CONFIRM_ACTIONS = {
  "reset-cooldown": {
    title: "重置冷卻期 / Reset Loss Cooldown",
    body: "連續虧損冷卻期是風控保護機制，重置後系統將立即恢復開倉。\n請確認當前市況適合繼續交易，否則可能加速虧損。",
    confirmLabel: "確認重置 / Confirm Reset"
  },
  "unhalt-session": {
    title: "解除熔斷 / Resume Trading",
    body: "熔斷保護在回撤嚴重時觸發，解除後所有交易功能恢復。\n⚠ 請確認風險已消除，否則可能觸發更大回撤。",
    confirmLabel: "確認解除 / Confirm Unhalt"
  },
  "delete-strategy": {
    title: "刪除策略 / Delete Strategy",
    body: "此操作無法撤銷，策略的所有參數與狀態將被永久刪除。\n策略刪除後立即生效，已開倉位不受影響但不再被該策略管理。",
    confirmLabel: "確認刪除 / Confirm Delete"
  },
  "paper-stop-all": {
    title: "停止 Paper + Demo / Stop Both Engines",
    body: "此操作會同時停止 Paper 與 Demo 引擎，並嘗試平掉對應持倉。\n請確認你不是只想暫停 Paper。",
    confirmLabel: "確認雙停 / Confirm Stop Both"
  }
};

/**
 * Show a custom confirmation dialog and return Promise<boolean>.
 * 显示自定义确认弹窗，返回 Promise<boolean>。
 * @param {string|Object} actionName - action key, plain title text, or per-call modal metadata
 * @returns {Promise<boolean>}
 */
function openConfirmModal(actionName) {
  const meta = (actionName && typeof actionName === 'object')
    ? actionName
    : (_OC_CONFIRM_ACTIONS[actionName] || {
    title: actionName || '確認操作 / Confirm Action',
    body: '此操作將立即執行，無法撤銷。\nThis action cannot be undone.',
    confirmLabel: '確認 / Confirm'
  });

  // Lazily inject overlay element / 懶加載注入 overlay 元素
  let overlay = document.getElementById('oc-generic-confirm-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'oc-generic-confirm-overlay';
    overlay.className = 'oc-confirm-overlay';
    overlay.innerHTML =
      '<div class="oc-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="oc-gc-title" tabindex="-1">' +
        '<h3 id="oc-gc-title"></h3>' +
        '<p id="oc-gc-body"></p>' +
        '<div class="btn-row">' +
          '<button id="oc-gc-cancel" class="oc-btn">取消 / Cancel</button>' +
          '<button id="oc-gc-confirm" class="oc-btn oc-btn-danger">確認</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);
  }

  // A3 HIGH-3 fix：concurrent-open guard（與 openTypedConfirmModal 對稱）
  if (overlay.classList.contains('show')) {
    return Promise.reject(new Error('openConfirmModal already open'));
  }

  document.getElementById('oc-gc-title').textContent = meta.title;
  document.getElementById('oc-gc-body').textContent = meta.body;
  var confirmBtn = document.getElementById('oc-gc-confirm');
  confirmBtn.textContent = meta.confirmLabel || '確認 / Confirm';
  confirmBtn.className = 'oc-btn ' + (meta.confirmClass || 'oc-btn-danger');
  overlay.classList.add('show');

  return new Promise(function(resolve) {
    var previousActive = document.activeElement;
    var cancelBtn = document.getElementById('oc-gc-cancel');
    function focusableNodes() {
      return Array.prototype.slice.call(
        overlay.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')
      ).filter(function(node) {
        return !node.disabled && node.offsetParent !== null;
      });
    }
    function close(val) {
      overlay.classList.remove('show');
      // Remove handlers to prevent duplicate firing / 移除监听防止重复触发
      cancelBtn.onclick = null;
      confirmBtn.onclick = null;
      overlay.onkeydown = null;
      if (previousActive && typeof previousActive.focus === 'function') {
        previousActive.focus();
      }
      resolve(val);
    }
    cancelBtn.onclick = function() { close(false); };
    confirmBtn.onclick = function() { close(true); };
    overlay.onkeydown = function(ev) {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        close(false);
        return;
      }
      if (ev.key !== 'Tab') return;
      var nodes = focusableNodes();
      if (!nodes.length) {
        ev.preventDefault();
        return;
      }
      var first = nodes[0];
      var last = nodes[nodes.length - 1];
      if (ev.shiftKey && document.activeElement === first) {
        ev.preventDefault();
        last.focus();
      } else if (!ev.shiftKey && document.activeElement === last) {
        ev.preventDefault();
        first.focus();
      }
    };
    setTimeout(function() { cancelBtn.focus(); }, 0);
  });
}

/**
 * Show a custom prompt dialog and return Promise<string|null>.
 * 顯示自定義輸入彈窗，返回 Promise<string|null>。
 */
function openPromptModal(options) {
  var meta = (typeof options === 'string') ? { title: options } : (options || {});
  var title = meta.title || '輸入內容 / Enter Value';
  var body = meta.body || '';
  var label = meta.label || 'Value';
  var defaultValue = meta.defaultValue == null ? '' : String(meta.defaultValue);
  var required = !!meta.required;
  var confirmLabel = meta.confirmLabel || '確認 / Confirm';
  var multiline = !!meta.multiline;
  var choices = Array.isArray(meta.choices) ? meta.choices : null;

  var overlay = document.getElementById('oc-generic-prompt-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'oc-generic-prompt-overlay';
    overlay.className = 'oc-confirm-overlay';
    overlay.innerHTML =
      '<div class="oc-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="oc-gp-title">' +
        '<h3 id="oc-gp-title"></h3>' +
        '<p id="oc-gp-body"></p>' +
        '<label class="oc-prompt-label" for="oc-gp-input" id="oc-gp-label"></label>' +
        '<input id="oc-gp-input" class="oc-prompt-input" type="text" autocomplete="off">' +
        '<textarea id="oc-gp-textarea" class="oc-prompt-textarea" style="display:none"></textarea>' +
        '<select id="oc-gp-select" class="oc-prompt-select" style="display:none"></select>' +
        '<div id="oc-gp-error" class="oc-prompt-error" role="alert"></div>' +
        '<div class="btn-row">' +
          '<button id="oc-gp-cancel" class="oc-btn">取消 / Cancel</button>' +
          '<button id="oc-gp-confirm" class="oc-btn oc-btn-primary">確認 / Confirm</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);
  }

  var titleEl = document.getElementById('oc-gp-title');
  var bodyEl = document.getElementById('oc-gp-body');
  var labelEl = document.getElementById('oc-gp-label');
  var inputEl = document.getElementById('oc-gp-input');
  var textareaEl = document.getElementById('oc-gp-textarea');
  var selectEl = document.getElementById('oc-gp-select');
  var errorEl = document.getElementById('oc-gp-error');
  var cancelBtn = document.getElementById('oc-gp-cancel');
  var confirmBtn = document.getElementById('oc-gp-confirm');

  titleEl.textContent = title;
  bodyEl.textContent = body;
  bodyEl.style.display = body ? '' : 'none';
  labelEl.textContent = label;
  errorEl.textContent = '';
  confirmBtn.textContent = confirmLabel;

  inputEl.style.display = choices || multiline ? 'none' : '';
  textareaEl.style.display = multiline ? '' : 'none';
  selectEl.style.display = choices ? '' : 'none';
  inputEl.value = defaultValue;
  textareaEl.value = defaultValue;
  selectEl.innerHTML = '';
  if (choices) {
    choices.forEach(function(choice) {
      var opt = document.createElement('option');
      opt.value = String(choice.value);
      opt.textContent = choice.label;
      if (String(choice.value) === defaultValue) opt.selected = true;
      selectEl.appendChild(opt);
    });
  }

  overlay.classList.add('show');

  return new Promise(function(resolve) {
    var activeField = choices ? selectEl : (multiline ? textareaEl : inputEl);
    function value() {
      return activeField.value == null ? '' : String(activeField.value);
    }
    function cleanup(result) {
      overlay.classList.remove('show');
      cancelBtn.onclick = null;
      confirmBtn.onclick = null;
      overlay.onkeydown = null;
      resolve(result);
    }
    cancelBtn.onclick = function() { cleanup(null); };
    confirmBtn.onclick = function() {
      var raw = value();
      if (required && !raw.trim()) {
        errorEl.textContent = '必填欄位 / Required field';
        activeField.focus();
        return;
      }
      cleanup(raw);
    };
    overlay.onkeydown = function(ev) {
      if (ev.key === 'Escape') cleanup(null);
      if (ev.key === 'Enter' && !multiline && !ev.shiftKey) {
        ev.preventDefault();
        confirmBtn.click();
      }
    };
    setTimeout(function() {
      activeField.focus();
      if (activeField.select) activeField.select();
    }, 0);
  });
}

/**
 * 高摩擦確認彈窗 — 要求 user 鍵入指定 phrase 才啟用「確認」按鈕。
 *
 * 用途：A3 v2 audit 標出 governance critical 寫操作（system_mode 切換 / live_execution_allowed
 * / bulk approve / recovery approve 等）必須超越單擊 yes/no — 強制鍵入「CONFIRM」或自定 phrase
 * 可降低誤觸，並讓 audit log 證據更明確。
 *
 * Returns Promise<boolean>：user 鍵入正確 phrase 並按確認 → true；其他路徑 → false。
 *
 * options 參數（純物件）：
 *   - title:        標題（預設「確認操作 / Confirm Action」）
 *   - body:         說明文字（預設提示「此動作影響真實資金/治理狀態」）
 *   - phrase:       user 必須鍵入的字串（預設 'CONFIRM'，case-sensitive）
 *   - confirmLabel: 確認按鈕文字（預設「確認執行 / Confirm」）
 *   - confirmClass: 確認按鈕 class（預設 'oc-btn-danger'）
 *   - hint:         input 上方的 hint 文字（預設提示鍵入 phrase）
 *   - actor:        顯示「操作者」（audit-aware 三原則第 2 條），可選
 *   - impact:       預期影響說明（可選）
 *   - rollback:     回滾路徑說明（可選）
 *
 * 設計約束：
 *   - 與 openConfirmModal 共用 .oc-confirm-overlay 與 .oc-confirm-dialog CSS
 *   - case-sensitive 比對，避免「confirm」/「CONFIRM」混淆
 *   - Esc 取消，Tab 鎖在 modal 內
 *   - phrase 比對成功才啟用 confirmBtn；input.value 任何修改即時校驗
 */
function openTypedConfirmModal(options) {
  var meta = (typeof options === 'string') ? { title: options } : (options || {});
  var title = meta.title || '確認操作 / Confirm Action';
  var body = meta.body || '此動作將立即執行，無法撤銷。\nThis action cannot be undone.';
  var phrase = meta.phrase || 'CONFIRM';
  var confirmLabel = meta.confirmLabel || '確認執行 / Confirm';
  var confirmClass = meta.confirmClass || 'oc-btn-danger';
  var hint = meta.hint || ('請鍵入「' + phrase + '」以確認 / Type "' + phrase + '" to confirm');
  var actor = meta.actor || '';
  var impact = meta.impact || '';
  var rollback = meta.rollback || '';

  var overlay = document.getElementById('oc-typed-confirm-overlay');
  // W-AUDIT-7c round 2 fix [#7]：singleton overlay 已 .show 狀態時拒絕第二次開啟，
  // 避免併發 Promise 覆蓋第一個 resolver（onclick handler / oninput / onkeydown 都會被新呼叫覆蓋）。
  if (overlay && overlay.classList.contains('show')) {
    console.error('[openTypedConfirmModal] modal already open; rejecting concurrent open');
    return Promise.reject(new Error('modal already open'));
  }
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'oc-typed-confirm-overlay';
    overlay.className = 'oc-confirm-overlay';
    overlay.innerHTML =
      '<div class="oc-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="oc-tc-title" tabindex="-1">' +
        '<h3 id="oc-tc-title"></h3>' +
        '<p id="oc-tc-body" style="white-space:pre-line"></p>' +
        '<div id="oc-tc-meta" style="font-size:11px;color:var(--text-dim);margin:6px 0 10px;line-height:1.6;display:none"></div>' +
        '<label class="oc-prompt-label" for="oc-tc-input" id="oc-tc-hint" style="display:block;margin-top:8px;font-size:12px;color:var(--text-dim)"></label>' +
        '<input id="oc-tc-input" class="oc-prompt-input" type="text" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" style="width:100%;font-family:monospace;letter-spacing:1px">' +
        '<div class="btn-row" style="margin-top:14px">' +
          '<button id="oc-tc-cancel" class="oc-btn">取消 / Cancel</button>' +
          '<button id="oc-tc-confirm" class="oc-btn oc-btn-danger" disabled>確認</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);
  }

  document.getElementById('oc-tc-title').textContent = title;
  document.getElementById('oc-tc-body').textContent = body;
  var metaEl = document.getElementById('oc-tc-meta');
  var metaParts = [];
  if (actor) metaParts.push('Actor / 操作者：' + actor);
  if (impact) metaParts.push('影響 / Impact：' + impact);
  if (rollback) metaParts.push('回滾 / Rollback：' + rollback);
  if (metaParts.length) {
    metaEl.textContent = metaParts.join('\n');
    metaEl.style.display = '';
    metaEl.style.whiteSpace = 'pre-line';
  } else {
    metaEl.style.display = 'none';
  }
  var hintEl = document.getElementById('oc-tc-hint');
  hintEl.textContent = hint;
  var inputEl = document.getElementById('oc-tc-input');
  inputEl.value = '';
  inputEl.placeholder = phrase;
  var confirmBtn = document.getElementById('oc-tc-confirm');
  confirmBtn.textContent = confirmLabel;
  confirmBtn.className = 'oc-btn ' + confirmClass;
  confirmBtn.disabled = true;
  var cancelBtn = document.getElementById('oc-tc-cancel');

  overlay.classList.add('show');

  return new Promise(function(resolve) {
    var previousActive = document.activeElement;
    function focusableNodes() {
      return Array.prototype.slice.call(
        overlay.querySelectorAll('button,input,[tabindex]:not([tabindex="-1"])')
      ).filter(function(node) { return !node.disabled && node.offsetParent !== null; });
    }
    function close(val) {
      overlay.classList.remove('show');
      cancelBtn.onclick = null;
      confirmBtn.onclick = null;
      overlay.onkeydown = null;
      inputEl.oninput = null;
      if (previousActive && typeof previousActive.focus === 'function') {
        previousActive.focus();
      }
      resolve(val);
    }
    function checkPhrase() {
      // case-sensitive 比對；trim 避免尾部空白誤判
      var typed = (inputEl.value || '').replace(/\s+$/, '');
      confirmBtn.disabled = (typed !== phrase);
    }
    inputEl.oninput = checkPhrase;
    cancelBtn.onclick = function() { close(false); };
    confirmBtn.onclick = function() {
      if (confirmBtn.disabled) return;
      close(true);
    };
    overlay.onkeydown = function(ev) {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        close(false);
        return;
      }
      if (ev.key === 'Enter' && !confirmBtn.disabled) {
        ev.preventDefault();
        close(true);
        return;
      }
      if (ev.key !== 'Tab') return;
      var nodes = focusableNodes();
      if (!nodes.length) { ev.preventDefault(); return; }
      var first = nodes[0], last = nodes[nodes.length - 1];
      if (ev.shiftKey && document.activeElement === first) {
        ev.preventDefault(); last.focus();
      } else if (!ev.shiftKey && document.activeElement === last) {
        ev.preventDefault(); first.focus();
      }
    };
    setTimeout(function() { inputEl.focus(); }, 50);
  });
}

// REF-20 R20-P1-U8 Disabled State Card factory (UX subdoc §8 + CognitiveModulator「能力完整但門檻提高」). API: window.OpenClawDisabledStateCard.render(containerId, { phase, icon, gate_label/_zh/_i18n_key, banner_text/_zh/_i18n_key, phase_label_zh/_en, metrics_layout: 'compare_12'|'replay_12' }). XSS-safe + A11y + i18n via t_zh.
(function() {
  if (!document.getElementById('oc-disabled-card-css')) {
    var s = document.createElement('style'); s.id = 'oc-disabled-card-css';
    s.textContent = '.oc-disabled-card{position:relative;background:rgba(22,27,34,0.7);border:1px dashed var(--border);border-radius:var(--card-radius);padding:18px 20px 22px;margin-bottom:14px;opacity:0.78;cursor:not-allowed}.oc-disabled-card:focus{outline:2px solid var(--accent);outline-offset:2px}.oc-disabled-card:focus:not(:focus-visible){outline:none}.oc-disabled-card-header{display:flex;align-items:flex-start;gap:10px;margin-bottom:8px}.oc-disabled-card-icon{font-size:22px;line-height:1;flex-shrink:0;color:var(--text-dim)}.oc-disabled-card-title{flex:1;min-width:0}.oc-disabled-card-title h3{font-size:14px;font-weight:600;margin:0 0 2px;color:var(--text)}.oc-disabled-card-title .en{color:var(--text-dim);font-size:12px;font-weight:400;margin-top:2px}.oc-disabled-card-phase{flex-shrink:0;font-size:10px;font-weight:700;padding:3px 9px;border-radius:999px;background:rgba(210,153,34,0.15);color:var(--yellow);border:1px solid rgba(210,153,34,0.4);letter-spacing:0.4px}.oc-disabled-card-phase.phase-p3{background:rgba(56,139,253,0.15);color:var(--blue);border-color:rgba(56,139,253,0.4)}.oc-disabled-card-phase.phase-p6{background:rgba(248,81,73,0.12);color:var(--red);border-color:rgba(248,81,73,0.35)}.oc-disabled-card-banner{font-size:12px;color:var(--text-dim);line-height:1.6;padding:8px 12px;background:rgba(13,17,23,0.55);border-left:3px solid var(--text-dim);border-radius:4px;margin-top:6px}.oc-disabled-card-banner .zh{display:block;color:var(--text)}.oc-disabled-card-banner .en{display:block;color:var(--text-dim);font-size:11px;margin-top:2px}.oc-disabled-card-metrics{display:grid;gap:8px;margin-top:14px;grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}.oc-disabled-card-metric{background:rgba(13,17,23,0.4);border:1px dashed #21262d;border-radius:6px;padding:8px 10px;min-height:46px}.oc-disabled-card-metric .label{font-size:9px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.4px}.oc-disabled-card-metric .val{font-size:13px;color:var(--text-dim);font-weight:500;margin-top:4px;opacity:0.7}@media(max-width:700px){.oc-disabled-card{padding:14px 14px 16px}.oc-disabled-card-metrics{grid-template-columns:1fr 1fr}}';
    document.head.appendChild(s);
  }
  // 12-cell layout labels: compare_12 = UX §5 Compare metrics; replay_12 = UX §4 Replay 10 form + 2 status fields.
  // i18n helper: t_zh miss returns raw key path (documented), strict !== confirms a real hit.
  var LBLS = { compare_12: [['淨利 bps (扣費後)','Net bps after fees'],['毛利 bps','Gross bps'],['費用 bps','Fee bps'],['分位 q10','Quantile q10'],['分位 q50','Quantile q50'],['分位 q90','Quantile q90'],['95% 信賴區間','95% CI'],['最大回撤','Max drawdown'],['交易筆數','Trade count'],['拒單率','Reject rate'],['資料層級','Data tier'],['執行可信度','Execution confidence']], replay_12: [['幣種集合','Symbol set'],['時間框架','Timeframe'],['資料層級','Data tier'],['運行環境','Runtime env'],['基準配置','Baseline config'],['候選配置','Candidate config'],['行情視窗','Market window'],['費率模型','Fee model'],['執行模型','Execution model'],['輸出政策','Output policy'],['清單雜湊','Manifest hash'],['實驗 ID','Experiment ID']] };
  function i18n(k, fb) { if (typeof k !== 'string' || !k) return fb || ''; if (typeof window.t_zh === 'function') { var v = window.t_zh(k); if (typeof v === 'string' && v !== k && v.length > 0) return v; } return fb || ''; }
  window.OpenClawDisabledStateCard = { render: function(containerId, opts) {
    var el = document.getElementById(containerId);
    if (!el) { console.warn('[OpenClawDisabledStateCard.render] container not found: ' + containerId); return false; }
    opts = opts || {};
    // P2/P3/P6 allowlist for phase chip variant; others fallback to P2 yellow visual.
    var p = String(opts.phase || '').toUpperCase(), pSlug = p === 'P3' ? 'phase-p3' : p === 'P6' ? 'phase-p6' : 'phase-p2', pZh = opts.phase_label_zh || (p ? p + ' 待啟用' : '待啟用'), pEn = opts.phase_label_en || (p ? p + ' Pending' : 'Pending'), gateZh = i18n(opts.gate_label_i18n_key, opts.gate_label_zh || ''), gateEn = opts.gate_label || ((!gateZh && !opts.gate_label) ? 'Disabled — gate pending' : ''), bannerZh = i18n(opts.banner_i18n_key, opts.banner_text_zh || ''), bannerEn = opts.banner_text || '', icon = opts.icon || '🔒', lbls = LBLS[opts.metrics_layout], metricsHtml = lbls ? ('<div class="oc-disabled-card-metrics">' + lbls.map(function(l) { return '<div class="oc-disabled-card-metric"><div class="label">' + ocEsc(l[0]) + '</div><div class="val" aria-hidden="true">— pending —</div><div class="label" style="opacity:0.5;margin-top:2px">' + ocEsc(l[1]) + '</div></div>'; }).join('') + '</div>') : '';
    el.innerHTML = '<div class="oc-disabled-card" role="status" aria-disabled="true" tabindex="0" title="' + ocEsc(gateZh || gateEn) + '"><div class="oc-disabled-card-header"><span class="oc-disabled-card-icon" aria-hidden="true">' + ocEsc(icon) + '</span><div class="oc-disabled-card-title"><h3>' + (gateZh ? '<span class="zh">' + ocEsc(gateZh) + '</span>' : '') + '</h3>' + (gateEn ? '<div class="en">' + ocEsc(gateEn) + '</div>' : '') + '</div><span class="oc-disabled-card-phase ' + ocSanitizeClass(pSlug) + '" aria-label="' + ocEsc(pZh + (pEn && pEn !== pZh ? ' / ' + pEn : '')) + '">' + ocEsc(pZh) + '</span></div>' + ((bannerZh || bannerEn) ? ('<div class="oc-disabled-card-banner">' + (bannerZh ? '<span class="zh">' + ocEsc(bannerZh) + '</span>' : '') + (bannerEn ? '<span class="en">' + ocEsc(bannerEn) + '</span>' : '') + '</div>') : '') + metricsHtml + '</div>';
    return true;
  } };
})();
