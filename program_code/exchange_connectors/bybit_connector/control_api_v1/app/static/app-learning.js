/**
 * OpenClaw Learning Cockpit Functions
 * OpenClaw 學習駕駛艙函數
 *
 * MODULE_NOTE (EN): Extracted from app.js (FIX-08 file size).
 * MODULE_NOTE (中): 從 app.js 提取（FIX-08 文件大小）。
 */

"use strict";

// ═══════════════════════════════════════════════════════════════════════════════
// L 章渲染函数 / L-Chapter Render Functions
//
// 渲染学习驾驶舱各标签页内容和净 PnL 仪表盘。
// Render learning cockpit tab contents and Net PnL dashboard.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 置信度级别徽章 / Confidence level badge.
 * 根据置信度级别返回对应颜色的标记 / Returns colored badge based on confidence level.
 */
function confidenceBadge(level) {
  const colors = { fact: "#27ae60", inference: "#f39c12", hypothesis: "#3498db" };
  const labels = { fact: "事实/fact", inference: "推断/inference", hypothesis: "假设/hypothesis" };
  const color = colors[level] || "#999";
  return `<span class="confidence-badge" style="background:${color}">${labels[level] || ocEsc(level)}</span>`;
}

/**
 * 状态徽章 / Status badge for hypotheses and experiments.
 */
function statusBadge(status) {
  const colors = {
    proposed: "#3498db", under_review: "#f39c12", testing: "#9b59b6",
    validated: "#27ae60", invalidated: "#e74c3c", archived: "#95a5a6",
    pending_approval: "#f39c12", approved: "#27ae60", rejected: "#e74c3c",
    in_progress: "#9b59b6", completed: "#2ecc71"
  };
  const color = colors[status] || "#999";
  return `<span class="status-badge" style="background:${color}">${ocEsc(status)}</span>`;
}

/**
 * 渲染学习观察流和经验记忆 / Render learning feed (observations + lessons).
 */
function renderLearningFeed(feedData) {
  if (!feedData) return;

  // 渲染观察列表 / Render observations list
  const obsList = document.getElementById("observationsList");
  if (obsList) {
    const obs = feedData.observations_recent || [];
    obsList.innerHTML = obs.length === 0
      ? '<div class="muted-row">暂无观察记录 / No observations yet</div>'
      : obs.map(o => `
        <div class="learning-record-item">
          <div class="learning-record-header">
            ${confidenceBadge(o.confidence_level)}
            <span class="learning-record-category">${ocEsc(o.category)}</span>
            <span class="learning-record-ts">${fmtTs(o.recorded_ts_ms)}</span>
          </div>
          <div class="learning-record-title">${escHtml(o.title)}</div>
          <div class="learning-record-detail">${escHtml(o.detail)}</div>
          <div class="learning-record-id">${ocEsc(o.observation_id)}</div>
        </div>`).join("");
  }

  // 渲染经验列表 / Render lessons list
  const lesList = document.getElementById("lessonsList");
  if (lesList) {
    const les = feedData.lessons_recent || [];
    lesList.innerHTML = les.length === 0
      ? '<div class="muted-row">暂无经验记录 / No lessons yet</div>'
      : les.map(l => `
        <div class="learning-record-item">
          <div class="learning-record-header">
            ${confidenceBadge(l.confidence_level)}
            <span class="learning-record-category">${ocEsc(l.category)}</span>
            <span class="learning-record-ts">${fmtTs(l.recorded_ts_ms)}</span>
          </div>
          <div class="learning-record-title">${escHtml(l.title)}</div>
          <div class="learning-record-detail">${escHtml(l.detail)}</div>
          <div class="learning-record-id">${ocEsc(l.lesson_id)}</div>
        </div>`).join("");
  }

  // 更新统计 / Update stats
  const totals = feedData.totals || {};
  setText("lrnObsCount", totals.total_observations ?? 0);
  setText("lrnLesCount", totals.total_lessons ?? 0);
  setText("lrnHypCount", totals.total_hypotheses ?? 0);
  setText("lrnExpCount", totals.total_experiments ?? 0);
}

/**
 * 渲染假设和实验队列 / Render hypotheses and experiments queue.
 */
function renderLearningExperiments(expData) {
  if (!expData) return;

  // 渲染假设列表 / Render hypotheses list
  const hypList = document.getElementById("hypothesesList");
  if (hypList) {
    const hyps = expData.hypotheses || [];
    hypList.innerHTML = hyps.length === 0
      ? '<div class="muted-row">暂无假设 / No hypotheses yet</div>'
      : hyps.map(h => `
        <div class="learning-record-item">
          <div class="learning-record-header">
            ${statusBadge(h.status)}
            ${confidenceBadge(h.confidence_level || "hypothesis")}
            <span class="learning-record-ts">${fmtTs(h.recorded_ts_ms)}</span>
          </div>
          <div class="learning-record-title">${escHtml(h.title)}</div>
          <div class="learning-record-detail">${escHtml(h.description || "")}</div>
          <div class="learning-record-prediction"><strong>预测 / Prediction:</strong> ${escHtml(h.testable_prediction || "")}</div>
          <div class="learning-record-id">${ocEsc(h.hypothesis_id)}</div>
          ${h.status === "proposed" || h.status === "under_review" ? `
            <div class="learning-record-actions">
              <button class="hyp-verdict-btn" data-hyp-id="${ocEsc(h.hypothesis_id)}" data-verdict="approved">批准 / Approve</button>
              <button class="hyp-verdict-btn btn-danger" data-hyp-id="${ocEsc(h.hypothesis_id)}" data-verdict="rejected">拒绝 / Reject</button>
              <button class="hyp-verdict-btn btn-muted" data-hyp-id="${ocEsc(h.hypothesis_id)}" data-verdict="archived">归档 / Archive</button>
            </div>` : ""}
          ${h.operator_verdict ? `<div class="learning-record-verdict">判定 / Verdict: ${ocEsc(h.operator_verdict)} (${ocEsc(h.operator_verdict_reason || "-")})</div>` : ""}
        </div>`).join("");
  }

  // 渲染实验列表 / Render experiments list
  const expList = document.getElementById("experimentsList");
  if (expList) {
    const exps = expData.experiments || [];
    expList.innerHTML = exps.length === 0
      ? '<div class="muted-row">暂无实验 / No experiments yet</div>'
      : exps.map(e => `
        <div class="learning-record-item">
          <div class="learning-record-header">
            ${statusBadge(e.status)}
            <span class="learning-record-category">hyp: ${ocEsc(e.hypothesis_id)}</span>
            <span class="learning-record-ts">${fmtTs(e.recorded_ts_ms)}</span>
          </div>
          <div class="learning-record-title">${escHtml(e.title)}</div>
          <div class="learning-record-detail">${escHtml(e.description || "")}</div>
          <div class="learning-record-id">${ocEsc(e.experiment_id)}</div>
          ${e.status === "pending_approval" ? `
            <div class="learning-record-actions">
              <button class="exp-approve-btn" data-exp-id="${ocEsc(e.experiment_id)}" data-action="approved">批准 / Approve</button>
              <button class="exp-approve-btn btn-danger" data-exp-id="${ocEsc(e.experiment_id)}" data-action="rejected">拒绝 / Reject</button>
            </div>` : ""}
          ${e.status === "approved" ? `
            <div class="learning-record-actions">
              <button class="exp-complete-btn" data-exp-id="${ocEsc(e.experiment_id)}">标记完成 / Mark Complete</button>
            </div>` : ""}
          ${e.result_summary ? `<div class="learning-record-verdict">结论 / Result: ${escHtml(e.result_summary)} ${confidenceBadge(e.result_confidence_level || "inference")}</div>` : ""}
        </div>`).join("");
  }

  // 更新待审批计数 / Update pending count
  setText("lrnPendingCount", expData.pending_approval_count ?? 0);
}

/**
 * 渲染净 PnL 仪表盘 / Render Net PnL Dashboard.
 */
function renderNetPnlDashboard(dashData) {
  if (!dashData) return;
  const daily = dashData.daily || {};

  setText("npRealizedPnl", fmtPnl(daily.realized_pnl));
  setText("npUnrealizedPnl", fmtPnl(daily.unrealized_pnl));
  setText("npGrossPnl", fmtPnl(daily.gross_pnl));
  setText("npTotalCost", fmtPnl(daily.total_cost));
  setText("npNetPnl", fmtPnl(daily.net_operating_pnl));
  setText("npSnapshotCount", (dashData.entry_totals || {}).total_period_snapshots ?? 0);

  // 成本分解 / Cost breakdown
  const brkEl = document.getElementById("npCostBreakdown");
  if (brkEl) {
    const brk = dashData.cost_breakdown || {};
    const keys = Object.keys(brk);
    brkEl.innerHTML = keys.length === 0
      ? '<div class="muted-row">暂无成本 / No costs yet</div>'
      : keys.map(k => `<div class="breakdown-item"><span>${ocEsc(k)}</span><strong>${fmtPnl(brk[k])}</strong></div>`).join("");
  }

  // 趋势列表 / Trend list
  const trendEl = document.getElementById("npTrendList");
  if (trendEl) {
    const trend = dashData.net_pnl_trend || [];
    trendEl.innerHTML = trend.length === 0
      ? '<div class="muted-row">暂无周期快照 / No period snapshots</div>'
      : trend.map(t => `
        <div class="entry-item">
          <span class="entry-item-label">${escHtml(t.period_label)}</span>
          <span>净 PnL: <strong>${fmtPnl(t.net_operating_pnl)}</strong></span>
          <span>毛 PnL: ${fmtPnl(t.gross_pnl)}</span>
          <span>成本: ${fmtPnl(t.total_cost)}</span>
        </div>`).join("");
  }
}

/**
 * HTML 转义 / Simple HTML escape to prevent XSS.
 */
function escHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

// ═══════════════════════════════════════════════════════════════════════════════
// L 章动作处理器 / L-Chapter Action Handlers
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 提交观察记录 / Submit an observation record.
 */
async function submitObservation() {
  const title = document.getElementById("obsTitle")?.value?.trim();
  const detail = document.getElementById("obsDetail")?.value?.trim();
  const category = document.getElementById("obsCategory")?.value;
  const confidence = document.getElementById("obsConfidence")?.value;

  if (!title || !detail) {
    setActionSummary("录入失败", "failed", "-", "-", "请填写标题和详情 / Title and detail are required.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/observation", baseEnvelope({
      payload: { title, detail, category, confidence_level: confidence }
    }));
    summarizeActionResult("learning-observation", result);
    document.getElementById("obsTitle").value = "";
    document.getElementById("obsDetail").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("观察录入失败 / Observation Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 提交经验教训 / Submit a lesson.
 */
async function submitLesson() {
  const title = document.getElementById("lessonTitle")?.value?.trim();
  const detail = document.getElementById("lessonDetail")?.value?.trim();
  const category = document.getElementById("lessonCategory")?.value;
  const confidence = document.getElementById("lessonConfidence")?.value;

  if (!title || !detail) {
    setActionSummary("录入失败", "failed", "-", "-", "请填写标题和详情 / Title and detail are required.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/lesson", baseEnvelope({
      payload: { title, detail, category, confidence_level: confidence }
    }));
    summarizeActionResult("learning-lesson", result);
    document.getElementById("lessonTitle").value = "";
    document.getElementById("lessonDetail").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("经验录入失败 / Lesson Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 提交假设 / Submit a hypothesis.
 */
async function submitHypothesis() {
  const title = document.getElementById("hypTitle")?.value?.trim();
  const description = document.getElementById("hypDescription")?.value?.trim();
  const prediction = document.getElementById("hypPrediction")?.value?.trim();

  if (!title || !description || !prediction) {
    setActionSummary("录入失败", "failed", "-", "-", "请填写标题、描述和可检验预测 / Title, description and prediction required.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/hypothesis", baseEnvelope({
      payload: { title, description, testable_prediction: prediction }
    }));
    summarizeActionResult("learning-hypothesis", result);
    document.getElementById("hypTitle").value = "";
    document.getElementById("hypDescription").value = "";
    document.getElementById("hypPrediction").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("假设录入失败 / Hypothesis Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 提交实验 / Submit an experiment.
 */
async function submitExperiment() {
  const hypothesisId = document.getElementById("expHypothesisId")?.value?.trim();
  const title = document.getElementById("expTitle")?.value?.trim();
  const description = document.getElementById("expDescription")?.value?.trim();
  const method = document.getElementById("expMethod")?.value?.trim();
  const criteria = document.getElementById("expSuccessCriteria")?.value?.trim();

  if (!hypothesisId || !title || !description || !method || !criteria) {
    setActionSummary("录入失败", "failed", "-", "-", "请填写所有必填字段 / All required fields must be filled.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/experiment", baseEnvelope({
      payload: { hypothesis_id: hypothesisId, title, description, method, success_criteria: criteria }
    }));
    summarizeActionResult("learning-experiment", result);
    document.getElementById("expTitle").value = "";
    document.getElementById("expDescription").value = "";
    document.getElementById("expMethod").value = "";
    document.getElementById("expSuccessCriteria").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("实验录入失败 / Experiment Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 假设审批 / Hypothesis verdict.
 */
async function applyHypothesisVerdict(hypothesisId, verdict) {
  try {
    const result = await apiPost(`/api/v1/learning/hypothesis/${hypothesisId}/verdict`, baseEnvelope({
      payload: { verdict, reason: "operator decision via GUI" }
    }));
    summarizeActionResult("hypothesis-verdict", result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("假设审批失败 / Verdict Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 实验审批 / Experiment approval.
 */
async function applyExperimentApproval(experimentId, action) {
  try {
    const result = await apiPost(`/api/v1/learning/experiment/${experimentId}/approve`, baseEnvelope({
      payload: { action, reason: "operator decision via GUI" }
    }));
    summarizeActionResult("experiment-approval", result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("实验审批失败 / Approval Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 实验完成 / Experiment completion.
 */
async function applyExperimentCompletion(experimentId) {
  const summary = await openPromptModal({
    title: "实验结论摘要 / Experiment Result",
    body: "记录实验完成后的 operator 结论。",
    label: "摘要 / Summary",
    required: true,
    multiline: true,
    confirmLabel: "提交 / Submit"
  });
  if (!summary) return;
  const confidence = await openPromptModal({
    title: "置信度级别 / Confidence Level",
    label: "级别 / Level",
    defaultValue: "inference",
    required: true,
    choices: [
      { value: "fact", label: "fact — 事实" },
      { value: "inference", label: "inference — 推断" },
      { value: "hypothesis", label: "hypothesis — 假设" }
    ],
    confirmLabel: "提交 / Submit"
  });
  if (!confidence) return;

  try {
    const result = await apiPost(`/api/v1/learning/experiment/${experimentId}/complete`, baseEnvelope({
      payload: { result_summary: summary, result_confidence_level: confidence }
    }));
    summarizeActionResult("experiment-completion", result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("实验完成失败 / Completion Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 保存周期快照 / Save period snapshot.
 */
async function savePeriodSnapshot() {
  const label = document.getElementById("periodLabel")?.value?.trim();
  if (!label) {
    setActionSummary("失败", "failed", "-", "-", "请输入周期标签 / Period label is required.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/pnl-period-snapshot", baseEnvelope({
      payload: { period_label: label }
    }));
    summarizeActionResult("period-snapshot", result);
    document.getElementById("periodLabel").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("快照保存失败 / Snapshot Failed", "failed", "-", "-", String(error), String(error));
  }
}
