# 2026-06-04 Alpha-Edge 改進實現方案派發綜合

角色：PM
範圍：結合 Claude 記憶、PM second-pass 報告、QC/MIT/PA/BB/CC 子 agent 調研結果，形成後續可派工實現方案。
狀態：方案與派工綜合；本輪未改交易代碼、未改策略/風控配置、未改 DB、未觸碰 runtime/auth/order path。

## 派發記錄

本輪依 repo dispatch 規則綁定角色，不使用匿名 worker 身份：

| 角色 | agent id | nickname | 範圍 | 輸出狀態 |
|---|---|---|---|---|
| `QC(default)` | `019e9012-7792-7182-afc9-db03c9ae3e13` | Pauli | residual alpha / DSR/PBO/CPCV / hidden OOS gate | 完成 |
| `MIT(default)` | `019e9012-77cd-7dc3-9839-8d6ced1c98cc` | Nash | data/schema/evidence lineage / PIT / regime leak | 完成 |
| `PA(default)` | `019e9012-780d-7bc1-96ec-b3063154d840` | Leibniz | Module / Interface / implementation architecture | 完成 |
| `BB(default)` | `019e9012-78ae-7ea1-b5bb-eafb26f1ba31` | Mill | Bybit `orderLinkId` / RevolutX portable lesson | 完成 |
| `CC(default)` | `019e9012-78e6-7a72-9fb6-0482af693b7b` | Franklin | root-principle / hard-boundary review | 完成 |

跳過 `AI-E(default)`：本輪不是模型成本、模型路由或 token economics 問題。
跳過 `FA(default)`：本輪先做實現方案收斂；正式 P1 manifest / promotion policy 改動前再補 FA functional gap audit。

## 最終裁決

我同意五個 agent 的共同結論：不要先做 QuantaAlpha 式大 DSL，也不要把 P0 縮成一個 `R_beta` 欄位。正確的最小方案是建立一個小而深的 evidence gate，把 `SignalSpec`、PIT lineage、regime classifier、residual beta、hidden OOS、promotion evidence、live-candidate lineage 串成同一個可強制執行的 Interface。

TradeBot 已經有不少可用 Module：17 維 edge feature vector 存在於 `rust/openclaw_engine/src/edge_predictor/features.rs:74`，runtime builder 也會組 funding / basis / orderbook imbalance / spread，見 `rust/openclaw_engine/src/edge_predictor/feature_builder.rs:55`。但 alpha 證據鏈目前缺一個統一 enforcement seam。現有 DSR/PBO/promotion tooling 不能替代 residual alpha gate，因為它主要吃 raw return series，且不強制 BTC/market residual evidence。

因此主線優先級調整為：

1. `P0-A` 先修已知 leak：multiday trend 全樣本 volatility tercile。
2. `P0-B` 建 residual alpha 純數學 Module。
3. `P0-C` 把 residual evidence 接成 demo promotion 和 LG-5 live-candidate 的 blocking gate。
4. `P1` 再做 `SignalSpec` / `EvidenceManifest` / hidden OOS registry / lineage downgrade。
5. `P2` 才做 `orderLinkId` hardening、postmortem cost-defeat、AST duplicate/complexity checks。

## P0-A：先修 Regime Leak

目標：把已知錯誤從 research harness 中移除，避免後續 residual gate 繼承錯誤標籤。

修改範圍：

- `helper_scripts/research/multiday_trend_diagnostic/data_loader.py`
- 對應測試，優先新增或擴展 `helper_scripts/research/tests/` 下的 multiday trend diagnostic 測試。

現狀問題：

- `helper_scripts/research/multiday_trend_diagnostic/data_loader.py:296` 使用 full-sample `np.quantile(finite_vols, 2/3)` 決定歷史高波動 regime，未來 volatility distribution 會影響過去 label。
- funding tilt 已有可復用的 prior-window 寫法：`helper_scripts/research/funding_tilt_diagnostic/data_loader.py:379` 與 `:407`。

驗收：

- 在序列尾部追加未來高波動資料，不得改變早期 regime label。
- 只用當前 index 之前的 finite rolling volatility，最少 prior 樣本不足時回 neutral / unknown，不偷看未來。
- 舊 multiday trend 結果在修復前一律標 `research_only`，不得作 promotion evidence。

建議派工鏈：

`PM -> PA -> E1(worker) -> E2(explorer) -> E4(worker) -> QC/MIT -> PM`

## P0-B：Residual Alpha Core

我採納 PA 的 Module 放置建議：核心純數學放在 `program_code/learning_engine/`，因為現有 `dsr_gate.py`、`pbo_gate.py`、`promotion_gate.py` 都在這個 evidence/gate 層；`program_code/ml_training/` 只做 adapter。

新增 Module：

- `program_code/learning_engine/residual_alpha_gate.py`

建議 Interface：

```python
ResidualAlphaGate.evaluate(
    candidate_returns,
    factor_panel,
    protocol,
) -> ResidualEdgeReport
```

`ResidualEdgeReport` 至少包含：

- `raw_mean_bps`
- `residual_mean_bps`
- `r_beta_retention = residual_mean_bps / raw_mean_bps`
- `beta_edge_share = (raw_mean_bps - residual_mean_bps) / abs(raw_mean_bps)`
- `beta_loadings`
- `r_squared`
- `factor_panel_hash`
- `fit_window`
- `coverage`
- `psr_raw` / `psr_residual`
- `dsr_raw` / `dsr_residual`
- `pbo_raw` / `pbo_residual`
- `verdict`
- `reasons`

Factor 最低要求：

- BTCUSDT return。
- PIT universe 等權 market return。
- 可選 sector / cluster / PC1，但 PC1/PCA 必須 train-only，不能 full-sample。

Fail 條件：

- raw mean positive 但 residual mean <= 0。
- `r_beta_retention < 0.5`。
- `beta_edge_share > 0.5`。
- residual PSR/DSR 不過門檻。
- PBO >= 0.5。
- PBO/DSR underpowered：對 promotion/live candidate 是 defer，不是 pass。
- factor coverage 不足或非 PIT aligned：`pending_schema` / `research_only`，不能 pass。

驗收測試：

- beta trap synthetic：`returns = beta * BTC + noise`，raw PSR/DSR 可以 pass，但 residual 必須 fail。
- true alpha synthetic：`returns = alpha + beta * BTC + noise`，residual pass 才允許 pass。
- leakage bite：未來 BTC shock 不得改變歷史 beta/residual。
- factor panel hash / fit window 變動會改變 report hash。

## P0-C：接入 Promotion 與 LG-5

這一段是 P0 真正有殺傷力的地方。若只生成 JSON artifact 而不接入 gate，仍然會被現有流程繞過。

接入點：

- `program_code/ml_training/promotion_evidence.py:126`：目前從 `raw_bps_series` 建 selection/tail evidence。應在這裡加入 residual returns，讓 DSR/PBO 同時跑 raw 與 residual。
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py:185`：`PipelineEntry` 目前有 `demo_selection_bias_report` / `demo_tail_risk_report`，應增加 `demo_residual_beta_report`。
- `program_code/ml_training/mlde_demo_applier.py:476`：`should_create_live_candidate` 目前主要看 expected/confidence/sample，應要求 `EvidenceManifest.verdict == promotion_ready` 且 residual gate pass。
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub_live_candidate_review.py:95`：目前期待 `live_candidate_eval_v1`。建議 bump `live_candidate_eval_v2`，缺 residual block 直接 reject/defer。

硬規則：

- `R_beta` 不可模仿 R4 的 informational skip。`governance_hub_live_candidate_review.py:995` 附近 R4 在 `K<5` 會 skip，`R_beta` 不能 skip-pass。
- `live_candidate_eval_v1` 或 v2 缺 residual block 不得 approve。
- raw pass / residual fail 必須 block。

可能需要 migration：

- 若 `promotion_pipeline` DB 表需要持久化 `demo_residual_beta_report`，應用 V128+ migration，且按 repo 規則先 Linux PG dry-run / double-apply / sqlx checksum。
- 若先不改 DB，可先把 residual report 作為 `promotion_evidence` artifact + payload hash，但 live candidate gate 仍要能讀到並 fail-closed。

## P1：SignalSpec / EvidenceManifest / Hidden OOS

不要先建 expression DSL。第一版 `SignalSpec` 只做 metadata contract 和 lineage。

建議新增 Module：

- `program_code/ml_training/candidate_evidence_manifest.py`

`SignalSpec` 最小欄位：

- `schema_version`
- `candidate_id`
- `family_id`
- `hypothesis`
- `horizon`
- `inputs`
- `pit_contract`
- `universe_ref`
- `regime_ref`
- `feature_schema`
- `cost_model_ref`
- `residualization`
- `failure_taxonomy`
- `hidden_oos_policy`

`EvidenceManifest` 最小欄位：

- `candidate_id / family_id / spec_hash`
- train / validation / hidden OOS window
- embargo / purge
- K trials
- raw and residual PSR/DSR/PBO
- net-of-cost bps
- PIT universe digest
- V125 history run lineage
- V127 regime label lineage
- artifact digests
- promotion decision

Hidden OOS 具體問題：

- V049 `replay.experiments` 有 train/OOS/candidate/embargo/K 欄位，但 register helper 目前會寫 NULL，見 `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/experiment_registry.py:1186`。
- 所以不能把「V049 存在」等同於 hidden OOS protocol 已落地。

建議：

- 短期：用 `EvidenceManifest` 強制記錄 hidden OOS split 和 `family_id`，manifest hash 包含 split。
- 中期：修 `experiment_registry.py` 的 alpha path，對 alpha candidate family 禁止 NULL train/candidate/OOS/embargo/K。
- 長期：如 V049 狀態欄不足，新增 alpha-specific OOS registry，記錄 `sealed/opened/consumed/invalidated`、`open_count`、`opened_by_role`。

Fail / downgrade 規則：

- hidden OOS 被打開後同一 family 不能再迭代使用。
- spec hash 變更後不能復用舊 hidden OOS result。
- family rename 不能重置 OOS；需要 family fingerprint。

## P1：Evidence Lineage Downgrade

`mlde_demo_applier_evidence_filter.py` 的 legacy fallback 可保留，因為它是兼容 Adapter。但 promotion-ready verdict 不能依賴這種 fallback。

現有風險：

- 缺 `evidence_source_tier` 時回空 filter：`program_code/ml_training/mlde_demo_applier_evidence_filter.py:210`。
- 部分 replay schema 時降到 FK-only：`program_code/ml_training/mlde_demo_applier_evidence_filter.py:252`。
- 缺 `replay_experiment_id` 時跳過 Block B：`program_code/ml_training/mlde_demo_applier_evidence_filter.py:271`。

建議：

- generic filter 保持 backward-compatible，不直接破壞舊資料讀取。
- `EvidenceManifest` 層對 missing lineage 統一輸出 `pending_schema` / `research_only`。
- `mlde_demo_applier.py` 和 live candidate payload 只接受 `promotion_ready`。

## P2：Bybit orderLinkId Hardening

這不是 P0。BB 和 CC 都指出：Rust 熱路徑多數已經有 `oc_*` id，真正缺口在底層兜底和 duplicate classifier。

關鍵事實：

- `OrderDispatchRequest.order_link_id` 是必填 String：`rust/openclaw_engine/src/tick_pipeline/mod.rs:748`。
- open primary 已生成 `oc_{mode}_{ts}_{seq}`：`rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:659`。
- 底層 `CreateOrderRequest.order_link_id` 仍 optional：`rust/openclaw_engine/src/order_manager.rs:123`。
- `OrderManager::place_order()` 只在 Some 時送出：`rust/openclaw_engine/src/order_manager.rs:387`。
- Python client 同樣 optional：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py:890`。

設計裁決：

- 不要照搬 Revolut X，在 REST client / HTTP attempt 裡缺了就 UUID。
- 應在 dispatch / intent 邊界一次性生成並驗證，把同一個 id 帶入所有 retry attempt。
- 不得因 `orderLinkId` 恢復 hidden open-order retry。`event_consumer/dispatch.rs` 已明確 open create 0 retry，這個邊界不動。

格式建議：

`oc_{em}_{kk}_{t36}_{s36}_{h6}`

- `em`: `dm|ld|lv`
- `kk`: `op|cl|mf|ic|rk`
- `t36`: ms timestamp base36
- `s36`: per-engine seq base36
- `h6`: symbol/strategy/lease hash

額外修正：

- Bybit `110072 OrderLinkedID is duplicate` 應納入「同一 pending dispatch id」的 duplicate/no-op 判斷。
- 不能把任意歷史 collision 當成功。
- closed PnL fallback 目前只認 `oc_dm` / `oc_ld` 前綴，改格式需同步測試 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/closed_pnl_pagination.py:39`。

## P2：Postmortem / Cost-Defeat

建議新增：

- `program_code/learning_engine/signal_postmortem.py`

Interface：

```python
class SignalPostmortem:
    failure_taxonomy: Literal[
        "no_edge",
        "beta_edge",
        "cost_defeat",
        "fill_failure",
        "regime_only",
        "sample_insufficient",
        "data_leak",
        "implementation_bug",
    ]
```

硬邊界：

- 可影響 research scheduler、proposal prior、postmortem 報告。
- 不得直接改 live weights、live config、strategy/risk TOML。
- 接 scheduling/weights 前必須過 attribution-chain / evidence manifest。

## P2/P3：AST / Complexity / Duplicate Checks

這是 QuantaAlpha/AlphaAgent 最值得借的工程模式，但必須在 `SignalSpec` 穩定後做。

第一版只做：

- allowed fields / operators。
- max depth。
- duplicate fingerprint。
- complexity budget。
- hypothesis-code alignment。

不做：

- broad expression DSL。
- automatic mutation/crossover。
- 直接 promotion verdict。

## 明確不做

- 不把 `R_beta` 放進 Rust order/risk hot path。
- 不讓 SignalSpec / AST checker 直接生成 order、Decision Lease、GuardianVerdict 或 ExecutionPlan。
- 不重開 paper promotion。
- 不把 live_demo 當 promotion lane。
- 不用 hidden OOS 反覆調參。
- 不把 missing evidence schema 視為正常 promotion。
- 不把 `orderLinkId` 當 retry 許可。

## 建議下一步派工

最小實作順序：

1. `P0-A-REGIME-LEAK-FIX`
   鏈：`PM -> PA -> E1 -> E2 -> E4 -> QC/MIT -> PM`
   範圍：`multiday_trend_diagnostic/data_loader.py` + regression test。

2. `P0-B-RESIDUAL-ALPHA-GATE-CORE`
   鏈：`PM -> QC -> MIT -> PA -> E1 -> E2 -> E4 -> QA -> PM`
   範圍：`program_code/learning_engine/residual_alpha_gate.py` + unit tests。

3. `P0-C-PROMOTION-LG5-RESIDUAL-GATE`
   鏈：`PM -> CC -> FA -> PA -> E1 -> E2 -> E4 -> QA -> PM`
   範圍：`promotion_evidence.py`、`promotion_pipeline.py`、`mlde_demo_applier.py`、`governance_hub_live_candidate_review.py`，如需持久化則加 V128+ migration。

4. `P1-SIGNALSPEC-EVIDENCE-MANIFEST`
   鏈：`PM -> CC -> FA -> PA -> E1 -> E2 -> QA -> PM`
   範圍：`candidate_evidence_manifest.py`、hidden OOS contract、lineage downgrade。

5. `P2-ORDERLINKID-HARDENING`
   鏈：`PM -> PA -> BB -> E1 -> E2 -> E4 -> QA -> PM`
   範圍：Rust dispatch id helper、duplicate code `110072` classifier、Python parity tests、Bybit reference update。

我的建議是先派 `P0-A` 和 `P0-B`，不要同時開 `P0-C`。`P0-C` 會碰 promotion/live-candidate gate 和可能的 migration，需要等 residual core 的 report schema 固定後再做，否則會反覆改接口。

## 本輪已完成的記憶修正

已更新 `.codex/MEMORY.md`：Codex 的文檔、報告、實施筆記、代碼注釋默認中文優先；除非 operator 明確要求英文、文件本身已鎖定英文、或需要保留精確 API / protocol wording。

已更新 `.codex/WORKLOG.md`：記錄本次 `QC/MIT/PA/BB/CC` 派發鏈與 investigation-only 邊界。

## 首批實作驗收

狀態：`P0-A` 與 `P0-B` 首批 checkpoint 已完成，驗收結論為 `ACCEPT_WITH_RISK`。

實作範圍：

- `P0-A-REGIME-LEAK-FIX`：`helper_scripts/research/multiday_trend_diagnostic/data_loader.py` 改為 expanding/prior-365 volatility tercile；新增 append future extreme vol 不改 prefix regime 的回歸測試。
- `P0-B-RESIDUAL-ALPHA-GATE-CORE`：新增 `program_code/learning_engine/residual_alpha_gate.py` 與聚焦測試，提供純離線 residual alpha gate，輸出 raw/residual mean、beta retention、beta edge share、PSR/DSR/PBO 欄位、coverage、fit window、factor hash、verdict/reasons。

驗收鏈：

- `E1(worker)=Anscombe`：完成 `P0-A` regime leak fix。
- `E1a(worker)=Huygens`：完成 `P0-B` 初版 core。
- `E2(explorer)=Kuhn`：接受 `P0-A`，退回 `P0-B` 初版。
- `E1a(worker)=Bohr`：修 `P0-B` first E2 blockers。
- `E2(explorer)=Banach`：再次退回 `P0-B`，指出 PBO peer input 未套 eval window。
- `E1a(worker)=Jason`：修 PBO peer eval-window scope。
- `E2(explorer)=Euclid`：`ACCEPT_WITH_RISK`，無 blocker。
- `E4(worker)=Hilbert`：只讀驗證 PASS。

已驗證的 P0-B blocker：

- eval_end 後 candidate/factor future rows 不改 report。
- eval_end 後 timestamped PBO peer future valid / NaN / invalid row 不改 report。
- report 顯式包含 `psr_raw` / `psr_residual` / `dsr_raw` / `dsr_residual` / `pbo_raw` / `pbo_residual`。
- default missing PBO 為 `defer_data`，不得 pass。
- duplicate factor timestamp 與 invalid fit window fail-closed。
- 無 timestamp 的純 numeric PBO peer sequence 仍要求長度等於 eval window。

驗證命令：

- `python3 -m pytest helper_scripts/research/tests/test_multiday_trend_diagnostic.py -q` → `37 passed`
- `python3 -m pytest program_code/learning_engine/tests/test_residual_alpha_gate.py -q` → `14 passed`
- `python3 -m pytest program_code/learning_engine/tests -q` → `178 passed`
- `python3 -m py_compile program_code/learning_engine/residual_alpha_gate.py helper_scripts/research/multiday_trend_diagnostic/data_loader.py` → PASS
- 直接 `awk` 掃描 P0-A/P0-B 文件、`.codex/MEMORY.md`、`.codex/WORKLOG.md` 尾隨空白 → PASS

保留風險：

- `P0-B` 只可視為 core diagnostic，不可宣稱完整 promotion gate。
- PBO 目前是 peer mean rank 近似，residual peer 使用同一 eval factor path / candidate beta proxy，不是正式 CPCV / peer-specific beta。
- DSR 目前是簡化 deflation，不是完整統計證據。
- `allow_missing_pbo_for_core_tests=True` 只能用於 core/unit diagnostic；後續 `P0-C` 必須在 production promotion path 禁用或 fail-closed。
- `residual_alpha_gate.py` 目前 931 行，未超 2000 hard cap，但後續可拆出 stats/PBO helper 降低審查負擔。

因此下一批不應直接把 `P0-B` 當 promotion-ready，而應先做 `P0-C` 的 fail-closed 接入：promotion/live-candidate caller 必須拒絕缺 residual block、缺 PBO evidence、或任何 `core_diagnostic_only` 旁路。
