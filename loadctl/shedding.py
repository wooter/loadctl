"""Shedding and restore algorithm."""
from __future__ import annotations
import logging, time
from loadctl.load import Load, LoadState, LoadType

logger = logging.getLogger(__name__)
RESTORE_COOLDOWN = 60

class SheddingEngine:
    def __init__(self):
        self.last_restore_time = 0.0

    def evaluate(self, loads: dict[str, Load], priority: list[str], free_amps: dict[int, float]) -> list[dict]:
        actions = []
        working_free = dict(free_amps)

        # Shedding: for each overloaded phase
        for phase, free in sorted(free_amps.items()):
            if free >= 0:
                continue
            deficit = abs(free)
            phase_loads = [
                name for name in reversed(priority)
                if name in loads and loads[name].is_on_phase(phase) and loads[name].state != LoadState.SHED
            ]
            for load_name in phase_loads:
                if deficit <= 0:
                    break
                load = loads[load_name]
                if load.load_type == LoadType.CHARGECTL and load.current_amps > load.min_amps:
                    can_free = load.current_amps - load.min_amps
                    reduce_by = min(can_free, deficit)
                    if reduce_by > 0:
                        actions.append({"load": load_name, "action": "reduce", "amps": load.current_amps - int(reduce_by)})
                        deficit -= reduce_by
                        for p in load.phases:
                            working_free[p] = working_free.get(p, 0) + reduce_by
                        continue
                actions.append({"load": load_name, "action": "shed"})
                for p in load.phases:
                    working_free[p] = working_free.get(p, 0) + load.estimated_amps
                deficit -= load.estimated_amps
                for dep_name, dep_load in loads.items():
                    if load_name in dep_load.depends_on and dep_load.state != LoadState.SHED:
                        actions.append({"load": dep_name, "action": "shed"})
                        for p in dep_load.phases:
                            working_free[p] = working_free.get(p, 0) + dep_load.estimated_amps

        # Restoring
        if all(f >= 0 for f in working_free.values()):
            now = time.time()
            if now - self.last_restore_time >= RESTORE_COOLDOWN:
                for load_name in priority:
                    if load_name not in loads:
                        continue
                    load = loads[load_name]
                    if load.state != LoadState.SHED:
                        continue
                    deps_ok = all(loads[dep].state != LoadState.SHED for dep in load.depends_on if dep in loads)
                    if not deps_ok:
                        continue
                    fits = all(working_free.get(p, 0) >= load.estimated_amps for p in load.phases)
                    if fits:
                        actions.append({"load": load_name, "action": "restore"})
                        self.last_restore_time = now
                        break
        return actions
