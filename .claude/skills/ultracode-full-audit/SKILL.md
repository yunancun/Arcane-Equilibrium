---
name: ultracode-full-audit
description: OpenClaw 全盤多視角審計編排設置（主會話/conductor 專用，非 subagent skill）。當 operator 啟用 ultracode 並要求「全盤審查/全面檢查/multi-agent 優化/冷酷對抗審計」時使用：主會話親做 Stage 0 凍結與 Stage 3-4 收斂，並行審計段（Stage 2）以 Workflow 調用 saved script openclaw-full-audit。未啟用 ultracode 時降級為 PM 順序鏈或先徵求 operator 同意。
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
腳本做：10 軸並行 fan-out（read-only 邊界 + 本輪 focus 注入；FACT/INFERENCE/ASSUMPTION 三分；無證據改列 assumptions）→ C/H 對抗複核（證據鏈 ∥ 影響復現雙質疑者，全反駁=剔除、單反駁=標 disputed）。返回 confirmed / disputed / medium_low_info / assumptions。

### Stage 3 — PA 驗真層（主會話接手，workflow 不固化此段）
拿 workflow 返回後，主會話親做或派 PA：
- 對 confirmed 去重、合併（同 file:line 跨軸重複歸一）、按 P0-P3 分級
- 對 disputed + assumptions 做 targeted re-probe（按 PM.md 多視角協議：獨立命中=置信升級；分歧=標明交 operator，不擇一抹平）
- 生成 validated fix plan：confirmed-only / rejected-unproven / 重複合併表 / 每項 path+line / fix owner / verifier / 可並行章節 / 必序列化章節 / session 拆分建議（避 compact）/ 每修復包檔案範圍+測試+驗收 / 需 operator 決策項 / 需 Linux read-only 證據項 / 未批准前嚴禁動手項
- → `PA/workspace/reports/{AUDIT_DATE}--cold_audit_validated_fix_plan.md`

### Stage 4 — PM 最終裁決（主會話）
讀 PA plan 終審：是否違 16 原則 / 合 dispatch protocol / runtime-docs drift / 需 operator 先決策 / 未證實猜測誤入。
- → `PM/workspace/reports/{AUDIT_DATE}--cold_audit_pm_final.md`（遵 CLAUDE.md docs 放置規則，不放 repo 根目錄）
- 只把已確認、可執行、需追蹤項更新進 TODO.md（連結報告非貼全文）；未證實猜測留 PA 報告附錄「待證假設」，不入 TODO

## args（全部可選）

| 參數 | 默認 | 說明 |
|---|---|---|
| `baseline` | null | Stage 0 凍結摘要（三端 SHA / dirty / BASELINE 行）；注入每軸對齊 affected line。未傳會 log 警告 |
| `scope` | srv/ 全倉 | 審計範圍描述 |
| `axes` | 10 軸 CC/FA/E3/BB/QC/MIT/AI-E/E5/A3/R4 | 審計軸=agent 名；全鏈深審加 `"E4"`（測試矩陣審計）`"TW"`（文檔盤點） |
| `focus` | null | 本輪靶向必查項。字串=注入全軸；`{CC:"...", E3:"..."}`=按軸注入。**非範圍上限**，role SOP 全量仍是基準 |
| `fix` | false | **默認 report-only**；true 時對 confirmed C/H 派 E1 worktree 修復 + E2 複審 + E4 回歸 |
| `max_fixes` | 5 | fix 模式單輪修復上限，餘量留報告 |

## 嚴重度映射

腳本用 CRITICAL/HIGH/MEDIUM/LOW/INFO；對應治理慣用 P0/P1/P2/P3：CRITICAL=P0、HIGH=P1、MEDIUM=P2、LOW+INFO=P3。PA/PM 報告用 P 級表述，與 finding 嚴重度一一對應。

## 標準調用劇本（冷酷對抗全程序鏈審計）

```
1. Stage 0：主會話凍結三端 SHA + dirty + BASELINE → 寫 baseline 報告
2. Stage 2（含 Stage 1 R4/TW）：
   Workflow({ name: "openclaw-full-audit", args: {
     baseline: "<Stage0 凍結摘要>",
     axes: ["CC","FA","E3","BB","QC","MIT","AI-E","E4","E5","A3","R4","TW"],
     focus: {  // 本輪靶向（深挖方向），按軸；不是範圍上限
       FA:  "authority chain lineage 完整性（StrategySignal→…→ExecutionReport 缺失 report）；GUI 聲稱成功 vs Rust authority 實態",
       E3:  "live/live_demo 五 gate 可繞性（live_reserved/operator role/OPENCLAW_ALLOW_MAINNET/secret slot/authorization.json）",
       QC:  "策略參數/風控閾值 tunable vs hardcoded；replay 誤用為 promotion evidence；Stage 0R/Stage 1 Demo 邊界污染",
       MIT: "migration metadata vs 實際 DB object 一致性（ssh read-only）；ML 階段 shadow/advisory/demo/live-blocked 明確定位",
       AI-E:"should_call_ai=true 未調用 / 偽 AI / fallback 不誠實 / 成本不落 ledger / tier-routing 與實際不一致",
       A3:  "fake-success：按了只改前端 state / Python API 回成功但 Rust authority 未變 / 顯示 live-ready 但 gate blocked",
       E4:  "測試盲區：fail-closed / timeout / Bybit retCode / concurrency / stale data / auth expiry / replay-promotion 邊界",
       BB:  "Bybit 限額類參數 hardcoded vs 應 config",
       E5:  "代碼級死代碼（重複邏輯/未引用 helper）— 與 FA 功能級死代碼切割"
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

## 與常規鏈的關係

不替代日常 PM→PA→E1→E2→E4 鏈與順序派工。單點改動走 PM.md 派工模板 + 對抗驗證多視角化協議。本 workflow 是「全盤體檢」批量形態。
