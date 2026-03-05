"""MQTT client for power data and load control."""
from __future__ import annotations

import json
import logging

import paho.mqtt.client as mqtt

from loadctl.config import Config

logger = logging.getLogger(__name__)
TOPIC_PREFIX = "loadctl"


class LoadMQTT:
    def __init__(self, config: Config):
        self.config = config
        self.power_data: dict[str, float] = {}
        self._topic_to_key: dict[str, str] = {}
        self._client: mqtt.Client | None = None
        for key, topic in config.power_topics.items():
            self._topic_to_key[topic] = key

    def get_subscribe_topics(self) -> list[str]:
        return list(self._topic_to_key.keys())

    def on_message(self, topic: str, payload: bytes) -> None:
        key = self._topic_to_key.get(topic)
        if key is None:
            return
        try:
            self.power_data[key] = float(payload.decode("utf-8").strip())
        except (ValueError, UnicodeDecodeError):
            logger.warning("Invalid payload on %s: %s", topic, payload)

    def connect(self) -> None:
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="loadctl")
        if self.config.mqtt_username:
            self._client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(self.config.mqtt_broker, self.config.mqtt_port)
        self._client.loop_start()
        logger.info("MQTT connecting to %s:%d", self.config.mqtt_broker, self.config.mqtt_port)

    def disconnect(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        if self._client:
            self._client.publish(topic, payload, retain=retain)

    def publish_status(self, data: dict) -> None:
        if self._client:
            self._client.publish(f"{TOPIC_PREFIX}/status", json.dumps(data), retain=True)

    def publish_load_state(self, load_name: str, state: dict) -> None:
        if self._client:
            self._client.publish(f"{TOPIC_PREFIX}/{load_name}/state", json.dumps(state), retain=True)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        logger.info("MQTT connected (rc=%s)", rc)
        for topic in self.get_subscribe_topics():
            client.subscribe(topic)

    def _on_message(self, client, userdata, message):
        self.on_message(message.topic, message.payload)
