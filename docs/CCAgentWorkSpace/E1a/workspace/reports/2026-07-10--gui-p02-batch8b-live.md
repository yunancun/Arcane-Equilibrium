# GUI 大改 P0.2 批次 8b — live inline style 清理(P0.2 最高風險子批,REAL FUNDS 真金面)

> **記錄狀態**:batch 8 拆 8a-demo[已完成 `b1e8ad4a6`]/8b-live[本檔]。E1a agent 完成清理但因
> harness「不寫 report .md」指令未落報告檔(同 7b/8a);本報告由主會話(PM)依 E1a 內聯自報
> + E2 對抗審查 + PM 本地驗證重建。2026-07-10。規格 `docs/execution_plan/gui_redesign/design/05_utilities.md`。

## 一、度量
| 檔 | 前 | 後 |
|---|---|---|
| tab-live.html | 68 | **0** |
| tab-live.js | 39 | **0** |

tab-live.js 1886→**1882** 行(<2000 硬頂);零新 utility(oc-utilities.css byte-identical,§4 未動);9 頁組件入 tab-live.html `<style>`(語義 token)。

## 二、硬邊界(REAL FUNDS 真金面)——零非樣式改動(E2 親算 HEAD↔working)
| 軸 | HEAD | working |
|---|---|---|
| onclick / endpoint 集合(sorted diff) | — | 空=IDENTICAL |
| openTypedConfirmModal(html/js) | 1/6 | 1/6 |
| classifyLiveMutation / openConfirmModal | 7/2 | 7/2 |
| doEmergencyStop / doLiveStop / doLiveCloseAll | 1/1/3 | 1/1/3 |
| closeLivePosition / liveStart / ocPost / ocToast | 12/1/6/11 | 同 |
| ocEsc(XSS) | 72 | 72 |
| live_reserved / authorization.json / execution_authority | 1/2/8 | 同 |
| typed-confirm phrase + 全 modal 文案(impact/rollback/confirmLabel) | — | byte-IDENTICAL |

淨 −4 行=恰好 4 個冗餘 `epBadge/cBadge.style.display=''` 純刪(className swap 已清 hidden)。五閘/授權/TTL/typed-confirm/緊急停止/平倉分離/確認流邏輯與文案零觸碰。

## 三、canon 6 熱紅(真金永不稀釋)——逐點 HEAD=WORKING
`rgba(239,68,68)` html 9=9(全在**未觸碰** `<style>` 塊:.btn-emergency/.live-mode-mainnet/.real-funds-badge/.trust-bar.crit)、`#ef4444` 0=0、`var(--live)` 0=0、`REAL FUNDS` html 4/js 3 全等、real-funds-badge/live-demo-badge 全等;前存 `<style>` 塊(20-244)byte-IDENTICAL(僅檔尾追加)。**熱紅構造性保全**(只動 inline style=);--live 與 --neg 未互換,無第四紅。canon 9:虧損紅 #f87171→--neg(=--red,**非 --live**,§5.5 收斂正確)。

## 四、E2 對抗審查(a27741b88,PASS to E4,0 blocking,3 INFO)
- 讀值陷阱 PASS:toggleFills 舊 `section.style.display!=='none'`→新 `!classList.contains('hidden')`,truth-table 兩態等價無反向,全檔僅此一 reader。
- 鐵則一精準:§6 三顯式值分支查目標 class CSS display 證安全(.trust-bar flex/.integrity-fail-view div-block/.live-dashboard block==舊值);_applyToBar 寫 tier-badge/expires/signed 色→不掛色 utility,clean-days 只 textContent→掛 t-dim(對稱精準);liveDustFooter per-axis(display 留 JS)。
- 鐵則二:epBadge/cBadge className swap 天然清 hidden;global-mode-control-note classList.toggle 無 wipe。
- 裸屬性 0;double class 0;oc-btn--xs 已存(零新 utility);node --check PASS;js 1882<2000。
- INFO(無返工):①btn-live-stop 不加 fw-semi 正確(.oc-btn-critical 供 700,加反 regression);②.live-table m-0==舊 margin-bottom:0;③色/尺寸收斂全 §5 sanctioned。

## 五、驗證(PM 本地全綠)
node --check tab-live.js + tab-live inline PASS;兩檔 style=0;oc-utilities byte-identical;回歸 structure/+G0.5 = **392 passed / 5 failed**(5F pre-existing);零 Python/Rust。

## 六、A3 必審 / 待辦
①start/風控鈕 700→600(stop 保 700 層級 OK);②虧損紅 #f87171→--neg 貫穿 positions/orders/fills;③#21262d→--border-subtle + 深底 rgba/銀灰 verbatim 混態待 P0.4 整面板重主題;④authority 紫 verbatim P0.4 非 --seal;⑤§6 引理+讀值陷阱修 E4 Linux 真渲染兩態實跑(integrity 切換/fills 折疊/ep·c badge);⑥integrity-fail 按鈕列 block→flex row 佈局機制變視覺等價。

## 七、P0.2 完結
8b 完成後 P0.2 八批全清(1,469→全站剩 63=待完結審計:app-learning.js 孤兒 defer + §7 合法 scoped-var + 批次計劃外檔待確認)。
