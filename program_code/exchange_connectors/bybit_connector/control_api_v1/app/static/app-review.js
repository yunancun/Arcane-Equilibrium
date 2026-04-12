/**
 * OpenClaw Review Queue & Event Binding
 * OpenClaw 審查隊列和事件綁定
 *
 * MODULE_NOTE (EN): Extracted from app.js (FIX-08 file size).
 * MODULE_NOTE (中): 從 app.js 提取（FIX-08 文件大小）。
 */

"use strict";

// ═══════════════════════════════════════════════════════════════════════════════
// L 章自动学习：审核队列渲染 + 动作处理 / Auto Learning: Review Queue Render + Actions
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 审核包状态标签 / Review packet status badge.
 */
function reviewStatusBadge(status) {
  const map = {
    pending_review: '<span class="badge badge-warning">待审核 / Pending</span>',
    approved: '<span class="badge badge-success">已批准 / Approved</span>',
    rejected: '<span class="badge badge-danger">已拒绝 / Rejected</span>',
    deferred: '<span class="badge badge-muted">已搁置 / Deferred</span>',
    ai_consulted: '<span class="badge badge-info">已咨询AI / AI Consulted</span>'
  };
  return map[status] || `<span class="badge">${ocEsc(status)}</span>`;
}

/**
 * 审核包类型标签 / Review packet type label.
 */
function reviewTypeLabel(packetType) {
  const map = {
    auto_observation: "自动观察 / Auto Observation",
    auto_lesson: "自动经验 / Auto Lesson",
    auto_hypothesis: "自动假设 / Auto Hypothesis"
  };
  return map[packetType] || ocEsc(packetType);
}

/**
 * 渲染单个审核包卡片 / Render a single review packet card.
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
          <div class="review-consequence">${escHtml((opts.approve || {}).consequence || "记录为正式条目")}</div>
        </div>
        <div class="review-action-group">
          <button class="review-decide-btn review-btn-reject" data-packet-id="${p.packet_id}" data-decision="reject">
            拒绝 / Reject
          </button>
          <div class="review-consequence">${escHtml((opts.reject || {}).consequence || "丢弃，不记录")}</div>
        </div>
        <div class="review-action-group">
          <button class="review-decide-btn review-btn-defer" data-packet-id="${p.packet_id}" data-decision="defer">
            搁置 / Defer
          </button>
          <div class="review-consequence">${escHtml((opts.defer || {}).consequence || "下次再看")}</div>
        </div>
        <div class="review-action-group">
          <button class="review-ai-consult-btn" data-packet-id="${p.packet_id}">
            询问 AI / Ask AI (${aiSec.recommended_tier || "light"}, ~$${(aiSec.estimated_cost_usd || 0.02).toFixed(2)})
          </button>
          <div class="review-consequence">${escHtml(aiSec.pre_built_question ? "让AI评估这个发现" : "暂无AI建议")}</div>
        </div>
      </div>`;
  }

  let aiResultHtml = "";
  if (p.ai_consultation_result) {
    const r = p.ai_consultation_result;
    aiResultHtml = `
      <div class="review-ai-result">
        <div class="review-ai-result-header">AI 咨询结果 / AI Consultation Result</div>
        <div class="review-ai-question"><strong>问题 / Question:</strong> ${escHtml(r.question_sent || "")}</div>
        <div class="review-ai-response"><strong>回复 / Response:</strong> ${escHtml(r.ai_response || "")}</div>
        <div class="review-ai-cost">费用 / Cost: $${(r.cost_usd || 0).toFixed(4)}</div>
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
        <div class="review-section-label">简要说明 / What Happened</div>
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
 * 渲染审核队列 / Render the review queue tab.
 */
function renderReviewQueue(queueData) {
  if (!queueData) return;

  const listEl = document.getElementById("reviewQueueList");
  if (listEl) {
    const pending = queueData.pending_packets || [];
    listEl.innerHTML = pending.length === 0
      ? '<div class="muted-row">暂无待审核项 / No pending review packets</div>'
      : pending.map(p => renderReviewPacketCard(p)).join("");
  }

  const decidedEl = document.getElementById("reviewRecentDecided");
  if (decidedEl) {
    const decided = queueData.recent_decided || [];
    if (decided.length > 0) {
      decidedEl.innerHTML = `
        <div class="review-decided-header">最近已处理 / Recently Decided (${decided.length})</div>
        ${decided.map(p => renderReviewPacketCard(p)).join("")}`;
    } else {
      decidedEl.innerHTML = "";
    }
  }

  // 更新待审核计数 / Update pending review count
  setText("lrnPendingCount", queueData.pending_count ?? 0);
}

/**
 * 触发自动扫描 / Trigger auto scan.
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
      `扫描${scanType} / Scan ${scanType}`, "success",
      result.state_revision || "-", "-",
      `生成 ${d.packets_generated || 0} 个审核包，跳过 ${d.skipped_duplicates || 0} 个重复。`,
      d
    );
    await loadDashboard();
  } catch (error) {
    setActionSummary(`扫描失败 / Scan Failed (${scanType})`, "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 对审核包做决定 / Apply a review decision.
 */
async function applyReviewDecision(packetId, decision) {
  try {
    const result = await apiPost(`/api/v1/learning/review/${encodeURIComponent(packetId)}/decide`, baseEnvelope({
      payload: { decision, reason: "" }
    }));
    const d = result.data || {};
    const labels = { approve: "批准", reject: "拒绝", defer: "搁置" };
    setActionSummary(
      `${labels[decision] || decision} / ${decision}`, "success",
      result.state_revision || "-", "-",
      `审核包 ${packetId} 已${labels[decision] || decision}。${d.record_created ? " 已创建记录 " + (d.created_record_id || "") : ""}`,
      d
    );
    await loadDashboard();
  } catch (error) {
    setActionSummary("审核失败 / Review Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 请求 AI 咨询 / Request AI consultation for a review packet.
 */
async function requestAIConsult(packetId) {
  try {
    const result = await apiPost(`/api/v1/learning/review/${encodeURIComponent(packetId)}/decide`, { ...baseEnvelope(), decision: 'ask_ai' });
    const d = result.data || {};
    setActionSummary(
      "AI 咨询 / AI Consult", "success",
      result.state_revision || "-", "-",
      `已咨询 AI (${d.ai_tier || "light"})，费用 $${(d.cost_usd || 0).toFixed(4)}`,
      d
    );
    await loadDashboard();
  } catch (error) {
    setActionSummary("AI 咨询失败 / AI Consult Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ── 事件绑定 / Event binding ──────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  ensureGuiEnhancements();

  // APR01-MEDIUM-13: Token is now in HttpOnly cookie. Clean up legacy localStorage.
  // Auto-connect using cookie auth (no manual token input needed).
  // APR01-MEDIUM-13：Token 已移至 HttpOnly cookie。清理旧 localStorage。
  // 使用 cookie 认证自动连接（无需手动输入 token）。
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

  // 使用事件委托处理所有动态按钮 / Use event delegation for all dynamic buttons
  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (target) {
      event.preventDefault();
      runQuickAction(target.dataset.action);
      return;
    }

    // 产品族配置应用 / Product family config apply
    const pfApply = event.target.closest(".pf-apply-btn");
    if (pfApply) {
      event.preventDefault();
      applyProductFamilyConfig(pfApply.dataset.family);
      return;
    }

    // 产品族权限应用 / Product family permissions apply
    const pfPermApply = event.target.closest(".pf-perm-apply-btn");
    if (pfPermApply) {
      event.preventDefault();
      applyProductFamilyPermissions(pfPermApply.dataset.family);
      return;
    }

    // 费用录入 / Cost entry submit
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

    // 系统设置：风险策略 / Settings: risk policy
    if (event.target.closest("#applyRiskSwitch")) {
      event.preventDefault();
      applyRiskPolicySetting();
      return;
    }

    // 系统设置：Demo/Learning / Settings: demo/learning
    if (event.target.closest("#applyDemoLearningSettings")) {
      event.preventDefault();
      applyDemoLearningSettings();
      return;
    }

    // ── L 章事件 / L-chapter events ─────────────────────────────────────────

    // 观察录入 / Observation submit
    if (event.target.closest("#submitObservation")) {
      event.preventDefault();
      submitObservation();
      return;
    }

    // 经验录入 / Lesson submit
    if (event.target.closest("#submitLesson")) {
      event.preventDefault();
      submitLesson();
      return;
    }

    // 假设录入 / Hypothesis submit
    if (event.target.closest("#submitHypothesis")) {
      event.preventDefault();
      submitHypothesis();
      return;
    }

    // 实验录入 / Experiment submit
    if (event.target.closest("#submitExperiment")) {
      event.preventDefault();
      submitExperiment();
      return;
    }

    // 假设审批按钮 / Hypothesis verdict buttons
    const hypVerdictBtn = event.target.closest(".hyp-verdict-btn");
    if (hypVerdictBtn) {
      event.preventDefault();
      applyHypothesisVerdict(hypVerdictBtn.dataset.hypId, hypVerdictBtn.dataset.verdict);
      return;
    }

    // 实验审批按钮 / Experiment approval buttons
    const expApproveBtn = event.target.closest(".exp-approve-btn");
    if (expApproveBtn) {
      event.preventDefault();
      applyExperimentApproval(expApproveBtn.dataset.expId, expApproveBtn.dataset.action);
      return;
    }

    // 实验完成按钮 / Experiment completion button
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

    // 自动扫描按钮 / Auto scan buttons
    const scanBtn = event.target.closest(".auto-scan-btn");
    if (scanBtn) {
      event.preventDefault();
      triggerAutoScan(scanBtn.dataset.scan);
      return;
    }

    // 审核决策按钮 / Review decision buttons
    const reviewDecideBtn = event.target.closest(".review-decide-btn");
    if (reviewDecideBtn) {
      event.preventDefault();
      applyReviewDecision(reviewDecideBtn.dataset.packetId, reviewDecideBtn.dataset.decision);
      return;
    }

    // AI 咨询按钮 / AI consultation button
    const aiConsultBtn = event.target.closest(".review-ai-consult-btn");
    if (aiConsultBtn) {
      event.preventDefault();
      requestAIConsult(aiConsultBtn.dataset.packetId);
      return;
    }

    // 学习标签页切换 / Learning tab switching
    const tabBtn = event.target.closest(".learning-tab");
    if (tabBtn) {
      event.preventDefault();
      const tabName = tabBtn.dataset.tab;
      // 切换标签页激活状态 / Toggle active tab
      document.querySelectorAll(".learning-tab").forEach(t => t.classList.remove("active"));
      tabBtn.classList.add("active");
      // 切换内容面板 / Toggle content panel
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

    // ── Paper Trading 按钮处理 / Paper Trading button handlers ──
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

    // ── Market Feed 按钮处理 / Market Feed button handlers ──
    const feedActionBtn = event.target.closest("[data-feed-action]");
    if (feedActionBtn) {
      event.preventDefault();
      handleMarketFeedAction(feedActionBtn.dataset.feedAction);
      return;
    }
  });
});

