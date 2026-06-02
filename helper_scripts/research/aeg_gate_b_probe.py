#!/usr/bin/env python3
"""Gate-B 隔離 listing-capture 探針 — entry 組裝器。

MODULE_NOTE:
  模塊用途：把 gate_b_rest（SoT 輪詢 + phase 狀態機）、gate_b_ws（獨立 public WS
    捕捉 + capture_lag + markout）、gate_b_artifact（落地 + manifest + verdict）三層
    組裝成一個可獨立執行的探針進程。WS 在背景執行緒跑 event loop；主執行緒以固定
    間隔輪詢 REST，把當前 PreLaunch 候選同步給 WS 動態訂閱、把 launchTime 餵入
    capture_lag 基準；到 ``--duration`` 結束後封裝 manifest / summary / verdict /
    parquet 鏡像。
  主要類/函數：``GateBProbe`` / ``run_probe`` / ``main``。
  依賴：本目錄三 module + Python 標準庫（argparse / threading）。WS/parquet 的
    第三方套件（websocket-client / duckdb）由各 module 延遲 import。
  硬邊界（R-0 隔離紅線）：
    - 絕不 import 任何生產模組（openclaw_engine / SymbolRegistry / KlineManager /
      governance_hub / production bybit_rest_client / scanner / strategy / intent /
      decision_lease）。本 entry 只 import 同目錄三 gate_b_* module。
    - 零 auth / 零 order / 零 DB write。
    - **本檔不在匯入時啟動任何連線或副作用**：只有 ``main()`` / ``run_probe()`` 被
      顯式呼叫才連 WS、打 REST。匯入本 module（import smoke / 隔離測試）零副作用。
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# 同目錄三層 module。為什麼用相對於本檔的絕對 import：探針可被當 script 直接跑
# （python helper_scripts/research/aeg_gate_b_probe.py），也可被測試以 module 匯入；
# 把本目錄加進 sys.path 後以模組名匯入，維持兩種用法皆可且不 import 生產套件。
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import gate_b_artifact as artifact  # noqa: E402
import gate_b_rest as rest  # noqa: E402
import gate_b_ws as ws  # noqa: E402


class GateBProbe:
    """組裝 REST + WS + artifact，跑一次有限時長的捕捉。"""

    def __init__(
        self,
        *,
        run_id: Optional[str] = None,
        artifact_root: Optional[Path] = None,
    ) -> None:
        self.run_id = run_id or f"gate_b_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.writer = artifact.GateBArtifactWriter(
            self.run_id, artifact_root=artifact_root
        )
        # REST 層：rest_phase_poll.jsonl 的 writer。
        self.rest_probe = rest.GateBRestProbe(jsonl_writer=self.writer.writer_for("rest"))
        # WS 層：kline/publictrade/control/capture_lag/markout 各 channel writer。
        self.ws_probe = ws.GateBWsProbe(jsonl_writers=self.writer.writers())
        # 收集 transition / capture_lag 供 summary（同時已落 JSONL）。
        self._transitions: list[dict[str, Any]] = []
        self._capture_lags: list[dict[str, Any]] = []
        self._pipeline_error: Optional[str] = None

    def _on_capture_lag_row(self, row: dict[str, Any]) -> None:
        # capture_lag writer 已寫檔；此處同步收進記憶體供 summary。
        self._capture_lags.append(row)

    def run(self, *, duration_seconds: float, dry_run: bool = False) -> dict[str, Any]:
        """跑探針：WS 背景 loop + 主執行緒 REST 輪詢，到時收尾。

        dry_run=True：不連 WS、不打 REST，只建立 artifact 目錄並寫一份
        INCONCLUSIVE verdict + manifest（供結構驗證 / smoke，不產生真實樣本）。
        """
        if dry_run:
            return self._finalize(dry_run=True)

        # capture_lag channel 包一層：既寫檔又收進記憶體。
        base_capture_writer = self.writer.writer_for("capture_lag")

        def _capture_writer(row: dict[str, Any]) -> None:
            base_capture_writer(row)
            self._on_capture_lag_row(row)

        # 重綁 WS 的 capture_lag writer（其餘 channel 維持原 writer）。
        ws_writers = self.writer.writers()
        ws_writers["capture_lag"] = _capture_writer
        self.ws_probe = ws.GateBWsProbe(jsonl_writers=ws_writers)

        stop = threading.Event()
        ws_thread = threading.Thread(
            target=self._run_ws_loop, args=(stop,), name="gate_b_ws", daemon=True
        )
        ws_thread.start()

        deadline = time.monotonic() + duration_seconds
        policy = rest.current_rest_poll_policy()
        try:
            while time.monotonic() < deadline:
                self._poll_cycle()
                # 等到下一輪或截止（取較小者），避免超出 duration。
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(policy.poll_interval_seconds, remaining))
        except rest.GateBRestError as exc:
            self._pipeline_error = f"rest_poll_failed:{exc}"
        except Exception as exc:  # noqa: BLE001 - entry 層需捕捉以保證收尾寫 verdict
            self._pipeline_error = f"probe_unexpected_error:{exc}"
        finally:
            stop.set()
            ws_thread.join(timeout=5.0)

        return self._finalize(dry_run=False)

    def _poll_cycle(self) -> None:
        """單輪 REST 輪詢 → 收集 transition → 同步 WS 訂閱 + launchTime。"""
        _phases, transitions = self.rest_probe.poll_once()
        for t in transitions:
            self._transitions.append(
                {
                    "symbol": t.symbol,
                    "prev_status": t.prev_status,
                    "new_status": t.new_status,
                    "launch_time_ms": t.launch_time_ms,
                    "detected_ingest_ts_ms": t.detected_ingest_ts_ms,
                }
            )
        # 把 launchTime 餵給 WS（capture_lag 基準），並動態同步訂閱集合。
        candidates = self.rest_probe.state.prelaunch_symbols()
        for sym in candidates:
            self.ws_probe.set_launch_time(sym, self.rest_probe.state.launch_time_of(sym))
        # 轉 Trading 的 symbol 也要餵 launchTime（capture_lag 在首筆成交時用）。
        for t in transitions:
            self.ws_probe.set_launch_time(t.symbol, t.launch_time_ms)
        self.ws_probe.sync_subscriptions(candidates)

    def _run_ws_loop(self, stop: threading.Event) -> None:
        try:
            self.ws_probe.connect()
            # run_forever 阻塞；stop 由主執行緒設後，WS 連線在 daemon thread 隨進程退出。
            self.ws_probe.run_forever()
        except Exception as exc:  # noqa: BLE001 - WS 執行緒錯誤記錄但不殺主流程
            try:
                self.writer.writer_for("control")(
                    {"kind": "ws_loop_error", "error": str(exc)}
                )
            except OSError:
                pass

    def _finalize(self, *, dry_run: bool) -> dict[str, Any]:
        """收尾：summary → verdict → parquet 鏡像 → manifest，回傳 verdict dict。"""
        summary = artifact.build_phase_transition_summary(
            self._transitions, self._capture_lags
        )
        artifact.write_json(self.writer.run_dir / "phase_transition_summary.json", summary)

        control_liveness = (
            {"control_symbol": "BTCUSDT", "control_tick_count": 0, "poisoned_suspect": False}
            if dry_run
            else self.ws_probe.control_liveness()
        )
        verdict = artifact.build_verdict(
            summary, control_liveness, pipeline_error=self._pipeline_error
        )
        artifact.write_json(self.writer.run_dir / "verdict.json", verdict)

        mirror = artifact.mirror_jsonl_to_parquet(self.writer.run_dir)

        self.writer.write_manifest(
            {
                "dry_run": dry_run,
                "verdict": verdict["capture_verdict"],
                "parquet_mirror": mirror,
            }
        )
        self.writer.close()
        return verdict


def run_probe(
    *,
    duration_seconds: float,
    run_id: Optional[str] = None,
    artifact_root: Optional[Path] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """便利函數：建立並執行一次探針，回傳 verdict dict。"""
    probe = GateBProbe(run_id=run_id, artifact_root=artifact_root)
    return probe.run(duration_seconds=duration_seconds, dry_run=dry_run)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Gate-B isolated listing-capture probe — standalone public WS + REST "
            "instruments-info, zero auth/order/DB. Captures capture_lag + markout "
            "for PreLaunch->Trading transitions."
        )
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=24 * 60 * 60,
        help="探針運行時長（秒）；預設 24h（phase 轉移稀有，需長窗）。",
    )
    parser.add_argument("--run-id", type=str, default=None, help="自訂 run_id（預設自動生成）。")
    parser.add_argument(
        "--artifact-root",
        type=str,
        default=None,
        help="artifact 根目錄覆寫；預設 ${OPENCLAW_DATA_DIR:-/tmp/openclaw}/aeg_gate_b_runs。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不連 WS/不打 REST，只建立目錄並寫 INCONCLUSIVE verdict + manifest（結構驗證）。",
    )
    args = parser.parse_args(argv)

    root = Path(args.artifact_root) if args.artifact_root else None
    verdict = run_probe(
        duration_seconds=args.duration_seconds,
        run_id=args.run_id,
        artifact_root=root,
        dry_run=args.dry_run,
    )
    # 把 verdict 摘要印到 stdout 供 operator 即時判讀。
    print(
        "gate_b verdict: "
        + str(verdict.get("capture_verdict"))
        + f" (transitions={verdict.get('transition_count')}, "
        + f"isolation_warning={verdict.get('isolation_health_warning')})"
    )
    # PIPELINE_ERROR 才視為非零退出（INCONCLUSIVE 是正常結果，退出 0）。
    return 1 if verdict.get("capture_verdict") == artifact.VERDICT_PIPELINE_ERROR else 0


if __name__ == "__main__":
    raise SystemExit(main())
