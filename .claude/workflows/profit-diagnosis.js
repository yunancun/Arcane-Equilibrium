// OpenClaw 盈利研判編排 — saved workflow（與 openclaw-full-audit 對偶：找問題 vs 找錢）
// 雙層：守（diagnose，救現有系統的錢漏/凍/沒賺，基於 runtime 證據）+ 攻（explore，侵略性、跳出
//   現有範式、從最廣 scope 主動找新 alpha 邊界）。read-only；所有 edge 帶證據不憑記憶（CLAUDE.md
//   不 fake + alpha evidence governance）；bull-only 標 regime-bet。調用見 reference memory / ultracode-full-audit skill 姊妹節。
// 2026-07-09 三視角對抗複審後更新：args parse guard / priors 防已判定方向重提 / coverage 顯式化 /
//   baseline 注入 / Map 注入 READONLY / regime_caveat 全鏈傳遞 / schema required 對齊消費者 /
//   成本牆雙側化 / 四軸 angle 換代（maker-nogo、WP1-7、profit-first loop、IBKR lane）。
// 2026-07-09 二審姿態校準（operator 鐵則）：目標=強硬堅強找出一切盈利可能、最大程度給盈利指導；
//   挫折第一反應=換思路+搜外部信息+學成熟經驗，不是放棄。落地=空手紀律（opportunities/top_moves
//   minItems:1，無機會→解鎖監測或外部學習項）+ EXT 外部成熟經驗軸 + mode 加 unlock/learn。
// 空手紀律為雙重強制（姿態紅隊 FAIL 後加固）：①schema minItems=tool-call 層硬拒+重試——已實證
//   （2026-07-09 smoke run wf_0e51a862-65a：空陣列被拒回「must NOT have fewer than 1 items」，FACT）；
//   ②代碼級後備=空手軸重派一輪、二輪仍空進 coverage(empty-hand)。另：NO-OP 洩壓閥已刪、承重欄位
//   minLength 防樣板句、EXT 帶 sources(url+claim_quote)+local_constraint_fit 防幻覺引用、Map 重派
//   +FACT 抽跑核對、paradigm_challenge 歸零/守側空手/mode 缺分區均警示進 coverage。
export const meta = {
  name: 'profit-diagnosis',
  description: 'OpenClaw 盈利研判：runtime 取數 → 守(診斷現有錢漏/凍/沒賺)+攻(侵略性探索新 alpha 邊界，跳出現有範式) → ROI 排序的開發機會地圖；read-only，edge 帶證據紀律',
  whenToUse: 'operator 要盈利歸因 / 開發方向指導 / 「為什麼不賺錢、下一步開發什麼能賺錢」時，主會話按 reference 調用；Stage 0 凍結與最終裁決由主會話親做；conductor 每輪以 args.priors 注入現行已判定裁決快照；read-only',
  phases: [
    { title: 'Evidence', detail: 'runtime 取真實證據（fills/edge/gate 拒單統計/dormant 清單/AI 成本 ROI/profit-first loop 候選與 order-fill proof 狀態）— MIT/AI-E read-only 共享取數' },
    { title: 'Probe', detail: '守(QC/BB/MIT/AI-E 各域診斷錢漏凍沒賺)+攻(同批侵略性探索新 alpha：原生數學找結構性 edge，priors 防重打已判定戰場)+EXT 外部成熟經驗軸；空手紀律：無機會不可接受，換思路輸出解鎖監測/外部學習項；死軸重派一輪' },
    { title: 'Map', detail: '綜合成盈利機會地圖：ROI 排序、defend/attack/unlock/learn 分區、翻牆概率、證據等級、regime 標記、驗證路徑、下一步 owner；top_moves 永不空手；覆蓋缺口顯式標注' },
  ],
}

// 守=診斷現有；攻=探索新邊界。area: leak(已實現端漏) / frozen(能力端凍) / unrealized(該開發未開發)
// axis 由 workflow 側附加（不叫 agent 填，防覆寫死欄位）
const PROBE_SCHEMA = {
  type: 'object', required: ['verdict', 'diagnoses', 'opportunities', 'report_path'], additionalProperties: false,
  properties: {
    verdict: { type: 'string', enum: ['FINDINGS', 'BLOCKED'] },   // 盈利研判無合法 NO-OP（空手紀律：白旗不是合法出口）；BLOCKED 進 coverage
    // 守：基於 runtime 證據盤點現有系統盈利歸因
    diagnoses: { type: 'array', items: {
      type: 'object', required: ['area', 'title', 'classification', 'evidence', 'blocker', 'profit_impact', 'confidence'], additionalProperties: false,
      properties: {
        area: { type: 'string', enum: ['leak', 'frozen', 'unrealized'] },
        title: { type: 'string' },
        classification: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        evidence: { type: 'string', minLength: 15 },     // runtime 證據（命令輸出/查詢結果/file:line）；minLength 防樣板句
        blocker: { type: 'string', enum: ['gate', 'dormant', 'undeveloped', 'cost', 'exit-policy', 'paradigm', 'other'] },
        profit_impact: { type: 'string', minLength: 8 }, // 對盈利的影響（bps/方向；帶估算依據，不憑記憶）
        regime_caveat: { type: 'string' },               // bull-only/單 regime 標 regime-bet
        confidence: { type: 'string', enum: ['high', 'med', 'low'] },
      },
    } },
    // 攻：侵略性探索 — 系統還沒碰、但可能有 edge 的新方向（跳出現有範式、最廣 scope）
    // est_edge/est_cost/wall_break_prob 為 ROI 排序承重欄位 → required（oppBrief/Map 直接消費）
    // minItems:1 = 空手紀律的 schema 級保證：找不到直接機會時輸出解鎖監測/外部學習項，不許交白卷
    opportunities: { type: 'array', minItems: 1, items: {
      type: 'object', required: ['title', 'hypothesis', 'why_not_tried', 'est_edge', 'est_cost', 'wall_break_prob', 'how_to_validate', 'classification', 'confidence'], additionalProperties: false,
      properties: {
        title: { type: 'string' },
        hypothesis: { type: 'string', minLength: 20 },   // 可證偽的 alpha 假設；minLength 防「N/A/待定」變相空手
        why_not_tried: { type: 'string', minLength: 10 },// 系統為何還沒碰（盲區/範式限制/數據缺）
        paradigm_challenge: { type: 'boolean' },          // 是否質疑現有範式
        est_edge: { type: 'string', minLength: 8 },      // 預期 edge 與依據（大膽假設，標 ASSUMPTION）
        est_cost: { type: 'string' },                    // 開發成本估
        wall_break_prob: { type: 'string', enum: ['high', 'med', 'low', 'unknown'] },  // 翻越本 lens 適用成本牆的概率
        how_to_validate: { type: 'string', minLength: 20 },  // leak-free 驗證路徑（小心求證，不 hype）
        regime_caveat: { type: 'string' },               // bull-only/單 regime 標 regime-bet
        classification: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        confidence: { type: 'string', enum: ['high', 'med', 'low'] },
      },
    } },
    report_path: { type: 'string' },
  },
}

// EXT 軸 schema 變體：外部引用必須帶可核實來源（url+原文引句）與本地約束映射——防幻覺引用（空手壓力下最危險的失效模式）
const EXT_SCHEMA = JSON.parse(JSON.stringify(PROBE_SCHEMA))
EXT_SCHEMA.properties.opportunities.items.required.push('sources', 'local_constraint_fit')
EXT_SCHEMA.properties.opportunities.items.properties.sources = { type: 'array', minItems: 1, items: {
  type: 'object', required: ['url', 'claim_quote'], additionalProperties: false,
  properties: { url: { type: 'string', minLength: 10 }, claim_quote: { type: 'string', minLength: 10 } },   // claim_quote=WebFetch 實開後引的一句原文
} }
EXT_SCHEMA.properties.opportunities.items.properties.local_constraint_fit = { type: 'string', minLength: 20 }   // 映射回 VIP0/資本量/read-only lane/Rust 授權邊界

const EVIDENCE_SCHEMA = {
  type: 'object', required: ['summary', 'report_path'], additionalProperties: false,
  properties: { summary: { type: 'string' }, report_path: { type: 'string' }, gaps: { type: 'string' } },
}

// evidence_level/wall_break_prob/blocker 是排序與「ASSUMPTION 先驗證」規則的承重欄位 → required
const MAP_SCHEMA = {
  type: 'object', required: ['report_path', 'top_moves'], additionalProperties: false,
  properties: {
    report_path: { type: 'string' },
    top_moves: { type: 'array', minItems: 1, items: {   // minItems:1：地圖永不空手
      type: 'object', required: ['rank', 'title', 'mode', 'roi_rationale', 'wall_break_prob', 'blocker', 'evidence_level', 'next_step', 'owner'], additionalProperties: false,
      properties: {
        rank: { type: 'integer' },
        title: { type: 'string' },
        mode: { type: 'string', enum: ['defend', 'attack', 'unlock', 'learn'] },   // 守(救現有)/攻(開新邊界)/解鎖(前提變化監測)/學(外部成熟經驗引入)
        roi_rationale: { type: 'string', minLength: 15 },         // 預期 edge 提升 / 開發成本
        wall_break_prob: { type: 'string', enum: ['high', 'med', 'low', 'unknown'] },
        blocker: { type: 'string' },                              // 阻塞點（gate/dormant/undeveloped/operator-decision/paradigm）
        evidence_level: { type: 'string', enum: ['FACT', 'INFERENCE', 'ASSUMPTION'] },
        regime_caveat: { type: 'string' },                        // bull-only 標記須傳遞到 operator 面板
        next_step: { type: 'string', minLength: 10 },
        owner: { type: 'string' },
      },
    } },
  },
}

// harness 可能將 args 以 JSON 字串傳入，未 parse 會靜默降級到默認配置（2026-07-04 姊妹 workflow 實證）
const args_ = (typeof args === 'string') ? (() => { try { return JSON.parse(args) } catch (_e) { return null } })() : args
const scope = (args_ && args_.scope) || 'srv/ 全系統盈利面（策略/gate/風控/fills/AI 成本/dormant 能力/未開發 alpha 邊界）+ 非-Bybit 研究 lane（IBKR stock_etf_cash read-only/shadow，ADR-0048 邊界：禁 order-write/禁 auto-promote，僅研究價值與數據累積 ROI 層面）'
const baseline = (args_ && args_.baseline) || null
const focus = (args_ && args_.focus) || null   // 本輪盈利靶向（例：某策略虧損根因、某 alpha 假設）

// priors=已判定裁決快照，防各軸把已 NO-GO/KILL 方向重新發現（最大 token 漏 + 違 TODO §2 no-repeat 契約）。
// conductor 每輪應以 args.priors 傳現行版（主會話 memory 在手，零過時）；下方 fallback 是 2026-07-09 快照，僅未傳時兜底。
const priors = (args_ && args_.priors) || `已判定裁決快照（2026-07-09 兜底版；正本見各 memory topic 檔與 TODO §2 Closed No-Repeat Markers）：
- 搜索空間根因已定案：OHLCV+TA net alpha=0（n=159萬）；cost_gate 拒單 99.97% 全真負 0 誤殺（srv/memory/project_2026_06_13_profit_diagnosis_searchspace_reconfirm.md）
- 另類數據軸已驗畢：funding/OI/LSR、liq-cascade 雙 NO-GO（down-beta 偽裝）；Polymarket 價格子軸 KILL（odds 是 spot 機械衍生），事件/監管子軸 PARK $0 累積（約 2026-09 起到期覆核）
- maker-first mature-perp NO-GO（fill_sim 0/172 格淨正；VIP0 maker=+2bps 費用非 rebate，break-even 需 ≤0.4bps/side）——TODO §2 no-repeat，重提須 fee-tier/rebate/事件前提變化證據（srv/memory/project_2026_07_06_maker_first_nogo.md）
- 「缺 AI」非不賺錢根因；直接 AI/RL/MCP trader 已拒（PM SIGNED-WITH-GATES），現行=WP1-WP7 證據閉環全 flag-OFF——故意不鏡像 TODO，唯一索引 srv/memory/project_2026_07_07_ai_ml_maturity_roadmap.md
- 成本牆雙側：taker 往返 11-27bps @VIP0 / maker +2bps·side（非 rebate）；各 lens 須用原生成本結構計價，勿一律套 taker 牆（operator 6/14 鐵則的範疇錯誤教訓，srv/memory/feedback_active_profit_unconventional_mandate.md）
- 現行盈利工程主線=profit-first 自主 loop（discover→admit→execute→review→learn，spec docs/agents/profit-first-autonomy-loop.md）；最大 unrealized 缺口=動態候選 avg net 正值但零 candidate-matched order/fill proof
- 仍開放前沿：新上市寬價差 niche、事件驅動大 move、跨所、鏈上/option flow/Kalshi 原生事件、IBKR stock/ETF lane 研究價值、infra-tier（費率階梯/資本）前提監測`

const READONLY = 'read-only 盈利研判：不修復 / 不改策略·風控·gate·config / 不部署 / 不重啟 / 不啟動交易 / 不改 auth。Linux 證據僅 ssh trade-core read-only 命令；遇任何 mutation 需求停止標 BLOCKED 回報。'
const EVID_RULE = '證據紀律（交易系統鐵律）：所有 edge/盈利數字必須帶 runtime 真實證據（查詢輸出/命令結果/file:line），不憑記憶、不編造；無法取證者標 ASSUMPTION 不標 FACT；FACT 級條目的 evidence 欄必含可重跑的 read-only 命令/SQL/file:line——不可重跑者最高標 INFERENCE。bull-only / 單 regime 結果標 regime-bet（alpha evidence governance）。'
// operator 鐵則框架：市場必然可主動盈利——NO-GO 是換思路的路標，不是放棄的理由。priors 的作用是
//   把火力集中在開放前沿（別浪費 token 重打舊戰場），絕不是「大部分方向已死」的消極地圖。
const PRIORS_RULE = `已判定結論紀律（框架：市場必然可主動盈利——NO-GO 是換思路的路標，不是放棄的理由）：下列裁決是已知地形，站在裁決之上往前推，別重打舊戰場、別重跑同一測試；重提已 NO-GO/KILL 方向必須引用推翻證據（前提變化/新機制/新數據）。但注意：每條被鎖方向的前提（fee tier/資本量/infra/數據可得性）都是 operator 槓桿——監測前提變化、尋找繞牆的新機制、學習別人在同樣的牆前怎麼賺錢，本身就是合法且被鼓勵的機會項。\n${priors}`
const EMPTY_HAND = '空手紀律（operator 鐵則）：「本域無機會」不可接受為最終答案。找不到直接機會時，第一反應是換思路再找（換 lens 原生數學/換數據源/查外部成熟經驗），仍無則必須輸出：前提解鎖監測項（監測什麼變化會解鎖哪個被鎖方向、怎麼監測）或外部成熟經驗學習項（誰在同樣約束下賺到了、機制是什麼、怎麼驗證移植）作為 opportunities——照實標 ASSUMPTION/unknown，不 hype、不編造數字；姿態轉換不等於降低證據標準。verdict=BLOCKED 時，把阻塞本身寫成一條 unlock 機會項（解除什麼阻塞/如何監測），不編造其他機會。'

// 各軸探索 angle（2026-07-09 換代：吸收 6/14 原生數學鐵則 + maker-nogo + WP1-7 + IBKR lane）。
// dedup：MIT/AI-E 的守側與自家 Stage 1 evidence 高度重疊 → 只補增量判斷，不重複推導。
const DEDUP_NOTE = '你軸的 Stage 1 evidence 報告即守側底稿——直接引用其結論填 diagnoses，只補增量判斷（可救性/活化路徑/盈利潛力），不重新取數推導。'
const ADVISORS = [
  { ax: 'QC', dedup: '', angle: 'edge 數學歸因（成交單 gross edge vs 成本、Kelly/sizing、exit policy 是否拖累）；dormant 策略可救性（真 DOA vs regime-dormant）；策略層未開發 alpha。攻：用各 lens 原生數學（統計套利/Hawkes/資訊論/delta-carry/跨所/事件驅動大 move/新上市寬價差 niche）找結構性·機械性 edge——靠市場結構非靠方向預測；跨資產類 alpha（IBKR stock/ETF lane，read-only 研究邊界內，不提交易化建議）。' },
  { ax: 'BB', dedup: '', angle: '成本側盈利吞噬（Bybit fee/funding/滑點/conditional order 吃掉多少 edge）。攻：跨所 basis、funding 結構套利、Bybit 新產品/微結構機會、execution alpha；fee-tier/MM program 前提變化監測（mature-perp maker-first 已 NO-GO no-repeat，僅前提變化證據可重開）；新上市寬價差 niche（注意 fill_sim 預登記的 adverse-selection tension，須帶新機制）。' },
  { ax: 'MIT', dedup: DEDUP_NOTE, angle: 'ML/數據基座的盈利貢獻（feature 是否真帶 edge、pipeline 哪些是死表）；dormant ML 能力；已 live 非-OHLCV 特徵的 edge 貢獻覆核（已可離線搜，非「未用」）。攻：真未試數據軸（鏈上/option flow/Kalshi 原生事件）；Polymarket 事件·監管子軸 PARK 累積進度覆核（價格衍生子軸已 KILL 勿重提）；IBKR stock/ETF lane 數據累積 ROI 與研究優先級。' },
  { ax: 'AI-E', dedup: DEDUP_NOTE, angle: 'AI 推理 ROI（L2 花費 vs 帶來 edge、cost_edge_ratio）。攻：WP1-WP7 證據閉環各包的 dormant 活化路徑與 P1 硬化債（WP1 proof_packet hash/WP4 no-contact alias）對盈利閉環的阻塞排序；advisory-only 邊界內 AI 能解鎖的盈利路徑（直接 AI/RL trader 已拒勿重提；路線圖故意不鏡像 TODO，讀 srv/memory/project_2026_07_07_ai_ml_maturity_roadmap.md）。' },
  // EXT=外部成熟經驗軸（operator 鐵則：挫折的第一反應是搜索新外部信息、學習別人的成熟經驗）——
  //   內視角四軸之外的專責外部情報 lens，agentType 用 QC（read-only + WebSearch/WebFetch）
  { ax: 'EXT', dedup: '', external: true, angle: '①同量級小資本/零售 tier 被實證的盈利機制（業界實踐/論文/開源 quant 系統/交易員社群共識）——重點是「別人如何在我們同樣的牆（VIP0 費率無 rebate/小資本/無付費 feed）前賺錢」，含 crypto 與跨資產；②交易所生態變化（Bybit 新產品/費率活動/新上市節奏/promotion、IBKR 可研究產品）；③把每個外部機制映射回我們的約束（VIP0/read-only lane/Rust 授權邊界/資本量）給可行性與 leak-free 驗證路徑，不可移植的說明缺什麼前提。' },
]

phase('Evidence')
log(`盈利研判：${scope}；模式 read-only${baseline ? '；基線已凍結' : '；⚠️ 建議主會話先 Stage 0 凍結三端 SHA + active 策略 roster'}${(args_ && args_.priors) ? '' : '；⚠️ 未傳 priors，用 2026-07-09 兜底快照（可能過時）'}`)
// Evidence 先行=共享取數，防內視角 4 probe（EXT 不取 runtime）各自重複拉同批 runtime 數據（QC 現已有 Bash，非權限問題；取數 SOP 在 MIT/AI-E 域是分工取捨）
const baseNote = baseline ? `\n凍結基線（證據對齊此基線，跨端 drift 時以此為準並標注）：${baseline}` : ''
const EVIDENCE_SPECS = [
  { ax: 'MIT', prompt: `read-only 盈利證據取數（為 Probe 階段供真實數據）：用你的 SOP 從 DB/runtime 取——近期成交 fills 的 gross edge 分布與成本分解、各策略 active/dormant 狀態清單、各 gate（cost_gate 等）拒單統計（拒絕率+抽樣，供反事實 edge 判斷真負 vs 誤殺）、feature/pipeline 哪些真帶 edge vs 死表、profit-first loop runtime 狀態（\`_latest\` Cost Gate 候選 packet / standing 授權 envelope / candidate-matched order-fill proof 有無——strict scan 結果）。${READONLY} ${EVID_RULE}${baseNote} 落盤帶證據摘要並回填 report_path；gaps 填取不到的數據。` },
  { ax: 'AI-E', prompt: `read-only AI 成本盈利證據：取 AI 成本 ledger / cost_edge_ratio，評 L2 推理 ROI（AI 花費 vs 帶來的 edge），列 flag-off / dormant 的 AI 能力（含 WP1-WP7 證據閉環各包狀態）。${READONLY} ${EVID_RULE}${baseNote} 落盤回填 report_path；gaps 填取不到的數據。` },
]
const runEvidence = (s, attempt) => agent(
  `${attempt > 1 ? '【死軸重派第 2 輪】' : ''}${s.prompt}`,
  { agentType: s.ax, label: `evidence:${s.ax}${attempt > 1 ? '#2' : ''}`, phase: 'Evidence', schema: EVIDENCE_SCHEMA },
).then(r => r && { ...r, ax: s.ax })
let evidence = (await parallel(EVIDENCE_SPECS.map(s => () => runEvidence(s, 1)))).filter(Boolean)
const evDead = EVIDENCE_SPECS.filter(s => !evidence.some(e => e.ax === s.ax))
if (evDead.length) {   // 與 Probe 同等待遇的死軸重派（前綴變化破 resume null cache）
  log(`⚠️ Evidence 死軸重派：${evDead.map(s => s.ax).join(',')}`)
  evidence = evidence.concat((await parallel(evDead.map(s => () => runEvidence(s, 2)))).filter(Boolean))
}
const evidenceHoles = EVIDENCE_SPECS.map(s => s.ax).filter(ax => !evidence.some(e => e.ax === ax))
const evidencePaths = evidence.map(e => `${e.ax}:${e.report_path}`).sort()
const evidenceGaps = evidence.filter(e => e.gaps).map(e => `${e.ax}:${e.gaps}`)
log(`取數完成 ${evidence.length}/${EVIDENCE_SPECS.length}${evidenceHoles.length ? `；⚠️ 死亡：${evidenceHoles.join(',')}` : ''}；證據報告：${evidencePaths.join(', ') || '（落盤待讀）'}${evidenceGaps.length ? `；缺口：${evidenceGaps.join('；')}` : ''}`)

phase('Probe')
const evidenceNote = evidencePaths.length ? `\nStage 1 已取的 runtime 證據在這些報告，先讀再研判：${evidencePaths.join(', ')}${evidenceGaps.length ? `；已聲明取數缺口：${evidenceGaps.join('；')}` : ''}${evidenceHoles.length ? `；⚠️ 下列軸的 Stage 1 取數未完成：${evidenceHoles.join(',')}——該軸守側自行 read-only 取數或標 ASSUMPTION` : ''}` : '\n（Stage 1 證據如缺，自己 read-only 取或標 ASSUMPTION）'
const focusNote = focus ? `\n本輪盈利靶向：${focus}` : ''
const OPP_FIELDS = '每條 opportunity 標 hypothesis（可證偽）/why_not_tried/paradigm_challenge/est_edge（依據）/est_cost/wall_break_prob（翻越你這個 lens 適用的成本牆——taker/maker/事件各有牆，數字以 runtime 取證或 priors 現行值為準）/how_to_validate（leak-free 驗證路徑）；bull-only 填 regime_caveat。大膽假設、小心求證——不吐 hype，每個方向必須能落到可驗證的 leak-free 假設。樣板句（N/A/待定/暫無/湊字 unknown）不合格：unlock 項必須具體到監測對象/閾值/由誰查看，learn 項必須具體到來源與驗證移植路徑。前沿示例清單是地板不是菜單——照抄示例不構成探索，每軸至少 1 條示例之外的方向或 paradigm_challenge=true 項。'
const probePrompt = a => `盈利研判（你=${a.ax}）。範圍：${scope}。${READONLY} ${EVID_RULE}${baseNote}${evidenceNote}${focusNote}\n\n${PRIORS_RULE}\n\n【守 — diagnoses（基於 runtime 證據盤點現有盈利歸因）】本域的：leak=已實現端為何不賺（gate 拒單是真負仍正確 還是正 edge 誤殺？——over-gate 雙向按淨貢獻=(避免虧損)−(誤殺正 edge)−(摩擦)計價，每輪帶新鮮數據重問；成本吃掉多少？exit 拖累？）；frozen=能力端（dormant 可救性、flag-off 預期 edge、被 gate 鎖死的潛在 edge）；unrealized=本域該開發未開發。每條標 area/classification/evidence/blocker/profit_impact；bull-only 填 regime_caveat。${a.dedup}\n\n【攻 — opportunities（侵略性、跳出現有範式、從最廣 scope 找新 alpha）】不要受現有策略 roster、現有數據範式設限——但已判定裁決是已知地形（見上紀律），站在裁決之上往前推。用各 lens 的原生數學評估（operator 6/14 鐵則），偏結構性·機械性 edge（靠市場結構非靠預測）。當前真開放前沿示例：事件/監管子軸 PARK 到期覆核、新上市寬價差 niche、跨所、鏈上/option flow、IBKR stock/ETF lane 研究價值、profit-first loop 零 order/fill proof 缺口、infra-tier 前提監測。你的探索角度：${a.angle}。主動 WebSearch 借鑒外部思路與數據源。${OPP_FIELDS}\n${EMPTY_HAND}\n\n報告落盤回填 report_path（main 只收 schema 摘要，全文留報告）。`
// EXT=純攻外部情報：無守側（diagnoses 留空陣列），必用 WebSearch/WebFetch 學習外部成熟經驗
const extPrompt = a => `外部盈利情報掃描（你=QC 擔任 EXT 軸）。範圍：${scope}。${READONLY} ${EVID_RULE}${baseNote}${focusNote}\n\n${PRIORS_RULE}\n\n任務（WebSearch/WebFetch 是你的主要工具，必須實際使用）：學習別人的成熟經驗，把外部已被驗證的盈利機制帶回來映射到我們的約束。探索角度：${a.angle}\n${OPP_FIELDS} 每條 opportunity 必填 sources（每個 url 必須 WebFetch 實開並在 claim_quote 引一句原文——打不開的來源整條剔除或明確標 unverified-source 並降 confidence=low；嚴禁憑訓練記憶編造論文/repo/URL）與 local_constraint_fit（映射回 VIP0 費率/資本量/read-only lane/Rust 授權邊界後還成不成立、缺什麼前提）；外部實證≠我們的證據，一律標 ASSUMPTION 直到本地 leak-free 驗證。diagnoses 留空陣列（守側歸內視角四軸）。\n${EMPTY_HAND}\n\n報告落盤回填 report_path（main 只收 schema 摘要，全文留報告）。`
const runProbe = (a, attempt) => agent(
  `${attempt > 1 ? '【死軸/空手重派第 2 輪】' : ''}${a.external ? extPrompt(a) : probePrompt(a)}`,
  { agentType: a.external ? 'QC' : a.ax, label: `probe:${a.ax}${attempt > 1 ? '#2' : ''}`, phase: 'Probe', schema: a.external ? EXT_SCHEMA : PROBE_SCHEMA },
).then(r => r && { ...r, axis: a.ax })
let probes = (await parallel(ADVISORS.map(a => () => runProbe(a, 1)))).filter(Boolean)
// 死亡或空手（攻側空）都重派一輪——空手紀律的代碼級後備（minItems 已實證 tool-call 層硬強制，
//   此處兜「持續違規→null→死軸」路徑；idle-kill/限額中斷是已知風險）；前綴變化天然破 resume 的 null cache
const needRetry = ADVISORS.filter(a => {
  const p = probes.find(x => x.axis === a.ax)
  return !p || !(p.opportunities || []).length
})
if (needRetry.length) {
  log(`⚠️ 死亡/空手軸重派：${needRetry.map(a => a.ax).join(',')}`)
  const retried = (await parallel(needRetry.map(a => () => runProbe(a, 2)))).filter(Boolean)
  // 按 retried(非 needRetry)過濾：重派死亡時保留第一輪部分結果（其空手狀態仍被 coverage 的 empty-hand 捕捉）
  probes = probes.filter(p => !retried.some(r => r.axis === p.axis)).concat(retried)
}
// 覆蓋誠實聲明：未回報/BLOCKED/二輪仍空手 ≠ 該域清白（姊妹 workflow coverage_holes 同構）
const coverageHoles = ADVISORS.filter(a => !probes.some(p => p.axis === a.ax)).map(a => a.ax)
  .concat(probes.filter(p => p.verdict === 'BLOCKED').map(p => `${p.axis}(BLOCKED)`))
  .concat(probes.filter(p => !(p.opportunities || []).length).map(p => `${p.axis}(empty-hand)`))
  .concat(evidenceHoles.map(ax => `${ax}(evidence)`))
const emptyDefense = probes.filter(p => p.axis !== 'EXT' && !(p.diagnoses || []).length).map(p => p.axis)
if (emptyDefense.length) log(`⚠️ 守側空手（僅警示，defend 類 top_moves 依賴守側輸入）：${emptyDefense.join(',')}`)

const allDiag = probes.flatMap(p => (p.diagnoses || []).map(d => ({ ...d, axis: p.axis })))
const allOpp = probes.flatMap(p => (p.opportunities || []).map(o => ({ ...o, axis: p.axis })))
const probePaths = probes.map(p => p.report_path).filter(Boolean).sort()
if (!allOpp.some(o => o.paradigm_challenge)) log('⚠️ 全 wave 零 paradigm_challenge——疑照抄菜單，conductor 應檢視攻側質量')
log(`研判完成 ${probes.length}/${ADVISORS.length}（${probes.map(p => `${p.axis}:${p.verdict}`).join(' ')}）${coverageHoles.length ? `；⚠️ 覆蓋缺口：${coverageHoles.join(', ')}` : ''}；診斷 ${allDiag.length}（漏 ${allDiag.filter(d => d.area === 'leak').length}/凍 ${allDiag.filter(d => d.area === 'frozen').length}/沒賺 ${allDiag.filter(d => d.area === 'unrealized').length}）+ 機會 ${allOpp.length}（質疑範式 ${allOpp.filter(o => o.paradigm_challenge).length}）`)

phase('Map')
// 綜合成 ROI 排序的開發機會地圖（守攻分區）；落盤，return 只給排序摘要 + 路徑
const diagBrief = allDiag.map(d => `[${d.axis}/${d.area}] ${d.title}（${d.classification}，blocker=${d.blocker}，impact=${d.profit_impact}${d.regime_caveat ? `，regime=${d.regime_caveat}` : ''}）`).join('\n')
const oppBrief = allOpp.map(o => `[${o.axis}${o.paradigm_challenge ? '/範式挑戰' : ''}] ${o.title}（edge=${o.est_edge}，cost=${o.est_cost}，翻牆=${o.wall_break_prob}，驗證=${o.how_to_validate}，${o.classification}${o.regime_caveat ? `，regime=${o.regime_caveat}` : ''}）`).join('\n')
const coverageNote = coverageHoles.length ? `\n⚠️ 覆蓋缺口（未回報/BLOCKED/空手 ≠ 該域清白；地圖按殘缺輸入產出，報告與 top_moves 均須標明）：${coverageHoles.join(', ')}` : ''
const runMap = attempt => agent(
  `${attempt > 1 ? '【重派第 2 輪】' : ''}綜合盈利機會地圖（你=PA）。${READONLY}${coverageNote}\n研判報告：${probePaths.join(', ') || '（僅下方摘要）'}——先用下方摘要 shortlist；對擬入 top_moves 的候選與全部 FACT 級 diagnoses 讀對應報告核證據，落選的 ASSUMPTION 項不必讀全文。擬入 top_moves 的 FACT 級支撐至少抽 1 條把 evidence 欄的 read-only 命令/SQL 實際重跑核對——重跑失敗或無可重跑命令 → 降 INFERENCE 並重排（防 FACT 自封/impact 灌水搶排名）。\n\n${PRIORS_RULE}\n\n診斷（守）：\n${diagBrief || '（無）'}\n\n機會（攻）：\n${oppBrief || '（無）'}\n\n產出 ROI 排序的 top_moves：每項 mode（defend 救現有 / attack 開新邊界 / unlock 前提解鎖監測 / learn 外部成熟經驗引入）、roi_rationale（預期 edge 提升 / 開發成本）、wall_break_prob、blocker、evidence_level、regime_caveat（有則必傳遞）、next_step、owner。排序原則：最快驗證路徑優先（flag-off 等近零成本驗證 > 開發新東西）；翻牆概率高 + 證據強優先；對 ASSUMPTION 級機會標「需先 leak-free 驗證」不直接排高；帶 regime_caveat 者不得僅憑 bull 窗數字排前；與已判定裁決衝突且無推翻證據者剔除——但其前提監測有價值時轉為 unlock 項而非丟棄。空手紀律（operator 鐵則）：top_moves 永不空手，「現無廉價 lever / 只能等」不可接受為最終結論——直接機會稀薄時以 unlock（監測什麼、閾值、誰看）與 learn（學什麼、驗證移植路徑）補位；defend 與 attack 都要有（不能只救現有也不能只畫餅），姿態強硬但證據誠實（不 hype、ASSUMPTION 照標）。報告落盤回填 report_path。${EVID_RULE}`,
  { agentType: 'PA', label: `profit-map${attempt > 1 ? '#2' : ''}`, phase: 'Map', schema: MAP_SCHEMA },
)
let mapResult = await runMap(1)
if (!mapResult) {   // 旗艦交付不容單點：與 probe 同等待遇重派一次
  log('⚠️ Map 死亡，重派')
  mapResult = await runMap(2)
}
const mapModes = new Set(((mapResult && mapResult.top_moves) || []).map(m => m.mode))
const modeGaps = mapResult ? ['defend', 'attack'].filter(m => !mapModes.has(m)) : []
if (modeGaps.length) log(`⚠️ top_moves 缺 ${modeGaps.join('/')} 分區（僅警示，交 conductor 判斷是否重派）`)

// return 瘦身：摘要 + 路徑，全文在 report_paths（沿用 full-audit 的 context 經濟）
const slimD = d => ({ axis: d.axis, area: d.area, title: d.title, blocker: d.blocker, impact: d.profit_impact, cls: d.classification, regime: d.regime_caveat })
const slimO = o => ({ axis: o.axis, title: o.title, paradigm: !!o.paradigm_challenge, edge: o.est_edge, wall: o.wall_break_prob, cls: o.classification, regime: o.regime_caveat })
return {
  scope, mode: 'read-only', baseline,
  coverage: {   // 覆蓋誠實：holes ≠ 清白；map_failed 時 top_moves 空陣列是「沒跑」不是「無機會」
    probes: probes.map(p => `${p.axis}:${p.verdict}`), holes: coverageHoles,
    evidence_gaps: evidenceGaps, defense_empty: emptyDefense,   // 存活 agent 自報缺口/守側空手也上交 conductor
    paradigm_challenges_zero: !allOpp.some(o => o.paradigm_challenge),   // 全 wave 零範式挑戰=疑照抄菜單
    mode_gaps: modeGaps, map_failed: !mapResult,
  },
  totals: {
    diagnoses: allDiag.length, leak: allDiag.filter(d => d.area === 'leak').length,
    frozen: allDiag.filter(d => d.area === 'frozen').length, unrealized: allDiag.filter(d => d.area === 'unrealized').length,
    opportunities: allOpp.length, paradigm_challenges: allOpp.filter(o => o.paradigm_challenge).length,
  },
  report_paths: { evidence: evidencePaths, probe: probePaths, map: mapResult && mapResult.report_path },
  top_moves: (mapResult && mapResult.top_moves) || [],   // ROI 排序開發機會（守攻分區）
  diagnoses: allDiag.map(slimD),     // 守：現有盈利歸因（全文在 probe 報告）
  opportunities: allOpp.map(slimO),  // 攻：新 alpha 邊界（全文在 probe 報告）
  // 主會話接手：top_moves 是開發優先級草案；operator 拍板。defend 類（flag-off/dormant 解凍）走最快驗證
  //   路徑；attack 類 ASSUMPTION 先 leak-free 驗證（QC walk-forward / 歷史 kline backfill）才升格開發項；
  //   可執行候選優先送 profit-first loop 的 discover→admit 通道（spec docs/agents/profit-first-autonomy-loop.md），
  //   與 TODO §1/§2 對齊後才另開 Sprint——不與 standing loop 形成兩條平行的開發權威。
  next: '主會話/PM 整合 top_moves → operator 拍板開發優先級；候選優先送 profit-first loop discover→admit 通道並與 TODO §1/§2 對齊；attack 類 ASSUMPTION 機會先 leak-free 驗證再進 Sprint；defend 類（flag-off/dormant 解凍）走最快驗證路徑；unlock 類按 TODO passive-wait 規則掛監測（healthcheck/review date/named condition）；learn 類派 QC/MIT 外部經驗驗證移植任務',
}
