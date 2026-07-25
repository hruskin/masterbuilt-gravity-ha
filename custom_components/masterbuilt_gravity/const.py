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

# ---------------------------------------------------------------------------
# AWS IoT control path (write). CAS REST is read-only - its only shadow route is
# a GET - so all control goes over AWS IoT MQTT, exactly as the official app does.
#
# The shared service-account credentials that mint the IoT certificate - the
# Cognito username, password, and app-client secret - are deliberately NOT stored
# in source. They are collected in the config flow and kept in Home Assistant's
# config entry (see CONF_COGNITO_* below and the README for how to obtain them
# from the official app). The values that remain here are identifiers and
# endpoints, not credentials: they ship in cleartext in every install and
# authenticate nothing on their own.
# ---------------------------------------------------------------------------
IOT_ENDPOINT = "a386xm06thrxxr-ats.iot.us-east-2.amazonaws.com"
COGNITO_REGION = "us-east-2"

COGNITO_USER_POOL_ID = "us-east-2_91Wt2hzCz"
COGNITO_IDENTITY_POOL_ID = "us-east-2:ff94e741-672e-4b13-86a4-78b9e89614bf"
COGNITO_CLIENT_ID = "1s3lnige0e77ojajdfn9pnsso4"

# Policy attach lives on a separate Elastic Beanstalk host, plain HTTP, no auth.
POLICY_URL = (
    "http://masterbuiltaws-production.6k9fbw6cvt.us-west-2.elasticbeanstalk.com/aws/policy"
)

# Subdirectory under HA's .storage for the minted IoT certificate/key.
IOT_STORAGE_DIR = "masterbuilt_gravity_iot"

# Chamber setpoint bounds. The grill reports its own limits in
# heat.t2.{min,max}; these are the observed XT defaults used as a fallback.
DEFAULT_MIN_TEMP_F = 150
DEFAULT_MAX_TEMP_F = 700

# Meat probe target bounds. Unlike the chamber, the shadow's probe entries carry
# only {temp, trgt} - no min/max - so these are sensible food-safe ranges rather
# than device-reported limits.
PROBE_MIN_F = 32
PROBE_MAX_F = 572
PROBE_MIN_C = 0
PROBE_MAX_C = 300

# Cook timer ceiling (minutes). `timers.dwn.trgt` is in MINUTES: the app reads
# "time_set_in_minutes" from its picker and sends it unchanged, matching the
# minutes_set field in the BLE telemetry frames.
TIMER_MAX_MINUTES = 1440  # 24 h

# A shadow whose newest reported timestamp is older than this means the grill has
# dropped its cloud session: `reported` is a stale snapshot and no command can be
# applied. Observed cause: BLE pairing appears to displace the Wi-Fi/cloud session
# (the shadow flag is literally named IS_BLE_OR_WIFI_ENGAGED). A power-cycle of the
# grill restores it.
STALE_AFTER_SECONDS = 180

# Target temperature sentinel meaning "not set / off" (0 F == ~-17 C).
TARGET_OFF = -17

# The grill/app fire their "reached" notification a few degrees below the
# setpoint (observed ~2 C; the exact offset isn't cleanly exposed). Applied to
# both grill and probe "at temperature" detection. Tune here if needed.
REACHED_TOLERANCE_C = 3
REACHED_TOLERANCE_F = 5


def _reached(current: float, target: float, fah: bool | None) -> bool:
    tol = REACHED_TOLERANCE_F if fah else REACHED_TOLERANCE_C
    return current >= target - tol

DEFAULT_SCAN_INTERVAL = 30  # seconds

CONF_EMAIL = "email"
CONF_PASSWORD = "password"

# Shared app "bootstrap" credentials for the AWS IoT control path. Entered in the
# config flow and stored in the HA config entry, never committed to source. The
# control path (mqtt_control.py) needs all three to mint an IoT certificate; leave
# them blank for a read-only (sensors only) setup. See the README for how to
# extract them from the official app.
CONF_COGNITO_USERNAME = "cognito_username"
CONF_COGNITO_PASSWORD = "cognito_password"
CONF_COGNITO_CLIENT_SECRET = "cognito_client_secret"

# Reported "errors" is a fixed-size list of error codes (0 == no error in that
# slot). Known code -> human text. Some texts are server-defined; extend as we
# observe more codes.
KNOWN_ERRORS: dict[int, str] = {
    4: "Charcoal failed to ignite",
}


def active_errors(reported: dict) -> list[int]:
    """Return the list of non-zero error codes currently reported."""
    return [c for c in (reported.get("errors") or []) if c]


def error_text(reported: dict) -> str:
    """Human-readable error summary, or 'OK' when no error is active."""
    active = active_errors(reported)
    if not active:
        return "OK"
    return ", ".join(KNOWN_ERRORS.get(c, f"Error {c}") for c in active)


def probe_present(reported: dict, n: int) -> bool:
    """True when meat probe ``n`` is currently plugged in."""
    return f"p{n}" in (reported.get("probes") or {})


def probe_reached(reported: dict, n: int) -> bool:
    """True when probe ``n`` has a target set and has reached it (with offset)."""
    p = (reported.get("probes") or {}).get(f"p{n}") or {}
    trgt, temp = p.get("trgt"), p.get("temp")
    if not trgt or temp is None:  # trgt 0/None == no target set
        return False
    return _reached(temp, trgt, reported.get("fah"))


def target_reached(reported: dict) -> bool:
    """Approximate 'at temperature': powered, valid setpoint, temp within tolerance.

    The reported shadow has no explicit "reached" flag and the grill fires its
    push notification a couple of degrees below the setpoint, so a small
    tolerance is applied. Note: ``engaged`` is NOT cooking – it is false once the
    grill settles at temperature – so it must not gate this.
    """
    trgt = (reported.get("heat") or {}).get("t2", {}).get("trgt")
    main = reported.get("mainTemp")
    if not reported.get("pwrOn") or main is None or trgt is None or trgt <= 0:
        return False
    return _reached(main, trgt, reported.get("fah"))
