# FA 業務鏈合併建議 — TODO + QCTODO 統一化

**作者**：FA（Functional Auditor）
**日期**：2026-05-09
**讀者**：PM
**性質**：純 read-only business-chain merge advice（PM 寫 code，PA 寫 architectural merge analysis，FA 寫業務鏈）
**對偶輸入**：TODO.md v18（573 行）+ QCTODO.md（327 行）+ FA business chain validation（5a2dee98）+ FA v3 verification

---

## §1 業務鏈完整度當前真實狀態

當前基準：**業務鏈 ~63%**。8 節點 percent breakdown：

```
自動掃描 95% / 策略選擇 56% / AI 風控 80% / 下單 35% / 止損 95% /
學習 31% / 進化 35% / 觀察 85% → 加權平均 ≈ 63%
```

### 1.1 v3 9 條 sign-off invariant 對應 v18 TODO 的 wave 覆蓋表

| FA-N | v3 invariant | v18 TODO 對應 | 狀態判定 |
|---|---|---|---|
| FA-1 | W-AUDIT-3b runtime smoke 已從 Linux 驗 | `W-AUDIT-3` PARTIAL `da2dba25` + F-01 source/test | **dormant** |
| FA-2 | W-AUDIT-4b 6 表 INSERT 必串行 | `W-AUDIT-4` PARTIAL（V068/V070/V071 reclassification COMMENT）| **dormant**：6 表 INSERT 仍 0 |
| FA-3 | F-08 cron 必 install + 24h fire | `P2-AUDIT-VERIFY-4`（cron not installed）| **partial** |
| FA-4 | W-AUDIT-9 Stage 0 binary fail-closed 不變式保留 | v18 無 W-AUDIT-9 wave | **缺** |
| FA-5 | W-AUDIT-8b/c/d Stage 2 abort gate 必明文 | v18 W-AUDIT-8a SPEC PHASE | **缺**：abort gate 未進 spec |
| FA-6 | D-02 Layer 2 manual SOP 不違反 ADR-0020 | v18 ADR-0020 已 land；無 SOP | **缺** |
| FA-7 | W-AUDIT-6 砍 6 polishing K -12 trial 量化記入 | v18 W-AUDIT-6 SOURCE/TEST CLOSED | **缺**：DSR penalty 量化結論未記 |
| FA-8 | v2-NEW-1 strategist cap 30%→50% 補 ADR-0021 | v18 P0-V2-NEW-2 DONE 但 0 ADR | **缺**：v3 P0-V3-ADR-0021-ARCH-04 ACTIVE |
| FA-9 | 6 表 0 INSERT 18 天無變動必 owner + ETA | v18 W-AUDIT-4 PARTIAL（無 escalation）| **缺**：未升 P1 individual ticket |

**結論**：v3 9 條 invariant 有 **5 條 v18 完全缺**。

### 1.2 D-XX dormant alpha owner 覆蓋

| D-XX | inventory 描述 | v18 / QCTODO owner 狀態 |
|---|---|---|
| D-01 | fake-live observability（W-AUDIT-3b）| QCTODO Track W ✅ owner = E1 |
| D-02 | ML 基座 wire | QCTODO B 群 B-M1/B-M2/B-M3 ✅ |
| D-04 | docs hygiene（W-AUDIT-1d）| v18 W-AUDIT-1 source-closed ✅ |
| D-05 | promotion_pipeline production caller | QCTODO C 群 C-A6 + C-D-05-wire ✅ |
| D-06 | promotion evidence（DSR/PBO/CPCV）| QCTODO C-A6 ✅ |
| D-07 | GUI 修整 | v18 W-AUDIT-7 ACTIVE + QCTODO §1 N+2 |
| D-08a | AlphaSurface Foundation | QCTODO D 群 W-AUDIT-8a ✅ |
| D-08b/c/d | 3 alpha source candidate | QCTODO A 群 A4-A/B/C ✅ |
| D-08e | Strategist→Analyst propose | QCTODO W-AUDIT-8e (R-2) Sprint N+4 |
| D-08f | Hypothesis Pipeline R-3（含 W-AUDIT-4 併入）| QCTODO W-AUDIT-8f (R-3) Sprint N+5 |
| D-08g | Per-alpha-source Live Promotion Gate R-4 | QCTODO W-AUDIT-8g (R-4) defer N+7 |
| D-09 | Graduated Canary Foundation | QCTODO W-AUDIT-9 ✅ |
| D-11 | 性能 W-AUDIT-5b | v18 W-AUDIT-5 ACTIVE ✅ |
| D-12 | Portfolio tail risk gate / cost edge | v18 W-AUDIT-6c DONE / cea-env restart 待 |
| D-13 | Cognitive Modulator | DORMANT（不解，至 N+8+）|
| D-14 | DreamEngine | DORMANT（ADR-0020 + Foundation Model 未 ready）|
| D-15 | OpportunityTracker 全 Agent 注入 | **無 owner**（建議 PM 標 dormant）|
| D-16 | openclaw_core 9 模組 sunset | v18 ADR-0015 標 sunset，N+6+；**無 owner** |
| D-17 | Layer 2 自主推理循環 | **永久 dormant by ADR-0020** |

**Owner 缺口**：D-15 + D-16 兩條 owner 缺；建議標 dormant + reason。

---

## §2 TODO + QCTODO 業務鏈相關項目歸併（8 項對照）

### 2.1 6 表 0 INSERT
- v18 W-AUDIT-4 framing：wave-level partial 模糊
- QCTODO B 群 + 4b 串行 push back：B-M1/B-M2/B-M3 三條 explicit
- **FA 統一**：merged TODO §P1 加 `P1-INSERT-PATH-1..6` 6 條 individual ticket（每條 owner + ETA + sequential dependency）；W-AUDIT-4 改為「container wave」。

### 2.2 F-08 5 ML cron install
- v18：`P2-AUDIT-VERIFY-4` source open / runtime not installed
- QCTODO：`[Xc] ml_training_cron_active` healthcheck PASS
- **FA 統一**：merged TODO 開 `P1-CRON-ML-1`（operator-authorized action，附 healthcheck `[Xc]` 24h fire criteria）

### 2.3 ExecutorAgent shadow_mode
- v18 W-AUDIT-3：PARTIAL，runtime fail-closed metrics 未驗
- QCTODO W-AUDIT-9：graduated canary T1-T7 = stage-aware
- **FA 統一**：merged TODO 把 W-AUDIT-3 + W-AUDIT-9 合併為 `Track-Executor-Path`：3b runtime smoke 必先 land → 9 T1-T7。Cross-wave conflict #2 必明文。

### 2.4 DSR/PBO promotion gate
- v18 W-AUDIT-6c：DONE source/test (`cc6476dd`)；runtime apply 待
- QCTODO C-A6：DSR/PBO/CPCV evidence pipeline 自動化 + `trial_sharpes` 持久化
- **FA 統一**：merged TODO 把 W-AUDIT-6c + C-A6 + C-D-05-wire 合併為 `Track-Promotion-Pipeline` sequential（A6 first → D-05-wire → D-12）。**A6 必先 land 才能 D-05-wire**（race condition）。

### 2.5 AlphaSurface
- v18：0 條目（W-AUDIT-8a SPEC PHASE 剛開）
- QCTODO W-AUDIT-8a：全新 wave，Phase A → D × 4 sprint × ~40 person-day
- **FA 統一**：merged TODO 必新增 `Track-Alpha-Surface` section，**alpha-bearing wave**（影響 PnL）標記重要。對應 D-08a。

### 2.6 5 策略 verdict（W-AUDIT-6 mid-ground）
- v18 W-AUDIT-6：SOURCE/TEST CLOSED by AMD-2026-05-09-02（Option ii）
- QCTODO W-AUDIT-6 mid-ground：保 6 / 砍 6 explicit；DSR K -12 量化結論
- **FA 統一**：merged TODO 保留 W-AUDIT-6 SOURCE/TEST CLOSED + 新增「砍 6 子項 grep blacklist」明文 + K -12 trial DSR penalty 量化結論。

### 2.7 D-05-wire promotion_pipeline 0 caller
- v18：隱含於 W-AUDIT-6c
- QCTODO C-D-05-wire：`set_promotion_pipeline()` singleton init 0.5 person-day
- **FA 統一**：merged TODO 列為 `Track-Promotion-Pipeline` 依附項（A6 後）。

### 2.8 attribution_chain_ok 0.5%
- v18 P0-EDGE-1 ACTIVE：generic
- QCTODO B 群 root cause：MIT v3 `label_close_tag` NULL 98.9%；1-day fix 最高 ROI
- **FA 統一**：merged TODO 在 P0 段新增 `P0-MIT-LABEL-CLOSE-TAG-1` ACTIVE 1-day fix；P0-EDGE-1 不變但加 cross-reference。**MIT root cause 不可被 P0-EDGE-1 generic 吸收**。

---

## §3 業務鏈 8 節點 gap 識別（merged TODO 後）

### 自動掃描（95%）— 無顯著 gap

### 策略選擇（56% → 預期 ~64% by N+5）
- A 群 A4-A/B/C IMPL 後 +2-5%；W-AUDIT-6d bb_reversion verdict +1%；W-AUDIT-8e Strategist alpha-source orchestrator +2%
- **gap**：3 alpha source 候選 0% PASS 率歷史，merged TODO 必含 Stage 2 abort gate 條文（FA-5）

### AI 風控（80%）
- **gap**：A6 → D-05-wire → D-12 sequential 鏈路明文化（不可並行）

### 下單（35% → 預期 ~50% by N+3）
- W-AUDIT-9 T1-T7 land 後 Stage 1+2 demo 真 spawn execute_via_ipc → +13-15%（standalone milestone）
- **gap**：v18 完全沒這節點 +%。merged TODO 必把 W-AUDIT-9 標 alpha-bearing milestone

### 止損（95%）— 無

### 學習（31% → 預期 ~47% by N+5）
- B 群 N+0 land + cron install + N+1 24h fire = +12%；MIT label_close_tag fix +3%
- **gap**：v18 6 表 INSERT path 18 天 0 進度 = 結構性 gap；必升 P1 individual ticket（FA-9）

### 進化（35% → 預期 ~47% by N+5）
- C 群 + W-AUDIT-9 IMPL = +9%；A 群 Stage 2 PASS = +2-3%
- **gap**：W-AUDIT-9 standalone milestone（FA-1）+ Stage 2 abort gate（FA-5）必 explicit

### 觀察（85% → 預期 ~90% by N+5）
- N+1 W-AUDIT-1d + N+4 Track W 收尾 +5%
- 無 hard gap

**結構性 gap 3 條**：
1. 6 表 INSERT path 18 天 0 進度（升 P1 individual ticket）
2. W-AUDIT-9 Stage 2 abort gate 條文
3. attribution real root cause（label_close_tag NULL 98.9%）— 1-day fix 必獨立 P0

---

## §4 22 條 Final Invariant（PA 11 + FA 9 + merge 新 2 deduplicate）

### 結構（5 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 1 | Sprint N+0 W-AUDIT-9 7 sub-task 全 land + `[58]` PASS + `governance.canary_stage_log` active | git log + healthcheck | PA-1 |
| 2 | Sprint N+0 W-AUDIT-8a Phase A trait 升級 land + 5 策略 byte-identical replay PASS + cargo build release 綠 | E2E byte-diff test | PA-2 |
| 3 | W-AUDIT-6 mid-ground 6 保子項 land + 砍 6 子項 grep blacklist 0 命中 | grep audit + commit | PA-3 |
| 4 | W-AUDIT-9 Stage 1 cohort active + 7d wall-clock 觀察期未提前升級 | governance.canary_stage_log + auto-promote 條件 | PA-4 + FA-Critique-2 |
| 5 | W-AUDIT-4b 6 表 INSERT path 已串行 IMPL（feature_baselines first → mlde_edge_training_rows → scorer_predictions → 3 advisor 並行）| commit ordering 驗 + schema test | FA-2 |

### 安全（5 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 6 | DOC-08 §12 9 條安全不變量未違反 | grep + healthcheck | PA-5 |
| 7 | live boundary 5-gate 所有 stage active 期間未繞過 | LiveDemo authorization 簽名+TTL+env_allowed | PA-6 |
| 8 | §二 16 根原則合規（especially 1/4/5/6/9）| AMD-2026-05-09-03 §6.3 校核 | PA-7 |
| 9 | shadow_mode_provider exception path fail-closed Stage 0（**不是** Stage 1）| E2 review T3 + unit test | PA-8 |
| 10 | W-AUDIT-9 Stage 0 binary fail-closed 不變式保留（Live boundary 5-gate / SM-04 / DOC-08 / §二 4 範圍均不被 graduated canary 觸碰）| 4 範圍逐條 invariant test | FA-4 |

### 治理（7 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 11 | canary_stage_log.decision_lease_id for manual_promote PG NOT NULL 強制 | V0XX migration CHECK | PA-9 |
| 12 | healthcheck `[58]` 對 SM-04 ≥ L3 escalate 必 hard FAIL → 觸 stage = 0 rollback | `[58]` IMPL 對 SM-04 L3 邏輯 explicit + unit test | PA-10 |
| 13 | A 群 3 新策略 IMPL 後 declared_alpha_sources() 與真實邏輯對齊 | grep ctor + QC review sign-off | PA-11 |
| 14 | W-AUDIT-8b/c/d sequence 必含 Stage 2 abort gate（C IMPL 後 Stage 2 demo 14d gross < 0 → A 群 8b/c 重評）| Sprint sign-off report 明文 | FA-5 |
| 15 | D-02 Layer 2 manual SOP 不違反 ADR-0020（manual probe 不可自動化為 cron / event-trigger）| code grep audit | FA-6 |
| 16 | W-AUDIT-6 mid-ground 砍 6 polishing K -12 trial DSR penalty 量化結論記入 sign-off report | sign-off report 明文 | FA-7 |
| 17 | v2-NEW-1 strategist cap 30%→50% 補 ADR-0021 | ADR-0021 land + commit | FA-8 |

### 監督 / record（5 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 18 | F-08 5 ML cron crontab -e install + 24h 真 fire 驗 | `[Xc] ml_training_cron_active` PASS | FA-3 |
| 19 | 6 表 0 INSERT 18 天無變動 gap 必有 owner + ETA（individual P1 ticket）| TODO entry P1 標記 | FA-9 |
| 20 | W-AUDIT-3b runtime smoke 已從 Linux 驗（pytest test_executor_fail_closed + engine restart 後 [55] chains_with_lease > 0）| ssh trade-core run + log | FA-1 |
| 21 | **【merge 新】** P0-MIT-LABEL-CLOSE-TAG-1 1-day fix 已 IMPL + attribution_chain_ok 24h ≥ 5%（從 0.5% → 5%）| `[42b]` PASS + writer fix commit | merged FA |
| 22 | **【merge 新】** Sprint N+0/N+2/N+5 capacity = 5 active + 1 stand-by E1 explicit recorded（不允許「臨時降級為 5/5 HOT」）| Sprint sign-off report 明文 | merged FA |

**git status clean 強制**（CLAUDE.md §七 P0-GOV-3）：merge 後 mandatory，process gate（不算 22 條 invariant 之內）。

---

## §5 業務鏈視角 TODO 重寫關鍵原則（6 條）

### 5.1 Wave 必標 alpha-bearing vs alpha-neutral

每 wave header 加 tag：
- **【alpha-bearing】**：W-AUDIT-8a-g / A4-A/B/C / W-AUDIT-9 Stage 1 launch
- **【alpha-neutral】**：W-AUDIT-2 / W-AUDIT-1d / W-AUDIT-7c / Track W maintenance

理由：避免「W-AUDIT-6 已 SOURCE/TEST CLOSED 應該開始盈利」誤解。

### 5.2 Dormant D-XX explicit + reason

merged TODO 必有 Dormant Section 顯式列：

```
| D-XX | Description | Status | Reason | Earliest reactivate |
| D-13 | Cognitive Modulator | DORMANT | 3-Tier 數據源未接齊 + alpha 無依賴 | Sprint N+8+ |
| D-14 | DreamEngine | DORMANT | Foundation Model + L4 meta-learning 未 ready | long-tail |
| D-15 | OpportunityTracker 全 Agent 注入 | DORMANT | 不影響 supervised live | Sprint N+5 可選 |
| D-16 | openclaw_core 9 模組 sunset cleanup | DORMANT | ADR-0015 已標 permanent sunset | Sprint N+6+ |
| D-17 | Layer 2 自主推理循環自動觸發 | PERMANENT DORMANT | ADR-0020 manual+supervisor-only | 不解 |
```

### 5.3 W-AUDIT-6 砍 6 子項 grep blacklist

```markdown
### W-AUDIT-6 砍 6 polishing — DEFERRED / REJECTED 2026-05-09 (E2 grep blacklist; 命中即 reject merge)

1. ❌ ma_crossover 5m 反向觀察重做
2. ❌ bb_breakout Donchian 5m optimization sweep
3. ❌ grid_trading symbol expansion ORDIUSDT → 5
4. ❌ funding_arb v3 MA pair retry
5. ❌ strategy_params 4×5 hardcoded → 動態 Sharpe-by-regime
6. ❌ 5 策略 cost_gate threshold 個別 tune

DSR penalty: K -12 trial; mu_0 從 ~2.83 降至 ~2.27。是 DSR 數學意義 right move，不是省工時妥協。
```

### 5.4 Sprint Milestone Banner（業務鏈 63% → 85-89%）

| Sprint | Week | 主題 | 業務鏈 milestone |
|---|---|---|---|
| N+0 | W1-W2 | FOUNDATION HEAVY | 63→65% |
| N+1 | W3-W4 | ALPHA SURFACE PANEL WIRING | 65→70% (Stage 1 standalone +5-7%) |
| N+2 | W5-W6 | A4-C IMPL + 8a Phase D + Stage 2 demo cohort 14d | 70→76% |
| N+3 | W7-W8 | A4-B IMPL + R-2 spec + Stage 3 demo full | 76→80% |
| N+4 | W9-W10 | R-3 spec + A4-A IMPL + 8e IMPL + Track W 收尾 | 80-83% |
| N+5 | W11-W12 | R-3 IMPL + R-4 spec + first per-alpha-source supervised live | **85-89%** |

### 5.5 Cross-wave Conflict 4 條繼承

| # | 衝突 | 解 |
|---|---|---|
| 1 | 8a Phase A migration ↔ W-AUDIT-6 mid-ground 5 策略改動 | 序列化（先 6 mid-ground，再 8a Phase A）|
| 2 | W-AUDIT-9 T3 ↔ ExecutorAgent shadow_mode 接線 | T3 結束前 shadow=true 不動 |
| 3 | W-AUDIT-8a Phase B+C ↔ W-AUDIT-5 性能 wave | Phase B+C 並行於 N+1，5 性能 reserved slot |
| 4 | A 群 3 新策略 ↔ W-AUDIT-9 Stage 1 cohort 選擇 | A4-C 用 Stage 1 paper cohort 入場 |

### 5.6 PA Push Back / FA Push Back 明文保留

繼承到 merged TODO「歷史治理決策」段，避免後續 session 不知道為何 capacity = 5+1。

---

## §6 PM Sign-off 業務鏈視角額外 5 條 check

### 6.1 alpha-bearing wave 是否真標 alpha-bearing
- 動作：grep `【alpha-bearing】` tag
- 預期：W-AUDIT-8a / 8b/c/d / A4-A/B/C / W-AUDIT-9 Stage 1 / 8e/f/g 全標
- 反例：W-AUDIT-9 標 alpha-neutral = FAIL

### 6.2 Dormant D-XX explicit + reason 完整
- grep D-13/14/15/16/17 5/5 命中 + reason + earliest reactivate

### 6.3 砍 6 子項 grep blacklist 6/6 explicit
- grep 6 條 ❌ 命中 6/6

### 6.4 Sprint milestone 業務鏈 % 符合 FA 預測帶
- N+0 63→65% / N+5 85-89% match

### 6.5 P0-MIT-LABEL-CLOSE-TAG-1 獨立 P0 ticket
- grep P0-MIT-LABEL-CLOSE-TAG-1 在 P0 段命中 + cross-reference P0-EDGE-1
- 反例：被 P0-EDGE-1 generic 吸收 = FAIL

**FA Sign-off 條件**：§4 22 invariant + §6 5 業務鏈 check 全 PASS = FA 業務鏈視角 GO。

---

## §7 FA 結論

**核心訊息**：

1. TODO + QCTODO merge 後業務鏈不會自動進步 — 必須串行 IMPL FA-1/FA-2/FA-9 三條結構性 gap
2. 22 條 final invariant 是不可動 SSOT
3. Dormant 5 條 D-XX 必 explicit
4. 砍 6 子項 explicit blacklist + K -12 量化結論記入
5. W-AUDIT-9 Stage 1 launch standalone milestone（+5-7% 不混 Track A funding skew）
6. P0-MIT-LABEL-CLOSE-TAG-1 1-day fix 必獨立 P0
7. Sprint capacity = 5 active + 1 stand-by 必明文（operator 已拍板 (a)，不可隨意降級）
8. Cross-wave conflict 4 條必繼承
9. Sprint milestone 業務鏈 % banner 必含

**FA 對 merged TODO 的 5 條 must-haves**：
1. Sprint Milestone Banner（§5.4）
2. Dormant Section 5/5 explicit（§5.2）
3. W-AUDIT-6 砍 6 grep blacklist 6/6 explicit + K -12（§5.3）
4. 22 條 final invariant 表（§4）
5. Cross-wave conflict 4 條（§5.5）

**對 Operator 的最後提醒**：
- TODO 重寫不是行政動作；是治理動作
- 22 條 invariant 任一缺失 = 後續 sub-agent 用「我以為 OK」當理由繞過 sign-off
- merged TODO 完成後 6 個月內，operator 必能用 grep 驗每條 invariant；否則 = 治理失效

---

**FA AUDIT DONE**
