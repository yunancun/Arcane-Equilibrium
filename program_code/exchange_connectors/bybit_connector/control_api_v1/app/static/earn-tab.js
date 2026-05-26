/* ─────────────────────────────────────────────────────────────────────────
   Earn Tab — Layer 1 Bybit Earn-only mainnet first stake (Sprint 1B Wave C)

   MODULE_NOTE
   模塊用途：tab-earn.html 對應 sibling JS。負責 6 端點 GET + 1 POST
             (POST /api/v1/earn/stake)、5-gate UI 對映後端 9-gate、Stage 0R
             3-state 渲染、typed-confirm phrase 強制帶 amount、防誤觸 cooldown、
             15s 輪詢 + iframe 切走自動 clearInterval。
   主要 fn：startEarnTab / _onSubmitClick / _renderPreflight / _renderProducts
             / _renderPositions / _renderRecords / _validateForm / _formatStage0r
   依賴：common-formatters.js (ocEsc / ocChip / ocNum / ocMoney / ocTime)
         common-modals.js (openTypedConfirmModal 必填 phrase + actor + impact + rollback)
         common.js (ocApi / ocPost / ocToast / ocExplain)
   後端契約 (per spec §4.2)：
     GET  /api/v1/earn/balance     → { usdt_balance, claimable_yield, last_recon_ts, recon_status, bybit_env, engine_mode }
     GET  /api/v1/earn/products    → { products:[FlexibleProduct], filtered_for }
     GET  /api/v1/earn/preflight   → { gate_a, gate_b, gate_c, gate_d, gate_e, all_pass, stage_0r:{status, json_path, last_run_ts, eligible_for_first_stake, fail_reasons} }
     GET  /api/v1/earn/positions   → { positions:[FlexiblePosition] }
     GET  /api/v1/earn/records     → { records:[EarnMovementRow], total }
     POST /api/v1/earn/stake       → { intent_id, lease_id, movement_id, submitted, rejected_reason, bybit_response }
   硬邊界 (per spec §6.6 + ux-checklist anti-pattern 8 條)：
     - typed-confirm phrase 帶 amount 動態構造（OQ-3 default）；case-sensitive
     - 後端再驗一次 phrase；前端 typed-confirm 不可作為唯一防線
     - 5-gate 任一 FAIL 或 Stage 0R != PASS → submit button disabled + 紅色 reason
     - Submit cooldown：失敗後 60s 才允許 retry
     - iframe 切走 / pagehide 必 clearInterval（per memory feedback agent-tracker）
     ─────────────────────────────────────────────────────────────────────── */

(function() {
  'use strict';

  // ─── 模組常數 / Module constants ────────────────────────────────────
  // typed-confirm phrase 模板帶 amount 動態構造（per spec OQ-3 default）
  // 為什麼鎖整數：後端 Pydantic `amount_usd: int` 浮點 input 會被 422 reject；
  //              GUI 端 _buildTypedConfirmPhrase 必先 Math.floor 強制整數，
  //              避免 phrase 與後端再驗一次 phrase 不匹配。
  function _buildTypedConfirmPhrase(amountUsd) {
    var n = Number(amountUsd);
    if (!isFinite(n)) return null;
    var amountInt = Math.floor(n);
    return 'CONFIRM EARN STAKE $' + amountInt + ' USDT';
  }

  // 失敗 retry cooldown 60s（per spec §6.4）
  // Failure retry cooldown: 60s after Bybit reject
  var _SUBMIT_FAIL_COOLDOWN_MS = 60 * 1000;

  // 15s auto-refresh（per spec §5.4）；對齊 sidebar / canary tab pattern
  // 15s auto-refresh interval (per spec §5.4)
  var _POLL_INTERVAL_MS = 15 * 1000;

  // ─── 模組狀態 / Module state ────────────────────────────────────────
  var _state = {
    // 最近一次 preflight all_pass + stage_0r status
    preflight_all_pass: false,
    stage_0r_status: 'PENDING',
    // 第一個 Available USDT FlexibleSaving 產品（auto-pick）
    selected_product: null,
    // submit cooldown 結束時間（ms epoch）
    submit_cooldown_until: 0,
    // submit 中防 double-click
    submit_in_flight: false,
    // 15s 輪詢 timer id；切走 tab 必清除
    poll_timer: null,
    // 上次成功 preflight ts 顯示用
    last_refresh_ts: 0,
  };

  // ─── DOM helper / XSS-safe ─────────────────────────────────────────
  function _el(id) { return document.getElementById(id); }

  function _show(id) { var e = _el(id); if (e) e.style.display = ''; }
  function _hide(id) { var e = _el(id); if (e) e.style.display = 'none'; }

  // ─── §3.1 Header / 標頭 ────────────────────────────────────────────
  function _renderHeader(bybitEnv, engineMode) {
    var envEl = _el('earn-env-badge');
    var emEl = _el('earn-engine-mode');
    var tsEl = _el('earn-last-refresh-ts');
    if (envEl) {
      var envLabel = bybitEnv || '--';
      var envType = 'neutral';
      if (envLabel === 'live') envType = 'bad';
      else if (envLabel === 'live_demo') envType = 'warn';
      else if (envLabel === 'demo') envType = 'info';
      envEl.innerHTML = ocChip(envLabel, envType);
    }
    if (emEl) {
      emEl.textContent = 'engine_mode：' + (engineMode || '--');
    }
    if (tsEl) {
      var now = new Date();
      // UTC + local 雙標（per gui-style-guide 原則 1）
      var utc = now.toISOString().slice(0, 19).replace('T', ' ') + 'Z';
      var local = now.toLocaleString('zh-CN', { hour12: false });
      tsEl.textContent = '採集時間：' + utc + ' / ' + local;
    }
    _state.last_refresh_ts = Date.now();
  }

  // ─── §3.2 Balance / 餘額 ───────────────────────────────────────────
  async function _loadBalance() {
    _show('earn-balance-loading');
    _hide('earn-balance-error');
    _hide('earn-balance-data');
    var resp = await ocApi('/api/v1/earn/balance');
    _hide('earn-balance-loading');
    if (!resp) {
      _show('earn-balance-error');
      return;
    }
    // 寬容處理 envelope：{data:{...}} 或直接平面 {...}
    var d = resp.data || resp;
    var usdt = (d && d.usdt_balance != null) ? d.usdt_balance : null;
    var claimable = (d && d.claimable_yield != null) ? d.claimable_yield : null;
    var reconTs = (d && d.last_recon_ts != null) ? d.last_recon_ts : null;
    var reconStatus = (d && d.recon_status) ? d.recon_status : 'pending_first_stake';

    _el('earn-balance-usdt').textContent = (usdt == null) ? '0.0000' : ocNum(usdt, 4);
    _el('earn-balance-claimable').textContent = (claimable == null) ? '0.0000' : ocNum(claimable, 4);
    _el('earn-balance-recon-ts').textContent = reconTs ? ocTime(reconTs) : '尚未對賬';

    var statusType = 'neutral';
    if (reconStatus === 'ok') statusType = 'good';
    else if (reconStatus === 'mismatch') statusType = 'warn';
    else if (reconStatus === 'mismatch_critical') statusType = 'bad';
    _el('earn-balance-recon-status').innerHTML = ocChip(ocEsc(reconStatus), statusType);

    // 同時更新 header env + engine_mode（若 balance endpoint 返回）
    if (d && (d.bybit_env || d.engine_mode)) {
      _renderHeader(d.bybit_env, d.engine_mode);
    }

    _show('earn-balance-data');
  }

  // ─── §3.3 5-Gate Preflight / 5-gate 預檢 ────────────────────────────
  // 5 light box 對應後端 9-gate (E-0..E-9) 5 governance gate 群組：
  // (a) Operator role → E-3 governance
  // (b) authorization.json → E-3/E-4 governance + lease
  // (c) OPENCLAW_ALLOW_MAINNET → E-0 capability
  // (d) Bybit secret slot → E-0/E-8 capability + bybit ack
  // (e) IntentProcessor wired → E-0/E-1 capability + payload
  // 9 個技術 gate 對 GUI 顯示無意義；5 governance 群組才是 operator-facing
  var _GATE_DEFS = [
    { key: 'gate_a', icon: '&#x1F464;', labelZh: 'Operator 角色', labelEn: 'Operator role',           tooltipDefault: 'PrimaryOperator / BackupOperator 角色驗證' },
    { key: 'gate_b', icon: '&#x1F510;', labelZh: 'authorization', labelEn: 'authorization.json',     tooltipDefault: 'HMAC valid + not expired + earn-write scope' },
    { key: 'gate_c', icon: '&#x1F30D;', labelZh: 'MAINNET 開關',  labelEn: 'ALLOW_MAINNET',          tooltipDefault: 'OPENCLAW_ALLOW_MAINNET=1（live）/ N/A（demo）' },
    { key: 'gate_d', icon: '&#x1F511;', labelZh: 'Bybit secret', labelEn: 'Bybit secret slot',      tooltipDefault: 'slot 含 earn scope + < 6 mo lifetime' },
    { key: 'gate_e', icon: '&#x2699;',  labelZh: 'Engine wired',  labelEn: 'IntentProcessor wired',  tooltipDefault: 'bybit_earn_client + earn_movement_writer injected' },
  ];

  function _gateBoxClass(status) {
    // status 字串：'PASS' / 'FAIL' / 'WARN' / 'N/A'（per spec §5.1）
    if (status === 'PASS') return 'gate-pass';
    if (status === 'FAIL') return 'gate-fail';
    if (status === 'WARN') return 'gate-warn';
    return 'gate-na';
  }

  function _gateIcon(status) {
    if (status === 'PASS') return '&#x2705;';   // ✅
    if (status === 'FAIL') return '&#x274C;';   // ❌
    if (status === 'WARN') return '&#x26A0;';   // ⚠
    return '&#x2796;';                          // ➖ N/A
  }

  function _renderGateGrid(preflight) {
    var grid = _el('earn-gate-grid');
    if (!grid) return;
    var html = '';
    var passCount = 0;
    for (var i = 0; i < _GATE_DEFS.length; i++) {
      var def = _GATE_DEFS[i];
      var gateData = preflight && preflight[def.key];
      var status;
      var tooltip;
      if (typeof gateData === 'string') {
        status = gateData;
        tooltip = def.tooltipDefault;
      } else if (gateData && typeof gateData === 'object') {
        status = String(gateData.status || 'FAIL').toUpperCase();
        tooltip = gateData.detail || def.tooltipDefault;
      } else {
        status = 'FAIL';
        tooltip = '後端未回報 / not reported';
      }
      if (status === 'PASS' || status === 'N/A') passCount++;
      var cls = _gateBoxClass(status);
      html += '<div class="earn-gate-box ' + ocSanitizeClass(cls) + '" title="' + ocEsc(tooltip) + '">' +
                '<span class="earn-gate-icon">' + _gateIcon(status) + '</span>' +
                '<div class="earn-gate-label">(' + String.fromCharCode(97 + i) + ') ' +
                  ocEsc(def.labelZh) + ' / ' + ocEsc(def.labelEn) + '</div>' +
                '<div class="earn-gate-detail">' + ocEsc(tooltip) + '</div>' +
              '</div>';
    }
    grid.innerHTML = html;

    // 整體 verdict line
    var allPass = !!(preflight && preflight.all_pass);
    var verdictEl = _el('earn-gate-verdict');
    if (verdictEl) {
      if (allPass) {
        verdictEl.className = 'earn-gate-verdict verdict-pass';
        verdictEl.textContent = '✅ 5/5 PASS — Stake submit unlocked';
      } else {
        verdictEl.className = 'earn-gate-verdict verdict-fail';
        verdictEl.textContent = '❌ ' + passCount + '/5 PASS — Submit disabled（修復 FAIL gate 後重試）';
      }
    }
    _state.preflight_all_pass = allPass;
  }

  function _renderStage0r(stage0r) {
    var row = _el('earn-stage0r-row');
    var badge = _el('earn-stage0r-badge');
    var detail = _el('earn-stage0r-detail');
    var copy = _el('earn-stage0r-copy');
    if (!row || !badge || !detail) return;

    var status = (stage0r && stage0r.status) ? String(stage0r.status).toUpperCase() : 'PENDING';
    _state.stage_0r_status = status;

    var cliCmd = 'python helper_scripts/canary/replay_earn_preflight.py --coin USDT --amount-usd 100 --days 7';

    if (status === 'PASS') {
      row.className = 'earn-stage0r-row stage0r-pass';
      badge.className = 'earn-stage0r-badge stage0r-pass';
      badge.textContent = 'Stage 0R: ✅ PASS';
      var ts = stage0r.last_run_ts ? ocTime(stage0r.last_run_ts) : '--';
      var path = stage0r.json_path || '--';
      detail.textContent = '最近執行：' + ts + '  ·  JSON：' + path;
      if (copy) copy.textContent = '';
    } else if (status === 'FAIL') {
      row.className = 'earn-stage0r-row stage0r-fail';
      badge.className = 'earn-stage0r-badge stage0r-fail';
      badge.textContent = 'Stage 0R: ❌ FAIL';
      var reasons = (stage0r.fail_reasons && stage0r.fail_reasons.length)
        ? stage0r.fail_reasons.join(' / ')
        : '未知原因 / no reason reported';
      detail.textContent = '失敗原因：' + reasons + ' — 請重跑 preflight harness';
      if (copy) copy.textContent = cliCmd;
    } else {
      row.className = 'earn-stage0r-row stage0r-pending';
      badge.className = 'earn-stage0r-badge stage0r-pending';
      badge.textContent = 'Stage 0R: ⏳ PENDING';
      detail.textContent = '尚未跑過或 JSON age > 24h — 請開 SSH 執行：';
      if (copy) copy.textContent = cliCmd;
    }
  }

  async function _loadPreflight() {
    _show('earn-preflight-loading');
    _hide('earn-preflight-error');
    _hide('earn-preflight-data');
    var resp = await ocApi('/api/v1/earn/preflight');
    _hide('earn-preflight-loading');
    if (!resp) {
      _show('earn-preflight-error');
      _state.preflight_all_pass = false;
      _state.stage_0r_status = 'PENDING';
      _refreshSubmitButton();
      return;
    }
    var d = resp.data || resp;
    _renderGateGrid(d);
    _renderStage0r(d.stage_0r || {});
    _show('earn-preflight-data');
    _refreshSubmitButton();
  }

  // ─── §3.4 Products / 可用產品列表 ──────────────────────────────────
  async function _loadProducts() {
    _show('earn-products-loading');
    _hide('earn-products-empty');
    _hide('earn-products-error');
    _hide('earn-products-data');

    var resp = await ocApi('/api/v1/earn/products');
    _hide('earn-products-loading');
    if (!resp) {
      _show('earn-products-error');
      return;
    }
    var d = resp.data || resp;
    var products = (d && d.products) ? d.products : [];

    // filter: coin=USDT AND category=FlexibleSaving AND status=Available
    var filtered = [];
    for (var i = 0; i < products.length; i++) {
      var p = products[i];
      if (!p) continue;
      if (String(p.coin || '').toUpperCase() !== 'USDT') continue;
      if (String(p.category || '') !== 'FlexibleSaving') continue;
      if (String(p.status || '') !== 'Available') continue;
      filtered.push(p);
    }
    // sort: estimateApr DESC
    filtered.sort(function(a, b) {
      return (Number(b.estimateApr) || 0) - (Number(a.estimateApr) || 0);
    });

    if (filtered.length === 0) {
      _show('earn-products-empty');
      _state.selected_product = null;
      _updateFormProductFields();
      _refreshSubmitButton();
      return;
    }

    // 渲染 table
    var html = '';
    for (var j = 0; j < filtered.length; j++) {
      var item = filtered[j];
      var aprPct = (Number(item.estimateApr) || 0).toFixed(2);
      var aprChip = j === 0 ? ocChip('Sprint 1B 鎖定', 'info') : '';
      html += '<tr>' +
        '<td><code style="font-size:11px">' + ocEsc(item.productId || '--') + '</code> ' + aprChip + '</td>' +
        '<td>' + ocEsc(item.coin || '--') + '</td>' +
        '<td>' + ocEsc(aprPct) + ' %</td>' +
        '<td>' + ocNum(item.minStake || 0, 2) + '</td>' +
        '<td>' + ocNum(item.maxStake || 0, 2) + '</td>' +
        '<td>' + ocChip(ocEsc(item.status || '--'), 'good') + '</td>' +
        '</tr>';
    }
    _el('earn-products-tbody').innerHTML = html;
    _show('earn-products-data');

    // 自動 pick 第一個 (highest APR USDT FlexibleSaving Available)
    _state.selected_product = filtered[0];
    _updateFormProductFields();
    _refreshSubmitButton();
  }

  function _updateFormProductFields() {
    var pidEl = _el('earn-product-id');
    var aprEl = _el('earn-apr');
    if (_state.selected_product) {
      pidEl.value = _state.selected_product.productId || '--';
      var apr = (Number(_state.selected_product.estimateApr) || 0).toFixed(2);
      aprEl.value = apr + ' %';
    } else {
      pidEl.value = '--';
      aprEl.value = '--';
    }
  }

  // ─── §3.5 Form validation + Submit / 表單驗證 + 提交 ────────────────
  function _getAmount() {
    var v = _el('earn-amount').value;
    var n = parseFloat(v);
    return isFinite(n) ? n : NaN;
  }

  function _validateForm() {
    var reasons = [];

    if (!_state.preflight_all_pass) {
      reasons.push('5-gate 尚未全部 PASS / not all gates PASS');
    }
    if (_state.stage_0r_status !== 'PASS') {
      reasons.push('Stage 0R preflight 尚未 PASS（請開 SSH 跑 harness）/ Stage 0R not PASS');
    }
    if (!_state.selected_product) {
      reasons.push('沒有可用的 USDT FlexibleSaving 產品 / no available product');
    }

    var amount = _getAmount();
    var amountEl = _el('earn-amount');
    var amountHintEl = _el('earn-amount-hint');
    // 為什麼整數檢查：後端 Pydantic amount_usd:int 浮點 422 reject；GUI 端先擋住更友好。
    if (!isFinite(amount)) {
      reasons.push('金額為空或非數字 / amount empty or invalid');
      if (amountEl) amountEl.className = 'earn-form-input';
      if (amountHintEl) {
        amountHintEl.textContent = '請輸入 $100 - $200 USDT 整數';
        amountHintEl.className = 'earn-form-hint';
      }
    } else if (amount < 100 || amount > 200) {
      reasons.push('金額需在 $100 - $200 區間 / amount must be $100-$200');
      if (amountEl) amountEl.className = 'earn-form-input input-error';
      if (amountHintEl) {
        amountHintEl.textContent = '✗ 金額超出 $100-$200 區間 / out of range';
        amountHintEl.className = 'earn-form-hint hint-error';
      }
    } else if (Math.floor(amount) !== amount) {
      reasons.push('金額需為整數 / amount must be integer');
      if (amountEl) amountEl.className = 'earn-form-input input-error';
      if (amountHintEl) {
        amountHintEl.textContent = '✗ 金額需為整數 / integer only';
        amountHintEl.className = 'earn-form-hint hint-error';
      }
    } else {
      if (amountEl) amountEl.className = 'earn-form-input input-ok';
      if (amountHintEl) {
        amountHintEl.textContent = '✓ 金額有效 / valid amount';
        amountHintEl.className = 'earn-form-hint hint-ok';
      }
    }

    var rationale = (_el('earn-rationale').value || '').trim();
    var rationaleHintEl = _el('earn-rationale-hint');
    if (rationale.length < 10) {
      reasons.push('理由至少 10 字 / rationale needs at least 10 chars');
      if (rationaleHintEl) {
        rationaleHintEl.textContent = rationale.length + ' / 200 字（最少 10 字）';
        rationaleHintEl.className = 'earn-form-hint hint-error';
      }
    } else if (rationale.length > 200) {
      reasons.push('理由超過 200 字 / rationale exceeds 200 chars');
      if (rationaleHintEl) {
        rationaleHintEl.textContent = rationale.length + ' / 200 字（已超出）';
        rationaleHintEl.className = 'earn-form-hint hint-error';
      }
    } else {
      if (rationaleHintEl) {
        rationaleHintEl.textContent = rationale.length + ' / 200 字';
        rationaleHintEl.className = 'earn-form-hint hint-ok';
      }
    }

    // cooldown 未過
    var now = Date.now();
    if (now < _state.submit_cooldown_until) {
      var remainSec = Math.ceil((_state.submit_cooldown_until - now) / 1000);
      reasons.push('Submit cooldown 中，' + remainSec + ' 秒後重試 / cooldown ' + remainSec + 's');
    }

    return reasons;
  }

  function _refreshSubmitButton() {
    var reasons = _validateForm();
    var btn = _el('earn-submit-btn');
    var reasonEl = _el('earn-submit-reason');
    var phrasePreviewEl = _el('earn-typed-phrase-preview');
    var amount = _getAmount();

    // 即時更新 typed-confirm phrase preview（amount 必為 100..200 整數）
    if (phrasePreviewEl) {
      if (isFinite(amount) && amount >= 100 && amount <= 200 && Math.floor(amount) === amount) {
        var phrase = _buildTypedConfirmPhrase(amount);
        phrasePreviewEl.textContent = phrase || 'CONFIRM EARN STAKE $<amount> USDT';
      } else {
        phrasePreviewEl.textContent = 'CONFIRM EARN STAKE $<amount> USDT';
      }
    }

    if (!btn) return;
    if (reasons.length === 0 && !_state.submit_in_flight) {
      btn.disabled = false;
      if (reasonEl) reasonEl.textContent = '';
    } else {
      btn.disabled = true;
      if (reasonEl) reasonEl.textContent = reasons.join('  ·  ');
    }
  }

  /**
   * 提交 first stake handler。
   *
   * 為什麼：(1) 前端 typed-confirm 是 reinforces 不是唯一防線（後端再驗一次）
   *        (2) cooldown + in_flight guard 防 double-click
   *        (3) 失敗後 60s cooldown 才允許 retry（per spec §6.4）
   *        (4) sync wait Bybit ack（OQ-6 default）；loading state 顯示
   */
  async function _onSubmitClick() {
    var btn = _el('earn-submit-btn');
    if (!btn || btn.disabled) return;
    var reasons = _validateForm();
    if (reasons.length > 0) {
      ocToast('Submit 阻擋：' + reasons[0], 'warn');
      return;
    }
    if (_state.submit_in_flight) return;

    var amount = _getAmount();
    var productId = _state.selected_product ? _state.selected_product.productId : null;
    var aprBps = _state.selected_product
      ? Math.round((Number(_state.selected_product.estimateApr) || 0) * 100)
      : 0;
    var rationale = (_el('earn-rationale').value || '').trim();
    var phrase = _buildTypedConfirmPhrase(amount);

    if (!productId || !phrase) {
      ocToast('表單資料不完整，請重新檢查 / form incomplete', 'warn');
      return;
    }

    // ─── Typed-confirm modal ────────────────────────────────────────
    // phrase 帶 amount 動態構造（OQ-3 default 反 muscle memory）；
    // case-sensitive 比對在 modal helper 內部進行（per common-modals.js）
    var proceed = false;
    try {
      proceed = await openTypedConfirmModal({
        title: '確認 Earn First Stake / Confirm Earn First Stake',
        body: '此操作將寫入真實 Bybit Earn balance，動主帳 USDT。\n'
            + '失敗範圍：Bybit retCode != 0 → fail-closed reject + audit log；\n'
            + '成功則 7d Stage 1 Demo micro-canary 觀察期啟動。',
        phrase: phrase,
        confirmLabel: '提交 Stake / Submit Stake',
        confirmClass: 'oc-btn-danger',
        actor: '當前 operator session',
        impact: String(Math.floor(amount)) + ' USDT FlexibleSaving stake @ ~'
              + ((Number(_state.selected_product.estimateApr) || 0).toFixed(2)) + '% APR '
              + '（預期年化 ~$'
              + (Math.floor(amount) * (Number(_state.selected_product.estimateApr) || 0) / 100).toFixed(2)
              + '）',
        rollback: 'Redeem 走 /api/v1/earn/redeem（Sprint 5+；Sprint 1B first stake 後 7d 觀察期內不 redeem）',
      });
    } catch (err) {
      ocToast('Modal 開啟失敗：' + (err && err.message ? err.message : 'unknown'), 'warn');
      return;
    }
    if (!proceed) {
      ocToast('已取消 Earn stake / Cancelled', 'neutral');
      return;
    }

    // ─── Submit POST + 同步 wait Bybit ack ─────────────────────────
    _state.submit_in_flight = true;
    _refreshSubmitButton();
    _show('earn-submit-loading');
    btn.disabled = true;

    try {
      // 為什麼 amount_usd 是 int：後端 Pydantic field `amount_usd: int` 浮點 422 reject；
      // 為什麼 type_confirm_phrase（非 typed_confirm_phrase）：對齊後端 field 命名。
      var resp = await ocApi('/api/v1/earn/stake', {
        method: 'POST',
        body: {
          coin: 'USDT',
          product_id: productId,
          amount_usd: Math.floor(amount),
          expected_apr_bps: aprBps,
          rationale: rationale,
          type_confirm_phrase: phrase,
        },
      });

      _hide('earn-submit-loading');
      _state.submit_in_flight = false;

      if (!resp) {
        _state.submit_cooldown_until = Date.now() + _SUBMIT_FAIL_COOLDOWN_MS;
        ocToast('Submit 失敗 — 後端拒絕或網路異常；60s cooldown 後可重試', 'error');
        _refreshSubmitButton();
        return;
      }

      var data = resp.data || resp;
      var submitted = !!(data && data.submitted);
      if (submitted) {
        ocToast('✓ Earn stake 已提交（intent_id=' + (data.intent_id || '?')
              + '；movement_id=' + (data.movement_id || '?') + '）', 'success');
        // 清空表單 + 立即刷新 records + positions + balance
        _el('earn-amount').value = '';
        _el('earn-rationale').value = '';
        _loadBalance();
        _loadPositions();
        _loadRecords();
        _refreshSubmitButton();
      } else {
        var reason = (data && data.rejected_reason) ? data.rejected_reason : 'unknown';
        _state.submit_cooldown_until = Date.now() + _SUBMIT_FAIL_COOLDOWN_MS;
        ocToast('Earn stake 拒絕：' + reason + '（60s cooldown）', 'error');
        _loadRecords(); // 拒絕 audit log 可能已寫入
        _refreshSubmitButton();
      }
    } catch (e) {
      _hide('earn-submit-loading');
      _state.submit_in_flight = false;
      _state.submit_cooldown_until = Date.now() + _SUBMIT_FAIL_COOLDOWN_MS;
      ocToast('Submit 例外：' + (e && e.message ? e.message : 'unknown'), 'error');
      _refreshSubmitButton();
    }
  }

  // ─── §3.6 Positions / 持倉 ──────────────────────────────────────────
  async function _loadPositions() {
    _show('earn-positions-loading');
    _hide('earn-positions-empty');
    _hide('earn-positions-error');
    _hide('earn-positions-data');

    var resp = await ocApi('/api/v1/earn/positions');
    _hide('earn-positions-loading');
    if (!resp) {
      _show('earn-positions-error');
      return;
    }
    var d = resp.data || resp;
    var positions = (d && d.positions) ? d.positions : [];
    if (positions.length === 0) {
      _show('earn-positions-empty');
      return;
    }
    var html = '';
    for (var i = 0; i < positions.length; i++) {
      var p = positions[i];
      var statusType = (String(p.status || '') === 'Holding') ? 'good' : 'info';
      html += '<tr>' +
        '<td><code style="font-size:11px">' + ocEsc(p.productId || '--') + '</code></td>' +
        '<td>' + ocEsc(p.coin || '--') + '</td>' +
        '<td>' + ocNum(p.amount || 0, 4) + '</td>' +
        '<td>' + ocNum(p.totalPnl || 0, 4) + '</td>' +
        '<td>' + ocNum(p.claimableYield || 0, 4) + '</td>' +
        '<td>' + ocChip(ocEsc(p.status || '--'), statusType) + '</td>' +
        '<td><code style="font-size:10px">' + ocEsc(p.orderId || '--') + '</code></td>' +
        '</tr>';
    }
    _el('earn-positions-tbody').innerHTML = html;
    _show('earn-positions-data');
  }

  // ─── §3.7 Records history / 歷史記錄 ────────────────────────────────
  async function _loadRecords() {
    _show('earn-records-loading');
    _hide('earn-records-empty');
    _hide('earn-records-error');
    _hide('earn-records-data');

    var direction = _el('earn-records-direction').value || 'all';
    var outcome = _el('earn-records-outcome').value || 'all';
    var qs = 'limit=50';
    if (direction !== 'all') qs += '&direction=' + encodeURIComponent(direction);
    if (outcome !== 'all') qs += '&outcome=' + encodeURIComponent(outcome);

    var resp = await ocApi('/api/v1/earn/records?' + qs);
    _hide('earn-records-loading');
    if (!resp) {
      _show('earn-records-error');
      return;
    }
    var d = resp.data || resp;
    var records = (d && d.records) ? d.records : [];
    if (records.length === 0) {
      _show('earn-records-empty');
      return;
    }
    var html = '';
    for (var i = 0; i < records.length; i++) {
      var r = records[i];
      // 為什麼 enum 對齊 V100：reconciliation_status CHECK enum 是
      // pending / matched / mismatch 三值；其他字串視為未知 (neutral)。
      var outcomeStr = String(r.outcome || r.reconciliation_status || '--');
      var outcomeType = 'neutral';
      if (outcomeStr === 'matched') outcomeType = 'good';
      else if (outcomeStr === 'mismatch') outcomeType = 'bad';
      else if (outcomeStr === 'pending') outcomeType = 'warn';

      var dirType = (String(r.direction || '') === 'stake') ? 'info' : 'warn';

      html += '<tr>' +
        '<td>' + ocEsc(ocTime(r.event_ts_utc)) + '</td>' +
        '<td>' + ocChip(ocEsc(r.direction || '--'), dirType) + '</td>' +
        '<td>' + ocNum(r.amount || r.amount_usdt || 0, 2) + '</td>' +
        '<td>' + ocNum((Number(r.apr) || 0), 2) + ' %</td>' +
        '<td>' + ocChip(ocEsc(outcomeStr), outcomeType) + '</td>' +
        '<td><code style="font-size:10px">' + ocEsc(r.lease_id || '--') + '</code></td>' +
        '<td><code style="font-size:10px">' + ocEsc(r.movement_id || '--') + '</code></td>' +
        '</tr>';
    }
    _el('earn-records-tbody').innerHTML = html;
    _show('earn-records-data');
  }

  // ─── Master refresh / 一次拉全部 6 端點 ──────────────────────────────
  async function _refreshAll() {
    _renderHeader(null, null);
    // 5 個 GET 並行（不依賴順序）
    await Promise.all([
      _loadBalance(),
      _loadPreflight(),
      _loadProducts(),
      _loadPositions(),
      _loadRecords(),
    ]);
    _refreshSubmitButton();
  }

  // ─── Polling / 輪詢 + iframe 切走 cleanup ────────────────────────────
  function _startPolling() {
    if (_state.poll_timer !== null) return;
    _state.poll_timer = setInterval(function() {
      _refreshAll();
    }, _POLL_INTERVAL_MS);
  }

  function _stopPolling() {
    if (_state.poll_timer !== null) {
      clearInterval(_state.poll_timer);
      _state.poll_timer = null;
    }
  }

  // pagehide + visibilitychange 雙監聽：iframe 切走 / hidden 必清 timer
  // （per memory feedback agent-tracker iframe setInterval 教訓）
  function _bindLifecycle() {
    window.addEventListener('pagehide', _stopPolling);
    document.addEventListener('visibilitychange', function() {
      if (document.hidden) {
        _stopPolling();
      } else {
        _refreshAll();
        _startPolling();
      }
    });
  }

  // ─── 啟動入口 / Entry ────────────────────────────────────────────────
  /**
   * Earn Tab 啟動入口。
   *
   * 為什麼：tab-earn.html boot script 呼叫 startEarnTab() 觸發 (1) 首次拉取
   *        6 endpoint (2) bind submit / refresh / form / records filter listener
   *        (3) 啟動 15s 輪詢 (4) iframe lifecycle cleanup hook。
   */
  function startEarnTab() {
    // bind 表單即時驗證
    var amountEl = _el('earn-amount');
    if (amountEl) amountEl.addEventListener('input', _refreshSubmitButton);
    var rationaleEl = _el('earn-rationale');
    if (rationaleEl) rationaleEl.addEventListener('input', _refreshSubmitButton);

    // bind submit
    var submitBtn = _el('earn-submit-btn');
    if (submitBtn) submitBtn.addEventListener('click', _onSubmitClick);

    // bind manual refresh
    var refreshBtn = _el('earn-refresh-btn');
    if (refreshBtn) refreshBtn.addEventListener('click', _refreshAll);

    // bind records filter
    var dirSel = _el('earn-records-direction');
    if (dirSel) dirSel.addEventListener('change', _loadRecords);
    var outSel = _el('earn-records-outcome');
    if (outSel) outSel.addEventListener('change', _loadRecords);

    // 首次拉取 + polling + lifecycle
    _refreshAll();
    _startPolling();
    _bindLifecycle();
  }

  // export to global for tab-earn.html boot script + future test fixture
  window.startEarnTab = startEarnTab;
  // 暴露 phrase builder 供 future test 驗證 OQ-3 phrase 格式
  window._earnTabBuildPhrase = _buildTypedConfirmPhrase;
})();
