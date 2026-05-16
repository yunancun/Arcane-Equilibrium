/**
 * 玄衡 GUI DOM Injection
 * 玄衡 GUI DOM 注入
 *
 * MODULE_NOTE (EN): Extracted from app.js (FIX-08 file size).
 * MODULE_NOTE (中): 從 app.js 提取（FIX-08 文件大小）。
 */

"use strict";

// ── DOM 注入：動態建立 GUI 各區块 / DOM injection: dynamically create GUI sections ──

function ensureGuiEnhancements() {
  const pageShell = document.querySelector(".page-shell");
  if (!pageShell) return;

  const topbarSubtle = document.querySelector(".topbar p");
  if (topbarSubtle) topbarSubtle.textContent = "RC2 控制台 · 玄衡受保護控制面 / OpenClaw services + Bybit venue adapter";

  // 更新表格头 / Update table headers
  const tableHeaders = [
    zhEnPrimary("產品族", "Product Family"),
    zhEnPrimary("交易所事實", "Exchange Fact"),
    zhEnPrimary("賬户事實", "Account Fact"),
    zhEnPrimary("已啟用", "Enabled"),
    zhEnPrimary("可见", "Visible"),
    zhEnPrimary("模式", "Mode"),
    zhEnPrimary("能力", "Capability"),
    zhEnPrimary("執行", "Execution")
  ];
  document.querySelectorAll("table thead th").forEach((th, idx) => {
    if (tableHeaders[idx]) th.innerHTML = tableHeaders[idx];
  });

  // 更新 summary grid 標簽 / Update summary grid labels
  const summaryTexts = [
    zhEnPrimary("全局模式", "Global Mode"),
    zhEnPrimary("執行權限", "Execution Authority"),
    zhEnPrimary("Demo 状态", "Demo State"),
    zhEnPrimary("快照", "Snapshot"),
    zhEnPrimary("Runtime 快照", "Runtime Snapshot"),
    zhEnPrimary("仍受保護", "Runtime Protected")
  ];
  document.querySelectorAll("#summaryGrid .summary-label").forEach((node, index) => {
    if (summaryTexts[index]) node.innerHTML = summaryTexts[index];
  });

  // 更新快捷動作按钮 / Update quick action buttons
  const actionButtonLabels = {
    refresh: ["刷新概览", "refresh overview"],
    validate: ["驗證 Demo 前提", "validate demo gates"],
    "set-demo-mode": ["切到 Demo Reserved", "global demo mode"],
    "enable-spot": ["開啟 Spot / 現货產品配置", "spot product config"],
    "arm-demo": ["執行 Demo Arm", "move to armed_but_closed"],
    bundle: ["安全復核打包", "multi-step guarded recheck"]
  };
  document.querySelectorAll("[data-action]").forEach((btn) => {
    const name = btn.dataset.action;
    if (actionButtonLabels[name]) {
      btn.innerHTML = `${actionButtonLabels[name][0]}<span class="button-sub">${actionButtonLabels[name][1]}</span>`;
    }
  });

  // 更新動作摘要 / Update action summary labels
  const actionTexts = [
    zhEnPrimary("最近動作", "Last Action"),
    zhEnPrimary("結果", "Result"),
    zhEnPrimary("状态版本", "State Revision"),
    zhEnPrimary("審計引用", "Audit Ref")
  ];
  document.querySelectorAll("#actionSummaryGrid .summary-label").forEach((node, index) => {
    if (actionTexts[index]) node.innerHTML = actionTexts[index];
  });

  // ── 注入：關键概念提示 / Inject: key concept hints ─────────────────────────
  if (!document.getElementById("guiConceptHints")) {
    const hintCard = document.createElement("section");
    hintCard.className = "card glossary-card";
    hintCard.id = "guiConceptHints";
    hintCard.innerHTML = `
      <details class="raw-toggle">
        <summary>${zhEnPrimary("關键概念提示（按需展開）", "Key Concept Hints")}</summary>
        <div class="glossary-wrap" style="padding:16px;">
          ${annotateGlossary("事實", "Facts", "先看交易所、賬户、runtime 實際返回了什么。事實是「真實情况」，不是你点按钮点出来的權限。", "Facts are the actual returned conditions, not permissions granted by a button.")}
          ${annotateGlossary("權限配置", "Control Permission", "再看你在控制面配置了什么，例如 demo reserved、spot shadow。這些是「允許系統往下判斷」，不是「马上能執行」。", "Control permissions allow the system to continue guarded evaluation; they are not immediate execution authority.")}
          ${annotateGlossary("状态推進", "State Progress", "最后看 demo validate、demo arm 這類步驟。它们表示系統流程往前走了，但仍可能保持封閉。", "State progress means the workflow moved forward, but it can still remain closed.")}
          ${annotateGlossary("最重要的一句", "Most Important Rule", "看得见 ≠ 被允許；被允許繼續判斷 ≠ 能執行；demo ≠ live。", "Visible is not allowed; allowed to continue is not executable; demo is not live.")}
        </div>
      </details>`;
    const hero = document.querySelector(".hero-card");
    if (hero) hero.after(hintCard);
  }

  // ── 注入：運行模式控制 + 經营摘要（双列）/ Inject: runtime mode control + business summary ──
  if (!document.getElementById("runtimeModeSection")) {
    const grid = document.createElement("section");
    grid.className = "grid two-up injected-grid";
    grid.id = "modeBizGrid";
    grid.innerHTML = `
      <section class="card" id="runtimeModeSection">
        <div class="card-header-row">
          <div>
            <h2>${zhEnPrimary("運行模式控制", "Runtime Mode Control")}</h2>
            <p class="subtle">受保護模式切换骨架；當前只開放低風險 guarded 動作，live 仍锁定。</p>
          </div>
        </div>
        <div class="mode-grid">
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("階段標簽", "Stage Label")}</span><strong id="modeStageLabel">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("能力状态", "Capability State")}</span><strong id="modeCapabilityState">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("Demo Arm Gate", "Demo Arm Gate")}</span><strong id="modeDemoArmGate">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("Demo Enable Gate", "Demo Enable Gate")}</span><strong id="modeDemoEnableGate">-</strong></div>
        </div>
        <div class="mode-actions">
          <button data-action="set-demo-mode">切到 Demo Reserved<span class="button-sub">global demo mode</span></button>
          <button data-action="enable-spot">開啟 Spot<span class="button-sub">spot product config</span></button>
          <button data-action="validate">驗證 Demo 前提<span class="button-sub">validate demo gates</span></button>
          <button data-action="arm-demo">執行 Demo Arm<span class="button-sub">move to armed_but_closed</span></button>
          <button class="button-muted" disabled>观測模式<span class="button-sub">Observe Only · later</span></button>
          <button class="button-muted" disabled>Live 模式<span class="button-sub">Live Mode · locked</span></button>
        </div>
        <div class="mode-note">先決定"系統要不要進入 demo/spot 的受保護流程"，再決定"現在是否滿足繼續前進的條件"。這不是真實執行權限開關區。</div>
      </section>

      <section class="card" id="businessSummarySection">
        <div class="card-header-row">
          <div>
            <h2>${zhEnPrimary("經营与收益摘要", "Business & Income Summary")}</h2>
            <p class="subtle">每日 PnL 指標 + 歷史條目。来自 /system/business/summary。</p>
          </div>
        </div>
        <div class="summary-grid business-grid">
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("已實現盈亏", "Realized PnL")}</span><strong id="bizRealizedPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("未實現盈亏", "Unrealized PnL")}</span><strong id="bizUnrealizedPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("毛盈亏", "Gross PnL")}</span><strong id="bizGrossPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("總成本", "Total Cost")}</span><strong id="bizTotalCost">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("净經营盈亏", "Net Operating PnL")}</span><strong id="bizNetOperatingPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("業務事件數", "Business Event Count")}</span><strong id="bizEventCount">-</strong></div>
        </div>
        <div class="biz-totals">
          <span>${zhEnPrimary("費用條目", "Cost entries")}: <strong id="bizCostCount">-</strong></span>
          <span>${zhEnPrimary("PnL 條目", "PnL entries")}: <strong id="bizPnlCount">-</strong></span>
          <span>${zhEnPrimary("業務事件", "Event entries")}: <strong id="bizEvtCount">-</strong></span>
        </div>
        <div class="mode-note">當前来自 /system/business/summary，包含每日 PnL 快照 + 最近歷史條目。</div>
      </section>`;
    const firstGrid = document.querySelector(".page-shell > .grid.two-up");
    if (firstGrid) firstGrid.before(grid);
  }

  // ── 注入：產品族配置區（只读摘要卡片）/ Inject: product family config summary cards ──
  if (!document.getElementById("productFamilyConfigSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "productFamilyConfigSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("產品族配置", "Product Family Configuration")}</h2>
          <p class="subtle">當前状态快照。點擊下方設置台可修改。/ Current state snapshot. Use the config console below to modify.</p>
        </div>
      </div>
      <div class="summary-grid business-grid config-family-grid">
        ${Object.entries(PRODUCT_FAMILY_CONFIG_IDS).map(([family, ids]) => `
          <div class="summary-item config-family-card">
            <span class="summary-label">${zhEnPrimary(PRODUCT_FAMILY_LABELS[family] || family, family)}</span>
            <strong id="${ids.summary}">-</strong>
            <div id="${ids.meta}" class="family-card-meta">-</div>
          </div>`).join("")}
      </div>`;
    const productFactsCard = Array.from(document.querySelectorAll(".page-shell > .card"))
      .find((node) => node.querySelector("h2")?.textContent.includes("產品族事實"));
    if (productFactsCard) productFactsCard.before(card);
  }

  // ── 注入：產品族配置設置台（可交互）/ Inject: product family config console (interactive) ──
  if (!document.getElementById("pfEditorSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "pfEditorSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("產品族配置設置台", "Product Family Config Console")}</h2>
          <p class="subtle">交互式配置每個產品族的控制開關。变更会調用 /control/product-family/{family}/config。
            / Interactive controls for each product family. Changes call /control/product-family/{family}/config.</p>
        </div>
      </div>
      <div id="pfEditorContainer" class="pf-editor-grid">
        <div class="muted-row">等待載入 / Loading...</div>
      </div>
      <div class="mode-note">
        <strong>安全提示 / Safety:</strong> mode_switch 只允許 disabled / observe_only / shadow_only。
        live 相關模式不在當前階段開放。/ live-related modes are NOT available at this stage.
      </div>`;
    const configCard = document.getElementById("productFamilyConfigSection");
    if (configCard) configCard.after(card);
  }

  // ── 注入：長期開關预留 / Inject: long-term switch preset ───────────────────
  if (!document.getElementById("longTermSwitchSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "longTermSwitchSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("長期開關预留", "Long-Term Switch Preset")}</h2>
          <p class="subtle">這裡只预留長期会用到的結構和名字，不在當前章節開放真實高權限能力。</p>
        </div>
      </div>
      <div class="summary-grid switch-grid" id="longTermSwitchGrid"></div>
      <div class="mode-note">當前這一块的定位是：先把未來一定会出現的總開關和安全開關位置固定下来，避免后面临時加入口。現在全部只做展示、锁定或预留。</div>`;
    const pfEditor = document.getElementById("pfEditorSection");
    if (pfEditor) pfEditor.after(card);
  }

  // ── 注入：收益录入面板 / Inject: income & cost entry panel ─────────────────
  if (!document.getElementById("incomeEntrySection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "incomeEntrySection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("收益与成本录入", "Income & Cost Entry")}</h2>
          <p class="subtle">手動录入費用條目和 PnL 更新。數據会累計到每日經营摘要。
            / Manually record cost entries and PnL updates. Data accumulates in the daily business summary.</p>
        </div>
      </div>
      <div class="grid two-up entry-grid">
        <div class="entry-form-card">
          <h3 class="entry-form-title">${zhEnPrimary("費用录入", "Cost Entry")}</h3>
          <div class="form-row">
            <label class="form-label">金额 / Amount (USDT)</label>
            <input type="number" id="costAmount" step="0.0001" placeholder="0.0000" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">類別 / Category</label>
            <select id="costCategory" class="form-input">
              <option value="manual">manual（手動）</option>
              <option value="ai_api">ai_api（AI API 費用）</option>
              <option value="exchange_fee">exchange_fee（交易所手續費）</option>
              <option value="slippage">slippage（滑点）</option>
              <option value="infra">infra（基礎設施）</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">備注 / Note</label>
            <input type="text" id="costNote" placeholder="可選 / optional" class="form-input">
          </div>
          <button id="submitCostEntry" class="entry-submit-btn">
            录入費用 / Record Cost
            <span class="button-sub">POST /input/cost</span>
          </button>
        </div>

        <div class="entry-form-card">
          <h3 class="entry-form-title">${zhEnPrimary("PnL 录入", "PnL Entry")}</h3>
          <div class="form-row">
            <label class="form-label">類型 / Type</label>
            <select id="pnlType" class="form-input">
              <option value="realized">realized（已實現）</option>
              <option value="unrealized">unrealized（未實現）</option>
              <option value="manual_adjustment">manual_adjustment（手動調整）</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">已實現盈亏增量 / Realized PnL delta (USDT)</label>
            <input type="number" id="pnlRealized" step="0.0001" placeholder="0.0000" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">未實現盈亏（快照）/ Unrealized PnL snapshot (USDT)</label>
            <input type="number" id="pnlUnrealized" step="0.0001" placeholder="0.0000" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">標的 / Symbol (可選)</label>
            <input type="text" id="pnlSymbol" placeholder="e.g. BTCUSDT" class="form-input">
          </div>
          <button id="submitPnlEntry" class="entry-submit-btn">
            录入 PnL / Record PnL
            <span class="button-sub">POST /input/pnl-entry</span>
          </button>
        </div>
      </div>

      <div class="entries-history">
        <div class="entries-col">
          <h4 class="entries-col-title">${zhEnPrimary("最近費用記錄", "Recent Cost Entries")}</h4>
          <div id="costEntriesList" class="entry-list">等待載入 / Loading...</div>
        </div>
        <div class="breakdown-col">
          <h4 class="entries-col-title">${zhEnPrimary("成本分解", "Cost Breakdown")}</h4>
          <div id="costBreakdownGrid" class="breakdown-grid">-</div>
        </div>
      </div>

      <div class="entries-history">
        <div class="entries-col full-width">
          <h4 class="entries-col-title">${zhEnPrimary("最近 PnL 記錄", "Recent PnL Entries")}</h4>
          <div id="pnlEntriesList" class="entry-list">等待載入 / Loading...</div>
        </div>
      </div>`;

    const longTermSection = document.getElementById("longTermSwitchSection");
    if (longTermSection) longTermSection.after(card);
  }

  // ── 注入：系統設置台 / Inject: system settings console ─────────────────────
  if (!document.getElementById("settingsConsoleSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "settingsConsoleSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("系統設置台", "System Settings Console")}</h2>
          <p class="subtle">調整全局風險策略、Demo 确認要求等系統级開關。所有变更有二次确認保護。
            / Adjust global risk policy, demo confirmation requirement, etc. All changes require second confirmation.</p>
        </div>
      </div>
      <div class="settings-grid">
        <div class="settings-block">
          <h4 class="settings-block-title">${zhEnPrimary("風險策略", "Risk Policy")}</h4>
          <div class="settings-row">
            <label class="settings-label">風險策略開關 / Risk Policy Switch</label>
            <select id="settingsRiskSwitch" class="form-input settings-select">
              <option value="default_guarded">default_guarded（默認受保護）</option>
              <option value="manual_blocked">manual_blocked（手動阻斷）</option>
            </select>
          </div>
          <div class="settings-row">
            <label class="settings-label">當前風險包絡状态 / Current Risk Envelope State</label>
            <span id="settingsRiskEnvelopeState">-</span>
          </div>
          <button id="applyRiskSwitch" class="settings-apply-btn">
            應用風險策略 / Apply Risk Policy
            <span class="button-sub">PUT control_plane.risk_envelope.risk_policy_switch</span>
          </button>
        </div>

        <div class="settings-block">
          <h4 class="settings-block-title">${zhEnPrimary("Demo 与學習開關", "Demo & Learning Switches")}</h4>
          <div class="settings-row">
            <label class="settings-label">Demo 操作員确認要求 / Demo Operator Ack Required</label>
            <input type="checkbox" id="settingsDemoAck" class="settings-checkbox" checked>
          </div>
          <div class="settings-row">
            <label class="settings-label">學習實驗需人工審批 / Learning Experiments Require Approval</label>
            <input type="checkbox" id="settingsLearningApproval" class="settings-checkbox" checked>
          </div>
          <button id="applyDemoLearningSettings" class="settings-apply-btn">
            應用 Demo/Learning 設置 / Apply Demo/Learning Settings
            <span class="button-sub">PUT control_plane.demo_control + learning_state</span>
          </button>
        </div>
      </div>
      <div class="mode-note">
        ⚠️ 風險策略 manual_blocked 会立即阻斷所有執行權限判斷。生產環境慎用。
        / ⚠️ Risk policy manual_blocked immediately blocks all execution authority. Use carefully in production.
      </div>`;

    const incomeSection = document.getElementById("incomeEntrySection");
    if (incomeSection) incomeSection.after(card);
  }

  // ── 注入：學習駕駛舱 / Inject: Learning Cockpit ─────────────────────────────
  // L 章核心 GUI 區域：四標簽页（觀察 / 經驗 / 假設 / 實驗）+ 录入表單 + 審批按钮。
  // L-chapter core GUI section: four tabs (observations / lessons / hypotheses / experiments)
  // + input forms + approval buttons.
  if (!document.getElementById("learningCockpitSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "learningCockpitSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("學習駕駛舱", "Learning Cockpit")}</h2>
          <p class="subtle">L 章：觀察流 / 經驗記憶 / 假設佇列 / 實驗佇列。所有記錄區分事實、推斷、假設（原則 8）。
            / L-Chapter: Observation Feed / Lessons Memory / Hypothesis Queue / Experiment Queue. All entries tagged with fact/inference/hypothesis (Principle 8).</p>
        </div>
      </div>
      <div class="learning-tabs">
        <button class="learning-tab active" data-tab="observations">${zhEnPrimary("觀察流", "Observations")}</button>
        <button class="learning-tab" data-tab="lessons">${zhEnPrimary("經驗記憶", "Lessons")}</button>
        <button class="learning-tab" data-tab="hypotheses">${zhEnPrimary("假設佇列", "Hypotheses")}</button>
        <button class="learning-tab" data-tab="experiments">${zhEnPrimary("實驗佇列", "Experiments")}</button>
        <button class="learning-tab" data-tab="reviewQueue">${zhEnPrimary("審核佇列", "Review Queue")}</button>
      </div>

      <div class="learning-tab-content active" id="tabObservations">
        <div class="entry-form-card learning-form">
          <h4 class="entry-form-title">${zhEnPrimary("录入觀察", "Record Observation")}</h4>
          <div class="form-row">
            <label class="form-label">標題 / Title</label>
            <input type="text" id="obsTitle" placeholder="簡要描述 / Brief description" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">详情 / Detail</label>
            <textarea id="obsDetail" rows="2" placeholder="完整觀察內容 / Full observation" class="form-input form-textarea"></textarea>
          </div>
          <div class="form-row form-row-inline">
            <div>
              <label class="form-label">類別 / Category</label>
              <select id="obsCategory" class="form-input">
                <option value="market">market（市场）</option>
                <option value="execution">execution（執行）</option>
                <option value="cost">cost（成本）</option>
                <option value="system">system（系統）</option>
                <option value="strategy">strategy（策略）</option>
                <option value="other">other（其他）</option>
              </select>
            </div>
            <div>
              <label class="form-label">置信度 / Confidence</label>
              <select id="obsConfidence" class="form-input">
                <option value="fact">fact（事實）</option>
                <option value="inference">inference（推斷）</option>
                <option value="hypothesis">hypothesis（假設）</option>
              </select>
            </div>
          </div>
          <button id="submitObservation" class="entry-submit-btn">
            录入觀察 / Record Observation
            <span class="button-sub">POST /input/observation</span>
          </button>
        </div>
        <div id="observationsList" class="learning-records-list">等待載入 / Loading...</div>
      </div>

      <div class="learning-tab-content" id="tabLessons">
        <div class="entry-form-card learning-form">
          <h4 class="entry-form-title">${zhEnPrimary("录入經驗", "Record Lesson")}</h4>
          <div class="form-row">
            <label class="form-label">標題 / Title</label>
            <input type="text" id="lessonTitle" placeholder="經驗概要 / Lesson summary" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">详情 / Detail</label>
            <textarea id="lessonDetail" rows="2" placeholder="經驗详情 / Full lesson" class="form-input form-textarea"></textarea>
          </div>
          <div class="form-row form-row-inline">
            <div>
              <label class="form-label">類別 / Category</label>
              <select id="lessonCategory" class="form-input">
                <option value="market_pattern">market_pattern（市场規律）</option>
                <option value="cost_insight">cost_insight（成本洞察）</option>
                <option value="execution_quality">execution_quality（執行质量）</option>
                <option value="strategy">strategy（策略）</option>
                <option value="system">system（系統）</option>
                <option value="other">other（其他）</option>
              </select>
            </div>
            <div>
              <label class="form-label">置信度 / Confidence</label>
              <select id="lessonConfidence" class="form-input">
                <option value="fact">fact（事實）</option>
                <option value="inference">inference（推斷）</option>
                <option value="hypothesis">hypothesis（假設）</option>
              </select>
            </div>
          </div>
          <button id="submitLesson" class="entry-submit-btn">
            录入經驗 / Record Lesson
            <span class="button-sub">POST /input/lesson</span>
          </button>
        </div>
        <div id="lessonsList" class="learning-records-list">等待載入 / Loading...</div>
      </div>

      <div class="learning-tab-content" id="tabHypotheses">
        <div class="entry-form-card learning-form">
          <h4 class="entry-form-title">${zhEnPrimary("提出假設", "Propose Hypothesis")}</h4>
          <div class="form-row">
            <label class="form-label">標題 / Title</label>
            <input type="text" id="hypTitle" placeholder="假設名稱 / Hypothesis name" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">描述 / Description</label>
            <textarea id="hypDescription" rows="2" placeholder="假設描述 / Description" class="form-input form-textarea"></textarea>
          </div>
          <div class="form-row">
            <label class="form-label">可檢驗预測 / Testable Prediction</label>
            <textarea id="hypPrediction" rows="2" placeholder="什么結果能證實或否定這個假設 / What outcome confirms or denies" class="form-input form-textarea"></textarea>
          </div>
          <button id="submitHypothesis" class="entry-submit-btn">
            提出假設 / Propose Hypothesis
            <span class="button-sub">POST /input/hypothesis (confidence_level = hypothesis)</span>
          </button>
        </div>
        <div id="hypothesesList" class="learning-records-list">等待載入 / Loading...</div>
      </div>

      <div class="learning-tab-content" id="tabExperiments">
        <div class="entry-form-card learning-form">
          <h4 class="entry-form-title">${zhEnPrimary("提出實驗", "Propose Experiment")}</h4>
          <div class="form-row">
            <label class="form-label">關联假設 ID / Hypothesis ID</label>
            <input type="text" id="expHypothesisId" placeholder="hyp:..." class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">標題 / Title</label>
            <input type="text" id="expTitle" placeholder="實驗名稱 / Experiment name" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">描述 / Description</label>
            <textarea id="expDescription" rows="2" placeholder="實驗描述 / Description" class="form-input form-textarea"></textarea>
          </div>
          <div class="form-row">
            <label class="form-label">方法 / Method</label>
            <textarea id="expMethod" rows="2" placeholder="如何驗證 / How to test" class="form-input form-textarea"></textarea>
          </div>
          <div class="form-row">
            <label class="form-label">成功標准 / Success Criteria</label>
            <input type="text" id="expSuccessCriteria" placeholder="什么結果算成功 / What counts as success" class="form-input">
          </div>
          <button id="submitExperiment" class="entry-submit-btn">
            提出實驗 / Propose Experiment
            <span class="button-sub">POST /input/experiment</span>
          </button>
        </div>
        <div id="experimentsList" class="learning-records-list">等待載入 / Loading...</div>
      </div>

      <div class="learning-tab-content" id="tabReviewQueue">
        <div class="review-scan-bar">
          <button class="auto-scan-btn" data-scan="observations">
            掃描觀察 / Scan Observations
            <span class="button-sub">POST /learning/auto/scan-observations</span>
          </button>
          <button class="auto-scan-btn" data-scan="lessons">
            掃描經驗 / Scan Lessons
            <span class="button-sub">POST /learning/auto/scan-lessons</span>
          </button>
          <button class="auto-scan-btn" data-scan="hypotheses">
            掃描假設 / Scan Hypotheses
            <span class="button-sub">POST /learning/auto/scan-hypotheses</span>
          </button>
        </div>
        <div id="reviewQueueList" class="learning-records-list">等待載入 / Loading...</div>
        <div id="reviewRecentDecided" class="learning-records-list"></div>
      </div>

      <div class="learning-stats" id="learningStats">
        <span>${zhEnPrimary("觀察", "Obs")}: <strong id="lrnObsCount">0</strong></span>
        <span>${zhEnPrimary("經驗", "Lessons")}: <strong id="lrnLesCount">0</strong></span>
        <span>${zhEnPrimary("假設", "Hyp")}: <strong id="lrnHypCount">0</strong></span>
        <span>${zhEnPrimary("實驗", "Exp")}: <strong id="lrnExpCount">0</strong></span>
        <span>${zhEnPrimary("待審批", "Pending")}: <strong id="lrnPendingCount">0</strong></span>
      </div>`;

    const settingsSection = document.getElementById("settingsConsoleSection");
    if (settingsSection) settingsSection.after(card);
  }

  // ── 注入：净 PnL 仪表盤 / Inject: Net PnL Dashboard ────────────────────────
  // L 章 Net PnL 模块：周期趋势、成本分解、快照保存。
  // L-chapter Net PnL module: period trends, cost breakdown, snapshot saving.
  if (!document.getElementById("netPnlDashboardSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "netPnlDashboardSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("净 PnL 仪表盤", "Net PnL Dashboard")}</h2>
          <p class="subtle">含所有成本分解的盈亏趋势追踪。来自 /learning/net-pnl。
            / PnL trend tracking with full cost breakdown. From /learning/net-pnl.</p>
        </div>
      </div>
      <div class="summary-grid business-grid">
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("已實現盈亏", "Realized PnL")}</span><strong id="npRealizedPnl">-</strong></div>
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("未實現盈亏", "Unrealized PnL")}</span><strong id="npUnrealizedPnl">-</strong></div>
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("毛盈亏", "Gross PnL")}</span><strong id="npGrossPnl">-</strong></div>
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("總成本", "Total Cost")}</span><strong id="npTotalCost">-</strong></div>
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("净經营盈亏", "Net Operating PnL")}</span><strong id="npNetPnl" class="pnl-highlight">-</strong></div>
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("周期快照數", "Period Snapshots")}</span><strong id="npSnapshotCount">-</strong></div>
      </div>
      <div class="net-pnl-actions">
        <div class="form-row form-row-inline">
          <div>
            <label class="form-label">周期標簽 / Period Label</label>
            <input type="text" id="periodLabel" placeholder="e.g. 2026-03-26" class="form-input">
          </div>
          <button id="savePeriodSnapshot" class="entry-submit-btn">
            保存快照 / Save Period Snapshot
            <span class="button-sub">POST /input/pnl-period-snapshot</span>
          </button>
        </div>
      </div>
      <div class="entries-history">
        <div class="entries-col">
          <h4 class="entries-col-title">${zhEnPrimary("成本分解", "Cost Breakdown")}</h4>
          <div id="npCostBreakdown" class="breakdown-grid">-</div>
        </div>
        <div class="entries-col">
          <h4 class="entries-col-title">${zhEnPrimary("周期趋势", "Period Trend")}</h4>
          <div id="npTrendList" class="entry-list">-</div>
        </div>
      </div>`;

    const learningSection = document.getElementById("learningCockpitSection");
    if (learningSection) learningSection.after(card);
  }

  // ── 注入：确認弹窗 / Inject: confirmation modal ─────────────────────────────
  if (!document.getElementById("confirmModal")) {
    const modal = document.createElement("div");
    modal.id = "confirmModal";
    modal.className = "confirm-modal hidden";
    modal.innerHTML = `
      <div class="confirm-modal-backdrop" data-close-modal="true"></div>
      <div class="confirm-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="confirmModalTitle">
        <div class="confirm-modal-header">
          <h3 id="confirmModalTitle">關键動作确認</h3>
          <button class="confirm-close" data-close-modal="true">×</button>
        </div>
        <div class="confirm-modal-body">
          <div id="confirmModalSubtitle" class="confirm-subtitle">-</div>
          <div class="confirm-block">
            <div class="confirm-label">風險說明 / Risk</div>
            <div id="confirmModalRisk">-</div>
          </div>
          <div class="confirm-block">
            <div class="confirm-label">后果說明 / Consequence</div>
            <div id="confirmModalConsequence">-</div>
          </div>
          <div class="confirm-note">請确認你理解該動作不會直接開放真實 live execution，但会推進控制状态或影响可见控制結果。</div>
        </div>
        <div class="confirm-modal-footer">
          <button class="button-muted confirm-cancel" data-close-modal="true">取消 / Cancel</button>
          <button id="confirmModalProceed">确認執行 / Confirm</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }

  function applyDevelopmentSupportVisibility(enabled) {
    const runtimeMode = document.getElementById("runtimeModeSection");
    if (runtimeMode) runtimeMode.style.display = enabled ? "" : "none";
  }
  applyDevelopmentSupportVisibility(
    typeof ocReadCachedDevelopmentSupportMode === "function"
      ? ocReadCachedDevelopmentSupportMode()
      : false
  );
  if (!window.__ocDevSupportLegacyDashboardBound && typeof ocListenDevelopmentSupportMode === "function") {
    window.__ocDevModeLegacyDashboardBound = true;
    window.__ocDevSupportLegacyDashboardBound = true;
    ocListenDevelopmentSupportMode(applyDevelopmentSupportVisibility);
  }
  if (typeof ocFetchDevelopmentSupportMode === "function") {
    ocFetchDevelopmentSupportMode().then(applyDevelopmentSupportVisibility);
  }
}
