/*
 * view-earn.js — 玄衡原生 view「Earn 理財 / First Stake」(Phase 2 第 9 個 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-earn.html`(iframe 後備)遷成玄衡殼內的**原生 view**。
 *   **本遷特殊 · 安全關鍵寫面**(mainnet USDT stake + typed-confirm + 5-gate + Stage 0R
 *   + cooldown)。核心策略=**verbatim 復用 earn-tab.js,絕不重寫任何安全邏輯**;view-earn.js
 *   只做「原生宿主」:忠實復現 tab-earn.html <body> 的 earn DOM,再呼 earn-tab.js 的入口
 *   `window.startEarnTab()`(首拉 6 端點 + 綁 submit/refresh/表單/records filter listener +
 *   啟 15s 輪詢 + lifecycle hook)。**typed-confirm phrase 帶 amount / 後端再驗一次 phrase /
 *   5-gate / Stage 0R / 60s cooldown 全在 earn-tab.js 內,本檔零觸碰。**
 * DOM 保真(硬紀律):SKELETON 逐一復現 earn-tab.js 全部 `getElementById` 選擇器依賴的元素
 *   (earn-tab.js 只以 id 選取,從不 querySelector/class 選取)。缺一元素 → gate 誤判 / 按鈕態
 *   錯 = 安全退步,故 id 集必齊。earn-tab.js 執行期 toggle 的狀態 class(gate-pass/gate-fail、
 *   stage0r-*、verdict-*、input-error/ok、hint-error/ok)由 view-earn.css 供樣式。
 * 為何 SKELETON 保留 legacy 短名(oc-card / oc-metrics / oc-metric* / oc-table* /
 *   oc-control-bar / oc-chip*):殼**刻意不呼** common.js `ocInjectBaseCSS()`(那會注入
 *   body{padding} + `*` reset 破壞殼 chrome),而這批 class 的樣式原本只在 ocInjectBaseCSS 內;
 *   ocChip() 亦硬 emit `.oc-chip`。故 view-earn.css 把這批(連同 .earn-* 樣式)以 `.earn-view`
 *   scope 補齊(對 ocInjectBaseCSS / tab-earn.html 頁內樣式塊 的**重複非移動**,legacy iframe 續靠
 *   自帶注入)。write-face 的 toast/modal/按鈕(.oc-toast* / .oc-confirm-* / .oc-btn*)已在
 *   shell-components.css(殼已載,R63 port),本檔不重複。
 * 主要函數:renderEarnView(注入 SKELETON + 填 explainer + 呼 startEarnTab,built guard 冪等)、
 *   pauseEarnView / resumeEarnView(見下 visibility 語義)。
 * 依賴(全復用,不重造):earn-tab.js(window.startEarnTab,須先於本檔載入)、common.js
 *   (ocApi / ocPost / ocToast / ocExplain / $)、common-formatters.js(ocEsc / ocChip / ocNum /
 *   ocTime / ocPctVal / ocSanitizeClass)、common-modals.js(openTypedConfirmModal);
 *   view-earn.css 供 .earn-* + scoped legacy 短名。
 * 硬邊界(canon / LOOP §6):
 *   ① **唯一寫路徑=earn-tab.js 的 POST /api/v1/earn/stake**(源碼實測:L537-538 唯一寫;
 *      L517 的 `/earn/redeem` 只是 typed-confirm modal `rollback:` 說明字串,非 wired 端點)。
 *      其餘 5 端點(balance/preflight/products/positions/records)全 GET。本檔零新寫路徑。
 *   ② 寫走 Rust authority:earn/stake 後端 9-gate + 再驗 phrase;GUI typed-confirm 非唯一防線
 *      (canon:硬邊界 fail-closed 不因 GUI 遷移弱化)。本檔不改動任何 gate/phrase/cooldown 邏輯。
 *   ③ visibility 語義(誠實限制):earn-tab.js 的 15s 輪詢 timer 是 IIFE closure 私有,
 *      **只暴露 window.startEarnTab / window._earnTabBuildPhrase,不暴露 stop/pause**。故:
 *        · pause = documented no-op —— 本檔清不到私有 timer;隱藏 view 時 15s 輪詢續跑
 *          (全 GET 唯讀無害,同 phase4 linucb 內部 interval 清不到之先例)。earn-tab.js 自帶的
 *          `document.visibilitychange` listener 仍會在**真瀏覽器 tab 隱藏**時 _stopPolling。
 *        · resume = 亦 no-op —— **絕不重呼 startEarnTab**:startEarnTab 非冪等(會重綁 submit/
 *          refresh/lifecycle listener → submit 雙綁 = 雙送單 = 安全退步)。輪詢從未停,資料靠
 *          既有 15s tick 保鮮;render 的 built guard 保證只首渲 + 只呼一次 startEarnTab。
 * 誠實邊界:靜態(node --check + ratchet + 註冊 smoke)只證 source 事實;**真渲染 / 選擇器真解析 /
 *   typed-confirm 真 DOM 閘 / 5-gate 真態 / stake 真行為 = NEEDS-LINUX runtime + operator**,
 *   不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;    // 原生 <section> 宿主(shell 注入)
  var built = false;  // rendered guard(防雙渲染 / 防雙呼 startEarnTab → 雙綁 listener)

  // ═══ Explainer 雙層文案(verbatim tab-earn.html lines 514-517;本檔在 render 後填入)═══
  // 為何在此:tab-earn.html 靠頁尾 inline <script> 呼 ocExplain 填 earn-explain;該行不在
  //   earn-tab.js(startEarnTab 不填 explainer),故忠實復現該行為以保 DOM 面完整。
  var EXPLAIN_SIMPLE =
    'Earn 理財 Tab 用於 Bybit Flexible USDT 首次 stake。所有寫操作必經 5-gate 預檢 + ' +
    'Stage 0R replay preflight + typed-confirm phrase(含 amount)。Bybit ack 失敗 fail-closed,不重試。';
  var EXPLAIN_DEEP =
    '本 Tab 是 Layer 1 Bybit Earn-only Sprint 1B「first stake」surface。後端 9-gate (E-0..E-9) ' +
    '對應前端 5-gate 5 light:(a) Operator 角色 (b) authorization.json (c) OPENCLAW_ALLOW_MAINNET ' +
    '(d) Bybit secret slot (e) IntentProcessor wired。typed-confirm phrase 強制帶 amount 反 ' +
    'muscle memory(OQ-3 default)。Stage 0R preflight 走 helper_scripts/canary/replay_earn_preflight.py ' +
    'CLI 觸發,GUI 只讀 JSON file。後續 stake / redeem / Auto-Allocator GUI deferred 至 Sprint 5+。';

  // ═══ 骨架(id/class verbatim 對齊 tab-earn.html <body> lines 256-509;全 earn-tab.js
  //   選擇器依賴的元素齊全;wrapper 用 .earn-view root 讓 view-earn.css 得以 scope legacy 短名)═══
  var SKELETON =
    '<div class="earn-view">' +

    // ── §3.1 標頭橫條 / Header bar ──
    '<div class="earn-header-row" role="region" aria-label="Earn 理財 header / Earn header">' +
      '<div>' +
        '<h2 class="earn-header-title">&#x1F4B0; Earn 理財 / Earn</h2>' +
        '<div class="earn-header-meta">' +
          '<span id="earn-env-badge">--</span>' +
          '&nbsp;·&nbsp;' +
          '<span id="earn-engine-mode">--</span>' +
          '&nbsp;·&nbsp;' +
          '<span id="earn-last-refresh-ts">採集時間:--</span>' +
        '</div>' +
      '</div>' +
      '<div class="earn-header-actions">' +
        '<button id="earn-refresh-btn" class="oc-btn" type="button" aria-label="重新整理 / Refresh">' +
          '&#x21BB; 重新整理 / Refresh' +
        '</button>' +
      '</div>' +
    '</div>' +

    // ── Explainer / 雙層解釋(earn-explain 由 render 後 ocExplain 填)──
    '<div class="oc-card">' +
      '<h3>&#x1F4D6; 為什麼這裡需要謹慎 / Why this requires care</h3>' +
      '<div id="earn-explain"></div>' +
    '</div>' +

    // ── §3.2 Earn 帳戶餘額 / Earn account balance ──
    '<section class="oc-card" role="region" aria-label="Earn 帳戶餘額 / Earn balance">' +
      '<h3>&#x1F4B5; Earn 帳戶餘額 / Earn Account Balance</h3>' +
      '<div id="earn-balance-loading" class="p-2 t-dim fs-dense">' +
        '&#x23F3; 正在讀取 Earn 餘額…' +
      '</div>' +
      '<div id="earn-balance-error" class="hidden p-2 t-warn fs-dense">' +
        '&#x26A0;&#xFE0F; Earn 餘額讀取失敗 — 後端可能尚未實裝 endpoint,或網路問題;下次 15 秒輪詢自動重試' +
      '</div>' +
      '<div id="earn-balance-data" class="hidden" tabindex="0">' +
        '<div class="oc-metrics">' +
          '<div class="oc-metric">' +
            '<div class="oc-metric-label">USDT Earn 餘額 / USDT Earn Balance</div>' +
            '<div class="oc-metric-val num" id="earn-balance-usdt">--</div>' +
            '<div class="oc-metric-sub" id="earn-balance-usdt-sub">USDT</div>' +
          '</div>' +
          '<div class="oc-metric">' +
            '<div class="oc-metric-label">可領取收益 / Claimable Yield</div>' +
            '<div class="oc-metric-val num" id="earn-balance-claimable">--</div>' +
            '<div class="oc-metric-sub">USDT</div>' +
          '</div>' +
          '<div class="oc-metric">' +
            '<div class="oc-metric-label">最近對賬 / Last Reconciliation</div>' +
            '<div class="oc-metric-val fs-base" id="earn-balance-recon-ts">--</div>' +
            '<div class="oc-metric-sub" id="earn-balance-recon-status">--</div>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</section>' +

    // ── §3.3 5-Gate Status Panel / 5-Gate 預檢面板 ──
    '<section class="oc-card" role="region" aria-label="5-Gate 預檢 / 5-Gate Preflight">' +
      '<h3 title="預檢 = 下單前的 5 道安全檢查,全部通過才允許提交 Earn 申購">&#x1F6E1;&#xFE0F; 下單前安全檢查 / 5-Gate 預檢' +
        '<span class="earn-h3-note" ' +
              'title="前端 5 個檢查群組對應後端 9 道細項閘門(編號 E-0 至 E-9),意義相同,只是顆粒度不同">' +
          '(5 道檢查 = 後端 9 道細項閘門) / (5 light groups = backend 9-gate E-0..E-9)' +
        '</span>' +
      '</h3>' +
      '<div class="fs-micro t-dim lh-cjk m-0 mt-1 mb-2">' +
        '這 5 道檢查確認你有下單權限、授權有效、實盤開關開啟、密鑰就緒、下單通道接好;' +
        '全部亮綠才能申購。<strong>Stage 0R</strong> 是另一道「歷史重放預檢」,需先離線跑過並 PASS。' +
      '</div>' +
      '<div id="earn-preflight-loading" class="p-2 t-dim fs-dense">' +
        '&#x23F3; 正在執行 5-gate 預檢…' +
      '</div>' +
      '<div id="earn-preflight-error" class="hidden p-2 t-warn fs-dense">' +
        '&#x26A0;&#xFE0F; 5-gate 預檢讀取失敗 — Submit 按鈕將保持禁用直到下次成功讀取' +
      '</div>' +
      '<div id="earn-preflight-data" class="hidden" tabindex="0">' +
        '<div class="earn-gate-grid" id="earn-gate-grid"></div>' +
        '<div class="earn-gate-verdict" id="earn-gate-verdict">--</div>' +
        '<div class="earn-stage0r-row stage0r-pending" id="earn-stage0r-row" ' +
             'title="Stage 0R = 歷史數據重放預檢,先在離線環境跑過策略並確認結果無誤,才放行真實申購">' +
          '<span class="earn-stage0r-badge stage0r-pending" id="earn-stage0r-badge">Stage 0R 歷史重放預檢 ⏳ 待跑</span>' +
          '<span id="earn-stage0r-detail" class="fs-dense lh-cjk">尚未跑過 Stage 0R preflight</span>' +
          '<span class="earn-stage0r-copy" id="earn-stage0r-copy"></span>' +
        '</div>' +
      '</div>' +
    '</section>' +

    // ── §3.4 Available products / 可用 Flexible 產品列表 ──
    '<section class="oc-card" role="region" aria-label="可用 Earn 產品 / Available Earn Products">' +
      '<h3>&#x1F4DC; 可用 Earn 產品 / Available Earn Products' +
        '<span class="earn-h3-note">' +
          '(Sprint 1B 鎖 USDT FlexibleSaving / Sprint 1B locked to USDT FlexibleSaving)' +
        '</span>' +
      '</h3>' +
      '<div id="earn-products-loading" class="p-2 t-dim fs-dense">' +
        '&#x23F3; 正在讀取可用產品…' +
      '</div>' +
      '<div id="earn-products-empty" class="hidden p-2 t-dim fs-dense">' +
        '&#x1F4A4; Bybit Earn 沒有可用的 USDT FlexibleSaving 產品(下架或維護中)' +
      '</div>' +
      '<div id="earn-products-error" class="hidden p-2 t-warn fs-dense">' +
        '&#x26A0;&#xFE0F; 產品列表讀取失敗 — 下次 15 秒輪詢自動重試' +
      '</div>' +
      '<div id="earn-products-data" class="hidden" tabindex="0">' +
        '<div class="oc-table-wrap">' +
          '<table class="oc-table" id="earn-products-table">' +
            '<thead><tr>' +
              '<th>產品 ID</th><th>幣種</th><th>預估 APR</th>' +
              '<th>Min Stake</th><th>Max Stake</th><th>狀態</th>' +
            '</tr></thead>' +
            '<tbody id="earn-products-tbody"></tbody>' +
          '</table>' +
        '</div>' +
      '</div>' +
    '</section>' +

    // ── §3.5 First Stake form / 首次 Stake 表單(寫面;受 5-gate + Stage 0R gate)──
    '<section class="oc-card" role="region" aria-label="首次 Stake 表單 / First Stake Form">' +
      '<h3>&#x1F510; 首次 Stake 表單 / First Stake Form</h3>' +
      '<div class="earn-typed-warn">' +
        '<b>注意:</b>此操作將寫入真實 Bybit Earn 帳戶,動主帳 USDT 資金。' +
        '所有 5-gate + Stage 0R 必先 PASS,並通過 typed-confirm phrase ' +
        '<code id="earn-typed-phrase-preview">CONFIRM EARN STAKE $&lt;amount&gt; USDT</code>' +
        '(大小寫敏感 / case-sensitive)。Bybit ack 失敗自動 fail-closed 並寫入 audit log,不重試。' +
      '</div>' +
      '<div class="earn-form-grid">' +
        '<div class="earn-form-row">' +
          '<label class="earn-form-label" for="earn-coin">幣種 / Coin</label>' +
          '<select id="earn-coin" class="earn-form-select earn-form-readonly" disabled>' +
            '<option value="USDT">USDT</option>' +
          '</select>' +
          '<span class="earn-form-hint">Sprint 1B 鎖 USDT / locked to USDT</span>' +
        '</div>' +
        '<div class="earn-form-row">' +
          '<label class="earn-form-label" for="earn-product-id">產品 ID / Product ID</label>' +
          '<input id="earn-product-id" type="text" class="earn-form-input earn-form-readonly" readonly value="--" />' +
          '<span class="earn-form-hint">自動選取第一個 Available USDT FlexibleSaving / auto-picked</span>' +
        '</div>' +
        '<div class="earn-form-row">' +
          '<label class="earn-form-label" for="earn-amount">金額 / Amount (USDT)</label>' +
          '<input id="earn-amount" type="number" min="100" max="200" step="1" ' +
                 'class="earn-form-input" placeholder="100 - 200" inputmode="numeric" />' +
          '<span class="earn-form-hint" id="earn-amount-hint">請輸入 $100 - $200 USDT 整數 / integer USDT only</span>' +
        '</div>' +
        '<div class="earn-form-row">' +
          '<label class="earn-form-label" for="earn-apr">預估 APR / Expected APR</label>' +
          '<input id="earn-apr" type="text" class="earn-form-input earn-form-readonly" readonly value="--" />' +
          '<span class="earn-form-hint">由產品 estimateApr 自動帶入 / from product.estimateApr</span>' +
        '</div>' +
      '</div>' +
      '<div class="earn-form-row mt-3">' +
        '<label class="earn-form-label" for="earn-rationale">理由 / Rationale (10-200 字)</label>' +
        '<textarea id="earn-rationale" class="earn-form-textarea" minlength="10" maxlength="200" ' +
                  'placeholder="例如:首次 Sprint 1B Earn first stake;驗證 V100 row INSERT 鏈路;Stage 0R preflight 已 PASS。"></textarea>' +
        '<span class="earn-form-hint" id="earn-rationale-hint">0 / 200 字</span>' +
      '</div>' +
      '<div class="earn-submit-row">' +
        '<button id="earn-submit-btn" class="oc-btn oc-btn-danger earn-submit-btn" type="button" disabled>' +
          '&#x1F4E5; 提交 Stake (typed-confirm) / Submit Stake' +
        '</button>' +
        '<span id="earn-submit-loading" class="earn-submit-loading hidden">' +
          '<span class="earn-spinner" aria-hidden="true"></span>' +
          '<span>正在等待 Bybit ack… / Waiting for Bybit ack…</span>' +
        '</span>' +
        '<span class="earn-submit-disabled-reason" id="earn-submit-reason">5-gate / Stage 0R 尚未 PASS</span>' +
      '</div>' +
    '</section>' +

    // ── §3.6 Active positions / 當前 Earn 持倉 ──
    '<section class="oc-card" role="region" aria-label="當前 Earn 持倉 / Active Earn Positions">' +
      '<h3>&#x1F4CB; 當前 Earn 持倉 / Active Earn Positions</h3>' +
      '<div id="earn-positions-loading" class="p-2 t-dim fs-dense">' +
        '&#x23F3; 正在讀取持倉…' +
      '</div>' +
      '<div id="earn-positions-empty" class="hidden p-2 t-dim fs-dense">' +
        '&#x1F4A4; 尚未有 Earn 持倉;首次 stake 成功後此處顯示 / No positions yet' +
      '</div>' +
      '<div id="earn-positions-error" class="hidden p-2 t-warn fs-dense">' +
        '&#x26A0;&#xFE0F; 持倉列表讀取失敗 — 下次 15 秒輪詢自動重試' +
      '</div>' +
      '<div id="earn-positions-data" class="hidden" tabindex="0">' +
        '<div class="oc-table-wrap">' +
          '<table class="oc-table" id="earn-positions-table">' +
            '<thead><tr>' +
              '<th>產品 ID</th><th>幣種</th><th>金額</th>' +
              '<th>累積收益</th><th>可領取</th><th>狀態</th><th>Order ID</th>' +
            '</tr></thead>' +
            '<tbody id="earn-positions-tbody"></tbody>' +
          '</table>' +
        '</div>' +
      '</div>' +
    '</section>' +

    // ── §3.7 Records history / 歷史審計記錄 ──
    '<section class="oc-card" role="region" aria-label="Earn 歷史審計記錄 / Earn Records History">' +
      '<h3>&#x1F4DC; 歷史審計記錄 / Records History</h3>' +
      '<div class="oc-control-bar">' +
        '<label class="earn-form-label m-0" for="earn-records-direction">方向 / Direction:</label>' +
        '<select id="earn-records-direction" class="earn-form-select earn-form-select--sm">' +
          '<option value="all">全部 / All</option>' +
          '<option value="stake">Stake</option>' +
          '<option value="redeem">Redeem</option>' +
        '</select>' +
        '<label class="earn-form-label m-0" for="earn-records-outcome">結果 / Outcome:</label>' +
        '<select id="earn-records-outcome" class="earn-form-select earn-form-select--sm">' +
          '<option value="all">全部 / All</option>' +
          '<option value="pending">待對賬 / Pending</option>' +
          '<option value="matched">已對賬 / Matched</option>' +
          '<option value="mismatch">對賬失敗 / Mismatch</option>' +
        '</select>' +
      '</div>' +
      '<div id="earn-records-loading" class="p-2 t-dim fs-dense">' +
        '&#x23F3; 正在讀取審計記錄…' +
      '</div>' +
      '<div id="earn-records-empty" class="hidden p-2 t-dim fs-dense">' +
        '&#x1F4A4; 尚未有 Earn 記錄 / No records yet' +
      '</div>' +
      '<div id="earn-records-error" class="hidden p-2 t-warn fs-dense">' +
        '&#x26A0;&#xFE0F; 審計記錄讀取失敗 — 下次 15 秒輪詢自動重試' +
      '</div>' +
      '<div id="earn-records-data" class="hidden" tabindex="0">' +
        '<div class="oc-table-wrap">' +
          '<table class="oc-table" id="earn-records-table">' +
            '<thead><tr>' +
              '<th>時間 (UTC + local)</th><th>方向</th><th>金額</th>' +
              '<th>APR</th><th>結果</th><th>Lease ID</th><th>Movement ID</th>' +
            '</tr></thead>' +
            '<tbody id="earn-records-tbody"></tbody>' +
          '</table>' +
        '</div>' +
      '</div>' +
    '</section>' +

    '</div>';

  // ═══ shell router 契約:render / resume / pause ═══
  // render:注入 SKELETON + 填 explainer + 呼 earn-tab.js 入口 startEarnTab(首拉 + 綁 listener +
  //   啟 15s 輪詢)。built guard 只首渲一次 —— 這是防「雙呼 startEarnTab → submit 雙綁 → 雙送單」的
  //   硬防線(startEarnTab 非冪等,見 MODULE_NOTE ③)。
  function renderEarnView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    host.innerHTML = SKELETON;
    built = true;
    // 填 explainer(復現 tab-earn.html 頁尾 inline script;earn-tab.js 不做這步)。
    try {
      var ex = document.getElementById('earn-explain');
      if (ex && typeof ocExplain === 'function') {
        ex.innerHTML = ocExplain(EXPLAIN_SIMPLE, EXPLAIN_DEEP);
      }
    } catch (e) { /* fail-soft:explainer 非安全關鍵,失敗不阻斷 startEarnTab */ }
    // 呼 earn-tab.js 唯一入口(verbatim 復用:5-gate / Stage 0R / typed-confirm / cooldown /
    //   POST stake 全在其內)。缺席則 fail-closed 可見化(對齊 tab-earn.html boot script 的 warn)。
    if (typeof window.startEarnTab === 'function') {
      window.startEarnTab();
    } else {
      console.warn('[view-earn] earn-tab.js 未載入(window.startEarnTab 缺席)— Earn view inactive');
    }
  }

  // resume:view 顯示 → **no-op**。**絕不重呼 startEarnTab**(非冪等會雙綁 submit/refresh/lifecycle
  //   listener = 雙送單安全退步)。earn-tab.js 的 15s 輪詢從未停,資料靠既有 tick 保鮮(見 MODULE_NOTE ③)。
  function resumeEarnView() {
    if (!built) return;
    // 刻意 no-op:輪詢續跑、listener 已綁;此處若做任何 startEarnTab/refresh 重入即破壞冪等。
  }

  // pause:view 隱藏 → **no-op**(誠實限制)。earn-tab.js 的輪詢 timer 是 closure 私有、未暴露 stop,
  //   本檔清不到;隱藏續輪詢=全 GET 唯讀無害(同 phase4 linucb 內部 interval 清不到先例)。
  //   真瀏覽器 tab 隱藏時,earn-tab.js 自帶的 document.visibilitychange listener 仍會 _stopPolling。
  function pauseEarnView() {
    // 刻意 no-op:見 MODULE_NOTE ③。
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;key=VIEWS 的 id 'earn')。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['earn'] = { render: renderEarnView, resume: resumeEarnView, pause: pauseEarnView };
  // 具名導出(task 契約:renderEarnView / pauseEarnView / resumeEarnView 可被引用)。
  window.renderEarnView = renderEarnView;
  window.resumeEarnView = resumeEarnView;
  window.pauseEarnView = pauseEarnView;
})();
