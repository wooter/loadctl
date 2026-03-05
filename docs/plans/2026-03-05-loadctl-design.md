# loadctl — Design Document

## Problem

A 20A-per-phase main fuse protects the house. Multiple high-power loads (2x Tesla Wall Chargers, pool filter pump, pool heat pump, jacuzzi) can trip the fuse when combined with normal household usage. Currently chargectl handles only the TWCs. The pool devices and jacuzzi are on HomeKit-switchable outlets but nothing orchestrates them.

## Solution

A phase-aware energy management system (`loadctl`) that reads per-phase power measurements, tracks controllable loads with their phase assignments, and sheds/restores loads based on configurable time-based priority rules. Sits above chargectl (TWC hardware controller) and Homebridge (HomeKit switch controller).

## Architecture

```
Power source (powerpi / P1 meter)
  → MQTT → loadctl
             ├── phase monitor (tracks amps per phase in real-time)
             ├── load manager (priority, phase assignment, state)
             ├── scheduler (time windows → active priority order)
             │
             ├── → MQTT → chargectl (cap max_amps)
             ├── → Homebridge API → pool pump on/off
             ├── → Homebridge API → heat pump on/off
             └── → Homebridge API → jacuzzi on/off
```

## Configuration

Single YAML file at `/etc/loadctl/config.yaml`:

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
    depends_on: []

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

## Shedding Algorithm

Every second, for each phase:

1. Calculate `used_amps = power / voltage` from MQTT measurements
2. Calculate `free_amps = max_amps - used_amps - margin`
3. If `free_amps < 0` on any phase → **shed**: starting from the lowest-priority load on that overloaded phase, turn it off (or reduce amps for TWC). Repeat until free_amps >= 0.
4. If `free_amps > restore_threshold` on all phases for 60 seconds → **restore**: starting from the highest-priority shed load, turn it back on if its phase has room.

Rules:
- Shedding is instant (protect the fuse)
- Restoring is slow (60s cooldown between restores, avoid oscillation)
- TWC is special: reduce amps gradually before shedding on/off loads
- `depends_on`: if pool_pump is shed, heat_pump is automatically shed
- Loads manually turned off via HomeKit stay off (loadctl doesn't force on)

## Homebridge Integration

Uses the Homebridge REST API (port 8581 by default) to:
- Query accessory state (on/off)
- Set accessory state (turn on/off)

## Interaction with chargectl

Phase 1 (now): loadctl publishes to `chargectl/control/max_amps` to cap chargectl's internal modulation. chargectl keeps its own modulation engine. Non-breaking, incremental deployment.

Phase 2 (later): Refactor chargectl to accept direct amps via `chargectl/control/set_amps`. Remove modulation engine from chargectl. loadctl becomes the sole decision-maker.

## MQTT Topics

### Subscribed
- Power measurement topics (configurable)
- `loadctl/control/#` (override commands)

### Published
- `loadctl/status` — JSON with per-phase amps, active schedule, load states
- `loadctl/{load_name}/state` — per-load state (on/off/shed/amps)
- `chargectl/control/max_amps` — TWC amp cap

## Logging

Python `logging` to stdout. INFO: load state changes, shedding events, schedule transitions. DEBUG: per-second measurements, Homebridge API calls.

## Project Structure

```
loadctl/
├── loadctl/
│   ├── __init__.py
│   ├── __main__.py        # entry point
│   ├── config.py          # YAML config loading
│   ├── phase_monitor.py   # per-phase power tracking
│   ├── load.py            # load definitions and state
│   ├── scheduler.py       # time window → priority mapping
│   ├── shedding.py        # shedding/restore algorithm
│   ├── homebridge.py      # Homebridge REST API client
│   └── mqtt_client.py     # MQTT subscribe + publish
├── config.example.yaml
├── pyproject.toml
├── README.md
├── INSTALL.md
└── tests/
```

## Dependencies

- `paho-mqtt` — MQTT client
- `pyyaml` — configuration
- `requests` — Homebridge API calls

## Explicit Non-Goals

- No web UI
- No solar tracking
- No database
- No Tesla API
- No scheduling of when loads should run (only priority when power is tight)
