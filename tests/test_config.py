from __future__ import annotations

import os
import tempfile

import pytest

from loadctl.config import load_config

MINIMAL_CONFIG = """
mqtt:
  broker: localhost
  port: 1883
grid:
  max_amps_per_phase: 20
  margin_amps: 3
power_source:
  topics:
    power_phase1: "RPICT4V3/RP1"
    power_phase2: "RPICT4V3/RP2"
    power_phase3: "RPICT4V3/RP3"
    voltage_phase1: "RPICT4V3/Vrms1"
    voltage_phase2: "RPICT4V3/Vrms2"
    voltage_phase3: "RPICT4V3/Vrms3"
homebridge:
  url: http://localhost:8581
  username: admin
  password: admin
loads:
  twc:
    type: chargectl
    phases: [1, 2, 3]
    mqtt_topic: "chargectl/control/max_amps"
    min_amps: 6
    max_amps: 17
    estimated_amps: 12
  pool_pump:
    type: homebridge
    phase: 2
    homebridge_accessory: "Pool Pump"
    estimated_amps: 5
schedule:
  daytime:
    hours: "08:00-22:00"
    priority: [pool_pump, twc]
  nighttime:
    hours: "22:00-08:00"
    priority: [twc, pool_pump]
logging:
  level: info
"""


def test_load_config():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(MINIMAL_CONFIG)
        f.flush()
        cfg = load_config(f.name)
    os.unlink(f.name)
    assert cfg.mqtt_broker == "localhost"
    assert cfg.mqtt_port == 1883
    assert cfg.max_amps_per_phase == 20
    assert cfg.margin_amps == 3
    assert cfg.homebridge_url == "http://localhost:8581"
    assert "twc" in cfg.loads
    assert cfg.loads["twc"]["type"] == "chargectl"
    assert cfg.loads["twc"]["phases"] == [1, 2, 3]
    assert "daytime" in cfg.schedule
    assert cfg.schedule["daytime"]["priority"] == ["pool_pump", "twc"]
    assert cfg.log_level == "info"


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")
