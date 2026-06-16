"""Thin async client for the Masterbuilt / Middleby CAS cloud API."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import aiohttp

from .const import APP_BASIC, CAS_BASE, THING_SALT

_LOGGER = logging.getLogger(__name__)


class MasterbuiltAuthError(Exception):
    """Raised when login fails (bad credentials)."""


class MasterbuiltApiError(Exception):
    """Raised on other API/transport errors."""


def thing_name(mac_address: str) -> str:
    """Derive the AWS IoT thing name from the API mac address.

    The API mac (e.g. ``424840F520A3CC06``) carries a 2-byte prefix; the thing
    name is md5 of the lowercased remainder plus a fixed salt.
    """
    base = mac_address[4:].lower()
    return hashlib.md5(f"{base}{THING_SALT}".encode()).hexdigest()


class MasterbuiltApi:
    """Handles login, device listing and shadow polling."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None

    async def async_login(self) -> str:
        """Authenticate and cache the bearer token."""
        url = f"{CAS_BASE}/api/v1/auth/login"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": APP_BASIC,
        }
        body = {"username": self._email, "password": self._password}
        try:
            async with self._session.post(url, json=body, headers=headers) as resp:
                if resp.status in (400, 401, 403):
                    raise MasterbuiltAuthError(f"login rejected ({resp.status})")
                if resp.status != 200:
                    raise MasterbuiltApiError(f"login failed ({resp.status})")
                data = await resp.json()
        except aiohttp.ClientError as err:
            raise MasterbuiltApiError(f"login transport error: {err}") from err
        token = data.get("token")
        if not token:
            raise MasterbuiltApiError("login response missing token")
        self._token = token
        return token

    async def _authed_get(self, path: str) -> Any:
        """GET with bearer token, re-authenticating once on 401."""
        if self._token is None:
            await self.async_login()
        for attempt in range(2):
            headers = {"Accept": "application/json", "Authorization": f"Bearer {self._token}"}
            try:
                async with self._session.get(f"{CAS_BASE}{path}", headers=headers) as resp:
                    if resp.status == 401 and attempt == 0:
                        await self.async_login()
                        continue
                    if resp.status != 200:
                        raise MasterbuiltApiError(f"GET {path} -> {resp.status}")
                    return await resp.json()
            except aiohttp.ClientError as err:
                raise MasterbuiltApiError(f"GET {path} transport error: {err}") from err
        raise MasterbuiltApiError(f"GET {path} failed after re-auth")

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Return the list of paired devices (grills)."""
        data = await self._authed_get("/api/v1/paired-device")
        return data if isinstance(data, list) else []

    async def async_get_shadow(self, mac_address: str) -> dict[str, Any]:
        """Return the reported shadow state for a device, or {} if unavailable."""
        path = (
            f"/api/v1/paired-device/{mac_address}/shadows/current"
            f"?thing_name={thing_name(mac_address)}"
        )
        data = await self._authed_get(path)
        return data.get("state", {}).get("reported", {}) or {}
