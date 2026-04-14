/**
 * OpenClaw Trading System — Shared Utilities
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
        sessionStorage.setItem('oc_login_redirect', window.location.pathname || '/console');
        window.location.href = '/login';
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

function ocPct(v) {
  if (v == null || isNaN(v)) return '--';
  return (v * 100).toFixed(1) + '%';
}

function ocTime(ts) {
  if (!ts) return '--';
  const d = typeof ts === 'number' ? new Date(ts > 1e12 ? ts : ts * 1000) : new Date(ts);
  return d.toLocaleString('zh-CN', { hour12: false });
}

function ocTimeShort(ts) {
  if (!ts) return '--';
  const d = typeof ts === 'number' ? new Date(ts > 1e12 ? ts : ts * 1000) : new Date(ts);
  return d.toLocaleTimeString('zh-CN', { hour12: false });
}

function ocPnlClass(v) {
  if (v == null) return '';
  return v >= 0 ? 'green' : 'red';
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
  if (el) el.textContent = text != null ? text : '--';
}

function ocSetHtml(id, html) {
  const el = $(id);
  if (el) el.innerHTML = html;
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

    /* Status Chips */
    .oc-chip { display: inline-flex; align-items: center; gap: 5px; border-radius: 999px;
      padding: 3px 10px; font-size: 11px; font-weight: 500; border: 1px solid transparent; }
    .oc-chip-good { background: rgba(63,185,80,0.12); border-color: rgba(63,185,80,0.25); color: var(--green); }
    .oc-chip-warn { background: rgba(210,153,34,0.12); border-color: rgba(210,153,34,0.25); color: var(--yellow); }
    .oc-chip-bad { background: rgba(248,81,73,0.12); border-color: rgba(248,81,73,0.25); color: var(--red); }
    .oc-chip-neutral { background: rgba(139,148,158,0.1); border-color: rgba(139,148,158,0.2); color: var(--text-dim); }
    .oc-chip-info { background: rgba(56,139,253,0.12); border-color: rgba(56,139,253,0.25); color: var(--blue); }
    .oc-chip-live { background: rgba(168,85,247,0.12); border-color: rgba(168,85,247,0.3); color: #a855f7; }

    /* Colors */
    .green { color: var(--green); } .red { color: var(--red); }
    .yellow { color: var(--yellow); } .blue { color: var(--blue); }

    /* Control Bar */
    .oc-control-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      padding: 12px 16px; background: var(--card-bg); border: 1px solid var(--border);
      border-radius: var(--card-radius); margin-bottom: 14px; }

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
    .oc-btn-danger { background: rgba(248,81,73,0.08); border-color: rgba(248,81,73,0.3); color: var(--red); }
    .oc-btn-danger:hover { background: rgba(248,81,73,0.2); }
    .oc-btn-future { border-style: dashed; opacity: 0.4; cursor: default; }
    .oc-btn-future:hover { border-color: var(--border); color: var(--text); }

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
    .oc-strat-card { background: var(--bg); border: 1px solid #21262d; border-radius: 8px; padding: 14px; }
    .oc-strat-card .strat-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .oc-strat-card .strat-name { font-weight: 600; font-size: 14px; }
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
  }
};

/**
 * Show a custom confirmation dialog and return Promise<boolean>.
 * 显示自定义确认弹窗，返回 Promise<boolean>。
 * @param {string} actionName - action key from _OC_CONFIRM_ACTIONS, or plain title text
 * @returns {Promise<boolean>}
 */
function openConfirmModal(actionName) {
  const meta = _OC_CONFIRM_ACTIONS[actionName] || {
    title: actionName || '確認操作 / Confirm Action',
    body: '此操作將立即執行，無法撤銷。\nThis action cannot be undone.',
    confirmLabel: '確認 / Confirm'
  };

  // Lazily inject overlay element / 懶加載注入 overlay 元素
  let overlay = document.getElementById('oc-generic-confirm-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'oc-generic-confirm-overlay';
    overlay.className = 'oc-confirm-overlay';
    overlay.innerHTML =
      '<div class="oc-confirm-dialog">' +
        '<h3 id="oc-gc-title"></h3>' +
        '<p id="oc-gc-body"></p>' +
        '<div class="btn-row">' +
          '<button id="oc-gc-cancel" class="oc-btn">取消 / Cancel</button>' +
          '<button id="oc-gc-confirm" class="oc-btn oc-btn-danger">確認</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);
  }

  document.getElementById('oc-gc-title').textContent = meta.title;
  document.getElementById('oc-gc-body').textContent = meta.body;
  var confirmBtn = document.getElementById('oc-gc-confirm');
  confirmBtn.textContent = meta.confirmLabel || '確認 / Confirm';
  overlay.classList.add('show');

  return new Promise(function(resolve) {
    function close(val) {
      overlay.classList.remove('show');
      // Remove handlers to prevent duplicate firing / 移除监听防止重复触发
      document.getElementById('oc-gc-cancel').onclick = null;
      confirmBtn.onclick = null;
      resolve(val);
    }
    document.getElementById('oc-gc-cancel').onclick = function() { close(false); };
    confirmBtn.onclick = function() { close(true); };
  });
}
