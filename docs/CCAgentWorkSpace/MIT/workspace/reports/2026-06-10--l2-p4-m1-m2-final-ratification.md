# MIT Verdict — L2 Mesh P4 online-FDR loop：M1+M2 Final Ratification（7 項裁決）

日期：2026-06-10 ｜ 作者：MIT ｜ 落盤：PM 主會話代行（MIT 任務無寫檔權限）
審計對象：`feat/l2-p4-design:docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--l2-p4-online-fdr-design.md`（421 行 SSOT）對照 `L2_TODO.md` §4 P4 / §5 ENDORSED 邊界 + main 工作樹代碼親驗。

## 0. Grounding 抽查（4 項材料性事實，全部親驗）

| 設計聲明 | 親驗結果 | 判定 |
|---|---|---|
| `dsr_gate.py:520-535` 模組級 `compute_dsr` 的 `n_trials`/`threshold` 可注入 | `dsr_gate.py:520-527`：`compute_dsr(observed_sharpe, n_trials, n_observations=100, threshold=DEFAULT_DSR_THRESHOLD, ...)` — threshold 確為模組級參數；`:373` 驗 `0<threshold<1`；`:76` `DEFAULT_DSR_THRESHOLD=0.95` | **MATCH** — Option B「零 dsr_gate 改動」前提成立 |
| `l2_candidate_evidence_adapter.py:145-148` `n_trials ← k_trials` 接縫 | `:146` `gi["n_trials"] = _int_or_none(row.get("k_trials"))` + 缺值 DEFER reason | **MATCH** |
| `pbo_gate.py` hand-rolled 無 scipy 慣例 | `:20,:36` "Hand-rolled CSCV (no scipy dependency)" 明文 | **MATCH** — n_eff_cluster 同款先例成立 |
| `l2_ml_advisory_executor.py:993-1067` math gate strictest-wins 序 | `:993-1067` Q1→DSR→PBO→B1→leak；`:1160-1167` `_strictest_math_verdict` any-fail→fail / any-DEFER→DEFER / else pass | **MATCH，但有一處 doc-impl 差異**（材料性，影響 #3）：`:1003` docstring 聲稱 "short-circuit on first DEFER/fail"，**實作無 short-circuit — 五 stage 全跑**。後果：`stage_verdicts["dsr"]` 可以是 pass/fail 而 overall=DEFER（如 single-config PBO honest-DEFER）。此事實是 #3 裁決的核心依據。 |

## 1. 核心數學定理（自含推導；多項裁決引用）

設 family 內每次「被計入」的 test i 以可預測（predictable）水準 α_i 進行（Option B 使 DSR test 的條件 type-I ≤ α_i 成立，前提 = Bailey–López de Prado DSR 在 null 下近似校準）。φ=1.0 refund 只在 demo-confirmed（confirmed ⊂ discoveries），則：

- **淨支出恆等式**：未獲 refund 的 Σα_i ≤ W_0（wealth 不可負 + refund 恰補回已扣額 ⇒ W_t ≤ W_0 恆成立——**wealth 永不超過初始值**）。
- **E[V_f] ≤ E[Σ_conducted α_i] ≤ W_0 + cap·E[C_f]**（C_f = confirmed discoveries ≤ R_f）。
- ⇒ 每 family **mFDR_{η=1} = E[V]/(E[R]+1) ≤ max(W_0, cap) = 0.1·α_target = 0.005**——比 target 多 10 倍 margin。此為 Foster & Stine (2008) alpha-investing mFDR 控制的直接版本；refund-on-confirm 比文獻標準 reward-on-rejection（Aharoni & Rosset 2014 GAI；Ramdas et al. 2017 LORD++/GAI++）**嚴格更保守**（payout 是 rejection 事件的子事件且 ψ=φ ≤ GAI payout cap，supermartingale 論證逐路徑成立）。
- **跨 family 聚合**（Foster–Stine multiple-streams 可加性）：E[V_total] ≤ N_fam·W_0 + cap·E[R_total] ⇒ 全域 mFDR_{η=N_fam} ≤ 0.1·α_target；**分母取 1 的全域 mFDR ≤ α_target 成立條件 = N_fam ≤ 1/γ = 10**（見 NOTE 區 4a）。

定理成立的三個前提：(a) α_i 在 test 前由 PG balance 決定（predictable ✓ STAGE 3.7 先於 STAGE 4）；(b) DSR null 校準近似成立（fat-tail/相依下為近似，由 N_eff、HAC、strictest-wins 多閘墊保守，confidence MED-HIGH）；(c) **每次被執行的 test 都被 debit** —— 前提 (c) 在設計現狀有一個洞，即 #3 的 MODIFY。

## 2. 七項逐項裁決

### #1 α_i spend 序列 `α_i = min(0.10·W_t, cap)` — **APPROVE-with-NOTE**（confidence HIGH）

固定比例 spend 是合法 GAI spending rule（任何 predictable α_t ≤ W_t 保持帳本不變量；Foster & Stine 2008 §4 例示比例型 spend）。幾何衰減軌跡 W_t = W_0·0.9^t（連跌時）使 Σα_i ≤ W_0 自動成立 = FDR budget 封頂的機制本體；refund 補血只發生在 confirmed discovery，不引入超額 wealth（W_t ≤ W_0 恆真）。保守方向 ✓。

NOTE（三點，皆非阻斷）：
- **(1a)** 在 φ=1.0 + W_0=0.005 + spend=0.10 下 **α_i ≤ 5e-4 恆成立，#7 的 cap=0.005 永不 binding**（binding 需 W_t > 0.05，唯 operator_adjustment 可達）——cap 是 defense-in-depth，operative constraint 是 spend_fraction。文檔須明示，防止誤把 cap 當有效約束。
- **(1b)** **無有限 α-death**：W−α_i = 0.9·W > 0 恆真 ⇒ `can_test` 永真、`alpha_wealth_exhausted` DEFER 結構性不可達；family 連跌後 α_i→0、threshold→1，變成「永遠可測但永遠不可能 pass」的殭屍態。建議 `assign_alpha_i` 加數值 floor（如 α_i < 1e-6 → return None ⇒ slot 不可測），一併解 (7c) 的 NUMERIC underflow。
- **(1c)** Foster–Stine 原式 cost = α/(1−α) ≥ α；設計扣 α 平額，低收 O(α²)≈2.5e-7——在直接 bound 下無關緊要，不需改。

### #2 α_i→DSR threshold mapping — **拍板：Option B**（confidence HIGH）

**Option A REJECT 理由**：A 切斷「帳本扣的 α_i」與「test 實際 type-I 水準」的恆等——test 恆以 level 0.05（threshold 0.95）執行，帳本卻記 ≤ 5e-4 ⇒ E[V] ≤ Σα_i 的核心不等式失效，真實 E[V] 可超帳本隱含 bound 10-100 倍；「FDR 保證」退化為 admission throttle 啟發式，§1 定理整個不成立。MIT 拒絕為 Option A 背書任何 FDR 語義。

**Option B APPROVE 理由**：`threshold = max(0.95, 1−α_i)` 使 P(pass | null) ≤ α_i 成立（DSR 校準前提下），§1 定理的前提 (b) 接通。單調只嚴不鬆：max(0.95,·) ≥ 0.95 = 今日 gate ⇒ 永不比現狀寬（root principle 5/6 ✓）。零改動前提已親驗成立（§0 第一行）。實際後果（#2×#7 交互）：**reachable wealth 下 threshold ≥ 0.9995**（非 0.995——cap 不 binding，α_i ≤ 5e-4），即 deflated PSR z-bar 從 1.645 升到 ≈3.29，T≈50-100 trades 下所需 observed Sharpe 約翻倍 ⇒ **初期 pass rate 預期 ≈ 0，這是設計後果非故障**，PM/operator 須有此預期（見 N-7）。邊界安全：α_i 浮點下溢至 0 → threshold=1.0 → DsrGate `:373` ValueError → `_run_dsr_stage` fail-soft DEFER（`:1081-1083`）= 收縮向，不 crash ✓。

### #3 DEFER-no-debit — **MODIFY**（confidence HIGH；唯一 binding 修訂）

設計的論據「DEFER ⇒ test not conducted」**在實作事實下為偽**：`_run_math_gate` 五 stage 全跑無 short-circuit（§0 親驗），故 `dsr=pass` ∧ `pbo=DEFER`（single-config 必然）⇒ overall=DEFER ⇒ 設計規則下**不扣帳，但 DSR 統計量已與 threshold 比較過——test 已被 conduct**。後果鏈：

1. **single-config 候選永遠拿不到 overall=pass**（PBO honest-DEFER 恆在）⇒ 在設計規則下可**無限次免費 re-look DSR**（資料逐日累積、同 pre_reg 重測、DEFER 不鑄 dead-mode lesson 故 novelty 不擋）——標準 optional-continuation 問題，免費 interim looks 不入帳直接破壞 §1 前提 (c)。
2. 設計 §14-2 主張的封堵（pre-reg hash + novelty + 完成必 debit）**封不住這條**：pre-reg hash 不含 evidence 資料、novelty 只 dedupe dead-mode lessons、「完成必 debit」恰恰是被繞過的那個定義。
3. 量級評估（誠實標註）：α_i ≤ 5e-4 + 資料 accrual 節奏限制 look 數（年 ~50-100 looks）+ 相依 looks 的 LIL 型膨脹 ⇒ 最壞有效水準仍約 ≤ 5e-3 = 0.1·α_target，**target 本身大概率不破**——所以這是 MODIFY 不是 REJECT。

**具體替代語義（binding，寫入 E1-B AC）**：
> debit 條件 = `overall ∈ {pass, fail}` **OR** `stage_verdicts["dsr"] ∈ {pass, fail}`。
> 即：α-bearing 統計量（DSR）一旦與 threshold 比較即視為 test conducted、必扣；純 DEFER（DSR 自身 DEFER：inputs missing / insufficient_observations / compute error）維持不扣——「資料稀缺不破產」的設計意圖完整保留（Q1/輸入缺失型 DEFER 全部仍免費）。

一行條件改動，無結構重設計。修訂後 §1 前提 (c) 乾淨成立。

### #4 primary-axis family — **APPROVE-with-NOTE**（confidence HIGH）

family = `capability_id:primary_axis`，拒 axes 組合 ✓ 正確：組合 family 的 2^|axes| 鑄幣面是真實 wealth-inflation 攻擊向量。FDR 數學上，family 錯誤指派（hypothesis 真實屬於 axis Y 卻 declared X）**不破全域 bound**——false discovery 不論記在哪個 family 帳上，E[V_total] ≤ Σ_f budget_f 不變；錯指派只損 per-family 可解釋性，不損保證。guard clause F 的 `primary_axis ∈ signal_axes_used` 確定性檢查充分。

NOTE：
- **(4a)** cardinality healthcheck 應綁定量化門檻 **N_fam ≤ 1/γ = 10**（§1 推導：超過即全域 mFDR_{η=1} ≤ α_target 不再成立，退化為 mFDR_{η=N_fam} 語義）。|capabilities|×|axes| 估 ~6-12，恰在邊界——healthcheck 閾值設 10、超限 alert + operator 裁決，比「維度衛生」泛語義強。
- **(4b)** `prh_family_spec_uk = (family_id, spec_sha256)`：**同 spec 換 primary_axis 可在兩個 family 各註冊一次**（合法 row）——各自付各自的 α，帳務上 sound、全域 bound 不破，但屬「同假設雙重機會」；建議 healthcheck 加 cross-family duplicate spec_sha256 計數（觀測即可，不必 DB 禁止）。

### #5 overlap 不足=不相關 — **APPROVE-with-NOTE**（confidence HIGH）

無法證明相關 ⇒ 不合併 ⇒ N_eff 偏大 ⇒ E[max SR_K] 偏大 ⇒ DSR deflation 偏狠 ⇒ 更難 pass。失敗模式收縮向 ✓。`min_overlap_bars=20`（daily ≈ 3 週）作為 Pearson corr 可估下限合理——20 bar 以下的 corr 估計 SE ≈ 1/√17 ≈ 0.24，在 cut=0.5 附近誤判率高，「不確定就當獨立」是教科書正確的保守解。全 pairs 無 overlap → N_eff = M（最大 deflation）✓。可審計性：N_eff 為整數、`max(1,·)` guard、DB CHECK `k_for_dsr=n_eff` 整數等式可審 ✓。

NOTE **(5a)**：設計 §3.1「N_eff 偏大 ⇒ **wealth 扣更多**」措辭不準——M2 單 debit 下 debit 額 = α_i 與 N_eff 無關，N_eff 只影響 DSR deflation。保守方向結論不變，但文檔該改（防後人誤讀 wealth 帳與 N_eff 耦合）。

### #6 cluster 超 cap = `ceil(size/cap)` effective trials — **APPROVE-with-NOTE**（confidence MED-HIGH）

對 ENDORSED 基線（一 cluster = 1 trial）嚴格單調更保守：size>25 的 mega-cluster 從 1 個 trial 變 ceil(size/25) 個 ✓，封死「千變體藏一桶」✓。整數、≥1、可進 DB CHECK ✓。

NOTE **(6a)**：corr>0.5 的 cluster 成員只共享 ~25% 變異——equicorrelated ρ=0.5 的 M-block 譜有效維度遠大於 M/25（如 M=1000 時 participation-ratio 型 N_eff ≫ 40）。`ceil(size/cap)` 對中度相關 mega-cluster 仍**低估** effective trials（相對譜方法）。不阻斷理由：(i) 相對 ENDORSED 基線只嚴不鬆；(ii) numpy `eigvalsh` 不需 scipy，未來可升級為譜 N_eff（per-cluster (Σλ)²/Σλ²），列 future enhancement 非 P4 義務；(iii) 上線初期幾乎全走 raw-K fallback（設計 §3.2 自認），此演算法短期不承重。

### #7 `min_batch_size=10` ⇒ cap = 0.005 — **APPROVE-with-NOTE**（confidence HIGH）

「任何單一 test 不得消耗超過總 FDR target 的 1/10」作為硬頂語義健全；10 與 §1 的 N_fam ≤ 1/γ = 10、γ=0.10 形成自洽的 10 倍 margin 體系。與 ENDORSED M1 公式相容 ✓。

NOTE：
- **(7a)** 如 (1a)：默認動態下 cap **vacuous**（α_i ≤ 5e-4 < 0.005 恆真），唯一 binding 場景 = operator_adjustment 把 wealth 抬過 0.05——這正是它該存在的理由（防 operator 手滑灌 wealth 後單 test 吃掉半個 target），docstring 必須寫明「defense-in-depth, not operative」。
- **(7b)** 命名語義漂移：`min_batch_size` 暗示批次晉升語義（batch-BH 類），實際是 per-test cap 除數。M1 ENDORSED 用此名故不改名，但 docstring 須消歧。
- **(7c)** `NUMERIC(14,10)` 與幾何衰減交互：α_i = 5e-4·0.9^t 在 t≈150 跌破 1e-10 精度 → 存儲取整為 0 → `awl_amount_sign_chk (debit AND amount<0)` 被違反 → INSERT 報錯。(1b) 的 assign_alpha_i floor（None ⇒ 不可測）同時解此題；fail mode 是 fail-loud 不是 silent，可接受但該預防。

## 3. 總裁決

**M1+M2 final ratification：APPROVE（7 項中 6 項 APPROVE/APPROVE-with-NOTE，1 項 MODIFY）。**
**P4 自 MIT 視角 E1-READY：YES，附 1 個 binding 條件**：

> **條件（binding）**：#3 的 debit 條件按本 verdict 替代語義修訂（`overall ∈ {pass,fail}` OR `dsr stage ∈ {pass,fail}` 即扣），寫入設計 §2.4 + E1-B 驗收 AC + E4 golden test（斷言「dsr=pass ∧ overall=DEFER 的 run 必有 debit row」）。一行語義改動，不需回 PA 重設計。

#2 拍板 Option B（Option A 不得作 fallback 保留 FDR 語義聲明；若 E1 因故退到 A，必須同步把所有「FDR target 保證」字樣降級為「admission throttle」）。φ=1.0 + W_0=0.10·α_target + spend 0.10 的 wealth 軌跡在 #3 修訂後**保 per-family mFDR ≤ 0.1·α_target（10x margin），全域 mFDR ≤ α_target（N_fam ≤ 10 條件下）**——§1 自含推導，依賴 DSR null 校準近似（confidence MED-HIGH，由 N_eff/HAC/strictest-wins 墊保守）。

成熟度聲明（誠實）：本裁決是 **design-stage ratification**（pre-Foundation）；V137 未建、0 row、Mac 無活 PG——runtime 維度（writer-spawn/row/consumer/decision-impact）全部 N/A，待 E1 落地後按 5 階段 4 維度另審。

## 4. NOTE 區 — 7 項之外的缺陷（不阻 gate；按 severity 排序）

| # | Finding | Severity | Confidence | 細節 / 修法 |
|---|---|---|---|---|
| N-1 | **V137 `awl_debit_fields_chk` 三值邏輯洞**：PG CHECK 對 NULL 判 pass——`n_eff>=1` 在 n_eff IS NULL 時整式 NULL → CHECK 通過 ⇒ debit row 可帶 NULL n_eff/k_for_dsr 入庫，「必填」聲明未被 DB enforce | **MED-HIGH** | HIGH（標準 PG 語義；Linux dry-run 可一行驗證） | 改 `n_eff IS NOT NULL AND n_eff>=1 AND k_for_dsr IS NOT NULL AND k_for_dsr=n_eff` |
| N-2 | **refund × debit_failed 無互斥**：兩個 partial unique 各管各的，同一 debit_id 可同時有 refund 與 debit_failed row（view 取 confirmed、balance 不受 debit_failed=0 影響，帳不爛但語義髒，違反設計自己的 §14-1「不靠應用層自律」） | MED | HIGH | 換成單一 `UNIQUE (debit_id) WHERE event_type IN ('refund','debit_failed')` 終局事件互斥索引 |
| N-3 | **orphan/oversized refund = wealth-inflation 向量**：refund row 無 FK 也無金額上限綁定對應 debit（CHECK 只驗 >0）——reconciler bug 或越權 INSERT 可灌 wealth。append-only + operator-scope 緩解但 DB 層開著 | MED | HIGH | DB 層 CHECK 無法跨 row；補 healthcheck SQL（refund 無對應 debit、或 refund.amount ≠ φ·|debit.amount| → alert）+ store 層斷言 |
| N-4 | **debit_id 決定性未規範**：冪等聲明依賴 unique index，但若 debit_id = 隨機 UUID per attempt，「gate verdict 後、INSERT 前 crash → 重試」會鑄新 debit_id 雙扣 | MED | MED-HIGH | 規範 debit_id = deterministic hash(pre_reg_id, evidence window, attempt) 寫入 E1 契約 |
| N-5 | **ledger `pre_reg_id` 無 FK**（設計 DDL 僅註解箭頭）→ orphan pre_reg_id 可入庫，斷 audit 鏈 | LOW-MED | HIGH | 加 `REFERENCES research.pre_registered_hypotheses(pre_reg_id)`（注意兩表創建順序） |
| N-6 | **raw-K fallback 偏差方向**：已驗 = 保守（raw K ≥ N_eff ⇒ over-deflate duplicates）✓ 設計誠實。但 `k_trials` 是 evidence-supplied（adapter `:146`）——信任邊界在 AEG pipeline 非 LLM，可接受；若未來 evidence 來源擴張須重審 | INFO | HIGH | 維持；evidence 來源變更時觸發重審 |
| N-7 | **實際 pass-rate 預期管理**：threshold ≥ 0.9995 + PBO 需 multi-config + B1 雙因子 ⇒ 初期 discovery 率 ≈ 0 是設計後果。PM 勿把長期 0 discovery 誤判為 pipeline 故障；對應 healthcheck 應監測「conducted tests > 0」而非「discoveries > 0」 | INFO | HIGH | runbook / healthcheck 語義註明 |
| N-8 | **executor docstring「short-circuit」與實作不符**（`:1003` vs 全 stage 執行）——pre-existing 非 P4 引入，但 P4 的 debit 語義依賴此行為，修 #3 時順手改 docstring | LOW | HIGH | E1-B 順帶一行 |
| N-9 | 假陽性候選自查：曾疑「demo-confirm refund 的異步到帳破壞 α_i predictability」——判定不成立：α_i 取 INSERT 時 PG balance，refund 屬過去 discoveries 的外部驗證事件，對當前 test 的 null 無資訊耦合，predictability 成立 | （已排除） | MED-HIGH | 列出供 PM 覆核，不入 finding |

## 5a. 補充裁決（同日）— QC FIX-3.1 ack：**ACK-with-條件**（confidence HIGH）

QC sign-off 建議 FIX-3.1（DSR 渲染前 input-availability precheck，注定 DEFER 的 run 免費 skip）。MIT 裁決：

**(1) Conditional-on-conducting 論證成立（收緊後）**：selection 不破 mFDR bound 的乾淨充分條件 = conduct 決策 C_i 可測於「test 逐 cell 保持 level 校準」的變數 σ-代數。DSR null 校準 conditional on (N,K)——對任何 C ∈ σ(存在性 flag, N, 日曆 span)，`P(pass|C,H0) ≤ α_i` 逐 cell 成立。「資料量與 Sharpe 精度相關」的對抗點被解掉：精度-given-N 正是 DSR 自己的 conditioning 變數，selecting on N 只是選校準 cell 非 selecting on 統計量。雙保險：(a) skip 只在 overall=pass 結構性不可達時觸發，被 skip run 對 V/R 增量恆 0；(b) 不渲染 ⇒ 無 dsr verdict 紀錄 ⇒ #3 封掉的 optional-continuation 通道根本不開——**#3 debit 規則一字不改**。

**(2) QC verbatim 謂詞一項不過邊界**：`down-span<180d` 如實作是 **value-derived**（`beta_neutral_check.py:245` 親驗——down_ts 由 BTC 價格條件篩出），conduct conditional on BTC down-heavy 路徑對 short-beta null 是 anti-conservative 方向。**修法零成本**：替換為 value-free 蘊含條件「aligned candidate history 日曆 span < 180d」（年輕 cohort 覆蓋完全相同；老候選 down-bar 稀缺照渲染照付=保守浪費可受）。

**允許集合邊界（binding，一句定死）**：
> skip 謂詞必須滿足 **value-invariance**：固定 timestamps/row 存在性下擾動任何 price/return 數值，謂詞真值不得改變——允許：輸入序列存在性（`is None`）、row/bar/trade 計數、日曆 span、schema/lineage 完備性；絕不可：down-bar 計數、value-derived down-span、vol、Sharpe、β、任何 returns 實現值的函數、任何先前 value-derived stage verdict、wealth 以外的任何統計量。

**Binding 條件 4 項（寫入 E1-B AC）**：① 謂詞替換（上述）；② total skip——不算 DSR、`stage_verdicts["dsr"]` 不記 pass/fail、DEFER reason=`precheck_input_unavailable`、skip 落 log（conducted 計數只算渲染過的，N-7 語義不被污染）；③ golden tests——(a) skip run ⇒ 無 debit ∧ 無 dsr verdict、(b) #3 golden test 原樣保留、(c) value-invariance mutation test（擾動數值斷言 skip 決策不變）；④ precheck 置於 STAGE 3.7 α_i assignment **之前**。

註記：謂詞 under-fire=照付=保守；over-fire=power 損失非 validity 損失；建議謂詞 reuse B1 入口存在性檢查碼路徑防 drift。N-8 docstring 由本 FIX 部分兌現。1b 的 assign_alpha_i floor 建議獨立成立不因本 ACK 撤銷。

## 5. 文獻錨點

Foster & Stine (2008) *α-investing: a procedure for sequential control of expected false discoveries*（mFDR_η ≤ α；multiple-streams 可加性）；Aharoni & Rosset (2014) GAI（payout/penalty 框架——φ=1.0 refund ≤ GAI payout cap 逐路徑成立）；Javanmard & Montanari (2018) / Ramdas et al. (2017) LORD/LORD++（W_0 ≤ α 慣例——本設計 W_0 = 0.1·α_target 更緊）；Ramdas et al. (2018) SAFFRON / Tian & Ramdas (2019) ADDIS（candidate-thresholding 路線，本設計未採、不必採）；Bailey & López de Prado (2014) DSR（null 校準假設的出處）。本 verdict 的核心 bound（§1）為自含推導，不依賴上列任何論文的精確 payout 常數——僅依賴 (a) predictability (b) per-test level ≤ α_i (c) conducted-test-pays 三前提。
