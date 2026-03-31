"""
H0 Gate — Local Deterministic Judgment Core / H0 確定性門控核心
Implementation of P1-16 per DOC-02 §3 (< 1 ms SLA, no I/O on hot path)

MODULE_NOTE (中文):
  本模組實現 H0 本地確定性門控，是 AI 治理層（H1-H5）的前置硬性過濾器：
  - H0GateConfig：門控參數配置（數據新鮮度、CPU/記憶體健康、DB 延遲、風控邊界等）
  - H0GateHealthSnapshot：系統健康快照（由外部監控線程週期性注入）
  - H0GateRiskSnapshot：風控快照（持倉數量、總曝險比例、冷卻期、Kill Switch 狀態）
  - H0GateCheckResult：單次 check() 結果（allowed bool、reason、check_name、latency_us）
  - H0Gate：主類，check() 熱路徑 <1ms SLA，5 個確定性子檢查依序執行

  子檢查順序：
    1. check_freshness   — Tick 數據新鮮度（symbol 有無數據 + 是否過期）
    2. check_health      — 系統資源健康（CPU / 記憶體 / DB 延遲 / 網絡丟包）
    3. check_eligibility — 符號與類別准入（category 白名單 + symbol 黑名單 + system_mode）
    4. check_risk_envelope — 風控邊界（持倉數 + 曝險比例 + kill switch）
    5. check_cooldown    — 冷卻期（時間戳比較）

  設計原則：
    - 熱路徑（check()）只做 Python 基本運算，嚴禁 I/O / 網絡 / DB 調用
    - 狀態更新（update_*）由外部線程非同步注入，Python GIL 保護基本賦值原子性
    - fail-closed：任何子檢查返回 False 立即終止，不繼續後續檢查

MODULE_NOTE (English):
  Implements H0 local deterministic gate, the mandatory hard filter before
  AI governance layers (H1-H5):
  - H0GateConfig: gate parameter configuration (data freshness, CPU/memory health,
    DB latency, risk envelope bounds, etc.)
  - H0GateHealthSnapshot: system health snapshot (injected by external monitor thread)
  - H0GateRiskSnapshot: risk snapshot (position count, total exposure %, cooldown,
    kill switch state)
  - H0GateCheckResult: result of a single check() call (allowed bool, reason,
    check_name, latency_us for SLA validation)
  - H0Gate: main class, check() hot path with <1ms SLA, 5 deterministic sub-checks

  Sub-check order (fail-fast):
    1. check_freshness   — tick data freshness (symbol present + not stale)
    2. check_health      — system resource health (CPU / memory / DB latency / network)
    3. check_eligibility — symbol/category allowlist + system_mode gate
    4. check_risk_envelope — risk envelope (position count + exposure % + kill switch)
    5. check_cooldown    — cooldown period (timestamp comparison)

  Design principles:
    - Hot path (check()) uses only basic Python arithmetic — no I/O, network, or DB
    - State updates (update_*) injected asynchronously by external threads;
      Python GIL protects simple attribute assignment atomicity
    - Fail-closed: any sub-check returning False terminates immediately

Governance reference:
  DOC-02 §3: H0 Gate deterministic gating, <1ms SLA requirement
  §5.4 (Principle 4): strategy cannot bypass risk control
  §5.5 (Principle 5): survival before profit
  §5.6 (Principle 6): fail to safe / conserve on uncertainty
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Dataclasses / 數據類
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class H0GateConfig:
    """
    Configuration for H0 Gate deterministic checks.
    H0 確定性門控參數配置。

    All thresholds are enforced on the hot path without I/O.
    所有閾值在熱路徑中純記憶體比對，無任何 I/O。
    """
    # Data freshness / 數據新鮮度
    max_data_age_ms: int = 1000           # 最大 tick 數據年齡（毫秒）

    # System resource health / 系統資源健康
    max_cpu_pct: float = 90.0             # CPU 使用率上限（%）
    min_memory_mb: int = 1024             # 可用記憶體下限（MB）
    max_db_latency_ms: float = 100.0      # DB 查詢延遲上限（毫秒）
    max_network_loss_pct: float = 5.0     # 網絡丟包率上限（%）

    # Symbol / category eligibility / 符號與類別准入
    allowed_categories: frozenset = field(
        default_factory=lambda: frozenset({"linear", "inverse", "spot"})
    )

    # Risk envelope / 風控邊界
    max_open_positions: int = 10          # 最大持倉數量
    max_total_exposure_pct: float = 90.0  # 最大總曝險比例（%）

    # Health snapshot TTL / 健康快照有效期
    health_snapshot_max_age_ms: int = 30_000  # 30 秒，超過視為快照過期


@dataclass
class H0GateHealthSnapshot:
    """
    System health snapshot injected by external monitor thread.
    由外部監控線程注入的系統健康快照。

    Updated periodically (e.g. every 5s). Not refreshed on hot path.
    週期性更新（例如每 5 秒），熱路徑不觸發刷新。
    """
    cpu_pct: float = 0.0                  # CPU 使用率（%）
    memory_available_mb: int = 9999       # 可用記憶體（MB），預設值大表示健康
    db_latency_ms: float = 0.0            # DB 最近查詢延遲（毫秒）
    network_loss_pct: float = 0.0         # 網絡丟包率（%）
    snapshot_ts_ms: int = 0               # 快照時間戳（毫秒，0 表示從未更新）


@dataclass
class H0GateRiskSnapshot:
    """
    Risk state snapshot injected by external risk monitor.
    由外部風控監控注入的風控狀態快照。

    Updated after every position change. Not queried on hot path beyond attribute read.
    每次持倉變更後更新。熱路徑僅做屬性讀取，不觸發計算。
    """
    open_position_count: int = 0          # 當前持倉數量
    total_exposure_pct: float = 0.0       # 總曝險比例（%，相對可用保證金）
    cooldown_until_ts_ms: int = 0         # 冷卻期截止時間戳（0 表示無冷卻）
    kill_switch_active: bool = False       # Kill Switch 是否啟動
    snapshot_ts_ms: int = 0               # 快照時間戳（毫秒）


@dataclass
class H0GateCheckResult:
    """
    Result of a single H0Gate.check() call.
    單次 H0Gate.check() 呼叫的結果。

    Designed for downstream consumption by H1-H5 AI governance layers.
    供下游 H1-H5 AI 治理層消費。
    """
    allowed: bool                          # True 表示通過，False 表示阻擋
    reason: str                            # 阻擋原因（通過時為 ""）
    check_name: str                        # 觸發阻擋的子檢查名稱，或 "all_passed"
    latency_us: int = 0                    # check() 執行耗時（微秒），供 E4 SLA 驗證


# ═══════════════════════════════════════════════════════════════════════════════
# H0 Gate Main Class / H0 門控主類
# ═══════════════════════════════════════════════════════════════════════════════

class H0Gate:
    """
    H0 Local Deterministic Judgment Core.
    H0 本地確定性判斷核心。

    Hot path check() must complete in <1ms. All state is pre-loaded into memory
    and updated asynchronously by external threads.

    熱路徑 check() 必須在 <1ms 內完成。所有狀態預載入記憶體，
    由外部線程異步更新，熱路徑只做記憶體讀取與數值比對。

    Usage / 使用方式:
        gate = H0Gate()
        # External monitor threads call:
        gate.update_health(snapshot)
        gate.update_risk(snapshot)
        gate.update_price_ts("BTCUSDT", int(time.time() * 1000))
        # Hot path:
        result = gate.check("BTCUSDT", "linear")
        if not result.allowed:
            logger.warning(f"H0 blocked: {result.reason}")
    """

    def __init__(self, config: H0GateConfig | None = None) -> None:
        """
        Initialize H0Gate with optional config.
        初始化 H0Gate，可選傳入配置。
        """
        self._config: H0GateConfig = config if config is not None else H0GateConfig()

        # Snapshots injected by external threads / 由外部線程注入的快照
        self._health_snapshot: H0GateHealthSnapshot = H0GateHealthSnapshot()
        self._risk_snapshot: H0GateRiskSnapshot = H0GateRiskSnapshot()

        # Price tick timestamps: symbol → last tick ts in ms / 價格 tick 時間戳
        # Key: symbol str, Value: int ms
        self._price_ts: dict[str, int] = {}

        # System mode / execution state (reflect runtime hard state) / 系統模式與執行狀態
        self._system_mode: str = "read_only"      # "read_only" | "active" | "disabled"
        self._execution_state: str = "disabled"   # "disabled" | "enabled"

        # Per-symbol eligibility override / 符號准入覆蓋（None = 使用類別白名單）
        # False → explicitly blocked; True or absent → allowed
        self._symbol_eligibility: dict[str, bool] = {}

        # Statistics for observability / 可觀測性統計
        self._stats: dict[str, int] = {
            "total_checks": 0,
            "allowed": 0,
            "blocked_freshness": 0,
            "blocked_health": 0,
            "blocked_eligibility": 0,
            "blocked_risk": 0,
            "blocked_cooldown": 0,
            "max_latency_us": 0,
            "total_latency_us": 0,
        }

    # ── Property access / 屬性訪問 ───────────────────────────────────────────

    @property
    def config(self) -> H0GateConfig:
        """Read-only access to config / 配置只讀訪問"""
        return self._config

    # ── State update methods (non-hot path) / 狀態更新方法（非熱路徑）────────

    def update_health(self, snapshot: H0GateHealthSnapshot) -> None:
        """
        Inject updated system health snapshot.
        注入更新的系統健康快照。

        Called by external health monitor thread, NOT on hot path.
        由外部健康監控線程調用，不在熱路徑上。
        """
        self._health_snapshot = snapshot
        logger.debug(
            "H0Gate health updated: cpu=%.1f%% mem=%dMB db_lat=%.1fms net_loss=%.1f%%",
            snapshot.cpu_pct,
            snapshot.memory_available_mb,
            snapshot.db_latency_ms,
            snapshot.network_loss_pct,
        )

    def update_risk(self, snapshot: H0GateRiskSnapshot) -> None:
        """
        Inject updated risk state snapshot.
        注入更新的風控狀態快照。

        Called after every position change or periodic risk poll.
        每次持倉變更或週期性風控輪詢後調用。
        """
        self._risk_snapshot = snapshot
        logger.debug(
            "H0Gate risk updated: positions=%d exposure=%.1f%% kill_switch=%s",
            snapshot.open_position_count,
            snapshot.total_exposure_pct,
            snapshot.kill_switch_active,
        )

    def update_price_ts(self, symbol: str, ts_ms: int) -> None:
        """
        Update the last known tick timestamp for a symbol.
        更新某符號的最後 tick 時間戳。

        Called by market data dispatcher on every tick.
        由市場數據分發器在每個 tick 時調用。
        """
        self._price_ts[symbol] = ts_ms

    def set_system_mode(self, mode: str) -> None:
        """
        Set system operating mode.
        設置系統操作模式。

        Args:
            mode: "read_only" | "active" | "disabled"
        """
        self._system_mode = mode
        logger.info("H0Gate system_mode set to: %s", mode)

    def set_execution_state(self, state: str) -> None:
        """
        Set execution state.
        設置執行狀態。

        Args:
            state: "disabled" | "enabled"
        """
        self._execution_state = state
        logger.info("H0Gate execution_state set to: %s", state)

    def set_symbol_eligibility(self, symbol: str, eligible: bool) -> None:
        """
        Override eligibility for a specific symbol.
        覆蓋特定符號的准入狀態。

        Args:
            symbol: Trading pair symbol, e.g. "BTCUSDT"
            eligible: True to allow, False to block
        """
        self._symbol_eligibility[symbol] = eligible
        logger.info(
            "H0Gate symbol eligibility: %s → %s",
            symbol,
            "allowed" if eligible else "blocked",
        )

    # ── Hot path entry point / 熱路徑入口 ────────────────────────────────────

    def check(self, symbol: str, category: str = "linear") -> H0GateCheckResult:
        """
        Main hot-path gate check. Must complete in <1ms.
        主熱路徑門控檢查，必須在 <1ms 內完成。

        Executes 5 sub-checks in order. Returns immediately on first failure
        (fail-fast). Tracks latency for SLA monitoring.

        依序執行 5 個子檢查，第一個失敗即立即返回（fail-fast）。
        記錄延遲以供 SLA 監控。

        Args:
            symbol:   Trading pair symbol, e.g. "BTCUSDT"
            category: Contract category: "linear" | "inverse" | "spot"

        Returns:
            H0GateCheckResult with allowed bool, reason, check_name, latency_us
        """
        t0 = time.perf_counter()
        now_ms = int(time.time() * 1000)

        self._stats["total_checks"] += 1

        # 1. Freshness check / 數據新鮮度檢查
        ok, reason = self.check_freshness(symbol, now_ms)
        if not ok:
            latency_us = int((time.perf_counter() - t0) * 1_000_000)
            self._record_block("blocked_freshness", latency_us)
            return H0GateCheckResult(
                allowed=False,
                reason=reason,
                check_name="freshness",
                latency_us=latency_us,
            )

        # 2. Health check / 系統健康檢查
        ok, reason = self.check_health(now_ms)
        if not ok:
            latency_us = int((time.perf_counter() - t0) * 1_000_000)
            self._record_block("blocked_health", latency_us)
            return H0GateCheckResult(
                allowed=False,
                reason=reason,
                check_name="health",
                latency_us=latency_us,
            )

        # 3. Eligibility check / 准入檢查
        ok, reason = self.check_eligibility(symbol, category)
        if not ok:
            latency_us = int((time.perf_counter() - t0) * 1_000_000)
            self._record_block("blocked_eligibility", latency_us)
            return H0GateCheckResult(
                allowed=False,
                reason=reason,
                check_name="eligibility",
                latency_us=latency_us,
            )

        # 4. Risk envelope check / 風控邊界檢查
        ok, reason = self.check_risk_envelope()
        if not ok:
            latency_us = int((time.perf_counter() - t0) * 1_000_000)
            self._record_block("blocked_risk", latency_us)
            return H0GateCheckResult(
                allowed=False,
                reason=reason,
                check_name="risk",
                latency_us=latency_us,
            )

        # 5. Cooldown check / 冷卻期檢查
        ok, reason = self.check_cooldown(now_ms)
        if not ok:
            latency_us = int((time.perf_counter() - t0) * 1_000_000)
            self._record_block("blocked_cooldown", latency_us)
            return H0GateCheckResult(
                allowed=False,
                reason=reason,
                check_name="cooldown",
                latency_us=latency_us,
            )

        # All checks passed / 全部通過
        latency_us = int((time.perf_counter() - t0) * 1_000_000)
        self._stats["allowed"] += 1
        self._stats["total_latency_us"] += latency_us
        if latency_us > self._stats["max_latency_us"]:
            self._stats["max_latency_us"] = latency_us

        return H0GateCheckResult(
            allowed=True,
            reason="",
            check_name="all_passed",
            latency_us=latency_us,
        )

    # ── Sub-checks / 子檢查 ──────────────────────────────────────────────────

    def check_freshness(self, symbol: str, now_ms: int) -> tuple[bool, str]:
        """
        Check whether price tick data for symbol is fresh enough.
        檢查符號的 tick 數據是否足夠新鮮。

        Blocks if:
          - symbol has never received a tick (no_data)
          - last tick is older than config.max_data_age_ms (data_stale)

        阻擋條件：
          - 符號從未收到 tick → no_data_{symbol}
          - 最後 tick 超過 max_data_age_ms → data_stale_{symbol}_{age}ms

        Args:
            symbol: Trading pair symbol
            now_ms: Current timestamp in milliseconds

        Returns:
            (True, "") if fresh; (False, reason_str) if blocked
        """
        last_ts = self._price_ts.get(symbol)

        if last_ts is None:
            return False, f"no_data_{symbol}"

        age_ms = now_ms - last_ts
        if age_ms >= self._config.max_data_age_ms:
            return False, f"data_stale_{symbol}_{age_ms}ms"

        return True, ""

    def check_health(self, now_ms: int) -> tuple[bool, str]:
        """
        Check system resource health against configured thresholds.
        檢查系統資源健康是否在配置閾值內。

        NOTE (Day 1 skeleton): Full threshold checks implemented.
        Snapshot staleness check also enforced via health_snapshot_max_age_ms.

        Day 2 will add: integration with live psutil / DB probe injection.

        Args:
            now_ms: Current timestamp in milliseconds

        Returns:
            (True, "") if healthy; (False, reason_str) if blocked
        """
        snap = self._health_snapshot

        # Check snapshot staleness / 檢查快照是否過期
        if snap.snapshot_ts_ms > 0:
            snap_age_ms = now_ms - snap.snapshot_ts_ms
            if snap_age_ms > self._config.health_snapshot_max_age_ms:
                return False, f"health_snapshot_stale_{snap_age_ms}ms"

        # CPU / CPU 使用率
        if snap.cpu_pct > self._config.max_cpu_pct:
            return False, f"cpu_too_high_{snap.cpu_pct:.1f}pct"

        # Memory / 可用記憶體
        if snap.memory_available_mb < self._config.min_memory_mb:
            return False, f"memory_low_{snap.memory_available_mb}mb"

        # DB latency / DB 延遲
        if snap.db_latency_ms > self._config.max_db_latency_ms:
            return False, f"db_latency_high_{snap.db_latency_ms:.1f}ms"

        # Network loss / 網絡丟包
        if snap.network_loss_pct > self._config.max_network_loss_pct:
            return False, f"network_loss_high_{snap.network_loss_pct:.1f}pct"

        return True, ""

    def check_eligibility(self, symbol: str, category: str) -> tuple[bool, str]:
        """
        Check whether the symbol/category combination is eligible for trading.
        檢查符號與類別組合是否准許交易。

        Blocks if:
          - category not in allowed_categories whitelist
          - symbol explicitly set to ineligible via set_symbol_eligibility()
          - system_mode is "disabled"

        Note: system_mode "read_only" is permitted (observation is always on).
        注意：system_mode 為 "read_only" 時允許通過（觀察模式始終開啟）。

        Args:
            symbol:   Trading pair symbol
            category: Contract category

        Returns:
            (True, "") if eligible; (False, reason_str) if blocked
        """
        # Category whitelist / 類別白名單
        if category not in self._config.allowed_categories:
            return False, f"category_not_allowed_{category}"

        # Per-symbol eligibility override / 符號准入覆蓋
        eligibility = self._symbol_eligibility.get(symbol)
        if eligibility is False:
            return False, f"symbol_not_eligible_{symbol}"

        # System mode gate / 系統模式門控
        # "disabled" blocks all; "read_only" and "active" both pass this check
        if self._system_mode == "disabled":
            return False, "system_disabled"

        return True, ""

    def check_risk_envelope(self) -> tuple[bool, str]:
        """
        Check risk envelope: position count, total exposure, kill switch.
        檢查風控邊界：持倉數量、總曝險比例、Kill Switch。

        NOTE (Day 1 skeleton): Core checks implemented.
        Day 2 will add: per-symbol concentration limits, correlation checks.

        Returns:
            (True, "") if within envelope; (False, reason_str) if blocked
        """
        snap = self._risk_snapshot

        # Kill switch takes highest priority / Kill Switch 最高優先
        if snap.kill_switch_active:
            return False, "kill_switch_active"

        # Open position count / 持倉數量上限
        if snap.open_position_count >= self._config.max_open_positions:
            return (
                False,
                f"max_positions_reached_{snap.open_position_count}"
                f"_of_{self._config.max_open_positions}",
            )

        # Total exposure / 總曝險比例
        if snap.total_exposure_pct >= self._config.max_total_exposure_pct:
            return (
                False,
                f"exposure_limit_reached_{snap.total_exposure_pct:.1f}pct"
                f"_of_{self._config.max_total_exposure_pct:.1f}pct",
            )

        return True, ""

    def check_cooldown(self, now_ms: int) -> tuple[bool, str]:
        """
        Check whether the system is in a cooldown period.
        檢查系統是否處於冷卻期。

        NOTE (Day 1 skeleton): Timestamp comparison implemented.
        Day 2 will add: per-symbol cooldown tracking, consecutive-loss cooldown.

        Args:
            now_ms: Current timestamp in milliseconds

        Returns:
            (True, "") if not in cooldown; (False, reason_str) if blocked
        """
        cooldown_until = self._risk_snapshot.cooldown_until_ts_ms

        if cooldown_until > 0 and now_ms < cooldown_until:
            remaining_ms = cooldown_until - now_ms
            return False, f"cooldown_active_{remaining_ms}ms_remaining"

        return True, ""

    # ── Internal helpers / 內部輔助方法 ─────────────────────────────────────

    def _record_block(self, stat_key: str, latency_us: int) -> None:
        """
        Record a blocked check in statistics.
        在統計中記錄一次阻擋。
        """
        self._stats[stat_key] += 1
        self._stats["total_latency_us"] += latency_us
        if latency_us > self._stats["max_latency_us"]:
            self._stats["max_latency_us"] = latency_us

    # ── Observability / 可觀測性 ─────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """
        Return accumulated statistics for monitoring.
        返回累積統計數據供監控使用。

        Returns a shallow copy to prevent external mutation.
        返回淺複製以防止外部修改。
        """
        stats = dict(self._stats)

        total = stats["total_checks"]
        if total > 0:
            stats["allow_rate_pct"] = round(stats["allowed"] / total * 100, 2)
            stats["avg_latency_us"] = round(stats["total_latency_us"] / total, 1)
        else:
            stats["allow_rate_pct"] = 0.0
            stats["avg_latency_us"] = 0.0

        # 便捷別名：合計所有 blocked_* 計數
        stats["passed"] = stats["allowed"]
        stats["blocked"] = (
            stats.get("blocked_freshness", 0)
            + stats.get("blocked_health", 0)
            + stats.get("blocked_eligibility", 0)
            + stats.get("blocked_risk", 0)
            + stats.get("blocked_cooldown", 0)
        )

        return stats

    def get_current_state(self) -> dict[str, Any]:
        """
        Return current gate state snapshot for API / GUI consumption.
        返回當前門控狀態快照，供 API / GUI 消費。
        """
        snap_h = self._health_snapshot
        snap_r = self._risk_snapshot
        now_ms = int(time.time() * 1000)

        return {
            "system_mode": self._system_mode,
            "execution_state": self._execution_state,
            "config": {
                "max_data_age_ms": self._config.max_data_age_ms,
                "max_cpu_pct": self._config.max_cpu_pct,
                "min_memory_mb": self._config.min_memory_mb,
                "max_db_latency_ms": self._config.max_db_latency_ms,
                "max_network_loss_pct": self._config.max_network_loss_pct,
                "allowed_categories": sorted(self._config.allowed_categories),
                "max_open_positions": self._config.max_open_positions,
                "max_total_exposure_pct": self._config.max_total_exposure_pct,
                "health_snapshot_max_age_ms": self._config.health_snapshot_max_age_ms,
            },
            "health": {
                "cpu_pct": snap_h.cpu_pct,
                "memory_available_mb": snap_h.memory_available_mb,
                "db_latency_ms": snap_h.db_latency_ms,
                "network_loss_pct": snap_h.network_loss_pct,
                "snapshot_ts_ms": snap_h.snapshot_ts_ms,
                "snapshot_age_ms": (
                    now_ms - snap_h.snapshot_ts_ms if snap_h.snapshot_ts_ms > 0 else None
                ),
            },
            "risk": {
                "open_position_count": snap_r.open_position_count,
                "total_exposure_pct": snap_r.total_exposure_pct,
                "cooldown_until_ts_ms": snap_r.cooldown_until_ts_ms,
                "cooldown_remaining_ms": max(0, snap_r.cooldown_until_ts_ms - now_ms)
                if snap_r.cooldown_until_ts_ms > 0
                else 0,
                "kill_switch_active": snap_r.kill_switch_active,
                "snapshot_ts_ms": snap_r.snapshot_ts_ms,
            },
            "tracked_symbols": len(self._price_ts),
            "symbol_overrides": {
                sym: elig for sym, elig in self._symbol_eligibility.items()
            },
            "stats": self.get_stats(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# H0 Health Worker / H0 健康監控工作線程
# ═══════════════════════════════════════════════════════════════════════════════

class H0HealthWorker:
    """
    Background daemon thread that periodically samples system health
    and injects H0GateHealthSnapshot into an H0Gate instance.

    背景守護線程，週期性採樣系統健康指標並注入 H0Gate 快照。

    Usage / 使用方式:
        worker = H0HealthWorker(gate, sample_interval_s=5.0)
        worker.start()
        # ... application runs ...
        worker.stop()

    Dependencies / 依賴:
        psutil (optional) — if not installed, CPU/memory sampling is skipped
        and defaults (0.0 / 9999 MB) are used instead.
        psutil 為可選依賴；未安裝時 CPU/記憶體採樣跳過，使用安全默認值。

    Design notes / 設計說明:
        - Thread is daemon=True; exits automatically when main process exits.
        - db_probe_fn: injectable callable returning DB latency in ms (float).
          Must be fast (<10ms); called inside the sample loop on every interval.
        - network_loss_pct: currently always 0.0 (requires icmp/ping tooling
          which is platform-specific; left for future integration).
        - Thread is non-blocking: sample loop uses threading.Event.wait()
          so stop() wakes the thread immediately.
    """

    def __init__(
        self,
        gate: H0Gate,
        sample_interval_s: float = 5.0,
        db_probe_fn: Callable[[], float] | None = None,
    ) -> None:
        """
        Initialize H0HealthWorker.

        Args:
            gate: H0Gate instance to inject health snapshots into.
            sample_interval_s: Sampling interval in seconds (default 5.0).
            db_probe_fn: Optional callable that measures DB round-trip latency.
                         Must return float (latency in ms). Called on each
                         sampling cycle. Should be fast (<10ms).
        """
        self._gate = gate
        self._sample_interval_s = sample_interval_s
        self._db_probe_fn = db_probe_fn

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Lifecycle / 生命週期 ─────────────────────────────────────────────────

    def start(self) -> None:
        """
        Start the background health sampling thread.
        啟動背景健康採樣線程。

        Idempotent: calling start() on an already-running worker is a no-op.
        """
        if self._thread is not None and self._thread.is_alive():
            logger.debug("H0HealthWorker already running — start() ignored")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="H0HealthWorker",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "H0HealthWorker started (interval=%.1fs, db_probe=%s)",
            self._sample_interval_s,
            "yes" if self._db_probe_fn is not None else "no",
        )

    def stop(self) -> None:
        """
        Stop the background health sampling thread.
        停止背景健康採樣線程。

        Signals the thread to exit and waits for it to finish (up to 10s).
        Does nothing if the thread is not running.
        """
        if self._thread is None or not self._thread.is_alive():
            logger.debug("H0HealthWorker not running — stop() ignored")
            return

        self._stop_event.set()
        self._thread.join(timeout=10.0)
        if self._thread.is_alive():
            logger.warning("H0HealthWorker thread did not stop within 10s")
        else:
            logger.info("H0HealthWorker stopped")
        self._thread = None

    @property
    def is_running(self) -> bool:
        """True if the worker thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    # ── Internal / 內部實現 ──────────────────────────────────────────────────

    def _run(self) -> None:
        """
        Main thread loop. Samples health and injects snapshot on each interval.
        主線程循環。每個採樣週期採集健康數據並注入快照。
        """
        logger.debug("H0HealthWorker loop started")
        while not self._stop_event.is_set():
            try:
                snapshot = self._sample_once()
                self._gate.update_health(snapshot)
            except Exception:
                logger.exception("H0HealthWorker sample failed — skipping cycle")
            # Use Event.wait for interruptible sleep / 可中斷睡眠
            self._stop_event.wait(timeout=self._sample_interval_s)
        logger.debug("H0HealthWorker loop exited")

    def _sample_once(self) -> H0GateHealthSnapshot:
        """
        Collect one health sample. Returns a populated H0GateHealthSnapshot.
        採集一次健康樣本，返回 H0GateHealthSnapshot。

        CPU and memory are sampled via psutil if available.
        If psutil is not installed, safe defaults are used (0% CPU, 9999 MB RAM).
        DB latency is measured via db_probe_fn if provided.
        Network loss is always 0.0 (future integration point).
        """
        cpu_pct = 0.0
        memory_available_mb = 9999

        try:
            import psutil  # type: ignore[import]
            cpu_pct = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            memory_available_mb = int(mem.available / (1024 * 1024))
        except ImportError:
            logger.debug(
                "psutil not installed — H0HealthWorker using defaults"
                " (cpu=0.0, mem=9999MB)"
            )
        except Exception:
            logger.warning("H0HealthWorker: psutil sampling error — using defaults")

        db_latency_ms = 0.0
        if self._db_probe_fn is not None:
            try:
                t0 = time.perf_counter()
                self._db_probe_fn()
                db_latency_ms = (time.perf_counter() - t0) * 1000.0
            except Exception:
                logger.warning(
                    "H0HealthWorker: db_probe_fn raised — db_latency_ms set to 0.0"
                )

        return H0GateHealthSnapshot(
            cpu_pct=cpu_pct,
            memory_available_mb=memory_available_mb,
            db_latency_ms=db_latency_ms,
            network_loss_pct=0.0,
            snapshot_ts_ms=int(time.time() * 1000),
        )
