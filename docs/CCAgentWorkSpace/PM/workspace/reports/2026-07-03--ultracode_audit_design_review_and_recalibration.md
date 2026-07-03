# Ultracode 全盤審計「設計本身」審查 + 全體系裁決座標校準 — 2026-07-03

Operator 命題：審 openclaw-full-audit 設計是否全面/無疏漏，特別加重程序優化軸；
期間 operator 逐步確立統一裁決座標（正本：Mac memory `feedback_goal_oriented_review`）：
①終極目的=可審計+可追蹤+有限自我進化+持續盈利；②風控=減虧=綜合盈利組成，
控制按淨貢獻=(避免虧損)−(誤殺正 edge)−(摩擦)計價，過緊與缺失同類缺陷雙向審，
live fail-closed 不鬆動；③精簡=開發成本側盈利槓桿（臃腫=每輪開發重複繳的 token 稅）。

## 方法
主會話親讀兩正本逐行核 + 6 視角獨立審（5 工程視角 workflow 兩度因 usage 中斷，
其 finding 由主會話親驗代替雙質疑者複核並標註）+ 目標對齊視角（含風控雙向補審）
+ 18 role 定義兩路校準審（治理組 16 findings / 工程組 9 findings，全部引文核實）。

## 設計裁決（對 openclaw-full-audit.js + ultracode-full-audit SKILL.md）
強項確認：對抗架構高質量（粒度不可壓縮鐵律/negative-space/seam critic/可達性
第三視角/無反證不成立）；可追蹤性雙 owner；審計產物自身有 lineage；fix 姿態正確。
系統性偏差（同根）：裁決座標繼承純風險視角——
- F8(H) 風控單向：defect_type 過鬆 5 類 vs 過緊 0 類；零 focus 問「拒單誤殺」；
  過緊類反被 latent 降級反殺。淨效果=實跑越多輪越安全越凍越不賺。
- F1(H) M/L 永不進 Verify→fix plan confirmed-only→目的承載型 MEDIUM 結構性無修復路徑。
- F2(H) fix 隊列 slice 無排序，CRITICAL 可被軸序擠出。
- F3(H) 「有限自我進化」四性質中唯一無 owner，落 audit↔profit 兩 workflow 縫隙。
- F6(H) Stage 4 無 profit-diagnosis ROI 對照（機會成本不可見）。
- 機械缺陷：BLOCKED verdict 無消費者；質疑者死亡靜默降門檻（0-1 票可 confirmed）；
  verify prompt 未注入 READONLY。
- F5(M) 審計迴圈無制度化自我進化；F4(M) 可審計性寄生劇本 focus；F7(L) latent 語義反轉。

## 已落地（本日兩 commit，均 [skip ci]）
1. `0494e0e76` 18 role + pr-adversarial-review 校準（21 項）：E5 計價雙軸+token 稅
   唯一 owner；E4 去 Mac 硬編碼(Linux 失效 bug)+Gate 雙向測試；E1/E1a Simplicity
   first；E2 臃腫合入可退回；PA 代碼足跡契約；CC/QC/BB/FA 雙向審；FA Gap 三分
   (+dormant)；QA 不凍死驗收；MIT V001-V024 stale 修正(實測 V146)；PM 派工模板
   +裁決座標注入/對抗驗證加 QC/sign-off 機會成本/三分類；R4 高頻讀檔巡檢；TW 引用不複寫。
2. 本 commit 設計修訂：DEFECT_TYPES+over-gate/evolution-blocker；GOAL_TYPES M 級
   准入 Verify；CAPABILITY_TYPES 豁免 latent 降級；質疑者法定人數=2；fix 隊列
   severity→可達性排序；coverage_holes 顯式化(BLOCKED 有消費者)；verify 注入
   READONLY；ANNOTATE 計價校正；SKILL.md 裁決座標節+Stage 4 ROI 對照+audit retro
   +QC/FA/E5 focus 雙向化。語法 node --check(ESM wrap) PASS。

## 需 operator 決策（未動）
1. CC/FA/QC 完成序列要求寫報告 vs tools 無寫入權矛盾——建議方案 A：加 Bash+
   disallowedTools: Edit,Write（對齊 E3/MIT 前例）。
2. PM.md P0 快速通道(跳 QA) vs QA.md「鏈不可跳」正面衝突，且無憲法出處。
3. 8 subagent 檔是否內嵌 STATUS 首行（兩 reviewer 意見分歧：中央注入 vs 非 PM 入口失效）。
4. CLAUDE.md 優先序措辭（real net PnL 列第 6）與新裁決座標的調和——治理級，建議 AMD。

## 殘留
- 5 工程視角的雙質疑者複核未跑完（usage 中斷 ×2）；其 finding 已由主會話親驗，
  置信度標註：機械類=已驗證，判斷類=單源。下輪 ultracode 空閒時可
  resumeFromRunId wf_714b5678-a49 補跑（cache 免重付 Audit 段）。
- spec-compliance skill 的 dormant 三分同步（FA role 已改，skill 正本未動）→ 派 TW/FA。
