# GUI 大改 P0.2 批次 8a — demo inline style 清理

> **記錄狀態**:batch 8(demo/live,交易關鍵)拆 8a-demo[本檔]/8b-live。E1a agent 完成清理
> 但因 harness「不寫 report .md」指令未落報告檔(同 7b);本報告由主會話(PM)依 E1a 內聯
> 自報 + E2 對抗審查 + PM 本地驗證重建。2026-07-10。規格 `docs/execution_plan/gui_redesign/design/05_utilities.md`。

## 一、度量
| 檔 | 前 | 後 |
|---|---|---|
| tab-demo.html | 51 | **0** |

只載 common*.js 自成一體;零新 utility(oc-utilities.css byte-identical,§4 未動,spec-drift 免);11 頁組件入 tab-demo body `<style>`(語義 token)。

## 二、硬邊界(demo=LiveDemo,live-grade 控制流)——零非樣式改動(E2 親算 HEAD↔working)
| 軸 | HEAD | working | 判定 |
|---|---|---|---|
| onclick 集合 | 21 | 21 | IDENTICAL |
| endpoint/path 字面 | 9 | 9 | IDENTICAL |
| openConfirmModal / classifyLiveMutation / ocResidualRiskBanner / ocToast | 3/3/1/8 | 相同 | IDENTICAL |
| ocEsc(XSS 逸出) | 29 | 29 | IDENTICAL |

`\bconfirm\b` 3→5 漂移=假陽性(新 CSS class 名 `demo-cta-confirm` 非執行碼;真 confirm 註釋逐字同)。五閘/授權/TTL/typed-confirm/全平 fail-closed 邏輯與確認文案(「確認關閉所有 Demo 倉位」「使用虛擬資金,不影響真實帳戶」)verbatim。

## 三、E2 對抗審查(a8c318fb,PASS to E4,0 blocking,3 INFO)
- 鐵則一:`.style.display` 14→6,轉走 8 個全 classList;殘 6=banner(未掛 utility,display+className 全 JS 驅動)+demoDustFooter(per-axis:display 留 JS,只 color/font/margin→class,無 display utility 故 !important 不壓);oc-btn--xs 不設 border/bg/color 不撞 range-btn active JS 寫。
- 鐵則二:16 處 className-wipe 目標全屬未觸碰元素或走 #id 選擇器(#demo-session-badge/#demo-close-all-summary);無 utility 掛 wipe 元素。
- §6 引理:.oc-demo-source-bar/.demo-cta-overlay display:flex 存在,.hidden !important 勝;6 處 toggle 等價。
- 裸屬性(7a HIGH)=0;double class=0;讀值陷阱 N/A(全寫無 === 讀)。
- canon 6/9:demo 無 --live 熱紅;全平確認框琥珀 #eab308 verbatim(虛擬資金警示,canon 6 真金不適用),無第四紅。
- INFO:①--card-bg→--bg-surface/--text-dim→--text-secondary=別名值恆等零視覺差;②demo-risk-btn 文字 --blue→--text-secondary(§5.5 中性化,真視覺變更,邊框藍 tint verbatim,交 PA/A3);③radius 10→8/6→5、weight 700→600、10→11px=§5 收斂微變。

## 四、驗證(PM 本地全綠)
node --check inline 2/0;tag 平衡;三連 link 未擾;oc-utilities.css byte-identical;回歸 structure/+G0.5 = **392 passed / 5 failed**(5F pre-existing);零 Python/Rust。

## 五、A3 必審 / 待辦
①demo-risk-btn 藍→灰雙主題觀感;②全平框琥珀 #eab308 vs --warn #d29922 P0.4 收斂;③fs-micro 令 10/11px 徽章微升;④§6 explicit-flex→引理兩態 E4 Linux 渲染實跑;⑤**8b-live 待做**(tab-live.html 68/tab-live.js 39=107,最高風險 REAL FUNDS/--live)。
