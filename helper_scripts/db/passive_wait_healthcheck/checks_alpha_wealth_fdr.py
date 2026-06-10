"""P4 online-FDR α-wealth / pre-registration / V132 哨兵 — `[82]`-`[86]`。

MODULE_NOTE
模塊用途：L2 Mesh P4 的五軸帳本完整性哨兵（V137 research.alpha_wealth_ledger
  + research.pre_registered_hypotheses + V132 hidden_oos_state_registry）：
    [82] alpha_wealth_family_cardinality — family 數 vs MIT 4a 量化門檻
         N_fam ≤ 1/γ = 10（超限 = 全域 mFDR ≤ α_target 詮釋不再成立）。
    [83] alpha_wealth_orphan_refund — refund 無對應 debit（MIT N-3
         wealth-inflation 向量；DB CHECK 無法跨 row，本哨兵補位）。
    [84] alpha_wealth_refund_amount_mismatch — refund.amount ≠ φ·|debit.amount|
         （MIT N-3 第二臂；φ=1.0 M1 ENDORSED）。
    [85] pre_reg_cross_family_duplicate_spec — 同 spec_sha256 跨 family 重註冊
         計數（MIT 4b：帳務 sound、觀測級即可，WARN 不 FAIL）。
    [86] hidden_oos_state_regression — V132 sealed 列被回寫指紋
         （QC QN-1：consumed/opened→sealed 回退偵測，best-effort）。
主要函數：check_82_* ~ check_86_*（`(cur) -> (status, msg)` 與既有 checks_*
  同契約）。
依賴：psycopg2 cursor（runner 注入）；0 其他依賴。
硬邊界：全部唯讀 SELECT；V137 表不存在 → 一律 PASS-skip 不 FAIL
  （pre-deploy 不 false-FAIL，部署後自動轉真檢查——checks_replay_maintenance
  graceful-absent 同款慣例）。

N-7 語義註記（MIT；勿改成 discovery 監測）：P4 初期 discovery ≈ 0 是設計後果
（threshold ≥ 0.9995），pipeline 健康訊號 = conducted tests（debit 列）在長，
不是 refund 在長。本模組五軸全部監測「帳本完整性」而非「discovery 產出」。
"""

from __future__ import annotations

from typing import Any

# MIT 4a：N_fam ≤ 1/γ = 10——超過即全域 mFDR_{η=1} ≤ α_target 推導失效，
# 退化為 mFDR_{η=N_fam} 語義；超限 alert + operator 裁決。
MAX_FAMILIES = 10

# M1 ENDORSED φ=1.0（exactly self-funding）。本檔刻意不 import
# learning_engine（healthcheck 自含、不依賴 A 線部署狀態）；若未來 φ 改值，
# [84] 的 SQL 等式（r.amount + d.amount = 0 ⟺ refund = 1.0·|debit|）須同步。
PHI_REFUND_EXPECTED = 1.0


def _rollback_quietly(cur: Any) -> None:
    """前一 check 的 aborted txn 不應汙染本 check（既有 checks_* 慣例）。"""
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 - rollback 失敗讓後續 execute 自然炸出
        pass


def _v137_deployed(cur: Any) -> bool:
    cur.execute(
        "SELECT to_regclass('research.alpha_wealth_ledger') IS NOT NULL"
        " AND to_regclass('research.pre_registered_hypotheses') IS NOT NULL"
    )
    row = cur.fetchone()
    return bool(row and row[0])


_SKIP_MSG = "SKIP (V137 not deployed): research FDR tables absent; check is dormant"


def check_82_alpha_wealth_family_cardinality(cur) -> tuple[str, str]:
    """[82] family 基數 vs MIT 4a 門檻（N_fam ≤ 10）。

    family_init 是每 family 恰一筆（awl_one_init_per_family），count = 真 family 數。
    > 10 → FAIL（全域 bound 詮釋破裂，operator 裁決）；== 10 → WARN（貼邊界）。
    """
    _rollback_quietly(cur)
    if not _v137_deployed(cur):
        return ("PASS", _SKIP_MSG)
    cur.execute(
        "SELECT count(*) FROM research.alpha_wealth_ledger"
        " WHERE event_type = 'family_init'"
    )
    n_fam = int(cur.fetchone()[0])
    msg = f"families={n_fam} bound={MAX_FAMILIES} (MIT 4a: N_fam<=1/gamma)"
    if n_fam > MAX_FAMILIES:
        return ("FAIL", msg + " — global mFDR<=alpha_target interpretation broken")
    if n_fam == MAX_FAMILIES:
        return ("WARN", msg + " — at boundary")
    return ("PASS", msg)


def check_83_alpha_wealth_orphan_refund(cur) -> tuple[str, str]:
    """[83] orphan refund（refund 列無對應 debit 列）。

    為什麼是 FAIL：refund 是 +amount 事件，無對應 debit = 憑空灌 wealth
    （MIT N-3 wealth-inflation 向量）。V137 CHECK 無法跨 row 驗，append-only
    下這指紋一旦出現必為 writer bug / 越權 INSERT，須人工 operator_adjustment
    對沖 + 追因。
    """
    _rollback_quietly(cur)
    if not _v137_deployed(cur):
        return ("PASS", _SKIP_MSG)
    cur.execute(
        """
        SELECT count(*)
        FROM research.alpha_wealth_ledger r
        WHERE r.event_type = 'refund'
          AND NOT EXISTS (
              SELECT 1 FROM research.alpha_wealth_ledger d
              WHERE d.debit_id = r.debit_id AND d.event_type = 'debit'
          )
        """
    )
    orphans = int(cur.fetchone()[0])
    if orphans > 0:
        return ("FAIL", f"orphan_refunds={orphans} (wealth-inflation vector, MIT N-3)")
    return ("PASS", "orphan_refunds=0")


def check_84_alpha_wealth_refund_amount_mismatch(cur) -> tuple[str, str]:
    """[84] refund.amount ≠ φ·|debit.amount|（φ=1.0）。

    NUMERIC 算術精確：φ=1.0 下 refund = |debit| ⟺ r.amount + d.amount = 0
    （debit 存負額）。任何 mismatch = reconciler N-3 斷言被繞過 / 手寫壞帳。
    """
    _rollback_quietly(cur)
    if not _v137_deployed(cur):
        return ("PASS", _SKIP_MSG)
    cur.execute(
        """
        SELECT count(*)
        FROM research.alpha_wealth_ledger r
        JOIN research.alpha_wealth_ledger d
          ON d.debit_id = r.debit_id AND d.event_type = 'debit'
        WHERE r.event_type = 'refund'
          AND r.amount + d.amount <> 0
        """
    )
    mismatches = int(cur.fetchone()[0])
    if mismatches > 0:
        return (
            "FAIL",
            f"refund_amount_mismatches={mismatches} "
            f"(phi={PHI_REFUND_EXPECTED} proportionality violated, MIT N-3)",
        )
    return ("PASS", f"refund_amount_mismatches=0 (phi={PHI_REFUND_EXPECTED})")


def check_85_pre_reg_cross_family_duplicate_spec(cur) -> tuple[str, str]:
    """[85] 跨 family 重複 spec_sha256（觀測級，MIT 4b）。

    同 spec 換 primary_axis 在兩 family 各註冊 = 各付各的 α，帳務 sound、
    全域 bound 不破——但屬「同假設雙重機會」，觀測即可：WARN 不 FAIL、
    不 DB 禁止（prh_family_spec_uk 僅鎖同 family）。
    """
    _rollback_quietly(cur)
    if not _v137_deployed(cur):
        return ("PASS", _SKIP_MSG)
    cur.execute(
        """
        SELECT count(*) FROM (
            SELECT spec_sha256
            FROM research.pre_registered_hypotheses
            GROUP BY spec_sha256
            HAVING count(DISTINCT family_id) > 1
        ) dup
        """
    )
    dups = int(cur.fetchone()[0])
    if dups > 0:
        return (
            "WARN",
            f"cross_family_duplicate_specs={dups} "
            "(double-chance same hypothesis; accounting sound, observe only)",
        )
    return ("PASS", "cross_family_duplicate_specs=0")


def check_86_hidden_oos_state_regression(cur) -> tuple[str, str]:
    """[86] V132 state 回退指紋（consumed/opened → sealed，QC QN-1）。

    偵測語義（best-effort，誠實標界）：
      - 'sealed' 是 INSERT 初態（registry 寫入鏈硬寫 'sealed',0,FALSE,FALSE,FALSE，
        created_at = updated_at 同 txn DEFAULT NOW()）。合法轉移離開 sealed
        （opened/consumed），永不回來——故 state='sealed' 而 updated_at 晚於
        created_at = 該列被回寫過 = 回退指紋。
      - V132 state_flags_chk 已擋「單欄 state 回寫」（flags 不一致即拒）；
        本哨兵抓的是「連 flags 一起重寫但沒偽造 updated_at」的中間檔。
      - 蓄意連 updated_at 一併偽造的多欄重寫在表內無痕（QC 已認此盲點），
        非本哨兵能力範圍——append-only ledger 化是治本（不在 P4 範圍）。
    V132 表缺 → PASS-skip（與 V137 同款部署順序容忍）。
    """
    _rollback_quietly(cur)
    cur.execute(
        "SELECT to_regclass('learning.hidden_oos_state_registry') IS NOT NULL"
    )
    row = cur.fetchone()
    if not (row and row[0]):
        return ("PASS", "SKIP (V132 not deployed): hidden_oos_state_registry absent")
    cur.execute(
        """
        SELECT count(*)
        FROM learning.hidden_oos_state_registry
        WHERE state = 'sealed'
          AND updated_at > created_at + interval '1 second'
        """
    )
    regressed = int(cur.fetchone()[0])
    if regressed > 0:
        return (
            "FAIL",
            f"sealed_rows_with_post_insert_updates={regressed} "
            "(state regression fingerprint, QC QN-1; sealed must be immutable-by-path)",
        )
    return ("PASS", "sealed_rows_with_post_insert_updates=0")
