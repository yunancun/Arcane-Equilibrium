"""Alpha discovery throughput helpers.

MODULE_NOTE:
  模塊用途：把 AEG 候選接入、SignalSpec、execution realism、多臂 discovery、
    edge snapshot adapter、FlashDip counterfactual ladder 收斂到同一個
    artifact-only research Module。
  依賴：標準庫 + 既有 AEG research builders / ml_training SignalSpec validator。
  硬邊界：不讀 DB、不連 Bybit、不寫 runtime/trading/auth/risk state。
"""

from __future__ import annotations

RUNNER_VERSION = "alpha_discovery_throughput_v0.1"
PACKET_SCHEMA_VERSION = "alpha_candidate_packet_v1"
DISCOVERY_LOOP_SCHEMA_VERSION = "alpha_discovery_loop_v1"
EDGE_SNAPSHOT_ADAPTER_SCHEMA_VERSION = "aeg_edge_snapshot_adapter_v1"

COUNTERFACTUAL_EVIDENCE_TIER = "counterfactual_replay"
COUNTERFACTUAL_PROMOTION_BLOCKER = "counterfactual_only_not_promotion_evidence"

__all__ = [
    "COUNTERFACTUAL_EVIDENCE_TIER",
    "COUNTERFACTUAL_PROMOTION_BLOCKER",
    "DISCOVERY_LOOP_SCHEMA_VERSION",
    "EDGE_SNAPSHOT_ADAPTER_SCHEMA_VERSION",
    "PACKET_SCHEMA_VERSION",
    "RUNNER_VERSION",
]
