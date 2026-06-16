"""Constants for the Masterbuilt Gravity integration."""
from __future__ import annotations

import base64

DOMAIN = "masterbuilt_gravity"

# CAS REST backend (reverse-engineered from the official app v1.0.41)
CAS_BASE = "https://cas.masterbuilt.com"

# App-level key used as HTTP Basic auth for the unauthenticated login endpoint.
_APP_KEY = (
    "XB7RVSq2IfoBO7894f6Vb4OVxlml0PIQBx~e:"
    "aMMIKdZV7UPboDjBus1pf4aOkQZT08miQ5PH85gwW0XjDwML"
)
APP_BASIC = "Basic " + base64.b64encode(_APP_KEY.encode()).decode()

# thingName = md5( lower(macAddress[4:]) + THING_SALT )
THING_SALT = ".Kavry9-vaqsar-wirtok"

# Target temperature sentinel meaning "not set / off" (0 F == ~-17 C).
TARGET_OFF = -17

DEFAULT_SCAN_INTERVAL = 30  # seconds

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
