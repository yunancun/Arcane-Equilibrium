# 條件式尾部錯位均值回歸篩查 — 證據報告（$0 唯讀 OFFLINE research，交 QC/MIT）

日期：2026-06-18 · 角色：E1 · 狀態：IMPL DONE，待 E2 審查
verdict 屬 QC/MIT；本檔只產出誠實證據，不下 go/no-go。

## 任務摘要
測本盈利弧從未跑過的反邏輯切法：掛 maker 限價 BUY @ `prior_close*(1-K)`（K∈{8,10,15,20}%），
只在當日 LOW<=該價成交（flash-crash），進場價=maker 價位（無 taker 成本），持有 N∈{1,2,3,5} 日
收盤平倉（+ target-vs-close 變體）。三 kill 硬打：alpha-vs-beta / falling-knife tail / capacity。

## 修改清單
- 新增 `helper_scripts/research/tail_dislocation_meanrev/screen.py`（READ-ONLY，~830 行）。
- 更新 `helper_scripts/SCRIPT_INDEX.md`（1 行條目）。
- 更新 `docs/CCAgentWorkSpace/E1/memory.md`（1 條近期記錄）。
- 0 production code / 0 PG 寫 / 0 migration / 0 auth/lease/risk 觸碰。
- artifact：`/tmp/openclaw/research/tail_dislocation_meanrev/tail_dislocation_screen_20260617T222026Z.json`（+sha256）。

## 治理對照
- R-0 隔離：set_session(readonly=True)，寫探針實證 fail-loud（ReadOnlySqlTransaction）。
- 只 SELECT market.klines（1d，唯一 CLEAN）+ market.funding_rates。
- net 禁 rebate；maker 進場 2bp + 退出 model 兩種（maker 2bp / taker 5.5bp）+ funding。
- Root Principle 5（survival > profit）= 本篩查的決定性 gate（見下）。

## 關鍵數字（Linux，2024-06..2026-06，26 大-cap，~2yr）

| cell | n | gross close | net maker | net taker | boot-t | alpha(t) | beta | CVaR5% | worst | maxDD(mk) |
|---|---|---|---|---|---|---|---|---|---|---|
| K8_N1 | 1519 | +1.06% | +1.02% | +0.99% | 5.9 | +1.09%(5.9) | 1.04 | −15.2% | −29.8% | 0.99 |
| K10_N3 | 819 | +3.40% | +3.36% | +3.32% | 8.4 | +2.88%(7.3) | 0.87 | −16.6% | −26.6% | 0.96 |
| K15_N3 | 247 | +6.66% | +6.63% | +6.59% | 8.8 | +5.47%(7.6) | 0.72 | −12.5% | −22.3% | 0.55 |
| K20_N3 | 96 | +13.35% | +13.31% | +13.27% | 13.1 | +11.29%(11.3) | 0.89 | −8.7% | −11.2% | 0.11 |

完整 16-cell 表見 artifact JSON `grid[]`。

## 三 KILL 結論

### kill #1 alpha-vs-beta — 罕見地 NOT 純 beta
- OLS（strat fwd ret ~ a + b·BTC fwd ret）：alpha 截距全顯著正（+1.1%~+11.3%，t 5.9~12.6），
  beta 多在 0.5~1.3。alpha 在 beta 中性化後存活 = 不是純 BTC-recovery 收割。
- up/down 鏡像：K8 在 BTC-down 子集確實轉負（−1.7%~−4.6%）→ 淺 K bounce 重度 beta-依賴；
  但 K15/K20 在 BTC-down 同窗仍正（+0.4%~+15%）→ 深 dislocation 是真 over-reaction reversal。
- PIT regime split（leak-free shift trailing BTC 趨勢）：edge 集中在 **down** regime（+3.4%~+17%），
  up regime 近零/負。beta-timing artifact 會集中在 up regime——此處相反 → 確證非 recovery-beta。

### kill #2 falling-knife tail — 致命（survival-violating）
- CVaR5% −10%~−22%；worst single −29%~−35%（FIL 2025-11、OP 2026-02 等接刀後續崩 17~27%，皆真實）。
- large-loss%（單筆<−10%）至 15%（N=5）。
- maxDD：all-in-sequential 0.96~1.0；**即使 daily-equal-weight 分散同日 fill 仍 0.77（K10/N3）**。
- 最致命：worst crash 日 **26 個 symbol 全部同時 fill（max 並發=26）= 零分散**——尾部完全相關，
  正是最需要分散時全給回去。對小帳戶=帳戶炸毀 → 違 Root Principle 5。

### kill #3 capacity/rarity
- 事件/年：K8 752、K10 406、K15 122、K20 47。深 K（高 alpha）= 稀有尾部 = 低容量。
- 同日並發 fill 中位數 3、≥10 fills 的日子 34 天 → 容量受同日相關性限制。

## 資料品質 / SURVIVORSHIP（誠實揭露）
- 26 symbol，全 730 bar、0 missing-day gap、0 non-positive price、0 zero-turnover。
- **無真下市/歸零事件落在窗內**：我的 >7d-gap 偵測器把 06-01 ingest cohort 誤標 possibly_delisted=true
  （false-positive，實際全活，只是兩個 ingest 批次截止日不同）。
- **結構性 survivor bias**：此 universe 全是存活兩年的大-cap → bounce 必然偏樂觀。真實情境下接刀接到
  下市/歸零資產（如歷史 LUNA/FTX 類）會是 −100%，本窗無此事件 → **真 verdict 偏更糟，不是更好**。
- funding 僅 ~1-2% 事件覆蓋（多數歷史窗早於 funding 資料 2026-04）；avg funding 微負（long 收）→
  省略略偏 conservative-favorable，已誠實標。

## leak-free 確認
- 進場 level = t-1 已知 prior_close 預設常數；fill 條件 = 當日 low（同日實現，非反推進場價）；
  exit = t+N 收盤（被量測 target）。
- naive 污染對照（用同日 low 當進場價=前視）膨脹 +6.5%(K8)~+44%(K20)，PIT 版避開 = 證乾淨。

## 不確定之處
- alpha 截距真實性受 survivor bias 上偏影響——QC 須在含真下市/歸零資產的更廣 universe 重驗。
- maxDD 等權模型仍是悲觀界（all-in 每事件）；真實 position sizing（3% risk/trade）下尾部仍相關但幅度待 QC 精算。
- target-vs-close 變體未顯著優於 close 退出（target_hit 23~52%）。

## preliminary lean
**LEANS_SURVIVAL_FAIL** — alpha 罕見地是真的（beta 中性後存活、集中 down regime、net 遠超 4bp 牆），
但 falling-knife 相關尾部（CVaR/worst/maxDD/26-symbol 同日全 fill）+ survivor-biased universe
使其在 Root Principle 5 下不可接受。決定性 verdict 屬 QC/MIT。

## Operator 下一步
1. E2 審查本 read-only 研究（chain：E1→E2→E4）。
2. QC/MIT：在含真下市/歸零資產的更廣 universe 重驗 alpha 真實性 + 精算 position-sized 尾部。
3. 若 QC 認 alpha 值得，唯一 survival-safe 形態需加：per-trade hard stop（接刀續崩斬倉）+ 同日並發上限
   + 排除 illiquid/high-delisting-risk symbol——但這會吃掉大部分 alpha，須 QC 量化權衡。
