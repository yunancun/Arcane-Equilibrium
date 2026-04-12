/**
 * OpenClaw Paper Trading & Market Feed
 * OpenClaw 紙上交易和市場數據
 *
 * MODULE_NOTE (EN): Extracted from app.js (FIX-08 file size).
 * MODULE_NOTE (中): 從 app.js 提取（FIX-08 文件大小）。
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
