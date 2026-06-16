# Masterbuilt Gravity – Home Assistant integrace

Neoficiální integrace pro grily **Masterbuilt Gravity Series** (560/800/1050).
Čte stav z cloudu Masterbuilt/Middleby (stejný backend, jako používá oficiální
mobilní aplikace) a vystavuje ho v Home Assistantu.

> Reverz-engineered z oficiální aplikace. Není to oficiální produkt Masterbuiltu.
> Funguje, dokud Middleby nezmění API nebo nerotuje zabudované klíče.

## Co umí (v0.1.0 – jen čtení)

Pro každý spárovaný gril:

- **Teplota grilu** (`mainTemp`) a **cílová teplota** (`heat.t2.trgt`)
- **Sondy 1–4** – teplota a cíl (objeví se, jen když jsou připojené)
- **Napájení**, **vaření**, **dvířka násypky**, **víko** (binární senzory)
- **Intenzita ohřevu**, **síla signálu** (RSSI), verze firmwaru

Jednotka (°C/°F) se přebírá z nastavení grilu (`fah`). Stav se čte i když je
gril offline (cloud drží poslední nahlášený stav).

## Instalace

**Ručně:** zkopíruj `custom_components/masterbuilt_gravity` do
`config/custom_components/` ve své HA instanci a restartuj.

**HACS:** přidej tento repozitář jako vlastní (custom) integraci.

Pak: *Nastavení → Zařízení a služby → Přidat integraci → Masterbuilt Gravity*
a přihlas se stejným e-mailem/heslem jako v mobilní aplikaci.

## Jak to funguje

1. `POST cas.masterbuilt.com/api/v1/auth/login` (Basic app-klíč + e-mail/heslo) → JWT
2. `GET /api/v1/paired-device` → seznam grilů (Bearer)
3. `GET /api/v1/paired-device/{mac}/shadows/current?thing_name=<md5>` → telemetrie

`thing_name = md5( lower(mac[4:]) + ".Kavry9-vaqsar-wirtok" )`

## Plánováno

- **v0.2** – nastavení cílové teploty / zapnutí–vypnutí (zápis do shadow `desired`)
- Případně lokální varianta přes BLE + ESP32 (bez cloudu)

## Licence

MIT
