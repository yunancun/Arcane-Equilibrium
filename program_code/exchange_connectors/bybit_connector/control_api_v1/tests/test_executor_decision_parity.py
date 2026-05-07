"""
G8-02 — Python↔Rust ExecutorAgent decision parity test (70-case ≥95% binary).
G8-02 — Python↔Rust ExecutorAgent 決策一致性測試（70 案例，binary agree ≥95%）。

MODULE_NOTE (EN):
  Static parity test (CI-runnable) covering Python's ``ExecutorAgent`` runtime
  decision vs the Rust ``RiskConfig.executor`` schema specification.

  Wave-3 scope (per PA RFC Q2 in
  ``docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--wave3_dispatch_research.md``):

      Decision points limited to ``RiskConfig.executor`` sub-config:
        1. ``shadow_mode``                    (bool · WIRED end-to-end)
        2. ``per_symbol_position_cap``        (Map<String, f64> · DEFERRED to G3-08)
        3. ``max_position_pct``               (f64 · DEFERRED to G3-08)

  Why only shadow_mode is exercised across 70 cases:
    - Python ``ExecutorAgent._execute_via_ipc`` (executor_agent.py:539-567) reads
      ``self._shadow_mode_provider()`` and chooses ``ipc_shadow`` vs ``ipc_real``.
      That provider is bound to the Rust-IPC-backed ``ExecutorConfigCache``
      (executor_config_cache.py:171-175) and therefore *is* the runtime
      manifestation of ``RiskConfig.executor.shadow_mode``.
    - ``per_symbol_position_cap`` and ``max_position_pct`` are present in the
      Rust schema (risk_config_advanced.rs:770-792) and TOML defaults, but
      neither Python ExecutorAgent nor the Rust ``intent_processor`` currently
      gates SubmitOrder on them. They are scoped to a future ticket (G3-08
      "防禦深度第二道") and intentionally marked ``pytest.skip`` here so the
      gap is visible to operator and PM. See ``test_per_symbol_cap_parity_deferred``
      and ``test_max_position_pct_parity_deferred``.

  Parity definition (per PA RFC Q2):
    case-level binary — same case_id ⇒ Python and reference-spec must
    produce identical (decision, reason). agree_count / 70 ≥ 0.95 ⇔ ≥ 67/70.

  Reference spec contract:
    Both sides observe the same ``RiskConfig.executor`` snapshot. The reference
    spec (``_reference_decide``) implements the documented semantics — it is
    *not* a re-implementation of Rust runtime, it *is* the schema's intent.
    Python ExecutorAgent is then validated against that intent through real
    ``execute_order()`` / ``_execute_via_ipc()`` calls.

  Mock boundaries (per task spec §"實作要求"):
    - IPC channel is never opened — ``cache._fetch_via_ipc_blocking`` is patched
      to return a synthesized ``ExecutorRuntimeConfig`` per case.
    - PG connection is never opened — synthetic replay rows live in YAML, no
      live ``decision_outcomes`` SELECT.
    - Business logic is NOT mocked — real ``ExecutorAgent.execute_order``,
      real ``shadow_mode_provider`` lambda chain, real ``_execute_via_ipc``.
    - SubmitOrder IPC stub: ``paper_trading_routes._ipc_command`` is replaced
      with an in-memory recorder (no socket).

MODULE_NOTE (中):
  Wave-3 G8-02 — 靜態 parity 測試（CI 可跑），驗 Python ``ExecutorAgent`` runtime
  決策與 Rust ``RiskConfig.executor`` schema spec 一致。70 case · binary agree ≥95%。

  Scope（per PA RFC Q2）：3 個 decision point 限定，但僅 ``shadow_mode`` 已實裝
  end-to-end；``per_symbol_position_cap`` / ``max_position_pct`` Phase A schema
  已落，runtime gate 屬 G3-08 範圍，本檔以 ``pytest.skip`` 標明 deferred。

  Mock 邊界：cache IPC patch、PG 不打、SubmitOrder ``_ipc_command`` 用 recorder。
  Python ExecutorAgent + shadow_mode_provider lambda + ``_execute_via_ipc``
  全部真實跑（**不**為「mock 業務邏輯」）。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

import pytest

# conftest.py already prepends control_api_v1 to sys.path; ensure for direct runs.
# conftest.py 已加 control_api_v1 進 sys.path；獨立跑時也補一次。
_TESTS_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TESTS_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

# Defer YAML import — pyyaml is in requirements but tests should not crash on
# import if it is missing during developer Mac venv bring-up.
# 延後 yaml import — 缺包時整檔不應 crash。
try:
    import yaml  # type: ignore
    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover — venv hygiene fallback
    _YAML_AVAILABLE = False
    yaml = None  # type: ignore

from app import executor_config_cache as ecc_mod
from app.executor_agent import ExecutorAgent, ExecutorConfig
from app.executor_config_cache import ExecutorConfigCache, ExecutorRuntimeConfig


# ─────────────────────────────────────────────────────────────────────────────
# Case loading / 案例載入
# ─────────────────────────────────────────────────────────────────────────────

FIXTURE_PATH = _TESTS_DIR / "fixtures" / "executor_parity_cases.yaml"


@dataclass(frozen=True)
class ParityCase:
    """One parity test case loaded from YAML.
    從 YAML 載入的單一 parity case。"""

    case_id: str
    source: str  # "golden" | "synthetic_handcrafted"
    description: str
    config: Dict[str, Any]                   # RiskConfig.executor sub-slice
    intent: Dict[str, Any]                   # SubmitOrderIntent shape
    expected_decision: str                   # "submit" | "block_shadow"
    expected_reason: str


def _load_cases() -> List[ParityCase]:
    """Load all parity cases from YAML fixture.
    從 YAML 載入所有 parity case。"""
    if not _YAML_AVAILABLE:
        pytest.skip("PyYAML missing — install via requirements.txt")
    if not FIXTURE_PATH.exists():
        pytest.fail(f"fixture missing: {FIXTURE_PATH}")
    raw = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "cases" not in raw:
        pytest.fail("malformed fixture: top-level must be {cases: [...]}")
    out: List[ParityCase] = []
    for entry in raw["cases"]:
        out.append(
            ParityCase(
                case_id=str(entry["case_id"]),
                source=str(entry.get("source", "unknown")),
                description=str(entry.get("description", "")),
                config=dict(entry["config"]),
                intent=dict(entry["intent"]),
                expected_decision=str(entry["expected_decision"]),
                expected_reason=str(entry["expected_reason"]),
            )
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Reference spec — codifies RiskConfig.executor semantic intent
# Reference spec — 落實 RiskConfig.executor schema 的語義意圖
# ─────────────────────────────────────────────────────────────────────────────

def _reference_decide(
    *,
    shadow_mode: bool,
    max_position_pct: float,
    per_symbol_position_cap: Dict[str, float],
    intent: Dict[str, Any],
) -> Tuple[str, str]:
    """Reference decision per RiskConfig.executor schema (G8-02 Wave-3 scope).
    依 RiskConfig.executor schema 語義產出 reference 決策（G8-02 Wave-3 scope）。

    Wave-3 only checks ``shadow_mode``. Wider gates (cap / pct) are documented
    intent in the Rust schema (risk_config_advanced.rs:770-843) but their
    runtime wiring is deferred to G3-08; in this test they are pass-through
    (no block) so case-level binary parity reflects only the wired path.

    Wave-3 僅檢查 shadow_mode；cap/pct 的 runtime 接線屬 G3-08，本測試這兩條
    一律 pass-through（不 block），讓 case-level binary parity 只覆 wired 路徑。
    """
    # Defensive coerce — config came from YAML so types are loose.
    # 防禦性轉型：config 來自 YAML 型別寬鬆。
    if bool(shadow_mode):
        return ("block_shadow", "shadow_mode")
    return ("submit", "live_intent_passthrough")


# ─────────────────────────────────────────────────────────────────────────────
# Python ExecutorAgent runtime decision driver
# Python ExecutorAgent runtime 決策驅動
# ─────────────────────────────────────────────────────────────────────────────

class _IpcCallRecorder:
    """Async stub recording each SubmitOrder IPC ``_ipc_command`` call.
    記錄每次 SubmitOrder IPC ``_ipc_command`` 呼叫的 async stub。

    Mirrors the contract of ``paper_trading_routes._ipc_command``:
    ``(method: str, params: dict | None) -> Awaitable[dict]``.
    對應 ``paper_trading_routes._ipc_command`` 的 contract。
    """

    def __init__(self, *, success: bool = True, fill_price: float = 50000.0) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._success = success
        self._fill_price = fill_price

    async def __call__(self, method: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        self.calls.append({"method": method, "params": dict(params or {})})
        if not self._success:
            return {"error": "rust_engine_rejected"}
        return {
            "order_id": f"ord_parity_{len(self.calls):04d}",
            "price": self._fill_price,
            "qty": float((params or {}).get("qty", 0.0)),
            "status": "Filled",
        }


def _build_runtime_config(case_config: Dict[str, Any]) -> ExecutorRuntimeConfig:
    """Build a post-parse ExecutorRuntimeConfig snapshot from case fixture.
    從 fixture 構建解析後的 ExecutorRuntimeConfig snapshot。"""
    per_symbol_raw = case_config.get("per_symbol_position_cap", {}) or {}
    per_symbol = {str(k): float(v) for k, v in per_symbol_raw.items()}
    return ExecutorRuntimeConfig(
        shadow_mode=bool(case_config["shadow_mode"]),
        max_position_pct=float(case_config["max_position_pct"]),
        per_symbol_position_cap=per_symbol,
        config_version=1,
        fetched_at_ms=1,
    )


def _drive_python_decision(case: ParityCase) -> Tuple[str, str]:
    """Drive Python ExecutorAgent for one case → return (decision, reason).
    為單一 case 驅動 Python ExecutorAgent → 回傳 (decision, reason)。

    Real call chain exercised:
      ExecutorConfigCache snapshot patched (no IPC socket)
        → cache.shadow_mode_provider() lambda
        → ExecutorAgent.__init__(shadow_mode_provider=...)
        → execute_order()
        → _execute_via_ipc()
            → if provider() True  : ExecutionReport.error == "shadow_mode"
            → if provider() False : real submit_paper_order IPC (recorded)
    """
    cache = ExecutorConfigCache()
    snapshot = _build_runtime_config(case.config)
    # Snapshot injection bypasses IPC socket entirely.
    # 直接注入 snapshot，繞過 IPC socket。
    cache._inject_snapshot_for_tests(snapshot)
    cache._mark_initialized_for_tests()

    agent = ExecutorAgent(
        config=ExecutorConfig(),
        message_bus=None,
        paper_engine=None,
        governance_hub=None,
        audit_callback=None,
        shadow_mode_provider=cache.shadow_mode_provider(),
    )
    agent.start()
    # Inject a market price so slippage math doesn't divide by zero.
    # 注入 market price 避免 slippage 計算除零。
    agent.update_market_prices({case.intent["symbol"]: 50000.0})

    ipc_recorder = _IpcCallRecorder(success=True, fill_price=50000.0)
    with patch("app.paper_trading_routes._ipc_command", new=ipc_recorder):
        report = agent.execute_order(
            intent_id=f"parity_{case.case_id}",
            symbol=str(case.intent["symbol"]),
            side=str(case.intent["side"]),
            qty=float(case.intent["qty"]),
        )

    metadata = report.metadata or {}
    exec_path = metadata.get("execution_path")

    # Decode the runtime decision from the ExecutionReport.
    # 從 ExecutionReport 解碼 runtime 決策。
    if exec_path == "ipc_shadow":
        # Shadow path — never emits IPC.
        # Shadow 路徑：永不送 IPC。
        assert ipc_recorder.calls == [], (
            f"shadow path must not emit IPC (case={case.case_id}); "
            f"shadow 路徑不可送 IPC"
        )
        return ("block_shadow", "shadow_mode")

    if exec_path == "ipc_real":
        # Live path — emitted exactly one submit_paper_order IPC.
        # Live 路徑：恰好送出一次 submit_paper_order IPC。
        if len(ipc_recorder.calls) != 1:
            return ("error", f"unexpected_ipc_call_count={len(ipc_recorder.calls)}")
        if ipc_recorder.calls[0]["method"] != "submit_paper_order":
            return ("error", f"unexpected_method={ipc_recorder.calls[0]['method']}")
        return ("submit", "live_intent_passthrough")

    if exec_path == "ipc_error":
        return ("error", "ipc_bridge_failed")

    # Fall-through: cache pre-init or other unexpected — fail-closed shadow.
    # 缺省路徑：cache 未初始化或其他意外 — fail-closed shadow。
    if report.error == "shadow_mode":
        return ("block_shadow", "shadow_mode")
    return ("error", f"unknown_path={exec_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Test class / 測試類
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutorDecisionParity:
    """G8-02 — Python ExecutorAgent runtime vs RiskConfig.executor reference spec.
    G8-02 — Python ExecutorAgent runtime vs RiskConfig.executor reference spec。

    Distribution (per PA RFC Q2):
      30 golden fixtures      : handcrafted boundary + center coverage
      40 synthetic handcrafted: YAML literal cases (no seed / no generator /
                                no PG snapshot replay — naming clarified
                                per E2 G8-02 review; previous name implied
                                a real replay which it is not).
      Pass condition           : agree_count >= 67  (70 × 0.95 = 66.5 → 67)
    """

    @classmethod
    def setup_class(cls) -> None:
        cls.cases: List[ParityCase] = _load_cases()
        cls.golden_cases: List[ParityCase] = [
            c for c in cls.cases if c.source == "golden"
        ]
        cls.synthetic_cases: List[ParityCase] = [
            c for c in cls.cases if c.source == "synthetic_handcrafted"
        ]

    def setup_method(self) -> None:
        # Drop singleton between cases to avoid stale snapshot leak.
        # 每個 method 重置 singleton 防止 snapshot leak。
        ecc_mod._reset_for_tests()

    def teardown_method(self) -> None:
        ecc_mod._reset_for_tests()

    # ── Helpers / 輔助 ──

    def _evaluate(self, cases: List[ParityCase]) -> Tuple[int, int, List[Dict[str, Any]]]:
        """Evaluate cases → (agree_count, total, disagreements).
        評估 case 集 → (一致數, 總數, 不一致清單)。"""
        agree = 0
        disagreements: List[Dict[str, Any]] = []
        for case in cases:
            python_decision, python_reason = _drive_python_decision(case)
            rust_decision, rust_reason = _reference_decide(
                shadow_mode=bool(case.config["shadow_mode"]),
                max_position_pct=float(case.config["max_position_pct"]),
                per_symbol_position_cap=dict(case.config.get("per_symbol_position_cap") or {}),
                intent=case.intent,
            )
            same_decision = python_decision == rust_decision
            same_reason = python_reason == rust_reason
            if same_decision and same_reason:
                agree += 1
            else:
                disagreements.append(
                    {
                        "case_id": case.case_id,
                        "source": case.source,
                        "description": case.description,
                        "python": (python_decision, python_reason),
                        "reference_spec": (rust_decision, rust_reason),
                        "expected": (case.expected_decision, case.expected_reason),
                    }
                )
        return agree, len(cases), disagreements

    @staticmethod
    def _format_disagreements(disagreements: List[Dict[str, Any]]) -> str:
        """Render disagreements for operator debug.
        產生 operator debug 用的不一致摘要。"""
        if not disagreements:
            return "(no disagreements)"
        lines = []
        for d in disagreements:
            lines.append(
                f"  case_id={d['case_id']!s:32s} src={d['source']:<18s} "
                f"py={d['python']!r}  ref={d['reference_spec']!r}  "
                f"expected={d['expected']!r}"
            )
        return "\n".join(lines)

    # ── Tests / 測試 ──

    def test_fixture_loaded_correctly(self) -> None:
        """Sanity: 70 case loaded with 30 golden + 40 synthetic_handcrafted.
        體檢：70 case 載入 = 30 golden + 40 synthetic_handcrafted。"""
        assert len(self.cases) == 70, (
            f"expected 70 cases, got {len(self.cases)} (fixture drift)"
        )
        assert len(self.golden_cases) == 30, (
            f"expected 30 golden, got {len(self.golden_cases)}"
        )
        assert len(self.synthetic_cases) == 40, (
            f"expected 40 synthetic, got {len(self.synthetic_cases)}"
        )
        # All case_ids unique. / case_id 全唯一。
        ids = [c.case_id for c in self.cases]
        assert len(set(ids)) == len(ids), "duplicate case_id detected"

    def test_golden_fixtures_agree_rate(self, capsys: pytest.CaptureFixture) -> None:
        """30 golden fixtures must achieve 100% agree (handpicked boundary).
        30 個 golden fixture 必須 100% agree（手選邊界）。"""
        agree, total, disagreements = self._evaluate(self.golden_cases)
        rate = agree / total if total else 0.0
        with capsys.disabled():
            print(
                f"\n[G8-02 golden] agree={agree}/{total} "
                f"({rate * 100:.2f}%)"
            )
            if disagreements:
                print("[G8-02 golden] DISAGREEMENTS:")
                print(self._format_disagreements(disagreements))
        assert agree == total, (
            f"golden agree {agree}/{total} (<100%); disagreements:\n"
            f"{self._format_disagreements(disagreements)}"
        )

    def test_synthetic_handcrafted_agree_rate(self, capsys: pytest.CaptureFixture) -> None:
        """40 synthetic handcrafted YAML cases must achieve 100% agree.
        40 個手寫 YAML 字面量 case 必須 100% agree。

        Naming note (E2 G8-02 review): these are static YAML-literal cases
        (no seed / no generator / no PG snapshot replay). The previous name
        implied a real replay; renamed to ``synthetic_handcrafted`` to
        honestly reflect that these are handcrafted fixtures, not real
        replays from production decision_outcomes.
        命名注意（E2 G8-02 審查）：本測試中的 case 是手寫 YAML 字面量
        （無種子 / 無生成器 / 無 PG snapshot replay）。原名暗示 real replay
        誤導，改名 ``synthetic_handcrafted`` 誠實標示其為手寫 fixture，
        非從 production decision_outcomes 取的真 replay。
        """
        agree, total, disagreements = self._evaluate(self.synthetic_cases)
        rate = agree / total if total else 0.0
        with capsys.disabled():
            print(
                f"\n[G8-02 synthetic_handcrafted] agree={agree}/{total} "
                f"({rate * 100:.2f}%)"
            )
            if disagreements:
                print("[G8-02 synthetic_handcrafted] DISAGREEMENTS:")
                print(self._format_disagreements(disagreements))
        assert agree == total, (
            f"synthetic_handcrafted agree {agree}/{total} (<100%); disagreements:\n"
            f"{self._format_disagreements(disagreements)}"
        )

    def test_overall_agree_rate_ge_95pct(self, capsys: pytest.CaptureFixture) -> None:
        """Overall 70 case agree rate must be >= 95% (>=67/70 binary).
        70 case 整體 agree rate 須 ≥ 95%（≥67/70 binary）。"""
        agree, total, disagreements = self._evaluate(self.cases)
        rate = agree / total if total else 0.0
        with capsys.disabled():
            print(
                f"\n[G8-02 OVERALL] agree={agree}/{total} "
                f"({rate * 100:.2f}%) — threshold 95% (≥67/70)"
            )
            if disagreements:
                print("[G8-02 OVERALL] DISAGREEMENTS:")
                print(self._format_disagreements(disagreements))
        assert agree >= 67, (
            f"agree={agree}/{total} below 67 (95% threshold); disagreements:\n"
            f"{self._format_disagreements(disagreements)}"
        )

    def test_disagreements_logged(self, capsys: pytest.CaptureFixture) -> None:
        """If disagreements exist, ensure each is reported with full context.
        若有不一致，必須完整輸出供 operator debug。"""
        _, _, disagreements = self._evaluate(self.cases)
        if not disagreements:
            with capsys.disabled():
                print("[G8-02 disagree-log] none — clean run")
            return
        with capsys.disabled():
            print(f"[G8-02 disagree-log] {len(disagreements)} cases:")
            print(self._format_disagreements(disagreements))
        # Each disagreement record carries the 5 required diagnostic fields.
        # 每筆不一致記錄帶 5 個診斷欄位。
        for d in disagreements:
            assert "case_id" in d
            assert "python" in d
            assert "reference_spec" in d
            assert "expected" in d
            assert "source" in d


class TestExecutorDecisionParityDeferred:
    """Markers for G3-08 deferred parity slices (per_symbol_cap + max_pct).
    G3-08 deferred parity 區塊（per_symbol_cap + max_pct）的 marker。

    These tests are intentionally ``pytest.skip``ped so the gap is visible in
    the test output / CI report but does not block Wave-3 close-out.
    Per PA RFC Q2:
      "the wider gates ('per_symbol_position_cap' + 'max_position_pct')
       have schema landed in Phase A but neither Python ExecutorAgent
       nor Rust intent_processor gates SubmitOrder on them yet."
    本測試集刻意 skip，讓 gap 在 CI report 可見，但不阻塞 Wave-3 收尾。
    """

    def test_per_symbol_cap_parity_deferred(self) -> None:
        """G3-08 deferred — per_symbol_position_cap runtime gate.
        G3-08 deferred — per_symbol_position_cap runtime gate。"""
        pytest.skip(
            "Rust intent_processor cap gate depends on G3-08 — "
            "RiskConfig.executor.per_symbol_position_cap schema landed in "
            "G3-02 Phase A but neither Python ExecutorAgent nor Rust "
            "intent_processor enforces it yet. See PA RFC Q2."
        )

    def test_max_position_pct_parity_deferred(self) -> None:
        """G3-08 deferred — max_position_pct runtime gate.
        G3-08 deferred — max_position_pct runtime gate。"""
        pytest.skip(
            "Rust intent_processor max_pct gate depends on G3-08 — "
            "RiskConfig.executor.max_position_pct schema landed in "
            "G3-02 Phase A but neither Python ExecutorAgent nor Rust "
            "intent_processor enforces it yet. See PA RFC Q2."
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
