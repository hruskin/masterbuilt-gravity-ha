<img src="https://raw.githubusercontent.com/hruskin/masterbuilt-gravity-ha/main/icon.png" alt="icon" width="96" align="right">

# Masterbuilt Gravity (Unofficial) – Home Assistant integration

Unofficial Home Assistant integration for **Masterbuilt Gravity Series** charcoal
grills + smokers (560 / 800 / 1050). It reads live state from the Masterbuilt /
Middleby cloud (the same backend the official mobile app uses) and exposes it as
Home Assistant entities.

> ⚠️ **Use at your own risk.** This is an unofficial, reverse-engineered project.
> It is **not** affiliated with, endorsed by, or supported by Masterbuilt or
> Middleby. It may stop working at any time if the vendor changes their API or
> rotates the embedded keys, and it could break without notice. No warranty of
> any kind – see [LICENSE](LICENSE).

## Features (v0.5.0 – read **and** control)

Per paired grill:

- **Thermostat** (`climate`) – set the chamber target temperature, and power the
  grill on/off. Bounds come from the grill itself (`heat.t2.min`/`max`; 150–700 °F
  on the XT).
- **Cloud connected** (diagnostic binary sensor) – see *Staleness* below.

- **Grill temperature** (`mainTemp`) and **target temperature** (`heat.t2.trgt`)
- **Probes 1–4** – temperature and target (appear only when a probe is plugged in)
- **Power**, **cooking**, **hopper door**, **lid** (binary sensors)
- **Problem** + **Error** – e.g. *Charcoal failed to ignite* (code 4); raw error
  codes exposed as attributes
- **Target reached** (binary sensor, derived from `mainTemp ≥ target`)
- **Heat intensity**, **signal strength** (RSSI), firmware version

Units (°C/°F) follow the grill's own setting (`fah`). State is available even when
the grill is offline (the cloud keeps the last reported state).

### How control works

The CAS REST API is **read-only** – its only shadow route is a `GET`. The official
app performs all control by publishing a *desired* shadow document over **AWS IoT
MQTT**, so this integration does the same (`mqtt_control.py`):

```
{"state": {"desired": {"heat": {"t2": {"heating": true, "trgt": 250}}}}}
   -> $aws/things/{thingName}/shadow/update
```

On first use it mints an AWS IoT certificate and caches it under
`.storage/masterbuilt_gravity_iot/`; subsequent commands reuse it. This adds
`awsiotsdk`, `boto3` and `pycognito` as requirements.

> **Note on embedded credentials.** Certificate minting uses a *shared service
> account* embedded in the official app (not your account), and the policy-attach
> endpoint is unauthenticated. These are **not** shipped in this repository: you
> enter them once in the config flow and Home Assistant stores them in the config
> entry (see [Obtaining the app control credentials](#obtaining-the-app-control-credentials)).
> That is workable for personal use with a grill you own, but redistributing those
> values is a different matter from reverse-engineering for interoperability, and
> likely conflicts with the app's terms of service.

### Staleness: the failure mode to know about

If the grill drops its cloud session, the shadow keeps serving its **last** reported
document indefinitely – every sensor silently freezes at old values and no command
can take effect, even though writes are still accepted by AWS. The new **Cloud
connected** binary sensor detects this from the shadow's metadata timestamps
(`seconds_since_report` attribute); it goes `off` after 3 minutes of silence.

Observed trigger: **pairing over BLE appears to displace the Wi-Fi/cloud session** –
the shadow flag is literally named `IS_BLE_OR_WIFI_ENGAGED`. **Power-cycling the
grill restores it.** Treat local-BLE tooling and cloud control as alternatives, not
complements.

## Installation

**Manual:** copy `custom_components/masterbuilt_gravity` into
`config/custom_components/` on your Home Assistant instance and restart.

**HACS:** add this repository as a custom integration repository.

Then: *Settings → Devices & Services → Add Integration → Masterbuilt Gravity* and
sign in with the same email/password you use in the mobile app.

The setup form also has three **optional** fields — *App control username /
password / client secret*. Leave them blank for a **read-only** (sensors only)
install; fill them in to enable **grill control**. They are stored in Home
Assistant's config entry, never in this repository. See below for where to get
them.

### Obtaining the app control credentials

These three values are the *shared service account* the official app uses to mint
its AWS IoT certificate — they are the same for every install, not your personal
account. They are not distributed here; extract them yourself from the official
Android app (v1.0.41) if you want control:

1. Get the APK/XAPK (e.g. from APKPure) and decompile it — [`jadx`](https://github.com/skylot/jadx)
   works well: `jadx -d out Masterbuilt.apk`.
2. **App client secret** → `res/raw/awsconfiguration.json`, field
   `CognitoUserPool.Default.AppClientSecret`. (The same file also confirms the
   non-secret ids already baked into `const.py`: `AppClientId`, user-pool and
   identity-pool ids.)
3. **Username and password** → the single hardcoded `AWSMobileClient.signIn(...)`
   call. Search the decompiled sources for `signIn(` or for `weareenvoy` — the
   two string literals passed to it are the username and password.

Paste those into the corresponding config-flow fields. Nothing else is needed;
the certificate is minted on first control command and cached under
`.storage/masterbuilt_gravity_iot/`.

> Existing installs created before this change, and read-only installs, simply
> leave the fields blank — sensors keep working. If you try to control the grill
> without them, the command fails with a message telling you to add them (delete
> and re-add the integration to bring the form back up).

## How it works

1. `POST cas.masterbuilt.com/api/v1/auth/login` (Basic app key + email/password) → JWT
2. `GET /api/v1/paired-device` → list of grills (Bearer)
3. `GET /api/v1/paired-device/{mac}/shadows/current?thing_name=<md5>` → telemetry

`thing_name = md5( lower(mac[4:]) + ".Kavry9-vaqsar-wirtok" )`

## Roadmap

- ~~control via local **BLE + ESP32**~~ — **not possible.** Static analysis of the
  official app (v1.0.41) shows BLE carries *no* control commands at all: it is used
  only for scanning, pairing, Wi-Fi provisioning and telemetry. Every device command
  (temperature, power, timer, probe targets) has exactly one encoder, the AWS IoT
  payload mapper, and `SendCommandUseCase` refuses to send unless MQTT is connected.
  Control is therefore cloud-only, and is implemented in v0.5.0 over MQTT.
- Meat probe target temperatures (the MQTT payload is known and implemented in
  `mqtt_control.async_set_probe_target`; needs `number` entities to expose it)
- Cook timers (`timers.up` / `timers.dwn`)
- Optional high/low temperature alarm thresholds

## License

MIT – see [LICENSE](LICENSE).

---

## Česky

Neoficiální integrace pro grily **Masterbuilt Gravity Series** (560/800/1050).
Čte živý stav z cloudu Masterbuilt/Middleby (stejný backend jako oficiální appka)
a vystavuje ho v Home Assistantu.

> ⚠️ **Použití na vlastní riziko.** Neoficiální, reverzně-inženýrský projekt, **bez**
> jakékoli vazby na Masterbuilt/Middleby. Může kdykoli přestat fungovat (změna API
> nebo rotace klíčů). Bez záruky – viz [LICENSE](LICENSE).

**Co umí (v0.2.0, jen čtení):** teplota grilu a cílová teplota, sondy 1–4,
napájení/vaření/dvířka/víko, **Problém** + **Chyba** (např. *roztopení selhalo*),
**cílová teplota dosažena**, intenzita ohřevu, RSSI, verze firmwaru. Jednotka dle
nastavení grilu, funguje i offline. Ovládání zatím není (plán: lokálně přes
BLE + ESP32).

**Instalace:** zkopíruj `custom_components/masterbuilt_gravity` do
`config/custom_components/` a restartuj HA (nebo přidej repo do HACS jako vlastní).
Pak *Nastavení → Zařízení a služby → Přidat integraci → Masterbuilt Gravity* a
přihlas se účtem z appky.
