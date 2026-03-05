"""Per-phase power monitoring."""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class PhaseMonitor:
    def __init__(self, max_amps: int, margin_amps: int):
        self.max_amps = max_amps
        self.margin_amps = margin_amps
        self._power: dict[int, float] = {}
        self._voltage: dict[int, float] = {}
        self._last_update = 0.0

    def update_power(self, phase: int, watts: float) -> None:
        self._power[phase] = watts
        self._last_update = time.time()

    def update_voltage(self, phase: int, volts: float) -> None:
        self._voltage[phase] = volts
        self._last_update = time.time()

    def get_phase_amps(self, phase: int) -> float | None:
        power = self._power.get(phase)
        voltage = self._voltage.get(phase)
        if power is None or voltage is None or voltage == 0:
            return None
        return power / voltage

    def get_free_amps(self, phase: int) -> float | None:
        amps = self.get_phase_amps(phase)
        if amps is None:
            return None
        return self.max_amps - amps - self.margin_amps

    def get_all_free_amps(self) -> dict[int, float]:
        result = {}
        for phase in set(self._power.keys()) | set(self._voltage.keys()):
            free = self.get_free_amps(phase)
            if free is not None:
                result[phase] = free
        return result

    def get_worst_phase(self) -> tuple[int | None, float | None]:
        free_amps = self.get_all_free_amps()
        if not free_amps:
            return None, None
        worst = min(free_amps, key=free_amps.get)
        return worst, free_amps[worst]

    def is_stale(self, timeout: float = 15.0) -> bool:
        if self._last_update == 0:
            return True
        return (time.time() - self._last_update) > timeout
