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

## Features (v0.2.0 – read only)

Per paired grill:

- **Grill temperature** (`mainTemp`) and **target temperature** (`heat.t2.trgt`)
- **Probes 1–4** – temperature and target (appear only when a probe is plugged in)
- **Power**, **cooking**, **hopper door**, **lid** (binary sensors)
- **Problem** + **Error** – e.g. *Charcoal failed to ignite* (code 4); raw error
  codes exposed as attributes
- **Target reached** (binary sensor, derived from `mainTemp ≥ target`)
- **Heat intensity**, **signal strength** (RSSI), firmware version

Units (°C/°F) follow the grill's own setting (`fah`). State is available even when
the grill is offline (the cloud keeps the last reported state).

Control (set temperature, power) is **not** implemented yet – see Roadmap.

## Installation

**Manual:** copy `custom_components/masterbuilt_gravity` into
`config/custom_components/` on your Home Assistant instance and restart.

**HACS:** add this repository as a custom integration repository.

Then: *Settings → Devices & Services → Add Integration → Masterbuilt Gravity* and
sign in with the same email/password you use in the mobile app.

## How it works

1. `POST cas.masterbuilt.com/api/v1/auth/login` (Basic app key + email/password) → JWT
2. `GET /api/v1/paired-device` → list of grills (Bearer)
3. `GET /api/v1/paired-device/{mac}/shadows/current?thing_name=<md5>` → telemetry

`thing_name = md5( lower(mac[4:]) + ".Kavry9-vaqsar-wirtok" )`

## Roadmap

- **v0.3** – control (set target temperature / power) via local **BLE + ESP32**
  (the cloud backend has no write API; the app writes over AWS IoT MQTT)
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
