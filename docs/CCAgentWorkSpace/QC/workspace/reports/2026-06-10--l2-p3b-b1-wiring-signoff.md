# QC B1 wiring sign-off — SANE（2026-06-10）

> PM 代持久化（QC Write disabled）。兩段式：QC 先出 BLOCKED-HANDOFF + 預註冊驗收帶（QC 無
> Bash，無法產 runtime 數字），E4 執行位按帶代跑，QC 按帶機械裁決。被驗 spec =
> `2026-06-09--l2-p3b-b1-altcap-spec.md`（B1 四常數正本）。

## 最終裁決：B1-wiring **SANE**

全部 13 項預註冊判準落帶、零 FATAL、零 DEFER 誤觸發。B1 wiring 鏈
（`load_factor_bundle` → `reindex_to_int_bar_index` → `beta_neutral_check`）接線正確。

## 交回數據（E4 執行位，Linux /tmp/wt-l2-owed-test @ fix/l2-owed，readonly session）

**Factor bundle**（window 2025-08-10..2026-06-01）：btc_bars=296（帶 [290,297]）｜alt_bars=295｜
corr(btc,alt)=0.8133（帶 [0.5,0.97]）｜down_bars=155 / span=286d（bear-heavy 方向一致）｜reasons=[]。

**候選 A 純噪音**（σ=0.3%、seed=20260610、key=bundle btc keys）：verdict=**pass**｜
β_btc=−0.00305 (SE 0.0129)｜β_alt=−0.00238｜β_down=−0.01433｜β_upper 全 <0.20
（0.0283/0.0185/0.0327）｜DW=2.107｜used_hac=False｜n_bars=295。

**候選 B BTC-clone**（y=r_btc+N(0,0.001²)）：verdict=**fail**｜**β_btc=0.99984∈[0.95,1.05]**
（共享索引對齊的銳利見證）｜β_alt=−0.00066（無交叉接線）｜β_down=1.00085｜reasons=
[beta_btc_above_threshold, beta_down_above_threshold, beta_btc_upper_above_cap,
beta_down_upper_above_cap]（精確對應、無多報漏報）。

**QC 帶外交叉復算（3 項全自洽）**：① upper bound 三條手算 bit 級吻合（β+1.96·SE 公式正確）；
② 跨候選 SE 比例 0.326≈σ 比 0.333（同一 (X'X)⁻¹ 縮放，回歸引擎內部一致）；③ 首跑超帶量
340−296=44≈45=buffer 天數（超帶根因診斷正確）。

## 執行期抓到並修復（隨 branch 走 E2 審）

1. 首跑 altcap producer `fe_sendauth`：harness 漏傳 dsn（adapter 本身支持注入，非 adapter bug）。
2. bundle btc_bars=340 超帶：45d mask buffer 漏入輸出 → `_clip_window` 修（`58192465`+`026dd75d`）
   ——mask 用 buffer 算（prior-only 回看保留，F5 正面）、returns/mask 輸出裁回 [ws,we]（量綱契約）。

## Caveats（QC 原文）

- `_clip_window` 與 harness dsn 修復是 production/harness 代碼變更，照常走 E2 review 隨分支收口，
  本裁決不替代代碼審。（已照辦：E2 narrow re-review 蓋 `58192465`/`026dd75d`/`2c5d6a62`。）
- 本裁決範圍 = **wiring sanity**（合成候選驗管道），不是 alpha 裁決——pass/fail 語義正確不蘊含
  任何真實候選有 edge；真實候選仍須走完整 B1+Q1+M3/M4 閘鏈。

## 過程記錄（BLOCKED-HANDOFF 階段的靜態 GREEN）

gate 端（main）與 06-09 APPROVE spec 零漂移：四常數 0.15/0.20/90d/180d-span/30 down-bars/N_oos 50
全對；雙因子強制、int-bar-index fail-loud 契約、down-mask leak-free（prior-only）、OLS/SE/HAC
（DW<1.5→Newey-West）全驗。F1-F8 findings 與預註冊帶全文見 QC agent 對話記錄
（PM session 2026-06-10）；F5（buffer≥30）答案=45d ✓、F7（零寫入）readonly session 硬化 ✓、
F8（iid DW≈2）=2.107 未觸發 ✓。
