# DSR 閘門修正派工指令（單元 1：核心與凍結身分）

| 項目 | 內容 |
|---|---|
| 文件性質 | 派工指令，不是授權文件。是否可派發，以 [TODO](../../TODO.md) 的 `P1-DSR-GATE-FIX` 列為準 |
| 日期 | 2026-10-19 起草，同日依 QC 與 PA 的審查修訂（Asia/Shanghai） |
| 依據 | Operator 2026-10-19 在對話中選擇「現在修，與 R8 平行」：只改源碼、不部署，部署到 Linux 與否另問。<br>TODO `P1-R8-DSR-GATE-SCALE-CHECK` 的查核結果。<br>QC 的修正規格與 PA 的身分路徑建議，收錄於本文 §2 至 §4 |
| 交付 | `DSR-GATE-FIX-CORE-20261019`（`work_item_id` 與 `lane_id` 都用這個名稱） |
| 不在範圍 | 部署、Linux、資料庫、runtime。<br>單元 2a：Demo 畢業證據改為配置層級，試驗家族的定義由 QC 或 MIT 先預登記。<br>單元 2b：L2 證據的單位契約。<br>單元 2c：殘差 alpha 路徑的呼叫端開始傳入頻率。這會讓殘差報告首次可能判 pass，影響 LG5 實盤候選審查等下游，須另經 Operator 決定。<br>倉庫內其他自行實作的 DSR，例如 `prepilot_gates`、`w2_paper_edge_metrics`。<br>DSR 閾值 0.95 不變 |

## 1. 問題與目標

`program_code/learning_engine/dsr_gate.py` 有兩個錯誤，QC 已以獨立實作重算證實：

1. 預期最大 Sharpe 只回傳標準常態單位的 E[max Z(K)]，沒有乘上試驗 Sharpe 的標準差 √V，門檻比正確值大約 √(T−1) 倍。
2. 傳入 `trial_sharpes` 時，以它們的樣本最大值作門檻；被選者本身在集合內時 DSR 不大於 0.5。

影響：
- **Demo 晉級的選擇偏差證據**：有盈利的策略經此路徑畢業的機率為 0；在各幣皆虧損的情形下，DSR 這個組件可能誤判 promote，但整體畢業仍會被 `min_sharpe` 0.8 等閘門擋下。
- **殘差 alpha 閘門**：恆失敗。
- **L2 顧問執行器**：Sharpe 沒有單位契約。

單元 1 的目標：
- 改正核心公式並建立單位契約。
- 各呼叫端只做機械式、fail-closed 的配合。
- 依 §4 重新觀測學習 runtime 身分。

單元 1 合併之後，在 2a、2b、2c 合併之前，Demo、L2 與殘差三條路徑的判定都不得比現在寬鬆。

## 2. 核心規格（`dsr_gate.py`）

### 2.1 介面

`DsrGate.compute_dsr` 與模組層的 `compute_dsr` 改為只接受關鍵字參數，並刪除既有的預設值：

```python
def compute_dsr(self, *, observed_sharpe: float, n_trials: int,
                n_observations: int, sharpe_frequency_seconds: float,
                skew: float | None, excess_kurtosis: float | None,
                trial_sharpes: Sequence[float] | None = None) -> DsrResult
```

各參數的契約：
- `observed_sharpe`：每期、未年化的 Sharpe，一期的長度為 `sharpe_frequency_seconds`。
- `n_observations`：T，同一頻率下的有效獨立期數，至少 2。
- `sharpe_frequency_seconds`：大於 0 的有限值，否則丟 `ValueError`。
- `skew` 與 `excess_kurtosis`：必填的關鍵字參數，不給就丟 `TypeError`。呼叫端沒有動差時傳 None，核心以 0 計算並記 `moments_assumed_gaussian=True`；
  傳 0.0 代表實測的動差為 0。核心只拒收 None 的頻率。

模組層 `compute_dsr` 依同樣規則轉傳全部參數，另外接受 `threshold` 與 `min_observations`。

保留的行為：
- `min_observations` 守衛：`n_observations` 低於門檻時 `insufficient_observations=True`，`gate()` 判 `defer_data`，優先於其他判決；
- `threshold` 必須在 (0, 1) 之內，`threshold=1.0` 仍丟 `ValueError`。

新增公開的 `compute_psr(*, observed_sharpe, n_observations, skew, excess_kurtosis, min_observations)`：
- 計算 PSR(0)，與頻率無關；分母項不大於 0 時回傳 0.0；`n_observations` 低於 `min_observations` 時回傳 None，與現行行為一致。
- 沒有頻率、只需要 PSR 的呼叫端改用它；不得以假的頻率呼叫 `compute_dsr`。

新增 `sharpe_inputs_from_returns(returns, *, sharpe_frequency_seconds) -> (sr, T, skew, excess_kurtosis)`：
- 動差採母體 z-moments，與 `residual_alpha_gate.py` 現有的算法一致。
- 手上有報酬序列的呼叫端改用它，不再自己傳純量 SR。

年化值誤傳無法用數值檢查擋下：合法的每期值與誤傳的年化值範圍重疊。所以改以契約欄位強制，並在結果中附診斷欄 `implied_annualized_sharpe`，該欄不影響判定。

### 2.2 門檻 SR0

- SR0 = √V × E[max Z(K)]。E[max Z(K)] 保留現有的 Bailey 與 López de Prado 近似，K = 1 時為 0。
- V = max(有限 `trial_sharpes` 的樣本變異數（ddof = 1）, 1 ÷ (T − 1))。有限的 `trial_sharpes` 少於 2 個時，V = 1 ÷ (T − 1)。
- V 用的 T 與計算 PSR 的 T 相同。
- 有限 `trial_sharpes` 的個數大於 `n_trials` 時，丟 `ValueError`：K 必須涵蓋全部已知試驗。
- 刪除以樣本最大值為門檻的分支。`trial_sharpes` 只用來估 V。
- `trial_sharpes` 必須與觀察值同頻率、同一評估協定，由呼叫端負責。

### 2.3 PSR 分母退化

分母項不大於 0 時：
- DSR 與 PSR(0) 都記 0.0；
- `degenerate_moments=True`、`passes_threshold=False`；
- `gate()` 判 `block`。

現行做法回傳 0.5，改掉。

### 2.4 `DsrResult`

- 保留 `trials_max_sharpe` 欄位名，語意改為 SR0（每期單位），並更新說明。
- 新增下列欄位，全部附預設值，接在既有欄位之後：
  - `expected_max_z`
  - `trial_sharpe_variance`（採用的 V）
  - `trial_variance_source`（`"sample"` 或 `"null_floor"`）
  - `n_trial_sharpes`
  - `sharpe_frequency_seconds`
  - `moments_assumed_gaussian`
  - `degenerate_moments`
  - `implied_annualized_sharpe`
  - `dsr_method_version`（值為 `"bldp2014_scaled_v2"`）
- 舊報告沒有 `dsr_method_version`，一律視為舊版、不可信的 DSR。不需要資料庫遷移。

## 3. 呼叫端（單元 1 只做機械式、fail-closed 的配合）

1. **`program_code/learning_engine/promotion_gate.py`**
   - `evaluate` 新增關鍵字參數 `sharpe_frequency_seconds`、`skew`、`excess_kurtosis`，原樣轉傳。
   - `sharpe_frequency_seconds` 可為 None；為 None 時 `skew` 與 `excess_kurtosis` 也可為 None，DSR 組件不計算，判 `defer_data`，理由為 `sharpe_frequency_unavailable`。
     頻率有值時，偏態與峰度依 §2.1 傳入（可為 None，表示假設常態）。核心的 `compute_dsr` 只拒收 None 的頻率。
   - DSR 不計算時，`SelectionBiasPromotionResult.dsr` 為 None：型別改為 Optional，`to_dict` 能輸出 None；
     讀取 `promotion_result['dsr']` 的 `program_code/learning_engine/signal_postmortem.py` 要能處理 None。
   - 其餘複合判定邏輯不變。
2. **`program_code/ml_training/promotion_evidence.py` 與 `control_api_v1/app/promotion_pipeline.py`（Demo 畢業路徑）**
   - 單元 1 傳 `sharpe_frequency_seconds=None`，所以 DSR 組件判 defer。畢業照舊不通過，但理由是誠實的。
   - 時間分桶的日報酬、配置層級的 K 與試驗帳去重，留給單元 2a。
3. **`program_code/learning_engine/residual_alpha_gate.py`**
   - `ResidualAlphaProtocol` 新增 `sharpe_frequency_seconds: float | None = None`；序列化沿用「有設定才輸出」的寫法，使舊報告的雜湊不變。
   - 為 None 時：PSR 以 §2.1 的 `compute_psr` 照常計算（它與頻率無關），DSR 記為 None，報告因 `dsr_*_not_computed` 判 **fail**，與現行結果同屬拒絕。
     不得把 `dsr_*_not_computed` 加進 defer-only 的理由集合：LG5 實盤候選審查會把 defer 與 fail 分開處理，改成 defer 等於放寬。
   - 有值時（本單元的程式內沒有呼叫端會設定，見下）：
     - `trial_sharpes` = [候選本身的 SR] 加上各 peer 在同一驗證窗、同一頻率下的 SR；dsr_raw 用 raw peers，dsr_residual 用 residual peers；
     - K = max(`protocol.n_trials`, 1 + peer 數)，並把實際採用的 K 寫進報告；不得讓 `compute_dsr` 因 K 不足而丟例外，因為 `_psr_dsr_via_gate` 不捕捉例外；
     - T 為驗證桶數；偏態與峰度照舊。
   - 本單元**不**讓任何呼叫端傳入頻率：`program_code/ml_training/residual_alpha_cycle.py` 的 `evaluate_cell`、`program_code/ml_training/residual_alpha_producer_db.py` 的兩個 builder 都維持不傳，
     殘差路徑維持 fail。開始傳入頻率是單元 2c，須另經 Operator 決定。
   - 這樣安排是為了讓三個凍結檔只改一次（身分只移動一次），同時不放寬任何判定。
4. **`control_api_v1/app/l2_ml_advisory_executor.py` 與 `l2_candidate_evidence_adapter.py`**
   - 執行器從 `gate_inputs` 讀取 `oos_sharpe_frequency_seconds`、`oos_skew`、`oos_excess_kurtosis` 三個鍵，原樣傳給 `compute_dsr`。
   - 任一鍵缺少時，DSR stage 判 DEFER，理由為 `oos_sharpe_unit_contract_missing`。
   - adapter 在單元 2b 才填這三個鍵；單元 1 的測試自行帶入，使既有「閾值經真 `compute_dsr` 生效」與「α 下溢會 raise」的突變對照仍有意義。
   - 語意改變：DSR stage 判 DEFER 時，α-wealth 不扣帳（只有 pass 或 fail 才算「已進行」）。L2 目前休眠，影響為零，但這是 FDR 帳務語意的改變，在回報中說明。
   - 完整的單位契約留給單元 2b。

## 4. 學習 runtime 身分：重新觀測

`dsr_gate.py`、`promotion_gate.py` 與 `residual_alpha_gate.py` 都在 `program_code/ml_training/learning_runtime_manifest.py` 的凍結清單中，修改它們會移動 v1 與 v2 的身分摘要。
依 PA 的建議，採「在原 schema 下重新觀測」：
1. 用既有的 builder（`build_source_compatibility_receipt` 與其 v2 版本），在原路徑重新產生 `docs/execution_plan/ai_ml_landing/receipts/S2.2A-source-compatibility-receipt-v1.json` 與 `-v2.json`。
   - `generated_at_utc` 寫重新產生當天（下稱 D）的 UTC 日期，沿用「只到日期」的慣例；不得沿用舊日期。
   - 模組沒有命令列入口：寫一次性的產生腳本，腳本不提交。
   - 序列化固定為 `json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"`，與現有兩份一致。
   - `repo_source_head` 是遙測欄位，寫開工時的 main commit。
   - receipt 最後產生；審查要求修改三個凍結檔時，修完後重新產生。
2. 更新寫死摘要的兩個測試：`program_code/ml_training/tests/test_learning_runtime_manifest.py`（v1）與 `tests/structure/test_learning_runtime_manifest_source_static.py`（v1 與 v2）。
   v1 常數名稱可改為表示「目前審定值」。
3. 把 W5 探針與相關測試中以舊時鐘為基準的時間值，全部移到新 receipt 的到期時刻之後：
   - `program_code/ml_training/aiml_gate_receipt_wave_w5.py` 的 `NOW` 與 `REPRODUCED_AT`；
   - `tests/structure/test_agent_governance_s2_4_acceptance_matrix.py` 的固定時鐘，以及一份已過期 refresh 的 `expires_at`；
   - `tests/structure/test_agent_governance_s2_4_install_w5.py` 的固定時鐘，以及「把觀測窗往前推」的攻擊測試所用的時間值。
   取值規則：
   - 新 receipt 的到期時刻 = D 01:00Z（`generated_at` 加 3600 秒）；
   - `REPRODUCED_AT` = D 01:05:00+00:00，必須嚴格晚於到期時刻；
   - `NOW` = `REPRODUCED_AT` 加 5 分鐘，必須落在 refresh 的 900 秒有效期內；
   - 往前推的觀測窗在新的 `NOW` 時仍須有效，攻擊測試才仍在驗證原本要驗證的情形。
4. 不重新發布 W5 綁定，也不改 `TODO.md` 的 `W5-RECEIPT-BINDING` 標記或 `EXPECTED_SOURCE_HEAD`。這一行由記錄者另記。
   - S2.4 相關的測試以 HEAD 已提交的版本為準，必須在提交之後、工作樹乾淨時執行。提交之前轉紅屬預期，不得以倒填日期或改其他常數的方式消除。
   - 提交之後，若 `tests/structure/test_aiml_w5_receipt_binding_projection.py` 或 `tests/structure/test_aiml_uid_persisted_chain_acceptance.py` 轉紅，停止並回報，不得修改綁定。
5. 回報中列出 v1 與 v2 的新舊摘要。摘要的移動必須可以機械核對，審查不能以重建測試綠燈代替：
   - `capture_contract_digest` 維持不變（目前為 `sha256:1e406a6e4d84e5cecebe565dc1314122f16fae1b13bd1bcf0b4c5cc4a8f397e7`）；它若移動，正式環境的後果是停止資料擷取，不只是隔離 fit；
   - 除 `learning_code_digest` 外，其餘訓練組件的摘要一律不變；
   - `learning_code` 的輸入中，只有三個凍結檔的雜湊改變。

**記錄者的裁定**（PM，未經 Operator 另行確認；記為 DRIFT，待 Operator 確認）：
- `docs/execution_plan/ai_ml_landing/design/S2.4-install-source-seams.md` 中「Original source receipts are immutable and never have their timestamps rewritten」一句，解讀為禁止改寫既有 receipt 的時間戳、讓它看起來仍然新鮮。
- 輸入改變後的重新觀測，是產生一份新的 receipt：新的自我摘要、誠實的日期，舊版本由 git 歷史保存。這是凍結機制設計中預期的做法（測試寫明「改了 allowlisted 檔卻沒重生 receipt」即紅燈）。
  該文件是 Operator 合入的規範文件，§9.2 的措辭另行排程修改。
- 本單元改到 W2 範圍的 `source_static` 測試與 W5 範圍的三個檔案，是綁定 head `6fd4ea73` 之後第一次動到這些範圍。
  S2.4@SOURCE_READY 仍只綁 `6fd4ea73`；任何 S2.4 effect（W6）開工之前，必須在確切的 head 上重新發布 W5 綁定。

## 5. 可改檔案

- **源碼**
  - `program_code/learning_engine/dsr_gate.py`、`promotion_gate.py`、`residual_alpha_gate.py`、`signal_postmortem.py`；
  - `program_code/ml_training/promotion_evidence.py`、`aiml_gate_receipt_wave_w5.py`；
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py`、`l2_ml_advisory_executor.py`、`l2_candidate_evidence_adapter.py`。
- **receipt**：§4 的兩份。
- **測試**
  - `program_code/learning_engine/tests/test_dsr_gate.py`；
  - §4 列出的四個測試檔；
  - 呼叫端的既有測試，只改因介面或公式改變而必須更新的斷言，每一處都在回報中說明：
    - `program_code/learning_engine/tests/` 下的 `test_promotion_gate.py`、`test_residual_alpha_gate.py`、`test_residual_alpha_producer.py`、`test_n_eff_cluster.py`、`test_alpha_wealth_controller.py`；
    - `program_code/ml_training/tests/` 下的 `test_promotion_evidence.py`、`test_residual_hidden_oos_bridge.py`、`test_residual_stage0r_preflight.py`、`test_residual_alpha_report_contract.py`；
    - `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/` 下的 `test_promotion_pipeline.py`、`test_edge_estimator_scheduler_promotion_evidence.py`、`test_l2_p3a_ml_advisory.py`、`test_l2_p4_online_fdr.py`、`test_l2_candidate_evidence_adapter.py`。
- `residual_alpha_producer.py`、`residual_alpha_producer_db.py` 與 `residual_alpha_cycle.py` 不在本單元範圍（見 §3.3）。
- 需要改到清單以外的檔案才能完成時，停止並回報。

## 6. 驗收

### 6.1 固定數值

以下期望值由不引用倉庫模組的獨立實作算出，容差 1e-6（D2 為 1e-12）。

E[max Z(K)] 的值：

| K | E[max Z(K)] |
|---|---|
| 1 | 0 |
| 2 | 0.5197553443 |
| 5 | 1.1925940010 |
| 10 | 1.5745983013 |
| 100 | 2.5306028932 |

**A. 不傳 `trial_sharpes`**（V = 1 ÷ (T − 1)，常態動差）

| K | T | SR | SR0 | DSR | PSR(0) |
|---|---|---|---|---|---|
| 1 | 250 | 0.10 | 0 | 0.942261 | 0.942261 |
| 10 | 50 | 0.20 | 0.224943 | 0.431374 | 0.917158 |
| 10 | 50 | 0.40 | 0.224943 | 0.880829 | 0.996473 |
| 10 | 250 | 0.10 | 0.099786 | 0.501343 | 0.942261 |
| 10 | 250 | 0.20 | 0.099786 | 0.941299 | 0.999111 |
| 10 | 2000 | 0.05 | 0.035218 | 0.745533 | 0.987262 |
| 10 | 2000 | 0.10 | 0.035218 | 0.998069 | — |
| 100 | 50 | 0.40 | 0.361515 | 0.602270 | — |
| 100 | 250 | 0.20 | 0.160370 | 0.732102 | — |
| 100 | 2000 | 0.05 | 0.056600 | 0.384031 | — |
| 100 | 2000 | 0.10 | 0.056600 | 0.973541 | — |

**B. 傳入 `trial_sharpes`**

| 案例 | 輸入 | 期望 |
|---|---|---|
| B1 | trials [0.05, 0.12, 0.30, 0.08]，observed 0.30，K = 4，T = 250 | V 取樣本變異數 0.0125583（大於下限 0.004016）；SR0 = 0.117905；DSR = 0.997530 |
| B4 | trials [0.19, 0.20, 0.195, 0.2, 0.198, 0.201, 0.199, 0.197, 0.2, 0.196]，SR = 0.2，K = 10，T = 500 | 樣本變異數低於下限，V 取下限 0.002004（`null_floor`）；SR0 = 0.070489；DSR = 0.997912 |
| B5 | trials [0.10]，SR = 0.10，K = 10，T = 250 | 只有一個試驗，V 取下限；DSR = 0.501343 |
| B7 | 有限試驗數大於 K | 丟 `ValueError` |

**C. 非常態與退化**

| 案例 | 輸入 | 期望 |
|---|---|---|
| C1 | SR = 0.2，K = 10，T = 250，skew = −1，excess kurtosis = 5 | DSR = 0.919724 |
| C2 | skew = 5，SR = 0.4，K = 10，T = 250（分母項小於 0） | DSR = 0，PSR(0) = 0，`degenerate_moments=True`，判 block |

**D. 反例**

| 案例 | 情境 | 期望 |
|---|---|---|
| D1 | 觀察值本身在試驗集合內（同 B1） | DSR 大於 0.5 |
| D2 | K = 1 | DSR 等於 PSR(0)；SR = 0.1、T = 250 時兩者都是 0.942261266719699 |
| D3 | 合併後全虧損：observed = −0.343，trials [−0.5, −0.5]，K = 2，T = 400 | DSR = 3.93e-13，判 block |

**E. 其他**
- 缺 `sharpe_frequency_seconds`、偏態或峰度時，丟 `TypeError`。
- `threshold=1.0` 仍丟 `ValueError`。
- 模組層 `compute_dsr` 與 `DsrGate` 在相同輸入下結果一致。
- 偏態或峰度傳 None 時，以 0 計算且 `moments_assumed_gaussian=True`；傳 0.0 時該旗標為 False。
- `compute_psr`：與 `compute_dsr` 在 K = 1 時的 PSR(0) 一致；分母項不大於 0 時回傳 0.0；`n_observations` 低於門檻時回傳 None。
- 殘差路徑在頻率為 None 時，PSR 照常算出、DSR 為 None、報告判 fail；理由集合中沒有新增 defer 項。
- 寫一個說明型測試，證明年化值誤傳無法用數值擋下：K = 5、T = 60 時，年化 0.8 誤當每期值傳入，DSR 約 0.99999。

### 6.2 行為

- **Demo 畢業路徑**：DSR 組件判 `defer_data`，理由為 `sharpe_frequency_unavailable`；畢業結果不比現在寬鬆。
- **L2**：DSR stage 判 DEFER，理由為 `oos_sharpe_unit_contract_missing`。
- **殘差 alpha 閘門**：本單元沒有呼叫端傳入頻率，DSR 不計算，報告判 fail，與現行同屬拒絕；PSR 照常計算。
  傳 `n_trials=1` 的呼叫端，今天 DSR 等於 PSR(0)、可能判 pass；本單元之後改判 fail，方向是更嚴。
  有頻率時依正確公式判定的程式路徑，以單元測試直接設定 protocol 驗證。

### 6.3 測試

- §5 列出的全部測試檔都要通過。
- 另外必須通過下列會讀到 receipt、摘要或 W 鏈的測試（S2.4 相關的在提交之後執行，見 §4 第 4 點）：
  - `tests/structure/test_aiml_w5_receipt_binding_projection.py`；
  - `tests/structure/test_aiml_uid_persisted_chain_acceptance.py`（需要完整 git 歷史，淺複製下跑不了）；
  - `tests/structure/test_agent_governance_s2_4_install_w5_emit.py`、`test_agent_governance_s2_4_install_integration.py`、`test_agent_governance_s2_2b.py`；
  - `program_code/ml_training/tests/test_aiml_gate_receipt_validator.py`、`test_aiml_gate_receipt_validator_s2_4.py`、`test_alr_event_consumer.py`、`test_alr_application_identity.py`。
- 再以 CI 治理分片的同一組指令（`.github/workflows/ci.yml` 的 development-agent governance 分片步驟）全量執行一次，並執行 `agent_governance.py validate` 與 `render --check`。
- 回報測試的四個數字（passed／failed／skipped／error），並寫明是受控擷取還是直接執行。本機是 Python 3.10.1，CI 是 3.12，本機通過不等於 CI 通過，回報時註明。

## 7. 共同規則

比照[階段 2 派工指令](2026-10-14--r8-stage2-local-research-dispatch.md) §2，以下列差異為準：

1. 只有一個交付，名稱見表頭。從含本文件的 main 開工，把完整 commit 記下來，task contract 與 context 都綁它。main 上找不到本文件就停止並回報 `NEEDS_CONTEXT`。
2. 這些模組依賴 numpy 與 pandas。實作者那邊的受控測試驗證若缺第三方套件而無法執行，在代碼審查通過之後停止，把提交留在本機分支並回報；獨立測試驗證與發布由記錄者處理。
3. 本機測試在倉庫根目錄以 `/usr/local/bin/python3 -m pytest` 執行（3.10.1，已有 numpy 與 pandas）。
4. 不要碰 `TODO.md`、§4 的兩份 receipt 以外的 `docs/` 檔案，以及 `CHANGELOG.md`。治理源碼、准入帳本、租約與審查狀態檔一律不碰，§5 明列的檔案除外。
5. 不連 Linux、資料庫、Demo 或 live；不部署。新增的註釋用中文；不寫入本機絕對路徑。
6. `l2_ml_advisory_executor.py`（2063 行）與 `tests/structure/test_agent_governance_s2_4_install_w5.py`（2001 行）已超過 2000 行且不在例外登記表內：改動不得讓它們變得更長；做不到時停止並回報。
7. 計時器與交付方式同 §2.4 與 §2.6；PR 標題以 `DSR gate fix core` 開頭。

## 8. 回報

用中文一次回報，內容包括：
- 一張總表：`work_status`、`gate_verdict`、`disposition`，以及本機分支與 commit，或停止原因；
- 與本指令的偏差；
- v1 與 v2 摘要的新值與舊值；
- 每一處既有測試斷言修改的理由；
- 測試的四個數字；
- 未驗證的範圍；
- 計時器與工時。
