// OpenClaw 盈利研判編排 — saved workflow（與 openclaw-full-audit 對偶：找問題 vs 找錢）
// 雙層：守（diagnose，救現有系統的錢漏/凍/沒賺，基於 runtime 證據）+ 攻（explore，侵略性、跳出
//   現有範式、從最廣 scope 主動找新 alpha 邊界）。read-only；所有 edge 帶證據不憑記憶（CLAUDE.md
//   不 fake + alpha evidence governance）；bull-only 標 regime-bet。調用見 reference memory / ultracode-full-audit skill 姊妹節。
export const meta = {
  name: 'profit-diagnosis',
  description: 'OpenClaw 盈利研判：runtime 取數 → 守(診斷現有錢漏/凍/沒賺)+攻(侵略性探索新 alpha 邊界，跳出現有範式) → ROI 排序的開發機會地圖；read-only，edge 帶證據紀律',
  whenToUse: 'operator 要盈利歸因 / 開發方向指導 / 「為什麼不賺錢、下一步開發什麼能賺錢」時，主會話按 reference 調用；Stage 0 凍結與最終裁決由主會話親做；read-only',
  phases: [
    { title: 'Evidence', detail: 'runtime 取真實證據（fills/edge/gate 拒單統計/dormant 清單/AI 成本 ROI）— MIT/AI-E read-only' },
    { title: 'Probe', detail: '守(QC/BB/MIT/AI-E 各域診斷錢漏凍沒賺)+攻(同批侵略性探索新 alpha，跳出範式、最廣 scope)' },
    { title: 'Map', detail: '綜合成盈利機會地圖：ROI 排序、守攻分區、翻牆概率、證據等級、驗證路徑、下一步 owner' },
  ],
}

// 守=診斷現有；攻=探索新邊界。area: leak(已實現端漏) / frozen(能力端凍) / unrealized(該開發未開發)
const PROBE_SCHEMA = {
  type: 'object', required: ['axis', 'verdict', 'diagnoses', 'opportunities', 'report_path'], additionalProperties: false,
  properties: {
    axis: { type: 'string' },
    verdict: { type: 'string', enum: ['FINDINGS', 'BLOCKED', 'NO-OP'] },
    // 守：基於 runtime 證據盤點現有系統盈利歸因
    diagnoses: { type: 'array', items: {
      type: 'object', required: ['area', 'title', 'classification', 'evidence', 'blocker', 'profit_impact', 'confidence'], additionalProperties: false,
      properties: {
        area: { type: 'string', enum: ['leak', 'frozen', 'unrealized'] },
        title: { type: 'string' },
        classification: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        evidence: { type: 'string' },                    // runtime 證據（命令輸出/查詢結果/file:line）
        blocker: { type: 'string', enum: ['gate', 'dormant', 'undeveloped', 'cost', 'exit-policy', 'paradigm', 'other'] },
        profit_impact: { type: 'string' },               // 對盈利的影響（bps/方向；帶估算依據，不憑記憶）
        regime_caveat: { type: 'string' },               // bull-only/單 regime 標 regime-bet
        confidence: { type: 'string', enum: ['high', 'med', 'low'] },
      },
    } },
    // 攻：侵略性探索 — 系統還沒碰、但可能有 edge 的新方向（跳出現有範式、最廣 scope）
    opportunities: { type: 'array', items: {
      type: 'object', required: ['title', 'hypothesis', 'why_not_tried', 'how_to_validate', 'classification', 'confidence'], additionalProperties: false,
      properties: {
        title: { type: 'string' },
        hypothesis: { type: 'string' },                  // 可證偽的 alpha 假設
        why_not_tried: { type: 'string' },               // 系統為何還沒碰（盲區/範式限制/數據缺）
        paradigm_challenge: { type: 'boolean' },          // 是否質疑現有範式（OHLCV+技術指標天花板等）
        est_edge: { type: 'string' },                    // 預期 edge 與依據（大膽假設，標 ASSUMPTION）
        est_cost: { type: 'string' },                    // 開發成本估
        wall_break_prob: { type: 'string', enum: ['high', 'med', 'low', 'unknown'] },  // 翻成本牆概率
        how_to_validate: { type: 'string' },             // leak-free 驗證路徑（小心求證，不 hype）
        classification: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        confidence: { type: 'string', enum: ['high', 'med', 'low'] },
      },
    } },
    report_path: { type: 'string' },
  },
}

const EVIDENCE_SCHEMA = {
  type: 'object', required: ['summary', 'report_path'], additionalProperties: false,
  properties: { summary: { type: 'string' }, report_path: { type: 'string' }, gaps: { type: 'string' } },
}

const MAP_SCHEMA = {
  type: 'object', required: ['report_path', 'top_moves'], additionalProperties: false,
  properties: {
    report_path: { type: 'string' },
    top_moves: { type: 'array', items: {
      type: 'object', required: ['rank', 'title', 'mode', 'roi_rationale', 'next_step', 'owner'], additionalProperties: false,
      properties: {
        rank: { type: 'integer' },
        title: { type: 'string' },
        mode: { type: 'string', enum: ['defend', 'attack'] },     // 守(救現有) / 攻(開新邊界)
        roi_rationale: { type: 'string' },                        // 預期 edge 提升 / 開發成本
        wall_break_prob: { type: 'string', enum: ['high', 'med', 'low', 'unknown'] },
        blocker: { type: 'string' },                              // 阻塞點（gate/dormant/undeveloped/operator-decision/paradigm）
        evidence_level: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        next_step: { type: 'string' },
        owner: { type: 'string' },
      },
    } },
  },
}

const scope = (args && args.scope) || 'srv/ 全系統盈利面（策略/gate/風控/fills/AI 成本/dormant 能力/未開發 alpha 邊界）'
const baseline = (args && args.baseline) || null
const focus = (args && args.focus) || null   // 本輪盈利靶向（例：某策略虧損根因、某 alpha 假設）

const READONLY = 'read-only 盈利研判：不修復 / 不改策略·風控·gate·config / 不部署 / 不重啟 / 不啟動交易 / 不改 auth。Linux 證據僅 ssh trade-core read-only 命令；遇任何 mutation 需求停止標 BLOCKED 回報。'
const EVID_RULE = '證據紀律（交易系統鐵律）：所有 edge/盈利數字必須帶 runtime 真實證據（查詢輸出/命令結果/file:line），不憑記憶、不編造；無法取證者標 ASSUMPTION 不標 FACT。bull-only / 單 regime 結果標 regime-bet（alpha evidence governance）。'

const ADVISORS = [
  { ax: 'QC', angle: 'edge 數學歸因（成交單 gross edge vs 成本、Kelly/sizing、exit policy 是否拖累）；dormant 策略可救性（真 DOA vs regime-dormant）；策略層未開發 alpha。攻：alpha 來源 framework / 行為金融異常 / replication-aware 的新信號軸，質疑現有信號範式是否到天花板。' },
  { ax: 'BB', angle: '成本側盈利吞噬（Bybit fee/funding/滑點/conditional order 吃掉多少 edge）；rebate/maker 機會。攻：跨所 basis、funding 結構套利、Bybit 新產品/微結構機會、execution alpha。' },
  { ax: 'MIT', angle: 'ML/數據基座的盈利貢獻（feature 是否真帶 edge、pipeline 哪些是死表）；dormant ML 能力。攻：還沒用的數據軸（鏈上/預測市場 Polymarket·Kalshi/社交/option flow/非-OHLCV 特徵）、新 ML 範式能解鎖的 alpha，質疑 OHLCV+技術指標範式天花板。' },
  { ax: 'AI-E', angle: 'AI 推理 ROI（L2 花費 vs 帶來 edge、cost_edge_ratio）；flag-off AI 能力的盈利潛力。攻：L2 自主推理能否做 alpha discovery / 事件解讀 / regime 判斷，AI 能解鎖但還沒接的盈利路徑。' },
]

phase('Evidence')
log(`盈利研判：${scope}；模式 read-only${baseline ? '；基線已凍結' : '；⚠️ 建議主會話先 Stage 0 凍結三端 SHA + active 策略 roster'}`)
// 取數需 Bash（QC 唯讀無 Bash）→ MIT/AI-E 取 runtime 真實數據供 Probe 階段研判
const evidence = (await parallel([
  () => agent(
    `read-only 盈利證據取數（為 Probe 階段供真實數據）：用你的 SOP 從 DB/runtime 取——近期成交 fills 的 gross edge 分布與成本分解、各策略 active/dormant 狀態清單、各 gate（cost_gate 等）拒單統計（拒絕率+抽樣，供反事實 edge 判斷真負 vs 誤殺）、feature/pipeline 哪些真帶 edge vs 死表。${READONLY} ${EVID_RULE} 落盤帶證據摘要並回填 report_path；gaps 填取不到的數據。`,
    { agentType: 'MIT', label: 'evidence:MIT', phase: 'Evidence', schema: EVIDENCE_SCHEMA },
  ),
  () => agent(
    `read-only AI 成本盈利證據：取 AI 成本 ledger / cost_edge_ratio，評 L2 推理 ROI（AI 花費 vs 帶來的 edge），列 flag-off / dormant 的 AI 能力。${READONLY} ${EVID_RULE} 落盤回填 report_path。`,
    { agentType: 'AI-E', label: 'evidence:AI-E', phase: 'Evidence', schema: EVIDENCE_SCHEMA },
  ),
])).filter(Boolean)
const evidencePaths = evidence.map(e => e.report_path).filter(Boolean)
log(`取數完成 ${evidence.length}/2；證據報告：${evidencePaths.join(', ') || '（落盤待讀）'}`)

phase('Probe')
const evidenceNote = evidencePaths.length ? `\nStage 1 已取的 runtime 證據在這些報告，先讀再研判：${evidencePaths.join(', ')}` : '\n（Stage 1 證據如缺，自己 read-only 取或標 ASSUMPTION）'
const focusNote = focus ? `\n本輪盈利靶向：${focus}` : ''
const probes = (await parallel(ADVISORS.map(a => () =>
  agent(
    `盈利研判（你=${a.ax}）。範圍：${scope}。${READONLY} ${EVID_RULE}${evidenceNote}${focusNote}\n\n【守 — diagnoses（基於 runtime 證據盤點現有盈利歸因）】本域的：leak=已實現端為何不賺（gate 拒單是真負 still 正確 還是正 edge 誤殺？成本吃掉多少？exit 拖累？）；frozen=能力端（dormant 可救性、flag-off 預期 edge、被 gate 鎖死的潛在 edge）；unrealized=本域該開發未開發。每條標 area/classification/evidence/blocker/profit_impact。\n\n【攻 — opportunities（侵略性、跳出現有範式、從最廣 scope 找新 alpha）】不要受現有策略 roster、現有結論、現有數據範式設限。主動提出這個系統還沒碰、但可能有 edge 的盈利方向。允許並鼓勵質疑現有範式（例：OHLCV+技術指標是否到天花板？6 週無 edge 是不是搜索空間本身錯了而非執行問題？該不該換軌到事件驅動/另類數據/跨所/微結構？）。你的探索角度：${a.angle}。可 WebSearch 借鑒外部思路與數據源。每條 opportunity 標 hypothesis（可證偽）/why_not_tried/paradigm_challenge/est_edge（依據）/est_cost/wall_break_prob（翻成本牆 11-27bps 的概率）/how_to_validate（leak-free 驗證路徑）。大膽假設、小心求證——不吐 hype，每個方向必須能落到可驗證的 leak-free 假設。\n\n報告落盤回填 report_path（main 只收 schema 摘要，全文留報告）。`,
    { agentType: a.ax, label: `probe:${a.ax}`, phase: 'Probe', schema: PROBE_SCHEMA },
  ).then(r => r && { ...r, axis: a.ax })
))).filter(Boolean)

const allDiag = probes.flatMap(p => (p.diagnoses || []).map(d => ({ ...d, axis: p.axis })))
const allOpp = probes.flatMap(p => (p.opportunities || []).map(o => ({ ...o, axis: p.axis })))
const probePaths = probes.map(p => p.report_path).filter(Boolean)
log(`研判完成 ${probes.length}/${ADVISORS.length}；診斷 ${allDiag.length}（漏 ${allDiag.filter(d => d.area === 'leak').length}/凍 ${allDiag.filter(d => d.area === 'frozen').length}/沒賺 ${allDiag.filter(d => d.area === 'unrealized').length}）+ 機會 ${allOpp.length}（質疑範式 ${allOpp.filter(o => o.paradigm_challenge).length}）`)

phase('Map')
// 綜合成 ROI 排序的開發機會地圖（守攻分區）；落盤，return 只給排序摘要 + 路徑
const diagBrief = allDiag.map(d => `[${d.axis}/${d.area}] ${d.title}（${d.classification}，blocker=${d.blocker}，impact=${d.profit_impact}）`).join('\n')
const oppBrief = allOpp.map(o => `[${o.axis}${o.paradigm_challenge ? '/範式挑戰' : ''}] ${o.title}（edge=${o.est_edge}，cost=${o.est_cost}，翻牆=${o.wall_break_prob}，${o.classification}）`).join('\n')
const mapResult = await agent(
  `綜合盈利機會地圖（你=PA）。讀全部研判報告：${probePaths.join(', ') || '（見下摘要）'}\n\n診斷（守）：\n${diagBrief || '（無）'}\n\n機會（攻）：\n${oppBrief || '（無）'}\n\n產出 ROI 排序的 top_moves：每項 mode（defend 救現有 / attack 開新邊界）、roi_rationale（預期 edge 提升 / 開發成本）、wall_break_prob、blocker、evidence_level、next_step、owner。排序原則：最快驗證路徑優先（flag-off 等近零成本驗證 > 開發新東西）；翻牆概率高 + 證據強優先；對 ASSUMPTION 級機會標「需先 leak-free 驗證」不直接排高。守與攻都要有（不能只救現有也不能只畫餅）。報告落盤回填 report_path。${EVID_RULE}`,
  { agentType: 'PA', label: 'profit-map', phase: 'Map', schema: MAP_SCHEMA },
)

// return 瘦身：摘要 + 路徑，全文在 report_paths（沿用 full-audit 的 context 經濟）
const slimD = d => ({ axis: d.axis, area: d.area, title: d.title, blocker: d.blocker, impact: d.profit_impact, cls: d.classification })
const slimO = o => ({ axis: o.axis, title: o.title, paradigm: o.paradigm_challenge, edge: o.est_edge, wall: o.wall_break_prob, cls: o.classification })
return {
  scope, mode: 'read-only', baseline,
  totals: {
    diagnoses: allDiag.length, leak: allDiag.filter(d => d.area === 'leak').length,
    frozen: allDiag.filter(d => d.area === 'frozen').length, unrealized: allDiag.filter(d => d.area === 'unrealized').length,
    opportunities: allOpp.length, paradigm_challenges: allOpp.filter(o => o.paradigm_challenge).length,
  },
  report_paths: { evidence: evidencePaths, probe: probePaths, map: mapResult && mapResult.report_path },
  top_moves: (mapResult && mapResult.top_moves) || [],   // ROI 排序開發機會（守攻分區）
  diagnoses: allDiag.map(slimD),     // 守：現有盈利歸因（全文在 probe 報告）
  opportunities: allOpp.map(slimO),  // 攻：新 alpha 邊界（全文在 probe 報告）
  // 主會話接手：top_moves 是開發優先級草案；operator 拍板哪些進 TODO/Sprint。所有 ASSUMPTION 級機會
  //   先走 leak-free 驗證（QC walk-forward / 歷史 kline backfill）才升格為開發項，不直接投產。
  next: '主會話/PM 整合 top_moves → operator 拍板開發優先級；attack 類 ASSUMPTION 機會先 leak-free 驗證再進 Sprint；defend 類（flag-off/dormant 解凍）走最快驗證路徑',
}
