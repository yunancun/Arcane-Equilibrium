/**
 * 玄衡 · Arcane Equilibrium — Modal Dialogs + Disabled State Card
 *
 * MODULE_NOTE
 * 模組用途：共用 modal SDK。3 個 modal 函式 + 1 個 DisabledStateCard factory：
 *   - openConfirmModal: 一般確認彈窗（reset / unhalt / delete / paper-stop-all 等預設）
 *   - openPromptModal: 輸入彈窗（text / textarea / select），支援 placeholder /
 *                       maxlength / char-counter（A3-MAJOR-2）
 *   - openTypedConfirmModal: 高摩擦確認彈窗，要求 user 鍵入 phrase 才啟用確認按鈕
 *                            （A3 v2 audit governance critical 寫操作必用）
 *   - window.OpenClawDisabledStateCard.render: P2/P3/P6 disabled state card factory
 *                                              （REF-20 R20-P1-U8）
 *
 * 共用 lock：3 個 modal 共用 module-level `_OC_MODAL_OPEN_LOCK`（A3-HIGH-3 fix）
 *           — 任一開啟即拒絕其他 modal，避免 onclick handler 互相覆蓋與
 *           microtask race window。
 *
 * 依賴：common-formatters.js 已先載入 — 本檔需 ocEsc / ocSanitizeClass
 *      （DisabledStateCard render 路徑用）。i18n_zh.js 為 optional dependency。
 *
 * 硬邊界：每個 modal 必在 close()/cleanup() 路徑釋放 `_OC_MODAL_OPEN_LOCK`，
 *         否則永久 deadlock。所有 innerHTML 拼接外部資料一律經 ocEsc。
 *
 * P2-COMMON-JS-LOC 拆分歷史：原 common.js 行 1744–2198 內聚搬出，以維持
 * §九 2000 LOC 硬上限。
 */

// A3-HIGH-3 fix (WP-01 Wave 1 follow-up)：module-level modal 鎖。
// 取代 DOM-state guard（`overlay.classList.contains('show')`）— DOM class 變更與
// microtask 之間存在 race window，第二個並發呼叫可能在 add('show') 前通過 guard。
// 設計：所有 3 個 modal（openConfirmModal / openTypedConfirmModal / openPromptModal）
// 共用同一 lock；任一開啟即拒絕其他 modal，避免 onclick handler 互相覆蓋。
// 釋放點：close()/cleanup() 一定要清 lock，否則永久 deadlock。
var _OC_MODAL_OPEN_LOCK = false;

/** Per-action metadata for dangerous operations / 危險操作的确認文本元數據 */
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
 * 顯示自定义确認弹窗，返回 Promise<boolean>。
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

  // 懶加載注入 overlay 元素
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

  // A3-HIGH-3 fix (WP-01 Wave 1 follow-up)：module-level lock 取代 DOM-state guard。
  // 舊 `overlay.classList.contains('show')` 是 DOM-class 檢查，存在 microtask race；
  // 改為 _OC_MODAL_OPEN_LOCK module-scope flag，所有 3 個 modal 共用同一鎖。
  if (_OC_MODAL_OPEN_LOCK) {
    return Promise.reject(new Error('openConfirmModal: modal_locked'));
  }
  _OC_MODAL_OPEN_LOCK = true;

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
      // 移除監听防止重復触发
      cancelBtn.onclick = null;
      confirmBtn.onclick = null;
      overlay.onkeydown = null;
      // A3-HIGH-3 fix：釋放 module-level lock，否則永久 deadlock
      _OC_MODAL_OPEN_LOCK = false;
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
  // A3-MAJOR-2 fix (WP-01 Wave 1 follow-up)：placeholder / maxlength / char-counter 支援，
  // 用於取代 canary-tab.js 自製 oc-promote-reason overlay。
  var placeholder = meta.placeholder == null ? '' : String(meta.placeholder);
  var maxlength = (typeof meta.maxlength === 'number' && meta.maxlength > 0) ? meta.maxlength : 0;

  // A3-HIGH-3 fix (WP-01 Wave 1 follow-up)：module-level lock 拒絕並發開啟
  if (_OC_MODAL_OPEN_LOCK) {
    console.error('[openPromptModal] modal already open; rejecting concurrent open');
    return Promise.reject(new Error('openPromptModal: modal_locked'));
  }
  _OC_MODAL_OPEN_LOCK = true;

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
        '<div id="oc-gp-counter" style="text-align:right;font-size:11px;color:var(--text-dim);display:none"><span id="oc-gp-counter-cur">0</span>/<span id="oc-gp-counter-max">0</span></div>' +
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

  // A3-MAJOR-2 fix：apply placeholder / maxlength / counter（取代 canary-tab.js 自製 overlay）
  // text input / textarea 才支援 placeholder + maxlength；select 跳過
  if (!choices) {
    if (multiline) {
      textareaEl.placeholder = placeholder;
      if (maxlength > 0) textareaEl.setAttribute('maxlength', String(maxlength));
      else textareaEl.removeAttribute('maxlength');
    } else {
      inputEl.placeholder = placeholder;
      if (maxlength > 0) inputEl.setAttribute('maxlength', String(maxlength));
      else inputEl.removeAttribute('maxlength');
    }
  }
  var counterEl = document.getElementById('oc-gp-counter');
  var counterCurEl = document.getElementById('oc-gp-counter-cur');
  var counterMaxEl = document.getElementById('oc-gp-counter-max');
  if (maxlength > 0 && !choices) {
    counterEl.style.display = '';
    counterMaxEl.textContent = String(maxlength);
    counterCurEl.textContent = String(defaultValue.length);
  } else {
    counterEl.style.display = 'none';
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
      // A3-MAJOR-2 fix：清 oninput handler 避免下次 modal 殘留
      if (activeField) activeField.oninput = null;
      // A3-HIGH-3 fix：釋放 module-level lock
      _OC_MODAL_OPEN_LOCK = false;
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
    // A3-MAJOR-2 fix：char-counter input handler（maxlength > 0 才啟用）
    if (maxlength > 0 && !choices) {
      activeField.oninput = function() { counterCurEl.textContent = String(value().length); };
    } else {
      activeField.oninput = null;
    }
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
  // W-AUDIT-7c round 2 [#7] + A3-HIGH-3 fix (WP-01 Wave 1 follow-up)：
  // 升級為 module-level lock，與 openConfirmModal / openPromptModal 共用同一鎖；
  // 舊 DOM-state guard（classList.contains('show')）有 microtask race window。
  if (_OC_MODAL_OPEN_LOCK) {
    console.error('[openTypedConfirmModal] modal already open; rejecting concurrent open');
    return Promise.reject(new Error('openTypedConfirmModal: modal_locked'));
  }
  _OC_MODAL_OPEN_LOCK = true;
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
      // A3-HIGH-3 fix：釋放 module-level lock
      _OC_MODAL_OPEN_LOCK = false;
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
