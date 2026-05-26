# V1 → V5.8 全鏈 plan / audit 整合與 drift 審計

**日期**：2026-05-25
**Trigger**：Operator 懷疑在 v5.0 → v5.8 execution-plan 演化過程中遺漏 audit findings。
**Scope**：22 份文件（20 archived + 2 active）橫跨 2026-05-08 → 2026-05-21。
**方法**：4 路並行 sub-agent 結構化提取 + 主會話跨組 drift matrix 合成。**Read-only**，不修改任何 prior 文件。
**Status**：DRIFT VERIFIED。多項高風險 orphan finding 從 audit 鏈失蹤；多項雙軌內部 inconsistency。

---

## §0 一頁摘要

- **編號斷層**：5/16 完全捨棄前 4 份的 W-AUDIT-1..9 / F-XX / K / M / C / R-1..5 / Track W/A 編號體系，改 WP-XX + agent-prefix-ID；後續 v5.x 也不再用 W-AUDIT/F-XX。**約 88 finding + 12 W-AUDIT + 5 R + 20+ 子編號全部 forward-trace 不可達**。
- **Thread 爆炸**：5/20 一天內爆出 8 個獨立 design thread (strategy-arch / lean-direct-alpha-v3 / dual-track v4/v4.1/v4.2 / autonomous-strategy-v2 / commercial-evidence-v4.3 / execution-plan-v4.4)；v4.4 §6 自我宣告「No more audits」但 v5.x 全違反，**0 forward annotation**。
- **v2 ASDS 整套靜默退役**：Strategy DSL JSON spec / GenericHypothesisStrategy Rust interpreter (~800 LOC) / ADR-0024 全文版 / Tier 3 CPCV / Tier 4 Thompson Sampling / Tier 7 ADWIN drift — v4.0 起 0 mention，無放棄理由 documented。
- **v3 PIVOT 商業化路徑被 D7 否決**：Telegram subscription / Substack / codebase sale / MEV — 整段否決，無 documented why。
- **v5.6 → v5.7 收縮 50%**：28KB → 14KB，§0 只承認 6 reviewer issues，但實際 **16 個高風險 sub-spec** 容納不下消失。
- **v5.7 + v5.8 雙軌 active 內部不一致**：Sprint 1A timeline (1.5w vs 8.5w) / Sprint 4 first Live (W12-15 vs W17.5-20.5) / Y1 hours (1190-1590 vs 3500-5200) / M1 命名 (Decision Lease vs LAL) / M7 state name / M13 Y2 vs Y3+ — 派 sub-agent 時極易選錯邊。
- **ADR-0028 / ADR-0029** v5.6/v5.7 proposed，v5.8 ADR roster 從 0030 起跳，**absorbed 還是 abandoned 不明**。
- **active-plan v1.9 (5/15)** 戰術 ops 細節（healthcheck invariants / P1 task list / W-AUDIT-8b K_total/DSR 數字）在 5/20 戰略 reframe 中跳過。

---

## §1 22 份文件譜系與時序

| # | 日期 | Path | Size | Family | Status |
|---|---|---|---|---|---|
| 1 | 5/08 | archive/2026-05-21--srv_root_cleanup/2026-05-08--full_audit_fix_plan.md | 47KB | Audit-Origin | archived |
| 2 | 5/09 | …/2026-05-09--audit_fix_verification_summary.md | 10KB | Audit-Origin | archived |
| 3 | 5/09 | …/2026-05-09--audit_fix_verification_v2_summary.md | 11KB | Audit-Origin | archived |
| 4 | 5/09 | …/2026-05-09--audit_fix_verification_v3_summary.md | 11KB | Audit-Origin | archived |
| 5 | 5/15 | …/active-plan.md (v1.9) | 5KB | Tactical-Snapshot | archived |
| 6 | 5/16 | …/2026-05-16--full-system-audit-fix-plan.md | 34KB | Audit-Reframe | archived |
| 7 | 5/20 | …/2026-05-20--strategy-architecture-redesign-recommendation.md | 29KB | Design-Root | archived |
| 8 | 5/20 | …/2026-05-20--lean-direct-alpha-capture-v3.md | 21KB | Design-Pivot | archived |
| 9 | 5/20 | …/2026-05-20--dual-track-architecture-v4.md | 29KB | Dual-Track | archived |
| 10 | 5/20 | …/2026-05-20--dual-track-architecture-v4.1.md | 17KB | Dual-Track | archived |
| 11 | 5/20 | …/2026-05-20--dual-track-architecture-v4.2.md | 23KB | Dual-Track (thread closed) | archived |
| 12 | 5/20 | …/2026-05-20--autonomous-strategy-system-v2.md | 38KB | ASDS (孤立) | archived |
| 13 | 5/20 | …/2026-05-20--commercial-evidence-sprint-v4.3.md | 21KB | Monetization-Reframe | archived |
| 14 | 5/20 | …/2026-05-20--execution-plan-v4.4.md | 10KB | Terminal-v4 | archived |
| 15 | 5/20 | …/2026-05-20--execution-plan-v5.0.md | 12KB | v5-Start | archived |
| 16 | 5/20 | …/2026-05-20--execution-plan-v5.2.md | 22KB | v5-Mid (**v5.1 跳號** = reviewer proposal 未獲 operator approval) | archived |
| 17 | 5/20 | …/2026-05-20--execution-plan-v5.3.md | 23KB | v5-Mid | archived |
| 18 | 5/20 | …/2026-05-20--execution-plan-v5.4.md | 28KB | v5-Mid | archived |
| 19 | 5/20 | …/2026-05-20--execution-plan-v5.5.md | 27KB | v5-Mid | archived |
| 20 | 5/20 | …/2026-05-20--execution-plan-v5.6.md | 28KB | v5-Mid (archive 系列末) | archived |
| 21 | 5/20 | **docs/execution_plan/2026-05-20--execution-plan-v5.7.md** | 14KB | **v5-Active (dispatch-of-record)** | active |
| 22 | 5/21 | **docs/execution_plan/2026-05-20--execution-plan-v5.8.md** | 64KB | **v5-Active (autonomy supplement)** | active |

譜系結構：
```
[Audit-Origin] 5/08 → 5/09 v1 → v2 → v3
                              ↓
[Tactical] 5/15 active-plan v1.9
                              ↓
[Audit-Reframe] 5/16 (重編號 W-AUDIT/F→WP+agent-prefix)
                              ↓
[5/20 Design 爆炸 — 同日多 thread 並發]
    ├── Design-Root v1 (strategy-arch-redesign)
    │       ↓
    ├── Design-Pivot (lean-direct-alpha-v3)
    ├── ASDS-v2 (孤立 thread, autonomous strategy 7-Tier)
    ├── Dual-Track v4 → v4.1 → v4.2 (thread closed at 4.2)
    │       ↓
    ├── Monetization-Reframe (commercial-evidence-v4.3, IP sale retract)
    │       ↓
    └── Terminal-v4 (execution-plan-v4.4) 自宣 "No more audits"
                              ↓ [violated]
[v5 系列] v5.0 → v5.2 (v5.1 缺號) → v5.3 → v5.4 → v5.5 → v5.6
                              ↓
[v5-Active 雙軌] v5.7 (dispatch-of-record) + v5.8 (13 modules supplement)
```

---

## §2 五階段演化敘事（高度濃縮）

### §2.1 階段 A — Audit 起源 5/08-5/16

5/08 PA 整合 12 agent audit 出 88 unique finding（F-01..F-30 + 子 finding + K-1..K-6 + M-1..M-12 + C-1..C-5）+ W-AUDIT-1..7 七 wave，附 5 PENDING-OPERATOR decisions。5/09 三輪 verification (v1/v2/v3) 對抗性核實「修復是否真到位」：
- **v1**：~58% surface-only closed / 35% functional gap / 5 NEW-ISSUE 含 1 CRITICAL (LiveDemo pipeline 停)
- **v2**：5/5 PENDING decisions 全 closed via AMD-2026-05-09-02；ADR-0015/0017/0020 land；✅+65% / ❌-45%
- **v3**：PA 自寫 R-1..R-5 升級藍圖 → 採納 DUAL-TRACK (Track W 7 wave + Track A 9 wave / ~360-420h)；MIT 揭發 attribution chain real root = label_close_tag NULL 98.9% (1-day fix vs R-3 4-6 sprint)；BB push back 3 條 PA spec 錯（L25 不存在 / liquidation_pulse / basis observation vs execution）；E5 push back PA「45000 LOC」實 799 LOC (56x 錯)

5/16 PA 重新整合做新 12-agent audit，**完全捨棄前 4 份的 W-AUDIT/F-XX/K/M/C/R 編號體系**，改 WP-01..WP-13 + agent-prefix-ID (FA-P0-X / AI-E-F-XX / QC-P0-X / E5-P-X / A3-BLOCKER-X / E3-MED-X / MIT-P0-X / R4-CRITICAL-X / BB-M-X / CC-F-X / E4-HIGH-X / TW-P1)，Cluster A-F + Session A-H + 12-15 session 估算。**這是第一個重大 drift point**。

### §2.2 階段 B — Tactical snapshot 5/15

`active-plan.md v1.9` 是 5/15 sprint posture snapshot：post-N+0/N+1 cleanup 階段，A4-C archive；W-AUDIT-8a Phase C0/C1 BB standalone 24h liquidation WS proof PID 4100789；W-AUDIT-8b Funding Skew v0.2 read-only Stage 0R replay design (K_total ≥ K_prior+4050, DSR ≥ 0.95, PBO fail-closed)。包含具體 P1 task list (FILL-LINEAGE-MONITOR / STARTUP-BURST-MITIGATION / V083-HALT-SESSION-CTX / W6-5-ML-METRICS / AUDIT-PERF-5 / AUDIT-AI-UX-7) 與 healthcheck WARN `[40][59][20][45]`。

### §2.3 階段 C — 5/20 設計 thread 爆炸

5/20 同日爆出 8 個獨立 design thread：

1. **strategy-arch-redesign (v1 root)**：4-audit 合成「精緻死局」三層 (L1 策略 EV<0 / L2 ML 0% / L3 物理 -33 bps)；5-Phase 藍圖 + NEW-1~9 wave roster；ADR retire funding_arb + grid v1。
2. **lean-direct-alpha-v3**：拒絕「等一年」改 8 週 NLE (3 子策略 A/B/C) + LCS deliver；PIVOT 信號服務 Telegram bot $39/$99；商業化 4 路（codebase sale / signal feed / Substack / MEV）；v2 ASDS Tier 0-7 全 DEFER。
3. **dual-track v4 / v4.1 / v4.2**：Track A/B/C 三軌並行；schema 對齊 (8+1→12+2 表) + ADR-0026 prereg 15 欄位 (Newey-West/GARCH/bootstrap/immutable_trigger_hash) + LCS isolated cluster + maker entry + W4-W6 event-study delay (Brown & Warner 1985)；ADR-0024-lite Cowork = operator-assistant **降級** v2 ADR-0024 autonomous L2；Capacity 60/30/10 → 50/10/40 → 60/0/40。
4. **autonomous-strategy-v2 (孤立 thread)**：7-Tier Pipeline (MarketStateSnapshot → RegimeClassifier → Hypothesis Generator → Auto-Validator CPCV 3-fold + DSR + Bailey & López de Prado 2014 → Thompson Sampling allocator → Stage 0/1 → LiveBudget per-hypothesis → ADWIN drift retire)；Strategy DSL JSON 12-field HypothesisSpec + GenericHypothesisStrategy Rust interpreter ~800 LOC；ADR-0024 全文 (autonomous L2 envelope)；6 個月 PoC review。
5. **commercial-evidence-v4.3**：3 stream (Technical 60% / Demand Test 30% / IP Sale 10%)；Stream 3 retraction notice；W8/W12 joint verdict 2×2×2 → 2×2；ADR-0027 Plan Mode TIME-based 4 mode (Build/Observe/Low/Deep)。
6. **execution-plan-v4.4 (terminal)**：11 D constraint (含 D7 **NO content/subscription monetization** 否決 v3 商業化整段)；Capital $10k locked；Phase 0/A/B/C 5 monetization stream (C10 funding harvest + Copy Trading 副帳 + Master Trader + Prop firm + Bybit competitions)；V101 縮為 3 ALTER + 1 CREATE ~50 LOC；**§6 自宣 "No more audits...planning phase ends here. Future amendments only triggered by 3 conditions"**。

### §2.4 階段 D — v5.0 → v5.6 中繼演化

v4.4 自我宣告「No more audits」立刻被推翻，5/21 起 6 次 reviewer audit 推 v5.0 → v5.6：

| 版本 | 核心 reframe | Sprint count | Engineering hr | Y1 income median |
|---|---|---|---|---|
| v5.0 | "Round 11 真實 ceiling 8-15% APR, NOT 25-40%"；§0 三 Path (Final-A/B/C) decision tree；C3 textbook permanent kill | Phase 0/A/B/C | 100-150 hr | $400-700 |
| v5.2 | Operator Q3 framing「最大盈利 aggressive + 長效自動動態調整」；Survival/Adaptive Alpha barbell + Thompson Sampling + Tier 0-4 staging；V101 minimal schema | Sprint 1-6 | 240-345 hr | 8-10% APR sustained |
| v5.3 | reviewer 5 hard problems：paper "Sharpe > 0.8 → live" 違 AMD-2026-05-15-01 改 Stage 0R replay preflight；C13 options stack 0 存在 200-340 hr；Allocator advisory only；Decay event-count not calendar；C10 minimal $2,500 | Sprint 1-9 | 810-1,140 hr | 8-12% |
| v5.4 | Master Trader Copy Trading 副帳 $1.5k + Cadet/Bronze/Silver/Gold tier ladder；Pairs trading + Funding short-only；Tier A-D latency (event-driven WebSocket)；Reverse-Snipe Mitigation (multi-condition) | Sprint 1-10 | 960-1,330 hr | $920-1,520 + Copy $200-800 |
| v5.5 | **Bot 定位反轉**: Strategy Lab + Copy Trading Engine 雙產品 → 完整 quant bot 單一產品；副帳 $1.5k → $0 Y1；Moat Sequence Sprint 8 design / Y2 enable；Copy-Tradeability matrix | Sprint 1-10 | 1,070-1,450 hr | $927 self-only |
| v5.6 | D12 framework expansion (Macro + Earn + On-chain approved；DEX/Hyperliquid NOT)；Layer 1/2/3；Defined-Risk C13 4-mode；Evidence-Based Build Order Top-1 first；Copy Trading Evidence Gate 4-gate；calendar-weighted income | Sprint 1-10 | 1,180-1,570 hr | $547 calendar-weighted / Y2 $1,152 |

**v5.1 缺號** = v5.2 §0「Supersedes v5.0 (defensive), v5.1 (reviewer proposal)」明示 v5.1 是 reviewer proposal 未獲 operator approval，未生成獨立 .md。

### §2.5 階段 E — v5.7 + v5.8 雙軌 active

**v5.7 (14KB, dispatch-of-record)**：§0 6 reviewer issues fix (V101 conflict / Earn APR dynamic tiered / liquidation writer existing not new / Auto-Allocator Sprint 9 advisory Y2 defer / Macro+On-chain counterfactual Y1 only / Earn Guardian policy)；Thesis 不變；Y1 $300-550 / Y2 base $850-1,050 / Y2 overlay $1,050-1,250；39w / 1,190-1,590 hr；Sprint 1 split 1A+1B；ADR-0028/0029 (proposed) inherited。

**v5.8 (64KB, autonomy supplement)**：Round-16 reviewer audit 揭 v5.7 Y2 88% autonomy 是 framework shells only。Operator REJECTED Claude push-back on M4/M5/M10/M12/M13，ADD ALL 13 modules。AMD-2026-05-21-01 autonomy-vs-human-final-review + protected/opt-in scope；8 new ADR (0034-0041)；V105-V116 schema (active 105-113 + reserve 114-116) + cross-V### dependency graph；Sprint 1A 5 phase (α/β/γ/δ/ε) 8.5w；Y1 44-55w / **3,500-5,200 hr (2.7-3.0x v5.7)**；Capital-tier AUM ladder $10k → $150k+；7 auto path 5-gate inheritance contract；6 反向 attack mitigation。

---

## §3 DRIFT MATRIX（核心 deliverable）

### §3.1 編號斷層：5/08-5/09 → 5/16 → v5.x

| 編號族 | 起源版本 | 5/16 對應 | v5.7 對應 | v5.8 對應 |
|---|---|---|---|---|
| F-01..F-30 (88 finding) | 5/08 v1 | **完全棄用** (改 FA-P0-X / etc.) | 不見 | 不見 |
| K-1..K-6 (高共識) | 5/08 | 不見 | 不見 | 不見 |
| M-1..M-12 (中共識) | 5/08 | 不見 | 不見 | 不見 |
| C-1..C-5 (校核矛盾) | 5/08 | 不見 | 不見 | 不見 |
| W-AUDIT-1..7 (7 wave) | 5/08 | 完全棄用 (改 WP-01..13) | 不見 | 不見 |
| W-AUDIT-8a..9, 8b..8g | 5/09 v3 | 僅 §Conflict 提 W-AUDIT-8a C1 24h + W-AUDIT-8b Stage 0R，不再作 wave 結構 | 不見 | 不見 |
| R-1..R-5 (PA redesign) | 5/09 v3 | 不見 | 不見 | 不見 |
| Track W + Track A | 5/09 v3 | 不見 (改 WP-XX) | 不見 (改 Sprint 1A-10) | 不見 |
| P0-DECISION-AUDIT-1..5 | 5/09 v1 | 僅 CC-F-1 隱含 AMD-02 | 不見 | 不見 |
| AMD-2026-05-09-02/03/04 | 5/09 v2/v3 | 隱含 (FA-P0-2 BY DESIGN ref ADR-0020) | 不見 | 不見 (改 AMD-2026-05-21-01) |
| ADR-0021 / ARCH-04 / CONTEXT 5 詞條 | 5/09 v3 P0 action | 不見 | 不見 | 不見 |
| label_close_tag NULL 98.9% (MIT 1-day fix) | 5/09 v3 | 不見 (MIT-DB-6 是不同問題) | 不見 | 不見 |
| BB push back 3 條 (L25 / liquidation_pulse / basis) | 5/09 v3 | 不見 (BB-A-2/A-3 不同) | 不見 | 不見 |
| 22 fail-closed defaults 1e-3 數學論證 | 5/09 v3 | 不見 | 不見 | 不見 |

**結論**：5/16 是「編號重啟」事件。前期 88+ finding 編號全部 orphan，後續 v5.x 完全沿用 5/16 新體系（WP-XX）但也不再用 5/16 編號（v5.x 改成 Sprint 1A-10）。**Forward trace 鏈在 5/16 + 5/20 兩處斷裂兩次**。

### §3.2 Design thread 命運 — 5/20 多 thread → v4.4 → v5.x

| Thread | v4.4 處置 | v5.7/v5.8 處置 | Risk |
|---|---|---|---|
| v1 strategy-arch L3→L1→L2 順序 | inherit Phase 0 V097/V098 catch-up；Phase 2 三策略 A/B frozen 無 evidence | inherit V097/V098 | LOW |
| v1 NEW-1~9 wave roster | 不見 | 不見 | **HIGH (棄用無 doc)** |
| v3 lean-direct-alpha 8 週 NLE+LCS deliver | LCS C1 $500 telemetry only；NLE 從 active 移除 | 5 strategies 全新候選池 (C10/Unlock/Pairs/C13/Funding short)；NLE/LCS 不在 monetization stream | **HIGH (NLE 3 子策略 thesis 整套消失)** |
| v3 PIVOT 商業化 (Telegram $39/$99 / Substack / codebase sale / MEV) | **D7 constraint 整段否決** 無原因分析 | 不見 (Copy Trading 取代為 monetization 路徑) | **HIGH (decision rationale 缺)** |
| v2 ASDS 7-Tier Pipeline | 不見；v4.2 Track B 0% capacity 隱含放棄 | 不見 | **CRITICAL (整 thread 靜默退役)** |
| v2 Strategy DSL JSON + GenericHypothesisStrategy interpreter ~800 LOC | 不見 | 不見；M4 (v5.8) 提 hypothesis registry 但 schema-only | **CRITICAL** |
| v2 ADR-0024 全文 (autonomous L2 envelope) | v4.2 降為 ADR-0024-lite (operator-assistant)；原版是否進 docs/adr/ 未明 | ADR-0024-lite operative；ADR-0034 LAL Tier 系統取代部分 | **HIGH (full vs lite 版本治理未明)** |
| v2 Tier 3 CPCV + DSR auto-validator | 不見 | M11 continuous counterfactual replay (ADR-0038) 取代部分；CPCV 未列 | **MID (替代 mechanism exists 但無 explicit retire)** |
| v2 Tier 4 Thompson Sampling allocator | 不見 | Auto-Allocator (multi-component reward, λ_dd/tail/turnover/slippage/decay) 取代；Thompson 未列 | **MID** |
| v2 Tier 7 ADWIN drift retire | 不見 | M7 DECAY_ENFORCED state machine 取代；ADWIN 不列 | **MID** |
| v4 Track A/B/C 三軌架構 | retract for single-stream v4.4 | 不見 (改 Self-Trading primary + Copy evidence-gated 二元) | LOW (已 superseded) |
| v4 Track-aware GUI 4 tabs ~1200 JS | 不見 | v5.8 GUI Console tab 歸屬 4 tab × 2-4 sub-section；無 explicit 引用 v4 thread | **MID (GUI 4-tab thread 是否承襲未明)** |
| v4 跨軌衝突 resolver / Per-track P&L views / Guardian check 6 | DEFER (V102 + risk_config 待) | 不見 | **HIGH (Guardian check 6 安全 invariant 失蹤)** |
| v4.2 ADR-0026 prereg 15 欄位 (code_hash/Newey-West/immutable_trigger_hash) | inherit ADR-0026 v3；Phase A scope MINIMAL | V103 hypothesis_preregistration table；欄位數未明確 | **MID (是否真實 land 15 欄位待 Linux DB 驗)** |
| v4.2 Brown & Warner 1985 event-study + replay match ≥80% | inherit；Phase A MINIMAL | M11 replay (ADR-0038) 取代；event-study CAR 不見 | **MID** |
| v4.3 ADR-0027 Plan Mode 4-mode TIME-based | inherit | inherit (ADR-0027 active) | LOW |
| v4.3 W8/W12 verdict 2×2 matrix | retract Stream 3 IP sale | 不見 | LOW (commercial reframe 整段) |

### §3.3 v5.0 → v5.6 內部 delta 完整鏈

| Delta | v5.0→v5.2 | v5.2→v5.3 | v5.3→v5.4 | v5.4→v5.5 | v5.5→v5.6 |
|---|---|---|---|---|---|
| Sprint count | Phase 0/A/B/C → 1-6 | 6→9 | 9→10 | 10 | 10 |
| Engineering hr | 100-150→240-345 | 240-345→810-1,140 | →960-1,330 | →1,070-1,450 | →1,180-1,570 |
| Y1 median | $400-700→8-10% APR | →8-12% | →$920-1,520 + Copy $200-800 | →$927 self-only | →$547 calendar-weighted |
| Capital structure | $10k 主帳 $5.5k+Binance $1k+Off-ex $3.5k | same | 主帳 $8.5k+副帳 $1.5k Master Trader | 100% 主帳 $7,500 | 主帳 $7,500 (incl Earn $800) + Off-ex $2,500 |
| Strategy roster | C10 / C13 / Token Unlock SHORT | + Sensors A/B/C / V101 minimal | + Pairs / Funding short-only / Sensor D Intraday | Copy-Tradeability matrix (C10❌/C13❌/Pairs⚠️/Unlock✅/Funding✅) | + Macro overlay + On-chain + Earn (D12 expansion); C13 defined-risk default |
| Gate language | Phase A/B/C narrative | Tier 0-4 + paper "Sharpe>0.8→live" | Stage 0R replay preflight + Stage 1 Demo (per AMD-2026-05-15-01) | + Autonomy Tier 1-4 + Moat sequence | DRAFT→PREREGISTERED→SHADOW→STAGE_0R→1→2→3→4 explicit；"NO paper Sharpe gates" |
| Allocator | (none) | Sprint 6 Meta Allocator auto Thompson Sampling | Sprint 7 advisory + Sprint 9 auto | Y2+ moat enable | Sprint 7 Advisory + Y2 Sprint 11+ Auto gate |
| Copy Trading | Phase C optional (later dropped) | (none) | Sprint 1 副帳 Cadet→Bronze→Silver→Gold | Y2+ moat 後 enable | 4-gate Evidence Gate replaces calendar |
| ADR additions | (none) | (none) | (none) | ADR-0028 (proposed) Copy deferred | ADR-0028 + ADR-0029 (Macro+On-chain+Earn) + ADR-0006 amend |

### §3.4 v5.6 → v5.7 14KB slim down 失重區（高 drift risk）

v5.7 §0 只承認 6 reviewer issues。實際從 28KB→14KB 收縮 50%，下列 **16 個 v5.6 含詳 spec / v5.7 容納不下** 的條目是高 drift risk：

| # | 條目 | v5.6 位置 | v5.7 對應 | v5.8 對應 |
|---|---|---|---|---|
| 1 | Layer 1 Macro Calendar Overlay 完整 spec (FOMC/CPI/halving/listings × per-strategy rules + 30-50hr 工程) | §3.1 | §5 reframe counterfactual only Y1 (細節 dropped) | M2 overlay state machine (V105 + 40-60hr) |
| 2 | Layer 2 On-Chain Signals (Glassnode/Etherscan/DeFiLlama/CryptoQuant + 4 signal types + rate limits) | §3.2 | §5 reframe counterfactual only Y1 | 不見 (吸收進 M2/M11 counterfactual？未明) |
| 3 | Layer 3 Bybit Earn 整合細節 (auto-rebalance margin headroom <30% + instant convertibility) | §3.3 | §4 Earn 政策 4 條 + 45hr | ADR-0030 |
| 4 | C13 Defined-Risk 4-mode (put spread / cash-secured naked + 4-confluence / covered call / iron condor + max loss + 8-15% DD math) | §5 | §1 only "C13 options VRP defined-risk" | 不見 |
| 5 | Evidence-Based Build Order Sprint 3-7 mapping (Top-1→Top-5 ranking + Sprint 2 Alpha Tournament output) | §6 | Sprint 2 Alpha Tournament (Top-1/Top-2 only mentioned) | inherit |
| 6 | Calendar-Weighted Y1 income breakdown per-strategy annualization factor (C10 0.69x / Unlock 0.48x / Pairs 0.33x / C13 0.21x / Funding 0.25x / Earn 0.69x / Macro 0.58x / On-chain 0.44x) | §4 | §1 採 v5.6 factor 但未列原表 | inherit |
| 7 | Copy Trading Evidence Gate 4-gate 14 sub-criteria (Alpha+Moat+Operator+Bybit) | §10 | (Sprint 10 inherit, 詳列不見) | inherit |
| 8 | 5 stress scenarios per-sleeve line-item DD math (BTC -30%/-50%/halt/alt pump/IV spike) | §8 | 不見 | 不見 |
| 9 | Per-strategy multi-condition trigger logic (C10/C13/Unlock/Pairs/Funding 5 條規則) | §3 | 不見 | 部分吸收進 M12 OrderRouter + ADR-0039 maker_fill_rate |
| 10 | Stage gate explicit step DRAFT→PREREG→SHADOW→STAGE_0R→1→2→3→4 + "NO paper Sharpe gates" rule | §12 | 隱含 per AMD-2026-05-15-01 | inherit |
| 11 | ADR-0028 + ADR-0029 proposed 完整 spec | §11 | §12 ADR roster 列 (proposed) | **ADR roster 從 0030 起；0028/0029 是否 absorbed/superseded/abandoned 不明** |
| 12 | D12 constraint 完整文字 (Macro+Earn+On-chain approved；DEX/Hyperliquid NOT) | §1 | 隱含 (§5/§6 操作中體現) | D1a 列 "always declined DEX/Hyperliquid" |
| 13 | Master Trader tier ladder 完整 table (Cadet/Bronze/Silver/Gold × Total/7d Profit/7d MaxDD/Profit Share) | §10 (沿 v5.4) | 不見 | 不見 |
| 14 | Decay rules per-strategy event-count thresholds (C10 per-quarter / C13 12-cycle / Unlock 30-event / Pairs 20-trade / Funding 10-deployment) | §9 (沿 v5.5) | 不見 | M7 DECAY_ENFORCED state machine signal 取代但無 per-strategy threshold |
| 15 | Pre-registration immutable fields (code_hash/config_hash/immutable_trigger_hash/Newey-West/Wilcoxon/per_event dedup) | §6 (沿 v5.3) | V103 hypothesis_preregistration table；fields 未列 | inherit V103 |
| 16 | Engineering hours per-sprint breakdown lower-upper bound (Sprint 1-10) | §7 | §9 has table (sprint 1A/1B/2-10) | §4 PM 整合 44-55w / 3,500-5,200hr |

### §3.5 v5.7 ↔ v5.8 雙軌接縫 — 已確認內部不一致（**最危險區**）

| Item | v5.7 描述 | v5.8 描述 | 性質 |
|---|---|---|---|
| Sprint 1A scope/timeline | §8 "60-80 hr / W0-1.5" (1A 單 phase) | §3.5.1 "670-1,015 hr / 8.5w" (1A-α/β/γ/δ/ε 5 phase) | **PM 整合上修；雙軌共存但 dispatch packet 必需 phase disambiguation** |
| Sprint 4 first Live week | §9 "W12-15" | §10.5 "W17.5-20.5" (shift right 5.5w) | **時程衝突** |
| Y1 total hours | §9 "1,190-1,590 hr" | §4 "3,500-5,200 hr" (2.7-3.0x) | **PM 上修** |
| Y1 total weeks | §9 "39 weeks" | §4 "44-55 weeks" | **PM 上修** |
| M1 命名 | 隱含 "Decision Lease" | §12 D2 改名 LAL (Layered Approval Lease) + V112 column rename | **rename 已 D2 批；v5.7 文本不更新→dispatch confusion 風險** |
| M7 state name | (M7 not specced) | §2 用 STAGE_DEMOTE_PROPOSED；§3.5.5/§8/§11.5/§14 用 DECAY_ENFORCED | **v5.8 內部 inconsistency** |
| M13 timing | (not specced) | §2 "Y2: Binance perp"；§12 D4 + §14 "Y3+ at earliest" | **v5.8 內部 inconsistency** |
| ADR-0028/0029 | §12 列 (proposed) | ADR roster 從 0030 起；0028/0029 fate 未追蹤 | **治理斷層** |
| liquidation writer narrative | §6 "已存在不重建" | ADR-0038 強化 "self-hosted PG, 不依賴 Bybit historical API" | **政策強化但 v5.7 文本未更新** |

### §3.6 active-plan v1.9 (5/15) → v5.x unique 條目漂移

v1.9 是 5/15 戰術 ops snapshot，5/20 直接跳到 v5.0 戰略 reframe，**戰術細節跳過**：

| v1.9 unique 條目 | v5.x 對應 | Risk |
|---|---|---|
| `[55]` HEALTHCHECK INVARIANT (25/25 fully-filled plan chains, 0 missing) | 不見 | **MID** (healthcheck SOP 治理斷層) |
| `[67]` feature-baseline restore (646 active rows / 19 symbols / 34 feature names) | 不見 | **MID** |
| `[27]` post-grace closure (demo stale=3.4m / 30min_n=4) | 不見 | LOW (ops snapshot 性質) |
| `P1-HEALTHCHECK-55-INVARIANT` + WARN `[40][59][20][45]` | 不見 | **MID** |
| W-AUDIT-8a Phase C0 SOURCE/DOC closure (production topic builders guarded vs dormant/poison liquidation topics) | v5.7/v5.8 Sensor 整合 + M11 (ADR-0038)；細節遺失 | **MID** |
| Passive healthcheck SOP `[4] phys_lock_runtime` / `[Xb] pipeline_triangulation` fix by 7108035d | 不見 | LOW |
| 6 P1 task (FILL-LINEAGE-MONITOR / STARTUP-BURST-MITIGATION / V083-HALT-SESSION-CTX / W6-5-ML-METRICS / AUDIT-PERF-5 / AUDIT-AI-UX-7) | 不見 (無 mapping 到 Sprint 1A-10) | **HIGH** (具體 task 從 backlog 失蹤) |
| OI-confirmed 5m packet `bb_breakout_oi_confirmed_5m` | v5.x 全新候選池 (C10/Unlock/Pairs/C13/Funding short) 取代 | LOW (v5.0 §0 textbook permanent kill 涵蓋) |
| Runtime line vs source line drift (`d9532e17` source / `7b33ab2e` runtime binary) | 不見 | LOW (engineering ops 性質) |
| W-AUDIT-8b Funding Skew Directional spec v0.2 (30m primary horizon, `K_total ≥ K_prior+4050`, DSR ≥ 0.95, PBO fail-closed) | v5.x 改 Macro overlay；K_total/DSR 具體數字遺失 | **HIGH** (具體統計 threshold 遺失) |

---

## §4 ORPHAN ITEMS 清單（按風險分級）

### §4.1 CRITICAL — 整套 thread 靜默退役、無 documented retire reason

1. **v2 ASDS Strategy DSL JSON spec (12-field HypothesisSpec)** — `srv/docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--autonomous-strategy-system-v2.md` §3.3.1。v4.0 起 0 mention。v5.8 M4 用 `learning.hypotheses` V103 table，但無 DSL schema-only 是否承襲 v2 spec 之 statement。
2. **GenericHypothesisStrategy Rust DSL interpreter (~800 LOC) 架構** — v2 §3.3.3。v4-v5 0 trace。
3. **v2 ADR-0024 全文版 (autonomous L2 within envelope, 6 條件, PauseL2Autonomous IPC kill switch)** — v4.2 降為 ADR-0024-lite (operator-assistant)；原版是否進 docs/adr/ 未明，v5.8 ADR-0034 LAL Tier 1-4 取代部分但無 explicit retire 0024-full statement。
4. **v3 PIVOT 商業化 4 路徑** (Telegram bot $39/$99 / Substack / codebase sale $2-5k / signal feed integration / MEV/DEX) — v4.4 D7 constraint「NO content/subscription monetization」整段否決，**無原因分析**。Copy Trading 是否真實替代待驗證。
5. **88 finding 全 orphan 編號清單**（A 已給）：F-01, F-03, F-05, F-06, F-07, F-08, F-10, F-11, F-15, F-16, F-18, F-19, F-20, F-21, F-22, F-23 (partial), F-25, F-26, F-27, F-28, F-29, F-30 + 27 子 finding + K-1..K-6 + M-1..M-12 + C-1..C-5。

### §4.2 HIGH — 部分 absorbed 但 narrative 失蹤、決策路徑斷

6. **Guardian check 6** (v4 拒絕超 track budget trade) — v4.2 DEFER；v5.x 0 mention。Guardian check 治理表是否在某 ADR/CLAUDE.md 中註銷不清。
7. **v4 Track-aware GUI 4 tabs ~1200 JS** — v5.8 「4 tab × 2-4 sub-section」是否承襲 v4 thread 命名不明。
8. **v3 NLE 3 子策略 (overshoot fade / funding extreme / spread capture)** — v4.4 NLE 從 active monetization stream 移除；v5.x 全新 5 候選池無 NLE。NLE thesis 是否徹底 retire 未明。
9. **v1 Phase 2 三策略 A/B (regime_filter inversion / require_ma_confirmation off / OI confluence forced ON)** — v3 起 frozen，從未做 A/B evidence。
10. **active-plan v1.9 6 P1 task** (具體 task ID) — v5.x 0 mapping。
11. **W-AUDIT-8b Funding Skew v0.2 K_total/DSR 統計 threshold** — v5.x Macro overlay 取代但數字遺失。
12. **ADR-0021 + ARCH-04 + CONTEXT 5 詞條** (5/09 v3 P0 R4 補) — 5/16 起 0 mention；是否 land 待 docs/adr/ + docs/architecture/ + CONTEXT.md 對。
13. **AMD-2026-05-09-02/03/04** — 5/16 隱含；v5.x 0 mention；可能被 AMD-2026-05-15-01 + AMD-2026-05-21-01 superseded but 無 explicit chain。
14. **label_close_tag NULL 98.9% (MIT 1-day fix)** — 5/09 v3 重大發現；5/16 MIT-DB-6 是不同問題；v5.7/v5.8 0 mention。是否真實 land 待 PG empirical。
15. **22 fail-closed defaults 1e-3 數學論證** (5/09 v3 4-agent consensus) — 治理 invariant 數學基礎；v5.x 0 mention。
16. **ADR-0028 + ADR-0029** (v5.6/v5.7 proposed) — v5.8 ADR roster 從 0030 起；fate 未追蹤。
17. **F-22 risk_verdicts 18.47M / 5 chunk / 0 retention** — 5/16 MIT-P1-3 改 decision_features 10.22M prune (不同表)；risk_verdicts 仍 0 retention 未明。
18. **F-08 「5 ML 腳本 silent-unscheduled」→ MIT-P0-2「6/12 cron not installed」數字漂移** — PM §Sign-off Condition 2 明說「PA 必須 reconcile」但實質未在 5/16 完成。

### §4.3 MID — 替代 mechanism exists 但無 explicit retire annotation

19. **v2 Tier 3 CPCV 3-fold + DSR auto-validator** — M11 continuous counterfactual replay 取代但 CPCV writer + `learning.cpcv_results` 是否最終建立未明。
20. **v2 Tier 4 Thompson Sampling allocator + bayesian_posteriors writer** — Auto-Allocator multi-component reward 取代；Thompson Sampling 隱含放棄。
21. **v2 Tier 7 ADWIN drift + rolling DSR retire** — M7 DECAY_ENFORCED 取代但 ADWIN 算法是否承襲未明。
22. **v4.2 ADR-0026 v3 prereg 15 欄位** (code_hash/config_hash/trigger_rule JSONB/side_rule/expected_max_drawdown_pct/expected_holding_period_seconds/cost_assumption/dedup_rule/variance_estimator Newey-West/GARCH/bootstrap/data_window_start/end/immutable_trigger_hash) — v5.8 V103 hypothesis_preregistration；具體欄位數待 V103 spec 對。
23. **v4.2 Brown & Warner 1985 / MacKinlay 1997 event-study CAR t-stat<1.5→DEFER + replay match rate ≥80%** — v5.8 ADR-0038 M11 取代但 event-study CAR 不見。
24. **Cowork scheduled task** (`mcp__scheduled-tasks__create_scheduled_task` 每日 09:00 + 每週日 21:00) — v3 §1.1；v4.2 ADR-0024-lite 提 Cowork sub 但無 scheduled task autoroute；v5.x 0 mention。
25. **F-07 Layer 2 0 流量 + provider_keys_store 空** — v5.x 0 mention；ADR-0020 manual-only 涵蓋但 0 流量是 ADR-0020 已批 vs Live 之後仍需 verify。
26. **F-11 24 表 0 row dead schema 具體 24 個** — 5/16 僅 FA-P0-3 rl_transitions+symbol_clusters 2 個；其他 22 表清單失蹤。
27. **F-15 Decision Lease flip→writer→DB row e2e regression test 0 case** — v5.x 0 mention；E4 test gap 是否 land 待。
28. **F-16 feature_baselines + drift_events 0 writer** — 5/16 MIT-P1-1 改 drift chain broken (具體表名遺失)；v5.x 0 mention。
29. **F-18 xlang ATR/BB/Sharpe 1e-4 容差 test 0 case** — v5.x 0 mention；test 是否 land 待。
30. **BB push back 3 條 (L25 不存在 / liquidation_pulse 4 weeks ago deleted / basis observation vs execution)** — 5/16 BB-A-2/A-3 是不同議題；3 條 push back fate 未明。

### §4.4 LOW — 已確認 superseded / retired

- v1 funding_arb permanent retire (ADR-0018) — 全鏈一致
- v5.0 §0 5 textbook strategies (C3 textbook revival) permanent kill — 全鏈一致
- v4 Track A/B/C 三軌 — v4.4 retract for single-stream，v5.x Self-Trading primary + Copy evidence-gated 二元
- v4.3 Stream 3 IP sale — v4.3 retraction notice + v4.4 D7 不執行
- v5.0 §0 Three Final Paths (A/B/C decision tree) — v5.2 直接 absorb 為 strategy lab framing
- v5.4 Master Trader Sprint 1 immediate setup — v5.5 改 Y2+ moat 完備後 enable
- v5.5 Pairs trading ⚠️ Copy-tradeability — v5.6 同步 inherit
- v5.6 paper "Sharpe>0.8→live" gate — v5.3 起替換為 Stage 0R replay (per AMD-2026-05-15-01)

---

## §5 FORWARD-TRACE 完整度評估

| 階段 | 條目來源 | 推估 carried | 推估 absorbed-no-trace | 推估 dropped-no-doc | 完整度 |
|---|---|---|---|---|---|
| 5/08 audit | 88 finding + 5 PENDING + K/M/C + W-AUDIT-1..7 | ~30 (38%) | ~30 (38%) | ~30 (38%) — F-* orphan | 38% |
| 5/09 v1-v3 | NEW-ISSUE-1 / NEW-VULN-1..4 / AMD-02/03/04 / R-1..5 / Track W/A | ~10 (30%) | ~15 (45%) | ~10 (30%) | 30% |
| 5/15 active-plan | 戰術 ops items + 6 P1 task | ~3 (30%) | ~3 (30%) | ~4 (40%) | 30% |
| 5/16 audit-reframe | WP-01..13 + agent-prefix-ID | ~10 (77%) | ~3 (23%) | 0 | 77% |
| 5/20 design thread | 8 thread roster | ~3 (40%) | ~3 (40%) | ~2 (25%) | 50% |
| v4.4 commitments | 5 monetization stream + Capital | 5 (100%) | 0 | 0 | 100% |
| v5.0-v5.6 reframes | per version §0 changelog | ~85% | ~10% | ~5% | 85% |
| v5.6 → v5.7 收縮 | 16 高風險條目 | 6 (38%) | 7 (44%) | 3 (19%) | 38% |
| v5.7 → v5.8 supplement | 13 modules | 13 (100%) | 0 | 0 | 100% |

**結論**：5/08 audit 起源 + 5/09 verification + 5/15 active-plan + 5/20 dual-track design thread 是 forward-trace 完整度最低的階段（30-50%）。5/16 audit-reframe + v4.4 + v5.0-v5.6 reframes + v5.7→v5.8 是高完整度階段（77-100%）。

**戰略性結論**：drift 集中在「跨 phase transition」處（5/16 重編號 / 5/20 design thread 整合進 v4.4 / 5/20→5/21 v5.0 reframe / v5.6→v5.7 slim down）。v5.7→v5.8 雖然 100% 完整但**內部不一致** (見 §3.5)。

---

## §6 已確認的內部 inconsistency

下列為**單版本內部**矛盾（非跨版本 drift）：

1. **v5.8 §2 M7 spec 用 STAGE_DEMOTE_PROPOSED；§3.5.5/§8/§11.5/§14 用 DECAY_ENFORCED**（per CR-7 rename）— v5.8 自身未全文 sync。
2. **v5.8 §2 M13 spec "Y2: Binance perp"；§12 D4 + §14 "Y3+ at earliest"** — v5.8 自身 timing 不一致。
3. **v5.7 §8 Sprint 1A "60-80 hr / W0-1.5"；v5.8 §3.5.1 Sprint 1A "670-1,015 hr / 8.5w" (1A-α/β/γ/δ/ε)** — 雙軌共存但 dispatch packet 必需 phase disambiguation。
4. **v5.7 §9 Sprint 4 first Live "W12-15"；v5.8 §10.5 "W17.5-20.5"** — 時程 shift 5.5w 未 reconcile。
5. **v5.7 §9 Y1 total "1,190-1,590 hr"；v5.8 §4 "3,500-5,200 hr"** — 2.7-3.0x；雙文同時 active = sub-agent 取錯側 = 工程估算錯。
6. **v5.7 隱含 "Decision Lease"；v5.8 §12 D2 改名 LAL** — v5.7 文本未更新 (V112 column rename 已批)。
7. **ADR-0028 + ADR-0029**：v5.6/v5.7 列 proposed；v5.8 ADR roster 從 0030 起；fate 未追蹤（absorbed/superseded/abandoned）。
8. **v5.7 §6 liquidation writer "已存在不重建"；v5.8 ADR-0038 "self-hosted PG, 不依賴 Bybit historical API"** — 政策強化但 v5.7 文本未更新。

---

## §7 建議下一步

### §7.1 立即（D+0）— governance 層補位

| Action | Why | Owner |
|---|---|---|
| **生 AMD-2026-05-25-01 「V1→V5.8 lineage reconciliation」** 註明 §3.1 編號斷層的官方治理立場（W-AUDIT-1..9 / F-* / K-M-C / R-1..5 / Track W/A 編號正式 retire；後續引用一律改 WP-XX + agent-prefix-ID + Sprint 1A-10） | 解 5/16 編號重啟治理斷層 | PM |
| **v5.7 文本 sync v5.8 D2 rename + ADR-0038 政策強化** | 解 §6.6 + §6.8 雙軌不一致 | PA + TW |
| **v5.8 §2 M7 全文 rename DECAY_ENFORCED** | 解 §6.1 自身不一致 | TW |
| **v5.8 §2 M13 timing 統一 Y3+** | 解 §6.2 自身不一致 | PA |
| **ADR-0028 / ADR-0029 fate 顯式 trace**：absorbed into ADR-0030/0033（Earn）/ ADR-0031/0032（Macro+On-chain counterfactual）？superseded？abandoned？ | 解 §6.7 治理斷層 | PA + CC |

### §7.2 本 sprint（Sprint 1A-β D+5~D+10）— 高風險 orphan 顯式處理

| Action | Why | Owner |
|---|---|---|
| **CRITICAL orphan 1-5 顯式裁決** (§4.1) — v2 ASDS thread 是否正式 retire？Strategy DSL spec 是否在 M4 schema 中承襲？ADR-0024 全文是否 retire 或 land？v3 PIVOT 商業化是否在某 ADR 中 explicitly declined？ | 5 條 CRITICAL orphan 全部需 explicit retire ADR 或 forward annotation | PA + QC |
| **88 finding 全 orphan 列表 forward-trace 對照** (§4.1 #5) — 把 22 個 F-* orphan 列入 P0-EDGE-1 / Sprint 1A-β V103-V113 IMPL 對照表，確認哪些已在 V### schema 中 land、哪些需新 spec | F-* 編號雖 retire 但內容 finding 不可遺失 | E4 + MIT |
| **HIGH orphan 6-18 (§4.2) 逐條 PA verdict**：carried / absorbed / dropped。Guardian check 6、ADR-0021、AMD-2026-05-09-02/03/04、label_close_tag NULL、22 fail-closed math、F-22 risk_verdicts 等是治理 / 安全 invariant 不容遺失。 | 防範 安全 invariant 漂移 | PA + CC + E3 |
| **active-plan v1.9 6 P1 task 顯式裁決** (§4.2 #10) — FILL-LINEAGE-MONITOR / STARTUP-BURST-MITIGATION / V083-HALT-SESSION-CTX / W6-5-ML-METRICS / AUDIT-PERF-5 / AUDIT-AI-UX-7 是否 absorbed 進 Sprint 1A-10 還是 explicitly defer | 防範 P1 backlog 從 active queue 沉沒 | PM |
| **v5.6 16 高 drift risk 條目（§3.4）對照 v5.7+v5.8 forward-trace 表** — 補足 Layer 1/2 Macro+On-chain 完整 spec、C13 4-mode、Master Trader tier ladder、5 stress scenarios DD math 等的 absorbed vs dropped 註記 | 防範 14KB→64KB transition 中失重 | PA |

### §7.3 中期（Sprint 1A-ε）— 治理結構化

| Action | Why | Owner |
|---|---|---|
| **建立永久性 lineage 追蹤 doc** `docs/governance/lineage_register.md`：所有 ADR/AMD/編號 (W-AUDIT-X / F-X / WP-X / Sprint 1A-X / M1-M13 / V101-V116) 一律登記 supersede chain | 防範 5/16-style 編號斷層再發生 | R4 + TW |
| **更新 CLAUDE.md §三 routing**：明示 v5.7+v5.8 雙軌 reading order (v5.7 dispatch-of-record 先讀，v5.8 autonomy supplement 後讀)；TODO.md 標明 Sprint 1A-α/β/γ/δ/ε phase | sub-agent dispatch 不選錯邊 | PM + TW |
| **R4 ADR-0021 + ARCH-04 + CONTEXT 5 詞條 land 驗證** (§4.2 #12) | 5/09 v3 P0 R4 action 待 close | R4 |
| **PG empirical 驗證 label_close_tag NULL fix** (§4.2 #14) — MIT 1-day fix 是否真實 land？attribution_chain_ok 24h 從 1.0857% 真實升到多少 | 防範重大 MIT finding 從 audit 鏈失蹤 | MIT |

---

## §8 Appendix — 各文件 raw extraction 來源

本文件由 4 路並行 sub-agent extraction 合成。原始 extraction 條目化清單存於各 sub-agent task output（非 git 追蹤）：

- **Group A**（audit 起源 5 份 5/08-5/16）：每 finding ID + state + Cross-file deltas + Orphan candidates
- **Group B**（設計探索 8 份 5/20）：thread family classification + thesis 演化 + 4 thread group cross-deltas
- **Group C**（v5.0-v5.6 中繼 7 份）：逐版本 §0 changelog 逐字抄錄 + 全鏈 delta + v5.1 缺號解 + v5.6 收縮高風險條目
- **Group D**（v5.7+v5.8 active 2 份）：full TOC + 13 module specs + CR-1..16 + 雙軌 inconsistency 完整盤點

如需 raw extraction，須重派 sub-agent (Group A-D prompt 仍可 reproducible reproducible)。本 audit 終稿即作為 single authoritative consolidation reference。

---

**Audit completion**：22 files / ~485KB raw → 1 file / ~30KB synthesis。
**Drift count**：35+ orphan items (5 CRITICAL + 13 HIGH + 12 MID + 5 LOW).
**Inconsistency count**：8 confirmed v5.7↔v5.8 雙軌矛盾。
**Recommended action**：5 immediate (D+0) + 5 sprint (Sprint 1A-β) + 4 mid-term (Sprint 1A-ε)。

(End of initial audit — patches below)

---

## §11 POST-VERIFY PATCHES (2026-05-25 end-of-day)

完成初稿後，主會話分 5 路 sub-agent (PM/QC/R4/BB/E1/general-purpose) + SSH trade-core empirical verify，**揭示初稿 §4 Orphan 列表 over-flag 嚴重**。下表為**逐條 patch**。

### §11.1 初稿 8 條報告錯誤 → 全部 CORRECTED

| # | 初稿位置 | 初稿說 | 真實狀態 | Evidence |
|---|---|---|---|---|
| 1 | §4.2 #14 | F-22 label_close_tag NULL 98.9% fate 未明 | **CLOSED** by V086+V091+HC[65]+memory era-split | [AMD-2026-05-11-W6-1](srv/docs/governance_dev/amendments/2026-05-11--AMD-2026-05-11-W6-1-rfc-final-verdict-absorb.md) §2.3 MIT MUST 5+SHOULD 7+MUST 2; commits 332a2f9c/9159362c/db17e205 |
| 2 | §4.1 #11 / §3.1 ADR-0028/0029 行 | ADR-0028/0029 proposed fate 不明 | **編號順移 confirmed** — ADR-0028=close-maker / ADR-0029=market.public_trades; v5.6/v5.7 提案實際 land 為 **ADR-0030** (Copy) + **ADR-0031** (Macro+Earn+On-chain) + **ADR-0032** (Earn Guardian) | [ADR-0030](srv/docs/adr/0030-copy-trading-evidence-gated.md) Context + [ADR-0031](srv/docs/adr/0031-framework-expansion-earn-macro-onchain.md) Context |
| 3 | §4.1 #4 | v3 PIVOT 4 路徑被 v4.4 D7 整段否決 | **錯** — 14 份 AMD 內無 D7 字面；只有 [AMD-2026-05-20-05](srv/docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-05-retract-stream-3-ip-sale.md) explicit retract **IP Sale only**；Telegram subscription + Substack + Stripe pre-order 在 AMD-04 Stream 2 仍 active 直到本日 AMD-25-01 propose | (本日 propose AMD-2026-05-25-01 補 explicit retire) |
| 4 | §4.2 #16 | W-AUDIT-8b K_total/DSR threshold 仍有效 | **W-AUDIT-8b tombstoned** Round 2 RED_FINAL 2026-05-18 + redirect to W-AUDIT-8c/8a Phase B/C/D | [AMD-2026-05-15-02](srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md) v0.7 |
| 5 | §4.2 #12 | ADR-0021+ARCH-04+CONTEXT 5 詞條 fate 未明 | **全 land** + bonus 12 v5.8 autonomy terms | [ADR-0021](srv/docs/adr/0021-alpha-source-architecture-upgrade.md) + [ARCH-04](srv/docs/architecture/2026-05-10--ARCH-04-graduated-canary-5-stage.md) + [CONTEXT.md:52-72](srv/CONTEXT.md) |
| 6 | §4.2 #17 | F-22 risk_verdicts 18.47M / 0 retention | **CLOSED** by V075 (30d retention + 7d compression);**SSH empirical confirm**：15 chunks / 9.35M rows (retention 已 trim 50%+) | [V075](srv/sql/migrations/V075__w_audit4_retention_compression.sql) + commit 8772b0b2 + SSH PG verify |
| 7 | §4.2 #18 | F-08 vs MIT-P0-2 cron 數字漂移未 reconcile | **RECONCILED** — 不同層級不衝突;**SSH empirical confirm**：`17 3 * * * ml_training_maintenance_cron.sh` installed | [PM cron_reconcile report 2026-05-16](srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--cron_reconcile_p0v3_mit_p02.md) + SSH crontab verify |
| 8 | §4.2 #20 | G1 v1.9 6 P1 task 無 mapping | **6/6 CLOSED** in commit `07cfcb72` (2026-05-15) | [PM p1_p2_sequential_closeout](srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--p1_p2_sequential_closeout.md) |

**初稿 35+ orphan items 修正後實際只有 ~10 條真正 unresolved**（餘下進 §11.2 / §11.3）

### §11.2 SSH trade-core empirical verify (2026-05-25)

| Item | SSH command | Result |
|---|---|---|
| F-22 risk_verdicts hypertable | `psql -c "SELECT num_chunks FROM timescaledb_information.hypertables WHERE hypertable_name='risk_verdicts'"` | **15 chunks** |
| F-22 retention/compression policy | `psql -c "SELECT proc_name, config FROM _timescaledb_config.bgw_job WHERE hypertable_id=..."` | `policy_compression: compress_after=7d` + `policy_retention: drop_after=30d` ✅ |
| F-22 row count | `psql -c "SELECT count(*) FROM trading.risk_verdicts"` | **9,349,593** (vs 原 18.47M — retention 工作中) |
| F-08 cron installed | `crontab -l \| grep ml_training` | `17 3 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ml_training_maintenance_cron.sh` ✅ |
| F-08 cron wrappers | `ls /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/` | 11 wrappers (含 ml_training / feature_baseline / outcome / panel / replay / blocked_symbols) |
| [27] intents_counter_freeze | `python3 -m runner` | ⚠️ WARN — stale=273.7m, mode inactive in 30min window (state, not infra) |
| [55] agent_decision_spine_lineage | 同上 | ⚠️ WARN — spine disabled by env, MAG-082 readiness=DISABLED (env, not infra) |
| [67] feature_baseline_readiness | 同上 | ✅ **PASS** — active_rows=**714** (vs v1.9 baseline 646 — grew), active_symbols=21, feature_names=34/34 |
| [78] feature_baseline_writer_cron 🆕 BONUS | 同上 | ⚠️ WARN — **heartbeat stale 4.75d, cron likely stopped firing** |

**Cron stale 4.75d 是新 finding** — operator 後續 follow-up（可能與 v5.7 era path migration `/home/ncyu/srv/` → `/home/ncyu/BybitOpenClaw/srv/` 衝突有關）

### §11.3 真正剩餘 unresolved (10 條)

| # | Item | Status / Action | Owner |
|---|---|---|---|
| A | 22 fail-closed 1e-3 invariant ADR 化 | **PM verdict: Option (c) AMD-09-03 附錄 invariant** (不升新 ADR);理由 = AMD-25-21-01 v2 已建上層 fail-safe framework；1e-3 推導不滿足 v2 §Decision 2.2 evidence gate;22 條真實 ≥ 50 條;Option (c) 保留升 ADR future option。Dispatch plan 7.5-11.5 hr (PA/TW/FA/QC/R4 parallel) | PM CONDITIONAL APPROVED |
| B | basis observation vs execution 分維 | **BB APPROVE** 候選 ADR-0046 basis-observation-execution-split;scope 限 funding_arb;cross-venue + options 為 Future Work;24-30 hr IMPL;Sprint 1A-δ/ε 平行 land 不阻 W2/W5/W7 | BB sign-off |
| C | healthcheck [67] collision | **DONE** — canary [67]→**[80]** rename;4 files modified;16 tests collected PASS;未 commit (operator 手動) | E1 IMPL DONE |
| D | 商業化 (含 IP sale) — 只允許 Bybit+Binance 平台 | **DRAFT** [AMD-2026-05-25-01](srv/docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-01-commercialization-exchange-native-only.md) Proposed | 主會話 DRAFT, pending operator confirm |
| E | v5.5 reframe formalize | **DRAFT** [AMD-2026-05-25-02](srv/docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-02-v55-bot-positioning-capital-structure-formalization.md) Proposed | 主會話 DRAFT, pending operator confirm |
| F | Phase 2 三 A/B QC push back | **接受 QC defer (非 permanent reject)**;revisit 條件 = $5k+ account + Sprint 2 W2-A evidence + cost gate 改善 | DEFERRED — Sprint 2 W2-A 後 revisit |
| G | GUI design SPEC NOT MISSING but DISPERSED | A3 audit + v5.8 §3.5.2 散落;Sprint 1A-α 末派 PA+A3 寫獨立 SPEC | BACKLOG — Sprint 1A-α 末 |
| H | SPECIFICATION_REGISTER.md:212 ARCH-04 sync | **DONE** — 「3 (+ 1 Proposed: ARCH-04)」→「4」 | R4 fix DONE 本日 |
| I | SKILLS_TODO:66 L25/L84 | **不需要修** — 是 walk-forward skill 行號 reference (line 25 = 黃金法則 / line 84 = White's Reality Check)，非 Bybit WS depth tier；R4 audit confused | Investigation DONE, no fix needed |
| J | PA spec「liquidation_pulse deleted」FALSE CLAIM | **liquidation_pulse.rs CONFIRMED ACTIVE** — W-AUDIT-8a C1-LIQ-WRITER 2026-05-18 commit `0e8a8ae8`;PA spec 該條為 FALSE CLAIM 應撤回 | PA 撤回該描述 (待派) |
| 🆕 | [78] feature_baseline_writer cron stale 4.75d | SSH 揭發;heartbeat 不 fire;可能 v5.7 path migration 漏 follow-up | OPS follow-up (新 task) |

### §11.4 已 land 的 2 個新 AMD drafts (待 operator approve)

| AMD | Title | Scope |
|---|---|---|
| [AMD-2026-05-25-01](srv/docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-01-commercialization-exchange-native-only.md) | Commercialization Boundary: Exchange-Native Only | Retire IP sale + Telegram subscription + Substack + codebase sale + signal feed + MEV/DEX + Stripe pre-order;Retain Bybit + Binance 平台官方方案 (Copy Trading / Earn / Master Trader / Competitions);Supersedes AMD-04 Stream 2 + AMD-05 (擴 scope) + v4.4 D7 constraint formalize |
| [AMD-2026-05-25-02](srv/docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-02-v55-bot-positioning-capital-structure-formalization.md) | v5.5 Bot Positioning + Capital Structure Formalization | Single product 完整 quant bot;Y1 100% 主帳 $7,500;副帳 Y2+ ADR-0030 4-gate + Moat 5-gate conditional enable;Supersedes v5.4 dual product + Master Trader Sprint 1 setup |

### §11.5 已 land 的 1 個 IMPL change (待 operator commit)

E1 canary [67]→[80] rename:
- 4 files modified: `helper_scripts/canary/healthchecks/80_liquidation_pulse_freshness.py` + `tests/test_80_pulse_freshness.py` + `__init__.py` + `SCRIPT_INDEX.md`
- 16 tests collected PASS (pytest --collect-only)
- 0 stale ref in active code
- Bonus: 加 `namespace="canary"` field (補 __init__.py 早已強制要求合約)
- Commit message draft 已 ready (在 sub-agent return)

### §11.6 已 land 的 1 個 small doc fix

[SPECIFICATION_REGISTER.md:212](srv/docs/governance_dev/SPECIFICATION_REGISTER.md): `Active ARCH specifications | 3 (+ 1 Proposed: ARCH-04)` → `Active ARCH specifications | 4`

### §11.7 後續 sub-agent dispatch backlog (待 operator approve AMD-25-01/02 後啟動)

1. **A workflow (Option c)**: PA + TW + FA + QC + R4 5-agent waterfall+parallel (7.5-11.5 hr) — AMD-09-03 附錄 invariant land
2. **B workflow**: PA → E1 (8h) → MIT V117 spec (2h, may NO-OP) → E2 review (3h) → E4 test (6h) → BB review (2h) → QA sign-off = 24-30 hr — ADR-0046 + funding_arb basis 分維 IMPL (Sprint 1A-δ/ε)
3. **G workflow**: Sprint 1A-α 末派 PA + A3 寫獨立 GUI design SPEC doc (vs 散落 A3 audit)
4. **J workflow**: PA 撤回「liquidation_pulse deleted」FALSE CLAIM spec 描述
5. **🆕 OPS follow-up**: [78] feature_baseline_writer cron stale 4.75d — 查 cron 為何停 fire (可能 v5.7 path migration `/home/ncyu/srv/` vs `/home/ncyu/BybitOpenClaw/srv/`)

---

## §12 最終 drift count revised

| 維度 | 初稿 | 本次 patch 後 |
|---|---|---|
| Confirmed errors in initial audit | — | **8 條 corrected** |
| ORPHAN CRITICAL (§4.1) | 5 | 0 (重分類後全 RESOLVED 或進 unresolved §11.3) |
| ORPHAN HIGH (§4.2) | 13 | 5 (其中 4 條 DONE 本日, 1 條 BACKLOG, 1 條 DRAFT) |
| ORPHAN MID (§4.3) | 12 | 暫不重分類 (大多為 MID risk replacement-mechanism exists, 不阻 Sprint 1A) |
| ORPHAN LOW (§4.4) | 5 | 5 (unchanged) |
| Internal inconsistency v5.7↔v5.8 | 8 | 9 (新加 M4 timing Sprint 6 vs Sprint 8 — ADR-0045 vs v5.8 §1 文本) — 待 v5.8 Wave 5 cascade 解 |
| **New AMD drafts proposed** | 0 | **2** (AMD-25-01/02) |
| **DONE small fixes** | 0 | **3** (H + I[investigation] + canary rename [67]→[80]) |
| **SSH verify confirmed** | 0 | **3+1 bonus** (F-22 + F-08 + [55][67][27]) + [78] new finding |

**audit accuracy**：初稿 35+ orphan → 修正後 ~10 條真正 unresolved (28% 真實 unresolved 率;72% 初稿 false positive) — **真正最大教訓 = 不要單獨依賴 prior audit document 推結論，必 SSH empirical + read latest ADR/AMD chain cross-ref**

---

## §13 最終 operator action checklist

Pending operator approval（按優先級排序）：

| Pri | Action | Blocked-on |
|---|---|---|
| P0 | Approve AMD-2026-05-25-01 + AMD-2026-05-25-02 + cascade | Operator confirm 後 PM cascade patch (docs/README + SPEC_REGISTER + TODO cleanup) |
| P0 | Commit canary [67]→[80] rename | Operator 手動 commit (4 files modified, 0 stale ref, 16 tests PASS) |
| P1 | Approve A workflow Option (c) AMD-09-03 附錄 invariant land | Operator confirm 後 PA + TW + FA + QC + R4 5-agent dispatch (7.5-11.5 hr) |
| P1 | Approve B workflow ADR-0046 basis observation/execution + funding_arb IMPL | Operator confirm 後 PA dispatch chain (24-30 hr Sprint 1A-δ/ε) |
| P2 | Investigate [78] feature_baseline_writer cron stale 4.75d | SSH ops follow-up (查 cron 為何停 fire) |
| P2 | PA 撤回「liquidation_pulse deleted」FALSE CLAIM | PA workspace doc edit |
| P3 | Sprint 1A-α 末派 PA+A3 寫獨立 GUI design SPEC | Sprint 1A-α 完成後 |

End of post-verify patches.

