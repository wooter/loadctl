from __future__ import annotations
import time
from loadctl.shedding import SheddingEngine
from loadctl.load import Load, LoadType, LoadState

def make_loads():
    return {
        "twc": Load("twc", LoadType.CHARGECTL, [1, 2, 3], 12, min_amps=6, max_amps=17),
        "pool_pump": Load("pool_pump", LoadType.HOMEBRIDGE, [2], 5, homebridge_accessory="Pool Pump"),
        "heat_pump": Load("heat_pump", LoadType.HOMEBRIDGE, [3], 8, homebridge_accessory="Heat Pump", depends_on=["pool_pump"]),
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
    free_amps = {1: -5.0, 2: 5.0, 3: 5.0}
    actions = engine.evaluate(loads, priority, free_amps)
    assert any(a["load"] == "jacuzzi" and a["action"] == "shed" for a in actions)

def test_shed_chargectl_reduces_amps_first():
    engine = SheddingEngine()
    loads = make_loads()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    free_amps = {1: 5.0, 2: -3.0, 3: 5.0}
    actions = engine.evaluate(loads, priority, free_amps)
    assert any(a["load"] == "twc" and a["action"] == "reduce" for a in actions)

def test_dependency_shedding():
    engine = SheddingEngine()
    loads = make_loads()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    free_amps = {1: 5.0, 2: -20.0, 3: 5.0}
    actions = engine.evaluate(loads, priority, free_amps)
    shed_names = [a["load"] for a in actions if a["action"] == "shed"]
    assert "pool_pump" in shed_names
    assert "heat_pump" in shed_names

def test_restore_when_room():
    engine = SheddingEngine()
    engine.last_restore_time = 0
    loads = make_loads()
    loads["jacuzzi"].shed()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    free_amps = {1: 15.0, 2: 15.0, 3: 15.0}
    actions = engine.evaluate(loads, priority, free_amps)
    assert any(a["load"] == "jacuzzi" and a["action"] == "restore" for a in actions)

def test_restore_respects_cooldown():
    engine = SheddingEngine()
    engine.last_restore_time = time.time()
    loads = make_loads()
    loads["jacuzzi"].shed()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    free_amps = {1: 15.0, 2: 15.0, 3: 15.0}
    actions = engine.evaluate(loads, priority, free_amps)
    assert not any(a["action"] == "restore" for a in actions)

def test_restore_checks_phase_room():
    engine = SheddingEngine()
    engine.last_restore_time = 0
    loads = make_loads()
    loads["jacuzzi"].shed()
    priority = ["heat_pump", "pool_pump", "twc", "jacuzzi"]
    free_amps = {1: 5.0, 2: 15.0, 3: 15.0}
    actions = engine.evaluate(loads, priority, free_amps)
    assert not any(a["load"] == "jacuzzi" and a["action"] == "restore" for a in actions)
