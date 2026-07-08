---
name: project_2026_06_01_fail_closed_gate_stack_root_cause
description: 2026-06-01 代碼審計找到 6 個 fail-closed gate（程式層真實但多為次要/潛伏）；但 Phase-1 Linux runtime 查驗【推翻】了「gate 棘輪是主因」的結論——cost_gate 零誤殺正確阻擋真負 edge，真問題回到「為何已實現 edge 普遍為負」(a 無alpha/b exit-drag/c 成本)
metadata: 
  node_type: memory
  type: project
  originSessionId: 07386332-55ba-43c0-a468-02f0f16dd863
---

## 耐久結論（runtime 查驗凌駕代碼審計）

2026-06-01 operator 要嚴審「6 週無 net-positive edge 的程序層根因」。主會話代碼審計（+9 對抗 sub-agent）找到 6 個 fail-closed gate，初判「gate 棘輪自我收緊是主因」。**Linux runtime 只讀查驗大幅推翻此排序**：
- cost_gate 14d 拒 90.5%，但被拒 estimate **100% 真負**（avg −13bps）、**0 筆正-edge 誤殺**（主會話親驗 SQL）→ 正確阻擋真負 edge，非錯殺好交易。
- H0 freshness 81M+41M checks **0 blocked**；驗證歸零（root#1）live 殺傷≈0（潛伏非主兇）。
- 真問題回到「為何幾乎每 cell 已實現 edge 都負」：(a) 入場無 alpha /(b) 有 alpha 被 exit policy 摧毀 /(c) 成本牆。

**收斂定案（QC 獨立驗 + PM 補查）**：扣 beta 後 grid 純 alpha ~+5-6bps@4h < 成本 15bps 且分週不穩（跌週賺漲週賠＝short-beta 偽裝非擇時）；ma KAMA×SMA20 在 1m 嚴重滯後＝信號本身負期望；唯 bb_reversion@mean_reverting 兩 OOS 半都正但 n=27 太薄。cost_gate 正確；4 個 bounded bug（bb_breakout OI gate / qty_zero 精度 / regime 接線 / root#1 歸零）是 hygiene 非 alpha 來源。兩個 regime「修復」（A-3a 死 schema 欄 / A-3b vocab mismatch）嚴查下證偽蒸發——教訓：孤立看 regime_multipliers 會誤判，須追 `derive_regime` 翻譯層。

**部署**：4 hygiene fix 全鏈綠（E2 4/4 APPROVE → MIT leak-free → E4 regression）後部署 `324001c3`（僅 code 檔），Linux atomic rebuild+restart，運行引擎 SHA == post-build SHA 親驗（DEPLOY-ATOMIC-VERIFIED）。誠實預期（已兌現）：此批＝hygiene + 啟動 bb_reversion 累積，本身不產生 alpha。

**元教訓（最耐久）**：代碼審計階段易把 gate stack 過度歸因為主因；runtime 查驗擋下此排序錯——這正是「先真實查驗再修」的價值。MIT 警告：別放鬆 cost_gate（放鬆只放出已知虧損單）、別把 grid 改長持有（regime-bet 陷阱）。

## 演變軌跡 / point-in-time 框定
- 「現有樣本無穩健 alpha / 搜索空間貧乏」是 **2026-06-01 當時 57 天 bursty 樣本**的觀察，非永久結論；此後資料大幅累積，且專案已於 2026-07-05+ 轉為 active profit-first 自主循環 + AI/ML roadmap（WP1-WP7）。「無 alpha / 搜索窮盡」框定應視為當時點狀態。
- 原始代碼審計 6-gate 推論全文（元根因「無 exploration floor」+ 6 機制 file:line + 證偽清單）已被上方 runtime 修正部分推翻，不再全文保留；追溯見本 session transcript 及 commit `324001c3` 前後 diff。

---

## [index-archive 2026-06-10] 原 MEMORY.md 索引條目全文(壓縮索引前歸檔,內容為當時點狀態)

- [6 週無 edge 根因調查 (2026-06-01) — Phase-1 runtime 推翻 gate-棘輪論](project_2026_06_01_fail_closed_gate_stack_root_cause.md) — 代碼審計找 6 個 fail-closed gate，但 **Linux runtime 查驗推翻「gate 棘輪是主因」**：cost_gate 14d 拒 90.5% 但被拒 estimate 100% 真負(avg −13bps)、0 誤殺正 edge（主會話親驗 SQL）→ 正確阻擋非錯殺；H0 81M+41M checks 0 blocked（root#2/#6b 部分證偽）；驗證歸零 root#1 殺傷≈0（潛伏）；真問題回到「為何已實現 edge 普遍負」= (a)無入場alpha/(b)exit-policy 摧毀真alpha(cut-winners/let-losers + regime_multipliers H2)/(c)成本，operator 拍板 QC 先做樞紐診斷再設計；bounded 真 bug：bb_breakout OI gate(14d僅2單)/qty_zero BTCUSDT 精度(13.9萬噪音 reject)/regime_1h 100%空+key mismatch；證偽手續費重複計數/信號反向/回測高估；**教訓：代碼審計易過度歸因 gate，runtime 查驗擋下排序錯**
</content>
</invoke>
