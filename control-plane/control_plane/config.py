from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str:
    v = os.getenv(name)
    if v is None:
        if default is None:
            raise RuntimeError(f"Missing required env var {name}")
        return default
    return v


@dataclass(frozen=True)
class Settings:
    mqtt_host: str
    mqtt_port: int
    edge_node_ids: list[str]
    log_level: str

    # TD3 / training hyperparameters
    gamma: float
    tau: float
    policy_noise_std: float
    noise_clip: float
    policy_delay: int
    replay_size: int
    batch_size: int
    actor_lr: float
    critic_lr: float
    quantize_every_critic_updates: int


def load_settings() -> Settings:
    edge_node_ids = [s.strip() for s in _env("EDGE_NODE_IDS", "zone-a,zone-b").split(",") if s.strip()]
    return Settings(
        mqtt_host=_env("MQTT_HOST", "localhost"),
        mqtt_port=int(_env("MQTT_PORT", "1883")),
        edge_node_ids=edge_node_ids,
        log_level=_env("LOG_LEVEL", "INFO"),

        gamma=float(_env("GAMMA", "0.99")),
        tau=float(_env("TAU", "0.005")),
        policy_noise_std=float(_env("POLICY_NOISE_STD", "0.2")),
        noise_clip=float(_env("NOISE_CLIP", "0.5")),
        policy_delay=int(_env("POLICY_DELAY", "2")),
        replay_size=int(_env("REPLAY_SIZE", "10000")),
        batch_size=int(_env("BATCH_SIZE", "64")),
        actor_lr=float(_env("ACTOR_LR", "0.0003")),
        critic_lr=float(_env("CRITIC_LR", "0.0003")),
        quantize_every_critic_updates=int(_env("QUANTIZE_EVERY", "200")),
    )
