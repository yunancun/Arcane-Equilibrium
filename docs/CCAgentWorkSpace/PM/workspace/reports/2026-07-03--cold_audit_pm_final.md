# 2026-07-03 冷酷對抗審計 — Stage 4 PM Final(終審裁決)

> 鏈:[baseline](2026-07-03--cold_audit_baseline.md) → Stage 2 `wf_6dc68c2f-4a0`(10 軸/143 findings/7.475M tokens)→ [PA validated fix plan](../../../PA/workspace/reports/2026-07-03--cold_audit_validated_fix_plan.md) → 本檔。
> 本輪降級聲明(args 注入失誤 + spend limit 截斷 Verify 尾段 + E4/TW 缺席)見 PA plan §0,不重複;結論以「已親證 FACT」為錨,quorum-missing 不入隊列。

## 1. 終審裁決

**核心圖景(一句話)**:系統的 live 安全邊界本輪未見可繞行缺陷(E3 軸全票複核零 C/H confirmed),但**學習/證據/監測產線自 06-24~06-30 起系統性停擺**——crontab 置換殺監測、over-gate 凍 probe、運行棧滯留 06-30 世代、SSOT 坐在 /tmp——「有限自我進化」四性質支柱目前是斷的,而且斷得無人知曉(監測自盲)。

- **16 原則對照**:P0-1(執行身份不可指認)觸原則 1/8;P0-3(/tmp SSOT)觸原則 8 與審計支柱;P1-1 over-gate 複合體觸原則 11/12(agent 獲授權卻被自家 gate 凍結,行為無法從證據演化);cost_edge dormant 觸原則 13。**live fail-closed 5 gates 與 9 不變量:未動、不動、本輪亦無任何修復項要求鬆動。**
- **dispatch protocol 合規**:fix plan owner 鏈全部走 PM→PA→E1→E2→E4 或對應審計鏈;高風險項(D1-D8)已隔離為 operator 先決,未批不動——符合。
- **runtime-docs drift**:TODO §0 runtime 事實已證 stale(CC);本檔與 fix plan 即為新證據面,TODO 更新只掛鏈接。
- **未證實猜測攔截**:10 條 quorum-missing disputed、93 條 assumptions、seam #2/#7 全部擋在 TODO 之外,留 PA plan 附錄。

## 2. ROI 對照 profit-diagnosis(2026-06-13)+ opportunity-cost

06-13 結論「搜索空間窮盡、剩 operator-hand」在本輪被**加上前置條件**:當前 fills/probe/監測產線停擺下,一切 alpha 判定與負向 PASS 都有 vacuous 風險(seam #7)。**修產線先於找 alpha**——這是本輪對開發順位的唯一裁決。

近零成本 defend 槓桿(未排入即為機會成本):
1. cron 三條快恢復(哨兵/healthcheck/watchdog)——監測復明,P0-2 內。
2. PG 調參(128MB→4-8GB)——一次動作救 MLDE lane + 全庫查詢,P1-5。
3. rpiTakerAccess(BB 三輪重申、已裁安全)——maker 執行成本改善,唯一正向 edge 機會項。
4. cost_edge demo advisory 腿 arm + event-store env var——原則 13 治理閉環,P2-2/3。

## 3. Audit Retro(審計迴圈自我進化)

**上輪(2026-06-14)open 項覆核**:
- AUTH-1 → 維持 RESOLVED,本輪 E3 無新繞行(全票複核)。
- PROFIT-1 → **哨兵鏈已雙重死亡**:追蹤 row 被 v530 刪(已知)+ 哨兵 [90] 宿主 passive_wait_healthcheck 於 06-27 被 crontab 置換殺死(本輪新證)。「WARN→啟 QC 方案 A」通路現實上不存在;隨 P0-2 恢復 healthcheck 後需重掛。
- SCHEMA-1 → contract test 已閉,但 06-30 cutover 使覆蓋面過期(seam #12→P1-8),v739 前必補。

**本輪 defect_type=other 清單(分類法演化候選)**:crontab 置換、runtime git reset、running-process-vs-source 滯留——共同形態是「**runtime mutation 無治理**」;建議新增 defect_type `runtime-mutation-ungoverned`。rpiTakerAccess 類建議 `opportunity-unclaimed`(正淨貢獻未取,與缺陷雙向對稱)。

**下輪 focus 建議**:①E4/TW 補審(本輪零覆蓋);②spend limit 解除後 resume `wf_6dc68c2f-4a0` 補 30 張質疑票;③seam #2(GUI↔engine↔TOML 三方對表,依賴 P0-1 重啟後才有意義);④v739 流量恢復後重測全部 vacuous PASS(BB rate/QC 黑名單/E3 負向);⑤memory 索引 vs 實檔 lineage(AI-E 幽靈報告類)。

## 4. TODO 更新記錄

進 TODO §1 四行(只掛鏈接不貼全文):`P0-RUNTIME-EXECUTION-IDENTITY`、`P0-CRON-MASSACRE-RECOVERY`、`P0-SSOT-VOLATILE-TMP`、`P1-COLD-AUDIT-2026-07-03-BATCH`(P1-1..P1-9 傘形,錨 PA plan)。operator 決策 D1-D8 隨傘形行帶出。P2/P3 不入 TODO,留 PA plan 為隊列正本。

---

# v2 簽收(2026-07-04 證據面補全後)

## 完整性判定:審計閉環達成

1. **12/12 軸報告齊全**:10 軸主輪(7 報告檔+E3 memory 形態+A3/R4 conductor 代落盤)+ E4/TW 補審報告檔(07-04)。
2. **對抗複核 quorum 全票**:resume 補 30 張缺票,disputed 18→1;E4/TW 7 confirmed 全票零 disputed。唯一殘留 disputed(cost_edge 原則13 解讀)已隔離為 operator 決策項 D5,事實面親證無爭議。
3. **PA 修復工程日誌 + FA 報告 → PM 簽收 → TODO 鏈**:FA `2026-07-03--full_repo_functional_audit.md` / PA plan(含 Addendum v2)/ 本檔;TODO §1 掛 P0×3 + P1 傘形。**全程 report-only,零業務代碼修復動作**(唯二觸碼:workflow 腳本 args guard 根修 + A3/R4 報告代落盤,均為審計工具鏈/文書,非業務面)。

## 重要修正錄(v1→v2)

- **P0-1 事實修正**:引擎進程存在(`openclaw-engine` 連字號名,PID 2368227,36% CPU/2.5GB RSS),07-03 03:02 重啟(=CC 所報無紀錄 runtime mutation)但**未 rebuild**,binary=06-29 build。P0-1 定性從「身份不可指認」修正為「世代失控+重啟不 rebuild+無 build-SHA 可觀測面」,嚴重度不變(仍 P0,原則 8 與 v739 有效性直接受制)。conductor 取證雙失誤(底線/連字號命名 + head 截斷)記入教訓。
- **P1-8 由推定升實錘**:E4 證跨語言契約零 golden-vector parity + runtime 雙 plan 檔分裂 + 證據鏈斷點(candidate_matched_demo_fills 無 producer)。
- 新增 P1-10(probe_ledger 472MB 無界+全量重讀)/ P1-11(1m 指標每 tick 重算);P0-2 補 F12(兩 cron log 0-byte);D9(ledger rotation 策略)。

## 實耗總帳與審計 ROI

三輪 workflow 合計 **11.23M subagent tokens / 220 agents**(主輪 7.475M+resume 2.082M+補審 1.673M)+ 主會話取證與收斂。產出:P0×3、P1×11、P2×15、P3 批,其中 runtime 產線停擺群(P0 全部+P1-1/4/8/10)在 v739 前不修則 Demo 自主迴圈的一切學習證據繼續為零——本輪審計的直接盈利路徑貢獻即在此。

## 下輪 focus(承 v1 retro,更新)

①v739 流量恢復後重測 vacuous PASS 全集;②seam #2 三方對表(依賴 D1 重啟後);③P2-4/5/6/9 四條定向 re-probe;④TW 揭示的 Codex 注釋治理欠帳盤點是否擴大;⑤audit workflow 自身:args guard 已修,建議 saved script 增加「args 未解析出物件時 log 警告並中止」硬化(本輪為 fail-soft 到默認)。
