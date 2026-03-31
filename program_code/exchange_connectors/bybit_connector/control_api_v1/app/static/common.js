/**
 * OpenClaw Trading System — Shared Utilities
 * 共享工具库：认证、API 调用、格式化、解释模式
 */

// ─── Auth ────────────────────────────────────────────────────────────────────
const OC_TOKEN_KEY = 'oc_trading_token';
const OC_USER_KEY = 'oc_username';

function ocAuthCheck() {
  if (!localStorage.getItem(OC_TOKEN_KEY)) {
    sessionStorage.setItem('oc_login_redirect', '/console');
    window.location.href = '/login';
    return false;
  }
  return true;
}

function ocGetToken() {
  return localStorage.getItem(OC_TOKEN_KEY) || '';
}

function ocLogout() {
  localStorage.removeItem(OC_TOKEN_KEY);
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
  const token = ocGetToken();
  if (!token) return null;
  if (_ocAuthFails >= _OC_AUTH_MAX) {
    console.warn('[ocApi] Auth lockout active (' + _ocAuthFails + ' failures). Probing...');
  }

  const method = (opts && opts.method) || 'GET';
  const headers = { 'Authorization': 'Bearer ' + token };
  if (opts && opts.body) headers['Content-Type'] = 'application/json';

  try {
    const r = await fetch(path, {
      method: method,
      headers: headers,
      body: opts && opts.body ? JSON.stringify(opts.body) : undefined,
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
    operator_id: localStorage.getItem(OC_USER_KEY) || 'gui-operator',
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
  // Display symbol for current currency: 'USDT ', '$', or '€'
  // 当前货币显示符号
  const c = ocCurrCode();
  if (c === 'EUR')  return '€';
  if (c === 'USDT') return 'USDT ';
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
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ─── Sanitize CSS class name (P2-NEW-6) ─────────────────────────────────────
// Only allow letters, digits, hyphens, underscores — strip everything else.
// 僅允許字母、數字、連字符、底線，其餘字符全部過濾。
function ocSanitizeClass(s) {
  if (s == null) return '';
  return String(s).replace(/[^a-zA-Z0-9\-_]/g, '');
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
function ocToast(msg, type) {
  const toast = document.createElement('div');
  toast.className = 'oc-toast oc-toast-' + (type || 'info');
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.classList.add('show'), 10);
  setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 3000);
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
    }

    /* Separator */
    .oc-sep { border: none; border-top: 1px solid #21262d; margin: 14px 0; }

    /* Toast */
    .oc-toast { position: fixed; bottom: 20px; right: 20px; padding: 10px 18px;
      border-radius: 8px; font-size: 13px; z-index: 9999; transform: translateY(20px);
      opacity: 0; transition: all 0.3s; pointer-events: none; }
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
  `;
  document.head.appendChild(style);
}
