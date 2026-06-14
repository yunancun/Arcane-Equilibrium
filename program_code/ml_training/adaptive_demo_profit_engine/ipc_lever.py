"""
MODULE_NOTE (中):
  用途：ADPE 把 allocator 配權決策落到 demo 引擎的**唯一 lever 薄殼**。複用既有
  sync_ipc_call('set_strategy_active') IPC（0 新 IPC、0 新 command、0 schema 改），
  並複用既有 RustSnapshotReader 讀「當前策略 active 態」供冪等 diff + kill-switch
  snapshot/restore。

  主要類 / 函數：
    - StrategyLever：注入 set_active_fn（IPC 寫）+ read_states_fn（snapshot 讀）的薄殼。
      production 用 _default_set_active / _default_read_states（接既有 IPC / snapshot）；
      測試注入 fake，不連真 engine。
    - StrategyLever.read_active_snapshot()：讀當前 {strategy: active?} 快照。
    - StrategyLever.apply_desired(desired, dry_run)：把期望態 diff 後**只在需變更時**
      發 IPC（冪等）；回 ApplyResult（含每筆變更 / 跳過 / 失敗）。
    - StrategyLever.restore_snapshot(snapshot, dry_run)：kill-switch 用，把策略 active 態
      還原成傳入 snapshot。

  依賴（lazy import，避免 ml_training 對 control_api app 的 import-time 硬耦合）：
    - exchange_connectors...app.ipc_client_sync.sync_ipc_call（既有 IPC 寫）。
    - exchange_connectors...app.ipc_state_reader.RustSnapshotReader（既有 snapshot 讀）。

  硬邊界 / 誠實鐵則（為什麼這樣設計）：
    1. **demo 沙盒 lever**。set_strategy_active 是 strategy 級啟停（非下單、非改 live
       config）；intent 仍走 IntentProcessor + Guardian + cost-gate（不繞寫入口）。
    2. **冪等 diff，不蓋 operator 顯式態盲改**。apply_desired 先讀現態，只對「現態 ≠
       期望態」者發 IPC；現態未知（snapshot 缺）時對該策略**不主動關**（fail-safe：
       寧可不動也不誤關 operator 想開的），記 skip。
    3. **dry_run 默認真**。runner 默認 dry-run，apply_desired/restore 只回 plan diff、
       不發 IPC；真發需顯式 dry_run=False。
    4. **IPC 失敗不 hidden retry**。單筆 set_active 失敗只記 failed + log，不重試
       下單效果（對齊 CLAUDE 硬邊界：不為交易效果加隱藏重試）；下 cycle 自然重試。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class LeverChange:
    """單筆 set_active 變更記錄（審計用）。"""

    strategy: str
    target_active: bool
    status: str  # "applied" | "skipped_same" | "skipped_unknown" | "failed" | "dry_run"
    detail: str = ""


@dataclass
class ApplyResult:
    """apply_desired / restore_snapshot 的結果聚合。"""

    changes: list[LeverChange] = field(default_factory=list)
    dry_run: bool = True

    @property
    def applied_count(self) -> int:
        return sum(1 for c in self.changes if c.status == "applied")

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.changes if c.status == "failed")


def _default_set_active(strategy: str, active: bool) -> dict:
    """production IPC 寫：複用既有 sync_ipc_call('set_strategy_active')。

    lazy import：避免 ml_training package import 時硬拉 control_api app 依賴鏈。
    回 IPC result dict（成功）或 raise（失敗，由上層 catch 記 failed）。
    """
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.ipc_client_sync import (  # noqa: PLC0415,E501
        sync_ipc_call,
    )

    return sync_ipc_call(
        "set_strategy_active",
        {"strategy_name": strategy, "active": bool(active)},
    )


def _default_read_states() -> dict[str, bool]:
    """production snapshot 讀：複用既有 RustSnapshotReader.get_strategies()。

    回 {strategy_name: active?}。snapshot 缺 / 引擎未跑 → 回空 dict（上層據此
    對未知策略走 fail-safe 不主動關）。
    """
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.ipc_state_reader import (  # noqa: PLC0415,E501
        RustSnapshotReader,
    )

    reader = RustSnapshotReader()
    states: dict[str, bool] = {}
    for s in reader.get_strategies() or []:
        if not isinstance(s, dict):
            continue
        name = s.get("name") or s.get("strategy_name")
        if not name:
            continue
        # snapshot 可能用 'active' / 'is_active' / 'state' 表達；保守取多鍵。
        if "active" in s:
            states[str(name)] = bool(s.get("active"))
        elif "is_active" in s:
            states[str(name)] = bool(s.get("is_active"))
        elif "state" in s:
            states[str(name)] = str(s.get("state")).lower() in ("active", "running")
    return states


class StrategyLever:
    """demo 引擎 strategy active 態的讀 / 寫薄殼（可注入，便於測試）。"""

    def __init__(
        self,
        set_active_fn: Optional[Callable[[str, bool], dict]] = None,
        read_states_fn: Optional[Callable[[], dict[str, bool]]] = None,
    ):
        self._set_active = set_active_fn or _default_set_active
        self._read_states = read_states_fn or _default_read_states

    def read_active_snapshot(self) -> dict[str, bool]:
        """讀當前 {strategy: active?} 快照（kill-switch snapshot 的來源）。"""
        try:
            return dict(self._read_states())
        except Exception as e:  # noqa: BLE001
            # snapshot 讀失敗 → 空 dict（上層 fail-safe：未知不主動關）。
            logger.warning("read_active_snapshot 失敗，回空快照: %s", e)
            return {}

    def apply_desired(
        self,
        desired: dict[str, bool],
        *,
        dry_run: bool = True,
    ) -> ApplyResult:
        """把期望態 desired={strategy: active?} 冪等地落到引擎。

        冪等規則：先讀現態，逐策略：
          - 現態 == 期望態 → skipped_same（不發 IPC）。
          - 現態未知（snapshot 缺該策略）且期望=關 → skipped_unknown（fail-safe 不誤關）。
          - 現態未知且期望=開 → 發 IPC 開（開是安全方向：要它跑）。
          - 現態 ≠ 期望態 → 發 IPC 設成期望態。
        dry_run=True：只記 dry_run 變更，不發 IPC。
        """
        result = ApplyResult(dry_run=dry_run)
        current = self.read_active_snapshot()

        for strategy, want_active in desired.items():
            want_active = bool(want_active)
            cur = current.get(strategy)

            if cur is not None and cur == want_active:
                result.changes.append(
                    LeverChange(strategy, want_active, "skipped_same")
                )
                continue

            # 現態未知 + 想關 → fail-safe 不主動關（寧可不動，不誤關 operator 想開的）。
            if cur is None and not want_active:
                result.changes.append(
                    LeverChange(
                        strategy,
                        want_active,
                        "skipped_unknown",
                        "現態未知，期望=關，fail-safe 不主動關",
                    )
                )
                continue

            self._dispatch_one(result, strategy, want_active, dry_run)

        return result

    def restore_snapshot(
        self,
        snapshot: dict[str, bool],
        *,
        dry_run: bool = True,
    ) -> ApplyResult:
        """kill-switch：把策略 active 態還原成傳入 snapshot。

        與 apply_desired 同冪等語意，但語義是「強制還原到快照」：snapshot 內每個
        策略都嘗試設回快照值（現態==快照值則 skipped_same）。snapshot 外的策略不碰。
        """
        return self.apply_desired(dict(snapshot), dry_run=dry_run)

    def _dispatch_one(
        self,
        result: ApplyResult,
        strategy: str,
        active: bool,
        dry_run: bool,
    ) -> None:
        """發單筆 set_active（或 dry-run 記錄）。失敗只記 failed，不 hidden retry。"""
        if dry_run:
            result.changes.append(LeverChange(strategy, active, "dry_run"))
            return
        try:
            resp = self._set_active(strategy, active)
            if isinstance(resp, dict) and resp.get("ok") is False:
                result.changes.append(
                    LeverChange(strategy, active, "failed", f"IPC non-ok: {resp}")
                )
                logger.warning(
                    "set_strategy_active non-ok strategy=%s active=%s resp=%s",
                    strategy, active, resp,
                )
            else:
                result.changes.append(LeverChange(strategy, active, "applied"))
        except Exception as e:  # noqa: BLE001
            # 不為交易效果加隱藏重試（CLAUDE 硬邊界）；記 failed，下 cycle 自然重試。
            result.changes.append(LeverChange(strategy, active, "failed", str(e)))
            logger.warning(
                "set_strategy_active 失敗 strategy=%s active=%s: %s",
                strategy, active, e,
            )
