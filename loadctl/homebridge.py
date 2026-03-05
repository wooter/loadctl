"""Homebridge REST API client."""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


class HomebridgeClient:
    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self._token: str | None = None
        self._accessory_cache: dict[str, dict] = {}

    def login(self) -> None:
        resp = requests.post(
            f"{self.url}/api/auth/login",
            json={"username": self.username, "password": self.password},
            timeout=10,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        logger.info("Homebridge authenticated")

    def get_accessory_state(self, accessory_name: str) -> bool | None:
        self._ensure_token()
        resp = requests.get(f"{self.url}/api/accessories", headers=self._headers(), timeout=10)
        resp.raise_for_status()
        for acc in resp.json():
            if acc.get("serviceName") == accessory_name:
                for char in acc.get("serviceCharacteristics", []):
                    if char.get("type") == "On" or char.get("description") == "On":
                        self._accessory_cache[accessory_name] = {"aid": acc["aid"], "on_iid": char["iid"]}
                        return bool(char.get("value", 0))
        return None

    def set_accessory(self, accessory_name: str, on: bool) -> bool:
        self._ensure_token()
        cached = self._accessory_cache.get(accessory_name)
        if not cached:
            self.get_accessory_state(accessory_name)
            cached = self._accessory_cache.get(accessory_name)
            if not cached:
                logger.warning("Accessory %s not found", accessory_name)
                return False
        resp = requests.put(
            f"{self.url}/api/accessories/{cached['aid']}",
            headers=self._headers(),
            json={"characteristicType": "On", "value": 1 if on else 0},
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
