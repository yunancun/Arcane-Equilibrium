"""alpha_wealth_refund_reconciler — P4 online-FDR α-wealth refund 對帳器（cron, flag-OFF）。

MODULE_NOTE
模塊用途：掃 V138 `research.alpha_wealth_ledger` 的 pending debit（經
  `research.alpha_wealth_debit_state` 視圖），按最新 demo binding 讀 demo
  forward 證據（round-trips / stage0r verdict / 日曆天數），餵 A 線純函數
  `demo_confirm_verdict` 三值裁決：
    confirmed → INSERT refund(+φ·|debit|)（φ=PHI_REFUND=1.0）
    failed    → INSERT debit_failed(0) + 鑄 dead-mode lesson（novelty 自饋失敗庫）
    pending   → 不動（債留著 = back-pressure 設計意圖）
主要函數：run_alpha_wealth_refund_reconciler（核心）、reconciler_enabled（flag）、
  main（CLI，--dry-run 預設）。
依賴：psycopg2（caller 注入 conn）、learning_engine.alpha_wealth_controller
  （lazy import：PHI_REFUND / MIN_FORWARD_OOS_DAYS / demo_confirm_verdict /
  refund_amount——M1 常數唯一定義點，禁本地重定義）、
  ml_training.residual_alpha_producer_db.load_round_trips（demo round-trip 證據）。
硬邊界：
  - 只寫 research.alpha_wealth_ledger（append-only INSERT）與 agent.lessons
    （dead_mode 鑄造）；0 live / lease / tier / order 接觸。
  - double-refund / refund+fail 並存在 DB 層不可能（V138 partial unique
    awl_one_terminal_per_debit）——本對帳器冪等，重跑安全。
  - N-3 斷言：refund INSERT 前回查 debit 列，金額不符即 abort 該筆 + log
    （wealth-inflation 防線，MIT N-3）。
  - binding 缺 = 永 pending（attribution 紀律：不猜 cell）。stage0r verdict
    三向映射（PM 裁決，對齊 M1 已 ratify 真值表）：'pass' → green=True、
    'fail'（gate 結論性統計否定）→ green=False，兩者進真值表（NOT-green 臂
    n≥30 → failed + debit_failed + 鑄 dead-mode，QC FIX-1.3）；'defer_data'
    或缺席 = 非結論性 → 本輪跳過維持 pending（不鑄 lesson）。
  - 三重 OFF：flag `OPENCLAW_ALPHA_WEALTH_RECONCILER` 預設 0 + cron job 不在
    DEFAULT_JOBS + V138 表 0 rows = 部署即行為中性。

──────────────────────────────────────────────────────────────────────────────
OPERATOR RUNBOOK（P4 activation 開閘序；全部 operator-gated，本模組不替開）

  1. tier：hypothesize capability 受 LearningTierGate min_tier=L3 鎖
     （in-memory tier 重啟歸 L1 = 結構性 TIER_LOCKED 是正確行為非缺陷）。
     L3 真實可達需 tier 持久化 + 晉升（獨立 governance 工作，不在 P4）。
  2. TOML：settings/l2_capability_registry.toml hypothesize stanza
     enabled=false → true（operator 編輯 + reload）。
  3. cron flags（per-job 顯式，皆不在 DEFAULT_JOBS）：
     - sealer（stage0r preflight，既有 job）：
       OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1 + OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1
       + --jobs residual_preflight（off-peak 03:17 慣例）。
     - 本對帳器：OPENCLAW_ALPHA_WEALTH_RECONCILER=1 + --jobs alpha_wealth_reconciler。

  sealer one-shot（單行；oos window 三 env 必填，PIT 邊界是 operator 承諾）：
    OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1 OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1 OPENCLAW_RESIDUAL_PREFLIGHT_OOS_START=2026-06-01T00:00:00Z OPENCLAW_RESIDUAL_PREFLIGHT_DATA_END=2026-06-10T00:00:00Z OPENCLAW_RESIDUAL_PREFLIGHT_SINCE=2026-03-01T00:00:00Z python3 helper_scripts/cron/ml_training_maintenance.py --jobs residual_preflight

  N-7 預期管理（MIT；勿誤判故障）：Option B 下 reachable wealth α_i ≤ 5e-4
  ⇒ DSR threshold ≥ 0.9995 ⇒ 初期 discovery ≈ 0 是設計後果非故障。健康訊號
  = conducted tests > 0（debit 列在長），不是 discoveries > 0（refund 列在長）。
  healthcheck [83]-[87]（checks_alpha_wealth_fdr.py）按此語義監測。
  另：demo-confirm 是 accounting-confirm（refund 觸發器），不是 alpha 證明
  （null-confirm 率 15-40%，QC FIX-2.3）；P5 晉升須另跑 opened-OOS math gate。
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

RECONCILER_ENV = "OPENCLAW_ALPHA_WEALTH_RECONCILER"
RECONCILER_ACTOR = "alpha_wealth_refund_reconciler"

# dead-mode lesson 鑄造常數：鏡像 helper_scripts/m4/seed_dead_mode_lessons.py
# 檢索鏈（layer2_critic._retrieve_lessons_sync filter 行為）：
#   - symbol = executor _SINK_SYMBOL_PLACEHOLDER（不一致 = novelty 永 miss）。
#   - source = 'dead_mode_seed'：incident sentinel A5 LESSONS_SOURCE_WHITELIST
#     成員；自創新 source 會觸發 A5 異常寫入告警。
#   - content 英文主幹（pg_trgm 字面 trigram，中文相似度 ≈ 0）。
DEAD_MODE_SOURCE = "dead_mode_seed"
DEAD_MODE_SYMBOL = "ml_advisory"
DEAD_MODE_LESSON_TYPE = "dead_mode"

# 獨立 conn 的 statement_timeout（E3：cron 資源隔離，不掛死共享 PG）。
STATEMENT_TIMEOUT_MS = 30_000

# float ↔ Decimal 交叉驗容差（N-3 斷言用；NUMERIC(14,10) 精度 1e-10 之下）。
_N3_CROSS_CHECK_TOL = 1e-12


def reconciler_enabled() -> bool:
    """env-flag（預設 OFF）：未明確設 ``OPENCLAW_ALPHA_WEALTH_RECONCILER=1`` 一律
    視為關（行為中性硬約束；鏡像 residual_alpha_cycle 同款 flag 語義）。"""
    raw = os.environ.get(RECONCILER_ENV)
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_controller() -> Any:
    """lazy import A 線純核心（learning_engine.alpha_wealth_controller）。

    為什麼 lazy：M1 常數（PHI_REFUND / MIN_FORWARD_OOS_DAYS）與
    demo_confirm_verdict 唯一定義在 A 線模組，本檔禁止複製字面（B2 契約條款）；
    lazy 使測試可 stub sys.modules、且 A 線未 merge 的分支上本模組仍可 import。
    """
    try:
        from program_code.learning_engine import alpha_wealth_controller as awc
    except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback（cron sys.path 形態）
        from learning_engine import alpha_wealth_controller as awc  # type: ignore
    return awc


def _default_round_trip_loader() -> Callable[..., list[dict[str, float]]]:
    """lazy 解析 demo round-trip loader（reuse residual_alpha_producer_db）。"""
    try:
        from program_code.ml_training.residual_alpha_producer_db import load_round_trips
    except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
        from ml_training.residual_alpha_producer_db import load_round_trips  # type: ignore
    return load_round_trips


# ─────────────────────────────────────────────────────────────────────────────
# SQL（全參數化；只讀 + append-only INSERT）
# ─────────────────────────────────────────────────────────────────────────────

# pending debit：消費 V138 debit_state 視圖（M1「debit_state 在 PG」落點），
# join 回 debit 事件列取 amount / capability / axis（視圖不帶金額）。
_PENDING_DEBITS_SQL = """
SELECT s.debit_id, s.family_id, s.pre_reg_id, s.alpha_i, s.n_eff, s.debited_at,
       d.capability_id, d.signal_axis, d.amount
FROM research.alpha_wealth_debit_state s
JOIN research.alpha_wealth_ledger d
  ON d.debit_id = s.debit_id AND d.event_type = 'debit'
WHERE s.debit_state = 'pending'
ORDER BY s.debited_at ASC, s.debit_id ASC
"""

# 最新 binding：E1-B 的 bind-demo route append 帶 demo_* 三欄 + debit_id 的事件列；
# 按 event_id 取最新（追加序 = 權威序）。不鎖 event_type——容忍 binding 事件的
# 確切 type 選擇（operator_adjustment 性質，PA §7），以三欄齊備為準。
_LATEST_BINDING_SQL = """
SELECT demo_strategy, demo_symbol, demo_deployed_at
FROM research.alpha_wealth_ledger
WHERE debit_id = %(debit_id)s
  AND demo_strategy IS NOT NULL
  AND demo_symbol IS NOT NULL
  AND demo_deployed_at IS NOT NULL
ORDER BY event_id DESC
LIMIT 1
"""

# stage0r verdict：preflight 蓋過 lineage 的 rec 列（replay_experiment_id 已蓋
# + payload 帶 canonical report）。取該 cell 最新一筆的 verdict。報告本體
# （ResidualEdgeReport）無 strategy/symbol 欄，cell 歸屬只在 rec 列上——
# 故讀 mlde_shadow_recommendations 而非 drar（drar 無 symbol 欄）。
# verdict 字彙 = gate ResidualAlphaVerdict {pass, fail, defer_data}
# （residual_alpha_gate.py:34；preflight 對任何 verdict 皆蓋章寫 payload）。
# 三向映射（PM 裁決）：'pass' → green=True、'fail' → green=False 皆進
# A 線真值表；'defer_data'（或缺席/字彙外值）非結論性 → 本輪跳過維持 pending。
_STAGE0R_VERDICT_SQL = """
SELECT payload->'demo_residual_alpha_report'->>'verdict' AS verdict
FROM learning.mlde_shadow_recommendations
WHERE strategy_name = %(strategy)s
  AND symbol = %(symbol)s
  AND replay_experiment_id IS NOT NULL
  AND payload ? 'demo_residual_alpha_report'
ORDER BY ts DESC
LIMIT 1
"""

# N-3 回查：refund INSERT 前以 debit_id 重讀 debit 列金額（append-only 下不應
# 變，但 wealth-inflation 防線必須驗的是「庫裡那筆」非記憶體快照）。
_FRESH_DEBIT_SQL = """
SELECT amount, family_id, capability_id, signal_axis, pre_reg_id
FROM research.alpha_wealth_ledger
WHERE debit_id = %(debit_id)s AND event_type = 'debit'
"""

_INSERT_EVENT_SQL = """
INSERT INTO research.alpha_wealth_ledger
    (family_id, capability_id, signal_axis, event_type, debit_id, amount,
     pre_reg_id, demo_strategy, demo_symbol, demo_deployed_at, evidence, actor_id)
VALUES
    (%(family_id)s, %(capability_id)s, %(signal_axis)s, %(event_type)s,
     %(debit_id)s, %(amount)s, %(pre_reg_id)s, %(demo_strategy)s,
     %(demo_symbol)s, %(demo_deployed_at)s, %(evidence)s::jsonb, %(actor_id)s)
"""

# prh statement：dead-mode lesson content 的假說本文來源（hypothesize contract
# 要求英文 statement → content 英文主幹自然成立）。
_PRH_STATEMENT_SQL = """
SELECT spec_jsonb->>'statement' AS statement
FROM research.pre_registered_hypotheses
WHERE pre_reg_id = %(pre_reg_id)s
"""

# dead-mode lesson 冪等鑄造（鏡像 seed_dead_mode_lessons._INSERT_SQL；
# source + context_id 為穩定錨點，重跑 rowcount=0）。
_INSERT_LESSON_SQL = """
INSERT INTO agent.lessons
    (symbol, lesson_type, content, session_trigger, context_id,
     outcome_net_bps, session_cost_usd, source)
SELECT %(symbol)s, %(lesson_type)s, %(content)s, %(session_trigger)s, %(context_id)s,
       NULL, NULL, %(source)s
WHERE NOT EXISTS (
    SELECT 1 FROM agent.lessons
    WHERE source = %(source)s AND context_id = %(context_id)s
)
"""


def _fdr_tables_deployed(cur: Any) -> bool:
    """V138 未部署 → 對帳器無事可做（SKIP 不 FAIL，部署順序容忍）。"""
    cur.execute(
        "SELECT to_regclass('research.alpha_wealth_ledger') IS NOT NULL"
        " AND to_regclass('research.alpha_wealth_debit_state') IS NOT NULL"
    )
    row = cur.fetchone()
    return bool(row and row[0])


def _calendar_days(now: datetime, deployed_at: datetime) -> int:
    """forward_oos_days = UTC 日曆天差（B2 語義：date 相減，非滿 24h 週期數）。"""
    now_utc = now.astimezone(timezone.utc)
    dep_utc = deployed_at.astimezone(timezone.utc)
    return (now_utc.date() - dep_utc.date()).days


def _mean_net_bps(round_trips: list[dict[str, float]]) -> float:
    """demo_net_bps = per-trade net bps 平均（realized_edge avg_net 同義）。

    空集回 0.0 僅為型別完整——n_trades=0 在 demo_confirm_verdict 必 pending，
    該值不會被消費成結論。
    """
    if not round_trips:
        return 0.0
    vals = [float(rt["net_bps"]) for rt in round_trips]
    finite = [v for v in vals if math.isfinite(v)]
    if not finite:
        return float("nan")  # 全壞值 → 交給 verdict 的非有限分流（pending）
    return sum(finite) / len(finite)


def _dead_mode_content(
    *,
    family_id: str,
    statement: str,
    stage0r_green: bool,
    demo_net_bps: float,
    n_trades: int,
    debit_id: str,
    demo_strategy: str,
    demo_symbol: str,
    deployed_date: str,
) -> str:
    """dead-mode lesson content（英文主幹；模板鏡像 seeder
    「DEAD MODE [family]: statement. Why dead: ... Evidence: ...」三段式）。"""
    why = []
    if not stage0r_green:
        why.append("stage0r replay preflight not green")
    if math.isfinite(demo_net_bps) and demo_net_bps < 0.0:
        why.append(f"demo forward net {demo_net_bps:.2f} bps < 0")
    why_text = " and ".join(why) if why else "demo forward confirmation failed"
    stmt = (statement or "unregistered hypothesis").strip()
    return (
        f"DEAD MODE [{family_id}]: {stmt}. "
        f"Why dead: {why_text} over {n_trades} demo round-trips. "
        f"Evidence: alpha-wealth debit {debit_id}, demo cell "
        f"{demo_strategy}::{demo_symbol} deployed {deployed_date}, "
        f"adjudicated by {RECONCILER_ACTOR}."
    )


def run_alpha_wealth_refund_reconciler(
    conn: Any,
    *,
    now: Optional[datetime] = None,
    dry_run: bool = True,
    engine_mode: str = "demo",
    round_trip_loader: Optional[Callable[..., list[dict[str, float]]]] = None,
) -> dict[str, Any]:
    """對帳一輪：pending debit × 最新 binding → 三值裁決 → 帳本事件。

    冪等性：refund / debit_failed 由 V138 awl_one_terminal_per_debit 在 DB 層
    封死重複；本函數重跑時 pending 集合自然縮小。每筆 debit 用 SAVEPOINT 隔離
    ——單筆失敗（含併發 unique 撞）不汙染整輪。

    dry_run=True（預設）：全部讀 + 裁決照算，計畫進 summary，結尾 rollback
    （零寫入保證）。dry_run=False：結尾 commit。

    Args:
        conn: psycopg2 連線（caller 注入；cron wrapper 建獨立 conn +
            statement_timeout，測試注入 fake——0 真 DSN fallback 鐵則）。
        now: 裁決時鐘（預設 UTC now；可注入供測試 / 重放）。
        round_trip_loader: 測試注入縫；None = lazy import 真
            load_round_trips（per-cell symbol 篩選，attribution 紀律）。
    """
    awc = _load_controller()
    loader = round_trip_loader or _default_round_trip_loader()
    now_dt = now or datetime.now(timezone.utc)

    summary: dict[str, Any] = {
        "dry_run": bool(dry_run),
        "engine_mode": engine_mode,
        "pending_seen": 0,
        "confirmed": 0,
        "failed": 0,
        "still_pending": 0,
        "no_binding": 0,
        "stage0r_verdict_missing": 0,
        "stage0r_deferred": 0,
        "n3_aborted": 0,
        "insert_conflicts": 0,
        "lessons_minted": 0,
        "lesson_errors": 0,
        "planned_events": [],
    }

    with conn.cursor() as cur:
        if not _fdr_tables_deployed(cur):
            summary["skipped"] = "fdr_tables_not_deployed"
            logger.info("alpha_wealth_reconciler: V138 tables absent; nothing to do")
            # 早退也收 txn（regclass 探測已開 txn；不留 idle-in-transaction）。
            conn.rollback()
            return summary

        cur.execute(_PENDING_DEBITS_SQL)
        pending = cur.fetchall()

    summary["pending_seen"] = len(pending)

    for row in pending:
        (debit_id, family_id, pre_reg_id, alpha_i, n_eff, debited_at,
         capability_id, signal_axis, debit_amount) = row

        with conn.cursor() as cur:
            # binding 缺 = 永 pending（attribution 紀律：不猜 cell）。
            cur.execute(_LATEST_BINDING_SQL, {"debit_id": debit_id})
            binding = cur.fetchone()
            if binding is None:
                summary["no_binding"] += 1
                continue
            demo_strategy, demo_symbol, demo_deployed_at = binding

            # stage0r verdict 缺席 = 證據缺，不渲染結論性裁決（既不退款也不鑄
            # dead-mode——把「preflight 還沒跑」誤判成 falsified 會汙染 novelty
            # 失敗庫，違 QC FIX-1.3 的 dead-mode 語義）。
            cur.execute(
                _STAGE0R_VERDICT_SQL,
                {"strategy": demo_strategy, "symbol": demo_symbol},
            )
            verdict_row = cur.fetchone()
            if verdict_row is None or verdict_row[0] is None:
                summary["stage0r_verdict_missing"] += 1
                continue
            stage0r_verdict = str(verdict_row[0])
            if stage0r_verdict not in ("pass", "fail"):
                # PM 三向裁決（E2 RETURN 複審輪）：'defer_data'（單配置 preflight
                # 誠實 defer 的常態）= 非結論性——既不退款也不鑄 dead-mode，
                # 本輪跳過維持 pending（與上方 verdict 缺席同構，上輪裁決不變）。
                # 字彙外值同走此臂（fail-closed：不認識的 verdict 不渲染結論）。
                summary["stage0r_deferred"] += 1
                continue
            # 'fail' 是 gate 的結論性統計否定（replay preflight 上 DSR/PBO/cost
            # gate 拒絕）——按 QC FIX-1.3「被證偽→鑄 dead-mode」走 A 線真值表
            # False 臂（M1：failed ⇔ n≥30 AND (net<0 OR NOT green) → failed +
            # debit_failed + lesson）；'pass' 走 True 臂。NOT-green 臂自此真實
            # 可達，不再被「僅 pass 進真值表」結構性餓死。
            stage0r_green = stage0r_verdict == "pass"

        # demo round-trips：嚴格按 binding cell（strategy::symbol）+
        # ts ≥ demo_deployed_at（loader 的 since 進 fills 查詢下界）。
        round_trips = loader(
            conn,
            str(demo_strategy),
            engine_mode=engine_mode,
            since=demo_deployed_at,
            symbol=str(demo_symbol),
        )
        n_trades = len(round_trips)
        demo_net_bps = _mean_net_bps(round_trips)
        forward_days = _calendar_days(now_dt, demo_deployed_at)

        verdict = awc.demo_confirm_verdict(
            n_trades=n_trades,
            stage0r_green=stage0r_green,
            demo_net_bps=demo_net_bps,
            forward_oos_days=forward_days,
        )

        if verdict == "pending":
            summary["still_pending"] += 1
            continue

        evidence = {
            "verdict": verdict,
            "phi": float(awc.PHI_REFUND),
            "n_trades": n_trades,
            "demo_net_bps": demo_net_bps if math.isfinite(demo_net_bps) else None,
            "forward_oos_days": forward_days,
            "min_forward_oos_days": int(awc.MIN_FORWARD_OOS_DAYS),
            "stage0r_green": stage0r_green,
            "binding": {
                "demo_strategy": str(demo_strategy),
                "demo_symbol": str(demo_symbol),
                "demo_deployed_at": demo_deployed_at.isoformat(),
            },
            "adjudicated_at": now_dt.isoformat(),
        }

        with conn.cursor() as cur:
            # 單筆 SAVEPOINT：併發 unique 撞 / 單筆異常不汙染整輪。
            cur.execute("SAVEPOINT awl_reconcile_item")
            try:
                if verdict == "confirmed":
                    # N-3 斷言：回查庫裡 debit 列，refund 金額必 == φ·|debit.amount|。
                    cur.execute(_FRESH_DEBIT_SQL, {"debit_id": debit_id})
                    fresh = cur.fetchone()
                    if fresh is None:
                        summary["n3_aborted"] += 1
                        logger.error(
                            "alpha_wealth_reconciler N-3 abort: debit row vanished debit_id=%s",
                            debit_id,
                        )
                        cur.execute("ROLLBACK TO SAVEPOINT awl_reconcile_item")
                        continue
                    fresh_amount = Decimal(fresh[0])
                    # quantize 到 NUMERIC(14,10) 存儲 scale：Decimal 乘法 scale
                    # 相加（1.0×1e-10 → 1e-11），不歸一會與 DB 回讀值 scale 漂移。
                    refund_dec = (
                        Decimal(str(awc.PHI_REFUND)) * abs(fresh_amount)
                    ).quantize(Decimal("1e-10"))
                    # 與 A 線純函數交叉驗（同一 φ、同一 |debit|，float 容差內必合）。
                    cross = awc.refund_amount(float(abs(fresh_amount)))
                    if (
                        fresh_amount != Decimal(debit_amount)
                        or abs(float(refund_dec) - cross) > _N3_CROSS_CHECK_TOL
                    ):
                        summary["n3_aborted"] += 1
                        logger.error(
                            "alpha_wealth_reconciler N-3 abort: refund amount mismatch "
                            "debit_id=%s ledger_amount=%s scan_amount=%s refund=%s cross=%s",
                            debit_id, fresh_amount, debit_amount, refund_dec, cross,
                        )
                        cur.execute("ROLLBACK TO SAVEPOINT awl_reconcile_item")
                        continue
                    plan = {
                        "event_type": "refund",
                        "debit_id": str(debit_id),
                        "amount": str(refund_dec),
                    }
                    if not dry_run:
                        cur.execute(
                            _INSERT_EVENT_SQL,
                            {
                                "family_id": family_id,
                                "capability_id": capability_id,
                                "signal_axis": signal_axis,
                                "event_type": "refund",
                                "debit_id": debit_id,
                                "amount": refund_dec,
                                "pre_reg_id": pre_reg_id,
                                "demo_strategy": demo_strategy,
                                "demo_symbol": demo_symbol,
                                "demo_deployed_at": demo_deployed_at,
                                "evidence": json.dumps(evidence, sort_keys=True),
                                "actor_id": RECONCILER_ACTOR,
                            },
                        )
                    summary["confirmed"] += 1
                    summary["planned_events"].append(plan)
                else:  # failed
                    plan = {
                        "event_type": "debit_failed",
                        "debit_id": str(debit_id),
                        "amount": "0",
                    }
                    if not dry_run:
                        cur.execute(
                            _INSERT_EVENT_SQL,
                            {
                                "family_id": family_id,
                                "capability_id": capability_id,
                                "signal_axis": signal_axis,
                                "event_type": "debit_failed",
                                "debit_id": debit_id,
                                "amount": Decimal("0"),
                                "pre_reg_id": pre_reg_id,
                                "demo_strategy": demo_strategy,
                                "demo_symbol": demo_symbol,
                                "demo_deployed_at": demo_deployed_at,
                                "evidence": json.dumps(evidence, sort_keys=True),
                                "actor_id": RECONCILER_ACTOR,
                            },
                        )
                    summary["failed"] += 1
                    summary["planned_events"].append(plan)
                cur.execute("RELEASE SAVEPOINT awl_reconcile_item")
            except Exception as exc:  # noqa: BLE001 - 單筆隔離，整輪續跑
                summary["insert_conflicts"] += 1
                logger.warning(
                    "alpha_wealth_reconciler: event insert failed (likely concurrent "
                    "terminal, DB unique guards hold) debit_id=%s err=%s: %s",
                    debit_id, type(exc).__name__, exc,
                )
                cur.execute("ROLLBACK TO SAVEPOINT awl_reconcile_item")
                continue

        # failed → 鑄 dead-mode lesson（獨立 SAVEPOINT：lesson 失敗不可吞掉
        # 已記帳的 debit_failed；帳務與 novelty 自饋分離）。
        if verdict == "failed":
            with conn.cursor() as cur:
                cur.execute("SAVEPOINT awl_lesson_item")
                try:
                    cur.execute(_PRH_STATEMENT_SQL, {"pre_reg_id": pre_reg_id})
                    stmt_row = cur.fetchone()
                    statement = str(stmt_row[0]) if stmt_row and stmt_row[0] else ""
                    content = _dead_mode_content(
                        family_id=str(family_id),
                        statement=statement,
                        stage0r_green=stage0r_green,
                        demo_net_bps=demo_net_bps,
                        n_trades=n_trades,
                        debit_id=str(debit_id),
                        demo_strategy=str(demo_strategy),
                        demo_symbol=str(demo_symbol),
                        deployed_date=demo_deployed_at.date().isoformat(),
                    )
                    if not dry_run:
                        cur.execute(
                            _INSERT_LESSON_SQL,
                            {
                                "symbol": DEAD_MODE_SYMBOL,
                                "lesson_type": DEAD_MODE_LESSON_TYPE,
                                "content": content[:4000],
                                "session_trigger": f"{RECONCILER_ACTOR}:{now_dt.date().isoformat()}",
                                "context_id": f"awl:{debit_id}",
                                "source": DEAD_MODE_SOURCE,
                            },
                        )
                        if cur.rowcount > 0:
                            summary["lessons_minted"] += 1
                    cur.execute("RELEASE SAVEPOINT awl_lesson_item")
                except Exception as exc:  # noqa: BLE001 - lesson 失敗不回滾帳務
                    summary["lesson_errors"] += 1
                    logger.warning(
                        "alpha_wealth_reconciler: dead-mode lesson mint failed "
                        "debit_id=%s err=%s: %s",
                        debit_id, type(exc).__name__, exc,
                    )
                    cur.execute("ROLLBACK TO SAVEPOINT awl_lesson_item")

    if dry_run:
        conn.rollback()  # 零寫入保證（belt：dry_run 路徑本就不 INSERT）
    else:
        conn.commit()
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    """CLI 入口：--dry-run 預設；--apply + flag 才寫。

    DSN 來源：--dsn 顯式優先，否則 OPENCLAW_DATABASE_URL（cron 環境慣例）。
    寫模式雙閘：--apply AND OPENCLAW_ALPHA_WEALTH_RECONCILER=1（缺一即拒）。
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=None, help="PG DSN（缺省讀 OPENCLAW_DATABASE_URL）")
    parser.add_argument(
        "--apply", action="store_true",
        help="真寫模式（預設 dry-run；另需 OPENCLAW_ALPHA_WEALTH_RECONCILER=1）",
    )
    parser.add_argument("--engine-mode", default="demo")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.apply and not reconciler_enabled():
        print(f"refused: --apply requires {RECONCILER_ENV}=1", file=sys.stderr)
        return 2

    dsn = args.dsn or os.environ.get("OPENCLAW_DATABASE_URL")
    if not dsn:
        print("refused: no DSN (--dsn or OPENCLAW_DATABASE_URL)", file=sys.stderr)
        return 2

    import psycopg2  # lazy：測試不經 main，不需依賴

    conn = psycopg2.connect(dsn, options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}")
    try:
        summary = run_alpha_wealth_refund_reconciler(
            conn, dry_run=not args.apply, engine_mode=args.engine_mode,
        )
    finally:
        conn.close()
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
