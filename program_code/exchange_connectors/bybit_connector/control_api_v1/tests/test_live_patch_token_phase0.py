"""
PHASE 0 AUTH-1 — live-patch token minter + 三 route engine-gate 測試。

MODULE_NOTE (中):
  覆蓋 design §0.6 測試矩陣的 Python 層 + 跨語言命門：
    - T12（命門）：canonical_json bytes / canonical_patch_hash 與 Rust live_authz.rs
      fixture byte-identical（含浮點/巢狀/中文 key/科學記號）。整機制的命門。
    - T1（operator 必測）：POST /agent-adjust engine=live → 403 agent_source_live_write_forbidden，
      0 mutation。
    - T9：POST /config/global engine=live 缺 5-gate → 409 live_gate_failed。
    - T11：engine=demo/paper（及不傳 engine）三 route → 維持既有行為、無 token 需求、0 回歸。
    - T13：secret 撤除 → mint raise（fail-closed kill-switch）。
    - minter 正確性：bind-string / nonce 隨機 / ts / token 三欄 / 浮點字串化 mirror。
    - 既有 5-gate live 路徑（update_per_engine_global_config）已補 token（在
      test_risk_routes_live_config_gate.py 驗證）。

  Mac mock pytest：本檔不驗 Rust hot-reload / 真 PG 落 row（E4 Linux 實證）。
  跨語言 byte-equal 由 Rust fixture sha256 常數對齊（live_authz.rs print_t12_fixture_hashes
  產出，下方 _RUST_T12_HASHES 嵌入）。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
import unittest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

# ── Path setup ────────────────────────────────────────────────────────────────
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app import live_patch_token as lpt  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# ── Rust fixture hashes（live_authz.rs::print_t12_fixture_hashes 產出，2026-06-17）──
# 這些是 Rust serde_json canonicalizer 對同一 JSON 的 SHA256；Python canonical_patch_hash
# 必逐一相符 → 證 token bind-string 跨語言 byte-equal（U-P0-1 命門）。
_RUST_T12_HASHES = [
    "267d7666548c67567718b069a95bf6bac682d5e51bde8b613236ef870e4ad565",
    "de47713b6f4991423558f4d1a4673b3e299a4dd80cb0c48ae1521874be1ca6a9",
    "48e80f50106ff3d8f619cc084a645f78f13377a050e9b0b231011cbb53ebcb51",
    "f0584c3633217d257470d8b01408910099b2f57f3ab2f756e4803b49849eb3a6",
    "c7ec31391287801019dd5826ce1e7cfffcb77e6a82e1e12abe560fcffa73a75a",
]
_T12_FIXTURES = [
    {"limits": {"leverage_max": 50.0, "per_trade_risk_pct": 0.03}, "agent": {"size_multiplier": 1.0}},
    {"cost_gate": {"k_taker": 0.0000001, "min_confidence": 0.625}},
    {"b": 2, "a": 1, "中文键": "值", "nested": {"z": 0.1, "y": -0.0, "x": 100000000.0}},
    {"arr": [1, 2.5, "three", {"k": 0.03}], "flag": True, "none": None},
    {"big": 1e20, "small": 1.5e-10, "whole": 3.0, "neg": -42.75},
]
# 對應的 Rust canonical bytes（明確 byte-equal 斷言，不只 hash）。
_T12_RUST_BYTES = [
    '{"agent":{"size_multiplier":1.0},"limits":{"leverage_max":50.0,"per_trade_risk_pct":0.03}}',
    '{"cost_gate":{"k_taker":1e-7,"min_confidence":0.625}}',
    '{"a":1,"b":2,"nested":{"x":100000000.0,"y":-0.0,"z":0.1},"中文键":"值"}',
    '{"arr":[1,2.5,"three",{"k":0.03}],"flag":true,"none":null}',
    '{"big":1e+20,"neg":-42.75,"small":1.5e-10,"whole":3.0}',
]


class TestT12CanonicalInterop(unittest.TestCase):
    """命門：Python canonical 與 Rust serde_json byte-identical。"""

    def test_canonical_bytes_match_rust(self) -> None:
        for i, (fix, expected) in enumerate(zip(_T12_FIXTURES, _T12_RUST_BYTES)):
            got = lpt.canonical_json(fix).decode("utf-8")
            self.assertEqual(got, expected, f"T12[{i}] canonical bytes diverge from Rust")

    def test_canonical_hash_match_rust(self) -> None:
        for i, (fix, rh) in enumerate(zip(_T12_FIXTURES, _RUST_T12_HASHES)):
            self.assertEqual(lpt.canonical_patch_hash(fix), rh, f"T12[{i}] hash diverge from Rust")

    def test_naive_json_dumps_would_diverge(self) -> None:
        """反向證：naive json.dumps 對科學記號值與 Rust 分歧（故必須用 mirror）。"""
        import json
        naive = json.dumps(_T12_FIXTURES[1], sort_keys=True, separators=(",", ":")).encode()
        # fixture[1] 含 1e-07：naive 給 "1e-07"，Rust/mirror 給 "1e-7"
        self.assertNotEqual(naive.decode(), _T12_RUST_BYTES[1])
        self.assertIn("1e-07", naive.decode())

    def test_rust_serde_float_str_samples(self) -> None:
        f = lpt._rust_serde_float_str
        self.assertEqual(f(0.03), "0.03")
        self.assertEqual(f(50.0), "50.0")
        self.assertEqual(f(1e-7), "1e-7")  # 非 1e-07
        self.assertEqual(f(0.00001), "0.00001")  # Rust 仍十進位，Python naive 會給 1e-05
        self.assertEqual(f(1e20), "1e+20")
        self.assertEqual(f(-0.0), "-0.0")
        self.assertEqual(f(100000000.0), "100000000.0")


class TestMinter(unittest.TestCase):
    """minter 正確性 + kill-switch。"""

    def test_mint_produces_three_fields_and_valid_hmac(self) -> None:
        secret = "minttest-secret"
        method = "patch_risk_config"
        patch_obj = {"limits": {"leverage_max": 50.0}}
        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": secret}):
            out = lpt.mint_live_authz_token(method, patch_obj)
        self.assertEqual(set(out), {"live_authz_token", "live_authz_nonce", "live_authz_ts"})
        self.assertEqual(len(out["live_authz_nonce"]), 32)  # 16 bytes hex
        # 手動重建 bind-string + HMAC 驗 token 正確（鏡 Rust verify）
        h = lpt.canonical_patch_hash(patch_obj)
        bind = b"\x1f".join([
            h.encode("ascii"), b"live", method.encode(),
            str(out["live_authz_ts"]).encode(), out["live_authz_nonce"].encode(),
        ])
        expect = hmac.new(secret.encode(), bind, hashlib.sha256).hexdigest()
        self.assertEqual(out["live_authz_token"], expect)

    def test_mint_nonce_is_random(self) -> None:
        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "s"}):
            a = lpt.mint_live_authz_token("patch_risk_config", {"x": 1.0})
            b = lpt.mint_live_authz_token("patch_risk_config", {"x": 1.0})
        self.assertNotEqual(a["live_authz_nonce"], b["live_authz_nonce"])

    def test_secret_killswitch_mint_raises(self) -> None:
        """T13：撤除 secret → mint raise（fail-closed，無 token 不可能鑄）。"""
        env = dict(os.environ)
        env.pop("OPENCLAW_LIVE_PATCH_SECRET", None)
        env.pop("OPENCLAW_LIVE_PATCH_SECRET_FILE", None)
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                lpt.mint_live_authz_token("patch_risk_config", {"x": 1.0})


class TestGeneralizedMintInterop(unittest.TestCase):
    """FIX 2：generalize 後的 call_params_with_token / hash_target_for 與 Rust
    canonical_hash_for 兩分支裁決逐字對齊（patch 類 vs 非 patch 類）。"""

    def test_hash_target_patch_branch(self) -> None:
        """patch 類：hash 對象 = params["patch"]（與 Rust 一致）。"""
        params = {"engine": "live", "patch": {"limits": {"leverage_max": 50.0}}, "source": "operator"}
        self.assertEqual(lpt.hash_target_for("patch_risk_config", params), {"limits": {"leverage_max": 50.0}})

    def test_hash_target_nonpatch_branch_strips_token_and_engine(self) -> None:
        """非 patch 類：hash 對象 = params 去 token 三欄 + engine（與 Rust 一致）。"""
        params = {
            "engine": "live", "enabled": True, "symbol": "BTCUSDT",
            "live_authz_token": "x", "live_authz_nonce": "y", "live_authz_ts": 99,
        }
        self.assertEqual(
            lpt.hash_target_for("set_dynamic_risk_enabled", params),
            {"enabled": True, "symbol": "BTCUSDT"},
        )

    def test_hash_target_nonpatch_resume_paper_empty(self) -> None:
        """resume_paper{engine:live}：去 engine 後 hash 對象 = {}（Rust canonical = "{}"）。"""
        self.assertEqual(lpt.hash_target_for("resume_paper", {"engine": "live"}), {})

    def test_call_params_with_token_nonpatch_matches_rust_bind(self) -> None:
        """命門（非 patch interop）：call_params_with_token 對 resume_paper /
        set_dynamic_risk_enabled 鑄的 token，用 Rust build_bind_bytes 同規則重建後 HMAC
        必相符 → 證 Rust check_live_authz 會 ACCEPT（與 Rust nonpatch_happy_path 對偶）。"""
        secret = "s3cr3t"
        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": secret}):
            for method, params in [
                ("resume_paper", {"engine": "live"}),
                ("set_dynamic_risk_enabled", {"engine": "live", "enabled": True}),
                ("reset_drawdown_baseline", {"engine": "live"}),
            ]:
                out = lpt.call_params_with_token(method, dict(params))
                self.assertIn("live_authz_token", out)
                self.assertEqual(out["engine"], "live")  # 原 params 欄保留
                # 重建 Rust bind-string：hash(hash_target) ∥ "live" ∥ method ∥ ts ∥ nonce
                target = lpt.hash_target_for(method, params)
                h = lpt.canonical_patch_hash(target)
                bind = b"\x1f".join([
                    h.encode("ascii"), b"live", method.encode(),
                    str(out["live_authz_ts"]).encode(), out["live_authz_nonce"].encode(),
                ])
                expect = hmac.new(secret.encode(), bind, hashlib.sha256).hexdigest()
                self.assertEqual(out["live_authz_token"], expect, f"{method} bind mismatch")


class TestOos4DefensiveInputHygiene(unittest.TestCase):
    """OOS-4：call_params_with_token / _attach_live_token_if_live 的純防禦輸入衛生。

    不改授權分工、不改行為（現有合法 caller happy-path 不變）；只驗輸入形狀：
    method ∈ LIVE_WRITE_METHODS、engine ∈ {live,demo,paper}、params 為 dict；違反 raise。
    """

    def _resolve_rust_live_authz(self):
        """定位 rust/openclaw_engine/src/ipc_server/live_authz.rs（禁硬編碼機器路徑）。
        repo root = srv = parents[5]（tests→control_api_v1→bybit_connector→
        exchange_connectors→program_code→srv），退化向上找含該檔的祖先。"""
        from pathlib import Path  # noqa: PLC0415

        rel = Path("rust") / "openclaw_engine" / "src" / "ipc_server" / "live_authz.rs"
        primary = Path(__file__).resolve().parents[5] / rel
        if primary.exists():
            return primary
        for anc in Path(__file__).resolve().parents:
            cand = anc / rel
            if cand.exists():
                return cand
        return None

    def test_python_whitelist_matches_rust_live_authz(self) -> None:
        """硬要求：Python LIVE_WRITE_METHODS 逐字等於 Rust live_authz.rs 白名單。
        兩邊分歧 = 治理債（某 method 一側可鑄、另一側判非 live-write）。"""
        import re  # noqa: PLC0415

        rust_path = self._resolve_rust_live_authz()
        if rust_path is None:
            self.skipTest("rust/openclaw_engine live_authz.rs 不可達（odd cwd / 目錄重排）")
        text = rust_path.read_text(encoding="utf-8")
        m = re.search(r"LIVE_WRITE_METHODS[^=]*=\s*&\[(.*?)\];", text, re.DOTALL)
        self.assertIsNotNone(m, "無法定位 Rust LIVE_WRITE_METHODS 陣列")
        rust_methods = set(re.findall(r'"([a-z_]+)"', m.group(1)))
        self.assertEqual(
            set(lpt.LIVE_WRITE_METHODS),
            rust_methods,
            "Python LIVE_WRITE_METHODS 與 Rust live_authz.rs 分歧——兩檔須同步",
        )

    def test_non_whitelisted_method_raises(self) -> None:
        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "s"}):
            with self.assertRaises(ValueError):
                lpt.call_params_with_token("not_a_live_write_method", {"engine": "live"})

    def test_illegal_engine_raises(self) -> None:
        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "s"}):
            with self.assertRaises(ValueError):
                lpt.call_params_with_token("resume_paper", {"engine": "mainnet"})

    def test_params_not_dict_raises(self) -> None:
        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "s"}):
            with self.assertRaises(ValueError):
                lpt.call_params_with_token("resume_paper", ["engine", "live"])  # type: ignore[arg-type]

    def test_happy_path_still_mints(self) -> None:
        """現有合法 live method + engine=="live" + dict → 仍正常鑄 token（行為不變）。"""
        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "s"}):
            out = lpt.call_params_with_token("reset_drawdown_baseline", {"engine": "live"})
        self.assertIn("live_authz_token", out)
        self.assertEqual(out["engine"], "live")

    def test_attach_helper_rejects_non_whitelisted_live_method(self) -> None:
        """_attach_live_token_if_live 命名入口：engine=="live" 但 method 非白名單 → raise。"""
        from app.risk_view_client import _attach_live_token_if_live  # noqa: PLC0415

        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "s"}):
            with self.assertRaises(ValueError):
                _attach_live_token_if_live("bogus_method", {"engine": "live"})

    def test_attach_helper_passthrough_non_live_unchanged(self) -> None:
        """demo/paper/缺 engine/非 dict → 原樣回傳（pass-through 不變，不 raise）。"""
        from app.risk_view_client import _attach_live_token_if_live  # noqa: PLC0415

        self.assertEqual(_attach_live_token_if_live("resume_paper", {"engine": "demo"}), {"engine": "demo"})
        self.assertIsNone(_attach_live_token_if_live("resume_paper", None))
        self.assertEqual(_attach_live_token_if_live("resume_paper", {}), {})


# ── Route-level tests ─────────────────────────────────────────────────────────


@dataclass
class _FakeActor:
    actor_id: str = "risk-operator"
    roles: set[str] | None = None
    scopes: set[str] | None = None

    def __post_init__(self) -> None:
        if self.roles is None:
            self.roles = {"operator", "viewer"}
        if self.scopes is None:
            self.scopes = {"risk:write"}


def _make_app(actor: _FakeActor) -> FastAPI:
    import importlib
    from app import risk_routes as _rr
    importlib.reload(_rr)
    app = FastAPI()
    app.include_router(_rr.risk_router)
    from app import main_legacy as base
    app.dependency_overrides[base.current_actor] = lambda: actor
    return app


def _fake_ipc(call_mock: AsyncMock) -> AsyncMock:
    client = MagicMock()
    client.call = call_mock
    return AsyncMock(return_value=client)


class TestAgentAdjustLiveForbidden(unittest.TestCase):
    """T1（operator 必測）：agent-adjust engine=live → 403，0 mutation。"""

    def test_agent_adjust_live_returns_403(self) -> None:
        app = _make_app(_FakeActor())
        client = TestClient(app)
        rvc = MagicMock()
        rvc.agent_adjust = AsyncMock(return_value={})
        rvc.refresh_config = AsyncMock(return_value={})
        rvc.get_agent_params = MagicMock(return_value={})
        # audit row 寫入 fail-soft（Mac 無 PG）；patch 掉避免噪音，並斷言被呼叫
        with patch("app.risk_routes._get_risk_view_client", new=AsyncMock(return_value=rvc)), patch(
            "app.risk_routes._write_config_reject_audit"
        ) as audit:
            resp = client.post(
                "/api/v1/paper/risk/agent-adjust",
                json={"engine": "live", "position_size_multiplier": 0.5},
            )
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertEqual(resp.json()["detail"]["error"], "agent_source_live_write_forbidden")
        # 0 mutation：agent_adjust IPC 永不被呼叫
        rvc.agent_adjust.assert_not_called()
        # 審計 row 落（source=agent）
        audit.assert_called_once()
        _a, kw = audit.call_args
        self.assertEqual(kw["source"], "agent")
        self.assertEqual(kw["engine"], "live")
        self.assertEqual(kw["reason"], "agent_source_live_write_forbidden")

    def test_agent_adjust_demo_unaffected(self) -> None:
        """T11：agent-adjust engine=demo（及 default paper）維持既有行為，0 token。"""
        app = _make_app(_FakeActor())
        client = TestClient(app)
        rvc = MagicMock()
        rvc.agent_adjust = AsyncMock(return_value={"ok": True})
        rvc.get_agent_params = MagicMock(return_value={"size_multiplier": 0.5})
        rvc.config_version = 5
        with patch("app.risk_routes._get_risk_view_client", new=AsyncMock(return_value=rvc)):
            resp = client.post(
                "/api/v1/paper/risk/agent-adjust",
                json={"engine": "demo", "position_size_multiplier": 0.5},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        rvc.agent_adjust.assert_called_once()
        # engine 不得進 updates（路由欄非 RiskConfig 欄位）
        sent = rvc.agent_adjust.call_args[0][0]
        self.assertNotIn("engine", sent)


class TestConfigGlobalEngineGate(unittest.TestCase):
    """T9 + T11：POST /config/global engine 路由 + 5-gate。"""

    def test_global_live_without_gates_409(self) -> None:
        app = _make_app(_FakeActor())
        client = TestClient(app)
        with patch(
            "app.live_preflight.all_five_live_gates_ok",
            return_value=(False, ["global_mode_not_live_reserved"]),
        ):
            resp = client.post(
                "/api/v1/paper/risk/config/global",
                json={"engine": "live", "max_leverage": 3.0},
            )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["detail"]["error"], "live_gate_failed")

    def test_global_live_with_gates_mints_token(self) -> None:
        app = _make_app(_FakeActor())
        client = TestClient(app)
        call_mock = AsyncMock(return_value={"ok": True, "version": 11, "source": "operator"})
        with patch.dict(os.environ, {"OPENCLAW_LIVE_PATCH_SECRET": "s"}), patch(
            "app.live_preflight.all_five_live_gates_ok", return_value=(True, [])
        ), patch("app.risk_routes._get_direct_ipc", new=_fake_ipc(call_mock)):
            resp = client.post(
                "/api/v1/paper/risk/config/global",
                json={"engine": "live", "max_leverage": 3.0},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        call_mock.assert_called_once()
        params = call_mock.call_args.kwargs["params"]
        self.assertEqual(params["engine"], "live")
        self.assertIn("live_authz_token", params)
        # canonical hash 對的是「實際送的 patch 物件」
        self.assertEqual(
            params["live_authz_token"],
            self._recompute(params, "s", "patch_risk_config"),
        )

    @staticmethod
    def _recompute(params: dict, secret: str, method: str) -> str:
        h = lpt.canonical_patch_hash(params["patch"])
        bind = b"\x1f".join([
            h.encode("ascii"), b"live", method.encode(),
            str(params["live_authz_ts"]).encode(), params["live_authz_nonce"].encode(),
        ])
        return hmac.new(secret.encode(), bind, hashlib.sha256).hexdigest()

    def test_global_demo_unaffected_no_token(self) -> None:
        """T11：engine=demo 走既有 client.update_global_config（不傳 engine、0 token）。"""
        app = _make_app(_FakeActor())
        client = TestClient(app)
        rvc = MagicMock()
        rvc.update_global_config = AsyncMock(return_value={"ok": True})
        rvc.config = {}
        rvc.config_version = 3
        gate = MagicMock(return_value=(False, ["should_not_consult"]))
        with patch("app.risk_routes._get_risk_view_client", new=AsyncMock(return_value=rvc)), patch(
            "app.live_preflight.all_five_live_gates_ok", gate
        ):
            resp = client.post(
                "/api/v1/paper/risk/config/global",
                json={"engine": "demo", "max_leverage": 3.0},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        gate.assert_not_called()  # demo no-op
        rvc.update_global_config.assert_called_once()
        sent = rvc.update_global_config.call_args[0][0]
        self.assertNotIn("engine", sent)

    def test_global_default_paper_unaffected(self) -> None:
        """T11：不傳 engine（default paper）→ 既有行為。"""
        app = _make_app(_FakeActor())
        client = TestClient(app)
        rvc = MagicMock()
        rvc.update_global_config = AsyncMock(return_value={"ok": True})
        rvc.config = {}
        rvc.config_version = 1
        with patch("app.risk_routes._get_risk_view_client", new=AsyncMock(return_value=rvc)):
            resp = client.post(
                "/api/v1/paper/risk/config/global",
                json={"max_leverage": 3.0},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        rvc.update_global_config.assert_called_once()


class TestPaperControlRoutesExplicitEngine(unittest.TestCase):
    """U-P0-3 fix：/reset-cooldown + /unhalt-session 顯式傳 engine="paper"，
    在 live-running 引擎上不解析為 live（不需 token），保留 operator paper-control 流程。"""

    def test_reset_cooldown_passes_engine_paper(self) -> None:
        app = _make_app(_FakeActor())
        client = TestClient(app)
        rvc = MagicMock()
        rvc.clear_consecutive_losses = AsyncMock(return_value={"result": "cleared"})
        rvc.get_status = MagicMock(return_value={"governor_tier": "Normal"})
        with patch("app.risk_routes._get_risk_view_client", new=AsyncMock(return_value=rvc)):
            resp = client.post("/api/v1/paper/risk/reset-cooldown")
        self.assertEqual(resp.status_code, 200, resp.text)
        rvc.clear_consecutive_losses.assert_called_once_with(engine="paper")

    def test_unhalt_session_passes_engine_paper(self) -> None:
        app = _make_app(_FakeActor())
        client = TestClient(app)
        rvc = MagicMock()
        rvc.unhalt_session = AsyncMock(return_value={"message": "resumed"})
        with patch("app.risk_routes._get_risk_view_client", new=AsyncMock(return_value=rvc)):
            resp = client.post("/api/v1/paper/risk/unhalt-session")
        self.assertEqual(resp.status_code, 200, resp.text)
        rvc.unhalt_session.assert_called_once_with(engine="paper")


class TestEngineValidator(unittest.TestCase):
    """engine 欄 validator 限 {paper,demo,live}。"""

    def test_invalid_engine_422(self) -> None:
        app = _make_app(_FakeActor())
        client = TestClient(app)
        resp = client.post(
            "/api/v1/paper/risk/config/global",
            json={"engine": "live_demo", "max_leverage": 3.0},
        )
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
