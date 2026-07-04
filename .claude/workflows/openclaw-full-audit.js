// OpenClaw 全盤多視角審計 — saved workflow（ultracode 編排形態的持久化設置）
// 調用方式、Stage 0 baseline freeze、Stage 3 PA 驗真層、Stage 4 PM 裁決見
//   .claude/skills/ultracode-full-audit/SKILL.md（主會話前後置由 conductor 親自做）
// 設計鐵律（經 2026-06-10 對抗審查確立）：
//   去重只在「呈現層」聚簇，verify 與 fix 永遠按原始 finding 粒度跑 —— 合併絕不縮減
//   對抗暴露面、絕不掩蓋同位置的第二個缺陷。defect_type 不進去重主鍵（各軸盲選必分叉）。
export const meta = {
  name: 'openclaw-full-audit',
  description: 'OpenClaw 全盤多視角審計（Stage 2-3 並行段）：審計群 fan-out + negative-space 盲區 → 每軸原始 finding 對抗複核（高危加可達性第三視角）+ seam critic → 呈現層機械聚簇（無損）→（可選）修復+複審 → 回歸；read-only 硬邊界內建',
  whenToUse: 'ultracode 啟用且 operator 要求全盤審查/全面優化檢查/冷酷對抗審計時，由主會話（conductor）按 ultracode-full-audit skill 調用；Stage 0 凍結與 Stage 3-4 收斂由主會話親做；默認 report-only',
  phases: [
    { title: 'Audit', detail: '審計 agent 並行 fan-out（默認 10 軸；read-only 邊界+本輪 focus 注入；finding 後置標註 defect_type/anchor；附 negative-space 盲區）' },
    { title: 'Verify', detail: '每軸原始 C/H+目的承載 M finding 雙質疑者（證據鏈∥影響）+ 高危類加第三質疑者（可達性）+ seam critic 審軸交界盲區' },
    { title: 'Cluster', detail: '對 confirmed 按 (file, anchor) 無損機械聚簇呈現，標 hit_axes（純報告層，不改 verify/fix 粒度）' },
    { title: 'Fix', detail: 'args.fix=true 時：對每條 confirmed 原始 finding（非聚簇體）E1 worktree 修復 → E2 複審' },
    { title: 'Regression', detail: '有修復落地時：E4 全量回歸對照 memory BASELINE' },
  ],
}

// defect_type 後置多選標註（含 other），僅供呈現層聚簇與 corroboration，不進去重主鍵、不限制調查範圍
const DEFECT_TYPES = ['hardcoded-config', 'missing-gate', 'auth-bypass', 'fake-success', 'dead-code', 'duplicate-logic', 'leakage', 'drift-source-runtime', 'lineage-gap', 'untruthful-ai', 'replay-misuse', 'perf-hotpath', 'index-broken', 'doc-stale', 'test-blindspot', 'bybit-incompat', 'math-error', 'schema-issue', 'secret-leak', 'readability-debt', 'over-gate', 'evolution-blocker', 'other']
// 高危類：強制加第三質疑者（可達性/可利用性）
const HIGH_RISK_TYPES = ['auth-bypass', 'secret-leak', 'missing-gate', 'leakage', 'replay-misuse']
// 機能/摩擦類（over-gate=負淨貢獻控制、evolution-blocker=進化凍死）：「生產不可達」正是缺陷本身，不適用 latent 降級
const CAPABILITY_TYPES = ['over-gate', 'evolution-blocker']
// 目的承載類：MEDIUM 也進對抗複核（削弱可審計性/進化能力/盈利的缺陷不得沉底）
const GOAL_TYPES = ['over-gate', 'evolution-blocker', 'lineage-gap']

const FINDINGS_SCHEMA = {
  type: 'object', required: ['verdict', 'confidence', 'findings'], additionalProperties: false,
  properties: {
    verdict: { type: 'string', enum: ['PASS', 'FINDINGS', 'BLOCKED', 'NO-OP'] },
    confidence: { type: 'string', enum: ['high', 'med', 'low'] },
    findings: { type: 'array', items: {
      type: 'object', required: ['title', 'severity', 'classification', 'confidence', 'evidence', 'impact'], additionalProperties: false,
      properties: {
        title: { type: 'string' },
        severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] },
        classification: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        confidence: { type: 'string', enum: ['high', 'med', 'low'] },
        evidence: { type: 'string' },
        impact: { type: 'string' },
        file: { type: 'string' },
        // 後置標註：寫完 finding 後再填，不前置選（防錨定淺化調查）
        defect_type: { type: 'array', items: { type: 'string', enum: DEFECT_TYPES } },
        // 聚簇錨點：函數/配置鍵/常數名（非行號，行號漂移）；配置類 finding 一律填 config-key
        symbol_anchor: { type: 'string' },
        // 跨檔同源：症狀檔的 finding 認為根因在上游時，填上游 檔::符號
        root_anchor: { type: 'string' },
        fix_hint: { type: 'string' },
      },
    } },
    // 有嫌疑但無證據 + 本域 negative-space 盲區（按 SOP 本該查但證據不足/未展開）：供 PA re-probe，不沉默丟棄
    assumptions: { type: 'array', items: {
      type: 'object', required: ['note', 'why_unproven'], additionalProperties: false,
      properties: { note: { type: 'string' }, why_unproven: { type: 'string' } },
    } },
    report_path: { type: 'string' },   // 落盤的 workspace 報告相對路徑（main/PA 按需讀全文，evidence 不進 return）
  },
}

const VERDICT_SCHEMA = {
  type: 'object', required: ['refuted', 'reason'], additionalProperties: false,
  properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } },
}
// 可達性第三視角：unreachable=生產 gate/配置/調用圖下不可觸發 → 降級為 latent
const REACH_SCHEMA = {
  type: 'object', required: ['reachable', 'reason'], additionalProperties: false,
  properties: { reachable: { type: 'string', enum: ['reachable', 'latent', 'unknown'] }, reason: { type: 'string' } },
}
const SEAM_SCHEMA = {
  type: 'object', required: ['reprobes'], additionalProperties: false,
  properties: { reprobes: { type: 'array', items: {
    type: 'object', required: ['seam', 'assign_axis', 'why'], additionalProperties: false,
    properties: { seam: { type: 'string' }, assign_axis: { type: 'string' }, why: { type: 'string' } },
  } } },
}

const FIX_SCHEMA = {
  type: 'object', required: ['status', 'summary'], additionalProperties: false,
  properties: { status: { type: 'string', enum: ['FIXED', 'BLOCKED', 'NO-OP'] }, summary: { type: 'string' }, files: { type: 'string' } },
}
const REVIEW_SCHEMA = {
  type: 'object', required: ['verdict', 'issues'], additionalProperties: false,
  properties: { verdict: { type: 'string', enum: ['APPROVE', 'RETURN'] }, issues: { type: 'string' } },
}

// ---- 確定性檔案路徑規範化（workflow 統一施加，不讓各 agent 心算）----
// 剝 worktree/絕對前綴 → 相對 srv/ 的 POSIX 小寫路徑；symlink 正本 .claude 已在 srv 下
function normalizeFile(f) {
  if (!f) return null
  let p = String(f).split('\\').join('/').toLowerCase().trim()
  const i = p.lastIndexOf('/srv/')
  if (i >= 0) p = p.slice(i + 5)
  else if (p.startsWith('srv/')) p = p.slice(4)
  return p || null
}
// 聚簇主鍵：規範化檔 + 符號錨點；缺 anchor 者回 null（不進機械聚簇，直接透傳交 PA）
function clusterKey(f) {
  const file = normalizeFile(f.file)
  if (!file || !f.symbol_anchor) return null
  return file + '::' + String(f.symbol_anchor).toLowerCase().trim()
}

// ---- 參數（args 全部可選）----
// 2026-07-04 實證(cold-audit R2):harness 可能將 args 以 JSON 字串傳入,未 parse 會靜默降級到默認配置
const args_ = (typeof args === 'string') ? (() => { try { return JSON.parse(args) } catch (_e) { return null } })() : args
const scope = (args_ && args_.scope) || 'srv/ 全倉（rust engine、control_api、GUI、helper_scripts、.claude 配置、治理文檔）'
const axes = (args_ && args_.axes) || ['CC', 'FA', 'E3', 'BB', 'QC', 'MIT', 'AI-E', 'E5', 'A3', 'R4']
const doFix = !!(args_ && args_.fix)
const maxFixes = (args_ && args_.max_fixes) || 5
const focus = (args_ && args_.focus) || null
const baseline = (args_ && args_.baseline) || null

const READONLY = 'read-only audit 硬邊界：不修復 / 不改功能 / 不部署 / 不重啟 runtime / 不改 DB schema / 不動 live·demo·paper auth / 不啟動交易 / 不改 risk·strategy·TOML live config。Linux 證據僅允許 ssh trade-core read-only 命令；遇任何 rebuild·restart·migration·auth·trading mutation 需求立即停止、標 BLOCKED 回報。'
const ANNOTATE = '【後置標註，寫完每條 finding 後再填，不要讓它影響你的調查方向】defect_type：從枚舉多選（覆蓋不全選 other，可多選——多視角分歧是 corroboration 證據不是錯誤）；symbol_anchor：缺陷所在函數/配置鍵/常數名（涉配置或常數的一律填 config-key/TOML-key/env-var 名，跨軸天然對齊）；root_anchor：若你判斷症狀的根因在上游別處，填上游 檔::符號。這些僅供事後機械聚簇展示，絕不限制你的調查範圍與深度。severity 計價校正（裁決座標）：over-gate/evolution-blocker 類 impact 以被壓制的期望盈利/被凍結的進化價值計、readability-debt/duplicate-logic 類以重複開發成本（被 agent 讀改頻率×體量×剩餘壽命）計，不以工程風險計——風控雙向：負淨貢獻控制（拒真無風險換益/凍死槓桿/摩擦>保護）與缺失控制同類缺陷。'

function focusFor(ax) {
  if (!focus) return ''
  const f = typeof focus === 'string' ? focus : focus[ax]
  return f ? `\n本輪額外必查項（靶向假設，非範圍上限；你的 role SOP 全量仍是基準範圍）：${f}` : ''
}

phase('Audit')
log(`範圍：${scope}；審計軸（${axes.length}）：${axes.join(', ')}；模式：${doFix ? 'fix' : 'report-only'}${baseline ? '；基線已凍結' : '；⚠️ 未傳 baseline（建議主會話先 Stage 0 凍結三端 SHA）'}`)
const audits = (await parallel(axes.map(ax => () =>
  agent(
    `按你的 role SOP 與掛載 skills 對以下範圍做全量審計（你的 role 範疇即審計範圍，下列 focus 僅為額外靶向，不是範圍上限）：${scope}。\n${READONLY}${baseline ? '\n凍結基線（affected line 對齊此基線）：' + baseline : ''}${focusFor(ax)}\n每條 finding 標：FACT/INFERENCE/ASSUMPTION 分類、severity、confidence、evidence（file:line 或命令輸出）、impact、fix 方向。全量輸出含 LOW/INFO/不確定項。\n${ANNOTATE}\nnegative-space（達最高對抗標準的反向自審）：在 assumptions 額外列出「你這一域按 SOP 本該覆蓋、但本輪證據不足或未深入展開的盲區」，每條 note=盲區、why_unproven=未展開原因——這是給 PA 的 re-probe 線索，不得因無證據而沉默略過。報告按你的完成序列落盤 workspace，並把該報告的相對路徑填入 report_path（main 只收結構化摘要，evidence/impact 全文留報告，不靠 return 回傳）。`,
    { agentType: ax, label: `audit:${ax}`, phase: 'Audit', schema: FINDINGS_SCHEMA },
  ).then(r => r && { axis: ax, ...r }),
))).filter(Boolean)

// 覆蓋洞顯式化：BLOCKED/未回報軸 ≠ 該域清白（verdict 欄位有消費者，不再靜默）
const coverage_holes = axes.filter(ax => !audits.some(a => a.axis === ax)).concat(audits.filter(a => a.verdict === 'BLOCKED').map(a => a.axis))
if (coverage_holes.length) log(`⚠️ 覆蓋洞：${coverage_holes.join(', ')} BLOCKED/未回報 — 本輪結果不構成該域清白證明`)

const all = audits.flatMap(a => (a.findings || []).map(f => ({ ...f, axis: a.axis })))
const assumptions = audits.flatMap(a => (a.assumptions || []).map(x => ({ ...x, axis: a.axis })))
const critical = all.filter(f => f.severity === 'CRITICAL' || f.severity === 'HIGH' || (f.severity === 'MEDIUM' && (f.defect_type || []).some(t => GOAL_TYPES.includes(t))))
log(`共 ${all.length} 條 finding（C/H+目的承載 M ${critical.length} 進對抗複核，其餘 M/L/INFO 直入報告）+ ${assumptions.length} 條待證假設/盲區`)

phase('Verify')
// 每軸原始 finding 各跑質疑者（粒度不變，對抗暴露面不被去重壓縮）；高危類追加可達性第三視角
const verifyJobs = critical.map(f => () => {
  const isHighRisk = f.severity === 'CRITICAL' || (f.defect_type || []).some(t => HIGH_RISK_TYPES.includes(t))
  const isCapability = (f.defect_type || []).some(t => CAPABILITY_TYPES.includes(t))
  const queries = [
    () => agent(
      `嘗試反駁這條審計發現（拿不出具體反證則 refuted=false，不為對抗而對抗）：[${f.axis}] ${f.title}\n分類：${f.classification}\n證據：${f.evidence}\n檔案：${f.file || '未指明'}\n你的視角：證據鏈成立性 — 引用的檔案/行/輸出是否真實存在、結論是否過度推斷（INFERENCE/ASSUMPTION 尤其要查）。實地核查後下結論。\n${READONLY}`,
      { label: `verify-evid:${f.axis}`, phase: 'Verify', schema: VERDICT_SCHEMA },
    ),
    () => agent(
      `嘗試反駁這條審計發現（拿不出具體反證則 refuted=false）：[${f.axis}] ${f.title}\n證據：${f.evidence}\n影響：${f.impact}\n你的視角：影響真實性 — 按證據實地復查，問題是否真實、severity 是否高估。\n${READONLY}`,
      { label: `verify-impact:${f.axis}`, phase: 'Verify', schema: VERDICT_SCHEMA },
    ),
  ]
  const reachJob = isHighRisk
    ? agent(
        `可達性/可利用性核查：[${f.axis}] ${f.title}\n證據：${f.evidence}\n檔案：${f.file || '未指明'}\n在當前生產 gate 鏈 / 配置 / 調用圖下，這條路徑是否真能被觸發？給出可達或不可達的具體證據鏈。reachable=生產可觸發 / latent=代碼級存在但生產不可達 / unknown=證據不足。\n${READONLY}`,
        { label: `verify-reach:${f.axis}`, phase: 'Verify', schema: REACH_SCHEMA },
      ).then(r => r || { reachable: 'unknown', reason: 'no-result' })
    : Promise.resolve(null)
  return Promise.all([parallel(queries), reachJob]).then(([vs, reach]) => {
    const votes = vs.filter(Boolean)
    const refutedCount = votes.filter(v => v.refuted).length
    const quorum = votes.length === 2   // 質疑者死亡=法定人數不足，降 disputed，不得靜默 confirmed
    return {
      ...f,
      confirmed: quorum && refutedCount === 0,
      disputed: refutedCount === 1 || (!quorum && refutedCount === 0),
      reachable: reach ? reach.reachable : null,
      // capability/摩擦類「不可達」是缺陷本身（凍死/鎖死），不降級
      latent: reach ? (reach.reachable === 'latent' && !isCapability) : false,
      refutations: votes.map(v => v.reason).join(' | '),
    }
  })
})
// seam critic 與 verify 並行：審 10 軸交界的無主盲區，產 re-probe 指令（不直接成 finding，必經一次帶證據審計才升格）
const seamJob = agent(
  `你是 cross-axis-seam critic。以下是本輪 ${axes.length} 軸（${axes.join('/')}）審計已報的 finding 標題清單：\n${all.map(f => `- [${f.axis}] ${f.title}`).join('\n') || '（無）'}\n\n專審「軸與軸交界、無單一 owner 的無主地帶」可能漏報的系統性盲區（例：source↔runtime drift、authority chain 跨語言 lineage、Rust↔Python IPC 邊界、ML↔策略交接、GUI↔Rust authority 一致性）。對每個盲區產出一條 re-probe 指令：seam=盲區描述、assign_axis=該派哪個軸去帶證據查、why=為何現有軸分工會漏它。不要重複已報 finding，只找縫隙。`,
  { label: 'seam-critic', phase: 'Verify', schema: SEAM_SCHEMA },
)
const [verified, seam] = await Promise.all([parallel(verifyJobs), seamJob])
const vOk = verified.filter(Boolean)
const confirmed = vOk.filter(f => f.confirmed && !f.latent)  // latent=生產不可達，降級不進修復隊列
const latent = vOk.filter(f => f.confirmed && f.latent)
const disputed = vOk.filter(f => f.disputed)
log(`對抗複核：confirmed ${confirmed.length} / latent(不可達降級) ${latent.length} / disputed ${disputed.length} / refuted ${vOk.length - confirmed.length - latent.length - disputed.length}；seam re-probe ${(seam && seam.reprobes || []).length} 條`)

phase('Cluster')
// 純呈現層：對 confirmed 按 (file, anchor) 無損聚簇 —— members 全保留，不改 severity/confidence/不影響 fix 粒度
const buckets = new Map()
const ungrouped = []
for (const f of confirmed) {
  const k = clusterKey(f)
  if (!k) { ungrouped.push(f); continue }
  if (!buckets.has(k)) buckets.set(k, [])
  buckets.get(k).push(f)
}
const consensus = []
for (const [k, members] of buckets) {
  const hitAxes = [...new Set(members.map(m => m.axis))]
  consensus.push({
    key: k,
    members,                              // 無損保留：每成員自帶 axis/evidence/impact/fix_hint
    hit_axes: hitAxes,
    multi_axis: hitAxes.length > 1,       // 多軸共置 → 提示 PA 查是否異質 corroboration（不自動升 confidence）
    severities: [...new Set(members.map(m => m.severity))],
    defect_types: [...new Set(members.flatMap(m => m.defect_type || []))],
  })
}
log(`聚簇：${consensus.length} 簇（其中多軸共置 ${consensus.filter(c => c.multi_axis).length}）+ ${ungrouped.length} 條無 anchor 透傳 PA`)

let fixes = []
if (doFix && confirmed.length) {
  phase('Fix')
  // 對「每條 confirmed 原始 finding」修復，不對聚簇體 —— 確保同位置的第二個缺陷不被合併掩蓋
  // 修復隊列按 severity→可達性排序後再截斷（防 CRITICAL 被軸序擠出隊列）
  const SEV_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4 }
  const queue = [...confirmed].sort((a, b) => (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9) || (b.reachable === 'reachable' ? 1 : 0) - (a.reachable === 'reachable' ? 1 : 0)).slice(0, maxFixes)
  if (confirmed.length > maxFixes) log(`修復上限 ${maxFixes}，餘 ${confirmed.length - maxFixes} 條留報告交 PM`)
  fixes = (await pipeline(queue,
    f => agent(
      `修復以下已對抗確認的審計發現（最小安全解，不擴 scope）：[${f.axis}] ${f.title}\n證據：${f.evidence}\n檔案：${f.file || '見證據'}\n錨點：${f.symbol_anchor || '見證據'}\n修復提示：${f.fix_hint || '無'}\n遵守你的方案執行協議：修復→自測→回報。`,
      { agentType: 'E1', label: `fix:${(f.symbol_anchor || f.file || f.title).slice(0, 28)}`, phase: 'Fix', isolation: 'worktree', schema: FIX_SCHEMA },
    ).then(r => ({ finding: f, fix: r })),
    r => (r && r.fix && r.fix.status === 'FIXED')
      ? agent(
          `對抗複審剛完成的修復：${r.finding.title}\n修復摘要：${r.fix.summary}\n涉及檔案：${r.fix.files || ''}\n按 pr-adversarial-review SOP 全量審；RETURN 時列具體 issue。`,
          { agentType: 'E2', label: `review:${(r.finding.symbol_anchor || r.finding.file || r.finding.title).slice(0, 28)}`, phase: 'Fix', schema: REVIEW_SCHEMA },
        ).then(rev => ({ ...r, review: rev }))
      : r,
  )).filter(Boolean)
}

let regression = null
if (fixes.some(x => x.fix && x.fix.status === 'FIXED')) {
  phase('Regression')
  regression = await agent(
    '對本輪修復後的代碼跑全量回歸（對照你 memory 的 BASELINE 行），含 GUI 靜態檢查；全部 fail 收集完再回報，不在首個 fail 中斷。',
    { agentType: 'E4', label: 'regression', phase: 'Regression' },
  )
}

// return 瘦身（context 經濟）：去 evidence/impact/fix_hint 全文 —— 它們已落盤在各軸 report_path，
// main 只吃決策骨架（axis/severity/title/file/anchor/可達性）。PA 需要全文時 Read 對應 report_path。
const slim = f => ({ axis: f.axis, severity: f.severity, title: f.title, file: f.file, anchor: f.symbol_anchor, defect_type: f.defect_type, reachable: f.reachable })
const report_paths = audits.map(a => ({ axis: a.axis, report: a.report_path })).filter(x => x.report)

return {
  scope, axes, mode: doFix ? 'fix' : 'report-only', baseline, coverage_holes,
  totals: {
    findings: all.length, critical_high: critical.length,
    confirmed: confirmed.length, latent: latent.length, disputed: disputed.length,
    clusters: consensus.length, multi_axis_clusters: consensus.filter(c => c.multi_axis).length,
    ungrouped: ungrouped.length, assumptions: assumptions.length, seam_reprobes: (seam && seam.reprobes || []).length,
  },
  report_paths,              // 各軸完整報告路徑 — evidence/impact 全文在此，main/PA 按需讀（不進 main context）
  consensus: consensus.map(c => ({ key: c.key, hit_axes: c.hit_axes, multi_axis: c.multi_axis, severities: c.severities, defect_types: c.defect_types, members: c.members.map(slim) })),
  ungrouped: ungrouped.map(slim),    // 無 anchor / 單軸 confirmed，直接交 PA
  latent: latent.map(slim),          // 生產不可達 latent debt（不進修復隊列，記錄）
  disputed: disputed.map(slim),      // 單質疑者反駁，PA re-probe
  medium_low_info: all.filter(f => f.severity !== 'CRITICAL' && f.severity !== 'HIGH').map(slim),
  assumptions,               // 待證假設 + 各軸 negative-space 盲區（本就精簡 note/why_unproven）
  seam_reprobes: (seam && seam.reprobes) || [],   // 軸交界盲區 → 派軸帶證據審後才升格 finding
  fixes, regression,
  // Stage 3-4 由主會話接手：細節在 report_paths，main 只持決策骨架；consensus 是呈現層去重（非語義替代）；
  //   跨檔/跨 type 同源、disputed、assumptions、seam_reprobes 仍需 PA 判斷與定向 re-probe（去重期望首次實戰回放校準，見 skill）。
  next: doFix
    ? '主會話接 Stage 3：PA 讀 report_paths 整合 consensus+ungrouped+fixes 分級成修復計劃；Stage 4 PM 裁決+TODO；worktree 修復需 operator 簽核合併'
    : '主會話接 Stage 3：PA 讀 report_paths 對 consensus 確認異質 corroboration、對 ungrouped/disputed/seam_reprobes/assumptions 定向 re-probe→validated fix plan；Stage 4 PM 裁決+TODO（見 ultracode-full-audit skill）',
}
