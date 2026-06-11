"""
MODULE_NOTE
模塊用途：
  L2 P4 online-FDR α-wealth PG 帳本層（PA P4 設計 §2.1 分層的「PG 帳本層」）。對
  `research.alpha_wealth_ledger`（append-only 事件帳本）與
  `research.pre_registered_hypotheses`（immutable pre-registration）做 INSERT/SELECT。
  wealth 真值在 PG（M1 NOTE：debit_state 必須持久化，非 in-memory fail-safe）——本模塊
  stateless、無任何 process-global authoritative state，故無 singleton 註冊義務
  （PA §2.1「無新 runtime mutable singleton」判定）。

主要函數：
  - canonical_spec_sha256：canonical JSON sha256（與 residual_hidden_oos_bridge
    `_canonical_sha256` byte-identical：sort_keys / separators=(",",":") / ensure_ascii）。
  - family_id_for / deterministic_debit_id：family 與 debit 識別（MIT #4 / N-4）。
  - ensure_family_initialized / get_family_balance：W_0 鑄造（冪等）+ SUM 餘額。
  - register_pre_registration：STAGE 3.6 pre-reg（FIX-1.1 supersedes 鏈 head 強制 +
    FIX-1.2 evidence 窗單調延伸 + hash 整合性對賬）。
  - record_debit：STAGE 4.5 debit 事件（確定性 debit_id + partial-unique 冪等）。
  - record_demo_binding：bind-demo route 的 operator_adjustment binding 事件。
  - load_wealth_summary：唯讀 wealth/debit_state 投影（GET route 用）。

依賴：db_pool.get_pg_conn（與 ml_advisory sink writer 同一 conn 注入範式；測試注入
  fake conn_provider，0 真連線——PA §8.2 測試隔離鐵則）。

硬邊界：
  - append-only：本模塊只有 INSERT 與 SELECT，0 UPDATE / 0 DELETE（E2/CC grep target）；
    錯帳唯一修正路徑 = operator_adjustment 新事件（審計留痕）。
  - 同步 psycopg2：caller（async executor / route）必須 `asyncio.to_thread` 包裹，
    嚴禁直呼於 event loop（PA §8.3 event-loop 阻塞殷鑑）。
  - fail-closed：store 不可達 → raise AlphaWealthStoreError，caller 映射
    DEFER `alpha_wealth_store_unavailable`（hypothesize 收縮，P3a 路徑零波及）。
  - 0 觸碰 live/tier/lease 面；research schema 之外無寫點。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

from . import db_pool

logger = logging.getLogger("l2_alpha_wealth_store")

# ledger 事件型別字面（V138 CHECK 集合；不在此複製 CHECK 邏輯，僅作參數字面）。
_EVT_FAMILY_INIT = "family_init"
_EVT_DEBIT = "debit"
_EVT_OPERATOR_ADJUSTMENT = "operator_adjustment"

# spec_jsonb 內 evidence 窗的鍵名（FIX-1.2：窗入 hash payload 的唯一載點）。
SPEC_EVIDENCE_WINDOW_KEY = "evidence_window"


class AlphaWealthStoreError(Exception):
    """store 不可達 / 非預期 DB 失敗。

    為什麼獨立例外型別：caller（executor STAGE 3.6/3.7/4.5）必須把「庫不可達」與
    「邏輯 DEFER（superseded / mismatch）」分流——前者映射 DEFER
    `alpha_wealth_store_unavailable`（fail-closed 收縮），後者帶各自 reason code。
    """


@dataclass
class PreRegistrationOutcome:
    """register_pre_registration 結果。ok=False ⇒ defer_reason 必填（caller DEFER）。"""

    ok: bool
    pre_reg_id: int | None = None
    spec_sha256: str = ""
    defer_reason: str = ""  # pre_registration_superseded / pre_registration_mismatch
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DebitOutcome:
    """record_debit 結果。deduped=True ⇒ 同 debit_id 已存在（冪等重放，未雙扣）。"""

    ok: bool
    debit_id: str = ""
    deduped: bool = False
    error: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# 純函數：canonical hash / 識別子（0 DB）
# ═══════════════════════════════════════════════════════════════════════════════


def canonical_spec_sha256(value: Any) -> str:
    """canonical sha256（hex64）。

    為什麼算法必須與 residual_hidden_oos_bridge._canonical_sha256 byte-identical
    （sort_keys=True / separators=(",",":") / ensure_ascii=True）：PA §4.2(2) 跨表
    hash 對賬要求單一算法——任何序列化差異都會讓 pre-reg 消費層誤判 mismatch。
    不 import bridge（ml_training ↔ control_api 跨層 import 面不開），以測試鎖等值。
    """
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def family_id_for(capability_id: str, primary_axis: str) -> str:
    """wealth family 識別：`capability_id:primary_axis`（MIT ratify #4）。

    為什麼不用 axes 組合：組合 family 的 2^|axes| 鑄幣面是 wealth-inflation 攻擊向量
    （每開新 family 鑄新 W_0）。primary_axis 由 guard clause F 強制 ∈ signal_axes_used。
    """
    return f"{capability_id}:{primary_axis}"


def deterministic_debit_id(
    pre_reg_id: int, window_start: str, window_end: str
) -> str:
    """確定性 debit_id（MIT N-4）：sha256(f"{pre_reg_id}:{window_start}:{window_end}")[:16]。

    為什麼禁隨機 / 禁 attempt 計數：「gate verdict 後、INSERT 前 crash → 重試」若鑄新
    debit_id 會雙扣；確定性 id + DB partial-unique（awl_one_debit_per_id）使重試冪等。
    同 pre_reg + 同窗 = 同一次 test；新 look 必經窗延伸（新 window_end）→ 新 debit_id。
    """
    payload = f"{int(pre_reg_id)}:{window_start}:{window_end}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _spec_core(spec_jsonb: Mapping[str, Any]) -> dict[str, Any]:
    """spec 的「核心身份」= 全部欄位除 evidence_window（FIX-1.2 窗單調規則的比較基底）。"""
    return {k: v for k, v in spec_jsonb.items() if k != SPEC_EVIDENCE_WINDOW_KEY}


def _spec_window(spec_jsonb: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """取 spec 內 evidence 窗（window_start, window_end）ISO 字串；缺 → (None, None)。"""
    win = spec_jsonb.get(SPEC_EVIDENCE_WINDOW_KEY)
    if not isinstance(win, Mapping):
        return None, None
    ws = win.get("window_start")
    we = win.get("window_end")
    return (str(ws) if ws is not None else None, str(we) if we is not None else None)


# ═══════════════════════════════════════════════════════════════════════════════
# 內部：conn 取得（與 ml_advisory sink writer 同範式）
# ═══════════════════════════════════════════════════════════════════════════════


def _provider(conn_provider: Any) -> Any:
    return conn_provider or db_pool.get_pg_conn


# ═══════════════════════════════════════════════════════════════════════════════
# wealth 帳本（research.alpha_wealth_ledger）
# ═══════════════════════════════════════════════════════════════════════════════


def ensure_family_initialized(
    family_id: str,
    *,
    capability_id: str,
    signal_axis: str,
    amount: float,
    actor_id: str,
    evidence: Mapping[str, Any] | None = None,
    conn_provider: Any = None,
) -> None:
    """冪等鑄造 family_init 事件（W_0）。已 init → no-op（partial-unique 擋）。

    為什麼 ON CONFLICT 對 partial unique index：awl_one_init_per_family 是
    `(family_id) WHERE event_type='family_init'` 的 partial unique；conflict target
    必須帶同一 predicate 才命中該 index（PG 語法要求）。冪等性由 DB 層封死，
    非應用層自律（PA §14-1）。
    """
    try:
        with _provider(conn_provider)() as conn:
            if conn is None:
                raise AlphaWealthStoreError("db_unavailable")
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO research.alpha_wealth_ledger (
                    family_id, capability_id, signal_axis, event_type,
                    amount, evidence, actor_id
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (family_id) WHERE event_type = 'family_init' DO NOTHING
                """,
                (
                    family_id,
                    capability_id,
                    signal_axis,
                    _EVT_FAMILY_INIT,
                    float(amount),
                    json.dumps(dict(evidence or {}), ensure_ascii=True, default=str),
                    actor_id,
                ),
            )
            conn.commit()
    except AlphaWealthStoreError:
        raise
    except Exception as exc:  # noqa: BLE001 — 不可達 / 非預期失敗 → fail-closed 例外
        raise AlphaWealthStoreError(f"family_init_failed: {exc}") from exc


def get_family_balance(family_id: str, *, conn_provider: Any = None) -> float:
    """family 餘額 = SELECT COALESCE(SUM(amount),0)（無物化 running balance，審計純淨）。"""
    try:
        with _provider(conn_provider)() as conn:
            if conn is None:
                raise AlphaWealthStoreError("db_unavailable")
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM research.alpha_wealth_ledger
                WHERE family_id = %s
                """,
                (family_id,),
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
    except AlphaWealthStoreError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AlphaWealthStoreError(f"balance_read_failed: {exc}") from exc


def record_debit(
    *,
    family_id: str,
    capability_id: str,
    signal_axis: str,
    debit_id: str,
    alpha_i: float,
    n_eff: int,
    pre_reg_id: int,
    actor_id: str,
    evidence: Mapping[str, Any] | None = None,
    conn_provider: Any = None,
) -> DebitOutcome:
    """STAGE 4.5 debit 事件：amount = −alpha_i；k_for_dsr 恆 = n_eff（M2 單 debit 合約）。

    冪等：確定性 debit_id（N-4）+ `ON CONFLICT (debit_id) WHERE event_type='debit'
    DO NOTHING`——crash-retry / 同窗重放不雙扣（rowcount=0 ⇒ deduped）。
    """
    try:
        with _provider(conn_provider)() as conn:
            if conn is None:
                return DebitOutcome(ok=False, debit_id=debit_id, error="db_unavailable")
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO research.alpha_wealth_ledger (
                    family_id, capability_id, signal_axis, event_type, debit_id,
                    amount, alpha_i, n_eff, k_for_dsr, pre_reg_id, evidence, actor_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (debit_id) WHERE event_type = 'debit' DO NOTHING
                """,
                (
                    family_id,
                    capability_id,
                    signal_axis,
                    _EVT_DEBIT,
                    debit_id,
                    -abs(float(alpha_i)),  # debit 必為負額（V138 awl_amount_sign_chk）
                    float(alpha_i),
                    int(n_eff),
                    int(n_eff),  # k_for_dsr 恆 = n_eff（DB CHECK 雙保險）
                    int(pre_reg_id),
                    json.dumps(dict(evidence or {}), ensure_ascii=True, default=str),
                    actor_id,
                ),
            )
            deduped = int(cur.rowcount or 0) == 0
            conn.commit()
            return DebitOutcome(ok=True, debit_id=debit_id, deduped=deduped)
    except Exception as exc:  # noqa: BLE001 — debit 寫失敗 → caller fail-closed（不鑄 discovery）
        logger.warning("alpha-wealth debit INSERT 失敗（caller 必 fail-closed）：%s", exc)
        return DebitOutcome(ok=False, debit_id=debit_id, error=str(exc))


def record_demo_binding(
    *,
    debit_id: str,
    demo_strategy: str,
    demo_symbol: str,
    demo_deployed_at: dt.datetime,
    actor_id: str,
    conn_provider: Any = None,
) -> dict[str, Any]:
    """bind-demo：對既存 debit append 一筆 operator_adjustment binding 事件（amount=0）。

    為什麼是新事件 row 而非 UPDATE：帳本 append-only（REVOKE UPDATE/DELETE）；
    reconciler 取「最新」binding（PA §7）。debit 不存在 → 拒（不對幽靈債建 binding）。
    """
    try:
        with _provider(conn_provider)() as conn:
            if conn is None:
                return {"ok": False, "error": "db_unavailable"}
            cur = conn.cursor()
            # binding 必須錨定既存 debit（同時取 family 血緣欄，binding 事件保持同 family）。
            cur.execute(
                """
                SELECT family_id, capability_id, signal_axis
                FROM research.alpha_wealth_ledger
                WHERE event_type = 'debit' AND debit_id = %s
                LIMIT 1
                """,
                (debit_id,),
            )
            row = cur.fetchone()
            if row is None:
                return {"ok": False, "error": "debit_not_found"}
            family_id, capability_id, signal_axis = str(row[0]), str(row[1]), str(row[2])
            cur.execute(
                """
                INSERT INTO research.alpha_wealth_ledger (
                    family_id, capability_id, signal_axis, event_type, debit_id,
                    amount, demo_strategy, demo_symbol, demo_deployed_at,
                    evidence, actor_id
                )
                VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    family_id,
                    capability_id,
                    signal_axis,
                    _EVT_OPERATOR_ADJUSTMENT,
                    debit_id,
                    demo_strategy,
                    demo_symbol,
                    demo_deployed_at,
                    json.dumps({"binding": True}, ensure_ascii=True),
                    actor_id,
                ),
            )
            conn.commit()
            return {
                "ok": True,
                "debit_id": debit_id,
                "family_id": family_id,
                "demo_strategy": demo_strategy,
                "demo_symbol": demo_symbol,
            }
    except Exception as exc:  # noqa: BLE001 — route 端回 503（store unavailable）
        logger.warning("alpha-wealth bind-demo 寫失敗：%s", exc)
        return {"ok": False, "error": "store_unavailable"}


def load_wealth_summary(
    family_id: str | None = None, *, conn_provider: Any = None, limit: int = 100
) -> dict[str, Any]:
    """唯讀 wealth 投影：per-family 餘額 + 最近 debit_state 視圖 rows（GET route 用）。"""
    try:
        with _provider(conn_provider)() as conn:
            if conn is None:
                raise AlphaWealthStoreError("db_unavailable")
            cur = conn.cursor()
            if family_id:
                cur.execute(
                    """
                    SELECT family_id, COALESCE(SUM(amount), 0)
                    FROM research.alpha_wealth_ledger
                    WHERE family_id = %s
                    GROUP BY family_id
                    """,
                    (family_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT family_id, COALESCE(SUM(amount), 0)
                    FROM research.alpha_wealth_ledger
                    GROUP BY family_id
                    ORDER BY family_id
                    """
                )
            balances = {str(r[0]): float(r[1]) for r in cur.fetchall()}

            if family_id:
                cur.execute(
                    """
                    SELECT debit_id, family_id, pre_reg_id, alpha_i, n_eff,
                           debited_at, debit_state
                    FROM research.alpha_wealth_debit_state
                    WHERE family_id = %s
                    ORDER BY debited_at DESC
                    LIMIT %s
                    """,
                    (family_id, int(limit)),
                )
            else:
                cur.execute(
                    """
                    SELECT debit_id, family_id, pre_reg_id, alpha_i, n_eff,
                           debited_at, debit_state
                    FROM research.alpha_wealth_debit_state
                    ORDER BY debited_at DESC
                    LIMIT %s
                    """,
                    (int(limit),),
                )
            debits = [
                {
                    "debit_id": str(r[0]),
                    "family_id": str(r[1]),
                    "pre_reg_id": int(r[2]) if r[2] is not None else None,
                    "alpha_i": float(r[3]) if r[3] is not None else None,
                    "n_eff": int(r[4]) if r[4] is not None else None,
                    "debited_at": r[5].isoformat() if r[5] is not None else None,
                    "debit_state": str(r[6]),
                }
                for r in cur.fetchall()
            ]
            return {"balances": balances, "debits": debits}
    except AlphaWealthStoreError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AlphaWealthStoreError(f"wealth_summary_read_failed: {exc}") from exc


# ═══════════════════════════════════════════════════════════════════════════════
# pre-registration（research.pre_registered_hypotheses；FIX-1.1 / FIX-1.2）
# ═══════════════════════════════════════════════════════════════════════════════


def register_pre_registration(
    *,
    family_id: str,
    capability_id: str,
    signal_axis: str,
    spec_jsonb: Mapping[str, Any],
    source_l2_reply_id: str | None,
    actor_id: str,
    conn_provider: Any = None,
) -> PreRegistrationOutcome:
    """STAGE 3.6 pre-registration：commit-before-render（hash 先於一切統計渲染，FIX-1.2）。

    決策樹（全部 mismatch / superseded 收縮向 DEFER，不偽造血緣）：
      1. 精確命中 (family_id, spec_sha256)：
         a. 庫內 spec_jsonb 重算 hash ≠ 存的 spec_sha256 → DEFER pre_registration_mismatch
            （jsonb round-trip / 竄改防線；HIGH-1 -0.0 殷鑑——spec 全字串設計使其不可達，
            但對賬仍做，不靠 caller 自律）。
         b. 該 row 已被 supersede（存在 supersedes_pre_reg_id 指向它的 row）→
            DEFER pre_registration_superseded（FIX-1.1：consume 限鏈 head）。
         c. 否則 reuse 既存 pre_reg_id（同 spec 同窗重放 = 同一 pre-reg）。
      2. 無精確命中 → 找同 family「同核心身份」（spec 去 evidence_window）的鏈 head：
         a. 無前行 → INSERT 新 row（supersedes NULL）。
         b. 有 head → FIX-1.2 窗單調：window_start 相等 AND window_end 不回退
            （僅向後 accrual 延伸）→ INSERT 新 row（supersedes=head）；
            其他偏離 → DEFER pre_registration_mismatch。
         c. 核心命中但全被 supersede 且無 head（血緣畸形）→ DEFER pre_registration_superseded。

    store 不可達 → raise AlphaWealthStoreError（caller 映射 alpha_wealth_store_unavailable）。
    """
    spec = dict(spec_jsonb)
    spec_sha = canonical_spec_sha256(spec)
    new_ws, new_we = _spec_window(spec)
    try:
        with _provider(conn_provider)() as conn:
            if conn is None:
                raise AlphaWealthStoreError("db_unavailable")
            cur = conn.cursor()

            # ── 1) 精確命中 (family_id, spec_sha256) ──
            cur.execute(
                """
                SELECT pre_reg_id, spec_jsonb, spec_sha256
                FROM research.pre_registered_hypotheses
                WHERE family_id = %s AND spec_sha256 = %s
                LIMIT 1
                """,
                (family_id, spec_sha),
            )
            exact = cur.fetchone()
            if exact is not None:
                pre_reg_id = int(exact[0])
                stored_spec = exact[1] if isinstance(exact[1], Mapping) else {}
                # 1a) 庫內 jsonb 重算對賬（hash 整合性；mismatch → DEFER）。
                if canonical_spec_sha256(dict(stored_spec)) != str(exact[2]):
                    return PreRegistrationOutcome(
                        ok=False,
                        spec_sha256=spec_sha,
                        defer_reason="pre_registration_mismatch",
                        details={"why": "stored_hash_integrity_failed"},
                    )
                # 1b) FIX-1.1：必須是 supersedes 鏈 head。
                cur.execute(
                    """
                    SELECT 1 FROM research.pre_registered_hypotheses
                    WHERE supersedes_pre_reg_id = %s
                    LIMIT 1
                    """,
                    (pre_reg_id,),
                )
                if cur.fetchone() is not None:
                    return PreRegistrationOutcome(
                        ok=False,
                        spec_sha256=spec_sha,
                        defer_reason="pre_registration_superseded",
                        details={"superseded_pre_reg_id": pre_reg_id},
                    )
                return PreRegistrationOutcome(
                    ok=True, pre_reg_id=pre_reg_id, spec_sha256=spec_sha
                )

            # ── 2) 同 family 同核心身份的鏈 head ──
            cur.execute(
                """
                SELECT pre_reg_id, spec_jsonb, supersedes_pre_reg_id
                FROM research.pre_registered_hypotheses
                WHERE family_id = %s
                ORDER BY pre_reg_id
                """,
                (family_id,),
            )
            rows = cur.fetchall()
            core_sha = canonical_spec_sha256(_spec_core(spec))
            superseded_ids = {
                int(r[2]) for r in rows if r[2] is not None
            }
            core_matches = [
                (int(r[0]), dict(r[1]) if isinstance(r[1], Mapping) else {})
                for r in rows
                if canonical_spec_sha256(
                    _spec_core(r[1] if isinstance(r[1], Mapping) else {})
                )
                == core_sha
            ]
            supersedes_id: int | None = None
            if core_matches:
                heads = [m for m in core_matches if m[0] not in superseded_ids]
                if not heads:
                    # 核心命中但血緣畸形（全被 supersede）→ fail-closed。
                    return PreRegistrationOutcome(
                        ok=False,
                        spec_sha256=spec_sha,
                        defer_reason="pre_registration_superseded",
                        details={"why": "no_chain_head_for_core"},
                    )
                # 多 head 不應存在；確定性取最新（最大 pre_reg_id）為 head。
                head_id, head_spec = max(heads, key=lambda m: m[0])
                prior_ws, prior_we = _spec_window(head_spec)
                # FIX-1.2 窗單調：window_start 相等、window_end 僅向後延伸；缺窗 = 偏離。
                if (
                    new_ws is None
                    or new_we is None
                    or prior_ws is None
                    or prior_we is None
                    or new_ws != prior_ws
                    or new_we < prior_we
                ):
                    return PreRegistrationOutcome(
                        ok=False,
                        spec_sha256=spec_sha,
                        defer_reason="pre_registration_mismatch",
                        details={
                            "why": "evidence_window_not_monotonic",
                            "prior_window": [prior_ws, prior_we],
                            "new_window": [new_ws, new_we],
                            "head_pre_reg_id": head_id,
                        },
                    )
                supersedes_id = head_id

            # ── INSERT 新 row（首次或合法窗延伸）。ON CONFLICT 兜 race（並行同 spec）。──
            cur.execute(
                """
                INSERT INTO research.pre_registered_hypotheses (
                    family_id, capability_id, signal_axis, source_l2_reply_id,
                    spec_jsonb, spec_sha256, supersedes_pre_reg_id, actor_id
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (family_id, spec_sha256) DO NOTHING
                RETURNING pre_reg_id
                """,
                (
                    family_id,
                    capability_id,
                    signal_axis,
                    source_l2_reply_id,
                    json.dumps(spec, ensure_ascii=True, default=str),
                    spec_sha,
                    supersedes_id,
                    actor_id,
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                # race：他方剛插同 (family, sha) → 回讀 reuse（仍受 head 檢查保護於下次 consume）。
                cur.execute(
                    """
                    SELECT pre_reg_id FROM research.pre_registered_hypotheses
                    WHERE family_id = %s AND spec_sha256 = %s
                    LIMIT 1
                    """,
                    (family_id, spec_sha),
                )
                raced = cur.fetchone()
                if raced is None:
                    raise AlphaWealthStoreError("pre_reg_insert_conflict_unresolvable")
                conn.commit()
                return PreRegistrationOutcome(
                    ok=True, pre_reg_id=int(raced[0]), spec_sha256=spec_sha
                )
            conn.commit()
            return PreRegistrationOutcome(
                ok=True, pre_reg_id=int(inserted[0]), spec_sha256=spec_sha
            )
    except AlphaWealthStoreError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AlphaWealthStoreError(f"pre_registration_failed: {exc}") from exc


__all__ = [
    "AlphaWealthStoreError",
    "PreRegistrationOutcome",
    "DebitOutcome",
    "SPEC_EVIDENCE_WINDOW_KEY",
    "canonical_spec_sha256",
    "family_id_for",
    "deterministic_debit_id",
    "ensure_family_initialized",
    "get_family_balance",
    "record_debit",
    "record_demo_binding",
    "load_wealth_summary",
    "register_pre_registration",
]
