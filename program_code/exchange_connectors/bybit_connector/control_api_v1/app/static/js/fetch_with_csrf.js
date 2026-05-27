/*
 * fetch_with_csrf.js — OPS-1 Track B CSRF helper for GUI fetch chains.
 *
 * 為什麼存在：所有 GUI 寫操作（POST/PUT/DELETE/PATCH）必須帶上
 * `X-CSRF-Token` header，值來自登入後設定的 `oc_csrf` cookie
 * （非 HttpOnly，可被 JS 讀）。本檔提供：
 *
 *   - ocReadCsrfToken()    — 從 document.cookie 讀 oc_csrf 值
 *   - ocCsrfHeaders(opts)  — 在既有 headers 上補 X-CSRF-Token
 *   - ocFetchWithCsrf(path, opts) — fetch wrapper：寫操作自動補 CSRF header
 *
 * 設計重點：
 *   - 讀操作（GET / HEAD / OPTIONS）不附 token，避免污染快取 / log
 *   - 不依賴特定 framework（vanilla JS，與 CLAUDE.md §九 對齊）
 *   - 不重複實作 timeout / error toast — 留給 ocApi() 套用本 helper 後處理
 *
 * 既有 common.js::ocApi() 已串入本 helper，所以多數 callsite 不必直接呼叫
 * ocFetchWithCsrf。若有第三方 inline 寫操作（例如新 tab JS），請改走 ocApi
 * 或 ocFetchWithCsrf，不要直接呼 fetch()。
 */

(function () {
  'use strict';

  const _WRITE_METHODS = new Set(['POST', 'PUT', 'DELETE', 'PATCH']);

  /**
   * 從 document.cookie 讀取指定 cookie 名稱的值。
   * 為什麼自寫而不用第三方：避免引入依賴，cookie 解析邏輯固定。
   */
  function ocReadCookie(name) {
    if (typeof document === 'undefined' || !document.cookie) return '';
    const pairs = document.cookie.split(';');
    for (let i = 0; i < pairs.length; i++) {
      const trimmed = pairs[i].trim();
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx < 0) continue;
      if (trimmed.substring(0, eqIdx) === name) {
        return decodeURIComponent(trimmed.substring(eqIdx + 1));
      }
    }
    return '';
  }

  /**
   * 讀取 oc_csrf cookie 的值。登入前回傳空字串（前端應拒絕送寫操作）。
   */
  function ocReadCsrfToken() {
    return ocReadCookie('oc_csrf');
  }

  /**
   * 在現有 headers 物件上補 X-CSRF-Token。
   * 寫操作必補；讀操作返回原 headers。
   */
  function ocCsrfHeaders(method, headers) {
    headers = headers || {};
    const upperMethod = (method || 'GET').toUpperCase();
    if (!_WRITE_METHODS.has(upperMethod)) return headers;
    const token = ocReadCsrfToken();
    if (token) {
      headers['X-CSRF-Token'] = token;
    }
    return headers;
  }

  /**
   * fetch wrapper：寫操作自動補 X-CSRF-Token；讀操作直接 pass-through。
   * 為什麼：給未走 ocApi() 的 callsite（例如 tab-*.html inline <script>）
   * 一個最小替換目標。GET / HEAD / OPTIONS 走原 fetch 行為。
   */
  function ocFetchWithCsrf(path, opts) {
    opts = opts || {};
    opts.headers = ocCsrfHeaders(opts.method, opts.headers);
    if (!('credentials' in opts)) opts.credentials = 'same-origin';
    return fetch(path, opts);
  }

  // ─── Export to window ────────────────────────────────────────────────────
  window.ocReadCsrfToken = ocReadCsrfToken;
  window.ocCsrfHeaders = ocCsrfHeaders;
  window.ocFetchWithCsrf = ocFetchWithCsrf;
})();
