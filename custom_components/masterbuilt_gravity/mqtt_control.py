"""AWS IoT MQTT control path for Masterbuilt Gravity.

The CAS REST API is read-only: its only shadow route is a GET, and the official app
performs *all* device control by publishing a desired shadow document over AWS IoT
MQTT. This module reproduces that path.

Bootstrap (mirrors the app):

    Cognito user-pool sign-in (shared service account, SRP)
      -> Cognito identity-pool AWS credentials
      -> IoT CreateKeysAndCertificate            (cached on disk; minted once)
      -> POST aws/policy                          (unauthenticated) to attach a policy
      -> MQTT connect (mutual TLS) -> publish $aws/things/{thing}/shadow/update

Everything here is blocking (boto3 / pycognito / awscrt), so every entry point hops to
an executor thread. A lock serialises publishes so concurrent entity calls cannot
interleave connections using the same MQTT client id.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Any

from homeassistant.core import HomeAssistant

from .api import thing_name
from .const import (
    COGNITO_CLIENT_ID,
    COGNITO_IDENTITY_POOL_ID,
    COGNITO_REGION,
    COGNITO_USER_POOL_ID,
    IOT_ENDPOINT,
    POLICY_URL,
)

_LOGGER = logging.getLogger(__name__)

MQTT_TIMEOUT = 20.0


class MasterbuiltControlError(Exception):
    """Raised when a control command could not be delivered."""


def _client_id(device_id: str) -> str:
    """Stable per-device MQTT client id.

    Must equal the ``client_device_id`` sent to the policy endpoint: AWS IoT policies
    gate ``iot:Connect`` on the client id, so a mismatch is refused at connect time.
    """
    return "mbha-" + hashlib.sha1(device_id.encode()).hexdigest()[:16]


class MasterbuiltMqttControl:
    """Publishes desired shadow documents for one account's grills."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage_dir: str,
        *,
        cognito_username: str | None,
        cognito_password: str | None,
        cognito_client_secret: str | None,
    ) -> None:
        self._hass = hass
        self._dir = storage_dir
        self._lock = asyncio.Lock()
        # Shared service-account credentials, supplied via the config flow (not
        # stored in source). None/blank means control is unconfigured - reads
        # still work, but any command raises a clear error at mint time.
        self._cognito_username = cognito_username
        self._cognito_password = cognito_password
        self._cognito_client_secret = cognito_client_secret

    # ---------------------------------------------------------------- public API

    async def async_set_target_temperature(self, device_id: str, temp: int) -> None:
        """Set the chamber setpoint (in the grill's own unit)."""
        await self.async_publish_desired(
            device_id, {"heat": {"t2": {"heating": True, "trgt": temp}}}
        )

    async def async_set_power(self, device_id: str, on: bool) -> None:
        """Turn the grill on or off."""
        await self.async_publish_desired(device_id, {"pwrOn": on})

    async def async_set_probe_target(
        self, device_id: str, position: int, temp: int
    ) -> None:
        """Set a meat probe target temperature."""
        await self.async_publish_desired(
            device_id, {"probes": {f"p{position}": {"trgt": temp}}}
        )

    async def async_set_timer(
        self, device_id: str, minutes: int, count_down: bool = True
    ) -> None:
        """Set a cook timer.

        ``trgt`` is in MINUTES: the app reads ``time_set_in_minutes`` from its picker
        and passes that value through unchanged, which also matches the ``minutes_set``
        field in the BLE telemetry frames.
        """
        key = "dwn" if count_down else "up"
        await self.async_publish_desired(
            device_id, {"timers": {key: {"trgt": minutes, "paused": False}}}
        )

    async def async_publish_desired(self, device_id: str, desired: dict[str, Any]) -> None:
        """Publish a ``desired`` shadow fragment and wait for accept/reject."""
        payload = {"state": {"desired": desired}}
        async with self._lock:
            await self._hass.async_add_executor_job(
                self._blocking_publish, device_id, payload
            )

    # ------------------------------------------------------------- blocking impl

    def _blocking_publish(self, device_id: str, payload: dict[str, Any]) -> None:
        """Connect, publish, confirm, disconnect. Runs in an executor thread."""
        from concurrent.futures import Future

        from awscrt import mqtt
        from awsiot import mqtt_connection_builder

        pem, key = self._ensure_certificate(device_id)
        thing = thing_name(device_id)
        base = f"$aws/things/{thing}/shadow/update"

        conn = mqtt_connection_builder.mtls_from_path(
            endpoint=IOT_ENDPOINT,
            cert_filepath=pem,
            pri_key_filepath=key,
            client_id=_client_id(device_id),
            clean_session=True,
            keep_alive_secs=30,
        )
        try:
            conn.connect().result(timeout=MQTT_TIMEOUT)
        except Exception as err:  # noqa: BLE001 - surfaced to the caller
            raise MasterbuiltControlError(f"MQTT connect failed: {err}") from err

        reply: Future = Future()

        def _on_msg(topic: str, payload: bytes, **_: Any) -> None:
            if not reply.done():
                reply.set_result((topic, payload))

        try:
            for suffix in ("accepted", "rejected"):
                conn.subscribe(
                    f"{base}/{suffix}", mqtt.QoS.AT_LEAST_ONCE, _on_msg
                )[0].result(timeout=MQTT_TIMEOUT)

            conn.publish(
                topic=base,
                payload=json.dumps(payload),
                qos=mqtt.QoS.AT_LEAST_ONCE,
            )[0].result(timeout=MQTT_TIMEOUT)

            try:
                topic, raw = reply.result(timeout=MQTT_TIMEOUT)
            except Exception as err:  # noqa: BLE001
                raise MasterbuiltControlError(
                    "no accepted/rejected reply from the shadow service"
                ) from err

            if topic.endswith("/rejected"):
                raise MasterbuiltControlError(
                    f"shadow update rejected: {raw.decode(errors='replace')[:200]}"
                )
            _LOGGER.debug("Shadow update accepted for %s: %s", device_id, payload)
        finally:
            try:
                conn.disconnect().result(timeout=10)
            except Exception:  # noqa: BLE001 - best effort teardown
                _LOGGER.debug("MQTT disconnect failed", exc_info=True)

    def _ensure_certificate(self, device_id: str) -> tuple[str, str]:
        """Return (cert_pem_path, private_key_path), minting them once if needed."""
        os.makedirs(self._dir, mode=0o700, exist_ok=True)
        pem = os.path.join(self._dir, f"{device_id}.cert.pem")
        key = os.path.join(self._dir, f"{device_id}.private.key")
        arn_file = os.path.join(self._dir, f"{device_id}.arn")

        if all(os.path.exists(p) for p in (pem, key, arn_file)):
            return pem, key

        _LOGGER.info("Minting AWS IoT certificate for %s (first run only)", device_id)
        creds = self._cognito_credentials()

        import boto3

        iot = boto3.client("iot", region_name=COGNITO_REGION, **creds)
        res = iot.create_keys_and_certificate(setAsActive=True)

        with open(pem, "w", encoding="utf-8") as fh:
            fh.write(res["certificatePem"])
        with open(key, "w", encoding="utf-8") as fh:
            fh.write(res["keyPair"]["PrivateKey"])
        os.chmod(key, 0o600)
        with open(arn_file, "w", encoding="utf-8") as fh:
            fh.write(res["certificateArn"])

        self._attach_policy(device_id, res["certificateArn"])
        return pem, key

    def _cognito_credentials(self) -> dict[str, str]:
        """SRP sign-in on the shared account, federated to identity-pool AWS creds."""
        if not all(
            (self._cognito_username, self._cognito_password, self._cognito_client_secret)
        ):
            raise MasterbuiltControlError(
                "AWS IoT control credentials are not configured. Add the Cognito "
                "username, password, and app-client secret to this integration "
                "(delete and re-add it, or use Reconfigure). See the README for how "
                "to obtain them from the official app."
            )

        import boto3
        from pycognito import Cognito

        user = Cognito(
            COGNITO_USER_POOL_ID,
            COGNITO_CLIENT_ID,
            client_secret=self._cognito_client_secret,
            username=self._cognito_username,
            user_pool_region=COGNITO_REGION,
        )
        # USER_PASSWORD_AUTH is disabled on this app client; pycognito uses SRP.
        user.authenticate(password=self._cognito_password)

        provider = f"cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
        logins = {provider: user.id_token}
        ident = boto3.client("cognito-identity", region_name=COGNITO_REGION)
        identity_id = ident.get_id(
            IdentityPoolId=COGNITO_IDENTITY_POOL_ID, Logins=logins
        )["IdentityId"]
        creds = ident.get_credentials_for_identity(
            IdentityId=identity_id, Logins=logins
        )["Credentials"]
        return {
            "aws_access_key_id": creds["AccessKeyId"],
            "aws_secret_access_key": creds["SecretKey"],
            "aws_session_token": creds["SessionToken"],
        }

    def _attach_policy(self, device_id: str, cert_arn: str) -> None:
        """Bind an IoT policy to the new certificate (unauthenticated endpoint)."""
        import requests

        resp = requests.post(
            POLICY_URL,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json={
                "aws_iot_thing_name": thing_name(device_id),
                "aws_iot_certificate_arn": cert_arn,
                "client_device_id": _client_id(device_id),
            },
            timeout=30,
        )
        if resp.status_code >= 300:
            raise MasterbuiltControlError(
                f"policy attach failed ({resp.status_code}): {resp.text[:200]}"
            )
        _LOGGER.debug("Attached IoT policy for %s", device_id)
