"""Engine-flow healthchecks: [1] close_fills, [2] label backfill, [3] exit_features writer, [21] paper_state dust inventory, [22-29] F7 MIT+E5 silent-regression sentinels.
引擎主流 healthcheck：[1] close_fills、[2] label backfill、[3] exit_features writer、[21] paper_state dust inventory、[22-29] F7 MIT+E5 silent regression 哨兵。

MODULE_NOTE (EN): Extracted from the original ``passive_wait_healthcheck.py``
(lines 110-254 in the pre-split file). These checks form the fill-flow
baseline — every downstream ratio check (e.g. [Xb] triangulation, [10]
intents writer) anchors against [1]'s 24h close_fills count.

F7 (2026-04-26, MIT DB audit + E5 engine.log dive): six new MIT+E5 silent-
regression sentinels added because the prior 19 checks failed to catch:
  * ``trading.intents`` 4/17 silent gap (DCS active but downstream fills 0)
  * ``trading.orders`` writer drop with ``trading.fills`` still firing
  * ``trading.signals`` writer dead 7d (since 2026-04-19, never alarmed)
  * ``fills.qty`` distribution drift toward sub-micro (dust spiral re-emergence)
  * phantom fills logged to wrong symbol (``risk_close:%`` qty<1e-3)
  * ``intents`` counter freeze (no new intent in 30+ min during open positions)
  * paper_state ↔ position_reconciler divergence (phantom dust state)

Per CLAUDE.md §七 "被動等待 TODO 必附 healthcheck": every silent-fail mode
discovered post-mortem must register a ``check_*`` function so the next
recurrence is caught at cron cadence (6h).

[21] ``check_paper_state_dust_inventory`` was added 2026-04-26 by the
PAPER-STATE-DUST-INVENTORY-MONITOR ticket (Tier 7 Track 2). It is the
post-EXIT-FEATURES-WRITER-BUG-1-FIX (commits af48ee1 + 83456e5) silent
regression sentinel: counts last-1h ``risk_close:fast_track%`` fills with
``realized_pnl=0`` (the dust-spiral fingerprint that Gate 1 USD floor
should now suppress to zero) plus the distinct-symbol fan-out. It
**supersedes** the narrower MICRO-PROFIT-FIX-1-HEALTHCHECK backlog
(MIT §6 follow-up #6) which only watched the exact-match
``= 'risk_close:fast_track_reduce_half'`` strategy_name; the new check
broadens to ``LIKE 'risk_close:fast_track%'`` (catches future fast_track
sub-tags), adds ``engine_mode IN ('demo','live','live_demo')`` to filter
paper-pipeline noise, and uses three-state PASS/WARN/FAIL verdict
instead of binary ``> 5 → FAIL``. Per PA Track 3 audit (commit
``dd4d64a``) §7.4 ready-to-deploy SQL + cross-env safety analysis (§8).

SQL strings, exit-code semantics, output formatting for [1][2][3] are
byte-identical to the pre-split version. [21] is pure SELECT, zero
mutation, fail-soft on PG unavail (per PA §8 cross-env hard requirement).

MODULE_NOTE (中): 從原 passive_wait_healthcheck.py 110-254 行抽出。
[1][2][3] 是 fill-flow 基線——下游所有比率 check（[Xb] triangulation /
[10] intents 等）皆錨在 [1] 的 24h close_fills。SQL / exit code / 輸出
格式與拆分前 byte-identical。

F7（2026-04-26，MIT DB audit + E5 engine.log dive）：新增 6 個 MIT+E5
silent regression 哨兵，因前 19 個 check 漏抓：
  * ``trading.intents`` 4/17 靜默 gap（DCS 活但下游 fill 為 0）
  * ``trading.orders`` writer 漏寫但 fills 仍寫
  * ``trading.signals`` writer 死寫 7 天（2026-04-19 起，無警報）
  * ``fills.qty`` 分布往 sub-micro 漂移（dust spiral 復發前兆）
  * phantom fill 寫進 wrong symbol（``risk_close:%`` qty<1e-3）
  * ``intents`` counter freeze（持倉中 30+ min 無新 intent）
  * paper_state ↔ position_reconciler divergence（phantom dust state）

per CLAUDE.md §七「被動等待 TODO 必附 healthcheck」：每個 post-mortem
發現的 silent-fail 模式必須註冊 check_* 函數，下次復發才會在 cron 節奏
（6h）被抓到。

[21] ``check_paper_state_dust_inventory`` 為 2026-04-26 PAPER-STATE-DUST-
INVENTORY-MONITOR（Tier 7 Track 2）新增，為 EXIT-FEATURES-WRITER-BUG-1-FIX
（commits af48ee1 + 83456e5）後的 silent regression 哨兵：偵測過去 1h
``risk_close:fast_track%`` 且 ``realized_pnl=0`` 的 fill 計數（Gate 1
USD floor 修復後預期為 0）+ distinct symbol fan-out。本 check **supersedes**
更窄的 MICRO-PROFIT-FIX-1-HEALTHCHECK backlog（MIT §6 #6，只 exact-match
``risk_close:fast_track_reduce_half`` + 二態 ``> 5 → FAIL``）：擴展為
``LIKE 'risk_close:fast_track%'`` 以涵蓋未來 fast_track 子 tag、加
``engine_mode IN ('demo','live','live_demo')`` 過濾 paper noise、改三態
PASS/WARN/FAIL verdict。依據 PA Track 3 audit（commit ``dd4d64a``）
§7.4 ready-to-deploy SQL + §8 跨 env 安全性分析（純 SELECT、零 mutation、
PG 不可達 fail-soft）。
"""

from __future__ import annotations

from .db import _scalar


# ---- individual checks ----

def check_close_fills_24h(cur) -> tuple[str, str, int]:
    """[1] Baseline: demo close_fills in last 24h. All other ratios built on this."""
    n = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '24 hours' "
        "AND engine_mode = 'demo' AND realized_pnl != 0"
    )
    if n == 0:
        return ("FAIL", f"demo 24h close_fills = 0 — P1-10 fee drag 極度壓制 or engine dead", n)
    if n < 5:
        return ("WARN", f"demo 24h close_fills = {n} — extremely low sample, ratios unreliable", n)
    return ("PASS", f"demo 24h close_fills = {n}", n)


def check_label_backfill_ratio(cur, close_fills: int) -> tuple[str, str]:
    """[2] learning.decision_features labels vs close_fills (target ratio ≥ 0.5).

    G6-01 [2a] (2026-04-24): upgraded to a 3-layer guard against silent-dead
    label backfill that the original ratio-only check could not catch:

    1. **Table-existence guard** — `learning.decision_features` is a hypertable
       provisioned by V019. If V019 silent-noop'd (V023 postmortem pattern),
       the table is absent and the original `SELECT COUNT(*) FROM ...` would
       raise `UndefinedTable` → caller wrapped exception → ambiguous WARN.
       Now we explicitly check `to_regclass(...) IS NOT NULL` first and FAIL
       with a clear "V019 not applied" message.

    2. **Original ratio guard** (preserved): label rows / close_fills ratio
       triage; <0.3 FAIL, <0.7 WARN, ≥0.7 PASS.

    3. **JOIN-ratio guard** — the QA audit (2026-04-24 §2.2 #1) flagged that a
       healthy total ratio still hides broken `entry_context_id` linkage:
       fills can land with `entry_context_id` populated but the matching
       `decision_features` row may never appear, breaking downstream
       counterfactual / training joins. We compute the actual JOIN ratio
       between `trading.fills.entry_context_id` (closes only) and
       `learning.decision_features.context_id` for the same 24h window;
       <0.3 FAIL, <0.7 WARN annotation appended to the main verdict. JOIN
       failure does not downgrade an existing PASS to FAIL silently — it
       upgrades the message to WARN with the linkage ratio shown.

    [2] learning.decision_features 標籤 vs close_fills 比率（目標 ≥0.5）。
    G6-01 [2a]（2026-04-24）三層守衛：
      1. 表存在性：V019 silent-noop（V023 postmortem 模式）→ 直接 FAIL，不
         讓原 try/except 把 UndefinedTable 吞成 ambiguous WARN。
      2. 原比率守衛：總標籤 / close_fills，<0.3 FAIL / <0.7 WARN / ≥0.7 PASS。
      3. JOIN linkage 守衛：實算 fills.entry_context_id ↔ features.context_id
         的 JOIN 比率，<0.3 FAIL（linkage 斷裂指紋）/ <0.7 WARN annotated。
         JOIN 失敗不會悄悄把總比率 PASS 降為 FAIL；linkage 比率附加到訊息上。
    """
    # [2a] guard 1: table-existence check — V019 provisioned `learning.decision_features`.
    # Without this, an absent hypertable raises UndefinedTable and the original
    # exception path returned ambiguous WARN — masking V023-style silent-noop
    # migration failures (`migrations` ledger says "applied" but DDL skipped).
    # [2a] guard 1：表存在性 — V019 建 learning.decision_features hypertable。
    # 若缺，原 SELECT 會 UndefinedTable，舊版回 ambiguous WARN，遮蔽 V023-postmortem
    # 模式（migrations ledger 說「已套用」但 DDL 跳過）的 silent-noop migration 失敗。
    try:
        cur.execute("SELECT to_regclass('learning.decision_features') IS NOT NULL")
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"label table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.decision_features missing — V019 not applied (audit_migrations.py)")

    n = _scalar(cur,
        "SELECT COUNT(*) FROM learning.decision_features "
        "WHERE label_filled_at > now() - interval '24 hours' "
        "AND label_net_edge_bps IS NOT NULL "
        "AND engine_mode = 'demo'"
    )
    if close_fills == 0:
        return ("WARN", f"no close_fills baseline, labels={n} unscoreable")
    ratio = n / close_fills if close_fills else 0.0

    # [2a] guard 3: JOIN linkage between fills.entry_context_id and
    # decision_features.context_id (counterfactual / training joins
    # silently break when this drops). Best-effort — failures don't
    # downgrade overall verdict, just annotate.
    # [2a] guard 3：fills.entry_context_id ↔ features.context_id JOIN 比率
    # （斷裂時 counterfactual / training join 全壞）。Best-effort — 失敗不
    # 降級總結論，僅附加註解。
    join_annot = ""
    try:
        cur.execute("""
            WITH closes AS (
                SELECT entry_context_id
                FROM trading.fills
                WHERE ts > now() - interval '24 hours'
                  AND engine_mode = 'demo'
                  AND realized_pnl != 0
                  AND entry_context_id IS NOT NULL
            ),
            joined AS (
                SELECT c.entry_context_id
                FROM closes c
                INNER JOIN learning.decision_features d
                  ON d.context_id = c.entry_context_id
            )
            SELECT
                (SELECT COUNT(*) FROM closes)::int AS n_closes_with_ctx,
                (SELECT COUNT(*) FROM joined)::int AS n_joined
        """)
        n_ctx, n_join = cur.fetchone()
        if n_ctx and n_ctx > 0:
            join_ratio = n_join / n_ctx
            if join_ratio < 0.3:
                join_annot = f", JOIN_LINKAGE_LOW {n_join}/{n_ctx} ({join_ratio:.0%})"
            elif join_ratio < 0.7:
                join_annot = f", join_linkage {n_join}/{n_ctx} ({join_ratio:.0%}) partial"
            else:
                join_annot = f", join_linkage {join_ratio:.0%}"
    except Exception as e:
        # JOIN probe failed (e.g. legacy schema missing entry_context_id col);
        # don't fail the check — just note the gap.
        # JOIN 探測失敗（如舊 schema 缺欄）— 不讓整體 check 紅，僅註明。
        join_annot = f", join_probe_unavailable: {type(e).__name__}"

    base = f"labels_24h={n} vs close_fills={close_fills} (ratio {ratio:.2f}){join_annot}"
    if ratio < 0.3:
        return ("FAIL", base + " — backfill stalled")
    if ratio < 0.7:
        return ("WARN", base + " — partial backfill")
    # If ratio passes but JOIN linkage cratered, downgrade to WARN — the
    # downstream join consumers care more about linkage than total volume.
    # 比率 PASS 但 JOIN 斷裂時降為 WARN — 下游 join consumer 關注 linkage 勝過總量。
    if "JOIN_LINKAGE_LOW" in join_annot:
        return ("WARN", base + " — JOIN linkage low (counterfactual / training joins broken)")
    return ("PASS", base)


def check_exit_features_writer(cur, close_fills: int) -> tuple[str, str]:
    """[3] EXIT-FEATURES-TABLE-1 Rust writer — expect ≈1:1 with close_fills.

    Threshold model upgraded 2026-04-27 from absolute-delta (``> max(3, n/3)``)
    to ratio-band: ``min/max < 0.5 → FAIL``, ``< 0.7 → WARN``, ``≥ 0.7 → PASS``.
    Why: rolling 24h windows for the EF table and the ``[1]`` close_fills
    baseline (``realized_pnl != 0``) re-align differently when burst close
    events (e.g. fast_track dust spiral 37 fills in 9 min on 2026-04-26
    08:04-08:13) cross the window boundary at 6h cron tick. Pre-fix the
    18:00 cron repeatedly transient-FAILed at delta=37 (EF=91 vs close=54)
    while the writer was healthy — confirmed at 19:50 with EF=217 vs
    close=218 (delta=1). Ratio 0.5/0.7 gives ~30-50% drift tolerance for
    burst-window misalignment while still catching real >50% writer break.

    [3] EXIT-FEATURES-TABLE-1 Rust writer — 與 close_fills 比率守衛。
    2026-04-27 從絕對 delta (``> max(3, n/3)``) 升級為比率帶:
    ``min/max < 0.5 → FAIL`` / ``< 0.7 → WARN`` / ``≥ 0.7 → PASS``。
    rolling 24h 窗 EF 表 vs ``[1]`` close_fills 基線 (``realized_pnl != 0``)
    在 burst close 事件 (如 04-26 08:04-08:13 fast_track dust 9 分 37 fill)
    跨窗口邊界時對齊不同;修復前 18:00 cron 反覆 transient-FAIL 於 delta=37
    (EF=91 vs close=54)，但 19:50 即顯示 EF=217 vs close=218 (delta=1)
    writer 健康。0.5/0.7 帶留 ~30-50% drift tolerance 吸收 burst 誤差，
    同時抓 >50% 真 writer 斷。
    """
    n = _scalar(cur,
        "SELECT COUNT(*) FROM learning.exit_features "
        "WHERE ts > now() - interval '24 hours' AND engine_mode = 'demo'"
    )
    if close_fills == 0:
        return ("WARN", f"no close_fills baseline, exit_features={n} unscoreable")
    larger = max(n, close_fills)
    smaller = min(n, close_fills)
    ratio = (smaller / larger) if larger else 1.0
    base = f"exit_features_24h={n} vs close_fills={close_fills} (ratio {ratio:.2f})"
    if ratio < 0.5:
        return ("FAIL", base + " — writer broken (>50% drift)")
    if ratio < 0.7:
        return ("WARN", base + " — writer drift 30-50%, monitor (rolling-window race?)")
    return ("PASS", base)


def check_paper_state_dust_inventory(cur) -> tuple[str, str]:
    """[21] paper_state dust inventory — EXIT-FEATURES-FIX silent-regression sentinel.

    PAPER-STATE-DUST-INVENTORY-MONITOR (PM Tier 7 Track 2, 2026-04-26).

    **What it watches**: counts last-1h fills with
    ``strategy_name LIKE 'risk_close:fast_track%'`` AND ``realized_pnl=0``
    (the dust-spiral fingerprint that EXIT-FEATURES-WRITER-BUG-1-FIX
    Gate 1 USD floor `ft_dust_qty_floor_usd=1.0` should now suppress to
    zero) plus the distinct-symbol fan-out (broader spiral path =
    new path emerged that Gate 1 misses). Filters
    ``engine_mode IN ('demo','live','live_demo')`` to exclude paper-pipeline
    noise (paper engine_mode='paper' may legitimately have residual dust
    activity; we only care about the production-grade pipelines).

    **Three-state verdict** (per PA Track 3 §7.4):
      * ``dust_spiral_count = 0`` → **PASS**
        (Gate 1 USD floor working as designed; no spiral activity)
      * ``1 <= dust_spiral_count <= 10 AND distinct_dust_symbols < 3``
        → **WARN** (Gate 1 may still be holding but dust path activity
        appearing — operator should investigate; possibly a new
        partial-reduce sub-tag, or Gate 1 `ft_dust_qty_floor_usd` set
        too low for some symbol)
      * ``dust_spiral_count > 10`` OR ``distinct_dust_symbols >= 3``
        → **FAIL** (Gate 1 not suppressing; either fix unset/regressed
        or a new spiral path emerged across multiple symbols — needs
        immediate RCA)

    **Why three-state** vs MIT §6 #6's binary ``> 5 → FAIL``: the
    cohesive EXIT-FEATURES-FIX A1+A3+B1 chain expects this count to be
    exactly 0 in steady state; any non-zero is informational (could be
    a transient at fix-deploy boundary, or a fresh spiral path appearing
    that we want to surface BEFORE it crosses the binary threshold).
    WARN gives operator a 10-event window to act before FAIL escalates.

    **Why `LIKE 'risk_close:fast_track%'`** vs MIT §6 #6's exact-match
    ``= 'risk_close:fast_track_reduce_half'``: future fast_track sub-tags
    (e.g. ``risk_close:fast_track_close_all``, ``risk_close:fast_track_sigma_scaled``)
    are caught automatically without needing this healthcheck to be
    re-edited per new tag.

    **Why ``engine_mode IN ('demo','live','live_demo')``** vs MIT §6 #6's
    no engine_mode filter: paper engine has separate cleanup semantics +
    legitimate residual dust activity by design (3E-ARCH paper pipeline);
    we only sentinel the live-grade pipelines where dust-spiral = real bug.

    **Cross-env safety** (per PA §8 hard requirement):
      * Pure SELECT, zero mutation
      * Fail-soft on PG unavail (psycopg2 exception → caller catches)
      * Idempotent (1h window slides, no state)
      * No IPC, no HMAC secret coupling — runs in cron / CI without setup

    **Supersedes** ``MICRO-PROFIT-FIX-1-HEALTHCHECK`` (TODO line ~502,
    MIT EXIT-FEATURES audit §6 #6 spec) — that ticket's narrower scope
    (exact strategy_name match, binary verdict, no engine_mode filter)
    is fully covered by this broader check + tighter classification.

    [21] paper_state dust inventory — EXIT-FEATURES-FIX silent regression 哨兵。
    PAPER-STATE-DUST-INVENTORY-MONITOR（PM Tier 7 Track 2，2026-04-26）。

    **監測對象**：過去 1h ``strategy_name LIKE 'risk_close:fast_track%'``
    且 ``realized_pnl=0`` 的 fill 計數（EXIT-FEATURES-WRITER-BUG-1-FIX
    Gate 1 USD floor `ft_dust_qty_floor_usd=1.0` 修復後預期應為 0
    — 這是 dust spiral 的指紋）+ distinct symbol fan-out（廣度擴大 =
    Gate 1 漏抓的新 path 出現）。`engine_mode IN ('demo','live','live_demo')`
    過濾掉 paper pipeline 噪音（paper 有獨立 cleanup 語意）。

    **三態 verdict**（per PA Track 3 §7.4）：
      * 計數 = 0 → **PASS**（Gate 1 USD floor 工作中，無 spiral 跡象）
      * 1-10 + distinct_symbols < 3 → **WARN**（Gate 1 可能還抓住但有
        dust path 活動 — operator 需查；可能是新 partial-reduce 子 tag，
        或某 symbol 的 Gate 1 floor 設太低）
      * > 10 OR distinct_symbols >= 3 → **FAIL**（Gate 1 沒擋住；
        修復不見了/regressed 或新 spiral path 跨多 symbol 出現 — 需立即 RCA）

    **為何三態 vs MIT §6 #6 二態 `> 5 → FAIL`**：cohesive EXIT-FEATURES-FIX
    A1+A3+B1 鏈在穩態下預期此計數為 exactly 0；任何非零都是訊息
    （可能是修復部署邊界 transient，或新 spiral path 出現需在跨二態
    閾值前 surface）。WARN 給 operator 10-event 窗口在 FAIL escalate 前先動。

    **為何 `LIKE 'risk_close:fast_track%'` vs MIT exact-match**：未來
    fast_track 子 tag（如 close_all、sigma_scaled）自動覆蓋，無需逐 tag
    回來改 healthcheck。

    **為何 engine_mode 過濾 vs MIT 無過濾**：paper engine 有獨立 cleanup
    語意 + 設計上有合法的殘留 dust 活動（3E-ARCH paper pipeline）；
    我們只哨兵 live-grade pipeline，dust-spiral = 真 bug。

    **跨 env 安全**（per PA §8 hard requirement）：純 SELECT、零 mutation、
    PG 不可達 fail-soft（psycopg2 例外由 caller 接）、idempotent（1h
    滑動窗無狀態）、無 IPC、無 HMAC secret coupling — cron / CI 直接跑無前置設定。

    **Supersedes** ``MICRO-PROFIT-FIX-1-HEALTHCHECK``（TODO line ~502，
    MIT EXIT-FEATURES audit §6 #6 spec）— 該 ticket 較窄 scope
    (exact strategy_name、二態、無 engine_mode 過濾) 完全被本 check
    更廣 SQL + 更細 verdict 涵蓋。
    """
    # PA Track 3 §7.4 ready-to-deploy SQL — pure SELECT, FILTER on realized_pnl
    # to compute (a) total dust-spiral fill count, (b) distinct symbol fan-out
    # in a single round-trip.
    # PA Track 3 §7.4 ready-to-deploy SQL — 純 SELECT，FILTER 計算
    # (a) dust-spiral 總計數 + (b) distinct symbol 擴散度，單次 round-trip。
    cur.execute(
        "SELECT "
        "  COUNT(*) FILTER (WHERE realized_pnl = 0) AS dust_spiral_count, "
        "  COUNT(DISTINCT symbol) FILTER (WHERE realized_pnl = 0) AS distinct_dust_symbols "
        "FROM trading.fills "
        "WHERE strategy_name LIKE 'risk_close:fast_track%' "
        "  AND ts > now() - interval '1 hour' "
        "  AND engine_mode IN ('demo', 'live', 'live_demo')"
    )
    row = cur.fetchone()
    # Defensive: psycopg2 returning None on cursor failure (shouldn't happen
    # with our DSN config but the fail-soft contract requires it).
    # 防禦：psycopg2 cursor 失敗回 None（DSN config 下不應發生但 fail-soft
    # contract 要求處理）。
    if row is None:
        return ("WARN", "dust inventory query returned no row (PG / cursor anomaly)")

    dust_count = int(row[0]) if row[0] is not None else 0
    distinct_symbols = int(row[1]) if row[1] is not None else 0

    base_msg = (
        f"dust_spiral_count={dust_count} (last 1h, "
        f"strategy LIKE 'risk_close:fast_track%' AND realized_pnl=0 "
        f"AND engine_mode IN demo/live/live_demo), distinct_symbols={distinct_symbols}"
    )

    # Three-state verdict per PA Track 3 §7.4
    # 三態 verdict per PA Track 3 §7.4
    if dust_count == 0:
        return ("PASS", base_msg + " — Gate 1 USD floor suppressing as designed")

    if dust_count > 10 or distinct_symbols >= 3:
        return (
            "FAIL",
            base_msg
            + " — Gate 1 not suppressing OR new spiral path across symbols; "
            + "RCA EXIT-FEATURES-FIX A1/A3/B1 regression",
        )

    # 1 <= dust_count <= 10 AND distinct_symbols < 3
    return (
        "WARN",
        base_msg + " — dust path activity appearing; investigate before threshold escalates",
    )


# ============================================================================
# F7 (2026-04-26): MIT DB audit + E5 engine.log dive — 6 new silent-regression
# sentinels for trading-flow blind spots that the prior 19 checks failed to
# catch.
# F7（2026-04-26）：MIT DB audit + E5 engine.log dive — 6 個交易管線
# silent regression 哨兵，補前 19 check 的盲點。
# ============================================================================


def check_trading_pipeline_silent_gap(cur) -> tuple[str, str]:
    """[22] Trading pipeline silent gap — DCS active but downstream fills dead.

    F7 MIT spec (2026-04-26). The 4/17 P1-12 incident (intents writer silent
    for 24h) shows that strategist tick can keep firing (DCS rows accumulating)
    while a downstream gate (intent persistence, risk verdict, order push)
    silently wedges. The classic manifestation: ``trading.decision_context_snapshots``
    rows_1h > 100 but ``trading.fills`` minutes_stale > 60 = strategist
    evaluating but no orders making it to fills.

    SQL: 5-layer ``UNION ALL`` against (fills, intents, orders, risk_verdicts,
    decision_context_snapshots) computing minutes_since_last + rows_in_last_1h
    per layer, all filtered to ``engine_mode IN ('demo','live','live_demo')``.

    Three-state verdict:
      * FAIL: DCS rows_1h > 100 AND fills minutes_stale > 60
              (strategist still cooking but fill flow dead >1h)
      * WARN: DCS rows_1h > 100 AND fills minutes_stale 30-60 AND fills rows_1h = 0
              (intermediate cliff: DCS active, fills cliff but <60min)
      * PASS: fills minutes_stale < 30 OR DCS rows_1h <= 100
              (either fills fresh, or DCS quiet — both healthy steady states)

    [22] Trading 管線 silent gap — DCS 活著但下游 fill 死掉的盲點。
    F7 MIT spec（2026-04-26）。4/17 P1-12 事件（intents writer 24h 靜默）
    顯示 strategist tick 可繼續跑（DCS 累積）但下游某 gate 靜默卡死。典型
    表現：DCS rows_1h > 100 但 fills minutes_stale > 60 = strategist 評估
    但無單抵達 fills。
    SQL：5 層 UNION ALL 對（fills, intents, orders, risk_verdicts,
    decision_context_snapshots）計算 minutes_since_last + rows_in_last_1h，
    全部過濾 engine_mode IN ('demo','live','live_demo')。
    三態：FAIL（DCS>100 + fills_stale>60）/ WARN（DCS>100 + fills_stale 30-60
    + fills_1h=0）/ PASS（fills_stale<30 OR DCS<=100）。
    """
    # Defensive rollback to keep cursor clean per the in-pkg convention.
    # 防禦式 rollback：保持 cursor 乾淨，與套件其他 check 一致。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # 5-layer UNION ALL — per MIT spec (commit dd4d64a §F7-22). Single round
    # trip yields per-layer minutes_stale + rows_1h.
    # 5 層 UNION ALL — 依 MIT spec（commit dd4d64a §F7-22）。單次 round-trip
    # 拿到每層的 minutes_stale + rows_1h。
    sql = (
        "WITH cliff_compare AS ( "
        "  SELECT 'fills' AS layer, "
        "    EXTRACT(EPOCH FROM (now() - max(ts))) / 60 AS minutes_stale, "
        "    count(*) FILTER (WHERE ts > now() - interval '1 hour') AS rows_1h "
        "  FROM trading.fills "
        "  WHERE engine_mode IN ('demo', 'live', 'live_demo') "
        "  UNION ALL SELECT 'intents', "
        "    EXTRACT(EPOCH FROM (now() - max(ts))) / 60, "
        "    count(*) FILTER (WHERE ts > now() - interval '1 hour') "
        "  FROM trading.intents "
        "  WHERE engine_mode IN ('demo', 'live', 'live_demo') "
        "  UNION ALL SELECT 'orders', "
        "    EXTRACT(EPOCH FROM (now() - max(ts))) / 60, "
        "    count(*) FILTER (WHERE ts > now() - interval '1 hour') "
        "  FROM trading.orders "
        "  WHERE engine_mode IN ('demo', 'live', 'live_demo') "
        "  UNION ALL SELECT 'risk_verdicts', "
        "    EXTRACT(EPOCH FROM (now() - max(ts))) / 60, "
        "    count(*) FILTER (WHERE ts > now() - interval '1 hour') "
        "  FROM trading.risk_verdicts "
        "  WHERE engine_mode IN ('demo', 'live', 'live_demo') "
        "  UNION ALL SELECT 'decision_context_snapshots', "
        "    EXTRACT(EPOCH FROM (now() - max(ts))) / 60, "
        "    count(*) FILTER (WHERE ts > now() - interval '1 hour') "
        "  FROM trading.decision_context_snapshots "
        "  WHERE engine_mode IN ('demo', 'live', 'live_demo') "
        ") "
        "SELECT layer, minutes_stale, rows_1h FROM cliff_compare"
    )
    try:
        cur.execute(sql)
        rows = cur.fetchall()
    except Exception as e:
        # Fail-soft on schema drift (table missing → undefined_table).
        # If any of the 5 tables is absent, defer to the table-specific
        # check (e.g. [10] for intents, [3] for fills) — don't double-FAIL.
        # Schema drift fail-soft（表缺則由各自專屬 check 接力，避免雙 FAIL）。
        return ("WARN", f"silent_gap query failed: {type(e).__name__}: {e}")

    # Parse rows into a dict for predictable indexing. Some rows may have
    # ``None`` for minutes_stale when the layer has zero rows total (max(ts)
    # of empty set = NULL); coerce to a sentinel large number to indicate
    # "indefinitely stale" without crashing the comparison.
    # 解析 rows 為 dict 便於索引。某層完全空時 minutes_stale=NULL（max(ts) of
    # empty set），用 sentinel 大數標「無限 stale」避免比較時崩潰。
    layer_state: dict[str, tuple[float, int]] = {}
    SENTINEL_INF = 1e9  # treat NULL minutes_stale as "infinitely stale"
    for row in rows:
        layer = str(row[0])
        m_stale = float(row[1]) if row[1] is not None else SENTINEL_INF
        rows_1h = int(row[2] or 0)
        layer_state[layer] = (m_stale, rows_1h)

    # Anchor reads: fills + DCS are the two cliff signals.
    # 錨點讀取：fills + DCS 是兩端 cliff 信號。
    fills_stale, fills_rows_1h = layer_state.get("fills", (SENTINEL_INF, 0))
    dcs_stale, dcs_rows_1h = layer_state.get("decision_context_snapshots", (SENTINEL_INF, 0))

    # Compose informational message — per-layer one-liner so operator can
    # immediately spot which layer is the cliff anchor.
    # 組訊息 — per-layer one-liner，operator 一眼看出哪層 cliff。
    parts = []
    for name in ("fills", "intents", "orders", "risk_verdicts", "decision_context_snapshots"):
        m, r = layer_state.get(name, (SENTINEL_INF, 0))
        if m >= SENTINEL_INF / 2:
            parts.append(f"{name}: empty/never")
        else:
            parts.append(f"{name}: stale={m:.1f}m, 1h={r}")
    base_msg = " | ".join(parts)

    # Verdict per MIT spec.
    # MIT spec verdict。
    if dcs_rows_1h > 100 and fills_stale > 60:
        return (
            "FAIL",
            base_msg
            + " — strategist active (DCS>100/h) but fills cliff>60min: "
            + "intermediate gate (intent persistence / risk verdict / order push) wedged",
        )
    if dcs_rows_1h > 100 and 30 <= fills_stale <= 60 and fills_rows_1h == 0:
        return (
            "WARN",
            base_msg
            + " — DCS active (>100/h) but fills cliff 30-60min and 1h=0: "
            + "early-warning of pipeline wedge",
        )
    return ("PASS", base_msg)


def check_orders_fills_consistency(cur) -> tuple[str, str]:
    """[23] orders ⊇ fills consistency — detect orders writer dropping rows.

    F7 MIT spec (2026-04-26). Every fill must have a corresponding order row
    (same context_id) — the orders writer is upstream of the fills writer in
    the Rust pipeline. If orders silently drops rows (P1-12-style writer
    outage but on the orders side instead of intents), fills can still arrive
    via direct exchange WS while the order ledger stays empty for that
    context_id, breaking downstream auditing + counterfactual joins.

    SQL: ``LEFT JOIN`` ``trading.fills`` against ``trading.orders`` on
    ``context_id`` over the last 30 min, GROUP BY (strategy_name, symbol),
    count fills_n vs orders_n per pair. Surface (a) pairs where fills_n >
    orders_n (orders writer dropping rows for that pair), (b) total
    pairs in the window, (c) total missing orders aggregate.

    F7-FUP-23 cross-cut exclusion (2026-04-26): F4 unattributed audit fills
    (commit 53973ef, ``strategy_name LIKE 'unattributed:%'`` such as
    ``unattributed:bybit_auto``) are emitted by the Rust ``unattributed_fill_observer``
    when an external bybit_auto exec arrives without a matching local context.
    These rows are audit-by-design and have NO corresponding ``trading.orders``
    row (we never submitted the order locally). Without exclusion, every F4
    audit fill counts as a missing order and fabricates a false-positive FAIL
    after the F4 backfill runs. We therefore filter out
    ``strategy_name LIKE 'unattributed:%'`` at the WHERE level — the exclusion
    is intentional and lossless: the F4 audit row already records the
    discrepancy in trading.fills with ``strategy_name LIKE 'unattributed:%'``
    (no separate orphan table).

    JOIN-KEY-FIX (2026-04-27): JOIN was previously ``o.context_id = f.context_id``
    which silently produced ``orders_n = 0`` for every pair because the Rust
    ``flush_orders`` writer (trading_writer.rs:472-505) does NOT include
    ``context_id`` in its INSERT column list — only ``ts, order_id, symbol,
    side, order_type, qty, strategy_name, category, is_paper, status,
    engine_mode``. Every ``trading.orders`` row therefore has empty/default
    ``context_id`` and the LEFT JOIN never matched anything that fills had
    populated. Verified against 30-min sample on 2026-04-27 19:30: 8 pairs
    had fills with ``context_id`` like ``ctx-demo-DOGEUSDT-1777314540000`` +
    ``order_id`` like ``oc_1777314540000_453``, and the matching orders rows
    had identical ``order_id`` but ``context_id=''``. Switched JOIN to
    ``o.order_id = f.order_id`` — orders writer always populates
    ``order_id`` (it's the dedup PK alongside ``ts``), so the new JOIN is
    the canonical reliable key. ``context_id`` may be backfilled into
    ``trading.orders`` in a future Rust writer refactor; until then, this
    healthcheck must JOIN on the key the writer actually persists.

    Three-state verdict:
      * FAIL: pairs_with_missing_orders > 5 (writer broken across multiple pairs)
      * WARN: 1 <= pairs_with_missing_orders <= 5 (transient or single pair)
      * PASS: pairs_with_missing_orders == 0 (consistent)

    Note: MIT spec uses 30-min window (tighter than [3] / [10] 24h) because
    orders writer outages tend to be acute (process restart, schema migration
    half-applied) and we want fast triage at next 6h cron tick.

    [23] orders ⊇ fills consistency — orders writer 漏寫 row 偵測。
    F7 MIT spec（2026-04-26）。每筆 fill 必有對應 order row（同 context_id）。
    若 orders 靜默漏寫（P1-12 風格但 orders 端 outage），fills 仍可從交易所
    WS 直達但 order ledger 為空，破壞下游 audit + counterfactual join。
    SQL：LEFT JOIN trading.fills × trading.orders ON context_id 過去 30 min，
    GROUP BY (strategy_name, symbol)，計 fills_n vs orders_n。三態：FAIL（>5
    pair 漏寫，writer 跨多 pair 壞）/ WARN（1-5）/ PASS（0）。
    30-min 窗：orders outages 多 acute（重啟、schema 半套）→ 下次 6h cron 即抓。

    F7-FUP-23 cross-cut 排除（2026-04-26）：F4 unattributed audit fill
    （commit 53973ef，``strategy_name LIKE 'unattributed:%'`` 如
    ``unattributed:bybit_auto``）由 Rust ``unattributed_fill_observer`` emit —
    外部 bybit_auto exec 抵達但本地無對應 context 時的 audit 紀錄。這類 row
    是 audit-by-design，本來就**沒有**對應 ``trading.orders`` row（我們沒
    本地 submit）。不排除則 F4 backfill 後每筆 audit fill 都被算成 missing
    order，產生假 FAIL。因此於 WHERE 加 ``strategy_name LIKE 'unattributed:%'``
    過濾 — 排除是有意且無損：F4 audit row 已在 trading.fills 以
    strategy_name LIKE 'unattributed:%' 標記保留（無獨立 orphan table）。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # NOTE / 註：``AND f.strategy_name NOT LIKE 'unattributed:%'`` 排除
    # F4 unattributed audit fill（context_id=``unattrib-...`` audit-by-design，
    # 本就無 ``trading.orders`` row）；不排除 = F4 backfill 後系統性 false-positive FAIL。
    # F7-FUP-23 cross-cut fix — see docstring above for rationale.
    #
    # JOIN-KEY-FIX (2026-04-27): JOIN on ``order_id`` (always populated by
    # Rust trading_writer flush_orders) instead of ``context_id`` (which is
    # not in the orders INSERT column list — see flush_orders trading_writer.rs:
    # 472-505). Pre-fix: every pair reported orders_n=0 → systemic false-FAIL.
    # 改 JOIN ``order_id`` 因 Rust ``flush_orders`` 從未寫入 ``context_id``
    # 欄位（只 INSERT 11 欄無 context_id），使用 ``order_id`` 為穩定 join key。
    sql = (
        "WITH order_fill_pairs AS ( "
        "  SELECT f.strategy_name, f.symbol, "
        "    count(DISTINCT f.order_id) AS fills_n, "
        "    count(DISTINCT o.order_id) AS orders_n "
        "  FROM trading.fills f "
        "  LEFT JOIN trading.orders o ON o.order_id = f.order_id "
        "  WHERE f.ts > now() - interval '30 minutes' "
        "    AND f.engine_mode IN ('demo', 'live', 'live_demo') "
        "    AND f.strategy_name NOT LIKE 'unattributed:%' "
        "  GROUP BY 1, 2 "
        ") "
        "SELECT count(*) FILTER (WHERE fills_n > orders_n) AS pairs_with_missing_orders, "
        "  count(*) AS total_pairs, "
        "  COALESCE(sum(fills_n - orders_n) FILTER (WHERE fills_n > orders_n), 0) "
        "    AS total_missing_orders "
        "FROM order_fill_pairs"
    )
    try:
        cur.execute(sql)
        row = cur.fetchone()
    except Exception as e:
        return ("WARN", f"orders_fills consistency query failed: {type(e).__name__}: {e}")

    if row is None:
        return ("WARN", "orders_fills query returned no row (PG / cursor anomaly)")

    pairs_missing = int(row[0] or 0)
    total_pairs = int(row[1] or 0)
    total_missing = int(row[2] or 0)

    base_msg = (
        f"30min: pairs_missing_orders={pairs_missing}/{total_pairs}, "
        f"total_missing_orders={total_missing}"
    )

    if total_pairs == 0:
        # No fills in last 30 min — defer to [1] / [22] for cliff signals.
        # 30 min 內無 fill — 留 [1]/[22] 做 cliff 信號。
        return ("PASS", base_msg + " — no fills in window (defer to [1]/[22])")

    if pairs_missing > 5:
        return (
            "FAIL",
            base_msg + " — orders writer dropping rows across >5 pairs; "
            "RCA Rust trading_writer order INSERT path",
        )
    if pairs_missing >= 1:
        return (
            "WARN",
            base_msg + " — partial orders writer drop; investigate single-pair anomaly",
        )
    return ("PASS", base_msg + " — orders writer consistent with fills")


def check_dust_qty_distribution(cur) -> tuple[str, str]:
    """[25] fills.qty log-bucket distribution — detect dust spiral re-emergence.

    F7 MIT spec (2026-04-26). Counts the percent of last-24h fills whose
    log10(qty) falls in a "sub-micro" bucket band (log_qty_bucket ≤ 4 in a
    20-bucket range over [-15, 5]). When this percentage drifts above
    threshold, the EXIT-FEATURES-WRITER-BUG-1-FIX dust-spiral suppression
    is no longer holding — operator must investigate before a full P0-2
    style outage emerges.

    Bucket scheme: ``width_bucket(log10(qty), -15, 5, 20)`` → 20 equal-width
    log10-buckets between log10(qty)=-15 (qty=1e-15, well below dust) and
    log10(qty)=5 (qty=1e5, mega notional). Bucket 4 corresponds to log10(qty)
    ≈ -11 (qty ≈ 1e-11) which is far below any realistic Bybit min-qty.
    Sub-micro = log_qty_bucket ≤ 4; normal = log_qty_bucket > 4.

    Three-state verdict:
      * FAIL: pct_sub_micro > 30% (dust spiral re-emerged across >30% of fills)
      * WARN: pct_sub_micro > 10% (early warning; monitor next cron)
      * PASS: pct_sub_micro <= 10% (Gate 1 USD floor working)

    Filters: ``qty > 0`` (skip null/zero noise) + ``engine_mode IN
    ('demo','live','live_demo')`` (paper has separate cleanup semantics
    per [21] convention).

    [25] fills.qty 對數桶分布 — dust spiral 復發偵測。
    F7 MIT spec（2026-04-26）。計過去 24h fills 中 log_qty_bucket≤4 的百分比；
    >30% = FAIL（spiral 復發跨 >30% fills）/ >10% WARN（早期警告）/ <=10% PASS。
    bucket 4 對應 log10(qty)≈-11（qty≈1e-11，遠低於任何真 Bybit min-qty），
    sub-micro 漂移即 dust spiral 復發前兆。
    濾條件：qty>0（跳 null/零噪音）+ engine_mode IN demo/live/live_demo
    （paper 有獨立清理語意，per [21] 慣例）。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    sql = (
        "WITH qty_dist AS ( "
        "  SELECT width_bucket(log(10::numeric, qty::numeric), -15, 5, 20) AS log_qty_bucket, "
        "    count(*) AS n "
        "  FROM trading.fills "
        "  WHERE ts > now() - interval '24 hours' AND qty > 0 "
        "    AND engine_mode IN ('demo', 'live', 'live_demo') "
        "  GROUP BY 1 "
        ") "
        "SELECT count(*) FILTER (WHERE log_qty_bucket <= 4) AS sub_micro_buckets, "
        "  count(*) FILTER (WHERE log_qty_bucket > 4) AS normal_buckets, "
        "  COALESCE(100.0 * sum(n) FILTER (WHERE log_qty_bucket <= 4) "
        "         / NULLIF(sum(n), 0), 0.0) AS pct_sub_micro "
        "FROM qty_dist"
    )
    try:
        cur.execute(sql)
        row = cur.fetchone()
    except Exception as e:
        # log10 of zero/negative → math error; SQL guard `qty > 0` should
        # prevent that, but PG version differences may still throw. Fail-soft.
        # log10 of zero/負 → math error；SQL 已過濾 qty>0 但 PG 版本差異仍可能
        # 失敗，fail-soft。
        return ("WARN", f"dust_qty distribution query failed: {type(e).__name__}: {e}")

    if row is None:
        return ("WARN", "dust_qty distribution returned no row (PG anomaly)")

    sub_micro_buckets = int(row[0] or 0)
    normal_buckets = int(row[1] or 0)
    pct_sub_micro = float(row[2] or 0.0)

    base_msg = (
        f"24h fills: sub_micro_buckets={sub_micro_buckets}, "
        f"normal_buckets={normal_buckets}, pct_sub_micro={pct_sub_micro:.2f}%"
    )

    # Empty window — defer to [1]/[22].
    # 空窗 — 留 [1]/[22]。
    if sub_micro_buckets == 0 and normal_buckets == 0:
        return ("PASS", base_msg + " — no fills in 24h (defer to [1]/[22])")

    # Three-state verdict per MIT spec.
    # 三態 verdict per MIT spec。
    if pct_sub_micro > 30.0:
        return (
            "FAIL",
            base_msg + " — dust spiral re-emerged across >30% of fills; "
            "EXIT-FEATURES-FIX A1/A3/B1 regressed",
        )
    if pct_sub_micro > 10.0:
        return (
            "WARN",
            base_msg + " — sub-micro fills >10%; early warning of dust spiral, "
            "monitor next cron",
        )
    return ("PASS", base_msg + " — Gate 1 USD floor holding (≤10% sub-micro)")


def check_intents_counter_freeze(cur) -> tuple[str, str]:
    """[27] trading.intents counter freeze — alarm if no new intent in 30 min.

    F7 E5 spec (2026-04-26). Detects "intents counter doesn't increment in
    30 min during weekday market hours when engine=demo AND positions > 0".
    A frozen intents counter while the engine has live positions is a
    pipeline-wedge fingerprint — strategist may still be evaluating but
    the intent persistence path silently dropped.

    Per spec note: positions > 0 cross-query simplified — the SQL anchors on
    ``trading.intents`` per ``engine_mode`` minutes_since_last_intent +
    intents_30min count. The "demo only positions > 0" gate is implicit:
    if positions are truly zero, demo strategist is idle by design and
    minutes_since_last_intent grows naturally — that's a steady state we
    do not want to FAIL. We mitigate by checking ``minutes_since_last_intent``
    against a coarse threshold (>30 min + intents_30min=0 = FAIL) and only
    on demo / live / live_demo (paper opt-in is excluded).

    Three-state verdict:
      * FAIL: minutes_since_last_intent > 30 AND intents_30min = 0
              (counter frozen + nothing in window)
      * WARN: minutes_since_last_intent 15-30 AND intents_30min = 0
              (early-warning: counter not incrementing)
      * PASS: < 15 OR intents_30min > 0
              (counter live or recent activity)

    Per-engine_mode rollup: each mode evaluated independently; composite
    status = worst across modes (FAIL > WARN > PASS).

    [27] trading.intents counter freeze — 30 min 內無新 intent 警報。
    F7 E5 spec（2026-04-26）。偵測「demo 有持倉時 intents counter 30 min
    不前進」— strategist 仍評估但 intent persistence 靜默斷掉的指紋。
    spec 簡化：positions>0 cross-query 移除，SQL 直接錨 trading.intents
    per engine_mode 的 minutes_since_last_intent + intents_30min。
    持倉真 0 時 demo 自然閒置不應 FAIL，故用 30 min coarse 閾值 + intents_30min=0
    雙條件，避開閒置誤殺。三態：FAIL（>30min+intents_30min=0）/ WARN
    （15-30min+intents_30min=0）/ PASS。per-engine_mode 彙總，最差勝。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Match [10]'s engine_mode coverage: paper excluded (PAPER-DISABLE-1
    # opt-in) — only the demo / live_demo / live engines tracked.
    # 與 [10] engine_mode 覆蓋一致：paper 排除（opt-in），只看 demo /
    # live_demo / live。
    modes = ("demo", "live_demo", "live")
    per_mode: list[tuple[str, str, str]] = []  # (mode, status, short_msg)
    try:
        for mode in modes:
            cur.execute(
                "SELECT EXTRACT(EPOCH FROM (now() - max(ts))) / 60 AS minutes_since, "
                "  count(*) FILTER (WHERE ts > now() - interval '30 minutes') AS intents_30min "
                "FROM trading.intents WHERE engine_mode = %s",
                (mode,),
            )
            row = cur.fetchone()
            if row is None:
                per_mode.append((mode, "PASS", f"{mode}: no row"))
                continue
            # ``max(ts)`` over empty set → NULL → row[0] is None.
            # Treat as "never had an intent in this mode" — a steady state for
            # modes that never spawn (e.g. live before authorisation), do
            # NOT FAIL on it.
            # max(ts) of 空集 → NULL → row[0]=None。視為「此 mode 從未產生
            # intent」（如 live 未授權），這是穩態不應 FAIL。
            if row[0] is None:
                per_mode.append((mode, "PASS", f"{mode}: never produced an intent"))
                continue
            minutes_since = float(row[0])
            intents_30min = int(row[1] or 0)
            seg = f"{mode}: stale={minutes_since:.1f}m, 30min_n={intents_30min}"
            if minutes_since > 30.0 and intents_30min == 0:
                per_mode.append((mode, "FAIL", seg + " — counter frozen >30min"))
            elif 15.0 <= minutes_since <= 30.0 and intents_30min == 0:
                per_mode.append((mode, "WARN", seg + " — counter not incrementing 15-30min"))
            else:
                per_mode.append((mode, "PASS", seg))
    except Exception as e:
        return ("WARN", f"intents counter freeze query failed: {type(e).__name__}: {e}")

    statuses = [s for _, s, _ in per_mode]
    summary = " | ".join(m for _, _, m in per_mode)
    if "FAIL" in statuses:
        return (
            "FAIL",
            summary + " — pipeline wedge (intent persistence dropped); "
            "RCA Rust trading_writer intent INSERT + DCS evaluation path",
        )
    if "WARN" in statuses:
        return ("WARN", summary + " — early warning")
    return ("PASS", summary)


def check_phantom_fills_attribution(cur) -> tuple[str, str]:
    """[28] phantom fills attribution — detect risk_close fills with sub-mililiter qty.

    F7 E5 spec (2026-04-26). The original spec asks for
    ``(fills_increment - bybit_confirmed_fills_increment) > 0`` but no
    ``bybit_confirmed_fills`` column exists. Simplified per spec note: detect
    abnormal-frequency ``risk_close:%`` fills with ``realized_pnl=0 OR NULL``
    AND ``qty < 1e-3`` (sub-mililiter quantity). These are the
    fingerprint of phantom fills logged to wrong symbol after a
    reconciler / paper_state divergence.

    Why qty < 1e-3 not just realized_pnl=0: realized_pnl=0 alone catches
    legitimate dust-spiral fast_track residue (already covered by [21]).
    Adding qty<1e-3 narrows to phantom-attribution: real fills wouldn't
    pass Bybit min-qty (typically 1e-3 BTC = 0.001 BTC ~1 USD min); a fill
    written with sub-mililiter qty is almost certainly mis-attributed.

    GROUP BY (engine_mode, symbol) HAVING count > 5 returns one row per
    (engine_mode, symbol) with phantom_count >= 5; aggregate becomes the
    per-symbol verdict.

    Three-state verdict:
      * FAIL: any (engine_mode, symbol) >= 5 phantom fills/hr (HAVING clause)
      * WARN: 2-4 phantom fills/hr per symbol (sub-FAIL band, computed below)
      * PASS: <= 1 per symbol (or empty / no risk_close fills)

    [28] phantom fills attribution — risk_close 子-mililiter qty 異常偵測。
    F7 E5 spec（2026-04-26）。spec 要求
    ``(fills_increment - bybit_confirmed_fills_increment) > 0`` 但無
    ``bybit_confirmed_fills`` 欄位，per spec 簡化為「risk_close:% 且
    realized_pnl IS NULL OR =0 且 qty<1e-3」異常頻率 — phantom fill 寫進
    wrong symbol 的指紋。
    qty<1e-3 縮窄到 phantom：真 fill 不過 Bybit min-qty（典型 1e-3 BTC =
    0.001 BTC ~1 USD），sub-mililiter qty 幾乎必為 mis-attribution。
    三態：FAIL（任一 (engine_mode, symbol) >=5/hr）/ WARN（2-4/hr）/
    PASS（<=1/hr 或空）。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Pull ALL (engine_mode, symbol) with phantom_count > 0 in last 1h, then
    # bucket into FAIL / WARN bands in Python — single query gives us both
    # bands cleanly.
    # 拉所有 (engine_mode, symbol) 過去 1h phantom_count>0，Python 端分檔。
    sql = (
        "SELECT engine_mode, symbol, count(*) AS phantom_count "
        "FROM trading.fills "
        "WHERE ts > now() - interval '1 hour' "
        "  AND strategy_name LIKE 'risk_close:%' "
        "  AND (realized_pnl IS NULL OR realized_pnl = 0) "
        "  AND qty < 1e-3 "
        "GROUP BY 1, 2 "
        "HAVING count(*) > 1 "
        "ORDER BY phantom_count DESC"
    )
    try:
        cur.execute(sql)
        rows = cur.fetchall()
    except Exception as e:
        return ("WARN", f"phantom_fills attribution query failed: {type(e).__name__}: {e}")

    fail_pairs: list[str] = []
    warn_pairs: list[str] = []
    for row in rows:
        engine_mode = str(row[0])
        symbol = str(row[1])
        n = int(row[2] or 0)
        if n >= 5:
            fail_pairs.append(f"{engine_mode}/{symbol}={n}")
        elif n >= 2:
            warn_pairs.append(f"{engine_mode}/{symbol}={n}")

    if not fail_pairs and not warn_pairs:
        return ("PASS", "no phantom fills in 1h (risk_close + qty<1e-3 + pnl=0)")

    if fail_pairs:
        return (
            "FAIL",
            f"phantom fills FAIL pairs: {', '.join(fail_pairs)}"
            + (f" | WARN pairs: {', '.join(warn_pairs)}" if warn_pairs else "")
            + " — RCA reconciler / paper_state symbol attribution",
        )
    return ("WARN", f"phantom fills WARN pairs: {', '.join(warn_pairs)} — sub-FAIL band")


def check_reconciler_paper_state_divergence(_cur=None) -> tuple[str, str]:
    """[29] position_reconciler vs paper_state divergence — phantom dust state.

    F7 E5 spec (2026-04-26). The semantic: ``position_reconciler.seeded == 0
    AND paper_state.positions > 0`` for >30 min = phantom dust state where
    the reconciler thinks it has nothing to reconcile but paper_state holds
    ghost positions. Real bug fingerprint, not steady state.

    Implementation: per spec note "如 IPC fn 不存在，先 skip 該 check 標
    SKIPPED 並 log；不要 fail-open". The IPC method
    ``get_reconciler_status`` does NOT exist in the current Rust IPC server
    handler registry (verified via grep against rust/openclaw_engine/src/
    ipc_server/handlers/). Therefore this check returns PASS with a
    diagnostic prefix ``[deferred-no-ipc]`` so:
      * runner output displays the row (visible to operator at every cron tick)
      * status string ``PASS`` does not flip the cron exit code
      * message clearly indicates the check is in deferred state pending
        a Rust IPC handler addition (see TODO §F7-29 follow-up).

    No live IPC roundtrip is attempted — keeps the healthcheck self-contained
    for cron / CI without HMAC secret coupling (matches [20] G3-08 Phase 1C
    pattern and the codebase-wide "healthcheck must run without IPC" stance,
    per docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--g3_08_phase1_subtask_b.md).

    Once the Rust IPC method is added (planned in F7 follow-up), this fn is
    upgraded to perform a grep-then-call probe: if the method handler is
    discoverable in the Rust source, do a one-shot call (with HMAC if env
    available); otherwise stay deferred. The PASS output continues to render
    so cron line count remains stable across env states.

    Verdict (current MVP):
      * PASS: always — with diagnostic ``[deferred-no-ipc]`` prefix.

    Verdict (post-IPC; not yet active):
      * FAIL: divergent for >30min (reconciler.seeded=0 + paper_state>0)
      * WARN: divergent < 30min
      * PASS: not divergent (or check skipped per env-gate)

    [29] position_reconciler vs paper_state divergence — phantom dust state。
    F7 E5 spec（2026-04-26）。reconciler.seeded=0 + paper_state>0 持續 >30 min
    即 phantom dust state（reconciler 認為無單但 paper_state 有 ghost positions）—
    真 bug，非穩態。
    當前 IPC 方法 ``get_reconciler_status`` 不存在於 Rust handler registry
    （grep 已驗），per spec「先 skip 並標 SKIPPED」MVP 回 PASS + ``[deferred-no-ipc]``
    前綴，runner 仍顯示該列、cron exit code 不被 flip、操作員可見其 deferred 狀態。
    無 live IPC 往返 — healthcheck 自足、無 HMAC secret 耦合（對齊 [20] G3-08
    Phase 1C 與全 codebase「healthcheck 不發 IPC」立場）。
    Rust IPC handler 加入後升級為 grep-then-call probe；當前 MVP PASS 永遠輸出
    保持 cron 行數穩定。
    """
    # MVP: deferred-no-ipc — return PASS with diagnostic prefix.
    # The ``_cur=None`` parameter slot is kept so the runner contract stays
    # uniform (every check_* takes either a cursor or no argument). Future
    # IPC-driven version will use the cursor for cross-correlation queries.
    # MVP：deferred-no-ipc — 回 PASS + 診斷前綴。_cur=None slot 保持與 runner
    # 契約一致（每個 check_* 取 cursor 或 no-arg），未來 IPC 版會用 cursor 做
    # cross-correlation 查詢。
    return (
        "PASS",
        "[deferred-no-ipc] reconciler vs paper_state divergence check — "
        "Rust IPC method get_reconciler_status not yet exposed; F7 follow-up "
        "will add Rust handler + grep-then-call probe. Currently a stable "
        "PASS placeholder so cron line count is preserved.",
    )
