"""Alpha Tournament Candidate Stage 0R runner helpers（Track B reduced scope）。

模塊用途：read-only Stage 0R candidate sanity runner，對 alpha tournament
candidate（A2 liquidation_cascade_fade）跑 6 sanity check（PSR/DSR + PBO +
leak + concentration + governance ATTEST）並輸出單一 JSON packet。

reduced scope（per spec v2 §1 + PM 2026-05-29 PG probe 證實）：
  - A2 path（functional）：復用 W-AUDIT-8c per-event 路徑（liquidation cascade
    fade，方向與 A2 一致），加兩個 candidate adapter（k_total override DSR
    重算 + fixed-horizon dynamic-exit proxy 標註）。**不改 8c SQL 結構**。
  - A1 path（STUB draft_only）：basis_panel 表 / basis 欄位在 PG 完全不存在
    （docker exec psql 實證 0 hit），A1 的 basis<0.3% entry gate 無資料源 →
    A1 cohort 邏輯不可建（建了即 dead code，違 feedback_no_dead_params）。
    runner 對 A1 硬標 verdict=draft_only, reason=basis_panel_infra_missing
    （infra gap 非 signal failure），不建任何 funding/basis cohort SQL/filter。

主要類函數：A2CandidateConfig / run_a2_candidate / a1_draft_only_packet。
依賴：純 stdlib + sibling W-AUDIT-8c metrics（compute_stage0r / dsr_with_k /
      prepare_parsed_rows）；read-only PG（psycopg2，僅 runner 殼用）。
硬邊界（per CLAUDE §四 + AMD §3.2）：純 offline replay；read-only PG SELECT；
      不下單 / 不碰 live / 不寫 trading|panel|market / 不調 Rust / 不碰
      authorization|lease|paper|mainnet / 不改 TOML / 不解鎖 candidate。
      packet 絕不 emit Stage 1 PASS / auto_promote / order / fill；governance
      check（1/5/6）標 ATTEST 待 E2 grep（ATTEST ≠ PASS）。
"""
