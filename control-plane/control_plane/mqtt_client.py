from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

import paho.mqtt.client as mqtt
import socket


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int
    client_id: str


class MqttBus:
    def __init__(self, cfg: MqttConfig, logger: logging.Logger):
        self._cfg = cfg
        self._log = logger
        self._client = mqtt.Client(client_id=cfg.client_id, clean_session=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._handlers: dict[str, Callable[[str, str], None]] = {}
        self._connected = False
        # Reduce reconnect thrash when using public brokers.
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

    def connect(self) -> None:
        """
        Connect with retries.

        Public brokers can be flaky (network drops, transient DNS failures). We keep
        retrying instead of crashing the container so traffic + trainer can recover.
        """
        if not self._client.is_connected():
            self._client.loop_start()

        backoff_s = 1.0
        while True:
            try:
                # Force a DNS lookup here so we can log resolution failures clearly.
                # (Paho will also resolve internally, but its exception can be opaque.)
                socket.getaddrinfo(self._cfg.host, self._cfg.port, 0, socket.SOCK_STREAM)

                self._log.info(
                    "Connecting to MQTT %s:%s as %s", self._cfg.host, self._cfg.port, self._cfg.client_id
                )
                self._client.connect(self._cfg.host, self._cfg.port, keepalive=30)

                deadline = time.time() + 10
                while not self._connected and time.time() < deadline:
                    time.sleep(0.05)
                if not self._connected:
                    raise RuntimeError("MQTT connect timeout")

                return
            except Exception as e:
                self._connected = False
                self._log.warning("MQTT connect failed (%s). Retrying in %.1fs...", e, backoff_s)
                time.sleep(backoff_s)
                backoff_s = min(30.0, backoff_s * 1.6)

    def close(self) -> None:
        try:
            self._client.loop_stop()
        finally:
            self._client.disconnect()

    def subscribe(self, topic: str, handler: Callable[[str, str], None], qos: int = 0) -> None:
        self._handlers[topic] = handler
        self._client.subscribe(topic, qos=qos)
        self._log.info("Subscribed %s", topic)

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> None:
        if not self._connected:
            # Best-effort reconnect so callers don't have to handle it.
            self.connect()
        self._client.publish(topic, payload=payload, qos=qos, retain=retain)

    # Callbacks
    def _on_connect(self, client: mqtt.Client, userdata: Optional[object], flags: dict, rc: int) -> None:
        self._connected = (rc == 0)
        self._log.info("MQTT connected rc=%s", rc)
        if not self._connected:
            self._log.warning("MQTT connect returned non-zero rc=%s", rc)

    def _on_disconnect(self, client: mqtt.Client, userdata: Optional[object], rc: int) -> None:
        self._connected = False
        self._log.warning("MQTT disconnected rc=%s", rc)

    def _on_message(self, client: mqtt.Client, userdata: Optional[object], msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")
        handler = self._handlers.get(topic)
        if handler is None:
            return
        try:
            handler(topic, payload)
        except Exception:
            self._log.exception("Handler failed for topic=%s", topic)
