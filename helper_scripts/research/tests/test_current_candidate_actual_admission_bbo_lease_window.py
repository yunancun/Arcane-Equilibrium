from __future__ import annotations

import datetime as dt
import json

from cost_gate_learning_lane import bbo_freshness_public_quote_capture as quote_mod
from cost_gate_learning_lane import (
    current_candidate_actual_admission_bbo_lease_window as mod,
)


NOW = dt.datetime(2026, 6, 27, 8, 45, tzinfo=dt.timezone.utc)
NOW_MS = int(NOW.timestamp() * 1000)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


class Clock:
    def __init__(self, start_ms: int = NOW_MS):
        self.now_ms = start_ms

    def now(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(self.now_ms / 1000.0, tz=dt.timezone.utc)

    def monotonic(self) -> float:
        return self.now_ms / 1000.0

    def advance(self, ms: int) -> None:
        self.now_ms += ms


class FakeHTTPResponse:
    def __init__(self, payload: dict, *, status: int = 200):
        self.status = status
        self.headers = {"X-Bapi-Limit": "120"}
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self._raw


class FakeOpener:
    def __init__(self, clock: Clock, payloads: dict[str, dict] | None = None):
        self.clock = clock
        self.payloads = payloads or _payloads()
        self.requests = []

    def __call__(self, req, timeout=None):  # noqa: ANN001, ARG002
        self.requests.append(req)
        path = __import__("urllib.parse").parse.urlsplit(req.full_url).path
        self.clock.advance(10)
        if path not in self.payloads:
            raise AssertionError(f"unexpected path: {path}")
        return FakeHTTPResponse(self.payloads[path])


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    payload.update(overrides)
    if "side_cell_key" not in overrides:
        payload["side_cell_key"] = (
            f"{payload['strategy_name']}|{payload['symbol']}|{payload['side']}"
        )
    return payload


def _admission_review(**overrides) -> dict:
    payload = {
        "schema_version": mod.gate_evidence.ADMISSION_REVIEW_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.gate_evidence.ADMISSION_REVIEW_BLOCKED_STATUS,
        "candidate": _candidate(),
        "source_blockers": [],
        "authority_contamination_reasons": [],
        "risk_semantics": {
            "gui_risk_config_is_source_of_truth": True,
            "gui_p1_risk_trade_pct": 10.0,
            "per_trade_risk_pct_fraction": 0.1,
            "position_size_max_pct": 25.0,
            "account_equity_usdt": 9552.43426257,
            "per_trade_budget_usdt": 955.24342626,
            "single_position_budget_usdt": 2388.10856564,
            "max_order_notional_usdt": 0.0,
            "resolved_cap_usdt": 955.24342626,
            "rounded_notional_usdt": 954.9165,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "bounded_probe_local_cap_usdt_is_authority": False,
        },
        "admission_envelope_preview": {
            "candidate": _candidate(),
            "risk_limits": {
                "per_order_cap_usdt": 955.24342626,
                "per_trade_risk_pct_fraction": 0.1,
                "per_trade_risk_pct_display": 10.0,
                "position_size_max_pct": 25.0,
                "account_equity_usdt": 9552.43426257,
                "per_trade_budget_usdt": 955.24342626,
                "single_position_budget_usdt": 2388.10856564,
                "max_order_notional_usdt": 0.0,
            },
            "order_shape": {
                "rounded_notional_usdt": 954.9165,
                "rounded_qty": 145.5,
                "limit_price": 6.563,
            },
            "runtime_admission_ready": False,
            "order_admission_ready": False,
        },
        "answers": {
            "review_contract_ready": True,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _gate_packet(**overrides) -> dict:
    payload = {
        "schema_version": mod.lease_validation.GATE_PACKET_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.lease_validation.GATE_BLOCKED_STATUS,
        "candidate": _candidate(),
        "runtime_admission_blockers": ["decision_lease_valid"],
        "source_blockers": [],
        "authority_contamination_reasons": [],
        "risk_context": {
            "gui_risk_config_is_source_of_truth": True,
            "sizing_source": "guardian_adjusted_sizing_proposal",
            "account_equity_usdt": 9552.43426257,
            "resolved_cap_usdt": 955.24342626,
            "single_position_budget_usdt": 2388.10856564,
            "effective_single_order_cap_usdt": 955.24342626,
            "per_trade_budget_usdt": 955.24342626,
            "max_order_notional_usdt": 0.0,
            "rounded_qty": 145.5,
            "rounded_notional_usdt": 954.9165,
            "per_trade_risk_pct_fraction": 0.1,
            "per_trade_risk_pct_display": 10.0,
            "position_size_max_pct": 25.0,
        },
        "answers": {
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "decision_lease_emitted": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
        },
    }
    payload.update(overrides)
    return payload


def _sizing_proposal(**overrides) -> dict:
    payload = {
        "schema_version": mod.lease_validation.SIZING_PROPOSAL_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.lease_validation.SIZING_READY_STATUS,
        "candidate": _candidate(),
        "source_blockers": [],
        "authority_contamination_reasons": [],
        "risk_context": {
            "gui_risk_config_is_source_of_truth": True,
            "risk_source_of_truth": "GUI-backed Rust RiskConfig",
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "account_equity_usdt": 9552.43426257,
            "gui_resolved_cap_usdt": 955.24342626,
            "per_trade_risk_pct_fraction": 0.1,
            "per_trade_risk_pct_display": 10.0,
            "position_size_max_pct": 25.0,
            "per_trade_budget_usdt": 955.24342626,
            "single_position_budget_usdt": 2388.10856564,
            "max_order_notional_usdt": 0.0,
            "guardian_risk_level": "NORMAL",
            "guardian_position_size_multiplier": 1.0,
            "guardian_adjusted_cap_usdt": 955.24342626,
            "local_10_usdt_cap_is_global_risk_authority": False,
        },
        "sizing_proposal": {
            "proposed_rounded_qty": 145.5,
            "proposed_rounded_notional_usdt": 954.9165,
            "single_position_budget_usdt": 2388.10856564,
            "effective_single_order_cap_usdt": 955.24342626,
            "notional_lte_guardian_adjusted_cap": True,
            "notional_lte_gui_resolved_cap": True,
            "notional_lte_single_position_budget": True,
            "notional_lte_effective_single_order_cap": True,
            "notional_gte_min_notional": True,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
        },
        "answers": {
            "review_contract_ready": True,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _required_requests(symbol: str = "AVAXUSDT") -> list[dict]:
    return [
        {
            "label": "server_time",
            "method": "GET",
            "path": quote_mod.TIME_PATH,
            "query": {},
        },
        {
            "label": "ticker",
            "method": "GET",
            "path": quote_mod.TICKERS_PATH,
            "query": {"category": "linear", "symbol": symbol},
        },
        {
            "label": "instrument",
            "method": "GET",
            "path": quote_mod.INSTRUMENTS_PATH,
            "query": {"category": "linear", "symbol": symbol},
        },
    ]


def _answers(**overrides) -> dict:
    payload = {
        "current_candidate_no_order_refresh_envelope_ready": True,
        "public_quote_capture_performed": False,
        "network_call_performed": False,
        "bybit_call_performed": False,
        "bybit_public_market_data_call_performed": False,
        "bybit_private_call_performed": False,
        "private_endpoint_called": False,
        "order_submission_performed": False,
        "order_admission_ready": False,
        "order_authority_granted": False,
        "probe_authority_granted": False,
        "live_authority_granted": False,
        "runtime_mutation_performed": False,
        "pg_write_performed": False,
        "global_cost_gate_lowering_recommended": False,
    }
    payload.update(overrides)
    return payload


def _envelope(**overrides) -> dict:
    candidate = overrides.pop("candidate", _candidate())
    payload = {
        "schema_version": mod.quote_refresh.CURRENT_ENVELOPE_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.quote_refresh.CURRENT_ENVELOPE_READY_STATUS,
        "candidate": candidate,
        "source_inputs": {
            "authority_preserved": True,
            "bounded_auth_no_authority": True,
        },
        "cap_resolution": {
            "risk_source_of_truth": "GUI-backed Rust RiskConfig",
            "account_equity_usdt": 9552.43426257,
            "per_trade_risk_pct_fraction": 0.1,
            "per_trade_risk_pct_display": 10.0,
            "position_size_max_pct": 25.0,
            "per_trade_budget_usdt": 955.24342626,
            "single_position_budget_usdt": 2388.10856564,
            "max_order_notional_usdt": 0.0,
            "resolved_cap_usdt": 955.24342626,
            "bounded_probe_local_cap_usdt_is_authority": False,
            "cap_formula": (
                "min(account_equity_usdt * per_trade_risk_pct, "
                "account_equity_usdt * position_size_max_pct / 100, "
                "max_order_notional_usdt if configured)"
            ),
        },
        "refresh_envelope": {
            "request_envelope_review": {
                "method": "GET",
                "required_requests": _required_requests(candidate["symbol"]),
                "allowed_base_urls": sorted(quote_mod.ALLOWED_BASE_URLS),
                "headers_allowlist": ["User-Agent"],
                "auth_or_cookie_headers_allowed": False,
                "private_or_order_paths_allowed": False,
                "redirects_allowed": False,
                "exact_query_required": True,
                "additional_requests_allowed": False,
            },
        },
        "summary": {
            "current_candidate_no_order_refresh_envelope_ready": True,
            "public_quote_capture_performed": False,
            "network_call_performed": False,
            "order_admission_ready": False,
            "request_count": 3,
            "max_fresh_bbo_age_ms": 1000,
            "resolved_cap_usdt": 955.24342626,
            "gui_p1_risk_trade_pct": 10.0,
            "local_10_usdt_cap_is_global_risk_authority": False,
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _payloads(
    *,
    symbol: str = "AVAXUSDT",
    bid: str = "6.562",
    ask: str = "6.563",
    bid_size: str = "120.0",
    ask_size: str = "110.0",
    last_price: str = "6.5625",
    mark_price: str = "6.5624",
    tick_size: str = "0.001",
    qty_step: str = "0.1",
    min_notional: str = "5",
    ticker_time_ms: int | None = NOW_MS + 20,
    instrument_status: str = "Trading",
) -> dict[str, dict]:
    return {
        quote_mod.TIME_PATH: {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"timeSecond": str(int((NOW_MS + 10) / 1000))},
            "time": NOW_MS + 10,
        },
        quote_mod.TICKERS_PATH: {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "linear",
                "list": [
                    {
                        "symbol": symbol,
                        "bid1Price": bid,
                        "ask1Price": ask,
                        "bid1Size": bid_size,
                        "ask1Size": ask_size,
                        "lastPrice": last_price,
                        "markPrice": mark_price,
                    }
                ],
            },
            "time": ticker_time_ms,
        },
        quote_mod.INSTRUMENTS_PATH: {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "linear",
                "list": [
                    {
                        "symbol": symbol,
                        "status": instrument_status,
                        "priceFilter": {"tickSize": tick_size},
                        "lotSizeFilter": {
                            "qtyStep": qty_step,
                            "minNotionalValue": min_notional,
                        },
                    }
                ],
            },
            "time": NOW_MS + 30,
        },
    }


def _status_payload(lease_count: int) -> dict:
    return {
        "enabled": True,
        "mode": "Normal",
        "risk_level": "Normal",
        "auth_effective_count": 2,
        "auth_pending_approval": 0,
        "lease_live_count": lease_count,
        "oms_active_count": 0,
    }


def _risk_state_payload() -> dict:
    return {
        "level": "Normal",
        "new_entries_allowed": True,
        "position_size_multiplier": 1.0,
        "reduce_only": False,
        "active_de_risking": False,
        "emergency_stops": False,
        "requires_operator": False,
    }


def test_dry_run_validates_source_without_network_or_lease() -> None:
    calls: list[str] = []
    clock = Clock()
    opener = FakeOpener(clock)

    async def dispatcher(method: str, params: dict, timeout: float) -> dict:  # noqa: ARG001
        calls.append(method)
        raise AssertionError("dispatcher should not be called")

    packet = mod.build_current_candidate_actual_admission_bbo_lease_window(
        admission_review=_admission_review(),
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        current_candidate_envelope=_envelope(),
        run=False,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        dispatcher=dispatcher,
        opener=opener,
    )

    assert packet["status"] == mod.DRY_RUN_READY_STATUS
    assert packet["source_blockers"] == []
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["public_quote_capture_performed"] is False
    assert packet["risk_context"]["resolved_cap_usdt"] == 955.24342626
    assert packet["risk_context"]["per_trade_risk_pct_fraction"] == 0.1
    assert packet["risk_context"]["position_size_max_pct"] == 25.0
    assert opener.requests == []
    assert calls == []


def test_explicit_run_refreshes_actual_bbo_and_gate_during_active_window() -> None:
    calls: list[str] = []
    clock = Clock()
    opener = FakeOpener(clock)

    async def dispatcher(method: str, params: dict, timeout: float) -> dict | list:  # noqa: ARG001
        calls.append(method)
        if method == "governance.acquire_lease":
            return {"lease_id": "lease:actual-bbo", "outcome": "Active"}
        if method == "governance.get_status":
            return _status_payload(lease_count=1)
        if method == "governance.list_leases":
            return [
                {
                    "lease_id": "lease:actual-bbo",
                    "state": "ACTIVE",
                    "scope": "TRADE_ENTRY",
                    "environment": "demo",
                    "demo_only": True,
                    "expires_at_utc": "2026-06-27T08:46:00+00:00",
                }
            ]
        if method == "governance.get_risk_state":
            return _risk_state_payload()
        if method == "governance.release_lease":
            return {"ok": True}
        raise AssertionError(method)

    packet = mod.build_current_candidate_actual_admission_bbo_lease_window(
        admission_review=_admission_review(),
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        current_candidate_envelope=_envelope(),
        run=True,
        require_env=False,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        dispatcher=dispatcher,
        opener=opener,
    )

    assert packet["status"] == mod.DONE_STATUS
    assert packet["runtime_blockers"] == []
    assert packet["loss_control_blockers"] == []
    assert calls[0] == "governance.acquire_lease"
    assert calls[-1] == "governance.release_lease"
    assert len(opener.requests) == 3
    assert packet["active_window"]["quote_started_after_lease_acquire"] is True
    assert packet["active_window"]["lease_released_before_artifact"] is True
    assert packet["answers"]["actual_admission_bbo_refreshed_during_active_lease"] is True
    assert (
        packet["answers"]["fresh_actual_admission_bbo_and_gate_ready_during_window"]
        is True
    )
    assert packet["answers"]["runtime_admission_ready_after_release"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["bybit_public_market_data_call_performed"] is True
    assert packet["answers"]["bybit_private_call_performed"] is False
    assert packet["actual_admission_bbo"]["resolved_cap_usdt"] == 955.24342626
    assert (
        packet["actual_admission_bbo"]["effective_single_order_cap_usdt"]
        == 955.24342626
    )
    assert (
        packet["actual_admission_bbo"]["single_position_budget_usdt"]
        == 2388.10856564
    )
    assert (
        packet["actual_admission_bbo"]["local_10_usdt_cap_is_global_risk_authority"]
        is False
    )
    assert packet["actual_admission_bbo"]["rounded_notional_usdt"] <= 955.24342626
    nested = packet["active_window_gate_evidence"]
    assert nested["status"] == mod.gate_evidence.READY_NO_ORDER_STATUS
    assert nested["decision_lease_gate_artifact"]["valid_for_current_candidate"] is True
    assert nested["guardian_risk_gate_artifact"]["valid_for_current_candidate"] is True


def test_authority_contamination_blocks_before_acquire_or_network() -> None:
    calls: list[str] = []
    clock = Clock()
    opener = FakeOpener(clock)

    async def dispatcher(method: str, params: dict, timeout: float) -> dict:  # noqa: ARG001
        calls.append(method)
        raise AssertionError("dispatcher should not be called")

    gate = _gate_packet(
        answers={
            "runtime_admission_ready": False,
            "order_admission_ready": True,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "decision_lease_emitted": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
        }
    )

    packet = mod.build_current_candidate_actual_admission_bbo_lease_window(
        admission_review=_admission_review(),
        gate_packet=gate,
        sizing_proposal=_sizing_proposal(),
        current_candidate_envelope=_envelope(),
        run=True,
        require_env=False,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        dispatcher=dispatcher,
        opener=opener,
    )

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert "lease_preflight_authority_boundary_violation" in packet[
        "authority_contamination_reasons"
    ]
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["public_quote_capture_performed"] is False
    assert opener.requests == []
    assert calls == []


def test_stale_admission_10_usdt_cap_blocks_before_acquire_or_network() -> None:
    calls: list[str] = []
    clock = Clock()
    opener = FakeOpener(clock)
    admission = _admission_review()
    admission["admission_envelope_preview"]["risk_limits"]["per_order_cap_usdt"] = 10.0

    async def dispatcher(method: str, params: dict, timeout: float) -> dict:  # noqa: ARG001
        calls.append(method)
        raise AssertionError("dispatcher should not be called")

    packet = mod.build_current_candidate_actual_admission_bbo_lease_window(
        admission_review=admission,
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        current_candidate_envelope=_envelope(),
        run=True,
        require_env=False,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        dispatcher=dispatcher,
        opener=opener,
    )

    assert packet["status"] == mod.SOURCE_NOT_READY_STATUS
    assert "admission_review_cap_mismatch_current_candidate_envelope" in packet[
        "source_blockers"
    ]
    assert (
        "admission_review_stale_local_10_usdt_cap_mismatch_gui_envelope"
        in packet["source_blockers"]
    )
    assert packet["source_preflight"]["admission_context"]["resolved_cap_usdt"] == 10.0
    assert packet["source_preflight"]["cap_resolution"]["resolved_cap_usdt"] == 955.24342626
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["public_quote_capture_performed"] is False
    assert opener.requests == []
    assert calls == []


def test_admission_single_position_budget_mismatch_blocks_before_acquire_or_network() -> None:
    calls: list[str] = []
    clock = Clock()
    opener = FakeOpener(clock)
    admission = _admission_review()
    admission["admission_envelope_preview"]["risk_limits"][
        "single_position_budget_usdt"
    ] = 10.0

    async def dispatcher(method: str, params: dict, timeout: float) -> dict:  # noqa: ARG001
        calls.append(method)
        raise AssertionError("dispatcher should not be called")

    packet = mod.build_current_candidate_actual_admission_bbo_lease_window(
        admission_review=admission,
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        current_candidate_envelope=_envelope(),
        run=True,
        require_env=False,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        dispatcher=dispatcher,
        opener=opener,
    )

    assert packet["status"] == mod.SOURCE_NOT_READY_STATUS
    assert "admission_review_single_position_budget_usdt_mismatch" in packet[
        "source_blockers"
    ]
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["public_quote_capture_performed"] is False
    assert opener.requests == []
    assert calls == []


def test_stale_bbo_blocks_loss_control_but_releases_lease() -> None:
    calls: list[str] = []
    clock = Clock()
    opener = FakeOpener(clock, _payloads(ticker_time_ms=NOW_MS - 5000))

    async def dispatcher(method: str, params: dict, timeout: float) -> dict | list:  # noqa: ARG001
        calls.append(method)
        if method == "governance.acquire_lease":
            return {"lease_id": "lease:actual-bbo", "outcome": "Active"}
        if method == "governance.get_status":
            return _status_payload(lease_count=1)
        if method == "governance.list_leases":
            return [{"lease_id": "lease:actual-bbo", "state": "ACTIVE"}]
        if method == "governance.get_risk_state":
            return _risk_state_payload()
        if method == "governance.release_lease":
            return {"ok": True}
        raise AssertionError(method)

    packet = mod.build_current_candidate_actual_admission_bbo_lease_window(
        admission_review=_admission_review(),
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        current_candidate_envelope=_envelope(),
        run=True,
        require_env=False,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        dispatcher=dispatcher,
        opener=opener,
    )

    assert packet["status"] == mod.BLOCKED_BY_LOSS_CONTROL_STATUS
    assert "bbo_freshness_exceeds_gate" in packet["loss_control_blockers"]
    assert packet["answers"]["actual_admission_bbo_refreshed_during_active_lease"] is False
    assert packet["answers"]["decision_lease_release_performed"] is True
    assert calls[-1] == "governance.release_lease"
    assert len(opener.requests) == 3


def test_release_failure_blocks_runtime_result() -> None:
    clock = Clock()
    opener = FakeOpener(clock)

    async def dispatcher(method: str, params: dict, timeout: float) -> dict | list:  # noqa: ARG001
        if method == "governance.acquire_lease":
            return {"lease_id": "lease:actual-bbo", "outcome": "Active"}
        if method == "governance.get_status":
            return _status_payload(lease_count=1)
        if method == "governance.list_leases":
            return [{"lease_id": "lease:actual-bbo", "state": "ACTIVE"}]
        if method == "governance.get_risk_state":
            return _risk_state_payload()
        if method == "governance.release_lease":
            return {"ok": False}
        raise AssertionError(method)

    packet = mod.build_current_candidate_actual_admission_bbo_lease_window(
        admission_review=_admission_review(),
        gate_packet=_gate_packet(),
        sizing_proposal=_sizing_proposal(),
        current_candidate_envelope=_envelope(),
        run=True,
        require_env=False,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        dispatcher=dispatcher,
        opener=opener,
    )

    assert packet["status"] == mod.BLOCKED_BY_RUNTIME_STATUS
    assert "lease_release_failed" in packet["runtime_blockers"]
    assert packet["answers"]["decision_lease_acquire_performed"] is True
    assert packet["answers"]["decision_lease_release_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
