// 通用後台 wave runner — saved workflow（PM 多 agent 並行派發 + journal 斷點續傳 + 四態收尾契約）
// 動機：desktop local-agent session pause 會殺光 in-flight BG agent 且不可復活
//   （memory `claude-desktop-bg-agent-idle-kill`）。Workflow journal 讓任何死法後
//   `Workflow({scriptPath, resumeFromRunId})` 重放：已完成 agent 走 cache 零 token，只重跑未完成者。
// 用法（operator 2026-06-11 核准常備）：
//   args = [{agentType, description, prompt, model?, isolation?, contextPath?}, ...]
//   PM 照常把完整派工契約寫進 prompt（含派工模板第 6 項 checkpoint 條款）；本腳本只管編排
//   與斷點續傳，不改 prompt 業務語義，但自動做兩件事：
//   1) 每個派發 prompt 尾端 append 四態收尾契約 CONTRACT（STATUS 首行 + 報告落檔 + ≤500 字摘要回覆）；
//   2) contextPath 存在時在 prompt 前注入「先讀 wave 共同背景檔」前綴（共享 context 只付一次）。
//   收齊後解析各 agent 的 STATUS 行做分組統計；NEEDS_CONTEXT/BLOCKED 不自動重派（處置權在 PM，
//   處置表正本=.claude/agents/PM.md「派工四態契約與升級階梯」），只在 log 與回傳醒目標出。
//   對 API 即死/被 skip（null）自帶一輪續作棒重派。
//   注意：workflow 自身也是 BG task —— 在飛時 PM 同樣駐留等收（blocking TaskOutput）。
export const meta = {
  name: 'agent-wave',
  description: '通用 wave runner：並行派發具名 agent（E1/E2/...），journal 斷點續傳（resumeFromRunId 只重跑未完成者），null 自動續作棒重派一輪',
  whenToUse: 'PM 跑 ≥3 agent 的 wave 且要死後零浪費重放時；args 必填：[{agentType, description, prompt, model?, isolation?, contextPath?}]；自動 append 四態收尾契約（最終回覆首行 STATUS: DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED），收齊後回傳 statuses 解析索引，NEEDS_CONTEXT/BLOCKED 標出待 PM 處置不自動重派',
  phases: [
    { title: 'Wave', detail: '並行派發 + 收齊' },
    { title: 'Retry', detail: 'API 即死者帶續作棒前綴重派一輪' },
  ],
}

// args 驗證 fail-fast：缺欄位寧可整批不跑，不靜默吞
if (!Array.isArray(args) || args.length === 0) {
  throw new Error('args 必須是非空陣列：[{agentType, description, prompt, model?, isolation?, contextPath?}, ...]')
}
args.forEach((t, i) => {
  if (!t || typeof t.prompt !== 'string' || !t.prompt.trim()) throw new Error(`args[${i}] 缺 prompt`)
  if (typeof t.agentType !== 'string' || !t.agentType.trim()) throw new Error(`args[${i}] 缺 agentType`)
  if (t.contextPath !== undefined && (typeof t.contextPath !== 'string' || !t.contextPath.trim())) {
    throw new Error(`args[${i}] contextPath 存在時必須是非空字串`)
  }
})

// 四態收尾契約 footer（四態協議借 obra/superpowers MIT；PM 處置表正本見 PM.md「派工四態契約與升級階梯」）。
// 為什麼 append 在 runner：保證 wave 內每個 agent 收到同一份契約，PM 手寫 prompt 漏附時不破洞。
const CONTRACT = `

【收尾契約】最終回覆第一行必須是 \`STATUS: DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED\` + 一行理由。完整報告寫 docs/CCAgentWorkSpace/<你的角色>/workspace/reports/YYYY-MM-DD--<desc>.md；回覆正文只給 ≤500 字摘要 + 報告路徑 + 關鍵結論，不貼全文。說「做不到/卡住」永遠可以；爛活比沒活更糟，絕不沉默交出不確定的工作。`

const key = (t, i) => t.description || `${t.agentType}-${i}`
const mkOpts = (t, i, ph) => ({
  label: ph === 'Retry' ? `relay:${key(t, i)}` : key(t, i),
  phase: ph,
  agentType: t.agentType,
  ...(t.model ? { model: t.model } : {}),
  ...(t.isolation ? { isolation: t.isolation } : {}),
})
// 完整派發 prompt = 共同背景前綴（可選）+ 原 prompt + 收尾契約。CONTRACT 恰 append 一次：
// Retry 走 RELAY + fullPrompt(t)，只多接力前綴，不會疊兩份 CONTRACT。
const fullPrompt = (t) => (t.contextPath ? `【共同背景】先讀 ${t.contextPath}（wave 共同背景檔，PM 已寫好）。\n\n` : '') + t.prompt + CONTRACT

phase('Wave')
log(`派發 ${args.length} 個 agent（journal 斷點續傳已啟用）`)
const first = await parallel(args.map((t, i) => () => agent(fullPrompt(t), mkOpts(t, i, 'Wave'))))

const results = args.map((_, i) => first[i])
// null（API 即死/被 skip）自動續作棒重派一輪；prompt 加接力前綴 → (prompt, opts) 改變，
// resumeFromRunId 重放時不會誤命中第一輪的 null cache
const deadIdx = args.map((_, i) => i).filter(i => first[i] === null)
if (deadIdx.length) {
  phase('Retry')
  const RELAY = '【續作棒】前一棒可能已部分完成：第一步先讀任務 worktree 的 git log + git status + diff，已完成部分 NO-OP 跳過，禁止重做。原任務契約如下：\n\n'
  log(`${deadIdx.length} 個 agent 失敗（API 即死/skip），續作棒重派：${deadIdx.map(i => key(args[i], i)).join(', ')}`)
  const second = await parallel(deadIdx.map(i => () => agent(RELAY + fullPrompt(args[i]), mkOpts(args[i], i, 'Retry'))))
  deadIdx.forEach((origI, j) => { results[origI] = second[j] })
}

const failed = args.map((t, i) => key(t, i)).filter((_, i) => results[i] === null)
log(failed.length
  ? `收齊 ${args.length - failed.length}/${args.length}；仍失敗：${failed.join(', ')}（查限額/credits 後 resumeFromRunId 補跑）`
  : `收齊 ${args.length}/${args.length} 全部完成`)

// STATUS 解析（容錯）：取回覆中第一個 STATUS 行；沒寫 → UNKNOWN（老 prompt / 違約 agent 都能收，不炸）；
// null（兩輪皆死）→ FAILED。長字面 DONE_WITH_CONCERNS 置前防被 DONE 前綴吞匹配。
const STATUS_RE = /^\s*STATUS:\s*(DONE_WITH_CONCERNS|DONE|NEEDS_CONTEXT|BLOCKED)\b/m
const statuses = {}
args.forEach((t, i) => {
  const m = typeof results[i] === 'string' ? STATUS_RE.exec(results[i]) : null
  statuses[key(t, i)] = results[i] === null ? 'FAILED' : (m ? m[1] : 'UNKNOWN')
})
const counts = {}
Object.values(statuses).forEach(s => { counts[s] = (counts[s] || 0) + 1 })
log(`STATUS 統計：${Object.entries(counts).map(([s, n]) => `${s}=${n}`).join(' ')}`)
// NEEDS_CONTEXT/BLOCKED 不自動重派——那是 PM 的判斷（NEEDS_CONTEXT→補餵缺的 context 重派；
// BLOCKED→換強模型/拆任務/升級 operator；禁無變更同模型裸重試），runner 只醒目標出。
const attention = Object.keys(statuses).filter(k => statuses[k] === 'NEEDS_CONTEXT' || statuses[k] === 'BLOCKED')
if (attention.length) {
  log(`【需 PM 處置，不自動重派】${attention.map(k => `${k}=${statuses[k]}`).join('、')}（NEEDS_CONTEXT→補餵缺的 context 重派；BLOCKED→換強模型/拆任務/升級 operator）`)
}

// 回傳契約（向後兼容、改動最小）：results 各 value 保留原始 final message 純字串
// （PM.md 回傳契約「value = sub-agent final message」不破，STATUS 行本就在字串首行可直讀；
//   改成 {status, text} 會讓 PM 取文多剝一層）。statuses / attention 為頂層另附的解析索引。
const out = {}
args.forEach((t, i) => { out[key(t, i)] = results[i] === null ? 'FAILED（兩輪皆 null — 查限額/credits 後 resumeFromRunId 重放）' : results[i] })
return { statuses, attention, results: out }
