/**
 * agent-tracker.js — AI 团队工作台前端 / AI Crew Dashboard frontend
 *
 * MODULE_NOTE (中):
 *   把 5-Agent (Scout / Strategist / Guardian / Analyst / Executor) 当前状态、
 *   今日成本、影子 vs 真仓视觉强隔离、最近活动 feed、思考预算进度条、
 *   决策租约 (lease) 与 H1-H5 治理 reject 摘要全部聚合在 Learning 标签内。
 *   纯只读：本档案不发任何 POST / PUT / DELETE，无危险按钮。
 *
 *   Round 2 修复（按 E2 retro review）：
 *     - C-1 (b): loadAgentFeed 改用 /strategist/history rows + 真实 schema
 *               (engine_mode/strategy_name/applied_at/source/reason)
 *     - C-1 (a): loadShadowLiveDiff 改呼 /api/v1/agents/shadow_vs_live_summary
 *               (新 endpoint，由 E1-A round 2 后端同步交付)
 *     - C-1 (a): loadAgentGovernance rejects 改呼 /api/v1/agents/recent_rejects
 *               (新 endpoint，取代不被识别的 ?outcome=reject query param)
 *     - C-2: loadAgentBudget 改用 nested schema (today.total_usd / budget.daily_hard_cap_usd)
 *     - 信任 backend 字段：renderAgentCard 不再 fallback shadow_mode=true，
 *       null/undefined → unknown state 红警语 (fail-loud)
 *     - M-2: 各 loader 用 module-level _pollSeq[key]++ ID stale-bail 防 race
 *
 * MODULE_NOTE (EN):
 *   Aggregate 5-Agent live state + today cost + shadow-vs-live visual isolation
 *   + recent activity feed + thinking-budget progress + governance leases / rejects
 *   into the Learning tab as a sub-section. Read-only: no POST / PUT / DELETE
 *   issued by this file, no dangerous toggle buttons.
 *
 *   Round 2 fixes (per E2 retro review):
 *     - C-1 (b): loadAgentFeed reads `/strategist/history` rows with real schema
 *               (engine_mode / strategy_name / applied_at / source / reason)
 *     - C-1 (a): loadShadowLiveDiff hits new `/api/v1/agents/shadow_vs_live_summary`
 *               (delivered in parallel by E1-A round 2 backend)
 *     - C-1 (a): loadAgentGovernance rejects hits new `/api/v1/agents/recent_rejects`
 *               (replaces unrecognized `?outcome=reject` query param)
 *     - C-2: loadAgentBudget uses nested schema (today.total_usd / budget.daily_hard_cap_usd)
 *     - Trust backend fields: renderAgentCard drops shadow_mode=true fallback;
 *       null/undefined → unknown state with red banner (fail-loud)
 *     - M-2: per-key `_pollSeq[key]++` ID stale-bail in each loader to prevent
 *       race conditions between fast successive refreshes.
 *
 * 关联文件 / Related:
 *   - tab-learning.html (loads this file; injects HTML scaffold)
 *   - common.js (ocApi / ocEsc / ocChip / ocSetHtml / ocStartRefresh helpers)
 *   - GET /api/v1/agents/roster                 (existing, agents_routes.py:712)
 *   - GET /api/v1/strategist/history            (existing, strategist_history_routes.py)
 *   - GET /api/v1/agents/shadow_vs_live_summary (NEW, round 2 contract)
 *   - GET /api/v1/agents/recent_rejects         (NEW, round 2 contract)
 *   - GET /api/v1/governance/leases             (existing)
 *   - GET /api/v1/paper/layer2/cost             (existing, nested schema)
 *
 * Refresh strategy:
 *   每个区块各自独立 setInterval；页面隐藏 (visibilitychange / pagehide) 时
 *   全部 clearInterval 以防 iframe 切走还在背景烧 API。
 *
 * Plan reference: aa-nifty-walrus.md (Operator-local plan; T3 + T4 + T5 frontend scope)
 */

"use strict";

// ─────────────────────────────────────────────────────────────────────────────
// State / Refresh timer registry / 全局刷新定时器注册表
// ─────────────────────────────────────────────────────────────────────────────
const _AGENT_TIMERS = {
  roster: null,
  feed: null,
  shadowLive: null,
  governance: null,
  budget: null,
};

// ─────────────────────────────────────────────────────────────────────────────
// Per-loader poll sequence counters / 每个 loader 的请求序号 (M-2 stale-bail)
// ─────────────────────────────────────────────────────────────────────────────
// `ocApi` 不接受 AbortSignal；改用单调递增 ID 在 .then 开头比对，过期就 bail。
// `ocApi` doesn't accept AbortSignal; use monotonically increasing IDs and
// compare in .then handler — if stale (newer call already started) abort render.
const _pollSeq = {
  roster: 0,
  feed: 0,
  shadowLive: 0,
  governance: 0,
  budget: 0,
};

/**
 * Register a setInterval timer keyed by id (auto-clears previous timer with same id).
 * 用 id 注册 setInterval；同 id 重复注册先清旧 timer。
 *
 * @param {string} key - timer slot key in _AGENT_TIMERS
 * @param {Function} fn - interval callback
 * @param {number} intervalMs - >= 30000 enforced for plan §约束 3
 */
function _agentRegisterTimer(key, fn, intervalMs) {
  if (intervalMs < 30000) {
    console.warn("[agent-tracker] interval < 30s rejected, forcing 30s on " + key);
    intervalMs = 30000;
  }
  if (_AGENT_TIMERS[key]) clearInterval(_AGENT_TIMERS[key]);
  _AGENT_TIMERS[key] = setInterval(fn, intervalMs);
}

/**
 * Clear all agent-tracker intervals when iframe is hidden / unloaded.
 * iframe 切走 / 卸载时清掉所有 agent-tracker 的 setInterval，避免背景烧 API。
 */
function _agentClearAllTimers() {
  Object.keys(_AGENT_TIMERS).forEach((k) => {
    if (_AGENT_TIMERS[k]) {
      clearInterval(_AGENT_TIMERS[k]);
      _AGENT_TIMERS[k] = null;
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Three-state container helper / 载入/空/失败三态切换
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Toggle 3-state container visibility (loading / empty / error / data).
 * 切换三态容器：所有 *-loading / *-empty / *-error 隐藏，仅显示选中态；
 * 'data' 表示真实数据态 — 所有 placeholder 都隐藏，调用端自行 ocSetHtml 主区块。
 *
 * @param {string} prefix - element id prefix, e.g. 'agent-roster'
 * @param {'loading'|'empty'|'error'|'data'} type - 当前要展示哪一态
 */
function setLoadingState(prefix, type) {
  const types = ["loading", "empty", "error"];
  types.forEach((t) => {
    const el = document.getElementById(prefix + "-" + t);
    if (el) el.style.display = (t === type) ? "" : "none";
  });
  const dataEl = document.getElementById(prefix + "-data");
  if (dataEl) dataEl.style.display = (type === "data") ? "" : "none";
}

// ─────────────────────────────────────────────────────────────────────────────
// State badge mapping / Agent 状态 → emoji + 颜色 + 中文 mapping
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Map (role, state) to badge { emoji, label_zh, chipType }.
 * 5 角色 × 14 state 的语义化映射；未知 state 一律红色 + ⚠️ 不留灰。
 *
 * chipType 对应 common.js ocChip 的 type: good / warn / bad / neutral / info / live。
 *
 * 设计意图：普通人看一眼就知道「这位 AI 现在在干嘛、健康不健康」，不靠英文。
 */
const _AGENT_STATE_MAP = {
  // 跨 role 通用
  active:      { emoji: "🟢", label_zh: "活跃中",       chip: "good"    },
  idle:        { emoji: "💤", label_zh: "待命",         chip: "neutral" },
  slow:        { emoji: "🐢", label_zh: "反应慢",       chip: "warn"    },
  offline:     { emoji: "🔌", label_zh: "已离线",       chip: "bad"     },
  thinking:    { emoji: "🤔", label_zh: "思考中",       chip: "info"    },
  watching:    { emoji: "👀", label_zh: "盯盘中",       chip: "info"    },
  budget_low:  { emoji: "🪫", label_zh: "预算告急",     chip: "warn"    },
  rejecting:   { emoji: "🛑", label_zh: "拒单中",       chip: "warn"    },
  guarding:    { emoji: "🛡️", label_zh: "守门中",       chip: "good"    },
  tightening:  { emoji: "🔒", label_zh: "收紧门槛",     chip: "warn"    },
  frozen:      { emoji: "🥶", label_zh: "冻结",         chip: "bad"     },
  shadow:      { emoji: "🌙", label_zh: "影子模式",     chip: "info"    },
  live:        { emoji: "🔴", label_zh: "真仓执行",     chip: "live"    },
  reviewing:   { emoji: "🔍", label_zh: "审核中",       chip: "info"    },
  waiting:     { emoji: "⏳", label_zh: "等待数据",     chip: "neutral" },
  unknown:     { emoji: "⚠️", label_zh: "状态未确认",   chip: "bad"     },
};

/**
 * Render a state badge HTML for a (role, state) pair.
 * 输出 inline-flex 的 emoji + label chip，未知 state 强制 bad chip + 警语。
 *
 * @param {string} role - agent role (scout/strategist/guardian/analyst/executor)
 * @param {string} state - state token from backend
 * @param {string} stateLabelZh - 后端给的中文标签 (优先用)
 * @returns {string} sanitized HTML
 */
function agentStateBadge(role, state, stateLabelZh) {
  const cfg = _AGENT_STATE_MAP[state] || _AGENT_STATE_MAP.unknown;
  const txt = stateLabelZh || cfg.label_zh;
  return ocChip(cfg.emoji + " " + txt, cfg.chip);
}

// ─────────────────────────────────────────────────────────────────────────────
// Tooltip helper / 8 条术语提示
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Bilingual tooltip glossary — 8 terms required by plan T4.
 * 术语 hover 双语提示；HTML title 属性已天然安全，但术语 key 仍走 ocEsc 防注入。
 */
const _AGENT_TOOLTIPS = {
  shadow:        "Agent 的所有决策只记录不送单 / Shadow mode: decisions logged, no real orders",
  edge:          "这笔交易预期能赚多少（扣掉手续费滑价之后）/ Expected net profit per trade",
  budget:        "每天给 AI 的思考费用上限，用完就停想 / Daily AI thinking budget",
  lease:         "Agent 的「这次允许下单」许可证 / Time-bound trading permission",
  governance:    "5 道关卡审 AI 提案 / 5-stage AI governance",
  heartbeat:     "最近活动心跳；程序是否已启动看「程序」字段 / Last activity heartbeat",
  reasoning:     "Agent 这次决策的完整思考过程 / Full reasoning trace",
  cost_edge:     "花的钱 ÷ 赚的钱，越低越好；超过 0.8 系统会建议减仓 / Cost-to-edge ratio",
};

/**
 * Wrap a label with a tooltip span.
 * 包一个 hover 双语提示的 span；自动 escape 文字 + tooltip。
 *
 * @param {string} key - _AGENT_TOOLTIPS key
 * @param {string} label - 显示文字
 * @returns {string} sanitized HTML
 */
function withTip(key, label) {
  const tip = _AGENT_TOOLTIPS[key] || "";
  return '<span class="agent-tip" title="' + ocEsc(tip)
    + '" style="border-bottom:1px dashed var(--text-dim);cursor:help">'
    + ocEsc(label) + '</span>';
}

// ─────────────────────────────────────────────────────────────────────────────
// Time helpers / 时间格式化
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Compute "N 分钟前" string from ISO timestamp.
 * 从 ISO 时间戳算「几分钟前」；> 60 min 显示小时；> 24h 显示天数；空 → '--'。
 */
function _agentRelTime(isoTs) {
  if (!isoTs) return "--";
  const t = new Date(isoTs).getTime();
  if (!isFinite(t)) return "--";
  const dMs = Date.now() - t;
  if (dMs < 0) return "刚刚";
  const sec = Math.floor(dMs / 1000);
  if (sec < 60) return sec + " 秒前";
  const min = Math.floor(sec / 60);
  if (min < 60) return min + " 分钟前";
  const hr = Math.floor(min / 60);
  if (hr < 24) return hr + " 小时前";
  const day = Math.floor(hr / 24);
  return day + " 天前";
}

/**
 * Format an ISO timestamp to local hh:mm:ss for compact reject list rows.
 * 把 ISO 时间戳格式化成本地 hh:mm:ss（拒单条目紧凑显示用）。
 */
function _agentTimeShort(isoTs) {
  if (!isoTs) return "--";
  const d = new Date(isoTs);
  if (!isFinite(d.getTime())) return "--";
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return hh + ":" + mm + ":" + ss;
}

/**
 * Heartbeat freshness chip: <2min good, 2-5min warn, >5min bad.
 * 心跳 chip 颜色：<2 分钟绿、2-5 分钟黄、>5 分钟红。
 */
function _heartbeatChip(isoTs) {
  if (!isoTs) return ocChip("无心跳", "bad");
  const dMs = Date.now() - new Date(isoTs).getTime();
  const min = dMs / 60000;
  let chip = "good";
  if (min > 5) chip = "bad";
  else if (min > 2) chip = "warn";
  return ocChip("💓 " + _agentRelTime(isoTs), chip);
}

// ─────────────────────────────────────────────────────────────────────────────
// Block A — 5-Agent roster cards / 5-Agent 卡片
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Render one agent card (4-column layout: identity / now-doing / state / cost).
 * 渲染单张 Agent 卡片；Executor 收到 shadow_mode 强制三层视觉隔离。
 *
 * Round 2 改动：信任后端 `shadow_mode` 字段 — null/undefined 不再 fallback 为 true，
 * 而是强制 unknown state + 红警语 (fail-loud)；后端 ExecutorAgent.get_stats() 已在
 * round 2 backend 接线 shadow_mode + orders_submitted 真实字段。
 *
 * Round 2 change: trust backend `shadow_mode` field — null/undefined no longer
 * silently fallback to true; instead force unknown state + red banner (fail-loud).
 * Backend ExecutorAgent.get_stats() now returns real shadow_mode + orders_submitted.
 *
 * @param {object} agent - roster.agents[i] payload
 * @returns {string} sanitized HTML
 */
function renderAgentCard(agent) {
  const role = agent.role || "unknown";
  let state = agent.state || "unknown";
  const isExecutor = role === "executor";

  // Trust backend shadow_mode — 严格 boolean 检查，null/undefined → unknown
  // strict boolean check; null/undefined → force state=unknown to fail-loud
  let isLive = false;
  let executorUnclear = false;
  if (isExecutor) {
    if (agent.shadow_mode === false) {
      isLive = true;
    } else if (agent.shadow_mode === true) {
      isLive = false;
    } else {
      // null / undefined / non-boolean — backend contract drift
      executorUnclear = true;
      state = "unknown";
    }
  }
  const isUnknown = state === "unknown";

  // 卡片底色 / Card background — Executor shadow vs live triple-isolation (plan T3)
  let bgStyle = "background:var(--card-bg);";
  let bannerHtml = "";
  if (isExecutor && !executorUnclear) {
    if (isLive) {
      bgStyle = "background:linear-gradient(135deg, #3d0d0d, #5c1a1a);"
              + "animation:agent-breathing 4s ease-in-out infinite;";
      bannerHtml = '<div class="exec-banner exec-banner-live">'
        + '🔴 真仓执行中 — 这位 Agent 正在用真钱下单'
        + '</div>';
    } else {
      bgStyle = "background:linear-gradient(135deg, #0d1f3d, #1a2f5c);";
      bannerHtml = '<div class="exec-banner exec-banner-shadow">'
        + '🌙 ' + withTip("shadow", "影子模式")
        + ' — 所有动作仅模拟，不会送真单到交易所'
        + '</div>';
    }
  }

  // unknown 状态强制红 + 暂停接单警语，永远不留灰色
  // Executor shadow_mode null → 额外标注「契约缺失，暂停接单」(fail-loud)
  let unknownBanner = "";
  if (isUnknown) {
    const txt = executorUnclear
      ? '⚠️ 后端未回报 shadow_mode 字段，已暂停接单 / Backend missing shadow_mode field, intake paused'
      : '⚠️ 状态未确认，已暂停接单 / State unknown, intake paused';
    unknownBanner = '<div style="background:rgba(248,81,73,0.15);border:1px solid var(--red);'
      + 'border-radius:6px;padding:6px 10px;margin-bottom:8px;color:var(--red);font-size:11px">'
      + ocEsc(txt)
      + '</div>';
  }

  // 4 列内容 / 4-column content
  const emoji = agent.emoji || "🤖";
  const labelZh = ocEsc(agent.label_zh || role);
  const labelEn = ocEsc(agent.label_en || role);
  const summary = ocEsc(agent.summary_zh || "（暂无概述）");
  const stateReason = ocEsc(agent.state_reason_zh || "");
  const runtimeState = String(agent.runtime_state || "--");
  const runtimeChip = ocChip("程序 " + runtimeState, runtimeState === "running" ? "good" : "bad");
  const stateBadge = agentStateBadge(role, state, agent.state_label_zh);
  const heartbeat = _heartbeatChip(agent.last_heartbeat_ts);

  // Round 2: Executor decisions 用 today_orders（真后端字段）；其他角色用 today_decisions
  // Round 2: Executor uses today_orders (real backend field per round 2 wiring);
  //          others fall back to today_decisions.
  let decisions;
  if (isExecutor) {
    decisions = (agent.today_orders != null) ? agent.today_orders : "--";
  } else {
    decisions = (agent.today_decisions != null) ? agent.today_decisions : 0;
  }
  const cost = (agent.today_cost_usd != null) ? agent.today_cost_usd : 0;

  // Executor live 模式数字单位强化
  let decisionLabel = "今日决策";
  if (isExecutor) {
    if (executorUnclear) decisionLabel = "今日下单";
    else                 decisionLabel = isLive ? "真实成单" : "模拟成单";
  }

  let html = '<div class="agent-card" style="' + bgStyle
    + 'border:1px solid var(--border);border-radius:10px;padding:14px;'
    + 'display:flex;flex-direction:column;gap:8px">';

  if (bannerHtml) html += bannerHtml;
  if (unknownBanner) html += unknownBanner;

  // Row 1: identity
  html += '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">';
  html += '<div>';
  html += '<div style="font-size:18px;font-weight:600">' + emoji + ' ' + labelZh + '</div>';
  html += '<div style="font-size:11px;color:var(--text-dim)">' + labelEn + '</div>';
  html += '</div>';
  html += '<div style="text-align:right">' + stateBadge + '</div>';
  html += '</div>';

  // Row 2: now-doing summary
  html += '<div style="font-size:12px;line-height:1.6;color:var(--text);'
    + 'background:rgba(13,17,23,0.4);border-left:2px solid var(--accent);'
    + 'padding:6px 10px;border-radius:0 6px 6px 0">'
    + '<span style="color:var(--text-dim)">现在在做：</span>' + summary
    + '</div>';
  if (stateReason) {
    html += '<div style="font-size:11px;line-height:1.5;color:var(--text-dim);'
      + 'background:rgba(210,153,34,0.08);border-left:2px solid var(--yellow);'
      + 'padding:6px 10px;border-radius:0 6px 6px 0">'
      + '<span style="color:var(--yellow)">状态依据：</span>' + stateReason
      + '</div>';
  }

  // Row 3: stats (heartbeat + decisions + cost)
  html += '<div style="display:flex;justify-content:space-between;align-items:center;'
    + 'gap:8px;font-size:11px;color:var(--text-dim);flex-wrap:wrap">';
  html += '<div>' + runtimeChip + '</div>';
  html += '<div>' + withTip("heartbeat", "心跳") + '：' + heartbeat + '</div>';
  html += '<div>' + ocEsc(decisionLabel) + '：<strong style="color:var(--text)">'
    + ocEsc(String(decisions)) + '</strong> 笔</div>';
  html += '<div>今日成本：<strong style="color:var(--text)">$' + Number(cost).toFixed(2)
    + '</strong></div>';
  html += '</div>';

  html += '</div>';
  return html;
}

/**
 * Load + render the 5-Agent roster grid (Block A).
 * 拉 /api/v1/agents/roster 渲染 5 张卡片；30s 自动刷新。
 *
 * Stale-bail: 启动前 ++_pollSeq.roster；await 后比对，过期就放弃 render。
 * Stale-bail: increment _pollSeq.roster pre-call; bail render if stale post-await.
 */
async function loadAgentRoster() {
  const mySeq = ++_pollSeq.roster;
  setLoadingState("agent-roster", "loading");
  let d;
  try {
    d = await ocApi("/api/v1/agents/roster");
  } catch (_) {
    d = null;
  }
  if (mySeq !== _pollSeq.roster) return;  // newer call already in flight, bail
  if (!d) {
    setLoadingState("agent-roster", "error");
    return;
  }
  // Backend contract returns `{data: {ts, agents}}` envelope (agents_routes.py:765).
  // 后端契约：{ok, data:{ts, agents, ...}, ...}。
  const payload = d.data || d;
  const agents = payload.agents || [];
  if (!agents.length) {
    setLoadingState("agent-roster", "empty");
    return;
  }
  let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:12px">';
  agents.forEach((a) => {
    html += renderAgentCard(a);
  });
  html += '</div>';
  ocSetHtml("agent-roster-data", html);
  setLoadingState("agent-roster", "data");
}

// ─────────────────────────────────────────────────────────────────────────────
// Block C — Recent activity feed / 最近活动 feed
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Map a strategist `source` value to a human-readable Chinese tag.
 * 把 strategist_applied_params.source 映射成中文短句，普通人看得懂。
 */
function _strategistSourceZh(source) {
  if (!source) return "应用参数";
  const map = {
    "manual_promote":      "手动晋升",
    "shadow_to_live":      "影子→真仓晋升",
    "auto_apply":          "自动套用",
    "rust_apply":          "Rust 引擎套用",
    "hot_reload":          "热重载",
    "rollback":            "回滚",
  };
  return map[source] || source;
}

/**
 * Load + render Strategist applied-params history + recent shadow fills as a
 * unified activity feed. 60s 自动刷新。
 *
 * Round 2 修复（C-1 b）：
 *   - strategist part 改读 `data.rows` (真 schema)，欄位映射如下：
 *     * 时间 = h.applied_at (ISO)
 *     * 角色 = '策略师' (固定)
 *     * 动作 = '套用参数: ' + h.strategy_name + ' (' + h.source + ')'
 *     * symbol slot 显示 h.strategy_name (后端无 symbol，系统按 strategy 套用)
 *     * 详情 = h.reason (短句)
 *   - shadow_fills 改读 `data.rows` (真 schema)
 *   - 两个 ocApi 都加 ?engine=demo 限定 (plan §C「demo intent + live_demo realized」)
 *
 * Round 2 fix (C-1 b):
 *   - strategist part reads `data.rows` per real schema (engine_mode/strategy_name/
 *     applied_at/source/reason).
 *   - shadow_fills part reads `data.rows`.
 *   - Both calls add `?engine=demo` per plan §C ("demo intent + live_demo realized").
 */
async function loadAgentFeed() {
  const mySeq = ++_pollSeq.feed;
  setLoadingState("agent-feed", "loading");
  const [histR, fillsR] = await Promise.allSettled([
    ocApi("/api/v1/strategist/history?engine=demo&limit=10"),
    ocApi("/api/v1/edge/shadow_fills?engine=demo&limit=10"),
  ]);
  if (mySeq !== _pollSeq.feed) return;
  const histOk = histR.status === "fulfilled" && histR.value;
  const fillsOk = fillsR.status === "fulfilled" && fillsR.value;
  if (!histOk && !fillsOk) {
    setLoadingState("agent-feed", "error");
    return;
  }
  // Merge entries with type tag, sort by ts desc
  // 把两路 entry 加 type 标签合一条时间线，按时间倒序排列。
  const entries = [];
  if (histOk) {
    // strategist_history_routes.py returns {data: {rows: [...], ...}}
    // each row: {id, engine_mode, strategy_name, applied_at, applied_at_ms,
    //            source, reason, prev_params_json, params_json}
    const histPayload = histR.value.data || histR.value;
    const rows = histPayload.rows || [];
    rows.forEach((h) => {
      const sourceZh = _strategistSourceZh(h.source);
      const strat = h.strategy_name || "?";
      entries.push({
        type: "strategist",
        ts: h.applied_at,
        outcome: sourceZh,
        symbol: strat,                     // strategy_name as symbol slot
        summary: "套用参数: " + strat + (h.reason ? " · " + h.reason : ""),
      });
    });
  }
  if (fillsOk) {
    // shadow_fills_routes.py returns {data: {rows: [...], ...}}
    // W1-T3 (PA 2026-04-29 strategy_name attribution cleanup §1.2 GUI passthrough):
    //   strategy_name will normalise to one of 5 enum values
    //   (ma_crossover/bb_reversion/bb_breakout/grid_trading/funding_arb) once
    //   W1-T2 lands; close-path detail moves to a sibling `exit_reason` field.
    //   Render `<strategy> (<exit_reason>)` when reason present, otherwise just
    //   the strategy. Both fields go through ocEsc downstream (see entries.slice
    //   render block below) so untrusted free-text exit_reason is XSS-safe.
    // W1-T3：strategy_name 正規化後 close path 細節落在 exit_reason；
    //   有 reason 顯示 `<strategy> (<reason>)`，否則僅顯示 strategy。
    //   兩個欄位都經 ocEsc 渲染 → free-text exit_reason XSS 安全。
    const fillsPayload = fillsR.value.data || fillsR.value;
    const rows = fillsPayload.rows || [];
    rows.forEach((f) => {
      const stratLabel = (f.strategy_name || f.strategy || "");
      const exitReason = f.exit_reason || "";
      const stratAndReason = exitReason
        ? stratLabel + " (" + exitReason + ")"
        : stratLabel;
      entries.push({
        type: "shadow_fill",
        ts: f.ts || f.created_at,
        outcome: "影子成交",
        symbol: f.symbol || "",
        summary: stratAndReason + " · " + (f.side || "")
          + " · qty " + (f.qty != null ? f.qty : "--"),
      });
    });
  }
  entries.sort((a, b) => {
    const ta = new Date(a.ts || 0).getTime();
    const tb = new Date(b.ts || 0).getTime();
    return tb - ta;
  });
  if (!entries.length) {
    setLoadingState("agent-feed", "empty");
    return;
  }
  let html = '<div style="display:flex;flex-direction:column;gap:6px">';
  entries.slice(0, 15).forEach((e) => {
    let chipType = "info";
    let typeLabel = "动态";
    if (e.type === "strategist") {
      typeLabel = "策略师";
      chipType = "info";
    } else if (e.type === "shadow_fill") {
      typeLabel = "影子成交";
      chipType = "info";
    }
    html += '<div style="padding:6px 0;border-bottom:1px solid #21262d;font-size:12px">';
    html += '<div style="display:flex;justify-content:space-between;align-items:center;gap:6px">';
    html += '<span>' + ocChip(typeLabel, chipType) + ' '
      + ocChip(ocEsc(e.outcome || "--"), chipType)
      + (e.symbol ? ' <strong>' + ocEsc(e.symbol) + '</strong>' : '')
      + '</span>';
    html += '<span style="color:var(--text-dim);font-size:11px">' + ocEsc(_agentRelTime(e.ts)) + '</span>';
    html += '</div>';
    if (e.summary) {
      html += '<div style="margin-top:3px;color:var(--text-dim);font-size:11px;line-height:1.5">'
        + ocEsc(e.summary) + '</div>';
    }
    html += '</div>';
  });
  html += '</div>';
  ocSetHtml("agent-feed-data", html);
  setLoadingState("agent-feed", "data");
}

// ─────────────────────────────────────────────────────────────────────────────
// Block E — Demo engine vs LiveDemo engine fills diff / Demo 引擎 vs LiveDemo 引擎成交对比
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Load + render Demo engine vs LiveDemo engine fills summary.
 * 拉 /api/v1/agents/shadow_vs_live_summary 渲染对比数字；60s 刷新。
 *
 * 语义说明 / Semantic note:
 *   后端 SQL 抓 trading.fills WHERE engine_mode IN ('demo','live','live_demo') —
 *   两边都是真实送单到 Bybit demo endpoint 的成交，差别在于 risk_config 引擎：
 *     - demo column: engine_mode='demo'，使用 risk_config_demo.toml
 *     - live_demo column: engine_mode='live_demo'，Live 管线走 demo endpoint，
 *       使用 risk_config_live.toml（CLAUDE.md §三 engine_mode_tag_live_demo）
 *   不要把这卡当成 ExecutorAgent shadow_mode（_shadow_mode=True 写到
 *   learning.decision_shadow_* 是另一回事，与本卡无关）。
 *
 *   Backend SQL filters trading.fills by engine_mode tag. Both sides are real fills
 *   submitted to Bybit demo endpoint. Difference is which risk_config TOML the engine
 *   pipeline reads. Unrelated to ExecutorAgent _shadow_mode (which logs intents to
 *   learning.decision_shadow_* without dispatching to Rust).
 *
 * 后端 endpoint URL 保留为 /api/v1/agents/shadow_vs_live_summary（backward compat）—
 * 后端将新增 alias，前端这里不动 URL。
 * Endpoint URL retained for backward compat; backend will add alias.
 *
 * Round 2 修复（C-1 a）：
 *   - schema：{demo:{count, total_pnl_usd, avg_slippage_bps},
 *             live_demo:{count, total_pnl_usd, avg_slippage_bps},
 *             diff:{fill_rate_delta_pct, slippage_delta_bps}}
 *   - 不 fallback 旧字段 — fail-loud；missing → empty state
 *
 * 文案：
 *   - Demo 引擎卡：「Demo 成交 N 笔 · Demo PnL +$X.XX」
 *   - LiveDemo 引擎卡：「LiveDemo 成交 N 笔 · LiveDemo PnL +$X.XX」
 *   - 中央 diff 行（Demo vs LiveDemo）：fill_rate_delta_pct (≥10% 红) + slippage_delta_bps
 */
async function loadShadowLiveDiff() {
  const mySeq = ++_pollSeq.shadowLive;
  setLoadingState("agent-shadow-live", "loading");
  let d;
  try {
    d = await ocApi("/api/v1/agents/shadow_vs_live_summary?since=24h");
  } catch (_) {
    d = null;
  }
  if (mySeq !== _pollSeq.shadowLive) return;
  if (!d) {
    setLoadingState("agent-shadow-live", "error");
    return;
  }
  // 后端契约：{ok, data:{demo, live_demo, diff}, ...} 或直接 {demo, live_demo, diff}
  const r = d.data || d;
  const demo = r.demo || {};
  const liveDemo = r.live_demo || {};
  const diff = r.diff || {};

  const demoCount = (demo.count != null) ? Number(demo.count) : 0;
  const demoPnl = demo.total_pnl_usd;
  const demoSlip = demo.avg_slippage_bps;
  const liveCount = (liveDemo.count != null) ? Number(liveDemo.count) : 0;
  const livePnl = liveDemo.total_pnl_usd;
  const liveSlip = liveDemo.avg_slippage_bps;

  if (demoCount === 0 && liveCount === 0) {
    setLoadingState("agent-shadow-live", "empty");
    return;
  }

  let html = '<div style="display:flex;flex-direction:column;gap:10px">';
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">';

  // Demo engine column (engine_mode='demo' fills) / Demo 引擎成交栏
  // Real fills to Bybit demo endpoint; uses risk_config_demo.toml.
  // 真实成交到 Bybit demo endpoint；使用 risk_config_demo.toml。
  html += '<div style="background:linear-gradient(135deg, #0d1f3d, #1a2f5c);'
    + 'border:1px solid #1a2f5c;border-radius:8px;padding:12px">';
  html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px">🟦 '
    + withTip("shadow", "Demo 引擎成交") + '</div>';
  html += '<div style="font-size:11px;color:var(--text-dim);margin-bottom:6px">'
    + 'Demo engine real fills（Bybit demo endpoint，使用 risk_config_demo.toml）</div>';
  html += '<div style="font-size:18px;font-weight:700">Demo 成交 '
    + demoCount + ' 笔</div>';
  if (demoPnl != null) {
    const cls = ocPnlClass(demoPnl);
    html += '<div class="' + cls + '" style="font-size:14px;margin-top:4px">Demo PnL '
      + ocMoney(demoPnl) + '</div>';
  }
  if (demoSlip != null) {
    html += '<div style="font-size:11px;color:var(--text-dim);margin-top:2px">'
      + '平均滑点 ' + Number(demoSlip).toFixed(2) + ' bps</div>';
  }
  html += '</div>';

  // LiveDemo engine column (engine_mode='live_demo' fills) / LiveDemo 引擎成交栏
  // Live pipeline routed to Bybit demo endpoint; uses risk_config_live.toml.
  // Live 管线走 demo endpoint；使用 risk_config_live.toml（CLAUDE.md §三 engine_mode_tag_live_demo）。
  const liveBg = liveCount > 0
    ? "background:linear-gradient(135deg, #3d0d0d, #5c1a1a);border:1px solid var(--red);"
    : "background:rgba(13,17,23,0.4);border:1px dashed var(--border);";
  html += '<div style="' + liveBg + 'border-radius:8px;padding:12px">';
  html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px">🔴 LiveDemo 引擎成交</div>';
  html += '<div style="font-size:11px;color:var(--text-dim);margin-bottom:6px">'
    + 'Live 管线走 demo endpoint（使用 risk_config_live.toml）</div>';
  if (liveCount > 0) {
    html += '<div style="font-size:18px;font-weight:700">LiveDemo 成交 '
      + liveCount + ' 笔</div>';
    if (livePnl != null) {
      const cls = ocPnlClass(livePnl);
      html += '<div class="' + cls + '" style="font-size:14px;margin-top:4px">LiveDemo PnL '
        + ocMoney(livePnl) + '</div>';
    }
    if (liveSlip != null) {
      html += '<div style="font-size:11px;color:var(--text-dim);margin-top:2px">'
        + '平均滑点 ' + Number(liveSlip).toFixed(2) + ' bps</div>';
    }
  } else {
    html += '<div style="font-size:14px;color:var(--text-dim)">— 此时段无 LiveDemo 成交 —</div>';
    html += '<div style="font-size:11px;color:var(--text-dim);margin-top:4px">'
      + '流量稀疏 / 引擎运行中（pipeline 状态请看 System tab）</div>';
  }
  html += '</div>';
  html += '</div>';  // end 2-column grid

  // Central diff row
  // Display fill_rate_delta_pct + slippage_delta_bps; ≥10% absolute → red.
  const fillDelta = diff.fill_rate_delta_pct;
  const slipDelta = diff.slippage_delta_bps;
  if (fillDelta != null || slipDelta != null) {
    const fillRed = (fillDelta != null && Math.abs(Number(fillDelta)) >= 10);
    const fillColor = fillRed ? "var(--red)" : "var(--text-dim)";
    html += '<div style="background:rgba(13,17,23,0.6);border:1px solid var(--border);'
      + 'border-radius:6px;padding:8px 12px;display:flex;justify-content:space-around;'
      + 'gap:8px;flex-wrap:wrap;font-size:12px">';
    if (fillDelta != null) {
      const sign = Number(fillDelta) >= 0 ? "+" : "";
      html += '<div>成交率差异（Demo vs LiveDemo）：<strong style="color:' + fillColor + '">'
        + sign + Number(fillDelta).toFixed(1) + '%</strong>'
        + (fillRed ? ' <span style="color:var(--red);font-size:11px">⚠ 偏离 ≥10%</span>' : '')
        + '</div>';
    }
    if (slipDelta != null) {
      const sign = Number(slipDelta) >= 0 ? "+" : "";
      html += '<div>滑点差异（Demo vs LiveDemo）：<strong style="color:var(--text)">'
        + sign + Number(slipDelta).toFixed(2) + ' bps</strong></div>';
    }
    html += '</div>';
  }

  html += '</div>';  // end column-flex container
  ocSetHtml("agent-shadow-live-data", html);
  setLoadingState("agent-shadow-live", "data");
}

// ─────────────────────────────────────────────────────────────────────────────
// Block F — Lease + Reject summary / 决策租约 + 治理拒单
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Risk-level chip color per round 2 schema (P0=bad, P1=warn, P2=info, default=neutral).
 * 风控等级映射 chip 颜色：P0 红 / P1 黄 / P2 蓝 / 其他灰。
 */
function _riskLevelChip(level) {
  if (!level) return ocChip("?", "neutral");
  const lvl = String(level).toUpperCase();
  let chip = "neutral";
  if (lvl === "P0") chip = "bad";
  else if (lvl === "P1") chip = "warn";
  else if (lvl === "P2") chip = "info";
  return ocChip(lvl, chip);
}

/**
 * Load + render active leases + recent rejects.
 * 拉 /api/v1/governance/leases + /api/v1/agents/recent_rejects；30s 刷新。
 *
 * Round 2 修复（C-1 a）：
 *   - rejects 改呼新 endpoint /api/v1/agents/recent_rejects?limit=5
 *   - schema：{rows:[{ts, symbol, reason, risk_level}, ...]}
 *   - 移除旧的 ?outcome=reject query (后端不识别 silent ignore)
 *   - 显示格式：「{ts hh:mm:ss}｜{symbol}｜被守门员擋下：{reason}（{P0/P1/P2}）」
 *
 * Round 2 fix (C-1 a):
 *   - rejects hits new endpoint /api/v1/agents/recent_rejects?limit=5
 *   - Remove unrecognized `?outcome=reject` legacy query
 *   - Format: "{hh:mm:ss}｜{symbol}｜被守门员擋下：{reason}（{P0/P1/P2}）"
 */
async function loadAgentGovernance() {
  const mySeq = ++_pollSeq.governance;
  setLoadingState("agent-governance", "loading");
  const [leasesR, rejectsR] = await Promise.allSettled([
    ocApi("/api/v1/governance/leases"),
    ocApi("/api/v1/agents/recent_rejects?limit=5"),
  ]);
  if (mySeq !== _pollSeq.governance) return;
  const leasesOk = leasesR.status === "fulfilled" && leasesR.value;
  const rejectsOk = rejectsR.status === "fulfilled" && rejectsR.value;
  if (!leasesOk && !rejectsOk) {
    setLoadingState("agent-governance", "error");
    return;
  }

  const leases = leasesOk
    ? ((leasesR.value.data && (leasesR.value.data.leases || leasesR.value.data.active))
        || leasesR.value.data || [])
    : [];
  // Round 2 contract: {data:{rows:[{ts, symbol, reason, risk_level}]}}
  const rejects = rejectsOk
    ? ((rejectsR.value.data && rejectsR.value.data.rows)
        || rejectsR.value.rows
        || [])
    : [];

  if ((!leases || !leases.length) && (!rejects || !rejects.length)) {
    setLoadingState("agent-governance", "empty");
    return;
  }

  let html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">';

  // Leases column
  html += '<div>';
  html += '<div style="font-size:12px;font-weight:600;margin-bottom:6px">📜 '
    + withTip("lease", "活跃决策租约") + '</div>';
  if (leases && leases.length) {
    html += '<div style="display:flex;flex-direction:column;gap:4px">';
    leases.slice(0, 6).forEach((l) => {
      const id = String(l.lease_id || l.id || "--").slice(0, 8);
      const sym = l.symbol || "--";
      const exp = l.expires_at || l.expiry || l.expires_ts;
      html += '<div style="font-size:11px;padding:4px 8px;background:rgba(13,17,23,0.5);'
        + 'border-radius:4px;display:flex;justify-content:space-between;gap:6px">';
      html += '<span><code>' + ocEsc(id) + '</code> · ' + ocEsc(sym) + '</span>';
      html += '<span style="color:var(--text-dim)">到期 ' + ocEsc(_agentRelTime(exp)) + '</span>';
      html += '</div>';
    });
    html += '</div>';
  } else {
    html += '<div style="font-size:11px;color:var(--text-dim);padding:8px 0">'
      + '当前没有活跃租约</div>';
  }
  html += '</div>';

  // Rejects column (round 2: real risk_verdicts.reject rows)
  html += '<div>';
  html += '<div style="font-size:12px;font-weight:600;margin-bottom:6px">🛑 '
    + withTip("governance", "守门员拒单") + '（最近 5 条）</div>';
  if (rejects && rejects.length) {
    html += '<div style="display:flex;flex-direction:column;gap:4px">';
    rejects.slice(0, 5).forEach((r) => {
      const reason = r.reason || "--";
      const ts = r.ts;
      const sym = r.symbol || "?";
      const lvl = r.risk_level;
      html += '<div style="font-size:11px;padding:4px 8px;background:rgba(248,81,73,0.06);'
        + 'border-left:2px solid var(--red);border-radius:0 4px 4px 0">';
      html += '<div style="display:flex;justify-content:space-between;gap:6px;align-items:center">';
      html += '<span><code style="color:var(--text-dim)">' + ocEsc(_agentTimeShort(ts)) + '</code>'
        + '｜<strong>' + ocEsc(sym) + '</strong></span>';
      html += _riskLevelChip(lvl);
      html += '</div>';
      html += '<div style="color:var(--text-dim);margin-top:2px">'
        + '被守门员擋下：' + ocEsc(reason) + '</div>';
      html += '</div>';
    });
    html += '</div>';
  } else {
    html += '<div style="font-size:11px;color:var(--text-dim);padding:8px 0">'
      + '近期无拒单</div>';
  }
  html += '</div>';

  html += '</div>';
  ocSetHtml("agent-governance-data", html);
  setLoadingState("agent-governance", "data");
}

// ─────────────────────────────────────────────────────────────────────────────
// Block D (MVP) — Thinking budget progress / 思考预算进度条 (简化版)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Load + render today's AI thinking budget as a simple progress bar (MVP, plan §scope).
 * 拉 /api/v1/paper/layer2/cost 渲染「今日 AI 花费 $X / $Y」进度条；120s 刷新。
 *
 * Round 2 修复（C-2）：改用真后端 nested schema：
 *   - spent     = c.today.total_usd
 *   - cap       = c.budget.daily_hard_cap_usd
 *   - remaining = c.budget.remaining_usd (展示用)
 * 移除旧 fallback chain (spent_usd / total_cost_usd / budget_usd / daily_cap_usd)。
 *
 * Round 2 fix (C-2): use real nested schema; drop flat fallback fields.
 *
 * Phase 2 will add cost_edge_ratio gradient warning — not in this MVP.
 */
async function loadAgentBudget() {
  const mySeq = ++_pollSeq.budget;
  setLoadingState("agent-budget", "loading");
  let d;
  try {
    d = await ocApi("/api/v1/paper/layer2/cost");
  } catch (_) {
    d = null;
  }
  if (mySeq !== _pollSeq.budget) return;
  if (!d) {
    setLoadingState("agent-budget", "error");
    return;
  }
  const c = d.data || d;
  // Round 2 nested schema only — fail-loud if absent
  const today = c.today || {};
  const budget = c.budget || {};
  const spent = (today.total_usd != null) ? Number(today.total_usd) : null;
  const cap = (budget.daily_hard_cap_usd != null) ? Number(budget.daily_hard_cap_usd) : null;
  const remaining = (budget.remaining_usd != null) ? Number(budget.remaining_usd) : null;

  if (spent == null && cap == null) {
    setLoadingState("agent-budget", "empty");
    return;
  }

  const spentVal = Number(spent || 0);
  const capVal = Number(cap || 0);
  const pct = capVal > 0 ? Math.min(100, (spentVal / capVal) * 100) : 0;
  let barColor = "var(--green)";
  if (pct >= 90) barColor = "var(--red)";
  else if (pct >= 70) barColor = "var(--yellow)";

  let html = '<div>';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">';
  html += '<span style="font-size:12px">' + withTip("budget", "今日思考预算") + '</span>';
  html += '<span style="font-size:13px;font-weight:600">$' + spentVal.toFixed(2)
    + ' / $' + capVal.toFixed(2) + '</span>';
  html += '</div>';
  html += '<div style="background:rgba(13,17,23,0.5);border-radius:4px;height:10px;overflow:hidden;border:1px solid #21262d">';
  html += '<div style="background:' + barColor + ';height:100%;width:' + pct.toFixed(1)
    + '%;transition:width 0.3s"></div>';
  html += '</div>';
  html += '<div style="font-size:11px;color:var(--text-dim);margin-top:4px">';
  if (capVal === 0) {
    html += '尚未设定每日预算上限';
  } else if (pct >= 90) {
    html += '⚠️ 预算告急 — Agent 即将停止主动思考（仅 fallback 决策）';
  } else if (pct >= 70) {
    html += '已用 ' + pct.toFixed(0) + '%，注意节流';
  } else {
    // Prefer backend-provided remaining; fallback to derived
    const rem = (remaining != null) ? remaining : (capVal - spentVal);
    html += '剩余 $' + Number(rem).toFixed(2) + ' 可供今日思考';
  }
  html += '</div>';
  html += '</div>';

  ocSetHtml("agent-budget-data", html);
  setLoadingState("agent-budget", "data");
}

// ─────────────────────────────────────────────────────────────────────────────
// Lifecycle / 生命周期
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Boot all agent-tracker blocks + register intervals.
 * 启动全部 5 个区块的首次加载 + 注册 setInterval；外部 init() 流程调用。
 */
function startAgentTracker() {
  // 立即加载一次 / fire once immediately
  loadAgentRoster();
  loadAgentFeed();
  loadShadowLiveDiff();
  loadAgentGovernance();
  loadAgentBudget();

  // 注册周期刷新（min 30s per plan §约束 3）
  _agentRegisterTimer("roster", loadAgentRoster, 30000);
  _agentRegisterTimer("feed", loadAgentFeed, 60000);
  _agentRegisterTimer("shadowLive", loadShadowLiveDiff, 60000);
  _agentRegisterTimer("governance", loadAgentGovernance, 30000);
  _agentRegisterTimer("budget", loadAgentBudget, 120000);
}

// iframe 切走 / unload 时清干净所有定时器
window.addEventListener("pagehide", _agentClearAllTimers);
document.addEventListener("visibilitychange", function () {
  if (document.hidden) {
    _agentClearAllTimers();
  } else {
    // 切回来时重启刷新 / re-arm on visibility regain
    startAgentTracker();
  }
});

// 货币切换时刷新展示金额相关区块
window.addEventListener("occurrencychange", function () {
  loadShadowLiveDiff();
  loadAgentBudget();
});
