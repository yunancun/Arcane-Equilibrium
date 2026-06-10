#!/usr/bin/env python3
"""
Lease IPC mutating smoke — P5-SM soak 收口 S5(b) 一次性 operator 腳本。

MODULE_NOTE:
    模塊用途：P5-SM-OPTION2 step-(i) soak gate S5(b)（PA 設計
    `2026-06-10--p5sm_soak_observability_redesign.md` §2.1/§4）——soak 收口時由
    operator **手動跑一次**的 mutating IPC smoke：N≥10 輪 acquire+release（真
    Python→IPC→Rust 管線、真 GovernanceCore lease SM），全成功 + V054
    `learning.lease_transitions` audit row shape 驗證通過才 PASS。這是兩個
    mutating dispatch arm（canary 鐵則禁打的那兩個）唯一被允許的曝險方式。

    主要函數：``run_smoke``（N 輪 acquire→release + 結果統計）、
    ``verify_transition_rows``（read-only PG 驗 V054/V078 row shape）、``main``。

    硬邊界（為什麼每條都 fail-closed）：
      - **無 cron / scheduler 接線**：本腳本只能 operator 手跑（PA §5.2 原則 1/2
        ——mutating 合成流量持續化 = 持續污染審計鏈，root principle 8）。任何人把
        本腳本接進 cron 即違反 PA 設計，SCRIPT_INDEX 與本注釋雙重明文禁止。
      - **mainnet fail-closed**（仿 clean_restart_flatten.py 模式）：
        ``OPENCLAW_ALLOW_MAINNET=1`` 環境直接拒跑（exit 7）。lease SM 本身不下單，
        但 smoke 的設計授權範圍只到 demo-grade 環境（LiveDemo / demo profile 環境），
        mainnet-enabled 主機上的治理 SM 操作一律走正式授權鏈，不走 smoke。
      - **默認 dry-run**：不帶 ``--run`` 只列印計畫（0 IPC、0 mutation）。顯式
        ``--run`` + 確認（或 ``--yes``）才真打（承「默認無害」原則）。
      - **痕跡可追溯**：每筆 intent_id 帶 ``soak_smoke:`` 前綴（root principle 8
        ——audit row 可逐筆歸因到本 smoke，收口報告 / 事後清查可 grep）。
      - **TTL 30s 有界**：即使 release 失敗，lease 也在 30s 內自動過期，不留
        長壽命 dangling active lease。

    為什麼 profile=Production（而非字面「demo profile」）：GovernanceProfile 只有
    Production/Validation/Exploration 三值；**Validation/Exploration 完全繞過
    lease SM**（Rust `acquire_lease` 對 `!profile.requires_lease()` 直接回
    `LeaseId::Bypass`，只寫合成 BYPASS row），且 bypass lease 無法 release
    （SM 反查 LeaseNotFound）→ 用它跑 smoke 等於沒驗 mutating arm。S5(b) 的目的
    是驗「真 SM engagement 的 acquire/release 全鏈 + 真 audit row」，故必須
    Production profile；「demo」語義由環境層保證（mainnet guard + 引擎本身跑
    LiveDemo，row 的 engine_mode 由 Rust 寫真值）。

    依賴：governance_lease_bridge（acquire/release_via_ipc，生產 one-shot IPC
    dispatcher、fail-closed）；psycopg2（僅 row-shape 驗證，read-only session）。

    SOP（soak 全週期，operator 視角）：
      1. soak 起點：把 ``OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1`` 與
         ``OPENCLAW_SM_IPC_CANARY_ENABLED=1`` 寫入
         ``$SECRETS_ROOT/environment_files/basic_system_services.env``（**非**
         operator-env 一次性設定——前兩次 soak 就是這樣被 restart 無聲終結的），
         然後 ``bash helper_scripts/restart_all.sh``（:717 起的 env-file fallback
         會轉發進 API 進程）。
      2. soak 期間：每日看一次 6h cron log 或手跑
         ``python -m helper_scripts.db.passive_wait_healthcheck.runner --check [81] --check [82]``；
         `[82]` FAIL = 窗中斷 / 基建死，先修再續（錨點自動重置，無需人工記帳）。
      3. soak 收口（S1-S4 全綠後）：在 trade-core 跑本腳本
         ``python helper_scripts/db/lease_ipc_mutating_smoke.py --run``（先 dry-run
         看計畫）；PASS 輸出連同 `[82]` PASS 數字 + ``grep SM_DIVERGENCE api.log``
         歸因清單一起進收口報告（S5(a)/(c)）。
      4. soak 結束 / step-(iv)：從 env 檔移除兩個 flag 並 restart。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# srv root on sys.path（helper_scripts/db/ → parents[2] = srv；鏡像同目錄測試檔
# 的 sys.path 慣例，不硬編任何使用者路徑）。
_SRV_ROOT = Path(__file__).resolve().parents[2]
if str(_SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRV_ROOT))

# S5(b) 下限：N≥10（PA 設計 §4 S5(b)；CLI 可加大不可低於此數）。
MIN_OPS: int = 10

# lease TTL（秒）：有界且遠小於 Rust 上限 300s——release 失敗時 lease 30s 自動
# 過期，不留 dangling active lease（fail-safe 兜底）。
SMOKE_TTL_SECONDS: float = 30.0

# 輪間 throttle（秒）：smoke 不是壓測，不可对引擎 burst（對齊 canary 防護精神）。
INTER_OP_SLEEP_SECONDS: float = 0.5

# audit row 落庫等待上限（秒）：Rust event_consumer → PG writer 是異步鏈，
# 輪詢直到 rows 齊或超時（超時 = shape 驗證 FAIL，fail-closed）。
ROW_SETTLE_TIMEOUT_SECONDS: float = 30.0

# V078 之後的 to_state 合法值（V054 9 值 + BYPASS；shape 驗證軸）。
VALID_TO_STATES: frozenset[str] = frozenset({
    "DRAFT", "REGISTERED", "ACTIVE", "BRIDGED", "FROZEN",
    "REVOKED", "EXPIRED", "REJECTED", "CONSUMED", "BYPASS",
})
VALID_PROFILES: frozenset[str] = frozenset({"Production", "Validation", "Exploration"})


def _mainnet_guard() -> Optional[str]:
    """mainnet fail-closed 守門：OPENCLAW_ALLOW_MAINNET=1 → 回拒絕理由字串。

    為什麼 fail-closed：smoke 的授權範圍只到 demo-grade 環境；mainnet-enabled
    主機上的治理操作必須走正式授權鏈（5 閘），不可被一支 helper 腳本繞道。
    """
    if os.environ.get("OPENCLAW_ALLOW_MAINNET", "") == "1":
        return (
            "OPENCLAW_ALLOW_MAINNET=1 — mainnet-enabled 環境拒跑 mutating smoke"
            "（demo-grade only；正式 live 治理操作走 5 閘授權鏈）"
        )
    return None


def run_smoke(n_ops: int) -> dict[str, Any]:
    """跑 N 輪 acquire→release（真 IPC、真 SM），回統計 dict。

    每輪：acquire(Production, TRADE_ENTRY, 30s, intent=soak_smoke:…) → 立即
    release(consumed=True)。任一步 None/False/bypass = 該輪 fail（fail-closed
    記錄原因，不重試——smoke 要的是管線真相，不是綠燈）。
    """
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (  # noqa: PLC0415
        governance_lease_bridge as bridge,
    )

    run_tag = uuid.uuid4().hex[:12]
    results: list[dict[str, Any]] = []
    lease_ids: list[str] = []
    for i in range(n_ops):
        intent_id = f"soak_smoke:{run_tag}:{i:03d}"
        op: dict[str, Any] = {"intent_id": intent_id, "ok": False, "reason": ""}
        lease_id = bridge.acquire_lease_via_ipc(
            intent_id=intent_id,
            scope="TRADE_ENTRY",
            ttl_seconds=SMOKE_TTL_SECONDS,
            profile="Production",
            source_stage="soak_smoke",
        )
        if lease_id is None:
            op["reason"] = "acquire failed (IPC/fail-closed/auth)"
            results.append(op)
            time.sleep(INTER_OP_SLEEP_SECONDS)
            continue
        if lease_id == "bypass":
            # Production 不應 Bypass；出現即 profile/SM 接線異常，計 fail。
            op["reason"] = "unexpected Bypass outcome on Production profile"
            results.append(op)
            time.sleep(INTER_OP_SLEEP_SECONDS)
            continue
        op["lease_id"] = lease_id
        lease_ids.append(lease_id)
        released = bridge.release_lease_via_ipc(lease_id=lease_id, consumed=True)
        if not released:
            op["reason"] = f"release failed for lease_id={lease_id}"
            results.append(op)
            time.sleep(INTER_OP_SLEEP_SECONDS)
            continue
        op["ok"] = True
        results.append(op)
        time.sleep(INTER_OP_SLEEP_SECONDS)

    ok_count = sum(1 for r in results if r["ok"])
    return {
        "run_tag": run_tag,
        "ops": results,
        "ok_count": ok_count,
        "total": n_ops,
        "all_ok": ok_count == n_ops,
        "lease_ids": lease_ids,
    }


def _connect_readonly():
    """read-only psycopg2 連線（env 慣例鏡像 passive_wait_healthcheck/db.py）。

    為什麼 readonly session：本腳本對 PG 只做 shape 驗證 SELECT；硬 read-only
    讓任何未來誤加的寫入在 PG 層直接被拒（defense-in-depth）。
    """
    import psycopg2  # noqa: PLC0415

    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER', '')}"
        f":{os.environ.get('POSTGRES_PASSWORD', '')}"
        f"@{os.environ.get('POSTGRES_HOST', '127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT', '5432')}"
        f"/{os.environ.get('POSTGRES_DB', '')}"
    )
    conn = psycopg2.connect(
        dsn,
        application_name="openclaw_lease_ipc_mutating_smoke",
        options="-c statement_timeout=30000 -c lock_timeout=5000",
    )
    conn.set_session(readonly=True)
    return conn


def verify_transition_rows(lease_ids: list[str]) -> tuple[bool, str]:
    """驗 V054 `learning.lease_transitions` 的 smoke rows shape（S5(b) 後半）。

    輪詢至 settle（Rust→PG 異步鏈）後逐 row 斷言：
      - NOT NULL 欄全在（transition_id/lease_id/to_state/event/initiator/
        profile/engine_mode/ts_ms）。
      - to_state ∈ V078 白名單、profile ∈ 3 值 CHECK 集。
      - 每個 smoke lease 至少各 1 筆 ACTIVE 與 1 筆 CONSUMED（acquire 與
        release 兩個 mutating arm 都真的留下 audit 痕跡）。
    engine_mode 只驗非空字串不釘值：Live 與 LiveDemo 同寫 'live_demo'
    （2026-04-16 既有語義），值無法區分環境——環境圍欄由 mainnet guard 負責。
    """
    if not lease_ids:
        return False, "no lease_ids captured (all acquires failed?)"
    deadline = time.monotonic() + ROW_SETTLE_TIMEOUT_SECONDS
    rows: list[tuple] = []
    with _connect_readonly() as conn:
        while True:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT lease_id, transition_id, to_state, event, initiator, "
                    "       profile, engine_mode, ts_ms "
                    "FROM learning.lease_transitions WHERE lease_id = ANY(%s)",
                    (lease_ids,),
                )
                rows = cur.fetchall() or []
            conn.rollback()  # 唯讀查詢後釋放 tx，不留 idle-in-transaction
            covered = {r[0] for r in rows}
            states_by_lease = {
                lid: {r[2] for r in rows if r[0] == lid} for lid in covered
            }
            settled = all(
                lid in covered
                and "ACTIVE" in states_by_lease[lid]
                and "CONSUMED" in states_by_lease[lid]
                for lid in lease_ids
            )
            if settled or time.monotonic() >= deadline:
                break
            time.sleep(2.0)

    problems: list[str] = []
    covered = {r[0] for r in rows}
    missing = [lid for lid in lease_ids if lid not in covered]
    if missing:
        problems.append(f"{len(missing)} lease(s) have no transition rows: {missing[:3]}…")
    for r in rows:
        lid, tid, to_state, event, initiator, profile, engine_mode, ts_ms = r
        for name, val in (
            ("transition_id", tid), ("to_state", to_state), ("event", event),
            ("initiator", initiator), ("profile", profile),
            ("engine_mode", engine_mode), ("ts_ms", ts_ms),
        ):
            if val is None or (isinstance(val, str) and not val):
                problems.append(f"lease {lid}: column {name} NULL/empty")
        if to_state not in VALID_TO_STATES:
            problems.append(f"lease {lid}: to_state {to_state!r} outside V078 CHECK set")
        if profile not in VALID_PROFILES:
            problems.append(f"lease {lid}: profile {profile!r} outside V054 CHECK set")
    for lid in lease_ids:
        states = {r[2] for r in rows if r[0] == lid}
        if "ACTIVE" not in states:
            problems.append(f"lease {lid}: no ACTIVE transition (acquire not audited)")
        if "CONSUMED" not in states:
            problems.append(f"lease {lid}: no CONSUMED transition (release not audited)")

    if problems:
        return False, "; ".join(problems[:10])
    return True, (
        f"{len(rows)} transition rows for {len(lease_ids)} smoke leases — "
        f"shape OK (NOT NULL + to_state/profile CHECK sets + ACTIVE/CONSUMED 雙痕跡)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "P5-SM soak S5(b) mutating IPC smoke (operator one-shot; "
            "default dry-run; NEVER wire into cron)"
        ),
    )
    ap.add_argument("--run", action="store_true",
                    help="真打 IPC（默認 dry-run 只列印計畫）")
    ap.add_argument("--yes", action="store_true", help="跳過互動確認")
    ap.add_argument("--ops", type=int, default=MIN_OPS,
                    help=f"acquire+release 輪數（下限 {MIN_OPS}，S5(b) floor）")
    ap.add_argument("--skip-db-verify", action="store_true",
                    help="跳過 PG row-shape 驗證（無 PG 環境時；結果標 PARTIAL）")
    args = ap.parse_args()

    guard_reason = _mainnet_guard()
    if guard_reason is not None:
        print(f"[REFUSED] {guard_reason}", file=sys.stderr)
        return 7
    if args.ops < MIN_OPS:
        print(f"[ERR] --ops {args.ops} < S5(b) floor {MIN_OPS}", file=sys.stderr)
        return 2

    plan = (
        f"plan: {args.ops} × (acquire[Production/TRADE_ENTRY/ttl={SMOKE_TTL_SECONDS:.0f}s]"
        f" → release[Consumed])，intent 前綴 soak_smoke:，輪間 {INTER_OP_SLEEP_SECONDS}s，"
        f"然後 read-only 驗 lease_transitions row shape"
    )
    if not args.run:
        print(f"[DRY-RUN] {plan}")
        print("[DRY-RUN] 加 --run 真打（operator 一次性；不可接 cron）")
        return 0
    if not args.yes:
        reply = input(f"{plan}\n確認執行 mutating smoke? [y/N] ").strip().lower()
        if reply != "y":
            print("aborted")
            return 0

    try:
        smoke = run_smoke(args.ops)
    except Exception as exc:  # noqa: BLE001 — 環境/匯入失敗 → exit 2 與報告
        print(f"[ERR] smoke run failed: {exc}", file=sys.stderr)
        return 2

    print(f"run_tag={smoke['run_tag']} ops={smoke['ok_count']}/{smoke['total']} ok")
    for op in smoke["ops"]:
        mark = "OK " if op["ok"] else "FAIL"
        print(f"  [{mark}] {op['intent_id']} {op.get('lease_id', '')} {op['reason']}")

    if not smoke["all_ok"]:
        print("[FAIL] S5(b) 要求全數成功；任何一輪失敗即收口未過", file=sys.stderr)
        return 1

    if args.skip_db_verify:
        print("[PARTIAL] ops 全成功；row-shape 驗證被 --skip-db-verify 跳過 — "
              "請在有 PG 的主機補跑驗證後才算 S5(b) PASS")
        return 1

    try:
        shape_ok, shape_msg = verify_transition_rows(smoke["lease_ids"])
    except Exception as exc:  # noqa: BLE001 — PG 不可用 → fail-closed 非綠
        print(f"[FAIL] row-shape verify error (fail-closed): {exc}", file=sys.stderr)
        return 1
    print(f"[{'PASS' if shape_ok else 'FAIL'}] row shape: {shape_msg}")
    return 0 if shape_ok else 1


if __name__ == "__main__":
    sys.exit(main())
