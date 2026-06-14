#!/usr/bin/env python3
"""check_cost_gate_double_deduct — PROFIT-1 雙重扣成本 latent issue 預防性哨兵。

MODULE_NOTE:
  背景：PROFIT-1 冷酷審計裁定 cost_gate 對 runtime-derived 正 edge cell 存在
  「雙重扣成本」效應——`runtime_bps` 已是扣成本後的淨值，cost_gate 又用
  `threshold_bps = fee_bps / clamp(win_rate, floor, 1.0) × safety_multiplier`
  二次扣成本門檻比較，把期望為正的單再拒一次。replay 裁 NO-FIX（目前 dormant：
  active 路徑要求 `validation_passed==true`，而生產 edge_estimates.json 目前無
  validated-positive cell，故此誤拒尚未發生）。

  風險窗：parallel session 正建 explore-gate；一旦 producer 把
  `validation_passed=true` 寫到任一正 cell（`runtime_bps>0`），此 dormant
  誤拒立即轉 active——validated-positive 但 `runtime_bps < threshold_bps`
  的 cell 會被 cost_gate_moderate（demo）/ cost_gate_live（live）拒掉。

  本 healthcheck 不改 gate 邏輯本身（gates.rs 是權威，replay 已裁 NO-FIX），
  只把此 latent issue 轉為「可監測」：對每個 edge cell，若
    validation_passed==true AND runtime_bps>0 AND runtime_bps < threshold_bps
  則該 cell 正/即將被 cost_gate 雙重扣成本誤拒。count>0 → WARN。

  SSOT 對齊（與 Rust `intent_processor/gates.rs` L42-45/215-218/326-329 一致）：
    fee_bps        = 2 × (fee_rate + slippage) × 1e4
    wr             = clamp(cell.win_rate, cost_gate_win_rate_floor, 1.0)
    threshold_bps  = fee_bps / wr × cost_gate_safety_multiplier
  關鍵：threshold 是 **per-cell**（用該 cell 的 win_rate clamp 到 [floor,1.0]），
  不是 per-env 標量。gates.rs 用 `cell.win_rate.clamp(floor,1.0)`；只有當 cell
  win_rate 恰落在 floor 以下時門檻才退化成 fee_bps/floor×safety。用固定 floor
  會恆 >= 真門檻（floor<=clamp 結果）→ 把 gate 實際會放行的 cell 也標誤拒
  （false positive）。故本 check 逐 cell 取 win_rate 算門檻，與 gate 行為對齊。
  三環境（demo / live / paper）各讀 `risk_config_<env>.toml` 取得 fee_bps /
  floor / safety；cell 的 runtime_bps / validation_passed / win_rate 讀
  `settings/edge_estimates.json`（與 `edge_estimates.rs` L158-168 反序列化語義
  對齊：runtime_bps key 優先、缺則 shrunk_bps fallback；win_rate_shrunk 優先、
  缺則 win_rate、皆缺則 0.5，最後 clamp 到 [0,1]）。

  偏差說明（spec vs 現實，本 check 相對 gate 的全部簡化，方向皆 over-report）：
    1. fee_rate：PA 任務指明 fee_rate / slippage「值取 risk_config_<env>.toml
       [slippage] 段」，但該段實際只含 slippage 的 `default_rate`，並無 fee_rate
       欄位——gates.rs 的 fee_rate 是 runtime 經 Bybit API 取得的 per-symbol taker
       費率，非 TOML 靜態值。本 check 取同一 TOML `[market_gate].max_taker_fee_bps`
       （per-env taker 費率上限，/1e4 轉小數）作 fee_rate → fee 偏大 → 門檻偏大 →
       命中更多 cell（保守 over-report）。
    2. win_rate：已逐 cell 對齊（見上），非簡化。
    3. n_trades / fresh / from_runtime_field：gates.rs 在進門檻比較分支前還有前置：
       demo 路徑 `cell.n_trades < cost_gate_min_n_trades_for_block` 短路到探索模式
       （低 n cell 在 demo 從不被門檻拒，L179-192）；demo+live 門檻分支前需
       `fresh && from_runtime_field && validation_passed`（L200/L308）。本 check 謂詞
       只有 validation_passed AND runtime_bps>0 AND runtime_bps<threshold，**省略**
       n_trades / fresh / from_runtime_field 三項前置——故謂詞比 gate 寬鬆，可能把
       「gate 因 low-n/stale 而走探索放行」的 cell 也標誤拒（保守 over-report）。
    全部偏差方向一致＝over-report（fail-safe 不漏報），代價是可能早報；本 check
    定位為 latent issue 早期預警非精準計數，over-report 可接受。

硬邊界：
  - 純 read-only（讀 JSON + TOML，0 寫入、0 PG、0 IPC、0 mutation）。
  - 跨平台（無 Linux guard）：Mac dev 可直接跑自測；不依賴 GNU stat / PG。
  - fail-soft：任一 config / JSON 取不到或解析失敗 → INSUFFICIENT_SAMPLE（SKIP），
    不 FAIL（無資料不可推論 latent issue 是否存在；製造 FAIL 噪音違 fail-soft）。

CLI:
  python3 check_cost_gate_double_deduct.py [--status] [--text] [--write-file PATH]

Exit codes（對齊 [80] / _common.py 慣例）:
  0 = PASS / INSUFFICIENT_SAMPLE（無 config / 無 validated-positive cell）
  1 = WARN / FAIL（≥1 cell 落入雙重扣成本誤拒窗）
  2 = environment error（保留；本 check 純 filesystem 一般不觸發）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 允許 standalone script + module 同時被呼叫（對齊 check_pg_dump_freshness.py pattern）
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402
    EXIT_FAIL,
    EXIT_PASS,
    VERDICT_FAIL,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_PASS,
    VERDICT_WARN,
    configure_logging,
    emit_result,
    severity_max,
)

# stdlib tomllib (3.11+)；passive_wait_healthcheck venv 為 3.12，可用。
import tomllib  # noqa: E402

# ───────────────────────────────────────────────────────────────────────────
# 三環境 → risk_config TOML 檔名映射（與 settings/risk_control_rules/ 對齊）。
# ───────────────────────────────────────────────────────────────────────────
ENVIRONMENTS: tuple[str, ...] = ("demo", "live", "paper")


def _resolve_srv_root() -> Path:
    """解析 srv root。優先 OPENCLAW_BASE_DIR；否則由本檔位置上推。

    本檔在 ``srv/helper_scripts/canary/healthchecks/`` → parents[3] = srv。
    對齊 [80] wrapper 的 OPENCLAW_BASE_DIR 慣例，禁硬編 user path（跨平台紅線）。
    """
    env_root = os.environ.get("OPENCLAW_BASE_DIR")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[3]


def _edge_estimates_path(srv_root: Path) -> Path:
    return srv_root / "settings" / "edge_estimates.json"


def _risk_config_path(srv_root: Path, env: str) -> Path:
    return srv_root / "settings" / "risk_control_rules" / f"risk_config_{env}.toml"


def _load_toml(path: Path) -> dict | None:
    """讀 TOML；不存在 / 解析失敗 → None（caller 判 INSUFFICIENT_SAMPLE）。"""
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _load_edge_estimates(path: Path) -> dict | None:
    """讀 edge_estimates.json；不存在 / 解析失敗 / 非 object → None。"""
    try:
        with path.open("rb") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


class GateParams:
    """單一環境的 cost_gate 門檻參數（per-env 常數，per-cell 門檻另算）。

    threshold 是 per-cell 的（依 cell.win_rate clamp），故這裡只存 per-env 不變
    的 fee_bps / win_rate_floor / safety_multiplier；真門檻由
    ``cell_threshold_bps`` 逐 cell 計算（與 gates.rs `cell.win_rate.clamp(...)` 對齊）。
    """

    __slots__ = ("fee_bps", "win_rate_floor", "safety_multiplier")

    def __init__(self, fee_bps: float, win_rate_floor: float, safety_multiplier: float):
        self.fee_bps = fee_bps
        self.win_rate_floor = win_rate_floor
        self.safety_multiplier = safety_multiplier

    def cell_threshold_bps(self, cell_win_rate: float) -> float:
        """以該 cell 的 win_rate 算門檻（與 gates.rs L42-45/215-218/326-329 一致）。

        wr = clamp(cell_win_rate, win_rate_floor, 1.0)；threshold = fee_bps/wr×safety。
        """
        wr = min(max(cell_win_rate, self.win_rate_floor), 1.0)
        return self.fee_bps / wr * self.safety_multiplier


def compute_gate_params(risk_cfg: dict) -> GateParams | None:
    """由單一 risk_config TOML 取得 per-env 門檻參數（fee_bps / floor / safety）。

    fee_bps    = 2 × (fee_rate + slippage) × 1e4
    fee_rate   = [market_gate].max_taker_fee_bps / 1e4（偏差說明見 MODULE_NOTE）。
    slippage   = [slippage].default_rate。
    缺任一欄 / 非數值 / win_rate_floor 非正 → None（caller 判 INSUFFICIENT_SAMPLE）。
    真門檻是 per-cell（見 GateParams.cell_threshold_bps），不在此算標量門檻。
    """
    slippage_section = risk_cfg.get("slippage")
    market_section = risk_cfg.get("market_gate")
    if not isinstance(slippage_section, dict) or not isinstance(market_section, dict):
        return None

    default_rate = slippage_section.get("default_rate")
    win_rate_floor = slippage_section.get("cost_gate_win_rate_floor")
    safety_multiplier = slippage_section.get("cost_gate_safety_multiplier")
    max_taker_fee_bps = market_section.get("max_taker_fee_bps")

    for v in (default_rate, win_rate_floor, safety_multiplier, max_taker_fee_bps):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
    # win_rate_floor 必須為正 → 否則 threshold 公式除零 / 負值無意義。
    if win_rate_floor <= 0.0:
        return None

    fee_rate = float(max_taker_fee_bps) / 1e4
    slippage = float(default_rate)
    fee_bps = 2.0 * (fee_rate + slippage) * 1e4
    return GateParams(fee_bps, float(win_rate_floor), float(safety_multiplier))


def _cell_runtime_bps(cell: dict) -> float | None:
    """取 cell 的 runtime edge bps（與 edge_estimates.rs 反序列化語義對齊）。

    優先 runtime_bps key（未驗證正 edge 已被 producer 歸零）；缺則 fallback
    shrunk_bps。兩者皆缺 / 非數值 → None（該 cell 不參與評估）。
    """
    for key in ("runtime_bps", "shrunk_bps"):
        v = cell.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def _cell_win_rate(cell: dict) -> float:
    """取 cell 的 win_rate（與 edge_estimates.rs L163-168 反序列化語義對齊）。

    win_rate_shrunk 優先、缺則 win_rate、皆缺則 0.5；最後 clamp 到 [0,1]
    （gates.rs 用的 cell.win_rate 已是此 clamp 後值）。bool 視為缺（int 子類陷阱）。
    """
    for key in ("win_rate_shrunk", "win_rate"):
        v = cell.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return min(max(float(v), 0.0), 1.0)
    return 0.5


def scan_double_deduct_cells(
    edge_estimates: dict,
    gate: GateParams,
) -> list[dict]:
    """掃出落入雙重扣成本誤拒窗的 cell（門檻 per-cell，依 cell.win_rate）。

    判據：validation_passed==true AND runtime_bps>0 AND
          runtime_bps < cell_threshold_bps（用該 cell 的 win_rate clamp 算門檻）。
    回傳每個命中 cell 的摘要 dict（key / runtime_bps / win_rate / threshold_bps）。
    `_meta` 與非 object value 跳過（與 edge_estimates.rs 只解析 object cell 對齊）。
    """
    hits: list[dict] = []
    for key, cell in edge_estimates.items():
        if key == "_meta" or not isinstance(cell, dict):
            continue
        validation_passed = cell.get("validation_passed")
        if validation_passed is not True:
            continue
        runtime_bps = _cell_runtime_bps(cell)
        if runtime_bps is None or runtime_bps <= 0.0:
            continue
        win_rate = _cell_win_rate(cell)
        threshold_bps = gate.cell_threshold_bps(win_rate)
        if runtime_bps < threshold_bps:
            hits.append(
                {
                    "cell": key,
                    "runtime_bps": runtime_bps,
                    "win_rate": win_rate,
                    "threshold_bps": threshold_bps,
                }
            )
    return hits


def _check_one_env(env: str, srv_root: Path, edge_estimates: dict | None) -> tuple[str, str]:
    """對單一環境跑門檻計算 + cell 掃描，回 (verdict, note)。"""
    risk_path = _risk_config_path(srv_root, env)
    risk_cfg = _load_toml(risk_path)
    if risk_cfg is None:
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            f"{env}: risk_config_{env}.toml 不可讀 / 解析失敗 → SKIP",
        )

    gate = compute_gate_params(risk_cfg)
    if gate is None:
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            f"{env}: [slippage]/[market_gate] 必要欄位缺失 → SKIP",
        )

    # 門檻是 per-cell（依 cell.win_rate）；note 報 floor 上界供 operator 參考。
    floor_threshold = gate.cell_threshold_bps(0.0)
    if edge_estimates is None:
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            f"{env}: edge_estimates.json 不可讀 → SKIP "
            f"(fee_bps={gate.fee_bps:.2f}, floor-threshold={floor_threshold:.2f}bps)",
        )

    hits = scan_double_deduct_cells(edge_estimates, gate)
    if not hits:
        return (
            VERDICT_PASS,
            f"{env}: 0 cell 落入雙重扣成本窗 "
            f"(fee_bps={gate.fee_bps:.2f}, floor-threshold={floor_threshold:.2f}bps)",
        )

    sample = ", ".join(
        f"{h['cell']}({h['runtime_bps']:.2f}<{h['threshold_bps']:.2f}@wr{h['win_rate']:.2f})"
        for h in hits[:5]
    )
    more = "" if len(hits) <= 5 else f" +{len(hits) - 5} more"
    return (
        VERDICT_WARN,
        f"{env}: {len(hits)} cell 被 cost_gate 雙重扣成本誤拒（validated-positive "
        f"runtime_bps < per-cell threshold，依 cell.win_rate）: {sample}{more}",
    )


def run() -> dict:
    """三環境逐一評估並合併 verdict（任一 env 最嚴者為整體 verdict）。"""
    srv_root = _resolve_srv_root()
    edge_path = _edge_estimates_path(srv_root)
    edge_estimates = _load_edge_estimates(edge_path)

    checks: list[tuple[str, str, str]] = []  # (env, verdict, note)
    overall = VERDICT_PASS
    for env in ENVIRONMENTS:
        v, m = _check_one_env(env, srv_root, edge_estimates)
        checks.append((env, v, m))
        overall = severity_max(overall, v)

    return {
        "metric": "cost_gate_double_deduct",
        "check_id": "[cost_gate_double_deduct]",
        "namespace": "canary",
        "spec": (
            "PROFIT-1 cost_gate double-cost-deduct latent issue preventive sentinel "
            "(aligns rust/openclaw_engine/src/intent_processor/gates.rs threshold formula)"
        ),
        "paths": {
            "edge_estimates": str(edge_path),
            "srv_root": str(srv_root),
        },
        "checks": [
            {"id": env, "verdict": v, "note": m}
            for env, v, m in checks
        ],
        "verdict": overall,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_cost_gate_double_deduct",
        description=(
            "PROFIT-1 cost_gate 雙重扣成本 latent issue 預防性哨兵：偵測 "
            "validation_passed AND runtime_bps>0 AND runtime_bps<threshold 的 cell"
        ),
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help=(
            "Print verdict + per-env JSON; exit 0 if PASS/INSUFFICIENT_SAMPLE, "
            "1 if WARN/FAIL. Default mode; flag preserved for wrapper API contract."
        ),
    )
    parser.add_argument(
        "--write-file",
        type=str,
        default=None,
        help="Optional JSON artifact write path.",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Human-readable text output instead of JSON.",
    )
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = _parse_args()
    result = run()
    emit_result(result, write_file=args.write_file, text_mode=args.text)
    if result["verdict"] in (VERDICT_FAIL, VERDICT_WARN):
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
