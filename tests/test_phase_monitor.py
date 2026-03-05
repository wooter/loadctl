from __future__ import annotations

import time

import pytest

from loadctl.phase_monitor import PhaseMonitor


def test_initial_state():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    assert mon.get_phase_amps(1) is None
    assert mon.get_free_amps(1) is None


def test_update_and_read():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    mon.update_power(1, 2300)
    mon.update_voltage(1, 230)
    assert mon.get_phase_amps(1) == pytest.approx(10.0)
    assert mon.get_free_amps(1) == pytest.approx(7.0)


def test_overloaded_phase():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    mon.update_power(1, 5060)
    mon.update_voltage(1, 230)
    assert mon.get_free_amps(1) == pytest.approx(-5.0)


def test_all_phases():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    for phase in [1, 2, 3]:
        mon.update_power(phase, 2300)
        mon.update_voltage(phase, 230)
    free = mon.get_all_free_amps()
    assert free == {1: pytest.approx(7.0), 2: pytest.approx(7.0), 3: pytest.approx(7.0)}


def test_worst_phase():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    mon.update_power(1, 1150); mon.update_voltage(1, 230)
    mon.update_power(2, 4600); mon.update_voltage(2, 230)
    mon.update_power(3, 2300); mon.update_voltage(3, 230)
    phase, free = mon.get_worst_phase()
    assert phase == 2
    assert free == pytest.approx(-3.0)


def test_is_stale():
    mon = PhaseMonitor(max_amps=20, margin_amps=3)
    mon.update_power(1, 2300); mon.update_voltage(1, 230)
    mon._last_update = time.time() - 20
    assert mon.is_stale(timeout=15)
    assert not mon.is_stale(timeout=30)
