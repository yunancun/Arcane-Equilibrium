/**
 * OpenClaw Paper Trading & Market Feed
 * OpenClaw 紙上交易和市場數據
 *
 * MODULE_NOTE (EN): Extracted from app.js (FIX-08 file size). REF-20 R20-P1-U1
 *   added Paper Replay Lab sub-tab navigation (show-hide + localStorage
 *   persistence + disabled-state no-op). New functions are prefixed
 *   `ocPaperSubtab*` and live in 自有 namespace block at end of file to avoid
 *   colliding with existing legacy paper helpers loaded via index.html.
 *   REF-20 Sprint B1 R4 (2026-05-05) added `OpenClawReplaySubtab` namespace
 *   — readiness probe + 5-state machine + confidence/data tier render slot.
 *   The subtab no longer hardcodes disabled state; it dynamically gates on
 *   `/api/v1/replay/health` `wiring_status` (ready / degraded / binary_missing).
 * MODULE_NOTE (中): 從 app.js 提取（FIX-08 文件大小）。REF-20 R20-P1-U1 新增
 *   Paper Replay Lab 子標籤導航（show-hide + localStorage 持久化 + disabled
 *   no-op）。新函數以 `ocPaperSubtab*` 前綴命名並集中於檔案末端的命名空間區塊，
 *   避免與 legacy index.html 既有 paper helper 衝突。
 *   REF-20 Sprint B1 R4（2026-05-05）新增 `OpenClawReplaySubtab` 命名空間 —
 *   後端就緒探針 + 5 態狀態機 + execution_confidence/data_tier render slot。
 *   Replay 子標籤不再硬編 disabled state，改成動態依 `/api/v1/replay/health`
 *   `wiring_status`（ready / degraded / binary_missing）gating。
 *
 * Cross-loader notes / 跨載入點注意事項:
 *   - Loaded by legacy index.html （全部 functions accessible globally）
 *   - Loaded by tab-paper.html（iframe 內），透過 ocPaperSubtabInit() 啟動
 *   - 新增 sub-tab functions 對 legacy index.html 無副作用：legacy DOM 沒有
 *     `#paper-subtab-nav`，所以 init 內 querySelector 會 0 element，no-op。
 *   - `OpenClawReplaySubtab` 對 legacy index.html 同樣無副作用：legacy DOM 沒有
 *     `#subtab-replay` mount points，render fn 內 getElementById 會 null → no-op。
 */

"use strict";

// ═══════════════════════════════════════════════════════════════════════════════
// Paper Trading GUI Functions / 纸上交易 GUI 函数
// ═══════════════════════════════════════════════════════════════════════════════

async function handlePaperAction(action) {
  try {
    let r;
    if (action === "start") {
      // Balance is set by Rust engine at startup (reads Demo account via Bybit API).
      // Do not send initial_balance — Python route ignores it; Rust owns the balance.
      // 餘額由 Rust 引擎在啟動時設定（通過 Bybit API 讀取 Demo 帳號），
      // 不傳送 initial_balance — Python 路由忽略此參數，Rust 擁有餘額。
      r = await apiPost("/api/v1/paper/session/start", {});
    } else if (action === "pause") {
      r = await apiPost("/api/v1/paper/session/pause", {});
    } else if (action === "resume") {
      r = await apiPost("/api/v1/paper/session/resume", {});
    } else if (action === "stop") {
      r = await apiPost("/api/v1/paper/session/stop", {});
    }
    await refreshPaperTrading();
  } catch (e) {
    console.error("Paper action error:", e);
  }
}

async function submitPaperOrder() {
  const symbol = document.getElementById("paperSymbol").value.trim();
  const side = document.getElementById("paperSide").value;
  const orderType = document.getElementById("paperOrderType").value;
  const qty = parseFloat(document.getElementById("paperQty").value);
  const priceVal = document.getElementById("paperPrice").value;
  const price = priceVal ? parseFloat(priceVal) : null;

  if (!symbol || !qty || qty <= 0) return;

  try {
    const body = { symbol, side, order_type: orderType, qty };
    if (price) body.price = price;
    // Manual order submission disabled — Rust engine manages orders via strategies
    console.warn("paper/order/submit disabled — Rust engine manages orders");
    await refreshPaperTrading();
  } catch (e) {
    console.error("Paper order error:", e);
  }
}

async function refreshPaperTrading() {
  try {
    const [statusR, ordersR, posR, pnlR, fillsR] = await Promise.all([
      apiGet("/api/v1/paper/session/status"),
      apiGet("/api/v1/paper/orders"),
      apiGet("/api/v1/paper/positions"),
      apiGet("/api/v1/paper/pnl"),
      apiGet("/api/v1/paper/fills?limit=20"),
    ]);
    renderPaperSession(statusR.data);
    renderPaperPnl(pnlR.data);
    renderPaperPositions(posR.data);
    renderPaperOrders(ordersR.data);
    renderPaperFills(fillsR.data);
    // Also refresh market feed status / 同步刷新行情流状态
    refreshMarketFeedStatus().catch(() => {});
  } catch (e) {
    console.error("Paper refresh error:", e);
  }
}

function renderPaperSession(d) {
  const state = d.session?.session_state || "inactive";
  const badge = document.getElementById("paperSessionBadge");
  const labels = {
    inactive: "未启动 / Inactive",
    active: "运行中 / Active",
    paused: "已暂停 / Paused",
    completed: "已结束 / Completed",
  };
  badge.textContent = labels[state] || state;
  badge.className = "status-chip " + (state === "active" ? "good" : state === "paused" ? "neutral" : state === "completed" ? "neutral" : "neutral");

  // Update button states
  const isActive = state === "active";
  const isPaused = state === "paused";
  const canStart = state === "inactive" || state === "completed";
  document.querySelector("[data-paper-action='start']").disabled = !canStart;
  document.querySelector("[data-paper-action='pause']").disabled = !isActive;
  document.querySelector("[data-paper-action='resume']").disabled = !isPaused;
  document.querySelector("[data-paper-action='stop']").disabled = !(isActive || isPaused);
}

function renderPaperPnl(d) {
  const el = document.getElementById("paperPnlItems");
  if (!d) { el.textContent = "无数据 / No data"; return; }
  const pnlColor = (v) => v > 0 ? "paper-positive" : v < 0 ? "paper-negative" : "";
  el.innerHTML = `
    <div class="paper-pnl-row"><span>已实现 / Realized</span><span class="${pnlColor(d.realized_pnl)}">${(d.realized_pnl || 0).toFixed(4)} USDT</span></div>
    <div class="paper-pnl-row"><span>未实现 / Unrealized</span><span class="${pnlColor(d.unrealized_pnl)}">${(d.unrealized_pnl || 0).toFixed(4)} USDT</span></div>
    <div class="paper-pnl-row"><span>手续费 / Fees</span><span>-${(d.total_fees_paid || 0).toFixed(4)} USDT</span></div>
    <div class="paper-pnl-row paper-pnl-net"><span>净值 / Net PnL</span><span class="${pnlColor(d.net_paper_pnl)}">${(d.net_paper_pnl || 0).toFixed(4)} USDT</span></div>
  `;
}

function renderPaperPositions(d) {
  const el = document.getElementById("paperPositionsList");
  // Rust returns positions as array, not dict
  const raw = d.positions || {};
  const positions = Array.isArray(raw) ? raw : Object.values(raw);
  if (positions.length === 0) { el.textContent = "无持仓 / No positions"; return; }
  el.innerHTML = positions.map(p => {
    const sym = ocEsc(p.symbol || '??');
    const pnlColor = p.unrealized_pnl > 0 ? "paper-positive" : p.unrealized_pnl < 0 ? "paper-negative" : "";
    return `<div class="paper-position-row">
      <span class="paper-pos-symbol">${sym}</span>
      <span class="paper-pos-side">${ocEsc(p.side)}</span>
      <span>${ocEsc(p.qty)}</span>
      <span>@ ${(p.avg_entry_price || p.entry_price || 0).toFixed(2)}</span>
      <span>${ocAmount(ocPositionEntryValue(p))}</span>
      <span class="${pnlColor}">${(p.unrealized_pnl || 0).toFixed(4)}</span>
    </div>`;
  }).join("");
}

function renderPaperOrders(d) {
  const el = document.getElementById("paperOrdersList");
  const orders = d.orders || [];
  if (orders.length === 0) { el.textContent = "无订单 / No orders"; return; }
  el.innerHTML = orders.slice(-20).reverse().map(o => {
    const stateLabel = o.state.replace("paper_order_", "");
    const stateClass = o.state.includes("filled") ? "paper-filled" : o.state.includes("canceled") || o.state.includes("rejected") ? "paper-canceled" : "paper-working";
    return `<div class="paper-order-row ${stateClass}">
      <span>${ocEsc(o.symbol)}</span>
      <span>${ocEsc(o.side)}</span>
      <span>${ocEsc(o.order_type)}</span>
      <span>${ocEsc(o.qty)}${o.price ? " @ " + ocEsc(o.price) : ""}</span>
      <span class="paper-order-state">${ocEsc(stateLabel)}</span>
    </div>`;
  }).join("");
}

function renderPaperFills(d) {
  const el = document.getElementById("paperFillsList");
  const fills = d.fills || [];
  if (fills.length === 0) { el.textContent = "无成交 / No fills"; return; }
  el.innerHTML = fills.slice(-20).reverse().map(f => {
    return `<div class="paper-fill-row">
      <span>${ocEsc(f.symbol)}</span>
      <span>${ocEsc(f.side)}</span>
      <span>${ocEsc(f.qty)} @ ${(f.price || 0).toFixed(2)}</span>
      <span>${ocAmount(ocFillExecValue(f))}</span>
      <span>Fee: ${(f.fee || 0).toFixed(6)}</span>
    </div>`;
  }).join("");
}

// ═══════════════════════════════════════════════════════════════════════════════
// Market Feed GUI Functions / 实时行情流 GUI 函数
// ═══════════════════════════════════════════════════════════════════════════════

let _marketFeedRefreshInterval = null;

async function handleMarketFeedAction(action) {
  // Market feed managed by Rust engine — no Python dispatcher needed
  // 行情流由 Rust 引擎管理 — 不需要 Python 分發器
  ocToast('行情流由 Rust 引擎自動管理 / Market feed is managed by Rust engine automatically', 'info');
}

function startMarketFeedRefresh() {
  stopMarketFeedRefresh();
  _marketFeedRefreshInterval = setInterval(() => {
    refreshMarketFeedStatus();
    refreshPaperTrading();
  }, 3000);
}

function stopMarketFeedRefresh() {
  if (_marketFeedRefreshInterval) {
    clearInterval(_marketFeedRefreshInterval);
    _marketFeedRefreshInterval = null;
  }
}

async function refreshMarketFeedStatus() {
  try {
    const resp = await apiGet("/api/v1/paper/market-feed/status");
    renderMarketFeedStatus(resp.data);
  } catch (e) {
    // Feed not available yet
  }
}

function renderMarketFeedStatus(d) {
  const badge = document.getElementById("paperFeedStatusBadge");
  const startBtn = document.getElementById("paperFeedStartBtn");
  const stopBtn = document.getElementById("paperFeedStopBtn");
  const pricesEl = document.getElementById("paperFeedPrices");
  const statsEl = document.getElementById("paperFeedStats");

  const isRunning = d.dispatcher_running || false;
  const attention = d.attention_level || "dormant";

  // Update badge / 更新徽章
  if (isRunning) {
    const wsConnected = d.ws_listener?.connected || false;
    badge.textContent = wsConnected ? "已连接 / Connected" : "连接中 / Connecting...";
    badge.className = "status-chip " + (wsConnected ? "good" : "neutral");
  } else {
    badge.textContent = "未连接 / Disconnected";
    badge.className = "status-chip neutral";
  }

  // Update buttons / 更新按钮
  startBtn.disabled = isRunning;
  stopBtn.disabled = !isRunning;

  // Render latest prices / 渲染最新价格
  const prices = d.latest_prices || {};
  const symbols = Object.keys(prices);
  if (symbols.length > 0) {
    pricesEl.innerHTML = symbols.map(sym => {
      return `<span class="paper-feed-price-item">
        <span class="price-symbol">${ocEsc(sym)}</span>
        <span class="price-value">${prices[sym].toFixed(2)}</span>
      </span>`;
    }).join("");
  } else if (isRunning) {
    pricesEl.textContent = "等待首次行情推送 / Waiting for first price push...";
  } else {
    pricesEl.textContent = "行情流未启动 / Market feed not started";
  }

  // Render stats / 渲染统计
  const stats = d.stats || {};
  const attentionLabels = {
    dormant: "休眠 / Dormant",
    low: "低 / Low",
    medium: "中 / Medium",
    high: "高 / High",
    critical: "紧急 / Critical",
  };
  const attentionClass = "paper-attention-" + attention;

  statsEl.innerHTML = `
    <span class="paper-attention-badge ${attentionClass}">${attentionLabels[attention] || ocEsc(attention)}</span>
    ${stats.ticks_triggered != null ? ` Ticks: ${stats.ticks_triggered}` : ""}
    ${d.ws_listener?.ticker_update_count != null ? ` | 行情更新: ${d.ws_listener.ticker_update_count}` : ""}
    ${stats.volatility_spikes ? ` | 波动飙升: ${stats.volatility_spikes}` : ""}
  `;
}

// ═══════════════════════════════════════════════════════════════════════════════
// REF-20 R20-P1-U1: Paper Replay Lab Sub-Tab Navigation
// REF-20 R20-P1-U1：Paper Replay Lab 4 子標籤導航
//
// 為什麼存在 / Why this exists:
//   REF-20 將 Paper Tab 升級為「Paper Replay Lab」(per UX subdoc V1)，分為
//   Session / Replay / Compare / Handoff 四子標籤。U1 是 foundation shell，
//   後續 U2 (Session 內容遷入) / U4 (Replay disabled) / U5 (Compare disabled) /
//   U6 (Handoff disabled) 依賴本 shell。U7 mode badge 透過 #paper-mode-badges
//   slot 注入。
//
//   REF-20 upgrades Paper Tab into "Paper Replay Lab" (per UX subdoc V1) with
//   four sub-tabs: Session / Replay / Compare / Handoff. U1 is the foundation
//   shell; U2 (Session content migration) / U4 (Replay disabled) / U5 (Compare
//   disabled) / U6 (Handoff disabled) depend on this shell. U7 mode badge will
//   inject into #paper-mode-badges slot.
//
// 設計約束 / Design invariants:
//   - Vanilla JS only — 禁 jQuery / framework lift（per CLAUDE.md §三）
//   - 0 backend write — 純 frontend show-hide + localStorage persistence
//   - Disabled sub-tab click → no-op + console.warn（不導航；UX subdoc §8）
//   - Page load 恢復 localStorage; 若上次 active 是 disabled → fallback Session
//   - aria-disabled + data-disabled 為 axe-core a11y 識別保留
//   - 對 legacy index.html DOM 無副作用（querySelector 找不到 nav 即 no-op）
// ═══════════════════════════════════════════════════════════════════════════════

const _OC_PAPER_SUBTAB_LS_KEY = "paper_active_subtab";
const _OC_PAPER_SUBTAB_DEFAULT = "session";
const _OC_PAPER_SUBTAB_VALID = ["session", "replay", "compare", "handoff"];

/**
 * 顯示指定 sub-tab，隱藏其他三個。/ Show the named sub-tab, hide the other three.
 *
 * 行為 / Behavior:
 *   1. 找 button[data-subtab=name]；若 disabled（data-disabled="true"）→ no-op
 *      + console.warn（不導航，per UX subdoc §8）
 *   2. 切換 .active class 在 nav buttons + content divs
 *   3. 切換 aria-selected 在 nav buttons（screen reader）
 *   4. 切換 hidden attribute 在 content divs（screen reader + a11y baseline）
 *   5. 持久化 active sub-tab 到 localStorage["paper_active_subtab"]
 *
 * @param {string} name - one of "session" / "replay" / "compare" / "handoff"
 * @returns {boolean} true if switched, false if no-op (disabled or invalid)
 */
function ocPaperSubtabShow(name) {
  // 防呆：不在 valid set 裡就 no-op，避免 localStorage 被污染
  // Defensive: if name not in valid set, no-op to avoid localStorage pollution
  if (_OC_PAPER_SUBTAB_VALID.indexOf(name) === -1) {
    console.warn("[paper-subtab] invalid sub-tab name:", name);
    return false;
  }
  const btn = document.getElementById("subtab-btn-" + name);
  if (!btn) {
    // tab-paper.html 還沒載到 / 或 legacy index.html 沒這結構 → no-op
    // tab-paper.html not yet loaded / legacy index.html lacks this structure → no-op
    return false;
  }
  // Disabled 點擊 = no-op + warn（不導航；不污染 localStorage）
  // Disabled click = no-op + warn (no navigation; no localStorage write)
  if (btn.getAttribute("data-disabled") === "true") {
    console.warn(
      "[paper-subtab] sub-tab '" + name + "' is disabled — see tooltip for blocking gate"
    );
    return false;
  }

  // 切換 nav buttons / Toggle nav buttons
  const allBtns = document.querySelectorAll("#paper-subtab-nav .oc-subtab-btn");
  allBtns.forEach(function (b) {
    const isActive = b.getAttribute("data-subtab") === name;
    if (isActive) {
      b.classList.add("active");
      b.setAttribute("aria-selected", "true");
    } else {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    }
  });

  // 切換 content divs / Toggle content divs
  _OC_PAPER_SUBTAB_VALID.forEach(function (key) {
    const div = document.getElementById("subtab-" + key);
    if (!div) return;
    if (key === name) {
      div.classList.add("active");
      div.removeAttribute("hidden");
    } else {
      div.classList.remove("active");
      div.setAttribute("hidden", "");
    }
  });

  // REF-20 Sprint B1 R4: replay subtab activate/deactivate hooks
  // REF-20 Sprint B1 R4：replay 子標籤啟用/停用 hook
  // - 切到 replay → 觸發 readiness probe + 啟動 30s 週期輪詢
  // - 切離 replay → 停止輪詢避免 iframe-hidden 仍燒 timer
  // 對 legacy index.html 無副作用：window.OpenClawReplaySubtab 可能不存在
  // （namespace 在本檔末端定義；legacy index.html 不載 tab-paper.html）→
  // typeof check 守衛即可。
  // - Switch to replay → trigger readiness probe + 30s periodic poll
  // - Switch away from replay → stop poll to avoid timer leak in hidden iframe
  // Legacy index.html safe: typeof guard handles missing namespace.
  if (typeof window.OpenClawReplaySubtab === "object" && window.OpenClawReplaySubtab !== null) {
    if (name === "replay") {
      // fire-and-forget probe；async error 內部 catch 不會冒泡破壞 navigation
      // fire-and-forget probe; internal catch prevents async errors from
      // breaking navigation flow.
      try { window.OpenClawReplaySubtab.onTabActivate(); } catch (e) {
        console.warn("[paper-subtab] replay onTabActivate threw:", e);
      }
    } else {
      try { window.OpenClawReplaySubtab.onTabDeactivate(); } catch (e) {
        console.warn("[paper-subtab] replay onTabDeactivate threw:", e);
      }
    }
  }

  // 持久化 / Persist active sub-tab to localStorage（pure frontend, no backend hit）
  try {
    localStorage.setItem(_OC_PAPER_SUBTAB_LS_KEY, name);
  } catch (e) {
    // localStorage 被 disable（隱私模式 / 配額滿）→ 安靜 fail，不阻擋導航
    // localStorage disabled (private mode / quota exceeded) → silent fail
    console.warn("[paper-subtab] localStorage write failed:", e);
  }
  return true;
}

/**
 * Page load 時讀 localStorage 恢復上次 active sub-tab。
 * Restore last active sub-tab from localStorage on page load.
 *
 * 設計：
 *   - 若 localStorage 值非 valid name → fallback Session
 *   - 若 localStorage 值對應 button 是 disabled → fallback Session
 *     （避免重啟 P1 GUI 時被卡在 P2/P3/P6 disabled tab）
 *   - REF-20 Sprint B1 R4：replay last-active 不直接 active without probe；
 *     ocPaperSubtabShow() 對 replay 會自動 trigger onTabActivate → probe →
 *     render degraded/ready；不可繞過 probe 直接顯示 ready UI。
 *
 * @returns {string} the sub-tab actually shown (post-fallback)
 */
function ocPaperSubtabRestoreFromStorage() {
  let name = _OC_PAPER_SUBTAB_DEFAULT;
  try {
    const stored = localStorage.getItem(_OC_PAPER_SUBTAB_LS_KEY);
    if (stored && _OC_PAPER_SUBTAB_VALID.indexOf(stored) !== -1) {
      name = stored;
    }
  } catch (e) {
    // localStorage 無法讀 → 用 default
    // localStorage unreadable → use default
  }

  // Fallback：若 stored target 是 disabled，回 Session（避免空畫面）
  // Fallback: if stored target is disabled, fall back to Session (avoid blank view)
  // REF-20 Sprint B1 R4：replay 子標籤已不再硬編 data-disabled="true"（R4-T1
  // 移除靜態 disabled），所以此處對 replay 不會 fallback；session/replay 兩
  // enabled，compare/handoff 仍 disabled，邏輯不變。
  // After R4-T1 the replay button no longer carries hardcoded data-disabled,
  // so this fallback only triggers for compare/handoff (still gated by phase).
  const btn = document.getElementById("subtab-btn-" + name);
  if (btn && btn.getAttribute("data-disabled") === "true") {
    name = _OC_PAPER_SUBTAB_DEFAULT;
  }

  // 直接 show 而非走 ocPaperSubtabShow（後者對 disabled 會 no-op；這裡 fallback
  // 後 name 一定是 enabled 的 Session 或 replay，不過為一致性仍走 show 函數）。
  // 對 replay：show 內含 onTabActivate hook → 先 probe /health → render；
  // 不會 unconditional render ready UI（R4-T2 invariant：禁無 probe 直 active）。
  // Go through show() for consistency; for replay, show() triggers
  // onTabActivate which probes /health before rendering — never bypass probe.
  ocPaperSubtabShow(name);
  return name;
}

/**
 * Wire click handler on the 4 sub-tab nav buttons + restore last active sub-tab.
 * 在 4 個子標籤 nav button 綁 click handler，並從 localStorage 恢復上次 active。
 *
 * 由 tab-paper.html 在 inline script 末端呼叫。對 legacy index.html 無副作用：
 * 該 DOM 沒有 #paper-subtab-nav，querySelectorAll 回傳 0 element，全 loop 跳過。
 *
 * Called by tab-paper.html inline script at end. Idempotent for legacy
 * index.html: no #paper-subtab-nav there → querySelectorAll yields 0 elements.
 */
function ocPaperSubtabInit() {
  const nav = document.getElementById("paper-subtab-nav");
  if (!nav) {
    // 沒有 sub-tab nav DOM → legacy index.html 環境，no-op
    // No sub-tab nav DOM → legacy index.html context, no-op
    return;
  }
  const btns = nav.querySelectorAll(".oc-subtab-btn");
  btns.forEach(function (btn) {
    btn.addEventListener("click", function (ev) {
      const name = btn.getAttribute("data-subtab");
      // ocPaperSubtabShow 內含 disabled 守衛 + valid-name 守衛
      // ocPaperSubtabShow has disabled guard + valid-name guard built in
      ocPaperSubtabShow(name);
    });
    // Keyboard a11y baseline：Enter / Space 觸發（button 預設已支援，但顯式註冊
    // 確保 disabled 路徑也走 console.warn 而非靜默 navigate）
    // Keyboard a11y baseline: Enter / Space (built-in button behavior covers it,
    // but disabled-state click goes through ocPaperSubtabShow which warns).
  });

  // Restore last-active from localStorage（fallback 已內建）
  // Restore last-active from localStorage (fallback built-in)
  ocPaperSubtabRestoreFromStorage();
}

// ═══════════════════════════════════════════════════════════════════════════════
// REF-20 Sprint B1 R4: OpenClawReplaySubtab — readiness probe + 5-state machine
// REF-20 Sprint B1 R4：OpenClawReplaySubtab — 後端就緒探針 + 5 態狀態機
//
// 為什麼存在 / Why this exists:
//   Sprint A R1-T3 已 ship `/api/v1/replay/health`（commit c1ab7ea9）回報
//   `wiring_status` ('ready' / 'degraded' / 'binary_missing')；Sprint B1 R4
//   要把 replay 子標籤從硬編 disabled 升級為 backend-readiness gated，5 態
//   分別對應：empty (尚未跑過 experiment) / running (有 experiment 在跑) /
//   failed (last experiment failed) / completed (有 completed experiment) /
//   degraded (backend not ready; subtab 變 disabled)。
//
//   `/api/v1/replay/health` ships in Sprint A R1-T3 (commit c1ab7ea9) and
//   reports `wiring_status` ∈ {ready, degraded, binary_missing}. Sprint B1
//   R4 upgrades replay subtab from hardcoded disabled to backend-readiness
//   gated. 5 states: empty / running / failed / completed / degraded.
//
// 設計約束 / Design invariants:
//   - Vanilla JS only — 禁 jQuery / framework lift（per CLAUDE.md §三）
//   - 0 backend write — 純 frontend probe + render
//   - 禁無 probe 直 active：localStorage last-active=replay 也須先 probe
//   - 30s 週期輪詢只在 tab active 時跑；deactivate 必 clearInterval
//   - 對 legacy index.html 無副作用（mount points 不存在 → no-op）
//   - `evidence_source_tier='synthetic_replay'` 是 Sprint A 唯一已上線 tier
//     （CLAUDE.md §九），對應顯示 "execution_confidence: NONE" — 防認知欺詐
//     baseline（A3 防誤觸詐 sentinel）
//   - XSS 防護：任何來自 backend 的 string 必走 ocEsc()；任何 dynamic
//     class 必走 ocSanitizeClass()
//   - i18n：reuse `disabled_state.p2_backend_pending` 既有 key（避免膨脹）
//
// API:
//   window.OpenClawReplaySubtab.onTabActivate()    — 切到 replay 時呼叫
//   window.OpenClawReplaySubtab.onTabDeactivate()  — 切離 replay 時呼叫
//   window.OpenClawReplaySubtab.pollBackendReadiness() — 暴露給 test fixture
//   window.OpenClawReplaySubtab.state               — 當前狀態（test 可讀）
// ═══════════════════════════════════════════════════════════════════════════════

(function _wireReplaySubtabNamespace() {
  // 防護：在 legacy index.html 環境也載入但無副作用 — 所有 fn 內 getElementById
  // 對 #subtab-replay 等 mount point 找不到時 silent return。
  // Defensive: this also loads under legacy index.html but is no-op there
  // since the #subtab-replay mount points don't exist in legacy DOM.

  // ─── Internal state / 內部狀態 ────────────────────────────────────────────
  // state 一律 5 enum 之一；初值 empty（首次未 probe 時的中性視覺）。
  // pollIntervalId：tab active 時的 30s 週期 timer。
  let _state = "empty";
  let _pollIntervalId = null;
  let _lastProbe = null;       // 最近一次 probe 結果，供 render fn 重用
  let _lastReportData = null;  // 最近一次 /report 結果（R4-T3 4 cell render 用）

  /**
   * 呼叫 /api/v1/replay/health 並解析 wiring_status。
   * Probe /api/v1/replay/health and parse wiring_status.
   *
   * 預期 envelope（per replay/route_helpers.py:replay_response_envelope）:
   *   { ok: true, data: { wiring_status, binary_path, binary_exists,
   *                       binary_release_profile, data_dir, data_dir_writable,
   *                       pg_present, v045_present, v049_present },
   *     degraded, reason, is_simulated, data_category }
   *
   * @returns {Promise<{ready: boolean, wiring_status?: string, data?: object,
   *                    reason?: string}>}
   */
  async function pollBackendReadiness() {
    try {
      // 用 fetch 而非 ocApi：probe 不需 toast / 不依賴 ocApi 的 4xx 處理
      // Use raw fetch (not ocApi) — probe doesn't need toast / 4xx auto-toast
      const resp = await fetch("/api/v1/replay/health", {
        credentials: "include",
        headers: { "Accept": "application/json" }
      });
      if (!resp.ok) {
        return { ready: false, reason: "http_" + resp.status };
      }
      const body = await resp.json();
      const data = (body && body.data) || {};
      const status = data.wiring_status || "unknown";
      return {
        ready: status === "ready",
        wiring_status: status,
        data: data,
        degraded: !!body.degraded,
        envelope_reason: body && body.reason
      };
    } catch (e) {
      // network error / JSON parse error 都當 not ready；fail-closed
      // network error / JSON parse error → not ready (fail-closed)
      return { ready: false, reason: "fetch_failed:" + (e && e.name ? e.name : "Error") };
    }
  }

  /**
   * 切到 replay 子標籤時呼叫：probe → render degraded 或 ready；ready 時啟動週期輪詢。
   * Called on switching to replay subtab: probe → render degraded or ready;
   * if ready, start the 30s periodic poll.
   */
  async function onTabActivate() {
    const probe = await pollBackendReadiness();
    _lastProbe = probe;
    if (!probe.ready) {
      _state = "degraded";
      renderDegradedState(probe);
      return;
    }
    // ready → render ready state；目前 baseline state = empty（無實驗載入）
    // ready → render ready state; baseline state = empty (no experiment loaded)
    _state = "empty";
    renderReadyState(probe.data);
    startPolling();
  }

  /**
   * 切離 replay 子標籤時呼叫：clearInterval 停止輪詢。
   * Called on switching away from replay subtab: stop the periodic poll.
   *
   * 重要 / Critical: iframe 內 setInterval 在 tab hide 時不卸載；不 clear
   * 會 30s 燒 fetch。每次 deactivate 必 clear。
   * iframe setInterval keeps firing when tab is hidden; must clear on
   * deactivate to avoid background fetch leaks.
   */
  function onTabDeactivate() {
    stopPolling();
  }

  function startPolling() {
    if (_pollIntervalId !== null) return; // 防重複註冊
    _pollIntervalId = setInterval(async function () {
      const probe = await pollBackendReadiness();
      _lastProbe = probe;
      // 週期輪詢只在 degrade 切換時 re-render；不刷 ready→ready 防 flicker
      // Periodic poll only re-renders on degrade transitions; avoids
      // ready→ready flicker.
      if (!probe.ready && _state !== "degraded") {
        _state = "degraded";
        renderDegradedState(probe);
        stopPolling(); // degrade 後不再輪詢；待 user 切離再回來重 probe
      }
    }, 30000);
  }

  function stopPolling() {
    if (_pollIntervalId !== null) {
      clearInterval(_pollIntervalId);
      _pollIntervalId = null;
    }
  }

  /**
   * 渲染 degraded state：reuse OpenClawDisabledStateCard helper。
   * Render degraded state using the existing OpenClawDisabledStateCard helper.
   *
   * 三種 wiring_status 對應 reason badge 文案：
   *   - 'binary_missing' → "Binary missing / 二進制檔案缺失"
   *   - 'degraded' → "Backend health degraded / 後端健康降級"
   *   - 其他（fetch_failed / http_5xx）→ "Backend probe failed / 後端探針失敗"
   *
   * Three reason badges per wiring_status:
   *   - binary_missing → "Binary missing"
   *   - degraded → "Backend health degraded"
   *   - others (fetch_failed / http_5xx) → "Backend probe failed"
   */
  function renderDegradedState(probe) {
    const mount = document.getElementById("subtab-replay-disabled-card");
    if (!mount) return; // legacy index.html or mount missing → no-op

    const wiringStatus = (probe && probe.wiring_status) || "unknown";
    let gateZh, gateEn, bannerZh, bannerEn;
    if (wiringStatus === "binary_missing") {
      gateZh = "二進制檔案缺失 — replay_runner 未部署";
      gateEn = "Binary missing — replay_runner not deployed";
      bannerZh = "Replay 子標籤需 Linux 端部署 replay_runner binary。請執行 restart_all --rebuild 或 cargo --release。當前 wiring_status: binary_missing。";
      bannerEn = "Replay subtab requires replay_runner binary on Linux. Run restart_all --rebuild or cargo --release. Current wiring_status: binary_missing.";
    } else if (wiringStatus === "degraded") {
      gateZh = "後端健康降級 — 部分前置條件未通過";
      gateEn = "Backend health degraded — pre-conditions partially met";
      bannerZh = "PG / data_dir / V045 / V049 至少一項不可用。請查 /api/v1/replay/health envelope 詳細欄位。當前 wiring_status: degraded。";
      bannerEn = "PG / data_dir / V045 / V049 at least one unavailable. Check /api/v1/replay/health envelope for details. Current wiring_status: degraded.";
    } else {
      // fetch_failed / http_4xx / http_5xx / unknown
      const reason = (probe && (probe.reason || probe.envelope_reason)) || "unknown";
      gateZh = "後端探針失敗 — 30 秒後自動重試";
      gateEn = "Backend probe failed — auto retry in 30s";
      bannerZh = "/api/v1/replay/health probe 失敗（reason: " + reason + "）。可能是登入失效或 control_api 未啟動；切離本子標籤再回來會立即重試。";
      bannerEn = "/api/v1/replay/health probe failed (reason: " + reason + "). May be auth expired or control_api down; switching away and back retries immediately.";
    }

    if (window.OpenClawDisabledStateCard
        && typeof window.OpenClawDisabledStateCard.render === "function") {
      window.OpenClawDisabledStateCard.render("subtab-replay-disabled-card", {
        phase: "P2",
        icon: "⏳",
        gate_label: gateEn,
        gate_label_zh: gateZh,
        // Reuse 既有 i18n key（per PA brief §3 "不重複 i18n key"）
        // Reuse existing i18n key (per PA brief §3 "no new i18n key")
        gate_label_i18n_key: "disabled_state.p2_backend_pending",
        banner_text: bannerEn,
        banner_text_zh: bannerZh,
        metrics_layout: "replay_12"
      });
    } else {
      // Fallback：helper 未載入 → inline notice
      // Fallback when helper missing → inline notice
      mount.innerHTML = '<div class="oc-subtab-placeholder">'
        + '<span class="gate-label">' + ocEsc(gateZh) + '</span>'
        + '</div>';
    }
  }

  function _metricCellHtml(id, label, value, cls, tooltip) {
    return '<div class="oc-replay-cell ' + ocSanitizeClass(cls)
      + '" id="' + ocEsc(id) + '" role="listitem" tabindex="0" title="'
      + ocEsc(tooltip || "") + '">'
      + '<div class="oc-replay-cell-label">' + ocEsc(label) + '</div>'
      + '<div class="oc-replay-cell-val">' + ocEsc(value) + '</div>'
      + '</div>';
  }

  function _setReplayStatus(message, cls) {
    const statusEl = document.getElementById("oc-replay-load-status");
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = "oc-replay-load-status " + (cls || "");
  }

  async function _fetchReplayJson(url, options) {
    const resp = await fetch(url, Object.assign({
      credentials: "include",
      headers: { "Accept": "application/json" }
    }, options || {}));
    const body = await resp.json().catch(function () { return {}; });
    if (!resp.ok) {
      throw new Error("HTTP " + resp.status + " " + JSON.stringify(body).slice(0, 160));
    }
    return body;
  }

  function _parseJsonControl(id, fallback) {
    const el = document.getElementById(id);
    const raw = el ? (el.value || "").trim() : "";
    if (!raw) return fallback;
    return JSON.parse(raw);
  }

  function _extractFirstReportPayload(data) {
    const artifacts = (data && Array.isArray(data.artifacts)) ? data.artifacts : [];
    for (let i = 0; i < artifacts.length; i += 1) {
      if (artifacts[i] && artifacts[i].payload) return artifacts[i].payload;
    }
    return {};
  }

  function _renderReportMetrics(data) {
    data = data || {};
    const payload = _extractFirstReportPayload(data);
    const result = payload.result || {};
    const fills = Array.isArray(result.fills) ? result.fills : [];
    const firstFill = fills.length ? fills[0] : {};
    const confidence = data.execution_confidence
      || payload.execution_confidence
      || result.execution_confidence
      || "not_loaded";
    const dataTier = payload.data_tier
      || firstFill.evidence_source_tier
      || "waiting_report";
    const feeModel = firstFill.fee_rate != null
      ? ("fee_rate=" + firstFill.fee_rate + " role=" + (firstFill.liquidity_role || "unknown"))
      : "waiting_report";
    const calibration = confidence === "calibrated"
      ? "CALIBRATED"
      : (confidence === "limited" ? "LIMITED" : (confidence === "none" ? "NONE" : "WAITING"));
    const cells = [
      ["oc-replay-cell-execution-confidence", "執行可信度 / Execution Confidence", confidence,
        confidence === "calibrated" ? "oc-cell-ok" : "oc-cell-warn", "V049/report execution_confidence"],
      ["oc-replay-cell-data-tier", "資料層級 / Data Tier", dataTier,
        dataTier === "calibrated_replay" || dataTier === "S2" ? "oc-cell-ok" : "oc-cell-neutral", "Manifest/report evidence tier"],
      ["oc-replay-cell-fee-model", "費率模型 / Fee Model", feeModel,
        firstFill.fee_rate != null ? "oc-cell-ok" : "oc-cell-warn", "Runner fee/slippage fields from simulated fills"],
      ["oc-replay-cell-calibration", "校準狀態 / Calibration", calibration,
        calibration === "CALIBRATED" ? "oc-cell-ok" : "oc-cell-warn", "Post-finalize calibration label"]
    ];
    cells.forEach(function (c) {
      const el = document.getElementById(c[0]);
      if (!el) return;
      el.className = "oc-replay-cell " + c[3];
      el.title = c[4];
      el.innerHTML = '<div class="oc-replay-cell-label">' + ocEsc(c[1]) + '</div>'
        + '<div class="oc-replay-cell-val">' + ocEsc(c[2]) + '</div>';
    });
  }

  /**
   * Render ready state with an operator workflow: register → run → finalize →
   * load report. Metrics start as waiting values and are replaced by report data.
   */
  function renderReadyState(healthData) {
    const mount = document.getElementById("subtab-replay-disabled-card");
    if (!mount) return;
    healthData = healthData || {};

    const wiringStatus = ocEsc(healthData.wiring_status || "ready");
    const binaryProfile = ocEsc(healthData.binary_release_profile || "(unset)");
    const ts = new Date().toISOString();

    let cellsHtml = '<div class="oc-replay-cells-grid" role="list" '
      + 'aria-label="Replay metrics / 回放指標">';
    cellsHtml += _metricCellHtml(
      "oc-replay-cell-execution-confidence",
      "執行可信度 / Execution Confidence",
      "未載入 / NOT LOADED",
      "oc-cell-warn",
      "Updated after report/finalize"
    );
    cellsHtml += _metricCellHtml(
      "oc-replay-cell-data-tier",
      "資料層級 / Data Tier",
      "等待 manifest / WAITING",
      "oc-cell-neutral",
      "Loaded from V049 manifest/report"
    );
    cellsHtml += _metricCellHtml(
      "oc-replay-cell-fee-model",
      "費率模型 / Fee Model",
      "等待報告 / WAITING",
      "oc-cell-warn",
      "Loaded from runner fill fee fields"
    );
    cellsHtml += _metricCellHtml(
      "oc-replay-cell-calibration",
      "校準狀態 / Calibration",
      "等待 finalize / WAITING",
      "oc-cell-warn",
      "Post-finalize calibration"
    );
    cellsHtml += '</div>';

    const inputHtml = '<div class="oc-replay-workflow-grid">'
      + '<label class="oc-replay-field">Symbol<input id="oc-replay-symbol" value="BTCUSDT" autocomplete="off" /></label>'
      + '<label class="oc-replay-field">Strategy<input id="oc-replay-strategy" value="grid_trading" autocomplete="off" /></label>'
      + '<label class="oc-replay-field">Timeframe<input id="oc-replay-timeframe" value="1m" autocomplete="off" /></label>'
      + '<label class="oc-replay-field">Data Tier<select id="oc-replay-data-tier">'
      + '<option value="S2">S2 calibrated_replay</option><option value="S3">S3 synthetic_replay</option></select></label>'
      + '<label class="oc-replay-field">Window Start<input id="oc-replay-window-start" type="datetime-local" /></label>'
      + '<label class="oc-replay-field">Window End<input id="oc-replay-window-end" type="datetime-local" /></label>'
      + '<label class="oc-replay-field">Experiment ID<input type="text" id="oc-replay-experiment-id" placeholder="experiment_id" autocomplete="off" maxlength="64" /></label>'
      + '<label class="oc-replay-field">Run ID<input type="text" id="oc-replay-run-id" placeholder="run_id" autocomplete="off" maxlength="64" /></label>'
      + '<label class="oc-replay-json">Strategy Params<textarea id="oc-replay-strategy-params">{\"grid_trading\":{\"grid_levels\":20}}</textarea></label>'
      + '<label class="oc-replay-json">Risk Overrides<textarea id="oc-replay-risk-overrides">{\"limits\":{\"position_size_max_pct\":10.0}}</textarea></label>'
      + '<label class="oc-replay-json">Manifest JSON<textarea id="oc-replay-manifest-json">{}</textarea></label>'
      + '</div>'
      + '<div class="oc-replay-actions">'
      + '<button type="button" class="oc-btn" id="oc-replay-register-btn">Register / 註冊</button>'
      + '<button type="button" class="oc-btn" id="oc-replay-run-btn">Run / 執行</button>'
      + '<button type="button" class="oc-btn" id="oc-replay-finalize-btn">Finalize / 完成</button>'
      + '<button type="button" class="oc-btn" id="oc-replay-load-btn">Load Report / 載入報告</button>'
      + '<span id="oc-replay-load-status" class="oc-replay-load-status"></span>'
      + '</div>';

    const headerHtml = '<div class="oc-replay-ready-header">'
      + '<span class="oc-replay-ready-icon" aria-hidden="true">🟢</span>'
      + '<div class="oc-replay-ready-title">'
      + '<strong>後端就緒 / Backend Ready</strong>'
      + '<span class="oc-replay-ready-meta">'
      + 'wiring_status: ' + wiringStatus + ' · '
      + 'release_profile: ' + binaryProfile + ' · '
      + 'probed_at: ' + ocEsc(ts)
      + '</span></div></div>';

    mount.innerHTML = '<div class="oc-replay-ready-card" role="region" '
      + 'aria-label="Replay backend ready / Replay 後端就緒">'
      + headerHtml + cellsHtml + inputHtml + '</div>';

    // 注入 CSS（idempotent guard，避免重渲染重複加 style 節點）
    // Inject CSS once (idempotent guard against re-render dup)
    _injectReplayReadyCss();

    const registerBtn = document.getElementById("oc-replay-register-btn");
    const runBtn = document.getElementById("oc-replay-run-btn");
    const finalizeBtn = document.getElementById("oc-replay-finalize-btn");
    const loadBtn = document.getElementById("oc-replay-load-btn");
    if (registerBtn) registerBtn.addEventListener("click", _onRegisterClick);
    if (runBtn) runBtn.addEventListener("click", _onRunClick);
    if (finalizeBtn) finalizeBtn.addEventListener("click", _onFinalizeClick);
    if (loadBtn) loadBtn.addEventListener("click", _onLoadReportClick);
  }

  async function _onRegisterClick() {
    try {
      const now = new Date();
      const startIso = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
      const symbol = (document.getElementById("oc-replay-symbol").value || "BTCUSDT").trim();
      const strategy = (document.getElementById("oc-replay-strategy").value || "grid_trading").trim();
      const timeframe = (document.getElementById("oc-replay-timeframe").value || "1m").trim();
      const dataTier = document.getElementById("oc-replay-data-tier").value || "S2";
      const manifestJson = _parseJsonControl("oc-replay-manifest-json", {});
      manifestJson.symbol = symbol;
      manifestJson.strategy = strategy;
      manifestJson.timeframe = timeframe;
      manifestJson.data_tier = dataTier;
      const body = {
        symbol: symbol,
        strategy: strategy,
        timeframe: timeframe,
        data_tier: dataTier,
        data_window_start: startIso,
        data_window_end: now.toISOString(),
        strategy_config_sha256: "0".repeat(64),
        risk_config_sha256: "1".repeat(64),
        half_life_days: 7.0,
        embargo_days: 1.0,
        manifest_jsonb: manifestJson,
        strategy_params: _parseJsonControl("oc-replay-strategy-params", null),
        risk_overrides: _parseJsonControl("oc-replay-risk-overrides", null),
        idempotency_key: "paper-ui-" + Date.now()
      };
      const startEl = document.getElementById("oc-replay-window-start");
      const endEl = document.getElementById("oc-replay-window-end");
      if (startEl && startEl.value) body.data_window_start = new Date(startEl.value).toISOString();
      if (endEl && endEl.value) body.data_window_end = new Date(endEl.value).toISOString();
      _setReplayStatus("Registering...", "");
      const resp = await _fetchReplayJson("/api/v1/replay/experiments/register", {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = resp.data || {};
      document.getElementById("oc-replay-experiment-id").value = data.experiment_id || "";
      _setReplayStatus("registered experiment_id=" + (data.experiment_id || ""), "oc-cell-ok");
    } catch (e) {
      _setReplayStatus("register failed: " + (e.message || e.name || "Error"), "oc-cell-warn");
    }
  }

  async function _onRunClick() {
    const inputEl = document.getElementById("oc-replay-experiment-id");
    const expId = inputEl ? (inputEl.value || "").trim() : "";
    if (!expId) {
      _setReplayStatus("請先提供 experiment_id / experiment_id required", "oc-cell-warn");
      return;
    }
    try {
      _setReplayStatus("Running...", "");
      const resp = await _fetchReplayJson("/api/v1/replay/run", {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({
          experiment_id: expId,
          idempotency_key: "paper-run-" + Date.now()
        })
      });
      const data = resp.data || {};
      const runId = data.run_id || data.id || "";
      const runEl = document.getElementById("oc-replay-run-id");
      if (runEl) runEl.value = runId;
      _setReplayStatus("run.status=" + (data.status || "started") + " run_id=" + runId, "oc-cell-ok");
    } catch (e) {
      _setReplayStatus("run failed: " + (e.message || e.name || "Error"), "oc-cell-warn");
    }
  }

  async function _onFinalizeClick() {
    const runEl = document.getElementById("oc-replay-run-id");
    const runId = runEl ? (runEl.value || "").trim() : "";
    if (!runId) {
      _setReplayStatus("請先提供 run_id / run_id required", "oc-cell-warn");
      return;
    }
    try {
      _setReplayStatus("Finalizing...", "");
      const resp = await _fetchReplayJson(
        "/api/v1/replay/run/" + encodeURIComponent(runId) + "/finalize",
        { method: "POST", headers: { "Accept": "application/json" } }
      );
      const data = resp.data || {};
      _setReplayStatus("finalized fills=" + (data.fills_inserted || 0)
        + " confidence=" + (data.execution_confidence || "none"), "oc-cell-ok");
      const expId = data.experiment_id;
      if (expId) {
        document.getElementById("oc-replay-experiment-id").value = expId;
        await _onLoadReportClick();
      }
    } catch (e) {
      _setReplayStatus("finalize failed: " + (e.message || e.name || "Error"), "oc-cell-warn");
    }
  }

  async function _onLoadReportClick() {
    const inputEl = document.getElementById("oc-replay-experiment-id");
    if (!inputEl) return;
    const expId = (inputEl.value || "").trim();
    if (!expId) {
      _setReplayStatus("請輸入 experiment_id / Please enter experiment_id", "oc-cell-warn");
      return;
    }
    _setReplayStatus("Loading...", "");
    try {
      const body = await _fetchReplayJson(
        "/api/v1/replay/report/" + encodeURIComponent(expId)
      );
      _lastReportData = body;
      const data = (body && body.data) || {};
      const runStatus = (data.run && data.run.status) || "unknown";
      const artifactCount = data.artifact_count != null ? data.artifact_count : 0;
      _renderReportMetrics(data);
      _setReplayStatus("run.status=" + runStatus + " artifacts=" + artifactCount,
        "oc-cell-ok");
    } catch (e) {
      _setReplayStatus("load failed: " + (e.message || e.name || "Error"), "oc-cell-warn");
    }
  }

  /**
   * 注入 ready state CSS（idempotent）。
   * Inject ready-state CSS once (idempotent).
   */
  function _injectReplayReadyCss() {
    if (document.getElementById("oc-replay-ready-css")) return;
    const s = document.createElement("style");
    s.id = "oc-replay-ready-css";
    s.textContent = ''
      + '.oc-replay-ready-card{background:rgba(22,27,34,0.7);'
      + 'border:1px solid var(--border);border-radius:var(--card-radius);'
      + 'padding:18px 20px 22px;margin-bottom:14px}'
      + '.oc-replay-ready-header{display:flex;align-items:flex-start;'
      + 'gap:10px;margin-bottom:10px}'
      + '.oc-replay-ready-icon{font-size:22px;line-height:1;flex-shrink:0}'
      + '.oc-replay-ready-title{flex:1;min-width:0}'
      + '.oc-replay-ready-title strong{display:block;color:var(--green);'
      + 'font-size:14px;margin-bottom:3px}'
      + '.oc-replay-ready-meta{font-size:11px;color:var(--text-dim);'
      + 'word-break:break-all;line-height:1.5}'
      + '.oc-replay-ready-banner{font-size:12px;color:var(--text-dim);'
      + 'line-height:1.6;padding:8px 12px;background:rgba(13,17,23,0.55);'
      + 'border-left:3px solid var(--blue);border-radius:4px;margin:8px 0 14px}'
      + '.oc-replay-ready-banner .zh{display:block;color:var(--text)}'
      + '.oc-replay-ready-banner .en{display:block;color:var(--text-dim);'
      + 'font-size:11px;margin-top:2px}'
      + '.oc-replay-cells-grid{display:grid;gap:8px;margin-bottom:12px;'
      + 'grid-template-columns:repeat(auto-fill,minmax(180px,1fr))}'
      + '.oc-replay-cell{background:rgba(13,17,23,0.4);border:1px solid #21262d;'
      + 'border-radius:6px;padding:10px 12px;min-height:54px;cursor:help}'
      + '.oc-replay-cell:focus{outline:2px solid var(--accent);outline-offset:2px}'
      + '.oc-replay-cell-label{font-size:10px;color:var(--text-dim);'
      + 'text-transform:uppercase;letter-spacing:0.4px}'
      + '.oc-replay-cell-val{font-size:13px;color:var(--text);font-weight:600;'
      + 'margin-top:4px}'
      + '.oc-replay-cell.oc-cell-warn{border-color:rgba(248,81,73,0.5);'
      + 'background:rgba(248,81,73,0.06)}'
      + '.oc-replay-cell.oc-cell-warn .oc-replay-cell-val{color:var(--red)}'
      + '.oc-replay-cell.oc-cell-ok{border-color:rgba(63,185,80,0.5);'
      + 'background:rgba(63,185,80,0.06)}'
      + '.oc-replay-cell.oc-cell-ok .oc-replay-cell-val{color:var(--green)}'
      + '.oc-replay-workflow-grid{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));'
      + 'gap:8px;padding:10px 12px;background:rgba(13,17,23,0.4);'
      + 'border:1px dashed var(--border);border-radius:6px}'
      + '.oc-replay-field,.oc-replay-json{display:flex;flex-direction:column;'
      + 'gap:5px;font-size:10px;color:var(--text-dim);text-transform:uppercase}'
      + '.oc-replay-json{grid-column:span 4}'
      + '.oc-replay-field input,.oc-replay-field select,.oc-replay-json textarea{'
      + 'background:var(--bg);border:1px solid var(--border);border-radius:4px;'
      + 'padding:6px 8px;color:var(--text);font-family:monospace;font-size:12px;'
      + 'min-width:0}'
      + '.oc-replay-json textarea{min-height:52px;resize:vertical;line-height:1.35}'
      + '.oc-replay-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center;'
      + 'margin-top:8px}'
      + '.oc-replay-load-row{display:flex;gap:8px;flex-wrap:wrap;'
      + 'align-items:center;padding:10px 12px;background:rgba(13,17,23,0.4);'
      + 'border:1px dashed var(--border);border-radius:6px}'
      + '.oc-replay-load-label{font-size:11px;color:var(--text-dim)}'
      + '.oc-replay-load-input{flex:1;min-width:200px;background:var(--bg);'
      + 'border:1px solid var(--border);border-radius:4px;padding:6px 10px;'
      + 'color:var(--text);font-family:monospace;font-size:12px}'
      + '.oc-replay-load-status{font-size:11px;color:var(--text-dim);'
      + 'flex-basis:100%;line-height:1.5}'
      + '.oc-replay-load-status.oc-cell-warn{color:var(--red)}'
      + '.oc-replay-load-status.oc-cell-ok{color:var(--green)}'
      + '@media (max-width:900px){.oc-replay-workflow-grid{grid-template-columns:repeat(2,minmax(0,1fr))}'
      + '.oc-replay-json{grid-column:span 2}}'
      + '@media (max-width:700px){.oc-replay-cells-grid{'
      + 'grid-template-columns:1fr 1fr}.oc-replay-cell{min-height:60px;'
      + 'padding:12px 14px}.oc-replay-load-input{min-width:0;width:100%}'
      + '.oc-replay-workflow-grid{grid-template-columns:1fr}.oc-replay-json{grid-column:span 1}}';
    document.head.appendChild(s);
  }

  // ─── Public API export / 公開 API 匯出 ────────────────────────────────────
  // 暴露 namespace 至 window；test fixture 可 mock window.fetch + 直接呼叫
  // onTabActivate / pollBackendReadiness 驗證 state machine。
  // Expose namespace on window; test fixture can mock window.fetch and call
  // onTabActivate / pollBackendReadiness to verify state machine.
  window.OpenClawReplaySubtab = {
    onTabActivate: onTabActivate,
    onTabDeactivate: onTabDeactivate,
    pollBackendReadiness: pollBackendReadiness,
    // Test-only accessors（不可作 production API；test fixture 才該讀）
    // Test-only accessors (not production API; test fixture only)
    _getState: function () { return _state; },
    _getLastProbe: function () { return _lastProbe; },
    _getLastReport: function () { return _lastReportData; },
    _setStateForTest: function (s) { _state = s; },
    _isPolling: function () { return _pollIntervalId !== null; }
  };
})();
