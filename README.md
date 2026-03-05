# loadctl

Phase-aware energy management system for homes with a limited main fuse (20A per phase). Orchestrates high-power loads -- EV chargers, pool pump, heat pump, jacuzzi -- to prevent tripping the breaker while maximizing usage of available capacity.

## Architecture

```
Power source (RPICT4V3 / P1 meter)
  --> MQTT --> loadctl
                |-- phase monitor    (real-time amps per phase)
                |-- load manager     (state, phase assignment, priorities)
                |-- scheduler        (time windows --> priority order)
                |
                |-- --> MQTT --> chargectl     (cap TWC max_amps)
                |-- --> Homebridge API --> pool pump    on/off
                |-- --> Homebridge API --> heat pump    on/off
                '-- --> Homebridge API --> jacuzzi      on/off
```

loadctl reads per-phase power and voltage from MQTT, calculates current draw on each phase, and sheds or restores loads to stay under the configured limit. TWC chargers are controlled via chargectl (MQTT), while switchable devices are controlled through the Homebridge REST API.

## Features

- **Phase-aware shedding** -- monitors all three phases independently, sheds only loads on overloaded phases
- **Graduated TWC control** -- reduces charger amps before shedding on/off loads
- **Time-based priority** -- configurable schedules (e.g. pool pump first during the day, charging first at night)
- **Dependency management** -- e.g. heat pump auto-sheds when pool pump is shed
- **Homebridge integration** -- controls smart switches via the Homebridge REST API
- **MQTT integration** -- subscribes to power data, publishes load states, controls chargectl
- **Restore cooldown** -- 60s between restores to prevent oscillation

## Controlled Loads

| Load | Type | Control Method | Phases |
|------|------|---------------|--------|
| TWC chargers | `chargectl` | MQTT (`chargectl/control/max_amps`) | 1, 2, 3 |
| Pool pump | `homebridge` | Homebridge API | 2 |
| Heat pump | `homebridge` | Homebridge API (depends on pool pump) | 3 |
| Jacuzzi | `homebridge` | Homebridge API | 1 |

## Quick Start

```bash
git clone https://github.com/wooter/loadctl.git
cd loadctl
python3 -m venv .venv && source .venv/bin/activate
pip install .

# Copy and edit config
sudo mkdir -p /etc/loadctl
sudo cp docs/plans/2026-03-05-loadctl-design.md /etc/loadctl/  # reference
# Create /etc/loadctl/config.yaml (see Config Reference below)

loadctl --config /etc/loadctl/config.yaml
```

See [INSTALL.md](INSTALL.md) for full installation and systemd setup.

## Config Reference

Configuration lives in `/etc/loadctl/config.yaml`.

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `mqtt` | `broker` | `localhost` | MQTT broker hostname |
| `mqtt` | `port` | `1883` | MQTT broker port |
| `mqtt` | `username` | `null` | MQTT username (optional) |
| `mqtt` | `password` | `null` | MQTT password (optional) |
| `grid` | `max_amps_per_phase` | `20` | Main fuse rating per phase |
| `grid` | `margin_amps` | `3` | Safety margin below max |
| `power_source` | `topics` | -- | Map of power/voltage MQTT topics per phase |
| `homebridge` | `url` | `http://localhost:8581` | Homebridge API URL |
| `homebridge` | `username` | `admin` | Homebridge login |
| `homebridge` | `password` | `admin` | Homebridge password |
| `loads` | -- | -- | Load definitions (see example config) |
| `schedule` | -- | -- | Time windows with priority lists |
| `logging` | `level` | `info` | Log level (`debug`, `info`, `warning`) |

### Load definition

```yaml
loads:
  twc:
    type: chargectl          # chargectl or homebridge
    phases: [1, 2, 3]        # which phases this load uses
    mqtt_topic: "chargectl/control/max_amps"
    min_amps: 6              # minimum before shedding entirely
    max_amps: 17             # maximum allowed amps
    estimated_amps: 12       # expected draw (for on/off loads)

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
    depends_on: [pool_pump]  # auto-shed if pool_pump is shed
```

## MQTT Topics

### Subscribed

| Topic | Description |
|-------|-------------|
| `RPICT4V3/RP1`, `RP2`, `RP3` | Real power per phase (watts) |
| `RPICT4V3/Vrms1`, `Vrms2`, `Vrms3` | RMS voltage per phase |
| `loadctl/control/#` | Override commands |

### Published

| Topic | Description |
|-------|-------------|
| `loadctl/status` | JSON: per-phase amps, active schedule, load states (retained) |
| `loadctl/{load}/state` | JSON: individual load state (retained) |

### Control (outgoing)

| Topic | Description |
|-------|-------------|
| `chargectl/control/max_amps` | Caps chargectl's internal modulation to this value |

## How Shedding Works

Every evaluation cycle:

1. **Measure** -- read power and voltage per phase from MQTT, calculate amps (`P / V`)
2. **Check** -- compute `free_amps = max_amps - used_amps - margin` for each phase
3. **Shed** -- if any phase has `free_amps < 0`, shed the lowest-priority load on that phase. For chargectl loads, reduce amps gradually first; only shed entirely if below `min_amps`
4. **Cascade** -- if a load with dependents is shed, its dependents are shed too
5. **Restore** -- if all phases have headroom and 60s have passed since last restore, bring back the highest-priority shed load that fits

Shedding is instant (protect the fuse). Restoring is slow (prevent oscillation).

## License

MIT
