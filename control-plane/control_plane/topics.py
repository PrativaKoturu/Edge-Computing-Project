from __future__ import annotations


def telemetry_topic(node_id: str) -> str:
    return f"edge/{node_id}/telemetry"


def request_topic(node_id: str) -> str:
    return f"edge/{node_id}/request"


def policy_topic(node_id: str) -> str:
    return f"edge/{node_id}/policy"


CONTROL_BROADCAST = "control/broadcast"
