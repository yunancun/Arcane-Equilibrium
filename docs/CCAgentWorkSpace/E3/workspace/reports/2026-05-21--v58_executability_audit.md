# v5.8 13-Module Autonomy Expansion 執行性審核 — E3 視角

**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.8 13 module 引入 11 個新攻擊面，但「自動化」與「5-gate fail-closed」直接衝突的有 4 個（M1 Tier 2 auto / M2 auto-disable / M6 reward weight auto / M7 auto-demote / M10 capital trigger）需明文 5-gate 不可被 auto path 繞過；M5/M12/M13 interface trait 未鎖死 signature 將擴大 Y3+ 攻擊面；M4 self-supervised DRAFT writeback 必須走單一寫入口；schema V105-V116 全部需明文 role 寫入隔離（learning.* 禁 production trading role 寫）。Sprint 1A-β 派發前 5 個 must-fix；Sprint 1A-γ/δ/ε 期間 6 個 should-fix。

---

## 0. OWASP T01-T10 對 13 module 新增攻擊面

| OWASP | 涉及 module | 評級 | 理由 |
|---|---|---|---|
| **T01 Broken Access Control** | M1, M2, M3, M4, M6, M7, M10 | **HIGH RISK** | M1 Tier 2 auto-approval / M2 auto-disable / M6 auto-weight / M7 auto-demote / M10 capital trigger 全是「無 operator click」的寫操作；現有 5-gate 為 binary fail-closed 設計，**v5.8 未明文這些 auto path 仍須走 5-gate**（默認應強制，但 spec 未鎖定）|
| **T02 Cryptographic Failures** | M1 lease tier signing, M4 DRAFT writeback, M12 multi-venue auth | **WARN** | M1 Tier 系統若 lease.actor 升級為 "system-auto" pseudo-actor 需 HMAC 簽名鏈擴展；M4 DRAFT 寫 learning.hypotheses 是否需 signature 防 tamper；M12/M13 多 venue API key scope 暴露面擴張未談 |
| **T03 Injection** | M4 pattern miner (raw market data ingestion) | **WARN** | M4 ingest market.kline / trading.fills / market.liquidations → pattern miner 若內部用 SQL aggregator 拼 symbol/strategy_id 字串入 query 必爆 SQL injection；建議全程 sqlx `query!()` 強制 |
| **T04 Insecure Design** | M1, M2, M6, M7, M8, M11 | **HIGH RISK** | M2 auto-disable 是 always-on（無 opt-in）→ 攻擊者觸發 false anomaly = 強制 disable production；M8 anomaly → M3 HEALTH_DEGRADED 級聯 → 攻擊者可造 portfolio-wide freeze；M11 replay divergence flag = 攻擊者操控 replay engine state 造全策略 false drift flag；M6 weight bound 若 operator 設 [0,0] → reward function 退化 = silent attack vector |
| **T05 Security Misconfiguration** | M5, M12, M13 interface stubs | **WARN** | M5 ModelClient trait / M12 OrderRouter trait / M13 AssetClass+Venue enum 在 Sprint 1A-δ 只是 stub，但 **trait signature 即固化**；Y3+ IMPL 時若新 capability（如 streaming prediction throttle / new venue scope）需擴 trait → 破壞性 change，攻擊者可 exploit trait pre-IMPL gap |
| **T06 Vulnerable Components** | M5 (ML streaming infra Y3+), M12 (Binance crate), M13 (multi-asset SDK) | **WARN** | M5 streaming ML 通常需 ONNX/Triton/TorchServe stack（新依賴大）；M12/M13 Binance/structured-products SDK 未選型；v5.7 已有 Binance WS 但 trade lib 是新依賴 |
| **T07 Authentication Failures** | M1 Tier 2 operator opt-in toggle | **WARN** | Console toggle "Auto-Approve On" 默認 OFF — 但 **Console toggle 自身的 auth 路徑** 是否走 Operator role + 5-gate？若 viewer 角色拿 GUI session 切 toggle = bypass 整個 Tier 0-4 系統 |
| **T08 Software/Data Integrity** | V105-V116 (12 new migrations), M11 replay state | **WARN** | 12 新 migration（v5.7 已加 V103-V104）+ M11 replay engine state — replay engine 若無 read-only marker，攻擊者 modify replay state = M7 decay false trigger / M8 anomaly false trigger 級聯 |
| **T09 Logging Failures** | M4 DRAFT writeback, M6 weight history, M11 divergence log, M8 anomaly events | **HIGH RISK** | 4 個 module 寫 learning.* 但 v5.8 未明文 audit append-only / WORM；M4 攻擊者拿 hypothesis_drafts.write 可植入惡意 DRAFT；M11 replay log payload 結構未鎖（沿用 v5.7 Risk 3 counterfactual 風險）|
| **T10 SSRF** | M2 macro feed (Y2 active), M8 ML autoencoder Y2+, M13 venue evaluation | **HIGH RISK** | M2 auto-enable Y2 依 macro feed external API（FOMC/CPI vendor）— 若 feed 域名走 config drift → SSRF；M13 venue evaluation Y3+ 需評多家 exchange 公開 API → outbound 域名爆增 |

---

## 0.5 13 module 引入的 attack surface

### M1 Decision Lease Tier 2 Auto-approval
- **新攻擊面**：lease.actor = "system-auto-tier2" pseudo-actor 寫操作（CLAUDE.md §四 原文「ML/DE/EA/SA 不得 live-order without GovernanceHub + Decision Lease approval」**未談 system-auto pseudo-actor**）
- **gate bypass path**：30 prior Advisory + 80% yes-rate + opt-in 全為 metadata 計算，**攻擊者若可寫 advisory_log (V112 tier_eligibility_log) → 偽造 prior 30 approvals → 解鎖 Tier 2 auto**
- **role escalation**：viewer/researcher 拿 Console session 切 "Auto-Approve On" toggle → 解鎖全策略 cross-strategy reweight
- **24h undo DoS / financial loss**：Tier 2 Auto 在 24h 內可 fill 不可逆部位（perp 已 close，spot Earn 已 stake 4-180d lock）→ undo 無法 rollback 已實現 PnL 損失

### M2 Overlay Auto-disable Always-on
- **false anomaly trigger**：M8 anomaly 觸發 → 強制 M2 disable production overlay → 改變既定 alpha source
- **macro/on-chain feed DoS**：外部 API auth fail / rate limit → counterfactual diverges → auto-disable cascade
- **「always-on」設計缺陷**：v5.8 寫「Auto-disable is always-on (does not require operator opt-in)」— **與 5-gate fail-closed 衝突**（5-gate 是 fail-closed=拒絕；auto-disable 是 fail-open=改變狀態），需明文哪個 priority 高

### M3 HEALTH State Machine
- **probe 操控攻擊**：DB write backlog / WS dropout rate / disk usage 三個 probe 都是「外部可觀測」→ 攻擊者填 DB / 注 WS jitter → 強制 HEALTH_DEGRADED → throttle non-critical strategies
- **HEALTH_CATASTROPHIC vs portfolio cum loss kill**：v5.8 §M3 寫「HEALTH_CATASTROPHIC → existing kill criteria (portfolio cum loss > $3,000) triggers」— 兩者誰先？順序若反，可能 race condition

### M4 Self-Supervised DRAFT Writeback
- **單一寫入口違反**：CLAUDE.md §二 原則 1「Single controlled write entry for orders/execution」+ 原則 7「Learning must not rewrite live state directly」— M4 bot 自己寫 learning.hypotheses **是否算 live state write**？v5.8 §M4 寫「DRAFT 不算 promote / execute」但 **DRAFT row 出現本身即可影響後續 Cowork 評審 — 是 indirect live state**
- **audit signature 缺失**：DRAFT writeback 未明文 HMAC / actor signing chain
- **role permission**：若 hypothesis_drafts.write 給 ml-training role → researcher/viewer 拿 ml-training role 可注 DRAFT，惡意 hypothesis 進 Cowork review queue（社會工程攻擊面）

### M5 Online Learning Interface Stub
- **trait signature 提前固化**：Sprint 1A-δ stub 只有 `get_predict_streaming() unimplemented panic!()` — 但 **trait signature 一旦固定，Y3+ 加 capability 需破壞性 change**（如 throttle / fallback / model rollback / drift detection callback 各需自己的 trait method）
- **return malicious prediction**：streaming model 比 daily batch 攻擊面大（daily 有人工 review window；streaming 沒有）— 攻擊者投毒訓練數據可在 minute granularity 影響交易

### M6 Bayesian Reward Weight Auto
- **bound [0,0] silent attack**：v5.8 寫「Weight bounds set by operator in Console (initial: conservative ranges)」— operator 若手滑/被釣魚設 λ_dd=[0,0] → DD 不再進 reward → bot 自動最大化 raw return（無 DD penalty）
- **rollback baseline 操控**：「Weight change rolled back if next-month Sharpe < baseline」— 攻擊者操控 baseline Sharpe（控制比較期）造成錯誤 rollback
- **30%-change cap bypass**：若多次 < 30% change 累積（如 28%+28%+28%）— 連續三 month 累積 + 80% drift 是否觸 confirm？v5.8 未談累積上限

### M7 Decay Auto-demote
- **N consecutive losing trades 操控**：攻擊者造 latency spike → slippage cascade → N 連虧 → 強制 decay → 50% size demote
- **counterfactual replay underperform 操控**：「Counterfactual replay (M11) shows strategy underperforming baseline by ≥ X bps」— 攻擊者操控 M11 replay engine 即可間接觸 M7 demote

### M8 Anomaly Active Trigger Y2
- **anomaly → M3 HEALTH_DEGRADED 級聯**：v5.8 §M8 「Y2 active trigger: high-severity anomaly → trigger M3 HEALTH_DEGRADED state」— 兩個 module 互相觸發是 amplification loop
- **portfolio-wide freeze**：「correlation-break anomaly → halt new positions on coupled strategies」— 攻擊者偽造 correlation break （vol jamming / spoof）→ 強制全策略凍倉

### M9 A/B Testing Framework
- **trial_id hash predictability**：v5.8 寫「Random by trial_id hash (deterministic, reproducible)」— 攻擊者預測 hash 即可預測 A/B 分組 → 在 attacker-favored 分組 spoof 數據
- **early stopping efficacy gate**：「Sequential testing with mSPRT + Early stopping for futility / efficacy」— attacker-controlled noise 可觸 premature efficacy gate → false promotion variant

### M10 Tier C-D Capital Scaling
- **AUM trigger source 操控**：「7-day moving AUM > threshold sustained 30 day → trigger eval」— AUM 計算源（live PnL + balance）若有 unrealized PnL 高估 → 攻擊者操控 mark price 可造假 trigger
- **Tier 升級 = 引入新 symbol/regime**：Tier C $25-50k 啟 new symbol screening / Tier D $50-100k 啟 regime auto-classify — **新策略引入即新攻擊面**（per AMD-2026-05-15-01 新策略需 operator approve；M10 capital trigger 自動觸發 是否繞過 AMD？）

### M11 Nightly Counterfactual Replay
- **replay engine state 操控**：「Compare replay-decided trades vs production-executed trades」— 若 replay engine state 可被 modify（含 strategy param / market data / fill model）→ 全策略 false drift flag → 級聯 M3 HEALTH_WARN + M7 decay + M8 anomaly 三 module
- **divergence flag access control**：v5.7 audit Risk 3 已標 counterfactual log payload 風險；M11 更廣（全策略 nightly），learning.replay_divergence_log Y2 enable trigger 後是否保留 GUI viewer 禁讀 + Copy Trading export 禁 join，**v5.8 未談**

### M12 OrderRouter Trait
- **multi-venue auth scope 擴大**：Y2 加 Binance perp → 多 API key scope（Bybit + Binance），每個 venue 都需 secret slot / HMAC chain
- **venue switch 攻擊**：falsify market data on one venue 導致 routing 偏好錯誤 venue — adaptive routing 對 cross-venue price discrepancy 敏感
- **maker-vs-taker reverse-snipe**：v5.8 §M12 寫「Reverse-snipe defense (maker default; switch to taker only on confirmed signal)」— 但 「confirmed signal」定義未明，攻擊者可造 fake confirmation 強制切 taker（吃 spread）

### M13 Venue Enum
- **enum 提前固化攻擊面**：Sprint 1A-δ AssetClass+Venue enum 即定 — Y2-Y3 加 venue 需 enum extension，每加一個 venue **既有 lease.scope / authorization.env_allowed 都需 backfill 校驗**，無 backfill → 舊 lease 可能對應錯誤 venue
- **D1a constraint enforcement**：「Always declined: DEX / Hyperliquid」— enum 是否 hardcode 拒絕 DEX variant？或只 doc-level？若只 doc，未來 enum 擴張時可意外加入 DEX

---

## 1. Top 3 執行性風險

### Risk 1：5-gate live boundary 在 M1 Tier 2 auto / M2 auto-disable / M6 auto-weight / M7 auto-demote / M10 capital trigger 路徑下「fail-closed default」未明文

- **嚴重度**：CRITICAL（HARD BLOCKER for Sprint 1A-β）
- **位置**：v5.8 §M1/M2/M6/M7/M10 + §11「Operator forgetfulness mitigation」段
- **描述**：
  - CLAUDE.md §四 Hard Boundaries 寫「True live requires all five gates」+「ML/DE/EA/SA must not live-order or mutate live parameters without GovernanceHub + Decision Lease approval」
  - v5.8 §11 列 6 個 「operator forgetfulness mitigation」全是 auto path：
    - M1 Tier 2 auto-approval（cross-strategy reweight 寫 live param）
    - M2 auto-disable（改 production overlay state）
    - M3 auto-degradation（throttle non-critical strategies）
    - M7 auto-demote（live size scaled to 50%）
    - M8 alert→action（M3 HEALTH_DEGRADED 級聯）
    - M11 daily replay（讀-only，安全）
  - 5 個 auto path 都是「live state write」— **v5.8 未明文這些 auto 路徑是否仍須走 5-gate**
  - 攻擊路徑：
    - 攻擊者拿 viewer/researcher 角色 + Console session
    - 觸發 M2 macro feed 假 disable trigger（污染 counterfactual）
    - 觸發 M7 N-consecutive losing trades 假數據（poison fills）
    - 觸發 M10 AUM moving threshold 假 trigger
    - 每個都繞 operator click（per 「forgetfulness mitigation」設計）→ 若 5-gate 不適用，攻擊者完成「live param write without Operator role auth」
- **為何屬「執行性」（非邏輯）**：
  - 邏輯審查確認 13 module 需要 auto path（operator 駁回 Claude push-back）
  - 執行性 gap = 「auto path 是否仍須 5-gate」**規格選擇未鎖定** → PA 派發 1A-β 時實作層自由心證 → 必然 drift
- **Must-fix 建議**：
  - 在 v5.8 §11 「Operator forgetfulness mitigation」段加 invariant：
    > "所有 v5.8 module auto path（M1 Tier 1+2 auto-approval / M2 auto-disable / M3 auto-degradation / M6 auto-weight / M7 auto-demote / M8 alert→action / M10 capital tier auto-trigger）寫 live state 必經完整 5-gate fail-closed：(a) Python live_reserved + Operator role auth 上下文 valid（auto path 使用 'system-auto-tier-N' pseudo-actor，但 pseudo-actor 必須 inherit 既有有效 Operator session 才能執行）(b) OPENCLAW_ALLOW_MAINNET（不豁免）(c) secret slot valid (d) authorization.json HMAC valid + env_allowed include 'auto-<tier>' (e) Decision Lease scope 限定該 module"
  - 5-gate auto path 任何一個 fail → 該 auto 動作 fall back to v5.7 Advisory queue（safer degradation）
  - PA dispatch Sprint 1A-β 時 ADR-0034 必含上述 5-gate inheritance 明文

---

### Risk 2：M4 self-supervised DRAFT writeback 違反「單一寫入口」+ 缺 audit signature

- **嚴重度**：CRITICAL
- **位置**：v5.8 §M4「Self-Supervised Hypothesis Discovery」段 + V103 extension
- **描述**：
  - CLAUDE.md §二 原則 1「Single controlled write entry for orders/execution」+ 原則 7「Learning must not rewrite live state directly」+ 原則 8「Every trade must be reconstructable and explainable」
  - v5.8 §M4 寫「Bot CAN propose hypotheses (write DRAFT row)」— **DRAFT row 是 indirect live state write**：
    - DRAFT 出現 → Cowork+operator review → 可能 approve → 進 preregistration → 進 Alpha Tournament → 可能 promote live
    - 鏈條中 DRAFT 寫入是「最早 entry point」→ DRAFT 寫入無 HMAC signature → 無法 reconstruct 「哪個 attacker plant 哪個 DRAFT」
  - 攻擊路徑：
    - 攻擊者拿 ml-training role 或 viewer-with-write-bug
    - 寫 DRAFT row 模擬「自然發現」（pattern_id / supporting_stats 偽造）
    - Cowork+operator review 時若 review depth 不足（DRAFT 量大時 ≥ 10/sprint）→ 惡意 DRAFT 進 Alpha Tournament
    - Alpha Tournament 跑 Stage 0R+0+1 後若策略本身 alpha 真實但 setup 有 hidden tail risk → 終致財損
  - 二級攻擊：DRAFT writeback 若不走 Decision Lease，攻擊者可批量 DDoS write Cowork review queue（社會工程 DoS）
- **為何屬「執行性」（非邏輯）**：
  - 邏輯確認 M4 需要 bot 自寫 DRAFT（operator's long-term iteration）
  - 執行性 gap = audit chain / writeback path / role permission 未明文
- **Must-fix 建議**：
  - 在 v5.8 §M4 加 「Critical constraints」extension：
    > "Bot DRAFT writeback：(a) 走 Decision Lease（scope=hypothesis_draft，actor=system-pattern-miner-vN，每次 writeback 用 Decision Lease grant + release pair）(b) DRAFT row 含 HMAC signature 欄位（signing key 用 hypothesis-draft-signing-key，獨立於 authorization HMAC key）(c) role permission：只有 ml-training-pattern-miner role 可寫 hypothesis_drafts，researcher/viewer/operator 全禁；ml-training-pattern-miner role 不可分配給人類 actor (d) DRAFT writeback rate limit（最多 N DRAFTs/day，超量必 Cowork review 報警）(e) audit log append-only WORM 同步寫 learning.hypothesis_draft_audit"
  - PA dispatch Sprint 1A-γ 時 V103 extension 必含 signature 欄位 + audit table
  - ADR-0034 Tier 1 「intra-strategy reparam」與 M4 DRAFT writeback 是否視為同 tier 需澄清（建議 DRAFT writeback 為單獨 lease scope）

---

### Risk 3：M5/M12/M13 interface trait signature 提前固化未鎖死關鍵 capability slot

- **嚴重度**：HIGH
- **位置**：v5.8 §M5/§M12/§M13 + §3「Sprint 1A-δ」段 + ADR-0035/0039/0040
- **描述**：
  - v5.8 Sprint 1A-δ 寫 3 個 interface stub：
    - M5 ModelClient trait（`get_predict()` / `get_predict_streaming() panic!`）
    - M12 OrderRouter trait（adaptive routing）
    - M13 AssetClass + Venue enum
  - **trait signature 一旦固化，Y3+ IMPL 時若新 capability 需 trait 修改 = breaking change**
  - 三大盲點：
    - **M5 streaming model** 需要的 capability：drift detection callback / model rollback hook / throttle interface / fallback model selector — 任何一個未 Sprint 1A-δ 鎖入 trait → Y3+ IMPL 需加 method → breaking change → 所有 consumer 需 refactor
    - **M12 OrderRouter** 需要的 capability：venue-specific rate limit accounting / cross-venue position netting / slippage forecast / reverse-snipe defense flag — 同樣未在 Sprint 1A-δ stub 鎖入
    - **M13 Venue enum** 在 Y2-Y3 加新 venue 時，**既有 lease.scope / authorization.env_allowed 需 backfill**（若 backfill 漏掉 → 舊 lease 對應到錯誤 venue）+ D1a「DEX/Hyperliquid declined」是否 hardcode 進 enum 拒絕 variant？或只 doc-level？
  - 攻擊路徑：
    - 攻擊者觀察 Y3+ IMPL gap 期間（已部署 stub 但未 IMPL real logic）
    - 若 stub `panic!()` 設計不嚴密 → 觸發 unimplemented path → DoS（trade halt）
    - 若 stub 默認 return value（如 default routing = Bybit perp）→ 攻擊者可能 spoof 加觸 streaming/multi-venue path
- **為何屬「執行性」（非邏輯）**：
  - 邏輯確認需要 M5/M12/M13 trait（capital scaling）
  - 執行性 gap = trait signature 哪些 capability 必含、stub 默認行為、enum extension governance 未明文
- **Must-fix 建議**：
  - 在 v5.8 §M5 trait 設計加：
    > "ModelClient trait Sprint 1A-δ 必含 method slots：get_predict() / get_predict_streaming() / register_drift_callback() / rollback_to_version(version_id) / set_throttle(rate) / get_health()。所有 streaming 相關 default impl = `unimplemented!()` panic（Y3+ IMPL 前任何 caller invoke streaming method 必 panic = fail-closed default）"
  - M12 OrderRouter trait 同步加 method slots：route_order() / get_venue_health() / get_cross_venue_position() / forecast_slippage() / reverse_snipe_flag()，default impl panic
  - M13 AssetClass + Venue enum 在 Sprint 1A-δ 加：
    > "Venue enum hardcode 拒絕 DEX / Hyperliquid / Uniswap / Aave variant（compile-time enforcement，不單 doc）；新增 venue variant 需 ADR amendment + 既有 lease scope / authorization env_allowed backfill checklist"
  - PA dispatch Sprint 1A-δ 時 ADR-0035/0039/0040 必含 trait method slot 列表 + enum 拒絕清單

---

## 2. 5-gate live boundary 在 13 module 下保留 hard binary fail-closed

- **核心結論**：v5.8 必須明文「auto path 不豁免 5-gate」
- **影響 module**：M1 (Tier 1+2) / M2 (auto-disable) / M3 (auto-degradation) / M6 (auto-weight) / M7 (auto-demote) / M8 (alert→action) / M10 (capital trigger)
- **fail-closed 退路**：所有 auto path 5-gate fail → fall back 到 v5.7 Advisory queue（operator 必須手動處理積壓）
- **「forgetfulness mitigation」 vs 「5-gate」優先**：
  - v5.8 §11 寫「Operator 可能忘記」 → 5 個 auto path 應「不需 operator click」
  - 但 5-gate 不是「click」而是「狀態 + auth」(Operator session 有效 + secret slot active + signed authorization unexpired + env_allowed match)
  - **解決**：auto path 不需 operator 即時 click，但需有效的 background Operator session + valid authorization；若 authorization expired (TTL 過期) → auto path 拒絕執行 → fall back Advisory
  - 這保留 5-gate fail-closed 同時實現「operator 短期忘記不影響 24-48h auto」(authorization TTL 通常 24h)，但「operator 長期忘記」(> TTL) 系統會自動降級到 Advisory（safer state）
- **GUI Console toggle "Auto-Approve On" 必須走 Operator role auth**：viewer/researcher 不可切

---

## 3. secret slot policy 新 external dependency

| Module | 新 external dependency | 已知 / 未知 | 需 secret slot |
|---|---|---|---|
| M2 macro feed Y2 active | FOMC/CPI vendor (v5.7 已標 trial) | 未選定 vendor | YES — `$OPENCLAW_SECRETS_DIR/external/macro-feed/<vendor>/api_key` |
| M2 on-chain Y2 active | Glassnode/Etherscan/DeFiLlama (v5.7 已標 free tier) | free tier 可能爆 rate | YES — `$OPENCLAW_SECRETS_DIR/external/<vendor>/api_key`（沿用 v5.7 audit must-fix #2 policy） |
| M4 pattern miner | 內部市場數據（無外部依賴） | OK | NO |
| M5 streaming ML Y3+ | ONNX/Triton/TorchServe stack | 未選型 | maybe — 若用 cloud inference 需 API key slot |
| M11 nightly replay | 內部 replay engine | OK | NO |
| M12 cross-venue Y2 | Binance perp API key | NEW | YES — `$OPENCLAW_SECRETS_DIR/external/binance-perp/api_key`（與 v5.7 Binance WS market-data-only 分開 — 此為 trade scope） |
| M13 multi-asset Y2-Y3 | Binance options / structured products | NEW | YES — per venue 一個 slot |

- **policy 沿用 v5.7 audit must-fix #2**：trial credential TTL 寫 `learning.external_credential_expiry`；fail-closed default；outbound 域名白名單 RiskConfig.external_sensor_whitelist
- **M12 Binance trade key 新增 invariant**：withdraw permission 永遠 false（per CLAUDE.md 硬約束）；read+trade only

---

## 4. 對 PA+FA+PM 匯總必收 top 3

1. **v5.8 §11 auto path 5-gate inheritance 明文** (Risk 1 must-fix) — invariant 寫入 + ADR-0034 含 「auto pseudo-actor inherits Operator session + authorization TTL fail-closed」
2. **v5.8 §M4 DRAFT writeback Decision Lease + HMAC signature + role permission** (Risk 2 must-fix) — V103 extension schema 含 signature 欄位 + audit table + 獨立 signing key slot
3. **v5.8 §M5/M12/M13 trait signature 必含 capability slot + default panic + Venue enum hardcode 拒絕 DEX/Hyperliquid** (Risk 3 must-fix) — ADR-0035/0039/0040 含 method slot 列表

---

## 5. v5.8 派發前 must-fix（fail-closed）

| # | Must-fix | 位置 | 阻塞性 | Sprint |
|---|---|---|---|---|
| 1 | v5.8 §11 「auto path 5-gate inheritance」明文（Risk 1） | spec | **HARD BLOCKER** Sprint 1A-β | 1A-β |
| 2 | v5.8 §M4 DRAFT Decision Lease + HMAC signature + ml-training-pattern-miner role + writeback rate limit（Risk 2） | spec + V103 extension | **HARD BLOCKER** Sprint 1A-γ | 1A-γ |
| 3 | v5.8 §M5/M12/M13 trait method slot 列表 + default panic + Venue enum DEX/Hyperliquid hardcode 拒絕（Risk 3） | spec + ADR-0035/0039/0040 | **HARD BLOCKER** Sprint 1A-δ | 1A-δ |
| 4 | v5.8 §M6 reward weight bound 下限保護（disallow [0,0]）+ 累積 30%-change cap | spec | SOFT BLOCKER | 1A-β |
| 5 | v5.8 §M10 capital trigger AUM 計算源明文（realized vs unrealized）+ 與 AMD-2026-05-15-01 「新策略需 operator approve」相容性澄清 | spec | SOFT BLOCKER | 1A-γ |

---

## 6. Sprint 1A-β-ε 期間 should-fix

| # | Should-fix | 位置 | Sprint |
|---|---|---|---|
| 6 | v5.8 §M1 GUI Console "Auto-Approve On" toggle 走 Operator role auth（非 viewer/researcher）| spec + GUI auth | 1A-β |
| 7 | v5.8 §M3 HEALTH_CATASTROPHIC vs portfolio cum loss kill 順序明文 | spec | 1A-β |
| 8 | v5.8 §M8 anomaly → M3 級聯 amplification loop cap（如 1-anomaly = 1-state-change/24h）| spec | 1A-γ |
| 9 | v5.8 §M9 trial_id hash predictability 改用 server-side seeded random（不可 attacker predict）| spec | 1A-γ |
| 10 | v5.8 §M11 replay_divergence_log GUI viewer 禁讀 + Copy Trading export 禁 join（沿用 v5.7 audit Risk 3 policy）| spec | 1A-β |
| 11 | v5.8 V105-V116 learning.* table 全部明文「production trading role 禁寫」（read-only for trade路徑）| schema | 1A-β-ε |

---

## 7. 可優化 / 拆分 / 並行

- **拆分**：Sprint 1A-β 5 module CRITICAL DESIGN (M1/M3/M6/M7/M11) 可拆 5 平行 E1 sub-track；must-fix #1 / #4 / #7 / #10 / #11 可在 1A-β week 0 並行 draft（純 spec 補丁無 code dep）
- **並行**：must-fix #2 (M4 DRAFT) + must-fix #3 (M5/M12/M13 trait) 可在 1A-γ/δ week 0 同時 draft；should-fix #9 (M9 hash randomness) 可獨立 1A-γ 內部完成
- **優化**：v5.7 audit must-fix #2 (external sensor secret slot policy) 沿用至 v5.8 §3 表格 M2/M12/M13 三 venue — 不重複建 policy，extend 既有
- **去重**：v5.7 audit Risk 3 (counterfactual log access control) 已包含 v5.8 M11 (nightly replay log access)，should-fix #10 可 reference v5.7 policy 不重新 draft

---

## 8. v5.7 audit must-fix 在 v5.8 下狀態

| v5.7 must-fix | v5.8 狀態 |
|---|---|
| #1 v5.7 §4 Earn 5-gate adapter 明文 | 仍 HARD BLOCKER（v5.7 Sprint 1B Earn governance 實作未動）|
| #2 v5.7 §6 External sensor secret slot policy | extend 至 v5.8 §3 M2/M12/M13 三外部 venue dependency |
| #3 BB Bybit /v5/earn API permission + demo support | 仍 HARD BLOCKER（runtime evidence 未補）|
| #4 ADR-0030 Earn audit log WORM | 仍 SOFT BLOCKER |

---

## 9. CLAUDE.md 核心 invariant 對 13 module 衝突檢查

| invariant | 衝突 module | 解決方法 |
|---|---|---|
| §四「True live requires all five gates」 | M1 Tier 2 / M2 / M6 / M7 / M10 auto path | must-fix #1 — auto path inherits 5-gate |
| §四「ML/DE/EA/SA 不得 live-order without GovernanceHub + Decision Lease approval」| M1 Tier 2 (cross-strategy reweight)、M6 (auto-weight) | must-fix #1 + auto path 走 Decision Lease |
| §二 原則 1「Single controlled write entry」| M4 DRAFT writeback | must-fix #2 — DRAFT 走 Decision Lease |
| §二 原則 7「Learning must not rewrite live state directly」| M4 DRAFT、M6 reward weight、M11 divergence log | must-fix #2 + indirect live state (DRAFT/weight/log) 需 signature + audit |
| §二 原則 8「Every trade must be reconstructable」| M1 Tier 0 per-fill auto + M7 demote auto + M10 capital trigger | audit append-only WORM for all auto path |
| §四「Bybit API timeout or nonzero retCode fails closed; do not add hidden retry paths」| M3 HEALTH state machine throttle/degrade | M3 throttle 必 transparent，不可成為「隱藏 retry」|
| D1c/D1d「no withdrawal API key」| M12 Binance perp + M13 multi-venue | trade-only key (withdraw=false 永遠) |

---

**E3 verdict 細節**：
- 5-gate live boundary 對 v5.8 13 module 是 **首要 invariant**，所有 auto path 必須 inherit fail-closed default；operator's「forgetfulness mitigation」目標可達成（authorization TTL 內 auto，TTL 外 fall back Advisory）但不豁免 5-gate
- M4 DRAFT writeback 是 **indirect live state** — 需 audit signature + Decision Lease 鎖鏈；CLAUDE.md 「Single controlled write entry」原則明文包含 learning.* indirect-influence-on-trade write
- M5/M12/M13 interface trait 在 Sprint 1A-δ 鎖死 method slot + default panic + enum 拒絕清單，避免 Y3+ breaking change 攻擊面
- M2 「always-on auto-disable」需明文「fail-closed when authorization invalid」否則與 5-gate 設計衝突
- M11 nightly counterfactual replay log payload 訪問控制沿用 v5.7 audit Risk 3 policy（GUI viewer reject + Copy Trading export reject）
- V105-V116 (12 新 migration) 全部需明文 role 寫入隔離 — learning.* schema 禁 production trading role 寫
- 沒看到 P0 / CRITICAL（既有 baseline 防護鏈 + must-fix #1-#3 補完即可）
- 5 must-fix 是 HARD/SOFT BLOCKER；6 should-fix 是 Sprint 1A-β-ε 期間並行可完成
- v5.8 「dispatch-safe」框架 OK，**Sprint 1A-β 派發前補 5 個 must-fix**即可放行

---

**END E3 v5.8 executability audit**
