/**
 * OpenClaw Review Queue & Event Binding
 * OpenClaw 審查隊列和事件綁定
 *
 * MODULE_NOTE (EN): Extracted from app.js (FIX-08 file size).
 * MODULE_NOTE (中): 從 app.js 提取（FIX-08 文件大小）。
 */

"use strict";

// ═══════════════════════════════════════════════════════════════════════════════
// L 章自動學習：審核佇列渲染 + 動作處理 / Auto Learning: Review Queue Render + Actions
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 審核包状态標簽 / Review packet status badge.
 */
function reviewStatusBadge(status) {
  const map = {
    pending_review: '<span class="badge badge-warning">待審核 / Pending</span>',
    approved: '<span class="badge badge-success">已批准 / Approved</span>',
    rejected: '<span class="badge badge-danger">已拒絕 / Rejected</span>',
    deferred: '<span class="badge badge-muted">已搁置 / Deferred</span>',
    ai_consulted: '<span class="badge badge-info">已諮詢AI / AI Consulted</span>'
  };
  return map[status] || `<span class="badge">${ocEsc(status)}</span>`;
}

/**
 * 審核包類型標簽 / Review packet type label.
 */
function reviewTypeLabel(packetType) {
  const map = {
    auto_observation: "自動觀察 / Auto Observation",
    auto_lesson: "自動經驗 / Auto Lesson",
    auto_hypothesis: "自動假設 / Auto Hypothesis"
  };
  return map[packetType] || ocEsc(packetType);
}

/**
 * 渲染單個審核包卡片 / Render a single review packet card.
 */
function renderReviewPacketCard(p) {
  const isPending = p.status === "pending_review" || p.status === "ai_consulted";
  const opts = p.options || {};
  const aiSec = p.ai_consultation || {};

  let actionsHtml = "";
  if (isPending) {
    actionsHtml = `
      <div class="review-actions">
        <div class="review-action-group">
          <button class="review-decide-btn review-btn-approve" data-packet-id="${p.packet_id}" data-decision="approve">
            批准 / Approve
          </button>
          <div class="review-consequence">${escHtml((opts.approve || {}).consequence || "記錄为正式條目")}</div>
        </div>
        <div class="review-action-group">
          <button class="review-decide-btn review-btn-reject" data-packet-id="${p.packet_id}" data-decision="reject">
            拒絕 / Reject
          </button>
          <div class="review-consequence">${escHtml((opts.reject || {}).consequence || "丢弃，不記錄")}</div>
        </div>
        <div class="review-action-group">
          <button class="review-decide-btn review-btn-defer" data-packet-id="${p.packet_id}" data-decision="defer">
            搁置 / Defer
          </button>
          <div class="review-consequence">${escHtml((opts.defer || {}).consequence || "下次再看")}</div>
        </div>
        <div class="review-action-group">
          <button class="review-ai-consult-btn" data-packet-id="${p.packet_id}">
            詢問 AI / Ask AI (${aiSec.recommended_tier || "light"}, ~$${(aiSec.estimated_cost_usd || 0.02).toFixed(2)})
          </button>
          <div class="review-consequence">${escHtml(aiSec.pre_built_question ? "讓AI評估這個發現" : "暂無AI建議")}</div>
        </div>
      </div>`;
  }

  let aiResultHtml = "";
  if (p.ai_consultation_result) {
    const r = p.ai_consultation_result;
    aiResultHtml = `
      <div class="review-ai-result">
        <div class="review-ai-result-header">AI 諮詢結果 / AI Consultation Result</div>
        <div class="review-ai-question"><strong>问題 / Question:</strong> ${escHtml(r.question_sent || "")}</div>
        <div class="review-ai-response"><strong>回復 / Response:</strong> ${escHtml(r.ai_response || "")}</div>
        <div class="review-ai-cost">費用 / Cost: $${(r.cost_usd || 0).toFixed(4)}</div>
      </div>`;
  }

  return `
    <div class="review-packet-card ${isPending ? "review-pending" : "review-decided"}">
      <div class="review-packet-header">
        ${reviewStatusBadge(p.status)}
        ${confidenceBadge(p.confidence_level || "inference")}
        <span class="review-packet-type">${reviewTypeLabel(p.packet_type)}</span>
        <span class="learning-record-ts">${fmtTs(p.created_ts_ms)}</span>
      </div>
      <div class="review-packet-section">
        <div class="review-section-label">簡要說明 / What Happened</div>
        <div class="review-section-content">${escHtml(p.what_happened || "")}</div>
      </div>
      <div class="review-packet-section">
        <div class="review-section-label">为什么重要 / Why It Matters</div>
        <div class="review-section-content">${escHtml(p.why_it_matters || "")}</div>
      </div>
      ${actionsHtml}
      ${aiResultHtml}
      <div class="learning-record-id">${p.packet_id}</div>
    </div>`;
}

/**
 * 渲染審核佇列 / Render the review queue tab.
 */
function renderReviewQueue(queueData) {
  if (!queueData) return;

  const listEl = document.getElementById("reviewQueueList");
  if (listEl) {
    const pending = queueData.pending_packets || [];
    listEl.innerHTML = pending.length === 0
      ? '<div class="muted-row">暂無待審核项 / No pending review packets</div>'
      : pending.map(p => renderReviewPacketCard(p)).join("");
  }

  const decidedEl = document.getElementById("reviewRecentDecided");
  if (decidedEl) {
    const decided = queueData.recent_decided || [];
    if (decided.length > 0) {
      decidedEl.innerHTML = `
        <div class="review-decided-header">最近已處理 / Recently Decided (${decided.length})</div>
        ${decided.map(p => renderReviewPacketCard(p)).join("")}`;
    } else {
      decidedEl.innerHTML = "";
    }
  }

  // 更新待審核計數 / Update pending review count
  setText("lrnPendingCount", queueData.pending_count ?? 0);
}

/**
 * 触发自動掃描 / Trigger auto scan.
 */
async function triggerAutoScan(scanType) {
  const routeMap = {
    observations: "/api/v1/learning/auto/scan-observations",
    lessons: "/api/v1/learning/auto/scan-lessons",
    hypotheses: "/api/v1/learning/auto/scan-hypotheses"
  };
  const route = routeMap[scanType];
  if (!route) return;

  try {
    const result = await apiPost(route, baseEnvelope());
    const d = result.data || {};
    setActionSummary(
      `掃描${scanType} / Scan ${scanType}`, "success",
      result.state_revision || "-", "-",
      `生成 ${d.packets_generated || 0} 個審核包，跳過 ${d.skipped_duplicates || 0} 個重復。`,
      d
    );
    await loadDashboard();
  } catch (error) {
    setActionSummary(`掃描失败 / Scan Failed (${scanType})`, "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 對審核包做決定 / Apply a review decision.
 */
async function applyReviewDecision(packetId, decision) {
  try {
    const result = await apiPost(`/api/v1/learning/review/${encodeURIComponent(packetId)}/decide`, baseEnvelope({
      payload: { decision, reason: "" }
    }));
    const d = result.data || {};
    const labels = { approve: "批准", reject: "拒絕", defer: "搁置" };
    setActionSummary(
      `${labels[decision] || decision} / ${decision}`, "success",
      result.state_revision || "-", "-",
      `審核包 ${packetId} 已${labels[decision] || decision}。${d.record_created ? " 已建立記錄 " + (d.created_record_id || "") : ""}`,
      d
    );
    await loadDashboard();
  } catch (error) {
    setActionSummary("審核失败 / Review Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 請求 AI 諮詢 / Request AI consultation for a review packet.
 */
async function requestAIConsult(packetId) {
  try {
    const result = await apiPost(`/api/v1/learning/review/${encodeURIComponent(packetId)}/decide`, { ...baseEnvelope(), decision: 'ask_ai' });
    const d = result.data || {};
    setActionSummary(
      "AI 諮詢 / AI Consult", "success",
      result.state_revision || "-", "-",
      `已諮詢 AI (${d.ai_tier || "light"})，費用 $${(d.cost_usd || 0).toFixed(4)}`,
      d
    );
    await loadDashboard();
  } catch (error) {
    setActionSummary("AI 諮詢失败 / AI Consult Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ── 事件綁定 / Event binding ──────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  ensureGuiEnhancements();

  // APR01-MEDIUM-13: Token is now in HttpOnly cookie. Clean up legacy localStorage.
  // Auto-connect using cookie auth (no manual token input needed).
  // APR01-MEDIUM-13：Token 已移至 HttpOnly cookie。清理旧 localStorage。
  // 使用 cookie 認證自動连接（無需手動輸入 token）。
  localStorage.removeItem('oc_trading_token');
  // Auto-connect: cookie is sent automatically, just load dashboard.
  // 自動連接：cookie 自動發送，直接載入儀表板。
  setTimeout(async () => {
    try {
      await loadDashboard();
      setConnectionStatus("已连接 / Connected", "good");
    } catch (error) {
      setConnectionStatus("连接失败 / Failed", "bad");
    }
  }, 200);

  // 使用事件委托處理所有動態按钮 / Use event delegation for all dynamic buttons
  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (target) {
      event.preventDefault();
      runQuickAction(target.dataset.action);
      return;
    }

    // 產品族配置應用 / Product family config apply
    const pfApply = event.target.closest(".pf-apply-btn");
    if (pfApply) {
      event.preventDefault();
      applyProductFamilyConfig(pfApply.dataset.family);
      return;
    }

    // 產品族權限應用 / Product family permissions apply
    const pfPermApply = event.target.closest(".pf-perm-apply-btn");
    if (pfPermApply) {
      event.preventDefault();
      applyProductFamilyPermissions(pfPermApply.dataset.family);
      return;
    }

    // 費用录入 / Cost entry submit
    if (event.target.closest("#submitCostEntry")) {
      event.preventDefault();
      submitCostEntry();
      return;
    }

    // PnL 录入 / PnL entry submit
    if (event.target.closest("#submitPnlEntry")) {
      event.preventDefault();
      submitPnlEntry();
      return;
    }

    // 系統設置：風險策略 / Settings: risk policy
    if (event.target.closest("#applyRiskSwitch")) {
      event.preventDefault();
      applyRiskPolicySetting();
      return;
    }

    // 系統設置：Demo/Learning / Settings: demo/learning
    if (event.target.closest("#applyDemoLearningSettings")) {
      event.preventDefault();
      applyDemoLearningSettings();
      return;
    }

    // ── L 章事件 / L-chapter events ─────────────────────────────────────────

    // 觀察录入 / Observation submit
    if (event.target.closest("#submitObservation")) {
      event.preventDefault();
      submitObservation();
      return;
    }

    // 經驗录入 / Lesson submit
    if (event.target.closest("#submitLesson")) {
      event.preventDefault();
      submitLesson();
      return;
    }

    // 假設录入 / Hypothesis submit
    if (event.target.closest("#submitHypothesis")) {
      event.preventDefault();
      submitHypothesis();
      return;
    }

    // 實驗录入 / Experiment submit
    if (event.target.closest("#submitExperiment")) {
      event.preventDefault();
      submitExperiment();
      return;
    }

    // 假設審批按钮 / Hypothesis verdict buttons
    const hypVerdictBtn = event.target.closest(".hyp-verdict-btn");
    if (hypVerdictBtn) {
      event.preventDefault();
      applyHypothesisVerdict(hypVerdictBtn.dataset.hypId, hypVerdictBtn.dataset.verdict);
      return;
    }

    // 實驗審批按钮 / Experiment approval buttons
    const expApproveBtn = event.target.closest(".exp-approve-btn");
    if (expApproveBtn) {
      event.preventDefault();
      applyExperimentApproval(expApproveBtn.dataset.expId, expApproveBtn.dataset.action);
      return;
    }

    // 實驗完成按钮 / Experiment completion button
    const expCompleteBtn = event.target.closest(".exp-complete-btn");
    if (expCompleteBtn) {
      event.preventDefault();
      applyExperimentCompletion(expCompleteBtn.dataset.expId);
      return;
    }

    // 保存周期快照 / Save period snapshot
    if (event.target.closest("#savePeriodSnapshot")) {
      event.preventDefault();
      savePeriodSnapshot();
      return;
    }

    // 自動掃描按钮 / Auto scan buttons
    const scanBtn = event.target.closest(".auto-scan-btn");
    if (scanBtn) {
      event.preventDefault();
      triggerAutoScan(scanBtn.dataset.scan);
      return;
    }

    // 審核決策按钮 / Review decision buttons
    const reviewDecideBtn = event.target.closest(".review-decide-btn");
    if (reviewDecideBtn) {
      event.preventDefault();
      applyReviewDecision(reviewDecideBtn.dataset.packetId, reviewDecideBtn.dataset.decision);
      return;
    }

    // AI 諮詢按钮 / AI consultation button
    const aiConsultBtn = event.target.closest(".review-ai-consult-btn");
    if (aiConsultBtn) {
      event.preventDefault();
      requestAIConsult(aiConsultBtn.dataset.packetId);
      return;
    }

    // 學習標簽页切换 / Learning tab switching
    const tabBtn = event.target.closest(".learning-tab");
    if (tabBtn) {
      event.preventDefault();
      const tabName = tabBtn.dataset.tab;
      // 切换標簽页激活状态 / Toggle active tab
      document.querySelectorAll(".learning-tab").forEach(t => t.classList.remove("active"));
      tabBtn.classList.add("active");
      // 切换內容面板 / Toggle content panel
      document.querySelectorAll(".learning-tab-content").forEach(c => c.classList.remove("active"));
      const panelMap = {
        observations: "tabObservations",
        lessons: "tabLessons",
        hypotheses: "tabHypotheses",
        experiments: "tabExperiments",
        reviewQueue: "tabReviewQueue"
      };
      document.getElementById(panelMap[tabName])?.classList.add("active");
      return;
    }

    // ── Paper Trading 按钮處理 / Paper Trading button handlers ──
    const paperActionBtn = event.target.closest("[data-paper-action]");
    if (paperActionBtn) {
      event.preventDefault();
      handlePaperAction(paperActionBtn.dataset.paperAction);
      return;
    }

    if (event.target.id === "paperSubmitOrder") {
      event.preventDefault();
      submitPaperOrder();
      return;
    }

    // ── Market Feed 按钮處理 / Market Feed button handlers ──
    const feedActionBtn = event.target.closest("[data-feed-action]");
    if (feedActionBtn) {
      event.preventDefault();
      handleMarketFeedAction(feedActionBtn.dataset.feedAction);
      return;
    }
  });
});

