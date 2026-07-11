# AI-E 盈利研判 Stage 2（守+攻）— 2026-07-09

**角色**：AI-E（AI 推理 ROI lens：L2 花費 vs 帶來 edge、cost_edge_ratio、dormant AI 能力可救性）。
**邊界**：read-only 全程遵守；零修復/零 config/零 deploy/零 restart/零 auth。本輪未新開 Linux 取數——守側全部承接 Stage 1 兩份 runtime 證據報告，只補增量判斷。
**Stage 1 底稿**：
- AI-E `workspace/reports/2026-07-09--ai_cost_roi_dormant_capability_audit.md`（engine PID 1561777, build 54d5fbf99）
- MIT `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-07-09--profit-evidence-readonly-probe.md`
**已判定裁決紀律**：maker-nogo / Rank7 四軸 NO-GO / Polymarket 價格軸 KILL / 直接 AI/RL trader 已拒——全部視為已知地形；本報告重提 06-13 O1 時附前提變化證據（非重打舊戰場）。

---

## 一、守 — Diagnoses（8 條）

### D1 [leak][FACT][high] L1 judge_edge 98% 撞 8s timeout——AI 判斷腿名存實亡
- 證據（承 AI-E N1，可重跑）：`agent.ai_invocations` provider=ollama 743 row（07-05→07-09），success=false 728 / true 15；`ollama_client.py:362 timeout=timeout or 8` 硬編；SQL：`SELECT success,count(*),percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) FROM agent.ai_invocations WHERE provider='ollama' GROUP BY success`。
- 增量判斷：可救性極高（timeout 校準/keep_alive/模型降級三選，E1 小時級工作量）；未修前一切「L1 判斷有無價值」的問題都不可答（樣本 98% censored）。
- 盈利影響：~180 call/day 全落回 L0 heuristic，AI 對 gate 質量零貢獻但白耗 ~24min/day 阻塞延遲。

### D2 [frozen][FACT][high] L1 進化迴圈餓死第 15 天 + ML 標籤斷糧（gate 鎖）
- 證據：strategist_applied max=2026-06-24（AI-E N4）；soak isolation 06-29 起擋全部 ordinary demo entry 415,651 rejects/10d（MIT F5）；realized_fill 標籤 7d 僅 14 行（MIT §D）；model_registry 93/93 shadow_only。
- 增量判斷：這不是 AI 棧故障而是上游 gate 決策——soak isolation 存續 vs 標籤斷糧的權衡屬 operator（MIT 建議 4 同判）。AI 能力建設在標籤斷糧下全部空轉。
- 盈利影響：唯一 production-impact ML 組件剩 James-Stein（阻擋方向）；學習迴路無新鮮供血=任何 AI 活化的邊際價值≈0，直到解鎖。

### D3 [frozen][FACT][high] Cloud L2 凍結槓桿滿 3 個月——技術前置本輪首次齊備，只剩 operator 一鍵
- 證據（承 AI-E N2/N5）：`ai_usage_log` 0 row all-time；三 key present（/proc/1561777/environ 親證）；teacher `enabled_at_boot=false`；daily $2 Rust gate `4e30b983b` 已入運行 binary（merge-base 親證）；advisor WarmUp armed。
- 增量判斷：與 06-13 相比，阻塞 L2 消費的治理前置（daily cap 腿、writer、flock、P1 契約債）已全部建成——剩餘 blocker 純為 operator 決策，dormant 可救性=高。
- 盈利影響：$2/day 預算=~37 次/day Sonnet 級深度推理 100% 閒置；06-13 O1/O2 攻性提案 0 消費。

### D4 [frozen][FACT][high] WP1-WP7 全 source-DONE + P1 債已修，但零 runtime caller=無接線 dormant
- 證據（承 AI-E N8）：七包 0 caller、`program_code` 非-tests 零 import、零 `OPENCLAW_` env flag；P1 債 `798843f23`（07-07）已修。
- 增量判斷：路線圖停在契約層。接線缺口不是均質的——WP2（PIT manifest）有現成首位消費者（ALR P2-4，見攻 O4），應排最前；WP1/WP6/WP7 隨後；WP3/WP5 依賴 serving/mutation 場景可後置。
- 盈利影響：證據閉環是任何 AI/ML 產出變成可推廣 alpha 證據的必經管道；無接線=盈利閉環 0 進度。

### D5 [leak][INFERENCE][med] cost_gate 唯一誤殺候選母集：「edge 正但<threshold」49,388 筆，成本模型高估 ~5×
- 證據（承 MIT C.2/C.3/F7）：整體反事實真負（avg −75.13bps、正率 14.9%）→ 無系統性誤殺；但 conservative_v1 slippage 30bps/腿 vs demo 實測 ~6bps；`cost_gate(JS-demo): edge=3.61bps < threshold=8.80bps` 類 30d 49,388 筆。
- 增量判斷：這是全系統「零新數據即可解鎖」性價比最高的一次重算（確定性、非 AI）；`slippage_quantile_artifact.py` 已存在。INFERENCE 因 realistic-cost 反事實未重跑（MIT gap 6）。
- 盈利影響：若翻出淨正 cell=直接解鎖被鎖 edge；若全負=誤殺假說徹底關閉，over-gate 淨貢獻裁決落錘。

### D6 [leak][FACT][high] 30d 全策略 true net 負、費用主導；AI 三層對已實現 PnL 零歸因（paradigm）
- 證據：MIT A.1（gross −150.72 / fees 255.39 / net −406.11 USDT/30d）+ AI-E N11（AI ROI 分子=0 分母=$0 未定義）。
- 增量判斷：AI 現位=per-signal 方向判斷（judge_edge yes/no）微調已知負 edge 搜索空間——即使 D1 修復，這個位置的期望增量≈0。與 06-13 O5 範式拷問同向：AI 該去搜索空間擴展與解讀層，不該留在方向判斷位（攻 O1/O2）。
- 盈利影響：「每日 AI 成本 <$2 達標」持續為 dead-AI 假合規。

### D7 [frozen][FACT][med] L2 memory recall dormant + sonnet-5 定價窗口流逝
- 證據（承 AI-E N6/N10）：`l2_call_ledger` 表不存在；env flag 未設；99 條 bge-m3 1024d embedded 教訓 0 召回。`ai_pricing.yaml` 無 sonnet-5 鍵；intro $2/$10 至 2026-08-31（07-09 官方複驗）。
- 增量判斷：memory recall=研究效率複利（間接盈利面），非直接 alpha；sonnet-5 鍵是 D3 解凍的同窗順手項（−33% 單價=同預算 +50% 推理量）。
- 盈利影響：低直接、正間接；定價窗口是期限性機會（08-31 截止）。

### D8 [unrealized][FACT][high] profit-first loop 唯一候選統計無效（承 MIT F1 CRITICAL）——dedup 該建未建
- 證據：5058 outcomes 僅 2 distinct entry_ts_ms（×2614/×2444 偽複製，n_eff≈1-2）；可重跑 grep/uniq 命令見 MIT F1；`outcome_review.py` 無 per-(cell,entry_ts) 去重。
- 增量判斷：純確定性修復（E1/QC，非 AI）；修 dedup+effective-n 前，false-negative 榜與 READY_FOR_PM_E3_DISPATCH 鏈全部不可信——這排在一切 bounded-probe dispatch 之前。
- 盈利影響：避免對無效候選消耗 E3/BB 窗口；修後榜單才是真誤殺信號源。
- regime_caveat：該候選本身=NEAR 單日 +1.6% 單 episode regime-bet。

---

## 二、攻 — Opportunities（6 條）

### O1 ★paradigm_challenge AI 重定位：方向判斷 → 事件/波動解讀層餵確定性 exit/sizing（防禦價值進 ROI 分子）
- hypothesis（可證偽）：L1 27B（$0 API）對事件流（listing/公告/監管）產出結構化「波動擴張概率」標籤，PIT 對齊後對未來 1-24h realized vol 的解釋力顯著優於純價格 baseline（IC/corr 對比）；標籤餵 exit-policy/sizing 而非方向 → 完全繞開 taker 方向成本牆。
- 外部依據：ECB 記者會 LLM vol 解讀 corr 0.5 vs 文本基線 0.1-0.2（arxiv 2508.13635）；GDELT 新聞特徵+XGBoost 含成本 OOS Sharpe 4.6-5.9（arxiv 2505.16136）——共同結構=「LLM 做特徵抽取、確定性模型做決策」；Alpha Illusion（arxiv 2605.16895）警告 LLM-as-trader 語義洩漏（FinMem post-cutoff −51%）→ 驗證必須含 post-cutoff 子集，本系統 math-primary 治理天然吻合。
- why_not_tried：系統內 AI 一直擺在方向判斷位；27B all-time 0 call；事件軸只有 $0 原始累積無解讀層。
- est_edge：防禦價值向——per-fill 左尾重（p10 −45.65bps，MIT A.3），vol-aware exit/sizing 若削左尾 10-20% 即正 ROI；數字為外部類比 ASSUMPTION。
- est_cost：$0 API + E1 1-2 sprint。wall_break_prob：med。
- how_to_validate：Gate-B listing 探針/公告原始流（06-02 起 R-0 zero-leak live）→ WP2 PIT manifest 封裝 → 27B 離線批量標註歷史事件（post-cutoff 子集單獨評估）→ IC vs baseline → 過則 shadow 餵 exit-policy 反事實。
- regime_caveat：事件樣本需分 regime 統計（listing pop 牛市偏強）。

### O2 L2 解凍最短路徑（premise-changed 重提 06-13 O1：AI 假設家族生成過 math gate）
- 前提變化證據（非重打舊戰場）：①WP1-WP7 契約層已建（06-13 不存在）②daily $2 Rust gate 已入 binary ③P1 契約債已修 ④Sonnet 5 intro $2/$10 至 08-31（−33%）⑤`P1-L2-ADVISORY-MESH-E2E-1` 現成 one-shot 驗證窗（TODO WAITING_OPERATOR）。
- hypothesis：~$0.05-0.5/day L2 做 OHLCV+TA 外「假設家族生成」，全過 WP2 PIT+DSR/PBO 確定性 gate，90 天內 ≥1 個非-OHLCV 候選通過 math gate（0 通過=假設證偽）。
- why_not_tried：teacher default-off + ADR-0020 manual-only + operator gate；06-13 至今 0 消費，但當時缺的治理前置如今已齊。
- est_edge：搜索空間擴展期權價值——上限=解除 06-13/14 判定的搜索空間根因（不可預估數字，ASSUMPTION）。
- est_cost：$1.5-15/月；先決=YAML 補 sonnet-5 鍵 + operator 開 E2E-1 或 teacher。wall_break_prob：unknown。
- how_to_validate：LLM 永不驗 alpha——每假設經 WP2 PIT manifest+DSR/PBO；E2E-1 一次真調用即可端到端驗管道。

### O3 L1 judge_edge A/B 價值歸因（D1 修復後的第一個問題）
- hypothesis（雙向可證偽）：L1 9B 判斷 vs L0 heuristic 在分歧樣本上的 blocked-signal 反事實淨差=0——若無優勢，180 call/day 降級 L0 省延遲；若有，AI 防禦價值首次有數（DOC-08 ROI 分子首次非零可測）。
- why_not_tried：07-05 前 writer 未通水；通水後 98% timeout 樣本全 censored。
- est_edge：歸因基礎設施價值——使 AI ROI 從「數學未定義」變可裁。est_cost：$0 + E1 小改（雙 verdict shadow log）。wall_break_prob：high（純內測無市場牆）。
- how_to_validate：N1 修向(a) timeout 校準 → 30d 雙 verdict 記錄 → 分歧子集反事實（blocked_outcome 管線現成）。

### O4 WP 接線最短盈利路徑：WP2→ALR P2-4 首位 runtime 消費者（零新 gate）
- hypothesis：把 WP2 PIT manifest+WP6 reward ledger+WP7 learning-effect review 接進 ALR P2-4 durable backlog 管線（TODO P2-ALR row 明言 LearningTarget→PIT dataset→training→after-cost challenger artifact），在現有 evidence-only 授權邊界內產出首個全鏈證據包；可證偽：challenger 過不了 WP7 stop-loop 檢定=學習無效證明（同樣有裁決價值）。
- why_not_tried：WP 鏈 operator 指令不鏡像 TODO（07-07），ALR 隊列與 WP 鏈是兩波獨立建設，無 cross-wiring dispatch。
- est_edge：使「學習→盈利效果」首次可裁；一切 AI 活化的證據前置。est_cost：E1 1 sprint，$0 AI。wall_break_prob：high（純接線）。
- how_to_validate：P2-4 acceptance 已含 after-cost challenger artifact；對 artifact 跑 WP2 manifest 驗證器+WP7 review 即閉環。

### O5 [unlock 監測項] 事件軸前提監測：listing effect 減弱的外部信號
- 外部證據：2025-11 起 listing 公告效應減弱案例（SEI/2Z 公告後無顯著漲、informed traders 提前入場，BeInCrypto 2025-11）→ 事件/監管 PARK 軸到期覆核不可拿中期文獻當 premise。
- hypothesis：Bybit 新上市公告後首小時中位數 abs move 仍 >50bps（可證偽 by Gate-B 探針數據）。
- 監測對象/閾值/由誰：Gate-B listing 探針累積的公告→±24h 價格反應分佈（$0 已在累積）；閾值=公告後 1h abs return 中位數 <2× 費用牆（~20bps）連續 3 個月 → 軸降級；AI-E/QC 於 PARK 到期覆核時查。
- est_edge：守住 O1/寬價差 niche 的共同前提。est_cost：$0。wall_break_prob：unknown。regime_caveat：分 regime 統計必要。

### O6 IBKR lane AI-lens 研究 ROI 預備：G4 開通前先定 PIT 特徵契約
- hypothesis：美股 session 風險特徵（overnight gap/sector ETF dispersion/VIX 期限結構）作 crypto regime 分類 PIT 協變量，可提升 down-beta 偽裝判別（06-03/06-13 多軸共同死因）——可證偽：加特徵後 regime 分類 OOS 無提升。
- why_not_tried：G4 首次外接 operator-gated，零數據流；lane enabled=false。
- est_edge：防禦價值向（regime 判別），未知量級 ASSUMPTION。est_cost：$0 AI；E1 契約定義工作——機會=現在定 WP2 契約，G4 一開即 day-1 leak-free 累積。wall_break_prob：unknown。
- how_to_validate：WP2 PIT manifest 定義 stock_etf 特徵表 → 累積 ≥90d → regime 分類 A/B 對比。ADR-0048 邊界內（read-only 研究，禁 order-write/auto-promote）。

---

## 三、外部 Sources
- https://beincrypto.com/crypto-exchange-listing-fails-november-2025/ （listing effect 減弱）
- https://arxiv.org/html/2605.16895 （Alpha Illusion：LLM trading agent 洩漏警告）
- https://arxiv.org/html/2505.16136v1 （GDELT 新聞特徵+XGBoost 含成本 OOS）
- https://arxiv.org/pdf/2508.13635 （ECB 記者會 LLM vol 解讀 corr 0.5）
- https://www.blockchainresearchlab.org/wp-content/uploads/2019/10/Exploring-Market-Reactions-to-Exchange-Listings-of-Cryptocurrencies-BRL-working-paper3.pdf （listing effect 基線文獻）

## 四、裁決摘要
verdict=FINDINGS。守側核心：AI 棧既不燒錢也不賺錢（$0/0 歸因），三把鎖=judge_edge timeout（小時級可修）、標籤斷糧（operator gate 權衡）、L2 operator 一鍵（技術前置已齊）。攻側核心：AI 離開方向判斷位——去解讀層（O1，$0 起步）與搜索空間生成（O2，前提已變）——所有輸出過確定性 math gate；O4 是零市場風險的證據閉環首接線。全部裁決屬 PM/operator，AI-E 不執行。

— AI-E, 2026-07-09
