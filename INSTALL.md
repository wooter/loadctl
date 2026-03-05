# Installing loadctl

## Prerequisites

- Raspberry Pi (or any Linux machine) with network access to:
  - MQTT broker (Mosquitto)
  - Homebridge instance
- Python 3.9 or later
- Mosquitto broker running and receiving power data (RPICT4V3 topics)
- Homebridge running with accessories configured for pool pump, heat pump, jacuzzi
- [chargectl](https://github.com/wooter/chargectl) running and subscribed to `chargectl/control/#`

## Install

```bash
# Clone the repository
git clone https://github.com/wooter/loadctl.git
cd loadctl

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install loadctl and its dependencies
pip install .
```

## Configure

Create the configuration directory and file:

```bash
sudo mkdir -p /etc/loadctl
sudo nano /etc/loadctl/config.yaml
```

Minimal configuration:

```yaml
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

  heat_pump:
    type: homebridge
    phase: 3
    homebridge_accessory: "Pool Heat Pump"
    estimated_amps: 8
    depends_on: [pool_pump]

  jacuzzi:
    type: homebridge
    phase: 1
    homebridge_accessory: "Jacuzzi"
    estimated_amps: 10

schedule:
  daytime:
    hours: "08:00-22:00"
    priority: [heat_pump, pool_pump, twc, jacuzzi]
  nighttime:
    hours: "22:00-08:00"
    priority: [twc, jacuzzi, pool_pump, heat_pump]

logging:
  level: info
```

## Test Manually

```bash
source .venv/bin/activate
loadctl --config /etc/loadctl/config.yaml
```

Verify in the logs that:
- MQTT connects and receives power data
- Homebridge authenticates successfully
- Phase amps are being calculated
- Loads appear with correct state

Press `Ctrl+C` to stop.

## Systemd Service

Create the service file:

```bash
sudo nano /etc/systemd/system/loadctl.service
```

Paste the following:

```ini
[Unit]
Description=loadctl - Phase-aware energy management
After=network.target mosquitto.service chargectl.service

[Service]
Type=simple
User=wouter
ExecStart=/home/wouter/loadctl/.venv/bin/loadctl --config /etc/loadctl/config.yaml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable loadctl
sudo systemctl start loadctl
```

## Check Logs

```bash
# Follow logs
journalctl -u loadctl -f

# Last 100 lines
journalctl -u loadctl -n 100
```

## Interaction with chargectl

loadctl does not control the Tesla Wall Connectors directly. Instead, it publishes to the MQTT topic `chargectl/control/max_amps` to cap chargectl's internal modulation.

- When loadctl reduces TWC amps, it publishes the new cap (e.g. `10`) to `chargectl/control/max_amps`
- chargectl continues its own modulation logic but will not exceed the cap
- When loadctl sheds TWC entirely, it publishes `0`
- When loadctl restores TWC, it publishes the configured `max_amps` value (e.g. `17`)

This is a non-breaking integration: chargectl keeps working independently if loadctl is stopped.
