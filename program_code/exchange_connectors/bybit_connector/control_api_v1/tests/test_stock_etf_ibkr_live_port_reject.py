"""IBKR live-port fail-closed 契約測試（純 dataclass 驗證，無網路）。

對應 remediation Item 13：Python 邊界 `IbkrReadOnlyEndpointConfig.validate_source_boundary`
先前放行 `(4001, 4002)` 兩個 port，但 4001 是 Rust `ibkr_phase2_gate.rs` 的
`IBKR_LIVE_GATEWAY_PORT`（硬拒）。收緊後只接受 4002（reserved paper TWS），使 Python
邊界與 Rust hard-deny 對齊。本測試證明：
  - 4001（live gateway）被拒，回傳 `port_not_reserved_paper_tws`；
  - 4002（reserved paper TWS）被接受，port 維度零 blocker；
  - 既有 live port 7496 仍被拒（不回歸）。

This is a pure dataclass boundary test: no socket, no secret, no IBKR SDK, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path


# parents[5] = srv root（與同目錄其他 stock_etf ibkr 測試一致的絕對 import 錨點）
SRV_ROOT = Path(__file__).resolve().parents[5]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from program_code.broker_connectors.ibkr_connector import (  # noqa: E402
    IbkrReadOnlyEndpointConfig,
)


# 唯一被關注的 port blocker 標籤（與 models.py 內字面量對齊）。
PORT_BLOCKER = "port_not_reserved_paper_tws"


def test_live_gateway_port_4001_is_rejected() -> None:
    """4001（Rust IBKR_LIVE_GATEWAY_PORT）必須被 Python 邊界拒絕。"""
    # 只覆寫 port，其餘欄位維持安全預設，隔離出 port 維度的單一效果。
    blockers = IbkrReadOnlyEndpointConfig(port=4001).validate_source_boundary()

    assert PORT_BLOCKER in blockers
    # 安全預設下，4001 唯一觸發的 blocker 就是 port——沒有連帶噪音。
    assert blockers == (PORT_BLOCKER,)


def test_reserved_paper_tws_port_4002_is_accepted() -> None:
    """4002（reserved paper TWS）在安全預設下必須完全通過（零 blocker）。"""
    # 4002 是 dataclass 的預設 port；顯式帶入以表意，行為應等同預設建構。
    blockers = IbkrReadOnlyEndpointConfig(port=4002).validate_source_boundary()

    assert PORT_BLOCKER not in blockers
    # 預設安全描述子在 port=4002 下不應產生任何 boundary blocker。
    assert blockers == ()
    # 預設建構（未指定 port）與顯式 4002 行為一致，證明 4002 是被接受的正常值。
    assert IbkrReadOnlyEndpointConfig().port == 4002
    assert IbkrReadOnlyEndpointConfig().validate_source_boundary() == ()


def test_legacy_live_tws_port_7496_still_rejected() -> None:
    """回歸護欄：既有 live TWS port 7496 收緊後仍必須被拒。"""
    blockers = IbkrReadOnlyEndpointConfig(port=7496).validate_source_boundary()

    assert PORT_BLOCKER in blockers


def test_only_4002_passes_across_candidate_ports() -> None:
    """跨候選 port 表格斷言：唯有 4002 在 port 維度通過，其餘（含 4001）皆拒。

    這條表格式檢查能 falsify pre-fix 舊邏輯 `port not in (4001, 4002)`——
    舊碼下 4001 不會出現在 rejected 集合，本測試即會失敗。
    """
    # port -> 是否應被接受（port 維度無 blocker）
    expected_accept = {
        4001: False,  # live gateway，硬拒
        4002: True,   # reserved paper TWS，唯一接受值
        7496: False,  # legacy live TWS
        7497: False,  # legacy paper TWS（非本邊界的 reserved 值，仍拒）
        0: False,
        -1: False,
    }

    for port, should_accept in expected_accept.items():
        blockers = IbkrReadOnlyEndpointConfig(port=port).validate_source_boundary()
        port_accepted = PORT_BLOCKER not in blockers
        assert port_accepted is should_accept, (
            f"port={port} expected accept={should_accept}, got blockers={blockers}"
        )
