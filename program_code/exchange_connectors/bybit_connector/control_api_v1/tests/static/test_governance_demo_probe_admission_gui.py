"""Governance GUI Demo probe admission static contract tests.

Scope:
  - Authorization approval must be visually distinct from Decision Lease.
  - Decision Lease card must remain read-only/no manual approval.
  - Bounded Demo probe admission panel must expose machine-checkable gates.
  - Fast Demo promotion loop doc must preserve hard boundaries.
"""

from __future__ import annotations

from pathlib import Path


_THIS_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _THIS_DIR.parent.parent / "app" / "static"
_REPO_ROOT = _THIS_DIR.parents[5]

_TAB_GOVERNANCE_HTML = _STATIC_DIR / "tab-governance.html"
_GOVERNANCE_TAB_JS = _STATIC_DIR / "governance-tab.js"
_FAST_LOOP_DOC = _REPO_ROOT / "docs" / "agents" / "profit-first-fast-demo-promotion-loop.md"
_BASE_LOOP_DOC = _REPO_ROOT / "docs" / "agents" / "profit-first-autonomy-loop.md"


def _read(path: Path) -> str:
    assert path.exists(), f"missing test fixture: {path}"
    return path.read_text(encoding="utf-8")


def test_authorization_approval_is_not_decision_lease_approval() -> None:
    html = _read(_TAB_GOVERNANCE_HTML)
    js = _read(_GOVERNANCE_TAB_JS)

    assert 'id="auth-lease-boundary-note"' in html
    assert "Approve Authorization / 批准授權" in html
    assert "批准的是 Authorization" in html
    assert "不會批准或建立某一筆 Decision Lease" in html
    assert "Approve 按鈕批准的是 Authorization" in js


def test_decision_lease_card_is_readonly_and_no_manual_approve_surface() -> None:
    html = _read(_TAB_GOVERNANCE_HTML)

    assert 'id="lease-readonly-boundary-note"' in html
    assert "只讀短租約追踪" in html
    assert "GUI 不提供手動批准 lease 的入口" in html
    assert "not_supported" in html
    assert "/api/v1/governance/leases/approve" not in html
    assert "govApproveLease" not in html


def test_bounded_demo_probe_admission_panel_contract_present() -> None:
    html = _read(_TAB_GOVERNANCE_HTML)
    js = _read(_GOVERNANCE_TAB_JS)

    required_html = [
        'id="demo-probe-admission-card"',
        'id="demo-probe-status"',
        'id="demo-probe-runtime-detail"',
        "Candidate Identity",
        "GUI RiskConfig",
        "Loss-Control Envelope",
        "Final Lease Window",
        "Rust Order Path",
        "Promotion Chain",
    ]
    missing = [needle for needle in required_html if needle not in html]
    assert not missing, f"Demo probe admission GUI missing markers: {missing}"

    required_js = [
        "function updateDemoProbeAdmissionCard()",
        "FINAL WINDOW OPEN",
        "READY FOR RUNNER",
        "GUI 不手工批准 lease",
        "runner 才能提交 bounded Demo order",
    ]
    missing_js = [needle for needle in required_js if needle not in js]
    assert not missing_js, f"Demo probe admission JS missing markers: {missing_js}"


def test_fast_demo_promotion_loop_preserves_hard_boundaries() -> None:
    fast_doc = _read(_FAST_LOOP_DOC)
    base_doc = _read(_BASE_LOOP_DOC)

    required = [
        "DEMO_ELIGIBLE_PARTIAL",
        "DEMO_READY_FINAL_WINDOW",
        "GUI/Rust RiskConfig cap lineage",
        "active Decision Lease in the final window",
        "Rust authority/order supplier path",
        "10 USDT",
        "Final Window",
        "after-cost review",
        "LIVE_REVIEW_REQUIRED",
        "GUI 不直接送交易所訂單",
        "不直接降低 Cost Gate",
    ]
    missing = [needle for needle in required if needle not in fast_doc]
    assert not missing, f"Fast Demo promotion loop doc missing required boundary text: {missing}"

    assert "profit-first-fast-demo-promotion-loop.md" in base_doc
