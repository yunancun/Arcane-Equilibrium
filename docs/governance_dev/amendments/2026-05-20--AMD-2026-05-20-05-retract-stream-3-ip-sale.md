# Amendment AMD-2026-05-20-05 — Retract Stream 3 IP Sale Prep (Operator Reality Check)

**對應 spec**: `srv/2026-05-20--commercial-evidence-sprint-v4.3.md` (in-place retraction notice added)
**修訂對象**: AMD-2026-05-20-04 §1 三 stream 架構 + v4.3 §3 Stream 3 IP Sale Prep + v4.3 §5 W8/W12 verdict matrix + v4.3 §12 EV 算式
**日期**: 2026-05-20
**狀態**: Accepted

---

## 1. Executive Decision

Operator 2026-05-20 confirms：**IP sale 不現實、不可能**。

v4.3 Stream 3 IP Sale Prep（README cleanup / architecture diagram / demo
video / private landing page / quiet outreach 5-10 個 networks）**整段
retract**。

Capacity 10% Stream 3 reallocate 給 Stream 1（Track A Technical Edge），
Stream 1 from 60% → **70%**。Stream 2 monetization demand test 維持 30%。

---

## 2. 為什麼接受 retraction

我之前在 v4.3 §3 push back reviewer 把 IP sale 列為 W12+ fallback，主張
W1 漸進 prep，理由：
- IP sale prep 工程量低（~16-24 hr 跨 8 週）
- ROI/hr 估 $62-280 較其他高
- 不和 Stream 1 / 2 衝突資源

**Operator 反駁的隱含理由**（我接受）：
- 我估的 IP value $5-15k 是 wishful thinking 沒有 buyer pool 證據
- Crypto quant community 多數已有 self-built infrastructure，不買 framework
- Outreach 5-10 networks 在 8 週內 closing deal 機率遠低於 30%
- 即使有人問價，cleanup + sale process 真實耗時 20-40 hr（不是 16-24）
- 我未驗證 buyer pool exists 就估 EV — bias confirmation 自我說服
- Operator 對 crypto quant 商業圈瞭解更深

**Self-critique**：v4.3 §3 IP sale prep 是我 v4.3 修正包裡**唯一 reviewer 沒
提的我自己加的東西**。「自己加的東西」最容易帶 confirmation bias。Operator
catch 對。寫進 memory：「自己加新項目時 EV 估算強制 cold reality check」。

---

## 3. v4.3 修訂內容

### 3.1 Stream 改 2 條

| Stream | v4.3 原 capacity | v4.3 retract 後 |
|---|---:|---:|
| 1. Technical Edge | 60% | **70%** |
| 2. Monetization Demand Test | 30% | 30% unchanged |
| ~~3. IP Sale Prep~~ | ~~10%~~ | **REMOVED** |

Stream 1 +10% 給予：更多 LCS event-study 統計分析時間 / NLE listing watcher
shadow run 監控 / Tier 0/1 collector 性能調優 / V101 V102 migration QA。

### 3.2 W8 Joint Verdict 簡化 2×2×2 → 2×2

```
W8 verdict matrix (revised post-retraction):

Stream 1 PASS (Sharpe > 1.0) + Stream 2 PASS (L4 ≥ 20)  → SCALE
Stream 1 PASS                + Stream 2 FAIL (L4 < 5)   → OBSERVE Mode（demo 持續，等 live gates 或 demand maturity）
Stream 1 FAIL (Sharpe < 0.5) + Stream 2 PASS            → PIVOT to Signal Service（Stream 1 KILL）
Stream 1 FAIL                + Stream 2 FAIL            → HARD KILL trigger W12
```

5 paths → 4 paths（drop "All-in IP sale" path）。

### 3.3 W12 Hard Kill 簡化 3-condition → 2-condition AND

```
W12 hard kill triggers (revised):
  - Stream 1 12-week demo cum net edge < 0 bps
  - Stream 2 L4 paid pre-orders < 10 over 8 weeks
  - (removed) ~~Stream 3 0 buyer inquiry over 12 weeks~~

→ KILL self-built trading mainline + monetization stream
→ Operator 重配時間：
  - $5760/年 burn 轉投資 index fund / 自我 reskilling / paid work
  - Codebase 變 sunk asset（不嘗試 sale；維持作 portfolio / 學習紀錄即可）
```

### 3.4 EV 算式修訂

| 原 v4.3 §12 | 修訂 |
|---|---|
| SCALE 5%: $25-100 | unchanged 5%: $25-100 |
| OBSERVE 25%: $13-50 | unchanged 25%: $13-50 |
| PIVOT 10%: $200-1200 | unchanged 10%: $200-1200 |
| ~~IP sale 5%: $250-750~~ | **REMOVED** |
| HARD KILL 55%: $0 | **60%** (吸收 IP sale 5% 機率): $0 |
| **Total EV**: $488-2100 | **$238-1350** |

Net (EV - marginal $400-500 burn): **-$262 to +$850** annual。仍 acceptable
（最壞 8-12 週 + small marginal loss；中位數仍正回報），但不如 v4.3 預估
樂觀。誠實版本。

### 3.5 v4.3 §3 / §6 / §7 Sprint Plan retract 對應段落

| v4.3 section | retraction |
|---|---|
| §3 Stream 3 IP Sale Prep（全段）| RETRACTED；保留段落作 audit trail，加 strikethrough 或 inline retract note |
| §7 Sprint plan Stream 3 columns | RETRACTED；改為 "—" |
| §5.1 W8 matrix 三軸 → 兩軸 | 用 §3.2 above 替代 |
| §5.2 W12 三 AND → 兩 AND | 用 §3.3 above 替代 |
| §12 EV 算式 | 用 §3.4 above 替代 |

PA dispatch 不執行 Stream 3 任何 deliverable。

---

## 4. 不變的部分

以下 unchanged from AMD-04 / v4.3：

- Stream 1 thesis（LCS isolated cluster + book recovery + maker；NLE shadow watcher）
- Stream 2 完整 spec（landing page + Telegram + Substack + Stripe + ToS + L1-L5 demand pyramid）
- ADR-0027 Plan Mode TIME-based budgeting
- Phase 0 V097/V098 catch-up
- V101 11+1 表 + V102 NOT NULL + indexes + views
- ADR-0026 v3 event-study + pre-registration（replay match defer Phase 1.5）
- ADR-0024-lite Cowork subscription operator-assistant
- Subscription = sunk cost framing
- v56 P0 hard precondition

---

## 5. Active TODO 條目修訂

### 5.1 取消

```
STREAM-3-IP-SALE-PREP             ⛔ RETRACTED 2026-05-20  per AMD-05
  - 全部 deliverables 不執行
  - 不寫 README cleanup / diagram / demo video / landing page / outreach
  - 不分配 operator hours
```

### 5.2 修訂

```
STREAM-1-TECHNICAL-EDGE-SPRINT    🔵 capacity 60% → 70%   [PA→E1+E1a]
  - +10% capacity for: V101 V102 QA, LCS event-study深度分析,
    Tier 0/1 collector 性能, NLE shadow monitoring

W8-JOINT-VERDICT-RUNBOOK          ⏳ PENDING               [PA]
  - 2 streams verdict data (technical × demand)
  - 2×2 matrix 套用 (4 paths)
  - Plan Mode 切換 per ADR-0027
```

---

## 6. governance 不變式

- 16 條根原則 unchanged
- AMD-2026-05-15-01 / -02 / ADR-0011 / ADR-0018 / ADR-0020 / ADR-0024-lite /
  ADR-0025 v3 / ADR-0026 v3 / ADR-0027 全部 unchanged
- v4.3 §0 reframe 為 commercial evidence sprint unchanged
- W8 + W12 economic gate 概念 unchanged（只是 axes 從 3 → 2）

---

## 7. Lesson Learned 寫進 memory

1. 「自己加新項目時 EV 估算強制 cold reality check」—— Stream 3 IP sale prep
   是我自己加的，沒 operator/reviewer 主動提；最容易 bias confirmation。
2. ROI/hr 看起來高但**忽略 buyer pool 不存在的根本前提**，是常見幻覺。
3. Operator 對 community 商業現實判斷 > Claude 對 EV 數學推導。
4. 寫 spec 時對「我自己想到的好點子」要加 50% bias discount。

---

## 8. References

- v4.3 spec: `srv/2026-05-20--commercial-evidence-sprint-v4.3.md`（in-place retraction notice at top）
- AMD-04: `2026-05-20--AMD-2026-05-20-04-v4.3-commercial-evidence-sprint.md`（部分 supersede）
- Operator decision 2026-05-20: IP sale 不現實、不可能（明確口述）

---

**END AMD-2026-05-20-05**
