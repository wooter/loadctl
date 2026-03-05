"""Configuration loading from YAML."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Config:
    mqtt_broker: str
    mqtt_port: int
    mqtt_username: str | None
    mqtt_password: str | None
    max_amps_per_phase: int
    margin_amps: int
    power_topics: dict[str, str]
    homebridge_url: str
    homebridge_username: str
    homebridge_password: str
    loads: dict[str, dict]
    schedule: dict[str, dict]
    log_level: str


def load_config(path: str) -> Config:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(p) as f:
        raw = yaml.safe_load(f)
    mqtt = raw.get("mqtt", {})
    grid = raw.get("grid", {})
    power = raw.get("power_source", {})
    hb = raw.get("homebridge", {})
    logging_cfg = raw.get("logging", {})
    return Config(
        mqtt_broker=mqtt.get("broker", "localhost"),
        mqtt_port=mqtt.get("port", 1883),
        mqtt_username=mqtt.get("username"),
        mqtt_password=mqtt.get("password"),
        max_amps_per_phase=grid.get("max_amps_per_phase", 20),
        margin_amps=grid.get("margin_amps", 3),
        power_topics=power.get("topics", {}),
        homebridge_url=hb.get("url", "http://localhost:8581"),
        homebridge_username=hb.get("username", "admin"),
        homebridge_password=hb.get("password", "admin"),
        loads=raw.get("loads", {}),
        schedule=raw.get("schedule", {}),
        log_level=logging_cfg.get("level", "info"),
    )
