# LG-5-IMPL-2 — Consumer review_live_candidate + bulk re-eval

Date: 2026-05-02
Owner: E1
Spec: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md`
Wave: 2 並行 #1 of 2 (與 IMPL-4 test scaffold 並行，無 file overlap)
Status: Implementation done; await E2 review.

## 目標

實裝 LG-5 Live Candidate Evaluation Contract consumer 側：
- `GovernanceHub.review_live_candidate(candidate_id) -> ReviewVerdict` 入口
- R1-R6 + R-meta 7 條 rule
- audit emission 至 `learning.governance_audit_log` (V035)
- approve 時透過 `hub.acquire_lease()` 取得 lease + 寫回 `mlde_param_applications.decision_lease_id`
- bulk re-evaluation script 對 24 pending live candidates 做歷史回填 + verdict + audit

## 交付

| Path | LOC | 說明 |
|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub_live_candidate_review.py` | 1373 | Consumer 主檔 (PM 預授權 split sibling)，governance_hub.py 0 變動 |
| `helper_scripts/learning/lg5_re_evaluate_pending.py` | 508 | Bulk re-eval CLI (--dry-run / --limit / --verbose) |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py` | 450 | 34 unit tests for R1-R6 + R-meta + math helpers + lease TTL bands |

## 驗證

- `python3 -m py_compile` 兩新檔 0 error
- `python3 -m pytest tests/test_lg5_review_live_candidate.py` 34 passed in 0.04s
- `python3 -m pytest control_api_v1/tests/` 3290 passed / 10 skipped (baseline 3262 + 我新增 34 = 3296，差 6 為 IMPL-1 round 2 land 已完成；無 regression)
- `grep -E '/home/ncyu|/Users/[^/]+'` 0 hit (跨平台 path 乾淨)
- `git diff --check` 0 whitespace error
- LOC: 1373 / 508 / 450 (consumer 在 800-1500 警告區間，可接受未需 split)

## 對 RFC v2 偏離

**0**（pure pattern match RFC §2.2 / §2.3 / §3 / §4 / §5.2 / §6 / §9）

唯一需 E2 / QC 確認的 spec gap fill-in：
1. R4 V_pending fallback：pool 成員無 `review_verdict.expected_net_bps_live_adjusted` 時取 `demo_cost_baseline.avg_realized_net_bps_7d` 當 proxy（RFC §3 R4 沒明寫此 fallback；conservative fill-in）。
2. R3 14d fallback 仍不足 → defer (RFC 沒明說 fail vs defer，採保守 defer 對齊 R3 status="defer" 路徑)。
3. target_name == strategy_name 的隱含假設：candidate row 從 `target_name` 取 strategy（mlde_demo_applier `_record_application` 寫入慣例），fallback `mlde_shadow_recommendations.strategy_name`。

## 邊界 case 決定

- **scipy 替代**: stdlib `statistics.NormalDist().inv_cdf` (PY3.8+ 內建)
- **Lock contention**: 嚴守 read → compute → audit → brief acquire_lease，DB helper 全部獨立 conn，從未在 hub._lock 內持 conn
- **Bulk script StubHub**: 故意 acquire_lease=None — re-eval 屬資訊性，不對歷史 row 發新 lease；audit row 仍寫
- **R-meta fail**: decision="defer" + reason="reject_attribution_chain_too_broken" (per RFC §2.2 enum + §3 R-meta 文字)
- **R6 first**: hard veto 路徑優先於個別 R1-R5 (避免 noise + 對齊 RFC §3 文字「不可被個別 rule pass 覆蓋」)
- **R-meta unknown 路徑**: 在 R6 不 veto + R-meta 路徑前先 check unknown → defer_attribution_chain_strategy_unknown (此屬 producer-side bug，給時間恢復)

## E2 review checklist (per RFC §9 重點)

1. governance_hub.py 完全不動（split sibling pattern 對齊 PM 預授權）→ ✓
2. lock contention：review_live_candidate 全部 DB op 都在 hub._lock 外 → ✓
3. audit fail-closed：audit emit fail → return defer/defer_audit_write_failed，無 silent swallow → ✓

## 報告

- 開發報告：`srv/.claude_reports/20260502_164126_lg5_impl2_consumer.md`
- 本 workspace 摘要：本檔
