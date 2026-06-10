# QC Sign-off — L2 Mesh P4 online-FDR loop（pre-reg hash 鏈 + sealed-holdout 5 gate + B1×#3 交互）

日期：2026-06-10 ｜ 作者：QC ｜ 落盤：PM 主會話代行（QC 任務無寫檔權限）｜ **總裁決：APPROVE-with-FIX — P4 可進 E1-READY**

**範圍與證據基礎（誠實聲明）**：P4 設計全文（421 行）只存在於 `feat/l2-p4-design` branch；QC 工具組無 Bash，無法 `git show`。本審計 grounding =（a）dispatch 對 §4.2/§9 機制的逐條描述、（b）MIT final ratification verdict 的 grounded 引文（其 §0 四項材料事實已親驗 MATCH）、（c）`L2_TODO.md` §4 P4 binding 參數、（d）**main 工作樹五處代碼全部親讀**。凡結論依賴設計原文字面者列「PM 4 項原文核對」（見文末 PM 附錄——已核完）。黑名單檢查：alpha-investing / DSR / PBO / B1 OLS+HAC，無黑名單方法，clean。

---

## Sign-off 點 1：pre-registration hash 鏈防 spec mining（設計 §4.2）— **APPROVE-with-FIX**

### 代碼層親驗（全部 PASS）

| 機制 | 親驗 | 結果 |
|---|---|---|
| canonical_sha256 byte-identical | `residual_hidden_oos_bridge.py:103-114` 與 `candidate_hidden_oos_sealer.py:34-38` 同為 `sort_keys=True / separators=(",",":") / ensure_ascii=True` | **MATCH**，commit-reveal 的 hash 算法單一 |
| sealer 承諾指紋 | `compute_split_hash` = canonical(family + 三窗 + embargo + K)（sealer `:41-60`）；`residual_hash` 綁 report 全文（bridge `:355`） | 窗口與 K **已入指紋**——sealed 端 window-shopping 被指紋封死 |
| 寫入唯一通道 | bridge `:398-402` 唯一寫入 = 注入 `run_register_in_pg_xact`（xact 內雙 INSERT）；`_persist_hidden_oos_state_registry`（registry `:1067-1157`）硬寫 `'sealed',0,FALSE,FALSE,FALSE` | 封存狀態由**消費端 xact** 寫，非 producer 自報 |
| 防覆寫 | `ON CONFLICT (replay_experiment_id) DO NOTHING`（`:1130`）= 首次承諾不可被重註冊覆寫；`family_split_uk` 無 conflict handler → 同 split 重註冊 raise → xact abort fail-loud | 「先承諾者勝」語義正確，**對 anti-spec-mining 是加分** |
| fail-closed 前置 | bridge `:207-351` 任一前置失敗回 `(None, err)` 不撞 V132 CHECK | ✓ |

### 攻擊者視角逐條

**修訂 = 新 row + supersedes 血緣，是否留 HARKing 後門？** 帳務上無後門（MIT #3 修訂後每 look 付費=paid sequential looks，mFDR bound 不破；血緣保留完整 audit trail）。殘縫 = **lineage-head 未必被 enforce**：消費層若可對已被 supersede 的舊 row 起測，可分叉血緣（A→A′，A 與 A′ 各測）——每測仍付費故 bound 不破，但污染 pre-registered 語義純度。→ **FIX-1.1**（E1-B AC）：consume 時 pre_reg 必須是 supersedes 鏈之 head，違者 DEFER `pre_registration_superseded`。

**hash 不含 evidence 資料，#3 修訂後殘餘 gaming 面？** 無界 gaming 面已閉（#3 把 re-look 內生化為 paid look）。殘餘兩個有界面：
- **(1a) evidence 窗口選擇（非 sealed 側）**：interim look 的非 OOS evidence 窗若不被 pre-reg hash 釘住，可逐 look 換窗取 max。每 look 付費 + B1 down-leg 180d span + bull-only 標籤三重墊底使其有界。→ **FIX-1.2**：pre-reg hash payload 釘 evidence 窗 spec（或「僅向後 accrual 延伸」單調規則），偏離 → DEFER `pre_registration_mismatch`；hash 重算必須在任何統計量渲染**之前**（precondition 位）。
- **(1b) falsification_test v1→v2**：親驗 v1 契約（`l2_prompt_contract_registry.py:254-293`）`falsification_test` 確為自由字串。v2 三欄結構化方向正確，但**存而不裁 = theater**。→ **FIX-1.3**：消費層必須真評估 falsification 欄；falsification 觸發 → 強制鑄 dead-mode lesson（namespace 同 `dead_mode_seed`），閉合 novelty 迴路（同時補強 #3：被證偽假說的近似重提交被 novelty DEFER 擋住）。

**append-only 現實邊界**（紀錄非 finding）：V137 將與 V133/V134 同構——prod 無 `trading_ai` role，append-only 靠 REVOKE PUBLIC + code 層 INSERT-only，對 owner/admin 非絕對；與既有 sign-off 前提一致。

**結論 1**：三層 enforce 骨架數學上成立且方向保守（一切 mismatch/缺值收縮向 DEFER）；#3 修訂生效前提下無未付費 spec-mining 通道。FIX-1.1/1.2/1.3 為 AC 級，不需回 PA。

---

## Sign-off 點 2：sealed-holdout「證實」5 條 gate（設計 §9）— **APPROVE-with-FIX**

### 2.1 可執行性 / 可證偽性 / 自我宣告空間

M1 demo-confirm bar 四條（`n_trades≥30` / green Stage-0R / `net≥0` / `≥21d`）全部機器可裁決、可證偽、證據來源皆系統側，無自我宣告空間 ✓。V132 機械：sealed→opened→consumed 單向消費意圖 + `family_split_uk` 防 split 重用 + FK `ON DELETE RESTRICT` + flag-consistency CHECK——骨架充分。

**統計力誠實標註（非阻斷）**：`n=30 + net≥0` 本質是帶成本拖累的符號檢定；取系統歷史量級（c≈10-27bps，σ≈50-100bps）null-confirm 機率 ≈ Φ(−c·√30/σ) ≈ **15-40%**。即 **confirm 是 refund 觸發器（帳務事件），不是 alpha 證明**；MIT §1 bound 對此 robust，但 P4→P5 的「證實」若被讀成晉升證據即犯 bull-only 陷阱。→ **FIX-2.3**：§9 confirm 語義固定為 accounting-confirm；P5 晉升須另跑 opened-OOS math gate（DSR/B1）+ regime 標籤（bull-only confirm = regime-bet/learning-only）。

### 2.2 §9.4 auto-loop 盲視 — **真實邊界語義縫（MED-HIGH，本 sign-off 主 FIX）**

親驗兩端語義**不等價**：
- bridge `_bucket_admissible`（`:150-161`）：**半開區間**，桶 `[b, b+bucket_sec)` admissible iff `b + bucket_sec ≤ oos_start`——跨界桶整顆逐出。
- adapter `_clip_window`（`:422-428`）：**閉區間** `{d: ws ≤ d ≤ we}` date-key；`_load_daily_closes`（`:472-486`）取到 `we` 整日終。

後果：若 auto-loop 把 `window_end` 設為 sealed `oos_start` 當日（最自然的 off-by-one 接線），閉區間 clip **納入** date == oos_start 的 bar——其 close 在 sealed OOS 窗內實現 → 一階前視洩漏，且**靜默**。等價條件 `we ≤ oos_start − 1 day` 目前無任何一層 enforce。更深：adapter 的 `ws/we` 來自 **evidence 自報**（`build_context_from_evidence:603-604`），P4 auto-loop 下盲視不能靠 producer 自律。

→ **FIX-2.1（必折入 E1 AC，否則 §9.4 盲視聲明不成立）**：消費層從 **V132 durable row** 重取 `window_start`（=oos_start），enforce `evidence.window_end ≤ oos_start − 1 daily bar`，違者 DEFER `sealed_boundary_violation`；`_clip_window` docstring 標明上界責任；E4 golden test：`window_end == oos_start.date()` 的 dispatch 必 DEFER。

### 2.3 雙 family 體系（V132 cell 級 vs L2 wealth capability:axis 級）— 無無界 leak 縫

結構論證：V132 family 不鑄 wealth，cardinality 無界不影響 N_fam ≤ 10；refund 錨定 debit_id 不經 family 映射 → 「false discovery 記哪個帳」與「holdout 屬哪個 cell」解耦，E[V_total] bound 不受跨體系映射影響。**不合併是正確設計**。有界縫：(2a) 同 cell 多 split OOS 窗重疊 → confirm 相關、牛市批量 null-confirm → healthcheck 重疊計數（觀測級）；(2b) 一次 consumption ↔ 多 hypothesis confirm 的基數未規範 → AC：至多一個，或顯式聲明多重性+healthcheck；(2c)=QN-1。

---

## 交互檢查：MIT #3 × B1 — 無阻斷交互

親驗 `_run_math_gate`：五 stage 全跑（docstring `:1003` 不符=MIT N-8）；B1=STEP3（key `beta_neutral`），DSR=STEP1。
1. **Promotion 語義零副作用**：B1 DEFER 經 strictest-wins 鎖死 overall ≠ pass → 不鑄 discovery → refund 不可達。扣帳是帳務事件，不進 promotion 鏈。B1 ENDORSED 邊界完整保留。
2. **經濟學側效應（材料性）**：B1 `DOWN_SUBSAMPLE_SPAN_DAYS_MIN=180`（親驗 `beta_neutral_check.py:74`）⇒ 年輕候選 ~6 個月 B1 必 DEFER；#3 下每 re-look 扣 10% wealth ⇒ 等 B1 可裁時 family 近殭屍態（與 MIT 1b 疊加）。方向保守但浪費 wealth。
3. **建議 FIX-3.1（需 MIT ack）**：DSR 渲染前加確定性 input-availability precheck——B1/leak 輸入在存在性層面已注定 DEFER（candidate_returns=None / altcap=None / down-span<180d）→ 跳過 DSR 渲染整 run 免費 DEFER。謂詞只依輸入存在性（predictable、與 Sharpe 值無關）不開 optional-continuation 後門；DSR 是攻擊者可離線自算的確定函數，skip 不外洩資訊；無 DSR 渲染則無 discovery 路徑。同時兌現 docstring short-circuit（N-8 一併閉）。若 MIT 不 ack，回退=接受側效應+runbook 標註，sign-off 不翻轉。
4. 順帶：B1 stage key = `"beta_neutral"` 非 `"b1"`，E1-B AC 措辭引用 key 時對齊（QN-6）。

---

## 總裁決

**QC sign-off：成立（APPROVE-with-FIX）— P4 可進 E1-READY**，條件全部 AC 級，無一需回 PA：

**Binding（折入 E1 驗收 AC）**：
1. **FIX-2.1** sealed-boundary guard（V132 row 重取 oos_start + `window_end ≤ oos_start − 1 daily bar` + DEFER `sealed_boundary_violation` + E4 off-by-one golden test）。
2. **FIX-1.1** pre-reg consume 限 supersedes 鏈 head；**FIX-1.2** hash 重算先於一切統計渲染 + evidence 窗釘入 hash payload（或單調 accrual 規則）；**FIX-1.3** falsification 真評估 + 觸發鑄 dead-mode lesson。
3. **FIX-2.3** confirm = accounting-confirm 語義固定；P5 晉升另要求 opened-OOS math gate + regime 標籤。

**建議（非 binding）**：FIX-3.1 pre-DSR input-availability skip（需 MIT ack predictability 論證）。

## NOTE 區（不阻斷）

| # | Finding | Severity | Confidence |
|---|---|---|---|
| QN-1 | V132 狀態機轉移單向性非 DB-enforced（consumed→sealed UPDATE 通過全部 CHECK）；建議 trigger / REVOKE UPDATE / 回退偵測 healthcheck（E1-C 順手） | MED | HIGH |
| QN-2 | 同 cell 多 split OOS 窗重疊 → confirm 相關性 → 牛市批量 null-confirm；帳務 robust，建議重疊計數 healthcheck | MED-LOW | MED-HIGH |
| QN-3 | demo-confirm null-confirm 率 15-40% 量級；refund 觸發器可接受，runbook 防誤讀為 alpha 證明 | INFO | MED |
| QN-4 | `_persist_hidden_oos_state_registry:1076-1078` manifest 無 hidden_oos_state → 靜默無 durable row；E1 消費層應顯式驗 row 存在 | LOW | HIGH |
| QN-5 | canonical JSON hash 跨語言/key-type 脆弱性——失敗方向=DEFER（保守）；非 Python 消費者出現時重審 | INFO | HIGH |
| QN-6 | B1 stage key = `"beta_neutral"`；AC 措辭對齊 | LOW | HIGH |
| QN-7 | 假陽性自查（已排除）：adapter `_to_date` intra-day 邊界洩漏——P4 evidence 為 daily bar 不材料；4h bar 入範圍時重審 | — | MED-HIGH |

---

## PM 附錄：4 項原文核對結果（主會話親核，設計全文 session 內已讀）

1. **§9 五條清單**：QC 重構**與原文不符**（QC 誤以 M1 demo-confirm bar 為 §9 主體；原文五條=真寫/hash 對賬/double-seal 可觀測/auto-loop 盲視/consumed 轉移不可由 L2 觸發）。已按 QC 條款回派重裁——**結果見下節「點 2 重裁補記」**。
2. **§4.2 hash payload**：原文 spec_jsonb={statement, mechanism, signal_axes_used, falsification_test}——**不含 evidence 窗 spec** → FIX-1.2 成立為真新增 AC。
3. **§9 opened-OOS math gate 重驗**：原文**無此要求** → FIX-2.3 成立（重裁後 re-scope 掛靠 M1/晉升節）。
4. **family 對齊註記 consumption↔confirm 基數**：原文**未規範** → 2.3(2b) AC 成立。

---

## 點 2 重裁補記（2026-06-10，QC 對照 §9 原文重裁；取代上文 2.1/2.2 中與 §9 歸屬相關的措辭）

§9 原文五條逐條：gate 1 真寫 PASS w/ INFO（F-a：`actor_id`/`source` 為 writer 自填，驗收須 log↔`created_at` 交叉核對；「INSERT 成功即證」只證 CHECK 所編碼者）；gate 2 hash 對賬 PASS（三 hash 任一 mismatch 即偽，自我宣告空間近零）；gate 3 double-seal PASS（純可觀測量）；gate 4(a) grep proof PASS w/ QN-3；**gate 4(b) FAIL as worded**（核心 finding）；gate 5 PASS w/ QN-1；家族對齊註記 PASS w/ INFO（「真實 cell」須繼承 gate 1 證據標準）。

**核心 finding：FIX-2.1 升級為 FIX-2.1b（MED-HIGH，confidence HIGH，代碼親驗）**——gate 4(b) 原文「evidence 窗尾端 > oos_start → DEFER `sealed_holdout_overlap`」的 acceptance 語義不足，且比初版 FIX-2.1 所述更寬：
1. `==` off-by-one：adapter `_clip_window` 閉區間（`:428`），`window_end == oos_start` 當日 bar 被納入（= sealed OOS 首觀測），原文 `>` 在等號處不 DEFER → 靜默一階前視。
2. **非對齊 oos_start 全漏（升級項）**：window_end 是 date 標籤（午夜起點）；oos_start 非午夜對齊時（bridge `:150-161` 明文處理 straddle bucket=活場景），連 `≥` 點比較也回 False，但該 daily bar 延伸至次日午夜 > oos_start → bar 跨界洩漏。**點比較對區間對象是錯的代表元**。
3. 正確語義=區間算術，鏡像 bridge `_bucket_admissible`（bucket=86400）：bar 可納入 iff `bar_end = date + 1d ≤ oos_start`；DEFER 條件=末 bar 尾端 > oos_start。
4. E4 測試契約連帶：按原文 `>` 寫的測試在 off-by-one bug 下照樣全綠（假保證）——`==` 與非對齊 straddle 兩個邊界 case 必須是 load-bearing assertion。

**FIX-2.1b 措辭（binding，取代 FIX-2.1）**：adapter 以 V132 row 重取 `window_start`（schema 親驗：該欄即 oos_start，命名一致）、enforce **末 bar 尾端 ≤ oos_start**、違者 DEFER；reason code 統一用原文 `sealed_holdout_overlap`（退役 `sealed_boundary_violation`，原文先佔名且 overlap 涵蓋邊界觸碰）。

**前裁決處置**：點 1（FIX-1.1/1.2/1.3）維持；FIX-2.3 維持但 **re-scope**——§9 實為純完整性認證、無統計充分性主張，demo-confirm 統計力疑慮（null-confirm 15-40%）撤離 §9、掛靠 M1/P5 晉升節（實質要求不變：accounting-confirm 語義 + opened-OOS math gate + regime 標籤）；QN-1 維持+nuance（V132 `state_flags_chk` 會擋單欄 state 回寫，意外回退有部分防護；蓄意多欄重寫仍全過）；QN-2 維持。**新增**：QN-3（grep proof 是必要非充分+point-in-time，建議 touch-time E2 義務或週期審計查詢，LOW-MED）、QN-4（V132 `family_split_uk` 允許同 cell 多 sealed row，原文單數措辭未定義聚合規則；fail-closed 默認=與**任一** sealed row 重疊即 DEFER，LOW-MED）。

**重裁後總結**：sign-off 點 2 = **APPROVE-with-FIX 維持**；FIX 集合更新為 **FIX-2.1b（唯一 §9 阻斷項，落實前不得裁定「sealed-holdout 證實」達成）** + FIX-2.3（re-scope）+ QN-1/2 維持 + QN-3/4 追加。FIX-2.1b 落實條件下，§9 五條全綠即構成 P4→P5 gate 的充分完整性證據。
