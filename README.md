# RA Roto Control

Networked motor-speed controller for **Radiant Atmospheres**. Bridges show-control protocols
(**DMX512, Art-Net, sACN/E1.31**) to **RS232 serial commands** driving a **Roboteq HDC2450** brushed-DC
motor controller — with a web interface for setup, DMX personas, network config, live troubleshooting
(real motor telemetry), and manual override. Sibling project to [raDMX](../raDMX).

## What it does

```
DMX512 / Art-Net / sACN ─► ESP32-POE-ISO ─► MAX3232 ─► RS232 ─► HDC2450 ─► roto motor
                                │  ◄── telemetry (amps, volts, temp, faults) ──┘
                                └──── web UI: config · personas · override · diagnostics
```

- **One motor**, commanded over serial: `!G 1 <-1000..+1000>` — one signed value is speed **and**
  direction (0 = stop). No DAC, no op-amp, no calibration.
- **DMX personas** incl. **ultra-slow modes** (compressed command ranges) + a live **multiplier**.
  See [`docs/PERSONAS.md`](docs/PERSONAS.md).
- **Wired Ethernet + PoE + galvanic isolation** (Olimex ESP32-POE-ISO) for rugged festival deployment.
- **Layered fail-safe** — the HDC2450's own `^RWD` command-loss watchdog stops the motor if the ESP32
  goes silent (works on serial, unlike analog), backed by firmware STOP + slew limiting.
- **Real telemetry** — motor amps, battery voltage, temperature, and fault flags in the web dashboard.

## Hardware

- **Host:** Olimex ESP32-POE-ISO
- **Motor controller:** Roboteq HDC2450 (Motor 1 channel)
- **Link:** ESP32 UART → MAX3232 → HDC2450 RS232 (DB25 pins 2/3), shared ground on pin 5
- **Optional:** KF0602D SSR for remote power-enable; MAX485 + XLR for physical DMX512 input

Full pinout, wiring diagram, BOM, and bring-up checklist: [`docs/HARDWARE.md`](docs/HARDWARE.md).

## Firmware

PlatformIO + Arduino-ESP32. Serial control core, Art-Net/sACN parsers, layered fail-safe, and a minimal
async web dashboard — **compiles clean** for the ESP32-POE-ISO (RAM 13.6%, Flash 67.9%).

```bash
cd firmware
pio run -e olimex_poe_iso            # build
pio run -e olimex_poe_iso -t upload  # flash
```

## Docs

| Doc | Contents |
|-----|----------|
| [`CLAUDE.md`](CLAUDE.md) | Project guide, locked decisions, operational rules |
| [`docs/HARDWARE.md`](docs/HARDWARE.md) | Pinout, MAX3232 wiring, BOM, bring-up checklist |
| [`docs/PERSONAS.md`](docs/PERSONAS.md) | DMX persona definitions + command scaling |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Firmware module map, protocols, safety model, roadmap |

## Status

**Phase 0 — Planning + firmware scaffold.** Decisions locked, docs written, firmware compiles clean.
Nothing has run on hardware yet. Next: serial bench bring-up (MAX3232 → `?FID` link check → live `!G`).
