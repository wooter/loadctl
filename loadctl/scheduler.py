"""Time-based schedule for load priorities."""
from __future__ import annotations

import logging
from datetime import datetime, time as dt_time

logger = logging.getLogger(__name__)


class TimeWindow:
    def __init__(self, name: str, start: dt_time, end: dt_time, priority: list[str]):
        self.name = name
        self.start = start
        self.end = end
        self.priority = priority

    def contains(self, t: dt_time) -> bool:
        if self.start <= self.end:
            return self.start <= t < self.end
        else:
            return t >= self.start or t < self.end


class Scheduler:
    def __init__(self, schedule_config: dict):
        self.windows: list[TimeWindow] = []
        for name, cfg in schedule_config.items():
            start_str, end_str = cfg["hours"].split("-")
            start = dt_time(*map(int, start_str.split(":")))
            end = dt_time(*map(int, end_str.split(":")))
            self.windows.append(TimeWindow(name, start, end, cfg["priority"]))

    def get_priority(self) -> list[str]:
        return self.get_priority_at(datetime.now().time())

    def get_priority_at(self, t: dt_time) -> list[str]:
        for window in self.windows:
            if window.contains(t):
                return window.priority
        return []
