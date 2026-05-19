/**
 * 玄衡 · Arcane Equilibrium — Mode Badge Component (REF-20 R20-P1-U7)
 *
 * MODULE_NOTE
 * 模組用途：4 維 inline pill 化 mode badge — 在 Paper Replay Lab 顯示
 *          每個 replay 結果的「資料層級 / 輸出策略 / 校準新鮮度 / 執行可信度」
 *          四個維度，配合 UX subdoc §7 防認知欺詐 + §10 a11y 規範。
 * 主要 helper：_OC_MODE_BADGE_DEFS、_ocResolveModeBadge、
 *              _ocLookupModeBadgeStateLabel、_ocRenderModeBadgePill。
 * 公開 API：window.OpenClawModeBadge.render / update / describe。
 * CSS 注入：_ocInjectModeBadgeCSS IIFE 在 script 載入時就會把 mode-badge
 *          專用 CSS 加到 document.head（依賴 oc-base-css 變數，但 CSS 規則
 *          不需在 ocInjectBaseCSS 之後執行）。
 * 依賴：common-formatters.js 已先載入 — 本檔需 ocEsc / ocSanitizeClass。
 *      i18n_zh.js 為 optional dependency；若未載入，state label 自動回退
 *      def 內既有 label_zh / label_en。
 * 硬邊界：防誤觸詐核心—execution_confidence='none' 必灰底 + ⚠️ icon
 *         + tooltip + 紅邊。所有動態文字必經 ocEsc，所有 class token 必經
 *         ocSanitizeClass，禁直接 innerHTML 拼接外部資料。
 *
 * P2-COMMON-JS-LOC 拆分歷史：原 common.js 行 1348–1742 內聚搬出，以維持
 * §九 2000 LOC 硬上限。
 *
 * 上游契約：
 *   - UX subdoc §7 Mode Badges
 *   - Workplan §4 Wave 2 R20-P1-U7
 *   - V3 §12 #25 replay_ml_maturity_label（雙驗 DB + UI surface）
 *
 * i18n hook：tooltip 文案此版本 EN inline + 中文輔助；REF-20 R20-P1-U9 將以
 * `i18n_zh.js` 對照表替換 `_OC_MODE_BADGE_DEFS` 內的 label/tip 字串。
 *
 * 注意（ambiguity for PM/A3 review）：UX subdoc §7 列出的 4 維是 run_mode /
 * data_tier / execution_confidence / runtime_environment；本任務 dispatch 文
 * 的 4 維為 data_tier / output_policy / calibration_freshness / execution_confidence。
 * 本 component 將 task dispatch 的 4 維作為 canonical mock seed，並在
 * `_OC_MODE_BADGE_DEFS` 同時保留 UX subdoc §7 的兩個備援 dimension（run_mode /
 * runtime_environment），待 PM/A3 final 對齊後選一套呈現。
 */

// State → variant 顏色對應表（per UX subdoc §10 「不可只靠顏色」原則：每個
// state 同時帶 icon + 文字 label，並控制色僅作為輔助視覺信號）。
//
// variant 對應 oc-chip 樣式：good=綠 / info=藍 / warn=黃 / bad=紅 / neutral=灰。
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
      // 'none' = 防誤觸詐 SENTINEL：灰底 + ⚠️ + tooltip + 紅邊（卡片右上）。Renderer 加
      // data-confidence-none="1" 屬性以便 caller card 套紅外框，依 UX subdoc §7 Rule 1。
      none:    { variant: 'bad',     icon: '⚠', label_en: 'None',    label_zh: '無',         tip_en: 'Execution confidence=none — result is NOT actionable', tip_zh: '執行可信度為「無」— 結果不可作為實盤依據', danger: true },
    },
  },
  // ── UX subdoc §7 補充維度（暫不放 mock seed，等 PM/A3 final）─────────────
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

// 內部輔助：把 (dimension, state) 元組解析為渲染所需的 metadata。
// 任一缺失即回退中性 unknown 形狀；component 不可在資料缺失時拋例外，
// 因為 P1 階段 mock state 全 unknown / none。
function _ocResolveModeBadge(dim, state) {
  var def = _OC_MODE_BADGE_DEFS[dim];
  if (!def) {
    return null;  // 未知 dimension 直接 skip
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
function _ocLookupModeBadgeStateLabel(meta) {
  if (!meta) return '';
  var keyPath = 'mode_badge.' + meta.dim + '.' + meta.state;
  if (typeof window.t_zh === 'function') {
    var looked = window.t_zh(keyPath);
    // t_zh miss → return raw key path; 用 strict !== 確認真有 hit。
    if (typeof looked === 'string' && looked !== keyPath && looked.length > 0) {
      return looked;
    }
  }
  return meta.label_zh || meta.label_en || '';
}

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
function _ocRenderModeBadgePill(meta) {
  if (!meta) return '';
  // 防誤觸詐：execution_confidence=none 用 bad variant + ⚠️ icon + 紅邊框
  var variant = ocSanitizeClass(meta.variant);
  var dimSlug = ocSanitizeClass(meta.dim);
  var stateSlug = ocSanitizeClass(meta.state);
  var dangerAttr = meta.danger ? ' data-confidence-none="1"' : '';
  // i18n lookup: state label 優先取 i18n_zh.js `mode_badge.<dim>.<state>`
  // 中文；t_zh 缺載入或 miss → fallback def 既有 label_zh → label_en。
  var dimLabel = ocEsc(meta.dim_label_zh || meta.dim_label_en);
  var stateLabel = ocEsc(_ocLookupModeBadgeStateLabel(meta));
  var icon = ocEsc(meta.icon);
  var tipEn = meta.tip_en || '';
  var tipZh = meta.tip_zh || '';
  // operator 中文 dominant：tooltip 用「zh / EN」順序 (operator 直視 channel)；
  // aria-label (screen reader) 仍保 EN 在前以維護 a11y baseline。
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
      var tmp = document.createElement('div');
      tmp.innerHTML = html;
      var fresh = tmp.firstChild;
      if (fresh) existing.replaceWith(fresh);
    } else {
      // 該 dim 尚未存在於列中，append 到尾端。
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
