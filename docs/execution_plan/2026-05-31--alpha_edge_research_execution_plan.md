# Alpha-Edge Research Execution Plan — Cost-Wall-Escape Program

| 項目 | 內容 |
|------|------|
| Date | 2026-05-31 |
| Author | PA (Project Architect) |
| Status | **PA DESIGN — awaiting PM 2nd sign-off**（PM 1st sign-off 已收 QC 解決方案研究提議 + 3 條強調）|
| Ticket family | `ALPHA-EDGE-*`（program-level；本計劃定義 4 track + wave/session 拆分）|
| 改動風險 | 計劃本身=文檔（低）；下轄 session 含 **高**（collector listing-capture Rust + WS 訂閱面、M7 V116 schema/detector）與 **中**（backfill 腳本、回測 harness）；硬邊界 **0 觸碰**（全 read-only research + capture-only 旁路）|
| Upstream evidence | `docs/audits/2026-05-31--p0_edge_cost_wall_investigation.md`（PM 全 session findings 匯報）；3 E1-ready spec（§6 整合表）；戰略決策 `TODO.md` v92（commit `3a7c4853`）|
| Scope 紅線 | 本檔=**dispatch packet 設計**，不寫 feature code / 不執行回填 / 不改 TODO（PM 整合）。產出 owner-chain + acceptance + 並行圖 + gate 表 + 既有資產整合位置 + NOW-dispatch session。|

---

## 0. PM 2nd sign-off 該檢查的 5 條（最 load-bearing）

> 這 5 條是本計劃最容易出錯、最影響後續 dispatch 正確性的判斷。PM 2 簽前逐條核。

1. **【survivorship 硬修，PM 1-簽強調 #1 已落地為 day-1 acceptance】** S1-W1-S1（backfill 前置）的 acceptance **明定**「symbol 清單 = `market.symbol_universe_snapshots` 歷史全集（含 `is_delisted_at_asof=true` / `status IN ('Delivering','Closed')`）∪ 當前 scanner universe ∪ Bybit 全 linear instrument 歷史」，**不是** backfill spec 原稿的「live scanner universe（survivor-only）」。**理由（PA 已 grep 自證）**：`market.symbol_universe_snapshots`（V058:31-50）已含 `status / listed_at / delisted_at / is_delisted_at_asof` 欄位，cron `DEFAULT_INSTRUMENT_STATUSES=("Trading","PreLaunch","Delivering","Closed")`（`ref21_backfill_v058_v059.py:32`）已採集 delisted——**delisted SoT 已存在於 DB**，backfill spec §2「Symbol source = live scanner universe」會引入致命倖存者偏差（Track 1 唯一致命污染源）。本計劃**覆蓋** backfill spec §2 的 symbol source，並要求 backfill spec 更新（§6 標 cleanup）。**PM 須確認此覆蓋已反映在 S1-W1-S1 acceptance（AC-S1-W1-S1.3）**。

2. **【執行可達性先於 demo 週期，PM 1-簽強調 #2 已落地為 kill-gate 排序】** Track 2 拆成 **Gate-A（NOW 可做，maker-fill feasibility 預研，kill-gate）** 與 **Gate-B（Q4，collector 改動 + 累積）** 兩段，且 **Gate-A 是 Gate-B 的硬前置**——Gate-A maker-fill<30% 直接殺 Track 2，省下 collector 改動（高風險 Rust + WS 訂閱面）+ 5-6mo 累積。collector listing-capture spec（PA 已寫）的 IMPL **不在 NOW**，只在 Gate-A PASS 後才解凍。**PM 須確認 Gate-A 排在 collector IMPL 之前**（A2 教訓：可達性是 kill-gate 不是事後驗）。

3. **【leak-free shift(1) 是所有回測 session 的 day-1 acceptance，PM 1-簽強調 #3】** 每一個含回測/sweep 的 session（S1-W2-S1/S2、Track 3、Track 4）acceptance **第一條**都是「leak-free shift(1) 並列對照 + look-ahead 指紋 grep（`rolling(N).max/min` 含 current bar 必並列 `shift(1)` 對照）」，**未附即 session FAIL**。**理由**：成本牆把 edge 壓到 1-3bps（findings §2.1），任何 look-ahead 都偽造 edge（memory `feedback_indicator_lookahead_bias`）。**PM 須確認沒有任何回測 session 的 acceptance 缺這一條**。

4. **【並行 ceiling = 7，且 NOW 只有 3 並行】** 並行圖（§3）NOW（週 0-2）只有 **3 個並行 session**（S1-W1-S1 backfill 前置 / S2-W0-S1 Gate-A feasibility / S4-W0-S1 bull-regime 回填）+ review 角色按需附掛，**遠在 7 ceiling 內**。memory 教訓（`project_2026_05_03_ref20_sprint1_2_closure`）：PM autonomous 曾跑 9-wave 跳 E2/E4 = 被點名反模式。本計劃**任何 wave 並行 session 數 ≤7**，且高風險 IMPL session 強制走 A3+E2 對抗核驗（memory `feedback_impl_done_adversarial_review`）。**PM 須確認沒有任何 wave 同時開 >7 session**。

5. **【retention BLOCKER 卡在 backfill 執行之前，不是事後】** S1-W1-S1（retention 決策 + window/symbol sign-off）是 **operator hand-action gate**，且 **硬卡** S1-W1-S2（執行回填）之前。`market.klines` retention `drop_after=365d` daily（backfill spec §1.4 FACT），>12mo 不延長 retention 會在 24h 內被 reap（載入即刪）。**PM 須確認 dispatch S1-W1-S2 前 operator 已拍 retention（1095d for 18mo / 400d for 12mo）+ window + symbol breadth**——這是 operator 決策 gate，不可由 sub-agent 代。

---

## 1. Taxonomy 定義（本計劃的 Sprint / Wave / Session）

> 對齊專案既有用法（Sprint 1/2/3/4；W1-W9 wave；dispatch unit）。本計劃為**研究型 program**（非單一功能 sprint），故引入 **Track** 作為頂層研究主線分類，Sprint/Wave/Session 嵌在 Track 內。

| 層級 | 定義 | 本計劃用法 | 例 |
|------|------|-----------|-----|
| **Track** | 一條獨立的 alpha 假設研究主線，有自己的機率、kill 線、checkpoint。**新增層級**（研究 program 特有）。| 4 個（Track 1 critical path / Track 2 listing / Track 3 ensemble / Track 4 funding-directional）。Track 間有硬依賴（§3）。| Track 1 = 低 turnover 多日 TSMOM + cross-sectional |
| **Sprint** | **多週階段**（對齊專案 Sprint 1-4 用法）。一個 Track 通常對應一個 Sprint-length 的執行段；本計劃用 `S<n>` 標號（S1=Track 1 主線 sprint，依此類推）。| S1 (~週 0-7, Track 1) / S2 (Gate-A NOW + Gate-B Q4, Track 2) / S3 (中期, Track 3) / S4 (Track 4)。**注意**：S2/S4 的 NOW 段與 S1-W1 並行（§3）。| S1 = Track 1 五-七週主線 |
| **Wave** | **Sprint 內的並行子組**（對齊專案 W1-W9 用法）。同一 Wave 內的 session 可並行（文件/資料面不重疊）；Wave 間多有串行依賴。`W<n>` 標號，`W0` = NOW-launchable 前置波。| S1-W1 (前置：回填+retention) / S1-W2 (主線回測) / S1-W3 (結論+gate)；S2-W0 (Gate-A) / S2-W1+ (Gate-B)。| S1-W2 = leak-free 回測波（2 並行 session）|
| **Session** | **單次 dispatch 工作單元**（對齊專案 dispatch unit）。一個 session = 一個 sub-agent 一次派發，有明確 owner chain / 輸入 / 輸出 / acceptance / 估時 / blocked-on。`S<n>-W<n>-S<n>` 三級標號。| S1-W1-S1 = backfill 前置決策；S1-W1-S2 = 執行回填；S1-W2-S1 = TSMOM sweep；…| 見 §2 逐 track work-chain |

**標號規則**：`S<sprint>-W<wave>-S<session>`。例：`S1-W2-S1` = Sprint 1（Track 1）、Wave 2（主線回測）、Session 1（TSMOM 時序動量 sweep）。Track↔Sprint 一對一（Track 1=S1，Track 2=S2，Track 3=S3，Track 4=S4），故 Track 名與 S-號可互指。

**角色鏈標記**：每 session 標 `owner chain`，格式 `PM → <執行角色> → <review 角色>`。研究 session 的 review = QC（alpha/統計）或 MIT（資料/leakage），IMPL session 的 review = E2（structural）+ E4（regression）+ 視風險加 A3 / BB / CC（per §八 chain + memory `feedback_impl_done_adversarial_review`）。

---

## 2. 逐 Track Work-Chain

> 每 session：owner chain / 輸入 / 輸出 / **acceptance（可證偽）** / 估時 / blocked-on。acceptance 編號 `AC-<session>.<n>`。

### Track 1（Sprint S1，critical path）— 低 turnover 多日 TSMOM + cross-sectional momentum

**機制狀態**：findings §2.3② VALIDATED（multi-day gross 389-1213bps，all-in 成本占 3-4%）。**bottleneck = 歷史深度**（klines 56d，~8 獨立週期 ≪ n≥30）。**前置 = 回填 12-18mo 日線+4h（含 delisted）**。機率 ~45-55%。前置 spec = `historical-kline-backfill-spec.md`（**須補 delisted symbol，§0 條 1 + §6**）。

#### S1-W1 — 回填前置波（retention 決策 + 執行 + 資料品質）

**S1-W1-S1 — 回填前置決策 + survivorship-corrected symbol 清單**
- **owner chain**: PM → MIT（symbol 清單推導 + retention advisory）+ operator（retention / window / breadth 拍板）→ PA review（survivorship 覆蓋確認）
- **輸入**: backfill spec §1.4（retention BLOCKER）+ §2（window/breadth 選項）；`market.symbol_universe_snapshots` 歷史；Bybit 全 linear instrument 歷史
- **輸出**: (a) operator 簽定的 retention 決策（1095d / 400d）+ window（12/18/24mo）+ breadth（25 / 40-50）；(b) **survivorship-corrected symbol 清單檔**（含 active ∪ delisted ∪ Bybit-historical，每 symbol 標 listed_at/delisted_at/狀態）
- **acceptance（可證偽）**:
  - AC-S1-W1-S1.1：retention 決策已 operator 簽（grep `_sqlx`/`timescaledb_information.jobs` 或 operator 書面確認）；若選 1095d，PG-growth 已 MIT sizing（1m ~26M rows/3y compressed，落 §3 capacity 數字）
  - AC-S1-W1-S1.2：window + breadth 數值寫定（非「待定」）
  - **AC-S1-W1-S1.3（survivorship 硬修，PM 1-簽 #1）**：symbol 清單檔**經 MIT 證**含 ≥1 個 `is_delisted_at_asof=true` 或 `status IN ('Delivering','Closed')` 的歷史 symbol（若 18mo 窗內確有 delisted）；清單推導 SQL 附在輸出（`SELECT DISTINCT symbol ... FROM market.symbol_universe_snapshots` UNION 當前 universe）；**純 survivor-only 清單 = FAIL**
- **估時**: ~0.5h operator + ~2h MIT advisory
- **blocked-on**: 無（NOW-launchable）

**S1-W1-S2 — 執行回填（Bybit daily + 4h，含 delisted）**
- **owner chain**: PM → E1（backfill 腳本 + BB API self-check + Linux 執行）→ MIT review（資料品質 verify）
- **輸入**: S1-W1-S1 輸出（retention 已延 + symbol 清單 + window）；backfill spec §3（API plan）+ §4（idempotent load）
- **輸出**: 回填完成 + per-symbol-per-timeframe coverage report（`min_ts/max_ts/n_rows/expected/coverage_pct/n_failed`）
- **acceptance（可證偽）**:
  - AC-S1-W1-S2.1：INSERT 用 `ON CONFLICT (symbol,timeframe,ts) DO NOTHING`（match live writer `market_writer.rs:268`）；re-run idempotent（第二次 0 新增）
  - AC-S1-W1-S2.2：`1d` timeframe 字串已宣告於 report；4h gap-fill 不 clobber 既有 live row（first-writer-wins）
  - AC-S1-W1-S2.3：fail-closed——任何 retCode≠0（除 10006 backoff）= 該 symbol loudly abort + report partial，**0 fabricated row**（tick_count=NULL 非 fake 0）
  - AC-S1-W1-S2.4：每 delisted symbol 的 `max_ts` ≈ 其 `delisted_at`（證 Bybit 對該 delisted 確有歷史 kline 可拉；若 Bybit 對 delisted 不返回歷史 → report 標明，MIT 在 verify 評估 survivorship 殘留偏差）
  - AC-S1-W1-S2.5：live-1m 表面 0 污染（backfill 只寫 `1d`+`4h`，不寫 `1m/5m/15m/1h`）
- **估時**: ~3-4h 腳本 + 單位數分鐘執行 + ~0.5h supervise
- **blocked-on**: **S1-W1-S1（retention 決策 = operator hand-action gate；硬卡，§0 #5）**

**S1-W1-S3 — 資料品質 verify**
- **owner chain**: PM → MIT（empirical PG verify）→ PA review（gate 通過判斷）
- **輸入**: S1-W1-S2 coverage report；backfill spec §6 step 5
- **輸出**: 資料品質 verdict（coverage / gap / leak-free / retention-未-reap / 無 1m 污染 / survivorship 殘留評估）
- **acceptance（可證偽）**:
  - AC-S1-W1-S3.1：核心 symbol coverage_pct ≥ 預設門檻（MIT 定，建議 ≥90% 對未 delisted、delisted 按其在世期）
  - AC-S1-W1-S3.2：跑下一個 daily retention job 後重查 `min(ts)` 確認**未被 reap**（retention 延長真生效；backfill spec §1.4 經驗確認）
  - AC-S1-W1-S3.3：leak-free 預確認（只含 closed bar，無 partial 當期 bar）
  - AC-S1-W1-S3.4：survivorship 殘留量化——report 給「18mo 窗內 delisted symbol 占比 + 其平均在世天數」，供 Track 1 回測解讀 n_independent
- **估時**: ~2h
- **blocked-on**: S1-W1-S2

#### S1-W2 — 主線回測波（leak-free，**2 並行 session**）

**S1-W2-S1 — TSMOM（時序動量）leak-free 回測 + (N,M) sweep**
- **owner chain**: PM → QC（alpha 設計 + 回測 + OOS/PSR/DSR）+ MIT（leakage / 樣本充足 cross-verify）→ QC+MIT joint go/no-go
- **輸入**: S1-W1-S3 通過的深窗資料；findings §2.3②；R-2b 原 SQL
- **輸出**: TSMOM edge verdict（per (N,M) cell 的 net / OOS Sharpe / PSR / DSR / 半衰期）
- **acceptance（可證偽）**:
  - **AC-S1-W2-S1.1（leak-free day-1，PM 1-簽 #3）**：leak-free `shift(1)` 並列對照 + look-ahead 指紋 grep（`rolling(N).max/min` 含 current bar 必並列 shift(1)）；**未附即 FAIL**
  - AC-S1-W2-S1.2：net edge > all-in 成本 **2×**（findings §2.3②／QC gate）；用 survivorship-corrected 資料計（含 delisted 在世期）
  - AC-S1-W2-S1.3：walk-forward OOS Sharpe ≥ 0.5× IS Sharpe；**OOS<0.3×IS = kill**
  - AC-S1-W2-S1.4：PSR(0) > 0.95 且 DSR > 0（DSR 必對 (N,M) sweep cell 數做 deflation——多重檢驗校正）
  - AC-S1-W2-S1.5：半衰期落 7-30d（QC 提議的 alpha 持久性窗）
  - AC-S1-W2-S1.6：n_independent ≥ 30（用 S1-W1-S3 的真 coverage 算，非假設全窗）
- **估時**: ~3-4h
- **blocked-on**: S1-W1-S3（深窗資料 green）

**S1-W2-S2 — cross-sectional momentum leak-free 回測**
- **owner chain**: PM → QC（cross-sectional rank 設計 + 回測）+ MIT（leakage / breadth 充足）→ QC+MIT joint
- **輸入**: 同 S1-W2-S1（**共用深窗資料，只讀不寫 → 可與 S1-W2-S1 並行**）
- **輸出**: cross-sectional edge verdict（long-top/short-bottom rank portfolio 的 net / OOS / PSR / DSR）
- **acceptance（可證偽）**: 同 AC-S1-W2-S1.1~.6（leak-free / net>2×成本 / OOS≥0.5×IS / PSR>0.95 / DSR>0），外加：
  - AC-S1-W2-S2.7：cross-sectional 需 breadth——若 S1-W1-S1 只回填 25 sym 而 breadth 成 binding，回標「breadth-limited，待擴 40-50 sym 重跑」（不偽造顯著性）
- **估時**: ~3-4h
- **blocked-on**: S1-W1-S3（與 S1-W2-S1 並行，不互卡）

#### S1-W3 — 結論波（CP-2 gate）

**S1-W3-S1 — Track 1 alpha go/no-go 結論 + 載體裁定**
- **owner chain**: PM → QC+MIT（joint verdict）→ PA（架構整合判斷：若 GO，下一步嵌入 Stage 0R 的接口）→ operator（CP-2 決策）
- **輸入**: S1-W2-S1 + S1-W2-S2 verdict
- **輸出**: Track 1 verdict（GO → 進 stage0_ready 路徑 + 解凍 autonomy gate / NO-GO → kill 或 narrow / PARTIAL → 擴 breadth 重跑）；**並裁定 Track 3 的「低 turnover 載體」是否確立**（Track 3 硬依賴此）
- **acceptance（可證偽）**:
  - AC-S1-W3-S1.1：verdict 明確落 GO / NO-GO / PARTIAL 之一，附 §4 gate 判據逐條 PASS/FAIL 證據
  - AC-S1-W3-S1.2：若 GO，明寫「低 turnover 多日載體已確立」→ Track 3 解凍前提達成（否則 Track 3 維持 blocked）
  - AC-S1-W3-S1.3：若 NO-GO，明寫 kill 理由（net<0 或 OOS<0.3×IS）+ Track 3 連帶處置（無載體 → Track 3 不啟）
- **估時**: ~2h
- **blocked-on**: S1-W2-S1 + S1-W2-S2

---

### Track 2（Sprint S2）— listing pump-dump fade

**逃逸機制①（findings §2.3①）大 move，成本占比<5%，機率最高（~50-65%）。當前不可診斷**（collector $50M turnover filter，0/52 捕捉到上市瞬間）。**兩段式 + Gate-A 是 kill-gate（PM 1-簽 #2）**。

#### S2-W0 — Gate-A（**NOW-launchable**，maker-fill feasibility 預研，kill-gate）

**S2-W0-S1 — listing-window 捕獲可行性 + maker-fill feasibility 預研**
- **owner chain**: PM → QC（feasibility 設計，復用 `a2_maker_fill_feasibility.py` 範式）+ MIT（既有 5 個有 kline 的新上市資料 + listing SoT 可行性）→ QC+MIT joint kill 判斷；BB advisory（PreLaunch 訂閱可行性，read-only 查證）
- **輸入**: findings §2.3①根因（collector disjoint）；collector listing-capture spec §5（forward-accumulation 現實）；既有 5 個被部分捕捉的新上市 1m kline；`a2_maker_fill_feasibility.py`
- **輸出**: Gate-A verdict——(a) listing-window maker-fill 可達性估計（用既有部分捕捉樣本 + 微結構模型）；(b) PreLaunch 訂閱是否 Bybit-可行（BB read-only 查證，**不改 collector**）；(c) kill / proceed 建議
- **acceptance（可證偽）**:
  - **AC-S2-W0-S1.1（kill-gate，PM 1-簽 #2）**：maker-fill feasibility 估計 < 30% → **Track 2 KILL**（明寫省下 collector IMPL + 5-6mo 累積）；≥30% → proceed 到 Gate-B
  - AC-S2-W0-S1.2：feasibility 估計復用 `a2_maker_fill_feasibility.py` 範式（與 A2 49% 結論同方法學，可比較），附 adverse-selection 估計
  - AC-S2-W0-S1.3：BB 查證 PreLaunch `kline.1`/`publicTrade` 訂閱不會「handler not found」毒化連接（沿 liquidation topic 教訓）——**read-only 查證，0 collector 改動**
  - AC-S2-W0-S1.4：**全程 0 code 改動 / 0 collector IMPL**（Gate-A 是純預研；IMPL 在 Gate-B 才解凍）
- **估時**: ~4-6h（QC feasibility ~3-4h + BB read-only 查證 ~1-2h）
- **blocked-on**: 無（**NOW-launchable，與 S1-W1-S1 + S4-W0-S1 三並行**）

#### S2-W1 — Gate-B IMPL 波（**僅 Gate-A PASS 後解凍**）

**S2-W1-S1 — collector listing-capture IMPL（Path B，繞 hard filter 注入 + capture-only 隔離）**
- **owner chain**: PM → PA（spec 已寫，dispatch 前 re-confirm）→ E1（Rust IMPL，§9 波次 W1 兩並行 E1 + W2 組裝）→ **E2 + A3 對抗核驗**（高風險：WS 訂閱面 + capture-only 隔離）→ E4（regression + proptest）→ BB（WS 訂閱配額 §11，可與 E2/E4 並行）→ CC（16-root）→ deploy
- **輸入**: collector listing-capture spec（全文，§3 Path B 設計 + §10 E2 三點 + §11 BB 五點）
- **輸出**: listing-capture 模組 land + deploy + D+14 healthcheck 排程
- **acceptance（可證偽）**:
  - AC-S2-W1-S1.1：capture-only symbol **0 漏進 strategy intent**（E1 附 call-path grep proof：所有 `registry.snapshot()` consumer 餵 strategy 的只取 trading_symbols；spec §10 #1）
  - AC-S2-W1-S1.2：deadlock-free 生命週期（capture window 過期 / 升格雙出口；proptest random capture/expire/promote 後 0 phantom symbol；spec §10 #2）
  - AC-S2-W1-S1.3：fail-closed + 不破壞 25-sym 核心（detector panic/poll fail/配額滿 → scanner+WS+交易主路徑 0 影響；spec §10 #3）
  - AC-S2-W1-S1.4：BB 確認單連接 topic 上限容得下 capture 配額（~1176 topics）或開獨立連接；PreLaunch 訂閱 24h 隔離 probe PASS（spec §11）
  - AC-S2-W1-S1.5：硬邊界 0 觸碰（capture-only 不下單/不開倉/不餵 intent；CC 16-root A 級）
- **估時**: E1 ~12-16h + E2 ~3-4h + E4 ~3-4h + BB ~2-3h（並行）+ deploy ~1h
- **blocked-on**: **S2-W0-S1（Gate-A maker-fill≥30% PASS）**；spec re-confirm（dispatch 前 grep build tree `SymbolSpec`，spec §0 強制）

**S2-W1-S2 — forward 累積 + 中期樣本盤點**（passive，~D+90）
- **owner chain**: PM → MIT（樣本盤點）→ QC review
- **輸入**: S2-W1-S1 deploy 後 forward capture 資料
- **輸出**: ~D+90 樣本盤點（n≈15-25？）+ D+14 healthcheck（確認有新上市被 capture）
- **acceptance（可證偽）**:
  - AC-S2-W1-S2.1：D+14 healthcheck——`market.klines` 出現 launchTime±5min 內第一根 bar（證 capture 真生效）；否則 RCA
  - AC-S2-W1-S2.2：~D+90 給 n（有效 pump-fade 樣本數）+ ETA-to-30 更新
- **估時**: ~1h healthcheck + ~2h D+90 盤點（passive wait between）
- **blocked-on**: S2-W1-S1 deploy

#### S2-W2 — Gate-B 回測波（~Q4，**僅累積 n≥30 後**）

**S2-W2-S1 — listing pump-fade alpha 回測（n≥30 + maker fill 實測）**
- **owner chain**: PM → QC（回測 + OOS/PSR/DSR）+ MIT（leakage / 樣本）→ QC+MIT joint
- **輸入**: S2-W1-S2 累積的 n≥30 capture 樣本
- **輸出**: listing pump-fade alpha verdict
- **acceptance（可證偽）**:
  - **AC-S2-W2-S1.1（leak-free day-1）**：shift(1) 並列 + 指紋 grep（同 §0 #3）
  - AC-S2-W2-S1.2（Gate-B per QC 提議）：樣本 ≥30 + 回測 net>0 + **maker fill 實測 ≥50%**（與 Gate-A 估計交叉驗證；實測<50% 而估計≥30% → 記方法學偏差）
  - AC-S2-W2-S1.3：PSR>0.95 + DSR>0
- **估時**: ~4h
- **blocked-on**: S2-W1-S2（n≥30，~Q4）

---

### Track 3（Sprint S3，conditional）— multi-factor ensemble

**conditional：必須等 Track 1 確立低 turnover 載體**（S1-W3-S1.2 GO）。組合 oi_delta（findings §2.2 已驗真訊號 1.9-2.9bps）+ funding tilt + basis 等低相關弱訊號。機率 ~30-40%。

#### S3-W1 — 訊號相關性篩選波（**Track 1 載體確立後才啟**）

**S3-W1-S1 — 候選弱訊號相關性 + ensemble 可行性**
- **owner chain**: PM → QC（訊號相關矩陣 + ensemble 設計）+ MIT（特徵 leakage + 資料品質）→ QC+MIT joint kill 判斷
- **輸入**: S1-W3-S1 確立的低 turnover 載體；oi_delta（findings §2.2，已驗 leak-free n=80393）；funding tilt / basis 候選；深窗回填資料（複用 S1-W1）
- **輸出**: ensemble 可行性 verdict（候選訊號相關矩陣 + 在載體上的組合 net edge）
- **acceptance（可證偽）**:
  - AC-S3-W1-S1.1（leak-free day-1）：所有候選訊號 shift(1) 並列（oi_delta 已驗，新候選必驗）
  - **AC-S3-W1-S1.2（kill 線 per QC 提議）**：候選訊號 ρ median > 0.5（PC1/BTC-beta 主導，無法分散）→ **Track 3 KILL**
  - AC-S3-W1-S1.3：ensemble net edge > 單一訊號 standalone（證組合有增益，非噪音疊加）；net>2×成本（成本牆仍適用）
  - AC-S3-W1-S1.4：在 Track 1 載體（已確立的低 turnover 多日框架）上組合——**若 Track 1 NO-GO（無載體）→ Track 3 不啟**（硬依賴）
- **估時**: ~4-5h
- **blocked-on**: **S1-W3-S1.2（Track 1 GO + 載體確立）**

---

### Track 4（Sprint S4）— funding-extreme directional（A1 重定向，降級）

**A1 重定向降級**：demo 無 spot lending → 裸空 regime bet（非乾淨市場中性）。改 funding percentile rank **連續訊號** + 重設 160% break-even。需回填 2024 bull regime 樣本。機率 ~20-30%（QC 傾向低期望）。

#### S4-W0 — bull-regime 回填波（**NOW-launchable，與 S1-W1 同批回填邊際成本低**）

**S4-W0-S1 — 2024 bull regime funding/price 回填**
- **owner chain**: PM → MIT（回填範圍：2024 bull 窗 funding history + 對應 klines）+ E1（若需 funding history 回填腳本）→ MIT verify
- **輸入**: findings §2.4 #1（2024-11 bull 窗 PEPE 69% 結算破 30% APR，BB 查證）；backfill spec（funding history 用 `/v5/market/funding/history`，與 kline 回填同批）
- **輸出**: 2024 bull regime funding + price 回填完成 + coverage report
- **acceptance（可證偽）**:
  - AC-S4-W0-S1.1：2024 bull 窗（含 11 月 PEPE 等高 funding 反例）funding history 回填，覆蓋足以重評 funding percentile rank 分布
  - AC-S4-W0-S1.2：與 S1-W1 同批執行（共用 Bybit public 回填 infra，邊際成本低）；同 fail-closed + idempotent + 含 delisted（若 2024 窗有 delisted 高 funding symbol）
  - AC-S4-W0-S1.3：0 live-state 改動（純研究資料回填）
- **估時**: ~2-3h（與 S1-W1-S2 共用腳本，邊際 ~1h）
- **blocked-on**: 無（**NOW-launchable，與 S1-W1-S1 + S2-W0-S1 三並行**；資料層面可與 S1-W1-S2 同批跑）

#### S4-W1 — funding-directional 回測波（bull 回填後）

**S4-W1-S1 — funding percentile rank 連續訊號 directional 回測**
- **owner chain**: PM → QC（連續訊號設計 + break-even 重設 + 回測）+ MIT（leakage / regime 覆蓋）→ QC+MIT joint
- **輸入**: S4-W0-S1 bull 回填資料；A1 原始（findings §2.4 #1 否證的 break-even 設計問題）
- **輸出**: funding-directional alpha verdict（連續訊號 + 重設 break-even 後的 net / regime 依賴度）
- **acceptance（可證偽）**:
  - **AC-S4-W1-S1.1（leak-free day-1）**：funding percentile rank 用 expanding/rolling shift(1)（percentile 含當期 = look-ahead），並列對照
  - AC-S4-W1-S1.2：重設後 break-even（非 160%）下 net>2×成本；**明標 regime 依賴度**（裸空 directional 在 bear/range 的表現，非只報 bull 窗）
  - AC-S4-W1-S1.3：QC 低期望已知——若 net 僅在單一 regime（bull）為正 → 標「regime-bet，非穩健 alpha」，不偽裝成市場中性
- **估時**: ~3-4h
- **blocked-on**: S4-W0-S1（bull 回填 verify PASS）

---

## 3. 並行關係圖（≤7 ceiling）

### NOW（週 0-2）— **3 並行 session**（遠在 7 ceiling 內）

```
NOW 並行（同批回填邊際成本低 / 文件資料不重疊）：
  ┌─ S1-W1-S1  Track 1 回填前置決策 + survivorship symbol 清單   [MIT+operator → PA]
  ├─ S2-W0-S1  Track 2 Gate-A maker-fill feasibility（kill-gate）  [QC+MIT → joint; BB advisory]
  └─ S4-W0-S1  Track 4 2024 bull regime 回填                      [MIT+E1 → MIT]

  → S1-W1-S1 與 S4-W0-S1 在資料層共用 Bybit public 回填 infra（S1-W1-S2 + S4-W0-S1 可同批執行，邊際成本低，PM 1-簽 sequencing 一致）
```

### 串行依賴鏈（硬依賴）

```
Track 1（critical path）:
  S1-W1-S1 ─(retention=operator gate, 硬卡)→ S1-W1-S2 ─→ S1-W1-S3 ─→ ┬ S1-W2-S1 (TSMOM) ┐
                                                                       └ S1-W2-S2 (X-sec)  ┴─→ S1-W3-S1 (CP-2 gate)
                                                                         (W2 兩 session 並行，共用只讀深窗資料)

Track 2:
  S2-W0-S1 (Gate-A, NOW) ─(maker-fill≥30% 硬前置)→ S2-W1-S1 (collector IMPL, 高風險) ─→ S2-W1-S2 (累積~D90) ─→ S2-W2-S1 (~Q4 回測)
                          └─ maker-fill<30% → KILL（省 collector IMPL + 5-6mo）

Track 3（conditional, 硬依賴 Track 1）:
  S1-W3-S1.2 (Track 1 GO + 載體確立) ─(硬依賴)→ S3-W1-S1 (ensemble; ρ>0.5 → KILL)
  └─ Track 1 NO-GO → Track 3 不啟

Track 4:
  S4-W0-S1 (bull 回填, NOW) ─→ S4-W1-S1 (funding-directional 回測)
```

### 並行窗口逐段（每段標同時 active session 數，驗 ≤7）

| 時段 | 同時 active session | 數 | 備註 |
|------|--------------------|----|----|
| 週 0-2（NOW）| S1-W1-S1 / S2-W0-S1 / S4-W0-S1（+ review 角色附掛）| **3** | NOW 三並行（PM 1-簽 sequencing）|
| 週 0-2 後段 | S1-W1-S2 + S4-W0-S1（同批回填）→ S1-W1-S3 ; S4-W1-S1（bull 回填完）| ≤3 | 回填執行 + Track 4 回測可起 |
| 週 2-7（Track 1 主線）| S1-W2-S1 + S1-W2-S2（並行）; 視 S2-W0 verdict 起 S2-W1-S1（若 Gate-A PASS）| ≤4 | S1-W2 兩並行 + 可能 collector IMPL |
| 週 7+ | S1-W3-S1 → 若 GO 起 S3-W1-S1 ; S2-W1-S2 passive 累積 | ≤3 | Track 3 解凍 |
| ~Q4 | S2-W2-S1（listing 回測）| 1 | Gate-B 收 |

**最大並行 = 4（週 2-7）** ≪ 7 ceiling。每個 IMPL session（S2-W1-S1）內部 review 角色（E2/A3/E4/BB/CC）按 §八 chain 串/並，不額外擴 session 計數（review 是 session 內 owner chain 的一環）。

---

## 4. Gate / Checkpoint 表

### Checkpoint（operator 決策點，QC 提議）

| CP | 時點 | 判據 | 不過的去向 |
|----|------|------|-----------|
| **CP-1** | ~週 2 | Track 1 回填完成 + 資料品質 green（S1-W1-S3 PASS）；Track 2 Gate-A verdict（kill/proceed）；Track 4 bull 回填完成 | 回填失敗 → RCA backfill 腳本 / Bybit 對 delisted 不返回 → MIT 量化 survivorship 殘留偏差，調整 Track 1 解讀 |
| **CP-2** | ~週 7 | Track 1 結論（S1-W3-S1）：GO / NO-GO / PARTIAL | NO-GO → Track 1 + Track 3 連帶 kill；剩 Track 2（~Q4）+ Track 4 + 回到 LiveDemo 降級主路 |
| **CP-3** | ~9 月 | 整體：Track 1/2/3/4 累積 verdict | operator 決策三選一：(a) 放寬約束（VIP 升級路徑 / 付費 feed）/ (b) learning-only（承認窄路無解，轉純學習平面）/ (c) 縮 universe（聚焦少數可行 symbol/regime）|

### 各 Track kill 線

| Track | kill 判據 | 時點 | kill 後去向 |
|-------|----------|------|-----------|
| Track 1 | net<0 **或** walk-forward OOS Sharpe < 0.3× IS | S1-W2-S1/S2 | Track 1 + Track 3 連帶 kill（Track 3 無載體）；CP-2 記 |
| Track 2 | **Gate-A: maker-fill 估計 < 30%**（kill-gate，省 collector IMPL + 5-6mo）；Gate-B: 樣本<30 或 net<0 或 maker fill 實測<30% | S2-W0-S1（Gate-A）/ S2-W2-S1（Gate-B）| Gate-A kill 即停 Track 2 全線；capture 機制殘值供其他 listing 研究 |
| Track 3 | 候選訊號 ρ median > 0.5（PC1/BTC-beta 主導，無法分散）| S3-W1-S1 | Track 3 kill；oi_delta 保留作未來 ensemble 候選 |
| Track 4 | net<0 跨 regime；或僅單 regime 為正（QC 低期望已知）| S4-W1-S1 | Track 4 標 regime-bet（非穩健 alpha），降為 learning-only |

---

## 5. 既有資產整合（位置 + 何時動）

| 資產 | 現狀 | 在本計劃的位置 | 何時動 |
|------|------|---------------|--------|
| **M7 V116 decay detector** | spec done（`v116-m7-decay-detector-spec.md`）；E1 IMPL **held**（autonomy freeze 唯一例外，但成本牆下無 alpha 可保護使其偏早，per TODO v92）| **不在本 4-track 內**——獨立解凍 gate。**解凍條件 = 首個 net-positive candidate 達 stage0_ready**（即 Track 1 S1-W3-S1 GO 或其他 track 過 gate）| **S1-W3-S1 GO（或任一 track 過 stage0_ready）後解凍 V116 IMPL**；在此之前 spec 按住。本計劃不重啟 M7，只標解凍觸發點。|
| **collector listing-capture spec** | spec done（`collector-listing-capture-spec.md`，PA 寫）；IMPL 未起 | Track 2 **Gate-B 前置**（= S2-W1-S1）| **僅 S2-W0-S1 Gate-A maker-fill≥30% PASS 後解凍 IMPL**（PM 1-簽 #2：可達性 kill-gate 先於 IMPL）|
| **historical-kline-backfill spec** | spec done（`historical-kline-backfill-spec.md`，MIT 寫）；**§2 symbol source = survivor-only，須補 delisted**（§0 #1）| Track 1 **前置**（= S1-W1）+ Track 4 bull 回填共用 infra（S4-W0-S1）| **NOW**（S1-W1-S1 起）。**dispatch S1-W1-S2 前須更新 backfill spec §2 symbol source 為 survivorship-corrected**（cleanup debt，PM 整合 TODO 時派 MIT 補 spec 或在 dispatch prompt 覆蓋）|
| **V### reconcile（V116/V117/V118-124）** | head=V115；V116=M7（free, held）；V117=ADR-0046 funding_arb 保留；M5/M7/M12/M13 reserve **V118-124**（doc cascade C-1..C-6 pending）| 本計劃**0 新 migration**（Track 1/4 backfill 是純 data INSERT；Track 2 collector MVP in-memory ledger 0 migration per spec §4）| backfill + collector MVP **不需** V###。**唯一可能新 migration** = collector capture audit ledger 落 PG（spec §4：V118+）或 M7 V116 解凍時——屆時走 PG dry-run double-apply（memory `feedback_v_migration_pg_dry_run`）。doc cascade C-1..C-6 是獨立 TODO（PM 整合時併 §4 matrix 更新）|

---

## 6. 第一個可立即 dispatch 的 session（NOW）+ owner chain + acceptance

> PM 2 簽後可直接派。NOW 三並行的第一個（critical path 起點）。

### S1-W1-S1 — Track 1 回填前置決策 + survivorship-corrected symbol 清單

**owner chain**: `PM → MIT（symbol 清單推導 + retention advisory）+ operator（retention/window/breadth 拍板）→ PA（survivorship 覆蓋 + retention 安全確認）`

**為何是第一個**：Track 1 是 critical path（最快出 edge 定論，數天到數週 vs Track 2 的 ~Q4）；S1-W1-S1 是其唯一無前置依賴的起點；且它含 **operator hand-action gate（retention 決策）**，越早拍越早解鎖 S1-W1-S2 執行回填。與 S2-W0-S1（Gate-A）+ S4-W0-S1（bull 回填）NOW 三並行。

**輸入**:
- `historical-kline-backfill-spec.md` §1.4（retention BLOCKER）+ §2（window/breadth 選項）+ §3（API plan）
- `market.symbol_universe_snapshots`（V058:31-50；含 `status/listed_at/delisted_at/is_delisted_at_asof`）— delisted SoT
- Bybit 全 linear instrument 歷史（`/v5/market/instruments-info`，含已下市）

**輸出**:
1. operator 簽定：retention 決策（1095d 延長 for 18mo / 400d for 12mo）+ window（12/18/24mo）+ breadth（25 MUST / 40-50 optional）
2. **survivorship-corrected symbol 清單檔**（active ∪ delisted ∪ Bybit-historical；每 symbol 標 listed_at / delisted_at / status / 在世天數）+ 推導 SQL

**acceptance（可證偽）**:
- **AC-S1-W1-S1.1**：retention 決策 operator 已簽（書面或 PG job 確認）；若 1095d，MIT 已 sizing PG-growth（落具體 rows/GB 數字，非「acceptable」空話）
- **AC-S1-W1-S1.2**：window + breadth 數值寫定（非「待定」/「TBD」）
- **AC-S1-W1-S1.3（survivorship 硬修，PM 1-簽 #1，最關鍵）**：symbol 清單經 MIT 證含歷史 delisted（`is_delisted_at_asof=true` 或 `status IN ('Delivering','Closed')`，若 18mo 窗確有）；推導 SQL 附輸出；**純 survivor-only 清單 = session FAIL，退回重做**

**估時**: ~0.5h operator 決策 + ~2h MIT advisory + ~0.5h PA 覆蓋確認

**blocked-on**: 無（NOW-launchable）

**dispatch 註記（PM 派時帶）**:
- 此 session **覆蓋** backfill spec §2「Symbol source = live scanner universe」——必須改為 survivorship-corrected（spec §2 標 cleanup；MIT 在本 session 順手提 spec patch 或 PM 在 prompt 明寫覆蓋）
- retention 決策是 **operator hand-action**，sub-agent 不可代拍（§0 #5）
- 全程 read-only（PG 查 symbol_universe_snapshots + Bybit public instruments-info）；0 回填執行（執行在 S1-W1-S2）；0 schema 改動
- NO-OP exit path：若 dispatch 時發現 retention 已被其他 session 延長 / symbol 清單已存在 → 直接進 PA 覆蓋確認，不重做

---

## 7. 紀律與邊界聲明（本計劃）

- **證據紀律**：fact/inference/assumption 分離承載——本計劃的 FACT（survivorship SoT 存在 / V### 號 / retention 365d / 機制已驗）均 grep 或讀 source 自證（§0 #1 已標 file:line）；機率（45-55% 等）/ ETA（數週到 Q4）為 QC 提議的 inference，標明非 fact；kill 判據為可證偽 acceptance。
- **acceptance 可證偽**：每 session acceptance 為具體數值/grep/SQL 可驗，非「looks good」。回測 session 第一條恆為 leak-free shift(1)（PM 1-簽 #3）。
- **繼承 PM 1-簽 3 條**：survivorship 含 delisted（§0 #1 + AC-S1-W1-S1.3）/ 執行可達性 kill-gate 先於 demo 週期（§0 #2 + AC-S2-W0-S1.1）/ leak-free shift(1) day-1（§0 #3 + 各回測 AC.1）。
- **不寫 feature code / 不執行回填 / 不改 TODO**：本檔僅 dispatch packet 設計；PM 2 簽後整合進 TODO。
- **硬邊界 0 觸碰**：全 read-only research（backfill/回測）+ capture-only 旁路（collector，不下單/不餵 intent）；無一 session 觸 live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / authorization.json / Decision Lease。
- **並行 ≤7**：最大並行 4（§3），高風險 IMPL（S2-W1-S1）強制 A3+E2 對抗核驗（memory `feedback_impl_done_adversarial_review`）。
- **派發前確認**：`git fetch --all` 已執行（2026-05-31）；`docs/execution_plan/2026-05-31--alpha_edge_research_execution_plan.md` 此前不存在；`git log --all | grep alpha.edge/edge.research/tsmom/listing.capture/kline.backfill` = 0；無相關 branch → NO-OP exit 不觸發，本檔為首版。

---

## 8. 16 根原則 / 硬邊界自檢

| # | 原則 | 本計劃 |
|---|------|--------|
| 2 讀寫分離 | backfill/回測純 read research；collector capture-only 不寫 trading state ✅ |
| 4 策略不繞風控 | Track 2 capture symbol 不餵 strategy intent（spec §3.2 隔離）✅ |
| 5 生存>利潤 | 未驗證波動標的不開倉（collector 否決「capture 即可交易」）；net>2×成本 gate ✅ |
| 6 失敗默認收縮 | 所有 kill 線 + fail-closed 回填 + Gate-A kill-gate ✅ |
| 7 學習≠改寫 live | M7 V116 detector-only（held）；回填/回測 0 live-state ✅ |
| 8 可解釋 | coverage report + capture audit ledger + verdict 附判據 ✅ |
| 10 認知誠實 | fact/inference/assumption 分離；機率/ETA 標 inference；leak-free 強制 ✅ |
| 13 成本感知 | 成本牆是全計劃中心約束；net>2×成本 是每 alpha gate ✅ |
| 14 零外部成本 | Bybit public 回填 no-auth；collector Path B engine 自包含 ✅ |
| 16 組合級風險 | Track 3 ρ>0.5 kill（相關曝險）；capture 隔離於 portfolio ✅ |

**硬邊界**：無觸碰。全 read-only research + capture-only 旁路 + M7 detector-only（held）。

---

**PA DESIGN DONE: report path: docs/execution_plan/2026-05-31--alpha_edge_research_execution_plan.md**
