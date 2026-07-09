# FA 業務鏈視角 · 全 Dispatch 工程安排驗證報告

**作者**：FA（Functional Auditor）
**日期**：2026-05-09
**對偶輸入**：PA dispatch DAG（並行撰寫，§6 補位）+ Operator 拍板的 4-agent loss audit dispatch list
**前序**：v3 verification（業務鏈 ~63%）+ PA `2026-05-09--full_audit_pa_fix_plan_v2.md` + W-AUDIT-8a SPEC + AMD-2026-05-09-03 graduated canary
**讀者**：PM（sign-off 前讀）/ Operator
**性質**：業務鏈視角的 milestone 預測 + Layer 2 SOP + W-AUDIT-6 mid-ground 細項影響 + 候選 alpha source 貢獻 + 對 PA DAG 的業務鏈 critique + sign-off pre-flight

---

## §1 業務鏈完整度 Sprint Milestone Breakdown

當前基準：**v3 ~63%**（v1 52% → v2 58% → v3 63%）。目標終點：**85%+** = 第一個 alpha-bearing 策略走完 Stage 2 demo 14d gross > 0 + Track W 7 wave 全收 + W-AUDIT-9 graduated canary IMPL active + Track A R-3 Hypothesis Pipeline 寫端真活。

下表「+%」是 FA 業務鏈視角預測（基於 8 節點加權公式 = 自動掃描 + 策略選擇 + AI 風控 + 下單 + 止損 + 學習 + 進化 + 觀察），不是 PA 工時或代碼覆蓋率。每 sprint 假設 ~5-7 working day。

### Sprint N+0（當前 → +7 day，~Week 1）— Track W kick-off

| 動作 | D-XX 解鎖 | 業務鏈 + |
|---|---|---|
| W-AUDIT-3b ExecutorAgent runtime smoke + fail-closed metrics 驗 | D-01 fake-live observability | 下單 35→38（+3）|
| W-AUDIT-1d cleanup（殭屍引用 + Last Updated header + worklogs 12 天斷層）| D-04 docs hygiene | 觀察 85→86（+1）|
| W-AUDIT-9 T1+T2 並行（Rust schema `executor_canary_stage` + V### migration）| D-09 graduated canary infra（前置）| 進化 35→36（+1）|
| W-AUDIT-8a Phase A SPEC review（PA + FA + QC 三角）| D-08a alpha surface foundation 開啟 | 0（spec phase）|

**Sprint N+0 結束預期**：~64-65%。**業務鏈瓶頸**：6 表 0 INSERT 仍未動（學習仍 31%）。

### Sprint N+1（+8 → +14 day，~Week 2）— W-AUDIT-4b INSERT path 第一波 + W-AUDIT-9 T3-T6

| 動作 | D-XX 解鎖 | 業務鏈 + |
|---|---|---|
| W-AUDIT-4b 6 表 INSERT path 串行 IMPL（feature_baselines first → mlde_edge_training_rows → scorer_predictions → 3 advisor 並行）| D-02-runtime ML 基座 wire | 學習 31→39（+8）|
| W-AUDIT-9 T3 `executor_config_cache.py` stage-aware（在 W-AUDIT-3b 完成後）| D-09 graduated canary | 下單 38→40（+2）|
| W-AUDIT-9 T6 `LeaseScope::CanaryStagePromotion` GUI manual stage promotion 動作 | D-09 graduated canary | 進化 36→37（+1）|
| W-AUDIT-8a Phase A IMPL start（Rust `AlphaSurface<'a>` 結構 + `AlphaSourceTag` enum + `Strategy` trait `declared_alpha_sources()`）| 半 D-08a | 0（infra）|

**Sprint N+1 結束預期**：~68-70%。**業務鏈瓶頸**：W-AUDIT-3 runtime fail-closed metrics 仍未從 Linux runtime spot-check（v3 outstanding）；W-AUDIT-4b 6 表 INSERT path 是「writer chain wire」，row count 不一定立即 > 0（cron 24h fire 需另算）。

### Sprint N+2（+15 → +21 day，~Week 3-4）— Cron install + W-AUDIT-9 IMPL land + W-AUDIT-8a Phase B

| 動作 | D-XX 解鎖 | 業務鏈 + |
|---|---|---|
| `crontab -e` install F-08 5 ML cron + 24h fire 驗 + V079 DB apply + rebuild restart | 解 D-02-cron / D-06 promotion evidence | 學習 39→43（+4）/ 進化 37→40（+3）|
| W-AUDIT-9 T4+T5（auto-rollback FSM + IPC schema）+ T7 regression test | 完成 D-09 | 下單 40→42（+2）|
| W-AUDIT-8a Phase B（Tier 2 funding_curve + OI delta panel writer + V### migration retention） | 半 D-08a | 0（infra；策略未消費）|
| W-AUDIT-6c runtime apply（V079 DSR/PBO + Kelly RiskConfig + portfolio VaR/CVaR）| D-05-half | 進化 40→42（+2）|
| W-AUDIT-7c GUI/AI（A3 18 ❌ 大半 + AI-E F-07 ANTHROPIC_API_KEY + cea-env restart）| D-07 GUI / D-12 cost edge | 觀察 86→88（+2）|

**Sprint N+2 結束預期**：~74-76%。**重要里程碑**：W-AUDIT-9 IMPL land = **P0-EDGE-1 雞蛋死循環解套**首次出現可信路徑（Stage 1 paper / Stage 2 single-symbol-demo 觀察期啟動）。

### Sprint N+3（+22 → +28 day，~Week 4-5）— W-AUDIT-9 Stage 1 開觀察 + W-AUDIT-8b funding skew start

| 動作 | D-XX 解鎖 | 業務鏈 + |
|---|---|---|
| W-AUDIT-9 Stage 1 paper 觀察（取代 binary fail-closed default；7d SLA）— **standalone milestone**，FA 估 +5-7% | D-09-stage1 | 進化/下單 +5-7（standalone）|
| W-AUDIT-8b candidate A funding skew spread IMPL（QC 設計 + E1×2 寫 + E4 e2e）走 Stage 1 入場 | 半 D-08b | 策略選擇 56→58（+2）|
| W-AUDIT-5b deferred performance（deepcopy / orjson / RwLock / event_consumer 拆）| D-11 性能 | 觀察 88→89（+1）|
| W-AUDIT-6d bb_reversion verdict + portfolio_var min_obs review | D-05 收尾 | 策略選擇 58→59（+1）|
| W-AUDIT-8a Phase C（Tier 3 microstructure: orderflow + liquidation pulse 接 Bybit `allLiquidation` WS）| 半 D-08a | 0（infra）|

**Sprint N+3 結束預期**：~80-82%（含 W-AUDIT-9 standalone milestone 的躍升）。

### Sprint N+4（+29 → +35 day，~Week 5-6）— Stage 2 single-symbol-demo + Track W 收尾

| 動作 | D-XX 解鎖 | 業務鏈 + |
|---|---|---|
| W-AUDIT-8b funding skew Stage 2 single-symbol-demo 14d 觀察開始 | 半 D-08b | 0（觀察期內）|
| W-AUDIT-8c liquidation cluster IMPL + Stage 1 入場 | 半 D-08c | 策略選擇 59→60（+1）|
| W-AUDIT-8a Phase D（Tier 4 EventAlert from Scout intel + RegimeTag + Sentiment stub）| 完成 D-08a | 0（infra）|
| Track W 全 closed：W-AUDIT-3/4/5/6/7/1/5b 全 PARTIAL→DONE | D-01 至 D-07 全收 | 學習 43→44（+1）/ 觀察 89→90（+1）|
| 6 表 24h cron fire row count > 0 驗 | D-02 完整收 | 學習 44→45（+1）|
| **D-08e Strategist→Analyst propose 通道 promote 至此 sprint**（與 Track W 並行）| D-08e early | 進化 +1 |

**Sprint N+4 結束預期**：~83-85%。**Track W 全收 = supervised live 規劃帶合規 / 安全 / 可觀測三件配齊**。

### Sprint N+5（+36 → +42 day，~Week 6-7）— Stage 2 PASS + supervised live 提案

| 動作 | D-XX 解鎖 | 業務鏈 + |
|---|---|---|
| W-AUDIT-8b funding skew Stage 2 14d PASS（demo gross > 0；至少 30 fill）| D-08b 完整 | 策略選擇 60→63（+3）/ 進化 45→47（+2）|
| W-AUDIT-8d BTC→Alt lead-lag IMPL + Stage 1 入場 | 半 D-08d | 策略選擇 63→64（+1）|
| W-AUDIT-8e Strategist→Analyst propose 通道 完整 + Analyst L2-L3 hypothesis IMPL | D-08e | 進化 47→49（+2）|
| W-AUDIT-8f Hypothesis Pipeline first-class object（W-AUDIT-4b PASS 後）| 半 D-08f | 學習 45→47（+2）|

**Sprint N+5 結束預期**：~87-89%。**這是 supervised live 真實可放權的業務鏈水位**。

### Sprint N+6 及之後（仍保 dormant 或長尾的 D-XX）

- **D-13 Cognitive Modulator 中期 defer**：與 alpha source 升級無依賴，3-Tier `consecutive_loss / weekly_pnl` 數據源仍未接齊；FA 認可繼續 dormant 至 Sprint N+8 之後再評。
- **D-14 DreamEngine 完整自主進化**：依賴 Foundation Model + L4 跨 strategy meta-learning（ADR-0020 限制 manual）；Sprint N+5 不解，long-tail。
- **D-15 OpportunityTracker 全 Agent 注入**：Sprint N+5 可選做（Scout 注入 50%，Strategist 0%，Guardian 0%）；不影響 supervised live 評估。
- **D-16 openclaw_core 9 模組 sunset 全執行**：ADR-0015 已標 permanent sunset candidates；FA 認可 Sprint N+6 後做 cleanup commit，不前置。
- **D-17 Layer 2 自主推理循環自動觸發**：ADR-0020 永久標 manual+supervisor-only；FA 認可永久 dormant，**不解**。

---

## §2 D-02 Layer 2 Manual 7d 試運行 SOP（Operator 自執行）

**目標**：在不違反 ADR-0020（Layer 2 manual+supervisor-only）的前提下，operator 每天手動觸發 1 次 L1 triage，觀察 cost vs avoided-loss 比例。

**FA 立場**：D-02 SOP 是 Layer 2 escalation 路徑的「low-volume probe」，**不是自主循環**。每天 1 次 manual call 是設計意圖；不可寫成 cron / scheduler / event-trigger（會違 ADR-0020）。

### Step 1：API key 取得（~15 min）

1. Operator 前往 [Anthropic Console](https://console.anthropic.com/)
2. Settings → API Keys → Create Key
3. 命名：`openclaw-layer2-manual-7d-trial`
4. 限額：建議 monthly budget = $5（7d × ~$0.30/day Haiku-3.5 + ~$0.30/day Sonnet 緊急 escalation = $4.20 上限）
5. 複製 `sk-ant-xxx...` key（只顯示一次）

### Step 2：寫入 `provider_keys_store`（~5 min）

**路徑**：`$OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key`

```bash
mkdir -p "$OPENCLAW_SECRETS_ROOT/secret_files/anthropic"
echo "sk-ant-xxx..." > "$OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key"
chmod 600 "$OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key"
```

**Python 端讀取**：`provider_keys_store.py:get_anthropic_key()` 已實作；不需新代碼。

**驗證**：

```bash
python3 -c "from app.providers.anthropic_client import test_connection; test_connection()"
```

預期 output：`200 OK · Claude API reachable · model_list=['claude-haiku-3.5','claude-sonnet-4.5']`

### Step 3：Manual trigger 7d daily SOP（每天 1 次）

**時間**：每天 09:00 UTC（demo collection window 之前）/ 或任意 operator 方便時間，不需固定。

**動作**：

```bash
ssh trade-core
curl -X POST http://localhost:8000/api/v1/layer2/run_session \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -d '{
    "trigger_kind": "manual_daily_probe",
    "scope": "L1_triage",
    "max_cost_usd": 0.50
  }'
```

**SOP 注意**：
- 每次 call 只做 L1 triage（成本控制 + complexity 評估）；**禁** manual 觸發 L4 跨 strategy escalation（會破 budget）
- 每次 call 後寫入 `decision_outcomes.layer2_manual_probe_log`（schema 已 active）

### Step 4：7d 觀察 metric

| 指標 | 採集 | 目標 |
|---|---|---|
| `cost_today_usd` | `SELECT SUM(cost_usd) FROM ai_costs WHERE date=today AND model LIKE 'claude%'` | < $0.50/day |
| `decisions_assisted_n` | `SELECT COUNT(*) FROM decision_outcomes WHERE layer2_assisted=true AND date=today` | 1-3 / day |
| `avoided_loss_estimate_usdt` | manual review GUI tab `learning/layer2_review` | > 2× cost_today |
| `false_positive_rate` | manual rate 0-1 (operator 主觀) | < 30% |

**累計 7d**：`cumulative_cost` 預期 $2-4；`cumulative_alpha_contribution` 預期 +2-5 USDT/week。

### Step 5：Pass / Fail

**Pass**：`alpha > 2× cost` ratio + `false_positive_rate < 40%` + 0 critical incident
**Fail**：`alpha < cost` 或 `false_positive_rate > 60%` 或 ≥ 1 件 layer2 建議導致 > 5 USDT 虧損

### Step 6：Fail rollback

```bash
rm "$OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key"
ssh trade-core "bash helper_scripts/restart_all.sh --keep-auth"
```

### 預期 alpha contribution

**FA 估算**：+2-5 USDT/week（保守）。如 7d < 1 USDT/week，建議 abort（manual 對 operator 是 fixed cost）。

---

## §3 W-AUDIT-6 Mid-ground 細項業務鏈影響

### 保 6 結構性子項

| 子項 | 業務鏈 % | DSR K Δ | L2 reach |
|---|---|---|---|
| DSR/PBO 自動化 evidence push | 進化+2 / 學習+1 | K +1 | Sprint N+5 W-AUDIT-8f 後接 |
| Kelly RiskConfig SSOT | 下單+1 | K +0 | 不接（風控側）|
| funding_arb retire + ADR-0018 | 策略選擇-2 / 風險側+1 | K -1 | 已 final |
| portfolio VaR/CVaR/EVT promotion gate | 進化+2 | K +1 | W-AUDIT-8b/c/d 觸發 |
| portfolio_var min_obs=200 review | 進化+0.5 | K +0 | 不接 |
| bb_reversion verdict（pair MA）| 策略選擇+1 | K +0 | Sprint N+5 W-AUDIT-8e 後重評 |

**保 6 合計**：**+5.5%**

### 砍 6 polishing 子項

| 子項 | 業務鏈 % | DSR K Δ | L2 reach |
|---|---|---|---|
| ma_crossover 5m 反向觀察重做 | 0 | K -1 | 不接 |
| bb_breakout Donchian 5m sweep | 0 | K -3 | 不接 |
| grid_trading symbol expansion ORDIUSDT→5 | 0 | K -5 | 不接 |
| funding_arb v3 MA pair retry | 0 | K -1 | 不接 |
| strategy_params 4×5 hardcoded sweep | 0 | K -0 | 不接 |
| 5 策略 cost_gate threshold tune | 0 | K -5 | 不接 |

**砍 6 合計**：**0%**（避 sweep noise +1.5% 假進度消除）

### DSR Multiple Testing Penalty 量化

- 保 6: K +3 trial
- 砍 6: K -15 trial
- **Net: K -12 trial**

DSR 公式 `mu_0 = sqrt(2 × ln(K))` 修正項。K 從 ~25 降至 ~13 → `mu_0` 從 ~2.83 降至 ~2.27 → DSR PASS threshold 對 5 策略 sharpe ~0.5 的真實要求從「需大樣本看出 0.56」降到「需大樣本看出 0.50」。

**FA Push back**：mid-ground 砍 6 polishing **正是 DSR 數學意義的 right move**。PM sign-off 必明文記入 K -12 量化結論，避免後續 polishing backlog 重新 lobby 時被當「省工時妥協」回擊。

---

## §4 D-05-wire / A6 / D-12 Dependency 鏈路

| Step | 動作 | 業務鏈 + | 解鎖下一步 |
|---|---|---|---|
| 1 | A6 DSR/PBO 自動化 land（V079 apply + edge_estimator_scheduler.py 真 push promotion evidence + cron 24h fire 驗）| 進化+2 / 學習+1 | D-05-wire 可拉 production caller |
| 2 | D-05-wire（PromotionPipeline production caller 接 V079 evidence；E1 寫 `_compute_promotion_evidence()` + `_route_to_promotion_pipeline()` callsite）| 進化+2 / 策略選擇+1 | D-12 自動 trigger |
| 3 | D-12 Portfolio tail risk gate（W-AUDIT-6c portfolio VaR/CVaR/EVT 已 IMPL；D-05-wire 後 promotion gate 自動把 portfolio_tail_risk 列為強制 check）| 進化+1 / 風險側+1 | 解 P0-EDGE-1 evidence 收集路徑 |

**累計 +8% 業務鏈進化節點**。

**FA Push back**：A6 必先 land 才能 D-05-wire；當前 v3 標 V079 source/test closed 但 **runtime apply 0**。Sprint N+0 或 N+1 V079 apply 列為 sequential blocker，不可並行 D-05-wire / D-12（會 race condition）。

---

## §5 New Strategy Candidate（A/B/C）對業務鏈 % 貢獻估算

PA dispatch list A 群並行 PA spec → IMPL 順序 C/B/A。

### 候選 A — Funding Skew Spread（W-AUDIT-8b，IMPL 順序 #3）

| 維度 | 貢獻 |
|---|---|
| (a) Alpha source layer | Tier 2 cross-section panel；首次 25-symbol funding curve 升 first-class → 業務鏈 +1.5% |
| (b) Dormant strategy slot 解鎖 | 補 funding_arb retire 後空缺 → 策略選擇 +1.5% |
| (c) Portfolio diversification ρ | ρ ~0.1 → portfolio Sharpe +0.5% |
| **總計** | **+3.5%**（樂觀，需 Stage 2 PASS 驗證）|

**FA 風險**：funding skew Bybit 沒 first-class API；需 client-side aggregate 25 symbol per-hour funding fetch（每天 600 calls）。如 BB rate limit 緊，fallback 5-symbol panel → +2%。

### 候選 B — Liquidation Cluster（W-AUDIT-8c，IMPL 順序 #2）

| 維度 | 貢獻 |
|---|---|
| (a) Alpha source layer | Tier 3 microstructure；Bybit `allLiquidation` WS 真接 → +2% |
| (b) Dormant strategy slot 解鎖 | event-trigger 模式（與 5 既存 reactive 不同） → 策略選擇 +1% |
| (c) Portfolio diversification ρ | ρ ~0.05 → portfolio Sharpe +0.7% |
| **總計** | **+3.7%**（最高潛力）|

**FA 風險**：latency 敏感，必 Rust hot-path；Python L0/L1 路徑會 fatal。建議走 Rust strategies/ trait 直接 IMPL。

### 候選 C — BTC→Alt Lead-Lag（W-AUDIT-8d，IMPL 順序 #1）

| 維度 | 貢獻 |
|---|---|
| (a) Alpha source layer | Tier 4 cross-asset → +1% |
| (b) Dormant strategy slot 解鎖 | "signal copier" 風格 → 策略選擇 +0.8% |
| (c) Portfolio diversification ρ | ρ ~0.3 → portfolio Sharpe +0.3% |
| **總計** | **+2.1%**（最低貢獻但最快 IMPL）|

**FA 立場**：候選 C 是「easy win」，BB 視角 Bybit fetch BTC + Alt 1m kline 已支援。建議首發 IMPL（#1）驗 W-AUDIT-9 graduated canary 機制；如 C Stage 2 PASS 再投資 B（最高潛力但 latency-sensitive）。

### 三候選累計

- 理論最大：A + B + C = +9.3%
- 實際保守：1-2 候選 PASS = +3-7%
- 22% 缺口分解：A/B/C +5%（中位）+ Track W 收尾 +10% + W-AUDIT-8e/f +5% = **+20%（85%），±5% uncertainty**

**FA Push back**：IMPL 順序 C/B/A 合理，但**要 explicit Stage 2 abort gate**：如 C Stage 2 fail（demo 14d gross < 0），整 Track A 8b/c 重評，不連續 IMPL。當前 PA DAG 隱含 sequential，需明文化為 stage-gated。

---

## §6 對 PA 工程 DAG 的業務鏈視角 Critique

### Critique 1 — Sprint N+1 W-AUDIT-4b INSERT path × 6 並行可能 race condition

PA Track W Week 2 寫「W-AUDIT-4b INSERT path × 6 表 E1×4 並行」。**業務鏈視角 push back**：6 表分屬 3 schema layer：

- feature_baselines 必先（input 用）
- mlde_edge_training_rows 中段（feature_baselines 後）
- scorer_predictions 終端（中段後）

E1×4 並行 = 4/6 錯誤順序 wire-up。**FA 建議**：W-AUDIT-4b 改 sequential 串行 IMPL（feature_baselines first → mlde_edge_training_rows → scorer_predictions → 3 advisor / drift 並行），工時可能從 ~30h 升到 ~38h，但避 schema relationship debug。

### Critique 2 — W-AUDIT-9 Stage 1 對下單節點解套是 standalone milestone

當前下單節點 35% 因 ExecutorAgent shadow_mode = true 永 log-only。W-AUDIT-9 land 後 Stage 1+2 在 demo 真 spawn ExecutorAgent.execute_via_ipc 走 stage-gated route。**這是下單節點 35% → 50% 關鍵躍升**（fake-live shadow → stage-controlled real demo fills）。

**FA 業務鏈視角**：Sprint N+3 PA 估 +3% 偏保守（FA 估 +5-7%）。建議在 Sprint N+3 預估表把 W-AUDIT-9 Stage 1 launch 列為 **standalone milestone**，不混 Track A funding skew Stage 1 行內。

### Critique 3 — Track W 92h vs 業務鏈 +10% 對 Track A 預算分配誤讀風險

Track W 92h → +10% 業務鏈 ≈ 9.2h/1%；Track A W-AUDIT-9 + 8a + 8b/c/d 估 ~270-330h → +15% ≈ 18-22h/1%。Track A 邊際效率 2x 低於 Track W，但**Track A 是「拓寬 alpha territory」一次性投資**。

**FA Push back 必明文記入 sign-off**：Track W 是 supervised live 前置門檻（合規/安全/可觀測 baseline），不是 alpha 拓寬；Track A 不能取代 Track W。即使 Track A 全做完業務鏈到 85%，沒做 Track W 仍卡 supervised live。

### Critique 4 — D-XX promote / defer fine-tune

| D-XX | PA 預設 | FA 業務鏈視角建議 |
|---|---|---|
| D-08a Phase A-D | 4 sprint × ~40 person-day | 維持；Phase B 2 sprint 內必接 1 demo strategy 消費（避 spec 完工但無 alpha 證據）|
| D-08e Strategist→Analyst propose | Sprint N+5 | **Promote 至 Sprint N+4**（與 Track W 收尾並行）|
| D-08f Hypothesis Pipeline (R-3) | Sprint N+5 後 | 維持 sequential；FA 強烈贊同 PA Push Back |
| D-08g Per-alpha-source Live Promotion Gate (R-4) | Sprint N+6+ | **Defer 至 Sprint N+7**：W-AUDIT-9 已部分覆蓋；R-4 真正獨立 IMPL 必後於 1-2 alpha source Stage 3 PASS |
| D-13 Cognitive Modulator | dormant | 維持 dormant 至 Sprint N+8+ |
| D-14 DreamEngine | dormant | 維持 dormant；ADR-0020 + Foundation Model 未 ready |
| D-17 Layer 2 自主推理循環 | 永久 dormant by ADR-0020 | **永不解**；D-02 SOP 是替代品不是 stepping stone |

---

## §7 Sign-off Pre-flight 業務鏈側 Checklist（9 條）

1. **W-AUDIT-3b runtime smoke 已從 Linux 驗** — `ssh trade-core` 跑 `python -m pytest -k test_executor_fail_closed` + 跑 engine restart 後驗 `[55] chains_with_lease > 0` + 驗 `executor_canary_stage = 0` (binary fail-closed unchanged for live)
2. **W-AUDIT-4b 6 表 INSERT path 已串行 IMPL** — 不可 E1×4 全並行；schema relationship 必驗
3. **F-08 cron `crontab -e` install + 24h 真 fire 驗證** — `[Xc] ml_training_cron_active` healthcheck PASS；不可只有 source/test
4. **W-AUDIT-9 Stage 0 binary fail-closed 不變式保留** — Live boundary 5-gate / SM-04 ladder / DOC-08 §12 9 不變量 / §二 16 原則硬不變式 4 個範圍均不被 graduated canary 觸碰
5. **W-AUDIT-8b/c/d sequence 必含 Stage 2 abort gate** — candidate C IMPL 後 Stage 2 demo 14d gross < 0，Track A 8b/c 必須重評不連續 IMPL；PM sign-off 報告必明文記
6. **D-02 Layer 2 manual SOP 不違反 ADR-0020** — 任何 IMPL 不可把 manual probe 自動化為 cron / event-trigger
7. **W-AUDIT-6 mid-ground 砍 6 polishing 的 K -12 trial penalty 量化結論記入 sign-off report** — 避免後續 polishing backlog 重新 lobby 時被當「省工時妥協」回擊
8. **`v2-NEW-1 strategist cap 30%→50%` 補 ADR-0021** — 必明文記 freedom-not-gate rationale + 與 SM-05 張力處理 + 50% 偏離監測指標
9. **6 表 0 INSERT 18 天無變動結構性 gap 必有 owner + ETA** — W-AUDIT-4b 必有 P1 escalation 而非 wave-level ACTIVE / PARTIAL 模糊狀態

**FA Sign-off 條件**：上 9 條全 PASS = 業務鏈視角 GO；任一 FAIL = 業務鏈視角 BLOCK，PM 必補充說明或拍板 known-deviation。

---

## §8 FA 結論

**業務鏈 milestone**：v3 63% → Sprint N+5 預期 **85-89%**。關鍵躍升點 = Sprint N+2 W-AUDIT-9 IMPL land（解 P0-EDGE-1 雞蛋死循環）+ Sprint N+5 W-AUDIT-8b funding skew Stage 2 PASS（首個 alpha-bearing 策略真 evidence）。

**對 PA dispatch list verdict**：**AGREE 主軸 + 4 條業務鏈視角 fine-tune push back**：
1. W-AUDIT-4b 6 表並行 → 串行（schema 關係依賴）
2. W-AUDIT-9 Stage 1 launch 應 standalone milestone（業務鏈 +5-7%，不混 Track A funding skew）
3. W-AUDIT-8b/c/d Stage 2 abort gate 必明文化
4. D-08e Strategist→Analyst propose 通道 promote 至 Sprint N+4（與 Track W 並行）

**對 Operator 的 hard truth**：
- Track W 92h 是 supervised live 前置門檻，不能被 Track A lobby 取代
- D-02 Layer 2 manual SOP 預期 +2-5 USDT/week 是保守上限；如不達 1 USDT/week 不值人工 fixed cost
- 候選 A/B/C 預期 +3-7% 業務鏈是中位估，新 alpha source 0% PASS 率歷史不支持「三都 PASS」樂觀情境
- W-AUDIT-6 砍 6 polishing 是 DSR 數學意義的 right move，不是省工時妥協

**最早 supervised live 規劃帶（業務鏈視角）**：
- 6/15 樂觀（業務鏈 75%+）：~30%
- 6/30 中位（業務鏈 80%+）：~40%
- 7/15 悲觀（業務鏈 85%+）：~25%
- 8/15 極悲觀：~5%

---

**FA AUDIT DONE**
