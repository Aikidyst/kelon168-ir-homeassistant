# KELON168 IR → Home Assistant

Control your **Kelon / Electra / Tadiran** air conditioner from Home Assistant using a cheap Tuya IR blaster — no cloud, fully local.

This project contains a fully reverse-engineered implementation of the **KELON168** IR protocol, a Home Assistant climate entity, and a script that dynamically generates IR codes without pre-recording hundreds of remote captures.

---

## Does this work for my AC?

If your AC remote looks like one of these, this likely works for you:

| Brand | Country | Remote model |
|-------|---------|-------------|
| Electra | Israel | Various |
| Tadiran | Israel | Various |
| Kelon | Global | DG11R2-01, RCH-R0Y3 |
| Airwell | Europe | RC-3, RC-4, RC-7 |
| Emailair | Australia | Various |

The KELON168 protocol is used across many OEM AC brands. If your remote sends 168-bit IR signals with `0x83 0x06` as the first two bytes, this is your protocol.

---

## Features

- ✅ Cool / Heat / Dry / Fan Only modes
- ✅ Temperature control (16–30°C)
- ✅ Fan speed (Auto / Low / Medium / High)
- ✅ **I Feel** mode (sends room temperature sensor reading to AC)
- ✅ Reliable **power-on** using Turbo frame trick (see below)
- ✅ Fully local — no cloud, no API keys
- ✅ Works with Tuya IR blasters via LocalTuya RC integration
- ✅ Easy migration to ESPHome IR blaster (one-line change)
- ✅ Dynamic code generation — no pre-recorded lookup tables

---

## Hardware Requirements

| Component | Notes |
|-----------|-------|
| Tuya IR blaster | Any Tuya-compatible IR blaster |
| LocalTuya RC integration | [ClusterM fork](https://github.com/ClusterM/tuya-local) with `remote.send_command` raw support |
| Home Assistant | Tested on 2026.6.0 |
| climate_template | HACS: [litinoveweedle/hass-template-climate](https://github.com/litinoveweedle/hass-template-climate) |

> **Why raw codes?**  
> LocalTuya RC stores learned codes as 42-bit NEC extended — only 25% of the KELON168 signal. The AC ignores truncated frames. Raw `8308,4527,554,...` format sends the complete 343-pulse signal and is the only working approach.

---

## Key Discovery: Power On/Off

The KELON168 protocol has **no absolute power-on command** — the power button is a toggle. This is a known limitation documented by the original protocol author.

**The workaround:** The **TURBO frame** unconditionally turns the AC on regardless of current state. Using turbo as a guaranteed power-on, followed immediately by a normal state frame to set the desired mode/temp/fan, gives reliable power-on from HA.

```
Power ON  = TURBO frame → state frame   ← guaranteed, never toggles off
Power OFF = TURBO frame → power toggle frame  ← guaranteed off
```

---

## Repository Structure

```
kelon168-ir-homeassistant/
├── README.md                          ← this file
├── kelon168.py                        ← IR code generator (Python)
├── climate_template_kelon168.yaml     ← HA climate entity config
└── KELON168_README.md                 ← full protocol specification
```

---

## Quick Start

### 1. Install prerequisites

Install via HACS:
- [LocalTuya RC (ClusterM fork)](https://github.com/ClusterM/tuya-local)
- [climate_template (litinoveweedle fork)](https://github.com/litinoveweedle/hass-template-climate)

### 2. Create helpers

In Home Assistant → Settings → Helpers, create:

| Helper | Type | Options |
|--------|------|---------|
| `input_select.bedroom_ac_hvac_mode` | Dropdown | off, cool, heat, dry, fan_only |
| `input_number.bedroom_ac_target_temperature` | Number | min=16, max=30, step=1 |
| `input_select.bedroom_ac_fan_mode` | Dropdown | auto, low, medium, high |
| `input_boolean.bedroom_ac_i_feel` | Toggle | — |

### 3. Add climate entity

Copy the contents of `climate_template_kelon168.yaml` into your `configuration.yaml`, updating these entity IDs to match your setup:

```yaml
# Update these to match your entities:
sensor.temp_tuya_screen_temperature    # your room temperature sensor
remote.tuya_ir_remote_control          # your Tuya IR blaster entity
```

### 4. Create the script

In HA → Settings → Scripts → Add Script → Edit in YAML, paste the script from the [script section](#script) below, or create it via the HA API.

### 5. Create the I Feel automation

In HA → Settings → Automations, create `automation.bedroom_ac_i_feel_resend`:

```yaml
alias: "Bedroom AC - I Feel Resend"
trigger:
  - platform: state
    entity_id: input_boolean.bedroom_ac_i_feel
condition:
  - condition: not
    conditions:
      - condition: state
        entity_id: input_select.bedroom_ac_hvac_mode
        state: "off"
action:
  - service: script.bedroom_ac_ir_send
    data:
      ac_action: state
      ac_mode:   "{{ states('input_select.bedroom_ac_hvac_mode') }}"
      ac_temp:   "{{ states('input_number.bedroom_ac_target_temperature') | int(22) }}"
      ac_fan:    "{{ states('input_select.bedroom_ac_fan_mode') }}"
      ac_ifeel:  "{{ is_state('input_boolean.bedroom_ac_i_feel', 'on') }}"
      ac_ifeel_temp: "{{ states('sensor.temp_tuya_screen_temperature') | float(22) | round | int }}"
```

### 6. Restart HA

Restart Home Assistant to load the climate entity.

---

## Migrating to ESPHome IR Blaster

Only two changes needed:

1. Update `entity_id` in the script from `remote.tuya_ir_remote_control` to your ESPHome remote entity
2. Change the raw string format in `_power_raw` and `_state_raw` variables:

```jinja2
{# From (Tuya): #}
{% set ns = namespace(p='raw:8308,4527') %}
{{ ns.p ~ ',554' }}

{# To (ESPHome): #}
{% set ns = namespace(p='[8308,4527') %}
{{ ns.p ~ ',554]' }}
```

---

## Protocol Summary

KELON168 is a 168-bit, 3-frame IR protocol (21 bytes, 343 pulses, LSB-first).

| Parameter | Value |
|-----------|-------|
| HDR_MARK | 8308 µs |
| HDR_SPACE | 4527 µs |
| BIT_MARK | 554 µs |
| ONE_SPACE | 1712 µs |
| ZER_SPACE | 554 µs |
| Frames | 3 (separated by 8308 µs gaps) |
| Total pulses | 343 |

See [KELON168_README.md](KELON168_README.md) for the full protocol specification including all byte definitions, checksums, and special modes.

---

## Tested On

- Kelon OEM bedroom AC, Electra/Tadiran branding, Israel
- Tuya IR blaster with LocalTuya RC (ClusterM fork)
- Home Assistant 2026.6.0

---

## Contributing

If you have a different Kelon/Electra/Tadiran unit and can capture IR codes, please open an issue with your raw captures. Especially useful:
- Heat mode at various fan speeds
- Dry mode
- Different temperature ranges
- Sleep mode

---

## Related Projects

- [IRremoteESP8266 KELON168](https://github.com/crankyoldgit/IRremoteESP8266) — Arduino/ESP IR library with basic KELON168 support
- [IRelectra](https://github.com/barakwei/IRelectra) — Electra AC IR for Arduino (different protocol variant)
- [tuya-ir-electra-home-assistant](https://github.com/rluvaton/tuya-ir-electra-home-assistant) — alternative Electra+Tuya HA integration
- [Davide Depau's blog](https://blog.depau.eu/2021/06/12/ir-remote-reveng/) — original KELON reverse engineering writeup

---

## License

MIT
