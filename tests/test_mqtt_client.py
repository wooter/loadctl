from __future__ import annotations

from loadctl.mqtt_client import LoadMQTT
from loadctl.config import Config


def make_config(**overrides):
    defaults = dict(
        mqtt_broker="localhost",
        mqtt_port=1883,
        mqtt_username=None,
        mqtt_password=None,
        max_amps_per_phase=20,
        margin_amps=3,
        power_topics={
            "power_phase1": "RPICT4V3/RP1",
            "power_phase2": "RPICT4V3/RP2",
            "power_phase3": "RPICT4V3/RP3",
            "voltage_phase1": "RPICT4V3/Vrms1",
            "voltage_phase2": "RPICT4V3/Vrms2",
            "voltage_phase3": "RPICT4V3/Vrms3",
        },
        homebridge_url="http://localhost:8581",
        homebridge_username="admin",
        homebridge_password="admin",
        loads={},
        schedule={},
        log_level="info",
    )
    defaults.update(overrides)
    return Config(**defaults)


def test_subscribe_topics():
    cfg = make_config()
    mqtt = LoadMQTT(cfg)
    topics = mqtt.get_subscribe_topics()
    assert "RPICT4V3/RP1" in topics
    assert len(topics) == 6


def test_parse_power_message():
    cfg = make_config()
    mqtt = LoadMQTT(cfg)
    mqtt.on_message("RPICT4V3/RP1", b"1500.5")
    assert mqtt.power_data["power_phase1"] == 1500.5


def test_parse_voltage_message():
    cfg = make_config()
    mqtt = LoadMQTT(cfg)
    mqtt.on_message("RPICT4V3/Vrms1", b"232.1")
    assert mqtt.power_data["voltage_phase1"] == 232.1
