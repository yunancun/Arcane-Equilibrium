"""HTTP -> real RiskViewClient -> in-memory IPC transport engine contract."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from test_risk_routes_live_config_gate import _make_app, _operator_actor


class EngineTransport:
    def __init__(self):
        self.configs = {e: {} for e in ('paper', 'demo', 'live')}
        self.versions = {e: 1 for e in self.configs}
        self.calls = []

    async def connect(self):
        pass

    async def call(self, method, params=None, **kw):
        params = params or {}
        self.calls.append((method, deepcopy(params)))
        engine = params.get('engine', 'paper') # Rust compatibility default
        if method == 'patch_risk_config':
            for section, values in params['patch'].items():
                self.configs[engine].setdefault(section, {}).update(deepcopy(values))
            self.versions[engine] += 1
        return {'config': deepcopy(self.configs[engine]), 'version': self.versions[engine]}


@pytest.mark.parametrize('suffix,body,section', [
    ('config/global', {'max_leverage': 7}, 'limits'),
    ('config/category/linear', {'max_leverage': 7}, 'overrides'),
    ('agent-adjust', {'effective_stop_loss_pct': 2}, 'agent'),
])
def test_demo_write_and_readback_never_mutate_paper(monkeypatch, suffix, body, section):
    app = _make_app(_operator_actor())
    from app import risk_routes as routes
    ipc = EngineTransport()
    monkeypatch.setattr(routes, 'EngineIPCClient', lambda: ipc)
    with TestClient(app) as client:
        response = client.post('/api/v1/paper/risk/' + suffix, json={**body, 'engine': 'demo'})
    assert response.status_code == 200, response.text
    assert ipc.configs['paper'] == {}
    assert section in ipc.configs['demo']
    assert response.json()['data']['engine'] == 'demo'
    assert response.json()['data_category'] == 'demo_risk_control'
    assert all(p.get('engine') == 'demo' for _, p in ipc.calls)


def test_live_response_never_claims_paper_simulation():
    from app.risk_routes import _risk_response
    response = _risk_response({'engine': 'live', 'version': 3})
    assert response['is_simulated'] is False
    assert response['data_category'] == 'live_risk_control'


@pytest.mark.parametrize('path', ['config', 'status', 'config/category/linear'])
def test_unavailable_engine_does_not_return_successful_empty_or_cached_data(monkeypatch, path):
    app = _make_app(_operator_actor())
    from app import risk_routes as routes
    class OfflineTransport(EngineTransport):
        async def call(self, *a, **kw):
            raise RuntimeError('transport down')
    monkeypatch.setattr(routes, 'EngineIPCClient', OfflineTransport)
    with TestClient(app) as client:
        response = client.get('/api/v1/paper/risk/' + path)
    assert response.status_code == 500
    assert 'rust_engine_unavailable' in response.text


@pytest.mark.parametrize('suffix,body', [
    ('config/global', {'engine': 'demo', 'max_cost_edge_ratio': 1.2}),
    ('config/category/linear', {'engine': 'demo', 'perp_max_funding_rate_abs': .01}),
])
def test_unsupported_engine_fields_are_rejected_before_any_write(monkeypatch, suffix, body):
    app = _make_app(_operator_actor())
    from app import risk_routes as routes
    ipc = EngineTransport()
    monkeypatch.setattr(routes, 'EngineIPCClient', lambda: ipc)
    with TestClient(app) as client:
        response = client.post('/api/v1/paper/risk/' + suffix, json=body)
    assert response.status_code == 422
    assert all(not method.startswith('patch_') for method, _ in ipc.calls)


def test_cold_client_does_not_treat_existing_version_as_write_success(monkeypatch):
    app = _make_app(_operator_actor())
    from app import risk_routes as routes
    class DroppingTransport(EngineTransport):
        async def call(self, method, params=None, **kw):
            if method == 'patch_risk_config':
                return {'version': 1} # No state change; first refresh must not fake an advance.
            return await super().call(method, params, **kw)
    monkeypatch.setattr(routes, 'EngineIPCClient', DroppingTransport)
    with TestClient(app) as client:
        response = client.post('/api/v1/paper/risk/config/global', json={'engine': 'demo', 'max_leverage': 7})
    assert response.status_code == 500
