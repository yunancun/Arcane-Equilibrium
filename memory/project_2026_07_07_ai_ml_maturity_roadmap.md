---
name: project_2026_07_07_ai_ml_maturity_roadmap
description: "maker-nogo 後 PM SIGNED-WITH-GATES 的 AI/ML 交易成熟度路線圖 WP1-WP7;證據閉環先行,全 flag-OFF/runtime-gated Python source contracts,tests PASS,WP1/WP4 P1 待修;TODO 故意不鏡像→memory 為唯一索引"
metadata:
  node_type: memory
  heat: 0
  type: project
  originSessionId: b8f94432-3891-440a-ba13-f17896dd26d5
---

maker-first NO-GO 後 PM 整合(QC/MIT/AI-E/PA/E3/BB + CC)出的 AI/ML 交易成熟度路線圖,狀態 `SIGNED-WITH-GATES`。plan:`docs/CCAgentWorkSpace/Operator/2026-07-05--ai_ml_trading_maturity_engineering_plan.md`;定位文 `2026-07-06--ai_ml_trade_engineering_roadmap_after_maker_challenge.md`。承 [[project_2026_07_06_maker_first_nogo]]、[[feedback_active_profit_unconventional_mandate]];與 [[project_2026_07_08_profit_first_autonomy_loop]] 並為 2026-07-05+ 主動建設兩翼。

**核心姿態(雙重拒絕)**:①拒把 maker-first NO-GO 外推成「AI 沒用 / 無可工程化方向」(定位文 `:14` 明言);②也拒現在就建直接 AI/RL/MCP trader。改走**證據閉環先行**的 work-package 鏈。

**WP 鏈**:WP1 ProofPacket 契約 / WP2 PIT dataset manifest gate / WP3 registry serving 契約(training→serving parity) / WP4 advisory·DreamEngine role hardening / WP5 Demo mutation envelope / WP6 reward-ledger→ProofPacket bridge / WP7 learning-effect review·stop loop。

**現狀=source-contract 層 DONE 且測過,但全 flag-OFF/runtime-gated,非全系統完成**:
- PM 評估:`PASS-SOURCE-CONTRACT-LAYER / FAIL-FULL-TRAINING-PROFIT-EVOLUTION-CLOSURE`(`2026-07-07--ai_ml_roadmap_wp1_wp5_completion_assessment.md`)。
- 全部是 `program_code/ml_training/*.py` Python 契約(如 WP5 `demo_mutation_envelope.py` 799 行);feat commits `e84d2c249`/`8534d716e`/`27f2cdb51`/`e49ef4545` 只碰 `program_code/ml_training`+docs。focused tests 綠:WP1-WP5 `245 passed,1 skipped`;WP7/reward/proof/demo `134 passed`。WP2.1/WP3.1/WP6/WP7 downstream `STOP_SOURCE_CLOSURE_COMPLETE_WAIT_RUNTIME`。
- **開著的 P1 硬化債**(strict adversarial audit `2026-07-07--ai_ml_roadmap_wp1_wp4_strict_adversarial_audit.md`):WP1 ProofPacket 收 malformed `sha256:` ref(`proof_packet_contract.py:625`)→ `ADVANCED_WITH_P1_FIX_REQUIRED`;WP4 advisory packet 收 truthy external-contact alias(`advisory_review_packet.py:229`)同級;WP3 trio 持久化非原子(P2)。
- **邊界**:無 runtime mutation / DB write / exchange·private read / secret / order·probe / Cost Gate 改動 / deploy / live / bandit runtime authority。project-venv quantile dry-run 在 registry DB precheck 仍 `success=False`。

**How to apply**:**operator 2026-07-07 明確指令此路線圖不鏡像進 root `TODO.md`**(`TODO.md:91`),故 memory 是它唯一的 durable 索引家——別以為 TODO 沒有=不存在。現狀是 source 契約+tests,不是可跑的 training-profit 閉環;引用「AI/ML 已成熟」前先看本條的 flag-OFF/P1-debt 事實。SHA `e49ef4545`。
