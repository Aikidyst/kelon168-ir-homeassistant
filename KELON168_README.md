# KELON168 IR Protocol — Bedroom AC

Fully reverse-engineered IR protocol for a **Kelon/OEM AC** (sold as Electra/Tadiran
in Israel) controlled via a **Tuya IR blaster** in Home Assistant.

---

## Hardware Context

| Component | Details |
|-----------|---------|
| AC unit | Kelon OEM (bedroom) — Electra/Tadiran branding |
| IR blaster | Tuya IR remote, LocalTuya RC integration (ClusterM fork) |
| HA entity | `remote.tuya_ir_remote_control` |
| HA version | 2026.6.0 |
| Temp sensor | `sensor.temp_tuya_screen_temperature` (bedroom, Tuya screen sensor) |
| Climate entity | `climate.bedroom_ac` (climate_template HACS integration) |

### Why raw codes are required

LocalTuya RC's `remote.send_command` stores learned codes internally as
`nec42-ext:addr=0x...,cmd=0x...` (42-bit NEC extended protocol). When transmitting,
it only sends those 42 bits — which is **25% of the KELON168 signal**. The AC ignores
truncated frames and does not respond.

The `raw:8308,4527,...` format (343 pulse values in microseconds) bypasses the NEC
decoder and sends the full signal. **Raw format is the only working approach.**

---

## Protocol Overview

**KELON168** — 168-bit, 3-frame IR protocol
21 bytes total, transmitted LSB-first within each byte.

| Frame | Bytes | Bits | Pulse count |
|-------|-------|------|-------------|
| Frame 1 (header + data) | 0–5 | 48 | 99 (incl. header) |
| Inter-frame gap | — | — | 1 (8308 µs low) |
| Frame 2 (data + checksum) | 6–13 | 64 | 129 |
| Inter-frame gap | — | — | 1 (8308 µs low) |
| Frame 3 (control + checksum) | 14–20 | 56 | 113 |
| **Total** | **21** | **168** | **343** |

### Timing constants (µs)

```
HDR_MARK  = 8308   Header mark (start of frame 1)
HDR_SPACE = 4527   Header space
BIT_MARK  = 554    Mark for every bit
ONE_SPACE = 1712   Space for bit = 1
ZER_SPACE = 554    Space for bit = 0 (physical remote may produce 625µs — both accepted)
GAP       = 8308   Inter-frame gap (low/space between frames)
```

---

## Power On/Off — Critical Finding

**The KELON168 protocol has NO absolute power-on or power-off command.**
The power frame is a **toggle** — it alternates AC state regardless of current state.

### Power ON (reliable)
Use the **TURBO frame** which unconditionally turns the AC on:
1. Send TURBO frame → AC always turns on in turbo mode
2. Send normal state frame → AC switches to desired mode/temp/fan

### Power OFF (guaranteed)
Send TURBO frame first (guarantees AC is ON), then immediately send the power toggle frame.

```
Power OFF = TURBO frame → power toggle frame
```

This eliminates the sync issue — no matter what state the AC is in, it will end up OFF.

### Power Toggle Frame Structure

```
byte2  = 0x04 | fan_code  (auto=0x04, high=0x05, med=0x06, low=0x07)
byte3  = (temp-16)<<4 | mode_lo  (remote's last known state)
byte6  = 0x95  (power frame marker, fixed)
byte7  = 0x24  (fixed — AC does not validate rolling counter)
byte15 = 0x01  (power toggle indicator)
byte20 = 0x09  (= byte15 ^ 0x08)
byte13 = XOR checksum (see formula below)
```

---

## 21-Byte State Structure

```
Byte  Typical  Field
────  ───────  ──────────────────────────────────────────────────────────────
 0    0x83     Fixed header byte 1
 1    0x06     Fixed header byte 2
 2    varies   Fan speed code (see Fan table)
 3    varies   Temperature + mode code
 4    0x00     Fixed
 5    0x00     Fixed (0x90 only for TURBO)
 6    0x8C     Fixed carrier byte (0x8D when I Feel active)
 7    varies   Mode+fan session byte (see byte7 table)
 8    0x00     Fixed
 9    0x00     Fixed
10    0x00     Fixed
11    0x00     I Feel flag: 0x80 when I Feel active, else 0x00
12    0x00     I Feel temp: remote sensor °C when I Feel active, else 0x00
13    varies   Checksum 1 = XOR(bytes 0–12) ^ 0x85
14    0x00     Fixed
15    varies   Mode/fan indicator byte
16    0x00     Fixed
17    0x00     Fixed
18    0x08     Fixed
19    0x00     Fixed
20    varies   Checksum 2 = byte15 ^ 0x08
```

---

## Checksum Formulas

### Frame 1+2 checksum (byte 13)
```
byte13 = XOR(bytes 0–12) ^ 0x85
       = byte2 ^ byte3 ^ byte6 ^ byte7 ^ byte11 ^ byte12  (simplified for normal case)
```

### Frame 3 checksum (byte 20)
```
byte20 = byte15 ^ 0x08
```

---

## Byte 3 Encoding (Temperature + Mode)

```
byte3 = (temp_code << 4) | mode_lo
temp_code = temp - 16  (range 16–30°C → codes 0x0–0xE)
```

For DRY and FAN_ONLY: temp_code = 7 (fixed, no temperature).

| Mode | mode_lo | byte3 at 22°C |
|------|---------|--------------|
| COOL | 0x2 | 0x62 |
| HEAT | 0x0 | 0x60 |
| DRY  | 0x3 | 0x73 (no temp) |
| FAN  | 0x4 | 0x74 (no temp) |

---

## Byte 2 — Fan Speed

### Normal state frames (COOL/HEAT/DRY/FAN_ONLY)

| Fan speed | byte2 |
|-----------|-------|
| auto      | 0x00  |
| low       | 0x03  |
| medium    | 0x02  |
| high      | 0x01  |

### FAN_ONLY mode

| Fan speed | byte2 |
|-----------|-------|
| auto      | **0x01** |
| low       | 0x03  |
| medium    | 0x02  |
| high      | 0x01  |

### Power toggle frame

| Fan speed | byte2 |
|-----------|-------|
| auto      | 0x04  |
| high      | 0x05  |
| medium    | 0x06  |
| low       | 0x07  |

---

## Byte 7 — Mode+Fan Session Byte

| Mode | Fan | byte7 |
|------|-----|-------|
| cool | auto | 0x05 |
| cool | low | 0x32 |
| cool | medium | 0x2E |
| cool | high | 0x2E |
| heat | auto | 0x25 |
| heat | low | 0x32 |
| heat | medium | 0x2E |
| heat | high | 0x2E |
| dry | auto | 0x28 |
| fan_only | auto | 0x2A |
| fan_only | low | 0x32 |
| fan_only | medium | 0x2E |
| fan_only | high | 0x2E |
| turbo | — | 0x38 |

---

## Byte 15 — Mode Indicator

| Condition | byte15 | byte20 |
|-----------|--------|--------|
| COOL/HEAT + fan auto | 0x02 | 0x0A |
| COOL/HEAT + explicit fan | 0x11 | 0x19 |
| DRY / FAN_ONLY | 0x06 | 0x0E |
| TURBO | 0x04 | 0x0C |
| I Feel active | 0x0D | 0x05 |
| Power toggle | 0x01 | 0x09 |

---

## Special Modes

### TURBO (Power-ON)
Turbo is used as a reliable **power-on** command — it always turns the AC on
regardless of current state. The AC enters turbo mode (16°C cool, high fan),
then the follow-up state frame switches to the desired mode.

```
byte2  = 0x01  (HIGH fan)
byte3  = 0x02  (16°C, COOL mode — forced)
byte5  = 0x90  ← turbo flag
byte6  = 0x8C
byte7  = 0x38
byte15 = 0x04
byte20 = 0x0C
```

### I Feel
The remote's built-in temperature sensor reading is sent to the AC.

```
byte6   = 0x8D  (0x8C + I Feel flag)
byte11  = 0x80  (I Feel active)
byte12  = sensor_temp (integer °C)
byte15  = 0x0D
byte20  = 0x05
byte13  recalculated including byte11/byte12
```

**In HA:** toggle `input_boolean.bedroom_ac_i_feel`. The I Feel resend automation
fires on toggle and resends the current state with I Feel overlay applied.

---

## Home Assistant Integration

### Required Helpers

| Entity | Type | Purpose |
|--------|------|---------|
| `input_select.bedroom_ac_hvac_mode` | input_select | Current mode: off/cool/heat/dry/fan_only |
| `input_number.bedroom_ac_target_temperature` | input_number | Set temp: 16–30°C, step 1 |
| `input_select.bedroom_ac_fan_mode` | input_select | Fan: auto/low/medium/high |
| `input_boolean.bedroom_ac_i_feel` | input_boolean | I Feel toggle |

### Climate Entity

Platform: `climate_template` (HACS: **litinoveweedle/hass-template-climate**)
Entity ID: `climate.bedroom_ac`
Defined in: `configuration.yaml` → `climate:` block

### Script

`script.bedroom_ac_ir_send` — stored in HA UI scripts storage (`.storage/scripts.yaml`).
Created via HA API, not in `configuration.yaml`.

Fields:
- `ac_action`: `power_off` | `power_on` | `state`
- `ac_mode`: `cool` | `heat` | `dry` | `fan_only`
- `ac_temp`: integer 16–30
- `ac_fan`: `auto` | `low` | `medium` | `high`
- `ac_ifeel`: boolean
- `ac_ifeel_temp`: integer °C

### Action Logic

| User action | ac_action sent | IR frames |
|-------------|---------------|-----------|
| Select `off` from card | `power_off` | TURBO frame + power toggle frame |
| Select mode from `off` | `power_on` | TURBO frame + state frame |
| Change temperature | `state` | State frame only |
| Change fan | `state` | State frame only |
| Toggle I Feel | (automation) | State frame with I Feel overlay |

### Automation

`automation.bedroom_ac_i_feel_resend` — fires when `input_boolean.bedroom_ac_i_feel`
changes state, condition: AC not off, sends state command with I Feel overlay.

### Hardcoded Entities

The following entity IDs are hardcoded in `configuration.yaml` (climate block):
- `sensor.temp_tuya_screen_temperature` — I Feel temperature source
- `input_boolean.bedroom_ac_i_feel` — I Feel toggle helper
- `input_select.bedroom_ac_hvac_mode` — mode helper
- `input_number.bedroom_ac_target_temperature` — temperature helper
- `input_select.bedroom_ac_fan_mode` — fan helper
- `remote.tuya_ir_remote_control` — Tuya IR blaster

---

## Known Limitations / Not Decoded

- **Absolute power off** — uses TURBO + power toggle sequence for guaranteed off.
- **HEAT mode byte7 for explicit fan** — uses COOL values as fallback (likely works).
- **DRY humidity levels** — only "none" level implemented.
- **SWING / SLEEP / TIMER** — not captured.

---

## Files

| File | Purpose |
|------|---------|
| `kelon168.py` | Python generator with self-tests |
| `climate_template_kelon168.yaml` | HA climate entity config |
| `KELON168_README.md` | This file |

---

## How to Continue in a New Chat

Paste this context:

> I have a KELON168 IR AC controlled via Tuya IR blaster in Home Assistant.
> Protocol is fully reverse-engineered. Python generator in kelon168.py.
> HA uses climate_template (litinoveweedle fork) + script.bedroom_ac_ir_send.
> Power ON = TURBO frame + state frame. Power OFF = TURBO frame → power toggle frame (guaranteed).
> Key entities: remote.tuya_ir_remote_control, climate.bedroom_ac,
> sensor.temp_tuya_screen_temperature (I Feel), input_boolean.bedroom_ac_i_feel.

Then attach kelon168.py and this README.
