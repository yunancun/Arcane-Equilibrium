# Multi-Session Race Protocol SOP — Operator Approval

**Date**: 2026-05-16
**Operator**: ncyu (cloud@ncyu.me)
**Authority**: PM 2026-05-16 sign-off + operator option (A) APPROVE + enforce
**Ticket**: `P0-3 Race Protocol SOP Phase 2 Rollout`

---

## OPERATOR ACK

> **Accept P0-GOV-MULTI-SESSION-RACE-SOP-1 Phase 2 rollout — E2 review §5 5 條 race check + PM dispatch §6 template 4 條 + lessons.md Phase 2 entry — 立即 enforce 2026-05-16；2-week observation 至 2026-05-30；2026-05-30 review fine-tune 必要時 revise 後再 enforce。**

**Selected option**: **(A) APPROVE + enforce**（PA Round 4 設計 + PM PM-sign-off 推薦）

---

## 拍板理由

### 1. Phase 1 已 land + 4 events 完整 root cause + remediation 證據鏈

- SOP 8 條 spec：`srv/docs/governance_dev/2026-05-16--P0-GOV-MULTI-SESSION-RACE-SOP-1.md`
- Phase 1 4 events lessons.md `Multi-session race incident` 區：
  - Event 1: 2026-05-15 23:35-23:48 UTC BB-MF-3 phantom sign-off + comment contamination
  - Event 2: 2026-05-15 23:48-23:55 UTC 主會話 stash 誤殺 BB-MF-3 + Wave 2 IMPL
  - Event 3: 2026-05-16 00:53 UTC E1 leftover P1 sub-agent vs v35 rebuild race（safely land）
  - Event 4: 2026-05-16 01:00 UTC E1 WP-13 leftover P1 retry quota fail

### 2. Phase 2 enforce 涵蓋 4 events root cause taxonomy

| Event root cause class | Phase 2 enforce 路徑 |
|---|---|
| Stash drop without provenance check | E2 §5c + 模板 §6c footer 第 3 條（stash 9 關鍵字 grep）|
| 不認識 WIP 誤 revert | E2 §5c + 模板 §6c footer 第 2 條 |
| Sub-agent dispatch / main thread race | 模板 §6a fetch + §6b branch check |
| Background sub-agent quota awareness | SOP Rule 5 + 未入 template（future P2 tooling）|

### 3. Phase 2 land 完整性（5 個 deliverable）

| # | 交付 | Status | 路徑 |
|---|---|---|---|
| 1 | E2 review §5 race check 5 條 | ✅ LAND | `srv/.claude/agents/E2.md` |
| 2 | PM dispatch §6 模板 4 條 | ✅ LAND | `srv/docs/CCAgentWorkSpace/PM/race_dispatch_template.md` |
| 3 | PM profile.md SOP 連結 | ✅ LAND | `srv/docs/CCAgentWorkSpace/PM/profile.md` |
| 4 | lessons.md Phase 2 entry | ✅ LAND | `srv/docs/lessons.md` § Phase 2 rollout |
| 5 | Operator approval doc（本檔）| ✅ LAND | `srv/docs/CCAgentWorkSpace/Operator/2026-05-16--race_protocol_sop_approved.md` |

### 4. Enforce 嚴格度判斷（為何 enforce 不 advisory-only）

- 4 events 損失量重大（Event 1+2 = 5 grid_trading IMPL + 8 unit tests + 2906 lib tests verify 浪費）
- Root cause 屬「人類認知 + 流程缺口」混合，無法靠 tooling 100% 解決
- Phase 2 enforce 是 **流程強制**（E2 / PM 必跑），不是 tooling 強制（future Phase 5 tooling 才 enforce CLI）
- Operator 評估嚴格度合理：SOP 太鬆 → Phase 3 race compound；太緊 → false positive friction；Phase 2 5+4 條精簡規則是平衡點

---

## Enforcement Timeline（per task brief P0-3）

| 時間 | Milestone |
|---|---|
| **2026-05-16 18:00+** | **Phase 2 enforce 立即生效**；起始 race event count = 0（baseline）|
| 2026-05-23 | 7 day mark — 主會話 + E2 review 紀錄是否有新 race event |
| **2026-05-30** | **2-week review** — PM 統計 enforce effectiveness：是否需 fine-tune（threshold / footer / 5 條 race check）|
| 2026-06-15 | 30 day mark — PA 寫 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-15--race_sop_phase2_30d_review.md` 統計 incident 頻次 + false positive + false negative |

### 2-week review (2026-05-30) 必評估

1. **新 race event 數**：0 → enforce 有效；1+ → 評估 SOP 規則 GAP 補新規則
2. **False positive 頻次**：E2 review §5 / PM 模板 §6 觸發但事後證明無真實 race → revise threshold（如 2h sibling window 過短 → 改 4h）
3. **Friction cost**：sub-agent dispatch / PR review 耗時是否被 5+4 條膨脹過多
4. **Sub-agent adoption rate**：dispatch prompt footer 4 條被 sub-agent 真正遵守的比例（commit message / report 觀察）

### Fine-tune action map

| 評估結果 | Action |
|---|---|
| 0 new race + 0 false positive → enforce stable | 保留 enforce 至 Phase 3 tooling phase |
| 0 new race + ≥ 3 false positive | Revise threshold（如 2h → 4h sibling window）|
| 1-2 new race | 評估 GAP → 補新規則（SOP Rule 9+）|
| ≥ 3 new race | Phase 2 設計失敗 → 全面重新規劃 |

---

## 後續 procedure 加固

- **未來 race 事件**（規則 1-5 任一被觸發 / IMPL 工作損失 / silent revert）必補 `docs/lessons.md` Multi-session race incident 區 entry（per SOP Rule 6 強制）
- **Phase 5 optional tooling**（per SOP §7）— `stash_inspect.sh` + `sibling_check.sh` 為 P2 backlog；如 Phase 2 enforce 效果不足且 false positive 不高，operator GO-AHEAD 才 IMPL tooling
- **未來 SOP revise**：必先 operator GO-AHEAD-OVERRIDE 才 sub-agent IMPL（同 governance-tier change 治理）

---

## 6 條 P2 follow-up（不阻 enforce）

1. **`stash_inspect.sh` 自動化**（SOP §7 Rule 3 自動化）— 0.5h E1 IMPL，最高 ROI；2026-05-30 review 後評估啟動
2. **`sibling_check.sh` 自動化**（SOP §7 Rule 4 自動化）— 0.3h E1 IMPL
3. **`pre_dispatch.sh` 自動化**（SOP §7 Rule 7+8 自動化）— 1.5h E1 IMPL
4. **`.git/hooks/pre-commit` `--only` 強制檢測**（SOP §7 Rule 1 自動化）— PA 評估「強制太狠」風險高；2026-05-30 後 operator 評估啟動
5. **30d review report**（per SOP §9 Phase 6）— PA 2026-06-15 寫
6. **Sub-agent quota dashboard tooling**（SOP Rule 5 enforce）— 若 Phase 2 期間 quota fail ≥ 2 → 啟動 P2-RACE-SOP-RULE5-TOOLING

---

## 相關文件

- SOP 8 條: `srv/docs/governance_dev/2026-05-16--P0-GOV-MULTI-SESSION-RACE-SOP-1.md`
- E2 §5 race check: `srv/.claude/agents/E2.md`
- PM §6 模板: `srv/docs/CCAgentWorkSpace/PM/race_dispatch_template.md`
- PM profile.md 連結: `srv/docs/CCAgentWorkSpace/PM/profile.md`
- Phase 1 events + Phase 2 entry: `srv/docs/lessons.md` § Multi-session race incident + § Phase 2 rollout
- PA Round 4 設計 (Phase 1 land): commit 鏈見 lessons.md Event 1-4 證據
- PM 12-agent audit sign-off: `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--12-agent-audit-pm-signoff.md`
- PM Wave 1-4 cross-validation: `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--wave_1_4_final_cross_validation_pm_consolidated.md`

---

**Status**: ✅ **APPROVED + ENFORCED**（2026-05-16）— governance hardening 立即生效；2 週後 2026-05-30 review fine-tune 必要時 revise；30 天後 2026-06-15 effectiveness report
