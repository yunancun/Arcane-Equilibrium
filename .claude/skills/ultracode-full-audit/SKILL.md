---
name: ultracode-full-audit
description: 主會話/conductor 專用，非 subagent skill：operator 要求「全盤審查/全面檢查/multi-agent 優化/冷酷對抗審計」時必讀，含 ultracode 未啟用時的降級判斷。
---

# Ultracode 全盤審計編排（持久化設置）

> 本 skill 是給**主會話（conductor）**的編排說明書，不掛載到任何 subagent。
> 正本腳本：`.claude/workflows/openclaw-full-audit.js`（Mac: `~/Projects/TradeBot/srv/`；Linux: `~/BybitOpenClaw/srv/`）
> 分工原則：**並行 fan-out 與對抗複核交給 workflow 腳本；需要主會話判斷的單點工作（git 凍結、跨報告收斂、operator 決策、TODO 裁決）由 conductor 親做，不下放給 fan-out。**

## 模式識別（先判斷再動）

1. **ultracode 已啟用**（session 設置開啟，或 operator 本輪輸入含 ultracode）→ 按下方五階段執行。
2. **未啟用 ultracode** → 不擅自跑 multi-agent fan-out：向 operator 確認，或降級為 PM 順序鏈（PM.md 派工模板逐軸派發，成本低很多）。
3. **active model 自檢**：主會話 system prompt 會聲明當前模型。頂級模型 → 編排與收斂由主迴圈直接承擔；較小模型 → 仍可跑 workflow（編排邏輯是確定性的），但 Fix 段建議 report-only，收斂段可能需分多 session 防 compact。
4. 計費知情：頂級新模型可能按倍率/credits 計量（以官方 pricing 為準）；大規模 fan-out（10 軸 + 對抗複核 ≈ 數十萬至上百萬 token）前先確認 operator 知情，尤其免費窗口結束後。

## 五階段流程（Stage 0/3/4 主會話親做；Stage 1/2 可 workflow 代跑）

### Stage 0 — Baseline freeze（主會話，審計可信度地基）
凍結後 fan-out，否則 finding 的 affected line 可能指向跑到一半就漂移的代碼。記錄並寫入 PM workspace 報告 `{AUDIT_DATE}--cold_audit_baseline.md`：
- AUDIT_DATE（執行當日，不寫死）
- 三端 git SHA：`git -C <srv> rev-parse HEAD`（Mac）、`git -C <srv> rev-parse origin/main`、`ssh trade-core 'git -C ~/BybitOpenClaw/srv rev-parse HEAD'`（read-only）
- dirty worktree 快照：`git status --short`
- E4 memory 最新 `BASELINE:` 行（測試基線錨）
- active SoT 清單、runtime 是否納入、允許的 ssh 命令範圍、本輪禁止事項、報告命名規則
- 把凍結摘要作為 `args.baseline` 傳入 workflow，注入每軸對齊

### Stage 1 — 索引/文檔地圖（可選前置，R4 ∥ TW）
全鏈深審時先建地圖供 Stage 2 引用。R4：索引完整性 + 交叉引用 + .claude 配置漂移 + memory 體量巡檢；TW：文檔去重盤點（範圍=上次盤查後至今，無則近 60 天）。可併入 Stage 2 的 axes（R4 已在默認軸內；TW 按需加），或先單獨派這兩個再跑主審計波。

### Stage 2 — 並行專項審計（workflow 腳本）
```
Workflow({ name: "openclaw-full-audit", args: { baseline, focus, axes?, scope?, fix? } })
```
腳本做（經 2026-06-10 對抗審查強化）：
1. **Audit**：10 軸並行 fan-out（read-only 邊界 + 本輪 focus；FACT/INFERENCE/ASSUMPTION 三分；finding **後置標註** defect_type[]/symbol_anchor/root_anchor——寫完才標、不前置選，防錨定淺化調查）+ 各軸 **negative-space 盲區自審**（按 SOP 本該查但未展開的，列 assumptions）。
2. **Verify**：對**每軸原始 C/H + 目的承載 M（GOAL_TYPES：over-gate/evolution-blocker/lineage-gap）finding** 各跑雙質疑者（證據鏈 ∥ 影響；對抗暴露面**不被去重壓縮**；質疑者法定人數=2，缺票降 disputed 不得靜默 confirmed）；auth-bypass/secret-leak/missing-gate/leakage/replay-misuse 類或 CRITICAL 追加**第三質疑者（可達性）**——latent（生產不可達）降級不進修復隊列（over-gate/evolution-blocker 機能類除外：不可達正是缺陷本身，不降級）。並行跑 **seam critic** 審軸交界無主盲區，產 re-probe 指令。
3. **Cluster**（純呈現層）：對 confirmed 按 `(規範化 file, symbol_anchor)` **無損聚簇**——members 全保留、不改 severity/confidence、**不影響 verify/fix 粒度**。多軸共置標 hit_axes 供 PA 判異質 corroboration。缺 anchor 者透傳。
返回 consensus / ungrouped / latent / disputed / medium_low_info / assumptions / seam_reprobes。

> **去重設計鐵律（對抗審查確立，勿違背）**：去重只在呈現層聚簇；verify 與 fix 永遠按原始 finding 粒度，合併**絕不**縮減對抗暴露面、**絕不**掩蓋同位置第二個缺陷（歷史教訓：同檔兩個 auth-bypass 被錯併→只修一個→另一個未鑑權上線）。defect_type **不進**聚簇主鍵（各軸盲選必分叉，反而漏併）。confidence **不等於**命中軸數（防虛假共識：3 個弱 agent 撞同一錯誤≠更可信，異質性由 PA 判）。

### Stage 3 — PA 驗真層（主會話接手，workflow 不固化此段）
拿 workflow 返回後，主會話親做或派 PA：
- **consensus 簇**：機械已按位置聚好，PA 免人工搜索；只需判每簇是否「異質 corroboration」（多軸推理路徑真獨立才算佐證，同源證據標 shared-premise）
- **ungrouped + 跨檔/跨 type 同源**：機械抓不到的殘餘語義去重在此（這是機械聚簇的能力邊界，見下「誠實校準」）
- **disputed + assumptions + seam_reprobes**：targeted re-probe（seam/盲區須派軸帶證據審後才升格 finding，不直接採信）
- 按 P0-P3 分級（CRITICAL=P0/HIGH=P1/MEDIUM=P2/LOW+INFO=P3）
- 生成 validated fix plan：confirmed-only / rejected-unproven / 每項 path+anchor / fix owner / verifier / 可並行+必序列化章節 / session 拆分建議（避 compact）/ 每修復包檔案範圍+測試+驗收 / 需 operator 決策項 / 需 Linux read-only 證據項 / latent debt 記錄 / 未批准前嚴禁動手項
- → `PA/workspace/reports/{AUDIT_DATE}--cold_audit_validated_fix_plan.md`

> **去重期望值誠實校準**：機械聚簇只可靠處理「同 file 同 anchor」的高精度子集（配置類 finding 跨軸天然對齊 anchor，招牌案例如多軸命中同一 TOML key 能抓）；「跨檔同源」（root 在 A.rs、symptom 在 B.py）與「同 bug 不同 anchor 字串」機械抓不到，仍歸 PA。這是 **pre-filter 非替代**——首次實戰後應回放最近 audit 統計機械抓取比例，校準是否值得，而非假設它消除全部 PA 去重。

### Stage 4 — PM 最終裁決（主會話）
讀 PA plan 終審：是否違 16 原則 / 合 dispatch protocol / runtime-docs drift / 需 operator 先決策 / 未證實猜測誤入 / 與最近 profit-diagnosis map 做 ROI 對照（存在時；近零成本 defend 槓桿未排入 → pm_final 加 opportunity-cost 節交 operator）。
- **audit retro（審計迴圈自我進化）**：pm_final 固定含三小節——上輪 open 項覆核、本輪 defect_type=other 清單（枚舉演化候選）、下輪 focus 建議（本輪漏報/assumptions 回流）。
- → `PM/workspace/reports/{AUDIT_DATE}--cold_audit_pm_final.md`（遵 CLAUDE.md docs 放置規則，不放 repo 根目錄）
- 只把已確認、可執行、需追蹤項更新進 TODO.md（連結報告非貼全文）；未證實猜測留 PA 報告附錄「待證假設」，不入 TODO

## args（全部可選）

| 參數 | 默認 | 說明 |
|---|---|---|
| `baseline` | null | Stage 0 凍結摘要（三端 SHA / dirty / BASELINE 行）；注入每軸對齊 affected line。未傳會 log 警告 |
| `scope` | srv/ 全倉 | 審計範圍描述 |
| `axes` | 10 軸 CC/FA/E3/BB/QC/MIT/AI-E/E5/A3/R4 | 審計軸=agent 名；全鏈深審加 `"E4"`（測試矩陣審計）`"TW"`（文檔盤點） |
| `focus` | null | 本輪靶向必查項。字串=注入全軸；`{CC:"...", E3:"..."}`=按軸注入。**非範圍上限**，role SOP 全量仍是基準 |
| `fix` | false | **默認 report-only**；true 時對 confirmed（severity→可達性排序後截 max_fixes）派 E1 worktree 修復 + E2 複審 + E4 回歸 |
| `max_fixes` | 5 | fix 模式單輪修復上限，餘量留報告 |

## 嚴重度映射

腳本用 CRITICAL/HIGH/MEDIUM/LOW/INFO；對應治理慣用 P0/P1/P2/P3：CRITICAL=P0、HIGH=P1、MEDIUM=P2、LOW+INFO=P3。PA/PM 報告用 P 級表述，與 finding 嚴重度一一對應。

## 裁決座標（operator 2026-07-03 確立；審查、分級、修復排序的統一計價）

盈利=終極目的核心；風控=減虧=綜合盈利組成，兩者不對立。每道控制按淨貢獻 =（避免虧損）−（誤殺正 edge）−（摩擦）計價：負淨貢獻控制（over-gate）與缺失控制（missing-gate）同類缺陷，**審計必須雙向找**。程序精簡=開發成本側盈利槓桿：readability-debt/duplicate-logic 按重複開發成本（被 agent 讀改頻率×體量×剩餘壽命）計，非按工程風險計。四性質（可審計/可追蹤/有限自我進化/持續盈利）承載型 MEDIUM 進對抗複核不沉底。同 P 級內 tiebreak 按對終極目的貢獻。**邊界**：live fail-closed 5 hard gates 與 9 安全不變量不受 over-gate 審查波及，永不鬆動。

## 對抗強度（最高標準的構成）

達「最高最嚴格對抗」由四件事構成，缺一不可：
1. **雙向對抗**：不只查假陽性（已報 finding 是否錯報），也查假陰性（盲區/漏報）——後者靠各軸 negative-space 自審 + seam critic。「雙向」同時指風控方向性：過鬆（missing-gate 等 5 高危類）與過緊（over-gate/evolution-blocker）並審。
2. **可達性第三視角**：高危類（auth/secret/gate/leakage/replay）+ CRITICAL 加第三質疑者判生產可達性；latent（代碼級存在但生產不可達）降級，不與可觸發缺陷同級（機能/摩擦類 over-gate/evolution-blocker 除外——其「不可達」正是缺陷本身）。
3. **粒度不可壓縮**：verify/fix 永遠按原始 finding，去重不削弱對抗（見上鐵律）。
4. **不為對抗而對抗**：質疑者「拿不出具體反證則 refuted=false」；seam/盲區產 re-probe 指令而非直接成 finding，必經一次帶證據審計才升格——空口指控進不了報告。

## 標準調用劇本（冷酷對抗全程序鏈審計）

```
1. Stage 0：主會話凍結三端 SHA + dirty + BASELINE → 寫 baseline 報告
2. Stage 2（含 Stage 1 R4/TW）：
   Workflow({ name: "openclaw-full-audit", args: {
     baseline: "<Stage0 凍結摘要>",
     axes: ["CC","FA","E3","BB","QC","MIT","AI-E","E4","E5","A3","R4","TW"],
     focus: {  // 本輪靶向（深挖方向），按軸；不是範圍上限
       FA:  "authority chain lineage 完整性（StrategySignal→…→ExecutionReport 缺失 report）；GUI 聲稱成功 vs Rust authority 實態；dormant/flag-off 槓桿 owner+解凍條件盤點、learning loop 端到端可達性（evolution-blocker）",
       E3:  "live/live_demo 五 gate 可繞性（live_reserved/operator role/OPENCLAW_ALLOW_MAINNET/secret slot/authorization.json）",
       QC:  "策略參數/風控閾值 tunable vs hardcoded；replay 誤用為 promotion evidence；Stage 0R/Stage 1 Demo 邊界污染；production gate 拒單誤殺率量化（over-gate 雙向：淨貢獻=(避免虧損)−(誤殺正 edge)−(摩擦)）",
       MIT: "migration metadata vs 實際 DB object 一致性（ssh read-only）；ML 階段 shadow/advisory/demo/live-blocked 明確定位",
       AI-E:"should_call_ai=true 未調用 / 偽 AI / fallback 不誠實 / 成本不落 ledger / tier-routing 與實際不一致",
       A3:  "fake-success：按了只改前端 state / Python API 回成功但 Rust authority 未變 / 顯示 live-ready 但 gate blocked",
       E4:  "測試盲區：fail-closed / timeout / Bybit retCode / concurrency / stale data / auth expiry / replay-promotion 邊界",
       BB:  "Bybit 限額類參數 hardcoded vs 應 config",
       E5:  "代碼級死代碼/重複邏輯/臃腫熱檔（token 稅=被 agent 讀改頻率×體量×剩餘壽命排序，產出 top 精簡標的）— 與 FA 功能級死代碼切割"
     }
   }})
3. Stage 3：主會話接 confirmed/disputed/assumptions → PA 去重分級 + re-probe → validated fix plan
4. Stage 4：PM 裁決 → cold_audit_pm_final.md + TODO 更新
```

> 深挖方向（source-vs-runtime drift、authority chain、live boundary、tunable-vs-hardcoded、AI truthfulness、replay/demo evidence、GUI fake-success、test blind spots）已按 primary 軸拆進上面 focus；Source-vs-Runtime drift 的三端 SHA 底數由 Stage 0 提供，MIT 接力查 migration/DB，剩餘無主 drift 由 PA Stage 3 收口。

## 與「手動 prompt（PM 順序鏈）」的選擇

| 維度 | workflow（本 skill 跑） | 手動 prompt PM 順序鏈 |
|---|---|---|
| 廣度/並行 | 強（10 軸同時，分鐘級） | 弱（串行，慢） |
| 深度單軸 | 受限（每軸獨立 context 一輪） | 強（主會話可逐報告追問深挖） |
| 收斂質量 | Stage 3 仍需主會話接手 | PA 層原生在鏈內 |
| 可重複/結構化 | 強（schema 強制） | 弱（每次手寫） |
| context 壓力 | 低（fan-out 隔離） | 高（主會話扛全部，易 compact） |

**最佳實踐 = 混合**：workflow 跑 Stage 2 廣度 fan-out + 對抗複核（拿結構化 confirmed/disputed/assumptions），主會話接 Stage 3-4 深度收斂。本 skill 的五階段就是這個混合形態 — 不是二選一。

## 姊妹編排：盈利研判（profit-diagnosis）

`openclaw-full-audit` 找**問題**（工程質量：bug/合規/安全），對偶的 `profit-diagnosis` 找**錢**（盈利歸因 + 開發方向）。交易系統的研判需兩者並用——前者保系統不出事，後者保系統會賺錢。

`Workflow({ name: "profit-diagnosis", args: { baseline, scope, focus, priors } })` — read-only，三階段：
- **Evidence**：MIT/AI-E 共享取數（fills/edge/gate 拒單統計/dormant 清單/AI 成本 ROI/profit-first loop 候選與 order-fill proof 狀態）——共享一次取數防內視角 4 probe（EXT 不取 runtime）重複拉；死軸重派一輪
- **Probe**：QC/BB/MIT/AI-E 各域**守**（診斷現有錢漏 leak/凍 frozen/沒賺 unrealized，基於 runtime 證據；over-gate 雙向按淨貢獻計價）+**攻**（侵略性、跳出現有範式、最廣 scope 含非-Bybit IBKR lane；用各 lens 原生數學找結構性·機械性 edge——operator 6/14 鐵則）+**EXT 外部成熟經驗軸**（QC 擔任，必用 WebSearch/WebFetch：別人如何在同樣的牆——VIP0 無 rebate/小資本——前賺錢；schema 強制 sources[url+claim_quote 實開引句]+local_constraint_fit 映射回本地約束，防幻覺引用）；死軸/空手軸自動重派一輪
- **Map**：PA 綜合成 ROI 排序的開發機會地圖（defend/attack/unlock/learn 四分區、翻牆概率、證據等級、regime 標記、驗證路徑、owner）；覆蓋缺口（死軸/BLOCKED）顯式進 return，≠該域清白

鐵律：**姿態（operator 鐵則）：強硬堅強找出一切盈利可能——挫折第一反應=換思路+搜外部信息+學成熟經驗，不是放棄；空手紀律雙重強制——schema minItems:1（tool-call 層硬拒+重試，2026-07-09 smoke 實證）+ 代碼級後備（空手軸重派、二輪仍空進 coverage）+ 承重欄位 minLength 防樣板句，「本域無機會/現無廉價 lever/只能等」不可接受為最終答案，直接機會稀薄時以 unlock（前提解鎖監測）與 learn（外部經驗引入）補位——姿態強硬但證據誠實（FACT 須可重跑，Map 對擬入榜 FACT 抽跑核對）**。所有 edge 數字帶 runtime 證據不憑記憶；bull-only 標 regime-bet 且標記須傳遞到 top_moves；**conductor 每輪必以 `priors` 注入現行已判定裁決快照（主會話 memory 在手零過時；腳本內建 fallback 是 2026-07-09 快照）——已 NO-GO/KILL 方向無推翻證據不得重提，禁止重跑同一測試；但 NO-GO 是換思路的路標非終點，被鎖方向的前提（fee tier/資本/infra）是 operator 槓桿，監測解鎖是合法機會項**；attack 類 ASSUMPTION 機會先 leak-free 驗證（QC walk-forward / 歷史 kline backfill）才升格開發項，不直接投產；最快驗證路徑（flag-off/dormant 解凍，近零成本）優先於開發新東西；top_moves 候選優先送 profit-first loop 的 discover→admit 通道（spec `docs/agents/profit-first-autonomy-loop.md`），不與 standing loop 形成平行開發權威。

## 與常規鏈的關係

不替代日常 PM→PA→E1→E2→E4 鏈與順序派工。單點改動走 PM.md 派工模板 + 對抗驗證多視角化協議。本 workflow 是「全盤體檢」批量形態。
