"""Main entry point for loadctl."""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from typing import Any

from loadctl import __version__
from loadctl.config import load_config, Config
from loadctl.homebridge import HomebridgeClient
from loadctl.load import Load, LoadState, LoadType, build_loads_from_config
from loadctl.mqtt_client import LoadMQTT
from loadctl.phase_monitor import PhaseMonitor
from loadctl.scheduler import Scheduler
from loadctl.shedding import SheddingEngine

logger = logging.getLogger("loadctl")

LOOP_INTERVAL = 5.0
STALE_TIMEOUT = 15.0

_shutdown = False


def _setup_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _update_phase_monitor(monitor: PhaseMonitor, mqtt: LoadMQTT) -> None:
    """Push latest MQTT power data into the phase monitor."""
    key_to_phase = {
        "power_phase1": (1, "power"),
        "power_phase2": (2, "power"),
        "power_phase3": (3, "power"),
        "voltage_phase1": (1, "voltage"),
        "voltage_phase2": (2, "voltage"),
        "voltage_phase3": (3, "voltage"),
    }
    for key, (phase, kind) in key_to_phase.items():
        value = mqtt.power_data.get(key)
        if value is not None:
            if kind == "power":
                monitor.update_power(phase, value)
            else:
                monitor.update_voltage(phase, value)


def _execute_action(
    action: dict[str, Any],
    loads: dict[str, Load],
    mqtt: LoadMQTT,
    homebridge: HomebridgeClient,
) -> None:
    """Execute a shed/reduce/restore action on a load."""
    load_name = action["load"]
    act = action["action"]
    load = loads.get(load_name)
    if load is None:
        logger.warning("Unknown load in action: %s", load_name)
        return

    if act == "shed":
        load.shed()
        if load.load_type == LoadType.HOMEBRIDGE and load.homebridge_accessory:
            try:
                homebridge.set_accessory(load.homebridge_accessory, False)
            except Exception:
                logger.exception("Failed to shed %s via Homebridge", load_name)
        elif load.load_type == LoadType.CHARGECTL and load.mqtt_topic:
            mqtt.publish(load.mqtt_topic, "0")
        logger.info("SHED %s", load_name)

    elif act == "reduce":
        target_amps = action.get("amps", load.min_amps)
        load.current_amps = target_amps
        if load.load_type == LoadType.CHARGECTL and load.mqtt_topic:
            mqtt.publish(load.mqtt_topic, str(int(target_amps)))
        logger.info("REDUCE %s to %dA", load_name, target_amps)

    elif act == "restore":
        load.restore()
        if load.load_type == LoadType.HOMEBRIDGE and load.homebridge_accessory:
            try:
                homebridge.set_accessory(load.homebridge_accessory, True)
            except Exception:
                logger.exception("Failed to restore %s via Homebridge", load_name)
        elif load.load_type == LoadType.CHARGECTL and load.mqtt_topic:
            mqtt.publish(load.mqtt_topic, str(int(load.current_amps)))
        logger.info("RESTORE %s", load_name)

    mqtt.publish_load_state(load_name, {
        "state": load.state.value,
        "current_amps": load.current_amps,
    })


def _publish_status(
    mqtt: LoadMQTT,
    monitor: PhaseMonitor,
    loads: dict[str, Load],
    priority: list[str],
) -> None:
    """Publish overall system status via MQTT."""
    phase_data = {}
    for phase in (1, 2, 3):
        amps = monitor.get_phase_amps(phase)
        free = monitor.get_free_amps(phase)
        phase_data[str(phase)] = {
            "amps": round(amps, 2) if amps is not None else None,
            "free_amps": round(free, 2) if free is not None else None,
        }
    load_data = {}
    for name, load in loads.items():
        load_data[name] = {
            "state": load.state.value,
            "current_amps": load.current_amps,
        }
    mqtt.publish_status({
        "phases": phase_data,
        "loads": load_data,
        "priority": priority,
        "stale": monitor.is_stale(STALE_TIMEOUT),
    })


def run_loop(
    mqtt: LoadMQTT,
    homebridge: HomebridgeClient,
    monitor: PhaseMonitor,
    scheduler: Scheduler,
    engine: SheddingEngine,
    loads: dict[str, Load],
) -> None:
    """Main control loop — runs until shutdown signal."""
    global _shutdown
    logger.info("Control loop started")
    while not _shutdown:
        _update_phase_monitor(monitor, mqtt)
        priority = scheduler.get_priority()
        free_amps = monitor.get_all_free_amps()

        # Watchdog: if data is stale, shed everything
        if monitor.is_stale(STALE_TIMEOUT):
            logger.warning("Power data stale — shedding all loads")
            for name, load in loads.items():
                if load.state != LoadState.SHED:
                    _execute_action({"load": name, "action": "shed"}, loads, mqtt, homebridge)
        else:
            actions = engine.evaluate(loads, priority, free_amps)
            for action in actions:
                _execute_action(action, loads, mqtt, homebridge)

        _publish_status(mqtt, monitor, loads, priority)
        time.sleep(LOOP_INTERVAL)

    logger.info("Control loop stopped")


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Received signal %s, shutting down", signum)
    _shutdown = True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="loadctl — phase-aware energy management")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--version", action="version", version=f"loadctl {__version__}")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    _setup_logging(config.log_level)

    logger.info("loadctl %s starting", __version__)

    mqtt = LoadMQTT(config)
    homebridge = HomebridgeClient(config.homebridge_url, config.homebridge_username, config.homebridge_password)
    monitor = PhaseMonitor(config.max_amps_per_phase, config.margin_amps)
    scheduler = Scheduler(config.schedule)
    engine = SheddingEngine()
    loads = build_loads_from_config(config.loads)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    run_loop(mqtt, homebridge, monitor, scheduler, engine, loads)
    mqtt.disconnect()
    logger.info("loadctl stopped")


if __name__ == "__main__":
    main()
