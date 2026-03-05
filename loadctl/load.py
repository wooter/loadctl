from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LoadType(Enum):
    HOMEBRIDGE = "homebridge"
    CHARGECTL = "chargectl"


class LoadState(Enum):
    ON = "on"
    SHED = "shed"
    OFF = "off"


@dataclass
class Load:
    name: str
    load_type: LoadType
    phases: list[int]
    estimated_amps: float
    state: LoadState = LoadState.ON
    homebridge_accessory: str | None = None
    mqtt_topic: str | None = None
    min_amps: float = 0
    max_amps: float = 0
    current_amps: float = 0
    depends_on: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.load_type == LoadType.CHARGECTL and self.max_amps > 0:
            self.current_amps = self.max_amps

    def is_on_phase(self, phase: int) -> bool:
        return phase in self.phases

    def shed(self) -> None:
        self.state = LoadState.SHED
        if self.load_type == LoadType.CHARGECTL:
            self.current_amps = 0

    def restore(self) -> None:
        self.state = LoadState.ON
        if self.load_type == LoadType.CHARGECTL:
            self.current_amps = self.max_amps

    def reduce_amps(self, amps: float) -> float:
        """Reduce current amps by the requested amount.

        If the reduction would bring current_amps below min_amps,
        the load is shed entirely and all current amps are freed.

        Returns the actual number of amps freed.
        """
        new_amps = self.current_amps - amps
        if new_amps < self.min_amps:
            freed = self.current_amps
            self.shed()
            return freed
        self.current_amps = new_amps
        return amps

    def increase_amps(self, amps: float) -> float:
        """Increase current amps by the requested amount, capped at max_amps.

        Returns the actual number of amps added.
        """
        headroom = self.max_amps - self.current_amps
        added = min(amps, headroom)
        self.current_amps += added
        if self.state == LoadState.SHED and self.current_amps > 0:
            self.state = LoadState.ON
        return added


def build_loads_from_config(config_loads: dict) -> dict[str, Load]:
    """Build Load objects from a configuration dictionary."""
    loads: dict[str, Load] = {}
    for name, cfg in config_loads.items():
        load_type = LoadType(cfg["type"])
        phases = cfg.get("phases") or [cfg["phase"]]
        loads[name] = Load(
            name=name,
            load_type=load_type,
            phases=phases,
            estimated_amps=cfg["estimated_amps"],
            homebridge_accessory=cfg.get("homebridge_accessory"),
            mqtt_topic=cfg.get("mqtt_topic"),
            min_amps=cfg.get("min_amps", 0),
            max_amps=cfg.get("max_amps", 0),
            depends_on=cfg.get("depends_on", []),
        )
    return loads
