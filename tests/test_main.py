from __future__ import annotations
from unittest.mock import patch
import tempfile, os

VALID_CONFIG = """
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
schedule:
  daytime:
    hours: "08:00-22:00"
    priority: [twc]
logging:
  level: debug
"""

def test_main_loads_and_starts():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(VALID_CONFIG)
        path = f.name
    with patch("loadctl.__main__.LoadMQTT") as mock_mqtt, \
         patch("loadctl.__main__.HomebridgeClient") as mock_hb, \
         patch("loadctl.__main__.run_loop") as mock_loop:
        from loadctl.__main__ import main
        main(["--config", path])
        mock_mqtt.assert_called_once()
        mock_hb.assert_called_once()
        mock_loop.assert_called_once()
    os.unlink(path)
