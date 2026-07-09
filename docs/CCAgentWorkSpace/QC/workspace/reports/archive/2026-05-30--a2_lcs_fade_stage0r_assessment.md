# QC 數學審計 — A2「LCS fade」(`liquidation_cascade_fade`) Stage 0R 狀態評估 · 2026-05-30

> 本檔由 QC sub-agent 產出（agent 受 session-limit 截斷未自行落檔，主會話 PM 代落檔，內容逐字保留）。

## Executive Summary（結論先行）

**A2 是否 ready 推進 Stage 1 Demo：否。判定 = REVISE / HOLD（不是 REJECT）。**

當前 A2 Stage 0R 真實 verdict = **`observe_more`**（runner 自報，real-PG offline 結果：n_eff=7、avg_net=−2.45 bps、13 days、`sample_insufficient`）。這是**正確且誠實**的結論 —— runner 沒有假 PASS。但「observe_more」按 SSOT §6 的定義就是「**no-capital-scale verdict**」，明確**不是** `stage0_ready`、更不是 Demo 啟動許可。Stage 1 alpha-bearing promotion 需要 green Stage 0R preflight（CLAUDE §四硬邊界），而當前 preflight = 黃燈（sample 不足）非綠燈。

**三句話定位**：
1. **工具（runner）方法論大致站得住**：k_total override、dynamic_exit proxy、time-block CSCV、sample_insufficient/signal_failure 分流、k_prior fail-closed 都是對的設計選擇，且都已誠實標註。對工具本身給 **APPROVE-WITH-CONDITIONS**。
2. **證據（A2 的 edge）完全不存在**：當前唯一一次 real-PG run 顯示 avg_net **為負**（−2.45 bps），離 +15 bps 的 floor 差 17 bps，且 n_eff=7 連最低 power 都達不到。**沒有任何 edge 證據支持推進。**
3. **alpha 假設本身有實質保留**（見 push back §6）：liquidation cascade fade 在 crypto perp 的可持續 edge 在 maker-only 執行 + 高成本 + 已被 HFT arb 的現實下高度可疑；當前負 net 與這個先驗一致。

**核心區分**：問的是「A2 夠不夠格從 Stage 0R 推進 Stage 1」。答案是工具能跑、誠實標 observe_more，但**證據面 0/3 達標**，且**目前根本沒有 committed、green、運行過的 Stage 0R preflight artifact 可以引用為 promotion evidence**（IMPL 已 land 在 main 但 runner 從未在 runtime env 端到端跑過 —— E1 自己標 psycopg2 TCP 留給 E4）。

---

## 1. 定位確認：「LCS」確切定義

「LCS」= **L**iquidation **C**ascade fade 的 **S**tage 0R（runner / candidate）。策略定義（spec + Rust skeleton + SQL 三處交叉確認）：

- **alpha_source_id** = `liquidation_cascade_fade`（`a2_cascade_adapter.py:76`），對應 SSOT 候選池 A2。
- **訊號定義**：5min rolling window 內 `dominant_notional_5m = max(long_notional_5m, short_notional_5m)` > per-symbol threshold（BTC $500k / ETH $300k），且 `event_count_5m ≥ 3`，且 `dominant_side != Mixed`。
- **方向（核心 thesis）**：**fade against the dominant cascade side**。`LongLiquidated → entry_is_long=true`；`ShortLiquidated → entry_is_long=false`。
- **出場**：OR(TP 1.5% / SL 2% / 60min time-stop / reverse-cascade flip > 1.5×)。
- **8c↔A2 方向一致性已驗**：8c SQL `expected_dir = +1` 與 A2 Rust `entry_is_long = LongLiquidated → true` 語意一致（v1 A1 方向接反 180°，A2 沒這問題）。

代碼定位：runner = `helper_scripts/reports/alpha_candidate_stage0r/{candidate_stage0r_runner.py, a2_cascade_adapter.py, candidate_stage0r_report.py, candidate_stage0r_smoke.py}`（已 commit main）；Rust = `rust/openclaw_engine/src/strategies/liquidation_cascade_fade/`；8c 統計核心 = `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py`；SQL = `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`。

---

## 2. Stage 0R runner 產出什麼 evidence

跑通後產生單一 JSON packet（stdout 或 `--out`）。**沒有寫任何 PG 表 / TOML / fill**（governance hard boundary，AMD §3.2，代碼確實只 emit `eligible_for_demo_canary` true/false）。指標：PSR(0) Bailey-LdP / DSR（k_total override 後）/ time-block CSCV PBO / block bootstrap CI（60m+4h）/ avg_net_bps / max_day_share / max_symbol_share / pooled n_eff（cluster-aware）/ sample_sufficiency 分類 / 6-check 三態 verdict。

**存哪**：純 stdout/檔 JSON，**不落 PG**。Stage 0R verdict 不寫 `learning.hypotheses` 也不寫 `canary_stage_log` —— 符合「replay 不取代 demo fill-lineage」硬邊界。

**關鍵 runtime 事實**：runner 在真 runtime env（psycopg2 TCP）**從未端到端跑過**。唯一數值結果來自 E1 用 docker exec SELECT 導出 CSV → offline harness，得 observe_more。**連「green Stage 0R preflight」這個 promotion 前提本身都還沒有正式 runtime artifact。**

---

## 3. 方法論審計（5 維度）— Conditional

### 黑名單檢查：✅ 0 觸碰（無 HMM/GARCH/VPIN/單獨波動率均值回歸）。LCS 用 `dominant_notional > 閾值`直接比較，**不是 `rolling(N).max()` 含-current-bar breach**，與 bb_breakout Donchian leak 有關鍵結構差異。

| 維度 | 狀態 | 證據 |
|---|---|---|
| 樣本基準 | ❌ | n_eff=7 ≪ floor 300；13 days；91 net values；avg_net=−2.45 bps（負）。未並列 buy-hold/random-entry baseline（C-4）。 |
| 統計顯著 | ⚠️ | PSR/DSR/Wilson/bootstrap 公式正確（Bailey-LdP skew/kurt-aware）。n=91/n_eff=7 下 noise 主導，三態正確判 INSUFFICIENT→observe_more。 |
| Look-ahead bias | ✅ | 8c SQL leak-free：entry = `bucket_end_ts+quiet` 後第一根 1m **open**；exit = `+horizon` 後第一根 open，LATERAL 嚴格未來 bar。adapter 0 改 SQL 結構。check 1 標 ATTEST 待 E2 call-path grep 親證。 |
| Sizing & 風控 | ⚠️ | 策略 spec §3.3 自承 Kelly baseline 期望**負**（1.5%TP×50% − 2%SL×50% = −0.25%）。R:R=0.75（賠率<1），需 win_rate>57% 才 break-even。當前 avg_net 負與此一致。 |
| Live 適用 | ❌ | (a) dynamic_exit 60m proxy「保守」斷言是假設非證據；(b) PostOnly maker 在 cascade 瞬間最難成交，offline 假設 100% fill at open 高估可達性；(c) cost_bps=12 在 cascade 期 spread 爆 30-50bp 下可能嚴重低估。 |

### k_total override 是否掩蓋 DSR fail？— **沒有，是正確修正**

8c `compute_stage0r` 內 `k_new = max(25,n_symbols)×11664`（line 1388）對應研究階段 11664-cell sweep。但 A2 candidate 是**固定單一閾值（pinned，非 sweep）**，真實 trial = 2 sym × 2 dir × 1 thr × 1 horizon = 4。沿用 inflated k → DSR benchmark √(2 ln 291600)≈5.06，對只試 4 組是過度懲罰 → A2 永遠 silent DSR fail。override 到 `k_candidate = k_prior + 4` 是 Bailey-LdP DSR **正確用法**，且保留 `dsr_8c_inflated_preserved` 透明欄位。**裁決：正確統計修正，NOT 放水。唯一 condition（C-1）：k_prior 必須是真實「先前所有 funding/liquidation 研究嘗試數」。**

---

## 4. promotion 判斷 + 還缺什麼

**不推進 Stage 1 Demo。** 證據 0/3：sample n_eff=7（差 ~43×）/ 經濟 edge −2.45bps（差 ~17.5bps 且符號負）/ 顯著性全 INSUFFICIENT。

### 還需 runtime evidence（ssh trade-core 取，PM 去跑）

**A.（先確認 preflight 能在 runtime 跑出來）**
```
ssh trade-core，srv 根目錄、runtime env：
  python3 -m helper_scripts.reports.alpha_candidate_stage0r --window-days 14 --out /tmp/a2_stage0r.json
取回：exit code / packet.candidates.A2.verdict / k_prior_source / sample_sufficiency.classification
```
**B.（k_prior 真實值）**
```sql
SELECT to_regclass('learning.strategy_trial_ledger');
-- 若非 NULL：
SELECT count(DISTINCT candidate_key) FROM learning.strategy_trial_ledger
WHERE candidate_key IS NOT NULL
  AND (strategy_name ILIKE '%liquidation%' OR trial_family ILIKE '%liquidation%'
       OR candidate_key ILIKE '%liquidation%'
       OR evidence->>'alpha_source_id' = 'liquidation_cascade_fade');
```
**C.（訊號頻率 / n_eff binding 維度 → ETA 關鍵）** 跑完讀 `packet.candidates.A2.pooled_n_eff_breakdown.binding_dimension`；若 binding = distinct_60min_clusters → 2-symbol 結構上難達 n_eff 300。

### 預估到位時間
- **不是時間問題，是 edge 缺失問題**。當前 −2.45 bps + n_eff=7，延長 window 不會把負 net 變正。
- 若硬走擴樣本：達 n_eff=300 在 2-symbol 上保守 ≥ 數月，且當前負軌跡不支持翻正。
- **更誠實路徑**：A2 維持 `observe_more` lane，**weekly 重跑 runner** 監看 avg_net 是否翻正 + n_eff trend，**不進 Stage 1 Demo**。

---

## 5. QC hard-gate 裁決

### Hard-gate 1：time-block CSCV 在 2-symbol/14d 統計效力 — CONDITIONAL PASS
- 改 time-block（day-block train/test）是**正確退路**（原 symbol×cell CSCV 在 2-symbol/single-cell 數學不成立）。
- 但這是 **day-block generalization proxy 非 Bailey-LdP CSCV PBO**（runner 已誠實標 `pbo_semantics`）。14d/single-cell 下無真 model-selection 維度 → PBO ≈ 粗糙 sub-period stability check，**不能作 A2 主要 overfit 證據**。A2 overfit 防線應是 **forward OOS（真實 demo fills）**。

### Hard-gate 2：k_prior 來源 — **runner 已修對，APPROVE**
TODO 描述「default 0」是 **stale**。實際（`candidate_stage0r_report.py`）：`--k-prior` default=None → **auto-query `learning.strategy_trial_ledger`** → ledger 不存在則 `k_prior_source="unavailable"` + **fail-closed 降保守**（stage0_ready 降 observe_more，eligible=False）。符合 RP6。**condition C-1**：跑 §4-B 後告知 ledger 是否存在 + count；不存在 → DSR check 在 ledger 補上前永遠走 fail-closed downgrade（類似 A1 basis_panel gap 的 infra prereq）。

---

## 6. Push back：alpha 假設本身可疑（直說）

對可持續性有實質保留，當前 −2.45 bps 與先驗一致。不是 RETRACT（不觸黑名單可回測方法乾淨），但要求計入決策：
1. **擁擠度**：liquidation cascade reversion 是最被廣知、最被 HFT 擁擠的 crypto 微結構 pattern 之一（散戶都看 liquidation heatmap）。1m sampling + maker-only 相對 cascade 秒級 alpha 半衰期可能錯過甜蜜點。
2. **執行可達性（致命非邊際）**：cascade 最劇烈時 orderbook 最薄、spread 最爆，PostOnly resting order 最不可能成交或只在 adverse 方向被逆選擇成交。offline「event 後第一根 1m open 成交」系統性高估真實 fill。
3. **成本樂觀**：cost_bps=12 在 cascade 期可達 30-50bp；TP 150bp 看似有餘裕但若成本翻 3-4 倍 + win_rate<57% edge 蒸發。
4. **regime 單向**：樣本（2026-05-11~18）是 bear regime，long-liq 爆量 short-liq 罕見，cross-regime generalization UNVERIFIED。「skew 是真的」≠「fade 這個 skew 賺錢」。
5. **數據點**：唯一 real-PG run = avg_net **−2.45 bps**，已是負，只是 n 不足以統計確認「顯著為負」。

**建議**：A2 維持 observe_more，不投 Stage 1 Demo 資本。若要驗執行可達性，比 Demo 更便宜的做法 = **maker-fill-feasibility 診斷**（量 cascade trigger 後 60s 內 best_bid/ask 是否觸及 PostOnly offset 價位估真實可達 fill rate）。若 cascade 瞬間 maker fill rate < 50%，thesis 在執行層就不成立，省下 Demo 週期。

---

## 對工具的最終裁決

**Runner/adapter 方法論：APPROVE-WITH-CONDITIONS**
- C-1：k_prior ledger 存在性 + count 必須在任何 stage0_ready 宣告前釐清（跑 §4-B）。
- C-2：check 1 (leak) + check 6 (governance) 是 ATTEST，權威 PASS 由 E2 call-path grep 給。
- C-3：runner 必須先在 runtime env（real psycopg2 TCP）端到端跑通一次（§4-A）；當前唯一結果來自 docker-exec-CSV offline harness，非正式 preflight artifact。
- C-4：A2 adapter 路徑未接 `_compute_baseline_lift`；promotion scorecard（SSOT §4）要求 baseline_lift，建議補 BTC/ETH same-window buy-hold / random-entry baseline 對照。

**A2 candidate promotion：REVISE / HOLD（不推進 Stage 1 Demo）** —— 證據 0/3，avg_net 為負，alpha 假設有未解的執行可達性 + regime 單向 + 擁擠度疑慮。

---

需 ssh trade-core 取的 evidence（彙整）：
1. §4-A runtime runner 端到端 → exit code + verdict + k_prior_source + sample_sufficiency。
2. §4-B `learning.strategy_trial_ledger` 存在性 + liquidation-family count。
3. §4-C `pooled_n_eff_breakdown.binding_dimension`（確認 n_eff 是否被 distinct_60min_clusters 卡死）。
