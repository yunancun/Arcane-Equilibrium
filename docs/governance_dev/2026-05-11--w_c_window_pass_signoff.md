# W-C MAG-082 Stage 2 WINDOW_PASS Sign-off

Date: 2026-05-11
Status: WINDOW_PASS (CONDITIONAL → PASS post Caveat 1+2 fix)
Predecessor: `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md` (W-C evidence window 啟動授權)
QA verdict: PASS (`docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_c_reaudit_post_fix.md`)
Operator sign-off: cloud@ncyu.me 2026-05-11

## 1. 決定

Operator 確認 W-C MAG-082 Stage 2 evidence window 達成 WINDOW_PASS 並授權：

- **W-D MAG-083 final release audit** 派發（QA + PA + QC 三角並行 review）
- **W-D MAG-084 operator sign-off** 在 MAG-083 PASS 後執行
- 不解除任何其他硬邊界（Mainnet / Executor 解鎖 / Stage 3+ / live order authority 仍封閉）

## 2. Evidence Trail

### 2.1 證據累積 baseline（pre-fix）

- W-C evidence window 自 2026-05-08 19:22 UTC 起累積 51 小時 fresh typed lineage（demo + live_demo）
- 174 complete chains（97 demo + 77 live_demo），5 個 object_type 全平衡，0 corruption
- 對應 `[55] agent_decision_spine_lineage` PASS `LINEAGE_READY_NOT_WINDOW_PASS`
- QA 第一次 audit verdict: CONDITIONAL_PASS（含 3 caveat）

### 2.2 Caveat 修復鏈（2026-05-10 → 2026-05-11）

| 工件 | 路徑 |
|---|---|
| PA 技術方案 | `docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md` |
| E1 Rust R1 IMPL（+877 LOC, 15 file） | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl.md` |
| E1 Rust R2 IMPL（1 line + test）| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl_round2.md` |
| E1 Python IMPL（+254 LOC）| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_c_fix_python_impl.md` |
| E2 R1 review | `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-10--w_c_fix_e2_review.md` |
| E2 R2 review | `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w_c_fix_e2_review_round2.md` |
| E5 perf review | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-10--w_c_fix_e5_perf_review.md` |
| E4 regression | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_c_fix_e4_regression.md` |
| QA re-audit | `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_c_reaudit_post_fix.md` |

### 2.3 Deploy

- Commit: `ccf7a4bc0822a9885312f1e8f0eb6678705cebc3` (27 files, +3964 / -17)
- Origin push: 2026-05-11 ~00:00 UTC
- Linux pull + cargo build --release 32.99s clean
- `bash helper_scripts/restart_all.sh --rebuild --keep-auth` 完成
- Engine PID 1596779（paper/demo/live 全 alive，snapshot fresh）
- Deploy_ts UTC: **2026-05-11T00:01:55+00:00**

### 2.4 Empirical post-deploy verification

#### Caveat 1: agent.decision_state_changes wiring

- Post-deploy 58 rows / 24h window，rate ~14.7/min
- Demo + live_demo 平衡（22+22）
- PA target ≥5/min ✓

#### Caveat 2: real-fill ExecutionReport propagation（PA §4.3 對抗 SQL）

- new_fills_post_deploy: 8（4 entry + 4 risk_exit by design）
- entry fills 4/4 = **100%** 有 matching real-fill ER
- ER without matching fill (orphan): **0**
- 真實 ER payload sample: `status=shadow_filled, filled_qty=104.7, liquidity_role=maker, avg_fill_price=0.2824, fees_paid=0.00591346, fill_id+decision_id+order_plan_id+exchange_order_id 全完整, metadata.fill_completion=true, quality_metrics.fill_completion=true`

#### Cross-language contract

- Rust `DecisionEdgeType::ExecutedBy → "executed_by"` byte-aligned Python SQL
- Rust 多處 `"fill_completion": true` JSON aligned Python `(details->>'fill_completion')::boolean IS TRUE`

#### [55] healthcheck

- 新 gate `bad_report_value_quality` / `chains_with_real_fill_report` / `state_changes_24h` 全 wired
- `OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS=2026-05-11T00:01:55+00:00` 哨兵正確啟動
- 現報 `WARN_REAL_FILL_PROPAGATION_PARTIAL`：分母含 196 pre-deploy stub-only chains 攤薄；**transition 期 expected，24h steady-state 自動轉 PASS**
- 不阻 W-D（empirical SQL 才是 ground truth）

## 3. 已 acknowledge 的 caveat

### Caveat 1: agent.decision_state_changes 0 row
**狀態**：CLOSED post-fix。58 rows / 14.7/min empirical 證實生效。

### Caveat 2: ExecutionReport stub payload
**狀態**：CLOSED post-fix。4/4 entry fills 100% real-fill ER，0 orphan。

### Caveat 3: lease_id='bypass' 100%
**狀態**：DEFERRED by-design。
- 2026-05-08 operator authorization 明文允許 bypass evidence mode
- 真實 Decision Lease lifecycle 9 狀態（DRAFT→REGISTERED→ACTIVE→BRIDGED→CONSUMED 等）SoT 在 `learning.lease_transitions` (V054) 表（24h 62k+ rows）
- W-D MAG-083 reviewer brief 必含此章節區分「Agent Spine bypass lineage 證據」vs「learning.lease_transitions 真實 lease lifecycle 證據」
- **Stage 3+ promotion 不可繼承 bypass lineage 當真實 lease 證據**

## 4. Authorized（W-D 派發 + 後續）

- **W-D MAG-083 audit dispatch**：QA + PA + QC 三角並行 review，reviewer brief 必含 4 章節：
  1. Caveat 1+2 fix wiring verified at deploy+~10min by adversarial SQL `missed_n=0`
  2. Real-fill propagation transition：bad_report_value_quality=0 / chains_with_real_fill_report rolling
  3. Caveat 3 lease_id='bypass' 是 2026-05-08 auth by-design，真實 lease lifecycle SoT 在 learning.lease_transitions
  4. Cross-language `executed_by` + `fill_completion=true` empirical byte-equal aligned
- W-D MAG-084 operator sign-off（在 MAG-083 PASS 後）
- CLAUDE.md §三 W-C row 更新為 WINDOW_PASS
- TODO.md §4.1 W-C 翻 ✅ DONE 2026-05-11

## 5. Not Authorized（硬邊界仍封閉）

- 真 Mainnet 流量（OPENCLAW_ALLOW_MAINNET=0 不變）
- Executor shadow unlock / 新 order authority
- Strategy / risk parameter changes
- Scanner hard authority / mode switch
- Stage 3+ promotion
- Live auth manual write / renew / revoke 跳過 signed 流程
- True-live autonomy（仍依賴 W-AUDIT-3..7 / edge / LG-2/3/4 / ops gates 完整）

## 6. 後續行動鏈

1. PM 同 commit 更新 TODO.md §4.1 + CLAUDE.md §三 W-C row
2. PM 派 W-D MAG-083 三角 audit（QA + PA + QC 並行）
3. W-D MAG-083 PASS 後 operator 簽 W-D MAG-084
4. Sprint N+1 D+0 後續 wave 不受 W-C closure 直接影響（W-C 是 critical path 的 blocker，現在解除）
5. Optional follow-up（不阻 W-D，P2 backlog）：
   - E1-Python R3 補 [55] chains 分母 cutoff filter（45-60min）讓 [55] 在 transition 期就 clean PASS
   - W1 wave `check_panel_freshness` pre-existing breakage 修復
   - E5 D-1 P2: `compute_spine_ids()` helper 抽出（stable_id 算法三處複製 invariant lock）

## 7. Cross-references

- 2026-05-08 W-C auth: `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`
- SM-02 R04 retrofit amendment: `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
- CLAUDE.md §三 W-C/MAG-082 + §四 hard boundary + §五 Decision Lease W-C evidence mode
- TODO.md §4.1 W-C / W-D / P0-AGENT-1/2/3/4

---

**Operator signature**: cloud@ncyu.me
**Sign-off datetime**: 2026-05-11 (Path B authorize: PM 直 commit + push + 同次 update TODO/CLAUDE + 派 W-D)
