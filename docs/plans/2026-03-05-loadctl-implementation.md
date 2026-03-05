# loadctl Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a phase-aware energy management system that orchestrates controllable loads (EV chargers, pool devices, jacuzzi) to keep per-phase amperage under the main fuse limit.

**Architecture:** Single Python package with six modules: config loading, phase monitor (per-phase amp tracking from MQTT), load definitions (state + phase + type), scheduler (time windows → priority), shedding engine (the brain), Homebridge REST client, and MQTT client. One main loop ties them together.

**Tech Stack:** Python 3.9+, paho-mqtt, pyyaml, requests, pytest. All modules use `from __future__ import annotations`.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `loadctl/__init__.py`
- Create: `config.example.yaml`
- Create: `.gitignore`
- Create: `tests/__init__.py`

**Step 1: Create all scaffolding files**

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "loadctl"
version = "0.1.0"
description = "Phase-aware energy management system for home load orchestration"
readme = "README.md"
requires-python = ">=3.9"
license = "MIT"
dependencies = [
    "paho-mqtt>=2.0",
    "pyyaml>=6.0",
    "requests>=2.28",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[project.scripts]
loadctl = "loadctl.__main__:main"
```

`loadctl/__init__.py`:
```python
"""loadctl - Phase-aware energy management system."""

__version__ = "0.1.0"
```

`config.example.yaml`:
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

`.gitignore`:
```
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.venv/
*.log
config.yaml
```

`tests/__init__.py`: empty file.

**Step 2: Commit**

```bash
git add pyproject.toml loadctl/__init__.py config.example.yaml .gitignore tests/__init__.py
git commit -m "feat: project scaffolding with pyproject.toml and example config"
```

---

### Task 2: Config loading

**Files:**
- Create: `loadctl/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing test**

```python
# tests/test_config.py
from __future__ import annotations

import tempfile
import os
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
    assert cfg.schedule["daytime"]["hours"] == "08:00-22:00"
    assert cfg.schedule["daytime"]["priority"] == ["pool_pump", "twc"]
    assert cfg.log_level == "info"


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/wouterhermans/Developer/loadctl && source .venv/bin/activate && python -m pytest tests/test_config.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write implementation**

```python
# loadctl/config.py
"""Configuration loading from YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    """Load configuration from a YAML file."""
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
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add loadctl/config.py tests/test_config.py
git commit -m "feat: config loading from YAML"
```

---

### Task 3: Load definitions and state

Pure data — no I/O. Defines load types, state tracking, phase assignments, and dependencies.

**Files:**
- Create: `loadctl/load.py`
- Create: `tests/test_load.py`

**Step 1: Write the failing tests**

```python
# tests/test_load.py
from __future__ import annotations

from loadctl.load import Load, LoadState, LoadType, build_loads_from_config


def test_create_homebridge_load():
    load = Load(
        name="pool_pump",
        load_type=LoadType.HOMEBRIDGE,
        phases=[2],
        estimated_amps=5,
        homebridge_accessory="Pool Pump",
    )
    assert load.name == "pool_pump"
    assert load.state == LoadState.ON
    assert load.phases == [2]
    assert load.estimated_amps == 5
    assert load.is_on_phase(2)
    assert not load.is_on_phase(1)


def test_create_chargectl_load():
    load = Load(
        name="twc",
        load_type=LoadType.CHARGECTL,
        phases=[1, 2, 3],
        estimated_amps=12,
        mqtt_topic="chargectl/control/max_amps",
        min_amps=6,
        max_amps=17,
    )
    assert load.load_type == LoadType.CHARGECTL
    assert load.is_on_phase(1)
    assert load.is_on_phase(3)
    assert load.current_amps == 17  # starts at max


def test_shed_homebridge_load():
    load = Load(
        name="pool_pump",
        load_type=LoadType.HOMEBRIDGE,
        phases=[2],
        estimated_amps=5,
    )
    load.shed()
    assert load.state == LoadState.SHED


def test_restore_homebridge_load():
    load = Load(
        name="pool_pump",
        load_type=LoadType.HOMEBRIDGE,
        phases=[2],
        estimated_amps=5,
    )
    load.shed()
    load.restore()
    assert load.state == LoadState.ON


def test_shed_chargectl_reduces_amps():
    load = Load(
        name="twc",
        load_type=LoadType.CHARGECTL,
        phases=[1, 2, 3],
        estimated_amps=12,
        min_amps=6,
        max_amps=17,
    )
    load.current_amps = 12
    freed = load.reduce_amps(5)
    assert load.current_amps == 7
    assert freed == 5


def test_shed_chargectl_respects_minimum():
    load = Load(
        name="twc",
        load_type=LoadType.CHARGECTL,
        phases=[1, 2, 3],
        estimated_amps=12,
        min_amps=6,
        max_amps=17,
    )
    load.current_amps = 8
    freed = load.reduce_amps(5)
    # Can only reduce to 6 (min), so freed = 2, then shed to 0
    assert load.current_amps == 0
    assert load.state == LoadState.SHED
    assert freed == 8  # freed all 8A


def test_build_loads_from_config():
    config_loads = {
        "twc": {
            "type": "chargectl",
            "phases": [1, 2, 3],
            "mqtt_topic": "chargectl/control/max_amps",
            "min_amps": 6,
            "max_amps": 17,
            "estimated_amps": 12,
        },
        "pool_pump": {
            "type": "homebridge",
            "phase": 2,
            "homebridge_accessory": "Pool Pump",
            "estimated_amps": 5,
        },
        "heat_pump": {
            "type": "homebridge",
            "phase": 3,
            "homebridge_accessory": "Heat Pump",
            "estimated_amps": 8,
            "depends_on": ["pool_pump"],
        },
    }
    loads = build_loads_from_config(config_loads)
    assert len(loads) == 3
    assert loads["twc"].load_type == LoadType.CHARGECTL
    assert loads["pool_pump"].phases == [2]
    assert loads["heat_pump"].depends_on == ["pool_pump"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_load.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# loadctl/load.py
"""Load definitions and state management."""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class LoadType(Enum):
    HOMEBRIDGE = "homebridge"
    CHARGECTL = "chargectl"


class LoadState(Enum):
    ON = "on"
    SHED = "shed"
    OFF = "off"  # manually turned off, loadctl won't force on


class Load:
    """A controllable electrical load."""

    def __init__(
        self,
        name: str,
        load_type: LoadType,
        phases: list[int],
        estimated_amps: float,
        homebridge_accessory: str | None = None,
        mqtt_topic: str | None = None,
        min_amps: int = 0,
        max_amps: int = 0,
        depends_on: list[str] | None = None,
    ):
        self.name = name
        self.load_type = load_type
        self.phases = phases
        self.estimated_amps = estimated_amps
        self.homebridge_accessory = homebridge_accessory
        self.mqtt_topic = mqtt_topic
        self.min_amps = min_amps
        self.max_amps = max_amps
        self.current_amps = max_amps if load_type == LoadType.CHARGECTL else 0
        self.depends_on = depends_on or []
        self.state = LoadState.ON

    def is_on_phase(self, phase: int) -> bool:
        """Check if this load draws from the given phase."""
        return phase in self.phases

    def shed(self) -> None:
        """Shed this load (turn off or set to 0A)."""
        self.state = LoadState.SHED
        if self.load_type == LoadType.CHARGECTL:
            self.current_amps = 0
        logger.info("Shed load %s", self.name)

    def restore(self) -> None:
        """Restore this load after shedding."""
        self.state = LoadState.ON
        if self.load_type == LoadType.CHARGECTL:
            self.current_amps = self.max_amps
        logger.info("Restored load %s", self.name)

    def reduce_amps(self, amount: float) -> float:
        """Reduce chargectl load by amount. Returns actual amps freed.

        If reducing below min_amps, sheds entirely.
        """
        if self.load_type != LoadType.CHARGECTL or self.state == LoadState.SHED:
            return 0

        old = self.current_amps
        new = self.current_amps - amount

        if new >= self.min_amps:
            self.current_amps = int(new)
            return old - self.current_amps
        else:
            # Can't stay above minimum, shed entirely
            self.shed()
            return old

    def increase_amps(self, amount: float) -> float:
        """Increase chargectl load by amount. Returns actual amps added."""
        if self.load_type != LoadType.CHARGECTL:
            return 0

        old = self.current_amps
        new = min(self.current_amps + amount, self.max_amps)
        self.current_amps = int(new)
        return self.current_amps - old


def build_loads_from_config(config_loads: dict) -> dict[str, Load]:
    """Build Load objects from the config loads dict."""
    loads = {}
    for name, cfg in config_loads.items():
        load_type = LoadType(cfg["type"])
        phases = cfg.get("phases", [cfg["phase"]] if "phase" in cfg else [])
        loads[name] = Load(
            name=name,
            load_type=load_type,
            phases=phases,
            estimated_amps=cfg.get("estimated_amps", 0),
            homebridge_accessory=cfg.get("homebridge_accessory"),
            mqtt_topic=cfg.get("mqtt_topic"),
            min_amps=cfg.get("min_amps", 0),
            max_amps=cfg.get("max_amps", 0),
            depends_on=cfg.get("depends_on", []),
        )
    return loads
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_load.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add loadctl/load.py tests/test_load.py
git commit -m "feat: load definitions with state, phases, dependencies"
```

---

### Task 4: Phase monitor

Tracks per-phase power from MQTT. Pure data — receives measurements, calculates amps.

**Files:**
- Create: `loadctl/phase_monitor.py`
- Create: `tests/test_phase_monitor.py`

**Step 1: Write the failing tests**

```python
# tests/test_phase_monitor.py
from __future__ import annotations

import time
from loadctl.phase_monitor import PhaseMonitor


def test_initial_state():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    assert mon.get_phase_amps(1) is None
    assert mon.get_free_amps(1) is None


def test_update_and_read():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    mon.update_power(1, 2300)  # watts
    mon.update_voltage(1, 230)  # volts
    assert mon.get_phase_amps(1) == pytest.approx(10.0)
    assert mon.get_free_amps(1) == pytest.approx(7.0)  # 20 - 10 - 3


def test_overloaded_phase():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    mon.update_power(1, 5060)
    mon.update_voltage(1, 230)
    assert mon.get_free_amps(1) == pytest.approx(-5.0)  # 20 - 22 - 3


def test_all_phases():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    for phase in [1, 2, 3]:
        mon.update_power(phase, 2300)
        mon.update_voltage(phase, 230)
    free = mon.get_all_free_amps()
    assert free == {1: pytest.approx(7.0), 2: pytest.approx(7.0), 3: pytest.approx(7.0)}


def test_worst_phase():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    mon.update_power(1, 1150)
    mon.update_voltage(1, 230)
    mon.update_power(2, 4600)
    mon.update_voltage(2, 230)
    mon.update_power(3, 2300)
    mon.update_voltage(3, 230)
    phase, free = mon.get_worst_phase()
    assert phase == 2
    assert free == pytest.approx(-3.0)  # 20 - 20 - 3


def test_is_stale():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    mon.update_power(1, 2300)
    mon.update_voltage(1, 230)
    mon._last_update = time.time() - 20
    assert mon.is_stale(timeout=15)
    assert not mon.is_stale(timeout=30)


import pytest
```

**Step 2: Run test, verify fails**

**Step 3: Write implementation**

```python
# loadctl/phase_monitor.py
"""Per-phase power monitoring."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class PhaseMonitor:
    """Tracks per-phase power measurements and calculates available amps."""

    def __init__(self, max_amps: int, margin_amps: int):
        self.max_amps = max_amps
        self.margin_amps = margin_amps
        self._power: dict[int, float] = {}
        self._voltage: dict[int, float] = {}
        self._last_update = 0.0

    def update_power(self, phase: int, watts: float) -> None:
        """Update power measurement for a phase."""
        self._power[phase] = watts
        self._last_update = time.time()

    def update_voltage(self, phase: int, volts: float) -> None:
        """Update voltage measurement for a phase."""
        self._voltage[phase] = volts
        self._last_update = time.time()

    def get_phase_amps(self, phase: int) -> float | None:
        """Get current amps on a phase. Returns None if no data."""
        power = self._power.get(phase)
        voltage = self._voltage.get(phase)
        if power is None or voltage is None or voltage == 0:
            return None
        return power / voltage

    def get_free_amps(self, phase: int) -> float | None:
        """Get free amps on a phase (max - used - margin). None if no data."""
        amps = self.get_phase_amps(phase)
        if amps is None:
            return None
        return self.max_amps - amps - self.margin_amps

    def get_all_free_amps(self) -> dict[int, float]:
        """Get free amps for all known phases."""
        result = {}
        for phase in set(self._power.keys()) | set(self._voltage.keys()):
            free = self.get_free_amps(phase)
            if free is not None:
                result[phase] = free
        return result

    def get_worst_phase(self) -> tuple[int | None, float | None]:
        """Get the phase with the least free amps."""
        free_amps = self.get_all_free_amps()
        if not free_amps:
            return None, None
        worst = min(free_amps, key=free_amps.get)
        return worst, free_amps[worst]

    def is_stale(self, timeout: float = 15.0) -> bool:
        """Check if measurements are too old."""
        if self._last_update == 0:
            return True
        return (time.time() - self._last_update) > timeout
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_phase_monitor.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add loadctl/phase_monitor.py tests/test_phase_monitor.py
git commit -m "feat: per-phase power monitoring with free amps calculation"
```

---

### Task 5: Scheduler

Maps time windows to active priority orders. Pure logic, no I/O.

**Files:**
- Create: `loadctl/scheduler.py`
- Create: `tests/test_scheduler.py`

**Step 1: Write the failing tests**

```python
# tests/test_scheduler.py
from __future__ import annotations

from datetime import time as dt_time
from loadctl.scheduler import Scheduler


def test_parse_schedule():
    schedule_config = {
        "daytime": {
            "hours": "08:00-22:00",
            "priority": ["heat_pump", "pool_pump", "twc"],
        },
        "nighttime": {
            "hours": "22:00-08:00",
            "priority": ["twc", "pool_pump", "heat_pump"],
        },
    }
    scheduler = Scheduler(schedule_config)
    assert len(scheduler.windows) == 2


def test_get_priority_daytime():
    schedule_config = {
        "daytime": {
            "hours": "08:00-22:00",
            "priority": ["heat_pump", "pool_pump", "twc"],
        },
        "nighttime": {
            "hours": "22:00-08:00",
            "priority": ["twc", "pool_pump", "heat_pump"],
        },
    }
    scheduler = Scheduler(schedule_config)
    # 14:00 is daytime
    priority = scheduler.get_priority_at(dt_time(14, 0))
    assert priority == ["heat_pump", "pool_pump", "twc"]


def test_get_priority_nighttime():
    schedule_config = {
        "daytime": {
            "hours": "08:00-22:00",
            "priority": ["heat_pump", "pool_pump", "twc"],
        },
        "nighttime": {
            "hours": "22:00-08:00",
            "priority": ["twc", "pool_pump", "heat_pump"],
        },
    }
    scheduler = Scheduler(schedule_config)
    # 23:00 is nighttime
    priority = scheduler.get_priority_at(dt_time(23, 0))
    assert priority == ["twc", "pool_pump", "heat_pump"]


def test_overnight_window():
    schedule_config = {
        "night": {
            "hours": "22:00-06:00",
            "priority": ["twc"],
        },
    }
    scheduler = Scheduler(schedule_config)
    # 02:00 should match overnight window
    priority = scheduler.get_priority_at(dt_time(2, 0))
    assert priority == ["twc"]


def test_no_matching_window_returns_empty():
    schedule_config = {
        "morning": {
            "hours": "06:00-12:00",
            "priority": ["twc"],
        },
    }
    scheduler = Scheduler(schedule_config)
    # 15:00 has no window
    priority = scheduler.get_priority_at(dt_time(15, 0))
    assert priority == []
```

**Step 2: Run test, verify fails**

**Step 3: Write implementation**

```python
# loadctl/scheduler.py
"""Time-based schedule for load priorities."""

from __future__ import annotations

import logging
from datetime import datetime, time as dt_time

logger = logging.getLogger(__name__)


class TimeWindow:
    """A named time window with a priority order."""

    def __init__(self, name: str, start: dt_time, end: dt_time, priority: list[str]):
        self.name = name
        self.start = start
        self.end = end
        self.priority = priority

    def contains(self, t: dt_time) -> bool:
        """Check if time t falls within this window."""
        if self.start <= self.end:
            # Normal window (e.g., 08:00-22:00)
            return self.start <= t < self.end
        else:
            # Overnight window (e.g., 22:00-08:00)
            return t >= self.start or t < self.end


class Scheduler:
    """Maps time of day to active load priority order."""

    def __init__(self, schedule_config: dict):
        self.windows: list[TimeWindow] = []
        for name, cfg in schedule_config.items():
            start_str, end_str = cfg["hours"].split("-")
            start = dt_time(*map(int, start_str.split(":")))
            end = dt_time(*map(int, end_str.split(":")))
            self.windows.append(TimeWindow(name, start, end, cfg["priority"]))

    def get_priority(self) -> list[str]:
        """Get the current priority order based on time of day."""
        return self.get_priority_at(datetime.now().time())

    def get_priority_at(self, t: dt_time) -> list[str]:
        """Get priority order for a specific time."""
        for window in self.windows:
            if window.contains(t):
                return window.priority
        return []
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add loadctl/scheduler.py tests/test_scheduler.py
git commit -m "feat: time-based scheduler for load priority windows"
```

---

### Task 6: Shedding engine

The brain. Takes phase monitor data + load states + priority order, decides what to shed/restore.

**Files:**
- Create: `loadctl/shedding.py`
- Create: `tests/test_shedding.py`

**Step 1: Write the failing tests**

```python
# tests/test_shedding.py
from __future__ import annotations

import time
from loadctl.shedding import SheddingEngine
from loadctl.load import Load, LoadType, LoadState


def make_loads():
    return {
        "twc": Load("twc", LoadType.CHARGECTL, [1, 2, 3], 12, min_amps=6, max_amps=17),
        "pool_pump": Load("pool_pump", LoadType.HOMEBRIDGE, [2], 5, homebridge_accessory="Pool Pump"),
        "heat_pump": Load("heat_pump", LoadType.HOMEBRIDGE, [3], 8,
                         homebridge_accessory="Heat Pump", depends_on=["pool_pump"]),
        "jacuzzi": Load("jacuzzi", LoadType.HOMEBRIDGE, [1], 10, homebridge_accessory="Jacuzzi"),
    }


def test_no_shedding_when_ok():
    engine = SheddingEngine()
    loads = make_loads()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    free_amps = {1: 5.0, 2: 5.0, 3: 5.0}
    actions = engine.evaluate(loads, priority, free_amps)
    assert len(actions) == 0


def test_shed_lowest_priority_on_overloaded_phase():
    engine = SheddingEngine()
    loads = make_loads()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    # Phase 1 is overloaded by 5A. Jacuzzi (lowest priority on phase 1) should be shed.
    free_amps = {1: -5.0, 2: 5.0, 3: 5.0}
    actions = engine.evaluate(loads, priority, free_amps)
    assert any(a["load"] == "jacuzzi" and a["action"] == "shed" for a in actions)


def test_shed_chargectl_reduces_amps_first():
    engine = SheddingEngine()
    loads = make_loads()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    # Phase 2 overloaded by 3A. TWC is on phase 2, reduce amps before shedding pool_pump.
    free_amps = {1: 5.0, 2: -3.0, 3: 5.0}
    actions = engine.evaluate(loads, priority, free_amps)
    # TWC should be reduced, not pool_pump shed
    assert any(a["load"] == "twc" and a["action"] == "reduce" for a in actions)


def test_dependency_shedding():
    engine = SheddingEngine()
    loads = make_loads()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    # Phase 2 overloaded badly. Pool pump needs to be shed.
    # Heat pump depends on pool_pump, so it should also be shed.
    free_amps = {1: 5.0, 2: -20.0, 3: 5.0}
    actions = engine.evaluate(loads, priority, free_amps)
    shed_names = [a["load"] for a in actions if a["action"] == "shed"]
    assert "pool_pump" in shed_names
    assert "heat_pump" in shed_names


def test_restore_when_room():
    engine = SheddingEngine()
    engine.last_restore_time = 0  # allow immediate restore
    loads = make_loads()
    loads["jacuzzi"].shed()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    # All phases have plenty of room, jacuzzi was shed, should restore
    free_amps = {1: 15.0, 2: 15.0, 3: 15.0}
    actions = engine.evaluate(loads, priority, free_amps)
    assert any(a["load"] == "jacuzzi" and a["action"] == "restore" for a in actions)


def test_restore_respects_cooldown():
    engine = SheddingEngine()
    engine.last_restore_time = time.time()  # just restored
    loads = make_loads()
    loads["jacuzzi"].shed()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    free_amps = {1: 15.0, 2: 15.0, 3: 15.0}
    actions = engine.evaluate(loads, priority, free_amps)
    # Should not restore during cooldown
    assert not any(a["action"] == "restore" for a in actions)


def test_restore_checks_phase_room():
    engine = SheddingEngine()
    engine.last_restore_time = 0
    loads = make_loads()
    loads["jacuzzi"].shed()  # jacuzzi is 10A on phase 1
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    # Phase 1 only has 5A free, jacuzzi needs 10A — can't restore
    free_amps = {1: 5.0, 2: 15.0, 3: 15.0}
    actions = engine.evaluate(loads, priority, free_amps)
    assert not any(a["load"] == "jacuzzi" and a["action"] == "restore" for a in actions)
```

**Step 2: Run test, verify fails**

**Step 3: Write implementation**

```python
# loadctl/shedding.py
"""Shedding and restore algorithm."""

from __future__ import annotations

import logging
import time

from loadctl.load import Load, LoadState, LoadType

logger = logging.getLogger(__name__)

RESTORE_COOLDOWN = 60  # seconds between restores


class SheddingEngine:
    """Decides which loads to shed or restore based on per-phase free amps."""

    def __init__(self):
        self.last_restore_time = 0.0

    def evaluate(
        self,
        loads: dict[str, Load],
        priority: list[str],
        free_amps: dict[int, float],
    ) -> list[dict]:
        """Evaluate current state and return a list of actions.

        Actions are dicts: {"load": name, "action": "shed"|"restore"|"reduce", "amps": N}
        """
        actions = []

        # Phase 1: Shedding — for each overloaded phase
        working_free = dict(free_amps)
        for phase, free in sorted(free_amps.items()):
            if free >= 0:
                continue

            deficit = abs(free)
            # Get loads on this phase, lowest priority first (reverse of priority list)
            phase_loads = [
                name for name in reversed(priority)
                if name in loads
                and loads[name].is_on_phase(phase)
                and loads[name].state != LoadState.SHED
            ]

            for load_name in phase_loads:
                if deficit <= 0:
                    break

                load = loads[load_name]

                # For chargectl: try reducing amps first
                if load.load_type == LoadType.CHARGECTL and load.current_amps > load.min_amps:
                    can_free = load.current_amps - load.min_amps
                    reduce_by = min(can_free, deficit)
                    if reduce_by > 0:
                        actions.append({
                            "load": load_name,
                            "action": "reduce",
                            "amps": load.current_amps - int(reduce_by),
                        })
                        deficit -= reduce_by
                        # Update working free amps for all phases this load is on
                        for p in load.phases:
                            working_free[p] = working_free.get(p, 0) + reduce_by
                        continue

                # Shed the load entirely
                actions.append({"load": load_name, "action": "shed"})
                for p in load.phases:
                    working_free[p] = working_free.get(p, 0) + load.estimated_amps
                deficit -= load.estimated_amps

                # Handle dependencies: shed loads that depend on this one
                for dep_name, dep_load in loads.items():
                    if load_name in dep_load.depends_on and dep_load.state != LoadState.SHED:
                        actions.append({"load": dep_name, "action": "shed"})
                        for p in dep_load.phases:
                            working_free[p] = working_free.get(p, 0) + dep_load.estimated_amps

        # Phase 2: Restoring — if no phase is overloaded and cooldown elapsed
        if all(f >= 0 for f in working_free.values()):
            now = time.time()
            if now - self.last_restore_time >= RESTORE_COOLDOWN:
                # Find highest-priority shed load that fits
                for load_name in priority:
                    if load_name not in loads:
                        continue
                    load = loads[load_name]
                    if load.state != LoadState.SHED:
                        continue

                    # Check dependencies: don't restore if a dependency is shed
                    deps_ok = all(
                        loads[dep].state != LoadState.SHED
                        for dep in load.depends_on
                        if dep in loads
                    )
                    if not deps_ok:
                        continue

                    # Check if there's room on all phases this load uses
                    fits = all(
                        working_free.get(p, 0) >= load.estimated_amps
                        for p in load.phases
                    )
                    if fits:
                        actions.append({"load": load_name, "action": "restore"})
                        self.last_restore_time = now
                        break  # Only restore one at a time

        return actions
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_shedding.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add loadctl/shedding.py tests/test_shedding.py
git commit -m "feat: phase-aware shedding engine with dependencies and restore cooldown"
```

---

### Task 7: Homebridge REST client

**Files:**
- Create: `loadctl/homebridge.py`
- Create: `tests/test_homebridge.py`

**Step 1: Write the failing tests**

```python
# tests/test_homebridge.py
from __future__ import annotations

from unittest.mock import patch, MagicMock
from loadctl.homebridge import HomebridgeClient


def test_login():
    client = HomebridgeClient("http://localhost:8581", "admin", "admin")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok123"}
    mock_resp.raise_for_status = MagicMock()

    with patch("loadctl.homebridge.requests.post", return_value=mock_resp) as mock_post:
        client.login()
        mock_post.assert_called_once()
        assert client._token == "tok123"


def test_get_accessory_state():
    client = HomebridgeClient("http://localhost:8581", "admin", "admin")
    client._token = "tok123"

    accessories = [
        {"aid": 10, "serviceName": "Pool Pump", "type": "Switch",
         "serviceCharacteristics": [
             {"description": "On", "value": 1, "iid": 11, "type": "On"}
         ]},
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = accessories
    mock_resp.raise_for_status = MagicMock()

    with patch("loadctl.homebridge.requests.get", return_value=mock_resp):
        state = client.get_accessory_state("Pool Pump")
        assert state is True


def test_set_accessory_off():
    client = HomebridgeClient("http://localhost:8581", "admin", "admin")
    client._token = "tok123"
    client._accessory_cache = {
        "Pool Pump": {"aid": 10, "on_iid": 11}
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with patch("loadctl.homebridge.requests.put", return_value=mock_resp) as mock_put:
        client.set_accessory("Pool Pump", False)
        mock_put.assert_called_once()
        call_json = mock_put.call_args[1]["json"]
        assert call_json["value"] == 0
```

**Step 2: Run test, verify fails**

**Step 3: Write implementation**

```python
# loadctl/homebridge.py
"""Homebridge REST API client."""

from __future__ import annotations

import logging
import requests

logger = logging.getLogger(__name__)


class HomebridgeClient:
    """Controls HomeKit accessories via Homebridge REST API."""

    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self._token: str | None = None
        self._accessory_cache: dict[str, dict] = {}

    def login(self) -> None:
        """Authenticate and get a bearer token."""
        resp = requests.post(
            f"{self.url}/api/auth/login",
            json={"username": self.username, "password": self.password},
            timeout=10,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        logger.info("Homebridge authenticated")

    def get_accessory_state(self, accessory_name: str) -> bool | None:
        """Get the on/off state of a named accessory. Returns None if not found."""
        self._ensure_token()
        resp = requests.get(
            f"{self.url}/api/accessories",
            headers=self._headers(),
            timeout=10,
        )
        resp.raise_for_status()

        for acc in resp.json():
            if acc.get("serviceName") == accessory_name:
                # Cache the aid and iid for later set calls
                for char in acc.get("serviceCharacteristics", []):
                    if char.get("type") == "On" or char.get("description") == "On":
                        self._accessory_cache[accessory_name] = {
                            "aid": acc["aid"],
                            "on_iid": char["iid"],
                        }
                        return bool(char.get("value", 0))
        return None

    def set_accessory(self, accessory_name: str, on: bool) -> bool:
        """Turn an accessory on or off. Returns True on success."""
        self._ensure_token()
        cached = self._accessory_cache.get(accessory_name)
        if not cached:
            # Try to discover it first
            self.get_accessory_state(accessory_name)
            cached = self._accessory_cache.get(accessory_name)
            if not cached:
                logger.warning("Accessory %s not found", accessory_name)
                return False

        resp = requests.put(
            f"{self.url}/api/accessories/{cached['aid']}",
            headers=self._headers(),
            json={
                "characteristicType": "On",
                "value": 1 if on else 0,
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Set %s to %s", accessory_name, "ON" if on else "OFF")
        return True

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def _ensure_token(self) -> None:
        if not self._token:
            self.login()
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_homebridge.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add loadctl/homebridge.py tests/test_homebridge.py
git commit -m "feat: Homebridge REST API client for accessory control"
```

---

### Task 8: MQTT client

**Files:**
- Create: `loadctl/mqtt_client.py`
- Create: `tests/test_mqtt_client.py`

**Step 1: Write the failing tests**

```python
# tests/test_mqtt_client.py
from __future__ import annotations

from loadctl.mqtt_client import LoadMQTT
from loadctl.config import Config


def make_config(**overrides):
    defaults = dict(
        mqtt_broker="localhost", mqtt_port=1883,
        mqtt_username=None, mqtt_password=None,
        max_amps_per_phase=20, margin_amps=3,
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
        loads={}, schedule={},
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
```

**Step 2: Run test, verify fails**

**Step 3: Write implementation**

```python
# loadctl/mqtt_client.py
"""MQTT client for power data and load control."""

from __future__ import annotations

import json
import logging
import paho.mqtt.client as mqtt
from loadctl.config import Config

logger = logging.getLogger(__name__)

TOPIC_PREFIX = "loadctl"


class LoadMQTT:
    """Handles MQTT for power measurements and status publishing."""

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
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="loadctl"
        )
        if self.config.mqtt_username:
            self._client.username_pw_set(
                self.config.mqtt_username, self.config.mqtt_password
            )
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
            self._client.publish(
                f"{TOPIC_PREFIX}/{load_name}/state", json.dumps(state), retain=True
            )

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        logger.info("MQTT connected (rc=%s)", rc)
        for topic in self.get_subscribe_topics():
            client.subscribe(topic)

    def _on_message(self, client, userdata, message):
        self.on_message(message.topic, message.payload)
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_mqtt_client.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add loadctl/mqtt_client.py tests/test_mqtt_client.py
git commit -m "feat: MQTT client for power data and status publishing"
```

---

### Task 9: Main loop

**Files:**
- Create: `loadctl/__main__.py`
- Create: `tests/test_main.py`

**Step 1: Write the failing test**

```python
# tests/test_main.py
from __future__ import annotations

from unittest.mock import patch
import tempfile
import os

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
```

**Step 2: Run test, verify fails**

**Step 3: Write implementation**

```python
# loadctl/__main__.py
"""loadctl entry point."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from loadctl import __version__
from loadctl.config import load_config
from loadctl.homebridge import HomebridgeClient
from loadctl.load import build_loads_from_config, LoadType, LoadState
from loadctl.mqtt_client import LoadMQTT
from loadctl.phase_monitor import PhaseMonitor
from loadctl.scheduler import Scheduler
from loadctl.shedding import SheddingEngine

logger = logging.getLogger("loadctl")

_running = True


def _handle_signal(sig, frame):
    global _running
    logger.info("Received signal %d, shutting down...", sig)
    _running = False


def run_loop(
    mqtt_client: LoadMQTT,
    homebridge: HomebridgeClient,
    monitor: PhaseMonitor,
    scheduler: Scheduler,
    engine: SheddingEngine,
    loads: dict,
) -> None:
    """Main control loop."""
    global _running

    logger.info("Entering main loop")

    while _running:
        # 1. Update phase monitor from MQTT data
        for phase_num in [1, 2, 3]:
            power = mqtt_client.power_data.get(f"power_phase{phase_num}")
            voltage = mqtt_client.power_data.get(f"voltage_phase{phase_num}")
            if power is not None:
                monitor.update_power(phase_num, power)
            if voltage is not None:
                monitor.update_voltage(phase_num, voltage)

        # 2. Get current priority from scheduler
        priority = scheduler.get_priority()

        # 3. Get free amps per phase
        free_amps = monitor.get_all_free_amps()

        if not free_amps:
            time.sleep(1)
            continue

        # 4. Watchdog: if data is stale, shed everything
        if monitor.is_stale():
            logger.warning("Power data stale, shedding all loads")
            for load in loads.values():
                if load.state != LoadState.SHED:
                    _execute_action({"load": load.name, "action": "shed"}, loads, mqtt_client, homebridge)
            time.sleep(1)
            continue

        # 5. Run shedding engine
        actions = engine.evaluate(loads, priority, free_amps)

        # 6. Execute actions
        for action in actions:
            _execute_action(action, loads, mqtt_client, homebridge)

        # 7. Publish status
        mqtt_client.publish_status({
            "free_amps": {str(k): round(v, 1) for k, v in free_amps.items()},
            "loads": {
                name: {
                    "state": load.state.value,
                    "amps": load.current_amps if load.load_type == LoadType.CHARGECTL else None,
                }
                for name, load in loads.items()
            },
        })

        time.sleep(1)


def _execute_action(action: dict, loads: dict, mqtt_client: LoadMQTT, homebridge: HomebridgeClient) -> None:
    """Execute a shedding/restore action."""
    load_name = action["load"]
    load = loads.get(load_name)
    if not load:
        return

    if action["action"] == "shed":
        load.shed()
        if load.load_type == LoadType.HOMEBRIDGE and load.homebridge_accessory:
            try:
                homebridge.set_accessory(load.homebridge_accessory, False)
            except Exception:
                logger.exception("Failed to shed %s via Homebridge", load_name)
        elif load.load_type == LoadType.CHARGECTL and load.mqtt_topic:
            mqtt_client.publish(load.mqtt_topic, "0")

        mqtt_client.publish_load_state(load_name, {"state": "shed"})

    elif action["action"] == "reduce":
        new_amps = action.get("amps", load.min_amps)
        load.current_amps = new_amps
        if load.mqtt_topic:
            mqtt_client.publish(load.mqtt_topic, str(new_amps))
        logger.info("Reduced %s to %dA", load_name, new_amps)
        mqtt_client.publish_load_state(load_name, {"state": "reduced", "amps": new_amps})

    elif action["action"] == "restore":
        load.restore()
        if load.load_type == LoadType.HOMEBRIDGE and load.homebridge_accessory:
            try:
                homebridge.set_accessory(load.homebridge_accessory, True)
            except Exception:
                logger.exception("Failed to restore %s via Homebridge", load_name)
        elif load.load_type == LoadType.CHARGECTL and load.mqtt_topic:
            mqtt_client.publish(load.mqtt_topic, str(load.max_amps))

        mqtt_client.publish_load_state(load_name, {"state": "on"})


def main(argv: list[str] | None = None) -> None:
    """Entry point for loadctl."""
    parser = argparse.ArgumentParser(
        prog="loadctl",
        description="Phase-aware energy management system",
    )
    parser.add_argument("--config", "-c", default="/etc/loadctl/config.yaml")
    parser.add_argument("--version", "-v", action="version", version=f"loadctl {__version__}")
    args = parser.parse_args(argv)

    config = load_config(args.config)

    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.info("loadctl %s starting", __version__)

    mqtt_client = LoadMQTT(config)
    homebridge = HomebridgeClient(config.homebridge_url, config.homebridge_username, config.homebridge_password)
    monitor = PhaseMonitor(config.max_amps_per_phase, config.margin_amps)
    scheduler = Scheduler(config.schedule)
    engine = SheddingEngine()
    loads = build_loads_from_config(config.loads)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        mqtt_client.connect()
        homebridge.login()
        run_loop(mqtt_client, homebridge, monitor, scheduler, engine, loads)
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
    finally:
        logger.info("Shutting down...")
        mqtt_client.disconnect()
        logger.info("Goodbye")


if __name__ == "__main__":
    main()
```

**Step 4: Run all tests**

Run: `python -m pytest -v`
Expected: all pass

**Step 5: Commit**

```bash
git add loadctl/__main__.py tests/test_main.py
git commit -m "feat: main loop with shedding, Homebridge control, and status publishing"
```

---

### Task 10: Documentation

**Files:**
- Create: `README.md`
- Create: `INSTALL.md`

Write README.md covering: what it is, architecture diagram, config reference, MQTT topics, how shedding works, hardware requirements.

Write INSTALL.md covering: prerequisites, install on RPi, configure, systemd service, migrating from standalone chargectl modulation.

**Step 1: Write both files**

(Content follows the same pattern as chargectl's docs — adapted for loadctl's config and features.)

**Step 2: Commit**

```bash
git add README.md INSTALL.md
git commit -m "docs: add README and installation guide"
```

---

### Task 11: Create GitHub repo and push

```bash
cd /Users/wouterhermans/Developer/loadctl
gh repo create wooter/loadctl --public --description "Phase-aware energy management system for home load orchestration" --source . --push
```
