from __future__ import annotations

from datetime import time as dt_time

from loadctl.scheduler import Scheduler


def test_parse_schedule():
    cfg = {
        "daytime": {
            "hours": "08:00-22:00",
            "priority": ["heat_pump", "pool_pump", "twc"],
        },
        "nighttime": {
            "hours": "22:00-08:00",
            "priority": ["twc", "pool_pump", "heat_pump"],
        },
    }
    scheduler = Scheduler(cfg)
    assert len(scheduler.windows) == 2


def test_get_priority_daytime():
    cfg = {
        "daytime": {
            "hours": "08:00-22:00",
            "priority": ["heat_pump", "pool_pump", "twc"],
        },
        "nighttime": {
            "hours": "22:00-08:00",
            "priority": ["twc", "pool_pump", "heat_pump"],
        },
    }
    scheduler = Scheduler(cfg)
    assert scheduler.get_priority_at(dt_time(14, 0)) == ["heat_pump", "pool_pump", "twc"]


def test_get_priority_nighttime():
    cfg = {
        "daytime": {
            "hours": "08:00-22:00",
            "priority": ["heat_pump", "pool_pump", "twc"],
        },
        "nighttime": {
            "hours": "22:00-08:00",
            "priority": ["twc", "pool_pump", "heat_pump"],
        },
    }
    scheduler = Scheduler(cfg)
    assert scheduler.get_priority_at(dt_time(23, 0)) == ["twc", "pool_pump", "heat_pump"]


def test_overnight_window():
    cfg = {"night": {"hours": "22:00-06:00", "priority": ["twc"]}}
    scheduler = Scheduler(cfg)
    assert scheduler.get_priority_at(dt_time(2, 0)) == ["twc"]


def test_no_matching_window():
    cfg = {"morning": {"hours": "06:00-12:00", "priority": ["twc"]}}
    scheduler = Scheduler(cfg)
    assert scheduler.get_priority_at(dt_time(15, 0)) == []
