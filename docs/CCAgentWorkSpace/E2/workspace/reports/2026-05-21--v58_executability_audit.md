# v5.8 13-Module Autonomy Expansion 執行性審核 — E2 對抗式視角

**日期**：2026-05-21
**Verdict**：HOLD（NEEDS-MAJOR-FIX；GO-WITH-CONDITIONS only after 6 must-fix）
**One-line summary**：v5.8 引入 13 模組 + 7 ADR + 12 schema 但工時 543-797 hr Sprint 1A 與 v5.7 12-prefix DONE 經驗矛盾（v5.7 75-105 hr 是 12 prefix 真實基線）；13 模組互相依賴圖未畫導致 Sprint 1A-β/γ/δ/ε 派發必撞；ADR-0024-lite + 16 root principles 對 M1 Tier 2 / M2 auto-disable / M3 auto-degrade 的「無 operator click」設計與「人類最後審核」原則邊界模糊；Live deploy 五門 + P0-EDGE-1/LG-3/OPS-1..4 完全在 v5.8 §10 風險表缺席。

---

## 0. v5.8 vs v5.7 delta + 內部一致性核驗

### 0.1 v5.8 真正 delta（剝離掉「v5.7 preserved」)

| Layer | v5.7 已有 | v5.8 新增 | 真實增量 |
|---|---|---|---|
| ADR | 0030/0031/0032/0033 (4) | 0034-0040 (7) | +7 ADR（M1/M5/M8/M9/M11/M12/M13 各 1） |
| Schema migration | V103/V104（hypotheses + preregistration + earn schema = 4 表 + Earn governance）| V105-V113 actual + V114-V116 reserved | +9 actual + 3 reserved；其中 V109 (anomaly) / V110 (reward weight) / V112 (lease tiers) / V113 (decay) 是 zero-baseline schema |
| Engineering hours Y1 | 1,275-1,710 hr (PM 仲裁 2) | 2,780-3,930 hr | **+1,505-2,220 hr = +118-130%**（v5.8 §10 自稱 2.3x，數學是 2.18-2.30x） |
| Timeline Y1 | 39 週 | 37-44 週（v5.8 §3 寫「Y1 timeline becomes 44.5 weeks」，§4 表 Sprint 10 「34-37 wk」，§14 「+5 weeks」）| **§3 / §4 / §14 三處時間數字不一致**；§4 表 Sprint 10 末 34-37 週 = Y1 縮短，§3 §14 = Y1 延長 5 週至 44 週 |
| 模組 IMPL coverage Y1 末 | 5 策略 + Earn + 2 counterfactual logger | + M1 Tier 1 + M3 部分 + M4 stage 1 + M7 auto-demote + M9 read-only + M11 nightly | 13 模組中 Y1 末完整 IMPL = 0；Sprint 4-10 partial IMPL = 6 模組；Y2-Y3 完整 IMPL = 7 模組 |

### 0.2 v5.8 與 v5.7 內部矛盾

| # | 矛盾位置 | 內容 | 嚴重度 |
|---|---|---|---|
| 1 | v5.8 §6 vs §0 | §6 自承「v5.8 does not accelerate Y2 90% target」+ §0 寫 Auto-Allocator gate「v5.8 does NOT shortcut this」— 既然不加速 Y2，**+1,505-2,220 hr** 換 Y1 末 60%→66% (+6%) + Y3 Q2 (本來不存在的) 95% 數字。Y3 Q2 數字依賴 capital growth + 12% Y3 APR 假設 stretched；如果 capital 沒到 $50k，M5/M12/M13 IMPL 全延後，2,220 hr 中相當部分變 dead investment。 | HIGH |
| 2 | v5.8 §3 vs §9 | §3 五階段 Sprint 1A-α/β/γ/δ/ε 寫「~7 weeks instead of 1.5 weeks」+ §4 表 Sprint 1A 「0-7」；但 §9 V103 寫「v5.7 lineage V103/V104：hypotheses + preregistration (v5.7) — EXTEND in v5.8 for M4」**— v5.7 12 prefix DONE 已 land V103 4 表 DDL spec 940 行**（TODO §0.5 C3）；v5.8 §9 對 V103 的 EXTEND 是否需要 re-PG-dry-run / 是否與 v5.7 V103 spec 兼容 = 沒寫 | CRITICAL |
| 3 | v5.8 §3 v.s. §4 v.s. §14 | §3「Y1 becomes 44.5 weeks」/ §4 表 Sprint 10「34-37 wk」/ §14「+5 weeks Y1 timeline (Sprint 1A 1.5w → 7w)」— 三處算術不通：1.5w → 7w = +5.5w；39w + 5.5w = 44.5w；但 §4 Sprint 10 列 「34-37 wk」是 Y1 完成週次，而 §3 寫「Y1 becomes 44.5 weeks」表示 Y1 末（Y1 完成），兩者矛盾。Sprint 2-10 是否各自 shift right ~3w？看 §4 表：v5.7 Sprint 2 「4-7」 vs v5.8 「10-13」 = shift 6 週（非 5.5 週）；Sprint 10 v5.7「36-39」 vs v5.8「34-37」 = shift -2 週（縮短！）。**§4 表本身內部就矛盾**。 | CRITICAL |
| 4 | v5.8 §11 vs CLAUDE.md §二 第 5 原則「survival > profit」+ ADR-0024-lite | §11「Operator forgetfulness mitigation」逐條設計 M1 Tier 2 / M2 auto-disable / M3 auto-degrade / M7 auto-demote 都是「不需 operator click」。v5.8 §11 末段自承「Some decisions remain operator-only (Stage transitions, size scale ups, new strategy promotion, Copy Trading enable, capital tier activation)」— **但 M1 Tier 2「auto-execute」對 ADR-0024-lite「Cowork operator-assistant, not autonomous L2」邊界模糊**。M1 Tier 2 auto-execute = 跨策略 reweight = 改 capital allocation 是不是 size scale up？v5.8 §2 M1 寫「Tier 4 (capital structure / venue change): always operator approval」但 Tier 2「cross-strategy reweight」會改各策略 capital share 比例，與 Tier 4「capital structure」邊界 thin。 | HIGH |
| 5 | v5.8 §1 M10 「Tier C activation by AUM > $25k」 + §5 capital trigger | §5「$10-25k」對應「M4 active, M9 manual A/B」+「$25-50k」對應「M10 Tier C」— 但 §1 表 M10 phase 「Sprint 1A DESIGN + Sprint 8 Discovery Pipeline IMPL」+「Y2-Y3 scaling activation」。**Sprint 8 IMPL 但 Y2 才 active：那 Sprint 8 IMPL 的 Tier C 是 read-only logger？還是 detector？**spec 沒明寫；Tier C 在 v5.8 §2 M10 「Y2 Q1-Q2 if Copy Trading scaling on」與 §5 「$25-50k」也不一致（Copy Trading scaling pacing 至少要 6 mo gate 證據 + Y2 Q1 approve；$25-50k AUM 在 Y2 Q2-Q4 才到，§1 「Y2-Y3 scaling activation」更準）。 | MEDIUM |
| 6 | v5.8 §9 V### 編號 vs TODO §0.5 PM 仲裁 1 (option A) | TODO §0.5 PM 仲裁 1：「V097/V098 catch-up → V099/V100=Track v3 → V101/V102=Earn schema」；v5.8 §9 寫「v5.7 lineage: V097, V098: Linux DB catch-up (in flight) / V099, V100: Track v3 (per PM arbitration) / V101, V102: Earn schema (per PM arbitration) / V103, V104: hypotheses + preregistration (v5.7) — EXTEND in v5.8 for M4」— **這對；但 v5.8 §1 §2 §4 寫「V105」for M2 overlay state machine + 「V106」for M3 health + 「V107」for M11 replay**，§9 又改寫成「V105: overlay / V106: health / V107: replay / V108: ab / V109: anomaly / V110: reward / V111: discovery / V112: lease tier / V113: decay」— **V108 (ab) 與 §1 §2 對應的 V### 沒寫；V112 (lease tier) 與 §2 M1 沒寫**。整份 v5.8 V### 編號在不同位置不一致，PA dispatch 時必須統一。 | HIGH |
| 7 | v5.8 §10 風險表 vs CLAUDE.md §四 hard boundary | §10「New risks v5.8 introduces」5 條只列「schema sprawl / DESIGN-only debt / timeline shift / engineering 2.3x / Auto-Allocator gate unchanged」— **完全沒提**：(a) Sprint 4 首次 Live precondition = P0-EDGE-1 + P0-LG-3 + P0-OPS-1..4 + 5-gate live；TODO §0 + §4 全 ACTIVE 未 closed；v5.8 §1 表 Sprint 4「Top-1 live + Top-2 + Options Stack 1」+ M1 Tier 1 IMPL — 但 P0-EDGE-1 連 demo 5 策略 EV 都未證；(b) ADR-0024-lite Cowork 邊界對 M1 Tier 2 / M4 auto DRAFT generator 的 implications；(c) Earn governance § 1A spec 已 land 460 行（TODO §0.5 C8）但 v5.8 § 沒引用，可能 schema migration V105-V113 與 Earn governance V### 衝突 | CRITICAL |

---

## 0.5 13 module 依賴關係圖（v5.8 沒畫）

```
                  [M11 nightly replay]
                  /        |          \
            (input)    (input)      (input)
                 |        |           |
          [M7 decay] [M8 anomaly]  [M1 Tier 2 gate]
                |        |           |
            (gate)   (alert)     (auto-approve)
                |        |           |
          [M1 Tier 1] [M3 health]  [M6 weight auto]
                |        |           |
           (auto)    (degrade)  (within bounds)
                            |
                  [M2 overlay state machine]
                       |          |
                  (auto-disable)(auto-enable)
                       |          |
                  [M8 alert] [M9 A/B significance]

[M4 hypothesis miner] ⟶ DRAFT ⟶ operator+Cowork review ⟶ Tournament
                                                          |
                                                    [M10 Tier B]

[M10 Tier C-E] ← AUM trigger ← live PnL aggregator (Y2+)
[M5 online learning] ← Y3+ AUM trigger
[M12 routing adaptive] ← Y2 fill quality regression
[M13 multi-venue] ← Binance trade-enable ADR amendment
```

**未識別依賴撞點**：

1. **M1 Tier 2 auto-execute 依賴 M7 decay (auto-demote) + M11 replay divergence**：M11 在 Sprint 3 IMPL，M7 在 Sprint 8 IMPL，M1 Tier 2 在 Sprint 7-8 IMPL + Y2 enable。**Sprint 7-8 並行 IMPL 三個互相依賴模組** = 必撞。
2. **M2 overlay auto-disable 依賴 M8 anomaly active trigger + M11 counterfactual divergence**：M8 active trigger Y2 才有 / M11 Sprint 3 IMPL 但 hookup Sprint 5+。M2 §11 「auto-disable always-on」要在 Y1 就工作 — 但依賴 M11 hookup 沒到位，M2 auto-disable 沒 trigger source。Y1 M2 auto-disable = dead path。
3. **M6 reward weight auto 依賴 M9 統計顯著 + M1 Tier 2 auto-apply gate**：v5.8 §2 M6「Y2: Auto-weight update (≤ 30% change) enabled」— M9 A/B framework Y2 auto-gate active；M1 Tier 2 Y2 enable；三個全在 Y2 並行依賴。Y2 任一遲 delay 必拖另兩個。
4. **M10 Tier C-E AUM trigger 數據源**：v5.8 §5「7-day moving AUM > threshold sustained 30 day → trigger eval」 — **AUM 計算的 live PnL 來源是 trading.fills aggregation**；P0-EDGE-1 未證明 net-positive，AUM 在 Y1 末很可能 $9k-11k 區間（虧損或微利）；觸發 Tier C 的 $25k threshold 在 Y2 Q2 都可能達不到。**M10 Tier C-E 工時 ~$400-600 hr 是 contingent investment**。
5. **M4 DRAFT → Cowork review 工時**：v5.8 §2 M4 「Bot CANNOT promote」是對的，但**Cowork review 工時沒計入 v5.8 §4 hours**。Cowork review = operator + Cowork assistant 月度評審，每月 ~4-6 hr operator 時間；Sprint 10 / Y1 末 first 5-10 DRAFTs 評審 → ~20-50 hr operator hands-on（v5.8 §4 完全沒列）。

---

## 1. Top 3 執行性風險（找盲點）

### Risk 1：Sprint 1A 543-797 hr 在 7 週內派 5-7 並行 sub-agent 是 v5.7 12-prefix DONE 經驗 5x 規模

- **嚴重度**：CRITICAL
- **位置**：v5.8 §3 + §4 表 Sprint 1A
- **描述**：v5.7 12 prefix DONE 2026-05-21 single-day completion 是 **75-105 hr** + 7 並行 sub-agent + PM hands-on（TODO §0.5）— 那是 single-sprint 1A baseline。v5.8 §3 寫 **543-797 hr** 在 7 週分 5 階段（α/β/γ/δ/ε），於是「每階段平均 ~110-160 hr / 1-2 週」。但**並行 5-7 個 sub-agent**已是 v5.7 12-prefix DONE 的 cap；v5.8 §3 寫「Sprint 1A-β: M1, M3, M6, M7, M11 schemas + ADRs : 220-320 hr」要 5 個並行 sub-agent 連續 2 週 = 10-day sustained parallelism。**operator 5-10x 規律歷史對照**：v5.7 reviewer estim 60-80 hr → 仲裁 75-105 hr → 實際 single-day commit chain 75-105 hr 中段。v5.8 §3 數字本身 = reviewer-style estim（沒驗證 13 module zero-baseline）。**真實工時**對 zero-baseline 13 module schema + 7 ADR + 12 V### 應該是 reviewer estim × 1.2-2x = **650-1,600 hr**（v5.8 §3 已經是 reviewer-corrected 但仍偏 lower end）。

- **為何屬「執行性」**：sub-agent 並行 cap = 7（v5.7 prefix DONE 證實）。Sprint 1A-β/γ/δ/ε 強制要求連續 7 週 5-7 並行 sub-agent + operator hands-on 仲裁 + PM 簽核 = 7 × 5 = 35 sub-agent task；前面 v5.7 prefix DONE 一天 7 並行已是 hands-on heavy。**operator 人力是 hard ceiling，不是 hours**。

- **Must-fix 建議**：v5.8 必須在 §3 加「並行 sub-agent + operator 時間 budget」table — Sprint 1A-β 220-320 hr / 5-7 sub-agent / operator hands-on est. ~30 hr / PM 簽核 ~10 hr；同理 γ/δ/ε。如果 operator 月 hands-on budget < 60 hr，必須拉長 Sprint 1A-β/γ/δ/ε 至 12-14 週（每階段 3 週）。

### Risk 2：13 模組依賴撞點未識別 → PA dispatch wave 必撞 race

- **嚴重度**：HIGH
- **位置**：v5.8 §3 + §12 + 全文無依賴圖
- **描述**：見 §0.5 5 條未識別依賴。**最危險的撞點**：Sprint 7-8 三模組並行 IMPL（M1 Tier 2 / M7 decay / M11 nightly replay hookup）— v5.8 §1 表 Sprint 7 列「Top-5 + Advisory Allocator + M1 Tier 2 + M6 Advisory reward weights」+ Sprint 8 「Decay (M7) IMPL + M4 pattern miner stage 2 + M9 manual A/B + M3 recovery logic + M8 alerting」。**Sprint 7-8 並行 6+ 模組 IMPL** = PA wave 必撞共享 schema (decision_lease) / 共享 IPC (Strategist→Allocator) / 共享 Python helper（auth/audit）。v5.8 §3 五階段拆分只在 DESIGN 階段；IMPL 階段（Sprint 4-10）沒拆 wave。

- **為何屬「執行性」**：v5.7 Sprint 1A-β-ε 7 週分階段 = DESIGN 並行 OK；但 Sprint 7-8 IMPL 同時 M1 Tier 2 + M6 + M7 + M3 recovery + M8 alerting + M4 stage 2 + M9 manual A/B = 7 模組 IMPL 並行依賴 decision_lease + IPC + helper layer 共享資源 → 必有 dependency lock 必有 schema reuse 必有 PG dry-run 衝突。

- **Must-fix 建議**：PA dispatch Sprint 1A-β 前**必先寫 13 模組依賴圖 + Sprint 4-10 IMPL wave roster**（哪個模組哪個 Sprint 哪個 wave）+ 識別 shared resources（decision_lease writer / IPC schema / Python helper / V### number reservation）。

### Risk 3：Live deploy 五門 + P0 blockers 在 v5.8 §10 完全缺席 → Sprint 4 首次 Live 阻塞

- **嚴重度**：CRITICAL
- **位置**：v5.8 §10 vs CLAUDE.md §四 + TODO §0 §4
- **描述**：v5.8 §4 表 Sprint 4「Top-1 live + Top-2 + Options Stack 1 + M1 Tier 1 IMPL + M9 read-only」— Sprint 4 = Y1 W16-19（v5.8 timeline）= 第一個 live deploy 點。**Live deploy hard precondition**（TODO §0 + CLAUDE.md §四 hard boundary）：
  - P0-EDGE-1 net-positive edge（5 textbook 策略 ≥ 3 個 demo 7d avg_net > 5bps Wilson CI lower > 0）— **ACTIVE 未 closed**
  - P0-LG-3 Wave 2.4 IMPL DISPATCH PENDING — **ACTIVE 未 closed**（spec ready 10d 等 operator 拍板）
  - P0-OPS-1..4（HTTPS / credential rotation / legal / runbook）— **ACTIVE 未 closed**
  - 5-gate live：Python `live_reserved` + Operator role auth + `OPENCLAW_ALLOW_MAINNET=1` + valid secret slot + signed `authorization.json`
  v5.8 §10「Risk + Constraint Recheck」段只寫「all v5.8 modules respect 5-gate live deploy」— **沒寫 P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 是 Sprint 4 Live precondition**。如果 Y1 W12-15（v5.7 timeline）或 W16-19（v5.8 timeline）這 4 條 P0 不全 closed，Sprint 4「Top-1 live」根本不能啟動。

- **為何屬「執行性」**：v5.8 §0「Operator REJECTED that push-back」是模組設計層；但 dispatch 派工層仍受 CLAUDE.md hard boundary + TODO active P0 阻塞。**v5.8 §12 dispatch plan 4 個 operator decision point 完全沒提這 4 條 P0**。

- **Must-fix 建議**：v5.8 §10 必須加 Section 「Sprint 4 Live precondition」明確列 P0-EDGE-1 + P0-LG-3 + P0-OPS-1..4 + 5-gate；§12 operator decision point 必須加第 5 條「**operator 確認 P0-EDGE-1 / LG-3 / OPS-1..4 ETA**，否則 Sprint 4 自動降級為 LiveDemo」。

---

## 2. 工時 5-10x 規律對照

### Sprint 1A 543-797 hr 真實估

v5.7 12 prefix DONE 真實工時：**75-105 hr**（仲裁中間值）+ 12 並行 sub-agent + PM hands-on + 1 天 commit chain。13 模組 schema + 7 ADR + 12 V### 比 v5.7 prefix DONE **複雜度 ~5-8x**（zero-baseline schema 比 prefix fix 重 3-5x；新 ADR 0034-0040 比 ADR-0030-0033 amend 重 2-3x）。

| 工時來源 | v5.8 §3 estim | 真實估（× 1.2-2x） |
|---|---|---|
| M1 lease tier schema + ADR-0034 | 60-80 | 80-160 |
| M2 overlay state machine schema + V105 | 40-60 | 50-120 |
| M3 health domain schema + V106 | 40-60 | 50-120 |
| M4 hypothesis discovery schema extension | 30-50 | 40-100 |
| M5 online learning interface stub | 8-12 | 10-25 |
| M6 reward weight history schema | 40-60 | 50-120 |
| M7 decay signals schema | 40-60 | 50-120 |
| M8 anomaly events schema + ADR-0036 | 40-60 | 50-120 |
| M9 A/B framework schema + ADR-0037 | 50-70 | 60-140 |
| M10 discovery tier schema | 30-50 | 40-100 |
| M11 replay divergence log + ADR-0038 | 40-60 | 50-120 |
| M12 OrderRouter interface + ADR-0039 | 20-30 | 25-60 |
| M13 AssetClass + ADR-0040 | 30-40 | 40-80 |
| **Sprint 1A v5.8 add** | **468-692** | **595-1,385** |
| + v5.7 baseline (12 prefix DONE 已含 V103/V104/Earn) | 75-105 | 75-105 |
| **Sprint 1A v5.8 total** | **543-797** | **670-1,490** |

**真實估 vs v5.8 estim ratio = 1.2-1.9x**。v5.8 §3 數字偏 lower end，但相比 v5.7 reviewer 60-80 hr → PM 仲裁 75-105 hr → 真實 75-105 hr 已 reviewer-corrected — **v5.8 §3 estim 仍有 20-90% upward risk**。

### Y1 total 2,780-3,930 hr 真實估

v5.8 §4 表 Y1 total = 2,780-3,930 hr；reviewer range 2,000-7,800 hr；v5.8 §10 自承「lower bound of reviewer range」。Y1 total 包含 Sprint 1A-10；以 Sprint 1A 1.2-1.9x ratio 推到 Y1 total：**3,340-7,470 hr**。如果取中段：**4,500-5,500 hr 是 Y1 真實估**。v5.8 估 3,200 hr median 偏低 ~30-70%。

### operator 5-10x 規律歷史對照

| 任務 | reviewer estim | LLM/PA estim | 真實 |
|---|---|---|---|
| v5.7 Sprint 1A | 60-80 hr (v5.7) | 75-105 hr (PM 仲裁) | 75-105 hr (12 prefix DONE) |
| v5.7 Y1 total | 1,190-1,590 hr (v5.7) | 1,275-1,710 hr (PM 仲裁) | unknown（Y1 未跑完） |
| v5.8 Sprint 1A | 468-692 hr (v5.8 add only) | 543-797 hr (v5.8 total) | 估 670-1,490 hr |
| v5.8 Y1 total | 2,780-3,930 hr | (同) | 估 4,500-5,500 hr |

**結論**：v5.7 已是 reviewer-corrected lower end；v5.8 同樣是 reviewer-corrected lower end。**operator 5-10x 規律的「真實值 = reviewer × 5-10x」是針對「未經 reviewer correction 的 LLM 初估」**；v5.8 已過 reviewer，所以倍率降至 1.2-2x（與 v5.7 audit Risk 2 相同論斷）。

---

## 3. operator forgetfulness mitigation 反向 attack 盲點

v5.8 §11 寫的「mitigation」逐條反向 attack：

| Mitigation | 反向 attack |
|---|---|
| **M1 Tier 2 auto-approval 24h undo** | 24h 內 bot 可能下 50-100 個 fill；undo「rollback to pre-proposal state」對 fill PnL **不可逆**（已出的單已成交）；只能 rollback proposal 參數，不能 rollback 倉位。Operator opt-in 後 forgot 看 Slack 通知，**24h 已 fill 部位無法 unwind**。 |
| **M2 overlay auto-disable always-on** | 觸發條件「30d Sharpe < 0 AND counterfactual diverges」+「regime change anomaly M8 flags + coupled drawdown」+「macro false-positive > 3 in 90d」— **false-positive sensitivity**：M8 anomaly 在 vol regime shift（normal market behavior）會觸發；如果 BTC 從 30% IV 升到 60% IV 是正常 regime shift，M2 auto-disable 會把 macro overlay 完全停掉，可能在 overlay 真有 alpha 時誤殺。 |
| **M3 HEALTH_DEGRADED throttle Tier 1** | M3 觸發條件「WS latency spike / DB write backlog」— **false-positive 在 healthy market burst**（NFP 公布、CPI 公布瞬間 WS 流量 spike 是正常）；M3 throttle 會在最關鍵的 high-vol moment 停止 reparam，可能錯過 alpha window；v5.8 §2 M3 沒寫 recovery hysteresis（HEALTH_DEGRADED → HEALTH_NORMAL 需多久穩定）= 可能 flap。 |
| **M7 auto-demote 50% size pending review** | review 窗口 14d 期間策略持續 lose 怎辦？v5.8 §2 M7 寫「STAGE_DEMOTED → live size scaled to 50% pending review」+「Review window (14 d) → either RECOVER (re-promote) or RETIRE (size = 0)」 — **14d × 50% size 可能繼續 -$200-500 損失**；應加「DEMOTED 後若 demoted 期間累積 loss > X% → 立刻 retire 跳 review」。 |
| **M8 alert severity → M3 auto-degradation** | M8 high-severity = correlation break + funding dislocation — **這些是市場異常事件，正是 alpha 發生時刻**（funding flip 是 funding_arb 入場信號，correlation break 是 pairs trading 入場信號）；M3 throttle 會在 alpha window 退出 = 反 alpha；v5.8 沒區分「market anomaly =alpha source」與「own behavior anomaly = halt」。 |
| **M11 daily replay quality report Slack** | operator 月忘記查 Slack 怎辦？v5.8 §2 M11 寫「Daily replay quality report → operator (Slack)」 — **passive report 沒 automation**；應加「報告 > 5 連續日 high-divergence flag 不被 acknowledge → 自動升 M3 HEALTH_WARN」。 |

**ADR-0024-lite + 16 root principles 第 7 原則「Learning must not rewrite live state directly」對 M1 Tier 2 auto-execute 的張力**：M1 Tier 2「跨策略 reweight」= Allocator 改變 capital allocation per strategy = **改 live state**。v5.8 §2 M1 寫「Tier 2 (cross-strategy reweight): Advisory Y1 / Auto Y2 with gate」— 但**「Auto Y2 with gate」是 ADR-0024-lite 邊界外**（Cowork operator-assistant，不是 autonomous L2）。v5.8 §11 末段自承「Some decisions remain operator-only (Stage transitions, size scale ups, new strategy promotion, Copy Trading enable, capital tier activation)」+ Tier 4 「always operator approval」— 但 Tier 2「跨策略 reweight」沒在 operator-only list 上；**M1 Tier 2 Auto Y2 與 ADR-0024-lite 衝突未在 v5.8 §10 §11 任何位置 surface**。

---

## 4. schema sprawl V103-V116 race-aware

### 4.1 V103/V104 EXTEND for M4 vs v5.7 已 land

TODO §0.5 C3：v5.7 V103/V104 schema spec land 940 行（PA + MIT）。v5.8 §9「V103, V104: hypotheses + preregistration (v5.7) — EXTEND in v5.8 for M4」— **EXTEND 內容沒寫**。M4 §2 「hypothesis_drafts table + state machine (already partly in V103; extend +30 hr)」— 是 ALTER TABLE add column？還是新增表（V103 中 hypothesis_drafts 已存在但 state 不夠）？

**Race scenario**：
- 2026-05-22 PA 派 V### re-number search/replace（TODO §0.5 must-fix）→ V103/V104 號碼鎖定為「hypotheses + preregistration」
- 2026-05-23+ v5.8 Sprint 1A-β 派 PA 寫 V103/V104 EXTEND spec for M4 → PA 必須拆「ALTER TABLE」at V107+ 或 inline V103
- 如果 inline V103 = 違反 V### immutability（V103 spec 已 land 2026-05-21）
- 如果 V107+ = 號碼又 race（v5.8 §9 V107 已 reserved for M11 replay）

### 4.2 V### 編號 v5.8 各處不一致（見 §0.2 #6）

PA dispatch Sprint 1A-β 前**必須統一 V### 編號表**。建議寫一個 V### registry 表 land 在 dispatch packet。

### 4.3 13 schema 同時 PG dry-run

CLAUDE.md「Data, Migrations, And Validation」要求「V### migrations with PG reflection... do Linux PG empirical dry-run before implementation sign-off」+「Migration idempotency must be tested by applying twice」。**13 V### 在 Sprint 1A-β/γ/δ/ε 同時推進 = 13 次 PG dry-run + 13 次 idempotency test**。v5.7 12 prefix DONE 一個 PG dry-run（V103/V104 head=V096 verification）已是 PA + MIT 合作；13 次 dry-run 在 7 週內 = operator + Linux PG access slot 緊張。

**Must-fix**：v5.8 必須加 PG dry-run cadence 表 — 哪週哪個 V### 跑 dry-run（避免並行衝突）。

---

## 5. P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 在 v5.8 缺席 → Sprint 4 Live 阻塞風險

詳 §1 Risk 3。v5.8 全文 grep「P0-EDGE-1」「P0-LG-3」「P0-OPS-1」全 zero hit；§10 風險表只提「5-gate live deploy (no bypass)」。

**operator decision point §12 4 條缺第 5 條**：
1. Approve v5.8 13-module scope
2. Approve Y1 timeline 39w → 44w
3. Approve engineering 2.3x
4. Confirm interface-stub policy
5. **MISSING**: Confirm P0-EDGE-1 / LG-3 / OPS-1..4 ETA OR accept Sprint 4 auto-降級 LiveDemo

**Must-fix**：v5.8 §12 加第 5 條 operator decision；§10 加 P0 precondition table。

---

## 6. 對 PA+FA+PM 匯總必收 top 3

1. **PA: 寫 13 模組依賴圖 + Sprint 4-10 IMPL wave roster + V### registry 表**（~6-10 hr；Sprint 1A-β 派發前必先 land）— 識別 Sprint 7-8 shared resources（decision_lease writer / IPC schema / Python helper / V### number）+ 給 PA dispatch 用的 wave 排程；V### registry land 後 v5.8 §1 §2 §3 §4 §9 一致化（PA fix doc cross-ref）。

2. **FA: 評估 M1 Tier 2 Auto Y2 是否 ADR-0024-lite 邊界內**（~2-4 hr）— Cowork operator-assistant 定義 vs 「跨策略 reweight = 改 live capital allocation」= 是否屬「Stage transition / size scale up / capital structure」邊界；若 FA verdict = 是邊界外，v5.8 §2 M1 Tier 2「Auto Y2 with gate」必須改為「Advisory Y2 with manual operator approval per proposal」。同步審 M6 Auto weight 是否 ADR-0024-lite 邊界內。

3. **PM: 仲裁 v5.8 §10 §11 §12 三大缺口**（hands-on ~4-8 hr）— (a) §10 加 P0 precondition table；(b) §11 加 6 條反向 attack 對應 mitigation；(c) §12 加第 5 條 operator decision point + Sprint 1A 並行 sub-agent + operator hands-on time budget 表。

---

## 7. v5.8 派發前 must-fix

| # | Owner | 工時 | 任務 |
|---|---|---|---|
| 1 | PA | 6-10 hr | 寫 13 模組依賴圖 + Sprint 4-10 IMPL wave roster + V### registry 表（統一 §1 §2 §3 §4 §9 V### 編號）+ Sprint 1A 並行 sub-agent 排程（α/β/γ/δ/ε 各階段 5-7 sub-agent + operator hands-on time budget） |
| 2 | FA | 2-4 hr | 評估 M1 Tier 2 Auto Y2 + M6 Auto weight 是否 ADR-0024-lite 邊界內；若否，v5.8 §2 改 Advisory + manual approval |
| 3 | PM | 4-8 hr | 仲裁三大缺口：§10 加 P0 precondition table（P0-EDGE-1 / LG-3 / OPS-1..4 + 5-gate live + ADR-0024-lite Cowork 邊界）+ §11 加反向 attack mitigation（6 條）+ §12 加第 5 條 operator decision point + Sprint 1A parallel sub-agent budget table |
| 4 | PA + MIT | 5-8 hr | V103/V104 EXTEND for M4 規格 — ALTER TABLE 還是新增表（V107+）；如 inline ALTER 必跑 V### re-PG-dry-run + idempotency test |
| 5 | PA | 3-5 hr | V### dry-run cadence 表 — 13 V### 7 週 schedule 哪週跑哪個（避免 PG slot 並行衝突 + operator hands-on slot） |
| 6 | PM + operator | hands-on 0.5-1 hr | TODO §1 路線變更區補填 v5.8 approve + Sprint 1A-β 啟動標記 + §10 加 v5.8-S1A-β task ID + 鏈到 v5.8 文件路徑（CLAUDE.md「TODO.md 是 active state authority」原則） |

完成前 5 項後 + operator 完成第 6 項 = v5.8 變 GO-WITH-CONDITIONS。

---

## 8. Sprint 1A-β-ε 期間 should-fix

| # | Owner | Sprint 階段 | 任務 |
|---|---|---|---|
| 1 | PA + MIT | 1A-β | M11 nightly replay schema + ADR-0038 必先 land（M2 / M7 / M8 都依賴 M11 replay divergence input） |
| 2 | QC + MIT | 1A-γ | M9 A/B framework statistical methodology 規格 — mSPRT + Bonferroni/FDR + effect size threshold + sample size pre-calc；對應 v5.7 audit Risk 6（counterfactual A/B framework 規格未定）的 v5.8 升級版 |
| 3 | E1 + E2 | 1A-δ | M5/M12/M13 interface stub「unimplemented panic!」設計 — Rust trait 怎樣 stub 才不死代碼；Y3+ IMPL trigger 應該是 explicit ADR retirement criteria（v5.8 §10 自承）但 retirement criteria 沒寫具體；補 ADR-0035/0039/0040 retirement criteria 明確化 |
| 4 | CC + FA | 1A-ε | Cross-ADR consistency audit — 4 + 7 = 11 ADR 跨引用一致性；ADR-0024-lite 對 M1/M4/M6/M10 的 implications 明確化 |
| 5 | FA + E3 | Sprint 2 | M10 AUM trigger 數據源 spec — live PnL aggregation 延遲；7-day moving AUM 計算頻率；30 day sustained 條件下，AUM 數據可信度（trading.fills 是否 source of truth？wallet balance API 是否更可信？） |
| 6 | FA | Sprint 3-4 | M2 overlay auto-disable 反 alpha 風險量化 — 模擬 BTC IV 30%→60% regime shift 觸發 M8 anomaly + M2 auto-disable 的 alpha 損失；補 hysteresis 設計（auto-disable cooldown 至少 30 d 才能重新 auto-enable） |
| 7 | QA + E4 | Sprint 4-7 | M1 Tier 2 24h undo 真實影響範圍 — 24h 內 fill 部位 unwind 成本；建議改為「24h proposal undo 只能 cancel 未 fill 部位 + 改參數 forward-only，已 fill 部位需 operator 手動 unwind 不自動 reverse」 |

---

**E2 REVIEW DONE: HOLD · report path: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-21--v58_executability_audit.md**
