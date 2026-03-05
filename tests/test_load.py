from __future__ import annotations
from loadctl.load import Load, LoadState, LoadType, build_loads_from_config

def test_create_homebridge_load():
    load = Load(name="pool_pump", load_type=LoadType.HOMEBRIDGE, phases=[2], estimated_amps=5, homebridge_accessory="Pool Pump")
    assert load.name == "pool_pump"
    assert load.state == LoadState.ON
    assert load.phases == [2]
    assert load.estimated_amps == 5
    assert load.is_on_phase(2)
    assert not load.is_on_phase(1)

def test_create_chargectl_load():
    load = Load(name="twc", load_type=LoadType.CHARGECTL, phases=[1, 2, 3], estimated_amps=12, mqtt_topic="chargectl/control/max_amps", min_amps=6, max_amps=17)
    assert load.load_type == LoadType.CHARGECTL
    assert load.is_on_phase(1)
    assert load.is_on_phase(3)
    assert load.current_amps == 17

def test_shed_homebridge_load():
    load = Load(name="pool_pump", load_type=LoadType.HOMEBRIDGE, phases=[2], estimated_amps=5)
    load.shed()
    assert load.state == LoadState.SHED

def test_restore_homebridge_load():
    load = Load(name="pool_pump", load_type=LoadType.HOMEBRIDGE, phases=[2], estimated_amps=5)
    load.shed()
    load.restore()
    assert load.state == LoadState.ON

def test_shed_chargectl_reduces_amps():
    load = Load(name="twc", load_type=LoadType.CHARGECTL, phases=[1, 2, 3], estimated_amps=12, min_amps=6, max_amps=17)
    load.current_amps = 12
    freed = load.reduce_amps(5)
    assert load.current_amps == 7
    assert freed == 5

def test_shed_chargectl_respects_minimum():
    load = Load(name="twc", load_type=LoadType.CHARGECTL, phases=[1, 2, 3], estimated_amps=12, min_amps=6, max_amps=17)
    load.current_amps = 8
    freed = load.reduce_amps(5)
    assert load.current_amps == 0
    assert load.state == LoadState.SHED
    assert freed == 8

def test_build_loads_from_config():
    config_loads = {
        "twc": {"type": "chargectl", "phases": [1, 2, 3], "mqtt_topic": "chargectl/control/max_amps", "min_amps": 6, "max_amps": 17, "estimated_amps": 12},
        "pool_pump": {"type": "homebridge", "phase": 2, "homebridge_accessory": "Pool Pump", "estimated_amps": 5},
        "heat_pump": {"type": "homebridge", "phase": 3, "homebridge_accessory": "Heat Pump", "estimated_amps": 8, "depends_on": ["pool_pump"]},
    }
    loads = build_loads_from_config(config_loads)
    assert len(loads) == 3
    assert loads["twc"].load_type == LoadType.CHARGECTL
    assert loads["pool_pump"].phases == [2]
    assert loads["heat_pump"].depends_on == ["pool_pump"]
