let inMemoryToken = "";

const CRITICAL_ACTIONS = {
  "set-demo-mode": {
    title: "切换到 Demo Reserved",
    subtitle: "Set global execution mode to demo_reserved",
    risk: "这一步只是把系统从“完全不走 demo 流程”，改成“允许继续做 demo 相关判断”。它不是下单，不是开启 live，也不是马上获得执行权。",
    consequence: "点完后，系统只会进入“可以继续做 demo 检查”的状态。你之后仍然还要 validate、arm，甚至 future enable；所以这一步只是打开下一道门，不是直接放权。"
  },
  "enable-spot": {
    title: "开启 Spot / 现货产品配置",
    subtitle: "Enable spot family in shadow mode",
    risk: "这一步只影响现货产品族。它会让 spot / 现货从“关闭/仅展示”进入 shadow 控制状态。shadow 的意思是：用于观察、验证、看控制结果，不是实际成交。",
    consequence: "点完后，只会改变现货这一类产品的控制展示和 gate 结果，不会影响其它产品族，也不会直接让账户获得真实现货下单权限。"
  },
  validate: {
    title: "验证 Demo 前提",
    subtitle: "Validate demo prerequisites and gates",
    risk: "这一步只是做检查。它会重新判断系统现在是否满足 demo 的前置条件。它不会切模式，也不会推进 demo 主状态。",
    consequence: "点完后，你主要会看到 gate 结果变了，比如“可以继续”还是“还不满足条件”。它不会直接提高执行权限。"
  },
  "arm-demo": {
    title: "执行 Demo Arm",
    subtitle: "Move demo state to armed_but_closed",
    risk: "这是 demo 流程里更关键的一步。它表示系统已经通过前置检查，进入“已准备好下一步，但仍然封闭”的状态。",
    consequence: "点完后，demo 会更接近后续 enable，但仍然不能直接执行。你可以把它理解成“已经准备好了，但保险还没真正打开”。"
  },
  bundle: {
    title: "执行安全复核打包",
    subtitle: "Run safe recheck bundle",
    risk: "这一步会把多项检查和刷新一起跑一遍。它适合在你想让整页判断一起更新时使用。",
    consequence: "点完后，readiness、gate、audit 等多个区域可能一起刷新。它本身不是切模式，也不是直接放权。"
  }
};

const PRODUCT_FAMILY_LABELS = {
  spot: "spot / 现货",
  margin: "margin / 保证金",
  perp_linear: "perp_linear / 线性永续",
  perp_inverse: "perp_inverse / 反向永续",
  options: "options / 期权",
  other_derivatives_reserved: "other_derivatives_reserved / 其他衍生品（预留）"
};

const PRODUCT_FAMILY_CONFIG_IDS = {
  spot: { summary: "cfgSpotSummary", meta: "cfgSpotMeta" },
  margin: { summary: "cfgMarginSummary", meta: "cfgMarginMeta" },
  perp_linear: { summary: "cfgLinearPerpSummary", meta: "cfgLinearPerpMeta" },
  perp_inverse: { summary: "cfgInversePerpSummary", meta: "cfgInversePerpMeta" },
  options: { summary: "cfgOptionsSummary", meta: "cfgOptionsMeta" },
  other_derivatives_reserved: { summary: "cfgOtherDerivativesSummary", meta: "cfgOtherDerivativesMeta" }
};

function headers() {
  return {
    Authorization: `Bearer ${inMemoryToken}`,
    "Content-Type": "application/json"
  };
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function safeText(value) {
  return value === undefined || value === null ? "-" : String(value);
}

function variantForState(value) {
  const normalized = String(value || "").toLowerCase();
  if (["passed", "healthy", "ready", "fresh", "complete", "shadow_only", "shadow_control_ready", "success", "true", "allowed"].includes(normalized)) return "good";
  if (["blocked", "disabled", "down", "missing", "failed", "unavailable", "unknown", "false"].includes(normalized)) return "bad";
  if (["partial", "degraded", "demo_reserved", "demo_blocked", "armed_but_closed", "visible_only", "shadow_visible"].includes(normalized)) return "warn";
  return "neutral";
}

function booleanZh(value, trueText, falseText) {
  return value ? trueText : falseText;
}

function setConnectionStatus(text, variant = "neutral") {
  const node = document.getElementById("connectionStatus");
  node.textContent = text;
  node.className = `status-chip ${variant}`;
}

function setRuntimeModeBadge(text, variant = "neutral") {
  const node = document.getElementById("runtimeModeBadge");
  node.textContent = text;
  node.className = `status-chip ${variant}`;
}

function setActionSummary(name, result, revision, auditRef, hint, raw) {
  document.getElementById("actionSummaryName").textContent = safeText(name);
  const resultNode = document.getElementById("actionSummaryResult");
  resultNode.textContent = safeText(result);
  resultNode.className = `action-result-value ${variantForState(result)}`;
  document.getElementById("actionSummaryRevision").textContent = safeText(revision);
  document.getElementById("actionSummaryAudit").textContent = safeText(auditRef);
  document.getElementById("actionSummaryHint").textContent = safeText(hint);
  document.getElementById("actionResultBox").textContent = typeof raw === "string" ? raw : pretty(raw);
}

function summarizeActionResult(actionName, result) {
  const actionMap = {
    refresh: "刷新概览",
    validate: "验证 Demo",
    bundle: "安全复核打包",
    "set-demo-mode": "切到 Demo Reserved",
    "enable-spot": "开启 Spot / 现货产品配置",
    "arm-demo": "执行 Demo Arm"
  };

  const actionEnMap = {
    refresh: "refresh overview",
    validate: "validate demo",
    bundle: "safe recheck bundle",
    "set-demo-mode": "set demo reserved",
    "enable-spot": "enable spot config",
    "arm-demo": "arm demo"
  };

  const data = result?.data || {};
  let hint = "动作执行完成。";
  let helper = "Action completed.";

  if (actionName === "validate") {
    hint = `系统刚完成一次检查：前提 gate = ${safeText(data.demo_prerequisites_gate_state)}；Arm gate = ${safeText(data.demo_arm_gate_state)}。这表示“现在能不能继续走 demo 流程”，不是“现在能不能直接执行”。`;
    helper = `This checked whether demo can continue, not whether execution is already open.`;
  } else if (actionName === "arm-demo") {
    hint = `Demo 状态现在是：${safeText(data.demo_state_switch)}。简单理解：系统已经更接近下一步，但还没有真正放开执行。`;
    helper = `The system moved closer to the next step, but execution is still not open.`;
  } else if (actionName === "set-demo-mode") {
    hint = `系统已经接受“进入 Demo Reserved”这个配置。简单理解：以后可以继续做 demo 相关判断了，但这一步本身不等于获得执行权。`;
    helper = `Demo evaluation path is now allowed to continue, but no execution authority was opened by this step alone.`;
  } else if (actionName === "enable-spot") {
    hint = `系统已经接受现货产品配置修改。简单理解：现货这类产品现在会进入 shadow 控制展示，但并不等于账户已经能真实现货下单。`;
    helper = `Spot moved into shadow control display, but real spot trading authority is still separate.`;
  } else if (actionName === "bundle") {
    hint = `系统刚完成一轮统一复核刷新。简单理解：页面上的多个判断结果都可能更新了，但这一步本身不直接放权。`;
    helper = `Multiple checks were refreshed together, but no authority was directly opened.`;
  } else if (actionName === "refresh") {
    hint = "界面已刷新。";
    helper = "Dashboard refreshed.";
  }

  setActionSummary(
    `${actionMap[actionName] || actionName} / ${actionEnMap[actionName] || actionName}`,
    safeText(result.action_result),
    safeText(result.state_revision),
    safeText(result.audit_ref),
    `${hint} ${helper}`,
    result
  );
}

function zhEnPrimary(zh, en) {
  return `<span class="label-zh">${zh}</span><span class="label-en">${en}</span>`;
}

function annotateGlossary(termZh, termEn, noteZh, noteEn) {
  return `<div class="glossary-pill"><span class="glossary-term">${termZh}</span><span class="glossary-term-en">${termEn}</span><span class="glossary-note">${noteZh} / ${noteEn}</span></div>`;
}

function renderKvGrid(nodeId, items) {
  const node = document.getElementById(nodeId);
  node.innerHTML = items.map(([labelHtml, value]) => {
    const safeValue = safeText(value);
    return `<div class="kv-item"><dt>${labelHtml}</dt><dd><span class="status-chip ${variantForState(safeValue)}">${safeValue}</span></dd></div>`;
  }).join("");
}

function ensureGuiEnhancements() {
  const pageShell = document.querySelector(".page-shell");
  if (!pageShell) return;

  document.querySelector("label[for='tokenInput']")?.replaceChildren("访问令牌 / Bearer Token");
  document.getElementById("connectButton").textContent = "连接 / Connect";

  const topbarSubtle = document.querySelector(".topbar p");
  if (topbarSubtle) topbarSubtle.textContent = "RC2 控制台 · OpenClaw/Bybit 受保护控制面 / RC2 control console for guarded operations";

  const heroSubtle = document.querySelector(".hero-card .subtle");
  if (heroSubtle) heroSubtle.textContent = "高层状态、保护边界与 runtime snapshot 绑定情况。English helper text is intentionally lighter below.";

  const summaryLabels = document.querySelectorAll("#summaryGrid .summary-label");
  const summaryTexts = [
    zhEnPrimary("全局模式", "Global Mode"),
    zhEnPrimary("执行权限", "Execution Authority"),
    zhEnPrimary("Demo 状态", "Demo State"),
    zhEnPrimary("快照", "Snapshot"),
    zhEnPrimary("Runtime 快照", "Runtime Snapshot"),
    zhEnPrimary("仍受保护", "Runtime Protected")
  ];
  summaryLabels.forEach((node, index) => { if (summaryTexts[index]) node.innerHTML = summaryTexts[index]; });

  const cards = document.querySelectorAll(".page-shell > .card, .page-shell > .grid.two-up .card");
  cards.forEach((card) => {
    const h2 = card.querySelector("h2");
    if (!h2) return;
    const current = h2.textContent.trim();
    if (current.includes("来源上下文")) {
      h2.innerHTML = zhEnPrimary("来源上下文", "Source Context");
      card.querySelector(".subtle").textContent = "连接状态、完整性和 connector 角色分离。Small English hints stay secondary to reduce clutter.";
    }
    if (current.includes("健康摘要")) {
      h2.innerHTML = zhEnPrimary("健康摘要", "Health Summary");
      card.querySelector(".subtle").textContent = "健康评分、关键 gate 与 freshness。Used to judge whether runtime facts are trustworthy enough.";
    }
    if (current.includes("产品族事实")) {
      h2.innerHTML = zhEnPrimary("产品族事实", "Product Family Facts");
      card.querySelector(".subtle").textContent = "这里优先展示事实层：交易所与账户真实返回的状态。控制层配置只是另一层。";
    }
    if (current.includes("快捷动作")) {
      h2.innerHTML = zhEnPrimary("快捷动作", "Quick Actions");
      card.querySelector(".subtle").textContent = "仅调用受保护控制面动作，不直接开放真实执行权限。Critical actions now require second confirmation.";
    }
    if (current.includes("调试原文")) {
      h2.innerHTML = zhEnPrimary("调试原文", "Debug Raw JSON");
      card.querySelector(".subtle").textContent = "默认折叠，仅在需要审计或排错时展开。These raw blocks are not the primary UI.";
    }
  });

  const ths = document.querySelectorAll("table thead th");
  const tableHeaders = [
    zhEnPrimary("产品族", "Product Family"),
    zhEnPrimary("交易所事实", "Exchange Fact"),
    zhEnPrimary("账户事实", "Account Fact"),
    zhEnPrimary("已启用", "Enabled"),
    zhEnPrimary("可见", "Visible"),
    zhEnPrimary("模式", "Mode"),
    zhEnPrimary("能力", "Capability"),
    zhEnPrimary("执行", "Execution")
  ];
  ths.forEach((th, idx) => { if (tableHeaders[idx]) th.innerHTML = tableHeaders[idx]; });

  const actionButtons = {
    refresh: "刷新概览",
    validate: "验证 Demo",
    "set-demo-mode": "切到 Demo Reserved",
    "enable-spot": "开启 Spot / 现货产品配置",
    "arm-demo": "执行 Demo Arm",
    bundle: "安全复核打包"
  };
  const actionButtonSubs = {
    refresh: "refresh overview",
    validate: "validate demo gates",
    "set-demo-mode": "global demo mode",
    "enable-spot": "spot product config",
    "arm-demo": "move to armed_but_closed",
    bundle: "multi-step guarded recheck"
  };
  document.querySelectorAll("[data-action]").forEach((button) => {
    const name = button.dataset.action;
    if (actionButtons[name]) button.innerHTML = `${actionButtons[name]}<span class="button-sub">${actionButtonSubs[name] || name.replaceAll("-", " ")}</span>`;
  });

  const actionSummaryLabels = document.querySelectorAll("#actionSummaryGrid .summary-label");
  const actionTexts = [
    zhEnPrimary("最近动作", "Last Action"),
    zhEnPrimary("结果", "Result"),
    zhEnPrimary("状态版本", "State Revision"),
    zhEnPrimary("审计引用", "Audit Ref")
  ];
  actionSummaryLabels.forEach((node, index) => { if (actionTexts[index]) node.innerHTML = actionTexts[index]; });

  const rawSummaries = document.querySelectorAll("details.raw-toggle summary");
  if (rawSummaries[0]) rawSummaries[0].innerHTML = zhEnPrimary("查看原始动作响应", "View raw action response");
  if (rawSummaries[1]) rawSummaries[1].innerHTML = zhEnPrimary("控制平面原文", "Control Plane Raw");
  if (rawSummaries[2]) rawSummaries[2].innerHTML = zhEnPrimary("审计摘要原文", "Audit Raw");
  if (rawSummaries[3]) rawSummaries[3].innerHTML = zhEnPrimary("系统总览原文", "Overview Raw");

  if (!document.getElementById("guiConceptHints")) {
    const hintCard = document.createElement("section");
    hintCard.className = "card glossary-card";
    hintCard.id = "guiConceptHints";
    hintCard.innerHTML = `
      <details class="raw-toggle">
        <summary>${zhEnPrimary("关键概念提示（按需展开）", "Key Concept Hints")}</summary>
        <div class="glossary-wrap" style="padding:16px;">
          ${annotateGlossary("事实", "Facts", "先看交易所、账户、runtime 实际返回了什么。事实是“真实情况”，不是你点按钮点出来的权限。", "Facts are the actual returned conditions, not permissions granted by a button.")}
          ${annotateGlossary("权限配置", "Control Permission", "再看你在控制面配置了什么，例如 demo reserved、spot shadow。这些是“允许系统往下判断”，不是“马上能执行”。", "Control permissions allow the system to continue guarded evaluation; they are not immediate execution authority.")}
          ${annotateGlossary("状态推进", "State Progress", "最后看 demo validate、demo arm 这类步骤。它们表示系统流程往前走了，但仍可能保持封闭。", "State progress means the workflow moved forward, but it can still remain closed.")}
          ${annotateGlossary("最重要的一句", "Most Important Rule", "看得见 ≠ 被允许；被允许继续判断 ≠ 能执行；demo ≠ live。", "Visible is not allowed; allowed to continue is not executable; demo is not live.")}
        </div>
      </details>`;
    const hero = document.querySelector(".hero-card");
    if (hero) hero.after(hintCard);
  }

  if (!document.getElementById("runtimeModeSection")) {
    const grid = document.createElement("section");
    grid.className = "grid two-up injected-grid";
    grid.innerHTML = `
      <section class="card" id="runtimeModeSection">
        <div class="card-header-row">
          <div>
            <h2>${zhEnPrimary("运行模式控制", "Runtime Mode Control")}</h2>
            <p class="subtle">受保护模式切换骨架；当前只开放低风险 guarded 动作，live 仍锁定。</p>
          </div>
        </div>
        <div class="mode-grid">
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("阶段标签", "Stage Label")}</span><strong id="modeStageLabel">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("能力状态", "Capability State")}</span><strong id="modeCapabilityState">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("Demo Arm Gate", "Demo Arm Gate")}</span><strong id="modeDemoArmGate">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("Demo Enable Gate", "Demo Enable Gate")}</span><strong id="modeDemoEnableGate">-</strong></div>
        </div>
        <div class="mode-actions">
          <button data-action="set-demo-mode">切到 Demo Reserved<span class="button-sub">global demo mode</span></button>
          <button data-action="enable-spot">开启 Spot / 现货产品配置<span class="button-sub">spot product config</span></button>
          <button data-action="validate">验证 Demo 前提<span class="button-sub">validate demo gates</span></button>
          <button data-action="arm-demo">执行 Demo Arm<span class="button-sub">move to armed_but_closed</span></button>
          <button class="button-muted" disabled>观测模式<span class="button-sub">Observe Only · later</span></button>
          <button class="button-muted" disabled>Live 模式<span class="button-sub">Live Mode · locked</span></button>
        </div>
        <div id="modeControlNote" class="mode-note">简单理解这一区域：先决定“系统要不要进入 demo/spot 的受保护流程”，再决定“现在是否满足继续前进的条件”。它不是“真实执行权限开关区”。</div>
      </section>
      <section class="card" id="businessSummarySection">
        <div class="card-header-row">
          <div>
            <h2>${zhEnPrimary("经营与收益摘要", "Business & Income Summary")}</h2>
            <p class="subtle">来自 overview 的 daily business summary；当前为展示骨架，后续继续接更真实的 runtime exporter。</p>
          </div>
        </div>
        <div class="summary-grid business-grid">
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("已实现盈亏", "Realized PnL")}</span><strong id="bizRealizedPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("未实现盈亏", "Unrealized PnL")}</span><strong id="bizUnrealizedPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("毛盈亏", "Gross PnL")}</span><strong id="bizGrossPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("总成本", "Total Cost")}</span><strong id="bizTotalCost">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("净经营盈亏", "Net Operating PnL")}</span><strong id="bizNetOperatingPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("业务事件数", "Business Event Count")}</span><strong id="bizEventCount">-</strong></div>
        </div>
        <div class="mode-note">当前只展示 overview 中已有的 daily business summary；后续可再做日/周/月切片与更完整收益面板。</div>
      </section>`;

    const firstGrid = document.querySelector(".page-shell > .grid.two-up");
    if (firstGrid) firstGrid.before(grid);
  }

  if (!document.getElementById("productFamilyConfigSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "productFamilyConfigSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("产品族配置", "Product Family Configuration")}</h2>
          <p class="subtle">这是后续正式承接“查看状态 + 调整设置”的独立区域。当前先做骨架，后续继续接入更多产品族设置。</p>
        </div>
      </div>
      <div class="summary-grid business-grid config-family-grid">
        <div class="summary-item config-family-card">
          <span class="summary-label">${zhEnPrimary("现货产品配置", "Spot Configuration")}</span>
          <strong id="cfgSpotSummary">-</strong>
          <div id="cfgSpotMeta" class="family-card-meta">-</div>
          <div class="family-actions"><button class="button-muted" disabled>设置入口（后续）<span class="button-sub">settings later</span></button></div>
        </div>
        <div class="summary-item config-family-card">
          <span class="summary-label">${zhEnPrimary("保证金产品配置", "Margin Configuration")}</span>
          <strong id="cfgMarginSummary">-</strong>
          <div id="cfgMarginMeta" class="family-card-meta">-</div>
          <div class="family-actions"><button class="button-muted" disabled>设置入口（后续）<span class="button-sub">settings later</span></button></div>
        </div>
        <div class="summary-item config-family-card">
          <span class="summary-label">${zhEnPrimary("线性永续配置", "Linear Perp Configuration")}</span>
          <strong id="cfgLinearPerpSummary">-</strong>
          <div id="cfgLinearPerpMeta" class="family-card-meta">-</div>
          <div class="family-actions"><button class="button-muted" disabled>设置入口（后续）<span class="button-sub">settings later</span></button></div>
        </div>
        <div class="summary-item config-family-card">
          <span class="summary-label">${zhEnPrimary("反向永续配置", "Inverse Perp Configuration")}</span>
          <strong id="cfgInversePerpSummary">-</strong>
          <div id="cfgInversePerpMeta" class="family-card-meta">-</div>
          <div class="family-actions"><button class="button-muted" disabled>设置入口（后续）<span class="button-sub">settings later</span></button></div>
        </div>
        <div class="summary-item config-family-card">
          <span class="summary-label">${zhEnPrimary("期权配置", "Options Configuration")}</span>
          <strong id="cfgOptionsSummary">-</strong>
          <div id="cfgOptionsMeta" class="family-card-meta">-</div>
          <div class="family-actions"><button class="button-muted" disabled>设置入口（后续）<span class="button-sub">settings later</span></button></div>
        </div>
        <div class="summary-item config-family-card">
          <span class="summary-label">${zhEnPrimary("其他衍生品（预留）", "Other Derivatives Reserved")}</span>
          <strong id="cfgOtherDerivativesSummary">-</strong>
          <div id="cfgOtherDerivativesMeta" class="family-card-meta">-</div>
          <div class="family-actions"><button class="button-muted" disabled>设置入口（后续）<span class="button-sub">settings later</span></button></div>
        </div>
      </div>
      <div class="mode-note">这里先回答两个最基础的问题：这个产品族现在是否启用、是否可见、处于什么模式。等主线推进后，再把真正可修改的设置接进来。</div>`;
    const productFactsCard = Array.from(document.querySelectorAll(".page-shell > .card")).find((node) => node.querySelector("h2")?.textContent.includes("产品族事实"));
    if (productFactsCard) {
      productFactsCard.before(card);
    }
  }

  if (!document.getElementById("confirmModal")) {
    const modal = document.createElement("div");
    modal.id = "confirmModal";
    modal.className = "confirm-modal hidden";
    modal.innerHTML = `
      <div class="confirm-modal-backdrop" data-close-modal="true"></div>
      <div class="confirm-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="confirmModalTitle">
        <div class="confirm-modal-header">
          <h3 id="confirmModalTitle">关键动作确认</h3>
          <button class="confirm-close" data-close-modal="true">×</button>
        </div>
        <div class="confirm-modal-body">
          <div id="confirmModalSubtitle" class="confirm-subtitle">-</div>
          <div class="confirm-block">
            <div class="confirm-label">风险说明 / Risk</div>
            <div id="confirmModalRisk">-</div>
          </div>
          <div class="confirm-block">
            <div class="confirm-label">后果说明 / Consequence</div>
            <div id="confirmModalConsequence">-</div>
          </div>
          <div class="confirm-note">请确认你理解该动作不会直接开放真实 live execution，但会推进控制状态或影响可见控制结果。 / Please confirm you understand this does not directly open live execution, but it changes guarded control state or visible control outcomes.</div>
        </div>
        <div class="confirm-modal-footer">
          <button class="button-muted confirm-cancel" data-close-modal="true">取消 / Cancel</button>
          <button id="confirmModalProceed">确认执行 / Confirm</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }
}

function openConfirmModal(actionName) {
  const meta = CRITICAL_ACTIONS[actionName];
  if (!meta) return Promise.resolve(true);
  const modal = document.getElementById("confirmModal");
  modal.classList.remove("hidden");
  document.getElementById("confirmModalTitle").textContent = meta.title;
  document.getElementById("confirmModalSubtitle").textContent = meta.subtitle;
  document.getElementById("confirmModalRisk").textContent = meta.risk;
  document.getElementById("confirmModalConsequence").textContent = meta.consequence;

  return new Promise((resolve) => {
    const cleanup = () => {
      modal.classList.add("hidden");
      document.querySelectorAll("[data-close-modal='true']").forEach((node) => node.replaceWith(node.cloneNode(true)));
      const proceed = document.getElementById("confirmModalProceed");
      proceed.replaceWith(proceed.cloneNode(true));
    };

    modal.querySelectorAll("[data-close-modal='true']").forEach((node) => {
      node.onclick = () => {
        cleanup();
        resolve(false);
      };
    });
    document.getElementById("confirmModalProceed").onclick = () => {
      cleanup();
      resolve(true);
    };
  });
}

function renderSummary(overview) {
  const runtime = overview.data.global_runtime;
  const demo = overview.data.demo_control_summary;
  const sourceContext = overview.source_context;

  document.getElementById("summaryGlobalMode").textContent = runtime.global_mode_state;
  document.getElementById("summaryExecutionAuthority").textContent = runtime.global_execution_authority_state;
  document.getElementById("summaryDemoState").textContent = demo.demo_state_switch;
  document.getElementById("summarySnapshot").textContent = `${overview.state_revision} / ${overview.snapshot_id}`;
  document.getElementById("summaryRuntimeSnapshot").textContent = sourceContext.pinned_runtime_snapshot_id;
  document.getElementById("summaryProtected").textContent = String(runtime.runtime_still_protected);

  setRuntimeModeBadge(`${runtime.global_mode_state} · ${demo.demo_state_switch}`, variantForState(runtime.global_execution_authority_state));
}

function renderModeControl(overview) {
  const runtime = overview.data.global_runtime;
  const demo = overview.data.demo_control_summary;
  const stageLabel = document.getElementById("modeStageLabel");
  const capability = document.getElementById("modeCapabilityState");
  const armGate = document.getElementById("modeDemoArmGate");
  const enableGate = document.getElementById("modeDemoEnableGate");
  if (!stageLabel) return;
  stageLabel.textContent = safeText(runtime.global_stage_label);
  capability.textContent = safeText(runtime.global_capability_state);
  armGate.textContent = safeText(demo.demo_arm_gate_state);
  enableGate.textContent = safeText(demo.demo_enable_gate_state);
}

function renderBusinessSummary(overview) {
  const daily = overview.data.daily_business_summary;
  const mapping = {
    bizRealizedPnl: daily.realized_pnl,
    bizUnrealizedPnl: daily.unrealized_pnl,
    bizGrossPnl: daily.gross_pnl,
    bizTotalCost: daily.total_cost,
    bizNetOperatingPnl: daily.net_operating_pnl,
    bizEventCount: daily.business_event_count
  };
  Object.entries(mapping).forEach(([id, value]) => {
    const node = document.getElementById(id);
    if (node) node.textContent = safeText(value);
  });
}

function renderProductFamilyConfig(productFamilies) {
  Object.entries(PRODUCT_FAMILY_CONFIG_IDS).forEach(([family, ids]) => {
    const data = productFamilies[family];
    const summaryNode = document.getElementById(ids.summary);
    const metaNode = document.getElementById(ids.meta);
    if (!summaryNode || !metaNode) return;
    if (!data) {
      summaryNode.textContent = "-";
      metaNode.textContent = "当前没有这类产品的配置摘要。";
      return;
    }

    const enabledText = booleanZh(data.controls.enabled_switch, "已启用", "未启用");
    const visibleText = booleanZh(data.controls.visibility_switch, "可见", "隐藏");
    summaryNode.textContent = `${enabledText} · ${visibleText} · 模式 ${safeText(data.controls.mode_switch)}`;
    metaNode.textContent = `交易所事实：${safeText(data.facts.exchange_permission_fact)}；账户事实：${safeText(data.facts.account_permission_fact)}；能力：${safeText(data.derived.capability_state)}`;
  });
}

function renderSourceContext(sourceContext) {
  renderKvGrid("sourceContextGrid", [
    [zhEnPrimary("只读连接器", "Readonly Connector"), sourceContext.readonly_connector_name],
    [zhEnPrimary("执行连接器", "Execution Connector"), sourceContext.execution_connector_name || "not_attached"],
    [zhEnPrimary("私有 REST", "REST Private"), sourceContext.rest_private_connection_state],
    [zhEnPrimary("私有 WS", "WS Private"), sourceContext.ws_private_connection_state],
    [zhEnPrimary("Runtime 连接", "Runtime Connection"), sourceContext.runtime_connection_state],
    [zhEnPrimary("账户完整性", "Account Completeness"), sourceContext.account_fact_completeness_state],
    [zhEnPrimary("快照完整性", "Snapshot Completeness"), sourceContext.source_snapshot_completeness_state],
    [zhEnPrimary("角色分离", "Role Separation"), sourceContext.connector_role_separation_ok],
    [zhEnPrimary("Runtime 快照", "Runtime Snapshot"), sourceContext.pinned_runtime_snapshot_id]
  ]);
}

function renderHealth(overview) {
  const health = overview.data.health_summary;
  renderKvGrid("healthGrid", [
    [zhEnPrimary("总健康分", "Overall Health Score"), health.scores.overall_health_score],
    [zhEnPrimary("AI 健康分", "AI Health Score"), health.scores.ai_health_score],
    [zhEnPrimary("交易所健康分", "Exchange Health Score"), health.scores.exchange_health_score],
    [zhEnPrimary("新鲜度分", "Data Freshness Score"), health.scores.data_freshness_score],
    [zhEnPrimary("总 Gate", "Health Gates Overall"), health.gates.health_gates_overall_state],
    [zhEnPrimary("Timeout Gate", "Exchange Timeout Gate"), health.gates.exchange_timeout_gate_state],
    [zhEnPrimary("WS 断连 Gate", "WS Disconnect Gate"), health.gates.ws_disconnect_gate_state],
    [zhEnPrimary("延迟 Gate", "Latency Gate"), health.gates.latency_gate_state],
    [zhEnPrimary("新鲜度 Gate", "Freshness Gate"), health.gates.freshness_gate_state]
  ]);
}

function renderProductFamilies(productFamilies) {
  const body = document.getElementById("productFamilyTableBody");
  const rows = Object.entries(productFamilies).map(([name, data]) => `
    <tr>
      <td>${PRODUCT_FAMILY_LABELS[name] || name}</td>
      <td><span class="status-chip ${variantForState(data.facts.exchange_permission_fact)}">${data.facts.exchange_permission_fact}</span></td>
      <td><span class="status-chip ${variantForState(data.facts.account_permission_fact)}">${data.facts.account_permission_fact}</span></td>
      <td>${String(data.controls.enabled_switch)}</td>
      <td>${String(data.controls.visibility_switch)}</td>
      <td>${data.controls.mode_switch}</td>
      <td><span class="status-chip ${variantForState(data.derived.capability_state)}">${data.derived.capability_state}</span></td>
      <td><span class="status-chip ${variantForState(data.derived.execution_authority_state)}">${data.derived.execution_authority_state}</span></td>
    </tr>`).join("");
  body.innerHTML = rows || '<tr><td colspan="8" class="muted-cell">无数据 / No data</td></tr>';
}

async function apiGet(path) {
  const response = await fetch(path, { headers: headers() });
  const data = await response.json();
  if (!response.ok) throw new Error(pretty(data));
  return data;
}

async function apiPost(path, payload) {
  const response = await fetch(path, { method: "POST", headers: headers(), body: JSON.stringify(payload) });
  const data = await response.json();
  if (!response.ok) throw new Error(pretty(data));
  return data;
}

async function loadDashboard() {
  ensureGuiEnhancements();
  const [overview, controlPlane, sourceContext, audit, productFamilies] = await Promise.all([
    apiGet("/api/v1/system/overview"),
    apiGet("/api/v1/system/control-plane"),
    apiGet("/api/v1/system/source-context"),
    apiGet("/api/v1/system/audit-summary"),
    apiGet("/api/v1/system/product-families")
  ]);

  renderSummary(overview);
  renderModeControl(overview);
  renderBusinessSummary(overview);
  renderProductFamilyConfig(productFamilies.data);
  renderSourceContext(sourceContext.data);
  renderHealth(overview);
  renderProductFamilies(productFamilies.data);

  document.getElementById("overviewBox").textContent = pretty(overview);
  document.getElementById("controlPlaneBox").textContent = pretty(controlPlane);
  document.getElementById("auditBox").textContent = pretty(audit);
}

async function getOverviewForEnvelope() {
  return await apiGet("/api/v1/system/overview");
}

function baseEnvelope(overview, extra = {}) {
  return {
    request_id: crypto.randomUUID(),
    idempotency_key: crypto.randomUUID(),
    operator_id: "demo-operator",
    reason: "gui-triggered action",
    client_ts_ms: Date.now(),
    expected_state_revision: overview.state_revision,
    expected_previous_state: null,
    payload: {},
    ...extra
  };
}

async function runQuickAction(actionName) {
  try {
    const overview = await getOverviewForEnvelope();
    let result;

    if (actionName !== "refresh") {
      const confirmed = await openConfirmModal(actionName);
      if (!confirmed) {
        setActionSummary("已取消 / Cancelled", "blocked", "-", "-", "用户取消了关键动作确认。 / User cancelled the critical action.", { cancelled: true, action: actionName });
        return;
      }
    }

    if (actionName === "refresh") {
      await loadDashboard();
      setActionSummary("刷新概览 / refresh overview", "success", overview.state_revision, "-", "界面已刷新。 / Dashboard refreshed.", { message: "Refresh completed." });
      return;
    }
    if (actionName === "validate") result = await apiPost("/api/v1/control/demo/validate", baseEnvelope(overview));
    if (actionName === "bundle") result = await apiPost("/api/v1/control/safe-recheck-bundle", baseEnvelope(overview));
    if (actionName === "set-demo-mode") {
      result = await apiPost("/api/v1/input/config-change", baseEnvelope(overview, {
        payload: { changes: [{ path: "global_runtime.controls.global_execution_mode_switch", value: "demo_reserved" }] }
      }));
    }
    if (actionName === "enable-spot") {
      result = await apiPost("/api/v1/input/config-change", baseEnvelope(overview, {
        payload: { changes: [
          { path: "product_family_status.spot.controls.enabled_switch", value: true },
          { path: "product_family_status.spot.controls.mode_switch", value: "shadow_only" }
        ] }
      }));
    }
    if (actionName === "arm-demo") {
      const demoState = overview.data.demo_control_summary.demo_state_switch;
      result = await apiPost("/api/v1/control/demo/arm", baseEnvelope(overview, {
        expected_previous_state: demoState,
        payload: { acknowledged: true }
      }));
    }

    summarizeActionResult(actionName, result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("动作失败 / Action Failed", "failed", "-", "-", String(error), String(error));
  }
}

document.addEventListener("DOMContentLoaded", () => {
  ensureGuiEnhancements();
  document.getElementById("connectButton").addEventListener("click", async () => {
    inMemoryToken = document.getElementById("tokenInput").value.trim();
    try {
      await loadDashboard();
      setConnectionStatus("已连接 / Connected", "good");
      setActionSummary("连接 / Connect", "success", "-", "-", "连接成功。 / Connected successfully.", { message: "Connected successfully." });
    } catch (error) {
      setConnectionStatus("连接失败 / Failed", "bad");
      setActionSummary("连接 / Connect", "failed", "-", "-", String(error), String(error));
    }
  });

  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    event.preventDefault();
    runQuickAction(target.dataset.action);
  });
});
