/*
 * view-ai-providers.js — 玄衡原生 view「AI 狀態」供應商 + 引擎設置面 companion(Phase 2 第 6 遷;含寫 + typed-confirm)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:tab-ai 遷移的**供應商 + 引擎設置面拆檔**(檔案 <800 硬性;主檔 view-ai.js 已承
 *   狀態/歷史/Phase3,成本面在 view-ai-cost.js)。本檔不註冊 OC_NATIVE_VIEWS(非獨立 view),
 *   而註冊 window.OC_AI_PROVIDERS = {render, load},由主檔 view-ai.js 於 render/loadAll 驅動
 *   (companion 缺席時主面照常降級)。**本檔承 tab-ai 的 3 config/DELETE 寫 + 1 typed-confirm**。
 *   內容逐節守恆(對 legacy tab-ai 供應商 + 設置 2 節,零丟失):
 *     ⑥AI 供應商管理(anthropic/openai/deepseek/local_llm/google 5 卡 + Scout 專用 perplexity 卡;
 *       每卡:密鑰輸入 + 保存 + 清除/檢測 + badge + 來源明細);⑦引擎設置(啟用/默認供應商/模型/
 *       日硬上限/彈性基準/彈性上下限/自動升級/自動提交/最大迭代 + Tier 2/3 預算降級 + 保存 + 當前配置);
 *       附:模型目錄刷新、Ollama 連通檢測、供應商 badge 真實狀態。
 *   刻意變更(canon 守恆):legacy `.oc-card/.oc-input/.oc-select/.oc-btn`(ocInjectBaseCSS,殼不呼叫)
 *     不可用,改殼組件庫(.panel/.tag/.note)+ 原生 input/select(殼作用域瀏覽器預設樣式);legacy
 *     頁內 id(key-anthropic/ai-model…)改殼作用域 class 選擇器(避免與殼全局 id 碰撞);legacy 裝飾
 *     emoji 不遷;canon 7 誠實:badge 客戶端未實裝時只顯「已存儲·客戶端未接」(warn),絕不假 Active。
 * 主要函數:render(建供應商 + 設置骨架,冪等)、load(4 唯讀 GET 渲染)、
 *   loadProviderStatus / loadProviderModelCatalog / checkOllamaStatus / loadConfig、
 *   saveProviderKey(POST config {provider_keys})、clearProviderKey(DELETE providers/{}, typed-confirm)、
 *   saveAIConfig(POST config {全 body})、syncModelSelectsFromProviders。
 * 依賴(全復用,不重造):common.js ocApi / ocPost / ocToast;common-modals.js openTypedConfirmModal
 *   (清除密鑰 typed-confirm);common-formatters.js ocEsc / ocPct / OC_EMPTY;組件庫 + tokens + oc-utilities。
 * 硬邊界(canon / LOOP §6):
 *   ① 寫面走既有 Rust/API authority——本檔 3 寫 preserve 既有端點,payload byte-parity:
 *      · POST /api/v1/paper/layer2/config(payload {provider_keys:{[provider]:key}} 保存密鑰;或全 body 保存設置);
 *      · DELETE /api/v1/paper/layer2/providers/{provider}(清除密鑰;∈ 5b DYNAMIC_DEBT_ALLOWLIST)。
 *      **絕不新增寫路徑、絕不改端點/payload**。
 *   ② **1 typed-confirm 必保(逐字保留,不弱化/移除)**:清除 API Key 屬 governance critical 寫
 *      (刪 secrets 文件 + 移進程 env),用既有 common-modals openTypedConfirmModal,phrase='CLEAR',
 *      title/body/impact/rollback/confirmLabel/confirmClass 逐字 port legacy;await 包 try/catch,
 *      singleton reject 不靜默,取消顯 toast 不靜默 return。DELETE 只在 typed 短語相符 + 確認後才送。
 *   ③ **response-gated 成功,絕不 fake-success**:ocApi/ocPost 非-2xx/網路/timeout/CSRF 失敗回 null;
 *      保存密鑰讀後端 envelope(provider_errors/provider_results/provider_status)真結果顯示,客戶端未實裝
 *      只顯「已存儲·未實裝」warn(不假 Active);保存設置僅 d.action_result==='success' 才成功,否則顯 reason_codes。
 *   ④ canon 7 三態:loading=「檢測中…」;無真值=「—」;error=顯錯不崩,保守 warn/bad,絕不假 provider 狀態。
 *   ⑤ visibility 由主檔統籌;ratchet 0/0/0:零裸 hex、零 inline 樣式屬性、零內聯樣式塊;tone 走 scoped-var。
 * 誠實邊界:靜態只證 source/路徑/端點對齊;**真渲染/三態/真 provider 狀態/3 寫真行為(真送達·真授權·
 *   真審計)/typed-confirm 真 DOM 行為 = NEEDS-LINUX runtime + operator 視覺**,不由本刀 attest。
 *   附:openTypedConfirmModal / 表單控件的視覺樣式由 common.js ocInjectBaseCSS 運行時注入樣式供給,殼未
 *   呼叫該注入(避免全域 body padding 破殼 chrome)→ modal/表單在殼內功能完整但樣式退化(與 learning
 *   遷移的 ocToast 同一既存殼級 gap);**typed-confirm 的 phrase 閘功能不受樣式影響,安全語義守恆**。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  var host = null;
  var built = false;

  // ── 執行期設置態(port legacy module 態)──
  var L2_MODEL_CATALOG = null;
  var AI_CONFIG_DIRTY = false;
  var AI_CONFIG_SAVING = false;
  var L2_PROVIDER_MODELS = {
    anthropic: [
      { value: 'haiku', label: 'haiku — Claude Haiku 4.5' },
      { value: 'sonnet', label: 'sonnet — Claude Sonnet 4.6' },
      { value: 'opus', label: 'opus — Claude Opus 4.7' },
    ],
    deepseek: [
      { value: 'deepseek-v4-flash', label: 'deepseek-v4-flash — V4 Flash' },
      { value: 'deepseek-v4-pro', label: 'deepseek-v4-pro — V4 Pro' },
      { value: 'deepseek-chat', label: 'deepseek-chat — deprecated 2026-07-24' },
      { value: 'deepseek-reasoner', label: 'deepseek-reasoner — deprecated 2026-07-24' },
    ],
    openai: [
      { value: 'gpt-5.4-mini', label: 'gpt-5.4-mini' },
      { value: 'gpt-5.4', label: 'gpt-5.4' },
      { value: 'gpt-5.5', label: 'gpt-5.5' },
      { value: 'gpt-4o-mini', label: 'gpt-4o-mini' },
      { value: 'gpt-4o', label: 'gpt-4o' },
      { value: 'o1', label: 'o1（reasoner）' },
    ],
    local_llm: [
      { value: 'local:', label: 'Local LLM — 等待本地模型目錄', providerAvailable: false },
    ],
  };
  var L2_SELECT_DEFAULTS = {
    'f-ai-model': { anthropic: 'sonnet', deepseek: 'deepseek-v4-flash', openai: 'gpt-5.4-mini' },
    'f-ai-tier2-model': { anthropic: 'haiku', deepseek: 'deepseek-v4-flash', openai: 'gpt-5.4-mini' },
    'f-ai-tier3-model': { anthropic: 'haiku', deepseek: 'deepseek-v4-flash', openai: 'gpt-5.4-mini' },
  };
  // API Key 格式校驗規則(與後端 validate_key 一致;提早攔截)。
  var KEY_FORMATS = {
    anthropic: { prefix: 'sk-ant-', minLen: 20, hint: '必須以 sk-ant- 開頭 / Must start with sk-ant-' },
    openai: { prefix: 'sk-', minLen: 20, hint: '必須以 sk- 開頭 / Must start with sk-' },
    deepseek: { prefix: 'sk-', minLen: 20, hint: '必須以 sk- 開頭 / Must start with sk-' },
    perplexity: { prefix: 'pplx-', minLen: 20, hint: '必須以 pplx- 開頭 / Must start with pplx-' },
    google: { prefix: null, minLen: 20, hint: '至少 20 個字符 / At least 20 characters' },
    local_llm: { prefix: 'http', minLen: 8, hint: '必須是 http:// 或 https:// URL' },
  };
  // 卡片描述(port legacy 5 主卡 + perplexity)。
  var PROVIDERS = [
    { key: 'anthropic', name: 'Anthropic (Claude)', models: 'Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5', type: 'password', ph: 'sk-ant-...', price: '參考價格:Haiku $0.25/Sonnet $3/Opus $15 per 1M tokens', action: 'clear' },
    { key: 'openai', name: 'OpenAI (GPT)', models: 'GPT-4o / GPT-4o-mini / o1 / o3', type: 'password', ph: 'sk-...', price: '參考價格:GPT-4o-mini $0.15/GPT-4o $2.5/o1 $15 per 1M tokens', action: 'clear' },
    { key: 'deepseek', name: 'DeepSeek', models: 'DeepSeek V4 Flash / V4 Pro', type: 'password', ph: 'sk-...', price: '參考價格:V4 Flash $0.14/$0.28 per 1M input/output tokens', action: 'clear' },
    { key: 'local_llm', name: '本地 LLM / Ollama', models: 'Qwen 3.5 27B / 9B — 零 API 成本', type: 'text', ph: 'http://127.0.0.1:11434', value: 'http://127.0.0.1:11434', price: '零成本,需要本地 GPU。', action: 'detect' },
    { key: 'google', name: 'Google (Gemini)', models: 'Gemini 2.5 Pro / Flash', type: 'password', ph: 'AI...', price: '參考價格:Flash $0.075/Pro $1.25 per 1M tokens', action: 'clear' },
  ];
  var SCOUT_PROVIDER = { key: 'perplexity', name: 'Perplexity', models: '搜索增強型 AI — 實時市場信息(不接 L2 推理)', type: 'password', ph: 'pplx-...', price: '參考價格:$5/1000 requests(含實時搜索)', action: 'clear' };

  // ── 小工具(拆檔各自持最小副本)──
  function root() { return host ? host.querySelector('.ai-providers-slot') : null; }
  function q(sel) { var r = root(); return r ? r.querySelector(sel) : null; }
  function esc(s) { return (typeof window.ocEsc === 'function') ? window.ocEsc(s) : String(s == null ? '' : s); }
  var EMPTY = (typeof window.OC_EMPTY === 'string') ? window.OC_EMPTY : '—';

  function toneVar(tone) {
    if (tone === 'good') return 'var(--pos)';
    if (tone === 'bad') return 'var(--neg)';
    if (tone === 'muted') return 'var(--text-muted)';
    if (tone === 'accent') return 'var(--accent)';
    return 'var(--warn)';
  }
  function applyTagTones(el) {
    if (!el) return;
    var tags = el.querySelectorAll('.tag[data-tone]');
    for (var i = 0; i < tags.length; i++) {
      tags[i].style.setProperty('--tag-tone', toneVar(tags[i].getAttribute('data-tone')));
    }
  }
  function setTag(el, text, tone) {
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'muted');
    el.style.setProperty('--tag-tone', toneVar(tone || 'muted'));
  }
  function toast(msg, type) { if (typeof window.ocToast === 'function') window.ocToast(msg, type); }

  // ═══ 供應商卡骨架 ═══
  function providerCardHtml(p) {
    var valueAttr = p.value ? (' value="' + esc(p.value) + '"') : '';
    var actionBtn = (p.action === 'detect')
      ? '<button type="button" class="tag pointer pv-detect" data-key="' + esc(p.key) + '" data-tone="accent">檢測</button>'
      : '<button type="button" class="tag pointer pv-clear" data-key="' + esc(p.key) + '" data-tone="bad">清除</button>';
    var modelsLine = (p.key === 'local_llm')
      ? '<div class="note ollama-models-line mb-2">' + esc(p.models) + '</div>'
      : '<div class="note mb-2">模型:' + esc(p.models) + '</div>';
    var detail = (p.key === 'local_llm')
      ? '<div class="note fs-micro mt-1 ollama-status-detail">零成本,需要本地 GPU。正在檢測 Ollama 連通性…</div>'
      : '<div class="note fs-micro mt-1 pd-' + esc(p.key) + '">來源:檢測中…</div>';
    return '<div class="panel">' +
      '<div class="row-between wrap gap-2">' +
        '<span class="fw-semi">' + esc(p.name) + '</span>' +
        '<span class="pb-' + esc(p.key) + ' tag" data-tone="muted">檢測中…</span>' +
      '</div>' +
      modelsLine +
      '<div class="row wrap gap-2">' +
        '<input type="' + esc(p.type) + '" class="pk-' + esc(p.key) + ' mono flex-1" placeholder="' + esc(p.ph) + '"' + valueAttr + ' autocomplete="off" />' +
        '<button type="button" class="tag pointer pv-save" data-key="' + esc(p.key) + '" data-tone="accent">保存</button>' +
        actionBtn +
      '</div>' +
      '<div class="note fs-micro mt-1">' + esc(p.price) + '</div>' +
      detail +
    '</div>';
  }

  // ═══ 引擎設置表單骨架 ═══
  function providerOptions() {
    return '<option value="anthropic">Anthropic (Claude)</option>' +
      '<option value="deepseek">DeepSeek</option>' +
      '<option value="openai">OpenAI (GPT)</option>' +
      '<option value="local_llm">Local LLM</option>';
  }
  function settingRow(labelZh, hint, control) {
    return '<div class="row-between wrap gap-2 mt-2">' +
      '<div><div class="fs-dense fw-semi">' + esc(labelZh) + '</div><div class="note fs-micro">' + esc(hint) + '</div></div>' +
      control + '</div>';
  }
  var SETTINGS_HTML =
    '<div class="panel">' +
      '<div class="row-between wrap gap-2">' +
        '<div class="panel-t"><span class="zh">引擎設置</span><span class="code">ENGINE SETTINGS</span></div>' +
        '<button type="button" class="tag pointer models-refresh" data-tone="muted">↻ Models</button>' +
      '</div>' +
      '<div class="note fs-micro mb-1 model-catalog-status">模型目錄:載入中</div>' +
      '<div class="note fs-micro mb-2 local-model-status">本地模型:載入中</div>' +
      '<div class="row wrap gap-4">' +
        '<div class="col flex-1">' +
          settingRow('啟用 AI 引擎 / Enable', '關閉後所有 AI 查詢將停止', '<select class="f-enabled"><option value="true">啟用</option><option value="false">禁用</option></select>') +
          settingRow('默認供應商 / Default Provider', 'L2 推理首選', '<select class="f-provider">' + providerOptions() + '</select>') +
          settingRow('默認模型 / Default Model', 'tier_key — adapter 自動映射 model_id', '<select class="f-ai-model"><option value="">—</option></select>') +
          settingRow('日硬上限 / Daily Hard Cap ($)', '所有供應商合計的每日成本硬上限', '<input type="number" class="f-hard-cap oc-input--num mono" step="0.5" min="0" max="100" />') +
          settingRow('彈性基準 / Adaptive Base ($)', '自適應預算基準值', '<input type="number" class="f-base-daily oc-input--num mono" step="0.5" min="0" max="50" />') +
          settingRow('彈性上限 / Max Multiplier (x)', '預算最多擴大到基準的幾倍', '<input type="number" class="f-max-mult oc-input--num mono" step="0.1" min="1" max="5" />') +
          settingRow('彈性下限 / Min Multiplier (x)', '預算最少縮減到基準的幾倍', '<input type="number" class="f-min-mult oc-input--num mono" step="0.1" min="0" max="1" />') +
          settingRow('允許自動升級模型 / Auto Upgrade', '允許系統自動選更貴但更準確的模型', '<select class="f-allow-opus"><option value="true">允許</option><option value="false">不允許</option></select>') +
          settingRow('自動提交到 Paper / Auto Submit', 'AI 建議是否自動提交為 Paper 模擬訂單', '<select class="f-auto-submit"><option value="true">自動</option><option value="false">手動</option></select>') +
          settingRow('最大迭代次數 / Max Iterations', '單次 AI 推理的最大思考輪數', '<input type="number" class="f-max-iter oc-input--num mono" step="1" min="1" max="50" />') +
          '<div class="note fw-semi t-warn mt-3">Tier 2 降級 — 中度成本壓縮</div>' +
          '<div class="note fs-micro mb-1">當今日花費 ≥ 閾值 × 日硬上限時,切到此 provider+model 繼續推理</div>' +
          settingRow('觸發閾值 / Trigger (×cap)', 'fraction 0-1', '<input type="number" class="f-tier2-threshold oc-input--num mono" step="0.05" min="0" max="1" />') +
          settingRow('Tier 2 供應商 / Provider', '', '<select class="f-tier2-provider">' + providerOptions() + '</select>') +
          settingRow('Tier 2 模型 / Model', '', '<select class="f-ai-tier2-model"><option value="">—</option></select>') +
          '<div class="note fw-semi t-neg mt-3">Tier 3 降級 — 極限省錢</div>' +
          '<div class="note fs-micro mb-1">當今日花費 ≥ 閾值 × 日硬上限時,切到此 provider+model(仍受 hard_cap 攔截)</div>' +
          settingRow('觸發閾值 / Trigger (×cap)', 'fraction 0-1', '<input type="number" class="f-tier3-threshold oc-input--num mono" step="0.05" min="0" max="1" />') +
          settingRow('Tier 3 供應商 / Provider', '', '<select class="f-tier3-provider">' + providerOptions() + '</select>') +
          settingRow('Tier 3 模型 / Model', '', '<select class="f-ai-tier3-model"><option value="">—</option></select>') +
          '<button type="button" class="tag pointer settings-save mt-3" data-tone="accent">保存設置 / Save Settings</button>' +
        '</div>' +
        '<div class="col flex-1">' +
          '<div class="silk">CURRENT CONFIG · 當前配置</div>' +
          '<div class="ai-config-current note mt-1">Loading…</div>' +
        '</div>' +
      '</div>' +
    '</div>';

  var PANEL =
    '<div class="panel">' +
      '<div class="panel-t"><span class="zh">AI 供應商管理</span><span class="code">AI PROVIDER MANAGEMENT</span></div>' +
      '<div class="note mb-2">在此管理 AI 供應商。API Key 保存於本地 secrets 文件夾(不上傳、不進 Git)。badge「已驗證·Active」=密鑰已存且 L2 客戶端就緒;「已存儲·客戶端未接」=密鑰已寫入但 L2 路徑暫無對應 client(canon 7 誠實,不假成功)。</div>' +
      '<div class="row wrap gap-3 provider-grid"></div>' +
    '</div>' +
    '<div class="panel">' +
      '<div class="panel-t"><span class="zh">Scout 搜索專用</span><span class="code">SCOUT SEARCH-ONLY</span></div>' +
      '<div class="note mb-2">此區域 provider 僅供 Scout 工具搜索實時市場信息使用,<b>不參與 L2 推理</b>,不可設為默認供應商或 Tier 2/3 fallback。</div>' +
      '<div class="row wrap gap-3 scout-grid"></div>' +
    '</div>' +
    SETTINGS_HTML;

  // ═══ 模型目錄(port legacy)═══
  function catalogModelLabel(m) {
    var label = m.label || m.value || m.model_id || 'model';
    if (m.model_id && m.model_id !== m.value && label.indexOf(m.model_id) < 0) label += ' [' + m.model_id + ']';
    if (m.deprecated) label += ' · deprecated ' + (m.deprecation_date || '');
    if (m.availability_source === 'documented_alias') label += ' · alias';
    if (m.supports_tools === false) label += ' · no tools';
    if (m.provider_available === false) label += ' · provider 未列出';
    return label;
  }
  function setModelOptions(selectCls, provider, selectedValue) {
    var select = q('.' + selectCls);
    if (!select) return;
    var models = L2_PROVIDER_MODELS[provider] || L2_PROVIDER_MODELS.anthropic;
    if (!models.length) { select.innerHTML = '<option value="" disabled>無可用模型</option>'; return; }
    select.innerHTML = models.map(function (m) {
      var disabled = m.providerAvailable === false ? ' disabled' : '';
      return '<option value="' + esc(m.value) + '"' + disabled + '>' + esc(m.label) + '</option>';
    }).join('');
    var values = models.map(function (m) { return m.value; });
    var fallback = (L2_SELECT_DEFAULTS[selectCls] || {})[provider] || values[0];
    select.value = values.indexOf(selectedValue) >= 0 ? selectedValue : fallback;
  }
  function selVal(cls) { var el = q('.' + cls); return el ? el.value : ''; }
  function syncModelSelectsFromProviders() {
    setModelOptions('f-ai-model', selVal('f-provider'), selVal('f-ai-model'));
    setModelOptions('f-ai-tier2-model', selVal('f-tier2-provider'), selVal('f-ai-tier2-model'));
    setModelOptions('f-ai-tier3-model', selVal('f-tier3-provider'), selVal('f-ai-tier3-model'));
  }
  function markAIConfigDirty() { AI_CONFIG_DIRTY = true; }

  function applyLocalModelsFromStatus(status) {
    if (!status) return;
    var models = Array.isArray(status.models) ? status.models.filter(Boolean) : [];
    var defaultModel = status.default_model || '';
    if (defaultModel && models.indexOf(defaultModel) < 0) models.unshift(defaultModel);
    if (status.available && models.length) {
      L2_PROVIDER_MODELS.local_llm = models.map(function (name) {
        return { value: 'local:' + name, label: name + ' — Local LLM · no tools', providerAvailable: true };
      });
      var st = q('.local-model-status');
      if (st) st.textContent = '本地模型:' + (status.provider || 'local') + ' · ' + models.join(', ');
    } else {
      L2_PROVIDER_MODELS.local_llm = [{ value: 'local:', label: 'Local LLM — 當前不可用', providerAvailable: false }];
      var st2 = q('.local-model-status');
      if (st2) st2.textContent = '本地模型:不可用' + (status.base_url ? (' · ' + status.base_url) : '');
    }
    if (selVal('f-provider') === 'local_llm' || selVal('f-tier2-provider') === 'local_llm' || selVal('f-tier3-provider') === 'local_llm') {
      syncModelSelectsFromProviders();
    }
  }
  function renderModelCatalogStatus(catalog) {
    var el = q('.model-catalog-status');
    if (!el || !catalog || !catalog.providers) return;
    var parts = ['anthropic', 'deepseek', 'openai', 'local_llm'].map(function (provider) {
      var p = catalog.providers[provider] || {};
      var status = p.refresh_status || 'unknown';
      var source = p.cache_hit ? 'cache' : status;
      var count = p.provider_models_count != null ? p.provider_models_count : '?';
      return provider + ':' + source + '(' + count + ')';
    });
    var ttlHours = catalog.ttl_seconds ? Math.round(catalog.ttl_seconds / 3600) : '?';
    var localTtl = catalog.local_ttl_seconds || 60;
    el.textContent = '模型目錄:' + parts.join(' · ') + ' · cloud TTL ' + ttlHours + 'h · local TTL ' + localTtl + 's';
  }
  function applyProviderModelCatalog(catalog) {
    if (!catalog || !catalog.providers) return;
    L2_MODEL_CATALOG = catalog;
    ['anthropic', 'deepseek', 'openai', 'local_llm'].forEach(function (provider) {
      var p = catalog.providers[provider];
      var rows = (p && Array.isArray(p.models)) ? p.models : [];
      var usable = rows.filter(function (m) { return m && m.l2_supported !== false; });
      if (usable.length) {
        L2_PROVIDER_MODELS[provider] = usable.map(function (m) {
          return { value: m.value || m.model_id, label: catalogModelLabel(m), providerAvailable: m.provider_available !== false, deprecated: !!m.deprecated };
        });
      }
    });
    renderModelCatalogStatus(catalog);
    syncModelSelectsFromProviders();
  }
  async function loadLocalModelsForEngineSettings() {
    var d = await ocApi('/api/v1/paper/layer2/ollama/status');
    if (d && d.data) applyLocalModelsFromStatus(d.data);
  }
  async function loadProviderModelCatalog(forceRefresh) {
    var qs = forceRefresh ? '?force_refresh=true' : '';
    var d = await ocApi('/api/v1/paper/layer2/providers/models' + qs);
    if (!built) return;
    if (!d || !d.data) {
      var st = q('.model-catalog-status');
      if (st) st.textContent = '模型目錄:載入失敗';
      await loadLocalModelsForEngineSettings();
      return;
    }
    applyProviderModelCatalog(d.data);
  }
  async function refreshProviderModels() {
    await loadProviderModelCatalog(true);
    toast('模型目錄已刷新 / Model catalog refreshed', 'success');
  }

  // ═══ 供應商 badge(port legacy _renderProviderBadge;canon 7 不假 Active)═══
  function providerSourceLabel(info) {
    if (!info || !info.configured) return '未配置';
    if (info.source === 'provider_store') return 'GUI provider store';
    if (info.source === 'env') return 'process env';
    if (info.source === 'legacy_secret_file') return 'legacy secret file';
    return info.source || 'unknown';
  }
  function renderProviderBadge(provider, info) {
    if (provider === 'local_llm') return; // 由 checkOllamaStatus 管理,避免互蓋
    var badge = q('.pb-' + provider);
    if (badge) {
      var text = '客戶端未接 / Not wired', tone = 'muted';
      if (info.configured) {
        if (info.client_implemented) {
          if (info.validated) { text = '已驗證 / Active'; tone = 'good'; }
          else { text = '已存儲 · 未驗證'; tone = 'warn'; }
        } else { text = '已存儲 · 客戶端未接'; tone = 'warn'; }
      } else {
        if (info.client_implemented) { text = '待密鑰 / Awaiting key'; tone = 'muted'; }
        else { text = '客戶端未接 / Not wired'; tone = 'muted'; }
      }
      setTag(badge, text, tone);
    }
    var detail = q('.pd-' + provider);
    if (detail) {
      var source = providerSourceLabel(info);
      var validation = info && info.validation_status ? (' · ' + info.validation_status) : '';
      var clearHint = info && info.configured && info.source_clearable === false ? ' · read-only source' : '';
      detail.textContent = '來源:' + source + validation + clearHint;
    }
    var input = q('.pk-' + provider);
    if (input && info.configured && info.masked) {
      var v = info.validated ? '已驗證' : '已存儲未驗證';
      input.placeholder = v + ':' + info.masked + '(輸入新值替換)';
    }
  }
  async function loadProviderStatus() {
    var d = await ocApi('/api/v1/paper/layer2/providers/status');
    if (!built) return;
    if (!d || !d.data || !d.data.providers) return;
    Object.keys(d.data.providers).forEach(function (name) { renderProviderBadge(name, d.data.providers[name]); });
  }

  // ═══ Ollama 檢測(port legacy checkOllamaStatus;/paper/layer2/ollama/status)═══
  async function checkOllamaStatus() {
    var badge = q('.pb-local_llm'), detail = q('.ollama-status-detail'), modelsLine = q('.ollama-models-line');
    if (badge) setTag(badge, '檢測中…', 'muted');
    if (detail) detail.textContent = '正在連接 Ollama…';
    var d = await ocApi('/api/v1/paper/layer2/ollama/status');
    if (!built) return;
    if (!d || !d.data) {
      if (badge) setTag(badge, '離線', 'bad');
      if (detail) detail.textContent = '無法連接後端,請確認服務正在運行。';
      return;
    }
    var s = d.data;
    applyLocalModelsFromStatus(s);
    if (s.available) {
      if (badge) setTag(badge, '已連接', 'good');
      var modelList = (s.models || []).join(', ') || s.default_model;
      if (modelsLine) modelsLine.textContent = 'Ollama — 可用模型:' + modelList;
      if (detail) detail.textContent = '已連接 ' + s.base_url + ' · 默認模型:' + s.default_model + ' · 共 ' + (s.model_count != null ? s.model_count : '?') + ' 個模型';
    } else {
      if (badge) setTag(badge, '不可用', 'bad');
      if (detail) detail.textContent = 'Ollama 未響應(' + s.base_url + ')。請確認 Ollama 服務已啟動(ollama serve)。';
    }
  }

  // ═══ 寫①:保存 provider 密鑰(POST /paper/layer2/config {provider_keys};response-gated envelope)═══
  async function saveProviderKey(provider) {
    var input = q('.pk-' + provider);
    if (!input) { toast('未知供應商 / Unknown provider', 'error'); return; }
    var key = input.value.trim();
    if (!key) { toast('請輸入 API Key / Please enter an API key', 'error'); return; }
    var fmt = KEY_FORMATS[provider];
    if (fmt) {
      if (fmt.prefix && key.indexOf(fmt.prefix) !== 0) { toast('格式錯誤:' + fmt.hint, 'error'); return; }
      if (key.length < fmt.minLen) { toast('Key 太短(至少 ' + fmt.minLen + ' 個字符)', 'error'); return; }
    }
    var d = await ocPost('/api/v1/paper/layer2/config', { provider_keys: (function () { var o = {}; o[provider] = key; return o; })() });
    if (!d) { toast('保存失敗(後端無響應)/ Backend not responding', 'error'); return; }
    // 後端回 envelope:provider_results / provider_errors / provider_status。
    var errs = (d.data && d.data.provider_errors) || [];
    var results = (d.data && d.data.provider_results) || [];
    var myErr = errs.filter(function (e) { return e.provider === provider; })[0];
    var myResult = results.filter(function (r) { return r.provider === provider; })[0];
    if (myErr) {
      toast(provider + ' 保存失敗:' + (myErr.detail || myErr.reason_code), 'error');
    } else if (myResult) {
      input.value = '';
      if (myResult.client_implemented) {
        var hot = myResult.hot_reloaded ? '(已熱重載客戶端)' : '';
        if (myResult.validated) toast(provider + ' API Key 已驗證並保存 ' + hot, 'success');
        else toast(provider + ' API Key 已保存,但未完成可用性驗證', 'warn');
      } else {
        // 誠實提示:key 落地但推理路徑未接,避免以為立即生效(canon 7 不假成功)。
        toast(provider + ' Key 已存儲;客戶端尚未實裝(僅存盤待用)', 'warn');
      }
      if (d.data && d.data.provider_status && d.data.provider_status.providers) {
        Object.keys(d.data.provider_status.providers).forEach(function (name) { renderProviderBadge(name, d.data.provider_status.providers[name]); });
      } else { loadProviderStatus(); }
      if (['anthropic', 'openai', 'deepseek', 'local_llm'].indexOf(provider) >= 0) await loadProviderModelCatalog(true);
    } else {
      toast(provider + ' 已提交,但後端未返回結果 — 請檢查 / 重試', 'warn');
      loadProviderStatus();
    }
  }

  // ═══ 寫②:清除 provider 密鑰(DELETE /paper/layer2/providers/{};★ typed-confirm CLEAR,逐字保留不弱化)═══
  // W-AUDIT-7c:API Key clear 屬 governance critical 寫(刪 secrets 文件 + 移進程 env)。
  //   用 openTypedConfirmModal 取代 native confirm() 防誤觸;await 包 try/catch(singleton reject 不靜默),
  //   cancel 顯 toast 不靜默 return。DELETE 只在 phrase='CLEAR' 相符 + 確認後才送(安全閘,response-gated)。
  async function clearProviderKey(provider) {
    if (!q('.pk-' + provider)) { toast('未知供應商', 'error'); return; }
    if (typeof window.openTypedConfirmModal !== 'function') { toast('確認對話框不可用 / Confirm dialog unavailable', 'error'); return; }
    var proceed;
    try {
      proceed = await window.openTypedConfirmModal({
        title: '清除 API Key / Clear API Key — ' + provider,
        body: '此操作將:\n  1. 刪除 GUI provider-store secrets 文件\n  2. 從當前進程 env 移除 API key\n\n若該 provider 仍由 process env 或 legacy secret file 提供,清除後仍會以 read-only source 顯示。\n如需完全停用,需同步移除部署 env 或 legacy secret file。',
        phrase: 'CLEAR',
        confirmLabel: '確認清除 / Clear Key',
        confirmClass: 'oc-btn-danger',
        impact: provider + ' provider 立即離線;fallback chain 重新計算',
        rollback: '需重新輸入 API key 才能恢復'
      });
    } catch (err) {
      if (err && err.message === 'modal already open') {
        toast('已有確認對話框打開,請先完成當前操作 / Another confirm dialog is open', 'warn');
      } else {
        toast('開啟確認對話框失敗 / Open confirm dialog failed: ' + (err && err.message || err), 'error');
      }
      return;
    }
    if (!proceed) { toast('已取消清除 ' + provider + ' / Clear cancelled', 'neutral'); return; }
    var d = await ocApi('/api/v1/paper/layer2/providers/' + encodeURIComponent(provider), { method: 'DELETE' });
    if (!d) { toast('清除失敗(後端無響應)', 'error'); return; }
    if (d.data && d.data.deleted) toast(provider + ' API Key 已清除', 'success');
    else toast(provider + ' 無密鑰可清除(已是空狀態)', 'neutral');
    if (d.data && d.data.provider_status && d.data.provider_status.providers) {
      Object.keys(d.data.provider_status.providers).forEach(function (name) { renderProviderBadge(name, d.data.provider_status.providers[name]); });
    } else { loadProviderStatus(); }
    if (['anthropic', 'openai', 'deepseek', 'local_llm'].indexOf(provider) >= 0) await loadProviderModelCatalog(true);
  }

  // ═══ 寫③:保存 AI 設置(POST /paper/layer2/config 全 body;response-gated d.action_result==='success')═══
  function numOr(cls, dflt) { var el = q('.' + cls); var n = el ? parseFloat(el.value) : NaN; return isNaN(n) ? dflt : n; }
  function intOr(cls, dflt) { var el = q('.' + cls); var n = el ? parseInt(el.value, 10) : NaN; return isNaN(n) ? dflt : n; }
  async function saveAIConfig() {
    syncModelSelectsFromProviders();
    var body = {
      daily_hard_cap_usd: numOr('f-hard-cap', 2),
      adaptive_base_daily_usd: numOr('f-base-daily', 8),
      adaptive_max_multiplier: numOr('f-max-mult', 2),
      adaptive_min_multiplier: numOr('f-min-mult', 0.3),
      allow_opus_upgrade: selVal('f-allow-opus') === 'true',
      adaptive_enabled: selVal('f-enabled') === 'true',
      default_model: selVal('f-ai-model'),
      default_provider: selVal('f-provider'),
      auto_submit_to_paper: selVal('f-auto-submit') === 'true',
      max_iterations: intOr('f-max-iter', 15),
      fallback_tier2_threshold_pct: numOr('f-tier2-threshold', 0.5),
      fallback_tier2_provider: selVal('f-tier2-provider'),
      fallback_tier2_model: selVal('f-ai-tier2-model'),
      fallback_tier3_threshold_pct: numOr('f-tier3-threshold', 0.85),
      fallback_tier3_provider: selVal('f-tier3-provider'),
      fallback_tier3_model: selVal('f-ai-tier3-model'),
    };
    AI_CONFIG_SAVING = true;
    try {
      var d = await ocPost('/api/v1/paper/layer2/config', body);
      if (d && d.action_result === 'success') {
        AI_CONFIG_DIRTY = false;
        toast('AI 設置已保存', 'success');
        load();
      } else if (d && d.action_result) {
        var codes = (d.reason_codes || []).join(', ') || d.action_result;
        toast('保存失敗:' + codes, 'error');
      } else {
        toast('保存失敗:後端拒絕或無響應,當前選擇不會自動覆蓋', 'error');
      }
    } finally {
      AI_CONFIG_SAVING = false;
    }
  }

  // ═══ 當前配置(port legacy loadConfig;/paper/layer2/config)═══
  function pct(v, dflt) { return (typeof window.ocPct === 'function') ? window.ocPct(v != null ? v : dflt) : String(v != null ? v : dflt); }
  async function loadConfig() {
    var d = await ocApi('/api/v1/paper/layer2/config');
    if (!built) return;
    var box = q('.ai-config-current');
    if (!d || !d.data) { if (box) box.textContent = 'No config'; return; }
    var cfg = d.data;
    var t2 = (cfg.fallback_tier2_provider || '?') + ' / ' + (cfg.fallback_tier2_model || '?') + ' @ ' + pct(cfg.fallback_tier2_threshold_pct, 0.5);
    var t3 = (cfg.fallback_tier3_provider || '?') + ' / ' + (cfg.fallback_tier3_model || '?') + ' @ ' + pct(cfg.fallback_tier3_threshold_pct, 0.85);
    var fields = [
      ['默認供應商', cfg.default_provider || 'anthropic'],
      ['默認模型(tier)', cfg.default_model || 'sonnet'],
      ['日硬上限', '$' + (cfg.daily_hard_cap_usd != null ? cfg.daily_hard_cap_usd : 2)],
      ['彈性基準', '$' + (cfg.adaptive_base_daily_usd != null ? cfg.adaptive_base_daily_usd : 8)],
      ['彈性範圍', (cfg.adaptive_min_multiplier != null ? cfg.adaptive_min_multiplier : 0.3) + 'x - ' + (cfg.adaptive_max_multiplier != null ? cfg.adaptive_max_multiplier : 2) + 'x'],
      ['自適應', cfg.adaptive_enabled !== false ? '啟用' : '禁用'],
      ['最大迭代', cfg.max_iterations != null ? cfg.max_iterations : 15],
      ['自動提交', cfg.auto_submit_to_paper ? '是' : '否'],
      ['搜索引擎', (cfg.search_providers_enabled || []).join(', ') || EMPTY],
      ['Tier 2 降級', t2],
      ['Tier 3 降級', t3],
    ];
    if (box) {
      box.innerHTML = '<table class="tbl"><tbody>' + fields.map(function (f) {
        return '<tr><td class="t-muted">' + esc(f[0]) + '</td><td class="num t-right">' + esc(String(f[1])) + '</td></tr>';
      }).join('') + '</tbody></table>';
    }
    if (AI_CONFIG_DIRTY || AI_CONFIG_SAVING) return;
    // 回填表單(僅在使用者未編輯/未保存中時)。
    setInputIfEmpty('f-hard-cap', cfg.daily_hard_cap_usd != null ? cfg.daily_hard_cap_usd : 2);
    setInputIfEmpty('f-base-daily', cfg.adaptive_base_daily_usd != null ? cfg.adaptive_base_daily_usd : 8);
    setInputIfEmpty('f-max-mult', cfg.adaptive_max_multiplier != null ? cfg.adaptive_max_multiplier : 2);
    setInputIfEmpty('f-min-mult', cfg.adaptive_min_multiplier != null ? cfg.adaptive_min_multiplier : 0.3);
    setInputIfEmpty('f-max-iter', cfg.max_iterations != null ? cfg.max_iterations : 15);
    setSelect('f-allow-opus', cfg.allow_opus_upgrade !== false ? 'true' : 'false');
    setSelect('f-enabled', cfg.adaptive_enabled !== false ? 'true' : 'false');
    setSelect('f-auto-submit', cfg.auto_submit_to_paper ? 'true' : 'false');
    if (cfg.default_provider) setSelect('f-provider', cfg.default_provider);
    setModelOptions('f-ai-model', selVal('f-provider'), cfg.default_model);
    if (cfg.fallback_tier2_threshold_pct != null) setInput('f-tier2-threshold', cfg.fallback_tier2_threshold_pct);
    if (cfg.fallback_tier2_provider) setSelect('f-tier2-provider', cfg.fallback_tier2_provider);
    setModelOptions('f-ai-tier2-model', selVal('f-tier2-provider'), cfg.fallback_tier2_model);
    if (cfg.fallback_tier3_threshold_pct != null) setInput('f-tier3-threshold', cfg.fallback_tier3_threshold_pct);
    if (cfg.fallback_tier3_provider) setSelect('f-tier3-provider', cfg.fallback_tier3_provider);
    setModelOptions('f-ai-tier3-model', selVal('f-tier3-provider'), cfg.fallback_tier3_model);
  }
  function setInput(cls, v) { var el = q('.' + cls); if (el) el.value = v; }
  function setInputIfEmpty(cls, v) { var el = q('.' + cls); if (el && !el.value) el.value = v; }
  function setSelect(cls, v) { var el = q('.' + cls); if (el) el.value = v; }

  // ═══ 控件接線(事件委派:provider 卡按鈕;設置變更 dirty;保存/刷新)═══
  function wire() {
    var slot = root();
    if (!slot) return;
    // provider 卡按鈕(保存/清除/檢測)事件委派。
    slot.addEventListener('click', function (ev) {
      var t = ev.target;
      var btn = (t && typeof t.closest === 'function') ? t.closest('button[data-key], button.settings-save, button.models-refresh') : null;
      if (!btn) return;
      if (btn.classList.contains('settings-save')) { saveAIConfig(); return; }
      if (btn.classList.contains('models-refresh')) { refreshProviderModels(); return; }
      var key = btn.getAttribute('data-key');
      if (!key) return;
      if (btn.classList.contains('pv-save')) saveProviderKey(key);
      else if (btn.classList.contains('pv-clear')) clearProviderKey(key);
      else if (btn.classList.contains('pv-detect')) checkOllamaStatus();
    });
    // 供應商切換 → dirty + 重算模型下拉;模型切換 → dirty。
    ['f-provider', 'f-tier2-provider', 'f-tier3-provider'].forEach(function (cls) {
      var el = q('.' + cls);
      if (el) el.addEventListener('change', function () { markAIConfigDirty(); syncModelSelectsFromProviders(); });
    });
    ['f-ai-model', 'f-ai-tier2-model', 'f-ai-tier3-model', 'f-enabled', 'f-allow-opus', 'f-auto-submit', 'f-hard-cap', 'f-base-daily', 'f-max-mult', 'f-min-mult', 'f-max-iter', 'f-tier2-threshold', 'f-tier3-threshold'].forEach(function (cls) {
      var el = q('.' + cls);
      if (el) el.addEventListener('change', markAIConfigDirty);
    });
  }

  // ═══ 主檔掛鉤:render(建骨架)+ load(4 GET 渲染)═══
  function render(hostEl) {
    if (hostEl) host = hostEl;
    var slot = root();
    if (!slot || built) return;
    slot.innerHTML = PANEL;
    built = true;
    var grid = q('.provider-grid');
    if (grid) grid.innerHTML = PROVIDERS.map(providerCardHtml).join('');
    var scout = q('.scout-grid');
    if (scout) scout.innerHTML = providerCardHtml(SCOUT_PROVIDER);
    applyTagTones(slot);
    syncModelSelectsFromProviders();
    wire();
  }
  async function load() {
    if (!built) return;
    await loadProviderModelCatalog(false);
    await Promise.allSettled([loadProviderStatus(), loadConfig()]);
    checkOllamaStatus();
  }

  // 註冊 companion hook(主檔 view-ai.js 於 render/loadAll 驅動;非獨立 OC_NATIVE_VIEWS)。
  window.OC_AI_PROVIDERS = { render: render, load: load };
})();
