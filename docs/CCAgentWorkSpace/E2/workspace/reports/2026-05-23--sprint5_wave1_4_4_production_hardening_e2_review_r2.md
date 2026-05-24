---
report: E2 round 2 mini-verify — Sprint 5+ Wave 1 §4.4 production hardening
date: 2026-05-23
author: E2 (Senior Backend Reviewer + Adversarial Auditor)
phase: Sprint 5+ Wave 1 Phase B-5 round 2 mini-verify (between E1 round 2 fix DONE and E4 regression)
parent_round1: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-23--sprint5_wave1_4_4_production_hardening_e2_review.md
parent_e1_round2: agent a1aabafdd8c98beef (R2-2 §4.4 fix sub-agent)
head_at_review: c4e1411d (combined R2-1 V101/V102 + R2-2 §4.4 + R2-3 Track B+C)
scope_limit: 1-1.5 hr single-thread mini-verify; 只驗 round 1 6 finding 修復狀態
verdict: APPROVE → PASS to E4
---

# §1 Executive Summary

## §1.1 Verdict

**APPROVE → PASS to E4**

Round 1 RETURN 4 finding（HIGH-1 + MEDIUM-1/2/3）+ 2 LOW optional 全修。修復品質完整：注釋 + env var rename + bash error 顯式化 + spec doc drift 全清；0 業務邏輯改動（純 hygiene）。

驗證命令 4 條全 PASS（bash -n × 2 + cargo test track_d 7/7 + lib health 153/153）。

## §1.2 6 Round 1 finding 修復狀態

| # | 嚴重性 | 位置 | 修復狀態 | 證據 |
|---|---|---|---|---|
| 1 | HIGH-1 | `rust/openclaw_engine/tests/sprint2_track_d_api_latency.rs:711-713, 742` | ✓ FIXED | L712 docstring「ws_p50=350 DEGRADED (>300 per Sprint 5+ Wave 1 §4.4 amend)」; L743 fixture「ws_rtt_p50_ms: 350, // DEGRADED (>300 per §4.4 amend)」 |
| 2 | MEDIUM-1 | `helper_scripts/db/ac1b_monthly_healthcheck.sh:34, 44, 136` | ✓ FIXED | L36 docstring + L50 inline rationale + L53 `SENTINEL_DIR="${OPENCLAW_CRON_HEARTBEAT_DIR:-$DATA_DIR/cron_heartbeat}"`; L144-148 sentinel rename `.last_run` → `.last_fire` |
| 3 | MEDIUM-2 | `helper_scripts/db/health_60s_boundary_verify.sh:130, 139` | ✓ FIXED | L131 + L147 顯式 `[[ ! "$x" =~ ^[0-9]+$ ]]` FAIL loud + 非數字另行 alert；移除原 L130/L139 `2>/dev/null`；對應 §2 samples_per_min + §3 30min_summary 兩個 branch 都修 |
| 4 | MEDIUM-3 | `docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md:144` | ✓ FIXED | L144 ladder row 直更 `< 170ms / 170-300ms / > 300ms`; L157-163 amendment block 完整（日期 + 為什麼 + 不變量 mainnet warning + open_fd ladder + Linux 6h empirical 1700-1800 fd baseline）|
| 5 | LOW-1 | `helper_scripts/db/ac1b_monthly_healthcheck.sh:18` | ✓ FIXED | L18 改用 `${OPENCLAW_BASE_DIR:-/home/ncyu/BybitOpenClaw/srv}` 抽象 + L20-21 inline 注釋說明「避硬編碼 /home/ncyu 阻礙未來 Apple Silicon Mac 部署 per CLAUDE §六」 |
| 6 | LOW-2 | `docs/CCAgentWorkSpace/Operator/2026-05-23--sprint5_wave1_production_hardening_design.md` | ✓ FIXED | L6 status 標「DESIGN-DONE (round 2 amendment 2026-05-23 — see note below)」; L7-13 round_2_amendment block 完整含 canonical PA packet redirect |

## §1.3 驗證命令結果（4/4 PASS）

```
$ bash -n /Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/ac1b_monthly_healthcheck.sh
ac1b PASS

$ bash -n /Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/health_60s_boundary_verify.sh
health_60s PASS

$ cargo test --release --test sprint2_track_d_api_latency
test result: ok. 7 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 7.00s

$ cargo test --release --lib health
test result: ok. 153 passed; 0 failed; 0 ignored; 0 measured; 3076 filtered out; finished in 0.10s
```

# §2 OBSERVATION（非 round 2 blocker；follow-up debt）

## §2.1 health_60s_boundary_verify.sh:114 同類 `2>/dev/null` 漏 catch

**位置**: `helper_scripts/db/health_60s_boundary_verify.sh:114`

**現狀**:
```bash
delta_int=$(printf "%.0f" "$col5" 2>/dev/null || echo 0)
```

**問題**: 同 round 1 MEDIUM-2 反模式精神（`silent fallback 0` 對非數字 col5 = NULL / column drift / SQL parse 漏接 → 走 OK band 而非 FAIL loud）。但 round 1 finding §2.3 只列「line 130, 139」（即 §2 samples_per_min + §3 30min_summary 兩 branch），未把 L114 §1 sample_inter_arrival branch 列為 scope。

**判斷**:
- Round 2 fix 嚴格按 round 1 點名 scope 修，**不算 RETURN**（E1 IMPL 並未錯誤）
- L114 屬「round 1 漏 catch、不在 round 2 scope」 — 同類 anti-pattern follow-up debt
- 不阻 round 2 PASS-to-E4 verdict
- 建議下次有 `health_60s_boundary_verify.sh` 修改時順手修（或單獨 hygiene PR）

# §3 §5 Multi-session race check（per CLAUDE 操作人格 + multi-session-race-SOP-1 Phase 2）

| Item | 結果 | 證據 |
|---|---|---|
| 5a fetch + sibling window | ✓ | origin/main HEAD c4e1411d = HEAD c4e1411d（0 drift）；fetch --prune origin 無新 commit |
| 5b status clean | ✓ | review scope 6 file（sprint2_track_d_api_latency.rs / ac1b_monthly_healthcheck.sh / health_60s_boundary_verify.sh / m3_health_monitoring_design_spec.md / Operator design.md）`git status --porcelain` 全 clean（已 commit c4e1411d）;剩 unstaged 屬其他 session WIP (PA/E1/CC autonomy work + Operator sprint_1b audit 等)，不在本 review scope |
| 5c unknown WIP 禁 revert | ✓ | 0 revert / 0 checkout / 0 stash drop |
| 5d sign-off path clean | n/a | E2 不 commit |
| 5e sibling overlap | ✓ | HEAD c4e1411d = origin/main HEAD（同步）；無新 sibling push 進 origin |

# §4 對抗反問結果（限縮 scope）

1. **Q: 「Round 2 fix 是否觸及 round 1 未指出的相鄰邏輯？」**
   - E2: 6 file 改動全嚴格圍繞 round 1 4 finding + 2 LOW；無連帶觸碰其他模塊；HIGH-1 fixture amend 只改注釋 + L743 fixture value，沒改 assertion；MEDIUM-2 修兩 branch 顯式化但未順手修 L114（嚴格 scope 控制）

2. **Q: 「PM Edit 模式 + sub-agent IMPL 是否漏注釋同步？」**
   - E2: round 1 §6.1 對抗反問 catch 過「PM 順手修 line 629 沒順手改 line 742」的 spec drift；round 2 fix 已對齊 L712/L743；E1 sub-agent a1aabafdd8c98beef IMPL report 應已主動 grep `ws_rtt_p50_ms.*200|ws_rtt_p50_ms.*150` 確認影響面（未直接 verify 但結果 6 file 全對齊）

3. **Q: 「Combined commit (R2-1 V101/V102 + R2-2 §4.4 + R2-3 Track B+C) 是否影響 §4.4 mini-verify scope 隔離？」**
   - E2: `git show --stat c4e1411d` 確認 §4.4 scope 6 file 與 V101/V102 + Track B+C 改動 0 overlap；mini-verify 只看 §4.4 scope 6 file 完全可隔離

4. **Q: 「Linux 6h empirical baseline 1700-1800 fd / 162ms ws_rtt 是否真實？」**
   - E2: m3_health_monitoring_design_spec.md L160-163 引用「Linux 6h empirical baseline 落 150-163ms」+「25 symbol × kline WS + REST pool + IPC + PG pool baseline 1700-1800 fd」與 PA report §2.1 數字一致；非空喊；E4 regression / operator Phase F deploy 後須 ssh trade-core 跑一次驗 `docker exec engine ls /proc/{pid}/fd/ | wc -l` actual production runtime（per round 1 §1.2 建議）

# §5 結論

**E2 round 2 verdict: APPROVE → PASS to E4**

- 6 round 1 finding 全修
- 0 新 finding
- 4 驗證命令全 PASS
- §5 multi-session race check 全 PASS
- OBSERVATION 1 條（L114 同類 `2>/dev/null` round 1 漏 catch）作 follow-up debt 記錄，不阻 merge

**下一步**: E4 regression（per PA spec §6.1 Phase C）

---

E2 REVIEW DONE: APPROVE → PASS to E4 (0 finding · OBSERVATION 1 條 follow-up debt) · report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-23--sprint5_wave1_4_4_production_hardening_e2_review_r2.md
