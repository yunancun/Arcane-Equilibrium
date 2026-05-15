/* ─────────────────────────────────────────────────────────────────────────
   Canary Tab — Graduated Canary Cohort Status renderer
   AMD-2026-05-09-03 W-AUDIT-9 T5 GUI surface 配套

   模組目的：
     渲染 OpenClaw Control Console Governance tab「Graduated Canary Cohort
     Status」section。包含：
       1. 5-stage 視覺合約（Stage 0..=4）+ scope 文案
       2. active cohort 列表 + 當前 stage / stage_entered_at_ms /
          observation_period_ms remaining / auto-promote 條件 / auto-rollback
          metric trip 狀態
       3. Manual Promote 按鈕（cohort 在 Stage 0/1/2 顯示；Stage 3+ 不顯示）
          - 走 openTypedConfirmModal typed-confirm（phrase = 'PROMOTE'，
            case-sensitive）
          - 確認後 fetch POST /api/v1/governance/canary/manual_promote
          - 後端走 LeaseScope::CanaryStagePromotion lease（per AMD §4.5）

   後端契約（per governance_canary_routes.py）：
     GET  /api/v1/governance/canary/cohorts
       → { ok, data: { cohorts:[], metric_registry:[], stages:[], now_ms } }
     POST /api/v1/governance/canary/manual_promote
       → body { cohort_id, from_stage, to_stage, reason }
       → 200 / 400 / 401 / 403 / 409 / 423 / 500 / 503

   不變量（per AMD-2026-05-09-03 §7 + memory feedback_chinese_only_comments）：
     - stage 4 不可作 to_stage（後端 400；GUI 隱藏 promote 按鈕）
     - manual_promote 必為相鄰 stage（後端 400；GUI 只顯示 +1 按鈕）
     - SHADOW_BYPASS lease 拒（後端 409；GUI 顯 toast 警示）
     - 觀察期 / metric live 顯示用 read-only；任何寫操作必經 typed-confirm

   多 session race + 注釋規範（per memory）：
     - 注釋默認只寫中文（2026-05-05 governance change）
     - openTypedConfirmModal singleton 防雙開（W-AUDIT-7c round 2 fix [#7]）
     - caller try/catch 包 await（W-AUDIT-7c round 3 fix）
     ─────────────────────────────────────────────────────────────────────── */

(function() {
  'use strict';

  // ─── 模組常數 ────────────────────────────────────────────────────────
  const CANARY_PROMOTE_PHRASE = 'PROMOTE';
  const STAGE_LABELS = {
    0: 'Stage 0 / Shadow',
    1: 'Stage 1 / Paper',
    2: 'Stage 2 / Demo single',
    3: 'Stage 3 / Demo full',
    4: 'Stage 4 / LIVE_PENDING',
  };
  const STAGE_SCOPES = {
    0: '影子模式 — 不送 intent 到 Rust submit path',
    1: '1 strategy × 1 symbol × paper × 7d',
    2: '1 strategy × 1 symbol × demo × 14d',
    3: '5 active strategies × demo × 21d',
    4: 'LIVE_PENDING — operator 顯式拍板（不自動晉升）',
  };
  // stage 觀察期長度（per AMD §2.2 表格）；0 = 持續態無自動晉升
  const STAGE_OBSERVATION_MS = {
    0: 0,
    1: 7 * 24 * 60 * 60 * 1000,   // 7d
    2: 14 * 24 * 60 * 60 * 1000,  // 14d
    3: 21 * 24 * 60 * 60 * 1000,  // 21d
    4: 0,
  };

  // ─── DOM helpers（XSS-safe） ──────────────────────────────────────────
  function _el(tagOrId) {
    if (typeof tagOrId === 'string' && tagOrId.indexOf('<') === -1) {
      return document.getElementById(tagOrId);
    }
    return null;
  }

  /**
   * 計算觀察期剩餘 / 已用時間的 human-readable 字串。
   * 回傳 { used_human, remaining_human, ratio } 三欄。
   */
  function _formatObservationProgress(currentStage, stageEnteredAtMs, nowMs) {
    const total = STAGE_OBSERVATION_MS[currentStage] || 0;
    if (total === 0) {
      return { used_human: '—', remaining_human: '持續態（無觀察期）', ratio: 0 };
    }
    const used = Math.max(0, nowMs - stageEnteredAtMs);
    const remaining = Math.max(0, total - used);
    const ratio = Math.min(1, used / total);

    function _humanMs(ms) {
      if (ms <= 0) return '0m';
      const days = Math.floor(ms / 86400000);
      const hours = Math.floor((ms % 86400000) / 3600000);
      const mins = Math.floor((ms % 3600000) / 60000);
      if (days > 0) return days + 'd ' + hours + 'h';
      if (hours > 0) return hours + 'h ' + mins + 'm';
      return mins + 'm';
    }

    return {
      used_human: _humanMs(used),
      remaining_human: _humanMs(remaining),
      ratio: ratio,
    };
  }

  /**
   * 渲染 5-stage 視覺合約（讀 stages array，畫成 5 個 chip + scope 文案）。
   */
  function _renderStageLadder(containerId, stages) {
    const el = _el(containerId);
    if (!el) return;
    if (!Array.isArray(stages) || stages.length === 0) {
      // fallback：用本地 STAGE_LABELS 渲染（後端不可用時不破畫面）
      stages = [0, 1, 2, 3, 4].map(function(s) {
        return { stage: s, label: STAGE_LABELS[s], scope: STAGE_SCOPES[s] };
      });
    }
    let html = '<div class="canary-stage-ladder" role="list" aria-label="Graduated canary 5 stages / 5 階段">';
    stages.forEach(function(s) {
      const stage = (typeof s.stage === 'number') ? s.stage : 0;
      const label = String(s.label || STAGE_LABELS[stage] || ('Stage ' + stage));
      const scope = String(s.scope || STAGE_SCOPES[stage] || '');
      // Stage 0 = neutral / 1-3 = info / 4 = warn（Stage 4 必人工拍板）
      const klass = stage === 0 ? 'canary-stage-chip stage-0'
                  : stage === 4 ? 'canary-stage-chip stage-4'
                  : 'canary-stage-chip stage-active';
      html += '<div class="' + ocSanitizeClass(klass) + '" role="listitem">'
            + '<div class="canary-stage-chip-label">' + ocEsc(label) + '</div>'
            + '<div class="canary-stage-chip-scope">' + ocEsc(scope) + '</div>'
            + '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  }

  /**
   * 渲染 active cohort 列表。
   * 每 cohort 顯示：cohort_id / current_stage / 觀察期進度 / promote 按鈕 /
   * last_transition_kind / last_decision_lease_id（縮）。
   */
  function _renderCohortList(containerId, cohorts, nowMs) {
    const el = _el(containerId);
    if (!el) return;

    if (!Array.isArray(cohorts) || cohorts.length === 0) {
      el.innerHTML =
        '<div class="canary-empty">'
        + '<p style="color:var(--text-dim);font-size:12px">'
        + '尚無 active cohort 落地（governance.canary_stage_log 為空）。'
        + '當 W-AUDIT-9 T3 shadow_mode_provider stage-aware land + operator '
        + '在 Settings tab 拍板 Stage 1 cohort 後，本表開始顯示。'
        + '</p></div>';
      return;
    }

    let html = '<div class="canary-cohort-grid">';
    cohorts.forEach(function(c) {
      const cohortId = String(c.cohort_id || 'global');
      const currentStage = (typeof c.current_stage === 'number') ? c.current_stage : 0;
      const enteredAtMs = (typeof c.stage_entered_at_ms === 'number') ? c.stage_entered_at_ms : 0;
      const lastKind = String(c.last_transition_kind || 'unknown');
      const lastLease = c.last_decision_lease_id ? String(c.last_decision_lease_id) : '';
      const leaseShort = lastLease ? lastLease.slice(-8) : '';

      const progress = _formatObservationProgress(currentStage, enteredAtMs, nowMs);
      const stageLabel = STAGE_LABELS[currentStage] || ('Stage ' + currentStage);
      const scope = STAGE_SCOPES[currentStage] || '';

      // promote 按鈕只對 Stage 0/1/2 顯示（Stage 3 自動 / Stage 4 走 5-gate）
      const canPromote = currentStage >= 0 && currentStage <= 2;
      const nextStage = currentStage + 1;
      const promoteLabel = canPromote
        ? ('Stage ' + currentStage + ' → ' + nextStage + ' 手動晉升')
        : '';

      const stageBadgeClass = currentStage === 0 ? 'canary-stage-badge stage-0'
                            : currentStage === 4 ? 'canary-stage-badge stage-4'
                            : 'canary-stage-badge stage-active';

      html += '<div class="canary-cohort-card" role="region" aria-label="'
            + ocEsc('Cohort ' + cohortId) + '">'
            + '<div class="canary-cohort-header">'
            +   '<div class="canary-cohort-id" title="' + ocEsc(cohortId) + '">'
            +     ocEsc(cohortId)
            +   '</div>'
            +   '<span class="' + ocSanitizeClass(stageBadgeClass) + '">'
            +     ocEsc(stageLabel)
            +   '</span>'
            + '</div>'
            + '<div class="canary-cohort-scope">' + ocEsc(scope) + '</div>'
            + '<div class="canary-cohort-progress">'
            +   '<div class="canary-progress-bar-wrap" role="progressbar" aria-valuenow="'
            +     ocEsc(String(Math.round(progress.ratio * 100)))
            +     '" aria-valuemin="0" aria-valuemax="100" aria-label="觀察期進度">'
            +     '<div class="canary-progress-bar-fill" style="width:'
            +       ocEsc(String(Math.round(progress.ratio * 100))) + '%"></div>'
            +   '</div>'
            +   '<div class="canary-progress-meta">'
            +     '已用 <strong>' + ocEsc(progress.used_human) + '</strong>'
            +     ' · 剩餘 <strong>' + ocEsc(progress.remaining_human) + '</strong>'
            +   '</div>'
            + '</div>'
            + '<div class="canary-cohort-meta">'
            +   '<span class="canary-meta-key">最近 transition：</span>'
            +   '<span class="canary-meta-val">' + ocEsc(lastKind) + '</span>';
      if (leaseShort) {
        html +=  ' · <span class="canary-meta-key">lease：</span>'
              + '<span class="canary-meta-val" style="font-family:monospace">…'
              + ocEsc(leaseShort) + '</span>';
      }
      html += '</div>';

      if (canPromote) {
        // button data-* 屬性帶 cohort 上下文，handler 從 dataset 讀；
        // ocEsc + ocSanitizeClass 於 attribute / class 都過 XSS 防線
        html += '<div class="canary-cohort-actions">'
              + '<button class="oc-btn oc-btn-primary canary-promote-btn" '
              +   'data-cohort-id="' + ocEsc(cohortId) + '" '
              +   'data-from-stage="' + ocEsc(String(currentStage)) + '" '
              +   'data-to-stage="' + ocEsc(String(nextStage)) + '">'
              +   '⬆ ' + ocEsc(promoteLabel)
              + '</button>'
              + '</div>';
      } else {
        html += '<div class="canary-cohort-actions" style="color:var(--text-dim);font-size:11px">'
              + (currentStage >= 3
                  ? '此 stage 不走手動晉升（Stage 3 自動 / Stage 4 走 5-gate live boundary）'
                  : '無可晉升動作')
              + '</div>';
      }
      html += '</div>';
    });
    html += '</div>';
    el.innerHTML = html;

    // 綁 click handler（沿用 inline data-* + addEventListener 不用 onclick=
    // 字面注入 handler，避免 cohort_id 含特殊字元 break parsing）
    const buttons = el.querySelectorAll('.canary-promote-btn');
    buttons.forEach(function(btn) {
      btn.addEventListener('click', function(ev) {
        const target = ev.currentTarget;
        const cohortId = target.dataset.cohortId || '';
        const fromStage = parseInt(target.dataset.fromStage || '0', 10);
        const toStage = parseInt(target.dataset.toStage || '0', 10);
        _onPromoteClick(target, cohortId, fromStage, toStage);
      });
    });
  }

  /**
   * 渲染 metric registry 表格。
   * 顯示 stage / metric_name / direction / threshold / observation_window /
   * description。對應 AMD §4.2 governance.canary_stage_metric_registry。
   */
  function _renderMetricRegistry(containerId, metrics) {
    const el = _el(containerId);
    if (!el) return;
    if (!Array.isArray(metrics) || metrics.length === 0) {
      el.innerHTML =
        '<p style="color:var(--text-dim);font-size:12px">'
        + 'metric registry 為空（V080 種子 row 尚未 land 或 active=false）。'
        + 'healthcheck [58] 會 WARN drift 提醒 operator seed metric。'
        + '</p>';
      return;
    }
    let html = '<div class="oc-table-wrap"><table class="oc-table">'
             + '<thead><tr>'
             +   '<th>Stage</th>'
             +   '<th>Metric / 指標</th>'
             +   '<th>Direction / 方向</th>'
             +   '<th>Threshold / 閾值</th>'
             +   '<th>Window / 觀察視窗</th>'
             +   '<th>Description / 說明</th>'
             + '</tr></thead><tbody>';
    metrics.forEach(function(m) {
      const stage = (typeof m.stage === 'number') ? m.stage : 0;
      const name = String(m.metric_name || '');
      const dir = String(m.direction || '');
      const threshold = (m.threshold_value === null || m.threshold_value === undefined)
        ? '—'
        : String(m.threshold_value);
      const windowMs = (typeof m.observation_window_ms === 'number')
        ? m.observation_window_ms
        : 0;
      const windowHuman = _humanMsCompact(windowMs);
      const desc = String(m.description || '');
      const dirClass = (dir.indexOf('rollback') === 0) ? 'oc-chip oc-chip-bad'
                     : (dir.indexOf('promote') === 0) ? 'oc-chip oc-chip-good'
                     : 'oc-chip oc-chip-neutral';
      html += '<tr>'
            + '<td>' + ocEsc('Stage ' + stage) + '</td>'
            + '<td>' + ocEsc(name) + '</td>'
            + '<td><span class="' + ocSanitizeClass(dirClass) + '">'
            +   ocEsc(dir) + '</span></td>'
            + '<td style="font-family:monospace">' + ocEsc(threshold) + '</td>'
            + '<td>' + ocEsc(windowHuman) + '</td>'
            + '<td style="font-size:11px;color:var(--text-dim)">' + ocEsc(desc) + '</td>'
            + '</tr>';
    });
    html += '</tbody></table></div>';
    el.innerHTML = html;
  }

  function _humanMsCompact(ms) {
    if (!ms || ms <= 0) return '—';
    const days = Math.floor(ms / 86400000);
    const hours = Math.floor((ms % 86400000) / 3600000);
    if (days > 0) return days + 'd';
    if (hours > 0) return hours + 'h';
    const mins = Math.floor(ms / 60000);
    return mins + 'm';
  }

  /**
   * Manual promote 按鈕點擊 handler。
   * 走 openTypedConfirmModal typed-confirm（phrase=PROMOTE，case-sensitive）；
   * 確認後 POST /api/v1/governance/canary/manual_promote。
   *
   * caller try/catch 包 await openTypedConfirmModal 修補 W-AUDIT-7c round 3
   * E2 RETURN HIGH-1 unhandled rejection 路徑。
   */
  async function _onPromoteClick(btn, cohortId, fromStage, toStage) {
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    try {
      // 4 個 modal 必填 metadata（per common.js openTypedConfirmModal options）
      const actor = '當前 operator session';
      const impact = '寫入 governance.canary_stage_log 一筆 manual_promote row '
                   + '（cohort=' + cohortId + ' Stage ' + fromStage + ' → '
                   + toStage + '）；觸發 LeaseScope::CanaryStagePromotion '
                   + 'lease（TTL 60s）。';
      const rollback = 'append-only audit log；無 UPDATE / DELETE。如需退降 '
                     + 'stage 必走 auto_rollback / incident_rollback 路徑（不走本端點）。';

      let proceed = false;
      try {
        proceed = await openTypedConfirmModal({
          title: '確認手動晉升 cohort stage',
          body: 'Cohort：' + cohortId + '\n'
              + 'Stage：' + fromStage + ' → ' + toStage + '\n'
              + '請鍵入「PROMOTE」確認。此動作會 acquire CanaryStagePromotion '
              + 'lease 並寫 audit log，無法撤銷。',
          phrase: CANARY_PROMOTE_PHRASE,
          confirmLabel: '⬆ 晉升 / Promote',
          confirmClass: 'oc-btn-primary',
          hint: '請鍵入「' + CANARY_PROMOTE_PHRASE + '」以確認 / Type "'
              + CANARY_PROMOTE_PHRASE + '" to confirm',
          actor: actor,
          impact: impact,
          rollback: rollback,
        });
      } catch (err) {
        // singleton modal already open / unexpected error
        if (typeof ocToast === 'function') {
          ocToast('操作未完成：' + (err && err.message ? err.message : 'unknown'), 'warn');
        }
        return;
      }

      if (!proceed) {
        if (typeof ocToast === 'function') {
          ocToast('已取消 manual promote / Cancelled', 'neutral');
        }
        return;
      }

      // A3-MAJOR-2 fix (WP-01 Wave 1 follow-up)：unify modal pattern — 改呼共享 openPromptModal SDK
      // 取代自製 oc-promote-reason overlay（原為第 5 個 ad-hoc modal pattern）。
      // SDK 已支援 multiline / maxlength / placeholder / char-counter / module-level lock。
      let reason = await openPromptModal({
        title: '請輸入晉升理由 / Enter Promotion Reason',
        body: '1-500 字，例如「Stage 1 entry_fills=12 滿足晉升條件，operator 拍板」',
        label: '晉升理由 / Reason',
        placeholder: 'operator manual promote',
        multiline: true,
        maxlength: 500,
        required: false,
        confirmLabel: '確認 / Confirm'
      }).catch(function() { return null; });
      if (reason === null) {
        if (typeof ocToast === 'function') {
          ocToast('已取消 manual promote / Cancelled', 'neutral');
        }
        return;
      }
      reason = String(reason).trim();
      if (reason.length === 0) reason = 'operator manual promote';
      if (reason.length > 500) reason = reason.slice(0, 500);

      // 提交 POST
      const res = await ocApi('/api/v1/governance/canary/manual_promote', {
        method: 'POST',
        body: {
          cohort_id: cohortId,
          from_stage: fromStage,
          to_stage: toStage,
          reason: reason,
        },
      });

      // 後端契約：{ ok, message, data: { stage_log_id, cohort_id, from_stage,
      // to_stage, decision_lease_id, transition_kind } }
      if (res && res.ok && res.data && typeof res.data.stage_log_id === 'number') {
        if (typeof ocToast === 'function') {
          ocToast(
            '✓ Manual promote 完成：' + cohortId + ' Stage '
            + fromStage + '→' + toStage
            + '（log id ' + res.data.stage_log_id + '）',
            'success'
          );
        }
        // 重整 cohort 列表
        loadCanaryCohorts();
      } else {
        const msg = (res && res.message) ? String(res.message) : 'manual_promote 失敗（後端回非預期 envelope）';
        if (typeof ocToast === 'function') {
          ocToast('✗ ' + msg, 'error');
        }
      }
    } finally {
      btn.disabled = false;
    }
  }

  /**
   * 從後端 fetch 並渲染整個 canary section。
   * - 失敗時不破畫面（顯示 fallback empty state）
   * - GUI 主 polling 不接此函式（per AMD §4.3 read-only；30s 輪詢由 caller
   *   或 ocLoadGovernance 觸發；本函式可獨立呼叫 reload）
   */
  async function loadCanaryCohorts() {
    const data = await ocApi('/api/v1/governance/canary/cohorts');
    if (!data || !data.ok || !data.data) {
      _renderStageLadder('canary-stage-ladder', null);
      _renderCohortList('canary-cohort-list', [], Date.now());
      _renderMetricRegistry('canary-metric-registry', []);
      return;
    }
    const payload = data.data;
    const nowMs = (typeof payload.now_ms === 'number') ? payload.now_ms : Date.now();
    _renderStageLadder('canary-stage-ladder', payload.stages || []);
    _renderCohortList('canary-cohort-list', payload.cohorts || [], nowMs);
    _renderMetricRegistry('canary-metric-registry', payload.metric_registry || []);
  }

  // ─── Public API ───────────────────────────────────────────────────────
  // Expose loadCanaryCohorts as global so governance-tab.js / 主 polling
  // 可呼叫 reload；其餘函式 module-private。
  window.loadCanaryCohorts = loadCanaryCohorts;
  window.OpenClawCanary = {
    loadCohorts: loadCanaryCohorts,
    // For tests / debug：暴露 helper
    _formatObservationProgress: _formatObservationProgress,
    _humanMsCompact: _humanMsCompact,
  };

  // ─── 自動載入 ─────────────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      // 確認 canary section 存在（governance tab include 本檔但 settings tab
      // 不會 — 容錯處理）
      if (_el('canary-stage-ladder')) {
        loadCanaryCohorts();
      }
    });
  } else {
    if (_el('canary-stage-ladder')) {
      loadCanaryCohorts();
    }
  }
})();
