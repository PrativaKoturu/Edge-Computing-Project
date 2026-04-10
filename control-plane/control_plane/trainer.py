from __future__ import annotations

import logging
import os
import time

import json
import torch
import torch.nn.functional as F

from .config import load_settings
from .messages import EdgeTelemetry, PolicyUpdate
from .mqtt_client import MqttBus, MqttConfig
from .replay_buffer import GlobalReplayBuffer, Transition
from .topics import policy_topic, telemetry_topic
from .models import Td3Agent
from .state_tracker import PerNodeStateTracker
from .profiler import BenchmarkCollector, get_device_info


def _now_ms() -> int:
    return int(time.time() * 1000)


def _setup_logger(level: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("trainer")


def _reward(t: EdgeTelemetry, cache_pressure: float) -> float:
    cache_hit = 1.0 if t.cache_hit else 0.0
    cache_miss = 1.0 if not t.cache_hit else 0.0
    anomaly_flag = 1.0 if t.anomaly else 0.0
    return (
        +1.0 * cache_hit
        - 1.0 * cache_miss
        - 0.001 * float(t.latency_ms)
        + 0.5 * anomaly_flag * cache_hit
        - 0.3 * float(cache_pressure)
    )


@torch.no_grad()
def _quantize_policy_weights(actor: torch.nn.Module) -> tuple[list[float], list[int]]:
    """
    Quantization spec (exact):
      1. Take first linear layer weights W: shape [19, 8]
      2. SVD -> U, S, Vt
      3. compressed = (S[:8] * Vt[:8]).mean(dim=1)  # shape [8]
      4. quantized = (compressed / maxabs * 127).int().clamp(-128, 127)
    """
    if not hasattr(actor, "input_proj"):
        raise RuntimeError("Actor missing input_proj; cannot quantize by spec")
    W = actor.input_proj.weight.detach().cpu()  # (19, 8)
    if tuple(W.shape) != (19, 8):
        raise RuntimeError(f"Expected actor first layer weight shape (19,8), got {tuple(W.shape)}")
    U, S, Vh = torch.linalg.svd(W, full_matrices=False)  # Vh: (8,8)
    compressed = (S[:8].unsqueeze(1) * Vh[:8]).mean(dim=1)  # (8,)
    maxabs = float(compressed.abs().max().item())
    if maxabs == 0.0:
        q = torch.zeros_like(compressed, dtype=torch.int32)
    else:
        q = (compressed / maxabs * 127.0).round().to(torch.int32).clamp(-128, 127)
    return compressed.to(torch.float32).tolist(), [int(x) for x in q.tolist()]


def main() -> None:
    settings = load_settings()
    log = _setup_logger(settings.log_level)

    # Device selection: use GPU if available, else CPU
    if torch.cuda.is_available():
        device = torch.device("cuda:0")
        log.info("Using GPU: %s", torch.cuda.get_device_name(0))
    else:
        device = torch.device("cpu")
        log.info("Using CPU (GPU not available)")

    # Log device info
    device_info = get_device_info()
    log.info("Device info: %s", device_info)

    agent = Td3Agent().to(device)
    actor_opt = torch.optim.Adam(agent.actor.parameters(), lr=settings.actor_lr)
    critic_opt = torch.optim.Adam(agent.critic.parameters(), lr=settings.critic_lr)

    rb = GlobalReplayBuffer(capacity=settings.replay_size)
    tracker = PerNodeStateTracker()
    bench = BenchmarkCollector()
    bench.system_profiler.start()

    critic_updates = 0
    policy_publishes = 0
    critic_losses: list[float] = []
    actor_losses: list[float] = []

    bus = MqttBus(
        MqttConfig(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            client_id=f"trainer-{os.getpid()}",
        ),
        logger=log,
    )

    def on_telemetry(topic: str, payload: str) -> None:
        nonlocal critic_updates, policy_publishes
        t = EdgeTelemetry.from_json(payload)

        # Record metrics for this zone
        bench.record_zone_telemetry(
            node_id=t.node_id,
            cache_hit=t.cache_hit,
            latency_ms=t.latency_ms,
            evicted=t.evicted,
            anomaly=t.anomaly,
        )

        # State before update (uses previous rolling windows + time since last request)
        s = tracker.build_state(
            node_id=t.node_id,
            telemetry_msg=t,
            payload_kb=t.payload_kb,
            anomaly_flag=1.0 if t.anomaly else 0.0,
            stream_id=t.stream_id,
        )

        # Cache pressure BEFORE update is based on current rolling evictions window.
        # The tracker encodes it as state[7].
        cache_pressure = float(s[7])

        r = _reward(t, cache_pressure=cache_pressure)

        # Update rolling trackers after observing the outcome
        tracker.update(t.node_id, t)

        # Next state after update (time_since_last_request becomes ~0)
        sp = tracker.build_state(
            node_id=t.node_id,
            telemetry_msg=t,
            payload_kb=t.payload_kb,
            anomaly_flag=1.0 if t.anomaly else 0.0,
            stream_id=t.stream_id,
        )

        a = float(1.0 if t.cache_decision else 0.0)
        rb.push(Transition(node_id=t.node_id, s=s, a=a, r=r, sp=sp, done=False))

        if len(rb) % 100 == 0:
            log.info(
                "Replay size=%d latest node=%s hit=%s lat=%dms score=%d",
                len(rb),
                t.node_id,
                t.cache_hit,
                t.latency_ms,
                t.score_int32,
            )

    bus.connect()
    for nid in settings.edge_node_ids:
        bus.subscribe(telemetry_topic(nid), on_telemetry, qos=0)

    log.info("Trainer loop started. Nodes=%s", ",".join(settings.edge_node_ids))

    try:
        step = 0
        while True:
            time.sleep(0.05)
            step += 1

            if len(rb) < settings.batch_size:
                continue

            batch = rb.sample(settings.batch_size)
            s = torch.tensor([t.s for t in batch], dtype=torch.float32, device=device)
            a = torch.tensor([[t.a] for t in batch], dtype=torch.float32, device=device)
            r = torch.tensor([[t.r] for t in batch], dtype=torch.float32, device=device)
            sp = torch.tensor([t.sp for t in batch], dtype=torch.float32, device=device)
            done = torch.tensor([[1.0 if t.done else 0.0] for t in batch], dtype=torch.float32, device=device)

            t0 = time.time()
            with torch.no_grad():
                noise = torch.randn((settings.batch_size, 1), device=device) * settings.policy_noise_std
                noise = noise.clamp(-settings.noise_clip, settings.noise_clip)
                ap = (agent.actor_target(sp) + noise).clamp(0.0, 1.0)
                q1_t, q2_t = agent.critic_target(sp, ap)
                q_t = torch.min(q1_t, q2_t)
                target = r + settings.gamma * q_t * (1.0 - done)
            bench.record_timing("inference", (time.time() - t0) * 1000)

            t0 = time.time()
            q1, q2 = agent.critic(s, a)
            critic_loss = F.mse_loss(q1, target) + F.mse_loss(q2, target)
            critic_opt.zero_grad()
            critic_loss.backward()
            critic_opt.step()
            bench.record_timing("critic_update", (time.time() - t0) * 1000)

            critic_updates += 1
            critic_losses.append(float(critic_loss.detach().cpu().item()))
            if len(critic_losses) > 10:
                critic_losses.pop(0)

            if critic_updates % settings.policy_delay == 0:
                t0 = time.time()
                actor_a = agent.actor(s)
                q1_pi, _ = agent.critic(s, actor_a)
                actor_loss = -q1_pi.mean()
                actor_opt.zero_grad()
                actor_loss.backward()
                actor_opt.step()
                bench.record_timing("actor_update", (time.time() - t0) * 1000)

                actor_losses.append(float(actor_loss.detach().cpu().item()))
                if len(actor_losses) > 10:
                    actor_losses.pop(0)

                agent.reset_targets(hard=False, tau=settings.tau)

            if critic_updates % 50 == 0:
                log.info(
                    "updates=%d replay=%d critic_loss(avg10)=%.4f actor_loss(avg10)=%.4f publishes=%d",
                    critic_updates,
                    len(rb),
                    sum(critic_losses) / max(1, len(critic_losses)),
                    sum(actor_losses) / max(1, len(actor_losses)),
                    policy_publishes,
                )
                # Publish stats for the dashboard (best-effort, no retention).
                bus.publish(
                    "trainer/stats",
                    json.dumps(
                        {
                            "replay_size": len(rb),
                            "critic_updates": critic_updates,
                            "critic_loss_avg10": sum(critic_losses) / max(1, len(critic_losses)),
                            "actor_loss_avg10": sum(actor_losses) / max(1, len(actor_losses)),
                            "policy_publishes": policy_publishes,
                        },
                        separators=(",", ":"),
                    ),
                )

            if critic_updates % settings.quantize_every_critic_updates == 0:
                float_w, int8_w = _quantize_policy_weights(agent.actor)
                for nid in settings.edge_node_ids:
                    bus.publish(
                        policy_topic(nid),
                        PolicyUpdate(node_id=nid, ts_ms=_now_ms(), float_weights=float_w, int8_weights=int8_w).to_json(),
                        qos=0,
                    )
                policy_publishes += 1

    except KeyboardInterrupt:
        log.info("Training interrupted.")
    finally:
        bench.system_profiler.stop()
        report = bench.report()
        log.info("Final benchmark report: %s", json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
