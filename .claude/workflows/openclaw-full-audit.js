// OpenClaw 全盤多視角審計 — saved workflow（ultracode 編排形態的持久化設置）
// 調用方式見 .claude/skills/ultracode-full-audit/SKILL.md
// 默認 report-only；修復需顯式 args: { fix: true }
export const meta = {
  name: 'openclaw-full-audit',
  description: 'OpenClaw 全盤多視角審計：審計群並行 → 匯總分級 → 對抗複核 → （可選）修復+複審 → 回歸',
  whenToUse: 'ultracode 啟用且 operator 要求全盤審查/全面優化檢查時，由主會話（conductor）調用；默認 report-only',
  phases: [
    { title: 'Audit', detail: '審計 agent 並行 fan-out（默認 CC/E3/FA/E5/MIT/R4，可選 QC/BB/A3/AI-E）' },
    { title: 'Verify', detail: 'CRITICAL/HIGH 發現對抗複核（證據鏈 + 影響復現雙質疑者）' },
    { title: 'Fix', detail: 'args.fix=true 時：E1 修復（worktree 隔離）→ E2 對抗複審' },
    { title: 'Regression', detail: '有修復落地時：E4 全量回歸對照 memory BASELINE' },
  ],
}

const FINDINGS_SCHEMA = {
  type: 'object', required: ['verdict', 'confidence', 'findings'], additionalProperties: false,
  properties: {
    verdict: { type: 'string', enum: ['PASS', 'FINDINGS', 'BLOCKED', 'NO-OP'] },
    confidence: { type: 'string', enum: ['high', 'med', 'low'] },
    findings: { type: 'array', items: {
      type: 'object', required: ['title', 'severity', 'confidence', 'evidence'], additionalProperties: false,
      properties: {
        title: { type: 'string' },
        severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] },
        confidence: { type: 'string', enum: ['high', 'med', 'low'] },
        evidence: { type: 'string' },
        file: { type: 'string' },
        fix_hint: { type: 'string' },
      },
    } },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', required: ['refuted', 'reason'], additionalProperties: false,
  properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } },
}

const FIX_SCHEMA = {
  type: 'object', required: ['status', 'summary'], additionalProperties: false,
  properties: {
    status: { type: 'string', enum: ['FIXED', 'BLOCKED', 'NO-OP'] },
    summary: { type: 'string' },
    files: { type: 'string' },
  },
}

const REVIEW_SCHEMA = {
  type: 'object', required: ['verdict', 'issues'], additionalProperties: false,
  properties: { verdict: { type: 'string', enum: ['APPROVE', 'RETURN'] }, issues: { type: 'string' } },
}

// ---- 參數（args 全部可選）----
const scope = (args && args.scope) || 'srv/ 全倉（rust engine、control_api、GUI、helper_scripts、.claude 配置、治理文檔）'
const axes = (args && args.axes) || ['CC', 'E3', 'FA', 'E5', 'MIT', 'R4']
const doFix = !!(args && args.fix)
const maxFixes = (args && args.max_fixes) || 5

phase('Audit')
log(`範圍：${scope}；審計軸：${axes.join(', ')}；模式：${doFix ? 'fix' : 'report-only'}`)
const audits = (await parallel(axes.map(ax => () =>
  agent(
    `按你的角色職責對以下範圍做全量審計：${scope}。執行你的啟動序列與既定 SOP；所有 finding（含 LOW/INFO/不確定）全部輸出並標 severity+confidence+證據（file:line 或命令輸出）；報告同時按你的完成序列落盤 workspace。`,
    { agentType: ax, label: `audit:${ax}`, phase: 'Audit', schema: FINDINGS_SCHEMA },
  ).then(r => r && { axis: ax, ...r }),
))).filter(Boolean)

const all = audits.flatMap(a => (a.findings || []).map(f => ({ ...f, axis: a.axis })))
const critical = all.filter(f => f.severity === 'CRITICAL' || f.severity === 'HIGH')
log(`共 ${all.length} 條 finding；C/H ${critical.length} 條進對抗複核（M/L/INFO 直接入報告）`)

phase('Verify')
const verified = await parallel(critical.map(f => () =>
  parallel([
    () => agent(
      `嘗試反駁這條審計發現（拿不出具體反證則 refuted=false）：[${f.axis}] ${f.title}\n證據：${f.evidence}\n檔案：${f.file || '未指明'}\n你的視角：證據鏈成立性 — 引用的檔案/行/輸出是否真實存在、結論是否過度推斷。實地核查後下結論。`,
      { label: `verify-evid:${f.axis}`, phase: 'Verify', schema: VERDICT_SCHEMA },
    ),
    () => agent(
      `嘗試反駁這條審計發現（拿不出具體反證則 refuted=false）：[${f.axis}] ${f.title}\n證據：${f.evidence}\n檔案：${f.file || '未指明'}\n你的視角：影響真實性 — 按證據實地復查，問題是否真實可達、severity 是否高估。`,
      { label: `verify-impact:${f.axis}`, phase: 'Verify', schema: VERDICT_SCHEMA },
    ),
  ]).then(vs => {
    const votes = vs.filter(Boolean)
    const refutedCount = votes.filter(v => v.refuted).length
    return { ...f, confirmed: refutedCount === 0, disputed: refutedCount === 1, refutations: votes.map(v => v.reason).join(' | ') }
  }),
))
const vOk = verified.filter(Boolean)
const confirmed = vOk.filter(f => f.confirmed)
const disputed = vOk.filter(f => f.disputed)
log(`對抗複核：confirmed ${confirmed.length} / disputed ${disputed.length} / refuted ${vOk.length - confirmed.length - disputed.length}`)

let fixes = []
if (doFix && confirmed.length) {
  phase('Fix')
  const queue = confirmed.slice(0, maxFixes)
  if (confirmed.length > maxFixes) log(`修復上限 ${maxFixes}，餘 ${confirmed.length - maxFixes} 條留報告交 PM`)
  fixes = (await pipeline(queue,
    f => agent(
      `修復以下已對抗確認的審計發現（最小安全解，不擴 scope）：[${f.axis}] ${f.title}\n證據：${f.evidence}\n檔案：${f.file || '見證據'}\n修復提示：${f.fix_hint || '無'}\n遵守你的方案執行協議：修復→自測→回報。`,
      { agentType: 'E1', label: `fix:${(f.file || f.title).slice(0, 28)}`, phase: 'Fix', isolation: 'worktree', schema: FIX_SCHEMA },
    ).then(r => ({ finding: f, fix: r })),
    r => (r && r.fix && r.fix.status === 'FIXED')
      ? agent(
          `對抗複審剛完成的修復：${r.finding.title}\n修復摘要：${r.fix.summary}\n涉及檔案：${r.fix.files || ''}\n按 pr-adversarial-review SOP 全量審；RETURN 時列具體 issue。`,
          { agentType: 'E2', label: `review:${(r.finding.file || r.finding.title).slice(0, 28)}`, phase: 'Fix', schema: REVIEW_SCHEMA },
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

return {
  scope, axes, mode: doFix ? 'fix' : 'report-only',
  totals: { findings: all.length, critical_high: critical.length, confirmed: confirmed.length, disputed: disputed.length },
  confirmed, disputed,
  medium_low_info: all.filter(f => f.severity !== 'CRITICAL' && f.severity !== 'HIGH'),
  fixes, regression,
  next: doFix
    ? 'PM 整合報告 → operator 簽核部署（worktree 修復需合併）'
    : '需修復時以 args {fix:true, max_fixes:N} 重跑 Fix 段，或交 PM 順序派工',
}
