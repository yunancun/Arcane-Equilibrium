"""
AI Service Feedback Loop — DB persistence + prompt enrichment for Strategist.
AI 服務反饋閉環 — DB 持久化 + Strategist prompt 增強。

MODULE_NOTE (EN): R-06-v2 learning loop closure. Two feedback paths:
  1. Analyst patterns: _handle_analyst() writes winning/losing patterns to
     learning.pattern_insights → Strategist reads when building Ollama prompt.
  2. Guardian rejections: Rust already writes verdicts to trading.risk_verdicts.
     Strategist reads per-strategy reject_rate from DB (join with trading.intents).
  Both paths are fail-open: DB errors never block IPC dispatch.
MODULE_NOTE (中): R-06-v2 學習閉環。兩條反饋路徑：
  1. Analyst 模式：_handle_analyst() 將贏/輸模式寫入 learning.pattern_insights →
     Strategist 構建 Ollama prompt 時讀取。
  2. Guardian 拒絕：Rust 已將裁定寫入 trading.risk_verdicts。Strategist 從 DB 讀取
     逐策略 reject_rate（與 trading.intents 連接）。
  兩條路徑皆 fail-open：DB 錯誤不阻擋 IPC dispatch。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB connection helper / DB 連接輔助
# ---------------------------------------------------------------------------

def _get_conn():
    """
    Get a DB connection from the app pool. Returns None on failure (fail-open).
    從 app 連接池獲取 DB 連接。失敗時返回 None（fail-open）。
    """
    try:
        from . import db_pool
        return db_pool.get_conn()
    except Exception:
        return None


def _put_conn(conn) -> None:
    """Return connection to pool. / 歸還連接到池。"""
    try:
        from . import db_pool
        db_pool.put_conn(conn)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Step 2: Analyst pattern persistence / 步驟 2：Analyst 模式持久化
# ---------------------------------------------------------------------------

def persist_analyst_feedback(
    strategy: str,
    symbol: str,
    metrics: dict[str, Any],
    engine_mode: str = "demo",
) -> None:
    """
    Write Analyst trade analysis patterns to learning.pattern_insights.
    將 Analyst 交易分析模式寫入 learning.pattern_insights。

    Called from ai_service._handle_analyst() after AnalystAgent.analyze_trade().
    由 ai_service._handle_analyst() 在 AnalystAgent.analyze_trade() 後調用。

    Fail-open: any error → log warning, never raises.
    失敗開放：任何異常 → 記錄警告，不向上拋出。
    """
    conn = _get_conn()
    if conn is None:
        return
    try:
        # Extract pattern-relevant data from metrics
        # 從 metrics 中提取模式相關數據
        n_trades = metrics.get("total_trades", 0)
        if n_trades < 1:
            return

        # Derive simple winning/losing signals from aggregated metrics
        # 從聚合指標衍生簡單的贏/輸信號
        win_rate = metrics.get("win_rate", 0.0)
        avg_pnl = metrics.get("avg_pnl_bps", metrics.get("avg_pnl", 0.0))
        confidence = min(0.85, 0.5 + n_trades * 0.001)

        patterns = []
        if win_rate > 0.55:
            patterns.append(("winning", f"win_rate={win_rate:.2%} above threshold", confidence))
        elif win_rate < 0.40:
            patterns.append(("losing", f"win_rate={win_rate:.2%} below threshold", confidence))

        if avg_pnl > 2.0:  # > 2 bps net positive
            patterns.append(("winning", f"avg_pnl={avg_pnl:.2f}bps positive edge", confidence))
        elif avg_pnl < -5.0:  # < -5 bps net negative
            patterns.append(("losing", f"avg_pnl={avg_pnl:.2f}bps negative edge", confidence))

        if not patterns:
            return

        with conn.cursor() as cur:
            for ptype, ptext, conf in patterns:
                cur.execute(
                    """INSERT INTO learning.pattern_insights
                       (strategy_name, symbol, pattern_type, pattern_text,
                        confidence, observation_count, engine_mode)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (strategy, symbol, ptype, ptext, conf, n_trades, engine_mode),
                )
        conn.commit()
        logger.debug(
            "Persisted %d analyst patterns for %s/%s / 寫入 %d 條 Analyst 模式",
            len(patterns), strategy, symbol, len(patterns),
        )
    except Exception as e:
        logger.warning("persist_analyst_feedback failed (fail-open): %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        _put_conn(conn)


# ---------------------------------------------------------------------------
# Strategist prompt feedback section / Strategist prompt 反饋段落
# ---------------------------------------------------------------------------

def get_feedback_section(strategy: str, days: int = 7) -> str:
    """
    Build a prompt section with Analyst insights + Guardian rejection stats.
    構建包含 Analyst 洞察 + Guardian 拒絕統計的 prompt 段落。

    Returns empty string if no feedback data available.
    無反饋數據時返回空字串。

    Fail-open: any error → empty string, never raises.
    失敗開放：任何異常 → 空字串，不向上拋出。
    """
    conn = _get_conn()
    if conn is None:
        return ""
    try:
        sections = []

        # ── Analyst patterns (Step 2) / Analyst 模式 ──
        with conn.cursor() as cur:
            cur.execute(
                """SELECT pattern_type, pattern_text, confidence, observation_count
                   FROM learning.pattern_insights
                   WHERE strategy_name = %s
                     AND ts > now() - interval '%s days'
                   ORDER BY ts DESC
                   LIMIT 8""",
                (strategy, days),
            )
            rows = cur.fetchall()

        if rows:
            lines = ["Recent trade pattern analysis:"]
            for ptype, ptext, conf, n_obs in rows:
                tag = "WIN" if ptype == "winning" else "LOSE"
                lines.append(f"  [{tag}] {ptext} (confidence={conf:.2f}, n={n_obs})")
            sections.append("\n".join(lines))

        # ── Guardian rejection stats (Step 3) / Guardian 拒絕統計 ──
        with conn.cursor() as cur:
            # Join risk_verdicts with intents to get per-strategy reject_rate
            # 連接 risk_verdicts 與 intents 取逐策略拒絕率
            cur.execute(
                """SELECT
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE rv.verdict = 'Rejected') AS rejected,
                       array_agg(DISTINCT rv.reason) FILTER (WHERE rv.verdict = 'Rejected'
                           AND rv.reason IS NOT NULL AND rv.reason != '') AS reasons
                   FROM trading.risk_verdicts rv
                   JOIN trading.intents i ON rv.intent_id = i.intent_id
                     AND rv.ts BETWEEN i.ts - interval '1 minute' AND i.ts + interval '1 minute'
                   WHERE i.strategy_name = %s
                     AND rv.ts > now() - interval '%s days'""",
                (strategy, days),
            )
            row = cur.fetchone()

        if row and row[0] and row[0] > 0:
            total, rejected, reasons = row
            reject_rate = rejected / total if total > 0 else 0.0
            lines = [f"Guardian rejection rate: {reject_rate:.1%} ({rejected}/{total} intents rejected)"]
            if reasons and reject_rate > 0.1:
                # Show top 3 rejection reasons / 顯示前 3 個拒絕原因
                clean_reasons = [r for r in reasons if r][:3]
                if clean_reasons:
                    lines.append(f"  Top rejection reasons: {'; '.join(clean_reasons)}")
                if reject_rate > 0.3:
                    lines.append("  NOTE: High rejection rate — consider more conservative parameters.")
            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    except Exception as e:
        logger.warning("get_feedback_section failed (fail-open): %s", e)
        return ""
    finally:
        _put_conn(conn)
