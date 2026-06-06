"""mlde_shadow_advisor residual hook 安全測試：env-flag OFF=零行為、fail-soft。"""

from __future__ import annotations

from program_code.ml_training import mlde_shadow_advisor as adv
from program_code.ml_training import residual_alpha_cycle as cyc


class _Cfg:
    engine_mode = "demo"


class _Rec:
    def __init__(self, strategy, symbol):
        self.strategy_name = strategy
        self.symbol = symbol
        self.payload = {}


def _raise(*_a, **_k):
    raise AssertionError("psycopg2.connect should NOT be called when flag OFF")


def test_hook_env_off_is_noop(monkeypatch):
    monkeypatch.setattr(cyc, "residual_producer_enabled", lambda: False)
    import psycopg2
    monkeypatch.setattr(psycopg2, "connect", _raise)  # env OFF 不該走到連線
    n = adv._maybe_attach_residual_evidence("dsn", [_Rec("grid_trading", "BTCUSDT")], _Cfg())
    assert n == 0  # 零行為改變


def test_hook_fail_soft_on_producer_error(monkeypatch):
    monkeypatch.setattr(cyc, "residual_producer_enabled", lambda: True)
    import psycopg2

    def _boom(*_a, **_k):
        raise RuntimeError("PG down")

    monkeypatch.setattr(psycopg2, "connect", _boom)
    # producer 出錯不得拋出（fail-soft，絕不中斷 recommendation cycle）
    n = adv._maybe_attach_residual_evidence("dsn", [_Rec("grid_trading", "BTCUSDT")], _Cfg())
    assert n == 0


def test_hook_attaches_when_enabled(monkeypatch):
    monkeypatch.setattr(cyc, "residual_producer_enabled", lambda: True)
    monkeypatch.setattr(cyc, "attach_residual_reports", lambda recs, conn, **k: len(recs))
    import psycopg2

    class _FakeConn:
        def set_session(self, **k):
            pass

        def close(self):
            pass

    monkeypatch.setattr(psycopg2, "connect", lambda *a, **k: _FakeConn())
    recs = [_Rec("grid_trading", "BTCUSDT"), _Rec("ma_crossover", None)]
    assert adv._maybe_attach_residual_evidence("dsn", recs, _Cfg()) == 2
