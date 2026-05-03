/**
 * OpenClaw Paper Trading & Market Feed
 * OpenClaw 紙上交易和市場數據
 *
 * MODULE_NOTE (EN): Extracted from app.js (FIX-08 file size). REF-20 R20-P1-U1
 *   added Paper Replay Lab sub-tab navigation (show-hide + localStorage
 *   persistence + disabled-state no-op). New functions are prefixed
 *   `ocPaperSubtab*` and live in 自有 namespace block at end of file to avoid
 *   colliding with existing legacy paper helpers loaded via index.html.
 * MODULE_NOTE (中): 從 app.js 提取（FIX-08 文件大小）。REF-20 R20-P1-U1 新增
 *   Paper Replay Lab 子標籤導航（show-hide + localStorage 持久化 + disabled
 *   no-op）。新函數以 `ocPaperSubtab*` 前綴命名並集中於檔案末端的命名空間區塊，
 *   避免與 legacy index.html 既有 paper helper 衝突。
 *
 * Cross-loader notes / 跨載入點注意事項:
 *   - Loaded by legacy index.html （全部 functions accessible globally）
 *   - Loaded by tab-paper.html（iframe 內），透過 ocPaperSubtabInit() 啟動
 *   - 新增 sub-tab functions 對 legacy index.html 無副作用：legacy DOM 沒有
 *     `#paper-subtab-nav`，所以 init 內 querySelector 會 0 element，no-op。
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
  const btn = document.getElementById("subtab-btn-" + name);
  if (btn && btn.getAttribute("data-disabled") === "true") {
    name = _OC_PAPER_SUBTAB_DEFAULT;
  }

  // 直接 show 而非走 ocPaperSubtabShow（後者對 disabled 會 no-op；這裡 fallback
  // 後 name 一定是 enabled 的 Session，不過為一致性仍走 show 函數）
  // Go through show() for consistency; post-fallback name is guaranteed enabled.
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
