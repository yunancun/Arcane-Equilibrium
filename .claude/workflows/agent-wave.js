// 通用後台 wave runner — saved workflow（PM 多 agent 並行派發 + journal 斷點續傳）
// 動機：desktop local-agent session pause 會殺光 in-flight BG agent 且不可復活
//   （memory `claude-desktop-bg-agent-idle-kill`）。Workflow journal 讓任何死法後
//   `Workflow({scriptPath, resumeFromRunId})` 重放：已完成 agent 走 cache 零 token，只重跑未完成者。
// 用法（operator 2026-06-11 核准常備）：
//   args = [{agentType, description, prompt, model?, isolation?}, ...]
//   PM 照常把完整派工契約寫進 prompt（含派工模板第 6 項 checkpoint 條款）；本腳本只管編排
//   與斷點續傳，不改 prompt 語義。對 API 即死/被 skip（null）自帶一輪續作棒重派。
//   注意：workflow 自身也是 BG task —— 在飛時 PM 同樣駐留等收（blocking TaskOutput）。
export const meta = {
  name: 'agent-wave',
  description: '通用 wave runner：並行派發具名 agent（E1/E2/...），journal 斷點續傳（resumeFromRunId 只重跑未完成者），null 自動續作棒重派一輪',
  whenToUse: 'PM 跑 ≥3 agent 的 wave 且要死後零浪費重放時；args 必填：[{agentType, description, prompt, model?, isolation?}]',
  phases: [
    { title: 'Wave', detail: '並行派發 + 收齊' },
    { title: 'Retry', detail: 'API 即死者帶續作棒前綴重派一輪' },
  ],
}

// args 驗證 fail-fast：缺欄位寧可整批不跑，不靜默吞
if (!Array.isArray(args) || args.length === 0) {
  throw new Error('args 必須是非空陣列：[{agentType, description, prompt, model?, isolation?}, ...]')
}
args.forEach((t, i) => {
  if (!t || typeof t.prompt !== 'string' || !t.prompt.trim()) throw new Error(`args[${i}] 缺 prompt`)
  if (typeof t.agentType !== 'string' || !t.agentType.trim()) throw new Error(`args[${i}] 缺 agentType`)
})

const key = (t, i) => t.description || `${t.agentType}-${i}`
const mkOpts = (t, i, ph) => ({
  label: ph === 'Retry' ? `relay:${key(t, i)}` : key(t, i),
  phase: ph,
  agentType: t.agentType,
  ...(t.model ? { model: t.model } : {}),
  ...(t.isolation ? { isolation: t.isolation } : {}),
})

phase('Wave')
log(`派發 ${args.length} 個 agent（journal 斷點續傳已啟用）`)
const first = await parallel(args.map((t, i) => () => agent(t.prompt, mkOpts(t, i, 'Wave'))))

const results = args.map((_, i) => first[i])
// null（API 即死/被 skip）自動續作棒重派一輪；prompt 加接力前綴 → (prompt, opts) 改變，
// resumeFromRunId 重放時不會誤命中第一輪的 null cache
const deadIdx = args.map((_, i) => i).filter(i => first[i] === null)
if (deadIdx.length) {
  phase('Retry')
  const RELAY = '【續作棒】前一棒可能已部分完成：第一步先讀任務 worktree 的 git log + git status + diff，已完成部分 NO-OP 跳過，禁止重做。原任務契約如下：\n\n'
  log(`${deadIdx.length} 個 agent 失敗（API 即死/skip），續作棒重派：${deadIdx.map(i => key(args[i], i)).join(', ')}`)
  const second = await parallel(deadIdx.map(i => () => agent(RELAY + args[i].prompt, mkOpts(args[i], i, 'Retry'))))
  deadIdx.forEach((origI, j) => { results[origI] = second[j] })
}

const failed = args.map((t, i) => key(t, i)).filter((_, i) => results[i] === null)
log(failed.length
  ? `收齊 ${args.length - failed.length}/${args.length}；仍失敗：${failed.join(', ')}（查限額/credits 後 resumeFromRunId 補跑）`
  : `收齊 ${args.length}/${args.length} 全部完成`)

// 回傳瘦身契約（PM.md 回傳契約）：value = sub-agent final message（VERDICT 行 + 結論 + 報告路徑）
const out = {}
args.forEach((t, i) => { out[key(t, i)] = results[i] === null ? 'FAILED（兩輪皆 null — 查限額/credits 後 resumeFromRunId 重放）' : results[i] })
return out
