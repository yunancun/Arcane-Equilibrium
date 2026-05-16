/**
 * Risk Tab — Inline script extracted from tab-risk.html.
 * 風控頁面 — 從 tab-risk.html 提取的內嵌腳本。
 *
 * MODULE_NOTE (EN): Extracted from tab-risk.html (FIX-08 file size).
 * MODULE_NOTE (中): 從 tab-risk.html 提取（FIX-08 文件大小）。
 */

// ─── Modal CSS ────────────────────────────────────────────────
if (!document.getElementById('oc-modal-css')) {
  const modalStyle = document.createElement('style');
  modalStyle.id = 'oc-modal-css';
  modalStyle.textContent = `
    .oc-modal { position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); display:flex; align-items:center; justify-content:center; z-index:1000; }
    .oc-modal-content { background:var(--card-bg); border-radius:12px; padding:24px; width:480px; max-width:90vw; }
  `;
  document.head.appendChild(modalStyle);
}

// ─── Risk Governor Constants ────────────────────────────────────
const RISK_LEVEL_NAMES = ['NORMAL', 'CAUTIOUS', 'REDUCED', 'DEFENSIVE', 'CIRCUIT_BREAKER', 'MANUAL_REVIEW'];
const RISK_LEVEL_COLORS = { 0: 'good', 1: 'good', 2: 'warn', 3: 'warn', 4: 'bad', 5: 'bad' };
let _currentRiskLevel = null;

// ─── Risk Governor Functions ───────────────────────────────────
async function loadRiskGovernor() {
  try {
    const d = await ocApi('/api/v1/governance/risk/level');
    if (!d || !d.ok || !d.data) {
      ocSetHtml('rg-level', '—');
      ocSetHtml('rg-name', '—');
      ocSetHtml('rg-reason', '—');
      ocSetHtml('rg-mode', '—');
      document.getElementById('rg-override-btn').style.display = 'none';
      return;
    }
    const r = d.data;
    _currentRiskLevel = r.level;

    // Level with color badge
    ocSetHtml('rg-level', ocChip(String(r.level), RISK_LEVEL_COLORS[r.level] || 'neutral'));
    ocSetHtml('rg-name', ocChip(r.level_name || RISK_LEVEL_NAMES[r.level] || '?', RISK_LEVEL_COLORS[r.level] || 'neutral'));
    ocSetHtml('rg-reason', ocEsc(r.escalation_reason || 'None / 無'));

    // Mode badge
    const modeColors = { NORMAL: 'good', RESTRICTED: 'warn', FROZEN: 'bad', MANUAL_REVIEW: 'info' };
    ocSetHtml('rg-mode', ocChip(r.mode || '—', modeColors[r.mode] || 'neutral'));

    // Show override button only if level > 0 (can de-escalate)
    document.getElementById('rg-override-btn').style.display = r.level > 0 ? '' : 'none';
  } catch (e) {
    console.warn('Risk governor unavailable:', e);
  }
}

function showRiskOverrideModal() {
  const sel = document.getElementById('rg-target-level');
  sel.innerHTML = '';
  // Only show levels BELOW current (de-escalation)
  for (let i = 0; i < _currentRiskLevel; i++) {
    const opt = document.createElement('option');
    opt.value = RISK_LEVEL_NAMES[i];
    opt.textContent = i + ' — ' + RISK_LEVEL_NAMES[i];
    sel.appendChild(opt);
  }
  document.getElementById('rg-override-reason').value = '';
  document.getElementById('modal-risk-override').style.display = 'flex';
}

function closeRiskOverrideModal() {
  document.getElementById('modal-risk-override').style.display = 'none';
}

async function submitRiskOverride() {
  const level = document.getElementById('rg-target-level').value;
  const reason = document.getElementById('rg-override-reason').value.trim();
  if (!reason || reason.length < 1) {
    ocToast('Please enter a reason / 請輸入原因', 'error');
    return;
  }
  try {
    const d = await ocPost('/api/v1/governance/risk/override', {
      target_level: level,
      reason: reason
    });
    document.getElementById('modal-risk-override').style.display = 'none';
    if (d && d.ok) {
      ocToast('Risk level de-escalated / 風險等級已降級', 'success');
    } else {
      ocToast('Override failed: ' + (d?.message || 'Unknown error'), 'error');
    }
    await loadRiskGovernor();
  } catch (e) {
    ocToast('Override error / 降級失敗: ' + e.message, 'error');
  }
}

// ─── Explainers ───────────────────────────────────────────────
$('rg-explainer').innerHTML = ocExplain(
  'SM-04 Risk Governor monitors system risk and auto-escalates when thresholds are breached. Only de-escalation (lowering the level) is allowed via override.',
  'SM-04 風險治理狀態機監控系統風險，當閾值被突破時自動升級。只允許通過覆蓋操作進行降級（降低等級）。六個等級：NORMAL (0) → CAUTIOUS (1) → REDUCED (2) → DEFENSIVE (3) → CIRCUIT_BREAKER (4) → MANUAL_REVIEW (5)。升級可自動觸發，降級需要 Operator 手動審批。'
);

$('explain-risk').innerHTML = ocExplain(
  '風控系統保護你的資金安全。它使用三層保護：品類限制（最嚴格）、全局限制（中等）、AI 可調參數（最靈活）。當風險過高時，系統會自動降低倉位或暫停交易。',
  '風控框架採用 P0/P1/P2 三層架構。P0 是按品類的硬上限（如單品種最大持倉、資金費率上限），由人工設定且不可被 AI 覆蓋。P1 是全局限制（最大槓桿、最大回撤、最大敞口百分比）。P2 是 AI 可自主調整的參數（止損百分比、跟蹤止損、倉位大小），Agent 會根據市場 regime 和歷史表現動態調整這些參數。'
);

$('explain-p0').innerHTML = ocExplain(
  '按交易品類設定的硬性限制，是最嚴格的一層保護。',
  'P0 限制包括：單品種最大持倉量、資金費率閾值（超過此值不開新倉）、最大持倉數量。這些參數由人工設定，AI 不能修改。'
);

$('explain-p1').innerHTML = ocExplain(
  '全局風控參數，適用於所有交易。',
  'P1 參數包括：最大槓桿倍數、最大總回撤百分比（觸發後暫停交易）、最大總敞口百分比（所有持倉市值占賬戶比例上限）、單筆最大風險百分比。'
);

$('explain-p2').innerHTML = ocExplain(
  'AI Agent 可以根據市場狀態自動調整的參數。',
  'P2 參數包括：止損百分比、跟蹤止損距離、倉位大小系數。AI 根據市場波動率、趨勢強度、近期盈虧來動態調整這些參數。例如在高波動市場中，AI 會自動縮小倉位、收緊止損。'
);

$('explain-stops').innerHTML = ocExplain(
  '在這裡設置止損硬限制。修改左側數值後點擊"保存設置"即可生效。這些是人工設定的硬邊界，AI Agent 不能超越這些限制。',
  'Hard Stop 是單筆最大虧損百分比，觸發後立即平倉不可撤銷。Trailing Stop 會跟隨最高價格移動，從最高點回撤超過設定百分比時觸發。Time Stop 防止長時間持倉占用資金。Max Session Drawdown 是賬戶級別的回撤保護，觸發後暫停所有交易。Max Leverage 限制單筆最大槓桿。Daily Loss 是當日虧損上限。'
);

$('explain-ai-consult').innerHTML = ocExplain(
  '讓 AI 分析你當前的交易狀況並給出止損建議。選擇模型和風格，點擊"詢問"按鈕，AI 會根據你的持倉、市場狀態和歷史表現給出具體建議。你可以選擇是否採納。',
  'AI 會獲取以下信息來生成建議：當前所有持倉的詳情、最近交易的勝率和回撤數據、當前市場 regime（趨勢/震盪）、波動率水平。基於這些信息，AI 會推薦具體的止損百分比、跟蹤止損距離和時間止損設置。不同模型的深度和成本不同：Haiku 最快最便宜但分析較淺，Opus 最深入但成本較高。'
);

$('explain-ai-risk').innerHTML = ocExplain(
  'AI 基於當前市場狀況給出的風控建議和壓力評估。',
  'AI 風控上下文包含：當前風險壓力水平（綜合回撤、波動率、連續虧損等因素）、建議的倉位調整、影響因素清單。這些信息供 P2 層的自動調整參考。'
);

$('explain-danger').innerHTML = ocExplain(
  '這些是緊急操作按鈕。只有在你確定系統誤判時才使用。"Reset Cooldown" 清除連續虧損後的冷卻期，允許繼續交易。"Unhalt Session" 解除熔斷保護，恢復被暫停的交易會話。',
  '冷卻期是連續虧損達到閾值後自動觸發的保護機制，防止情緒化追單。熔斷是回撤達到 P1 設定閾值後的強制暫停。手動解除這些保護意味著你承認當前的觸發條件是合理的但你選擇繼續——這需要格外謹慎。'
);

// ─── Save Risk Config ─────────────────────────────────────────
function toggleTPInputs() {
  const enabled = $('in-tp-enabled').checked;
  $('in-take-profit').disabled = !enabled;
  if (!enabled) $('in-take-profit').style.opacity = '0.4';
  else $('in-take-profit').style.opacity = '1';
}

// ─── LIVE-P2-2: Per-engine risk selector (paper|demo|live) ────────────────────
// Default to 'demo' since PAPER-DISABLE-1 (2026-04-16): paper pipeline is
// intentionally drained unless OPENCLAW_ENABLE_PAPER=1 is set, so landing on
// 'paper' makes the Rust engine look offline even when demo+live are healthy.
// Demo is the primary learning/edge-accumulation channel per project_edge_data_isolation.md.
// 預設選 demo：PAPER-DISABLE-1 後 paper 預設 drain，落在 paper 會讓 Rust 引擎看起來離線；
// demo 才是主要學習/edge 累積通道。
let _selectedRiskEngine = 'demo';
let _liveRiskSavePendingCallback = null;
let _paperRiskEngineEnabled = true;

function applyPaperRiskAvailability(enabled) {
  _paperRiskEngineEnabled = !!enabled;
  const paperBtn = $('etab-paper');
  if (paperBtn) {
    paperBtn.style.display = _paperRiskEngineEnabled ? '' : 'none';
  }
  if (!_paperRiskEngineEnabled && _selectedRiskEngine === 'paper') {
    selectRiskEngine('demo');
  }
}

async function loadPaperRiskAvailability() {
  const d = await ocApi('/api/v1/settings/paper-engine');
  const data = (d && d.data) ? d.data : d;
  if (!data) return;
  applyPaperRiskAvailability(!!data.enabled);
}

function selectRiskEngine(engine) {
  if (engine === 'paper' && !_paperRiskEngineEnabled) {
    engine = 'demo';
  }
  _selectedRiskEngine = engine;
  ['paper', 'demo', 'live'].forEach(e => {
    const b = $('etab-' + e);
    if (!b) return;
    const active = e === engine;
    b.style.opacity = active ? '1' : '0.55';
    b.style.background = active ? (e === 'live' ? 'rgba(248,81,73,0.15)' : 'rgba(56,139,253,0.15)') : '';
    b.style.borderColor = active ? (e === 'live' ? 'rgba(248,81,73,0.5)' : 'rgba(56,139,253,0.4)') : '';
    b.style.color = active ? (e === 'live' ? 'var(--red)' : 'var(--blue)') : '';
  });
  const w = $('engine-risk-live-warn');
  if (w) w.style.display = engine === 'live' ? '' : 'none';
  // Update engine badges on each editable card / 更新每張可編輯卡片的引擎標記
  _updateEngineBadges(engine);
  _riskFormDirty = false;
  // loadRiskConfig() reads _selectedRiskEngine, so calling it is enough.
  // This also refreshes P0/P1/P2 display cards for the selected engine.
  // loadRiskConfig() 讀取 _selectedRiskEngine，呼叫它即可同時更新 P0/P1/P2 顯示與輸入框。
  loadRiskConfig();
}

// _updateEngineBadges — set color-coded engine indicator on all editable cards
// 在所有可編輯卡片上設置顏色區分的引擎標記
function _updateEngineBadges(engine) {
  const labels = { paper: 'Paper', demo: 'Demo', live: 'Live' };
  const colors = {
    paper: { bg: 'rgba(56,139,253,0.15)', border: 'rgba(56,139,253,0.5)', text: 'var(--blue)' },
    demo:  { bg: 'rgba(210,153,34,0.15)', border: 'rgba(210,153,34,0.5)', text: 'var(--yellow)' },
    live:  { bg: 'rgba(248,81,73,0.15)',  border: 'rgba(248,81,73,0.5)',  text: 'var(--red)' },
  };
  const c = colors[engine] || colors.paper;
  document.querySelectorAll('.rc-engine-badge').forEach(badge => {
    badge.textContent = labels[engine] || engine;
    badge.style.background = c.bg;
    badge.style.borderColor = c.border;
    badge.style.color = c.text;
    badge.style.fontWeight = '600';
  });
}

// Return save URL for current engine / 返回當前引擎的保存 URL
function _engineSaveUrl() {
  return _selectedRiskEngine === 'paper'
    ? '/api/v1/paper/risk/config/global'
    : '/api/v1/paper/risk/config/engine/' + _selectedRiskEngine + '/global';
}

// Wrap save with live confirmation dialog / 為 live 引擎包裝確認對話框
function _wrapLiveSave(cb, desc) {
  if (_selectedRiskEngine !== 'live') { cb(); return; }
  const d = $('dlg-engine-live-confirm-detail');
  if (d) d.textContent = '操作：' + desc + ' (engine=live)';
  _liveRiskSavePendingCallback = cb;
  const dlg = document.getElementById('dlg-engine-live-confirm');
  if (dlg) dlg.style.display = 'flex';
}
function confirmLiveEngineRiskSave() {
  document.getElementById('dlg-engine-live-confirm').style.display = 'none';
  if (_liveRiskSavePendingCallback) { _liveRiskSavePendingCallback(); _liveRiskSavePendingCallback = null; }
}

window.addEventListener('message', function(ev) {
  if (ev.origin !== window.location.origin) return;
  if (!ev.data) return;
  if (ev.data.type === 'openclaw-paper-engine-setting') {
    applyPaperRiskAvailability(!!ev.data.enabled);
    return;
  }
  if (ev.data.type !== 'openclaw-risk-select') return;
  if (ev.data.riskTab) switchRiskTab(ev.data.riskTab);
  if (ev.data.engine) selectRiskEngine(ev.data.engine);
  if (ev.data.scrollTo === 'top') {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (ev.data.scrollTo) {
    const target = document.getElementById(ev.data.scrollTo);
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
});

// ─── Dirty-tracking: skip input population during 15s refresh while user has unsaved edits ──
// 髒標記：用戶有未保存的編輯時，15s 刷新跳過輸入框填充
// WP-F/AH-06 fix: prevents loadAll from overwriting user edits in-flight.
let _riskFormDirty = false;
const _RISK_INPUT_IDS = [
  'in-hard-stop', 'in-take-profit', 'in-trailing', 'in-atr-mult', 'in-time-stop',
  'in-drawdown', 'in-leverage', 'in-daily-loss', 'in-p1-risk', 'in-single-pos',
  'in-total-exp', 'in-corr-exp', 'in-allowed-cats', 'in-same-dir',
  'in-cooldown-count', 'in-cooldown-min',
];
_RISK_INPUT_IDS.forEach(id => {
  const el = $(id);
  if (el) el.addEventListener('input', () => { _riskFormDirty = true; _updateDiffHighlights(); });
});
// in-tp-enabled uses 'change' (checkbox), not 'input' — must be tracked separately.
// in-tp-enabled 是 checkbox，用 change 事件，需單獨追蹤。
const _tpEl = $('in-tp-enabled');
if (_tpEl) _tpEl.addEventListener('change', () => { _riskFormDirty = true; _updateDiffHighlights(); });

// ─── §4.1 Diff mode: highlight right-panel display cells when inputs differ from loaded values ──
// §4.1 對比模式：當輸入值與已載入值不同時，高亮右側顯示格並標示原始值
const _DIFF_MAP = {
  'in-hard-stop':      's-hard',
  'in-take-profit':    's-tp',
  'in-trailing':       's-trailing',
  'in-time-stop':      's-time',
  'in-atr-mult':       's-atr',
  'in-drawdown':       's-drawdown',
  'in-leverage':       's-leverage',
  'in-daily-loss':     's-daily',
  'in-p1-risk':        's-p1-risk',
  'in-single-pos':     's-single-pos',
  'in-total-exp':      's-total-exp',
  'in-same-dir':       's-same-dir',
  'in-cooldown-count': 's-cool-count',
  'in-cooldown-min':   's-cool-min',
};

function _updateDiffHighlights() {
  Object.entries(_DIFF_MAP).forEach(([inId, dispId]) => {
    const inp = $(inId);
    const disp = $(dispId);
    if (!inp || !disp) return;
    const orig = inp.dataset.original;
    if (orig === undefined) return; // not yet loaded, skip
    const changed = String(inp.value).trim() !== String(orig).trim();
    disp.classList.toggle('oc-diff-changed', changed);
    // Insert / remove "was: X" diff label inside the metric cell parent
    // 在指標格父元素中插入/移除「was: X」差異標籤
    const parent = disp.closest('.oc-metric') || disp.parentElement;
    let lbl = parent ? parent.querySelector('.oc-diff-label') : null;
    if (changed) {
      if (!lbl) {
        lbl = document.createElement('div');
        lbl.className = 'oc-diff-label';
        if (parent) parent.appendChild(lbl);
      }
      lbl.textContent = '← was: ' + orig;
    } else if (lbl) {
      lbl.remove();
    }
  });
}

// Reset diff highlights after successful save — call after _riskFormDirty = false
// 保存成功後重置對比高亮 — 在 _riskFormDirty = false 之後呼叫
function _resetDiffHighlights() {
  Object.entries(_DIFF_MAP).forEach(([inId, dispId]) => {
    const inp = $(inId);
    const disp = $(dispId);
    if (inp) { inp.dataset.original = String(inp.value); }
    if (disp) { disp.classList.remove('oc-diff-changed'); }
    const parent = disp ? (disp.closest('.oc-metric') || disp.parentElement) : null;
    const lbl = parent ? parent.querySelector('.oc-diff-label') : null;
    if (lbl) lbl.remove();
  });
}

// _btnSaving — helper: disable btn and show loading text during async save
// _btnSaving — 輔助函數：保存期間禁用按鈕並顯示"儲存中..."
function _btnSaving(btn, saving) {
  if (!btn) return;
  if (saving) {
    // Capture original label before overwriting
    // 在覆蓋之前儲存原始文字
    btn.dataset.origText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '儲存中... / Saving...';
  } else {
    btn.disabled = false;
    btn.textContent = btn.dataset.origText || btn.textContent;
  }
}

// saveStopSettings — 止損管理器專用（Stop Manager 區块）
// Routes to the currently selected engine (paper/demo/live). Live engine triggers confirm dialog.
// 路由到當前選擇的引擎（paper/demo/live）。Live 引擎觸發確認對話框。
async function saveStopSettings(btn) {
  _wrapLiveSave(() => _doSaveStopSettings(btn), '止損設置 / Stop Settings');
}
async function _doSaveStopSettings(btn) {
  _btnSaving(btn, true);
  try {
    const tpEnabled = $('in-tp-enabled').checked;
    const trailingVal = parseFloat($('in-trailing').value);
    const atrVal = parseFloat($('in-atr-mult').value);
    const body = {
      max_stop_loss_pct: parseFloat($('in-hard-stop').value) || 5,
      tp_enabled: tpEnabled,
      max_take_profit_pct: tpEnabled ? (parseFloat($('in-take-profit').value) || 20) : 20,
      trailing_stop_pct: trailingVal > 0 ? trailingVal : null,
      atr_multiplier: atrVal > 0 ? atrVal : null,
      max_session_drawdown_pct: parseFloat($('in-drawdown').value) || 15,
      max_daily_loss_pct: parseFloat($('in-daily-loss').value) || 5,
      max_leverage: parseFloat($('in-leverage').value) || 20,
      max_holding_hours: parseFloat($('in-time-stop').value) || 72,
    };
    const d = await ocPost(_engineSaveUrl(), body);
    if (d) {
      const engLabel = _selectedRiskEngine.toUpperCase();
      ocToast('[' + engLabel + '] 止損設置已保存 / Stop settings saved', 'success');
      _riskFormDirty = false; _resetDiffHighlights(); loadAll();
    } else ocToast('Save failed / 保存失敗', 'error');
  } finally {
    _btnSaving(btn, false);
  }
}

// savePositionSettings — 倉位控制專用（Position Sizing & Exposure 區块）
// Routes to the currently selected engine. Live engine triggers confirm dialog.
// 路由到當前選擇的引擎。Live 引擎觸發確認對話框。
async function savePositionSettings(btn) {
  _wrapLiveSave(() => _doSavePositionSettings(btn), '倉位控制 / Position Settings');
}
async function _doSavePositionSettings(btn) {
  _btnSaving(btn, true);
  try {
    // p1_risk_pct now wired to Rust (RiskConfig.limits.per_trade_risk_pct) — sent
    // as percent, Rust stores as fraction. Hot-reloaded into IntentProcessor Gate 2.6.
    // p1_risk_pct 已接 Rust，發送百分比，Rust 存小數，熱重載到 Gate 2.6。
    const corrExpVal = parseFloat($('in-corr-exp').value);
    const catsRaw = ($('in-allowed-cats').value || '').trim();
    const body = {
      p1_risk_pct: parseFloat($('in-p1-risk').value) || 3,
      max_single_position_pct: parseFloat($('in-single-pos').value) || 20,
      max_total_exposure_pct: parseFloat($('in-total-exp').value) || 100,
      max_same_direction_positions: parseInt($('in-same-dir').value) || 3,
      // null = remove limit; only send if user entered a positive value
      // null = 不限制；只在用戶輸入正值時發送
      max_correlated_exposure_pct: (corrExpVal > 0) ? corrExpVal : null,
      // Parse comma-separated string to array; null if empty (keep current Rust value)
      // 逗號分隔字串轉陣列；空白則傳 null（保持 Rust 現值）
      allowed_categories: catsRaw ? catsRaw.split(',').map(s => s.trim()).filter(Boolean) : null,
      preferred_margin_mode: $('in-margin-mode').value || null,
      preferred_position_mode: $('in-position-mode').value || null,
    };
    const d = await ocPost(_engineSaveUrl(), body);
    if (d) {
      const engLabel = _selectedRiskEngine.toUpperCase();
      ocToast('[' + engLabel + '] 倉位設置已保存 / Position settings saved', 'success');
      _riskFormDirty = false; _resetDiffHighlights(); loadAll();
    } else ocToast('Save failed / 保存失敗', 'error');
  } finally {
    _btnSaving(btn, false);
  }
}

// saveCooldownSettings — 冷卻保護專用（Loss Cooldown 區块）
// Routes to the currently selected engine. Live engine triggers confirm dialog.
// 路由到當前選擇的引擎。Live 引擎觸發確認對話框。
async function saveCooldownSettings(btn) {
  _wrapLiveSave(() => _doSaveCooldownSettings(btn), '冷卻設置 / Cooldown Settings');
}
async function _doSaveCooldownSettings(btn) {
  _btnSaving(btn, true);
  try {
    const body = {
      consecutive_loss_cooldown_count: parseInt($('in-cooldown-count').value) || 3,
      consecutive_loss_cooldown_minutes: parseFloat($('in-cooldown-min').value) || 30,
    };
    const d = await ocPost(_engineSaveUrl(), body);
    if (d) {
      const engLabel = _selectedRiskEngine.toUpperCase();
      ocToast('[' + engLabel + '] 冷卻設置已保存 / Cooldown settings saved', 'success');
      _riskFormDirty = false; _resetDiffHighlights(); loadAll();
    } else ocToast('Save failed / 保存失敗', 'error');
  } finally {
    _btnSaving(btn, false);
  }
}

async function saveH0ShadowMode() {
  const enabled = $('in-h0-shadow').checked;
  const doSave = async () => {
    const d = await ocPost(_engineSaveUrl(), { h0_shadow_mode: enabled });
    const engLabel = _selectedRiskEngine.toUpperCase();
    if (d) { ocToast('[' + engLabel + '] ' + (enabled ? 'H0 Shadow Mode ON — 僅觀察不阻斷' : 'H0 Shadow Mode OFF — 正式門控'), 'success'); }
    else ocToast('Save failed', 'error');
  };
  _wrapLiveSave(doSave, 'H0 Shadow Mode');
}

// ─── AI Stop-Loss Consultation ────────────────────────────────
let _lastAIAdvice = null;

async function askAIStopLoss() {
  const model = $('ai-model').value;
  const focus = $('ai-focus').value;
  $('btn-ask-ai').disabled = true;
  $('btn-ask-ai').textContent = '⏳ Asking AI...';
  $('ai-advice-body').textContent = '正在查詢 AI，請稍候...\nQuerying AI, please wait...';

  // Gather context data
  const [riskD, sessD, stratD] = await Promise.allSettled([
    ocApi('/api/v1/paper/risk/status'),
    ocApi('/api/v1/paper/session/status'),
    ocApi('/api/v1/strategy/status'),
  ]);

  const riskStatus = riskD.status === 'fulfilled' && riskD.value ? riskD.value.data : {};
  const session = sessD.status === 'fulfilled' && sessD.value ? sessD.value.data : {};
  const orchestrator = stratD.status === 'fulfilled' && stratD.value ? stratD.value.data : {};

  const missingContext = [];
  if (!riskStatus || Object.keys(riskStatus).length === 0) missingContext.push('risk status endpoint unavailable');
  if (!session || Object.keys(session).length === 0) missingContext.push('paper session endpoint unavailable');
  if (!orchestrator || Object.keys(orchestrator).length === 0) missingContext.push('strategy status endpoint unavailable');
  if (missingContext.length === 3) {
    $('ai-advice-body').textContent =
      '無法取得後端風控上下文，已停止 AI 諮詢，避免使用偽造的 0 值。\n' +
      'Backend risk context is unavailable. AI consultation was not sent to avoid fabricated zero values.';
    $('btn-ask-ai').disabled = false;
    $('btn-ask-ai').textContent = '🤖 向 AI 詢問止損建議 / Ask AI';
    return;
  }

  const fmtMoneyOrUnknown = (v, decimals = 2) => {
    const n = Number(v);
    return Number.isFinite(n) ? '$' + n.toFixed(decimals) : 'unavailable';
  };
  const fmtNumOrUnknown = (v, decimals = 0) => {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(decimals) : 'unavailable';
  };
  const fmtPctOrUnknown = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return 'unavailable';
    return (Math.abs(n) <= 1 ? n * 100 : n).toFixed(2) + '%';
  };

  const pnl = session.pnl || {};
  const sess = session.session || {};
  const initialBalance = sess.initial_paper_balance_usdt ?? sess.initial_balance ?? null;
  const netPnl = pnl.net_paper_pnl ?? null;
  const displayBalance = Number.isFinite(Number(initialBalance)) && Number.isFinite(Number(netPnl))
    ? Number(initialBalance) + Number(netPnl)
    : null;

  const prompt = `You are an expert crypto trading risk manager. Analyze the current trading situation and recommend specific stop-loss settings.

Current Account Status:
- Balance: ${fmtMoneyOrUnknown(displayBalance)}
- Net PnL: ${fmtMoneyOrUnknown(netPnl, 4)}
- Open Positions: ${fmtNumOrUnknown(session.position_count)}
- Total Orders: ${fmtNumOrUnknown(session.order_count)}
- Drawdown: ${fmtPctOrUnknown(riskStatus.drawdown_pct ?? riskStatus.current_drawdown ?? riskStatus.drawdown)}
- Governor Tier: ${riskStatus.governor_tier || 'unavailable'}
- Session Halted: ${riskStatus.session_halted !== undefined ? String(riskStatus.session_halted) : 'unavailable'}
- Market Regime: ${orchestrator.market_regime || 'unavailable'}
- Data Quality: ${missingContext.length ? missingContext.join('; ') : 'all context endpoints returned data'}

Risk Style: ${focus === 'conservative' ? 'Conservative — prioritize capital preservation, minimize drawdown' : focus === 'aggressive' ? 'Aggressive — accept higher volatility for potential returns' : 'Balanced — balance risk and reward'}

Please recommend specific values for:
1. Hard Stop Loss % (per trade)
2. Trailing Stop % (from peak profit)
3. Time Stop (hours)
4. Max Session Drawdown %
5. Max Leverage
6. Max Daily Loss %

Explain your reasoning briefly. Answer in both Chinese and English.`;

  try {
    const d = await ocPost('/api/v1/paper/layer2/trigger', {
      reason: 'gui_risk_consultation',
      model: model,
      prompt: prompt,
    });

    if (d && d.data) {
      const result = d.data.result || d.data.recommendation || d.data.response || JSON.stringify(d.data, null, 2);
      _lastAIAdvice = d.data;
      $('ai-advice-body').textContent = result;
      $('btn-apply-ai').style.display = '';
    } else {
      $('ai-advice-body').textContent = 'AI 查詢失敗。請檢查 AI 引擎是否已配置。\nAI query failed. Check if AI engine is configured.';
    }
  } catch(e) {
    $('ai-advice-body').textContent = 'Error: ' + e.message;
  }

  $('btn-ask-ai').disabled = false;
  $('btn-ask-ai').textContent = '🤖 向 AI 詢問止損建議 / Ask AI';
}

// D-01 fix: Copy AI advice to clipboard for reference while adjusting values.
// D-01 修復：複製 AI 建議到剪貼板，方便調整數值時參考。
function applyAIAdvice() {
  const body = $('ai-advice-body');
  const text = body ? body.textContent : '';
  if (!text || !navigator.clipboard) {
    ocToast('No advice to copy / 無建議可複製', 'info');
    return;
  }
  navigator.clipboard.writeText(text).then(
    () => ocToast('AI advice copied to clipboard / 建議已複製到剪貼板', 'success'),
    () => ocToast('Copy failed — select text manually / 複製失敗，請手動選取', 'info')
  );
}

// ─── Actions ──────────────────────────────────────────────────
async function resetCooldown() {
  if (!await openConfirmModal("reset-cooldown")) return;
  const d = await ocPost('/api/v1/paper/risk/reset-cooldown');
  if (d) { ocToast('Cooldown reset OK', 'success'); loadAll(); }
  else ocToast('Reset failed', 'error');
}

async function unhaltSession() {
  if (!await openConfirmModal("unhalt-session")) return;
  const d = await ocPost('/api/v1/paper/risk/unhalt-session');
  if (d) { ocToast('Session unhalted', 'success'); loadAll(); }
  else ocToast('Unhalt failed', 'error');
}

// ─── Data Loading ─────────────────────────────────────────────
async function loadRiskStatus() {
  // Check Rust engine availability via /live endpoint — its engine_available field is
  // rust.is_available() (process-level), NOT pipeline-level. Paper endpoint uses
  // pipeline-level and reports false whenever paper is drained (PAPER-DISABLE-1 default).
  // Fall back to /paper only if /live errors out (first-boot edge case).
  // 透過 /live 端點檢查 Rust 引擎存活：其 engine_available = rust.is_available()（進程級），
  // 非管線級。Paper 端點是管線級，paper drained 時會報 false（PAPER-DISABLE-1 預設）。
  // /live 失敗才退回 /paper（啟動邊界情況）。
  try {
    const engineEl = $('r-engine-status');
    const modeEl = $('r-session-mode');
    let engineAvail = false;
    let sessState = 'unknown';
    let probeSource = 'live';
    try {
      const pd = await ocApi('/api/v1/live/session/status');
      if (pd && pd.data) {
        engineAvail = pd.data.engine_available === true;
        sessState = (pd.data.session && pd.data.session.session_state) || 'unknown';
      }
    } catch (_) {
      probeSource = 'paper';
      const pd2 = await ocApi('/api/v1/paper/session/status');
      if (pd2 && pd2.data) {
        engineAvail = pd2.data.engine_available === true;
        sessState = (pd2.data.session && pd2.data.session.session_state) || 'unknown';
      }
    }
    const stateLabels = { active: '運行中', observing: '觀察中', paused: '已暫停', offline: '離線', idle: '未啟動', stopped: '已停止' };
    engineEl.textContent = engineAvail ? '✓ 運行中' : '✗ 未連接';
    engineEl.className = 'oc-chip ' + (engineAvail ? 'oc-chip-good' : 'oc-chip-bad');
    modeEl.textContent = engineAvail
      ? '| ' + probeSource.toUpperCase() + ': ' + (stateLabels[sessState] || sessState)
      : '';
  } catch (e) { /* non-blocking */ }

  const d = await ocApi('/api/v1/paper/risk/status');
  // Show visible error in first risk metric cell if API is unreachable
  // 若 API 不可達，在第一個風控指標格顯示錯誤（非靜默返回）
  if (!d || !d.data) { ocSetText('r-pressure', '⚠'); ocSetText('r-drawdown', '⚠'); return; }
  const s = d.data;

  // Metrics
  const pressure = s.risk_pressure || s.pressure || s.drawdown_pct || 0;
  const elP = $('r-pressure');
  elP.textContent = (pressure * 100).toFixed(0) + '%';
  elP.className = 'oc-metric-val ' + (pressure > 0.7 ? 'red' : pressure > 0.4 ? 'yellow' : 'green');

  const drawdown = s.current_drawdown || s.drawdown || s.drawdown_pct || 0;
  const elD = $('r-drawdown');
  elD.textContent = (drawdown * 100).toFixed(1) + '%';
  elD.className = 'oc-metric-val ' + (drawdown > 0.1 ? 'red' : drawdown > 0.05 ? 'yellow' : 'green');

  ocSetText('r-peak', ocBalance(s.peak_balance || s.peak_balance_usdt || s.peak, 2));

  const halted = s.session_halted || s.halted || false;
  const elH = $('r-halted');
  elH.textContent = halted ? 'YES' : 'No';
  elH.className = 'oc-metric-val ' + (halted ? 'red' : 'green');

  // 1C-3-C: Rust-native shape — governor_tier replaces the deprecated cooldown_active flag.
  // 1C-3-C：Rust 原生 shape — 用 governor_tier 取代舊的 cooldown_active 旗標。
  const tier = s.governor_tier || 'NORMAL';
  const elC = $('r-cooldown');
  elC.textContent = tier;
  const tierBad = (tier === 'CIRCUIT_BREAKER' || tier === 'MANUAL_REVIEW' || tier === 'DEFENSIVE');
  const tierWarn = (tier === 'REDUCED' || tier === 'CAUTIOUS');
  elC.className = 'oc-metric-val ' + (tierBad ? 'red' : tierWarn ? 'yellow' : 'green');

  // consecutive_losses is now a per-symbol map. Display the worst-symbol count.
  // consecutive_losses 現為 per-symbol map，顯示最差 symbol 的次數。
  let maxLosses = 0;
  const lossMap = s.consecutive_losses_by_symbol || s.consecutive_losses;
  if (lossMap && typeof lossMap === 'object') {
    for (const k in lossMap) { if (lossMap[k] > maxLosses) maxLosses = lossMap[k]; }
  } else if (typeof lossMap === 'number') {
    maxLosses = lossMap;  // legacy fallback
  }
  ocSetText('r-losses', maxLosses);

  // Badge
  const badge = $('risk-badge');
  if (halted) { badge.textContent = 'HALTED'; badge.className = 'oc-chip oc-chip-bad'; }
  else if (pressure > 0.7) { badge.textContent = 'HIGH RISK'; badge.className = 'oc-chip oc-chip-bad'; }
  else if (pressure > 0.4) { badge.textContent = 'ELEVATED'; badge.className = 'oc-chip oc-chip-warn'; }
  else { badge.textContent = 'NORMAL'; badge.className = 'oc-chip oc-chip-good'; }
}

async function loadRiskConfig() {
  // Always fetch for the currently selected engine so P0/P1/P2 display cards and inputs
  // all reflect the chosen engine. The 15s loadAll() refresh also respects this.
  // 始終讀取當前選中引擎的配置，P0/P1/P2 顯示卡與輸入框統一更新。15s 刷新也遵守此邏輯。
  const _engine = _selectedRiskEngine || 'paper';
  const _url = _engine === 'paper' ? '/api/v1/paper/risk/config' : '/api/v1/paper/risk/config/engine/' + _engine;
  const badge = $('engine-risk-loaded-badge');
  if (badge) { badge.textContent = '加載中...'; badge.className = 'oc-chip oc-chip-neutral'; }
  const d = await ocApi(_url);
  if (!d || !d.data) {
    if (badge) { badge.textContent = '加載失敗'; badge.className = 'oc-chip oc-chip-warn'; }
    return;
  }
  // Route returns _risk_response({"config": {...}, "version": N}) so envelope is
  // d.data = {config: {global_config, limits, ...}, version: N}. Earlier code read
  // cfg.global_config directly which was always undefined → all reads fell through
  // to JS defaults → values appeared to "revert" after every save.
  // 路由實際回傳 {data: {config: {...}, version: N}}，必須再下一層讀 config。
  const cfg = (d.data && d.data.config) || d.data || {};
  const _ver = (d.data && d.data.version) || (cfg.meta && cfg.meta.version) || '?';
  if (badge) {
    badge.textContent = _engine.toUpperCase() + ' v' + _ver;
    badge.className = _engine === 'live' ? 'oc-chip oc-chip-bad' : 'oc-chip oc-chip-good';
  }

  // P0 - Category config: field is "category_overrides" or "category" or from allowed_categories
  // NOTE: don't read cfg.overrides here — Rust returns {linear: null, spot: null, ...}
  // and typeof null === 'object' would crash Object.entries(null) below.
  // 不要讀 cfg.overrides — Rust 回 null 值會讓下方 Object.entries(null) 拋錯。
  const p0 = cfg.category_overrides || cfg.category || cfg.p0 || {};
  const gc = cfg.global_config || cfg.global || cfg.p1 || {};
  let html0 = '<div class="oc-metrics" style="grid-template-columns:1fr">';
  if (typeof p0 === 'object' && Object.keys(p0).length) {
    Object.entries(p0).forEach(([cat, limits]) => {
      html0 += '<div class="oc-metric"><div class="oc-metric-label">' + ocEsc(cat) + '</div><div class="oc-metric-val" style="font-size:12px">';
      if (typeof limits === 'object') {
        Object.entries(limits).forEach(([k, v]) => { html0 += ocEsc(k.replace(/_/g,' ')) + ': ' + ocEsc(v) + '<br>'; });
      } else { html0 += ocEsc(limits); }
      html0 += '</div></div>';
    });
  } else {
    // Show allowed categories from global config
    const cats = gc.allowed_categories || [];
    html0 += '<div class="oc-metric"><div class="oc-metric-label">Allowed Categories</div><div class="oc-metric-val" style="font-size:13px">' + (cats.length ? cats.join(', ') : '--') + '</div></div>';
    html0 += '<div class="oc-metric"><div class="oc-metric-label">Max Single Position</div><div class="oc-metric-val" style="font-size:13px">' + (gc.max_single_position_pct || '--') + '%</div></div>';
  }
  html0 += '</div>';
  ocSetHtml('p0-config', html0);

  // P1 - Global config: field is "global_config"
  let html1 = '<div class="oc-metrics" style="grid-template-columns:1fr">';
  const p1Fields = [
    ['Max Leverage', gc.max_leverage],
    ['Max Session Drawdown', gc.max_session_drawdown_pct != null ? gc.max_session_drawdown_pct + '%' : null],
    ['Max Daily Loss', gc.max_daily_loss_pct != null ? gc.max_daily_loss_pct + '%' : null],
    ['Max Total Exposure', gc.max_total_exposure_pct != null ? gc.max_total_exposure_pct + '%' : null],
    ['Max Correlated Exp', gc.max_correlated_exposure_pct != null ? gc.max_correlated_exposure_pct + '%' : null],
    ['Loss Cooldown Count', gc.consecutive_loss_cooldown_count],
    ['Cooldown Minutes', gc.consecutive_loss_cooldown_minutes],
    ['Max Holding Hours', gc.max_holding_hours],
  ];
  p1Fields.forEach(([label, val]) => {
    html1 += '<div class="oc-metric"><div class="oc-metric-label">' + label + '</div><div class="oc-metric-val" style="font-size:14px">' + (val != null ? val : '--') + '</div></div>';
  });
  html1 += '</div>';
  ocSetHtml('p1-config', html1);

  // P2 - Agent adjustable: field is "agent_adjustable" or from global config
  const p2 = cfg.agent_adjustable || cfg.agent || cfg.p2 || {};
  let html2 = '<div class="oc-metrics" style="grid-template-columns:1fr">';
  const p2Fields = [
    ['Max Stop Loss', (p2.max_stop_loss_pct || gc.max_stop_loss_pct || '--') + '%'],
    ['Max Take Profit', (p2.max_take_profit_pct || gc.max_take_profit_pct || '--') + '%'],
    ['Max Single Position', (p2.max_single_position_pct || gc.max_single_position_pct || '--') + '%'],
    ['Position Size Factor', p2.position_size_factor || '--'],
    ['Trailing Stop', (p2.trailing_stop_pct || '--') + '%'],
  ];
  p2Fields.forEach(([label, val]) => {
    html2 += '<div class="oc-metric"><div class="oc-metric-label">' + label + '</div><div class="oc-metric-val" style="font-size:14px">' + (val != null ? val : '--') + '</div></div>';
  });
  html2 += '</div>';
  ocSetHtml('p2-config', html2);

  // ── Merge Rust engine active config as source of truth for engine-managed params ──
  // Rust 引擎活躍配置為引擎管理參數的真相源
  const ra = cfg.rust_active || {};
  const rStop = ra.stop_config || {};
  const rGuard = ra.guardian_config || {};
  const rRisk = ra.risk_manager_config || {};
  const ap = cfg.agent_params || {};

  // Stop Manager — populate display (prefer fresh ConfigStore `gc` → state-reader snapshot fallback)
  // ARCH-RC1 fake-success fix: `gc` is built from `client.refresh_config()` (fresh ConfigStore IPC).
  // `rStop/rGuard/rRisk` come from `reader.get_snapshot()` which is the tick-pushed state-reader
  // snapshot — lags one tick behind a config patch, so reading it first caused "Save success but
  // display shows old value" (user-visible fake success). Always prefer fresh config.
  // 顯示優先順序：fresh ConfigStore (gc) → state-reader snapshot (滯後一拍) → 預設值。
  const hardStop = gc.max_stop_loss_pct ?? rStop.hard_stop_pct ?? 5;
  ocSetText('s-hard', hardStop + '%');
  const tpOn = gc.tp_enabled === true || (gc.tp_enabled == null && rStop.take_profit_pct != null);
  const tpVal = gc.max_take_profit_pct ?? rStop.take_profit_pct ?? 20;
  ocSetText('s-tp', tpOn ? (tpVal + '%') : '關閉 / OFF');
  $('s-tp').style.color = tpOn ? 'var(--green)' : 'var(--text-dim)';
  const trailingVal = gc.trailing_stop_pct ?? rStop.trailing_stop_pct ?? ap.trailing_stop_distance_pct ?? null;
  ocSetText('s-trailing', trailingVal != null && trailingVal !== '' ? trailingVal + '%' : '關閉 / OFF');
  const atrMult = gc.atr_multiplier ?? rStop.atr_multiplier ?? null;
  ocSetText('s-atr', atrMult != null && atrMult !== '' ? atrMult + 'x' : '關閉 / OFF');
  const timeStop = gc.max_holding_hours ?? rStop.time_stop_hours ?? null;
  ocSetText('s-time', timeStop != null ? timeStop + 'h' : '關閉 / OFF');
  const maxDD = gc.max_session_drawdown_pct ?? rGuard.max_drawdown_pct ?? 15;
  ocSetText('s-drawdown', maxDD + '%');
  const maxLev = gc.max_leverage ?? rGuard.max_leverage ?? 20;
  ocSetText('s-leverage', maxLev + 'x');
  ocSetText('s-daily', gc.max_daily_loss_pct != null ? gc.max_daily_loss_pct + '%' : '--');

  // Position Sizing & Exposure display — fresh ConfigStore first, snapshot fallback
  // P1 risk: Rust stores as fraction (0.03), display as % (3%)
  // Prefer fresh ConfigStore (gc.p1_risk_pct, already in percent from route).
  // Fallback to snapshot rRisk.p1_risk_pct (fraction) only if gc missing.
  let p1RiskPct;
  if (gc.p1_risk_pct != null) {
    p1RiskPct = parseFloat(gc.p1_risk_pct);
  } else if (rRisk.p1_risk_pct != null) {
    p1RiskPct = rRisk.p1_risk_pct < 1 ? rRisk.p1_risk_pct * 100 : rRisk.p1_risk_pct;
  } else {
    p1RiskPct = 2;
  }
  ocSetText('s-p1-risk', p1RiskPct.toFixed(1) + '%');
  ocSetText('s-single-pos', (gc.max_single_position_pct ?? rRisk.max_single_position_pct ?? '--') + '%');
  ocSetText('s-total-exp', (gc.max_total_exposure_pct ?? rRisk.max_total_exposure_pct ?? '--') + '%');
  const corrExpDisplay = gc.max_correlated_exposure_pct;
  ocSetText('s-corr-exp', corrExpDisplay != null ? corrExpDisplay + '%' : '--');
  const allowedCatsDisplay = gc.allowed_categories;
  ocSetText('s-allowed-cats', Array.isArray(allowedCatsDisplay) && allowedCatsDisplay.length ? allowedCatsDisplay.join(', ') : '--');
  const sameDirVal = gc.max_same_direction_positions ?? rGuard.max_same_direction_positions ?? 3;
  ocSetText('s-same-dir', sameDirVal);
  ocSetText('s-margin-mode', gc.preferred_margin_mode ?? 'isolated');
  ocSetText('s-position-mode', gc.preferred_position_mode ?? 'one_way');

  // Cooldown display — fresh ConfigStore first, snapshot fallback
  const coolCount = gc.consecutive_loss_cooldown_count ?? rRisk.consecutive_loss_cooldown_count ?? 3;
  const coolMin = gc.consecutive_loss_cooldown_minutes ?? rRisk.consecutive_loss_cooldown_minutes ?? 30;
  ocSetText('s-cool-count', coolCount);
  ocSetText('s-cool-min', coolMin + ' min');

  // H0 Shadow Mode
  const h0Shadow = gc.h0_shadow_mode ?? true;
  $('in-h0-shadow').checked = h0Shadow;
  const h0El = $('h0-status');
  h0El.textContent = h0Shadow ? 'Shadow (觀察)' : 'Active (門控)';
  h0El.className = 'oc-chip ' + (h0Shadow ? 'oc-chip-warn' : 'oc-chip-good');

  // Populate input fields — `gc` is the fresh Rust ConfigStore snapshot (post 1C-3 single source
  // of truth). After save, risk_view_client._patch() awaits the IPC and refreshes cache, so the
  // next GET returns the patched value. Don't read rStop/rGuard for input defaults — those are
  // tick-pushed and lag one tick behind a config patch.
  // 輸入框用 fresh Rust ConfigStore (gc) 作真相源。post 1C-3 只有一個真相源，IPC patch
  // 後 cache 已刷新，下一次 GET 返回新值。rStop/rGuard 滯後一拍，不用作輸入預設。

  // WP-F/AH-06: skip input population when user has unsaved edits (dirty flag).
  // Display-only fields (ocSetText, ocSetHtml) always update — they don't conflict.
  // 當用戶有未保存的編輯時跳過輸入框填充。純顯示欄位始終更新。
  if (!_riskFormDirty) {
    function _setInput(id, val) {
      const el = $(id);
      if (el) {
        el.value = val;
        // §4.1 diff mode: store original value so input→display diff can be highlighted
        // §4.1 對比模式：儲存原始值供輸入→顯示欄位差異高亮使用
        el.dataset.original = String(val);
      }
    }
    _setInput('in-hard-stop', gc.max_stop_loss_pct ?? 5);
    // Checkboxes are not text-editable — safe to always update
    $('in-tp-enabled').checked = gc.tp_enabled === true;
    _setInput('in-take-profit', gc.max_take_profit_pct ?? 20);
    toggleTPInputs();
    _setInput('in-trailing', gc.trailing_stop_pct ?? '');
    _setInput('in-atr-mult', gc.atr_multiplier ?? '');
    _setInput('in-time-stop', gc.max_holding_hours ?? 72);
    _setInput('in-drawdown', gc.max_session_drawdown_pct ?? 15);
    _setInput('in-leverage', gc.max_leverage ?? 20);
    _setInput('in-daily-loss', gc.max_daily_loss_pct ?? 5);
    // p1_risk_pct now sourced from Rust ConfigStore (limits.per_trade_risk_pct).
    // Route exposes it as percent already, so no /100 vs *100 ambiguity here.
    // p1_risk_pct 從 Rust ConfigStore 取得，路由已換算為百分比。
    const gcP1Pct = gc.p1_risk_pct != null ? gc.p1_risk_pct : p1RiskPct;
    _setInput('in-p1-risk', parseFloat(gcP1Pct).toFixed(1));
    _setInput('in-single-pos', gc.max_single_position_pct ?? 20);
    _setInput('in-total-exp', gc.max_total_exposure_pct ?? 100);
    _setInput('in-corr-exp', gc.max_correlated_exposure_pct ?? '');
    _setInput('in-allowed-cats', (gc.allowed_categories || []).join(', '));
    _setInput('in-same-dir', gc.max_same_direction_positions ?? 3);
    _setInput('in-margin-mode', gc.preferred_margin_mode ?? 'isolated');
    _setInput('in-position-mode', gc.preferred_position_mode ?? 'one_way');
    _setInput('in-cooldown-count', gc.consecutive_loss_cooldown_count ?? 3);
    _setInput('in-cooldown-min', gc.consecutive_loss_cooldown_minutes ?? 30);
  }
}

async function loadAIContext() {
  const d = await ocApi('/api/v1/paper/risk/ai-context');
  if (!d || !d.data) { ocSetHtml('ai-risk-body', '<div class="oc-loading">No AI context available</div>'); return; }
  const ctx = d.data;
  let html = '<div class="oc-metrics">';
  const items = [
    ['Risk Suggestion', ctx.suggestion || ctx.recommendation],
    ['Pressure Level', ctx.pressure_level || ctx.risk_level],
    ['Market Regime', ctx.market_regime],
    ['Volatility', ctx.volatility],
  ];
  items.forEach(([label, val]) => {
    html += '<div class="oc-metric"><div class="oc-metric-label">' + label + '</div><div class="oc-metric-val" style="font-size:13px">' + ocEsc(val || '--') + '</div></div>';
  });
  html += '</div>';

  if (ctx.factors && ctx.factors.length) {
    html += '<h4 style="margin-top:12px;font-size:12px;color:var(--text-dim)">影響因素 / Factors:</h4><ul style="margin:6px 0 0 16px;font-size:12px;color:var(--text-dim)">';
    ctx.factors.forEach(f => { html += '<li>' + ocEsc(typeof f === 'string' ? f : f.description || f.name) + '</li>'; });
    html += '</ul>';
  }
  ocSetHtml('ai-risk-body', html);
}

async function loadDynamicRisk() {
  // DYNAMIC-RISK-1: per-engine sizer status. Rust returns `SizerStatus` fields:
  //   enabled, base_pct, current_pct, min_pct, max_pct, step_pct,
  //   sharpe_high, sharpe_low, trades_in_window, min_trades, last_sharpe,
  //   last_update_ms, last_direction, update_interval_ms
  // DYNAMIC-RISK-1：按引擎的調整器狀態；Rust 回 SizerStatus。
  const engine = _selectedRiskEngine || 'demo';
  const d = await ocApi('/api/v1/strategy/dynamic-risk/status?engine=' + encodeURIComponent(engine));
  if (!d || !d.data) {
    const s = document.getElementById('dr-status');
    if (s) { s.textContent = 'API 失敗 / Failed'; s.className = 'oc-chip oc-chip-bad'; }
    return;
  }
  const dr = d.data;
  const toggleEl = document.getElementById('dr-toggle');
  if (toggleEl) toggleEl.checked = !!dr.enabled;
  // Percent fields from Rust are fractional (0.03 = 3%) — convert for display.
  // Rust 端為小數（0.03=3%）— 顯示時乘 100。
  const currentPct = (dr.current_pct !== undefined) ? dr.current_pct : (dr.current_risk_pct || 0) / 100;
  const basePct    = (dr.base_pct    !== undefined) ? dr.base_pct    : (dr.base_risk_pct    || 0) / 100;
  ocSetText('dr-current-risk', (currentPct * 100).toFixed(2));
  ocSetText('dr-base-risk',    (basePct    * 100).toFixed(2));
  const statusEl = document.getElementById('dr-status');
  const tradesInWindow = dr.trades_in_window || 0;
  const minTrades      = dr.min_trades || 50;
  const available      = dr.available !== false; // undefined ⇒ true (happy path)
  if (!available) {
    statusEl.textContent = '引擎離線 / Engine offline';
    statusEl.className = 'oc-chip oc-chip-bad';
  } else if (!dr.enabled) {
    statusEl.textContent = '已禁用';
    statusEl.className = 'oc-chip oc-chip-neutral';
  } else if (tradesInWindow < minTrades) {
    statusEl.textContent = '等待數據(' + tradesInWindow + '/' + minTrades + '筆)';
    statusEl.className = 'oc-chip oc-chip-warn';
  } else {
    const sharpe = (dr.last_sharpe !== undefined && dr.last_sharpe !== null)
      ? 'Sharpe=' + dr.last_sharpe.toFixed(2)
      : '運行中';
    statusEl.textContent = sharpe + ' · ' + tradesInWindow + '筆';
    statusEl.className = 'oc-chip oc-chip-good';
  }
}

async function toggleDynamicRisk() {
  const engine = _selectedRiskEngine || 'demo';
  const enabled = document.getElementById('dr-toggle').checked;
  const d = await ocPost('/api/v1/strategy/dynamic-risk/toggle', { enabled: enabled, engine: engine });
  if (d) {
    if (enabled) {
      ocToast('動態風控已啟用 (' + engine + ') — 數據充足後自動生效', 'success');
    } else {
      ocToast('動態風控已禁用 (' + engine + ') — 已恢復基準值', 'success');
    }
    loadDynamicRisk();
  } else {
    // Revert toggle on failure
    document.getElementById('dr-toggle').checked = !enabled;
    ocToast('設置失敗', 'error');
  }
}

$('explain-position-sizing').innerHTML = ocExplain(
  '控制每筆交易的倉位大小和總體曝險。P1 Risk 決定每筆交易最大投入比例，過低會導致高價資產（如 BTC）無法下單。',
  'P1 Per-Trade Risk 是 Intent Processor 中的硬上限（p1_risk_pct），所有交易的倉位 = min(Kelly 計算量, 餘額 × P1% / 價格)。BTC @$67K 時，P1=2% 對 $1000 餘額只能下 0.0003 BTC（低於最小手數 0.001），需 7% 以上才能下單。Max Single Position 限制單倉占比。Total Exposure 限制所有倉位市值總和。Same-Direction 由 Guardian 檢查，防止全做多或全做空的方向集中風險。'
);

$('explain-cooldown').innerHTML = ocExplain(
  '連續虧損後自動進入冷卻期，暫時禁止開新倉。防止情緒化追單造成更大虧損。冷卻期到期自動恢復。',
  '當連續虧損次數達到 Trigger Count 時，系統進入冷卻狀態，持續 Duration 分鐘。冷卻期間：不允許開新倉，但已有倉位的止損/止盈照常執行。冷卻到期後自動恢復交易。也可在 Danger Zone 手動重置。建議保守設置：3 次 / 30 分鐘。'
);

$('explain-h0').innerHTML = ocExplain(
  'H0 是引擎的第一道交易準入檢查，在任何 AI 治理層之前運行。檢查數據新鮮度、系統健康、風險包絡等。',
  'H0 Gate 由 5 個子檢查組成：(1) Freshness — tick 數據是否過期，(2) Health — CPU/內存/DB 延遲，(3) Eligibility — 幣種/品類白名單，(4) Risk Envelope — 持倉數和曝險上限，(5) Cooldown — 冷卻期。Shadow Mode 下，所有檢查照常運行並記錄日志，但不會真正阻止交易。適合初期調優階段使用，確認規則合理後關閉 Shadow 進入正式門控。'
);

$('explain-auto-adjust').innerHTML = ocExplain(
  'Agent 根據交易表現自動調整參數。Sharpe 動態風控在累積足夠數據後自動啟用，表現好時增加風險，表現差時自動縮減。',
  'Sharpe 動態風控調整 risk_per_trade_pct（每筆風險比例），與 ATR 止損互補：Sharpe 管「投多少」，ATR 管「止損放多遠」。Sharpe>1 時逐步加倉（最高 5%），Sharpe<0 時逐步減倉（最低 1%），每次最多 ±0.5%，每 5 分鐘調一次。需要 50 筆以上交易數據才會啟用。'
);

async function loadAll() {
  await Promise.allSettled([loadRiskGovernor(), loadRiskStatus(), loadRiskConfig(), loadAIContext(), loadDynamicRisk()]);
}

selectRiskEngine(_selectedRiskEngine);
loadPaperRiskAvailability();
loadAll();
ocStartRefresh(loadAll, 15000);
ocInitFx();
window.addEventListener('occurrencychange', loadAll);

// ═══════════════════════════════════════════════════════════════════════════
// AI Budget — independent block (Phase 4 · 4-16 · WP-ARCH-RC1 reference)
// AI 預算 — 獨立區塊，不共享 form / 不共享 saveRiskConfig 路徑
// async fetch + await IPC, no local cache, no file write
// ═══════════════════════════════════════════════════════════════════════════
const _AI_BUDGET_SCOPES = [
  ['local_total',       'ai-budget-local-total'],
  ['platform_hard_cap', 'ai-budget-platform-cap'],
  ['agent_teacher',     'ai-budget-agent-teacher'],
  ['agent_analyst',     'ai-budget-agent-analyst'],
  ['agent_reserve',     'ai-budget-agent-reserve'],
];

async function loadAiBudget() {
  const statusEl = document.getElementById('ai-budget-status');
  const editEl   = document.getElementById('ai-budget-edit');
  if (!statusEl || !editEl) return;
  try {
    const r = await fetch('/api/v1/ai_budget/status', { credentials: 'include' });
    const data = await r.json();
    if (data && data.ok) {
      // Populate inputs from data.config (scope → monthly_usd)
      // 從 data.config 填入各 scope 輸入框
      const cfg = data.config || {};
      for (const [scope, elemId] of _AI_BUDGET_SCOPES) {
        const el = document.getElementById(elemId);
        if (el && Number.isFinite(cfg[scope])) el.value = cfg[scope];
      }
      // Progress bar — local_total usage % / 本地總額用量百分比
      const usage = (data.usage_mtd || {}).local_total || 0;
      const limit = (data.config || {}).local_total || 0;
      const pct = limit > 0 ? Math.min(100, (usage / limit) * 100) : 0;
      const fillEl = document.getElementById('ai-budget-bar-fill');
      const textEl = document.getElementById('ai-budget-bar-text');
      if (fillEl) fillEl.style.width = pct.toFixed(1) + '%';
      if (textEl) textEl.textContent =
        'MTD: $' + usage.toFixed(2) + ' / $' + limit.toFixed(2) + ' (' + pct.toFixed(1) + '%)';
      // Degrade light: green/yellow/red/grey
      // 降級紅黃綠燈
      const lightEl = document.getElementById('ai-budget-degrade-light');
      const labelEl = document.getElementById('ai-budget-degrade-label');
      const lvl = data.degrade_level || 'none';
      const colorMap = {
        none: '#2ea043', soft_warn: '#d29922', hard_limit: '#f85149', killswitch: '#8b1a1a',
      };
      if (lightEl) lightEl.style.background = colorMap[lvl] || '#888';
      if (labelEl) labelEl.textContent = 'degrade: ' + lvl;
      statusEl.textContent = 'OK · refreshed ' + new Date().toLocaleTimeString();
      statusEl.className = '';
      editEl.style.display = 'block';
    } else {
      statusEl.textContent = 'Engine error: ' + ((data && data.error) || 'unknown');
      statusEl.className = 'oc-chip oc-chip-warn';
    }
  } catch (e) {
    statusEl.textContent = 'Engine unreachable: ' + e.message;
    statusEl.className = 'oc-chip oc-chip-warn';
  }
}

async function saveAiBudget(btn) {
  // Disable button + show "Saving..." / 禁用按鈕並顯示儲存中
  const oldText = btn.textContent;
  btn.disabled = true;
  btn.textContent = '⏳ Saving...';
  try {
    // Save each scope sequentially via async IPC await
    // 逐一 await IPC 寫入每個 scope
    for (const [scope, elemId] of _AI_BUDGET_SCOPES) {
      const el = document.getElementById(elemId);
      if (!el) continue;
      const val = parseFloat(el.value);
      if (!Number.isFinite(val) || val < 0) continue;
      const r = await fetch('/api/v1/ai_budget/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ scope: scope, monthly_usd: val, updated_by: 'gui_operator' }),
      });
      if (!r.ok) {
        const errText = await r.text();
        throw new Error(scope + ': HTTP ' + r.status + ' ' + errText);
      }
    }
    btn.textContent = '✅ Saved';
    await loadAiBudget();
    setTimeout(() => { btn.textContent = oldText; btn.disabled = false; }, 1500);
  } catch (e) {
    btn.textContent = '❌ ' + (e.message || 'error');
    setTimeout(() => { btn.textContent = oldText; btn.disabled = false; }, 3000);
  }
}

// Initial load + 30s polling / 初次載入 + 30 秒輪詢
loadAiBudget();
setInterval(loadAiBudget, 30000);
