# A1 funding_short_v2 修復核驗 + 結構性可行性審計

| 項目 | 內容 |
|------|------|
| 日期 | 2026-05-31 |
| 觸發 | 平行 session commit `f7271405`（restore A1 functional replay）聲稱修復了 A1 alpha candidate 的程序層問題，需獨立核驗其正確性與結論 |
| 範圍 | A1 (funding_short_v2) 的 stub 修復、SQL、Rust 門檻、跨語言單位、look-ahead；PG 真實數據（MIT sub-agent）；Bybit 官方 funding 數據（外部 ground-truth） |
| 方法 | 親讀 source（非採信報告文字）+ git 修前修後對比 + MIT 獨立 PG 審計 + 自抓 Bybit `/v5/market/funding/history` 自行解析 |
| 結論等級 | ★★ funding_short_v2 結構性 NO-GO（永久，非市場/pipeline 問題） |

---

## 一、檢查了什麼

1. **程序修復正確性** —— `f7271405` 改動的 6 個檔案（runner/report/SQL/params.rs/toml/tests）逐行核驗。
2. **無造假 alpha** —— 確認門檻常量是否被偷偷放鬆。
3. **跨語言一致性** —— Rust `compute_edge` 與 Python replay gate 的單位是否對齊。
4. **數據洩漏** —— A1 feature SQL 的 as-of join 是否 leak-free。
5. **載重結論的真實性** —— 「A1 無 signal 是因 funding 太低」是否被 PG 真實數據支持（MIT）。
6. **funding 數據可信度** —— 我方 panel 是否只抓到 baseline 假數據；與原始表、與交易所官方是否一致。
7. **結構性可行性** —— 自抓 Bybit 官方 funding 歷史，驗證 funding 物理範圍 vs 策略門檻。

---

## 二、發現

### 2.1 三個程序問題：屬實，且修復正確 ✅

| 宣稱問題 | 核驗 | 證據 |
|----------|------|------|
| A1 是 stale stub，硬編 `basis_panel_infra_missing` | 屬實 | 修前 `f7271405^` 確有硬編 stub；`V115__panel_basis_panel.sql` 建表後 stub 未更新。修法：硬編 → runtime `to_regclass('panel.basis_panel')` 動態探測（`candidate_stage0r_report.py:191`），正確做法 |
| A1 net 漏算 funding carry | 屬實、方法論正確 | 新 SQL 將持倉窗 funding settlement 計入 net_bps（`alpha_candidate_a1_funding_short_features.sql:119`）；as-of join leak-free（funding/basis 取 `snapshot_ts ≤ signal_ts`，exit/carry 才用未來窗且明標為 outcome） |
| A2 SQL 註釋 `%(name)s` 會炸 | 屬實（真 footgun） | psycopg2 帶 params dict 時掃描**含註釋**的整個 query 做 `%` 代換，假鍵 `name` → `KeyError`。修復移除假鍵 + 裸 `%`（`w_audit_8c_liquidation_cluster_stage0r_features.sql:116`） |
| 未放鬆門檻造假 alpha | 屬實（誠實） | params.rs / toml 為**純註釋改動**，常量 `0.30 / 0.20 / 1.5` 一字未動；compute_edge break-even 22/10000/1.5 = 14.67 bps/8h ≈ 160.6% APR 經 Rust（`mod.rs:166`）與 Python（`candidate_stage0r_runner.py:385`）雙端核實，單位一致 |

工程品質：已 commit（非 overlay）、probe artifact 真實存在、tests 47/47。**屬合格的對抗式自審。**

### 2.2 收尾結論的歸因需修正 ⚠️

平行 session 結論：「A1 無 signal 是因 funding 太低，**不是 basis pipeline 缺失**。」後半與 probe 自身數據矛盾。

probe `reject_counts`（MIT 自 `candidate_stage0r_after_fix_14d.json` 撈出）：

| reject 原因 | 佔比 | 性質 |
|-------------|------|------|
| `missing_basis_asof` | **93%** | basis_panel 僅 **1.8 / 14 天**數據覆蓋 probe 窗 → as-of join 撲空 |
| funding 兩道 gate（30% / 160%） | 各 7%（lockstep） | 僅擋到能走到該步的少數 row |

混淆了「**表存在**」（stub 確 stale，已正確修復）與「**數據足夠**」。basis_panel 2026-05-30 才首寫、僅 1.8 天，故**當前 #1 binding 正是 basis 數據不足**——恰為其宣稱「不是」的成因。此為「等數據累積」即可解的獨立 pipeline 問題，與下節結構死因不同層，不應混為一談。

### 2.3 funding 數據可信、無 pipeline clamp ✅

對「正側 funding 是否被我方 pipeline 截斷」做對抗性反查，結論：數據忠實。
- 我方 WS→panel 路徑 `funding_curve.rs:80` 僅 `rate × 10000` 純單位轉換，無 clamp；REST settlement 路徑 `rest_poller.rs` 純轉發。
- 三源獨立一致：`panel.funding_rates_panel`（WS）/ `market.funding_rates`（REST）/ Bybit 官方 API，max 均為 +1.0 bps。
- 非 baseline 假數據：distinct 1,200+ 值、會走負至 -3.19 bps、source_tier = `bybit_v5_ws_tickers`。

### 2.4 結構性根因：Bybit 正側 funding 硬上限 🔴

自抓 Bybit `/v5/market/funding/history`（200 結算/symbol，~66 天，含 probe 窗），自行解析：

| Symbol | 正側 max funding | = APR | 破 30% 入場 gate 筆數 | 負側 min |
|--------|------------------|-------|----------------------|----------|
| BTCUSDT | +0.0001 | 10.9% | **0** | -0.00016 |
| SOLUSDT | +0.0001 | 10.9% | **0** | -0.00031 |
| DOGEUSDT | +0.0001 | 10.9% | **0** | -0.00020 |
| 1000PEPEUSDT | +0.0001 | 10.9% | **0** | -0.00048 |
| WIFUSDT | +0.00005 | 5.5% | **0** | **-0.00776（-85% APR）** |

- **正側硬鎖 +0.01%/8h（+10.9% APR）**，連最高波動 memecoin（PEPE/WIF/DOGE）亦然；1000 筆結算 **0 筆**破 30% gate。
- **負側自由**（WIF 達 -85% APR）→ 不對稱 = 交易所結構性上限，非市場巧合。
- MIT 同步驗：我方 25-symbol universe 517,675 row，0 row 跨任何 gate。

funding_short_v2 入場門檻 30% APR、break-even 160% APR，**雙雙設在交易所結構上限（10.9% APR）之上**。

---

## 三、結論

1. **funding_short_v2 為結構性 NO-GO（永久）。** 收正 funding 做空需正側 funding 遠高於成本門檻，而 Bybit linear perp 正側 funding 結構性封頂 +10.9% APR。策略在 Bybit 上**數學上永遠無法進場**——與市場狀況、basis 數據、任何 pipeline 修復皆無關。等 basis_panel 累積至 14 天、或解除 BTC/ETH fence 擴至 altcoin，**均無效**（已實證 memecoin 亦封頂）。

2. **三個程序修復本身正確、值得保留**，但它們是在打磨一個結構上無法 fire 的策略。

3. **本應在 QC 策略設計階段一眼查出**：建立 funding-harvest 策略前先核對目標交易所對該 alpha 來源的硬上限 vs 策略門檻。建議納入 `quant-strategy-design` checklist，可攔截下一個同類白做的候選。

4. **獨立可修問題**：basis_panel 數據不成熟（1.8/14 天）會污染**任何**依賴 basis 的 candidate 之 probe；屬「等累積」問題（最早 ~2026-06-13 達 14 天），與本案結構死因分開處理。

5. 附帶：A2 (liquidation_cascade_fade) 同 probe avg_net = -4.11 bps（負）、n_eff = 9，亦 non-viable；psycopg2 註釋 `%` footgun 已 ≥2 次（另見 `liquidation_cluster_stage0r_report.py:1070` 漏傳 `notional_pct_floor`），建議加 CI lint 掃 SQL 註釋非法 `%` 根治，勿反應式逐次修。

---

## 附錄：證據與可復現

- 修復 commit：`f7271405` fix(alpha-stage0r): restore A1 functional replay
- probe artifact：`trade-core:/tmp/openclaw/a1_fix_probe/candidate_stage0r_after_fix_14d.json`（overall observe_more / A1 draft_only / selected_signals 0）
- PG 審計：MIT sub-agent，`docker exec trading_postgres psql -U trading_admin -d trading_ai`，migration head 115，純讀
- Bybit ground-truth：`curl https://api.bybit.com/v5/market/funding/history?category=linear&symbol=<SYM>&limit=200`，自行解析 max(fundingRate)
- 核驗者：主審查 session（PM/Conductor）+ MIT（PG 數據）+ Bybit 官方 API（外部）
