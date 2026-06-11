---
name: reference-ultracode-full-audit
description: ultracode 全盤審計編排的持久化設置 — saved workflow + conductor skill 的位置與調用方式
metadata: 
  node_type: memory
  type: reference
  originSessionId: f24d69ff-8ed3-407e-9b02-642e02da37d9
---

Operator 很少跑 ultracode，但啟用後希望編排形態即取即用（手動 prompt 或自動識別）。2026-06-10 已落地為兩件套（單副本在 srv/.claude，根目錄 symlink）：

- **Saved workflow**：`srv/.claude/workflows/openclaw-full-audit.js` — 審計群並行（默認 10 軸 CC/FA/E3/BB/QC/MIT/AI-E/E5/A3/R4）→ 每軸原始 C/H finding 對抗複核 →（`args.fix=true` 才）E1 worktree 修復→E2 複審→E4 回歸對照 BASELINE。**默認 report-only**，`max_fixes` 默認 5；args：baseline/scope/axes/focus/fix。
- **Conductor skill**：`srv/.claude/skills/ultracode-full-audit/SKILL.md` — 主會話專用（不掛 subagent）；五階段（Stage0 baseline freeze + Stage1 R4/TW + Stage2 workflow + Stage3 PA 驗真層 + Stage4 PM 裁決，0/3/4 主會話親做）；模式識別（ultracode off→降級 PM 順序鏈；active model 自檢；計費知情）；標準劇本（深挖方向按 primary 軸拆進 focus）。調用 `Workflow({name:"openclaw-full-audit", args})`，fallback `scriptPath`。

**How to apply**：operator 啟用 ultracode + 說「全盤審查/全面檢查/冷酷對抗審計」→ 主會話按該 skill 跑五階段；修復要二次顯式 `fix:true`。單點改動不用它，走 PM.md 派工模板+對抗驗證多視角化協議。

**2026-06-10 對抗審查強化（main `0ec27eca`）**：4-critic 對抗審查（全 FLAWED，2 CRITICAL，含真實歷史案例佐證）逼出去重設計鐵律——**去重只在呈現層(Cluster)聚簇，verify/fix 永遠按原始 finding 粒度**（教訓：同檔兩 auth-bypass 若 Verify 前合併→只修一個→另一個未鑑權上線=去重親手造安全回歸）。聚簇主鍵 `(normalized_file, symbol_anchor)`，defect_type 不進主鍵（各軸盲選必分叉反漏併招牌案例）；後置標註防錨定淺化；confidence≠命中軸數（異質 corroboration 由 PA 判）。對抗強度四要素：①雙向（假陽性 verify + 假陰性 negative-space 各軸自審 + seam critic）②可達性第三質疑者（auth/secret/gate/leakage/replay+CRITICAL，latent 降級）③粒度不可壓縮 ④不為對抗而對抗（seam/盲區產 re-probe 非直接 finding）。誠實校準：機械只抓「同 file 同 anchor」高精度子集，pre-filter 非替代，首次實戰回放校準。**教訓**：① `git push 2>&1|tail && {成功}` 被 tail 吞 exit code 誤判，push 判定須 `git push; echo $?` 不 pipe；② Mac→github:22 timeout 時走 git bundle→`scp trade-core`→Linux push 中轉（Linux→GitHub 穩）；③ 關鍵設計決策用 workflow 派 4-critic 對抗審查（over/under-merge/completeness/constraint-fidelity）值回票價，救下安全回歸。

**2026-06-10 交接 context 優化 + profit-diagnosis 盈利研判（main `c05ae67e`+）**：①交接鏈兩洩漏點修復——workflow return 瘦身（evidence/impact 全文不進 main，改 slim+report_paths 各軸報告路徑按需讀；schema 加 report_path 欄位）+ PM.md 回傳契約（subagent final message 只 VERDICT+1-3 句+路徑+計數，完整留落盤不複述）+ Conductor context 紀律（main 只持決策骨架+指針，進度走 TodoWrite/決策走報告防 compact，大 fan-out 優先 Workflow）。②**新增 profit-diagnosis saved workflow**（`srv/.claude/workflows/profit-diagnosis.js`，與 full-audit 對偶：找錢 vs 找問題）——operator 要求「侵略性、跳出 box、最廣 scope 找盈利」。三階段 read-only：Evidence(MIT/AI-E runtime 取 fills/edge/gate 拒單/dormant/AI 成本)→Probe(QC/BB/MIT/AI-E 各域**守**診斷 leak/frozen/unrealized +**攻**侵略性探索新 alpha，允許質疑 OHLCV 範式天花板/搜索空間是否本身錯，可 WebSearch)→Map(PA 綜合 ROI 排序機會地圖，守攻分區)。鐵律：edge 帶 runtime 證據不憑記憶、bull 標 regime-bet、attack 類 ASSUMPTION 先 leak-free 驗證才升格、flag-off/dormant 近零成本驗證優先。**方向指導（memory 已知，需 runtime 驗證）**：cost_gate 拒 90.5%=真負 0 誤殺→放鬆 gate≠解法（真問題=無正 edge alpha 非 gate 太嚴）；flag-off(residual producer/STAGE0R)=最快驗證路徑；歷史 kline backfill=最快多 regime 樣本；A1=regime-dormant 可救。skill 接入見 ultracode-full-audit「姊妹編排」節。**memory 分叉注意**：本 session 實讀 `srv/memory/`，非 CLAUDE.md 寫的 `.claude/projects/-TradeBot/memory/`（後者舊快照），屬 [[project_multi_session_memory_race]]。
