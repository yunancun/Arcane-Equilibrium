// OpenClaw 全盤多視角審計 — saved workflow（ultracode 編排形態的持久化設置）
// 調用方式、Stage 0 baseline freeze、Stage 3 PA 驗真層、Stage 4 PM 裁決見
//   .claude/skills/ultracode-full-audit/SKILL.md（主會話前後置由 conductor 親自做）
// 本腳本只負責並行審計段（Stage 2）+ 對抗複核 +（可選）修復+回歸。默認 report-only。
export const meta = {
  name: 'openclaw-full-audit',
  description: 'OpenClaw 全盤多視角審計（Stage 2-3 並行段）：審計群 fan-out → C/H 對抗複核 →（可選）修復+複審 → 回歸；read-only 硬邊界內建',
  whenToUse: 'ultracode 啟用且 operator 要求全盤審查/全面優化檢查時，由主會話（conductor）按 ultracode-full-audit skill 調用；Stage 0 凍結與 Stage 3-4 收斂由主會話親做；默認 report-only',
  phases: [
    { title: 'Audit', detail: '審計 agent 並行 fan-out（默認 10 軸 CC/FA/E3/BB/QC/MIT/AI-E/E5/A3/R4，args.axes 可改；read-only 邊界+本輪 focus 注入）' },
    { title: 'Verify', detail: 'CRITICAL/HIGH 發現對抗複核（證據鏈 + 影響復現雙質疑者）' },
    { title: 'Fix', detail: 'args.fix=true 時：E1 修復（worktree 隔離）→ E2 對抗複審' },
    { title: 'Regression', detail: '有修復落地時：E4 全量回歸對照 memory BASELINE' },
  ],
}

// finding 加 FACT/INFERENCE/ASSUMPTION 三分 + impact；無證據者改列 assumptions 不沉默丟棄
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
        fix_hint: { type: 'string' },
      },
    } },
    // 有嫌疑但無證據：列此處供 PA re-probe，不得當無事丟棄（recall 保護）
    assumptions: { type: 'array', items: {
      type: 'object', required: ['note', 'why_unproven'], additionalProperties: false,
      properties: { note: { type: 'string' }, why_unproven: { type: 'string' } },
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
// 默認全 10 軸（補齊 BB/QC/AI-E/A3）；E4 測試矩陣審計與 TW 文檔盤點按需加入 axes
const axes = (args && args.axes) || ['CC', 'FA', 'E3', 'BB', 'QC', 'MIT', 'AI-E', 'E5', 'A3', 'R4']
const doFix = !!(args && args.fix)
const maxFixes = (args && args.max_fixes) || 5
// 本輪靶向必查項：字串（注入全軸）或 {軸名: '額外必查項'}（按軸注入）。非範圍上限。
const focus = (args && args.focus) || null
// 凍結基線（由主會話 Stage 0 填入：三端 SHA / dirty / E4 BASELINE 行），注入每軸供「affected line」對齊
const baseline = (args && args.baseline) || null

const READONLY = 'read-only audit 硬邊界：不修復 / 不改功能 / 不部署 / 不重啟 runtime / 不改 DB schema / 不動 live·demo·paper auth / 不啟動交易 / 不改 risk·strategy·TOML live config。Linux 證據僅允許 ssh trade-core read-only 命令；遇任何 rebuild·restart·migration·auth·trading mutation 需求立即停止、標 BLOCKED 回報，不擅自執行。'

function focusFor(ax) {
  if (!focus) return ''
  const f = typeof focus === 'string' ? focus : focus[ax]
  return f ? `\n本輪額外必查項（靶向假設，非範圍上限；你的 role SOP 全量仍是基準範圍）：${f}` : ''
}

phase('Audit')
log(`範圍：${scope}；審計軸（${axes.length}）：${axes.join(', ')}；模式：${doFix ? 'fix' : 'report-only'}${baseline ? '；基線已凍結' : '；⚠️ 未傳 baseline（建議主會話先 Stage 0 凍結三端 SHA）'}`)
const audits = (await parallel(axes.map(ax => () =>
  agent(
    `按你的 role SOP 與掛載 skills 對以下範圍做全量審計（你的 role 範疇即審計範圍，下列 focus 僅為額外靶向，不是範圍上限）：${scope}。\n${READONLY}${baseline ? '\n凍結基線（affected line 對齊此基線）：' + baseline : ''}${focusFor(ax)}\n每條 finding 標：FACT/INFERENCE/ASSUMPTION 分類、severity、confidence、evidence（file:line 或命令輸出）、impact、fix 方向。全量輸出含 LOW/INFO/不確定項；有嫌疑但拿不出證據者不入 findings，改列 assumptions（附 why_unproven）供 PA re-probe，不得沉默丟棄。報告按你的完成序列落盤 workspace。`,
    { agentType: ax, label: `audit:${ax}`, phase: 'Audit', schema: FINDINGS_SCHEMA },
  ).then(r => r && { axis: ax, ...r }),
))).filter(Boolean)

const all = audits.flatMap(a => (a.findings || []).map(f => ({ ...f, axis: a.axis })))
const assumptions = audits.flatMap(a => (a.assumptions || []).map(x => ({ ...x, axis: a.axis })))
const critical = all.filter(f => f.severity === 'CRITICAL' || f.severity === 'HIGH')
log(`共 ${all.length} 條 finding（C/H ${critical.length} 進對抗複核，M/L/INFO 直入報告）+ ${assumptions.length} 條待證假設`)

phase('Verify')
const verified = await parallel(critical.map(f => () =>
  parallel([
    () => agent(
      `嘗試反駁這條審計發現（拿不出具體反證則 refuted=false）：[${f.axis}] ${f.title}\n分類：${f.classification}\n證據：${f.evidence}\n檔案：${f.file || '未指明'}\n你的視角：證據鏈成立性 — 引用的檔案/行/輸出是否真實存在、結論是否過度推斷（INFERENCE/ASSUMPTION 尤其要查）。實地核查後下結論。`,
      { label: `verify-evid:${f.axis}`, phase: 'Verify', schema: VERDICT_SCHEMA },
    ),
    () => agent(
      `嘗試反駁這條審計發現（拿不出具體反證則 refuted=false）：[${f.axis}] ${f.title}\n證據：${f.evidence}\n檔案：${f.file || '未指明'}\n影響：${f.impact}\n你的視角：影響真實性 — 按證據實地復查，問題是否真實可達、severity 是否高估。`,
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
  scope, axes, mode: doFix ? 'fix' : 'report-only', baseline,
  totals: { findings: all.length, critical_high: critical.length, confirmed: confirmed.length, disputed: disputed.length, assumptions: assumptions.length },
  confirmed, disputed,
  medium_low_info: all.filter(f => f.severity !== 'CRITICAL' && f.severity !== 'HIGH'),
  assumptions,
  fixes, regression,
  // Stage 3-4 由主會話接手：assumptions 與 disputed 進 PA re-probe；confirmed 去重合併分級成修復計劃；PM 裁決+TODO
  next: doFix
    ? '主會話接 Stage 3：PA 整合 confirmed+fixes 去重分級→修復計劃；Stage 4 PM 裁決+TODO；worktree 修復需 operator 簽核合併'
    : '主會話接 Stage 3：PA 對 confirmed 去重合併分級、對 disputed+assumptions targeted re-probe→validated fix plan；Stage 4 PM 裁決+TODO（見 ultracode-full-audit skill）',
}
