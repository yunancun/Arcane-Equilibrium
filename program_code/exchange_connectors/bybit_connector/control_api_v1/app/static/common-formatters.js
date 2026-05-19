/**
 * 玄衡 · Arcane Equilibrium — Common Formatters / Escapers / Strategy Chips
 *
 * MODULE_NOTE
 * 模組用途：純展示層 helper — 金額 / 數字 / 百分比 / 日期 / 時間 格式化、
 *          HTML / CSS 轉義、策略身份 chip、品類 tag、PnL 趨勢 SVG 渲染。
 * 主要 helper：ocMoney / ocBalance / ocNum / ocPct / ocDate / ocTime /
 *              ocEsc / ocSanitizeClass / ocChip / ocStrategy* / ocCategoryTag /
 *              ocPnlTrend / ocPnlSeriesTrend / ocPnlSeriesTableRows /
 *              ocPnlSeriesFromFills / ocPnlCell / ocMiniTrendSvg /
 *              ocPerformanceMetric* / ocFillTime / ocPnlClass /
 *              ocFirstFinite / ocPositionEntryValue / ocFillExecValue。
 * 依賴：common.js 已先載入 — 本檔需 ocFxConvert / ocCurrSymbol（在 common.js
 *       Currency Toggle System 區段定義）。常數 OC_STRATEGY_COLOR_META 與
 *       _OC_CAT_CONFIG 在本檔內聚定義。
 * 硬邊界：純函式，無任何 fetch / 寫入 / 全域狀態修改。所有動態文字必經 ocEsc
 *         過濾，class token 必經 ocSanitizeClass，禁止 XSS 漏洞。
 *
 * P2-COMMON-JS-LOC 拆分歷史：原 common.js 行 416–961 內聚搬出，以維持
 * §九 2000 LOC 硬上限。
 */

// ─── Formatters ──────────────────────────────────────────────────────────────
function ocMoney(v, decimals) {
  // PnL display: converts to active currency, adds +/- prefix.
  // Example: ocMoney(100) → "+USDT 100.00" / "+$100.00" / "+€92.00"
  // PnL 顯示：转换为當前货币，添加 +/- 前缀。
  if (v == null || isNaN(v)) return '--';
  const d = decimals != null ? decimals : 2;
  const converted = ocFxConvert(Number(v));
  const prefix = converted >= 0 ? '+' : '-';
  return prefix + ocCurrSymbol() + Math.abs(converted).toFixed(d);
}

function ocBalance(v, decimals) {
  // Balance display: converts to active currency, no +/- prefix.
  // Example: ocBalance(9994) → "USDT 9994.00" / "$9994.00" / "€9194.48"
  // 余额顯示：转换为當前货币，無 +/- 前缀。
  if (v == null || isNaN(v)) return '--';
  const d = decimals != null ? decimals : 2;
  const converted = ocFxConvert(Number(v));
  return ocCurrSymbol() + converted.toFixed(d);
}

function ocNum(v, decimals) {
  if (v == null || isNaN(v)) return '--';
  return Number(v).toFixed(decimals != null ? decimals : 2);
}

function ocFirstFinite(obj, keys) {
  if (!obj || !Array.isArray(keys)) return null;
  for (const k of keys) {
    const raw = obj[k];
    if (raw == null || raw === '') continue;
    const n = Number(raw);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function ocPositionEntryValue(pos) {
  // 持倉開倉名義金額。Bybit 行優先用 positionValue，否則用當前數量 * 開倉均價。
  const direct = ocFirstFinite(pos, ['positionValue', 'position_value', 'entry_value', 'entryValue']);
  if (direct != null && direct > 0) return direct;
  const qty = ocFirstFinite(pos, ['size', 'qty', 'position_qty', 'positionQty']);
  const entry = ocFirstFinite(pos, ['avgPrice', 'avg_price', 'avg_entry_price', 'entry_price']);
  const absQty = qty == null ? null : Math.abs(qty);
  if (absQty != null && entry != null && absQty > 0 && entry > 0) return absQty * entry;
  return null;
}

function ocFillExecValue(fill) {
  // 成交名義金額。Bybit 有 execValue；DB/engine 備援列用 qty * price 回推。
  const direct = ocFirstFinite(fill, [
    'execValue', 'exec_value', 'executed_value', 'cumExecValue', 'cum_exec_value',
    'notional', 'trade_value',
  ]);
  if (direct != null && direct > 0) return direct;
  const qty = ocFirstFinite(fill, ['execQty', 'exec_qty', 'qty', 'fill_qty']);
  const price = ocFirstFinite(fill, ['execPrice', 'exec_price', 'price', 'fill_price']);
  const absQty = qty == null ? null : Math.abs(qty);
  if (absQty != null && price != null && absQty > 0 && price > 0) return absQty * price;
  return null;
}

function ocAmount(v, decimals) {
  if (v == null || isNaN(v) || Number(v) <= 0) return '--';
  const abs = Math.abs(Number(v));
  const d = decimals != null ? decimals : (abs > 0 && abs < 0.01 ? 4 : 2);
  return ocBalance(v, d);
}

function ocPct(v) {
  if (v == null || isNaN(v)) return '--';
  return (v * 100).toFixed(1) + '%';
}

function ocDate(ts) {
  if (ts == null || ts === '') return null;
  const raw = typeof ts === 'string' ? ts.trim() : ts;
  if (raw === '') return null;
  const n = typeof raw === 'number' ? raw : Number(raw);
  const d = Number.isFinite(n) ? new Date(n > 1e12 ? n : n * 1000) : new Date(raw);
  return Number.isFinite(d.getTime()) ? d : null;
}

function ocTime(ts) { const d = ocDate(ts); return d ? d.toLocaleString('zh-CN', { hour12: false }) : '--'; }
function ocTimeShort(ts) { const d = ocDate(ts); return d ? d.toLocaleTimeString('zh-CN', { hour12: false }) : '--'; }

function ocFillTime(ts) {
  const d = ocDate(ts);
  if (!d) return '--';
  const p = n => String(n).padStart(2, '0');
  let tz = '';
  try { const t = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(d).find(x => x.type === 'timeZoneName'); tz = t ? t.value : ''; } catch (_) {}
  return p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ' UTC (local: ' + p(d.getHours()) + ':' + p(d.getMinutes()) + (tz ? ' ' + tz : '') + ')';
}

function ocPnlClass(v) {
  if (v == null) return '';
  return v >= 0 ? 'green' : 'red';
}

// Demo/Paper/Live 共用的後端 canonical performance metric 輔助函式。
function ocPerformanceMetricByKey(metrics, key) {
  if (!Array.isArray(metrics)) return null;
  return metrics.find(m => m && m.key === key) || null;
}

// 依 key 回傳 metric value，供小型狀態卡使用。
function ocPerformanceMetricValue(metrics, key) {
  const metric = ocPerformanceMetricByKey(metrics, key);
  return metric ? metric.value : null;
}

// 從 API payload 選 canonical metrics；空 legacy 陣列必須回落到 DB truth。
function ocPerformanceMetricsFromPayload(payload) {
  if (Array.isArray(payload)) return payload;
  const top = payload && Array.isArray(payload.performance_metrics) ? payload.performance_metrics : null;
  const dbMetrics = payload && payload.db_true_metrics && Array.isArray(payload.db_true_metrics.performance_metrics)
    ? payload.db_true_metrics.performance_metrics : null;
  if (top && top.length > 0) return top;
  if (dbMetrics && dbMetrics.length > 0) return dbMetrics;
  return top || dbMetrics || [];
}

// 格式化後端 metric 描述，避免各 tab 重複實作單位邏輯。
function ocFormatPerformanceMetric(metric) {
  if (!metric) return '--';
  const value = metric.value;
  if (value == null || value === '') return '--';
  if (value === 'inf') return '∞';
  const unit = String(metric.unit || '');
  const n = Number(value);
  if (!Number.isFinite(n)) return '--';
  if (unit === 'count') return String(Math.round(n));
  if (unit === 'money' || unit === 'usdt') return ocMoney(n);
  if (unit === 'money_abs') return ocBalance(n, 4);
  if (unit === 'bps') return n.toFixed(2) + ' bps';
  if (unit === 'rate') return (n * 100).toFixed(1) + '%';
  if (unit === 'percent') return n.toFixed(2) + '%';
  if (unit === 'ratio') return ocNum(n, 2);
  if (unit === 'seconds') {
    if (n >= 3600) return (n / 3600).toFixed(1) + ' h';
    if (n >= 60) return (n / 60).toFixed(1) + ' min';
    return Math.round(n) + ' sec';
  }
  return ocNum(n, 2);
}

// 僅對明確標記為 PnL polarity 的 metric 套用正負色。
function ocPerformanceMetricClass(metric) {
  if (!metric || metric.polarity !== 'pnl') return '';
  const n = Number(metric.value);
  if (!Number.isFinite(n) || n === 0) return '';
  return n > 0 ? 'green' : 'red';
}

// 渲染 canonical performance metric grid。
function ocRenderPerformanceMetrics(metrics) {
  if (!Array.isArray(metrics) || metrics.length === 0) {
    return '<div class="oc-loading">暂無指標數據</div>';
  }
  return metrics.map(metric => {
    const key = ocEsc(metric.key || '');
    const label = ocEsc(metric.label || metric.key || '--');
    const tooltip = ocEsc(metric.tooltip_zh || '');
    const source = ocEsc(metric.source || '');
    const cls = ocPerformanceMetricClass(metric);
    const value = ocEsc(ocFormatPerformanceMetric(metric));
    return '<div class="oc-metric oc-perf-metric" data-metric-key="' + key + '" data-source="' + source + '">' +
      '<div class="oc-metric-label" title="' + tooltip + '">' + label + '</div>' +
      '<div class="oc-metric-val ' + cls + '">' + value + '</div>' +
    '</div>';
  }).join('');
}

// 渲染 dashboard gate 趨勢使用的小型 inline sparkline。
function ocMiniTrendSvg(values, opts) {
  var nums = Array.isArray(values)
    ? values.map(function(v) { return Number(v); }).filter(function(v) { return Number.isFinite(v); })
    : [];
  if (nums.length < 2) {
    return '<div class="oc-mini-trend-empty">collecting trend</div>';
  }
  opts = opts || {};
  var width = Number(opts.width || 180);
  var height = Number(opts.height || 54);
  var pad = Number(opts.pad || 5);
  var minV = Math.min.apply(null, nums);
  var maxV = Math.max.apply(null, nums);
  if (opts.includeZero) {
    minV = Math.min(minV, 0);
    maxV = Math.max(maxV, 0);
  }
  var span = maxV - minV;
  if (span <= 0) span = 1;
  var usableW = width - pad * 2;
  var usableH = height - pad * 2;
  var points = nums.map(function(v, i) {
    var x = nums.length === 1 ? width / 2 : pad + (i / (nums.length - 1)) * usableW;
    var y = pad + (1 - ((v - minV) / span)) * usableH;
    return x.toFixed(1) + ',' + y.toFixed(1);
  }).join(' ');
  var tone = opts.tone || 'info';
  var stroke = tone === 'good' ? 'var(--green)'
             : tone === 'bad' ? 'var(--red)'
             : tone === 'warn' ? 'var(--yellow)'
             : 'var(--blue)';
  var zeroLine = '';
  if (opts.includeZero && minV < 0 && maxV > 0) {
    var zy = pad + (1 - ((0 - minV) / span)) * usableH;
    zeroLine = '<line x1="' + pad + '" y1="' + zy.toFixed(1) + '" x2="' + (width - pad) +
      '" y2="' + zy.toFixed(1) + '" class="oc-mini-trend-zero" />';
  }
  return '<svg class="oc-mini-trend" viewBox="0 0 ' + width + ' ' + height +
    '" preserveAspectRatio="none" aria-hidden="true">' + zeroLine +
    '<polyline points="' + points + '" fill="none" stroke="' + stroke +
    '" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />' +
    '</svg>';
}

// ─── Status Chip HTML ────────────────────────────────────────────────────────
function ocChip(text, type) {
  // type: good, warn, bad, neutral, info
  return '<span class="oc-chip oc-chip-' + (type || 'neutral') + '">' + ocEsc(text) + '</span>';
}

// ─── Escape HTML ─────────────────────────────────────────────────────────────
function ocEsc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ─── Sanitize CSS class name (P2-NEW-6) ─────────────────────────────────────
// 僅允許字母、數字、連字符、底線，其餘字符全部過濾。
function ocSanitizeClass(s) {
  if (s == null) return '';
  return String(s).replace(/[^a-zA-Z0-9\-_]/g, '');
}

// ─── Strategy Identity Color / 策略身份顏色 ─────────────────────────────────
// Shared by Strategy, Demo, and Live so one strategy keeps the same color everywhere.
const OC_STRATEGY_COLOR_META = {
  grid_trading: { label: 'grid_trading', zh: '網格', color: '#58a6ff' },
  ma_crossover: { label: 'ma_crossover', zh: '均線', color: '#3fb950' },
  bb_reversion: { label: 'bb_reversion', zh: '回歸', color: '#a855f7' },
  bb_breakout: { label: 'bb_breakout', zh: '突破', color: '#f78166' },
  funding_arb: { label: 'funding_arb', zh: '費率', color: '#d29922' },
};

function ocStrategyKey(strategy) {
  if (strategy == null) return '';
  const raw = String(strategy).trim();
  if (!raw || raw === '--') return '';
  const normalized = raw
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
    .toLowerCase();
  const aliases = {
    grid: 'grid_trading',
    grid_trading: 'grid_trading',
    ma_crossover: 'ma_crossover',
    bb_reversion: 'bb_reversion',
    bb_breakout: 'bb_breakout',
    funding_arb: 'funding_arb',
    funding_rate_arb: 'funding_arb',
    fundingrate_arb: 'funding_arb',
  };
  if (aliases[normalized]) return aliases[normalized];
  for (const key of Object.keys(OC_STRATEGY_COLOR_META)) {
    if (normalized === key || normalized.startsWith(key + '_')) return key;
  }
  if (normalized.startsWith('funding_rate_arb_') || normalized.startsWith('fundingrate_arb_')) return 'funding_arb';
  return '';
}

function ocStrategyMeta(strategy) {
  const key = ocStrategyKey(strategy);
  if (!key || !OC_STRATEGY_COLOR_META[key]) return null;
  return Object.assign({ key: key }, OC_STRATEGY_COLOR_META[key]);
}

function ocStrategyLabel(strategy) {
  const meta = ocStrategyMeta(strategy);
  if (!meta) return strategy == null ? '' : String(strategy);
  return meta.label + ' / ' + meta.zh;
}

function ocStrategyChip(strategy, options) {
  const raw = strategy == null ? '' : String(strategy);
  if (!raw || raw === '--') return '--';
  const meta = ocStrategyMeta(raw);
  if (!meta) return ocEsc(raw);
  const opts = options || {};
  const text = opts.label || meta.label;
  const title = meta.label + ' / ' + meta.zh;
  return '<span class="oc-strategy-chip oc-strategy-' + meta.key + '" title="' + ocEsc(title) + '">'
    + '<span class="oc-strategy-dot"></span>' + ocEsc(text) + '</span>';
}

// ─── Product Category Tag / 產品品類標籤 ─────────────────────────────────────
// 在持倉/訂單/成交旁顯示帶顏色的品類標籤，便於區分不同產品類型。
const _OC_CAT_CONFIG = {
  linear:  { label: 'U本位',   color: '#3b82f6', bg: 'rgba(59,130,246,0.15)' },
  spot:    { label: '現货',     color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
  inverse: { label: '币本位',   color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
  option:  { label: '期權',     color: '#a855f7', bg: 'rgba(168,85,247,0.15)' },
};
function ocCategoryTag(category) {
  const cat = (category || 'linear').toLowerCase();
  const cfg = _OC_CAT_CONFIG[cat] || { label: cat, color: '#94a3b8', bg: 'rgba(148,163,184,0.15)' };
  return '<span style="display:inline-block;font-size:10px;padding:1px 5px;border-radius:3px;'
    + 'color:' + cfg.color + ';background:' + cfg.bg + ';border:1px solid ' + cfg.color + ';'
    + 'margin-left:4px;vertical-align:middle;line-height:14px">' + ocEsc(cfg.label) + '</span>';
}

// 渲染累計盈虧走勢。字段兼容：realized_pnl / closedPnl / pnl。左舊右新；
// y 軸總是包含 0，方便零線直觀分隔盈虧。zeroLineId 可選，傳入會自動調整
// 虛線 y 座標。
function ocPnlTrend(lineId, labelId, fills, zeroLineId) {
  var lineEl = document.getElementById(lineId);
  var labelEl = document.getElementById(labelId);
  if (!lineEl) return;
  if (!fills || !fills.length) {
    lineEl.setAttribute('points', '');
    if (labelEl) { labelEl.textContent = 'no data'; labelEl.setAttribute('fill', 'var(--text-dim)'); }
    return;
  }
  var sorted = fills.slice().reverse().slice(0, 50);
  var cumulative = 0;
  var series = sorted.map(function(f) {
    var v = f.realized_pnl != null ? f.realized_pnl
          : (f.closedPnl != null ? f.closedPnl
          : (f.pnl != null ? f.pnl : 0));
    var n = parseFloat(v);
    if (!isFinite(n)) n = 0;
    cumulative += n;
    return cumulative;
  });
  if (series.length < 2) {
    lineEl.setAttribute('points', '');
    if (labelEl) labelEl.textContent = 'collecting data...';
    return;
  }
  var W = 400, H = 120, pad = 8;
  var minV = Math.min(0, Math.min.apply(null, series));
  var maxV = Math.max(0, Math.max.apply(null, series));
  var range = (maxV - minV) || 1;
  var yFor = function(v) { return H - pad - ((v - minV) / range) * (H - pad * 2); };
  var points = series.map(function(v, i) {
    var x = pad + (i / (series.length - 1)) * (W - pad * 2);
    return x.toFixed(1) + ',' + yFor(v).toFixed(1);
  }).join(' ');
  lineEl.setAttribute('points', points);
  var last = series[series.length - 1];
  lineEl.setAttribute('stroke', last >= 0 ? 'var(--green)' : 'var(--red)');
  if (zeroLineId) {
    var zEl = document.getElementById(zeroLineId);
    if (zEl) {
      var zy = yFor(0).toFixed(1);
      zEl.setAttribute('x1', pad);
      zEl.setAttribute('x2', W - pad);
      zEl.setAttribute('y1', zy);
      zEl.setAttribute('y2', zy);
    }
  }
  if (labelEl) {
    labelEl.textContent = (last >= 0 ? '+' : '') + last.toFixed(4) + ' USDT (' + series.length + ' fills)';
    labelEl.setAttribute('fill', last >= 0 ? 'var(--green)' : 'var(--red)');
  }
}

function ocPnlSeriesTrend(lineId, labelId, points, zeroLineId, summary) {
  var lineEl = document.getElementById(lineId);
  var labelEl = document.getElementById(labelId);
  if (!lineEl) return;
  var rows = Array.isArray(points) ? points : [];
  if (!rows.length) {
    lineEl.setAttribute('points', '');
    if (labelEl) { labelEl.textContent = 'no data'; labelEl.setAttribute('fill', 'var(--text-dim)'); }
    return;
  }
  var series = rows.map(function(p) {
    var n = Number(p && p.cumulative_net_pnl);
    return Number.isFinite(n) ? n : 0;
  });
  var W = 400, H = 120, pad = 8;
  var minV = Math.min(0, Math.min.apply(null, series));
  var maxV = Math.max(0, Math.max.apply(null, series));
  var range = (maxV - minV) || 1;
  var yFor = function(v) { return H - pad - ((v - minV) / range) * (H - pad * 2); };
  var pointsAttr = series.map(function(v, i) {
    var x = series.length > 1 ? pad + (i / (series.length - 1)) * (W - pad * 2) : W / 2;
    return x.toFixed(1) + ',' + yFor(v).toFixed(1);
  }).join(' ');
  lineEl.setAttribute('points', pointsAttr);
  var last = series[series.length - 1];
  lineEl.setAttribute('stroke', last >= 0 ? 'var(--green)' : 'var(--red)');
  if (zeroLineId) {
    var zEl = document.getElementById(zeroLineId);
    if (zEl) {
      var zy = yFor(0).toFixed(1);
      zEl.setAttribute('x1', pad);
      zEl.setAttribute('x2', W - pad);
      zEl.setAttribute('y1', zy);
      zEl.setAttribute('y2', zy);
    }
  }
  if (labelEl) {
    var fills = summary && Number.isFinite(Number(summary.fills)) ? Number(summary.fills) : 0;
    var rangeLabel = summary && summary.range ? String(summary.range).toUpperCase() : '';
    labelEl.textContent = (last >= 0 ? '+' : '') + last.toFixed(4) + ' USDT' +
      (rangeLabel ? ' · ' + rangeLabel : '') + ' · ' + fills + ' fills';
    labelEl.setAttribute('fill', last >= 0 ? 'var(--green)' : 'var(--red)');
  }
}

function ocPnlSeriesTableRows(points) {
  var rows = Array.isArray(points) ? points.slice() : [];
  rows = rows.filter(function(p) {
    return p && (Number(p.fills) || Number(p.net_pnl) || Number(p.funding_pnl));
  }).slice(-14).reverse();
  if (!rows.length) {
    return '<tr class="empty-row"><td colspan="5">no PnL buckets</td></tr>';
  }
  return rows.map(function(p) {
    var net = Number(p.net_pnl);
    var cum = Number(p.cumulative_net_pnl);
    var fees = Number(p.fees);
    return '<tr>' +
      '<td>' + ocEsc(ocTime(p.ts_ms)) + '</td>' +
      '<td>' + (Number(p.fills) || 0) + '</td>' +
      '<td class="' + ocPnlClass(net) + '">' + ocMoney(Number.isFinite(net) ? net : 0, 4) + '</td>' +
      '<td class="' + ocPnlClass(cum) + '">' + ocMoney(Number.isFinite(cum) ? cum : 0, 4) + '</td>' +
      '<td>' + ocBalance(Number.isFinite(fees) ? fees : 0, 4) + '</td>' +
      '</tr>';
  }).join('');
}

function ocPnlSeriesFromFills(fills, rangeKey) {
  var rows = Array.isArray(fills) ? fills.slice() : [];
  rows = rows.map(function(f) {
    var ts = f && (f.exec_time || f.execTime || f.ts_ms || f.ts || f.time);
    var d = ocDate(ts);
    var grossRaw = f && (f.realized_pnl != null ? f.realized_pnl
      : (f.closedPnl != null ? f.closedPnl : (f.pnl != null ? f.pnl : 0)));
    var feeRaw = f && (f.fee != null ? f.fee : (f.execFee != null ? f.execFee : 0));
    var gross = Number(grossRaw);
    var fee = Number(feeRaw);
    if (!Number.isFinite(gross)) gross = 0;
    if (!Number.isFinite(fee)) fee = 0;
    return {
      ts_ms: d ? d.getTime() : 0,
      gross_pnl: gross,
      fees: fee,
      funding_pnl: 0,
      net_pnl: gross - fee,
      fills: 1,
    };
  }).filter(function(p) {
    return p.ts_ms > 0;
  }).sort(function(a, b) {
    return a.ts_ms - b.ts_ms;
  });
  var rangeMsMap = {
    '1h': 60 * 60 * 1000,
    '6h': 6 * 60 * 60 * 1000,
    '24h': 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000,
    '30d': 30 * 24 * 60 * 60 * 1000,
  };
  var key = String(rangeKey || '').toLowerCase();
  if (rangeMsMap[key]) {
    var cutoff = Date.now() - rangeMsMap[key];
    rows = rows.filter(function(p) { return p.ts_ms >= cutoff; });
  }

  var cumulative = 0;
  var points = rows.map(function(p) {
    cumulative += Number(p.net_pnl) || 0;
    return {
      ts_ms: p.ts_ms,
      fills: p.fills,
      gross_pnl: Number(p.gross_pnl) || 0,
      fees: Number(p.fees) || 0,
      funding_pnl: 0,
      net_pnl: Number(p.net_pnl) || 0,
      cumulative_net_pnl: cumulative,
      source: 'recent_fills_fallback',
    };
  });
  return {
    available: points.length > 0,
    source: 'recent_fills_fallback',
    range: rangeKey || 'fills',
    fills: points.length,
    points: points,
  };
}

function ocSetPnlRangeButtons(containerId, activeRange) {
  var el = document.getElementById(containerId);
  if (!el) return;
  var active = String(activeRange || '').toLowerCase();
  el.querySelectorAll('button[data-pnl-range]').forEach(function(btn) {
    var isActive = String(btn.getAttribute('data-pnl-range') || '').toLowerCase() === active;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    btn.style.borderColor = isActive ? 'rgba(56,139,253,0.75)' : '';
    btn.style.background = isActive ? 'rgba(56,139,253,0.16)' : '';
    btn.style.color = isActive ? 'var(--blue)' : '';
  });
}

// 渲染盈亏單元格。開倉單 PnL≈0 顯示灰色破折號；平倉單顯示带符號的綠/红金额。
// 兼容字段：realized_pnl (Rust engine) / closedPnl (Bybit API)。
function ocPnlCell(raw) {
  const pnl = parseFloat(raw);
  if (!isFinite(pnl) || Math.abs(pnl) < 0.0001) {
    return '<td style="color:var(--text-dim)">—</td>';
  }
  const cls = pnl >= 0 ? 'green' : 'red';
  const sign = pnl >= 0 ? '+' : '';
  return '<td class="' + cls + '">' + sign + pnl.toFixed(4) + '</td>';
}
