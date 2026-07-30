"""Mutation proof for the recovery readback Adapter's fixed socket provenance."""

from __future__ import annotations

from pathlib import Path

import pytest

from test_agent_governance_s2_host_kernel import HELPERS, _raw_command_findings


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    (
        (
            "socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)",
            "socket.socket(socket.AF_INET, socket.SOCK_STREAM)",
            "AF_UNIX",
        ),
        (
            "client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)",
            "socket = object()\n    "
            "client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)",
            "socket module reassignment",
        ),
        (
            "client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)",
            "socket.socket.connect = object()\n    "
            "client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)",
            "socket module reassignment",
        ),
        (
            "client.connect(FIXED_ATTESTOR_SOCKET_PATH)",
            "client.connect(('203.0.113.1', 443))",
            "fixed attestor endpoint",
        ),
        (
            "client.connect(FIXED_ATTESTOR_SOCKET_PATH)",
            "FIXED_ATTESTOR_SOCKET_PATH = '/tmp/foreign.sock'\n        "
            "client.connect(FIXED_ATTESTOR_SOCKET_PATH)",
            "endpoint reassignment",
        ),
        (
            "client.connect(FIXED_ATTESTOR_SOCKET_PATH)",
            "peer = client\n        peer.connect(FIXED_ATTESTOR_SOCKET_PATH)",
            "socket client alias",
        ),
    ),
)
def test_recovery_readback_socket_provenance_mutations_are_caught(
    tmp_path: Path,
    old: str,
    new: str,
    expected: str,
) -> None:
    original = HELPERS / "agent_governance_s2_5_recovery_readback.py"
    source = original.read_text(encoding="utf-8")
    assert old in source
    mutated = tmp_path / original.name
    mutated.write_text(source.replace(old, new, 1), encoding="utf-8")

    assert any(
        expected in finding for finding in _raw_command_findings(mutated)
    )
