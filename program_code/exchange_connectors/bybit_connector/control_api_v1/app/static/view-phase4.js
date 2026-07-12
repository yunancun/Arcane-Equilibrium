/*
 * view-phase4.js — 玄衡原生 view「Phase 4 儀表板」(Phase 2 第 7 個 iframe→原生遷移;read-only)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-phase4.html`(iframe 後備)遷成玄衡殼內的**原生 view**,
 *   延續 gates/monitor/development/learning/agents/ai 六遷的 strangler-fig。**本遷特殊**:
 *   phase4 是 **card-host 儀表板**——不重建內容於玄衡組件庫,而是**逐字移植** tab-phase4.html
 *   的 card-loading pattern:fetch `/static/cards/{teacher,linucb,news,dl3}_card.html` 片段 →
 *   innerHTML 注入 slot → 重跑內嵌 script(定義各卡 loader / 自管輪詢)。card 檔為 legacy
 *   iframe 與新 native 兩路**共用**(絕不修改),故其 CSS class 由 view-phase4.css 於殼文檔供給。
 *   內容 / 行為守恆(strangler-fig 硬紀律):DOM id/class(p4-light-* / phase4-degraded /
 *   phase4-card-*-slot)、card-loading、status 輪詢邏輯全 verbatim 對齊 tab-phase4.html。
 * 主要函數:renderPhase4View(建骨架 + 注入 4 卡 + 啟 host poller,冪等)、
 *   resumePhase4View(顯示→立即 refresh + 幂等重啟 poller)、pausePhase4View(隱藏→停兩 host interval)、
 *   loadTeacherSlot/loadLinucbSlot/loadNewsSlot/loadDl3Slot(card-loading)、
 *   applyLight/showDegraded/refresh(status 輪詢)。
 * 依賴(全復用,不重造):殼 common.js 的 ocApi(GET;auth 由 HttpOnly cookie);card 片段自帶
 *   loader;view-phase4.css 供 phase4-light / p4-grid 等 class;shell-components/oc-utilities 供 .panel/.note/.p-4。
 * 硬邊界(canon / LOOP §6):
 *   ① **零寫路徑**——phase4 全唯讀 GET:4 個 /static/cards/*.html + /api/v1/phase4/status(host)+
 *      各卡 /api/v1/phase4/{teacher,linucb,news,dl3};**絕不引入任何 POST/PUT/DELETE/order**。
 *   ② canon 7:任何錯誤 / 非物件 status → 全 grey + degraded 橫幅,**絕不假 green / 假成功**
 *      (verbatim tab-phase4.html refresh fail-closed)。
 *   ③ visibility 語義:隱藏時 pause 停兩個 host interval(30s status + 10s teacher),
 *      鏡像 iframe openclaw-tab-visibility 暫停(隱藏續輪詢=freshness/safety 退步)。
 *   ④ ratchet 0/0/0:零裸 hex、零 inline style 屬性、零頁內樣式塊;degraded 顯隱走
 *      el.style.display=(scoped 賦值,非樣式屬性字面)。
 *   ⑤ **linucb 內部 interval 已知限制**:linucb_card.html 的 script 內自帶 refresh()+
 *      setInterval(refresh,30000)(closure 私有,不暴露 id),本檔**清不到**故不試圖 clear;
 *      這與 legacy iframe 行為對等(legacy 亦從不 clear linucb 內部輪詢)。防雙份 interval 的
 *      唯一手段=render 的 built guard(只注入一次卡片);pause 只能停本檔掌控的兩個 host interval。
 * 誠實邊界:靜態(node --check + ratchet)只證 source 事實;**真渲染 / 真卡片注入 / 真輪詢 /
 *   真三態燈色 = NEEDS-LINUX runtime + operator 視覺**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;             // 原生 <section> 宿主(shell 注入)
  var built = false;          // rendered guard(防雙渲染;雙渲染=linucb 內部 interval 跑兩份)
  var statusTimer = null;     // host 30s status 輪詢 interval id(null=停;pause 必清)
  var teacherTimer = null;    // host 10s teacher 快刷 interval id(null=停;pause 必清)

  // status 輪詢常量(verbatim tab-phase4.html lines 354-355)
  var MODULES = ['teacher', 'linucb', 'news', 'dl3'];
  var VALID = { grey: 1, green: 1, yellow: 1, red: 1 };

  // ═══ 骨架(id/class verbatim 對齊 tab-phase4.html lines 162-347;燈預設 grey=未啟動)═══
  // 外框改玄衡組件(.panel/.panel-t/.note;legacy oc-card/subtitle 殼作用域不可用),
  // 但載重 id/class(phase4-degraded / p4-light-* / phase4-light* / phase4-card-*-slot)逐字守恆。
  var SKELETON =
    '<div class="p-4">' +
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">Phase 4 儀表板</span><span class="code">PHASE 4 DASHBOARD</span></div>' +
        '<div class="note">Teacher · LinUCB · News · DL-3 — 骨架階段(所有模块默认 grey 表示未啟動)/ skeleton stage (all modules default to grey = not started)</div>' +
        // degraded 橫幅(canon 7:IPC 降級 → 全 grey;預設 CSS display:none,showDegraded 切換)
        '<div id="phase4-degraded" class="phase4-degraded-banner">&#x26A0; IPC degraded — falling back to grey lights / IPC 降级，所有指示灯回退为 grey</div>' +
        // ═ 紅黃綠燈行(verbatim tab-phase4.html lines 167-196)═
        '<div class="phase4-light-row" id="phase4-lights">' +
          '<div class="phase4-light" data-module="teacher">' +
            '<div class="phase4-light-dot grey" id="p4-light-teacher"></div>' +
            '<div class="phase4-light-label"><span class="name">Teacher</span><span class="sub">Claude Teacher · 教师指令</span></div>' +
          '</div>' +
          '<div class="phase4-light" data-module="linucb">' +
            '<div class="phase4-light-dot grey" id="p4-light-linucb"></div>' +
            '<div class="phase4-light-label"><span class="name">LinUCB</span><span class="sub">Bandit · 多臂老虎机</span></div>' +
          '</div>' +
          '<div class="phase4-light" data-module="news">' +
            '<div class="phase4-light-dot grey" id="p4-light-news"></div>' +
            '<div class="phase4-light-label"><span class="name">News</span><span class="sub">Free RSS · 新闻信號</span></div>' +
          '</div>' +
          '<div class="phase4-light" data-module="dl3">' +
            '<div class="phase4-light-dot grey" id="p4-light-dl3"></div>' +
            '<div class="phase4-light-label"><span class="name">DL-3</span><span class="sub">Time-series Foundation · 時序基礎模型</span></div>' +
          '</div>' +
        '</div>' +
      '</div>' +
      // ═ 4 個 card slot(id verbatim;各由 loadXSlot 注入 /static/cards/X_card.html 片段)═
      '<div id="phase4-card-teacher-slot" data-module="teacher"><div class="phase4-card-placeholder">loading teacher card… / 正在載入 Teacher 卡片…</div></div>' +
      '<div id="phase4-card-linucb-slot" data-module="linucb"><div class="phase4-card-placeholder">loading linucb card… / 正在載入 LinUCB 卡片…</div></div>' +
      '<div id="phase4-card-news-slot" data-module="news"><div class="phase4-card-placeholder">loading news card… / 正在載入 News 卡片…</div></div>' +
      '<div id="phase4-card-dl3-slot" data-module="dl3"><div class="phase4-card-placeholder">loading dl3 card… / 正在載入 DL-3 卡片…</div></div>' +
    '</div>';

  // ═══ Card-loading pattern(verbatim tab-phase4.html lines 205-347)═══
  // teacher/news/dl3 同構:取 .phase4-card 移入 slot、內嵌 script 追加 document.body、呼各自 loader。
  // linucb 例外:clone 全 childNodes 入 slot、slot 內 replaceChild 重跑 script;不呼 loader
  //   (它自帶 refresh()+setInterval 自管輪詢,見 MODULE_NOTE ⑤ 已知限制)。

  function loadTeacherSlot() {
    fetch('/static/cards/teacher_card.html', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : ''; })
      .then(function (html) {
        var slot = document.getElementById('phase4-card-teacher-slot');
        if (!slot || !html) return;
        var tmp = document.createElement('div');
        tmp.innerHTML = html;
        var card = tmp.querySelector('.phase4-card');
        if (card) { slot.innerHTML = ''; slot.appendChild(card); }
        // 重跑內嵌 script(瀏覽器不會自動執行注入的 script 節點)→ 定義 window.loadTeacherCard
        var scripts = tmp.querySelectorAll('script');
        scripts.forEach(function (s) {
          var ns = document.createElement('script');
          ns.textContent = s.textContent;
          document.body.appendChild(ns);
        });
        if (typeof window.loadTeacherCard === 'function') { window.loadTeacherCard(); }
      })
      .catch(function () { /* fail-soft */ });
  }

  function loadLinucbSlot() {
    fetch('/static/cards/linucb_card.html', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : ''; })
      .then(function (html) {
        var slot = document.getElementById('phase4-card-linucb-slot');
        if (!slot || !html) return;
        var tmp = document.createElement('div');
        tmp.innerHTML = html;
        slot.innerHTML = '';
        Array.prototype.forEach.call(tmp.childNodes, function (n) {
          slot.appendChild(n.cloneNode(true));
        });
        // 重跑內嵌 script(slot 內 replaceChild;linucb 自管 refresh()+setInterval,不呼 loader)
        Array.prototype.forEach.call(slot.querySelectorAll('script'), function (orig) {
          var s = document.createElement('script');
          if (orig.src) s.src = orig.src; else s.textContent = orig.textContent;
          orig.parentNode.replaceChild(s, orig);
        });
      })
      .catch(function () { /* fail-soft */ });
  }

  function loadNewsSlot() {
    fetch('/static/cards/news_card.html', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : ''; })
      .then(function (html) {
        var slot = document.getElementById('phase4-card-news-slot');
        if (!slot || !html) return;
        var tmp = document.createElement('div');
        tmp.innerHTML = html;
        var card = tmp.querySelector('.phase4-card');
        if (card) { slot.innerHTML = ''; slot.appendChild(card); }
        var scripts = tmp.querySelectorAll('script');
        scripts.forEach(function (s) {
          var ns = document.createElement('script');
          ns.textContent = s.textContent;
          document.body.appendChild(ns);
        });
        if (typeof window.loadNewsCard === 'function') { window.loadNewsCard(); }
      })
      .catch(function () { /* fail-soft */ });
  }

  function loadDl3Slot() {
    fetch('/static/cards/dl3_card.html', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : ''; })
      .then(function (html) {
        var slot = document.getElementById('phase4-card-dl3-slot');
        if (!slot || !html) return;
        var tmp = document.createElement('div');
        tmp.innerHTML = html;
        var card = tmp.querySelector('.phase4-card');
        if (card) { slot.innerHTML = ''; slot.appendChild(card); }
        var scripts = tmp.querySelectorAll('script');
        scripts.forEach(function (s) {
          var ns = document.createElement('script');
          ns.textContent = s.textContent;
          document.body.appendChild(ns);
        });
        if (typeof window.loadDl3Card === 'function') { window.loadDl3Card(); }
      })
      .catch(function () { /* fail-soft */ });
  }

  // ═══ status 輪詢(verbatim tab-phase4.html lines 353-410)═══

  // applyLight:套燈色 class。注:'phase4-card-'+mod 分支(卡片內狀態點)在源碼即無匹配元素
  //   (slot 是 phase4-card-*-slot、卡片 div 是 *-card),為源碼既有 no-op,逐字守恆(卡片
  //   自身狀態點由各卡 loader 更新)。
  function applyLight(mod, status) {
    var safe = VALID[status] ? status : 'grey';
    var dot = document.getElementById('p4-light-' + mod);
    if (dot) {
      dot.className = 'phase4-light-dot ' + safe;
    }
    var card = document.getElementById('phase4-card-' + mod);
    if (card) {
      var pill = card.querySelector('.phase4-card-status .phase4-light-dot');
      if (pill) pill.className = 'phase4-light-dot ' + safe;
    }
  }

  function showDegraded(on) {
    var el = document.getElementById('phase4-degraded');
    if (el) el.style.display = on ? 'block' : 'none';
  }

  async function refresh() {
    try {
      var fn = (typeof ocApi === 'function') ? ocApi : null;
      var data;
      if (fn) {
        data = await fn('/api/v1/phase4/status');
      } else {
        var r = await fetch('/api/v1/phase4/status', { credentials: 'same-origin' });
        data = await r.json();
      }
      if (!data || typeof data !== 'object') {
        // canon 7:非物件 → 全 grey + degraded,絕不假 green
        MODULES.forEach(function (m) { applyLight(m, 'grey'); });
        showDegraded(true);
        return;
      }
      MODULES.forEach(function (m) { applyLight(m, data[m]); });
      showDegraded(!!data.degraded);
      // 順帶刷各卡內容(loader 於卡片注入後定義;未定義則 guard 略過,不崩)
      if (typeof window.loadTeacherCard === 'function') {
        try { window.loadTeacherCard(); } catch (e) { /* fail-soft */ }
      }
      if (typeof window.loadDl3Card === 'function') {
        try { window.loadDl3Card(); } catch (e) { /* fail-soft */ }
      }
      if (typeof window.loadNewsCard === 'function') {
        try { window.loadNewsCard(); } catch (e) { /* fail-soft */ }
      }
    } catch (e) {
      // Fail-closed:任何錯誤 → 全 grey + degraded 橫幅
      MODULES.forEach(function (m) { applyLight(m, 'grey'); });
      showDegraded(true);
    }
  }

  // ═══ 輪詢生命週期(僅可見時運行;幂等:已在跑則不重建,pause 清後 resume 重啟)═══
  // 存下兩個 host interval id(30s status + 10s teacher);linucb 內部 interval 不在此列(清不到)。
  function startPolling() {
    if (statusTimer == null) {
      statusTimer = setInterval(refresh, 30000);  // 30s — 全局燈 + 各卡刷新
    }
    if (teacherTimer == null) {
      // Teacher 卡單獨 10s 快刷(Claude 反饋循環更新頻繁;verbatim tab-phase4.html lines 417-421)
      teacherTimer = setInterval(function () {
        if (typeof window.loadTeacherCard === 'function') {
          try { window.loadTeacherCard(); } catch (e) { /* fail-soft */ }
        }
      }, 10000);
    }
  }
  function stopPolling() {
    if (statusTimer != null) { clearInterval(statusTimer); statusTimer = null; }
    if (teacherTimer != null) { clearInterval(teacherTimer); teacherTimer = null; }
  }

  // ═══ shell router 契約:render / resume / pause(second-adapter 擴充點)═══
  // render:建骨架 + 逐一注入 4 卡 + 啟 host poller(存兩 interval id);built guard 只首渲一次
  //   (雙渲染=linucb 內部 interval 跑兩份,故 guard 為硬防線)。立即 refresh 屬 resume(visibility 語義)。
  function renderPhase4View(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    host.innerHTML = SKELETON;
    built = true;
    // 逐一 fetch 注入 4 卡 + 重跑內嵌 script(verbatim card-loading pattern)
    loadTeacherSlot();
    loadLinucbSlot();
    loadNewsSlot();
    loadDl3Slot();
    // 啟 host poller(30s + 10s),存 interval id 供 pause 清
    startPolling();
  }
  // resume:view 顯示 → 立即拉一次 status(鏡像顯示即刷新)+ 幂等重啟 poller(pause 清後重建)。
  function resumePhase4View() {
    if (!built) return;
    refresh();
    startPolling();
  }
  // pause:view 隱藏 → 停兩個 host interval(freshness/safety:隱藏不得續打後端)。
  //   linucb 內部 interval 清不到(closure 私有),與 legacy iframe 行為對等(見 MODULE_NOTE ⑤)。
  function pausePhase4View() {
    stopPolling();
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;stable host / 唯一擴充點)。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['phase4'] = { render: renderPhase4View, resume: resumePhase4View, pause: pausePhase4View };
  // 具名導出(task 契約:renderPhase4View / pausePhase4View / resumePhase4View 可被引用)。
  window.renderPhase4View = renderPhase4View;
  window.resumePhase4View = resumePhase4View;
  window.pausePhase4View = pausePhase4View;
})();
