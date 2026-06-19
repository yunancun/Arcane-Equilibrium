# Alpha Discovery Throughput 1-6 工程計劃

日期：2026-06-19
角色：PM local synthesis（未 spawn subagent；本輪使用本地綁定角色視角完成審核）
範圍：artifact-only / read-only alpha discovery 基建；不改 live gate、不改 Rust 下單權威、不部署、不重啟。

## 0. 事實、推論、假設

事實：
- `TODO.md` v227 顯示 Gate-B latest = `WATCH_ONLY`，FlashDip demo pilot 仍為 DB 級零樣本。
- AEG/ADR-0047 要求 regime、breadth、freshness、survivorship、execution realism、統計 gate 同時成立。
- 現有 `aeg_s3_candidate_rows`、`aeg_candidate_metrics`、`aeg_execution_realism`、`aeg_robustness_matrix` 已有強 gate，但候選 producer 仍要知道太多 gate 欄位。
- `candidate_signal_spec.py` / `candidate_evidence_manifest.py` 已有 manifest/SignalSpec 驗證器，但尚未成為 AEG research producer 的小 Interface。

推論：
- 當前瓶頸不是 gate 太嚴，而是 discovery throughput 低：候選接入成本高、execution realism upstream 分散、低頻事件等待時間長、AEG verdict 到 Rust edge snapshot 的語義轉換不集中。

假設：
- 本批先做 artifact-only Module 和 focused tests，允許後續再接 cron / Linux read-only runner。
- 本批不處理既有 dirty WIP 的 owner 問題，不覆蓋未追蹤 ADPE/recorder/VRP 等文件。

## 1. 落地 1：Alpha Candidate Packet Module

目标：把候選 producer 的 Interface 收斂為「最小事件/收益 panel」，由一個 Module 生成 `aeg_s3_candidate_rows` 可消費的 evidence。

預計文件：
- `helper_scripts/research/alpha_discovery_throughput/packet.py`
- `helper_scripts/research/tests/test_alpha_discovery_throughput.py`

Interface：
- input：候選 metadata、sample rows、daily returns、PBO candidates、可選 SignalSpec。
- output：標準 candidate evidence dict，並可直接餵入 `aeg_s3_candidate_rows.builder.build_direct_report`。

驗收：
- 完整 packet 可生成 direct report，且被 `aeg_candidate_metrics` 消費。
- 缺 daily returns / independence bucket / PBO 時仍沿用既有 fail-closed 行為，不合成假序列。
- Module 不讀 DB、不連 Bybit、不碰 runtime/trading path。

## 2. 落地 2：Execution Realism Spine

目标：把微結構 observation rows 統一轉為 `aeg_execution_realism` input，先計算 maker fill、adverse selection、latency、participation、capacity，再交既有 gate 重算 PASS/FAIL。

預計文件：
- `helper_scripts/research/alpha_discovery_throughput/execution_spine.py`

Interface：
- input：observation rows（fill/not fill、adverse bps、latency ms、participation、capacity、fee/cost metadata）。
- output：`aeg_execution_realism.builder.evaluate` 的標準 payload。

驗收：
- n<30、maker fill<0.60、adverse p95>3.5 會 fail-closed。
- 正常 maker observation 能得到 PASS 與 round-trip p95 cost。

## 3. 落地 3：多臂 Discovery Loop

目标：把 Gate-B、funding/OI、VRP/vol-event、scanner shadow、FlashDip counterfactual 等 discovery arm 用同一個 read-only scheduler 評估：RUN / WAIT / BLOCK / READY_FOR_AEG_CHAIN。

預計文件：
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`

Interface：
- input：arm 狀態列表與 gate counters。
- output：排序後 action plan / killboard summary。

驗收：
- `WATCH_ONLY` Gate-B 會 WAIT，不啟 probe。
- 樣本足夠且 artifacts ready 的 arm 會 READY_FOR_AEG_CHAIN。
- 所有 action 都是 artifact-only recommendation，不直接跑交易或 mutate runtime。

## 4. 落地 4：AEG Verdict -> Edge Snapshot Adapter

目标：把 robustness matrix durable verdict 轉成 Rust `edge_estimates_live_demo.json` 可讀 shape，但只有通過 AEG gate 的 row 才產生 positive runtime cell。

預計文件：
- `helper_scripts/research/alpha_discovery_throughput/edge_snapshot_adapter.py`

Interface：
- input：`verdict_matrix` rows / summary。
- output：edge snapshot dict，cell key = `strategy_family::symbol_or_aggregate`，含 `runtime_bps`、`validation_passed`、`validation_reason`、`n`、`win_rate`、`std_bps`、`_meta.updated_at`。

驗收：
- durable-alpha candidate 才 `validation_passed=true` 且 positive `runtime_bps`。
- 非 durable row 寫 0 runtime 或不寫 positive cell，避免 research-positive 誤入 Rust cost gate。
- `_meta.updated_at` 必有，讓 Rust freshness gate 可判定。

## 5. 落地 5：最小 Hypothesis / SignalSpec Manifest

目标：復用現有 `candidate_signal_spec.py`，讓 AEG producer 在 packet 入口先驗 SignalSpec，而不是等 promotion 時才發現 schema/lineage 不足。

預計文件：
- `helper_scripts/research/alpha_discovery_throughput/signal_manifest.py`

Interface：
- input：最小 hypothesis manifest fields。
- output：canonical `signal_spec` + hash + validation result。

驗收：
- valid manifest 通過現有 validator。
- PIT future-data allowed、缺 residualization、缺 hidden-OOS policy 會 fail-closed。

## 6. 落地 6：FlashDip Counterfactual Ladder

目标：不改 `flash_dip_buy` 交易邏輯，新增 read-only counterfactual ladder builder：K=5/10/15/20/25 生成「若掛單」事件樣本，用來累積 near-miss / death-rate / markout evidence。

預計文件：
- `helper_scripts/research/alpha_discovery_throughput/flash_dip_ladder.py`

Interface：
- input：daily close 與 subsequent low/close rows，symbol/regime/date。
- output：candidate packet samples，sample_unit=`flash_dip_counterfactual_ladder`。

驗收：
- 不下單、不讀 secrets、不改 strategy config。
- 對每個 K 產生獨立 parameter cell / independence bucket。
- gross/cost/net 清楚標記 counterfactual，不可自動 promotion。

## 7. 三輪對抗性審核

### Round 1：CC(default) / FA(default) / PA(default)

攻擊：
- 可能把 research artifact 誤接成 live authority。
- 可能把 Module 做成 pass-through，沒有真正增加 Depth。
- 可能重複既有 SignalSpec / EvidenceManifest，增加兩套 truth。

裁決：
- 本批所有 Module 必須 artifact-only，static tests 禁 `psycopg2`、`asyncpg`、`INSERT/UPDATE/DELETE`、`OPENCLAW_ALLOW_MAINNET`、`execution_authority`。
- Packet Module 必須以現有 AEG builders 為 downstream，不重新定義 promotion gate。
- SignalManifest 只做 Adapter，復用 `candidate_signal_spec.py`。

### Round 2：QC(default) / MIT(default) / AI-E(default)

攻擊：
- 多臂 discovery loop 可能鼓勵 p-hacking。
- FlashDip ladder 是 counterfactual，不能作 demo/live promotion evidence。
- Edge snapshot adapter 可能把 aggregate row 或 bull-only row 轉成 positive edge。

裁決：
- Discovery loop 只輸出 action/killboard，不輸出 promotion verdict。
- FlashDip ladder samples 必須標記 `evidence_tier=counterfactual_replay` / `promotion_blocker=counterfactual_only`。
- Edge snapshot adapter 只接受 `final_label == durable-alpha candidate` 且 `non_bull_independent_pass` / regime slice 過關的 row；aggregate row 不 promotion。

### Round 3：E2(explorer) / E4(worker) / QA(worker)

攻擊：
- 新 package 可能破壞 import path 或測試環境。
- execution p95 / quantile 計算可能因小樣本或空值 fail-open。
- compact 後可能忘記更新 script index / focused tests。

裁決：
- 新增單一 focused test file 覆蓋 1-6。
- Quantile 空值 / 小樣本一律產 fail-closed payload。
- 更新 `helper_scripts/SCRIPT_INDEX.md` 2026-06-19 section。

## 8. Compact 後恢復 Checklist

1. 先看本文件。
2. 僅新增/修改：
   - `helper_scripts/research/alpha_discovery_throughput/*`
   - `helper_scripts/research/tests/test_alpha_discovery_throughput.py`
   - `helper_scripts/SCRIPT_INDEX.md`
3. 不碰既有 dirty WIP。
4. Focused verification：
   - `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py`
   - 若 import path 需要，沿用 `helper_scripts/research/tests/conftest.py`。
5. 本批不 deploy、不 rebuild、不 restart、不 Linux PG write、不 Bybit private call。

